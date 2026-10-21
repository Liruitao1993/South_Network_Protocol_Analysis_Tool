# -*- coding: utf-8 -*-
"""生产测试架页回归：纯逻辑组帧 + checksum8 + GUI（offscreen）+ main_gui 接线。

覆盖的冻结判据：

A. 纯逻辑（`production_testbench_core`）
   - 现场样例帧**逐字节复现**（75 字节，CS8 = 0x39），字段顺序/长度/校验范围任一改动即红
   - checksum8 = 8 位算术和（溢出回绕）与三种落位方式（追加 / 覆盖末字节 / 插在 16H 前）
   - HEX / ASCII 编解码、显示渲染、时间戳
   - 脏配置回落默认、配置读写往返

B. GUI（`production_testbench_widget`，offscreen + 假串口）
   - 5 条发送框、未连接禁用、连接后启用
   - 参数预览/发送 = 样例帧；单框 CS8 三种方式；非法输入不发送且日志有原因
   - HEX/ASCII 显示、时间戳开关、恢复现场示例、改参数即时生效
   - 落盘后重开恢复、主题切换、cleanup 幂等

C. main_gui 接线
   - 「生产测试架」tab 常驻可见（切协议不隐藏）、懒加载注入共享串口、主题钩子不抛

直接运行: python test/test_production_testbench.py
"""

import _path_setup  # noqa: E402,F401

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json  # noqa: E402
import pathlib  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# 构造主窗口前屏蔽模态框（offscreen 下会永久阻塞）
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402

SANDBOX = _config_sandbox.install()

import production_testbench_core as core  # noqa: E402
import production_testbench_widget as wgt  # noqa: E402

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    line = f"[{tag}] {name}"
    if detail and not cond:
        line += f"  -- {detail}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


def section(title):
    print(f"\n=== {title} ===")


class FakeWorker(QObject):
    """假串口线程：只需主窗口/页面用到的那几条信号与两个方法。"""

    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.opened = True
        self.sent = []

    def is_open(self):
        return self.opened

    def write_raw(self, data):
        if not self.opened:
            return False
        self.sent.append(bytes(data))
        return True


# ======================================================================
# A. 纯逻辑
# ======================================================================
def test_core():
    section("A. 纯逻辑：字段表 / 组帧 / checksum8 / 文本")

    keys = [s.key for s in (*core.HEADER_FIELDS, *core.BODY_FIELDS)]
    check("字段 key 唯一", len(keys) == len(set(keys)), str(len(keys)))
    check("参数 47 项（+ 帧头 2 项 = 现场参数表 49 项）",
          len(core.BODY_FIELDS) == 47, str(len(core.BODY_FIELDS)))
    check("参数区合计 53 字节",
          sum(s.size for s in core.BODY_FIELDS) == core.BODY_LEN,
          str(sum(s.size for s in core.BODY_FIELDS)))
    grouped = [k for _title, ks in core.FIELD_GROUPS for k in ks]
    check("分组覆盖全部参数区字段且不重复",
          sorted(grouped) == sorted(s.key for s in core.BODY_FIELDS))

    frame = core.build_bench_frame()
    check("现场样例帧逐字节复现",
          core.format_hex_field(frame) == core.ORACLE_FRAME_HEX,
          core.format_hex_field(frame))
    check("整帧 75 字节", len(frame) == core.FRAME_LEN, str(len(frame)))
    check("帧头：68 + 地址6 + 68", frame[0] == 0x68 and frame[7] == 0x68 and frame[1:7] == b"\xAA" * 6)
    check("控制域 14H / 长度域 = 参数区 53", frame[8] == 0x14 and frame[9] == core.BODY_LEN)
    check("命令标识 55AA55AA", frame[10:14] == core.BENCH_CMD)
    check("测试STA=01 / 测试无线=00", frame[14] == 0x01 and frame[15] == 0x00)
    check("保留 4 字节为 00", frame[69:73] == b"\x00" * 4)
    check("末字节 16H", frame[-1] == 0x16)
    check("CS8 = 首字节到保留位末字节的算术和", frame[-2] == core.checksum8(frame[:-2]),
          f"{frame[-2]:02X} vs {core.checksum8(frame[:-2]):02X}")
    check("反例：校验范围不含 68H 帧头时对不上（证明范围含帧头）",
          core.checksum8(frame[7:-2]) != frame[-2],
          f"{core.checksum8(frame[7:-2]):02X}")

    # checksum8 本体
    check("checksum8 空数据 = 0", core.checksum8(b"") == 0)
    check("checksum8 溢出回绕", core.checksum8(bytes([0xFF, 0x02])) == 0x01)

    data = bytes.fromhex("68AA0116")
    check("CS8 追加到末尾",
          core.apply_checksum8(data, core.CS_MODE_APPEND).hex().upper() == "68AA011629",
          core.apply_checksum8(data, core.CS_MODE_APPEND).hex().upper())
    check("CS8 覆盖末字节",
          core.apply_checksum8(data, core.CS_MODE_REPLACE_LAST).hex().upper() == "68AA0113",
          core.apply_checksum8(data, core.CS_MODE_REPLACE_LAST).hex().upper())
    check("CS8 插在 16H 前",
          core.apply_checksum8(data, core.CS_MODE_BEFORE_END).hex().upper() == "68AA011316",
          core.apply_checksum8(data, core.CS_MODE_BEFORE_END).hex().upper())
    check("末字节非 16H 时 before_end 回落追加",
          core.apply_checksum8(bytes.fromhex("0102"), core.CS_MODE_BEFORE_END).hex().upper()
          == "010203")

    # 文本编解码
    check("HEX 解析：空格/换行/逗号/0x 前缀",
          core.parse_hex_text("0x68, AA\n01\t16") == bytes.fromhex("68AA0116"))
    for text, why in (("68A", "奇数长度"), ("68 ZZ", "非法字符"), ("", "空内容")):
        try:
            core.parse_hex_text(text)
            ok = False
        except core.ParamError:
            ok = True
        check(f"HEX 解析拒绝：{why}", ok)
    check("HEX 渲染大写空格分隔", core.render_display(b"\x68\xAA", "hex") == "68 AA")
    check("ASCII 渲染不可打印为 .", core.render_display(b"AT\r\n", "ascii") == "AT..")
    check("ASCII 发送编码", core.parse_ascii_text("AT+CSQ") == b"AT+CSQ")

    cfg = core.SendBoxConfig(text="68 AA 01 16", mode="hex", cs8=True,
                             cs8_mode=core.CS_MODE_BEFORE_END)
    check("发送框载荷（HEX + CS8 插在 16H 前）",
          core.build_send_payload(cfg) == bytes.fromhex("68AA011316"))
    cfg_ascii = core.SendBoxConfig(text="AT", mode="ascii", cs8=False)
    check("发送框载荷（ASCII 不校验）", core.build_send_payload(cfg_ascii) == b"AT")

    # 字段顺序：改单个字节必须只落在该字段偏移
    values = core.default_values()
    values["module_type"] = "03"
    f2 = core.build_bench_frame(values)
    check("模块类型改动只影响参数区第 9 字节（偏移 25）",
          f2[25] == 0x03 and f2[:25] == frame[:25] and f2[26:-2] == frame[26:-2])
    check("参数改动后 CS8 重算", f2[-2] == core.checksum8(f2[:-2]) and f2[-2] != frame[-2])
    f3 = core.build_bench_frame({"test_sta": 0})
    check("测试STA=00 落在帧头偏移 14", f3[14] == 0x00 and f3[15] == 0x00)
    f4 = core.build_bench_frame({"meter_addr_hi": "A1A2A3A4"})
    check("表号 4 字节落在偏移 36..39", f4[36:40] == bytes.fromhex("A1A2A3A4"))

    # 非法输入
    try:
        core.build_bench_frame({"charge_time": "6"})
        ok, msg = False, ""
    except core.ParamError as exc:
        ok, msg = True, str(exc)
    check("长度不符时拒绝并给出字段名", ok and "充电时间" in msg, msg if ok else "未抛异常")
    try:
        core.build_bench_frame(addr_hex="AA")
        ok = False
    except core.ParamError:
        ok = True
    check("地址域长度不符时拒绝", ok)
    try:
        core.build_bench_frame({"has_capacitor": 2})
        ok = False
    except core.ParamError:
        ok = True
    check("下拉字段取值超范围时拒绝", ok)

    # 配置合并 / 读写
    merged = core.merge_config({
        "params": {"charge_time": "EE", "discharge_time": "ZZ", "module_type": "03",
                   "has_capacitor": "07"},
        "addr_hex": "112233445566",
        "send_boxes": [{"name": "A", "text": "68", "mode": "ascii", "cs8": True}],
        "display": {"mode": "ascii", "timestamp": False, "autoscroll": False},
    })
    check("脏参数（非 HEX）回落默认", merged["params"]["discharge_time"] == "0E")
    check("合法参数保留", merged["params"]["charge_time"] == "EE"
          and merged["params"]["module_type"] == "03")
    check("下拉字段非法取值回落默认", merged["params"]["has_capacitor"] == "01")
    check("地址域合法值保留", merged["addr_hex"] == "112233445566")
    check("发送框不足 5 条时补齐", len(merged["send_boxes"]) == core.SEND_BOX_COUNT)
    check("显示偏好保留", merged["display"] == {"mode": "ascii", "timestamp": False,
                                              "autoscroll": False})
    check("整体脏数据（非 dict）回落默认",
          core.merge_config("oops") == core.default_config())

    # 参数帧发送形态（HEX 二进制 / ASCII 文本）
    oracle_frame = bytes.fromhex(core.ORACLE_FRAME_HEX)
    check("frame_payload：HEX 原样二进制",
          core.frame_payload(oracle_frame, "hex") == oracle_frame)
    check("frame_payload：ASCII = 大写 HEX 文本",
          core.frame_payload(oracle_frame, "ascii")
          == core.ORACLE_FRAME_HEX.encode("ascii"))
    check("默认 params_mode = hex", core.default_config()["params_mode"] == "hex")
    check("非法 params_mode 回落默认",
          core.merge_config({"params_mode": "bogus"})["params_mode"] == "hex")
    check("params_mode 保留合法值",
          core.merge_config({"params_mode": "ascii"})["params_mode"] == "ascii")

    # 三栏布局配置
    check("默认配置含三栏布局",
          core.default_config()["layout"]["sizes"] == list(core.DEFAULT_LAYOUT_SIZES)
          and core.default_config()["layout"]["left_collapsed"] is False)
    kept = core.merge_config({"layout": {"left_collapsed": True,
                                         "right_collapsed": False,
                                         "sizes": [300, 700, 30]}})
    check("布局折叠状态与宽度保留",
          kept["layout"] == {"left_collapsed": True, "right_collapsed": False,
                             "sizes": [300, 700, 30]}, str(kept["layout"]))
    bad_layout = core.merge_config({"layout": {"sizes": [0, -1, "x"],
                                               "left_collapsed": "yes"}})
    check("脏布局尺寸回落默认、布尔按真值取",
          bad_layout["layout"]["sizes"] == list(core.DEFAULT_LAYOUT_SIZES)
          and bad_layout["layout"]["left_collapsed"] is True,
          str(bad_layout["layout"]))

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ptb_cfg_"))
    path = str(tmp / "cfg.json")
    check("配置写盘成功", core.save_config(path, merged) is True)
    loaded = core.load_config(path)
    check("配置读回一致（参数/地址/显示）",
          loaded["params"]["charge_time"] == "EE"
          and loaded["addr_hex"] == "112233445566"
          and loaded["display"]["mode"] == "ascii")
    check("缺失文件回落默认", core.load_config(str(tmp / "missing.json")) == core.default_config())
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ 坏 JSON")
    check("损坏 JSON 回落默认", core.load_config(path) == core.default_config())


# ======================================================================
# B. GUI
# ======================================================================
def read_log(tab):
    """读取日志窗口内容（日志每 100 ms 合并刷新，测试里先强制刷一次）。"""
    tab._flush_log()
    return tab.log_text.toPlainText()


def test_gui(app):
    section("B. GUI：发送框 / 参数帧 / 日志 / 落盘 / 主题")

    tab = wgt.ProductionTestbenchWidget()
    tab.resize(1500, 900)
    tab.show()
    app.processEvents()
    check("5 条发送配置框", len(tab.send_boxes) == core.SEND_BOX_COUNT,
          str(len(tab.send_boxes)))
    check("三栏布局：左发送配置 / 中接收日志 / 右测试架参数",
          tab.split_columns.count() == 3
          and tab.split_columns.widget(0) is tab.left_panel
          and tab.split_columns.widget(1) is tab.log_group
          and tab.split_columns.widget(2) is tab.right_panel)
    check("左右栏都有折叠按钮",
          tab.left_panel.btn_toggle.isVisible() and tab.right_panel.btn_toggle.isVisible())
    base_sizes = tab.split_columns.sizes()
    check("三栏初始都有宽度", all(v > 0 for v in base_sizes), str(base_sizes))
    check("折叠按钮贴外沿（左栏在左、右栏在右）",
          tab.left_panel.btn_toggle.geometry().x() < tab.left_panel.title_label.geometry().x()
          and tab.right_panel.btn_toggle.geometry().x()
          > tab.right_panel.title_label.geometry().x(),
          f"L {tab.left_panel.btn_toggle.geometry()} / R {tab.right_panel.btn_toggle.geometry()}")
    check("发送区无横向滚动条", tab.send_scroll.horizontalScrollBar().maximum() == 0,
          str(tab.send_scroll.horizontalScrollBar().maximum()))
    check("参数区无横向滚动条", tab.params_scroll.horizontalScrollBar().maximum() == 0,
          str(tab.params_scroll.horizontalScrollBar().maximum()))

    # ── 折叠 / 展开：宽度让给日志，展开后还原 ──
    tab.left_panel.set_expanded(False)
    app.processEvents()
    left_sizes = tab.split_columns.sizes()
    check("折叠左栏后只剩窄条",
          left_sizes[0] <= wgt.SIDE_COLLAPSED_WIDTH + 1, str(left_sizes))
    check("折叠左栏后日志变宽", left_sizes[1] > base_sizes[1],
          f"{base_sizes} -> {left_sizes}")
    check("折叠后发送区内容隐藏", not tab.left_panel.body.isVisible())
    check("折叠窄条上有竖排标题",
          tab.left_panel.vertical_label.isVisible()
          and tab.left_panel.vertical_label.text().replace("\n", "") == "发送配置",
          tab.left_panel.vertical_label.text())
    tab.left_panel.set_expanded(True)
    app.processEvents()
    restored = tab.split_columns.sizes()
    check("展开左栏恢复原宽度", abs(restored[0] - base_sizes[0]) <= 10,
          f"{base_sizes} -> {restored}")

    tab.right_panel.set_expanded(False)
    app.processEvents()
    right_sizes = tab.split_columns.sizes()
    check("折叠右栏后只剩窄条",
          right_sizes[2] <= wgt.SIDE_COLLAPSED_WIDTH + 1, str(right_sizes))
    check("折叠右栏后日志变宽", right_sizes[1] > restored[1],
          f"{restored} -> {right_sizes}")
    check("折叠后参数区内容隐藏", not tab.right_panel.body.isVisible())
    tab.right_panel.set_expanded(True)
    app.processEvents()
    check("展开右栏恢复原宽度",
          abs(tab.split_columns.sizes()[2] - base_sizes[2]) <= 10,
          str(tab.split_columns.sizes()))

    # ── 拖动分隔条（三栏宽度可调；左右栏有最小宽度，取 340/760/380）──
    tab.split_columns.setSizes([340, 760, 380])
    app.processEvents()
    dragged = tab.split_columns.sizes()
    check("三栏宽度可拖动",
          abs(dragged[0] - 340) <= 15 and abs(dragged[2] - 380) <= 15
          and dragged[1] > 700, str(dragged))
    tab.split_columns.setSizes(list(base_sizes))
    app.processEvents()
    check("未连接时发送按钮全部禁用",
          all(not b.btn_send.isEnabled() for b in tab.send_boxes)
          and not tab.btn_send_params.isEnabled())
    check("参数预览 = 现场样例帧", tab.preview_edit.text().replace(" ", "").upper()
          == core.ORACLE_FRAME_HEX)
    check("预览状态行给出字节数与 CS8",
          "75 字节" in tab.lbl_preview_state.text()
          and "0x39" in tab.lbl_preview_state.text(), tab.lbl_preview_state.text())

    fake = FakeWorker()
    tab.set_serial_worker(fake)
    check("注入串口后发送按钮启用",
          all(b.btn_send.isEnabled() for b in tab.send_boxes) and tab.btn_send_params.isEnabled())
    check("状态行显示已连接", "已连接" in tab.lbl_serial_state.text(), tab.lbl_serial_state.text())

    # 参数帧发送
    tab._on_send_params()
    check("发送参数帧 = 现场样例字节",
          fake.sent and core.format_hex_field(fake.sent[-1]) == core.ORACLE_FRAME_HEX)
    check("TX 日志带 [TX] 前缀", "[TX] 68 AA" in read_log(tab))

    # 发送形态：HEX（二进制）/ ASCII（HEX 文本），与左侧发送框同一语义
    check("参数帧默认按 HEX（二进制）发送", len(fake.sent[-1]) == core.FRAME_LEN)
    tab.combo_params_mode.setCurrentIndex(1)
    tab._on_send_params()
    ascii_payload = fake.sent[-1]
    check("参数帧可切 ASCII 发送（HEX 文本字符）",
          len(ascii_payload) == core.FRAME_LEN * 2 and ascii_payload.isascii()
          and ascii_payload.decode("ascii") == core.ORACLE_FRAME_HEX,
          str(len(ascii_payload)))
    check("ASCII 发送在日志里注明形态", "ASCII 文本" in read_log(tab))
    tab.combo_params_mode.setCurrentIndex(0)

    # 单框 CS8 三种方式
    box = tab.send_boxes[0]
    box.text_edit.setPlainText("68 AA 01 16")
    box.cs8_check.setChecked(True)
    for idx, expect in ((0, "68AA011629"), (1, "68AA0113"), (2, "68AA011316")):
        box.cs8_mode.setCurrentIndex(idx)
        box._on_send()
        check(f"发送框 CS8 方式 {core.CS_MODES[idx][1]}",
              core.format_hex_field(fake.sent[-1]) == expect,
              core.format_hex_field(fake.sent[-1]))
    box.cs8_check.setChecked(False)
    box._on_send()
    check("关闭 CS8 时原样发送",
          core.format_hex_field(fake.sent[-1]) == "68AA0116")

    # 非法输入：不发送、日志给原因
    before = len(fake.sent)
    box.text_edit.setPlainText("68 A")
    box._on_send()
    check("非法 HEX 不发送", len(fake.sent) == before)
    check("非法 HEX 日志给原因", "内容非法" in read_log(tab))
    check("发送框状态显示错误", box.status.text() != "就绪", box.status.text())

    # HEX / ASCII 显示 + 时间戳
    fake.raw_data_received.emit(bytes.fromhex("68AA0116"))
    last = read_log(tab).strip().splitlines()[-1]
    check("HEX 显示接收", "[RX] 68 AA 01 16" in last, last)
    check("默认带时间戳", last[:4].isdigit() and last[4] == "-", last)
    tab.combo_display.setCurrentIndex(1)
    fake.raw_data_received.emit(b"AT\r\n")
    last = read_log(tab).strip().splitlines()[-1]
    check("ASCII 显示接收", "[RX] AT.." in last, last)
    tab.chk_timestamp.setChecked(False)
    fake.raw_data_received.emit(b"OK")
    last = read_log(tab).strip().splitlines()[-1]
    check("关闭时间戳后不带日期", last.startswith("[RX]"), last)
    tab.combo_display.setCurrentIndex(0)

    # 日志合并刷新：高吞吐时不再逐行 insertText（否则 1000 行/秒会卡界面）
    tab._on_clear_log()
    for i in range(5):
        tab._log(f"批量 {i}", "info")
    check("合并刷新前不逐行写入", tab.log_text.toPlainText() == "",
          tab.log_text.toPlainText())
    tab._flush_log()
    check("flush 后一次写入 5 行",
          len(read_log(tab).strip().splitlines()) == 5, read_log(tab))
    tab._on_clear_log()
    for i in range(wgt.LOG_FLUSH_MAX + 5):
        tab._log(f"x{i}")
    check("超过上限立即刷新",
          len(tab.log_text.toPlainText().strip().splitlines()) >= wgt.LOG_FLUSH_MAX,
          str(len(tab.log_text.toPlainText().strip().splitlines())))
    tab._on_clear_log()

    # 参数改动即时生效 + 恢复现场示例
    check("帧头两项测试开关也在参数面板里",
          "test_sta" in tab._param_widgets and "test_wireless" in tab._param_widgets)
    tab._set_param("test_sta", 0)
    tab._set_param("test_wireless", 1)
    tab._refresh_preview()
    check("面板可改帧头测试STA / 测试无线",
          tab.current_frame_hex()[28:32] == "0001", tab.current_frame_hex()[28:32])
    tab._set_param("module_type", "03")
    tab._refresh_preview()
    check("界面改参数后帧字节变化",
          tab.current_frame_hex()[50:52] == "03", tab.current_frame_hex()[50:52])
    tab._on_restore_defaults()
    check("恢复现场示例后回到样例帧", tab.current_frame_hex() == core.ORACLE_FRAME_HEX)

    # 复制报文
    tab._on_copy_frame()
    check("复制报文到剪贴板",
          QApplication.clipboard().text().replace(" ", "").upper() == core.ORACLE_FRAME_HEX)

    # 落盘 → 重开恢复
    tab.send_boxes[2].name_edit.setText("读版本")
    tab.send_boxes[2].text_edit.setPlainText("68 01 02 16")
    tab.send_boxes[2].cs8_check.setChecked(True)
    tab._set_param("erase_delay", "07")
    tab.right_panel.set_expanded(False)          # 折叠状态也要记住
    tab.combo_params_mode.setCurrentIndex(1)     # 发送形态也要记住
    app.processEvents()
    tab.split_columns.setSizes([360, 900, wgt.SIDE_COLLAPSED_WIDTH])
    app.processEvents()
    tab.cleanup()
    cfg_path = pathlib.Path(SANDBOX) / wgt.CONFIG_NAME
    check("落盘文件已写入沙箱", cfg_path.exists(), str(cfg_path))
    saved = json.loads(cfg_path.read_text(encoding="utf-8"))
    check("落盘包含发送框与参数", saved["send_boxes"][2]["name"] == "读版本"
          and saved["params"]["erase_delay"] == "07")
    check("落盘包含三栏折叠状态与宽度",
          saved["layout"]["right_collapsed"] is True
          and saved["layout"]["left_collapsed"] is False
          and len(saved["layout"]["sizes"]) == 3, str(saved.get("layout")))
    check("落盘包含参数帧发送形态", saved.get("params_mode") == "ascii",
          str(saved.get("params_mode")))

    tab2 = wgt.ProductionTestbenchWidget()
    tab2.set_serial_worker(FakeWorker())
    tab2.resize(1500, 900)
    tab2.show()
    app.processEvents()
    check("重开后发送框内容恢复",
          tab2.send_boxes[2].name_edit.text() == "读版本"
          and tab2.send_boxes[2].cs8_check.isChecked())
    check("重开后参数恢复", tab2._param_values()["erase_delay"] == "07")
    check("重开后按恢复参数组帧",
          tab2.current_frame_hex()[136:138] == "07", tab2.current_frame_hex()[136:138])
    check("重开后折叠状态恢复", not tab2.right_panel.is_expanded()
          and tab2.left_panel.is_expanded())
    check("重开后参数帧发送形态恢复",
          str(tab2.combo_params_mode.currentData()) == "ascii",
          str(tab2.combo_params_mode.currentData()))
    check("重开后三栏宽度恢复",
          abs(tab2.split_columns.sizes()[2] - wgt.SIDE_COLLAPSED_WIDTH) <= 1
          and abs(tab2.split_columns.sizes()[0] - saved["layout"]["sizes"][0]) <= 12,
          f"{saved['layout']['sizes']} -> {tab2.split_columns.sizes()}")

    # 主题 / 断开 / 幂等
    try:
        tab2.restyle_for_theme(True)
        tab2.restyle_for_theme(False)
        theme_ok = True
    except Exception as exc:  # noqa: BLE001
        theme_ok = False
        print(f"    异常：{type(exc).__name__}: {exc}")
    check("主题切换不抛异常", theme_ok)
    tab2._serial_worker.connection_changed.emit(False)
    check("断开后发送按钮禁用",
          all(not b.btn_send.isEnabled() for b in tab2.send_boxes)
          and not tab2.btn_send_params.isEnabled())
    try:
        tab2.cleanup()
        tab2.cleanup()
        idem_ok = True
    except Exception as exc:  # noqa: BLE001
        idem_ok = False
        print(f"    异常：{type(exc).__name__}: {exc}")
    check("cleanup 幂等", idem_ok)

    tab.deleteLater()
    tab2.deleteLater()
    return fake


# ======================================================================
# C. main_gui 接线
# ======================================================================
def test_wiring(app, fake):
    section("C. main_gui 接线：常驻 tab / 懒加载 / 主题")

    import main_gui

    win = main_gui.MainWindow()
    app.processEvents()

    titles = [win.tab_widget.tabText(i) for i in range(win.tab_widget.count())]
    check("「生产测试架」tab 已注册", "生产测试架" in titles, str(titles))
    idx = win._testbench_tab_index
    check("排在「蓝牙工具」之后（不打断既有的工具页相邻关系）",
          idx == win._bluetooth_tool_tab_index + 1,
          f"{win._bluetooth_tool_tab_index} -> {idx}")
    check("tab 常驻可见", win.tab_widget.isTabVisible(idx))
    check("懒加载前未创建页面", not hasattr(win, "testbench_tab"))

    win.tab_widget.setCurrentIndex(idx)
    app.processEvents()
    check("切到该页后完成懒加载", hasattr(win, "testbench_tab"))
    tab = getattr(win, "testbench_tab", None)
    check("注入的是主窗口共享串口", tab is not None and tab._serial_worker is win.serial_worker)

    for proto in (0, 8, 9, 14):
        win.protocol_combo.setCurrentIndex(proto)
        app.processEvents()
        if not win.tab_widget.isTabVisible(idx):
            break
    check("切换协议后 tab 仍可见（与协议无关）", win.tab_widget.isTabVisible(idx))

    try:
        win._restyle_for_theme()
        hook_ok = True
    except Exception as exc:  # noqa: BLE001
        hook_ok = False
        print(f"    异常：{type(exc).__name__}: {exc}")
    check("主窗口主题钩子调用不抛异常", hook_ok)

    try:
        tab.cleanup()
        cleanup_ok = True
    except Exception as exc:  # noqa: BLE001
        cleanup_ok = False
        print(f"    异常：{type(exc).__name__}: {exc}")
    check("页面 cleanup 可用", cleanup_ok)

    win.close()
    app.processEvents()


def main():
    app = QApplication.instance() or QApplication([])
    test_core()
    fake = test_gui(app)
    test_wiring(app, fake)

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项：")
        for name in FAILURES:
            print(f"  - {name}")
        sys.stdout.flush()
        os._exit(1)
    print(f"全部测试通过（{PASS} 项）✓")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
