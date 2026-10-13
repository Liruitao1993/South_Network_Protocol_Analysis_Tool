# -*- coding: utf-8 -*-
"""`frame_addr_fix`（按协议替换地址 + 重算校验）纯逻辑回归测试。

覆盖：
  [1] 字段声明：`fields_for` / `is_supported` / `supported_choices`（含不支持协议）
  [2] 地址文本两套语义：带分隔符 = 在线字节；书写序 = 按协议编码；长度/越界/非法字符报错
  [3] 各协议**真帧** oracle：地址已变 + **该协议校验器 0 fail** + 帧长不变 + 只有地址/校验字节变
  [4] 错误矩阵：无地址域 / 长度不符 / 结构不符 / 原校验不符 / 协议不支持 / 空输入
  [5] 反例自检：校验器对「改了地址但不重算校验」的帧必须报错（证明 oracle 有效）

运行: python test/test_bluetooth_addr_fix.py
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402

import frame_addr_fix as fix  # noqa: E402
import protocol_registry  # noqa: E402

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {detail}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


def hx(text):
    return bytes.fromhex(text.replace(" ", ""))


def validator_for(index):
    return protocol_registry.make_validator(index)


# ── 真帧夹具（来源：各协议预设库 / 仓库自身组帧器，均已通过该协议校验器）──────

#: 南网（协议0）带地址域（控制域 D5=1）：源 00×6，目的 22 00 00 00 00 00
SOUTH_ADDR = hx("68 28 00 20 00 00 00 00 00 00 22 00 00 00 00 00 02 00 01 02 02 "
                "E8 00 00 00 1E 00 09 00 01 02 03 04 05 06 07 08 09 85 16")
#: 南网（协议0）无地址域（控制域 D5=0）
SOUTH_NOADDR = hx("68 0C 00 00 02 00 03 02 00 E8 EF 16")
#: 645（协议6）读正向有功总电能（地址 00×6）
DLT645 = hx("68 00 00 00 00 00 00 68 11 04 33 33 34 33 B2 16")
#: 698.45（协议8）柔控命令（SA=33 00 00 00 00，CA=00）
T698 = hx("68 1F 00 43 04 33 00 00 00 00 00 0C 57 06 01 01 80 02 02 00 02 02 05 "
          "D0 07 00 00 11 05 00 32 4D 16")
#: 依瓦645（协议13）透传模式请求（表号 045000000013）
YW645 = hx("68 04 50 00 00 00 13 68 30 02 37 14 B4 16")
#: 南网上行（协议14）读当前数据·正向有功总电能（A1=00 00 00，A2=1，A3=0）
CSG_UPLINK = hx("68 10 00 10 00 68 4B 00 00 00 01 00 00 00 0C 60 01 01 00 00 01 00 BB 16")


def gdw_frames():
    """国网（协议7）用仓库自身组帧器造带地址域的帧（组帧器即布局权威）。"""
    from gdw_send_frame_lib import GDWFrameGenerator
    gen = GDWFrameGenerator()
    out = [
        gen.generate_frame(afn=1, fn=1, field_values={},
                           info_config={"通信模块标识": 1, "中继级别": 0},
                           src_addr="000000000001", dst_addr="000000000002"),
        gen.generate_frame(afn=1, fn=1, field_values={},
                           info_config={"通信模块标识": 1, "中继级别": 2},
                           src_addr="000000000001", dst_addr="000000000002",
                           relay_addrs=["000000000003", "000000000004"]),
    ]
    no_addr = gen.generate_frame(afn=1, fn=1, field_values={},
                                 info_config={"通信模块标识": 0},
                                 src_addr="000000000001", dst_addr="000000000002")
    return out, no_addr


# ── [1] 字段声明 ────────────────────────────────────────────────────────────

def test_fields():
    section("[1] 字段声明")

    check("支持 6 个协议（0/6/7/8/13/14）",
          tuple(fix.SUPPORTED_PROTOCOLS) == (0, 6, 7, 8, 13, 14), fix.SUPPORTED_PROTOCOLS)
    for index in fix.SUPPORTED_PROTOCOLS:
        check(f"协议{index} 有字段声明", bool(fix.fields_for(index)), fix.fields_for(index))
    check("协议9/10/11/12/1/5 无字段声明（不支持）",
          all(not fix.fields_for(i) for i in (1, 2, 3, 4, 5, 9, 10, 11, 12)),
          [fix.fields_for(i) for i in (1, 9, 12)])
    check("南网/国网 = 源地址+目的地址两组",
          [f.key for f in fix.fields_for(0)] == ["src", "dst"]
          and [f.key for f in fix.fields_for(7)] == ["src", "dst"])
    check("645/依瓦 = 单表地址；698 = SA+CA；14 = 终端地址",
          [f.key for f in fix.fields_for(6)] == ["addr"]
          and [f.key for f in fix.fields_for(13)] == ["addr"]
          and [f.key for f in fix.fields_for(8)] == ["sa", "ca"]
          and [f.key for f in fix.fields_for(14)] == ["a2"])
    check("字段带标签与写法提示（界面直接显示）",
          all(f.label and f.hint for f in fix.fields_for(8)), fix.fields_for(8))
    choices = fix.supported_choices()
    check("下拉候选 = 支持协议且显示名含索引",
          [i for _n, i in choices] == list(fix.SUPPORTED_PROTOCOLS)
          and all(f"[{i}]" in n for n, i in choices), choices)
    check("is_supported 与 fields_for 同源",
          all(fix.is_supported(i) == bool(fix.fields_for(i)) for i in range(0, 15)))
    check("protocol_label 给出短名（越界回落空串）",
          fix.protocol_label(6) != "" and fix.protocol_label(99) == "",
          (fix.protocol_label(6), fix.protocol_label(99)))


# ── [2] 地址文本语义 ────────────────────────────────────────────────────────

def test_parse_address():
    section("[2] 地址文本两套语义")

    meter = fix.fields_for(0)[1]

    data, err = fix.parse_address("000000000022", meter, 6)
    check("书写序 12 位数字 → 上线逆序", err == "" and data == bytes.fromhex("220000000000"),
          (data.hex(" "), err))

    data, err = fix.parse_address("22 00 00 00 00 00", meter, 6)
    check("带分隔符 hex → 按在线顺序原样", err == "" and data == bytes.fromhex("220000000000"),
          (data.hex(" "), err))

    data, err = fix.parse_address("0x220000000000", meter, 6)
    check("0x 前缀 → 按在线顺序", err == "" and data == bytes.fromhex("220000000000"),
          (data.hex(" "), err))

    data, err = fix.parse_address("22 00 00 00", meter, 6)
    check("在线字节长度不符 → 报错（不截断/不补齐）",
          data == b"" and "6 字节" in err, err)

    data, err = fix.parse_address("", meter, 6)
    check("空地址 → 报错", data == b"" and "不能为空" in err, err)

    data, err = fix.parse_address("00000000000G", meter, 6)
    check("非法字符 → 报错", data == b"" and err != "", err)

    yw = fix.fields_for(13)[0]
    data, err = fix.parse_address("45000000013", yw, 6)
    check("依瓦：十进制表号高位补 0 → 高字节在前",
          err == "" and data == bytes.fromhex("045000000013"), (data.hex(" "), err))
    data, err = fix.parse_address("45000000001A", yw, 6)
    check("依瓦：非数字（含 A）→ 报错", data == b"" and "数字" in err, err)

    term = fix.fields_for(14)[0]
    data, err = fix.parse_address("1234567", term, 3)
    check("南网上行：终端地址十进制 → 小端 3 字节",
          err == "" and data == bytes.fromhex("87d612"), (data.hex(" "), err))
    data, err = fix.parse_address("16777216", term, 3)
    check("南网上行：终端地址越界 → 报错", data == b"" and "越界" in err, err)

    ca = [f for f in fix.fields_for(8) if f.key == "ca"][0]
    check("698 CA：十进制 7 → 0x07",
          fix.parse_address("7", ca, 1) == (b"\x07", ""), fix.parse_address("7", ca, 1))
    check("698 CA：hex 1F → 0x1F",
          fix.parse_address("1F", ca, 1)[0] == b"\x1F", fix.parse_address("1F", ca, 1)[0])
    check("698 CA：越界报错", fix.parse_address("256", ca, 1)[0] == b""
          and "越界" in fix.parse_address("256", ca, 1)[1])

    sa = [f for f in fix.fields_for(8) if f.key == "sa"][0]
    data, err = fix.parse_address("0000000033", sa, 5)
    check("698 SA：书写序 → 右补零后逆序",
          err == "" and data == bytes.fromhex("3300000000"), (data.hex(" "), err))
    check("698 SA：超长报错", fix.parse_address("0000000000FF", sa, 5)[0] == b""
          and "最多" in fix.parse_address("0000000000FF", sa, 5)[1])


# ── [3] 各协议真帧 oracle ───────────────────────────────────────────────────

def _oracle(title, frame, index, values, expect_addr_span, expect_cs_offsets):
    """替换地址后：① 地址 span 内字节 == 期望；② 校验器 0 fail；③ 帧长不变；④ 只有地址/校验字节变。"""
    res = fix.apply(frame, index, values)
    if not res.ok:
        check(f"{title}：apply 成功", False, res.error)
        return
    check(f"{title}：帧长不变", len(res.frame) == len(frame),
          f"{len(frame)} → {len(res.frame)}")
    changed = {i for i in range(len(frame)) if frame[i] != res.frame[i]}
    allowed = set(range(*expect_addr_span)) | set(expect_cs_offsets)
    check(f"{title}：只有地址域/校验字节变化", changed <= allowed,
          f"changed={sorted(changed)} allowed={sorted(allowed)}")
    check(f"{title}：地址域确实变了", bool(changed & set(range(*expect_addr_span))),
          res.notes)
    check(f"{title}：notes 含地址与校验（旧→新）",
          any("地址域" in n for n in res.notes) and any("校验" in n for n in res.notes),
          res.notes)
    v = validator_for(index).verify(res.frame)
    bad = [c.name for c in v.checks if c.level.value == "fail"]
    check(f"{title}：**该协议校验器 0 fail**", v.valid and v.fail_count == 0,
          f"valid={v.valid} fail={v.fail_count} {bad}")


def test_south():
    section("[3a] 南网（协议0）")
    res = fix.apply(SOUTH_ADDR, 0, {"src": "000000000009", "dst": "000000000010"})
    check("南网：apply 成功", res.ok, res.error)
    if res.ok:
        check("南网：源地址上线逆序写入", res.frame[4:10] == bytes.fromhex("090000000000"),
              res.frame[4:10].hex(" "))
        check("南网：目的地址上线逆序写入", res.frame[10:16] == bytes.fromhex("100000000000"),
              res.frame[10:16].hex(" "))
        check("南网：校验和 = 帧内新值的和（自洽）",
              (sum(res.frame[3:-2]) & 0xFF) == res.frame[-2], res.frame[-2])
        v = validator_for(0).verify(res.frame)
        check("南网：校验器 0 fail", v.valid and v.fail_count == 0,
              f"fail={v.fail_count}")
    _oracle("南网-只改目的地址", SOUTH_ADDR, 0, {"dst": "000000000077"},
            (10, 16), {len(SOUTH_ADDR) - 2})


def test_dlt645():
    section("[3b] DLT645（协议6）")
    res = fix.apply(DLT645, 6, {"addr": "000000000033"})
    check("645：apply 成功", res.ok, res.error)
    if res.ok:
        check("645：表地址低字节在前", res.frame[1:7] == bytes.fromhex("330000000000"),
              res.frame[1:7].hex(" "))
        check("645：数据域未受影响（加扰字节原样）",
              res.frame[10:-2] == DLT645[10:-2], res.frame[10:-2].hex(" "))
        v = validator_for(6).verify(res.frame)
        check("645：校验器 0 fail", v.valid and v.fail_count == 0, f"fail={v.fail_count}")
    _oracle("645-hex 在线写法", DLT645, 6, {"addr": "33 00 00 00 00 00"},
            (1, 7), {len(DLT645) - 2})


def test_gdw():
    section("[3c] 国网（协议7）")
    frames, no_addr = gdw_frames()
    for i, frame in enumerate(frames):
        level = "无中继" if i == 0 else "2 级中继"
        res = fix.apply(frame, 7, {"src": "000000000009", "dst": "000000000010"})
        check(f"国网（{level}）：apply 成功", res.ok, res.error)
        if not res.ok:
            continue
        info0 = frame[4]
        alen = 12 + 6 * ((info0 >> 4) & 0x0F)
        addr_start = 10
        check(f"国网（{level}）：源地址写入",
              res.frame[addr_start:addr_start + 6] == bytes.fromhex("090000000000"),
              res.frame[addr_start:addr_start + 6].hex(" "))
        check(f"国网（{level}）：目的地址写入（中继原样保留）",
              res.frame[addr_start + alen - 6:addr_start + alen] == bytes.fromhex("100000000000"),
              res.frame[addr_start + alen - 6:addr_start + alen].hex(" "))
        if i == 1:
            check("国网（2 级中继）：中继地址未被改动",
                  res.frame[16:28] == frame[16:28], res.frame[16:28].hex(" "))
        check(f"国网（{level}）：帧长不变", len(res.frame) == len(frame))
        v = validator_for(7).verify(res.frame)
        check(f"国网（{level}）：校验器 0 fail", v.valid and v.fail_count == 0,
              f"fail={v.fail_count}")
    res = fix.apply(no_addr, 7, {"src": "000000000009"})
    check("国网（通信模块标识=0）：明确报「不含地址域」",
          not res.ok and "不含地址域" in res.error, res.error)


def test_69845():
    section("[3d] 698.45（协议8）")
    res = fix.apply(T698, 8, {"sa": "0000000099", "ca": "7"})
    check("698：apply 成功", res.ok, res.error)
    if res.ok:
        check("698：地址特征字节保留（0x04）", res.frame[4] == 0x04, hex(res.frame[4]))
        check("698：SA 写入（书写序逆序）", res.frame[5:10] == bytes.fromhex("9900000000"),
              res.frame[5:10].hex(" "))
        check("698：CA 写入", res.frame[10] == 0x07, hex(res.frame[10]))
        check("698：APDU 未受影响", res.frame[13:-3] == T698[13:-3])
        v = validator_for(8).verify(res.frame)
        check("698：校验器 0 fail（HCS/FCS 已重算）", v.valid and v.fail_count == 0,
              f"fail={v.fail_count}")
    res = fix.apply(T698, 8, {"sa": "0000000099"})
    check("698：只改 SA 也能过校验器",
          res.ok and validator_for(8).verify(res.frame).fail_count == 0,
          res.error)


def test_yw645():
    section("[3e] 依瓦定制645（协议13）")
    res = fix.apply(YW645, 13, {"addr": "450000000099"})
    check("依瓦：apply 成功", res.ok, res.error)
    if res.ok:
        check("依瓦：表地址高字节在前", res.frame[1:7] == bytes.fromhex("450000000099"),
              res.frame[1:7].hex(" "))
        check("依瓦：数据域（+0x33）原样", res.frame[10:-2] == YW645[10:-2])
        v = validator_for(13).verify(res.frame)
        check("依瓦：校验器 0 fail", v.valid and v.fail_count == 0, f"fail={v.fail_count}")


def test_csg_uplink():
    section("[3f] 南网上行（协议14）")
    res = fix.apply(CSG_UPLINK, 14, {"a2": "1234567"})
    check("南网上行：apply 成功", res.ok, res.error)
    if res.ok:
        check("南网上行：A2 小端写入，A1/A3 保留",
              res.frame[7:14] == bytes.fromhex("000000") + bytes.fromhex("87d612") + b"\x00",
              res.frame[7:14].hex(" "))
        check("南网上行：长度域形态与帧长不变",
              len(res.frame) == len(CSG_UPLINK) and res.frame[1:5] == CSG_UPLINK[1:5])
        v = validator_for(14).verify(res.frame)
        check("南网上行：校验器 0 fail", v.valid and v.fail_count == 0, f"fail={v.fail_count}")
    res = fix.apply(CSG_UPLINK, 14, {"a2": "00 00 00 87 d6 12 00"})
    check("南网上行：7 字节 hex 整段地址域写法可用", res.ok, res.error)


# ── [4] 错误矩阵 ────────────────────────────────────────────────────────────

def test_errors():
    section("[4] 错误矩阵")

    res = fix.apply(SOUTH_NOADDR, 0, {"src": "000000000009"})
    check("南网 D5=0：报「不含地址域」", not res.ok and "不含地址域" in res.error, res.error)

    res = fix.apply(SOUTH_ADDR, 0, {})
    check("南网：一个地址都没填 → 报错", not res.ok and "至少填一个" in res.error, res.error)

    res = fix.apply(DLT645, 6, {})
    check("645：未填表地址 → 报错", not res.ok and "未填写表地址" in res.error, res.error)

    res = fix.apply(DLT645, 6, {"addr": "00 00"})
    check("645：长度不符 → 报错", not res.ok and "6 字节" in res.error, res.error)

    res = fix.apply(DLT645[:-2] + b"\x00\x16", 6, {"addr": "000000000033"})
    check("645：原帧校验和不符 → 拒绝（不洗白）",
          not res.ok and "校验和不符" in res.error, res.error)

    res = fix.apply(b"\x68\x01\x02", 6, {"addr": "000000000033"})
    check("645：结构不符 → 拒绝", not res.ok and "结构不符" in res.error, res.error)

    res = fix.apply(T698[:-4] + b"\x00\x00\x00\x16", 8, {"sa": "0000000099"})
    check("698：HCS/FCS 不符 → 拒绝", not res.ok and "HCS/FCS" in res.error, res.error)

    res = fix.apply(YW645[:-2] + b"\x00\x16", 13, {"addr": "450000000099"})
    check("依瓦：原帧校验和不符 → 拒绝", not res.ok and "校验和不符" in res.error, res.error)

    res = fix.apply(CSG_UPLINK[:-2] + b"\x00\x16", 14, {"a2": "1"})
    check("南网上行：CS 不符 → 拒绝", not res.ok and "CS 不符" in res.error, res.error)

    for index in (9, 12, 1):
        res = fix.apply(SOUTH_ADDR, index, {"src": "000000000009"})
        check(f"协议{index}：明确报「暂不支持」（v1 仅 0/6/7/8/13/14）",
              not res.ok and "暂不支持" in res.error, res.error)

    res = fix.apply(b"", 0, {"src": "000000000009"})
    check("空帧 → 报错", not res.ok and "为空" in res.error, res.error)

    res = fix.apply(SOUTH_ADDR, None, {"src": "000000000009"})
    check("未选协议 → 报错", not res.ok and "未选择协议" in res.error, res.error)


# ── [5] 反例自检 ────────────────────────────────────────────────────────────

def test_negatives():
    section("[5] 反例自检（判据有效）")

    # ① 改了地址但不重算校验 → 各协议校验器必须报错（否则 oracle 恒真）
    broken = bytearray(SOUTH_ADDR)
    broken[4:10] = bytes.fromhex("090000000000")
    check("南网：改地址不重算校验 → 校验器报错",
          validator_for(0).verify(bytes(broken)).fail_count > 0)

    broken = bytearray(DLT645)
    broken[1:7] = bytes.fromhex("330000000000")
    check("645：改地址不重算校验 → 校验器报错",
          validator_for(6).verify(bytes(broken)).fail_count > 0)

    broken = bytearray(T698)
    broken[5:10] = bytes.fromhex("9900000000")
    check("698：改 SA 不重算 HCS/FCS → 校验器报错",
          validator_for(8).verify(bytes(broken)).fail_count > 0)

    broken = bytearray(CSG_UPLINK)
    broken[7:14] = bytes.fromhex("00000087d61200")
    check("南网上行：改地址不重算 CS → 校验器报错",
          validator_for(14).verify(bytes(broken)).fail_count > 0)

    # ② 地址编码方向确实有判别力（不是恒等）
    data, _err = fix.parse_address("000000000022", fix.fields_for(0)[1], 6)
    check("地址编码不是恒等（书写序 ≠ 上线序）",
          data != bytes.fromhex("000000000022"), data.hex(" "))

    # ③ 长度校验不是恒真
    check("长度校验对越界输入返回空",
          fix.parse_address("00 01 02 03 04 05 06 07", fix.fields_for(0)[0], 6)[0] == b"")


def main():
    print("=" * 64)
    print("frame_addr_fix（按协议替换地址 + 重算校验）回归")
    print("=" * 64)

    test_fields()
    test_parse_address()
    test_south()
    test_dlt645()
    test_gdw()
    test_69845()
    test_yw645()
    test_csg_uplink()
    test_errors()
    test_negatives()

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    import os  # noqa: E402

    main()
