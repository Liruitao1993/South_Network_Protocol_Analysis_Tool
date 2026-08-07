# 实现计划：批量解析 Python 脚本预处理

## 执行顺序

### Step 1: 新增 py_script_engine.py
- 文件：`py_script_engine.py`
- 实现 `load_script(path)` — 用 importlib 或 exec 加载 .py，返回 module
- 实现 `build_context(main_window)` — 取协议索引/名称/解析器
- 实现 `run_script(module, text, context)` — 找 process() 并调用
- 验证：写个测试脚本验证三函数可用性

### Step 2: 新增示例脚本
- 目录：`scripts/`
- `scripts/hex_clean.py`：去除非十六进制字符，按行分割，每行归一化为连续 hex
- `scripts/tcp_payload_extract.py`：从 "tcp data: XX XX ..." 格式提取 payload
- `scripts/filter_by_parse.py`：逐行调用 parser.parse，只保留解析成功的帧
- 验证：手动 import 运行

### Step 3: main_gui.py 插入脚本区 UI
- 位置：`create_batch_parse_tab()` 内，CLI 预处理区与导出按钮之间
- 控件：`QLabel("脚本:")` + `QComboBox`（可编辑？否，仅选择） + 「加载」按钮 + 「运行」按钮 + 「×」删除按钮 + 「?」帮助按钮
- 下拉框显示 name，userData 存 path
- 工具提示说明功能与安全提示

### Step 4: 实现持久化
- `_load_py_scripts()`：读 config.json `py_scripts` 段，空则自动注册示例
- `_persist_py_scripts()`：下拉项写回 config.json
- 「加载」按钮：`QFileDialog.getOpenFileName` 选 .py，取文件名（去扩展）为显示名，追加到下拉，持久化
- 「×」按钮：移除当前选中项，持久化

### Step 5: 实现运行逻辑
- `_run_py_script()`：
  - 校验输入框非空、脚本已选
  - 调用 engine 三连（load / build_context / run）
  - 结果回填 + 状态栏更新
  - 异常捕获 + QMessageBox

### Step 6: 帮助与文档
- `_show_py_script_help()`：弹窗说明 API 契约、context 字段、示例
- `scripts/` 下放 README.md 说明脚本编写规范

### Step 7: 验证
- 启动 GUI，检查脚本区控件是否可见
- 加载一个 .py 文件，关闭重开，确认下拉保留
- 运行 hex_clean 示例脚本，确认文本被正确处理
- 运行一个故意报错的脚本，确认弹错误框且原内容保留
- 确认 CLI 预处理、LLM 预处理不受影响
- 运行 `test_csg_batch_parse_level.py` 等现有批量相关测试（如有）

## 高风险点

- **main_gui.py 体积大**：插入 UI 代码位置要准确，用 `Edit` 精确替换，避免破坏布局
- **parser 获取方式**：需确认当前协议对应 parser 在主窗口中如何持有（可能是即时创建，也可能是成员变量），需先探查
- **示例脚本调用 parser**：parser 的 `parse` 方法签名各协议不一致，需在示例中用 try/except 兼容

## 回滚点

每步完成后均可独立回滚：
- Step 1/2：删除新文件
- Step 3-6：在 main_gui.py 中删除新增代码块（有明确标记）
- 配置残留无害
