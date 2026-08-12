# 设计：校验结果展开/收缩 + 结果表全屏/恢复

全部改动在 `main_gui.py`。锚点：`create_single_parse_tab`（L849-987，校验结果 L976-983、导出按钮行 L961-972）；批量解析页（L1478-1603，summary_group/detail_group 挂于 `self.result_splitter`）。

## 1. 通用辅助方法 `_make_fullscreen_controls`

```python
def _make_fullscreen_controls(self, hide_widgets: list) -> QHBoxLayout:
    """构建右对齐「全屏/恢复」按钮对。
    全屏: 隐藏 hide_widgets 中的兄弟控件，让所在表格撑满窗口
    恢复: 重新显示
    返回按钮行布局，调用方 addLayout 到表格所在布局。
    """
    row = QHBoxLayout()
    row.setSpacing(6)
    row.addStretch()
    fs_btn = QPushButton("全屏")
    rs_btn = QPushButton("恢复")
    for b in (fs_btn, rs_btn):
        b.setFixedHeight(26)
        b.setFont(self._ui_font(-1))
    rs_btn.setEnabled(False)

    def _fs():
        for w in hide_widgets:
            w.hide()
        fs_btn.setEnabled(False)
        rs_btn.setEnabled(True)

    def _rs():
        for w in hide_widgets:
            w.show()
        fs_btn.setEnabled(True)
        rs_btn.setEnabled(False)

    fs_btn.clicked.connect(_fs)
    rs_btn.clicked.connect(_rs)
    row.addWidget(fs_btn)
    row.addWidget(rs_btn)
    return row
```

## 2. 单帧解析页

### 2a. 校验结果 展开/收缩（替换 L976-983 区块）

```python
self.verify_group = QGroupBox("校验结果")
verify_layout = QVBoxLayout(self.verify_group)
verify_layout.setContentsMargins(8, 8, 8, 8)
verify_layout.setSpacing(4)

verify_head = QHBoxLayout()
verify_head.addStretch()
self.verify_expand_btn = QPushButton("展开")
self.verify_collapse_btn = QPushButton("收缩")
for b in (self.verify_expand_btn, self.verify_collapse_btn):
    b.setFixedHeight(24)
    b.setFont(self._ui_font(-1))
self.verify_expand_btn.setEnabled(False)   # 默认展开
self.verify_expand_btn.clicked.connect(self._on_verify_expand)
self.verify_collapse_btn.clicked.connect(self._on_verify_collapse)
verify_head.addWidget(self.verify_expand_btn)
verify_head.addWidget(self.verify_collapse_btn)
verify_layout.addLayout(verify_head)

self.verify_scroll = QScrollArea()
self.verify_scroll.setWidgetResizable(True)
self.verify_scroll.setFrameShape(QFrame.Shape.NoFrame)
self.verify_label = QLabel("点击「校验报文」按钮进行协议一致性校验")
self.verify_label.setWordWrap(True)
self.verify_label.setFont(self._ui_font(-1, family="Consolas"))
self.verify_scroll.setWidget(self.verify_label)
verify_layout.addWidget(self.verify_scroll, 1)
result_layout.addWidget(self.verify_group)
```

新增方法：

```python
def _on_verify_expand(self):
    self.verify_scroll.show()
    self.verify_group.setMaximumHeight(16777215)
    self.verify_expand_btn.setEnabled(False)
    self.verify_collapse_btn.setEnabled(True)

def _on_verify_collapse(self):
    self.verify_scroll.hide()
    head_h = self.verify_collapse_btn.sizeHint().height() + 8
    self.verify_group.setMaximumHeight(head_h + 26)  # 26 = QGroupBox 标题区+边距
    self.verify_expand_btn.setEnabled(True)
    self.verify_collapse_btn.setEnabled(False)
```

### 2b. 解析结果表 全屏/恢复（导出按钮行 L970 后追加）

```python
full_row = self._make_fullscreen_controls([input_group, self.verify_group])
export_row.addLayout(full_row)   # export_row 已有 addStretch
```

注意 `input_group` 在 L860-924 为局部变量，同方法内可引用。

## 3. 批量解析页

- `summary_group`（含 `batch_summary_table`）：在 `summary_layout` 中 `batch_summary_table` 之后（L1550 后）追加按钮行：`self._make_fullscreen_controls([self.result_splitter.widget(1)])`
- `detail_group`（含 `batch_detail_table`）：在 `detail_layout` 中 `batch_detail_table` 之后（L1601 后）追加：`self._make_fullscreen_controls([self.result_splitter.widget(0), self.batch_detail_hex])`

按钮行与表格同组，全屏时隐藏对侧组即可撑满。

## 兼容性 / 风险

- `_display_verify_result` 只改 `verify_label.setText` 与 `verify_group.setStyleSheet`，标签移入滚动区后行为不变。
- `clear_single` L3776 重置 `verify_label` 文本，不受影响。
- 收缩高度常数（+26）依赖 Qt 样式：QGroupBox 标题区高度约 20-26px；若主题变化导致按钮被裁，`_on_verify_collapse` 可再调大。offscreen 验证按钮可点击。
- 全屏仅隐藏兄弟控件，不销毁；splitter 布局自动重排。

## 回滚

改动只在 `main_gui.py`；先 `git stash`（该文件有其它未提交改动）再 `git checkout -- main_gui.py`。