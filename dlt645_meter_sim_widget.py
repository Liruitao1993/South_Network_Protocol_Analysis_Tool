# -*- coding: utf-8 -*-
"""DLT645 虚拟表 Tab（协议6 从站模拟器）。

- 离线：粘贴主站读数据请求 → 生成从站响应 → 解析回读 / 复制 hex
- 档案：DI → 可读值表，可编辑保存到 dlt645_sim_data.json
- 串口：独立串口持续监听 68…16 请求并自动回复（建议虚拟串口对）

核心逻辑在 dlt645_sim/（无 Qt）。
"""

from __future__ import annotations

import json
import time
from typing import Optional

import serial
import serial.tools.list_ports
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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
from dlt645_sim.archive import DLT645Archive
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

    def __init__(self, port: str, baud: int, parity: str, stopbits: float,
                 engine_factory, parent=None):
        super().__init__(parent)
        self._port, self._baud = port, baud
        self._parity, self._stopbits = parity, stopbits
        self._engine_factory = engine_factory
        self._running = False
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
                            engine = self._engine_factory()
                            resps = engine.handle_frame(frame)
                            req_hex = frame.hex(" ")
                            self.log.emit(f"← 请求: {req_hex[:80]}")
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
                    time.sleep(0.2)
        finally:
            try:
                ser.close()
            except Exception:
                pass
            self.log.emit("○ 645 从站监听已停止")

    def stop(self):
        self._running = False


class Dlt645VirtualMeterWidget(QWidget):
    """协议6「DLT645虚拟表」组件。"""

    parse_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.address = "000000000000"
        self.archive = DLT645Archive()
        self._load_archive_file()
        self.parser = DLT645Parser()
        self._serial_thread: Optional[Dlt645SerialSlaveThread] = None
        self._last_response_hex = ""
        self._build_ui()
        self._refresh_archive_table()

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
        return DLT645MeterSim(address=self.address, archive=self.archive)

    def _fill_example(self):
        gen = DLT645FrameGenerator()
        frame = gen.build_frame(
            self.address, gen.build_control(0x11), encode_di("00010000")
        )
        self.req_input.setPlainText(frame.hex(" ").upper())

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
        engine = self._make_engine()
        resps = engine.handle_frame(req)
        self.log_view.appendPlainText(f"← 请求 {req.hex(' ').upper()}")
        if engine.last_error:
            self.log_view.appendPlainText(f"  ⚠ {engine.last_error}")
        if not resps:
            self.log_view.appendPlainText("  （无响应帧）")
            return
        self._last_response_hex = resps[0].hex(" ").upper()
        for r in resps:
            self.log_view.appendPlainText(f"→ 响应 {r.hex(' ').upper()}")
        self._fill_resp_table(resps[0])

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
                {"address": self.address, "values": data}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        self.log_view.appendPlainText(f"● 档案已保存（{len(data)} 项）→ {path.name}")

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
                {"address": self.address, "values": self.archive.as_dict()},
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
