# -*- coding: utf-8 -*-
"""Modbus 寄存器列表 GUI：管理对话框 + 查询页浏览面板。

两个组件：

- :class:`ModbusRegisterDialog` —— 增删改「每种品牌电表的寄存器列表」，
  保存后写回 ``modbus_registers.json``（走 ``modbus_register_store``）；
- :class:`ModbusRegisterPanel` —— 挂在查询标签页的只读浏览面板，
  下拉选择要用于解析的寄存器列表（与主窗口顶栏下拉框同一份选中状态）。

设计约束（与项目其它 Tab 一致）：
- 纯展示层不做解析，寄存器列表的读写全部经 ``modbus_register_store``；
- 对话框只在「保存」时写盘，取消/关闭不产生副作用；
- 组件不直接触碰 ``MainWindow``，选中变化用 Qt 信号交给主窗口处理。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import modbus_register_store as store

#: 表格列（顺序与 _fill_table / _collect_registers 一一对应）
REG_COLUMNS = ("地址", "名称", "数据类型", "数量", "系数", "单位", "说明")

#: 地址按十六进制录入（Modbus 惯例）；纯数字也按 hex 解释，与显示格式一致
ADDR_HINT = "地址按十六进制填写（如 0x0000 / 0010），不是 PLC 的 40001 编号"


def parse_address_text(text: str) -> Optional[int]:
    """地址文本 → 整数（十六进制；支持 ``0x`` 前缀）；非法返回 None。"""
    raw = str(text or "").strip().replace(" ", "")
    if not raw:
        return None
    try:
        if raw.lower().startswith("0x"):
            raw = raw[2:]
        return int(raw, 16)
    except ValueError:
        return None


def format_address(addr: int) -> str:
    """整数 → 表格显示文本 ``0x0000``。"""
    try:
        return f"0x{int(addr):04X}"
    except (TypeError, ValueError):
        return "0x0000"


class ModbusRegisterDialog(QDialog):
    """寄存器列表管理对话框（新建 / 复制 / 删除 / 编辑 / 导入 / 导出）。"""

    #: 保存成功（main_gui 据此刷新下拉框、查询页并重解析）
    profilesChanged = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        select_id: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modbus 寄存器列表管理")
        self.resize(1000, 700)
        self._profiles: List[dict] = [
            copy.deepcopy(p) for p in store.profiles() if isinstance(p, dict)
        ]
        self._current_id = select_id or store.selected_id()
        if not any(p.get("id") == self._current_id for p in self._profiles):
            self._current_id = self._profiles[0]["id"] if self._profiles else ""
        self._loading = False
        self._build_ui()
        self._reload_list()
        self._load_current()

    # ── 界面 ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        body = QHBoxLayout()

        # 左侧：列表 + 操作
        left_box = QGroupBox("寄存器列表（按品牌 / 型号）")
        left = QVBoxLayout(left_box)
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_list_changed)
        left.addWidget(self.list_widget, 1)

        left_btns = QHBoxLayout()
        new_btn = QPushButton("新建")
        new_btn.setToolTip("新建一份空白寄存器列表")
        new_btn.clicked.connect(self._on_new)
        copy_btn = QPushButton("复制")
        copy_btn.setToolTip("复制当前列表（用于同品牌不同型号微调）")
        copy_btn.clicked.connect(self._on_duplicate)
        del_btn = QPushButton("删除")
        del_btn.setToolTip("删除当前寄存器列表（不可撤销）")
        del_btn.clicked.connect(self._on_delete)
        for btn in (new_btn, copy_btn, del_btn):
            left_btns.addWidget(btn)
        left.addLayout(left_btns)
        body.addWidget(left_box, 0)

        # 右侧：表单 + 寄存器表格
        right_box = QGroupBox("寄存器定义")
        right = QVBoxLayout(right_box)

        form = QGridLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：XX 品牌三相智能电表 DTSD-1")
        self.brand_edit = QLineEdit()
        self.brand_edit.setPlaceholderText("品牌 / 厂家（仅用于分类显示）")
        self.transport_combo = QComboBox()
        for value, label in (
            ("auto", "自动识别（推荐）"),
            ("rtu", "Modbus RTU（串口）"),
            ("tcp", "Modbus TCP（以太网）"),
        ):
            self.transport_combo.addItem(label, value)
        self.byte_order_combo = QComboBox()
        self.byte_order_combo.addItem("大端（高字节在前，默认）", "big")
        self.byte_order_combo.addItem("小端（寄存器内字节交换）", "little")
        self.word_order_combo = QComboBox()
        self.word_order_combo.addItem("高字在前（ABCD，默认）", "big")
        self.word_order_combo.addItem("低字在前（CDAB）", "little")
        self.start_addr_edit = QLineEdit()
        self.start_addr_edit.setToolTip(
            "读响应帧的起始寄存器地址（响应帧本身不带地址）。\n"
            "例如一次读 0x0006 起的 4 个寄存器，这里就填 0x0006。"
        )
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("备注：协议手册版本、适用表型等")

        form.addWidget(QLabel("名称："), 0, 0)
        form.addWidget(self.name_edit, 0, 1)
        form.addWidget(QLabel("品牌："), 0, 2)
        form.addWidget(self.brand_edit, 0, 3)
        form.addWidget(QLabel("传输："), 1, 0)
        form.addWidget(self.transport_combo, 1, 1)
        form.addWidget(QLabel("字节序："), 1, 2)
        form.addWidget(self.byte_order_combo, 1, 3)
        form.addWidget(QLabel("字序："), 2, 0)
        form.addWidget(self.word_order_combo, 2, 1)
        form.addWidget(QLabel("响应起始地址："), 2, 2)
        form.addWidget(self.start_addr_edit, 2, 3)
        form.addWidget(QLabel("备注："), 3, 0)
        form.addWidget(self.note_edit, 3, 1, 1, 3)
        right.addLayout(form)

        hint = QLabel(
            f"提示：{ADDR_HINT}。数据类型决定占用寄存器个数（uint32/float32 占 2 个，"
            "uint64/float64 占 4 个），系数用于把原始值换算成工程量。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        right.addWidget(hint)

        self.table = QTableWidget(0, len(REG_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(REG_COLUMNS))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 70)
        right.addWidget(self.table, 1)

        row_btns = QHBoxLayout()
        add_btn = QPushButton("添加寄存器")
        add_btn.clicked.connect(self._on_add_row)
        del_row_btn = QPushButton("删除选中行")
        del_row_btn.clicked.connect(self._on_delete_row)
        import_btn = QPushButton("导入 JSON…")
        import_btn.clicked.connect(self._on_import)
        export_btn = QPushButton("导出 JSON…")
        export_btn.clicked.connect(self._on_export)
        for btn in (add_btn, del_row_btn, import_btn, export_btn):
            row_btns.addWidget(btn)
        row_btns.addStretch()
        right.addLayout(row_btns)

        body.addWidget(right_box, 1)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        bottom.addWidget(self.status_label, 1)
        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("关闭")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(save_btn)
        bottom.addWidget(cancel_btn)
        root.addLayout(bottom)

    # ── 列表 / 表单同步 ─────────────────────────────────────────
    def _reload_list(self) -> None:
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for profile in self._profiles:
            item = QListWidgetItem(
                f"{profile.get('name', '未命名')}"
                + (f"（{profile['brand']}）" if profile.get("brand") else "")
            )
            item.setData(Qt.ItemDataRole.UserRole, profile.get("id"))
            item.setToolTip(
                f"{len(profile.get('registers') or [])} 个寄存器；"
                f"响应起始地址 {format_address(profile.get('start_addr') or 0)}"
            )
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        index = self._index_of(self._current_id)
        if index >= 0:
            self.list_widget.setCurrentRow(index)

    def _index_of(self, profile_id: str) -> int:
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item and item.data(Qt.ItemDataRole.UserRole) == profile_id:
                return index
        return -1

    def _current_profile(self) -> Optional[dict]:
        for profile in self._profiles:
            if profile.get("id") == self._current_id:
                return profile
        return None

    def _on_list_changed(self, current, previous) -> None:
        if self._loading or current is None:
            return
        new_id = current.data(Qt.ItemDataRole.UserRole)
        if not new_id or new_id == self._current_id:
            return
        # 切换前把当前编辑内容写回工作副本，避免用户改一半切走就丢
        self._commit_current_editors()
        self._current_id = new_id
        self._load_current()

    def _commit_current_editors(self) -> None:
        """把表单/表格内容写回工作副本（不校验、不写盘）。"""
        profile = self._current_profile()
        if profile is None:
            return
        profile["name"] = self.name_edit.text().strip() or profile.get("name") or "未命名"
        profile["brand"] = self.brand_edit.text().strip()
        profile["transport"] = self.transport_combo.currentData() or "auto"
        profile["byte_order"] = self.byte_order_combo.currentData() or "big"
        profile["word_order"] = self.word_order_combo.currentData() or "big"
        start = parse_address_text(self.start_addr_edit.text())
        if start is not None and 0 <= start <= 0xFFFF:
            profile["start_addr"] = start
        profile["note"] = self.note_edit.text().strip()
        profile["registers"] = self._collect_registers(strict=False)

    def _load_current(self) -> None:
        profile = self._current_profile()
        self._loading = True
        try:
            if profile is None:
                for widget in (
                    self.name_edit,
                    self.brand_edit,
                    self.start_addr_edit,
                    self.note_edit,
                ):
                    widget.setText("")
                self.table.setRowCount(0)
                self.status_label.setText("没有寄存器列表，点击「新建」开始")
                return
            self.name_edit.setText(str(profile.get("name") or ""))
            self.brand_edit.setText(str(profile.get("brand") or ""))
            self.start_addr_edit.setText(format_address(profile.get("start_addr") or 0))
            self.note_edit.setText(str(profile.get("note") or ""))
            self._set_combo_data(self.transport_combo, profile.get("transport"))
            self._set_combo_data(self.byte_order_combo, profile.get("byte_order"))
            self._set_combo_data(self.word_order_combo, profile.get("word_order"))
            self._fill_table(profile.get("registers") or [])
            self.status_label.setText(
                f"{profile.get('name', '')}：{len(profile.get('registers') or [])} 个寄存器"
            )
        finally:
            self._loading = False

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _fill_table(self, registers: List[dict]) -> None:
        self.table.setRowCount(0)
        for entry in registers:
            self._append_row(entry)

    def _append_row(self, entry: Optional[dict] = None) -> None:
        entry = entry or {}
        row = self.table.rowCount()
        self.table.insertRow(row)
        addr = entry.get("addr", 0)
        self.table.setItem(
            row, 0, QTableWidgetItem(format_address(addr if isinstance(addr, int) else 0))
        )
        self.table.setItem(row, 1, QTableWidgetItem(str(entry.get("name") or "")))
        combo = QComboBox()
        for dtype in store.DATA_TYPES:
            combo.addItem(f"{dtype}", dtype)
        index = combo.findData(entry.get("type") or "uint16")
        combo.setCurrentIndex(index if index >= 0 else 0)
        self.table.setCellWidget(row, 2, combo)
        self.table.setItem(row, 3, QTableWidgetItem(str(entry.get("count") or 1)))
        self.table.setItem(
            row, 4, QTableWidgetItem(str(entry.get("scale", 1)))
        )
        self.table.setItem(row, 5, QTableWidgetItem(str(entry.get("unit") or "")))
        self.table.setItem(row, 6, QTableWidgetItem(str(entry.get("note") or "")))

    # ── 表格读写 ────────────────────────────────────────────────
    def _cell_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _collect_registers(self, strict: bool = True) -> List[dict]:
        """读取表格为寄存器条目列表；``strict`` 为 True 时非法内容抛 ValueError。"""
        registers: List[dict] = []
        seen: Dict[int, int] = {}
        for row in range(self.table.rowCount()):
            addr_text = self._cell_text(row, 0)
            name = self._cell_text(row, 1)
            combo = self.table.cellWidget(row, 2)
            dtype = combo.currentData() if isinstance(combo, QComboBox) else "uint16"
            count_text = self._cell_text(row, 3) or "1"
            scale_text = self._cell_text(row, 4) or "1"
            unit = self._cell_text(row, 5)
            note = self._cell_text(row, 6)
            if not addr_text and not name and not unit and not note:
                continue  # 空行忽略
            addr = parse_address_text(addr_text)
            if addr is None or not 0 <= addr <= 0xFFFF:
                if strict:
                    raise ValueError(
                        f"第 {row + 1} 行地址 {addr_text!r} 非法（应为十六进制 0000~FFFF）"
                    )
                continue
            if addr in seen:
                if strict:
                    raise ValueError(f"第 {row + 1} 行地址 {format_address(addr)} 与第 {seen[addr]} 行重复")
                continue
            seen[addr] = row + 1
            try:
                count = max(1, min(int(count_text), 120))
            except ValueError:
                if strict:
                    raise ValueError(f"第 {row + 1} 行数量 {count_text!r} 不是整数")
                count = 1
            try:
                scale = float(scale_text)
            except ValueError:
                if strict:
                    raise ValueError(f"第 {row + 1} 行系数 {scale_text!r} 不是数字")
                scale = 1.0
            registers.append(
                {
                    "addr": addr,
                    "name": name,
                    "type": dtype if dtype in store.DATA_TYPES else "uint16",
                    "count": count,
                    "scale": scale,
                    "unit": unit,
                    "note": note,
                }
            )
        registers.sort(key=lambda e: e["addr"])
        return registers

    # ── 行操作 ──────────────────────────────────────────────────
    def _on_add_row(self) -> None:
        existing = self._collect_registers(strict=False)
        next_addr = 0
        if existing:
            last = max(existing, key=lambda e: e["addr"])
            next_addr = min(0xFFFF, last["addr"] + int(last.get("count") or 1))
        self._append_row({"addr": next_addr, "count": 1, "scale": 1})
        self.table.setCurrentCell(self.table.rowCount() - 1, 0)

    def _on_delete_row(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        for row in rows:
            self.table.removeRow(row)

    # ── 列表操作（新建 / 复制 / 删除 / 导入 / 导出）─────────────
    def _on_new(self) -> None:
        self._commit_current_editors()
        profile = {
            "id": store.new_profile_id(),
            "name": f"新建寄存器列表 {len(self._profiles) + 1}",
            "brand": "",
            "transport": "auto",
            "byte_order": "big",
            "word_order": "big",
            "start_addr": 0,
            "note": "",
            "registers": [
                {"addr": 0, "name": "示例寄存器", "type": "uint16", "count": 1, "scale": 1, "unit": "", "note": ""}
            ],
        }
        self._profiles.append(profile)
        self._current_id = profile["id"]
        self._reload_list()
        self._load_current()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _on_duplicate(self) -> None:
        self._commit_current_editors()
        profile = self._current_profile()
        if profile is None:
            QMessageBox.information(self, "提示", "请先选中一份寄存器列表")
            return
        clone = copy.deepcopy(profile)
        clone["id"] = store.new_profile_id()
        clone["name"] = f"{profile.get('name', '未命名')}（副本）"
        self._profiles.append(clone)
        self._current_id = clone["id"]
        self._reload_list()
        self._load_current()

    def _on_delete(self) -> None:
        profile = self._current_profile()
        if profile is None:
            return
        answer = QMessageBox.question(
            self,
            "删除确认",
            f"确定删除寄存器列表「{profile.get('name', '')}」？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        target_id = profile["id"]
        try:
            store.delete_profile(target_id)
        except OSError as exc:
            QMessageBox.critical(self, "删除失败", f"写入配置文件失败：{exc}")
            return
        self._profiles = [p for p in self._profiles if p.get("id") != target_id]
        self._current_id = self._profiles[0]["id"] if self._profiles else ""
        self._reload_list()
        self._load_current()
        self.profilesChanged.emit()

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入寄存器列表", "", "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            imported = store.import_profiles(text)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self._profiles = [copy.deepcopy(p) for p in store.profiles()]
        self._current_id = imported[-1] if imported else self._current_id
        self._reload_list()
        self._load_current()
        self.profilesChanged.emit()
        QMessageBox.information(self, "导入完成", f"已导入 {len(imported)} 份寄存器列表")

    def _on_export(self) -> None:
        self._commit_current_editors()
        profile = self._current_profile()
        if profile is None:
            QMessageBox.information(self, "提示", "请先选中一份寄存器列表")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出寄存器列表",
            f"{profile.get('name', 'modbus_registers')}.json",
            "JSON 文件 (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(store.profile_to_json(profile))
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    # ── 保存 ────────────────────────────────────────────────────
    def _on_save(self) -> None:
        self._commit_current_editors()
        profile = self._current_profile()
        if profile is None:
            QMessageBox.information(self, "提示", "请先新建一份寄存器列表")
            return
        if not str(profile.get("name") or "").strip():
            QMessageBox.warning(self, "保存失败", "名称不能为空")
            return
        try:
            registers = self._collect_registers(strict=True)
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        if not registers:
            QMessageBox.warning(self, "保存失败", "至少需要一个寄存器条目")
            return
        profile["registers"] = registers
        try:
            store.upsert_profile(profile)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "保存失败", f"写入配置文件失败：{exc}")
            return
        self._profiles = [copy.deepcopy(p) for p in store.profiles()]
        self._reload_list()
        self.status_label.setText(f"已保存：{profile.get('name', '')}")
        self.profilesChanged.emit()
        QMessageBox.information(self, "保存成功", f"寄存器列表「{profile.get('name', '')}」已保存")


class ModbusRegisterPanel(QWidget):
    """查询页里的寄存器列表浏览面板（只读 + 选择用于解析的列表）。"""

    #: 用户选择了另一份寄存器列表（空串 = 通用解析）
    selectionChanged = Signal(str)
    #: 用户点击「管理寄存器列表…」
    manageRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.addWidget(QLabel("解析用寄存器列表："))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(260)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        top.addWidget(self.combo)
        manage_btn = QPushButton("管理寄存器列表…")
        manage_btn.setToolTip("新建 / 编辑 / 删除 / 导入导出寄存器列表（写入 modbus_registers.json）")
        manage_btn.clicked.connect(self.manageRequested.emit)
        top.addWidget(manage_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setToolTip("重新读取配置文件（手工编辑过 modbus_registers.json 时使用）")
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(refresh_btn)
        top.addStretch()
        layout.addLayout(top)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #666;")
        layout.addWidget(self.hint_label)

        self.table = QTableWidget(0, len(REG_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(REG_COLUMNS))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((90, 180, 110, 60, 70, 70)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)

        self.refresh()

    # ── 数据 ────────────────────────────────────────────────────
    def refresh(self) -> None:
        """重新读配置并刷新下拉框与表格。"""
        store.reload()
        current = store.selected_id()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("通用解析（不指定寄存器列表）", "")
        for profile in store.profiles():
            label = str(profile.get("name") or "未命名")
            brand = str(profile.get("brand") or "").strip()
            if brand:
                label = f"{label}（{brand}）"
            self.combo.addItem(label, profile.get("id") or "")
        index = self.combo.findData(current)
        self.combo.setCurrentIndex(index if index >= 0 else 0)
        self.combo.blockSignals(False)
        self._refresh_table()

    def current_id(self) -> str:
        return self.combo.currentData() or ""

    def set_current_id(self, profile_id: str) -> None:
        """外部同步选中项（不发 selectionChanged）。"""
        index = self.combo.findData(profile_id or "")
        if index < 0:
            index = 0
        if index == self.combo.currentIndex():
            self._refresh_table()
            return
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)
        self._refresh_table()

    def _refresh_table(self) -> None:
        profile_id = self.current_id()
        profile = store.get_profile(profile_id) if profile_id else None
        self.table.setRowCount(0)
        if profile is None:
            self.hint_label.setText(
                "当前为通用解析：只解析到「读/写操作、起始地址与数量、寄存器原始值」。"
                "响应帧本身不含寄存器地址，如需按品牌语义翻译，请在上方选择或新建寄存器列表。"
            )
            return
        registers = profile.get("registers") or []
        self.hint_label.setText(
            f"共 {len(registers)} 个寄存器；响应起始地址 "
            f"{format_address(profile.get('start_addr') or 0)}；"
            f"字节序 {profile.get('byte_order')} / 字序 {profile.get('word_order')}"
            + (f"；{profile.get('note')}" if profile.get("note") else "")
        )
        for entry in registers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                format_address(entry.get("addr", 0)),
                str(entry.get("name") or ""),
                str(entry.get("type") or ""),
                str(entry.get("count") or 1),
                str(entry.get("scale", 1)),
                str(entry.get("unit") or ""),
                str(entry.get("note") or ""),
            )
            for column, text in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(text))

    def _on_combo_changed(self, index: int) -> None:
        self._refresh_table()
        self.selectionChanged.emit(self.current_id())


__all__ = [
    "REG_COLUMNS",
    "parse_address_text",
    "format_address",
    "ModbusRegisterDialog",
    "ModbusRegisterPanel",
]
