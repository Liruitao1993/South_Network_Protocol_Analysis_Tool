"""GUI通用工具：中文右键菜单、可缩放表格、按钮图标等"""

from PySide6.QtWidgets import QLineEdit, QTextEdit, QTableWidget, QPushButton, QStyle
from PySide6.QtCore import Qt, QSize
from typing import Optional


# 按钮图标映射：icon_key -> Qt 内置标准图标（QStyle.StandardPixmap）。
# 全部用 Qt 内置标准图标，零额外资源、跨平台稳定、随系统主题/高 DPI 自动适配。
_STANDARD_ICON_MAP = {
    "open": QStyle.StandardPixmap.SP_DirOpenIcon,               # 打开/载入/浏览
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,          # 保存/导出
    "export": QStyle.StandardPixmap.SP_DialogSaveButton,        # 导出（别名字，语义清晰）
    "open_file": QStyle.StandardPixmap.SP_DialogOpenButton,     # 打开文件
    "add": QStyle.StandardPixmap.SP_FileDialogNewFolder,        # 添加/新增
    "apply": QStyle.StandardPixmap.SP_DialogApplyButton,        # 应用/确定/生成/注册
    "ok": QStyle.StandardPixmap.SP_DialogOkButton,              # 确定
    "cancel": QStyle.StandardPixmap.SP_DialogCancelButton,      # 取消/关闭
    "up": QStyle.StandardPixmap.SP_ArrowUp,                  # 上移
    "down": QStyle.StandardPixmap.SP_ArrowDown,              # 下移
    "edit": QStyle.StandardPixmap.SP_FileDialogListView,     # 编辑（QStyle 无铅笔图标，用文档+横线隐喻）
    "refresh": QStyle.StandardPixmap.SP_BrowserReload,          # 刷新/交换/重载
    "delete": QStyle.StandardPixmap.SP_TrashIcon,               # 删除/清除/移除
    "clear": QStyle.StandardPixmap.SP_LineEditClearButton,      # 清空
    "play": QStyle.StandardPixmap.SP_MediaPlay,                 # 解析/发送/开始/运行/校验
    "stop": QStyle.StandardPixmap.SP_MediaStop,                 # 停止/关闭
    "pause": QStyle.StandardPixmap.SP_MediaPause,               # 暂停
    "copy": QStyle.StandardPixmap.SP_FileDialogContentsView,    # 复制/查询/搜索/定位
    "help": QStyle.StandardPixmap.SP_MessageBoxInformation,     # 帮助/说明
    "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,      # 警告类
}


# 默认图标尺寸（逻辑像素，随系统高 DPI 自动缩放）
_BTN_ICON_SIZE = 16

# 未知图标键告警去重（静默跳过曾导致「分享此帧」无图标长期未发现）
_unknown_icon_keys_warned: set = set()


def set_btn_icon(btn: QPushButton, icon_key: str, icon_only: bool = False) -> QPushButton:
    """为按钮添加 Qt 内置标准图标（图标 + 文字并存）。

    - icon_key: _STANDARD_ICON_MAP 中的键；未知键跳过并打印一次告警（不崩溃）。
    - icon_only: 为 True 时隐藏文字仅显示图标（默认 False 保留文字）。
    图标尺寸固定 _BTN_ICON_SIZE，随系统高 DPI 自动适配；颜色随系统主题。
    """
    pix = _STANDARD_ICON_MAP.get(icon_key)
    if pix is None:
        if icon_key not in _unknown_icon_keys_warned:
            _unknown_icon_keys_warned.add(icon_key)
            print(f"[gui_utils] set_btn_icon 未知图标键: {icon_key!r}（已跳过，"
                  f"可用键: {sorted(_STANDARD_ICON_MAP)}）")
        return btn
    icon = btn.style().standardIcon(pix)
    btn.setIcon(icon)
    btn.setIconSize(QSize(_BTN_ICON_SIZE, _BTN_ICON_SIZE))
    if icon_only:
        btn.setText("")
        btn.setToolTip(btn.toolTip() or btn.text())
    return btn


def set_btn(btn: QPushButton, kind: str = "primary", size: Optional[str] = None) -> QPushButton:
    """统一按钮风格：设语义类（btnKind）与尺寸（btnSize），形状/颜色/状态全由主题 QSS 接管。

    - kind: primary(主蓝) / success(绿) / danger(红) / warning(橙) / accent(紫)
            / secondary(次要灰) / ghost(透明图标按钮)
    - size: None(默认 min-h26) / "sm"(22) / "lg"(30)
    行内不要再写 border-radius/padding/background/字号，否则会切断 QSS 伪状态。
    """
    btn.setProperty("btnKind", kind)
    if size:
        btn.setProperty("btnSize", size)
    # 动态属性变更后需 unpolish/polish 让属性选择器重新匹配
    style = btn.style()
    if style is not None:
        style.unpolish(btn)
        style.polish(btn)
    return btn


class ZoomableTableWidget(QTableWidget):
    """支持 Ctrl+滚轮整体缩放的表格（类 Excel）。

    缩放 = 字号 + 行高同步（列宽保持，避免破坏固定列布局）；
    Ctrl+0 恢复缩放前基准。缩放为 per-table 覆盖，
    全局字体设置变更后表格回到基准字号。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._zoom_base: Optional[tuple] = None  # (pointSizeF, defaultSectionSize)

    def _zoom_start(self):
        """首次缩放前记录基准（缩放前字体为基准字号）"""
        f = self.font()
        vh = self.verticalHeader()
        self._zoom_base = (f.pointSizeF(), vh.defaultSectionSize() or 20)

    def refresh_qss_font(self):
        """主题 QSS font-size 生效后调用：以当前实际字体为新缩放基准。

        Qt 限制：样式表设置的字体不反映到 widget.font()，Ctrl+0 恢复会
        用旧基准字号覆盖 QSS 字号；行高也需按新字号重算，否则文字被裁切。
        """
        self._zoom_base = None
        fm = self.fontMetrics()
        vh = self.verticalHeader()
        vh.setDefaultSectionSize(max(6, fm.height() + 6))

    def _apply_zoom(self, factor: float):
        self._zoom_start()
        f = self.font()
        f.setPointSizeF(max(5.0, min(24.0, (f.pointSizeF() or 9.0) * factor)))
        self.setFont(f)
        vh = self.verticalHeader()
        vh.setDefaultSectionSize(max(6, int(vh.defaultSectionSize() * factor)))

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            y = e.angleDelta().y()
            if y != 0:
                self._apply_zoom(1.1 if y > 0 else 0.9)
                e.accept()
                return
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        if (e.modifiers() & Qt.KeyboardModifier.ControlModifier
                and e.key() == Qt.Key.Key_0 and self._zoom_base is not None):
            base_pt, base_row = self._zoom_base
            f = self.font()
            f.setPointSizeF(base_pt)
            self.setFont(f)
            self.verticalHeader().setDefaultSectionSize(base_row)
            self._zoom_base = None
            e.accept()
            return
        super().keyPressEvent(e)


def setup_chinese_context_menu(widget):
    """为单行/多行文本输入控件设置中文右键菜单"""
    if not isinstance(widget, (QLineEdit, QTextEdit)):
        return
    # 若已有自定义右键菜单，则不覆盖
    if widget.contextMenuPolicy() == Qt.CustomContextMenu:
        return

    def _show_menu(pos):
        menu = widget.createStandardContextMenu()
        menu.setStyleSheet("QMenu { background-color: white; color: black; } QMenu::item:selected { background-color: #e3f2fd; }")
        text_map = {
            "Undo": "撤销",
            "Redo": "恢复",
            "Cut": "剪切",
            "Copy": "复制",
            "Paste": "粘贴",
            "Delete": "删除",
            "Select All": "全选",
            "Undo\tCtrl+Z": "撤销\tCtrl+Z",
            "Redo\tCtrl+Y": "恢复\tCtrl+Y",
            "Cut\tCtrl+X": "剪切\tCtrl+X",
            "Copy\tCtrl+C": "复制\tCtrl+C",
            "Paste\tCtrl+V": "粘贴\tCtrl+V",
            "Delete": "删除",
            "Select All\tCtrl+A": "全选\tCtrl+A",
        }
        for action in menu.actions():
            original = action.text().replace("&", "")
            if original in text_map:
                action.setText(text_map[original])
        menu.exec(widget.mapToGlobal(pos))

    widget.setContextMenuPolicy(Qt.CustomContextMenu)
    widget.customContextMenuRequested.connect(_show_menu)


def apply_chinese_context_menus(parent_widget):
    """为parent_widget及其子控件中所有QLineEdit/QTextEdit设置中文右键菜单"""
    seen = set()
    for cls in (QLineEdit, QTextEdit):
        for widget in parent_widget.findChildren(cls):
            wid = id(widget)
            if wid not in seen:
                seen.add(wid)
                setup_chinese_context_menu(widget)
