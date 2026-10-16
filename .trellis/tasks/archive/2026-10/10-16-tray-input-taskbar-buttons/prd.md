# 桌面粘性入口：托盘菜单内嵌报文输入框 + 任务栏缩略图按钮

## Goal

用户问：「汽水音乐电脑版安装后会在任务栏上建立**可交互的控件**（不是小图标），我这个工程能不能也在 Win11 任务栏上建立一个**报文输入控件**，增加用户粘性？」

**先把能力边界弄清楚**（这是本任务的第一个交付物，避免做了没用）：

| 用户看到的东西 | 实际是什么 | 第三方能否用 |
|---|---|---|
| 任务栏上「封面 + 标题 + 上一首/播放/下一首 + ♥」 | **SMTC 系统媒体卡片**（`SystemMediaTransportControls`） | 只有**媒体会话**能占；非媒体应用要用得"伪装成媒体"，且按钮语义固定 |
| 想在任务栏那一行放**输入框** | —— | **不能**。Win11 已移除 Win10 的 deskband/自定义工具栏，任务栏对第三方封闭 |
| 托盘图标右键菜单 | `QSystemTrayIcon` 菜单 | **可以**放任意控件（`QWidgetAction`） ✓ |
| 悬停任务栏图标时的预览按钮 | `ITaskbarList3/4::ThumbBarAddButtons` | **可以**（官方接口，Win7+；本机 Win11 实测可用） ✓ |

⇒ 本任务落两条**系统支持**的入口：① 托盘菜单内嵌输入框；② 任务栏缩略图按钮。

## Requirements

1. **托盘菜单内嵌报文输入框**（`system_integration/sys_tray.py`）：`QWidgetAction` 里放「输入框 + 解析按钮」；
   回车或点按钮 → `parse_text_requested(str)` 信号 + 清空输入 + 收起菜单。
   解析路径**由主窗口注入**（托盘模块不 import 解析器）。
2. **解析判据与剪贴板检测同源**（`clipboard_monitor.strict_hex`）：整串严格 HEX ⇒ `_parse_and_show_dialog`
   （协议先按特征识别，识别不出用当前下拉）；否则退回「按文本提取报文」（与文件右键/`--file` 同一实现）；
   两者都不是 ⇒ **不静默**：状态栏 + 托盘气泡说明。
3. **任务栏缩略图按钮**（新模块 `system_integration/taskbar_buttons.py`，纯 ctypes、零新依赖）：
   `available()` / `set_buttons(win, [(提示, QIcon)])` / `clear(win)`；点击经 `WM_COMMAND` →
   `QAbstractNativeEventFilter` → `clicked(int)` 信号；**任何失败静默降级返回 False**（非 Windows / 无任务栏 /
   接口拿不到），绝不抛、绝不影响主程序。
4. **四个按钮**（`MainWindow.TASKBAR_BUTTONS` 单一清单 + `_on_taskbar_button` 分派）：
   解析剪贴板 / 快捷解析 / 批量解析 / 光伏升级（切协议 8 + 切到该页）。
5. **生命周期**：`showEvent` 里 `QTimer.singleShot(0, _setup_taskbar_buttons)`（**句柄变化才重挂**，
   避免重复 `ThumbBarAddButtons` 叠加）；`closeEvent` 真实退出路径 `clear()`；挂失败只提示一次（状态栏），不反复刷。

## Acceptance Criteria

- [ ] 托盘：菜单里有内嵌输入框；回车发出 `parse_text_requested` 且输入清空；空白不提交；`set_input_enabled` 可禁用并改占位提示
- [ ] `_parse_text_input`：严格 HEX → `_parse_and_show_dialog(字节, 识别出的协议)`；非 HEX 文本 → `_parse_text_content`；
      空/无可提取 ⇒ False（调用方给状态栏 + 气泡提示）
- [ ] `qimage_to_hicon`：真实 QImage → 非 0 HICON；空图/非图像 → None
- [ ] `set_buttons([])`、未就绪时 → False 不抛；`clear()` 幂等
- [ ] 合成 `WM_COMMAND`：命中自己那批 id ⇒ 发 `clicked` 且**吞掉**消息；别的 id / 别的消息类型 ⇒ 不发也不吞
- [ ] `_on_taskbar_button`：4 个 id 分别落到 解析剪贴板 / 快捷解析 / 批量解析(切 tab) / 光伏升级(协议8 + 切 tab)；越界 id 无动作
- [ ] **真机**：`_setup_taskbar_buttons()` → True、按钮 id `0x7700..0x7703`、`PostMessage(WM_COMMAND)` 能触发回调
- [ ] 回归：`test/test_tray_taskbar_entries.py` 全绿并登记 `release_check.py:GUI_TESTS`；`release_check.py --with-gui` 无**新增** FAIL

## Notes

- **Win11 实测硬坑**（已写进 AGENTS §8 陷阱 78 与 spec §7k）：`IID_ITaskbarList3` 在本机（10.0.26300）返回
  `E_NOINTERFACE`，**必须先用 `IID_ITaskbarList4`**；涉及 `HANDLE` 的 Win32 调用**必须显式 `argtypes`**
  （否则 `DeleteObject` 抛 OverflowError）；PySide6 的 `nativeEventFilter` 返回**单个 bool**（元组会吞掉所有 WM_COMMAND）。
- **不做的**：SMTC 伪媒体卡片（用户截图那种）—— 语义错位 + 非媒体会话是否显示需实测，本次不做（真机已确认
  缩略图按钮可用，价值更直接）；AppBar 屏幕边缘常驻条 —— 会占屏幕空间，需用户确认后再谈。
- **已知边界**（已向用户说明）：缩略图按钮只在窗口**有任务栏按钮**时可见；点 X 隐藏到托盘后就没有了
  （想常驻要改「关到托盘」为「最小化到托盘」，那是行为变更、需单独确认）。
- 本任务**跳过独立复核子代理**（改动 400 行自包含模块 + 真机验证 S_OK 与点击路由已闭环）；如需再补一轮
  trellis-check 可作为后续。
