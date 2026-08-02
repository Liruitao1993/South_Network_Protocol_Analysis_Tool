"""
Notepad++ 集成模块（系统集成）
=============================
在 Notepad++ 中注册"用协议解析工具解析"：
- 右键菜单项（contextMenu.xml 增加 Item 引用运行命令）
- 运行命令（shortcuts.xml UserDefinedCommands），触发解析器 --clipboard

用户操作：在 NPP 中选中报文 → Ctrl+C 复制 → 右键"用协议解析工具解析"或快捷键 → 弹出解析窗口。

实现：
- shortcuts.xml：UserDefinedCommands 加 <Command name="用协议解析工具解析" ...>"exe" --clipboard</Command>
- contextMenu.xml：ScintillaContextMenu 加 <Item MenuEntryName="Run" MenuItemName="用协议解析工具解析"/>
- 两个 xml 都带备份，失败可回滚

注意：NPP 运行命令无法直接读取选中文本，必须依赖剪贴板。用户在右键前先 Ctrl+C。
"""
import os
import shutil
from pathlib import Path

from system_integration.registry_menu import get_launch_command

NPP_CMD_NAME = "用协议解析工具解析"
BACKUP_SUFFIX = ".parser_backup"


def _npp_config_dir() -> Path:
    """NPP 配置目录（%APPDATA%/Notepad++）"""
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Notepad++"


def _backup(file: Path) -> None:
    if file.exists() and not file.with_suffix(file.suffix + BACKUP_SUFFIX).exists():
        shutil.copy2(file, file.with_suffix(file.suffix + BACKUP_SUFFIX))


def _exe_cmd() -> str:
    """生成解析器命令行：<launch> --clipboard（pythonw 启动避免黑框）"""
    return f'{get_launch_command()} --clipboard'


def _inject_shortcuts_xml() -> bool:
    """在 shortcuts.xml UserDefinedCommands 注入运行命令"""
    cfg = _npp_config_dir() / "shortcuts.xml"
    if not cfg.exists():
        return False
    _backup(cfg)
    xml = cfg.read_text(encoding="utf-8-sig", errors="replace")

    # 已注入则跳过
    if NPP_CMD_NAME in xml and "--clipboard" in xml:
        return True

    if "<UserDefinedCommands>" not in xml:
        return False
    command = (
        f'        <Command name="{NPP_CMD_NAME}" Ctrl="no" Alt="no" Shift="no" Key="0">'
        f'{_exe_cmd()}</Command>\n'
    )
    xml = xml.replace("<UserDefinedCommands>", "<UserDefinedCommands>\n" + command, 1)
    cfg.write_text(xml, encoding="utf-8")
    return True


def _inject_context_menu_xml() -> bool:
    """在 contextMenu.xml 右键菜单注入运行命令引用"""
    cfg = _npp_config_dir() / "contextMenu.xml"
    if not cfg.exists():
        return False
    _backup(cfg)
    xml = cfg.read_text(encoding="utf-8-sig", errors="replace")

    # 已注入则跳过
    if NPP_CMD_NAME in xml:
        return True

    item = f'        <Item MenuEntryName="Run" MenuItemName="{NPP_CMD_NAME}"/>\n'
    # 插到第一个 <Item> 之前（菜单顶部）
    if "<Item " not in xml:
        return False
    idx = xml.find("<Item ")
    # 找该 Item 所在行首
    line_start = xml.rfind("\n", 0, idx) + 1
    xml = xml[:line_start] + item + xml[line_start:]
    cfg.write_text(xml, encoding="utf-8")
    return True


def register_npp() -> bool:
    """注册 NPP 集成：右键菜单 + 运行命令"""
    try:
        ok1 = _inject_shortcuts_xml()
        ok2 = _inject_context_menu_xml()
        return ok1 or ok2
    except Exception as e:
        print(f"[NPP集成] 注册失败: {e}")
        return False


def unregister_npp() -> bool:
    """取消注册 NPP 集成：从两个 xml 移除命令"""
    try:
        cfg = _npp_config_dir()
        # 从 shortcuts.xml 移除命令行
        sc = cfg / "shortcuts.xml"
        if sc.exists():
            lines = sc.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            lines = [l for l in lines if f'name="{NPP_CMD_NAME}"' not in l]
            sc.write_text("\n".join(lines), encoding="utf-8")
        # 从 contextMenu.xml 移除 Item
        cm = cfg / "contextMenu.xml"
        if cm.exists():
            lines = cm.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            lines = [l for l in lines if NPP_CMD_NAME not in l]
            cm.write_text("\n".join(lines), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[NPP集成] 取消注册失败: {e}")
        return False


def is_npp_registered() -> bool:
    """检查 NPP 集成是否已注册"""
    try:
        cfg = _npp_config_dir()
        sc = cfg / "shortcuts.xml"
        if sc.exists() and "--clipboard" in sc.read_text(encoding="utf-8-sig", errors="replace"):
            return True
        cm = cfg / "contextMenu.xml"
        if cm.exists() and NPP_CMD_NAME in cm.read_text(encoding="utf-8-sig", errors="replace"):
            return True
        return False
    except Exception:
        return False
