# 系统集成增强 - 实施计划

## 步骤

### 1. 新建 system_integration/ 包骨架
- `system_integration/__init__.py`
- `system_integration/sys_tray.py` — SystemTrayManager
- `system_integration/global_hotkey.py` — GlobalHotkeyManager
- `system_integration/registry_menu.py` — RegistryMenuManager
- `system_integration/single_instance.py` — SingleInstanceServer

### 2. sys_tray.py
- 构造图标 + 菜单（显示主窗口 / 开机自启开关 / 退出）
- 左键单击显示/隐藏
- `_toggle_auto_start()`：读写 HKCU Run 键

### 3. global_hotkey.py
- HotkeyThread：RegisterHotKey + PeekMessage 循环
- 信号 `hotkey_triggered`
- 解析热键字符串（Ctrl/Alt/Shift + 字母）→ 虚拟键码 + 修饰符

### 4. registry_menu.py
- `register()`：写 `HKCU\Software\Classes\*` shell 项 + 扩展名子菜单
- `unregister()` / `is_registered()`
- 协议名 → 索引映射

### 5. single_instance.py
- QLocalServer 监听；`send_args()` / `start_server()` / `args_received` 信号

### 6. 系统集成设置对话框 system_settings.py
- 开机自启复选框 / 关闭行为单选 / 热键配置 / 右键菜单注册按钮
- 读取/保存 config.json "system" 段

### 7. main_gui.py 集成
- `_show_theme_settings_dialog` 中内嵌系统设置分组
- `__init__` 创建 tray + hotkey + single_instance 管理器
- `closeEvent` 重写：关闭→托盘
- `main()` 命令行参数解析（--parse/--protocol/--file/--minimized）
- 弹窗解析结果对话框（4列表格 + 复制）

### 8. 错误处理
- 热键注册失败 → 提示继续运行
- 右键菜单注册失败 → QMessageBox 报错
- 剪贴板无 hex → 提示
- 单实例重复启动 → 传参给已有实例并退出

### 9. 测试验证
- 语法检查：`python -c "import ast; ast.parse(...)"`
- 启动测试：`python main_gui.py`
- 功能验证（人工）：自启/托盘/热键/右键菜单/命令行

## 验证命令

```bash
python -c "import ast; ast.parse(open('system_integration/sys_tray.py', encoding='utf-8').read())"
python -c "import ast; ast.parse(open('main_gui.py', encoding='utf-8').read())"
python main_gui.py --parse "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16" --protocol "南网协议"
```

## 风险点

- **RegisterHotKey 与 Qt 消息循环**：在独立线程做 PeekMessage 循环，避免阻塞 Qt 事件循环
- **PyInstaller 单文件模式**：`sys.argv[0]` 指向临时解压路径，需用 `sys.executable` 定位 exe 真实路径写注册表
- **剪贴板格式**：可能含中文/空格/换行，先 `_clean_hex_input` 清洗再判断
- **托盘图标**：需要 `.ico` 图标文件，打包时含入；无图标则用默认程序图标

## 修改的文件

- 新建：`system_integration/` 包（6 个文件）
- 修改：`main_gui.py`（tray/热键/单实例/命令行/弹窗解析）
- 修改：`theme_settings.py`（内嵌系统设置分组）
- 修改：`南网协议解析工具.spec`（含入图标）
