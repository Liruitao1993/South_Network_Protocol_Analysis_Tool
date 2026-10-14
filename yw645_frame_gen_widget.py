# -*- coding: utf-8 -*-
"""依瓦定制645协议（协议13）组帧面板（独立子控件，无协议 6 依赖）。

自包含子控件：地址（12 位表号 / 广播）→ 模式（读/透传 4 个已定义模式 + 写模式占位）
→ 数据项表格（ID / FL / 值，增删改与上下移）或透传数据域 → 组帧。

设计依据：``.trellis/tasks/10-09-yiwa-645-protocol/design.md §7 / §9``。
输出**统一交给父控件**（``FrameGenWidget.result_hex`` 与 ``preview_table``）呈现 ——
与协议9 ``CsgTestFrameGenWidget`` 同一挂载范式（父控件持「生成帧 / 添加到预设」按钮）。

⚠ 文档缺陷 D1（写模式命令码缺失）
==============================
模式下拉含「写模式（文档未定义命令码）」占位项。选中它时：若「写模式命令码」留空，
生成会给出**可读错误**（不静默、不臆造 0x50/0x60）；如现场实测到命令码，可手填后生成。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import yw645_frame_gen as fg
import yw645_wire as W
from yw645_di import DI_TABLE

#: 数据项表格列
_COL_ID = 0
_COL_FL = 1
_COL_DATA = 2

#: 请求类模式（表格只填 ID，FL/值被忽略）
_REQUEST_MODES = ("read_req", "pass_req")
#: 透传类模式（数据域为不透明载荷，用「透传数据域」输入框）
_PASS_MODES = ("pass_req", "pass_rsp")


def _hex_byte_len(text: str) -> int:
    """hex 串字节数（容忍空格）；非法时返回 -1。"""
    s = "".join(str(text or "").split()).replace("0x", "").replace("0X", "")
    if not s:
        return 0
    if len(s) % 2:
        return -1
    if any(c not in "0123456789abcdefABCDEF" for c in s):
        return -1
    return len(s) // 2


class YW645FrameGenWidget(QWidget):
    """依瓦定制645（协议13）组帧表单。父控件负责输出预览与「添加到预设」。"""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._build_ui()
        # 默认表单 = 文档「模块读设备类型」（广播，读模式请求，ID 0010）
        self.reset()

    # ── UI ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ① 地址
        addr_group = QGroupBox("① 地址域（高字节在前，与 DL/T 645-2007 相反）")
        addr_layout = QVBoxLayout(addr_group)
        addr_layout.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(QLabel("表号:"))
        self.addr_edit = QLineEdit()
        self.addr_edit.setPlaceholderText("12 位十进制表号，如 45000000013（>12 位取低 12 位，<12 位高位补 0）")
        self.addr_edit.setMinimumWidth(220)
        row.addWidget(self.addr_edit, 1)
        self.broadcast_check = QCheckBox("广播地址 AA AA AA AA AA AA")
        self.broadcast_check.setToolTip("勾选后忽略表号输入，使用广播地址 AA×6（文档 L63）")
        row.addWidget(self.broadcast_check)
        row.addStretch()
        addr_layout.addLayout(row)
        self.addr_note = QLabel("")
        self.addr_note.setStyleSheet("color: #888;")
        self.addr_note.setWordWrap(True)
        addr_layout.addWidget(self.addr_note)
        root.addWidget(addr_group)

        # ② 模式
        mode_group = QGroupBox("② 模式（COMMAND 高 4 位）")
        mode_layout = QGridLayout(mode_group)
        mode_layout.setHorizontalSpacing(8)
        mode_layout.setVerticalSpacing(4)
        mode_layout.addWidget(QLabel("模式:"), 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(240)
        for key, code, label in fg.MODE_OPTIONS:
            self.mode_combo.addItem(label, key)
        self.mode_combo.setToolTip(
            "读模式请求 0x10 / 返回 0x20；透传模式请求 0x30 / 返回 0x40；"
            "写模式命令码文档未定义（占位，须手填实测值）"
        )
        mode_layout.addWidget(self.mode_combo, 0, 1)
        mode_layout.addWidget(QLabel("数据项形态:"), 0, 2)
        self.with_fl_combo = QComboBox()
        self.with_fl_combo.addItem("自动（请求不带 FL / 返回带 FL）", None)
        self.with_fl_combo.addItem("带 FL + 数据（回复形态）", True)
        self.with_fl_combo.addItem("不带 FL（请求形态）", False)
        self.with_fl_combo.setToolTip("默认按模式推导（文档 L120：请求不带数据长度，回复时带）")
        mode_layout.addWidget(self.with_fl_combo, 0, 3)
        mode_layout.addWidget(QLabel("写模式命令码:"), 1, 0)
        self.write_cmd_edit = QLineEdit()
        self.write_cmd_edit.setPlaceholderText("如 0x50（文档未定义写模式，留空则禁用生成）")
        self.write_cmd_edit.setMaximumWidth(260)
        mode_layout.addWidget(self.write_cmd_edit, 1, 1)
        mode_layout.setColumnStretch(4, 1)
        self.mode_hint = QLabel("")
        self.mode_hint.setStyleSheet("color: #888;")
        self.mode_hint.setWordWrap(True)
        mode_layout.addWidget(self.mode_hint, 2, 0, 1, 5)
        root.addWidget(mode_group)

        # ③ 数据项 / 透传数据域
        item_group = QGroupBox("③ 数据域")
        item_layout = QVBoxLayout(item_group)
        item_layout.setSpacing(4)
        self.items_table = QTableWidget(0, 3)
        self.items_table.setHorizontalHeaderLabels(
            ["数据项 ID（2B hex）", "长度 FL（请求形态忽略）", "数据项值（hex）"]
        )
        self.items_table.horizontalHeader().setSectionResizeMode(_COL_ID, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(_COL_FL, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(_COL_DATA, QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setMinimumHeight(110)
        item_layout.addWidget(self.items_table)

        btns = QHBoxLayout()
        self.add_item_btn = QPushButton("添加数据项")
        self.del_item_btn = QPushButton("删除选中")
        self.up_item_btn = QPushButton("上移")
        self.down_item_btn = QPushButton("下移")
        for b in (self.add_item_btn, self.del_item_btn, self.up_item_btn, self.down_item_btn):
            btns.addWidget(b)
        btns.addStretch()
        item_layout.addLayout(btns)

        body_row = QHBoxLayout()
        self.body_label = QLabel("透传数据域（未加 0x33 的 hex）:")
        body_row.addWidget(self.body_label)
        self.body_edit = QLineEdit()
        self.body_edit.setPlaceholderText("如 04 E1 —— 组帧时自动 +0x33（线上为 37 14）")
        body_row.addWidget(self.body_edit, 1)
        item_layout.addLayout(body_row)

        self.item_hint = QLabel("")
        self.item_hint.setStyleSheet("color: #888;")
        self.item_hint.setWordWrap(True)
        item_layout.addWidget(self.item_hint)
        root.addWidget(item_group, 1)

        # ④ 生成注记（长度 / COMMAND / CS）
        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet("color: #888;")
        root.addWidget(self.note_label)

        # 信号
        self.addr_edit.textChanged.connect(self._on_changed)
        self.broadcast_check.toggled.connect(self._on_broadcast_toggled)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.with_fl_combo.currentIndexChanged.connect(self._on_changed)
        self.write_cmd_edit.textChanged.connect(self._on_changed)
        self.body_edit.textChanged.connect(self._on_changed)
        self.items_table.itemChanged.connect(self._on_item_changed)
        self.add_item_btn.clicked.connect(self._on_add_item)
        self.del_item_btn.clicked.connect(self._on_del_item)
        self.up_item_btn.clicked.connect(lambda: self._move_item(-1))
        self.down_item_btn.clicked.connect(lambda: self._move_item(1))

    # ── 模式联动 ─────────────────────────────────────────────────────

    def current_mode(self) -> str:
        return self.mode_combo.currentData() or "read_req"

    def _apply_mode_ui(self) -> None:
        mode = self.current_mode()
        is_pass = mode in _PASS_MODES
        is_write = mode == fg.WRITE_MODE_KEY
        show_items = not is_pass and not is_write
        self.items_table.setVisible(show_items)
        for b in (self.add_item_btn, self.del_item_btn, self.up_item_btn, self.down_item_btn):
            b.setVisible(show_items)
        self.body_label.setVisible(is_pass or is_write)
        self.body_edit.setVisible(is_pass or is_write)
        self.write_cmd_edit.setEnabled(is_write)
        if is_write:
            self.mode_hint.setText(
                "⚠ 写模式命令码在《依瓦定制645协议》中未定义（文档仅列出读/透传的 4 个命令码）。"
                "请在上方填写现场实测命令码；留空则无法生成（本工具不推测 0x50/0x60）。"
            )
            self.item_hint.setText("")
        elif is_pass:
            self.mode_hint.setText(
                "透传模式（文档「透传模式（用于 CIU）」）：数据域为转发载荷，模块无须解包直接转发，"
                "故此处按不透明 hex 填写（组帧时自动 +0x33），不做数据项切分。"
            )
            self.item_hint.setText("")
        else:
            self.mode_hint.setText("")
            self.item_hint.setText(
                "请求形态（0x10）只发送 ID；返回形态（0x20）需 ID + 长度 FL + 数据项值。"
                "FL 留空自动按「数据项值」字节数计算。附录A：0010 设备类型、0020 设备号。"
            )

    def _on_mode_changed(self, *_args: Any) -> None:
        self._apply_mode_ui()
        if self.current_mode() in ("read_rsp",):
            # 返回形态默认补齐 FL 列
            self._autofill_fl()
        self._on_changed()

    def _on_broadcast_toggled(self, checked: bool) -> None:
        self.addr_edit.setEnabled(not checked)
        self._on_changed()

    def _on_changed(self, *_args: Any) -> None:
        if self._loading:
            return
        self._refresh_note()
        self.changed.emit()

    # ── 数据项表格 ───────────────────────────────────────────────────

    def _add_item_row(self, item_id: str = "", fl: str = "", data: str = "") -> None:
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        self.items_table.setItem(row, _COL_ID, QTableWidgetItem(item_id))
        self.items_table.setItem(row, _COL_FL, QTableWidgetItem(str(fl)))
        self.items_table.setItem(row, _COL_DATA, QTableWidgetItem(data))

    def _on_add_item(self, *_args: Any) -> None:
        was_loading = self._loading
        self._loading = True
        self._add_item_row(DI_TABLE[0]["id"] if DI_TABLE else "0010", "", "")
        self._loading = was_loading
        self._on_changed()

    def _on_del_item(self, *_args: Any) -> None:
        rows = sorted({i.row() for i in self.items_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        was_loading = self._loading
        self._loading = True
        for r in rows:
            self.items_table.removeRow(r)
        self._loading = was_loading
        self._on_changed()

    def _move_item(self, delta: int) -> None:
        rows = sorted({i.row() for i in self.items_table.selectedIndexes()})
        if len(rows) != 1:
            return
        row = rows[0]
        target = row + delta
        if target < 0 or target >= self.items_table.rowCount():
            return
        was_loading = self._loading
        self._loading = True
        values = [self._cell_text(row, c) for c in range(3)]
        self.items_table.removeRow(row)
        self.items_table.insertRow(target)
        for c, value in enumerate(values):
            self.items_table.setItem(target, c, QTableWidgetItem(value))
        self.items_table.selectRow(target)
        self._loading = was_loading
        self._on_changed()

    def _cell_text(self, row: int, col: int) -> str:
        item = self.items_table.item(row, col)
        return item.text() if item is not None else ""

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item is None:
            return
        if item.column() == _COL_DATA:
            # 数据改动 → 自动刷新 FL 列（留空时也让位给自动计算，但显示实际值更直观）
            fl_len = _hex_byte_len(item.text())
            was_loading = self._loading
            self._loading = True
            fl_item = self.items_table.item(item.row(), _COL_FL)
            if fl_item is None:
                fl_item = QTableWidgetItem("")
                self.items_table.setItem(item.row(), _COL_FL, fl_item)
            if fl_len >= 0:
                fl_item.setText(str(fl_len))
            self._loading = was_loading
        self._on_changed()

    def _autofill_fl(self) -> None:
        was_loading = self._loading
        self._loading = True
        for row in range(self.items_table.rowCount()):
            fl_len = _hex_byte_len(self._cell_text(row, _COL_DATA))
            fl_item = self.items_table.item(row, _COL_FL)
            if fl_item is None:
                fl_item = QTableWidgetItem("")
                self.items_table.setItem(row, _COL_FL, fl_item)
            if fl_len >= 0:
                fl_item.setText(str(fl_len))
        self._loading = was_loading

    # ── 地址注记 ─────────────────────────────────────────────────────

    def address_bytes(self) -> Optional[bytes]:
        """当前应采用的 6 字节地址；非法返回 ``None``。"""
        if self.broadcast_check.isChecked():
            return W.BROADCAST_ADDR
        try:
            return W.encode_addr12(self.addr_edit.text())
        except ValueError:
            return None

    def _address_note(self) -> str:
        if self.broadcast_check.isChecked():
            return "采用地址：广播 AA AA AA AA AA AA"
        raw = self.addr_edit.text().strip()
        addr = self.address_bytes()
        if addr is None:
            return "⚠ 地址非法：请输入十进制数字（>12 位取低 12 位，<12 位高位补 0）"
        text = " ".join(f"{b:02X}" for b in addr)
        digits = "".join(f"{b:02X}" for b in addr)
        note = f"采用地址：{text}"
        entered = "".join(raw.split())
        if len(entered) > 12:
            note += f"（输入 {len(entered)} 位，按文档取低 12 位）"
        elif len(entered) < 12 and entered:
            note += f"（输入 {len(entered)} 位，高位已补 0，实际表号 {digits.lstrip('0') or '0'}）"
        return note

    # ── 生成 ─────────────────────────────────────────────────────────

    def _collect_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for row in range(self.items_table.rowCount()):
            item_id = "".join(self._cell_text(row, _COL_ID).split())
            data = "".join(self._cell_text(row, _COL_DATA).split())
            fl_text = self._cell_text(row, _COL_FL).strip()
            entry: Dict[str, Any] = {"id": item_id, "data": data}
            if fl_text:
                entry["fl"] = fl_text
            items.append(entry)
        return items

    def build(self) -> bytes:
        """组帧；失败抛 :class:`yw645_frame_gen.YW645BuildError` 并红字提示。"""
        mode = self.current_mode()
        kwargs: Dict[str, Any] = {
            "addr": W.BROADCAST_ADDR if self.broadcast_check.isChecked()
            else (self.addr_edit.text().strip() or "0"),
            "mode": mode,
            "with_fl": self.with_fl_combo.currentData(),
        }
        if mode in _PASS_MODES or mode == fg.WRITE_MODE_KEY:
            # 透传/写模式的数据域是不透明载荷 —— 以**模式**判定，不能用 isVisible()
            # （offscreen / 未 show 的窗口里子控件 isVisible() 恒为 False）
            kwargs["body"] = self.body_edit.text().strip()
        else:
            kwargs["items"] = self._collect_items()
        if mode == fg.WRITE_MODE_KEY:
            cmd_text = self.write_cmd_edit.text().strip()
            if cmd_text:
                try:
                    kwargs["cmd_override"] = int(cmd_text, 0)
                except ValueError:
                    err = f"写模式命令码不是合法数字：{cmd_text!r}（支持十进制或 0x 前缀十六进制）"
                    self._set_note(err, error=True)
                    raise fg.YW645BuildError(err) from None
        try:
            frame = fg.build_frame(**kwargs)
        except fg.YW645BuildError as exc:
            self._set_note(f"⚠ 组帧失败：{exc}", error=True)
            raise
        self._set_note(
            f"✓ {fg.describe_frame(frame)} | {self._address_note()}",
            error=False,
        )
        return frame

    def frame_hex(self) -> Optional[str]:
        """组帧并返回空格分隔大写 hex；失败返回 ``None``（已在 note 区提示原因）。"""
        try:
            frame = self.build()
        except fg.YW645BuildError:
            return None
        text = frame.hex().upper()
        return " ".join(text[i:i + 2] for i in range(0, len(text), 2))

    def _set_note(self, text: str, *, error: bool) -> None:
        self.note_label.setText(text)
        self.note_label.setStyleSheet(
            "color: #D32F2F;" if error else "color: #2E7D32;"
        )

    def _refresh_note(self, *_args: Any) -> None:
        """轻量刷新地址注记（不做完整组帧，避免每次输入都弹错误）。"""
        self.addr_note.setText(self._address_note())
        try:
            frame = self.build()
        except fg.YW645BuildError:
            return
        self._set_note(
            f"✓ {fg.describe_frame(frame)} | {self._address_note()}",
            error=False,
        )

    # ── 状态 ─────────────────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        return {
            "addr": self.addr_edit.text(),
            "broadcast": self.broadcast_check.isChecked(),
            "mode": self.current_mode(),
            "with_fl": self.with_fl_combo.currentData(),
            "items": self._collect_items(),
            "body": self.body_edit.text(),
            "write_cmd": self.write_cmd_edit.text(),
        }

    def apply_state(self, state: Optional[Dict[str, Any]]) -> None:
        if not state:
            return
        self._loading = True
        try:
            if "addr" in state:
                self.addr_edit.setText(str(state.get("addr", "")))
            self.broadcast_check.setChecked(bool(state.get("broadcast")))
            self.addr_edit.setEnabled(not self.broadcast_check.isChecked())
            mode = state.get("mode") or "read_req"
            idx = self.mode_combo.findData(mode)
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
            wf = state.get("with_fl", None)
            idx = self.with_fl_combo.findData(wf)
            if idx < 0:
                idx = 0
            self.with_fl_combo.setCurrentIndex(idx)
            self.write_cmd_edit.setText(str(state.get("write_cmd", "")))
            self.body_edit.setText(str(state.get("body", "")))
            self.items_table.setRowCount(0)
            for item in state.get("items", []) or []:
                self._add_item_row(
                    str(item.get("id", "")),
                    str(item.get("fl", "")),
                    str(item.get("data", "")),
                )
        finally:
            self._loading = False
        self._apply_mode_ui()
        self._on_changed()

    def reset(self) -> None:
        """恢复默认：文档「模块读设备类型」（广播 + 读模式请求 + ID 0010）。"""
        self.apply_state(fg.template_state("read_dev_type"))
