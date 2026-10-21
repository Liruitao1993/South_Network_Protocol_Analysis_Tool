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
from typing import Optional

import serial
import serial.tools.list_ports
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidgetItem, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

import app_paths
import thread_registry
from gui_utils import ZoomableTableWidget, set_btn, set_btn_icon
from meter_sim import MeterSimEngine, SimOptions, load_archive
from meter_sim import link_layer
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
                 engine_factory, parent=None):
        super().__init__(parent)
        self._port, self._baud = port, baud
        self._parity, self._stopbits = parity, stopbits
        self._engine_factory = engine_factory
        self._running = False
        thread_registry.track(self, "MeterSimSerialSlave")

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
                    frames, consumed, rest = link_layer.extract_frames(buf)
                    if frames:
                        buf = rest if rest is not None else b""
                        for frame in frames:
                            engine = self._engine_factory()
                            resps = engine.handle_frame(frame)
                            for msg in engine.logs:
                                self.log.emit("  " + msg)
                            req_hex = frame.hex(" ")
                            self.log.emit(f"← 收到请求: {req_hex[:80]}")
                            resp_hexes = []
                            for r in resps:
                                try:
                                    ser.write(r)
                                    resp_hexes.append(r.hex(" "))
                                    self.log.emit(f"→ 回复: {r.hex(' ')[:80]}")
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
        layout.addWidget(QLabel("收发日志："))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
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
        self.chk_energy = QCheckBox("正向有功电能(00100200)随运行时间递增")
        self.chk_energy.setChecked(self.options.energy_increase)
        self.chk_freeze = QCheckBox("日/月/曲线冻结自动时标（按请求 Selector 时间）")
        self.chk_freeze.setChecked(self.options.auto_freeze_time)
        self.chk_mac = QCheckBox("明文安全请求回复附加 MAC(0A0B0C0D)")
        self.chk_mac.setChecked(self.options.mac_enabled)

        grid.addWidget(QLabel("通配地址模拟表数量："), 0, 0)
        grid.addWidget(self.spin_meter_count, 0, 1)
        grid.addWidget(self.chk_energy, 1, 0, 1, 3)
        grid.addWidget(self.chk_freeze, 2, 0, 1, 3)
        grid.addWidget(self.chk_mac, 3, 0, 1, 3)

        grid.addWidget(QLabel("名单模式："), 4, 0)
        self.list_mode = QComboBox()
        self.list_mode.addItems(["未启用", "黑名单", "白名单"])
        if self.options.whitelist:
            self.list_mode.setCurrentIndex(2)
        elif self.options.blacklist:
            self.list_mode.setCurrentIndex(1)
        grid.addWidget(self.list_mode, 4, 1)
        grid.addWidget(QLabel("地址表（/ 分隔，反转 hex，如 060504030201）："), 5, 0)
        self.list_edit = QPlainTextEdit()
        self.list_edit.setMaximumHeight(60)
        existing = self.options.blacklist or self.options.whitelist
        self.list_edit.setPlainText("/".join(existing))
        grid.addWidget(self.list_edit, 5, 1, 1, 2)

        self.chk_leak = QCheckBox("曲线冻结漏点时段（时段内曲线记录返回0行）")
        self.chk_leak.setChecked(self.options.leak_window is not None)
        grid.addWidget(self.chk_leak, 6, 0, 1, 3)
        self.time_from = QTimeEdit()
        self.time_to = QTimeEdit()
        self.time_from.setDisplayFormat("HH:mm")
        self.time_to.setDisplayFormat("HH:mm")
        if self.options.leak_window:
            f, t = self.options.leak_window
            self.time_from.setTime(self.time_from.time().addSecs(f * 60))
            self.time_to.setTime(self.time_to.time().addSecs(t * 60))
        grid.addWidget(QLabel("从"), 7, 0)
        grid.addWidget(self.time_from, 7, 1)
        grid.addWidget(QLabel("到"), 7, 2)
        grid.addWidget(self.time_to, 7, 3)

        btn_save = QPushButton("保存设置")
        set_btn(btn_save, "primary", "sm")
        set_btn_icon(btn_save, "save")
        btn_save.clicked.connect(self._save_settings)
        grid.addWidget(btn_save, 8, 0)
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    # ── 引擎 ──────────────────────────────────────────────
    def _current_options(self) -> SimOptions:
        mode = self.list_mode.currentIndex()
        addrs = [a.strip() for a in self.list_edit.toPlainText()
                 .replace("\n", "/").split("/") if a.strip()]
        return SimOptions(
            meter_count=self.spin_meter_count.value(),
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
            self._make_engine, self)
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
            resps = engine.handle_frame(f)
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
                opts.meter_count = d.get("meter_count", 3)
                opts.energy_increase = d.get("energy_increase", False)
                opts.auto_freeze_time = d.get("auto_freeze_time", True)
                opts.mac_enabled = d.get("mac_enabled", True)
                opts.blacklist = d.get("blacklist", [])
                opts.whitelist = d.get("whitelist", [])
                lw = d.get("leak_window")
                if lw:
                    opts.leak_window = tuple(lw)
        except Exception:
            pass
        return opts

    def _save_settings(self):
        opts = self._current_options()
        self.options = opts
        data = {
            "meter_count": opts.meter_count,
            "energy_increase": opts.energy_increase,
            "auto_freeze_time": opts.auto_freeze_time,
            "mac_enabled": opts.mac_enabled,
            "blacklist": opts.blacklist,
            "whitelist": opts.whitelist,
            "leak_window": opts.leak_window,
        }
        p = app_paths.data_path(SETTINGS_FILE)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        self._log(f"设置已保存: {p}")
        QMessageBox.information(self, "保存成功", "模拟设置已保存")

    # ── 关闭清理 ──────────────────────────────────────────
    def shutdown(self):
        if self._serial_thread and self._serial_thread.isRunning():
            self._serial_thread.stop()
            self._serial_thread.wait(2000)
            self._serial_thread = None
