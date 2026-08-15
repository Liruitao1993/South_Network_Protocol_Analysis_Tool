# 实现计划: 批量解析 LLM 智能预处理

## 实现顺序

### Step 1: LLM API 客户端 (`llm_preprocess.py`)
- `LLMAPIClient` 类：endpoint/key/model 配置、chat 方法
- 用 `urllib.request` 发 HTTP 请求（无额外依赖）
- 支持 OpenAI 兼容 API 格式
- 错误处理：超时、认证失败、响应格式错误

### Step 2: 分块器 + Worker (`llm_preprocess.py`)
- `LLMChunker`：按行数分块
- `LLMWorker(QThread)`：异步调用 + 进度信号 + 合并结果
- 连接 `finished`/`error` 信号

### Step 3: 预处理面板 UI (`llm_preprocess_widget.py`)
- 输入区：QPlainTextEdit + 加载文件按钮
- Prompt 区：QComboBox（模板）+ QPlainTextEdit（自定义）
- 操作区：执行按钮 + QProgressBar + 状态标签
- 输出区：QPlainTextEdit + 保存按钮 + 「加载到批量解析」按钮
- 信号：`load_to_batch_parse_requested(str)` → 通知 MainWindow

### Step 4: 集成到 MainWindow (`main_gui.py`)
- 导入 `LLMPreprocessWidget`
- 在 `create_batch_parse_tab()` 中添加 LLM 预处理面板（作为可折叠区域或子标签页）
- 连接 `load_to_batch_parse_requested` 信号到 `batch_input.setText()`
- config.json 读写：`_load_llm_config()` / `_save_llm_config()`

### Step 5: 设置面板
- 在 `ConfigDialog` 或独立设置页中添加 LLM API 配置
- endpoint、api_key、model 输入框
- 测试连接按钮

### Step 6: Prompt 模板
- 内置 5 个常用模板
- 模板存储在 config.json 的 `llm.prompt_templates` 数组
- 用户可编辑/保存自定义模板

### Step 7: 测试 + 验证
- 测试 LLM API 调用（mock 或真实）
- 测试分块逻辑
- 测试多轮预处理流程
- 测试加载到批量解析的完整链路
- 测试错误处理（网络失败、API 错误）

## 验证命令

```bash
# 语法检查
python -c "import llm_preprocess; import llm_preprocess_widget"

# 单元测试（可选）
python test_llm_preprocess.py

# GUI 集成验证
python main_gui.py  # 手动测试 LLM 预处理面板
```

## 风险文件

| 文件 | 风险 | 原因 |
|---|---|---|
| `main_gui.py` | 中 | 需在批量解析标签页中插入新组件，注意布局兼容 |
| `config.json` | 低 | 新增段，不影响现有段 |

## 回滚点

- Step 1-3 可独立回滚（新增文件，删除即可）
- Step 4 需回滚 main_gui.py 的导入和集成代码
- config.json 的 `llm` 段可安全删除（不影响其他配置）
