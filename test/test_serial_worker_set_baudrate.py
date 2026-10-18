"""`serial_worker.SerialWorker.set_baudrate` 运行中热切换波特率的回归测试。

覆盖：
  [1] 端口未打开/串口对象未开：只记配置 + 发 `baudrate_changed`，不写 [串口] 日志
  [2] 端口已开：**先 flush 排空发送缓冲、再改速率**（顺序不可换，否则残帧）、
      共用写锁、发日志 + `baudrate_changed`、**不关也不重开端口**
  [3] 参数非法（非数/0/负/None/空）：False + `error_occurred`，配置与串口都不动
  [4] flush 失败 / 改速率失败：False + `error_occurred`，**不改** `_baudrate`（不许说谎）、
      不发 `baudrate_changed`
  [5] 反例自检：判据能区分（成功切换确实改了速率；`logs`/`baudrate_changed` 不是恒空/恒满）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_serial_worker_set_baudrate.py
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
    """鸭子类型的串口：只实现 `set_baudrate` 用到的 ``is_open`` / ``flush`` / ``baudrate``。

    - ``events`` 是**顺序账本**：``("flush",)`` / ``("baudrate", n)`` / ``("close",)``，
      用来断言「先排空再改速率」与「绝不关/重开端口」；
    - ``flush_fail`` / ``baud_fail`` 模拟底层失败（真实现会抛 `serial.SerialException`）。
    """

    def __init__(self, is_open=True, flush_fail=False, baud_fail=False, baudrate=9600):
        self.is_open = is_open
        self._baudrate = int(baudrate)
        self._flush_fail = bool(flush_fail)
        self._baud_fail = bool(baud_fail)
        self.events = []

    def flush(self):
        self.events.append(("flush",))
        if self._flush_fail:
            raise serial.SerialException("模拟 flush 失败")

    def close(self):
        self.events.append(("close",))
        self.is_open = False

    @property
    def baudrate(self):
        return self._baudrate

    @baudrate.setter
    def baudrate(self, value):
        self.events.append(("baudrate", int(value)))
        if self._baud_fail:
            raise serial.SerialException("模拟改 DCB 失败")
        self._baudrate = int(value)


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
    """构造 SerialWorker（可选接假串口）+ 信号收集器 → (worker, logs, errors, bauds)。"""
    w = SerialWorker()
    if fake is not None:
        w._ser = fake
    logs, errors, bauds = [], [], []
    w.log_message.connect(lambda s: logs.append(s))
    w.error_occurred.connect(lambda s: errors.append(s))
    w.baudrate_changed.connect(lambda n: bauds.append(int(n)))
    return w, logs, errors, bauds


def main():
    print("=" * 64)
    print("SerialWorker.set_baudrate（运行中波特率热切换）")
    print("=" * 64)
    QApplication.instance() or QApplication([])

    section("[1] 端口未打开 / 串口对象未开：只记配置")
    w, logs, errors, bauds = make_worker(None)
    w.configure(port="COM9", baudrate=9600)
    check("未接串口也能切（返回 True）", w.set_baudrate(115200) is True)
    check("配置已记下（下次 open_port 生效）", w.baudrate() == 115200, w.baudrate())
    check("发 baudrate_changed（UI 才能同步回显）", bauds == [115200], str(bauds))
    check("没发生的事不写日志（未开端口 => 无 [串口] 行）", logs == [], str(logs))
    check("无错误", errors == [], str(errors))

    w2, _logs2, _errs2, bauds2 = make_worker(FakeSerial(is_open=False))
    w2.configure(port="COM9", baudrate=9600)
    check("[对照] 有串口对象但 is_open=False 也走「只记配置」",
          w2.set_baudrate(115200) is True and w2.baudrate() == 115200
          and bauds2 == [115200] and _logs2 == [],
          f"{w2.baudrate()} / {_logs2}")

    section("[2] 端口已开：先排空发送缓冲再改速率，且不关/不重开端口")
    fake = FakeSerial(is_open=True)
    w3, logs3, errs3, bauds3 = make_worker(fake)
    lock = CountingLock()
    w3._write_lock = lock
    check("返回 True", w3.set_baudrate(115200) is True)
    check("顺序 = 先 flush 后改速率（换序就发残帧）",
          fake.events == [("flush",), ("baudrate", 115200)], str(fake.events))
    check("串口对象上的速率真的变了", fake.baudrate == 115200, fake.baudrate)
    check("worker 记下新速率", w3.baudrate() == 115200, w3.baudrate())
    check("用了共用写锁（与 send_frame/write_raw 同一把）", lock.entered == 1, lock.entered)
    check("发 [串口] 日志且带新速率",
          len(logs3) == 1 and "115200" in logs3[0], str(logs3))
    check("发 baudrate_changed", bauds3 == [115200], str(bauds3))
    check("无错误", errs3 == [], str(errs3))
    check("绝不关端口（一个 close 都没有）",
          not any(e[0] == "close" for e in fake.events), str(fake.events))

    section("[3] 参数非法：配置与串口都不动")
    for bad in ("abc", 0, -1, None, "", "9e9x"):
        fake4 = FakeSerial(is_open=True)
        w4, logs4, errs4, bauds4 = make_worker(fake4)
        w4.configure(port="COM9", baudrate=9600)
        ok = w4.set_baudrate(bad)
        check(f"非法波特率 {bad!r} => False + error_occurred",
              ok is False and len(errs4) == 1 and "波特率非法" in errs4[0],
              f"{ok} / {errs4}")
        check(f"非法波特率 {bad!r} 不动串口（零 flush/改速）", fake4.events == [],
              str(fake4.events))
        check(f"非法波特率 {bad!r} 不改配置", w4.baudrate() == 9600, w4.baudrate())
        check(f"非法波特率 {bad!r} 不发 baudrate_changed", bauds4 == [], str(bauds4))

    section("[4] 底层失败：不改 _baudrate（不许说谎）、不发 baudrate_changed")
    fake5 = FakeSerial(is_open=True, flush_fail=True)
    w5, logs5, errs5, bauds5 = make_worker(fake5)
    w5.configure(port="COM9", baudrate=9600)
    check("flush 失败 => False + error_occurred",
          w5.set_baudrate(115200) is False and len(errs5) == 1
          and "切换波特率失败" in errs5[0], str(errs5))
    check("flush 失败 => 停在 flush，没动速率（残帧风险宁可停下）",
          fake5.events == [("flush",)], str(fake5.events))
    check("flush 失败 => 不改 _baudrate / 不发 baudrate_changed",
          w5.baudrate() == 9600 and bauds5 == [], f"{w5.baudrate()} / {bauds5}")
    check("flush 失败 => 不写「已切换」日志", logs5 == [], str(logs5))

    fake6 = FakeSerial(is_open=True, baud_fail=True)
    w6, _logs6, errs6, bauds6 = make_worker(fake6)
    w6.configure(port="COM9", baudrate=9600)
    check("改速率失败 => False + error_occurred",
          w6.set_baudrate(115200) is False and "切换波特率失败" in errs6[0], str(errs6))
    check("改速率失败 => 先 flush 过（顺序没错），串口仍停在旧速率",
          fake6.events == [("flush",), ("baudrate", 115200)] and fake6.baudrate == 9600,
          f"{fake6.events} / {fake6.baudrate}")
    check("改速率失败 => 不改 _baudrate / 不发 baudrate_changed",
          w6.baudrate() == 9600 and bauds6 == [], f"{w6.baudrate()} / {bauds6}")

    section("[5] 反例自检（判据不是恒真）")
    check("反例：成功的切换确实改了串口速率（不是只记账）",
          fake.baudrate == 115200 and w3.baudrate() == 115200)
    check("反例：成功与失败两条路的日志/信号数不同（判据能区分）",
          len(logs3) == 1 and bauds3 == [115200] and logs5 == [] and bauds5 == [],
          f"{len(logs3)} / {bauds3} / {logs5} / {bauds5}")
    check("反例：未开端口时确实没有 [串口] 日志（与已开端口那组不同）",
          logs == [] and len(logs3) == 1)

    print()
    print("=" * 64)
    print(f"PASS={PASS} FAIL={FAIL}")
    print("=" * 64)
    sys.stdout.flush()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
