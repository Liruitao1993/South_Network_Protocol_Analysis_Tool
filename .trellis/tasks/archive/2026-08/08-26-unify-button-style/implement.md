# 执行记录：统一全应用按钮风格

## 方案

- 全局 QSS（theme_settings.build_button_qss）统一形状：圆角 4px、padding 4px 12px、bold、无边框；
  动态属性 `btnKind` 区分 primary/success/danger/warning/accent/secondary/ghost，每色 normal/hover/pressed/disabled 四态；
  `btnSize` 分 sm(22)/默认(26)/lg(30)。三套主题（浅/暗/毛玻璃）各一套调色板，ThemeManager.apply 时追加到 QSS 末尾。
- `gui_utils.set_btn(btn, kind, size)` 设动态属性并 unpolish/polish 触发重匹配。
- 行内删除圆角/padding/背景/字号，改调 set_btn；裸按钮自动继承统一基础样式。

## 语义映射

- primary 蓝：解析/校验/导出报告/查询/发送/生成（EB）/添加字段
- success 绿：生成帧/打开串口/添加到测试方案/确定/保存/开始抓包/注册/开始记录
- danger 红：停止/删除/关闭串口/停止抓包/停止记录/删除字段
- warning 橙：填充CRC-24/命令说明/清空后台/添加到预设
- accent 紫：填充CRC-32/添加到测试方案/Lua 迷你
- secondary 灰：清空/取消/关闭/全屏/交换/载入/导出/刷新/暂停/注销/展开收缩
- ghost 透明：最大化图标按钮（diff）

## 改动文件

- theme_settings.py：新增 build_button_qss + 三套 BUTTON_PALETTE + button_qss_for_theme；apply 末尾注入；GLASS 圆角随统一 4。
- gui_utils.py：新增 set_btn。
- main_gui.py：单帧按钮行(lg)、串口开关(success/danger 切换)、保存/取消、导出图片、全屏、展开/收缩、关闭、各弹窗按钮。
- frame_gen_widget.py：生成/发送/添加预设/添加测试方案/清空日志、命令说明、EB 生成/应用、A-XDR +/删、清空响应、模板字段按钮。
- diff_widget.py：开始对比/交换/载入 A/B/导出/关闭/两个最大化按钮。
- monitor/tcp_monitor.py：开始/停止(success↔danger)、刷新/清空/暂停/加载、CSV 记录(success↔danger)。
- monitor/frame_monitor.py：添加到测试/校验/清空/导出。
- preset_buttons.py：确定、预设命令按钮。
- test_plan_widget.py：确定/开始/停止/清空后台/导出报告、表格迷你发送按钮(sm)。
- topology_widget.py：查询/清除/导出/定位/清除搜索。
- lookup_pages.py：添加/删除自定义 DI。
- system_integration/system_settings.py：注册/注销菜单与 Notepad++。

未改：monitor_widget / llm_preprocess_widget / llm_api_manager / archive_widget / message_tool_widget（按钮本就裸用或工厂只管尺寸，自动继承统一蓝）。LLM 折叠头(checkable)与串口刷新图标按钮保留各自特殊样式（自洽，不影响统一）。

## 验证

- 全部 17 个改动文件语法检查通过。
- offscreen 三主题（default/dark/glass）启动正常；按钮统计：primary 48 / success 9 / secondary 19 / warning 4 / accent 3 / danger 1(初始态) / 继承统一 93；共 163 按钮。
- 遍历全部 12 协议 + 全部 tab 无异常。
- danger 启动计数低属正常：停止/关闭类按钮在运行时由 set_btn 切换为 danger。

## 待真机确认

- 三主题下按钮颜色/hover/pressed/disabled 视觉效果（offscreen 无渲染）。
- 彩色按钮在毛玻璃半透明背景上的对比度。
