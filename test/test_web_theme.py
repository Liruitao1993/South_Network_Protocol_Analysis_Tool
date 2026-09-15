# -*- coding: utf-8 -*-
"""Web 主题系统回归测试（任务 09-15-web-theme-system）

覆盖：
  1. 预设/维度清单完整性（每个预设都有 label/mode/accent/gray/radius，取值合法）
  2. token 契约：浅色与深色键集合一致；含全部语义 token 与 --sp-m1..6
  3. `build_theme_css()` 结构：`:root` / `html.dark` / `.nw-accent-*` / 深色强调色块
  4. 关键「浅色等价」断言：token 浅色值 == 改造前硬编码值（逐 token 对齐）
  5. 标记配色单一来源：CSS 变量值 == `spectrum_widget.MARKER_COLORS_*`
  6. `ThemeState` 端到端：预设套用 / 维度微调转「自定义」/ restore / persist 脚本
  7. 组件树可构建且含主题控件；组件区不再出现裸 hex（token 化完成度）

直接运行: PYTHONIOENCODING=utf-8 python test/test_web_theme.py
"""

import _path_setup  # noqa: E402

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from reflex_web import theme_web  # noqa: E402

PASS = 0
FAILURES = []

# 改造前的浅色硬编码值（token 化前的真身，用于「浅色等价」断言）
LEGACY_LIGHT = {
    "--bg": "#f1f5f9",
    "--card": "#ffffff",
    "--card-hover": "#f8fafc",
    "--border": "#e2e8f0",
    "--border-strong": "#cbd5e1",
    "--text": "#0f172a",
    "--text-2": "#334155",
    "--muted": "#64748b",
    "--muted-2": "#94a3b8",
    "--accent": "#2563eb",
    "--accent-ink": "#1d4ed8",
    "--ok": "#16a34a",
    "--warn": "#f59e0b",
    "--danger": "#dc2626",
    "--code-bg": "#f8fafc",
    "--grid": "#e2e8f0",
    "--plot-bg": "#fbfdff",
    "--trace": "#0f766e",
}


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


# ═══════════════════════════════════════════════════════════════
# 1. 预设与维度
# ═══════════════════════════════════════════════════════════════

def test_presets():
    print("\n[1] 预设与维度清单")
    check("预设数量 = 6", len(theme_web.PRESETS) == 6, str(len(theme_web.PRESETS)))
    ids = [p["id"] for p in theme_web.PRESETS]
    check("预设 id 唯一", len(ids) == len(set(ids)), str(ids))
    accents = [a for a, _ in theme_web.ACCENTS]
    ok = True
    for p in theme_web.PRESETS:
        for key in ("id", "label", "mode", "accent", "gray", "radius", "desc"):
            ok = ok and bool(p.get(key))
        ok = ok and p["mode"] in theme_web.MODES
        ok = ok and p["accent"] in accents
        ok = ok and p["gray"] in theme_web.GRAYS
        ok = ok and p["radius"] in theme_web.RADII
    check("每个预设字段齐全且取值合法", ok)
    opts = theme_web.preset_options()
    values = [o["value"] for o in opts]
    check("下拉项含 6 预设（带 preset: 前缀）",
          sum(1 for v in values if v.startswith(theme_web.PRESET_PREFIX)) == 6, str(values[:7]))
    check("下拉项含 5 个强调色 + 3 个模式",
          sum(1 for v in values if v.startswith(theme_web.ACCENT_PREFIX)) == 5
          and sum(1 for v in values if v.startswith(theme_web.MODE_PREFIX)) == 3, str(values))
    check("模式循环 浅→深→跟随系统→浅",
          [theme_web.next_mode(m) for m in ("light", "dark", "system")] == ["dark", "system", "light"])
    check("模式图标齐全",
          theme_web.mode_icon("light") == "sun" and theme_web.mode_icon("dark") == "moon"
          and theme_web.mode_icon("system") == "monitor")
    check("模式选项三项", len(theme_web.MODE_OPTIONS) == 3, str(theme_web.MODE_OPTIONS))
    check("theme_class 合法性", theme_web.theme_class("teal") == "nw-theme nw-accent-teal")
    check("theme_class 非法值回落 blue",
          theme_web.theme_class("zzz") == "nw-theme nw-accent-blue")


# ═══════════════════════════════════════════════════════════════
# 2~5. token 契约与 CSS
# ═══════════════════════════════════════════════════════════════

def test_tokens():
    print("\n[2] token 契约")
    check("浅色/深色键集合一致",
          set(theme_web.TOKENS_LIGHT) == set(theme_web.TOKENS_DARK),
          f"{set(theme_web.TOKENS_LIGHT) ^ set(theme_web.TOKENS_DARK)}")
    check("token 数量 ≥ 20", len(theme_web.TOKENS_LIGHT) >= 20, str(len(theme_web.TOKENS_LIGHT)))
    for key, legacy in LEGACY_LIGHT.items():
        check(f"浅色 {key} 与改造前一致", theme_web.TOKENS_LIGHT[key].lower() == legacy,
              f"{theme_web.TOKENS_LIGHT[key]} vs {legacy}")
    diff = [k for k in theme_web.TOKENS_LIGHT
            if theme_web.TOKENS_LIGHT[k] == theme_web.TOKENS_DARK[k]]
    check("深浅色确有差异的 token ≥ 15", len(theme_web.TOKENS_LIGHT) - len(diff) >= 15,
          f"相同项 {diff}")

    print("\n[3] build_theme_css 结构")
    css = theme_web.build_theme_css()
    check("含 :root token 块", ":root" in css and "--bg:" in css)
    check("含 html.dark 覆盖块", "html.dark {" in css)
    check("深色 token 覆盖 --bg（页面底色跟随）",
          "html.dark {" in css and "--bg: " in css.split("html.dark {")[1][:400])
    for accent, _ in theme_web.ACCENTS:
        check(f"强调色块 {accent}", f".nw-accent-{accent} {{" in css)
        check(f"深色强调色块 {accent}", f"html.dark .nw-accent-{accent} {{" in css)
    for token in theme_web.TOKENS_LIGHT:
        if css.count(token + ":") < 2:
            check(f"token {token} 在浅/深两套都定义", False, f"出现 {css.count(token + ':')} 次")
            break
    else:
        check("每个 token 在浅/深两套都定义", True)
    check("含标记变量 --sp-m1/--sp-m6", "--sp-m1:" in css and "--sp-m6:" in css)

    print("\n[4] 标记配色单一来源")
    from spectrum_widget import MARKER_COLORS_DARK, MARKER_COLORS_LIGHT

    for i, color in enumerate(MARKER_COLORS_LIGHT):
        check(f"浅色 --sp-m{i + 1} 与 spectrum_widget 一致", f"--sp-m{i + 1}: {color};" in css)
    for i, color in enumerate(MARKER_COLORS_DARK):
        check(f"深色 --sp-m{i + 1} 与 spectrum_widget 一致", f"--sp-m{i + 1}: {color};" in css)
    from reflex_web import spectrum_web as sw

    check("标记图元引用 CSS 变量", sw.marker_var(0) == "var(--sp-m1)"
          and sw.marker_var(6) == "var(--sp-m1)", f"{sw.marker_var(0)}/{sw.marker_var(6)}")


# ═══════════════════════════════════════════════════════════════
# 6. ThemeState
# ═══════════════════════════════════════════════════════════════

def test_state():
    print("\n[5] ThemeState 端到端")
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return
    st = app.ThemeState(_reflex_internal_init=True)
    check("默认经典浅色", st.preset == "classic-light" and st.mode == "light"
          and st.accent == "blue", f"{st.preset}/{st.mode}/{st.accent}")
    check("root_class 含强调色", st.root_class == "nw-theme nw-accent-blue", st.root_class)

    st.apply_choice("preset:night-teal")
    check("套用「暗夜青绿」→ 模式+强调色同时变",
          st.mode == "dark" and st.accent == "teal" and st.preset == "night-teal",
          f"{st.mode}/{st.accent}/{st.preset}")
    check("切换到 teal 后 root_class 跟随",
          st.root_class == "nw-theme nw-accent-teal", st.root_class)

    st.apply_choice("accent:violet")
    check("下拉选中强调色 → 预设转「自定义」",
          st.accent == "violet" and st.preset == "custom", f"{st.accent}/{st.preset}")
    st.set_dimension("accent", "不存在的色")
    check("非法强调色被忽略", st.accent == "violet")

    st.apply_choice("mode:system")
    check("下拉开模式项可切跟随系统", st.mode == "system", st.mode)
    check("theme_choice 跟随（自定义时显示强调色项）",
          st.theme_choice == "accent:violet", st.theme_choice)
    st.cycle_mode()
    check("模式按钮循环 跟随系统→浅色", st.mode == "light", st.mode)
    check("mode_button_label/icon 与模式一致",
          st.mode_button_label == "浅色" and st.mode_button_icon == "sun",
          f"{st.mode_button_label}/{st.mode_button_icon}")

    st.restore(json.dumps({"mode": "dark", "accent": "green", "gray": "sand", "radius": "full"}))
    check("restore 读回四项",
          (st.mode, st.accent, st.gray, st.radius) == ("dark", "green", "sand", "full"),
          f"{st.mode}/{st.accent}/{st.gray}/{st.radius}")
    check("非预设组合 → 自定义", st.preset == theme_web.CUSTOM_PRESET, st.preset)
    st.restore(json.dumps({"mode": "dark", "accent": "teal", "gray": "slate", "radius": "medium"}))
    check("与预设一致的组合 → 回显预设 id", st.preset == "night-teal", st.preset)
    check("theme_choice 随之指向预设",
          st.theme_choice == "preset:night-teal", st.theme_choice)
    st.restore("不是 json")
    check("非法 restore 不炸且不改状态", st.accent == "teal", st.accent)
    st.restore("")
    check("空 restore 直接返回", st.mode == "dark")
    check("match_preset 未命中 → 自定义",
          theme_web.match_preset("dark", "blue", "sand", "medium") == theme_web.CUSTOM_PRESET)

    js = theme_web.persist_js("dark", "teal", "slate", "medium")
    check("persist 脚本写 localStorage + 应用模式",
          "localStorage.setItem('nw-theme'" in js and "classList.add(dark ? 'dark' : 'light')" in js,
          js[:80])
    check("persist 脚本同步 provider 读取的 theme 键",
          "localStorage.setItem('theme'" in js, js[-120:])
    check("restore 脚本读同一份键且注册跟随系统监听",
          "nw-theme" in theme_web.restore_js() and "__nwMqBound" in theme_web.restore_js(),
          theme_web.restore_js()[:80])
    check("apply 片段自包含（不依赖先前注入的全局函数）",
          "document.documentElement" in theme_web.apply_mode_js("dark")
          and "__nwApplyTheme" not in theme_web.apply_mode_js("dark"))


# ═══════════════════════════════════════════════════════════════
# 7. 组件树 + token 化完成度
# ═══════════════════════════════════════════════════════════════

def test_component_tree():
    print("\n[6] 组件树与 token 化完成度")
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return
    page = str(app.tool_page())
    for probe in ("theme-preset", "theme-mode", "spectrum-svg"):
        check(f"工具页含 {probe}", probe in page)
    check("根容器挂主题 class（ThemeState.root_class）", "root_class" in page, page[:120])
    check("主题 CSS 已注入页面", ":root" in page and "html.dark" in page)
    check("主题下拉含强调色/模式项",
          "accent:" in str(theme_web.preset_options()) and "mode:" in str(theme_web.preset_options()))
    check("模式按钮由 State 驱动（图标/文案 Var）",
          "mode_button_icon" in page and "mode_button_label" in page)

    src = (WEB / "reflex_web" / "reflex_web.py").read_text(encoding="utf-8")
    # CSS 段之外不应再有裸 hex（GLOBAL_CSS/SEARCHABLE_CSS 已 token 化）
    stripped = src
    for name in ("SEARCHABLE_CSS", "GLOBAL_CSS"):
        i = stripped.find(f'{name} = """')
        j = stripped.find('"""', i + 20)
        stripped = stripped[:i] + stripped[j:]
    # 允许 var(--token, #fallback) 里的兜底色（缺 token 时不至于变透明）
    stripped = re.sub(r'var\(--[\w-]+,\s*#[0-9a-fA-F]{6}\)', "var(--x)", stripped)
    leftover = re.findall(r'#[0-9a-fA-F]{6}', stripped)
    check("组件区无裸 hex（token 化完成；var 兜底色除外）", not leftover,
          f"{len(leftover)} 处: {sorted(set(leftover))[:6]}")
    check("GLOBAL_CSS 已用 token", "var(--bg)" in src and "var(--card)" in src)


def main():
    print("=" * 62)
    print("Web 主题系统回归测试")
    print("=" * 62)
    test_presets()
    test_tokens()
    test_state()
    test_component_tree()
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
