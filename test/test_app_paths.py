# -*- coding: utf-8 -*-
"""
app_paths.py 数据文件定位测试（test_app_paths.py）

运行：python test/test_app_paths.py
覆盖：
- 开发模式：app_data_dir() 落项目根，data_path 指向项目根下文件
- 模拟 frozen（PyInstaller onefile）：monkeypatch sys.frozen / sys.executable /
  sys._MEIPASS 后，app_data_dir() 返回 exe 所在目录
- resource_path frozen 下指向 _MEIPASS 资源目录
- ensure_data_file：目标不存在时从 _MEIPASS 复制种子文件；目标已存在时不覆盖
- ensure_data_file：种子源不存在时静默返回目标路径（不抛异常）
"""

import _path_setup  # noqa: E402

import sys
import tempfile
from pathlib import Path

import app_paths  # noqa: E402
from app_paths import app_data_dir, data_path, resource_path, ensure_data_file  # noqa: E402

PROJECT_ROOT = Path(app_paths.__file__).resolve().parent

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


def section(title):
    print(f"\n== {title} ==")


# ---------------- 1. 开发模式 ----------------
section("开发模式路径定位")
check("app_data_dir = 项目根", app_data_dir() == PROJECT_ROOT,
      f"got {app_data_dir()}")
check("data_path 落项目根", data_path("config.json") == PROJECT_ROOT / "config.json",
      f"got {data_path('config.json')}")
check("resource_path 开发模式 = 数据目录", resource_path("config.json") == PROJECT_ROOT / "config.json")

# ---------------- 2. 模拟 frozen ----------------
section("frozen（PyInstaller）模拟")

_orig_frozen = getattr(sys, "frozen", None)
_orig_meipass = getattr(sys, "_MEIPASS", None)
_orig_executable = sys.executable

try:
    with tempfile.TemporaryDirectory() as exe_dir_s, tempfile.TemporaryDirectory() as meipass_s:
        exe_dir = Path(exe_dir_s)
        meipass = Path(meipass_s)
        fake_exe = exe_dir / "南网协议解析工具.exe"
        fake_exe.write_text("fake")

        # 种子资源放 _MEIPASS
        seed = meipass / "custom_di.json"
        seed.write_text('{"seed": true}', encoding="utf-8")

        sys.frozen = True
        sys.executable = str(fake_exe)
        sys._MEIPASS = str(meipass)

        check("frozen app_data_dir = exe 目录", app_data_dir() == exe_dir.resolve(),
              f"got {app_data_dir()}")
        check("frozen data_path 落 exe 目录", data_path("custom_di.json") == exe_dir.resolve() / "custom_di.json")
        check("frozen resource_path 指向 _MEIPASS", resource_path("custom_di.json") == meipass / "custom_di.json")

        # ensure_data_file：种子复制
        target = ensure_data_file("custom_di.json")
        check("ensure_data_file 返回 exe 目录路径", target == exe_dir.resolve() / "custom_di.json")
        check("种子已复制到 exe 目录", target.exists() and target.read_text(encoding="utf-8") == '{"seed": true}')

        # 二次调用不覆盖用户修改
        target.write_text('{"user": "modified"}', encoding="utf-8")
        ensure_data_file("custom_di.json")
        check("二次调用不覆盖已有文件", target.read_text(encoding="utf-8") == '{"user": "modified"}')

        # 种子源不存在：不抛异常，返回目标路径
        missing = ensure_data_file("no_such_seed.json")
        check("种子缺失不抛异常", missing == exe_dir.resolve() / "no_such_seed.json" and not missing.exists())
finally:
    if _orig_frozen is None:
        if hasattr(sys, "frozen"):
            del sys.frozen
    else:
        sys.frozen = _orig_frozen
    if _orig_meipass is None:
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
    else:
        sys._MEIPASS = _orig_meipass
    sys.executable = _orig_executable

check("恢复后 app_data_dir 回到项目根", app_data_dir() == PROJECT_ROOT)

# ---------------- 结果 ----------------
print(f"\n共 {passed + failed} 项: {passed} passed / {failed} failed")
if failed:
    sys.exit(1)
