"""GUI 主题感知图标加载（Lucide SVG → QIcon）。

Lucide SVG 用 stroke="currentColor"，QtSvg 不识别该关键字（直接 QIcon(path)
会渲染成黑色，暗色主题下隐形）。本模块用自定义 QIconEngine，每次绘制时按
控件状态从 QPalette 取色，把 currentColor 替换为实际颜色后再渲染：

- 亮/暗主题自动跟随（paint 现取调色板颜色，主题切换无需重载图标）
- 禁用态自动变灰（Disabled 调色板组）
- 图标缺失时返回空 QIcon（不崩溃，仅打印一次警告）

用法：
    from app_icons import load_icon
    button.setIcon(load_icon("refresh-cw"))
    tab_widget.addTab(widget, load_icon("terminal"), "单帧解析")

图标文件：icons/lucide/<name>.svg（Lucide 1.38.0，ISC 许可，见 icons/README.md）。
"""

from __future__ import annotations

import functools
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

_ICONS_DIR = Path(__file__).resolve().parent / "icons" / "lucide"

# name → SVG 原始字节（None 表示已确认缺失，避免重复查盘/刷屏）
_svg_cache: dict[str, bytes | None] = {}
# (name, #rrggbb) → 渲染器
_renderer_cache: dict[tuple[str, str], QSvgRenderer] = {}


def _svg_bytes(name: str) -> bytes | None:
    if name not in _svg_cache:
        path = _ICONS_DIR / f"{name}.svg"
        if path.exists():
            _svg_cache[name] = path.read_bytes()
        else:
            print(f"[app_icons] 图标文件不存在: {path}")
            _svg_cache[name] = None
    return _svg_cache[name]


def _renderer(name: str, color_hex: str) -> QSvgRenderer | None:
    key = (name, color_hex)
    r = _renderer_cache.get(key)
    if r is None:
        data = _svg_bytes(name)
        if data is None:
            return None
        # Lucide 全文件仅一处 currentColor（根元素 stroke）
        data = data.replace(b"currentColor", color_hex.encode("ascii"))
        r = QSvgRenderer(data)
        if not r.isValid():
            return None
        _renderer_cache[key] = r
    return r


class _LucideIconEngine(QIconEngine):
    """按 QIcon.Mode 取调色板颜色现场渲染 SVG 的图标引擎。"""

    def __init__(self, name: str):
        super().__init__()
        self._name = name

    def _color(self, mode: QIcon.Mode):
        app = QApplication.instance()
        pal = app.palette() if app is not None else QPalette()
        if mode == QIcon.Mode.Disabled:
            return pal.color(
                QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText
            )
        return pal.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.ButtonText)

    def paint(self, painter: QPainter, rect, mode, state):  # noqa: ANN001
        renderer = _renderer(self._name, self._color(mode).name())
        if renderer is not None:
            painter.save()
            renderer.render(painter, QRectF(rect))
            painter.restore()

    def pixmap(self, size, mode, state):  # noqa: ANN001
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        self.paint(painter, QRectF(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return pm

    def clone(self) -> QIconEngine:
        return _LucideIconEngine(self._name)


@functools.lru_cache(maxsize=256)
def load_icon(name: str) -> QIcon:
    """加载 Lucide 图标（kebab-case 文件名，不含 .svg）。

    缺失时返回空 QIcon（isNull() 为 True），调用方无需特判。
    """
    if _svg_bytes(name) is None:
        return QIcon()
    return QIcon(_LucideIconEngine(name))
