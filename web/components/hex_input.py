# -*- coding: utf-8 -*-
"""十六进制输入框组件：清洗、验证、占位符示例"""
import re
from nicegui import ui
from typing import Optional, Callable


class HexInput:
    def __init__(
        self,
        placeholder: str = "请输入十六进制报文，支持空格/逗号/换行分隔，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
        on_parse: Optional[Callable[[bytes], None]] = None,
        height: str = "100px",
    ):
        self.on_parse = on_parse
        self._placeholder = placeholder
        self._height = height
        self._textarea = None
        self._example_frames = {
            "确认帧": "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
            "复位硬件": "68 0C 00 40 01 00 01 01 02 E8 2D 16",
            "添加从节点": "68 1A 00 40 40 00 01 04 02 E8 02 AA AA AA AA BB BB BB BB 5C 16",
            "启动文件传输": "68 1C 00 40 07 00 01 07 02 E8 01 05 99 99 99 99 99 99 00 10 00 01 00 00 AB CD 0A 8F 16",
        }

    def build(self):
        with ui.card().classes("w-full shadow-md rounded-borders q-pa-md").style(
            "background: #f8f9fa; border: 1px solid #e0e0e0;"
        ):
            with ui.column().classes("w-full q-gutter-sm"):
                # 标题行：图标 + 标题 + 分割线
                with ui.row().classes("w-full items-center q-gutter-xs"):
                    ui.icon("data_object", size="20px", color="primary")
                    ui.label("报文输入").classes("text-subtitle1 text-weight-bold text-grey-8")
                    ui.space()
                    ui.html('<div class="header-line-divider flex-grow"></div>')

                self._textarea = ui.textarea(
                    placeholder=self._placeholder,
                ).classes("hex-input w-full").props(
                    f'dense rows=3 style="height: {self._height}; min-height: {self._height};"'
                )

                # 示例按钮行
                with ui.row().classes("q-gutter-xs q-mt-xs items-center"):
                    for name, frame in self._example_frames.items():
                        ui.button(
                            name,
                            icon="label",
                            on_click=lambda f=frame: self.load_example(f)
                        ).props("dense outline size=sm").classes("text-caption")

                    ui.space()
                    ui.button(
                        "清空",
                        icon="delete_sweep",
                        on_click=self.clear
                    ).props("dense outline size=sm color=negative").classes("text-caption")

    def load_example(self, frame: str):
        self._textarea.value = frame

    def clear(self):
        self._textarea.value = ""

    def get_bytes(self) -> Optional[bytes]:
        """获取清洗后的字节数据，失败返回 None 并显示错误通知"""
        raw = self._textarea.value or ""
        if not raw.strip():
            ui.notify("请输入报文内容", type="warning")
            return None

        # 清洗：去除 0x 前缀、空格、逗号、换行、制表符
        clean = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', raw)  # 0xF -> F
        clean = re.sub(r'[^0-9A-Fa-f]', '', clean)

        if not clean:
            ui.notify("输入不包含有效十六进制字符", type="negative")
            return None

        if len(clean) % 2 != 0:
            ui.notify("十六进制字符串长度必须为偶数", type="negative")
            return None

        try:
            frame_bytes = bytes.fromhex(clean)
            if self.on_parse:
                self.on_parse(frame_bytes)
            return frame_bytes
        except ValueError as ex:
            ui.notify(f"十六进制解析失败: {ex}", type="negative")
            return None

    @property
    def value(self) -> str:
        return self._textarea.value or ""

    @value.setter
    def value(self, val: str):
        self._textarea.value = val
