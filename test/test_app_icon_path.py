# -*- coding: utf-8 -*-
"""app_icon.ico 定位回归测试（offscreen）

背景缺陷：窗口/托盘图标曾用 Path(__file__).parent 定位，frozen 单文件 exe 下
__file__ 指向 _MEIPASS 临时目录，而 spec datas 未打包 app_icon.ico → 图标静默缺失
（开发模式正常）。修复：_app_icon_path() = resource_path 优先 + exe 目录回退，
且 spec datas 补 ('app_icon.ico', '.')。

覆盖：
  1. 开发模式：定位到项目根 app_icon.ico 且文件存在；MainWindow 窗口图标非空
  2. 模拟 frozen 且 _MEIPASS 含 ico：定位到 _MEIPASS 副本
  3. 模拟 frozen 且 _MEIPASS 无 ico、exe 目录有 ico：回退 exe 目录
  4. spec datas 含 ('app_icon.ico', '.')（防止再次漏打包）
"""

import _path_setup  # noqa: E402

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


def main():
    import app_paths
    import main_gui

    project_root = Path(app_paths.__file__).resolve().parent

    # 1. 开发模式
    p = main_gui._app_icon_path()
    check("开发模式定位项目根 app_icon.ico", p == project_root / "app_icon.ico",
          f"got {p}")
    check("项目根 app_icon.ico 存在", p.exists())

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = main_gui.MainWindow()
    check("MainWindow 窗口图标非空", not win.windowIcon().isNull())

    # 2/3. 模拟 frozen
    orig = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None),
            sys.executable)
    try:
        with tempfile.TemporaryDirectory() as exe_s, \
                tempfile.TemporaryDirectory() as mei_s:
            exe_dir = Path(exe_s)
            meipass = Path(mei_s)
            fake_exe = exe_dir / "tool.exe"
            fake_exe.write_text("fake")

            # 2) _MEIPASS 含 ico
            shutil.copy2(project_root / "app_icon.ico", meipass / "app_icon.ico")
            sys.frozen = True
            sys.executable = str(fake_exe)
            sys._MEIPASS = str(meipass)
            check("frozen 优先 _MEIPASS 内置资源",
                  main_gui._app_icon_path() == meipass / "app_icon.ico",
                  f"got {main_gui._app_icon_path()}")

            # 3) _MEIPASS 无 ico → 回退 exe 目录
            (meipass / "app_icon.ico").unlink()
            shutil.copy2(project_root / "app_icon.ico", exe_dir / "app_icon.ico")
            check("frozen _MEIPASS 缺失时回退 exe 目录",
                  main_gui._app_icon_path() == exe_dir / "app_icon.ico",
                  f"got {main_gui._app_icon_path()}")
    finally:
        sys.frozen, sys._MEIPASS, sys.executable = orig[0], orig[1], orig[2]
        if orig[0] is None:
            del sys.frozen
        if orig[1] is None and hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS

    # 4. spec datas 防漏打包
    spec_text = (project_root / "南网协议解析工具.spec").read_text(encoding="utf-8")
    check("spec datas 含 app_icon.ico",
          "('app_icon.ico', '.')" in spec_text)

    print("=" * 50)
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项失败: {FAILURES}")
        raise SystemExit(1)
    print(f"[OK] 全部 {PASS} 项检查通过")


if __name__ == "__main__":
    main()
