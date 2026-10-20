"""生成 GitHub 社交预览图（1280x640）docs/images/og-social.png

布局：# 图标 + 标题 + 一句话 + 协议标签 + 数据带；底部一条**放大**的真实解析表格横带
（社交卡片缩略后仍能看清「字段 / 原始值 / 解析值」），避免整窗截图缩到卡片里变成糊字。

用途：仓库 Settings → Social preview 上传，以及知乎/公众号/分享卡片的头图。
运行：python tools/gen_og_image.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images" / "og-social.png"
SHOT = ROOT / "docs" / "images" / "readme-single-frame.png"
ICON = ROOT / "app_icon.ico"

W, H = 1280, 640

BG_TOP = (9, 20, 34)
BG_BOTTOM = (17, 41, 63)
ACCENT = (64, 196, 255)
ACCENT2 = (255, 176, 32)
TEXT = (238, 245, 252)
MUTED = (148, 170, 192)

BOLD = "C:/Windows/Fonts/msyhbd.ttc"
REG = "C:/Windows/Fonts/msyh.ttc"


def vertical_gradient(w: int, h: int) -> Image.Image:
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(round(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
    return strip.resize((w, h), Image.BILINEAR)


def paste_shot_band(base: Image.Image, box: tuple[int, int, int, int], radius: int = 14) -> None:
    """底部解析表格横带：裁掉工具栏/输入区，只留字段表格，放大填满。"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    shot = Image.open(SHOT).convert("RGB")
    # 只保留解析结果表格（字段 / 原始值 / 解析值），去掉顶部工具栏与输入框
    shot = shot.crop((24, 348, shot.width - 8, 726))

    scale = max(w / shot.width, h / shot.height)
    shot = shot.resize((round(shot.width * scale), round(shot.height * scale)), Image.LANCZOS)
    left = max(0, (shot.width - w) // 2)
    shot = shot.crop((left, 0, left + w, h))

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)

    shadow = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((40, 34, w + 40, h + 34), radius=radius, fill=(0, 0, 0, 165))
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    base.paste(shadow, (x0 - 40, y0 - 34), shadow)

    base.paste(shot, (x0, y0), mask)

    border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, outline=(96, 138, 174, 235), width=2)
    base.paste(border, (x0, y0), border)


def chips(draw: ImageDraw.ImageDraw, items: list[str], x: int, y: int, f: ImageFont.FreeTypeFont) -> None:
    cx = x
    for text in items:
        tw = draw.textlength(text, font=f)
        pad_x, pad_y = 14, 6
        box = (cx, y, cx + tw + pad_x * 2, y + f.size + pad_y * 2 + 6)
        draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=(27, 57, 85), outline=(52, 96, 130), width=1)
        draw.text((cx + pad_x, y + pad_y + 3), text, font=f, fill=(188, 215, 236))
        cx = box[2] + 10


def main() -> None:
    img = vertical_gradient(W, H)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((760, -260, 1460, 300), fill=(64, 196, 255, 38))
    gd.ellipse((-200, 300, 420, 780), fill=(255, 176, 32, 22))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    img.paste(glow, (0, 0), glow)

    draw = ImageDraw.Draw(img)

    if ICON.exists():
        icon = Image.open(ICON).resize((68, 68), Image.LANCZOS).convert("RGBA")
        img.paste(icon, (72, 44), icon)
        draw = ImageDraw.Draw(img)

    draw.text((156, 52), "Windows 免安装 · 双击即用 · 离线可用", font=font(REG, 21), fill=ACCENT)
    draw.text((72, 126), "电力通信报文解析工具", font=font(BOLD, 60), fill=TEXT)
    draw.text(
        (72, 202),
        "把一串十六进制，变成逐字段讲清楚的一张表",
        font=font(REG, 27),
        fill=(198, 218, 234),
    )

    chips(draw, ["南网", "国网", "698.45", "DLT645", "DLMS/HDLC", "新一代载波"], 72, 250, font(REG, 20))

    # 数据带
    f_stat, f_stat_label = font(BOLD, 27), font(REG, 19)
    sx = 74
    for value, label in [("15", "种协议"), ("20+", "功能模块"), ("MIT", "开源协议"), ("exe", "免安装")]:
        draw.text((sx, 300), value, font=f_stat, fill=ACCENT2)
        vw = draw.textlength(value, font=f_stat)
        draw.text((sx + vw + 7, 310), label, font=f_stat_label, fill=MUTED)
        sx += vw + 7 + draw.textlength(label, font=f_stat_label) + 38

    paste_shot_band(img, (64, 360, 1216, 612), radius=14)

    draw.rectangle((0, H - 5, W, H), fill=ACCENT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"written: {OUT} ({OUT.stat().st_size} bytes)")


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


if __name__ == "__main__":
    main()
