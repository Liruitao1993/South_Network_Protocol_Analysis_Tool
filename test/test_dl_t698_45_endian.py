"""协议8（DL/T 698.45-2017）字节序契约测试：**链路层小端 / A-XDR 数据大端**。

运行：
    pwsh -c '$env:PYTHONIOENCODING="utf-8"; python -u test/test_dl_t698_45_endian.py'

判据全部来自协议文档《面向对象的用电信息数据交换协议(20210910).md》
（`协议文档/8.698.45协议/`），**不是**本工程 encode 出来的，故可抓住「自证闭环」类假绿：
  - L347 链路层：「低字节在前，高字节在后」→ 长度域/HCS/FCS 小端；
  - §7.1 APDU 编码规则 = A-XDR（DL/T 790.6-2010）→ 多字节大端；
  - 附录 H.1.1「登录」：00 B4 = 180s、07 E0 = 2016 年、00 A4 = 164ms；
  - 附录 H.3.2「读取多个对象属性」：12 09 6D = 2413（241.3V）、05 00 00 03 E8 = 1000；
  - 用户实测帧（2026-09-28 现场）：FF FF 9E D0 应为 -24880（曾错读 -794886145）。
"""

import sys

import _path_setup  # noqa: E402,F401

from dl_t698_45_apdu_parser import DLT69845APDUParser  # noqa: E402
from dl_t698_45_axdr import AXDRCoder  # noqa: E402
from dl_t698_45_frame_gen import DLT69845FrameGenerator  # noqa: E402
from dl_t698_45_parser import DLT69845Parser  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n== {title} ==")


# 用户现场实测帧（服务器/终端上行 GET-Response，OI=0x2004 属性2 特征0 索引1）
USER_FRAME = bytes.fromhex(
    "681F00C3260231310400009001" "7F8D" "850109200402010105FFFF9ED00000" "6D17" "16"
)


def test_link_layer_stays_little_endian():
    """链路层必须仍是小端（改 A-XDR 时最容易被一并改错的回归点）"""
    section("链路层小端（不得随 A-XDR 一起改成大端）")
    r = DLT69845Parser().parse(USER_FRAME)
    check("解析成功", r["解析状态"] == "成功", str(r.get("错误信息", "")))
    check("长度域 1F 00 → 31（小端）", r["长度域"]["长度值"] == 31, str(r["长度域"]["长度值"]))
    check("HCS 校验通过", r["帧头校验HCS"]["校验结果"] == "通过", r["帧头校验HCS"]["原始值"])
    check("FCS 校验通过", r["帧校验FCS"]["校验结果"] == "通过", r["帧校验FCS"]["原始值"])
    check("服务器地址 SA 反转（低字节在前）",
          r["地址域"]["服务器地址SA"]["解析值"] == "90000004313102",
          r["地址域"]["服务器地址SA"]["解析值"])


def test_user_frame_value_big_endian():
    """用户报障帧：同一段字节，改前 -794886145 / 改后 -24880"""
    section("用户实测帧：05 FF FF 9E D0 → -24880（大端）")
    data = DLT69845Parser().parse(USER_FRAME)["链路用户数据"]["APDU"]["数据"]
    check("原始编码 = 05FFFF9ED0", data["原始编码"] == "05FFFF9ED0", data["原始编码"])
    check("原始值 = FFFF9ED0", data["原始值"] == "FFFF9ED0", data["原始值"])
    check("解析值 = -24880（原错误值 -794886145）", data["解析值"] == -24880, str(data["解析值"]))
    check("说明标注大端", "大端" in data["说明"], data["说明"])


def test_oracle_698_login_request():
    """附录 H.1.1 登录请求：01 00 00 00 B4 | 07 E0 05 13 04 08 05 00 00 A4"""
    section("oracle：附录 H.1.1「登录」请求（SEQUENCE 定长字段不带 tag）")
    apdu = bytes.fromhex("01" "00" "00" "00B4" "07E005130408050000A4")
    r = DLT69845APDUParser().parse(apdu)
    check("APDU 解析成功", r["解析状态"] == "成功", str(r.get("错误信息", "")))
    check("类型 = LINK-Request", r["APDU类型"] == "LINK-Request", r.get("APDU类型", ""))
    check("请求类型 = 登录", r["请求类型"]["解析值"] == 0, r["请求类型"]["说明"])
    check("心跳周期 = 180s（00 B4 大端）", r["心跳周期"]["解析值"] == 180, r["心跳周期"]["原始值"])
    check("请求时间 = 2016-05-19 08:05:00.164",
          r["请求时间"]["解析值"] == "2016-05-19 08:05:00.164", r["请求时间"]["解析值"])
    check("毫秒 00 A4 = 164（不是 41984）", "毫秒=164" in r["请求时间"]["说明"], r["请求时间"]["说明"])


def test_oracle_698_login_response():
    """附录 H.1.1 登录响应：81 00 80 | 三段 date_time"""
    section("oracle：附录 H.1.1「登录」响应（结果字节 + 三段 date_time）")
    apdu = bytes.fromhex(
        "81" "00" "80"
        "07E00513040805000089"
        "07E0051304080501025F"
        "07E005130408050202DA"
    )
    r = DLT69845APDUParser().parse(apdu)
    check("APDU 解析成功", r["解析状态"] == "成功", str(r.get("错误信息", "")))
    check("类型 = LINK-Response", r["APDU类型"] == "LINK-Response", r.get("APDU类型", ""))
    check("结果 = 成功（bit0~2=0）", r["结果"]["解析值"] == 0, r["结果"]["说明"])
    check("时钟可信标志 bit7 = 1", r["结果"]["时钟可信"] is True, r["结果"]["说明"])
    check("请求时间 = 08:05:00.137",
          r["请求时间"]["解析值"] == "2016-05-19 08:05:00.137", r["请求时间"]["解析值"])
    check("收到时间 = 08:05:01.607",
          r["收到时间"]["解析值"] == "2016-05-19 08:05:01.607", r["收到时间"]["解析值"])
    check("响应时间 = 08:05:02.730",
          r["响应时间"]["解析值"] == "2016-05-19 08:05:02.730", r["响应时间"]["解析值"])


def test_oracle_698_multi_object_response():
    """附录 H.3.2 读取多个对象属性：数组 long-unsigned 2413 与 double-long 1000"""
    section("oracle：附录 H.3.2「读取多个对象属性」响应")
    apdu = bytes.fromhex(
        "85" "02" "02" "02"
        "20000200" "01" "01" "03" "12096D" "12096D" "12096D"
        "20010200" "01" "01" "03" "05000003E8" "05000003E8" "05000003E8"
        "00" "00"
    )
    r = DLT69845APDUParser().parse(apdu)
    check("APDU 解析成功", r["解析状态"] == "成功", str(r.get("错误信息", "")))
    check("子类型 = GetResponseNormalList", r["子类型"] == "GetResponseNormalList", r.get("子类型", ""))
    items = r["列表"]
    check("列表 2 项", len(items) == 2, str(len(items)))
    volt = [e["解析值"] for e in items[0]["数据"]["解析值"]]
    check("电压数组三项 = 2413（12 09 6D 大端）", volt == [2413, 2413, 2413], str(volt))
    check("OI 大端 = 0x2000（电压）", items[0]["OAD"]["解析值"]["OI"] == "0x2000",
          items[0]["OAD"]["解析值"]["OI"])
    cur = [e["解析值"] for e in items[1]["数据"]["解析值"]]
    check("电流数组三项 = 1000（05 00 00 03 E8 大端）", cur == [1000, 1000, 1000], str(cur))
    check("数据业务按 10^-1 显示 241.3 V",
          items[0]["数据业务"].get("A相") == "241.3 V", str(items[0].get("数据业务")))


def test_axdr_roundtrip_and_endianness():
    """A-XDR 编解码往返 + 大端铁证"""
    section("A-XDR 编解码：多字节大端 + 往返自洽")
    c = AXDRCoder()
    cases = [
        (0x0F, -2, "integer(1B)"),
        (0x11, 2, "unsigned(1B)"),
        (0x10, -2, "long(2B)"),
        (0x12, 4660, "long-unsigned(2B)"),
        (0x05, -24880, "double-long(4B)"),
        (0x06, 4294934224, "double-long-unsigned(4B)"),
        (0x14, -3, "long64(8B)"),
        (0x15, 3, "long64-unsigned(8B)"),
        (0x17, 1.5, "float32"),
        (0x18, 2.5, "float64"),
    ]
    for tag, val, label in cases:
        encoded = c.encode(val, tag)
        back = c.decode(encoded, 0)[0]["解析值"]
        ok = abs(back - val) < 1e-6 if isinstance(val, float) else back == val
        check(f"{label} 往返", ok, f"{val} → {encoded.hex().upper()} → {back}")
    check("long-unsigned 4660 = 12 34（大端）",
          c.encode(4660, 0x12).hex().upper() == "121234", c.encode(4660, 0x12).hex().upper())
    check("double-long -24880 = 05 FF FF 9E D0",
          c.encode(-24880, 0x05).hex().upper() == "05FFFF9ED0", c.encode(-24880, 0x05).hex().upper())
    check("OAD OI 大端：00 01 → 0x0001",
          c.decode(bytes.fromhex("5100010200"), 0)[0]["解析值"]["OI"] == "0x0001")
    check("OAD OI 大端：20 00 → 0x2000",
          c.decode(bytes.fromhex("5120000200"), 0)[0]["解析值"]["OI"] == "0x2000")


def test_frame_gen_roundtrip():
    """组帧侧同步大端 + 组帧↔解析自洽"""
    section("组帧：心跳周期大端，且组帧→解析自洽")
    gen, parser = DLT69845FrameGenerator(), DLT69845Parser()
    sa = bytes([0x01, 0x07, 0x08])
    frame = gen.generate_link_request(sa, ca=0x09, piid=0x00, req_type=0x00, heartbeat=180)
    check("帧内出现 00 B4（大端心跳周期）", b"\x00\xb4" in frame, frame.hex().upper())
    check("帧内不含 B4 00（小端）", b"\xb4\x00" not in frame, frame.hex().upper())
    apdu = parser.parse(frame)["链路用户数据"]["APDU"]
    check("回解析心跳周期 = 180", apdu["心跳周期"]["解析值"] == 180, str(apdu["心跳周期"]))
    check("回解析请求类型 = 登录", apdu["请求类型"]["解析值"] == 0, apdu["请求类型"]["说明"])
    resp = gen.generate_link_response(sa, ca=0x09, piid_acd=0x00, result=0x00, heartbeat=180)
    check("响应帧同样 00 B4", b"\x00\xb4" in resp, resp.hex().upper())


def main():
    test_link_layer_stays_little_endian()
    test_user_frame_value_big_endian()
    test_oracle_698_login_request()
    test_oracle_698_login_response()
    test_oracle_698_multi_object_response()
    test_axdr_roundtrip_and_endianness()
    test_frame_gen_roundtrip()

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    sys.stdout.flush()
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
