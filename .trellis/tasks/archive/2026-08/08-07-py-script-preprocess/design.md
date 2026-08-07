# 设计：批量解析 Python 脚本预处理

## 架构总览

新增独立模块 `py_script_engine.py` 封装脚本加载、执行、context 构建。UI 部分在 `main_gui.py` 批量解析工具栏插入脚本选择区，与 CLI 预处理并列。

```
┌─────────────────────────────────────────────────────────────┐
│ 批量解析工具栏                                                │
│ [CLI 预处理区] │ [Python 脚本区] │ [导出按钮]                  │
└─────────────────────────────────────────────────────────────┘
         │                      │
         ▼                      ▼
   pp_cli.py           py_script_engine.py
     (已有)          ┌─────────────────────┐
                     │ load_script(path)   │  读取文件 + 编译
                     │ run_script(module,  │
                     │   text, context)    │  调用 process()
                     │ build_context(...)  │  构造 context dict
                     └─────────────────────┘
                              │
                              ▼
                        用户 .py 脚本
                     (可 import 项目内模块)
```

## 数据结构

### config.json 新增段

```json
{
  "py_scripts": [
    {"name": "TCP hex 提取", "path": "scripts/tcp_hex_extract.py"},
    {"name": "自定义清洗", "path": "C:/Users/xxx/myscript.py"}
  ]
}
```

- `name`：显示名（脚本文件名默认，可重命名——本期不做重命名，用文件名）
- `path`：绝对路径或相对项目根的相对路径

### context dict

```python
{
    "protocol_index": int,        # 当前协议索引 0-10
    "protocol_name": str,         # 协议显示名
    "config_dir": str,            # config.json 所在目录（即项目根）
    "parser": object,             # 当前协议解析器实例
    "main_window": QMainWindow,   # 主窗口引用（可选，脚本可操作 UI）
}
```

`parser` 来源：主窗口根据 `current_protocol` 返回对应 parser 实例。需要新增一个辅助方法 `_get_current_parser()` 复用已有 parser。

## 模块边界

### 新增：`py_script_engine.py`

```python
def load_script(path: str) -> types.ModuleType:
    """加载并编译脚本文件，返回 module 对象。异常向上抛。"""

def build_context(main_window) -> dict:
    """从主窗口取当前协议、解析器等，构造 context。"""

def run_script(module, text: str, context: dict) -> str:
    """调用 module.process(text, context)，返回结果。无 process 函数抛异常。"""
```

### 修改：`main_gui.py`

- `create_batch_parse_tab()`：工具栏新增脚本区 UI（在 CLI 预处理区之后、导出按钮之前插入分隔线 + 脚本控件）
- `_load_py_scripts()`：从 config.json 加载脚本列表到下拉框
- `_persist_py_scripts()`：下拉框内容写回 config.json
- `_load_py_script_file()`：文件对话框选 .py，加入下拉列表并持久化
- `_run_py_script()`：执行当前选中脚本，结果回填 batch_input
- `_delete_py_script()`：从下拉列表移除选中项
- `_show_py_script_help()`：显示脚本 API 说明 + 示例

### 新增：`scripts/` 目录与示例脚本

- `scripts/__init__.py`（空，包标记）
- `scripts/hex_clean.py`：通用 hex 提取 + 每行一帧
- `scripts/tcp_payload_extract.py`：TCP 日志 payload 提取
- `scripts/filter_by_parse.py`：调用解析器过滤有效帧

### 首次启动注册

`_load_py_scripts()` 中，若 `config.json` 无 `py_scripts` 段，自动注册 `scripts/` 下示例脚本。

## 执行流程

1. 用户从下拉选择脚本 → 或点「加载」选 .py 文件
2. 点「运行」
3. 读取 `batch_input.toPlainText()` 作为输入
4. 调用 `py_script_engine.load_script(path)` → `build_context(self)` → `run_script(mod, text, ctx)`
5. 结果非空则 `batch_input.setPlainText(result)`，状态栏更新行数
6. 异常则 `QMessageBox.critical` 显示 traceback，原内容保留

## 兼容性

- 纯新增功能，不修改现有预处理逻辑
- 三种预处理（CLI / LLM / Python 脚本）完全独立，用户可按任意顺序串联使用
- `config.json` 新增字段，旧配置自动兼容（缺省为空列表，首次启动填充示例）

## 风险

- **脚本安全性**：直接 exec 运行，恶意脚本可破坏系统。本项目为本地工具，信任用户自有脚本，接受此风险。UI 加 tooltip 提示。
- **脚本无限循环**：同步执行会卡住 GUI。MVP 不加超时机制，复杂需求后续加 QThread 异步执行。
- **解析器引用**：`context['parser']` 指向主窗口持有 parser，脚本修改其状态可能影响后续解析。文档化说明。

## 回滚

- 删除 `py_script_engine.py`、`scripts/` 目录
- 移除 `main_gui.py` 中脚本区 UI 及方法
- `config.json` 中 `py_scripts` 段残留无害
