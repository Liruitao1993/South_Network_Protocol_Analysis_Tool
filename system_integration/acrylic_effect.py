"""
Windows 毛玻璃（Acrylic / 亚克力）背景效果
=========================================

为无边框置顶悬浮窗（如快捷解析小窗）启用系统级亚克力模糊：
窗口背后桌面/其他窗口内容会被模糊并叠加一层色调，配合半透明卡片色
即得到「毛玻璃」观感。

- 仅 Windows 10 1803+ / Windows 11 生效（ACCENT_ENABLE_ACRYLICBLURBEHIND）
- 非 Windows 或调用失败时安全降级（函数静默返回 False），不影响运行

Qt 侧需配合：窗口设置 WA_TranslucentBackground，卡片/控件使用半透明背景色。
"""

from __future__ import annotations

import sys


def enable_acrylic(window, tint=(28, 32, 44), alpha=40) -> bool:
    """
    为指定 QWidget 顶层窗口启用亚克力毛玻璃。

    Args:
        window: 顶层 QWidget（须已创建 winId，一般在 showEvent 中调用）。
        tint:   (r, g, b) 叠加色调 0~255。
        alpha:  色调叠加不透明度 0~255；低值时模糊感更强、底色更透。
                卡片自身的半透明背景色决定主体观感，这里给很低的基色即可。

    Returns:
        True 表示已（重新）应用亚克力；False 表示平台不支持或失败。
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(window.winId())
        if not hwnd:
            return False

        class _ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_uint),
                ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_uint),
            ]

        # ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
        # GradientColor 为 0xAABBGGRR：alpha 高字节
        r, g, b = (max(0, min(255, int(c))) for c in tint[:3])
        a = max(0, min(255, int(alpha)))
        gradient = (a << 24) | (b << 16) | (g << 8) | r

        accent = _ACCENTPOLICY(4, 2, gradient, 0)

        class _WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(ctypes.c_int)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        data = _WINCOMPATTRDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.POINTER(ctypes.c_int))

        user32 = ctypes.windll.user32
        set_attr = getattr(user32, "SetWindowCompositionAttribute", None)
        if set_attr is None:
            return False
        set_attr.restype = ctypes.c_int
        set_attr.argtypes = [wintypes.HWND, ctypes.POINTER(_WINCOMPATTRDATA)]
        return bool(set_attr(hwnd, ctypes.byref(data)))
    except Exception:
        return False
