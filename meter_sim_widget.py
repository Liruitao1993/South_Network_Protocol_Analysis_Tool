# -*- coding: utf-8 -*-
"""虚拟表 Tab（协议8 DL/T 698.45 从站模拟器）。

两种模式：
- 离线模拟：粘贴主站请求帧 hex → 生成响应帧（表格回读解析 + hex 复制）
- 串口从站：独立串口持续监听 698 请求帧，自动组帧回复（建议配虚拟串口对）

档案数据 meter_sim_data.json（OI→A-XDR 数据）可在「档案数据」页增删改、导入导出。
核心逻辑在 meter_sim 包（不依赖 Qt）。
"""

from atomic_io import atomic_write_json
import json
import time
from collections import deque
from typing import Optional

import serial
import serial.tools.list_ports
import sta_reset
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidgetItem, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

import app_paths
import thread_registry
from gui_utils import ZoomableTableWidget, set_btn, set_btn_icon
from meter_sim import MeterSimEngine, SimOptions, load_archive
from meter_sim import dynamic_data, link_layer
from dl_t698_45_parser import DLT69845Parser

SETTINGS_FILE = "meter_sim_settings.json"


def _clean_hex(text: str) -> str:
    """清洗 hex 输入：去空格/换行/0x 前缀等非 hex 字符。"""
    out = []
    for ch in text.strip():
        if ch in "0123456789abcdefABCDEF":
            out.append(ch)
    return "".join(out)


class SerialSlaveThread(QThread):
    """串口从站监听线程：收字节流 → 提帧 → 引擎处理 → 回写响应。"""

    log = Signal(str)
    frame_exchanged = Signal(str, list)  # 请求hex, 响应帧hex列表

    def __init__(self, port: str, baud: int, parity: str, stopbits: float,
                 engine_factory, options_factory=None, parent=None):
        super().__init__(parent)
        self._port, self._baud = port, baud
        self._parity, self._stopbits = parity, stopbits
        self._engine_factory = engine_factory
        self._options_factory = options_factory
        self._engine = None      # 复用引擎，保住 start_time（电能递增按运行时长）
        self._running = False
        self._tx: "deque[bytes]" = deque()   # 待下发帧（STA 复位等主动命令）
        thread_registry.track(self, "MeterSimSerialSlave")

    def send_frame(self, frame: bytes):
        """排队一帧由从站线程写入串口（线程独占串口句柄，不能从 GUI 线程直写）。"""
        self._tx.append(bytes(frame))

    def _handle_645(self, frame: bytes, ser, resps_out: list):
        """处理 645 帧（与 698 同总线时出现，如「STA 硬件初始化」广播）。"""
        info = sta_reset.parse_frame(frame)
        if info is None:
            self.log.emit(f"← 收到 645 帧({len(frame)}B，非本工具处理类型): "
                          f"{frame.hex(' ')}")
            return
        self.log.emit(f"← 收到 645 帧({len(frame)}B): {frame.hex(' ')}")
        self.log.emit(f"  {sta_reset.describe(frame)}")
        if info["broadcast"]:
            # 645 广播命令不要求从站应答（以前会把这种帧当 698 巨帧卡死收帧）
            self.log.emit("  → 广播复位命令：按 645「广播不要求应答」静默忽略")
            return
        rsp = sta_reset.build_ack_frame(frame)
        ser.write(rsp)
        resps_out.append(rsp.hex(" "))
        self.log.emit(f"→ 回复({len(rsp)}B): {rsp.hex(' ')}")

    def _engine_for_frame(self):
        """取引擎：首次创建，之后只刷新选项（选项实时生效、运行时长不清零）。"""
        if self._engine is None:
            self._engine = self._engine_factory()
        elif self._options_factory is not None:
            self._engine.options = self._options_factory()
        return self._engine

    def run(self):
        try:
            ser = serial.Serial()
            ser.port = self._port
            ser.baudrate = self._baud
            ser.parity = self._parity
            ser.stopbits = self._stopbits
            ser.timeout = 0.2
            ser.open()
        except Exception as e:
            self.log.emit(f"❌ 串口打开失败: {e}")
            return
        self._running = True
        self.log.emit(f"● 从站监听已启动 {self._port}@{self._baud}")
        buf = b""
        try:
            while self._running:
                try:
                    n = ser.in_waiting
                    if n:
                        buf += ser.read(n)
                    else:
                        time.sleep(0.05)
                        # 缓冲无新数据也尝试提帧（处理末尾帧）
                    while self._tx:
                        try:
                            out = self._tx.popleft()
                            ser.write(out)
                            self.log.emit(f"⇱ 已下发({len(out)}B): {out.hex(' ')}")
                        except Exception as e:
                            self.log.emit(f"❌ 下发失败: {e}")
                    # 先摘出 645 帧（STA 复位等），否则会被当 698 巨帧卡住收帧
                    for f645 in link_layer.extract_645_frames(buf):
                        handled = []
                        self._handle_645(f645, ser, handled)
                        buf = buf.replace(f645, b"", 1)
                    frames, consumed, rest = link_layer.extract_frames(buf)
                    if frames:
                        buf = rest if rest is not None else b""
                        for frame in frames:
                            engine = self._engine_for_frame()
                            resps = engine.handle_frame(frame)
                            for msg in engine.logs:
                                self.log.emit("  " + msg)
                            req_hex = frame.hex(" ")
                            # 整帧完整打印（含 16 帧尾与 FCS/HCS 校验位），不再截断
                            self.log.emit(f"← 收到请求({len(frame)}B): {req_hex}")
                            resp_hexes = []
                            for r in resps:
                                try:
                                    ser.write(r)
                                    resp_hexes.append(r.hex(" "))
                                    self.log.emit(
                                        f"→ 回复({len(r)}B): {r.hex(' ')}")
                                except Exception as e:
                                    self.log.emit(f"❌ 回复发送失败: {e}")
                            self.frame_exchanged.emit(req_hex, resp_hexes)
                except Exception as e:
                    self.log.emit(f"❌ 监听异常: {e}")
                    time.sleep(0.2)
        finally:
            try:
                ser.close()
            except Exception:
                pass
            self.log.emit("○ 从站监听已停止")

    def stop(self):
        self._running = False


class VirtualMeterWidget(QWidget):
    """虚拟表主组件（独立 tab，协议8 可见）。"""

    parse_requested = Signal(str)  # 请求主窗口把 hex 送单帧解析器回读


    def __init__(self, parent=None):
        super().__init__(parent)
        self.archive = load_archive()
        self.options = self._load_settings()
        self._serial_thread: Optional[SerialSlaveThread] = None
        self.parser = DLT69845Parser()
        self._build_ui()
        self._refresh_archive_table()
        self._refresh_ports()
        self._update_addr_status()

    # ── UI 构建 ───────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_run_tab(), "运行")
        self.tabs.addTab(self._build_archive_tab(), "档案数据")
        self.tabs.addTab(self._build_settings_tab(), "模拟设置")

    def _build_run_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        # 虚拟表地址区（决定响应帧 SA 与通信地址/表号的回值）
        grp_addr = QGroupBox("虚拟表地址（响应帧 SA 与通信地址/表号的回值）")
        gal = QHBoxLayout(grp_addr)
        self.addr_edit = QLineEdit(self.options.meter_address or "")
        self.addr_edit.setPlaceholderText("12 位数字，如 000000000123（留空＝用档案表号）")
        self.addr_edit.setMaximumWidth(180)
        self.addr_edit.setToolTip(
            "本机模拟的电表通信地址（12 位十进制数字）。\n"
            "影响：响应帧 SA、4001/4002/202a 通信地址回值、通配/广播请求的应答地址。\n"
            "留空则取「档案数据」里 40020200 表号（当前值见右侧提示）。")
        self.addr_edit.editingFinished.connect(self._apply_address)
        self.addr_status = QLabel()
        self.addr_status.setWordWrap(True)
        gal.addWidget(QLabel("虚拟表地址"))
        gal.addWidget(self.addr_edit)
        gal.addWidget(self.addr_status, 1)
        layout.addWidget(grp_addr)

        # 模组复位（代替上下电）
        grp_rst = QGroupBox("被测模组复位（STA 硬件初始化，645 广播，用于代替上下电）")
        grl = QHBoxLayout(grp_rst)
        self.btn_sta_reset = QPushButton("下发 STA 复位")
        set_btn(self.btn_sta_reset, "ghost", "sm")
        set_btn_icon(self.btn_sta_reset, "apply")
        self.btn_sta_reset.setToolTip(
            "向总线广播 DL/T 645 写数据命令（DI 04A00401）：\n"
            "68 AA AA AA AA AA AA 68 14 0C … DA 16\n"
            "模组固定在工装底座无法断电时，用它代替上下电。")
        self.btn_sta_reset.clicked.connect(self._send_sta_reset)
        self.lbl_sta_frame = QLabel(sta_reset.build_frame().hex(" "))
        self.lbl_sta_frame.setWordWrap(True)
        self.lbl_sta_frame.setStyleSheet("font-family: Consolas, monospace;")
        grl.addWidget(self.btn_sta_reset)
        grl.addWidget(self.lbl_sta_frame, 1)
        layout.addWidget(grp_rst)

        # 串口从站区
        grp = QGroupBox("串口从站（独立串口，建议使用虚拟串口对，如 VSPD/com0com）")
        gl = QHBoxLayout(grp)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(110)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "115200"])
        self.baud_combo.setCurrentText("115200")
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["N", "E", "O"])
        self.stop_combo = QComboBox()
        self.stop_combo.addItems(["1", "2"])
        btn_refresh = QPushButton("刷新")
        set_btn(btn_refresh, "ghost", "sm")
        btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_serial = QPushButton("开始监听")
        set_btn(self.btn_serial, "primary", "sm")
        set_btn_icon(self.btn_serial, "play")
        self.btn_serial.clicked.connect(self._toggle_serial)
        self.serial_status = QLabel("○ 未启动")
        for w in (QLabel("端口"), self.port_combo, QLabel("波特率"),
                  self.baud_combo, QLabel("校验"), self.parity_combo,
                  QLabel("停止位"), self.stop_combo, btn_refresh,
                  self.btn_serial, self.serial_status):
            gl.addWidget(w)
        gl.addStretch(1)
        layout.addWidget(grp)

        # 离线模拟区
        grp2 = QGroupBox("离线模拟（输入主站请求帧 hex，生成虚拟表响应）")
        gl2 = QVBoxLayout(grp2)
        self.req_input = QPlainTextEdit()
        self.req_input.setPlaceholderText(
            "粘贴 698 请求帧 hex，如：\n"
            "68 17 00 43 05 01 02 03 04 05 06 00 ... 16\n"
            "可点「示例」填入读取电压请求")
        self.req_input.setMaximumHeight(90)
        self.req_input.setLineWrapMode(QPlainTextEdit.NoWrap)
        gl2.addWidget(self.req_input)
        row = QHBoxLayout()
        btn_example = QPushButton("示例")
        btn_gen = QPushButton("生成响应")
        btn_copy = QPushButton("复制响应hex")
        btn_parse = QPushButton("送单帧解析器回读")
        set_btn(btn_example, "ghost", "sm")
        set_btn(btn_gen, "primary", "sm")
        set_btn(btn_copy, "ghost", "sm")
        set_btn(btn_parse, "ghost", "sm")
        set_btn_icon(btn_gen, "apply")
        btn_example.clicked.connect(self._fill_example)
        btn_gen.clicked.connect(self._offline_generate)
        btn_copy.clicked.connect(self._copy_response)
        btn_parse.clicked.connect(self._send_to_parser)
        for b in (btn_example, btn_gen, btn_copy, btn_parse):
            row.addWidget(b)
        row.addStretch(1)
        gl2.addLayout(row)
        layout.addWidget(grp2)

        # 日志
        layout.addWidget(QLabel("收发日志（整帧完整 hex，含 HCS/FCS 与 16 帧尾）："))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)  # 长帧单行 + 横向滚动
        self.log_view.setStyleSheet("font-family: Consolas, monospace;")
        layout.addWidget(self.log_view)

        # 响应解析表
        layout.addWidget(QLabel("最近响应帧解析："))
        self.resp_table = ZoomableTableWidget()
        self.resp_table.setColumnCount(4)
        self.resp_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        self.resp_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.resp_table, 1)

        self._last_response_hex = ""
        return page

    def _build_archive_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        tip = QLabel("档案数据：key=OI+属性+索引（冻结键形如 50040200_20210200）；"
                     "数据hex 为 A-XDR 编码属性值。改动后点「保存」持久化。")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self.archive_table = ZoomableTableWidget()
        self.archive_table.setColumnCount(7)
        self.archive_table.setHorizontalHeaderLabels(
            ["key", "OI", "属性", "索引", "名称", "数据hex", "解码预览"])
        self.archive_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.archive_table, 1)
        row = QHBoxLayout()
        for text, slot, kind in (
                ("新增行", self._archive_add, "primary"),
                ("删除选中行", self._archive_delete, "danger"),
                ("刷新解码预览", self._archive_refresh_preview, "ghost"),
                ("保存", self._archive_save, "primary"),
                ("导入JSON", self._archive_import, "ghost"),
                ("导出JSON", self._archive_export, "ghost")):
            b = QPushButton(text)
            set_btn(b, kind, "sm")
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        box = QGroupBox("模拟设置")
        grid = QGridLayout(box)

        self.spin_meter_count = QSpinBox()
        self.spin_meter_count.setRange(1, 200)
        self.spin_meter_count.setValue(self.options.meter_count)
        self.spin_meter_count.setToolTip(
            "通配地址请求（如 AA×6 读通信地址）回几块表：1 = 只回本机虚拟地址。")
        self.chk_strict = QCheckBox("仅应答本机地址（关闭则任意单地址请求也应答）")
        self.chk_strict.setChecked(self.options.strict_address)
        self.chk_strict.setToolTip(
            "勾选：单地址请求只有 SA 等于本机虚拟地址（或命中白名单）才回复。\n"
            "关闭：任意单地址请求都回复，兼容旧行为。\n"
            "通配地址、全 99 / 全 AA 广播地址、白名单地址无论开关如何都应答。")
        self.chk_energy = QCheckBox("正向有功电能(00100200)随运行时间递增")
        self.chk_energy.setChecked(self.options.energy_increase)
        self.chk_freeze = QCheckBox("日/月/曲线冻结自动时标（按请求 Selector 时间）")
        self.chk_freeze.setChecked(self.options.auto_freeze_time)
        self.chk_mac = QCheckBox("明文安全请求回复附加 MAC(0A0B0C0D)")
        self.chk_mac.setChecked(self.options.mac_enabled)

        grid.addWidget(QLabel("通配地址模拟表数量："), 0, 0)
        grid.addWidget(self.spin_meter_count, 0, 1)
        grid.addWidget(QLabel("（1 = 只回本机虚拟地址）"), 0, 2, 1, 2)
        grid.addWidget(self.chk_strict, 1, 0, 1, 4)
        grid.addWidget(self.chk_energy, 2, 0, 1, 3)
        grid.addWidget(self.chk_freeze, 3, 0, 1, 3)
        grid.addWidget(self.chk_mac, 4, 0, 1, 3)

        grid.addWidget(QLabel("名单模式："), 5, 0)
        self.list_mode = QComboBox()
        self.list_mode.addItems(["未启用", "黑名单", "白名单"])
        if self.options.whitelist:
            self.list_mode.setCurrentIndex(2)
        elif self.options.blacklist:
            self.list_mode.setCurrentIndex(1)
        grid.addWidget(self.list_mode, 5, 1)
        grid.addWidget(QLabel("地址表（/ 分隔，反转 hex，如 060504030201）："), 6, 0)
        self.list_edit = QPlainTextEdit()
        self.list_edit.setMaximumHeight(60)
        existing = self.options.blacklist or self.options.whitelist
        self.list_edit.setPlainText("/".join(existing))
        grid.addWidget(self.list_edit, 6, 1, 1, 2)

        self.chk_leak = QCheckBox("曲线冻结漏点时段（时段内曲线记录返回0行）")
        self.chk_leak.setChecked(self.options.leak_window is not None)
        grid.addWidget(self.chk_leak, 7, 0, 1, 3)
        self.time_from = QTimeEdit()
        self.time_to = QTimeEdit()
        self.time_from.setDisplayFormat("HH:mm")
        self.time_to.setDisplayFormat("HH:mm")
        if self.options.leak_window:
            f, t = self.options.leak_window
            self.time_from.setTime(self.time_from.time().addSecs(f * 60))
            self.time_to.setTime(self.time_to.time().addSecs(t * 60))
        grid.addWidget(QLabel("从"), 8, 0)
        grid.addWidget(self.time_from, 8, 1)
        grid.addWidget(QLabel("到"), 8, 2)
        grid.addWidget(self.time_to, 8, 3)

        btn_save = QPushButton("保存设置")
        set_btn(btn_save, "primary", "sm")
        set_btn_icon(btn_save, "save")
        btn_save.clicked.connect(self._save_settings)
        grid.addWidget(btn_save, 9, 0)
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    # ── 引擎 ──────────────────────────────────────────────
    def send_sta_reset_frame(self, frame: bytes) -> bool:
        """外部（国网协议测试页的流程测试）要求下发 STA 复位。

        只负责把帧排进从站线程的发送队列；串口未监听时返回 False，让调用方退回其它通道。
        """
        th = self._serial_thread
        if th is None or not th.isRunning():
            return False
        th.send_frame(frame)
        self._log(f"⇱ 已排队下发 STA 硬件初始化（复位）: {bytes(frame).hex(' ')}")
        return True

    def _send_sta_reset(self):
        """下发 STA 硬件初始化（复位）广播帧，代替给模组上下电。"""
        frame = sta_reset.build_frame()
        th = self._serial_thread
        if th is None or not th.isRunning():
            self._log("  （串口未监听，未下发；请先点「开始监听」，"
                      f"或复制此帧到串口工具发送：{frame.hex(' ')}）")
            QMessageBox.information(
                self, "提示",
                "虚拟表串口尚未监听。\n\n可先点「开始监听」再下发，"
                "或用串口工具直接发送：\n" + frame.hex(" ").upper())
            return
        th.send_frame(frame)
        self._log(f"⇱ 已排队下发 STA 硬件初始化（复位）: {frame.hex(' ')}")

    def _address_value(self) -> Optional[str]:
        """虚拟表地址设置值（未填/非法返回 None = 用档案表号）。"""
        return dynamic_data.normalize_address(self.addr_edit.text()) or None

    def _current_options(self) -> SimOptions:
        mode = self.list_mode.currentIndex()
        addrs = [a.strip() for a in self.list_edit.toPlainText()
                 .replace("\n", "/").split("/") if a.strip()]
        return SimOptions(
            meter_count=self.spin_meter_count.value(),
            meter_address=self._address_value(),
            strict_address=self.chk_strict.isChecked(),
            blacklist=addrs if mode == 1 else [],
            whitelist=addrs if mode == 2 else [],
            energy_increase=self.chk_energy.isChecked(),
            auto_freeze_time=self.chk_freeze.isChecked(),
            leak_window=((self.time_from.time().hour() * 60
                          + self.time_from.time().minute(),
                          self.time_to.time().hour() * 60
                          + self.time_to.time().minute())
                         if self.chk_leak.isChecked() else None),
            mac_enabled=self.chk_mac.isChecked(),
        )

    def _make_engine(self) -> MeterSimEngine:
        return MeterSimEngine(self.archive, self._current_options())

    def _apply_address(self):
        """地址编辑完成：规范成 12 位数字并落盘；非法回退并提示。"""
        raw = self.addr_edit.text().strip()
        if not raw:
            self.options.meter_address = None
            self._update_addr_status()
            self._persist_settings()
            self._log("虚拟表地址已清空：改用档案表号")
            return
        addr = dynamic_data.normalize_address(raw)
        if not addr:
            QMessageBox.warning(
                self, "虚拟表地址无效",
                f"「{raw}」不是 12 位以内的十进制数字地址。\n\n"
                "请填 12 位数字表地址（如 000000000123）；留空表示用档案表号。")
            self.addr_edit.setText(self.options.meter_address or "")
            return
        self.options.meter_address = addr
        self.addr_edit.setText(addr)
        self._update_addr_status()
        self._persist_settings()
        self._log(f"● 虚拟表地址已设为 {addr}（响应帧 SA / 通信地址回值同步生效）")

    def _update_addr_status(self):
        """显示当前实际生效的应答地址（设置值或档案表号）。"""
        try:
            addr = self._make_engine().own_address()
        except Exception:
            addr = "—"
        src = "设置值" if self._address_value() else "档案 40020200 表号"
        self.addr_status.setText(f"当前应答地址：{addr}（{src}）")

    # ── 串口 ──────────────────────────────────────────────
    def _refresh_ports(self):
        self.port_combo.clear()
        for p in serial.tools.list_ports.comports():
            self.port_combo.addItem(p.device)

    def _toggle_serial(self):
        if self._serial_thread and self._serial_thread.isRunning():
            self._serial_thread.stop()
            self._serial_thread.wait(2000)
            self._serial_thread = None
            self.btn_serial.setText("开始监听")
            set_btn_icon(self.btn_serial, "play")
            self.serial_status.setText("○ 未启动")
            return
        if not self.port_combo.currentText():
            QMessageBox.warning(self, "提示", "未选择串口")
            return
        parity_map = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
                      "O": serial.PARITY_ODD}
        stop = float(self.stop_combo.currentText())
        self._serial_thread = SerialSlaveThread(
            self.port_combo.currentText(), int(self.baud_combo.currentText()),
            parity_map[self.parity_combo.currentText()], stop,
            self._make_engine, self._current_options, self)
        self._serial_thread.log.connect(self._log)
        self._serial_thread.frame_exchanged.connect(self._on_exchanged)
        self._serial_thread.start()
        self.btn_serial.setText("停止监听")
        set_btn_icon(self.btn_serial, "stop")
        self.serial_status.setText("● 监听中")

    # ── 离线 ──────────────────────────────────────────────
    def _fill_example(self):
        # 读取电压(20000200) 的 GetRequestNormal，SA=05 010203040506
        from dl_t698_45_frame_gen import DLT69845FrameGenerator
        sa = bytes([0x05, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06])
        frame = DLT69845FrameGenerator().generate_get_request_normal(
            sa, 0, 0x01, bytes.fromhex("20000200"))
        self.req_input.setPlainText(frame.hex(" "))

    def _offline_generate(self):
        hextext = _clean_hex(self.req_input.toPlainText())
        if len(hextext) < 40:
            QMessageBox.warning(self, "提示", "请输入完整请求帧 hex")
            return
        try:
            frame = bytes.fromhex(hextext)
        except ValueError:
            QMessageBox.warning(self, "提示", "hex 格式错误")
            return
        frames, _, _ = link_layer.extract_frames(frame)
        if not frames:
            self._log("❌ 未从输入中提取到合法 68...16 帧")
            QMessageBox.warning(self, "提示", "未找到合法 698 帧（68 起 16 止）")
            return
        engine = self._make_engine()
        all_resp = []
        for f in frames:
            for msg in engine.logs:
                self._log("  " + msg)
            self._log(f"← 请求({len(f)}B): {f.hex(' ')}")
            resps = engine.handle_frame(f)
            for r in resps:
                self._log(f"→ 响应({len(r)}B): {r.hex(' ')}")
            all_resp.extend(resps)
        if not all_resp:
            self._log("⚠ 引擎未生成响应（名单过滤/不支持服务/未知请求）")
            QMessageBox.information(self, "提示", "未生成响应，请查看日志")
            return
        self._last_response_hex = "\n".join(r.hex(" ") for r in all_resp)
        self._log(f"← 请求 {len(frames)} 帧 → 回复 {len(all_resp)} 帧")
        self._show_response(all_resp[0])

    def _show_response(self, frame: bytes):
        try:
            rows = self.parser.parse_to_table(frame)
        except Exception as e:
            self._log(f"❌ 响应回读解析异常: {e}")
            rows = []
        self.resp_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c in range(min(4, len(r))):
                self.resp_table.setItem(i, c, QTableWidgetItem(str(r[c])))

    def _on_exchanged(self, req_hex: str, resp_hexes: list):
        if resp_hexes:
            self._last_response_hex = "\n".join(resp_hexes)
            try:
                self._show_response(bytes.fromhex(resp_hexes[0].replace(" ", "")))
            except ValueError:
                pass

    def _copy_response(self):
        if not self._last_response_hex:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._last_response_hex)
        self._log("已复制响应 hex 到剪贴板")

    def _send_to_parser(self):
        """把响应 hex 送到主窗口单帧解析（由 main_gui 连接）。"""
        if self._last_response_hex and hasattr(self, "parse_requested"):
            self.parse_requested.emit(self._last_response_hex.split("\n")[0])

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {msg}")

    # ── 档案表 ────────────────────────────────────────────
    def _refresh_archive_table(self):
        items = self.archive.items
        self.archive_table.setRowCount(len(items))
        for i, it in enumerate(items):
            vals = [it["key"], it["oi"], it["attr"], it["idx"],
                    it.get("name", ""), it.get("data", ""),
                    self._decode_preview(it.get("data", ""))]
            for c, v in enumerate(vals):
                self.archive_table.setItem(i, c, QTableWidgetItem(str(v)))

    def _decode_preview(self, data_hex: str) -> str:
        try:
            from dl_t698_45_axdr import AXDRCoder
            val, _ = AXDRCoder().decode(bytes.fromhex(data_hex))
            s = str(val.get("值", val.get("value", "")))
            return s[:60]
        except Exception:
            return ""

    def _archive_add(self):
        r = self.archive_table.rowCount()
        self.archive_table.insertRow(r)
        for c, v in enumerate(["", "", "", "", "新数据项", "", ""]):
            self.archive_table.setItem(r, c, QTableWidgetItem(v))

    def _archive_delete(self):
        r = self.archive_table.currentRow()
        if r >= 0:
            key_item = self.archive_table.item(r, 0)
            if key_item and key_item.text():
                self.archive.remove(key_item.text())
            self.archive_table.removeRow(r)

    def _archive_refresh_preview(self):
        for r in range(self.archive_table.rowCount()):
            data_item = self.archive_table.item(r, 5)
            if data_item:
                self.archive_table.setItem(
                    r, 6, QTableWidgetItem(self._decode_preview(data_item.text())))

    def _collect_archive_from_table(self):
        items = []
        for r in range(self.archive_table.rowCount()):
            def cell(c):
                it = self.archive_table.item(r, c)
                return it.text().strip() if it else ""
            key = cell(0)
            if not key:
                continue
            items.append(self.archive.make_item(
                key, cell(4) or "自定义", cell(5)))
        return items

    def _archive_save(self):
        self.archive.items = self._collect_archive_from_table()
        self.archive._index = {it["key"].lower(): it for it in self.archive.items}
        path = self.archive.save()
        self._log(f"档案已保存: {path}（{len(self.archive.items)} 条）")
        QMessageBox.information(self, "保存成功", f"档案已保存\n{path}")

    def _archive_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入档案 JSON", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.archive = self.archive.from_json(f.read())
            self._refresh_archive_table()
            self._log(f"已导入档案 {len(self.archive.items)} 条（保存后生效）")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _archive_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出档案 JSON", "meter_sim_data.json", "JSON Files (*.json)")
        if not path:
            return
        items = self._collect_archive_from_table()
        atomic_write_json(path, {"version": 1, "items": items}, indent=1)
        self._log(f"档案已导出: {path}")

    # ── 设置持久化 ────────────────────────────────────────
    def _load_settings(self) -> SimOptions:
        opts = SimOptions()
        try:
            p = app_paths.data_path(SETTINGS_FILE)
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                opts.meter_count = d.get("meter_count", 1)
                opts.energy_increase = d.get("energy_increase", False)
                opts.auto_freeze_time = d.get("auto_freeze_time", True)
                opts.mac_enabled = d.get("mac_enabled", True)
                opts.strict_address = d.get("strict_address", False)
                addr = dynamic_data.normalize_address(d.get("meter_address"))
                opts.meter_address = addr or None
                opts.blacklist = d.get("blacklist", [])
                opts.whitelist = d.get("whitelist", [])
                lw = d.get("leak_window")
                if lw:
                    opts.leak_window = tuple(lw)
        except Exception:
            pass
        return opts

    def _settings_payload(self, opts: SimOptions) -> dict:
        return {
            "meter_count": opts.meter_count,
            "meter_address": opts.meter_address,
            "strict_address": opts.strict_address,
            "energy_increase": opts.energy_increase,
            "auto_freeze_time": opts.auto_freeze_time,
            "mac_enabled": opts.mac_enabled,
            "blacklist": opts.blacklist,
            "whitelist": opts.whitelist,
            "leak_window": opts.leak_window,
        }

    def _persist_settings(self):
        """静默落盘（改地址时即时生效，不弹窗）。"""
        try:
            p = app_paths.data_path(SETTINGS_FILE)
            p.write_text(
                json.dumps(self._settings_payload(self._current_options()),
                           ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception as e:
            self._log(f"⚠ 设置落盘失败: {e}")

    def _save_settings(self):
        opts = self._current_options()
        self.options = opts
        p = app_paths.data_path(SETTINGS_FILE)
        p.write_text(json.dumps(self._settings_payload(opts), ensure_ascii=False,
                                indent=1), encoding="utf-8")
        self._update_addr_status()
        self._log(f"设置已保存: {p}")
        QMessageBox.information(self, "保存成功", "模拟设置已保存")

    # ── 关闭清理 ──────────────────────────────────────────
    def shutdown(self):
        if self._serial_thread and self._serial_thread.isRunning():
            self._serial_thread.stop()
            self._serial_thread.wait(2000)
            self._serial_thread = None
