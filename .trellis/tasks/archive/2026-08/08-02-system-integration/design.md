# 系统集成增强 - 设计文档

## 架构

```
main_gui.py
  ├── SystemTrayManager (sys_tray.py)     QSystemTrayIcon 管理
  ├── GlobalHotkeyManager (global_hotkey.py)  RegisterHotKey 全局热键
  ├── RegistryMenuManager (registry_menu.py) HKCU 右键菜单注册
  ├── SingleInstanceServer (single_instance.py) QLocalServer 单实例
  └── SettingsDialog (system_settings.py)  系统集成设置对话框
```

主窗口通过组合持有上述管理器实例；设置对话框内嵌到 `ThemeSettingsDialog`。

## 核心模块

### 1. SystemTrayManager (sys_tray.py)
- 构造：图标 + 右键菜单（显示主窗口 / 开机自启开关 / 退出）+ 左键单击显示/隐藏
- `MainWindow.closeEvent` → 若 `tray_enabled`，`hide()` + `event.ignore()` + 气泡提示一次
- 左键单击：`show()` 已隐藏则显示，否则 `hide()`
- 退出：`tray_exit()` 标记 `_exiting=True`，调 `app.quit()`
- 开机自启开关：写入/删除 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，值名 `协议解析工具`

### 2. GlobalHotkeyManager (global_hotkey.py)
- 用 Windows API `RegisterHotKey`（`ctypes`，HWND=0），消息循环内 `PeekMessage` 检测 WM_HOTKEY
- 原因：QShortcut 无法跨进程捕获；`keyboard` 库需管理员权限且与 GUI 线程混用有风险
- `HotkeyThread(QThread)`：独立线程，`RegisterHotKey(0, 1, MOD_CONTROL|MOD_ALT, 'P')`，循环 PeekMessage，WM_HOTKEY → signal → 主线程回调
- 回调：读剪贴板 → 提取 hex → 按当前协议解析 → 弹出结果对话框
- 默认 `Ctrl+Alt+P`，可改键（虚拟键码 + 修饰符）
- 解析调用复用 `MainWindow.parse_single` 的解析器路径，但使用独立弹窗而非主窗口表格

### 3. RegistryMenuManager (registry_menu.py)
- 注册 `HKCU\Software\Classes\*\shell\协议解析工具` → 命令 `exe_path --file "%1" --protocol <协议名>`
- 扩展 `.log .txt .hex .bin` 二级子菜单：每个扩展名一个 shell 项，子菜单各协议
- 子菜单项：南网协议 / 国网协议 / 新一代载波 / 国网新一代 / HDLC/DLMS / DLT645 / PLC RF / 698.45
- 用 `winreg` 写入；提供 `register()` / `unregister()` / `is_registered()`
- 文件类型映射协议名 → `protocol_combo` 索引

### 4. SingleInstanceServer (single_instance.py)
- 用 `QLocalServer` 监听固定名 `协议解析工具_singleton`
- 重复启动：`QLocalSocket` 尝试连接 → 成功则发送参数并退出；失败则成为主实例
- 收到参数 → 主窗口 `show()` + 按参数执行（--file 加载解析 / --parse 解析 / --protocol 切换）

### 5. SettingsDialog (system_settings.py)
- 内嵌到 `ThemeSettingsDialog` 底部，新增"系统集成"分组：
  - 开机自启复选框（读/写 HKCU Run）
  - 关闭行为单选：最小化到托盘 / 直接退出
  - 全局热键输入框（默认 Ctrl+Alt+P）+ 启用/禁用开关
  - 注册右键菜单按钮 / 取消注册按钮 + 状态提示
- 保存到 `config.json` 的 `"system"` 段

## 命令行参数

- `--parse <hex>`：启动后直接解析该 hex 并弹窗显示
- `--protocol <name>`：启动时切换协议
- `--file <path>`：读取文件内容，提取 hex 帧，按协议解析并弹窗
- `--minimized`：启动后最小化到托盘（若托盘启用）
- 无参数：正常启动

## 解析复用的关键路径

`_get_current_parser()` (main_gui.py:2444) 返回当前协议的 `parse_to_table` 对象；
热键/文件/命令行统一走该路径。弹窗解析结果对话框：
- 4列表格（字段/原始值/解析值/说明）+ hex 显示 + 复制菜单
- 协议索引来自 `protocol_combo` 当前值或参数指定

## 配置持久化

`config.json` 新增 `"system"` 段：
```json
"system": {
  "auto_start": false,
  "close_to_tray": true,
  "hotkey_enabled": true,
  "hotkey": "Ctrl+Alt+P",
  "tray_startup_hint": true
}
```
`_load_app_config`/`_save_app_config` 读写该段。

## 兼容性与风险

- 热键使用原生 `RegisterHotKey`，PyInstaller 打包后仍可用；无需管理员权限
- 右键菜单注册在 HKCU（无需管理员），卸载时需取消注册
- 退出崩溃历史问题：`closeEvent` 中不做 UI 销毁，仅 `hide()` + `event.ignore()`，避免已删除 C++ 对象访问
- 热键触发时若正在抓包/批量解析，弹窗与主窗口并行，不阻塞
- 若全局热键注册失败（如键冲突），降级提示并继续运行
