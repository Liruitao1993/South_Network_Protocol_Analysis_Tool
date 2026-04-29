"""
预设按钮模块

提供 PresetButtonWidget 页面和 command.json 数据管理。
- 动态加载 command.json 按分组生成按钮
- 支持搜索过滤、右键删除
- 点击按钮发出信号，由主窗口恢复到组帧页面
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGroupBox, QMessageBox, QLineEdit,
    QDialog, QTextEdit, QComboBox, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu


# 南网和国网各自独立的预设文件
NW_COMMAND_PATH = Path(__file__).parent / "NW_command.json"
GW_COMMAND_PATH = Path(__file__).parent / "GW_command.json"


def _get_path(protocol: str) -> Path:
    return NW_COMMAND_PATH if protocol == "south" else GW_COMMAND_PATH


class PresetButtonManager:
    """预设按钮数据管理器——封装 NW_command.json / GW_command.json 的读写"""

    @staticmethod
    def load_commands(protocol: str) -> List[Dict[str, Any]]:
        path = _get_path(protocol)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("commands", [])
        except (json.JSONDecodeError, OSError) as e:
            print(f"加载 {path.name} 失败: {e}")
            return []

    @staticmethod
    def save_commands(protocol: str, commands: List[Dict[str, Any]]) -> bool:
        path = _get_path(protocol)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"commands": commands}, f, ensure_ascii=False, indent=2)
            return True
        except OSError as e:
            print(f"保存 {path.name} 失败: {e}")
            return False

    @staticmethod
    def add_command(protocol: str, cmd: Dict[str, Any]) -> bool:
        commands = PresetButtonManager.load_commands(protocol)
        if "id" not in cmd:
            cmd["id"] = str(uuid.uuid4())[:8]
        commands.append(cmd)
        return PresetButtonManager.save_commands(protocol, commands)

    @staticmethod
    def remove_command(protocol: str, cmd_id: str) -> bool:
        commands = PresetButtonManager.load_commands(protocol)
        commands = [c for c in commands if c.get("id") != cmd_id]
        return PresetButtonManager.save_commands(protocol, commands)

    @staticmethod
    def update_command(protocol: str, cmd_id: str, new_data: Dict[str, Any]) -> bool:
        commands = PresetButtonManager.load_commands(protocol)
        for c in commands:
            if c.get("id") == cmd_id:
                c.update(new_data)
                break
        return PresetButtonManager.save_commands(protocol, commands)


class AddPresetDialog(QDialog):
    """添加预设按钮对话框"""

    def __init__(self, frame_hex: str, protocol: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加命令到预设按钮")
        self.setMinimumWidth(400)
        self._frame_hex = frame_hex
        self._protocol = protocol
        self._result: Optional[Dict[str, Any]] = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # 协议显示
        proto_label = QLabel(
            f"协议: {'南网协议' if self._protocol == 'south' else '国网协议'}"
        )
        proto_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        layout.addWidget(proto_label)

        # 按钮名称
        layout.addWidget(QLabel("按钮名称:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("如：查询厂商代码")
        layout.addWidget(self.name_input)

        # 分组名称（支持下拉选择已有分组 + 手动输入新分组）
        layout.addWidget(QLabel("分组名称:"))
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        existing_groups = self._load_existing_groups()
        self.group_combo.addItem("常用查询")
        self.group_combo.addItem("常用设置")
        self.group_combo.addItem("测试命令")
        for g in existing_groups:
            if g not in ("常用查询", "常用设置", "测试命令"):
                self.group_combo.addItem(g)
        layout.addWidget(self.group_combo)

        # 功能描述
        layout.addWidget(QLabel("功能描述:"))
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("简要描述该命令的用途...")
        self.desc_input.setMaximumHeight(80)
        layout.addWidget(self.desc_input)

        # 报文预览（只读）
        layout.addWidget(QLabel("报文内容:"))
        self.frame_preview = QTextEdit()
        self.frame_preview.setPlainText(self._frame_hex)
        self.frame_preview.setReadOnly(True)
        self.frame_preview.setMaximumHeight(60)
        layout.addWidget(self.frame_preview)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "border-radius: 4px; padding: 4px 16px; font-weight: bold; }"
        )
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        apply_chinese_context_menus(self)

    def _load_existing_groups(self) -> List[str]:
        commands = PresetButtonManager.load_commands(self._protocol)
        groups = set()
        for c in commands:
            groups.add(c.get("group_name", "默认分组"))
        return sorted(groups)

    def _on_ok(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入按钮名称！")
            return
        group = self.group_combo.currentText().strip() or "默认分组"
        desc = self.desc_input.toPlainText().strip()

        self._result = {
            "protocol": self._protocol,
            "button_name": name,
            "group_name": group,
            "frame_hex": self._frame_hex,
            "description": desc,
        }
        self.accept()

    def get_result(self) -> Optional[Dict[str, Any]]:
        return self._result


class PresetButtonWidget(QWidget):
    """预设按钮页面——动态加载对应协议 JSON 生成按钮"""

    # (protocol, frame_hex, config_snapshot)
    button_clicked = Signal(str, str, dict)
    button_deleted = Signal(str)

    def __init__(self, protocol: str = "south", parent=None):
        super().__init__(parent)
        self._protocol = protocol  # "south" 或 "gdw"
        self._group_boxes: Dict[str, QGroupBox] = {}
        self._buttons: Dict[str, QPushButton] = {}
        self.setup_ui()
        self.load_buttons()

    def set_protocol(self, protocol: str):
        """切换当前显示的协议预设"""
        if protocol in ("south", "gdw") and protocol != self._protocol:
            self._protocol = protocol
            self.load_buttons()
            self.log_text.append(f"[系统] 已切换至 {'南网' if protocol == 'south' else '国网'}预设命令")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # 顶部说明
        hint = QLabel(
            "预设命令：点击按钮可快速发送报文。右键点击按钮可删除。"
        )
        hint.setStyleSheet("color: #666; font-size: 12px;")
        hint.setWordWrap(True)
        main_layout.addWidget(hint)

        # 搜索过滤
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入按钮名称或分组名称过滤...")
        self.search_input.textChanged.connect(self._filter_buttons)
        search_layout.addWidget(self.search_input)
        main_layout.addLayout(search_layout)

        # 统计
        self.stats_label = QLabel("共 0 个预设命令")
        self.stats_label.setStyleSheet("color: #999; font-size: 11px;")
        main_layout.addWidget(self.stats_label)

        # 滚动区域（按钮分组）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_layout.setSpacing(6)
        scroll.setWidget(self.scroll_content)
        main_layout.addWidget(scroll, 1)

        # ---- 底部日志区域 ----
        log_group = QGroupBox("串口日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 4, 6, 4)
        log_layout.setSpacing(4)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setPlaceholderText("点击预设按钮后，串口收发记录将显示在这里...")
        self.log_text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_text.customContextMenuRequested.connect(self._on_log_context_menu)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)

        apply_chinese_context_menus(self)

    def load_buttons(self):
        """从对应协议 JSON 加载并重新生成全部按钮"""
        self._clear_all()
        commands = PresetButtonManager.load_commands(self._protocol)
        self._build_buttons(commands)
        self.stats_label.setText(f"共 {len(commands)} 个预设命令")

    def _clear_all(self):
        """清空所有分组控件（保留 scroll_layout 的 stretch）"""
        self._group_boxes.clear()
        self._buttons.clear()
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_buttons(self, commands: List[Dict[str, Any]]):
        """按 group_name 分组构建按钮，水平排列、自适应宽度"""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for cmd in commands:
            group = cmd.get("group_name", "默认分组")
            groups.setdefault(group, []).append(cmd)

        for group_name in sorted(groups.keys()):
            cmds = groups[group_name]
            group_box = QGroupBox(group_name)
            group_box.setStyleSheet(
                "QGroupBox { font-weight: bold; color: #333; }"
            )
            row_layout = QHBoxLayout(group_box)
            row_layout.setSpacing(6)
            row_layout.setContentsMargins(6, 6, 6, 4)
            row_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

            for cmd in cmds:
                btn = QPushButton(cmd.get("button_name", "未命名"))
                tooltip_lines = [cmd.get("description", "")]
                if cmd.get("frame_hex"):
                    tooltip_lines.append(f"\n报文: {cmd['frame_hex']}")
                btn.setToolTip("\n".join(tooltip_lines))
                btn.setMinimumHeight(28)
                # 不设置固定宽度，让按钮根据文字自适应
                btn.setStyleSheet(
                    "QPushButton { background-color: #2196F3; color: white; "
                    "border-radius: 4px; padding: 3px 10px; font-weight: bold; }"
                    "QPushButton:hover { background-color: #1976D2; }"
                    "QPushButton:pressed { background-color: #0D47A1; }"
                )
                btn.clicked.connect(
                    lambda checked=False, c=cmd: self._on_button_clicked(c)
                )
                # 右键删除菜单
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, c=cmd, b=btn: self._show_context_menu(c, b)
                )
                self._buttons[cmd.get("id", "")] = btn
                row_layout.addWidget(btn)

            row_layout.addStretch()
            self._group_boxes[group_name] = group_box
            self.scroll_layout.addWidget(group_box)

        self.scroll_layout.addStretch()

    def _on_button_clicked(self, cmd: Dict[str, Any]):
        """按钮点击：发出信号，并在日志区记录"""
        protocol = cmd.get("protocol", "south")
        frame_hex = cmd.get("frame_hex", "")
        btn_name = cmd.get("button_name", "未命名")
        group_name = cmd.get("group_name", "默认分组")

        self.button_clicked.emit(
            protocol, frame_hex, cmd.get("config", {}),
        )

        # 日志输出
        proto_display = "南网" if protocol == "south" else "国网"
        log_line = (
            f"[{self._current_time()}] [{proto_display}] [{group_name}] "
            f"{btn_name}  ->  {frame_hex}"
        )
        self.log_text.append(log_line)
        self._trim_log(self.log_text)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def set_serial_worker(self, worker):
        """绑定串口工作线程，接收收发日志和帧数据"""
        self._serial_worker = worker
        if worker:
            worker.log_message.connect(self._on_serial_log)
            worker.frame_received.connect(self._on_serial_frame_received)

    def _on_serial_log(self, msg: str):
        """串口日志（发送/接收原始字节）"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")
        self._trim_log(self.log_text)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_serial_frame_received(self, frame: bytes):
        """收到完整帧后，在日志中追加简要解析"""
        from protocol_parser import ProtocolFrameParser
        from gdw10376_parser import GDW10376Parser
        try:
            if self._protocol == "south":
                parser = ProtocolFrameParser()
                table_data = parser.parse_to_table(frame)
                key_fields = ("应用功能码 (AFN)", "数据标识 (DI)", "传输方向")
            else:
                parser = GDW10376Parser()
                table_data = parser.parse_to_table(frame)
                key_fields = ("应用功能码(AFN)", "数据单元标识(DT)", "传输方向")
            summary_parts = []
            for item in table_data:
                field_name = item[0].strip()
                if field_name in key_fields:
                    parsed = str(item[2]) if item[2] else str(item[3])
                    summary_parts.append(f"{field_name}: {parsed}")
            if summary_parts:
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_text.append(f"[{ts}] [解析] {' | '.join(summary_parts)}")
            else:
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_text.append(f"[{ts}] [解析] 帧结构识别成功")
        except Exception as e:
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.append(f"[{ts}] [解析失败] {e}")
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @staticmethod
    def _current_time() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _on_log_context_menu(self, pos):
        """日志区域右键菜单"""
        menu = QMenu(self)
        clear_action = menu.addAction("清空日志")
        copy_action = menu.addAction("复制选中内容")
        select_all_action = menu.addAction("全选")
        action = menu.exec(self.log_text.mapToGlobal(pos))
        if action == clear_action:
            self.log_text.clear()
        elif action == copy_action:
            self.log_text.copy()
        elif action == select_all_action:
            self.log_text.selectAll()

    @staticmethod
    def _trim_log(log_widget: QTextEdit, max_lines: int = 500):
        """当日志超过max_lines行时，自动删除最早的行"""
        doc = log_widget.document()
        if doc.blockCount() > max_lines:
            cursor = log_widget.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor, doc.blockCount() - max_lines)
            cursor.removeSelectedText()

    def _show_context_menu(self, cmd: Dict[str, Any], btn: QPushButton):
        """右键菜单：删除预设"""
        menu = QMenu(self)
        delete_action = menu.addAction("删除此预设")
        action = menu.exec(btn.mapToGlobal(btn.rect().center()))
        if action == delete_action:
            reply = QMessageBox.question(
                self,
                "确认删除",
                f"确定删除预设按钮 '{cmd.get('button_name')}' 吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                PresetButtonManager.remove_command(self._protocol, cmd.get("id"))
                self.load_buttons()
                self.button_deleted.emit(cmd.get("id", ""))

    def _filter_buttons(self, text: str):
        """根据输入文本过滤按钮和分组可见性"""
        keyword = text.strip().lower()
        total_visible = 0

        for group_name, group_box in self._group_boxes.items():
            group_match = keyword in group_name.lower()
            hbox = group_box.layout()
            group_has_visible = False

            for i in range(hbox.count()):
                item = hbox.itemAt(i)
                if item is None:
                    continue
                btn = item.widget()
                if not isinstance(btn, QPushButton):
                    continue
                btn_match = keyword in btn.text().lower()
                visible = not keyword or group_match or btn_match
                btn.setVisible(visible)
                if visible:
                    group_has_visible = True
                    total_visible += 1

            group_box.setVisible(group_has_visible)

        self.stats_label.setText(
            f"显示 {total_visible} / {len(self._buttons)} 个预设命令"
            if keyword
            else f"共 {len(self._buttons)} 个预设命令"
        )

    def refresh(self):
        """外部调用刷新按钮列表"""
        self.load_buttons()
