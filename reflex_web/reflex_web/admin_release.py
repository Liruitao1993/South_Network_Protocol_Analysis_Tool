# -*- coding: utf-8 -*-
"""管理员发布管理后端逻辑（纯逻辑，无 UI 依赖）

职责：
- AdminConfig：管理员密码配置读写与校验
- ReleaseManager：exe 发布、回滚、版本列表、SHA-256 计算

与 auto_updater.py 私有源 version.json 格式完全兼容：
    {version, url, notes, sha256}
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# ═══════════════════════════════════════════════════════════════
# AdminConfig
# ═══════════════════════════════════════════════════════════════

DEFAULT_ADMIN_PASSWORD = "admin123"


class AdminConfig:
    """管理员密码配置（基于 json 文件）

    配置文件结构：
    {
        "password_hash": "sha256(salt + password)",
        "password_salt": "随机十六进制盐",
        "created_at": "ISO 时间戳",
        "is_default_password": true/false
    }
    """

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self._data: Dict = {}
        self._load_or_init()

    def _load_or_init(self):
        if self.config_path.exists():
            try:
                self._data = json.loads(self.config_path.read_text(encoding="utf-8"))
                return
            except Exception:
                pass
        # 初始化默认配置
        salt = secrets.token_hex(16)
        self._data = {
            "password_hash": _hash_password(salt, DEFAULT_ADMIN_PASSWORD),
            "password_salt": salt,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "is_default_password": True,
        }
        self._save()

    def _save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def verify_password(self, password: str) -> bool:
        if not password:
            return False
        salt = self._data.get("password_salt", "")
        expected = self._data.get("password_hash", "")
        actual = _hash_password(salt, password)
        return secrets.compare_digest(expected, actual)

    def change_password(self, old_password: str, new_password: str) -> Tuple[bool, str]:
        """修改密码。返回 (成功, 消息)"""
        if not self.verify_password(old_password):
            return False, "原密码错误"
        if not new_password or len(new_password) < 6:
            return False, "新密码至少 6 位"
        salt = secrets.token_hex(16)
        self._data["password_hash"] = _hash_password(salt, new_password)
        self._data["password_salt"] = salt
        self._data["is_default_password"] = False
        self._save()
        return True, "密码修改成功"

    @property
    def is_default_password(self) -> bool:
        return bool(self._data.get("is_default_password", False))


def _hash_password(salt: str, password: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════
# ReleaseManager
# ═══════════════════════════════════════════════════════════════

@dataclass
class VersionInfo:
    version: str
    url: str
    notes: str
    sha256: str
    size_mb: float = 0.0
    exe_name: str = ""
    published_at: str = ""


class ReleaseManager:
    """版本发布管理器

    目录结构：
        downloads/
            南网协议解析工具.exe    # 当前发布的 exe（固定文件名，方便下载页展示）
            version.json           # 当前版本信息
            archive/               # 历史版本归档
                1.13.0.exe
                1.14.0.exe
    """

    # 当前发布的 exe 固定文件名（与客户端下载页/auto_updater 对齐）
    CURRENT_EXE_NAME = "南网协议解析工具.exe"

    def __init__(self, downloads_dir: Path):
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir = self.downloads_dir / "archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    # ── 基础工具 ─────────────────────────────────────────────

    def current_exe_path(self) -> Path:
        return self.downloads_dir / self.CURRENT_EXE_NAME

    def version_json_path(self) -> Path:
        return self.downloads_dir / "version.json"

    def is_valid_exe(self, data: bytes) -> bool:
        """校验 PE 文件头 MZ"""
        return len(data) >= 2 and data[:2] == b"MZ"

    # ── 读取 ─────────────────────────────────────────────────

    def get_current_version(self) -> Optional[VersionInfo]:
        """读取当前 version.json"""
        vj = self.version_json_path()
        if not vj.exists():
            return None
        try:
            data = json.loads(vj.read_text(encoding="utf-8"))
        except Exception:
            return None
        exe_name = data.get("exe_name", "") or self.CURRENT_EXE_NAME
        exe = self.downloads_dir / exe_name
        size_mb = round(exe.stat().st_size / 1024 / 1024, 2) if exe.exists() else 0.0
        mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exe.stat().st_mtime)) if exe.exists() else ""
        return VersionInfo(
            version=data.get("version", ""),
            url=data.get("url", ""),
            notes=data.get("notes", ""),
            sha256=data.get("sha256", ""),
            size_mb=size_mb,
            exe_name=exe_name,
            published_at=mtime,
        )

    def list_history(self) -> List[Dict]:
        """列出归档目录中的历史版本"""
        if not self.archive_dir.exists():
            return []
        result = []
        for f in sorted(self.archive_dir.glob("*.exe")):
            if f.is_file():
                ver = f.stem  # 文件名（无扩展名）即版本号
                size_mb = round(f.stat().st_size / 1024 / 1024, 2)
                mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime))
                result.append({
                    "version": ver,
                    "size_mb": size_mb,
                    "archived_at": mtime,
                    "filename": f.name,
                })
        # 按版本号倒序（新版本在上）
        result.sort(key=lambda x: _version_tuple(x["version"]), reverse=True)
        return result

    # ── 发布 ─────────────────────────────────────────────────

    def publish(
        self,
        exe_data: bytes,
        version: str,
        notes: str,
        download_url: str,
        exe_name: str = "",
        progress_cb=None,
    ) -> Tuple[bool, str, Optional[VersionInfo]]:
        """发布新版本

        Args:
            exe_data: exe 二进制内容
            version: 版本号（如 1.14.0）
            notes: 更新说明
            download_url: 下载地址（完整 URL）
            exe_name: 保存的文件名，为空则用 CURRENT_EXE_NAME
            progress_cb: 可选进度回调，参数为百分比 float

        Returns:
            (成功, 消息, 版本信息)
        """
        # 校验
        if not exe_data:
            return False, "exe 内容为空", None
        if not self.is_valid_exe(exe_data):
            return False, "文件不是有效的 exe（缺少 MZ 头）", None
        if not version or not _is_valid_version(version):
            return False, "版本号格式不正确（如 1.14.0）", None
        if not download_url:
            return False, "下载地址不能为空", None

        target_name = exe_name or self.CURRENT_EXE_NAME
        # 安全校验：文件名不能含路径分隔符
        if "/" in target_name or "\\" in target_name or ".." in target_name:
            return False, "文件名包含非法字符", None

        try:
            # 1. 旧版本归档
            current = self.get_current_version()
            cur_exe = self.current_exe_path()
            # 如果上一个发布用了不同文件名，也要找到并归档
            prev_name = current.exe_name if current and current.exe_name else self.CURRENT_EXE_NAME
            prev_exe = self.downloads_dir / prev_name
            if current and prev_exe.exists() and current.version:
                archive_path = self.archive_dir / f"{current.version}.exe"
                if archive_path.exists():
                    archive_path.unlink()
                shutil.move(str(prev_exe), str(archive_path))

            # 2. 写入新 exe
            new_exe = self.downloads_dir / target_name
            tmp_path = self.downloads_dir / f".{target_name}.tmp"
            with open(tmp_path, "wb") as f:
                f.write(exe_data)
            # 原子替换
            if new_exe.exists():
                new_exe.unlink()
            tmp_path.rename(new_exe)

            # 3. 计算 SHA-256
            sha = sha256_of_file(new_exe, progress_cb=progress_cb)

            # 4. 生成 version.json
            info = {
                "version": version,
                "url": download_url,
                "notes": notes,
                "sha256": sha,
                "exe_name": target_name,
            }
            self.version_json_path().write_text(
                json.dumps(info, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            vi = VersionInfo(
                version=version,
                url=download_url,
                notes=notes,
                sha256=sha,
                size_mb=round(new_exe.stat().st_size / 1024 / 1024, 2),
                exe_name=target_name,
                published_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return True, f"版本 {version} 发布成功", vi
        except Exception as e:
            return False, f"发布失败: {e}", None

    # ── 回滚 ─────────────────────────────────────────────────

    def rollback(self, version: str, download_url: str = "", exe_name: str = "") -> Tuple[bool, str]:
        """回滚到指定历史版本

        将当前 exe 归档（用当前版本号），然后把 archive/<version>.exe 恢复为当前版本，
        重算 SHA-256 并重写 version.json。
        """
        archive_path = self.archive_dir / f"{version}.exe"
        if not archive_path.exists():
            return False, f"归档中找不到版本 {version}"

        try:
            current = self.get_current_version()
            cur_name = current.exe_name if current and current.exe_name else self.CURRENT_EXE_NAME
            cur_exe = self.downloads_dir / cur_name
            target_name = exe_name or cur_name or self.CURRENT_EXE_NAME

            # 当前 exe 先归档
            if current and cur_exe.exists() and current.version:
                cur_archive = self.archive_dir / f"{current.version}.exe"
                if not cur_archive.exists():
                    shutil.copy2(str(cur_exe), str(cur_archive))

            # 恢复归档版本
            new_exe = self.downloads_dir / target_name
            shutil.copy2(str(archive_path), str(new_exe))

            # 重算 SHA-256
            sha = sha256_of_file(new_exe)

            # 下载地址：如果传入就用，否则保留旧的
            url = download_url
            if not url and current:
                url = current.url

            info = {
                "version": version,
                "url": url,
                "notes": f"回滚到版本 {version}",
                "sha256": sha,
                "exe_name": target_name,
            }
            self.version_json_path().write_text(
                json.dumps(info, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True, f"已回滚到版本 {version}"
        except Exception as e:
            return False, f"回滚失败: {e}"

    # ── 删除历史版本 ─────────────────────────────────────────

    def delete_history(self, version: str) -> Tuple[bool, str]:
        archive_path = self.archive_dir / f"{version}.exe"
        if not archive_path.exists():
            return False, f"归档中找不到版本 {version}"
        try:
            archive_path.unlink()
            return True, f"已删除历史版本 {version}"
        except Exception as e:
            return False, f"删除失败: {e}"


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def sha256_of_file(path: Path, chunk_size: int = 1 << 20, progress_cb=None) -> str:
    """计算文件 SHA-256，可选进度回调"""
    total = path.stat().st_size
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress_cb and total:
                progress_cb(done * 100.0 / total)
    if progress_cb:
        progress_cb(100.0)
    return h.hexdigest()


def _is_valid_version(version: str) -> bool:
    """简单校验版本号格式：数字.数字.数字（支持两段或多段）"""
    parts = version.split(".")
    if len(parts) < 2:
        return False
    return all(p.isdigit() for p in parts)


def _version_tuple(version: str) -> tuple:
    """版本号转 tuple 用于排序"""
    try:
        return tuple(int(p) for p in version.split("."))
    except Exception:
        return (0,)


# ═══════════════════════════════════════════════════════════════
# 快速自检
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        dl = Path(td) / "downloads"
        rm = ReleaseManager(dl)

        # 构造一个假 exe（MZ 头 + 内容）
        fake_exe = b"MZ" + b"\x00" * 1024

        ok, msg, vi = rm.publish(fake_exe, "1.14.0", "首次发布", "http://10.1.10.172:8091/download/南网协议解析工具.exe")
        print(f"发布 1.14.0: {ok} {msg}")
        assert ok, msg

        cur = rm.get_current_version()
        print(f"当前版本: {cur.version} sha256={cur.sha256[:16]}...")

        # 发布第二个版本
        fake_exe2 = b"MZ" + b"\x01" * 2048
        ok, msg, vi = rm.publish(fake_exe2, "1.15.0", "第二个版本", "http://10.1.10.172:8091/download/南网协议解析工具.exe")
        print(f"发布 1.15.0: {ok} {msg}")
        assert ok, msg

        hist = rm.list_history()
        print(f"历史版本: {[h['version'] for h in hist]}")
        assert len(hist) == 1

        # 回滚
        ok, msg = rm.rollback("1.14.0", "http://10.1.10.172:8091/download/南网协议解析工具.exe")
        print(f"回滚 1.14.0: {ok} {msg}")
        assert ok, msg

        cur = rm.get_current_version()
        print(f"回滚后版本: {cur.version}")
        assert cur.version == "1.14.0"

        hist = rm.list_history()
        print(f"回滚后历史: {[h['version'] for h in hist]}")
        assert any(h["version"] == "1.15.0" for h in hist)  # 1.15.0 被归档

        # 密码
        cfg = AdminConfig(Path(td) / "admin_config.json")
        assert cfg.is_default_password
        assert cfg.verify_password("admin123")
        assert not cfg.verify_password("wrong")
        ok, msg = cfg.change_password("admin123", "newpass123")
        assert ok, msg
        assert cfg.verify_password("newpass123")
        assert not cfg.is_default_password
        print("密码测试: 通过")

        print("\n所有自检通过 ✓")
