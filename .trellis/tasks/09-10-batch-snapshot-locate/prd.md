# 批量解析右键定位原始日志快照

## Goal

批量解析的输入日志往往先经过预处理（hex_clean 脚本 / CLI 预处理 / 协议9监控头剥离），输入框内容被改写后，摘要表中的帧无法再回看它在**原始日志**中的位置与上下文。本任务为协议无关的批量解析摘要表新增「转到原始报文位置」右键功能：拖入/打开/粘贴原始日志时建立**不可变快照**（预处理只改输入框、永不改快照），右键摘要表某帧 → 弹出 Notepad++ 式只读查看器展示快照原文，自动高亮并滚动到该帧命中行，弹窗内置关键字搜索定位。

## Confirmed Facts（代码证据）

- 批量解析链 `parse_batch`（main_gui.py L7468 起）：输入框全文 →（协议9/10/11 strip、`_clean_hex_input` 均为**内存内变换**，不动输入框）→ `_extract_frames_for_protocol` → 每帧仅存 `batch_results[i]["_input"] = frame_hex`（L7712-7720），**帧→原文位置信息全程丢失**。
- 回填式预处理**会覆写输入框**：CLI 预处理 `_run_cli_preprocessor` L8789 `setPlainText(result)`；Python 脚本 `_on_py_script_finished`（QTextCursor 全文替换）。这是原文丢失点，也是"事后匹配框内容"方案的致命缺陷（用户已指出）。
- 输入框写入点（快照挂钩处）：拖拽 `DragDropTextEdit.dropEvent` L956；「打开文件」`load_from_file` L7380；「粘贴」`paste_from_clipboard` L7393。三处均为 `setPlainText(全文)`。
- 摘要表 `batch_summary_table`（创建段 L2594-2628）：第 0 列 item `Qt.UserRole` 存 `batch_results` 原始索引；右键已被通用复制菜单占用（`_setup_table_copy_menu` L2622，处理函数 L5908）。
- 帧 hex ≥16 字节（32 hex 字符），在快照归一化字符流中随机误命中概率可忽略；重发帧多次出现用"摘要第 n 次 = 快照第 n 个命中"消歧（提取按行序，顺序天然一致）。
- 单帧页已有行内高亮+滚动惯例 `_highlight_bytes`（L9946+，黄色 extraSelection 同色系）；新组件规范见 `.trellis/spec/frontend/component-guidelines.md`（独立文件 + 纯逻辑层无 Qt 可测 + 构建/弹出分方法）。
- 协议9 跨行帧形态：`_strip_csg_new_gen_frame_prefix` 可把跨行帧体拼接，故快照匹配必须支持**跨行命中**（全文归一化字符流 + 行号映射，一次 find 覆盖单行/跨行）。

## Requirements

### R1 快照链（协议无关）
- `MainWindow._batch_snapshot_text/_batch_snapshot_name`：拖入（文件名）/打开文件（文件名）/粘贴（"剪贴板"）三处建立，**重复设置以最后一次全文为准**（用户换日志=换基线）。
- CLI/脚本回填、手工编辑、parse_batch 内存变换**一律不触碰快照**。
- 用户未走上述入口直接手敲再解析：`parse_batch` 兜底把当时框内全文记为快照（仅当快照为空）。
- 「清空」`clear_batch`：清框同时清快照与弹窗引用。

### R2 帧→快照行定位（纯逻辑，无 Qt 可测）
- `find_frame_in_text(text, frame_hex) -> list[(起行, 止行)]`（按文本顺序、不重叠扫描）：快照逐行提取 hex 字符构成全文归一化流，每字符携带源行号；`frame_hex` 归一化后在流中循环 `find`，命中段映射回 (起行,止行)——单行/跨行统一处理。
- 消歧：帧在 `batch_results[0..idx-1]` 中已出现 n 次 → 取第 n 个命中（1-based）；命中不足取最后一个；零命中返回空由 GUI 提示。

### R3 快照查看器弹窗（Notepad++ 式，只读）
- 新独立文件 `batch_source_view.py`；`QPlainTextEdit` 只读 + 行号边栏 + NoWrap + 等宽字体；窗口 ≥1000×640，非模态单实例（重复右键复用并重新定位）。
- 打开即：目标帧行范围黄底高亮、`centerCursor` 滚动居中；状态行显示「帧 #k 定位到第 a–b 行」或未命中提示。
- 内嵌查找条（可显隐）：关键字 + 上一个/下一个 + 命中计数「当前/总数」+ 区分大小写；回车=下一个；所有命中橙色高亮、当前命中红底；Esc 收起查找条并清除搜索高亮（帧黄底保留）；Ctrl+F 唤起。
- 不可编辑、无文件菜单；关闭即释放。

### R4 右键接线
- `batch_summary_table` 专用上下文菜单（替换通用复制菜单挂载）：「转到原始报文位置」/「复制本帧HEX」/ 分隔线 /「复制选中行」/「复制全部」（后两项复用既有方法）。
- 右键落在选区外先选中该行（Qt 惯例）；构建菜单与弹出分为两个方法（可测）。
- 无快照时点定位 → 提示引导（不弹查看器、不崩溃）。

### R5 约束
- 零新增第三方依赖；不修改 `parse_batch` 帧提取/解析循环内部（只在入口挂快照兜底）；不改 `_strip_*` / `_extract_frames_for_protocol` 签名。

## Acceptance Criteria

1. 拖入含监控前缀的协议9原始日志 → 跑 hex_clear 回填 → 批量解析 → 右键任一帧：弹窗展示的是**含监控前缀的原始行**，目标行高亮居中，行号正确。
2. 同一帧在日志中重发 2 次：摘要两条帧右键分别落到第 1、2 个命中行。
3. 弹窗查找条输入 hex 片段回车：命中计数正确、循环跳转；Esc 收起后帧高亮仍在。
4. 直接粘贴 698.45（协议8）hex 行解析后右键同样工作（协议无关）。
5. `test/test_batch_snapshot_locate.py`：纯逻辑（单行/跨行/重发消歧/未命中/时间戳不误拆）+ offscreen GUI（快照链三入口、parse_batch 兜底、clear_batch 清快照、菜单构建项、定位弹窗高亮行号、查找计数）全过；协议9/8 既有批量回归无破坏。
6. CHANGELOG 1.23.0 增条目；AGENTS.md §3 增 `batch_source_view.py`。
