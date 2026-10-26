# 树/表行内复选框不可见（item view indicator 无可见边框）

## Goal

现场反馈：协议测试页左侧命令树里「有好多的复选框，看不太清楚，可能是复选框的全局配置，边框没有颜色」。

实测确认（真实平台渲染取像素，default 主题）：**未勾选**的行内复选框是**白底 + 白框**（整块全白，
与行底色 `#ffffff` 无差别）；dark 主题下也只有勾选时才看得见勾。原因：
主题 QSS 只写了 `QCheckBox::indicator`（按钮式复选框），**管不到 `QTreeView / QTableView / QListView`
行内的 item indicator**；未写规则时 Qt 用调色板绘制，而本项目的 QSS 把 `background-color` 映射到
调色板角色后，未选指示器的边框颜色与行底色相同。

本任务给 4 套 QSS 主题补行内指示器规则，并用**渲染级**回归钉住（静态字符串断言挡不住「白底白框」）。

## 现状证据

- `theme_settings.py` 的 4 套 QSS：`LIGHT_QSS`（default）、`DARK_QSS`（dark）、`GLASS_QSS`（glass）、
  `MICA_QSS`（mica）各自都有 `QCheckBox::indicator` 三条（默认/勾选/部分勾选），但**没有任何**
  `QTreeView::indicator` / `QAbstractItemView::indicator` 规则。
- 实测（真实平台，非 offscreen）：

  | 主题 | 未勾选行内指示器 | 行底色 |
  |---|---|---|
  | default | 全 `#ffffff`（框不可见） | `#ffffff` |
  | dark | 仅 `#4a4a4a` 分支线，框内无边框色 | `#2b2b2b` |

- `QAbstractItemView::indicator` 选择器实测可命中树/表/列表行内指示器（把测试 QSS 换成
  绿底红框后，像素里出现 `#00ff00`/`#ff0000` 家族）；`QTreeView::indicator` 同样生效。
- 已有相关回归：`test/test_theme_settings.py` 的 1c 节（QListWidget 交替行可读性）证明
  「渲染取像素 + 对比度」是本仓认可的做法；但**没有**覆盖行内复选框。

## Requirements

### R1 QSS（4 套主题各一份，禁止只改 default）

每套在 `QCheckBox::indicator:indeterminate` 之后追加：

```css
/* 列表/表格/树 的行内复选框（item view indicator）：QCheckBox::indicator 管不到它们，
   未写规则时边框与行底色同色（default 白底白框）⇒ 现场「复选框看不清楚」。 */
QAbstractItemView::indicator { width:14px; height:14px; border:1px solid <边框>; border-radius:2px; background-color:<底>; }
QAbstractItemView::indicator:checked { background-color:<强调>; border:1px solid <深化边框>; }
QAbstractItemView::indicator:indeterminate { background-color:<浅强调>; border:1px solid <深化边框>; }
```

配色（与各主题既有 QCheckBox 同口径、保证与行底色对比度 ≥ 3:1）：

| 主题 | 未选边框 | 未选底 | 已选底 | 已选边框 | 部分选底 |
|---|---|---|---|---|---|
| default | `#4b5563` | `#ffffff` | `#2196F3` | `#0D47A1` | `#90CAF9` |
| dark | `#9aa0a6` | `#2d2d2d` | `#42a5f5` | `#c7d2fe` | `#555555` |
| glass | `#64748b` | `rgba(255,255,255,220)` | `rgba(59,130,246,220)` | `#2563eb` | `rgba(147,197,253,220)` |
| mica | `#8a8a8a` | `#fdfdfd` | `#005fb8` | `#005fb8` | `#84beef` |

原生主题（fusion / windows / windowsvista 的纯原生部分）不写 QSS —— 由系统绘制，保持不变。

### R2 回归测试（`test/test_theme_settings.py` 新增 1d 节）

1. **静态守卫**：4 套 QSS 都必须含 `QAbstractItemView::indicator`，且该块含 `border:` /
   `background-color:` / `:checked` / `:indeterminate`（防止只补一半）；
2. **渲染级（核心）**：对 default/dark/glass/mica 逐个 `ThemeManager.apply` 后，建一个
   `QTreeWidget` + 一个可勾选且未勾选的 item，`grab()` 取图，在
   `visualItemRect` 的左侧 24px 内（**排除**分支箭头区）统计「与行底色 WCAG 对比度 ≥ 3 的像素数」，
   断言 ≥ 20（14px 方框的边框有 40+ 像素；修复前 default 为 0）；
3. 勾选态与未勾选态**像素集合必须不同**（防止 checked 规则漏写导致看不出是否勾选）；
4. 反例自检：把该主题 QSS 临时去掉 indicator 块后再渲染，断言第 2 条判据会失败
   （证明测试能抓住回退，而不是恒真）。

### R3 验证与文档

- `test/test_theme_settings.py` 全绿（既有 73 项 + 新增）；
- 真实平台（非 offscreen）在 645 协议测试页命令树与 626 页表上看一眼：未勾选框有清晰灰框；
- AGENTS §8 新增一条陷阱：**QSS 的行内复选框要用 `QAbstractItemView::indicator`**（`QCheckBox::indicator`
  管不到），并说明「白底白框」的成因与回归位置；
- `main_gui.py:CHANGELOG`（1.24.1 续）记一条。

## Acceptance Criteria

- A1 default 主题下，645/698 协议测试页命令树里未勾选的复选框**能看见方框**（灰框 + 白底），
  勾选后为蓝底；dark 主题同样可辨。
- A2 `QTableWidget` 行内复选框（如串口工具命令表、归档页）同样有可见边框，且不影响单元格文字。
- A3 `test_theme_settings.py` 新增断言在「去掉 indicator 块」的变异下变红，恢复后全绿。
- A4 `python release_check.py --with-gui` → FAIL=0（既有环境红除外）。

## 非目标

- 不改 `QCheckBox` / `QRadioButton` 既有样式与尺寸；
- 不引入图标资源（纯 QSS 边框/底色）；
- 不做「hover / focus」等新状态样式（保持最小改动）；
- 不改 18 个既有主题 id 与调色板逻辑。
