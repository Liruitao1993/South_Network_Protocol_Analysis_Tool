# -*- coding: utf-8 -*-
"""单帧解析标签页"""
from nicegui import ui
from web.components.hex_input import HexInput
from web.components.parse_table import ParseTable
from web.components.byte_highlighter import ByteHighlighter
from web.protocol_registry import make_parser, make_validator


class SingleParseTab:
    def __init__(self, protocol_selector):
        self.protocol_selector = protocol_selector
        self.current_protocol = 0
        self.parser = make_parser(0)
        self.validator = make_validator(0)
        self._frame_bytes = b''
        self._parse_table = None
        self._hex_input = None
        self._verify_label = None
        self._raw_bytes_html = None
        self._btn_crc24 = None
        self._btn_crc32 = None

    @staticmethod
    def _section_header(icon: str, title: str, color: str = "primary"):
        """统一卡片头部：图标 + 标题 + 分割线"""
        with ui.row().classes("w-full items-center q-mb-sm"):
            ui.icon(icon, color=color, size="24px").classes("q-mr-sm")
            ui.label(title).classes("text-subtitle1 text-weight-bold text-grey-9")
            ui.space()
            ui.html('<div class="header-line-divider flex-grow"></div>')

    def build(self):
        # 注入 html2canvas 库（用于导出图片）
        ui.add_head_html(
            '<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>'
        )
        with ui.column().classes("w-full h-full q-pa-md q-gutter-md").style("overflow: auto;"):
            # 输入区 - HexInput 自身已包含卡片，不再外层嵌套
            self._hex_input = HexInput(
                on_parse=self._on_parse,
                height="80px",
            )
            self._hex_input.build()

            # 操作按钮 - 分两组：核心操作 + CRC工具
            with ui.card().classes("w-full shadow-1 rounded-borders py-2 px-3"):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.row().classes("items-center q-gutter-sm"):
                        with ui.row().classes("items-center q-gutter-xs"):
                            ui.icon("bolt", color="primary", size="20px")
                            ui.label("核心操作").classes("text-xs text-grey-6 text-weight-medium")
                        ui.button("解析报文", icon="play_arrow", on_click=self._do_parse).props("dense color=primary unelevated").classes("toolbar-btn rounded-btn").tooltip("解析输入的十六进制报文")
                        ui.button("校验报文", icon="verified", on_click=self._do_verify).props("dense color=info unelevated").classes("toolbar-btn rounded-btn").tooltip("执行协议一致性校验")
                        ui.button("添加到测试方案", icon="add_task", on_click=self._add_to_test).props("dense color=positive outline").classes("toolbar-btn rounded-btn").tooltip("将当前报文加入测试方案")

                    with ui.row().classes("items-center q-gutter-sm"):
                        ui.separator().props("vertical")
                        with ui.row().classes("items-center q-gutter-xs"):
                            ui.icon("shield", color="orange", size="20px")
                            ui.label("CRC工具").classes("text-xs text-grey-6 text-weight-medium")
                        self._btn_crc24 = ui.button("CRC-24", icon="fingerprint", on_click=self._fill_crc24).props("dense color=orange outline").classes("toolbar-btn rounded-btn").tooltip("新一代载波 CRC-24")
                        self._btn_crc32 = ui.button("CRC-32", icon="fingerprint", on_click=self._fill_crc32).props("dense color=purple outline").classes("toolbar-btn rounded-btn").tooltip("新一代载波 CRC-32")
                        self._btn_crc24.set_visibility(False)
                        self._btn_crc32.set_visibility(False)

            # 结果区
            with ui.splitter(value=70).classes("w-full").style("flex: 1; min-height: 0;") as splitter:
                with splitter.before:
                    with ui.card().classes("w-full h-full shadow-2 rounded-borders"):
                        self._section_header("analytics", "解析结果")
                        self._parse_table = ParseTable(
                            on_row_click=self._on_row_highlight,
                            on_row_double_click=self._on_row_double_click,
                            on_export_image=self._export_image,
                        )
                        self._parse_table.build()

                with splitter.after:
                    with ui.card().classes("w-full h-full shadow-2 rounded-borders"):
                        with ui.tabs().classes("w-full detail-tabs") as detail_tabs:
                            tab_verify = ui.tab("校验结果", icon="check_circle")
                            tab_raw = ui.tab("原始字节", icon="memory")

                        with ui.tab_panels(detail_tabs, value=tab_verify).classes("w-full h-[calc(100%-48px)]"):
                            with ui.tab_panel(tab_verify):
                                self._verify_label = ui.label("点击「校验报文」按钮进行协议一致性校验").classes("q-pa-md text-grey-7")
                                self._verify_label.style("white-space: pre-wrap; font-family: monospace; font-size: 12px;")

                            with ui.tab_panel(tab_raw):
                                self._raw_bytes_html = ui.html("").classes("q-pa-md")
                                self._raw_bytes_html.style("overflow: auto; height: 100%; font-family: monospace; font-size: 12px;")

    def on_protocol_change(self, protocol_idx: int):
        """协议切换回调"""
        self.current_protocol = protocol_idx
        self.parser = make_parser(protocol_idx)
        self.validator = make_validator(protocol_idx)

        # CRC 按钮仅在新一代载波协议(9)下显示
        if self._btn_crc24:
            self._btn_crc24.set_visibility(protocol_idx == 9)
        if self._btn_crc32:
            self._btn_crc32.set_visibility(protocol_idx == 9)

        # 更新占位符提示
        placeholders = {
            0: "南网协议示例: 68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
            1: "PLC RF示例: 68 0A 01 00 00 00 01 02 03 04 16",
            2: "HDLC示例: 7E A0 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 7E",
            6: "DLT645示例: 68 12 34 56 78 90 01 01 00 00 00 00 00 00 00 00 16",
            7: "国网协议示例: 68 10 00 00 00 00 01 00 01 00 00 00 00 00 00 00 00 00 00 00 16",
            8: "698.45示例: 68 0A 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 16",
            9: "新一代载波示例: 11 01 01 00 00 00 00 01 00 01 00 00 ...",
        }
        if self._hex_input:
            self._hex_input._placeholder = placeholders.get(protocol_idx, "请输入十六进制报文")
            self._hex_input._textarea.props(f'placeholder="{self._hex_input._placeholder}"')
            self._hex_input._textarea.update()

    def _on_parse(self, frame_bytes: bytes):
        """HexInput 回调：解析并填充表格"""
        self._frame_bytes = frame_bytes
        self._do_parse_internal(frame_bytes)

    def _do_parse(self):
        """解析按钮点击"""
        frame_bytes = self._hex_input.get_bytes()
        if frame_bytes:
            self._do_parse_internal(frame_bytes)

    def _do_parse_internal(self, frame_bytes: bytes):
        """内部解析逻辑"""
        try:
            # 协议特定预处理
            if self.current_protocol == 9:  # 新一代载波
                parse_level = self.protocol_selector.current_csg_level
                strip_head = self.protocol_selector.strip_head or 0
                strip_tail = self.protocol_selector.strip_tail or 0
                # 在调用 parser 前手动剥离首尾字节（与 main_gui.py 一致）
                if strip_head > 0 or strip_tail > 0:
                    total = len(frame_bytes)
                    tail_end = total - strip_tail if strip_tail > 0 else total
                    if strip_head >= tail_end:
                        ui.notify(
                            f"剔除字节数过多（前{strip_head}+尾{strip_tail}），"
                            f"超出报文总长{total}字节", type="warning")
                        return
                    frame_bytes = frame_bytes[strip_head:tail_end]
                    self._frame_bytes = frame_bytes
                result = self.parser.parse_to_table(
                    frame_bytes,
                    parse_level=parse_level,
                )
            else:
                result = self.parser.parse_to_table(frame_bytes)

            self._parse_table.set_data(result, frame_bytes)

            # 显示原始字节
            html = ByteHighlighter.highlight_bytes(frame_bytes, [])
            self._raw_bytes_html.set_content(html)

            ui.notify(f"解析完成，共 {len(result)} 行", type="positive")
        except Exception as e:
            ui.notify(f"解析失败: {e}", type="negative")
            import traceback
            traceback.print_exc()

    def _do_verify(self):
        """校验按钮点击"""
        frame_bytes = self._hex_input.get_bytes()
        if not frame_bytes:
            return

        try:
            result = self.validator.verify(frame_bytes)
            # 格式化显示
            lines = [f"[{'通过' if result.valid else '失败'}] {result.summary()}"]
            for check in result.checks:
                icon = "✅" if check.level.value == "pass" else "❌" if check.level.value == "fail" else "⚠️"
                lines.append(f"  {icon} {check.name}: 期望={check.expected}, 实际={check.actual} - {check.message}")
            if result.warnings:
                for w in result.warnings:
                    lines.append(f"  ⚠️ {w}")
            if result.errors:
                for e in result.errors:
                    lines.append(f"  ❌ {e}")

            self._verify_label.set_text("\n".join(lines))
            ui.notify(result.summary(), type="positive" if result.valid else "negative")
        except Exception as e:
            ui.notify(f"校验出错: {e}", type="negative")

    def _on_row_highlight(self, start: int, end: int):
        """行点击：高亮原始字节"""
        if start is not None and end is not None and self._frame_bytes:
            ranges = [(start, end)] if start <= end else []
            html = ByteHighlighter.highlight_bytes(self._frame_bytes, ranges)
            self._raw_bytes_html.set_content(html)

    def _on_row_double_click(self, field: str, start: int, end: int):
        """双击行：提取 APDU 重新解析 (DLMS/HDLC)"""
        if self.current_protocol in (2, 3, 4, 5) and "APDU" in field.upper():
            if start is not None and end is not None and start <= end:
                apdu_bytes = self._frame_bytes[start:end+1]
                # TODO: 弹窗显示 DLMSDeepParser 结果
                ui.notify(f"双击提取 APDU: {len(apdu_bytes)} 字节，深度解析待实现", type="info")

    def _add_to_test(self):
        """添加到测试方案"""
        frame_hex = self._frame_bytes.hex().upper()
        # TODO: 发送信号给 TestPlanTab
        ui.notify(f"已添加到测试方案: {frame_hex[:32]}...", type="positive")

    def _fill_crc24(self):
        """填充 CRC-24 (新一代载波)"""
        ui.notify("CRC-24 填充待实现", type="info")

    def _fill_crc32(self):
        """填充 CRC-32 (新一代载波 MAC帧)"""
        ui.notify("CRC-32 填充待实现", type="info")

    async def _export_image(self):
        """用 html2canvas 截取解析结果表格，导出为 PNG"""
        if not self._parse_table:
            ui.notify("无解析结果可导出", type="warning")
            return
        js_code = """
        (async () => {
            const el = document.querySelector('.q-card');
            if (!el) return null;
            const canvas = await html2canvas(el, {
                backgroundColor: '#ffffff',
                scale: 2,
                useCORS: true,
                logging: false,
            });
            return canvas.toDataURL('image/png');
        })()
        """
        try:
            result = await ui.run_javascript(js_code, timeout=10)
        except Exception:
            result = None
        if not result or not result.startswith('data:image/png;base64,'):
            ui.notify('截图失败', type='negative')
            return
        import base64
        b64 = result.split(',', 1)[1]
        img_bytes = base64.b64decode(b64)
        ui.download(img_bytes, 'parse_result.png')
        ui.notify('已导出图片', type='positive')
