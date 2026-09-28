"""串口工具「按协议分帧 + 协议字段」纯逻辑测试（无 GUI）。

覆盖：
  [1] declared_frame_len：未指定协议时的启发式（三种 68 结构 + 反例）
  [2] frame_length_for：按协议策略分帧（5 策略 × 正常 / 越界 / 自证失败）
  [3] hdlc_frame_len：7EH 定界（连续标志位不产空帧 / 未收全 / 噪声 / 超长）
  [4] format_parse_rows：日志文字格式 / 空值跳过 / 截断
  [5] coerce_protocol：协议字段归一化反例
  [6] normalize_command：协议字段（缺键 / 合法 / 越界 / 字符串 / bool）
  [7] merge_params：parse_enabled / parse_max_lines 钳制
  [8] 协议元数据辅助（protocol_options / protocol_short_name）
  [9] 反例自检（严格策略确实比启发式更严）

运行: python -u test/test_serial_proto_frame.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

import serial_tool_widget as stw  # noqa: E402

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


# ── 构造帧 ───────────────────────────────────────────────────────────

# 南网/国网：68 + L(2B 小端) + … + 16H，L = 整帧字节数（与实测 208 字节报文同形）
F68 = b"\x68\xD0\x00" + bytes(range(256))[:204] + b"\x16"          # 208 字节
# 645：68 + 地址(6B) + 68 + 控制码 + 数据长度(1B@9) + … + 16H，整帧 = L + 12
F645 = bytes.fromhex("6812345678901268110433333333AA16")            # 16 字节
# 698.45：68 + L(2B 小端) + C(1B) + … + FCS + 16H，**无第二个 68H**，整帧 = L + 2
# （DL/T 698.45-2017 6.2.2 a：L 是不含起始/结束字符的数据长度；现场实测帧）
F698 = bytes.fromhex("681F00C32602313104000090017F8D850109200402010105FFFF9ED000006D1716")  # 33 字节
# DLMS Wrapper：版本 0001 + 源端口(2B) + 目的端口(2B) + 长度(2B 大端@6) + APDU
FWRAP = bytes.fromhex("000100000000000A") + bytes(10)              # 18 字节
# HDLC：7EH + 地址 + 控制 + 载荷 + FCS(2) + 7EH
FHDLC = b"\x7E\x10\x11\x12\x13\x7E"                                # 6 字节


def main():
    print("=" * 64)
    print("串口工具（按协议分帧 + 协议字段，纯逻辑）")
    print("=" * 64)

    section("[1] declared_frame_len：未指定协议时的启发式")
    check("国网/南网 208 字节帧 → 208", stw.declared_frame_len(F68) == 208,
          str(stw.declared_frame_len(F68)))
    check("645 帧 → 16（L + 12）", stw.declared_frame_len(F645) == 16,
          str(stw.declared_frame_len(F645)))
    check("698.45 帧 → 33（L + 2）", stw.declared_frame_len(F698) == 33,
          str(stw.declared_frame_len(F698)))
    check("非 68H 开头 → 0", stw.declared_frame_len(b"\x01\x02" + bytes(10)) == 0)
    check("不足 8 字节 → 0（分不清三种结构）",
          stw.declared_frame_len(b"\x68\x11\x00\x68") == 0)
    check("长度域越界（> 上限）→ 0",
          stw.declared_frame_len(b"\x68\xFF\xFF" + bytes(20)) == 0)
    check("类静态方法委托同一实现",
          stw.SerialToolWidget._declared_frame_len(F68) == 208)

    section("[2] frame_length_for：按协议策略分帧")
    check("0/7 ft12_68 → 208",
          stw.frame_length_for("ft12_68", F68) == 208,
          str(stw.frame_length_for("ft12_68", F68)))
    check("6 dlt645 → 16",
          stw.frame_length_for("dlt645", F645) == 16,
          str(stw.frame_length_for("dlt645", F645)))
    check("8 dlt698_45 → 33（L + 2）",
          stw.frame_length_for("dlt698_45", F698) == 33,
          str(stw.frame_length_for("dlt698_45", F698)))
    check("4 dlms_wrapper → 18（8 + 长度域 10）",
          stw.frame_length_for("dlms_wrapper", FWRAP) == 18,
          str(stw.frame_length_for("dlms_wrapper", FWRAP)))
    check("2/3 hdlc_7e 委托 hdlc_frame_len → 6",
          stw.frame_length_for("hdlc_7e", FHDLC) == 6,
          str(stw.frame_length_for("hdlc_7e", FHDLC)))

    # 自证失败 / 不匹配：一律 0（交回既有路径，不猜）
    check("ft12_68 遇 698 帧（按南网口径到齐却非 16H）→ 0（不误判）",
          stw.frame_length_for("ft12_68", F698) == 0,
          str(stw.frame_length_for("ft12_68", F698)))
    check("ft12_68 遇 645 结构（第 8 字节 68H）→ 0（不误判）",
          stw.frame_length_for("ft12_68", F645) == 0,
          str(stw.frame_length_for("ft12_68", F645)))
    check("dlt645 遇南网/国网帧（第 8 字节非 68H）→ 0",
          stw.frame_length_for("dlt645", F68) == 0)
    check("dlt698_45 遇南网/国网帧（末字节自证是南网）→ 0",
          stw.frame_length_for("dlt698_45", F68) == 0)
    check("dlms_wrapper 版本非 0001 → 0",
          stw.frame_length_for("dlms_wrapper", b"\x00\x02" + bytes(16)) == 0)
    check("dlms_wrapper 长度域为 0 → 0",
          stw.frame_length_for("dlms_wrapper", bytes.fromhex("0001000000000000") + bytes(8)) == 0)
    check("dlms_wrapper 长度域过大（越界）→ 0",
          stw.frame_length_for("dlms_wrapper", bytes.fromhex("000100000000FFFF")) == 0)
    check("未知策略 → 0", stw.frame_length_for("nope", F68) == 0)
    check("空策略 → 0", stw.frame_length_for("", F68) == 0)
    check("空缓冲 → 0", stw.frame_length_for("ft12_68", b"") == 0)

    section("[3] hdlc_frame_len：7EH 定界")
    check("完整帧 → 6（含首尾 7EH）", stw.hdlc_frame_len(FHDLC) == 6,
          str(stw.hdlc_frame_len(FHDLC)))
    check("只有头标志（未收全）→ 0", stw.hdlc_frame_len(b"\x7E\x10\x11") == 0)
    check("首字节非 7EH → 0", stw.hdlc_frame_len(b"\x10\x11\x7E") == 0)
    check("过短（7E 7E，不足最小帧长）→ 0", stw.hdlc_frame_len(b"\x7E\x7E") == 0)
    # 连续标志位（共享 7E）：第二帧必须从第二个 7E 起算，不得产生空帧
    two = b"\x7E\x10\x11\x12\x13\x7E" + b"\x7E\x20\x21\x22\x23\x7E"
    n1 = stw.hdlc_frame_len(two)
    check("共享标志位：第一帧 = 6", n1 == 6, str(n1))
    n2 = stw.hdlc_frame_len(two[n1:])
    check("共享标志位：第二帧 = 6（从第二个 7E 起算）", n2 == 6, str(n2))
    check("共享标志位：两帧共 12 字节（无空帧）", n1 + n2 == 12, f"{n1}+{n2}")
    check("帧内 7DH 转义不影响定界（7E 只可能是标志）",
          stw.hdlc_frame_len(b"\x7E\x10\x7D\x5E\x11\x7E") == 6,
          str(stw.hdlc_frame_len(b"\x7E\x10\x7D\x5E\x11\x7E")))
    check("超长帧（尾标志太远）→ 0",
          stw.hdlc_frame_len(b"\x7E" + bytes(stw.RAW_MAX_FRAME_LEN + 10)) == 0)

    section("[4] format_parse_rows：日志文字格式")
    table = [
        ("起始字符", "0x68", "68H", "帧起始标志", 0, 0),
        ("长度域", "0x D0 00", "208", "用户数据长度=202字节", 1, 2),
        ("空值行", "", "", "", None, None),          # 名称/值全空 → 跳过
        ("无解析值", "0x41", "", "", 3, 3),           # 回落原始值
        ("有值无说明", "0x01", "1", "", 4, 4),
    ]
    rows = stw.format_parse_rows(table, 30)
    check("空值行被跳过（4 行）", len(rows) == 4, str(len(rows)))
    check("格式 = 缩进 + 字段名 = 解析值 + 说明",
          rows[0] == "    起始字符 = 68H  帧起始标志", rows[0])
    check("解析值为空时回落原始值",
          rows[2] == "    无解析值 = 0x41", rows[2])
    check("无说明时不追加空白", rows[3] == "    有值无说明 = 1", rows[3])
    check("全部行都有 4 空格缩进", all(r.startswith("    ") for r in rows))
    check("不出现裸 ' = '", all(r.strip() != "=" and " =  " not in r for r in rows))

    rows = stw.format_parse_rows(table, 2)
    check("超上限截断为 max_lines + 1 行（含提示）", len(rows) == 3, str(len(rows)))
    check("截断提示含总数与省略数",
          rows[-1] == "    …（共 4 行，已省略 2 行）", rows[-1])
    rows = stw.format_parse_rows(table, 0)
    check("max_lines = 0 → 不限制（4 行全出，无提示）",
          len(rows) == 4 and "省略" not in "".join(rows), str(rows))
    rows = stw.format_parse_rows(table, -1)
    check("max_lines < 0 → 同样不限制", len(rows) == 4, str(len(rows)))
    rows = stw.format_parse_rows(table, 99)
    check("上限大于总行数 → 不追加提示", len(rows) == 4, str(len(rows)))
    check("空表 → 空列表", stw.format_parse_rows([], 30) == [])
    check("None → 空列表", stw.format_parse_rows(None, 30) == [])
    check("坏元素（非序列）被跳过不抛异常",
          stw.format_parse_rows([None, 42, ("名称", "0x01", "1", "")], 30)
          == ["    名称 = 1"])

    section("[5] coerce_protocol：协议字段归一化")
    _pc = stw.protocol_count()
    import protocol_registry as _pr
    check("环境就绪：协议总数与注册表一致",
          _pc == len(_pr.combo_labels()), f"{_pc} vs {len(_pr.combo_labels())}")
    check("None → None", stw.coerce_protocol(None) is None)
    check("True → None（bool 不是协议）", stw.coerce_protocol(True) is None)
    check("False → None", stw.coerce_protocol(False) is None)
    check("-1 → None", stw.coerce_protocol(-1) is None)
    check(f"{_pc}（越界）→ None", stw.coerce_protocol(_pc) is None)
    check("99 → None", stw.coerce_protocol(99) is None)
    check("'abc' → None", stw.coerce_protocol("abc") is None)
    check("'' → None", stw.coerce_protocol("") is None)
    check("0 → 0", stw.coerce_protocol(0) == 0)
    check("11 → 11", stw.coerce_protocol(11) == 11)
    check("'7'（字符串数字）→ 7", stw.coerce_protocol("7") == 7)
    check("' 8 '（含空白）→ 8", stw.coerce_protocol(" 8 ") == 8)

    section("[6] normalize_command：协议字段")
    base = {"name": "查询", "data_hex": "68 12 00 41 16"}
    check("缺 protocol 键 → None（旧配置兼容）",
          stw.normalize_command(dict(base))["protocol"] is None)
    check("protocol = 7 → 7",
          stw.normalize_command({**base, "protocol": 7})["protocol"] == 7)
    check("protocol = 0 → 0（假值不得被吞）",
          stw.normalize_command({**base, "protocol": 0})["protocol"] == 0)
    check("protocol = '7' → 7",
          stw.normalize_command({**base, "protocol": "7"})["protocol"] == 7)
    check("protocol = 99 → None",
          stw.normalize_command({**base, "protocol": 99})["protocol"] is None)
    check("protocol = True → None",
          stw.normalize_command({**base, "protocol": True})["protocol"] is None)
    check("非法 protocol 不影响其余字段",
          stw.normalize_command({**base, "protocol": 99})["name"] == "查询")
    check("发送数据非法仍整条丢弃",
          stw.normalize_command({"name": "x", "data_hex": "zz"}) is None)

    section("[7] merge_params：解析参数钳制")
    merged = stw.merge_params({})
    check("默认 parse_enabled = True", merged["parse_enabled"] is True)
    check("默认 parse_max_lines = 0（不限制）", merged["parse_max_lines"] == 0)
    check("parse_enabled = False 生效",
          stw.merge_params({"parse_enabled": False})["parse_enabled"] is False)
    check("parse_max_lines = 5 生效",
          stw.merge_params({"parse_max_lines": 5})["parse_max_lines"] == 5)
    check("parse_max_lines = 0 → 0（不限制，不得被钳到下限）",
          stw.merge_params({"parse_max_lines": 0})["parse_max_lines"] == 0)
    check("parse_max_lines = -3 → 0（不限制）",
          stw.merge_params({"parse_max_lines": -3})["parse_max_lines"] == 0)
    check("parse_max_lines = 9999 → 上限 2000",
          stw.merge_params({"parse_max_lines": 9999})["parse_max_lines"] == 2000)
    check("parse_max_lines = 'abc' → 默认 0（不限制）",
          stw.merge_params({"parse_max_lines": "abc"})["parse_max_lines"] == 0)
    check("既有参数不受影响（rx_mode 仍生效）",
          stw.merge_params({"rx_mode": "frame"})["rx_mode"] == "frame")

    section("[8] 协议元数据辅助")
    opts = stw.protocol_options()
    _last = stw.protocol_count() - 1
    check("选项数 = 1 + 注册表协议数",
          len(opts) == 1 + stw.protocol_count(), str(len(opts)))
    check("首项为「不解析」/ None", opts[0] == (stw.PROTOCOL_NONE_LABEL, None),
          str(opts[0]))
    check("第二项为 [0] 南网协议", opts[1][1] == 0 and "[0]" in opts[1][0],
          str(opts[1]))
    check(f"末项索引为 {_last}", opts[-1][1] == _last, str(opts[-1]))
    check("short_name(0) = 南网协议",
          stw.protocol_short_name(0) == "南网协议", stw.protocol_short_name(0))
    check("short_name(7) = 国网协议",
          stw.protocol_short_name(7) == "国网协议", stw.protocol_short_name(7))
    check("short_name(None) = 不解析",
          stw.protocol_short_name(None) == stw.PROTOCOL_NONE_LABEL)
    check("short_name(99) = 不解析（非法回落）",
          stw.protocol_short_name(99) == stw.PROTOCOL_NONE_LABEL)

    section("[9] 配置迁移：旧默认值不得覆盖新默认值（回归）")
    # 实测报障：1.23.47 运行时把默认值 30 存进了 serial_tool_config.json，
    # 1.23.48 改了默认值却不生效（日志仍显示「已省略 83 行」）。
    check("CONFIG_VERSION 已升到 2", stw.CONFIG_VERSION == 2,
          str(stw.CONFIG_VERSION))
    v1_params = {"parse_max_lines": 30, "rx_mode": "frame", "interval_ms": 500}
    migrated = stw.migrate_params(v1_params, 1)
    check("v1 的旧默认 30 → 迁移为 0（不限制）",
          migrated["parse_max_lines"] == 0, str(migrated["parse_max_lines"]))
    check("迁移不改原对象（纯函数）",
          v1_params["parse_max_lines"] == 30, str(v1_params["parse_max_lines"]))
    check("迁移保留其余参数",
          migrated["rx_mode"] == "frame" and migrated["interval_ms"] == 500,
          str(migrated))
    check("v1 里用户特意设的 5 保留",
          stw.migrate_params({"parse_max_lines": 5}, 1)["parse_max_lines"] == 5)
    check("v1 里用户设的 0 保留",
          stw.migrate_params({"parse_max_lines": 0}, 1)["parse_max_lines"] == 0)
    check("v2 里的 30 保留（已是用户选择）",
          stw.migrate_params({"parse_max_lines": 30}, 2)["parse_max_lines"] == 30)
    check("非 dict 参数 → 空 dict", stw.migrate_params(None, 1) == {})
    check("缺键的 v1 配置 → 默认 0（不限制）",
          stw.migrate_params({}, 1).get("parse_max_lines",
                                        stw.DEFAULT_PARSE_MAX_LINES) == 0)

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "serial_tool_config.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"version": 1,
                       "commands": [{"name": "c", "data_hex": "68 16",
                                     "match_type": "none", "match_hex": ""}],
                       "params": {"parse_max_lines": 30, "rx_mode": "frame"}}, fh)
        _cmds, params = stw.load_config(path)
        check("load_config 走迁移：v1 文件里的 30 → 0",
              params["parse_max_lines"] == 0, str(params["parse_max_lines"]))
        check("load_config 迁移后其余参数仍在",
              params["rx_mode"] == "frame", str(params["rx_mode"]))
        # 真实复现：模拟用户那次运行 —— 用旧默认存盘，再读回
        _cmds2, params2 = stw.load_config(path)
        stw.save_config(path, _cmds2, params2)
        with open(path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        check("回写后版本升为 2", saved["version"] == 2, str(saved["version"]))
        check("回写后不再存 30",
              saved["params"]["parse_max_lines"] == 0,
              str(saved["params"]["parse_max_lines"]))
        _cmds3, params3 = stw.load_config(path)
        check("再读回仍是 0（不会来回抖动）",
              params3["parse_max_lines"] == 0, str(params3["parse_max_lines"]))

    section("[10] 匹配诊断纯函数（失败原因 / HEX 预览 / 偏移）")
    check("match_type_label 含中文与键",
          stw.match_type_label("contains") == "包含(contains)",
          stw.match_type_label("contains"))
    check("match_type_label 未知键回落原样",
          stw.match_type_label("weird") == "weird(weird)")
    check("first_diff_offset：首字节就不同 → 0",
          stw.first_diff_offset(b"\x01\x02", b"\x09\x02") == 0)
    check("first_diff_offset：第 3 字节不同 → 2",
          stw.first_diff_offset(b"\x01\x02\x03", b"\x01\x02\x09") == 2)
    check("first_diff_offset：一方是前缀 → 共同长度",
          stw.first_diff_offset(b"\x01\x02", b"\x01\x02\x03") == 2)
    check("hex_preview 短数据原样",
          stw.hex_preview(b"\x68\x16") == "68 16")
    check("hex_preview 空数据有文案", stw.hex_preview(b"") == "（空）")
    long_hex = stw.hex_preview(bytes(range(200)), 8)
    check("hex_preview 超限截断并标注总长",
          long_hex.startswith("00 01 02 03 04 05 06 07 …")
          and "共 200 字节" in long_hex, long_hex)
    # 失败原因：每种匹配方式都要说清「差在哪」
    exp = bytes.fromhex("6800")
    check("未收到数据 → 设备无响应",
          "未收到任何数据" in stw.match_failure_reason("contains", exp, b""))
    check("contains 未命中 → 说明预期串不在其中",
          "未出现在收到的数据中" in stw.match_failure_reason("contains", exp, b"\x01\x02"))
    r = stw.match_failure_reason("equals", exp, b"\x01\x02\x03")
    check("equals 长度不同 → 给出两个长度", "长度不一致" in r and "2 字节" in r and "3 字节" in r, r)
    r = stw.match_failure_reason("equals", exp, bytes.fromhex("6801"))
    check("equals 长度同内容不同 → 给出偏移与两字节",
          "偏移 1" in r and "00" in r and "01" in r, r)
    r = stw.match_failure_reason("starts_with", exp, b"\x01")
    check("starts_with 长度不足 → 说明比预期短", "比预期短" in r, r)
    r = stw.match_failure_reason("starts_with", exp, b"\x01\x02")
    check("starts_with 长度够但内容不同 → 给出偏移",
          "偏移 0" in r, r)
    r = stw.match_failure_reason("ends_with", exp, b"\x01")
    check("ends_with 长度不足 → 说明比预期短", "比预期短" in r, r)
    r = stw.match_failure_reason("ends_with", exp, b"\x01\x02")
    check("ends_with 长度够但结尾不同 → 给出实际结尾",
          "结尾不一致" in r and "01 02" in r, r)
    check("regex 未匹配 → 提示检查正则",
          "正则" in stw.match_failure_reason("regex", b"ab", b"cd"))
    check("none 不应判失败 → 有专门文案",
          "本不应判失败" in stw.match_failure_reason("none", exp, b"\x01"))
    # 「预期填成了发送值」是最常见的误填，必须点名
    sent = bytes.fromhex("68120041")
    r = stw.match_failure_reason("contains", sent, b"\x01\x02", sent)
    check("预期 == 发送值 → 点名常见误填", "发送数据完全相同" in r and "误填" in r, r)
    r = stw.match_failure_reason("contains", exp, b"\x01\x02", sent)
    check("预期 != 发送值 → 不给误填提示", "误填" not in r, r)

    section("[11] 反例自检（严格策略确实比启发式更严）")
    # 启发式能认出 698 帧，但指定 ft12_68 时必须拒绝（否则会按南网/国网切错帧）
    check("启发式认 698 帧（33 = L + 2）", stw.declared_frame_len(F698) == 33)
    check("指定 ft12_68 时拒绝 698 帧", stw.frame_length_for("ft12_68", F698) == 0)
    check("两者结论确实不同（判据有效）",
          stw.declared_frame_len(F698) != stw.frame_length_for("ft12_68", F698))
    # 策略表必须只含已实现自证的协议
    check("策略表不含无自证依据的协议",
          set(stw.STRATEGY_BY_PROTOCOL) == {0, 2, 3, 4, 6, 7, 8},
          str(sorted(stw.STRATEGY_BY_PROTOCOL)))
    check("策略表每个值都在 STRATEGY_NAMES 里有中文名",
          all(v in stw.STRATEGY_NAMES for v in stw.STRATEGY_BY_PROTOCOL.values()))

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
