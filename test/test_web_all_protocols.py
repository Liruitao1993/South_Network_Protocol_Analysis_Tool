# -*- coding: utf-8 -*-
"""Web 版全协议解析路径回归测试。

验证 reflex_web 的解析分发（_get_parser + _safe_parse_to_table）对全部 12 种协议
的真实帧都不会因「调用了不正确的函数」而崩溃——这是 Web 部署最常见的低级错误
（例如 DLT645Parser 只有 parse() 没有 parse_to_table、协议 3/4/5 应走 APDU/Wrapper
方法而非完整 HDLC 解析）。

与 reflex_web/reflex_web/reflex_web.py 中 State._get_parser 与
State._safe_parse_to_table 保持逻辑一致。
"""
import _path_setup  # noqa: E402

# ── 复制 Web 版 _get_parser 逻辑（保持同步）──────────────────
def get_parser(p):
    """复制 reflex_web.py::State._get_parser"""
    if p == 0:
        from protocol_parser import ProtocolFrameParser
        return ProtocolFrameParser()
    if p == 1:
        from plc_rf_parser import PLCRFProtocolParser
        return PLCRFProtocolParser()
    if p in (2, 3, 4, 5):
        from hdlc_parser import HDLCParser
        if p == 2:
            return HDLCParser()
        if p in (3, 5):
            class APDUParserWeb:
                def __init__(self, h):
                    self.h = h
                def parse_to_table(self, data, **kw):
                    return self.h.parse_apdu_to_table(data)
            return APDUParserWeb(HDLCParser())
        class WrapperParserWeb:
            def __init__(self, h):
                self.h = h
            def parse_to_table(self, data, **kw):
                return self.h.parse_wrapper_to_table(data)
        return WrapperParserWeb(HDLCParser())
    if p == 6:
        from dlt645_parser import DLT645Parser
        return DLT645Parser()
    if p == 7:
        from gdw10376_parser import GDW10376Parser
        return GDW10376Parser()
    if p == 8:
        from dl_t698_45_parser import DLT69845Parser
        return DLT69845Parser()
    if p == 9:
        from csg_new_gen_parser import CSGNewGenParser
        return CSGNewGenParser()
    if p == 10:
        from gw_new_gen_parser import GWNewGenParser
        return GWNewGenParser()
    if p == 11:
        from hdc10_parser import HDC10Parser
        return HDC10Parser()
    from protocol_parser import ProtocolFrameParser
    return ProtocolFrameParser()


# ── 复制 Web 版 _safe_parse_to_table 逻辑（保持同步）──────────
def safe_parse_to_table(parser, frame_bytes, **kwargs):
    if not hasattr(parser, "parse_to_table"):
        r = parser.parse(frame_bytes)
        result = []
        data_len = r.get("data_length", 0)
        total_len = 10 + data_len + 2
        for field, raw, desc in r.get("fields", []):
            bs, be, pv = 0, 0, ""
            if "帧起始符 1" in field:
                bs, be = 0, 0
            elif "从站地址" in field:
                bs, be = 1, 6
            elif "帧起始符 2" in field:
                bs, be = 7, 7
            elif "控制码" in field:
                bs, be = 8, 8
                pv = r.get("control_parsed", "")
            elif "数据长度" in field:
                bs, be = 9, 9
            elif "数据标识 DI" in field:
                bs, be = 10, 13
                dc, dd = r.get("di_code", ""), r.get("di_desc", "")
                pv = f"{dc} ({dd})" if dc and dd else dc
            elif "数据内容" in field:
                bs, be = 14, 10 + data_len - 1
            elif "数据域" in field:
                bs, be = 10, 10 + data_len - 1
            elif "校验和" in field:
                bs, be = total_len - 2, total_len - 2
            elif "帧结束符" in field:
                bs, be = total_len - 1, total_len - 1
            result.append((field, raw, pv, desc, bs, be))
        return result
    return parser.parse_to_table(frame_bytes, **kwargs)


# ── 各协议测试帧 ────────────────────────────────────────────
FRAMES = {
    0: "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
    1: "02 00 05 C0 20 01 00 99 01 01 00 02 00 00 00 00 00 01 10 25",
    2: "7E A0 0F 21 03 0E 93 06 07 E6 01 03 07 81 08 00 01 00 12 34 56 00 00 00 01 00 00 00 00 14 46 15 A6 7E",
    3: "C0 01 C1 00 01 00 00 01 80 02 00 00 00",
    4: "60 00 0F 00 00 00 00 01 00 00 00 14 46 15 A6",
    5: "C0 01 C1 00 01 00 00 01 80 02 00 00 00",
    6: "68 AA AA AA AA AA AA 68 11 04 33 33 33 33 AD 16",
    7: "68 0F 00 43 00 00 00 00 00 00 00 00 00 03 01 00 48 16",
    8: "68 0E 00 41 01 07 08 09 88 03 01 00 00 00 00 34 87 16",
    9: "11 01 01 00 00 00 00 01 00 01 00 00 00 00 00 00 03 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F 10 11 12 13 14 15 16 17 18 19 1A 1B 1C 1D 1E 1F 20",
    10: "C1 20 00 01 00 01 B2 B7 00 0F 80 FF 00 00 01 00 00 03 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F",
    11: "00 3A CF 9E E0 A8 12 69 A7 A0 BE 06 00 42 6D 29 00 03 01 02 03 04 05 06 07 08 09 0A 0B 0C",
}

NAMES = {0:"南网",1:"PLC RF",2:"HDLC",3:"DLMS-APDU(国网)",4:"Wrapper",5:"APDU裸",6:"DLT645",7:"国网",8:"698.45",9:"新一代载波",10:"国网新一代",11:"HDC 1.0"}

passed = 0
failed = 0
for p in sorted(FRAMES):
    name = NAMES[p]
    try:
        parser = get_parser(p)
        fb = bytes.fromhex(FRAMES[p].replace(" ", ""))
        if p == 9:
            rows = safe_parse_to_table(parser, fb, parse_level="auto")
        elif p in (10, 11):
            rows = safe_parse_to_table(parser, fb, parse_level="auto", channel="plc")
        else:
            rows = safe_parse_to_table(parser, fb)
        assert rows, f"{name}: 解析结果为空"
        print(f"  [OK] {name} (协议{p}): {len(rows)} 行")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name} (协议{p}): {type(e).__name__}: {e}")
        failed += 1

print(f"\n结果: {passed} 通过, {failed} 失败")
raise SystemExit(1 if failed else 0)
