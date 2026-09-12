# -*- coding: utf-8 -*-
"""DLT645 虚拟表 Tab（协议6 从站模拟器）。

- 离线：粘贴主站读数据请求 → 生成从站响应 → 解析回读 / 复制 hex
- 档案：DI → 可读值表，可编辑保存到 dlt645_sim_data.json
- 串口：独立串口持续监听 68…16 请求并自动回复（建议虚拟串口对）

核心逻辑在 dlt645_sim/（无 Qt）。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

import serial
import serial.tools.list_ports
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import app_paths
import thread_registry
from dlt645_frame_gen import DLT645FrameGenerator, encode_di
from dlt645_parser import DLT645Parser
from dlt645_sim import DLT645MeterSim
from dlt645_sim import lme_query as lme
from dlt645_sim.archive import DLT645Archive
from dlt645_sim.dynamic_data import EVENT_WORD_DI, RandomEventWord
from dlt645_sim.engine import extract_645_frames
from gui_utils import ZoomableTableWidget, set_btn, set_btn_icon

SETTINGS_FILE = "dlt645_sim_data.json"


def _clean_hex(text: str) -> str:
    return "".join(ch for ch in (text or "") if ch in "0123456789abcdefABCDEF")


def _set_item(table, row: int, col: int, text: str, editable: bool = False):
    from PySide6.QtCore import Qt

    item = QTableWidgetItem(text)
    item.setToolTip(text)
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, col, item)


class Dlt645SerialSlaveThread(QThread):
    """645 串口从站：收流提帧 → 引擎应答 → 回写。"""

    log = Signal(str)
    frame_exchanged = Signal(str, list)
    #: 收到 DIR=1（从站/模块发出）的帧：本机作为主站读到模块回包，交由 GUI 解析展示
    slave_frame = Signal(str)

    def __init__(self, port: str, baud: int, parity: str, stopbits: float,
                 engine_factory, parent=None):
        super().__init__(parent)
        self._port, self._baud = port, baud
        self._parity, self._stopbits = parity, stopbits
        self._engine_factory = engine_factory
        self._running = False
        self._ser = None  # run() 打开后赋值；供「离线响应下发到串口」写入
        self._write_lock = threading.Lock()
        thread_registry.track(self, "DLT645SimSerialSlave")

    def run(self):
        try:
            ser = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                parity=self._parity,
                stopbits=self._stopbits,
                timeout=0.2,
            )
        except Exception as e:
            self.log.emit(f"❌ 串口打开失败: {e}")
            return
        self._running = True
        self._ser = ser
        self.log.emit(f"● 645 从站监听已启动 {self._port}@{self._baud}")
        buf = b""
        try:
            while self._running:
                try:
                    n = ser.in_waiting
                    if n:
                        buf += ser.read(n)
                    else:
                        time.sleep(0.05)
                    frames = extract_645_frames(buf)
                    if frames:
                        consumed = sum(len(fr) for fr in frames)
                        buf = buf[consumed:]
                        for frame in frames:
                            req_hex = frame.hex(" ")
                            # ctrl 在 idx8；D7=1 表示帧由从站/模块发出 → 这是模块回包，
                            # 不是发给本虚拟表的请求，直接上报（不再回「非主站帧，忽略」）
                            if len(frame) > 8 and (frame[8] & 0x80):
                                self.log.emit(f"◀ 模块回包: {req_hex[:80]}")
                                self.slave_frame.emit(req_hex)
                                continue
                            engine = self._engine_factory()
                            resps = engine.handle_frame(frame)
                            self.log.emit(f"← 请求: {req_hex[:80]}")
                            if engine.last_note:
                                self.log.emit(f"  ◈ {engine.last_note}")
                            if engine.last_error:
                                self.log.emit(f"  ⚠ {engine.last_error}")
                            resp_hexes = []
                            for r in resps:
                                try:
                                    ser.write(r)
                                    resp_hexes.append(r.hex(" "))
                                    self.log.emit(f"→ 回复: {r.hex(' ')[:80]}")
                                except Exception as e:
                                    self.log.emit(f"❌ 回复失败: {e}")
                            self.frame_exchanged.emit(req_hex, resp_hexes)
                except Exception as e:
                    self.log.emit(f"❌ 监听异常: {e}")
                    time.sleep(0.2)   # 退避：持续读异常（如拔线）时避免热循环刷日志
        finally:
            self._ser = None
            try:
                ser.close()
            except Exception:
                pass
            self.log.emit("○ 645 从站监听已停止")

    def write_frame(self, data: bytes):
        """把一帧写入串口（GUI 线程调用）。返回 None=成功，str=错误信息。

        与 run() 的读循环并发：pyserial 全双工、读写各自缓冲，加锁仅护 write。
        """
        ser = self._ser
        if ser is None or not self._running:
            return "串口未在监听（请先点「开始监听」）"
        try:
            with self._write_lock:
                ser.write(data)
            return None
        except Exception as e:
            return str(e)

    def stop(self):
        self._running = False


class Dlt645VirtualMeterWidget(QWidget):
    """协议6「DLT645虚拟表」组件。"""

    parse_requested = Signal(str)
    address_written = Signal(str)  # 15H 主站写表地址成功（跨线程安全，跳回 GUI）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.address = "000000000000"
        self.archive = DLT645Archive()
        #: 事件状态字随机源：引擎每帧重建，故由本组件持有（见 dlt645_sim/dynamic_data.py）
        self._event_word = RandomEventWord()
        self._random_event = False
        self._load_archive_file()
        self.parser = DLT645Parser()
        self._serial_thread: Optional[Dlt645SerialSlaveThread] = None
        self._last_response_hex = ""
        self._last_response_frames: list[bytes] = []
        self._build_ui()
        self._refresh_ports()  # 构造即填充端口列表（此前从未调用，下拉永远为空）
        self._refresh_archive_table()
        self.address_written.connect(self._apply_written_address)

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_run_tab(), "运行")
        self.tabs.addTab(self._build_archive_tab(), "档案数据")

    def _build_run_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        grp = QGroupBox("串口从站（独立串口，建议虚拟串口对）")
        gl = QHBoxLayout(grp)
        gl.addWidget(QLabel("表地址"))
        self.addr_edit = QLineEdit(self.address)
        self.addr_edit.setFixedWidth(120)
        self.addr_edit.setMaxLength(14)
        self.addr_edit.setToolTip(
            "12 位十六进制电表通信地址（A0-A5）。\n"
            "影响：示例请求帧地址、响应帧地址、档案保存/导出。\n"
            "广播：999999999999（校时）/ AAAAAAAAAAAA（读地址）。\n"
            "离线与串口应答均实时生效。"
        )
        self.addr_edit.editingFinished.connect(self._on_addr_edited)
        gl.addWidget(self.addr_edit)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(110)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(
            ["1200", "2400", "4800", "9600", "19200", "38400", "115200"]
        )
        self.baud_combo.setCurrentText("9600")
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
        for w in (
            QLabel("端口"), self.port_combo, QLabel("波特率"), self.baud_combo,
            QLabel("校验"), self.parity_combo, QLabel("停止位"), self.stop_combo,
            btn_refresh, self.btn_serial, self.serial_status,
        ):
            gl.addWidget(w)
        gl.addStretch(1)
        layout.addWidget(grp)

        layout.addWidget(self._build_sim_settings_group())

        layout.addWidget(self._build_lme_group())

        grp2 = QGroupBox("离线模拟（主站请求 hex → 虚拟表响应）")
        gl2 = QVBoxLayout(grp2)
        self.req_input = QPlainTextEdit()
        self.req_input.setPlaceholderText(
            "粘贴 645 主站读数据请求，如：\n"
            "68 00 00 00 00 00 00 68 11 04 33 33 34 33 E5 16\n"
            "（读正向有功总电能 00010000，地址全 0）"
        )
        self.req_input.setMaximumHeight(90)
        self.req_input.setLineWrapMode(QPlainTextEdit.NoWrap)
        gl2.addWidget(self.req_input)
        row = QHBoxLayout()
        btn_example = QPushButton("示例")
        btn_gen = QPushButton("生成响应")
        btn_copy = QPushButton("复制响应hex")
        btn_parse = QPushButton("送单帧解析器回读")
        btn_send = QPushButton("下发响应到串口")
        set_btn(btn_example, "ghost", "sm")
        set_btn(btn_gen, "primary", "sm")
        set_btn(btn_copy, "ghost", "sm")
        set_btn(btn_parse, "ghost", "sm")
        set_btn(btn_send, "success", "sm")
        set_btn_icon(btn_gen, "apply")
        set_btn_icon(btn_send, "play")
        btn_send.setToolTip(
            "把「生成响应」得到的虚拟表应答帧真实写入串口 TX。\n"
            "用于向主站/集中器注入指定报文（需先在上方「开始监听」占用串口）。"
        )
        btn_example.clicked.connect(self._fill_example)
        btn_gen.clicked.connect(self._offline_generate)
        btn_copy.clicked.connect(self._copy_response)
        btn_parse.clicked.connect(self._send_to_parser)
        btn_send.clicked.connect(self._send_response_to_serial)
        for b in (btn_example, btn_gen, btn_copy, btn_parse, btn_send):
            row.addWidget(b)
        row.addStretch(1)
        gl2.addLayout(row)
        layout.addWidget(grp2)

        layout.addWidget(QLabel("收发日志："))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(140)
        self.log_view.setStyleSheet("font-family: Consolas, monospace;")
        layout.addWidget(self.log_view)

        layout.addWidget(QLabel("最近响应帧解析："))
        self.resp_table = ZoomableTableWidget()
        self.resp_table.setColumnCount(4)
        self.resp_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        self.resp_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.resp_table, 1)
        return page

    # ── 模拟设置（事件状态字随机变化等）────────────────────────────────
    def _build_sim_settings_group(self) -> QGroupBox:
        grp = QGroupBox("模拟设置")
        gl = QVBoxLayout(grp)
        row = QHBoxLayout()
        self.chk_random_event = QCheckBox("随机产生事件")
        self.chk_random_event.setChecked(self._random_event)
        self.chk_random_event.setToolTip(
            f"勾选后每次读取事件状态字（DI {EVENT_WORD_DI} 主动上报状态字，12 字节）\n"
            "都返回一个新的随机值，且与上一次不同；\n"
            "不勾选时读「档案数据」中的值（默认 12 字节全 0 = 无事件，次次相同）。"
        )
        self.chk_random_event.toggled.connect(self._on_random_event_toggled)
        row.addWidget(self.chk_random_event)
        hint = QLabel(
            f"每次读取 {EVENT_WORD_DI}（主动上报状态字 / 事件状态字）返回新的随机 12 字节值；"
            "不勾选时读档案值（默认全 0，不变化）。离线与串口应答均生效。"
        )
        hint.setWordWrap(True)
        row.addWidget(hint, 1)
        gl.addLayout(row)
        return grp

    def _on_random_event_toggled(self, checked: bool):
        self._random_event = bool(checked)
        self._event_word.reset()   # 清「上次值」记忆，避免与新开启的序列比较
        self.log_view.appendPlainText(
            f"● 随机产生事件：{'开启' if checked else '关闭'}"
            + (f"（每次读 {EVENT_WORD_DI} 随机变化）" if checked else "（读档案值）"))
        self._archive_save_quiet()

    # ── 模块版本查询（LME 自定义下发，主站方向）─────────────────────────
    def _build_lme_group(self) -> QGroupBox:
        """三个一键按钮：读模块版本(4.2) / 读内部详细信息(4.6) / 设置(4.7)。"""
        grp = QGroupBox("模块版本查询（LME 自定义下发）")
        gl = QVBoxLayout(grp)

        top = QHBoxLayout()
        top.addWidget(QLabel("目标地址"))
        self.lme_addr_edit = QLineEdit(lme.DEFAULT_ADDR)
        self.lme_addr_edit.setFixedWidth(130)
        self.lme_addr_edit.setMaxLength(14)
        self.lme_addr_edit.setToolTip(
            "下发给模块的 645 表地址（12 位十六进制）。\n"
            "默认 AAAAAAAAAAAA = 手册 §5.1.1 虚拟电表上位机的点对点口径；\n"
            "按目标表地址/模块地址填写即可（线上自动低字节在前）。"
        )
        top.addWidget(self.lme_addr_edit)

        self.btn_lme_42 = QPushButton("读模块版本(4.2)")
        self.btn_lme_46 = QPushButton("读内部详细信息(4.6)")
        self.btn_lme_47 = QPushButton("设置(4.7)")
        set_btn(self.btn_lme_42, "primary", "sm")
        set_btn(self.btn_lme_46, "primary", "sm")
        set_btn(self.btn_lme_47, "warning", "sm")
        set_btn_icon(self.btn_lme_42, "copy")
        set_btn_icon(self.btn_lme_46, "copy")
        set_btn_icon(self.btn_lme_47, "apply")
        self.btn_lme_42.setToolTip(
            "手册 4.2：读 HPLC 单模 STA 软件详细版本信息（DI=04FFAAF9，无参数）。\n"
            "请求 C=11H，数据域仅 DI；应答含外部/内部厂商、MCU/APS/NWK/PHY/DSP 版本。"
        )
        self.btn_lme_46.setToolTip(
            "手册 4.6：读 HPLC 双模 STA 内部详细信息（DI=FF00DD01）。\n"
            "请求 C=11H，条目按「分类/数据ID」填写，逗号分隔；留空 = M=0 读全部支持条目。"
        )
        self.btn_lme_47.setToolTip(
            "手册 4.7：设置 HPLC 双模 STA 详细信息（DI=FF00DD01，C=14H）。\n"
            "条目按「分类/数据ID:数据hex」填写；下发前会列出条目二次确认。"
        )
        for b in (self.lme_addr_edit, self.btn_lme_42, self.btn_lme_46, self.btn_lme_47):
            top.addWidget(b)
        top.addStretch(1)
        gl.addLayout(top)

        ent_row = QHBoxLayout()
        self.lme_entry_label = QLabel("条目")
        self.lme_entry_edit = QLineEdit()
        self.lme_entry_edit.setPlaceholderText("如 0/15,1/3（留空 = 读模块全部支持条目）")
        self.lme_entry_label.setFixedWidth(
            self.lme_entry_label.fontMetrics().horizontalAdvance("条目"))
        ent_row.addWidget(self.lme_entry_label)
        ent_row.addWidget(self.lme_entry_edit, 1)
        gl.addLayout(ent_row)

        gs_row = QHBoxLayout()
        gs_row.addWidget(QLabel("帧"))
        self.lme_frame_edit = QLineEdit()
        self.lme_frame_edit.setReadOnly(True)
        self.lme_frame_edit.setPlaceholderText("点左侧按钮生成请求帧")
        self.lme_frame_edit.setStyleSheet("font-family: Consolas, monospace;")
        self.btn_lme_send = QPushButton("下发到串口")
        self.btn_lme_copy = QPushButton("复制hex")
        set_btn(self.btn_lme_send, "success", "sm")
        set_btn(self.btn_lme_copy, "ghost", "sm")
        set_btn_icon(self.btn_lme_send, "play")
        set_btn_icon(self.btn_lme_copy, "copy")
        self.btn_lme_send.setToolTip(
            "把帧框中的请求帧写入串口 TX（需先在「串口从站」点「开始监听」）。\n"
            "点三个读取/设置按钮时若串口已在监听，会自动下发，无需再点此按钮。")
        gs_row.addWidget(self.lme_frame_edit, 1)
        gs_row.addWidget(self.btn_lme_send)
        gs_row.addWidget(self.btn_lme_copy)
        gl.addLayout(gs_row)

        self.btn_lme_42.clicked.connect(lambda: self._lme_build_and_send(lme.KIND_SINGLE_STA))
        self.btn_lme_46.clicked.connect(lambda: self._lme_build_and_send(lme.KIND_DUAL_STA))
        self.btn_lme_47.clicked.connect(lambda: self._lme_build_and_send(lme.KIND_DUAL_SET))
        self.btn_lme_send.clicked.connect(self._lme_send_frame)
        self.btn_lme_copy.clicked.connect(self._lme_copy_frame)

        self._lme_kind = lme.KIND_DUAL_STA
        self._lme_frame: bytes = b""
        self._lme_sync_entry_visibility()
        return grp

    def _lme_sync_entry_visibility(self):
        """4.2 无数据单元 → 隐藏并清空条目框；4.6/4.7 显示并更新语义提示。"""
        kind = self._lme_kind
        need = lme.KIND_NEEDS_ENTRIES.get(kind, True)
        self.lme_entry_label.setVisible(need)
        self.lme_entry_edit.setVisible(need)
        if not need:
            self.lme_entry_edit.clear()
            self.lme_entry_edit.setPlaceholderText("")
            return
        if kind == lme.KIND_DUAL_STA:
            self.lme_entry_edit.setPlaceholderText(
                "条目 分类/数据ID，逗号分隔，如 0/15,1/3；留空 = 读模块全部支持条目")
            self.lme_entry_edit.setToolTip(
                "分类 0 基本信息，1 程序信息（内部版本），2 硬件信息，3 网络信息，"
                "4 运行信息，5 CCO运行信息，7 OTP信息。\n"
                "示例：0/15 本地接口默认信息（波特率/校验位）、1/3 总工程版本、1/12 APS层版本。")
        else:
            self.lme_entry_edit.setPlaceholderText(
                "条目 分类/数据ID:数据hex，逗号分隔，如 0/15:0500")
            self.lme_entry_edit.setToolTip(
                "TLV 头「编码格式/长度」按 LME_INFO_ENTRIES 条目定义自动填；"
                "数据字节数上限 31（5bit）。\n"
                "条目不在定义表时按 BIN 编码。示例：0/15:0500（波特率 BR_9600 + 无校验）")

    def _lme_set_kind(self, kind: str):
        self._lme_kind = kind
        self._lme_sync_entry_visibility()

    def _lme_build_and_send(self, kind: str):
        """组帧 → 帧框 + 日志 → 已监听则下发（未监听仅提示日志，不弹窗）。"""
        self._lme_set_kind(kind)
        addr = self.lme_addr_edit.text()
        text = self.lme_entry_edit.text() if lme.KIND_NEEDS_ENTRIES.get(kind, True) else ""
        try:
            frame = lme.build_query(kind, addr, text)
        except ValueError as e:
            QMessageBox.warning(self, "生成失败", str(e))
            return
        except Exception as e:  # 兜底：不让异常冒到 Qt 事件循环
            QMessageBox.critical(self, "生成失败", f"未预期的错误：{e}")
            return

        self._lme_frame = frame
        self.lme_frame_edit.setText(frame.hex(" ").upper())
        self.log_view.appendPlainText(f"● {lme.KIND_LABELS.get(kind, kind)}")
        self.log_view.appendPlainText(f"  请求帧 {lme.describe_frame(frame)}")

        if kind == lme.KIND_DUAL_SET and not self._lme_confirm_set(text):
            self.log_view.appendPlainText("  （已取消下发，帧保留在帧框）")
            return
        self._lme_write(frame)

    def _lme_confirm_set(self, text: str) -> bool:
        """4.7 写类下发前二次确认（可能改模块参数），列出条目明细。"""
        try:
            items = lme.describe_items(text, lme.KIND_DUAL_SET)
        except ValueError:
            items = [text]
        detail = "\n".join(f"  • {s}" for s in items) or "  （无）"
        ret = QMessageBox.question(
            self, "确认下发设置帧",
            "即将向模块下发 4.7 设置请求（C=14H），可能修改模块参数：\n\n"
            f"{detail}\n\n确认下发？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return ret == QMessageBox.StandardButton.Yes

    def _lme_write(self, frame: bytes) -> Optional[str]:
        """写串口；未监听仅记日志（三个按钮不弹窗打断），点「下发到串口」才提示。

        返回 None = 成功或未监听；返回 str = 写失败原因（由调用方决定是否弹窗）。
        """
        th = self._serial_thread
        if th is None or not th.isRunning():
            self.log_view.appendPlainText(
                "  （串口未监听，未下发：可先在上方「开始监听」，或点「下发到串口」重发）")
            return None
        err = th.write_frame(frame)
        if err:
            self.log_view.appendPlainText(f"  ❌ 下发失败: {err}")
            return err
        self.log_view.appendPlainText(f"  ⇱ 已下发 {frame.hex(' ').upper()}")
        return None

    def _lme_send_frame(self):
        """手动重发帧框内容（点按钮未监听时帧仍生成，之后可在这里补发）。"""
        if not self._lme_frame:
            QMessageBox.warning(self, "提示", "请先点上方读取/设置按钮生成请求帧。")
            return
        th = self._serial_thread
        if th is None or not th.isRunning():
            QMessageBox.warning(
                self, "串口未监听",
                "串口从站未运行，无法下发。\n\n请先在上方「串口从站」选择端口并点「开始监听」。")
            return
        if self._lme_kind == lme.KIND_DUAL_SET and not self._lme_confirm_set(
                self.lme_entry_edit.text()):
            self.log_view.appendPlainText("  （已取消下发，帧保留在帧框）")
            return
        err = self._lme_write(self._lme_frame)
        if err:
            QMessageBox.critical(
                self, "下发失败", f"请求帧写入串口失败：\n{err}")

    def _lme_copy_frame(self):
        if not self._lme_frame:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._lme_frame.hex(" ").upper())
        self.log_view.appendPlainText("（请求帧 hex 已复制）")

    def _on_slave_frame(self, frame_hex: str):
        """模块回包（串口 DIR=1 帧）：解析进结果表 + 日志摘要。"""
        try:
            frame = bytes.fromhex(frame_hex.replace(" ", ""))
        except ValueError:
            self.log_view.appendPlainText(f"⚠ 模块回包 hex 非法: {frame_hex[:60]}")
            return
        try:
            parsed = lme.decode_reply(frame)
        except Exception as e:
            self.log_view.appendPlainText(f"⚠ 模块回包解析异常: {e}")
            return
        self._fill_resp_table(frame)
        self.log_view.appendPlainText(f"◀ 模块回包解析: {lme.reply_summary(parsed)}")
        if not parsed.get("valid", True):
            self.log_view.appendPlainText(
                f"  ⚠ 帧校验未通过: {parsed.get('error') or '未知原因'}")

    def _build_archive_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        tip = QLabel(
            "DI → 数据值（与 encode_value 同口径）。值须匹配该 DI 的 data_type"
            "（电能 XXXXXX.XX、电压 XXX.X 等）。改动后点「保存」。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self.archive_table = ZoomableTableWidget()
        self.archive_table.setColumnCount(3)
        self.archive_table.setHorizontalHeaderLabels(["DI", "名称", "数据值"])
        self.archive_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.archive_table, 1)
        row = QHBoxLayout()
        for text, slot, kind in (
            ("新增行", self._archive_add, "primary"),
            ("删除选中", self._archive_delete, "danger"),
            ("保存", self._archive_save, "primary"),
            ("重载默认", self._archive_reset, "ghost"),
            ("导出JSON", self._archive_export, "ghost"),
            ("导入JSON", self._archive_import, "ghost"),
        ):
            b = QPushButton(text)
            set_btn(b, kind, "sm")
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _make_engine(self) -> DLT645MeterSim:
        return DLT645MeterSim(
            address=self.address, archive=self.archive,
            on_address_written=self.address_written.emit,
            event_word_source=self._event_word.next_value if self._random_event else None,
        )

    def _fill_example(self):
        gen = DLT645FrameGenerator()
        frame = gen.build_frame(
            self.address, gen.build_control(0x11), encode_di("00010000")
        )
        self.req_input.setPlainText(frame.hex(" ").upper())

    def _on_addr_edited(self):
        """表地址编辑完成：规范化 12 位大写 hex，非法回退旧值并提示。

        引擎每帧经 _make_engine() 重建读取 self.address → 离线与串口应答
        实时生效；「示例」请求帧同样使用当前地址。
        """
        raw = _clean_hex(self.addr_edit.text())
        if len(raw) == 12:
            self.address = raw.upper()
            self.addr_edit.setText(self.address)
            self.log_view.appendPlainText(f"● 表地址已设为 {self.address}")
            return
        QMessageBox.warning(
            self, "表地址无效",
            f"「{self.addr_edit.text()}」不是 12 位十六进制电表地址。\n\n"
            "示例：000000000000（默认）/ 123456789012\n"
            "广播：999999999999（校时）/ AAAAAAAAAAAA（读地址）",
        )
        self.addr_edit.setText(self.address)  # 回退上一有效值

    def _apply_written_address(self, new_addr: str):
        """主站经 15H 写入新表地址：同步引擎地址与编辑框并持久化。

        引擎每帧经 _make_engine 重建读 self.address → 下一帧起应答即用新地址。
        串口线程触发时经 address_written 信号跳回 GUI 线程执行。
        """
        self.address = new_addr
        self.addr_edit.setText(new_addr)
        self.log_view.appendPlainText(
            f"● 主站写地址成功(15H)，表地址已更新为 {new_addr}")
        self._archive_save_quiet()

    def _offline_generate(self):
        text = self.req_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请先粘贴主站请求帧")
            return
        clean = _clean_hex(text)
        if not clean or len(clean) % 2:
            QMessageBox.warning(self, "提示", "hex 非法")
            return
        req = bytes.fromhex(clean)
        # DIR=1（D7=1，ctrl 在 idx8）：这是从站/模块发出的帧（如 LME 查询回包），
        # 本虚拟表作为主站收到 → 直接解析展示，不再回「收到非主站帧，忽略」
        if len(req) > 8 and (req[8] & 0x80):
            self.log_view.appendPlainText(
                f"◀ 检测到从站回包，直接解析 {req.hex(' ').upper()}")
            self._on_slave_frame(req.hex(" "))
            self._last_response_frames = [req]
            self._last_response_hex = req.hex(" ").upper()
            return
        engine = self._make_engine()
        resps = engine.handle_frame(req)
        self.log_view.appendPlainText(f"← 请求 {req.hex(' ').upper()}")
        if engine.last_note:
            self.log_view.appendPlainText(f"  ◈ {engine.last_note}")
        if engine.last_error:
            self.log_view.appendPlainText(f"  ⚠ {engine.last_error}")
        if not resps:
            self.log_view.appendPlainText("  （无响应帧）")
            return
        self._last_response_frames = list(resps)
        self._last_response_hex = resps[0].hex(" ").upper()
        for r in resps:
            self.log_view.appendPlainText(f"→ 响应 {r.hex(' ').upper()}")

    def _fill_resp_table(self, frame: bytes):
        try:
            parsed = self.parser.parse(frame)
            fields = parsed.get("fields") or []
        except Exception as e:
            self.resp_table.setRowCount(1)
            _set_item(self.resp_table, 0, 0, f"解析错误: {e}")
            for c in range(1, 4):
                _set_item(self.resp_table, 0, c, "")
            return
        self.resp_table.setRowCount(len(fields))
        for r, item in enumerate(fields):
            if len(item) >= 3:
                _set_item(self.resp_table, r, 0, str(item[0]))
                _set_item(self.resp_table, r, 1, str(item[1]))
                _set_item(self.resp_table, r, 2, str(item[2]) if len(item) > 3 else "")
                _set_item(self.resp_table, r, 3, str(item[-1]))
            else:
                _set_item(self.resp_table, r, 0, str(item))
                for c in range(1, 4):
                    _set_item(self.resp_table, r, c, "")

    def _copy_response(self):
        if not self._last_response_hex:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._last_response_hex)
        self.log_view.appendPlainText("（响应 hex 已复制）")

    def _send_response_to_serial(self):
        """把最近一次「生成响应」的应答帧真实写入串口 TX。

        与从站自动应答共用同一串口：需先「开始监听」占用端口。多帧全部下发。
        """
        if not self._last_response_frames:
            QMessageBox.warning(
                self, "提示", "请先点「生成响应」得到要下发的应答帧。")
            return
        th = self._serial_thread
        if th is None or not th.isRunning():
            QMessageBox.warning(
                self, "串口未监听",
                "串口从站未运行，无法下发。\n\n请先在上方「串口从站」选择端口并点「开始监听」。")
            return
        for i, fr in enumerate(self._last_response_frames, 1):
            err = th.write_frame(fr)
            if err:
                self.log_view.appendPlainText(f"❌ 下发失败(第{i}帧): {err}")
                QMessageBox.critical(self, "下发失败", f"第 {i} 帧写入串口失败：\n{err}")
                return
            self.log_view.appendPlainText(
                f"⇱ 已下发到串口 (第{i}/{len(self._last_response_frames)}帧) "
                f"{fr.hex(' ').upper()}")

    def _send_to_parser(self):
        if self._last_response_hex:
            self.parse_requested.emit(self._last_response_hex)

    def _refresh_archive_table(self):
        items = sorted(self.archive.as_dict().items())
        self.archive_table.setRowCount(len(items))
        for r, (di, val) in enumerate(items):
            _set_item(self.archive_table, r, 0, di)
            _set_item(self.archive_table, r, 1, self._di_name(di))
            _set_item(self.archive_table, r, 2, val, editable=True)

    @staticmethod
    def _di_name(di: str) -> str:
        try:
            from dlt645_di_lookup import get_dlt645_di_lookup

            lookup = get_dlt645_di_lookup()
            for attr in ("search", "get_info"):
                fn = getattr(lookup, attr, None)
                if not callable(fn):
                    continue
                info = fn(di)
                if isinstance(info, dict):
                    return str(info.get("name") or info.get("di_name") or di)
                if isinstance(info, list) and info:
                    row = info[0]
                    if isinstance(row, (tuple, list)) and len(row) >= 2:
                        return str(row[1])
        except Exception:
            pass
        known = {
            "00010000": "正向有功总电能",
            "00020000": "反向有功总电能",
            "02010100": "A相电压",
            "02020100": "B相电压",
            "02030100": "C相电压",
            "04000101": "当前日期",
            "04000201": "当前时间",
        }
        return known.get(di, di)

    def _archive_add(self):
        r = self.archive_table.rowCount()
        self.archive_table.insertRow(r)
        _set_item(self.archive_table, r, 0, "00010000")
        _set_item(self.archive_table, r, 1, "正向有功总电能")
        _set_item(self.archive_table, r, 2, "000000.00", editable=True)

    def _archive_delete(self):
        rows = sorted({i.row() for i in self.archive_table.selectedItems()}, reverse=True)
        for r in rows:
            self.archive_table.removeRow(r)

    def _archive_save(self):
        data = {}
        for r in range(self.archive_table.rowCount()):
            di_item = self.archive_table.item(r, 0)
            val_item = self.archive_table.item(r, 2)
            if not di_item or not val_item:
                continue
            di = (di_item.text() or "").strip().upper().replace(" ", "")
            if len(di) != 8:
                continue
            data[di] = val_item.text().strip()
        self.archive = DLT645Archive(data)
        path = app_paths.data_path(SETTINGS_FILE)
        path.write_text(
            json.dumps(
                {"address": self.address, "values": data,
                 "random_event": self._random_event},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        self.log_view.appendPlainText(f"● 档案已保存（{len(data)} 项）→ {path.name}")

    def _archive_save_quiet(self):
        """持久化档案+当前地址（无弹窗无日志；15H 写地址成功后调用）。"""
        try:
            app_paths.data_path(SETTINGS_FILE).write_text(
                json.dumps(
                    {"address": self.address, "values": self.archive.as_dict(),
                     "random_event": self._random_event},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            self.log_view.appendPlainText(f"⚠ 新地址持久化失败: {e}")

    def _archive_reset(self):
        self.archive = DLT645Archive()
        self._refresh_archive_table()

    def _archive_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出档案", "dlt645_sim_data.json", "JSON (*.json)"
        )
        if not path:
            return
        open(path, "w", encoding="utf-8").write(
            json.dumps(
                {"address": self.address, "values": self.archive.as_dict(),
                 "random_event": self._random_event},
                ensure_ascii=False,
                indent=2,
            )
        )

    def _archive_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入档案", "", "JSON (*.json)")
        if not path:
            return
        try:
            obj = json.loads(open(path, encoding="utf-8").read())
            values = obj.get("values") if isinstance(obj, dict) else None
            if not isinstance(values, dict):
                QMessageBox.warning(self, "导入失败", "JSON 需含 values 对象")
                return
            if obj.get("address"):
                self.address = str(obj["address"])
                self.addr_edit.setText(self.address)
            # 导入可选字段：缺失按 False（不能保留上一个文件的勾选状态）
            self._random_event = bool(obj.get("random_event", False))
            self.chk_random_event.setChecked(self._random_event)
            self.archive = DLT645Archive(values)
            self._refresh_archive_table()
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _load_archive_file(self):
        path = app_paths.data_path(SETTINGS_FILE)
        if not path.exists():
            return
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                if obj.get("address"):
                    self.address = str(obj["address"])
                if isinstance(obj.get("values"), dict):
                    self.archive = DLT645Archive(obj["values"])
                if "random_event" in obj:
                    self._random_event = bool(obj.get("random_event"))
                    if hasattr(self, "chk_random_event"):
                        self.chk_random_event.setChecked(self._random_event)
        except Exception:
            pass

    def _refresh_ports(self):
        self.port_combo.clear()
        try:
            ports = list(serial.tools.list_ports.comports())
        except Exception:
            ports = []
        for p in ports:
            self.port_combo.addItem(f"{p.device}", p.device)
        if self.port_combo.count() == 0:
            self.port_combo.addItem("（无可用串口）", "")

    def _toggle_serial(self):
        if self._serial_thread is not None and self._serial_thread.isRunning():
            self._serial_thread.stop()
            self._serial_thread.wait(1500)
            self._serial_thread = None
            self.btn_serial.setText("开始监听")
            self.serial_status.setText("○ 已停止")
            return
        port = self.port_combo.currentData() or ""
        if not port:
            QMessageBox.warning(self, "提示", "请选择串口")
            return
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            baud = 9600
        self._serial_thread = Dlt645SerialSlaveThread(
            port,
            baud,
            self.parity_combo.currentText() or "N",
            1 if self.stop_combo.currentText() == "1" else 2,
            self._make_engine,
        )
        self._serial_thread.log.connect(self._append_log)
        self._serial_thread.slave_frame.connect(self._on_slave_frame)
        self._serial_thread.start()
        self.btn_serial.setText("停止监听")
        self.serial_status.setText("● 运行中…")

    def _append_log(self, msg: str):
        self.log_view.appendPlainText(msg)

    def shutdown(self):
        if self._serial_thread is not None:
            self._serial_thread.stop()
            self._serial_thread.wait(2000)
            self._serial_thread = None
