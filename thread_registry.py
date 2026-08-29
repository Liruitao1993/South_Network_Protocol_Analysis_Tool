"""QThread 注册中心
=================
QThread 不是 Python ``threading.Thread`` 的子类，``threading.enumerate()``
枚举不到它。本模块提供一个极简登记处，供状态栏统计存活工作线程、
以及关闭时统一回收。

登记对象用弱引用持有，线程结束/被 deleteLater 后自动从快照中剔除，
不阻止 Qt 回收 C++ 对象。
"""

from __future__ import annotations

import threading
from typing import List, Tuple
from weakref import ref

from PySide6.QtCore import QThread

# 弱引用列表：每个元素是 weakref(QThread)
_QTHREADS: List["ref[QThread]"] = []


def track(qthread: QThread, name: str | None = None) -> QThread:
    """登记一个 QThread。可设 objectName 便于状态栏识别。返回原对象，便于链式调用。"""
    if name:
        try:
            qthread.setObjectName(name)
        except RuntimeError:
            pass
    _QTHREADS.append(ref(qthread))
    return qthread


def qthreads_alive() -> List[QThread]:
    """返回当前仍存活且在运行的 QThread，顺手清理失效弱引用。"""
    alive: List[QThread] = []
    dead_idx: List[int] = []
    for i, wr in enumerate(_QTHREADS):
        obj = wr()
        if obj is None:
            dead_idx.append(i)
            continue
        try:
            if obj.isRunning():
                alive.append(obj)
        except RuntimeError:
            # C++ 对象已被 deleteLater 回收
            dead_idx.append(i)
    for i in reversed(dead_idx):
        del _QTHREADS[i]
    return alive


def py_threads_alive() -> List[threading.Thread]:
    """返回当前存活的 Python threading.Thread（含主线程）。"""
    return list(threading.enumerate())


def snapshot() -> Tuple[List[threading.Thread], List[QThread]]:
    """返回 (Python 线程列表, QThread 列表)。"""
    return py_threads_alive(), qthreads_alive()
