"""GUI 测试的 config.json 沙箱：把用户配置重定向到临时目录（test/ 目录共享）。

**为什么需要**（任务 09-15-gui-window-state-persist 起）：`MainWindow` 在「真实退出」
路径会把窗口几何 / 分栏比例 / 列宽写进 `config.json`。凡是构造并 **show()/close()**
主窗口的测试，都会把 offscreen 合成出来的几何写进**开发机的真实 `config.json`**，
用户下次启动即被套用（实测写入过 684×666 这类尺寸）。

两类测试处理方式不同：

- **只构造、从不 show** 的测试：无需沙箱。`main_gui.closeEvent` 有
  `_window_shown_once` 守卫（从未示人的窗口不写盘）。
- **会 show 窗口** 的测试（如 `test_app_exit.py` 测托盘/关闭、`test_theme_settings.py`）：
  必须沙箱，否则跑一趟 `release_check.py` 就会改掉用户的窗口布局。

用法（测试进程短命，`install()` 无需还原）：

    import _config_sandbox

    _config_sandbox.install()          # ① 整个进程生效（推荐）

    with _config_sandbox.sandbox():    # ② 精确作用域
        ...

**实现要点**：必须**同时** patch `app_paths.data_path` 与 `main_gui.data_path`——
后者在 `import main_gui` 时已把名字绑进模块命名空间（`from app_paths import ...`），
只 patch 前者对已导入的 `MainWindow` 不生效。这也是 `test_window_state.py`
内联 Sandbox 采用的同一口径。
"""

from __future__ import annotations

import pathlib
import tempfile
from contextlib import contextmanager
from unittest.mock import patch


def _fake_data_path(tmp: str):
    """构造替身 `data_path`：所有数据文件都落到 `tmp` 下。"""

    def _data_path(name):
        return pathlib.Path(tmp) / str(name)

    return _data_path


@contextmanager
def sandbox():
    """精确作用域的配置沙箱：进入时重定向，退出时还原。"""
    import app_paths

    with tempfile.TemporaryDirectory(prefix="nw_cfg_") as tmp:
        fake = _fake_data_path(tmp)
        with patch.object(app_paths, "data_path", fake):
            try:
                import main_gui
            except ImportError:
                main_gui = None  # 无 Qt 环境下退化为「只隔离 app_paths」
            if main_gui is None:
                yield pathlib.Path(tmp)
            else:
                with patch.object(main_gui, "data_path", fake):
                    yield pathlib.Path(tmp)


def install() -> pathlib.Path:
    """进程级安装（不还原）：返回沙箱目录。

    测试脚本以 `os._exit()` 结束、进程短命，故无需 stop()；
    返回目录便于断言「写到了沙箱」而不是真实配置。
    """
    import app_paths

    tmp = tempfile.mkdtemp(prefix="nw_cfg_")
    fake = _fake_data_path(tmp)
    patch.object(app_paths, "data_path", fake).start()
    try:
        import main_gui
    except ImportError:
        return pathlib.Path(tmp)
    patch.object(main_gui, "data_path", fake).start()
    return pathlib.Path(tmp)


__all__ = ["install", "sandbox"]
