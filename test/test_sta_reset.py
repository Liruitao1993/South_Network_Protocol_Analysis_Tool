# -*- coding: utf-8 -*-
"""STA 硬件初始化（复位）命令回归测试。

现场帧：68 AA AA AA AA AA AA 68 14 0C 34 37 D3 37 33 6A 3D D3 33 33 33 33 DA 16
用途：被测模组固定在工装底座无法断电，异常时用这条 645 广播写数据命令代替上下电。
覆盖：组帧逐字节一致 / 识别 / 645 虚拟表处置（广播静默、单播 94H）/
      698 虚拟表提取器不把 645 帧当巨帧卡死 / 698 串口线程收到即正确处理。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sta_reset
from dlt645_sim.engine import DLT645MeterSim
from meter_sim import link_layer

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def test_frame():
    print("Test: 复位帧组帧与识别")
    f = sta_reset.build_frame()
    check("与现场实测帧逐字节一致", f == sta_reset.REFERENCE_FRAME, f.hex(" "))
    check("帧长 24", len(f) == 24, str(len(f)))
    check("帧尾 16", f[-1] == 0x16)
    check("控制码 0x14", f[8] == 0x14, hex(f[8]))
    check("地址域广播 AA×6", f[1:7] == b"\xAA" * 6)
    check("CS 求和校验", (sum(f[:-2]) & 0xFF) == f[-2], hex(f[-2]))
    info = sta_reset.parse_frame(f)
    check("DI 识别 04A00401", info and info["di"] == "04A00401")
    check("密码 00370AA0", info and info["password"] == "00370AA0")
    check("判定为广播", info and info["broadcast"] is True)
    check("说明含用途文案", "STA 硬件初始化（复位）" in sta_reset.describe(f))
    # 单播
    uni = sta_reset.build_frame("260526000028")
    check("单播帧地址正确", uni[1:7] == bytes.fromhex("280000260526"), uni[1:7].hex())
    check("单播不判为广播", sta_reset.parse_frame(uni)["broadcast"] is False)
    # 非复位帧
    other = bytes.fromhex("681234567890681104333333338B16")
    check("普通读帧不误判", not sta_reset.is_sta_reset_frame(other))
    check("scan 能从噪声中挑出", sta_reset.scan(b"\x00\x11" + f + b"\x16") == [f])


def test_645_engine():
    print("Test: 645 虚拟表处置")
    f = sta_reset.build_frame()
    sim = DLT645MeterSim("260526000028")
    resps = sim.handle_frame(f)
    check("广播复位不应答", resps == [], [r.hex(" ") for r in resps])
    check("广播复位有中文说明", "STA 硬件初始化（复位）" in (sim.last_note or ""),
          sim.last_note or "")
    check("广播复位不再报错", sim.last_error is None, str(sim.last_error))

    uni = sta_reset.build_frame("260526000028")
    sim2 = DLT645MeterSim("260526000028")
    r2 = sim2.handle_frame(uni)
    check("单播复位回 1 帧", len(r2) == 1, str(len(r2)))
    if r2:
        check("应答控制码 94H", r2[0][8] == 0x94, hex(r2[0][8]))
        check("应答长度 00", r2[0][9] == 0x00)
        check("应答地址=本机地址", r2[0][1:7] == bytes.fromhex("280000260526"),
              r2[0][1:7].hex())

    # 其它 DI 的 14H 仍按异常应答（不改变既有语义）
    other = bytes.fromhex("682605260000681C0C" + "33333333" + "33333333" + "33333333")
    other = other + bytes([sum(other) & 0xFF]) + b"\x16"
    sim3 = DLT645MeterSim("260526000028")
    r3 = sim3.handle_frame(other)
    check("其它写数据仍异常应答", r3 and (r3[0][8] & 0x40) != 0,
          [r.hex(" ") for r in r3])


def test_698_framing():
    print("Test: 698 虚拟表收帧不被 645 帧卡死")
    from dl_t698_45_frame_gen import DLT69845FrameGenerator

    f = sta_reset.build_frame()
    req = DLT69845FrameGenerator().generate_get_request_normal(
        bytes([0x05]) + bytes.fromhex("270000002100"), 0, 0x01,
        bytes.fromhex("20000200"))
    frames, consumed, rest = link_layer.extract_frames(f + req)
    check("645 帧被跳过，698 帧仍提取到", frames == [req],
          [x.hex(" ") for x in frames])
    check("645 帧未被当作 698 巨帧滞留", rest == b"", f"rest={rest!r}")
    check("645 帧单独可提取", link_layer.extract_645_frames(f + req) == [f])
    # 645 帧在末尾（无后续 698）也不应报错
    frames2, consumed2, rest2 = link_layer.extract_frames(req + f)
    check("尾部 645 帧不影响 698 提取", frames2 == [req],
          [x.hex(" ") for x in frames2])
    check("尾部残余为空", rest2 == b"", rest2.hex())


def main():
    print("=" * 52)
    print("STA 硬件初始化（复位）命令回归")
    print("=" * 52)
    test_frame()
    test_645_engine()
    test_698_framing()
    print("=" * 52)
    print(f"共 {PASS + FAIL} 项: {PASS} passed / {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
