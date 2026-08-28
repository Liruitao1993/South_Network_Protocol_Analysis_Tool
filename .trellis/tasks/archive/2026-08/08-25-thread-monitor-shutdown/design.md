# 设计：线程计数显示与统一关闭回收

## 方案

### 1. 线程注册中心 `thread_registry.py`

QThread 不是 Python `threading.Thread` 子类，`threading.enumerate()` 枚举不到它。新增轻量注册中心：

- `track(qthread, name=None)`：QThread 创建时登记，可选设 `objectName`。内部用普通 list，读取时清理已结束/已被 deleteLater 的弱引用失效项。
- `qthreads_alive()`：返回当前 `isRunning()` 的 QThread 列表，顺便回收死线程引用。
- `snapshot()`：返回 `(py_threads, qt_threads)`，前者来自 `threading.enumerate()`，后者来自注册表。

状态栏计数 = `len(py_threads) + len(qt_threads)`（含主线程，与「进程总线程数」语义一致）。tooltip 分组列出 Python 线程名与 QThread 对象名。

### 2. 登记点（在各 QThread.__init__ 调 track）

- `serial_worker.py` → SerialWorker
- `monitor/tcp_monitor.py` → PacketSniffer
- `system_integration/global_hotkey.py` → GlobalHotkeyThread
- `llm_preprocess.py` → LLMWorker
- `llm_api_manager.py` → _TestThread
- `main_gui.py` → _UpdateCheckWorker、_UpdateDownloadWorker；Python 脚本线程 `_py_script_thread`（创建处 track）

`test_plan_widget.py` 的 Lua `threading.Thread` 已是 daemon，短任务，随进程退出，不登记也不单独回收。

### 3. 状态栏计数

`setup_ui`/`__init__` 末尾加 `self._thread_count_lbl = QLabel()`，`statusBar().addPermanentWidget(...)`。
加 1s `QTimer` `_thread_count_timer`，槽 `_refresh_thread_count()`：
- 调 `thread_registry.snapshot()` 计数、拼 tooltip。
- tooltip：`Python 线程 (n):\n- MainThread\n- ...\n\nQThread (m):\n- SerialWorker\n- ...`。

### 4. 统一关闭回收 `_shutdown_threads()`

在 `closeEvent` 真正退出分支（已有 `_is_closing=True` 之后）调用。顺序：

1. 停所有相关 QTimer：`_update_poll_timer.stop()`、`_thread_count_timer.stop()`、TCP 监控 `_ui_timer`（由其 stop 流程处理）。
2. 更新检查/下载线程：`disconnect` 信号（关 _is_closing 已拦回调）+ `wait(500)`。
3. `serial_worker.close_port()` + `wait(1500)`。
4. `_hotkey_manager.stop()`（内部已 wait）。
5. `_clipboard_monitor.stop()`。
6. `tcp_monitor_tab._stop_capture()`（内部 sniffer.stop + wait(2000)）。
7. `llm_preprocess_widget`：若有运行中 worker，`cancel()`。
8. Python 脚本线程：`requestInterruption()` + `quit()` + `wait(1000)`。
9. 兜底：遍历 `thread_registry.qthreads_alive()`，对仍 running 的 QThread 统一 `quit()` + `wait(1000)`；网络 IO 阻塞无法中断的不断开就随进程退出（不 terminate，避免资源损坏）。

每步 try/except 包裹，单点失败不阻断后续回收。

### 5. 不做

- 不 `terminate()` 阻塞在系统调用的线程（scapy/网络），可能死锁或损坏；stop 标志 + 有限等待 + 信号断开后随进程结束。
- 不动 daemon 性质的临时 Lua 线程。
- 不引入 psutil。

## 影响文件

- 新增 `thread_registry.py`
- `main_gui.py`（状态栏、计时、shutdown、登记两个 worker 与脚本线程）
- `serial_worker.py`、`monitor/tcp_monitor.py`、`system_integration/global_hotkey.py`、`llm_preprocess.py`、`llm_api_manager.py`（各加一行 track）
