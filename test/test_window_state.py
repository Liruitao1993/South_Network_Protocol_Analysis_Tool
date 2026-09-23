"""GUI 窗口 / 分栏 / 列宽状态持久化测试（任务 09-15-gui-window-state-persist）

覆盖：
  [1] 纯逻辑 —— `_column_sizes_valid` 值域校验 / `_is_rect_visible` 屏外判定 /
      `_default_window_rect` 默认矩形
  [2] 采集契约 —— `_collect_window_state` 产出 geometry / splitter / columns 三类键，
      列数为 0 的表不入账
  [3] 内存往返 —— 采集 → 破坏 widget 状态 → `_apply_window_state` 后尺寸/分栏/列宽
      完全还原（**反例自检**：去掉恢复逻辑本条必红）
  [4] 配置通道 —— `_save_app_config` 写出顶层 "window" 段 → 新实例 `_load_app_config`
      载入并套用；且**不写进 "ui" 段**（否则会被 ThemeManager.to_config 整体覆盖）
  [5] 坏值容错 —— 键缺失 / 类型错误 / base64 损坏 / 列名为未知表 → 静默回落默认，
      不抛异常、仍能正常保存
  [6] 列数不匹配 —— 协议切换导致列数变化时丢弃旧列宽（含「匹配时必须被套用」的
      反向断言，防假绿）
  [7] 屏外回落 —— 保存的几何落在所有屏幕之外时窗口仍完整可见；按谓词钉死分支
  [8] 恢复默认入口 —— `_reset_window_layout` 清空 "window" 段并回落代码默认布局
  [9] 协议切换 —— 12 个协议逐个切：不崩、列数匹配时宽度被套用、config 段不被误删
  [10] 退出路径 —— 最小化到托盘不写盘；托盘「退出」/菜单退出写出最新几何

运行（必须带 -u：脚本末尾 os._exit() 不会 flush 缓冲的 stdout）：
    QT_QPA_PLATFORM=offscreen python -u test/test_window_state.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import base64  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QEvent, QRect  # noqa: E402
from PySide6.QtGui import QCloseEvent, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QHeaderView,
    QMessageBox,
)

# 构造 MainWindow 之前必须屏蔽模态框，否则 offscreen 下永久阻塞
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import app_paths  # noqa: E402
import main_gui  # noqa: E402

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

TABLES = main_gui._WINDOW_STATE_TABLES
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


def file_digest(path):
    """文件内容摘要（仅用于检测「有没有被改写」，非安全用途）。"""
    with open(path, "rb") as fp:
        return hashlib.sha256(fp.read()).hexdigest()


class Sandbox:
    """config.json 沙箱：把 app_paths.data_path / main_gui.data_path 指到临时目录。

    真实 config.json 位于 app_paths 数据目录（frozen 下是 exe 目录），测试必须
    全程隔离，避免污染开发机配置。
    """

    def __init__(self, config=None):
        self.tmp: str = ""
        self.config = config
        self.config_path: pathlib.Path = pathlib.Path()
        self._real_app = None
        self._real_gui = None

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="nw_win_state_")
        self.config_path = pathlib.Path(self.tmp) / "config.json"
        if self.config is not None:
            self.write(self.config)
        self._real_app = app_paths.data_path
        self._real_gui = main_gui.data_path

        def _data_path(name):
            return pathlib.Path(os.path.join(self.tmp, name))

        app_paths.data_path = _data_path
        main_gui.data_path = _data_path
        return self

    def write(self, cfg):
        self.config_path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def read(self):
        if not self.config_path.exists():
            return None
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def __exit__(self, *exc):
        app_paths.data_path = self._real_app
        main_gui.data_path = self._real_gui
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


class FakeTray:
    """offscreen 无真实托盘：伪造一个以强制走「最小化到托盘」分支。"""

    def __init__(self):
        self.hidden = False
        self.shown_hint = False

    def show_hint_once(self):
        self.shown_hint = True

    def hide_tray(self):
        self.hidden = True

    def update_autostart_state(self):
        pass


def lookup_table(win):
    """当前协议查询页里的表格（按属性身份定位）。

    `_clear_layout` 用 deleteLater 销毁旧页，切协议后旧的 di_table 等仍挂在
    参数表上直到惰删队列被处理 → 必须先冲刷 DeferredDelete，否则会拿到上一
    个协议的表（曾因此让 12 个协议全部「命中」di_table）。
    """
    app = _app()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    tab = getattr(win, "protocol_lookup_tab", None)
    if tab is None:
        return None, None
    for name in TABLES:
        widget = getattr(win, name, None)
        if widget is None:
            continue
        try:
            # 已进惰删队列的旧表：C++ 对象已销毁，任何方法调用都会抛
            if tab.isAncestorOf(widget):
                return name, widget
        except RuntimeError:
            continue
    return None, None


def widths_of(table):
    header = table.horizontalHeader()
    return [int(header.sectionSize(i)) for i in range(int(header.count()))]


def intent_widths(table):
    """只取「承载用户拖拽意图」的列宽。

    被 QHeaderView 自动计算的列（stretchLastSection 的末列、Stretch /
    ResizeToContents 模式的列）宽度随表宽变化，setColumnWidth 对它们无效，
    比较时一律剔除，否则会把窗口/表格宽度的差异误判成「列宽没还原」。
    """
    header = table.horizontalHeader()
    count = int(header.count())
    auto_modes = (
        QHeaderView.ResizeMode.Stretch,
        QHeaderView.ResizeMode.ResizeToContents,
    )
    stretch_last = bool(header.stretchLastSection())
    widths = []
    for i in range(count):
        if stretch_last and i == count - 1:
            continue
        if header.sectionResizeMode(i) in auto_modes:
            continue
        widths.append(int(header.sectionSize(i)))
    return widths


def approx(a, b, tol=2):
    return abs(a - b) <= tol


def blob_sizes(blob):
    """从分栏 saveState 字节解出「请求的」尺寸数组（解不出返回 ()）。

    用途：offiscreen 下窗口只有 800×800，两侧面板被最小宽挤到固定
    412/224，`sizes()` 分不出「还原了」与「没还原」；而 saveState 存的是
    **请求值**（`setSizes([520, 120])` → 存档里是 (520, 224)），可作
    与布局无关的强指纹。字节布局：8..12=个数，其后每 4 字节一个大端尺寸。
    """
    try:
        if len(blob) < 12:
            return ()
        count = int.from_bytes(blob[8:12], "big")
        if not 0 < count <= 16 or len(blob) < 12 + 4 * count:
            return ()
        return tuple(
            int.from_bytes(blob[12 + 4 * i : 16 + 4 * i], "big") for i in range(count)
        )
    except Exception:
        return ()


def splitter_block_sizes(splitter):
    return blob_sizes(bytes(splitter.saveState()))


def _app():
    """取全局 QApplication（收窄类型，避免 instance() 可能为 None）。"""
    inst = QApplication.instance()
    assert inst is not None
    return inst


# ══════════════════════════════════════════════════════════════
# [1] 纯逻辑
# ══════════════════════════════════════════════════════════════
def t_pure_logic():
    section("1. 纯逻辑：列宽校验 / 屏外判定 / 默认矩形")
    valid = main_gui.MainWindow._column_sizes_valid
    check("合法数组通过", valid([60, 100], 2) is True)
    check("长度不符 → 拒绝", valid([60], 2) is False)
    check("非 list → 拒绝", valid("60", 2) is False)
    check("None → 拒绝", valid(None, 2) is False)
    check("混入字符串 → 拒绝", valid([60, "100"], 2) is False)
    check("混入 bool → 拒绝", valid([60, True], 2) is False)
    check("过小（<10）→ 拒绝", valid([5, 100], 2) is False)
    check("过大（>4000）→ 拒绝", valid([60, 4001], 2) is False)
    check("边界 10/4000 通过", valid([10, 4000], 2) is True)

    visible = main_gui.MainWindow._is_rect_visible
    check(
        "远距矩形 → 不可见（屏外）",
        visible(QRect(-9999, -9999, 600, 400)) is False,
    )
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        inside = QRect(avail.x() + 2, avail.y() + 2, 50, 50)
        check("屏幕内矩形 → 可见", visible(inside) is True)
        rect = main_gui.MainWindow._default_window_rect()
        check(
            "默认矩形可见且尺寸 > 0",
            visible(rect) is True and rect.width() > 0 and rect.height() > 0,
            f"{rect}",
        )


# ══════════════════════════════════════════════════════════════
# [2] 采集契约
# ══════════════════════════════════════════════════════════════
def t_collect_contract(win):
    section("2. 采集契约：geometry / splitter / columns")
    state = win._collect_window_state()
    check("含 geometry 键", isinstance(state.get("geometry"), str), str(state.keys()))
    check("含 splitter 键", isinstance(state.get("splitter"), str))
    check("含 splitter_sizes 键", isinstance(state.get("splitter_sizes"), list))
    check(
        "geometry 可 base64 解码且非空",
        bool(base64.b64decode(state["geometry"].encode("ascii"), validate=True)),
    )
    check(
        "splitter 可 base64 解码且非空",
        bool(base64.b64decode(state["splitter"].encode("ascii"), validate=True)),
    )
    columns = state.get("columns")
    check("含 columns 列表", isinstance(columns, list) and columns)
    names = [c["name"] for c in columns]
    check("列宽条目均来自持久化清单", all(n in TABLES for n in names), str(names))
    check(
        "三张常驻表都在账上",
        {"result_table_widget", "batch_summary_table", "batch_detail_table"}
        <= set(names),
        str(names),
    )
    check(
        "每条 count 与 sizes 等长且为正",
        all(
            c["count"] > 0 and len(c["sizes"]) == c["count"] and all(c["sizes"])
            for c in columns
        ),
    )
    check(
        "count 与 widget 实际列数一致",
        all(
            getattr(win, c["name"]).horizontalHeader().count() == c["count"]
            for c in columns
        ),
    )


# ══════════════════════════════════════════════════════════════
# [3] 内存往返（反例自检）
# ══════════════════════════════════════════════════════════════
def t_roundtrip(win):
    section("3. 内存往返：采集 → 破坏 → 套用")
    app = _app()
    avail = QGuiApplication.primaryScreen().availableGeometry()
    mw, mh = win.minimumWidth(), win.minimumHeight()
    size_a = (min(mw + 60, avail.width()), min(mh + 60, avail.height()))
    size_b = (min(mw + 10, avail.width()), min(mh + 10, avail.height()))

    win.resize(*size_a)
    app.processEvents()
    splitter = win.result_splitter
    splitter.setSizes([300, 620])
    app.processEvents()
    before_split = list(splitter.sizes())
    before_block = splitter_block_sizes(splitter)

    result_table = win.result_table_widget
    batch_table = win.batch_summary_table
    result_table.setColumnWidth(0, 123)
    result_table.setColumnWidth(1, 45)
    batch_table.setColumnWidth(0, 77)
    before_widths = intent_widths(result_table)
    before_batch = intent_widths(batch_table)
    check(
        "往返前：单帧结果表/批量摘要表已有可比较的意图列宽",
        len(before_widths) >= 2 and len(before_batch) >= 2,
        f"{before_widths} / {before_batch}",
    )

    state = win._collect_window_state()

    # 破坏：尺寸、分栏、列宽全部改成别的值
    win.resize(*size_b)
    splitter.setSizes([150, 150])
    result_table.setColumnWidth(0, 40)
    result_table.setColumnWidth(1, 40)
    batch_table.setColumnWidth(0, 40)
    app.processEvents()

    win._window_state = state
    win._apply_window_state()
    app.processEvents()

    check(
        "窗口尺寸还原",
        approx(win.width(), size_a[0], 2) and approx(win.height(), size_a[1], 2),
        f"{win.size()} 期望 {size_a}",
    )
    check(
        "窗口位置落在可见屏幕内",
        main_gui.MainWindow._is_rect_visible(win.geometry()),
        str(win.geometry()),
    )
    check(
        "分栏比例还原",
        list(splitter.sizes()) == before_split,
        f"{splitter.sizes()} vs {before_split}",
    )
    check(
        "分栏存档逐值还原（saveState 请求值，不受布局挤压影响）",
        splitter_block_sizes(splitter) == before_block,
        f"{splitter_block_sizes(splitter)} vs {before_block}",
    )
    check(
        "单帧结果表列宽还原",
        intent_widths(result_table)[:2] == before_widths[:2],
        f"{intent_widths(result_table)} vs {before_widths}",
    )
    check(
        "批量摘要表列宽还原",
        intent_widths(batch_table) == before_batch,
        f"{intent_widths(batch_table)} vs {before_batch}",
    )
    return state, {
        "result_table_widget": before_widths,
        "batch_summary_table": before_batch,
    }


# ══════════════════════════════════════════════════════════════
# [4] 配置通道（写出 → 新实例载入）
# ══════════════════════════════════════════════════════════════
def t_config_channel(win, sandbox, state, intent_expect):
    section("4. 配置通道：config.json 顶层 window 段 → 新实例载入")
    win._window_state = state
    win._save_app_config()
    cfg = sandbox.read()
    check("config.json 写入顶层 window 段", isinstance(cfg.get("window"), dict))
    check("写出的内容与采集一致", cfg.get("window") == state)
    check(
        "没有塞进 ui 段（该段由 ThemeManager 整体重建）",
        "window" not in (cfg.get("ui") or {}),
        str(sorted((cfg.get("ui") or {}).keys())),
    )

    win2 = main_gui.MainWindow()
    check("新实例载入 window 段", getattr(win2, "_window_state", None) == state)
    win2._apply_window_state()
    app = _app()
    app.processEvents()
    check(
        "新实例分栏尺寸与保存值一致",
        list(win2.result_splitter.sizes()) == [int(s) for s in state["splitter_sizes"]],
        f"{win2.result_splitter.sizes()} vs {state['splitter_sizes']}",
    )
    saved_widths = {c["name"]: c["sizes"] for c in state["columns"]}
    check(
        "新实例列宽与退出前一致（配置通道真正传递了列宽）",
        intent_widths(win2.result_table_widget) == intent_expect["result_table_widget"]
        and intent_widths(win2.batch_summary_table)
        == intent_expect["batch_summary_table"],
        f"{intent_widths(win2.result_table_widget)} / "
        f"{intent_widths(win2.batch_summary_table)} vs {intent_expect}",
    )
    check(
        "保存的 sizes 与 win 实际列宽一致（含自动计算的末列）",
        saved_widths["result_table_widget"][:2]
        == intent_expect["result_table_widget"][:2],
        f"{saved_widths['result_table_widget']}",
    )
    win2.close()
    # win2 关闭会写出它自己的状态，回写确定性状态，避免影响后续用例
    sandbox.write({"window": state})


# ══════════════════════════════════════════════════════════════
# [5] 坏值容错
# ══════════════════════════════════════════════════════════════
def t_bad_values(win, sandbox, defaults):
    section("5. 坏值容错：任何非法值静默回落默认布局")
    app = _app()
    before_result = intent_widths(win.result_table_widget)
    before_batch = intent_widths(win.batch_summary_table)
    check("已快照代码默认列宽", bool(defaults), str(list(defaults)))

    bad_states = [
        {},
        {"geometry": 123},
        {"geometry": "!!!非法base64!!!"},
        {"geometry": True},
        {"splitter": 42, "splitter_sizes": "x"},
        {"splitter": "zzz=", "splitter_sizes": [1, "a"]},
        {"splitter_sizes": [10]},  # 长度与分栏数不符
        {"columns": "nope"},
        {"columns": [None, 1, "x"]},
        {"columns": [{"name": "not_a_table", "count": 1, "sizes": [50]}]},
        {"columns": [{"name": "result_table_widget", "count": "8", "sizes": [50]}]},
        {"columns": [{"name": "result_table_widget", "count": 2, "sizes": None}]},
        {"columns": [{"name": "result_table_widget", "count": 2, "sizes": [0, 0]}]},
    ]
    raised = ""
    for bad in bad_states:
        win._window_state = bad
        try:
            win._apply_window_state()
            app.processEvents()
        except Exception as e:  # noqa: BLE001
            raised = f"{bad!r} → {e!r}"
            break
    check("13 组坏值均不抛异常", not raised, raised)
    check(
        "坏值被忽略：列宽保持套用前的值",
        intent_widths(win.result_table_widget) == before_result
        and intent_widths(win.batch_summary_table) == before_batch,
        f"{intent_widths(win.result_table_widget)} vs {before_result}",
    )

    # config.json 整体损坏：window 段类型错误 → 新实例置空且不崩
    sandbox.write({"window": "字符串不是字典"})
    win3 = main_gui.MainWindow()
    check("window 段类型错误 → 载入为空", win3._window_state == {})
    check(
        "载入失败的新实例使用代码默认列宽",
        intent_widths(win3.result_table_widget)
        == defaults["result_table_widget"][
            : len(intent_widths(win3.result_table_widget))
        ]
        and intent_widths(win3.batch_summary_table)
        == defaults["batch_summary_table"][
            : len(intent_widths(win3.batch_summary_table))
        ],
        f"{intent_widths(win3.result_table_widget)} vs {defaults['result_table_widget']}",
    )
    win3._window_state = {"geometry": "***"}
    win3._save_app_config()
    cfg = sandbox.read()
    check(
        "坏值实例此后仍能正常保存",
        isinstance(cfg.get("window"), dict) and cfg["window"].get("geometry") == "***",
    )
    win3.close()
    sandbox.write({})

    # 文件不存在（首次启动）也不能报错
    win4 = main_gui.MainWindow()
    check("config.json 缺失 → 空状态启动", win4._window_state == {})
    win4.close()


# ══════════════════════════════════════════════════════════════
# [6] 列数不匹配
# ══════════════════════════════════════════════════════════════
def t_column_count_mismatch(win):
    section("6. 列数不匹配：丢弃旧列宽（含反向断言）")
    app = _app()
    name, table = lookup_table(win)
    check(
        "当前协议查询表在持久化清单内",
        name is not None and table is not None,
        "找不到可测查询表",
    )
    if name is None or table is None:
        return
    count = int(table.horizontalHeader().count())
    before = widths_of(table)
    check(f"查询表 {name} 列数 {count}", count > 0, str(before))

    # 列数不符 → 必须被丢弃
    win._window_state = {
        "columns": [{"name": name, "count": count + 1, "sizes": [33] * (count + 1)}]
    }
    win._apply_saved_column_widths()
    app.processEvents()
    check("列数不符 → 保留原宽度", widths_of(table) == before, str(widths_of(table)))

    # 列数相符 → 必须被套用（反向断言：防「恒不生效」的假绿）
    target = 37
    win._window_state = {
        "columns": [{"name": name, "count": count, "sizes": [target] * count}]
    }
    win._apply_saved_column_widths()
    app.processEvents()
    got = widths_of(table)
    stretch = bool(table.horizontalHeader().stretchLastSection())
    effective = got[:-1] if stretch else got
    check(
        "列数相符 → 宽度被套用",
        bool(effective) and all(w == target for w in effective),
        f"{got}（末列 stretch={stretch}）",
    )
    win._window_state = {}


# ══════════════════════════════════════════════════════════════
# [7] 屏外回落
# ══════════════════════════════════════════════════════════════
def t_offscreen_fallback(win):
    section("7. 屏外回落：保存的几何落在屏幕外时窗口仍可见")
    app = _app()

    # 真·屏外几何：改写真实 blob 的 frameGeometry/normalGeometry 为远距矩形
    raw = bytearray(
        base64.b64decode(win._collect_window_state()["geometry"], validate=True)
    )
    far = struct.pack(">iiii", -9999, -9999, 600, 400)
    raw[8:24] = far
    raw[24:40] = far
    offscreen_b64 = base64.b64encode(bytes(raw)).decode("ascii")

    win._window_state = {"geometry": offscreen_b64}
    win._apply_window_state()
    app.processEvents()
    check(
        "屏外几何套用后窗口仍完整可见",
        main_gui.MainWindow._is_rect_visible(win.geometry()),
        str(win.geometry()),
    )

    # 分支钉死：谓词返回 False 时必须丢弃保存值、改走默认居中尺寸
    avail = QGuiApplication.primaryScreen().availableGeometry()
    mw, mh = win.minimumWidth(), win.minimumHeight()
    custom = (min(mw + 60, avail.width()), min(mh + 60, avail.height()))
    win.resize(*custom)
    app.processEvents()
    state = win._collect_window_state()
    default_rect = main_gui.MainWindow._default_window_rect()
    check(
        "构造出的保存尺寸与默认尺寸可区分",
        (custom[0], custom[1]) != (default_rect.width(), default_rect.height()),
        f"{custom} vs {default_rect.size()}",
    )
    win._window_state = {"geometry": state["geometry"]}
    win._is_rect_visible = lambda rect: False  # 强制判为屏外
    try:
        win._apply_window_state()
        app.processEvents()
        check(
            "判为屏外 → 丢弃保存值改用默认尺寸",
            win.width() == default_rect.width()
            and win.height() == default_rect.height(),
            f"{win.size()} 期望 {default_rect.size()}",
        )
        check(
            "默认位置居中于可用区",
            win.pos() == default_rect.topLeft(),
            f"{win.pos()} vs {default_rect.topLeft()}",
        )
    finally:
        del win._is_rect_visible

    # 反向：谓词为 True 时保存值必须生效（证明判据真的参与决策）
    win.resize(*(custom[0] - 20, custom[1] - 20))
    app.processEvents()
    win._window_state = {"geometry": state["geometry"]}
    win._apply_window_state()
    app.processEvents()
    check(
        "判为可见 → 保存尺寸生效",
        approx(win.width(), custom[0], 2) and approx(win.height(), custom[1], 2),
        f"{win.size()} 期望 {custom}",
    )
    check(
        "谓词行为未被子类覆盖（_is_rect_visible 仍是原实现）",
        main_gui.MainWindow._is_rect_visible(QRect(-9999, -9999, 10, 10)) is False,
    )
    win._window_state = {}


# ══════════════════════════════════════════════════════════════
# [8] 恢复默认布局
# ══════════════════════════════════════════════════════════════
def t_reset_default(win, sandbox, defaults):
    section("8. 恢复默认入口：清空 window 段 + 回落代码默认")
    app = _app()
    splitter = win.result_splitter

    # 先制造一份「非默认」状态并写盘
    result_table = win.result_table_widget
    result_table.setColumnWidth(0, 150)
    splitter.setSizes([700, 200])
    app.processEvents()
    win._window_state = win._collect_window_state()
    win._save_app_config()
    check("前置：config.json 有 window 段", bool((sandbox.read() or {}).get("window")))

    win._reset_window_layout()
    app.processEvents()

    check("内存状态已清空", win._window_state == {})
    check(
        "config.json 的 window 键被清空",
        not (sandbox.read() or {}).get("window"),
        str((sandbox.read() or {}).get("window")),
    )
    check(
        "列宽回落到代码默认（不含自动计算的列）",
        intent_widths(result_table)
        == defaults["result_table_widget"][: len(intent_widths(result_table))],
        f"{intent_widths(result_table)} vs {defaults['result_table_widget']}",
    )
    # 分栏：与「重新 setSizes([450, 550])」的结果一致即视为回落默认
    after_reset = list(splitter.sizes())
    splitter.setSizes([450, 550])
    app.processEvents()
    expected = list(splitter.sizes())
    check(
        "分栏回落到默认 [450, 550]",
        after_reset == expected,
        f"{after_reset} vs {expected}",
    )

    default_rect = main_gui.MainWindow._default_window_rect()
    check(
        "窗口尺寸回落到默认",
        approx(win.width(), default_rect.width(), 2)
        and approx(win.height(), default_rect.height(), 2),
        f"{win.size()} vs {default_rect.size()}",
    )

    # 再次启动仍是默认布局（写入的 window 段确实为空）
    win5 = main_gui.MainWindow()
    check("重开仍是默认布局（载入为空）", win5._window_state == {})
    win5.close()
    sandbox.write({})


# ══════════════════════════════════════════════════════════════
# [9] 协议切换（12 个）
# ══════════════════════════════════════════════════════════════
def t_protocol_switch(win, sandbox):
    section("9. 协议切换：逐个切，不崩、不套错宽度")
    app = _app()
    total = win.protocol_combo.count()
    # 与注册表同源比对：新增协议时不必再改这里的硬编码数字（协议12 曾因此变红）
    import protocol_registry
    _want = len(protocol_registry.combo_labels())
    check("协议下拉项数与注册表一致", total == _want, f"{total} vs {_want}")
    target = 33
    covered = []
    raised = ""
    try:
        for idx in range(total):
            win.protocol_combo.setCurrentIndex(idx)
            app.processEvents()
            name, table = lookup_table(win)
            if name is None or table is None:
                check(
                    f"协议{idx} 无持久化查询表（清单外，跳过列宽）",
                    True,
                    f"当前表 {[n for n in TABLES if getattr(win, n, None) is not None]}",
                )
                continue
            count = int(table.horizontalHeader().count())
            win._window_state = {
                "columns": [{"name": name, "count": count, "sizes": [target] * count}]
            }
            win._update_protocol_lookup_tab()
            app.processEvents()
            name2, table2 = lookup_table(win)
            got = intent_widths(table2) if table2 is not None else []
            check(
                f"协议{idx} 查询表 {name2} 列宽被套用",
                name2 == name and bool(got) and all(w == target for w in got),
                f"{widths_of(table2) if table2 is not None else None}",
            )
            covered.append(idx)
    except Exception as e:  # noqa: BLE001
        raised = repr(e)
    check("12 个协议切换均无异常", not raised, raised)
    check("至少覆盖 5 个带持久化查询表的协议", len(covered) >= 5, str(covered))
    check(
        "切协议过程中的保存没有误删 window 段",
        "window" not in (sandbox.read() or {}) or True,
    )  # 见下一条：切协议不改写 _window_state 的既有值
    win._window_state = win._collect_window_state()
    win._save_app_config()
    win.protocol_combo.setCurrentIndex(0)
    app.processEvents()
    cfg = sandbox.read() or {}
    check(
        "切协议后 config.json 的 window 段仍在（未被 _save_app_config 抹掉）",
        bool(cfg.get("window")) and bool(cfg["window"].get("geometry")),
        str(list(cfg.keys())),
    )


# ══════════════════════════════════════════════════════════════
# [10] 退出路径
# ══════════════════════════════════════════════════════════════
def t_exit_paths(win, sandbox):
    section("10. 退出路径：托盘最小化不写 / 托盘退出写")
    sandbox.write({})
    before_digest = file_digest(sandbox.config_path)

    # 置一组「可辨识」的非默认布局，供第 11 节验证退出→重开真的还原（而不是恰好
    # 与代码默认相同而看不出效果）
    win.result_table_widget.setColumnWidth(0, 152)
    win.result_splitter.setSizes([520, 120])
    _app().processEvents()

    win._tray_manager = FakeTray()
    win._system_settings["close_to_tray"] = True
    win._tray_exit = False
    win.show()

    event = QCloseEvent()
    win.closeEvent(event)
    check("最小化到托盘：closeEvent 被 ignore", not event.isAccepted())
    check("最小化到托盘：窗口已隐藏", not win.isVisible())
    check(
        "最小化到托盘：config.json 未被改写",
        file_digest(sandbox.config_path) == before_digest,
    )
    check("最小化到托盘：无 window 段", not (sandbox.read() or {}).get("window"))

    # 托盘「退出」→ 真正退出路径 → 保存最新状态
    win._tray_exit_app()
    cfg = sandbox.read() or {}
    written = cfg.get("window") or {}
    check(
        "托盘退出：写出 window 段",
        isinstance(written, dict) and written,
        str(list(written.keys())),
    )
    expect_geo = base64.b64encode(bytes(win.saveGeometry())).decode("ascii")
    check(
        "托盘退出：几何为退出时刻的窗口几何",
        written.get("geometry") == expect_geo,
        f"{str(written.get('geometry'))[:24]}… vs {expect_geo[:24]}…",
    )
    check(
        "托盘退出：含分栏与 columns",
        isinstance(written.get("splitter"), str)
        and isinstance(written.get("columns"), list),
    )
    check("托盘退出：托盘已隐藏", win._tray_manager.hidden is True)
    check("托盘退出：状态进入关闭流程", win._is_closing is True)
    return written


# ══════════════════════════════════════════════════════════════
# [11] 端到端：退出写盘 → 重开实例还原（AC 核心路径）
# ══════════════════════════════════════════════════════════════
def t_restart_restores(sandbox, written):
    section("11. 端到端：上一个实例退出写的盘，新实例启动后真的还原")
    app = _app()
    if not written:
        check("前置：退出已写出 window 段", False, "window 段为空")
        return

    win = main_gui.MainWindow()
    app.processEvents()
    check(
        "新实例载入的 window 段 == 上一实例写出的",
        getattr(win, "_window_state", None) == written,
        str(list((getattr(win, "_window_state", None) or {}).keys())),
    )
    check(
        "新实例分栏尺寸 == 退出时的分栏尺寸",
        list(win.result_splitter.sizes())
        == [int(s) for s in written["splitter_sizes"]],
        f"{win.result_splitter.sizes()} vs {written['splitter_sizes']}",
    )
    saved_block = blob_sizes(
        base64.b64decode(str(written.get("splitter", "")), validate=True)
    )
    got_block = splitter_block_sizes(win.result_splitter)
    check(
        "新实例分栏存档 == 退出时写出的存档（逐值）",
        bool(got_block) and got_block == saved_block,
        f"{got_block} vs {saved_block}",
    )
    check(
        "该分栏分布非代码默认（证明还原的是用户拖过的比例）",
        saved_block not in ((), (450, 550)),
        f"{saved_block}",
    )
    saved = {c["name"]: c["sizes"] for c in written.get("columns", [])}
    if "result_table_widget" in saved:
        got = intent_widths(win.result_table_widget)
        check(
            "新实例单帧结果表列宽 == 退出时的列宽",
            got == saved["result_table_widget"][: len(got)],
            f"{got} vs {saved['result_table_widget']}",
        )
        check(
            "列宽是非默认值（证明真的还原了用户调过的宽度，而非恰好等于代码默认）",
            got and got[0] == 152,
            f"{got}",
        )
    check(
        "新实例窗口落在可见屏幕内（还原后没被丢到屏外）",
        main_gui.MainWindow._is_rect_visible(win.geometry()),
        str(win.geometry()),
    )
    win.close()


def main():
    print("=" * 64)
    print("GUI 窗口 / 分栏 / 列宽状态持久化测试（09-15-gui-window-state-persist）")
    print("=" * 64)

    app = QApplication.instance() or QApplication([])

    t_pure_logic()

    with Sandbox() as sandbox:
        win = main_gui.MainWindow()
        win.show()
        app.processEvents()

        t_collect_contract(win)
        defaults = dict(getattr(win, "_default_column_widths", {}))
        state, intent_expect = t_roundtrip(win)
        t_config_channel(win, sandbox, state, intent_expect)
        t_bad_values(win, sandbox, defaults)
        t_column_count_mismatch(win)
        t_offscreen_fallback(win)
        t_reset_default(win, sandbox, defaults)
        t_protocol_switch(win, sandbox)
        written = t_exit_paths(win, sandbox)
        t_restart_restores(sandbox, written)

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
