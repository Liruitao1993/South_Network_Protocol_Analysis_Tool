# -*- coding: utf-8 -*-
"""协议10/11 应用层报文摘要「业务名 + 关键业务字段」回归测试
（任务 09-16-gw-app-summary-detail）

背景（用户现场反馈）：
  协议11（HDC 1.0）批量解析把级别选为「应用层报文(app)」时，摘要列只有
  `端口:18 | 报文:0x0030`——同一批 21 帧**摘要完全相同**（业务数据区的
  `开始升级 / 升级ID / 升级时间窗 / …` 全部没进摘要），扫读时无法区分。
  而两协议的字段分布**不同构**：协议11 业务名在「── 业务数据 ──」区头行
  （字段名自带），协议10 的业务名已作为「报文ID」解析值给出、业务字段与
  元数据平铺——故采用同一条兼容规则（元数据黑名单 + 业务名两优先级）。

覆盖：
  [1] 纯函数 `_gw_app_biz_summary`：两协议布局都提取 `("开始升级", [升级ID, 升级时间窗])`；
      只有元数据 / 未知业务 → 返回 ("", [])
  [2] 协议11 端到端摘要：精确文案（验收 1），且不再等于旧摘要
  [3] 可区分性：用户 20 行现场样本（app 级别、真实批量解析）→ 每条带正确分钟数，
      摘要种类数 == 不同分钟数种类数（旧实现下全部相同）
  [4] 协议10 端到端：含业务名与 2 个业务字段，业务名不重复出现
  [5] 元数据排除：安全模式/业务报文ID/报文控制字/协议版本号/报文头长度/数据长度 不入选
  [6] 回归：网络层帧摘要与改动前逐字符一致（不被注入业务字段）、空表/失败帧不变
  [7] 两端对拍（桌面 vs Web，协议10/11）+ `get_frame_summary` 协议10 走应用层专用分支
  [8] 真实 MPDU（auto/fc_pb/app 三级别，夹具 `test/hdc10_real_frames.pkl`）：关键字段
      **不得**混入 FC/MAC 头字段（`版本`/`原始源TEI`/`定界符类型`/`网络类型`…）——
      扫描窗口必须限定在应用层/业务数据段（全表扫描会被这些前置行占满关键字段位）

运行（必须带 -u；脚本末尾 os._exit() 不会 flush 缓冲的 stdout）：
    QT_QPA_PLATFORM=offscreen python -X utf8 -u test/test_gw_app_summary_detail.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pickle  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "reflex_web"))

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402
import gw_new_gen_parser  # noqa: E402
import hdc10_parser  # noqa: E402
import main_gui  # noqa: E402
from _batch_wait import wait_batch  # noqa: E402
from reflex_web import web_utils  # noqa: E402

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

_config_sandbox.install()

PASS = 0
FAILURES = []


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
# 样本与宿主
# ══════════════════════════════════════════════════════════════
FRAME_UPGRADE = "12300000010500003F30AE7B78009001972306005ECCEFB1"
# 现场 20 行样本（`升级时间窗` = 第 13 字节，即各帧唯一差异）
SAMPLE_WINDOWS = (
    0x78, 0x77, 0x77, 0x70, 0x70, 0x6F, 0x6E, 0x6D, 0x6B, 0x6A,
    0x67, 0x65, 0x64, 0x63, 0x62, 0x60, 0x5E, 0x5D, 0x5B, 0x59,
)
SAMPLE_LINES = "\n".join(
    "    Line {no}: 260916-112229-213: B1D[3] mrd:ar[24]:"
    "12300000010500003F30AE7B{win:02X}009001972306005ECCEFB1".format(no=no, win=win)
    for no, win in zip(
        (16068, 16218, 16373, 24212, 24381, 24545, 25546, 25707, 26493, 26820,
         28581, 29334, 29705, 30197, 30625, 31251, 31961, 32314, 33094, 34125),
        SAMPLE_WINDOWS,
    )
)

EXPECT_11 = (
    "端口:18 | 报文:0x0030 | 开始升级 | 升级ID:2075013183 | 升级时间窗:120分钟"
)
EXPECT_10 = (
    "端口:升级业务 | 报文:开始升级(下行) | 升级ID:2075013183 | 升级时间窗:120分钟"
)
OLD_11 = "端口:18 | 报文:0x0030"  # 改动前协议11 的摘要（现场痛点）
FC_ONLY_BASELINE = "NID:0 | SOF帧(数据帧) | 0→0"  # 改动前网络层摘要基线


class Host:
    """复用 MainWindow 未绑定方法（纯摘要逻辑，无需 GUI 驱动）。"""

    _get_gw_new_gen_summary = main_gui.MainWindow._get_gw_new_gen_summary
    _TEST_MODE_SENTINELS = main_gui.MainWindow._TEST_MODE_SENTINELS
    _extract_test_mode_content = main_gui.MainWindow._extract_test_mode_content


def app_table(protocol: int):
    """现场帧的 app 级别解析表（协议10 / 11）。"""
    parser = hdc10_parser.HDC10Parser() if protocol == 11 else gw_new_gen_parser.GWNewGenParser()
    return parser.parse_to_table(bytes.fromhex(FRAME_UPGRADE), parse_level="app")


def main():
    host = Host()
    table11, table10 = app_table(11), app_table(10)

    # ── [1] 纯函数 ──────────────────────────────────────────
    section("[1] 纯函数 _gw_app_biz_summary（两协议布局）")
    biz11, fields11 = main_gui._gw_app_biz_summary(table11)
    biz10, fields10 = main_gui._gw_app_biz_summary(table10)
    check("协议11 业务名（业务数据区头行）", biz11 == "开始升级", repr(biz11))
    check(
        "协议11 关键字段（升级ID/升级时间窗）",
        fields11 == ["升级ID:2075013183", "升级时间窗:120分钟"],
        repr(fields11),
    )
    check("协议10 业务名（报文ID 解析值）", biz10 == "开始升级", repr(biz10))
    check(
        "协议10 关键字段",
        fields10 == ["升级ID:2075013183", "升级时间窗:120分钟"],
        repr(fields10),
    )
    meta_only = [
        ("  报文端口号", "0x12", "18", "升级业务"),
        ("  安全模式", "0x0", "0", "明文传输"),
        ("  报文控制字", "0x00", "0", "控制字: 0x00"),
    ]
    check("只有元数据 → 无业务名无字段", main_gui._gw_app_biz_summary(meta_only) == ("", []))
    unknown = [
        ("── 业务数据 ──", "", "4字节", "报文ID: 0x099"),
        ("  保留业务", "", "4字节", "未定义"),
    ]
    check(
        "业务数据区无带缩进字段行 → 不误报（协议10 优先级②不适用 hex）",
        main_gui._gw_app_biz_summary(unknown)[1] == [],
        repr(main_gui._gw_app_biz_summary(unknown)),
    )
    check("空表 → ('', [])", main_gui._gw_app_biz_summary([]) == ("", []))

    # ── [2] 协议11 端到端 ───────────────────────────────────
    section("[2] 协议11 应用层摘要（验收 1）")
    got11 = host._get_gw_new_gen_summary(table11)
    check("精确文案", got11 == EXPECT_11, repr(got11))
    check("不再等于旧摘要（有可读业务信息）", got11 != OLD_11, repr(got11))

    # ── [3] 可区分性（真实批量解析） ────────────────────────
    section("[3] 用户 20 行现场样本：摘要按内容可区分")
    app = QApplication.instance() or QApplication(sys.argv or [])
    win = main_gui.MainWindow()
    idx11 = int(main_gui.protocol_registry.name_to_index("HDC 1.0"))
    win.protocol_combo.setCurrentIndex(idx11)
    win._hdc10_parse_level = "app"  # 截图里的现场设置
    win.batch_input.setPlainText(SAMPLE_LINES)
    win.parse_batch()
    check("批量解析已收尾（wait_batch）", wait_batch(win))
    check("提取到 20 帧", len(win.batch_results) == 20, str(len(win.batch_results)))
    summaries = [r.get("摘要", "") for r in win.batch_results]
    expect_windows = [f"升级时间窗:{w}分钟" for w in SAMPLE_WINDOWS]
    check(
        "每条摘要含各自正确的分钟数",
        all(exp in got for exp, got in zip(expect_windows, summaries)),
        str([(e, g) for e, g in zip(expect_windows, summaries) if e not in g][:2]),
    )
    check(
        "摘要种类数 == 不同分钟数种类数（旧实现下全部相同）",
        len(set(summaries)) == len(set(SAMPLE_WINDOWS)),
        f"{len(set(summaries))} vs {len(set(SAMPLE_WINDOWS))}",
    )
    check(
        "摘要不再全同（旧实现 20 条一模一样）",
        len(set(summaries)) > 1 and summaries[0] != OLD_11,
        repr(summaries[:2]),
    )
    check("每条含业务名与关键字段", all(
        "开始升级" in s and "升级ID:2075013183" in s for s in summaries
    ))

    # ── [4] 协议10 端到端 ───────────────────────────────────
    section("[4] 协议10 应用层摘要")
    got10 = host._get_gw_new_gen_summary(table10)
    check("精确文案", got10 == EXPECT_10, repr(got10))
    check("业务名不重复出现", got10.count("开始升级") == 1, repr(got10))

    # ── [5] 元数据排除 ──────────────────────────────────────
    section("[5] 元数据字段不得占业务字段位")
    for meta in ("安全模式:", "业务报文ID:", "报文控制字:"):
        check(f"协议11 摘要不含 {meta}", meta not in got11, repr(got11))
    for meta in ("安全机制:", "协议版本号:", "报文头长度:", "数据长度:", "控制/保留:"):
        check(f"协议10 摘要不含 {meta}", meta not in got10, repr(got10))

    # ── [6] 回归：网络层/空表/失败帧 ────────────────────────
    section("[6] 回归（网络层帧不被注入业务字段；有 MMTYPE 时摘要须带出）")
    fc = bytes.fromhex("09" + "00" * 15)
    rows_fc = gw_new_gen_parser.GWNewGenParser().parse_to_table(fc, parse_level="fc_only")
    got_fc = host._get_gw_new_gen_summary(rows_fc)
    check("协议10 fc_only 摘要与改动前逐字符一致", got_fc == FC_ONLY_BASELINE, repr(got_fc))
    check("网络层摘要未被注入业务字段", "升级" not in got_fc, repr(got_fc))
    # 网络层 MME 帧（1.23.29 起）：字段名协议11 为「消息类型(MMTYPE)」也须命中
    mme_rows = hdc10_parser.HDC10Parser().parse_to_table(
        bytes.fromhex(
            "C0"
            "00000100019673005C80FF0800960000"
            "200000000124010101010101"
            "000000002000000001240100000000000000000001030001"
            "329FBACA69DE640900000000A860CAF104A18A64E8F2"
            "0000040099F4484C3039000000000000000065F9"
            "0000000000000000000000000000000000000000000000000000"
            "688150C40000000000000000BA711E"
        ),
        parse_level="pb_only",
        frame_type=1,
    )
    got_mme = host._get_gw_new_gen_summary(mme_rows)
    check("协议11 pb_only 网络层帧摘要含 MMTYPE", "MMTYPE:" in got_mme and "关联请求" in got_mme,
          repr(got_mme))
    check("网络层 MME 摘要未被注入应用层业务字段", "端口:" not in got_mme, repr(got_mme))
    check("空表仍返回 '-'", host._get_gw_new_gen_summary([]) == "-")
    check(
        "失败帧仍返回失败原因",
        host._get_gw_new_gen_summary([("❌ 帧数据过短", "", "", "帧数据过短")]) == "帧数据过短",
    )

    win.close()
    app.processEvents()

    # ── [7] 两端对拍 + 分派修正 ─────────────────────────────
    section("[7] 桌面 / Web 对拍与协议10 分派修正")
    for proto, table in ((11, table11), (10, table10)):
        desktop = host._get_gw_new_gen_summary(table)
        web = web_utils.get_hdc10_summary(table)
        check(f"协议{proto} 摘要逐字符一致", desktop == web, f"{desktop!r} != {web!r}")
    check(
        "get_frame_summary(协议10) == get_hdc10_summary",
        web_utils.get_frame_summary(table10, 10) == web_utils.get_hdc10_summary(table10),
    )
    check(
        "get_frame_summary(协议10) != 协议9 摘要函数（分派修正）",
        web_utils.get_frame_summary(table10, 10)
        != web_utils.get_csg_new_gen_summary(table10),
    )
    check(
        "get_frame_summary(协议9) 仍走协议9 摘要函数",
        web_utils.get_frame_summary(table10, 9)
        == web_utils.get_csg_new_gen_summary(table10),
    )
    check(
        "Web 协议11 摘要文案",
        web_utils.get_hdc10_summary(table11) == EXPECT_11,
        repr(web_utils.get_hdc10_summary(table11)),
    )

    # ── [8] 真实 MPDU：扫描窗口限定（防网络层字段冒充业务字段） ──
    section("[8] 真实报文 auto/fc_pb/app：关键字段不得混入 FC/MAC 头字段")
    net_fields = (
        "版本", "原始源TEI", "原始目的TEI", "定界符类型", "网络类型",
        "MSDU序列号", "发送类型", "MSDU类型", "网络标识",
    )
    with open(ROOT / "test" / "hdc10_real_frames.pkl", "rb") as fp:
        real_frames = pickle.load(fp)
    parsed_cache = []
    app_tables = 0
    for proto, parser in (
        (11, hdc10_parser.HDC10Parser()),
        (10, gw_new_gen_parser.GWNewGenParser()),
    ):
        for level in ("auto", "fc_pb", "app"):
            for fi, fbytes, _key in real_frames:
                try:
                    rows = parser.parse_to_table(fbytes, parse_level=level)
                except Exception:
                    continue
                names = {str(r[0]).strip() for r in rows}
                if not ({"报文端口号", "报文ID"} & names):
                    continue  # 无应用层 → 不适用业务段
                app_tables += 1
                parsed_cache.append((proto, level, fi, rows))
    check("夹具中存在带应用层的 MPDU 表", app_tables > 0, str(app_tables))
    desktop_polluted, web_polluted = [], []
    for proto, level, fi, rows in parsed_cache:
        for bucket, func in (
            (desktop_polluted, main_gui._gw_app_biz_summary),
            (web_polluted, web_utils._gw_app_biz_summary),
        ):
            bad = [f for f in func(rows)[1] if f.split(":")[0] in net_fields]
            if bad:
                bucket.append((proto, level, fi, bad))
    check("桌面：真实帧关键字段不含网络层字段", not desktop_polluted, str(desktop_polluted[:2]))
    check("Web：真实帧关键字段不含网络层字段", not web_polluted, str(web_polluted[:2]))
    check(
        "真实帧的现场同型帧（协议11/auto）仍解析出业务名",
        all(
            main_gui._gw_app_biz_summary(rows)[0]
            for p, lv, _fi, rows in parsed_cache
            if p == 11 and lv == "auto"
        ),
        str(
            [
                main_gui._gw_app_biz_summary(rows)[0]
                for p, lv, _fi, rows in parsed_cache
                if p == 11 and lv == "auto"
            ]
        ),
    )
    # 关键字段可以为空（如「通信测试报文」业务数据区只有元数据行），
    # 但只要非空就必须来自应用层段（已由上两条断言钉住）

    # ── [9] Web 协议10 非应用层表不退化（仍走协议9 摘要函数） ──
    section("[9] Web 协议10 网络层帧保持既有摘要路径（不退化）")
    net_tables = [
        rows
        for proto, _lv, _fi, rows in parsed_cache
        if proto == 10
    ]
    # 构造纯网络层表（真实夹具里 fc_only 输入）
    fc_only_tables = []
    for _fi, fbytes, _key in real_frames[:20]:
        try:
            rows = gw_new_gen_parser.GWNewGenParser().parse_to_table(
                fbytes, parse_level="fc_only"
            )
        except Exception:
            continue
        names = {str(r[0]).strip() for r in rows}
        if not ({"报文端口号", "报文ID"} & names):
            fc_only_tables.append(rows)
    check("构造出协议10 非应用层表", bool(fc_only_tables), str(len(fc_only_tables)))
    check(
        "协议10 网络层帧摘要 == 协议9 摘要函数（即未被切到 hdc10 实现）",
        all(
            web_utils.get_frame_summary(rows, 10) == web_utils.get_csg_new_gen_summary(rows)
            for rows in fc_only_tables
        ),
        "存在被切走的表",
    )
    check(
        "协议10 应用层帧摘要 != 协议9 摘要函数（走增强实现）",
        web_utils.get_frame_summary(table10, 10) != web_utils.get_csg_new_gen_summary(table10),
    )
    _ = net_tables

    print(f"\n结果：PASS={PASS}  FAIL={len(FAILURES)}")
    for name in FAILURES:
        print(f"  - {name}")
    return 0 if not FAILURES else 1


code = main()
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
