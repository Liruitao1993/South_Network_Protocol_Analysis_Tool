# -*- coding: utf-8 -*-
"""协议11（HDC 1.0）「校验位留空」台体日志帧容错回归

报障场景（协议选 [11] HDC 1.0，级别「FC+PB解析(完整MPDU)」）：台体把报文内容组好后
落日志，FCCS / PBCS / ICV 由**硬件发射机在发射时**填充，日志里留空为全 0：

    01 00 00 00 00 F0 FF FE 63 11 26 42 00 00 00 00
    C0 00 00 FF 1F 00 01 00 30 08 00 FF 00 00 01 00
    00 11 06 00 00 01 61 10 00 C5 0F 88 0D  + 0 填充至 152 字节

修复前：`_detect_fc` 只看 FCCS → 判「无 FC」；DT=1（SOF）没有兜底分支 →
整帧掉进「裸 MAC 帧」解析，吐一屏错位臆造（版本=1 单跳帧协议、MSDU长度=0、
ICV 校验失败、144 字节多余数据），业务内容完全读不出。

覆盖：
  [1] 夹具自洽（PBCS/FCCS 确实是全 0，ICV 确实是 C5 0F 88 0D）
  [2] `_detect_fc` 对 FCCS 留空的 SOF 帧改判帧体结构 → 判为完整 MPDU
  [3] `_detect_fc` 保持严格 + 变异反证（FCCS 有值但不过、结构破坏、长度不足、
      非 SOF、首块无帧起始位 → 一律不判 MPDU）
  [4] auto / fc_pb 端到端：字段条条自洽、⚠ 未填充提示齐全、业务内容可读
  [5] fc_mac 与 fc_pb 的 PBH/MAC 头一致（尾部 0 填充不得把合法 PBH 当 MAC 头）
  [6] 显式 fc_pb/fc_mac 尊重声明，但不得劫持 PB 级输入与边界输入
"""

import _path_setup  # noqa: E402,F401

import os
import pickle
import sys

from hdc10_parser import HDC10Parser, _crc24

# ── 用户报障帧（台体日志，152 字节；前 45 字节为报文内容，其余 0 填充）──
REPORTED_HEX = """
01 00 00 00 00 F0 FF FE 63 11 26 42 00 00 00 00
C0 00 00 FF 1F 00 01 00 30 08 00 FF 00 00 01 00
00 11 06 00 00 01 61 10 00 C5 0F 88 0D
"""
REPORTED = bytes.fromhex("".join(REPORTED_HEX.split())) + bytes(152 - 45)
CONTENT_END = 45                      # ICV 结束于字节 44，其后为日志 0 填充
FRAME_LEN = 152
PB_LEN = FRAME_LEN - 16               # FC(16B) 之后剩 136 字节 = 单 PB

PICKLE = os.path.join(os.path.dirname(__file__), "hdc10_real_frames.pkl")

FAILURES = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


def section(title):
    print(f"\n── {title} " + "─" * max(0, 52 - len(title)))


def rows_of(frame, level, **kw):
    return HDC10Parser().parse_to_table(frame, parse_level=level, **kw)


def find(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    return None


def raw(rows, name):
    """取「原始值」列（第 2 列）。"""
    r = find(rows, name)
    return None if r is None else str(r[1])


def val(rows, name):
    """取「解析值」列（第 3 列）。"""
    r = find(rows, name)
    return None if r is None else str(r[2])


def desc(rows, name):
    """取「说明」列（第 4 列）。"""
    r = find(rows, name)
    return None if r is None else str(r[3])


def fingerprint(rows):
    return [tuple(str(c) for c in r) for r in rows]


def mutate(frame, off, value):
    m = bytearray(frame)
    m[off] = value
    return bytes(m)


def load_fixtures():
    with open(PICKLE, "rb") as f:
        return pickle.load(f)


def main():
    p = HDC10Parser()

    # ── [1] 夹具自洽 ────────────────────────────────────────────
    section("[1] 报障帧夹具自洽")
    check(f"帧长 {FRAME_LEN} 字节", len(REPORTED) == FRAME_LEN, str(len(REPORTED)))
    check("字节45 起为全 0 日志填充", set(REPORTED[CONTENT_END:]) == {0})
    check("FCCS(字节13-15) 留空为全 0", REPORTED[13:16] == b"\x00\x00\x00")
    check("分集拷贝基本模式=4（字节11 高 4 位）→ PB 136B 与 FC 后剩余长度自洽",
          (REPORTED[11] >> 4) == 0x04 and len(REPORTED) - 16 == PB_LEN,
          f"byte11=0x{REPORTED[11]:02X}")
    check("PBCS(PB 尾 3 字节) 留空为全 0", REPORTED[-3:] == b"\x00\x00\x00")
    check("ICV(字节41-44) = C5 0F 88 0D",
          REPORTED[41:45] == bytes.fromhex("C50F880D"))

    # ── [2] FCCS 留空 → 改判帧体结构 ───────────────────────────
    section("[2] _detect_fc：FCCS 留空的 SOF 帧按帧体结构判为完整 MPDU")
    check("报障帧 _detect_fc = True", p._detect_fc(REPORTED) is True)
    check("同等条件下 FCCS 计算值与日志值不同（证明确实留空，不是巧合通过）",
          int.from_bytes(REPORTED[13:16], "little") != _crc24(REPORTED[:13]))
    _pbh_len, score = p._probe_pb_form(REPORTED[17:])
    check(f"帧体打分 {score} ≥ 阈值 4（MSDU 长度/类型 + 端口/报文ID + ICV 自校验）",
          score >= 4, f"score={score}")

    # ── [3] 严格性与变异反证 ────────────────────────────────────
    section("[3] _detect_fc 严格性 + 变异反证")
    check("FCCS 置非零但校验不过 → 不判 MPDU（保持严格）",
          p._detect_fc(mutate(REPORTED, 13, 0x11)) is False)
    check("截断到 25 字节（< 26）→ 不判 MPDU",
          p._detect_fc(REPORTED[:25]) is False)
    check("定界符非 SOF（DT=0）→ 不判 MPDU（留空容错只对 SOF 生效）",
          p._detect_fc(mutate(REPORTED, 0, 0x00)) is False)
    check("偏移16 首块去掉帧起始位 → 不判 MPDU（FC 之后布局自相矛盾）",
          p._detect_fc(mutate(REPORTED, 16, 0x00)) is False)
    check("MSDU 类型改成 0x77（非已知集合）→ 不判 MPDU",
          p._detect_fc(mutate(REPORTED, 24, 0x77)) is False)
    check("MSDU 长度改成 127（与剩余长度不自洽）→ 不判 MPDU",
          p._detect_fc(mutate(REPORTED, 25, 0x7F)) is False)
    check("端口/报文ID/ICV 三处全被破坏 → 强证据皆失，不判 MPDU",
          p._detect_fc(mutate(mutate(mutate(mutate(REPORTED, 33, 0xFF),
                                            34, 0xFF), 35, 0xFF), 41, 0x00))
          is False)

    # ── [4] 端到端：auto / fc_pb ────────────────────────────────
    section("[4] 端到端解析（auto / fc_pb，级别「FC+PB解析(完整MPDU)」）")
    auto = rows_of(REPORTED, "auto")
    fc_pb = rows_of(REPORTED, "fc_pb")
    names = [str(r[0]).strip() for r in auto]
    check("无「❌ 解析失败」行", not any(n.startswith("❌") for n in names),
          str([n for n in names if n.startswith("❌")]))
    check("按完整 MPDU 解析（FC 字段行存在）", "定界符类型(DT)" in names)
    check("DT = SOF帧", "SOF帧" in str(desc(auto, "定界符类型(DT)")),
          str(desc(auto, "定界符类型(DT)")))
    check("FCCS 行给出「未填充(全 0)」状态而非误报校验失败",
          "未填充" in str(desc(auto, "帧控制校验序列(FCCS)"))
          and val(auto, "帧控制校验序列(FCCS)") == "0x000000",
          str(desc(auto, "帧控制校验序列(FCCS)")))
    check("FCCS 行给出应有的计算值 0xB3A813",
          "0xB3A813" in str(desc(auto, "帧控制校验序列(FCCS)")),
          str(desc(auto, "帧控制校验序列(FCCS)")))
    check("追加「⚠ FCCS 未通过」行且说明留空原因",
          find(auto, "⚠ FCCS 未通过") is not None
          and "留空" in str(desc(auto, "⚠ FCCS 未通过")),
          str(desc(auto, "⚠ FCCS 未通过")))
    check(f"物理块长度 = FC 后剩余 {PB_LEN} 字节（与分集拷贝基本模式自洽）",
          val(auto, "物理块(PB)") == f"{PB_LEN}字节", str(val(auto, "物理块(PB)")))
    check("分集拷贝基本模式说明含 136B", "136B" in str(desc(auto, "分集拷贝基本模式")),
          str(desc(auto, "分集拷贝基本模式")))
    check("PBH = 0xC0（seq=0 起始+结束，单 PB 完整 MAC 帧）",
          val(auto, "PB头(PBH)") == "seq=0", str(val(auto, "PB头(PBH)")))
    check("MSDU类型 = 48（应用层报文）", val(auto, "MSDU类型") == "48",
          str(val(auto, "MSDU类型")))
    check("MSDU长度 = 8字节", val(auto, "MSDU长度") == "8字节",
          str(val(auto, "MSDU长度")))
    check("报文端口号 = 0x11（普通业务的解析值为 17）",
          raw(auto, "报文端口号") == "0x11" and val(auto, "报文端口号") == "17",
          f"{raw(auto, '报文端口号')}/{val(auto, '报文端口号')}")
    check("报文ID = 0x0006（通信测试）", val(auto, "报文ID") == "0x0006",
          str(val(auto, "报文ID")))
    check("业务数据解出通信测试-频段切换（目标频段原始值 1，解析为频段1）",
          find(auto, "通信测试报文") is not None
          and raw(auto, "频段值(目标频段)") == "1"
          and "通信频段1" in str(val(auto, "频段值(目标频段)")),
          f"{raw(auto, '频段值(目标频段)')}/{val(auto, '频段值(目标频段)')}")
    check("ICV 校验正确（C5 0F 88 0D，未被留空 → 逐条自洽）",
          "校验正确" in str(desc(auto, "完整性校验值(ICV)")),
          str(desc(auto, "完整性校验值(ICV)")))
    check("PBCS 留空单独成行（与「无 PBCS/截断」区分，不判为错误）",
          find(auto, "⚠ PBCS未填充") is not None
          and val(auto, "⚠ PBCS未填充") == "全 0",
          str(find(auto, "⚠ PBCS未填充")))
    check("不再出现裸「PBCS」行（未误判为校验失败）", find(auto, "PBCS") is None)
    check("fc_pb 与 auto 输出逐字符一致（同一帧同一结论）",
          fingerprint(auto) == fingerprint(fc_pb))
    check(f"ICV 之后的 {FRAME_LEN - CONTENT_END} 字节 0 填充如实标注为帧尾多余数据",
          val(auto, "帧尾多余数据") == f"{FRAME_LEN - CONTENT_END}字节",
          str(val(auto, "帧尾多余数据")))

    # ── [5] fc_mac 与 fc_pb 的 PBH / MAC 头一致 ────────────────
    section("[5] fc_mac：SOF 首块帧起始位已置 → 直接采信 PBH")
    fc_mac = rows_of(REPORTED, "fc_mac")
    check("fc_mac 识别出 PBH（不得因尾部 0 填充判「无 PBH」）",
          val(fc_mac, "PB头") == "seq=0", str(val(fc_mac, "PB头")))
    check("fc_mac MSDU类型 = 48 与 auto 一致",
          val(fc_mac, "MSDU类型") == val(auto, "MSDU类型") == "48",
          str(val(fc_mac, "MSDU类型")))
    check("fc_mac MSDU长度 = 8字节 与 auto 一致",
          val(fc_mac, "MSDU长度") == val(auto, "MSDU长度") == "8字节",
          str(val(fc_mac, "MSDU长度")))
    check("fc_mac 原始源TEI/原始目的TEI 与 auto 一致",
          all(val(fc_mac, n) == val(auto, n)
              for n in ("原始源TEI", "原始目的TEI")),
          f"fc_mac={val(fc_mac, '原始源TEI')}/{val(fc_mac, '原始目的TEI')} "
          f"auto={val(auto, '原始源TEI')}/{val(auto, '原始目的TEI')}")

    # ── [6] 级别尊重 + 劫持防护 ─────────────────────────────────
    section("[6] 显式级别尊重声明，但不劫持 PB 级输入")
    # FCCS 有值但校验不过：auto 不认 MPDU，显式 fc_pb 尊重用户的级别声明
    bad_fccs = mutate(REPORTED, 13, 0x11)
    auto_bad = rows_of(bad_fccs, "auto")
    fc_pb_bad = rows_of(bad_fccs, "fc_pb")
    check("FCCS 有值但校验不过时 auto 不按 MPDU 解析",
          "定界符类型(DT)" not in [str(r[0]).strip() for r in auto_bad])
    check("显式 fc_pb 尊重声明：仍按完整 MPDU 解析",
          "定界符类型(DT)" in [str(r[0]).strip() for r in fc_pb_bad])
    check("显式 fc_pb 的 ⚠ FCCS 行说明「按指定的完整MPDU级别继续解析」",
          "按指定的" in str(desc(fc_pb_bad, "⚠ FCCS 未通过")),
          str(desc(fc_pb_bad, "⚠ FCCS 未通过")))

    for n in (0, 1, 8, 15, 16, 17, 25, 26):
        errs = []
        for lvl in ("auto", "fc_pb", "fc_mac", "fc_only", "pb_only",
                    "mac_only", "app"):
            try:
                rows_of(bytes(n), lvl)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{lvl}({n}):{type(exc).__name__}")
        check(f"边界输入 {n} 字节 × 7 级别不抛异常", not errs, str(errs))

    fixtures = load_fixtures()
    check(f"真实夹具 {len(fixtures)} 帧", len(fixtures) >= 50, str(len(fixtures)))
    hijack = []
    for fi, fb, _key in fixtures:
        if fingerprint(rows_of(fb, "auto")) != fingerprint(rows_of(fb, "fc_pb")):
            hijack.append((fi, len(fb), f"0x{fb[0]:02X}"))
    check("PB 级输入在 fc_pb 级别下不被劫持进 FC 路径（auto 与 fc_pb 全等）",
          not hijack, str(hijack[:5]))
    c1 = [fb for _fi, fb, _k in fixtures if fb[0] == 0xC1]
    check("夹具中存在 byte0=0xC1 的 PB 帧（低 3 位为 1 的劫持候选）", bool(c1))
    if c1:
        check("该 0xC1 帧 fc_pb 与 auto 结果全等（规范硬条件挡住劫持）",
              fingerprint(rows_of(c1[0], "auto"))
              == fingerprint(rows_of(c1[0], "fc_pb")))
    mac_errs = []
    for fi, fb, _k in fixtures:
        try:
            rows_of(fb, "fc_mac")
        except Exception as exc:  # noqa: BLE001
            mac_errs.append(f"{fi}:{type(exc).__name__}")
    check("PB 级输入 fc_mac 级别不抛异常", not mac_errs, str(mac_errs[:5]))

    print("\n" + "=" * 58)
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 项失败: {FAILURES}")
        sys.exit(1)
    print(f"[OK] 全部 {PASS} 项检查通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
