# 技术设计 · 多线程下载器四批次加固

## 1. 现状与改动边界

| 文件 | 角色 | 本轮改动 |
|---|---|---|
| `downloader.py` | 纯逻辑：规划/探测/分段/合并/续传/控制 | 新增响应自证、单流续传、取消保留策略、快速取消、429 退避、删死参数 |
| `update_download_dialog.py` | 非模态面板（不做网络 IO） | 按钮宽度、暂停态显示、`closeEvent` = 后台运行、`mark_*` 状态收口 |
| `main_gui.py` | `_UpdateDownloadWorker` + `_start_download` + 收尾 | 防重入、退出取消、状态栏清理、面板重开入口、删死信号 |

不改：`auto_updater.py` 的 `update.bat` 模板、`Opdater.verify` / `stage_and_replace`（仅调用点微调）。

## 2. R1 · 服务端忽略 Range（HTTP 200）的处理

**问题**：`_download_segment` 接受 `status in (200, 206)`，200 时按 `seg.start + seg.done` 落盘 ⇒ 越段污染 + `seg.done` 被推大。

**设计**：引入**分段响应自证**函数，返回 `(ok, reason, reset_done)`：

```python
class _RangeViolation(DownloadError):
    """该源无法按段提供数据（忽略 Range / 偏移不符 / 总长不符）。"""
    def __init__(self, msg, reset: bool = True): ...
```

判据（顺序执行，任一不过即 `_RangeViolation`）：

1. `status == 200`：
   - `seg.start == 0 and seg.done == 0 and len(plan.segments) == 1` → 允许（等价整文件）；
   - 否则 `_RangeViolation("服务器忽略了 Range 请求", reset_done=True)`。
2. `status == 206`：解析 `Content-Range: bytes a-b/total`
   - 解析失败 → 视为违规（无自证即不可信）；
   - `a != seg.start + seg.done` → 违规（偏移不符）；
   - `total` 存在且 `!= plan.total_size` → **不可重试**的 `DownloadError`（资源已变化）。
3. 其他状态码沿用现有 `HTTP xxx` 错误。

**处理**：`_download_segment` 捕获 `_RangeViolation`：
- `reset_done=True` ⇒ `seg.done = 0`，**不再重试**，向上抛 `_RangeUnsupported`；
- `download_multithreaded` 捕获 `_RangeUnsupported` ⇒ 清理该 .part 的脏区（`cleanup_partial`）后**回落单流**（`_download_single_stream`），并把 `plan.supports_range` 记 False。

> 取舍：不做「某段可分段、某段不可」的混合模式 —— 一旦有段不支持，说明源整体行为不可信，回落单流最安全。

## 3. R2 · 退出取消 + 可中断暂停

- `DownloadControl` 新增：

```python
self._resume = threading.Event(); self._resume.set()

def pause(self):  self._pause.set(); self._resume.clear()
def resume(self): self._pause.clear(); self._resume.set()
def cancel(self): self._cancel.set(); self._pause.clear(); self._resume.set()
def wait_resumed(self, timeout: float | None = None) -> bool:
    """等待 resume/cancel；返回 True = 应继续，False = 已取消或超时。"""
```

- `_UpdateDownloadWorker.run` 里 pause 等待改 `self.control.wait_resumed(0.5)` 循环（每次回看 `cancelled`），彻底去掉 `time.sleep(0.1)` 轮询。
- `main_gui.closeEvent` 收尾块：对 `_download_thread` 先 `cancel()` 再 `wait(2000)`；`_safe_wait` 保持兜底。因为 `cancel()` 会 set `_resume`，暂停态线程立即退出等待 → 分段线程在块边界退出 → executor join。

## 4. R3 · 下载防重入

`_start_download()` 开头：

```python
th = getattr(self, "_download_thread", None)
if th is not None and th.isRunning():
    dlg = getattr(self, "_download_dlg", None)
    if dlg is not None:
        dlg.show(); dlg.raise_(); dlg.activateWindow()
    self.statusBar().showMessage("已有下载任务在进行，请先取消或等它完成", 6000)
    return
```

## 5. R4/R5 · 续传自证

`_load_progress` 增加：

```python
if data.get("url") and data["url"] != plan.url:
    return segments          # url 变了：整份作废
```

（`data.get("url")` 空串时保持兼容旧文件。）

`Content-Range` 校验落在 `§2` 的 `_verify_segment_response`，单一实现，不重复。

## 6. R6 · 单流续传

`_download_single_stream(url, dest, ..., resume=True)`：

- 读取已有 `.part` 大小 `off`；
- 请求头加 `Range: bytes=<off>-`（仅当 `off > 0`）；
- 响应 206 ⇒ `open(part, "ab")` 追加、`done` 从 `off` 起算；
- 响应 200 ⇒ 服务端不支持续传：记 `resume_supported=False`，`open(part, "wb")` 从头写，**并通过 `DownloadProgress(state="restart")` 明示**（面板只显示一行提示，不改状态机）；
- `resume=False` ⇒ 先 `cleanup_partial(dest)`。

## 7. R7 · 磁盘错误

`download_multithreaded` 预分配段：

```python
try:
    with open(part_path, mode) as handle:
        if handle.seek(0, os.SEEK_END) < total:
            handle.truncate(total)
except OSError as exc:
    raise DownloadError(_describe_os_error(exc, total)) from exc
```

`_describe_os_error`：`ENOSPC` → `磁盘空间不足：需要 <format_bytes(total)> 可用空间（<exc>）`；其它 `OSError` → `无法读写临时文件：<exc>`。`_merge_segments` 的写盘 `OSError` 同用该函数。

## 8. R8/R9/R10/R11 · 面板与接线

- **R8**：`UpdateDownloadDialog.closeEvent` → `event.ignore(); self.background_requested.emit(); self.hide()`（等价「后台运行」），并置 `self._went_background = True`。`main_gui` 在「配置」菜单加「下载进度…」（仅当 `_download_dlg` 存在且 `_download_thread.isRunning()` 时 enabled），点击 `show()/raise_()/activateWindow()`。状态栏进度文本前置「点『配置 → 下载进度』可查看」。
- **R9**：`_on_download_done` / `_on_download_cancelled_cb` / `_on_download_failed`（新增统一收尾 `_clear_download_statusbar()`）调用 `self.statusBar().clearMessage()`。
- **R10**：三按钮改 `gui_utils.fit_btn_width(self.pause_btn, self.background_btn, self.cancel_btn)`，删掉 `setFixedWidth`。
- **R11**：`update_progress` 读 `progress.state`：
  - `paused` → 标题区 `threads_label` 显示「已暂停」、每行状态列「⏸ 已暂停」、`hint_label` 保留暂停说明；
  - `running` → 恢复「下载中」；
  - 状态存 `self._last_state`，表格 `_refresh_table` 用它决定状态列文案（不新增 `mark_*` API）。

## 9. R12/R13/R14 · 去死代码

- **R12**：`DEFAULT_MAX_THREADS` 真正生效 —— `choose_thread_count(total, max_threads=None)` 的 `limit` 取 `DEFAULT_MAX_THREADS`（16）；`_resolve_download_threads(None)` 保持返回 `None`（= 自动），文档注释与 README/CHANGELOG 口径统一写「自动（上限 16，可在更新设置里调到 32）」。

  > 依据：`DEFAULT_MAX_THREADS` 的注释本来就是「自适应时的天花板」。让常量生效比删掉它更符合原意，也让「自动」不再一上来就 32 线程。

- **R13**：删除 `download_multithreaded(..., http_probe=None)` 参数（全仓无调用方传它，`test_downloader` 只用 `http_head`）。
- **R14**：删除 `_UpdateDownloadWorker.progress` 信号与 `progress_cb` 传参（无人连接；状态栏与面板都吃 `stats`）。

## 10. R15 · 取消保留进度

`download_multithreaded(..., on_cancel="keep" | "clean" = "keep")`：

- `keep`：只保存进度（`.part` + `progress.json` 保留），抛 `DownloadCancelled`；
- `clean`：`cleanup_partial(dest)` 后抛。

面板：`cancel_requested` 拆成 `cancel_requested`（保留）与 `discard_requested`（清理），「取消」按钮 + 下拉/次按钮「取消并清理」。为最小改动：主按钮文案「取消（保留进度）」，另加一个「清理缓存」按钮，仅在 `mark_cancelled` 之后可用（下载停止时清）。

> 产品决定：默认保留，避免 100 MB 白下；「清理缓存」随时可用（含失败后）。

## 11. R16 · 快速取消

- 取消判定后立即 `pool.shutdown(wait=False, cancel_futures=True)`，不再 `for fut in futures: fut.result()` 顺序等待全部；
- 已完成/失败的 future 仍收集错误（用 `concurrent.futures.as_completed` + 取消时提前 `break`）；
- 删除 `if control.cancelled: pass` 空语句。

## 12. R17 · Retry-After

`_download_segment` 的异常分支：

```python
delay = RETRY_BACKOFF * (attempt + 1)
if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 503):
    ra = exc.headers.get("Retry-After") if exc.headers else None
    if ra and ra.strip().isdigit():
        delay = min(float(ra), RETRY_AFTER_MAX)   # RETRY_AFTER_MAX = 10.0
time.sleep(delay)
```

## 13. 测试设计（可反证）

| 测试文件 | 新增用例 |
|---|---|
| `test/test_downloader.py` | R1（第 N 段回 200）、R4（url 不符作废）、R5（Content-Range 偏移错）、R6（单流 Range 续传 + resume=False 清缓存）、R7（ENOSPC 中文）、R12（自动上限）、R15（keep vs clean）、R16（取消不等待卡死段）、R17（429 Retry-After 计时）、静态守卫（`http_probe` 不存在、无 `for fut in futures` 顺序等待） |
| `test/test_update_download_dialog.py` | R8（closeEvent 变后台 + 可从 `background_requested` 观测）、R10（三字号不裁字 + 未写死）、R11（paused 状态显示）、R15（清理缓存按钮存在且发出 `discard_requested`） |
| `test/test_update_download_wiring.py`（新） | offscreen：R2（pause 后 close 主窗口 → cancel 生效 + 线程退出）、R3（重复 `_start_download` 被拒 + 面板 show）、R9（结束后状态栏空）、R8（菜单项能重开面板）、R14（源码无 `progress` 死信号）、R15（取消后 `.part` 存在） |

反证要求：对 R1/R2/R3/R5/R10/R15 各做一次「把修复改回旧写法 → 断言必须变红 → 还原」。

## 14. 风险与回滚

- 风险：`_download_single_stream` 追加写可能遇到「.part 比真实已下载更长」（历史预分配）⇒ 续传起点必须取 `min(off, total)`，且**单流不预分配**（`.part` 大小即真实进度），避免误判。
- 回滚：改动集中在三个文件 + 测试；`git checkout -- downloader.py update_download_dialog.py main_gui.py` 即可回到 1.23.95 行为。
