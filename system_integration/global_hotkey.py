"""
全局热键模块（系统集成）
========================
使用 Windows API RegisterHotKey 实现全局热键（跨进程捕获）。
QShortcut 无法跨进程；`keyboard` 库需管理员权限且与 GUI 线程混用有风险。

实现：独立线程循环 PeekMessage 检测 WM_HOTKEY，通过 Qt Signal 发回主线程。
"""
import ctypes
import ctypes.wintypes as wt
import threading

from PySide6.QtCore import QThread, Signal

# Windows 常量
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# 热键字符串 → (虚拟键码, 修饰符) 映射
# 虚拟键码：A-Z = ord(字母)，数字 = ord(数字字符)，F1-F12 = 0x70-0x7B
MODIFIER_MAP = {
    "ctrl": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


def parse_hotkey(hotkey_str: str):
    """解析热键字符串如 "Ctrl+Alt+P" → (vk_code, modifiers)"""
    parts = [p.strip().lower() for p in hotkey_str.replace(" ", "").split("+") if p.strip()]
    if not parts:
        return None
    key = parts[-1]
    modifiers = 0
    for mod in parts[:-1]:
        if mod in MODIFIER_MAP:
            modifiers |= MODIFIER_MAP[mod]
        else:
            return None

    # 解析按键
    if len(key) == 1 and key.isalpha():
        vk = ord(key.upper())
    elif len(key) == 1 and key.isdigit():
        vk = ord(key)  # 数字 0-9
    elif key.startswith("f") and len(key) in (2, 3) and key[1:].isdigit():
        f_num = int(key[1:])
        if 1 <= f_num <= 12:
            vk = 0x70 + f_num - 1
        else:
            return None
    else:
        return None
    return vk, modifiers


class GlobalHotkeyThread(QThread):
    """独立线程运行 RegisterHotKey + PeekMessage 循环"""
    hotkey_triggered = Signal()

    def __init__(self, vk: int, modifiers: int, parent=None):
        super().__init__(parent)
        self._vk = vk
        self._modifiers = modifiers
        self._id = 1
        self._running = False
        self._registered = False
        self._hThread = None

    def run(self):
        self._running = True
        user32 = ctypes.windll.user32

        msg = wt.MSG()
        # 先调用一次 PeekMessage 创建线程消息队列（RegisterHotKey hWnd=0 依赖队列）
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)  # PM_NOREMOVE

        # 注册热键
        if not user32.RegisterHotKey(0, self._id, self._modifiers, self._vk):
            self._registered = False
            return
        self._registered = True
        try:
            while self._running:
                # PeekMessage 非阻塞轮询 + 小睡，避免空转烧 CPU
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):  # PM_REMOVE
                    if msg.message == WM_HOTKEY and msg.wParam == self._id:
                        self.hotkey_triggered.emit()
                    else:
                        # 需要翻译并分发普通消息
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    self.msleep(30)
        finally:
            user32.UnregisterHotKey(0, self._id)

    def stop(self):
        self._running = False
        self.wait(2000)

    def is_registered(self) -> bool:
        return self._registered


class GlobalHotkeyManager:
    """管理全局热键的注册与触发回调"""

    def __init__(self, hotkey_str: str = "Ctrl+Alt+X"):
        self._hotkey_str = hotkey_str
        self._thread = None
        self._callback = None

    def set_hotkey(self, hotkey_str: str):
        """设置热键字符串（下次 start 生效）"""
        self._hotkey_str = hotkey_str

    def set_callback(self, callback):
        """设置热键触发回调（在主线程执行）"""
        self._callback = callback

    def start(self) -> bool:
        """启动热键监听，返回是否成功注册"""
        self.stop()
        parsed = parse_hotkey(self._hotkey_str)
        if parsed is None:
            return False
        vk, modifiers = parsed
        self._thread = GlobalHotkeyThread(vk, modifiers)
        if self._callback is not None:
            self._thread.hotkey_triggered.connect(self._callback)
        self._thread.start()
        self._thread.wait(500)  # 等待注册结果
        return self._thread.is_registered()

    def stop(self):
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()
