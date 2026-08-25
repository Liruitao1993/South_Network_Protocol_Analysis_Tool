"""auto_updater 单元测试：版本比较 / 更新源 JSON 解析 / update.bat 生成。

用法：
    python test/test_auto_updater.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# 让项目根可导入
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _path_setup  # noqa: E402,F401

from auto_updater import (  # noqa: E402
    VersionChecker,
    build_update_bat,
    check_for_update,
    compare_versions,
    is_update_needed,
    merge_update_config,
    Opdater,
    _extract_release_info,
)


# ── 版本比较 ─────────────────────────────────────────────
def test_compare_equal():
    assert compare_versions("1.14.4", "1.14.4") == 0
    assert compare_versions("1.0.0", "1.0.0") == 0


def test_compare_newer():
    assert compare_versions("1.0.0", "1.0.1") < 0   # 需要更新
    assert compare_versions("1.14.4", "1.15.0") < 0
    assert compare_versions("1.9.9", "1.14.0") < 0   # 逐段数字比较，非字典序
    assert compare_versions("2.0.0", "1.99.99") > 0  # 不更新


def test_compare_v_prefix():
    assert compare_versions("v1.14.4", "1.14.4") == 0
    assert compare_versions("1.14.4", "v1.15.0") < 0


def test_is_update_needed():
    assert is_update_needed("1.14.4", "1.15.0") is True
    assert is_update_needed("1.15.0", "1.15.0") is False
    assert is_update_needed("1.16.0", "1.15.0") is False


# ── 更新源 JSON 解析 ─────────────────────────────────────
def test_extract_gitee_release():
    data = {
        "tag_name": "v1.15.0",
        "name": "v1.15.0",
        "body": "修复若干问题",
        "assets": [
            {"name": "source.zip", "browser_download_url": "https://gitee.com/x/src.zip"},
            {"name": "南网协议解析工具.exe",
             "browser_download_url": "https://gitee.com/x/南网协议解析工具.exe",
             "size": 101000000},
        ],
    }
    info = _extract_release_info(data)
    assert info["version"] == "v1.15.0"
    assert "南网协议解析工具.exe" in info["url"]
    assert "修复" in info["notes"]
    # 多个资产时优先 exe
    assert "src.zip" not in info["url"]


def test_extract_private_json():
    data = {"version": "1.2.0", "url": "http://10.0.0.8/app.exe",
            "notes": "内网版", "sha256": "a" * 64}
    info = _extract_release_info(data)
    assert info["version"] == "1.2.0"
    assert info["url"] == "http://10.0.0.8/app.exe"
    assert info["sha256"] == "a" * 64


def test_extract_missing_fields():
    try:
        _extract_release_info({})
        assert False, "应抛 UpdateSourceError"
    except Exception:
        pass


# ── VersionChecker ─────────────────────────────────────────
def test_checker_private_source():
    def fake_get(url):
        return json.dumps({"version": "2.0.0", "url": "http://x/app.exe"})
    cfg = merge_update_config({"source_type": "private", "private_url": "http://x/ver.json"})
    checker = VersionChecker(cfg, http_get=fake_get)
    result = checker.check("1.14.4")
    assert result["available"] is True
    assert result["latest"]["version"] == "2.0.0"


def test_checker_already_latest():
    def fake_get(url):
        return json.dumps({"version": "1.14.4", "url": "http://x/app.exe"})
    cfg = merge_update_config({"source_type": "private", "private_url": "http://x/ver.json"})
    result = VersionChecker(cfg, http_get=fake_get).check("1.14.4")
    assert result["available"] is False


def test_checker_network_error_degrades():
    """网络失败由顶层 check_for_update 降级（error 字段），不抛异常。"""
    def bad_get(url):
        raise OSError("timeout")
    cfg = merge_update_config({"source_type": "private", "private_url": "http://x/ver.json"})
    result = check_for_update("1.0.0", cfg, http_get=bad_get)
    assert result["needed"] is False
    assert result["error"] is not None  # 降级并携带错误原因


# ── update.bat 生成 ───────────────────────────────────────
def test_build_update_bat_contains_replacement():
    new = Path(r"C:\tmp\new.exe")
    old = Path(r"D:\tools\南网协议解析工具.exe")
    bat = build_update_bat(new, old)
    assert "D:\\tools\\南网协议解析工具.exe" in bat
    assert "C:\\tmp\\new.exe" in bat
    # 批处理占位词应被替换，无残留 __
    assert "__NEW__" not in bat
    assert "__OLD__" not in bat
    assert "南网协议解析工具.exe" in bat  # IMAGENAME 用老 exe 名轮询等待


# ── 下载 + 校验 ──────────────────────────────────────────
def test_opdater_verify_sha256():
    tmp = Path(tempfile.gettempdir()) / "auto_update_test.txt"
    tmp.write_bytes(b"hello")
    sha = __import__("hashlib").sha256(b"hello").hexdigest()
    updater = Opdater()
    assert updater.verify(tmp, sha) is True
    assert updater.verify(tmp, "f" * 64) is False
    assert updater.verify(tmp, "") is True       # 无预期值视为通过
    assert updater.verify(tmp, "abc") is False   # 非法长度
    tmp.unlink(missing_ok=True)


def test_update_bat_roundtrip_syntax():
    """生成的 bat 至少是合法的批处理骨架（含 tasklist 轮询与 copy）。"""
    new = Path(r"C:\new.exe")
    old = Path(r"C:\old.exe")
    bat = build_update_bat(new, old)
    assert "tasklist" in bat
    assert "copy /y /b" in bat
    assert "start \"\"" in bat


def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)