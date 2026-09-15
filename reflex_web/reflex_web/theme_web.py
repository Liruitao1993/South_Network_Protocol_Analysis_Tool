# -*- coding: utf-8 -*-
"""Web 主题系统：预设 + CSS token（纯逻辑，无 Qt / 无 reflex）。

设计（`.trellis/tasks/09-15-web-theme-system/design.md`）：

- **模式**（浅色/深色/跟随系统）由 Reflex/Radix 原生机制负责（根节点 `light`/`dark` 类 + localStorage），
  本模块只提供深色下的 token 覆盖；
- **预设主题** = 模式 × 强调色（× 灰阶 × 圆角）的命名组合，供顶栏下拉一键套用；
- **token 层**：浅色取**当前实际值**（保证与改造前逐像素等价），深色只覆盖 token；
- 频谱图标记配色由 `spectrum_widget.MARKER_COLORS_*` 生成 CSS 变量（单一来源）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spectrum_widget import MARKER_COLORS_DARK, MARKER_COLORS_LIGHT  # noqa: E402

# ══════════════════════════════════════════════════════════════
# 维度清单
# ══════════════════════════════════════════════════════════════

MODES: Tuple[str, ...] = ("light", "dark", "system")

# 模式下拉项（value, label）
MODE_OPTIONS: Tuple[Tuple[str, str], ...] = (
    ("light", "浅色"),
    ("dark", "深色"),
    ("system", "跟随系统"),
)

# Radix 的 accent_color 取值（自定义 CSS 侧只覆盖 --accent/--accent-soft）
ACCENTS: Tuple[Tuple[str, str], ...] = (
    ("blue", "蓝（默认）"),
    ("teal", "青绿"),
    ("violet", "紫"),
    ("amber", "琥珀"),
    ("green", "绿"),
)

GRAYS: Tuple[str, ...] = ("slate", "gray", "sand")
RADII: Tuple[str, ...] = ("none", "small", "medium", "large", "full")

DEFAULT_ACCENT = "blue"
DEFAULT_GRAY = "slate"
DEFAULT_RADIUS = "medium"
CUSTOM_PRESET = "custom"

# ══════════════════════════════════════════════════════════════
# 预设主题（模式 × 强调色）
# ══════════════════════════════════════════════════════════════

PRESETS: List[Dict[str, str]] = [
    {
        "id": "classic-light",
        "label": "经典浅色",
        "mode": "light",
        "accent": "blue",
        "gray": "slate",
        "radius": "medium",
        "desc": "默认观感：浅灰底 + 卡片白 + 蓝色强调",
    },
    {
        "id": "night-blue",
        "label": "夜间深色",
        "mode": "dark",
        "accent": "blue",
        "gray": "slate",
        "radius": "medium",
        "desc": "深蓝底 + 高对比文字，适合弱光/夜间",
    },
    {
        "id": "night-teal",
        "label": "暗夜青绿",
        "mode": "dark",
        "accent": "teal",
        "gray": "slate",
        "radius": "medium",
        "desc": "深底 + 青绿强调，长时间盯屏更柔和",
    },
    {
        "id": "night-violet",
        "label": "暗夜紫",
        "mode": "dark",
        "accent": "violet",
        "gray": "gray",
        "radius": "medium",
        "desc": "深底 + 紫色强调",
    },
    {
        "id": "warm-amber",
        "label": "浅色琥珀",
        "mode": "light",
        "accent": "amber",
        "gray": "sand",
        "radius": "medium",
        "desc": "暖色强调，与频谱/功率类数据观感相配",
    },
    {
        "id": "eye-green",
        "label": "护眼绿",
        "mode": "light",
        "accent": "green",
        "gray": "gray",
        "radius": "large",
        "desc": "绿色强调 + 大圆角，长时阅读更舒适",
    },
]

PRESET_BY_ID = {p["id"]: p for p in PRESETS}


PRESET_PREFIX = "preset:"
ACCENT_PREFIX = "accent:"
MODE_PREFIX = "mode:"


def preset_options() -> List[Dict[str, str]]:
    """主题下拉项：6 个预设 + 5 个「只换强调色」+ 3 个模式。

    紧凑设计（顶栏只放一个下拉 + 一个模式按钮）：预设改模式+外观，强调色项只改颜色，
    模式项只改模式（跟随系统走按钮循环，此处仍提供以便直接选中）。
    """
    options = [
        {"label": p["label"], "value": PRESET_PREFIX + p["id"], "desc": p["desc"]}
        for p in PRESETS
    ]
    options += [
        {"label": f"强调色 · {label}", "value": ACCENT_PREFIX + value,
         "desc": "保持当前模式，仅切换强调色（转为自定义）"}
        for value, label in ACCENTS
    ]
    options += [
        {"label": f"模式 · {label}", "value": MODE_PREFIX + value,
         "desc": "只切换明暗模式"}
        for value, label in MODE_OPTIONS
    ]
    return options


def match_preset(mode: str, accent: str, gray: str, radius: str) -> str:
    """四项与某个预设完全一致时返回该预设 id，否则「自定义」。

    用于 restore：刷新后应显示「经典浅色」而不是「强调色 · 蓝」。
    """
    for preset in PRESETS:
        if (preset["mode"], preset["accent"], preset["gray"], preset["radius"]) == (
            mode, accent, gray, radius
        ):
            return preset["id"]
    return CUSTOM_PRESET


def next_mode(mode: str) -> str:
    """模式循环：浅色 → 深色 → 跟随系统 → 浅色。"""
    order = [m for m, _ in MODE_OPTIONS]
    try:
        return order[(order.index(mode) + 1) % len(order)]
    except ValueError:
        return "light"


def mode_label(mode: str) -> str:
    for value, label in MODE_OPTIONS:
        if value == mode:
            return label
    return "浅色"


def mode_icon(mode: str) -> str:
    """模式按钮图标（lucide 名）。"""
    return {"light": "sun", "dark": "moon", "system": "monitor"}.get(mode, "sun")


# ══════════════════════════════════════════════════════════════
# Token（浅色 = 改造前实际值；深色 = 覆盖值）
# ══════════════════════════════════════════════════════════════

TOKENS_LIGHT: Dict[str, str] = {
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
    "--accent-soft": "rgba(37, 99, 235, 0.10)",
    "--accent-ink": "#1d4ed8",
    "--ok": "#16a34a",
    "--ok-soft": "rgba(22, 163, 74, 0.12)",
    "--warn": "#f59e0b",
    "--danger": "#dc2626",
    "--code-bg": "#f8fafc",
    "--grid": "#e2e8f0",
    "--plot-bg": "#fbfdff",
    "--trace": "#0f766e",
    "--field-bg": "#ffffff",
    "--shadow": "rgba(15, 23, 42, 0.06)",
}

TOKENS_DARK: Dict[str, str] = {
    "--bg": "#0b1220",
    "--card": "#141d31",
    "--card-hover": "#1b2743",
    "--border": "#27334d",
    "--border-strong": "#3b4a6b",
    "--text": "#e6edf7",
    "--text-2": "#c3cfe2",
    "--muted": "#9fb0c9",
    "--muted-2": "#7d8ea8",
    "--accent": "#60a5fa",
    "--accent-soft": "rgba(96, 165, 250, 0.16)",
    "--accent-ink": "#93c5fd",
    "--ok": "#34d399",
    "--ok-soft": "rgba(52, 211, 153, 0.16)",
    "--warn": "#fbbf24",
    "--danger": "#f87171",
    "--code-bg": "#0d1526",
    "--grid": "#2a354f",
    "--plot-bg": "#0d1526",
    "--trace": "#5eead4",
    "--field-bg": "#0f1a2e",
    "--shadow": "rgba(0, 0, 0, 0.35)",
}

# 强调色覆盖（自定义 CSS 侧；Radix 组件侧由 rx.theme(accent_color=…) 负责）
ACCENT_OVERRIDES: Dict[str, Dict[str, str]] = {
    "blue": {
        "--accent": "#2563eb",
        "--accent-soft": "rgba(37, 99, 235, 0.10)",
        "--accent-ink": "#1d4ed8",
    },
    "teal": {"--accent": "#0d9488", "--accent-soft": "rgba(13, 148, 136, 0.12)", "--accent-ink": "#0f766e"},
    "violet": {"--accent": "#7c3aed", "--accent-soft": "rgba(124, 58, 237, 0.12)", "--accent-ink": "#6d28d9"},
    "amber": {"--accent": "#d97706", "--accent-soft": "rgba(217, 119, 6, 0.12)", "--accent-ink": "#b45309"},
    "green": {"--accent": "#15803d", "--accent-soft": "rgba(21, 128, 61, 0.12)", "--accent-ink": "#166534"},
}

# 深色下的强调色（浅色字面量在深底上对比不足）
ACCENT_OVERRIDES_DARK: Dict[str, Dict[str, str]] = {
    "blue": {"--accent": "#60a5fa", "--accent-soft": "rgba(96, 165, 250, 0.16)", "--accent-ink": "#93c5fd"},
    "teal": {"--accent": "#2dd4bf", "--accent-soft": "rgba(45, 212, 191, 0.16)", "--accent-ink": "#5eead4"},
    "violet": {"--accent": "#a78bfa", "--accent-soft": "rgba(167, 139, 250, 0.18)", "--accent-ink": "#c4b5fd"},
    "amber": {"--accent": "#fbbf24", "--accent-soft": "rgba(251, 191, 36, 0.16)", "--accent-ink": "#fcd34d"},
    "green": {"--accent": "#4ade80", "--accent-soft": "rgba(74, 222, 128, 0.16)", "--accent-ink": "#86efac"},
}


# ── 客户端脚本 ──
# 注意：不用 <script> 注入（react 插入的 script 不保证执行），改为把片段拼进
# `rx.call_script`；且每个片段**自包含**（不依赖先前片段已定义），避免顺序耦合。

_APPLY_JS = (
    "(() => {"
    " const root = document.documentElement;"
    " const sysDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;"
    " const dark = MODE === 'dark' || (MODE === 'system' && sysDark);"
    " root.classList.remove('light', 'dark');"
    " root.classList.add(dark ? 'dark' : 'light');"
    " root.style.colorScheme = dark ? 'dark' : 'light';"
    " localStorage.setItem('theme', dark ? 'dark' : 'light');"
    " return dark ? 'dark' : 'light'; })()"
)

_GUARD_JS = (
    # 实测：Reflex/Radix 的 ThemeProvider 会在挂载后（以及其自身状态变化时）重写根节点的
    # light/dark 类，dev 模式还会把模式强制复位为编译期默认值 —— 只写一次类会被它覆盖。
    # 用一个 class 观察器把最终态纠回「我们保存的模式」（幂等：一致时直接返回，不会自激）。
    "(function () {"
    " if (window.__nwGuard) return;"
    " window.__nwGuard = true;"
    " const want = () => {"
    "   let s = {}; try { s = JSON.parse(localStorage.getItem('nw-theme') || '{}'); } catch (e) {}"
    "   const mode = s.mode || 'light';"
    "   const sysDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;"
    "   return {dark: mode === 'dark' || (mode === 'system' && sysDark)};"
    " };"
    " const fix = () => {"
    "   const w = want();"
    "   const root = document.documentElement;"
    "   if (root.classList.contains('dark') === w.dark) return;"
    "   root.classList.remove('light', 'dark');"
    "   root.classList.add(w.dark ? 'dark' : 'light');"
    "   root.style.colorScheme = w.dark ? 'dark' : 'light';"
    "   localStorage.setItem('theme', w.dark ? 'dark' : 'light');"
    " };"
    " new MutationObserver(fix).observe(document.documentElement, {attributes: true, attributeFilter: ['class']});"
    " fix();"
    "})()"
)


def apply_mode_js(mode: str) -> str:
    """应用模式的**自包含**片段（不依赖其它脚本已注入）。

    竞态说明：Reflex/Radix 的 ThemeProvider 挂载后也会写根节点类，且 dev 模式可能把
    模式强制复位为编译期默认值。因此 `restore_js` 在本片段之后还会把**解析出的模式**
    延迟镜像进 Provider 读取的 `localStorage['theme']`（见 restore_js），两边收敛一致。
    """
    snippet = _APPLY_JS.replace("MODE", f"'{mode}'")
    return (
        "(function () {"
        " const run = () => " + snippet + ";"
        " run();"
        " " + _GUARD_JS + ";"
        " return run(); })()"
    )


def persist_js(mode: str, accent: str, gray: str, radius: str) -> str:
    """写入 localStorage + 即时应用模式（服务端状态已先行更新）。"""
    payload = (
        f"{{mode: '{mode}', accent: '{accent}', gray: '{gray}', radius: '{radius}'}}"
    )
    return (
        "(() => { const s = " + payload + ";"
        " localStorage.setItem('nw-theme', JSON.stringify(s));"
        " return " + apply_mode_js(mode) + "; })()"
    )


def restore_js() -> str:
    """on_load：读回本地主题并应用（含跟随系统监听与模式守卫），返回原始串给 State.restore。"""
    return (
        "(function () {"
        " let raw = ''; try { raw = localStorage.getItem('nw-theme') || ''; } catch (e) {}"
        " let mode = 'light'; try { mode = (JSON.parse(raw || '{}').mode) || 'light'; } catch (e) {}"
        " const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');"
        " if (mq && !window.__nwMqBound) {"
        "   window.__nwMqBound = true;"
        "   mq.addEventListener('change', function () {"
        "     let s = {}; try { s = JSON.parse(localStorage.getItem('nw-theme') || '{}'); } catch (e) {}"
        "     if (s.mode !== 'system') return;"
        "     const root = document.documentElement;"
        "     const dark = mq.matches;"
        "     root.classList.remove('light', 'dark');"
        "     root.classList.add(dark ? 'dark' : 'light');"
        "     root.style.colorScheme = dark ? 'dark' : 'light';"
        "     localStorage.setItem('theme', dark ? 'dark' : 'light');"
        "   });"
        " }"
        " " + apply_mode_js("MODE").replace("MODE", "mode")
        # 延迟把解析后的模式镜像进 Reflex Provider 读取的 `theme` 键：它的挂载副作用
        # 可能在我们的脚本之后才写该键（两边口径不一致）。
        + "; setTimeout(function () {"
        + "   const root = document.documentElement;"
        + "   localStorage.setItem('theme', root.classList.contains('dark') ? 'dark' : 'light');"
        + " }, 900);"
        + "; return raw; })()"
    )


def theme_class(accent: str) -> str:
    """界面根容器 class（自定义 CSS 作用域 + 强调色开关）。"""
    key = accent if accent in ACCENT_OVERRIDES else DEFAULT_ACCENT
    return f"nw-theme nw-accent-{key}"


def _decls(tokens: Dict[str, str], indent: str = "  ") -> str:
    return "\n".join(f"{indent}{k}: {v};" for k, v in tokens.items())


def marker_css(dark: bool) -> str:
    """频谱图标记配色变量（由 spectrum_widget 的常量生成，保持单一来源）。"""
    colors = MARKER_COLORS_DARK if dark else MARKER_COLORS_LIGHT
    return "\n".join(f"  --sp-m{i + 1}: {c};" for i, c in enumerate(colors))


def build_theme_css() -> str:
    """主题 CSS：`:root` 浅色 token + `html.dark` 深色覆盖 + 每强调色覆盖块。"""
    parts = [
        "/* ===== 主题 token（浅色；深色见 html.dark）===== */",
        # 只挂 :root：挂到 .nw-theme 会在容器上覆盖 html.dark 的继承值（深色失效）
        ":root {",
        _decls(TOKENS_LIGHT),
        marker_css(False),
        "}",
        "",
        "/* 深色：Radix/Reflex 会在根节点加 .dark 类 */",
        "html.dark {",
        _decls(TOKENS_DARK),
        marker_css(True),
        "}",
        "",
        "/* 强调色覆盖（浅色） */",
    ]
    for accent, tokens in ACCENT_OVERRIDES.items():
        parts.append(f".nw-accent-{accent} {{")
        parts.append(_decls(tokens))
        parts.append("}")
    parts.append("")
    parts.append("/* 强调色覆盖（深色） */")
    for accent, tokens in ACCENT_OVERRIDES_DARK.items():
        parts.append(f"html.dark .nw-accent-{accent} {{")
        parts.append(_decls(tokens))
        parts.append("}")
    parts.append("")
    return "\n".join(parts)
