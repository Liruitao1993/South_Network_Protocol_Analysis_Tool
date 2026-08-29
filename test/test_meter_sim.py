# -*- coding: utf-8 -*-
"""协议8 虚拟表（698.45 从站模拟器）测试。

核心断言策略：用 DLT69845FrameGenerator 构造主站请求 → MeterSimEngine 生成响应
→ DLT69845Parser 回读响应帧（自组帧自解析闭环）。
"""
import os
import sys
import time

import _path_setup  # noqa: E402,F401

from dl_t698_45_frame_gen import DLT69845FrameGenerator
from dl_t698_45_parser import DLT69845Parser

from meter_sim import MeterSimEngine, SimOptions, load_archive
from meter_sim import link_layer
from meter_sim.response_builder import wrap_security_plain_mac

FG = DLT69845FrameGenerator()
PARSER = DLT69845Parser()

# 主站单地址 SA：特征 0x05（单地址，长度6）+ 6 字节地址
SA_SINGLE = bytes([0x05, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06])
# 通配地址 SA：特征 0x45（通配类型=1，长度6）+ AA×6
SA_WILD = bytes([0x45]) + b"\xAA" * 6

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond), info))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f"  {info}" if info and not cond else ""))


def table_text(resp_frame):
    rows = PARSER.parse_to_table(resp_frame)
    return "\n".join(str(r[0]) + " " + str(r[2]) for r in rows)


def get_request(oad: bytes) -> bytes:
    return FG.generate_get_request_normal(SA_SINGLE, 0, 0x01, oad)


def engine():
    return MeterSimEngine(load_archive(), SimOptions())


# ── 0. 档案 ──────────────────────────────────────────────
def test_archive():
    print("Test: 档案加载")
    arc = load_archive()
    check("档案条目数=194", len(arc.items) == 194, f"实际 {len(arc.items)}")
    check("lookup 命中正向有功电能", arc.lookup_key("00100200") is not None)
    check("lookup 未知返回 None", arc.lookup_key("deadbeef") is None)
    frozen = arc.lookup("2021", "02", "00", frozen="5004")
    check("冻结档案 5004/2021 命中", frozen is not None)


# ── 1. 链路层帧提取 ─────────────────────────────────────
def test_extract():
    print("Test: 链路层帧提取")
    req = get_request(bytes.fromhex("20000200"))
    # 粘包两帧
    frames, _, rest = link_layer.extract_frames(req + req)
    check("粘包提取2帧", len(frames) == 2, f"实际 {len(frames)}")
    check("粘包无剩余", rest == b"")
    # FE 前缀
    frames2, _, _ = link_layer.extract_frames(b"\xFE\xFE" + req)
    check("FE 前缀跳过", len(frames2) == 1)
    # 半帧保留
    frames3, consumed, rest3 = link_layer.extract_frames(req[:10])
    check("半帧不报错并保留", len(frames3) == 0 and len(rest3) == 10)
    # 帧头解析
    hdr = link_layer.parse_header(req)
    check("帧头 func=3", hdr["func"] == 3)
    check("帧头单播类型0", hdr["addr_type"] == 0)
    check("通配地址识别", link_layer.is_wildcard_sa(link_layer.parse_header(
        FG.generate_get_request_normal(SA_WILD, 0, 1, bytes.fromhex("00100200")))))


# ── 2. Normal 请求闭环（≥10 个典型 OAD）────────────────
TYPICAL_OADS = [
    ("00000200", "组合有功电能"),
    ("00100200", "正向有功电能"),
    ("20000200", "电压"),
    ("20000201", "A相电压"),
    ("10100200", "正向有功最大需量"),
    ("40000200", "日期时间"),
    ("40010200", "通信地址"),
    ("40020200", "表号"),
    ("202a0200", "目标服务器地址"),
    ("20220200", "事件记录序号"),
]


def test_normal_roundtrip():
    print("Test: GET Normal 请求→响应→回读")
    eng = engine()
    for oad_hex, name in TYPICAL_OADS:
        req = get_request(bytes.fromhex(oad_hex))
        resps = eng.handle_frame(req)
        check(f"Normal {oad_hex}({name}) 有响应", len(resps) == 1)
        if not resps:
            continue
        text = table_text(resps[0])
        check(f"Normal {oad_hex} 回读含响应", "响应" in text or "Get-Response" in text.upper()
              or "85" in text, text[:60])
        # 帧边界合法
        check(f"Normal {oad_hex} 帧尾16", resps[0][0] == 0x68 and resps[0][-1] == 0x16)


def test_unknown_oad_dar():
    print("Test: 未知 OAD 返回 DAR")
    eng = engine()
    resps = eng.handle_frame(get_request(bytes.fromhex("77770200")))
    check("未知 OID 仍响应1帧", len(resps) == 1)
    if resps:
        # APDU 中应含 DAR 0x09
        apdu = link_layer.parse_header(resps[0])["apdu"]
        check("DAR=对象不存在(0x09)", 0x09 in apdu, apdu.hex())


# ── 3. NormalList ───────────────────────────────────────
def test_normal_list():
    print("Test: GET NormalList")
    eng = engine()
    oads = [bytes.fromhex(h) for h in ("20000200", "20000201", "00100200")]
    apdu = bytes([0x05, 0x02, 0x01, len(oads)]) + b"".join(oads)
    req = FG._assemble_frame(SA_SINGLE, 0, 0x43, apdu)
    resps = eng.handle_frame(req)
    check("NormalList 响应1帧", len(resps) == 1)
    if resps:
        text = table_text(resps[0])
        check("NormalList 回读含响应", "响应" in text)
        check("NormalList 帧长>20", len(resps[0]) > 20)


# ── 4. Record 冻结（Selector 01）────────────────────────
def test_record():
    print("Test: GET Record 日冻结 Selector01")
    eng = engine()
    ts = bytes([0x1C, 0x07, 0xE9, 8, 27, 12, 0, 0])  # 2025-08-27 12:00:00
    apdu = (bytes([0x05, 0x03, 0x01]) + bytes.fromhex("50040200")
            + bytes([0x01]) + bytes.fromhex("50040200") + ts
            + bytes([0x01, 0x00]) + bytes.fromhex("20210200"))
    req = FG._assemble_frame(SA_SINGLE, 0, 0x43, apdu)
    resps = eng.handle_frame(req)
    check("Record 响应1帧", len(resps) == 1)
    if resps:
        check("Record 帧尾16", resps[0][-1] == 0x16)
        apdu_resp = link_layer.parse_header(resps[0])["apdu"]
        check("Record 服务码85 03", apdu_resp[0] == 0x85 and apdu_resp[1] == 0x03,
              apdu_resp[:4].hex())


# ── 5. 链接请求 ─────────────────────────────────────────
def test_link():
    print("Test: 链接请求")
    eng = engine()
    req = FG.generate_link_request(SA_SINGLE, 0, piid=0x22, req_type=1)
    resps = eng.handle_frame(req)
    check("链接请求有响应", len(resps) == 1)
    if resps:
        apdu = link_layer.parse_header(resps[0])["apdu"]
        check("链接响应 81", apdu[0] == 0x81, apdu.hex())


# ── 6. 安全明文 + MAC ───────────────────────────────────
def test_security():
    print("Test: 安全明文请求 → MAC 封装响应")
    eng = engine()
    inner_req = bytes([0x05, 0x01, 0x01]) + bytes.fromhex("40000200")
    wrap = wrap_security_plain_mac  # 仅参照封装格式
    # 请求侧 10 00 len inner 01
    sec_req_apdu = bytes([0x10, 0x00, len(inner_req)]) + inner_req + b"\x01"
    req = FG._assemble_frame(SA_SINGLE, 0, 0x43, sec_req_apdu)
    resps = eng.handle_frame(req)
    check("安全请求有响应", len(resps) == 1)
    if resps:
        apdu = link_layer.parse_header(resps[0])["apdu"]
        check("响应安全封装 90 00", apdu[0] == 0x90 and apdu[1] == 0x00, apdu[:4].hex())
        check("响应含 MAC 0A0B0C0D", b"\x0A\x0B\x0C\x0D" in apdu)


# ── 7. 通配多表 / 名单 ──────────────────────────────────
def test_wildcard():
    print("Test: 通配地址多表响应")
    opts = SimOptions(meter_count=3)
    eng = MeterSimEngine(load_archive(), opts)
    req = FG.generate_get_request_normal(SA_WILD, 0, 0x01,
                                         bytes.fromhex("40020200"))
    resps = eng.handle_frame(req)
    check("通配返回3帧", len(resps) == 3, f"实际 {len(resps)}")
    if len(resps) == 3:
        # 三块表 SA 表号递增
        sas = [link_layer.parse_header(f)["sa"].hex() for f in resps]
        check("三帧 SA 互不相同", len(set(sas)) == 3, str(sas))


def test_blacklist():
    print("Test: 黑名单不回复")
    # SA body 反转 hex
    opts = SimOptions(blacklist=["060504030201"])
    eng = MeterSimEngine(load_archive(), opts)
    resps = eng.handle_frame(get_request(bytes.fromhex("20000200")))
    check("黑名单命中0响应", len(resps) == 0, f"实际 {len(resps)}")


# ── 8. 电能量递增 / 漏点 ────────────────────────────────
def test_dynamic():
    print("Test: 动态特性")
    opts = SimOptions(energy_increase=True)
    eng = MeterSimEngine(load_archive(), opts)
    r1 = eng.handle_frame(get_request(bytes.fromhex("00100200")))
    time.sleep(1.1)
    eng2 = MeterSimEngine(load_archive(), SimOptions(energy_increase=True))
    eng2.start_time = time.time() - 5  # 模拟已运行5秒
    r2 = eng2.handle_frame(get_request(bytes.fromhex("00100200")))
    check("递增模式两帧均生成", len(r1) == 1 and len(r2) == 1)

    # 漏点
    opts_leak = SimOptions(leak_window=(0, 1440))  # 全天区间
    eng_leak = MeterSimEngine(load_archive(), opts_leak)
    ts = bytes([0x1C, 0x07, 0xE9, 8, 27, 12, 0, 0])
    apdu = (bytes([0x05, 0x03, 0x02]) + bytes.fromhex("50020200")
            + bytes([0x01]) + bytes.fromhex("50020200") + ts
            + bytes([0x01, 0x00]) + bytes.fromhex("00100200"))
    req = FG._assemble_frame(SA_SINGLE, 0, 0x43, apdu)
    resps = eng_leak.handle_frame(req)
    check("曲线漏点仍响应1帧", len(resps) == 1)
    if resps:
        apdu_resp = link_layer.parse_header(resps[0])["apdu"]
        check("漏点响应含0行标记(0100)", b"\x01\x00" in apdu_resp, apdu_resp.hex()[:40])


# ── 9. 垃圾帧不崩溃 ─────────────────────────────────────
def test_garbage():
    print("Test: 异常输入容错")
    eng = engine()
    for bad in (b"\x68\x11\x00\x43" + b"\x00" * 20, b"\x68\x05\x00" + b"\x99" * 10):
        try:
            r = eng.handle_frame(bad)
            check(f"畸形帧不崩溃 ({bad[:4].hex()})", isinstance(r, list))
        except Exception as e:
            check(f"畸形帧不崩溃 ({bad[:4].hex()})", False, str(e))


for fn in [test_archive, test_extract, test_normal_roundtrip, test_unknown_oad_dar,
           test_normal_list, test_record, test_link, test_security,
           test_wildcard, test_blacklist, test_dynamic, test_garbage]:
    fn()

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"\n共 {len(results)} 项: {passed} passed / {failed} failed")
sys.exit(1 if failed else 0)
