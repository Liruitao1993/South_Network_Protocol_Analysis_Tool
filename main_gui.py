import pathlib
"""
南网协议解析工具 - PySide6 GUI版
简洁界面，支持单帧解析和批量解析
"""

import sys
import os

# 在导入 PySide6 之前屏蔽 Qt DirectWrite 字体回退警告（无害噪音）
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QSplitter, QGroupBox, QDialog, QTabWidget, QComboBox,
    QListView, QFrame, QMenuBar, QSpinBox, QCheckBox, QMenu, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QObject
from PySide6.QtWidgets import QStyle
from PySide6.QtGui import QFont, QTextCursor, QTextCharFormat, QColor, QIcon, QKeySequence, QShortcut, QGuiApplication

from protocol_parser import ProtocolFrameParser
from plc_rf_parser import PLCRFProtocolParser
from hdlc_parser import HDLCParser
from dlt645_parser import DLT645Parser
from gdw10376_parser import GDW10376Parser
from dl_t698_45_parser import DLT69845Parser
from csg_new_gen_parser import CSGNewGenParser
from gw_new_gen_parser import GWNewGenParser
from hdc10_parser import HDC10Parser
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
from monitor_widget import RealtimeMonitorWidget
from monitor.tcp_monitor import TCPMonitorWidget
from system_integration.sys_tray import SystemTrayManager
from system_integration.global_hotkey import GlobalHotkeyManager
from system_integration.single_instance import SingleInstanceServer
from system_integration.registry_menu import get_exe_path
from system_integration.clipboard_monitor import ClipboardMonitor, detect_protocol
from system_integration.parse_prompt_dialog import ParsePromptDialog
from message_tool_widget import MessageToolWidget
from serial_worker import SerialWorker
from gui_utils import apply_chinese_context_menus, setup_chinese_context_menu
from enhanced_export import EnhancedBatchResultExporter
from theme_settings import ThemeManager, ThemeSettingsDialog
from llm_preprocess_widget import LLMPreprocessWidget
from llm_api_manager import LLMApiManagerDialog
from preprocessors import list_scripts as _list_pp_scripts, get_script as _get_pp_script


APP_VERSION = "1.12.0"
BUILD_DATE = "2026-08-12"  # 编译日期，每次打包前更新

CHANGELOG = [
    ("1.12.0", "2026-08-04", [
        "新增 LLM 智能预处理功能：批量解析标签页新增可折叠 LLM 预处理面板，支持通过 OpenAI 兼容 API 对原始日志进行多轮智能清洗后再解析",
        "内置 5 个 prompt 模板：提取 hex 帧、清理前缀、提取 TCP 报文、按协议分类、修复 hex 格式",
        "大文件自动分块（默认 200 行/块），异步调用不阻塞 GUI",
        "API 配置持久化到 config.json 的 llm 段，支持测试连接",
        "新增 llm_preprocess.py（API 客户端 + 分块器 + 异步 Worker）和 llm_preprocess_widget.py（预处理面板 UI）",
        "新增通用文本预处理工具 pp_cli.py：管道式命令链（find/excluding/replace/head/tail/skip/hex_extract/dedup），支持正则，可独立 CLI 或 GUI 内嵌使用",
        "批量解析标签页工具栏新增「预处理」命令输入框 +「执行」按钮 +「?」帮助按钮，输入命令链后对输入框内容执行预处理并回填结果",
    ]),
    ("1.11.1", "2026-08-04", [
        "修复勾选「ED监控协议」后不完整/非法 ED..EE 帧被静默回退为 FC 起始解析的 bug：单帧解析、解析弹窗、批量解析三处路径在 ED 头剥离失败时均明确报错（报文不完整/缺 EF 或 EE），首字节 ED 不再被当作南网新一代 FC 起始符",
        "新增 test_ed_fallback_fix.py（14 用例，覆盖单帧/弹窗/批量三条路径的失败报错与完整 ED 帧回归）",
    ]),
    ("1.11.0", "2026-08-01", [
        "新一代载波协议(通感一体化,索引9)网间协调帧(NET,定界符类型=3)可变区域解析：邻居网络比特图1~4 / 本网络无线信道编号 / 持续时间(40ms) / 带宽结束标志位 / 本网络无线option / 带宽结束偏移(4ms) / 带宽开始偏移(4ms)，字节12短网络标识高位组合完整SNID",
        "新一代载波协议聚合帧(物理块聚合标志=1)级联块应用层解析：抽取 _parse_msdu_payload 共享方法，级联块内 MAC 帧解析 MSDU 头(VLAN/MSDU类型)并按类型分派应用层报文(端口/控制域/业务标识/转发DLT645)，消除伪 MSDU 残留行",
        "新增 test_net_frame_real / test_net_frame_nonzero_fields / test_aggregated_frame_app_layer 回归用例",
    ]),
    ("1.10.0", "2026-07-31", [
        "新增「主题与字体设置」（菜单 配置→主题与字体）：5 套主题（默认浅色 / Fusion 经典 / Fusion 暗色 / Windows 原生 / Windows Vista 原生），切换即时预览",
        "全局样式表升级为应用级：QMessageBox / 文件对话框等所有弹窗统一跟随主题",
        "字体设置：字体族（系统字体列表）+ 字号（8~24pt），与主题一起持久化到 config.json 的 ui 段",
        "暗色主题下自动适配统计标签 / 串口状态 / 批量状态等动态控件配色",
        "新增 theme_settings.py（主题注册表 + ThemeManager + ThemeSettingsDialog）与 test_theme_settings.py",
    ]),
    ("1.9.5", "2026-06-27", [
        "国网新一代(索引10)自动区分 HDC 1.0(旧版双模) / HDC 2.0(新一代)：依据FC字节12 D[7:4]标准版本号",
        "FC解析后新增「协议版本判定」行，据此自动选择MAC帧头解析规则(0=HDC 1.0, 1=HDC 2.0)",
        "标准MAC帧头：HDC 1.0下 D5(聚合帧标志)/发送帧序号/链路标识符 三处新增字段回退标注为「保留」",
        "单跳MAC帧头：HDC 1.0用旧消息类型表(0=发现列表消息)、D7标注保留；HDC 2.0用新表(0=无线发现列表)、D7=聚合帧标志",
        "std_version 参数贯穿 parse_to_table→_parse_msdu_from_frame/_parse_pb_by_frame_type→_parse_mac_header→标准/单跳帧头",
        "参考旧版规范 Q/GDW 12087.41/42-2020(国网新一代协议/HDC-国网双模协议 PDF)；test_gw_new_gen.py 新增3组版本区分用例(共36断言)",
    ]),
    ("1.9.4", "2026-06-27", [
        "国网新一代(索引10)解析级别新增「FC+PB解析(完整MPDU)」：FC(16B) + 完整物理块PB(PBH 1B + MAC帧头 + MSDU)",
        "修正「FC+MAC解析」未计算物理块头PBH(1B)的缺陷：原直接从偏移16解析MAC, 导致MAC头错位1字节",
        "fc_mac 现用 _locate_pbh_mac 定位 PBH+MAC, 正确先显示 PBH 行再解析 MAC 帧头",
    ]),
    ("1.9.3", "2026-06-27", [
        "修复国网新一代(索引10)完整帧结构解析：正确的帧格式为 FC(16B) + PB(物理块)",
        "PB = PBH(物理块头,1B) + MAC帧头 + MSDU；FC末3字节为FCCS(FC自身CRC校验), 其后直接为PB, 无独立HCS",
        "原代码误设 FC 后有 HCS(3B)+PBH(1B) 跳4字节, 导致 MAC 头从错误偏移解析(版本无效、TEI错乱)",
        "新增 _locate_pbh_mac：用 FC 的源/目的TEI 强校验定位 PBH+MAC 起始, 正确跳过1字节PBH",
        "新增 _pbh_row 生成物理块头行(D[5:0]=序列号 D6=帧起始 D7=帧结束)",
    ]),
    ("1.9.2", "2026-06-27", [
        "国网新一代(索引10)监控/批量摘要增强：对齐参考监控工具风格体现关键业务信息",
        "摘要字段：网络标识(NID)|帧类型(信标/SOF/选择确认/网间协调)|管理消息类型(MMTYPE)|源→目的TEI|msduSeq|单播/广播|报文ID+方向|报文序号|规约(698.45)|数据长度",
        "新增 _get_gw_new_gen_summary（按去缩进字段名索引，FC级优先），接入监控器与批量摘要两处",
        "新增 test_gw_monitor_summary.py（11个断言，复用 MainWindow 方法免 GUI 驱动）",
    ]),
    ("1.9.1", "2026-06-27", [
        "监控器新增「监控解帧(96..16)」模式(默认开启)：按监控设备包装格式自动解帧，彻底解决串口连帧",
        "包装格式 96H+RSSI(1)+NTB(4,小端)+[LEN(12b)+协议类型(3b)+CHANNEL(1b)]+DATA(LEN)+CS(1)+16H",
        "按 LEN 定界逐包抽取，正确处理连帧与 DATA 内含 0x16 的情况；分片到达自动缓存补齐",
        "伪帧头(LEN超限/帧尾非0x16)自动跳过恢复；CS校验(帧头到CS前累加和&0xFF)错误时标红",
        "详情表前置监控包装头信息(RSSI/NTB/协议类型/CHANNEL/CS)，摘要加[RSSI/信道/CS]前缀",
        "开启解帧时禁用静默间隔/剔除设置(由LEN自动定界)；新增 test_monitor_deframe.py(7用例)",
    ]),
    ("1.9.0", "2026-07-08", [
        "新增「监控器」标签页：南网新一代(9)/国网新一代(10)协议实时报文监控",
        "串口原始字节流按静默间隔(默认30ms，10-200ms可调)自动组帧并实时解析",
        "监控器支持解析前剔除报文头/尾字节(包装头+校验尾)，剔除后的帧用于解析/详情HEX/字节高亮",
        "左侧帧列表(序号/时间/方向/长度/摘要)环形缓冲1000帧，支持自动滚动/暂停/清空/导出CSV",
        "右侧详情：完整解析表格+原始HEX，点击解析行高亮对应字节；双击帧行送入单帧解析页",
        "新增 monitor_widget.py（RealtimeMonitorWidget 组件）与 test_monitor_widget.py",
    ]),
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


class DragDropTextEdit(QTextEdit):
    """支持拖拽文件加载的 QTextEdit"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path and os.path.isfile(file_path):
                    try:
                        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                        content = None
                        for enc in encodings:
                            try:
                                with open(file_path, 'r', encoding=enc) as f:
                                    content = f.read()
                                break
                            except (UnicodeDecodeError, UnicodeError):
                                continue
                        if content is None:
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                content = f.read()
                        self.setPlainText(content)
                        # 通知父窗口文件已加载
                        main_win = self.window()
                        if hasattr(main_win, 'update_stats'):
                            import os as _os
                            fname = _os.path.basename(file_path)
                            lines = content.splitlines()
                            main_win.update_stats(f"已拖入文件 {fname}（{len(lines)} 行）")
                    except Exception as e:
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.critical(self, "错误", f"读取文件失败：{e}")
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"协议解析工具 v{APP_VERSION} ({BUILD_DATE}) - 作者: liruitao")
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
        self.hdc10_parser = HDC10Parser()

        # 新一代载波协议解析级别：auto=自动, fc_pb=FC+PB, fc_only=仅FC, app=应用层
        self._csg_parse_level = "auto"
        # 字节剔除缓存：记录上次剔除后成功解析的hex，避免重复剔除
        self._csg_last_stripped_hex = ""

        # 国网新一代解析级别：auto=自动, fc_pb=FC+完整PB, fc_only=仅FC, fc_mac=FC+PB头+MAC, app=应用层
        self._gw_parse_level = "auto"
        # HDC 1.0解析级别
        self._hdc10_parse_level = "auto"
        self._hdc10_channel = "plc"

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

        # 主题与字体配置（应用级样式由 main() 在 QApplication 上应用，此处仅保存配置供动态控件适配）
        self._theme_id, self._font_family, self._font_size = ThemeManager.load_from_config(self._app_config)
        # 系统集成配置（config.json "system" 段）
        self._system_settings: Dict[str, Any] = {}
        self._load_system_settings()
        self._stats_labels: List[tuple] = []      # (QLabel, 字号) 列表，主题切换时统一重设
        self._serial_status_color = "#999"       # 串口状态标签当前颜色（主题切换时重设）
        self._serial_status_bold = False       # 串口状态标签当前是否粗体（主题切换时重设）

        self.setup_ui()
        self._setup_menu_bar()

        # 系统集成管理器（托盘 / 全局热键 / 单实例）
        self._setup_system_integration()

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
        proto_label.setFont(self._ui_font(0, bold=True))
        proto_label.setFixedWidth(65)
        proto_layout.addWidget(proto_label)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("[0] 南网协议 (Q/CSG1209021-2019)")
        self.protocol_combo.addItem("[1] PLC RF协议 (万胜海外 V1_04)")
        self.protocol_combo.addItem("[2] HDLC/国网DLMS (IEC 62056-46)")
        self.protocol_combo.addItem("[3] DLMS-APDU(国网)")
        self.protocol_combo.addItem("[4] DLMS Wrapper裸报文")
        self.protocol_combo.addItem("[5] DLMS-APDU裸报文")
        self.protocol_combo.addItem("[6] DLT645-2007 电表协议")
        self.protocol_combo.addItem("[7] 国网协议 (Q/GDW 10376.2-2024)")
        self.protocol_combo.addItem("[8] 698.45协议 (DL/T 698.45-2017)")
        self.protocol_combo.addItem("[9] 新一代载波协议 (通感一体化)")
        self.protocol_combo.addItem("[10] 国网新一代双模通信互联互通")
        self.protocol_combo.addItem("[11] HDC 1.0 双模互联互通")
        self.protocol_combo.setMinimumWidth(320)
        self.protocol_combo.setFont(self._ui_font(0))
        # 让弹出菜单宽度自动适应最宽的文字
        self.protocol_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.protocol_combo.currentIndexChanged.connect(self._on_protocol_changed)
        proto_layout.addWidget(self.protocol_combo)

        # ---- 新一代载波协议解析级别选择（仅协议索引9时可见）----
        self.csg_parse_level_label = QLabel("解析级别：")
        self.csg_parse_level_label.setFont(self._ui_font(-1))
        proto_layout.addWidget(self.csg_parse_level_label)

        self.csg_parse_level_combo = QComboBox()
        self.csg_parse_level_combo.addItem("自动识别", "auto")
        self.csg_parse_level_combo.addItem("FC+PB解析(完整MPDU)", "fc_pb")
        self.csg_parse_level_combo.addItem("FC+eFC解析", "fc_efc")
        self.csg_parse_level_combo.addItem("仅FC解析", "fc_only")
        self.csg_parse_level_combo.addItem("应用层报文", "app")
        self.csg_parse_level_combo.addItem("仅PB解析(完整物理块)", "pb_only")
        self.csg_parse_level_combo.setFont(self._ui_font(-1))
        self.csg_parse_level_combo.setMinimumWidth(180)
        self.csg_parse_level_combo.currentIndexChanged.connect(self._on_csg_parse_level_changed)
        self.csg_parse_level_combo.setVisible(False)
        proto_layout.addWidget(self.csg_parse_level_combo)
        self.csg_parse_level_label.setVisible(False)

        # ---- 南网新一代通道选择（仅协议索引9时可见）----
        self.csg_channel_label = QLabel("通道：")
        self.csg_channel_label.setFont(self._ui_font(-1))
        self.csg_channel_label.setVisible(False)
        proto_layout.addWidget(self.csg_channel_label)

        self.csg_channel_combo = QComboBox()
        self.csg_channel_combo.addItem("自动识别", "auto")
        self.csg_channel_combo.addItem("PLC 载波", "plc")
        self.csg_channel_combo.addItem("HRF 无线", "hrf")
        self.csg_channel_combo.setFont(self._ui_font(-1))
        self.csg_channel_combo.setMinimumWidth(100)
        # 从配置恢复
        csg_ch = getattr(self, '_csg_channel', 'auto')
        idx = self.csg_channel_combo.findData(csg_ch)
        if idx >= 0:
            self.csg_channel_combo.setCurrentIndex(idx)
        self.csg_channel_combo.currentIndexChanged.connect(self._on_csg_channel_changed)
        self.csg_channel_combo.setVisible(False)
        proto_layout.addWidget(self.csg_channel_combo)

        # ---- 南网新一代PB帧类型选择（仅pb_only模式可见）----
        self.csg_pb_frame_type_label = QLabel("帧类型：")
        self.csg_pb_frame_type_label.setFont(self._ui_font(-1))
        self.csg_pb_frame_type_label.setVisible(False)
        proto_layout.addWidget(self.csg_pb_frame_type_label)

        self.csg_pb_frame_type_combo = QComboBox()
        self.csg_pb_frame_type_combo.addItem("SOF帧", "sof")
        self.csg_pb_frame_type_combo.addItem("信标帧", "beacon")
        self.csg_pb_frame_type_combo.addItem("ACK帧(SACK)", "sack")
        self.csg_pb_frame_type_combo.addItem("NET帧", "net")
        self.csg_pb_frame_type_combo.setFont(self._ui_font(-1))
        self.csg_pb_frame_type_combo.setMinimumWidth(120)
        self.csg_pb_frame_type_combo.setVisible(False)
        proto_layout.addWidget(self.csg_pb_frame_type_combo)

        # ---- 新一代载波协议字节剔除（仅协议索引9时可见）----
        self.csg_strip_head_label = QLabel("剔除前:")
        self.csg_strip_head_label.setFont(self._ui_font(-1))
        self.csg_strip_head_label.setVisible(False)
        proto_layout.addWidget(self.csg_strip_head_label)

        self.csg_strip_head_spin = QSpinBox()
        self.csg_strip_head_spin.setRange(0, 999)
        self.csg_strip_head_spin.setValue(0)
        self.csg_strip_head_spin.setSuffix(" 字节")
        self.csg_strip_head_spin.setFont(self._ui_font(-1))
        self.csg_strip_head_spin.setVisible(False)
        self.csg_strip_head_spin.setToolTip("解析前剔除报文头部指定字节数（0=不剔除）")
        proto_layout.addWidget(self.csg_strip_head_spin)

        self.csg_strip_tail_label = QLabel("尾部:")
        self.csg_strip_tail_label.setFont(self._ui_font(-1))
        self.csg_strip_tail_label.setVisible(False)
        proto_layout.addWidget(self.csg_strip_tail_label)

        self.csg_strip_tail_spin = QSpinBox()
        self.csg_strip_tail_spin.setRange(0, 999)
        self.csg_strip_tail_spin.setValue(0)
        self.csg_strip_tail_spin.setSuffix(" 字节")
        self.csg_strip_tail_spin.setFont(self._ui_font(-1))
        self.csg_strip_tail_spin.setVisible(False)
        self.csg_strip_tail_spin.setToolTip("解析前剔除报文尾部指定字节数（0=不剔除）")
        proto_layout.addWidget(self.csg_strip_tail_spin)

        # ---- 国网新一代解析级别选择（仅协议索引10时可见）----
        self.gw_parse_level_label = QLabel("解析级别：")
        self.gw_parse_level_label.setFont(self._ui_font(-1))
        self.gw_parse_level_label.setVisible(False)
        proto_layout.addWidget(self.gw_parse_level_label)

        self.gw_parse_level_combo = QComboBox()
        self.gw_parse_level_combo.addItem("自动识别", "auto")
        self.gw_parse_level_combo.addItem("FC+PB解析(完整MPDU)", "fc_pb")
        self.gw_parse_level_combo.addItem("仅FC解析", "fc_only")
        self.gw_parse_level_combo.addItem("仅MAC帧", "mac_only")
        self.gw_parse_level_combo.addItem("仅PB", "pb_only")
        self.gw_parse_level_combo.addItem("FC+MAC解析", "fc_mac")
        self.gw_parse_level_combo.addItem("应用层报文", "app")
        self.gw_parse_level_combo.setFont(self._ui_font(-1))
        self.gw_parse_level_combo.setMinimumWidth(150)
        self.gw_parse_level_combo.currentIndexChanged.connect(self._on_gw_parse_level_changed)
        self.gw_parse_level_combo.setVisible(False)
        proto_layout.addWidget(self.gw_parse_level_combo)

        # ---- 国网新一代PB帧类型选择（仅pb_only模式可见）----
        self.gw_pb_frame_type_label = QLabel("帧类型：")
        self.gw_pb_frame_type_label.setFont(self._ui_font(-1))
        self.gw_pb_frame_type_label.setVisible(False)
        proto_layout.addWidget(self.gw_pb_frame_type_label)

        self.gw_pb_frame_type_combo = QComboBox()
        self.gw_pb_frame_type_combo.addItem("SOF帧", 1)
        self.gw_pb_frame_type_combo.addItem("信标帧", 0)
        self.gw_pb_frame_type_combo.addItem("ACK帧(SACK)", 2)
        self.gw_pb_frame_type_combo.addItem("NET帧", 3)
        self.gw_pb_frame_type_combo.setFont(self._ui_font(-1))
        self.gw_pb_frame_type_combo.setMinimumWidth(120)
        self.gw_pb_frame_type_combo.setVisible(False)
        proto_layout.addWidget(self.gw_pb_frame_type_combo)

        # ---- 国网新一代通道选择（仅协议索引10时可见）----
        self.gw_channel_label = QLabel("通道：")
        self.gw_channel_label.setFont(self._ui_font(-1))
        self.gw_channel_label.setVisible(False)
        proto_layout.addWidget(self.gw_channel_label)

        self.gw_channel_combo = QComboBox()
        self.gw_channel_combo.addItem("PLC 载波", "plc")
        self.gw_channel_combo.addItem("HRF 无线", "hrf")
        self.gw_channel_combo.setFont(self._ui_font(-1))
        self.gw_channel_combo.setMinimumWidth(100)
        # 从配置恢复
        gw_ch = getattr(self, '_gw_channel', 'plc')
        idx = self.gw_channel_combo.findData(gw_ch)
        if idx >= 0:
            self.gw_channel_combo.setCurrentIndex(idx)
        self.gw_channel_combo.currentIndexChanged.connect(self._on_gw_channel_changed)
        self.gw_channel_combo.setVisible(False)
        proto_layout.addWidget(self.gw_channel_combo)

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
        self.serial_refresh_btn.setStyleSheet(self._serial_refresh_style())
        from PySide6.QtCore import QSize
        self.serial_refresh_btn.setIconSize(QSize(18, 18))
        self.serial_refresh_btn.clicked.connect(self._refresh_serial_ports)
        serial_layout.addWidget(self.serial_refresh_btn)

        serial_layout.addWidget(QLabel("波特率:"))
        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.setEditable(True)  # 允许手动输入自定义波特率
        self.serial_baud_combo.addItems([
            "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200",
            "230400", "460800", "921600", "1000000", "2000000", "3000000",
        ])
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
        self.serial_status_label.setStyleSheet(self._serial_status_style("#999"))
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

        # 报文工具页面（所有协议可见）
        self.message_tool_tab = MessageToolWidget()
        self.tab_widget.addTab(self.message_tool_tab, "报文工具")

        # TCP 流量监控器页面（始终可见）
        self.tcp_monitor_tab = TCPMonitorWidget()
        self.tcp_monitor_tab.set_parsers(
            self.gw_new_gen_parser, self.csg_new_gen_parser,
            gw_summary_fn=self._get_gw_new_gen_summary,
            csg_summary_fn=self._get_csg_new_gen_summary,
        )
        self.tab_widget.addTab(self.tcp_monitor_tab, "TCP监控")

        # 实时监控器页面（南网新一代(9)/国网新一代(10) 专用，默认隐藏）
        self.monitor_tab = RealtimeMonitorWidget()
        self.monitor_tab.set_serial_worker(self.serial_worker)
        self.monitor_tab.set_send_to_single_handler(self._send_frame_to_single_parse)
        self._monitor_tab_index = self.tab_widget.addTab(self.monitor_tab, "监控器")
        self.tab_widget.setTabVisible(self._monitor_tab_index, False)

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

        # ED 监控协议勾选项（仅南网新一代协议显示）
        self.ed_monitor_chk = QCheckBox("ED监控协议")
        self.ed_monitor_chk.setToolTip("勾选后解析 ED..EE 监控包装头（PLC2.0 收发机报文格式），\n前置显示 RSSI/NTB/信道等信息，再解析业务帧")
        self.ed_monitor_chk.setVisible(False)
        btn_layout.addWidget(self.ed_monitor_chk)

        # 4字节反转勾选项（仅南网新一代协议显示）
        self.csg_reverse_4byte_chk = QCheckBox("4字节反转")
        self.csg_reverse_4byte_chk.setToolTip("勾选后对输入 hex 按 4 字节一组做端序翻转（大端↔小端），\n例如 C9D50438 → 3804D5C9），再进行解析")
        self.csg_reverse_4byte_chk.setVisible(False)
        btn_layout.addWidget(self.csg_reverse_4byte_chk)

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
        table_font = self._ui_font(-2)
        self.result_table_widget.setFont(table_font)
        # 行高更紧凑
        self.result_table_widget.verticalHeader().setDefaultSectionSize(10)
        self.result_table_widget.verticalHeader().hide()
        # 右键复制菜单 + Ctrl+C
        self._setup_table_copy_menu(self.result_table_widget)

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
        verify_layout.setContentsMargins(8, 8, 8, 8)
        verify_layout.setSpacing(4)

        # 头部按钮行：展开 / 收缩（收缩后仅保留标题+按钮行，内容进入滚动区）
        verify_head = QHBoxLayout()
        verify_head.addStretch()
        self.verify_expand_btn = QPushButton("展开")
        self.verify_collapse_btn = QPushButton("收缩")
        for b in (self.verify_expand_btn, self.verify_collapse_btn):
            b.setFixedHeight(24)
            b.setFont(self._ui_font(-1))
        self.verify_expand_btn.setEnabled(False)  # 默认展开态
        self.verify_expand_btn.setToolTip("展开校验结果全文")
        self.verify_collapse_btn.setToolTip("收缩校验结果，仅保留摘要入口")
        self.verify_expand_btn.clicked.connect(self._on_verify_expand)
        self.verify_collapse_btn.clicked.connect(self._on_verify_collapse)
        verify_head.addWidget(self.verify_expand_btn)
        verify_head.addWidget(self.verify_collapse_btn)
        verify_layout.addLayout(verify_head)

        # 校验结果内容（滚动区，收缩时隐藏）
        self.verify_scroll = QScrollArea()
        self.verify_scroll.setWidgetResizable(True)
        self.verify_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.verify_label = QLabel("点击「校验报文」按钮进行协议一致性校验")
        self.verify_label.setWordWrap(True)
        self.verify_label.setFont(self._ui_font(-1, family="Consolas"))
        self.verify_scroll.setWidget(self.verify_label)
        verify_layout.addWidget(self.verify_scroll, 1)
        result_layout.addWidget(self.verify_group)

        # 全屏/恢复按钮：解析结果表格撑满窗口（隐藏输入区+校验结果区）
        export_row.addLayout(
            self._make_table_fullscreen_btn("解析结果 - 全屏", self.result_table_widget))

        layout.addWidget(result_group, 1)

        return tab

    # ------------------------------------------------------------- 视图辅助
    def _make_table_fullscreen_btn(self, title: str, table: QTableWidget) -> QHBoxLayout:
        """构建右对齐「全屏」按钮：点击在新窗口全屏展示解析结果表格。

        与报文对比「结果详情」交互一致：弹窗内克隆表格快照展示，
        点「关闭」或窗口 X 关闭后主界面原样恢复。
        """
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch()
        fs_btn = QPushButton("全屏")
        fs_btn.setFixedHeight(26)
        fs_btn.setFont(self._ui_font(-1))
        fs_btn.setToolTip("在新窗口全屏展示解析结果表格，关闭窗口即恢复")
        fs_btn.clicked.connect(lambda: self._open_table_popup(title, table))
        row.addWidget(fs_btn)
        return row

    def _open_table_popup(self, title: str, source_table: QTableWidget):
        """以独立弹窗全屏展示解析结果表格（克隆快照，关闭后主界面原样恢复）"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(1200, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 克隆源表格内容为快照（读取型展示，不共享原表格）
        clone = QTableWidget(source_table.rowCount(), source_table.columnCount())
        headers = []
        for c in range(source_table.columnCount()):
            h = source_table.horizontalHeaderItem(c)
            headers.append(h.text() if h else "")
        clone.setHorizontalHeaderLabels(headers)
        for r in range(source_table.rowCount()):
            for c in range(source_table.columnCount()):
                item = source_table.item(r, c)
                if item:
                    clone.setItem(r, c, QTableWidgetItem(item.text()))
        # 外观对齐源表格
        header = clone.horizontalHeader()
        header.setStretchLastSection(True)
        src_header = source_table.horizontalHeader()
        for c in range(source_table.columnCount()):
            if src_header.sectionSize(c) > 20:
                clone.setColumnWidth(c, src_header.sectionSize(c))
        clone.setEditTriggers(QTableWidget.NoEditTriggers)
        clone.setSelectionBehavior(QTableWidget.SelectRows)
        clone.setAlternatingRowColors(True)
        clone.verticalHeader().hide()
        clone.setFont(source_table.font())
        layout.addWidget(clone, 1)

        # 关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.setFixedSize(80, 28)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #fff; color: #666; border: 1px solid #dcdcdc; "
            "border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #f0f0f0; }"
        )
        btn_close.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dialog.exec()

    def _on_verify_expand(self):
        """展开校验结果全文"""
        self.verify_scroll.show()
        self.verify_group.setMaximumHeight(16777215)
        self.verify_expand_btn.setEnabled(False)
        self.verify_collapse_btn.setEnabled(True)

    def _on_verify_collapse(self):
        """收缩校验结果：隐藏内容，仅保留组标题和按钮行"""
        self.verify_scroll.hide()
        head_h = self.verify_collapse_btn.sizeHint().height() + 8
        # 26 ≈ QGroupBox 标题区 + 布局边距（随主题可能有差异，预留余量）
        self.verify_group.setMaximumHeight(head_h + 28)
        self.verify_expand_btn.setEnabled(True)
        self.verify_collapse_btn.setEnabled(False)

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
        self.di_stats_label = self._make_stats_label()
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
        table_font = self._ui_font(-2)
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
        """创建批量解析标签页（左右分栏布局：左侧摘要 + 右侧详情）"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # ── 输入区 ──────────────────────────────────────────────
        input_group = QGroupBox("批量输入报文")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.load_file_btn = self._make_toolbar_btn("从文件加载")
        self.load_file_btn.setToolTip("支持每行一帧的文本文件")
        self.load_file_btn.clicked.connect(self.load_from_file)
        toolbar.addWidget(self.load_file_btn)

        self.paste_btn = self._make_toolbar_btn("从剪贴板粘贴")
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        toolbar.addWidget(self.paste_btn)

        self.batch_parse_btn = self._make_toolbar_btn("开始批量解析", min_width=90)
        self.batch_parse_btn.clicked.connect(self.parse_batch)
        toolbar.addWidget(self.batch_parse_btn)

        self.clear_batch_btn = self._make_toolbar_btn("清空")
        self.clear_batch_btn.clicked.connect(self.clear_batch)
        toolbar.addWidget(self.clear_batch_btn)

        # ── CLI 预处理 ──────────────────────────────────────────
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFrameShadow(QFrame.Sunken)
        toolbar.addWidget(sep1)

        pp_label = QLabel("预处理:")
        pp_label.setFont(self._ui_font(-1))
        toolbar.addWidget(pp_label)

        self._pp_cmd_combo = QComboBox()
        self._pp_cmd_combo.setEditable(True)
        self._pp_cmd_combo.setFont(self._ui_font(-1, family="Consolas"))
        self._pp_cmd_combo.setMinimumWidth(260)
        self._pp_cmd_combo.setPlaceholderText('如: find "tcp data:" excluding "len:\\d+: "')
        self._pp_cmd_combo.setToolTip(
            "通用文本预处理命令链（支持正则）\n"
            "可用命令: find <pat> | excluding <pat> | replace <pat> <repl>\n"
            "          head <n> | tail <n> | skip <n> | hex_extract | dedup\n"
            "          tcp_extract | merge_payloads\n"
            "点「★」保存当前命令到列表，点「×」删除选中命令")
        # 加载预设命令
        self._pp_preset_commands = [
            'find "tcp data:" tcp_extract',
            'find "fc_payload_data" merge_payloads',
            'find "tcp data:"',
            'find "fc_payload_data"',
            'find "60F0" excluding "mrd:" dedup',
            'find "nwk:" replace ".*nwk:" "NWK:" head 20',
            'hex_extract dedup',
            'excluding "len:" head 50',
        ]
        self._load_pp_commands()
        toolbar.addWidget(self._pp_cmd_combo)

        self._pp_save_btn = self._make_toolbar_btn("★", icon_btn=True)
        self._pp_save_btn.setToolTip("保存当前命令到常用列表")
        self._pp_save_btn.clicked.connect(self._save_pp_command)
        toolbar.addWidget(self._pp_save_btn)

        self._pp_del_btn = self._make_toolbar_btn("×", icon_btn=True)
        self._pp_del_btn.setToolTip("删除下拉列表中选中的命令")
        self._pp_del_btn.clicked.connect(self._delete_pp_command)
        toolbar.addWidget(self._pp_del_btn)

        self._pp_run_btn = self._make_toolbar_btn("执行")
        self._pp_run_btn.setToolTip("对输入框内容执行预处理命令链，结果回填到输入框")
        self._pp_run_btn.clicked.connect(self._run_cli_preprocessor)
        toolbar.addWidget(self._pp_run_btn)

        self._pp_help_btn = self._make_toolbar_btn("?", icon_btn=True)
        self._pp_help_btn.setToolTip("显示预处理命令帮助")
        self._pp_help_btn.clicked.connect(self._show_pp_help)
        toolbar.addWidget(self._pp_help_btn)

        # ── Python 脚本预处理 ───────────────────────────────────
        sep_py = QFrame()
        sep_py.setFrameShape(QFrame.VLine)
        sep_py.setFrameShadow(QFrame.Sunken)
        toolbar.addWidget(sep_py)

        py_label = QLabel("脚本:")
        py_label.setFont(self._ui_font(-1))
        toolbar.addWidget(py_label)

        self._py_script_combo = QComboBox()
        self._py_script_combo.setFont(self._ui_font(-1, family="Consolas"))
        self._py_script_combo.setMinimumWidth(180)
        self._py_script_combo.setToolTip(
            "Python 脚本预处理\n"
            "加载自定义 .py 脚本，对输入文本进行清洗/转换\n"
            "脚本需定义 process(text, context) -> str\n"
            "⚠ 直接运行本地脚本，仅加载可信脚本")
        self._load_py_scripts()
        toolbar.addWidget(self._py_script_combo)

        self._py_load_btn = self._make_toolbar_btn("加载")
        self._py_load_btn.setToolTip("加载 .py 脚本文件到列表")
        self._py_load_btn.clicked.connect(self._load_py_script_file)
        toolbar.addWidget(self._py_load_btn)

        self._py_run_btn = self._make_toolbar_btn("运行")
        self._py_run_btn.setToolTip("对输入框内容运行当前脚本，结果回填")
        self._py_run_btn.clicked.connect(self._run_py_script)
        toolbar.addWidget(self._py_run_btn)

        self._py_del_btn = self._make_toolbar_btn("×", icon_btn=True)
        self._py_del_btn.setToolTip("从列表中移除当前脚本（不删除磁盘文件）")
        self._py_del_btn.clicked.connect(self._delete_py_script)
        toolbar.addWidget(self._py_del_btn)

        self._py_help_btn = self._make_toolbar_btn("?", icon_btn=True)
        self._py_help_btn.setToolTip("显示 Python 脚本预处理帮助")
        self._py_help_btn.clicked.connect(self._show_py_script_help)
        toolbar.addWidget(self._py_help_btn)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        toolbar.addWidget(sep)

        # 导出按钮
        self.batch_export_excel_btn = self._make_toolbar_btn("导出 Excel")
        self.batch_export_excel_btn.clicked.connect(lambda: self.export_batch("excel"))
        toolbar.addWidget(self.batch_export_excel_btn)

        self.batch_export_json_btn = self._make_toolbar_btn("导出 JSON")
        self.batch_export_json_btn.clicked.connect(lambda: self.export_batch("json"))
        toolbar.addWidget(self.batch_export_json_btn)

        toolbar.addStretch()

        # 帧计数徽章
        self.batch_frame_count_label = QLabel("共 0 帧")
        self.batch_frame_count_label.setStyleSheet(self._batch_count_style())
        toolbar.addWidget(self.batch_frame_count_label)

        input_layout.addLayout(toolbar)

        # 输入文本框
        self.batch_input = DragDropTextEdit()
        self.batch_input.setPlaceholderText(
            "粘贴或输入报文数据，支持多种协议：\n"
            "南网/国网协议：68开头，16结束\n"
            "HDLC协议：7E开头，7E结束\n"
            "其他协议：每行一帧直接解析"
        )
        self.batch_input.setMaximumHeight(140)
        input_layout.addWidget(self.batch_input)

        # 帧计数防抖定时器
        self._frame_count_timer = QTimer(self)
        self._frame_count_timer.setSingleShot(True)
        self._frame_count_timer.setInterval(200)
        self._frame_count_timer.timeout.connect(self._do_count_frames)
        self.batch_input.textChanged.connect(self._frame_count_timer.start)

        layout.addWidget(input_group)

        # ── LLM 预处理面板（可折叠） ──────────────────────────────
        self.llm_toggle_btn = QPushButton("▶ LLM 智能预处理")
        self.llm_toggle_btn.setCheckable(True)
        self.llm_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; padding: 4px 8px; font-weight: bold; }"
            "QPushButton:checked { background-color: #e8f4fd; }"
        )
        self.llm_toggle_btn.clicked.connect(self._toggle_llm_panel)
        layout.addWidget(self.llm_toggle_btn)

        self.llm_preprocess_widget = LLMPreprocessWidget()
        self.llm_preprocess_widget.hide()  # 默认折叠
        layout.addWidget(self.llm_preprocess_widget)

        # ── 结果区分栏（左侧摘要 + 右侧详情） ───────────────────
        self.result_splitter = QSplitter(Qt.Horizontal)

        # 左侧：摘要列表
        summary_group = QGroupBox("解析结果摘要")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(8, 10, 8, 8)
        summary_layout.setSpacing(6)

        # 搜索过滤栏
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)

        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(-1))
        filter_bar.addWidget(search_label)

        self.batch_search_edit = QLineEdit()
        self.batch_search_edit.setPlaceholderText("输入关键词过滤（摘要/类型/TEI…）")
        self.batch_search_edit.setFont(self._ui_font(-1))
        self.batch_search_edit.setClearButtonEnabled(True)
        self.batch_search_edit.textChanged.connect(self._on_batch_filter_changed)
        filter_bar.addWidget(self.batch_search_edit, 1)

        status_label = QLabel("状态：")
        status_label.setFont(self._ui_font(-1))
        filter_bar.addWidget(status_label)

        self.batch_status_filter = QComboBox()
        self.batch_status_filter.addItem("全部", "all")
        self.batch_status_filter.addItem("成功", "success")
        self.batch_status_filter.addItem("失败", "fail")
        self.batch_status_filter.addItem("异常", "error")
        self.batch_status_filter.setFont(self._ui_font(-1))
        self.batch_status_filter.currentIndexChanged.connect(self._on_batch_filter_changed)
        filter_bar.addWidget(self.batch_status_filter)

        self.batch_filter_count = QLabel("")
        self.batch_filter_count.setFont(self._ui_font(-1))
        self.batch_filter_count.setStyleSheet("color: #666;")
        filter_bar.addWidget(self.batch_filter_count)

        summary_layout.addLayout(filter_bar)

        self.batch_summary_table = QTableWidget()
        self.batch_summary_table.setColumnCount(5)
        self.batch_summary_table.setHorizontalHeaderLabels([
            "#", "状态", "长度", "协议/类型", "摘要"
        ])
        header = self.batch_summary_table.horizontalHeader()
        # 列宽设置
        self.batch_summary_table.setColumnWidth(0, 40)
        self.batch_summary_table.setColumnWidth(1, 50)
        self.batch_summary_table.setColumnWidth(2, 60)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.batch_summary_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.batch_summary_table.setSelectionMode(QTableWidget.SingleSelection)
        self.batch_summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.batch_summary_table.setAlternatingRowColors(True)
        self.batch_summary_table.verticalHeader().hide()
        table_font = self._ui_font(-2)
        self.batch_summary_table.setFont(table_font)
        self.batch_summary_table.verticalHeader().setDefaultSectionSize(22)
        # 右键复制菜单 + Ctrl+C
        self._setup_table_copy_menu(self.batch_summary_table)
        # 选中行/项变化时更新详情
        self.batch_summary_table.cellClicked.connect(self._on_batch_row_selected)
        self.batch_summary_table.itemSelectionChanged.connect(self._on_batch_row_selected)
        summary_layout.addWidget(self.batch_summary_table)

        # 全屏：弹窗展示摘要表（关闭即恢复）
        summary_layout.addLayout(
            self._make_table_fullscreen_btn("解析结果摘要 - 全屏", self.batch_summary_table))

        self.result_splitter.addWidget(summary_group)

        # 右侧：详情面板
        detail_group = QGroupBox("选中帧详细解析")
        detail_layout = QVBoxLayout(detail_group)
        detail_layout.setContentsMargins(8, 10, 8, 8)
        detail_layout.setSpacing(6)

        # 原始报文行
        hex_row = QHBoxLayout()
        hex_row.setSpacing(6)
        hex_label = self._make_stats_label("原始报文：", 12)
        hex_row.addWidget(hex_label)

        self.batch_detail_hex = QTextEdit()
        self.batch_detail_hex.setReadOnly(True)
        self.batch_detail_hex.setMaximumHeight(60)
        self.batch_detail_hex.setFont(self._ui_font(-1, family="Consolas"))
        self.batch_detail_hex.setPlaceholderText("选择左侧列表中的帧以查看详情…")
        hex_row.addWidget(self.batch_detail_hex, 1)

        self.batch_copy_hex_btn = QPushButton("复制")
        self.batch_copy_hex_btn.setMaximumWidth(60)
        self.batch_copy_hex_btn.clicked.connect(self._copy_batch_detail_hex)
        hex_row.addWidget(self.batch_copy_hex_btn)

        detail_layout.addLayout(hex_row)

        # 详情表格
        self.batch_detail_table = QTableWidget()
        self.batch_detail_table.setColumnCount(4)
        self.batch_detail_table.setHorizontalHeaderLabels([
            "字段", "原始值", "解析值", "说明"
        ])
        detail_header = self.batch_detail_table.horizontalHeader()
        detail_header.setStretchLastSection(True)
        detail_header.setSectionResizeMode(QHeaderView.Interactive)
        self.batch_detail_table.setColumnWidth(0, 180)
        self.batch_detail_table.setColumnWidth(1, 120)
        self.batch_detail_table.setColumnWidth(2, 200)
        self.batch_detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.batch_detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.batch_detail_table.setAlternatingRowColors(True)
        self.batch_detail_table.verticalHeader().hide()
        detail_font = self._ui_font(-2)
        self.batch_detail_table.setFont(detail_font)
        self.batch_detail_table.verticalHeader().setDefaultSectionSize(20)
        # 右键复制菜单 + Ctrl+C
        self._setup_table_copy_menu(self.batch_detail_table)
        detail_layout.addWidget(self.batch_detail_table)

        # 全屏：弹窗展示详情表（关闭即恢复）
        detail_layout.addLayout(
            self._make_table_fullscreen_btn("选中帧详细解析 - 全屏", self.batch_detail_table))

        self.result_splitter.addWidget(detail_group)

        # 初始分割比例（约 45:55）
        self.result_splitter.setSizes([450, 550])

        layout.addWidget(self.result_splitter, 1)

        # ── 底部状态栏 ──────────────────────────────────────────
        self.batch_status_bar = QLabel("就绪")
        self.batch_status_bar.setStyleSheet(self._batch_status_style())
        layout.addWidget(self.batch_status_bar)

        # 兼容：保留 stats_label 引用（初始化为空，不显示到布局中）
        self.stats_label = QLabel("状态：待解析")
        self.stats_label.setVisible(False)

        return tab

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
            baud = self._get_baud_value()
            if baud is None:
                return
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
            self.serial_status_label.setStyleSheet(self._serial_status_style("#4CAF50", bold=True))
        else:
            self.serial_status_label.setText("未连接")
            self.serial_status_label.setStyleSheet(self._serial_status_style("#999"))
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

    def _debug_log(self, msg: str):
        """输出调试日志到终端（黑窗口），GUI 模式下从终端启动可见"""
        print(f"[DEBUG] {msg}", flush=True)

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
        elif index == 10:  # 国网新一代双模通信互联互通
            self.single_input.setPlaceholderText("请输入国网新一代报文，例如：ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00")
        elif index == 11:  # HDC 1.0 双模互联互通
            self.single_input.setPlaceholderText("请输入HDC 1.0报文，例如：01 00 01 00 00 10 00 11 ...")

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
        self.csg_pb_frame_type_label.setVisible(show_csg_level and self._csg_parse_level == "pb_only")
        self.csg_pb_frame_type_combo.setVisible(show_csg_level and self._csg_parse_level == "pb_only")
        # ED 监控协议勾选项：仅协议索引9（南网新一代）时可见
        self.ed_monitor_chk.setVisible(show_csg_level)
        # 4字节反转勾选项：仅协议索引9（南网新一代）时可见
        self.csg_reverse_4byte_chk.setVisible(show_csg_level)
        # 通道下拉框：仅协议索引9（南网新一代）时可见
        self.csg_channel_combo.setVisible(show_csg_level)

        # 国网新一代/HDC 1.0 解析级别选择：协议索引10和11时可见
        show_gw_level = (index in (10, 11))
        self.gw_parse_level_label.setVisible(show_gw_level)
        self.gw_parse_level_combo.setVisible(show_gw_level)
        # 通道下拉框：协议索引10和11时可见
        self.gw_channel_combo.setVisible(show_gw_level)

        # 同步解析级别combo到对应协议的当前值
        if index == 10:
            idx = self.gw_parse_level_combo.findData(self._gw_parse_level)
            if idx >= 0:
                self.gw_parse_level_combo.setCurrentIndex(idx)
        elif index == 11:
            idx = self.gw_parse_level_combo.findData(self._hdc10_parse_level)
            if idx >= 0:
                self.gw_parse_level_combo.setCurrentIndex(idx)

        # 清空当前结果
        self.clear_single()

        # 同步协议到报文对比标签页
        if hasattr(self, 'diff_tab'):
            self.diff_tab.set_protocol(index)
            self.diff_tab.set_parser(self._get_current_parser())

        # 监控器标签页：仅南网新一代(9)/国网新一代(10)可见，并注入对应解析器与摘要函数
        if hasattr(self, '_monitor_tab_index'):
            show_monitor = index in (9, 10)
            self.tab_widget.setTabVisible(self._monitor_tab_index, show_monitor)
            if show_monitor:
                parser = self.csg_new_gen_parser if index == 9 else self.gw_new_gen_parser
                # 协议9(新一代通感一体化/PLC2.0收发机)用 ED..EE 包装；
                # 协议10(国网新一代/HPLC)用 96..16 包装
                wrapper = "plc2" if index == 9 else "hplc"
                self.monitor_tab.set_protocol(parser, self._get_monitor_summary,
                                              wrapper_format=wrapper)

    def _get_monitor_summary(self, table_data: list) -> str:
        """监控器摘要生成：按当前协议分派到对应摘要函数"""
        if self.current_protocol == 9:
            return self._get_csg_new_gen_summary(table_data)
        if self.current_protocol == 10:
            return self._get_gw_new_gen_summary(table_data)
        return self._get_summary_from_table_data(table_data)

    def _send_frame_to_single_parse(self, hex_str: str):
        """监控器双击帧：送入单帧解析页并触发解析"""
        self.single_input.setPlainText(hex_str)
        self.tab_widget.setCurrentIndex(0)
        self.parse_single()

    def _on_csg_parse_level_changed(self, index: int):
        """新一代载波协议解析级别改变时的回调"""
        level = self.csg_parse_level_combo.currentData()
        self._csg_parse_level = level or "auto"
        # pb_only模式显示帧类型选择
        show_frame_type = (self._csg_parse_level == "pb_only")
        self.csg_pb_frame_type_label.setVisible(show_frame_type)
        self.csg_pb_frame_type_combo.setVisible(show_frame_type)

    def _on_gw_parse_level_changed(self, index: int):
        """国网新一代/HDC 1.0 解析级别改变时的回调"""
        level = self.gw_parse_level_combo.currentData()
        if self.current_protocol == 11:
            self._hdc10_parse_level = level or "auto"
        else:
            self._gw_parse_level = level or "auto"

        # 根据解析级别显示/隐藏帧类型选择
        cur_level = self._hdc10_parse_level if self.current_protocol == 11 else self._gw_parse_level
        show_frame_type = (cur_level == "pb_only")
        self.gw_pb_frame_type_label.setVisible(show_frame_type and self.current_protocol in (10, 11))
        self.gw_pb_frame_type_combo.setVisible(show_frame_type and self.current_protocol in (10, 11))

    def _on_csg_channel_changed(self, index: int):
        """南网新一代通道切换回调"""
        channel = self.csg_channel_combo.currentData()
        self._csg_channel = channel or "plc"
        # 自动重解析
        if self.single_input.toPlainText().strip():
            self.parse_single()

    def _on_gw_channel_changed(self, index: int):
        """国网新一代/HDC 1.0 通道切换回调"""
        channel = self.gw_channel_combo.currentData()
        if self.current_protocol == 11:
            self._hdc10_channel = channel or "plc"
        else:
            self._gw_channel = channel or "plc"
        # 自动重解析
        if self.single_input.toPlainText().strip():
            self.parse_single()

    def _toggle_llm_panel(self):
        """切换 LLM 预处理面板的显示/隐藏"""
        widget = self.llm_preprocess_widget
        btn = self.llm_toggle_btn
        if widget.isVisible():
            widget.hide()
            btn.setText("▶ LLM 智能预处理")
            btn.setChecked(False)
        else:
            widget.show()
            btn.setText("▼ LLM 智能预处理")
            btn.setChecked(True)
            # 刷新模型列表（可能刚在 API 管理中添加了新配置）
            widget._refresh_profiles()

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

        elif self.current_protocol == 11:
            # HDC 1.0 双模互联互通：报文ID查询
            self.tab_widget.setTabText(lookup_tab_index, "报文ID查询")
            self._create_hdc10_lookup_content(self.protocol_lookup_tab_layout)

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
        self.oad_stats_label = self._make_stats_label()
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
        table_font = self._ui_font(-2)
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
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)

        self.csg_new_gen_search = QLineEdit()
        self.csg_new_gen_search.setPlaceholderText("输入关键词搜索业务标识（如：确认、数据传输、命令...）")
        self.csg_new_gen_search.setFont(self._ui_font(0))
        self.csg_new_gen_search.textChanged.connect(self._load_csg_new_gen_map_data)
        search_layout.addWidget(self.csg_new_gen_search)
        layout.addLayout(search_layout)

        # 统计标签
        self.csg_new_gen_stats_label = QLabel()
        self.csg_new_gen_stats_label.setFont(self._ui_font(-1))
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
        table_font = self._ui_font(-2)
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
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)
        self.gw_new_gen_search = QLineEdit()
        self.gw_new_gen_search.setPlaceholderText("输入关键词搜索报文ID/端口号/消息类型...")
        self.gw_new_gen_search.setFont(self._ui_font(0))
        self.gw_new_gen_search.textChanged.connect(self._load_gw_new_gen_map_data)
        search_layout.addWidget(self.gw_new_gen_search)
        layout.addLayout(search_layout)

        self.gw_new_gen_stats_label = QLabel()
        self.gw_new_gen_stats_label.setFont(self._ui_font(-1))
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

    def _create_hdc10_lookup_content(self, layout):
        """创建HDC 1.0双模互联互通报文ID查询页面内容"""
        from hdc10_parser import (
            HDC10Parser, MSG_ID_NAMES, APP_PORTS, DELIMITER_TYPES,
            MSDU_TYPES, PROTOCOL_TYPES, TX_TYPES, BROADCAST_DIRS, SECURITY_MODES
        )
        parser = HDC10Parser()

        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)
        self.hdc10_search = QLineEdit()
        self.hdc10_search.setPlaceholderText("输入关键词搜索报文ID/端口号/消息类型...")
        self.hdc10_search.setFont(self._ui_font(0))
        self.hdc10_search.textChanged.connect(self._load_hdc10_map_data)
        search_layout.addWidget(self.hdc10_search)
        layout.addLayout(search_layout)

        self.hdc10_stats_label = QLabel()
        self.hdc10_stats_label.setFont(self._ui_font(-1))
        layout.addWidget(self.hdc10_stats_label)

        self.hdc10_table = QTableWidget()
        self.hdc10_table.setColumnCount(4)
        self.hdc10_table.setHorizontalHeaderLabels(["分类", "代码", "名称", "说明"])
        self.hdc10_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.hdc10_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.hdc10_table.setAlternatingRowColors(True)
        self.hdc10_table.verticalHeader().hide()
        self.hdc10_table.verticalHeader().setDefaultSectionSize(20)
        header = self.hdc10_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.hdc10_table)

        self._hdc10_entries = []
        for code, name in MSG_ID_NAMES.items():
            self._hdc10_entries.append(("报文ID(业务)", f"0x{code:03X}", name, ""))
        for code, name in APP_PORTS.items():
            self._hdc10_entries.append(("报文端口号", f"0x{code:02X}", name, ""))
        for code, name in DELIMITER_TYPES.items():
            self._hdc10_entries.append(("定界符类型", str(code), name, ""))
        for code, name in MSDU_TYPES.items():
            self._hdc10_entries.append(("MSDU类型", str(code), name, ""))
        for code, name in PROTOCOL_TYPES.items():
            self._hdc10_entries.append(("规约类型", str(code), name, ""))
        for code, name in TX_TYPES.items():
            self._hdc10_entries.append(("发送类型", str(code), name, ""))
        for code, name in BROADCAST_DIRS.items():
            self._hdc10_entries.append(("广播方向", str(code), name, ""))
        for code, name in SECURITY_MODES.items():
            self._hdc10_entries.append(("安全模式", str(code), name, ""))
        self._load_hdc10_map_data()

    def _load_hdc10_map_data(self):
        """加载/过滤HDC 1.0报文ID数据"""
        search = self.hdc10_search.text().strip().lower() if hasattr(self, 'hdc10_search') else ""
        results = [e for e in self._hdc10_entries
                   if not search or search in e[0].lower() or search in e[1].lower() or search in e[2].lower()]
        self.hdc10_table.setRowCount(len(results))
        for row, (cat, code, name, note) in enumerate(results):
            self.hdc10_table.setItem(row, 0, QTableWidgetItem(cat))
            self.hdc10_table.setItem(row, 1, QTableWidgetItem(str(code)))
            self.hdc10_table.setItem(row, 2, QTableWidgetItem(name))
            self.hdc10_table.setItem(row, 3, QTableWidgetItem(note))
        self.hdc10_stats_label.setText(f"匹配 {len(results)} / {len(self._hdc10_entries)} 条记录")

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
        self.gdw_stats_label = self._make_stats_label()
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
        table_font = self._ui_font(-2)
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
        self.di_stats_label = self._make_stats_label()
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
        table_font = self._ui_font(-2)
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
        self.obis_stats_label = self._make_stats_label(size=11)
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
        table_font = self._ui_font(-2)
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
        table_font = self._ui_font(-2)
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
        self.cmd_stats_label = self._make_stats_label(size=11)
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
        table_font = self._ui_font(-2)
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

    def _get_current_parser(self, protocol_index=None, parse_level=None, frame_type=None):
        """获取当前选中的解析器

        可指定协议索引（用于热键弹窗切换协议）与解析级别覆盖
        （用于弹窗内选择解析级别，None 用主窗口当前设置）。
        """
        protocol_index = self.current_protocol if protocol_index is None else protocol_index
        if protocol_index == 0:
            return self.parser
        elif protocol_index == 1:
            return self.plc_rf_parser
        elif protocol_index == 2:  # HDLC/国网DLMS (完整HDLC帧)
            return self.hdlc_parser
        elif protocol_index == 3:  # DLMS-APDU(国网) (直接解析APDU)
            # 返回一个匿名对象，调用parse_apdu_to_table
            class APDUParserGuowang:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_apdu_to_table(data)
            return APDUParserGuowang(self.hdlc_parser)
        elif protocol_index == 4:  # DLMS Wrapper裸报文 (直接解析Wrapper+APDU)
            # 返回一个匿名对象，调用parse_wrapper_to_table
            class WrapperParser:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_wrapper_to_table(data)
            return WrapperParser(self.hdlc_parser)
        elif protocol_index == 5:  # DLMS-APDU裸报文 (直接解析APDU)
            # 返回一个匿名对象，调用parse_apdu_to_table
            class APDUParser:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser
                def parse_to_table(self, data):
                    return self.hdlc_parser.parse_apdu_to_table(data)
            return APDUParser(self.hdlc_parser)
        elif protocol_index == 6:  # DLT645-2007
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
        elif protocol_index == 7:  # 国网协议
            return self.gdw_parser
        elif protocol_index == 8:  # 698.45
            return self.dl_t698_45_parser
        elif protocol_index == 9:  # 新一代载波协议(通感一体化)
            # 包装解析器以传递解析级别参数（弹窗覆盖优先，否则用主窗口设置）
            csg_parser = self.csg_new_gen_parser
            if parse_level is None:
                parse_level = getattr(self, '_csg_parse_level', 'auto')
            # pb_only模式下获取帧类型（未指定时用主窗口 combo）
            if frame_type is None and parse_level == 'pb_only':
                frame_type = self.csg_pb_frame_type_combo.currentData()
            class CSGGenGuiParser:
                def __init__(self, parser, level, ftype=None, channel='plc'):
                    self.parser = parser
                    self.level = level
                    self.frame_type = ftype
                    self.channel = channel
                def parse_to_table(self, data):
                    kwargs = {'parse_level': self.level, 'channel': self.channel}
                    if self.frame_type is not None:
                        kwargs['pb_frame_type'] = self.frame_type
                    return self.parser.parse_to_table(data, **kwargs)
            csg_channel = getattr(self, '_csg_channel', 'auto')
            return CSGGenGuiParser(csg_parser, parse_level, frame_type, csg_channel)
        elif protocol_index == 10:  # 国网新一代双模通信互联互通
            # 包装解析器以传递解析级别参数（弹窗覆盖优先，否则用主窗口设置）
            gw_parser = self.gw_new_gen_parser
            if parse_level is None:
                parse_level = getattr(self, '_gw_parse_level', 'auto')
            # pb_only模式下获取帧类型（未指定时用主窗口 combo）
            if frame_type is None and parse_level == 'pb_only':
                frame_type = self.gw_pb_frame_type_combo.currentData()
            class GWGenGuiParser:
                def __init__(self, parser, level, ftype=None, channel='plc'):
                    self.parser = parser
                    self.level = level
                    self.frame_type = ftype
                    self.channel = channel
                def parse_to_table(self, data):
                    kwargs = {'parse_level': self.level, 'channel': self.channel}
                    if self.frame_type is not None:
                        kwargs['frame_type'] = self.frame_type
                    return self.parser.parse_to_table(data, **kwargs)
            gw_channel = getattr(self, '_gw_channel', 'plc')
            return GWGenGuiParser(gw_parser, parse_level, frame_type, gw_channel)

        elif protocol_index == 11:  # HDC 1.0 双模互联互通
            hdc10_parser = self.hdc10_parser
            if parse_level is None:
                parse_level = getattr(self, '_hdc10_parse_level', 'auto')
            if frame_type is None and parse_level == 'pb_only':
                frame_type = self.gw_pb_frame_type_combo.currentData()
            class HDC10GuiParser:
                def __init__(self, parser, level, ftype=None, channel='plc'):
                    self.parser = parser
                    self.level = level
                    self.frame_type = ftype
                    self.channel = channel
                def parse_to_table(self, data):
                    kwargs = {'parse_level': self.level, 'channel': self.channel}
                    if self.frame_type is not None:
                        kwargs['frame_type'] = self.frame_type
                    return self.parser.parse_to_table(data, **kwargs)
            hdc10_channel = getattr(self, '_hdc10_channel', 'plc')
            return HDC10GuiParser(hdc10_parser, parse_level, frame_type, hdc10_channel)

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

    @staticmethod
    def _reverse_4byte_groups(hex_str: str) -> str:
        """4字节一组做端序翻转（大端↔小端）。

        输入纯 hex 字符串，按每 8 个字符（4 字节）为一组，
        组内字节顺序反转。不足 4 字节的尾部保持原样。

        例：C9D50438 00000556 → 3804D5C9 56050000
        """
        result = []
        n = len(hex_str)
        i = 0
        while i < n:
            group = hex_str[i:i + 8]
            if len(group) == 8:
                # 字节序反转: 字节0字节1字节2字节3 → 字节3字节2字节1字节0
                result.append(group[6:8] + group[4:6] + group[2:4] + group[0:2])
            else:
                result.append(group)
            i += 8
        return ''.join(result)

    # 新一代载波协议监控日志前缀标记与监控头长度
    # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <N字节监控头> <协议报文>"
    # 实际报文从标记后的第 16 个字节（1-based）开始，即需要跳过 15 字节监控头
    CSG_MONITOR_PREFIX = "> 接收机 Has Get"
    CSG_MONITOR_HEADER_BYTES = 15  # 标记之后需跳过的监控头字节数

    def _strip_csg_monitor_prefix(self, text: str) -> str:
        """剥离新一代载波协议监控日志前缀（仅在协议8批量解析时调用）

        监控日志格式示例:
            15:49:51 254  -> 接收机 Has Get ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 69 19 09 ...
                                                      ^^^^^^^^^^^^^^^ 15字节监控头 ^^^^^^^^^^^^^^^^
                                                                                      ^ 第16字节(69)开始为真实协议报文

        处理规则（逐行）:
          1. 仅保留含 "> 接收机 Has Get" 标记的行，其余行（时间戳、测试标记、
             纯文本日志、空行等）全部丢弃，避免被 _clean_hex_input 误清洗成伪帧
          2. 对保留的行：定位标记，取其后内容，跳过前 15 字节监控头，
             从第 16 字节开始保留作为协议报文

        注意：必须在 _clean_hex_input 之前调用，否则标记中的中文/箭头会被清洗掉，
        导致无法定位监控头边界。
        """
        import re
        prefix = self.CSG_MONITOR_PREFIX
        prefix_len = len(prefix)

        out_lines = []
        for line in text.splitlines():
            pos = line.find(prefix)
            if pos == -1:
                # 不含监控标记的行：直接丢弃（时间戳/测试标记/纯文本日志等）
                continue
            # 标记之后的内容
            after = line[pos + prefix_len:]
            # 提取连续 hex token（容忍空格/多空格/非hex分隔符）
            tokens = re.findall(r'[0-9A-Fa-f]{1,2}', after)
            # 跳过 15 字节监控头，从第 16 字节开始保留协议报文
            payload_tokens = tokens[self.CSG_MONITOR_HEADER_BYTES:]
            if payload_tokens:
                out_lines.append(' '.join(payload_tokens))
        return '\n'.join(out_lines)

    def _strip_gw_new_gen_prefix(self, text: str) -> str:
        """剥离国网新一代双模协议日志前缀（仅在协议10批量解析时调用）

        日志格式示例:
            Line 339: 260718-111145-349: B1D[3] mrd:ar[75]:110300000132F303420D2305683D0043...

        处理规则:
          1. 以 fc_payload_data := ' 开头，' 后跟空白或 } 结尾为一个完整帧
          2. 帧可能跨多行，中间所有 hex 拼接为一个完整帧
          3. 无引号包裹的行：取最后一个冒号后的 hex
          4. 清理非 hex 字符，若解析级别为 app 则扫描 '11' 定位应用层起始
          5. 过短（<4 hex字符）的帧丢弃

        注意：必须在 _clean_hex_input 之前调用，否则前缀中的数字会被误当作 hex 数据。
        """
        import re
        parse_level = getattr(self, '_gw_parse_level', 'auto')
        out_lines = []

        # ── 状态机：提取所有完整 hex 帧 ──
        hex_frames = []
        in_payload = False    # 是否在引号包裹的 payload 内
        payload_hex = ""      # 当前 payload 累积的 hex

        for line in text.splitlines():
            line_s = line.strip()
            if not line_s:
                continue

            # ── 在 payload 引号内：收集 hex 直到闭合引号 ──
            if in_payload:
                # 查找闭合引号: ' 后跟空白或 } (如 '0 3", 'O }", 'O}")
                close_match = re.search(r"'\s*[}]?", line_s)
                if close_match:
                    before_close = line_s[:close_match.start()]
                    payload_hex += re.sub(r'[^0-9A-Fa-f]', '', before_close).upper()
                    in_payload = False
                    if len(payload_hex) >= 4:
                        hex_frames.append(payload_hex)
                    payload_hex = ""
                else:
                    # 无闭合引号：整行都是 hex 数据（可能还有下一行）
                    payload_hex += re.sub(r'[^0-9A-Fa-f]', '', line_s).upper()
                continue

            # ── 检测 payload 起始：fc_payload_data := ' 或类似的引号开启 ──
            payload_start = re.search(r"fc_payload_data\s*:=\s*['\"]", line_s)
            if payload_start:
                after_quote = line_s[payload_start.end():]
                # 同行内是否有闭合引号？
                close_match = re.search(r"'\s*[}]?", after_quote)
                if close_match:
                    hex_clean = re.sub(r'[^0-9A-Fa-f]', '', after_quote[:close_match.start()]).upper()
                    if len(hex_clean) >= 4:
                        hex_frames.append(hex_clean)
                else:
                    # 引号跨行
                    payload_hex = re.sub(r'[^0-9A-Fa-f]', '', after_quote).upper()
                    in_payload = True
                continue

            # ── 普通行：取最后一个冒号后的 hex ──
            last_colon = line_s.rfind(':')
            hex_part = line_s[last_colon + 1:].strip() if last_colon >= 0 else line_s
            # 若行内含引号（闭合引号残留），只取引号前
            quote_pos = -1
            for q in ("'", '"'):
                p = hex_part.find(q)
                if p >= 0 and (quote_pos < 0 or p < quote_pos):
                    quote_pos = p
            if quote_pos >= 0:
                hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part[:quote_pos]).upper()
            else:
                hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part).upper()
            if len(hex_clean) >= 4:
                hex_frames.append(hex_clean)

        # 处理尾部残留（引号未闭合的不完整帧）
        if payload_hex and len(payload_hex) >= 4:
            hex_frames.append(payload_hex)

        # ── 按解析级别定位帧起始 ──
        for hex_clean in hex_frames:
            if parse_level == 'app':
                found = False
                i = 0
                while i < len(hex_clean) - 1:
                    if hex_clean[i:i+2] == '11' and len(hex_clean) - i >= 8:
                        hex_clean = hex_clean[i:]
                        found = True
                        break
                    i += 2
                if not found:
                    continue
            out_lines.append(hex_clean)

        return '\n'.join(out_lines)

    def _strip_csg_new_gen_frame_prefix(self, text: str, parse_level: str = "auto") -> str:
        """南网新一代通感一体化批量解析预处理（在 _clean_hex_input 之前调用）

        主动定位帧起始并剔除非报文内容，逻辑对齐国网新一代 _strip_gw_new_gen_prefix，
        但依据南网帧结构与物理块头(4字节)特征：

        - 若文本含监控日志标记 ``> 接收机 Has Get``：沿用 _strip_csg_monitor_prefix，
          仅保留监控行并剥离 15 字节监控头（保留既有已测行为）。
        - 否则按行处理：取最后一个冒号后的 hex（兼容 "Line XXX: ...: hex" 日志），
          清洗为纯 hex，再按解析级别定位帧起始：
            * fc_pb / fc_only / fc_efc / auto  → 扫描 FC 起始特征字节
              (bit3=接入指示=1, bits0-2=定界符类型∈{0,1,2,3}，即低4位∈{0x8,0x9,0xA,0xB})
              如典型 SOF 起始 0x09 / 0x89 ...
            * pb_only  → 输入即物理块本身，直接保留整行（无FC签名）
            * app      → 扫描端口 0x11 定位应用层报文起始
          过短的行（<4 hex字符）直接丢弃。
        - TCP 包装报文：检测 ``EDA5`` 固定前缀，从 ``ED`` 偏移 15 字节（30 hex字符）定位 FC 起始，
          剥离 15 字节 TCP 包装头后即为 FC+PB 帧数据（适用于除 pb_only 外的所有级别）。
        """
        import re
        # 监控日志格式：沿用已有逻辑（仅保留监控行，剥离监控头）
        if self.CSG_MONITOR_PREFIX in text:
            return self._strip_csg_monitor_prefix(text)

        out_lines = []

        # ── 状态机：提取所有完整 hex 帧（支持跨行引号包裹） ──
        hex_frames = []
        in_payload = False    # 是否在引号包裹的 payload 内
        payload_hex = ""      # 当前 payload 累积的 hex

        for line in text.splitlines():
            line_s = line.strip()
            if not line_s:
                continue

            # ── 在 payload 引号内：收集 hex 直到闭合引号 ──
            if in_payload:
                close_match = re.search(r"'\s*[}]?", line_s)
                if close_match:
                    before_close = line_s[:close_match.start()]
                    payload_hex += re.sub(r'[^0-9A-Fa-f]', '', before_close).upper()
                    in_payload = False
                    if len(payload_hex) >= 4:
                        hex_frames.append(payload_hex)
                    payload_hex = ""
                else:
                    payload_hex += re.sub(r'[^0-9A-Fa-f]', '', line_s).upper()
                continue

            # ── 检测 payload 起始：fc_payload_data := ' ──
            payload_start = re.search(r"fc_payload_data\s*:=\s*['\"]", line_s)
            if payload_start:
                after_quote = line_s[payload_start.end():]
                close_match = re.search(r"'\s*[}]?", after_quote)
                if close_match:
                    hex_clean = re.sub(r'[^0-9A-Fa-f]', '', after_quote[:close_match.start()]).upper()
                    if len(hex_clean) >= 4:
                        hex_frames.append(hex_clean)
                else:
                    payload_hex = re.sub(r'[^0-9A-Fa-f]', '', after_quote).upper()
                    in_payload = True
                continue

            # ── 普通行：取最后一个冒号后的 hex ──
            last_colon = line_s.rfind(':')
            hex_part = line_s[last_colon + 1:].strip() if last_colon >= 0 else line_s
            quote_pos = -1
            for q in ("'", '"'):
                p = hex_part.find(q)
                if p >= 0 and (quote_pos < 0 or p < quote_pos):
                    quote_pos = p
            if quote_pos >= 0:
                hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part[:quote_pos]).upper()
            else:
                hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part).upper()
            if len(hex_clean) >= 4:
                hex_frames.append(hex_clean)

        if payload_hex and len(payload_hex) >= 4:
            hex_frames.append(payload_hex)

        # ── 按解析级别定位帧起始 ──
        for hex_clean in hex_frames:
            # 检测 TCP 包装前缀 EDA5：从 ED 偏移 15 字节(30 hex)定位 FC 起始
            if parse_level != "pb_only" and hex_clean.startswith("EDA5"):
                if len(hex_clean) >= 62:
                    hex_clean = hex_clean[30:]
                    out_lines.append(hex_clean)
                continue

            if parse_level == "pb_only":
                pass  # 直接保留
            elif parse_level == "app":
                found = False
                i = 0
                while i + 32 <= len(hex_clean):
                    if hex_clean[i:i+2] == '11' and len(hex_clean) - i >= 8:
                        hex_clean = hex_clean[i:]
                        found = True
                        break
                    i += 2
                if not found:
                    continue
            else:
                if hex_clean.startswith("ED"):
                    pass  # ED 包装帧直接保留
                else:
                    found = False
                    i = 0
                    while i + 32 <= len(hex_clean):
                        byte_val = int(hex_clean[i:i+2], 16)
                        low = byte_val & 0x0F
                        if low in (0x08, 0x09, 0x0A, 0x0B):
                            hex_clean = hex_clean[i:]
                            found = True
                            break
                        i += 2
                    if not found:
                        continue
            out_lines.append(hex_clean)

        return '\n'.join(out_lines)


    # ── PLC2.0 收发机监控包装头(ED..EE)解析 ──
    # 常量定义（与 monitor_widget 保持一致）
    _PLC2_CTRL1_NAMES = {0x00: "数据报文", 0x01: "控制报文"}
    _PLC2_CTRL2_DATA_NAMES = {
        0x01: "FC数据", 0x02: "FC+Payload数据", 0x03: "Payload数据",
        0x04: "发送完成", 0x05: "选择确认帧发送完成",
        0x06: "RF和HPLC同时发送FC+Payload", 0x07: "FC+Payload数据",
        0x08: "UL-OFDMA帧(DL-OFDMA的SACK帧)",
    }
    _PLC2_CHANNEL_NAMES = {
        0x01: "HPLC", 0x02: "RF", 0x03: "HPLC+RF", 0x20: "PLC2.0 OFDMA",
    }

    def _plc2_channel_name(self, ch: int) -> str:
        if ch in self._PLC2_CHANNEL_NAMES:
            return self._PLC2_CHANNEL_NAMES[ch]
        if 0x10 <= ch <= 0x1C:
            return f"PLC2.0 MIMO(0x{ch:02X})"
        return f"保留(0x{ch:02X})"

    def _parse_ed_monitor_header(self, frame_bytes: bytes):
        """解析 ED..EE PLC2.0 监控包装头

        包结构: ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)
        数据报文(ctrl1=0x00) ctrl2=0x01/0x02/0x03 的数据域公共头(9字节):
          物理信道(1)+时间戳(4,LE)+物理块个数(1)+保留/CRC(1)+单个物理块长度(2,LE)

        Returns:
            (meta_rows, business_bytes, business_offset) 成功时返回前置行列表、业务字节、
                业务字节在原始帧中的偏移量
            (None, None, None) 帧不是有效的 ED 包装格式
        """
        n = len(frame_bytes)
        if n < 8 or frame_bytes[0] != 0xED:
            return None, None, None

        frame_len = frame_bytes[1] | (frame_bytes[2] << 8)  # = 数据域长度 + 4
        if frame_len < 4 or frame_len > 4096:
            return None, None, None
        total = frame_len + 4  # ED(1)+帧长(2)+[控制域1..CS=帧长]+EE(1)
        if total > n:
            return None, None, None
        # 强定界校验
        if frame_bytes[5] != 0xEF or frame_bytes[total - 1] != 0xEE:
            return None, None, None

        ctrl1 = frame_bytes[3]
        ctrl2 = frame_bytes[4]
        data_len = frame_len - 4
        data_start = 6
        data = frame_bytes[data_start:data_start + data_len]
        cs_offset = data_start + data_len
        cs = frame_bytes[cs_offset]
        ee_offset = total - 1
        calc_cs = sum(frame_bytes[:cs_offset]) & 0xFF

        ctrl1_name = self._PLC2_CTRL1_NAMES.get(ctrl1, f"保留(0x{ctrl1:02X})")
        ctrl2_name = (self._PLC2_CTRL2_DATA_NAMES if ctrl1 == 0x00 else {}).get(
            ctrl2, f"保留(0x{ctrl2:02X})")
        cs_txt = "✓ 正确" if cs == calc_cs else ("保留(0xFF)" if cs == 0xFF else "✗ 错误")

        rows = [
            ("── PLC2.0 监控包装头 ──", "", "", "ED..EE 监控设备附加信息（不属于业务帧）", None, None),
            ("起始符(ED)", f"0x{frame_bytes[0]:02X}", "ED", "PLC2.0 收发机包装起始标识", 0, 0),
            ("帧长", f"{frame_bytes[1]:02X} {frame_bytes[2]:02X}", f"{frame_len} 字节",
             "控制域1+控制域2+EF+数据域+CS(小端)", 1, 2),
            ("控制域1", f"0x{ctrl1:02X}", ctrl1_name, "0x00-数据报文 0x01-控制报文", 3, 3),
            ("控制域2", f"0x{ctrl2:02X}", ctrl2_name, "报文子类型", 4, 4),
            ("数据域起始符(EF)", f"0x{frame_bytes[5]:02X}", "EF", "数据域起始标识", 5, 5),
            ("数据域长度", str(data_len), f"{data_len} 字节", f"字节 {data_start}~{cs_offset-1}", data_start, cs_offset - 1),
        ]

        business = b""
        business_offset = data_start  # 默认偏移
        # 数据报文 0x01/0x02/0x03：解析 9 字节公共头
        if ctrl1 == 0x00 and ctrl2 in (0x01, 0x02, 0x03) and data_len >= 9:
            ch = data[0]
            ts = int.from_bytes(data[1:5], "little")
            pb_cnt = data[5]
            flag6 = data[6]
            pb_len = int.from_bytes(data[7:9], "little")
            business = data[9:]
            business_offset = data_start + 9  # 业务帧从数据域第10字节开始
            crc_txt = "错误" if (ctrl2 == 0x02 and flag6 == 1) else "正确/保留"
            rows += [
                ("物理信道", f"0x{ch:02X}", self._plc2_channel_name(ch),
                 "0x01-HPLC 0x02-RF 0x03-HPLC+RF 0x10~0x1C-MIMO 0x20-OFDMA",
                 data_start, data_start),
                ("时间戳", f"0x{ts:08X}", str(ts), "HW→PC 接收开始时间(小端)",
                 data_start + 1, data_start + 4),
                ("物理块个数", str(pb_cnt), str(pb_cnt), None,
                 data_start + 5, data_start + 5),
                ("Payload CRC", f"0x{flag6:02X}", crc_txt,
                 "ctrl2=0x02时: 0-正确 1-错误；其余保留",
                 data_start + 6, data_start + 6),
                ("单个物理块长度", str(pb_len), f"{pb_len} 字节(小端)", None,
                 data_start + 7, data_start + 8),
            ]
        else:
            business = data

        rows += [
            ("校验(CS)", f"0x{cs:02X}", cs_txt,
             "ED..数据域末所有字节求和取低8bit", cs_offset, cs_offset),
            ("结束符(EE)", f"0x{frame_bytes[ee_offset]:02X}", "EE", "PLC2.0 包装结束标识", ee_offset, ee_offset),
            ("── 业务帧 ──", "", "", "以下为载波业务帧解析结果", business_offset, cs_offset - 1),
        ]

        return rows, business, business_offset


    def parse_single(self):
        """解析单帧报文"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 清理输入（支持空格、逗号、换行等分隔符）
        clean_input = self._clean_hex_input(input_text)
        clean_input = clean_input.strip()

        # 4字节反转（仅南网新一代 + 勾选时）
        if (self.current_protocol == 9
                and hasattr(self, 'csg_reverse_4byte_chk')
                and self.csg_reverse_4byte_chk.isChecked()
                and clean_input):
            clean_input = self._reverse_4byte_groups(clean_input)

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

            # ED 监控协议头解析（仅南网新一代协议 + 勾选项启用时）
            full_frame_bytes = frame_bytes  # 保存完整帧（用于高亮定位和 current_result）
            ed_meta_rows = None
            ed_business_offset = 0
            ed_mode = (self.current_protocol == 9
                       and self.ed_monitor_chk.isChecked()
                       and len(frame_bytes) >= 1
                       and frame_bytes[0] == 0xED)
            if ed_mode:
                ed_rows, business, ed_business_offset = self._parse_ed_monitor_header(frame_bytes)
                if ed_rows is None or business is None:
                    declared = (frame_bytes[1] | (frame_bytes[2] << 8)) + 4 if len(frame_bytes) >= 3 else 0
                    msg = ("ED 监控帧解析失败：报文不完整或格式错误。\n"
                           "已勾选「ED监控协议」，首字节 ED 不能作为业务帧起始符解析。\n"
                           "请检查报文是否被截断（帧长字段声明整包应为 %d 字节，实际 %d 字节），"
                           "或缺少 EF 数据域起始符 / EE 结束符。" % (declared, len(frame_bytes)))
                    QMessageBox.critical(self, "ED 监控帧错误", msg)
                    return
                ed_meta_rows = ed_rows
                frame_bytes = business  # 后续解析使用业务载荷
                # 不替换 hex_display，保持输入框显示完整帧

            # 使用当前选中的解析器
            current_parser = self._get_current_parser()
            table_data = current_parser.parse_to_table(frame_bytes)
            # ED 监控头前置 + 业务行偏移修正
            if ed_meta_rows:
                # 业务行的 byte_start/byte_end 需要加上 ED 头偏移
                shifted_table = []
                for row in table_data:
                    if len(row) >= 6 and row[4] is not None and row[5] is not None:
                        shifted_row = (
                            row[0], row[1], row[2], row[3],
                            row[4] + ed_business_offset,
                            row[5] + ed_business_offset,
                        )
                        # 处理可能的第 7 个元素 (is_child)
                        if len(row) > 6:
                            shifted_row = shifted_row + (row[6],)
                        shifted_table.append(shifted_row)
                    else:
                        shifted_table.append(row)
                table_data = ed_meta_rows + shifted_table
            self._populate_table_from_data(table_data)

            # 保存当前结果（使用完整帧，确保高亮和双击提取正确）
            self.current_result = full_frame_bytes
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
            from validator.hdc10_validator import HDC10Validator
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
                11: HDC10Validator(),   # HDC 1.0 双模互联互通
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

    def _setup_table_copy_menu(self, table: QTableWidget):
        """为解析结果表格设置右键复制菜单和 Ctrl+C 快捷键"""
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_table_copy_menu(t, pos)
        )
        # Ctrl+C 快捷键
        shortcut = QShortcut(QKeySequence.Copy, table)
        shortcut.setContext(Qt.WidgetShortcut)
        shortcut.activated.connect(lambda t=table: self._copy_table_rows(t, all_rows=False))

    def _show_table_copy_menu(self, table: QTableWidget, pos):
        """显示表格右键复制菜单"""
        menu = QMenu(table)
        has_selection = len(table.selectedItems()) > 0

        copy_sel = menu.addAction("复制选中行")
        copy_sel.setEnabled(has_selection)
        copy_sel.triggered.connect(lambda: self._copy_table_rows(table, all_rows=False))

        copy_all = menu.addAction("复制全部")
        copy_all.triggered.connect(lambda: self._copy_table_rows(table, all_rows=True))

        menu.exec(table.mapToGlobal(pos))

    def _copy_table_rows(self, table: QTableWidget, all_rows: bool = False):
        """将表格行复制到剪贴板（制表符分隔，含表头）"""
        col_count = table.columnCount()
        row_count = table.rowCount()

        # 收集需要复制的行号
        if all_rows:
            rows = list(range(row_count))
        else:
            selected = table.selectedIndexes()
            if not selected:
                # 无选中时退化为全部
                rows = list(range(row_count))
            else:
                row_set = sorted({idx.row() for idx in selected})
                rows = row_set

        if not rows:
            return

        # 表头
        headers = []
        for c in range(col_count):
            item = table.horizontalHeaderItem(c)
            headers.append(item.text() if item else "")
        lines = ["\t".join(headers)]

        # 数据行
        for r in rows:
            cells = []
            for c in range(col_count):
                item = table.item(r, c)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        text = "\n".join(lines)
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)

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
        theme_action = config_menu.addAction("主题与字体(&T)...")
        theme_action.triggered.connect(self._show_theme_settings_dialog)
        sys_action = config_menu.addAction("系统集成设置(&S)...")
        sys_action.triggered.connect(self._show_system_settings_dialog)
        llm_api_action = config_menu.addAction("模型API管理(&M)...")
        llm_api_action.triggered.connect(self._show_llm_api_manager)

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
        title_label.setFont(self._ui_font(6, bold=True))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"版本 2.0")
        version_label.setFont(self._ui_font(1))
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #666;")
        layout.addWidget(version_label)

        desc_label = QLabel("支持南网协议 / PLC RF / HDLC/DLMS 多协议报文解析")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        author_label = QLabel("作者: liruitao")
        author_label.setFont(self._ui_font(0))
        author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_label.setStyleSheet("color: #888;")
        layout.addWidget(author_label)

        changelog_label = QLabel("版本更新记录")
        changelog_label.setFont(self._ui_font(0, bold=True))
        layout.addWidget(changelog_label)

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setFont(self._ui_font(-1))

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

    # ==================== 系统集成（托盘 / 热键 / 单实例 / 命令行） ====================

    def _setup_system_integration(self):
        """初始化系统托盘、全局热键、单实例监听（在 setup_ui 之后调用）"""
        # 系统托盘
        self._tray_manager = None
        self._hotkey_manager = None
        self._single_instance = None
        self._tray_exit = False  # 托盘"退出"标志：true 时 closeEvent 真正退出

        icon_path = str(Path(__file__).parent / "app_icon.ico")
        tray = SystemTrayManager(self)
        if tray.create(icon_path):
            self._tray_manager = tray
            tray.show_requested.connect(self._tray_show_window)
            tray.exit_requested.connect(self._tray_exit_app)
            tray.autostart_toggled.connect(self._on_tray_autostart_toggled)
            tray.update_autostart_state()

        # 全局热键
        self._hotkey_manager = GlobalHotkeyManager(
            self._system_settings.get("hotkey", "Ctrl+Alt+X")
        )
        self._hotkey_manager.set_callback(self._on_global_hotkey)
        self._restart_hotkey()

        # 单实例监听
        self._single_instance = SingleInstanceServer(self)
        self._single_instance.args_received.connect(self._on_second_instance_args)

        # 剪贴板监听（检测其他软件复制的 hex 报文 → 弹提示框）
        self._clipboard_monitor = ClipboardMonitor(self)
        self._clipboard_monitor.hex_ready.connect(self._on_clipboard_hex)
        self._clipboard_monitor.set_enabled(
            bool(self._system_settings.get("clipboard_monitor", True))
        )
        self._clipboard_monitor.start()

    def _on_clipboard_hex(self, frame_bytes: bytes, hex_str: str, detected_protocol):
        """剪贴板检测到 hex 报文 → 弹提示框（单实例复用，避免堆积）"""
        # 去重：主窗口自身解析填入剪贴板时不弹
        if hasattr(self, '_last_parsed_hex') and self._last_parsed_hex:
            own = self._last_parsed_hex.replace(' ', '').lower()
            if own == hex_str.lower():
                return

        # 复用已存在的提示框：更新内容而非新建（防止多次复制后窗口堆叠）
        if hasattr(self, '_prompt_dialog') and self._prompt_dialog is not None:
            try:
                if self._prompt_dialog.isVisible():
                    self._prompt_dialog.update_content(
                        frame_bytes, hex_str, detected_protocol)
                    return
            except RuntimeError:
                pass  # C++ 对象已删除，重新创建

        dialog = ParsePromptDialog(frame_bytes, hex_str, detected_protocol, self)
        self._prompt_dialog = dialog
        # 关闭后清理引用，避免悬空
        dialog.destroyed.connect(lambda *_: self._clear_prompt_ref(dialog))
        # 填充协议下拉（11 协议）
        items = []
        for i in range(self.protocol_combo.count()):
            items.append((self.protocol_combo.itemText(i), i))
        dialog.add_protocols(items)
        # 显示（非模态 + 置顶，不阻塞主窗口）
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        # 解析确认后打开解析窗口
        dialog.accepted.connect(
            lambda d=dialog: self._open_prompt_parse(d.get_selection())
        )

    def _clear_prompt_ref(self, dialog):
        """提示框销毁时清引用"""
        if getattr(self, '_prompt_dialog', None) is dialog:
            self._prompt_dialog = None

    def _open_prompt_parse(self, selection):
        """提示框确认解析：按所选协议打开解析窗口（不弹主窗口）"""
        frame_bytes, proto_idx = selection
        if proto_idx is None:
            proto_idx = self.current_protocol
        # 不显示主窗口，直接弹解析结果窗口（避免窗口太多）
        self._parse_and_show_dialog(frame_bytes, initial_protocol=proto_idx)

    def _restart_hotkey(self):
        """按当前设置启动/停止全局热键监听"""
        if not hasattr(self, "_hotkey_manager") or self._hotkey_manager is None:
            return
        enabled = bool(self._system_settings.get("hotkey_enabled", True))
        if enabled:
            hotkey = self._system_settings.get("hotkey", "Ctrl+Alt+X")
            self._hotkey_manager.set_hotkey(hotkey)
            ok = self._hotkey_manager.start()
            if not ok:
                print(f"[全局热键] 注册失败，请检查热键格式或是否被占用: {hotkey}")
        else:
            self._hotkey_manager.stop()

    def _on_tray_autostart_toggled(self, enabled: bool):
        """托盘菜单中"开机自启"开关被切换"""
        self._system_settings["auto_start"] = bool(enabled)
        try:
            from system_integration.registry_menu import set_autostart
            set_autostart(bool(enabled))
            # 同步写回 config.json
            try:
                config = {}
                if self._config_path.exists():
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                config["system"] = self._system_settings
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[系统设置保存失败] {e}")
        except Exception as e:
            print(f"[开机自启设置失败] {e}")

    def _tray_show_window(self):
        """托盘"显示主窗口"：显示并置顶"""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_exit_app(self):
        """托盘"退出"：真正退出程序"""
        self._tray_exit = True
        self.close()

    def closeEvent(self, event):
        """关闭窗口：若启用托盘且非主动退出，最小化到托盘"""
        if (self._tray_manager is not None and not self._tray_exit
                and self._system_settings.get("close_to_tray", True)):
            event.ignore()
            self.hide()
            self._tray_manager.show_hint_once()
            return
        # 清理托盘与热键
        if self._tray_manager is not None:
            self._tray_manager.hide_tray()
        if self._hotkey_manager is not None:
            self._hotkey_manager.stop()
        event.accept()

    def _on_global_hotkey(self):
        """全局热键触发：读取剪贴板 hex → 按当前协议解析 → 弹窗"""
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text()
        if not text or not text.strip():
            QMessageBox.information(self, "全局热键", "剪贴板为空，请先复制报文。")
            return
        clean = self._clean_hex_input(text)
        clean = clean.strip()
        if len(clean) % 2 != 0 or not all(c in '0123456789abcdefABCDEF' for c in clean):
            QMessageBox.information(self, "全局热键", "剪贴板内容不是有效的十六进制报文。")
            return
        try:
            frame_bytes = bytes.fromhex(clean)
        except Exception:
            QMessageBox.information(self, "全局热键", "剪贴板内容不是有效的十六进制报文。")
            return
        self._parse_and_show_dialog(frame_bytes)

    def _parse_and_show_dialog(self, frame_bytes: bytes, initial_protocol: int = None):
        """解析字节并弹出结果对话框（热键/命令行/文件右键共用）

        顶部提供协议选择下拉，切换时用所选协议重新解析。
        新一代载波(9)/国网新一代(10)额外提供解析级别下拉 + ED 监控头自动剥离。
        initial_protocol: 初始协议索引，None 用当前主窗口协议。
        """
        if initial_protocol is None:
            initial_protocol = self.current_protocol

        dialog = QDialog(self)
        dialog.setWindowTitle("解析结果")
        dialog.resize(960, 640)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(dialog)

        # 顶部：协议选择 + 解析级别 + hex 显示
        proto_row = QHBoxLayout()
        proto_row.addWidget(QLabel("协议:"))
        proto_combo = QComboBox()
        for i in range(self.protocol_combo.count()):
            proto_combo.addItem(self.protocol_combo.itemText(i), i)
        proto_combo.setCurrentIndex(
            proto_combo.findData(initial_protocol)
            if proto_combo.findData(initial_protocol) >= 0 else 0
        )
        proto_combo.setMinimumWidth(280)
        proto_row.addWidget(proto_combo)

        # 解析级别下拉（仅 9/10 可见）：自动识别 + 各级别
        level_label = QLabel("解析级别:")
        proto_row.addWidget(level_label)
        level_combo = QComboBox()
        CSG_LEVELS = [
            ("自动识别", "auto"), ("FC+PB解析(完整MPDU)", "fc_pb"),
            ("FC+eFC解析", "fc_efc"), ("仅FC解析", "fc_only"),
            ("应用层报文", "app"), ("仅PB解析(完整物理块)", "pb_only"),
        ]
        GW_LEVELS = [
            ("自动识别", "auto"), ("仅FC解析", "fc_only"),
            ("仅MAC帧", "mac_only"), ("仅PB", "pb_only"),
            ("FC+MAC解析", "fc_mac"), ("应用层报文", "app"),
        ]
        level_combo.setVisible(False)
        level_label.setVisible(False)
        proto_row.addWidget(level_combo)

        # PB帧类型下拉（仅 pb_only 可见）
        frame_type_label = QLabel("帧类型:")
        frame_type_combo = QComboBox()
        frame_type_label.setVisible(False)
        frame_type_combo.setVisible(False)
        proto_row.addWidget(frame_type_label)
        proto_row.addWidget(frame_type_combo)
        proto_row.addStretch()
        layout.addLayout(proto_row)

        # ED 监控头剥离开关（仅 9/10 可见，默认勾选）
        ed_chk = QCheckBox("剥离ED监控头")
        ed_chk.setChecked(True)
        ed_chk.setVisible(False)
        ed_chk.setToolTip("勾选后自动识别并剥离 ED..EF..EE 监控包装头，前置显示监控信息再解析业务帧")
        layout.addWidget(ed_chk)

        hex_text = QTextEdit()
        hex_text.setReadOnly(True)
        hex_text.setFont(self._ui_font(0, family="Consolas"))
        hex_text.setMaximumHeight(70)
        hex_str = ' '.join(f'{b:02X}' for b in frame_bytes)
        hex_text.setText(f"报文: {hex_str}")
        layout.addWidget(hex_text)

        # 解析结果表格（紧凑排版，与主窗口解析表一致：小字号 + 贴合行高）
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(13)
        table_font = self._ui_font(-2)
        table.setFont(table_font)
        self._setup_table_copy_menu(table)
        layout.addWidget(table)

        error_label = QLabel()
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: #d32f2f;")
        error_label.hide()
        layout.addWidget(error_label)

        def _is_new_gen(idx):
            return idx in (9, 10)

        def _update_extras_visibility(idx):
            """按协议索引显示/隐藏解析级别、帧类型、ED监控头控件"""
            show = _is_new_gen(idx)
            level_label.setVisible(show)
            level_combo.setVisible(show)
            ed_chk.setVisible(show)
            if not show:
                frame_type_label.setVisible(False)
                frame_type_combo.setVisible(False)
                return
            # 填解析级别选项（9/10 不同）
            level_combo.blockSignals(True)
            level_combo.clear()
            levels = CSG_LEVELS if idx == 9 else GW_LEVELS
            for text, val in levels:
                level_combo.addItem(text, val)
            # 默认自动识别
            level_combo.setCurrentIndex(level_combo.findData("auto"))
            # 填帧类型选项
            frame_type_combo.blockSignals(True)
            frame_type_combo.clear()
            if idx == 9:
                for text, val in [("SOF帧", "sof"), ("信标帧", "beacon"),
                                  ("ACK帧(SACK)", "sack"), ("NET帧", "net")]:
                    frame_type_combo.addItem(text, val)
            else:
                for text, val in [("SOF帧", 1), ("信标帧", 0),
                                  ("ACK帧(SACK)", 2), ("NET帧", 3)]:
                    frame_type_combo.addItem(text, val)
            level_combo.blockSignals(False)
            frame_type_combo.blockSignals(False)
            # pb_only 时显示帧类型
            is_pb = level_combo.currentData() == "pb_only"
            frame_type_label.setVisible(show and is_pb)
            frame_type_combo.setVisible(show and is_pb)

        def _preprocess(idx, raw):
            """协议预处理：ED 监控头剥离 + 前置行。返回 (bytes, extra_rows, err)"""
            if idx not in (9, 10) or not ed_chk.isChecked() or not raw or raw[0] != 0xED:
                return raw, None, None
            declared = (raw[1] | (raw[2] << 8)) + 4 if len(raw) >= 3 else 0
            err = ("ED 监控帧解析失败：报文不完整或格式错误，"
                   "首字节 ED 不能作为业务帧起始符解析。\n"
                   "请检查报文是否被截断（帧长字段声明整包应为 %d 字节，实际 %d 字节），"
                   "或缺少 EF 数据域起始符 / EE 结束符。" % (declared, len(raw)))
            try:
                rows, business, offset = self._parse_ed_monitor_header(raw)
            except Exception:
                return None, None, err
            if rows is None or business is None:
                return None, None, err
            return business, rows, None

        def do_parse(idx=None):
            """用当前所选协议重新解析并填充表格"""
            if idx is None:
                idx = proto_combo.currentData()
            dialog.setWindowTitle(f"解析结果 - {proto_combo.currentText()}")
            table.setRowCount(0)
            error_label.hide()
            # 预处理：ED 头剥离
            parse_bytes, ed_rows, ed_err = _preprocess(idx, frame_bytes)
            if ed_err is not None:
                error_label.setText(ed_err)
                error_label.show()
                return
            try:
                kwargs = {}
                if _is_new_gen(idx):
                    kwargs["parse_level"] = level_combo.currentData()
                    if level_combo.currentData() == "pb_only":
                        kwargs["frame_type"] = frame_type_combo.currentData()
                parser = self._get_current_parser(idx, **kwargs)
                data = parser.parse_to_table(parse_bytes)
            except Exception as e:
                error_label.setText(f"解析失败（{proto_combo.currentText()}）：{str(e)}")
                error_label.show()
                return
            # ED 监控头前置行
            if ed_rows:
                data = ed_rows + list(data)
            for r, item in enumerate(data):
                table.insertRow(r)
                table.setItem(r, 0, QTableWidgetItem(str(item[0])))
                table.setItem(r, 1, QTableWidgetItem(str(item[1])))
                table.setItem(r, 2, QTableWidgetItem(str(item[2])))
                table.setItem(r, 3, QTableWidgetItem(str(item[3])))
            # 行高自适应文字内容（紧凑贴合）
            table.resizeRowsToContents()

        def _on_level_changed(_idx):
            is_pb = level_combo.currentData() == "pb_only"
            frame_type_label.setVisible(is_pb)
            frame_type_combo.setVisible(is_pb)
            do_parse()

        level_combo.currentIndexChanged.connect(_on_level_changed)
        frame_type_combo.currentIndexChanged.connect(lambda _: do_parse())
        proto_combo.currentIndexChanged.connect(
            lambda _: (_update_extras_visibility(proto_combo.currentData()), do_parse())
        )
        _update_extras_visibility(initial_protocol)
        do_parse(proto_combo.currentData())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("复制全部")
        copy_btn.clicked.connect(lambda: self._copy_table_rows(table, True))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # 显示（非模态，不阻塞）
        dialog.show()

    def _on_second_instance_args(self, args: list):
        """第二个实例发来的命令行参数：执行 + 按需激活窗口"""
        # 无参数：仅激活已有主窗口
        if not args:
            self._tray_show_window()
            return
        # 有解析动作（--parse/--file/--clipboard）：直接弹解析结果，不弹主窗口
        has_action = any(a in ("--parse", "--file", "--clipboard") for a in args)
        if not has_action:
            self._tray_show_window()
        self._handle_cli_args(args)

    def _handle_cli_args(self, args: list):
        """处理命令行参数（--parse / --protocol / --file / --minimized / --clipboard）"""
        # 解析参数
        protocol_index = None
        parse_hex = None
        file_path = None
        minimized = False
        clipboard = False
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--parse" and i + 1 < len(args):
                parse_hex = args[i + 1]
                i += 2
            elif arg == "--protocol" and i + 1 < len(args):
                protocol_index = self._protocol_name_to_index(args[i + 1])
                i += 2
            elif arg == "--file" and i + 1 < len(args):
                file_path = args[i + 1]
                i += 2
            elif arg == "--clipboard":
                clipboard = True
                i += 1
            elif arg == "--minimized":
                minimized = True
                i += 1
            else:
                i += 1

        # 切换协议
        if protocol_index is not None and 0 <= protocol_index < self.protocol_combo.count():
            self.protocol_combo.setCurrentIndex(protocol_index)

        # 最小化到托盘
        if minimized and self._tray_manager is not None:
            self.hide()
            return

        # 读剪贴板解析（NPP/UE 右键菜单、外部调用用）
        if clipboard:
            QTimer.singleShot(200, self._parse_clipboard_and_show)
            return

        # 文件解析
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                QMessageBox.critical(self, "文件读取失败", f"无法读取文件：{str(e)}")
                return
            self._parse_text_content(content)
            return

        # 直接 hex 解析
        if parse_hex:
            clean = self._clean_hex_input(parse_hex)
            if len(clean) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in clean):
                try:
                    self._parse_and_show_dialog(bytes.fromhex(clean))
                except Exception as e:
                    QMessageBox.critical(self, "解析错误", f"解析失败：{str(e)}")

    def _parse_clipboard_and_show(self):
        """读取剪贴板 hex 并弹出解析对话框（--clipboard 参数用）"""
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text() or ""
        if not text.strip():
            QMessageBox.information(self, "解析", "剪贴板为空，请先在编辑器中复制报文。")
            return
        clean = self._clean_hex_input(text)
        clean = clean.strip()
        if len(clean) % 2 != 0 or not all(c in '0123456789abcdefABCDEF' for c in clean):
            QMessageBox.information(self, "解析", "剪贴板内容不是有效的十六进制报文。")
            return
        try:
            frame_bytes = bytes.fromhex(clean)
        except Exception:
            QMessageBox.information(self, "解析", "剪贴板内容不是有效的十六进制报文。")
            return
        # 不弹主窗口，直接显示解析结果（避免窗口太多）
        self._parse_and_show_dialog(frame_bytes)

    def _protocol_name_to_index(self, name: str) -> int:
        """协议名 → protocol_combo 索引（支持中文名 / 数字索引）"""
        name = str(name).strip()
        if name.isdigit():
            return int(name)
        names = {
            "南网协议": 0, "南网": 0,
            "PLC RF协议": 1, "PLC RF": 1, "PLC": 1,
            "HDLC": 2, "HDLC/DLMS": 2,
            "DLMS-APDU国网": 3, "APDU国网": 3,
            "DLMS Wrapper": 4, "Wrapper": 4,
            "DLMS-APDU裸": 5, "APDU": 5,
            "DLT645": 6, "DLT645-2007": 6, "645": 6,
            "国网协议": 7, "国网": 7,
            "698.45": 8, "698": 8,
            "新一代载波": 9, "载波": 9,
            "国网新一代": 10, "双模": 10,
            "HDC1.0": 11, "HDC 1.0": 11, "hdc10": 11, "旧版双模": 11,
        }
        if name in names:
            return names[name]
        # 模糊匹配
        for key, idx in names.items():
            if key in name or name in key:
                return idx
        return None

    def _parse_text_content(self, content: str):
        """从文本内容提取帧并按当前协议解析，弹出结果（文件右键 / --file 共用）"""
        try:
            frames = self._extract_frames_for_protocol(content, self.current_protocol)
        except Exception:
            frames = [f.strip() for f in content.splitlines() if f.strip()]
        if not frames:
            QMessageBox.information(self, "提示", "文件中未找到可解析的报文。")
            return
        # 取第一帧解析
        first = frames[0]
        clean = self._clean_hex_input(first)
        if len(clean) % 2 != 0 or not all(c in '0123456789abcdefABCDEF' for c in clean):
            QMessageBox.information(self, "提示", "文件中未找到有效的十六进制报文。")
            return
        try:
            self._parse_and_show_dialog(bytes.fromhex(clean))
        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败：{str(e)}")

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
        self._debug_log(f"parse_batch: 输入 {len(input_text)} 字符")
        self._debug_log(f"parse_batch: 前200字符:\n{input_text[:200]}")

        # 新一代载波协议(索引9)：先剥离监控日志前缀（在 hex 清洗前处理原始文本）
        # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>"
        # 需要先识别 "-> 接收机 Has Get" 标记，去除其后 15 字节监控头，再提取协议报文
        if self.current_protocol == 9:
            before = len(input_text)
            input_text = self._strip_csg_new_gen_frame_prefix(
                input_text, getattr(self, '_csg_parse_level', 'auto'))
            self._debug_log(f"_strip_csg_new_gen_frame_prefix: {before}→{len(input_text)} 字符")
            self._debug_log(f"  前200字符:\n{input_text[:200]}")

        # 国网新一代双模协议(索引10)：剥离日志前缀（在 hex 清洗前处理原始文本）
        # 日志格式: "Line XXX: timestamp: metadata:hex_data"
        # 取最后一个冒号后的 hex 数据，app 级别时扫描 '11' 定位应用层起始
        if self.current_protocol in (10, 11):
            before = len(input_text)
            input_text = self._strip_gw_new_gen_prefix(input_text)
            self._debug_log(f"_strip_gw_new_gen_prefix: {before}→{len(input_text)} 字符")

        # 预处理：去除空格、逗号等分隔符，保留换行以区分多帧
        before = len(input_text)
        input_text = self._clean_hex_input(input_text, keep_newlines=True)
        self._debug_log(f"_clean_hex_input: {before}→{len(input_text)} 字符")
        self._debug_log(f"  keep_newlines=True, 行数={len(input_text.splitlines())}")
        # 显示每行的前 40 字符
        for i, ln in enumerate(input_text.splitlines()[:5], 1):
            self._debug_log(f"  行{i}: [{len(ln)//2:3d}B] {ln[:60]}")
        if len(input_text.splitlines()) > 5:
            self._debug_log(f"  ... 共 {len(input_text.splitlines())} 行")

        # 新一代载波协议(索引9)：先剥离监控日志前缀（在 hex 清洗前处理原始文本）
        # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>"
        # 需要先识别 "-> 接收机 Has Get" 标记，去除其后 15 字节监控头，再提取协议报文
        if self.current_protocol == 9:
            input_text = self._strip_csg_new_gen_frame_prefix(
                input_text, getattr(self, '_csg_parse_level', 'auto'))

        # 国网新一代/HDC 1.0 (索引10/11)：剥离日志前缀
        if self.current_protocol in (10, 11):
            input_text = self._strip_gw_new_gen_prefix(input_text)

        # 预处理：去除空格、逗号等分隔符，保留换行以区分多帧
        input_text = self._clean_hex_input(input_text, keep_newlines=True)

        if not input_text:
            # 区分：原始输入为空 vs 预处理/清洗后为空
            raw = self.batch_input.toPlainText().strip()
            if raw:
                QMessageBox.warning(self, "警告",
                    "预处理后未保留有效报文内容！\n\n"
                    "可能原因：\n"
                    "• 预处理命令（如 find）过滤后，匹配行不含十六进制数据\n"
                    "• 日志行中的报文内容被文本描述覆盖\n\n"
                    "建议：检查预处理命令的过滤条件，或先不执行预处理查看原始内容。")
            else:
                QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 根据当前协议选择帧提取方式
        frames = self._extract_frames_for_protocol(input_text, self.current_protocol)
        self._debug_log(f"_extract_frames_for_protocol: 找到 {len(frames)} 帧")
        for i, f in enumerate(frames[:5], 1):
            fhex = f[0] if isinstance(f, tuple) else f
            self._debug_log(f"  帧{i}: [{len(fhex)//2:3d}B] {fhex[:60]}")
        if len(frames) > 5:
            self._debug_log(f"  ... 共 {len(frames)} 帧")

        if not frames:
            # 给出更详细的诊断
            sample = input_text[:200].replace('\n', '\\n')
            QMessageBox.warning(self, "警告",
                f"未识别到有效帧！\n\n"
                f"清洗后内容（前200字符）：\n{sample}\n\n"
                f"可能原因：\n"
                f"• 当前协议（{self.protocol_combo.currentText()}）的帧起始符不匹配\n"
                f"• 内容为日志文本而非原始报文\n"
                f"• 报文被截断或格式异常")
            return

        # 清空之前的结果
        self.batch_results = []
        self.batch_summary_table.setRowCount(0)
        self.batch_detail_table.setRowCount(0)
        self.batch_detail_hex.clear()

        success_count = 0
        fail_count = 0

        for i, frame_item in enumerate(frames):
            # 协议9返回元组(frame_hex, ed_data_type)，其他协议返回纯字符串
            if isinstance(frame_item, tuple):
                frame_hex, ed_data_type = frame_item
            else:
                frame_hex = frame_item
                ed_data_type = ""

            # 前 5 帧打印 debug 日志
            if i < 5:
                self._debug_log(f"解析帧{i+1}: [{len(frame_hex)//2:3d}B] "
                                f"开始={frame_hex[:4]}... "
                                f"ed_type={ed_data_type or '无'}")

            table_data = []
            try:
                frame_bytes = bytes.fromhex(frame_hex)
                # 协议9：ED 开头但提取失败（报文不完整/格式错误）→ 明确报错，
                # 绝不把 ED 首字节当 FC 起始符送解析器
                if (self.current_protocol == 9 and frame_hex.startswith("ED")
                        and not ed_data_type):
                    table_data = [("❌ 解析失败", "", "",
                                   "ED 监控帧解析失败：报文不完整或格式错误，"
                                   "首字节 ED 不能作为业务帧起始符解析", None, None)]
                    summary = "ED 帧解析失败（报文不完整或格式错误）"
                    status = "失败"
                    fail_count += 1
                # 协议9：合法 ED 帧但无业务数据（控制报文、空数据报文等）
                # 直接解析监控头，不送 CSGNewGenParser
                elif (self.current_protocol == 9 and ed_data_type
                        and ed_data_type.startswith("ED:")
                        and frame_hex.startswith("ED")):
                    meta_rows, business_bytes, business_offset = (
                        self._parse_ed_monitor_header(frame_bytes))
                    if meta_rows is not None:
                        # 去掉最后一行"── 业务帧 ──"，因为没有业务数据
                        if meta_rows and meta_rows[-1][0].startswith("── 业务帧"):
                            meta_rows = meta_rows[:-1]
                        meta_rows.append((
                            "── 业务帧 ──", "", "",
                            f"无业务数据（{ed_data_type[3:]}）",
                            business_offset, business_offset))
                        table_data = meta_rows
                        summary = f"[ED:{ed_data_type[3:]}] PLC2.0监控包装帧"
                        status = "成功"
                        success_count += 1
                    else:
                        table_data = [("❌ 解析失败", "", "", "ED 监控帧格式错误", None, None)]
                        summary = "ED 帧格式错误"
                        status = "失败"
                        fail_count += 1
                else:
                    # 使用当前协议对应的解析器
                    current_parser = self._get_current_parser()
                    # 调用parse_to_table生成表格数据
                    table_data = current_parser.parse_to_table(frame_bytes)

                    # 从表格数据生成摘要
                    summary = self._get_summary_from_table_data(table_data)
                    # ED 监控帧数据来源标记
                    if ed_data_type:
                        summary = f"[ED:{ed_data_type}] {summary}"

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
                self.batch_results.append({
                    "_input": frame_hex,
                    "_status": status,
                    "错误": str(e),
                    "摘要": summary
                })

            # 添加到摘要表格
            row = self.batch_summary_table.rowCount()
            self.batch_summary_table.insertRow(row)

            # 序号
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignCenter)
            num_item.setData(Qt.UserRole, i)  # 存储原始 batch_results 索引
            self.batch_summary_table.setItem(row, 0, num_item)

            # 状态（emoji）
            status_emoji = "✅" if status == "成功" else "❌"
            status_item = QTableWidgetItem(status_emoji)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "成功":
                status_item.setForeground(Qt.darkGreen)
            else:
                status_item.setForeground(Qt.red)
            self.batch_summary_table.setItem(row, 1, status_item)

            # 长度
            len_item = QTableWidgetItem(str(len(frame_hex) // 2))
            len_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.batch_summary_table.setItem(row, 2, len_item)

            # 协议/类型
            proto_type = self._get_frame_type_name(table_data, status)
            proto_item = QTableWidgetItem(proto_type)
            if status != "成功":
                proto_item.setForeground(Qt.red)
            self.batch_summary_table.setItem(row, 3, proto_item)

            # 摘要
            self.batch_summary_table.setItem(row, 4, QTableWidgetItem(summary))

        # 更新状态栏
        self._update_status_bar(success_count, fail_count, len(frames))

        # 自动选中第一行并显示详情
        if self.batch_summary_table.rowCount() > 0:
            self.batch_summary_table.selectRow(0)
            self._on_batch_row_selected()

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

        elif self.current_protocol in (10, 11):
            # 国网新一代/HDC 1.0：网络标识/帧类型/TEI/MSDU序列/发送类型/报文等关键信息
            return self._get_gw_new_gen_summary(table_data)

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

        # ── ED 监控包装帧（PLC2.0收发机接口格式）──
        if "── PLC2.0 监控包装头 ──" in fields:
            parts = ["PLC2.0监控包装帧"]
            ctrl1 = fields.get("控制域1")
            ctrl2 = fields.get("控制域2")
            if ctrl1:
                parts.append(str(ctrl1[2]))
            if ctrl2:
                parts.append(str(ctrl2[2]))
            data_len = fields.get("数据域长度")
            if data_len:
                dlen_val = data_len[2]
                if isinstance(dlen_val, int):
                    parts.append(f"数据:{dlen_val}字节")
                else:
                    parts.append(f"数据:{dlen_val}")
            # 有业务帧时提取业务帧类型（在"── 业务帧 ──"之后）
            business_found = False
            for item in table_data:
                if item[0].startswith("── 业务帧"):
                    business_found = True
                    continue
                if business_found and item[0] and not item[0].startswith(" ") and "校验" not in item[0] and "结束符" not in item[0]:
                    parts.append(str(item[3] or item[2] or item[0]))
                    break
            return " | ".join(parts)

        # ── 公共：MSDU 类型作为顶层分类（若存在）──
        msdu_type_prefix = ""
        if "MSDU类型" in fields:
            msdu_type_name = fields["MSDU类型"][3]  # 如 "应用层报文"/"网络管理消息"
            if msdu_type_name:
                msdu_type_prefix = msdu_type_name

        # ── 应用层报文：含业务标识字段（优先于定界符类型展示）──
        if "业务标识" in fields:
            summary_parts = [msdu_type_prefix if msdu_type_prefix else "应用层"]
            # 0. 附带上层定界符类型（如果有）
            if "定界符类型" in fields:
                delim_desc = fields["定界符类型"][3]
                summary_parts.append(delim_desc)
            # 1. 帧类型域（业务大类）
            frame_type_item = fields.get("  帧类型域(D3~D0)")
            if frame_type_item:
                ft_comment = frame_type_item[3]  # "0 - 确认/否认"
                ft_name = ft_comment.split(" - ", 1)[1] if " - " in ft_comment else ft_comment
                summary_parts.append(ft_name)
            # 2. 业务标识（名称 + 编号）
            svc_item = fields["业务标识"]
            svc_val = svc_item[2]
            svc_comment = svc_item[3]  # "业务标识 0 - 确认"
            svc_desc = svc_comment.split(" - ", 1)[1] if " - " in svc_comment else svc_comment
            try:
                summary_parts.append(f"业务标识:{svc_desc}(0x{int(svc_val):02X})")
            except (ValueError, TypeError):
                summary_parts.append(f"业务标识:{svc_desc}")
            # 3. 传输方向
            dir_item = fields.get("  传输方向位(D15)")
            if dir_item:
                dir_comment = dir_item[3]  # "0 - 下行(CCO→STA)"
                dir_name = dir_comment.split(" - ", 1)[1] if " - " in dir_comment else dir_comment
                summary_parts.append(dir_name)
            # 4. 源/目的TEI
            if "源TEI" in fields:
                summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
            if "目的TEI" in fields:
                summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
            # 5. 核心内容：从业务数据单元子字段提取关键信息
            core = self._extract_csg_core_content(table_data)
            if core:
                summary_parts.append(core)
            return " | ".join(summary_parts)

        # ── 网络层：含 MMTYPE 字段（管理消息）──
        if "管理消息类型(MMTYPE)" in fields:
            mmtype_item = fields["管理消息类型(MMTYPE)"]
            mmtype_comment = mmtype_item[3]  # "管理消息: 关联请求(MMeAssocReq)"
            mmtype_val = mmtype_item[2]
            # 提取冒号后的消息名称
            mmtype_name = mmtype_comment.split(":", 1)[1].strip() if ":" in mmtype_comment else mmtype_comment
            prefix = msdu_type_prefix if msdu_type_prefix else "网络管理消息"
            try:
                # MMTYPE 解析值为 '0x0030' 形式字符串，需先去 0x 前缀按 16 进制解析
                mm_val = int(mmtype_val, 16) if str(mmtype_val).lower().startswith("0x") else int(mmtype_val)
            except (ValueError, TypeError):
                mm_val = 0
            summary_parts = [f"{prefix} | MMTYPE:{mmtype_name}(0x{mm_val:04X})"]
            # 附带管理消息版本
            if "管理消息版本" in fields:
                ver = fields["管理消息版本"][2]
                summary_parts.append(f"版本{ver}")
            # 附带源/目的TEI
            if "源TEI" in fields:
                summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
            if "目的TEI" in fields:
                summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
            return " | ".join(summary_parts)

        # ── 网络层：MPDU/MAC 物理层帧（定界符类型字段）──
        if "定界符类型" in fields:
            delim_item = fields["定界符类型"]
            delim_desc = delim_item[3]  # "SOF帧" / "信标帧" / "选择确认帧(SACK)"
            delim_val = delim_item[2]
            prefix = msdu_type_prefix if msdu_type_prefix else "网络层"
            summary_parts = [f"{prefix} | {delim_desc}"]
            # 信标帧：额外显示信标类型（发现/代理/中央）
            if delim_desc == "信标帧":
                beacon_type = ""
                if "信标载荷头" in fields:
                    beacon_head_item = fields["信标载荷头"]
                    beacon_parsed = beacon_head_item[2]
                    if isinstance(beacon_parsed, str) and "类型:" in beacon_parsed:
                        idx = beacon_parsed.index("类型:") + 3
                        beacon_type = beacon_parsed[idx:].split(",")[0].split(" ")[0]
                if not beacon_type and "信标类型" in fields:
                    beacon_type = str(fields["信标类型"][3] or fields["信标类型"][2])
                if beacon_type:
                    summary_parts.append(f"信标类型:{beacon_type}")
                # 信标帧附带网络标识
                if "网络标识(SNID)" in fields:
                    summary_parts.append(f"SNID:{fields['网络标识(SNID)'][2]}")
            # SOF/SACK 帧附带源/目的TEI和帧序号
            if delim_desc in ("SOF帧", "选择确认帧(SACK)"):
                if "源TEI" in fields:
                    summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
                if "目的TEI" in fields:
                    summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
                if "发送序号" in fields:
                    summary_parts.append(f"序号:{fields['发送序号'][2]}")
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

    def _get_gw_new_gen_summary(self, table_data: list) -> str:
        """国网新一代(索引10)监控/批量摘要生成

        体现监控工具关注的关键业务信息：
          网络标识(NID) | 帧类型(信标/SOF/选择确认/网间协调) | 管理消息类型(MMTYPE) |
          源→目的TEI | MSDU序列号 | 发送类型(单播/广播) | MSDU类型 |
          应用层端口/报文ID(方向)/报文序号/规约类型/数据长度

        table_data 格式: (field, raw, parsed, comment, byte_start, byte_end, is_child)
        """
        if not table_data:
            return "-"

        # 解析失败：直接返回失败原因
        for item in table_data:
            if str(item[0]).startswith("❌"):
                return item[3] if item[3] else "解析失败"

        # 以去除缩进的字段名建立索引（首个出现优先：FC 在 MAC/应用层之前）
        fs = {}
        for item in table_data:
            key = str(item[0]).strip()
            if key:
                fs.setdefault(key, item)

        def val(name):
            it = fs.get(name)
            return str(it[2]).strip() if it and it[2] not in (None, "") else ""

        def cmt(name):
            it = fs.get(name)
            return str(it[3]).strip() if it and it[3] not in (None, "") else ""

        parts = []

        # 1. 网络标识(NID)
        nid = val("网络标识(NID)")
        if nid:
            parts.append(f"NID:{nid}")

        # 2. 帧类型（定界符类型），comment 形如 "DT=1: SOF帧"
        delim = cmt("定界符类型")
        frame_type_name = ""
        if delim:
            frame_type_name = delim.split(":", 1)[1].strip() if ":" in delim else delim
            sof_sub = val("帧类型")  # SOF帧子类型: 数据帧/信道探测帧
            if "SOF" in frame_type_name and sof_sub:
                parts.append(f"{frame_type_name}({sof_sub})")
            else:
                parts.append(frame_type_name)

        # 3. 管理消息类型(MMTYPE)：如 关联确认(MMeAssocCnf)/发现列表
        mmtype = cmt("管理消息类型(MMTYPE)")
        if mmtype:
            parts.append(f"MMTYPE:{mmtype}")

        # 4. 源→目的TEI：优先 FC 级，其次 MAC 级原始源/目的
        src = val("源TEI") or val("原始源TEI")
        dst = val("目的TEI") or val("原始目的TEI")
        if src or dst:
            parts.append(f"{src or '?'}→{dst or '?'}")

        # 5. MSDU序列号
        seq = val("MSDU序列号")
        if seq:
            parts.append(f"msduSeq:{seq}")

        # 6. 发送类型（单播/本地广播/...）
        send_type = cmt("发送类型")
        if send_type and "保留" not in send_type:
            parts.append(send_type)

        # 7. MSDU类型（非保留且未在别处体现）
        msdu_type = cmt("MSDU类型")
        if msdu_type and "保留" not in msdu_type and "网络管理" not in msdu_type:
            parts.append(msdu_type)

        # 8. 应用层：报文端口 + 报文ID(含方向) + 报文序号 + 规约类型 + 数据长度
        port = val("报文端口号")
        if port:
            parts.append(f"端口:{port}")
        msg_id = val("报文ID")
        if msg_id:
            # 方向(上行/下行)在"应用层报文"行 comment 中，如 "...报文ID=xxx 下行"
            app_cmt = cmt("应用层报文")
            direction = ""
            for d in ("下行", "上行"):
                if d in app_cmt:
                    direction = d
                    break
            parts.append(f"报文:{msg_id}({direction})" if direction else f"报文:{msg_id}")
        # 报文序号（STA 应答时返回）
        msg_seq = val("报文序号")
        if msg_seq:
            parts.append(f"序号:{msg_seq}")
        # 规约类型（如 DL/T 698.45），精简展示
        proto = val("规约类型")
        if proto:
            parts.append(f"规约:{proto.replace('DL/T ', '')}")
        dlen = val("转发数据长度")
        if dlen:
            parts.append(f"数据:{dlen}")

        return " | ".join(parts) if parts else "-"

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
        elif protocol_index == 10:
            # 国网新一代双模：按行提取，每行一帧
            # 前缀已在 parse_batch 中通过 _strip_gw_new_gen_prefix 剥离
            return [f.strip() for f in text.splitlines() if f.strip() and len(f.strip()) >= 4]
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
          - **ED 监控帧处理**：若帧以 ED 开头，解析 ED..EE 包装头，提取业务帧

        Returns:
            list of tuple: [(frame_hex, ed_data_type), ...]
              - frame_hex: 提取后的帧 hex 字符串
              - ed_data_type: ED 数据类型描述（如 "FC数据"、"FC+Payload数据"），非 ED 帧为空字符串
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

            ed_data_type = ""
            # ED 监控帧处理：解析 ED..EE 包装头，提取业务帧
            if clean_line.startswith("ED"):
                business_hex, data_type = self._extract_business_from_ed_frame(clean_line)
                if business_hex:
                    clean_line = business_hex
                    ed_data_type = data_type
                elif data_type.startswith("ED:"):
                    # 合法 ED 帧但无业务数据（控制报文、空数据报文等）
                    # 保留原始 ED hex，标记类型供后续解析识别
                    ed_data_type = data_type
                # 其余情况（ED 解析失败）保留原始帧，ed_data_type 为空

            frames.append((clean_line, ed_data_type))
        return frames
    def _extract_business_from_ed_frame(self, hex_str: str) -> tuple:
        """从 ED..EE PLC2.0 监控包装帧中提取业务数据

        包结构: ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)
        数据域公共头(9字节): 物理信道(1)+时间戳(4,LE)+物理块个数(1)+保留(1)+物理块长度(2,LE)

        注意：监控日志可能在 ED 帧后附加 FF EE 标记，需要正确处理

        Returns:
            (business_hex, data_type_desc) 成功时返回业务数据hex和类型描述
            ("", "") 解析失败
        """
        try:
            frame_bytes = bytes.fromhex(hex_str)
        except ValueError:
            return "", ""

        n = len(frame_bytes)
        if n < 8 or frame_bytes[0] != 0xED:
            return "", ""

        # 解析帧长字段
        frame_len = frame_bytes[1] | (frame_bytes[2] << 8)
        if frame_len < 4 or frame_len > 4096:
            return "", ""

        # 计算预期的整包长度
        expected_total = frame_len + 4  # ED(1) + 帧长(2) + [内容:frame_len字节] + EE(1)

        # 查找实际的 EE 终止符位置
        # 优先使用帧长计算的位置，如果该位置不是 EE，则搜索
        ee_pos = -1
        if expected_total <= n and frame_bytes[expected_total - 1] == 0xEE:
            ee_pos = expected_total - 1
        else:
            # 帧长字段可能不准确，或者后面有多余数据(如 FF EE 标记)
            # 从位置6后搜索第一个 EE
            for i in range(6, min(n, expected_total + 10)):  # 允许一定偏差
                if frame_bytes[i] == 0xEE:
                    ee_pos = i
                    break

        if ee_pos < 0:
            return "", ""  # 找不到 EE 终止符

        # 验证 EF 起始符
        if frame_bytes[5] != 0xEF:
            return "", ""

        # 计算实际的数据范围
        # ED帧结构: ED(0) + 帧长(1-2) + ctrl1(3) + ctrl2(4) + EF(5) + 数据域 + CS + EE(ee_pos)
        data_start = 6
        data_end = ee_pos - 1  # 排除 CS(ee_pos-1) 和 EE(ee_pos)

        ctrl1 = frame_bytes[3]
        ctrl2 = frame_bytes[4]

        # 数据域为空：合法 ED 帧但没有业务数据（控制报文、空数据报文等）
        if data_end <= data_start:
            if ctrl1 == 0x01:
                return "", f"ED:控制报文(0x{ctrl2:02X})"
            elif ctrl1 == 0x00:
                return "", f"ED:数据报文(空,0x{ctrl2:02X})"
            else:
                return "", f"ED:空数据(0x{ctrl1:02X}/0x{ctrl2:02X})"

        data = frame_bytes[data_start:data_end]
        data_len = len(data)

        # 非数据报文或数据域不足，返回空
        if ctrl1 != 0x00 or ctrl2 not in (0x01, 0x02, 0x03) or data_len < 9:
            # 控制报文或非标准数据子类型但有数据域：仍然视为合法 ED 帧，无业务数据
            if ctrl1 == 0x01:
                return "", f"ED:控制报文(0x{ctrl2:02X})"
            else:
                return "", f"ED:非业务帧(0x{ctrl1:02X}/0x{ctrl2:02X})"

        # 跳过 9 字节公共头，提取业务数据
        business = data[9:]
        if len(business) < 4:
            # 公共头完整但业务数据不足：仍按合法 ED 数据帧处理
            return "", f"ED:数据报文(业务不足,0x{ctrl2:02X})"

        # 根据 ctrl2 确定数据类型描述
        ctrl2_desc = {
            0x01: "FC数据",
            0x02: "FC+Payload数据",
            0x03: "Payload数据",
        }.get(ctrl2, f"未知(0x{ctrl2:02X})")

        return business.hex().upper(), ctrl2_desc

    def _run_cli_preprocessor(self):
        """执行通用预处理命令链：读取 batch_input → 解析命令 → 结果回填"""
        cmd_text = self._pp_cmd_combo.currentText().strip()
        if not cmd_text:
            QMessageBox.warning(self, "警告", "请输入预处理命令！\n"
                                "示例: find \"tcp data:\" excluding \"len:\\d+: \"\n"
                                "输入 ? 查看所有可用命令。")
            return

        input_text = self.batch_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "输入框为空，请先粘贴或加载报文！")
            return

        try:
            # 用 shlex 正确解析带引号的参数
            import shlex
            commands = shlex.split(cmd_text)
        except ValueError as e:
            QMessageBox.warning(self, "命令解析错误",
                                f"命令格式错误: {e}\n请检查引号是否匹配。")
            return

        try:
            from pp_cli import parse_and_run
            result = parse_and_run(input_text, commands)

            if not result.strip():
                QMessageBox.information(self, "预处理结果",
                                        "预处理后无有效数据（所有行被过滤）")
                return

            # 回填到输入框
            self.batch_input.setPlainText(result)
            frame_count = len([l for l in result.splitlines() if l.strip()])
            self.update_stats(
                f"预处理完成（{cmd_text}）：{frame_count} 行")

        except Exception as e:
            QMessageBox.critical(self, "预处理失败",
                                 f"执行预处理命令失败：\n{e}")

    def _load_pp_commands(self):
        """从 config.json 加载预处理命令列表"""
        commands = list(self._pp_preset_commands)
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                saved = config.get("pp_commands", [])
                # 合并：预设命令在前，用户保存的在后，去重
                seen = set()
                merged = []
                for c in commands + saved:
                    if c not in seen:
                        seen.add(c)
                        merged.append(c)
                commands = merged
            except Exception:
                pass
        self._pp_cmd_combo.clear()
        self._pp_cmd_combo.addItems(commands)

    def _save_pp_command(self):
        """保存当前输入框中的命令到常用列表"""
        cmd = self._pp_cmd_combo.currentText().strip()
        if not cmd:
            QMessageBox.warning(self, "警告", "命令为空，无法保存")
            return
        # 检查是否已存在
        idx = self._pp_cmd_combo.findText(cmd)
        if idx >= 0:
            self._pp_cmd_combo.setCurrentIndex(idx)
            return  # 已存在，直接选中

        self._pp_cmd_combo.addItem(cmd)
        self._pp_cmd_combo.setEditText(cmd)
        self._persist_pp_commands()
        self.update_stats(f"已保存预处理命令: {cmd}")

    def _delete_pp_command(self):
        """删除下拉列表中选中的命令"""
        cmd = self._pp_cmd_combo.currentText().strip()
        if not cmd:
            return
        idx = self._pp_cmd_combo.findText(cmd)
        if idx < 0:
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要从常用列表中删除以下命令吗？\n\n{cmd}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._pp_cmd_combo.removeItem(idx)
            self._persist_pp_commands()

    def _persist_pp_commands(self):
        """将当前命令列表持久化到 config.json 的 pp_commands 段"""
        config: Dict[str, Any] = {}
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}
        commands = [self._pp_cmd_combo.itemText(i)
                    for i in range(self._pp_cmd_combo.count())]
        config["pp_commands"] = commands
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[预处理命令保存失败] {e}")

    def _show_pp_help(self):
        """显示预处理命令帮助"""
        from pp_cli import COMMANDS
        lines = ["通用文本预处理命令（支持正则）:\n"]
        for name, info in COMMANDS.items():
            lines.append(f"  {name:15s} {info['help']}")
        lines.append("\n命令链示例:")
        lines.append('  find "tcp data:"')
        lines.append('  find "tcp data:" excluding "len:\\d+: "')
        lines.append('  find "60F0" excluding "mrd:" dedup')
        lines.append('  find "nwk:" replace ".*nwk:" "NWK:" head 10')
        lines.append('  hex_extract')
        lines.append("\n常用命令管理:")
        lines.append("  ★  保存当前命令到下拉列表（持久化到 config.json）")
        lines.append("  ×  删除下拉列表中选中的命令")
        lines.append("  下拉列表可直接选择已保存的命令，也可手动输入新命令")
        QMessageBox.information(self, "预处理命令帮助", "\n".join(lines))

    # ==================== Python 脚本预处理 ====================

    def _resolve_script_path(self, path):
        """解析脚本路径：相对路径按项目根解析，返回绝对路径"""
        from pathlib import Path as _P
        p = _P(path)
        if p.is_absolute():
            return str(p)
        return str((_P(__file__).parent / p).resolve())

    def _load_py_scripts(self):
        """从 config.json 加载 Python 脚本列表；首次启动注册示例脚本"""
        from pathlib import Path as _P
        scripts_dir = _P(__file__).parent / "scripts"
        # 内置示例脚本（首次启动自动注册，用相对路径）
        builtins = []
        if scripts_dir.is_dir():
            for name, fname in [
                ("Hex 清洗（示例）", "hex_clean.py"),
                ("TCP Payload 提取（示例）", "tcp_payload_extract.py"),
                ("按解析过滤（示例）", "filter_by_parse.py"),
            ]:
                fpath = scripts_dir / fname
                if fpath.is_file():
                    # 存相对路径，便于项目迁移
                    builtins.append({"name": name, "path": f"scripts/{fname}"})

        saved = []
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                saved = config.get("py_scripts", [])
            except Exception:
                saved = []

        # 无任何记录 → 首次启动，填充内置示例
        if not saved and builtins:
            self._py_builtin_scripts = builtins
            for s in builtins:
                abs_path = self._resolve_script_path(s["path"])
                self._py_script_combo.addItem(s["name"], abs_path)
            # 持久化（用相对路径存内置示例）
            self._persist_py_scripts(builtins)
            return

        # 有保存记录 → 加载
        self._py_builtin_scripts = builtins  # 保存引用供参考
        for s in saved:
            if isinstance(s, dict) and "name" in s and "path" in s:
                abs_path = self._resolve_script_path(s["path"])
                self._py_script_combo.addItem(s["name"], abs_path)

    def _persist_py_scripts(self, scripts_list=None):
        """将脚本列表持久化到 config.json 的 py_scripts 段

        Args:
            scripts_list: 可选，指定要保存的列表（每项含 name/path）。
                         None 则从下拉框读取，路径尽量存相对形式。
        """
        from pathlib import Path as _P
        base = _P(__file__).parent
        config: Dict[str, Any] = {}
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}

        if scripts_list is None:
            scripts = []
            for i in range(self._py_script_combo.count()):
                name = self._py_script_combo.itemText(i)
                path = self._py_script_combo.itemData(i)
                if not path:
                    continue
                # 项目内脚本存相对路径，外部脚本存绝对路径
                p = _P(path)
                try:
                    rel = p.relative_to(base)
                    path_str = str(rel).replace('\\', '/')
                except ValueError:
                    path_str = str(p)
                scripts.append({"name": name, "path": path_str})
        else:
            scripts = scripts_list

        config["py_scripts"] = scripts
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Python脚本保存失败] {e}")

    def _load_py_script_file(self):
        """通过文件对话框加载 .py 脚本到下拉列表"""
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path as _P

        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Python 脚本", "", "Python 脚本 (*.py);;所有文件 (*.*)"
        )
        if not path:
            return

        # 检查文件是否已在列表中
        for i in range(self._py_script_combo.count()):
            if self._py_script_combo.itemData(i) == path:
                self._py_script_combo.setCurrentIndex(i)
                self.update_stats(f"脚本已在列表中: {self._py_script_combo.itemText(i)}")
                return

        # 用文件名（去扩展）作为显示名
        name = _P(path).stem
        self._py_script_combo.addItem(name, path)
        self._py_script_combo.setCurrentIndex(self._py_script_combo.count() - 1)
        self._persist_py_scripts()
        self.update_stats(f"已加载脚本: {name}")

    def _delete_py_script(self):
        """从下拉列表移除当前脚本（不删除磁盘文件）"""
        idx = self._py_script_combo.currentIndex()
        if idx < 0:
            return

        name = self._py_script_combo.itemText(idx)
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(
            self, "确认移除",
            f"确定从列表中移除脚本「{name}」吗？\n\n（不会删除磁盘上的 .py 文件）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        self._py_script_combo.removeItem(idx)
        self._persist_py_scripts()
        self.update_stats(f"已移除脚本: {name}")

    def _run_py_script(self):
        """运行当前选中的 Python 脚本（后台线程，不阻塞 UI），结果回填到 batch_input"""
        import time
        t0 = time.time()

        idx = self._py_script_combo.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "警告", "请先加载或选择一个 Python 脚本！")
            return

        script_path = self._py_script_combo.itemData(idx)
        if not script_path:
            QMessageBox.warning(self, "警告", "脚本路径无效！")
            return

        # 读取输入文本（可能是大文本，计时）
        input_text = self.batch_input.toPlainText()
        t1 = time.time()
        print(f"[脚本] 读取输入: {len(input_text)} 字符, 耗时 {(t1-t0)*1000:.1f}ms")

        if not input_text.strip():
            QMessageBox.warning(self, "警告", "输入框为空，请先粘贴或加载报文！")
            return

        # 防止重复执行
        if getattr(self, "_py_script_running", False):
            QMessageBox.information(self, "提示", "脚本正在运行中，请稍候...")
            return

        script_name = self._py_script_combo.itemText(idx)
        self._py_script_running = True
        self._py_run_btn.setEnabled(False)
        self._py_run_btn.setText("运行中...")
        self.update_stats(f"正在运行脚本（{script_name}）...")

        # 构造 context（主线程中做，只包含轻量数据；parser 懒加载）
        from py_script_engine import build_context
        try:
            context = build_context(self)
        except Exception as e:
            self._py_script_running = False
            self._py_run_btn.setEnabled(True)
            self._py_run_btn.setText("运行")
            QMessageBox.critical(self, "脚本上下文构造失败", str(e))
            return

        t2 = time.time()
        print(f"[脚本] 准备阶段完成, 耗时 {(t2-t0)*1000:.1f}ms")

        # Worker + Thread
        self._py_script_thread = QThread(self)
        worker = _PyScriptWorker(script_path, input_text, context)
        worker.moveToThread(self._py_script_thread)
        self._py_script_worker = worker

        # 信号连接
        self._py_script_thread.started.connect(worker.run)
        worker.finished.connect(self._on_py_script_finished)
        worker.error.connect(self._on_py_script_error)
        worker.finished.connect(self._py_script_thread.quit)
        worker.error.connect(self._py_script_thread.quit)
        self._py_script_thread.finished.connect(worker.deleteLater)
        self._py_script_thread.finished.connect(self._py_script_thread.deleteLater)

        # 记录脚本名用于完成提示
        self._py_script_running_name = script_name

        self._py_script_thread.start()

    def _on_py_script_finished(self, result):
        """脚本执行成功回调"""
        import time
        t0 = time.time()
        self._py_script_running = False
        self._py_run_btn.setEnabled(True)
        self._py_run_btn.setText("运行")

        if not result.strip():
            QMessageBox.information(self, "脚本结果",
                                    "脚本输出为空，未修改输入内容。")
            return

        # 高效回填：用 QTextCursor 全选替换，减少重绘
        doc = self.batch_input.document()
        self.batch_input.setUpdatesEnabled(False)
        cursor = self.batch_input.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(result)
        cursor.endEditBlock()
        # 光标移到开头
        cursor.setPosition(0)
        self.batch_input.setTextCursor(cursor)
        self.batch_input.setUpdatesEnabled(True)
        t1 = time.time()
        print(f"[脚本回调] 回填 {len(result)} 字符, 耗时 {(t1-t0)*1000:.1f}ms")

        line_count = len([l for l in result.splitlines() if l.strip()])
        script_name = getattr(self, "_py_script_running_name", "脚本")
        self.update_stats(f"脚本处理完成（{script_name}）：{line_count} 行")

    def _on_py_script_error(self, error_msg):
        """脚本执行失败回调"""
        self._py_script_running = False
        self._py_run_btn.setEnabled(True)
        self._py_run_btn.setText("运行")
        QMessageBox.critical(self, "脚本执行失败", error_msg)

    def _show_py_script_help(self):
        """显示 Python 脚本预处理帮助"""
        lines = [
            "Python 脚本预处理",
            "────────────────────────────────",
            "",
            "加载自定义 .py 脚本，对输入框文本进行清洗/提取/转换。",
            "脚本需定义入口函数：",
            "",
            "    def process(text, context):",
            "        \"\"\"",
            "        Args:",
            "            text:    输入框原始文本（str）",
            "            context: 上下文字典",
            "        Returns:",
            "            处理后的文本（str）",
            "        \"\"\"",
            "        return text",
            "",
            "context 包含字段：",
            "  protocol_index : int      当前协议索引（0-10）",
            "  protocol_name  : str      当前协议名称",
            "  config_dir     : str      项目根目录",
            "  parser         : object   当前协议解析器实例",
            "  main_window    : object   主窗口引用（慎用）",
            "",
            "脚本可自由 import 项目内模块（如 protocol_parser、hdlc_parser 等）。",
            "",
            "⚠ 安全提示：脚本直接运行，仅加载可信的 .py 文件。",
            "",
            "示例脚本位于项目 scripts/ 目录下。",
        ]
        QMessageBox.information(self, "Python 脚本预处理帮助", "\n".join(lines))

    def clear_batch(self):
        """清空批量解析内容"""
        self.batch_input.clear()
        self.batch_summary_table.setRowCount(0)
        self.batch_detail_table.setRowCount(0)
        self.batch_detail_hex.clear()
        self.batch_results = []
        self.batch_status_bar.setText("就绪")
        self.batch_frame_count_label.setText("共 0 帧")
        self.update_stats("待解析")
        # 重置搜索过滤
        if hasattr(self, 'batch_search_edit'):
            self.batch_search_edit.clear()
        if hasattr(self, 'batch_status_filter'):
            self.batch_status_filter.setCurrentIndex(0)
        if hasattr(self, 'batch_filter_count'):
            self.batch_filter_count.setText("")

    def export_batch(self, fmt=None):
        """增强版批量解析结果导出 - 支持 JSON/Excel 多格式，Excel 含 Sheet2 详细解析

        Args:
            fmt: 导出格式，可选 "excel" / "json" / None
                 - "excel" 或 "json": 直接弹出保存对话框，跳过格式选择
                 - None: 显示完整的导出选项对话框（默认，向后兼容）
        """
        from PySide6.QtWidgets import QFileDialog
        
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

        # 快速路径：指定格式时直接弹出保存文件对话框
        if fmt in ("excel", "json"):
            if fmt == "excel":
                default_name = f"batch_parse_{protocol_name}.xlsx"
                filter_str = "Excel 文件 (*.xlsx);;所有文件 (*)"
            else:
                default_name = f"batch_parse_{protocol_name}.json"
                filter_str = "JSON 文件 (*.json);;所有文件 (*)"

            file_path, _ = QFileDialog.getSaveFileName(
                self, "选择导出位置", default_name, filter_str
            )
            if not file_path:
                return

            try:
                export_dir = str(Path(file_path).parent)
                exporter = EnhancedBatchResultExporter(export_dir)

                if fmt == "excel":
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
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))
            return

        # 创建导出器
        exporter = EnhancedBatchResultExporter()

        # 显示导出选项对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox
        from PySide6.QtWidgets import QLabel, QRadioButton, QPushButton, QLineEdit
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
            raw_label.setFont(self._ui_font(0, family="Consolas"))
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
                table_font = self._ui_font(-2)
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
                text_edit.setFont(self._ui_font(0, family="Consolas"))
                text_edit.setText(json.dumps(result, ensure_ascii=False, indent=2))
                layout.addWidget(text_edit)
        else:
            # 异常帧，显示错误信息
            error_text = result.get("错误", json.dumps(result, ensure_ascii=False, indent=2))
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(self._ui_font(0, family="Consolas"))
            text_edit.setText(error_text)
            layout.addWidget(text_edit)

        dialog.exec()

    def _get_frame_type_name(self, table_data: list, status: str) -> str:
        """从解析表格数据中提取帧类型名称（用于摘要表的"协议/类型"列）"""
        if status != "成功" or not table_data:
            if status == "失败":
                return "解析失败"
            elif status == "异常":
                return "异常"
            else:
                return "-"

        if self.current_protocol == 0:  # 南网协议
            for item in table_data:
                field = str(item[0])
                if "AFN" in field and not field.startswith(" "):
                    return str(item[3] or item[2] or "南网协议")
            return "南网协议"

        elif self.current_protocol == 7:  # 国网协议
            for item in table_data:
                field = str(item[0])
                if "AFN" in field and not field.startswith(" "):
                    return str(item[3] or item[2] or "国网协议")
            return "国网协议"

        elif self.current_protocol == 8:  # 698.45
            for item in table_data:
                field = str(item[0])
                if ("APDU" in field or "功能码" in field or "服务" in field) and not field.startswith(" "):
                    return str(item[3] or item[2] or "698.45协议")
            return "698.45协议"

        elif self.current_protocol in (2, 3, 4, 5):  # DLMS 族
            for item in table_data:
                field = str(item[0])
                if ("帧类型" in field or "服务" in field or "功能" in field) and not field.startswith(" "):
                    val = str(item[3] or item[2] or "")
                    if val:
                        return val
            proto_names = {2: "HDLC", 3: "DLMS-APDU", 4: "DLMS-Wrapper", 5: "DLMS-APDU"}
            return proto_names[self.current_protocol]

        elif self.current_protocol == 9:  # 新一代载波
            for item in table_data:
                field = str(item[0])
                if ("帧类型" in field or field.strip() == "FC") and not field.startswith(" "):
                    return str(item[3] or item[2] or "新一代载波")
            return "新一代载波"

        elif self.current_protocol == 10:  # 国网新一代
            for item in table_data:
                field = str(item[0])
                if ("帧类型" in field or "MSDU类型" in field) and not field.startswith(" "):
                    return str(item[3] or item[2] or "国网新一代")
            return "国网新一代"

        elif self.current_protocol == 6:  # DLT645
            for item in table_data:
                if "控制码" in str(item[0]) and not str(item[0]).startswith(" "):
                    return str(item[3] or item[2] or "DLT645")
            return "DLT645协议"

        elif self.current_protocol == 1:  # PLC RF
            for item in table_data:
                field = str(item[0])
                if ("命令字" in field or "功能" in field) and not field.startswith(" "):
                    return str(item[3] or item[2] or "PLC RF")
            return "PLC RF协议"

        else:
            return self.protocol_combo.currentText().split(" ")[0]

    def _on_batch_filter_changed(self):
        """批量解析结果搜索过滤（关键词 + 状态）"""
        if not hasattr(self, 'batch_results') or not self.batch_results:
            return
        keyword = self.batch_search_edit.text().strip().lower()
        status_filter = self.batch_status_filter.currentData()
        visible_count = 0
        total = self.batch_summary_table.rowCount()
        for row in range(total):
            item = self.batch_summary_table.item(row, 0)
            if item is None:
                continue
            orig_idx = item.data(Qt.UserRole)
            if orig_idx is None or orig_idx >= len(self.batch_results):
                continue
            result = self.batch_results[orig_idx]
            status = result.get("_status", "")
            # 状态过滤
            if status_filter == "success" and status != "成功":
                self.batch_summary_table.setRowHidden(row, True)
                continue
            if status_filter == "fail" and status != "失败":
                self.batch_summary_table.setRowHidden(row, True)
                continue
            if status_filter == "error" and status != "异常":
                self.batch_summary_table.setRowHidden(row, True)
                continue
            # 关键词过滤（匹配摘要 + 协议类型 + 原始HEX）
            if keyword:
                summary = str(result.get("摘要", "")).lower()
                proto_item = self.batch_summary_table.item(row, 3)
                proto = proto_item.text().lower() if proto_item else ""
                raw_hex = str(result.get("_input", "")).lower()
                if keyword not in summary and keyword not in proto and keyword not in raw_hex:
                    self.batch_summary_table.setRowHidden(row, True)
                    continue
            self.batch_summary_table.setRowHidden(row, False)
            visible_count += 1
        # 更新计数
        if keyword or status_filter != "all":
            self.batch_filter_count.setText(f"显示 {visible_count} / {total}")
        else:
            self.batch_filter_count.setText("")
        # 如果当前选中行被隐藏，选中第一条可见行
        current = self.batch_summary_table.currentRow()
        if current < 0 or self.batch_summary_table.isRowHidden(current):
            for r in range(total):
                if not self.batch_summary_table.isRowHidden(r):
                    self.batch_summary_table.selectRow(r)
                    break

    def _on_batch_row_selected(self, row=None, col=None):
        """批量解析摘要表行选中时的处理（填充右侧详情面板）"""
        # 获取当前选中行的原始 batch_results 索引
        if row is not None:
            table_row = row
        else:
            table_row = self.batch_summary_table.currentRow()
            if table_row < 0:
                return
        # 从序号列 item 中读取原始索引（过滤后行号≠原始索引）
        item = self.batch_summary_table.item(table_row, 0)
        if item is None:
            return
        orig_idx = item.data(Qt.UserRole)
        if orig_idx is None:
            # 兼容旧逻辑：直接用行号当索引
            orig_idx = table_row
        if orig_idx < 0 or orig_idx >= len(self.batch_results):
            return
        self._populate_batch_detail(orig_idx)

    def _populate_batch_detail(self, index: int):
        """填充批量解析详情面板（右侧表格 + 原始报文）"""
        if index < 0 or index >= len(self.batch_results):
            return

        result = self.batch_results[index]
        raw_hex = result.get("_input", "")

        # 填充原始报文
        if raw_hex:
            hex_display = ' '.join(raw_hex[j:j+2] for j in range(0, len(raw_hex), 2))
            self.batch_detail_hex.setPlainText(hex_display)
        else:
            self.batch_detail_hex.clear()

        # 填充详情表格
        self.batch_detail_table.setRowCount(0)

        status = result.get("_status", "")
        if status == "异常":
            # 异常帧：显示错误信息
            error_text = result.get("错误", str(result))
            self.batch_detail_table.insertRow(0)
            err_item = QTableWidgetItem(f"❌ 解析异常：{error_text}")
            err_item.setForeground(Qt.red)
            self.batch_detail_table.setItem(0, 0, err_item)
            return

        table_data = result.get("_table_data", [])
        if not table_data:
            return

        for r, item in enumerate(table_data):
            field_name = str(item[0]) if item[0] is not None else ""
            raw_val = str(item[1]) if item[1] is not None else ""
            parsed_val = str(item[2]) if item[2] is not None else ""
            comment = str(item[3]) if item[3] is not None else ""

            # 检测子字段：优先用 is_child 标志(index 6)，其次用前导空格判断
            is_child = False
            if len(item) > 6:
                is_child = bool(item[6])
            if not is_child and (field_name.startswith("  ") or field_name.startswith("\t")):
                is_child = True

            # 构造显示用字段名
            if is_child:
                display_name = "  └ " + field_name.lstrip()
            else:
                display_name = field_name

            self.batch_detail_table.insertRow(r)

            field_item = QTableWidgetItem(display_name)
            if is_child:
                field_item.setForeground(QColor("#555555"))
            self.batch_detail_table.setItem(r, 0, field_item)
            self.batch_detail_table.setItem(r, 1, QTableWidgetItem(raw_val))
            self.batch_detail_table.setItem(r, 2, QTableWidgetItem(parsed_val))
            self.batch_detail_table.setItem(r, 3, QTableWidgetItem(comment))

    def _do_count_frames(self):
        """实时统计输入中的帧数量（防抖调用）"""
        text = self.batch_input.toPlainText().strip()
        if not text:
            self.batch_frame_count_label.setText("共 0 帧")
            return

        try:
            if self.current_protocol in (9, 10):
                # 新一代协议按行近似统计（精确统计需要完整前缀剥离，代价较高）
                count = sum(1 for line in text.splitlines() if line.strip())
            else:
                frames = self._extract_frames_for_protocol(text, self.current_protocol)
                count = len(frames)
        except Exception:
            count = 0

        self.batch_frame_count_label.setText(f"共 {count} 帧")

    def _copy_batch_detail_hex(self):
        """复制当前选中帧的原始报文到剪贴板"""
        text = self.batch_detail_hex.toPlainText().strip()
        if not text:
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        # 临时更新状态栏提示
        old_text = self.batch_status_bar.text()
        self.batch_status_bar.setText("原始报文已复制到剪贴板")
        QTimer.singleShot(1500, lambda: self.batch_status_bar.setText(old_text))

    def _update_status_bar(self, success_count: int, fail_count: int, total: int):
        """更新批量解析底部状态栏"""
        self.batch_status_bar.setText(
            f"解析完成 — 共 {total} 帧（✅ {success_count} 成功，❌ {fail_count} 失败）"
        )

    def update_stats(self, text: str):
        """更新状态标签（兼容旧 stats_label，同时更新批量解析状态栏）"""
        if hasattr(self, 'stats_label') and self.stats_label:
            self.stats_label.setText(f"状态：{text}")
        if hasattr(self, 'batch_status_bar') and self.batch_status_bar:
            self.batch_status_bar.setText(text)
    
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
            if self.current_protocol == 10:
                # 国网新一代双模通信互联互通
                parsed_data = self.gw_new_gen_parser.parse_to_table(extracted_bytes)
                dialog_title = f"深度解析国网新一代 (提取 {len(extracted_bytes)} 字节)"
            elif self.current_protocol == 11:
                # HDC 1.0 双模互联互通
                parsed_data = self.hdc10_parser.parse_to_table(extracted_bytes)
                dialog_title = f"深度解析HDC 1.0 (提取 {len(extracted_bytes)} 字节)"
            elif self.current_protocol in (8, 9):
                # 698.45 / 新一代载波
                parsed_data = self.gw_new_gen_parser.parse_to_table(extracted_bytes)
                dialog_title = f"深度解析新一代载波 (提取 {len(extracted_bytes)} 字节)"
            elif len(extracted_bytes) >=12 and extracted_bytes[0] == 0x68 and extracted_bytes[7] == 0x68 and extracted_bytes[-1] == 0x16:
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
        hex_text.setFont(self._ui_font(0, family="Consolas"))
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
        table_font = self._ui_font(-2)
        table.setFont(table_font)
        # 右键复制菜单 + Ctrl+C
        self._setup_table_copy_menu(table)

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

    def _get_baud_value(self) -> Optional[int]:
        """获取并校验波特率输入（支持编辑框自定义值），无效返回 None 并提示"""
        baud_text = self.serial_baud_combo.currentText().strip()
        try:
            baud = int(baud_text)
            if baud <= 0:
                raise ValueError
            return baud
        except ValueError:
            QMessageBox.warning(self, "警告", f"波特率无效：{baud_text}，请输入正整数")
            return None

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

        # 加载南网/国网新一代通道配置
        parse_cfg = self._app_config.get("parse", {})
        self._csg_channel = parse_cfg.get("csg_channel", "auto")
        self._gw_channel = parse_cfg.get("gw_channel", "plc")
        # 同步到 combo（combo 在 create_single_parse_tab 中创建，稍后初始化时设置）

    def _load_system_settings(self):
        """加载系统集成设置（config.json "system" 段）"""
        from system_integration.system_settings import DEFAULT_SYSTEM_SETTINGS
        settings = dict(DEFAULT_SYSTEM_SETTINGS)
        sys_cfg = self._app_config.get("system", {})
        if isinstance(sys_cfg, dict):
            for k in settings:
                if k in sys_cfg:
                    settings[k] = sys_cfg[k]
        self._system_settings = settings

    def _apply_system_settings(self, settings: dict):
        """应用系统集成设置（对话框确定 / 托盘自启开关时调用）"""
        self._system_settings = dict(settings)
        # 写入 config.json
        try:
            config = {}
            if self._config_path.exists():
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            config["system"] = self._system_settings
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[系统设置保存失败] {e}")

        # 开机自启
        from system_integration.registry_menu import set_autostart
        try:
            set_autostart(bool(self._system_settings.get("auto_start")))
        except Exception as e:
            print(f"[开机自启设置失败] {e}")

        # 托盘自启开关状态同步
        if hasattr(self, "_tray_manager") and self._tray_manager is not None:
            self._tray_manager.update_autostart_state()

        # 全局热键：设置变更后重启热键监听
        if hasattr(self, "_hotkey_manager") and self._hotkey_manager is not None:
            self._restart_hotkey()

        # 剪贴板监听开关
        if hasattr(self, "_clipboard_monitor") and self._clipboard_monitor is not None:
            self._clipboard_monitor.set_enabled(
                bool(self._system_settings.get("clipboard_monitor", True))
            )

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

        # 更新主题与字体配置
        config["ui"] = ThemeManager.to_config(self._theme_id, self._font_family, self._font_size)

        # 更新 LLM 预处理配置
        if hasattr(self, "llm_preprocess_widget"):
            self.llm_preprocess_widget.save_config()

        # 保存通道配置
        parse_cfg = config.get("parse", {})
        parse_cfg["csg_channel"] = getattr(self, '_csg_channel', 'plc')
        parse_cfg["gw_channel"] = getattr(self, '_gw_channel', 'plc')
        config["parse"] = parse_cfg

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

    # ==================== 主题与字体 ====================

    def _is_dark_theme(self) -> bool:
        """当前是否为暗色主题"""
        return self._theme_id == "dark"

    def _make_stats_label(self, text: str = "", size: int = 12) -> QLabel:
        """创建随主题适配的统计/状态标签（注册到列表，主题切换时统一重设）"""
        lbl = QLabel(text)
        lbl.setStyleSheet(self._stats_style(size))
        self._stats_labels.append((lbl, size))
        return lbl

    def _stats_style(self, size: int = 12) -> str:
        """统计/状态标签样式（暗色主题下用浅灰文字）"""
        color = "#aaa" if self._is_dark_theme() else "#666"
        return f"color: {color}; font-size: {size}px;"

    def _make_toolbar_btn(self, text: str = "", height: int = 28,
                           min_width: int = 0, icon_btn: bool = False) -> QPushButton:
        """创建统一风格的工具栏按钮。

        参数:
            text: 按钮文本
            height: 统一高度（默认 28，与工具栏其他控件对齐）
            min_width: 最小宽度，0 表示由内容决定
            icon_btn: 是否为图标按钮（固定接近正方形、限制最大宽度）
        """
        btn = QPushButton(text)
        btn.setFont(self._ui_font(-1))
        btn.setMinimumHeight(height)
        if min_width:
            btn.setMinimumWidth(min_width)
        if icon_btn:
            btn.setMaximumWidth(height)
            # 保持内边距一致，避免不同主题下发散
            btn.setStyleSheet(f"QPushButton {{ padding: 2px {height // 4}px; }}")
        return btn

    def _batch_count_style(self) -> str:
        """批量解析帧计数标签样式"""
        if self._is_dark_theme():
            return "color: #bbb; font-size: 12px; padding: 2px 10px; background: #3a3a3a; border-radius: 10px;"
        return "color: #666; font-size: 12px; padding: 2px 10px; background: #f0f0f0; border-radius: 10px;"

    def _batch_status_style(self) -> str:
        """批量解析状态栏样式"""
        if self._is_dark_theme():
            return ("color: #bbb; font-size: 12px; padding: 4px 10px; "
                    "background: #333333; border: 1px solid #555555; border-radius: 4px;")
        return ("color: #666; font-size: 12px; padding: 4px 10px; "
                "background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 4px;")

    def _serial_status_style(self, color: str, bold: bool = False) -> str:
        """串口状态标签样式（灰色在暗色下提亮；同时记录当前颜色/粗体供主题切换重设）"""
        self._serial_status_color = color
        self._serial_status_bold = bold
        if self._is_dark_theme() and color == "#999":
            color = "#bbb"
        weight = " font-weight: bold;" if bold else ""
        return f"color: {color}; font-size: 12px;{weight}"

    def _serial_refresh_style(self) -> str:
        """串口刷新按钮样式（hover 色随主题明暗）"""
        if self._is_dark_theme():
            return ("QPushButton { background: transparent; border: none; padding: 2px; }"
                    "QPushButton:hover { background: rgba(255,255,255,25); border-radius: 3px; }"
                    "QPushButton:pressed { background: rgba(255,255,255,50); }")
        return ("QPushButton { background: transparent; border: none; padding: 2px; }"
                "QPushButton:hover { background: rgba(0,0,0,20); border-radius: 3px; }"
                "QPushButton:pressed { background: rgba(0,0,0,40); }")

    def _ui_font(self, delta: int = 0, bold: bool = False, family: str = None) -> QFont:
        """统一字体：字号跟随配置 _font_size，字体族跟随配置 _font_family（可覆盖）。

        层级约定（相对 _font_size，默认10）：
          delta=0  正文/搜索框/编辑区/主下拉
          delta=-1 普通标签/输入框/按钮/次要说明
          delta=-2 表格
          delta=+6 大标题
        """
        f = QFont(family or self._font_family, self._font_size + delta)
        f.setBold(bold)
        return f

    def _restyle_for_theme(self):
        """主题切换后重设动态控件样式（统计标签/串口状态/批量状态等）"""
        for lbl, size in self._stats_labels:
            try:
                lbl.setStyleSheet(self._stats_style(size))
            except RuntimeError:
                pass  # 退出时 C++ 对象已析构，忽略
        if hasattr(self, "serial_status_label"):
            try:
                self.serial_status_label.setStyleSheet(
                    self._serial_status_style(self._serial_status_color, self._serial_status_bold))
            except RuntimeError:
                pass
        if hasattr(self, "serial_refresh_btn"):
            try:
                self.serial_refresh_btn.setStyleSheet(self._serial_refresh_style())
            except RuntimeError:
                pass
        if hasattr(self, "batch_frame_count_label"):
            try:
                self.batch_frame_count_label.setStyleSheet(self._batch_count_style())
            except RuntimeError:
                pass
        if hasattr(self, "batch_status_bar"):
            try:
                self.batch_status_bar.setStyleSheet(self._batch_status_style())
            except RuntimeError:
                pass

    def _show_theme_settings_dialog(self):
        """显示主题与字体设置对话框（含系统集成设置）"""
        dialog = ThemeSettingsDialog(self._theme_id, self._font_family, self._font_size, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._theme_id, self._font_family, self._font_size = dialog.get_settings()
            self._save_app_config()
            # 应用系统集成设置（自启 / 热键 / 关闭行为）
            sys_settings = dialog.get_system_settings()
            self._apply_system_settings(sys_settings)
        # 无论确定/取消（取消时对话框已还原主题），同步动态控件样式
        self._restyle_for_theme()

    def _show_system_settings_dialog(self):
        """显示系统集成设置对话框（配置菜单→系统集成设置）"""
        from system_integration.system_settings import SystemIntegrationSettings
        dialog = QDialog(self)
        dialog.setWindowTitle("系统集成设置")
        dialog.setMinimumWidth(560)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        layout = QVBoxLayout(dialog)
        panel = SystemIntegrationSettings(dialog)
        layout.addWidget(panel)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_system_settings(panel.save_settings())

    def _show_llm_api_manager(self):
        """显示 LLM 模型 API 管理对话框"""
        dlg = LLMApiManagerDialog(self)
        dlg.exec()
        # 关闭后刷新 LLM 预处理面板的模型列表
        if hasattr(self, "llm_preprocess_widget"):
            self.llm_preprocess_widget._refresh_profiles()

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
            self.serial_status_label.setStyleSheet(self._serial_status_style("#999"))
            self._save_serial_config()
        else:
            port = self.serial_port_combo.currentText()
            if not port:
                QMessageBox.warning(self, "警告", "请先选择串口端口")
                return
            baud = self._get_baud_value()
            if baud is None:
                return
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
            self.serial_status_label.setStyleSheet(self._serial_status_style("#999"))

    def _on_serial_error(self, msg: str):
        """串口错误回调"""
        self.serial_status_label.setText(f"错误: {msg}")
        self.serial_status_label.setStyleSheet(self._serial_status_style("#f44336"))


def main():
    # 修复 Windows 终端中文乱码：将 stdout/stderr 切换为 UTF-8
    # PyInstaller GUI 模式（console=False）下 sys.stdout/stderr 为 None，需守卫
    if sys.platform == 'win32':
        import io
        if sys.stdout is not None:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if sys.stderr is not None:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    # 单实例：已有实例在运行则传参并退出
    from system_integration.single_instance import try_connect_existing
    if try_connect_existing(sys.argv[1:]):
        return 0

    app = QApplication(sys.argv)

    # 提前设全局默认字体，避免 Qt 回退到 MS Sans Serif 触发 DirectWrite 警告
    app.setFont(QFont("Microsoft YaHei UI", 9))

    # 应用主题与字体设置（从 config.json 读取，未配置时使用默认浅色主题 + 微软雅黑 10pt）
    ThemeManager.apply_from_file(app)

    window = MainWindow()

    # 处理命令行参数（--parse / --protocol / --file / --minimized / --clipboard）
    cli_args = [a for a in sys.argv[1:] if a]
    has_parse_action = any(a in ("--parse", "--file", "--clipboard") for a in cli_args)

    if cli_args and not has_parse_action:
        window.show()
        window._handle_cli_args(cli_args)
    elif has_parse_action:
        # 解析动作：不显示主窗口，直接弹解析结果（避免窗口太多）
        window._handle_cli_args(cli_args)
    else:
        window.show()

    sys.exit(app.exec())




class _PyScriptWorker(QObject):
    """Python 脚本后台执行 Worker

    在独立线程中加载并运行脚本，通过信号返回结果或错误。
    """

    finished = Signal(str)    # 成功：返回处理后文本
    error = Signal(str)       # 失败：返回错误消息

    def __init__(self, script_path, input_text, context):
        super().__init__()
        self._script_path = script_path
        self._input_text = input_text
        self._context = context

    def run(self):
        import time
        t0 = time.time()
        try:
            from py_script_engine import load_script, run_script
            t1 = time.time()
            module = load_script(self._script_path)
            t2 = time.time()
            result = run_script(module, self._input_text, self._context)
            t3 = time.time()
            print(f"[脚本线程] import: {(t1-t0)*1000:.1f}ms, "
                  f"load: {(t2-t1)*1000:.1f}ms, "
                  f"run: {(t3-t2)*1000:.1f}ms, "
                  f"total: {(t3-t0)*1000:.1f}ms")
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


if __name__ == "__main__":
    main()
