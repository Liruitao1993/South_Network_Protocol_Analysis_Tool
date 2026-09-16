"""批量解析「等待后台收尾」助手（test/ 目录共享，非测试脚本本身）。

任务 09-15-gui-batch-parse-perf 步骤 2 起，`MainWindow.parse_batch()` 立即返回，
真正的逐帧解析在 `BatchParseWorker` 线程执行、结果通过信号分批回填，收尾
（完成 / 取消 / 失败）才把 `_batch_worker` 置回 None。测试若沿用
「调用 parse_batch() 后立刻断言 batch_results」的写法会读到空集。

用法：

    from _batch_wait import wait_batch

    win.parse_batch()
    assert wait_batch(win), "批量解析超时未结束"
    assert win.batch_results

实现：泵事件循环（`QApplication.processEvents`）直到 `_batch_worker` 为 None；
解析中无 worker（输入为空/未提取到帧，`parse_batch` 提前返回）时立即返回 True。
"""

import sys
import time


def wait_batch(win, timeout: float = 30.0) -> bool:
    """等待后台批量解析收尾（完成/取消/失败任一路径）。

    Args:
        win: MainWindow 实例
        timeout: 超时秒数

    Returns:
        True = 已在超时前收尾；False = 超时（worker 仍在跑）
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while getattr(win, "_batch_worker", None) is not None:
        if app is not None:
            app.processEvents()
        if time.monotonic() > deadline:
            # 不静默：超时必须在测试输出里看得到（调用方随后的断言也会失败，
            # 这行输出把失败归因到「批量解析没结束」而不是业务断言本身）
            print(
                f"[wait_batch] 超时 {timeout:g}s：批量解析仍未收尾"
                f"（_batch_worker 非 None），后续断言基于不完整结果！",
                file=sys.stderr,
                flush=True,
            )
            return False
        time.sleep(0.005)
    if app is not None:
        # 收尾槽可能还有一批 progress 排在队列里，一并处理干净再断言
        app.processEvents()
    return True


__all__ = ["wait_batch"]
