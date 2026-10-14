# -*- coding: utf-8 -*-
"""协议13（依瓦定制645）**Web 端（Reflex）支持**回归测试 —— 任务 10-09-yiwa-645-protocol 阶段 5。

运行（本机 Windows console 默认 GBK，⚠/✓ 会 UnicodeEncodeError，必须 UTF-8）：
    pwshu '$env:PYTHONIOENCODING="utf-8"; python test/test_yw645_web.py'

覆盖（prd R7.1~R7.4 / AC12）
============================
1. **单源守卫（静态）**：`web_utils` 的帧提取是 `from yw645_wire import extract_yw645_frames`
   （对象同一性 + 无自定义 def + `extract_frames_for_protocol` 协议13 分支为单行委托）；
   查询数据源是 `from yw645_di import DI_TABLE`（无第二份手写清单）。
2. **提取互斥**：混合日志（南网/国网/645/698.45 + 依瓦）中协议13 只提取依瓦帧，
   且 `web_utils.extract_frames_for_protocol(..., 13)` == `yw645_wire.extract_yw645_frames`。
3. **摘要单一来源**：`get_frame_summary(rows, 13, frame_bytes)` == `YW645Parser.get_summary`。
4. **查询页 `di_yw645`**：列口径与桌面一致，数据 == `DI_TABLE` 程序化推导，关键词过滤生效。
5. **两端解析对拍（AC12）**：同一帧在桌面链路（`protocol_registry.build_gui_parser` +
   `parser_registry.get_parser`）与 Web 链路（Reflex `State.parse_frame`）解析，
   行数与每行 raw/parsed/comment 字段逐行一致。
6. **State 单帧 + 批量端到端**：协议13 可解析、摘要回落解析器单源、混合日志批量只留依瓦帧。
7. **组帧页可见提示（R7.4）**：协议13 时组帧页出现「Web 端暂不提供组帧」提示，不静默缺失。
8. **首页协议表交叉引用**：`landing_web.PROTOCOLS[13]` 与 `protocol_registry` 一致
   （逐行对拍由 `test/test_web_landing.py` 负责，这里只做交叉引用，不重复实现）。

说明
====
- Web 端**没有**协议12（模组化）支持，故协议下拉存在索引空洞（0~11 + 13）；
  `State.PROTOCOL_OPTIONS` 的标签解析按 `value` 查（不按位置索引）。
- Reflex 把非 ASCII 渲染成 `\\uXXXX`，凡断言中文文案前先 `unescape`（同 test_web_landing.py）。
"""

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

import asyncio  # noqa: E402
import inspect  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from reflex_web import landing_web as L  # noqa: E402
from reflex_web import lookup_utils, web_utils  # noqa: E402

from parser_registry import get_parser  # noqa: E402
from protocol_registry import build_gui_parser, protocol_count  # noqa: E402
from yw645_di import DI_TABLE  # noqa: E402
from yw645_parser import YW645Parser  # noqa: E402
from yw645_wire import extract_yw645_frames  # noqa: E402

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAILURES.append(name)
        print(f"  [FAIL] {name}  -- {detail}")


def section(title):
    print(f"\n== {title} ==")


def unescape(rendered: str) -> str:
    """Reflex 在 JSX 里把非 ASCII 转义成 `\\uXXXX`，中文断言前先解开。"""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), rendered)


# ── oracle：9 条文档示例（与 test_yw645_*.py 同源）──────────────────────
X1 = "68AAAAAAAAAAAA681004001000201016"
X2 = "6810300000001068200D00100101002006103000000010D516"
X3 = "680450000000136830023714B416"
X5 = "6810300000001068400E37146465666768696A6B6C6D636E9F16"
X9 = "681030000000106840023713AC16"
MIXED = [X2, X3, X5, X9]

# 其它 68 家族协议帧（互斥判据反例，取自既有示例，非本任务新增数据）
FRAME_NANWANG = "680E00000000010001E80005EF16"      # 南网：byte7 = 0x00
FRAME_GUOWANG = "680F0043000000000000000301004816"  # 国网：byte7 = 0x00
FRAME_DLT645 = "68AAAAAAAAAAAA68110433333333AD16"   # 645：byte7 = 0x68（最接近形态）
FRAME_69845 = "680E004101070809AEC60100000000348716"  # 698.45：无第二个 68H


def _import_app():
    """导入 Reflex 应用模块（未安装 reflex 时返回 None）。"""
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return None
    return app


# ═══════════════════════════════════════════════════════════════
# 1. 单源守卫（静态）
# ═══════════════════════════════════════════════════════════════

def test_single_source():
    section("1. 单源守卫（静态）")
    src = inspect.getsource(web_utils)

    check(
        "web_utils 从 yw645_wire import 提取器（非复刻）",
        "from yw645_wire import extract_yw645_frames" in src,
    )
    check(
        "web_utils 内不存在自定义 def extract_yw645_frames（复刻守卫）",
        "def extract_yw645_frames" not in src,
    )
    check(
        "web_utils.extract_yw645_frames 就是 yw645_wire 的那个对象",
        web_utils.extract_yw645_frames is extract_yw645_frames,
    )
    fn_src = inspect.getsource(web_utils.extract_frames_for_protocol)
    check(
        "extract_frames_for_protocol 协议13 分支为单行委托",
        "return extract_yw645_frames(text)" in fn_src,
    )

    # 查询页数据源
    lsrc = inspect.getsource(lookup_utils._search_yw645_di)
    check(
        "_search_yw645_di 从 yw645_di 取 DI_TABLE（非复刻）",
        "from yw645_di import DI_TABLE" in lsrc,
    )


# ═══════════════════════════════════════════════════════════════
# 2. 提取互斥
# ═══════════════════════════════════════════════════════════════

def test_extract_mutex():
    section("2. 提取互斥（混合日志只留依瓦帧）")
    for name, single in (("X2", X2), ("X3", X3), ("X5", X5), ("X9", X9)):
        out = web_utils.extract_frames_for_protocol(single, 13)
        check(f"{name} 单帧提取", out == [single], str(out))

    text = "\n".join([FRAME_NANWANG, FRAME_GUOWANG, FRAME_DLT645, FRAME_69845, X2, X3])
    web_out = web_utils.extract_frames_for_protocol(text, 13)
    check(
        "混合日志只提取依瓦帧（互斥）",
        web_out == [X2, X3],
        f"实际 {web_out}",
    )
    check(
        "与 yw645_wire 唯一实现逐元素相同（委托而非复刻）",
        web_out == extract_yw645_frames(text),
    )
    # 前置噪声（日志前缀/汉字/时间戳）不影响
    noisy = "2026-10-09 12:34:56 INFO 接收 <- " + X3
    check("日志前缀噪声可剥离", web_utils.extract_frames_for_protocol(noisy, 13) == [X3])

    # 其它协议在同一混合日志上不会抓到依瓦帧（反向互斥）
    nanwang_out = web_utils.extract_frames_for_protocol(text, 0)
    check("协议0（南网）提取不含依瓦帧", X3 not in nanwang_out, str(nanwang_out))


# ═══════════════════════════════════════════════════════════════
# 3. 摘要单一来源
# ═══════════════════════════════════════════════════════════════

def test_summary_single_source():
    section("3. 摘要单一来源（委托 YW645Parser.get_summary）")
    for name, hex_str in (("X2", X2), ("X3", X3), ("X5", X5)):
        frame = bytes.fromhex(hex_str)
        rows = YW645Parser().parse(frame)
        web = web_utils.get_frame_summary(rows, 13, frame)
        expected = YW645Parser().get_summary(frame)
        check(f"{name} Web 摘要 == 解析器 get_summary", web == expected, f"{web!r} vs {expected!r}")
    # 空表仍返回「空」（不抛错）
    check("空表摘要为「空」", web_utils.get_frame_summary([], 13, b"") == "空")


# ═══════════════════════════════════════════════════════════════
# 4. 查询页 di_yw645
# ═══════════════════════════════════════════════════════════════

def test_lookup():
    section("4. 查询页 di_yw645")
    cfg = lookup_utils.get_query_config(13)
    check(
        "查询列与桌面同口径",
        cfg["columns"] == ["ID", "数据项名称", "长度", "数据类型", "读/写", "说明"],
        str(cfg["columns"]),
    )
    check("查询标题为 DI 查询", cfg["title"] == "DI 查询", cfg["title"])

    expected = [
        [
            f"{e['id'][:2]} {e['id'][2:]}",
            e.get("name", ""),
            e.get("length", ""),
            e.get("dtype", ""),
            e.get("rw", ""),
            e.get("note", ""),
        ]
        for e in DI_TABLE
    ]
    rows = lookup_utils.get_lookup_data(13)
    cols = cfg["columns"]
    got = [[r[c] for c in cols] for r in rows]
    check("查询数据 == DI_TABLE 程序化推导（数据源单一）", got == expected, str(got))

    # 关键词过滤：ID 两种写法 + 中文名称
    check(
        "过滤 '设备号'",
        [r["ID"] for r in lookup_utils.get_lookup_data(13, "设备号")] == ["00 20"],
    )
    check(
        "过滤 '0020'（无空格写法）",
        [r["ID"] for r in lookup_utils.get_lookup_data(13, "0020")] == ["00 20"],
    )
    check(
        "过滤 '00 10'（空格写法）",
        [r["ID"] for r in lookup_utils.get_lookup_data(13, "00 10")] == ["00 10"],
    )
    check("过滤 '不存在的词' → 0 条", lookup_utils.get_lookup_data(13, "zzz") == [])


# ═══════════════════════════════════════════════════════════════
# 5. 两端解析对拍（AC12）
# ═══════════════════════════════════════════════════════════════

def _desktop_rows(hex_str: str):
    """桌面链路：注册表工厂 + parser_registry（与 main_gui._get_current_parser 同源）。"""
    parser = build_gui_parser(13, get_parser("yw645"))
    return parser.parse_to_table(bytes.fromhex(hex_str))


def _web_rows(app, hex_str: str):
    """Web 链路：Reflex State.parse_frame（真实入口）。"""
    st = app.State(_reflex_internal_init=True)
    st.set_protocol("13")
    st.frame_hex = hex_str
    asyncio.run(st.parse_frame())
    return st


def _clean_field(name: str) -> str:
    """去掉 Web 展示层的缩进/层级前缀（'　└ '）。"""
    return str(name).replace("　", "").replace("└", "").strip()


def test_desktop_web_parity():
    section("5. 两端解析对拍（AC12：行数与关键字段逐行一致）")
    app = _import_app()
    if app is None:
        return

    for name, hex_str in (("X2", X2), ("X3", X3), ("X5", X5), ("X9", X9)):
        desktop = _desktop_rows(hex_str)
        st = _web_rows(app, hex_str)
        web = st.parse_result

        print(f"  -- {name}: 桌面 {len(desktop)} 行 / Web {len(web)} 行")
        check(f"{name} 行数一致", len(desktop) == len(web), f"{len(desktop)} vs {len(web)}")
        if len(desktop) != len(web):
            continue

        mismatches = []
        for i, (dr, wr) in enumerate(zip(desktop, web)):
            exp_field = _clean_field(dr[0])
            got_field = _clean_field(wr["field"])
            exp = {
                "field": exp_field,
                "raw": str(dr[1]) if dr[1] else "",
                "parsed": str(dr[2]) if dr[2] else "",
                "comment": str(dr[3]) if dr[3] else "",
            }
            got = {
                "field": got_field,
                "raw": wr["raw"],
                "parsed": wr["parsed"],
                "comment": wr["comment"],
            }
            if exp != got:
                mismatches.append((i, exp, got))
        check(
            f"{name} 每行字段（field/raw/parsed/comment）逐行一致",
            not mismatches,
            str(mismatches[:2]),
        )

    # 关键字段抽样（X2 的设备类型/设备号值）
    st = _web_rows(app, X2)
    kv = {_clean_field(r["field"]): r["parsed"] for r in st.parse_result}
    check("X2 Web 表号 = 103000000010", kv.get("表号") == "103000000010", str(kv.get("表号")))
    check("X2 Web 模式 = 读模式返回", kv.get("模式") == "读模式返回", str(kv.get("模式")))
    check("X2 Web 状态成功", st.message_type == "success", st.message)
    check(
        "X2 Web 协议名按 value 查得到标签",
        st.last_protocol_name.startswith("[13]"),
        st.last_protocol_name,
    )


# ═══════════════════════════════════════════════════════════════
# 6. State 单帧 + 批量端到端
# ═══════════════════════════════════════════════════════════════

def test_state_parse_and_batch():
    section("6. State 单帧 + 批量端到端")
    app = _import_app()
    if app is None:
        return

    # 解析器分派：协议13 → YW645Parser（不是南网兜底）
    st = app.State(_reflex_internal_init=True)
    st.set_protocol("13")
    check("current_protocol == 13", st.current_protocol == 13, str(st.current_protocol))
    check("协议13 parser 为 YW645Parser", type(st._get_parser()).__name__ == "YW645Parser")
    check(
        "协议13 validator 为 YW645Validator",
        type(st._get_validator()).__name__ == "YW645Validator",
    )
    check("协议13 无解析级别参数（空 kwargs）", st._parse_kwargs() == {}, str(st._parse_kwargs()))
    check(
        "parse_kwargs_for(13) 返回 {} 不抛异常",
        web_utils.parse_kwargs_for(13) == {},
    )

    # 批量：混合日志只留依瓦帧，摘要回落解析器单源
    st2 = app.State(_reflex_internal_init=True)
    st2.set_protocol("13")
    st2.batch_input = "\n".join(
        [FRAME_NANWANG, FRAME_DLT645, FRAME_69845, X2, X3]
    )

    async def drive(state):
        async for _ in state.parse_batch():
            pass

    asyncio.run(drive(st2))
    check("批量仅提取 2 帧（互斥）", len(st2.batch_results) == 2, str(len(st2.batch_results)))
    if len(st2.batch_results) == 2:
        summaries = [r["summary"] for r in st2.batch_results]
        expected = [YW645Parser().get_summary(bytes.fromhex(X2)),
                    YW645Parser().get_summary(bytes.fromhex(X3))]
        check("批量摘要 == 解析器 get_summary（单源）", summaries == expected,
              f"{summaries} vs {expected}")
        check("批量状态均成功", all(r["status"] == "成功" for r in st2.batch_results),
              str([r["status"] for r in st2.batch_results]))


# ═══════════════════════════════════════════════════════════════
# 7. 组帧页可见提示（R7.4）
# ═══════════════════════════════════════════════════════════════

def test_frame_gen_hint():
    section("7. 组帧页可见提示（R7.4：Web 无组帧，不得静默缺失）")
    app = _import_app()
    if app is None:
        return

    src = unescape(str(app.frame_gen_tab()))
    check("组帧页含协议13 提示文案", "组帧暂未在 Web 端提供" in src)
    check("提示绑定协议13 条件", "current_protocol" in src)
    check("组帧页仍保留「当前协议暂不支持组帧」兜底徽章",
          "当前协议暂不支持组帧" in unescape(str(app.frame_gen_tab())))
    # State 层不应为协议13 造组帧路径（本期范围外）
    st = app.State(_reflex_internal_init=True)
    st.set_protocol("13")
    try:
        st._build_frame_bytes()
    except ValueError as e:
        check("协议13 生成帧抛可读错误", "暂不支持组帧" in str(e), str(e))
    except Exception as e:  # noqa: BLE001
        check("协议13 生成帧抛 ValueError", False, f"{type(e).__name__}: {e}")
    else:
        check("协议13 生成帧抛 ValueError", False, "未抛异常")


# ═══════════════════════════════════════════════════════════════
# 8. 首页协议表交叉引用
# ═══════════════════════════════════════════════════════════════

def test_landing_cross_ref():
    section("8. 首页协议表交叉引用")
    check("landing PROTOCOLS 行数 == registry 协议数",
          len(L.PROTOCOLS) == protocol_count(),
          f"{len(L.PROTOCOLS)} vs {protocol_count()}")
    row = next((p for p in L.PROTOCOLS if p["index"] == "13"), None)
    check("landing 含 index=13 行", row is not None)
    if row:
        check("index=13 协议名为依瓦定制645", row["name"] == "依瓦定制645", row["name"])
        check("index=13 标准号含 V1.0", "V1.0" in row["standard"], row["standard"])
    check("首页文案含依瓦定制645", "依瓦定制645" in unescape(str(L.PROTOCOLS)))


# ═══════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 62)
    print("协议13（依瓦定制645）Web 端支持回归 —— test_yw645_web.py")
    print("=" * 62)
    test_single_source()
    test_extract_mutex()
    test_summary_single_source()
    test_lookup()
    test_desktop_web_parity()
    test_state_parse_and_batch()
    test_frame_gen_hint()
    test_landing_cross_ref()
    print("\n" + "=" * 62)
    print(f"结果: PASS={PASS} FAIL={len(FAILURES)}")
    if FAILURES:
        for name in FAILURES:
            print(f"  ✗ {name}")
    print("=" * 62)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
