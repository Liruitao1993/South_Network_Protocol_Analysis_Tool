import pathlib
"""
南网协议解析工具 - PySide6 GUI版
简洁界面，支持单帧解析和批量解析
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QSplitter, QGroupBox, QDialog, QTabWidget, QComboBox,
    QListView, QFrame, QMenuBar, QSpinBox
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStyle
from PySide6.QtGui import QFont, QTextCursor, QTextCharFormat, QColor, QIcon

from protocol_parser import ProtocolFrameParser
from plc_rf_parser import PLCRFProtocolParser
from hdlc_parser import HDLCParser
from dlt645_parser import DLT645Parser
from gdw10376_parser import GDW10376Parser
from dl_t698_45_parser import DLT69845Parser
from csg_new_gen_parser import CSGNewGenParser
from gw_new_gen_parser import GWNewGenParser
from obis_lookup import OBISLookup, get_obis_lookup
from command_lookup import CommandLookup, get_command_lookup
from dlt645_di_lookup import DLT645DILookup, get_dlt645_di_lookup
from gdw_afn_lookup import GDWAFNLookup, get_gdw_afn_lookup
from frame_gen_widget import FrameGenWidget
from archive_widget import ArchiveWidget
from topology_widget import TopologyWidget
from preset_buttons import PresetButtonWidget
from test_plan_widget import TestPlanWidget
from diff_widget import DiffWidget
from serial_worker import SerialWorker
from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu
from enhanced_export import EnhancedBatchResultExporter


APP_VERSION = "1.8.2"

CHANGELOG = [
    ("1.8.2", "2026-07-06", [
        "新增「报文对比」标签页：双报文字节级/字段级对比分析，支持字段感知对齐",
        "支持差异高亮（修改/新增/删除）、人话解读、忽略校验和/序列号、导出报告",
        "新增 frame_diff_engine.py（对比引擎）和 diff_widget.py（GUI 组件）",
        "新增 TUI 版本：tui_app.py + tui_app.tcss，基于 Textual 框架，支持单帧解析+字节高亮、批量多帧解析+摘要、协议一致性校验",
        "新增 NiceGUI Web 版本（web_app.py + web/）：基于 NiceGUI 框架的浏览器解析器，支持完整 10 种协议解析、单帧/批量/报文对比/组帧/预设/查询/测试计划/档案/拓扑等标签页，集成串口通信，暗色主题，健康检查端点 /health",
        "新增 enhanced_export.py：Excel 增强导出（协议元数据、字节高亮样式、分 Sheet 导出），CSV/TXT/JSON 多格式导出",
    ]),
    ("1.8.1", "2026-06-27", [
        "测试方案新增 Lua 脚本支持：可在测试流程中嵌入可编程逻辑，支持条件分支、循环遍历、数据解析、变量共享",
        "新增 lua_script_engine.py（Lua 脚本引擎），提供 send/wait/log/hex_to_bytes 等 API 函数",
        "依赖：lupa（Python-Lua 桥接，pip install lupa）",
    ]),
    ("1.8.0", "2026-07-04", [
        "新增 DLMS-APDU(国网) 协议选项（索引3），使用 HDLC 解析器的 APDU 深度解析功能",
        "HDLC/DLMS 协议重命名为 HDLC/国网DLMS，明确国网协议背景",
        "协议索引重新编号：原 3~8 顺延为 4~9，共 10 种协议",
    ]),
    ("1.7.2", "2026-06-21", [
        "修复新一代载波协议（索引8）选择确认帧(SACK)解析：字节12正确解析为扩展帧类型+标准版本号",
        "SACK子解析器返回值修正，与其他帧类型子解析器保持一致",
    ]),
    ("1.7.1", "2026-06-18", [
        "新一代载波协议（索引8）批量解析：新增监控日志前缀剥离，支持 '<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>' 格式",
        "新一代载波协议批量解析摘要：区分网络层/应用层报文，展示 MSDU 类型、MMTYPE、定界符类型、业务标识等关键业务内容",
        "修复：过滤掉非监控前缀且非纯 hex 的日志行（如时间戳、测试标记、中文说明），避免被误解析为伪帧",
    ]),
    ("1.7.0", "2026-06-18", [
        "新增 DL/T 698.45-2017 协议（协议索引7）支持：链路层解析器、APDU 解析器、A-XDR 编解码、OI 查询、帧生成器、校验器",
        "新增 新一代载波协议（通感一体化，协议索引8）支持：MAC/MSDU 帧解析、应用层业务报文解析、命令载荷解析、校验器",
        "新一代载波协议支持 4 种解析级别切换：自动识别 / FC+PB 完整 MPDU / 仅 FC / 应用层报文",
        "新增新一代载波协议业务标识查询页面",
        "组帧/预设标签页扩展支持 698.45 协议（dlt698 模式）",
        "校验引擎统一接入 DLT69845Validator 与 CSGNewGenValidator",
        "新增 crcmod 依赖（698.45 CRC 使用 X-25 / CRC16）",
    ]),
    ("1.6.8", "2026-05-09", [
        "档案管理：修复缺失 json 导入导致导出失败的问题",
        "档案管理：修复协议切换时错误清空档案数据的问题",
        "拓扑信息：新增组网完成时间统计功能（自动刷新模式）",
    ]),
    ("1.6.7", "2026-04-30", [
        "修复南网协议DI字节序解析（恢复小端序，修复DI查找匹配）",
        "修复查询运行参数信息(E8 03 03 74)数据内容解析器IndexError",
        "修复国网验证器长度域校验逻辑（长度域值即帧总长度）",
        "南网/国网控制域位域显示二进制位值（D7~D0）",
        "国网信息域位域显示二进制位值（D0~D7）",
    ]),
    ("1.6.6", "2026-04-30", [
        "修复DI解析字节序问题，恢复小端序正确匹配DI_COMBINATION_MAP",
    ]),
    ("1.6.5", "2026-04-22", [
        "系统性修复字节序解析：所有多字节字段按小端序（低字节在前）解析",
        "修复ASCII字段反转：厂商代码/芯片代码等2字节ASCII正确反转显示",
        "修复BCD字段反转：版本时间/版本日期/版本号等按传输顺序反转后解析",
        "修复所有int.from_bytes大端序为小端序，符合协议低字节在前规范",
        "修复组帧引擎默认字节序为小端序，确保发送帧字节序正确",
        "修复_bcd_to_str支持非标准BCD十六进制（如0xC0显示为C0）",
    ]),
    ("1.6.4", "2026-04-22", [
        "修复BCD日期解析：版本时间/版本日期/协议发布日期按BCD码原值显示",
        "修复BCD版本号解析：多字节BCD字段按小端序反转后显示",
        "修复批量查询厂商信息中的BCD日期和版本号解析",
    ]),
    ("1.6.3", "2026-04-22", [
        "添加任务字段优化：任务模式字拆分为响应标识/转发标识/优先级下拉选择",
        "添加任务字段优化：报文内容拆分为业务代码（下拉）+报文有效内容（输入）",
        "添加任务支持条件字段：业务代码仅在转发标识=1时自动打包进报文",
        "引擎支持sub_fields位域合并和条件子字段打包",
        "添加多播任务同样支持任务模式字位域拆分",
    ]),
    ("1.6.2", "2026-04-22", [
        "修正字段定义：移除多余字段（启动/暂停任务、查询白名单生效信息）",
        "修正字段定义：补充缺失字段（重启节点等待时长、台区识别保留字节等）",
        "修正字段定义：修复字段名与文档不匹配问题（无线参数、台区识别等）",
        "修正字段定义：为15个查询命令补充下行参数字段",
        "修正字段定义：统一多字节数值字段为小端序",
    ]),
    ("1.6.1", "2026-04-22", [
        "协议组帧功能完善：支持88个下行DI命令",
        "命令说明弹窗支持非模态显示，可同时编辑主窗口",
        "字段模板表格和按钮布局优化，纵向空间更紧凑",
        "命令说明内容来源于PLUZ计量自动化系统技术规范文档",
        "串口通信支持配置、发送、日志和接收帧解析",
    ]),
    ("1.6.0", "2026-04-21", [
        "新增国网协议(Q/GDW 10376.2-2024)解析支持",
        "支持国网协议AFN+Fn组合查询功能",
        "国网协议支持单帧解析、批量解析、字节高亮",
        "支持国网协议控制域、信息域、地址域、应用数据域完整解析",
    ]),
    ("1.5.0", "2026-04-17", [
        "重构主界面代码，精简655行GUI代码，优化协议解析工具结构",
        "增强南网协议解析器，扩展控制域与用户数据区解析能力",
        "优化PyInstaller构建配置，提升打包稳定性与兼容性",
    ]),
    ("1.4.0", "2026-04-16", [
        "修复表格交替行颜色失效的问题（stylesheet优化）",
        "新增AGENTS.md项目指南文件，便于AI辅助开发",
        "PyInstaller打包配置修复：添加custom_di.json和dlt645_di.json到datas",
    ]),
    ("1.3.0", "2026-04-16", [
        "修复查询页面切换时按钮残留问题（递归清理layout）",
        "修复命令字查询页缺失的4个方法（_load_command_map_data等）",
        "修复命令字表格\"十六进制\"列显示十进制的bug，简化为2列",
        "新增菜单栏与\"关于\"对话框",
    ]),
    ("1.2.0", "2026-04-16", [
        "优化HDLC解析器，修复APDU数据解析中的索引错误",
        "新增Wrapper帧提取功能",
    ]),
    ("1.1.0", "2026-04-15", [
        "优化HDLC解析器，增强对返回数据和未知响应类型的处理",
        "更新主界面，改善协议选择和输入提示",
    ]),
    ("1.0.1", "2026-04-15", [
        "新增README文档",
        "更新编译后的二进制文件",
    ]),
    ("1.0.0", "2026-04-14", [
        "初始版本发布",
        "支持南网协议/PLC RF/HDLC/DLMS多协议解析",
        "单帧解析与批量解析功能",
        "DI/命令字/OBIS查询功能",
    ]),
]


def _get_git_changelog() -> list:
    """从git日志获取变更记录，用于动态追加到CHANGELOG"""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ai | %s", "-30"],
            capture_output=True, timeout=5,
            cwd=str(Path(__file__).parent),
        )
        if result.returncode != 0:
            return []
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                output = result.stdout.decode(enc)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            output = result.stdout.decode("utf-8", errors="replace")
        entries = []
        for line in output.strip().splitlines():
            if " | " in line:
                date_msg = line.split(" | ", 1)
                date = date_msg[0][:10]
                msg = date_msg[1]
                entries.append((date, msg))
        return entries
    except Exception:
        return []


# 配置文件路径标签映射
FILE_PATH_LABELS = {
    "nw_command": "南网预设命令",
    "gw_command": "国网预设命令",
    "test_plan": "测试方案",
    "custom_di": "南网自定义DI",
    "dlt645_di": "DLT645 DI映射",
    "gdw_custom_afn": "国网自定义AFN",
    "command": "PLC RF命令字",
}


class ConfigDialog(QDialog):
    """配置文件路径管理对话框"""

    def __init__(self, file_paths: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置管理")
        self.setMinimumWidth(650)
        self._file_paths = dict(file_paths)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        desc = QLabel("管理各配置文件的存储路径。支持相对路径（相对于程序目录）或绝对路径。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)

        # 表格布局：每行 = 标签 + 路径输入 + 浏览按钮
        self._inputs: Dict[str, QLineEdit] = {}
        for key, label in FILE_PATH_LABELS.items():
            row = QHBoxLayout()
            row.setSpacing(8)

            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(110)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)

            edit = QLineEdit()
            edit.setText(self._file_paths.get(key, ""))
            edit.setPlaceholderText(f"默认: {key}.json")
            self._inputs[key] = edit
            row.addWidget(edit, 1)

            btn = QPushButton("浏览...")
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda checked=False, k=key, e=edit: self._browse_file(k, e))
            row.addWidget(btn)

            layout.addLayout(row)

        layout.addStretch()

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "border-radius: 4px; padding: 5px 18px; font-weight: bold; }"
        )
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _browse_file(self, key: str, edit: QLineEdit):
        """弹出文件选择对话框"""
        current = edit.text().strip()
        start_dir = str(Path(__file__).parent)
        if current:
            p = Path(current)
            if not p.is_absolute():
                p = Path(__file__).parent / p
            if p.parent.exists():
                start_dir = str(p.parent)

        path, _ = QFileDialog.getOpenFileName(
            self, f"选择 {FILE_PATH_LABELS.get(key, key)}", start_dir, "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if path:
            # 尽量保存为相对路径
            try:
                rel = Path(path).relative_to(Path(__file__).parent)
                edit.setText(str(rel))
            except ValueError:
                edit.setText(path)

    def _on_save(self):
        """保存按钮点击"""
        for key, edit in self._inputs.items():
            val = edit.text().strip()
            if val:
                self._file_paths[key] = val
            elif key in self._file_paths:
                del self._file_paths[key]
        self.accept()

    def get_file_paths(self) -> Dict[str, str]:
        return self._file_paths


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"协议解析工具 v{APP_VERSION}")
        self.setMinimumSize(1000, 700)

        # 协议选择：0=南网协议，1=PLC RF协议，2=HDLC/国网DLMS，3=DLMS-APDU(国网)，4=Wrapper，5=APDU，6=DLT645，7=国网协议，8=698.45，9=新一代载波协议(通感一体化)
        self.current_protocol = 0

        # 初始化解析器
        self.parser = ProtocolFrameParser()
        self.plc_rf_parser = PLCRFProtocolParser()
        self.hdlc_parser = HDLCParser()
        self.dlt645_parser = DLT645Parser()
        self.gdw_parser = GDW10376Parser()
        self.dl_t698_45_parser = DLT69845Parser()
        self.csg_new_gen_parser = CSGNewGenParser()
        self.gw_new_gen_parser = GWNewGenParser()

        # 新一代载波协议解析级别：auto=自动, fc_pb=FC+PB, fc_only=仅FC, app=应用层
        self._csg_parse_level = "auto"
        # 字节剔除缓存：记录上次剔除后成功解析的hex，避免重复剔除
        self._csg_last_stripped_hex = ""

        # 国网新一代解析级别：auto=自动, fc_only=仅FC, fc_mac=FC+MAC, app=应用层
        self._gw_parse_level = "auto"

        # 初始化查询器
        self.obis_lookup = get_obis_lookup()
        self.command_lookup = get_command_lookup()
        self.gdw_afn_lookup = get_gdw_afn_lookup()

        # 批量解析结果缓存
        self.batch_results: List[Dict[str, Any]] = []

        # 字节高亮映射
        self._byte_ranges: list = []

        # 上次单帧解析的 hex（供报文对比载入）
        self._last_parsed_hex: Optional[str] = None

        # 应用配置（先加载，setup_ui 会用到）
        self._config_path = Path(__file__).parent / "config.json"
        self._app_config: Dict[str, Any] = {}
        self._file_paths: Dict[str, Path] = {}
        self._load_app_config()

        self.setup_ui()
        self._setup_menu_bar()
        self.apply_styles()

    def setup_ui(self):
        """设置UI布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ========== 顶部栏：协议选择 + 串口配置 ==========
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        # ---- 协议选择分组 ----
        proto_group = QGroupBox("协议选择")
        proto_layout = QHBoxLayout(proto_group)
        proto_layout.setContentsMargins(8, 4, 8, 4)
        proto_layout.setSpacing(6)

        proto_label = QLabel("当前协议：")
        proto_label.setFont(QFont("", 10, QFont.Bold))
        proto_label.setFixedWidth(65)
        proto_layout.addWidget(proto_label)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("南网协议 (Q/CSG1209021-2019)")
        self.protocol_combo.addItem("PLC RF协议 (万胜海外 V1_04)")
        self.protocol_combo.addItem("HDLC/国网DLMS (IEC 62056-46)")
        self.protocol_combo.addItem("DLMS-APDU(国网)")
        self.protocol_combo.addItem("DLMS Wrapper裸报文")
        self.protocol_combo.addItem("DLMS-APDU裸报文")
        self.protocol_combo.addItem("DLT645-2007 电表协议")
        self.protocol_combo.addItem("国网协议 (Q/GDW 10376.2-2024)")
        self.protocol_combo.addItem("698.45协议 (DL/T 698.45-2017)")
        self.protocol_combo.addItem("新一代载波协议 (通感一体化)")
        self.protocol_combo.addItem("国网新一代双模通信互联互通")
        self.protocol_combo.setMinimumWidth(280)
        self.protocol_combo.setFont(QFont("Microsoft YaHei", 10))
        # 让弹出菜单宽度自动适应最宽的文字
        self.protocol_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.protocol_combo.currentIndexChanged.connect(self._on_protocol_changed)
        proto_layout.addWidget(self.protocol_combo)

        # ---- 新一代载波协议解析级别选择（仅协议索引9时可见）----
        self.csg_parse_level_label = QLabel("解析级别：")
        self.csg_parse_level_label.setFont(QFont("Microsoft YaHei", 9))
        proto_layout.addWidget(self.csg_parse_level_label)

        self.csg_parse_level_combo = QComboBox()
        self.csg_parse_level_combo.addItem("自动识别", "auto")
        self.csg_parse_level_combo.addItem("FC+PB解析(完整MPDU)", "fc_pb")
        self.csg_parse_level_combo.addItem("FC+eFC解析", "fc_efc")
        self.csg_parse_level_combo.addItem("仅FC解析", "fc_only")
        self.csg_parse_level_combo.addItem("应用层报文", "app")
        self.csg_parse_level_combo.setFont(QFont("Microsoft YaHei", 9))
        self.csg_parse_level_combo.setMinimumWidth(180)
        self.csg_parse_level_combo.currentIndexChanged.connect(self._on_csg_parse_level_changed)
        self.csg_parse_level_combo.setVisible(False)
        proto_layout.addWidget(self.csg_parse_level_combo)
        self.csg_parse_level_label.setVisible(False)

        # ---- 新一代载波协议字节剔除（仅协议索引9时可见）----
        self.csg_strip_head_label = QLabel("剔除前:")
        self.csg_strip_head_label.setFont(QFont("Microsoft YaHei", 9))
        self.csg_strip_head_label.setVisible(False)
        proto_layout.addWidget(self.csg_strip_head_label)

        self.csg_strip_head_spin = QSpinBox()
        self.csg_strip_head_spin.setRange(0, 999)
        self.csg_strip_head_spin.setValue(0)
        self.csg_strip_head_spin.setSuffix(" 字节")
        self.csg_strip_head_spin.setFont(QFont("Microsoft YaHei", 9))
        self.csg_strip_head_spin.setVisible(False)
        self.csg_strip_head_spin.setToolTip("解析前剔除报文头部指定字节数（0=不剔除）")
        proto_layout.addWidget(self.csg_strip_head_spin)

        self.csg_strip_tail_label = QLabel("尾部:")
        self.csg_strip_tail_label.setFont(QFont("Microsoft YaHei", 9))
        self.csg_strip_tail_label.setVisible(False)
        proto_layout.addWidget(self.csg_strip_tail_label)

        self.csg_strip_tail_spin = QSpinBox()
        self.csg_strip_tail_spin.setRange(0, 999)
        self.csg_strip_tail_spin.setValue(0)
        self.csg_strip_tail_spin.setSuffix(" 字节")
        self.csg_strip_tail_spin.setFont(QFont("Microsoft YaHei", 9))
        self.csg_strip_tail_spin.setVisible(False)
        self.csg_strip_tail_spin.setToolTip("解析前剔除报文尾部指定字节数（0=不剔除）")
        proto_layout.addWidget(self.csg_strip_tail_spin)

        # ---- 国网新一代解析级别选择（仅协议索引10时可见）----
        self.gw_parse_level_label = QLabel("解析级别：")
        self.gw_parse_level_label.setFont(QFont("Microsoft YaHei", 9))
        self.gw_parse_level_label.setVisible(False)
        proto_layout.addWidget(self.gw_parse_level_label)

        self.gw_parse_level_combo = QComboBox()
        self.gw_parse_level_combo.addItem("自动识别", "auto")
        self.gw_parse_level_combo.addItem("仅FC解析", "fc_only")
        self.gw_parse_level_combo.addItem("FC+MAC解析", "fc_mac")
        self.gw_parse_level_combo.addItem("应用层报文", "app")
        self.gw_parse_level_combo.setFont(QFont("Microsoft YaHei", 9))
        self.gw_parse_level_combo.setMinimumWidth(150)
        self.gw_parse_level_combo.currentIndexChanged.connect(self._on_gw_parse_level_changed)
        self.gw_parse_level_combo.setVisible(False)
        proto_layout.addWidget(self.gw_parse_level_combo)

        proto_layout.addStretch()

        top_bar.addWidget(proto_group, 1)

        # ---- 串口配置分组 ----
        serial_group = QGroupBox("串口配置")
        serial_layout = QHBoxLayout(serial_group)
        serial_layout.setContentsMargins(8, 4, 8, 4)
        serial_layout.setSpacing(6)

        serial_layout.addWidget(QLabel("端口:"))
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setMinimumWidth(80)
        serial_layout.addWidget(self.serial_port_combo)

        self.serial_refresh_btn = QPushButton()
        _icon_dir = pathlib.Path(__file__).parent / "icons"
        self.serial_refresh_btn.setIcon(QIcon(str(_icon_dir / "refresh.svg")))
        self.serial_refresh_btn.setToolTip("刷新串口列表")
        self.serial_refresh_btn.setMaximumWidth(30)
        self.serial_refresh_btn.setMinimumHeight(24)
        self.serial_refresh_btn.setFlat(True)
        self.serial_refresh_btn.setStyleSheet("QPushButton { background: transparent; border: none; padding: 2px; }"
            "QPushButton:hover { background: rgba(0,0,0,20); border-radius: 3px; }"
            "QPushButton:pressed { background: rgba(0,0,0,40); }")
        from PySide6.QtCore import QSize
        self.serial_refresh_btn.setIconSize(QSize(18, 18))
        self.serial_refresh_btn.clicked.connect(self._refresh_serial_ports)
        serial_layout.addWidget(self.serial_refresh_btn)

        serial_layout.addWidget(QLabel("波特率:"))
        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.addItems(["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"])
        self.serial_baud_combo.setCurrentText("9600")
        self.serial_baud_combo.setMinimumWidth(80)
        serial_layout.addWidget(self.serial_baud_combo)

        serial_layout.addWidget(QLabel("校验:"))
        self.serial_parity_combo = QComboBox()
        self.serial_parity_combo.addItems(["无", "偶", "奇"])
        self.serial_parity_combo.setMinimumWidth(60)
        serial_layout.addWidget(self.serial_parity_combo)

        self.serial_open_btn = QPushButton("打开串口")
        self.serial_open_btn.setMinimumHeight(28)
        self.serial_open_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.serial_open_btn.clicked.connect(self._on_serial_open_clicked)
        serial_layout.addWidget(self.serial_open_btn)

        self.serial_status_label = QLabel("未连接")
        self.serial_status_label.setStyleSheet("color: #999; font-size: 12px;")
        serial_layout.addWidget(self.serial_status_label)

        serial_layout.addStretch()
        top_bar.addWidget(serial_group)

        main_layout.addLayout(top_bar)

        # ========== 串口工作线程 ==========
        self.serial_worker = SerialWorker()
        self.serial_worker.connection_changed.connect(self._on_serial_connection_changed)
        self.serial_worker.error_occurred.connect(self._on_serial_error)
        self._refresh_serial_ports()
        self._load_serial_config()

        # 选项卡
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_single_parse_tab(), "单帧解析")
        # 查询页面根据协议动态创建
        self.protocol_lookup_tab = QWidget()
        self.protocol_lookup_tab_layout = QVBoxLayout(self.protocol_lookup_tab)
        self.tab_widget.addTab(self.protocol_lookup_tab, "查询")
        self.tab_widget.addTab(self.create_batch_parse_tab(), "批量解析")
        # 协议组帧页面（南网和国网协议支持）
        self.frame_gen_tab = FrameGenWidget()
        self.frame_gen_tab.set_serial_worker(self.serial_worker)
        self._frame_gen_tab_index = self.tab_widget.addTab(self.frame_gen_tab, "协议组帧")
        # 预设命令页面（传入配置文件路径）
        self.preset_tab = PresetButtonWidget(
            nw_path=self._file_paths.get("nw_command"),
            gw_path=self._file_paths.get("gw_command"),
        )
        self.preset_tab.set_serial_worker(self.serial_worker)
        self._preset_tab_index = self.tab_widget.addTab(self.preset_tab, "预设命令")
        self.preset_tab.button_clicked.connect(self._on_preset_button_clicked)
        self.frame_gen_tab.preset_added.connect(self.preset_tab.refresh)
        # 测试方案页面（传入配置文件路径）
        self.test_plan_tab = TestPlanWidget(
            file_path=self._file_paths.get("test_plan"),
        )
        self.test_plan_tab.set_serial_worker(self.serial_worker)
        self._test_plan_tab_index = self.tab_widget.addTab(self.test_plan_tab, "测试方案")
        self.frame_gen_tab.test_plan_added.connect(self.test_plan_tab.add_item)
        # 档案管理页面（南网和国网协议支持）
        self.archive_tab = ArchiveWidget()
        self.archive_tab.set_serial_worker(self.serial_worker)
        self._archive_tab_index = self.tab_widget.addTab(self.archive_tab, "档案管理")

        # 拓扑信息页面（南网和国网协议支持）
        self.topology_tab = TopologyWidget()
        self.topology_tab.set_serial_worker(self.serial_worker)
        self._topology_tab_index = self.tab_widget.addTab(self.topology_tab, "拓扑信息")

        # 报文对比页面
        self.diff_tab = DiffWidget()
        self._diff_tab_index = self.tab_widget.addTab(self.diff_tab, "报文对比")

        main_layout.addWidget(self.tab_widget, 1)

        # 初始化查询页面内容
        self._update_protocol_lookup_tab()

        # 统一设置中文右键菜单（在标签页创建完成后应用）
        self._apply_chinese_menus_to_all_tabs()

    def create_single_parse_tab(self) -> QWidget:
        """创建单帧解析标签页 - 上下布局"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # === 上方：输入区 ===
        input_group = QGroupBox("输入报文")
        input_layout = QVBoxLayout(input_group)

        self.single_input = QTextEdit()
        self.single_input.setPlaceholderText("请输入十六进制报文，支持空格、逗号、换行等分隔符，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
        self.single_input.setMaximumHeight(80)
        input_layout.addWidget(self.single_input)

        # 按钮行
        btn_layout = QHBoxLayout()
        self.parse_btn = QPushButton("解析报文")
        self.parse_btn.setMinimumHeight(32)
        self.parse_btn.clicked.connect(self.parse_single)
        btn_layout.addWidget(self.parse_btn)

        self.verify_btn = QPushButton("校验报文")
        self.verify_btn.setMinimumHeight(32)
        self.verify_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border-radius: 3px; padding: 4px 12px; }"
        )
        self.verify_btn.clicked.connect(self.verify_single)
        btn_layout.addWidget(self.verify_btn)

        self.add_to_test_btn = QPushButton("添加到测试方案")
        self.add_to_test_btn.setMinimumHeight(32)
        self.add_to_test_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 12px; }"
        )
        self.add_to_test_btn.clicked.connect(self._add_parsed_to_test_plan)
        btn_layout.addWidget(self.add_to_test_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setMinimumHeight(32)
        clear_btn.clicked.connect(self.clear_single)
        btn_layout.addWidget(clear_btn)

        # CRC 填充按钮
        self.fill_crc24_btn = QPushButton("填充CRC-24")
        self.fill_crc24_btn.setMinimumHeight(32)
        self.fill_crc24_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; border-radius: 3px; padding: 4px 12px; }"
        )
        self.fill_crc24_btn.clicked.connect(self._fill_crc24)
        btn_layout.addWidget(self.fill_crc24_btn)

        self.fill_crc32_btn = QPushButton("填充CRC-32")
        self.fill_crc32_btn.setMinimumHeight(32)
        self.fill_crc32_btn.setStyleSheet(
            "QPushButton { background-color: #9C27B0; color: white; border-radius: 3px; padding: 4px 12px; }"
        )
        self.fill_crc32_btn.clicked.connect(self._fill_crc32)
        btn_layout.addWidget(self.fill_crc32_btn)

        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)

        layout.addWidget(input_group)

        # === 下方：解析结果表格 ===
        result_group = QGroupBox("解析结果")
        result_layout = QVBoxLayout(result_group)

        self.result_table_widget = QTableWidget()
        self.result_table_widget.setColumnCount(4)
        self.result_table_widget.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        # 允许用户拖拽调整列宽
        header = self.result_table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # 设置默认列宽
        self.result_table_widget.setColumnWidth(0, 130)
        self.result_table_widget.setColumnWidth(1, 100)
        self.result_table_widget.setColumnWidth(2, 100)
        self.result_table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table_widget.setAlternatingRowColors(True)
        self.result_table_widget.verticalHeader().hide()
        self.result_table_widget.verticalHeader().setDefaultSectionSize(13)
        table_font = QFont()
        table_font.setPointSize(7)
        self.result_table_widget.setFont(table_font)
        # 行高更紧凑
        self.result_table_widget.verticalHeader().setDefaultSectionSize(10)
        self.result_table_widget.verticalHeader().hide()

        # 选中行时高亮报文字节
        self.result_table_widget.currentCellChanged.connect(self._highlight_bytes)
        # 双击行时，提取该区域字节作为DLMS-APDU重新解析
        self.result_table_widget.doubleClicked.connect(self._extract_apdu_reparse)
        # 存储每行对应的字节范围
        self._byte_ranges: list = []

        # 导出图片按钮行
        export_row = QHBoxLayout()
        export_row.addStretch()
        self.export_result_btn = QPushButton("导出图片")
        self.export_result_btn.setToolTip("将解析结果表格导出为完整的PNG图片")
        self.export_result_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border-radius: 3px; padding: 3px 12px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        self.export_result_btn.clicked.connect(self._export_result_image)
        export_row.addWidget(self.export_result_btn)
        result_layout.addLayout(export_row)

        result_layout.addWidget(self.result_table_widget)

        # === 校验结果区域 ===
        self.verify_group = QGroupBox("校验结果")
        verify_layout = QVBoxLayout(self.verify_group)
        self.verify_label = QLabel("点击「校验报文」按钮进行协议一致性校验")
        self.verify_label.setWordWrap(True)
        self.verify_label.setFont(QFont("Consolas", 9))
        verify_layout.addWidget(self.verify_label)
        result_layout.addWidget(self.verify_group)

        layout.addWidget(result_group, 1)

        return tab

    def _export_result_image(self):
        """将解析结果表格导出为完整的PNG图片"""
        table = self.result_table_widget
        if table.rowCount() == 0:
            QMessageBox.warning(self, "提示", "当前没有解析结果可以导出！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出解析结果图片",
            f"解析结果_{self.current_protocol}.png",
            "PNG 图片 (*.png)"
        )
        if not file_path:
            return

        from PySide6.QtCore import QSize
        from PySide6.QtGui import QPixmap, QPainter

        # 保存当前状态
        orig_h = table.height()
        orig_min_h = table.minimumHeight()
        orig_max_h = table.maximumHeight()
        orig_vscroll_policy = table.verticalScrollBarPolicy()

        # 计算完整高度：表头 + 所有行 + 边距
        header_h = table.horizontalHeader().height()
        total_row_h = sum(table.rowHeight(i) for i in range(table.rowCount()))
        full_h = header_h + total_row_h + 10
        full_w = table.viewport().width() + 2  # 略宽于可视区

        try:
            # 临时调整表格尺寸以显示全部行
            table.setMinimumHeight(full_h)
            table.setMaximumHeight(full_h)
            table.verticalScrollBar().setVisible(False)
            table.adjustSize()
            QApplication.processEvents()

            # 使用 grab() 截取完整表格
            pixmap = table.grab()

            pixmap.save(file_path, "PNG")
            QMessageBox.information(self, "导出成功",
                f"解析结果已导出为图片：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出图片时出错：{str(e)}")
        finally:
            # 恢复原始状态
            table.setMinimumHeight(orig_min_h)
            table.setMaximumHeight(orig_max_h)
            table.verticalScrollBar().setVisible(orig_vscroll_policy != Qt.ScrollBarAlwaysOff)
            table.resize(table.width(), orig_h)

    def create_di_lookup_tab(self) -> QWidget:
        """创建DI查询标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.di_search_input = QLineEdit()
        self.di_search_input.setPlaceholderText("输入DI编码(如E8020201)或中文关键词(如添加任务)搜索...")
        self.di_search_input.setClearButtonEnabled(True)
        self.di_search_input.textChanged.connect(self._filter_di_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.di_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.di_stats_label = QLabel()
        self.di_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.di_stats_label)

        # 表格
        self.di_table = QTableWidget()
        self.di_table.setColumnCount(6)
        self.di_table.setHorizontalHeaderLabels(["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义"])
        header = self.di_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.di_table.setColumnWidth(0, 60)
        self.di_table.setColumnWidth(1, 60)
        self.di_table.setColumnWidth(2, 60)
        self.di_table.setColumnWidth(3, 60)
        self.di_table.setColumnWidth(4, 200)
        self.di_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.di_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.di_table.setAlternatingRowColors(True)
        self.di_table.verticalHeader().hide()
        self.di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        self.di_table.setFont(table_font)
        layout.addWidget(self.di_table)

        # 按钮栏
        btn_layout = QHBoxLayout()
        add_di_btn = QPushButton("添加自定义DI")
        add_di_btn.clicked.connect(self._add_custom_di)
        btn_layout.addWidget(add_di_btn)

        del_di_btn = QPushButton("删除选中自定义DI")
        del_di_btn.clicked.connect(self._del_custom_di)
        btn_layout.addWidget(del_di_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_di_map_data()

        return tab

    def _load_di_map_data(self):
        """从解析器加载DI组合MAP数据到表格（含自定义标记）"""
        self._di_data = []
        di_map = self.parser.DI_COMBINATION_MAP
        afn_map = self.parser.AFN_MAP
        custom_list = ProtocolFrameParser.load_custom_di_list()
        custom_keys = {(e["di3"], e["di2"], e["di1"], e["di0"]) for e in custom_list}

        for (di3, di2, di1, di0), desc in di_map.items():
            afn_val = di1
            afn_name = afn_map.get(afn_val, f"未知({afn_val:02X})")
            is_custom = (di3, di2, di1, di0) in custom_keys
            self._di_data.append((di3, di2, di1, di0, afn_val, afn_name, desc, is_custom))

        self.di_table.setRowCount(len(self._di_data))
        for row, (di3, di2, di1, di0, afn_val, afn_name, desc, is_custom) in enumerate(self._di_data):
            self.di_table.setItem(row, 0, QTableWidgetItem(f"{di3:02X}"))
            self.di_table.setItem(row, 1, QTableWidgetItem(f"{di2:02X}"))
            self.di_table.setItem(row, 2, QTableWidgetItem(f"{di1:02X}"))
            self.di_table.setItem(row, 3, QTableWidgetItem(f"{di0:02X}"))
            self.di_table.setItem(row, 4, QTableWidgetItem(f"{afn_val:02X}H {afn_name}"))
            desc_item = QTableWidgetItem(("★ " if is_custom else "") + desc)
            if is_custom:
                desc_item.setForeground(QColor("#1976D2"))
            self.di_table.setItem(row, 5, desc_item)

        self.di_stats_label.setText(f"共 {len(self._di_data)} 条记录（其中自定义 {len(custom_keys)} 条）")

    def _filter_di_table(self, text: str):
        """根据搜索文本过滤DI表格"""
        keyword = text.strip().upper()
        match_count = 0

        for row in range(self.di_table.rowCount()):
            if not keyword:
                self.di_table.setRowHidden(row, False)
                match_count += 1
                continue

            # 构建该行的搜索文本：DI拼接 + AFN + 中文含义
            di3 = self.di_table.item(row, 0).text()
            di2 = self.di_table.item(row, 1).text()
            di1 = self.di_table.item(row, 2).text()
            di0 = self.di_table.item(row, 3).text()
            afn_text = self.di_table.item(row, 4).text()
            desc_text = self.di_table.item(row, 5).text()

            di_str = f"{di3}{di2}{di1}{di0}"
            di_spaced = f"{di3} {di2} {di1} {di0}"
            search_text = f"{di_str} {di_spaced} {afn_text} {desc_text}".upper()

            if keyword in search_text:
                self.di_table.setRowHidden(row, False)
                match_count += 1
            else:
                self.di_table.setRowHidden(row, True)

        if keyword:
            self.di_stats_label.setText(f"匹配 {match_count} / {self.di_table.rowCount()} 条记录")
        else:
            self.di_stats_label.setText(f"共 {self.di_table.rowCount()} 条记录")

    def _add_custom_di(self):
        """添加自定义DI对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义DI")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)

        # DI3
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("DI3:"))
        di3_input = QLineEdit()
        di3_input.setPlaceholderText("如 E8 或 EA")
        di3_input.setMaxLength(2)
        h1.addWidget(di3_input)
        layout.addLayout(h1)

        # DI2 DI1 DI0 同一行
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("DI2:"))
        di2_input = QLineEdit()
        di2_input.setMaxLength(2)
        h2.addWidget(di2_input)
        h2.addWidget(QLabel("DI1:"))
        di1_input = QLineEdit()
        di1_input.setMaxLength(2)
        h2.addWidget(di1_input)
        h2.addWidget(QLabel("DI0:"))
        di0_input = QLineEdit()
        di0_input.setMaxLength(2)
        h2.addWidget(di0_input)
        layout.addLayout(h2)

        # 中文含义
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("含义:"))
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("如：查询XX信息")
        h3.addWidget(desc_input)
        layout.addLayout(h3)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("添加")
        cancel_btn = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        apply_chinese_context_menus(dialog)

        if dialog.exec() != QDialog.Accepted:
            return

        # 验证输入
        try:
            di3 = int(di3_input.text().strip(), 16)
            di2 = int(di2_input.text().strip(), 16)
            di1 = int(di1_input.text().strip(), 16)
            di0 = int(di0_input.text().strip(), 16)
        except ValueError:
            QMessageBox.warning(self, "错误", "DI字段必须为十六进制（00-FF）！")
            return

        desc = desc_input.text().strip()
        if not desc:
            QMessageBox.warning(self, "错误", "请填写中文含义！")
            return

        # 检查重复
        custom_list = ProtocolFrameParser.load_custom_di_list()
        key = (di3, di2, di1, di0)
        for e in custom_list:
            if (e["di3"], e["di2"], e["di1"], e["di0"]) == key:
                QMessageBox.warning(self, "重复", "该DI已存在于自定义列表中！")
                return

        # 保存到 JSON
        custom_list.append({"di3": di3, "di2": di2, "di1": di1, "di0": di0, "desc": desc})
        ProtocolFrameParser.save_custom_di(custom_list)

        # 合并到解析器（单帧解析也能识别）
        if key not in self.parser.DI_COMBINATION_MAP:
            self.parser.DI_COMBINATION_MAP[key] = desc

        # 刷新表格
        self._load_di_map_data()
        QMessageBox.information(self, "成功", f"已添加自定义DI: {di3:02X} {di2:02X} {di1:02X} {di0:02X} → {desc}")

    def _del_custom_di(self):
        """删除选中的自定义DI"""
        row = self.di_table.currentRow()
        if row < 0 or row >= len(self._di_data):
            QMessageBox.warning(self, "提示", "请先选中一条记录！")
            return

        di3, di2, di1, di0, afn_val, afn_name, desc, is_custom = self._di_data[row]

        if not is_custom:
            QMessageBox.warning(self, "提示", "只能删除自定义DI（蓝色★标记的记录）！")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除自定义DI：{di3:02X} {di2:02X} {di1:02X} {di0:02X} ({desc})？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 从 JSON 移除
        custom_list = ProtocolFrameParser.load_custom_di_list()
        key = (di3, di2, di1, di0)
        custom_list = [e for e in custom_list
                       if (e["di3"], e["di2"], e["di1"], e["di0"]) != key]
        ProtocolFrameParser.save_custom_di(custom_list)

        # 从解析器移除
        if key in self.parser.DI_COMBINATION_MAP:
            del self.parser.DI_COMBINATION_MAP[key]

        self._load_di_map_data()
        QMessageBox.information(self, "成功", "已删除自定义DI")

    def create_batch_parse_tab(self) -> QWidget:
        """创建批量解析标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        # 工具栏
        toolbar = QHBoxLayout()

        self.load_file_btn = QPushButton("从文件加载")
        self.load_file_btn.setToolTip("支持每行一帧的文本文件")
        self.load_file_btn.clicked.connect(self.load_from_file)
        toolbar.addWidget(self.load_file_btn)

        self.paste_btn = QPushButton("从剪贴板粘贴")
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        toolbar.addWidget(self.paste_btn)

        toolbar.addStretch()

        self.batch_parse_btn = QPushButton("开始批量解析")
        self.batch_parse_btn.setMinimumHeight(35)
        self.batch_parse_btn.clicked.connect(self.parse_batch)
        toolbar.addWidget(self.batch_parse_btn)

        self.clear_batch_btn = QPushButton("清空")
        self.clear_batch_btn.clicked.connect(self.clear_batch)
        toolbar.addWidget(self.clear_batch_btn)

        layout.addLayout(toolbar)

        # 输入区
        input_group = QGroupBox("输入报文列表（每行一帧，自动根据当前协议识别）")
        input_layout = QVBoxLayout(input_group)

        self.batch_input = QTextEdit()
        self.batch_input.setPlaceholderText("粘贴或输入报文数据，支持多种协议：\n南网/国网协议：68开头，16结束\nHDLC协议：7E开头，7E结束\n其他协议：每行一帧直接解析")
        self.batch_input.setMaximumHeight(150)
        input_layout.addWidget(self.batch_input)

        layout.addWidget(input_group)

        # 结果统计
        self.stats_label = QLabel("状态：待解析")
        self.stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.stats_label)

        # 结果表格
        result_group = QGroupBox("解析结果")
        result_layout = QVBoxLayout(result_group)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels([
            "序号", "原始数据", "长度", "方向", "业务摘要", "状态"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.result_table.setColumnWidth(0, 50)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setAlternatingRowColors(True)
        # 紧凑字体和行高
        table_font = QFont()
        table_font.setPointSize(8)
        self.result_table.setFont(table_font)
        self.result_table.verticalHeader().setDefaultSectionSize(20)
        self.result_table.verticalHeader().hide()
        self.result_table.cellClicked.connect(self.show_detail_dialog)
        result_layout.addWidget(self.result_table)

        # 批量导出按钮
        export_batch_btn = QPushButton("导出全部结果(JSON)")
        export_batch_btn.clicked.connect(self.export_batch)
        result_layout.addWidget(export_batch_btn)

        layout.addWidget(result_group, 1)

        return tab

    def apply_styles(self):
        """应用样式表 - 全局白色背景黑色字体"""
        self.setStyleSheet("""
            /* ========== 全局基础 ========== */
            * {
                color: #000000;
            }
            QWidget {
                background-color: #ffffff;
                color: #000000;
            }
            QMainWindow {
                background-color: #f5f5f5;
            }

            /* ========== 对话框 / 弹窗 ========== */
            QDialog {
                background-color: #ffffff;
                color: #000000;
            }
            QMessageBox {
                background-color: #ffffff;
                color: #000000;
            }
            QMessageBox QLabel {
                color: #000000;
                background-color: transparent;
            }
            QMessageBox QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #1976D2;
            }

            /* ========== 右键菜单 ========== */
            QMenu {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 30px 6px 20px;
                background-color: #ffffff;
                color: #000000;
            }
            QMenu::item:selected {
                background-color: #e3f2fd;
                color: #000000;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 8px;
            }

            /* ========== 工具提示 ========== */
            QToolTip {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px;
            }

            /* ========== 滚动条 ========== */
            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background-color: #f5f5f5;
                height: 10px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: #c0c0c0;
                min-width: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #a0a0a0;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }

            /* ========== 分组框 ========== */
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 6px;
                background-color: #ffffff;
                color: #000000;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #000000;
            }

            /* ========== 按钮 ========== */
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton#secondary {
                background-color: #757575;
            }

            /* ========== 文本编辑框 ========== */
            QTextEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px;
                background-color: #ffffff;
                font-family: Consolas, Monaco, monospace;
                color: #000000;
            }

            /* ========== 行编辑框 ========== */
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px;
                background-color: #ffffff;
                color: #000000;
            }

            /* ========== 表格 ========== */
            QTableWidget {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: #ffffff;
                gridline-color: #e0e0e0;
                color: #000000;
                font-size: 9pt;
            }
            QTableWidget::item:!alternate {
                background-color: #ffffff;
                color: #000000;
                padding: 2px 4px;
            }
            QTableWidget::item:alternate {
                background-color: #e8e8e8;
                color: #000000;
                padding: 2px 4px;
            }
            QTableWidget::item:selected {
                background-color: #2196F3;
                color: white;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                padding: 4px 8px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
                color: #000000;
                font-size: 9pt;
            }

            /* ========== 标签 ========== */
            QLabel {
                color: #000000;
                background-color: transparent;
            }

            /* ========== 选项卡 ========== */
            QTabWidget::pane {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                padding: 6px 14px;
                margin-right: 2px;
                border: 1px solid #cccccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                background-color: #f5f5f5;
                color: #000000;
            }
            QTabBar::tab:selected {
                background-color: #2196F3;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e0e0e0;
            }

            /* ========== 下拉框 ========== */
            QComboBox {
                border: 1px solid #888;
                border-radius: 2px;
                padding: 4px 22px 4px 6px;
                background-color: #ffffff;
                color: #000000;
                min-height: 18px;
            }
            QComboBox:hover {
                border: 1px solid #666;
            }
            QComboBox:focus {
                border: 1px solid #6699cc;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #666;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #888;
                background-color: #ffffff;
                selection-background-color: #80b8e8;
                selection-color: #000000;
            }
            QComboBox QListView::item {
                background-color: #ffffff;
                color: #000000;
                padding: 3px 6px;
            }
            QComboBox QListView::item:selected {
                background-color: #80b8e8;
                color: #000000;
            }
            QComboBox QListView::item:hover {
                background-color: #e3f2fd;
                color: #000000;
            }

            /* ========== 复选框 / 单选框 ========== */
            QCheckBox, QRadioButton {
                color: #000000;
                background-color: transparent;
            }

            /* ========== 文件对话框 ========== */
            QFileDialog {
                background-color: #ffffff;
                color: #000000;
            }

            /* ========== 输入对话框 ========== */
            QInputDialog {
                background-color: #ffffff;
                color: #000000;
            }

            /* ========== 菜单栏 ========== */
            QMenuBar {
                background-color: #f5f5f5;
                color: #000000;
                border-bottom: 1px solid #d0d0d0;
                padding: 2px;
            }
            QMenuBar::item {
                padding: 4px 10px;
                background-color: transparent;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
            }
            QMenu {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 30px 6px 20px;
            }
            QMenu::item:selected {
                background-color: #e3f2fd;
            }
        """)

    # ==================== 串口功能 ====================

    def _refresh_serial_ports(self):
        """刷新可用串口列表"""
        self.serial_port_combo.clear()
        ports = SerialWorker.list_ports()
        if not ports:
            self.serial_port_combo.addItem("无可用串口")
            self.serial_port_combo.setEnabled(False)
        else:
            for p in ports:
                self.serial_port_combo.addItem(p)
            self.serial_port_combo.setEnabled(True)

    def _on_serial_open_clicked(self):
        """打开/关闭串口按钮点击"""
        if self.serial_worker.is_open():
            self.serial_worker.close_port()
            self.serial_open_btn.setText("打开串口")
            self.serial_open_btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
            )
            self.serial_port_combo.setEnabled(True)
            self.serial_baud_combo.setEnabled(True)
            self.serial_parity_combo.setEnabled(True)
        else:
            port = self.serial_port_combo.currentText()
            if not port or port == "无可用串口":
                QMessageBox.warning(self, "警告", "请选择一个有效的串口")
                return
            baud = int(self.serial_baud_combo.currentText())
            parity = self.serial_parity_combo.currentText()
            self.serial_worker.configure(port, baudrate=baud, parity=parity)
            if self.serial_worker.open_port():
                self.serial_open_btn.setText("关闭串口")
                self.serial_open_btn.setStyleSheet(
                    "QPushButton { background-color: #f44336; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
                )
                self.serial_port_combo.setEnabled(False)
                self.serial_baud_combo.setEnabled(False)
                self.serial_parity_combo.setEnabled(False)

    def _on_serial_connection_changed(self, connected: bool):
        """串口连接状态变化回调"""
        if connected:
            self.serial_status_label.setText("已连接")
            self.serial_status_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")
        else:
            self.serial_status_label.setText("未连接")
            self.serial_status_label.setStyleSheet("color: #999; font-size: 12px;")
            self.serial_open_btn.setText("打开串口")
            self.serial_open_btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
            )
            self.serial_port_combo.setEnabled(True)
            self.serial_baud_combo.setEnabled(True)
            self.serial_parity_combo.setEnabled(True)

    def _on_serial_error(self, msg: str):
        """串口错误回调"""
        QMessageBox.warning(self, "串口错误", msg)

    # ==================== 预设按钮功能 ====================

    def _on_preset_button_clicked(self, protocol: str, frame_hex: str, config: dict):
        """预设按钮点击：通过串口直接发送报文"""
        # 先切到对应协议（保持界面一致性）
        if protocol == "south" and self.current_protocol != 0:
            self.protocol_combo.setCurrentIndex(0)
        elif protocol == "gdw" and self.current_protocol != 6:
            self.protocol_combo.setCurrentIndex(6)

        # 检查串口是否打开
        if not self.serial_worker or not self.serial_worker.is_open():
            QMessageBox.warning(self, "串口未打开", "请先打开串口后再发送预设命令。")
            return

        # 把报文同步到组帧页面（方便查看）
        self.frame_gen_tab.result_hex.setText(frame_hex)

        # 直接通过串口发送
        self.serial_worker.send_hex_string(frame_hex)

        # 在串口日志显示
        self.frame_gen_tab._on_serial_log(f"[预设发送] {frame_hex}")

    # ==================== 单帧解析功能 ====================

    def _on_protocol_changed(self, index: int):
        """协议选择改变时的回调"""
        self.current_protocol = index
        # 更新占位符提示
        if index == 0:
            self.single_input.setPlaceholderText("请输入十六进制报文，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16")
        elif index == 1:
            self.single_input.setPlaceholderText("请输入PLC RF报文，例如：02 00 05 C0 20 01 00 99")
        elif index == 2:
            self.single_input.setPlaceholderText("请输入HDLC报文，例如：7E A0 07 01 01 93 ... 7E")
        elif index == 3:  # DLMS-APDU(国网)
            self.single_input.setPlaceholderText("请输入国网DLMS APDU报文，例如：C0 01 C1 00 ...")
        elif index == 4:  # DLMS Wrapper裸报文
            self.single_input.setPlaceholderText("请输入Wrapper报文，例如：00 01 00 02 00 1E ...")
        elif index == 5:  # DLMS-APDU裸报文
            self.single_input.setPlaceholderText("请输入APDU报文，例如：C0 01 C1 00 ...")
        elif index == 6:  # DLT645-2007
            self.single_input.setPlaceholderText("请输入DLT645报文，例如：68 AA AA AA AA AA AA 68 11 04 33 33 33 33 CS 16")
        elif index == 7:  # 国网协议
            self.single_input.setPlaceholderText("请输入国网报文，例如：68 0F 00 43 00 00 00 00 00 00 00 00 00 03 01 00 48 16")
        elif index == 8:  # 698.45
            self.single_input.setPlaceholderText("请输入698.45报文，例如：68 0E 00 41 01 07 08 09 AE C6 01 00 00 00 00 34 87 16")
        elif index == 9:  # 新一代载波协议(通感一体化)
            self.single_input.setPlaceholderText("请输入新一代载波报文，例如：11 01 01 00 00 00 00 01 00 01 00 00")
        else:  # index == 10, 国网新一代双模通信互联互通
            self.single_input.setPlaceholderText("请输入国网新一代报文，例如：ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00")

        # 更新查询页面
        self._update_protocol_lookup_tab()

        # 协议组帧页面和预设命令页面在南网、国网、698.45协议下显示
        if hasattr(self, '_frame_gen_tab_index'):
            show_frame_gen = index in (0, 7, 8)
            self.tab_widget.setTabVisible(self._frame_gen_tab_index, show_frame_gen)
            if show_frame_gen:
                if index == 0:
                    mode = "south"
                elif index == 7:
                    mode = "gdw"
                else:
                    mode = "dlt698"
                self.frame_gen_tab.set_protocol_mode(mode)
            else:
                self.frame_gen_tab.reset()
        if hasattr(self, '_preset_tab_index'):
            self.tab_widget.setTabVisible(self._preset_tab_index, index in (0, 7, 8))
            if index in (0, 7, 8):
                if index == 0:
                    mode = "south"
                elif index == 7:
                    mode = "gdw"
                else:
                    mode = "dlt698"
                self.preset_tab.set_protocol(mode)
        # 档案管理页面在南网、国网协议下显示
        if hasattr(self, '_archive_tab_index'):
            show_archive = index in (0, 7)
            self.tab_widget.setTabVisible(self._archive_tab_index, show_archive)
            if show_archive:
                if index == 0:
                    mode = "south"
                else:
                    mode = "gdw"
                self.archive_tab.set_protocol_mode(mode)
        # 拓扑信息页面在南网、国网协议下显示
        if hasattr(self, '_topology_tab_index'):
            show_topology = index in (0, 7)
            self.tab_widget.setTabVisible(self._topology_tab_index, show_topology)
            if show_topology:
                if index == 0:
                    mode = "south"
                else:
                    mode = "gdw"
                self.topology_tab.set_protocol_mode(mode)
            else:
                self.topology_tab.clear_nodes()

        # 新一代载波协议解析级别选择和字节剔除：仅协议索引9时可见
        show_csg_level = (index == 9)
        self.csg_parse_level_label.setVisible(show_csg_level)
        self.csg_parse_level_combo.setVisible(show_csg_level)
        self.csg_strip_head_label.setVisible(show_csg_level)
        self.csg_strip_head_spin.setVisible(show_csg_level)
        self.csg_strip_tail_label.setVisible(show_csg_level)
        self.csg_strip_tail_spin.setVisible(show_csg_level)

        # 国网新一代解析级别选择：仅协议索引10时可见
        show_gw_level = (index == 10)
        self.gw_parse_level_label.setVisible(show_gw_level)
        self.gw_parse_level_combo.setVisible(show_gw_level)

        # 清空当前结果
        self.clear_single()

        # 同步协议到报文对比标签页
        if hasattr(self, 'diff_tab'):
            self.diff_tab.set_protocol(index)
            self.diff_tab.set_parser(self._get_current_parser())

    def _on_csg_parse_level_changed(self, index: int):
        """新一代载波协议解析级别改变时的回调"""
        level_map = {0: "auto", 1: "fc_pb", 2: "fc_efc", 3: "fc_only", 4: "app"}
        self._csg_parse_level = level_map.get(index, "auto")

    def _on_gw_parse_level_changed(self, index: int):
        """国网新一代解析级别改变时的回调"""
        level_map = {0: "auto", 1: "fc_only", 2: "fc_mac", 3: "app"}
        self._gw_parse_level = level_map.get(index, "auto")

    def _update_protocol_lookup_tab(self):
        """根据当前协议更新查询页面内容"""
        # 清空当前查询页面内容（递归清除所有子layout和widget）
        self._clear_layout(self.protocol_lookup_tab_layout)

        # 更新选项卡标签
        lookup_tab_index = self.tab_widget.indexOf(self.protocol_lookup_tab)

        if self.current_protocol == 0:
            # 南网协议：DI查询
            self.tab_widget.setTabText(lookup_tab_index, "DI查询")
            self._create_di_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol == 1:
            # 万胜PLC RF协议：命令字查询
            self.tab_widget.setTabText(lookup_tab_index, "命令字查询")
            self._create_command_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol in (2, 3, 4, 5):
            # HDLC/DLMS-APDU(国网)/Wrapper/DLMS-APDU：OBIS查询
            self.tab_widget.setTabText(lookup_tab_index, "OBIS查询")
            self._create_obis_lookup_content(self.protocol_lookup_tab_layout)
            
        elif self.current_protocol == 6:
            # DLT645-2007协议：DI查询
            self.tab_widget.setTabText(lookup_tab_index, "DI查询")
            self._create_dlt645_di_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol == 7:
            # 国网协议：AFN查询
            self.tab_widget.setTabText(lookup_tab_index, "AFN查询")
            self._create_gdw_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol == 8:
            # 698.45协议：OAD查询
            self.tab_widget.setTabText(lookup_tab_index, "OAD查询")
            self._create_oad_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol == 9:
            # 新一代载波协议(通感一体化)：业务标识查询
            self.tab_widget.setTabText(lookup_tab_index, "业务标识查询")
            self._create_csg_new_gen_lookup_content(self.protocol_lookup_tab_layout)

        elif self.current_protocol == 10:
            # 国网新一代双模通信互联互通：报文ID查询
            self.tab_widget.setTabText(lookup_tab_index, "报文ID查询")
            self._create_gw_new_gen_lookup_content(self.protocol_lookup_tab_layout)

    def _create_oad_lookup_content(self, layout):
        """创建698.45协议OAD查询页面内容"""
        from dl_t698_45_oi_lookup import OILookup

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.oad_search_input = QLineEdit()
        self.oad_search_input.setPlaceholderText("输入OI(如2000)或中文关键词(如通信地址)搜索...")
        self.oad_search_input.setClearButtonEnabled(True)
        self.oad_search_input.textChanged.connect(self._filter_oad_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.oad_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.oad_stats_label = QLabel()
        self.oad_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.oad_stats_label)

        # 表格
        self.oad_table = QTableWidget()
        self.oad_table.setColumnCount(5)
        self.oad_table.setHorizontalHeaderLabels(["OI", "对象名称", "属性", "方法", "说明"])
        header = self.oad_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.oad_table.setColumnWidth(0, 80)
        self.oad_table.setColumnWidth(1, 120)
        self.oad_table.setColumnWidth(2, 200)
        self.oad_table.setColumnWidth(3, 120)
        self.oad_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.oad_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.oad_table.setAlternatingRowColors(True)
        self.oad_table.verticalHeader().hide()
        self.oad_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        self.oad_table.setFont(table_font)
        layout.addWidget(self.oad_table)

        # 加载数据
        self._load_oad_map_data()

    def _create_csg_new_gen_lookup_content(self, layout):
        """创建新一代载波协议(通感一体化)业务标识查询页面内容"""
        from csg_new_gen_parser import (
            MSG_PORT_MAP, MSG_ID_MAP, FRAME_TYPE_MAP, DIRECTION_MAP,
            PRM_MAP, RESPONSE_MAP, EXTENSION_MAP, CONFIRM_SERVICE_MAP,
            DATA_SERVICE_MAP, CMD_FUNC_SERVICE_MAP, CMD_COMM_SERVICE_MAP,
            MPDU_VERSION_MAP,
        )

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(QFont("Microsoft YaHei", 10))
        search_layout.addWidget(search_label)

        self.csg_new_gen_search = QLineEdit()
        self.csg_new_gen_search.setPlaceholderText("输入关键词搜索业务标识（如：确认、数据传输、命令...）")
        self.csg_new_gen_search.setFont(QFont("Microsoft YaHei", 10))
        self.csg_new_gen_search.textChanged.connect(self._load_csg_new_gen_map_data)
        search_layout.addWidget(self.csg_new_gen_search)
        layout.addLayout(search_layout)

        # 统计标签
        self.csg_new_gen_stats_label = QLabel()
        self.csg_new_gen_stats_label.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self.csg_new_gen_stats_label)

        # 查询表格
        self.csg_new_gen_table = QTableWidget()
        self.csg_new_gen_table.setColumnCount(4)
        self.csg_new_gen_table.setHorizontalHeaderLabels(["分类", "代码", "名称", "说明"])
        self.csg_new_gen_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.csg_new_gen_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.csg_new_gen_table.setAlternatingRowColors(True)
        self.csg_new_gen_table.verticalHeader().hide()
        self.csg_new_gen_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        self.csg_new_gen_table.setFont(table_font)
        # 表头自适应
        header = self.csg_new_gen_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.csg_new_gen_table)

        # 存储查找表
        self._csg_new_gen_entries = []
        # 构建条目列表
        for cat, map_dict in [
            ("报文端口号", MSG_PORT_MAP),
            ("报文标识符", MSG_ID_MAP),
            ("帧类型域", FRAME_TYPE_MAP),
            ("传输方向", DIRECTION_MAP),
            ("启动标志(PRM)", PRM_MAP),
            ("响应标识", RESPONSE_MAP),
            ("业务扩展域", EXTENSION_MAP),
            ("确认/否认业务", CONFIRM_SERVICE_MAP),
            ("数据传输业务", DATA_SERVICE_MAP),
            ("命令-功能业务", CMD_FUNC_SERVICE_MAP),
            ("命令-通信管理业务", CMD_COMM_SERVICE_MAP),
            ("MPDU标准版本", MPDU_VERSION_MAP),
        ]:
            for code, name in map_dict.items():
                self._csg_new_gen_entries.append((cat, f"0x{code:02X}" if isinstance(code, int) else code, name, ""))

        self._load_csg_new_gen_map_data()

    def _load_csg_new_gen_map_data(self):
        """加载/过滤新一代载波协议业务标识数据"""
        search = self.csg_new_gen_search.text().strip().lower() if hasattr(self, 'csg_new_gen_search') else ""
        results = [e for e in self._csg_new_gen_entries
                   if not search or search in e[0].lower() or search in e[1].lower() or search in e[2].lower()]

        self.csg_new_gen_table.setRowCount(len(results))
        for row, (cat, code, name, note) in enumerate(results):
            self.csg_new_gen_table.setItem(row, 0, QTableWidgetItem(cat))
            self.csg_new_gen_table.setItem(row, 1, QTableWidgetItem(str(code)))
            self.csg_new_gen_table.setItem(row, 2, QTableWidgetItem(name))
            self.csg_new_gen_table.setItem(row, 3, QTableWidgetItem(note))

        self.csg_new_gen_stats_label.setText(f"匹配 {len(results)} / {len(self._csg_new_gen_entries)} 条记录")

    def _create_gw_new_gen_lookup_content(self, layout):
        """创建国网新一代双模通信互联互通报文ID查询页面内容"""
        from gw_new_gen_parser import GWNewGenParser
        parser = GWNewGenParser()

        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(QFont("Microsoft YaHei", 10))
        search_layout.addWidget(search_label)
        self.gw_new_gen_search = QLineEdit()
        self.gw_new_gen_search.setPlaceholderText("输入关键词搜索报文ID/端口号/消息类型...")
        self.gw_new_gen_search.setFont(QFont("Microsoft YaHei", 10))
        self.gw_new_gen_search.textChanged.connect(self._load_gw_new_gen_map_data)
        search_layout.addWidget(self.gw_new_gen_search)
        layout.addLayout(search_layout)

        self.gw_new_gen_stats_label = QLabel()
        self.gw_new_gen_stats_label.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self.gw_new_gen_stats_label)

        self.gw_new_gen_table = QTableWidget()
        self.gw_new_gen_table.setColumnCount(4)
        self.gw_new_gen_table.setHorizontalHeaderLabels(["分类", "代码", "名称", "说明"])
        self.gw_new_gen_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.gw_new_gen_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.gw_new_gen_table.setAlternatingRowColors(True)
        self.gw_new_gen_table.verticalHeader().hide()
        self.gw_new_gen_table.verticalHeader().setDefaultSectionSize(20)
        header = self.gw_new_gen_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.gw_new_gen_table)

        self._gw_new_gen_entries = []
        for code, name in parser.MSG_IDS.items():
            sec = (code >> 12) & 0x0F
            self._gw_new_gen_entries.append(("报文ID", f"0x{code:04X}", name, f"安全机制={sec}"))
        for code, name in parser.PORT_NAMES.items():
            self._gw_new_gen_entries.append(("报文端口号", f"0x{code:02X}", name, ""))
        for code, name in parser.DELIMITER_TYPES.items():
            self._gw_new_gen_entries.append(("定界符类型", str(code), name, ""))
        for code, name in parser.MSDU_TYPES.items():
            self._gw_new_gen_entries.append(("MSDU类型", str(code), name, ""))
        for code, name in parser.PROTOCOL_TYPES.items():
            self._gw_new_gen_entries.append(("规约类型", str(code), name, ""))
        for code, name in parser.SEND_TYPES.items():
            self._gw_new_gen_entries.append(("发送类型", str(code), name, ""))
        for code, name in parser.BROADCAST_DIRS.items():
            self._gw_new_gen_entries.append(("广播方向", str(code), name, ""))
        self._load_gw_new_gen_map_data()

    def _load_gw_new_gen_map_data(self):
        """加载/过滤国网新一代报文ID数据"""
        search = self.gw_new_gen_search.text().strip().lower() if hasattr(self, 'gw_new_gen_search') else ""
        results = [e for e in self._gw_new_gen_entries
                   if not search or search in e[0].lower() or search in e[1].lower() or search in e[2].lower()]
        self.gw_new_gen_table.setRowCount(len(results))
        for row, (cat, code, name, note) in enumerate(results):
            self.gw_new_gen_table.setItem(row, 0, QTableWidgetItem(cat))
            self.gw_new_gen_table.setItem(row, 1, QTableWidgetItem(str(code)))
            self.gw_new_gen_table.setItem(row, 2, QTableWidgetItem(name))
            self.gw_new_gen_table.setItem(row, 3, QTableWidgetItem(note))
        self.gw_new_gen_stats_label.setText(f"匹配 {len(results)} / {len(self._gw_new_gen_entries)} 条记录")

    def _load_oad_map_data(self):
        """加载698.45 OI映射数据"""
        from dl_t698_45_oi_lookup import OILookup
        lookup = OILookup()
        self._oad_data = []
        for oi, name in lookup.OI_NAME_MAP.items():
            class_id = lookup.OI_TO_CLASS_ID.get(oi)
            if class_id is not None:
                info = lookup.CLASS_ID_MAP.get(class_id, {})
                attrs = ", ".join([f"{k}:{v}" for k, v in info.get("attributes", {}).items()])
                methods = ", ".join([f"{k}:{v}" for k, v in info.get("methods", {}).items()])
            else:
                attrs = ""
                methods = ""
            self._oad_data.append((f"0x{oi:04X}", name, attrs, methods or "-", f"OI=0x{oi:04X}"))
        self._filter_oad_table()

    def _filter_oad_table(self):
        """过滤OAD查询表格"""
        keyword = self.oad_search_input.text().strip().lower() if hasattr(self, 'oad_search_input') else ""
        filtered = []
        for row in self._oad_data:
            if not keyword or any(keyword in str(cell).lower() for cell in row):
                filtered.append(row)
        self.oad_table.setRowCount(len(filtered))
        for i, row in enumerate(filtered):
            for j, val in enumerate(row):
                self.oad_table.setItem(i, j, QTableWidgetItem(str(val)))
        self.oad_stats_label.setText(f"共 {len(filtered)} 条记录")

    def _create_gdw_lookup_content(self, layout):
        """创建国网协议AFN查询页面内容"""
        # 搜索栏 + 操作按钮
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.gdw_search_input = QLineEdit()
        self.gdw_search_input.setPlaceholderText("输入AFN(如03H)或Fn(如F1)或中文关键词搜索...")
        self.gdw_search_input.setClearButtonEnabled(True)
        self.gdw_search_input.textChanged.connect(self._filter_gdw_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.gdw_search_input)

        # 添加自定义按钮
        add_btn = QPushButton("添加自定义")
        add_btn.setToolTip("添加自定义AFN+Fn组合")
        add_btn.clicked.connect(self._add_custom_gdw_fn)
        search_layout.addWidget(add_btn)

        # 删除自定义按钮
        del_btn = QPushButton("删除自定义")
        del_btn.setToolTip("删除选中的自定义AFN+Fn组合")
        del_btn.clicked.connect(self._delete_custom_gdw_fn)
        search_layout.addWidget(del_btn)

        layout.addLayout(search_layout)

        # 统计标签
        self.gdw_stats_label = QLabel()
        self.gdw_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.gdw_stats_label)

        # 表格
        self.gdw_table = QTableWidget()
        self.gdw_table.setColumnCount(4)
        self.gdw_table.setHorizontalHeaderLabels(["AFN", "AFN名称", "Fn", "功能说明"])
        header = self.gdw_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.gdw_table.setColumnWidth(0, 60)
        self.gdw_table.setColumnWidth(1, 180)
        self.gdw_table.setColumnWidth(2, 60)
        self.gdw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.gdw_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.gdw_table.setAlternatingRowColors(True)
        self.gdw_table.verticalHeader().hide()
        self.gdw_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        self.gdw_table.setFont(table_font)
        layout.addWidget(self.gdw_table)

        # 加载数据
        self._load_gdw_map_data()

    def _load_gdw_map_data(self):
        """从国网解析器加载AFN+Fn数据到表格（包含自定义条目）"""
        data = self.gdw_parser.get_afn_fn_list()
        self._gdw_data = data
        self.gdw_table.setRowCount(len(data))
        for row, (afn, afn_name, fn, fn_name) in enumerate(data):
            item_afn = QTableWidgetItem(f"{afn:02X}H")
            item_afn_name = QTableWidgetItem(afn_name)
            item_fn = QTableWidgetItem(f"F{fn}")
            item_fn_name = QTableWidgetItem(fn_name)
            # 自定义条目用蓝色标记
            is_custom = (afn in self.gdw_parser._custom_fn_map and fn in self.gdw_parser._custom_fn_map.get(afn, {}))
            if is_custom:
                blue_brush = QColor("#E3F2FD")
                for item in (item_afn, item_afn_name, item_fn, item_fn_name):
                    item.setBackground(blue_brush)
            self.gdw_table.setItem(row, 0, item_afn)
            self.gdw_table.setItem(row, 1, item_afn_name)
            self.gdw_table.setItem(row, 2, item_fn)
            self.gdw_table.setItem(row, 3, item_fn_name)
        self.gdw_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_gdw_table(self, text: str):
        """根据搜索文本过滤国网AFN表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_gdw_map_data()
            return
        results = self.gdw_parser.search_afn_fn(keyword)
        self.gdw_table.setRowCount(len(results))
        for row, (afn, afn_name, fn, fn_name) in enumerate(results):
            item_afn = QTableWidgetItem(f"{afn:02X}H")
            item_afn_name = QTableWidgetItem(afn_name)
            item_fn = QTableWidgetItem(f"F{fn}")
            item_fn_name = QTableWidgetItem(fn_name)
            is_custom = (afn in self.gdw_parser._custom_fn_map and fn in self.gdw_parser._custom_fn_map.get(afn, {}))
            if is_custom:
                blue_brush = QColor("#E3F2FD")
                for item in (item_afn, item_afn_name, item_fn, item_fn_name):
                    item.setBackground(blue_brush)
            self.gdw_table.setItem(row, 0, item_afn)
            self.gdw_table.setItem(row, 1, item_afn_name)
            self.gdw_table.setItem(row, 2, item_fn)
            self.gdw_table.setItem(row, 3, item_fn_name)
        self.gdw_stats_label.setText(f"匹配 {len(results)} / {len(self._gdw_data)} 条记录")

    def _add_custom_gdw_fn(self):
        """弹出对话框添加自定义AFN+Fn"""
        from PySide6.QtWidgets import QDialog, QFormLayout, QSpinBox, QLineEdit as QLE, QDialogButtonBox, QMessageBox
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义AFN+Fn")
        dialog.setMinimumWidth(300)
        layout = QFormLayout(dialog)

        afn_input = QSpinBox()
        afn_input.setRange(0, 255)
        afn_input.setPrefix("0x")
        afn_input.setDisplayIntegerBase(16)
        layout.addRow("AFN (十六进制):", afn_input)

        fn_input = QSpinBox()
        fn_input.setRange(1, 248)
        layout.addRow("Fn:", fn_input)

        name_input = QLE()
        name_input.setPlaceholderText("输入功能名称")
        layout.addRow("功能名称:", name_input)

        afn_name_input = QLE()
        afn_name_input.setPlaceholderText("可选：自定义AFN类别名称")
        layout.addRow("AFN类别名称(可选):", afn_name_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            afn = afn_input.value()
            fn = fn_input.value()
            name = name_input.text().strip()
            afn_name = afn_name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "警告", "功能名称不能为空")
                return
            # Check if already exists as standard
            if afn in self.gdw_parser.FN_MAP and fn in self.gdw_parser.FN_MAP.get(afn, {}):
                QMessageBox.warning(self, "警告", f"AFN={afn:02X}H Fn=F{fn} 已在标准定义中存在")
                return
            # Add custom AFN name if provided
            if afn_name:
                self.gdw_parser.add_custom_afn(afn, afn_name)
            # Add custom Fn
            self.gdw_parser.add_custom_fn(afn, fn, name)
            self._load_gdw_map_data()
            self.gdw_search_input.clear()
            QMessageBox.information(self, "成功", f"已添加自定义组合: AFN={afn:02X}H Fn=F{fn}")

    def _delete_custom_gdw_fn(self):
        """删除选中的自定义AFN+Fn"""
        row = self.gdw_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中要删除的自定义条目")
            return
        afn_text = self.gdw_table.item(row, 0).text().replace("H", "")
        fn_text = self.gdw_table.item(row, 2).text()
        try:
            afn = int(afn_text, 16)
            fn = int(fn_text.replace("F", ""))
        except ValueError:
            return
        # Check if it's custom
        is_custom = (afn in self.gdw_parser._custom_fn_map and fn in self.gdw_parser._custom_fn_map.get(afn, {}))
        if not is_custom:
            QMessageBox.information(self, "提示", "只能删除自定义添加的条目")
            return
        reply = QMessageBox.question(self, "确认删除", f"确定删除自定义组合 AFN={afn:02X}H Fn=F{fn}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.gdw_parser.remove_custom_fn(afn, fn)
            self._load_gdw_map_data()
            QMessageBox.information(self, "成功", "已删除自定义组合")

    def _create_di_lookup_content(self, layout):
        """创建南网协议DI查询页面内容"""
        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.di_search_input = QLineEdit()
        self.di_search_input.setPlaceholderText("输入DI编码(如E8020201)或中文关键词(如添加任务)搜索...")
        self.di_search_input.setClearButtonEnabled(True)
        self.di_search_input.textChanged.connect(self._filter_di_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.di_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.di_stats_label = QLabel()
        self.di_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.di_stats_label)

        # 表格
        self.di_table = QTableWidget()
        self.di_table.setColumnCount(6)
        self.di_table.setHorizontalHeaderLabels(["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义"])
        header = self.di_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.di_table.setColumnWidth(0, 60)
        self.di_table.setColumnWidth(1, 60)
        self.di_table.setColumnWidth(2, 60)
        self.di_table.setColumnWidth(3, 60)
        self.di_table.setColumnWidth(4, 200)
        self.di_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.di_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.di_table.setAlternatingRowColors(True)
        self.di_table.verticalHeader().hide()
        self.di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        self.di_table.setFont(table_font)
        layout.addWidget(self.di_table)

        # 按钮栏
        btn_layout = QHBoxLayout()
        add_di_btn = QPushButton("添加自定义DI")
        add_di_btn.clicked.connect(self._add_custom_di)
        btn_layout.addWidget(add_di_btn)

        del_di_btn = QPushButton("删除选中自定义DI")
        del_di_btn.clicked.connect(self._del_custom_di)
        btn_layout.addWidget(del_di_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_di_map_data()

    def _create_obis_lookup_content(self, layout):
        """创建OBIS查询页面（HDLC/Wrapper/APDU协议）"""
        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(30)
        self.obis_search_input = QLineEdit()
        self.obis_search_input.setPlaceholderText("输入OBIS码(如0.0.96.1.0.255)或关键词搜索...")
        self.obis_search_input.setClearButtonEnabled(True)
        self.obis_search_input.textChanged.connect(self._filter_obis_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.obis_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.obis_stats_label = QLabel()
        self.obis_stats_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.obis_stats_label)

        # 表格
        self.obis_table = QTableWidget()
        self.obis_table.setColumnCount(4)
        self.obis_table.setHorizontalHeaderLabels(["OBIS码", "对象名称", "对象类型", "访问属性"])
        header = self.obis_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.obis_table.setColumnWidth(0, 100)
        self.obis_table.setColumnWidth(1, 130)
        self.obis_table.setColumnWidth(2, 90)
        self.obis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.obis_table.setAlternatingRowColors(True)
        self.obis_table.verticalHeader().hide()
        self.obis_table.verticalHeader().setDefaultSectionSize(14)
        table_font = QFont()
        table_font.setPointSize(7)
        self.obis_table.setFont(table_font)

        layout.addWidget(self.obis_table)

        # 加载数据
        self._load_obis_map_data()

    def _create_dlt645_di_lookup_content(self, layout):
        """创建DLT645-2007 DI查询页面"""
        # 初始化DI查询器
        self.dlt645_di_lookup = get_dlt645_di_lookup()

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.dlt645_di_search_input = QLineEdit()
        self.dlt645_di_search_input.setPlaceholderText("输入DI编码(如04000101)或中文关键词搜索...")
        self.dlt645_di_search_input.setClearButtonEnabled(True)
        self.dlt645_di_search_input.textChanged.connect(self._filter_dlt645_di_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.dlt645_di_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.dlt645_di_stats_label = QLabel()
        self.dlt645_di_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.dlt645_di_stats_label)

        # 表格
        self.dlt645_di_table = QTableWidget()
        self.dlt645_di_table.setColumnCount(5)
        self.dlt645_di_table.setHorizontalHeaderLabels(["DI编码", "名称", "单位", "数据类型", "说明"])
        header = self.dlt645_di_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.dlt645_di_table.setColumnWidth(0, 90)
        self.dlt645_di_table.setColumnWidth(1, 180)
        self.dlt645_di_table.setColumnWidth(2, 60)
        self.dlt645_di_table.setColumnWidth(3, 80)
        self.dlt645_di_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dlt645_di_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dlt645_di_table.setAlternatingRowColors(True)
        self.dlt645_di_table.verticalHeader().hide()
        self.dlt645_di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        self.dlt645_di_table.setFont(table_font)

        layout.addWidget(self.dlt645_di_table)

        # 按钮栏
        btn_layout = QHBoxLayout()
        add_dlt645_di_btn = QPushButton("添加自定义DI")
        add_dlt645_di_btn.clicked.connect(self._add_dlt645_custom_di)
        btn_layout.addWidget(add_dlt645_di_btn)

        del_dlt645_di_btn = QPushButton("删除选中自定义DI")
        del_dlt645_di_btn.clicked.connect(self._del_dlt645_custom_di)
        btn_layout.addWidget(del_dlt645_di_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_dlt645_di_map_data()

    def _load_dlt645_di_map_data(self):
        """从DLT645 DI查询器加载数据到表格"""
        data = self.dlt645_di_lookup.data
        self._dlt645_di_data = data
        self.dlt645_di_table.setRowCount(len(data))
        for row, (di_code, di_name, unit, data_type, desc, is_custom) in enumerate(data):
            self.dlt645_di_table.setItem(row, 0, QTableWidgetItem(di_code))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + di_name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.dlt645_di_table.setItem(row, 1, name_item)
            self.dlt645_di_table.setItem(row, 2, QTableWidgetItem(unit))
            self.dlt645_di_table.setItem(row, 3, QTableWidgetItem(data_type))
            self.dlt645_di_table.setItem(row, 4, QTableWidgetItem(desc))
        custom_count = sum(1 for item in data if item[5])
        self.dlt645_di_stats_label.setText(f"共 {len(data)} 条记录（其中自定义 {custom_count} 条）")

    def _filter_dlt645_di_table(self, text: str):
        """根据搜索文本过滤DLT645 DI表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_dlt645_di_map_data()
            return
        results = self.dlt645_di_lookup.search(keyword)
        self.dlt645_di_table.setRowCount(len(results))
        for row, (di_code, di_name, unit, data_type, desc, is_custom) in enumerate(results):
            self.dlt645_di_table.setItem(row, 0, QTableWidgetItem(di_code))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + di_name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.dlt645_di_table.setItem(row, 1, name_item)
            self.dlt645_di_table.setItem(row, 2, QTableWidgetItem(unit))
            self.dlt645_di_table.setItem(row, 3, QTableWidgetItem(data_type))
            self.dlt645_di_table.setItem(row, 4, QTableWidgetItem(desc))
        custom_count = sum(1 for item in results if item[5])
        self.dlt645_di_stats_label.setText(f"匹配 {len(results)} / {len(self._dlt645_di_data)} 条记录（其中自定义 {custom_count} 条）")

    def _add_dlt645_custom_di(self):
        """添加DLT645自定义DI对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义DI (DLT645)")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)

        # DI编码
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("DI编码:"))
        di_code_input = QLineEdit()
        di_code_input.setPlaceholderText("如 04000101")
        di_code_input.setMaxLength(8)
        h1.addWidget(di_code_input)
        layout.addLayout(h1)

        # 名称
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("名称:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("如：当前正向有功总电能")
        h2.addWidget(name_input)
        layout.addLayout(h2)

        # 单位
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("单位:"))
        unit_input = QLineEdit()
        unit_input.setPlaceholderText("如：kWh（可留空）")
        h3.addWidget(unit_input)
        layout.addLayout(h3)

        # 数据类型
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("数据类型:"))
        data_type_input = QLineEdit()
        data_type_input.setPlaceholderText("如：XX（可留空）")
        h4.addWidget(data_type_input)
        layout.addLayout(h4)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("添加")
        cancel_btn = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return

        di_code = di_code_input.text().strip().upper()
        name = name_input.text().strip()
        unit = unit_input.text().strip()
        data_type = data_type_input.text().strip()

        if not di_code or not name:
            QMessageBox.warning(self, "错误", "DI编码和名称不能为空！")
            return

        success = self.dlt645_di_lookup.add_custom_di(di_code, name, unit, data_type)
        if success:
            self._load_dlt645_di_map_data()
            QMessageBox.information(self, "成功", f"已添加自定义DI: {di_code} → {name}")
        else:
            QMessageBox.warning(self, "错误", "添加失败，请检查DI编码格式（8位十六进制）")

    def _del_dlt645_custom_di(self):
        """删除选中的DLT645自定义DI"""
        row = self.dlt645_di_table.currentRow()
        if row < 0 or row >= len(self._dlt645_di_data):
            QMessageBox.warning(self, "提示", "请先选中一条记录！")
            return

        di_code, di_name, unit, data_type, desc, is_custom = self._dlt645_di_data[row]

        if not is_custom:
            QMessageBox.warning(self, "提示", "只能删除自定义DI（蓝色★标记的记录）！")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除自定义DI：{di_code} ({di_name})？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success = self.dlt645_di_lookup.delete_custom_di(di_code)
        if success:
            self._load_dlt645_di_map_data()
            QMessageBox.information(self, "成功", "已删除自定义DI")
        else:
            QMessageBox.warning(self, "错误", "删除失败")

    def _create_command_lookup_content(self, layout):
        """创建万胜PLC RF协议命令字查询页面"""
        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(30)
        self.cmd_search_input = QLineEdit()
        self.cmd_search_input.setPlaceholderText("输入命令字编码或中文关键词搜索...")
        self.cmd_search_input.setClearButtonEnabled(True)
        self.cmd_search_input.textChanged.connect(self._filter_command_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.cmd_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.cmd_stats_label = QLabel()
        self.cmd_stats_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.cmd_stats_label)

        # 表格
        self.cmd_table = QTableWidget()
        self.cmd_table.setColumnCount(2)
        self.cmd_table.setHorizontalHeaderLabels(["命令字", "名称"])
        header = self.cmd_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.cmd_table.setColumnWidth(0, 80)
        self.cmd_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cmd_table.setAlternatingRowColors(True)
        self.cmd_table.verticalHeader().hide()
        self.cmd_table.verticalHeader().setDefaultSectionSize(14)
        table_font = QFont()
        table_font.setPointSize(7)
        self.cmd_table.setFont(table_font)

        layout.addWidget(self.cmd_table)

        # 加载数据
        self._load_command_map_data()

    def _load_command_map_data(self):
        """从命令字查询器加载数据到表格"""
        data = self.command_lookup._data
        self.cmd_table.setRowCount(len(data))
        for row, (code, name, desc, is_custom) in enumerate(data):
            self.cmd_table.setItem(row, 0, QTableWidgetItem(f"{code:04X}"))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.cmd_table.setItem(row, 1, name_item)
        self.cmd_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_command_table(self, text: str):
        """根据搜索文本过滤命令字表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_command_map_data()
            return
        results = self.command_lookup.search(keyword)
        self.cmd_table.setRowCount(len(results))
        for row, (code, name, desc, is_custom) in enumerate(results):
            self.cmd_table.setItem(row, 0, QTableWidgetItem(f"{code:04X}"))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.cmd_table.setItem(row, 1, name_item)
        self.cmd_stats_label.setText(f"匹配 {len(results)} / {len(self.command_lookup._data)} 条记录")

    def _load_obis_map_data(self):
        """从OBIS查询器加载数据到表格"""
        data = self.obis_lookup._data
        self.obis_table.setRowCount(len(data))
        for row, (obis, name, desc, is_custom) in enumerate(data):
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            self.obis_table.setItem(row, 0, QTableWidgetItem(obis_str))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.obis_table.setItem(row, 1, name_item)
            # 根据OBIS A值推断对象类型
            a = obis[0]
            type_map = {
                0: "General", 1: "Register", 2: "ExtendedRegister",
                3: "DemandRegister", 5: "ProfileGeneric", 7: "ScriptTable",
                10: "Association LN", 17: "ActivityCalendar",
                20: "DisconnectControl",
            }
            self.obis_table.setItem(row, 2, QTableWidgetItem(type_map.get(a, f"Type_{a}")))
            self.obis_table.setItem(row, 3, QTableWidgetItem("Read/Write" if is_custom else "Read"))
        self.obis_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_obis_table(self, text: str):
        """根据搜索文本过滤OBIS表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_obis_map_data()
            return
        results = self.obis_lookup.search(keyword)
        self.obis_table.setRowCount(len(results))
        for row, (obis, name, desc, is_custom) in enumerate(results):
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            self.obis_table.setItem(row, 0, QTableWidgetItem(obis_str))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.obis_table.setItem(row, 1, name_item)
            a = obis[0]
            type_map = {
                0: "General", 1: "Register", 2: "ExtendedRegister",
                3: "DemandRegister", 5: "ProfileGeneric", 7: "ScriptTable",
                10: "Association LN", 17: "ActivityCalendar",
                20: "DisconnectControl",
            }
            self.obis_table.setItem(row, 2, QTableWidgetItem(type_map.get(a, f"Type_{a}")))
            self.obis_table.setItem(row, 3, QTableWidgetItem("Read/Write" if is_custom else "Read"))
        self.obis_stats_label.setText(f"匹配 {len(results)} / {len(self.obis_lookup._data)} 条记录")

    def _get_current_parser(self):
        """获取当前选中的解析器"""
        if self.current_protocol == 0:
            return self.parser
        elif self.current_protocol == 1:
            return self.plc_rf_parser
        elif self.current_protocol == 2:  # HDLC/国网DLMS (完整HDLC帧)
            return self.hdlc_parser
        elif self.current_protocol == 3:  # DLMS-APDU(国网) (直接解析APDU)
            # 返回一个匿名对象，调用parse_apdu_to_table
            class APDUParserGuowang:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_apdu_to_table(data)
            return APDUParserGuowang(self.hdlc_parser)
        elif self.current_protocol == 4:  # DLMS Wrapper裸报文 (直接解析Wrapper+APDU)
            # 返回一个匿名对象，调用parse_wrapper_to_table
            class WrapperParser:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_wrapper_to_table(data)
            return WrapperParser(self.hdlc_parser)
        elif self.current_protocol == 5:  # DLMS-APDU裸报文 (直接解析APDU)
            # 返回一个匿名对象，调用parse_apdu_to_table
            class APDUParser:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_apdu_to_table(data)
            return APDUParser(self.hdlc_parser)
        elif self.current_protocol == 6:  # DLT645-2007
            class DLT645GuiParser:
                def __init__(self, parser):
                    self.parser = parser
                def parse_to_table(self, data):
                    result = self.parser.parse(data)
                    table = []
                    # DLT645 帧结构计算字节范围
                    data_len = result.get('data_length', 0)
                    total_len = 10 + data_len + 2

                    for field, raw, desc in result['fields']:
                        byte_start = 0
                        byte_end = 0
                        parsed_value = ''

                        if '帧起始符 1' in field:
                            byte_start, byte_end = 0, 0
                        elif '从站地址' in field:
                            byte_start, byte_end = 1, 6
                        elif '帧起始符 2' in field:
                            byte_start, byte_end = 7, 7
                        elif '控制码' in field:
                            byte_start, byte_end = 8, 8
                            parsed_value = result.get('control_parsed', '')
                        elif '数据长度' in field:
                            byte_start, byte_end = 9, 9
                        elif '数据标识 DI' in field:
                            byte_start, byte_end = 10, 13
                            di_code = result.get('di_code', '')
                            di_desc = result.get('di_desc', '')
                            parsed_value = f"{di_code} ({di_desc})" if di_code and di_desc else di_code
                        elif '数据内容' in field:
                            byte_start, byte_end = 14, 10 + data_len - 1
                        elif '数据域' in field:
                            byte_start, byte_end = 10, 10 + data_len - 1
                        elif '校验和' in field:
                            byte_start, byte_end = total_len - 2, total_len - 2
                        elif '帧结束符' in field:
                            byte_start, byte_end = total_len - 1, total_len - 1

                        table.append((field, raw, parsed_value, desc, byte_start, byte_end))

                    return table
            return DLT645GuiParser(self.dlt645_parser)
        elif self.current_protocol == 7:  # 国网协议
            return self.gdw_parser
        elif self.current_protocol == 8:  # 698.45
            return self.dl_t698_45_parser
        elif self.current_protocol == 9:  # 新一代载波协议(通感一体化)
            # 包装解析器以传递解析级别参数
            csg_parser = self.csg_new_gen_parser
            parse_level = getattr(self, '_csg_parse_level', 'auto')
            class CSGGenGuiParser:
                def __init__(self, parser, level):
                    self.parser = parser
                    self.level = level
                def parse_to_table(self, data):
                    return self.parser.parse_to_table(data, parse_level=self.level)
            return CSGGenGuiParser(csg_parser, parse_level)
        elif self.current_protocol == 10:  # 国网新一代双模通信互联互通
            # 包装解析器以传递解析级别参数
            gw_parser = self.gw_new_gen_parser
            parse_level = getattr(self, '_gw_parse_level', 'auto')
            class GWGenGuiParser:
                def __init__(self, parser, level):
                    self.parser = parser
                    self.level = level
                def parse_to_table(self, data):
                    return self.parser.parse_to_table(data, parse_level=self.level)
            return GWGenGuiParser(gw_parser, parse_level)

    def load_example(self, data: str):
        """加载示例数据"""
        self.single_input.setText(data)

    @staticmethod
    def _clean_hex_input(text: str, keep_newlines: bool = False) -> str:
        """预处理报文输入：去除空格、逗号、换行等分隔符，支持0x前缀，仅保留十六进制字符

        支持的输入格式：
          - 纯 hex: 6811010101
          - 空格分隔: 68 11 01 01 01
          - 逗号分隔: 68,11,01,01,01
          - 混合分隔: 68, 11, 01 - 01. 01
          - 0x 前缀: 0x68 0x11 0x01 或 0x68,0x11,0x01
          - 换行分隔(多帧): 每行一帧
        """
        import re
        # 先处理 0x/0X 前缀：将 0x68 转为 68，避免 0x 被误清洗导致字节对齐错误
        text = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', text)
        pattern = r'[^0-9A-Fa-f\n]' if keep_newlines else r'[^0-9A-Fa-f]'
        return re.sub(pattern, '', text)

    # 新一代载波协议监控日志前缀标记与监控头长度
    # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <N字节监控头> <协议报文>"
    # 实际报文从标记后的第 16 个字节（1-based）开始，即需要跳过 15 字节监控头
    CSG_MONITOR_PREFIX = "-> 接收机 Has Get"
    CSG_MONITOR_HEADER_BYTES = 15  # 标记之后需跳过的监控头字节数

    def _strip_csg_monitor_prefix(self, text: str) -> str:
        """剥离新一代载波协议监控日志前缀（仅在协议8批量解析时调用）

        监控日志格式示例:
            15:49:51 254  -> 接收机 Has Get ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 68 11 01 01 ...
                                                      ^^^^^^^^^^^^^^^ 15字节监控头 ^^^^^^^^^^^^^^^^
                                                                                      ^ 第16字节(68)开始为真实协议报文

        处理规则（逐行）:
          1. 含 "-> 接收机 Has Get" 标记的行：定位标记，取其后内容，跳过前 15 字节
             (30 个 hex 字符) 监控头，从第 16 字节开始保留作为协议报文
          2. 不含标记的行：仅当该行整体为纯 hex 报文（允许空格/逗号/短横线分隔）时保留；
             含中文、时间戳、测试标记、# 等非 hex 内容的日志行直接丢弃，避免时间戳/文本被
             _clean_hex_input 误清洗成伪帧。

        注意：必须在 _clean_hex_input 之前调用，否则标记中的中文/箭头会被清洗掉，
        导致无法定位监控头边界。
        """
        import re
        prefix = self.CSG_MONITOR_PREFIX
        prefix_len = len(prefix)
        # 非监控前缀行允许的字符：hex 数字、空白、逗号、短横线
        hex_only_line_re = re.compile(r'^[0-9A-Fa-f\s,\-]*$')

        out_lines = []
        for line in text.splitlines():
            pos = line.find(prefix)
            if pos == -1:
                # 无监控前缀：仅保留看起来就是纯 hex 报文的行，过滤掉时间戳/中文/测试标记等日志行
                if hex_only_line_re.match(line):
                    out_lines.append(line)
                continue
            # 标记之后的内容
            after = line[pos + prefix_len:]
            # 提取连续 hex token（容忍空格/多空格/非hex分隔符）
            tokens = re.findall(r'[0-9A-Fa-f]{1,2}', after)
            # 跳过 15 字节监控头，从第 16 字节开始保留协议报文
            payload_tokens = tokens[self.CSG_MONITOR_HEADER_BYTES:]
            out_lines.append(' '.join(payload_tokens))
        return '\n'.join(out_lines)


    def parse_single(self):
        """解析单帧报文"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 清理输入（支持空格、逗号、换行等分隔符）
        clean_input = self._clean_hex_input(input_text)
        clean_input = clean_input.strip()

        # 验证输入
        if not all(c in '0123456789abcdefABCDEF' for c in clean_input):
            QMessageBox.critical(self, "错误", "输入包含非法字符，请只输入十六进制字符（0-9, A-F）！")
            return

        if len(clean_input) % 2 != 0:
            QMessageBox.critical(self, "错误", "输入长度为奇数，十六进制字符串必须是偶数长度！")
            return

        try:
            # 转换为字节
            frame_bytes = bytes.fromhex(clean_input)

            # 格式化为空格分隔的 hex，方便高亮
            hex_display = ' '.join(f'{b:02X}' for b in frame_bytes)
            self.single_input.setPlainText(hex_display)

            # 通感一体化协议：字节剔除（在解析前执行，支持缓存避免重复剔除）
            if self.current_protocol == 9:
                strip_head = self.csg_strip_head_spin.value()
                strip_tail = self.csg_strip_tail_spin.value()
                current_hex = clean_input.lower()
                # 如果当前输入与上次剔除后的结果相同，说明已经剔除过，跳过
                if (strip_head > 0 or strip_tail > 0) and current_hex != self._csg_last_stripped_hex:
                    total = len(frame_bytes)
                    tail_end = total - strip_tail if strip_tail > 0 else total
                    if strip_head >= tail_end:
                        QMessageBox.critical(self, "错误",
                            f"剔除字节数过多（前{strip_head}+尾{strip_tail}={strip_head+strip_tail}），"
                            f"报文仅{total}字节！")
                        return
                    frame_bytes = frame_bytes[strip_head:tail_end]
                    hex_display = ' '.join(f'{b:02X}' for b in frame_bytes)
                    self.single_input.setPlainText(hex_display)
                    # 缓存剔除后的hex（无空格小写），供下次比对
                    self._csg_last_stripped_hex = ''.join(f'{b:02x}' for b in frame_bytes)

            # 使用当前选中的解析器
            current_parser = self._get_current_parser()
            table_data = current_parser.parse_to_table(frame_bytes)
            self._populate_table_from_data(table_data)

            # 保存当前结果
            self.current_result = frame_bytes
            self._last_parsed_hex = hex_display

        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败：{str(e)}")

    def verify_single(self):
        """校验单帧报文的协议一致性"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 清理输入（支持空格、逗号、换行等分隔符）
        clean_input = self._clean_hex_input(input_text)
        clean_input = clean_input.strip()

        # 验证输入
        if not all(c in '0123456789abcdefABCDEF' for c in clean_input):
            QMessageBox.critical(self, "错误", "输入包含非法字符，请只输入十六进制字符（0-9, A-F）！")
            return

        if len(clean_input) % 2 != 0:
            QMessageBox.critical(self, "错误", "输入长度为奇数，十六进制字符串必须是偶数长度！")
            return

        try:
            frame_bytes = bytes.fromhex(clean_input)

            # 根据当前协议选择验证器
            from validator import NWValidator, GDWValidator, HDLCValidator, PLCRFValidator, DLT645Validator

            from validator.dl_t698_45_validator import DLT69845Validator
            from validator.csg_new_gen_validator import CSGNewGenValidator
            from validator.gw_new_gen_validator import GWNewGenValidator
            validators = {
                0: NWValidator(),      # 南网
                1: PLCRFValidator(),   # PLC RF
                2: HDLCValidator(),    # HDLC/国网DLMS
                3: HDLCValidator(),    # DLMS-APDU(国网)
                4: HDLCValidator(),    # Wrapper
                5: HDLCValidator(),    # APDU
                6: DLT645Validator(),  # DLT645
                7: GDWValidator(),     # 国网
                8: DLT69845Validator(), # 698.45
                9: CSGNewGenValidator(), # 新一代载波协议(通感一体化)
                10: GWNewGenValidator(), # 国网新一代双模通信互联互通
            }

            validator = validators.get(self.current_protocol)
            if validator:
                result = validator.verify(frame_bytes)
                self._display_verify_result(result)
            else:
                self.verify_label.setText("当前协议不支持校验")

        except Exception as e:
            QMessageBox.critical(self, "校验错误", f"校验失败：{str(e)}")

    def _display_verify_result(self, result):
        """显示校验结果"""
        from validator.base import CheckLevel

        lines = []
        lines.append(f"协议: {result.protocol}")
        lines.append(f"整体结果: {'✅ 通过' if result.valid else '❌ 失败'}")
        lines.append("")

        for check in result.checks:
            icon = "✅" if check.level == CheckLevel.PASS else "❌" if check.level == CheckLevel.FAIL else "⚠️"
            lines.append(f"{icon} {check.name}: {check.message}")

        if result.warnings:
            lines.append("")
            lines.append("⚠️ 警告:")
            for w in result.warnings:
                lines.append(f"  - {w}")

        if result.errors:
            lines.append("")
            lines.append("❌ 错误:")
            for e in result.errors:
                lines.append(f"  - {e}")

        self.verify_label.setText("\n".join(lines))

        # 设置颜色
        if result.valid:
            self.verify_group.setStyleSheet("QGroupBox { border: 2px solid #4CAF50; }")
        else:
            self.verify_group.setStyleSheet("QGroupBox { border: 2px solid #f44336; }")

    def _add_parsed_to_test_plan(self):
        """将当前解析的帧添加到测试方案"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请先解析报文！")
            return

        # 清理 HEX（支持空格、逗号、换行等分隔符）
        clean_hex = self._clean_hex_input(input_text)
        clean_hex = clean_hex.strip()

        if not clean_hex:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 根据协议生成名称
        protocol_names = {
            0: "南网", 1: "PLC RF", 2: "HDLC", 3: "Wrapper",
            4: "APDU", 5: "DLT645", 6: "国网", 7: "698.45"
        }
        protocol_name = protocol_names.get(self.current_protocol, "未知")
        name = f"{protocol_name}帧-{len(self.test_plan_tab._items) + 1}"

        # 添加到测试方案
        self.test_plan_tab.add_item(name, clean_hex)
        QMessageBox.information(self, "成功", f"已添加到测试方案: {name}")

    def _get_frame_bytes_for_fill(self):
        """获取当前输入框的帧字节，返回 (frame_bytes, hex_str) 或 None"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请先输入报文内容！")
            return None
        clean_input = self._clean_hex_input(input_text).strip()
        if not all(c in '0123456789abcdefABCDEF' for c in clean_input):
            QMessageBox.critical(self, "错误", "输入包含非法字符！")
            return None
        if len(clean_input) % 2 != 0:
            QMessageBox.critical(self, "错误", "输入长度必须为偶数！")
            return None
        return bytes.fromhex(clean_input), clean_input.upper()

    def _update_input_hex(self, frame_bytes: bytes):
        """将更新后的帧字节写回输入框"""
        hex_display = ' '.join(f'{b:02X}' for b in frame_bytes)
        self.single_input.setPlainText(hex_display)

    def _fill_crc24(self):
        """填充 CRC-24 校验位（FC FCS + eFC CRC）"""
        result = self._get_frame_bytes_for_fill()
        if result is None:
            return
        frame_bytes, hex_str = result
        frame_len = len(frame_bytes)

        if frame_len < 16:
            QMessageBox.warning(self, "警告", "帧长度不足 16 字节，无法填充 FC FCS！")
            return

        from csg_new_gen_parser import _crc24_func
        modified = bytearray(frame_bytes)
        filled = []

        # ── FC FCS: 字节0-12的CRC-24，写入字节13-15（小端序）──
        fc_crc = _crc24_func(bytes(modified[0:13]))
        modified[13] = fc_crc & 0xFF
        modified[14] = (fc_crc >> 8) & 0xFF
        modified[15] = (fc_crc >> 16) & 0xFF
        filled.append(f"FC FCS=0x{fc_crc:06X}(字节13-15)")

        # ── eFC CRC: 字节16-28的CRC-24，写入字节29-31（小端序）──
        # 判断是否为 SOF 帧且 OFDMA 需要 eFC
        if frame_len >= 32:
            # 检查定界符类型（字节0 bit0-2）
            delimiter_type = modified[0] & 0x07
            if delimiter_type == 1:  # SOF帧
                # 检查ISAC帧的multi_site位 (byte19 bit0)
                if modified[19] & 0x01:  # multi_site=1
                    # OFDMA type (byte19 bit1-2): type1不携带eFC
                    ofdma_type = (modified[19] >> 1) & 0x03
                    if ofdma_type != 1:
                        efc_crc = _crc24_func(bytes(modified[16:29]))
                        modified[29] = efc_crc & 0xFF
                        modified[30] = (efc_crc >> 8) & 0xFF
                        modified[31] = (efc_crc >> 16) & 0xFF
                        filled.append(f"eFC CRC=0x{efc_crc:06X}(字节29-31)")

        self._update_input_hex(bytes(modified))
        QMessageBox.information(self, "成功", "已填充: " + "\n".join(filled))

    def _fill_crc32(self):
        """填充 CRC-32 校验位（MAC 帧完整性校验）"""
        result = self._get_frame_bytes_for_fill()
        if result is None:
            return
        frame_bytes, hex_str = result
        frame_len = len(frame_bytes)

        if frame_len < 20:
            QMessageBox.warning(self, "警告", "帧长度不足，无法填充 CRC-32！")
            return

        from csg_new_gen_parser import _crc32_func
        modified = bytearray(frame_bytes)

        # 确定 MAC 帧的起始位置
        # 检查是否为完整 MPDU（FC头 + PB + MAC帧）
        delimiter_type = modified[0] & 0x07
        if delimiter_type == 1 and frame_len >= 24:
            # SOF帧: FC=16字节, PB头=4字节, MAC帧从字节20开始
            mac_start = 20
            # MAC头大小: 短头12字节(byte20 bit0=1), 长头32字节(byte20 bit0=0)
            mac_header_size = 12 if (modified[20] & 0x01) else 32
            # MSDU 长度字段: MAC bytes 2-3 (全局偏移 mac_start+2)
            if mac_start + 4 <= frame_len:
                msdu_len = int.from_bytes(modified[mac_start+2:mac_start+4], 'little')
            else:
                msdu_len = frame_len - mac_start - mac_header_size - 4
            msdu_start = mac_start + mac_header_size
            msdu_end = msdu_start + msdu_len
            crc_pos = msdu_end  # CRC-32 写入位置
        else:
            # 非MPDU格式: 假设整个帧就是一个 MAC 帧，最后4字节是CRC-32
            mac_start = 0
            mac_header_size = 12 if (modified[0] & 0x01) else 32
            if mac_start + 4 <= frame_len:
                msdu_len = int.from_bytes(modified[2:4], 'little')
            else:
                msdu_len = frame_len - mac_header_size - 4
            msdu_start = mac_start + mac_header_size
            msdu_end = msdu_start + msdu_len
            crc_pos = msdu_end

        # 确保 CRC 位置在帧内
        if crc_pos + 4 > frame_len:
            # 帧长度不够，将 CRC 放在帧末尾
            crc_pos = frame_len - 4
            msdu_end = crc_pos

        if msdu_end <= msdu_start:
            QMessageBox.warning(self, "警告", "MSDU 范围无效，无法计算 CRC-32！")
            return

        # 计算 CRC-32 (覆盖 MSDU 载荷，不包括 MAC 帧头)
        msdu_data = bytes(modified[msdu_start:msdu_end])
        crc_val = _crc32_func(msdu_data)

        # 写入 CRC-32 (小端序)
        modified[crc_pos]     = crc_val & 0xFF
        modified[crc_pos + 1] = (crc_val >> 8) & 0xFF
        modified[crc_pos + 2] = (crc_val >> 16) & 0xFF
        modified[crc_pos + 3] = (crc_val >> 24) & 0xFF

        self._update_input_hex(bytes(modified))
        QMessageBox.information(self, "成功",
            f"已填充 CRC-32=0x{crc_val:08X}\n"
            f"计算范围: MSDU载荷(字节{msdu_start}-{msdu_end-1}, {len(msdu_data)}字节)\n"
            f"写入位置: 字节{crc_pos}-{crc_pos+3}")

    def clear_single(self):
        """清空单帧解析输入和结果"""
        self.single_input.clear()
        self.result_table_widget.setRowCount(0)
        self.current_result = None
        self._byte_ranges = []
        # 清空校验结果
        if hasattr(self, 'verify_label'):
            self.verify_label.setText("点击「校验报文」按钮进行协议一致性校验")
        if hasattr(self, 'verify_group'):
            self.verify_group.setStyleSheet("")

    def export_single(self):
        """导出单帧解析结果"""
        if not hasattr(self, 'current_result') or not self.current_result:
            QMessageBox.warning(self, "警告", "没有可导出的解析结果！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存解析结果", "parse_result.txt", "文本文件 (*.txt)"
        )

        if file_path:
            try:
                # 使用当前选中的解析器
                current_parser = self._get_current_parser()
                table_data = current_parser.parse_to_table(self.current_result)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("字段\t原始值\t解析值\t说明\n")
                    for field_name, raw_value, parsed_value, comment, _, _ in table_data:
                        f.write(f"{field_name}\t{raw_value}\t{parsed_value}\t{comment}\n")
                QMessageBox.information(self, "成功", f"结果已保存到：{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败：{str(e)}")

    @staticmethod
    def _clear_layout(layout):
        """递归清除layout中的所有子layout和widget"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                MainWindow._clear_layout(child.layout())

    def _apply_chinese_menus_to_all_tabs(self):
        """为所有标签页中的文本输入控件设置中文右键菜单"""
        # 应用到主窗口及其所有子控件
        apply_chinese_context_menus(self)
        
        # 确保各个标签页中的控件也被处理
        if hasattr(self, 'single_input'):
            setup_chinese_context_menu(self.single_input)
        if hasattr(self, 'batch_input'):
            setup_chinese_context_menu(self.batch_input)
        if hasattr(self, 'frame_gen_tab'):
            apply_chinese_context_menus(self.frame_gen_tab)
        if hasattr(self, 'preset_tab'):
            apply_chinese_context_menus(self.preset_tab)

    def _setup_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 配置菜单
        config_menu = menubar.addMenu("配置(&C)")
        config_action = config_menu.addAction("配置文件路径(&P)...")
        config_action.triggered.connect(self._show_config_dialog)

        help_menu = menubar.addMenu("帮助(&H)")

        about_action = help_menu.addAction("关于(&A)")
        about_action.triggered.connect(self._show_about_dialog)

    def _show_about_dialog(self):
        """显示"关于"对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        dialog.setMinimumSize(520, 480)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        title_label = QLabel(f"协议解析工具")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"版本 2.0")
        version_label.setFont(QFont("Microsoft YaHei", 11))
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #666;")
        layout.addWidget(version_label)

        desc_label = QLabel("支持南网协议 / PLC RF / HDLC/DLMS 多协议报文解析")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        changelog_label = QLabel("版本更新记录")
        changelog_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        layout.addWidget(changelog_label)

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setFont(QFont("Microsoft YaHei", 9))

        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        html_parts = []
        html_parts.append(f"<b>v2.0 ({today})</b><ul>")
        html_parts.append("<li>优化界面布局，提高信息密度</li>")
        html_parts.append("<li>统一表格字体为7pt，行高压缩至13px</li>")
        html_parts.append("</ul>")
        html_parts.append("<b>v1.0</b><ul>")
        html_parts.append("<li>初始版本发布</li>")
        html_parts.append("<li>支持南网、PLC RF、HDLC/DLMS、DLT645协议</li>")
        html_parts.append("</ul>")

        changelog_text.setHtml("".join(html_parts))
        layout.addWidget(changelog_text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        dialog.exec()

    # ==================== 批量解析功能 ====================

    def load_from_file(self):
        """从文件加载报文列表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择报文文件", "", "文本文件 (*.txt *.csv *.log);;所有文件 (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                self.batch_input.setPlainText(content)
                frames = self._extract_frames(content)
                self.update_stats(f"已从文件加载，识别到 {len(frames)} 帧报文（点击\"开始批量解析\"执行）")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取文件失败：{str(e)}")

    def paste_from_clipboard(self):
        """从剪贴板粘贴"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.batch_input.setPlainText(text)
            frames = self._extract_frames(text)
            self.update_stats(f"已粘贴，识别到 {len(frames)} 帧报文（点击\"开始批量解析\"执行）")

    @staticmethod
    def _clear_layout(layout):
        """递归清除layout中的所有子layout和widget"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                MainWindow._clear_layout(child.layout())

    @staticmethod
    def _extract_frames(text: str) -> list:
        """从混杂文本中提取完整的68起始帧（南网协议）

        预处理规则：
        1. 剔除时间戳、特殊符号前缀（[]、<>等非hex字符）
        2. 从hex字符串中按68H起始、利用长度域+校验和验证帧完整性
        """
        import re
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()

        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find('68', i)
            if pos == -1:
                break

            if pos + 6 > len(clean):
                break

            try:
                low_byte = int(clean[pos + 2:pos + 4], 16)
                high_byte = int(clean[pos + 4:pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            if length < 8 or length > 2048:
                i = pos + 2
                continue

            frame_hex_len = length * 2
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos:pos + frame_hex_len]
            if candidate[-2:] != '16':
                i = pos + 2
                continue

            try:
                frame_bytes = bytes.fromhex(candidate)
                cs_expected = sum(frame_bytes[3:length - 1]) & 0xFF
                cs_actual = frame_bytes[length - 1]
                if cs_expected == cs_actual:
                    frames.append(candidate)
                    i = pos + frame_hex_len
                    continue
            except ValueError:
                pass

            i = pos + 2

        return frames

    def parse_batch(self):
        """批量解析 - 支持所有协议"""
        input_text = self.batch_input.toPlainText().strip()

        # 新一代载波协议(索引9)：先剥离监控日志前缀（在 hex 清洗前处理原始文本）
        # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>"
        # 需要先识别 "-> 接收机 Has Get" 标记，去除其后 15 字节监控头，再提取协议报文
        if self.current_protocol == 9:
            input_text = self._strip_csg_monitor_prefix(input_text)

        # 预处理：去除空格、逗号等分隔符，保留换行以区分多帧
        input_text = self._clean_hex_input(input_text, keep_newlines=True)

        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 根据当前协议选择帧提取方式
        frames = self._extract_frames_for_protocol(input_text, self.current_protocol)
        if not frames:
            QMessageBox.warning(self, "警告", f"未识别到有效帧！")
            return

        # 清空之前的结果
        self.batch_results = []
        self.result_table.setRowCount(0)

        success_count = 0
        fail_count = 0

        for i, frame_hex in enumerate(frames):
            table_data = []
            direction = "-"
            try:
                frame_bytes = bytes.fromhex(frame_hex)
                # 使用当前协议对应的解析器
                current_parser = self._get_current_parser()
                # 调用parse_to_table生成表格数据
                table_data = current_parser.parse_to_table(frame_bytes)

                # 南网协议/国网协议/698.45提取方向
                if self.current_protocol in (0, 7, 8):
                    direction = self._extract_direction_from_table(table_data)

                # 从表格数据生成摘要（取前3个字段作为摘要）
                summary = self._get_summary_from_table_data(table_data)

                # 检查解析是否失败（校验错误、长度不匹配等）
                is_parse_failed = any(item[0] == "❌ 解析失败" for item in table_data)
                if is_parse_failed:
                    status = "失败"
                    fail_count += 1
                    # 提取失败原因作为摘要
                    for item in table_data:
                        if item[0] == "❌ 解析失败":
                            summary = item[3] if item[3] else "解析失败"
                            break
                else:
                    status = "成功"
                    success_count += 1

                # 保存结果（表格数据可以在详情查看时使用）
                self.batch_results.append({
                    "_input": frame_hex,
                    "_status": status,
                    "_table_data": table_data,
                    "摘要": summary
                })

            except Exception as e:
                status = "异常"
                summary = str(e)[:50]
                fail_count += 1
                # 异常时 table_data 为空，方向保持 "-"
                self.batch_results.append({
                    "_input": frame_hex,
                    "_status": status,
                    "错误": str(e),
                    "摘要": summary
                })

            # 添加到表格
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem(str(i + 1)))

            hex_display = ' '.join(frame_hex[j:j+2] for j in range(0, len(frame_hex), 2))
            if len(hex_display) > 50:
                hex_display = hex_display[:50] + "..."
            self.result_table.setItem(row, 1, QTableWidgetItem(hex_display))
            self.result_table.setItem(row, 2, QTableWidgetItem(str(len(frame_hex) // 2)))

            # 方向：南网协议/国网协议/698.45从控制域DIR位解析，其他协议暂无
            direction = "-"
            if self.current_protocol in (0, 7, 8):
                direction = self._extract_direction_from_table(table_data)
            self.result_table.setItem(row, 3, QTableWidgetItem(direction))

            # 业务摘要
            self.result_table.setItem(row, 4, QTableWidgetItem(summary))

            # 状态
            status_item = QTableWidgetItem(status)
            if status == "成功":
                status_item.setForeground(Qt.darkGreen)
            else:
                status_item.setForeground(Qt.red)
            self.result_table.setItem(row, 5, status_item)

        self.update_stats(f"解析完成：成功 {success_count} 帧，失败 {fail_count} 帧，共 {len(frames)} 帧")

    def _extract_direction_from_table(self, table_data: list) -> str:
        """从南网/国网协议表格数据中提取传输方向"""
        # table_data 格式: (field_name, raw_value, parsed_value, comment, byte_start, byte_end)
        # 控制域子字段"传输方向"的 field_name 为"  传输方向"或"  传输方向(DIR)"（带前缀空格）
        for item in table_data:
            field_name = item[0]
            parsed_val = item[2]
            # 查找传输方向字段（去除空格后匹配）
            if "传输方向" in field_name or "DIR" in field_name:
                dir_code = str(parsed_val).strip()
                if dir_code == "0":
                    return "下行帧(集中器→模块)"
                elif dir_code == "1":
                    return "上行帧(模块→集中器)"
                else:
                    return f"未知({dir_code})"
        return "-"

    def _get_summary_from_table_data(self, table_data: list) -> str:
        """从表格数据中提取摘要信息，取重要的前几个字段拼接"""
        if not table_data:
            return "-"

        summary_parts = []

        if self.current_protocol == 0:
            # 南网协议：提取 AFN 名称（comment）、SEQ 值、DI 业务说明（comment）
            afn_val = None
            seq_val = None
            di_desc = None
            for item in table_data:
                field_name = item[0]
                parsed_val = item[2]
                comment = item[3]
                if field_name == "应用功能码 (AFN)":
                    # AFN 的 parsed_val 为空，说明在 comment 中
                    afn_val = comment if comment else parsed_val
                elif field_name == "帧序列号 (SEQ)":
                    seq_val = parsed_val
                elif field_name == "数据标识 (DI)":
                    # DI 的业务说明在 comment 中
                    if comment and not di_desc:
                        di_desc = comment
            if di_desc:
                summary_parts.insert(0, f"DI:{di_desc}")
            if afn_val is not None:
                summary_parts.append(f"AFN:{afn_val}")
            if seq_val is not None:
                summary_parts.append(f"SEQ:{seq_val}")
            return " | ".join(summary_parts) if summary_parts else "-"

        elif self.current_protocol == 7:
            # 国网协议：提取 AFN 名称、Fn 说明、传输方向
            afn_name = None
            fn_desc = None
            dir_desc = None
            for item in table_data:
                field_name = item[0]
                parsed_val = item[2]
                comment = item[3]
                if field_name == "应用功能码(AFN)":
                    afn_name = comment if comment else parsed_val
                elif field_name == "数据单元标识(DT)":
                    fn_desc = comment if comment else parsed_val
                elif "传输方向" in field_name:
                    dir_desc = "下行" if str(parsed_val).strip() == "0" else "上行" if str(parsed_val).strip() == "1" else "-"
            if dir_desc:
                summary_parts.append(dir_desc)
            if afn_name:
                summary_parts.append(f"AFN:{afn_name}")
            if fn_desc:
                summary_parts.append(fn_desc)
            return " | ".join(summary_parts) if summary_parts else "-"

        elif self.current_protocol == 8:
            # 698.45：提取 APDU 类型、DIR+PRM、功能码
            apdu_type = None
            dir_prm = None
            func_desc = None
            for item in table_data:
                field_name = item[0]
                parsed_val = item[2]
                comment = item[3]
                if field_name == "  APDU类型":
                    apdu_type = str(parsed_val) if parsed_val else comment
                elif field_name == "  DIR+PRM":
                    dir_prm = str(parsed_val) if parsed_val else comment
                elif field_name == "  功能码":
                    func_desc = str(parsed_val) if parsed_val else comment
            if dir_prm:
                summary_parts.append(dir_prm)
            if func_desc:
                summary_parts.append(func_desc)
            if apdu_type:
                summary_parts.append(apdu_type)
            return " | ".join(summary_parts) if summary_parts else "-"

        elif self.current_protocol == 9:
            # 新一代载波协议：区分网络层报文(MPDU/MAC/MMTYPE)与应用层报文(业务标识)
            return self._get_csg_new_gen_summary(table_data)

        else:
            # 其他协议：取前几个非冗余字段
            for i, item in enumerate(table_data):
                if i >= 4:
                    break
                field_name = item[0]
                parsed_val = item[2]
                if any(k in field_name for k in ["帧起始", "格式", "长度", "校验", "结束标志"]):
                    continue
                summary_parts.append(f"{parsed_val}")
            return " | ".join(summary_parts) if summary_parts else "-"

    def _get_csg_new_gen_summary(self, table_data: list) -> str:
        """新一代载波协议(索引9)批量解析摘要生成

        区分报文类型并优先使用 MSDU 类型作为顶层分类：
        - 含 "管理消息类型(MMTYPE)" → "<MSDU类型> | MMTYPE:..."
        - 含 "定界符类型" (MPDU/MAC 物理层帧) → "<MSDU类型> | <定界符> | 源/目的TEI"
        - 含 "业务标识" (应用层) → "<MSDU类型> | <帧类型> | 业务标识:... | 方向 | 核心内容"

        table_data 格式: (field_name, raw_value, parsed_value, comment, byte_start, byte_end)
        """
        if not table_data:
            return "-"

        # 解析失败：提取失败原因
        for item in table_data:
            if item[0].startswith("❌"):
                return item[3] if item[3] else "解析失败"

        # ── 字段索引：快速定位关键字段 ──
        fields = {item[0]: item for item in table_data}

        # ── 公共：MSDU 类型作为顶层分类（若存在）──
        msdu_type_prefix = ""
        if "MSDU类型" in fields:
            msdu_type_name = fields["MSDU类型"][3]  # 如 "应用层报文"/"网络管理消息"
            if msdu_type_name:
                msdu_type_prefix = msdu_type_name

        # ── 网络层：含 MMTYPE 字段（管理消息）──
        if "管理消息类型(MMTYPE)" in fields:
            mmtype_item = fields["管理消息类型(MMTYPE)"]
            mmtype_comment = mmtype_item[3]  # "管理消息: 关联请求(MMeAssocReq)"
            # 提取冒号后的消息名称
            mmtype_name = mmtype_comment.split(":", 1)[1].strip() if ":" in mmtype_comment else mmtype_comment
            prefix = msdu_type_prefix if msdu_type_prefix else "网络层"
            summary_parts = [f"{prefix} | MMTYPE:{mmtype_name}"]
            # 附带管理消息版本
            if "管理消息版本" in fields:
                ver = fields["管理消息版本"][2]
                summary_parts.append(f"版本{ver}")
            return " | ".join(summary_parts)

        # ── 网络层：MPDU/MAC 物理层帧（定界符类型字段）──
        if "定界符类型" in fields:
            delim_item = fields["定界符类型"]
            delim_desc = delim_item[3]  # "SOF帧" / "信标帧" / "选择确认帧(SACK)"
            prefix = msdu_type_prefix if msdu_type_prefix else "网络层"
            summary_parts = [f"{prefix} | {delim_desc}"]
            # 信标帧：额外显示信标类型（发现/代理/中央）
            if delim_desc == "信标帧" and "信标载荷头" in fields:
                beacon_head_item = fields["信标载荷头"]
                beacon_parsed = beacon_head_item[2]  # "类型:发现信标"
                if isinstance(beacon_parsed, str) and beacon_parsed.startswith("类型:"):
                    beacon_type = beacon_parsed[3:]
                    summary_parts.append(f"信标类型:{beacon_type}")
            # 附带源/目的TEI（若有）
            if "源TEI" in fields:
                summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
            if "目的TEI" in fields:
                summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
            return " | ".join(summary_parts)

        # ── 应用层报文：含业务标识字段 ──
        if "业务标识" in fields:
            summary_parts = [msdu_type_prefix if msdu_type_prefix else "应用层"]
            # 1. 帧类型域（业务大类）
            frame_type_item = fields.get("  帧类型域(D3~D0)")
            if frame_type_item:
                ft_comment = frame_type_item[3]  # "0 - 确认/否认"
                ft_name = ft_comment.split(" - ", 1)[1] if " - " in ft_comment else ft_comment
                summary_parts.append(ft_name)
            # 2. 业务标识（含描述）
            svc_item = fields["业务标识"]
            svc_comment = svc_item[3]  # "业务标识 0 - 确认"
            svc_desc = svc_comment.split(" - ", 1)[1] if " - " in svc_comment else svc_comment
            summary_parts.append(f"业务标识:{svc_desc}")
            # 3. 传输方向
            dir_item = fields.get("  传输方向位(D15)")
            if dir_item:
                dir_comment = dir_item[3]  # "0 - 下行(CCO→STA)"
                dir_name = dir_comment.split(" - ", 1)[1] if " - " in dir_comment else dir_comment
                summary_parts.append(dir_name)
            # 4. 核心内容：从业务数据单元子字段提取关键信息
            core = self._extract_csg_core_content(table_data)
            if core:
                summary_parts.append(core)
            return " | ".join(summary_parts)

        # ── 兜底：MSDU 负载等未分类报文，取前几个有效字段 ──
        parts = []
        for item in table_data[:4]:
            fn, pv, desc = item[0], item[2], item[3]
            if any(k in fn for k in ["帧起始", "格式", "长度", "校验", "结束"]):
                continue
            parts.append(str(desc) if desc else str(pv))
        return " | ".join(parts) if parts else "-"

    def _extract_csg_core_content(self, table_data: list) -> str:
        """从新一代载波协议应用层报文中提取核心业务内容（用于摘要）

        根据帧类型+业务标识组合，提取最有信息量的字段：
          - 确认/否认：否认原因码
          - 数据传输帧：源/目的地址 + 数据长度
          - 命令帧：目标设备地址 + 命令参数
          - 其他：取业务数据单元中首个有意义的字段
        """
        fields = {item[0]: item for item in table_data}

        # ── 获取帧类型和业务标识 ──
        ft_desc = fields.get("  帧类型域(D3~D0)", ("","","",""))[3]
        svc_desc = fields.get("业务标识", ("","","",""))[3]
        # 从 "业务标识 N - 名称" 中提取业务名
        svc_name = svc_desc.split(" - ", 1)[1] if " - " in svc_desc else svc_desc

        # ── 否认帧：显示否认原因 ──
        if "否认" in svc_name:
            deny_item = fields.get("否认原因码")
            if deny_item:
                return f"原因:{deny_item[3]}"
            return "否认"

        # ── 确认帧：显示确认状态 ──
        if "确认" in svc_name and "否认" not in svc_name:
            confirm_item = fields.get("确认/否认负载")
            if confirm_item:
                return confirm_item[3]  # "确认报文，无业务数据"
            return "确认"

        # ── 数据传输帧：源/目的地址 + 数据长度 ──
        if "数据传输" in ft_desc:
            parts = []
            src = fields.get("源地址")
            dst = fields.get("目的地址")
            if src:
                # 提取冒号后的实际地址值
                addr = src[3].split(": ", 1)[1] if ": " in src[3] else src[2]
                parts.append(f"源:{addr}")
            if dst:
                addr = dst[3].split(": ", 1)[1] if ": " in dst[3] else dst[2]
                parts.append(f"目的:{addr}")
            data_len = fields.get("转发数据长度")
            if data_len:
                parts.append(f"{data_len[2]}字节")
            return " | ".join(parts) if parts else svc_name

        # ── 命令帧：命令名 + 关键参数 ──
        if "命令" in ft_desc:
            parts = [svc_name]
            # 提取设备地址（若有）
            dev_addr = fields.get("设备地址")
            if dev_addr:
                addr = dev_addr[3].split(": ", 1)[1] if ": " in dev_addr[3] else dev_addr[2]
                parts.append(f"设备:{addr}")
            # 提取命令关键参数（非保留/非控制域的有意义字段）
            cmd_skip = {"帧类型域", "传输方向位", "启动标志", "响应标识", "业务扩展域",
                        "任务优先级", "保留", "业务标识", "帧序号", "帧长", "报文端口号",
                        "报文标识符", "应用版本号", "业务数据单元", "控制域"}
            for fn, item in fields.items():
                if fn.startswith("  "):
                    continue  # 跳过控制域位域子字段
                if any(k in fn for k in cmd_skip):
                    continue
                desc = item[3]
                val = item[2]
                if desc and "保留" not in desc and "默认" not in desc and "未解析" not in desc:
                    if val and str(val) != "0" and str(val) != "0字节":
                        # 避免与 svc_name 重复
                        if desc[:len(svc_name)] != svc_name:
                            parts.append(f"{desc[:30]}")
            return " | ".join(parts[:4])  # 最多4段

        # ── 兜底：取业务数据单元中首个有意义的字段 ──
        skip_keys = ["控制域", "传输方向", "启动标志", "响应标识", "业务扩展域标识",
                     "任务优先级", "保留(D", "帧类型域", "报文端口号", "报文标识符",
                     "应用版本号", "帧序号", "帧长", "业务标识", "保留",
                     "MSDU", "VLAN", "级联", "物理块", "MPDU", "MAC"]
        for fn, item in fields.items():
            if any(k in fn for k in skip_keys):
                continue
            desc = item[3]
            if not desc or desc in ("保留", "保留字段", "保留位默认填0"):
                continue
            if any(k in desc for k in ["未解析", "可能为填充", "尚未实现"]):
                continue
            if fn in ("业务数据单元", "确认/否认负载", "管理消息数据"):
                continue
            return f"{fn.strip()}:{desc[:30]}"
        return svc_name if svc_name else ""

    def _extract_frames_for_protocol(self, text: str, protocol_index: int) -> list:
        """根据协议提取对应格式的帧"""
        import re

        if protocol_index in (0, 7):
            # 南网协议 / 国网协议：68开头，16结束，FT1.2帧格式
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_68_frames(clean)
        elif protocol_index == 8:
            # 698.45：68开头，16结束，但长度域定义不同
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_69845_frames(clean)
        elif protocol_index == 1:
            # PLC RF协议：尝试通用提取
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_generic_frames(clean, min_len=4, max_len=256)
        elif protocol_index == 2:
            # HDLC/DLMS协议：7E开头，7E结束
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_hdlc_frames(clean)
        elif protocol_index == 3:
            # DLMS-APDU(国网)：按行分割，每行一帧
            return [f.strip() for f in text.splitlines() if f.strip()]
        elif protocol_index == 4:
            # DLMS Wrapper裸报文：识别Wrapper头部(8字节)并分割
            return self._extract_wrapper_frames(text)
        elif protocol_index == 5:
            # DLMS-APDU裸报文：按行分割，每行一帧
            return [f.strip() for f in text.splitlines() if f.strip()]
        elif protocol_index == 9:
            # 新一代载波协议(通感一体化)：按行提取，过滤无效短帧
            # 监控前缀已在 parse_batch 中通过 _strip_csg_monitor_prefix 剥离
            return self._extract_csg_new_gen_frames(text)
        else:
            # 通用：每行一帧
            return [f.strip() for f in text.splitlines() if f.strip()]

    def _extract_wrapper_frames(self, text: str) -> list:
        """
        从文本中提取Wrapper帧
        Wrapper格式: 版本(2B) + 源端口(2B) + 目的端口(2B) + 长度(2B) = 8字节头部
        版本固定为 0x0001
        支持处理带日志前缀的格式，如 "WRAPPER[1] Sent 0001000000010000003B ..."
        """
        import re
        frames = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # 提取连续的长串十六进制数据（至少16个字符）
            # 这样 WRAPPER 中的零散字母不会被误认为数据
            hex_matches = re.findall(r'[0-9A-Fa-f]{16,}', line)
            if not hex_matches:
                continue

            for hex_pattern in hex_matches:
                hex_pattern = hex_pattern.upper()

                # 扫描整个十六进制字符串，寻找Wrapper头部 (0001xxxx)
                i = 0
                while i <= len(hex_pattern) - 16:  # 至少需要8字节(16字符)头部
                    # 检查是否是Wrapper头部: 版本=0001
                    if hex_pattern[i:i+4] == '0001':
                        # 解析Wrapper头部的长度字段
                        apdu_len = int(hex_pattern[i+12:i+16], 16)

                        # 验证长度合理性（允许apdu_len=0，因为数据可能被截断）
                        if 0 <= apdu_len <= 8192:
                            # 计算完整帧长度: 8字节头部 + apdu_len
                            frame_len = 16 + apdu_len * 2

                            if i + frame_len <= len(hex_pattern):
                                # 提取完整帧
                                frame_hex = hex_pattern[i:i+frame_len]
                                frames.append(frame_hex)
                                i += frame_len
                                continue
                            else:
                                # 数据被截断，但仍提取可用的头部+部分数据
                                frame_hex = hex_pattern[i:]
                                frames.append(frame_hex)
                                break
                    i += 2

        return frames if frames else [re.sub(r'[^0-9A-Fa-f]', '', text).upper()]

    def _extract_hdlc_frames(self, clean: str) -> list:
        """提取HDLC帧（7E开头，7E结束）"""
        frames = []
        i = 0
        while i < len(clean) - 3:
            # 找下一个7E起始
            pos = clean.find('7E', i)
            if pos == -1:
                break
            # 找下一个7E结束
            end = clean.find('7E', pos + 2)
            if end == -1:
                # 如果没找到结束，直接取到结尾或者最大长度
                end = min(pos + 512, len(clean))
            candidate = clean[pos:end + 2]
            if len(candidate) >= 6:  # 至少3字节
                frames.append(candidate)
            i = end + 2
        return frames

    def _extract_68_frames(self, clean: str) -> list:
        """提取南网68格式帧（Q/CSG1209021-2019 FT1.2）

        帧格式: 68H | L(2B小端) | C(1B) | 用户数据(L-6字节) | CS(1B) | 16H
        L = 帧总字节数（含起始符、长度域、控制域、校验和、结束符）
        验证规则:
          1. 起始字符 = 68H
          2. L >= 8（最小帧长度）
          3. 帧末尾 = 16H
          4. 校验和：从控制域到用户数据末尾的所有字节累加和 mod 256
        """
        frames = []
        i = 0
        while i < len(clean) - 7:
            # 找下一个 68 起始
            pos = clean.find('68', i)
            if pos == -1:
                break

            # 尝试按长度域解析帧边界
            if pos + 6 > len(clean):
                i = pos + 2
                continue

            try:
                low_byte = int(clean[pos + 2:pos + 4], 16)
                high_byte = int(clean[pos + 4:pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            # L 至少为 8（起始1 + 长度2 + 控制1 + 校验1 + 结束1 + 用户数据至少3）
            if length < 8 or length > 2048:
                i = pos + 2
                continue

            frame_hex_len = length * 2

            # 检查数据是否足够
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos:pos + frame_hex_len]

            # 验证结束符 = 16H
            if candidate[-2:] != '16':
                i = pos + 2
                continue

            # 通过长度域和结束符验证，接受此帧（不校验CS，由解析器负责校验）
            frames.append(candidate)
            i = pos + frame_hex_len
            continue

        return frames

    def _extract_69845_frames(self, clean: str) -> list:
        """提取698.45格式帧（DL/T 698.45-2017）

        帧格式: 68H | L(2B小端) | C(1B) | SA | CA | HCS(2B) | APDU | FCS(2B) | 16H
        L = 控制域 + 地址域 + 链路用户数据的长度（不含68、LL、16）
        帧总长度 = 1(68) + 2(LL) + L + 1(16) = L + 4
        验证规则:
          1. 起始字符 = 68H
          2. L >= 8（最小有效长度）
          3. 帧末尾 = 16H
          4. 长度域一致性: 实际帧长 = L + 4
        """
        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find('68', i)
            if pos == -1:
                break

            if pos + 6 > len(clean):
                i = pos + 2
                continue

            try:
                low_byte = int(clean[pos + 2:pos + 4], 16)
                high_byte = int(clean[pos + 4:pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            # L 至少为 8（控制1 + SA至少1 + CA1 + HCS2 + FCS2 + APDU至少1）
            if length < 8 or length > 2048:
                i = pos + 2
                continue

            # 698.45: 帧总长度 = L + 4
            total_len = length + 4
            frame_hex_len = total_len * 2

            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos:pos + frame_hex_len]

            # 验证结束符 = 16H
            if candidate[-2:] != '16':
                i = pos + 2
                continue

            frames.append(candidate)
            i = pos + frame_hex_len
            continue

        return frames

    def _extract_generic_frames(self, clean: str, min_len: int = 4, max_len: int = 512) -> list:
        """通用帧提取：按行或直接提取完整有效hex字符串"""
        if len(clean) >= min_len * 2 and len(clean) <= max_len * 2:
            return [clean] if len(clean) % 2 == 0 else []
        return []

    def _extract_csg_new_gen_frames(self, text: str) -> list:
        """提取新一代载波协议帧

        输入 text 已经过 _clean_hex_input(keep_newlines=True) 清洗，
        且监控前缀已在 parse_batch 中剥离，此处为纯 hex 字符串（含换行）。

        处理规则:
          - 按行分割（每行一帧，兼容多帧批量输入）
          - 去除空白后只保留偶数长度的有效 hex 行
          - 过滤过短的行（< 4 字节，无法构成最小应用层报文）
        """
        frames = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # 仅保留 hex 字符（清洗后应已是纯 hex，此处兜底）
            clean_line = ''.join(c for c in line if c in '0123456789ABCDEFabcdef').upper()
            if len(clean_line) < 8:  # 至少 4 字节
                continue
            if len(clean_line) % 2 != 0:
                # 奇数长度：丢弃末尾字符以保证字节对齐
                clean_line = clean_line[:-1]
            frames.append(clean_line)
        return frames

    def clear_batch(self):
        """清空批量解析内容"""
        self.batch_input.clear()
        self.result_table.setRowCount(0)
        self.batch_results = []
        self.update_stats("待解析")

    def export_batch(self):
        """增强版批量解析结果导出 - 支持 JSON/Excel 多格式，Excel 含 Sheet2 详细解析"""
        if not self.batch_results:
            QMessageBox.warning(self, "警告", "没有可导出的解析结果！")
            return

        # 获取协议名称
        protocol_names = [
            "南网协议", "PLC_RF协议", "HDLC协议", "DLMS_APDU",
            "DLMS_Wrapper", "DLMS_APDU", "DLT645协议",
            "国网协议", "698.45协议", "新一代载波协议"
        ]
        protocol_name = protocol_names[self.current_protocol] if self.current_protocol < len(protocol_names) else f"协议{self.current_protocol}"

        # 创建导出器
        exporter = EnhancedBatchResultExporter()

        # 显示导出选项对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox
        from PySide6.QtWidgets import QLabel, QRadioButton, QPushButton, QLineEdit, QFileDialog
        from PySide6.QtCore import Qt

        dialog = QDialog(self)
        dialog.setWindowTitle("批量解析导出")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel(f"导出协议: {protocol_name}  |  共 {len(self.batch_results)} 条结果")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #2196F3;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 格式选择
        layout.addWidget(QLabel("选择导出格式:"))

        excel_radio = QRadioButton("Excel 格式（Sheet1 汇总 + Sheet2 每帧详细解析）")
        excel_radio.setChecked(True)
        layout.addWidget(excel_radio)

        json_radio = QRadioButton("JSON 格式（完整数据 + 元数据）")
        layout.addWidget(json_radio)

        # Excel 已打包进 exe，直接启用
        excel_radio.setEnabled(True)

        # 说明
        info_label = QLabel("Excel 导出包含两个工作表：\n  Sheet1「汇总表」- 帧序号/状态/摘要\n  Sheet2「详细解析」- 每帧所有字段逐行展开")
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 文件路径选择
        layout.addWidget(QLabel("输出路径:"))

        path_layout = QHBoxLayout()
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("选择导出文件保存位置...")
        path_layout.addWidget(path_edit)

        browse_btn = QPushButton("浏览...")
        browse_btn.setMaximumWidth(80)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # 浏览按钮点击事件
        def browse_path():
            if excel_radio.isChecked():
                default_name = f"batch_parse_{protocol_name}.xlsx"
                filter_str = "Excel 文件 (*.xlsx);;所有文件 (*)"
            else:
                default_name = f"batch_parse_{protocol_name}.json"
                filter_str = "JSON 文件 (*.json);;所有文件 (*)"

            file_path, _ = QFileDialog.getSaveFileName(
                self, "选择导出位置", default_name, filter_str
            )
            if file_path:
                path_edit.setText(file_path)

        browse_btn.clicked.connect(browse_path)

        # 格式切换时更新默认文件名
        def update_default_name():
            if excel_radio.isChecked():
                default_name = f"batch_parse_{protocol_name}.xlsx"
            else:
                default_name = f"batch_parse_{protocol_name}.json"
            path_edit.setText(default_name)

        excel_radio.toggled.connect(update_default_name)
        json_radio.toggled.connect(update_default_name)

        # 初始化默认路径
        update_default_name()

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("导出")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")

        def do_export():
            try:
                file_path = path_edit.text().strip()
                if not file_path:
                    QMessageBox.warning(self, "警告", "请选择导出路径！")
                    return

                # 获取导出目录和文件名
                export_dir = str(Path(file_path).parent)
                file_name = Path(file_path).stem

                # 创建导出器，指定导出目录
                exporter = EnhancedBatchResultExporter(export_dir)

                if excel_radio.isChecked():
                    # Excel 导出需要完整的文件路径
                    result_path = exporter.export_to_excel(
                        self.batch_results, protocol_name,
                        output_file=file_path
                    )
                else:
                    result_path = exporter.export_to_json(
                        self.batch_results, protocol_name,
                        output_file=file_path
                    )

                QMessageBox.information(self, "导出成功", f"结果已保存到:\n{result_path}")
                dialog.accept()
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))

        button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(do_export)
        button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec()

    def show_detail_dialog(self, row, col):
        """单击列表行时弹出详细解析窗口（表格形式）"""
        if row < 0 or row >= len(self.batch_results):
            return

        result = self.batch_results[row]

        dialog = QDialog(self)
        dialog.setWindowTitle(f"解析详情 - 第 {row + 1} 帧")
        dialog.setMinimumSize(800, 500)

        layout = QVBoxLayout(dialog)

        # 原始数据
        raw_hex = result.get("_input", result.get("原始数据", ""))
        if raw_hex:
            hex_display = ' '.join(raw_hex[j:j+2] for j in range(0, len(raw_hex), 2))
            raw_label = QLabel(f"原始报文：{hex_display}")
            raw_label.setFont(QFont("Consolas", 10))
            raw_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            raw_label.setWordWrap(True)
            layout.addWidget(raw_label)

        # 用表格显示解析结果
        if "_input" in result and result.get("_status") != "异常":
            try:
                # 优先使用批量解析时已保存的表格数据
                if "_table_data" in result:
                    table_data = result["_table_data"]
                else:
                    # 否则重新用当前协议解析器解析
                    frame_bytes = bytes.fromhex(result["_input"])
                    current_parser = self._get_current_parser()
                    table_data = current_parser.parse_to_table(frame_bytes)

                detail_table = QTableWidget()
                detail_table.setColumnCount(4)
                detail_table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
                header = detail_table.horizontalHeader()
                header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                header.setStretchLastSection(True)
                detail_table.setColumnWidth(0, 160)
                detail_table.setColumnWidth(1, 120)
                detail_table.setColumnWidth(2, 180)
                detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
                detail_table.setSelectionBehavior(QTableWidget.SelectRows)
                detail_table.setAlternatingRowColors(True)
                detail_table.verticalHeader().hide()
                detail_table.verticalHeader().setDefaultSectionSize(20)
                table_font = QFont()
                table_font.setPointSize(8)
                detail_table.setFont(table_font)

                detail_table.setRowCount(len(table_data))
                for r, item in enumerate(table_data):
                    detail_table.setItem(r, 0, QTableWidgetItem(str(item[0])))
                    detail_table.setItem(r, 1, QTableWidgetItem(str(item[1])))
                    detail_table.setItem(r, 2, QTableWidgetItem(str(item[2])))
                    detail_table.setItem(r, 3, QTableWidgetItem(str(item[3])))

                layout.addWidget(detail_table)
            except Exception:
                # 回退到JSON显示
                text_edit = QTextEdit()
                text_edit.setReadOnly(True)
                text_edit.setFont(QFont("Consolas", 10))
                text_edit.setText(json.dumps(result, ensure_ascii=False, indent=2))
                layout.addWidget(text_edit)
        else:
            # 异常帧，显示错误信息
            error_text = result.get("错误", json.dumps(result, ensure_ascii=False, indent=2))
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont("Consolas", 10))
            text_edit.setText(error_text)
            layout.addWidget(text_edit)

        dialog.exec()

    def update_stats(self, text: str):
        """更新状态标签"""
        self.stats_label.setText(f"状态：{text}")
    
    # ==================== 表格结果填充与字节高亮 ====================

    def _populate_table_from_data(self, table_data: list):
        """从解析器生成的表格数据填充表格（6元组：含字节范围）"""
        self.result_table_widget.setRowCount(0)
        self._byte_ranges = []

        for row, item in enumerate(table_data):
            field_name, raw_value, parsed_value, comment = item[0], item[1], item[2], item[3]
            byte_start = item[4] if len(item) > 4 else None
            byte_end = item[5] if len(item) > 5 else None

            self.result_table_widget.insertRow(row)
            self.result_table_widget.setItem(row, 0, QTableWidgetItem(field_name))
            self.result_table_widget.setItem(row, 1, QTableWidgetItem(str(raw_value)))
            self.result_table_widget.setItem(row, 2, QTableWidgetItem(str(parsed_value)))
            self.result_table_widget.setItem(row, 3, QTableWidgetItem(str(comment)))
            self._byte_ranges.append((byte_start, byte_end))

    def _highlight_bytes(self, row: int, col: int, prev_row: int, prev_col: int):
        """选中表格行时，高亮输入框中对应的报文字节"""
        if not self._byte_ranges:
            return

        doc = self.single_input.document()
        cursor = QTextCursor(doc)

        # 先清除所有高亮，恢复默认格式
        cursor.select(QTextCursor.SelectionType.Document)
        default_fmt = QTextCharFormat()
        default_fmt.setFontFamily("Consolas, Monaco, monospace")
        default_fmt.setForeground(QColor("#000000"))
        default_fmt.setBackground(QColor("#FFFFFF"))
        cursor.setCharFormat(default_fmt)

        # 检查行有效性
        if row < 0 or row >= len(self._byte_ranges):
            return

        byte_start, byte_end = self._byte_ranges[row]
        if byte_start is None or byte_end is None:
            return

        # 在 "XX XX XX ..." 格式中，第 i 个字节对应字符位置 i*3 ~ i*3+1
        char_start = byte_start * 3
        char_end = byte_end * 3 + 2

        # 边界保护
        text_len = len(self.single_input.toPlainText())
        if char_end > text_len:
            char_end = text_len

        # 选中对应字符，应用高亮
        highlight_cursor = QTextCursor(doc)
        highlight_cursor.setPosition(char_start)
        highlight_cursor.setPosition(char_end, QTextCursor.MoveMode.KeepAnchor)

        hl_fmt = QTextCharFormat()
        hl_fmt.setFontFamily("Consolas, Monaco, monospace")
        hl_fmt.setForeground(QColor("#000000"))
        hl_fmt.setBackground(QColor(255, 235, 59, 160))  # 黄色半透明高亮
        highlight_cursor.setCharFormat(hl_fmt)

    def _extract_apdu_reparse(self, index):
        """双击表格行时，提取该行对应字节范围，弹窗深度解析DLMS-APDU"""
        row = index.row()
        if not self._byte_ranges or row < 0 or row >= len(self._byte_ranges):
            return

        byte_start, byte_end = self._byte_ranges[row]
        if byte_start is None or byte_end is None:
            return

        # 获取完整原始报文（从输入框解析得到）
        if not hasattr(self, 'current_result'):
            QMessageBox.information(self, "提示", "无法获取原始报文数据，请先解析")
            return

        full_bytes = self.current_result
        # 提取对应范围字节（byte_end 包含在内）
        extracted_bytes = full_bytes[byte_start : byte_end + 1]

        if len(extracted_bytes) == 0:
            QMessageBox.information(self, "提示", "选中区域字节为空")
            return

        # 自动识别协议类型
        extracted_bytes = bytes(extracted_bytes)
        dialog_title = ""
        try:
            # 先检测是否是DLT645协议帧
            if len(extracted_bytes) >=12 and extracted_bytes[0] == 0x68 and extracted_bytes[7] == 0x68 and extracted_bytes[-1] == 0x16:
                # DLT645协议
                result = self.dlt645_parser.parse(extracted_bytes)
                parsed_data = []
                for field, raw, desc in result['fields']:
                    parsed_data.append((field, raw, '', desc, 0, 0))
                dialog_title = f"深度解析DLT645-2007 (提取 {len(extracted_bytes)} 字节)"
            else:
                # 默认DLMS APDU协议
                parsed_data = self.hdlc_parser.parse_apdu_to_table(extracted_bytes)
                dialog_title = f"深度解析DLMS-APDU (提取 {len(extracted_bytes)} 字节)"
        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败:\n{str(e)}")
            return

        # 创建弹窗显示解析结果
        dialog = QDialog(self)
        dialog.setWindowTitle(dialog_title)
        dialog.resize(900, 600)

        layout = QVBoxLayout(dialog)

        # 显示提取的十六进制
        hex_text = QTextEdit()
        hex_text.setReadOnly(True)
        hex_text.setFont(QFont("Consolas", 10))
        hex_text.setMaximumHeight(80)
        hex_str = ' '.join(f'{b:02X}' for b in extracted_bytes)
        hex_text.setText(f"提取字节: {hex_str}")
        layout.addWidget(hex_text)

        # 解析结果表格
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["字段", "十六进制", "解析值", "说明"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        table.setColumnWidth(0, 160)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 180)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(20)
        table_font = QFont()
        table_font.setPointSize(8)
        table.setFont(table_font)

        for r, item in enumerate(parsed_data):
            field_name = item[0]
            raw_hex = item[1]
            parsed_val = str(item[2])
            comment = item[3]
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(field_name))
            table.setItem(r, 1, QTableWidgetItem(raw_hex))
            table.setItem(r, 2, QTableWidgetItem(parsed_val))
            table.setItem(r, 3, QTableWidgetItem(comment))

        layout.addWidget(table)
        dialog.setLayout(layout)
        dialog.exec()

    # ==================== 串口配置与持久化 ====================

    def _load_serial_config(self):
        """从 config.json 加载串口配置"""
        config_path = Path(__file__).parent / "config.json"
        if not config_path.exists():
            return
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            serial_config = config.get("serial", {})
            port = serial_config.get("port", "")
            baud = serial_config.get("baudrate", "9600")
            parity = serial_config.get("parity", "无")

            # 应用配置（仅当值有效时）
            if port:
                idx = self.serial_port_combo.findText(port)
                if idx >= 0:
                    self.serial_port_combo.setCurrentIndex(idx)
            if baud:
                self.serial_baud_combo.setCurrentText(str(baud))
            if parity:
                self.serial_parity_combo.setCurrentText(parity)
        except Exception:
            pass

    def _resolve_config_path(self, raw: str) -> Path:
        """将配置文件路径字符串解析为绝对 Path"""
        p = Path(raw)
        if p.is_absolute():
            return p
        return Path(__file__).parent / p

    def _load_app_config(self):
        """加载应用配置（串口 + 文件路径）"""
        if not self._config_path.exists():
            self._app_config = {}
            self._file_paths = {}
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._app_config = json.load(f)
        except Exception:
            self._app_config = {}

        paths = self._app_config.get("file_paths", {})
        self._file_paths = {}
        for key, val in paths.items():
            if val:
                self._file_paths[key] = self._resolve_config_path(val)

    def _save_app_config(self):
        """保存应用配置到 config.json"""
        config: Dict[str, Any] = {}
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}

        # 更新串口配置
        config["serial"] = {
            "port": self.serial_port_combo.currentText(),
            "baudrate": self.serial_baud_combo.currentText(),
            "parity": self.serial_parity_combo.currentText(),
        }

        # 更新文件路径配置
        file_paths: Dict[str, str] = {}
        for key, path in self._file_paths.items():
            if path:
                try:
                    rel = path.relative_to(Path(__file__).parent)
                    file_paths[key] = str(rel)
                except ValueError:
                    file_paths[key] = str(path)
        config["file_paths"] = file_paths

        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[配置保存失败] {e}")

    def _show_config_dialog(self):
        """显示配置路径管理对话框"""
        # 构建当前路径字典（字符串形式传给对话框）
        current_paths: Dict[str, str] = {}
        for key, path in self._file_paths.items():
            if path:
                try:
                    rel = path.relative_to(Path(__file__).parent)
                    current_paths[key] = str(rel)
                except ValueError:
                    current_paths[key] = str(path)

        dialog = ConfigDialog(current_paths, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_paths = dialog.get_file_paths()
        self._file_paths = {}
        for key, val in new_paths.items():
            if val:
                self._file_paths[key] = self._resolve_config_path(val)

        # 保存到 config.json
        self._save_app_config()

        # 动态刷新各页面
        self.preset_tab.set_file_paths(
            nw_path=self._file_paths.get("nw_command"),
            gw_path=self._file_paths.get("gw_command"),
        )
        self.test_plan_tab.set_file_path(self._file_paths.get("test_plan"))

        QMessageBox.information(self, "配置", "配置文件路径已更新并保存。")

    def _save_serial_config(self):
        """保存串口配置到 config.json（保留现有 file_paths）"""
        self._save_app_config()

    def _refresh_serial_ports(self):
        """刷新可用串口列表"""
        from serial_worker import SerialWorker
        current = self.serial_port_combo.currentText()
        self.serial_port_combo.clear()
        ports = SerialWorker.list_ports()
        for p in ports:
            self.serial_port_combo.addItem(p)
        # 恢复之前选中的端口（如果仍在列表中）
        if current:
            idx = self.serial_port_combo.findText(current)
            if idx >= 0:
                self.serial_port_combo.setCurrentIndex(idx)

    def _on_serial_open_clicked(self):
        """打开/关闭串口按钮点击"""
        if self.serial_worker.is_open():
            self.serial_worker.close_port()
            self.serial_open_btn.setText("打开串口")
            self.serial_open_btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
                "QPushButton:disabled { background-color: #cccccc; }"
            )
            self.serial_port_combo.setEnabled(True)
            self.serial_baud_combo.setEnabled(True)
            self.serial_parity_combo.setEnabled(True)
            self.serial_status_label.setText("未连接")
            self.serial_status_label.setStyleSheet("color: #999; font-size: 12px;")
            self._save_serial_config()
        else:
            port = self.serial_port_combo.currentText()
            if not port:
                QMessageBox.warning(self, "警告", "请先选择串口端口")
                return
            baud = int(self.serial_baud_combo.currentText())
            parity = self.serial_parity_combo.currentText()
            self.serial_worker.configure(port, baudrate=baud, parity=parity)
            if self.serial_worker.open_port():
                self.serial_open_btn.setText("关闭串口")
                self.serial_open_btn.setStyleSheet(
                    "QPushButton { background-color: #f44336; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
                    "QPushButton:disabled { background-color: #cccccc; }"
                )
                self.serial_port_combo.setEnabled(False)
                self.serial_baud_combo.setEnabled(False)
                self.serial_parity_combo.setEnabled(False)
                self.serial_status_label.setText("已连接")
                self.serial_status_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
                self._save_serial_config()

    def _on_serial_connection_changed(self, connected: bool):
        """串口连接状态变化回调"""
        if not connected and self.serial_open_btn.text() == "关闭串口":
            # 被动断开（如设备拔出）
            self.serial_open_btn.setText("打开串口")
            self.serial_open_btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 12px; font-weight: bold; }"
                "QPushButton:disabled { background-color: #cccccc; }"
            )
            self.serial_port_combo.setEnabled(True)
            self.serial_baud_combo.setEnabled(True)
            self.serial_parity_combo.setEnabled(True)
            self.serial_status_label.setText("未连接")
            self.serial_status_label.setStyleSheet("color: #999; font-size: 12px;")

    def _on_serial_error(self, msg: str):
        """串口错误回调"""
        self.serial_status_label.setText(f"错误: {msg}")
        self.serial_status_label.setStyleSheet("color: #f44336; font-size: 12px;")


def main():
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle('Fusion')

    # 设置字体
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    # 全局复选框样式：白色背景 + 黑色边框，确保在浅色主题下清晰可见
    app.setStyleSheet("""
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid black;
            background-color: white;
        }
        QCheckBox::indicator:checked {
            background-color: #2196F3;
            border: 1px solid black;
        }
        QCheckBox::indicator:indeterminate {
            background-color: #90CAF9;
            border: 1px solid black;
        }
    """)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
