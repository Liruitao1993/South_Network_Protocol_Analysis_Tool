"""Web 版产品首页（落地页）回归测试（任务 09-15-web-landing-page）

覆盖：
  1. 内容不变式：12 协议（索引连续唯一）/ 12 功能卡 / 4 条 CLI / 系统集成 / 统计条
  2. 防漂移：协议行数 == `protocol_registry.protocol_count()`；CLI 参数名在 main_gui 里真实存在
  3. 组件树可构建（无参 + 带假数据），含全部 data-testid 锚点
  4. 缺图降级：`image_available` 真假时 img / 占位卡互斥，绝不出现空 src 的 img
  5. 死链守卫：落地页里的站内链接全部 ∈ `INTERNAL_LINKS ∪ 锚点`，且站点内不存在指向
     已废弃路由的链接（老 `/` 语义已改为首页，工具页在 `/app`）
  6. 路由与页面搬迁：`/` → 落地页、`/app` → 工具页；工具页 9 个 tab 与主题控件完好

直接运行: PYTHONIOENCODING=utf-8 python test/test_web_landing.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from reflex_web import landing_web as L  # noqa: E402

PASS = 0
FAILURES = []

# 落地页必须暴露的锚点（供人工/自动化定位；少一个就是回归）
EXPECTED_TESTIDS = (
    "landing-root",
    "nav-brand",
    "nav-online",
    "hero-title",
    "hero-download",
    "hero-online",
    "feature-grid",
    "protocol-table",
    "quickstart-cli",
    "cta-download",
    "cta-online",
    "landing-footer",
)


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


def has_testid(rendered: str, testid: str) -> bool:
    """Reflex 把 `data_testid=` 渲染成 JSX 的 `"data-testid":"x"`。"""
    return f'"data-testid":"{testid}"' in rendered


def unescape(rendered: str) -> str:
    """Reflex 在 JSX 里把非 ASCII 转义成 `\\uXXXX`，中文断言前必须先解开。"""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), rendered)


# ═══════════════════════════════════════════════════════════════
# 1. 内容不变式
# ═══════════════════════════════════════════════════════════════


def test_content():
    print("\n[1] 内容不变式")
    sys.path.insert(0, str(ROOT))
    import protocol_registry as pr

    check(
        "协议条数与注册表一致",
        len(L.PROTOCOLS) == pr.protocol_count(),
        f"landing={len(L.PROTOCOLS)} registry={pr.protocol_count()}",
    )
    idx = [p["index"] for p in L.PROTOCOLS]
    check("协议索引连续且唯一", idx == [str(i) for i in range(len(idx))], str(idx))
    for field in ("name", "standard", "endian", "check"):
        vals = [p[field] for p in L.PROTOCOLS]
        check(f"协议 {field} 全非空", all(v and v.strip() for v in vals))
    names = [p["name"] for p in L.PROTOCOLS]
    check("协议名唯一", len(set(names)) == len(names))

    check("功能卡 ≥ 10 张", len(L.FEATURES) >= 10, f"实际 {len(L.FEATURES)}")
    titles = [f["title"] for f in L.FEATURES]
    check("功能卡标题唯一", len(set(titles)) == len(titles), str(titles))
    check("功能卡图标非空", all(f.get("icon") for f in L.FEATURES))
    check("功能卡描述非空", all(f.get("desc", "").strip() for f in L.FEATURES))

    check("CLI 示例 4 条", len(L.CLI_ACTIONS) == 4, f"实际 {len(L.CLI_ACTIONS)}")
    check("系统集成 ≥ 5 条", len(L.SYSTEM_INTEGRATIONS) >= 5)
    check("统计条 ≥ 3 项", len(L.HERO_STATS) >= 3)
    check(
        "统计条字段完整", all(s.get("label") and ("value" in s) for s in L.HERO_STATS)
    )


# ═══════════════════════════════════════════════════════════════
# 2. 防漂移（与注册表 / 真实 CLI 对拍）
# ═══════════════════════════════════════════════════════════════


def test_no_drift():
    print("\n[2] 防漂移对拍")
    sys.path.insert(0, str(ROOT))
    try:
        import protocol_registry as pr

        check(
            "协议行数与 protocol_registry 一致",
            len(L.PROTOCOLS) == pr.protocol_count(),
            f"{len(L.PROTOCOLS)} vs {pr.protocol_count()}",
        )
        labels = pr.combo_labels()
        check(
            "协议行数与注册表标签数一致",
            len(labels) == len(L.PROTOCOLS),
            f"labels={len(labels)} rows={len(L.PROTOCOLS)}",
        )
        # 逐行与注册表标签对拍：协议改名/新增时落地页表格必须同步（防表格腐烂）
        for i, proto in enumerate(L.PROTOCOLS):
            label = labels[i] if i < len(labels) else ""
            keyword = proto["name"].split("（")[0].split(" ")[0]
            check(
                f"第 {i} 行协议名与注册表同源",
                keyword in label,
                f"{keyword!r} 不在 {label!r}",
            )
    except Exception as e:  # noqa: BLE001
        check("导入 protocol_registry", False, f"{type(e).__name__}: {e}")

    # CLI 参数名必须真在 main_gui 的参数解析分支里（防文案漂移）。
    # 注意：`any(a in ("--parse","--file","--clipboard") …)` 这类元组判断会让
    # 「f'"{flag}"' in src」假绿 → 必须断言**真实分支形态** `arg == "--flag"`，
    # 且要抽出每条命令的**全部** flag（旧的 `re.search` 只取第一个，--protocol 从未被查）。
    try:
        src = (ROOT / "main_gui.py").read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        check("读取 main_gui.py", False, f"{type(e).__name__}: {e}")
        return
    flags = sorted(
        {f for a in L.CLI_ACTIONS for f in re.findall(r"--[a-z_]+", a["cmd"])}
    )
    check("从 CLI_ACTIONS 抽出 ≥5 个参数", len(flags) >= 5, str(flags))
    for flag in flags:
        check(
            f'CLI 参数 {flag} 有真实解析分支（arg == "{flag}"）',
            f'arg == "{flag}"' in src,
            flag,
        )
    check(
        "每条命令都至少带一个可校验的参数",
        all(re.search(r"--[a-z_]+", a["cmd"]) for a in L.CLI_ACTIONS),
    )


# ═══════════════════════════════════════════════════════════════
# 3. 组件树
# ═══════════════════════════════════════════════════════════════


def test_component_tree():
    print("\n[3] 组件树可构建")
    try:
        plain = str(L.landing_page())
        rich = str(
            L.landing_page(
                version="9.9.9",
                version_date="2026-01-01",
                exe_name="南网协议解析工具9.9.9.exe",
                exe_size_mb="97.6",
                exe_available=True,
                image_src="data:image/png;base64,AAAA",
                image_available=True,
            )
        )
    except Exception as e:  # noqa: BLE001
        check("landing_page() 构建", False, f"{type(e).__name__}: {e}")
        return
    check("无参构建成功", len(plain) > 1000, str(len(plain)))
    check("带数据构建成功", len(rich) > 1000, str(len(rich)))

    rich_text = unescape(rich)
    for testid in EXPECTED_TESTIDS:
        check(f"锚点 {testid}", has_testid(rich, testid))
    check(
        "Hero 主标题在页面上",
        L.HERO_TITLE_LEAD in rich_text and L.HERO_TITLE_ACCENT in rich_text,
    )
    check("12 个协议名全部出现在页面", all(p["name"] in rich_text for p in L.PROTOCOLS))
    check("12 张功能卡标题全部出现", all(f["title"] in rich_text for f in L.FEATURES))
    check("版本徽章含版本号", "v9.9.9" in rich_text, rich_text[:80])
    check("exe 体积文案带单位", "97.6 MB" in rich_text)
    check("落地页样式表已内联", "landing-hero" in rich and "landing-root" in rich)


# ═══════════════════════════════════════════════════════════════
# 4. 缺图降级
# ═══════════════════════════════════════════════════════════════


def test_image_fallback():
    print("\n[4] 缺图降级")
    without = str(L.landing_page(image_available=False))
    with_img = str(
        L.landing_page(image_available=True, image_src="data:image/png;base64,AAAA")
    )
    check("无截图时不渲染 img", not has_testid(without, "hero-shot"))
    check("无截图时渲染占位卡", has_testid(without, "hero-shot-placeholder"))
    check("有截图时渲染 img", has_testid(with_img, "hero-shot"))
    check("有截图时不渲染占位卡", not has_testid(with_img, "hero-shot-placeholder"))
    # 缺图时不得出现 src="" 的破图
    check("无截图时无空 src 的 img", 'src:""' not in without.replace(" ", ""))


# ═══════════════════════════════════════════════════════════════
# 5. 死链守卫
# ═══════════════════════════════════════════════════════════════


def link_target(rendered: str, testid: str) -> str:
    """取出带该 testid 的元素上的路由目标（Reflex 把 `href=` 编成 `to:"..."`）。

    props 顺序不保证（实测 `{className, data-testid, to}`），故两个方向都试。
    """
    for pat in (
        r'"data-testid":"%s"[^}]*?to:"([^"]*)"' % re.escape(testid),
        r'to:"([^"]*)"[^}]*?"data-testid":"%s"' % re.escape(testid),
    ):
        m = re.search(pat, rendered)
        if m:
            return m.group(1)
    return ""


def test_links():
    print("\n[5] 链接白名单与站内接线")
    rendered = str(L.landing_page(version="9.9.9", exe_name="x.exe", exe_size_mb="1.0"))
    # Reflex 把 rx.el.a 编译成路由 Link：站点内链接落在 to:"..."（锚点也是 to:"#..."）
    tos = set(re.findall(r'to:"([^"]+)"', rendered))
    internal = {t for t in tos if t.startswith("/")}
    anchors = {t for t in tos if t.startswith("#")}
    check("站内链接非空（守卫本身有效）", bool(internal), str(sorted(tos))[:120])
    bad = sorted(internal - L.ALLOWED_HREFS)
    check("站内链接全部在白名单内", not bad, str(bad))
    bad_anchor = sorted(a for a in anchors if a not in L.ALLOWED_HREFS)
    check("锚点全部指向已定义 section", not bad_anchor, str(bad_anchor))
    # 白名单是字面量：改坏 INTERNAL_LINKS 的值必须被这条抓住（派生白名单会漏）
    check(
        "白名单未被 INTERNAL_LINKS 派生（改值即报红）",
        {
            "/",
            "/app",
            "/feedback",
            "/share",
            "#features",
            "#protocols",
            "#quickstart",
            "#download",
        }
        == L.ALLOWED_HREFS,
        str(sorted(L.ALLOWED_HREFS)),
    )
    for section in L.SECTION_IDS:
        check(
            f"section id={section} 存在", f'id:"{section}"' in rendered, rendered[:80]
        )

    # ── 接线断言：**必须读组合层渲染结果**，否则「链接语义被改回去」无法被发现 ──
    # （纯查 landing_web 的常量对常量恒真：渲染与白名单同源，见 A1 复核结论）
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check(
            "导入 reflex_web.reflex_web（接线断言）", False, f"{type(e).__name__}: {e}"
        )
        return
    tool = str(app.tool_page())
    check(
        "工具页品牌块 → 首页 /",
        link_target(tool, "nav-brand") == "/",
        link_target(tool, "nav-brand"),
    )
    check(
        "独立页版式含「在线工具」→ /app（工具页 header 两分支共用）",
        link_target(tool, "nav-tool") == "/app",
        link_target(tool, "nav-tool"),
    )
    check(
        "独立页「管理员登录」→ /app（弹窗只挂工具页）",
        link_target(tool, "btn-login-home") == "/app",
        link_target(tool, "btn-login-home"),
    )

    share = str(app.share_page())
    check(
        "/share「去解析并分享」→ /app",
        link_target(share, "share-goto-tool") == "/app",
        link_target(share, "share-goto-tool"),
    )
    feedback = str(app.feedback_page())
    check(
        "/feedback 导航 → /app 与首页",
        link_target(feedback, "nav-tool") == "/app"
        and link_target(feedback, "nav-brand") == "/",
        f"{link_target(feedback, 'nav-tool')} / {link_target(feedback, 'nav-brand')}",
    )
    admin = str(app.feedback_admin_page())
    check(
        "/feedback-admin「前往在线工具」→ /app",
        link_target(admin, "admin-goto-tool") == "/app",
        link_target(admin, "admin-goto-tool"),
    )
    check(
        "/feedback-admin 导航 → /app 与首页",
        link_target(admin, "nav-tool") == "/app"
        and link_target(admin, "nav-brand") == "/",
        f"{link_target(admin, 'nav-tool')} / {link_target(admin, 'nav-brand')}",
    )
    # 源码层反例守卫：这几处改前是 href="/"（工具页语义），不许回归
    src = (WEB / "reflex_web" / "reflex_web.py").read_text(encoding="utf-8")
    check(
        "reflex_web.py 无遗留「返回主页」按钮",
        'data_testid="nav-home"' not in src and '"返回主页"' not in src,
    )
    stale = src.count('href="/"')
    check(
        'reflex_web.py 不再出现裸 href="/"（工具页语义已改 /app）',
        stale == 0,
        f"{stale} 处",
    )


# ═══════════════════════════════════════════════════════════════
# 6. 路由与页面搬迁
# ═══════════════════════════════════════════════════════════════


def _route_key(app, route: str) -> str:
    """Reflex 把 route 归一化成 pages 键（'/' → 'index'）。

    `_page_route_key` 在本机版本里被 staticmethod 包了一层，故带 TypeError 兜底。
    """
    fn = app._page_route_key
    try:
        return fn(route)
    except TypeError:
        return fn(app, route)


def test_routes():
    print("\n[6] 路由与页面搬迁")
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return
    pages = set(app.app._unevaluated_pages.keys())
    home_key = _route_key(app.app, "/")
    tool_key = _route_key(app.app, "/app")
    check(
        "根路由已注册（产品首页）", home_key in pages, f"{home_key} in {sorted(pages)}"
    )
    check("工具页路由已注册", tool_key in pages, f"{tool_key} in {sorted(pages)}")
    check(
        "独立页路由未被破坏",
        {"feedback", "feedback-admin", "share"} <= pages,
        str(sorted(pages)),
    )
    check("旧页面函数名 index 已不存在（改名 tool_page）", not hasattr(app, "index"))
    check(
        "tool_page / landing_page 均存在",
        hasattr(app, "tool_page") and hasattr(app, "landing_page"),
    )

    tool = str(app.tool_page())
    for tab in (
        "tab-single",
        "tab-batch",
        "tab-frame",
        "tab-diff",
        "tab-lookup",
        "tab-spectrum",
        "tab-tool",
        "tab-download",
        "tab-feedback",
    ):
        check(f"工具页 tab {tab}", has_testid(tool, tab))
    check(
        "工具页顶栏含主题控件",
        has_testid(tool, "theme-preset") and has_testid(tool, "theme-mode"),
    )
    check("工具页顶栏品牌可点回首页", has_testid(tool, "nav-brand"))
    check("独立页导航改指在线工具", has_testid(tool, "nav-tool"))

    # 版本徽章：唯一数据源 = downloads/version.json（顶栏曾写死 v1.13.0）
    import json as _json

    vj = ROOT / "reflex_web" / "downloads" / "version.json"
    try:
        published = str(
            _json.loads(vj.read_text(encoding="utf-8")).get("version", "") or ""
        )
    except Exception:
        published = ""
    check(
        "顶栏版本徽章与 version.json 同源",
        published == app.PUBLISHED_VERSION,
        f"{app.PUBLISHED_VERSION!r} vs {published!r}",
    )
    check("顶栏不再写死假版本号（v1.13.0）", "v1.13.0" not in tool)

    landing = str(app.landing_page())
    check(
        "首页含主题控件（与工具页共用 theme_controls_compact）",
        has_testid(landing, "theme-preset") and has_testid(landing, "theme-mode"),
    )
    check(
        "首页注入 State 下载事件/数据",
        "download_client" in landing and "download_exe_size_mb" in landing,
    )
    check(
        "首页挂主题 token 样式（theme_style）",
        ":root" in landing and "html.dark" in landing,
    )


def main():
    print("=" * 62)
    print("Web 产品首页（落地页）回归测试")
    print("=" * 62)
    test_content()
    test_no_drift()
    test_component_tree()
    test_image_fallback()
    test_links()
    test_routes()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"全部通过（{PASS} 项）✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
