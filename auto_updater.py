"""GUI 自动升级检查与全自动替换模块。

纯逻辑，无 PySide/Qt 依赖，可被 `test/test_auto_updater.py` 独立测试。

三大职责：
1. VersionChecker — 从更新源拉取最新版本信息并做语义化版本比对
2. Opdater — 下载新版 exe 到临时目录，可选 SHA-256 校验
3. update.bat 编排 — 处理 Windows exe 自替换锁（运行中的 exe 无法覆盖自身）

支持三种更新源：
- GitHub Releases（**默认**，作者公开仓库，无需鉴权）：
      https://api.github.com/repos/{owner}/{repo}/releases/latest
      https://api.github.com/repos/{owner}/{repo}/releases?per_page=30   （版本列表）
  顺带把 GitHub 资产的 `digest`（`sha256:...`）取作校验值，并带出 `html_url`
  （发布页）与更新说明 `body`（markdown，由 GUI 渲染）。
- Gitee Releases（国内备用）：https://gitee.com/api/v5/repos/{owner}/{repo}/releases/latest
- 私有 HTTP 源：一个静态 version.json，形如
      {"version":"1.15.0","url":"https://host/南网协议解析工具.exe","notes":"...","sha256":"..."}
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
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


# ── 默认更新源：作者公开 GitHub 仓库 Release ───────────────
# 这里是**代码级**默认值；`main_gui.AUTHOR_GITHUB_URL` 仍是作者仓库地址的唯一来源，
# 启动时用 `merge_update_config(..., repo_url=AUTHOR_GITHUB_URL)` 把它解析进来，
# 于是改地址只改那一处（「关于」的 Star 按钮与自动升级源同源）。
DEFAULT_GITHUB_OWNER = "Liruitao1993"
DEFAULT_GITHUB_REPO = "South_Network_Protocol_Analysis_Tool"
RELEASES_PER_PAGE = 30
GITHUB_RELEASE_TIMEOUT = 15.0

_GITHUB_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/\s?#]+)/([^/\s?#]+)",
    re.IGNORECASE,
)


def parse_github_repo_url(url: str) -> Dict[str, str]:
    """从仓库地址解析出 {"github_owner","github_repo"}；解析不出返回 {}。

    容忍尾部 `/`、`/releases`、`.git`、查询串等写法；
    结果只含两个键，便于直接 `merge_update_config` 合并。
    """
    m = _GITHUB_REPO_RE.match(str(url or "").strip())
    if not m:
        return {}
    owner = (m.group(1) or "").strip()
    repo = (m.group(2) or "").strip()
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]
    if not owner or not repo:
        return {}
    return {"github_owner": owner, "github_repo": repo}


def github_repo_url(owner: str, repo: str) -> str:
    """仓库主页地址（失败提示里给用户手动访问用）。"""
    return f"https://github.com/{owner}/{repo}"


def default_github_api(owner: str, repo: str) -> str:
    """GitHub 最新 Release 接口。"""
    return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"


def default_github_releases_api(owner: str, repo: str, per_page: int = RELEASES_PER_PAGE) -> str:
    """GitHub Release 列表接口（版本列表对话框用）。"""
    return f"https://api.github.com/repos/{owner}/{repo}/releases?per_page={int(per_page)}"


def describe_http_status(code: int) -> str:
    """把 HTTP 状态码翻译成用户能看懂的一句话（不暴露英文栈）。"""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "更新源返回了无法识别的响应"
    if code == 404:
        return "更新源地址不存在（HTTP 404）——请检查仓库地址，或该仓库还没有发布 Release"
    if code == 401:
        return "更新源需要鉴权（HTTP 401）——该仓库可能不是公开仓库"
    if code in (403, 429):
        return f"更新源拒绝请求或触发频率限制（HTTP {code}）——请稍后再试"
    if 500 <= code < 600:
        return f"更新源服务器错误（HTTP {code}）——请稍后再试"
    if 400 <= code < 500:
        return f"请求被拒绝（HTTP {code}）"
    return f"更新源返回 HTTP {code}"


def default_gitee_api(owner: str, repo: str) -> str:
    return f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/latest"


def _digest_to_sha256(digest: str) -> str:
    """把 GitHub 资产的 digest（`sha256:abc…`）转成裸 sha256；非 sha256/非法长度返回 ''。"""
    text = str(digest or "").strip()
    if not text:
        return ""
    if ":" in text:
        algo, _, value = text.partition(":")
        if algo.strip().lower() != "sha256":
            return ""
        text = value.strip()
    text = text.lower()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        return ""
    return text


# 源码压缩包不是「可自动替换的安装包」，即便命中了下载关键字也要排除
_SOURCE_ARCHIVE_HINTS = ("source code", "source.zip", "src.zip", "源码")

# **接口端点不是下载地址**：GitHub/Gitee 的 release 对象顶层 `url` 指向 API 自身
# （如 https://api.github.com/repos/o/r/releases/12345），拿它当下载地址会把
# 接口返回的 JSON 当成新 exe 覆盖自身（1.23.87 独立验证实测：无资产的旧版本
# 1.8.2 正是这个形态）。一律拒绝。
_API_URL_HINTS = ("api.github.com/repos/", "gitee.com/api/v5/repos/")


def _looks_like_api_url(url: str) -> bool:
    """判断是否指向 releases API 端点（而非资产直链）。"""
    u = str(url or "").strip().lower()
    return any(h in u for h in _API_URL_HINTS)


def _is_release_object(data: Dict[str, Any]) -> bool:
    """是否 releases API 的「发布对象」。

    发布对象（GitHub/Gitee）→ 下载地址**只能**来自 assets；私有 version.json
    （只有 version/url/notes/sha256 这些键）才允许用顶层 url。
    """
    return (
        isinstance(data.get("assets"), list)
        or bool(data.get("tag_name"))
        or bool(data.get("html_url"))
    )


def _pick_asset(assets, download_keywords) -> Dict[str, str]:
    """从 release assets 里挑一个可下载资产，返回 {"name","url","digest"}（没有则 {}）。

    命中规则：name 含下载关键字（默认 exe）且不是源码压缩包；优先浏览器直链
    （`browser_download_url`，GitHub/Gitee 都有），回退 API url。
    """
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        lower = name.lower()
        try:
            if not any(str(k).lower() in lower for k in download_keywords):
                continue
        except Exception:
            continue
        if any(h in lower for h in _SOURCE_ARCHIVE_HINTS):
            continue
        url = (
            asset.get("browser_download_url")
            or asset.get("download_url")
            or asset.get("url")
        )
        if not url:
            continue
        return {
            "name": name,
            "url": str(url),
            "digest": str(asset.get("digest") or ""),
        }
    return {}


def _extract_release_info(data: Dict[str, Any], download_keywords=("exe",)) -> Dict[str, Any]:
    """从 releases API 响应或 version.json 提取统一信息。

    返回 {"version","url","notes","sha256","asset_name","html_url","published_at"}
    （后三项缺失时为空串，便于 GUI 直接读而不用 get 兜底）。
    """
    # 版本：tag_name（Gitee/GitHub/私有都常用）或 name/version
    tag = data.get("tag_name") or data.get("name") or data.get("version") or data.get("tag")
    if tag is None:
        raise UpdateSourceError("更新源缺少版本号字段 (tag_name/version)")

    # 下载 URL：优先 assets 里的安装包资产，其次顶层 url / browser_download_url
    asset = _pick_asset(data.get("assets"), download_keywords)
    url = asset.get("url") or ""
    if not url and not _is_release_object(data):
        # 私有 version.json 习惯用顶层 url
        fallback = (
            data.get("download_url") or data.get("url") or data.get("browser_download_url")
        )
        url = str(fallback or "")
    if url and _looks_like_api_url(url):
        # 兜底：任何路径下都不接受接口端点（宁可报错，也不能把 JSON 当安装包）
        url = ""
    if not url:
        raise UpdateSourceError(
            "该版本没有可下载的安装包资产（assets 里没有 exe/压缩包，"
            "或只有源码包）——请在「配置→更新设置」确认更新源，或到发布页手动下载"
        )

    # 校验值：顶层 sha256 优先（私有 version.json），否则取资产 digest（GitHub: sha256:…）
    sha256 = str(data.get("sha256") or "").strip().lower()
    if not sha256:
        sha256 = _digest_to_sha256(asset.get("digest", ""))

    return {
        "version": str(tag),
        "url": str(url),
        "notes": str(data.get("notes") or data.get("body") or data.get("description") or ""),
        "sha256": sha256,
        "asset_name": str(asset.get("name") or ""),
        "html_url": str(data.get("html_url") or ""),
        "published_at": str(data.get("published_at") or data.get("created_at") or ""),
    }


def _http_get_text(url: str, timeout: float = GITHUB_RELEASE_TIMEOUT) -> str:
    """标准库 HTTP GET 文本（零依赖）。可被替换/测试注入。

    失败一律转成 UpdateSourceError 并给出中文原因（404/403 等状态码经
    `describe_http_status` 翻译），避免 GUI 直接抛英文 urllib 栈。
    """
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jiexigongju-updater",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, errors="replace")
    except urllib.error.HTTPError as e:  # 是 URLError 子类，必须先于它捕获
        raise UpdateSourceError(describe_http_status(getattr(e, "code", 0))) from e
    except urllib.error.URLError as e:
        raise UpdateSourceError(f"网络请求失败：{getattr(e, 'reason', e)}") from e
    except (TimeoutError, OSError) as e:
        raise UpdateSourceError(f"网络请求失败：{e}") from e


class VersionChecker:
    """从更新源拉取最新版本信息并比对。"""

    def __init__(self, source_config: Dict[str, Any], http_get: Optional[Callable] = None):
        self.source_config = merge_update_config(source_config)
        self.http_get = http_get or _http_get_text

    def _github_owner_repo(self) -> tuple:
        cfg = self.source_config
        owner = str(cfg.get("github_owner", "") or "").strip()
        repo = str(cfg.get("github_repo", "") or "").strip()
        if not owner or not repo:
            raise UpdateSourceError("GitHub 源未配置 github_owner / github_repo")
        return owner, repo

    def build_url(self) -> str:
        cfg = self.source_config
        stype = cfg.get("source_type", "github")
        if stype == "private":
            url = str(cfg.get("private_url", "") or "").strip()
            if not url:
                raise UpdateSourceError("私有源未配置 private_url")
            return url
        if stype == "gitee":
            owner = str(cfg.get("gitee_owner", "") or "").strip()
            repo = str(cfg.get("gitee_repo", "") or "").strip()
            if not owner or not repo:
                raise UpdateSourceError("Gitee 源未配置 gitee_owner / gitee_repo")
            return default_gitee_api(owner, repo)
        # github（默认）
        owner, repo = self._github_owner_repo()
        return default_github_api(owner, repo)

    def build_list_url(self) -> str:
        """版本列表接口地址（github / gitee；私有源无列表概念）。"""
        cfg = self.source_config
        stype = cfg.get("source_type", "github")
        if stype == "private":
            raise UpdateSourceError("私有源没有版本列表，只能取最新版")
        if stype == "gitee":
            owner = str(cfg.get("gitee_owner", "") or "").strip()
            repo = str(cfg.get("gitee_repo", "") or "").strip()
            if not owner or not repo:
                raise UpdateSourceError("Gitee 源未配置 gitee_owner / gitee_repo")
            return f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases"
        owner, repo = self._github_owner_repo()
        return default_github_releases_api(owner, repo)

    def release_page_url(self) -> str:
        """该源的「发布页」地址（GitHub/Gitee 仓库的 releases 页）。"""
        cfg = self.source_config
        stype = cfg.get("source_type", "github")
        if stype == "gitee":
            owner = str(cfg.get("gitee_owner", "") or "").strip()
            repo = str(cfg.get("gitee_repo", "") or "").strip()
            return f"https://gitee.com/{owner}/{repo}/releases" if owner and repo else ""
        if stype == "private":
            return ""
        owner, repo = self._github_owner_repo()
        return f"{github_repo_url(owner, repo)}/releases"

    def fetch_latest(self) -> Dict[str, Any]:
        """拉取并解析最新版本信息。失败抛 UpdateSourceError。"""
        url = self.build_url()
        text = self.http_get(url)
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            raise UpdateSourceError(f"更新源返回的不是合法 JSON: {str(text)[:120]}")
        if not isinstance(data, dict):
            raise UpdateSourceError("更新源返回的不是单个 Release 对象")
        return _extract_release_info(data)

    def fetch_all_releases(self) -> List[Dict[str, Any]]:
        """拉取全部版本列表（GitHub / Gitee）；私有源退回单版本。

        返回按版本号降序排序的 [{version, url, notes, sha256, created_at, ...}]。
        草稿（draft）一律略过——作者还没打算放出去。失败抛 UpdateSourceError。
        """
        stype = self.source_config.get("source_type", "github")
        if stype == "private":
            latest = self.fetch_latest()
            return [latest] if latest else []
        text = self.http_get(self.build_list_url())
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            raise UpdateSourceError(f"更新源返回的不是合法 JSON: {str(text)[:120]}")
        if not isinstance(data, list):
            raise UpdateSourceError("版本列表接口应返回数组")
        out = []
        for rel in data:
            if not isinstance(rel, dict) or rel.get("draft"):
                continue
            try:
                info = _extract_release_info(rel)
            except Exception:
                continue  # 略过无安装包资产的 release
            info["created_at"] = str(rel.get("created_at") or info.get("published_at") or "")
            info["prerelease"] = bool(rel.get("prerelease"))
            out.append(info)
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
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jiexigongju-updater",
                "Accept": "application/octet-stream, application/zip, */*",
            },
        )
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                total = int(resp.headers.get("Content-Length") or 0) or None
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
        except urllib.error.HTTPError as e:
            raise DownloadError(describe_http_status(getattr(e, "code", 0))) from e
        except urllib.error.URLError as e:
            raise DownloadError(f"下载失败：{getattr(e, 'reason', e)}") from e
        except (TimeoutError, OSError) as e:
            raise DownloadError(f"下载失败：{e}") from e
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


# Windows PE 可执行文件的最小长度：DOS 头(64) + PE 头，远小于真实 exe
MIN_PE_BYTES = 1024


def is_pe_executable(path: Path) -> bool:
    """下载物是不是 Windows 可执行文件（校验 `MZ` 魔数 + 最小体积）。

    这是**替换 exe 前的最后一道闸**：更新源给错地址时（接口 JSON、登录 HTML、
    错误页）体积与魔数都对不上，宁可报错也不能把正在运行的 exe 覆盖成垃圾。
    读不出来/文件不存在返回 False。
    """
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size < MIN_PE_BYTES:
            return False
        with open(p, "rb") as f:
            return f.read(2) == b"MZ"
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────
# 就地替换（Windows exe 自替换）
# ─────────────────────────────────────────────────────────────
UPDATE_BAT_TEMPLATE = r"""@echo off
rem 自动升级（带兜底）：等旧进程退出 -> 备份 -> 覆盖 -> 大小校验 -> 启动 -> 15 秒健康检查
rem 任何一步失败都回滚到 %OLD%.bak，保证用户手上始终有一个能启动的 exe
setlocal
set "NEW=__NEW__"
set "OLD=__OLD__"
set "IMG=__IMG__"
set "BAK=%OLD%.bak"

rem 1) 等旧进程完全退出（同名进程可能不止一个）
:wait_loop
tasklist /fi "IMAGENAME eq %IMG%" 2>nul | find /i "%IMG%" >nul
if not errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    goto :wait_loop
)

rem 2) 新包不存在：什么都不动，直接启动旧版
if not exist "%NEW%" (
    if exist "%OLD%" start "" "%OLD%"
    goto :eof
)

rem 3) 备份旧版（移动失败说明文件被占用，直接放弃本次升级，绝不动旧文件）
if exist "%BAK%" del /f /q "%BAK%" >nul 2>nul
if exist "%OLD%" move /y "%OLD%" "%BAK%" >nul 2>nul
if exist "%OLD%" (
    del /f /q "%NEW%" >nul 2>nul
    start "" "%OLD%"
    goto :eof
)

rem 4) 覆盖并校验大小（不等长 = 复制不完整，回滚）
copy /y /b "%NEW%" "%OLD%" >nul 2>nul
for %%A in ("%NEW%") do set "SZ_NEW=%%~zA"
for %%A in ("%OLD%") do set "SZ_OLD=%%~zA"
if not "%SZ_NEW%"=="%SZ_OLD%" goto :rollback

rem 5) 启动新版并做健康检查：15 秒后进程仍在才算成功
start "" "%OLD%"
ping 127.0.0.1 -n 16 >nul
tasklist /fi "IMAGENAME eq %IMG%" 2>nul | find /i "%IMG%" >nul
if errorlevel 1 goto :rollback

del /f /q "%NEW%" >nul 2>nul
goto :eof

rem 6) 回滚：删掉可疑的新文件 -> 还原备份 -> 启动旧版（删除可能被占用，重试 10 次）
:rollback
set "TRY=0"
:rb_del
if not exist "%OLD%" goto :rb_move
del /f /q "%OLD%" >nul 2>nul
set /a TRY+=1
if %TRY% GEQ 10 goto :rb_move
ping 127.0.0.1 -n 2 >nul
goto :rb_del
:rb_move
if exist "%BAK%" move /y "%BAK%" "%OLD%" >nul 2>nul
if exist "%OLD%" start "" "%OLD%"
del /f /q "%NEW%" >nul 2>nul
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
def summarize_notes(notes: str, limit: int = 80) -> str:
    """把 Release 说明（markdown 多行）压成一行摘要，供状态栏/提示气泡使用。

    去掉 markdown 语法噪音（标题符号、表格竖线、行内代码/加粗标记），
    空白折叠后用 `…` 截断——只做展示，不改动原文（原文另有完整展示）。
    """
    text = str(notes or "")
    if not text.strip():
        return ""
    out_lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("---"):  # 分隔线本身没有信息量
            continue
        s = s.lstrip("#>").strip()  # 标题 / 引用前缀
        s = re.sub(r"^\s*[-*+]\s+", "", s)  # 列表前缀
        s = s.replace("|", " ").replace("`", "").replace("**", "").strip()
        if not s or set(s) <= {"-", ":", " "}:  # markdown 表格对齐行
            continue
        out_lines.append(s)
        if sum(len(x) for x in out_lines) >= limit:
            break
    joined = " ".join(" ".join(out_lines).split())
    return joined[:limit] + ("…" if len(joined) > limit else "")


DEFAULT_UPDATE_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "check_on_start": True,
    # 默认走作者公开 GitHub Release（无需鉴权、随包更新即生效）
    "source_type": "github",
    "github_owner": DEFAULT_GITHUB_OWNER,
    "github_repo": DEFAULT_GITHUB_REPO,
    # 备用源：Gitee（国内节点）/ 自建私有 HTTP（静态 version.json）
    "gitee_owner": "",
    "gitee_repo": "",
    "private_url": "",
    "sha256_verify": True,
    "last_check": "",
}


def merge_update_config(
    user_cfg: Optional[Dict[str, Any]], repo_url: str = ""
) -> Dict[str, Any]:
    """把 config.json 的 update 段与默认值合并，保证缺省字段存在。

    `repo_url`（可选）= 作者仓库地址（`main_gui.AUTHOR_GITHUB_URL`）：能解析出
    owner/repo 时**作为默认值**填入，让「仓库地址」在项目里只有一处来源；
    用户显式写进 config.json 的 github_owner/github_repo 仍然优先。
    """
    merged = dict(DEFAULT_UPDATE_CONFIG)
    github_defaults = {
        "github_owner": DEFAULT_GITHUB_OWNER,
        "github_repo": DEFAULT_GITHUB_REPO,
    }
    if repo_url:
        github_defaults.update(parse_github_repo_url(repo_url) or {})
    merged.update(github_defaults)
    if isinstance(user_cfg, dict):
        merged.update(user_cfg)
    # 空串视为「未设置」（设置对话框里清空输入框 = 回到默认）——
    # 否则会拿着空 owner 去请求 GitHub，报错原因还看不出是配置问题
    for key, val in github_defaults.items():
        if not str(merged.get(key) or "").strip():
            merged[key] = val
    return merged


def github_fields_for_save(owner: str, repo: str, repo_url: str = "") -> Dict[str, str]:
    """「更新设置」保存时用：与默认值相同的 owner/repo 写空串（回落默认）。

    默认值 = 内置常量，或在能解析时以 `repo_url`（`AUTHOR_GITHUB_URL`）为准。
    若把默认值原样落盘，用户**点过一次确定**之后改 `AUTHOR_GITHUB_URL` 就不再生效
    （显式配置优先），「仓库地址唯一来源」会被悄悄破坏 —— 所以这里存空串，
    下次打开对话框仍回显解析出来的同一个默认值，用户看不到差别。
    """
    defaults = {
        "github_owner": DEFAULT_GITHUB_OWNER,
        "github_repo": DEFAULT_GITHUB_REPO,
    }
    if repo_url:
        defaults.update(parse_github_repo_url(repo_url) or {})
    out = {"github_owner": str(owner or "").strip(), "github_repo": str(repo or "").strip()}
    for key, val in defaults.items():
        if out[key] == str(val or "").strip():
            out[key] = ""
    return out


_UNSAFE_FILENAME_CHARS = '\\/:*?"<>|'


def safe_file_stem(text: str, fallback: str = "new") -> str:
    """把版本号等文本转成可安全拼进文件名的片段。

    tag 里出现 `/`（如 `release/1.24`）会变成子目录、`:` 等字符在 Windows 非法，
    直接拼进临时文件名会让下载以 OSError 表现为「下载失败」。空白与控制字符也替换掉。
    """
    cleaned = "".join(
        "_" if (c in _UNSAFE_FILENAME_CHARS or ord(c) < 32) else c
        for c in str(text or "")
    ).strip().strip(".")
    return cleaned or fallback


def describe_source(update_config: Dict[str, Any]) -> str:
    """给用户看的一句话更新源描述（对话框/日志用，不含 URL 细节）。"""
    cfg = merge_update_config(update_config)
    stype = cfg.get("source_type", "github")
    if stype == "private":
        return f"私有 HTTP（{cfg.get('private_url', '') or '未配置'}）"
    if stype == "gitee":
        owner = str(cfg.get("gitee_owner", "") or "")
        repo = str(cfg.get("gitee_repo", "") or "")
        return f"Gitee Releases（{owner}/{repo}）" if owner and repo else "Gitee Releases（未配置）"
    owner = str(cfg.get("github_owner", "") or "")
    repo = str(cfg.get("github_repo", "") or "")
    return f"GitHub Releases（{owner}/{repo}）" if owner and repo else "GitHub Releases（未配置）"


def check_for_update(
    local_version: str,
    update_config: Dict[str, Any],
    http_get=None,
    repo_url: str = "",
) -> Dict[str, Any]:
    """一步式：按配置拉取最新版并判断是否需要更新。

    返回 {"needed": bool, "latest": {...}, "error": str|None}
    网络失败不抛异常，error 字段描述原因（GUI 层可静默）。
    """
    cfg = merge_update_config(update_config, repo_url=repo_url)
    if not cfg.get("enabled", True):
        return {"needed": False, "latest": None, "error": None}
    try:
        checker = VersionChecker(cfg, http_get=http_get)
        result = checker.check(local_version)
        return {"needed": result["available"], "latest": result["latest"], "error": None}
    except Exception as e:  # 网络/解析异常均降级，不阻塞主程序
        return {"needed": False, "latest": None, "error": str(e)}