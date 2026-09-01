# GUI 图标集成阶段 1：主题感知图标引擎 + 标签页/窗口图标

## Goal

Lucide SVG 已入库（icons/lucide/，见 09-01-lucide-icons-bulk）。本阶段搭图标
使用基础设施并接入最显眼的三处：主窗口任务栏图标、11+ 个标签页图标、串口刷新按钮。
按钮/菜单/对话框的铺开是阶段 2。

## 核心设计：主题感知 QIconEngine

Lucide SVG 用 `stroke="currentColor"`，QtSvg 不识别该关键字，直接 QIcon(path)
会渲染成黑色，暗色主题下隐形。方案：新增根模块 `app_icons.py`：

- `load_icon(name) -> QIcon`：读 `icons/lucide/<name>.svg` 字节，返回自定义
  QIconEngine 包装的 QIcon。
- 自定义 engine 在 `paint()` 时按 QIcon.Mode 取色（Normal/Active/Selected =
  调色板 ButtonText；Disabled = Disabled 组 ButtonText），把 SVG 字节中的
  `currentColor` 替换为该颜色 hex，用 QSvgRenderer 现场渲染。
- 效果：图标颜色自动跟随亮/暗主题，禁用态自动变灰，主题切换无需重载
  （paint 每次现取调色板颜色）。
- SVG 字节按 name 缓存、QSvgRenderer 按 (name, color) 缓存。
- 语义色（成功绿/错误红/警告琥珀）阶段 2 再加 `load_icon(name, role=...)`。

## Requirements

- 新增 `app_icons.py`（项目根，与 share_dialog.py 同级，main_gui 直接 import）。
- main_gui.py：
  - `MainWindow` 设置 `setWindowIcon`（用现有 `app_icon.ico`）。
  - 全部 addTab 调用改为带图标重载，映射：
    单帧解析 terminal / 查询 search / 批量解析 files / 协议组帧 wrench /
    预设命令 bookmark / 测试方案 clipboard-list / 档案管理 archive /
    拓扑信息 network / 报文对比 file-diff / 报文工具 toolbox / 虚拟表 gauge /
    TCP监控 radar / 监控器 activity。
  - 串口刷新按钮图标由 icons/refresh.svg（iconfont 蓝色填充）换为
    `load_icon("refresh-cw")`，统一 Lucide 线性风格。
- `南网协议解析工具.spec`：datas 加入 `icons/` 目录（打包后 SVG 可被找到）。
- 新增 `test/test_app_icons.py`（offscreen）：SVG currentColor 替换正确、
  QIcon 非空、pixmap 渲染非空、缺失图标降级不崩。
- 不改动 Web/Reflex 侧；不动托盘（已用 app_icon.ico）。

## Acceptance Criteria

- [ ] 亮色主题：标签页图标为深色（跟随文字色）；暗色主题：图标为浅色，
      切换主题即时生效，无需重启。
- [ ] 禁用态控件上图标变灰。
- [ ] 13 个标签页均有图标且视觉风格统一（线性 24 viewBox）。
- [ ] 开发运行时任务栏/窗口图标为 app_icon（非 Python 默认图标）。
- [ ] 串口刷新按钮图标为 Lucide refresh-cw。
- [ ] `python test/test_app_icons.py` 通过；`test/test_theme_settings.py`
      回归通过（offscreen）。
- [ ] main_gui 可正常启动（offscreen 冒烟导入不报错）。

## Notes

- 阶段 2 候选：41 个按钮、菜单 QAction、分享/反馈对话框、状态语义色
  （check/x/triangle-alert）。
- QSvgRenderer 依赖 PySide6.QtSvg（pyside6 默认包含）。
