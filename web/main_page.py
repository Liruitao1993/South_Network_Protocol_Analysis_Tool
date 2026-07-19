# coding: utf-8
"""Main page layout with fixed header, tab bar, and scrollable content areas."""
"""主页面布局：顶部栏 + 标签页容器"""
import logging
import re
from pathlib import Path
from nicegui import ui
from web.components.protocol_selector import ProtocolSelector

log = logging.getLogger("web.main_page")


def _read_version() -> str:
    """从 main_gui.py 文本中解析 APP_VERSION，避免 import PySide6。"""
    try:
        text = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
            encoding="utf-8", errors="ignore"
        )
        m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "1.0.0"


class MainPage:
    TAB_REGISTRY = {
        "single":  ("web.tabs.single_parse", "SingleParseTab"),
        "lookup":  ("web.tabs.lookup", "LookupTab"),
        "batch":   ("web.tabs.batch_parse", "BatchParseTab"),
        "frame":   ("web.tabs.frame_gen", "FrameGenTab"),
        "diff":    ("web.tabs.diff", "DiffTab"),
    }

    def __init__(self):
        self.protocol_selector = ProtocolSelector()
        self._tab_instances = {}
        self._version = _read_version()

    def build(self):
        HEADER_H = 72
        FOOTER_H = 32
        CSG_CTRLS_H = 56
        TAB_BAR_H = 44

        # ── Header ──────────────────────────────────────────────────
        with ui.header().classes("app-header").style(
            f"height: {HEADER_H}px; min-height: {HEADER_H}px;"
        ):
            with ui.row().classes("w-full h-full items-center px-5 no-wrap"):
                # Logo + Title
                with ui.row().classes("items-center gap-2.5"):
                    ui.icon("electrical_services", size="28px", color="white")
                    ui.label("南网协议解析工具").classes(
                        "text-h6 font-bold text-white no-wrap"
                    )

                # Vertical divider
                ui.html('<div class="header-vdivider"></div>').classes(
                    "p-0 m-0 flex items-center"
                )

                # Protocol selector (only the selector part, not CSG controls)
                self.protocol_selector.build_selector()

                # Spacer
                ui.space()

                # Version badge
                with ui.row().classes("items-center gap-1.5 version-badge px-3 py-1 rounded-full"):
                    ui.icon("tag", size="12px", color="white")
                    ui.label(f"v{self._version}").classes("text-xs text-white font-medium")

                # Status indicator
                with ui.row().classes("items-center gap-1.5 ml-3 px-3 py-1 rounded-full bg-white/15"):
                    ui.html('<span class="status-dot"></span>').classes("p-0 m-0")
                    ui.label("就绪").classes("status-text text-xs text-white")

        # ── Main content area ───────────────────────────────────────
        # CSG 控制条（仅新一代载波显示）
        self.protocol_selector.build_csg_controls()

        # ── Tab definitions ─────────────────────────────────────────
        tab_defs = [
            ("single", "单帧解析", "list_alt"),
            ("lookup", "查询", "search"),
            ("batch", "批量解析", "dynamic_feed"),
            ("frame", "协议组帧", "edit_note"),
            ("diff", "报文对比", "compare_arrows"),
        ]

        # ── Pill-style tab bar ──────────────────────────────────────
        with ui.tabs().classes("app-tab-bar w-full") as tab_bar:
            tabs = {}
            for key, label, icon in tab_defs:
                tabs[key] = ui.tab(label, icon=icon)

        # ── Tab panels: 固定高度 + 内容滚动，避免顶栏重叠 ───────────
        # Tab panels with fixed height - inner areas scroll independently

        content_h = f"calc(100vh - {HEADER_H + FOOTER_H + CSG_CTRLS_H + 44}px)"
        with ui.tab_panels(tab_bar, value=tabs["single"]).classes("w-full").style("height: calc(100vh - 204px); overflow: hidden;"):
            for key, _, _ in tab_defs:
                with ui.tab_panel(tabs[key]).classes("w-full").style("height: 100%;"):
                    self._build_tab(key)


        with ui.tab_panels(tab_bar, value=tabs["single"]).classes(
            "w-full"
        ):            for key, _, _ in tab_defs:
                with ui.tab_panel(tabs[key]).classes("w-full").style("height: 100%;"):
                    self._build_tab(key)

        # ── Footer ──────────────────────────────────────────────────
        with ui.footer().classes("app-footer").style(
            f"height: {FOOTER_H}px; min-height: {FOOTER_H}px;"
        ):
            with ui.row().classes("w-full h-full items-center justify-between px-5"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("info_outline", size="14px").classes("text-gray-400")
                    ui.label("南网协议解析工具 · 南方电网协议解析与调试").classes(
                        "text-xs text-gray-500"
                    )
                with ui.row().classes("items-center gap-3"):
                    ui.label("NiceGUI Web 版").classes("text-xs text-gray-400")
                    ui.html('<div class="footer-vdivider"></div>')
                    ui.label(f"v{self._version}").classes("text-xs text-gray-400")

        # ── Protocol change handler ─────────────────────────────────
        def _on_protocol_change(proto_idx):
            for inst in self._tab_instances.values():
                if hasattr(inst, "on_protocol_change"):
                    inst.on_protocol_change(proto_idx)

        self.protocol_selector._on_change = _on_protocol_change

    def _build_tab(self, key):
        reg = self.TAB_REGISTRY.get(key)
        if not reg:
            return
        module_path, class_name = reg
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            instance = cls(self.protocol_selector)
            instance.build()
            self._tab_instances[key] = instance
            log.info("Tab '%s' built", key)
        except Exception as ex:
            log.error("Failed to build tab '%s': %s", key, ex)
            ui.notify(f"标签页加载失败: {ex}", type="negative")
