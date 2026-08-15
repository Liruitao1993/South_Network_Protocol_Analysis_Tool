# 技术设计: 批量解析 LLM 智能预处理

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                  MainWindow                      │
│  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ 批量解析标签页 │  │ LLM 预处理面板（新增）   │  │
│  │              │  │ ┌──────────────────────┐  │  │
│  │  输入区       │←─┤│ 输出区 + 加载按钮     │  │  │
│  │  解析按钮     │  │ └──────────────────────┘  │  │
│  │  结果表格     │  │ ┌──────────────────────┐  │  │
│  │              │←──┤│ 输入区 + prompt编辑   │  │  │
│  └──────────────┘  │ │ 执行按钮              │  │  │
│                    │ └──────────────────────┘  │  │
│                    └──────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │                        │
         │ parse_batch()          │ LLMWorker(QThread)
         ▼                        ▼
┌──────────────┐         ┌──────────────────┐
│ 现有解析流程  │         │ LLMAPIClient     │
│ 无任何改动    │         │ (requests/urllib)│
└──────────────┘         └──────────────────┘
```

## 新增文件

| 文件 | 职责 |
|---|---|
| `llm_preprocess.py` | LLM API 客户端 + 分块逻辑 + QThread 工作线程 |
| `llm_preprocess_widget.py` | 预处理面板 UI 组件 |

## 修改文件

| 文件 | 改动 |
|---|---|
| `main_gui.py` | 导入 LLMPreprocessWidget，集成到批量解析标签页 |
| `config.json` | 新增 `llm` 段（endpoint、api_key、model、chunk_size） |

## 核心类设计

### `llm_preprocess.py`

```python
class LLMAPIClient:
    """OpenAI 兼容 API 客户端"""
    def __init__(self, endpoint: str, api_key: str, model: str):
        ...
    
    def chat(self, prompt: str, content: str, temperature: float = 0.0) -> str:
        """发送请求，返回纯文本响应"""
        # POST {endpoint}/chat/completions
        # headers: Authorization: Bearer {api_key}
        # body: {model, messages: [{role:"system", content:prompt}, {role:"user", content:content}], temperature}
        ...

class LLMChunker:
    """大文件分块器"""
    def __init__(self, chunk_lines: int = 200):
        self.chunk_lines = chunk_lines
    
    def chunk(self, text: str) -> List[str]:
        """按行数分块"""
        lines = text.splitlines(keepends=True)
        return ["".join(lines[i:i+self.chunk_lines]) 
                for i in range(0, len(lines), self.chunk_lines)]

class LLMWorker(QThread):
    """异步 LLM 调用工作线程"""
    progress = Signal(str)      # 状态信息
    finished = Signal(str)      # 最终结果
    error = Signal(str)         # 错误信息
    
    def __init__(self, client: LLMAPIClient, chunker: LLMChunker, 
                 prompt: str, content: str):
        ...
    
    def run(self):
        """分块调用 LLM，合并结果"""
        chunks = self.chunker.chunk(self.content)
        results = []
        for i, chunk in enumerate(chunks):
            self.progress.emit(f"处理中... ({i+1}/{len(chunks)})")
            result = self.client.chat(self.prompt, chunk)
            results.append(result)
        self.finished.emit("\n".join(results))
```

### `llm_preprocess_widget.py`

```python
class LLMPreprocessWidget(QWidget):
    """LLM 预处理面板"""
    
    def __init__(self):
        # 输入区：文本编辑器（加载文件/粘贴）
        # Prompt 区：模板下拉 + 自定义编辑
        # 操作区：执行按钮 + 进度条
        # 输出区：文本编辑器（结果 + 保存/加载按钮）
        ...
    
    def load_file(self):
        """加载日志文件到输入区"""
        ...
    
    def execute_preprocess(self):
        """执行 LLM 预处理"""
        # 1. 读取输入区文本
        # 2. 读取 prompt
        # 3. 创建 LLMWorker 异步执行
        # 4. 连接信号：progress → 进度条, finished → 输出区
        ...
    
    def save_output(self):
        """保存输出到文件"""
        ...
    
    def load_to_batch_parse(self):
        """将输出加载到批量解析输入区"""
        # 通过信号通知 MainWindow
        ...
```

## 数据流

### 配置读写
```
config.json {
  "llm": {
    "endpoint": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "gpt-4o",
    "chunk_lines": 200,
    "prompt_templates": [...]
  }
}
```

### LLM 调用流程
```
用户点击「执行预处理」
  → 读取输入区文本 + prompt
  → LLMChunker.chunk(text) 分块
  → for each chunk:
      → LLMWorker.progress(进度)
      → LLMAPIClient.chat(prompt, chunk)
      → 收集结果
  → 合并所有块结果
  → LLMWorker.finished(合并结果)
  → 写入输出区
```

### 加载到批量解析
```
用户点击「加载到批量解析」
  → 读取输出区文本
  → 写入 MainWindow.batch_input
  → 切换到批量解析标签页
  → 用户可点击「开始批量解析」
```

## 兼容性

- 不修改 `parse_batch()` 及任何现有解析逻辑
- 不修改现有批量解析 UI
- LLM 预处理面板是纯新增组件
- config.json 新增 `llm` 段，不影响现有段
- 新增依赖：无（用 stdlib urllib.request 替代 requests，避免强制依赖）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| LLM 输出不稳定 | temperature=0.0 + prompt 明确格式要求 |
| API 调用超时 | 设置 60s 超时 + 重试 1 次 |
| 大文件 token 超限 | 自动分块 + 用户可调块大小 |
| API key 泄露 | config.json 加入 .gitignore |
| 网络不可用 | 错误提示 + 降级为手动输入 |
