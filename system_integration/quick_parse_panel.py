"""
快捷解析小窗（uTools 风格，系统集成）
====================================
全局热键唤出的无边框置顶悬浮面板：

- 结构为两张独立卡片：输入卡（徽章行 + 输入框）常驻；粘贴/输入报文后
  实时在下方浮出结果卡（状态提示 + 结果表格 + 底部操作行）
- 清空输入自动收回为单输入卡形态
- 卡片半透明悬浮感；两卡间及边缘空白处按住拖动移动窗口，右下角 QSizeGrip 调整大小
- Esc / 再次热键 / 点击面板外部 → 隐藏

面板为「哑组件」：不 import 任何 parser/validator，解析能力由 MainWindow
注入回调（clean_fn/parse_fn/validate_fn/open_full_fn），避免
system_integration 层横向依赖解析器。
"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui_utils import ZoomableTableWidget
from system_integration.acrylic_effect import enable_acrylic
from system_integration.clipboard_monitor import detect_protocol

# 实时解析防抖（毫秒）
_PARSE_DEBOUNCE_MS = 300
# 展开态默认宽度
_DEFAULT_WIDTH = 720
_MIN_WIDTH = 520
# 表格最小高度（展开但内容少时保证可拖拽区域）
_TABLE_MIN_H = 96


class _VisibleSizeGrip(QSizeGrip):
    """右下角可见缩放柄：绘制三条斜向抓手线，半透明随主题着色。

    原生 QSizeGrip 在 WA_TranslucentBackground 无边框窗上几乎不可见，
    导致用户找不到调整宽度/高度的热区；本类仅加视觉提示，交互仍走
    QSizeGrip 原生 WM 命中测试（可同时拖宽/拖高）。
    """

    def __init__(self, parent, is_dark_fn=None):
        super().__init__(parent)
        self._is_dark_fn = is_dark_fn or (lambda: False)
        self.setFixedSize(20, 20)
        self.setToolTip("拖动调整小窗大小（宽 / 高）")

    def paintEvent(self, event):
        from PySide6.QtGui import QColor, QPainter, QPen

        dark = bool(self._is_dark_fn()) if callable(self._is_dark_fn) else False
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(255, 255, 255, 150) if dark else QColor(70, 90, 140, 160)
        pen = QPen(color)
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        # 右下角三条等距斜线（从右下角向左上排列）
        w, h = self.width(), self.height()
        gap = 5
        for i in range(3):
            # 每条线平行于 / 方向：从右边缘某点到下边缘某点，间隔 gap
            x0 = w - 4 - i * gap
            y1 = h - 4 - i * gap
            painter.drawLine(x0, h - 2, w - 2, y1)
        painter.end()


class QuickParsePanel(QWidget):
    """uTools 风格快捷解析悬浮小窗。"""

    def __init__(
        self,
        parent=None,
        *,
        protocol_items,
        clean_fn,
        parse_fn,
        validate_fn,
        open_full_fn,
        is_dark_fn=None,
    ):
        """
        Args:
            protocol_items: [(显示文本, 协议索引), ...]
            clean_fn:       (text) -> cleaned_hex_str      hex 清洗
            parse_fn:       (frame_bytes, idx) -> (rows|None, err|None, note|None)
                            rows 为 4 元组列表 (字段, 原始值, 解析值, 说明)
            validate_fn:    (frame_bytes, idx) -> (valid|None, summary_str)
            open_full_fn:   (frame_bytes, idx) -> None     打开完整解析弹窗
            is_dark_fn:     () -> bool                     是否暗色主题
        """
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(_MIN_WIDTH)

        self._clean_fn = clean_fn
        self._parse_fn = parse_fn
        self._validate_fn = validate_fn
        self._open_full_fn = open_full_fn
        self._is_dark_fn = is_dark_fn or (lambda: False)
        self._frame_bytes = b""
        self._ever_activated = False  # 至少激活过一次，失焦自动隐藏才生效
        self._proto_manual = False  # 用户手动选过协议后，自动识别不再覆盖
        self._drag_offset = None  # 按下时鼠标相对窗口左上角的偏移
        self._user_geom = False  # 用户拖动/调整过几何后不再自动居中/适配高度
        self._prog_resize = False  # 程序触发的 resize 不算用户调整
        self._last_valid = (None, "")  # 最近一次校验结果（restyle 时重绘徽章用）
        self._expanded = False  # 当前是否为展开态（决定输入卡是否带边框）
        self._glass_qss = ""  # 展开态毛玻璃面板样式（_restyle 填充）
        self._empty_qss = ""  # 空态透明面板样式（_restyle 填充）

        self._build_ui(protocol_items)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._do_parse)

    # ------------------------------------------------------------------ UI

    def _build_ui(self, protocol_items):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)  # 给毛玻璃面板留出投影空间
        outer.setSpacing(0)

        # ── 单一毛玻璃面板（WOX 风格：一个连续圆角半透明容器，不再是两张浮卡）──
        self.panel = QFrame()
        self.panel.setObjectName("qpPanel")
        self.panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._shadows = [self._make_shadow(self.panel)]

        box = QVBoxLayout(self.panel)
        box.setContentsMargins(16, 14, 16, 12)
        box.setSpacing(10)

        # 兼容既有引用：input_card 即主面板；result_card 为面板内结果区容器
        self.input_card = self.panel
        self.in_layout = box

        # ── 徽章行：协议 + 帧长 + 校验（空态隐藏）──
        self.header = QWidget()
        top = QHBoxLayout(self.header)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.proto_combo = QComboBox()
        for text, idx in protocol_items:
            self.proto_combo.addItem(text, idx)
        self.proto_combo.setMinimumWidth(240)
        self.proto_combo.setToolTip("自动识别协议；识别错误时可手动切换")
        top.addWidget(self.proto_combo)
        top.addStretch()
        self.len_label = QLabel("")
        self.valid_label = QLabel("")
        for w in (self.len_label, self.valid_label):
            w.setFixedHeight(20)
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.valid_label.setToolTip("")
        top.addWidget(self.len_label)
        top.addWidget(self.valid_label)
        self.header.setVisible(False)
        box.addWidget(self.header)

        # ── 输入框（常驻）──
        self.input = QTextEdit()
        self.input.setPlaceholderText(
            "粘贴或输入十六进制报文，实时解析…   Esc 关闭 · 右下角拖大小"
        )
        self.input.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.input.setMinimumHeight(46)
        self.input.setFont(QFont("Consolas", 11))
        box.addWidget(self.input, 0)

        # ── 结果区容器（状态提示 + 表格 + 底部行）；空态整体隐藏 ──
        self.result_card = QWidget()
        self.result_card.setObjectName("qpResult")
        layout = QVBoxLayout(self.result_card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        self.table = ZoomableTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        self.table.setEditTriggers(ZoomableTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            ZoomableTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(15)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 120)
        self.table.setFont(QFont("Microsoft YaHei", 8))
        self.table.setMinimumHeight(_TABLE_MIN_H)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setSizePolicy(sp)
        self.table.setVisible(False)
        layout.addWidget(self.table, 1)

        # ── 底部行：操作按钮（左）+ 键位提示（右）──
        self.footer = QWidget()
        bottom = QHBoxLayout(self.footer)
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)
        self.full_btn = QPushButton("在主窗口打开")
        self.full_btn.setToolTip(
            "用完整解析窗口打开当前报文（含解析级别/ED 剥离等高级选项）"
        )
        self.full_btn.clicked.connect(self._open_full)
        self.copy_btn = QPushButton("复制结果")
        self.copy_btn.setToolTip("复制解析结果文本")
        self.copy_btn.clicked.connect(self._copy_result)
        bottom.addWidget(self.full_btn)
        bottom.addWidget(self.copy_btn)
        bottom.addStretch()
        self.hint_label = QLabel(
            "打开完整视图 Enter · 关闭 Esc · 复制 Ctrl+C"
        )
        bottom.addWidget(self.hint_label)
        self.footer.setVisible(False)
        layout.addWidget(self.footer)

        self.result_card.setVisible(False)
        box.addWidget(self.result_card, 1)

        outer.addWidget(self.panel)

        # 右下角可见缩放柄：斜纹提示 + 原生 QSizeGrip 交互（宽/高均可拖）
        self.size_grip = _VisibleSizeGrip(self, is_dark_fn=self._is_dark_fn)

        # 信号
        self.input.textChanged.connect(self._on_text_changed)
        self.proto_combo.currentIndexChanged.connect(self._on_proto_manually_changed)

        self._set_empty_state()
        self._restyle()

    def _make_shadow(self, target):
        shadow = QGraphicsDropShadowEffect(target)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 6)
        shadow.setColor(self._shadow_color())
        target.setGraphicsEffect(shadow)
        return shadow

    def _shadow_color(self):
        from PySide6.QtGui import QColor

        dark = self._is_dark_fn() if callable(self._is_dark_fn) else False
        return QColor(0, 0, 0, 180 if dark else 120)

    # -------------------------------------------------------------- 显隐

    def showEvent(self, event):
        super().showEvent(event)
        # 窗口创建/显示后应用系统级毛玻璃（亚克力）；随主题色调，非 Windows 静默降级
        self._apply_acrylic()

    def _apply_acrylic(self):
        dark = bool(self._is_dark_fn()) if callable(self._is_dark_fn) else False
        if dark:
            enable_acrylic(self, tint=(24, 27, 38), alpha=60)
        else:
            enable_acrylic(self, tint=(236, 242, 252), alpha=50)

    def toggle_panel(self):
        """热键入口：可见则隐藏，不可见则显示（并预填剪贴板）。"""
        if self.isVisible():
            self.hide()
            return
        if not self._user_geom:
            self._reposition()
        self._restyle()
        self._apply_acrylic()  # 主题可能在隐藏期间切换，重新着色
        self._prefill_clipboard()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def _reposition(self):
        screen = (
            QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        )
        try:
            screen = (
                QGuiApplication.screenAt(QCursor.pos())
                or QGuiApplication.primaryScreen()
            )
            if screen is None:
                return
            avail = screen.availableGeometry()
            x = avail.center().x() - _DEFAULT_WIDTH // 2
            y = avail.y() + int(avail.height() * 0.12)
        except Exception:
            return
        self.move(x, y)

    def changeEvent(self, event):
        # 失焦（点击面板外部 / 切换应用）自动隐藏——uTools 行为。
        # 需先激活过一次：show() 后未获得焦点（如 offscreen）时不立即自隐。
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self._ever_activated = True
            elif self._ever_activated and self.isVisible():
                self.hide()
        super().changeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------- 拖动 / 缩放

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 子控件（label/card 背景）未处理的按下会冒泡到这里形成拖动；
        # 输入框/combo/按钮/表格自行消费事件，不会触发拖动
        if self._drag_offset is not None and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._user_geom = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 缩放柄贴窗口右下角（margin 透明区）；22px 热区贴右下角，增大有效抓取面积
        self.size_grip.move(
            self.width() - self.size_grip.width(),
            self.height() - self.size_grip.height(),
        )
        self.size_grip.raise_()
        if getattr(self, "_prog_resize", False):
            self._prog_resize = False
        elif self.isVisible():
            self._user_geom = True

    # ------------------------------------------------------------ 几何适配

    def _fit_height(self):
        """按当前可见内容把窗口高度收缩到恰好（宽不变），封顶屏幕 80%。"""
        # 收起/展开刚改变子控件可见性时布局缓存尚未失效，需强制同步重算
        outer_layout = self.layout()
        if outer_layout is not None:
            outer_layout.invalidate()
        for card in (self.input_card, self.result_card):
            inner = card.layout()
            if inner is not None:
                inner.invalidate()
                # 只 invalidate 不 activate 时，外层 activate()/sizeHint() 仍读
                # 旧缓存 → 窗口高度滞留/回弹；必须先激活内层布局
                inner.activate()
        if outer_layout is not None:
            outer_layout.activate()
        self._prog_resize = True
        try:
            screen = (
                QGuiApplication.screenAt(QCursor.pos())
                or QGuiApplication.primaryScreen()
            )
            if screen is None:
                return
            avail = screen.availableGeometry()
            cap = int(avail.height() * 0.8)
        except Exception:
            return
        hint_h = self.sizeHint().height()
        self.resize(max(self.minimumWidth(), self.width()), min(hint_h, cap))
        self.updateGeometry()

    def _prefill_clipboard(self):
        """显示时预填剪贴板：合法 hex 则填入并全选+解析，否则清空等待输入。"""
        self._proto_manual = False  # 每次唤出重新自动识别
        text = QGuiApplication.clipboard().text() or ""
        frame = self._try_clean(text)
        if frame is not None:
            self.input.blockSignals(True)
            self.input.setPlainText(" ".join(f"{b:02X}" for b in frame))
            self.input.selectAll()
            self.input.blockSignals(False)
            self._frame_bytes = frame
            self._do_parse()
        else:
            self.input.blockSignals(True)
            self.input.clear()
            self.input.blockSignals(False)
            self._frame_bytes = b""
            self._set_empty_state()

    # -------------------------------------------------------------- 解析

    def _on_text_changed(self):
        self._proto_manual = False  # 新输入：恢复自动识别
        self._debounce.start(_PARSE_DEBOUNCE_MS)

    def _on_proto_manually_changed(self, _idx):
        self._proto_manual = True  # 用户手动选择：自动识别不再覆盖
        if self._frame_bytes:
            self._do_parse()

    def _try_clean(self, text):
        """文本 → bytes；非法/不足 4 字节返回 None。"""
        try:
            clean = self._clean_fn(text)
        except Exception:
            return None
        clean = clean.strip()
        if not clean or len(clean) % 2 != 0:
            return None
        if not all(c in "0123456789abcdefABCDEF" for c in clean):
            return None
        frame = bytes.fromhex(clean)
        if len(frame) < 4:
            return None
        return frame

    def _do_parse(self):
        frame = self._try_clean(self.input.toPlainText())
        if frame is None:
            self._frame_bytes = b""
            if self.input.toPlainText().strip():
                self._set_error(
                    "不是有效的十六进制报文（需要偶数长度的 hex，至少 4 字节）。"
                )
            else:
                self._set_empty_state()
            return

        self._frame_bytes = frame
        idx = self.proto_combo.currentData()

        # 自动识别协议（用户未手动选择时；静默切换不触发手动连接）
        if not self._proto_manual:
            detected = detect_protocol(frame)
            if detected is not None:
                di = self.proto_combo.findData(detected)
                if di >= 0 and di != self.proto_combo.currentIndex():
                    self.proto_combo.blockSignals(True)
                    self.proto_combo.setCurrentIndex(di)
                    self.proto_combo.blockSignals(False)
                    idx = detected

        # 帧长
        self.len_label.setText(f"{len(frame)} 字节")

        # 解析
        try:
            rows, err, note = self._parse_fn(frame, idx)
        except Exception as e:
            rows, err, note = None, f"解析异常：{e}", None

        if err is not None:
            self._set_error(err)
        elif not rows:
            self._set_error("未解析出任何字段。")
        else:
            self._fill_table(rows)
            if note:
                self.status_label.setText(note)
                self._style_status("#b26a00")
                self.status_label.setVisible(True)

        # 校验徽章
        try:
            valid, summary = self._validate_fn(frame, idx)
        except Exception:
            valid, summary = None, ""
        self._set_valid_badge(valid, summary)

        self._expand()
        self._fit_height()

    def _fill_table(self, rows):
        self.status_label.setVisible(False)
        self.table.setVisible(True)
        self.table.setRowCount(0)
        for r, item in enumerate(rows):
            self.table.insertRow(r)
            for c in range(4):
                self.table.setItem(
                    r, c, QTableWidgetItem(str(item[c]) if c < len(item) else "")
                )

    # ------------------------------------------------------- 形态切换

    def _expand(self):
        """展开：结果区浮出（徽章行/表格/底部键位提示显示）。"""
        self.header.setVisible(True)
        self.result_card.setVisible(True)
        self.footer.setVisible(True)
        self._sync_card_chrome(expanded=True)

    def _set_empty_state(self):
        """收起：仅显示输入框（结果区隐藏），主毛玻璃面板始终保留。"""
        self.table.setVisible(False)
        self.status_label.setVisible(False)
        self.header.setVisible(False)
        self.footer.setVisible(False)
        self.result_card.setVisible(False)
        self.len_label.setText("")
        self._set_valid_badge(None, "", quiet=True)
        self._sync_card_chrome(expanded=False)
        self._fit_height()

    def _set_error(self, msg):
        self.table.setVisible(False)
        self.len_label.setText("")
        self._set_valid_badge(None, "", quiet=True)
        self.header.setVisible(True)
        self.result_card.setVisible(True)
        self.footer.setVisible(True)
        self.status_label.setText("⚠ " + msg)
        self._style_status("#d32f2f")
        self.status_label.setVisible(True)
        self._sync_card_chrome(expanded=True)

    def _sync_card_chrome(self, expanded):
        """按形态切换主面板外观与输入框高度。

        空态：面板透明无边框禁投影（只显示输入框本身），输入框拉高填充，
        允许纵向拖拽改高度。
        展开态：面板呈现毛玻璃底色+1px 细边框+投影，输入框限高，
        多余高度让给结果表格。
        """
        self._expanded = expanded
        if expanded:
            self.input.setMaximumHeight(70)  # 展开后输入框限高，避免挤占表格
            if self._glass_qss:
                self.panel.setStyleSheet(self._glass_qss)
            for sh in getattr(self, "_shadows", []):
                sh.setEnabled(True)
        else:
            self.input.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX：空态可拉高
            if self._empty_qss:
                self.panel.setStyleSheet(self._empty_qss)
            for sh in getattr(self, "_shadows", []):
                sh.setEnabled(False)


    def _style_status(self, color):
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    # ---------------------------------------------------------- 校验徽章

    def _badge_qss(self, bg, fg, bold=False):
        return (
            f"padding: 2px 8px; border-radius: 10px; font-size: 12px; "
            f"background: {bg}; color: {fg};" + ("font-weight: bold;" if bold else "")
        )

    def _badge_colors(self, valid):
        """按主题返回 (bg, fg)。"""
        dark = bool(self._is_dark_fn())
        if valid is None:
            return (
                ("rgba(255,255,255,0.10)", "#9aa0a6")
                if dark
                else ("rgba(224,224,224,0.85)", "#666666")
            )
        if valid:
            return (
                ("rgba(102,187,106,0.30)", "#a5d6a7")
                if dark
                else ("rgba(232,245,233,0.92)", "#2e7d32")
            )
        return (
            ("rgba(239,83,80,0.28)", "#ef9a9a")
            if dark
            else ("rgba(255,235,238,0.92)", "#c62828")
        )

    def _set_valid_badge(self, valid, summary, quiet=False):
        """设置校验徽章；quiet=True 仅记录状态不显示文本（收起态）。"""
        self._last_valid = (valid, summary)
        if quiet:
            return
        bg, fg = self._badge_colors(valid)
        if valid is None:
            self.valid_label.setText("—")
            self.valid_label.setStyleSheet(self._badge_qss(bg, fg))
            self.valid_label.setToolTip("当前协议不支持自动校验")
        elif valid:
            self.valid_label.setText("✓ 校验通过")
            self.valid_label.setStyleSheet(self._badge_qss(bg, fg, bold=True))
            self.valid_label.setToolTip(summary or "校验通过")
        else:
            self.valid_label.setText("✗ 校验失败")
            self.valid_label.setStyleSheet(self._badge_qss(bg, fg, bold=True))
            self.valid_label.setToolTip(summary or "校验失败")

    def _sync_badge(self):
        self._set_valid_badge(*self._last_valid)

    # -------------------------------------------------------------- 动作

    def _open_full(self):
        if not self._frame_bytes:
            return
        idx = self.proto_combo.currentData()
        self.hide()
        self._open_full_fn(self._frame_bytes, idx)

    def _copy_result(self):
        lines = []
        for r in range(self.table.rowCount()):
            cells = []
            for c in range(4):
                it = self.table.item(r, c)
                cells.append(it.text() if it is not None else "")
            lines.append("\t".join(cells))
        if lines:
            QGuiApplication.clipboard().setText("\n".join(lines))
            self.status_label.setText("已复制解析结果。")
            self._style_status("#2e7d32")
            self.status_label.setVisible(True)
            QTimer.singleShot(
                1500, lambda: self.status_label.setVisible(self.table.isVisible())
            )

    # -------------------------------------------------------------- 主题

    def _restyle(self):
        dark = bool(self._is_dark_fn())
        if dark:
            # 深色毛玻璃：深蓝灰半透明面板（约 45%）+ 亮色细边
            bg = "rgba(30, 33, 46, 115)"
            border = "rgba(255,255,255,0.14)"
            fg = "#e8ebf2"
            sub_fg = "#aab1c0"
            input_qss = (
                "QTextEdit { background: rgba(255,255,255,0.07); color: #e8ebf2; "
                "border: 1px solid rgba(255,255,255,0.13); border-radius: 8px; "
                "padding: 7px 10px; font-size: 15px; "
                "selection-background-color: rgba(139,92,246,0.45); }")
            btn_qss = (
                "QPushButton { background: rgba(255,255,255,0.10); color: #e8ebf2; "
                "border: 1px solid rgba(255,255,255,0.16); border-radius: 8px; padding: 5px 14px; }"
                "QPushButton:hover { background: rgba(139,92,246,0.30); }"
                "QPushButton:pressed { background: rgba(139,92,246,0.45); }")
            combo_qss = (
                "QComboBox { background: rgba(255,255,255,0.08); color: #e8ebf2; "
                "border: 1px solid rgba(255,255,255,0.16); border-radius: 8px; padding: 3px 8px; }"
                "QComboBox QAbstractItemView { background: rgba(38,42,56,240); color: #e8ebf2; "
                "selection-background-color: rgba(139,92,246,0.5); border: none; }")
            table_qss = (
                "QTableWidget { background: transparent; color: #dfe3ec; border: none; "
                "border-radius: 6px; gridline-color: rgba(255,255,255,0.08); }"
                "QTableWidget::item { padding: 3px 8px; }"
                "QTableWidget::item:selected { background: rgba(139,92,246,0.55); color: #ffffff; }"
                "QHeaderView::section { background: transparent; color: #c6ccda; "
                "border: none; border-bottom: 1px solid rgba(255,255,255,0.12); padding: 4px; }")
        else:
            # 浅色毛玻璃：淡白半透明面板（WOX 风格淡灰白）+ 白色高光细边
            bg = "rgba(250, 250, 252, 150)"
            border = "rgba(255,255,255,0.80)"
            fg = "#2b3242"
            sub_fg = "#8a8f9a"
            input_qss = (
                "QTextEdit { background: rgba(255,255,255,0.60); color: #2b3242; "
                "border: 1px solid rgba(60,70,110,0.14); border-radius: 8px; "
                "padding: 7px 10px; font-size: 15px; "
                "selection-background-color: rgba(139,92,246,0.28); }")
            btn_qss = (
                "QPushButton { background: rgba(255,255,255,0.65); color: #3a415a; "
                "border: 1px solid rgba(60,70,110,0.16); border-radius: 8px; padding: 5px 14px; }"
                "QPushButton:hover { background: rgba(139,92,246,0.18); }"
                "QPushButton:pressed { background: rgba(139,92,246,0.30); }")
            combo_qss = (
                "QComboBox { background: rgba(255,255,255,0.65); color: #3a415a; "
                "border: 1px solid rgba(60,70,110,0.16); border-radius: 8px; padding: 3px 8px; }"
                "QComboBox QAbstractItemView { background: rgba(250,250,253,248); color: #3a415a; "
                "selection-background-color: rgba(139,92,246,0.30); border: none; }")
            table_qss = (
                "QTableWidget { background: transparent; color: #333a4e; border: none; "
                "border-radius: 6px; gridline-color: rgba(60,70,110,0.08); }"
                "QTableWidget::item { padding: 3px 8px; }"
                "QTableWidget::item:selected { background: rgba(106,76,222,0.92); color: #ffffff; }"
                "QHeaderView::section { background: transparent; color: #5a627a; "
                "border: none; border-bottom: 1px solid rgba(60,70,110,0.12); padding: 4px; }")
        # 单一毛玻璃主面板（唯一的描边/底色容器，消除双边框）
        self._glass_qss = (
            f"#qpPanel {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 14px; }}")
        self._empty_qss = (
            "#qpPanel { background: transparent; border: none; "
            "border-radius: 14px; }")
        self.panel.setStyleSheet(self._glass_qss if self._expanded else self._empty_qss)
        self.input.setStyleSheet(input_qss)
        self.proto_combo.setStyleSheet(combo_qss)
        for btn in (self.full_btn, self.copy_btn):
            btn.setStyleSheet(btn_qss)
        self.table.setStyleSheet(table_qss)
        self.hint_label.setStyleSheet(f"color: {sub_fg}; font-size: 12px;")
        # 投影颜色随主题；空态禁用投影（仅展开态呈现毛玻璃投影）
        for sh in getattr(self, "_shadows", []):
            sh.setColor(self._shadow_color())
            sh.setEnabled(self._expanded)
        # 徽章按最近状态重绘
        self._sync_badge()
