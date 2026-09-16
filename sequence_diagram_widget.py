"""通信时序图标签页（协议9批量解析结果可视化）

将批量解析结果（batch_results）渲染为类标准序列图：顶部网元节点框 + 纵向
生命线 + 带箭头的消息流，并与批量解析摘要表双向联动。

文件分两层（AGENTS.md §4.1：新增 UI 组件拆分独立文件，纯逻辑层不依赖 Qt）：
  - 纯逻辑层（文件前半，无 Qt，可脚本测试）：
      SequenceNode / SequenceMessage / SequenceModel
      build_sequence_model_csg(batch_results, frame_indices=None)  协议9提取器
      build_sequence_model(batch_results, protocol, ...)           分派入口
  - UI 层（文件后半，PySide6）：
      SequenceDiagramView(QGraphicsView)   缩放/平移/点击
      SequenceDiagramWidget(QWidget)       工具栏 + 画布
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════════
# 纯逻辑层（无 Qt 依赖，可独立脚本测试）
# ══════════════════════════════════════════════════════════════════

CCO_TEI = 1  # 集中器（协调器）TEI 恒为 1
UNASSOC_TEI = 0  # 未入网站点 TEI（关联请求等入网前帧源TEI=0，尚未分配具体TEI）
_DELIM_BEACON = 0  # 定界符类型：信标帧
_DELIM_SACK = 2  # 定界符类型：选择确认帧
_BROADCAST_KEYWORD = "广播"  # 应用层「发送类型」注释中的广播判别关键字
_LABEL_MAX_LEN = 60  # 消息标签摘要截断长度（超出追加省略号）
_BROADCAST_KINDS = ("beacon", "broadcast")  # 真广播消息（标签加[广播]标识）
_DASHED_KINDS = ("beacon", "sack", "broadcast")  # 虚线橙色箭头（控制/广播类）
_SVC_TEST_FRAME = 0xF0  # 业务标识：测试帧（台体发射机初始化过程发送）
_ASSOC_REQ_KEYWORD = "关联请求"
_ASSOC_CNF_KEYWORD = "关联确认"
# 协议9/10/11 解析器字段同构但字段名/缩进有差异：去缩进索引 + 多字段名候选
_DELIM_NAMES = ("定界符类型", "定界符类型(DT)")
_MMTYPE_NAMES = ("管理消息类型(MMTYPE)", "消息类型(MMTYPE)")


@dataclass
class SequenceNode:
    """时序图网元节点（顶部方框 + 纵向生命线）"""

    key: str  # 唯一标识 "TEI:<int>"
    tei: int
    label: str  # 显示名：CCO / STA-XXXX
    role: str  # CCO / STA


@dataclass
class SequenceMessage:
    """时序图消息（生命线之间的箭头）"""

    frame_idx: int  # batch_results 原始索引（点击联动摘要表用）
    src_key: str  # 源节点 key
    dst_key: str | None  # 目的节点 key；None = 广播（信标/SACK/应用层广播）
    label: str  # 显示标签 "#N 摘要(截断)"
    kind: str  # unicast / broadcast / beacon / sack
    summary_full: str  # 完整摘要（tooltip）
    marker: str = ""


@dataclass
class SequenceModel:
    """时序图数据模型"""

    nodes: list = field(default_factory=list)  # list[SequenceNode]
    messages: list = field(default_factory=list)  # list[SequenceMessage]
    skipped: int = 0  # 被跳过的帧数（解析失败 / 无TEI且非信标SACK）
    phases: list = field(default_factory=list)


def _to_int(value):
    """table_data parsed_value 容错转 int（失败返回 None）。

    实测形态为十进制字符串（"1"/"291"），但曾有 0x 前缀字符串导致 int()
    崩溃的教训（main_gui CHANGELOG），故十进制/0x0b 前缀多级兜底。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s, 10)
    except ValueError:
        pass
    try:
        return int(s, 0)  # 兼容 "0x.." / "0b.." 前缀形态
    except ValueError:
        return None


def _make_node(tei: int) -> SequenceNode:
    """按 TEI 建节点：TEI=1 为 CCO，TEI=0 为未入网站点，其余为 STA-XXXX"""
    if tei == CCO_TEI:
        return SequenceNode(key=f"TEI:{tei}", tei=tei, label="CCO", role="CCO")
    if tei == UNASSOC_TEI:
        # 关联请求等入网前帧源TEI=0：节点尚未分配具体TEI，不能标成 STA-0000
        return SequenceNode(
            key=f"TEI:{tei}", tei=tei, label="未入网站点", role="UNASSOC"
        )
    return SequenceNode(key=f"TEI:{tei}", tei=tei, label=f"STA-{tei:04X}", role="STA")


def _truncate(text: str, max_len: int = _LABEL_MAX_LEN) -> str:
    """摘要过长时省略号截断（完整文本由 tooltip 展示）"""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _msg_label(frame_idx: int, kind: str, summary: str) -> str:
    """消息标签：#帧号 + [广播]标识（广播类）+ 截断摘要"""
    tag = "[广播] " if kind in _BROADCAST_KINDS else ""
    return f"#{frame_idx + 1} {tag}{_truncate(summary)}"


def _delim_kind(fields: dict):
    """定界符类型判别（兼容 9/10/11 字段名与注释形态）：信标=0 / SACK=2 / None"""
    for name in _DELIM_NAMES:
        it = fields.get(name)
        if it is None:
            continue
        text = f"{it[2]} {it[3]}"
        if "信标" in text:
            return _DELIM_BEACON
        if "SACK" in text or "选择确认" in text or "ACK帧" in text:
            return _DELIM_SACK
    return None


def _tei_item(fields: dict, kind: str):
    """源/目的 TEI 行查找（FC 级优先，MAC 级原始 TEI 兜底，国网新一代两者并存）"""
    for name in (f"{kind}TEI", f"原始{kind}TEI"):
        it = fields.get(name)
        if it is not None and _to_int(it[2]) is not None:
            return it
    return None


def build_sequence_model_csg(
    batch_results, frame_indices=None, table_data_resolver=None
) -> SequenceModel:
    """协议9/10/11 批量解析结果 → 时序图模型（通用提取管道）。

    三协议解析器字段同构（定界符类型/源TEI/目的TEI/发送类型/MMTYPE），
    仅字段名与缩进差异：统一去缩进索引 + 多字段名候选（_DELIM_NAMES/
    _MMTYPE_NAMES/原始TEI 兜底）。

    提取规则（顺序即优先级）：
      1. _status != "成功" → 跳过（skipped += 1）
      2. 定界符类型=信标(0) → CCO 广播消息（无目的节点）
      3. 定界符类型=SACK(2) → 有向确认：帧内「目的TEI」是箭头所指节点
         （src=源TEI，缺省 CCO；无目的TEI 时退化为广播画法）
      4. 业务标识=0xF0 测试帧 → 源节点为台体发射机（台体初始化过程发送，
         非 CCO 报文）；目的按目的TEI/广播规则
      5. 源TEI+目的TEI → 单播；应用层「发送类型」注释含"广播" → 广播
      6. 既无 TEI 又非信标/SACK/测试帧 → 跳过

    节点规则：key="TEI:<int>"，TEI=1 → CCO；同 TEI 去重；
    CCO 恒最左，其余按消息流中首次出现顺序。

    Args:
        batch_results: MainWindow.batch_results（或其子集），每项含
            _status/_table_data/摘要 等键；ED 监控包装帧的 _table_data
            为「监控包装头行 + 内层业务帧字段」，字段名相同，照常提取。
        frame_indices: 与 batch_results 等长的原始索引列表（勾选子集时
            保持 frame_idx 与 #N 为 batch_results 原始序号）；None 时用
            位置序号（全部帧场景）。
        table_data_resolver: 详情按需解析器 ``(result) -> list``；任务
            09-15-gui-batch-parse-perf 步骤 3 起 ``batch_results`` 不再常驻
            ``_table_data``，未注入时旧行为不变（只读记录自带字段）。
    """
    if frame_indices is not None and len(frame_indices) != len(batch_results):
        raise ValueError("frame_indices 长度必须与 batch_results 一致")

    nodes: list = []
    node_map: dict = {}
    messages: list = []
    skipped = 0
    has_test_frame = False
    req_idxs: list = []
    cnf_idxs: list = []
    cnf_dst = None

    def ensure_node(tei: int) -> SequenceNode:
        node = node_map.get(f"TEI:{tei}")
        if node is None:
            node = _make_node(tei)
            node_map[node.key] = node
            nodes.append(node)
        return node

    for pos, result in enumerate(batch_results):
        frame_idx = frame_indices[pos] if frame_indices is not None else pos

        # 规则1：解析失败/异常帧跳过
        if result.get("_status") != "成功":
            skipped += 1
            continue

        # 详情按需：命中记录自带的 _table_data（兼容旧路径/测试）或交给
        # 注入的 resolver（main_gui._batch_detail_resolver → _get_frame_table_data）
        table_data = result.get("_table_data")
        if table_data is None and table_data_resolver is not None:
            table_data = table_data_resolver(result)
        table_data = table_data or []
        # 字段名 → 行 索引（同 _get_csg_new_gen_summary 的做法）；
        # ED 包装帧的「── PLC2.0 监控包装头 ──」等分段行不会与字段名冲突
        # 去缩进索引（协议10/11 字段名带缩进；首个出现优先：FC 在 MAC/应用层之前）
        fields = {}
        for item in table_data:
            if item and item[0]:
                fields.setdefault(str(item[0]).strip(), item)

        summary = str(result.get("摘要") or "")
        mm_comment = ""
        for mm_name in _MMTYPE_NAMES:
            mm_item = fields.get(mm_name)
            if mm_item is not None:
                mm_comment = str(mm_item[3])
                break

        delim_type = _delim_kind(fields)

        # 规则2：信标 → 广播（广播消息不产生目的节点）；源取信标源TEI，缺省 CCO
        if delim_type == _DELIM_BEACON:
            b_src_item = _tei_item(fields, "源")
            b_src = _to_int(b_src_item[2]) if b_src_item is not None else None
            # 信标源TEI 缺省/为0(协议9信标载荷无有效源TEI)时归 CCO
            src = ensure_node(b_src if b_src not in (None, UNASSOC_TEI) else CCO_TEI)
            messages.append(
                SequenceMessage(
                    frame_idx,
                    src.key,
                    None,
                    _msg_label(frame_idx, "beacon", summary),
                    "beacon",
                    summary,
                )
            )
            continue

        # 规则3：SACK → 有向确认箭头：帧内「目的TEI」即箭头所指节点；
        # 源取源TEI（Bitloading扩展帧携带），缺省 CCO；无目的TEI 退化为广播画法
        if delim_type == _DELIM_SACK:
            sack_src_item = _tei_item(fields, "源")
            sack_src_tei = (
                _to_int(sack_src_item[2]) if sack_src_item is not None else None
            )
            src = ensure_node(sack_src_tei if sack_src_tei is not None else CCO_TEI)
            sack_dst_item = _tei_item(fields, "目的")
            sack_dst_tei = (
                _to_int(sack_dst_item[2]) if sack_dst_item is not None else None
            )
            if sack_dst_tei is not None:
                dst = ensure_node(sack_dst_tei)
                messages.append(
                    SequenceMessage(
                        frame_idx,
                        src.key,
                        dst.key,
                        _msg_label(frame_idx, "sack", summary),
                        "sack",
                        summary,
                    )
                )
            else:
                messages.append(
                    SequenceMessage(
                        frame_idx,
                        src.key,
                        None,
                        _msg_label(frame_idx, "sack", summary),
                        "sack",
                        summary,
                    )
                )
            continue

        # 规则4/5：源节点判别——业务标识=0xF0 测试帧的发送方是台体发射机
        # （台体初始化过程发送，并非 CCO 报文）；其余帧按源TEI
        svc_item = fields.get("业务标识")
        svc_id = _to_int(svc_item[2]) if svc_item is not None else None
        is_test_frame = svc_id == _SVC_TEST_FRAME

        src_item = _tei_item(fields, "源")
        dst_item = _tei_item(fields, "目的")
        src_tei = _to_int(src_item[2]) if src_item is not None else None
        dst_tei = _to_int(dst_item[2]) if dst_item is not None else None
        if is_test_frame:
            src = ensure_node(CCO_TEI)
            has_test_frame = True
        elif src_tei is not None:
            src = ensure_node(src_tei)
        else:
            src = None
        if src is not None and dst_tei is not None:
            send_item = fields.get("发送类型")
            is_broadcast = send_item is not None and _BROADCAST_KEYWORD in str(
                send_item[3]
            )
            if is_broadcast:
                messages.append(
                    SequenceMessage(
                        frame_idx,
                        src.key,
                        None,
                        _msg_label(frame_idx, "broadcast", summary),
                        "broadcast",
                        summary,
                    )
                )
            else:
                dst = ensure_node(dst_tei)
                marker = ""
                if _ASSOC_CNF_KEYWORD in mm_comment:
                    marker = f"入网→STA-{dst_tei:04X}"
                messages.append(
                    SequenceMessage(
                        frame_idx,
                        src.key,
                        dst.key,
                        _msg_label(frame_idx, "unicast", summary),
                        "unicast",
                        summary,
                        marker,
                    )
                )
                if _ASSOC_REQ_KEYWORD in mm_comment:
                    req_idxs.append(len(messages) - 1)
                if marker:
                    cnf_idxs.append(len(messages) - 1)
                    cnf_dst = dst_tei
            continue

        # 规则6：既无 TEI 又非信标/SACK/测试帧 → 跳过
        skipped += 1

    # 节点排序：CCO 恒最左，其余保持首次出现顺序（sort 稳定）
    nodes.sort(key=lambda n: 0 if n.tei == CCO_TEI else 1)
    # 物理实体归并①：台体模拟CCO → CCO 生命线改标注
    if has_test_frame:
        cco = node_map.get(f"TEI:{CCO_TEI}")
        if cco is not None:
            cco.label = "台体发射机(模拟CCO)"
    # 物理实体归并②：未入网站点(TEI=0)归并到关联确认分配的TEI(同一DUT)
    if cnf_dst is not None:
        ok, nk = f"TEI:{UNASSOC_TEI}", f"TEI:{cnf_dst}"
        if ok in node_map and nk in node_map:
            nodes = [n for n in nodes if n.key != ok]
            del node_map[ok]
            node_map[nk].label = f"STA-{cnf_dst:04X} (DUT)"
            for m in messages:
                if m.src_key == ok:
                    m.src_key = nk
                if m.dst_key == ok:
                    m.dst_key = nk
            nodes.sort(key=lambda n: 0 if n.tei == CCO_TEI else 1)
    phases: list = []
    if req_idxs:
        i_req = req_idxs[0]
        if i_req > 0:
            phases.append((0, "阶段① 初始化（信标/测试帧）"))
        phases.append((i_req, "阶段② 关联入网"))
        if cnf_idxs and cnf_idxs[0] + 1 < len(messages):
            phases.append((cnf_idxs[0] + 1, "阶段③ 业务测试"))
    return SequenceModel(nodes=nodes, messages=messages, skipped=skipped, phases=phases)


def build_sequence_model(
    batch_results, protocol: int, frame_indices=None, table_data_resolver=None
):
    """时序图模型分派入口：协议 9/10/11 字段同构，共用通用提取管道；其余返回 None"""
    if protocol in (9, 10, 11):
        return build_sequence_model_csg(
            batch_results,
            frame_indices=frame_indices,
            table_data_resolver=table_data_resolver,
        )
    return None


# ══════════════════════════════════════════════════════════════════
# UI 层（PySide6）
# ══════════════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import QPointF, QRectF, Qt, Signal
    from PySide6.QtGui import (
        QColor,
        QFont,
        QImage,
        QPainter,
        QPalette,
        QPen,
        QPolygonF,
        QTransform,
    )
    from PySide6.QtWidgets import (
        QFileDialog,
        QGraphicsLineItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsTextItem,
        QGraphicsView,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    _QT_AVAILABLE = True
except ImportError:  # 无 Qt 环境下纯逻辑层仍可独立导入/测试
    _QT_AVAILABLE = False


if _QT_AVAILABLE:
    import app_icons

    # ── 布局常量（design.md「布局」）──
    NODE_TOP = 0  # 节点框顶部 y
    NODE_H = 36  # 节点框高
    NODE_SPACING = 360  # 节点水平间距下限（实际由 _build_scene 按标签宽度自适应加宽）
    NODE_MIN_W = 96  # 节点框最小宽
    MSG_FIRST_Y = 96  # 第 0 条消息 y（顶部留阶段①分隔线与标签空间）
    MSG_ROW_H = 48  # 消息行高
    SCENE_BOTTOM_PAD = 40  # 场景底部余量
    _ARROW_LEN = 10  # 箭头三角形长度
    _ARROW_HALF_W = 5  # 箭头三角形半宽

    def _make_arrow_head(x: float, y: float, pointing_left: bool) -> QPolygonF:
        """消息线末端箭头三角形（pointing_left=True 时朝左）"""
        s = 1 if pointing_left else -1  # 底边相对尖端的偏移方向
        return QPolygonF(
            [
                QPointF(x, y),
                QPointF(x + s * _ARROW_LEN, y - _ARROW_HALF_W),
                QPointF(x + s * _ARROW_LEN, y + _ARROW_HALF_W),
            ]
        )

    class SequenceDiagramView(QGraphicsView):
        """时序图画布：Ctrl+滚轮缩放、拖拽平移、点击消息发 message_clicked"""

        message_clicked = Signal(int)

        def __init__(self, scene, parent=None):
            super().__init__(scene, parent)
            self._zoom = 1.0
            self._press_pos = None
            self.setRenderHint(QPainter.Antialiasing)
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        def wheelEvent(self, event):
            # Ctrl+滚轮缩放（与 ZoomableTableWidget 惯例一致）；普通滚轮滚动
            if event.modifiers() & Qt.ControlModifier:
                factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
                self._zoom = max(0.1, min(8.0, self._zoom * factor))
                self.setTransform(QTransform().scale(self._zoom, self._zoom))
                event.accept()
            else:
                super().wheelEvent(event)

        def mousePressEvent(self, event):
            self._press_pos = event.pos()
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event):
            super().mouseReleaseEvent(event)
            # 点击（非拖拽）命中消息 item 时发出 batch_results 原始帧索引；
            # 消息线/箭头/标签均经 setData(0, frame_idx) 存储索引
            if self._press_pos is not None and (
                (event.pos() - self._press_pos).manhattanLength() < 6
            ):
                item = self.itemAt(event.pos())
                while item is not None:
                    idx = item.data(0)
                    if idx is not None:
                        self.message_clicked.emit(int(idx))
                        break
                    item = item.parentItem()
            self._press_pos = None

        def fit_window(self):
            """适应窗口：整图可见并同步缩放系数"""
            scene = self.scene()
            if scene is None or scene.sceneRect().isNull():
                return
            self.fitInView(
                scene.sceneRect().adjusted(-20, -20, 20, 20), Qt.KeepAspectRatio
            )
            self._zoom = self.transform().m11()

    class SequenceDiagramWidget(QWidget):
        """通信时序图标签页：工具栏（刷新/适应窗口/导出PNG/状态）+ 时序图画布"""

        message_clicked = Signal(int)  # 点击消息（frame_idx = batch_results 原始索引）
        refresh_requested = Signal()  # 「刷新」：请求主窗口按当前 batch_results 重建

        def __init__(self, parent=None):
            super().__init__(parent)
            self._model: SequenceModel | None = None
            self._msg_items: dict = {}  # frame_idx -> dict(line/arrow/label/...)
            self._highlight_idx = None
            self._pending_fit = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)

            # ── 工具栏 ──
            toolbar = QHBoxLayout()
            toolbar.setSpacing(6)

            self.refresh_btn = QPushButton("刷新")
            self.refresh_btn.setIcon(app_icons.load_icon("refresh-cw"))
            self.refresh_btn.setToolTip("按当前批量解析结果重新生成时序图")
            self.refresh_btn.clicked.connect(self.refresh_requested)
            toolbar.addWidget(self.refresh_btn)

            self.fit_btn = QPushButton("适应窗口")
            self.fit_btn.setIcon(app_icons.load_icon("maximize-2"))
            self.fit_btn.setToolTip("缩放复位，整图适应当前窗口")
            self.fit_btn.clicked.connect(self.view_fit)
            toolbar.addWidget(self.fit_btn)

            self.export_btn = QPushButton("导出 PNG")
            self.export_btn.setIcon(app_icons.load_icon("image"))
            self.export_btn.setToolTip("将整幅时序图导出为 PNG 图片")
            self.export_btn.clicked.connect(self._on_export_png)
            toolbar.addWidget(self.export_btn)

            hint = QLabel("滚轮滚动 / Ctrl+滚轮缩放 / 拖拽平移 / 点击消息定位到摘要表")
            hint.setStyleSheet("color: #999;")
            toolbar.addWidget(hint)
            toolbar.addStretch()

            self.status_label = QLabel("未生成")
            toolbar.addWidget(self.status_label)
            layout.addLayout(toolbar)

            # ── 画布 ──
            self._scene = QGraphicsScene(self)
            self.view = SequenceDiagramView(self._scene)
            self.view.message_clicked.connect(self.message_clicked)
            layout.addWidget(self.view, 1)

            self._build_scene()  # 空态提示

        # ── 对外接口 ──────────────────────────────────────────────

        def set_model(self, model):
            """设置/清空时序图模型并重建场景（None = 清空）"""
            self._model = model
            self._build_scene()
            # 生成后整图可见；tab 未显示时延迟到 showEvent 再 fit
            if model is not None and model.messages:
                if self.isVisible():
                    self.view.fit_window()
                else:
                    self._pending_fit = True

        def highlight_frame(self, frame_idx: int):
            """高亮指定帧对应的消息（摘要表 → 图 联动）"""
            self._apply_highlight(self._highlight_idx, False)
            self._highlight_idx = None
            items = self._msg_items.get(frame_idx)
            if items is None:
                return
            self._highlight_idx = frame_idx
            self._apply_highlight(frame_idx, True)
            line = items.get("line")
            if line is not None:
                self.view.ensureVisible(line)

        def view_fit(self):
            self.view.fit_window()

        def showEvent(self, event):
            super().showEvent(event)
            if self._pending_fit:
                self._pending_fit = False
                self.view.fit_window()

        # ── 场景绘制 ──────────────────────────────────────────────

        def _build_scene(self):
            """把 SequenceModel 布局为 QGraphicsItem（节点框/生命线/箭头/文字）"""
            self._scene.clear()
            self._msg_items = {}
            self._highlight_idx = None
            model = self._model

            if model is None or not model.messages:
                hint = QGraphicsTextItem(
                    "暂无通信消息\n"
                    "请先在「批量解析」页完成协议9/10/11批量解析，"
                    "再点击工具栏「时序图」生成"
                )
                hint.setDefaultTextColor(
                    self.palette().color(QPalette.ColorRole.PlaceholderText)
                )
                self._scene.addItem(hint)
                self._scene.setSceneRect(hint.boundingRect().adjusted(-20, -20, 20, 20))
                if model is None:
                    self.status_label.setText("未生成")
                else:
                    self.status_label.setText(
                        f"0 条消息 / 0 个节点，已跳过 {model.skipped} 帧"
                    )
                return

            text_color = self.palette().color(QPalette.ColorRole.Text)
            node_fill = self.palette().color(QPalette.ColorRole.Base)
            node_border = QColor("#9E9E9E")
            lifeline_pen = QPen(QColor("#9E9E9E"), 1, Qt.DashLine)
            unicast_pen = QPen(QColor("#1976D2"), 2)  # 单播实线（蓝）
            broadcast_pen = QPen(QColor("#F57C00"), 2, Qt.DashLine)  # 广播虚线（橙）

            font = self.font()
            fm = self.fontMetrics()

            # ── 节点（顶部方框 + 生命线）──
            # 自适应水平间距：按最宽消息标签扩展，保证摘要文字在两条生命线
            # 之间完整舒展、不拥挤（下限 NODE_SPACING）
            max_label_w = 0
            for msg in model.messages:
                lw0 = fm.horizontalAdvance(msg.label)
                if lw0 > max_label_w:
                    max_label_w = lw0
            spacing = max(NODE_SPACING, int(max_label_w * 1.2) + 120)
            self._spacing = spacing
            n_nodes = len(model.nodes)
            node_x = {node.key: i * spacing for i, node in enumerate(model.nodes)}
            right_edge = max((n_nodes - 1) * spacing + 120, 240)
            scene_bottom = MSG_FIRST_Y + len(model.messages) * MSG_ROW_H + 30
            for node in model.nodes:
                x = node_x[node.key]
                w = max(NODE_MIN_W, fm.horizontalAdvance(node.label) + 28)
                rect = QGraphicsRectItem(x - w / 2, NODE_TOP, w, NODE_H)
                rect.setBrush(node_fill)
                rect.setPen(QPen(node_border, 1))
                self._scene.addItem(rect)

                text = QGraphicsSimpleTextItem(node.label)
                text.setFont(font)
                tw = text.boundingRect().width()
                th = text.boundingRect().height()
                text.setPos(x - tw / 2, NODE_TOP + (NODE_H - th) / 2)
                text.setBrush(text_color)
                self._scene.addItem(text)

                lifeline = QGraphicsLineItem(x, NODE_TOP + NODE_H, x, scene_bottom)
                lifeline.setPen(lifeline_pen)
                lifeline.setZValue(-1)  # 生命线压底，不挡消息
                self._scene.addItem(lifeline)

            # ── 阶段分隔线 ──
            phase_pen = QPen(QColor("#8E8E8E"), 1, Qt.DashLine)
            for idx, name in getattr(model, "phases", []):
                py = MSG_FIRST_Y + idx * MSG_ROW_H - 26
                div = QGraphicsLineItem(-140, py, right_edge + 40, py)
                div.setPen(phase_pen)
                self._scene.addItem(div)
                ptext = QGraphicsSimpleTextItem(name)
                ptext.setFont(font)
                ptext.setPos(-136, py - 18)
                ptext.setBrush(QColor("#8E8E8E"))
                self._scene.addItem(ptext)

            # ── 消息（按帧序自上而下）──
            for k, msg in enumerate(model.messages):
                y = MSG_FIRST_Y + k * MSG_ROW_H
                src_x = node_x.get(msg.src_key, 0)
                if msg.dst_key is not None:
                    # 有向消息：源生命线 → 目的生命线；控制类(SACK)虚线、
                    # 数据类实线
                    dst_x = node_x.get(msg.dst_key, src_x)
                    x1, x2 = src_x, dst_x
                    if x1 == x2:
                        x2 = x1 + 40  # 自环兜底：短横线避免零长不可见
                    pen = (
                        QPen(broadcast_pen)
                        if msg.kind in _DASHED_KINDS
                        else QPen(unicast_pen)
                    )
                else:
                    # 广播：虚线箭头覆盖全部已有节点（中央信标对所有STA有效），
                    # 从源拉到对侧最远已有节点，不伸入无节点空白
                    xs = list(node_x.values())
                    if len(xs) > 1:
                        x2 = max(xs) if src_x != max(xs) else min(xs)
                    else:
                        x2 = src_x + int(spacing * 0.6)
                    x1 = src_x
                    pen = (
                        QPen(broadcast_pen)
                        if msg.kind in _DASHED_KINDS
                        else QPen(unicast_pen)
                    )

                line_item = QGraphicsLineItem(x1, y, x2, y)
                line_item.setPen(pen)
                line_item.setData(0, msg.frame_idx)
                line_item.setToolTip(msg.summary_full)
                self._scene.addItem(line_item)

                arrow = QGraphicsPolygonItem(
                    _make_arrow_head(x2, y, pointing_left=(x2 < x1))
                )
                arrow.setBrush(pen.color())
                arrow.setPen(QPen(pen.color(), 1))
                arrow.setData(0, msg.frame_idx)
                arrow.setToolTip(msg.summary_full)
                self._scene.addItem(arrow)

                # 消息标签放线段中点上方；超长已在模型层截断，完整摘要 tooltip
                label_item = QGraphicsSimpleTextItem(msg.label)
                label_item.setFont(font)
                lw = label_item.boundingRect().width()
                lh = label_item.boundingRect().height()
                mid = (x1 + x2) / 2
                label_item.setPos(mid - lw / 2, y - lh - 4)
                label_item.setBrush(text_color)
                label_item.setData(0, msg.frame_idx)
                label_item.setToolTip(msg.summary_full)
                self._scene.addItem(label_item)

                if msg.marker and msg.dst_key is not None:
                    mx = node_x.get(msg.dst_key, x2)
                    mtext = QGraphicsSimpleTextItem(msg.marker)
                    mtext.setFont(font)
                    mw = mtext.boundingRect().width()
                    mh = mtext.boundingRect().height()
                    mrect = QGraphicsRectItem(mx - mw / 2 - 6, y + 6, mw + 12, mh + 6)
                    mrect.setBrush(node_fill)
                    mrect.setPen(QPen(QColor("#F57C00"), 1))
                    mrect.setZValue(1)
                    self._scene.addItem(mrect)
                    mtext.setZValue(2)
                    mtext.setPos(mx - mw / 2, y + 9)
                    mtext.setBrush(QColor("#F57C00"))
                    self._scene.addItem(mtext)

                self._msg_items[msg.frame_idx] = {
                    "line": line_item,
                    "arrow": arrow,
                    "label": label_item,
                    "line_pen": QPen(line_item.pen()),
                    "arrow_brush": arrow.brush(),
                }

            self._scene.setSceneRect(-160, -16, right_edge + 160, scene_bottom + 40)
            self.status_label.setText(
                f"{len(model.messages)} 条消息 / {len(model.nodes)} 个节点"
                + (f"，已跳过 {model.skipped} 帧" if model.skipped else "")
            )

        def _apply_highlight(self, frame_idx, on: bool):
            """设置/还原消息高亮（主题强调色加粗，虚线形态保持）"""
            items = self._msg_items.get(frame_idx)
            if not items:
                return
            if on:
                color = self.palette().color(QPalette.ColorRole.Highlight)
                pen = QPen(items["line_pen"])
                pen.setColor(color)
                pen.setWidth(3)
                items["line"].setPen(pen)
                items["arrow"].setBrush(color)
                items["arrow"].setPen(QPen(color, 1))
                font = QFont(self.font())
                font.setBold(True)
                items["label"].setFont(font)
            else:
                items["line"].setPen(QPen(items["line_pen"]))
                items["arrow"].setBrush(items["arrow_brush"])
                items["arrow"].setPen(QPen(items["line_pen"].color(), 1))
                items["label"].setFont(self.font())

        # ── 导出 ──────────────────────────────────────────────────

        def _on_export_png(self):
            """QGraphicsScene.render 渲染整图保存 PNG（分辨率=内容尺寸）"""
            if self._model is None or not self._model.messages:
                QMessageBox.information(self, "提示", "暂无可导出的时序图，请先生成。")
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "导出时序图", "通信时序图.png", "PNG 图片 (*.png)"
            )
            if not path:
                return
            rect = self._scene.sceneRect()
            img = QImage(rect.size().toSize(), QImage.Format_ARGB32)
            img.fill(self.palette().color(QPalette.ColorRole.Base))
            painter = QPainter(img)
            painter.setRenderHint(QPainter.Antialiasing)
            self._scene.render(painter, QRectF(img.rect()), rect)
            painter.end()
            if img.save(path, "PNG"):
                self.status_label.setText(f"已导出: {path}")
            else:
                QMessageBox.warning(self, "导出失败", f"无法保存文件：{path}")
