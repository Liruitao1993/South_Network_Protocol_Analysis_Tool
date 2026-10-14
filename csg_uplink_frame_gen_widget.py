# -*- coding: utf-8 -*-
"""南网上行通信规约（协议14 Q/CSG 11109004-2013）组帧面板（独立子控件）。

自包含子控件：地址域（省地市区县码 / 终端地址 / 主站地址）→ 控制域（DIR/PRM/CON/PSEQ）
→ 应用功能码 AFN → 信息体表格（DA1 / DA2 / DI / 内容，增删改与上下移）→ 组帧。
输出统一交给父控件（``FrameGenWidget.result_hex`` / ``preview_table``）呈现，与协议9/13 同范式。
"""

from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import csg_uplink_di as DI
import csg_uplink_frame_gen as fg

_COL_DA1, _COL_DA2, _COL_DI, _COL_DATA = range(4)


def _hexbytes(text: str) -> bytes:
    s = "".join(str(text or "").split()).replace("0x", "").replace("0X", "")
    if not s:
        return b""
    if len(s) % 2:
        raise fg.BuildError(f"十六进制长度必须为偶数：{text!r}")
    return bytes.fromhex(s)


class CSGUplinkFrameGenWidget(QWidget):
    """协议14 组帧子控件。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_template(0)

    # ── UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 模板
        tpl_row = QHBoxLayout()
        tpl_row.addWidget(QLabel("模板："))
        self.tpl_combo = QComboBox()
        self.templates = fg.templates()
        for t in self.templates:
            self.tpl_combo.addItem(t["name"])
        self.tpl_combo.currentIndexChanged.connect(self._load_template)
        tpl_row.addWidget(self.tpl_combo, 1)
        layout.addLayout(tpl_row)

        # 地址域
        addr_group = QGroupBox("地址域 A")
        ag = QGridLayout(addr_group)
        ag.addWidget(QLabel("省地市区县码 A1："), 0, 0)
        self.a1_input = QLineEdit("000000")
        self.a1_input.setPlaceholderText("6 位十六进制，如 440306")
        self.a1_input.textChanged.connect(self._emit_changed)
        ag.addWidget(self.a1_input, 0, 1)
        ag.addWidget(QLabel("终端地址 A2："), 0, 2)
        self.a2_input = QLineEdit("1")
        self.a2_input.setPlaceholderText("1~16777215（BIN）")
        self.a2_input.textChanged.connect(self._emit_changed)
        ag.addWidget(self.a2_input, 0, 3)
        ag.addWidget(QLabel("主站地址 A3："), 1, 0)
        self.a3_input = QLineEdit("0")
        self.a3_input.setPlaceholderText("0~255")
        self.a3_input.textChanged.connect(self._emit_changed)
        ag.addWidget(self.a3_input, 1, 1)
        layout.addWidget(addr_group)

        # 控制域 + AFN
        cfg_group = QGroupBox("控制域 / 应用层")
        cg = QGridLayout(cfg_group)
        cg.addWidget(QLabel("DIR："), 0, 0)
        self.dir_combo = QComboBox()
        self.dir_combo.addItems(["下行（主站→终端）", "上行（终端→主站）"])
        self.dir_combo.currentIndexChanged.connect(self._emit_changed)
        cg.addWidget(self.dir_combo, 0, 1)
        cg.addWidget(QLabel("PRM："), 0, 2)
        self.prm_combo = QComboBox()
        self.prm_combo.addItems(["启动站 (1)", "从动站 (0)"])
        self.prm_combo.currentIndexChanged.connect(self._emit_changed)
        cg.addWidget(self.prm_combo, 0, 3)
        self.con_check = QCheckBox("CON 请求确认")
        self.con_check.toggled.connect(self._emit_changed)
        cg.addWidget(self.con_check, 1, 0, 1, 2)
        cg.addWidget(QLabel("PSEQ："), 1, 2)
        self.pseq_spin = QSpinBox()
        self.pseq_spin.setRange(0, 15)
        self.pseq_spin.valueChanged.connect(self._emit_changed)
        cg.addWidget(self.pseq_spin, 1, 3)
        cg.addWidget(QLabel("AFN："), 2, 0)
        self.afn_combo = QComboBox()
        for code, name in DI.AFN_NAMES.items():
            self.afn_combo.addItem(f"{code:02X}H {name}", code)
        self.afn_combo.currentIndexChanged.connect(self._on_afn_changed)
        cg.addWidget(self.afn_combo, 2, 1, 1, 3)
        layout.addWidget(cfg_group)

        # 信息体表格
        body_group = QGroupBox("信息体（DA1 信息点元 / DA2 信息点组 / DI 数据标识 / 内容）")
        bg = QVBoxLayout(body_group)
        self.info_table = QTableWidget(0, 4)
        self.info_table.setHorizontalHeaderLabels(["DA1 (hex)", "DA2 (hex)", "DI (8 hex)", "内容 (hex)"])
        self.info_table.horizontalHeader().setSectionResizeMode(_COL_DATA, QHeaderView.ResizeMode.Stretch)
        self.info_table.setMinimumHeight(140)
        bg.addWidget(self.info_table)
        btn_row = QHBoxLayout()
        for text, slot in (("添加行", self._add_row), ("删除行", self._del_row),
                           ("上移", lambda: self._move_row(-1)), ("下移", lambda: self._move_row(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        bg.addLayout(btn_row)
        layout.addWidget(body_group)
        layout.addStretch()

    def _on_afn_changed(self) -> None:
        self.changed.emit()

    def _emit_changed(self, *_args) -> None:
        """所有子控件信号统一经此槽转发（规避 PySide6 信号→信号析构崩溃）。"""
        self.changed.emit()

    def _on_item_changed(self, *_args) -> None:
        """表格单元变化 → 转发 changed。"""
        self.changed.emit()

    # ── 表格操作 ─────────────────────────────────────────────────

    def _add_row(self, da1="01", da2="01", di="E0000000", data="") -> None:
        r = self.info_table.rowCount()
        self.info_table.insertRow(r)
        for c, v in enumerate((da1, da2, di, data)):
            self.info_table.setItem(r, c, QTableWidgetItem(str(v)))
        self.changed.emit()

    def _del_row(self) -> None:
        r = self.info_table.currentRow()
        if r >= 0:
            self.info_table.removeRow(r)
            self.changed.emit()

    def _move_row(self, delta: int) -> None:
        r = self.info_table.currentRow()
        t = r + delta
        if r < 0 or t < 0 or t >= self.info_table.rowCount():
            return
        vals_r = [self.info_table.item(r, c).text() if self.info_table.item(r, c) else "" for c in range(4)]
        vals_t = [self.info_table.item(t, c).text() if self.info_table.item(t, c) else "" for c in range(4)]
        for c in range(4):
            self.info_table.setItem(r, c, QTableWidgetItem(vals_t[c]))
            self.info_table.setItem(t, c, QTableWidgetItem(vals_r[c]))
        self.info_table.setCurrentCell(t, 0)
        self.changed.emit()

    def _row_vals(self, r: int) -> List[str]:
        return [self.info_table.item(r, c).text() if self.info_table.item(r, c) else "" for c in range(4)]

    # ── 模板 / 状态 ──────────────────────────────────────────────

    def _load_template(self, idx: int) -> None:
        if not (0 <= idx < len(self.templates)):
            return
        t = self.templates[idx]
        afn_pos = self.afn_combo.findData(t["afn"])
        if afn_pos >= 0:
            self.afn_combo.setCurrentIndex(afn_pos)
        self.info_table.setRowCount(0)
        for b in t["bodies"]:
            r = self.info_table.rowCount()
            self.info_table.insertRow(r)
            for c, v in enumerate((f"{b['da1']:02X}", f"{b['da2']:02X}", b["di"], b.get("content", ""))):
                self.info_table.setItem(r, c, QTableWidgetItem(str(v)))
        self.changed.emit()

    def get_state(self) -> Dict[str, Any]:
        return {
            "a1": self.a1_input.text(),
            "a2": self.a2_input.text(),
            "a3": self.a3_input.text(),
            "dir": self.dir_combo.currentIndex(),
            "prm": self.prm_combo.currentIndex(),
            "con": self.con_check.isChecked(),
            "pseq": self.pseq_spin.value(),
            "afn": self.afn_combo.currentIndex(),
            "rows": [self._row_vals(r) for r in range(self.info_table.rowCount())],
        }

    def apply_state(self, st: Dict[str, Any]) -> None:
        if not st:
            return
        self.a1_input.setText(str(st.get("a1", "000000")))
        self.a2_input.setText(str(st.get("a2", "1")))
        self.a3_input.setText(str(st.get("a3", "0")))
        self.dir_combo.setCurrentIndex(int(st.get("dir", 0)))
        self.prm_combo.setCurrentIndex(int(st.get("prm", 0)))
        self.con_check.setChecked(bool(st.get("con", False)))
        self.pseq_spin.setValue(int(st.get("pseq", 0)))
        self.afn_combo.setCurrentIndex(int(st.get("afn", 0)))
        self.info_table.setRowCount(0)
        for row in st.get("rows", []) or []:
            r = self.info_table.rowCount()
            self.info_table.insertRow(r)
            for c in range(4):
                self.info_table.setItem(r, c, QTableWidgetItem(str(row[c]) if c < len(row) else ""))

    def reset(self) -> None:
        self._load_template(0)

    # ── 组帧 ─────────────────────────────────────────────────────

    def build(self) -> str:
        """按当前表单组帧，返回大写十六进制串；参数非法抛 :class:`fg.BuildError`。"""
        afn = self.afn_combo.currentData()
        if afn is None:
            raise fg.BuildError("请选择应用功能码 AFN")
        bodies = []
        for r in range(self.info_table.rowCount()):
            da1_s, da2_s, di_s, data_s = self._row_vals(r)
            if not di_s.strip():
                continue
            try:
                da1 = int(da1_s.strip() or "0", 16)
                da2 = int(da2_s.strip() or "0", 16)
            except ValueError as exc:
                raise fg.BuildError(f"第 {r + 1} 行 DA1/DA2 非十六进制：{da1_s!r}/{da2_s!r}") from exc
            bodies.append(fg.InfoBody(da1=da1, da2=da2, di=di_s.strip(), content=_hexbytes(data_s)))
        try:
            a2 = int(str(self.a2_input.text()).strip() or "0")
            a3 = int(str(self.a3_input.text()).strip() or "0")
        except ValueError as exc:
            raise fg.BuildError(f"A2/A3 必须为十进制整数：{exc}") from exc
        frame = fg.build_frame(
            afn=afn,
            bodies=bodies,
            dir_up=self.dir_combo.currentIndex() == 1,
            prm=0 if self.prm_combo.currentIndex() == 1 else 1,
            a1=self.a1_input.text().strip() or "000000",
            a2=a2,
            a3=a3,
            con=self.con_check.isChecked(),
            pseq=self.pseq_spin.value(),
        )
        return frame.hex(" ").upper()
