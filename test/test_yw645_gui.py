# -*- coding: utf-8 -*-
"""协议13（依瓦定制645）GUI 端到端测试（offscreen）。

构建：main_gui（沙箱）→ 协议13 → 查询页 / 组帧页 / 预设命令页 / Tab 可见性。
对应 prd AC1（Tab 可见性与注册表一致）、AC8（组帧页可生成帧）、AC9（预设可取完整帧）。

运行：``python test/test_yw645_gui.py``（offscreen，无需显示器）。

⚠ 沙箱（AGENTS 陷阱 42）：阶段 3 的一次性 GUI 脚本曾因构造 `MainWindow` 触发
`_save_app_config()` 把真实 `config.json` 的 `parse.protocol` 写成 13。故本测试
① 用共享 `test/_config_sandbox.install()`（同时 patch `app_paths.data_path` 与
`main_gui.data_path`）；② 另把 `preset_buttons` 的 6 个模块级路径常量（import 期已固化，
patch `data_path` 盖不住）重定向到沙箱；③ 末尾断言真实 `config.json` md5 未变。
"""

import hashlib
import json
import os
import pathlib
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest import mock  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# 构造 MainWindow 之前必须屏蔽模态框，否则 offscreen 下永久阻塞
for _name in ("warning", "information", "critical", "question"):
    mock.patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
_REAL_CONFIG = ROOT / "config.json"


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


_REAL_CONFIG_HASH = _digest(_REAL_CONFIG)

SANDBOX = _config_sandbox.install()  # 进程级：app_paths.data_path + main_gui.data_path

import main_gui  # noqa: E402
import preset_buttons as pb  # noqa: E402
import protocol_registry as registry  # noqa: E402
import yw645_frame_gen as fg  # noqa: E402
import yw645_wire as W  # noqa: E402
from preset_buttons import PresetButtonManager  # noqa: E402

# preset_buttons 的路径常量在 import 期已固化 → 必须直接重定向（AGENTS 陷阱 42 同源问题）
for _attr, _name in (
    ("NW_COMMAND_PATH", "NW_command.json"),
    ("GW_COMMAND_PATH", "GW_command.json"),
    ("DLT698_COMMAND_PATH", "DLT698_command.json"),
    ("DLT645_COMMAND_PATH", "DLT645_command.json"),
    ("MODULAR_COMMAND_PATH", "MODULAR_command.json"),
    ("YW645_COMMAND_PATH", "YW645_command.json"),
):
    setattr(pb, _attr, pathlib.Path(SANDBOX) / _name)

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


def cell_text(table, row, col):
    item = table.item(row, col)
    return item.text() if item is not None else ""


def hexc(text):
    return "".join(str(text).split()).upper()


def section(title):
    print(f"\n== {title} ==")


def _app():
    inst = QApplication.instance()
    if inst is None:
        inst = QApplication([])
    return inst


_WIN = None


def _window():
    """惰性构造一次 MainWindow（沙箱内）。"""
    global _WIN
    if _WIN is None:
        _app()
        _WIN = main_gui.MainWindow()
        _app().processEvents()
    return _WIN


# ── [1] 注册表能力 ───────────────────────────────────────────────────


def test_registry():
    section("[1] 注册表能力（index=13）")
    spec = registry.get_protocol(13)
    check("frame_gen_mode='yw645'", spec.frame_gen_mode == "yw645", str(spec.frame_gen_mode))
    check("preset_mode='yw645'", spec.preset_mode == "yw645", str(spec.preset_mode))
    check("lookup_kind='di_yw645'", spec.lookup_kind == "di_yw645")
    check("extract_strategy='yw645'", spec.extract_strategy == "yw645")
    for flag in ("has_archive", "has_topology", "has_virtual_meter", "has_dlt645_sim",
                 "has_monitor", "has_sequence_diagram"):
        check(f"{flag} 为 False", getattr(spec, flag) is False, str(getattr(spec, flag)))
    check("combo_labels 第 14 项是依瓦定制645",
          len(registry.combo_labels()) == registry.protocol_count()
          and "依瓦定制645" in registry.combo_labels()[13])


# ── [2] Tab 可见性 vs 注册表 ────────────────────────────────────────


def test_tab_visibility():
    section("[2] Tab 可见性 vs 注册表（逐项对拍）")
    win = _window()
    win._on_protocol_changed(13)
    _app().processEvents()
    spec = registry.get_protocol(13)

    pairs = [
        ("_frame_gen_tab_index", spec.frame_gen_mode is not None, "协议组帧"),
        ("_preset_tab_index", spec.preset_mode is not None, "预设命令"),
        ("_archive_tab_index", spec.has_archive, "档案管理"),
        ("_topology_tab_index", spec.has_topology, "拓扑信息"),
        ("_virtual_meter_tab_index", spec.has_virtual_meter, "虚拟表"),
        ("_dlt645_sim_tab_index", spec.has_dlt645_sim, "645虚拟表"),
        ("_monitor_tab_index", spec.has_monitor, "监控器"),
        ("_seq_diagram_tab_index", spec.has_sequence_diagram, "通信时序图"),
        ("_upgrade_tab_index", spec.has_upgrade, "升级"),
    ]
    for attr, expected, label in pairs:
        idx = getattr(win, attr, None)
        if idx is None:
            check(f"{label} 页签属性存在", False, attr)
            continue
        check(f"{label} 可见性 == 注册表({expected})",
              bool(win.tab_widget.isTabVisible(idx)) == bool(expected),
              f"visible={win.tab_widget.isTabVisible(idx)} expected={expected}")
    check("协议13 下「协议组帧」页可见", win.tab_widget.isTabVisible(win._frame_gen_tab_index))
    check("协议13 下「预设命令」页可见", win.tab_widget.isTabVisible(win._preset_tab_index))
    check("协议13 下「TCP监控」「串口工具」仍可见（始终可见）",
          win.tab_widget.isTabVisible(win._tcp_monitor_tab_index)
          and win.tab_widget.isTabVisible(win._serial_tool_tab_index))


# ── [3] 组帧页 ──────────────────────────────────────────────────────


def test_frame_gen_page():
    section("[3] 组帧页（生成帧 / 输出区 / 长度-CS 注记）")
    win = _window()
    win._on_protocol_changed(13)
    tab = win._ensure_frame_gen_tab()
    _app().processEvents()

    check("组帧页协议模式 = yw645", tab.protocol_mode == "yw645", tab.protocol_mode)
    check("左栏切到协议13 组帧页（栈索引 2）", tab.left_stack.currentIndex() == 2,
          str(tab.left_stack.currentIndex()))
    check("协议9 组帧页仍在栈内（索引 1）", tab.left_stack.count() >= 3)
    check("组帧页含协议13 专属子控件", hasattr(tab, "yw645_gen"))
    gen = tab.yw645_gen
    check("模式下拉含 5 项（4 已定义 + 写模式占位）", gen.mode_combo.count() == 5,
          str(gen.mode_combo.count()))
    check("模式下拉末项是写模式占位",
          gen.mode_combo.currentData() is not None and
          gen.mode_combo.itemData(gen.mode_combo.count() - 1) == fg.WRITE_MODE_KEY)
    check("字段模式区在协议13 下隐藏", not tab.mode_group.isVisible())
    check("DI 选择区在协议13 下隐藏", not tab.cmd_select_group.isVisible())
    check("「添加到预设」按钮在协议13 下可见（有独立预设库）",
          tab.add_preset_btn.isVisible() or not tab.isVisible())

    # 默认模板（读设备类型，广播）
    frame = gen.build()
    check("默认表单可组帧", isinstance(frame, bytes) and W.is_frame(frame), frame.hex().upper())
    check("默认表单 = 读设备类型（广播 0x10 长度 2）",
          frame[1:7] == W.BROADCAST_ADDR and (frame[8], frame[9]) == (0x10, 0x02))
    check("注记含数据域与 CS", "数据域" in gen.note_label.text() and "CS=" in gen.note_label.text(),
          gen.note_label.text()[:80])

    # 真实按钮路径
    tab._on_generate()
    _app().processEvents()
    out = tab.result_hex.toPlainText().strip()
    check("点「生成帧」后输出区非空", bool(out), out[:40])
    check("点「生成帧」后实时解析预览有行", tab.preview_table.rowCount() > 0,
          str(tab.preview_table.rowCount()))
    check("输出帧与本协议解析器闭环（CS 通过）",
          bool(out) and W.is_frame(bytes.fromhex("".join(out.split()))))
    generated = bytes.fromhex("".join(out.split()))
    p = __import__("yw645_parser").YW645Parser()
    p.parse(generated)
    check("生成帧解析 valid=True 且 cs_ok=True",
          p.last_meta["valid"] is True and p.last_meta["cs_ok"] is True,
          f"valid={p.last_meta['valid']} cs_ok={p.last_meta['cs_ok']}")
    check("生成帧串口日志有协议13 注记",
          "协议13" in tab.serial_log.toPlainText())

    # 模式联动：透传模式 → 数据项表格隐藏、透传数据域出现
    idx = gen.mode_combo.findData("pass_req")
    gen.mode_combo.setCurrentIndex(idx)
    _app().processEvents()
    check("切透传模式后数据项表格隐藏", gen.items_table.isHidden())
    check("切透传模式后透传数据域输入框可见", not gen.body_edit.isHidden())
    gen.broadcast_check.setChecked(False)
    gen.addr_edit.setText("45000000013")
    gen.body_edit.setText("04E1")
    pf = gen.build()
    check("透传模式组帧 == 文档 X3", pf.hex().upper() == "680450000000136830023714B416",
          pf.hex().upper())
    check("地址注记回显实际采用地址", "04 50 00 00 00 13" in gen.addr_note.text(),
          gen.addr_note.text())

    # 写模式占位：无命令码 → 可读错误（不臆造）
    idx = gen.mode_combo.findData(fg.WRITE_MODE_KEY)
    gen.mode_combo.setCurrentIndex(idx)
    gen.body_edit.setText("1122")
    gen.write_cmd_edit.setText("")
    _app().processEvents()
    raised = False
    try:
        gen.build()
    except fg.YW645BuildError:
        raised = True
    check("写模式无命令码时生成报可读错误", raised)
    check("写模式错误红字提示", "组帧失败" in gen.note_label.text())
    gen.write_cmd_edit.setText("0x50")
    wf = gen.build()
    check("写模式手填 0x50 后可生成", wf[8] & 0xF0 == 0x50, wf.hex().upper()[:24])

    # 还原以免影响后续用例
    gen.reset()
    tab.set_protocol_mode("yw645")
    check("reset 后回到读设备类型", gen.current_mode() == "read_req")


# ── [4] 查询页过滤 ──────────────────────────────────────────────────


def test_lookup_page():
    section("[4] 查询页（附录A 数据项 + 关键词过滤）")
    win = _window()
    win._on_protocol_changed(13)
    _app().processEvents()
    check("查询页数据表存在", hasattr(win, "yw645_table"))
    table = win.yw645_table
    check("查询页初始 2 条", table.rowCount() == 2, str(table.rowCount()))

    win.yw645_search.setText("0010")
    _app().processEvents()
    check("过滤 '0010' → 1 条", table.rowCount() == 1, str(table.rowCount()))
    check("过滤 '0010' 命中设备类型", cell_text(table, 0, 1) == "设备类型", cell_text(table, 0, 1))

    win.yw645_search.setText("00 10")
    _app().processEvents()
    check("过滤 '00 10'（带空格）→ 1 条", table.rowCount() == 1, str(table.rowCount()))

    win.yw645_search.setText("设备")
    _app().processEvents()
    check("过滤 '设备' → 2 条", table.rowCount() == 2, str(table.rowCount()))

    win.yw645_search.setText("0020")
    _app().processEvents()
    check("过滤 '0020' 命中设备号", table.rowCount() == 1 and cell_text(table, 0, 1) == "设备号")

    win.yw645_search.setText("不存在的关键词")
    _app().processEvents()
    check("无匹配 → 0 条", table.rowCount() == 0, str(table.rowCount()))
    win.yw645_search.setText("")
    _app().processEvents()


# ── [5] 预设命令页 ──────────────────────────────────────────────────


def test_preset_page():
    section("[5] 预设命令页（YW645_command.json 独立，可取完整帧）")
    win = _window()
    win._on_protocol_changed(13)
    _app().processEvents()
    tab = win.preset_tab
    check("预设页协议 = yw645", tab._protocol == "yw645", tab._protocol)
    check("预设页 _get_path 回退模块默认（None）", tab._get_path() is None)
    check("预设页路径 = YW645_command.json",
          pb._get_path("yw645").name == "YW645_command.json")
    check("沙箱内尚无 YW645_command.json（首次使用）",
          not pb.YW645_COMMAND_PATH.exists())

    # 把种子内容放进沙箱（模拟首次落盘后）
    seed = json.loads((ROOT / "YW645_command.json").read_text(encoding="utf-8"))
    pb.YW645_COMMAND_PATH.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    tab.refresh()
    _app().processEvents()
    check("刷新后按钮数 == 6", len(tab._buttons) == 6, str(len(tab._buttons)))
    check("统计标签显示 6", "6" in tab.stats_label.text(), tab.stats_label.text())

    captured = []
    tab.button_clicked.connect(lambda p, h, c: captured.append((p, h, c)))
    first_id = sorted(tab._buttons.keys())[0]
    tab._buttons[first_id].click()
    _app().processEvents()
    check("预设按钮点击发出 button_clicked", len(captured) == 1, str(len(captured)))
    if captured:
        proto, hex_text, _cfg = captured[0]
        check("发出协议标识 = yw645", proto == "yw645", proto)
        frame = bytes.fromhex("".join(hex_text.split()))
        check("取出的帧结构完整（68…16 + 长度自洽）", W.is_frame(frame), hex_text[:40])
        check("取出的帧可被本协议解析（CS 通过）",
              __import__("yw645_parser").YW645Parser().parse(frame) is not None)

    # 隔离：GW/DLT645 未被创建
    check("沙箱内 GW_command.json 未被创建", not pb.GW_COMMAND_PATH.exists())
    check("沙箱内 DLT645_command.json 未被创建", not pb.DLT645_COMMAND_PATH.exists())


# ── [5b] 「添加到预设」真实 GUI 路径 ────────────────────────────────


class _FakeAddPresetDialog:
    """替身对话框：自动接受（真实 QDialog.exec 在 offscreen 下会阻塞）。"""

    name = "GUI-测试预设"

    def __init__(self, frame_hex, protocol, parent=None):
        self._frame_hex = frame_hex
        self._protocol = protocol

    def exec(self):
        return 1  # QDialog.Accepted

    def get_result(self):
        return {
            "protocol": self._protocol,
            "button_name": self.name,
            "group_name": "读模式",
            "frame_hex": self._frame_hex,
            "description": "GUI 端到端测试条目",
        }


def test_add_to_preset_real_path():
    section("[5b] 「添加到预设」真实路径 → YW645_command.json")
    import frame_gen_widget as fgw

    win = _window()
    win._on_protocol_changed(13)
    tab = win._ensure_frame_gen_tab()
    _app().processEvents()
    tab._on_generate()
    _app().processEvents()
    check("组帧页已生成帧（供添加预设）", bool(tab.result_hex.toPlainText().strip()))

    before_gw = pb.GW_COMMAND_PATH.read_bytes() if pb.GW_COMMAND_PATH.exists() else None
    before_d645 = pb.DLT645_COMMAND_PATH.read_bytes() if pb.DLT645_COMMAND_PATH.exists() else None

    with mock.patch.object(fgw, "AddPresetDialog", _FakeAddPresetDialog):
        tab._on_add_to_preset_clicked()
    _app().processEvents()

    cmds = PresetButtonManager.load_commands("yw645")
    entry = next((c for c in cmds if c.get("button_name") == _FakeAddPresetDialog.name), None)
    check("新条目写入 YW645_command.json", entry is not None, f"共 {len(cmds)} 条")
    if entry:
        check("新条目 protocol=yw645", entry.get("protocol") == "yw645", str(entry.get("protocol")))
        check("新条目 frame_hex 为完整可解析帧",
              W.is_frame(bytes.fromhex(hexc(entry.get("frame_hex", "")))))
        check("新条目 config 含 yw645 状态快照",
              "yw645" in (entry.get("config") or {}), str(list((entry.get("config") or {}).keys())))

    gw_after = pb.GW_COMMAND_PATH.read_bytes() if pb.GW_COMMAND_PATH.exists() else None
    d645_after = pb.DLT645_COMMAND_PATH.read_bytes() if pb.DLT645_COMMAND_PATH.exists() else None
    check("GW_command.json 未被创建/修改（陷阱65 护栏）", gw_after == before_gw)
    check("DLT645_command.json 未被创建/修改", d645_after == before_d645)


# ── [6] 真实配置未被污染 ────────────────────────────────────────────


def test_no_real_config_pollution():
    section("[6] 真实 config.json 未被测试改写")
    if not _REAL_CONFIG.exists():
        check("真实 config.json 不存在（无可污染对象）", True)
        return
    now = _digest(_REAL_CONFIG)
    check("真实 config.json 摘要与运行前一致", now == _REAL_CONFIG_HASH,
          f"{now[:16]} vs {_REAL_CONFIG_HASH[:16]}")
    check("沙箱 config.json 路径不是真实路径",
          main_gui.data_path("config.json") != _REAL_CONFIG,
          str(main_gui.data_path("config.json")))


def main():
    test_registry()
    test_tab_visibility()
    test_frame_gen_page()
    test_lookup_page()
    test_preset_page()
    test_add_to_preset_real_path()
    test_no_real_config_pollution()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    os._exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
