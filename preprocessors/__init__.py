# -*- coding: utf-8 -*-
"""CLI 预处理工具注册表

通用文本预处理工具 pp_cli.py 提供管道式命令链：
    find <pat> | excluding <pat> | replace <pat> <repl>
    head <n> | tail <n> | skip <n> | hex_extract | dedup

GUI 集成通过 main_gui.py 的 _pp_cmd_edit 输入命令，
调用 pp_cli.parse_and_run() 执行管线。
"""
from typing import Dict, List, Any


def list_scripts() -> List[Dict[str, Any]]:
    """返回预处理工具列表（兼容旧接口）"""
    return [
        {
            "id": "pp_cli",
            "name": "通用预处理",
            "description": "管道式命令链（find/excluding/replace/head/tail/skip/hex_extract/dedup）",
            "order": 10,
        },
    ]


def get_script(script_id: str) -> Dict[str, Any]:
    """按 ID 获取工具元信息（兼容旧接口）"""
    for s in list_scripts():
        if s["id"] == script_id:
            return s
    return {}
