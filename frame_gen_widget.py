"""南网协议组帧Widget

提供基于DI_FIELD_SCHEMA的动态表单和通用组帧界面，
支持预定义schema和自定义字段模板两种模式。
可嵌入main_gui.py作为独立标签页使用。
"""

from typing import Dict, Any, List, Tuple
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QGroupBox, QScrollArea, QCheckBox, QMessageBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, QRegularExpression
from PySide6.QtGui import QFont, QKeyEvent, QIntValidator, QRegularExpressionValidator

from send_frame_lib import ProtocolFrameGenerator
from gui_utils import set_btn, set_btn_icon
from frame_generator_schema import DI_FIELD_SCHEMA
from protocol_parser import ProtocolFrameParser
from gdw_send_frame_lib import GDWFrameGenerator
from gdw_frame_generator_schema import GDW_AFNFN_SCHEMA
from gdw10376_parser import GDW10376Parser
from dl_t698_45_frame_gen import DLT69845FrameGenerator
from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA, APDU_TYPE_LIST, OI_PRESET_LIST
from dl_t698_45_parser import DLT69845Parser
from preset_buttons import PresetButtonManager, AddPresetDialog
from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu, ZoomableTableWidget
from gdw_eb_di_lookup import get_eb_di_lookup
from gdw_eb_di_fields import EB_DI_FIELDS, encode_eb_di_data
from dlt645_frame_gen import DLT645FrameGenerator, describe_control, encode_di
from dlt645_frame_schema import (
    build_di_fields,
    get_command,
    length_warning,
    list_commands,
)
from dlt645_parser import DLT645Parser


# =============================================================================
# 通用字段模板类型定义
# =============================================================================

class CustomFieldTemplate:
    """通用字段模板项（参考图2模式）"""
    def __init__(self, name: str = "", length: int = 1, ftype: str = "uint8",
                 endian: str = "big", display: str = "hex", reverse: bool = False):
        self.name = name
        self.length = length
        self.ftype = ftype      # uint8/uint16/uint32/bytes/checksum
        self.endian = endian    # big/little
        self.display = display  # hex/dec
        self.reverse = reverse  # 字节反转（地址类）


class FrameGenWidget(QWidget):
    """协议组帧页面Widget"""

    # 当帧被添加到预设时发出（protocol, frame_hex, config_snapshot）
    preset_added = Signal(str, str, dict)
    # 当帧被添加到测试方案时发出（name, frame_hex）
    test_plan_added = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 协议模式: "south"=南网, "gdw"=国网, "dlt698"=698.45
        self.protocol_mode = "south"
        self.generator = ProtocolFrameGenerator()
        self.parser = ProtocolFrameParser()
        self.gdw_generator = GDWFrameGenerator()
        self.gdw_parser = GDW10376Parser()
        self.dlt698_generator = DLT69845FrameGenerator()
        self.dlt698_parser = DLT69845Parser()
        self._field_widgets: Dict[str, Dict[str, Any]] = {}
        self._current_di_key: Tuple[int, int, int, int] = None
        self._current_afn_fn: Tuple[int, int] = None
        self._current_dlt698_key: Tuple[str, str] = None  # (apdu_type, sub_type)
        self._form_container: QWidget = None
        self._custom_templates: List[CustomFieldTemplate] = []
        self._custom_mode = False
        self._axdr_mode = False
        self._axdr_items: list = []  # A-XDR tree items
        self._update_timer: QTimer = None
        self.serial_worker = None
        # EB 数据标识 645/698 帧生成器状态
        self._eb_fields_container: QWidget = None
        self._eb_field_widgets: Dict[str, Dict[str, Any]] = {}
        self._eb_list_widgets: Dict[str, Any] = {}
        self._eb_current_di: str = ""
        self.eb_gen_frame: str = ""
        self.setup_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # ================== 左侧面板 ==================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(4)

        # ---- 命令选择区（南网DI / 国网AFN+Fn） ----
        self.cmd_select_group = QGroupBox("DI 选择")
        cmd_layout = QHBoxLayout(self.cmd_select_group)
        cmd_layout.setContentsMargins(6, 4, 6, 4)
        cmd_layout.setSpacing(6)
        cmd_layout.addWidget(QLabel("选择命令："))

        # 南网DI选择
        self.di_combo = QComboBox()
        self.di_combo.setMinimumWidth(360)
        self.di_combo.setEditable(True)
        self.di_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.di_combo.completer().setCompletionMode(self.di_combo.completer().CompletionMode.PopupCompletion)
        self.di_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.di_combo.completer().popup().setStyleSheet(
            "background-color: #ffffff; color: #000000; selection-background-color: #2196F3; selection-color: #ffffff;"
        )
        self._populate_di_combo()
        self.di_combo.currentIndexChanged.connect(self._on_di_changed)
        cmd_layout.addWidget(self.di_combo)

        # 国网AFN+Fn选择（默认隐藏）
        self.afn_fn_combo = QComboBox()
        self.afn_fn_combo.setMinimumWidth(360)
        self.afn_fn_combo.setEditable(True)
        self.afn_fn_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.afn_fn_combo.completer().setCompletionMode(self.afn_fn_combo.completer().CompletionMode.PopupCompletion)
        self.afn_fn_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.afn_fn_combo.completer().popup().setStyleSheet(
            "background-color: #ffffff; color: #000000; selection-background-color: #2196F3; selection-color: #ffffff;"
        )
        self._populate_afn_fn_combo()
        self.afn_fn_combo.currentIndexChanged.connect(self._on_afn_fn_changed)
        self.afn_fn_combo.setVisible(False)
        cmd_layout.addWidget(self.afn_fn_combo)

        self.cmd_help_btn = QPushButton("命令说明")
        set_btn(self.cmd_help_btn, "warning", "sm")
        set_btn_icon(self.cmd_help_btn, "help")
        self.cmd_help_btn.setEnabled(False)
        self.cmd_help_btn.clicked.connect(self._on_cmd_help_clicked)
        cmd_layout.addWidget(self.cmd_help_btn)
        cmd_layout.addStretch()
        left_layout.addWidget(self.cmd_select_group)

        # ---- 帧配置（南网模式） ----
        self.south_config_group = QGroupBox("帧配置")
        south_config_layout = QHBoxLayout(self.south_config_group)
        south_config_layout.setContentsMargins(6, 4, 6, 4)
        south_config_layout.setSpacing(6)

        south_config_layout.addWidget(QLabel("源地址:"))
        self.src_addr_input = QLineEdit("000000000000")
        self.src_addr_input.setMaxLength(12)
        south_config_layout.addWidget(self.src_addr_input)

        south_config_layout.addWidget(QLabel("目的地址:"))
        self.dst_addr_input = QLineEdit("000000000000")
        self.dst_addr_input.setMaxLength(12)
        south_config_layout.addWidget(self.dst_addr_input)

        south_config_layout.addWidget(QLabel("DIR:"))
        self.dir_combo = QComboBox()
        self.dir_combo.addItem("0-下行(集中器→模块)", 0)
        self.dir_combo.addItem("1-上行(模块→集中器)", 1)
        south_config_layout.addWidget(self.dir_combo)

        south_config_layout.addWidget(QLabel("PRM:"))
        self.prm_combo = QComboBox()
        self.prm_combo.addItem("0-从动站", 0)
        self.prm_combo.addItem("1-启动站", 1)
        south_config_layout.addWidget(self.prm_combo)

        south_config_layout.addWidget(QLabel("ADD:"))
        self.add_combo = QComboBox()
        self.add_combo.addItem("0-不带地址域", 0)
        self.add_combo.addItem("1-带地址域", 1)
        south_config_layout.addWidget(self.add_combo)

        south_config_layout.addStretch()
        left_layout.addWidget(self.south_config_group)

        # ---- 国网帧配置（信息域R + 地址域A，默认隐藏） ----
        self.gdw_config_group = QGroupBox("国网帧配置")
        gdw_config_layout = QVBoxLayout(self.gdw_config_group)
        gdw_config_layout.setContentsMargins(6, 4, 6, 4)
        gdw_config_layout.setSpacing(4)

        # 信息域R配置
        info_layout = QHBoxLayout()
        info_layout.setSpacing(6)
        info_layout.addWidget(QLabel("通信方式:"))
        self.gdw_comm_type = QComboBox()
        self.gdw_comm_type.addItem("0-保留", 0)
        self.gdw_comm_type.addItem("1-集中式路由载波", 1)
        self.gdw_comm_type.addItem("2-分布式路由载波", 2)
        self.gdw_comm_type.addItem("3-HPLC载波", 3)
        self.gdw_comm_type.addItem("4-双模HDC", 4)
        self.gdw_comm_type.addItem("10-微功率无线", 10)
        self.gdw_comm_type.addItem("20-以太网", 20)
        info_layout.addWidget(self.gdw_comm_type)

        info_layout.addWidget(QLabel("DIR:"))
        self.gdw_dir = QComboBox()
        self.gdw_dir.addItem("0-下行", 0)
        self.gdw_dir.addItem("1-上行", 1)
        info_layout.addWidget(self.gdw_dir)

        info_layout.addWidget(QLabel("PRM:"))
        self.gdw_prm = QComboBox()
        self.gdw_prm.addItem("1-启动站", 1)
        self.gdw_prm.addItem("0-从动站", 0)
        info_layout.addWidget(self.gdw_prm)

        info_layout.addWidget(QLabel("序列号:"))
        self.gdw_seq = QLineEdit("0")
        self.gdw_seq.setFixedWidth(40)
        self.gdw_seq.setValidator(QIntValidator(0, 255, self.gdw_seq))
        self.gdw_seq.textChanged.connect(self._schedule_realtime_update)
        info_layout.addWidget(self.gdw_seq)
        info_layout.addStretch()
        gdw_config_layout.addLayout(info_layout)

        # 信息域R详细配置
        info_detail_layout = QHBoxLayout()
        info_detail_layout.setSpacing(6)

        info_detail_layout.addWidget(QLabel("路由标识:"))
        self.gdw_route_flag = QComboBox()
        self.gdw_route_flag.addItem("0-带路由", 0)
        self.gdw_route_flag.addItem("1-不带路由", 1)
        info_detail_layout.addWidget(self.gdw_route_flag)

        info_detail_layout.addWidget(QLabel("通信模块标识:"))
        self.gdw_comm_module = QComboBox()
        self.gdw_comm_module.addItem("0-对主节点", 0)
        self.gdw_comm_module.addItem("1-对从节点", 1)
        self.gdw_comm_module.currentIndexChanged.connect(self._on_gdw_comm_module_changed)
        info_detail_layout.addWidget(self.gdw_comm_module)

        info_detail_layout.addWidget(QLabel("中继级别:"))
        self.gdw_relay_level = QComboBox()
        for i in range(16):
            self.gdw_relay_level.addItem(f"{i}", i)
        self.gdw_relay_level.currentIndexChanged.connect(self._on_gdw_relay_level_changed)
        info_detail_layout.addWidget(self.gdw_relay_level)

        info_detail_layout.addWidget(QLabel("信道标识:"))
        self.gdw_channel = QLineEdit("0")
        self.gdw_channel.setFixedWidth(30)
        self.gdw_channel.setValidator(QIntValidator(0, 15, self.gdw_channel))
        self.gdw_channel.textChanged.connect(self._schedule_realtime_update)
        info_detail_layout.addWidget(self.gdw_channel)

        info_detail_layout.addWidget(QLabel("应答字节数:"))
        self.gdw_resp_bytes = QLineEdit("0")
        self.gdw_resp_bytes.setFixedWidth(40)
        self.gdw_resp_bytes.setValidator(QIntValidator(0, 255, self.gdw_resp_bytes))
        self.gdw_resp_bytes.textChanged.connect(self._schedule_realtime_update)
        info_detail_layout.addWidget(self.gdw_resp_bytes)

        info_detail_layout.addStretch()
        gdw_config_layout.addLayout(info_detail_layout)

        # 地址域配置
        addr_layout = QHBoxLayout()
        addr_layout.setSpacing(6)
        addr_layout.addWidget(QLabel("源地址(A1):"))
        self.gdw_src_addr = QLineEdit("000000000000")
        self.gdw_src_addr.setMaxLength(12)
        self.gdw_src_addr.setPlaceholderText("12位十进制BCD")
        self.gdw_src_addr.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d*"), self.gdw_src_addr))
        self.gdw_src_addr.textChanged.connect(self._schedule_realtime_update)
        addr_layout.addWidget(self.gdw_src_addr)

        addr_layout.addWidget(QLabel("目的地址(A3):"))
        self.gdw_dst_addr = QLineEdit("000000000000")
        self.gdw_dst_addr.setMaxLength(12)
        self.gdw_dst_addr.setPlaceholderText("12位十进制BCD")
        self.gdw_dst_addr.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d*"), self.gdw_dst_addr))
        self.gdw_dst_addr.textChanged.connect(self._schedule_realtime_update)
        addr_layout.addWidget(self.gdw_dst_addr)
        addr_layout.addStretch()
        gdw_config_layout.addLayout(addr_layout)

        # 中继地址（动态）
        self.gdw_relay_container = QWidget()
        self.gdw_relay_layout = QHBoxLayout(self.gdw_relay_container)
        self.gdw_relay_layout.setContentsMargins(0, 0, 0, 0)
        self.gdw_relay_layout.setSpacing(6)
        self.gdw_relay_layout.addWidget(QLabel("中继地址:"))
        self.gdw_relay_inputs: List[QLineEdit] = []
        gdw_config_layout.addWidget(self.gdw_relay_container)
        self.gdw_relay_container.setVisible(False)

        self.gdw_config_group.setVisible(False)
        left_layout.addWidget(self.gdw_config_group)

        # ---- 698.45 APDU选择（默认隐藏） ----
        self.dlt698_combo = QComboBox()
        self.dlt698_combo.setMinimumWidth(360)
        self.dlt698_combo.setEditable(True)
        self.dlt698_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dlt698_combo.completer().setCompletionMode(self.dlt698_combo.completer().CompletionMode.PopupCompletion)
        self.dlt698_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.dlt698_combo.completer().popup().setStyleSheet(
            "background-color: #ffffff; color: #000000; selection-background-color: #2196F3; selection-color: #ffffff;"
        )
        self._populate_dlt698_combo()
        self.dlt698_combo.currentIndexChanged.connect(self._on_dlt698_changed)
        self.dlt698_combo.setVisible(False)
        cmd_layout.addWidget(self.dlt698_combo)

        # ---- 698.45帧配置（默认隐藏） ----
        self.dlt698_config_group = QGroupBox("698.45 帧配置")
        dlt698_config_layout = QVBoxLayout(self.dlt698_config_group)
        dlt698_config_layout.setContentsMargins(6, 4, 6, 4)
        dlt698_config_layout.setSpacing(4)

        # 地址特征配置行
        addr_feat_layout = QHBoxLayout()
        addr_feat_layout.setSpacing(6)
        addr_feat_layout.addWidget(QLabel("地址类型:"))
        self.dlt698_addr_type = QComboBox()
        self.dlt698_addr_type.addItem("单地址", 0)
        self.dlt698_addr_type.addItem("通配地址", 1)
        self.dlt698_addr_type.addItem("组地址", 2)
        self.dlt698_addr_type.addItem("广播地址", 3)
        self.dlt698_addr_type.setToolTip("D7-D6: 地址类型")
        addr_feat_layout.addWidget(self.dlt698_addr_type)

        addr_feat_layout.addWidget(QLabel("逻辑地址:"))
        self.dlt698_logic_addr = QComboBox()
        self.dlt698_logic_addr.addItem("逻辑地址0", 0)
        self.dlt698_logic_addr.addItem("逻辑地址1", 1)
        self.dlt698_logic_addr.addItem("扩展逻辑地址(2~255)", 3)
        self.dlt698_logic_addr.setToolTip("D5-D4: 逻辑地址")
        addr_feat_layout.addWidget(self.dlt698_logic_addr)

        addr_feat_layout.addWidget(QLabel("地址长度:"))
        self.dlt698_addr_len = QComboBox()
        self.dlt698_addr_len.addItem("自动(广播=1)", 0)
        for i in range(1, 17):
            self.dlt698_addr_len.addItem(f"{i}", i)
        self.dlt698_addr_len.setCurrentText("6")
        self.dlt698_addr_len.setToolTip("D3-D0: 地址字节长度(1~16, 广播固定1)")
        addr_feat_layout.addWidget(self.dlt698_addr_len)

        addr_feat_layout.addWidget(QLabel("SA地址:"))
        self.dlt698_sa_raw = QLineEdit("000000000000")
        self.dlt698_sa_raw.setMaxLength(12)
        self.dlt698_sa_raw.setMinimumWidth(140)
        self.dlt698_sa_raw.setToolTip("服务器地址(不含特征字节)，自动补齐/截断到地址长度")
        addr_feat_layout.addWidget(self.dlt698_sa_raw)

        addr_feat_layout.addStretch()
        dlt698_config_layout.addLayout(addr_feat_layout)

        # 控制域 + CA 配置行
        dlt698_ctrl_layout = QHBoxLayout()
        dlt698_ctrl_layout.setSpacing(6)

        dlt698_ctrl_layout.addWidget(QLabel("CA:"))
        self.dlt698_ca = QLineEdit("0")
        self.dlt698_ca.setFixedWidth(30)
        self.dlt698_ca.setToolTip("客户机地址(1字节)")
        dlt698_ctrl_layout.addWidget(self.dlt698_ca)

        dlt698_ctrl_layout.addWidget(QLabel("DIR:"))
        self.dlt698_dir = QComboBox()
        self.dlt698_dir.addItem("0-客户机→服务器", 0)
        self.dlt698_dir.addItem("1-服务器→客户机", 1)
        dlt698_ctrl_layout.addWidget(self.dlt698_dir)

        dlt698_ctrl_layout.addWidget(QLabel("PRM:"))
        self.dlt698_prm = QComboBox()
        self.dlt698_prm.addItem("1-发起(请求)", 1)
        self.dlt698_prm.addItem("0-响应", 0)
        dlt698_ctrl_layout.addWidget(self.dlt698_prm)

        dlt698_ctrl_layout.addWidget(QLabel("SC:"))
        self.dlt698_sc = QComboBox()
        self.dlt698_sc.addItem("0-不加扰", 0)
        self.dlt698_sc.addItem("1-加扰码", 1)
        dlt698_ctrl_layout.addWidget(self.dlt698_sc)

        dlt698_ctrl_layout.addWidget(QLabel("分帧:"))
        self.dlt698_seg = QComboBox()
        self.dlt698_seg.addItem("0-完整", 0)
        self.dlt698_seg.addItem("1-分帧", 1)
        dlt698_ctrl_layout.addWidget(self.dlt698_seg)

        dlt698_ctrl_layout.addWidget(QLabel("功能码:"))
        self.dlt698_func = QComboBox()
        self.dlt698_func.addItem("3-用户数据", 3)
        self.dlt698_func.addItem("1-链路管理", 1)
        dlt698_ctrl_layout.addWidget(self.dlt698_func)
        dlt698_ctrl_layout.addStretch()
        dlt698_config_layout.addLayout(dlt698_ctrl_layout)

        self.dlt698_config_group.setVisible(False)
        left_layout.addWidget(self.dlt698_config_group)

        # ---- DLT645-2007（协议6）命令选择 + 帧配置（默认隐藏）----
        self._dlt645_gen = DLT645FrameGenerator()
        self._current_dlt645_key = None
        self._dlt645_field_widgets: Dict[str, QLineEdit] = {}
        self._dlt645_addr_touched = False
        self._dlt645_addr_programmatic = False

        self.dlt645_combo = QComboBox()
        self.dlt645_combo.setMinimumWidth(360)
        self.dlt645_combo.setEditable(True)
        self.dlt645_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dlt645_combo.completer().setCompletionMode(
            self.dlt645_combo.completer().CompletionMode.PopupCompletion)
        self.dlt645_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.dlt645_combo.completer().popup().setStyleSheet(
            "background-color: #ffffff; color: #000000; "
            "selection-background-color: #2196F3; selection-color: #ffffff;"
        )
        self._populate_dlt645_combo()
        self.dlt645_combo.currentIndexChanged.connect(self._on_dlt645_cmd_changed)
        self.dlt645_combo.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt645_combo.setVisible(False)
        cmd_layout.addWidget(self.dlt645_combo)

        self.dlt645_config_group = QGroupBox("DLT645-2007 帧配置")
        d645_layout = QVBoxLayout(self.dlt645_config_group)
        d645_layout.setContentsMargins(6, 4, 6, 4)
        d645_layout.setSpacing(4)

        d645_addr_row = QHBoxLayout()
        d645_addr_row.setSpacing(6)
        d645_addr_row.addWidget(QLabel("表地址:"))
        # 可编辑下拉：内置地址类型（广播/通配/全零）+ 历史输入过的地址（持久化），
        # 也可直接手动输入 12 位地址
        self.dlt645_addr = QComboBox()
        self.dlt645_addr.setEditable(True)
        self.dlt645_addr.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dlt645_addr.setMinimumWidth(200)
        self.dlt645_addr.completer().setCompletionMode(
            self.dlt645_addr.completer().CompletionMode.PopupCompletion)
        self.dlt645_addr.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.dlt645_addr.setToolTip(
            "12 位地址（书写序，高位在前），线上自动转为低字节在前；\n"
            "下拉可选 广播/通配/全零 或历史输入过的地址，也可直接输入")
        self._dlt645_addr_defaults = [
            "999999999999", "AAAAAAAAAAAA", "000000000000"]
        self._dlt645_addr_history = self._load_dlt645_addr_history()
        self._refresh_dlt645_addr_items()
        self.dlt645_addr.setCurrentText("000000000000")
        self.dlt645_addr.editTextChanged.connect(self._on_dlt645_addr_edited)
        self.dlt645_addr.editTextChanged.connect(self._schedule_realtime_update)
        self.dlt645_addr.currentIndexChanged.connect(self._on_dlt645_addr_selected)
        d645_addr_row.addWidget(self.dlt645_addr, 1)
        self.dlt645_addr_type_label = QLabel("")
        self.dlt645_addr_type_label.setStyleSheet("color: #666;")
        d645_addr_row.addWidget(self.dlt645_addr_type_label)
        self.dlt645_broadcast = QCheckBox("广播")
        self.dlt645_broadcast.setToolTip("勾选后地址域自动填当前命令的广播地址")
        self.dlt645_broadcast.toggled.connect(self._on_dlt645_broadcast)
        self.dlt645_broadcast.toggled.connect(self._schedule_realtime_update)
        d645_addr_row.addWidget(self.dlt645_broadcast)
        d645_layout.addLayout(d645_addr_row)

        self.dlt645_ctrl_label = QLabel("")
        self.dlt645_ctrl_label.setStyleSheet("color: #666;")
        self.dlt645_ctrl_label.setWordWrap(True)
        d645_layout.addWidget(self.dlt645_ctrl_label)

        self.dlt645_di_row = QWidget()
        d645_di_row_layout = QHBoxLayout(self.dlt645_di_row)
        d645_di_row_layout.setContentsMargins(0, 0, 0, 0)
        d645_di_row_layout.setSpacing(6)
        d645_di_row_layout.addWidget(QLabel("数据标识:"))
        self.dlt645_di_combo = QComboBox()
        self.dlt645_di_combo.setMinimumWidth(360)
        self.dlt645_di_combo.setEditable(True)
        self.dlt645_di_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dlt645_di_combo.completer().setCompletionMode(
            self.dlt645_di_combo.completer().CompletionMode.PopupCompletion)
        self.dlt645_di_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.dlt645_di_combo.setToolTip("可直接输入 8 位 DI，或输入中文关键词搜索（1099 条）")
        self._populate_dlt645_di_combo()
        self.dlt645_di_combo.currentIndexChanged.connect(self._on_dlt645_di_changed)
        self.dlt645_di_combo.editTextChanged.connect(self._on_dlt645_di_changed)
        self.dlt645_di_combo.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt645_di_combo.editTextChanged.connect(self._schedule_realtime_update)
        d645_di_row_layout.addWidget(self.dlt645_di_combo, 1)
        d645_layout.addWidget(self.dlt645_di_row)

        self.dlt645_di_info = QLabel("")
        self.dlt645_di_info.setStyleSheet("color: #888;")
        self.dlt645_di_info.setWordWrap(True)
        d645_layout.addWidget(self.dlt645_di_info)

        self.dlt645_field_container = QWidget()
        self.dlt645_field_layout = QVBoxLayout(self.dlt645_field_container)
        self.dlt645_field_layout.setContentsMargins(0, 0, 0, 0)
        self.dlt645_field_layout.setSpacing(4)
        d645_layout.addWidget(self.dlt645_field_container)

        self.dlt645_verify_label = QLabel("")
        self.dlt645_verify_label.setWordWrap(True)
        d645_layout.addWidget(self.dlt645_verify_label)

        self.dlt645_warn_label = QLabel("")
        self.dlt645_warn_label.setStyleSheet("color: #E65100;")
        self.dlt645_warn_label.setWordWrap(True)
        d645_layout.addWidget(self.dlt645_warn_label)

        self.dlt645_config_group.setVisible(False)
        left_layout.addWidget(self.dlt645_config_group)

        # ---- 模式切换 ----
        self.mode_group = QGroupBox("字段模式")
        mode_layout = QHBoxLayout(self.mode_group)
        mode_layout.setContentsMargins(6, 4, 6, 4)
        mode_layout.setSpacing(6)
        self.mode_predefined_rb = QCheckBox("使用预定义字段")
        self.mode_predefined_rb.setChecked(True)
        self.mode_predefined_rb.stateChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_predefined_rb)

        self.mode_custom_rb = QCheckBox("使用自定义字段模板")
        self.mode_custom_rb.stateChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_custom_rb)

        self.mode_axdr_rb = QCheckBox("A-XDR自定义数据")
        self.mode_axdr_rb.stateChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_axdr_rb)
        mode_layout.addStretch()
        left_layout.addWidget(self.mode_group)

        # ---- EB 数据标识 645/698 帧生成器（仅协议7 国网显示） ----
        self._build_eb_gen_group(left_layout)

        # ---- 动态表单区 ----
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        self._form_container = QWidget()
        self._form_layout = QVBoxLayout(self._form_container)
        self._form_layout.setAlignment(Qt.AlignTop)
        form_scroll.setWidget(self._form_container)
        left_layout.addWidget(form_scroll, 1)

        # ---- 生成按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        self.generate_btn = QPushButton("生成帧")
        set_btn(self.generate_btn, "success")
        set_btn_icon(self.generate_btn, "apply")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.generate_btn)
        btn_layout.addStretch()
        left_layout.addLayout(btn_layout)

        # ---- 结果显示 ----
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        result_layout.setContentsMargins(6, 4, 6, 4)
        result_layout.setSpacing(4)
        self.result_hex = QTextEdit()
        self.result_hex.setReadOnly(True)
        self.result_hex.setMaximumHeight(36)
        self.result_hex.setFont(QFont("Consolas", 10))
        result_layout.addWidget(self.result_hex)
        left_layout.addWidget(result_group)

        # ---- 串口发送按钮 + 添加到预设 ----
        serial_btn_layout = QHBoxLayout()
        serial_btn_layout.setSpacing(6)
        self.send_serial_btn = QPushButton("发送到串口")
        set_btn(self.send_serial_btn, "primary")
        set_btn_icon(self.send_serial_btn, "play")
        self.send_serial_btn.clicked.connect(self._on_send_to_serial)
        serial_btn_layout.addWidget(self.send_serial_btn)

        self.add_preset_btn = QPushButton("添加到预设")
        set_btn(self.add_preset_btn, "warning")
        set_btn_icon(self.add_preset_btn, "add")
        self.add_preset_btn.clicked.connect(self._on_add_to_preset_clicked)
        serial_btn_layout.addWidget(self.add_preset_btn)

        self.add_test_plan_btn = QPushButton("添加到测试方案")
        set_btn(self.add_test_plan_btn, "accent")
        set_btn_icon(self.add_test_plan_btn, "add")
        self.add_test_plan_btn.clicked.connect(self._on_add_to_test_plan_clicked)
        serial_btn_layout.addWidget(self.add_test_plan_btn)

        self.clear_log_btn = QPushButton("清空日志")
        set_btn(self.clear_log_btn, "secondary")
        set_btn_icon(self.clear_log_btn, "clear")
        self.clear_log_btn.clicked.connect(self._on_clear_serial_log)
        serial_btn_layout.addWidget(self.clear_log_btn)
        serial_btn_layout.addStretch()
        left_layout.addLayout(serial_btn_layout)

        # ---- 串口日志 ----
        log_group = QGroupBox("串口日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 4, 6, 4)
        log_layout.setSpacing(4)
        self.serial_log = QTextEdit()
        self.serial_log.setReadOnly(True)
        self.serial_log.setMaximumHeight(120)
        self.serial_log.setFont(QFont("Consolas", 9))
        self.serial_log.setContextMenuPolicy(Qt.CustomContextMenu)
        self.serial_log.customContextMenuRequested.connect(self._on_serial_log_context_menu)
        log_layout.addWidget(self.serial_log)
        left_layout.addWidget(log_group)

        splitter.addWidget(left_widget)

        # ================== 右侧面板（实时解析预览） ==================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(4)

        preview_group = QGroupBox("实时解析预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 4, 6, 4)
        preview_layout.setSpacing(4)

        self.preview_table = ZoomableTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        header = self.preview_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.preview_table.setColumnWidth(0, 130)
        self.preview_table.setColumnWidth(1, 100)
        self.preview_table.setColumnWidth(2, 100)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().hide()
        table_font = QFont()
        table_font.setPointSize(7)
        self.preview_table.setFont(table_font)
        self.preview_table.verticalHeader().setDefaultSectionSize(10)

        preview_layout.addWidget(self.preview_table)
        right_layout.addWidget(preview_group, 1)

        # ---- 响应帧解析 ----
        resp_group = QGroupBox("响应帧解析")
        resp_layout = QVBoxLayout(resp_group)
        resp_layout.setContentsMargins(6, 4, 6, 4)
        resp_layout.setSpacing(4)

        self.response_table = ZoomableTableWidget()
        self.response_table.setColumnCount(4)
        self.response_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        resp_header = self.response_table.horizontalHeader()
        resp_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        resp_header.setStretchLastSection(True)
        self.response_table.setColumnWidth(0, 130)
        self.response_table.setColumnWidth(1, 100)
        self.response_table.setColumnWidth(2, 100)
        self.response_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.response_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.response_table.setAlternatingRowColors(True)
        self.response_table.verticalHeader().hide()
        resp_font = QFont()
        resp_font.setPointSize(7)
        self.response_table.setFont(resp_font)
        self.response_table.verticalHeader().setDefaultSectionSize(10)

        resp_layout.addWidget(self.response_table)

        # 清空响应解析按钮
        resp_btn_layout = QHBoxLayout()
        self.clear_resp_btn = QPushButton("清空响应解析")
        set_btn(self.clear_resp_btn, "secondary")
        set_btn_icon(self.clear_resp_btn, "clear")
        self.clear_resp_btn.clicked.connect(self._on_clear_response_table)
        resp_btn_layout.addWidget(self.clear_resp_btn)
        resp_btn_layout.addStretch()
        resp_layout.addLayout(resp_btn_layout)

        right_layout.addWidget(resp_group, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([700, 500])
        main_layout.addWidget(splitter)

        # ---- 连接固定控件的实时更新信号 ----
        self.src_addr_input.textChanged.connect(self._schedule_realtime_update)
        self.dst_addr_input.textChanged.connect(self._schedule_realtime_update)
        self.dir_combo.currentIndexChanged.connect(self._schedule_realtime_update)
        self.prm_combo.currentIndexChanged.connect(self._schedule_realtime_update)
        self.add_combo.currentIndexChanged.connect(self._schedule_realtime_update)

        # ---- 连接国网控件的实时更新信号 ----
        self.gdw_comm_type.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_dir.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_prm.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_seq.textChanged.connect(self._schedule_realtime_update)
        self.gdw_route_flag.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_comm_module.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_relay_level.currentIndexChanged.connect(self._schedule_realtime_update)
        self.gdw_channel.textChanged.connect(self._schedule_realtime_update)
        self.gdw_resp_bytes.textChanged.connect(self._schedule_realtime_update)
        self.gdw_src_addr.textChanged.connect(self._schedule_realtime_update)
        self.gdw_dst_addr.textChanged.connect(self._schedule_realtime_update)

        # ---- 连接698.45控件的实时更新信号 ----
        self.dlt698_addr_type.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt698_logic_addr.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt698_addr_len.currentIndexChanged.connect(self._on_dlt698_addr_len_changed)
        self.dlt698_addr_len.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt698_sa_raw.textChanged.connect(self._schedule_realtime_update)
        self.dlt698_ca.textChanged.connect(self._schedule_realtime_update)
        self.dlt698_dir.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt698_prm.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt698_sc.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt698_seg.currentIndexChanged.connect(self._schedule_realtime_update)
        self.dlt698_func.currentIndexChanged.connect(self._schedule_realtime_update)

        # 初始化 SA 输入框长度限制
        self._on_dlt698_addr_len_changed(0)

        apply_chinese_context_menus(self)

    # ------------------------------------------------------------------
    # OI 下拉框联动
    # ------------------------------------------------------------------
    def _on_oi_combo_changed(self, index: int):
        """OI 预设下拉框选择改变时，同步值到旁边的文本输入框"""
        combo = self.sender()
        if combo is None:
            return
        val = combo.currentData()
        if val is None:
            return
        # 找到对应的 edit 控件并写入十六进制值
        for widget_info in self._field_widgets.values():
            if widget_info.get("widget") is combo:
                edit = widget_info.get("edit")
                if edit:
                    edit.setText(f"{val:04X}")
                break
        self._schedule_realtime_update()

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------
    def _on_mode_changed(self, state):
        sender = self.sender()
        if sender == self.mode_predefined_rb and self.mode_predefined_rb.isChecked():
            self.mode_custom_rb.setChecked(False)
            self.mode_axdr_rb.setChecked(False)
            self._custom_mode = False
            self._axdr_mode = False
        elif sender == self.mode_custom_rb and self.mode_custom_rb.isChecked():
            if self.protocol_mode == "dlt698":
                self.mode_custom_rb.setChecked(False)
                self.mode_predefined_rb.setChecked(True)
                self._custom_mode = False
                self._axdr_mode = False
            else:
                self.mode_predefined_rb.setChecked(False)
                self.mode_axdr_rb.setChecked(False)
                self._custom_mode = True
                self._axdr_mode = False
        elif sender == self.mode_axdr_rb and self.mode_axdr_rb.isChecked():
            self.mode_predefined_rb.setChecked(False)
            self.mode_custom_rb.setChecked(False)
            self._custom_mode = False
            self._axdr_mode = True
        else:
            # 确保至少选中一个
            if not self.mode_predefined_rb.isChecked() and not self.mode_custom_rb.isChecked() and not self.mode_axdr_rb.isChecked():
                self.mode_predefined_rb.setChecked(True)
                self._custom_mode = False
                self._axdr_mode = False
        # 仅重新构建字段表单区（不清空模式切换控件本身）
        if self.protocol_mode == "south":
            self._rebuild_field_form(self._current_di_key)
        elif self.protocol_mode == "dlt698":
            self._rebuild_dlt698_field_form(self._current_dlt698_key)
        else:
            self._rebuild_gdw_field_form(self._current_afn_fn)

    # ------------------------------------------------------------------
    # EB 数据标识 645/698 帧生成器（协议7 国网 52H-F1/56H-F2 报文内容辅助）
    # ------------------------------------------------------------------
    EB_CTRL_OPTIONS = [
        ("91H 读数据响应", "91"),
        ("11H 读数据请求", "11"),
        ("14H 写数据请求", "14"),
        ("94H 写数据响应", "94"),
        ("81H 主动上报", "81"),
        ("01H 上报确认", "01"),
    ]
    EB_698_SERVICES = [
        ("GET-Request 读取", "GET-Request"),
        ("GET-Response 读响应", "GET-Response"),
        ("SET-Request 设置/配置", "SET-Request"),
        ("SET-Response 写确认", "SET-Response"),
        ("ACTION-Request 操作", "ACTION-Request"),
        ("ACTION-Response 操作响应", "ACTION-Response"),
        ("REPORT-Notification 主动上报", "REPORT-Notification"),
        ("REPORT-Response 上报确认", "REPORT-Response"),
    ]

    def _build_eb_gen_group(self, parent_layout: QVBoxLayout):
        """构建 EB 数据标识 645/698 帧生成器面板（仅协议7 显示）"""
        self.eb_gen_group = QGroupBox("EB 数据标识 645/698 帧生成器")
        self.eb_gen_group.setCheckable(True)
        self.eb_gen_group.setChecked(True)
        self.eb_gen_group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #B0BEC5; border-radius: 4px; margin-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        eb_layout = QVBoxLayout(self.eb_gen_group)
        eb_layout.setContentsMargins(6, 4, 6, 4)
        eb_layout.setSpacing(4)

        # 承载格式 + EB 数据标识
        sel_row = QHBoxLayout()
        sel_row.setSpacing(6)
        sel_row.addWidget(QLabel("承载格式:"))
        self.eb_format_combo = QComboBox()
        self.eb_format_combo.addItem("645 帧（68 封装）", "645")
        self.eb_format_combo.addItem("698.45 完整帧", "698")
        self.eb_format_combo.currentIndexChanged.connect(self._on_eb_format_changed)
        sel_row.addWidget(self.eb_format_combo)
        sel_row.addWidget(QLabel("EB数据标识:"))
        self.eb_di_combo = QComboBox()
        self.eb_di_combo.setMinimumWidth(240)
        self.eb_di_combo.setEditable(True)
        self.eb_di_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.eb_di_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.eb_di_combo.currentIndexChanged.connect(self._on_eb_di_changed)
        sel_row.addWidget(self.eb_di_combo, 1)
        eb_layout.addLayout(sel_row)

        # ---- 645 模式配置 ----
        self.eb_645_widget = QWidget()
        eb645 = QHBoxLayout(self.eb_645_widget)
        eb645.setContentsMargins(0, 0, 0, 0)
        eb645.setSpacing(6)
        eb645.addWidget(QLabel("控制码:"))
        self.eb_ctrl_combo = QComboBox()
        for label, val in self.EB_CTRL_OPTIONS:
            self.eb_ctrl_combo.addItem(label, val)
        eb645.addWidget(self.eb_ctrl_combo)
        eb645.addWidget(QLabel("地址域A0~A5(hex):"))
        self.eb_addr_edit = QLineEdit("000000000000")
        self.eb_addr_edit.setMaxLength(12)
        self.eb_addr_edit.setFixedWidth(110)
        self.eb_addr_edit.setToolTip("12位hex（6字节）")
        eb645.addWidget(self.eb_addr_edit)
        eb645.addWidget(QLabel("数据内容(hex):"))
        self.eb_data_edit = QLineEdit()
        self.eb_data_edit.setPlaceholderText("可留空，如 01 01 112233445566")
        eb645.addWidget(self.eb_data_edit, 1)
        eb_layout.addWidget(self.eb_645_widget)

        # ---- 698 模式配置 ----
        self.eb_698_widget = QWidget()
        eb698_top = QVBoxLayout(self.eb_698_widget)
        eb698_top.setContentsMargins(0, 0, 0, 0)
        eb698_top.setSpacing(4)
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.addWidget(QLabel("数据内容来源:"))
        self.eb_698_src_combo = QComboBox()
        self.eb_698_src_combo.addItem("按字段配置（推荐）", 1)
        self.eb_698_src_combo.addItem("直接填 hex", 0)
        self.eb_698_src_combo.currentIndexChanged.connect(self._on_eb_format_changed)
        row1.addWidget(self.eb_698_src_combo)
        row1.addWidget(QLabel("698 服务:"))
        self.eb_698_service_combo = QComboBox()
        for label, val in self.EB_698_SERVICES:
            self.eb_698_service_combo.addItem(label, val)
        self.eb_698_service_combo.setCurrentIndex(2)  # SET-Request
        row1.addWidget(self.eb_698_service_combo, 1)
        eb698_top.addLayout(row1)

        # 698 链路层头部
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(QLabel("SA类型:"))
        self.eb_698_addr_type = QComboBox()
        self.eb_698_addr_type.addItem("单地址(0)", 0)
        self.eb_698_addr_type.addItem("通配地址(1)", 1)
        self.eb_698_addr_type.addItem("组地址(2)", 2)
        self.eb_698_addr_type.addItem("广播地址(3)", 3)
        row2.addWidget(self.eb_698_addr_type)
        row2.addWidget(QLabel("SA长度:"))
        self.eb_698_addr_len = QComboBox()
        for i in range(1, 17):
            self.eb_698_addr_len.addItem(f"{i}", i)
        self.eb_698_addr_len.setCurrentText("6")
        row2.addWidget(self.eb_698_addr_len)
        row2.addWidget(QLabel("SA(hex):"))
        self.eb_698_sa_edit = QLineEdit("000000000000")
        self.eb_698_sa_edit.setFixedWidth(100)
        row2.addWidget(self.eb_698_sa_edit)
        row2.addWidget(QLabel("CA:"))
        self.eb_698_ca_edit = QLineEdit("0")
        self.eb_698_ca_edit.setFixedWidth(30)
        row2.addWidget(self.eb_698_ca_edit)
        eb698_top.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(6)
        row3.addWidget(QLabel("DIR:"))
        self.eb_698_dir = QComboBox()
        self.eb_698_dir.addItem("0-客户机→服务器", 0)
        self.eb_698_dir.addItem("1-服务器→客户机", 1)
        row3.addWidget(self.eb_698_dir)
        row3.addWidget(QLabel("PRM:"))
        self.eb_698_prm = QComboBox()
        self.eb_698_prm.addItem("1-启动站", 1)
        self.eb_698_prm.addItem("0-从动站", 0)
        row3.addWidget(self.eb_698_prm)
        row3.addWidget(QLabel("功能码:"))
        self.eb_698_func = QComboBox()
        self.eb_698_func.addItem("3-用户数据", 3)
        self.eb_698_func.addItem("1-链路管理", 1)
        row3.addWidget(self.eb_698_func)
        row3.addWidget(QLabel("自由数据hex:"))
        self.eb_698_data_edit = QLineEdit()
        self.eb_698_data_edit.setPlaceholderText("A-XDR octet-string 内容")
        row3.addWidget(self.eb_698_data_edit, 1)
        eb698_top.addLayout(row3)
        eb_layout.addWidget(self.eb_698_widget)

        # 数据字段表单（按 EB 数据项 schema，复用 _create_field_widget）
        self._eb_fields_container = QWidget()
        self._eb_fields_layout = QVBoxLayout(self._eb_fields_container)
        self._eb_fields_layout.setContentsMargins(0, 0, 0, 0)
        self._eb_fields_layout.setSpacing(2)
        self._eb_fields_layout.setAlignment(Qt.AlignTop)
        eb_fields_scroll = QScrollArea()
        eb_fields_scroll.setWidgetResizable(True)
        eb_fields_scroll.setMaximumHeight(260)
        eb_fields_scroll.setWidget(self._eb_fields_container)
        eb_layout.addWidget(eb_fields_scroll)

        # 生成按钮 + 消息
        gen_row = QHBoxLayout()
        gen_row.setSpacing(6)
        self.eb_gen_btn = QPushButton("生成帧")
        set_btn(self.eb_gen_btn, "primary")
        set_btn_icon(self.eb_gen_btn, "apply")
        self.eb_gen_btn.clicked.connect(self._gen_eb_frame)
        gen_row.addWidget(self.eb_gen_btn)
        self.eb_apply_btn = QPushButton("填入报文内容字段")
        set_btn(self.eb_apply_btn, "success")
        set_btn_icon(self.eb_apply_btn, "apply")
        self.eb_apply_btn.clicked.connect(self._apply_eb_to_content)
        gen_row.addWidget(self.eb_apply_btn)
        self.eb_gen_msg = QLabel("")
        self.eb_gen_msg.setStyleSheet("font-size: 11px;")
        self.eb_gen_msg.setWordWrap(True)
        gen_row.addWidget(self.eb_gen_msg, 1)
        gen_row.addStretch()
        eb_layout.addLayout(gen_row)

        # 生成的 EB 帧（只读显示）
        self.eb_gen_result = QLineEdit()
        self.eb_gen_result.setReadOnly(True)
        self.eb_gen_result.setFont(QFont("Consolas", 9))
        self.eb_gen_result.setPlaceholderText("生成的 EB 645/698 帧显示在此")
        eb_layout.addWidget(self.eb_gen_result)

        self.eb_gen_group.setVisible(False)
        parent_layout.addWidget(self.eb_gen_group)

        # 最后填充 EB 数据标识下拉（此时 _eb_fields_layout 已存在）
        self._populate_eb_di_combo()
        # 连接 645/698 输入控件实时刷新（仅生成按钮触发，不需实时，故不连）
        self.eb_698_widget.setVisible(False)
        self._on_eb_format_changed(0)

    def _populate_eb_di_combo(self):
        """填充 EB 数据标识下拉框（gdw_eb_di_lookup 57 项）"""
        self.eb_di_combo.clear()
        self.eb_di_combo.addItem("-- 请选择 EB 数据标识 --", None)
        try:
            lookup = get_eb_di_lookup()
            for code, info in sorted(lookup.get_all().items()):
                label = f"{code} {info.get('名称', '')}"
                self.eb_di_combo.addItem(label, code)
        except Exception:
            pass

    def _on_eb_format_changed(self, index: int):
        """承载格式 645/698 切换：切换配置面板与字段表单"""
        fmt = self.eb_format_combo.currentData()
        is_698 = (fmt == "698")
        self.eb_645_widget.setVisible(not is_698)
        self.eb_698_widget.setVisible(is_698)
        self._rebuild_eb_fields()

    def _on_eb_di_changed(self, index: int):
        """EB 数据标识改变：重建数据字段表单"""
        self._eb_current_di = self.eb_di_combo.currentData() or ""
        self._rebuild_eb_fields()

    def _rebuild_eb_fields(self):
        """按当前 EB 数据标识重建数据字段表单（复用 _create_field_widget）"""
        if not hasattr(self, '_eb_fields_layout'):
            return
        self._clear_layout(self._eb_fields_layout)
        self._eb_field_widgets.clear()
        self._eb_list_widgets.clear()

        di = self._eb_current_di
        fmt = self.eb_format_combo.currentData()
        use_field = (fmt == "698") and self.eb_698_src_combo.currentData() == 1
        info = EB_DI_FIELDS.get(di)
        if not info or not use_field:
            hint = QLabel("当前数据项无字段定义，请使用「数据内容 hex」直接填写。")
            hint.setStyleSheet("color: #888; font-size: 11px;")
            hint.setWordWrap(True)
            self._eb_fields_layout.addWidget(hint)
            return
        title = QLabel(f"<b>数据内容字段（{info.get('名称', di)}）</b>")
        self._eb_fields_layout.addWidget(title)
        for field in info.get("fields", []):
            widget = self._create_field_widget(field, widget_store=self._eb_field_widgets)
            if widget:
                # list 类型：实际 list widget（带 _items）存在 _eb_field_widgets[name]["widget"]
                if field.get("type") == "list":
                    lw = self._eb_field_widgets.get(field["name"], {}).get("widget")
                    if lw is not None and hasattr(lw, "_items"):
                        self._eb_list_widgets[field["name"]] = lw
                self._eb_fields_layout.addWidget(widget)
        apply_chinese_context_menus(self._eb_fields_container)

    def _collect_eb_field_values(self) -> Dict[str, Any]:
        """收集 EB 数据字段表单值 {字段名: 值}（list 从 _items 读取）"""
        values: Dict[str, Any] = {}
        info = EB_DI_FIELDS.get(self._eb_current_di, {})
        for field in info.get("fields", []):
            name = field["name"]
            ftype = field.get("type", "hex")
            if ftype == "list":
                widget = self._eb_list_widgets.get(name)
                if widget is None:
                    widget = self._eb_field_widgets.get(name, {}).get("widget")
                items = []
                if widget is not None and hasattr(widget, "_items"):
                    for _, item_widgets in widget._items:
                        item = {}
                        for iname, iw in item_widgets.items():
                            if isinstance(iw, QComboBox):
                                item[iname] = iw.currentData()
                            else:
                                item[iname] = iw.text().strip()
                        items.append(item)
                values[name] = items
            else:
                wi = self._eb_field_widgets.get(name, {})
                w = wi.get("widget")
                if w is None:
                    values[name] = field.get("default", "")
                    continue
                if isinstance(w, QComboBox):
                    values[name] = w.currentData()
                else:
                    values[name] = w.text().strip()
        return values

    def _build_eb_645_frame(self) -> bytes:
        """生成 EB 数据标识 645 帧: 68 A0..A5 68 C L DI3 DI2 DI1 DI0 DATA CS 16

        标准口径：数据域逐字节 +0x33、CS 覆盖帧头（含两个 68H 与地址域）。
        统一调用 DLT645FrameGenerator——此前此处手写封装 CS 漏算帧头且未加扰，
        产出的帧真实设备不认、本工具解析器也判非法。
        """
        di = self._eb_current_di
        if not di or not di.startswith("EB") or len(di) != 8:
            raise ValueError("请先选择 EB 数据标识（如 EB030002）")
        ctrl = int(self.eb_ctrl_combo.currentData(), 16)
        data = bytes.fromhex(self.eb_data_edit.text().replace(" ", "")) if self.eb_data_edit.text().strip() else b""
        addr = bytes.fromhex(self.eb_addr_edit.text().replace(" ", ""))
        if len(addr) != 6:
            addr = addr[:6].ljust(6, b'\x00')
        return self._dlt645_gen.build_frame(
            addr, ctrl, encode_di(di) + data)

    def _build_eb_698_frame(self) -> bytes:
        """生成 EB 数据标识 698.45 完整帧（68 L C SA CA HCS APDU FCS 16）"""
        di = self._eb_current_di
        if not di or not di.startswith("EB") or len(di) != 8:
            raise ValueError("请先选择 EB 数据标识（如 EB030002）")
        service = self.eb_698_service_combo.currentData()
        data_hex = self.eb_698_data_edit.text().strip()
        if self.eb_698_src_combo.currentData() == 1 and di in EB_DI_FIELDS:
            try:
                data_bytes = encode_eb_di_data(di, self._collect_eb_field_values())
                data_hex = data_bytes.hex()
            except Exception:
                data_hex = self.eb_698_data_edit.text().strip()

        try:
            import sys as _sys, os as _os
            _reflex_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "reflex_web")
            if _reflex_dir not in _sys.path:
                _sys.path.insert(0, _reflex_dir)
            from frame_gen_utils import build_eb_698_frame, build_dlt698_sa
        except ImportError:
            raise ValueError("缺少 reflex_web/frame_gen_utils.py，无法生成 698 帧")
        addr_type = self.eb_698_addr_type.currentData()
        addr_len = self.eb_698_addr_len.currentData()
        sa_raw = self.eb_698_sa_edit.text().strip()
        sa = build_dlt698_sa(addr_type, 0, addr_len, sa_raw)
        ca_text = self.eb_698_ca_edit.text().strip()
        try:
            ca = int(ca_text, 0) & 0xFF
        except (ValueError, TypeError):
            ca = 0
        frame = build_eb_698_frame(
            di, service, data_hex,
            sa=sa, ca=ca,
            dir_bit=self.eb_698_dir.currentData(),
            prm_bit=self.eb_698_prm.currentData(),
            func_code=self.eb_698_func.currentData(),
        )
        if isinstance(frame, bytes):
            return frame
        return bytes.fromhex(frame.replace(" ", ""))

    def _gen_eb_frame(self):
        """生成 EB 645/698 帧并显示"""
        try:
            fmt = self.eb_format_combo.currentData()
            if fmt == "698":
                frame = self._build_eb_698_frame()
            else:
                frame = self._build_eb_645_frame()
            self.eb_gen_frame = frame.hex()
            hex_str = frame.hex().upper()
            formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            self.eb_gen_result.setText(formatted)
            lookup = get_eb_di_lookup()
            name = lookup.get(self._eb_current_di).get("名称", "") if lookup.get(self._eb_current_di) else ""
            self._set_eb_msg(f"已生成 {self._eb_current_di} {name} {'698' if fmt == '698' else '645'} 帧（{len(frame)} 字节）", False)
        except Exception as e:
            self._set_eb_msg(f"生成失败: {e}", True)

    def _apply_eb_to_content(self):
        """将生成的 EB 帧填入当前国网命令的「报文内容」字段"""
        if not self.eb_gen_frame:
            self._set_eb_msg("请先生成 EB 帧", True)
            return
        if self.protocol_mode != "gdw" or not self._current_afn_fn:
            self._set_eb_msg("请先在协议7 组帧页选择 52H-F1 等命令", True)
            return
        schema = GDW_AFNFN_SCHEMA.get(self._current_afn_fn, {})
        target = None
        for f in schema.get("fields", []):
            if f.get("name") == "报文内容":
                target = f
                break
        if target is None:
            for f in schema.get("fields", []):
                if f.get("type") == "bytes":
                    target = f
                    break
        if target is None:
            self._set_eb_msg("当前命令无「报文内容」字段可填入", True)
            return
        wi = self._field_widgets.get(target["name"], {})
        widget = wi.get("widget")
        if not isinstance(widget, QLineEdit):
            self._set_eb_msg(f"字段「{target['name']}」不可编辑", True)
            return
        widget.setText(self.eb_gen_frame)
        self._set_eb_msg(f"已填入字段「{target['name']}」（{len(self.eb_gen_frame)//2} 字节）", False)

    def _set_eb_msg(self, text: str, is_error: bool):
        self.eb_gen_msg.setText(text)
        color = "#D32F2F" if is_error else "#388E3C"
        self.eb_gen_msg.setStyleSheet(f"font-size: 11px; color: {color};")

    def reset_eb_generator(self):
        """重置 EB 生成器状态"""
        self.eb_gen_frame = ""
        self.eb_gen_result.clear()
        self._set_eb_msg("", False)
        if hasattr(self, "eb_format_combo"):
            self.eb_format_combo.setCurrentIndex(0)
        if hasattr(self, "eb_di_combo"):
            self.eb_di_combo.setCurrentIndex(0)
        self._eb_current_di = ""
        self._rebuild_eb_fields()

    # ------------------------------------------------------------------
    # DI 下拉框
    # ------------------------------------------------------------------
    def _populate_di_combo(self):
        self.di_combo.clear()
        self.di_combo.addItem("-- 请选择DI --", None)
        for di_key, schema in DI_FIELD_SCHEMA.items():
            direction = schema.get("direction", "both")
            # 组帧页面只显示下行命令（上行响应帧由解析功能处理）
            if direction != "down":
                continue
            name = schema.get("name", "未知")
            label = f"【下行】 {name}  ({di_key[0]:02X} {di_key[1]:02X} {di_key[2]:02X} {di_key[3]:02X})"
            self.di_combo.addItem(label, di_key)

    def _populate_afn_fn_combo(self):
        """填充国网AFN+Fn下拉框"""
        self.afn_fn_combo.clear()
        self.afn_fn_combo.addItem("-- 请选择AFN+Fn --", None)
        for afn, fn, name in self.gdw_generator.get_supported_afn_fn():
            label = f"【下行】 {name}  (AFN={afn:02X}H Fn=F{fn})"
            self.afn_fn_combo.addItem(label, (afn, fn))

    def _on_di_changed(self, index: int):
        di_key = self.di_combo.currentData()
        self._current_di_key = di_key
        self.cmd_help_btn.setEnabled(di_key is not None)
        self._rebuild_form(di_key)

    def _on_afn_fn_changed(self, index: int):
        afn_fn = self.afn_fn_combo.currentData()
        self._current_afn_fn = afn_fn
        self.cmd_help_btn.setEnabled(afn_fn is not None)
        self._rebuild_gdw_form(afn_fn)

    def _on_cmd_help_clicked(self):
        """显示命令说明弹窗"""
        if self.protocol_mode == "south":
            if not self._current_di_key:
                return
            schema = DI_FIELD_SCHEMA.get(self._current_di_key)
            if not schema:
                return
            doc = schema.get("doc", "暂无说明")
            name = schema.get("name", "未知命令")
        elif self.protocol_mode == "dlt698":
            if not self._current_dlt698_key:
                return
            schema = DLT69845_FIELD_SCHEMA.get(self._current_dlt698_key)
            if not schema:
                return
            doc = schema.get("doc", "暂无说明")
            name = schema.get("name", "未知命令")
        else:
            if not self._current_afn_fn:
                return
            schema = GDW_AFNFN_SCHEMA.get(self._current_afn_fn)
            if not schema:
                return
            doc = schema.get("doc", "暂无说明")
            name = schema.get("name", "未知命令")

        dialog = QDialog(self)
        dialog.setWindowTitle(f"命令说明 - {name}")
        dialog.setMinimumSize(520, 360)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(doc)
        text_edit.setFont(QFont("Microsoft YaHei", 10))
        setup_chinese_context_menu(text_edit)
        layout.addWidget(text_edit, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setMinimumWidth(80)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._help_dialog = dialog
        dialog.show()

    # ------------------------------------------------------------------
    # 动态表单
    # ------------------------------------------------------------------
    def _rebuild_form(self, di_key: Tuple[int, int, int, int]):
        # 清空旧表单
        self._clear_layout(self._form_layout)
        self._field_widgets.clear()

        if not di_key:
            self.mode_group.setVisible(True)
            return

        schema = DI_FIELD_SCHEMA.get(di_key)
        if not schema:
            self.mode_group.setVisible(True)
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            # 无数据单元：隐藏模式切换，显示提示
            self.mode_group.setVisible(False)
            self._custom_mode = False
            hint = QLabel("<b>该命令无数据单元，无需添加用户数据</b>")
            hint.setStyleSheet("color: #2196F3; font-size: 13px; padding: 20px;")
            hint.setAlignment(Qt.AlignCenter)
            self._form_layout.addWidget(hint)
            self._schedule_realtime_update()
            return

        # 有数据单元：显示模式切换
        self.mode_group.setVisible(True)

        # 如果没有预定义字段，自动切换到自定义模式
        has_predefined = bool(fields)
        if not has_predefined:
            self.mode_custom_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = True
        elif not self._custom_mode:
            self.mode_predefined_rb.setChecked(True)
            self.mode_custom_rb.setChecked(False)

        self._rebuild_field_form(di_key)

    def _rebuild_gdw_form(self, afn_fn: Tuple[int, int]):
        """重建国网模式表单"""
        self._clear_layout(self._form_layout)
        self._field_widgets.clear()

        if not afn_fn:
            self.mode_group.setVisible(True)
            return

        schema = GDW_AFNFN_SCHEMA.get(afn_fn)
        if not schema:
            self.mode_group.setVisible(True)
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            self.mode_group.setVisible(False)
            self._custom_mode = False
            hint = QLabel("<b>该命令无数据单元，无需添加用户数据</b>")
            hint.setStyleSheet("color: #2196F3; font-size: 13px; padding: 20px;")
            hint.setAlignment(Qt.AlignCenter)
            self._form_layout.addWidget(hint)
            self._schedule_realtime_update()
            return

        self.mode_group.setVisible(True)
        has_predefined = bool(fields)
        if not has_predefined:
            self.mode_custom_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = True
        elif not self._custom_mode:
            self.mode_predefined_rb.setChecked(True)
            self.mode_custom_rb.setChecked(False)

        self._rebuild_gdw_field_form(afn_fn)

    def _rebuild_gdw_field_form(self, afn_fn: Tuple[int, int]):
        """仅重建国网字段表单区"""
        self._clear_layout(self._form_layout)
        self._field_widgets.clear()

        if not afn_fn:
            return
        schema = GDW_AFNFN_SCHEMA.get(afn_fn)
        if not schema:
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            return

        if self._custom_mode:
            self._build_custom_template_ui()
            self._connect_template_signals()
        else:
            for field in schema.get("fields", []):
                widget = self._create_field_widget(field)
                if widget:
                    self._form_layout.addWidget(widget)
            self._connect_field_signals()
        self._schedule_realtime_update()
        apply_chinese_context_menus(self._form_container)

    def _on_gdw_comm_module_changed(self, index: int):
        """国网通信模块标识改变：决定是否显示地址域"""
        # 地址域始终显示，但通信模块标识影响组帧时是否包含地址
        pass

    def _on_gdw_relay_level_changed(self, index: int):
        """国网中继级别改变：动态显示中继地址输入框"""
        level = self.gdw_relay_level.currentData()
        # 清除旧的中继输入框
        while self.gdw_relay_layout.count() > 1:
            item = self.gdw_relay_layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        self.gdw_relay_inputs.clear()

        if level > 0:
            self.gdw_relay_container.setVisible(True)
            for i in range(level):
                lbl = QLabel(f"A2-{i+1}:")
                edit = QLineEdit("000000000000")
                edit.setMaxLength(12)
                edit.setFixedWidth(100)
                edit.textChanged.connect(self._schedule_realtime_update)
                self.gdw_relay_layout.addWidget(lbl)
                self.gdw_relay_layout.addWidget(edit)
                self.gdw_relay_inputs.append(edit)
            self.gdw_relay_layout.addStretch()
            apply_chinese_context_menus(self.gdw_relay_container)
        else:
            self.gdw_relay_container.setVisible(False)


    # ------------------------------------------------------------------
    # 698.45 地址编码
    # ------------------------------------------------------------------
    def _on_dlt698_addr_len_changed(self, index: int):
        """地址长度改变时更新SA输入框长度限制"""
        addr_len = self.dlt698_addr_len.currentData()
        if addr_len == 0:
            addr_len = 6
        self.dlt698_sa_raw.setMaxLength(addr_len * 2)
        # 截断超长内容
        text = self.dlt698_sa_raw.text()
        if len(text) > addr_len * 2:
            self.dlt698_sa_raw.setText(text[:addr_len * 2])

    def _get_dlt698_sa(self) -> bytes:
        """从 UI 控件组装服务器地址 SA（含地址特征字节 + 地址字节）

        地址特征字节: bit7-6=地址类型, bit5-4=逻辑地址, bit3-0=地址长度-1
        广播地址时返回 1 字节 0xAA
        """
        addr_type = self.dlt698_addr_type.currentData()
        logic_addr = self.dlt698_logic_addr.currentData()
        addr_len = self.dlt698_addr_len.currentData()

        # 广播地址: 固定 1 字节 0xAA
        if addr_type == 3:
            return bytes([0xAA])

        # 地址长度: D3-D0 编码为 (n-1)，0 = 自动
        if addr_len == 0:
            addr_len = 6  # 默认 6 字节

        # 地址特征字节
        feature = ((addr_type & 0x03) << 6) | ((logic_addr & 0x03) << 4) | ((addr_len - 1) & 0x0F)

        # 收集 SA 地址字节
        sa_text = self.dlt698_sa_raw.text().strip().replace(" ", "")
        try:
            sa_bytes = bytes.fromhex(sa_text) if sa_text else b""
        except ValueError:
            sa_bytes = b""

        # 补齐或截断到 addr_len
        if len(sa_bytes) < addr_len:
            sa_bytes = sa_bytes + b'\x00' * (addr_len - len(sa_bytes))
        elif len(sa_bytes) > addr_len:
            sa_bytes = sa_bytes[:addr_len]

        # GUI 大端正序输入，报文小端字节逆序
        return bytes([feature]) + sa_bytes[::-1]

    # ------------------------------------------------------------------
    # 698.45 APDU 下拉框与表单
    # ------------------------------------------------------------------
    def _populate_dlt698_combo(self):
        """填充698.45 APDU类型下拉框"""
        self.dlt698_combo.clear()
        self.dlt698_combo.addItem("-- 请选择APDU命令 --", None)
        for apdu_type, sub_type, name in self.dlt698_generator.get_supported_commands():
            label = f"【请求】 {name}  ({apdu_type}/{sub_type})"
            self.dlt698_combo.addItem(label, (apdu_type, sub_type))
        # 自定义 APDU
        self.dlt698_combo.addItem("【自定义】 自定义APDU命令  (输入服务码/子类型)", ("_custom_", "_custom_"))

    def _on_dlt698_changed(self, index: int):
        key = self.dlt698_combo.currentData()
        self._current_dlt698_key = key
        self.cmd_help_btn.setEnabled(key is not None)
        self._rebuild_dlt698_form(key)

    def _rebuild_dlt698_form(self, key: Tuple[str, str]):
        """重建698.45模式表单"""
        self._clear_layout(self._form_layout)
        self._field_widgets.clear()

        if not key:
            self.mode_group.setVisible(True)
            return

        # 自定义 APDU：自动切到 A-XDR 模式
        if key == ("_custom_", "_custom_"):
            self.mode_group.setVisible(True)
            self.mode_axdr_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self.mode_custom_rb.setChecked(False)
            self._custom_mode = False
            self._axdr_mode = True
            self._rebuild_dlt698_field_form(key)
            return

        schema = DLT69845_FIELD_SCHEMA.get(key)
        if not schema:
            self.mode_group.setVisible(True)
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            self.mode_group.setVisible(False)
            self._custom_mode = False
            hint = QLabel("<b>该命令无数据单元，无需添加用户数据</b>")
            hint.setStyleSheet("color: #2196F3; font-size: 13px; padding: 20px;")
            hint.setAlignment(Qt.AlignCenter)
            self._form_layout.addWidget(hint)
            self._schedule_realtime_update()
            return

        self.mode_group.setVisible(True)
        has_predefined = bool(fields)
        if not has_predefined:
            self.mode_axdr_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = False
            self._axdr_mode = True
        elif not self._axdr_mode:
            self.mode_predefined_rb.setChecked(True)
            self.mode_axdr_rb.setChecked(False)
            self._custom_mode = False

        self._rebuild_dlt698_field_form(key)

    # ------------------------------------------------------------------
    # DLT645-2007（协议6）命令下拉、DI 驱动字段与组帧
    # ------------------------------------------------------------------
    def _populate_dlt645_combo(self):
        """命令下拉：主站请求 / 从站应答 / 异常应答三组，itemData = (direction, func)"""
        self.dlt645_combo.clear()
        for key, group, text in list_commands():
            self.dlt645_combo.addItem(f"【{group}】{text}", tuple(key))

    def _populate_dlt645_di_combo(self):
        """1099 条 DI 全量入下拉；搜索靠 completer 的 MatchContains（可输 DI 或中文）"""
        self.dlt645_di_combo.clear()
        try:
            from dlt645_di_lookup import get_dlt645_di_lookup
            rows = get_dlt645_di_lookup().data
        except Exception:
            rows = []
        for row in rows:
            di_code = str(row[0]).upper()
            di_name = str(row[1] or "")
            self.dlt645_di_combo.addItem(f"{di_code}  {di_name}", di_code)
        self._dlt645_last_di = None

    def _reset_dlt645_selection(self):
        """选中首个命令并刷新面板（setCurrentIndex 同值不发信号，故显式调一次）"""
        if self.dlt645_combo.count():
            self.dlt645_combo.setCurrentIndex(0)
        self._on_dlt645_cmd_changed()

    def _dlt645_cmd_key(self):
        data = self.dlt645_combo.currentData()
        if not data:
            return None
        direction, func = data
        return (direction, int(func))

    def _dlt645_current_di(self) -> str:
        """从可编辑下拉取 DI：优先用输入文本（允许手填），否则用选中项的 data"""
        text = (self.dlt645_di_combo.currentText() or "").strip()
        code = text.split()[0].replace("-", "").upper() if text else ""
        if len(code) == 8 and all(c in "0123456789ABCDEF" for c in code):
            return code
        data = self.dlt645_di_combo.currentData()
        return str(data).upper() if data else ""

    def _on_dlt645_cmd_changed(self, *_args):
        key = self._dlt645_cmd_key()
        if not key:
            return
        try:
            spec = get_command(key)
        except ValueError:
            return
        self._current_dlt645_key = key
        ctrl = self._dlt645_gen.build_control(
            spec["func"], dir_bit=spec["dir"], err=bool(spec.get("err")))
        dlen = spec.get("data_len")
        len_txt = f"L={dlen:02X}H" if isinstance(dlen, int) else "L=按内容"
        tip = spec.get("hint") or ""
        self.dlt645_ctrl_label.setText(
            f"{describe_control(ctrl)}｜{len_txt}" + (f"｜{tip}" if tip else ""))
        self.dlt645_di_row.setVisible(bool(spec.get("has_di")))
        # 未手动改过地址时，地址随命令切到文档规定的默认值（校时 99×6 / 地址命令 AA×6）
        if not self._dlt645_addr_touched and not self.dlt645_broadcast.isChecked():
            self._set_dlt645_addr(spec.get("addr_default") or "000000000000")
        self._rebuild_dlt645_fields()
        # 切命令后立即调度一次预览刷新（不必等用户改字段）
        self._schedule_realtime_update()

    def _on_dlt645_di_changed(self, *_args):
        """DI 变化时重建字段表单；按解析后的 8 位码去重，避免逐字输入反复重建"""
        di = self._dlt645_current_di()
        if di == getattr(self, "_dlt645_last_di", None):
            return
        self._dlt645_last_di = di
        if self._current_dlt645_key:
            self._rebuild_dlt645_fields()

    def _on_dlt645_addr_edited(self, *_args):
        if getattr(self, "_dlt645_addr_programmatic", False):
            return
        self._dlt645_addr_touched = True
        self._update_dlt645_addr_type_label()

    def _on_dlt645_addr_selected(self, *_args):
        """从下拉选择地址类型/历史地址：视为用户意图"""
        self._dlt645_addr_touched = True
        self._update_dlt645_addr_type_label()

    def _dlt645_addr_value(self) -> str:
        return (self.dlt645_addr.currentText() or "").strip()

    def _set_dlt645_addr(self, value: str):
        """程序性设置地址（不标记 touched），并刷新类型标签与预览"""
        self._dlt645_addr_programmatic = True
        self.dlt645_addr.setCurrentText(value)
        self._dlt645_addr_programmatic = False
        self._update_dlt645_addr_type_label()
        self._schedule_realtime_update()

    def _update_dlt645_addr_type_label(self):
        v = self._dlt645_addr_value().upper()
        if v == "999999999999":
            t = "广播地址"
        elif v == "AAAAAAAAAAAA":
            t = "通配地址(读/写通信地址用)"
        elif v == "000000000000":
            t = "全零地址"
        elif v in [h.upper() for h in self._dlt645_addr_history]:
            t = "历史地址"
        elif not v:
            t = ""
        else:
            t = "单地址(手动)"
        self.dlt645_addr_type_label.setText(f"类型: {t}" if t else "")

    @staticmethod
    def _load_dlt645_addr_history() -> List[str]:
        """读取历史地址（dlt645_addr_history.json，缺失/损坏时返回空）"""
        try:
            import json
            import os
            from app_paths import data_path
            p = str(data_path("dlt645_addr_history.json"))
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                hist = data.get("history", []) if isinstance(data, dict) else []
                return [str(x) for x in hist if isinstance(x, str)][:20]
        except Exception:
            pass
        return []

    def _push_dlt645_addr_history(self, addr: str):
        """生成成功后记录地址（去重、最多20条、持久化）"""
        addr = (addr or "").strip().upper()
        if len(addr) != 12:
            return
        hist = [addr] + [h for h in self._dlt645_addr_history
                         if h.upper() != addr]
        self._dlt645_addr_history = hist[:20]
        self._refresh_dlt645_addr_items()
        self._update_dlt645_addr_type_label()
        try:
            import json
            from app_paths import data_path
            with open(str(data_path("dlt645_addr_history.json")), "w",
                      encoding="utf-8") as fh:
                json.dump({"history": self._dlt645_addr_history}, fh,
                          ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _refresh_dlt645_addr_items(self):
        """重建地址下拉项：内置类型 + 历史（保留当前输入）"""
        cur = self.dlt645_addr.currentText()
        items = list(self._dlt645_addr_defaults)
        for h in self._dlt645_addr_history:
            if h not in items:
                items.append(h)
        self.dlt645_addr.blockSignals(True)
        self.dlt645_addr.clear()
        self.dlt645_addr.addItems(items)
        self.dlt645_addr.setCurrentText(cur)
        self.dlt645_addr.blockSignals(False)

    def _on_dlt645_broadcast(self, checked: bool):
        if checked:
            self._dlt645_addr_backup = self._dlt645_addr_value()
            addr = "999999999999"
            key = self._current_dlt645_key
            if key:
                try:
                    spec = get_command(key)
                except ValueError:
                    spec = None
                # 读/写通信地址用 AA×6（文档 §7.4/§7.5），其余广播用 99×6
                if spec and spec["func"] in (0x13, 0x15):
                    addr = "AAAAAAAAAAAA"
            self._set_dlt645_addr(addr)
        else:
            self._set_dlt645_addr(
                getattr(self, "_dlt645_addr_backup", "") or "000000000000")
        self._dlt645_addr_touched = True

    def _update_dlt645_di_info(self, di: str):
        from dlt645_frame_schema import get_di_info
        if not di:
            self.dlt645_di_info.setText("未选择数据标识（可输 8 位 DI 或中文关键词搜索）")
            return
        info = get_di_info(di)
        if info["name"]:
            unit = f"｜单位 {info['unit']}" if info["unit"] else ""
            self.dlt645_di_info.setText(
                f"{di}｜{info['name']}｜格式 {info['data_type'] or '未声明'}"
                f"｜长度 {info['length']} 字节{unit}")
        else:
            self.dlt645_di_info.setText(f"{di}｜不在 dlt645_di.json 映射表，按裸字节填写")

    def _rebuild_dlt645_fields(self):
        """按当前命令 + 所选 DI 的 data_type 掩码重建字段表单"""
        self._clear_layout(self.dlt645_field_layout)
        self._dlt645_field_widgets = {}
        key = self._current_dlt645_key
        if not key:
            return
        try:
            spec = get_command(key)
        except ValueError:
            return
        fields = [f for f in (spec.get("fields") or []) if f.get("type") != "di"]
        if spec.get("has_di"):
            di = self._dlt645_current_di()
            self._update_dlt645_di_info(di)
            # 读请求（11H/12H）数据域仅 DI：丢弃通用值字段（避免展示被忽略的输入框），
            # 但保留 LME 查询请求的结构化条目字段（lme_entries）；
            # 写数据 14H / 读应答 91H·92H 的数据域才含值，按掩码推导字段
            derived = build_di_fields(di) if di else []
            if key[0] == "req" and key[1] in (0x11, 0x12):
                derived = [f for f in derived
                           if f.get("type") == "lme_entries"]
            # schema 里的通用值字段被掩码推导出的专用字段取代（裸 hex 兜底保留）
            fields = derived + [f for f in fields if f.get("type") not in
                                ("di_value", "demand", "demand_time")]
        else:
            self.dlt645_di_info.setText("")
        for f in fields:
            row = QHBoxLayout()
            row.setSpacing(6)
            lab = QLabel(f"{f['name']}:")
            lab.setMinimumWidth(130)
            row.addWidget(lab)
            edit = QLineEdit(str(f.get("default", "")))
            hint = f.get("hint") or ""
            if hint:
                edit.setToolTip(hint)
                edit.setPlaceholderText(hint[:60])
            row.addWidget(edit, 1)
            # 动态字段也要接实时预览调度（与其他协议的固定控件同模式）
            edit.textChanged.connect(self._schedule_realtime_update)
            self.dlt645_field_layout.addLayout(row)
            self._dlt645_field_widgets[f["name"]] = edit
        self._refresh_dlt645_warning()

    def _collect_dlt645_values(self) -> Dict[str, Any]:
        fv: Dict[str, Any] = {}
        key = self._current_dlt645_key
        if key:
            try:
                spec = get_command(key)
            except ValueError:
                spec = {}
            if spec.get("has_di"):
                di = self._dlt645_current_di()
                if di:
                    fv["数据标识 DI"] = di
        for name, w in self._dlt645_field_widgets.items():
            fv[name] = w.text().strip()
        return fv

    def _refresh_dlt645_warning(self, fv=None):
        """数据长度与 DI 声明不符时给警告，**不阻断**组帧（不校验 DI 可写性）"""
        key = self._current_dlt645_key
        if not key:
            self.dlt645_warn_label.setText("")
            return
        try:
            self.dlt645_warn_label.setText(length_warning(
                key, fv if fv is not None else self._collect_dlt645_values()))
        except Exception:
            self.dlt645_warn_label.setText("")

    def _verify_dlt645_frame(self, frame: bytes):
        """组帧后立刻用本工具的解析器回读，让「组帧→解析」闭环在 UI 上可见"""
        try:
            r = DLT645Parser.parse(frame)
            ok = bool(r.get("valid"))
            di = r.get("di_code") or ""
            desc = r.get("di_desc") or ""
            extra = f"｜DI={di} {desc}".rstrip() if di else ""
            self.dlt645_verify_label.setText(
                f"解析回读：{'通过' if ok else '失败'}{extra}"
                + ("" if ok else f"｜{r.get('error') or ''}"))
            self.dlt645_verify_label.setStyleSheet(
                "color: #2E7D32;" if ok else "color: #C62828;")
        except Exception as e:
            self.dlt645_verify_label.setText(f"解析回读异常：{e}")
            self.dlt645_verify_label.setStyleSheet("color: #C62828;")

    def _generate_dlt645_frame(self):
        """生成 DLT645-2007 帧（协议6）"""
        key = self._current_dlt645_key
        if not key:
            QMessageBox.warning(self, "警告", "请先选择命令")
            return
        fv = self._collect_dlt645_values()
        addr = self._dlt645_addr_value() or None
        try:
            frame = self._dlt645_gen.generate_frame(key, fv, addr=addr)
        except ValueError as e:
            self.dlt645_verify_label.setText("")
            self.dlt645_warn_label.setText(str(e))
            QMessageBox.warning(self, "组帧失败", str(e))
            return
        hex_str = frame.hex().upper()
        self.result_hex.setText(
            " ".join(hex_str[i:i + 2] for i in range(0, len(hex_str), 2)))
        self._refresh_dlt645_warning(fv)
        self._verify_dlt645_frame(frame)
        # 生成成功后记入历史地址（下拉可选，持久化）
        self._push_dlt645_addr_history(addr or "")
        # 点「生成帧」也同步刷新右侧实时预览（不依赖防抖定时器是否已被触发）
        self._schedule_realtime_update()

    def _clear_layout(self, layout):
        """递归清空 layout 中所有 widget 和子 layout"""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _rebuild_dlt698_field_form(self, key: Tuple[str, str]):
        """仅重建698.45字段表单区"""
        self._clear_layout(self._form_layout)
        self._field_widgets.clear()

        if not key:
            return

        # A-XDR 模式：固定字段 PIID(优先级+序号) + OI + 属性ID+索引/方法ID+模式 + A-XDR编辑器
        if self._axdr_mode:
            apdu_type = key[0] if key else ""

            # PIID = 服务优先级(D7) + 服务序号(D6-D0)
            piid_container = QWidget()
            piid_layout = QHBoxLayout(piid_container)
            piid_layout.setContentsMargins(4, 2, 4, 2)
            piid_layout.addWidget(QLabel("PIID"))
            piid_layout.addWidget(QLabel("服务优先级:"))
            priority_combo = QComboBox()
            priority_combo.addItem("0-普通", 0)
            priority_combo.addItem("1-高优先级", 1)
            priority_combo.currentIndexChanged.connect(self._schedule_realtime_update)
            piid_layout.addWidget(priority_combo)
            piid_layout.addWidget(QLabel("服务序号:"))
            seq_edit = QLineEdit("1")
            seq_edit.setFixedWidth(50)
            seq_edit.textChanged.connect(self._schedule_realtime_update)
            piid_layout.addWidget(seq_edit)
            self._field_widgets["PIID_优先级"] = {"widget": priority_combo}
            self._field_widgets["PIID_序号"] = {"widget": seq_edit}
            piid_layout.addStretch()
            self._form_layout.addWidget(piid_container)

            # OI（预设下拉 + 手动输入，二选一）
            oi_container = QWidget()
            oi_layout = QHBoxLayout(oi_container)
            oi_layout.setContentsMargins(4, 2, 4, 2)
            oi_layout.addWidget(QLabel("OI  [对象标识 (2字节小端序)]"))
            oi_preset_combo = QComboBox()
            oi_preset_combo.addItem("-- 预设OI --", None)
            for oi_val, oi_name in OI_PRESET_LIST:
                oi_preset_combo.addItem(f"{oi_name} (0x{oi_val:04X})", oi_val)
            oi_edit = QLineEdit()
            oi_edit.setPlaceholderText("或手动输入hex 如 0400")
            oi_edit.setMinimumWidth(140)
            oi_edit.textChanged.connect(self._schedule_realtime_update)
            def _on_axdr_oi_preset(idx, _c=oi_preset_combo, _e=oi_edit):
                v = _c.itemData(idx)
                if v is not None:
                    _e.setText(f"{v:04X}")
            oi_preset_combo.currentIndexChanged.connect(_on_axdr_oi_preset)
            oi_layout.addWidget(oi_preset_combo)
            oi_layout.addWidget(oi_edit)
            self._field_widgets["OI"] = {"widget": oi_edit}
            oi_layout.addStretch()
            self._form_layout.addWidget(oi_container)

            # 描述符类型：属性(OAD) / 方法(OMD) 可自由选择（默认按命令类型）
            desc_container = QWidget()
            desc_layout = QHBoxLayout(desc_container)
            desc_layout.setContentsMargins(4, 2, 4, 2)
            desc_layout.addWidget(QLabel("描述符类型"))
            desc_combo = QComboBox()
            desc_combo.addItem("属性 (OAD)", "OAD")
            desc_combo.addItem("方法 (OMD)", "OMD")
            if apdu_type == "ACTION-Request":
                desc_combo.setCurrentIndex(1)
            desc_layout.addWidget(desc_combo)
            desc_layout.addStretch()
            self._form_layout.addWidget(desc_container)
            self._field_widgets["描述符类型"] = {"widget": desc_combo}

            # 属性(OAD)：属性标识 + 索引
            attr_container = QWidget()
            attr_layout = QHBoxLayout(attr_container)
            attr_layout.setContentsMargins(4, 2, 4, 2)
            attr_layout.addWidget(QLabel("属性标识"))
            attr_edit = QLineEdit("2")
            attr_edit.setFixedWidth(40)
            attr_layout.addWidget(attr_edit)
            attr_layout.addWidget(QLabel("索引"))
            idx_edit = QLineEdit("0")
            idx_edit.setFixedWidth(40)
            attr_layout.addWidget(idx_edit)
            attr_layout.addStretch()
            self._form_layout.addWidget(attr_container)
            self._field_widgets["属性标识"] = {"widget": attr_edit}
            self._field_widgets["索引"] = {"widget": idx_edit}

            # 方法(OMD)：方法标识 + 操作模式
            omd_container = QWidget()
            omd_layout = QHBoxLayout(omd_container)
            omd_layout.setContentsMargins(4, 2, 4, 2)
            omd_layout.addWidget(QLabel("方法标识"))
            method_edit = QLineEdit("1")
            method_edit.setFixedWidth(40)
            omd_layout.addWidget(method_edit)
            omd_layout.addWidget(QLabel("操作模式"))
            mode_edit = QLineEdit("0")
            mode_edit.setFixedWidth(40)
            omd_layout.addWidget(mode_edit)
            omd_layout.addStretch()
            self._form_layout.addWidget(omd_container)
            self._field_widgets["方法标识"] = {"widget": method_edit}
            self._field_widgets["操作模式"] = {"widget": mode_edit}

            def _on_desc_type_changed(idx, _c=desc_combo,
                                      _a=attr_container, _m=omd_container):
                is_oad = _c.itemData(idx) == "OAD"
                _a.setVisible(is_oad)
                _m.setVisible(not is_oad)
                self._schedule_realtime_update()
            desc_combo.currentIndexChanged.connect(_on_desc_type_changed)
            _on_desc_type_changed(desc_combo.currentIndex())

            self._connect_field_signals()
            self._build_axdr_editor(key)
            return

        schema = DLT69845_FIELD_SCHEMA.get(key)
        if not schema:
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            return

        if self._custom_mode and self.protocol_mode != "dlt698":
            self._build_custom_template_ui()
            self._connect_template_signals()
        else:
            for field in schema.get("fields", []):
                ftype = field.get("type", "bytes")
                if ftype == "oi":
                    # OI 特殊处理：预设下拉框 + 手动输入（二选一，手动输入优先）
                    container = QWidget()
                    layout = QHBoxLayout(container)
                    layout.setContentsMargins(4, 2, 4, 2)
                    label_text = field.get("name", "OI")
                    desc = field.get("desc", "")
                    if desc:
                        label_text += f"  [{desc}]"
                    label = QLabel(label_text)
                    label.setMinimumWidth(180)
                    label.setToolTip(desc)
                    layout.addWidget(label)
                    oi_combo = QComboBox()
                    oi_combo.addItem("-- 预设OI --", None)
                    for oi_val, oi_name in OI_PRESET_LIST:
                        oi_combo.addItem(f"{oi_name} (0x{oi_val:04X})", oi_val)
                    oi_edit = QLineEdit()
                    oi_edit.setPlaceholderText("或手动输入hex 如 0400")
                    oi_edit.setFixedWidth(110)
                    def _on_oi_preset(idx, _c=oi_combo, _e=oi_edit):
                        v = _c.itemData(idx)
                        if v is not None:
                            _e.setText(f"{v:04X}")
                    oi_combo.currentIndexChanged.connect(_on_oi_preset)
                    layout.addWidget(oi_combo)
                    layout.addWidget(oi_edit)
                    self._field_widgets[field["name"]] = {"widget": oi_edit}
                    layout.addStretch()
                    self._form_layout.addWidget(container)
                elif ftype == "piid":
                    # PIID = 服务优先级(D7) + 服务序号(D6-D0)，拆成两个子输入
                    container = QWidget()
                    layout = QHBoxLayout(container)
                    layout.setContentsMargins(4, 2, 4, 2)
                    label = QLabel(field.get("name", "PIID") + "  [服务优先级D7 + 服务序号D6-D0]")
                    label.setMinimumWidth(180)
                    label.setToolTip(field.get("desc", ""))
                    layout.addWidget(label)
                    layout.addWidget(QLabel("优先级:"))
                    priority_combo = QComboBox()
                    priority_combo.addItem("0-普通", 0)
                    priority_combo.addItem("1-高优先级", 1)
                    priority_combo.currentIndexChanged.connect(self._schedule_realtime_update)
                    layout.addWidget(priority_combo)
                    layout.addWidget(QLabel("序号:"))
                    seq_edit = QLineEdit(str(field.get("default", 1)))
                    seq_edit.setFixedWidth(50)
                    seq_edit.textChanged.connect(self._schedule_realtime_update)
                    layout.addWidget(seq_edit)
                    self._field_widgets[f"{field['name']}_优先级"] = {"widget": priority_combo}
                    self._field_widgets[f"{field['name']}_序号"] = {"widget": seq_edit}
                    layout.addStretch()
                    self._form_layout.addWidget(container)
                elif ftype == "oad_list":
                    # OAD列表：一个大文本框
                    container = QWidget()
                    layout = QHBoxLayout(container)
                    layout.setContentsMargins(4, 2, 4, 2)
                    desc = field.get("desc", "格式：OI(4B)+属性标识(2B) 空格分隔")
                    label = QLabel(f"{field['name']}  [{desc}]")
                    label.setMinimumWidth(180)
                    layout.addWidget(label)
                    edit = QLineEdit(field.get("default", "00000000"))
                    edit.setPlaceholderText("如：02400102 00400202")
                    edit.textChanged.connect(self._schedule_realtime_update)

                    def _update_oad_count(text):
                        raw = text.replace(" ", "").strip()
                        if len(raw) >= 8 and len(raw) % 8 == 0:
                            count = len(raw) // 8
                        else:
                            count = 0
                        count_info = self._field_widgets.get("OAD项数", {}).get("widget")
                        if count_info:
                            count_info.setText(str(count))

                    edit.textChanged.connect(_update_oad_count)
                    layout.addWidget(edit)
                    self._field_widgets[field["name"]] = {"widget": edit}
                    layout.addStretch()
                    self._form_layout.addWidget(container)
                    # 初始触发一次项数计算
                    _update_oad_count(edit.text())
                else:
                    widget = self._create_field_widget(field)
                    if widget:
                        self._form_layout.addWidget(widget)
            self._connect_field_signals()
        self._schedule_realtime_update()
        apply_chinese_context_menus(self._form_container)

    def _rebuild_field_form(self, di_key: Tuple[int, int, int, int]):
        """仅重建字段表单区（模式切换时调用，不清空模式控件）"""
        # 清空旧表单（保留模式切换控件，因为它们不在 _form_layout 中）
        self._clear_layout(self._form_layout)
        self._field_widgets.clear()

        if not di_key:
            return

        schema = DI_FIELD_SCHEMA.get(di_key)
        if not schema:
            return

        fields = schema.get("fields")
        if fields is not None and len(fields) == 0:
            return

        if self._custom_mode:
            self._build_custom_template_ui()
            self._connect_template_signals()
        else:
            for field in schema.get("fields", []):
                widget = self._create_field_widget(field)
                if widget:
                    self._form_layout.addWidget(widget)
            self._connect_field_signals()
        self._schedule_realtime_update()
        apply_chinese_context_menus(self._form_container)

    # ------------------------------------------------------------------
    # A-XDR 数据类型树形编辑器
    # ------------------------------------------------------------------
    A_XDR_TYPE_LIST = [
        ("null", 0x00, "空"),
        ("array", 0x01, "数组"),
        ("structure", 0x02, "结构体"),
        ("bool", 0x03, "布尔值"),
        ("bit-string", 0x04, "位串"),
        ("double-long", 0x05, "32位整数"),
        ("double-long-unsigned", 0x06, "32位正整数"),
        ("octet-string", 0x09, "字节串"),
        ("visible-string", 0x0A, "ASCII字符串"),
        ("UTF8-string", 0x0C, "UTF8字符串"),
        ("integer", 0x0F, "8位整数"),
        ("long", 0x10, "16位整数"),
        ("unsigned", 0x11, "8位正整数"),
        ("long-unsigned", 0x12, "16位正整数"),
        ("long64", 0x14, "64位整数"),
        ("long64-unsigned", 0x15, "64位正整数"),
        ("enum", 0x16, "枚举"),
        ("float32", 0x17, "32位浮点数"),
        ("float64", 0x18, "64位浮点数"),
        ("date_time", 0x19, "日期时间SIZE(10)"),
        ("date", 0x1A, "日期SIZE(5)"),
        ("time", 0x1B, "时间SIZE(3)"),
        ("date_time_s", 0x1C, "日期时间SIZE(7)"),
        ("OI", 0x50, "对象标识"),
        ("OAD", 0x51, "对象属性描述符"),
        ("OMD", 0x53, "对象方法描述符"),
        ("TI", 0x54, "时间间隔"),
        ("TSA", 0x55, "时间戳"),
        ("MAC", 0x56, "消息认证码"),
        ("RN", 0x57, "随机数"),
    ]

    VAR_LEN_TYPES = {"array", "structure", "octet-string", "visible-string", "UTF8-string", "bit-string"}

    COMPOUND_TYPES = {"array", "structure"}

    def _build_axdr_editor(self, key):
        """构建 A-XDR 树形编辑器"""
        from dl_t698_45_axdr import AXDRCoder
        self._axdr_coder = AXDRCoder()
        self._axdr_root = {"type": "structure", "tag": 0x02, "value": "root", "children": self._axdr_items or []}

        # 工具栏
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton("+ 添加数据项")
        add_btn.clicked.connect(self._add_axdr_root_item)
        toolbar.addWidget(add_btn)
        toolbar.addStretch()
        self._form_layout.addWidget(toolbar_widget)

        # 树形容器
        self._axdr_tree = QWidget()
        self._axdr_tree_layout = QVBoxLayout(self._axdr_tree)
        self._axdr_tree_layout.setAlignment(Qt.AlignTop)
        self._axdr_tree_layout.setSpacing(2)
        self._form_layout.addWidget(self._axdr_tree)

        # 渲染现有项
        self._render_all_axdr_items()

    def _render_all_axdr_items(self):
        """渲染所有 A-XDR 根级项"""
        if not hasattr(self, '_axdr_tree_layout'):
            return
        while self._axdr_tree_layout.count():
            item = self._axdr_tree_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for i, child in enumerate(self._axdr_items):
            self._render_axdr_item(child, self._axdr_tree_layout, 0, i)

    def _render_axdr_item(self, item: dict, parent_layout, level: int, index: int):
        """渲染单个 A-XDR 数据项"""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4 + level * 20, 1, 4, 1)
        row_layout.setSpacing(4)

        # 类型下拉
        combo = QComboBox()
        combo.setFixedWidth(160)
        combo.setStyleSheet(
            "QComboBox { background-color: #ffffff; color: #000000; }"
            "QComboBox QAbstractItemView { background-color: #ffffff; color: #000000; selection-background-color: #e3f2fd; }"
        )
        for t_name, t_tag, t_desc in self.A_XDR_TYPE_LIST:
            combo.addItem(f"{t_desc} (0x{t_tag:02X})", t_tag)
        # 设置当前类型
        tag = item.get("tag", 0x11)
        combo.blockSignals(True)
        idx = combo.findData(tag)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        combo.currentIndexChanged.connect(
            lambda idx, it=item: self._on_axdr_type_changed(it)
        )
        row_layout.addWidget(combo)

        # 长度/个数输入 (可变长类型与复合类型)
        t = item.get("type", "unsigned")
        len_edit = QLineEdit()
        len_edit.setFixedWidth(50)
        len_edit.setPlaceholderText("个数" if t in self.COMPOUND_TYPES else "长度")

        if t in self.COMPOUND_TYPES:
            count = len(item.get("children", []))
            len_edit.setText(str(count))
        elif t in self.VAR_LEN_TYPES:
            val = item.get("value", "")
            if t in ("octet-string", "bit-string"):
                try:
                    count = len(bytes.fromhex(str(val).replace(" ", "")))
                except ValueError:
                    count = 0
            elif t in ("visible-string", "UTF8-string"):
                count = len(str(val))
            else:
                count = item.get("length", 0)
            len_edit.setText(str(count))
            item["length"] = count
        else:
            len_edit.setEnabled(False)
            fixed_lengths = {
                "null": 0, "bool": 1, "integer": 1, "unsigned": 1, "enum": 1,
                "long": 2, "long-unsigned": 2, "OI": 2,
                "double-long": 4, "double-long-unsigned": 4, "float32": 4,
                "OAD": 4, "OMD": 4,
                "long64": 8, "long64-unsigned": 8, "float64": 8,
                "date_time": 10, "date": 5, "time": 4, "date_time_s": 7,
                "TI": 3, "TSA": 7, "MAC": 4, "RN": 4,
            }
            len_edit.setText(str(fixed_lengths.get(t, "")))

        len_edit.editingFinished.connect(lambda it=item: self._on_axdr_length_changed(it))
        len_edit.textChanged.connect(self._schedule_realtime_update)
        row_layout.addWidget(len_edit)
        item["_len_edit"] = len_edit

        # 值输入区域
        value_widget = self._create_axdr_value_widget(item)
        row_layout.addWidget(value_widget)

        # 操作按钮
        if t in self.COMPOUND_TYPES:
            add_btn = QPushButton("+")
            set_btn(add_btn, "secondary", "sm")
            add_btn.setFixedWidth(28)
            add_btn.clicked.connect(lambda checked=False, it=item: self._on_add_axdr_child(it))
            row_layout.addWidget(add_btn)

        del_btn = QPushButton("删")
        del_btn.setFixedWidth(28)
        del_btn.setToolTip("删除此项")
        set_btn(del_btn, "danger", "sm")
        del_btn.clicked.connect(lambda checked=False, it=item: self._on_del_axdr_item(it))
        row_layout.addWidget(del_btn)

        row_layout.addStretch()
        parent_layout.addWidget(row)

        # 存储引用
        item["_combo"] = combo
        item["_row"] = row
        item["_value_widget"] = value_widget

        # 渲染子项（仅 compound 类型）
        if item["type"] in self.COMPOUND_TYPES:
            children = item.setdefault("children", [])
            for ci, child in enumerate(children):
                self._render_axdr_item(child, parent_layout, level + 1, ci)

    def _create_axdr_value_widget(self, item: dict):
        """为 A-XDR 数据项创建值输入控件"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        t = item["type"]

        if t in self.COMPOUND_TYPES:
            label = QLabel("...")
            label.setStyleSheet("color: #999; font-size: 11px;")
            layout.addWidget(label)
            return container

        if t == "bool":
            cb = QCheckBox()
            cb.setChecked(bool(item.get("value", False)))
            cb.stateChanged.connect(self._schedule_realtime_update)
            layout.addWidget(cb)
            return container

        if t in ("octet-string", "bit-string", "date_time", "date", "time", "date_time_s",
                  "TI", "TSA", "MAC", "RN"):
            edit = QLineEdit(item.get("value", ""))
            edit.setPlaceholderText("hex...")
            edit.setMinimumWidth(100)
            edit.textChanged.connect(self._schedule_realtime_update)
            layout.addWidget(edit)
            return container

        if t in ("visible-string", "UTF8-string"):
            edit = QLineEdit(str(item.get("value", "")))
            edit.setMinimumWidth(120)
            edit.textChanged.connect(self._schedule_realtime_update)
            layout.addWidget(edit)
            return container

        if t == "OI":
            combo = QComboBox()
            combo.addItem("-- OI --", 0)
            from dl_t698_45_frame_schema import OI_PRESET_LIST
            for oi_val, oi_name in OI_PRESET_LIST:
                combo.addItem(f"{oi_name} (0x{oi_val:04X})", oi_val)
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.lineEdit().setPlaceholderText("预设或手动输入hex 如 0400")
            cur = item.get("value", 0)
            idx = combo.findData(cur)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif cur:
                combo.setCurrentText(f"{int(cur):04X}")
            combo.currentIndexChanged.connect(self._schedule_realtime_update)
            combo.lineEdit().textChanged.connect(lambda *_: self._schedule_realtime_update())
            layout.addWidget(combo)
            return container

        if t == "OAD":
            oi_val = item.get("oi", 0)
            oi_combo = QComboBox()
            oi_combo.addItem("OI...", 0)
            from dl_t698_45_frame_schema import OI_PRESET_LIST
            for oi_v, oi_name in OI_PRESET_LIST:
                oi_combo.addItem(f"{oi_name} (0x{oi_v:04X})", oi_v)
            oi_combo.setEditable(True)
            oi_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            oi_combo.lineEdit().setPlaceholderText("预设或手动输入hex")
            idx = oi_combo.findData(oi_val)
            if idx >= 0:
                oi_combo.setCurrentIndex(idx)
            elif oi_val:
                oi_combo.setCurrentText(f"{int(oi_val):04X}")
            oi_combo.currentIndexChanged.connect(self._schedule_realtime_update)
            oi_combo.lineEdit().textChanged.connect(lambda *_: self._schedule_realtime_update())
            layout.addWidget(QLabel("OI:"))
            layout.addWidget(oi_combo)

            attr_edit = QLineEdit(str(item.get("attr", 2)))
            attr_edit.setFixedWidth(30)
            attr_edit.textChanged.connect(self._schedule_realtime_update)
            layout.addWidget(QLabel("属性:"))
            layout.addWidget(attr_edit)

            idx_edit = QLineEdit(str(item.get("index", 0)))
            idx_edit.setFixedWidth(25)
            idx_edit.textChanged.connect(self._schedule_realtime_update)
            layout.addWidget(QLabel("索引:"))
            layout.addWidget(idx_edit)
            return container

        if t == "OMD":
            oi_val = item.get("oi", 0)
            oi_combo = QComboBox()
            oi_combo.addItem("OI...", 0)
            from dl_t698_45_frame_schema import OI_PRESET_LIST
            for oi_v, oi_name in OI_PRESET_LIST:
                oi_combo.addItem(f"{oi_name} (0x{oi_v:04X})", oi_v)
            oi_combo.setEditable(True)
            oi_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            oi_combo.lineEdit().setPlaceholderText("预设或手动输入hex")
            idx = oi_combo.findData(oi_val)
            if idx >= 0:
                oi_combo.setCurrentIndex(idx)
            elif oi_val:
                oi_combo.setCurrentText(f"{int(oi_val):04X}")
            oi_combo.currentIndexChanged.connect(self._schedule_realtime_update)
            oi_combo.lineEdit().textChanged.connect(lambda *_: self._schedule_realtime_update())
            layout.addWidget(QLabel("OI:"))
            layout.addWidget(oi_combo)

            method_edit = QLineEdit(str(item.get("method", 1)))
            method_edit.setFixedWidth(30)
            method_edit.textChanged.connect(self._schedule_realtime_update)
            layout.addWidget(QLabel("方法:"))
            layout.addWidget(method_edit)

            mode_edit = QLineEdit(str(item.get("mode", 0)))
            mode_edit.setFixedWidth(25)
            mode_edit.textChanged.connect(self._schedule_realtime_update)
            layout.addWidget(QLabel("模式:"))
            layout.addWidget(mode_edit)
            return container

        # 默认：数值/十六进制输入
        default_val = item.get("value", 0)
        edit = QLineEdit(str(default_val))
        edit.setPlaceholderText("数值")
        edit.setMinimumWidth(60)
        edit.textChanged.connect(self._schedule_realtime_update)
        layout.addWidget(edit)
        return container

    def _on_axdr_type_changed(self, item: dict):
        """A-XDR 类型改变时更新 item 并重建渲染"""
        combo = item.get("_combo")
        if combo is None:
            return
        new_tag = combo.currentData()
        if new_tag is None:
            return
        old_tag = item.get("tag")
        if new_tag == old_tag:
            return
        from dl_t698_45_axdr import get_tag_name
        new_type = get_tag_name(new_tag)
        item["tag"] = new_tag
        item["type"] = new_type
        if new_type not in self.COMPOUND_TYPES and "children" in item:
            del item["children"]
        if new_type in self.COMPOUND_TYPES:
            item.setdefault("children", [])
        self._render_all_axdr_items()
        self._schedule_realtime_update()

    def _on_axdr_length_changed(self, item: dict):
        """A-XDR 长度/个数改变时更新 item"""
        len_edit = item.get("_len_edit")
        if len_edit is None:
            return
        try:
            new_len = int(len_edit.text().strip())
        except ValueError:
            return
        t = item.get("type", "")
        if t in self.COMPOUND_TYPES:
            children = item.setdefault("children", [])
            while len(children) < new_len:
                children.append({"type": "unsigned", "tag": 0x11, "value": 0})
            while len(children) > new_len:
                children.pop()
            self._render_all_axdr_items()
            self._schedule_realtime_update()
        elif t in self.VAR_LEN_TYPES:
            item["length"] = new_len
            self._schedule_realtime_update()

    def _add_axdr_root_item(self):
        """添加根级数据项"""
        new_item = {"type": "unsigned", "tag": 0x11, "value": 0}
        self._axdr_items.append(new_item)
        self._render_all_axdr_items()
        self._schedule_realtime_update()

    def _on_add_axdr_child(self, parent_item: dict):
        """为复合类型添加子项"""
        children = parent_item.setdefault("children", [])
        new_child = {"type": "unsigned", "tag": 0x11, "value": 0}
        children.append(new_child)
        self._render_all_axdr_items()
        self._schedule_realtime_update()

    def _on_del_axdr_item(self, item: dict):
        """删除一个 A-XDR 数据项"""
        for i, ri in enumerate(self._axdr_items):
            if ri is item:
                del self._axdr_items[i]
                self._render_all_axdr_items()
                self._schedule_realtime_update()
                return
        for ri in self._axdr_items:
            if self._remove_from_children(ri, item):
                self._render_all_axdr_items()
                self._schedule_realtime_update()
                return

    def _remove_from_children(self, parent: dict, target: dict) -> bool:
        """递归查找并移除子项"""
        children = parent.get("children", [])
        for i, child in enumerate(children):
            if child is target:
                del children[i]
                return True
            if self._remove_from_children(child, target):
                return True
        return False

    def _collect_axdr_values(self, item: dict) -> dict:
        """从 UI 控件收集 A-XDR 数据项的值"""
        t = item["type"]
        w = item.get("_value_widget")

        result = {"tag": item["tag"], "type": t}

        # 收集长度/个数
        len_edit = item.get("_len_edit")
        if len_edit and len_edit.isEnabled():
            try:
                result["length"] = int(len_edit.text().strip())
            except ValueError:
                result["length"] = 0
        else:
            result["length"] = item.get("length", 0)

        if w is None:
            result["value"] = item.get("value", 0)
            if t in self.COMPOUND_TYPES:
                result["children"] = [self._collect_axdr_values(c) for c in item.get("children", [])]
            return result

        if t == "bool":
            cb = w.findChild(QCheckBox)
            val = cb.isChecked() if cb else False
        elif t in ("OAD", "OMD"):
            # 复合子控件
            combos = w.findChildren(QComboBox)
            # 排除可编辑下拉框内部的行编辑，避免干扰 属性/索引 输入框定位
            edits = [e for e in w.findChildren(QLineEdit)
                     if not isinstance(e.parent(), QComboBox)]
            oi_val = item.get("oi", 0)
            if combos:
                data = combos[0].currentData()
                if data is not None:
                    oi_val = data
                else:
                    txt = combos[0].currentText().strip().replace(" ", "")
                    try:
                        oi_val = int(txt, 16) if txt else 0
                    except ValueError:
                        oi_val = item.get("oi", 0)
            item["oi"] = oi_val
            sub_vals = {}
            for e in edits:
                try:
                    sub_vals[e.objectName()] = int(e.text())
                except ValueError:
                    sub_vals[e.objectName()] = e.text()
            if t == "OAD":
                val = {"OI": oi_val, "属性编号": item.get("attr", 2), "属性特征": 0, "元素索引": item.get("index", 0)}
            else:
                val = {"OI": oi_val, "方法标识": item.get("method", 1), "操作模式": item.get("mode", 0)}
            # Update from edits
            if len(edits) >= 2:
                item["attr"] = int(edits[0].text() or 2) if not t == "OMD" else item.get("attr", 2)
                item["index"] = int(edits[-1].text() or 0) if t == "OAD" else item.get("index", 0)
        elif t in ("octet-string", "bit-string", "date_time", "date", "time", "date_time_s",
                    "TI", "TSA", "MAC", "RN"):
            edit = w.findChild(QLineEdit)
            val = edit.text().strip() if edit else ""
        elif t in ("visible-string", "UTF8-string"):
            edit = w.findChild(QLineEdit)
            val = edit.text() if edit else ""
        elif t == "OI":
            combo = w.findChild(QComboBox)
            if combo is not None:
                val = combo.currentData()
                if val is None:
                    txt = combo.currentText().strip().replace(" ", "")
                    try:
                        val = int(txt, 16) if txt else 0
                    except ValueError:
                        val = 0
            else:
                val = 0
        elif t in ("integer", "long", "long64"):
            edit = w.findChild(QLineEdit)
            try:
                val = int(edit.text()) if edit else 0
            except (ValueError, AttributeError):
                val = 0
        elif t in ("float32", "float64"):
            edit = w.findChild(QLineEdit)
            try:
                val = float(edit.text()) if edit else 0.0
            except (ValueError, AttributeError):
                val = 0.0
        else:
            edit = w.findChild(QLineEdit)
            try:
                txt = edit.text().strip() if edit else "0"
                val = int(txt, 0) if txt else 0
            except (ValueError, AttributeError):
                val = 0

        item["value"] = val
        result["value"] = val
        if t in self.COMPOUND_TYPES:
            result["children"] = [self._collect_axdr_values(c) for c in item.get("children", [])]

        return result

    def _encode_axdr_data(self) -> bytes:
        """将所有 A-XDR 数据项编码为字节"""
        from dl_t698_45_axdr import AXDRCoder
        coder = AXDRCoder()
        data = b""
        for item in self._axdr_items:
            collected = self._collect_axdr_values(item)
            data += self._encode_axdr_item(coder, collected)
        return data

    def _encode_axdr_item(self, coder, item: dict) -> bytes:
        """递归编码单个 A-XDR 数据项"""
        tag = item["tag"]
        t = item["type"]
        value = item.get("value", 0)
        length = item.get("length", 0)

        if t in self.COMPOUND_TYPES:
            children = item.get("children", [])
            result = bytes([tag])
            child_data = b""
            for child in children:
                child_data += self._encode_axdr_item(coder, child)
            # A-XDR structure/array：tag 后为元素个数（非字节总长）
            result += coder._encode_length(len(children))
            result += child_data
            return result

        if t == "bool":
            return coder.encode(value, tag)
        if t in ("octet-string", "bit-string"):
            raw = bytes.fromhex(str(value).replace(" ", "")) if isinstance(value, str) and value else b""
            if length > 0:
                raw = raw.ljust(length, b'\x00')[:length]
            return bytes([tag]) + coder._encode_length(len(raw)) + raw
        if t in ("visible-string", "UTF8-string"):
            data = str(value).encode('ascii' if t == "visible-string" else 'utf-8', errors='replace')
            if length > 0:
                data = data.ljust(length, b'\x00')[:length]
            return bytes([tag]) + coder._encode_length(len(data)) + data
        if t in ("date_time", "date", "time", "date_time_s", "TI", "TSA", "MAC", "RN"):
            raw = bytes.fromhex(str(value).replace(" ", "")) if isinstance(value, str) and value else b""
            if length > 0:
                raw = raw.ljust(length, b'\x00')[:length]
            return bytes([tag]) + coder._encode_length(len(raw)) + raw
        if t == "OI":
            return coder.encode(int(value), tag)
        if t in ("OAD", "OMD"):
            return coder.encode(value, tag)
        if t == "null":
            return coder.encode(None, tag)

        # 数值类型
        return coder.encode(value, tag)

    # ------------------------------------------------------------------
    # 自定义字段模板 UI（参考图2）
    # ------------------------------------------------------------------
    def _build_custom_template_ui(self):
        # ---- 模板表格 ----
        table_group = QGroupBox("字段模板定义（参考协议文档填写）")
        table_layout = QVBoxLayout(table_group)
        table_layout.setSpacing(4)
        table_layout.setContentsMargins(8, 8, 8, 8)

        # 说明标签
        hint = QLabel("添加字段：定义名称、长度、类型、字节序，并在右侧填写字段值。组帧时按顺序打包。")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        table_layout.addWidget(hint)

        self.template_table = ZoomableTableWidget()
        self.template_table.setColumnCount(7)
        self.template_table.setHorizontalHeaderLabels([
            "序号", "名称", "长度(字节)", "数据类型", "字节序", "显示进制", "字段值填充"
        ])
        header = self.template_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setFixedHeight(22)
        self.template_table.setColumnWidth(0, 45)
        self.template_table.setColumnWidth(1, 120)
        self.template_table.setColumnWidth(2, 70)
        self.template_table.setColumnWidth(3, 90)
        self.template_table.setColumnWidth(4, 70)
        self.template_table.setColumnWidth(5, 70)
        self.template_table.setColumnWidth(6, 160)
        self.template_table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        self.template_table.setAlternatingRowColors(True)
        # 紧凑行高，隐藏垂直表头（序号列已自带行号）
        self.template_table.verticalHeader().setVisible(False)
        self.template_table.verticalHeader().setDefaultSectionSize(20)
        self.template_table.setStyleSheet("QTableWidget::item { padding: 1px 3px; } QComboBox { min-height: 18px; max-height: 22px; padding: 1px 4px; } QLineEdit { min-height: 18px; max-height: 22px; padding: 1px 4px; }")
        self.template_table.setMinimumHeight(140)
        table_layout.addWidget(self.template_table, 1)

        # 模板操作按钮
        tpl_btn_layout = QHBoxLayout()
        tpl_btn_layout.setSpacing(6)
        add_row_btn = QPushButton("添加字段")
        add_row_btn.setStyleSheet("QPushButton { padding: 2px 10px; }")
        add_row_btn.clicked.connect(self._add_template_row)
        del_row_btn = QPushButton("删除选中字段")
        del_row_btn.setStyleSheet("QPushButton { padding: 2px 10px; }")
        del_row_btn.clicked.connect(self._del_template_row)
        load_tpl_btn = QPushButton("加载默认模板")
        load_tpl_btn.setStyleSheet("QPushButton { padding: 2px 10px; }")
        load_tpl_btn.clicked.connect(self._load_default_template)
        tpl_btn_layout.addWidget(add_row_btn)
        tpl_btn_layout.addWidget(del_row_btn)
        tpl_btn_layout.addWidget(load_tpl_btn)
        tpl_btn_layout.addStretch()
        table_layout.addLayout(tpl_btn_layout)

        self._form_layout.addWidget(table_group, 1)

        # 初始化默认模板（如果空）
        if not self._custom_templates:
            self._load_default_template()
        else:
            self._refresh_template_table()

    def _load_default_template(self):
        """加载默认的通用字段模板"""
        self._custom_templates = [
            CustomFieldTemplate("用户数据", 1, "bytes", "big", "hex", False)
        ]
        self._refresh_template_table()

    def _refresh_template_table(self):
        """刷新模板表格显示"""
        self.template_table.setRowCount(len(self._custom_templates))
        for row, tpl in enumerate(self._custom_templates):
            self.template_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.template_table.setItem(row, 1, QTableWidgetItem(tpl.name))
            self.template_table.setItem(row, 2, QTableWidgetItem(str(tpl.length)))

            type_combo = QComboBox()
            type_combo.addItems(["uint8", "uint16", "uint32", "bytes", "checksum"])
            type_combo.setCurrentText(tpl.ftype)
            type_combo.setFixedHeight(20)
            self.template_table.setCellWidget(row, 3, type_combo)

            endian_combo = QComboBox()
            endian_combo.addItems(["big", "little"])
            endian_combo.setCurrentText(tpl.endian)
            endian_combo.setFixedHeight(20)
            self.template_table.setCellWidget(row, 4, endian_combo)

            display_combo = QComboBox()
            display_combo.addItems(["hex", "dec"])
            display_combo.setCurrentText(tpl.display)
            display_combo.setFixedHeight(20)
            self.template_table.setCellWidget(row, 5, display_combo)

            # 字段值输入列
            if tpl.ftype == "checksum":
                cs_label = QLabel("自动计算")
                cs_label.setStyleSheet("color: #2196F3; font-size: 11px;")
                cs_label.setFixedHeight(20)
                cs_label.setAlignment(Qt.AlignCenter)
                self.template_table.setCellWidget(row, 6, cs_label)
            else:
                val_edit = QLineEdit()
                val_edit.setFixedHeight(20)
                if tpl.display == "hex":
                    val_edit.setPlaceholderText("hex")
                else:
                    val_edit.setPlaceholderText("decimal")
                self.template_table.setCellWidget(row, 6, val_edit)
        self._connect_template_signals()
        self._schedule_realtime_update()
        apply_chinese_context_menus(self.template_table)

    def _add_template_row(self):
        """添加一行模板字段"""
        self._sync_templates_from_table()
        self._custom_templates.append(CustomFieldTemplate("新字段", 1, "bytes", "big", "hex", False))
        self._refresh_template_table()

    def _del_template_row(self):
        """删除选中的模板字段"""
        row = self.template_table.currentRow()
        if row >= 0 and row < len(self._custom_templates):
            self._sync_templates_from_table()
            del self._custom_templates[row]
            self._refresh_template_table()

    def _sync_templates_from_table(self):
        """从表格同步模板数据到内存"""
        new_templates = []
        for row in range(self.template_table.rowCount()):
            name_item = self.template_table.item(row, 1)
            len_item = self.template_table.item(row, 2)
            type_combo = self.template_table.cellWidget(row, 3)
            endian_combo = self.template_table.cellWidget(row, 4)
            display_combo = self.template_table.cellWidget(row, 5)

            name = name_item.text() if name_item else f"字段{row+1}"
            try:
                length = int(len_item.text()) if len_item else 1
            except ValueError:
                length = 1
            ftype = type_combo.currentText() if type_combo else "bytes"
            endian = endian_combo.currentText() if endian_combo else "big"
            display = display_combo.currentText() if display_combo else "hex"

            new_templates.append(CustomFieldTemplate(name, length, ftype, endian, display, False))
        self._custom_templates = new_templates

    # ------------------------------------------------------------------
    # 预定义字段控件
    # ------------------------------------------------------------------
    def _create_field_widget(self, field: Dict[str, Any], widget_store: Dict[str, Dict[str, Any]] = None) -> QWidget:
        """创建单个字段的输入控件。

        Args:
            field: 字段 schema
            widget_store: 控件存放字典（默认 self._field_widgets，EB 生成器传 _eb_field_widgets）
        """
        if widget_store is None:
            widget_store = self._field_widgets
        name = field["name"]
        ftype = field["type"]
        desc = field.get("description", "")
        default = field.get("default")
        optional = field.get("optional", False)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)

        label_text = name
        if desc:
            label_text += f"  [{desc}]"
        label = QLabel(label_text)
        label.setMinimumWidth(180)
        label.setToolTip(desc)
        layout.addWidget(label)

        if optional:
            cb = QCheckBox("启用")
            cb.setChecked(True)
            layout.addWidget(cb)
            widget_store[name] = {"checkbox": cb, "widget": None}
        else:
            widget_store[name] = {"widget": None}

        if "sub_fields" in field:
            sub_container = QWidget()
            sub_layout = QHBoxLayout(sub_container)
            sub_layout.setContentsMargins(0, 0, 0, 0)
            sub_layout.setSpacing(4)
            sub_widgets: Dict[str, Any] = {}
            for sub in field["sub_fields"]:
                sub_name = sub["name"]
                sub_type = sub.get("type", "bytes")
                sub_default = sub.get("default")
                sub_desc = sub.get("description", "")
                sub_label = QLabel(sub_name)
                sub_label.setStyleSheet("font-size: 11px; color: #555;")
                sub_label.setToolTip(sub_desc)
                sub_layout.addWidget(sub_label)
                if sub_type == "enum":
                    combo = QComboBox()
                    for val, text in sub.get("enum_map", {}).items():
                        combo.addItem(f"{text} (0x{val:02X})", val)
                    if sub_default is not None:
                        idx = combo.findData(sub_default)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                    combo.currentIndexChanged.connect(self._schedule_realtime_update)
                    sub_layout.addWidget(combo)
                    sub_widgets[sub_name] = combo
                elif sub_type in ("uint8", "uint16", "uint32"):
                    edit = QLineEdit()
                    if sub_default is not None:
                        edit.setText(str(sub_default))
                    edit.setFixedWidth(50)
                    edit.textChanged.connect(self._schedule_realtime_update)
                    sub_layout.addWidget(edit)
                    sub_widgets[sub_name] = edit
                elif sub_type == "bytes":
                    edit = QLineEdit()
                    if sub_default is not None:
                        edit.setText(str(sub_default))
                    edit.textChanged.connect(self._schedule_realtime_update)
                    sub_layout.addWidget(edit)
                    sub_widgets[sub_name] = edit
            sub_layout.addStretch()
            layout.addWidget(sub_container)
            widget_store[name]["widget"] = sub_container
            widget_store[name]["sub_widgets"] = sub_widgets

        elif ftype in ("uint8", "uint16", "uint32"):
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            # 限制为非负整数
            edit.setValidator(QIntValidator(0, 2147483647, edit))
            layout.addWidget(edit)
            widget_store[name]["widget"] = edit

        elif ftype == "bytes":
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            if field.get("reverse"):
                edit.setPlaceholderText("正常顺序hex，自动反转")
            else:
                edit.setPlaceholderText("HEX")
            # 限制只允许十六进制字符和空格
            regex = QRegularExpression(r"[0-9A-Fa-f ]+")
            edit.setValidator(QRegularExpressionValidator(regex, edit))
            layout.addWidget(edit)
            widget_store[name]["widget"] = edit

        elif ftype == "enum":
            combo = QComboBox()
            enum_map = field.get("enum_map", {})
            for val, text in enum_map.items():
                combo.addItem(f"{text}  (0x{val:02X})", val)
            if default is not None:
                idx = combo.findData(default)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            layout.addWidget(combo)
            widget_store[name]["widget"] = combo

        elif ftype == "list":
            list_widget = self._create_list_widget(field)
            layout.addWidget(list_widget, 1)
            widget_store[name]["widget"] = list_widget

        else:
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            layout.addWidget(edit)
            widget_store[name]["widget"] = edit

        layout.addStretch()
        return container

    def _create_list_widget(self, field: Dict[str, Any]) -> QWidget:
        item_fields = field["item_fields"]
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(f"<b>{field['name']}</b>")
        layout.addWidget(header)

        items_widget = QWidget()
        items_layout = QVBoxLayout(items_widget)
        items_layout.setAlignment(Qt.AlignTop)
        layout.addWidget(items_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加")
        del_btn = QPushButton("删除最后一项")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        container._items_layout = items_layout
        container._items: List[Tuple[QWidget, Dict[str, Any]]] = []
        container._item_fields = item_fields

        def add_item():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(2, 2, 2, 2)
            item_widgets: Dict[str, Any] = {}
            for item_field in item_fields:
                item_name = item_field["name"]
                item_type = item_field["type"]
                lbl = QLabel(item_name)
                lbl.setStyleSheet("font-size: 11px; color: #555;")
                row_layout.addWidget(lbl)
                if item_type == "bytes":
                    edit = QLineEdit()
                    dft = item_field.get("default", "")
                    edit.setText(str(dft))
                    if item_field.get("reverse"):
                        edit.setPlaceholderText("hex, 自动反转")
                    edit.textChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(edit)
                    item_widgets[item_name] = edit
                elif item_type in ("uint8", "uint16", "uint32"):
                    edit = QLineEdit()
                    dft = item_field.get("default", 0)
                    edit.setText(str(dft))
                    edit.textChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(edit)
                    item_widgets[item_name] = edit
                elif item_type == "enum":
                    combo = QComboBox()
                    for val, text in item_field.get("enum_map", {}).items():
                        combo.addItem(f"{text} (0x{val:02X})", val)
                    dft = item_field.get("default")
                    if dft is not None:
                        idx = combo.findData(dft)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                    combo.currentIndexChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(combo)
                    item_widgets[item_name] = combo
                else:
                    edit = QLineEdit()
                    edit.textChanged.connect(self._schedule_realtime_update)
                    row_layout.addWidget(edit)
                    item_widgets[item_name] = edit
            row_layout.addStretch()
            items_layout.addWidget(row_widget)
            container._items.append((row_widget, item_widgets))
            self._schedule_realtime_update()

        def del_item():
            if container._items:
                row_widget, _ = container._items.pop()
                row_widget.deleteLater()

        add_btn.clicked.connect(add_item)
        del_btn.clicked.connect(del_item)
        add_item()
        return container

    # ------------------------------------------------------------------
    # 收集字段值并组帧
    # ------------------------------------------------------------------
    def _collect_values(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        if self.protocol_mode == "south":
            if not self._current_di_key:
                return values
        elif self.protocol_mode == "dlt698":
            if not self._current_dlt698_key:
                return values
        else:
            if not self._current_afn_fn:
                return values

        if self._custom_mode:
            self._sync_templates_from_table()
            for row, tpl in enumerate(self._custom_templates):
                if tpl.ftype == "checksum":
                    continue
                val_widget = self.template_table.cellWidget(row, 6)
                if not isinstance(val_widget, QLineEdit):
                    continue
                text = val_widget.text().strip()
                if tpl.ftype in ("uint8", "uint16", "uint32"):
                    if tpl.display == "hex":
                        values[tpl.name] = int(text, 16) if text else 0
                    else:
                        values[tpl.name] = int(text, 10) if text else 0
                else:
                    values[tpl.name] = text
        else:
            if self.protocol_mode == "south":
                schema = DI_FIELD_SCHEMA.get(self._current_di_key, {})
            elif self.protocol_mode == "dlt698":
                schema = DLT69845_FIELD_SCHEMA.get(self._current_dlt698_key, {})
            else:
                schema = GDW_AFNFN_SCHEMA.get(self._current_afn_fn, {})
            for field in schema.get("fields", []):
                name = field["name"]
                widget_info = self._field_widgets.get(name)
                if not widget_info:
                    continue
                if "checkbox" in widget_info:
                    if not widget_info["checkbox"].isChecked():
                        continue
                widget = widget_info["widget"]
                ftype = field["type"]

                if "sub_widgets" in widget_info:
                    # 收集子字段值
                    for sub_name, sub_widget in widget_info["sub_widgets"].items():
                        sub_field = next((s for s in field.get("sub_fields", []) if s["name"] == sub_name), None)
                        if not sub_field:
                            continue
                        sub_type = sub_field.get("type", "bytes")
                        if sub_type == "enum":
                            values[sub_name] = sub_widget.currentData()
                        elif sub_type in ("uint8", "uint16", "uint32"):
                            text = sub_widget.text().strip()
                            values[sub_name] = int(text, 0) if text else 0
                        elif sub_type == "bytes":
                            values[sub_name] = sub_widget.text().strip()
                    # 计算父字段值
                    if ftype in ("uint8", "enum"):
                        parent_val = 0
                        for sub in field.get("sub_fields", []):
                            sub_name = sub["name"]
                            sub_val = values.get(sub_name, sub.get("default", 0))
                            bit_width = sub.get("bit_width", 1)
                            bit_offset = sub.get("bit_offset", 0)
                            mask = (1 << bit_width) - 1
                            parent_val |= (int(sub_val) & mask) << bit_offset
                        values[name] = parent_val
                    elif ftype == "bytes":
                        parent_val = ""
                        for sub in field.get("sub_fields", []):
                            cond = sub.get("condition")
                            if cond:
                                ref_val = values.get(cond["field"])
                                if ref_val != cond["value"]:
                                    continue
                            sub_name = sub["name"]
                            sub_val = values.get(sub_name, sub.get("default", ""))
                            sub_type = sub.get("type", "bytes")
                            if sub_type in ("uint8", "enum"):
                                parent_val += f"{int(sub_val):02X}"
                            elif sub_type == "bytes":
                                parent_val += str(sub_val)
                        values[name] = parent_val

                elif ftype in ("uint8", "uint16", "uint32"):
                    text = widget.text().strip()
                    values[name] = int(text, 0) if text else 0
                elif ftype == "bytes":
                    values[name] = widget.text().strip()
                elif ftype == "enum":
                    values[name] = widget.currentData()
                elif ftype == "list":
                    items = []
                    for _, item_widgets in widget._items:
                        item_values: Dict[str, Any] = {}
                        for item_name, item_widget in item_widgets.items():
                            if isinstance(item_widget, QComboBox):
                                item_values[item_name] = item_widget.currentData()
                            else:
                                item_values[item_name] = item_widget.text().strip()
                        items.append(item_values)
                    values[name] = items
                elif ftype == "oi":
                    if isinstance(widget, QComboBox):
                        val = widget.currentData()
                        values[name] = val if val is not None else 0
                    else:
                        text = widget.text().strip()
                        try:
                            values[name] = int(text, 16) if text else 0
                        except ValueError:
                            values[name] = 0
                elif ftype == "oad_list":
                    values[name] = widget.text().strip()
                else:
                    values[name] = widget.text().strip()

        # dlt698: 由 PIID 子输入合成 PIID 字节（优先级D7+序号D6-D0），并收集自定义数据内容
        if self.protocol_mode == "dlt698" and not self._custom_mode:
            prio_w = self._field_widgets.get("PIID_优先级", {}).get("widget")
            seq_w = self._field_widgets.get("PIID_序号", {}).get("widget")
            if prio_w is not None and seq_w is not None:
                try:
                    prio = int(prio_w.currentData() or 0) & 0x01
                    seq = int(seq_w.text().strip() or 1) & 0x7F
                    values["PIID"] = (prio << 7) | seq
                except ValueError:
                    values["PIID"] = 1
            custom_w = self._field_widgets.get("自定义数据内容", {}).get("widget")
            if custom_w is not None:
                custom_text = custom_w.text().strip()
                if custom_text:
                    values["自定义数据内容"] = custom_text
            # 索引字段由 schema 处理，无需特殊合成

        return values

    def _generate_custom_data(self) -> bytes:
        """根据自定义模板生成用户数据区字节"""
        import struct
        self._sync_templates_from_table()
        data = b""
        checksum_idx = -1

        for row, tpl in enumerate(self._custom_templates):
            if tpl.ftype == "checksum":
                checksum_idx = row
                data += b"\x00" * tpl.length  # 占位，后面回填
                continue

            val_widget = self.template_table.cellWidget(row, 6)
            if isinstance(val_widget, QLineEdit):
                text = val_widget.text().strip().replace(" ", "")
            else:
                text = ""

            if tpl.ftype == "bytes":
                if text:
                    try:
                        raw = bytes.fromhex(text)
                    except ValueError:
                        raw = b""
                else:
                    raw = b""
                if len(raw) < tpl.length:
                    raw = raw + b"\x00" * (tpl.length - len(raw))
                elif len(raw) > tpl.length:
                    raw = raw[:tpl.length]
            elif tpl.ftype in ("uint8", "uint16", "uint32"):
                try:
                    if tpl.display == "hex":
                        val = int(text, 16) if text else 0
                    else:
                        val = int(text, 10) if text else 0
                except ValueError:
                    val = 0
                if tpl.ftype == "uint8":
                    raw = struct.pack("B", val & 0xFF)
                elif tpl.ftype == "uint16":
                    if tpl.endian == "little":
                        raw = struct.pack("<H", val & 0xFFFF)
                    else:
                        raw = struct.pack(">H", val & 0xFFFF)
                else:  # uint32
                    if tpl.endian == "little":
                        raw = struct.pack("<I", val & 0xFFFFFFFF)
                    else:
                        raw = struct.pack(">I", val & 0xFFFFFFFF)
            else:
                raw = b"\x00" * tpl.length

            data += raw

        # 回填校验和
        if checksum_idx >= 0:
            cs = sum(data) & 0xFF
            # 校验和字段在data中的偏移量
            offset = 0
            for i, tpl in enumerate(self._custom_templates):
                if i == checksum_idx:
                    data = data[:offset] + struct.pack("B", cs) + data[offset+1:]
                    break
                offset += tpl.length

        return data

    # ------------------------------------------------------------------
    # 实时解析预览
    # ------------------------------------------------------------------
    def _schedule_realtime_update(self):
        """调度实时更新（200ms debounce）"""
        if self._update_timer is not None:
            self._update_timer.stop()
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._do_realtime_update)
        self._update_timer.start(200)

    def _do_realtime_update(self):
        """执行实时组帧与解析"""
        try:
            if self.protocol_mode == "south":
                self._do_realtime_update_south()
            elif self.protocol_mode == "dlt698":
                self._do_realtime_update_dlt698()
            elif self.protocol_mode == "dlt645":
                self._do_realtime_update_dlt645()
            else:
                self._do_realtime_update_gdw()
        except Exception:
            pass

    def _do_realtime_update_dlt645(self):
        """DLT645-2007 实时组帧与解析（200ms 轮询）

        与其他模式一致：字段变化后自动重生成帧、刷新生成结果 hex，
        并把解析结果填入右侧「实时解析预览」表。
        """
        key = self._current_dlt645_key
        if not key:
            self.preview_table.setRowCount(0)
            return
        fv = self._collect_dlt645_values()
        addr = self._dlt645_addr_value() or None
        try:
            frame = self._dlt645_gen.generate_frame(key, fv, addr=addr)
        except Exception:
            # 输入不完整/非法时静默清空预览（定时器高频运行，不弹窗）
            self.preview_table.setRowCount(0)
            return
        hex_str = frame.hex().upper()
        self.result_hex.setText(
            " ".join(hex_str[i:i + 2] for i in range(0, len(hex_str), 2)))
        try:
            r = DLT645Parser.parse(frame)
        except Exception:
            self.preview_table.setRowCount(0)
            return
        # parse() 的 fields 行有 3 元组（表头类）与 4 元组两种，统一补齐到 4 列
        rows = []
        for it in r.get("fields", []):
            it = tuple(it)
            rows.append(it + ("",) * max(0, 4 - len(it)))
        self._populate_preview_table(rows)
        self._refresh_dlt645_warning(fv)
        self._verify_dlt645_frame(frame)

    def _do_realtime_update_south(self):
        """南网实时组帧与解析"""
        if not self._current_di_key:
            self.preview_table.setRowCount(0)
            return

        src_text = self.src_addr_input.text().strip().replace(" ", "")
        dst_text = self.dst_addr_input.text().strip().replace(" ", "")
        if len(src_text) != 12 or len(dst_text) != 12:
            self.preview_table.setRowCount(0)
            return
        try:
            src_addr = bytes.fromhex(src_text)
            dst_addr = bytes.fromhex(dst_text)
        except ValueError:
            self.preview_table.setRowCount(0)
            return

        di_key = self._current_di_key
        dir_flag = self.dir_combo.currentData()
        prm = self.prm_combo.currentData()
        add_flag = self.add_combo.currentData()

        if self._custom_mode:
            data = self._generate_custom_data()
            di3, di2, di1, di0 = di_key
            frame = self.generator._build_frame(
                di3, di2, di1, di0,
                src_addr=src_addr, dst_addr=dst_addr, data=data,
                dir_flag=dir_flag, prm=prm, add_flag=add_flag
            )
        else:
            field_values = self._collect_values()
            frame = self.generator.generate_frame(
                di_key, field_values,
                src_addr=src_addr, dst_addr=dst_addr,
                dir_flag=dir_flag, prm=prm, add_flag=add_flag
            )

        table_data = self.parser.parse_to_table(frame)
        self._populate_preview_table(table_data)

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

    def _do_realtime_update_gdw(self):
        """国网实时组帧与解析"""
        if not self._current_afn_fn:
            self.preview_table.setRowCount(0)
            return

        afn, fn = self._current_afn_fn
        try:
            seq = int(self.gdw_seq.text().strip()) & 0xFF
            channel = int(self.gdw_channel.text().strip()) & 0x0F
            resp_bytes = int(self.gdw_resp_bytes.text().strip()) & 0xFF
        except ValueError:
            self.preview_table.setRowCount(0)
            return

        info_config = {
            "dir": self.gdw_dir.currentData(),
            "prm": self.gdw_prm.currentData(),
            "通信方式": self.gdw_comm_type.currentData(),
            "路由标识": self.gdw_route_flag.currentData(),
            "附属节点标识": 0,
            "通信模块标识": self.gdw_comm_module.currentData(),
            "冲突检测": 0,
            "中继级别": self.gdw_relay_level.currentData(),
            "纠错编码标识": 0,
            "信道标识": channel,
            "预计应答字节数": resp_bytes,
            "通信速率": 0,
            "速率单位标识": 0,
            "报文序列号": seq,
        }

        src_addr = self.gdw_src_addr.text().strip()
        dst_addr = self.gdw_dst_addr.text().strip()
        relay_addrs = [edit.text().strip() for edit in self.gdw_relay_inputs]

        field_values = self._collect_values()

        frame = self.gdw_generator.generate_frame(
            afn, fn, field_values, info_config,
            src_addr=src_addr, dst_addr=dst_addr, relay_addrs=relay_addrs
        )

        table_data = self.gdw_parser.parse_to_table(frame)
        self._populate_preview_table(table_data)

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

    def _populate_preview_table(self, table_data: list):
        """填充实时预览表格"""
        self.preview_table.setRowCount(0)
        for row, item in enumerate(table_data):
            field_name = item[0]
            raw_value = item[1]
            parsed_value = item[2]
            comment = item[3]
            self.preview_table.insertRow(row)
            self.preview_table.setItem(row, 0, QTableWidgetItem(str(field_name)))
            self.preview_table.setItem(row, 1, QTableWidgetItem(str(raw_value)))
            self.preview_table.setItem(row, 2, QTableWidgetItem(str(parsed_value)))
            self.preview_table.setItem(row, 3, QTableWidgetItem(str(comment)))

    def _do_realtime_update_dlt698(self):
        """698.45实时组帧与解析"""
        if not self._current_dlt698_key:
            self.preview_table.setRowCount(0)
            return

        apdu_type, sub_type = self._current_dlt698_key

        # 收集地址信息
        sa = self._get_dlt698_sa()
        ca_text = self.dlt698_ca.text().strip()
        if not sa:
            self.preview_table.setRowCount(0)
            return
        try:
            ca = int(ca_text, 0) & 0xFF
        except (ValueError, TypeError):
            self.preview_table.setRowCount(0)
            return

        dir_bit = self.dlt698_dir.currentData()
        prm_bit = self.dlt698_prm.currentData()
        sc_bit = self.dlt698_sc.currentData()
        seg_bit = self.dlt698_seg.currentData()
        func_code = self.dlt698_func.currentData()

        # A-XDR 模式：使用 A-XDR 数据生成（PIID + OAD/OMD + A-XDR用户数据）
        if self._axdr_mode:
            try:
                axdr_data = self._encode_axdr_data()
                field_values = self._collect_values()
                # 补充 OI 下拉框的值
                for name, widget_info in list(self._field_widgets.items()):
                    widget = widget_info.get("widget")
                    if isinstance(widget, QComboBox):
                        val = widget.currentData()
                        if val is not None:
                            field_values[name] = val

                import struct as _struct
                # PIID = 优先级(D7) | 序号(D6-D0)
                priority = int(field_values.get("PIID_优先级", 0)) & 0x01
                seq = int(field_values.get("PIID_序号", 1)) & 0x7F
                piid = (priority << 7) | seq

                if apdu_type == "_custom_":
                    apdu_bytes = bytes([0x05, 0x01, piid]) + axdr_data
                else:
                    apdu_header = self.dlt698_generator._build_apdu_header(apdu_type, sub_type)
                    apdu_body = _struct.pack("B", piid)

                    oi_widget = self._field_widgets.get("OI", {}).get("widget")
                    oi_text = oi_widget.text().strip().replace(" ", "") if isinstance(oi_widget, QLineEdit) else "0000"
                    try:
                        oi_bytes = bytes.fromhex(oi_text)
                    except ValueError:
                        oi_bytes = b'\x00\x00'
                    oi_bytes = oi_bytes.ljust(2, b'\x00')[:2]

                    if apdu_type in ("GET-Request", "SET-Request", "ACTION-Request"):
                        desc_widget = self._field_widgets.get("描述符类型", {}).get("widget")
                        desc_kind = desc_widget.currentData() if isinstance(desc_widget, QComboBox) else None
                        if desc_kind is None:
                            desc_kind = "OMD" if apdu_type == "ACTION-Request" else "OAD"

                        def _int_edit(name, default):
                            w = self._field_widgets.get(name, {}).get("widget")
                            if isinstance(w, QLineEdit):
                                try:
                                    return int(w.text().strip() or default, 0)
                                except ValueError:
                                    return default
                            return int(field_values.get(name, default))

                        if desc_kind == "OMD":
                            method = _int_edit("方法标识", 1) & 0x1F
                            mode = _int_edit("操作模式", 0) & 0xFF
                            apdu_body += oi_bytes + _struct.pack("B", method) + _struct.pack("B", mode)
                        else:
                            attr = _int_edit("属性标识", 2) & 0x1F
                            idx = _int_edit("索引", 0) & 0xFF
                            apdu_body += oi_bytes + _struct.pack("B", attr) + _struct.pack("B", idx)

                    apdu_body += axdr_data

                    # 请求尾部「没有时间标签」（文档 H.3/H.4/H.5：GET/SET/ACTION 均以 OPTIONAL TimeLabel 结尾，00=无）
                    if apdu_type in ("GET-Request", "SET-Request", "ACTION-Request"):
                        apdu_body += b'\x00'

                    apdu_bytes = apdu_header + apdu_body

                frame = self.dlt698_generator._assemble_frame(
                    sa, ca,
                    self.dlt698_generator.build_control(dir_bit=dir_bit, prm_bit=prm_bit,
                                                          seg_bit=seg_bit, sc_bit=sc_bit, func_code=func_code),
                    apdu_bytes
                )
            except Exception:
                self.preview_table.setRowCount(0)
                return
            table_data = self.dlt698_parser.parse_to_table(frame)
            self._populate_preview_table(table_data)
            hex_str = frame.hex().upper()
            self.result_hex.setText(" ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2)))
            return

        field_values = self._collect_values()
        # OI 字段特殊处理：如果 widget 是 QComboBox，取 currentData
        if not self._custom_mode:
            for name, widget_info in list(self._field_widgets.items()):
                widget = widget_info.get("widget")
                if isinstance(widget, QComboBox):
                    val = widget.currentData()
                    if val is not None:
                        field_values[name] = val

        try:
            frame = self.dlt698_generator.generate_frame(
                apdu_type, sub_type, field_values,
                sa=sa, ca=ca,
                dir_bit=dir_bit, prm_bit=prm_bit,
                seg_bit=seg_bit, sc_bit=sc_bit,
                func_code=func_code
            )
        except Exception:
            self.preview_table.setRowCount(0)
            return

        table_data = self.dlt698_parser.parse_to_table(frame)
        self._populate_preview_table(table_data)

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

    def _connect_field_signals(self):
        """连接预定义字段widget的实时更新信号"""
        for widget_info in self._field_widgets.values():
            widget = widget_info.get("widget")
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._schedule_realtime_update)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._schedule_realtime_update)
            elif widget is not None and hasattr(widget, '_items'):
                # list widget: connect add/del buttons indirectly via _schedule
                # 子字段的lineedits/combos在add_item时已创建，这里无法提前连接
                # 因此list类型实时更新依赖用户点击生成按钮，或者我们在add_item里连接
                pass
            cb = widget_info.get("checkbox")
            if isinstance(cb, QCheckBox):
                cb.stateChanged.connect(self._schedule_realtime_update)

    def _connect_template_signals(self):
        """连接自定义模板表格的实时更新信号"""
        if not hasattr(self, 'template_table'):
            return
        self.template_table.itemChanged.connect(self._schedule_realtime_update)
        for row in range(self.template_table.rowCount()):
            for col in (3, 4, 5):
                cw = self.template_table.cellWidget(row, col)
                if isinstance(cw, QComboBox):
                    cw.currentIndexChanged.connect(self._schedule_realtime_update)
            cw6 = self.template_table.cellWidget(row, 6)
            if isinstance(cw6, QLineEdit):
                cw6.textChanged.connect(self._schedule_realtime_update)

    def _on_generate(self):
        try:
            if self.protocol_mode == "south":
                self._generate_south_frame()
            elif self.protocol_mode == "dlt698":
                self._generate_dlt698_frame()
            elif self.protocol_mode == "dlt645":
                self._generate_dlt645_frame()
            else:
                self._generate_gdw_frame()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"组帧失败：{str(e)}")

    def _generate_south_frame(self):
        """生成南网协议帧"""
        if not self._current_di_key:
            QMessageBox.warning(self, "警告", "请先选择一个DI命令")
            return

        src_text = self.src_addr_input.text().strip().replace(" ", "")
        dst_text = self.dst_addr_input.text().strip().replace(" ", "")
        if len(src_text) != 12 or len(dst_text) != 12:
            QMessageBox.warning(self, "警告", "源地址和目的地址必须为12位十六进制字符（6字节）")
            return
        try:
            src_addr = bytes.fromhex(src_text)
            dst_addr = bytes.fromhex(dst_text)
        except ValueError:
            QMessageBox.warning(self, "警告", "地址格式错误，请输入有效的十六进制字符串")
            return

        di_key = self._current_di_key
        dir_flag = self.dir_combo.currentData()
        prm = self.prm_combo.currentData()
        add_flag = self.add_combo.currentData()

        if self._custom_mode:
            data = self._generate_custom_data()
            di3, di2, di1, di0 = di_key
            frame = self.generator._build_frame(
                di3, di2, di1, di0,
                src_addr=src_addr, dst_addr=dst_addr, data=data,
                dir_flag=dir_flag, prm=prm, add_flag=add_flag
            )
        else:
            field_values = self._collect_values()
            frame = self.generator.generate_frame(
                di_key, field_values,
                src_addr=src_addr, dst_addr=dst_addr,
                dir_flag=dir_flag, prm=prm, add_flag=add_flag
            )

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

    def _generate_gdw_frame(self):
        """生成国网协议帧"""
        if not self._current_afn_fn:
            QMessageBox.warning(self, "警告", "请先选择一个AFN+Fn命令")
            return

        afn, fn = self._current_afn_fn

        # 收集信息域配置
        try:
            seq = int(self.gdw_seq.text().strip()) & 0xFF
            channel = int(self.gdw_channel.text().strip()) & 0x0F
            resp_bytes = int(self.gdw_resp_bytes.text().strip()) & 0xFF
        except ValueError:
            QMessageBox.warning(self, "警告", "信息域配置值格式错误")
            return

        info_config = {
            "dir": self.gdw_dir.currentData(),
            "prm": self.gdw_prm.currentData(),
            "通信方式": self.gdw_comm_type.currentData(),
            "路由标识": self.gdw_route_flag.currentData(),
            "附属节点标识": 0,
            "通信模块标识": self.gdw_comm_module.currentData(),
            "冲突检测": 0,
            "中继级别": self.gdw_relay_level.currentData(),
            "纠错编码标识": 0,
            "信道标识": channel,
            "预计应答字节数": resp_bytes,
            "通信速率": 0,
            "速率单位标识": 0,
            "报文序列号": seq,
        }

        src_addr = self.gdw_src_addr.text().strip()
        dst_addr = self.gdw_dst_addr.text().strip()
        relay_addrs = [edit.text().strip() for edit in self.gdw_relay_inputs]

        try:
            field_values = self._collect_values()
            frame = self.gdw_generator.generate_frame(
                afn, fn, field_values, info_config,
                src_addr=src_addr, dst_addr=dst_addr, relay_addrs=relay_addrs
            )
        except Exception as e:
            QMessageBox.warning(self, "组帧失败", f"生成帧时出错:\n{e}")
            return

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

    def _generate_dlt698_frame(self):
        """生成698.45协议帧"""
        if not self._current_dlt698_key:
            QMessageBox.warning(self, "警告", "请先选择一个APDU命令")
            return

        apdu_type, sub_type = self._current_dlt698_key

        sa = self._get_dlt698_sa()
        ca_text = self.dlt698_ca.text().strip()
        if not sa:
            QMessageBox.warning(self, "警告", "请输入有效的SA地址")
            return
        try:
            ca = int(ca_text, 0) & 0xFF
        except (ValueError, TypeError):
            QMessageBox.warning(self, "警告", "CA地址格式错误")
            return

        dir_bit = self.dlt698_dir.currentData()
        prm_bit = self.dlt698_prm.currentData()
        sc_bit = self.dlt698_sc.currentData()
        seg_bit = self.dlt698_seg.currentData()
        func_code = self.dlt698_func.currentData()

        # A-XDR 模式：使用 A-XDR 数据生成（PIID + OAD/OMD + A-XDR用户数据）
        if self._axdr_mode:
            try:
                axdr_data = self._encode_axdr_data()
                field_values = self._collect_values()
                for name, widget_info in list(self._field_widgets.items()):
                    widget = widget_info.get("widget")
                    if isinstance(widget, QComboBox):
                        val = widget.currentData()
                        if val is not None:
                            field_values[name] = val

                import struct as _struct
                priority = int(field_values.get("PIID_优先级", 0)) & 0x01
                seq = int(field_values.get("PIID_序号", 1)) & 0x7F
                piid = (priority << 7) | seq

                if apdu_type == "_custom_":
                    apdu_bytes = bytes([0x05, 0x01, piid]) + axdr_data
                else:
                    apdu_header = self.dlt698_generator._build_apdu_header(apdu_type, sub_type)
                    apdu_body = _struct.pack("B", piid)

                    oi_widget = self._field_widgets.get("OI", {}).get("widget")
                    oi_text = oi_widget.text().strip().replace(" ", "") if isinstance(oi_widget, QLineEdit) else "0000"
                    try:
                        oi_bytes = bytes.fromhex(oi_text)
                    except ValueError:
                        oi_bytes = b'\x00\x00'
                    oi_bytes = oi_bytes.ljust(2, b'\x00')[:2]

                    if apdu_type in ("GET-Request", "SET-Request", "ACTION-Request"):
                        desc_widget = self._field_widgets.get("描述符类型", {}).get("widget")
                        desc_kind = desc_widget.currentData() if isinstance(desc_widget, QComboBox) else None
                        if desc_kind is None:
                            desc_kind = "OMD" if apdu_type == "ACTION-Request" else "OAD"

                        def _int_edit(name, default):
                            w = self._field_widgets.get(name, {}).get("widget")
                            if isinstance(w, QLineEdit):
                                try:
                                    return int(w.text().strip() or default, 0)
                                except ValueError:
                                    return default
                            return int(field_values.get(name, default))

                        if desc_kind == "OMD":
                            method = _int_edit("方法标识", 1) & 0x1F
                            mode = _int_edit("操作模式", 0) & 0xFF
                            apdu_body += oi_bytes + _struct.pack("B", method) + _struct.pack("B", mode)
                        else:
                            attr = _int_edit("属性标识", 2) & 0x1F
                            idx = _int_edit("索引", 0) & 0xFF
                            apdu_body += oi_bytes + _struct.pack("B", attr) + _struct.pack("B", idx)

                    apdu_body += axdr_data

                    # 请求尾部「没有时间标签」（00=无，同实时预览路径）
                    if apdu_type in ("GET-Request", "SET-Request", "ACTION-Request"):
                        apdu_body += b'\x00'

                    apdu_bytes = apdu_header + apdu_body

                frame = self.dlt698_generator._assemble_frame(
                    sa, ca,
                    self.dlt698_generator.build_control(dir_bit=dir_bit, prm_bit=prm_bit,
                                                          seg_bit=seg_bit, sc_bit=sc_bit, func_code=func_code),
                    apdu_bytes
                )
            except Exception as e:
                QMessageBox.critical(self, "错误", f"A-XDR组帧失败：{str(e)}")
                return
            hex_str = frame.hex().upper()
            self.result_hex.setText(" ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2)))
            return

        field_values = self._collect_values()
        if not self._custom_mode:
            for name, widget_info in list(self._field_widgets.items()):
                widget = widget_info.get("widget")
                if isinstance(widget, QComboBox):
                    val = widget.currentData()
                    if val is not None:
                        field_values[name] = val

        frame = self.dlt698_generator.generate_frame(
            apdu_type, sub_type, field_values,
            sa=sa, ca=ca,
            dir_bit=dir_bit, prm_bit=prm_bit,
            seg_bit=seg_bit, sc_bit=sc_bit,
            func_code=func_code
        )

        hex_str = frame.hex().upper()
        formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        self.result_hex.setText(formatted)

    # ------------------------------------------------------------------
    # 串口功能
    # ------------------------------------------------------------------
    def set_serial_worker(self, worker):
        """设置串口工作线程实例"""
        self.serial_worker = worker
        if worker:
            worker.log_message.connect(self._on_serial_log)
            worker.frame_received.connect(self._on_serial_frame_received)
            worker.connection_changed.connect(self._update_send_button_state)

    def _update_send_button_state(self, connected: bool):
        """根据串口连接状态更新发送按钮"""
        self.send_serial_btn.setEnabled(connected)

    def _on_send_to_serial(self):
        """将当前生成的帧发送到串口"""
        if not self.serial_worker or not self.serial_worker.is_open():
            QMessageBox.warning(self, "警告", "串口未打开，请先打开串口")
            return
        hex_text = self.result_hex.toPlainText().strip()
        if not hex_text:
            QMessageBox.warning(self, "警告", "当前没有可发送的帧，请先生成帧")
            return
        self.serial_worker.send_hex_string(hex_text)

    def _on_add_to_preset_clicked(self):
        """将当前生成的帧添加到预设按钮"""
        frame_hex = self.result_hex.toPlainText().strip()
        if not frame_hex:
            QMessageBox.warning(self, "警告", "当前没有可添加的帧，请先生成帧")
            return

        dialog = AddPresetDialog(frame_hex, self.protocol_mode, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        result = dialog.get_result()
        if not result:
            return

        # 附加当前完整配置快照，方便恢复
        result["config"] = self.get_config_snapshot()

        if PresetButtonManager.add_command(self.protocol_mode, result):
            QMessageBox.information(
                self, "成功",
                f"已添加预设按钮：{result['button_name']}\n分组：{result['group_name']}"
            )
            self.preset_added.emit(self.protocol_mode, frame_hex, result["config"])
        else:
            QMessageBox.critical(self, "错误", "保存预设按钮失败")

    def _on_add_to_test_plan_clicked(self):
        """将当前生成的帧添加到测试方案"""
        frame_hex = self.result_hex.toPlainText().strip()
        if not frame_hex:
            QMessageBox.warning(self, "警告", "当前没有可添加的帧，请先生成帧")
            return
        # 尝试从当前DI/AFN+Fn获取中文名称
        name = ""
        if self.protocol_mode == "south" and self._current_di_key:
            schema = DI_FIELD_SCHEMA.get(self._current_di_key)
            if schema:
                name = schema.get("name", "")
            if not name:
                text = self.di_combo.currentText()
                name = self._extract_name_from_label(text)
        elif self.protocol_mode == "gdw" and self._current_afn_fn:
            text = self.afn_fn_combo.currentText()
            name = self._extract_name_from_label(text)
        elif self.protocol_mode == "dlt698" and self._current_dlt698_key:
            schema = DLT69845_FIELD_SCHEMA.get(self._current_dlt698_key)
            if schema:
                name = schema.get("name", "")
        if not name:
            name = "测试项"
        self.test_plan_added.emit(name, frame_hex.replace(" ", ""))
        QMessageBox.information(self, "成功", f"已添加到测试方案：{name}")

    @staticmethod
    def _extract_name_from_label(label: str) -> str:
        """从combo标签中提取中文名称
        格式: 【下行】 中文名称  (DI3 DI2 DI1 DI0) 或 【下行】 中文名称  (AFN=XXH Fn=FY)
        """
        if not label or label.startswith("--"):
            return ""
        # 去掉 【下行】 前缀
        if label.startswith("【下行】"):
            label = label[4:]
        # 去掉 (DI码) 或 (AFN=... ) 后缀
        if "(" in label:
            label = label[:label.index("(")]
        return label.strip()

    def get_config_snapshot(self) -> Dict[str, Any]:
        """获取当前组帧页面的完整配置快照"""
        snapshot = {
            "protocol_mode": self.protocol_mode,
            "current_di_key": self._current_di_key,
            "current_afn_fn": self._current_afn_fn,
            "custom_mode": self._custom_mode,
            "south": {
                "src_addr": self.src_addr_input.text(),
                "dst_addr": self.dst_addr_input.text(),
                "dir": self.dir_combo.currentData(),
                "prm": self.prm_combo.currentData(),
                "add": self.add_combo.currentData(),
            },
            "gdw": {
                "comm_type": self.gdw_comm_type.currentData(),
                "dir": self.gdw_dir.currentData(),
                "prm": self.gdw_prm.currentData(),
                "seq": self.gdw_seq.text(),
                "route_flag": self.gdw_route_flag.currentData(),
                "comm_module": self.gdw_comm_module.currentData(),
                "relay_level": self.gdw_relay_level.currentData(),
                "channel": self.gdw_channel.text(),
                "resp_bytes": self.gdw_resp_bytes.text(),
                "src_addr": self.gdw_src_addr.text(),
                "dst_addr": self.gdw_dst_addr.text(),
                "relay_addrs": [e.text() for e in self.gdw_relay_inputs],
            },
        }

        # 收集字段值
        try:
            snapshot["field_values"] = self._collect_values()
        except Exception:
            snapshot["field_values"] = {}

        # 自定义模板
        if self._custom_mode:
            self._sync_templates_from_table()
            snapshot["custom_templates"] = [
                {
                    "name": t.name,
                    "length": t.length,
                    "ftype": t.ftype,
                    "endian": t.endian,
                    "display": t.display,
                    "reverse": t.reverse,
                }
                for t in self._custom_templates
            ]
        else:
            snapshot["custom_templates"] = []

        return snapshot

    def apply_config_snapshot(self, config: Dict[str, Any]):
        """从配置快照恢复组帧页面状态"""
        if not config:
            return

        # 恢复协议模式（由外部先调用 set_protocol_mode，这里只校验）
        mode = config.get("protocol_mode", self.protocol_mode)

        # 恢复南网配置
        south = config.get("south", {})
        if "src_addr" in south:
            self.src_addr_input.setText(south["src_addr"])
        if "dst_addr" in south:
            self.dst_addr_input.setText(south["dst_addr"])
        if "dir" in south:
            idx = self.dir_combo.findData(south["dir"])
            if idx >= 0:
                self.dir_combo.setCurrentIndex(idx)
        if "prm" in south:
            idx = self.prm_combo.findData(south["prm"])
            if idx >= 0:
                self.prm_combo.setCurrentIndex(idx)
        if "add" in south:
            idx = self.add_combo.findData(south["add"])
            if idx >= 0:
                self.add_combo.setCurrentIndex(idx)

        # 恢复国网配置
        gdw = config.get("gdw", {})
        if "comm_type" in gdw:
            idx = self.gdw_comm_type.findData(gdw["comm_type"])
            if idx >= 0:
                self.gdw_comm_type.setCurrentIndex(idx)
        if "dir" in gdw:
            idx = self.gdw_dir.findData(gdw["dir"])
            if idx >= 0:
                self.gdw_dir.setCurrentIndex(idx)
        if "prm" in gdw:
            idx = self.gdw_prm.findData(gdw["prm"])
            if idx >= 0:
                self.gdw_prm.setCurrentIndex(idx)
        if "seq" in gdw:
            self.gdw_seq.setText(str(gdw["seq"]))
        if "route_flag" in gdw:
            idx = self.gdw_route_flag.findData(gdw["route_flag"])
            if idx >= 0:
                self.gdw_route_flag.setCurrentIndex(idx)
        if "comm_module" in gdw:
            idx = self.gdw_comm_module.findData(gdw["comm_module"])
            if idx >= 0:
                self.gdw_comm_module.setCurrentIndex(idx)
        if "relay_level" in gdw:
            idx = self.gdw_relay_level.findData(gdw["relay_level"])
            if idx >= 0:
                self.gdw_relay_level.setCurrentIndex(idx)
        if "channel" in gdw:
            self.gdw_channel.setText(str(gdw["channel"]))
        if "resp_bytes" in gdw:
            self.gdw_resp_bytes.setText(str(gdw["resp_bytes"]))
        if "src_addr" in gdw:
            self.gdw_src_addr.setText(gdw["src_addr"])
        if "dst_addr" in gdw:
            self.gdw_dst_addr.setText(gdw["dst_addr"])

        # 恢复中继地址（需等 relay_level 信号触发后再设置）
        relay_addrs = gdw.get("relay_addrs", [])
        if relay_addrs:
            # 用 QTimer 延迟一帧，让 _on_gdw_relay_level_changed 先完成
            def _fill_relay():
                for i, edit in enumerate(self.gdw_relay_inputs):
                    if i < len(relay_addrs):
                        edit.setText(relay_addrs[i])
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, _fill_relay)

        # 恢复命令选择
        di_key = config.get("current_di_key")
        afn_fn = config.get("current_afn_fn")
        if mode == "south" and di_key:
            # di_key 被 JSON 序列化后变成了 list，需要转回 tuple
            if isinstance(di_key, list):
                di_key = tuple(di_key)
            for i in range(self.di_combo.count()):
                data = self.di_combo.itemData(i)
                if data == di_key:
                    self.di_combo.setCurrentIndex(i)
                    break
        elif mode == "gdw" and afn_fn:
            if isinstance(afn_fn, list):
                afn_fn = tuple(afn_fn)
            for i in range(self.afn_fn_combo.count()):
                data = self.afn_fn_combo.itemData(i)
                if data == afn_fn:
                    self.afn_fn_combo.setCurrentIndex(i)
                    break

        # 恢复自定义模板
        custom_templates_data = config.get("custom_templates", [])
        if custom_templates_data:
            self._custom_templates = [
                CustomFieldTemplate(
                    t["name"], t["length"], t["ftype"],
                    t["endian"], t["display"], t["reverse"]
                )
                for t in custom_templates_data
            ]

        # 恢复模式
        custom_mode = config.get("custom_mode", False)
        if custom_mode:
            self.mode_custom_rb.setChecked(True)
            self.mode_predefined_rb.setChecked(False)
            self._custom_mode = True
        else:
            self.mode_predefined_rb.setChecked(True)
            self.mode_custom_rb.setChecked(False)
            self._custom_mode = False

        # 恢复字段值（在表单重建后）
        field_values = config.get("field_values", {})
        if field_values:
            # 延迟一帧，让表单控件已创建
            def _apply_fields():
                for name, widget_info in self._field_widgets.items():
                    if name not in field_values:
                        continue
                    val = field_values[name]
                    widget = widget_info.get("widget")
                    if "sub_widgets" in widget_info:
                        for sub_name, sub_widget in widget_info["sub_widgets"].items():
                            if sub_name in field_values:
                                sv = field_values[sub_name]
                                if isinstance(sub_widget, QComboBox):
                                    idx = sub_widget.findData(sv)
                                    if idx >= 0:
                                        sub_widget.setCurrentIndex(idx)
                                else:
                                    sub_widget.setText(str(sv))
                    elif isinstance(widget, QComboBox):
                        idx = widget.findData(val)
                        if idx >= 0:
                            widget.setCurrentIndex(idx)
                    elif isinstance(widget, QLineEdit):
                        widget.setText(str(val))
                    elif widget is not None and hasattr(widget, '_items'):
                        # list 类型：先清空再添加
                        items = val if isinstance(val, list) else []
                        # 删除现有项
                        while widget._items:
                            row_widget, _ = widget._items.pop()
                            row_widget.deleteLater()
                        for item_values in items:
                            # 触发 add_item（通过点击按钮太复杂，直接重建）
                            pass  # list 类型暂不支持精确恢复
                self._schedule_realtime_update()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, _apply_fields)

    def _on_clear_serial_log(self):
        """清空串口日志"""
        self.serial_log.clear()

    def _on_clear_response_table(self):
        """清空响应帧解析表格"""
        self.response_table.setRowCount(0)

    def _on_serial_log_context_menu(self, pos):
        """串口日志区域右键菜单"""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        clear_action = menu.addAction("清空日志")
        copy_action = menu.addAction("复制选中内容")
        select_all_action = menu.addAction("全选")
        action = menu.exec(self.serial_log.mapToGlobal(pos))
        if action == clear_action:
            self.serial_log.clear()
        elif action == copy_action:
            self.serial_log.copy()
        elif action == select_all_action:
            self.serial_log.selectAll()

    @staticmethod
    def _trim_log(log_widget, max_lines: int = 500):
        """当日志超过max_lines行时，自动删除最早的行"""
        doc = log_widget.document()
        if doc.blockCount() > max_lines:
            cursor = log_widget.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor, doc.blockCount() - max_lines)
            cursor.removeSelectedText()

    def _on_serial_log(self, msg: str):
        """串口日志消息回调"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.serial_log.append(f"[{ts}] {msg}")
        self._trim_log(self.serial_log)
        # 自动滚动到底部
        scrollbar = self.serial_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_serial_frame_received(self, frame: bytes):
        """收到串口帧后的解析与显示"""
        try:
            if self.protocol_mode == "south":
                table_data = self.parser.parse_to_table(frame)
                key_fields = ("应用功能码 (AFN)", "数据标识 (DI)", "传输方向")
            elif self.protocol_mode == "dlt698":
                table_data = self.dlt698_parser.parse_to_table(frame)
                key_fields = ("控制域", "APDU类型", "DIR+PRM")
            elif self.protocol_mode == "dlt645":
                # 协议6 原先落进 else 分支被 gdw_parser 解析 → 收到回包也只显示解析失败
                table_data = self._dlt645_to_table(frame)
                key_fields = ("控制码", "数据标识 DI", "从站地址")
            else:
                table_data = self.gdw_parser.parse_to_table(frame)
                key_fields = ("应用功能码(AFN)", "数据单元标识(DT)", "传输方向")
            self._populate_response_table(table_data)
            summary_parts = []
            for item in table_data:
                field_name = item[0].strip()
                if field_name in key_fields:
                    parsed = str(item[2]) if item[2] else str(item[3])
                    summary_parts.append(f"{field_name}: {parsed}")
            ts = datetime.now().strftime("%H:%M:%S")
            if summary_parts:
                self.serial_log.append(f"[{ts}] [解析] {' | '.join(summary_parts)}")
            else:
                self.serial_log.append(f"[{ts}] [解析] 帧结构识别成功")
        except Exception as e:
            ts = datetime.now().strftime("%H:%M:%S")
            self.serial_log.append(f"[{ts}] [解析失败] {e}")

    def _populate_response_table(self, table_data: list):
        """填充响应帧解析表格"""
        self.response_table.setRowCount(0)
        for row, item in enumerate(table_data):
            field_name = item[0]
            raw_value = item[1]
            parsed_value = item[2]
            comment = item[3]
            self.response_table.insertRow(row)
            self.response_table.setItem(row, 0, QTableWidgetItem(str(field_name)))
            self.response_table.setItem(row, 1, QTableWidgetItem(str(raw_value)))
            self.response_table.setItem(row, 2, QTableWidgetItem(str(parsed_value)))
            self.response_table.setItem(row, 3, QTableWidgetItem(str(comment)))

    @staticmethod
    def _dlt645_to_table(frame: bytes) -> list:
        """DL/T645 解析结果 → 统一 6 元组表格行

        ``DLT645Parser.parse`` 返回 dict，``fields`` 内为 3 元组
        ``(字段, 原始值, 说明)``；LME 自定义接口子字段为 4 元组
        ``(字段, 原始值, 解析值, 说明)``。口径与 ``main_gui`` 深度解析一致
        （见 main_gui.py 的 ``parsed_data.append((field, raw, lme_parsed, desc, 0, 0))``）。
        """
        result = DLT645Parser.parse(frame)
        rows = []
        for item in result.get("fields", []):
            if len(item) == 4:
                field, raw, parsed, desc = item
            else:
                field, raw, desc = item
                parsed = ""
            rows.append((field, raw, parsed, desc, 0, 0))
        return rows

    # ------------------------------------------------------------------
    # 协议模式切换
    # ------------------------------------------------------------------
    def set_protocol_mode(self, mode: str):
        """切换协议模式: 'south'='南网', 'gdw'='国网', 'dlt698'='698.45', 'dlt645'='DLT645-2007'"""
        if mode not in ("south", "gdw", "dlt698", "dlt645"):
            return
        self.protocol_mode = mode

        # 隐藏所有配置面板
        self.di_combo.setVisible(False)
        self.afn_fn_combo.setVisible(False)
        self.dlt698_combo.setVisible(False)
        self.dlt645_combo.setVisible(False)
        self.south_config_group.setVisible(False)
        self.gdw_config_group.setVisible(False)
        self.dlt698_config_group.setVisible(False)
        self.dlt645_config_group.setVisible(False)

        # 切换命令选择区
        if mode == "south":
            self.cmd_select_group.setTitle("DI 选择")
            self.di_combo.setVisible(True)
            self.south_config_group.setVisible(True)
            self.mode_custom_rb.setVisible(True)
        elif mode == "dlt698":
            self.cmd_select_group.setTitle("APDU 选择")
            self.dlt698_combo.setVisible(True)
            self.dlt698_config_group.setVisible(True)
            self.mode_custom_rb.setVisible(False)
            self._custom_mode = False
        elif mode == "dlt645":
            self.cmd_select_group.setTitle("命令选择")
            self.dlt645_combo.setVisible(True)
            self.dlt645_config_group.setVisible(True)
            self.mode_custom_rb.setVisible(False)
            self._custom_mode = False
            self._dlt645_addr_touched = False
        else:  # gdw
            self.cmd_select_group.setTitle("AFN+Fn 选择")
            self.afn_fn_combo.setVisible(True)
            self.gdw_config_group.setVisible(True)

        # EB 数据标识 645/698 生成器仅协议7 显示
        self.eb_gen_group.setVisible(mode == "gdw")
        if mode != "gdw":
            self.reset_eb_generator()

        # 清空当前选择
        self.di_combo.setCurrentIndex(0)
        self.afn_fn_combo.setCurrentIndex(0)
        self.dlt698_combo.setCurrentIndex(0)
        self._current_di_key = None
        self._current_afn_fn = None
        self._current_dlt698_key = None
        self._current_dlt645_key = None
        self._dlt645_field_widgets.clear()
        self.dlt645_verify_label.setText("")
        self.dlt645_warn_label.setText("")
        self._rebuild_form(None)
        self.result_hex.clear()
        self.preview_table.setRowCount(0)

        # dlt645 的命令选择必须在上面「清空当前选择」之后重建：
        # 否则 _current_dlt645_key 会被同步清空，生成时误报「请先选择命令」。
        # 又因首个命令就是下拉第 0 项，setCurrentIndex(0) 不会发信号，故需显式刷新。
        if mode == "dlt645":
            self._reset_dlt645_selection()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def reset(self):
        self.di_combo.setCurrentIndex(0)
        self.afn_fn_combo.setCurrentIndex(0)
        self.dlt698_combo.setCurrentIndex(0)
        self.src_addr_input.setText("000000000000")
        self.dst_addr_input.setText("000000000000")
        self.gdw_src_addr.setText("000000000000")
        self.gdw_dst_addr.setText("000000000000")
        self.dlt698_addr_type.setCurrentIndex(0)
        self.dlt698_logic_addr.setCurrentIndex(0)
        self.dlt698_addr_len.setCurrentText("5")
        self.dlt698_sa_raw.setText("0000000000")
        self.dlt698_ca.setText("0")
        self.dir_combo.setCurrentIndex(0)
        self.prm_combo.setCurrentIndex(0)
        self.add_combo.setCurrentIndex(0)
        self.gdw_dir.setCurrentIndex(0)
        self.gdw_prm.setCurrentIndex(0)
        self.gdw_comm_type.setCurrentIndex(0)
        self.gdw_route_flag.setCurrentIndex(0)
        self.gdw_comm_module.setCurrentIndex(0)
        self.gdw_relay_level.setCurrentIndex(0)
        self.gdw_seq.setText("0")
        self.gdw_channel.setText("0")
        self.gdw_resp_bytes.setText("0")
        self.dlt698_dir.setCurrentIndex(0)
        self.dlt698_prm.setCurrentIndex(0)
        self.dlt698_sc.setCurrentIndex(0)
        self.dlt698_seg.setCurrentIndex(0)
        self.dlt698_func.setCurrentIndex(1)
        self._current_dlt698_key = None
        if hasattr(self, "dlt645_addr"):
            self._dlt645_addr_touched = False
            self.dlt645_broadcast.setChecked(False)
            self._set_dlt645_addr("000000000000")
            self._current_dlt645_key = None
            self.dlt645_verify_label.setText("")
            self.dlt645_warn_label.setText("")
            self._reset_dlt645_selection()
        self.result_hex.clear()
        if hasattr(self, 'preview_table'):
            self.preview_table.setRowCount(0)
        if hasattr(self, 'response_table'):
            self.response_table.setRowCount(0)
        self._custom_templates = []
        self._custom_mode = False
        self.mode_predefined_rb.setChecked(True)
        self.mode_custom_rb.setChecked(False)
        self._rebuild_form(None)
        self.reset_eb_generator()
