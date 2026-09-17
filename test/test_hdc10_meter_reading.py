"""HDC 1.0（协议索引11）抄表报文解析 —— proto_ver NameError 回归

缺陷（现场报障）:
    协议11 + 解析级别「应用层报文(app)」+ 报文ID 0x001/0x002/0x003（抄表类）
    + 报文端口号 0x11 时，`hdc10_parser._parse_meter_reading` 引用了**从未赋值**的
    局部名 `proto_ver` → 抛 NameError，GUI 弹「解析失败：name 'proto_ver' is not defined」，
    该帧完全无法解析。默认「自动识别」级别走 MAC 帧路径、不经过该函数，故缺陷长期潜伏。

修复:
    补 `proto_ver = b0 & 0x3F`（与同文件 `_parse_confirm` / `_parse_timesync` 等 6 处同款写法）。

协议依据:
    HDC 1.0 第 4-3 部分 表3「下行抄表报文」字节0 bit0-5 = 协议版本号；
    §5.3.1.2「协议版本号是 6 比特的字段…考虑兼容性，本版本取值固定为 1」。
"""

import subprocess
import sys
from pathlib import Path

import _path_setup  # noqa: E402,F401

from hdc10_parser import HDC10Parser

ROOT = Path(__file__).resolve().parent.parent

# 用户现场帧：88 字节，端口 0x11 + 报文ID 0x0003「终端主动并发抄表」（规约 DL/T698.45）
USER_FRAME_CONCURRENT = (
    "11 03 00 00 01 02 B3 04 87 44 19 0A 68 49 00 43 05 02 66 00 05 00 20 02 69 4A 10 00 25 05 03 02 50 "
    "04 02 00 01 20 21 02 00 1C 07 EA 09 10 00 00 00 03 00 20 21 02 00 00 00 10 02 00 00 00 20 02 00 00 00 "
    "01 10 DA F7 12 94 1E 1C 22 38 49 D8 94 65 87 90 87 6A 34 40 16"
)

# 报文ID 在应用层报文的偏移 1~2（小端）；0x0001/0x0002/0x0003 均为抄表类
MSG_ID_NAMES = {
    0x001: "终端主动抄表",
    0x002: "路由主动抄表",
    0x003: "终端主动并发抄表",
}


def _parse(hex_str: str, level: str = "app") -> list:
    frame = bytes.fromhex(hex_str.replace(" ", ""))
    return HDC10Parser().parse_to_table(frame, parse_level=level)


def _find(rows: list, name: str) -> tuple:
    """按「去缩进后字段名精确相等」取行（找不到时把表内字段名一并报出，便于定位）"""
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    raise AssertionError(
        f"未找到字段: {name}；表内字段={[str(r[0]).strip() for r in rows]}"
    )


def _val(rows: list, name: str) -> str:
    return str(_find(rows, name)[2]).strip()


def _with_msg_id(frame_hex: str, msg_id: int) -> str:
    """把现场帧的应用层报文ID 改为指定值（保持帧长与其余字节不变）"""
    b = bytearray(bytes.fromhex(frame_hex.replace(" ", "")))
    b[1] = msg_id & 0xFF
    b[2] = (msg_id >> 8) & 0xFF
    return bytes(b).hex().upper()


# ── 1. 缺陷本体：app 级别不再抛 NameError ────────────────────────────────


def test_app_level_no_longer_raises():
    """修复前此处抛 NameError: name 'proto_ver' is not defined"""
    rows = _parse(USER_FRAME_CONCURRENT, "app")
    assert isinstance(rows, list) and rows, "app 级别应产出解析行"
    assert len(rows) >= 12, f"行数异常（{len(rows)} 行），疑似提前中断"


def test_app_level_all_rows_have_four_columns():
    """所有行结构完整（6 元组 → GUI 取前 4 列），防中途抛错留下半截表"""
    rows = _parse(USER_FRAME_CONCURRENT, "app")
    for i, r in enumerate(rows):
        assert len(r) >= 4, f"第 {i} 行字段数不足: {r!r}"


# ── 2. 现场帧 golden 字段 ──────────────────────────────────────────────


def test_application_header_fields():
    """应用层报文头：端口 0x11 / 报文ID 0x0003 / 报文控制字"""
    rows = _parse(USER_FRAME_CONCURRENT, "app")
    assert _val(rows, "报文端口号") == "17", "端口号解析值应为十进制 17（=0x11）"
    assert _val(rows, "报文ID") == "0x0003", "应识别为 0x0003 终端主动并发抄表"
    assert _val(rows, "报文控制字") == "0", "报文控制字 0x00"


def test_proto_ver_is_one():
    """协议版本号补赋值后取 b0 & 0x3F；文档规定本版本固定为 1，现场帧 b0=0x01"""
    rows = _parse(USER_FRAME_CONCURRENT, "app")
    assert _val(rows, "协议版本号") == "1", "协议版本号应为 1（文档 §5.3.1.2）"
    assert str(_find(rows, "协议版本号")[1]).strip() == "0x01", "原始值应为 0x01"


def test_meter_reading_header_fields():
    """抄表报文头：头长 2×4B=8B / 配置字 0 / 规约类型 3=DL/T698.45 / 报文序号"""
    rows = _parse(USER_FRAME_CONCURRENT, "app")
    assert _val(rows, "报文头长度") == "2×4B=8B", "报文头长度 = 2 个 4 字节块"
    assert _val(rows, "配置字") == "0", "并发抄表配置字 0（未重试/否认重试0/最大重试0）"
    assert _val(rows, "转发数据规约类型") == "3", "规约类型 3 = DL/T698.45"
    assert _val(rows, "报文序号") == "17543", "报文序号 0x4487 = 17543"


def test_data_length_and_tail():
    """转发数据长度 75 字节；DATA 起于偏移 12，帧尾 1 字节 0x16 不计入 DATA"""
    frame = bytes.fromhex(USER_FRAME_CONCURRENT.replace(" ", ""))
    rows = _parse(USER_FRAME_CONCURRENT, "app")
    data_row = _find(rows, "数据(DATA)")
    assert _val(rows, "转发数据长度") == "75字节", "声明长度（表3 转发数据长度 12bit）"
    assert str(data_row[2]).strip() == "75字节", "DATA 实际展开长度应与声明一致"
    assert data_row[4] == 12, (
        f"DATA 起始偏移应为 12（应用层头4+报文头8），实际 {data_row[4]}"
    )
    # 帧长 88 = 应用层头 4 + 报文头 8 + DATA 75 + 帧尾 1
    assert len(frame) == 88
    assert frame[-1] == 0x16, "帧尾应为 0x16（1 字节，不在 DATA 显示范围内）"
    assert data_row[5] == 12 + 75 - 1, (
        f"DATA 结束偏移应为 {12 + 75 - 1}，实际 {data_row[5]}"
    )
    assert str(data_row[1]).upper().startswith("68 49 00 43"), (
        "DATA 应为内嵌 698.45 报文起始"
    )


# ── 3. 三类抄表报文（0x001/0x002/0x003）都可用 ─────────────────────────


def test_all_three_meter_reading_msg_ids():
    """三个抄表报文ID 均能解析（修复前都会踩同一个 NameError）"""
    for msg_id, name in MSG_ID_NAMES.items():
        frame_hex = _with_msg_id(USER_FRAME_CONCURRENT, msg_id)
        rows = _parse(frame_hex, "app")
        assert _val(rows, "报文ID") == f"0x{msg_id:04X}", (
            f"0x{msg_id:03X} 报文ID 识别错误"
        )
        # 业务名即报文头字段名（"  {name}报文头"）
        assert f"{name}报文头" in [str(r[0]).strip() for r in rows], (
            f"0x{msg_id:03X} 应展开「{name}报文头」，实际字段={[str(r[0]).strip() for r in rows]}"
        )
        assert _val(rows, "协议版本号") in ("1",), f"0x{msg_id:03X} 协议版本号应为 1"


def test_msg_id_003_is_concurrent_meter_reading():
    """0x0003 的业务名必须落到「终端主动并发抄表」（文档表2 报文ID 含义）"""
    rows = _parse(USER_FRAME_CONCURRENT, "app")
    assert "终端主动并发抄表报文头" in [str(r[0]).strip() for r in rows]


# ── 4. auto 级别回归（修复不得改变既有路径）────────────────────────────


def test_auto_level_output_unchanged():
    """auto 级别走 MAC 帧路径（不进 _parse_meter_reading），输出为修复前基线"""
    rows = _parse(USER_FRAME_CONCURRENT, "auto")
    assert len(rows) == 7, f"auto 级别行数基线为 7，实际 {len(rows)}"
    names = [str(r[0]).strip() for r in rows]
    for expected in ("── MAC帧 ──", "版本", "消息类型", "MSDU长度", "── MSDU + ICV ──"):
        assert expected in names, f"auto 基线缺少字段「{expected}」：{names}"
    assert _val(rows, "版本") == "1", "单跳帧协议（短帧头）"


def test_auto_level_does_not_hit_meter_reading_branch():
    """auto 级别不应出现抄表报文头字段（证明两级别路径确实不同）"""
    rows = _parse(USER_FRAME_CONCURRENT, "auto")
    names = [str(r[0]).strip() for r in rows]
    assert not any("报文头" in n for n in names), (
        f"auto 级别不应展开抄表报文头：{names}"
    )


# ── 5. 异常路径容错 ───────────────────────────────────────────────────


def test_short_payload_shows_too_short():
    """payload < 8 字节 → 走「抄表报文(过短)」分支，不抛异常"""
    # 应用层头 4 字节 + payload 3 字节（长度不足 8）
    rows = _parse("11 03 00 00 01 02 03", "app")
    names = [str(r[0]).strip() for r in rows]
    assert any("过短" in n for n in names), f"应提示抄表报文过短：{names}"


def test_min_length_boundary_ok():
    """payload 恰好 8 字节 → 正常展开报文头（边界不误判为过短）"""
    rows = _parse("11 03 00 00 01 02 B3 04 87 44 19 0A", "app")
    names = [str(r[0]).strip() for r in rows]
    assert "协议版本号" in names, f"8 字节 payload 应正常解析：{names}"
    assert not any("过短" in n for n in names), "8 字节正好达到下限，不应报过短"


# ── 6. 静态守卫：同类「未定义名」不得复发 ──────────────────────────────


def test_no_undefined_names_in_parser():
    """ruff F821 守卫：本次缺陷即 F821 类型，防止同类复发"""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "F821",
            "--no-cache",
            "hdc10_parser.py",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if "No module named" in out or "unrecognized" in out:
        return  # 环境无 ruff 时跳过（不误报失败）
    assert "F821" not in out, f"hdc10_parser.py 存在未定义名：\n{out}"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
