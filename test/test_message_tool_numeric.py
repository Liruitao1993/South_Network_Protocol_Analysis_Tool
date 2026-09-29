"""报文工具「数值 ⟷ HEX（大端/小端）」回归测试（1.23.60 起；1.23.62 补 HEX→数值方向）。

覆盖：
  [1] 类型表：与 dl_t698_45_axdr 的已实现解码器一一对应（无哑条目、无遗漏）
  [2] 往返 oracle：编码结果喂回 698.45 A-XDR 解码器，解析值/原始值/消耗字节须一致
  [3] 文档锚点：698 附录 H.1.1 的 07 E0=2016 / 00 B4=180 / 00 A4=164，
      以及 A-XDR 大端判据 FF FF 9E D0 = -24880
  [4] 边界值（各类型 min/max）与「小端 = 大端逆序」不变式
  [5] 错误路径：格式错误 / 超范围 / bool 非 0-1 / NaN / inf 均给中文原因且不改输出
  [6] HEX→数值：与编码器**严格互逆**（全类型 × 边界值）、文档锚点、连续/带分隔写法等价
  [7] HEX→数值错误路径：空 / 非 HEX / 奇数位 / 字节数与类型不符，均不静默截断
  [8] offscreen GUI：下拉项与表同源、两个方向按钮真实点击接线、回车接线、
      空输入提示、错误弹窗不落输出、布局与按钮不裁字

运行: QT_QPA_PLATFORM=offscreen python -u test/test_message_tool_numeric.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
import struct  # noqa: E402
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

# 沙箱：MessageToolWidget 本身不落盘，但同进程内其他组件可能写 app_paths 数据文件
_config_sandbox.install()

from dl_t698_45_axdr import AXDRCoder, TAG_TYPE  # noqa: E402

import message_tool_widget as mtw  # noqa: E402

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


# 下拉表里的 12 个基础类型（DL/T 790.6-2010 / 698.45 A-XDR 中「可用十进制表述」的那些）
EXPECTED_AXDR_NAMES = [
    "bool", "integer", "unsigned", "enum",
    "long", "long-unsigned",
    "double-long", "double-long-unsigned",
    "long64", "long64-unsigned",
    "float32", "float64",
]

# 类型名 -> (字节数, kind)，与 message_tool_widget.NUMERIC_TYPES 独立对照
EXPECTED_WIDTHS = {
    "bool": (1, "bool"),
    "integer": (1, "int"),
    "unsigned": (1, "uint"),
    "enum": (1, "uint"),
    "long": (2, "int"),
    "long-unsigned": (2, "uint"),
    "double-long": (4, "int"),
    "double-long-unsigned": (4, "uint"),
    "long64": (8, "int"),
    "long64-unsigned": (8, "uint"),
    "float32": (4, "float"),
    "float64": (8, "float"),
}


def type_key(label):
    """下拉文案 'long-unsigned（无符号长整型，2字节，0~65535）' -> 'long-unsigned'。"""
    return label.split("（")[0]


def decode_round_trip(be_hex, tag):
    data = bytes([tag]) + bytes.fromhex(be_hex.replace(" ", ""))
    return AXDRCoder().decode(data, 0)


def main():
    print("== [1] 类型表与 698.45 A-XDR 解码器一致性 ==")
    keys = [type_key(label) for label, _n, _k in mtw.NUMERIC_TYPES]
    check("类型数与 12 个基础类型一致", len(keys) == 12, f"实际 {len(keys)}: {keys}")
    check("类型名集合与预期一致", keys == EXPECTED_AXDR_NAMES, f"{keys}")
    check(
        "下拉文案不含重名（NUMERIC_TYPE_SPECS 无覆盖）",
        len(mtw.NUMERIC_TYPE_SPECS) == len(keys),
        f"{len(mtw.NUMERIC_TYPE_SPECS)} vs {len(keys)}",
    )
    for label, nbytes, kind in mtw.NUMERIC_TYPES:
        key = type_key(label)
        want = EXPECTED_WIDTHS.get(key)
        check(f"{key} 宽度/符号性", (nbytes, kind) == want, f"实际 {(nbytes, kind)} 期望 {want}")
        # 每个类型都必须在 A-XDR 表里有 tag、且解码器已实现（否则是哑条目）
        check(f"{key} 在 AXDR_TAG 中存在", key in TAG_TYPE, f"{key} 不在 {sorted(TAG_TYPE)}")
        check(
            f"{key} 解码器已实现",
            hasattr(AXDRCoder, "_decode_" + key.replace("-", "_")),
            f"缺少 _decode_{key.replace('-', '_')}",
        )
        # NUMERIC_TYPE_SPECS 必须能按下拉文案取到同一条
        check(
            f"{key} 可按下拉文案反查",
            mtw.NUMERIC_TYPE_SPECS.get(label) == (nbytes, kind),
            f"{mtw.NUMERIC_TYPE_SPECS.get(label)}",
        )

    print("== [2] 编码 -> 698.45 A-XDR 解码 往返 oracle ==")
    probes = {
        "bool": ["0", "1"],
        "integer": ["-128", "127", "0"],
        "unsigned": ["0", "255"],
        "enum": ["0", "255"],
        "long": ["-32768", "32767"],
        "long-unsigned": ["0", "65535"],
        "double-long": ["-2147483648", "2147483647"],
        "double-long-unsigned": ["0", "4294967295"],
        "long64": ["-9223372036854775808", "9223372036854775807"],
        "long64-unsigned": ["0", "18446744073709551615"],
        "float32": ["1.5", "-0.25", "0"],
        "float64": ["1.5", "-0.25", "0"],
    }
    for label, nbytes, kind in mtw.NUMERIC_TYPES:
        key = type_key(label)
        tag = TAG_TYPE[key]
        for text in probes[key]:
            be_hex, le_hex, normalized = mtw.encode_numeric_value(text, nbytes, kind)
            be_bytes = bytes.fromhex(be_hex.replace(" ", ""))
            check(f"{key} 大端字节数 = {nbytes}", len(be_bytes) == nbytes, f"{be_hex}")
            check(
                f"{key} 小端 = 大端逆序",
                le_hex.split(" ") == [f"{b:02X}" for b in reversed(be_bytes)],
                f"{be_hex} / {le_hex}",
            )
            res, consumed = decode_round_trip(be_hex, tag)
            check(
                f"{key} 解码消耗 {1 + nbytes} 字节",
                consumed == 1 + nbytes,
                f"consumed={consumed}",
            )
            if kind == "bool":
                check(
                    f"{key}({text}) 解码为布尔 {text == '1'}",
                    res["解析值"] is (text == "1"),
                    f"{res['解析值']!r}",
                )
            elif kind == "float":
                check(
                    f"{key}({text}) 解码往返一致",
                    res["解析值"] == float(text),
                    f"{res['解析值']!r}",
                )
            else:
                check(
                    f"{key}({text}) 解码往返一致",
                    res["解析值"] == int(text),
                    f"{res['解析值']!r}",
                )
            check(
                f"{key}({text}) 原始值 = 大端 HEX",
                res["原始值"].upper().replace("0X", "") == be_bytes.hex().upper(),
                f"{res['原始值']} vs {be_bytes.hex().upper()}",
            )
            norm_ok = (
                float(normalized) == float(text) if kind == "float" else normalized == text
            )
            check(
                f"{key}({text}) 规范化十进制回读一致",
                norm_ok,
                f"{normalized!r}",
            )

    print("== [3] 协议文档锚点 ==")
    for value, want_be in (("2016", "07 E0"), ("180", "00 B4"), ("164", "00 A4")):
        be_hex, _le, _norm = mtw.encode_numeric_value(value, 2, "uint")
        check(f"long-unsigned {value} -> {want_be}", be_hex == want_be, f"{be_hex}")
    be_hex, le_hex, _n = mtw.encode_numeric_value("-24880", 4, "int")
    check("double-long -24880 大端 = FF FF 9E D0", be_hex == "FF FF 9E D0", f"{be_hex}")
    check("double-long -24880 小端 = D0 9E FF FF", le_hex == "D0 9E FF FF", f"{le_hex}")
    be_hex, _le, _n = mtw.encode_numeric_value("-1", 4, "int")
    check("double-long -1 大端 = FF FF FF FF", be_hex == "FF FF FF FF", f"{be_hex}")

    print("== [4] 边界值 ±1 ==")
    bounds = [
        ("integer", 1, "int", -128, 127),
        ("unsigned", 1, "uint", 0, 255),
        ("long", 2, "int", -32768, 32767),
        ("long-unsigned", 2, "uint", 0, 65535),
        ("double-long", 4, "int", -2147483648, 2147483647),
        ("double-long-unsigned", 4, "uint", 0, 4294967295),
        ("long64", 8, "int", -9223372036854775808, 9223372036854775807),
        ("long64-unsigned", 8, "uint", 0, 18446744073709551615),
    ]
    for name, nbytes, kind, lo, hi in bounds:
        for value, should_pass in ((lo, True), (hi, True), (lo - 1, False), (hi + 1, False)):
            try:
                mtw.encode_numeric_value(str(value), nbytes, kind)
                ok = should_pass
                why = f"{name}={value} 未报错"
            except ValueError as exc:
                ok = not should_pass and "超出" in str(exc)
                why = f"{name}={value} -> {exc}"
            check(f"{name} 边界 {value}", ok, why)

    print("== [5] 错误路径（中文原因） ==")
    err_cases = [
        ("abc", 4, "int", "不是合法的十进制整数"),
        ("12.5", 2, "uint", "不是合法的十进制整数"),
        ("", 4, "int", "请输入十进制数值"),
        ("2", 1, "bool", "bool 只能取"),
        ("-1", 1, "bool", "bool 只能取"),
        ("abc", 4, "float", "不是合法的十进制浮点数"),
        ("nan", 4, "float", "不支持 NaN"),
        ("inf", 8, "float", "不支持正负无穷"),
        ("1e40", 4, "float", "超出 float32 表示范围"),
    ]
    for text, nbytes, kind, want in err_cases:
        try:
            mtw.encode_numeric_value(text, nbytes, kind)
            check(f"错误路径 {kind}({text!r}) 应报错", False, "未抛 ValueError")
        except ValueError as exc:
            check(f"错误路径 {kind}({text!r}) 原因可读", want in str(exc), f"实际: {exc}")
    # float64 表示范围内的大值不报错（反例：判据不能过严）
    be_hex, _le, _n = mtw.encode_numeric_value("1e40", 8, "float")
    check(
        "float64 1e40 合法且等于 struct 大端编码",
        bytes.fromhex(be_hex.replace(" ", "")) == struct.pack(">d", 1e40),
        f"{be_hex}",
    )

    print("== [6] HEX→数值：与编码器严格互逆 ==")
    for label, nbytes, kind in mtw.NUMERIC_TYPES:
        key = type_key(label)
        for text in probes[key]:
            be_hex, le_hex, normalized = mtw.encode_numeric_value(text, nbytes, kind)
            want = normalized.split("（")[0]
            be_v, le_v, hx = mtw.decode_numeric_value(be_hex, nbytes, kind)
            # 编码的大端 HEX → 解码的「大端列」必须回到原值
            check(f"{key}({text}) 大端 HEX 解码：大端列 = 原值",
                  be_v.split("（")[0] == want, f"{be_v!r}")
            check(f"{key}({text}) 回显规范化 HEX = 编码大端", hx == be_hex, f"{hx} vs {be_hex}")
            # 编码的小端 HEX → 解码的「小端列」必须回到原值
            le_v2_be, le_v2_le, _hx2 = mtw.decode_numeric_value(le_hex, nbytes, kind)
            check(f"{key}({text}) 小端 HEX 解码：小端列 = 原值",
                  le_v2_le.split("（")[0] == want, f"{le_v2_le!r}")
            # 两端对称：大端 HEX 的「小端列」== 小端 HEX 的「大端列」（多字节时两者都是换序值）
            check(f"{key}({text}) 两端结果互换对称",
                  le_v2_be == le_v if nbytes > 1 else be_v == le_v,
                  f"{le_v2_be} vs {le_v}")
            # 连续无分隔写法（如 FFFF9ED0）必须与带空格写法等价
            check(f"{key}({text}) 连续写法等价",
                  mtw.decode_numeric_value(be_hex.replace(" ", ""), nbytes, kind)
                  == (be_v, le_v, hx))
            # 错误字节数必须报错，不静默截断
            try:
                mtw.decode_numeric_value(be_hex, nbytes + 1, kind)
                check(f"{key}({text}) 字节数不符应报错", False, "未抛 ValueError")
            except ValueError as exc:
                check(f"{key}({text}) 字节数不符报错可读", "需要" in str(exc), f"实际: {exc}")

    # 文档锚点：A-XDR 大端判据（dl_t698_45_axdr.py 文件头记录的历史修复实例）
    be_v, le_v, hx = mtw.decode_numeric_value("FF FF 9E D0", 4, "int")
    check("double-long FF FF 9E D0 大端 = -24880（A-XDR 正确值）", be_v == "-24880", be_v)
    check("double-long FF FF 9E D0 小端 = -794886145（历史误读值）", le_v == "-794886145", le_v)
    check("回显 HEX 规范化", hx == "FF FF 9E D0", hx)
    check("long-unsigned 07 E0 大端 = 2016（附录 H.1.1 年份）",
          mtw.decode_numeric_value("07E0", 2, "uint")[0] == "2016",
          mtw.decode_numeric_value("07E0", 2, "uint")[0])
    check("bool 01 → 1（true）", mtw.decode_numeric_value("01", 1, "bool")[0] == "1（true）")
    check("bool 00 → 0（false）", mtw.decode_numeric_value("00", 1, "bool")[0] == "0（false）")
    check("分隔符容错（逗号/分号/冒号/0x 前缀）",
          mtw.decode_numeric_value("0xFF,FF;9E:D0", 4, "int")[0] == "-24880")
    check("float32 3F C0 00 00 大端 = 1.5",
          mtw.decode_numeric_value("3F C0 00 00", 4, "float")[0] == "1.5",
          mtw.decode_numeric_value("3F C0 00 00", 4, "float")[0])

    print("== [7] HEX→数值错误路径（不静默截断） ==")
    hex_errs = [
        ("", 4, "int", "请输入 HEX 值"),
        ("   ", 4, "int", "请输入 HEX 值"),
        ("0G", 1, "int", "非 HEX 字符"),
        ("FFF", 2, "int", "奇数"),
        ("FF FF", 4, "int", "需要 4 字节，实际 2 字节"),
        ("FF FF FF FF FF", 4, "int", "需要 4 字节，实际 5 字节"),
        ("07 E0", 1, "uint", "需要 1 字节，实际 2 字节"),
    ]
    for text, nbytes, kind, want in hex_errs:
        try:
            mtw.decode_numeric_value(text, nbytes, kind)
            check(f"HEX 错误路径 {kind}({text!r}) 应报错", False, "未抛 ValueError")
        except ValueError as exc:
            check(f"HEX 错误路径 {kind}({text!r}) 原因可读", want in str(exc), f"实际: {exc}")
    # 反例：字节数正确时不得报错（判据不能过严）
    check("反例：4 字节类型给 4 字节不报错",
          mtw.decode_numeric_value("00 00 04 D2", 4, "uint")[0] == "1234")

    print("== [8] offscreen GUI ==")
    app = QApplication.instance() or QApplication([])
    widget = mtw.MessageToolWidget()
    check("窗口构造成功", widget is not None)
    # 必须在 show() 之后量尺寸：headless 下未显示控件的 width() 是默认 640（陷阱 63 的假绿来源）
    widget.resize(1200, 700)
    widget.show()
    app.processEvents()
    combo_vis = widget.num_type_combo.visibleRegion().boundingRect()
    check(
        "类型下拉真实绘制（visibleRegion 非空，非「有控件没画出来」）",
        combo_vis.height() > 10 and combo_vis.width() > 100,
        f"{combo_vis}",
    )
    edit_vis = widget.num_value_edit.visibleRegion().boundingRect()
    check("数值输入框真实绘制", edit_vis.height() > 10 and edit_vis.width() > 100, f"{edit_vis}")
    combo_items = [widget.num_type_combo.itemText(i) for i in range(widget.num_type_combo.count())]
    check(
        "下拉项与 NUMERIC_TYPES 同源",
        combo_items == [label for label, _n, _k in mtw.NUMERIC_TYPES],
        f"{combo_items}",
    )
    check("下拉项均能反查到规格", all(widget.num_type_combo.itemText(i) in mtw.NUMERIC_TYPE_SPECS
                                    for i in range(widget.num_type_combo.count())))
    btn = next((b for b in widget.findChildren(QPushButton) if b.text() == "数值 → HEX"), None)
    check("「数值 → HEX」按钮存在（无死按钮）", btn is not None)
    # 陷阱 63：写死宽度会裁字；判据是「实得宽度 >= sizeHint」且未设上限
    check(
        "按钮宽度不裁字（width >= sizeHint）",
        btn.width() >= btn.sizeHint().width(),
        f"width={btn.width()} sizeHint={btn.sizeHint().width()}",
    )
    check("按钮未写死上限（可随字号增长）", btn.maximumWidth() > 100000, f"{btn.maximumWidth()}")

    # 正常路径：真实点击
    widget.num_type_combo.setCurrentText("double-long-unsigned（无符号双长整型，4字节）")
    widget.num_value_edit.setText("1234")
    btn.click()
    out = widget.output_text.toPlainText()
    check("输出含大端 HEX", "大端(高字节在前): 00 00 04 D2" in out, out)
    check("输出含小端 HEX", "小端(低字节在前): D2 04 00 00" in out, out)
    check("输出含类型与字节数", "4" in out and "double-long-unsigned" in out, out)
    check("正常路径无弹窗", not MSGS, f"{MSGS}")

    # returnPressed 接线
    widget.num_type_combo.setCurrentText("unsigned（无符号整型，1字节，0~255）")
    widget.num_value_edit.setText("7")
    widget.num_value_edit.returnPressed.emit()
    check("回车触发编码", "大端(高字节在前): 07" in widget.output_text.toPlainText(),
          widget.output_text.toPlainText())

    # 错误路径：弹窗且不改动已有输出
    before = widget.output_text.toPlainText()
    widget.num_value_edit.setText("999")
    btn.click()
    check("超出范围弹警告", any(k == "warning" and "超出" in m for k, m in MSGS), f"{MSGS}")
    check("错误路径不覆盖输出", widget.output_text.toPlainText() == before)

    MSGS.clear()
    widget.num_value_edit.setText("")
    btn.click()
    check("空输入提示", any(k == "information" and "请输入十进制数值" in m for k, m in MSGS), f"{MSGS}")

    MSGS.clear()
    widget.num_value_edit.setText("abc")
    btn.click()
    check("非数字弹警告", any(k == "warning" and "不是合法的十进制整数" in m for k, m in MSGS), f"{MSGS}")

    # ---- HEX → 数值（对称方向）----
    HEX_VIS = widget.num_hex_edit.visibleRegion().boundingRect()
    check("HEX 输入框真实绘制", HEX_VIS.height() > 10 and HEX_VIS.width() > 100, f"{HEX_VIS}")
    btn_hex = next((b for b in widget.findChildren(QPushButton) if b.text() == "HEX → 数值"), None)
    check("「HEX → 数值」按钮存在（无死按钮）", btn_hex is not None)
    check(
        "HEX→数值 按钮不裁字（width >= sizeHint）",
        btn_hex.width() >= btn_hex.sizeHint().width(),
        f"width={btn_hex.width()} sizeHint={btn_hex.sizeHint().width()}",
    )
    check("HEX→数值 按钮未写死上限", btn_hex.maximumWidth() > 100000, f"{btn_hex.maximumWidth()}")

    MSGS.clear()
    widget.num_type_combo.setCurrentText("double-long（双长整型，4字节，有符号）")
    widget.num_hex_edit.setText("FF FF 9E D0")
    btn_hex.click()
    out = widget.output_text.toPlainText()
    check("HEX→数值：大端解析 = -24880", "大端解析(高字节在前): -24880" in out, out)
    check("HEX→数值：小端解析 = -794886145", "小端解析(低字节在前): -794886145" in out, out)
    check("HEX→数值：回显规范化 HEX", "HEX 值: FF FF 9E D0" in out, out)
    check("HEX→数值：正常路径无弹窗", not MSGS, f"{MSGS}")

    # 回车接线（连续无分隔写法）
    widget.num_type_combo.setCurrentText("long-unsigned（无符号长整型，2字节，0~65535）")
    widget.num_hex_edit.setText("07E0")
    widget.num_hex_edit.returnPressed.emit()
    check("HEX 回车触发解码", "大端解析(高字节在前): 2016" in widget.output_text.toPlainText(),
          widget.output_text.toPlainText())

    MSGS.clear()
    widget.num_type_combo.setCurrentText("double-long（双长整型，4字节，有符号）")
    before = widget.output_text.toPlainText()
    widget.num_hex_edit.setText("FF FF")
    btn_hex.click()
    check("字节数不符弹警告且提示需要几字节",
          any(k == "warning" and "需要 4 字节" in m for k, m in MSGS), f"{MSGS}")
    check("HEX 错误路径不覆盖输出", widget.output_text.toPlainText() == before)

    MSGS.clear()
    widget.num_hex_edit.setText("")
    btn_hex.click()
    check("HEX 空输入提示", any(k == "information" and "请输入 HEX 值" in m for k, m in MSGS), f"{MSGS}")

    MSGS.clear()
    widget.num_hex_edit.setText("FFF")
    btn_hex.click()
    check("HEX 奇数位弹警告", any(k == "warning" and "奇数" in m for k, m in MSGS), f"{MSGS}")

    widget.deleteLater()
    app.processEvents()

    print(f"\nPASS={PASS} FAIL={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
