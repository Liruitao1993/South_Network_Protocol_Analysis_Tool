"""TCP 监控「记录位置」回归测试（现场诉求：记录下来的 CSV 找不到、也不知道去哪找）。

覆盖：
  [1] 纯函数 default_record_dir / resolve_record_dir（默认目录、用户配置优先、空白回落）
  [2] 纯函数 load_record_config（缺失/损坏/非对象一律回落空配置；容 BOM；合法可读）
  [3] 纯函数 save_record_config（原子写往返、自动建目录、失败返回 False 不抛）
  [4] 纯函数 open_in_file_manager（Windows 定位文件 / 回落打开目录 / Linux xdg-open）
  [5] GUI 工具栏接线：打开位置 / 记录目录（菜单 3 项）/ 状态栏
  [6] 选择记录目录 → 落盘 + tooltip 刷新；取消选择不变
  [7] 恢复默认目录 → 配置键删除 + 回落默认
  [8] 重启持久化：新 widget 读到用户设置的目录
  [9] 开始记录 → 文件落在配置目录；状态栏文件名 + tooltip 完整路径
  [10] 打开位置 → 定位当前记录文件；目录缺失自动创建；异常不崩（只提示）
  [11] 保存失败 → 提示且目录仍生效（不静默）
  [12] 回归：QFileDialog 已导入（「加载记录」按钮原先必然 NameError）
  [13] 静态守卫：记录路径必须经 record_dir()，不得裸调 app_data_dir()

运行: python test/test_tcp_monitor_record_dir.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re  # noqa: E402
import sys  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# 控制台为 GBK 时，收尾行的 “✓” 会让整轮测试在最后一行抛 UnicodeEncodeError；
# 只放宽 errors（不动 encoding）——标准路径（PYTHONIOENCODING=utf-8）行为不变。
try:
    sys.stdout.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import app_paths  # noqa: E402

# 沙箱：数据目录 + 配置文件目录都指向临时目录（**必须在 import 被测模块前**安装，
# 且必须同时 patch `data_path` 与 `app_data_dir` —— 后者决定默认记录目录，
# 漏 patch 会让测试往开发机真实项目根拉一个 Output/ 目录）。
_SANDBOX = Path(tempfile.mkdtemp(prefix="nw_tcpmon_"))
patch.object(app_paths, "data_path", lambda name: _SANDBOX / str(name)).start()
patch.object(app_paths, "app_data_dir", lambda: _SANDBOX).start()

from monitor import tcp_monitor as tm  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n{title}")


def sandbox_dir(name):
    """沙箱下的一个子目录路径（不创建）。"""
    return str(_SANDBOX / name)


# ── [1] 纯函数：默认目录与解析 ────────────────────────────────────────
def test_default_and_resolve():
    section("[1] default_record_dir / resolve_record_dir")
    d = tm.default_record_dir()
    check("默认目录 = <数据目录>/Output",
          Path(d) == _SANDBOX / "Output", d)
    check("显式注入 data_dir 生效",
          tm.default_record_dir("/tmp/x") == str(Path("/tmp/x") / "Output"),
          tm.default_record_dir("/tmp/x"))
    check("配置优先于默认",
          tm.resolve_record_dir("D:/rec", d) == "D:/rec")
    check("配置为空 → 回落默认", tm.resolve_record_dir("", d) == d)
    check("配置为纯空白 → 回落默认", tm.resolve_record_dir("   ", d) == d)
    check("配置为 None → 回落默认", tm.resolve_record_dir(None, d) == d)


# ── [2] 纯函数：读配置 ───────────────────────────────────────────────
def test_load_config():
    section("[2] load_record_config：缺失/损坏/非对象/BOM")
    check("文件不存在 → 空配置", tm.load_record_config() == {})

    p = _SANDBOX / "broken.json"
    p.write_text("{ 不是合法 json", encoding="utf-8")
    check("损坏 JSON → 空配置（不抛）", tm.load_record_config(p) == {})

    p.write_text('["数组不是对象"]', encoding="utf-8")
    check("非对象（数组）→ 空配置", tm.load_record_config(p) == {})

    p.write_text('"字符串"', encoding="utf-8")
    check("非对象（字符串）→ 空配置", tm.load_record_config(p) == {})

    p.write_text('\ufeff{"record_dir": "E:/带BOM"}', encoding="utf-8")
    check("带 BOM 的 UTF-8 可读（编辑器另存常见）",
          tm.load_record_config(p) == {"record_dir": "E:/带BOM"},
          str(tm.load_record_config(p)))

    p.write_text(json.dumps({"record_dir": "E:/中文目录"}, ensure_ascii=False),
                 encoding="utf-8")
    check("合法配置可读且中文不乱码",
          tm.load_record_config(p)["record_dir"] == "E:/中文目录")


# ── [3] 纯函数：写配置 ───────────────────────────────────────────────
def test_save_config():
    section("[3] save_record_config：原子写 / 自动建目录 / 失败不抛")
    deep = _SANDBOX / "a" / "b" / "cfg.json"
    ok = tm.save_record_config({"record_dir": "E:/deep"}, deep)
    check("目录不存在时自动创建并写入", ok and deep.exists(), f"ok={ok}")
    check("往返一致", tm.load_record_config(deep) == {"record_dir": "E:/deep"})
    check("无 .tmp 残留", not deep.with_name(deep.name + ".tmp").exists())

    # 失败路径：目标路径是个目录 → open() 抛 IsADirectoryError（OSError 子类）
    d = _SANDBOX / "as_dir"
    d.mkdir(exist_ok=True)
    check("写入失败返回 False 且不抛", tm.save_record_config({"x": 1}, d) is False)


# ── [4] 纯函数：打开位置 ─────────────────────────────────────────────
def test_open_in_file_manager():
    section("[4] open_in_file_manager：定位文件 / 打开目录 / Linux 回落")
    d = sandbox_dir("out4")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "tcp_monitor_20260924_120000.csv")
    with open(f, "w", encoding="utf-8") as fp:
        fp.write("时间,方向\n")

    with patch("subprocess.Popen") as popen:
        target = tm.open_in_file_manager(f, d)
    check("有记录文件 → 返回文件路径", target == f, target)
    args = popen.call_args[0][0]
    check("Windows 用 explorer /select 定位并选中文件",
          isinstance(args, str) and args.startswith("explorer /select,")
          and os.path.basename(f) in args, str(args))

    with patch("subprocess.Popen"), patch.object(os, "startfile") as startfile:
        target = tm.open_in_file_manager("", d)
    check("无记录文件 → 打开目录（返回目录）",
          target == d and startfile.called, f"{target} called={startfile.called}")

    with patch("subprocess.Popen"), patch.object(os, "startfile") as startfile:
        target = tm.open_in_file_manager(os.path.join(d, "已删除.csv"), d)
    check("记录文件已不存在 → 回落打开目录",
          target == d and startfile.called, target)

    # 模拟非 Windows（os 上无 startfile 属性）→ 回落 xdg-open
    stub_os = SimpleNamespace(path=os.path)          # 刻意不提供 startfile
    with patch.object(tm, "os", stub_os), patch("subprocess.Popen") as popen:
        target = tm.open_in_file_manager(f, d)
    check("Linux 分支回落 xdg-open 打开目录",
          target == d and popen.call_args[0][0] == ["xdg-open", d],
          str(popen.call_args))


# ── [5] GUI：工具栏接线 ─────────────────────────────────────────────
def test_toolbar_wiring(app):
    section("[5] 工具栏接线：打开位置 / 记录目录（菜单 3 项）")
    w = tm.TCPMonitorWidget()
    check("「打开位置」按钮存在", hasattr(w, "open_record_btn"))
    check("「记录目录」按钮存在", hasattr(w, "record_dir_btn"))
    acts = [a.text() for a in w.record_dir_btn.menu().actions()] if w.record_dir_btn.menu() else []
    check("记录目录菜单 3 项",
          acts == ["选择记录目录…", "打开记录目录", "恢复默认目录"], str(acts))
    check("tooltip 显示当前目录（默认来源）",
          tm.default_record_dir() in w.record_dir_btn.toolTip()
          and "默认" in w.record_dir_btn.toolTip(), w.record_dir_btn.toolTip())
    check("打开位置 tooltip 含当前目录",
          tm.default_record_dir() in w.open_record_btn.toolTip())
    check("状态栏初始「未记录」", w.csv_status_label.text() == "未记录",
          w.csv_status_label.text())
    # 图标键必须是 gui_utils._STANDARD_ICON_MAP 的合法键：写错会被静默跳过
    # （同 test_button_icons.py 记录的「分享此帧无图标」同类缺陷），故断言非空。
    check("「打开位置」图标非空（图标键合法）", not w.open_record_btn.icon().isNull())
    check("「记录目录」图标非空（图标键合法）", not w.record_dir_btn.icon().isNull())
    return w


# ── [6][7][8] GUI：目录可配 + 持久化 ─────────────────────────────────
def test_choose_and_persist(app, w):
    section("[6] 选择记录目录 → 落盘 + tooltip 刷新；取消不变")
    chosen = sandbox_dir("用户选的目录")
    with patch.object(tm.QFileDialog, "getExistingDirectory", lambda *a, **k: chosen):
        w._choose_record_dir()
    check("record_dir() 生效为用户目录", w.record_dir() == chosen, w.record_dir())
    check("落盘到 tcp_monitor_config.json",
          tm.load_record_config() == {"record_dir": chosen},
          str(tm.load_record_config()))
    check("tooltip 标注「用户设置」并含新目录",
          "用户设置" in w.record_dir_btn.toolTip()
          and chosen in w.record_dir_btn.toolTip(), w.record_dir_btn.toolTip())
    check("打开位置 tooltip 同步刷新", chosen in w.open_record_btn.toolTip())

    # 取消选择（返回空串）→ 配置不变
    with patch.object(tm.QFileDialog, "getExistingDirectory", lambda *a, **k: ""):
        w._choose_record_dir()
    check("取消选择不改配置", w.record_dir() == chosen, w.record_dir())

    section("[8] 重启持久化：新 widget 读到用户设置的目录")
    w2 = tm.TCPMonitorWidget()
    check("新 widget 直接读到用户目录", w2.record_dir() == chosen, w2.record_dir())

    section("[7] 恢复默认目录")
    w._reset_record_dir()
    check("回落默认目录", w.record_dir() == tm.default_record_dir(), w.record_dir())
    check("配置文件里的键已删除", "record_dir" not in tm.load_record_config(),
          str(tm.load_record_config()))
    check("tooltip 回到「默认」",
          "默认" in w.record_dir_btn.toolTip()
          and "用户设置" not in w.record_dir_btn.toolTip())


# ── [9] GUI：记录落在配置目录 ────────────────────────────────────────
def test_record_to_configured_dir(app, w):
    section("[9] 开始记录 → 文件落在配置目录；状态栏/tooltip 可定位")
    chosen = sandbox_dir("记录目录9")
    with patch.object(tm.QFileDialog, "getExistingDirectory", lambda *a, **k: chosen):
        w._choose_record_dir()

    w.csv_record_btn.setChecked(True)          # 触发 _on_csv_record_toggled → _start_csv_recording
    try:
        check("记录已开始（文件对象存在）", w._csv_file is not None)
        check("文件落在配置目录",
              os.path.dirname(w._csv_path) == chosen, w._csv_path)
        check("文件名带 tcp_monitor_ 前缀与 .csv",
              os.path.basename(w._csv_path).startswith("tcp_monitor_")
              and w._csv_path.endswith(".csv"), os.path.basename(w._csv_path))
        check("文件真实存在", os.path.exists(w._csv_path))
        check("状态栏显示文件名",
              os.path.basename(w._csv_path) in w.csv_status_label.text(),
              w.csv_status_label.text())
        check("状态栏 tooltip 给完整路径",
              w._csv_path in w.csv_status_label.toolTip(),
              w.csv_status_label.toolTip())
    finally:
        w.csv_record_btn.setChecked(False)     # → _stop_csv_recording
    check("停止后 tooltip 仍指向该记录文件（可继续定位）",
          w._csv_path in w.csv_status_label.toolTip())
    check("停止后状态栏含帧数", "帧" in w.csv_status_label.text(),
          w.csv_status_label.text())


# ── [10] GUI：打开位置 ──────────────────────────────────────────────
def test_open_location(app, w):
    section("[10] 打开位置：定位当前记录文件 / 目录自动创建 / 异常不崩")
    with patch.object(tm, "open_in_file_manager") as oifm:
        oifm.return_value = w._csv_path
        w._open_record_location()
    check("有记录文件时传入该文件（定位选中）",
          oifm.call_args[0][0] == w._csv_path, str(oifm.call_args))
    check("同时传入当前记录目录",
          oifm.call_args[0][1] == w.record_dir(), str(oifm.call_args))

    # 目录不存在 → 自动创建（否则资源管理器打不开）
    ghost = sandbox_dir("不存在的目录10")
    with patch.object(tm.QFileDialog, "getExistingDirectory", lambda *a, **k: ghost):
        w._choose_record_dir()
    with patch.object(tm, "open_in_file_manager"):
        w._open_record_location()
    check("记录目录不存在时自动创建", os.path.isdir(ghost), ghost)

    # 打开失败 → 只提示，不崩
    with patch.object(tm, "open_in_file_manager", side_effect=OSError("boom")):
        try:
            w._open_record_location()
            ok = True
        except Exception as exc:                      # noqa: BLE001
            ok, _ = False, exc
    check("打开失败只提示不抛异常", ok)

    # 无记录文件时（清空 _csv_path）→ 仍能打开目录
    w._csv_path = ""
    with patch.object(tm, "open_in_file_manager") as oifm:
        w._open_record_location()
    check("无记录文件时传入空路径（由 helper 打开目录）",
          oifm.call_args[0][0] == "", str(oifm.call_args))
    w._reset_record_dir()


# ── [11] GUI：保存失败不静默 ────────────────────────────────────────
def test_save_failure(app, w):
    section("[11] 保存失败 → 提示且目录仍生效")
    target = sandbox_dir("保存失败也生效")
    warned = []
    with patch.object(tm, "save_record_config", lambda *a, **k: False), \
            patch.object(QMessageBox, "warning",
                         lambda *a, **k: warned.append(a[1:]) or 0), \
            patch.object(tm.QFileDialog, "getExistingDirectory", lambda *a, **k: target):
        w._choose_record_dir()
    check("保存失败时弹出提示", bool(warned), str(warned))
    check("目录仍立即生效（不因保存失败而不生效）",
          w.record_dir() == target, w.record_dir())
    w._reset_record_dir()


# ── [12] 回归：QFileDialog 导入 ─────────────────────────────────────
def test_qfiledialog_import(app, w):
    section("[12] 回归：QFileDialog 已导入（「加载记录」原先必然 NameError）")
    check("模块命名空间有 QFileDialog", hasattr(tm, "QFileDialog"))
    try:
        with patch.object(tm.QFileDialog, "getOpenFileName", lambda *a, **k: ("", "")):
            w._load_csv_recording()
        ok, detail = True, ""
    except Exception as exc:                          # noqa: BLE001
        ok, detail = False, repr(exc)
    check("_load_csv_recording 不再抛 NameError", ok, detail)

    # 默认起始目录 = 当前记录目录（不是空串）
    seen = {}
    with patch.object(tm.QFileDialog, "getOpenFileName",
                      lambda *a, **k: (seen.update(start=a[2]), ("", ""))[1]):
        w._load_csv_recording()
    check("文件对话框起始目录 = 当前记录目录",
          seen.get("start") == w.record_dir(), str(seen))


# ── [13] 静态守卫 ───────────────────────────────────────────────────
def test_static_guards():
    section("[13] 静态守卫：路径单一来源")
    src = Path("monitor/tcp_monitor.py").read_text(encoding="utf-8")
    check("记录路径统一经 record_dir()", "output_dir = self.record_dir()" in src)
    check("配置路径经 app_paths.data_path（非 from-import）",
          "app_paths.data_path(TCP_MONITOR_CONFIG_NAME)" in src)
    check("无裸 app_data_dir() 调用（负向断言，避免绕过沙箱）",
          re.search(r"(?<![\w.])app_data_dir\(\)", src) is None,
          str(re.search(r"(?<![\w.])app_data_dir\(\)", src)))
    check("记录目录名常量单一来源", src.count('"Output"') == 1
          or "DEFAULT_RECORD_DIR_NAME" in src)

    # 图标键合法性：全仓 set_btn_icon 调用不得使用未知键（gui_utils 会静默跳过）
    import gui_utils
    used = set(re.findall(r'set_btn_icon\([^,]+,\s*"([^"]+)"', src))
    bad = sorted(k for k in used if k not in gui_utils._STANDARD_ICON_MAP)
    check("tcp_monitor 内 set_btn_icon 键全部合法", not bad, str(bad))


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    test_default_and_resolve()
    test_load_config()
    test_save_config()
    test_open_in_file_manager()
    w = test_toolbar_wiring(app)

    # QFileDialog 是「加载记录」与「选择记录目录」的共同依赖：缺失时后续用例会因
    # patch 目标不存在而抛未捕获异常 → 进程可能以 0xC0000409 崩溃且 stdout 全空
    # （极难诊断，同 AGENTS §8 陷阱 62 的信号）。故此处显式判一次并跳过，让失败干净可见。
    if hasattr(tm, "QFileDialog"):
        test_choose_and_persist(app, w)
        test_record_to_configured_dir(app, w)
        test_open_location(app, w)
        test_save_failure(app, w)
        test_qfiledialog_import(app, w)
    else:
        check("[阻断] QFileDialog 未导入（「加载记录」必然 NameError）", False)
        print("  （跳过依赖 QFileDialog 的 GUI 用例 —— 上一条已判定失败）")

    test_static_guards()
    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）✓")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
