# -*- coding: utf-8 -*-
"""南网光伏无线模组接口手册（V1.6）扩展 **组帧** 回归。

覆盖：
  [1] 模块规模：12 个 DI 都有字段模板与编码器（缺一即红）
  [2] 扩展控制码：06H / 86H / 1EH / 9EH 可用，控制码与手册一致
  [3] 手册原文发送帧逐字节复现（4.4.1 读地址 / 4.4.2 频段 / 4.4.3 地址列表 / 4.4.6 拓扑）
  [4] 12 个 DI 的「组帧 → 解析」闭环（编码必须能被 parse_wireless_di 还原）
  [5] 关键口径：超时 T 按 BCD、信道 2 字节 BCD 低字节在前、地址列表 1+6×M、
      04900103 按 108 字节补齐（手册长度列 108 ≠ 字段累加 106）
  [6] get_di_info 无线优先：04E60001 不再落到附件1 的 length=16
  [7] length_warning 用无线口径，且读请求不带数据域时不误报
  [8] 读请求数据域：02EB0000 带 Z+C+T+DATA，其余无线 DI 只带 DI
  [9] 1EH 在网状态上报 / 9EH 确认（§4.3.1 示例帧）
  [10] 反例与非法输入（中文报错，不静默）

运行: python -u test/test_dlt645_pv_wireless_frame.py
"""

import _path_setup  # noqa: E402,F401

import sys  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # noqa: BLE001
    pass

import dlt645_frame_schema as S  # noqa: E402
import dlt645_pv_wireless_frame as WF  # noqa: E402
from dlt645_frame_gen import DLT645FrameGenerator, encode_di  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402
from dlt645_pv_wireless import WIRELESS_DI_MAP, parse_wireless_di  # noqa: E402

PASS = 0
FAIL = 0

GEN = DLT645FrameGenerator()
PARSER = DLT645Parser()

ADDR = "880000000099"      # 手册示例里协议转换单元无线模组的地址（4.4.x）


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}")


def hexs(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def rows_of(di: str, fv: dict, ctrl: int = 0x91):
    """组帧数据域 → 解析行（parse_wireless_di 认「含 DI 的完整数据域」）。"""
    payload = WF.build_wireless_payload(di, fv)
    rows, _name = parse_wireless_di(di, ctrl, encode_di(di) + payload)
    return rows


def row_value(rows, key: str):
    """按行名前缀取解析值（第 3 列）。"""
    for r in rows:
        if str(r[0]).strip().endswith(key):
            return r[2]
    return None


# ── [1] 模块规模 ────────────────────────────────────────────────────
def test_scale():
    check(WF.field_count() == 12, f"12 个 DI 都有字段模板（当前 {WF.field_count()}）")
    check(WF.missing_builders() == [], f"无缺模板/编码器的 DI：{WF.missing_builders()}")
    for di in WIRELESS_DI_MAP:
        fields = S.build_di_fields(di)
        check(bool(fields) and all(f["name"] != "数据内容" for f in fields),
              f"{di} 走无线结构化模板（{len(fields)} 个字段），不退化成裸 hex")


# ── [2] 扩展控制码 ──────────────────────────────────────────────────
def test_control_codes():
    cases = [(("req", 0x06), 0x06, "上报确认应答"), (("rsp", 0x06), 0x86, "主动上报"),
             (("req", 0x1E), 0x1E, "在网状态上报"), (("rsp", 0x1E), 0x9E, "在网状态确认")]
    for key, want_ctrl, want_name in cases:
        spec = S.get_command(key)
        ctrl = GEN.build_control(spec["func"], dir_bit=spec["dir"], err=bool(spec.get("err")))
        check(ctrl == want_ctrl, f"{key} → C={ctrl:02X}H（应为 {want_ctrl:02X}H）")
        check(want_name in spec["name"], f"{key} 名称含「{want_name}」：{spec['name']}")
    names = [t for _k, _g, t in S.list_commands()]
    check(any("86H" in n for n in names), "命令下拉含 86H 主动上报")
    check(any("1EH" in n for n in names), "命令下拉含 1EH 在网状态上报")
    check(any("9EH" in n for n in names), "命令下拉含 9EH 在网状态确认")
    check(any("06H" in n for n in names), "命令下拉含 06H 上报确认")


# ── [3] 手册原文发送帧逐字节复现 ────────────────────────────────────
def test_manual_frames():
    # 4.4.1 读通信地址：68 AA×6 68 13 00 DF 16
    fr = GEN.generate_frame(("req", 0x13), {})
    check(hexs(fr) == "68 AA AA AA AA AA AA 68 13 00 DF 16",
          f"§4.4.1 读地址请求复现：{hexs(fr)}")

    # 4.4.2 获取无线频段信息：68 99 00 00 00 00 88 68 11 04 35 33 19 37 BE 16
    fr = GEN.generate_frame(("req", 0x11), {"数据标识 DI": "04E60002"}, ADDR)
    check(hexs(fr) == "68 99 00 00 00 00 88 68 11 04 35 33 19 37 BE 16",
          f"§4.4.2 读频段请求复现：{hexs(fr)}")

    # 4.4.3 地址列表请求：68 99 00 00 00 00 88 68 11 04 34 33 19 37 BD 16
    fr = GEN.generate_frame(("req", 0x11), {"数据标识 DI": "04E60001"}, ADDR)
    check(hexs(fr) == "68 99 00 00 00 00 88 68 11 04 34 33 19 37 BD 16",
          f"§4.4.3 读地址列表请求复现：{hexs(fr)}")

    # 4.4.6 拓扑请求：68 99 00 00 00 00 88 68 11 04 33 34 C3 37 67 16
    fr = GEN.generate_frame(("req", 0x11), {"数据标识 DI": "04900100"}, ADDR)
    check(hexs(fr) == "68 99 00 00 00 00 88 68 11 04 33 34 C3 37 67 16",
          f"§4.4.6 读拓扑请求复现：{hexs(fr)}")

    # 4.4.4 数据转发请求：68 03 12 88 60 00 00 68 11 0A 33 33 1E 35 3B 35 43 33 33 33 93 16
    # 手册示例 CS 为 93H（应为 EDH，原文笔误），故这里只比对到数据域
    fr = GEN.generate_frame(("req", 0x11),
                            {"数据标识 DI": "02EB0000", "波特率特征字 Z": "08",
                             "校验方式 C": "02", "超时 T（BCD）": "10",
                             "转发数据（逆变器报文）": "00 00 00"},
                            "000060881203")
    check(hexs(fr[:-2]) == "68 03 12 88 60 00 00 68 11 0A 33 33 1E 35 3B 35 43 33 33 33",
          f"§4.4.4 数据转发请求（帧头+数据域）复现：{hexs(fr[:-2])}")
    check(len(fr) == 22 and fr[9] == 0x0A, f"§4.4.4 L=0AH（07H + 3 字节转发数据），实际 L={fr[9]:02X}H")


# ── [4] 12 个 DI 的组帧→解析闭环 ─────────────────────────────────────
ROUNDTRIP = {
    "02EB0000": ({"波特率特征字 Z": "08", "校验方式 C": "02", "超时 T（BCD）": "10",
                  "转发数据（逆变器报文）": "11 22 33"}, "2400bps"),
    "04E60001": ({"地址列表": "000006881031,000006881203,000006881252,"
                             "000006881253,075506980071"}, "5 台"),
    "04E60002": ({"无线调制方式": "2", "无线信道编号": "32", "信道协商使能": "1"},
                 "32（BCD，低字节在前）"),
    "04900100": ({"拓扑条目": "000006881031,50,000006881034;"
                             "000006881252,30,FFFFFFFFFFFF"}, "2 个"),
    "04900101": ({"块状态字（位图 hex）": "FF 07"}, "最高置位 bit10"),
    "04900102": ({"升级文件名（ASCII）": "fw_v16.bin", "文件校验 CRC32": "78563412",
                  "升级状态": "6"}, "升级成功"),
    "04900103": ({"升级文件名（ASCII）": "fw_v16.bin", "文件大小（字节）": "65536",
                  "文件校验 CRC32": "78563412", "升级块大小（字节）": "241"},
                 "65536 字节"),
    "04900104": ({"升级块序号": "3", "升级块数据": "AA BB CC"}, "3"),
    "04900105": ({"最大升级块大小（字节）": "241"}, "241 字节"),
    "04900106": ({"执行升级时间": "2611010830"}, "2026-11-01 08:30"),
    "04900107": ({"版本信息（ASCII）": "V1.6.0"}, "V1.6.0"),
    "028100FF": ({"在网状态": "1"}, "在网"),
}


def test_roundtrip():
    for di, (fv, expect) in ROUNDTRIP.items():
        rows = rows_of(di, fv)
        joined = " | ".join(str(r[2]) for r in rows)
        check(expect in joined, f"{di} 回读含「{expect}」：{joined[:70]}")
        check(not any("⚠" in str(r[0]) for r in rows),
              f"{di} 解析无告警行：{[r[0] for r in rows if '⚠' in str(r[0])]}")


def test_roundtrip_details():
    # 地址列表：每个地址都要原样还原（BCD 低位在前）
    rows = rows_of("04E60001", {"地址列表": "000006881031,000006881203,075506980071"})
    got = [r[2] for r in rows if "地址" in str(r[0])]
    check(got == ["000006881031", "000006881203", "075506980071"],
          f"地址列表逐个还原：{got}")

    # 拓扑：父节点全 FF → 未入网
    rows = rows_of("04900100", {"拓扑条目": "000006881252,30,FFFFFFFFFFFF"})
    check(any("未入网" in str(r[2]) for r in rows), "拓扑父节点 FFFFFFFFFFFF → 未入网")

    # 数据转发：T=10H 必须按 BCD 读成 1000ms（不是 1600ms）
    rows = rows_of("02EB0000", {"波特率特征字 Z": "08", "校验方式 C": "02",
                                "超时 T（BCD）": "10"})
    check(any("1000 ms" in str(r[2]) for r in rows), "超时 T=10H → 1000ms（BCD 口径）")
    check(not any("1600" in str(r[2]) for r in rows), "超时 T 未被误算成 1600ms")

    # 执行升级时间全 FF → 立即执行
    rows = rows_of("04900106", {"执行升级时间": "FF"})
    check(any("立即执行" in str(r[2]) for r in rows), "执行时间 FF → 立即执行")
    rows = rows_of("04900106", {"执行升级时间": ""})
    check(any("立即执行" in str(r[2]) for r in rows), "执行时间留空 → 立即执行")


# ── [5] 关键口径 ───────────────────────────────────────────────────
def test_key_conventions():
    # 信道 2 字节 BCD 低字节在前：信道 32 → 线上 32 00
    payload = WF.build_wireless_payload("04E60002", {"无线调制方式": "2",
                                                     "无线信道编号": "32",
                                                     "信道协商使能": "1"})
    check(payload == bytes([0x02, 0x32, 0x00, 0x01]),
          f"信道 32 线上为 32 00（低字节在前）：{hexs(payload)}")
    # 信道 200 → 线上 00 02
    payload = WF.build_wireless_payload("04E60002", {"无线信道编号": "200"})
    check(payload[1:3] == bytes([0x00, 0x02]), f"信道 200 线上为 00 02：{hexs(payload[1:3])}")

    # 地址列表 1+6×M
    payload = WF.build_wireless_payload("04E60001", {"地址列表": "000006881031"})
    check(len(payload) == 1 + 6 and payload[0] == 1, f"地址列表长度 = 1+6×M：{hexs(payload)}")
    check(payload[1:] == bytes.fromhex("311088060000"), "地址线上低字节在前")

    # 04900103 固定 108 字节（手册长度列 108，字段累加 106，补 2 字节尾部保留）
    payload = WF.build_wireless_payload("04900103", {"升级文件名（ASCII）": "a",
                                                     "文件大小（字节）": "1",
                                                     "升级块大小（字节）": "128"})
    check(len(payload) == 108, f"04900103 数据域 108 字节（当前 {len(payload)}）")
    check(payload[:32] == b"a" + b"\x00" * 31, "文件名 ASCII 32 字节右补 0x00")
    check(payload[32:36] == (1).to_bytes(4, "little"), "文件大小 4 字节低字节在前")
    check(payload[40:42] == (128).to_bytes(2, "little"), "块大小 2 字节低字节在前")

    # 04900102 固定 37 字节
    payload = WF.build_wireless_payload("04900102", {"升级状态": "6"})
    check(len(payload) == 37, f"04900102 数据域 37 字节（当前 {len(payload)}）")
    check(payload[36] == 6, "升级状态在第 37 字节")

    # 04900106 时间 5 字节 BCD 低字节在前
    payload = WF.build_wireless_payload("04900106", {"执行升级时间": "2611010830"})
    check(payload == bytes.fromhex("3008011126"),
          f"执行时间 2611010830 线上为 30 08 01 11 26：{hexs(payload)}")

    # 04900105 块大小 2 字节 BIN
    payload = WF.build_wireless_payload("04900105", {"最大升级块大小（字节）": "241"})
    check(payload == bytes([0xF1, 0x00]), f"块大小 241 → F1 00：{hexs(payload)}")

    # 04900104 块序号 2 字节 BIN
    payload = WF.build_wireless_payload("04900104", {"升级块序号": "258",
                                                     "升级块数据": "AA"})
    check(payload == bytes([0x02, 0x01, 0xAA]), f"块序号 258 → 02 01：{hexs(payload)}")


# ── [6] get_di_info 无线优先 ────────────────────────────────────────
def test_di_info_priority():
    info = S.get_di_info("04E60001")
    check(info["name"] == "下挂光伏逆变器地址列表", f"04E60001 名称取无线手册：{info['name']}")
    check(info["length"] == 0, f"04E60001 长度按 1+6×M 记为不定长（当前 {info['length']}）")
    check(info["data_type"] == "M|addr×M", f"04E60001 格式取无线口径：{info['data_type']}")
    check(S.get_di_info("04900103")["length"] == 108, "04900103 定长 108")
    # 非无线 DI 不受影响
    check(S.get_di_info("00010000")["name"] != "", "标准 DI 仍走 dlt645_di.json")


# ── [7] length_warning ─────────────────────────────────────────────
def test_length_warning():
    # 定长 DI 填对 → 无警告
    warn = S.length_warning(("rsp", 0x11), {"数据标识 DI": "04900105",
                                            "数据值": "F1 00"})
    check(not warn, f"04900105 长度正确时无警告：{warn}")
    # 不定长 DI → 不校验
    warn = S.length_warning(("rsp", 0x11), {"数据标识 DI": "04E60001",
                                            "地址列表": "000006881031"})
    check(not warn, f"04E60001（不定长）不产生长度警告：{warn}")
    # 读请求里不带数据域的无线 DI → 不误报
    warn = S.length_warning(("req", 0x11), {"数据标识 DI": "04900105"})
    check(not warn, f"读请求 04900105 不误报长度：{warn}")
    # 标准 DI 的长度校验仍然生效
    warn = S.length_warning(("rsp", 0x11), {"数据标识 DI": "00010000", "数据值": "12"})
    check("声明数据长度" in warn or not warn, f"标准 DI 校验路径不崩：{warn[:40]}")


# ── [8] 读请求数据域 ───────────────────────────────────────────────
def test_request_payload():
    # 02EB0000 读请求必须带 Z + C + T + DATA
    data = S.build_data(("req", 0x11), {"数据标识 DI": "02EB0000",
                                        "波特率特征字 Z": "08", "校验方式 C": "02",
                                        "超时 T（BCD）": "10",
                                        "转发数据（逆变器报文）": "11 22"})
    check(data == encode_di("02EB0000") + bytes([0x08, 0x02, 0x10, 0x11, 0x22]),
          f"02EB0000 读请求带 Z/C/T/DATA：{hexs(data)}")
    # 其余无线 DI 读请求只带 DI
    for di in ("04E60001", "04E60002", "04900100", "04900107"):
        data = S.build_data(("req", 0x11), {"数据标识 DI": di})
        check(data == encode_di(di), f"{di} 读请求只带 DI：{hexs(data)}")
    # 标准 DI 读请求不受影响
    check(S.build_data(("req", 0x11), {"数据标识 DI": "00010000"})
          == encode_di("00010000"), "标准 DI 读请求仍只带 DI")


# ── [9] 1EH / 9EH ─────────────────────────────────────────────────
def test_online_frames():
    fr = GEN.generate_frame(("req", 0x1E), {"在网状态": "1"}, "A6A5A4A3A2A1")
    check(hexs(fr[:-2]) == "68 A1 A2 A3 A4 A5 A6 68 1E 05 32 33 B4 35 34",
          f"§4.3.1 在网状态上报（帧头+数据域）：{hexs(fr)}")
    check(len(fr) == 17, f"在网状态上报共 17 字节（当前 {len(fr)}）")

    fr = GEN.generate_frame(("rsp", 0x1E), {}, "A6A5A4A3A2A1")
    check(hexs(fr[:-2]) == "68 A1 A2 A3 A4 A5 A6 68 9E 00",
          f"§4.3.1 在网状态确认（L=00H）：{hexs(fr)}")
    check(len(fr) == 12, f"确认帧共 12 字节（当前 {len(fr)}）")

    # 离网
    fr = GEN.generate_frame(("req", 0x1E), {"在网状态": "0"}, "A6A5A4A3A2A1")
    check(hexs(fr).split()[11] == "33", f"在网状态 0 → 数据域末字节 33H：{hexs(fr)}")


# ── [10] 反例与非法输入 ────────────────────────────────────────────
def test_negative():
    def expect_value_error(fn, keyword, msg):
        try:
            fn()
        except ValueError as exc:
            check(keyword in str(exc), f"{msg}：{exc}")
        except Exception as exc:      # noqa: BLE001
            check(False, f"{msg}：抛了 {type(exc).__name__} 而非 ValueError：{exc}")
        else:
            check(False, f"{msg}：应当报错却通过了")

    expect_value_error(lambda: WF.build_wireless_payload(
        "04E60001", {"地址列表": "000006881031,000006881203", "有效数量 M": "5"}),
        "不一致", "M 与地址个数不一致时报错")
    expect_value_error(lambda: WF.build_wireless_payload("04E60002", {"无线信道编号": "300"}),
                       "应在 1~200", "信道越界报错")
    expect_value_error(lambda: WF.build_wireless_payload("04900102", {"升级状态": "300"}),
                       "应在 0~255", "升级状态越界报错")
    expect_value_error(lambda: WF.build_wireless_payload("04900107", {"版本信息（ASCII）": "版本"}),
                       "ASCII", "非 ASCII 版本号报错")
    expect_value_error(lambda: WF.build_wireless_payload("04900106", {"执行升级时间": "2611"}),
                       "10 位", "执行时间位数不对报错")
    expect_value_error(lambda: WF.build_wireless_payload(
        "04E60001", {"地址列表": " ".join(["000006881031"] * 13)}),
        "最多 12", "地址超过 12 项报错")
    expect_value_error(lambda: WF.build_wireless_payload("04900100", {"拓扑条目": "000006881031"}),
                       "至少要有", "拓扑条目缺信号质量报错")

    # 非本手册 DI：三个接口都返回 None，标准路径不受影响
    check(WF.build_wireless_fields("00010000") is None, "非无线 DI：字段返回 None")
    check(WF.build_wireless_payload("00010000", {}) is None, "非无线 DI：编码返回 None")
    check(WF.wireless_request_extra("00010000", {}) is None, "非无线 DI：请求附加返回 None")
    check(WF.wireless_di_info("00010000") is None, "非无线 DI：info 返回 None")


if __name__ == "__main__":
    print("=" * 62)
    print("南网光伏无线模组接口手册 V1.6 · 组帧扩展回归")
    print("=" * 62)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print(f"\n[{fn.__name__}]")
        try:
            fn()
        except Exception as exc:      # noqa: BLE001
            FAIL += 1
            print(f"  [ERR ] {type(exc).__name__}: {exc}")
    print("\n" + "=" * 62)
    print(f"结果：{PASS} 通过，{FAIL} 失败")
    print("=" * 62)
    raise SystemExit(1 if FAIL else 0)
