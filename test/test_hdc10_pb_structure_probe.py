# -*- coding: utf-8 -*-
"""协议11（HDC 1.0）「无物理块头」帧误判修复 —— PB 形态探测回归

现场报障（2026-09-17）:
    「这一帧用协议10 能解析，用协议11 无法解析」——160 字节帧在协议11 的
    「解析级别 = 应用层报文(app)」下能看到业务内容，切回「自动识别(auto)」只有 17 行、
    MAC/MSDU 树全乱、看不到任何业务字段（与协议10 打开同一帧的结果不一致）。

根因:
    `hdc10_parser._parse_pb_block` 处理 SOF 帧时**无条件**假设物理块以物理块头(PBH)
    开头、直接剥离 1 字节。但该现场帧的 PB 体**没有 PBH**，第 1 字节即 MAC 帧头起始：
      * 其 bit7(帧结束标志) 与 bit6(帧起始标志) 同时为 0 —— 合法 PBH 的 bit7 恒为 1
      * 紧随字节不构成合法 MAC 头（版本 0 时 byte1 与 byte6 必须为 0x00）
    整体错位 1 字节后，MSDU 长度被读成 1792（0x700）等荒谬值。

决定性证据（现场帧）:
    按「无 PBH」（MAC 头自 data[16] 起）解析时
        帧内 ICV@102 == crc32(MSDU[44:102])   完全相等
    4 字节值偶然相等的概率为 1/2^32，排除巧合；按「有 PBH」解析则 MSDU 长度 = 1792。
    可复现证据脚本与改动前基线见归档任务目录
    `.trellis/tasks/archive/2026-09/09-17-hdc10-pb-structure-probe/`（`probe_evidence.py`、
    `baseline_pb_only.txt`）。

修复:
    新增 `HDC10Parser._probe_pb_form(data) -> (skip, mac_frame_len)` 逐字节打分探测 PB 形态：
      * 存在合规 MAC 头（版本 0 且 byte1/byte6 为 0x00）→ 无 PBH（skip=0）
      * 合法 PBH（bit7=1）且其后存在合规 MAC 头 → 有 PBH（skip=1）
      * 无任何合规信号 → 回落旧行为（有 PBH），与改动前一致
    `_parse_pb_block`（SOF 且未直接给出块大小时）与 `_parse_pb_and_mac_header` 均改走该探测。

同时修复的既有缺陷:
    `_parse_pb_and_mac_header` 把原帧**绝对**偏移 base_offset 当作 `_parse_mac_header(data, offset)`
    的 **data 内相对索引**（旧代码传 `base_offset + 1`）⇒ 解析级别 fc_mac 下 MAC 头整体错位：
    原始源TEI 读成 2、MSDU类型 读成 0、MSDU长度 读成 1280。现统一传 0（配合已切片的数据）。

协议依据（下列表号均为 HDC 1.0 版本文档，存于 `国网新一代协议/HDC-国网双模协议/`）:
    《双模通信互联互通技术规范 第4-2部分：数据链路层通信协议》
      表37「物理块头的格式」序列号(bit0~5, 6bit)、帧起始标志(bit6)、帧结束标志(bit7)
        —— 合法 PBH 的 bit7 恒为 1；该表**无「块大小码」字段**
      表10「MAC 帧头（标准帧协议）」版本(bit0~3)与保留(bit4~7，必为 0)、字节6 保留(必为 0)、
        字节7 MSDU 类型、字节8~9 的低 11bit MSDU 长度
      ICV = CRC-32(MSDU 载荷)，不含 MAC 帧头
    《双模通信互联互通技术规范 第4-3部分：应用层通信协议》
      表3「抄表下行报文格式说明」字节6 设备超时时间(§5.3.1.8, ×100ms)、字节7 选项字(§5.3.1.9)
      表8「选项字含义」（终端主动 / 路由主动抄表: bit0 方向位；终端主动并发抄表: bit7~0 报文间间隔）
      表9「方向位含义」、表10「抄表上行报文格式说明」字节6~7 选项字 16bit = 报文应答状态
"""

import hashlib
import json
import pickle
import sys
from pathlib import Path

import _path_setup  # noqa: E402,F401

from hdc10_parser import HDC10Parser, _PB_PROBE_MIN_SCORE

ROOT = Path(__file__).resolve().parent.parent
PICKLE = ROOT / "test" / "hdc10_real_frames.pkl"

# 现场帧（160 字节）：FC 16B + PB（无 PBH，MAC 头自 data[16] 起） + 41B 尾部填充
# 业务：端口 0x11 + 报文ID 0x0003「终端主动并发抄表」（转发数据规约 = DL/T698.45）
FIELD_FRAME = (
    "01 55 E2 D4 33 F0 FF 03 D3 13 B6 42 00 BE AF B8 "
    "10 00 FF 3F 02 68 62 30 3A 00 CF 08 00 07 00 00 20 00 00 27 16 39 99 00 00 35 47 "
    "99 11 03 00 00 01 72 E3 02 D8 FF 14 06 68 2C 00 43 05 99 47 35 00 00 99 00 89 F8 "
    "10 00 08 05 01 00 20 10 02 00 00 01 10 37 19 A6 2F C5 FF 9E D0 A1 8E 62 EA 7E "
    "08 98 AA 0C BD 16 7A 1A 2B 55 " + "00 " * 41
)

PASS = 0
FAIL = 0
FAILED = []


def section(title):
    print(f"\n{title}")


def check(desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {desc}")
    else:
        FAIL += 1
        FAILED.append(desc)
        print(f"  ✗ {desc}" + (f"\n      {detail}" if detail else ""))


def _to_bytes(hex_str):
    return bytes.fromhex(hex_str.replace(" ", ""))


def _parse(data, level="auto", **kwargs):
    if isinstance(data, str):
        data = _to_bytes(data)
    return HDC10Parser().parse_to_table(data, parse_level=level, **kwargs)


def _find(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    return None


def _val(rows, name, idx=2):
    row = _find(rows, name)
    return None if row is None else str(row[idx]).strip()


def _describe(rows, name):
    row = _find(rows, name)
    return "" if row is None else str(row[3])


def _fingerprint(rows):
    raw = json.dumps([list(r) for r in rows], ensure_ascii=False,
                     sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _forced_pbh_parser():
    """构造「探测恒判定有 PBH」的解析器 —— 变异反证：证明探测是修复的必要条件

    仅覆盖实例方法，不改动类；行为等价于修复前的无条件剥离 PBH。
    """
    parser = HDC10Parser()
    parser._probe_pb_form = lambda data: (1, 1)  # type: ignore[method-assign]
    return parser


def load_frames():
    with open(PICKLE, "rb") as fp:
        return pickle.load(fp)


def main():
    field_bytes = _to_bytes(FIELD_FRAME)
    parser = HDC10Parser()

    # ── [1] 现场帧 auto：探测生效、MAC/MSDU 不再错位 ──────────────
    section("[1] A1 现场帧 auto 级别：PB 形态探测生效")
    rows = _parse(FIELD_FRAME, "auto")
    check("A1 帧长 147 字节（FC 16 + MAC帧 90 + 尾部填充 41）",
          len(field_bytes) == 147, str(len(field_bytes)))
    check("A1 auto 行数 = 57（修复前 17 行、无业务内容）", len(rows) == 57, f"实际={len(rows)}")
    probe_row = _find(rows, "物理块(PB) - 未检测到合法物理块头")
    check("A1 输出「未检测到合法物理块头」行",
          probe_row is not None,
          f"表内字段={[str(r[0]).strip() for r in rows]}")
    check("A1 该行说明含「直接起始于 MAC 帧头」（交代依据）",
          probe_row is not None and "直接起始于 MAC 帧头" in str(probe_row[3]),
          "" if probe_row is None else str(probe_row[3]))
    check("A1 原始源TEI = 1（错位时为 2）", _val(rows, "原始源TEI") == "1", str(_val(rows, "原始源TEI")))
    check("A1 原始目的TEI = 4095", _val(rows, "原始目的TEI") == "4095", str(_val(rows, "原始目的TEI")))
    check("A1 MSDU类型 = 48（应用层报文；错位时为 0）",
          _val(rows, "MSDU类型") == "48", str(_val(rows, "MSDU类型")))
    check("A1 MSDU长度 = 58字节（错位时为 1280/1792 字节）",
          _val(rows, "MSDU长度") == "58字节", str(_val(rows, "MSDU长度")))
    check("A1 ICV 校验正确（ICV = CRC-32(MSDU)，不含 MAC 头）",
          "校验正确" in _describe(rows, "完整性校验值(ICV)"),
          _describe(rows, "完整性校验值(ICV)"))

    # ── [2] 现场帧业务内容 ─────────────────────────────────────
    section("[2] A2 现场帧业务内容可读（协议10 早已能读，本项要求两端一致）")
    check("A2 报文端口号 = 17 (0x11 普通业务)", _val(rows, "报文端口号") == "17", str(_val(rows, "报文端口号")))
    check("A2 报文ID = 0x0003 (终端主动并发抄表)", _val(rows, "报文ID") == "0x0003", str(_val(rows, "报文ID")))
    check("A2 业务报文头 8 字节", _val(rows, "终端主动并发抄表报文头") == "8字节",
          str(_val(rows, "终端主动并发抄表报文头")))
    check("A2 协议版本号 = 1", _val(rows, "协议版本号") == "1", str(_val(rows, "协议版本号")))
    check("A2 报文头长度 = 2×4B=8B", _val(rows, "报文头长度") == "2×4B=8B", str(_val(rows, "报文头长度")))
    check("A2 转发数据规约类型 = 3 (DL/T698.45)",
          _val(rows, "转发数据规约类型") == "3", str(_val(rows, "转发数据规约类型")))
    check("A2 转发数据长度 = 46字节", _val(rows, "转发数据长度") == "46字节", str(_val(rows, "转发数据长度")))
    check("A2 数据(DATA) = 46字节（与转发数据长度自洽）",
          _val(rows, "数据(DATA)") == "46字节", str(_val(rows, "数据(DATA)")))

    # ── [3] 同批补齐的抄表头字段（表3 / 表8 / 表9 / §5.3.1.8）────
    section("[3] A2b 抄表头补齐字段：设备超时时间 / 选项字")
    check("A2b 设备超时时间 = 2000ms（0x14 × 100ms，§5.3.1.8）",
          _val(rows, "设备超时时间") == "2000ms", str(_val(rows, "设备超时时间")))
    check("A2b 设备超时时间说明引用 §5.3.1.8",
          "§5.3.1.8" in _describe(rows, "设备超时时间"), _describe(rows, "设备超时时间"))
    check("A2b 选项字 = 0x06", _val(rows, "选项字") == "0x06", str(_val(rows, "选项字")))
    check("A2b 并发抄表下选项字按「报文间间隔」解释（6 × 10ms，表8）",
          "报文间间隔" in _describe(rows, "选项字"), _describe(rows, "选项字"))

    # ── [4] fc_mac 级别：既有偏移错位修复 ───────────────────────
    section("[4] A3/A5 fc_mac 级别 MAC 头偏移（既有缺陷）回归")
    mac_rows = _parse(FIELD_FRAME, "fc_mac")
    check("A5 fc_mac 原始源TEI = 1（旧代码传 base_offset+1 时读成 2）",
          _val(mac_rows, "原始源TEI") == "1", str(_val(mac_rows, "原始源TEI")))
    check("A5 fc_mac MSDU类型 = 48（旧代码读成 0）",
          _val(mac_rows, "MSDU类型") == "48", str(_val(mac_rows, "MSDU类型")))
    check("A5 fc_mac MSDU长度 = 58字节（旧代码读成 1280）",
          _val(mac_rows, "MSDU长度") == "58字节", str(_val(mac_rows, "MSDU长度")))
    check("A3 fc_mac 与 auto 的 MAC 头关键字段一致",
          all(_val(mac_rows, n) == _val(rows, n)
              for n in ("原始源TEI", "原始目的TEI", "MSDU类型", "MSDU长度", "MSDU序列号")),
          f"fc_mac={[_val(mac_rows, n) for n in ('原始源TEI', '原始目的TEI', 'MSDU类型', 'MSDU长度')]} "
          f"auto={[_val(rows, n) for n in ('原始源TEI', '原始目的TEI', 'MSDU类型', 'MSDU长度')]}")

    # ── [5] 探测纯函数判据（表21 / 表11）───────────────────────
    section("[5] A6 _probe_pb_form 判据（表21 物理块头 / 表11 MAC 帧头）")
    pb = field_bytes[16:]
    probe = parser._probe_pb_form(pb)
    check("A6 现场帧 PB（MAC 头起始）→ skip=0 且得分达阈值",
          probe[0] == 0 and probe[1] >= _PB_PROBE_MIN_SCORE,
          f"实际={probe} 阈值={_PB_PROBE_MIN_SCORE}")
    # PBH 首字节低 4 位 = 0（表37 序列号的低 4 位，不是“块大小码”）→ 不被首字节 ver 检查直接挡掉，
    # 进而用错位后的字节判定得分不足 → 回落「有 PBH」，即真帧不会被误判为无 PBH
    with_pbh = bytes([0xC0]) + pb
    check("A6 合法 PBH 前置 → skip=1（不误判为无 PBH）",
          parser._probe_pb_form(with_pbh)[0] == 1, str(parser._probe_pb_form(with_pbh)))
    check("A6 PBH 低 4 位非 0/1（非 MAC 头版本值）→ 直接按有 PBH 处理",
          parser._probe_pb_form(b"\xc4" + pb) == (1, 0),
          str(parser._probe_pb_form(b"\xc4" + pb)))
    check("A6 全零段无任何合规信号 → 回落旧行为（有 PBH）",
          parser._probe_pb_form(bytes(40))[0] == 1, str(parser._probe_pb_form(bytes(40))))
    check("A6 首字节 bit7=1 且后续非 MAC 头 → 仍按有 PBH 处理",
          parser._probe_pb_form(b"\xaa\xbb" * 20)[0] == 1,
          str(parser._probe_pb_form(b"\xaa\xbb" * 20)))

    # ── [6] 变异反证：去掉探测必然回到错位 ─────────────────────
    section("[6] A6b 变异反证（强制「有 PBH」= 修复前行为）")
    forced_rows = _forced_pbh_parser().parse_to_table(field_bytes, parse_level="auto")
    check("A6b 变异后 MSDU类型 ≠ 48（证明探测是修复的必要条件）",
          _val(forced_rows, "MSDU类型") != "48", str(_val(forced_rows, "MSDU类型")))
    check("A6b 变异后行数远少于修复后（无业务内容）",
          len(forced_rows) < len(rows), f"变异={len(forced_rows)} 修复后={len(rows)}")
    check("A6b 变异后指纹与修复后不同",
          _fingerprint(forced_rows) != _fingerprint(rows))

    # ── [7] 真实夹具：探测对裸 PB 输入零影响 + 全级别不崩 ──────
    section("[7] A4/A8 真实夹具（test/hdc10_real_frames.pkl，60 帧）")
    frames = load_frames()
    check("A7 夹具帧数 = 60", len(frames) == 60, str(len(frames)))

    self_diff = []
    for i, item in enumerate(frames):
        fb = item[1]
        if HDC10Parser()._parse_pb_only(fb, 1) != _forced_pbh_parser()._parse_pb_only(fb, 1):
            self_diff.append(i)
    check("A4 pb_only 60 帧：正常解析 == 强制「有 PBH」解析（探测对裸 PB 输入零影响）",
          not self_diff, f"差异帧={self_diff}")

    errors = []
    for level in ("auto", "fc_pb", "fc_only", "mac_only", "pb_only", "fc_mac", "app"):
        for i, item in enumerate(frames):
            try:
                HDC10Parser().parse_to_table(item[1], parse_level=level)
            except Exception as exc:  # noqa: BLE001
                errors.append((level, i, f"{type(exc).__name__}: {exc}"))
    check("A8 60 帧 × 7 解析级别 无异常抛出",
          not errors, f"异常 {len(errors)} 条，前 5: {errors[:5]}")

    # ── [8] 边界输入 ──────────────────────────────────────────
    section("[8] A8 边界输入不抛异常")
    boundary_errors = []
    for n in (0, 1, 8, 15, 16, 17):
        for level in ("auto", "fc_mac", "app", "pb_only"):
            try:
                HDC10Parser().parse_to_table(bytes(n), parse_level=level)
            except Exception as exc:  # noqa: BLE001
                boundary_errors.append((n, level, f"{type(exc).__name__}: {exc}"))
    check("A8 长度 0/1/8/15/16/17 × 4 级别 无异常",
          not boundary_errors, f"异常={boundary_errors[:5]}")

    hdr_errors = []
    for n in (0, 1, 7, 8, 9):
        try:
            parser._parse_pb_and_mac_header(bytes(n), 0, 1)
        except Exception as exc:  # noqa: BLE001
            hdr_errors.append((n, f"{type(exc).__name__}: {exc}"))
    check("A8 _parse_pb_and_mac_header 长度 0/1/7/8/9 段 无异常",
          not hdr_errors, f"异常={hdr_errors}")

    probe_errors = []
    for n in (0, 1, 9, 28):
        try:
            parser._probe_pb_form(bytes(n))
        except Exception as exc:  # noqa: BLE001
            probe_errors.append((n, f"{type(exc).__name__}: {exc}"))
    check("A8 _probe_pb_form 长度 0/1/9/28 段 无异常",
          not probe_errors, f"异常={probe_errors}")

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    if FAILED:
        print("失败项:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
