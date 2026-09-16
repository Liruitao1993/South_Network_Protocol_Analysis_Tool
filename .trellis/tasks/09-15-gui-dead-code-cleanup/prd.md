# GUI 死代码清理（重复方法 / 零引用方法 / 根目录临时脚本）

## Goal

清掉 `main_gui.py` 与仓库根目录已确认无用的代码：**5 组重复定义的方法**（后定义静默覆盖前者，改前一份毫无效果——真实维护陷阱）、**7 个全仓库零引用的方法**、**13 个根目录 `_*.py` 临时脚本**。

不改任何行为。

## Confirmed Facts（AST + 全仓库 grep 证据，2026-09-15）

### A. MainWindow 内重复方法（AST 扫描：246 个定义 / 241 个唯一名）

Python 后定义覆盖先定义 → **前者是死代码**：

| 方法 | 死版本（首个定义） | 生效版本（末个定义） | 两份是否相同 |
| --- | --- | --- | --- |
| `_refresh_serial_ports` | `main_gui.py:2858-2868` | `main_gui.py:10764-10777` | 否（生效版多 `_save_serial_config` / 状态栏样式） |
| `_on_serial_open_clicked` | `main_gui.py:2870-2894` | `main_gui.py:10779-10811` | 否（生效版保留当前端口文本 + 存配置） |
| `_on_serial_connection_changed` | `main_gui.py:2896-2910` | `main_gui.py:10813-10823` | 否 |
| `_on_serial_error` | `main_gui.py:2912-2914` | `main_gui.py:10825-10828` | 否（死版用 `QMessageBox.warning`，生效版改状态栏） |
| `_clear_layout` | `main_gui.py:5729-5736` | `main_gui.py:7262-7269` | **是（逐行相同）** |

说明：调用点 `main_gui.py:1644/1700` 连的是生效版本（末个定义），故删除首个定义是严格无行为变更。

### B. 全仓库零引用的方法（grep `\bname\b` 仅命中定义行）

| 位置 | 符号 | 备注 |
| --- | --- | --- |
| `main_gui.py:934` | `_get_git_changelog`（模块级函数） | CHANGELOG 现为手写列表，未接线 |
| `main_gui.py:2196` | `create_di_lookup_tab` | 另见 `lookup_pages.create_di_lookup_page`（`AGENTS.md` 记「当前无调用方」） |
| `main_gui.py:4680` | `load_example` | |
| `main_gui.py:5696` | `export_single` | 单帧导出实际走别的入口 |
| `main_gui.py:7657` | `_extract_direction_from_table` | |
| `main_gui.py:9712` | `show_detail_dialog` | |
| `main_gui.py:10756` | `_show_llm_api_manager` | |

已排除的唯一动态派发通道：`protocol_registry.lookup_builder_method`（`protocol_registry.py:482`）只返回 9 个 `_create_*_lookup_content` 名字，**不包含上表任何一项**；`getattr(self, "...")` 的其余用法全部是读属性而非取方法。

### C. 根目录临时脚本（13 个 `_*.py`，全仓库 0 引用）

- docx→md 一次性转换：`_convert_doc_to_docx.py`、`_convert_gw_all_docs.py`、`_convert_gw_doc.py`、`_convert_gw_new_gen_docs.py`、`_convert_remaining_doc.py`、`_convert_single.py`、`_run_convert.py`（已被仓库既有 `convert_docx_to_md.py` 取代）
- 文档表格抽取：`_dump_gw_mac_tables.py`
- 环境诊断：`_diag.py`
- 幽灵窗口复现：`_tmp_ghost_repro.py`、`_tmp_ghost2.py`（2026-09-01）
- **孤儿代码片段**：`_generated_mapping.py`、`_generated_mapping_v2.py` —— 二者 **`ast.parse` 报 `SyntaxError: unexpected indent`（第 1 行）**，即「粘贴进来的方法体」，不可 import；其中 `_generated_mapping_v2.py` 的 `_get_f0_32_entry_name` 映射键值（如 `(0, 0) → "本分类ID所有数据ID"`）在当前仓库其它地方**已无对应实现**（`git log -S "本分类ID所有数据ID"` 显示历史上曾在 `e21b38e` / `fd1feed` 出现）

## Requirements

- **R1** 删除 A 表 5 个死版本方法；删前逐对 diff，若发现生效版**缺失**死版行为（尤其 `_on_serial_error` 的提示方式）先合并行为再删。
- **R2** 删除 B 表 7 个零引用方法；删前用 `grep -rn` 二次确认（含 `test/`、`reflex_web/`、`*.json` 配置、`.spec`）。
- **R3** 删除 C 表 13 个根目录脚本；`_generated_mapping*.py` 需先确认其映射数据是否仍需保留（若需，先并入解析器或转为正式数据文件，再删脚本）。
- **R4** 不新增/修改 `.gitignore` 以掩盖问题（保持「设计上有用的脚本放 `scripts/` 并在 `AGENTS.md` 登记」的现有约定）。
- **R5** 每删除一组，跑一次冒烟（`python main_gui.py` 无法在 CI 跑时用 offscreen 构造 `MainWindow` + 串口标签页交互）确认无 `AttributeError`。

## Acceptance Criteria

- [ ] `grep -rn "def _refresh_serial_ports\|def _on_serial_open_clicked\|def _on_serial_connection_changed\|def _on_serial_error\|def _clear_layout" main_gui.py` 各只命中 1 处。
- [ ] AST 复扫 `MainWindow`：定义数 == 唯一名数（246 → 241 以下，且无重复名）。
- [ ] 上表 7 个符号在仓库中 0 命中。
- [ ] 根目录无 `_*.py`（`ls _*.py` 报 not found）。
- [ ] 串口打开/关闭/错误提示、协议切换、查询页切换、批量清空（`_clear_layout` 调用方）手测行为与改动前一致。
- [ ] `python release_check.py` 无 FAIL / WARN；`test/test_nanwang_custom_di.py`、`test/test_app_exit.py` 等 offscreen GUI 回归全过。
- [ ] `main_gui.py:CHANGELOG` 增条目（净删除行数入账）。

## Out of Scope

- 不做 `main_gui.py` 的 Tab 拆分 / 文件切分重构。
- 不清理 `except Exception: pass` 的异常吞噬（15 处）——属行为变更，另开。
- 不动 `test/` 下历史遗留的调试脚本（`test_mac_*.py` 等，`AGENTS.md` 已登记为可清理项，但归测试目录治理）。
- 不修 `protocol_registry` 之外仍存在的 36 处 `current_protocol ==` 硬编码分支。

## Open Questions

- 无阻塞项。`_generated_mapping*.py` 的数据是否需保留，实现时用 `git log -S` 与解析器现状对照后按 R3 处理即可。
