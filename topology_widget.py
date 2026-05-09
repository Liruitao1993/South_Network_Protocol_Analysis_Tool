"""拓扑信息可视化Widget

使用 QGraphicsView + QGraphicsScene 绘制电力线网络拓扑树。
支持南网/国网协议的拓扑数据解析与展示。
可作为独立 Tab 使用，自带串口收发和分帧读取能力。
"""

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsLineItem, QGraphicsTextItem, QGraphicsItem,
    QLabel, QComboBox, QTextEdit, QMessageBox, QCheckBox, QSpinBox, QDoubleSpinBox, QLineEdit, QGroupBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter

from send_frame_lib import ProtocolFrameGenerator
from gdw_send_frame_lib import GDWFrameGenerator
from protocol_parser import ProtocolFrameParser
from gdw10376_parser import GDW10376Parser
from topology_graph import TopologyGraph


@dataclass
class TopoNode:
    """拓扑节点数据模型"""
    address: str = ""              # 12位地址字符串
    tei: int = 0                   # 节点标识 TEI
    proxy_tei: int = -1            # 代理节点标识（父节点）
    level: int = 0                 # 层级 0=CCO
    role: str = "STA"              # CCO / PCO / STA
    phase: str = "-"               # A / B / C / AB / AC / BC / ABC
    channel: str = "-"             # 载波 / 无线
    module_type: str = "-"         # 单载波 / 双模 / 无线
    signal_quality: str = "-"      # 信号质量
    extra: Dict[str, any] = field(default_factory=dict)


class TopoNodeItem(QGraphicsEllipseItem):
    """拓扑图节点图形项"""

    ROLE_COLORS = {
        "CCO": "#FF9800",
        "PCO": "#2196F3",
        "STA": "#4CAF50",
    }
    PHASE_COLORS = {
        "A": "#F44336", "B": "#4CAF50", "C": "#2196F3",
        "AB": "#FF9800", "AC": "#9C27B0", "BC": "#00BCD4",
        "ABC": "#673AB7",
    }
    RADIUS = 18

    def __init__(self, node: TopoNode, x: float, y: float):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2)
        self.node = node
        self.setPos(x, y)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # 颜色：优先按相位，无相位则按角色
        if node.phase != "-" and node.phase in self.PHASE_COLORS:
            base_color = QColor(self.PHASE_COLORS[node.phase])
        else:
            base_color = QColor(self.ROLE_COLORS.get(node.role, "#9E9E9E"))
        self.setBrush(QBrush(base_color))
        self.setPen(QPen(QColor("#333333"), 2))

        # 节点标签：只显示 TEI
        label = str(node.tei)
        self.text_item = QGraphicsTextItem(label, self)
        self.text_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        # 居中
        br = self.text_item.boundingRect()
        self.text_item.setPos(-br.width() / 2, -br.height() / 2)

        # 角色标签（节点下方）
        role_label = QGraphicsTextItem(node.role, self)
        role_label.setFont(QFont("Microsoft YaHei", 9))
        role_label.setDefaultTextColor(QColor("#666666"))
        rbr = role_label.boundingRect()
        role_label.setPos(-rbr.width() / 2, r + 2)

        # 悬停提示
        self.setToolTip(self._build_tooltip())

    def _build_tooltip(self) -> str:
        n = self.node
        lines = [
            f"地址: {n.address}",
            f"TEI: {n.tei}",
            f"角色: {n.role}",
            f"层级: {n.level}",
            f"相位: {n.phase}",
            f"信道: {n.channel}",
            f"模块: {n.module_type}",
        ]
        if n.signal_quality != "-":
            lines.append(f"信号质量: {n.signal_quality}")
        if n.proxy_tei >= 0:
            lines.append(f"代理TEI: {n.proxy_tei}")
        return "\n".join(lines)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("#FF5722"), 3))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor("#333333"), 2))
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击节点弹出详细信息"""
        msg = QMessageBox()
        msg.setWindowTitle(f"节点详情 (TEI={self.node.tei})")
        msg.setStyleSheet(
            "QMessageBox { background-color: #FFFFFF; }"
            "QLabel { color: #000000; font-size: 13px; }"
            "QPushButton { background-color: #F0F0F0; color: #000000; }"
        )
        n = self.node
        detail = (
            f"<b>节点地址:</b> {n.address}<br>"
            f"<b>TEI:</b> {n.tei}<br>"
            f"<b>角色:</b> {n.role}<br>"
            f"<b>层级:</b> {n.level}<br>"
            f"<b>相位:</b> {n.phase}<br>"
            f"<b>信道:</b> {n.channel}<br>"
            f"<b>模块类型:</b> {n.module_type}<br>"
        )
        if n.signal_quality != "-":
            detail += f"<b>信号质量:</b> {n.signal_quality}<br>"
        if n.proxy_tei >= 0:
            detail += f"<b>代理TEI:</b> {n.proxy_tei}"
        msg.setText(detail)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        super().mouseDoubleClickEvent(event)


class TopologyGraphicsView(QGraphicsView):
    """拓扑图主视图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background-color: #FAFAFA; border: 1px solid #cccccc;")
        self._node_items: Dict[int, TopoNodeItem] = {}
        self._highlighted_tei: Optional[int] = None

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        self.scale(factor, factor)

    def clear(self):
        self._scene.clear()
        self._node_items.clear()
        self._highlighted_tei = None

    def build_tree(self, nodes: Dict[int, TopoNode]):
        """根据节点字典构建拓扑树"""
        self._scene.clear()
        if not nodes:
            self._draw_empty_hint()
            return

        # 查找根节点（CCO 或 level=0 或 proxy_tei 不在字典中）
        root = None
        for n in nodes.values():
            if n.role == "CCO" or n.level == 0:
                root = n
                break
        if not root:
            # 如果没有CCO，找proxy_tei不在字典中或proxy_tei=-1的节点
            for n in nodes.values():
                if n.proxy_tei not in nodes or n.proxy_tei == -1 or n.proxy_tei == n.tei:
                    root = n
                    break
        if not root:
            root = next(iter(nodes.values()))

        # 构建父子关系
        children: Dict[int, List[int]] = {tei: [] for tei in nodes}
        orphans: List[int] = []  # proxy_tei 不在 nodes 中的节点
        for n in nodes.values():
            if n.tei == n.proxy_tei:
                continue
            if n.proxy_tei in children:
                children[n.proxy_tei].append(n.tei)
            else:
                orphans.append(n.tei)

        # 孤儿节点挂到根节点下，确保能被绘制
        if orphans:
            children[root.tei].extend(orphans)

        # 递归布局
        positions: Dict[int, Tuple[float, float]] = {}
        self._layout_subtree(root.tei, children, positions, 0)

        # 处理仍不在 positions 中的节点（如多个独立根节点），
        # 将它们作为根节点的额外子节点补充布局
        missing = [tei for tei in nodes if tei not in positions]
        if missing:
            # 将缺失节点追加到根的子列表，重新布局
            for tei in missing:
                if tei not in children[root.tei]:
                    children[root.tei].append(tei)
            positions.clear()
            self._layout_subtree(root.tei, children, positions, 0)

        # 归一化到左上角 + 边距
        self._normalize_positions(positions)

        # 绘制边（先画线，避免覆盖节点）
        # 根据子节点信道类型区分连线样式：载波=蓝色实线，无线=橙色虚线，未知=灰色虚线
        for parent_tei, child_teis in children.items():
            if parent_tei not in positions:
                continue
            px, py = positions[parent_tei]
            for child_tei in child_teis:
                if child_tei not in positions:
                    continue
                cx, cy = positions[child_tei]
                child_node = nodes[child_tei]
                if child_node.channel == "无线":
                    pen = QPen(QColor("#FF5722"), 2.5)
                    pen.setStyle(Qt.PenStyle.DashLine)
                elif child_node.channel == "载波":
                    pen = QPen(QColor("#2196F3"), 2.5)
                    pen.setStyle(Qt.PenStyle.SolidLine)
                else:
                    pen = QPen(QColor("#999999"), 1.5)
                    pen.setStyle(Qt.PenStyle.DashLine)
                line = QGraphicsLineItem(px, py + TopoNodeItem.RADIUS, cx, cy - TopoNodeItem.RADIUS)
                line.setPen(pen)
                self._scene.addItem(line)

        # 绘制节点
        self._node_items.clear()
        for tei, pos in positions.items():
            node = nodes[tei]
            item = TopoNodeItem(node, pos[0], pos[1])
            self._scene.addItem(item)
            self._node_items[tei] = item

        # 恢复高亮状态（如果重建后仍有匹配的节点）
        if self._highlighted_tei is not None and self._highlighted_tei in self._node_items:
            self._apply_highlight(self._highlighted_tei)

        # 调整场景大小
        rect = self._scene.itemsBoundingRect()
        self._scene.setSceneRect(rect.adjusted(-80, -80, 80, 80))

    def _layout_subtree(self, tei: int, children: Dict[int, List[int]],
                        positions: Dict[int, Tuple[float, float]], depth: int,
                        x_offset: float = 0) -> float:
        """递归布局子树，返回该子树的宽度（以节点间距为单位）"""
        H_SPACING = 70
        V_SPACING = 100

        child_teis = [c for c in children.get(tei, []) if c != tei and c not in positions]
        if not child_teis:
            # 叶子节点
            positions[tei] = (x_offset, depth * V_SPACING)
            return 1.0

        # 先布局所有子节点，依次向右排列
        total_width = 0.0
        for child in child_teis:
            w = self._layout_subtree(child, children, positions, depth + 1,
                                     x_offset + total_width * H_SPACING)
            total_width += w

        # 父节点 X 坐标 = 第一个子节点到最后一个子节点的中点
        first_child_x = positions[child_teis[0]][0]
        last_child_x = positions[child_teis[-1]][0]
        parent_x = (first_child_x + last_child_x) / 2
        parent_y = depth * V_SPACING
        positions[tei] = (parent_x, parent_y)
        return total_width if total_width > 0 else 1.0

    def _normalize_positions(self, positions: Dict[int, Tuple[float, float]]):
        if not positions:
            return
        xs = [p[0] for p in positions.values()]
        ys = [p[1] for p in positions.values()]
        min_x, min_y = min(xs), min(ys)
        offset_x = 80 - min_x
        offset_y = 60 - min_y
        for k in positions:
            positions[k] = (positions[k][0] + offset_x, positions[k][1] + offset_y)

    def _draw_empty_hint(self):
        text = QGraphicsTextItem("暂无拓扑数据\n请点击「查询拓扑」按钮获取")
        text.setFont(QFont("Microsoft YaHei", 14))
        text.setDefaultTextColor(QColor("#999999"))
        br = text.boundingRect()
        text.setPos(-br.width() / 2 + 150, -br.height() / 2 + 150)
        self._scene.addItem(text)
        self._scene.setSceneRect(0, 0, 300, 300)

    def _apply_highlight(self, tei: int):
        """将指定节点设为高亮（红色边框）并取消其他节点高亮"""
        for t, item in self._node_items.items():
            if t == tei:
                item.setPen(QPen(QColor("#FF0000"), 4))
            else:
                item.setPen(QPen(QColor("#333333"), 2))
        self._highlighted_tei = tei

    def clear_highlight(self):
        """清除所有节点高亮"""
        for item in self._node_items.values():
            item.setPen(QPen(QColor("#333333"), 2))
        self._highlighted_tei = None

    def focus_on_node(self, tei: int):
        """将视图中心移动到指定节点"""
        item = self._node_items.get(tei)
        if item:
            self.centerOn(item)
            self.ensureVisible(item, 50, 50)

    def search_nodes(self, tei_kw: str, addr_kw: str, role_kw: str) -> List[int]:
        """按字段搜索节点，返回匹配的 TEI 列表（各字段为 AND 关系）"""
        tei_kw = tei_kw.strip().lower()
        addr_kw = addr_kw.strip().lower()
        role_kw = role_kw.strip().lower()
        matches = []
        for tei, item in self._node_items.items():
            node = item.node
            if tei_kw and str(node.tei).lower() != tei_kw:
                continue
            if addr_kw and addr_kw not in node.address.lower():
                continue
            if role_kw and role_kw not in node.role.lower():
                continue
            matches.append(tei)
        return matches


class TopologyWidget(QWidget):
    """拓扑信息页面Widget（可独立作为Tab）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes: Dict[int, TopoNode] = {}
        self.protocol_mode = "south"
        self.serial_worker = None
        self.generator = ProtocolFrameGenerator()
        self.gdw_generator = GDWFrameGenerator()
        self.parser = ProtocolFrameParser()
        self.gdw_parser = GDW10376Parser()

        # 分帧读取状态
        self._pending_query = False
        self._total_nodes = 0
        self._next_start = 0
        self._gdw_start_seq = 1
        self._gdw_fn = 21        # 默认 F21（单模），也支持 F20（双模）

        # networkx 拓扑图存储
        self.topo_graph = TopologyGraph()

        # 自动刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)

        # 组网计时状态
        self._formation_start_time: Optional[float] = None
        self._formation_node_count: Optional[int] = None
        self._formation_done = False
        self._formation_elapsed_seconds: Optional[float] = None

        # 组网完成判定模式: "ratio"(成功率) 或 "count"(数量)
        self._formation_mode: str = "ratio"
        self._formation_ratio_threshold: float = 0.98
        self._formation_count_threshold: Optional[int] = None

        # 节点搜索状态
        self._search_results: List[int] = []
        self._search_index = 0
        self._search_key: Optional[Tuple[str, str, str]] = None

        self.setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(6, 6, 6, 6)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.query_btn = QPushButton("查询拓扑")
        self.query_btn.clicked.connect(self._on_query)
        toolbar.addWidget(self.query_btn)

        self.clear_btn = QPushButton("清除拓扑")
        self.clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(self.clear_btn)

        toolbar.addWidget(QLabel("显示层级:"))
        self.level_filter = QComboBox()
        self.level_filter.addItem("全部", -1)
        for i in range(8):
            self.level_filter.addItem(f"第{i}层", i)
        self.level_filter.currentIndexChanged.connect(self._on_level_filter_changed)
        toolbar.addWidget(self.level_filter)

        toolbar.addWidget(QLabel("国网模式:"))
        self.gdw_mode_combo = QComboBox()
        self.gdw_mode_combo.addItem("单模(F21)", 21)
        self.gdw_mode_combo.addItem("双模(F20)", 20)
        toolbar.addWidget(self.gdw_mode_combo)

        self.export_btn = QPushButton("导出拓扑(JSON)")
        self.export_btn.clicked.connect(self._on_export)
        toolbar.addWidget(self.export_btn)

        toolbar.addStretch()

        # 自动刷新
        self.auto_refresh_cb = QCheckBox("自动刷新")
        self.auto_refresh_cb.stateChanged.connect(self._on_auto_refresh_changed)
        toolbar.addWidget(self.auto_refresh_cb)

        toolbar.addWidget(QLabel("间隔(秒):"))
        self.refresh_interval_sb = QSpinBox()
        self.refresh_interval_sb.setRange(3, 600)
        self.refresh_interval_sb.setValue(10)
        self.refresh_interval_sb.setFixedWidth(60)
        toolbar.addWidget(self.refresh_interval_sb)

        toolbar.addWidget(QLabel("组网模式:"))
        self.formation_mode_combo = QComboBox()
        self.formation_mode_combo.addItem("成功率", "ratio")
        self.formation_mode_combo.addItem("数量", "count")
        self.formation_mode_combo.currentIndexChanged.connect(self._on_formation_mode_changed)
        toolbar.addWidget(self.formation_mode_combo)

        self.formation_ratio_sb = QDoubleSpinBox()
        self.formation_ratio_sb.setRange(1, 100)
        self.formation_ratio_sb.setValue(98)
        self.formation_ratio_sb.setSuffix("%")
        self.formation_ratio_sb.setDecimals(0)
        self.formation_ratio_sb.setFixedWidth(70)
        toolbar.addWidget(self.formation_ratio_sb)

        self.formation_count_sb = QSpinBox()
        self.formation_count_sb.setRange(1, 10000)
        self.formation_count_sb.setValue(100)
        self.formation_count_sb.setFixedWidth(70)
        self.formation_count_sb.setVisible(False)
        toolbar.addWidget(self.formation_count_sb)

        layout.addLayout(toolbar)

        # 搜索栏（第二行）
        search_bar = QHBoxLayout()
        search_bar.setSpacing(6)

        search_group = QGroupBox("节点搜索")
        search_group_layout = QHBoxLayout(search_group)
        search_group_layout.setSpacing(6)
        search_group_layout.setContentsMargins(6, 4, 6, 4)

        search_group_layout.addWidget(QLabel("TEI:"))
        self.search_tei = QLineEdit()
        self.search_tei.setPlaceholderText("TEI")
        self.search_tei.setFixedWidth(70)
        self.search_tei.returnPressed.connect(self._on_search_node)
        search_group_layout.addWidget(self.search_tei)

        search_group_layout.addWidget(QLabel("地址:"))
        self.search_addr = QLineEdit()
        self.search_addr.setPlaceholderText("节点地址")
        self.search_addr.setFixedWidth(100)
        self.search_addr.returnPressed.connect(self._on_search_node)
        search_group_layout.addWidget(self.search_addr)

        search_group_layout.addWidget(QLabel("角色:"))
        self.search_role = QLineEdit()
        self.search_role.setPlaceholderText("CCO/PCO/STA")
        self.search_role.setFixedWidth(70)
        self.search_role.returnPressed.connect(self._on_search_node)
        search_group_layout.addWidget(self.search_role)

        self.search_btn = QPushButton("定位")
        self.search_btn.clicked.connect(self._on_search_node)
        search_group_layout.addWidget(self.search_btn)

        self.clear_search_btn = QPushButton("清除")
        self.clear_search_btn.clicked.connect(self._on_clear_search)
        search_group_layout.addWidget(self.clear_search_btn)

        search_group_layout.addStretch()
        search_bar.addWidget(search_group)
        layout.addLayout(search_bar)

        # 图例说明
        legend = QHBoxLayout()
        legend.addWidget(QLabel("图例:"))
        for label, color in [("CCO", "#FF9800"), ("PCO", "#2196F3"), ("STA", "#4CAF50"),
                             ("A相", "#F44336"), ("B相", "#4CAF50"), ("C相", "#2196F3")]:
            dot = QLabel(f"● {label}")
            dot.setStyleSheet(f"color: {color}; font-weight: bold;")
            legend.addWidget(dot)
        # 信道线条标识
        plc_line = QLabel("— 载波")
        plc_line.setStyleSheet("color: #2196F3; font-weight: bold;")
        legend.addWidget(plc_line)
        rf_line = QLabel("- - 无线")
        rf_line.setStyleSheet("color: #FF5722; font-weight: bold;")
        legend.addWidget(rf_line)
        legend.addStretch()
        layout.addLayout(legend)

        # 拓扑图
        self.view = TopologyGraphicsView()
        layout.addWidget(self.view, 1)

        # 统计信息
        self.stats_label = QLabel("节点总数: 0 | CCO: 0 | PCO: 0 | STA: 0")
        self.stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.stats_label)

        self.formation_label = QLabel("组网状态: 未开始")
        self.formation_label.setStyleSheet("color: #2196F3; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.formation_label)

        # 日志
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(80)
        self.log_edit.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_edit)

    # ------------------------------------------------------------------
    # Serial worker
    # ------------------------------------------------------------------
    def set_serial_worker(self, worker):
        """设置串口工作线程实例"""
        self.serial_worker = worker
        if worker:
            worker.frame_received.connect(self._on_frame_received)
            worker.connection_changed.connect(self._update_button_state)

    def _update_button_state(self, connected: bool):
        self.query_btn.setEnabled(connected)

    # ------------------------------------------------------------------
    # Protocol mode
    # ------------------------------------------------------------------
    def set_protocol_mode(self, mode: str):
        self.protocol_mode = mode
        self.gdw_mode_combo.setVisible(mode == "gdw")

    # ------------------------------------------------------------------
    # Frame helpers
    # ------------------------------------------------------------------
    def _build_south_frame(self, di_key: Tuple[int, int, int, int], field_values: Dict[str, Any]) -> bytes:
        src = bytes.fromhex("000000000000")
        dst = bytes.fromhex("000000000000")
        return self.generator.generate_frame(
            di_key, field_values,
            src_addr=src, dst_addr=dst,
            dir_flag=0, prm=1, add_flag=0
        )

    def _build_gdw_frame(self, afn: int, fn: int, field_values: Dict[str, Any]) -> bytes:
        info_config = {
            "dir": 0, "prm": 1, "报文序列号": 0,
            "通信模块标识": 0, "中继级别": 0,
            "路由标识": 0, "附属节点标识": 0,
            "冲突检测": 0, "纠错编码标识": 0,
            "信道标识": 0, "预计应答字节数": 0,
            "通信速率": 0, "速率单位标识": 0,
        }
        return self.gdw_generator.generate_frame(
            afn, fn, field_values, info_config,
            src_addr="000000000000",
            dst_addr="000000000000"
        )

    def _send_hex(self, hex_str: str, cmd_name: str):
        if not self.serial_worker:
            QMessageBox.warning(self, "警告", "串口未连接！")
            return
        self.serial_worker.send_hex_string(hex_str)
        self._log(f"[发送] {cmd_name}: {hex_str}")

    # ------------------------------------------------------------------
    # Auto refresh
    # ------------------------------------------------------------------
    def _on_auto_refresh_changed(self, state: int):
        if state == Qt.CheckState.Checked.value:
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()

    def _start_auto_refresh(self):
        # 同步 UI 上的组网判定设置
        self._formation_mode = self.formation_mode_combo.currentData()
        self._formation_ratio_threshold = self.formation_ratio_sb.value() / 100.0
        self._formation_count_threshold = self.formation_count_sb.value()

        # 重置组网计时
        self._formation_start_time = time.time()
        self._formation_node_count = None
        self._formation_done = False
        self._formation_elapsed_seconds = None

        interval_ms = self.refresh_interval_sb.value() * 1000
        self._refresh_timer.start(interval_ms)
        self._log(f"[自动刷新] 已启动，间隔 {self.refresh_interval_sb.value()} 秒")

        # 立即查询一次从节点数量（用于组网完成判定）
        if self.protocol_mode == "south":
            frame = self._build_south_frame((0xE8, 0x00, 0x03, 0x05), {})
        else:
            frame = self._build_gdw_frame(0x10, 1, {})
        self._send_hex(frame.hex().upper(), "查询从节点数量(组网计时)")

    def _stop_auto_refresh(self):
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
            self._log("[自动刷新] 已停止")
        # 停止后清理组网计时状态，防止手动查询误用
        self._formation_start_time = None
        self._formation_node_count = None
        self._formation_done = False
        self._formation_elapsed_seconds = None
        self._update_formation_ui()

    def _on_formation_mode_changed(self, index: int):
        """切换组网判定模式时显示/隐藏对应的输入框"""
        mode = self.formation_mode_combo.currentData()
        is_ratio = mode == "ratio"
        self.formation_ratio_sb.setVisible(is_ratio)
        self.formation_count_sb.setVisible(not is_ratio)

    def _check_formation_complete(self):
        """检查是否组网完成（按成功率或按数量）"""
        if self._formation_done:
            return
        if self._formation_node_count is None:
            return
        if self._formation_node_count == 0:
            self._log("[组网] CCO 上报从节点总数为 0，跳过完成判定")
            return
        # 拓扑节点总数减去 1 个 CCO 即为从节点数
        sta_count = max(0, len(self.nodes) - 1)

        if self._formation_mode == "count":
            target = self._formation_count_threshold
            if target is None or target <= 0:
                return
            if sta_count >= target:
                start_time = self._formation_start_time
                if start_time is not None:
                    self._formation_done = True
                    self._formation_elapsed_seconds = time.time() - start_time
                    self._update_formation_ui()
                    self._log(
                        f"[组网完成] 拓扑从节点{sta_count} >= 设定数量{target}, "
                        f"耗时 {self._formation_elapsed_seconds:.1f} 秒"
                    )
        else:
            ratio = sta_count / self._formation_node_count
            if ratio >= self._formation_ratio_threshold:
                start_time = self._formation_start_time
                if start_time is not None:
                    self._formation_done = True
                    self._formation_elapsed_seconds = time.time() - start_time
                    self._update_formation_ui()
                    self._log(
                        f"[组网完成] 拓扑从节点{sta_count} / CCO总数{self._formation_node_count} = "
                        f"{ratio * 100:.1f}%, 耗时 {self._formation_elapsed_seconds:.1f} 秒"
                    )

    def _update_formation_ui(self):
        """更新组网状态标签，同时显示 CCO 从节点总数"""
        total_str = f"CCO从节点总数: {self._formation_node_count}" if self._formation_node_count is not None else "CCO从节点总数: --"
        if self._formation_done and self._formation_elapsed_seconds is not None:
            text = f"组网状态: 完成 | 耗时: {self._formation_elapsed_seconds:.1f} 秒 | {total_str}"
        elif self._formation_start_time is not None:
            elapsed = time.time() - self._formation_start_time
            text = f"组网状态: 进行中 | 已耗时: {elapsed:.1f} 秒 | {total_str}"
        else:
            text = f"组网状态: 未开始 | {total_str}"
        self.formation_label.setText(text)

    def _on_search_node(self):
        """搜索节点并定位高亮（支持 TEI / 地址 / 角色 多字段联合过滤）"""
        tei_kw = self.search_tei.text().strip()
        addr_kw = self.search_addr.text().strip()
        role_kw = self.search_role.text().strip()

        if not tei_kw and not addr_kw and not role_kw:
            return

        matches = self.view.search_nodes(tei_kw, addr_kw, role_kw)
        if not matches:
            filters = []
            if tei_kw:
                filters.append(f"TEI={tei_kw}")
            if addr_kw:
                filters.append(f"地址={addr_kw}")
            if role_kw:
                filters.append(f"角色={role_kw}")
            QMessageBox.information(self, "搜索", f"未找到匹配的节点: {' | '.join(filters)}")
            self._log(f"[搜索] 未找到匹配: {' | '.join(filters)}")
            return

        # 如果搜索条件变化则重置索引
        new_key = (tei_kw, addr_kw, role_kw)
        old_key = getattr(self, '_search_key', None)
        if new_key != old_key:
            self._search_results = matches
            self._search_index = 0
            self._search_key = new_key
        else:
            self._search_index = (self._search_index + 1) % len(self._search_results)

        tei = self._search_results[self._search_index]
        self.view._apply_highlight(tei)
        self.view.focus_on_node(tei)
        self._log(
            f"[搜索] 定位到 TEI={tei} ({self._search_index + 1}/{len(self._search_results)})"
        )

    def _on_clear_search(self):
        """清除搜索状态和高亮"""
        self.search_tei.clear()
        self.search_addr.clear()
        self.search_role.clear()
        self._search_results.clear()
        self._search_index = 0
        self._search_key = None
        self.view.clear_highlight()
        self._log("[搜索] 已清除")

    def _on_refresh_timeout(self):
        if self._pending_query:
            return
        if not self.serial_worker or not self.serial_worker.is_open():
            return
        self._on_query()
        self._update_formation_ui()

    # ------------------------------------------------------------------
    # Query & pagination
    # ------------------------------------------------------------------
    def _on_query(self):
        # 如果不是自动刷新模式，重置组网状态防止手动查询污染计时
        if not self._refresh_timer.isActive():
            self._formation_start_time = None
            self._formation_node_count = None
            self._formation_done = False
            self._formation_elapsed_seconds = None
            self._update_formation_ui()
        self.nodes.clear()
        self._pending_query = True
        self._total_nodes = 0

        if self.protocol_mode == "south":
            self._next_start = 0
            self._query_south_page()
        else:
            self._gdw_fn = self.gdw_mode_combo.currentData()
            self._gdw_start_seq = 1
            self._query_gdw_page()

    def _query_south_page(self):
        frame = self._build_south_frame(
            (0xE8, 0x03, 0x03, 0x65),
            {"节点起始序号": self._next_start, "节点数量": 50}
        )
        self._send_hex(frame.hex().upper(), f"查询网络拓扑(start={self._next_start})")

    def _query_gdw_page(self):
        frame = self._build_gdw_frame(
            0x10, self._gdw_fn,
            {"节点起始序号": self._gdw_start_seq, "节点数量": 50}
        )
        self._send_hex(frame.hex().upper(), f"查询网络拓扑(F{self._gdw_fn}, start={self._gdw_start_seq})")

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------
    def _on_frame_received(self, frame: bytes):
        if not frame:
            return
        self._log(f"[原始帧] {frame.hex().upper()}")
        if self.protocol_mode == "south":
            self._handle_south_response(frame)
        else:
            self._handle_gdw_response(frame)

    def _handle_south_response(self, frame: bytes):
        if len(frame) < 8 or frame[0] != 0x68:
            return
        try:
            result = self.parser.parse(frame)
        except Exception:
            return

        user_data = self._extract_south_user_data(frame)
        if not user_data:
            return

        di_info = result.get("用户数据区", {}).get("数据标识", {})
        di_key = (
            di_info.get("DI3", 0),
            di_info.get("DI2", 0),
            di_info.get("DI1", 0),
            di_info.get("DI0", 0)
        )

        # 查询从节点数量响应（组网计时用）
        if di_key == (0xE8, 0x00, 0x03, 0x05):
            if len(user_data) >= 2:
                count = int.from_bytes(user_data[0:2], 'little')
                self._formation_node_count = count
                self._log(f"[组网] CCO 从节点总数: {count}")
            return

        if di_key != (0xE8, 0x04, 0x03, 0x65):
            return

        nodes = self._parse_south_topology(user_data)
        if nodes:
            for n in nodes:
                self.nodes[n.tei] = n
            self.topo_graph.add_nodes(self.nodes)
            self._apply_filter_and_draw()
            self._update_stats()
            self._log(f"[应答] 南网拓扑: 本次{len(nodes)}个节点，累计{len(self.nodes)}个")

            # 检查是否需要继续分页
            if len(user_data) >= 5:
                total = int.from_bytes(user_data[0:2], 'little')
                self._total_nodes = total
                start = int.from_bytes(user_data[2:4], 'little')
                count = user_data[4]
                self._next_start = start + count
                if self._pending_query and self._next_start < total:
                    self._query_south_page()
                else:
                    self._pending_query = False
                    self._check_formation_complete()
                    self._log(f"[完成] 南网拓扑查询完成，共{len(self.nodes)}个节点")
        else:
            self._pending_query = False
            self._log("[应答] 南网拓扑: 无有效节点数据")

    def _handle_gdw_response(self, frame: bytes):
        if len(frame) < 13 or frame[0] != 0x68:
            return

        afn, fn = self._extract_gdw_afn_fn(frame)
        # 查询从节点数量响应（组网计时用）
        if afn == 0x10 and fn == 1:
            table_data = self.gdw_parser.parse_to_table(frame)
            for name, raw, parsed, comment, bs, be in table_data:
                if "从节点总数量" in name or "从节点数量" in name:
                    try:
                        self._formation_node_count = int(parsed)
                        self._log(f"[组网] CCO 从节点总数: {parsed}")
                    except (ValueError, TypeError):
                        self._log(f"[组网] 从节点数量解析失败: {parsed!r}")
                    break
            return

        if afn != 0x10 or fn not in (20, 21):
            return

        data_unit = self._extract_gdw_data_unit(frame)
        nodes = self._parse_gdw_topology(data_unit, fn)
        if nodes:
            for n in nodes:
                self.nodes[n.tei] = n
            self.topo_graph.add_nodes(self.nodes)
            self._apply_filter_and_draw()
            self._update_stats()
            self._log(f"[应答] 国网拓扑(F{fn}): 本次{len(nodes)}个节点，累计{len(self.nodes)}个")

            # 检查是否需要继续分页
            if len(data_unit) >= 5:
                total = int.from_bytes(data_unit[0:2], 'little')
                self._total_nodes = total
                start = int.from_bytes(data_unit[2:4], 'little')
                count = data_unit[4]
                self._gdw_start_seq = start + count
                if self._pending_query and self._gdw_start_seq <= total:
                    self._query_gdw_page()
                else:
                    self._pending_query = False
                    self._check_formation_complete()
                    self._log(f"[完成] 国网拓扑查询完成，共{len(self.nodes)}个节点")
        else:
            self._pending_query = False
            self._log("[应答] 国网拓扑: 无有效节点数据")

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_south_user_data(frame: bytes) -> bytes:
        if len(frame) < 8 or frame[0] != 0x68:
            return b""
        length = int.from_bytes(frame[1:3], 'little')
        user_data_len = length - 6
        return frame[4:4 + user_data_len]

    @staticmethod
    def _extract_gdw_afn_fn(frame: bytes) -> Tuple[Optional[int], Optional[int]]:
        """从国网帧中直接提取 AFN 和 FN"""
        if len(frame) < 13 or frame[0] != 0x68:
            return None, None
        comm_module_flag = (frame[4] >> 2) & 0x01
        relay_level = (frame[4] >> 4) & 0x0F
        if comm_module_flag:
            addr_len = 12 + 6 * relay_level
        else:
            addr_len = 0
        afn_pos = 4 + 6 + addr_len
        if afn_pos + 3 > len(frame) - 2:
            return None, None
        afn = frame[afn_pos]
        dt1 = frame[afn_pos + 1]
        dt2 = frame[afn_pos + 2]
        fn = None
        for i in range(8):
            if dt1 & (1 << i):
                fn = dt2 * 8 + i + 1
                break
        return afn, fn

    @staticmethod
    def _extract_gdw_data_unit(frame: bytes) -> bytes:
        """从国网帧中提取数据单元"""
        if len(frame) < 13 or frame[0] != 0x68:
            return b""
        length = frame[1] + frame[2] * 256
        comm_module_flag = (frame[4] >> 2) & 0x01
        relay_level = (frame[4] >> 4) & 0x0F
        if comm_module_flag:
            addr_len = 12 + 6 * relay_level
        else:
            addr_len = 0
        data_start = 4 + 6 + addr_len + 1 + 2  # info + addr + AFN + DT
        # L = 用户数据长度 + 6，所以 CS 在 L-2，16H 在 L-1
        data_end = length - 2
        if data_start >= data_end or data_end > len(frame):
            return b""
        return frame[data_start:data_end]

    @staticmethod
    def _parse_south_topology(user_data: bytes) -> List[TopoNode]:
        """解析南网 E8 04 03 65 网络拓扑响应"""
        if len(user_data) < 5:
            return []
        total = int.from_bytes(user_data[0:2], 'little')
        start = int.from_bytes(user_data[2:4], 'little')
        count = user_data[4]
        nodes = []
        offset = 5
        for i in range(count):
            if offset + 19 > len(user_data):
                break
            addr = user_data[offset:offset + 6][::-1].hex().upper()
            tei = int.from_bytes(user_data[offset + 6:offset + 8], 'little')
            proxy_tei = int.from_bytes(user_data[offset + 8:offset + 10], 'little')
            info_byte = user_data[offset + 18]
            level = info_byte & 0x0F
            role_val = (info_byte >> 4) & 0x07
            role = {1: "STA", 2: "PCO", 4: "CCO"}.get(role_val, "未知")
            channel = "无线" if (info_byte >> 7) & 0x01 else "载波"
            nodes.append(TopoNode(
                address=addr, tei=tei, proxy_tei=proxy_tei,
                level=level, role=role, channel=channel
            ))
            offset += 19
        return nodes

    @staticmethod
    def _parse_gdw_topology(data_unit: bytes, fn: int = 21) -> List[TopoNode]:
        """解析国网 AFN=10 F20/F21 网络拓扑响应

        复用 gdw10376_parser 中的位定义：
        - TEI / proxy 均为 12bit (D0~D11)
        - F20 双模: role=D4~D6, channel=D7, module_type=D12~D15
        - F21 单模: role=D4~D7
        """
        if len(data_unit) < 5:
            return []
        total = int.from_bytes(data_unit[0:2], 'little')
        start = int.from_bytes(data_unit[2:4], 'little')
        count = data_unit[4]
        nodes = []
        offset = 5
        is_dual_mode = (fn == 20)
        for i in range(count):
            if offset + 11 > len(data_unit):
                break
            addr = data_unit[offset:offset + 6][::-1].hex().upper()
            # TEI / proxy 只取低 12bit（与 gdw10376_parser 一致）
            tei = int.from_bytes(data_unit[offset + 6:offset + 8], 'little') & 0x0FFF
            proxy_tei = int.from_bytes(data_unit[offset + 8:offset + 10], 'little') & 0x0FFF
            info_byte = data_unit[offset + 10]
            level = info_byte & 0x0F
            if is_dual_mode:
                role_val = (info_byte >> 4) & 0x07
                channel = "无线" if (info_byte >> 7) & 0x01 else "载波"
                mod_val = (data_unit[offset + 7] >> 4) & 0x0F
                mod_map = {0: "高速载波单模", 1: "高速载波+无线双模", 2: "无线单模"}
                module_type = mod_map.get(mod_val, f"保留({mod_val})")
            else:
                role_val = (info_byte >> 4) & 0x0F
                channel = "-"
                module_type = "-"
            role = {1: "STA", 2: "PCO", 4: "CCO"}.get(role_val, "未知")
            nodes.append(TopoNode(
                address=addr, tei=tei, proxy_tei=proxy_tei,
                level=level, role=role, channel=channel, module_type=module_type
            ))
            offset += 11
        return nodes

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    def _apply_filter_and_draw(self):
        level = self.level_filter.currentData()
        if level < 0:
            filtered = dict(self.nodes)
        else:
            filtered = {tei: n for tei, n in self.nodes.items() if n.level <= level}
        self.view.build_tree(filtered)

    def _update_stats(self):
        total = len(self.nodes)
        cco = sum(1 for n in self.nodes.values() if n.role == "CCO")
        pco = sum(1 for n in self.nodes.values() if n.role == "PCO")
        sta = sum(1 for n in self.nodes.values() if n.role == "STA")
        self.stats_label.setText(f"节点总数: {total} | CCO: {cco} | PCO: {pco} | STA: {sta}")

    def clear_nodes(self):
        self.nodes.clear()
        self.topo_graph.clear()
        self.view.clear()
        self.view._draw_empty_hint()
        self._update_stats()
        self._pending_query = False

    def _on_clear(self):
        self.clear_nodes()

    def _on_export(self):
        import json
        from PySide6.QtWidgets import QFileDialog
        if self.topo_graph.node_count() == 0:
            QMessageBox.information(self, "提示", "当前没有拓扑数据可导出")
            return
        data = self.topo_graph.export_dict()
        path, _ = QFileDialog.getSaveFileName(self, "导出拓扑 JSON", "topology.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log(f"[导出] 拓扑已保存到: {path}")

    def _on_level_filter_changed(self):
        self._apply_filter_and_draw()

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_edit.append(f"[{ts}] {msg}")
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
