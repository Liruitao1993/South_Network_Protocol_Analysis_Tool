"""国网协议7 福建增补规约 + 本地通信模块扩展协议（EB 数据标识）测试

覆盖：
- 福建增补帧识别（AFN 50H~56H）
- 各 AFN/Fn 数据单元解析（附件3：1376.2集中器本地通信模块接口协议【福建增补】）
- EB 数据标识深度解析（附件1：本地通信模块扩展协议 V3.31）
- 福建增补组帧 + 回读
- 校验器支持
- 2024 国网帧回归

运行：python test/test_gdw_fujian.py
"""

import _path_setup  # noqa: E402

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gdw10376_parser import GDW10376Parser  # noqa: E402
from gdw_send_frame_lib import GDWFrameGenerator  # noqa: E402
from gdw_eb_di_lookup import get_eb_di_lookup  # noqa: E402
from validator.gdw_validator import GDWValidator  # noqa: E402


def make_fujian_frame(afn, fn, data_bytes, src="000000000001", dst="001122334455", seq=0, dir_val=0):
    """构造福建增补帧: 68 L C R(6B) A1(6B) A3(6B) AFN DT1 DT2 data CS 16

    fn 为信息类编号（1~248），自动转换为 DT1/DT2。
    """
    # Fn -> DT1/DT2: Fn=(DT2*8)+位号
    fn = fn - 1
    dt1 = 1 << (fn % 8)
    dt2 = fn // 8
    R = bytes([0x00] * 5 + [seq])
    A1 = bytes.fromhex(src)
    A3 = bytes.fromhex(dst)
    C = (dir_val << 7) | (1 << 6)  # DIR + PRM=1
    user = R + A1 + A3 + bytes([afn, dt1, dt2]) + data_bytes
    L = len(user) + 6
    body = bytes([C]) + user
    cs = sum(body) & 0xFF
    return bytes([0x68]) + L.to_bytes(2, 'little') + body + bytes([cs, 0x16])


def make_645_frame(ctrl, di_bytes, data_bytes, addr="001122334455"):
    """构造 645 帧: 68 A0..A5 68 控制码 L DATA CS 16"""
    body = bytes([ctrl, len(di_bytes) + len(data_bytes)]) + di_bytes + data_bytes
    cs = sum(body) & 0xFF
    return bytes([0x68]) + bytes.fromhex(addr) + bytes([0x68]) + body + bytes([cs, 0x16])


def row_values(rows, name_contains):
    """按字段名子串查找解析结果行"""
    return [r for r in rows if name_contains in str(r[0])]


def test_eb_v342_deep_parse():
    """V3.42 新增 EB 数据标识深度解析（信号质量/测距/NTB校时698）"""
    parser = GDW10376Parser()
    # EB030313 周边节点质量_本台区
    rows = []
    parser._parse_eb_di("EB030313", bytes([0x01]) + bytes.fromhex("001122334455") + bytes([90, 80, 70, 85, 75, 65]), 0, rows)
    assert any("节点1载波上下行通信成功率" in str(r[0]) for r in rows), "EB030313 未解析"
    assert any("90%" in str(r) for r in rows), "EB030313 成功率错误"
    # EB030314 周边节点质量_非本台区
    rows = []
    parser._parse_eb_di("EB030314", bytes([0x01]) + bytes.fromhex("A1A2A3") + bytes.fromhex("0102") + bytes([80, 70, 75, 65]), 0, rows)
    assert any("节点1SNID" in str(r[0]) for r in rows), "EB030314 未解析"
    assert any("节点1TEI" in str(r[0]) for r in rows), "EB030314 TEI 未解析"
    # EB030320 启动通信测距
    rows = []
    parser._parse_eb_di("EB030320", bytes([0x01, 0x1E, 0x01, 0x01]) + bytes.fromhex("001122334455"), 0, rows)
    assert any("测距类型" in str(r[0]) for r in rows), "EB030320 未解析"
    assert any("能直接侦听到的节点" in str(r) for r in rows), "EB030320 测距类型错误"
    # EB030321 测距结果
    rows = []
    data = bytes.fromhex("260825101530") + bytes.fromhex("260825101545") + (1).to_bytes(2, 'little') + bytes([0x01]) + bytes.fromhex("001122334455") + (1000).to_bytes(2, 'little') + (2000).to_bytes(2, 'little')
    parser._parse_eb_di("EB030321", data, 0, rows)
    assert any("结果1载波测距值" in str(r[0]) for r in rows), "EB030321 未解析"
    assert any("1000ns" in str(r) for r in rows), "EB030321 载波测距值错误"
    # EB030506 NTB校时_698方式
    rows = []
    parser._parse_eb_di("EB030506", bytes([0x1C]) + bytes.fromhex("20260825101530") + (400000).to_bytes(4, 'little'), 0, rows)
    assert any("2026-08-25 10:15:30" in str(r) for r in rows), "EB030506 时间错误"
    assert any("400000" in str(r) for r in rows), "EB030506 NTB 错误"
    # EB030520 新枚举值
    from gdw_eb_di_lookup import get_eb_di_lookup
    info = get_eb_di_lookup().get("EB030520")
    assert info and "698" in info["功能"], "EB030520 映射未更新"
    # EBEEEEEE 取消标记
    info = get_eb_di_lookup().get("EBEEEEEE")
    assert info and "取消" in info["名称"], "EBEEEEEE 取消标记缺失"
    print("PASS test_eb_v342_deep_parse")


def test_fujian_frame_identification():
    """福建增补帧识别：AFN=52H 信息域为保留+序列号结构，地址域 A1+A3"""
    parser = GDW10376Parser()
    data = bytes([0x01]) + bytes.fromhex("001122334455") + bytes([0, 1, 10]) + (0).to_bytes(2, 'little') + b''
    frame = make_fujian_frame(0x52, 1, data)
    rows = parser.parse_to_table(frame)
    # 信息域应按福建增补解析（保留+序列号）
    reserves = row_values(rows, "保留")
    assert len(reserves) >= 5, f"福建增补信息域应有保留字段, 实际: {len(reserves)}"
    # 地址域 A1+A3
    addr_rows = row_values(rows, "源地址(A1)")
    assert len(addr_rows) == 1, "福建增补帧应有源地址A1"
    dst_rows = row_values(rows, "目的地址(A3)")
    assert len(dst_rows) == 1, "福建增补帧应有目的地址A3"
    # AFN 识别
    afn_rows = row_values(rows, "应用功能码(AFN)")
    assert afn_rows and "数据转发（福建增补）" in afn_rows[0][3], f"AFN名称错误: {afn_rows}"
    print("PASS test_fujian_frame_identification")


def test_afn50_confirm_deny():
    """AFN=50H F1 确认 / F2 否认"""
    parser = GDW10376Parser()
    # F1 确认（上行，无数据单元）
    frame = make_fujian_frame(0x50, 1, b'', dir_val=1)
    rows = parser.parse_to_table(frame)
    assert any("确认" in str(r[0]) for r in rows), "AFN=50H F1 应识别为确认"
    # F2 否认（错误状态字）
    frame = make_fujian_frame(0x50, 2, bytes([0x0B]), dir_val=1)
    rows = parser.parse_to_table(frame)
    err_rows = row_values(rows, "错误状态字")
    assert err_rows and "从节点不应答" in err_rows[0][3], f"错误状态字解析错误: {err_rows}"
    print("PASS test_afn50_confirm_deny")


def test_afn52_f1_transparent_forward():
    """AFN=52H F1 透明转发通信协议数据帧（上行）"""
    parser = GDW10376Parser()
    # 上行 F1: 通信对象类型(1) + 通信对象地址(6) + 报文长度(2) + 报文内容
    eb_frame = make_645_frame(0x91, bytes.fromhex("EB040201"), bytes.fromhex("0005"))
    data = bytes([0x01]) + bytes.fromhex("001122334455") + len(eb_frame).to_bytes(2, 'little') + eb_frame
    frame = make_fujian_frame(0x52, 1, data, dir_val=1)
    rows = parser.parse_to_table(frame)
    assert any("转发通信协议数据帧" in str(r[3]) for r in rows), "AFN=52H F1 未识别"
    # 内嵌 645 EB 数据标识深度解析
    di_rows = row_values(rows, "数据标识")
    assert di_rows and "EB040201" in di_rows[0][1], f"未解析内嵌 EB 数据标识: {di_rows}"
    assert any("模块复位总次数" in str(r) for r in rows), "EB040201 名称未解析"
    print("PASS test_afn52_f1_transparent_forward")


def test_afn52_f2_task_queue():
    """AFN=52H F2 CCO任务队列_智能补采"""
    parser = GDW10376Parser()
    # 方案号(2) + 序号(2) + 对象类型(1) + 地址(6) + 规约类型(1) + 保留(1) + 长度(2) + 内容
    data = (1).to_bytes(2, 'little') + (1).to_bytes(2, 'little') + bytes([0x01]) + bytes.fromhex("001122334455") + bytes([0x02, 0x00]) + (4).to_bytes(2, 'little') + bytes.fromhex("68AABB")
    frame = make_fujian_frame(0x52, 2, data)
    rows = parser.parse_to_table(frame)
    assert any("任务方案号" in str(r[0]) for r in rows), "任务方案号未解析"
    assert any("具体任务序号" in str(r[0]) for r in rows), "具体任务序号未解析"
    proto_rows = row_values(rows, "规约类型")
    assert proto_rows and "DL/T 645-2007" in proto_rows[0][3], f"规约类型解析错误: {proto_rows}"
    print("PASS test_afn52_f2_task_queue")


def test_afn53_f4_vendor_info():
    """AFN=53H F4 厂商代码和版本信息（上行）"""
    parser = GDW10376Parser()
    # 通信对象类型(1) + 通信对象地址(6) + 厂商代码(2) + 芯片代码(2) + 日期(3) + 版本(2)
    data = bytes([0x01]) + bytes.fromhex("001122334455") + b"FJ" + b"IC" + bytes([0x15, 0x06, 0x24]) + bytes([0x13, 0x01])
    frame = make_fujian_frame(0x53, 4, data, dir_val=1)
    rows = parser.parse_to_table(frame)
    vendor_rows = row_values(rows, "厂商代码")
    assert vendor_rows and vendor_rows[0][2] == "FJ", f"厂商代码解析错误: {vendor_rows}"
    date_rows = row_values(rows, "版本日期")
    assert date_rows and "2024" in date_rows[0][2], f"版本日期解析错误: {date_rows}"
    print("PASS test_afn53_f4_vendor_info")


def test_afn53_f6_serial_params():
    """AFN=53H F6 本地通信模块串口当前通信参数（上行）"""
    parser = GDW10376Parser()
    # 当前速率(1) + 允许最高速率(1) + 自动恢复时长(2)
    data = bytes([0x06, 0x0A]) + (120).to_bytes(2, 'little')  # 9600bps + 115200bps + 120分钟
    frame = make_fujian_frame(0x53, 6, data, dir_val=1)
    rows = parser.parse_to_table(frame)
    rate_rows = row_values(rows, "串口当前通信速率")
    assert rate_rows and "9600" in rate_rows[0][2], f"当前速率解析错误: {rate_rows}"
    restore_rows = row_values(rows, "自动恢复默认速率时长")
    assert restore_rows and "120" in restore_rows[0][2], f"恢复时长解析错误: {restore_rows}"
    print("PASS test_afn53_f6_serial_params")


def test_afn55_f9_preannounce():
    """AFN=55H F9 预告抄读对象"""
    parser = GDW10376Parser()
    # 对象数量(2) + 延时修正标志(1) + n×[序号(2)+对象类型(1)+地址(6)]
    data = (1).to_bytes(2, 'little') + bytes([0x01]) + (1).to_bytes(2, 'little') + bytes([0x01]) + bytes.fromhex("001122334455")
    frame = make_fujian_frame(0x55, 9, data)
    rows = parser.parse_to_table(frame)
    assert any("本次预告对象数量" in str(r[0]) for r in rows), "预告对象数量未解析"
    assert any("预告对象1通信地址" in str(r[0]) for r in rows), "预告对象地址未解析"
    print("PASS test_afn55_f9_preannounce")


def test_afn56_f2_event_report():
    """AFN=56H F2 从节点主动上报事件内容（上行）"""
    parser = GDW10376Parser()
    # 通信对象类型(1) + 任务对象通信地址(6) + 主动上报报文长度(1) + 报文
    # 内嵌 645 停上电事件: 68 001122334455 68 81 0C EB030002 01 01 001122334455 CS 16
    di = bytes.fromhex("EB030002")
    data645 = bytes([0x01, 0x01]) + bytes.fromhex("001122334455")  # 停上电类型=上电 + 数量1 + 地址
    eb_frame = make_645_frame(0x81, di, data645)
    data = bytes([0x01]) + bytes.fromhex("001122334455") + bytes([len(eb_frame)]) + eb_frame
    frame = make_fujian_frame(0x56, 2, data, dir_val=1)
    rows = parser.parse_to_table(frame)
    di_rows = row_values(rows, "数据标识")
    assert di_rows and "EB030002" in di_rows[0][1], f"未解析 EB030002: {di_rows}"
    assert any("从节点模块停上电事件" in str(r) for r in rows), "EB030002 名称未解析"
    assert any("模块上电" in str(r) for r in rows), "停上电类型未解析"
    print("PASS test_afn56_f2_event_report")


def test_eb_di_lookup():
    """EB 数据标识查询"""
    lookup = get_eb_di_lookup()
    info = lookup.get("EB030110")
    assert info and "台区识别" in info["名称"], f"EB030110 查询失败: {info}"
    assert lookup.get_name("EB040201") == "模块复位总次数"
    # 搜索
    results = lookup.search("台区")
    assert any("EB0301" in k for k in results), "台区搜索失败"
    print("PASS test_eb_di_lookup")


def test_eb_deep_parse():
    """EB 数据标识深度解析（附件1 各数据项）"""
    parser = GDW10376Parser()
    # EB030110 台区识别任务启动: 方法(1) + 时长(2)
    rows = []
    parser._parse_eb_di("EB030110", bytes([0x01, 0x05, 0x00]), 0, rows)
    assert any("工频电压特征" in str(r) for r in rows), "台区识别方法未解析"
    # EB030501 模块时钟: YYMMDD hhmmss
    rows = []
    parser._parse_eb_di("EB030501", bytes.fromhex("260825101530"), 0, rows)
    assert any("2026-08-25" in str(r) for r in rows), "模块时钟未解析"
    # EB040302 停上电记录: 停电时刻(6) + 上电时刻(6)
    rows = []
    parser._parse_eb_di("EB040302", bytes.fromhex("241201010000") + bytes.fromhex("250102020000"), 0, rows)
    assert any("记录1停电时刻" in str(r[0]) for r in rows), "停上电记录未解析"
    # EB030503 校时记录: YYMMDD hhmmss(6) + NTB(4)
    rows = []
    parser._parse_eb_di("EB030503", bytes.fromhex("260825101530") + bytes.fromhex("00000064"), 0, rows)
    assert any("低4字节时间差" in str(r[0]) for r in rows), "NTB 时间差未解析"
    # EBEEEEEE 多数据项: 个数(1) + [长度(1)+内容]
    rows = []
    data = bytes([0x02, 0x06]) + bytes.fromhex("EB040201") + bytes.fromhex("0005") + bytes([0x06]) + bytes.fromhex("EB040202") + bytes.fromhex("0008")
    parser._parse_eb_di("EBEEEEEE", data, 0, rows)
    assert any("数据项1标识" in str(r[0]) for r in rows), "多数据项未解析"
    assert any("数据项2标识" in str(r[0]) for r in rows), "多数据项第2项未解析"
    print("PASS test_eb_deep_parse")


def test_fujian_frame_generation():
    """福建增补组帧 + 回读"""
    gen = GDWFrameGenerator()
    parser = GDW10376Parser()
    # 52H-F1 透明转发（报文长度自动计算）
    f645 = make_645_frame(0x91, bytes.fromhex("EB040201"), bytes.fromhex("0005"))
    frame = gen.generate_frame(
        afn=0x52, fn=1,
        field_values={
            "通信对象类型": 1, "通信对象地址": "001122334455",
            "透明转发通信控制字": 0, "接收等待报文超时时间": 1, "接收等待字节超时时间": 10,
            "报文内容": f645.hex(),
        },
        info_config={"报文序列号": 1},
        src_addr="000000000001", dst_addr="001122334455",
    )
    # 帧结构校验：起始 68 + 长度 + 控制 + R(6) + A1(6) + A3(6) + AFN(52)
    assert frame[0] == 0x68, "帧起始符错误"
    assert frame[22] == 0x52, f"AFN 位置错误: {frame[22]:02X}"
    rows = parser.parse_to_table(frame)
    assert any("数据转发（福建增补）" in str(r[3]) for r in rows), "组帧回读 AFN 未识别"
    # 报文长度自动计算
    len_rows = row_values(rows, "报文长度")
    assert len_rows and len_rows[0][2] == str(len(f645)), f"报文长度自动计算错误: {len_rows}"
    # EB 深度解析
    assert any("EB040201" in str(r) for r in rows), "组帧内嵌 EB 未解析"
    print("PASS test_fujian_frame_generation")


def test_afn55_f2_schema_list():
    """福建增补 55H-F2 允许/禁止上报（list 字段组帧）"""
    gen = GDWFrameGenerator()
    frame = gen.generate_frame(
        afn=0x55, fn=2,
        field_values={
            "本次设置的对象数量": 1,
            "对象列表": [
                {"通信对象类型": 1, "任务对象通信地址": "001122334455", "事件上报状态标志": 1},
            ],
        },
        info_config={"报文序列号": 0},
        src_addr="000000000001", dst_addr="001122334455",
    )
    assert frame[22] == 0x55, "AFN 位置错误"
    assert frame[25] == 0x01, "对象数量错误"  # 数据单元首字节（AFN 22 + DT 23-24 之后）= 对象数量
    parser = GDW10376Parser()
    rows = parser.parse_to_table(frame)
    assert any("允许、禁止从节点上报" in str(r[3]) for r in rows), "55H-F2 未识别"
    assert any("对象1事件上报状态标志" in str(r[0]) for r in rows), "对象上报标志未解析"
    print("PASS test_afn55_f2_schema_list")


def test_validator_fujian():
    """校验器对福建增补帧支持"""
    gen = GDWFrameGenerator()
    v = GDWValidator()
    frame = gen.generate_frame(
        afn=0x52, fn=1,
        field_values={"通信对象类型": 1, "通信对象地址": "001122334455",
                      "透明转发通信控制字": 0, "接收等待报文超时时间": 1, "接收等待字节超时时间": 10,
                      "报文内容": ""},
        info_config={"报文序列号": 1},
        src_addr="000000000001", dst_addr="001122334455",
    )
    result = v.verify(frame)
    assert result.valid, f"福建增补帧校验失败: {[c.message for c in result.checks if c.level.name=='FAIL']}"
    # AFN 检查应识别真实 AFN=0x52
    afn_checks = [c for c in result.checks if c.name == "AFN值域"]
    assert afn_checks and "0x52" in afn_checks[0].actual, f"AFN 检查未识别福建增补: {afn_checks}"
    print("PASS test_validator_fujian")


def test_gdw_2024_regression():
    """2024 国网帧回归（无地址域 03H-F1）"""
    parser = GDW10376Parser()
    # 68 L C R(6B) AFN(03) DT(01 00) CS 16
    R = bytes(6)
    user = R + bytes([0x03, 0x01, 0x00])
    L = len(user) + 6
    body = bytes([0x43]) + user
    cs = sum(body) & 0xFF
    frame = bytes([0x68]) + L.to_bytes(2, 'little') + body + bytes([cs, 0x16])
    rows = parser.parse_to_table(frame)
    # 信息域应按 2024 国网结构解析（路由标识等，非保留）
    assert any("D0 路由标识" in str(r[0]) for r in rows), "2024 国网信息域未按原结构解析"
    assert any("查询数据" in str(r[3]) for r in rows), "2024 国网 AFN=03H 未识别"
    print("PASS test_gdw_2024_regression")


def test_fujian_afn_map_present():
    """福建增补 AFN/Fn 映射存在"""
    parser = GDW10376Parser()
    assert parser.FUJIAN_AFNS == {0x50, 0x51, 0x52, 0x53, 0x55, 0x56}, "FUJIAN_AFNS 错误"
    for afn in parser.FUJIAN_AFNS:
        assert afn in parser.AFN_MAP, f"AFN {afn:02X} 不在 AFN_MAP"
        assert afn in parser.FN_MAP and len(parser.FN_MAP[afn]) > 0, f"AFN {afn:02X} 无 Fn 定义"
    # 查询页列表应包含福建增补
    afn_fn_list = parser.get_afn_fn_list()
    fujian_entries = [x for x in afn_fn_list if x[0] in parser.FUJIAN_AFNS]
    assert len(fujian_entries) >= 27, f"福建增补条目不足: {len(fujian_entries)}"
    print("PASS test_fujian_afn_map_present")


def _build_eb_645_frame_logic(di, ctrl, addr_hex, data_hex=""):
    """EB 645 帧纯逻辑（与 GUI _build_eb_645_frame / Web gen_eb_645_frame 一致）"""
    di_bytes = bytes.fromhex(di)
    data = bytes.fromhex(data_hex.replace(" ", "")) if data_hex.strip() else b""
    addr = bytes.fromhex(addr_hex.replace(" ", ""))
    if len(addr) != 6:
        addr = addr[:6].ljust(6, b'\x00')
    data_len = len(di_bytes) + len(data)
    body = bytes([ctrl, data_len]) + di_bytes + data
    cs = sum(body) & 0xFF
    return bytes([0x68]) + addr + bytes([0x68]) + body + bytes([cs, 0x16])


def test_eb_645_frame_generation():
    """EB 数据标识 645 帧生成：68 A0..A5 68 C L DI3 DI2 DI1 DI0 DATA CS 16"""
    frame = _build_eb_645_frame_logic("EB030002", 0x81, "000000000000", "01 01 112233445566")
    b = frame
    assert b[0] == 0x68 and b[7] == 0x68 and b[-1] == 0x16, "645 帧结构错误"
    assert b[10:14] == bytes.fromhex("EB030002"), "EB030002 字节序错误"
    cs_calc = sum(b[8:-2]) & 0xFF
    assert b[-2] == cs_calc, f"CS 校验错误: {b[-2]:02X} vs {cs_calc:02X}"
    # 数据标识长度 L = DI 4B + 数据 8B = 0C
    assert b[9] == 0x0C, f"数据长度错误: {b[9]:02X}"
    # 与 Web 版逐字节一致
    expected = "6800000000000068810CEB0300020101112233445566E416"
    assert frame.hex().upper() == expected, f"与 Web 版不一致: {frame.hex().upper()}"
    print("PASS test_eb_645_frame_generation")


def test_eb_698_frame_generation():
    """EB 数据标识 698.45 完整帧生成：对照附件1 文档示例 + Web 版"""
    import os as _os
    import sys as _sys
    _reflex_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "reflex_web")
    _sys.path.insert(0, _reflex_dir)
    from frame_gen_utils import build_eb_698_frame, build_dlt698_sa
    from gdw_eb_di_fields import encode_eb_di_data, EB_DI_FIELDS

    # 字段编码（附件1 定义）
    assert encode_eb_di_data('EB030002', {'停上电类型': 1, '本次上报数量': 1,
                                          '模块地址列表': [{'模块地址': '112233445566'}]}).hex() == '0101112233445566'
    assert encode_eb_di_data('EB030110', {'台区识别方法': 0, '识别时长(分钟)': 5}).hex() == '000005'
    assert len(EB_DI_FIELDS) >= 40, f"字段定义不足: {len(EB_DI_FIELDS)}"

    sa = build_dlt698_sa(0, 0, 6, "000000000000")
    frame_bytes = build_eb_698_frame("EB030110", "SET-Request", "000005",
                                     sa=sa, ca=0, dir_bit=0, prm_bit=1, func_code=3)
    b = bytes(frame_bytes) if isinstance(frame_bytes, bytes) else bytes.fromhex(frame_bytes)
    assert b[0] == 0x68 and b[-1] == 0x16, "698 完整帧 68..16 结构错误"
    assert b[3] == 0x43, f"控制域应为 0x43: {b[3]:02X}"
    # HCS/FCS 校验
    from dl_t698_45_frame_gen import DLT69845FrameGenerator
    gen = DLT69845FrameGenerator()
    assert gen._calc_crc(b[1:12]) == b[12:14], "HCS 校验错误"
    assert gen._calc_crc(b[1:-3]) == b[-3:-1], "FCS 校验错误"
    # APDU 内嵌 EB OAD
    apdu = b[14:-3]
    assert apdu.hex().upper().find('EB030110') >= 0, "APDU 未含 EB OAD"
    # 长度域 = 帧长-2
    length = int.from_bytes(b[1:3], 'little') & 0x3FFF
    assert length == len(b) - 2, f"长度域错误: {length} vs {len(b)-2}"
    print("PASS test_eb_698_frame_generation")


def test_eb_gui_integration():
    """GUI FrameGenWidget EB 生成器集成：698 字段表单 → 生成 → 填入 52H-F1 报文内容"""
    import os as _os
    _os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit
    from frame_gen_widget import FrameGenWidget

    app = QApplication.instance() or QApplication([])
    w = FrameGenWidget()
    w.set_protocol_mode('gdw')

    # EB 下拉已填充
    assert w.eb_di_combo.count() > 50, f"EB 下拉项不足: {w.eb_di_combo.count()}"
    # 选 EB030110，698 字段模式
    w.eb_di_combo.setCurrentIndex(w.eb_di_combo.findData('EB030110'))
    w.eb_format_combo.setCurrentIndex(w.eb_format_combo.findData('698'))
    w.eb_698_src_combo.setCurrentIndex(w.eb_698_src_combo.findData(1))
    w._rebuild_eb_fields()
    assert set(w._eb_field_widgets.keys()) == {'台区识别方法', '识别时长(分钟)'}, \
        f"EB030110 字段表单错误: {list(w._eb_field_widgets.keys())}"

    # 填字段值 → 生成 698 帧
    combo = w._eb_field_widgets['台区识别方法']['widget']
    combo.setCurrentIndex(combo.findData(0))
    w._eb_field_widgets['识别时长(分钟)']['widget'].setText('5')
    w.eb_698_service_combo.setCurrentIndex(w.eb_698_service_combo.findData('SET-Request'))
    w._gen_eb_frame()
    assert w.eb_gen_frame.startswith('68') and w.eb_gen_frame.endswith('16'), "698 完整帧未生成"
    assert w.eb_gen_result.text().startswith("68"), "698 帧未显示到结果框"

    # 选择 52H-F1（转发通信协议数据帧），填入报文内容
    target_idx = None
    for i in range(w.afn_fn_combo.count()):
        d = w.afn_fn_combo.itemData(i)
        if d and isinstance(d, tuple) and d[0] == 0x52 and d[1] == 1:
            target_idx = i
            break
    assert target_idx is not None, "未找到 52H-F1"
    w.afn_fn_combo.setCurrentIndex(target_idx)
    assert w._current_afn_fn == (0x52, 1), f"_current_afn_fn 错误: {w._current_afn_fn}"
    w._apply_eb_to_content()
    widget = w._field_widgets.get('报文内容', {}).get('widget')
    assert widget is not None and widget.text() == w.eb_gen_frame, "报文内容未填入 EB 帧"
    # 实时组帧含 EB 帧（结果框为大写空格分隔，EB 帧为小写紧凑）
    w._do_realtime_update_gdw()
    result_lower = w.result_hex.toPlainText().replace(" ", "").lower()
    assert w.eb_gen_frame in result_lower, \
        f"主帧未包含 EB 帧内容: 主帧={result_lower[:80]}... EB={w.eb_gen_frame[:40]}..."
    print("PASS test_eb_gui_integration")


if __name__ == "__main__":
    test_fujian_frame_identification()
    test_afn50_confirm_deny()
    test_afn52_f1_transparent_forward()
    test_afn52_f2_task_queue()
    test_afn53_f4_vendor_info()
    test_afn53_f6_serial_params()
    test_afn55_f9_preannounce()
    test_afn56_f2_event_report()
    test_eb_di_lookup()
    test_eb_deep_parse()
    test_eb_v342_deep_parse()
    test_fujian_frame_generation()
    test_afn55_f2_schema_list()
    test_validator_fujian()
    test_gdw_2024_regression()
    test_fujian_afn_map_present()
    test_eb_645_frame_generation()
    test_eb_698_frame_generation()
    test_eb_gui_integration()
    print("\n全部 19 项测试通过")
