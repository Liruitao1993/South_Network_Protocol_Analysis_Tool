"""实时报文监控器组件

南网新一代(协议索引9) / 国网新一代(协议索引10) 专用：
- 监听 SerialWorker.raw_data_received 原始字节流，按静默间隔（默认30ms）自动组帧
- 左侧帧列表（序号/时间/方向/长度/摘要），环形缓冲最多1000帧，增量更新
- 右侧详情：单击帧行展示完整解析表格 + 原始HEX，点击解析行高亮对应字节
- 双击帧行送入主界面单帧解析页
- 报文过滤器：SNID/NID、帧类型、MSDU类型过滤（仅影响UI显示）
- 实时CSV日志记录（全量记录，不受过滤影响）

解析器与摘要函数由 main_gui 注入（set_protocol），避免横向耦合。
"""

import csv
import os
from collections import deque
from datetime import datetime
from typing import Callable, List, Optional, Set

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QTextCursor, QTextCharFormat
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QSpinBox, QCheckBox,
    QTextEdit, QFileDialog, QMessageBox, QHeaderView, QAbstractItemView,
    QLineEdit, QMenu,
)


class RealtimeMonitorWidget(QWidget):
    """实时报文监控器标签页"""

    MAX_FRAMES = 1000  # 环形缓冲上限

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parser = None                                # 当前协议解析器实例
        self._summary_fn: Optional[Callable[[list], str]] = None   # 摘要生成回调
        self._send_to_single_fn: Optional[Callable[[str], None]] = None  # 送单帧解析回调
        self._serial_worker = None
        # 监控包装格式：hplc=96..16(国网新一代) / plc2=ED..EE(新一代通感一体化/PLC2.0收发机)
        self._wrapper_format = "hplc"

        self._frames: deque = deque(maxlen=self.MAX_FRAMES)  # 帧记录环形缓冲
        self._rx_buffer = bytearray()                        # 未组帧字节缓冲
        self._paused = False
        self._seq = 0                                        # 帧序号（不清空时持续递增）
        self._filtered_count = 0                             # 被过滤掉的帧计数

        # CSV 实时日志状态
        self._csv_file = None
        self._csv_writer = None
        self._csv_path = ""
        self._csv_count = 0

        # 静默间隔组帧定时器：超时说明一帧结束
        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.timeout.connect(self._flush_frame)

        self._build_ui()

    # ================================================================
    # 外部注入接口
    # ================================================================
    def set_serial_worker(self, worker):
        """绑定串口工作线程，监听原始数据信号"""
        if self._serial_worker is not None:
            try:
                self._serial_worker.raw_data_received.disconnect(self._on_raw_data)
            except (TypeError, RuntimeError):
                pass
        self._serial_worker = worker
        if worker is not None:
            worker.raw_data_received.connect(self._on_raw_data)

    def set_protocol(self, parser, summary_fn: Optional[Callable[[list], str]] = None,
                     wrapper_format: str = "hplc"):
        """注入当前协议的解析器与摘要函数；协议切换时清空已有记录

        wrapper_format: 监控包装格式
            - "hplc": 96H..16H 包装（国网新一代 HPLC 监控设备）
            - "plc2": ED..EE 包装（新一代通感一体化 PLC2.0 收发机，参考
              《PLC2.0收发机报文格式》ED+帧长(2,LE)+控制域1+控制域2+EF+数据域+CS+EE）
        """
        self._parser = parser
        self._summary_fn = summary_fn
        self._wrapper_format = wrapper_format
        self._apply_wrapper_format()
        self.clear_frames()

    def _apply_wrapper_format(self):
        """根据包装格式更新解帧复选框的标签与说明，以及过滤器SNID/NID标签"""
        if self._wrapper_format == "plc2":
            self.deframe_chk.setText("监控解帧(ED..EE)")
            self.deframe_chk.setToolTip(
                "按 PLC2.0 收发机包装格式自动解帧：\n"
                "ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)\n"
                "数据域(数据报文): 物理信道(1)+时间戳(4,LE)+物理块个数(1)+保留/CRC(1)"
                "+单个物理块长度(2,LE)+数据FC/Payload(变长)\n"
                "可正确处理连帧；开启时忽略静默间隔与剔除设置"
            )
            self.snid_nid_label.setText("SNID:")
            self.snid_nid_edit.setPlaceholderText("如 1,5,12 (空=不过滤)")
            self.snid_nid_edit.setToolTip("保留显示的短网络标识(SNID)，范围 0~31，逗号分隔，空表示不过滤")
        else:
            self.deframe_chk.setText("监控解帧(96..16)")
            self.deframe_chk.setToolTip(
                "按监控包装格式自动解帧：\n"
                "96H(1)+RSSI(1)+NTB(4)+[LEN(12b)+协议类型(3b)+CHANNEL(1b)](2)+DATA(LEN)+CS(1)+16H(1)\n"
                "可正确处理连帧与 DATA 内含 0x16 的情况；开启时忽略静默间隔与剔除设置"
            )
            self.snid_nid_label.setText("NID:")
            self.snid_nid_edit.setPlaceholderText("如 1,100 (空=不过滤)")
            self.snid_nid_edit.setToolTip("保留显示的网络标识(NID)，范围 1~65535，逗号分隔，空表示不过滤")

    def set_send_to_single_handler(self, fn: Callable[[str], None]):
        """注入"送入单帧解析"回调（参数为空格分隔的 hex 字符串）"""
        self._send_to_single_fn = fn

    # ================================================================
    # UI 构建
    # ================================================================
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---------- 工具栏 ----------
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.auto_scroll_chk = QCheckBox("自动滚动")
        self.auto_scroll_chk.setChecked(True)
        toolbar.addWidget(self.auto_scroll_chk)

        self.pause_btn = QPushButton("暂停接收")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause_toggled)
        toolbar.addWidget(self.pause_btn)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear_frames)
        toolbar.addWidget(clear_btn)

        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(export_btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("静默间隔:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 200)
        self.interval_spin.setValue(30)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setToolTip("串口数据静默超过该时长即判定为一帧结束")
        toolbar.addWidget(self.interval_spin)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("剔除头部:"))
        self.strip_head_spin = QSpinBox()
        self.strip_head_spin.setRange(0, 64)
        self.strip_head_spin.setValue(0)
        self.strip_head_spin.setSuffix(" 字节")
        self.strip_head_spin.setToolTip("解析前剔除报文头部的 N 个字节（如监控包装头）")
        self.strip_head_spin.valueChanged.connect(self._on_strip_changed)
        toolbar.addWidget(self.strip_head_spin)

        toolbar.addWidget(QLabel("剔除尾部:"))
        self.strip_tail_spin = QSpinBox()
        self.strip_tail_spin.setRange(0, 64)
        self.strip_tail_spin.setValue(0)
        self.strip_tail_spin.setSuffix(" 字节")
        self.strip_tail_spin.setToolTip("解析前剔除报文尾部的 M 个字节（如校验和/帧尾）")
        self.strip_tail_spin.valueChanged.connect(self._on_strip_changed)
        toolbar.addWidget(self.strip_tail_spin)

        toolbar.addSpacing(12)
        self.deframe_chk = QCheckBox("监控解帧(96..16)")
        self.deframe_chk.setChecked(True)
        self.deframe_chk.setToolTip(
            "按监控包装格式自动解帧：\n"
            "96H(1)+RSSI(1)+NTB(4)+[LEN(12b)+协议类型(3b)+CHANNEL(1b)](2)+DATA(LEN)+CS(1)+16H(1)\n"
            "可正确处理连帧与 DATA 内含 0x16 的情况；开启时忽略静默间隔与剔除设置"
        )
        self.deframe_chk.toggled.connect(self._on_deframe_toggled)
        toolbar.addWidget(self.deframe_chk)
        # 初始同步：默认开启解帧，禁用静默间隔/剔除设置
        self.interval_spin.setEnabled(not self.deframe_chk.isChecked())
        self.strip_head_spin.setEnabled(not self.deframe_chk.isChecked())
        self.strip_tail_spin.setEnabled(not self.deframe_chk.isChecked())

        toolbar.addStretch()
        self.count_label = QLabel("显示 0 帧")
        self.count_label.setStyleSheet("color: #666;")
        toolbar.addWidget(self.count_label)

        layout.addLayout(toolbar)

        # ---------- 过滤器工具栏 ----------
        filter_toolbar = QHBoxLayout()
        filter_toolbar.setSpacing(8)

        self.filter_enabled_chk = QCheckBox("启用过滤")
        self.filter_enabled_chk.setChecked(False)
        self.filter_enabled_chk.setToolTip("启用后，仅符合条件的报文在UI中显示；CSV日志不受影响")
        filter_toolbar.addWidget(self.filter_enabled_chk)

        self.snid_nid_label = QLabel("NID:")
        filter_toolbar.addWidget(self.snid_nid_label)
        self.snid_nid_edit = QLineEdit()
        self.snid_nid_edit.setFixedWidth(120)
        self.snid_nid_edit.setPlaceholderText("如 1,100 (空=不过滤)")
        self.snid_nid_edit.setToolTip("保留显示的网络标识(NID)，范围 1~65535，逗号分隔，空表示不过滤")
        filter_toolbar.addWidget(self.snid_nid_edit)

        filter_toolbar.addSpacing(8)
        filter_toolbar.addWidget(QLabel("帧类型:"))
        self.frame_type_btn = QPushButton("全部")
        self.frame_type_btn.setFixedWidth(100)
        self.frame_type_btn.setToolTip("选择要保留显示的帧类型（多选）")
        self._frame_type_menu = QMenu(self)
        self._frame_type_options = ["信标帧", "SOF帧", "选择确认帧(SACK)", "网间协调帧"]
        self._frame_type_actions: List[QAction] = []
        for name in self._frame_type_options:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(self._update_frame_type_btn_text)
            self._frame_type_menu.addAction(action)
            self._frame_type_actions.append(action)
        self.frame_type_btn.setMenu(self._frame_type_menu)
        filter_toolbar.addWidget(self.frame_type_btn)

        filter_toolbar.addSpacing(8)
        filter_toolbar.addWidget(QLabel("MSDU类型:"))
        self.msdu_type_btn = QPushButton("全部")
        self.msdu_type_btn.setFixedWidth(120)
        self.msdu_type_btn.setToolTip("选择要保留显示的MSDU类型（多选）")
        self._msdu_type_menu = QMenu(self)
        self._msdu_type_options = ["网络管理消息", "应用层报文", "IP报文"]
        self._msdu_type_actions: List[QAction] = []
        for name in self._msdu_type_options:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(self._update_msdu_type_btn_text)
            self._msdu_type_menu.addAction(action)
            self._msdu_type_actions.append(action)
        self.msdu_type_btn.setMenu(self._msdu_type_menu)
        filter_toolbar.addWidget(self.msdu_type_btn)

        filter_toolbar.addSpacing(8)
        self.invert_filter_chk = QCheckBox("反向过滤")
        self.invert_filter_chk.setToolTip("勾选时表示隐藏匹配的帧（而非保留）")
        filter_toolbar.addWidget(self.invert_filter_chk)

        filter_toolbar.addSpacing(16)
        self.csv_record_btn = QPushButton("开始记录")
        self.csv_record_btn.setCheckable(True)
        self.csv_record_btn.toggled.connect(self._on_csv_record_toggled)
        self.csv_record_btn.setToolTip("开启/停止实时CSV日志记录（全量记录，不受过滤影响）")
        filter_toolbar.addWidget(self.csv_record_btn)

        self.csv_status_label = QLabel("未记录")
        self.csv_status_label.setStyleSheet("color: #888;")
        filter_toolbar.addWidget(self.csv_status_label)

        filter_toolbar.addSpacing(8)
        self.csv_path_label = QLabel("路径: 未记录")
        self.csv_path_label.setStyleSheet("color: #666; font-family: Consolas, monospace; font-size: 11px;")
        self.csv_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.csv_path_label.setMaximumWidth(350)
        filter_toolbar.addWidget(self.csv_path_label)

        self.browse_log_btn = QPushButton("浏览")
        self.browse_log_btn.setFixedWidth(60)
        self.browse_log_btn.setContentsMargins(8, 0, 8, 0)
        self.browse_log_btn.setToolTip("打开日志目录")
        self.browse_log_btn.clicked.connect(self._open_log_directory)
        filter_toolbar.addWidget(self.browse_log_btn)

        filter_toolbar.addStretch()

        layout.addLayout(filter_toolbar)

        # ---------- 主区域：左帧列表 / 右详情 ----------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：帧列表
        self.frame_table = QTableWidget(0, 5)
        self.frame_table.setHorizontalHeaderLabels(["序号", "时间", "方向", "长度", "摘要"])
        self.frame_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.frame_table.setColumnWidth(0, 55)
        self.frame_table.setColumnWidth(1, 100)
        self.frame_table.setColumnWidth(2, 45)
        self.frame_table.setColumnWidth(3, 55)
        self.frame_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.frame_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.frame_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.frame_table.verticalHeader().hide()
        self.frame_table.currentCellChanged.connect(self._on_frame_row_changed)
        self.frame_table.cellDoubleClicked.connect(self._on_frame_double_clicked)
        splitter.addWidget(self.frame_table)

        # 右侧：解析表格 + 原始HEX（上下分割）
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        self.detail_table = QTableWidget(0, 4)
        self.detail_table.setHorizontalHeaderLabels(["字段名", "原始值", "解析值", "说明"])
        self.detail_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.detail_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.verticalHeader().hide()
        self.detail_table.currentCellChanged.connect(self._on_detail_row_changed)
        right_splitter.addWidget(self.detail_table)

        self.hex_text = QTextEdit()
        self.hex_text.setReadOnly(True)
        self.hex_text.setFont(QFont("Consolas", 10))
        self.hex_text.setPlaceholderText("选中左侧帧后显示原始报文；点击解析表格行可高亮对应字节")
        right_splitter.addWidget(self.hex_text)

        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)
        splitter.addWidget(right_splitter)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

    # ================================================================
    # 帧重组（静默间隔组帧 / 监控包装解帧）
    # ================================================================
    def _on_raw_data(self, data: bytes):
        """收到串口原始数据（GUI线程执行）

        - 监控解帧模式：累积到缓冲区，按 96..16 包装格式逐包抽取，剩余不完整字节留待
        - 静默间隔模式：累积并重启静默定时器，超时即一帧
        """
        if self._paused:
            return
        self._rx_buffer.extend(data)
        if self.deframe_chk.isChecked():
            self._drain_wrapper_buffer()
        else:
            self._frame_timer.start(self.interval_spin.value())

    def _flush_frame(self):
        """静默超时：缓冲区内容作为一帧处理"""
        if not self._rx_buffer:
            return
        frame = bytes(self._rx_buffer)
        self._rx_buffer.clear()
        self._process_frame(frame)

    # ---- 监控包装解帧 --------------------------------------------
    MAX_WRAP_LEN = 2048  # 单包 DATA 最大字节数（防止伪帧头声明超长导致停滞）

    def _drain_wrapper_buffer(self):
        """从缓冲区中按监控包装格式抽取所有完整包，逐包解析；剩余字节留在缓冲区"""
        if self._wrapper_format == "plc2":
            packets, consumed = self._deframe_plc2_wrapper(self._rx_buffer)
        else:
            packets, consumed = self._deframe_wrapper(self._rx_buffer)
        if consumed > 0:
            del self._rx_buffer[:consumed]
        for meta, data in packets:
            self._process_frame(bytes(data), meta=meta)

    def _deframe_wrapper(self, buf) -> tuple:
        """按监控包装格式切分缓冲区

        包结构: 96H(1) + RSSI(1) + NTB(4,小端) + [LEN(12b)+协议类型(3b)+CHANNEL(1b)](2)
                  + DATA(LEN) + CS(1) + 16H(1)
          - LEN 低字节在前: LEN = byte6 | ((byte7 & 0x0F) << 8)
          - 协议类型 = (byte7 >> 4) & 0x07，CHANNEL = (byte7 >> 7) & 0x01
          - CS = 帧头 96 到 CS 前所有字节累加和 & 0xFF

        返回 (packets, consumed):
          packets = [(meta_dict, data_bytes), ...]；consumed = 已处理字节数（之前可删）
        """
        packets = []
        i = 0
        n = len(buf)
        while i < n:
            if buf[i] != 0x96:
                i += 1
                continue
            if i + 8 > n:
                break  # 包头不完整，等待更多数据
            b6 = buf[i + 6]
            b7 = buf[i + 7]
            length = b6 | ((b7 & 0x0F) << 8)
            if length > self.MAX_WRAP_LEN:
                i += 1  # LEN 不合理，判为伪帧头
                continue
            total = 8 + length + 2  # 头 + DATA + CS + 16H
            if i + total > n:
                break  # 整包不完整，等待更多数据
            if buf[i + total - 1] != 0x16:
                i += 1  # 帧尾不是 0x16，判为伪帧头
                continue
            data = bytes(buf[i + 8:i + 8 + length])
            cs = buf[i + 8 + length]
            calc_cs = sum(buf[i:i + 8 + length]) & 0xFF
            meta = {
                "rssi": buf[i + 1],
                "ntb": int.from_bytes(bytes(buf[i + 2:i + 6]), "little"),
                "len": length,
                "proto_type": (b7 >> 4) & 0x07,
                "channel": (b7 >> 7) & 0x01,
                "cs": cs,
                "cs_ok": calc_cs == cs,
            }
            packets.append((meta, data))
            i += total
        return packets, i

    _PROTO_TYPE_NAMES = {
        0: "国网HPLC", 1: "南网宽带", 2: "IEEE1901", 3: "国网HPLC双模块",
    }

    def _build_hplc_meta_rows(self, meta: dict) -> list:
        """将 HPLC(96..16) 监控包装头信息生成详情表前置行（不参与字节高亮）"""
        ch = "RF" if meta["channel"] else "HPLC"
        cs_txt = "✓ 正确" if meta["cs_ok"] else "✗ 错误"
        proto = self._PROTO_TYPE_NAMES.get(meta["proto_type"], f"保留({meta['proto_type']})")
        return [
            ("── 监控包装 ──", "", "", "监控设备附加信息（不属于业务帧）", None, None),
            ("信号强度(RSSI)", str(meta["rssi"]), str(meta["rssi"]), "监控点接收信号强度", None, None),
            ("NTB", f"0x{meta['ntb']:08X}", str(meta["ntb"]), "接收NTB值(低字节在前)", None, None),
            ("帧长度(LEN)", str(meta["len"]), f"{meta['len']} 字节", "DATA长度(12bit低字节在前)", None, None),
            ("协议类型", str(meta["proto_type"]), proto, "0-国网HPLC 1-南网宽带 2-IEEE1901 3-国网HPLC双模块", None, None),
            ("信道(CHANNEL)", str(meta["channel"]), ch, "0:HPLC 1:RF", None, None),
            ("校验和(CS)", f"0x{meta['cs']:02X}", cs_txt, "帧头到CS前累加和 & 0xFF", None, None),
            ("── 业务帧(DATA) ──", "", "", "以下为载波业务帧解析结果", None, None),
        ]

    # ================================================================
    # PLC2.0 收发机包装（ED..EE，新一代通感一体化/PLC2.0）
    # 参考《PLC2.0收发机报文格式0629.docx》
    # ================================================================
    _PLC2_CTRL1_NAMES = {0x00: "数据报文", 0x01: "控制报文"}
    # 控制域2（数据报文）子类型
    _PLC2_CTRL2_DATA_NAMES = {
        0x01: "FC数据", 0x02: "FC+Payload数据", 0x03: "Payload数据",
        0x04: "发送完成", 0x05: "选择确认帧发送完成",
        0x06: "RF和HPLC同时发送FC+Payload", 0x07: "FC+Payload数据",
        0x08: "UL-OFDMA帧(DL-OFDMA的SACK帧)",
    }
    # 物理信道
    _PLC2_CHANNEL_NAMES = {
        0x01: "HPLC", 0x02: "RF", 0x03: "HPLC+RF", 0x20: "PLC2.0 OFDMA",
    }
    MAX_PLC2_LEN = 4096  # 单包数据域最大字节数（防止伪帧头声明超长导致停滞）

    def _plc2_channel_name(self, ch: int) -> str:
        if ch in self._PLC2_CHANNEL_NAMES:
            return self._PLC2_CHANNEL_NAMES[ch]
        if 0x10 <= ch <= 0x1C:
            return f"PLC2.0 MIMO(0x{ch:02X})"
        return f"保留(0x{ch:02X})"

    def _deframe_plc2_wrapper(self, buf) -> tuple:
        """按 PLC2.0 收发机包装格式(ED..EE)切分缓冲区

        包结构: ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)
          - 帧长 = 控制域1+控制域2+数据域起始符+数据域+校验 的总字节数 = 数据域长度 + 4
          - 整包长度 = 帧长 + 4
          - CS: 报文之前所有字节(ED..数据域末)求和取低8bit；暂保留，目前填0xFF
          - EF(数据域起始符) 与 EE(结束符) 作为强定界校验

        数据报文(控制域1=0x00) 控制域2=0x01/0x02/0x03 的数据域公共头(9字节):
          物理信道(1)+时间戳(4,LE)+物理块个数(1)+[保留/CRC](1)+单个物理块长度(2,LE)
          其后为 业务帧(数据FC / FC+Payload / Payload)，交给解析器。

        返回 (packets, consumed): packets=[(meta, business_bytes), ...]
          business_bytes 为空表示控制报文/其他子类型(无业务帧)。
        """
        packets = []
        i = 0
        n = len(buf)
        while i < n:
            if buf[i] != 0xED:
                i += 1
                continue
            if i + 6 > n:
                break  # 头部不完整(至少 ED+帧长2+控制域1+控制域2+EF)
            frame_len = buf[i + 1] | (buf[i + 2] << 8)  # = 数据域长度 + 4
            if frame_len < 4 or frame_len > self.MAX_PLC2_LEN:
                i += 1  # 帧长不合理，判为伪帧头
                continue
            total = frame_len + 4  # ED(1)+帧长(2)+[控制域1..CS=帧长]+EE(1)
            if i + total > n:
                break  # 整包不完整，等待更多数据
            # 强定界校验：数据域起始符 EF 与 结束符 EE
            if buf[i + 5] != 0xEF or buf[i + total - 1] != 0xEE:
                i += 1
                continue
            ctrl1 = buf[i + 3]
            ctrl2 = buf[i + 4]
            data_len = frame_len - 4
            data_start = i + 6
            data域 = bytes(buf[data_start:data_start + data_len])
            cs = buf[data_start + data_len]
            calc_cs = sum(buf[i:data_start + data_len]) & 0xFF  # ED..数据域末

            meta = {
                "ctrl1": ctrl1,
                "ctrl2": ctrl2,
                "ctrl1_name": self._PLC2_CTRL1_NAMES.get(ctrl1, f"保留(0x{ctrl1:02X})"),
                "ctrl2_name": (self._PLC2_CTRL2_DATA_NAMES if ctrl1 == 0x00 else {}).get(
                    ctrl2, f"保留(0x{ctrl2:02X})"),
                "frame_len": frame_len,
                "data_len": data_len,
                "cs": cs,
                "cs_ok": cs == calc_cs,
                "has_business": False,
            }

            # 数据报文 0x01/0x02/0x03：解析 9 字节公共头并提取业务帧
            if ctrl1 == 0x00 and ctrl2 in (0x01, 0x02, 0x03) and data_len >= 9:
                ch = data域[0]
                ts = int.from_bytes(data域[1:5], "little")
                pb_cnt = data域[5]
                flag6 = data域[6]  # 0x02=Payload是否CRC错误(0正确/1错误)；0x01/0x03=保留
                pb_len = int.from_bytes(data域[7:9], "little")
                business = data域[9:]
                meta.update({
                    "channel": ch,
                    "channel_name": self._plc2_channel_name(ch),
                    "timestamp": ts,
                    "pb_count": pb_cnt,
                    "flag6": flag6,
                    "pb_len": pb_len,
                    "payload_crc_err": (ctrl2 == 0x02 and flag6 == 1),
                    "has_business": True,
                    "business": business,
                })
            else:
                meta["raw_data"] = data域
            packets.append((meta, meta.get("business", b"")))
            i += total
        return packets, i

    def _build_meta_rows(self, meta: dict) -> list:
        """按当前包装格式生成详情表前置行（不参与字节高亮）"""
        if self._wrapper_format == "plc2":
            return self._build_plc2_meta_rows(meta)
        return self._build_hplc_meta_rows(meta)

    def _build_plc2_meta_rows(self, meta: dict) -> list:
        """PLC2.0 收发机(ED..EE) 包装头信息 -> 详情表前置行"""
        cs_txt = ("✓ 正确" if meta["cs_ok"] else
                  ("保留(目前0xFF)" if meta["cs"] == 0xFF else "✗ 错误"))
        rows = [
            ("── PLC2.0 收发机包装 ──", "", "", "监控设备附加信息（不属于业务帧）", None, None),
            ("控制域1", f"0x{meta['ctrl1']:02X}", meta["ctrl1_name"],
             "0x00-数据报文 0x01-控制报文", None, None),
            ("控制域2", f"0x{meta['ctrl2']:02X}", meta["ctrl2_name"], "报文子类型", None, None),
            ("帧长", str(meta["frame_len"]), f"{meta['frame_len']} 字节",
             "控制域1+控制域2+数据域起始符+数据域+校验(小端)", None, None),
            ("数据域长度", str(meta["data_len"]), f"{meta['data_len']} 字节", None, None, None),
        ]
        if meta.get("has_business"):
            crc_txt = "错误" if meta.get("payload_crc_err") else "正确/保留"
            rows += [
                ("物理信道", f"0x{meta['channel']:02X}", meta["channel_name"],
                 "0x01-HPLC 0x02-RF 0x03-HPLC+RF 0x10~0x1C-PLC2.0MIMO 0x20-OFDMA", None, None),
                ("时间戳", f"0x{meta['timestamp']:08X}", str(meta["timestamp"]),
                 "HW->PC 接收开始时间(小端)", None, None),
                ("物理块个数", str(meta["pb_count"]), str(meta["pb_count"]), None, None, None),
                ("Payload CRC", f"0x{meta['flag6']:02X}", crc_txt,
                 "控制域2=0x02时: 0-正确 1-错误；其余为保留", None, None),
                ("单个物理块长度", str(meta["pb_len"]), f"{meta['pb_len']} 字节(小端)", None, None, None),
                ("校验(CS)", f"0x{meta['cs']:02X}", cs_txt,
                 "报文之前所有字节求和取8bit；暂保留，目前填0xFF", None, None),
                ("── 业务帧(数据FC/Payload) ──", "", "", "以下为载波业务帧解析结果", None, None),
            ]
        else:
            rows += [
                ("数据域", ' '.join(f'{b:02X}' for b in meta.get("raw_data", b'')[:64]),
                 f"{meta['data_len']} 字节", "控制报文/其他子类型，原始数据域(最多展示64字节)", None, None),
                ("校验(CS)", f"0x{meta['cs']:02X}", cs_txt,
                 "报文之前所有字节求和取8bit；暂保留，目前填0xFF", None, None),
                ("── 无业务帧 ──", "", "", "控制报文/无载波业务帧解析结果", None, None),
            ]
        return rows

    def _meta_summary_prefix(self, meta: dict) -> str:
        """监控包装头信息的摘要前缀（按包装格式分派）"""
        if self._wrapper_format == "plc2":
            if meta.get("has_business"):
                flag = " CRC✗" if meta.get("payload_crc_err") else ""
                return f"[{meta['channel_name']} {meta['ctrl2_name']}{flag}] "
            return f"[{meta['ctrl1_name']} {meta['ctrl2_name']}] "
        ch = "RF" if meta["channel"] else "HPLC"
        cs_flag = "" if meta["cs_ok"] else " CS✗"
        return f"[RSSI:{meta['rssi']} {ch}{cs_flag}] "

    def _on_deframe_toggled(self, checked: bool):
        """切换监控解帧模式：开启时禁用静默间隔/剔除设置（由 LEN 自动定界）"""
        self.interval_spin.setEnabled(not checked)
        self.strip_head_spin.setEnabled(not checked)
        self.strip_tail_spin.setEnabled(not checked)
        # 切换模式时清空未组帧缓冲，避免旧模式残留字节干扰
        self._rx_buffer.clear()
        if self._frame_timer.isActive():
            self._frame_timer.stop()

    # ================================================================
    # 帧处理与列表更新
    # ================================================================
    def _process_frame(self, frame: bytes, meta: Optional[dict] = None):
        """接收一帧：建立记录，CSV全量记录，按过滤规则决定是否UI显示

        meta 非空时为监控包装解帧模式，frame 即已解出的 DATA（业务帧）。
        """
        self._seq += 1
        record = self._build_record(
            self._seq, datetime.now().strftime("%H:%M:%S.%f")[:-3], frame, meta=meta
        )

        # 1. 提取过滤字段（用于过滤判定和CSV记录）
        filter_fields = self._extract_filter_fields(record)

        # 2. 实时CSV记录（全量，不受过滤影响）
        self._write_csv_record(record, filter_fields)

        # 3. 过滤判定：决定是否在UI中显示
        if self._should_display_with_fields(record, filter_fields):
            self._frames.append(record)
            self._append_frame_row(record)
        else:
            self._filtered_count += 1

        self._update_count_label()

    def _build_record(self, seq: int, time_str: str, raw_frame: bytes,
                      meta: Optional[dict] = None) -> dict:
        """生成一条帧记录

        - meta 为空（静默间隔模式）：对 raw_frame 执行剔除头/尾后解析
        - meta 非空（监控解帧模式）：raw_frame 即已解出的 DATA，直接解析，
          并将监控包装头信息（RSSI/NTB/协议类型/CHANNEL/CS）前置到详情表

        解析帧用于解析、详情HEX、字节高亮与双击送单帧，保证偏移对齐；
        原始帧（raw）与 meta 一并保存，以便剔除参数变化时重新解析。
        """
        table_data: List[tuple] = []
        summary = "-"
        ok = True

        # 剔除头/尾字节（仅静默间隔模式；监控解帧模式 raw_frame 已是 DATA）
        parse_frame = raw_frame
        strip_error = None
        if meta is None:
            strip_head = self.strip_head_spin.value()
            strip_tail = self.strip_tail_spin.value()
            if strip_head > 0 or strip_tail > 0:
                total = len(raw_frame)
                tail_end = total - strip_tail if strip_tail > 0 else total
                if strip_head >= tail_end:
                    strip_error = (f"剔除字节过多（头{strip_head}+尾{strip_tail}），"
                                   f"报文仅{total}字节")
                else:
                    parse_frame = raw_frame[strip_head:tail_end]

        hex_str = ' '.join(f'{b:02X}' for b in parse_frame)

        if strip_error is not None:
            ok = False
            summary = strip_error
            table_data = [("❌ 剔除错误", "", "", strip_error, 0, max(len(raw_frame) - 1, 0))]
            hex_str = ' '.join(f'{b:02X}' for b in raw_frame)
        elif meta is not None and meta.get("has_business") is False:
            # PLC2.0 控制报文/无业务帧：不调用解析器，展示原始数据域
            summary = f"{meta.get('ctrl1_name', '')} {meta.get('ctrl2_name', '')}"
            table_data = [("ℹ️ 无业务帧", "", "",
                           f"{meta.get('ctrl1_name', '')}·{meta.get('ctrl2_name', '')}",
                           None, None)]
            hex_str = ' '.join(f'{b:02X}' for b in meta.get("raw_data", b''))
        elif self._parser is None:
            summary = "未设置解析器"
            ok = False
        else:
            try:
                table_data = self._parser.parse_to_table(parse_frame, parse_level="auto") or []
                if self._summary_fn is not None:
                    summary = self._summary_fn(table_data)
                if table_data and str(table_data[0][0]).startswith("❌"):
                    ok = False
            except Exception as e:
                ok = False
                summary = f"解析异常: {e}"
                table_data = [("❌ 解析异常", "", "", str(e), 0, max(len(parse_frame) - 1, 0))]

        # 监控解帧模式：前置包装头信息行，摘要加包装头前缀
        if meta is not None:
            table_data = self._build_meta_rows(meta) + table_data
            summary = self._meta_summary_prefix(meta) + summary
            # HPLC(96..16): CS错误标记失败；PLC2.0(ED..EE): CS为保留位不影响，
            # 仅 Payload CRC 错误(控制域2=0x02且标志位=1)标记失败
            if self._wrapper_format != "plc2":
                if not meta.get("cs_ok", True):
                    ok = False
            elif meta.get("payload_crc_err"):
                ok = False

        return {
            "seq": seq,
            "time": time_str,
            "direction": "RX",
            "length": (meta["data_len"] if (meta is not None and meta.get("has_business") is False)
                       else (len(parse_frame) if strip_error is None else len(raw_frame))),
            "raw": raw_frame,
            "meta": meta,
            "hex": hex_str,
            "summary": summary,
            "table_data": table_data,
            "ok": ok,
        }

    def _on_strip_changed(self, _value: int = 0):
        """剔除参数变化：用原始帧重新解析已接收的所有帧并刷新列表/详情"""
        if not self._frames:
            return
        cur_row = self.frame_table.currentRow()
        rebuilt = deque(maxlen=self.MAX_FRAMES)
        for rec in self._frames:
            rebuilt.append(self._build_record(
                rec["seq"], rec["time"], rec["raw"], meta=rec.get("meta")))
        self._frames = rebuilt
        self._rebuild_frame_table()
        # 恢复选中行并刷新详情
        if 0 <= cur_row < len(self._frames):
            self.frame_table.setCurrentCell(cur_row, 0)

    def _rebuild_frame_table(self):
        """根据 _frames 重建整个帧列表"""
        auto = self.auto_scroll_chk.isChecked()
        self.auto_scroll_chk.setChecked(False)  # 重建期间不自动滚底
        self.frame_table.setRowCount(0)
        for rec in self._frames:
            self._append_frame_row(rec)
        self.auto_scroll_chk.setChecked(auto)
        self._update_count_label()

    def _append_frame_row(self, record: dict):
        """增量追加一行到帧列表（与 _frames 索引一一对应）"""
        # deque 已满时会丢弃最旧记录，表格同步删除首行
        if self.frame_table.rowCount() >= self.MAX_FRAMES:
            self.frame_table.removeRow(0)

        row = self.frame_table.rowCount()
        self.frame_table.insertRow(row)
        values = [
            str(record["seq"]),
            record["time"],
            record["direction"],
            str(record["length"]),
            record["summary"],
        ]
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            if not record["ok"]:
                item.setForeground(QColor("#C00000"))
            self.frame_table.setItem(row, col, item)

        if self.auto_scroll_chk.isChecked():
            self.frame_table.scrollToBottom()

    # ================================================================
    # 帧选中 → 详情展示
    # ================================================================
    def _on_frame_row_changed(self, row: int, _col: int, _prev_row: int, _prev_col: int):
        if row < 0 or row >= len(self._frames):
            return
        record = self._frames[row]
        self._show_detail(record)

    def _show_detail(self, record: dict):
        """填充解析表格与原始HEX"""
        # 解析表格
        table_data = record["table_data"]
        self.detail_table.setRowCount(0)  # 先清空，避免触发高亮槽
        self.detail_table.setRowCount(len(table_data))
        for i, item in enumerate(table_data):
            name = str(item[0]) if len(item) > 0 else ""
            raw = str(item[1]) if len(item) > 1 else ""
            parsed = str(item[2]) if len(item) > 2 else ""
            comment = str(item[3]) if len(item) > 3 else ""
            byte_start = item[4] if len(item) > 4 else None
            byte_end = item[5] if len(item) > 5 else None

            name_item = QTableWidgetItem(name)
            # 字节范围存于首列 item，供点击高亮使用
            name_item.setData(Qt.ItemDataRole.UserRole, byte_start)
            name_item.setData(Qt.ItemDataRole.UserRole + 1, byte_end)
            self.detail_table.setItem(i, 0, name_item)
            self.detail_table.setItem(i, 1, QTableWidgetItem(raw))
            self.detail_table.setItem(i, 2, QTableWidgetItem(parsed))
            self.detail_table.setItem(i, 3, QTableWidgetItem(comment))

        # 原始HEX
        self.hex_text.setPlainText(record["hex"])
        self.hex_text.setExtraSelections([])

    def _on_detail_row_changed(self, row: int, _col: int, _prev_row: int, _prev_col: int):
        """点击解析表格行：高亮HEX中对应字节（byte_start/byte_end 为闭区间）"""
        if row < 0:
            return
        item = self.detail_table.item(row, 0)
        if item is None:
            return
        byte_start = item.data(Qt.ItemDataRole.UserRole)
        byte_end = item.data(Qt.ItemDataRole.UserRole + 1)
        if byte_start is None or byte_end is None:
            self.hex_text.setExtraSelections([])
            return

        # "XX XX XX ..." 格式中第 i 字节对应字符位置 i*3 ~ i*3+1
        char_start = byte_start * 3
        char_end = byte_end * 3 + 2
        text_len = len(self.hex_text.toPlainText())
        if char_start >= text_len:
            return
        char_end = min(char_end, text_len)

        cursor = QTextCursor(self.hex_text.document())
        cursor.setPosition(char_start)
        cursor.setPosition(char_end, QTextCursor.MoveMode.KeepAnchor)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FFE58F"))
        fmt.setForeground(QColor("#000000"))

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = fmt
        self.hex_text.setExtraSelections([selection])

    # ================================================================
    # 双击送单帧解析
    # ================================================================
    def _on_frame_double_clicked(self, row: int, _col: int):
        if row < 0 or row >= len(self._frames):
            return
        if self._send_to_single_fn is not None:
            self._send_to_single_fn(self._frames[row]["hex"])

    # ================================================================
    # 工具栏动作
    # ================================================================
    def _on_pause_toggled(self, checked: bool):
        self._paused = checked
        self.pause_btn.setText("继续接收" if checked else "暂停接收")
        if checked:
            # 暂停时丢弃未组帧数据，避免恢复后拼出假帧
            self._frame_timer.stop()
            self._rx_buffer.clear()

    def clear_frames(self):
        """清空帧列表、缓冲与详情"""
        self._frame_timer.stop()
        self._rx_buffer.clear()
        self._frames.clear()
        self._filtered_count = 0
        self.frame_table.setRowCount(0)
        self.detail_table.setRowCount(0)
        self.hex_text.clear()
        self._update_count_label()

    def _export_csv(self):
        """导出监控记录为 CSV"""
        if not self._frames:
            QMessageBox.information(self, "提示", "暂无监控记录可导出")
            return
        default_name = f"monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出监控记录", default_name, "CSV文件 (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["序号", "时间", "方向", "长度", "摘要", "原始HEX"])
                for rec in self._frames:
                    writer.writerow([
                        rec["seq"], rec["time"], rec["direction"],
                        rec["length"], rec["summary"], rec["hex"],
                    ])
            QMessageBox.information(self, "导出成功", f"已导出 {len(self._frames)} 条记录到:\n{path}")
        except OSError as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ================================================================
    # 计数标签更新
    # ================================================================
    def _update_count_label(self):
        """更新帧计数标签：显示数 / 过滤数 / 记录数"""
        parts = [f"显示 {len(self._frames)} 帧"]
        if self._filtered_count > 0:
            parts.append(f"过滤 {self._filtered_count}")
        if self._csv_count > 0:
            parts.append(f"记录 {self._csv_count}")
        self.count_label.setText(" / ".join(parts))

    # ================================================================
    # 报文过滤器
    # ================================================================
    def _extract_filter_fields(self, record: dict) -> dict:
        """从帧记录的解析结果中提取过滤用字段"""
        fields = {}
        for item in record.get("table_data", []):
            if len(item) < 4:
                continue
            name = str(item[0]).strip()
            parsed = str(item[2]) if item[2] is not None else ""
            comment = str(item[3]) if item[3] is not None else ""

            # SNID（南网新一代）: comment 含 "完整SNID=0x0A(10)"
            if "完整SNID" in comment and "snid" not in fields:
                try:
                    # 提取括号内的数值
                    fields["snid"] = int(comment.split("(")[1].rstrip(")"))
                except (IndexError, ValueError):
                    pass
            elif name == "短网络标识低位(SNID)" and "snid" not in fields:
                try:
                    fields["snid"] = int(parsed)
                except ValueError:
                    pass

            # NID（国网新一代）: 字段名 "网络标识(NID)"
            if name == "网络标识(NID)" and "nid" not in fields:
                try:
                    fields["nid"] = int(parsed)
                except ValueError:
                    pass

            # 定界符类型
            if name == "定界符类型" and "frame_type" not in fields:
                fields["frame_type"] = comment  # 如 "DT=1: SOF帧" 或 "SOF帧"

            # MSDU类型
            if name == "MSDU类型" and "msdu_type" not in fields:
                fields["msdu_type"] = comment  # 如 "应用层报文" / "网络管理消息"

        return fields

    def _get_filter_ids(self) -> Set[int]:
        """解析 SNID/NID 输入框中的数值列表"""
        text = self.snid_nid_edit.text().strip()
        if not text:
            return set()
        ids = set()
        for part in text.replace("，", ",").split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
            elif part.startswith("0x") or part.startswith("0X"):
                try:
                    ids.add(int(part, 16))
                except ValueError:
                    pass
        return ids

    def _get_selected_frame_types(self) -> Set[str]:
        """获取帧类型多选中已选中的类型名称"""
        selected = set()
        all_checked = True
        for action in self._frame_type_actions:
            if action.isChecked():
                selected.add(action.text())
            else:
                all_checked = False
        # 全选等同于不过滤
        return set() if all_checked else selected

    def _get_selected_msdu_types(self) -> Set[str]:
        """获取MSDU类型多选中已选中的类型名称"""
        selected = set()
        all_checked = True
        for action in self._msdu_type_actions:
            if action.isChecked():
                selected.add(action.text())
            else:
                all_checked = False
        return set() if all_checked else selected

    def _should_display_with_fields(self, record: dict, filter_fields: dict) -> bool:
        """判断帧是否应在UI中显示（过滤未启用时始终True）"""
        if not self.filter_enabled_chk.isChecked():
            return True

        match = True

        # SNID/NID 过滤
        filter_ids = self._get_filter_ids()
        if filter_ids:
            if self._wrapper_format == "plc2":
                # 南网新一代：按 SNID 过滤
                snid = filter_fields.get("snid")
                match = snid is not None and snid in filter_ids
            else:
                # 国网新一代：按 NID 过滤
                nid = filter_fields.get("nid")
                match = nid is not None and nid in filter_ids

        # 帧类型过滤
        selected_frame_types = self._get_selected_frame_types()
        if selected_frame_types and match:
            ft = filter_fields.get("frame_type", "")
            if ft:
                match = any(t in ft for t in selected_frame_types)
            # 若帧无定界符类型字段（如纯应用层），不作帧类型过滤

        # MSDU类型过滤
        selected_msdu_types = self._get_selected_msdu_types()
        if selected_msdu_types and match:
            msdu_type = filter_fields.get("msdu_type", "")
            if msdu_type:
                match = msdu_type in selected_msdu_types
            # 若帧无MSDU类型字段，不作MSDU过滤

        # 反向过滤
        if self.invert_filter_chk.isChecked():
            return not match
        return match

    def _update_frame_type_btn_text(self):
        """更新帧类型按钮文本（显示已选项数或"全部"）"""
        checked = [a for a in self._frame_type_actions if a.isChecked()]
        if len(checked) == len(self._frame_type_actions):
            self.frame_type_btn.setText("全部")
        elif len(checked) == 0:
            self.frame_type_btn.setText("无")
        elif len(checked) == 1:
            self.frame_type_btn.setText(checked[0].text()[:6])
        else:
            self.frame_type_btn.setText(f"{len(checked)}项")

    def _update_msdu_type_btn_text(self):
        """更新MSDU类型按钮文本（显示已选项数或"全部"）"""
        checked = [a for a in self._msdu_type_actions if a.isChecked()]
        if len(checked) == len(self._msdu_type_actions):
            self.msdu_type_btn.setText("全部")
        elif len(checked) == 0:
            self.msdu_type_btn.setText("无")
        elif len(checked) == 1:
            self.msdu_type_btn.setText(checked[0].text()[:6])
        else:
            self.msdu_type_btn.setText(f"{len(checked)}项")

    # ================================================================
    # 实时 CSV 日志记录
    # ================================================================
    def _on_csv_record_toggled(self, checked: bool):
        """开始/停止CSV记录"""
        if checked:
            self._start_csv_recording()
            self.csv_record_btn.setText("停止记录")
        else:
            self._stop_csv_recording()
            self.csv_record_btn.setText("开始记录")

    def _start_csv_recording(self):
        """开始CSV记录：创建Output目录并打开文件"""
        try:
            os.makedirs("Output", exist_ok=True)
            filename = f"monitor_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self._csv_path = os.path.join("Output", filename)
            self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8-sig")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "序号", "时间", "方向", "长度", "SNID/NID",
                "帧类型", "MSDU类型", "摘要", "原始HEX"
            ])
            self._csv_count = 0
            self.csv_status_label.setText(f"记录中: {filename} (0帧)")
            self.csv_status_label.setStyleSheet("color: #C00000; font-weight: bold;")
            self.csv_path_label.setText(f"路径: {self._csv_path}")
            self.csv_path_label.setStyleSheet("color: #333; font-family: Consolas, monospace; font-size: 11px;")
        except OSError as e:
            QMessageBox.critical(self, "CSV记录失败", f"无法创建日志文件:\n{e}")
            self.csv_record_btn.setChecked(False)

    def _stop_csv_recording(self):
        """停止CSV记录：关闭文件句柄"""
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except OSError:
                pass
            self._csv_file = None
            self._csv_writer = None
            basename = os.path.basename(self._csv_path) if self._csv_path else ""
            self.csv_status_label.setText(f"已停止: {basename} ({self._csv_count}帧)")
            self.csv_status_label.setStyleSheet("color: #888;")
            self.csv_path_label.setText(f"路径: {self._csv_path}")
            self.csv_path_label.setStyleSheet("color: #888; font-family: Consolas, monospace; font-size: 11px;")

    def _open_log_directory(self):
        """打开日志目录"""
        log_dir = os.path.abspath("Output")
        os.makedirs(log_dir, exist_ok=True)
        try:
            os.startfile(log_dir)  # Windows
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", log_dir])  # Linux
        except OSError:
            pass  # 静默忽略

    def _write_csv_record(self, record: dict, filter_fields: dict):
        """写入一条CSV记录（每帧必调用，不受过滤影响）"""
        if self._csv_writer is None:
            return
        net_id = filter_fields.get("snid", filter_fields.get("nid", ""))
        try:
            self._csv_writer.writerow([
                record["seq"], record["time"], record["direction"],
                record["length"], net_id if net_id != "" else "",
                filter_fields.get("frame_type", ""),
                filter_fields.get("msdu_type", ""),
                record["summary"], record["hex"],
            ])
            self._csv_file.flush()
            self._csv_count += 1
            basename = os.path.basename(self._csv_path)
            self.csv_status_label.setText(f"记录中: {basename} ({self._csv_count}帧)")
        except OSError:
            pass  # 文件写入失败时静默忽略，避免阻塞帧接收
