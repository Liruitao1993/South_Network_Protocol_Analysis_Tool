# -*- coding: utf-8 -*-
"""
TCP 流量监控器 Widget

基于 scapy 的 TCP 流量捕获 + 流重组 + 应用层协议解析。
支持国网新一代 / 南网新一代协议自动识别与解析。
"""

import time
import csv
import os
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QLineEdit, QSplitter, QMessageBox, QGroupBox, QMenu, QTextEdit,
    QTabWidget, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QGuiApplication
from gui_utils import ZoomableTableWidget

# scapy 可选依赖
try:
    from scapy.all import sniff, IP, TCP, get_if_list, get_if_addr
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


# ── 流重组器 ──────────────────────────────────────────────

class FlowBuffer:
    """
    单方向 TCP 字节流缓冲区，负责切出完整应用帧。

    切帧格式：监控器协议封装（南网新一代 PLC2 监控协议）
      ED + 帧长(2B小端) + 控制域1(1B) + 控制域2(1B) + EF + 数据域 + CS + EE
    帧长 = 数据域长度 + 4
    数据报文(ctrl1=0x00)的数据域前 9 字节是公共头，其后为业务帧。
    """

    SOF = 0xED
    EF = 0xEF
    EE = 0xEE
    MAX_FRAME_LEN = 4096

    def __init__(self):
        self._buf = bytearray()
        self._frames: List[Tuple[float, bytes]] = []  # (时间戳, 业务帧数据)

    def append(self, data: bytes, timestamp: float):
        """追加数据并尝试切帧"""
        self._buf.extend(data)
        self._deframe(timestamp)

    def _deframe(self, timestamp: float):
        """从缓冲区切出监控封装帧，提取业务帧数据"""
        i = 0
        n = len(self._buf)
        while i < n:
            if self._buf[i] != self.SOF:
                i += 1
                continue
            # 至少 6 字节头：ED + 帧长(2) + ctrl1 + ctrl2 + EF
            if i + 6 > n:
                break
            frame_len = self._buf[i + 1] | (self._buf[i + 2] << 8)
            if frame_len < 4 or frame_len > self.MAX_FRAME_LEN:
                i += 1
                continue
            # 总长度 = ED(1) + 帧长字段(2) + [ctrl1+ctrl2+EF+数据域+CS = frame_len] + EE(1)
            total = frame_len + 4
            if i + total > n:
                break
            # 强定界校验
            if self._buf[i + 5] != self.EF or self._buf[i + total - 1] != self.EE:
                i += 1
                continue
            ctrl1 = self._buf[i + 3]
            ctrl2 = self._buf[i + 4]
            data_start = i + 6
            data_len = frame_len - 4
            cs_pos = data_start + data_len

            # 校验和（ED 到数据域末尾的累加 & 0xFF）
            calc_cs = sum(self._buf[i:cs_pos]) & 0xFF
            stored_cs = self._buf[cs_pos]
            cs_ok = (calc_cs == stored_cs)

            # 提取业务帧
            business = b''
            if ctrl1 == 0x00 and ctrl2 in (0x01, 0x02, 0x03) and data_len >= 9:
                # 数据报文：剥 9 字节公共头（信道1 + 时间戳4 + PB数1 + 标志1 + PB长2）
                business = bytes(self._buf[data_start + 9:data_start + data_len])
            elif ctrl1 == 0x00 and ctrl2 == 0x00:
                # 控制报文：无业务帧
                pass
            else:
                # 其他类型：取整个数据域尝试解析
                business = bytes(self._buf[data_start:data_start + data_len])

            if business:
                self._frames.append((timestamp, business))

            i += total
            continue

        # 保留未处理的尾部
        if i > 0:
            del self._buf[:i]

    def pop_frames(self) -> List[Tuple[float, bytes]]:
        """取出所有已切分的帧并清空"""
        frames = self._frames
        self._frames = []
        return frames

    @property
    def pending_bytes(self) -> int:
        return len(self._buf)

class TCPFlow:
    """一条 TCP 流（双向）"""

    def __init__(self, flow_id: int, src_ip: str, src_port: int, dst_ip: str, dst_port: int):
        self.flow_id = flow_id
        self.endpoint_a = (src_ip, src_port)
        self.endpoint_b = (dst_ip, dst_port)
        self.packet_count = 0
        self.byte_count = 0
        self.last_seen = 0.0
        # 两个方向的缓冲区
        self._a_to_b = FlowBuffer()
        self._b_to_a = FlowBuffer()
        # 已切出的帧：(时间戳, 方向(0=a→b/1=b→a), 帧数据)
        self._frames: List[Tuple[float, int, bytes]] = []
        # 原始 TCP segment：(时间戳, 方向, payload bytes)
        self._segments: List[Tuple[float, int, bytes]] = []
        self._new_segment_count = 0  # 自上次取出后的新增段数

    def add_packet(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int,
                   payload: bytes, timestamp: float):
        self.packet_count += 1
        self.byte_count += len(payload)
        self.last_seen = timestamp

        if (src_ip, src_port) == self.endpoint_a and (dst_ip, dst_port) == self.endpoint_b:
            direction = 0
            buf = self._a_to_b
        else:
            direction = 1
            buf = self._b_to_a

        # 存原始 segment
        self._segments.append((timestamp, direction, payload))
        self._new_segment_count += 1

        if payload:
            buf.append(payload, timestamp)
            new_frames = buf.pop_frames()
            for ts, frame in new_frames:
                self._frames.append((ts, direction, frame))

    @property
    def segments(self) -> List[Tuple[float, int, bytes]]:
        """所有原始 TCP segment"""
        return self._segments

    @property
    def new_segment_count(self) -> int:
        return self._new_segment_count

    def reset_new_segment_count(self):
        self._new_segment_count = 0

    def pop_new_frames(self) -> List[Tuple[float, int, bytes]]:
        """取出新帧并清空"""
        frames = self._frames
        self._frames = []
        return frames

    @property
    def total_frames(self) -> int:
        return len(self._frames)

    @property
    def display_key(self) -> str:
        a = f"{self.endpoint_a[0]}:{self.endpoint_a[1]}"
        b = f"{self.endpoint_b[0]}:{self.endpoint_b[1]}"
        return f"{a} ↔ {b}"


class TCPFlowReassembler:
    """TCP 流重组管理器"""

    def __init__(self):
        self._flows: Dict[Tuple, TCPFlow] = {}
        self._flow_list: List[TCPFlow] = []  # 按加入顺序
        self._next_id = 1
        self._new_flows: List[TCPFlow] = []  # 自上次取出后的新流
        self._updated_flow_ids: set = set()  # 自上次取出后有更新的流

    def _normalize_key(self, ip1: str, port1: int, ip2: str, port2: int) -> Tuple:
        """流 key 归一化（按 IP:Port 排序，双向同一条流）"""
        a = (ip1, port1)
        b = (ip2, port2)
        if a > b:
            a, b = b, a
        return (a[0], a[1], b[0], b[1])

    def process_packet(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int,
                       payload: bytes, timestamp: float):
        key = self._normalize_key(src_ip, src_port, dst_ip, dst_port)
        flow = self._flows.get(key)
        if flow is None:
            flow = TCPFlow(self._next_id, key[0], key[1], key[2], key[3])
            self._flows[key] = flow
            self._flow_list.append(flow)
            self._new_flows.append(flow)
            self._next_id += 1

        flow.add_packet(src_ip, src_port, dst_ip, dst_port, payload, timestamp)
        self._updated_flow_ids.add(flow.flow_id)

    def pop_new_flows(self) -> List[TCPFlow]:
        """取出新增流"""
        flows = self._new_flows
        self._new_flows = []
        return flows

    def pop_updated_ids(self) -> set:
        """取出有更新的流 ID 集合"""
        ids = self._updated_flow_ids
        self._updated_flow_ids = set()
        return ids

    def get_flow(self, flow_id: int) -> Optional[TCPFlow]:
        """按 ID 取流"""
        for f in self._flow_list:
            if f.flow_id == flow_id:
                return f
        return None

    @property
    def all_flows(self) -> List[TCPFlow]:
        return list(self._flow_list)

    def clear(self):
        self._flows.clear()
        self._flow_list.clear()
        self._new_flows.clear()
        self._updated_flow_ids.clear()
        self._next_id = 1


# ── 抓包线程 ──────────────────────────────────────────────

class PacketSniffer(QThread):
    """scapy 抓包线程"""

    packet_received = Signal(str, int, str, int, bytes, float)  # src_ip, src_port, dst_ip, dst_port, payload, timestamp
    error_occurred = Signal(str)

    def __init__(self, iface: str, bpf_filter: str = ""):
        super().__init__()
        self._iface = iface
        self._bpf = bpf_filter
        self._running = False

    def run(self):
        if not SCAPY_AVAILABLE:
            self.error_occurred.emit("scapy 未安装，请先 pip install scapy")
            return

        self._running = True
        try:
            # 用 timeout=1 循环抓包，确保 stop() 能在 1 秒内响应
            # 直接 stop_filter 在无流量时会一直阻塞
            while self._running:
                sniff(
                    iface=self._iface if self._iface else None,
                    filter=self._bpf if self._bpf else None,
                    prn=self._handle_packet,
                    store=False,
                    timeout=1,
                )
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _handle_packet(self, pkt):
        if not self._running:
            return
        if IP not in pkt or TCP not in pkt:
            return
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        ts = float(pkt.time)
        self.packet_received.emit(
            ip.src, tcp.sport, ip.dst, tcp.dport, payload, ts
        )

    def stop(self):
        self._running = False


# ── 主 Widget ────────────────────────────────────────────

class TCPMonitorWidget(QWidget):
    """TCP 流量监控器主控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gw_parser = None
        self._csg_parser = None
        self._sniffer: Optional[PacketSniffer] = None
        self._reassembler = TCPFlowReassembler()
        self._current_flow_id: Optional[int] = None
        self._flow_rows: Dict[int, int] = {}  # flow_id -> 表格行号
        self._frame_cache: List[dict] = []  # 当前流的所有帧：{ts, direction, frame, protocol, summary, parsed}
        self._auto_scroll = True  # 应用层帧列表自动滚动
        self._gw_summary_fn = None
        self._csg_summary_fn = None
        # CSV 实时记录
        self._csv_file = None
        self._csv_writer = None
        self._csv_path = ""
        self._csv_count = 0
        # 已加载的历史记录流数据 {flow_id: {frames, ...}}
        self._loaded_flows = None

        self._build_ui()
        self._refresh_interfaces()

        # UI 节流定时器（100ms 批量刷新）
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._flush_ui_updates)
        self._pending_flow_updates = False

    def set_parsers(self, gw_parser, csg_parser, gw_summary_fn=None, csg_summary_fn=None):
        """注入协议解析器和摘要生成函数"""
        self._gw_parser = gw_parser
        self._csg_parser = csg_parser
        self._gw_summary_fn = gw_summary_fn
        self._csg_summary_fn = csg_summary_fn

    # ── UI 构建 ────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        toolbar.addWidget(QLabel("网卡："))
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(200)
        toolbar.addWidget(self.iface_combo)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_interfaces)
        toolbar.addWidget(refresh_btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("过滤："))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("BPF 过滤，如 tcp port 8080 或 host 192.168.1.1")
        self.filter_edit.setToolTip(
            "BPF 过滤语法示例：\n"
            "  tcp port 8080              — 单个端口\n"
            "  host 192.168.1.100        — 单个IP\n"
            "  src host 192.168.1.100    — 源IP\n"
            "  dst host 192.168.1.1      — 目的IP\n"
            "  tcp port 8080 or tcp port 9090  — 多个端口\n"
            "  tcp portrange 8080-8090   — 端口范围\n"
            "  host 192.168.1.100 and tcp port 8080  — IP+端口组合\n"
            "\n"
            "留空 = 抓取所有 TCP 流量"
        )
        toolbar.addWidget(self.filter_edit, 1)

        self.start_btn = QPushButton("开始抓包")
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 14px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.start_btn.clicked.connect(self._toggle_capture)
        toolbar.addWidget(self.start_btn)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_all)
        toolbar.addWidget(clear_btn)

        self.pause_btn = QPushButton("暂停刷新")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self._toggle_pause)
        toolbar.addWidget(self.pause_btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("协议："))
        self.proto_combo = QComboBox()
        self.proto_combo.addItems(["自动识别", "国网新一代", "南网新一代"])
        toolbar.addWidget(self.proto_combo)

        toolbar.addStretch()

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.status_label)

        layout.addLayout(toolbar)

        # 主分割：上 = 流列表，下 = 帧列表 + 解析详情
        main_splitter = QSplitter(Qt.Vertical)

        # 上：TCP 流列表
        flow_group = QGroupBox("TCP 流列表")
        flow_layout = QVBoxLayout(flow_group)
        flow_layout.setContentsMargins(6, 8, 6, 6)

        self.flow_table = ZoomableTableWidget()
        self.flow_table.setColumnCount(6)
        self.flow_table.setHorizontalHeaderLabels(
            ["流ID", "源地址", "目的地址", "包数", "字节数", "最新时间"]
        )
        self.flow_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.flow_table.setSelectionMode(QTableWidget.SingleSelection)
        self.flow_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.flow_table.setAlternatingRowColors(True)
        self.flow_table.verticalHeader().hide()
        hdr = self.flow_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        self.flow_table.setColumnWidth(0, 50)
        self.flow_table.setColumnWidth(3, 60)
        self.flow_table.setColumnWidth(4, 80)
        self.flow_table.setColumnWidth(5, 140)
        f = QFont()
        f.setPointSize(8)
        self.flow_table.setFont(f)
        self.flow_table.verticalHeader().setDefaultSectionSize(20)
        self.flow_table.cellClicked.connect(self._on_flow_selected)
        self._setup_table_copy_menu(self.flow_table)
        flow_layout.addWidget(self.flow_table)

        main_splitter.addWidget(flow_group)

        # 下：帧列表 + 解析详情
        detail_splitter = QSplitter(Qt.Horizontal)

        # 左下：应用层帧列表
        frame_group = QGroupBox("应用层帧")
        frame_layout = QVBoxLayout(frame_group)
        frame_layout.setContentsMargins(6, 8, 6, 6)
        frame_layout.setSpacing(4)

        # 帧列表顶部工具栏：记录/加载/自动滚动
        frame_toolbar = QHBoxLayout()
        frame_toolbar.setSpacing(6)
        self.csv_record_btn = QPushButton("开始记录")
        self.csv_record_btn.setCheckable(True)
        self.csv_record_btn.toggled.connect(self._on_csv_record_toggled)
        self.csv_record_btn.setFixedWidth(80)
        frame_toolbar.addWidget(self.csv_record_btn)

        load_btn = QPushButton("加载记录")
        load_btn.clicked.connect(self._load_csv_recording)
        load_btn.setFixedWidth(80)
        frame_toolbar.addWidget(load_btn)

        self.csv_status_label = QLabel("未记录")
        self.csv_status_label.setStyleSheet("color: #888; font-size: 11px;")
        frame_toolbar.addWidget(self.csv_status_label)

        frame_toolbar.addStretch()
        self.frame_autoscroll_cb = QCheckBox("自动滚动")
        self.frame_autoscroll_cb.setChecked(True)
        self.frame_autoscroll_cb.toggled.connect(self._toggle_frame_autoscroll)
        frame_toolbar.addWidget(self.frame_autoscroll_cb)
        frame_layout.addLayout(frame_toolbar)

        self.frame_table = ZoomableTableWidget()
        self.frame_table.setColumnCount(5)
        self.frame_table.setHorizontalHeaderLabels(
            ["时间", "方向", "长度", "协议", "摘要"]
        )
        self.frame_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.frame_table.setSelectionMode(QTableWidget.SingleSelection)
        self.frame_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.frame_table.setAlternatingRowColors(True)
        self.frame_table.verticalHeader().hide()
        fhdr = self.frame_table.horizontalHeader()
        fhdr.setSectionResizeMode(0, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(1, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(2, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(3, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(4, QHeaderView.Stretch)
        self.frame_table.setColumnWidth(0, 100)
        self.frame_table.setColumnWidth(1, 60)
        self.frame_table.setColumnWidth(2, 60)
        self.frame_table.setColumnWidth(3, 90)
        self.frame_table.setFont(f)
        self.frame_table.verticalHeader().setDefaultSectionSize(20)
        self.frame_table.cellClicked.connect(self._on_frame_selected)
        self._setup_table_copy_menu(self.frame_table)
        frame_layout.addWidget(self.frame_table)

        detail_splitter.addWidget(frame_group)

        # 右下：TabWidget — 原始报文 / 解析结果
        self.detail_tabs = QTabWidget()

        # --- Tab 1: 原始 TCP 报文 ---
        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        raw_layout.setContentsMargins(4, 4, 4, 4)
        raw_layout.setSpacing(4)

        self.segment_table = ZoomableTableWidget()
        self.segment_table.setColumnCount(3)
        self.segment_table.setHorizontalHeaderLabels(["时间", "方向", "长度"])
        self.segment_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.segment_table.setSelectionMode(QTableWidget.SingleSelection)
        self.segment_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.segment_table.setAlternatingRowColors(True)
        self.segment_table.verticalHeader().hide()
        shdr = self.segment_table.horizontalHeader()
        shdr.setSectionResizeMode(0, QHeaderView.Fixed)
        shdr.setSectionResizeMode(1, QHeaderView.Fixed)
        shdr.setSectionResizeMode(2, QHeaderView.Stretch)
        self.segment_table.setColumnWidth(0, 100)
        self.segment_table.setColumnWidth(1, 50)
        self.segment_table.setFont(f)
        self.segment_table.verticalHeader().setDefaultSectionSize(20)
        self.segment_table.cellClicked.connect(self._on_segment_selected)
        self._setup_table_copy_menu(self.segment_table)
        raw_layout.addWidget(self.segment_table, 1)

        self.segment_hex = QTextEdit()
        self.segment_hex.setReadOnly(True)
        self.segment_hex.setMaximumHeight(120)
        self.segment_hex.setFont(QFont("Consolas", 9))
        self.segment_hex.setPlaceholderText("选中 segment 以查看原始字节…")
        raw_layout.addWidget(self.segment_hex)

        self.detail_tabs.addTab(raw_tab, "原始报文")

        # --- Tab 2: 解析结果 ---
        parse_tab = QWidget()
        parse_layout = QVBoxLayout(parse_tab)
        parse_layout.setContentsMargins(4, 4, 4, 4)
        parse_layout.setSpacing(4)

        self.parse_hex = QTextEdit()
        self.parse_hex.setReadOnly(True)
        self.parse_hex.setMaximumHeight(60)
        self.parse_hex.setFont(QFont("Consolas", 9))
        self.parse_hex.setPlaceholderText("选中帧以查看详情…")
        parse_layout.addWidget(self.parse_hex)

        self.parse_table = ZoomableTableWidget()
        self.parse_table.setColumnCount(4)
        self.parse_table.setHorizontalHeaderLabels(
            ["字段", "原始值", "解析值", "说明"]
        )
        phdr = self.parse_table.horizontalHeader()
        phdr.setStretchLastSection(True)
        phdr.setSectionResizeMode(QHeaderView.Interactive)
        self.parse_table.setColumnWidth(0, 140)
        self.parse_table.setColumnWidth(1, 100)
        self.parse_table.setColumnWidth(2, 120)
        self.parse_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.parse_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.parse_table.setAlternatingRowColors(True)
        self.parse_table.verticalHeader().hide()
        self.parse_table.setFont(f)
        self.parse_table.verticalHeader().setDefaultSectionSize(18)
        self._setup_table_copy_menu(self.parse_table)
        parse_layout.addWidget(self.parse_table, 1)

        self.detail_tabs.addTab(parse_tab, "解析结果")

        detail_splitter.addWidget(self.detail_tabs)
        detail_splitter.setSizes([350, 450])

        main_splitter.addWidget(detail_splitter)
        main_splitter.setSizes([180, 400])

        layout.addWidget(main_splitter, 1)

        if not SCAPY_AVAILABLE:
            self.status_label.setText("scapy 未安装，无法抓包")
            self.status_label.setStyleSheet("color: #f44336;")
            self.start_btn.setEnabled(False)

    # ── 网卡管理 ──────────────────────────────────────

    def _refresh_interfaces(self):
        """刷新网卡列表"""
        self.iface_combo.clear()
        if not SCAPY_AVAILABLE:
            return
        try:
            ifaces = get_if_list()
            for iface in ifaces:
                try:
                    addr = get_if_addr(iface)
                except Exception:
                    addr = ""
                display = f"{iface}" + (f" ({addr})" if addr else "")
                self.iface_combo.addItem(display, iface)
            if not ifaces:
                self.status_label.setText("未找到可用网卡")
                self.start_btn.setEnabled(False)
        except Exception as e:
            self.status_label.setText(f"获取网卡失败: {e}")
            self.start_btn.setEnabled(False)

    # ── 抓包控制 ──────────────────────────────────────

    def _toggle_capture(self):
        if self._sniffer and self._sniffer.isRunning():
            self._stop_capture()
        else:
            self._start_capture()

    def _start_capture(self):
        if not SCAPY_AVAILABLE:
            QMessageBox.warning(self, "提示", "scapy 未安装，无法抓包。\n请运行: pip install scapy")
            return

        iface_data = self.iface_combo.currentData()
        if not iface_data:
            QMessageBox.warning(self, "提示", "请选择网卡")
            return

        bpf_filter = self.filter_edit.text().strip()
        if bpf_filter:
            # 确保只抓 TCP（用户输入已有 tcp 开头就不加）
            if not bpf_filter.lower().startswith("tcp"):
                bpf_filter = f"tcp and ({bpf_filter})"
        else:
            bpf_filter = "tcp"

        self._sniffer = PacketSniffer(iface_data, bpf_filter)
        self._sniffer.packet_received.connect(self._on_packet_received)
        self._sniffer.error_occurred.connect(self._on_sniffer_error)
        self._sniffer.finished.connect(self._on_sniffer_finished)
        self._sniffer.start()

        self.start_btn.setText("停止抓包")
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; border-radius: 3px; padding: 4px 14px; }"
            "QPushButton:hover { background-color: #d32f2f; }"
        )
        self.iface_combo.setEnabled(False)
        self.filter_edit.setEnabled(False)
        self.status_label.setText("抓包中…")
        self.status_label.setStyleSheet("color: #4CAF50;")
        self._ui_timer.start()

    def _stop_capture(self):
        if self._sniffer:
            self._sniffer.stop()
            self._sniffer.wait(2000)

    def _on_sniffer_finished(self):
        self.start_btn.setText("开始抓包")
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 3px; padding: 4px 14px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.iface_combo.setEnabled(True)
        self.filter_edit.setEnabled(True)
        self.status_label.setText(f"已停止（共 {len(self._reassembler.all_flows)} 条流）")
        self.status_label.setStyleSheet("color: #888;")
        self._ui_timer.stop()
        self._flush_ui_updates()  # 最后刷一次

    def _toggle_pause(self):
        """暂停/继续 UI 刷新"""
        if self.pause_btn.isChecked():
            self.pause_btn.setText("继续刷新")
            self._ui_timer.stop()
            self.status_label.setText("已暂停刷新")
        else:
            self.pause_btn.setText("暂停刷新")
            if self._sniffer and self._sniffer.isRunning():
                self._ui_timer.start()
                self.status_label.setText("抓包中…")
            else:
                self.status_label.setText("就绪")

    def _toggle_frame_autoscroll(self, checked: bool):
        """应用层帧列表自动滚动开关"""
        self._auto_scroll = checked

    def _on_sniffer_error(self, msg: str):
        msg_lower = msg.lower()
        if "npcap" in msg_lower or "winpcap" in msg_lower or "no available pcap device" in msg_lower:
            QMessageBox.critical(
                self, "抓包错误",
                f"无法抓包：\n{msg}\n\n"
                "请确认：\n"
                "1. 已安装 npcap（https://npcap.com/）\n"
                "2. 安装时勾选了 \"WinPcap API-compatible Mode\"\n"
                "3. 以管理员权限运行本程序"
            )
        elif "filter" in msg_lower or "syntax" in msg_lower:
            QMessageBox.critical(self, "过滤错误", f"过滤表达式语法错误：\n{msg}")
        else:
            QMessageBox.critical(self, "抓包错误", f"抓包失败：\n{msg}")

    # ── 包处理 ────────────────────────────────────────

    def _on_packet_received(self, src_ip, src_port, dst_ip, dst_port, payload, timestamp):
        """抓包线程发来的包（主线程）"""
        self._reassembler.process_packet(src_ip, src_port, dst_ip, dst_port, payload, timestamp)
        self._pending_flow_updates = True

    def _flush_ui_updates(self):
        """批量刷新 UI（节流）"""
        if not self._pending_flow_updates:
            return
        self._pending_flow_updates = False

        # 新增流
        new_flows = self._reassembler.pop_new_flows()
        for flow in new_flows:
            row = self.flow_table.rowCount()
            self.flow_table.insertRow(row)
            self.flow_table.setItem(row, 0, QTableWidgetItem(str(flow.flow_id)))
            self.flow_table.setItem(row, 1, QTableWidgetItem(f"{flow.endpoint_a[0]}:{flow.endpoint_a[1]}"))
            self.flow_table.setItem(row, 2, QTableWidgetItem(f"{flow.endpoint_b[0]}:{flow.endpoint_b[1]}"))
            self.flow_table.setItem(row, 3, QTableWidgetItem(str(flow.packet_count)))
            self.flow_table.setItem(row, 4, QTableWidgetItem(str(flow.byte_count)))
            self.flow_table.setItem(row, 5, QTableWidgetItem(self._fmt_time(flow.last_seen)))
            self._flow_rows[flow.flow_id] = row

        # 更新流统计
        updated_ids = self._reassembler.pop_updated_ids()
        for fid in updated_ids:
            flow = self._reassembler.get_flow(fid)
            if flow and fid in self._flow_rows:
                row = self._flow_rows[fid]
                self.flow_table.setItem(row, 3, QTableWidgetItem(str(flow.packet_count)))
                self.flow_table.setItem(row, 4, QTableWidgetItem(str(flow.byte_count)))
                self.flow_table.setItem(row, 5, QTableWidgetItem(self._fmt_time(flow.last_seen)))

        # 如果当前关注的流有更新，刷新帧列表和 segment 列表
        if self._current_flow_id is not None and self._current_flow_id in updated_ids:
            self._refresh_frame_list(self._current_flow_id)
            # segment 列表增量追加
            flow = self._reassembler.get_flow(self._current_flow_id)
            if flow and flow.new_segment_count > 0:
                segs = flow.segments
                start_idx = len(segs) - flow.new_segment_count
                for i in range(start_idx, len(segs)):
                    ts, direction, payload = segs[i]
                    row = self.segment_table.rowCount()
                    self.segment_table.insertRow(row)
                    self.segment_table.setItem(row, 0, QTableWidgetItem(self._fmt_time(ts)))
                    dir_text = "→" if direction == 0 else "←"
                    self.segment_table.setItem(row, 1, QTableWidgetItem(dir_text))
                    self.segment_table.setItem(row, 2, QTableWidgetItem(str(len(payload))))
                self.segment_table.scrollToBottom()
                flow.reset_new_segment_count()

    # ── 流/帧选择 ─────────────────────────────────────

    def _on_flow_selected(self, row: int, col: int):
        item = self.flow_table.item(row, 0)
        if not item:
            return
        try:
            flow_id = int(item.text())
        except ValueError:
            return
        self._current_flow_id = flow_id
        # 刷新应用帧列表
        self._frame_cache.clear()
        self.frame_table.setRowCount(0)

        # 加载模式：从 _loaded_flows 读
        if self._loaded_flows and flow_id in self._loaded_flows:
            info = self._loaded_flows[flow_id]
            for frame_info in info["frames"]:
                self._frame_cache.append(frame_info)
                r = self.frame_table.rowCount()
                self.frame_table.insertRow(r)
                self.frame_table.setItem(r, 0, QTableWidgetItem(frame_info.get("time_str", "")))
                dir_text = "→" if frame_info["direction"] == 0 else "←"
                self.frame_table.setItem(r, 1, QTableWidgetItem(dir_text))
                self.frame_table.setItem(r, 2, QTableWidgetItem(str(len(frame_info["frame"]))))
                self.frame_table.setItem(r, 3, QTableWidgetItem(frame_info["protocol"]))
                self.frame_table.setItem(r, 4, QTableWidgetItem(frame_info["summary"]))
            # 清空 segment（加载模式无原始 TCP 段）
            self.segment_table.setRowCount(0)
        else:
            # 实时模式
            self._refresh_frame_list(flow_id)
            self._refresh_segment_list(flow_id)

        # 清空解析结果
        self.parse_table.setRowCount(0)
        self.parse_hex.clear()
        self.segment_hex.clear()

    def _refresh_frame_list(self, flow_id: int):
        """刷新当前流的帧列表（增量追加，解析并生成详细摘要）"""
        flow = self._reassembler.get_flow(flow_id)
        if not flow:
            return

        new_frames = flow.pop_new_frames()
        if not new_frames:
            return

        src_addr = f"{flow.endpoint_a[0]}:{flow.endpoint_a[1]}"
        dst_addr = f"{flow.endpoint_b[0]}:{flow.endpoint_b[1]}"

        for ts, direction, frame in new_frames:
            # 解析 + 生成摘要
            proto_name, summary, parsed = self._parse_and_summarize(frame)
            self._frame_cache.append({
                "ts": ts,
                "direction": direction,
                "frame": frame,
                "protocol": proto_name,
                "summary": summary,
                "parsed": parsed,
            })
            row = self.frame_table.rowCount()
            self.frame_table.insertRow(row)
            self.frame_table.setItem(row, 0, QTableWidgetItem(self._fmt_time(ts)))
            dir_text = "→" if direction == 0 else "←"
            self.frame_table.setItem(row, 1, QTableWidgetItem(dir_text))
            self.frame_table.setItem(row, 2, QTableWidgetItem(str(len(frame))))
            self.frame_table.setItem(row, 3, QTableWidgetItem(proto_name))
            self.frame_table.setItem(row, 4, QTableWidgetItem(summary))

            # CSV 记录（全量，所有流）
            if self._csv_writer is not None:
                if direction == 0:
                    s, d = src_addr, dst_addr
                else:
                    s, d = dst_addr, src_addr
                self._write_csv_record(
                    flow_id, ts, direction, s, d,
                    len(frame), proto_name, summary, frame
                )

        # 自动滚动
        if self._auto_scroll and new_frames:
            self.frame_table.scrollToBottom()

    def _refresh_segment_list(self, flow_id: int):
        """刷新当前流的原始 TCP segment 列表"""
        flow = self._reassembler.get_flow(flow_id)
        if not flow:
            return
        segments = flow.segments
        self.segment_table.setRowCount(len(segments))
        for i, (ts, direction, payload) in enumerate(segments):
            self.segment_table.setItem(i, 0, QTableWidgetItem(self._fmt_time(ts)))
            dir_text = "→" if direction == 0 else "←"
            self.segment_table.setItem(i, 1, QTableWidgetItem(dir_text))
            self.segment_table.setItem(i, 2, QTableWidgetItem(str(len(payload))))
        # 滚动到底部
        if segments:
            self.segment_table.scrollToBottom()

    def _on_segment_selected(self, row: int, col: int):
        """选中原始 TCP segment 时显示 hex"""
        if self._current_flow_id is None:
            return
        flow = self._reassembler.get_flow(self._current_flow_id)
        if not flow or row < 0 or row >= len(flow.segments):
            return
        ts, direction, payload = flow.segments[row]
        if payload:
            hex_str = ' '.join(f'{b:02X}' for b in payload)
            self.segment_hex.setText(f"{len(payload)} 字节\n{hex_str}")
        else:
            self.segment_hex.setText("(空 payload，纯 ACK/SYN 等控制段)")

    def _on_frame_selected(self, row: int, col: int):
        if row < 0 or row >= len(self._frame_cache):
            return
        info = self._frame_cache[row]
        frame = info["frame"]
        parsed = info["parsed"]
        # 显示 hex
        hex_str = ' '.join(f'{b:02X}' for b in frame)
        self.parse_hex.setText(f"帧长度: {len(frame)} 字节\n{hex_str}")
        # 用缓存的解析结果填充表格
        self._fill_parse_table(parsed)

    def _parse_and_summarize(self, frame: bytes) -> Tuple[str, str, list]:
        """解析帧并生成摘要，返回 (协议名, 摘要, 解析结果列表)"""
        proto_mode = self.proto_combo.currentIndex()  # 0=自动 1=国网 2=南网
        parser = None
        proto_name = "未知"
        summary_fn = None

        if proto_mode == 1 and self._gw_parser:
            parser = self._gw_parser
            proto_name = "国网新一代"
            summary_fn = self._gw_summary_fn
        elif proto_mode == 2 and self._csg_parser:
            parser = self._csg_parser
            proto_name = "南网新一代"
            summary_fn = self._csg_summary_fn
        else:
            # 自动识别：先试南网（因为 TCP 监控大概率是南网 PLC2），不行试国网
            if self._csg_parser and self._try_parse(self._csg_parser, frame):
                parser = self._csg_parser
                proto_name = "南网新一代"
                summary_fn = self._csg_summary_fn
            elif self._gw_parser and self._try_parse(self._gw_parser, frame):
                parser = self._gw_parser
                proto_name = "国网新一代"
                summary_fn = self._gw_summary_fn

        if not parser:
            return (proto_name, "无法识别协议", [])

        try:
            rows = parser.parse_to_table(frame)
        except Exception as e:
            return (proto_name, f"解析错误: {e}", [])

        # 生成摘要
        if summary_fn:
            try:
                summary = summary_fn(rows)
            except Exception:
                summary = self._fallback_summary(rows)
        else:
            summary = self._fallback_summary(rows)

        return (proto_name, summary, rows)

    def _fallback_summary(self, table_data: list) -> str:
        """无 summary_fn 时的简易摘要"""
        if not table_data:
            return "-"
        # 找几个关键字段
        fields = {item[0]: item for item in table_data}
        parts = []
        if "定界符类型" in fields:
            parts.append(fields["定界符类型"][3])
        if "MSDU类型" in fields:
            parts.append(fields["MSDU类型"][3])
        if "管理消息类型(MMTYPE)" in fields:
            parts.append(fields["管理消息类型(MMTYPE)"][3][:20])
        if "业务标识" in fields:
            parts.append(fields["业务标识"][2][:20])
        return " | ".join(parts) if parts else "-"

    def _fill_parse_table(self, table_data: list):
        """用解析结果填充右侧解析表格"""
        self.parse_table.setRowCount(0)
        if not table_data:
            return
        for i, row_data in enumerate(table_data):
            self.parse_table.insertRow(i)
            field = str(row_data[0])
            raw = str(row_data[1])
            parsed = str(row_data[2])
            desc = str(row_data[3])
            self.parse_table.setItem(i, 0, QTableWidgetItem(field))
            self.parse_table.setItem(i, 1, QTableWidgetItem(raw))
            self.parse_table.setItem(i, 2, QTableWidgetItem(parsed))
            self.parse_table.setItem(i, 3, QTableWidgetItem(desc))

    def _try_parse(self, parser, frame: bytes) -> bool:
        """尝试解析，成功返回 True"""
        try:
            result = parser.parse_to_table(frame)
            return len(result) > 0
        except Exception:
            return False

    # ── CSV 记录与加载 ────────────────────────────────

    def _on_csv_record_toggled(self, checked: bool):
        """开始/停止 CSV 记录"""
        if checked:
            self._start_csv_recording()
            self.csv_record_btn.setText("停止记录")
        else:
            self._stop_csv_recording()
            self.csv_record_btn.setText("开始记录")

    def _start_csv_recording(self):
        """开始 CSV 记录"""
        try:
            os.makedirs("Output", exist_ok=True)
            filename = f"tcp_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self._csv_path = os.path.join("Output", filename)
            self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8-sig")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "流ID", "时间", "方向", "源地址", "目的地址",
                "长度", "协议", "摘要", "原始HEX"
            ])
            self._csv_count = 0
            self.csv_status_label.setText(f"记录中: {filename} (0帧)")
            self.csv_status_label.setStyleSheet("color: #C00000; font-size: 11px; font-weight: bold;")
        except Exception as e:
            QMessageBox.critical(self, "CSV 记录失败", f"无法创建日志文件:\n{e}")
            self.csv_record_btn.setChecked(False)

    def _stop_csv_recording(self):
        """停止 CSV 记录"""
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except Exception:
                pass
            self._csv_file = None
            self._csv_writer = None
            basename = os.path.basename(self._csv_path) if self._csv_path else ""
            self.csv_status_label.setText(f"已停止: {basename} ({self._csv_count}帧)")
            self.csv_status_label.setStyleSheet("color: #888; font-size: 11px;")

    def _write_csv_record(self, flow_id: int, ts: float, direction: int,
                          src_addr: str, dst_addr: str, length: int,
                          proto_name: str, summary: str, frame: bytes):
        """写入一条 CSV 记录"""
        if self._csv_writer is None:
            return
        try:
            time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            dir_str = "→" if direction == 0 else "←"
            hex_str = ' '.join(f'{b:02X}' for b in frame)
            self._csv_writer.writerow([
                flow_id, time_str, dir_str, src_addr, dst_addr,
                length, proto_name, summary, hex_str
            ])
            self._csv_file.flush()
            self._csv_count += 1
            if self._csv_count % 10 == 0:
                basename = os.path.basename(self._csv_path)
                self.csv_status_label.setText(f"记录中: {basename} ({self._csv_count}帧)")
        except Exception:
            pass

    def _load_csv_recording(self):
        """加载历史 CSV 记录"""
        path, _ = QFileDialog.getOpenFileName(
            self, "加载 TCP 监控记录", "", "CSV文件 (*.csv)"
        )
        if not path:
            return

        try:
            # 清空现有数据
            self._clear_all(confirm=False)
            # 停止抓包
            if self._sniffer and self._sniffer.isRunning():
                self._stop_capture()

            flows_map = {}  # flow_id -> (src, dst, packets, bytes, frames list)
            seq = 0

            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    flow_id = int(row.get("流ID", 0))
                    time_str = row.get("时间", "")
                    dir_str = row.get("方向", "→")
                    src_addr = row.get("源地址", "")
                    dst_addr = row.get("目的地址", "")
                    length = int(row.get("长度", 0))
                    proto_name = row.get("协议", "")
                    summary = row.get("摘要", "")
                    hex_str = row.get("原始HEX", "")
                    frame = bytes.fromhex(hex_str.replace(" ", "")) if hex_str else b''
                    direction = 0 if dir_str == "→" else 1

                    # 解析帧（为了填充缓存和摘要）
                    parsed = []
                    if frame and (self._gw_parser or self._csg_parser):
                        try:
                            if self._csg_parser:
                                rows = self._csg_parser.parse_to_table(frame)
                                if rows and not rows[0][0].startswith("❌"):
                                    parsed = rows
                                    proto_name = "南网新一代"
                                    if self._csg_summary_fn:
                                        summary = self._csg_summary_fn(rows)
                            if not parsed and self._gw_parser:
                                rows = self._gw_parser.parse_to_table(frame)
                                if rows and not rows[0][0].startswith("❌"):
                                    parsed = rows
                                    proto_name = "国网新一代"
                                    if self._gw_summary_fn:
                                        summary = self._gw_summary_fn(rows)
                        except Exception:
                            pass

                    # 加入流
                    if flow_id not in flows_map:
                        parts = src_addr.split(":")
                        dst_parts = dst_addr.split(":")
                        flows_map[flow_id] = {
                            "src": src_addr,
                            "dst": dst_addr,
                            "packets": 0,
                            "bytes": 0,
                            "frames": [],
                            "last_time": time_str,
                        }
                    flows_map[flow_id]["packets"] += 1
                    flows_map[flow_id]["bytes"] += length
                    flows_map[flow_id]["last_time"] = time_str
                    flows_map[flow_id]["frames"].append({
                        "ts": 0.0,  # 简化，不做时间戳
                        "time_str": time_str,
                        "direction": direction,
                        "frame": frame,
                        "protocol": proto_name,
                        "summary": summary,
                        "parsed": parsed,
                    })
                    seq += 1

            # 填充流列表
            flow_ids = sorted(flows_map.keys())
            for fid in flow_ids:
                info = flows_map[fid]
                row = self.flow_table.rowCount()
                self.flow_table.insertRow(row)
                self.flow_table.setItem(row, 0, QTableWidgetItem(str(fid)))
                self.flow_table.setItem(row, 1, QTableWidgetItem(info["src"]))
                self.flow_table.setItem(row, 2, QTableWidgetItem(info["dst"]))
                self.flow_table.setItem(row, 3, QTableWidgetItem(str(info["packets"])))
                self.flow_table.setItem(row, 4, QTableWidgetItem(str(info["bytes"])))
                self.flow_table.setItem(row, 5, QTableWidgetItem(info["last_time"]))
                # 存入 reassembler 模拟结构（直接用 widget 侧的 cache）
                self._flow_rows[fid] = row

            # 存帧数据到一个专门的 loaded_flows dict
            self._loaded_flows = flows_map

            self.status_label.setText(f"已加载 {len(flow_ids)} 条流，共 {seq} 帧")
            self.csv_status_label.setText(f"已加载: {os.path.basename(path)}")
            self.csv_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")

        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载 CSV 文件:\n{e}")

    # ── 清空 ──────────────────────────────────────────

    def _clear_all(self, confirm: bool = True):
        if confirm:
            ret = QMessageBox.question(
                self, "确认清空", "确定要清空所有捕获数据吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                return
        self._reassembler.clear()
        self._flow_rows.clear()
        self._frame_cache.clear()
        self._current_flow_id = None
        self._loaded_flows = None
        self.flow_table.setRowCount(0)
        self.frame_table.setRowCount(0)
        self.segment_table.setRowCount(0)
        self.parse_table.setRowCount(0)
        self.parse_hex.clear()
        self.segment_hex.clear()
        if not (self._sniffer and self._sniffer.isRunning()):
            self.status_label.setText("已清空")

    # ── 工具方法 ──────────────────────────────────────

    def _fmt_time(self, ts: float) -> str:
        """格式化时间戳"""
        import datetime
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S.%f")[:-3]

    # ── 表格复制功能 ──────────────────────────────────

    def _setup_table_copy_menu(self, table: QTableWidget):
        """为表格设置右键复制菜单和 Ctrl+C 快捷键"""
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_table_copy_menu(t, pos)
        )
        shortcut = QShortcut(QKeySequence.Copy, table)
        shortcut.setContext(Qt.WidgetShortcut)
        shortcut.activated.connect(lambda t=table: self._copy_table_rows(t, all_rows=False))

    def _show_table_copy_menu(self, table: QTableWidget, pos):
        menu = QMenu(table)
        has_selection = len(table.selectedItems()) > 0

        copy_sel = menu.addAction("复制选中行")
        copy_sel.setEnabled(has_selection)
        copy_sel.triggered.connect(lambda: self._copy_table_rows(table, all_rows=False))

        copy_all = menu.addAction("复制全部")
        copy_all.triggered.connect(lambda: self._copy_table_rows(table, all_rows=True))

        menu.exec(table.mapToGlobal(pos))

    def _copy_table_rows(self, table: QTableWidget, all_rows: bool = False):
        col_count = table.columnCount()
        row_count = table.rowCount()

        if all_rows:
            rows = list(range(row_count))
        else:
            selected = table.selectedIndexes()
            if not selected:
                rows = list(range(row_count))
            else:
                rows = sorted({idx.row() for idx in selected})

        if not rows:
            return

        headers = []
        for c in range(col_count):
            item = table.horizontalHeaderItem(c)
            headers.append(item.text() if item else "")
        lines = ["\t".join(headers)]

        for r in rows:
            cells = []
            for c in range(col_count):
                item = table.item(r, c)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        text = "\n".join(lines)
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
