"""
剪贴板报文自动检测模块（系统集成）
==================================
监听系统剪贴板，当用户在其他软件中 Ctrl+C 复制一段十六进制报文时，
自动弹出提示框，点击"解析"即转入解析器。

原理：QClipboard.dataChanged 信号（Windows 底层 WM_CLIPBOARDUPDATE，
即使主窗口在托盘也生效）。去抖 + 校验 hex，避免自身复制触发。

使用：
    monitor = ClipboardMonitor()
    monitor.hex_ready.connect(callback)   # 参数 (bytes, hex_str, detected_protocol)
    monitor.start()
"""
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

# 连续两次相同内容的最小间隔（毫秒）。仅防单次复制的重复 dataChanged 事件，
# 不能太长，否则用户关闭提示框后再次复制同一报文会被吞掉
DEDUP_MS = 250
# 复制后延迟校验，等待剪贴板完全写入
READ_DELAY_MS = 120
# 报文最小字节数（过短不弹）
MIN_BYTES = 4


def detect_protocol(frame: bytes) -> int:
    """从字节特征快速识别协议索引（与 protocol_combo 一致）

    启发式规则：
    - ED..EF..EE 监控封装           → 9 (新一代载波)
    - 68 xx ... 68 控 ... CS 16     → 6 (DLT645)
    - 68 xx .. .. 16 (FT1.2)        → 0 (南网) 或 7 (国网)，默认 0
    - 7E ... 7E                     → 2 (HDLC/DLMS)
    - 其他                           → None（由用户选择）
    """
    n = len(frame)
    if n < 4:
        return None
    # ED..EF..EE 监控封装（PLC2.0 收发机格式）→ 新一代载波
    if frame[0] == 0xED and n >= 8 and frame[5] == 0xEF and frame[-1] == 0xEE:
        return 9
    # 68 开头 FT1.2 帧
    if frame[0] == 0x68 and frame[-1] == 0x16 and n >= 10:
        # DLT645：帧起始符 68 出现在字节 0 和 7
        if frame[7] == 0x68:
            return 6
        return 0  # 南网协议（国网 7 需看 AFN，默认南网，弹窗可切）
    # HDLC：7E 开头
    if frame[0] == 0x7E:
        return 2
    return None


class ClipboardMonitor(QObject):
    """剪贴板监听：检测到 hex 报文时发信号"""

    # (frame_bytes: bytes, hex_str: str, protocol_index: int|None)
    hex_ready = Signal(bytes, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_content = ""
        self._last_time = 0
        self._enabled = True

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def start(self):
        """开始监听剪贴板"""
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        clip.dataChanged.connect(self._on_data_changed)

    def stop(self):
        clip = QGuiApplication.clipboard()
        if clip is not None:
            try:
                clip.dataChanged.disconnect(self._on_data_changed)
            except Exception:
                pass

    def _on_data_changed(self):
        """剪贴板变化：延迟读取 + 校验 hex"""
        if not self._enabled:
            return
        # 延迟读取，等待剪贴板内容写入完成
        QTimer.singleShot(READ_DELAY_MS, self._check_clipboard)

    def _check_clipboard(self):
        if not self._enabled:
            return
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = clip.text() or ""
        text = text.strip()

        # 去抖：内容相同且时间过近则忽略
        import time
        now = time.time() * 1000
        if text == self._last_content and (now - self._last_time) < DEDUP_MS:
            return

        self._last_content = text
        self._last_time = now

        # 严格校验：除 16 进制字符 + 分隔符外，出现任何其他字符则不触发
        clean = strict_hex(text)
        if clean is None:
            return

        nbytes = len(clean) // 2
        if nbytes < MIN_BYTES:
            return

        try:
            frame = bytes.fromhex(clean)
        except Exception:
            return
        proto = detect_protocol(frame)
        self.hex_ready.emit(frame, clean, proto)


def strict_hex(text: str):
    """严格校验：内容必须纯 16 进制字符 + 分隔符（空格/逗号/0x前缀/换行）

    出现任何非 16 进制字符（如字母 G、中文、标点）→ 返回 None 不触发。
    有效则返回清洗后的 hex 字符串（仅 16 进制字符）。
    """
    import re
    # 允许的分隔符：空格、逗号、句点、连字符、换行、制表符、0x/0X 前缀
    # 先移除 0x/0X 前缀
    work = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', text)
    # 剩余字符必须是 16 进制字符 或 分隔符
    sep = set(' ,.-_\t\n\r;:')
    for ch in work:
        if ch in '0123456789abcdefABCDEF':
            continue
        if ch in sep:
            continue
        return None  # 出现非 hex 非分隔符 → 不触发
    clean = re.sub(r'[^0-9A-Fa-f]', '', work)
    if not clean or len(clean) % 2 != 0:
        return None
    return clean
