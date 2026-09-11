"""核心测试一键跑（无 pytest 依赖）。

默认跑 release_check.CORE_TESTS 列表；`--with-gui` 追加 offscreen GUI。
与 `python release_check.py` 共用清单，避免两套列表漂移。
"""

import _path_setup  # noqa: E402

import sys
from pathlib import Path

# 从 release_check 导入清单（同目录）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_check import CORE_TESTS, GUI_TESTS, run_test_script  # noqa: E402


def main() -> int:
    with_gui = "--with-gui" in sys.argv
    tests = list(CORE_TESTS)
    if with_gui:
        tests.extend(GUI_TESTS)
    fails = []
    for rel in tests:
        ok, detail = run_test_script(rel, timeout=240)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {rel}" + ("" if ok else f" :: {detail}"))
        if not ok:
            fails.append(rel)
    print(f"\n共 {len(tests)} 项，失败 {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
