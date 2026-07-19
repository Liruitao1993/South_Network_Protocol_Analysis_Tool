# -*- coding: utf-8 -*-
"""国网新一代双模通信互联互通协议 解析器测试"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from gw_new_gen_parser import GWNewGenParser


def test_basic_parse():
    """测试基本解析"""
    parser = GWNewGenParser()

    # 构造一个简单的测试帧：FC(16字节) + 应用层
    frame = bytes([
        0x10,  # 字节0: 定界符类型=0(信标) + 网络类型=2
        0x00, 0x01,  # NID=1
        0x00,  # 保留
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # 可变区域
        0x00,  # 版本号=0
        0x00, 0x00, 0x00,  # FCCS
        # 应用层
        0x11,  # 报文端口号=0x11(抄表)
        0x00, 0x01,  # 报文ID=0x0001(终端主动抄表)
        0x00,  # 控制字
        0x01, 0x02, 0x03, 0x04,  # 业务数据
    ])

    result = parser.parse_to_table(frame)
    assert len(result) > 0, "解析结果不应为空"
    print(f"✅ 基本解析: {len(result)} 行")

    # 打印结果
    for row in result:
        field = row[0]
        raw = row[1]
        parsed = row[2]
        comment = row[3]
        print(f"  {field}: {raw} -> {parsed} ({comment})")


def test_sof_frame():
    """测试SOF帧"""
    parser = GWNewGenParser()

    frame = bytes([
        0x11,  # 字节0: 定界符类型=1(SOF) + 网络类型=2
        0x00, 0x02,  # NID=2
        0x00,  # 保留
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # 可变区域
        0x10,  # 版本号=1(HDC 2.0)
        0x12, 0x34, 0x56,  # FCCS
        # 应用层 - 校时报文
        0x11,  # 端口=抄表
        0x00, 0x04,  # 报文ID=0x0004(校时)
        0x00,  # 控制字
    ])

    result = parser.parse_to_table(frame)
    assert len(result) > 0
    print(f"✅ SOF帧: {len(result)} 行")


def test_msg_id_lookup():
    """测试报文ID查找"""
    parser = GWNewGenParser()

    # 验证所有报文ID都有描述
    for msg_id, name in parser.MSG_IDS.items():
        assert name, f"报文ID 0x{msg_id:04X} 没有名称"
    print(f"✅ 报文ID: {len(parser.MSG_IDS)} 个全部有描述")

    # 验证端口号
    for port, name in parser.PORT_NAMES.items():
        assert name, f"端口号 0x{port:02X} 没有名称"
    print(f"✅ 端口号: {len(parser.PORT_NAMES)} 个全部有描述")


def test_short_frame():
    """测试过短帧"""
    parser = GWNewGenParser()
    result = parser.parse_to_table(bytes([0x10]))
    assert len(result) > 0
    print(f"✅ 过短帧: {len(result)} 行")


if __name__ == "__main__":
    test_basic_parse()
    print()
    test_sof_frame()
    print()
    test_msg_id_lookup()
    print()
    test_short_frame()
    print("\n✅ 全部测试通过!")
