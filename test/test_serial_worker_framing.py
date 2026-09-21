# -*- coding: utf-8 -*-
"""SerialWorker 切帧：DL/T645（协议6）与 FT1.2 双格式

用户（2026-09-21）:
    刚才使用GUI版本，协议6，打开了串口进行报文发送测试，只有发送没有接收。

根因：``SerialWorker._process_buffer`` 只按 **FT1.2** 切帧
（``68H + 长度(2B 小端) + … + 16H``），而 DL/T645-2007 是
``68H + 地址(6B) + 68H + C + L + 数据(L) + CS + 16H`` —— 它把**地址低字节当长度域**，
``68 01 00 …`` 算出长度 1（<8）→ 整帧丢弃 ⇒ ``frame_received`` 永不触发，
而协议组帧页只连了 ``frame_received``（未连 ``raw_data_received``），
于是串口日志里**只有 ``[发送]`` 没有 ``[接收]``**。

覆盖:
  [1] DL/T645 单帧（用户截图那帧）→ 切出 1 帧且 ``[接收]`` 日志正确
  [2] DL/T645 带 4 字节 FE 唤醒前导 → 前导被丢弃、帧体完整
  [3] DL/T645 粘包（2 帧一次到达）→ 切出 2 帧
  [4] DL/T645 半帧分两次到达 → 第二次才切出（不早切、不误切）
  [5] 从站应答帧（C=0x91）同样可切
  [6] FT1.2 回归：常规帧与「长度域对不上、靠 16H 兜底」的容错路径均不变
  [7] 垃圾数据不产出、不抛异常；缓冲区超限被清理

运行: python -X utf8 -u test/test_serial_worker_framing.py
"""

import os
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from serial_worker import SerialWorker  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

PASS = 0
FAIL = 0
FAILED = []

# 用户截图里的主站读数据请求：68 + 表地址000000000001 + 68 + 11(读数据) + 04 + DI + CS + 16
DLT645_REQ = bytes.fromhex("6801000000000068110433333433B316")
# 从站正常应答（C=0x91），数据域 4 字节
DLT645_RSP = bytes.fromhex("68010000000000689104333334338C16")
# FT1.2（IEC 62056-21）：68 + 长度(2B 小端,含整帧) + … + 16
FT12_FRAME = bytes.fromhex("680C00C10000000000000016")


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


def new_worker():
    """建一个未启动的 worker 并接住信号"""
    w = SerialWorker()
    got = {"frames": [], "logs": []}
    w.frame_received.connect(got["frames"].append)
    w.log_message.connect(got["logs"].append)
    return w, got


def feed(w, data: bytes):
    """模拟串口读到一个 chunk：进缓冲区并切帧"""
    w._buffer.extend(data)
    w._process_buffer()


def main():
    # ── [1] DL/T645 单帧 ────────────────────────────────────────
    section("[1] DL/T645-2007 单帧（用户截图那帧）")
    w, got = new_worker()
    feed(w, DLT645_REQ)
    check("切出 1 帧", len(got["frames"]) == 1, str(got["frames"]))
    check("帧内容完整（16 字节，未截断）",
          got["frames"] and got["frames"][0] == DLT645_REQ,
          f"{got['frames'][0].hex().upper() if got['frames'] else '-'}")
    logs = [x for x in got["logs"] if "[接收]" in x]
    check("产生 [接收] 日志（此前完全没有）", len(logs) == 1, str(got["logs"]))
    check("日志内容为该帧十六进制",
          logs and "68 01 00 00 00 00 00 68 11 04 33 33 34 33 B3 16" in logs[0],
          str(logs))
    check("缓冲区已清空", len(w._buffer) == 0, str(len(w._buffer)))

    # ── [2] FE 唤醒前导 ─────────────────────────────────────────
    section("[2] DL/T645 带 4 字节 FEH 唤醒前导")
    w, got = new_worker()
    feed(w, bytes([0xFE] * 4) + DLT645_REQ)
    check("切出 1 帧", len(got["frames"]) == 1, str(len(got["frames"])))
    check("帧体不含前导 FE（从 68H 起）",
          got["frames"] and got["frames"][0] == DLT645_REQ,
          f"{got['frames'][0].hex().upper() if got['frames'] else '-'}")

    # ── [3] 粘包 ────────────────────────────────────────────────
    section("[3] DL/T645 粘包（一次到达 2 帧）")
    w, got = new_worker()
    feed(w, DLT645_REQ + DLT645_RSP)
    check("切出 2 帧", len(got["frames"]) == 2, str(len(got["frames"])))
    check("两帧内容各自正确",
          len(got["frames"]) == 2 and got["frames"][0] == DLT645_REQ
          and got["frames"][1] == DLT645_RSP)

    # ── [4] 半帧分两次到达 ──────────────────────────────────────
    section("[4] DL/T645 半帧分两次到达（不得早切/误切）")
    w, got = new_worker()
    feed(w, DLT645_REQ[:8])
    check("第一次（仅 8 字节）不产出帧", len(got["frames"]) == 0,
          str(len(got["frames"])))
    check("第一次不产生 [接收] 日志",
          not any("[接收]" in x for x in got["logs"]), str(got["logs"]))
    feed(w, DLT645_REQ[8:])
    check("第二次补齐后切出 1 帧",
          len(got["frames"]) == 1 and got["frames"][0] == DLT645_REQ,
          str(len(got["frames"])))
    check("缓冲区清空", len(w._buffer) == 0, str(len(w._buffer)))

    # ── [5] 从站应答帧 ──────────────────────────────────────────
    section("[5] 从站应答帧（C=0x91）")
    w, got = new_worker()
    feed(w, DLT645_RSP)
    check("切出 1 帧且内容正确",
          len(got["frames"]) == 1 and got["frames"][0] == DLT645_RSP,
          f"{got['frames'][0].hex().upper() if got['frames'] else '-'}")

    # ── [6] FT1.2 回归 ─────────────────────────────────────────
    section("[6] FT1.2 回归（不得被 DL/T645 分支抢走）")
    w, got = new_worker()
    feed(w, FT12_FRAME)
    check("FT1.2 常规帧仍切出 1 帧",
          len(got["frames"]) == 1 and got["frames"][0] == FT12_FRAME,
          f"{got['frames'][0].hex().upper() if got['frames'] else '-'}")
    check("日志前缀为 [接收]",
          any(x.endswith("68 0C 00 C1 00 00 00 00 00 00 00 16")
              for x in got["logs"] if "[接收]" in x), str(got["logs"]))
    # 容错：长度域与 16H 对不上，靠「找下一个 16H」兜底
    w, got = new_worker()
    bad = bytes.fromhex("680900C10000001600")   # 长度域=9，但 index8 不是 16H
    feed(w, bad)
    check("FT1.2 容错路径仍生效（[接收(容错)]）",
          len(got["frames"]) == 1
          and any("[接收(容错)]" in x for x in got["logs"]),
          str(got["logs"]))
    # DL/T645 与 FT1.2 混流
    w, got = new_worker()
    feed(w, DLT645_REQ + FT12_FRAME)
    check("DL/T645 与 FT1.2 混流各切 1 帧",
          len(got["frames"]) == 2 and got["frames"][0] == DLT645_REQ
          and got["frames"][1] == FT12_FRAME,
          str([f.hex().upper() for f in got["frames"]]))

    # ── [7] 健壮性 ──────────────────────────────────────────────
    section("[7] 健壮性：垃圾数据 / 超长缓冲")
    w, got = new_worker()
    feed(w, bytes.fromhex("AABBCCDDEE"))
    check("无 68H 的垃圾数据不产出帧", len(got["frames"]) == 0)
    w, got = new_worker()
    feed(w, bytes.fromhex("68010000"))          # 截断的 DL/T645 头
    check("截断头不产出帧、不抛异常", len(got["frames"]) == 0)
    w, got = new_worker()
    feed(w, bytes.fromhex("68FF"))              # 只有 2 字节
    check("超短数据不抛异常", len(got["frames"]) == 0)
    w, got = new_worker()
    feed(w, bytes([0xAA] * 5000))
    check("缓冲超 4096 被清理到 1024 以内", len(w._buffer) <= 1024,
          str(len(w._buffer)))
    w, got = new_worker()
    feed(w, DLT645_REQ)
    feed(w, DLT645_REQ)
    check("连续两次单帧各产出一次", len(got["frames"]) == 2,
          str(len(got["frames"])))

    # ── [8] 接收回包解析：协议组帧页的 dlt645 分支 ───────────────
    section("[8] 协议组帧页接收回包解析（dlt645 分支）")
    import frame_gen_widget as _fgw
    rows = _fgw.FrameGenWidget._dlt645_to_table(DLT645_REQ)
    check("_dlt645_to_table 产出 8 行", len(rows) == 8, str(len(rows)))
    check("每行为 6 元组（表格/摘要同构）",
          all(len(r) == 6 for r in rows), str(rows[:1]))
    names = [str(r[0]).strip() for r in rows]
    check("含 控制码 / 数据标识 DI / 从站地址（与接收摘要 key_fields 对齐）",
          all(k in names for k in ("控制码", "数据标识 DI", "从站地址")), str(names))
    check("控制码解析为「主站请求 | 读数据」",
          any(n == "控制码" and "读数据" in str(r[3])
              for n, r in zip(names, rows)),
          str([r for r in rows if str(r[0]).strip() == "控制码"]))
    # 原先协议6 落进 else 分支被 gdw_parser 解析 → 收到回包也只显示解析失败
    check("协议组帧页接收分支已含 dlt645（源码守卫）",
          'self.protocol_mode == "dlt645"' in
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "frame_gen_widget.py"), encoding="utf-8").read())

    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    for n in FAILED:
        print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    # Qt offscreen 收尾可能崩（0xC0000409），打印后直接交出退出码
    _code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)
