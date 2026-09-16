# -*- coding: utf-8 -*-
"""HDC 1.0（协议11）批量解析前缀剥离级别来源与 app 端口判据回归测试
（任务 09-16-hdc10-batch-strip-level）

背景（现场缺陷）：
  协议11 的解析级别存 `_hdc10_parse_level`、协议10 存 `_gw_parse_level`（两个属性
  相互独立，但界面共用同一个下拉框 `gw_parse_level_combo`）。`_strip_gw_new_gen_prefix`
  早期**硬读** `_gw_parse_level`，于是只要曾在协议10 下选过「应用层报文(app)」，
  切到协议11 后界面显示「自动识别」、批量解析却按 app 过滤 —— 现场样本帧
  （`1230…`，端口 0x12 升级业务）里没有偶字节 `11`，被整批丢弃，弹
  「预处理后未保留有效报文内容！」。同时 app 判据只认端口 `11`，即便级别传对也
  会丢掉 0x12/0x1A 的应用层帧。

覆盖：
  [1] 纯函数矩阵 ── auto 保留全部行；app 保留端口 11/12（丢弃 FC 起始帧）；pb_only 原样
  [2] 级别来源 ── 协议11 下 `_gw_parse_level='app'` 残留不再影响；协议10 下
      `_hdc10_parse_level` 也不影响协议10（两向隔离）
  [3] 端口集合来源 ── 取自解析器端口表（hdc10_parser.APP_PORTS /
      gw_new_gen_parser.PORT_NAMES），且必须包含 0x12（防退回「只认 11」）
  [4] 两端对拍 ── 桌面 `_strip_gw_new_gen_prefix` 与 Web
      `web_utils.strip_gw_new_gen_prefix` 在 协议10/11 × auto/app 下逐字符一致
  [5] 端到端（核心验收）── 用户 20 行真实日志样本：协议11 + `_gw_parse_level='app'`
      残留 → 20 帧、全部「成功」、摘要含 0x0030，且**不弹**空内容警告（修复前必红）
  [6] 协议10 回归 ── 同样本在协议10 下仍 20 帧全成功
  [7] 非 app 级别不变 ── auto / pb_only 输出与修复前逐字符一致
  [8] 沙箱自检 ── 全程未改写真实 config.json

运行（必须带 -u：脚本末尾 os._exit() 不会 flush 缓冲的 stdout）：
    QT_QPA_PLATFORM=offscreen python -u test/test_hdc10_batch_strip_level.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import hashlib  # noqa: E402
import pathlib  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

# 构造 MainWindow 之前屏蔽模态框并留痕（offscreen 下模态框会永久阻塞）
DIALOGS = []
for _name in ("warning", "information", "critical", "question"):
    patch.object(
        QMessageBox,
        _name,
        lambda *a, _n=_name, **k: (
            DIALOGS.append((_n, str(a[2]) if len(a) > 2 else "")),
            0,
        )[1],
    ).start()

import app_paths  # noqa: E402
import gw_new_gen_parser  # noqa: E402
import hdc10_parser  # noqa: E402
import main_gui  # noqa: E402
from _batch_wait import wait_batch  # noqa: E402
from reflex_web import web_utils  # noqa: E402

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

PASS = 0
FAILURES = []

# 沙箱接管前的真实 data_path 引用（供 [8] 读真实 config.json 做摘要对比）
_REAL_APP_DATA_PATH = app_paths.data_path
_REAL_GUI_DATA_PATH = main_gui.data_path


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


def section(title):
    print(f"\n--- {title} ---")


# ══════════════════════════════════════════════════════════════
# 样本（现场日志，含搜索结果行号前缀与 4 空格缩进）
# ══════════════════════════════════════════════════════════════
LINE_UPGRADE = (
    "    Line 16068: 260916-112229-213: B1D[3] mrd:ar[24]:"
    "12300000010500003F30AE7B78009001972306005ECCEFB1"
)
FRAME_UPGRADE = "12300000010500003F30AE7B78009001972306005ECCEFB1"
LINE_NORMAL = "260804-192442-570: B1D[3] mrd:ar[17]:110101000260F001000005000200010002"
FRAME_NORMAL = "110101000260F001000005000200010002"
LINE_FC = "260718-111145-349: B1D[3] mrd:ar[8]:09630F0100000000"

MIXED_TEXT = "\n".join((LINE_UPGRADE, LINE_NORMAL, LINE_FC))
MIXED_AUTO = "\n".join((FRAME_UPGRADE, FRAME_NORMAL, "09630F0100000000"))

# 用户现场 20 行（除时间窗字节外内容一致），行号与现场一致
SAMPLE_LINES = "\n".join(
    "    Line {no}: 260916-112229-213: B1D[3] mrd:ar[24]:"
    "12300000010500003F30AE7B{win:02X}009001972306005ECCEFB1".format(no=no, win=win)
    for no, win in (
        (16068, 0x78), (16218, 0x77), (16373, 0x77), (24212, 0x70), (24381, 0x70),
        (24545, 0x6F), (25546, 0x6E), (25707, 0x6D), (26493, 0x6B), (26820, 0x6A),
        (28581, 0x67), (29334, 0x65), (29705, 0x64), (30197, 0x63), (30625, 0x62),
        (31251, 0x60), (31961, 0x5E), (32314, 0x5D), (33094, 0x5B), (34125, 0x59),
    )
)


class Sandbox:
    """config.json 沙箱：把 app_paths.data_path / main_gui.data_path 指到临时目录。

    MainWindow 关闭时会写出窗口/分栏/列宽状态，测试必须全程隔离，避免污染
    开发机的真实 config.json（AGENTS §8 陷阱 42：两处 data_path 都要 patch）。
    """

    def __init__(self):
        self.tmp = ""
        self._real_app = None
        self._real_gui = None

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="nw_hdc10_strip_")
        self._real_app = app_paths.data_path
        self._real_gui = main_gui.data_path

        def _data_path(name):
            return pathlib.Path(os.path.join(self.tmp, name))

        app_paths.data_path = _data_path
        main_gui.data_path = _data_path
        return self

    def __exit__(self, *exc):
        app_paths.data_path = self._real_app
        main_gui.data_path = self._real_gui
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def file_digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "<missing>"


def main():
    real_config = _REAL_APP_DATA_PATH("config.json")
    digest_before = file_digest(real_config)

    app = QApplication.instance() or QApplication(sys.argv or [])
    win = main_gui.MainWindow()
    idx11 = int(main_gui.protocol_registry.name_to_index("HDC 1.0"))
    idx10 = int(main_gui.protocol_registry.name_to_index("国网新一代"))

    # ── [1] 纯函数矩阵 ─────────────────────────────────────────
    section("[1] 纯函数矩阵（_strip_gw_new_gen_prefix）")
    win.protocol_combo.setCurrentIndex(idx11)
    auto_out = win._strip_gw_new_gen_prefix(MIXED_TEXT, "auto")
    check("auto 保留全部行（12/11/09 起始）", auto_out == MIXED_AUTO, repr(auto_out))
    app_out = win._strip_gw_new_gen_prefix(MIXED_TEXT, "app")
    check(
        "app 保留端口 11/12 起始帧",
        app_out == "\n".join((FRAME_UPGRADE, FRAME_NORMAL)),
        repr(app_out),
    )
    check("app 仍丢弃非应用层起始帧（09 起始 FC）", "09630F" not in app_out, repr(app_out))
    pb_out = win._strip_gw_new_gen_prefix(MIXED_TEXT, "pb_only")
    check("pb_only 原样保留（非 app 级别不做端口截断）", pb_out == MIXED_AUTO, repr(pb_out))

    # ── [2] 级别来源（两向隔离） ───────────────────────────────
    section("[2] 级别来源：协议10/11 互不串味")
    win.protocol_combo.setCurrentIndex(idx11)
    win._gw_parse_level = "app"  # 协议10 残留（缺陷触发点）
    win._hdc10_parse_level = "auto"
    check(
        "协议11：协议10 残留 app 不再影响（= auto 结果）",
        win._strip_gw_new_gen_prefix(MIXED_TEXT) == MIXED_AUTO,
        repr(win._strip_gw_new_gen_prefix(MIXED_TEXT)),
    )
    win._hdc10_parse_level = "app"
    check(
        "协议11：显式 app 级别生效（12/11 保留、FC 丢弃）",
        win._strip_gw_new_gen_prefix(MIXED_TEXT) == "\n".join((FRAME_UPGRADE, FRAME_NORMAL)),
        repr(win._strip_gw_new_gen_prefix(MIXED_TEXT)),
    )
    win._hdc10_parse_level = "auto"

    win.protocol_combo.setCurrentIndex(idx10)
    win._gw_parse_level = "auto"
    win._hdc10_parse_level = "app"  # 协议11 残留
    check(
        "协议10：协议11 残留 app 不影响（= auto 结果）",
        win._strip_gw_new_gen_prefix(MIXED_TEXT) == MIXED_AUTO,
        repr(win._strip_gw_new_gen_prefix(MIXED_TEXT)),
    )
    win._gw_parse_level = "app"
    check(
        "协议10：显式 app 级别生效",
        win._strip_gw_new_gen_prefix(MIXED_TEXT) == "\n".join((FRAME_UPGRADE, FRAME_NORMAL)),
        repr(win._strip_gw_new_gen_prefix(MIXED_TEXT)),
    )
    win._gw_parse_level = "auto"

    # ── [3] 端口集合取自解析器端口表 ───────────────────────────
    section("[3] app 端口集合来源（解析器端口表，单一来源）")
    want11 = tuple(f"{p:02X}" for p in hdc10_parser.APP_PORTS)
    want10 = tuple(f"{p:02X}" for p in gw_new_gen_parser.GWNewGenParser.PORT_NAMES)
    got11 = main_gui._gw_app_port_prefixes(11)
    got10 = main_gui._gw_app_port_prefixes(10)
    check("协议11 集合 == hdc10_parser.APP_PORTS", got11 == want11, f"{got11} != {want11}")
    check("协议10 集合 == gw_new_gen_parser.GWNewGenParser.PORT_NAMES", got10 == want10, f"{got10} != {want10}")
    check("集合含 0x12 升级业务（防退回只认 11）", "12" in got11 and "12" in got10, str(got11))
    check("集合含 0x1A 鉴权安全", "1A" in got11, str(got11))
    check("集合含 0x11 普通业务", "11" in got11, str(got11))

    # ── [4] 两端对拍 ───────────────────────────────────────────
    section("[4] 桌面 / Web 两端对拍")
    check("Web 端口集合与桌面一致", web_utils.gw_app_port_prefixes(11) == got11)
    same_all = True
    for proto in (10, 11):
        for level in ("auto", "app", "pb_only", "fc_only"):
            win.protocol_combo.setCurrentIndex(proto)
            d = win._strip_gw_new_gen_prefix(MIXED_TEXT, level)
            w = web_utils.strip_gw_new_gen_prefix(MIXED_TEXT, level, proto)
            if d != w:
                same_all = False
                print(f"      [diff] 协议{proto} {level}: 桌面={d!r} Web={w!r}")
    check("协议10/11 × auto/app/pb_only/fc_only 输出逐字符一致", same_all)

    # ── [5] 端到端（核心验收） ─────────────────────────────────
    section("[5] 端到端：协议11 批量解析 20 行现场样本")
    win.protocol_combo.setCurrentIndex(idx11)
    win._gw_parse_level = "app"  # 现场残留值（协议10 的）
    win._hdc10_parse_level = "auto"
    win.batch_input.setPlainText(SAMPLE_LINES)
    DIALOGS.clear()
    win.parse_batch()
    finished = wait_batch(win)
    check("批量解析已收尾（wait_batch）", finished)
    check("提取到 20 帧", len(win.batch_results) == 20, str(len(win.batch_results)))
    statuses = {r.get("_status") for r in win.batch_results}
    check("全部帧状态『成功』", statuses == {"成功"}, str(statuses))
    check(
        "未弹「预处理后未保留有效报文内容」",
        not any("未保留有效报文内容" in text for _, text in DIALOGS),
        str(DIALOGS),
    )
    if win.batch_results:
        first = win.batch_results[0]
        check("帧类型含 [11]", "[11]" in str(first.get("_type_name")), str(first.get("_type_name")))
        check("摘要含 0x0030（开始升级）", "0x0030" in str(first.get("摘要")), str(first.get("摘要")))
        detail = win._get_frame_table_data(0) or []
        check("首帧详情表非空", len(detail) > 0, str(len(detail)))
    else:
        check("帧类型含 [11]", False, "无结果")
        check("摘要含 0x0030（开始升级）", False, "无结果")
        check("首帧详情表非空", False, "无结果")

    # ── [6] 协议10 回归 ───────────────────────────────────────
    section("[6] 协议10 回归（同样本仍可用）")
    win.protocol_combo.setCurrentIndex(idx10)
    win._gw_parse_level = "auto"
    win.batch_input.setPlainText(SAMPLE_LINES)
    win.parse_batch()
    finished10 = wait_batch(win)
    check("协议10 批量解析收尾", finished10)
    check("协议10 提取到 20 帧", len(win.batch_results) == 20, str(len(win.batch_results)))
    check(
        "协议10 全部帧状态『成功』",
        {r.get("_status") for r in win.batch_results} == {"成功"},
        str({r.get("_status") for r in win.batch_results}),
    )

    # ── [7] 非 app 级别不变 ───────────────────────────────────
    section("[7] 非 app 级别行为不变（回归基线）")
    win.protocol_combo.setCurrentIndex(idx11)
    check(
        "auto 输出 = 三帧原文换行拼接（含 09 起始帧）",
        win._strip_gw_new_gen_prefix(MIXED_TEXT, "auto") == MIXED_AUTO,
    )
    check(
        "pb_only 不截断（输出同 auto）",
        win._strip_gw_new_gen_prefix(MIXED_TEXT, "pb_only") == MIXED_AUTO,
    )
    fc_only = win._strip_gw_new_gen_prefix(MIXED_TEXT, "fc_only")
    check("fc_only 同样不截断", fc_only == MIXED_AUTO, repr(fc_only))

    win.close()
    app.processEvents()

    # ── [8] 沙箱自检 ──────────────────────────────────────────
    section("[8] 沙箱自检：真实 config.json 未被改写")
    app_paths.data_path = _REAL_APP_DATA_PATH
    main_gui.data_path = _REAL_GUI_DATA_PATH
    digest_after = file_digest(real_config)
    check(
        "真实 config.json 摘要不变",
        digest_before == digest_after,
        f"{digest_before} -> {digest_after}",
    )

    print(f"\n结果：PASS={PASS}  FAIL={len(FAILURES)}")
    if FAILURES:
        for name in FAILURES:
            print(f"  - {name}")
    return 0 if not FAILURES else 1


with Sandbox():
    code = main()

sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
