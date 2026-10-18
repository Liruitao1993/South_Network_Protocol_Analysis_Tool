# -*- coding: utf-8 -*-
"""报文工具「地址替换（按协议替换地址域 + 重算校验）」回归测试。

覆盖：
  [1] 口径与字段来源：FE_WAKEUP_PROTOCOLS / supported_choices 顺序 / fields_for 字段集 /
      addr_field_errors（写法级校验，698 SA 长度留待 apply 判定）
  [2] 六协议**真帧** oracle：replace_frame_address → 帧长不变 + 地址域写入期望字节 +
      **该协议校验器 0 fail** + 只有地址/校验字节变化 + notes 非空
  [2b] 前导 FEH 门控：只对协议 6/8 剥离并**原样恢复**；其余协议带 FE 拒绝（不得被「救活」）
  [2c] 错误矩阵：空/非法 HEX/奇数位/未填地址/未选协议/不支持协议/错协议自证失败 → 一律可读原因
  [2d] 输入写法容错：分隔符与 0x 前缀、连续无分隔写法与空格写法**结果等价**
  [3] 反例自检：改了地址但不重算校验 → 校验器必红（证明 [2] 的 oracle 有效）
  [4] offscreen GUI：协议下拉与 supported_choices 同源、切协议重建地址行、填值回切保留、
      提示行预览、真实点击替换（结果行/输出/剪贴板/回填输入）、失败不覆盖结果行、按钮不裁字

帧夹具与 `test/test_serial_addr_fix.py` / `test/test_bluetooth_addr_fix.py` 同源（六协议真帧；
国网用仓库自身组帧器造，组帧器即布局权威）—— 地址/校验算法本身由 `frame_addr_fix` 负责，
这里只关心「报文工具这层」的编排与界面接线。

运行: QT_QPA_PLATFORM=offscreen python -u test/test_message_tool_addr_fix.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

import _config_sandbox  # noqa: E402

# 构造/操作 widget 前屏蔽模态框（offscreen 下会永久阻塞）
MSGS = []


def _recorder(kind):
    def _fn(*args, **kwargs):
        MSGS.append((kind, args[2] if len(args) > 2 else ""))
        return 0
    return _fn


for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, _recorder(_name)).start()

_config_sandbox.install()

import frame_addr_fix  # noqa: E402

import message_tool_widget as mtw  # noqa: E402
import protocol_registry  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


def hx(text):
    return bytes.fromhex(text.replace(" ", ""))


def unhex(text):
    return bytes.fromhex(str(text).replace(" ", ""))


def hex_text(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def v_fail(index, frame):
    """校验器的失败项数量（0 = 通过）。"""
    result = protocol_registry.make_validator(index).verify(frame)
    return result.fail_count


# ── 真帧夹具（与 test_serial_addr_fix.py 同源）─────────────────────────────

#: 南网（协议0）带地址域（控制域 D5=1）：源 00×6，目的 22 00 00 00 00 00
SOUTH_ADDR = hx("68 28 00 20 00 00 00 00 00 00 22 00 00 00 00 00 02 00 01 02 02 "
                "E8 00 00 00 1E 00 09 00 01 02 03 04 05 06 07 08 09 85 16")
#: 南网（协议0）无地址域（控制域 D5=0）
SOUTH_NOADDR = hx("68 0C 00 00 02 00 03 02 00 E8 EF 16")
#: 645（协议6）读正向有功总电能（表地址 00×6）
DLT645 = hx("68 00 00 00 00 00 00 68 11 04 33 33 34 33 B2 16")
#: 698.45（协议8）柔控命令（地址特征 0x04 + SA=33 00 00 00 00 + CA=00）
T698 = hx("68 1F 00 43 04 33 00 00 00 00 00 0C 57 06 01 01 80 02 02 00 02 02 05 "
          "D0 07 00 00 11 05 00 32 4D 16")
#: 依瓦645（协议13）透传模式请求（表号 045000000013）
YW645 = hx("68 04 50 00 00 00 13 68 30 02 37 14 B4 16")
#: 南网上行（协议14）读当前数据·正向有功总电能（A1=00 00 00，A2=1，A3=0）
CSG_UPLINK = hx("68 10 00 10 00 68 4B 00 00 00 01 00 00 00 0C 60 01 01 00 00 01 00 BB 16")

FE4 = b"\xfe\xfe\xfe\xfe"


def gdw_frame():
    """国网（协议7）带地址域的帧：用仓库自身组帧器造（组帧器即布局权威）。"""
    from gdw_send_frame_lib import GDWFrameGenerator

    return GDWFrameGenerator().generate_frame(
        afn=1, fn=1, field_values={},
        info_config={"通信模块标识": 1, "中继级别": 0},
        src_addr="000000000001", dst_addr="000000000002",
    )


# ── [1] 口径与字段来源 ─────────────────────────────────────────────────────

def test_constants():
    section("[1] 口径与字段来源")

    check("前导 FE 只对 6/8（645 §5.3.1 / 698.45 §6.3.1 b)",
          tuple(mtw.FE_WAKEUP_PROTOCOLS) == (6, 8), mtw.FE_WAKEUP_PROTOCOLS)

    choices = frame_addr_fix.supported_choices()
    check("下拉项顺序与 SUPPORTED_PROTOCOLS 一致",
          [index for _label, index in choices] == list(frame_addr_fix.SUPPORTED_PROTOCOLS),
          choices)
    check("下拉项标签带 [i] 前缀（与主窗口协议下拉同口径）",
          all(label.startswith(f"[{index}]") for label, index in choices), choices)
    check("协议 9（新一代）不在下拉里（v1 不支持地址替换）",
          9 not in [index for _label, index in choices])

    expected_keys = {
        0: ("src", "dst"),
        6: ("addr",),
        7: ("src", "dst"),
        8: ("sa", "ca"),
        13: ("addr",),
        14: ("a2",),
    }
    for index, keys in expected_keys.items():
        got = tuple(spec.key for spec in frame_addr_fix.fields_for(index))
        check(f"协议{index} 地址字段集 = {keys}（界面不硬编码协议细节）", got == keys, got)
    check("不支持的协议 9 无字段（界面据此不出地址行）", frame_addr_fix.fields_for(9) == ())

    # addr_field_errors：写法级校验（空值跳过；698 SA 长度留待 apply 判定）
    check("645 地址长度不符报错", any("6 字节" in e for e in
                                   mtw.addr_field_errors(6, {"addr": "00 00"})),
          mtw.addr_field_errors(6, {"addr": "00 00"}))
    check("空值跳过（不误报）", mtw.addr_field_errors(6, {"addr": ""}) == [])
    check("698 SA 长度推导不出 → 不在这里报错（交给 apply）",
          mtw.addr_field_errors(8, {"sa": "0000000099", "ca": "7"}) == [],
          mtw.addr_field_errors(8, {"sa": "0000000099", "ca": "7"}))
    check("698 CA 越界报错", any("255" in e for e in
                              mtw.addr_field_errors(8, {"ca": "300"})),
          mtw.addr_field_errors(8, {"ca": "300"}))
    check("非 HEX 写法报错", any("十六进制" in e or "HEX" in e for e in
                              mtw.addr_field_errors(6, {"addr": "ZZ"})))


# ── [2] 六协议真帧 oracle ──────────────────────────────────────────────────

def oracle(title, frame, index, values, span, expect_addr, extra_changed=frozenset()):
    """替换后：① 帧长不变 ② 地址 span == 期望 ③ 校验器 0 fail ④ 只有地址/校验字节变。"""
    new_hex, notes, error = mtw.replace_frame_address(hex_text(frame), index, values)
    if error:
        check(f"{title}：替换成功", False, error)
        return
    new = unhex(new_hex)
    check(f"{title}：输出是空格分隔 HEX（可反解）", new_hex.count(" ") == len(new) - 1, new_hex[:30])
    check(f"{title}：帧长不变", len(new) == len(frame), f"{len(frame)} → {len(new)}")
    check(f"{title}：地址域写入期望字节", new[span[0]:span[1]] == expect_addr,
          new[span[0]:span[1]].hex(" "))
    changed = {i for i in range(len(frame)) if frame[i] != new[i]}
    allowed = set(range(*span)) | set(extra_changed)
    check(f"{title}：只有地址域/校验字节变化", changed <= allowed,
          f"changed={sorted(changed)} allowed={sorted(allowed)}")
    check(f"{title}：**该协议校验器 0 fail**", v_fail(index, new) == 0, f"fail={v_fail(index, new)}")
    check(f"{title}：notes 非空（地址/校验旧→新）", bool(notes), notes)


def test_oracle_frames():
    section("[2] replace_frame_address 六协议真帧 oracle")

    oracle("南网(0)", SOUTH_ADDR, 0, {"dst": "000000000010"}, (10, 16),
           bytes.fromhex("100000000000"), {len(SOUTH_ADDR) - 2})
    oracle("645(6)", DLT645, 6, {"addr": "000000000033"}, (1, 7),
           bytes.fromhex("330000000000"), {len(DLT645) - 2})
    oracle("698.45(8)", T698, 8, {"sa": "0000000099", "ca": "7"}, (5, 11),
           bytes.fromhex("9900000000") + b"\x07",
           set(range(4, 5)) | {11, 12, len(T698) - 3, len(T698) - 2})
    oracle("依瓦645(13)", YW645, 13, {"addr": "450000000099"}, (1, 7),
           bytes.fromhex("450000000099"), {len(YW645) - 2})
    oracle("南网上行(14)", CSG_UPLINK, 14, {"a2": "1234567"}, (7, 14),
           bytes.fromhex("000000") + (1234567).to_bytes(3, "little") + b"\x00",
           {len(CSG_UPLINK) - 2})

    frame = gdw_frame()
    alen = 12 + 6 * ((frame[4] >> 4) & 0x0F)
    oracle("国网(7)", frame, 7, {"dst": "000000000010"}, (10, 10 + alen),
           bytes.fromhex("010000000000") + bytes.fromhex("100000000000"),
           {len(frame) - 2})

    # 源 + 目的同时替换（两个字段一起填）
    new_hex, _notes, error = mtw.replace_frame_address(
        hex_text(SOUTH_ADDR), 0, {"src": "000000000009", "dst": "000000000010"})
    check("南网：源+目的同时替换成功", not error, error)
    if not error:
        new = unhex(new_hex)
        check("南网：源地址已替换", new[4:10] == bytes.fromhex("090000000000"), new[4:10].hex(" "))
        check("南网：目的地址已替换", new[10:16] == bytes.fromhex("100000000000"), new[10:16].hex(" "))
        check("南网：该校验器 0 fail", v_fail(0, new) == 0)

    # 南网无地址域：明确报错，不得静默返回原帧
    _new, _notes, error = mtw.replace_frame_address(
        hex_text(SOUTH_NOADDR), 0, {"src": "000000000009"})
    check("南网 D5=0：报「不含地址域」", "不含地址域" in error, error)


def test_fe_prefix():
    section("[2b] 前导 FEH（只对协议 6/8 剥离并原样恢复）")

    for index, frame, values, label in (
        (8, T698, {"sa": "0000000099"}, "698.45"),
        (6, DLT645, {"addr": "000000000033"}, "645"),
    ):
        new_hex, notes, error = mtw.replace_frame_address(hex_text(FE4 + frame), index, values)
        check(f"{label}：带前导 FE 也能替换", not error, error)
        if error:
            continue
        new = unhex(new_hex)
        check(f"{label}：前导 FE 原样保留", new[:4] == FE4, new[:4].hex(" "))
        check(f"{label}：前导之后就是 68H", new[4:5] == b"\x68", new[4:5].hex(" "))
        check(f"{label}：带前导的新帧校验器 0 fail", v_fail(index, new) == 0)
        check(f"{label}：notes 非空", bool(notes), notes)

    # 其余协议规范里没有前导码 ⇒ 带 FE 就报错（不得被「救活」）
    for index, frame, values, label in (
        (0, SOUTH_ADDR, {"dst": "000000000010"}, "南网(0)"),
        (7, gdw_frame(), {"dst": "000000000010"}, "国网(7)"),
    ):
        new_hex, _notes, error = mtw.replace_frame_address(
            hex_text(FE4 + frame), index, values)
        check(f"{label}：带前导 FE 拒绝替换（规范无前导码）", bool(error), error)
        check(f"{label}：拒绝时 new_hex 为空（调用方据此不改结果）", new_hex == "", new_hex[:20])


def test_errors():
    section("[2c] 错误矩阵")

    _new, _notes, error = mtw.replace_frame_address("68 12 0G", 6, {"addr": "000000000033"})
    check("非法 HEX：报具体原因", "非 HEX" in error, error)

    _new, _notes, error = mtw.replace_frame_address("", 6, {"addr": "000000000033"})
    check("空报文：报错", bool(error), error)

    _new, _notes, error = mtw.replace_frame_address(hex_text(DLT645), None, {"addr": "x"})
    check("未选协议：报「未选择协议」", "未选择协议" in error, error)

    _new, _notes, error = mtw.replace_frame_address(hex_text(DLT645), 9, {"addr": "x"})
    check("协议9 不支持：给可读原因（不静默）", "暂不支持" in error, error)

    _new, _notes, error = mtw.replace_frame_address(hex_text(DLT645), 6, {"addr": "00 00"})
    check("645 地址长度不符：报错", "6 字节" in error, error)

    _new, _notes, error = mtw.replace_frame_address(hex_text(DLT645), 6, {})
    check("645 未填地址：报错", bool(error), error)

    # 错协议（用 645 帧按南网替换）→ 结构自证失败，不得「洗」成看似合法的帧
    _new, _notes, error = mtw.replace_frame_address(hex_text(DLT645), 0, {"dst": "000000000010"})
    check("错协议：结构自证失败且原因可读",
          bool(error) and any(k in error for k in ("结构", "长度", "帧头", "不含地址域")), error)

    # 原帧校验被改坏 → 拒绝（先自证再改）
    broken = bytearray(DLT645)
    broken[-2] ^= 0xFF
    _new, _notes, error = mtw.replace_frame_address(hex_text(bytes(broken)), 6,
                                                   {"addr": "000000000033"})
    check("原帧校验不符：拒绝替换", "校验" in error, error)

    # bool 协议索引不算数字（防 True == 1 的误判）
    _new, _notes, error = mtw.replace_frame_address(hex_text(DLT645), True, {"addr": "000000000033"})
    check("bool 协议索引拒绝", bool(error), error)


def test_input_tolerance():
    section("[2d] 输入写法容错与等价性")

    want = mtw.replace_frame_address(hex_text(DLT645), 6, {"addr": "000000000033"})[0]
    check("空格写法产出非空结果", bool(want), want)

    for label, text in (
        ("逗号分隔", "68,00,00,00,00,00,00,68,11,04,33,33,34,33,B2,16"),
        ("分号分隔", "68;00;00;00;00;00;00;68;11;04;33;33;34;33;B2;16"),
        ("0x 前缀", "0x68 0x00 0x00 0x00 0x00 0x00 0x00 0x68 0x11 0x04 0x33 0x33 0x34 0x33 0xB2 0x16"),
        ("连续无分隔", hex_text(DLT645).replace(" ", "")),
        ("小写", "68 00 00 00 00 00 00 68 11 04 33 33 34 33 b2 16"),
    ):
        got, _notes, error = mtw.replace_frame_address(text, 6, {"addr": "000000000033"})
        check(f"{label}：与空格写法结果等价", not error and got == want, f"{error} {got[:30]}")

    # 奇数位：拒绝（不静默截断）
    _new, _notes, error = mtw.replace_frame_address("680 00000 0000068", 6, {"addr": "000000000033"})
    check("奇数位 HEX：拒绝且原因可读", "奇数" in error, error)


# ── [3] 反例自检（证明 oracle 有效）────────────────────────────────────────

def test_oracle_is_valid():
    section("[3] 反例自检")

    # 645：只改地址、不重算 CS → 校验器必红
    mutated = bytearray(DLT645)
    mutated[1:7] = bytes.fromhex("330000000000")
    check("反例：645 改地址不重算校验 → 校验器必红", v_fail(6, bytes(mutated)) > 0,
          f"fail={v_fail(6, bytes(mutated))}")
    check("对照：645 原帧校验器 0 fail", v_fail(6, DLT645) == 0)

    # 南网：只改地址、不重算 CS → 校验器必红
    south_mut = bytearray(SOUTH_ADDR)
    south_mut[10:16] = bytes.fromhex("100000000000")
    check("反例：南网改地址不重算 CS → 校验器必红", v_fail(0, bytes(south_mut)) > 0,
          f"fail={v_fail(0, bytes(south_mut))}")
    check("对照：南网原帧校验器 0 fail", v_fail(0, SOUTH_ADDR) == 0)

    # 698：改 SA 但不重算 HCS/FCS → 校验器必红
    t698_mut = bytearray(T698)
    t698_mut[6] = 0x99
    check("反例：698 改 SA 不重算 HCS/FCS → 校验器必红", v_fail(8, bytes(t698_mut)) > 0,
          f"fail={v_fail(8, bytes(t698_mut))}")
    check("对照：698 原帧校验器 0 fail", v_fail(8, T698) == 0)

    # 真实替换结果必须比反例「更合法」——同一帧、同一地址，权威算法重算后 0 fail
    fixed, _notes, error = mtw.replace_frame_address(hex_text(T698), 8, {"sa": "0000000099"})
    check("对照：698 走替换 → 0 fail 且与反例不同", not error and v_fail(8, unhex(fixed)) == 0, error)


# ── [4] offscreen GUI ────────────────────────────────────────────────────

def _addr_edit(widget, key):
    return widget._addr_edits.get(key)


def test_gui():
    section("[4] offscreen GUI")

    app = QApplication.instance() or QApplication([])
    widget = mtw.MessageToolWidget()
    widget.resize(1200, 700)
    widget.show()
    app.processEvents()

    combo_items = [widget.addr_protocol_combo.itemText(i)
                   for i in range(widget.addr_protocol_combo.count())]
    check("协议下拉与 frame_addr_fix.supported_choices 同源",
          combo_items == [label for label, _index in frame_addr_fix.supported_choices()],
          combo_items)
    check("协议下拉默认第一项（南网）", widget.addr_protocol_index() == 0,
          widget.addr_protocol_index())
    check("协议下拉按内容取宽（不整行拉满）",
          widget.addr_protocol_combo.width() < widget.width() // 2,
          f"{widget.addr_protocol_combo.width()} / {widget.width()}")
    check("协议下拉不裁字（width >= sizeHint）",
          widget.addr_protocol_combo.width() >= widget.addr_protocol_combo.sizeHint().width(),
          f"width={widget.addr_protocol_combo.width()} "
          f"sizeHint={widget.addr_protocol_combo.sizeHint().width()}")
    check("协议下拉弹出列表按最长项放宽（不被截）",
          widget.addr_protocol_combo.view().minimumWidth() > widget.addr_protocol_combo.width(),
          f"{widget.addr_protocol_combo.view().minimumWidth()}")

    # 动态字段：南网 → 源/目的；切到 645 → 表地址；切到 698 → SA/CA
    check("南网：生成源/目的两行", tuple(widget._addr_edits) == ("src", "dst"),
          tuple(widget._addr_edits))
    widget.addr_protocol_combo.setCurrentIndex(
        [i for i in range(widget.addr_protocol_combo.count())
         if widget.addr_protocol_combo.itemData(i) == 6][0])
    app.processEvents()
    check("切到 645：地址行变成 1 个（表地址）", tuple(widget._addr_edits) == ("addr",),
          tuple(widget._addr_edits))
    check("645 输入框提示来自字段声明",
          _addr_edit(widget, "addr").placeholderText() == frame_addr_fix.fields_for(6)[0].hint)
    widget.addr_protocol_combo.setCurrentIndex(
        [i for i in range(widget.addr_protocol_combo.count())
         if widget.addr_protocol_combo.itemData(i) == 8][0])
    app.processEvents()
    check("切到 698：地址行变成 SA/CA", tuple(widget._addr_edits) == ("sa", "ca"),
          tuple(widget._addr_edits))

    # 切协议保留已填值（按 key 暂存，回切回填）
    edit = _addr_edit(widget, "sa")
    edit.setText("0000000099")
    widget.addr_protocol_combo.setCurrentIndex(
        [i for i in range(widget.addr_protocol_combo.count())
         if widget.addr_protocol_combo.itemData(i) == 6][0])
    app.processEvents()
    widget.addr_protocol_combo.setCurrentIndex(
        [i for i in range(widget.addr_protocol_combo.count())
         if widget.addr_protocol_combo.itemData(i) == 8][0])
    app.processEvents()
    check("切协议再切回：已填值仍在", _addr_edit(widget, "sa").text() == "0000000099",
          _addr_edit(widget, "sa").text())

    # 提示行：地址回显 + 当前报文的替换预览
    check("提示行（698 SA）说明长度按帧内地址特征确定",
          "长度按帧内地址特征确定" in widget.lbl_addr_hint.text(),
          widget.lbl_addr_hint.text())
    check("提示行给出预览（输入框为空时无预览）", "预览" not in widget.lbl_addr_hint.text(),
          widget.lbl_addr_hint.text())

    widget.input_text.setPlainText(hex_text(T698))
    app.processEvents()
    hint = widget.lbl_addr_hint.text()
    check("填入报文后提示行出现预览", "预览：" in hint, hint)
    check("预览行给出替换后的报文（与纯逻辑同源）",
          mtw.replace_frame_address(hex_text(T698), 8, {"sa": "0000000099"})[0] in hint, hint)

    # 定长地址字段：提示行回显「写入 N 字节」
    widget.addr_protocol_combo.setCurrentIndex(
        [i for i in range(widget.addr_protocol_combo.count())
         if widget.addr_protocol_combo.itemData(i) == 6][0])
    app.processEvents()
    _addr_edit(widget, "addr").setText("000000000033")
    app.processEvents()
    check("提示行回显「将写入 6 字节」",
          "6 字节" in widget.lbl_addr_hint.text() and "字节" in widget.lbl_addr_hint.text(),
          widget.lbl_addr_hint.text())
    check("645 提示行含写在线字节（低字节在前 33 00…）",
          "330000000000" in widget.lbl_addr_hint.text().replace(" ", ""),
          widget.lbl_addr_hint.text())
    widget.addr_protocol_combo.setCurrentIndex(
        [i for i in range(widget.addr_protocol_combo.count())
         if widget.addr_protocol_combo.itemData(i) == 8][0])
    app.processEvents()

    # 真实点击「替换地址」
    btn = next((b for b in widget.findChildren(QPushButton) if b.text() == "替换地址"), None)
    check("「替换地址」按钮存在（无死按钮）", btn is not None)
    check("按钮不裁字（width >= sizeHint）", btn.width() >= btn.sizeHint().width(),
          f"width={btn.width()} sizeHint={btn.sizeHint().width()}")
    check("按钮未写死上限", btn.maximumWidth() > 100000, btn.maximumWidth())
    check("结果行真实绘制", widget.addr_result_edit.visibleRegion().boundingRect().width() > 100,
          widget.addr_result_edit.visibleRegion().boundingRect())

    MSGS.clear()
    btn.click()
    app.processEvents()
    expect = mtw.replace_frame_address(hex_text(T698), 8, {"sa": "0000000099"})[0]
    check("点击后结果行 = 替换后报文", widget.addr_result_edit.text() == expect,
          widget.addr_result_edit.text())
    check("结果帧校验器 0 fail", v_fail(8, unhex(widget.addr_result_edit.text())) == 0)
    out = widget.output_text.toPlainText()
    check("输出含协议短名", "698" in out or "698.45" in out, out)
    check("输出含说明（地址旧→新）", "地址域" in out, out)
    check("成功路径无弹窗", not MSGS, f"{MSGS}")

    # 复制结果 → 剪贴板
    copy_btn = next((b for b in widget.findChildren(QPushButton) if b.text() == "复制结果"), None)
    check("「复制结果」按钮存在", copy_btn is not None)
    if copy_btn is not None:
        app.clipboard().clear()
        copy_btn.click()
        check("剪贴板拿到结果报文", app.clipboard().text() == expect, app.clipboard().text())

    # 结果 → 输入（迭代编辑）
    widget.input_text.clear()
    to_input = next((b for b in widget.findChildren(QPushButton) if b.text() == "结果→输入"), None)
    check("「结果→输入」按钮存在", to_input is not None)
    if to_input is not None:
        to_input.click()
        check("结果回填到输入框", widget.input_text.toPlainText() == expect,
              widget.input_text.toPlainText()[:30])

    # 失败路径：结果行**不得**被改写（否则用户会以为已替换成功）
    widget.input_text.setPlainText(hex_text(T698))
    app.processEvents()
    widget.addr_protocol_combo.setCurrentIndex(
        [i for i in range(widget.addr_protocol_combo.count())
         if widget.addr_protocol_combo.itemData(i) == 8][0])
    app.processEvents()
    _addr_edit(widget, "sa").setText("0000000099")
    widget.input_text.setPlainText(hex_text(DLT645))          # 645 帧按 698 替换 → 自证失败
    app.processEvents()
    before = widget.addr_result_edit.text()
    MSGS.clear()
    btn.click()
    app.processEvents()
    check("自证失败：弹警告", any(k == "warning" for k, _m in MSGS), f"{MSGS}")
    check("自证失败：结果行保持原值", widget.addr_result_edit.text() == before,
          widget.addr_result_edit.text()[:30])
    check("自证失败：输出记录可读原因", "失败" in widget.output_text.toPlainText(),
          widget.output_text.toPlainText())

    # 未填地址 → 提示（不做无意义的替换）
    MSGS.clear()
    _addr_edit(widget, "sa").setText("")
    _addr_edit(widget, "ca").setText("")
    widget.input_text.setPlainText(hex_text(T698))
    app.processEvents()
    btn.click()
    check("未填地址：提示先填地址", any(k == "information" and "地址" in m for k, m in MSGS), f"{MSGS}")

    # 非法 HEX 输入
    MSGS.clear()
    _addr_edit(widget, "sa").setText("0000000099")
    widget.input_text.setPlainText("68 12 0G")
    app.processEvents()
    check("提示行刷新不弹窗（预览失败只写在提示行里）", not MSGS, f"{MSGS}")
    check("提示行写出预览失败原因", "非 HEX" in widget.lbl_addr_hint.text(),
          widget.lbl_addr_hint.text())
    btn.click()
    check("非法 HEX：弹警告", any(k == "warning" for k, _m in MSGS), f"{MSGS}")

    # 地址写法非法 → 在按钮处拦住（提示行也可读）
    MSGS.clear()
    _addr_edit(widget, "ca").setText("300")
    widget.input_text.setPlainText(hex_text(T698))
    app.processEvents()
    btn.click()
    check("地址越界：弹警告「地址无效」", any(k == "warning" and "255" in m for k, m in MSGS),
          f"{MSGS}")

    # 清空所有输入时提示行回到引导文案（不残留旧预览）
    MSGS.clear()
    _addr_edit(widget, "ca").setText("")
    _addr_edit(widget, "sa").setText("")
    app.processEvents()
    check("未填地址时提示行回到引导文案", "填写地址后" in widget.lbl_addr_hint.text(),
          widget.lbl_addr_hint.text())

    widget.deleteLater()
    app.processEvents()


def main():
    test_constants()
    test_oracle_frames()
    test_fe_prefix()
    test_errors()
    test_input_tolerance()
    test_oracle_is_valid()
    test_gui()
    print(f"\nPASS={PASS} FAIL={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
