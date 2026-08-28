# 执行记录：线程计数显示与统一关闭回收

## 改动清单

- 新增 `thread_registry.py`：QThread 弱引用注册中心（track / qthreads_alive / py_threads_alive / snapshot）。
- 各 QThread 构造时登记并设 objectName：
  - `serial_worker.py` SerialWorker
  - `monitor/tcp_monitor.py` PacketSniffer；新增 `TCPMonitorWidget.cleanup()`（停 `_ui_timer` + 抓包线程）
  - `system_integration/global_hotkey.py` GlobalHotkeyThread
  - `llm_preprocess.py` LLMWorker（惰性 import，兼容无 Qt 环境）
  - `llm_api_manager.py` _TestThread
  - `main_gui.py`：_UpdateCheckWorker、_UpdateDownloadWorker、`_py_script_thread` 创建处 track
- `main_gui.py` 状态栏：
  - 新增 `_thread_count_lbl`（永久控件，显示「线程: N」）+ 1s `_thread_count_timer`。
  - 新增 `_refresh_thread_count()`：计数 = Python 线程 + QThread；tooltip 分组列出名称。
- `main_gui.py` 关闭回收：
  - 新增 `_shutdown_threads()`，在 `closeEvent` 真正退出分支调用（`_is_closing=True` 之后）。
  - 顺序：停定时器 → 更新检查/下载线程断开信号+wait → 串口 close_port+wait → 热键 stop → 剪贴板 stop → TCP cleanup → LLM cancel → 脚本线程 requestInterruption+quit+wait → 兜底遍历注册表 requestInterruption+quit+wait。
  - 每步 try/except；阻塞线程不 terminate，超时随进程退出。

## 验证

- 语法检查全部通过。
- offscreen 启动：状态栏显示 `线程: 1`，tooltip 正确分组列出。
- 启动测试 QThread 时计数增至 2，`close()` 后线程被中断回收（running=False）。
- 所有被改模块导入正常；构造即登记 objectName。
- 未做硬件级实测（真实串口/全局热键/scapy 抓包需真机环境），逻辑路径与各模块既有 stop/wait 接口一致。

## 回滚点

- 删除 `thread_registry.py` 并移除各文件 track 调用、状态栏 label/timer、`_shutdown_threads` 调用即可回滚。closeEvent 原有更新线程等待逻辑已被 `_shutdown_threads` 内对应步骤取代。
