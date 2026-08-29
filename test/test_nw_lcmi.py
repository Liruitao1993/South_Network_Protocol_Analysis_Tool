# -*- coding: utf-8 -*-
"""南网本地通信模块接口协议（文档13）完善回归测试。

覆盖：
1. 新增 15 个 DI 的解析断言（手工构造帧 -> parse）
2. 新增 8 个下行 DI 组帧 round-trip（ProtocolFrameGenerator.generate_frame -> 解析器回读）
3. 4 处文档冲突修正的双格式用例（新文档格式 + PLUZ 旧格式）
4. NW_command.json 14 条预设帧解析不回归

运行：python test/test_nw_lcmi.py（退出码 0 即通过）
"""

import _path_setup  # noqa: E402

import io
import json
import sys

from protocol_parser import ProtocolFrameParser
from send_frame_lib import ProtocolFrameGenerator

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def build_nw_frame(control: int, user_data: bytes) -> bytes:
    """手工构造南网 FT1.2 帧：68 + L(2B小端) + C + 用户数据 + CS + 16

    L = 用户数据长度 + 6；CS = 控制域 + 用户数据 的算术和（mod 256）
    """
    length = len(user_data) + 6
    cs = (control + sum(user_data)) & 0xFF
    return (bytes([0x68]) + length.to_bytes(2, 'little') + bytes([control])
            + user_data + bytes([cs, 0x16]))


def build_user_data(di_key, content: bytes) -> bytes:
    """构造无地址域的用户数据区：AFN + SEQ + DI(小端) + 数据内容"""
    di3, di2, di1, di0 = di_key
    return bytes([di1, 0x00]) + bytes([di0, di1, di2, di3]) + content


def parse_content(parser, di_key, content: bytes) -> dict:
    """构造帧并解析，返回数据标识内容 dict（解析失败时返回空 dict）"""
    frame = build_nw_frame(0x00, build_user_data(di_key, content))
    result = parser.parse(frame)
    if result.get("解析状态") != "成功":
        return {"__失败__": result.get("错误信息")}
    return result["用户数据区"].get("数据标识内容", {})


def parse_full(parser, di_key, content: bytes) -> dict:
    """构造帧并解析，返回完整解析结果"""
    frame = build_nw_frame(0x00, build_user_data(di_key, content))
    return parser.parse(frame)


# ==================== 1. 新增 15 个 DI 解析 ====================

def test_new_di_parsers():
    print("== 新增 15 个 DI 解析 ==")
    parser = ProtocolFrameParser()
    addr1 = bytes.fromhex("112233445566")
    addr2 = bytes.fromhex("AABBCCDDEEFF")

    # 1) E8 02 04 A0 设置即插即用功能开关：开关 2B BIN 小端
    c = parse_content(parser, (0xE8, 0x02, 0x04, 0xA0), bytes.fromhex("0100"))
    check("A0设置即插即用 开关=1 开启",
          c.get("即插即用功能开关", {}).get("十进制") == 1
          and c.get("即插即用功能开关", {}).get("说明") == "开启", str(c))

    # 2) E8 02 04 A1 添加黑名单节点：n 1B + 地址 6B*n
    c = parse_content(parser, (0xE8, 0x02, 0x04, 0xA1), bytes([2]) + addr1 + addr2)
    check("A1添加黑名单 数量=2", c.get("黑名单节点数量", {}).get("十进制") == 2, str(c))
    lst = c.get("黑名单节点列表", [])
    check("A1添加黑名单 地址反转显示",
          len(lst) == 2 and lst[0]["黑名单节点地址"]["解析值"] == addr1[::-1].hex().upper(), str(lst))

    # 3) E8 02 04 A2 删除黑名单节点：n 1B + 地址 6B*n
    c = parse_content(parser, (0xE8, 0x02, 0x04, 0xA2), bytes([1]) + addr1)
    check("A2删除黑名单 数量=1", c.get("黑名单节点数量", {}).get("十进制") == 1, str(c))
    check("A2删除黑名单 地址解析",
          c.get("黑名单节点列表", [{}])[0].get("黑名单节点地址", {}).get("原始值") == addr1.hex().upper(), str(c))

    # 4) E8 02 04 A3 设置CCO时钟：BCD 6B 秒分时日月年
    c = parse_content(parser, (0xE8, 0x02, 0x04, 0xA3), bytes.fromhex("305912260825"))
    check("A3设置CCO时钟 时间串", c.get("时间") == "2025-08-26 12:59:30", str(c))
    check("A3设置CCO时钟 秒BCD", c.get("当前时间-秒", {}).get("BCD") == "30", str(c))

    # 5) E8 03 03 15 批量查询模块特征信息：起始序号 2B + 数量 1B
    c = parse_content(parser, (0xE8, 0x03, 0x03, 0x15), bytes.fromhex("05000A"))
    check("15批量查询模块特征 起始序号=5", c.get("节点起始序号", {}).get("十进制") == 5, str(c))
    check("15批量查询模块特征 数量=10", c.get("节点数量", {}).get("十进制") == 10, str(c))

    # 6) E8 03 03 16 查询指定模块特征信息：n 1B + 地址 6B*n
    c = parse_content(parser, (0xE8, 0x03, 0x03, 0x16), bytes([2]) + addr1 + addr2)
    check("16查询指定模块特征 数量=2", c.get("本次查询从节点数量", {}).get("十进制") == 2, str(c))
    check("16查询指定模块特征 地址列表",
          len(c.get("从节点地址列表", [])) == 2
          and c["从节点地址列表"][1]["从节点地址"]["解析值"] == addr2[::-1].hex().upper(), str(c))

    # 7) E8 03 03 A0 查询即插即用功能开关：无数据内容
    r = parse_full(parser, (0xE8, 0x03, 0x03, 0xA0), b"")
    check("A0查询即插即用 DI名称",
          r["用户数据区"]["数据标识(DI)"]["业务说明"] == "查询即插即用功能开关", str(r.get("错误信息")))
    check("A0查询即插即用 无内容", "数据标识内容" not in r["用户数据区"], "")

    # 8) E8 03 03 A1 查询黑名单节点信息：起始序号 2B + 数量 1B
    c = parse_content(parser, (0xE8, 0x03, 0x03, 0xA1), bytes.fromhex("010005"))
    check("A1查询黑名单 起始序号=1", c.get("从节点起始序号", {}).get("十进制") == 1, str(c))
    check("A1查询黑名单 数量=5", c.get("从节点数量", {}).get("十进制") == 5, str(c))

    # 9) E8 04 03 15 批量返回模块特征信息：总数 2B + n 1B + n*(地址6B + 特征8B)
    feature = bytes(7) + bytes([0x03])  # D1=载波多帧支持=1, D0=数据有效=1
    content = bytes.fromhex("0300") + bytes([1]) + addr1 + feature
    c = parse_content(parser, (0xE8, 0x04, 0x03, 0x15), content)
    check("15批量返回模块特征 总数量=3", c.get("节点总数量", {}).get("十进制") == 3, str(c))
    check("15批量返回模块特征 应答数量=1", c.get("本次应答的节点数量", {}).get("十进制") == 1, str(c))
    nodes = c.get("节点列表", [])
    check("15批量返回模块特征 载波多帧支持",
          len(nodes) == 1 and nodes[0]["模块特征信息"]["载波多帧支持"] == "支持", str(nodes))
    check("15批量返回模块特征 数据有效",
          nodes and nodes[0]["模块特征信息"]["数据有效标志"] == "数据有效", str(nodes))

    # 10) E8 04 03 16 返回指定模块特征信息：n 1B + n*(地址6B + 特征8B)
    feature_off = bytes(7) + bytes([0x00])  # 不支持且离线
    c = parse_content(parser, (0xE8, 0x04, 0x03, 0x16), bytes([1]) + addr1 + feature_off)
    check("16返回指定模块特征 应答数量=1", c.get("本次应答的节点数量", {}).get("十进制") == 1, str(c))
    nodes = c.get("节点列表", [])
    check("16返回指定模块特征 离线判定",
          nodes and nodes[0]["模块特征信息"]["数据有效标志"] == "节点离线，数据无效", str(nodes))

    # 11) E8 04 03 A0 返回即插即用功能开关：2B BIN 小端
    c = parse_content(parser, (0xE8, 0x04, 0x03, 0xA0), bytes.fromhex("0000"))
    check("A0返回即插即用 开关=0 关闭",
          c.get("即采功能开关", {}).get("十进制") == 0
          and c.get("即采功能开关", {}).get("说明") == "关闭即插即用功能", str(c))

    # 12) E8 04 03 A1 返回黑名单节点信息：总数 2B + n 1B + 地址 6B*n
    c = parse_content(parser, (0xE8, 0x04, 0x03, 0xA1), bytes.fromhex("0200") + bytes([2]) + addr1 + addr2)
    check("A1返回黑名单 总数量=2", c.get("黑名单节点总数量", {}).get("十进制") == 2, str(c))
    check("A1返回黑名单 列表2项",
          len(c.get("黑名单节点列表", [])) == 2
          and c["黑名单节点列表"][1]["黑名单节点地址"]["解析值"] == addr2[::-1].hex().upper(), str(c))

    # 13) E8 05 05 A0 上报未识别节点信息：n 1B + 地址 6B*n
    c = parse_content(parser, (0xE8, 0x05, 0x05, 0xA0), bytes([1]) + addr1)
    check("A0上报未识别节点 数量=1", c.get("上报未识别节点数量", {}).get("十进制") == 1, str(c))
    check("A0上报未识别节点 地址",
          c.get("未识别节点列表", [{}])[0].get("未识别节点地址", {}).get("解析值") == addr1[::-1].hex().upper(), str(c))

    # 14) E8 05 05 11 上报组合多帧任务数据：任务ID 2B + 报文长度 2B + 组合内容
    # 组合内容 = [长度2B头 + 内容] x 2：02 00 AA BB + 02 00 CC DD
    combined = bytes.fromhex("0200AABB0200CCDD")
    content = bytes.fromhex("0100") + len(combined).to_bytes(2, 'little') + combined
    c = parse_content(parser, (0xE8, 0x05, 0x05, 0x11), content)
    check("11上报组合多帧 任务ID=1", c.get("任务ID", {}).get("十进制") == 1, str(c))
    check("11上报组合多帧 报文长度2B=8", c.get("报文长度", {}).get("十进制") == 8, str(c))
    subs = c.get("组合多帧列表", [])
    check("11上报组合多帧 子帧2项",
          len(subs) == 2 and subs[0]["报文内容"] == "AABB" and subs[1]["报文内容"] == "CCDD", str(subs))

    # 15) E8 05 05 12 上报从节点事件扩展：报文长度 2B + 内容
    c = parse_content(parser, (0xE8, 0x05, 0x05, 0x12), bytes.fromhex("0300") + bytes.fromhex("112233"))
    check("12上报从节点事件扩展 长度=3", c.get("报文长度", {}).get("十进制") == 3, str(c))
    check("12上报从节点事件扩展 内容", c.get("报文内容") == "112233", str(c))

    # 容错：数据不足仍给出提示而非空白
    c = parse_content(parser, (0xE8, 0x02, 0x04, 0xA0), bytes.fromhex("01"))
    check("A0设置即插即用 容错长度不足", "说明" in c and "原始数据" in c, str(c))


# ==================== 2. 组帧 round-trip（8 个下行 DI）====================

def test_frame_gen_round_trip():
    print("== 组帧 round-trip（8 个下行 DI）==")
    parser = ProtocolFrameParser()
    gen = ProtocolFrameGenerator()
    src = bytes.fromhex("010203040506")
    dst = bytes.fromhex("000000000000")

    def gen_and_parse(di_key, values):
        frame = gen.generate_frame(di_key, values, src_addr=src, dst_addr=dst,
                                   dir_flag=0, prm=1, add_flag=1)
        r = parser.parse(frame)
        return frame, r

    # 1) E8 02 04 A0 设置即插即用功能开关
    frame, r = gen_and_parse((0xE8, 0x02, 0x04, 0xA0), {"即插即用功能开关": 1})
    c = r["用户数据区"].get("数据标识内容", {})
    check("组帧 A0设置即插即用 DI名称",
          r["用户数据区"]["数据标识(DI)"]["业务说明"] == "设置即插即用功能开关", str(r.get("错误信息")))
    check("组帧 A0设置即插即用 回读=1", c.get("即插即用功能开关", {}).get("十进制") == 1,
          f"frame={frame.hex()} c={c}")

    # 2) E8 02 04 A1 添加黑名单节点（count_field 自动计数）
    values = {"黑名单节点列表": [{"黑名单节点地址": "112233445566"}, {"黑名单节点地址": "AABBCCDDEEFF"}]}
    frame, r = gen_and_parse((0xE8, 0x02, 0x04, 0xA1), values)
    c = r["用户数据区"].get("数据标识内容", {})
    check("组帧 A1添加黑名单 数量自动=2", c.get("黑名单节点数量", {}).get("十进制") == 2,
          f"frame={frame.hex()} c={c}")
    check("组帧 A1添加黑名单 地址回读",
          len(c.get("黑名单节点列表", [])) == 2
          and c["黑名单节点列表"][0]["黑名单节点地址"]["解析值"] == "112233445566"
          and c["黑名单节点列表"][1]["黑名单节点地址"]["解析值"] == "AABBCCDDEEFF", str(c))

    # 3) E8 02 04 A2 删除黑名单节点
    frame, r = gen_and_parse((0xE8, 0x02, 0x04, 0xA2),
                             {"黑名单节点列表": [{"黑名单节点地址": "001122334455"}]})
    c = r["用户数据区"].get("数据标识内容", {})
    check("组帧 A2删除黑名单 回读",
          c.get("黑名单节点数量", {}).get("十进制") == 1
          and c.get("黑名单节点列表", [{}])[0].get("黑名单节点地址", {}).get("解析值") == "001122334455",
          f"frame={frame.hex()} c={c}")

    # 4) E8 02 04 A3 设置CCO时钟（BCD 6B）
    values = {"当前时间-秒": "30", "当前时间-分": "59", "当前时间-时": "12",
              "当前时间-日": "26", "当前时间-月": "08", "当前时间-年": "25"}
    frame, r = gen_and_parse((0xE8, 0x02, 0x04, 0xA3), values)
    c = r["用户数据区"].get("数据标识内容", {})
    check("组帧 A3设置CCO时钟 时间回读", c.get("时间") == "2025-08-26 12:59:30",
          f"frame={frame.hex()} c={c}")

    # 5) E8 03 03 15 批量查询模块特征信息
    frame, r = gen_and_parse((0xE8, 0x03, 0x03, 0x15), {"节点起始序号": 3, "节点数量": 4})
    c = r["用户数据区"].get("数据标识内容", {})
    check("组帧 15批量查询模块特征 回读",
          c.get("节点起始序号", {}).get("十进制") == 3 and c.get("节点数量", {}).get("十进制") == 4,
          f"frame={frame.hex()} c={c}")

    # 6) E8 03 03 16 查询指定模块特征信息（count_field 自动计数）
    frame, r = gen_and_parse((0xE8, 0x03, 0x03, 0x16),
                             {"从节点地址列表": [{"从节点地址": "001122334455"}]})
    c = r["用户数据区"].get("数据标识内容", {})
    check("组帧 16查询指定模块特征 回读",
          c.get("本次查询从节点数量", {}).get("十进制") == 1
          and c.get("从节点地址列表", [{}])[0].get("从节点地址", {}).get("解析值") == "001122334455",
          f"frame={frame.hex()} c={c}")

    # 7) E8 03 03 A0 查询即插即用功能开关（无字段）
    frame, r = gen_and_parse((0xE8, 0x03, 0x03, 0xA0), {})
    check("组帧 A0查询即插即用 成功且DI名称",
          r.get("解析状态") == "成功"
          and r["用户数据区"]["数据标识(DI)"]["业务说明"] == "查询即插即用功能开关",
          f"frame={frame.hex()} err={r.get('错误信息')}")
    check("组帧 A0查询即插即用 校验和通过", r["校验和"]["校验结果"] == "通过", str(r.get("校验和")))

    # 8) E8 03 03 A1 查询黑名单节点信息
    frame, r = gen_and_parse((0xE8, 0x03, 0x03, 0xA1), {"从节点起始序号": 0, "从节点数量": 2})
    c = r["用户数据区"].get("数据标识内容", {})
    check("组帧 A1查询黑名单 回读",
          c.get("从节点起始序号", {}).get("十进制") == 0 and c.get("从节点数量", {}).get("十进制") == 2,
          f"frame={frame.hex()} c={c}")

    # 组帧公共断言：帧结构完整（68 开头 16 结尾，校验通过，源地址回读）
    check("组帧 帧结构 源地址回读",
          r["用户数据区"]["地址域"]["源地址"]["解析值"] == "010203040506", str(r["用户数据区"].get("地址域")))


# ==================== 3. 文档冲突修正（双格式兼容）====================

def test_conflict_fixes():
    print("== 文档冲突修正（双格式兼容）==")
    parser = ProtocolFrameParser()

    # 冲突1：返回未完成任务列表（E8 04 02 04）
    # 新文档格式：数量 2B + ID 2B*n（2+2n == 总长）
    new_fmt = bytes.fromhex("0200") + bytes.fromhex("0A00") + bytes.fromhex("1400")
    c = parse_content(parser, (0xE8, 0x04, 0x02, 0x04), new_fmt)
    check("冲突1 新格式 数量=2", c.get("本次上报的任务数量", {}).get("十进制") == 2, str(c))
    check("冲突1 新格式 任务ID回读",
          [t["任务ID"]["十进制"] for t in c.get("任务列表", [])] == [10, 20], str(c))
    # PLUZ 旧格式：总数 2B + 返回数 1B + ID 2B*n（回退）
    pluz_fmt = bytes.fromhex("0500") + bytes([2]) + bytes.fromhex("0A00") + bytes.fromhex("1400")
    c = parse_content(parser, (0xE8, 0x04, 0x02, 0x04), pluz_fmt)
    check("冲突1 PLUZ格式 总任务数=5", c.get("总任务数", {}).get("十进制") == 5, str(c))
    check("冲突1 PLUZ格式 返回任务数=2", c.get("返回任务数", {}).get("十进制") == 2, str(c))

    # 冲突2：添加多播任务（E8 02 02 07）D4=1 时报文长度 2B
    # 新格式：任务ID(2B) + 模式字0x10(D4=1) + 数量0xFFFF + 超时(2B) + 长度(2B) + 内容
    new_mcast = bytes.fromhex("0100") + bytes([0x10]) + bytes.fromhex("FFFF") \
        + bytes.fromhex("1E00") + bytes.fromhex("0200") + bytes.fromhex("AABB")
    c = parse_content(parser, (0xE8, 0x02, 0x02, 0x07), new_mcast)
    check("冲突2 多播D4=1 长度2B=2", c.get("报文长度", {}).get("十进制") == 2, str(c))
    check("冲突2 多播D4=1 内容", c.get("报文内容") == "AABB", str(c))
    check("冲突2 多播D4=1 组合多帧标志",
          c.get("任务模式字", {}).get("组合多帧标志") == "组合多帧任务数据", str(c.get("任务模式字")))
    # PLUZ 旧格式：模式字 0x00，报文长度 1B
    pluz_mcast = bytes.fromhex("0100") + bytes([0x00]) + bytes.fromhex("FFFF") \
        + bytes.fromhex("1E00") + bytes([2]) + bytes.fromhex("AABB")
    c = parse_content(parser, (0xE8, 0x02, 0x02, 0x07), pluz_mcast)
    check("冲突2 多播D4=0 长度1B=2", c.get("报文长度", {}).get("十进制") == 2, str(c))
    check("冲突2 多播D4=0 内容不变", c.get("报文内容") == "AABB", str(c))

    # 冲突3：启动/暂停任务（E8 02 02 08/09）空数据不生成字段行，>=2B 仍解析任务ID
    check("冲突3 启动任务 空数据无字段行",
          parser._parse_start_task_data(b"") == {"说明": "启动任务命令，无数据内容"}, "")
    check("冲突3 暂停任务 空数据无字段行",
          parser._parse_pause_task_data(b"") == {"说明": "暂停任务命令，无数据内容"}, "")
    check("冲突3 启动任务 PLUZ任务ID兼容",
          parser._parse_start_task_data(bytes.fromhex("0100")).get("任务ID", {}).get("十进制") == 1, "")
    check("冲突3 暂停任务 1字节容错",
          "说明" in parser._parse_pause_task_data(bytes([0x01])), "")
    # 完整帧级别：启动任务带任务ID
    c = parse_content(parser, (0xE8, 0x02, 0x02, 0x08), bytes.fromhex("0200"))
    check("冲突3 启动任务帧 任务ID=2", c.get("任务ID", {}).get("十进制") == 2, str(c))

    # 冲突4：任务模式字位定义（E8 02 02 01 添加任务）
    # 模式字 0x91 = D7响应=1 + D4组合多帧=1 + 优先级1；南网1字节报文长度
    add_task = bytes.fromhex("0100") + bytes([0x91]) + bytes.fromhex("1E00") + bytes([1]) + bytes([0xAA])
    c = parse_content(parser, (0xE8, 0x02, 0x02, 0x01), add_task)
    mode = c.get("任务模式字", {})
    check("冲突4 组合多帧标志显示", mode.get("组合多帧标志") == "组合多帧任务数据", str(mode))
    check("冲突4 优先级数值不变", str(mode.get("任务优先级", "")).startswith("1"), str(mode))
    check("冲突4 优先级D3~D0注释", "D3~D0" in str(mode.get("说明", "")), str(mode))
    # 模式字 0x40 = D6转发标识（PLUZ扩展）
    add_task_fwd = bytes.fromhex("0100") + bytes([0x40]) + bytes.fromhex("1E00") + bytes([1]) + bytes([0x00])
    c = parse_content(parser, (0xE8, 0x02, 0x02, 0x01), add_task_fwd)
    check("冲突4 转发标识PLUZ扩展标注",
          "PLUZ扩展" in str(c.get("任务模式字", {}).get("转发标识", "")), str(c.get("任务模式字")))


# ==================== 4. NW_command.json 预设帧回归 ====================

def test_preset_regression():
    print("== NW_command.json 预设帧回归 ==")
    with io.open("NW_command.json", encoding="utf-8") as f:
        commands = json.load(f)["commands"]
    check("预设帧数量=14", len(commands) == 14, f"len={len(commands)}")

    parser = ProtocolFrameParser()
    ok = 0
    for i, cmd in enumerate(commands):
        frame_hex = cmd.get("frame_hex", "")
        frame = bytes.fromhex(frame_hex.replace(" ", ""))
        r = parser.parse(frame)
        if r.get("解析状态") == "成功" and r.get("校验和", {}).get("校验结果") == "通过":
            ok += 1
        else:
            print(f"  [回归] 第{i+1}条 {frame_hex} -> {r.get('错误信息')}")
    check("预设帧全部解析成功且校验通过", ok == len(commands), f"{ok}/{len(commands)}")


if __name__ == "__main__":
    test_new_di_parsers()
    test_frame_gen_round_trip()
    test_conflict_fixes()
    test_preset_regression()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)
