# 设计：uTools 风格快捷解析小窗

## 架构与边界

新增 `system_integration/quick_parse_panel.py`，单一组件 `QuickParsePanel(QWidget)`：
- **面板组件保持「哑」**：不 import 任何 parser/validator，解析能力由 MainWindow 注入回调，避免 system_integration → 解析器的横向耦合（与现有 system_integration 模块一致，仅依赖 Qt + clipboard_monitor.detect_protocol）
- MainWindow 负责：懒创建面板、注入 3 个回调、热键路由

```
GlobalHotkeyManager._on_global_hotkey (main_gui)
   → QuickParsePanel.toggle_panel()
        show: 读剪贴板 → 合法 hex 则填入输入框（全选状态）→ 实时解析
              否则清空输入框等待输入
        hide: 已可见则隐藏（uTools 式切换）

输入框 textChanged → QTimer 300ms 防抖
   → _clean_hex（注入）→ detect_protocol(frame_bytes)
   → 协议下拉静默切换（不触发用户手动切换标记）
   → parse_fn(frame_bytes, idx) → (rows: list[tuple4]|None, err: str|None)
   → validate_fn(frame_bytes, idx) → (valid: bool|None, summary: str)  # None=不支持校验
   → 渲染：徽章 + 字段表 / 错误态 / 空态
```

## 面板结构（自上而下）

```
┌─ QuickParsePanel (Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint) ─┐
│  WA_TranslucentBackground + 内部圆角容器（QSS radius=12px + QGraphicsDropShadowEffect）│
│                                                                          │
│  [协议下拉 ▼] [帧长: N 字节]              [校验 ✓通过 12项] [✗失败]      │  ← 徽章行
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 粘贴或输入十六进制报文，自动识别协议…（QTextEdit, Consolas, NoWrap, │   │  ← 输入框
│  │  最大 2 行高 64px，横向滚动）                                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌─ 结果卡片（QScrollArea，最高屏幕 55%）────────────────────────────┐   │
│  │ ZoomableTableWidget 4 列（字段/原始值/解析值/说明），13px 紧凑行   │   │
│  │ 空态：「输入报文后实时显示解析结果」                                │   │
│  │ 错误态：红色错误文案（解析失败/非 hex/多帧提示）                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  [在主窗口打开完整视图]  [复制结果]              Esc 关闭 · 实时解析      │  ← 底部行
└──────────────────────────────────────────────────────────────────────────┘
```

- 固定宽 720px；高度按内容增长，结果区封顶屏幕可用高度 55% 后内部滚动
- 定位：屏幕可用区水平居中、顶部 12% 处（`availableGeometry` 计算，多屏用光标所在屏）

## 关键行为

1. **显示/隐藏切换**：`toggle_panel()`——可见则 hide；不可见则 show + raise_ + activate + 重新定位 + 读剪贴板。Esc 键（QShortcut/QKeyEvent）隐藏。失焦自动隐藏：`changeEvent(QEvent.ActivationChange)` 中 `not isActiveWindow()` → hide（点面板内部不失焦，点外部/切应用即关，uTools 行为）。
2. **剪贴板预填**：show 时读 `QGuiApplication.clipboard().text()`，经注入的 clean_fn 清洗；合法（偶数长度纯 hex 且 ≥4 字节）则填入并 `selectAll()`（打字即覆盖、可直接 Esc 关）；不合法则输入框留空 + placeholder。
3. **实时解析**：`textChanged` → 300ms `QTimer.singleShot` 防抖 → 清洗 → 识别 → 解析。协议下拉手动切换 → 立即用当前帧重解析（文本不变，重新自动识别只在文本变化时发生，手动选择不被覆盖）。
4. **协议识别**：`clipboard_monitor.detect_protocol` 返回 None 时下拉保持当前选择（默认 0），徽章区显示「未识别协议，请手动选择」。
5. **校验徽章**：`validate_fn` 返回 `(valid, summary)`；valid=True 绿色「✓ 校验通过」、False 红色「✗ 校验失败（鼠标悬停看 summary）」、None 灰色「—」。复用 `validator/*.verify(frame_bytes).valid/.summary()`。
6. **完整视图**：按钮调用注入 `open_full_fn(frame_bytes, idx)` → MainWindow 现有 `_parse_and_show_dialog(bytes, idx)`（960×640 大弹窗，含解析级别/ED 剥离），小窗保持打开还是关闭？——打开完整视图时**隐藏小窗**（焦点转移，避免窗口堆叠）。
7. **多帧/超长输入**：清洗后若包含多个完整帧特征（如出现 ≥2 个 `...16` 结束且协议为 0/6/7/8），卡片显示提示「检测到多帧，小窗仅解析第一帧；批量解析请用主窗口 批量解析 tab」+ 仍解析第一帧。实现：取第一帧用现有 `_extract_frames_for_protocol`？——该方法在 MainWindow 内，注入 parse_fn 时由 MainWindow 侧做「取首帧」，面板只展示返回的 rows + 可选 note。**简化**：MVP 不切帧，整包送 parser（解析器对尾部多余字节通常报错或忽略），错误态正常显示；多帧切帧列为第二期。→ 已在 PRD Out of Scope。
8. **主题**：面板在每次 show 时按 `QApplication.palette()` 明暗或注入 `is_dark()` 刷新圆角容器/徽章/表格配色（QSS 字符串）；应用级 QSS 自动作用于 Qt.Tool 窗口，按钮字体等继承，无需额外处理。

## 注入接口（MainWindow → 面板）

```python
QuickParsePanel(
    parent,
    clean_fn=lambda text: self._clean_hex_input(text),          # hex 清洗
    parse_fn=self._quick_panel_parse,     # (frame_bytes, idx) -> (rows|None, err|None, note|None)
    validate_fn=self._quick_panel_validate,  # (frame_bytes, idx) -> (valid|None, summary)
    open_full_fn=self._quick_panel_open_full,  # (frame_bytes, idx) -> None
    is_dark_fn=lambda: self._is_dark_theme(),
)
```

- `_quick_panel_parse`：镜像 `_parse_and_show_dialog.do_parse` 核心——9/10 走 `parse_level="auto"` + ED 头剥离（`_parse_ed_monitor_header`，失败返回错误文案）；其余协议直接 `_get_current_parser(idx).parse_to_table(bytes)`；返回 `(rows, err, note)`
- `_quick_panel_validate`：懒构建 validator 实例 dict（同 `_run_validation` L4316-4335 的映射），`verify(frame_bytes)` → `(result.valid, result.summary())`，不支持协议返回 `(None, "")`
- `_quick_panel_open_full`：调 `_parse_and_show_dialog(frame_bytes, idx)` 并 `self.panel.hide()`

## 热键与设置

- `main_gui._on_global_hotkey`：从「读剪贴板→大弹窗」改为 `self._quick_panel.toggle_panel()`（面板懒创建，首次热键时实例化）
- `_parse_and_show_dialog` 保留：命令行 `--parse/--file/--clipboard`、文件右键、Notepad++ 集成、面板「完整视图」按钮仍用它
- `system_integration/system_settings.py` L116 提示文案改为「复制报文后按热键唤出快捷解析小窗，输入即解析」
- `南网协议解析工具.spec` hiddenimports 增加 `system_integration.quick_parse_panel`

## 兼容性与风险

- 全局热键仅 Windows（现状不变）；面板组件本身跨平台
- Qt.Tool 窗口无任务栏图标、随父窗口销毁；WA_DeleteOnClose 不设（面板复用，toggle 显隐）
- 解析在主线程同步执行：单帧 parse_to_table 实测 <50ms，300ms 防抖下不卡输入；超大帧（数千字节）可能短暂卡顿——MVP 接受，后续可移线程
- 圆角+阴影：WA_TranslucentBackground 下容器自绘背景色；暗色主题单独配色
- 剪贴板预填沿用现有严格 hex 校验逻辑，不会把普通文本当报文
