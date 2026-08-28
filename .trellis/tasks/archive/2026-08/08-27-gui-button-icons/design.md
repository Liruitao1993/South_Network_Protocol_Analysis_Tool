# 设计：GUI 按钮添加图标

## 现状（调查结论）

- 上一任务「统一按钮风格」已把全应用按钮统一到 `btnKind` 语义色 + `set_btn()`，但**纯文字**按钮，无图标。
- 批量工具栏有 4 个文本字形按钮（★保存 / ×删除 / ?帮助），风格与其余按钮不一致。
- `icons/` 目录存在并打包，但只承载 app 图标等；本任务不新增资源。
- Qt 内置标准图标通过 `self.style().standardIcon(QStyle.StandardPixmap.SP_xxx)` 获取，主题无关、零资源、随系统渲染（含高 DPI）。

## 目标

- 为语义明确的主要功能按钮配 Qt 内置标准图标（图标 + 文字并存）。
- 保留 `btnKind` 语义色、文字、布局与尺寸体系，不破坏上一任务成果。
- 图标统一 16px，与文字间留间距（`setIconSize`），随主题/高 DPI 正常显示。
- 无合适标准图标的按钮保留原样或就近映射，不强行硬配出怪异图标。

## 技术方案

### 1. gui_utils 加图标辅助（核心）

新增 `set_btn_icon(btn, icon_key)`，内部把图标 key 映射到 `QStyle.StandardPixmap` 并 `btn.setIcon(icon) + btn.setIconSize(QSize(16,16))`。用统一的 `_STANDARD_ICON_MAP`：

```python
from PySide6.QtWidgets import QStyle
from PySide6.QtGui import QIcon

_STANDARD_ICON_MAP = {
    "open":      QStyle.StandardPixmap.SP_DirOpenIcon,          # 打开/载入
    "save":      QStyle.StandardPixmap.SP_DialogSaveButton,     # 保存
    "open_file": QStyle.StandardPixmap.SP_DialogOpenButton,     # 打开文件
    "apply":     QStyle.StandardPixmap.SP_DialogApplyButton,    # 应用/确定
    "ok":        QStyle.StandardPixmap.SP_DialogOkButton,       # 确定
    "cancel":    QStyle.StandardPixmap.SP_DialogCancelButton,   # 取消/关闭
    "refresh":   QStyle.StandardPixmap.SP_BrowserReload,        # 刷新
    "delete":    QStyle.StandardPixmap.SP_TrashIcon,            # 删除/清空
    "clear":     QStyle.StandardPixmap.SP_LineEditClearButton,  # 清空
    "play":      QStyle.StandardPixmap.SP_MediaPlay,            # 解析/发送/开始/运行
    "stop":      QStyle.StandardPixmap.SP_MediaStop,            # 停止
    "pause":     QStyle.StandardPixmap.SP_MediaPause,           # 暂停
    "copy":      QStyle.StandardPixmap.SP_FileDialogContentsView,  # 复制（或换 FileIcon）
    "export":    QStyle.StandardPixmap.SP_DialogSaveButton,     # 导出/报告
    "help":      QStyle.StandardPixmap.SP_MessageBoxInformation,  # 帮助/说明
    "search":    QStyle.StandardPixmap.SP_FileDialogContentsView,  # 查询/搜索
    "warning":   QStyle.StandardPixmap.SP_MessageBoxWarning,    # 警告类
    "apply2":    QStyle.StandardPixmap.SP_DialogApplyButton,    # 通用执行
}
```

实现要点：
- `set_btn_icon` 里 `icon_key` 未知时**静默跳过**（`_STANDARD_ICON_MAP.get`），保证不会因缺映射崩溃。
- 图标按钮也可单独设 `iconOnly=True`：设图标 + 隐藏文字（`btn.setText("")`），但**默认不用**（保持图标+文字并存，符合需求）。
- 图标颜色随系统主题自动适配（Qt 标准图标自带配色），无需手动处理。

### 2. 各文件按钮加图标（图标+文字并存）

按上一任务 implement.md 的「改动文件」清单逐文件给主要按钮配图，映射原则：
- 解析/校验/生成帧/发送/开始/运行 → `play`
- 保存 → `save`；导出/导出报告 → `export`
- 删除/删除字段 → `delete`；清空/清空日志 → `clear`
- 打开串口/打开文件/载入 → `open` / `open_file`
- 停止/关闭串口/停止抓包/停止记录 → `stop`；暂停 → `pause`
- 刷新/交换 → `refresh`
- 查询/搜索 → `search`
- 命令说明/帮助 → `help`
- 添加到测试方案/添加到预设/确定/应用 → `apply` / `ok` / `cancel`

具体逐文件：
- `main_gui.py`：单帧解析（解析/校验/发送）、批量解析工具栏（★保存→save、×删除→delete、?帮助→help、导出/导出选中→export、清空→clear、载入→open、刷新→refresh）、串口（打开/停止）、各弹窗（下载/取消）。
- `frame_gen_widget.py`：生成帧/发送/添加预设/添加测试方案/清空日志/命令说明/A-XDR 加减。
- `diff_widget.py`：开始对比/交换/载入A/B/导出/关闭。
- `monitor/tcp_monitor.py`：开始/停止/刷新/清空/暂停/加载/CSV 记录。
- `monitor/frame_monitor.py`：添加到测试/校验/清空/导出。
- `preset_buttons.py`：确定、预设命令按钮。
- `test_plan_widget.py`：确定/开始/停止/清空后台/导出报告。
- `topology_widget.py`：查询/清除/导出/定位/清除搜索。
- `lookup_pages.py`：添加/删除自定义 DI。
- `system_integration/system_settings.py`：注册/注销菜单。
- `monitor_widget.py` / `archive_widget.py` / `message_tool_widget.py` / `llm_*`：给明显主操作按钮补图标（若语义明确）。

### 3. 不新增资源、不改 spec

全部用 `QStyle.StandardPixmap` 内置图标，`icons/` 目录与 spec 打包**完全不动**。

## 影响文件

gui_utils.py（新增 set_btn_icon + _STANDARD_ICON_MAP）、main_gui.py、frame_gen_widget.py、diff_widget.py、monitor/tcp_monitor.py、monitor/frame_monitor.py、preset_buttons.py、test_plan_widget.py、monitor_widget.py、archive_widget.py、topology_widget.py、lookup_pages.py、message_tool_widget.py、llm_preprocess_widget.py、llm_api_manager.py、system_integration/system_settings.py。

## 验收

- [ ] 主要页面主操作按钮均带图标（图标+文字并存，文字完整显示）。
- [ ] 图标 16px、与文字留间距、随主题/高 DPI 正常。
- [ ] 三主题（浅/暗/毛玻璃）下图标清晰、不模糊、不溢出。
- [ ] 无合适图标的按钮保持原样或就近映射，无怪异图标。
- [ ] 语法检查通过，offscreen 三主题启动主窗口无异常。
- [ ] `set_btn_icon` 对未知 key 静默安全（不崩溃）。
