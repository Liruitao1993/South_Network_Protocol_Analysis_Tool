# -*- coding: utf-8 -*-
"""Web 版全协议解析路径回归测试。

验证 reflex_web 的解析分发对全部 12 种协议的真实帧都不会因「调用了不正确的
函数」而崩溃——这是 Web 部署最常见的低级错误（例如 DLT645Parser 只有 parse()
没有 parse_to_table、协议 3/4/5 应走 APDU/Wrapper 方法而非完整 HDLC 解析）。

**本测试不再手抄产品逻辑**：解析器构造与 645 转表一律调用产品实现
（`protocol_registry` + `parser_registry`），手抄体会与产品代码静默漂移
（曾被用于固化的 `total_len = 10 + data_len + 2` 越界缺陷即出自此处）。
"""
import _path_setup  # noqa: E402


def get_parser(p):
    """解析器构造：与桌面 `_get_current_parser` / Web `State._get_parser` 同一注册表路径。"""
    import parser_registry
    import protocol_registry

    spec = protocol_registry.get_protocol(p)
    base = parser_registry.get_parser(spec.parser_key)
    return protocol_registry.build_gui_parser(p, base, parse_level="auto", channel="plc")


def safe_parse_to_table(parser, frame_bytes, **kwargs):
    """与 State._safe_parse_to_table 同口径：645 无 parse_to_table → 注册表同款转换。"""
    if not hasattr(parser, "parse_to_table"):
        from protocol_registry import DLT645GuiParser

        return DLT645GuiParser(parser).parse_to_table(frame_bytes)
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
        rows = safe_parse_to_table(parser, fb)
        assert rows, f"{name}: 解析结果为空"
        print(f"  [OK] {name} (协议{p}): {len(rows)} 行")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name} (协议{p}): {type(e).__name__}: {e}")
        failed += 1

print(f"\n结果: {passed} 通过, {failed} 失败")
raise SystemExit(1 if failed else 0)
