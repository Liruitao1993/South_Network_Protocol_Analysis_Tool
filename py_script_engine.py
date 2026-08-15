"""
Python 脚本预处理引擎。

加载用户自定义 .py 脚本，通过约定的 process(text, context) 入口函数
对批量解析输入文本进行预处理。脚本可自由 import 项目内模块、
调用 context['parser'] 等内置对象。

安全说明：脚本直接 exec 运行，无沙箱，仅适用于受信任的本地脚本。
"""

import os
import sys
import traceback
import types
import uuid


class _LazyParser:
    """懒加载 parser 包装器：第一次访问属性时才真正从 main_window 取 parser。

    避免脚本不需要 parser 时也触发 HDLC/DLMS 等重量级解析器初始化。
    """

    def __init__(self, main_window):
        self._main_window = main_window
        self._parser = None
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            self._parser = self._main_window._get_current_parser()
        except Exception:
            self._parser = None

    def __getattr__(self, name):
        # 不拦截内部属性
        if name.startswith('_'):
            raise AttributeError(name)
        self._ensure_loaded()
        if self._parser is None:
            raise RuntimeError("当前协议解析器不可用")
        return getattr(self._parser, name)

    def __repr__(self):
        if self._loaded:
            return f"<LazyParser loaded={self._parser is not None}>"
        return "<LazyParser (not loaded yet)>"


def load_script(path: str) -> types.ModuleType:
    """加载并编译 Python 脚本文件，返回 module 对象。

    Args:
        path: 脚本文件路径（.py）

    Returns:
        编译后的 module 对象

    Raises:
        FileNotFoundError: 文件不存在
        SyntaxError: 脚本语法错误
        Exception: 其他加载/执行异常
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"脚本文件不存在: {path}")

    # 确保脚本所在目录在 sys.path 中，方便脚本相对 import
    script_dir = os.path.dirname(os.path.abspath(path))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    # 用唯一模块名避免缓存冲突
    module_name = f"_user_script_{uuid.uuid4().hex}"
    module = types.ModuleType(module_name)
    module.__file__ = os.path.abspath(path)
    module.__name__ = module_name

    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    code = compile(source, os.path.abspath(path), "exec")
    exec(code, module.__dict__)  # noqa: S102 - 信任本地脚本

    return module


def build_context(main_window) -> dict:
    """从主窗口构造脚本 context。

    context 包含：
    - protocol_index: 当前协议索引（int）
    - protocol_name: 当前协议显示名（str）
    - config_dir: 配置/项目根目录（str）
    - app_dir: 应用根目录（即 main_gui.py 所在目录）
    - parser: 当前协议解析器实例（懒加载，首次访问时才构造）
    - main_window: 主窗口引用（仅主线程可访问 UI）
    """
    idx = main_window.current_protocol

    # 优先从协议下拉框取显示名
    if hasattr(main_window, "protocol_combo") and 0 <= idx < main_window.protocol_combo.count():
        name = main_window.protocol_combo.itemText(idx)
    else:
        name = f"协议{idx}"

    config_dir = str(main_window._config_path.parent) \
        if hasattr(main_window, "_config_path") else os.getcwd()

    return {
        "protocol_index": idx,
        "protocol_name": name,
        "config_dir": config_dir,
        "app_dir": config_dir,
        "parser": _LazyParser(main_window),  # 懒加载
        "main_window": main_window,
    }


def run_script(module, text: str, context: dict) -> str:
    """执行脚本的 process 函数。

    脚本需定义：
        def process(text: str, context: dict) -> str:

    Args:
        module: load_script 返回的模块对象
        text: 输入文本
        context: build_context 返回的上下文字典

    Returns:
        处理后的文本字符串

    Raises:
        AttributeError: 脚本未定义 process 函数
        Exception: 脚本执行中的任何异常，原样上抛（含 traceback 信息）
    """
    if not hasattr(module, "process") or not callable(module.process):
        raise AttributeError(
            "脚本未定义可调用的 process(text, context) 函数。\n"
            "请在脚本中添加：\n"
            "    def process(text, context):\n"
            "        # 处理 text\n"
            "        return text"
        )

    try:
        result = module.process(text, context)
    except Exception:
        tb = traceback.format_exc()
        raise RuntimeError(f"脚本执行失败:\n{tb}") from None

    if result is None:
        raise ValueError("脚本 process() 返回了 None，请返回字符串。")

    if not isinstance(result, str):
        try:
            result = str(result)
        except Exception:
            raise TypeError(
                f"脚本 process() 返回类型 {type(result).__name__}，"
                f"期望返回字符串 str。"
            )

    return result
