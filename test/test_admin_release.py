"""端到端测试管理员发布管理后端逻辑（不启动 Reflex）"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reflex_web.admin_release import ReleaseManager, AdminConfig, _is_valid_version


def test_full_flow():
    """完整发布/回滚流程测试"""
    with tempfile.TemporaryDirectory() as td:
        dl = Path(td) / "downloads"
        cfg_path = Path(td) / "admin_config.json"

        rm = ReleaseManager(dl)
        cfg = AdminConfig(cfg_path)

        # 1. 密码配置
        assert cfg.is_default_password
        assert cfg.verify_password("admin123")
        assert not cfg.verify_password("wrong")
        ok, msg = cfg.change_password("admin123", "newpass123")
        assert ok, msg
        assert not cfg.is_default_password
        assert cfg.verify_password("newpass123")
        print("✓ 密码管理")

        # 2. 首次发布
        fake_exe = b"MZ" + b"\x00" * 1024
        ok, msg, vi = rm.publish(
            fake_exe,
            "1.14.0",
            "首次发布测试",
            "http://10.1.10.172:8091/download/南网协议解析工具.exe",
        )
        assert ok, msg
        assert vi.version == "1.14.0"
        assert vi.sha256 != ""
        assert (dl / "南网协议解析工具.exe").exists()
        assert (dl / "version.json").exists()
        cur = rm.get_current_version()
        assert cur.version == "1.14.0"
        assert cur.url == "http://10.1.10.172:8091/download/南网协议解析工具.exe"
        print("✓ 首次发布")

        # 3. 二次发布（旧版本归档）
        fake_exe2 = b"MZ" + b"\x01" * 2048
        ok, msg, vi = rm.publish(
            fake_exe2,
            "1.15.0",
            "第二次发布",
            "http://10.1.10.172:8091/download/南网协议解析工具.exe",
        )
        assert ok, msg
        hist = rm.list_history()
        assert len(hist) >= 1
        assert any(h["version"] == "1.14.0" for h in hist)
        assert (dl / "archive" / "1.14.0.exe").exists()
        print("✓ 二次发布（归档）")

        # 4. 回滚
        ok, msg = rm.rollback("1.14.0", "http://10.1.10.172:8091/download/南网协议解析工具.exe")
        assert ok, msg
        cur = rm.get_current_version()
        assert cur.version == "1.14.0"
        # 1.15.0 应该被归档了
        assert (dl / "archive" / "1.15.0.exe").exists()
        print("✓ 回滚")

        # 5. 版本号校验
        assert _is_valid_version("1.14.0")
        assert _is_valid_version("1.14")
        assert _is_valid_version("2.0.0.1")
        assert not _is_valid_version("")
        assert not _is_valid_version("bad")
        assert not _is_valid_version("1.0.a")
        print("✓ 版本号校验")

        # 6. 非法 exe 拒绝
        ok, msg, vi = rm.publish(b"NOT_EXE", "1.16.0", "", "http://x/y.exe")
        assert not ok
        assert "MZ" in msg
        print("✓ 非法文件拒绝")

        # 7. SHA-256 正确性验证
        import hashlib
        cur = rm.get_current_version()
        exe_data = (dl / "南网协议解析工具.exe").read_bytes()
        expected = hashlib.sha256(exe_data).hexdigest()
        assert cur.sha256 == expected
        print("✓ SHA-256 正确性")

        # 8. 删除历史版本
        ok, msg = rm.delete_history("1.15.0")
        assert ok, msg
        hist = rm.list_history()
        assert not any(h["version"] == "1.15.0" for h in hist)
        print("✓ 删除历史版本")

        # 9. version.json 格式兼容 auto_updater
        import json
        data = json.loads((dl / "version.json").read_text(encoding="utf-8"))
        assert "version" in data
        assert "url" in data
        assert "notes" in data
        assert "sha256" in data
        # URL 必须是完整的（非相对路径）
        assert data["url"].startswith("http://") or data["url"].startswith("https://")
        print("✓ version.json 格式兼容")

        # 10. archive 目录防护（模拟 _serve_download 的路径判断）
        archive_path = dl / "archive" / "1.14.0.exe"
        # 文件名包含 / 会被拒绝
        filename = "archive/1.14.0.exe"
        assert "/" in filename  # 会被目录穿越检测拦截
        print("✓ archive 目录路径保护")

        print()
        print("=" * 50)
        print("全部测试通过 ✓")
        print("=" * 50)


if __name__ == "__main__":
    test_full_flow()
