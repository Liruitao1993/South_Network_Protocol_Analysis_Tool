# 关闭软件时拦截后台更新检查弹窗

## Goal

关闭软件时仍弹出「发现新版本：… 是否下载并更新？」对话框。要求关闭流程中不允许任何更新检查回调弹窗。

## Root Cause

更新检查用 `_UpdateCheckWorker(QThread)` 做网络 IO，超时最长 15s。用户点关闭时，若检查线程仍在跑，`closeEvent` 只 `wait(500)`+`wait(2000)` 就放行退出；线程结束后发出的 `result_ready` / `release_list_ready` 信号可能已排队进主线程事件队列，`disconnect` 清不掉已排队事件，应用完全退出前回调被执行，弹出更新确认框。

弹窗显示 `1.14.4 → 1.14.5`，与当前源码 `APP_VERSION=1.14.7` 不符，说明实际弹窗大概率来自系统中仍在运行的 1.14.4 旧进程（托盘/开机自启/打包安装版残留），但代码层关闭竞态同样需要修复以保证新版本不再复现。

## Implementation

文件：`main_gui.py`

1. `__init__` 增加 `self._is_closing = False`。
2. `closeEvent` 真正退出分支（最小化到托盘分支除外）开头置 `self._is_closing = True`，再停定时器/收尾线程。
3. 更新检查回调/触发入口加关闭守卫，命中直接 return：
   - `_auto_check_update`（定时器/singleShot 入口）
   - `_on_update_check_result_cb`（最新版检查结果）
   - `_on_version_list_result_cb`（版本列表结果）
   - `_on_update_status_clicked`（状态栏点击）
4. 最小化到托盘路径不置位，恢复显示后更新检查照常工作。

## Acceptance Criteria

- [x] offscreen：`_is_closing=True` 时投递 `result_ready`/`release_list_ready` 回调，不弹任何 QMessageBox。
- [x] 启动时 `_is_closing=False`，正常更新检查/状态栏提示不受影响。
- [x] 最小化到托盘后恢复，更新周期检查仍正常（该路径不置位）。
- [x] 语法检查通过、主窗口启动正常。

## Notes

- 轻量任务 PRD-only。
- 提示用户：若关闭后仍弹 `1.14.4→1.14.5`，说明是旧版本进程残留，需在任务管理器结束旧进程或卸载旧安装版/检查开机自启与托盘。
