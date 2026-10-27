"""
预设按钮模块

提供 PresetButtonWidget 页面和 command.json 数据管理。
- 动态加载 command.json 按分组生成按钮
- 支持搜索过滤、右键删除
- 点击按钮发出信号，由主窗口恢复到组帧页面
- 支持**直接粘贴报文**新增预设（``AddPresetDialog(..., editable_frame=True)``）
- 支持按当前协议**一键批量替换地址**并重算校验
  （复用 ``frame_addr_fix`` + ``message_tool_widget.replace_frame_address``，见 AGENTS §8 陷阱 69/75）
"""

from atomic_io import atomic_write_json

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGroupBox, QMessageBox, QLineEdit,
    QDialog, QTextEdit, QComboBox, QMenu, QFormLayout, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from gui_utils import (
    apply_chinese_context_menus, set_btn, set_btn_icon,
)
from app_paths import data_path

import protocol_registry
import frame_addr_fix


# 南网、国网、698.45、DLT645、模组化、依瓦定制645 各自独立的预设文件
NW_COMMAND_PATH = data_path("NW_command.json")
GW_COMMAND_PATH = data_path("GW_command.json")
DLT698_COMMAND_PATH = data_path("DLT698_command.json")
DLT645_COMMAND_PATH = data_path("DLT645_command.json")
MODULAR_COMMAND_PATH = data_path("MODULAR_command.json")
# 协议13（依瓦定制645）预设命令种子数据（YW645_command.json）
YW645_COMMAND_PATH = data_path("YW645_command.json")
# 协议14（南网上行通信规约）预设命令种子数据（CSG_UPLINK_command.json）
CSG_UPLINK_COMMAND_PATH = data_path("CSG_UPLINK_command.json")


#: set_protocol 支持的协议标识（顺序无关，仅用于校验）
SUPPORTED_PROTOCOLS = ("south", "gdw", "dlt698", "dlt645", "modular", "yw645", "csg_uplink")

#: 协议标识 → 中文显示名（日志/对话框共用，避免多处各写一份）
PROTOCOL_DISPLAY = {
    "south": "南网",
    "gdw": "国网",
    "dlt698": "698.45",
    "dlt645": "DLT645",
    "modular": "模组化",
    "yw645": "依瓦定制645",
    "csg_uplink": "南网上行通信规约",
}


def _get_path(protocol: str) -> Path:
    if protocol == "south":
        return NW_COMMAND_PATH
    if protocol == "dlt698":
        return DLT698_COMMAND_PATH
    if protocol == "dlt645":
        return DLT645_COMMAND_PATH
    if protocol == "modular":
        return MODULAR_COMMAND_PATH
    # ⚠ 协议13 必须走显式分支：本函数原本的兜底是 GW_COMMAND_PATH，
    # 少这一条会把依瓦帧写进 GW_command.json（污染国网命令库，
    # 同 AGENTS 陷阱 65 记录的协议9 事故）。
    if protocol == "yw645":
        return YW645_COMMAND_PATH
    # ⚠ 协议14 同理必须显式分支（否则南网上行帧会落 GW_command.json）。
    if protocol == "csg_uplink":
        return CSG_UPLINK_COMMAND_PATH
    return GW_COMMAND_PATH


# ── 批量替换地址（纯逻辑，无 Qt）─────────────────────────────────────────────
# 地址定位 / 字节序 / 校验算法一律来自 `frame_addr_fix`（**不要另写第二份**），
# 报文文本这层的编排（HEX 解析 → 协议 6/8 剥/恢复前导 FEH → 回写）来自
# `message_tool_widget.replace_frame_address`（**唯一实现**）。
# 两者都必须**按需导入**：`message_tool_widget` 顶层 import 可选依赖 crcmod，
# 模块级导入会让没装 crcmod 的机器连预设页都打不开（AGENTS §8 陷阱 69/77）。

#: 批量替换结果状态（两态：成功 / 跳过；跳过必须带可读原因）
ADDR_STATUS_OK = "ok"
ADDR_STATUS_SKIPPED = "skipped"


@dataclass
class AddrBatchItem:
    """一条预设的地址替换结果（`index` 是传入列表内的下标，调用方据此映射回原下标）。"""

    index: int
    name: str
    status: str
    frame_hex: str
    error: str = ""
    notes: List[str] = field(default_factory=list)


def preset_protocol_index(preset_key: str) -> Optional[int]:
    """预设协议标识（south/gdw/…）→ 协议索引；未知 / 空 → ``None``。

    唯一来源 = ``protocol_registry`` 的 ``preset_mode``（**不要在预设页另写一张映射表**）。
    """
    key = str(preset_key or "").strip()
    if not key:
        return None
    for spec in protocol_registry.all_protocols():
        if spec.preset_mode == key:
            return spec.index
    return None


def batch_fix_presets(
    commands: Sequence[Mapping[str, Any]],
    protocol_index: int,
    values: Mapping[str, str],
) -> List[AddrBatchItem]:
    """逐条按协议替换地址并重算校验；**不修改入参**（写回由调用方负责）。

    失败不抛出、不中断整批：该条 ``skipped`` + 可读原因（与串口/蓝牙页同一口径）。
    """
    from message_tool_widget import replace_frame_address     # 按需导入（见上）

    items: List[AddrBatchItem] = []
    for index, cmd in enumerate(commands):
        name = str(cmd.get("button_name") or "未命名")
        raw_hex = str(cmd.get("frame_hex") or "")
        frame_hex = raw_hex.strip()
        if not frame_hex:
            items.append(AddrBatchItem(index, name, ADDR_STATUS_SKIPPED, raw_hex,
                                       error="报文为空"))
            continue
        try:
            new_hex, notes, error = replace_frame_address(frame_hex, protocol_index, values)
        except Exception as exc:                              # noqa: BLE001 - 兜底成可读原因
            items.append(AddrBatchItem(
                index, name, ADDR_STATUS_SKIPPED, raw_hex,
                error=f"替换失败：{type(exc).__name__}: {exc}",
            ))
            continue
        if error:
            items.append(AddrBatchItem(index, name, ADDR_STATUS_SKIPPED, raw_hex,
                                       error=str(error)))
        else:
            items.append(AddrBatchItem(index, name, ADDR_STATUS_OK, new_hex,
                                       notes=list(notes)))
    return items


class PresetButtonManager:
    """预设按钮数据管理器——封装 NW_command.json / GW_command.json / DLT698_command.json 的读写"""

    @staticmethod
    def load_commands(protocol: str, path: Optional[Path] = None) -> List[Dict[str, Any]]:
        if path is None:
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
    def save_commands(protocol: str, commands: List[Dict[str, Any]], path: Optional[Path] = None) -> bool:
        if path is None:
            path = _get_path(protocol)
        try:
            atomic_write_json(path, {"commands": commands})
            return True
        except OSError as e:
            print(f"保存 {path.name} 失败: {e}")
            return False

    @staticmethod
    def add_command(protocol: str, cmd: Dict[str, Any], path: Optional[Path] = None) -> bool:
        commands = PresetButtonManager.load_commands(protocol, path)
        if "id" not in cmd:
            cmd["id"] = str(uuid.uuid4())[:8]
        commands.append(cmd)
        return PresetButtonManager.save_commands(protocol, commands, path)

    @staticmethod
    def remove_command(protocol: str, cmd_id: str, path: Optional[Path] = None) -> bool:
        commands = PresetButtonManager.load_commands(protocol, path)
        commands = [c for c in commands if c.get("id") != cmd_id]
        return PresetButtonManager.save_commands(protocol, commands, path)

    @staticmethod
    def update_command(protocol: str, cmd_id: str, new_data: Dict[str, Any], path: Optional[Path] = None) -> bool:
        commands = PresetButtonManager.load_commands(protocol, path)
        for c in commands:
            if c.get("id") == cmd_id:
                c.update(new_data)
                break
        return PresetButtonManager.save_commands(protocol, commands, path)


class AddPresetDialog(QDialog):
    """添加预设按钮对话框。

    ``editable_frame=True``（预设页「添加命令」）时报文框**可编辑**，支持直接粘贴 HEX，
    并在确定前校验/归一化；默认 ``False`` 保持既有调用方（组帧页「添加到预设」）逐字节不变。
    """

    def __init__(self, frame_hex: str, protocol: str, parent=None,
                 editable_frame: bool = False):
        super().__init__(parent)
        self.setWindowTitle("添加命令到预设按钮")
        self.setMinimumWidth(400)
        self._frame_hex = frame_hex
        self._protocol = protocol
        self._editable_frame = bool(editable_frame)
        self._result: Optional[Dict[str, Any]] = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # 协议显示
        proto_names = {"south": "南网协议", "gdw": "国网协议", "dlt698": "698.45 协议",
                       "dlt645": "DLT645-2007 电表协议", "modular": "模组化终端功能模块接口",
                       "yw645": "依瓦定制645", "csg_uplink": "南网上行通信规约"}
        proto_label = QLabel(
            f"协议: {proto_names.get(self._protocol, self._protocol)}"
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

        # 报文内容（可编辑 = 直接粘贴；否则只读预览）
        layout.addWidget(QLabel("报文内容:"))
        self.frame_preview = QTextEdit()
        if self._editable_frame:
            self.frame_preview.setPlaceholderText(
                "在此粘贴报文（HEX，可直接 Ctrl+V；空格/连续写法都可以）..."
            )
            self.frame_preview.setFont(QFont("Consolas", 9))
            self.frame_preview.setMaximumHeight(110)
            preset_text = str(self._frame_hex or "").strip() or self._clipboard_hex()
            self.frame_preview.setPlainText(preset_text)
        else:
            self.frame_preview.setPlainText(self._frame_hex)
            self.frame_preview.setReadOnly(True)
            self.frame_preview.setMaximumHeight(60)
        layout.addWidget(self.frame_preview)

        # 编辑模式：一键从剪贴板带入（复制报文后直接点，不必 Ctrl+V）
        if self._editable_frame:
            paste_row = QHBoxLayout()
            self.paste_btn = QPushButton("从剪贴板粘贴")
            set_btn(self.paste_btn, "secondary", "sm")
            set_btn_icon(self.paste_btn, "copy")
            self.paste_btn.clicked.connect(self._on_paste_clicked)
            paste_row.addWidget(self.paste_btn)
            paste_row.addStretch()
            layout.addLayout(paste_row)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        set_btn(ok_btn, "success")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        apply_chinese_context_menus(self)

    # ── 报文文本的解析/归一化（单一来源：message_tool_widget.hex_text_to_bytes）──

    @staticmethod
    def normalize_frame_text(text: str):
        """HEX 文本 → ``(空格分隔大写 HEX, 错误)``；错误非空 = 原文不可用。"""
        from message_tool_widget import hex_text_to_bytes      # 按需导入（crcmod）
        try:
            data = hex_text_to_bytes(str(text or ""))
        except ValueError as exc:
            return "", str(exc)
        return " ".join(f"{b:02X}" for b in data), ""

    @classmethod
    def _clipboard_hex(cls) -> str:
        """剪贴板里的合法 HEX（归一化后）；取不到/不是 HEX → 空串（不打扰用户）。"""
        app = QApplication.instance()
        if app is None:
            return ""
        try:
            text = app.clipboard().text()
        except Exception:                                      # noqa: BLE001 - 剪贴板不可用
            return ""
        norm, error = cls.normalize_frame_text(text)
        return "" if error else norm

    def _on_paste_clicked(self):
        text = ""
        app = QApplication.instance()
        if app is not None:
            try:
                text = app.clipboard().text()
            except Exception:                                  # noqa: BLE001
                text = ""
        norm, error = self.normalize_frame_text(text)
        if error:
            QMessageBox.warning(
                self, "剪贴板内容不可用",
                f"剪贴板里不是有效的 HEX 报文：{error}",
            )
            return
        self.frame_preview.setPlainText(norm)

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

        frame_hex = self._frame_hex
        if self._editable_frame:
            frame_hex, error = self.normalize_frame_text(self.frame_preview.toPlainText())
            if error:
                QMessageBox.warning(self, "报文无效", f"报文不是有效的 HEX：{error}")
                return

        self._result = {
            "protocol": self._protocol,
            "button_name": name,
            "group_name": group,
            "frame_hex": frame_hex,
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

    def __init__(self, protocol: str = "south", parent=None,
                 nw_path: Optional[Path] = None, gw_path: Optional[Path] = None):
        super().__init__(parent)
        self._protocol = protocol  # "south" / "gdw" / "dlt698"
        self._nw_path = nw_path
        self._gw_path = gw_path
        self._group_boxes: Dict[str, QGroupBox] = {}
        self._buttons: Dict[str, QPushButton] = {}
        # 地址区：当前协议的输入控件 + 「按协议暂存已填值」（切走再切回不丢）
        self._addr_edits: Dict[str, QLineEdit] = {}
        self._addr_values_by_protocol: Dict[str, Dict[str, str]] = {}
        self._addr_form_host: Optional[QWidget] = None
        self.setup_ui()
        self.load_buttons()

    def set_protocol(self, protocol: str):
        """切换当前显示的协议预设"""
        if protocol in SUPPORTED_PROTOCOLS and protocol != self._protocol:
            self._protocol = protocol
            self.load_buttons()
            self._sync_addr_group()
            proto_display = PROTOCOL_DISPLAY.get(protocol, protocol)
            self.log_text.append(f"[系统] 已切换至 {proto_display}预设命令")

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

        # 搜索过滤 + 添加命令（同一行）
        search_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加命令")
        set_btn(self.add_btn, "primary", "sm")
        set_btn_icon(self.add_btn, "add")
        self.add_btn.setToolTip("直接粘贴报文新建预设按钮（复制报文后打开本对话框会自动带入）")
        self.add_btn.clicked.connect(self._on_add_clicked)
        search_layout.addWidget(self.add_btn)
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

        # ---- 批量替换地址（按当前协议动态生成字段；内容在 _sync_addr_group 重建）----
        self.addr_group = QGroupBox("批量替换地址")
        addr_outer = QVBoxLayout(self.addr_group)
        addr_outer.setContentsMargins(6, 4, 6, 4)
        addr_outer.setSpacing(4)
        self._addr_outer = addr_outer
        self.addr_hint = QLabel("")
        self.addr_hint.setStyleSheet("color: #666; font-size: 12px;")
        self.addr_hint.setWordWrap(True)
        addr_outer.addWidget(self.addr_hint)
        main_layout.addWidget(self.addr_group)

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
        self._sync_addr_group()

    def _get_path(self) -> Optional[Path]:
        """获取当前协议对应的配置路径（None 表示使用模块默认路径）"""
        if self._protocol == "south":
            return self._nw_path
        if self._protocol == "dlt698":
            return None  # 698 预设无自定义路径，回退模块默认 DLT698_command.json
        if self._protocol == "dlt645":
            return None  # 645 预设无自定义路径，回退模块默认 DLT645_command.json
        if self._protocol == "modular":
            return None  # 模组化预设无自定义路径，回退模块默认 MODULAR_command.json
        if self._protocol == "yw645":
            return None  # 依瓦定制645预设无自定义路径，回退模块默认 YW645_command.json
        if self._protocol == "csg_uplink":
            return None  # 南网上行预设无自定义路径，回退模块默认 CSG_UPLINK_command.json
        return self._gw_path

    # ── 批量替换地址（GUI 编排：计算在 batch_fix_presets，写回/落盘只在这里）──────

    def _clear_addr_form(self):
        """移除上一份地址表单。

        整块换新而不是 ``QFormLayout.removeRow``：后者会**连同该行控件一起删除**，
        再补 ``deleteLater()`` 就成了二次删除（AGENTS §8 陷阱 69 / spec §7l）。
        """
        host = self._addr_form_host
        if host is None:
            return
        self._addr_outer.removeWidget(host)
        host.setParent(None)
        host.deleteLater()
        self._addr_form_host = None

    def _sync_addr_group(self):
        """按当前协议重建地址输入区（字段标签/写法提示全部来自 `frame_addr_fix`）。"""
        if self._addr_edits:                       # 切走前收下用户已填的值
            self._addr_values_by_protocol[self._protocol] = {
                key: edit.text() for key, edit in self._addr_edits.items()
            }
        self._addr_edits = {}
        self._clear_addr_form()

        proto_name = PROTOCOL_DISPLAY.get(self._protocol, self._protocol)
        self.addr_group.setTitle(f"批量替换地址（{proto_name}）")
        index = preset_protocol_index(self._protocol)
        fields = frame_addr_fix.fields_for(index) if index is not None else ()

        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(4)

        remembered = self._addr_values_by_protocol.get(self._protocol, {})
        if fields:
            form = QFormLayout()
            form.setSpacing(4)
            for spec in fields:
                edit = QLineEdit(remembered.get(spec.key, ""))
                edit.setPlaceholderText(spec.hint)
                edit.setToolTip(spec.hint)
                edit.textChanged.connect(self._on_addr_text_changed)
                self._addr_edits[spec.key] = edit
                form.addRow(f"{spec.label}：", edit)
            host_layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.batch_addr_btn = QPushButton("一键替换地址")
        set_btn(self.batch_addr_btn, "warning")
        set_btn_icon(self.batch_addr_btn, "refresh")
        self.batch_addr_btn.setEnabled(bool(fields))
        self.batch_addr_btn.setToolTip(
            "把上面填写的地址写入当前协议的全部预设，并按协议重算校验（失败项保持原样）"
        )
        self.batch_addr_btn.clicked.connect(self._on_batch_addr_clicked)
        btn_row.addWidget(self.batch_addr_btn)
        btn_row.addStretch()
        host_layout.addLayout(btn_row)

        self._addr_outer.insertWidget(0, host)
        self._addr_form_host = host

        if fields:
            self.addr_hint.setText(
                "地址写法见输入框提示。只替换能通过「结构 + 原帧校验」自证的预设；"
                "失败项保持原样，并在确认框与日志里给出原因。"
            )
        else:
            self.addr_hint.setText(
                f"{proto_name}暂不支持地址替换"
                "（v1 支持 南网 / 645 / 国网 / 698.45 / 依瓦645 / 南网上行）。"
            )

    def _on_addr_text_changed(self, _text: str = ""):
        """记住当前协议已填的地址（切协议来回不丢）。"""
        self._addr_values_by_protocol[self._protocol] = {
            key: edit.text() for key, edit in self._addr_edits.items()
        }

    def _filled_addr_values(self) -> Dict[str, str]:
        """当前输入区里**非空**的地址（key = frame_addr_fix 字段 key）。"""
        return {
            key: edit.text().strip()
            for key, edit in self._addr_edits.items()
            if edit.text().strip()
        }

    def _on_add_clicked(self):
        """添加命令：弹框里**直接粘贴报文**建预设按钮（剪贴板是合法 HEX 时自动带入）。"""
        dialog = AddPresetDialog("", self._protocol, parent=self, editable_frame=True)
        if dialog.exec() != QDialog.Accepted:
            return
        result = dialog.get_result()
        if not result:
            return
        result.setdefault("protocol", self._protocol)
        if not PresetButtonManager.add_command(self._protocol, result, self._get_path()):
            QMessageBox.warning(self, "保存失败", "写入预设文件失败，命令未添加。")
            return
        self.load_buttons()
        self.log_text.append(
            f"[{self._current_time()}] [系统] 已添加预设：{result.get('button_name')}"
            f"（{result.get('group_name')}）"
        )
        self._trim_log(self.log_text)

    def _on_batch_addr_clicked(self):
        """一键替换地址：计算 → 确认 → 写回 → 一次落盘 → 刷新 → 日志/汇总。"""
        index = preset_protocol_index(self._protocol)
        proto_name = PROTOCOL_DISPLAY.get(self._protocol, self._protocol)
        if index is None:
            QMessageBox.information(self, "暂不支持", f"{proto_name}暂不支持地址替换。")
            return
        values = self._filled_addr_values()
        if not values:
            QMessageBox.warning(self, "请先填写地址", "至少填写一个地址字段再执行替换。")
            return

        from message_tool_widget import addr_field_errors      # 按需导入（crcmod）
        errors = addr_field_errors(index, values)
        if errors:
            QMessageBox.warning(self, "地址格式有误", "\n".join(errors))
            return

        commands = PresetButtonManager.load_commands(self._protocol, self._get_path())
        # 作用范围与 load_buttons 同一过滤判据：只改**本协议**条目，同文件里其它协议的
        # 历史混入条目不碰（用户看不见的条目不该被悄悄改掉）。
        scope = [
            pos for pos, cmd in enumerate(commands)
            if cmd.get("protocol", self._protocol) == self._protocol
        ]
        items = batch_fix_presets([commands[pos] for pos in scope], index, values)
        ok_items = [it for it in items if it.status == ADDR_STATUS_OK]
        skipped = [it for it in items if it.status != ADDR_STATUS_OK]
        detail = self._skipped_detail(skipped)

        if not ok_items:
            QMessageBox.warning(
                self, "没有可替换的预设",
                f"「{proto_name}」下没有可替换的预设（成功 0 条，跳过 {len(skipped)} 条）。"
                f"{detail}",
            )
            return

        if QMessageBox.question(
            self, "确认替换地址",
            f"将对「{proto_name}」的 {len(ok_items)} 个预设替换地址并重算校验。\n"
            f"成功 {len(ok_items)} 条，跳过 {len(skipped)} 条。{detail}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        for item in ok_items:
            commands[scope[item.index]]["frame_hex"] = item.frame_hex
        if not PresetButtonManager.save_commands(self._protocol, commands, self._get_path()):
            QMessageBox.warning(self, "保存失败", "写入预设文件失败，本次替换未保存。")
            return
        self._log_batch_result(ok_items, skipped)
        self.load_buttons()
        QMessageBox.information(
            self, "替换完成",
            f"已替换 {len(ok_items)} 条，跳过 {len(skipped)} 条。{detail}",
        )

    @staticmethod
    def _skipped_detail(items: Sequence[AddrBatchItem], limit: int = 8) -> str:
        """跳过项的可读明细（确认框/汇总用，最多 ``limit`` 条）。"""
        if not items:
            return ""
        lines = [f"\n\n跳过 {len(items)} 条："]
        for item in items[:limit]:
            lines.append(f"· {item.name}：{item.error}")
        if len(items) > limit:
            lines.append(f"……另有 {len(items) - limit} 条（详见日志）")
        return "\n".join(lines)

    def _log_batch_result(self, ok_items: Sequence[AddrBatchItem],
                          skipped: Sequence[AddrBatchItem]):
        """逐条写日志（面板唯一出口仍是 `log_text.append`；与其它日志同一格式）。"""
        ts = self._current_time()
        self.log_text.append(
            f"[{ts}] [地址替换] 成功 {len(ok_items)} 条，跳过 {len(skipped)} 条"
        )
        for item in ok_items:
            detail = "；".join(item.notes) if item.notes else "地址未变化（校验值一致）"
            self.log_text.append(f"[{ts}] [地址替换] {item.name}：{detail}")
        for item in skipped:
            self.log_text.append(f"[{ts}] [地址替换] {item.name}：跳过（{item.error}）")
        self._trim_log(self.log_text)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def set_file_paths(self, nw_path: Optional[Path] = None, gw_path: Optional[Path] = None):
        """动态更新配置文件路径并刷新"""
        self._nw_path = nw_path
        self._gw_path = gw_path
        self.load_buttons()

    def load_buttons(self):
        """从对应协议 JSON 加载并重新生成全部按钮"""
        self._clear_all()
        commands = PresetButtonManager.load_commands(self._protocol, self._get_path())
        # 按 protocol 过滤：显式标记为其他协议的条目不显示（历史 GW 文件曾混入 dlt698 条目）；
        # 无 protocol 键的老数据按文件归属正常显示
        commands = [
            cmd for cmd in commands
            if cmd.get("protocol", self._protocol) == self._protocol
        ]
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
                # 不设置固定宽度，让按钮根据文字自适应
                set_btn(btn, "primary")
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
        proto_display = PROTOCOL_DISPLAY.get(protocol, protocol)
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
                PresetButtonManager.remove_command(self._protocol, cmd.get("id"), self._get_path())
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
