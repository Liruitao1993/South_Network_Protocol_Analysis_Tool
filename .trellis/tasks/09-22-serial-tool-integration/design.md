# 技术设计：串口工具集成

对应 `prd.md`（R1~R9）。本文只写技术设计与契约。

## 1. 模块边界

| 文件 | 动作 | 内容 |
| --- | --- | --- |
| `serial_tool_widget.py` | **新增** | `SerialToolWidget(QWidget)`（页面主体）+ `SerialCommandDialog(QDialog)`（增改命令）+ `SerialSendWorker(QThread)`（精确间隔发送线程）+ 纯函数 `check_match()` / `hex_str_to_bytes()` / `load_hex_messages()` |
| `serial_worker.py` | **小改（纯增量）** | 新增 `write_raw(data) -> bool`：发送字节但**不发日志信号**，并给 `send_frame`/`write_raw` 加同一把写锁 |
| `main_gui.py` | **小改** | `setup_ui` 加占位 Tab「串口工具」；Tab 切换处理加 `elif`；新增 `_ensure_serial_tool_tab()`（懒加载 + 接线 + 中文右键菜单） |
| `test/test_serial_tool_widget.py` | **新增** | 见 R9 |
| `test/test_serial_worker_write_raw.py` | **新增** | `write_raw` 行为（发字节、不发日志信号、未连接返回 False） |

**复用（不新增第二份实现）**：`serial_worker.SerialWorker`（端口列举/打开/接收循环）、`gui_utils.set_btn`/`set_btn_icon`/`ZoomableTableWidget`、`app_icons.load_icon`、`_setup_table_copy_menu`、`apply_chinese_context_menus`、`thread_registry.track`、`app_paths.data_path`、项目主题 QSS。

**不照搬**：源工具的 `THEMES`/`BAUD_RATES` 常量里的主题部分（波特率列表照搬）、`QMainWindow`/状态栏、自定义 stylesheet。

## 2. 数据流

```
SerialToolWidget
  ├─ 串口：SerialWorker(实例独占) ── raw_data_received(bytes) ──┬─→ 匹配（实时，先于聚合）
  │                                                              └─→ 显示缓冲（raw 聚合 / frame 尾切分）
  ├─ 发送：SerialSendWorker(QThread) ── write_raw() ──→ SerialWorker._ser.write()
  │        └─ 信号 sent(seq, msg_index, data) / done() / failed(str)
  ├─ 匹配：_pending_match(deque) ← 发送回调入队；接收数据从队首连续匹配；100ms 定时器清超时
  └─ 统计/日志：200ms 轮询刷新标签；日志按类别着色 + 批量追加
```

## 3. 契约 A：串口层（`serial_worker.SerialWorker`）

```python
    def __init__(...):
        ...
        self._write_lock = Lock()      # 新增：GUI 线程与发送线程并发写保护

    def send_frame(self, frame_bytes: bytes) -> bool:
        """（原行为不变）写字节 + 发 [发送] 日志"""

    def write_raw(self, data: bytes) -> bool:
        """静默发送：只写字节，不发任何信号。

        为什么需要：负载测试按毫秒级间隔连发，逐帧 log_message.emit 会让 GUI
        队列被日志淹没（源工具正是为此把 TX 显示做成可关闭 + 批量）。
        未打开串口 → error_occurred + 返回 False；写异常 → error_occurred + False。
        与 send_frame 共用 _write_lock。
        """
```

- **不改变** `send_frame`/`send_hex_string`/`run()`/`_process_buffer()` 的既有行为（既有测试 `test/test_serial_worker_framing.py` 必须全绿）。
- 串口工具**复用主窗口共享的 `MainWindow.serial_worker`**（`_ensure_serial_tool_tab` 里 `tab.set_serial_worker(self.serial_worker)`），**不新建** `SerialWorker`：
  - 端口/波特率/校验只在顶部「串口配置」设置（`main_gui.py:12195` 一带），本页只读跟随 `connection_changed`；
  - 本页只订阅 `raw_data_received` / `error_occurred` / `connection_changed`，`set_serial_worker` 换绑时先解绑旧信号（照抄 `monitor_widget.set_serial_worker` 的写法）；
  - `cleanup()` **不关闭串口**（端口归主窗口与顶部串口配置），只停发送线程 + 落盘。
  - 理由：**一个 COM 口只能被打开一次**，各页各持 `SerialWorker` 会互相抢口（顶栏连上后本页再连必失败），且波特率会出现两处配置——与组帧页/监控器页的既有约定也不一致。

## 4. 契约 B：发送线程 `SerialSendWorker(QThread)`

照搬源工具 `SenderThread` 语义（**精确间隔**）：

```python
class SerialSendWorker(QThread):
    sent = Signal(int, int, bytes)   # seq(从0起), msg_index, data
    done = Signal()
    failed = Signal(str)

    def __init__(self, worker: SerialWorker, messages: list[bytes],
                 interval_ms: float, loop_count: int):  # loop_count=0 → 无限
```

- 循环：`for loop in range(...)` → `for i, msg in enumerate(messages)` → `worker.write_raw(msg)` → `sent.emit(seq, i, msg)`；`stop_event` 置位则立即 `done.emit()` 返回。
- 延时（除最后一条外）：`interval_s > 0.005` 时 `sleep(interval_s - 0.002)`，随后 `while perf_counter() < target: pass` 忙等。
- 写失败 → `failed.emit(msg)` 并结束（不再继续发）。
- `stop()` 置 `stop_event`；上层 `stop()` 后 `join(timeout=2)`（与源工具一致）。

## 5. 契约 C：接收与分帧

- 订阅 `SerialWorker.raw_data_received(bytes)`（每批原始字节）：
  1. **先**喂匹配（`_on_rx_match_data`），保证匹配不受显示聚合影响；
  2. 再进显示路径：
     - `raw` 模式：**帧结构优先、时间聚合兜底**。先 `_emit_structured_frames()` 按长度域切出**已收全且末字节为 16H** 的 68 帧（一行一帧）；剩余部分再按时间判定刷出。**不能按每次 `read` 直接输出**：串口驱动会把同一帧拆成多次交付，那样一帧会打成多行、RX 帧数虚增（首次实测报障）。**只做时间聚合也不够**：实测 208 字节国网帧被拆成 77+92+36+3 共 4 行，即交付块间隔本身就大于 10ms 静默窗口（第二次实测报障）—— 故改为按长度域收全。`_declared_frame_len()` 按**第二个起始符 68H 的位置**互斥判别三种结构（判别顺序先查第 4 字节，因 698.45 的第 4 字节恒为 68H；不足 8 字节或长度域越界一律退回时间聚合，**错切帧比不切更糟**）：698.45（第 4 字节，`68H + L(2B 小端) + 68H + … + FCS + 16H`，整帧 = L + 3，见协议文档 6.2.2）、645（第 8 字节，`68H + A(6) + 68H + C + L(1B) + … + 16H`，整帧 = L + 12）、南网/国网（以上都不是，`68H + L(2B 小端) + … + CS + 16H`，L = 整帧字节数）；末字节非 16H 时退回时间聚合。时间兜底参数：静默窗口 `RAW_FLUSH_DELAY_MS`(10ms)、最长持有 `RAW_MAX_HOLD_MS`(200ms，防持续流无界增长)、已声明长度未收全时的容忍静默 `FRAME_IDLE_MS`(300ms) 与绝对上限 `FRAME_HOLD_MAX_MS`(5s)。
     - `frame` 模式：进 `_frame_buffer`，按 `frame_tail` 循环切分（`find` → 取到含帧尾为止 → 余量留缓冲），逐帧刷出；**尾部残帧保留**直到下次收到数据或手动停止。
  3. 切换接收模式 / `cleanup()` 时**立即刷出**原始聚合缓冲（不丢数据）。
- `frame_tail` 解析用 `hex_str_to_bytes`；非法则保持上一有效值并提示（AC5.2）。
- 接收统计：`frames_received`/`bytes_received` 在刷出时累加（源工具口径：raw 模式按刷出批次计 1 帧）。

## 6. 契约 D：匹配与超时（纯函数，可单测）

```python
def check_match(received: bytes, expected: bytes, match_type: str) -> bool:
    """none→True；equals→==；contains→in；starts_with/ends_with；
    regex→按 latin-1 解码后 re.search(IGNORECASE)，非法正则返回 False。"""
```

- 入队（发送回调）：`启用匹配 and cmd.match_type != "none"` → `_tx_total += 1` 且 `_pending_match.append({...})`。
- 匹配（接收）：`while _pending_match:` 取**队首**，`check_match(data, expected, type)` 为真则 `_rx_matched += 1` 并 `popleft()`，继续试新队首；为假即 break（保持顺序语义）。
- 超时（100ms 定时器）：队首 `now - sent_time > timeout` 则弹出并 `_rx_missed += 1`，日志「#seq 名称 超时未匹配」。
- 停止/收尾：剩余 `_pending_match` 全部计入 `_rx_missed`（与源工具一致）。
- 统计标签：`发送 N 帧 / M B`、`接收 N 帧 / M B`、`匹配: 成功 A / 失败 B / 成功率 C%`、`运行: Xs`；成功率 = `matched / _tx_total`（`_tx_total == 0` 时显示 `—`）。
- 「清除统计」仅在非发送中可用；清除同时重置收发线程计数。

## 7. 契约 E：持久化

`app_paths.data_path("serial_tool_config.json")`：

```json
{
  "version": 1,
  "commands": [{"name": "...", "data_hex": "...", "match_type": "contains", "match_hex": "..."}],
  "params": {"interval_ms": 100, "loop_count": 1, "timeout_ms": 5000,
             "match_enabled": true, "rx_mode": "raw", "frame_tail": "FE 16",
             "show_tx": true, "show_rx": true, "auto_scroll": true}
}
```

- **导入/导出**：导出写**裸列表**（`[{"name","data_hex","match_type","match_hex"}, ...]`）→ 与源工具 `commands.json` 双向兼容；导入同时接受裸列表与本项目的 `{commands: [...]}` 形式。
- 写入时机：命令表增删改/上下移后、参数变更后（去抖：QTimer 500ms 合并写）、页面销毁前；读取时机：页面首次创建时。
- 文件缺失/损坏 → 用默认值，不抛异常（AC8.3）；落盘失败只记日志不弹窗。

## 8. 契约 F：UI 与主窗口集成

- 页面布局（与源工具同构，改用本项目控件风格）：
  - 第 1 行「串口」`QGroupBox`（**只读**）：`连接状态：<已连接/未连接>` + 提示「端口的连接/断开与波特率请在顶部『串口配置』中设置」
  - 中部 `QSplitter(Horizontal)`：左 = 「命令列表」(4 列表格 + 增删改上下移/保存/加载/加载报文文件按钮行) + 「发送配置」(间隔/次数/超时/启用匹配/开始发送) + 「接收模式」(原始数据/按帧尾分割 + 帧尾编辑)；右 = 「统计」+ 「日志窗口」(彩色 + 清空/自动滚动/显示发送/显示接收)
- 控件风格：文本按钮 `set_btn(...)` + `set_btn_icon(...)`；表格用 `ZoomableTableWidget` + `_setup_table_copy_menu`；页面构造末尾 `apply_chinese_context_menus(self)`；「开始发送」按钮的可用性由 `connection_changed` 驱动（未连接置灰，与 `frame_gen_widget._update_send_button_state` 同口径）。
- 日志着色：用 `QTextCharFormat` + `QTextCursor.insertText`（TX `#C00000` / RX `#008000` / 匹配 ✓ 绿 ✗ 红 / 系统与统计 `#1565C0`），与项目其它日志页风格一致；`setMaximumBlockCount(10000)`。
- **日志节流（AC7.3）**：发送日志不逐帧写，改为**按 100ms 批量汇总**（如 `[TX] #1..#37 共 37 帧`，或关闭显示时不写）；接收同样按批合并。
- 主窗口集成（照搬 TCP 监控的懒加载模式）：
  - `setup_ui`：`self._serial_tool_placeholder = QWidget()` + `self._serial_tool_tab_index = self.tab_widget.addTab(self._serial_tool_placeholder, app_icons.load_icon("cable"), "串口工具")`
  - Tab 切换处理：`elif index == getattr(self, "_serial_tool_tab_index", -1): self._ensure_serial_tool_tab()`
  - `_ensure_serial_tool_tab()`：`from serial_tool_widget import SerialToolWidget` → 实例化 → `self.serial_tool_tab = tab` → `self._replace_lazy_tab(self._serial_tool_placeholder, self._serial_tool_tab_index, tab)` → `apply_chinese_context_menus(tab)`
  - 与协议无关，**始终可见**（不加入任何协议可见性表）。
- 关闭/退出：主窗口关闭时停止发送线程与串口（复用 `thread_registry` 的统一收尾；页面暴露 `cleanup()`）。

## 9. 兼容性

| 既有契约 | 处理 |
| --- | --- |
| `SerialWorker.send_frame` 每帧发日志（`frame_gen_widget` 依赖 `log_message` 显示） | 不动；新场景走 `write_raw` |
| `test/test_serial_worker_framing.py`（28 项） | 必须全绿（只增不改） |
| `config.json` 的 `serial` 段（顶栏串口配置） | 不读写；串口工具用自己的数据文件 |
| `main_gui.setup_ui` 的 Tab 索引 | 新 Tab **追加在末尾**，不改既有索引；`_replace_lazy_tab` 已处理图标保留 |
| 源工具 `commands.json` | 可直接被「加载配置」导入（裸列表） |

## 10. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 高速发送淹没 GUI（逐帧日志/信号） | `write_raw` 静默发送 + 发送日志 100ms 批量 + 统计 200ms 轮询（照搬源工具做法） |
| 发送线程与接收线程并发写/读同一串口 | pyserial 读写可并发；写侧加 `_write_lock`；接收只在 worker 线程 |
| 忙等占 CPU（源工具为保精度刻意忙等） | 仅间隔 ≤5ms 或尾段 2ms 内忙等；间隔大时先 sleep |
| 停止/异常时线程残留 | 统一 `stop()` + `join(timeout=2)`；`cleanup()` 幂等；`thread_registry` 兜底 |
| 页面懒加载导致首帧延迟 | 与 TCP 监控同机制（首次切到该页才创建），不拖慢启动 |
| 端口被组帧页占用 | 明确「各自独立句柄」，打开失败按 AC2.3 报错（不静默） |
| 落盘写坏数据文件 | 写临时文件后 `os.replace` 原子替换；损坏时回落默认值 |

## 11. 回滚

- 三处改动互相独立可回滚：① `serial_worker.write_raw`（纯增量，删掉即可）② `serial_tool_widget.py`（新文件，删文件 + 移除 Tab 注册）③ `main_gui` 的 Tab 注册（3 处小改）。
- 快速开关：不注册 Tab 即完全回到现状（无副作用）。

## 12. 验证策略

- 新增 2 个测试文件（R9），offscreen 可跑，登记 `release_check.py:CORE_TESTS`。
- 硬门槛：`test/test_serial_worker_framing.py` 全绿 + `python release_check.py` 无新增 FAIL。
- 无串口环境的可测性：匹配/统计/分帧/持久化全部走纯函数或直接调方法（不打开真实串口）；串口相关分支用假 `SerialWorker`（鸭子类型）验证调用序列。
- 人工冒烟（需真实串口/回环）：连接 → 加命令 → 开始发送 → 看 TX/RX 日志与成功率；建议用虚拟串口对（com0com）或回环线自测。
