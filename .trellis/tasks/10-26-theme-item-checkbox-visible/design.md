# 设计：行内复选框可见性

> PRD 见 `prd.md`。核心：**`QCheckBox::indicator` 不覆盖 item view 的行内指示器**，
> 需要 `QAbstractItemView::indicator`；判据必须是**渲染后像素对比度**，字符串断言挡不住白底白框。

## 1. 改动点

| 文件 | 改动 |
|---|---|
| `theme_settings.py` | 4 套 QSS 各追加 `QAbstractItemView::indicator` 三态规则（值见 PRD 表） |
| `test/test_theme_settings.py` | 新增 1d 节：静态守卫 + 渲染对比度 + 勾选/未勾选可区分 + 变异自检 |
| `AGENTS.md` | §8 陷阱 93（`QCheckBox::indicator` 管不到行内复选框） |
| `main_gui.py` | CHANGELOG（1.24.1 续）一条 |

不改：`ThemeManager.apply` 的调色板逻辑、`QCheckBox` 规则、原生主题（qss=None）。

## 2. 为什么选 `QAbstractItemView::indicator`

- 一份选择器同时覆盖 `QTreeView/QTreeWidget`、`QTableView/QTableWidget`、`QListView/QListWidget`；
- 实测命中（运行时注入测试 QSS：绿底红框 → 树内未勾选指示器像素出现 `#00ff00`）；
- 比逐个写 `QTreeView::indicator` 少漂移；后续新增只读表也能自动跟随。

## 3. 配色与对比度

- `default`：框 `#4b5563` 与行底 `#ffffff` 对比度 ≈ 7.5:1；
- `dark`：框 `#9aa0a6` 与 `#2b2b2b` ≈ 5.4:1；
- `glass`：`#64748b` 与半透明白 ≈ 5:1；`mica`：`#8a8a8a` 与 `#fdfdfd` ≈ 3.2:1（满足 3:1 非文本要求）。
- 已勾选保持高饱和底（蓝），保证「有没有勾」一眼可辨；部分勾选用浅强调色。

## 4. 测试实现要点

```python
# 渲染：offscreen 也能取像素（本测试原本就 offscreen）
tree = QTreeWidget(); item = QTreeWidgetItem(["x"]); item.setFlags(...|UserCheckable)
item.setCheckState(0, Qt.Unchecked)
app.setStyleSheet(theme_qss)          # 直接用 THEMES 里对应主题的 qss + 按钮 QSS（与 apply 同源）
tree.grab() → QImage
rect = tree.visualItemRect(item)
bg = 取 rect 右侧远端的多数色（行底色）
区域 = rect.left() .. rect.left()+24  （分支箭头在 rect 左侧之外，天然排除）
判定：该区域内「与 bg 的 WCAG 对比度 ≥ 3」的像素数 ≥ 20
```

- **不调 `ThemeManager.apply` 走完整主题**（会改全局调色板、show 窗口），而是与 `apply` 相同的
  QSS + `QStyleFactory.create("Fusion")` 组合，保持测试确定性；断言用的 QSS 从 `THEMES` 取，
  防止测试自造一份与产品不同源的样式。
- 反例自检：从 QSS 字符串里删掉 `QAbstractItemView::indicator {...}` 块（正则）后重新渲染，
  断言像素数断言**失败**，再恢复 —— 证明判据不是恒真。
- 勾选/未勾选可区分：同一区域像素颜色集合不同，且勾选态中心像素与行底色对比度 ≥ 3。

## 5. 风险

- QSS 里给 indicator 设 `width/height` 会改变行内缩进：14px 与原生（≈13~16px）接近，逐页核对首页表/树。
- `QListView`（QCompleter 补全弹层）里的非勾选条目不受影响（只有 checkable item 才画指示器）。
- 原生主题不写 QSS，行为不变（既有断言「原生主题 qss is None」仍成立）。
