# -*- coding: utf-8 -*-
"""监控包装解帧(ED..EE, PLC2.0收发机) 功能验证（临时脚本）

包结构: ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)
  帧长 = 控制域1+控制域2+EF+数据域+CS = 数据域长度 + 4；整包 = 帧长 + 4
数据报文(控制域1=0x00) 控制域2=0x01/0x02/0x03 数据域公共头(9字节):
  物理信道(1)+时间戳(4,LE)+物理块个数(1)+[保留/CRC](1)+单个物理块长度(2,LE)+数据FC/Payload(变长)
参考《PLC2.0收发机报文格式0629.docx》
"""


import _path_setup  # noqa: E402

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from monitor_widget import RealtimeMonitorWidget

app = QApplication([])


class StubParser:
    """仅记录收到的业务帧，避免耦合 csg 解析器内部实现"""
    def __init__(self):
        self.received = []

    def parse_to_table(self, data, parse_level="auto"):
        self.received.append(bytes(data))
        return [("业务帧", "", "", f"{len(data)}字节", 0, max(len(data) - 1, 0))]


def summ(td):
    return f"字段:{len(td)}"


def make_plc2_wrap(data域: bytes, ctrl1=0x00, ctrl2=0x02, cs=None) -> bytes:
    """构造 PLC2.0 收发机 ED..EE 包装包

    data域 为 EF 之后、CS 之前的数据域（调用方负责按子类型组装公共头+业务帧）。
    cs=None 时按"报文之前所有字节求和取8bit"计算真实CS；否则用指定CS。
    """
    frame_len = len(data域) + 4  # 控制域1+控制域2+EF+数据域+CS
    head = bytes([0xED, frame_len & 0xFF, (frame_len >> 8) & 0xFF,
                  ctrl1, ctrl2, 0xEF])
    body = head + data域
    calc_cs = sum(body) & 0xFF  # ED..数据域末
    return body + bytes([calc_cs if cs is None else cs, 0xEE])


def make_data域(business: bytes, ch=0x01, ts=0x11223344, pb_cnt=0x02,
                flag6=0x00, pb_len=0x0010) -> bytes:
    """组装 数据报文(0x01/0x02/0x03) 的数据域公共头(9B) + 业务帧"""
    return (bytes([ch])
            + ts.to_bytes(4, "little")
            + bytes([pb_cnt, flag6])
            + pb_len.to_bytes(2, "little")
            + business)


def new_widget():
    w = RealtimeMonitorWidget()
    w.set_protocol(StubParser(), summ, wrapper_format="plc2")
    assert w._wrapper_format == "plc2"
    assert w.deframe_chk.isChecked(), "解帧应默认开启"
    return w


# ---------- 场景1：单个 FC+Payload 包（控制域2=0x02） ----------
business = bytes(range(20))  # 20 字节业务帧
data域 = make_data域(business, ch=0x01, ts=0x11223344, pb_cnt=0x02, pb_len=0x0010)
w = new_widget()
w._on_raw_data(make_plc2_wrap(data域, ctrl1=0x00, ctrl2=0x02))
assert len(w._frames) == 1, f"应解出1包, 实得{len(w._frames)}"
rec = w._frames[0]
meta = rec["meta"]
assert meta["ctrl1"] == 0x00 and meta["ctrl2"] == 0x02
assert meta["ctrl2_name"] == "FC+Payload数据", meta["ctrl2_name"]
assert meta["frame_len"] == len(data域) + 4
assert meta["data_len"] == len(data域)
assert meta["channel"] == 0x01 and meta["channel_name"] == "HPLC"
assert meta["timestamp"] == 0x11223344, f"时间戳: {meta['timestamp']:#x}"
assert meta["pb_count"] == 0x02 and meta["pb_len"] == 0x0010
assert meta["has_business"] is True
assert meta["payload_crc_err"] is False
assert meta["cs_ok"] is True, "真实CS应校验通过"
assert rec["raw"] == business, f"业务帧提取错误: {rec['raw'].hex()}"
assert w._parser.received == [business], "业务帧应送入解析器"
assert len(w._rx_buffer) == 0
print("1 单个FC+Payload包：包装头解析+业务帧提取 OK")
print("  摘要=", rec["summary"])

# ---------- 场景2：连帧（两个包一次性到达） ----------
w = new_widget()
biz1 = bytes([0xAA, 0xBB, 0xCC])
biz2 = bytes([0xDD, 0xEE])
p1 = make_plc2_wrap(make_data域(biz1, ch=0x02, ts=1), ctrl2=0x02)
p2 = make_plc2_wrap(make_data域(biz2, ch=0x01, ts=2), ctrl2=0x02)
w._on_raw_data(p1 + p2)
assert len(w._frames) == 2, f"连帧应解出2包: {len(w._frames)}"
assert w._frames[0]["raw"] == biz1 and w._frames[0]["meta"]["channel"] == 0x02
assert w._frames[1]["raw"] == biz2 and w._frames[1]["meta"]["channel"] == 0x01
assert w._parser.received == [biz1, biz2]
print("2 连帧一次到达：正确拆分2个包 OK")

# ---------- 场景3：数据域内含 0xEE/0xED/0xEF（不应误切） ----------
w = new_widget()
biz = bytes([0xED, 0xEE, 0xEF, 0x16, 0x96, 0xED, 0xEE])
w._on_raw_data(make_plc2_wrap(make_data域(biz), ctrl2=0x02))
assert len(w._frames) == 1, "数据域含EE/ED/EF不应误切"
assert w._frames[0]["raw"] == biz, f"数据域内特殊字节被误切: {w._frames[0]['raw'].hex()}"
print("3 数据域含EE/ED/EF：按帧长定界不误切 OK")

# ---------- 场景4：分片到达（半包 -> 补齐） ----------
w = new_widget()
p = make_plc2_wrap(make_data域(bytes([0x01, 0x02, 0x03, 0x04]), ts=0x55), ctrl2=0x02)
w._on_raw_data(p[:5])  # 不到 EF
assert len(w._frames) == 0 and len(w._rx_buffer) == 5
w._on_raw_data(p[5:])
assert len(w._frames) == 1 and len(w._rx_buffer) == 0
assert w._frames[0]["raw"] == bytes([0x01, 0x02, 0x03, 0x04])
print("4 分片到达：半包缓存补齐后解出 OK")

# ---------- 场景5：伪帧头（0xED但LEN超限/缺EF/缺EE）后恢复 ----------
w = new_widget()
# 0xED + 超大帧长(0xFFF0) -> 伪头跳过
garbage = bytes([0xED, 0xF0, 0xFF, 0x00, 0x00, 0xEF, 0xFF, 0xEE])
good = make_plc2_wrap(make_data域(bytes([0x77, 0x88])), ctrl2=0x02)
w._on_raw_data(garbage + good)
assert len(w._frames) == 1, f"伪头后应恢复解出真包: {len(w._frames)}"
assert w._frames[0]["raw"] == bytes([0x77, 0x88])
print("5 伪帧头后恢复：跳过伪头解出真包 OK")

# ---------- 场景6：控制报文（控制域1=0x01）无业务帧 ----------
w = new_widget()
# 控制报文 ctrl2=0x00 复位：数据域为空
w._on_raw_data(make_plc2_wrap(b"", ctrl1=0x01, ctrl2=0x00))
assert len(w._frames) == 1
rec = w._frames[0]
assert rec["meta"]["has_business"] is False
assert rec["meta"]["ctrl1_name"] == "控制报文"
assert w._parser.received == [], "控制报文不应调用解析器"
assert any("无业务帧" in (r[0] or "") for r in rec["table_data"]), "应含无业务帧行"
assert rec["ok"] is True, "控制报文(无CRC错误)应OK"
print("6 控制报文：不调解析器，展示无业务帧 OK")

# ---------- 场景7：FC数据(0x01) 与 Payload数据(0x03) ----------
w = new_widget()
fc_biz = bytes([0x12] * 16)
pl_biz = bytes([0x34] * 8)
w._on_raw_data(make_plc2_wrap(make_data域(fc_biz), ctrl2=0x01) +
               make_plc2_wrap(make_data域(pl_biz), ctrl2=0x03))
assert len(w._frames) == 2
assert w._frames[0]["meta"]["ctrl2_name"] == "FC数据"
assert w._frames[0]["raw"] == fc_biz
assert w._frames[1]["meta"]["ctrl2_name"] == "Payload数据"
assert w._frames[1]["raw"] == pl_biz
print("7 FC数据(0x01)/Payload数据(0x03)：业务帧正确提取 OK")

# ---------- 场景8：Payload CRC 错误标记（控制域2=0x02, flag6=1） ----------
w = new_widget()
w._on_raw_data(make_plc2_wrap(make_data域(bytes([0x01]), flag6=0x01), ctrl2=0x02))
rec = w._frames[0]
assert rec["meta"]["payload_crc_err"] is True
assert rec["ok"] is False, "Payload CRC错误帧应标记不OK"
assert "CRC✗" in rec["summary"], f"摘要应含CRC错误标记: {rec['summary']}"
print("8 Payload CRC错误：正确标记 OK")

# ---------- 场景9：CS=0xFF(保留位) 不影响 OK ----------
w = new_widget()
w._on_raw_data(make_plc2_wrap(make_data域(bytes([0x01])), ctrl2=0x02, cs=0xFF))
rec = w._frames[0]
assert rec["meta"]["cs"] == 0xFF
assert rec["meta"]["cs_ok"] is False, "0xFF一般不等于实际校验和"
assert rec["ok"] is True, "PLC2.0 CS为保留位，不应因CS不符标记失败"
print("9 CS=0xFF保留位：不影响OK判定 OK")

# ---------- 场景10：详情表前置包装头行 ----------
w = new_widget()
w._on_raw_data(make_plc2_wrap(make_data域(bytes([0x01, 0x02]), ts=0xCAFEBABE), ctrl2=0x02))
td = w._frames[0]["table_data"]
labels = [r[0] for r in td]
assert labels[0] == "── PLC2.0 收发机包装 ──", labels[0]
assert any("控制域1" in l for l in labels)
assert any("控制域2" in l for l in labels)
assert any("物理信道" in l for l in labels)
assert any("时间戳" in l for l in labels)
assert any("业务帧" in l for l in labels)
# 包装头行不参与高亮
for r in td[:9]:
    assert r[4] is None, f"包装头行不应高亮: {r[0]}"
print("10 详情前置PLC2.0包装头信息行（不高亮）OK")

print("全部通过")
