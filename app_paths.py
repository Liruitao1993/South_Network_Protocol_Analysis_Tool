"""应用数据文件路径工具。

PyInstaller 单文件 exe 中 ``__file__`` 指向临时解压目录（_MEIPASS，进程退出即删），
用户配置会全部丢失。本模块统一约定：

- **可写数据文件**（config.json、预设、测试方案、档案、自定义 DI 等）→ ``data_path()``，
  frozen 时落 **exe 所在目录**，开发模式落项目根；
- **内置只读资源** → 继续用 ``__file__``（frozen 下即 _MEIPASS，天然正确）。

注意：``sys.frozen`` / ``sys.executable`` / ``sys._MEIPASS`` 一律在函数调用时读取，
禁止模块级缓存，否则测试无法通过 monkeypatch 模拟 frozen 态。
本模块只依赖标准库（protocol_parser 等无 Qt 模块也会引用）。
"""

import shutil
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """用户可写数据目录：frozen 时为 exe 所在目录，开发模式为项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_path(name: str) -> Path:
    """可写数据文件路径（如 ``data_path("config.json")``）。"""
    return app_data_dir() / name


def resource_path(name: str) -> Path:
    """内置只读资源路径：frozen 时在 _MEIPASS，开发模式同数据目录。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", app_data_dir()))
        return base / name
    return app_data_dir() / name


def ensure_data_file(name: str) -> Path:
    """确保数据文件存在：不存在且内置资源有同名文件时复制一份作为初始值。

    dev 模式下源==目标为 no-op；目标目录不可写（如 Program Files）时静默吞错。
    """
    target = data_path(name)
    if target.exists():
        return target
    source = resource_path(name)
    if source.exists() and source.resolve() != target.resolve():
        try:
            shutil.copy2(source, target)
        except OSError:
            pass
    return target
