# -*- coding: utf-8 -*-
"""串口状态面板：端口选择、波特率、打开/关闭"""
from nicegui import ui
from typing import Optional, Callable, List


class SerialPanel:
    def __init__(
        self,
        on_open: Optional[Callable[[str, int, str], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ):
        self.on_open = on_open
        self.on_close = on_close
        self._adapter = None
        self._port_select = None
        self._baud_select = None
        self._parity_select = None
        self._open_btn = None
        self._status_label = None
        self._status_icon = None
        self._is_open = False

    def set_adapter(self, adapter):
        self._adapter = adapter
        adapter.register_callback('connection_changed', self._on_conn_changed)
        adapter.register_callback('error', lambda msg: ui.notify(f"串口错误: {msg}", type="negative"))

    def build(self):
        with ui.card().classes("w-full shadow-md rounded-borders q-pa-sm").style(
            "background: #f8f9fa; border: 1px solid #e0e0e0;"
        ):
            with ui.row().classes("items-center q-gutter-sm"):
                ui.html(
                    '<span class="material-icons" style="font-size:18px; color:#546e7a;">cable</span>'
                )
                ui.label("串口:").classes("text-sm")

                self._port_select = ui.select(
                    options=self._get_ports(),
                    value=self._get_ports()[0] if self._get_ports() else "",
                ).classes("w-32").props("dense outlined")

                ui.button(icon="refresh", on_click=self._refresh_ports).props("dense flat round size=sm").tooltip("刷新串口列表")

                ui.html(
                    '<span class="material-icons" style="font-size:18px; color:#546e7a;">speed</span>'
                )
                ui.label("波特率:").classes("text-sm")
                self._baud_select = ui.select(
                    options=["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"],
                    value="9600",
                ).classes("w-28").props("dense outlined")

                ui.label("校验:").classes("text-sm")
                self._parity_select = ui.select(
                    options=["无", "偶", "奇"],
                    value="无",
                ).classes("w-20").props("dense outlined")

                self._open_btn = ui.button(
                    "打开串口",
                    icon="link",
                    on_click=self._toggle_port,
                ).props("dense color=positive").classes("q-ml-sm")

                self._status_label = ui.label("未连接").classes("text-sm text-grey-7")
                self._status_icon = ui.html(
                    '<span class="material-icons" style="font-size:14px; color:#e53935;">radio_button_unchecked</span>'
                )

    def _get_ports(self) -> List[str]:
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
            return ports if ports else ["COM1", "COM2", "COM3", "COM4"]
        except Exception:
            return ["COM1", "COM2", "COM3", "COM4"]

    def _refresh_ports(self):
        ports = self._get_ports()
        self._port_select.options = ports
        if ports:
            self._port_select.value = ports[0]
        self._port_select.update()

    def _toggle_port(self):
        if not self._is_open:
            port = self._port_select.value
            baud = int(self._baud_select.value)
            parity_map = {"无": "N", "偶": "E", "奇": "O"}
            parity = parity_map.get(self._parity_select.value, "N")
            if not port:
                ui.notify("请选择串口", type="warning")
                return
            if self._adapter:
                ok = self._adapter.open(port, baud, parity)
                if not ok:
                    ui.notify("串口打开失败", type="negative")
            elif self.on_open:
                self.on_open(port, baud, parity)
        else:
            if self._adapter:
                self._adapter.close()
            elif self.on_close:
                self.on_close()

    def _on_conn_changed(self, connected: bool):
        self._is_open = connected
        if connected:
            self._open_btn.props(remove="color=positive", add="color=negative")
            self._open_btn.set_text("关闭串口")
            self._open_btn.set_icon("link_off")
            self._status_label.set_text(f"已连接: {self._port_select.value}")
            self._status_label.classes(remove="text-grey-7", add="text-green-7")
            self._status_icon.content = '<span class="material-icons" style="font-size:14px; color:#43a047;">radio_button_checked</span>'
            self._status_icon.update()
        else:
            self._open_btn.props(remove="color=negative", add="color=positive")
            self._open_btn.set_text("打开串口")
            self._open_btn.set_icon("link")
            self._status_label.set_text("未连接")
            self._status_label.classes(remove="text-green-7", add="text-grey-7")
            self._status_icon.content = '<span class="material-icons" style="font-size:14px; color:#e53935;">radio_button_unchecked</span>'
            self._status_icon.update()

    def set_connected(self, connected: bool, port: str = ""):
        self._is_open = connected
        if connected:
            self._open_btn.props(remove="color=positive", add="color=negative")
            self._open_btn.set_text("关闭串口")
            self._open_btn.set_icon("link_off")
            self._status_label.set_text(f"已连接: {port}")
            self._status_label.classes(remove="text-grey-7", add="text-green-7")
            self._status_icon.content = '<span class="material-icons" style="font-size:14px; color:#43a047;">radio_button_checked</span>'
            self._status_icon.update()
        else:
            self._open_btn.props(remove="color=negative", add="color=positive")
            self._open_btn.set_text("打开串口")
            self._open_btn.set_icon("link")
            self._status_label.set_text("未连接")
            self._status_label.classes(remove="text-green-7", add="text-grey-7")
            self._status_icon.content = '<span class="material-icons" style="font-size:14px; color:#e53935;">radio_button_unchecked</span>'
            self._status_icon.update()
