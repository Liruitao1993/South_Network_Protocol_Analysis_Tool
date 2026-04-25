"""测试方案Widget

提供测试方案管理页面：
- 帧列表管理（增删改、上下移动）
- 支持从协议组帧页面添加帧
- 支持导出/导入帧列表（JSON）
- 顺序发送并匹配响应帧
- 匹配规则支持 HEX/ASCII 模式，XX 为通配符
- 支持逐行超时设置（默认 2000ms）
- 测试结果：通过 / 失败 / 超时
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QComboBox, QSpinBox, QMessageBox, QFileDialog, QTextEdit,
    QDialog, QLineEdit, QGroupBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu

# 自动持久化文件路径
TEST_PLAN_PATH = Path(__file__).parent / "test_plan.json"


class AddTestItemDialog(QDialog):
    """添加测试项对话框"""

    def __init__(self, name: str = "", frame_hex: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加测试项")
        self.setMinimumWidth(450)
        self._result: Optional[Dict[str, Any]] = None
        self._init_ui(name, frame_hex)

    def _init_ui(self, name: str, frame_hex: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("名称:"))
        self.name_input = QLineEdit(name)
        self.name_input.setPlaceholderText("如：查询厂商代码")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("帧内容 (十六进制，支持空格):"))
        self.frame_input = QLineEdit(frame_hex)
        self.frame_input.setPlaceholderText("68 0E 00 00 00 00 ...")
        layout.addWidget(self.frame_input)

        layout.addWidget(QLabel("匹配规则 (HEX/ASCII，XX 为通配符):"))
        self.match_input = QLineEdit(frame_hex)
        self.match_input.setPlaceholderText("默认与帧内容相同，可修改为 XX 通配...")
        layout.addWidget(self.match_input)

        row = QHBoxLayout()
        row.addWidget(QLabel("匹配模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["HEX", "ASCII"])
        row.addWidget(self.mode_combo)
        row.addWidget(QLabel("超时 (ms):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(100, 30000)
        self.timeout_spin.setValue(2000)
        self.timeout_spin.setSingleStep(100)
        row.addWidget(self.timeout_spin)
        row.addStretch()
        layout.addLayout(row)

        self.match_enabled = QCheckBox("启用匹配")
        self.match_enabled.setChecked(True)
        layout.addWidget(self.match_enabled)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 4px; padding: 4px 16px; font-weight: bold; }"
        )
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_ok(self):
        name = self.name_input.text().strip()
        frame = self.frame_input.text().strip()
        if not name:
            QMessageBox.warning(self, "输入错误", "名称不能为空")
            return
        if not frame:
            QMessageBox.warning(self, "输入错误", "帧内容不能为空")
            return
        self._result = {
            "name": name,
            "frame_hex": frame,
            "match_rule": self.match_input.text().strip(),
            "match_mode": self.mode_combo.currentText(),
            "timeout_ms": self.timeout_spin.value(),
            "match_enabled": self.match_enabled.isChecked(),
        }
        self.accept()

    def get_result(self) -> Optional[Dict[str, Any]]:
        return self._result


class TestPlanWidget(QWidget):
    """测试方案页面Widget"""

    # 当帧被添加到测试方案时发出（供外部日志或联动）
    item_added = Signal(str, str)  # name, frame_hex

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Dict[str, Any]] = []
        self._serial_worker = None
        self._current_test_index: int = -1
        self._testing: bool = False
        self._stop_requested: bool = False
        self._wait_timer: QTimer = None
        self._waiting_for_response: bool = False
        self._any_frame_received: bool = False
        self.setup_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # ---- 顶部按钮工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_add = QPushButton("添加")
        self.btn_add.setToolTip("手动添加测试项")
        self.btn_add.clicked.connect(self._on_add_item)
        toolbar.addWidget(self.btn_add)

        self.btn_del = QPushButton("删除")
        self.btn_del.setToolTip("删除选中的测试项")
        self.btn_del.clicked.connect(self._on_delete_item)
        toolbar.addWidget(self.btn_del)

        self.btn_up = QPushButton("上移")
        self.btn_up.setToolTip("将选中项上移")
        self.btn_up.clicked.connect(self._on_move_up)
        toolbar.addWidget(self.btn_up)

        self.btn_down = QPushButton("下移")
        self.btn_down.setToolTip("将选中项下移")
        self.btn_down.clicked.connect(self._on_move_down)
        toolbar.addWidget(self.btn_down)

        toolbar.addSpacing(12)

        self.btn_start = QPushButton("开始测试")
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 14px; font-weight: bold; }"
        )
        self.btn_start.clicked.connect(self._on_start_test)
        toolbar.addWidget(self.btn_start)

        self.btn_stop = QPushButton("停止测试")
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; border-radius: 3px; padding: 4px 14px; font-weight: bold; }"
        )
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_test)
        toolbar.addWidget(self.btn_stop)

        self.chk_stop_on_fail = QCheckBox("失败时停止")
        self.chk_stop_on_fail.setChecked(True)
        self.chk_stop_on_fail.setStyleSheet(
            "QCheckBox { spacing: 6px; padding: 4px 10px; background-color: #E3F2FD; "
            "border: 1px solid #90CAF9; border-radius: 4px; font-weight: bold; color: #1565C0; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
            "QCheckBox::indicator:checked { background-color: #1565C0; border: 2px solid #1565C0; }"
            "QCheckBox::indicator:unchecked { background-color: #FFFFFF; border: 2px solid #90CAF9; }"
        )
        toolbar.addWidget(self.chk_stop_on_fail)

        toolbar.addStretch()

        self.btn_export = QPushButton("导出")
        self.btn_export.setToolTip("导出帧列表到 JSON")
        self.btn_export.clicked.connect(self._on_export)
        toolbar.addWidget(self.btn_export)

        self.btn_import = QPushButton("导入")
        self.btn_import.setToolTip("从 JSON 导入帧列表")
        self.btn_import.clicked.connect(self._on_import)
        toolbar.addWidget(self.btn_import)

        self.btn_clear_results = QPushButton("清空结果")
        self.btn_clear_results.setToolTip("清空所有测试结果和状态")
        self.btn_clear_results.clicked.connect(self._on_clear_results)
        toolbar.addWidget(self.btn_clear_results)

        main_layout.addLayout(toolbar)

        # ---- 提示说明 ----
        hint_label = QLabel("提示：匹配规则中的 <b>XX</b> 表示通配符（不判断该字节），可直接双击编辑规则修改需要匹配的报文内容")
        hint_label.setStyleSheet("color: #666666; font-size: 12px; padding: 2px 4px;")
        main_layout.addWidget(hint_label)

        # ---- 测试项表格 ----
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "序号", "名称", "帧内容", "操作", "状态",
            "启用匹配", "匹配规则", "匹配模式", "测试结果", "超时(ms)"
        ])
        # 表格复选框样式
        self.table.setStyleSheet(
            "QTableWidget::item { padding: 4px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
            "QCheckBox::indicator:checked { background-color: #1565C0; border: 2px solid #1565C0; }"
            "QCheckBox::indicator:unchecked { background-color: #FFFFFF; border: 2px solid #B0BEC5; }"
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        # 默认列宽
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 50)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 220)
        self.table.setColumnWidth(7, 60)
        self.table.setColumnWidth(8, 60)
        self.table.setColumnWidth(9, 70)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        table_font = QFont()
        table_font.setPointSize(8)
        self.table.setFont(table_font)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.itemChanged.connect(self._on_table_item_changed)
        main_layout.addWidget(self.table, 1)

        # ---- 日志输出区 ----
        log_group = QGroupBox("测试日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        from PySide6.QtWidgets import QPlainTextEdit
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(500)
        log_font = QFont("Consolas", 9)
        self.log_edit.setFont(log_font)
        log_layout.addWidget(self.log_edit)
        main_layout.addWidget(log_group, 0)
        main_layout.setStretchFactor(log_group, 0)
        main_layout.setStretchFactor(self.table, 1)

        # ---- 超时定时器 ----
        self._wait_timer = QTimer(self)
        self._wait_timer.setSingleShot(True)
        self._wait_timer.timeout.connect(self._on_test_timeout)

        # 自动加载上次方案
        self._auto_load()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def set_serial_worker(self, worker):
        """设置串口工作线程"""
        self._serial_worker = worker
        if worker:
            worker.frame_received.connect(self._on_frame_received)

    def add_item(self, name: str, frame_hex: str):
        """从外部添加测试项（如协议组帧页面）"""
        item = {
            "name": name or "未命名",
            "frame_hex": frame_hex,
            "match_rule": frame_hex,
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "match_enabled": True,
            "test_result": "未测",
            "status": "待测",
        }
        self._items.append(item)
        self._refresh_table()
        self._log(f"[添加] {item['name']}: {self._fmt_hex(item['frame_hex'])}")
        self.item_added.emit(item["name"], item["frame_hex"])
        self._auto_save()

    def clear(self):
        """清空所有测试项"""
        self._stop_test()
        self._items.clear()
        self._refresh_table()
        self.log_edit.clear()

    # ------------------------------------------------------------------
    # 表格刷新与控件绑定
    # ------------------------------------------------------------------
    def _refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            # 序号（不可编辑）
            no_item = QTableWidgetItem(str(row + 1))
            no_item.setFlags(no_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, no_item)
            # 名称
            self.table.setItem(row, 1, QTableWidgetItem(item["name"]))
            # 帧内容
            self.table.setItem(row, 2, QTableWidgetItem(self._fmt_hex(item["frame_hex"])))
            # 操作（发送按钮）
            send_btn = QPushButton("发送")
            send_btn.setStyleSheet(
                "QPushButton { background-color: #2196F3; color: white; border-radius: 2px; padding: 1px 4px; font-size: 11px; }"
            )
            send_btn.clicked.connect(lambda checked=False, r=row: self._on_send_single(r))
            self.table.setCellWidget(row, 3, send_btn)
            # 状态（不可编辑）
            status_item = QTableWidgetItem(item.get("status", "待测"))
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._set_status_style(status_item, item.get("status", "待测"))
            self.table.setItem(row, 4, status_item)
            # 启用匹配（使用复选框项）
            chk_item = QTableWidgetItem()
            chk_item.setFlags(chk_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            chk_item.setCheckState(
                Qt.CheckState.Checked if item.get("match_enabled", True) else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 5, chk_item)
            # 匹配规则（可编辑，显示带空格的 hex）
            rule_item = QTableWidgetItem(self._fmt_hex(item.get("match_rule", "")))
            rule_item.setFlags(rule_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 6, rule_item)
            # 匹配模式
            mode_combo = QComboBox()
            mode_combo.addItems(["HEX", "ASCII"])
            mode_combo.setCurrentText(item.get("match_mode", "HEX"))
            mode_combo.currentTextChanged.connect(lambda text, r=row: self._on_match_mode_changed(r, text))
            self.table.setCellWidget(row, 7, mode_combo)
            # 测试结果（不可编辑，只设置文字颜色）
            result_item = QTableWidgetItem(item.get("test_result", "未测"))
            result_item.setFlags(result_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._set_result_style(result_item, item.get("test_result", "未测"))
            self.table.setItem(row, 8, result_item)
            # 超时
            spin = QSpinBox()
            spin.setRange(100, 30000)
            spin.setValue(item.get("timeout_ms", 2000))
            spin.setSingleStep(100)
            spin.valueChanged.connect(lambda val, r=row: self._on_timeout_changed(r, val))
            self.table.setCellWidget(row, 9, spin)
        self.table.blockSignals(False)

    def _set_status_style(self, item: QTableWidgetItem, status: str):
        if status == "测试中":
            item.setForeground(QColor("#FF9800"))
        elif status == "待测":
            item.setForeground(QColor("#666666"))
        elif status == "已测试":
            item.setForeground(QColor("#1565C0"))
        else:
            item.setForeground(QColor("#000000"))

    def _set_result_style(self, item: QTableWidgetItem, result: str):
        """设置测试结果文字颜色"""
        color_map = {
            "通过": "#008800",   # 绿色
            "失败": "#CC0000",   # 红色
            "超时": "#FF6600",   # 橙色
            "未测": "#999999",   # 灰色
        }
        item.setForeground(QColor(color_map.get(result, "#000000")))

    # ------------------------------------------------------------------
    # 表格控件事件
    # ------------------------------------------------------------------
    def _on_table_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._items):
            return
        if col == 1:
            self._items[row]["name"] = item.text()
        elif col == 2:
            self._items[row]["frame_hex"] = item.text().replace(" ", "")
        elif col == 5:
            self._items[row]["match_enabled"] = (item.checkState() == Qt.CheckState.Checked)
        elif col == 6:
            self._items[row]["match_rule"] = item.text().replace(" ", "")
        self._auto_save()

    def _on_match_mode_changed(self, row: int, text: str):
        if 0 <= row < len(self._items):
            self._items[row]["match_mode"] = text
            self._auto_save()

    def _on_timeout_changed(self, row: int, val: int):
        if 0 <= row < len(self._items):
            self._items[row]["timeout_ms"] = val
            self._auto_save()

    # ------------------------------------------------------------------
    # 导出/导入
    # ------------------------------------------------------------------
    # 工具栏按钮
    # ------------------------------------------------------------------
    def _on_add_item(self):
        dlg = AddTestItemDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                item = {
                    **result,
                    "test_result": "未测",
                    "status": "待测",
                }
                self._items.append(item)
                self._refresh_table()
                self._log(f"[添加] {item['name']}: {self._fmt_hex(item['frame_hex'])}")
                self._auto_save()

    def _on_delete_item(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行")
            return
        for row in rows:
            if 0 <= row < len(self._items):
                name = self._items[row]["name"]
                del self._items[row]
                self._log(f"[删除] 第 {row + 1} 行: {name}")
        self._refresh_table()
        self._auto_save()

    def _on_move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self._items[row], self._items[row - 1] = self._items[row - 1], self._items[row]
            self._refresh_table()
            self.table.selectRow(row - 1)
            self._auto_save()

    def _on_move_down(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._items) - 1:
            self._items[row], self._items[row + 1] = self._items[row + 1], self._items[row]
            self._refresh_table()
            self.table.selectRow(row + 1)
            self._auto_save()

    def _on_clear_results(self):
        for item in self._items:
            item["test_result"] = "未测"
            item["status"] = "待测"
        self._refresh_table()
        self.log_edit.clear()
        self._log("[清空] 所有测试结果已重置")

    # ------------------------------------------------------------------
    # 导出/导入
    # ------------------------------------------------------------------
    def _on_export(self):
        if not self._items:
            QMessageBox.information(self, "提示", "当前没有测试项可导出")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出测试方案", "test_plan.json", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            export_data = [
                {
                    "name": item["name"],
                    "frame_hex": item["frame_hex"],
                    "match_rule": item["match_rule"],
                    "match_mode": item["match_mode"],
                    "timeout_ms": item["timeout_ms"],
                    "match_enabled": item["match_enabled"],
                }
                for item in self._items
            ]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            self._log(f"[导出] 已保存 {len(export_data)} 项到 {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入测试方案", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                QMessageBox.warning(self, "导入失败", "文件格式错误：应为 JSON 数组")
                return
            imported = 0
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                item = {
                    "name": entry.get("name", "未命名"),
                    "frame_hex": entry.get("frame_hex", ""),
                    "match_rule": entry.get("match_rule", entry.get("frame_hex", "")),
                    "match_mode": entry.get("match_mode", "HEX"),
                    "timeout_ms": entry.get("timeout_ms", 2000),
                    "match_enabled": entry.get("match_enabled", True),
                    "test_result": "未测",
                    "status": "待测",
                }
                self._items.append(item)
                imported += 1
            self._refresh_table()
            self._log(f"[导入] 已从 {path} 导入 {imported} 项")
            self._auto_save()
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    # ------------------------------------------------------------------
    # 单帧发送
    # ------------------------------------------------------------------
    def _on_send_single(self, row: int):
        if self._testing:
            QMessageBox.warning(self, "警告", "当前正在顺序测试中，请先停止测试")
            return
        if not self._serial_worker:
            QMessageBox.warning(self, "错误", "串口未初始化")
            return
        if not self._serial_worker.is_open():
            QMessageBox.warning(self, "错误", "串口未打开，请先打开串口")
            return
        if row < 0 or row >= len(self._items):
            return
        self._current_test_index = row
        item = self._items[row]
        self._run_single_test(row, item, sequential=False)

    # ------------------------------------------------------------------
    # 顺序测试控制
    # ------------------------------------------------------------------
    def _on_start_test(self):
        if not self._items:
            QMessageBox.information(self, "提示", "测试列表为空")
            return
        if not self._serial_worker:
            QMessageBox.warning(self, "错误", "串口未初始化")
            return
        if not self._serial_worker.is_open():
            QMessageBox.warning(self, "错误", "串口未打开，请先打开串口")
            return
        self._testing = True
        self._stop_requested = False
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._current_test_index = 0
        self._log("=" * 40)
        self._log("[测试开始] 顺序执行测试项...")
        self._execute_next()

    def _on_stop_test(self):
        self._stop_requested = True
        if self._wait_timer and self._wait_timer.isActive():
            self._wait_timer.stop()
        self._testing = False
        self._waiting_for_response = False
        self._any_frame_received = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if 0 <= self._current_test_index < len(self._items):
            self._items[self._current_test_index]["status"] = "待测"
            self._refresh_table_row(self._current_test_index)
        self._log("[测试停止] 用户手动停止")

    def _execute_next(self):
        if self._stop_requested:
            return
        if self._current_test_index >= len(self._items):
            self._finish_test()
            return
        item = self._items[self._current_test_index]
        self._run_single_test(self._current_test_index, item, sequential=True)

    def _finish_test(self):
        self._testing = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._log("[测试完成] 所有测试项执行结束")
        self._log("=" * 40)

    def _run_single_test(self, row: int, item: Dict[str, Any], sequential: bool = False):
        item["status"] = "测试中"
        item["test_result"] = "未测"
        self._refresh_table_row(row)
        frame = item["frame_hex"].replace(" ", "")
        self._log(f"[{row + 1}] 发送 -> {item['name']}: {self._fmt_hex(frame)}")
        self._waiting_for_response = True
        self._any_frame_received = False
        self._serial_worker.send_hex_string(frame)
        timeout = item.get("timeout_ms", 2000)
        self._wait_timer.start(timeout)

    def _on_test_timeout(self):
        if not self._waiting_for_response:
            return
        self._waiting_for_response = False
        row = self._current_test_index
        if 0 <= row < len(self._items):
            item = self._items[row]
            item["status"] = "已测试"
            if self._any_frame_received:
                # 收到过帧但都不匹配
                item["test_result"] = "失败"
                self._log(f"[{row + 1}] 结果 -> 失败 (超时时间内收到帧但规则均不匹配)")
            else:
                # 完全没有收到帧
                item["test_result"] = "超时"
                self._log(f"[{row + 1}] 结果 -> 超时 (>{item.get('timeout_ms', 2000)}ms 无响应)")
            self._refresh_table_row(row)
            if self._testing and self.chk_stop_on_fail.isChecked() and item["test_result"] == "失败":
                self._log("[测试停止] 失败时停止已启用")
                self._finish_test()
                return
        self._any_frame_received = False
        if self._testing:
            self._current_test_index += 1
            self._execute_next()

    def _on_frame_received(self, frame: bytes):
        if not self._waiting_for_response:
            return
        row = self._current_test_index
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        received_hex = frame.hex().upper()
        self._any_frame_received = True
        self._log(f"[{row + 1}] 接收 <- {self._fmt_hex(received_hex)}")

        if not item.get("match_enabled", True):
            # 未启用匹配：收到第一帧即通过
            self._waiting_for_response = False
            if self._wait_timer and self._wait_timer.isActive():
                self._wait_timer.stop()
            item["test_result"] = "通过"
            item["status"] = "已测试"
            self._log(f"[{row + 1}] 结果 -> 通过 (未启用匹配)")
            self._refresh_table_row(row)
            if self._testing:
                self._current_test_index += 1
                self._execute_next()
            return

        mode = item.get("match_mode", "HEX")
        rule = item.get("match_rule", "")
        matched = self._match_frame(rule, received_hex, mode)
        if matched:
            # 匹配成功：停止等待，标记通过
            self._waiting_for_response = False
            if self._wait_timer and self._wait_timer.isActive():
                self._wait_timer.stop()
            item["test_result"] = "通过"
            item["status"] = "已测试"
            self._log(f"[{row + 1}] 结果 -> 通过")
            self._refresh_table_row(row)
            if self._testing:
                self._current_test_index += 1
                self._execute_next()
        else:
            # 匹配失败：继续等待（可能是确认帧），不停止定时器
            self._log(f"[{row + 1}] 不匹配 -> 继续等待后续响应帧...")
            # 状态保持"测试中"

    # ------------------------------------------------------------------
    # 匹配引擎
    # ------------------------------------------------------------------
    @staticmethod
    def _match_frame(rule: str, actual: str, mode: str) -> bool:
        """匹配响应帧

        Args:
            rule: 匹配规则，XX 为通配符
            actual: 实际接收到的帧（HEX 字符串无空格）
            mode: "HEX" 或 "ASCII"
        """
        if mode == "HEX":
            expected = rule.replace(" ", "").upper()
            actual_clean = actual.replace(" ", "").upper()
        else:
            expected = rule
            actual_clean = actual

        if len(expected) != len(actual_clean):
            return False

        i = 0
        while i < len(expected):
            if i + 1 < len(expected) and expected[i] == "X" and expected[i + 1] == "X":
                i += 2
            else:
                if expected[i] != actual_clean[i]:
                    return False
                i += 1
        return True

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _refresh_table_row(self, row: int):
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        self.table.blockSignals(True)
        # 序号
        self.table.item(row, 0).setText(str(row + 1))
        # 名称
        self.table.item(row, 1).setText(item["name"])
        # 帧内容
        self.table.item(row, 2).setText(self._fmt_hex(item["frame_hex"]))
        # 状态
        status_item = self.table.item(row, 4)
        status_item.setText(item.get("status", "待测"))
        self._set_status_style(status_item, item.get("status", "待测"))
        # 启用匹配
        chk_item = self.table.item(row, 5)
        chk_item.setCheckState(
            Qt.CheckState.Checked if item.get("match_enabled", True) else Qt.CheckState.Unchecked
        )
        # 匹配规则（带空格的 hex）
        self.table.item(row, 6).setText(self._fmt_hex(item.get("match_rule", "")))
        # 测试结果（带颜色）
        result_item = self.table.item(row, 8)
        result_item.setText(item.get("test_result", "未测"))
        self._set_result_style(result_item, item.get("test_result", "未测"))
        self.table.blockSignals(False)

    def _log(self, msg: str):
        self.log_edit.appendPlainText(msg)

    @staticmethod
    def _fmt_hex(hex_str: str) -> str:
        s = hex_str.replace(" ", "").upper()
        return " ".join(s[i:i + 2] for i in range(0, len(s), 2))

    def _stop_test(self):
        self._stop_requested = True
        if self._wait_timer and self._wait_timer.isActive():
            self._wait_timer.stop()
        self._testing = False
        self._waiting_for_response = False

    # ------------------------------------------------------------------
    # 自动持久化
    # ------------------------------------------------------------------
    def _auto_save(self):
        """自动保存当前方案到 test_plan.json"""
        try:
            export_data = [
                {
                    "name": item["name"],
                    "frame_hex": item["frame_hex"],
                    "match_rule": item["match_rule"],
                    "match_mode": item["match_mode"],
                    "timeout_ms": item["timeout_ms"],
                    "match_enabled": item["match_enabled"],
                }
                for item in self._items
            ]
            with open(TEST_PLAN_PATH, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[测试方案自动保存失败] {e}")

    def _auto_load(self):
        """自动加载上次保存的方案"""
        if not TEST_PLAN_PATH.exists():
            return
        try:
            with open(TEST_PLAN_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            self._items = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                item = {
                    "name": entry.get("name", "未命名"),
                    "frame_hex": entry.get("frame_hex", ""),
                    "match_rule": entry.get("match_rule", entry.get("frame_hex", "")),
                    "match_mode": entry.get("match_mode", "HEX"),
                    "timeout_ms": entry.get("timeout_ms", 2000),
                    "match_enabled": entry.get("match_enabled", True),
                    "test_result": "未测",
                    "status": "待测",
                }
                self._items.append(item)
            self._refresh_table()
            self._log(f"[自动加载] 已从 {TEST_PLAN_PATH.name} 加载 {len(self._items)} 项")
        except Exception as e:
            print(f"[测试方案自动加载失败] {e}")
