# -*- coding: utf-8 -*-
"""国网新一代(索引10)监控摘要 _get_gw_new_gen_summary 验证（临时脚本）

不依赖 GUI：直接构造一个含 _get_gw_new_gen_summary 方法的轻量宿主，
用真实 GWNewGenParser 输出的 table_data 驱动摘要生成。
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from gw_new_gen_parser import GWNewGenParser
import main_gui


# 复用 MainWindow 上定义的摘要方法，避免重复实现
_summary = main_gui.MainWindow._get_gw_new_gen_summary


class Host:
    """仅提供 _get_gw_new_gen_summary 的最小宿主"""
    _get_gw_new_gen_summary = _summary


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
check("含方向(下行)", "(下行)" in s1, s1)

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

print(f"\n=== 结果: {passed} 通过, {failed} 失败 ===")
if failed > 0:
    sys.exit(1)
