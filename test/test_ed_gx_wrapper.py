# -*- coding: utf-8 -*-
"""ED 广西台体包装头（14B 头）offscreen 回归测试

背景：广西台体发射机报文同样 ED..EE 包装，但数据域公共头为 8 字节
（时间戳4+物理信道1+物理块个数1+物理块长度2），业务帧自第 14 字节起；
PLC2.0 台体公共头 9 字节（多 Payload CRC 1 字节），业务帧自第 15 字节起。

覆盖：
  1. wrapper="gx" 解析：业务偏移=14、业务字节正确、包装头标题/物理块长度行正确
  2. wrapper="plc2" 同帧：业务偏移=15（错位 1 字节，证明格式必须可选）
  3. _extract_business_from_ed_frame 双格式业务提取
  4. ED 包装格式下拉：两项、默认 plc2、切换后 _ed_wrapper_mode 生效
  5. 批量提取链路 _extract_csg_new_gen_frames 在 gx 模式下剥离 14B 头

直接运行: python test_ed_gx_wrapper.py
"""

import _path_setup  # noqa: E402

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASS += 1
    else:
        FAILURES.append(name)


def _wrap_ed(data: bytes) -> bytes:
    """ED..EE 包装：ED+帧长(2,LE)+ctrl1+ctrl2+EF+data+CS+EE"""
    frame_len = len(data) + 4
    body = bytes([0x00, 0x02, 0xEF]) + data  # ctrl1=数据报文 ctrl2=0x02 EF
    # CS = ED..数据域末所有字节求和取低8bit（帧长两字节逐字节累加）
    cs = (
        0xED
        + (frame_len & 0xFF)
        + ((frame_len >> 8) & 0xFF)
        + sum(body)
    ) & 0xFF
    return (
        bytes([0xED])
        + frame_len.to_bytes(2, "little")
        + body
        + bytes([cs, 0xEE])
    )


def _build_gx_frame(business: bytes, pb_len: int = 136) -> bytes:
    """构造广西台体 ED..EE 包装帧：8 字节数据域公共头"""
    data = (
        (0).to_bytes(4, "little")  # 时间戳
        + bytes([0x01])  # 物理信道 HPLC
        + bytes([0x01])  # 物理块个数
        + pb_len.to_bytes(2, "little")  # 单个物理块长度
        + business
    )
    return _wrap_ed(data)


def _build_plc2_frame(business: bytes, pb_len: int = 136) -> bytes:
    """构造 PLC2.0 台体 ED..EE 包装帧：9 字节数据域公共头"""
    data = (
        bytes([0x01])  # 物理信道 HPLC
        + (0).to_bytes(4, "little")  # 时间戳
        + bytes([0x01])  # 物理块个数
        + bytes([0x00])  # Payload CRC/保留
        + pb_len.to_bytes(2, "little")  # 单个物理块长度
        + business
    )
    return _wrap_ed(data)


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    import main_gui
    from test_csg_sequence_model import SOF_DOWN  # FC16+PB136=152B 业务帧

    win = main_gui.MainWindow()
    win.current_protocol = 9
    app.processEvents()

    frame = _build_gx_frame(SOF_DOWN)

    # ── 1. gx 解析：业务偏移 14 ──
    rows, business, off = win._parse_ed_monitor_header(frame, wrapper="gx")
    check("gx 包装头解析成功", rows is not None and business is not None)
    check("gx 业务偏移=14", off == 14, f"off={off}")
    check("gx 业务字节=原始业务帧", business == SOF_DOWN)
    check(
        "gx 包装头标题行",
        rows is not None and rows[0][0] == "── 广西台体监控包装头 ──",
        f"title={rows[0][0] if rows else None}",
    )
    pb_row = next((r for r in rows if r[0] == "单个物理块长度"), None)
    check(
        "gx 物理块长度行=136 且偏移 12~13",
        pb_row is not None and pb_row[1] == "136" and pb_row[4] == 12,
        f"pb_row={pb_row}",
    )
    check(
        "gx 无 Payload CRC 行",
        all(r[0] != "Payload CRC" for r in rows),
    )

    # ── 2. plc2 同帧：偏移 15（错位证明格式必须可选）──
    _rows2, business2, off2 = win._parse_ed_monitor_header(frame, wrapper="plc2")
    check("plc2 同帧业务偏移=15", off2 == 15, f"off2={off2}")
    check(
        "plc2 同帧业务错位1字节",
        business2 == SOF_DOWN[1:],
        f"head={business2[:8].hex()}",
    )

    # ── 3. 业务提取双格式 ──
    bh_gx, dt_gx = win._extract_business_from_ed_frame(frame.hex().upper(), "gx")
    check(
        "gx 业务提取=原始业务hex",
        bh_gx == SOF_DOWN.hex().upper(),
        f"head={bh_gx[:16]}",
    )
    check("gx 类型描述", dt_gx == "FC+Payload数据", f"dt={dt_gx}")
    bh_plc2, _dt2 = win._extract_business_from_ed_frame(frame.hex().upper(), "plc2")
    check("plc2 提取结果与 gx 不同", bh_plc2 != bh_gx)

    # ── 4. 下拉控件与自动识别 ──
    combo = win.ed_wrapper_combo
    check("下拉三项", combo.count() == 3, f"count={combo.count()}")
    check("默认自动识别", win._ed_wrapper_mode() == "auto")
    check(
        "自动识别 gx 帧",
        win._detect_ed_wrapper(frame) == "gx",
        f"det={win._detect_ed_wrapper(frame)}",
    )
    plc2_frame = _build_plc2_frame(SOF_DOWN)
    check(
        "自动识别 plc2 帧",
        win._detect_ed_wrapper(plc2_frame) == "plc2",
        f"det={win._detect_ed_wrapper(plc2_frame)}",
    )
    check(
        "auto 模式逐帧格式(gx帧)",
        win._ed_wrapper_for_frame(frame) == "gx",
    )
    check(
        "auto 模式逐帧格式(plc2帧)",
        win._ed_wrapper_for_frame(plc2_frame) == "plc2",
    )
    combo.setCurrentIndex(combo.findData("gx"))
    check("手动 gx 覆盖自动", win._ed_wrapper_for_frame(plc2_frame) == "gx")
    combo.setCurrentIndex(combo.findData("auto"))

    # ── 4b. 不传 wrapper 的调用点默认走自动识别（历史缺陷：默认硬编码 plc2，
    #        快捷解析小窗漏传 wrapper → gx 帧按 9B 头错位 1 字节）──
    rows_d, business_d, off_d = win._parse_ed_monitor_header(frame)
    check(
        "默认(不传 wrapper)按自动识别取 gx 布局：偏移=14",
        off_d == 14 and business_d == SOF_DOWN,
        f"off={off_d} head={business_d[:8].hex() if business_d else None}",
    )
    check(
        "默认调用标题行为广西台体",
        rows_d is not None and rows_d[0][0] == "── 广西台体监控包装头 ──",
        f"title={rows_d[0][0] if rows_d else None}",
    )
    bh_d, dt_d = win._extract_business_from_ed_frame(frame.hex().upper())
    check(
        "业务提取默认(不传 wrapper)同样识别 gx",
        bh_d == SOF_DOWN.hex().upper() and dt_d == "FC+Payload数据",
        f"head={bh_d[:16]}",
    )

    # ── 5. 批量提取链路在 auto 模式剥离 gx 14B 头 ──
    frames = win._extract_csg_new_gen_frames(frame.hex().upper())
    check("批量提取 1 帧", len(frames) == 1, f"n={len(frames)}")
    hex_out, ed_type = frames[0][:2]
    check("批量提取含行号", frames[0][2] == 0, f"line_no={frames[0][2]}")
    check(
        "批量提取业务帧(auto识别gx)",
        hex_out == SOF_DOWN.hex().upper() and ed_type == "FC+Payload数据",
        f"head={hex_out[:16]} type={ed_type}",
    )
    # auto 模式 plc2 帧同样正确剥离 15B 头
    frames_p = win._extract_csg_new_gen_frames(plc2_frame.hex().upper())
    hex_p, type_p = frames_p[0][:2]
    check(
        "批量提取业务帧(auto识别plc2)",
        hex_p == SOF_DOWN.hex().upper() and type_p == "FC+Payload数据",
        f"head={hex_p[:16]} type={type_p}",
    )
    # 切回 plc2：批量链路不再剥离 gx 头（业务错位→保留原始 ED 帧或空业务）
    combo.setCurrentIndex(combo.findData("plc2"))
    frames2 = win._extract_csg_new_gen_frames(frame.hex().upper())
    hex_out2, ed_type2 = frames2[0][:2]
    check(
        "plc2 模式不误剥 gx 头",
        hex_out2 != SOF_DOWN.hex().upper(),
        f"head={hex_out2[:16]} type={ed_type2}",
    )

    win.close()
    win.deleteLater()
    app.processEvents()

    print("=" * 56)
    if FAILURES:
        print(f"共 {len(FAILURES)} 项失败: {FAILURES}")
        raise SystemExit(1)
    print(f"全部测试通过（{PASS} 项）✓")


if __name__ == "__main__":
    main()
