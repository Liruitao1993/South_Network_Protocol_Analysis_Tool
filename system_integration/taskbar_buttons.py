"""任务栏缩略图工具栏按钮（`ITaskbarList3::ThumbBarAddButtons`）—— 纯 ctypes，零新依赖。

**是什么**：鼠标悬停在任务栏图标上时，预览缩略图下方出现一排**可点按钮**（微软官方接口，
Win7 引入、**Win11 仍在用**）。这是第三方在 Windows 11 上能做出来的「任务栏上的可交互控件」
—— Win11 已移除 Win10 的「任务栏自定义工具栏 / deskband」，无法把任意控件塞进任务栏内部，
但缩略图按钮是受支持的入口。

**怎么用**（`main_gui` 侧）：

    tb = TaskbarButtons()
    tb.set_buttons(win, [(1, "解析剪贴板", icon), (2, "快捷解析", icon)])
    tb.clicked.connect(on_click_id)          # 按钮被点（真实点击或 WM_COMMAND 都走这里）
    tb.clear(win)                            # 收尾

**实现要点**（都踩过坑，改前先读）：

- 只声明用到的那几个 vtable 槽位（`HrInit`=3 / `ThumbBarAddButtons`=15 /
  `ThumbBarSetImageList`=17），**索引顺序不能错**（IUnknown 3 + ITaskbarList 5 + ITaskbarList2 1
  + ITaskbarList3 之后才是这三个）；
- 图标走 `THUMBBUTTON.hIcon`（不建 ImageList 也支持，但文档建议配 `ThumbBarSetImageList`；
  这里直接用 hIcon，省掉 image list 的索引管理），HICON 由 QImage 现转（`CreateIconIndirect`），
  **不做文件依赖**（仓库只有 SVG 图标）；
- 按钮点击由外壳发 `WM_COMMAND` 到**主窗口**（`LOWORD(wParam)` = 按钮 id）⇒ 用
  `QAbstractNativeEventFilter` 拦下来转成 `clicked` 信号并**吞掉**该消息（只吞 id 匹配的）；
- 窗口必须**有任务栏按钮**（可见或最小化；被 `hide()` 到托盘后没有按钮 ⇒ 调用返回 False）；
- 任何一步失败都**静默降级**返回 False（非 Windows / 无任务栏 / 接口不可用），绝不影响主程序。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

IS_WINDOWS = sys.platform.startswith("win")

#: 按钮 id 起点（避开 Qt/系统常用命令 id）
BASE_BUTTON_ID = 0x7700

#: 最多 7 个（接口硬限制）
MAX_BUTTONS = 7

# THUMBBUTTON 的 dwMask / dwFlags 位（shobjidl_core.h）
THB_BITMAP = 0x1
THB_ICON = 0x2
THB_TOOLTIP = 0x4
THB_FLAGS = 0x8
THBF_ENABLED = 0x0
THBF_DISABLED = 0x1
THBF_DISMISSONCLICK = 0x2
THBF_NOBACKGROUND = 0x4
THBF_HIDDEN = 0x8
THBF_NONINTERACTIVE = 0x10

WM_COMMAND = 0x0111

_CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
#: 取接口时按这个顺序试（**都用同一批 vtable 槽位**：ITaskbarList2 之后依次是
#: ThumbBarAddButtons 15 / ThumbBarUpdateButtons 16 / ThumbBarSetImageList 17 /
#: SetOverlayIcon 18 / SetThumbnailTooltip 19 / SetThumbnailClip 20；ITaskbarList4 只在末尾
#: 追加 SetTabProperties，故索引不变）。
#:
#: ⚠ **Win11 实测（10.0.26300）**：`CoCreateInstance`/`QI` 拿 `IID_ITaskbarList3`
#: 直接返回 `E_NOINTERFACE(0x80004002)`，而 `IID_ITaskbarList4` 正常（`HrInit`、
#: `ThumbBarAddButtons`、`SetThumbnailTooltip` 都返回 `S_OK`）—— 所以**必须先试 4**，
#: 只写 3 会在 Win11 上直接判「不可用」。
_IID_CANDIDATES = (
    "{C43DC798-95D1-4BEA-9030-BB99E2983A1A}",   # ITaskbarList4（Win7+，Win11 可用）
    "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84}",   # ITaskbarList3
    "{602D4995-B13A-429b-A66E-1935E44F4317}",   # ITaskbarList2
)

_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106：已按别的模式初始化（可继续用）


if IS_WINDOWS:  # pragma: no cover - 平台分支
    from ctypes import byref, sizeof, Structure
    from ctypes.wintypes import BOOL, DWORD, HWND, LPCWSTR, UINT

    class GUID(Structure):
        _fields_ = [("Data1", DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class THUMBBUTTON(Structure):
        _fields_ = [("dwMask", DWORD), ("iId", UINT), ("iBitmap", UINT),
                    ("hIcon", wintypes.HANDLE), ("pszTip", LPCWSTR), ("dwFlags", DWORD)]

    class ICONINFO(Structure):
        _fields_ = [("fIcon", BOOL), ("xHotspot", DWORD), ("yHotspot", DWORD),
                    ("hbmMask", wintypes.HANDLE), ("hbmColor", wintypes.HANDLE)]

    class BITMAPINFOHEADER(Structure):
        _fields_ = [("biSize", DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", DWORD),
                    ("biSizeImage", DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", DWORD),
                    ("biClrImportant", DWORD)]

    class BITMAPINFO(Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    # ⚠ 必须显式声明 argtypes：HANDLE 在 64 位下是 8 字节指针，不声明时 ctypes 按 C int
    # 传递 ⇒ `DeleteObject(hbm)` 会抛 `OverflowError: int too long to convert`（实测踩到）。
    _gdi32.CreateDIBSection.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.UINT,
                                        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                                        wintypes.DWORD]
    _gdi32.CreateDIBSection.restype = wintypes.HANDLE
    _gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT,
                                    ctypes.c_void_p]
    _gdi32.CreateBitmap.restype = wintypes.HANDLE
    _gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    _gdi32.DeleteObject.restype = wintypes.BOOL
    _user32.CreateIconIndirect.argtypes = [ctypes.c_void_p]
    _user32.CreateIconIndirect.restype = wintypes.HANDLE
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _ole32.CoInitializeEx.restype = ctypes.c_long
    _ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_void_p)]
    _ole32.CoCreateInstance.restype = ctypes.c_long


def _guid(text: str) -> "GUID":
    """`"{...}"` → GUID。"""
    from uuid import UUID
    u = UUID(text.strip("{}"))
    g = GUID()
    g.Data1, g.Data2, g.Data3 = u.time_low, u.time_mid, u.time_hi_version
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


def qimage_to_hicon(image) -> Optional[int]:
    """QImage（含 alpha）→ HICON；失败返回 None。

    32bpp top-down DIB + 全 0 的 1bpp AND 掩码 ⇒ `CreateIconIndirect`。
    """
    if not IS_WINDOWS:
        return None
    try:
        from PySide6.QtGui import QImage
    except Exception:  # pragma: no cover
        return None
    img = image
    if not isinstance(img, QImage):
        return None
    if img.format() != QImage.Format.Format_ARGB32:
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return None

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h                # 负高度 = top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0            # BI_RGB
    bits = ctypes.c_void_p()
    hbm_color = _gdi32.CreateDIBSection(None, byref(bmi), 0, byref(bits), None, 0)
    if not hbm_color or not bits:
        return None
    hbm_mask = None
    hicon = 0
    try:
        data = img.constBits().tobytes()            # PySide6 给 memoryview ⇒ 转 bytes 才能 memmove
        stride = img.bytesPerLine()
        row_bytes = w * 4
        if stride == row_bytes:
            ctypes.memmove(bits, data, min(len(data), w * h * 4))
        else:                                       # 有行对齐填充时逐行搬
            for y in range(h):
                src = y * stride
                ctypes.memmove(ctypes.c_void_p(bits.value + y * row_bytes),
                               data[src:src + row_bytes], row_bytes)
        hbm_mask = _gdi32.CreateBitmap(w, h, 1, 1, None)
        if not hbm_mask:
            return None
        info = ICONINFO(True, 0, 0, hbm_mask, hbm_color)
        hicon = int(_user32.CreateIconIndirect(byref(info)) or 0)   # 拷贝位图，之后可删
    finally:
        if hbm_mask:
            _gdi32.DeleteObject(hbm_mask)
        _gdi32.DeleteObject(hbm_color)
    return hicon or None


class _NativeClickFilter(QAbstractNativeEventFilter):
    """把缩略图按钮的 `WM_COMMAND` 转成 Python 回调（只吞自己那批 id）。"""

    def __init__(self, owner: "TaskbarButtons"):
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt 命名)
        """⚠ PySide6 的返回是**单个 bool**（True = 已处理/吞掉）；返回元组会被当 truthy
        把**所有** WM_COMMAND 都吞掉（曾踩）。"""
        try:
            if event_type != b"windows_generic_MSG":
                return False
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message != WM_COMMAND:
                return False
            btn_id = int(msg.wParam) & 0xFFFF
            if btn_id in self._owner._ids:
                self._owner.clicked.emit(btn_id)
                return True        # 吞掉（已处理）
        except Exception:
            pass
        return False


class TaskbarButtons(QObject):
    """任务栏缩略图工具栏按钮（一个实例可管一个窗口）。"""

    clicked = Signal(int)        # 按钮 id（`BASE_BUTTON_ID + 序号`）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._taskbar = None
        self._ids: List[int] = []
        self._hwnd = 0
        self._filter = None
        self._co_inited = False

    # ── 可用性 ────────────────────────────────────────────────────────────

    def available(self) -> bool:
        """本机是否能用（非 Windows / COM 建不出来 ⇒ False）。"""
        return self._ensure_taskbar() is not None

    def _ensure_taskbar(self):
        if not IS_WINDOWS:
            return None
        if self._taskbar is not None:
            return self._taskbar
        try:
            if not self._co_inited:
                hr = _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
                # S_OK(0) / S_FALSE(1) / RPC_E_CHANGED_MODE（Qt 已按别的模式初始化）都可用
                self._co_inited = hr in (0, 1, _RPC_E_CHANGED_MODE)
            clsid = _guid(_CLSID_TaskbarList)
            ptr = ctypes.c_void_p()
            for iid_text in _IID_CANDIDATES:
                iid = _guid(iid_text)
                ptr = ctypes.c_void_p()
                hr = _ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid), byref(ptr))
                if hr == 0 and ptr:
                    break
                ptr = None
            if not ptr:
                return None
            self._taskbar = ptr
            self._hr_init()
            return self._taskbar
        except Exception:
            return None

    def _call(self, index: int, restype, *argtypes):
        """按 vtable 索引取方法（IUnknown 3 + …），返回可调用对象。"""
        tb = self._taskbar
        vtable = ctypes.cast(tb, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        method = proto(vtable[index])
        return method

    def _hr_init(self) -> None:
        try:
            self._call(3, ctypes.c_long)(self._taskbar)          # ITaskbarList::HrInit
        except Exception:
            pass

    # ── 挂按钮 ────────────────────────────────────────────────────────────

    def set_buttons(self, window, buttons: Sequence[Tuple[str, object]]) -> bool:
        """给 `window`（QWidget）挂按钮：`[("工具提示", QIcon|QImage|None), …]`。

        成功 True；不可用/无任务栏按钮/接口报错 ⇒ False（调用方据此静默降级）。
        """
        if not buttons or not IS_WINDOWS:
            return False
        tb = self._ensure_taskbar()
        if tb is None:
            return False
        hwnd = self._hwnd_of(window)
        if not hwnd:
            return False
        items = list(buttons)[:MAX_BUTTONS]
        try:
            arr = (THUMBBUTTON * len(items))()
            ids = []
            for i, (tip, icon) in enumerate(items):
                btn_id = BASE_BUTTON_ID + i
                ids.append(btn_id)
                hicon = self._hicon(icon)
                arr[i].dwMask = THB_TOOLTIP | (THB_ICON if hicon else 0)
                arr[i].iId = btn_id
                arr[i].hIcon = hicon or None
                arr[i].pszTip = tip
                arr[i].dwFlags = THBF_ENABLED | THBF_DISMISSONCLICK
            method = self._call(15, ctypes.c_long, HWND, UINT,
                                ctypes.POINTER(THUMBBUTTON))     # ThumbBarAddButtons
            hr = method(tb, hwnd, len(items), arr)
            if hr != 0:
                return False
            self._ids = ids
            self._hwnd = hwnd
            self._install_filter()
            return True
        except Exception:
            return False

    def clear(self, window=None) -> None:
        """卸掉按钮（`ThumbBarUpdateButtons` 置 `THBF_HIDDEN`）并摘掉事件过滤器。"""
        if IS_WINDOWS and self._taskbar is not None and self._ids:
            hwnd = self._hwnd_of(window) or self._hwnd
            if hwnd:
                try:
                    arr = (THUMBBUTTON * len(self._ids))()
                    for i, btn_id in enumerate(self._ids):
                        arr[i].dwMask = THB_FLAGS
                        arr[i].iId = btn_id
                        arr[i].dwFlags = THBF_HIDDEN | THBF_DISABLED
                    self._call(16, ctypes.c_long, HWND, UINT,
                               ctypes.POINTER(THUMBBUTTON))(self._taskbar, hwnd,
                                                            len(self._ids), arr)
                except Exception:
                    pass
        self._ids = []
        self._remove_filter()

    def _install_filter(self) -> None:
        if self._filter is not None:
            return
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return
        self._filter = _NativeClickFilter(self)
        app.installNativeEventFilter(self._filter)

    def _remove_filter(self) -> None:
        if self._filter is None:
            return
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeNativeEventFilter(self._filter)
            except Exception:
                pass
        self._filter = None

    # ── 辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _hwnd_of(window) -> int:
        try:
            handle = window.windowHandle()
            if handle is None:
                return 0
            return int(handle.winId())
        except Exception:
            return 0

    def _hicon(self, icon) -> int:
        """QIcon / QImage / None → HICON（失败 None）。尺寸取系统小图标。"""
        if icon is None:
            return None
        try:
            from PySide6.QtGui import QIcon, QImage
            size = 16
            try:
                size = int(_user32.GetSystemMetrics(49)) or 16      # SM_CXSMICON
            except Exception:
                pass
            img = None
            if isinstance(icon, QIcon):
                img = icon.pixmap(size, size).toImage()
            elif isinstance(icon, QImage):
                img = icon
            if img is None or img.isNull():
                return None
            return qimage_to_hicon(img)
        except Exception:
            return None


__all__ = ["TaskbarButtons", "BASE_BUTTON_ID", "MAX_BUTTONS", "qimage_to_hicon"]
