# research · 仓库复用与既有缺陷（2026-10-14，三路只读调查结论）

## 1. 串口通道与等待（结论）

- **唯一共享串口** = `main_gui.py:3035` 的 `self.serial_worker`；各页用 `set_serial_worker(worker)` 订阅（`serial_tool_widget.py:1970-1993` 为范本）。**不得**自建句柄（一个 COM 口只能打开一次）。
- `SerialWorker`：`send_frame`（带 `[发送]` 日志）/ `write_raw`（静默，`serial_worker.py:111`）；信号 `frame_received` / `raw_data_received` / `log_message` / `connection_changed` / `error_occurred`；无 `data_sent`。
- **`frame_received` 不能用于 698**：`_process_buffer`（`serial_worker.py:172-240`）只认 645 双 68H 与 FT1.2（`end_pos = pos + L`），698 整帧 = `L+2` ⇒ 必然落到「找第一个 0x16」容错分支被截断（600B 载荷含 0x16 概率 ≈90%）。**必须用 `raw_data_received` 自组帧**。
- 「发一帧 → 等一帧 → 超时」的**唯一先例**是 `test_plan_widget.TestPlanWidget`（单发 `QTimer` + 标志位，无重试，超时 100~600000ms 默认 2000），但它的等待挂在 `frame_received` 上且驱动 API 私有 ⇒ **只抄模式，不复用**。
- 698 分帧判据的既有正确实现：`serial_tool_widget.frame_length_for("dlt698_45", buf)`（`L+2` + 末字节 `16H` 自证 + 前导 FEH 容忍，`:1326-1388` + `:2756-2757`）。测试锚点：`test_dl_t698_45_extract.py:146-171`、`test_serial_proto_frame.py:67-92`。

## 2. 必须修复的既有缺陷（新页面绕不过）

| 缺陷 | 位置 | 证据 | 影响 |
|---|---|---|---|
| bit-string 长度域按字节（应为**位**） | `dl_t698_45_axdr.py:235-241`（解码）/ `:485-487`（编码） | doc 实帧 `04 03 E0` + 表188 `SIZE(3)`；改用位后 doc 帧**完整解析成功**（实测 32 行） | 阻塞 AC3/AC4 回读；`frame_gen_widget` 的 698 A-XDR 模式同样错 |
| 定长时间类型编码器多写长度域 | `_encode_date_time_s`/`_encode_date_time`/`_encode_date`/`_encode_time`（`:499-513`） | 规范类型表 + 示例 `1C 07 E0 01 14 00 00 00`；本仓库解码器本就按定长解（编码↔解码不自洽） | 执行升级帧会多 1 字节 |
| `_decode_time` 读 4 字节（规范 SIZE(3)） | `dl_t698_45_axdr.py:304-313` | 规范类型表 `time 27/3` | 本功能不使用；按 design §6.3 的「先试后验」处理 |

仓库内**无任何** 698 bit-string 测试（唯一 bit-string 测试在 `test_modular_iface_axdr.py`，用的是协议12 自己的模块）⇒ 修复无回归面。

## 3. 标签页接线（`main_gui.py`）

- 懒加载样板：占位 `QWidget` + `addTab` 取索引 + **创建处即 `setTabVisible(idx, False)`**（构造期 `_on_protocol_changed` 可能一次都不触发：`protocol_combo.addItem` 在 `connect` 之前，`:2792` vs `:2802`）→ `_ensure_lazy_tab`（`:4412-4429`）→ `_ensure_xxx_tab()`（样板 `:4500-4518`，末行 `_replace_lazy_tab` + `apply_chinese_context_menus`）→ `_on_protocol_changed` 显隐（`:4853-4860`）→ `_shutdown_threads`（`:8613-8627`）→ `_restyle_for_theme`（`:13310-13319`）。
- `ProtocolSpec` 共 23 字段（`protocol_registry.py:20-60`）；协议8 条目 `:180-195`。**全仓无对 ProtocolSpec 的反射**，新增 `has_upgrade` 只影响显式读取处。
- 拖放：全仓唯一先例 `main_gui.DragDropTextEdit`（`:2287-2349`）按**文本编码**读文件、且在 main_gui 内 ⇒ 二进制的升级包必须在页面内自建 `_DropArea`。
- 按钮宽度：`gui_utils.fit_btn_width`（`:84`）/ `fit_btn_width_for_texts`（`:115`）；折叠区 `collapsible_section.CollapsibleSection`（`:58`）；`ButtonScrollArea` 在 `bluetooth_tool_widget.py:116`（本页不需要）。
- 规范编号：`.trellis/spec/frontend/component-guidelines.md` 现有最大 §7i ⇒ 新章节 **§7j**。

## 4. 惰性 import 铁律

`dl_t698_45_parser.py:8`、`dl_t698_45_frame_gen.py:4` 顶层 `import crcmod.predefined`（可选依赖）⇒ 任何会被 GUI 间接 import 的模块**不得顶层 import 它们**。落地方式：Qt 页面在**动作方法内**惰性 import `dl_t698_45_upgrade`，并对其 ImportError 给出「请 pip install crcmod」的可读提示。

## 5. 既有行为（记录，不修）

升级期间其它订阅 `frame_received` 的页面（组帧页/预设/测试方案/档案/拓扑/旧监控器）会把 698 帧显示成被截断的「接收帧」——`SerialWorker` 既有容错分支的必然结果，非本次引入。
