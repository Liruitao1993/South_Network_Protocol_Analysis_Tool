"""重新抓取 README 用的真实界面截图（中文正常渲染）。

背景：仓库里原有的 docs/images/readme-*.png 中文全部渲染成方块（□），
说明它们不是从真实运行的界面截出来的。本脚本直接构造 MainWindow、
灌入**真实生成的合法报文**、调用真实解析逻辑，再用 QWidget.grab() 存图。

用法：
    python tools/capture_readme_shots.py           # 抓全部
    python tools/capture_readme_shots.py single    # 只抓单帧解析
    python tools/capture_readme_shots.py batch     # 只抓批量解析

产物：docs/images/_shot_single.png / _shot_batch.png（前缀 = 待人工挑选）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT))

from dl_t698_45_frame_gen import DLT69845FrameGenerator  # noqa: E402

_GEN = DLT69845FrameGenerator()
# SA = 地址特征 0x01(单地址,长度2) + 2 字节地址；CA 1 字节
_SA = bytes([0x01, 0x00, 0x01])


def _get_frame(oad: bytes, piid: int) -> str:
    """用仓库自带组帧器生成一帧合法的 698.45 GET-Request（HCS/FCS 均由它计算）。"""
    raw = _GEN.generate_get_request_normal(_SA, ca=0x17, piid=piid, oad=oad, time_tag_none=True)
    return raw.hex(" ").upper()


SINGLE_FRAME = _get_frame(bytes([0x20, 0x0F, 0x02, 0x00]), 0x60)  # 读「日期时间」类
BATCH_FRAMES = [
    _get_frame(bytes([0x20, 0x0F, 0x02, 0x00]), 0x60),
    _get_frame(bytes([0x20, 0x0F, 0x03, 0x00]), 0x61),
    _get_frame(bytes([0x40, 0x00, 0x02, 0x01]), 0x62),
]
BATCH_LOG = "\n".join(BATCH_FRAMES)


def _pump(app, n: int = 8) -> None:
    for _ in range(n):
        app.processEvents()


def _trim_bottom(path: Path, margin: int = 26) -> None:
    """裁掉底部整片背景空白，让截图更紧凑。"""
    from PIL import Image

    im = Image.open(path).convert("RGB")
    w, h = im.size
    bg = im.getpixel((w // 2, h - 3))

    last = h - 1
    while last > 0:
        row = im.crop((0, last, w, last + 1)).getdata()
        if any(abs(px[0] - bg[0]) + abs(px[1] - bg[1]) + abs(px[2] - bg[2]) > 12 for px in row):
            break
        last -= 1

    new_h = min(h, last + 1 + margin)
    if new_h < h - 4:
        im.crop((0, 0, w, new_h)).save(path)
        print(f"[trim] {path.name}: {h} -> {new_h}")


def _crop_bottom(path: Path, keep_h: int | None = None) -> None:
    """按指定高度裁掉底部（状态栏 + 空白区）。keep_h=None 时自动探测。"""
    if keep_h is None:
        _trim_bottom(path)
        return

    from PIL import Image

    im = Image.open(path).convert("RGB")
    w, h = im.size
    if keep_h < h:
        im.crop((0, 0, w, keep_h)).save(path)
        print(f"[crop] {path.name}: {h} -> {keep_h}")


def _shoot_single(app, MainWindow, path: Path, size=(1560, 940)) -> None:
    win = MainWindow()
    win.resize(*size)
    win.show()
    _pump(app, 20)

    win.protocol_combo.setCurrentIndex(8)  # 8 = 698.45
    _pump(app)

    win.single_input.setPlainText(SINGLE_FRAME)
    _pump(app)

    win.parse_single()
    _pump(app, 14)

    # 校验结果面板默认是收缩空态，留着只是一块空框 —— 抓图时隐藏，图更紧凑
    group = getattr(win, "verify_group", None)
    if group is not None:
        group.setVisible(False)
        _pump(app, 4)

    win.grab().save(str(path))
    print(f"written: {path}\n  frame: {SINGLE_FRAME}")
    win.close()
    win.deleteLater()
    _pump(app)
    _crop_bottom(path, keep_h=776)  # 表格末行（结束符）下方留白 + 去掉状态栏


def _shoot_batch(app, MainWindow, path: Path, size=(1560, 940)) -> None:
    win = MainWindow()
    win.resize(*size)
    win.show()
    _pump(app, 20)

    win.protocol_combo.setCurrentIndex(8)
    _pump(app)

    for i in range(win.tab_widget.count()):
        if "批量" in win.tab_widget.tabText(i):
            win.tab_widget.setCurrentIndex(i)
            break
    _pump(app, 12)

    win.batch_input.setPlainText(BATCH_LOG)
    _pump(app)

    win.batch_parse_btn.click()
    _pump(app, 40)

    # 选中第 1 行，让右侧「选中帧详细解析」有内容
    try:
        for name in ("batch_summary_table", "batch_table", "summary_table"):
            table = getattr(win, name, None)
            if table is not None and table.rowCount() > 0:
                table.selectRow(0)
                print(f"[batch] selected row 0 in {name}")
                break
    except Exception as exc:
        print(f"[warn] select row skipped: {exc}")
    _pump(app, 20)

    win.grab().save(str(path))
    print(f"written: {path}")
    win.close()
    win.deleteLater()
    _pump(app)
    _trim_bottom(path)


def main(argv: list[str]) -> int:
    from PySide6.QtWidgets import QApplication

    import main_gui

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])

    which = argv[1] if len(argv) > 1 else "all"

    if which in ("all", "single"):
        _shoot_single(app, main_gui.MainWindow, OUT_DIR / "_shot_single.png")
    if which in ("all", "batch"):
        _shoot_batch(app, main_gui.MainWindow, OUT_DIR / "_shot_batch.png")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
