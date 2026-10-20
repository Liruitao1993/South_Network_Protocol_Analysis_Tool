"""GUI 自动升级检查与全自动替换模块。

纯逻辑，无 PySide/Qt 依赖，可被 `test/test_auto_updater.py` 独立测试。

三大职责：
1. VersionChecker — 从更新源拉取最新版本信息并做语义化版本比对
2. Opdater — 下载新版 exe 到临时目录，可选 SHA-256 校验
3. update.bat 编排 — 处理 Windows exe 自替换锁（运行中的 exe 无法覆盖自身）

支持两种更新源：
- Gitee Releases（默认，国内容户友好）：https://gitee.com/api/v5/repos/{owner}/{repo}/releases/latest
- 私有 HTTP 源：一个静态 version.json，形如
      {"version":"1.15.0","url":"https://host/南网协议解析工具.exe","notes":"...","sha256":"..."}
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

APP_VERSION_ATTR = "APP_VERSION"  # main_gui 的版本常量名（供外部读取，避免循环依赖）


# ─────────────────────────────────────────────────────────────
# 版本比较
# ─────────────────────────────────────────────────────────────
def _parse_version(version: str) -> list:
    """把 '1.14.4' 拆成可比较分段 [1, 14, 4]。

    过滤空段与非数字段；纯字符串段回退为字符串比较留档。
    返回 (数字列表, 尾部字符串段列表)。
    """
    numeric: list = []
    tail: list = []
    for part in str(version).strip().replace("v", "").split("."):
        part_s = part.strip()
        if not part_s:
            continue
        try:
            numeric.append(int(part_s))
        except ValueError:
            tail.append(part_s.lower())
    return numeric, tail


def compare_versions(local: str, remote: str) -> int:
    """语义化比较版本号。

    返回：
        <0  local 旧（需要更新）
        0   local == remote
        >0  local 新（不需要更新）
    """
    if isinstance(local, int):  # 传入了 APP_VERSION 常数等
        local = str(local)
    if isinstance(remote, int):
        remote = str(remote)
    ln, lt = _parse_version(local)
    rn, rt = _parse_version(remote)

    # 数字段逐段比较（较短的按 0 补齐）
    for i in range(max(len(ln), len(rn))):
        lv = ln[i] if i < len(ln) else 0
        rv = rn[i] if i < len(rn) else 0
        if lv != rv:
            return -1 if lv < rv else 1

    # 数字段相等，比较尾部字符串段
    for i in range(max(len(lt), len(rt))):
        lv = lt[i] if i < len(lt) else ""
        rv = rt[i] if i < len(rt) else ""
        if lv != rv:
            return -1 if lv < rv else 1
    return 0


def is_update_needed(local: str, remote: str) -> bool:
    """本地是否低于远程（需要更新）。"""
    return compare_versions(local, remote) < 0


# ─────────────────────────────────────────────────────────────
# 更新源
# ─────────────────────────────────────────────────────────────
class UpdateSourceError(Exception):
    """更新源拉取/解析失败。"""


def default_gitee_api(owner: str, repo: str) -> str:
    return f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/latest"


def _extract_release_info(data: Dict[str, Any], download_keywords=("exe",)) -> Dict[str, Any]:
    """从 releases API 响应或 version.json 提取统一信息。

    返回 {"version", "url", "notes", "sha256"}
    """
    # 版本：tag_name（Gitee/私有都常用）或 version
    tag = data.get("tag_name") or data.get("name") or data.get("version") or data.get("tag")
    if tag is None:
        raise UpdateSourceError("更新源缺少版本号字段 (tag_name/version)")

    # 下载 URL：优先 assets 里 exe 资产，其次顶层 url / browser_download_url
    url = data.get("url")
    assets = data.get("assets") or []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        aname = str(asset.get("name") or "")
        try:
            if any(k.lower() in aname.lower() for k in download_keywords):
                url = asset.get("browser_download_url") or asset.get("download_url") or asset.get("url")
                break
        except Exception:
            continue
    if not url:
        # 私有 version.json 习惯用顶层 url
        url = data.get("download_url") or data.get("url") or data.get("browser_download_url")
    if not url:
        raise UpdateSourceError("更新源缺少下载地址 (assets[].browser_download_url 或 url)")

    return {
        "version": str(tag),
        "url": str(url),
        "notes": str(data.get("notes") or data.get("body") or data.get("description") or ""),
        "sha256": str(data.get("sha256") or "").strip(),
    }


def _http_get_text(url: str, timeout: float = 15.0) -> str:
    """标准库 HTTP GET 文本（零依赖）。可被替换/测试注入。"""
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jiexigongju-updater",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        enc = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(enc, errors="replace")


class VersionChecker:
    """从更新源拉取最新版本信息并比对。"""

    def __init__(self, source_config: Dict[str, Any], http_get: Optional[Callable] = None):
        self.source_config = dict(source_config or {})
        self.http_get = http_get or _http_get_text

    def build_url(self) -> str:
        cfg = self.source_config
        stype = cfg.get("source_type", "gitee")
        if stype == "private":
            url = cfg.get("private_url", "").strip()
            if not url:
                raise UpdateSourceError("私有源未配置 private_url")
            return url
        # gitee（默认）
        owner = cfg.get("gitee_owner", "").strip()
        repo = cfg.get("gitee_repo", "").strip()
        if not owner or not repo:
            raise UpdateSourceError("Gitee 源未配置 gitee_owner / gitee_repo")
        return default_gitee_api(owner, repo)

    def fetch_latest(self) -> Dict[str, Any]:
        """拉取并解析最新版本信息。失败抛 UpdateSourceError。"""
        url = self.build_url()
        text = self.http_get(url)
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            raise UpdateSourceError(f"更新源返回的不是合法 JSON: {text[:120]}")
        return _extract_release_info(data)

    def fetch_all_releases(self) -> List[Dict[str, Any]]:
        """拉取全部版本列表（Gitee 源）；私有源退回单版本。

        返回按版本号降序排序的 [{version, url, notes, sha256, created_at}]。
        失败抛 UpdateSourceError。
        """
        cfg = self.source_config
        stype = cfg.get("source_type", "gitee")
        list_urls = {
            "gitee": "https://gitee.com/api/v5/repos/%s/%s/releases"
                     % (cfg.get("gitee_owner", "").strip(),
                        cfg.get("gitee_repo", "").strip()),
        }
        if stype not in list_urls:
            # 私有源无非 latest 概念，退回单版本
            latest = self.fetch_latest()
            return [latest] if latest else []
        text = self.http_get(list_urls[stype])
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            raise UpdateSourceError(f"更新源返回的不是合法 JSON: {text[:120]}")
        if not isinstance(data, list):
            raise UpdateSourceError("Gitee releases 接口应返回数组")
        out = []
        for rel in data:
            try:
                info = _extract_release_info(rel)
                info["created_at"] = str(rel.get("created_at") or "")
                info["prerelease"] = bool(rel.get("prerelease"))
                out.append(info)
            except Exception:
                continue  # 略过无 exe 资产的 release
        out.sort(key=lambda r: _parse_version(r["version"]), reverse=True)
        return out

    def check(self, local_version: str) -> Dict[str, Any]:
        """拉取最新版并判断是否需要更新。

        返回 {"available": bool, "latest": {...}} 或抛 UpdateSourceError。
        """
        latest = self.fetch_latest()
        needed = is_update_needed(local_version, latest["version"])
        return {"available": needed, "local": local_version, "latest": latest}


# ─────────────────────────────────────────────────────────────
# 下载与校验
# ─────────────────────────────────────────────────────────────
class DownloadError(Exception):
    """下载失败。"""


def _download_to_stream(url: str, dest_path: Path, progress_cb=None, http_get_binary=None, timeout: float = 120.0) -> Path:
    """流式下载 url 到 dest_path，可选进度回调 percent(float 0..100)。"""
    if http_get_binary is None:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jiexigongju-updater",
                "Accept": "application/octet-stream, application/zip, */*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length") or 0) or None
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            done = 0
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb and total:
                        progress_cb(min(100.0, done * 100.0 / total))
    else:
        data = http_get_binary(url)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)
        if progress_cb:
            progress_cb(100.0)

    if dest_path.stat().st_size == 0:
        raise DownloadError("下载完成但文件为空")

    # 服务器无 Content-Length 时，进度回调 100（无总长信息则无从计算）
    if progress_cb:
        progress_cb(100.0)
    return dest_path


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 16)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────
# 就地替换（Windows exe 自替换）
# ─────────────────────────────────────────────────────────────
UPDATE_BAT_TEMPLATE = r"""@echo off
rem 自动升级：等待原进程退出 -> 覆盖可执行文件 -> 冷启动新版
setlocal
set "NEW=__NEW__"
set "OLD=__OLD__"
set "IMG=__IMG__"
:wait_loop
tasklist /fi "IMAGENAME eq %IMG%" 2>nul | find /i "%IMG%" >nul
if not errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    goto :wait_loop
)
copy /y /b "%NEW%" "%OLD%" >nul
start "" "%OLD%"
rem 清理临时下载
del "%NEW%" >nul 2>nul
goto :eof
"""


def build_update_bat(new_exe: Path, old_exe: Path) -> str:
    """生成 update.bat 内容。用显式替换避免批处理 `%` 与 str.format 冲突。"""
    old_basename = Path(old_exe).name
    return (
        UPDATE_BAT_TEMPLATE.replace("__NEW__", str(new_exe))
        .replace("__OLD__", str(old_exe))
        .replace("__IMG__", old_basename)
    )


class Opdater:
    """下载新版 exe 并编排就地替换（Windows exe 自替换）。"""

    def __init__(self, http_get_binary=None):
        self.http_get_binary = http_get_binary

    def download(self, url: str, dest_file: Path, progress_cb=None) -> Path:
        """下载到 dest_file；服务器给出 Content-Length 时回调 percent(0..100)。"""
        return _download_to_stream(url, dest_file, progress_cb=progress_cb,
                                   http_get_binary=self.http_get_binary)

    def verify(self, dest_file: Path, expected_sha256: str) -> bool:
        """可选 SHA-256 校验；无预期值视为通过。"""
        if not expected_sha256:
            return True
        if len(expected_sha256) not in (64, 128):
            return False
        calc = sha256_of(dest_file)
        return calc.lower() == expected_sha256.strip().lower()

    def stage_and_replace(self, new_exe: Path, running_exe: Path) -> Optional[Path]:
        """写 update.bat 并以分离进程启动；返回 bat 路径，失败返回 None。"""
        running_exe = Path(running_exe).resolve()
        new_exe = Path(new_exe).resolve()
        tmp_dir = Path(tempfile.gettempdir()) / "jiexigongju_updater"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        bat = tmp_dir / "update.bat"
        bat.write_text(build_update_bat(new_exe, running_exe), encoding="gbk", errors="replace")
        try:
            subprocess.Popen(
                [str(bat), str(new_exe), str(running_exe)],
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
                start_new_session=True,
            )
            return bat
        except Exception:
            return None

    def make_backup(self, running_exe: Path) -> Optional[Path]:
        """把当前 exe 备份到临时目录（可选），失败返回 None。"""
        try:
            src = Path(running_exe)
            if not src.exists():
                return None
            tmp_dir = Path(tempfile.gettempdir()) / "jiexigongju_updater"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            bak = tmp_dir / (src.stem + "_bak" + src.suffix)
            shutil.copy2(src, bak)
            return bak
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────
# 顶层便捷函数（GUI 与测试共用）
# ─────────────────────────────────────────────────────────────
DEFAULT_UPDATE_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "check_on_start": True,
    "source_type": "gitee",
    "gitee_owner": "lirt1993_admin",
    "gitee_repo": "jiexigongju",
    "private_url": "",
    "sha256_verify": True,
    "last_check": "",
}


def merge_update_config(user_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把 config.json 的 update 段与默认值合并，保证缺省字段存在。"""
    merged = dict(DEFAULT_UPDATE_CONFIG)
    if isinstance(user_cfg, dict):
        merged.update(user_cfg)
    return merged


def check_for_update(local_version: str, update_config: Dict[str, Any], http_get=None) -> Dict[str, Any]:
    """一步式：按配置拉取最新版并判断是否需要更新。

    返回 {"needed": bool, "latest": {...}, "error": str|None}
    网络失败不抛异常，error 字段描述原因（GUI 层可静默）。
    """
    cfg = merge_update_config(update_config)
    if not cfg.get("enabled", True):
        return {"needed": False, "latest": None, "error": None}
    try:
        checker = VersionChecker(cfg, http_get=http_get)
        result = checker.check(local_version)
        return {"needed": result["available"], "latest": result["latest"], "error": None}
    except Exception as e:  # 网络/解析异常均降级，不阻塞主程序
        return {"needed": False, "latest": None, "error": str(e)}