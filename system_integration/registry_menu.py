"""
注册表操作模块（系统集成）
=========================
- 开机自启：HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
- 文件右键菜单：HKCU\\Software\\Classes\\*\\shell\\<App> + 各扩展名二级子菜单

所有操作均在 HKCU 下，无需管理员权限。
"""
import os
import sys
from pathlib import Path

import winreg

APP_NAME = "协议解析工具"
AUTO_START_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SHELL_KEY = r"Software\Classes"

# 支持的文件扩展名
SUPPORTED_EXTENSIONS = [".log", ".txt", ".hex", ".bin"]

# 右键菜单协议项：菜单名 → 协议索引（与 protocol_combo 一致）
# 只列常用协议，避免菜单过长
MENU_PROTOCOLS = [
    ("南网协议", 0),
    ("国网协议", 7),
    ("新一代载波", 9),
    ("国网新一代", 10),
    ("HDLC/DLMS", 2),
    ("DLT645", 6),
    ("PLC RF", 1),
    ("698.45协议", 8),
]


def get_exe_path() -> str:
    """返回可执行文件路径（开发模式返回 main_gui.py，打包后返回 exe）"""
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(__file__).resolve().parent.parent / "main_gui.py")


def get_launch_command() -> str:
    """返回带引号的完整启动命令（无控制台窗口）

    开发模式：pythonw.exe "main_gui.py"（避免黑框）
    打包后：  "exe路径"（GUI 模式，本身无控制台）
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # 找 pythonw.exe（与当前 python.exe 同目录）
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if pythonw.exists():
        return f'"{pythonw}" "{get_exe_path()}"'
    # 找不到 pythonw 时退化为 python.exe（开发环境异常情况）
    return f'"{sys.executable}" "{get_exe_path()}"'


def _open_key(root, path, access):
    import winreg
    return winreg.OpenKey(root, path, 0, access)


def _create_key(root, path):
    import winreg
    return winreg.CreateKeyEx(root, path, 0, winreg.KEY_ALL_ACCESS)


def _delete_key_recursive(root, sub_path):
    """递归删除注册表键及其所有子键"""
    import winreg
    try:
        key = winreg.OpenKey(root, sub_path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
        # 删除所有子键
        try:
            while True:
                sub_key_name = winreg.EnumKey(key, 0)
                _delete_key_recursive(key, sub_key_name)
        except OSError:
            pass
        winreg.CloseKey(key)
        winreg.DeleteKey(root, sub_path)
    except OSError:
        pass


# ==================== 开机自启 ====================

def get_autostart() -> bool:
    """检查开机自启是否已注册"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTO_START_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    """设置开机自启（enabled=True 写入，False 删除）"""
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, AUTO_START_KEY, 0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
    )
    try:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass
    finally:
        winreg.CloseKey(key)


# ==================== 文件右键菜单 ====================

def _menu_command(protocol_index: int) -> str:
    """生成右键菜单项命令：<launch> --file "%1" --protocol <index>"""
    return f'{get_launch_command()} --file "%1" --protocol {protocol_index}'


def register_context_menu() -> bool:
    """注册文件右键菜单（HKCU 级，无需管理员权限）"""
    import winreg
    try:
        # 一级：所有文件的右键菜单
        shell_path = rf"{SHELL_KEY}\*\shell\{APP_NAME}"
        with _create_key(winreg.HKEY_CURRENT_USER, shell_path) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "用协议解析工具解析")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, get_exe_path())
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "用协议解析工具解析")
            winreg.SetValueEx(key, "SubCommands", 0, winreg.REG_SZ, "")

        # 二级子菜单（各扩展名各协议）
        for ext in SUPPORTED_EXTENSIONS:
            ext_base = ext.lstrip(".")
            for label, proto_idx in MENU_PROTOCOLS:
                sub_path = (
                    rf"{SHELL_KEY}\{ext}\shell\{APP_NAME}_{ext_base}_{proto_idx}"
                )
                with _create_key(winreg.HKEY_CURRENT_USER, sub_path) as key:
                    winreg.SetValueEx(key, None, 0, winreg.REG_SZ, label)
                    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, get_exe_path())
                    winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, label)
                # 命令子键
                cmd_path = sub_path + r"\command"
                with _create_key(winreg.HKEY_CURRENT_USER, cmd_path) as key:
                    winreg.SetValueEx(key, None, 0, winreg.REG_SZ, _menu_command(proto_idx))
        return True
    except Exception as e:
        print(f"[注册表] 注册右键菜单失败: {e}")
        return False


def unregister_context_menu() -> bool:
    """取消注册文件右键菜单"""
    try:
        shell_path = rf"{SHELL_KEY}\*\shell\{APP_NAME}"
        _delete_key_recursive(winreg.HKEY_CURRENT_USER, shell_path)

        for ext in SUPPORTED_EXTENSIONS:
            ext_base = ext.lstrip(".")
            for _, proto_idx in MENU_PROTOCOLS:
                sub_path = rf"{SHELL_KEY}\{ext}\shell\{APP_NAME}_{ext_base}_{proto_idx}"
                _delete_key_recursive(winreg.HKEY_CURRENT_USER, sub_path)
        return True
    except Exception as e:
        print(f"[注册表] 取消注册右键菜单失败: {e}")
        return False


def is_context_menu_registered() -> bool:
    """检查右键菜单是否已注册"""
    import winreg
    try:
        shell_path = rf"{SHELL_KEY}\*\shell\{APP_NAME}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, shell_path, 0, winreg.KEY_READ):
            return True
    except OSError:
        return False
