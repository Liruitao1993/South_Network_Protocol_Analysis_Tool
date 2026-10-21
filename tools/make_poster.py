# -*- coding: utf-8 -*-
"""生成朋友圈推广海报（1080×1440 竖版 / 1080×1080 方版）。

设计语言与 `docs/images/og-social.png` 保持一致（深藏青底 + 橙色点缀 + 蓝色协议胶囊），
只是把信息密度压到朋友圈一屏能看清。

用法::

    python tools/make_poster.py                  # 两种尺寸都出
    python tools/make_poster.py --variant tall   # 只出竖版

产物默认写到 ``推广/朋友圈/``。二维码由外部接口生成（指向 GitHub 仓库），
拿不到网络时自动降级为纯文字 CTA，不会阻塞出图。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "推广" / "朋友圈"
SHOT = ROOT / "docs" / "images" / "readme-single-frame.png"
QR = Path(os.environ.get("TEMP", "/tmp")) / "ptb_qr.png"

REPO_TEXT = "South_Network_Protocol_Analysis_Tool"
REPO_URL = "https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool"

# ── 配色（与 og-social.png 同源）────────────────────────────────────────
C_BG_TOP = QColor("#07131F")
C_BG_BOT = QColor("#0B2536")
C_TITLE = QColor("#FFFFFF")
C_SUB = QColor("#A9C0D0")
C_MUTED = QColor("#8FA7B8")
C_CHIP_LINE = QColor("#2E6C8C")
C_CHIP_TEXT = QColor("#CFE8F5")
C_ORANGE = QColor("#F5A623")
C_YELLOW = QColor("#FFC24B")
C_CYAN = QColor("#7FD4F0")
C_OK = QColor("#57D0A0")

FONT_FAMILY = "Microsoft YaHei UI"


def _font(size: int, bold: bool = False) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setPixelSize(size)
    f.setBold(bold)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def _rounded(p: QPainter, rect: QRectF, radius: float, fill: QColor | None = None,
             border: QColor | None = None, border_w: float = 1.0) -> None:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    if fill is not None:
        p.fillPath(path, fill)
    if border is not None:
        p.setPen(QPen(border, border_w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


def draw_background(p: QPainter, w: int, h: int) -> None:
    grad = QLinearGradient(0, 0, w * 0.35, h)
    grad.setColorAt(0.0, C_BG_TOP)
    grad.setColorAt(1.0, C_BG_BOT)
    p.fillRect(0, 0, w, h, grad)

    # 左上冷光
    glow = QRadialGradient(QPointF(w * 0.12, h * 0.02), w * 0.75)
    glow.setColorAt(0.0, QColor(52, 152, 219, 46))
    glow.setColorAt(1.0, QColor(52, 152, 219, 0))
    p.fillRect(0, 0, w, int(h * 0.55), glow)

    # 右下暖光
    glow2 = QRadialGradient(QPointF(w * 0.95, h * 0.92), w * 0.5)
    glow2.setColorAt(0.0, QColor(245, 166, 35, 26))
    glow2.setColorAt(1.0, QColor(245, 166, 35, 0))
    p.fillRect(0, int(h * 0.55), w, int(h * 0.45), glow2)

    # 细网格
    p.setPen(QPen(QColor(255, 255, 255, 9), 1))
    step = 60
    for x in range(0, w, step):
        p.drawLine(x, 0, x, h)
    for y in range(0, h, step):
        p.drawLine(0, y, w, y)


def draw_logo(p: QPainter, x: float, y: float, size: float) -> float:
    rect = QRectF(x, y, size, size)
    _rounded(p, rect, size * 0.22, fill=QColor("#0F3350"),
             border=QColor("#2C6E8F"), border_w=2.0)
    # 顶部橙色条
    bar = QPainterPath()
    bar.addRoundedRect(QRectF(x + size * 0.22, y + size * 0.16, size * 0.56, size * 0.09),
                       size * 0.05, size * 0.05)
    p.fillPath(bar, C_ORANGE)
    p.setFont(_font(int(size * 0.36), bold=True))
    p.setPen(C_TITLE)
    p.drawText(QRectF(x, y + size * 0.28, size, size * 0.55),
               Qt.AlignmentFlag.AlignCenter, "南解")
    return x + size


def draw_chips(p: QPainter, x: float, y: float, max_w: float,
               items: list[str], font_size: int = 26, gap: float = 14,
               line_gap: float = 14) -> float:
    p.setFont(_font(font_size))
    fm = p.fontMetrics()
    cx, cy = x, y
    h = font_size + 26
    for text in items:
        w = fm.horizontalAdvance(text) + 44
        if cx + w > x + max_w:
            cx = x
            cy += h + line_gap
        rect = QRectF(cx, cy, w, h)
        _rounded(p, rect, h / 2, fill=QColor(28, 74, 102, 120), border=C_CHIP_LINE, border_w=1.4)
        p.setPen(C_CHIP_TEXT)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        cx += w + gap
    return cy + h


def draw_stats(p: QPainter, x: float, y: float, width: float, items: list[tuple[str, str]]) -> None:
    col_w = width / len(items)
    for i, (value, label) in enumerate(items):
        cx = x + col_w * i
        p.setFont(_font(46, bold=True))
        p.setPen(C_YELLOW)
        p.drawText(QRectF(cx, y, col_w, 56), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
        p.setFont(_font(22))
        p.setPen(C_MUTED)
        p.drawText(QRectF(cx, y + 54, col_w, 30), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)


def draw_shot(p: QPainter, x: float, y: float, w: float, h: float) -> None:
    if not SHOT.exists():
        return
    img = QImage(str(SHOT))
    if img.isNull():
        return
    # 阴影
    for i, alpha in enumerate((26, 18, 10)):
        _rounded(p, QRectF(x - 6 - i * 4, y - 4 - i * 4, w + 12 + i * 8, h + 8 + i * 8),
                 18, fill=QColor(0, 0, 0, alpha))
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(x, y, w, h), 14, 14)
    p.save()
    p.setClipPath(clip)
    scaled = img.scaled(int(w), int(h), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
    p.drawImage(QPointF(x + (w - scaled.width()) / 2, y + (h - scaled.height()) / 2), scaled)
    p.restore()
    p.setPen(QPen(QColor(159, 211, 232, 150), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(clip)


def draw_features(p: QPainter, x: float, y: float, width: float, items: list[str],
                  cols: int = 2, font_size: int = 27) -> None:
    p.setFont(_font(font_size))
    col_w = width / cols
    row_h = font_size + 22
    for i, text in enumerate(items):
        cx = x + col_w * (i % cols)
        cy = y + row_h * (i // cols)
        p.setPen(C_OK)
        p.drawText(QRectF(cx, cy, 30, row_h), Qt.AlignmentFlag.AlignVCenter, "✓")
        p.setPen(QColor("#DCE9F2"))
        p.drawText(QRectF(cx + 34, cy, col_w - 34, row_h),
                   Qt.AlignmentFlag.AlignVCenter, text)


def draw_qr(p: QPainter, x: float, y: float, size: float) -> bool:
    if not QR.exists():
        return False
    img = QImage(str(QR))
    if img.isNull():
        return False
    _rounded(p, QRectF(x, y, size, size), 12, fill=QColor("#FFFFFF"))
    pad = 7
    p.drawImage(QRectF(x + pad, y + pad, size - pad * 2, size - pad * 2), img)
    return True


def make_tall(path: Path) -> None:
    w, h = 1080, 1440
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    draw_background(p, w, h)
    m = 64

    # 顶部：logo + 环境标签
    right = draw_logo(p, m, 56, 76)
    p.setFont(_font(25))
    p.setPen(QColor("#A9C0D0"))
    p.drawText(QRectF(right + 22, 58, w - right - 40, 40),
               Qt.AlignmentFlag.AlignVCenter, "Windows 免安装 · 双击即用 · 内网离线可用")
    p.setFont(_font(21))
    p.setPen(QColor("#6E8BA0"))
    p.drawText(QRectF(right + 22, 96, w - right - 40, 30),
               Qt.AlignmentFlag.AlignVCenter, "v1.23.88  ·  MIT 开源  ·  单文件 EXE")

    # 标题
    p.setFont(_font(76, bold=True))
    p.setPen(C_TITLE)
    p.drawText(QRectF(m, 168, w - m * 2, 88), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "电力通信报文解析工具")

    p.setFont(_font(34))
    p.setPen(C_SUB)
    p.drawText(QRectF(m, 260, w - m * 2, 48), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "把一串十六进制，变成逐字段讲清楚的一张表")

    # 协议胶囊（两行）
    draw_chips(p, m, 332, w - m * 2,
               ["南网 Q/CSG1209021", "国网 Q/GDW10376", "698.45", "DLT645-2007",
                "DLMS / HDLC", "HDC 1.0", "国网双模", "南网上行"],
               font_size=25, gap=14, line_gap=12)

    # 数据条
    draw_stats(p, m, 470, w - m * 2,
               [("15", "种协议"), ("20+", "功能模块"), ("190", "套自动化测试"), ("MIT", "开源协议")])

    # 截图（缩到 860 居中，给底部 CTA 留出空间）
    shot_w = 860
    shot_x = (w - shot_w) / 2
    shot_y = 590
    shot_h = shot_w / 1.856
    draw_shot(p, shot_x, shot_y, shot_w, shot_h)

    # 能力点（2 列 × 3 行）
    draw_features(p, m, 1072, w - m * 2,
                  ["逐字段解析 + 校验自证", "组帧/地址替换自动算校验",
                   "批量日志 → 摘要/详情/时序图", "698.45 逐包升级 + 版本判定",
                   "生产测试架：参数帧一键下发", "报文对比：字节级 / 字段级"])

    # 底部 CTA
    bar_y = 1238
    bar = QRectF(m, bar_y, w - m * 2, 122)
    _rounded(p, bar, 16, fill=QColor(255, 255, 255, 10), border=QColor(46, 108, 140, 150), border_w=1.2)

    qr_size = 92
    qr_x = w - m - 18 - qr_size
    if draw_qr(p, qr_x, bar_y + 6, qr_size):
        p.setFont(_font(16))
        p.setPen(C_MUTED)
        p.drawText(QRectF(qr_x - 22, bar_y + 100, qr_size + 44, 18),
                   Qt.AlignmentFlag.AlignCenter, "扫码看项目")
        text_w = qr_x - m - 44
    else:
        text_w = w - m * 2 - 40

    p.setFont(_font(26, bold=True))
    p.setPen(C_TITLE)
    p.drawText(QRectF(m + 22, bar_y + 22, text_w, 34), Qt.AlignmentFlag.AlignVCenter,
               "免费下载 · MIT 开源")
    p.setFont(_font(19))
    p.setPen(C_CYAN)
    p.drawText(QRectF(m + 22, bar_y + 64, text_w, 28), Qt.AlignmentFlag.AlignVCenter,
               "github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool")

    p.setFont(_font(19))
    p.setPen(QColor("#6E8BA0"))
    p.drawText(QRectF(m, 1384, w - m * 2, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "支持串口 / 蓝牙 / TCP 监控   ·   配置与日志全部留在本机")

    p.end()
    img.save(str(path))


def make_square(path: Path) -> None:
    w, h = 1080, 1080
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    draw_background(p, w, h)
    m = 60
    right = draw_logo(p, m, 44, 68)
    p.setFont(_font(23))
    p.setPen(QColor("#A9C0D0"))
    p.drawText(QRectF(right + 20, 46, w - right - 30, 34), Qt.AlignmentFlag.AlignVCenter,
               "Windows 免安装 · 离线可用 · MIT 开源")
    p.setFont(_font(19))
    p.setPen(QColor("#6E8BA0"))
    p.drawText(QRectF(right + 20, 80, w - right - 30, 26), Qt.AlignmentFlag.AlignVCenter,
               "v1.23.88  ·  单文件 EXE")

    p.setFont(_font(66, bold=True))
    p.setPen(C_TITLE)
    p.drawText(QRectF(m, 132, w - m * 2, 84), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "电力通信报文解析工具")
    p.setFont(_font(28))
    p.setPen(C_SUB)
    p.drawText(QRectF(m, 218, w - m * 2, 42), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "15 种协议 · 逐字段解析 · 组帧升级一站式")

    draw_chips(p, m, 282, w - m * 2,
               ["南网", "国网", "698.45", "DLT645", "DLMS/HDLC", "HDC 1.0"],
               font_size=23, gap=12)

    shot_w = 880
    shot_x = (w - shot_w) / 2
    shot_y = 356
    shot_h = shot_w / 1.856
    draw_shot(p, shot_x, shot_y, shot_w, shot_h)

    draw_features(p, m, 856, w - m * 2,
                  ["逐字段解析", "组帧算校验", "批量日志分析", "698.45 升级"],
                  cols=2, font_size=24)

    bar_y = 952
    bar = QRectF(m, bar_y, w - m * 2, 96)
    _rounded(p, bar, 14, fill=QColor(255, 255, 255, 10), border=QColor(46, 108, 140, 150), border_w=1.2)

    qr_size = 76
    qr_x = w - m - 14 - qr_size
    has_qr = draw_qr(p, qr_x, bar_y + 10, qr_size)
    text_w = (qr_x - m - 36) if has_qr else (w - m * 2 - 40)

    p.setFont(_font(22, bold=True))
    p.setPen(C_TITLE)
    p.drawText(QRectF(m + 20, bar_y + 12, text_w, 30), Qt.AlignmentFlag.AlignVCenter,
               "免费下载 · GitHub 开源")
    p.setFont(_font(17))
    p.setPen(C_CYAN)
    p.drawText(QRectF(m + 20, bar_y + 48, text_w, 26), Qt.AlignmentFlag.AlignVCenter,
               "github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool")

    p.end()
    img.save(str(path))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841  (QPainter 需要）
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    variant = ""
    if "--variant" in sys.argv:
        variant = sys.argv[sys.argv.index("--variant") + 1]

    if variant in ("", "tall"):
        out = OUT_DIR / "海报-朋友圈-1080x1440.png"
        make_tall(out)
        print(f"tall: {out}")
    if variant in ("", "square"):
        out = OUT_DIR / "海报-朋友圈-1080x1080.png"
        make_square(out)
        print(f"square: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
