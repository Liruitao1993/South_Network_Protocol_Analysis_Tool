# -*- coding: utf-8 -*-
"""国网新一代(索引10)监控摘要 _get_gw_new_gen_summary 验证（临时脚本）

不依赖 GUI：直接构造一个含 _get_gw_new_gen_summary 方法的轻量宿主，
用真实 GWNewGenParser 输出的 table_data 驱动摘要生成。
"""


import _path_setup  # noqa: E402

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from gw_new_gen_parser import GWNewGenParser
import main_gui


# 复用 MainWindow 上定义的摘要方法，避免重复实现
_summary = main_gui.MainWindow._get_gw_new_gen_summary


class Host:
    """仅提供摘要方法的最小宿主"""

    _get_gw_new_gen_summary = _summary
    # 摘要内部会调用该方法取测试模式（staticmethod 需显式包裹，否则会多传 self）
    _extract_test_mode_content = staticmethod(
        main_gui.MainWindow._extract_test_mode_content
    )
    _TEST_MODE_SENTINELS = main_gui.MainWindow._TEST_MODE_SENTINELS


host = Host()
parser = GWNewGenParser()
passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [OK] {name}")
    else:
        failed += 1
        print(f"  [XX] {name} {detail}")


def summ(frame: bytes) -> str:
    td = parser.parse_to_table(frame, parse_level="auto")
    return host._get_gw_new_gen_summary(td)


# ---------- 1. 应用层紧跟FC（抄表业务，规约3=698.45，数据长度63）----------
frame1 = bytes([
    0x11, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x11, 0x01, 0x00, 0x00,
    0x41, 0x08, 0xF3, 0x03, 0x42, 0x0D, 0x23, 0x05,
    0x68, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0x16,
])
s1 = summ(frame1)
print("1 应用层报文摘要:", s1)
check("含端口(抄表业务)", "端口:抄表业务" in s1, s1)
check("含数据长度63", "数据:63" in s1, s1)
check("含规约(698.45)", "规约:698.45" in s1, s1)
check("含报文序号", "序号:" in s1, s1)
# 该帧业务数据选项字 = 0x0523（见解析行「选项字」），bit0=1 → 上行；
# 原断言写 (下行) 与本帧字节不符（帧是手写构造，选项字未按下行置 0）
check("含方向(上行)", "(上行)" in s1, s1)

# ---------- 2. 确认/否认报文 ----------
frame2 = bytes([
    0x11, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x11, 0x20, 0x00, 0x00,
    0x41, 0x04, 0x42, 0x00,
])
s2 = summ(frame2)
print("2 确认/否认摘要:", s2)
check("含报文(确认/否认)", "报文:" in s2 and "确认" in s2, s2)

# ---------- 3. 校时报文 ----------
frame3 = bytes([
    0x11, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x11, 0x04, 0x00, 0x00,
    0x41, 0x04, 0x00, 0x08, 0x01, 0x00,
    0x30, 0x12, 0x06, 0x27, 0x01, 0x26,
])
s3 = summ(frame3)
print("3 校时报文摘要:", s3)
check("含报文(校时)", "报文:" in s3, s3)

# ---------- 4. 完整MAC帧头+应用层：应体现TEI/MSDU序列/发送类型 ----------
frame4 = bytes([
    0x11, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    # MAC帧头(15字节)
    0x00, 0x11, 0x00, 0x01, 0x00, 0x05, 0x30, 0x00,
    0x4B, 0x00, 0x00, 0x22, 0x00, 0x00, 0x22,
    # 应用层
    0x11, 0x01, 0x00, 0x00,
    0x41, 0x08, 0xF3, 0x03, 0x42, 0x0D, 0x23, 0x05,
    0x68, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x16,
])
td4 = parser.parse_to_table(frame4, parse_level="auto")
s4 = host._get_gw_new_gen_summary(td4)
print("4 MAC帧头+应用层摘要:", s4)
has_mac = any("MAC帧头" in row[0] for row in td4)
if has_mac:
    check("含MSDU序列号或TEI(MAC头已解析)",
          "msduSeq:" in s4 or "→" in s4, s4)
else:
    check("MAC头未解析则退化为应用层摘要", "端口:" in s4, s4)

# ---------- 5. 解析失败/空输入 ----------
check("空table_data返回'-'", host._get_gw_new_gen_summary([]) == "-")
err_td = [("❌ 解析失败", "", "", "帧数据过短", None, None, False)]
check("失败帧返回失败原因", host._get_gw_new_gen_summary(err_td) == "帧数据过短")

# ---------- 6. FC-only：应体现帧类型 ----------
td6 = parser.parse_to_table(frame1, parse_level="fc_only")
s6 = host._get_gw_new_gen_summary(td6)
print("6 FC-only摘要:", s6)
check("FC-only含帧类型信息", len(s6) > 1 and s6 != "-", s6)

# ---------- 7. 测试类报文：检测扩展命令应体现测试模式 ----------
from gw_new_gen_cmd_payloads import _parse_comm_test

# 字节1高4位=测试模式；模式3=HPLC物理层透传测试模式（配置值/数据域随模式而定）
td7 = _parse_comm_test(bytes([0x41, 0x30, 0x00, 0x00, 0x00, 0x00]), 0, 0)
s7 = host._get_gw_new_gen_summary(td7)
print("7 检测扩展命令(模式3)摘要:", s7)
check("含测试模式(PLC物理层透传)", "测试模式:HPLC物理层透传测试模式(3)" in s7, s7)

# 模式13=安全测试模式，子模式 SM3算法测试
td8 = _parse_comm_test(bytes([0x41, 0xD0, 0x00, 0x00, 0x02, 0x00]), 0, 0)
s8 = host._get_gw_new_gen_summary(td8)
print("8 安全测试模式摘要:", s8)
check("含测试模式(安全测试模式)", "测试模式:安全测试模式(13)" in s8, s8)
check("含安全测试子模式", "安全测试模式:SM3算法测试" in s8, s8)

# 模式15=新一代扩展测试模式，子模式6=CCO信标机制切换（帧取自 test/test_gw_ext_cmd.py）
td10 = _parse_comm_test(bytes.fromhex("01F01600000001"), 0, 0)
s10 = host._get_gw_new_gen_summary(td10)
print("10 新一代测试模式摘要:", s10)
check("含测试模式(新一代扩展测试模式)", "测试模式:新一代扩展测试模式(15)" in s10, s10)
check("含新一代子模式名(取 parsed 槽)", "新一代测试模式:CCO信标机制切换" in s10, s10)

# 模式1 的名称自带括号 → 不应重复追加模式号
td11 = _parse_comm_test(bytes.fromhex("0110000000"), 0, 0)
s11 = host._get_gw_new_gen_summary(td11)
print("11 模式1摘要:", s11)
check("名称自带括号时不重复括号", "(暂未使用)(1)" not in s11 and "测试模式:" in s11, s11)

# 普通通信测试（模式=0）不应出现测试模式片段
td9 = _parse_comm_test(bytes([0x41, 0x00, 0x00, 0x08]), 0, 0)
s9 = host._get_gw_new_gen_summary(td9)
print("9 普通通信测试摘要:", s9)
check("普通通信测试无测试模式片段", "测试模式" not in s9, s9)

print(f"\n=== 结果: {passed} 通过, {failed} 失败 ===")
if failed > 0:
    sys.exit(1)
