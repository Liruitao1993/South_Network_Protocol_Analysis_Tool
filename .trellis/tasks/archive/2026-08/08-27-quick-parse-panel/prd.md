# uTools 风格快捷解析小窗（热键唤出输入框 + 结果卡片）

## Goal

仿 uTools 快捷面板：按全局热键（现 Ctrl+Alt+X）→ 屏幕上方居中弹出无边框置顶小窗（圆角卡片式输入框）→ 粘贴/输入报文 hex → 输入框**下方实时弹出结果卡片**显示完整解析；Esc / 再按热键 / 点击外部关闭。无需打开主窗口即可完成「看一眼报文」的高频操作。

## Background (confirmed facts)

uTools 交互模式（u-tools.cn / 知乎介绍）：全局热键唤出无边框圆角悬浮面板（水平居中靠上、置顶、无任务栏图标、带投影）；单输入行；结果卡片随输入实时出现在输入框下方；Esc/再按热键/点外部关闭。

可复用现有设施（不改解析器）：
- `system_integration/global_hotkey.py`：`GlobalHotkeyManager`（RegisterHotKey + 回调），热键可配置，默认 `Ctrl+Alt+X`；`main_gui._on_global_hotkey`（L5396）现为「读剪贴板 → 大弹窗」
- `main_gui._parse_and_show_dialog`（L5415-5627）：解析渲染管线参考——`_get_current_parser(idx, **kwargs).parse_to_table(bytes)` → 4 元组行 `(字段, 原始值, 解析值, 说明)`；9/10 协议有 parse_level/frame_type/ED 剥离
- `clipboard_monitor.detect_protocol(frame) -> int|None`（L27）：ED→9、DLT645→6、68..16→0、7E→2
- validator：`validator/*.verify(frame_bytes) -> ValidationResult`，`.valid` / `.summary()`；注册映射见 main_gui L4316-4335
- `MainWindow._clean_hex_input`、`_parse_ed_monitor_header`；系统设置面板已有 hotkey/hotkey_enabled；spec hiddenimports 逐模块列出 system_integration.*

## Requirements

1. **新组件** `system_integration/quick_parse_panel.py`：`QuickParsePanel(QWidget)`，`Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint` + `WA_TranslucentBackground`，圆角容器 + 投影；宽 720px 固定，水平居中、屏幕顶部 12%；结果区最高屏幕 55% 后内部滚动
2. **面板结构**：徽章行（协议下拉[12 项，自动识别可手动切换] + 帧长 + 校验✓/✗徽章）→ 输入框（Consolas、不自动折行、≤2 行高）→ 结果卡片（ZoomableTableWidget 4 列紧凑字段树，复用 parse_to_table 全量行）→ 底部（「在主窗口打开完整视图」「复制结果」+ 快捷键提示）
3. **实时解析**：textChanged 防抖 300ms → 清洗 → detect_protocol 自动选协议 → 解析 → 渲染；空态/错误态（非 hex、解析失败、未识别协议）有明确提示，不崩
4. **入口行为（已确认）**：复用 `Ctrl+Alt+X`——热键改为唤出小窗；唤出时剪贴板含合法 hex（≥4 字节偶数长度）则自动填入并解析（输入全选，打字即覆盖），否则空白等待；热键再次按下/ Esc / 面板失焦（点外部/切应用）→ 隐藏
5. **校验徽章**：调 validator，valid=True 绿「✓ 校验通过」、False 红「✗ 校验失败」（tooltip 显示 summary）、不支持校验灰色「—」
6. **完整视图**：卡片按钮 → 现有 `_parse_and_show_dialog(bytes, idx)` 大弹窗（含解析级别/ED 剥离），小窗随之隐藏；命令行/右键/Notepad++ 的大弹窗路径不变
7. **面板哑组件**：不 import parser/validator；clean/parse/validate/open_full/is_dark/协议列表全部由 MainWindow 注入回调
8. **主题**：每次显示时按明暗主题刷新圆角容器/徽章/输入框配色；应用级 QSS 自动继承
9. **设置文案**：system_settings 热键提示改为「复制报文后按热键唤出快捷解析小窗，输入即解析」
10. **打包**：spec hiddenimports 增加 `system_integration.quick_parse_panel`

## Acceptance Criteria

- [ ] 按 Ctrl+Alt+X 弹出置顶无边框圆角小窗，居中靠上、带阴影、无任务栏图标
- [ ] 剪贴板有合法报文 hex 时唤出即自动填入并显示完整解析结果；无则空白显示占位提示
- [ ] 在输入框粘贴/输入报文，300ms 内自动解析：协议下拉自动识别切换、帧长正确、字段树填充；手动切换协议下拉后按所选协议重解析
- [ ] 校验徽章：合法帧显示绿色通过；非法帧红色失败（tooltip 有详情）；不支持校验协议灰色
- [ ] Esc / 再按热键 / 点击面板外部 → 小窗隐藏；再次热键唤出
- [ ] 「完整视图」打开现有大解析弹窗（协议一致）且小窗隐藏；「复制结果」可粘贴
- [ ] 非 hex 文本 / 截断帧 / 解析异常：卡片显示红色错误提示，不抛异常不白屏
- [ ] 暗色主题下卡片配色可读
- [ ] `test/test_quick_parse_panel.py` 通过（offscreen：空态/真实帧解析/自动识别/错误态/徽章/显隐切换/协议切换/完整视图回调）
- [ ] 版本 bump 1.17.0，CHANGELOG + AGENTS.md（§3 架构、§10 日志）同步

## Out of Scope

- 多帧粘贴切分（MVP 整包送解析器；批量多帧用主窗口批量解析 tab）——第二期
- 9/10 协议的解析级别/帧类型/ED 剥离手动控件（小窗固定 auto + ED 自动剥离；高级选项在「完整视图」大弹窗）
- 命令行 --clipboard / 文件右键路径改道小窗（保持大弹窗不变）
- 剪贴板自动检测弹窗（复制即弹）行为不变
- 解析移后台线程（单帧 <50ms，防抖足够；超大帧卡顿第二期优化）
- Reflex Web 版

## Open Questions

- 无（入口行为、卡片内容均已经用户确认；实时解析为既定设计）
