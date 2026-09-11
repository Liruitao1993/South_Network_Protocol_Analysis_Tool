# 实现计划：批量解析右键定位原始日志快照

## Step 1 — `batch_source_view.py`（新文件）— 完成
- [x] 前半纯逻辑（无 Qt import）：`normalize_hex`、`hex_stream(text)->(stream,line_of)`（**逐行剥行首时间戳/日志标签**，防时间戳数字混入帧体打断连续性；移植自 scripts/hex_clean.py）、`find_frame_in_stream / find_frame_in_text -> list[(s,e)]`（非重叠、跨行统一、<4 字符返回 []）
- [x] 后半 Qt：`_LineNumberArea` + `SourceLogView(QPlainTextEdit)` 只读+行号边栏+NoWrap+等宽；`SourceViewerDialog(QDialog)` = `set_source`（同文本对象跳过重灌）/`show_frame`（黄底整行范围+centerCursor+状态行）/`toggle_find_bar`/`find_next/find_prev`（全命中橙色、当前红底、循环取模、计数）/`_apply_extras`（帧+搜索两组 selections 合并）/`keyPressEvent`（Ctrl+F 唤起、Esc 收起并清搜索）
- [x] 验证：import + 纯逻辑 11 项手测通过

## Step 2 — main_gui 快照链 — 完成
- [x] `__init__`：`_batch_snapshot_text/_batch_snapshot_name/_snapshot_hex_cache/_src_viewer`
- [x] `_set_batch_snapshot(text, name)`（CRLF/LF 归一 + 流缓存失效）
- [x] 三入口挂钩：`DragDropTextEdit.dropEvent`（hasattr 守卫，文件名）/ `load_from_file`（basename）/ `paste_from_clipboard`（"剪贴板"）
- [x] `parse_batch` 入口兜底：快照空且框非空 → 以现框文为快照（"输入框内容"）
- [x] `clear_batch`：清快照两字段 + 关查看器（close/deleteLater/置 None）
- [x] `_snapshot_stream()` 懒建缓存：同一快照对象复用（右键重复点击 O(1)，10MB 日志只归一化一次）

## Step 3 — main_gui 右键接线 — 完成
- [x] 摘要表改挂 `_setup_batch_summary_menu()`（专用菜单，含原通用复制项）
- [x] `_build_batch_summary_menu(table, pos)` 纯构建（可测）：定位/复制本帧HEX/分隔/复制选中行/复制全部；右键落选区外先 selectRow；空表/无数据时定位项禁用
- [x] `_locate_frame_in_snapshot(frame_idx)`：nth 消歧（摘要中该帧第 n 次出现 → 快照第 n 个命中，超界取末个）→ 缓存流匹配 → `_ensure_source_viewer()`（非模态单实例）`set_source + show_frame + raise`；无快照弹信息提示，零命中弹窗但状态行「未能定位」+ update_stats
- [x] spec hiddenimports 登记 `batch_source_view`

## Step 4 — 测试 — 完成
- [x] `test/test_batch_snapshot_locate.py` **41 项全过**：纯逻辑 12（单行/跨行/重发非重叠/重叠假命中/大小写/短输入/未命中/流一致性/监控头邻接不误拆）+ 快照链 6 + offscreen GUI 23（真实协议9 监控日志 parse_batch → 定位行号断言 0/2/1、重发消歧、查看器复用、搜索 1/3→2/3→1/3 与 extras 合并、Ctrl+F 真实按键、clear_batch 清理、菜单项/启用态/选区外先选中、无快照 monkeypatch 捕获提示、parse_batch 兜底）
- [x] 回归无破坏：test_batch_src_line_jump(7) / test_csg_batch_prefix / test_csg_batch_parse_level / test_csg_summary / test_dl_t698_45 / test_hex_clean_script(19) / test_csg_sequence_model / test_csg_sequence_gui(27) 全 exit=0
- 坑记录：`extraSelections()[0].cursor` 链式访问会因 shiboken 临时列表析构连带 cursor 失效 → 测试必须持列表引用；`Qt.Modifier.ControlModifier` 不存在 → `Qt.KeyboardModifier.ControlModifier`

## Step 5 — 文档 — 完成
- [x] CHANGELOG 1.23.0 新条目
- [x] AGENTS.md §3 架构树 + §7 测试清单（含 hex_clean_script）


## Step 6 — 二阶段增强（用户追加需求：更快 + 弹窗保持）— 完成
- [x] 加速：`_snapshot_hits` 按帧命中缓存（`_snapshot_frame_hits`），重复定位/连续切行零重算 find；快照重建/清空三处同步失效
- [x] 快捷键：摘要表 `QShortcut(Ctrl+G, WidgetShortcut)` → `_locate_current_batch_frame`（取当前行 UserRole 索引）；右键菜单项文本与 setShortcut 同步示警
- [x] 弹窗保持：`_locate_frame_in_snapshot(idx, silent=True)` —— 弹窗已开时切行（`_on_batch_row_selected` 尾部挂跟随）只刷新高亮，不 show/raise/activate、不弹任何模态提示；弹窗关闭后自动停止跟随
- [x] 测试扩至 47 项（缓存计数 monkeypatch 验证零重算 / 真实 QKeyEvent Ctrl+G / 切行跟随行号断言 / 关窗后不跟随）；回归 test_batch_src_line_jump / test_csg_sequence_gui / test_hex_clean_script 全过
- 坑记录：QAction.setShortcut 会显示快捷键并支持触发，但焦点在表格时以 QShortcut(WidgetShortcut) 为准（菜单未弹出时 QAction 快捷键不生效——实测 Ctrl+G 走 QShortcut 路径）