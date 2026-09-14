# 实施计划：频谱图绘制

前置：`prd.md`（需求/验收）、`design.md`（契约/公式/接线段）。**按步骤顺序执行，每步自带验收命令**；不在中途跑全量 `release_check`（末步统一跑）。

环境：命令在项目根执行；中文输出设 `PYTHONIOENCODING=utf-8`。

---

## 步骤 1 — `spectrum_widget.py` 纯逻辑层（无 Qt）

新增 `spectrum_widget.py`，文件前 1/3 只写纯逻辑层（**不得出现 `PySide6` import**），Qt import 放到后半并用 `try/except ImportError` 包住（保证无 Qt 环境可导入纯逻辑层，同 `sequence_diagram_widget.py` 结构）。

实现 `design.md` §3 全部符号：`SpectrumInputError`、`SpectrumParams`、`SpectrumTrace`、`parse_levels`、`build_trace`、`freqs_for`、`display_levels`、`y_range`、`y_ticks`、`x_tick_labels`、`format_hz`、`format_level`、`count_out_of_range`，以及常量 `UNIT_*` / `DETECTORS` / `HZ_UNITS` / `SEPARATORS` / `UNIT_OFFSET_FROM_DBM`。

要点：
- 分隔符替换 + 逐 token `float()`；失败立刻抛 `SpectrumInputError(f"第 {i} 项不是有效数值：{token}")`（1-based，**不静默丢弃**）。
- 拒绝 `nan`/`inf`（`math.isfinite`）。
- 参数校验严格按 `design.md` §3.2 错误矩阵，消息面向用户。
- 数值超出纵轴范围时**不抛错**：进 `warnings`，绘制侧裁剪（AGENTS.md §8 陷阱 23 口径：有内容 + 明确提示，不返空）。

**验收**：`python -c "import spectrum_widget as s; t=s.build_trace('1 2 3', s.SpectrumParams(240e6, 960e6)); print(len(t.freqs), t.freqs[0], t.freqs[-1])"` → `3 240000000.0 960000000.0`

---

## 步骤 2 — `test/test_spectrum_model.py`（纯逻辑回归）

脚本式 `check()` 断言（参照 `test/test_csg_sequence_model.py` 风格；文件头 `import _path_setup  # noqa: E402`）。覆盖 `design.md` §6 第 1~7 组的每一条，特别是：
- 中文全角分隔符（`，`/`、`）与混排分隔；
- 错误矩阵逐行 `raises`（含消息关键字）；
- `freqs_for` 端点精确性与 `step_hz`；
- 仪器式 `y_ticks` 首值 == 参考电平、步长 == 每格 dB；
- 自动模式 5% 边距 + `max == min` 退化不除零；
- `dBμV` +107 / `dBmV` +47。

**验收**：`python test/test_spectrum_model.py` → 全部 PASS，退出码 0。

---

## 步骤 3 — Qt 层（`SpectrumCanvas` + `SpectrumWidget`）

- `SpectrumCanvas(QWidget)`：`paintEvent` 全量绘制 —— 绘图区背景/网格（10 横格 × `y_divs` 纵格）/边框/标题带（标题 + 参数注记）/X 轴刻度标签（含单位）/Y 轴刻度标签；迹线 `QPolygonF` 折线（N ≤ 201 加数据点标记）；超范围点在状态行提示。`render_image(w,h)` 用 `QImage` + `QPainter` 复用同一绘制函数（导出与测试共用，**不复制第二份绘制逻辑**）。
- `SpectrumWidget(QWidget)`：`QSplitter`（左参数表单 / 右「画布 + trace 输入」）；工具栏按钮 `绘制` / `粘贴` / `清空` / `导出 PNG`，复选框 `纵轴自动适配`；参数派生显示（中心频率/扫宽/频率步进）随输入实时刷新；状态行显示 `点数 / 频率步进 / span / RBW`，错误以 `warn` 色显示（不弹模态框，避免打断批量操作）。
- 主题：`restyle_for_theme(dark)` 切 `_palette` 后 `update()`；创建时按当前主题初始化。
- **不落盘任何配置**（本功能无持久化）：因此测试不需要 `app_paths.data_path` 沙箱（若后续加参数持久化，必须按 `AGENTS.md` 记忆教训补沙箱）。

**验收**：`QT_QPA_PLATFORM=offscreen python -c "..."` 生成一张 1600×1000 PNG 并**用 `read` 工具目视核对**（标题/注记/网格/刻度/迹线齐全、无文字重叠）。

---

## 步骤 4 — `main_gui.py` 接线（3 处，`design.md` §5）

① `from spectrum_widget import SpectrumWidget`；②「报文工具」tab（`main_gui.py:1692`）之后创建常驻 tab（图标 `chart-spline`，索引存 `self._spectrum_tab_index`）；③ `_restyle_for_theme`（`10548` 区）追加 `restyle_for_theme` 调用。

**禁止**：硬编码 tab 索引；改 `_on_protocol_changed`/`protocol_registry`（频谱图与协议无关，常驻）。

**验收**：`QT_QPA_PLATFORM=offscreen python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; import main_gui; from PySide6.QtWidgets import QApplication; a=QApplication([]); w=main_gui.MainWindow(); print(w.tab_widget.tabText(w._spectrum_tab_index))"` → `频谱图`

---

## 步骤 5 — `test/test_spectrum_gui.py`（offscreen 集成）

覆盖 `design.md` §6 GUI 组 1~8（tab 常驻可见 / 控件齐全 / 粘贴→绘制点数 / 非法输入不崩 / 自动适配切换 / `render_image` 双主题尺寸与非纯色 / 导出 PNG 可读回 / 主题切换调色板变化）。导出用例写 `tempfile` 目录并在 `finally` 清理。

**验收**：`PYTHONIOENCODING=utf-8 python test/test_spectrum_gui.py` → 全部 PASS。注意本机 `MainWindow` 退出期既有 fastfail（退出码可能非 0，与断言无关），以断言计数为准。

---

## 步骤 6 — 发布门槛

`release_check.py`：`CORE_TESTS` 追加 `test/test_spectrum_model.py`；`GUI_TESTS` 追加 `test/test_spectrum_gui.py`。

**验收**：`python release_check.py` → 无 FAIL（基线 PASS=48 FAIL=0 WARN=0，本次应增加新条目）。

---

## 步骤 7 — 文档与版本

- `main_gui.py`：`APP_VERSION` → `1.23.9`；`CHANGELOG` 头部新增 1.23.9 条目（功能点、自绘零依赖、新增测试）。
- `AGENTS.md`：§3 文件树加 `spectrum_widget.py`（GUI 组件段）；§7 测试清单加两个新测试；§10 摘要加 1.23.9。
- `README.md`：功能列表加「频谱图」。
- `BUILD_DATE` **不改**（本任务不打包；打包时按既有规则更新）。

**验收**：`python release_check.py` 仍无 FAIL（徽章/版本一致性由该脚本检查）。

---

## 步骤 8 — 端到端人工核验

用主窗口真实链路（offscreen 或用户本机 GUI）：填 起始 240 MHz / 终止 960 MHz / RBW 100 kHz / 参考 −20 dB / 每格 10 dB / 8 格 → 粘贴 100 点 → 目视核对 `prd.md` 验收 1~7；导出 PNG 后 `read` 目视。

---

## 完成定义（DoD）

`prd.md` 验收 1~8 全部满足 + 步骤 1~8 的验收命令均通过 + `release_check.py` 无 FAIL。
