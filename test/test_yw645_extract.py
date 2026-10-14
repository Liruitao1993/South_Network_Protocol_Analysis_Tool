# -*- coding: utf-8 -*-
"""协议13（依瓦定制645）**批量/串口帧提取**测试：`yw645_wire.extract_yw645_frames`。

运行（本机 console 默认 GBK，需 UTF-8）：
    pwshu '$env:PYTHONIOENCODING="utf-8"; python test/test_yw645_extract.py'

覆盖（prd R2.11 / AC13，design.md §6）
===================================
1. 单帧提取（9 条文档示例逐条 golden）
2. 一行内多帧拼接
3. 前置噪声（日志前缀 / 汉字 / 时间戳）
4. 长度域偏小 —— **必须按长度域定位帧尾，不得被尾部 16H 骗到**（prd F5）
5. 长度域偏大 / 截断 —— 不足即丢弃
6. 末字节不符（16H→17H）—— 不提取
7. 数据域内含 0x16（合成帧）—— 按长度域切出整帧，不在数据域内截断
8. X5 / X7 golden（X7 是作者自述「虚拟」的帧，只验地址/长度/CS 与切帧）
9. **四协议混合日志互斥**（南网 / 国网 / 645 / 698.45 各一帧 + 依瓦一帧 → 只提取依瓦）

⚠ 提取器唯一实现在 `yw645_wire.extract_yw645_frames`（桌面 `main_gui._extract_yw645_frames`
只做委托，Web 端同源 import）—— 本测试直接测该唯一实现，不另写复刻。
"""

import sys

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

from yw645_wire import (  # noqa: E402
    MODE_PASS_REQUEST,
    encode_addr12,
    encode_frame,
    extract_yw645_frames,
)

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
    print(f"\n== {title} ==")


# ── oracle：9 条文档示例（与 test_yw645_wire.py 同源，程序化抽取自 .md）──────
ORACLE_HEX = {
    "X1": "68AAAAAAAAAAAA681004001000201016",
    "X2": "6810300000001068200D00100101002006103000000010D516",
    "X3": "680450000000136830023714B416",
    "X4": "6810300000001068300237149D16",
    "X5": "6810300000001068400E37146465666768696A6B6C6D636E9F16",
    "X6": "680450000000136830023613B216",
    "X7": "68045000000013684024361343C33333333395F6435A3333B4F456883834434338B3F63373B0F692B1F634B2F6333116",
    "X8": "6810300000001068300237139C16",
    "X9": "681030000000106840023713AC16",
}

#: 其它 68 家族协议帧（互斥性判据的反例，全部取自本仓既有示例）
FRAME_NANWANG = "680E00000000010001E80005EF16"  # 南网：byte7 = 0x00
FRAME_GUOWANG = "680F0043000000000000000301004816"  # 国网：byte7 = 0x00
FRAME_DLT645 = "68AAAAAAAAAAAA68110433333333AD16"  # 645：byte7 = 0x68（最接近的形态）
FRAME_69845 = "680E004101070809AEC60100000000348716"  # 698.45：无第二个 68H（byte7 = 0x09）


# ── 1. 单帧提取 ────────────────────────────────────────────────────────


def test_single_frame():
    section("1. 单帧提取（9 条示例逐条 golden）")
    for name, hex_str in ORACLE_HEX.items():
        out = extract_yw645_frames(hex_str)
        check(f"{name} 提取为 1 帧且逐字节相同", out == [hex_str], str(out))
    # 小写输入同样命中（大小写归一）
    check(
        "小写输入归一为大写",
        extract_yw645_frames(ORACLE_HEX["X3"].lower()) == [ORACLE_HEX["X3"]],
    )
    # 带空格分隔的 hex
    spaced = " ".join(ORACLE_HEX["X3"][i : i + 2] for i in range(0, len(ORACLE_HEX["X3"]), 2))
    check("带空格分隔仍可提取", extract_yw645_frames(spaced) == [ORACLE_HEX["X3"]])


# ── 2. 一行内多帧拼接 ─────────────────────────────────────────────────


def test_multi_frame_one_line():
    section("2. 一行内多帧拼接（按长度域逐帧推进）")
    joined = ORACLE_HEX["X3"] + ORACLE_HEX["X6"] + ORACLE_HEX["X8"]
    out = extract_yw645_frames(joined)
    check(
        "三帧拼接 → 提取 3 帧且顺序/内容一致",
        out == [ORACLE_HEX["X3"], ORACLE_HEX["X6"], ORACLE_HEX["X8"]],
        str(out),
    )
    check("每帧长度 = 数据域 2 + 12 = 14 字节", all(len(f) == 28 for f in out), str([len(f) for f in out]))
    # 多行（每行一帧）
    multi_line = "\n".join([ORACLE_HEX["X2"], ORACLE_HEX["X5"]])
    check(
        "多行输入 → 两帧",
        extract_yw645_frames(multi_line) == [ORACLE_HEX["X2"], ORACLE_HEX["X5"]],
    )


# ── 3. 前置噪声 ───────────────────────────────────────────────────────


def test_noise_prefix():
    section("3. 前置噪声（日志前缀 / 汉字 / 时间戳）")
    cases = [
        ("纯汉字前缀", "接收报文：" + ORACLE_HEX["X6"]),
        (
            "时间戳+日志前缀",
            "2026-10-09 12:34:56.123 INFO 依瓦 接收 <- " + ORACLE_HEX["X6"],
        ),
        ("方括号序号前缀", "[RX]#12 " + ORACLE_HEX["X6"]),
    ]
    for label, text in cases:
        out = extract_yw645_frames(text)
        check(f"{label} → 提取出 X6", out == [ORACLE_HEX["X6"]], str(out))


# ── 4/5. 长度域边界（偏小 / 偏大 / 截断）──────────────────────────────


def test_length_field_governs():
    section("4. 长度域偏小：必须按长度域切，不得被尾部 16H 骗到")
    # 4a. 声明 8 字节数据域（整帧 20 字节），其后还有一段以 16H 结尾的杂散字节：
    #     正确行为 = 只产出 20 字节这一帧，不把后面那段一起吞进来。
    addr = encode_addr12("45000000013")
    frame = encode_frame(addr, MODE_PASS_REQUEST, bytes(range(8)))
    fh = frame.hex().upper()
    check("合成帧：数据域 8 字节 → 整帧 20 字节", len(fh) == 40, str(len(fh)))
    with_junk = fh + "AABBCCDDEEFF16"
    out = extract_yw645_frames(with_junk)
    check("声明 8 → 只切出 20 字节帧（不吞尾部 16H）", out == [fh], str(out))

    # 4b. X2 把 L 由 0x0D 改成 0x08（声明 8、实际给了 13）：
    #     按 8+12=20 字节落位后末字节不是 16H ⇒ 自证失败，不得返回整条 25 字节帧。
    x2_bad = ORACLE_HEX["X2"][:18] + "08" + ORACLE_HEX["X2"][20:]
    check("构造：X2 的 L 声明 8（帧内实有 13 字节数据）", x2_bad[18:20] == "08", x2_bad[18:20])
    out_bad = extract_yw645_frames(x2_bad)
    check(
        "长度域偏小 → 不返回整条 25 字节 X2（禁止被末字节 16H 骗到）",
        ORACLE_HEX["X2"] not in out_bad,
        str(out_bad),
    )

    section("5. 长度域偏大 / 截断")
    # 声明 8 但只给了不足 20 字节
    check("长度域偏大（数据不足）→ 不提取", extract_yw645_frames(fh[:30]) == [], str(extract_yw645_frames(fh[:30])))
    # 截断 X3（去掉末字节 16H 后再去掉一半 CS）
    check("截断帧 → 不提取", extract_yw645_frames(ORACLE_HEX["X3"][:-2]) == [])


# ── 6. 末字节不符 ─────────────────────────────────────────────────────


def test_end_byte_mismatch():
    section("6. 末字节不符（16H → 17H）")
    bad = ORACLE_HEX["X3"][:-2] + "17"
    check("末字节为 17H → 不提取", extract_yw645_frames(bad) == [], str(extract_yw645_frames(bad)))
    # 末尾的 16H 被换成 00H
    bad2 = ORACLE_HEX["X6"][:-2] + "00"
    check("末字节为 00H → 不提取", extract_yw645_frames(bad2) == [], str(extract_yw645_frames(bad2)))


# ── 7. 数据域内含 0x16 ────────────────────────────────────────────────


def test_embedded_16_in_data():
    section("7. 数据域内含 0x16：按长度域切出整帧（不在数据域内截断）")
    # 未混淆字节 0xE3 + 0x33 = 0x116 & 0xFF = 0x16 ⇒ 数据域线上确实是 16 16 16
    addr = encode_addr12("45000000013")
    frame = encode_frame(addr, MODE_PASS_REQUEST, bytes([0xE3, 0xE3, 0xE3]))
    fh = frame.hex().upper()
    check("合成帧长 = 数据域 3 + 12 = 15 字节", len(fh) == 30, str(len(fh)))
    check("数据域线上含 0x16（帧内字节 10..12）", fh[20:26] == "161616", fh[20:26])
    out = extract_yw645_frames(fh)
    check("按长度域切出整帧", out == [fh], str(out))
    # 反证：若按「搜索 16H」截断，会在数据域首个 0x16 处停（11 字节）
    naive = fh[: fh.find("16", 20) + 2]
    check("证明与「搜索 16H」截断结果不同", naive != fh and out and out[0] != naive, naive)


# ── 8. X5 / X7 golden ────────────────────────────────────────────────


def test_x5_x7_golden():
    section("8. X5 / X7 golden")
    for name in ("X5", "X7"):
        out = extract_yw645_frames(ORACLE_HEX[name])
        check(f"{name} 提取为整帧", out == [ORACLE_HEX[name]], str(out))
    check("X7 长度 = 数据域 36 + 12 = 48 字节", len(ORACLE_HEX["X7"]) == 96, str(len(ORACLE_HEX["X7"])))


# ── 9. 四协议混合日志互斥 ─────────────────────────────────────────────


def test_mixed_protocol_exclusion():
    section("9. 四协议混合日志互斥（AC13）")
    lines = [
        "2026-10-09 12:34:56.001 南网 接收: " + FRAME_NANWANG,
        "2026-10-09 12:34:57.001 国网 接收: " + FRAME_GUOWANG,
        "2026-10-09 12:34:58.001 645 接收: " + FRAME_DLT645,
        "2026-10-09 12:34:59.001 698.45 接收: " + FRAME_69845,
        "2026-10-09 12:35:00.001 依瓦 接收: " + ORACLE_HEX["X3"],
    ]
    text = "\n".join(lines)
    out = extract_yw645_frames(text)
    check("混合日志只提取出依瓦帧（恰好 1 帧）", out == [ORACLE_HEX["X3"]], str(out))

    # 逐条单独喂：只有依瓦字符集能过两道自证
    for label, frame in (
        ("南网", FRAME_NANWANG),
        ("国网", FRAME_GUOWANG),
        ("645", FRAME_DLT645),
        ("698.45", FRAME_69845),
    ):
        check(f"{label} 帧不被误提取", extract_yw645_frames(frame) == [], str(extract_yw645_frames(frame)))

    # **自证① 单独生效的算例**：byte7 不是 0x68，但长度域恰好自洽且末字节为 16H
    # （只有自证① 能拦住它）—— 若实现丢掉自证①，本条必红。
    fake = "6804500000001300300237144C16"
    check(
        "伪帧 byte7≠0x68（长度域恰好自洽、末字节 16H）仍不提取 —— 自证①生效",
        extract_yw645_frames(fake) == [],
        str(extract_yw645_frames(fake)),
    )


#: 645 帧构造器：68 + 6B地址(低字节在前) + 68 + C + L + DATA(+0x33) + CS + 16
def _dlt645(ctrl: int, data: bytes, addr: str = "AAAAAAAAAAAA") -> str:
    body = bytes.fromhex(addr) + b"\x68" + bytes([ctrl, len(data)])
    body += bytes((b + 0x33) & 0xFF for b in data)
    return (b"\x68" + body + bytes([sum(b"\x68" + body) & 0xFF]) + b"\x16").hex().upper()


def test_dlt645_known_ambiguity():
    """**已知且不可判别的歧义**（记录行为、非认可）—— 防止未来静默扩大。

    事实（本会话实测，帧结构层）：DL/T645-2007 的组帧为
    ``68 + A(6) + 68 + C + L + DATA(L,+0x33) + CS + 16``，整帧 = ``L + 12``。
    依瓦的整帧 = ``data_len + 12``，而 ``data_len = ((CMD & 0x0F) << 8) | L``。
    ⇒ 当 **645 控制码的 D3..D0 == 0** 时（如 0x10 / 0x90 / 0xF0），
    ``data_len = L``，两者**整帧长度与逐字节布局完全同构**（CS、末尾 16H 位置也相同）。

    这不是实现缺陷：**从字节上不存在判别依据**，加启发式（如限制 CMD 高 4 位
    必为 1/2/3/4）反而会丢掉 prd R2.4 要求「未知模式也必须解析」的合法帧。
    危害有限：实测该误提取**不会吞掉真正的依瓦帧**（底下第 3 条断言钉住）。

    处置：行为记录于本测试 + `progress.md` + AGENTS.md 陷阱条目（阶段 6）。
    """
    section("10. 与 DL/T645 的已知歧义（D3..D0 == 0 时结构同构，不可判别）")

    # 1) 常见 645 控制码：D3..D0 != 0 ⇒ 长度域算出超大值 ⇒ 正确跳过
    for ctrl in (0x11, 0x91, 0x08, 0x0F, 0x8F):
        f = _dlt645(ctrl, b"\x2C\xDD\x32\x37")
        check(
            f"645 控制码 0x{ctrl:02X}（D3..D0={ctrl & 0x0F:X}）不被误提取",
            extract_yw645_frames(f) == [],
            str(extract_yw645_frames(f)),
        )

    # 2) D3..D0 == 0：结构同构 ⇒ **会**被提取（记录当前行为）
    for ctrl in (0x10, 0x90, 0xF0):
        f = _dlt645(ctrl, b"\x2C\xDD\x32\x37")
        got = extract_yw645_frames(f)
        check(
            f"645 控制码 0x{ctrl:02X}（D3..D0=0）与依瓦同构 ⇒ 提取（已知歧义，无判别依据）",
            got == [f],
            str(got),
        )

    # 3) 关键安全性质：歧义不会吞掉/错位真正的依瓦帧
    x4 = ORACLE_HEX["X4"]
    for ctrl in (0x10, 0x90):
        got = extract_yw645_frames(_dlt645(ctrl, b"\x2C\xDD\x32\x37") + x4)
        check(
            f"645(0x{ctrl:02X}) 紧跟依瓦帧 ⇒ 依瓦帧仍完整提取（不被吞）",
            got[-1] == x4,
            str(got),
        )


def main():
    test_single_frame()
    test_multi_frame_one_line()
    test_noise_prefix()
    test_length_field_governs()
    test_end_byte_mismatch()
    test_embedded_16_in_data()
    test_x5_x7_golden()
    test_mixed_protocol_exclusion()
    test_dlt645_known_ambiguity()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
