# -*- coding: utf-8 -*-
"""画布配色单源（深浅主题）—— 给自绘 / 图形视图 / 行号槽这类「非 QSS 控件」。

QSS 主题（`theme_settings`）只覆盖标准控件；**自绘画布**（`QGraphicsView` 场景、
`paintEvent` 里 fillRect 的区域、`QTextCharFormat` 的默认前后景）必须自己跟着主题走，
否则深色主题下会出现整块白底（拓扑图就是典型：曾写死 `#FAFAFA`）。

约定：颜色一律用 `#rrggbb` 字符串（本模块**不 import Qt**，可脱 GUI 单测）；
使用方各自负责把字符串包成 `QColor`。

键位（按语义，不按像素位置）：
    bg       —— 画布/视图底色
    bg_alt   —— 次级底色（行号槽、表头、留白条纹）
    border   —— 边框/分隔线
    text     —— 主前景（正文、节点轮廓、连线主干）
    muted    —— 次要文字（节点角色名、统计行）
    hint     —— 占位/空态提示
    line     —— 弱化连线（未知信道）
    highlight —— 高亮（当前定位节点）
    hover    —— 悬停高亮
"""

from typing import Dict

__all__ = ["CANVAS_PALETTES", "palette"]

#: 键位说明见模块 docstring；两套必须键位完全一致（有测试守）
CANVAS_PALETTES: Dict[bool, Dict[str, str]] = {
    False: {  # 浅色
        "bg": "#FAFAFA",
        "bg_alt": "#F2F2F2",
        "border": "#CCCCCC",
        "text": "#333333",
        "muted": "#666666",
        "hint": "#999999",
        "line": "#999999",
        "highlight": "#FF0000",
        "hover": "#FF5722",
    },
    True: {  # 深色（与日志面板 #1E1E1E 同一族，避免同屏两个深灰）
        "bg": "#1E1E1E",
        "bg_alt": "#262626",
        "border": "#4A4A4A",
        "text": "#E0E0E0",
        "muted": "#B0BEC5",
        "hint": "#9AA0A6",
        "line": "#7A7A7A",
        "highlight": "#FF5252",
        "hover": "#FF8A65",
    },
}


def palette(dark: bool) -> Dict[str, str]:
    """取对应主题的配色（返回**副本**，调用方可放心改而不污染单源）。"""
    return dict(CANVAS_PALETTES[bool(dark)])
