#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
协议解析工具 — TUI 版本 (基于 Textual)

支持 10 种电力通信协议的终端图形化解析：
  - 单帧解析 + 字节高亮
  - 批量多帧解析 + 摘要
  - 协议一致性校验

运行方式:
    python tui_app.py

依赖: textual, 以及项目内所有 parser/validator/lookup 模块
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 确保项目根目录在 sys.path 中 ──
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Textual ──
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)
from textual.widget import Widget
from textual import events
from rich.text import Text as RichText
from rich.style import Style

# ── 协议解析器 ──
from protocol_parser import ProtocolFrameParser
from plc_rf_parser import PLCRFProtocolParser
from hdlc_parser import HDLCParser
from dlt645_parser import DLT645Parser
from gdw10376_parser import GDW10376Parser
from dl_t698_45_parser import DLT69845Parser
from csg_new_gen_parser import CSGNewGenParser

# ── 校验器 ──
from validator import (
    NWValidator,
    GDWValidator,
    HDLCValidator,
    PLCRFValidator,
    DLT645Validator,
)
from validator.dl_t698_45_validator import DLT69845Validator
from validator.csg_new_gen_validator import CSGNewGenValidator

# ── 常量 ──
PROTOCOL_NAMES = [
    "南网协议 (Q/CSG1209021-2019)",       # 0
    "PLC RF 协议 (万胜海外)",             # 1
    "HDLC/国网DLMS (IEC 62056-46)",       # 2
    "DLMS-APDU(国网)",                    # 3
    "DLMS Wrapper 裸报文",                # 4
    "DLMS-APDU 裸报文",                   # 5
    "DLT645-2007 电表协议",              # 6
    "国网协议 (Q/GDW 10376.2-2024)",     # 7
    "698.45 协议 (DL/T 698.45-2017)",    # 8
    "新一代载波协议 (通感一体化)",         # 9
]

PROTOCOL_SHORT = [
    "南网",       # 0
    "PLC RF",     # 1
    "HDLC",       # 2
    "APDU(国网)", # 3
    "Wrapper",    # 4
    "APDU",       # 5
    "DLT645",     # 6
    "国网",       # 7
    "698.45",     # 8
    "新一代",     # 9
]

# 新一代载波协议监控日志前缀
CSG_MONITOR_PREFIX = "> 接收机 Has Get"
CSG_MONITOR_HEADER_BYTES = 15


# ═══════════════════════════════════════════════════════════════════
# 工具函数（从 main_gui.py 抽取，保持行为一致）
# ═══════════════════════════════════════════════════════════════════

def clean_hex_input(text: str, keep_newlines: bool = False) -> str:
    """预处理报文输入：去除空格、逗号、换行等分隔符，仅保留十六进制字符"""
    text = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', text)
    pattern = r'[^0-9A-Fa-f\n]' if keep_newlines else r'[^0-9A-Fa-f]'
    return re.sub(pattern, '', text)


def strip_csg_monitor_prefix(text: str) -> str:
    """剥离新一代载波协议监控日志前缀

    仅保留含 "> 接收机 Has Get" 标记的行，其余行（时间戳/测试标记/纯文本日志等）
    全部丢弃；对保留行剥离标记后 15 字节监控头，取第 16 字节起的协议报文。
    """
    prefix = CSG_MONITOR_PREFIX
    prefix_len = len(prefix)

    out_lines = []
    for line in text.splitlines():
        pos = line.find(prefix)
        if pos == -1:
            # 不含监控标记的行：直接丢弃
            continue
        after = line[pos + prefix_len:]
        tokens = re.findall(r'[0-9A-Fa-f]{1,2}', after)
        payload_tokens = tokens[CSG_MONITOR_HEADER_BYTES:]
        if payload_tokens:
            out_lines.append(' '.join(payload_tokens))
    return '\n'.join(out_lines)


def extract_frames_for_protocol(text: str, protocol_index: int) -> list:
    """根据协议提取对应格式的帧"""
    if protocol_index in (0, 7):
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return _extract_68_frames(clean)
    elif protocol_index == 8:
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return _extract_69845_frames(clean)
    elif protocol_index == 1:
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return _extract_generic_frames(clean)
    elif protocol_index == 2:
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return _extract_hdlc_frames(clean)
    elif protocol_index == 3:
        return [f.strip() for f in text.splitlines() if f.strip()]
    elif protocol_index == 4:
        return _extract_wrapper_frames(text)
    elif protocol_index == 5:
        return [f.strip() for f in text.splitlines() if f.strip()]
    elif protocol_index == 9:
        return _extract_csg_new_gen_frames(text)
    else:
        return [f.strip() for f in text.splitlines() if f.strip()]


def _extract_68_frames(clean: str) -> list:
    """提取南网/国网 68 格式帧"""
    frames = []
    i = 0
    while i < len(clean) - 7:
        pos = clean.find('68', i)
        if pos == -1:
            break
        if pos + 6 > len(clean):
            i = pos + 2
            continue
        try:
            low_byte = int(clean[pos + 2:pos + 4], 16)
            high_byte = int(clean[pos + 4:pos + 6], 16)
            length = low_byte | (high_byte << 8)
        except ValueError:
            i = pos + 2
            continue
        if length < 8 or length > 1024:
            i = pos + 2
            continue
        frame_hex_len = length * 2
        if pos + frame_hex_len > len(clean):
            i = pos + 2
            continue
        candidate = clean[pos:pos + frame_hex_len]
        if candidate[-2:] != '16':
            i = pos + 2
            continue
        frames.append(candidate)
        i = pos + frame_hex_len
    return frames


def _extract_69845_frames(clean: str) -> list:
    """提取 698.45 格式帧"""
    frames = []
    i = 0
    while i < len(clean) - 7:
        pos = clean.find('68', i)
        if pos == -1:
            break
        if pos + 6 > len(clean):
            i = pos + 2
            continue
        try:
            low_byte = int(clean[pos + 2:pos + 4], 16)
            high_byte = int(clean[pos + 4:pos + 6], 16)
            length = low_byte | (high_byte << 8)
        except ValueError:
            i = pos + 2
            continue
        if length < 8 or length > 2048:
            i = pos + 2
            continue
        total_len = length + 4
        frame_hex_len = total_len * 2
        if pos + frame_hex_len > len(clean):
            i = pos + 2
            continue
        candidate = clean[pos:pos + frame_hex_len]
        if candidate[-2:] != '16':
            i = pos + 2
            continue
        frames.append(candidate)
        i = pos + frame_hex_len
    return frames


def _extract_hdlc_frames(clean: str) -> list:
    """提取 HDLC 帧"""
    frames = []
    i = 0
    while i < len(clean) - 3:
        pos = clean.find('7E', i)
        if pos == -1:
            break
        end = clean.find('7E', pos + 2)
        if end == -1:
            end = min(pos + 512, len(clean))
        candidate = clean[pos:end + 2]
        if len(candidate) >= 6:
            frames.append(candidate)
        i = end + 2
    return frames


def _extract_wrapper_frames(text: str) -> list:
    """提取 Wrapper 帧"""
    frames = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        hex_matches = re.findall(r'[0-9A-Fa-f]{16,}', line)
        if not hex_matches:
            continue
        for hex_pattern in hex_matches:
            hex_pattern = hex_pattern.upper()
            i = 0
            while i <= len(hex_pattern) - 16:
                if hex_pattern[i:i + 4] == '0001':
                    apdu_len = int(hex_pattern[i + 12:i + 16], 16)
                    if 0 <= apdu_len <= 8192:
                        frame_len = 16 + apdu_len * 2
                        if i + frame_len <= len(hex_pattern):
                            frames.append(hex_pattern[i:i + frame_len])
                            i += frame_len
                            continue
                        else:
                            frames.append(hex_pattern[i:])
                            break
                i += 2
    return frames if frames else [re.sub(r'[^0-9A-Fa-f]', '', text).upper()]


def _extract_generic_frames(clean: str) -> list:
    """通用帧提取"""
    if len(clean) >= 8 and len(clean) <= 1024 and len(clean) % 2 == 0:
        return [clean]
    return []


def _extract_csg_new_gen_frames(text: str) -> list:
    """提取新一代载波协议帧"""
    frames = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        clean_line = ''.join(c for c in line if c in '0123456789ABCDEFabcdef').upper()
        if len(clean_line) < 8:
            continue
        if len(clean_line) % 2 != 0:
            clean_line = clean_line[:-1]
        frames.append(clean_line)
    return frames


# ═══════════════════════════════════════════════════════════════════
# TUI 应用
# ═══════════════════════════════════════════════════════════════════

class HexHighlighter(Static):
    """高亮显示 hex 字节的静态文本组件"""

    def show_hex(self, hex_str: str, highlight_start: int = -1, highlight_end: int = -1):
        """显示 hex 字符串，高亮指定字节范围"""
        rt = RichText()
        tokens = hex_str.replace(' ', '').strip()
        # 每 2 字符一个字节
        byte_offset = 0
        char_index = 0
        while char_index < len(tokens):
            if char_index + 2 <= len(tokens):
                byte_hex = tokens[char_index:char_index + 2]
            else:
                byte_hex = tokens[char_index:]
            byte_index = byte_offset

            if highlight_start <= byte_index <= highlight_end and highlight_start >= 0:
                rt.append(f"{byte_hex} ", style=Style(color="black", bgcolor="yellow", bold=True))
            else:
                rt.append(f"{byte_hex} ", style=Style(color="cyan"))

            char_index += 2
            byte_offset += 1

        self.update(rt)

    def show_empty(self):
        self.update(RichText("(无报文)", style=Style(dim=True)))


class ProtocolParserTUI(App):
    """协议解析工具 — TUI 主应用"""

    CSS_PATH = "tui_app.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "退出"),
        Binding("ctrl+p", "focus_input", "聚焦输入"),
        Binding("ctrl+r", "parse_current", "解析"),
        Binding("ctrl+v", "validate_current", "校验"),
        Binding("ctrl+b", "parse_batch", "批量解析"),
        Binding("f1", "show_help", "帮助"),
    ]

    def __init__(self):
        super().__init__()
        self.current_protocol = 0
        self._parsed_table_data: list = []
        self._parsed_bytes: bytes = b""
        self._batch_results: list = []

        # 初始化解析器
        self._parser_nw = ProtocolFrameParser()
        self._parser_plcrf = PLCRFProtocolParser()
        self._parser_hdlc = HDLCParser()
        self._parser_dlt645 = DLT645Parser()
        self._parser_gdw = GDW10376Parser()
        self._parser_69845 = DLT69845Parser()
        self._parser_csg = CSGNewGenParser()

        # 初始化校验器
        self._validators = {
            0: NWValidator(),
            1: PLCRFValidator(),
            2: HDLCValidator(),
            3: HDLCValidator(),       # DLMS-APDU(国网)
            4: HDLCValidator(),       # Wrapper
            5: HDLCValidator(),       # APDU
            6: DLT645Validator(),
            7: GDWValidator(),
            8: DLT69845Validator(),
            9: CSGNewGenValidator(),  # 新一代载波
        }

    # ── 布局 ──

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="top-bar"):
            with Horizontal(id="protocol-bar"):
                yield Label("当前协议:", id="proto-label")
                yield Select(
                    [(name, idx) for idx, name in enumerate(PROTOCOL_NAMES)],
                    value=0,
                    id="protocol-select",
                )

        with TabbedContent(id="main-tabs"):
            # ── Tab 1: 单帧解析 ──
            with TabPane("单帧解析", id="tab-single"):
                with Vertical(id="single-layout"):
                    with Horizontal(id="single-input-bar"):
                        yield Input(
                            placeholder="输入十六进制报文 (如: 68 11 01 01...)",
                            id="single-input",
                        )
                    yield HexHighlighter("", id="hex-highlight")
                    with Container(id="result-container"):
                        yield DataTable(id="result-table", cursor_type="row")

            # ── Tab 2: 批量解析 ──
            with TabPane("批量解析", id="tab-batch"):
                with Vertical(id="batch-layout"):
                    yield TextArea.code_editor(
                        "",
                        language="text",
                        id="batch-input",
                    )
                    yield Label("", id="batch-stats")
                    yield DataTable(id="batch-summary-table", cursor_type="row")

            # ── Tab 3: 校验 ──
            with TabPane("校验", id="tab-validate"):
                with Vertical(id="validate-layout"):
                    yield Label("", id="validate-status")
                    yield DataTable(id="validate-table", cursor_type="row")

        yield Footer()

    # ── 挂载后初始化 ──

    def on_mount(self) -> None:
        """应用启动后初始化表格列"""
        self.title = "协议解析工具 (TUI)"
        self.sub_title = PROTOCOL_SHORT[0]

        # 协议选择变更事件
        select = self.query_one("#protocol-select", Select)
        select.focus()

        # 初始化结果表格
        result_table = self.query_one("#result-table", DataTable)
        result_table.add_column("字段名", width=22)
        result_table.add_column("原始值", width=18)
        result_table.add_column("解析值", width=22)
        result_table.add_column("说明", width=40)

        # 初始化批量摘要表格
        batch_table = self.query_one("#batch-summary-table", DataTable)
        batch_table.add_column("#", width=4)
        batch_table.add_column("状态", width=6)
        batch_table.add_column("摘要", width=60)

        # 初始化校验表格
        val_table = self.query_one("#validate-table", DataTable)
        val_table.add_column("校验项", width=20)
        val_table.add_column("级别", width=8)
        val_table.add_column("期望值", width=12)
        val_table.add_column("实际值", width=12)
        val_table.add_column("说明", width=30)

        # 设置输入框焦点
        self.set_focus(self.query_one("#single-input", Input))

    # ── 协议切换 ──

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "protocol-select":
            self.current_protocol = event.value
            self.sub_title = PROTOCOL_SHORT[self.current_protocol]
            self.notify(f"已切换到: {PROTOCOL_NAMES[self.current_protocol]}", timeout=2)
            self._clear_results()

    # ── 单帧解析 ──

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """输入框回车触发解析"""
        if event.input.id == "single-input":
            self.action_parse_current()

    def action_focus_input(self) -> None:
        self.set_focus(self.query_one("#single-input", Input))

    def action_parse_current(self) -> None:
        """解析当前单帧输入"""
        input_widget = self.query_one("#single-input", Input)
        raw_text = input_widget.value.strip()
        if not raw_text:
            self.notify("请输入报文内容", severity="warning")
            return

        # 清洗输入
        clean = clean_hex_input(raw_text)
        if not all(c in '0123456789abcdefABCDEF' for c in clean):
            self.notify("输入包含非法字符", severity="error")
            return
        if len(clean) % 2 != 0:
            self.notify("十六进制字符串必须是偶数长度", severity="error")
            return

        try:
            frame_bytes = bytes.fromhex(clean)
        except ValueError as e:
            self.notify(f"hex 解析失败: {e}", severity="error")
            return

        # 格式化显示
        hex_display = ' '.join(f'{b:02X}' for b in frame_bytes)
        input_widget.value = hex_display
        self._parsed_bytes = frame_bytes

        # 高亮视图
        highlighter = self.query_one("#hex-highlight", HexHighlighter)
        highlighter.show_hex(hex_display)

        # 解析
        try:
            parser = self._get_current_parser()
            table_data = parser.parse_to_table(frame_bytes)
        except Exception as e:
            self.notify(f"解析失败: {e}", severity="error")
            return

        self._parsed_table_data = table_data
        self._populate_result_table(table_data)

    def _populate_result_table(self, table_data: list) -> None:
        """填充结果 DataTable"""
        table = self.query_one("#result-table", DataTable)
        table.clear()

        for row in table_data:
            if len(row) >= 6:
                field, raw, parsed, desc, b_start, b_end = row[0], row[1], row[2], row[3], row[4], row[5]
            elif len(row) >= 4:
                field, raw, parsed, desc = row[0], row[1], row[2], row[3]
                b_start = b_end = None
            else:
                continue

            # 格式化为字符串
            raw_str = str(raw) if raw else "-"
            parsed_str = str(parsed) if parsed else (raw_str if raw else "-")
            desc_str = str(desc) if desc else "-"

            # 用 Rich Text 标记错误行
            if "❌" in str(field):
                field_rt = RichText(str(field), style=Style(color="red", bold=True))
                table.add_row(field_rt, raw_str, parsed_str, desc_str, key=f"row-{len(table.rows)}")
            elif "⚠" in str(field) or "警告" in str(field):
                field_rt = RichText(str(field), style=Style(color="yellow"))
                table.add_row(field_rt, raw_str, parsed_str, desc_str, key=f"row-{len(table.rows)}")
            else:
                table.add_row(field, raw_str, parsed_str, desc_str, key=f"row-{len(table.rows)}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """点击表格行时高亮对应字节；批量摘要行点击查看详情"""
        # 批量摘要表格：点击行查看该帧详情
        if event.data_table.id == "batch-summary-table":
            row_idx = event.cursor_row
            if 0 <= row_idx < len(self._batch_results):
                result = self._batch_results[row_idx]
                if "_table_data" in result:
                    self._parsed_table_data = result["_table_data"]
                    if "_bytes" in result:
                        self._parsed_bytes = result["_bytes"]
                        hex_display = ' '.join(f'{b:02X}' for b in self._parsed_bytes)
                        highlighter = self.query_one("#hex-highlight", HexHighlighter)
                        highlighter.show_hex(hex_display)
                    else:
                        try:
                            self._parsed_bytes = bytes.fromhex(result["_input"])
                            hex_display = ' '.join(f'{b:02X}' for b in self._parsed_bytes)
                            highlighter = self.query_one("#hex-highlight", HexHighlighter)
                            highlighter.show_hex(hex_display)
                        except Exception:
                            pass
                    self._populate_result_table(self._parsed_table_data)
                    tabs = self.query_one("#main-tabs", TabbedContent)
                    tabs.active = "tab-single"
            return

        # 结果表格：点击行高亮对应字节
        if event.data_table.id != "result-table":
            return

        row_idx = event.cursor_row
        if row_idx < 0 or row_idx >= len(self._parsed_table_data):
            return

        row = self._parsed_table_data[row_idx]
        if len(row) >= 6:
            b_start = row[4]
            b_end = row[5]
            if b_start is not None and b_end is not None:
                hex_display = ' '.join(f'{b:02X}' for b in self._parsed_bytes)
                highlighter = self.query_one("#hex-highlight", HexHighlighter)
                highlighter.show_hex(hex_display, highlight_start=b_start, highlight_end=b_end)

    # ── 批量解析 ──

    def action_parse_batch(self) -> None:
        """批量解析"""
        textarea = self.query_one("#batch-input", TextArea)
        input_text = textarea.text.strip()
        if not input_text:
            self.notify("请输入批量报文内容", severity="warning")
            return

        # 新一代协议需要先剥离监控前缀
        if self.current_protocol == 9:
            input_text = strip_csg_monitor_prefix(input_text)

        input_text = clean_hex_input(input_text, keep_newlines=True)

        frames = extract_frames_for_protocol(input_text, self.current_protocol)
        if not frames:
            self.notify("未识别到有效帧", severity="warning")
            return

        self._batch_results = []
        success_count = 0
        fail_count = 0

        for i, frame_hex in enumerate(frames):
            try:
                frame_bytes = bytes.fromhex(frame_hex)
                parser = self._get_current_parser()
                table_data = parser.parse_to_table(frame_bytes)

                is_failed = any("❌ 解析失败" in str(item[0]) for item in table_data)

                if is_failed:
                    status = "失败"
                    fail_count += 1
                    summary = next((str(item[3]) for item in table_data if "❌ 解析失败" in str(item[0])), "解析失败")
                else:
                    status = "成功"
                    success_count += 1
                    summary = self._get_summary(table_data)

                self._batch_results.append({
                    "_input": frame_hex,
                    "_bytes": frame_bytes,
                    "_status": status,
                    "_table_data": table_data,
                    "摘要": summary,
                })
            except Exception as e:
                fail_count += 1
                self._batch_results.append({
                    "_input": frame_hex,
                    "_status": "异常",
                    "摘要": str(e)[:60],
                })

        # 填充批量摘要表格
        batch_table = self.query_one("#batch-summary-table", DataTable)
        batch_table.clear()
        for i, result in enumerate(self._batch_results):
            status = result["_status"]
            summary = result.get("摘要", "-")
            # Rich style for status
            if status == "成功":
                status_rt = RichText(status, style=Style(color="green"))
            elif status == "失败":
                status_rt = RichText(status, style=Style(color="red", bold=True))
            else:
                status_rt = RichText(status, style=Style(color="yellow"))
            batch_table.add_row(str(i + 1), status_rt, summary, key=f"batch-{i}")

        # 更新统计
        stats_label = self.query_one("#batch-stats", Label)
        stats_label.update(f"共 {len(frames)} 帧 | 成功 {success_count} | 失败 {fail_count}")

        self.notify(f"批量解析完成: {len(frames)} 帧, 成功 {success_count}, 失败 {fail_count}")

    def _get_summary(self, table_data: list) -> str:
        """根据协议从表格数据提取摘要"""
        if not table_data:
            return "-"

        if self.current_protocol == 0:
            # 南网协议
            parts = []
            for item in table_data:
                field, parsed, comment = str(item[0]), str(item[2]), str(item[3])
                if "应用功能码 (AFN)" in field and comment:
                    parts.append(f"AFN:{comment}")
                elif "帧序列号 (SEQ)" in field:
                    parts.append(f"SEQ:{parsed}")
                elif "数据标识 (DI)" in field and comment:
                    parts.insert(0, f"DI:{comment}")
            return " | ".join(parts) if parts else "-"

        elif self.current_protocol == 7:
            # 国网协议
            parts = []
            for item in table_data:
                field, parsed, comment = str(item[0]), str(item[2]), str(item[3])
                if "应用功能码 (AFN)" in field and comment:
                    parts.append(f"AFN:{comment}")
                elif "帧序列号 (SEQ)" in field:
                    parts.append(f"SEQ:{parsed}")
            return " | ".join(parts) if parts else "-"

        elif self.current_protocol in (2, 3, 4, 5):
            # HDLC/DLMS 系列
            for item in table_data:
                field = str(item[0])
                if "帧类型" in field and str(item[2]):
                    return f"帧类型: {item[2]}"
            return "HDLC/DLMS 帧"

        elif self.current_protocol == 9:
            # 新一代载波
            return self._get_csg_summary(table_data)

        # 通用：取前几个有意义的字段
        parts = []
        for item in table_data[:5]:
            field = str(item[0])
            val = str(item[2]) if item[2] else str(item[3]) if item[3] else ""
            if val and val != "-" and not field.startswith("❌"):
                parts.append(val[:30])
        return " | ".join(parts[:3]) if parts else "-"

    def _get_csg_summary(self, table_data: list) -> str:
        """新一代载波协议摘要"""
        msdu_type = None
        frame_type = None
        service_id = None
        direction = None

        for item in table_data:
            field = str(item[0])
            val = str(item[2]) if item[2] else str(item[3])
            if "MSDU类型" in field:
                msdu_type = val
            elif "帧类型" in field:
                frame_type = val
            elif "业务标识" in field:
                service_id = val
            elif "方向" in field:
                direction = val

        parts = []
        if msdu_type:
            parts.append(f"MSDU:{msdu_type}")
        if frame_type:
            parts.append(f"帧:{frame_type}")
        if service_id:
            parts.append(f"业务:{service_id}")
        if direction:
            parts.append(f"方向:{direction}")
        return " | ".join(parts) if parts else "-"

    # ── 校验 ──

    def action_validate_current(self) -> None:
        """校验当前单帧报文"""
        if not self._parsed_bytes:
            self.notify("请先解析一帧报文", severity="warning")
            return

        self._run_validation(self._parsed_bytes)

    def _run_validation(self, frame_bytes: bytes) -> None:
        """执行协议校验并展示结果"""
        validator = self._validators.get(self.current_protocol)
        if not validator:
            self.notify("当前协议无校验器", severity="warning")
            return

        try:
            result = validator.verify(frame_bytes)
        except Exception as e:
            self.notify(f"校验失败: {e}", severity="error")
            return

        # 更新状态标签
        status_label = self.query_one("#validate-status", Label)
        status_label.update(
            f"[{PROTOCOL_SHORT[self.current_protocol]}] {result.summary()}"
        )

        # 填充校验表格
        val_table = self.query_one("#validate-table", DataTable)
        val_table.clear()

        for check in result.checks:
            level_str = {
                "pass": "✅ 通过",
                "fail": "❌ 失败",
                "warn": "⚠️ 警告",
            }.get(check.level.value if hasattr(check.level, 'value') else str(check.level), str(check.level))

            val_table.add_row(
                check.name,
                level_str,
                check.expected,
                check.actual,
                check.message,
            )

        # 切换到校验 tab
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = "tab-validate"

    # ── 帮助 ──

    def action_show_help(self) -> None:
        """显示帮助信息"""
        help_text = (
            f"[bold]协议解析工具 TUI v1.0[/bold]\n\n"
            f"[bold]快捷键:[/bold]\n"
            f"  Ctrl+P  - 聚焦输入框\n"
            f"  Ctrl+R  - 解析当前帧 (或 Enter)\n"
            f"  Ctrl+V  - 校验当前帧\n"
            f"  Ctrl+B  - 批量解析\n"
            f"  Ctrl+Q  - 退出\n"
            f"  F1      - 显示帮助\n\n"
            f"[bold]Tab 切换:[/bold] 点击对应标签页\n\n"
            f"[bold]支持 10 种协议:[/bold]\n"
        )
        for i, name in enumerate(PROTOCOL_NAMES):
            help_text += f"  {i}. {name}\n"
        self.notify("帮助已输出到通知栏", timeout=4)

        # 在通知中显示简化版
        self.notify(
            "快捷键: Ctrl+P 聚焦 | Ctrl+R 解析 | Ctrl+V 校验 | Ctrl+B 批量 | Ctrl+Q 退出",
            timeout=8,
        )

    # ── 清理 ──

    def _clear_results(self) -> None:
        """清空所有解析结果"""
        self._parsed_table_data = []
        self._parsed_bytes = b""
        self._batch_results = []

        result_table = self.query_one("#result-table", DataTable)
        result_table.clear()

        highlighter = self.query_one("#hex-highlight", HexHighlighter)
        highlighter.show_empty()

        batch_table = self.query_one("#batch-summary-table", DataTable)
        batch_table.clear()

        val_table = self.query_one("#validate-table", DataTable)
        val_table.clear()

        stats_label = self.query_one("#batch-stats", Label)
        stats_label.update("")

        status_label = self.query_one("#validate-status", Label)
        status_label.update("")

    # ── 获取当前解析器（与 main_gui.py 的 _get_current_parser 行为一致）──

    def _get_current_parser(self):
        """获取当前协议对应的解析器"""
        if self.current_protocol == 0:
            return self._parser_nw
        elif self.current_protocol == 1:
            return self._parser_plcrf
        elif self.current_protocol == 2:
            return self._parser_hdlc
        elif self.current_protocol == 3:
            # DLMS-APDU(国网)
            hdlc = self._parser_hdlc
            class APDUParserGW:
                def parse_to_table(self, data):
                    return hdlc.parse_apdu_to_table(data)
            return APDUParserGW()
        elif self.current_protocol == 4:
            # Wrapper
            hdlc = self._parser_hdlc
            class WrapperParser:
                def parse_to_table(self, data):
                    return hdlc.parse_wrapper_to_table(data)
            return WrapperParser()
        elif self.current_protocol == 5:
            # APDU
            hdlc = self._parser_hdlc
            class APDUParser:
                def parse_to_table(self, data):
                    return hdlc.parse_apdu_to_table(data)
            return APDUParser()
        elif self.current_protocol == 6:
            # DLT645
            dlt645 = self._parser_dlt645
            class DLT645GuiParser:
                def parse_to_table(self, data):
                    result = dlt645.parse(data)
                    table = []
                    data_len = result.get('data_length', 0)
                    total_len = 10 + data_len + 2

                    for field, raw, desc in result['fields']:
                        byte_start = 0
                        byte_end = 0
                        parsed_value = ''

                        if '帧起始符 1' in field:
                            byte_start, byte_end = 0, 0
                        elif '从站地址' in field:
                            byte_start, byte_end = 1, 6
                        elif '帧起始符 2' in field:
                            byte_start, byte_end = 7, 7
                        elif '控制码' in field:
                            byte_start, byte_end = 8, 8
                            parsed_value = result.get('control_parsed', '')
                        elif '数据长度' in field:
                            byte_start, byte_end = 9, 9
                        elif '数据标识 DI' in field:
                            byte_start, byte_end = 10, 13
                            di_code = result.get('di_code', '')
                            di_desc = result.get('di_desc', '')
                            parsed_value = f"{di_code} ({di_desc})" if di_code and di_desc else di_code
                        elif '数据内容' in field:
                            byte_start, byte_end = 14, 10 + data_len - 1
                        elif '数据域' in field:
                            byte_start, byte_end = 10, 10 + data_len - 1
                        elif '校验和' in field:
                            byte_start, byte_end = total_len - 2, total_len - 2
                        elif '帧结束符' in field:
                            byte_start, byte_end = total_len - 1, total_len - 1

                        table.append((field, raw, parsed_value, desc, byte_start, byte_end))
                    return table

            return DLT645GuiParser()
        elif self.current_protocol == 7:
            return self._parser_gdw
        elif self.current_protocol == 8:
            return self._parser_69845
        elif self.current_protocol == 9:
            csg = self._parser_csg

            class CSGGenGuiParser:
                def parse_to_table(self, data):
                    return csg.parse_to_table(data, parse_level="auto")

            return CSGGenGuiParser()
        else:
            return self._parser_nw


# ═══════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = ProtocolParserTUI()
    app.run()
