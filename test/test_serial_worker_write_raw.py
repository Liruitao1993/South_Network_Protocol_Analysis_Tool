"""`serial_worker.SerialWorker.write_raw` 静默发送回归测试。

覆盖：
  [1] write_raw 写出正确字节并返回 True，且**不发任何日志信号**
  [2] 对照：send_frame 同样写出字节但**必须**发 [发送] 日志
  [3] 未打开/已关闭串口 → False + error_occurred
  [4] 写异常 → False + error_occurred
  [5] send_frame 与 write_raw 共用同一把写锁（并发写保护）
  [6] 反例自检：断言「无日志」的判据确实能区分两个方法

运行: QT_QPA_PLATFORM=offscreen python -u test/test_serial_worker_write_raw.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402

import serial  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from serial_worker import SerialWorker  # noqa: E402

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


class FakeSerial:
    """鸭子类型的串口：只实现 SerialWorker 用到的 is_open / write。"""

    def __init__(self, is_open=True, fail=False):
        self.is_open = is_open
        self.written = []
        self._fail = fail

    def write(self, data):
        if self._fail:
            raise serial.SerialException("模拟写失败")
        self.written.append(bytes(data))
        return len(data)


class CountingLock:
    """可计数的上下文管理器，用于验证「共用写锁」。"""

    def __init__(self):
        self.entered = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *exc):
        return False


def make_worker(fake=None):
    """构造 SerialWorker 并接上假串口 + 信号收集器。"""
    w = SerialWorker()
    if fake is not None:
        w._ser = fake
    logs, errors = [], []
    w.log_message.connect(lambda s: logs.append(s))
    w.error_occurred.connect(lambda s: errors.append(s))
    return w, logs, errors


def main():
    print("=" * 64)
    print("SerialWorker.write_raw（B1）")
    print("=" * 64)
    QApplication.instance() or QApplication([])

    section("[1] write_raw：写字节 + 不发日志")
    fake = FakeSerial()
    w, logs, errors = make_worker(fake)
    ok = w.write_raw(b"\x68\x01\x02\x16")
    check("返回 True", ok is True, str(ok))
    check("字节已写入串口", fake.written == [b"\x68\x01\x02\x16"], str(fake.written))
    check("未发 log_message 信号", logs == [], str(logs))
    check("未发 error_occurred", errors == [], str(errors))

    section("[2] 对照：send_frame 必须发日志")
    fake2 = FakeSerial()
    w2, logs2, _errs2 = make_worker(fake2)
    ok2 = w2.send_frame(b"\xAA\xBB")
    check("send_frame 返回 True", ok2 is True)
    check("send_frame 写入字节", fake2.written == [b"\xAA\xBB"], str(fake2.written))
    check("send_frame 发 log_message", len(logs2) == 1 and "AA BB" in logs2[0],
          str(logs2))

    section("[3] 未打开 / 已关闭")
    w3, _logs3, errs3 = make_worker(None)          # 未接假串口
    check("无串口 → False", w3.write_raw(b"\x01") is False)
    check("无串口 → error_occurred", len(errs3) == 1 and "未打开" in errs3[0],
          str(errs3))

    w4, _logs4, errs4 = make_worker(FakeSerial(is_open=False))
    check("is_open=False → False", w4.write_raw(b"\x01") is False)
    check("is_open=False → error_occurred", len(errs4) == 1, str(errs4))

    section("[4] 写异常")
    fake5 = FakeSerial(fail=True)
    w5, _logs5, errs5 = make_worker(fake5)
    check("写异常 → False", w5.write_raw(b"\x01") is False)
    check("写异常 → error_occurred 含「发送失败」",
          len(errs5) == 1 and "发送失败" in errs5[0], str(errs5))
    check("写异常 → 未写入", fake5.written == [], str(fake5.written))

    section("[5] 共用写锁")
    fake6 = FakeSerial()
    w6, _logs6, _errs6 = make_worker(fake6)
    lock = CountingLock()
    w6._write_lock = lock
    w6.write_raw(b"\x01")
    w6.send_frame(b"\x02")
    check("write_raw 与 send_frame 各取锁一次（共用同一把）",
          lock.entered == 2, f"进入 {lock.entered} 次")

    section("[6] 反例自检：无日志判据有效")
    check(
        "send_frame 有日志而 write_raw 无日志（判据能区分两者）",
        len(logs2) == 1 and logs == [],
        f"send_frame={len(logs2)} write_raw={len(logs)}",
    )

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
