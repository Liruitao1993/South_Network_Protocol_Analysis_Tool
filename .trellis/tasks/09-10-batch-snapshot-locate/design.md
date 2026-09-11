# 设计：批量解析右键定位原始日志快照

## 架构

```
DragDropTextEdit.dropEvent ─┐
load_from_file              ├→ MainWindow._set_batch_snapshot(text, name)   [快照=唯一不可变原文]
paste_from_clipboard       ─┘        │
parse_batch（入口兜底：快照空且框非空→以框现文为快照）
                                     ▼
                        self._batch_snapshot_text / _name
                                     │
CLI/脚本回填 · clear_batch(清空) · 手工编辑 ── 不写快照（回填式预处理保留原文的唯一保证）
                                     │
parse_batch 完成后不预计算行号（帧多时省时间；右键按需算）
                                     ▼
batch_summary_table 右键 ── _show_batch_summary_menu(pos)
   │  itemAt(pos) 取行 → UserRole=frame_idx；选区外先 selectRow
   ├─ 「转到原始报文位置」 _locate_frame_in_snapshot(frame_idx)
   │     hex = batch_results[i]["_input"]
   │     nth = 前 i 条中相同 _input 的个数        （重发消歧）
   │     hits = find_frame_in_text(snapshot, hex) （纯逻辑）
   │     hit  = hits[nth] or hits[-1]；空 → update_stats 提示
   │     viewer = _ensure_source_viewer()          （非模态单实例）
   │     viewer.show_frame(hit, frame_idx+1)       （高亮整行范围+居中+状态行）
   ├─ 「复制本帧HEX」 clipboard.setText(hex)
   └─ 「复制选中行」/「复制全部」 → 复用 _copy_table_rows
```

> **性能**：归一化流（10MB 日志 ≈ 2M 字符列表）只建一次并缓存（`MainWindow._snapshot_hex_cache = (snapshot_text, stream, line_of)`，快照不变即复用），右键只付 `str.find` 成本。

## 纯逻辑层（batch_source_view.py 前半，不 import Qt）

```python
def _line_offsets(text) -> list[int]         # 每行起始的文档字符偏移（\n 计 1）
def hex_stream(text) -> (stream, line_of)    # 全文 hex 字符归一化大写流 + 每字符源行号(0-based)
def find_frame_in_text(text, frame_hex) -> list[(s_line, e_line)]
    # stream.find(frame_hex) 循环（非重叠），命中段 [s,e) → (line_of[s], line_of[e-1])
    # 单行/跨行统一；frame_hex 先 re.sub 归一化；<4 字符返回 []
```

要点：
- 监控头/时间戳含 hex 字符**无害**：匹配的是帧体连续段，邻接噪声不参与子串比较；≥32 字符的 hex 子串随机误命中可忽略。
- 非重叠扫描与提取顺序一致：提取按行序取帧，第 n 次出现的帧 ↔ 快照第 n 个非重叠命中。
- 行号内部 0-based，UI 显示 +1。

## UI 层（batch_source_view.py 后半）

- `SourceLogView(QPlainTextEdit)`：只读、NoWrap、等宽(Consolas 10)、行号边栏（经典 recipe：`setViewportMargins` + `highlightCurrentLine` 关闭 + paintEvent 经 lineNumberAreaPaintEvent 绘 blockNumber）。
- `SourceViewerDialog(QDialog)`：
  - `set_source(text, name)`：仅当内容/标题变化时 setPlainText（复用窗口避免大日志重灌）。
  - `show_frame(hit, frame_no)`：黄底 extraSelection 覆盖整行范围 + `centerCursor`；状态行 QLabel「帧 #k → 第 a–b 行」或「未定位」。
  - 查找条（默认隐藏）：QLineEdit + 上一个/下一个 + 计数 + 区分大小写；`_do_search()` 用 `toPlainText().find` 收集全部命中（0-based 文档偏移，普通文本无需 hex 映射）→ 所有命中橙色 extraSelection，当前命中红底 + 光标定位 + 居中；回车/按钮循环取模；Esc 清搜索态（帧高亮两组 selections 合并管理：`_frame_sel`/`_search_sels`，`_apply_extras()` 统一 setExtraSelections）。
  - `keyPressEvent`：Ctrl+F 显示并聚焦查找条。
- 构建/弹出分离：dialog 由 MainWindow `_ensure_source_viewer()` 懒建（parent=win，Qt.Window 语义即非模态），测试可直接构造类实例断言结构。

## main_gui 接线

| 位置 | 改动 |
|---|---|
| `__init__` L1135 附近 | `_batch_snapshot_text=""` `_batch_snapshot_name=""` `_src_viewer=None` |
| `dropEvent` L956 后 | `mw._set_batch_snapshot(content, basename)`（hasattr 守卫） |
| `load_from_file` L7380 | 同上（对话框文件名 basename） |
| `paste_from_clipboard` L7393 | `_set_batch_snapshot(text, "剪贴板")` |
| `parse_batch` L7470 入口 | 快照空且 full_text 非空 → 以现框文为快照（手敲兜底） |
| `clear_batch` ~L9216 | 清快照两字段 + `_src_viewer=None`（关窗 deleteLater） |
| L2622 | `_setup_table_copy_menu(summary_table)` → `_setup_batch_summary_menu()` |
| 新方法区（Python 脚本预处理段后） | `_set_batch_snapshot` / `_setup_batch_summary_menu` / `_show_batch_summary_menu` / `_build_batch_summary_menu`（纯构建可测） / `_locate_frame_in_snapshot` / `_ensure_source_viewer` |

**不碰**：`_strip_csg_new_gen_frame_prefix`、`_clean_hex_input`、`_extract_frames_for_protocol`、解析循环体。

## 边界与失败模式

- 无快照（旧配置/未走入口且框空）→ 状态栏提示，不弹窗。
- 快照有、帧零命中（如帧由脚本合成/拼接）→ 弹窗照常打开显示全文 + 状态行「未能定位」。
- 查看器持快照引用不复制巨型副本：`set_source` 内容相同则跳过重灌（右键重复点击 O(1)）。
- Windows 换行：`splitlines` 处理 \r\n，文档偏移按 \n 计——`setPlainText` 会丢弃 \r（Qt 行为），行偏移以清洗后 `\n`-join 为准：`_set_batch_snapshot` 入口统一 `text.replace("\r\n","\n").replace("\r","\n")`。

## 测试（test/test_batch_snapshot_locate.py）

纯逻辑：单行命中/跨行命中/重发多命中/时间戳噪声不误拆/大小写/短帧拒绝。
offscreen：三入口建快照（dropEvent 直接调 `_set_batch_snapshot` 亦可）、parse_batch 兜底、CLI 回填不污染快照（模拟：设快照→回填→快照不变）、clear_batch 清理、右键菜单项集合、协议9真实两帧日志 parse_batch→右键定位→dialog extraSelections 行号断言、查找计数。
