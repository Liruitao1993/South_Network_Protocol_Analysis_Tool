# -*- coding: utf-8 -*-
"""协议6（DL/T645-2007）扩展数据项「入网信息」DI FFAA0001 解析测试。

现场两帧（用户 2026-11-10 提供）：

- 读取帧：``68 AA AA AA AA AA AA 68 11 04 34 33 DD 32 57 16``
- 应答帧：``68 33 00 98 06 55 07 68 91 16 34 33 DD 32 34 66 33 CB 39 88 3A
  35 43 34 33 44 B4 68 B4 93 39 33 9F 16``

字段规则（用户口径）：
入网状态 1B（0 未入网 / 1 已入网 / 2 离网）、STA 地址 6B、本节点 TEI 2B
（16bit 值高 4bit 固定为 1，低 12bit 为 TEI）、代理节点 TEI 2B、
入网通道/角色/层级 1B（bit7 通道 / bit6~4 角色 / bit3~0 层级）、入网 CCO 地址 6B。

注意：解析器交给扩展模块的 `data` 已**减 33H**，所以上面帧里的 ``34 33 DD 32``
解出来是 ``01 00 AA FF`` → DI = ``FFAA0001``。

运行：``python test/test_dlt645_net_info_ext.py``
"""

import _path_setup  # noqa: E402,F401

import sys

import dlt645_net_info_ext as ext  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name} {detail}")
        FAILED.append(f"{name} {detail}")


def fields_of(result):
    """把 fields 转成 {字段名: (原始值, 解析值, 说明)}（同名取第一条）。"""
    out = {}
    for item in result["fields"]:
        name = item[0]
        if name in out:
            continue
        if len(item) == 4:
            out[name] = (item[1], item[2], item[3])
        elif len(item) == 3:
            out[name] = (item[1], "", item[2])
        else:
            out[name] = ("", "", "")
    return out


REQ_HEX = "68 AA AA AA AA AA AA 68 11 04 34 33 DD 32 57 16"
RESP_HEX = ("68 33 00 98 06 55 07 68 91 16 34 33 DD 32 34 66 33 CB 39 88 3A "
            "35 43 34 33 44 B4 68 B4 93 39 33 9F 16")

parser = DLT645Parser()

# ======================================================================
print("[1] 读取帧（11H，数据域只有 DI）")
# ======================================================================
req = parser.parse(bytes.fromhex(REQ_HEX.replace(" ", "")))
check("CS 校验通过", req["checksum_valid"] is True,
      (req["checksum"], req["checksum_expected"]))
check("DI = FFAA0001", req["di_code"] == "FFAA0001", req["di_code"])
check("DI 名称来自扩展表", "入网信息" in req["di_desc"], req["di_desc"])
check("控制码识别为读数据请求",
      req["control"] == 0x11 and "读数据" in req["control_desc"], req["control_desc"])
req_fields = fields_of(req)
check("请求帧给出「仅数据标识、无数据域」提示",
      any("请求帧" in v[1] for k, v in req_fields.items() if k.startswith("  └ 入网信息")),
      req_fields.get("  └ 入网信息"))
check("请求帧不编造字段值", "  └ 入网状态" not in req_fields, list(req_fields))

# ======================================================================
print("[2] 应答帧（91H，L=16H=22 字节）逐字段")
# ======================================================================
resp = parser.parse(bytes.fromhex(RESP_HEX.replace(" ", "")))
check("CS 校验通过", resp["checksum_valid"] is True,
      (resp["checksum"], resp["checksum_expected"]))
check("数据长度 22", resp["data_length"] == 22, resp["data_length"])
check("DI = FFAA0001", resp["di_code"] == "FFAA0001", resp["di_code"])
check("DI 名称", "入网信息" in resp["di_desc"], resp["di_desc"])
check("控制码 91H（从站应答/读数据应答）",
      resp["control"] == 0x91 and "从站应答" in resp["control_desc"],
      resp["control_desc"])
check("从站地址 075506980033", resp["address"] == "075506980033", resp["address"])

f = fields_of(resp)
check("入网状态 = 1（已入网）", "已入网" in f["  └ 入网状态"][1], f["  └ 入网状态"])
check("STA 地址 = 07 55 06 98 00 33",
      f["  └ STA 地址"][1] == "07 55 06 98 00 33", f["  └ STA 地址"])
check("本节点 TEI = 2（0x1002 取低 12bit）",
      "TEI=2" in f["  └ 本节点 TEI"][1] and "0x1002" in f["  └ 本节点 TEI"][1],
      f["  └ 本节点 TEI"])
check("本节点 TEI 高 4bit = 1 → 无告警行", "  └ ⚠ 本节点 TEI 高4bit" not in f, list(f))
check("代理节点 TEI = 1（0x0001）",
      "TEI=1" in f["  └ 代理节点 TEI"][1], f["  └ 代理节点 TEI"])
check("入网通道=载波 / 角色=末端节点 / 层级=1",
      "载波" in f["  └ 入网通道/角色/层级"][1]
      and "末端节点" in f["  └ 入网通道/角色/层级"][1]
      and "层级=1" in f["  └ 入网通道/角色/层级"][1],
      f["  └ 入网通道/角色/层级"])
check("入网 CCO 地址 = 00 06 60 81 35 81",
      f["  └ 入网 CCO 地址"][1] == "00 06 60 81 35 81", f["  └ 入网 CCO 地址"])
check("保留原始数据域备查（减33H后）",
      f.get("数据内容(原始)", ("", ""))[0] == "013300980655070210010011813581600600",
      f.get("数据内容(原始)"))

# ======================================================================
print("[3] 边界：通道/角色取值、高 4bit 异常、长度不足、多余字节")
# ======================================================================
check("角色 2 → 代理节点", ext.JOIN_ROLE_TEXT[2] == "代理节点")
check("入网状态表完整", ext.JOIN_STATE_TEXT == {0: "未入网", 1: "已入网", 2: "离网"},
      ext.JOIN_STATE_TEXT)

# 直接调扩展模块：body = 状态 + STA + 本TEI + 代TEI + flag + CCO
body = (bytes([2])                          # 离网
        + bytes.fromhex("332211005566")     # STA（低位在前）
        + bytes.fromhex("02 30")            # 本节点 TEI：0x3002（高 4bit=3，异常）
        + bytes.fromhex("05 40")            # 代理 TEI：0x4005（高 4bit=4）
        + bytes([0x91])                      # 无线 + 角色 1 + 层级 1
        + bytes.fromhex("010203040506"))
rows, name = ext.parse_net_info("FFAA0001", 0x91, b"\x01\x00\xAA\xFF" + body)
row_map = {r[0]: r for r in rows}
check("离网状态解析", "离网" in row_map["  └ 入网状态"][2], row_map["  └ 入网状态"])
check("本节点 TEI 高 4bit≠1 时给出告警行",
      "  └ ⚠ 本节点 TEI 高4bit" in row_map, list(row_map))
check("告警行写明协议规定值",
      "应为 1" in row_map["  └ ⚠ 本节点 TEI 高4bit"][3],
      row_map["  └ ⚠ 本节点 TEI 高4bit"])
check("无线通道识别", "无线" in row_map["  └ 入网通道/角色/层级"][2],
      row_map["  └ 入网通道/角色/层级"])

short_body = bytes([1]) + bytes(6) + bytes(2)     # 只有 9 字节
rows_short, _ = ext.parse_net_info("FFAA0001", 0x91, b"\x01\x00\xAA\xFF" + short_body)
short_map = {r[0]: r for r in rows_short}
check("长度不足给出告警", "  └ ⚠ 数据域不足" in short_map, list(short_map))
check("缺项字段标「（缺）」",
      short_map.get("  └ 代理节点 TEI", ("", ""))[1] in ("", "（缺）")
      or any("缺" in str(v) for v in short_map.get("  └ 代理节点 TEI", ("", ""))),
      short_map.get("  └ 代理节点 TEI"))

long_body = body + b"\xAA\xBB"
rows_long, _ = ext.parse_net_info("FFAA0001", 0x91, b"\x01\x00\xAA\xFF" + long_body)
long_map = {r[0]: r for r in rows_long}
check("多余字节单独列出", "  └ 多余字节" in long_map, list(long_map))

# 非 BCD 地址：0x0F 这种半字节 >9
bad_addr_body = bytes([1]) + bytes([0x0F] * 6) + bytes(9)
rows_bad, _ = ext.parse_net_info("FFAA0001", 0x91, b"\x01\x00\xAA\xFF" + bad_addr_body)
bad_map = {r[0]: r for r in rows_bad}
check("非 BCD 地址标「（BCD 非法）」",
      "BCD 非法" in bad_map["  └ STA 地址"][2], bad_map["  └ STA 地址"])

check("空数据域（无 DI 后内容）不崩",
      ext.parse_net_info("FFAA0001", 0x11, b"")[0][0][0].startswith("  └ 入网信息"))
check("非本 DI 直接返回空", ext.parse_net_info("00010000", 0x91, b"\x00" * 22) == ([], ""))
check("is_net_info_di 大小写不敏感", ext.is_net_info_di("ffaa0001") is True)

# ======================================================================
print("[4] DI 表并入（解析器 + 查询页同一来源）")
# ======================================================================
merged = ext.merge_net_info_di_map({"00010000": {"name": "x"}})
check("并入后保留原条目", "00010000" in merged, list(merged))
check("并入后新增 FFAA0001", ext.DI_NET_JOIN_INFO in merged, list(merged))
check("并入不修改入参", "FFAA0001" not in {"00010000": {}}, "ok")

parser_map = DLT645Parser._load_di_map()
check("解析器 DI 表含 FFAA0001", "FFAA0001" in parser_map, "缺失")
check("解析器 DI 表仍含标准 DI", "00010000" in parser_map, "标准 DI 丢了")
from dlt645_di_lookup import get_dlt645_di_lookup  # noqa: E402

lookup = get_dlt645_di_lookup()
check("查询页能查到 FFAA0001",
      (lookup.get_di_info("FFAA0001") or {}).get("name", "").startswith("入网信息"),
      lookup.get_di_info("FFAA0001"))
check("查询页搜索「入网」命中",
      any(item[0] == "FFAA0001" for item in lookup.search("入网")),
      [i[0] for i in lookup.search("入网")][:5])

# ======================================================================
print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败：")
    for item in FAILED:
        print("   -", item)
    sys.exit(1)
print("✅ 全部通过")
