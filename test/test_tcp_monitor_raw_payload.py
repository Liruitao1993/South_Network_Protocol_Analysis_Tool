"""`FlowBuffer` 切帧策略回归测试（原始载荷成帧，R1）。

覆盖：
  [1] auto：非 ED 方向按 TCP segment 逐包成帧（AC1.1）
  [2] auto：ED 封装方向行为与改动前一致（AC1.2）
  [3] 同一批字节不重复上报（AC1.3）
  [4] 空载荷不产帧（AC1.4）
  [5] 反例：原始载荷含 0xED 不得被误判为 ED 帧
  [6] 跨包 ED 帧仍能切出（waiting 语义）
  [7] raw 方向遇到完整 ED 帧可升级回 ED（抓包中途开始的场景）
  [8] mode="ed" 保持旧行为（回滚开关有效）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_tcp_monitor_raw_payload.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402

from monitor.tcp_monitor import FlowBuffer  # noqa: E402

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
    print(f"\n{title}")


def ed_frame(payload: bytes, ts: float = 0.0) -> bytes:
    """构造一个合法 ED..EE 监控封装帧：ED + 帧长(2,小端) + ctrl1 + ctrl2 + EF + 数据 + CS + EE"""
    frame_len = len(payload) + 4
    return (
        bytes([0xED, frame_len & 0xFF, (frame_len >> 8) & 0xFF, 0x01, 0x02, 0xEF])
        + payload
        + bytes([0x00, 0xEE])
    )


def raw_69845() -> bytes:
    """698.45 风格 APDU 字节（含 0x68 起头，非 ED 封装）"""
    return bytes.fromhex("681E00430501000000006811043333333334333333333333333333")


def main():
    print("=" * 64)
    print("FlowBuffer 切帧策略（B2 / R1）")
    print("=" * 64)

    section("[1] auto：原始载荷按 segment 逐包成帧")
    buf = FlowBuffer()
    segs = [raw_69845(), bytes(range(200)), b"\x00" * 17]
    for i, seg in enumerate(segs):
        buf.append(seg, float(i))
    frames = buf.pop_frames()
    check("3 个 segment → 3 帧", len(frames) == 3, f"实际 {len(frames)}")
    check(
        "逐帧长度等于对应 segment 长度",
        [len(f[1]) for f in frames] == [len(s) for s in segs],
        str([len(f[1]) for f in frames]),
    )
    check(
        "逐帧字节内容与 segment 一致",
        all(f[1] == s for f, s in zip(frames, segs)),
    )
    check(
        "逐帧时间戳与 append 一致",
        [f[0] for f in frames] == [0.0, 1.0, 2.0],
        str([f[0] for f in frames]),
    )
    check("判定为 raw", buf.decided == "raw", str(buf.decided))
    check("无残留字节", buf.pending_bytes == 0, str(buf.pending_bytes))

    section("[2] auto：ED 封装方向行为与改动前一致")
    buf = FlowBuffer()
    f1, f2 = ed_frame(b"AAAA"), ed_frame(b"BBBBBB")
    buf.append(f1, 1.0)
    buf.append(f2, 2.0)
    frames = buf.pop_frames()
    check("2 个 ED 帧 → 2 帧", len(frames) == 2, str(len(frames)))
    check("帧字节与构造一致", [f[1] for f in frames] == [f1, f2])
    check("判定为 ed", buf.decided == "ed", str(buf.decided))

    # ED 帧前面带非 ED 噪声：仍按现状丢弃噪声、切出 ED 帧
    buf = FlowBuffer()
    buf.append(b"\x11\x22\x33" + f1, 3.0)
    frames = buf.pop_frames()
    check("ED 帧前的非 ED 噪声被丢弃（与旧行为一致）",
          len(frames) == 1 and frames[0][1] == f1, str([len(f[1]) for f in frames]))

    section("[3] 同一批字节不重复上报")
    buf = FlowBuffer()
    ed = ed_frame(b"CCCC")
    buf.append(raw_69845(), 1.0)     # 先原始
    buf.append(ed, 2.0)              # 后 ED
    frames = buf.pop_frames()
    total = sum(len(f[1]) for f in frames)
    check(
        "上报总字节数 == 输入总字节数（无重复无丢失）",
        total == len(raw_69845()) + len(ed),
        f"上报 {total} / 输入 {len(raw_69845()) + len(ed)}",
    )

    section("[4] 空载荷不产帧")
    buf = FlowBuffer()
    buf.append(b"", 1.0)
    buf.append(b"", 2.0)
    check("空载荷 → 0 帧", buf.pop_frames() == [])
    check("空载荷不产生残留", buf.pending_bytes == 0)

    section("[5] 反例：原始载荷含 0xED 不得被误判")
    # (a) 中间含 0xED 且后两字节看似合法帧长：先等（可能是跨包 ED 帧），
    #     超过等待上限（MAX_WAIT_SEGMENTS）后必须回退 raw 并按 segment 补发
    payload = bytes([0x00, 0xED, 0x7F, 0x00, 0x00, 0x00, 0x00, 0xEE]) + b"payload"
    seg2, seg3 = b"second-segment", b"third-segment"
    buf = FlowBuffer()
    buf.append(payload, 1.0)
    check("(a) 看似合法 ED 候选：先等待不产出、不误判",
          buf.pop_frames() == [] and buf.decided is None, str(buf.decided))
    buf.append(seg2, 2.0)
    buf.append(seg3, 3.0)
    frames = buf.pop_frames()
    check("(a) 超过等待上限 → 回退 raw 并按 segment 补发",
          len(frames) == 3
          and [len(f[1]) for f in frames] == [len(payload), len(seg2), len(seg3)],
          str([len(f[1]) for f in frames]))
    check("(a) 字节无丢失无重复",
          b"".join(f[1] for f in frames) == payload + seg2 + seg3)
    check("(a) 判定为 raw", buf.decided == "raw", str(buf.decided))
    check("(a) 无残留", buf.pending_bytes == 0, str(buf.pending_bytes))

    # (b) 段尾恰好是 0xED（长度域/EF 都还没到）
    buf = FlowBuffer()
    buf.append(b"hello\xED", 1.0)
    frames = buf.pop_frames()
    check("(b) 段尾 0xED：先缓冲不产帧（等可能的跨包 ED 帧）",
          frames == [] and buf.pending_bytes == 6,
          f"帧数={len(frames)} 残留={buf.pending_bytes}")
    buf.append(b"world", 2.0)   # 后续字节构不成 ED 帧 → 应回退 raw 并补发
    frames = buf.pop_frames()
    check("(b) 后续构不成 ED 帧 → 回退 raw，两段各一帧",
          len(frames) == 2 and [f[1] for f in frames] == [b"hello\xED", b"world"],
          str([f[1] for f in frames]))

    section("[6] 跨包 ED 帧仍能切出")
    buf = FlowBuffer()
    whole = ed_frame(b"X" * 40)
    buf.append(whole[:10], 1.0)      # 半帧
    check("半帧时无输出且不误判 raw",
          buf.pop_frames() == [] and buf.decided is None, str(buf.decided))
    buf.append(whole[10:], 2.0)      # 补齐
    frames = buf.pop_frames()
    check("补齐后切出完整 ED 帧",
          len(frames) == 1 and frames[0][1] == whole, str([len(f[1]) for f in frames]))
    check("判定为 ed", buf.decided == "ed", str(buf.decided))

    section("[7] raw 方向遇完整 ED 帧可升级回 ED")
    buf = FlowBuffer()
    tail = ed_frame(b"TAILTAIL")[6:]      # 模拟某 ED 帧的尾巴（无 ED 头）
    buf.append(tail, 1.0)
    check("尾巴段被当原始载荷产出", len(buf.pop_frames()) == 1)
    check("判定为 raw", buf.decided == "raw", str(buf.decided))
    full = ed_frame(b"NEXTFRAME")
    buf.append(full, 2.0)
    frames = buf.pop_frames()
    check("后续完整 ED 帧被切出并升级为 ed",
          len(frames) == 1 and frames[0][1] == full and buf.decided == "ed",
          f"帧数={len(frames)} decided={buf.decided}")

    # 升级时 ED 帧前面还有字节 → 前段按原始载荷产出，字节不重复
    buf = FlowBuffer()
    buf.append(b"noise", 1.0)
    buf.pop_frames()
    buf.append(b"pre" + full, 2.0)
    frames = buf.pop_frames()
    check("升级时前缀字节按原始载荷产出",
          len(frames) == 2 and frames[0][1] == b"pre" and frames[1][1] == full,
          str([f[1][:6] for f in frames]))

    section("[8] mode 开关")
    buf = FlowBuffer(mode="ed")
    buf.append(raw_69845(), 1.0)
    check('mode="ed"：原始载荷仍为 0 帧（旧行为可回滚）', buf.pop_frames() == [])
    buf2 = FlowBuffer(mode="raw")
    buf2.append(ed_frame(b"AA"), 1.0)
    frames = buf2.pop_frames()
    check('mode="raw"：ED 帧也被当原始载荷整段产出',
          len(frames) == 1 and frames[0][1] == ed_frame(b"AA"),
          str(len(frames)))
    try:
        FlowBuffer(mode="bogus")
        check("非法 mode 抛 ValueError", False, "未抛异常")
    except ValueError:
        check("非法 mode 抛 ValueError", True)

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）✓")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
