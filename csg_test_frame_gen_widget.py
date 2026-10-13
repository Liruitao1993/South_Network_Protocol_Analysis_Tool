# -*- coding: utf-8 -*-
"""协议9（新一代载波 / 通感一体化）测试帧组帧面板。

自包含子控件：模式清单（A 新测试ID / B 2.0 测试扩展ID / C 表61 原有模式）
→ 参数表单（由 ``csg_new_gen_frame_gen.ModeField`` 自动生成，界面不硬编码模式个数）
→ 应用层/业务报文头参数 + ED 封装参数 → 组帧。

输出统一交给父控件（``FrameGenWidget``）的 ``result_hex`` 与 ``preview_table`` 呈现；
预览里除了四层帧，还会把 BDU **回读解析**一遍（组帧即对拍，肉眼可见字段是否对得上）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import csg_frame_reverse as rev
import csg_frame_templates as tpl
import csg_link_frame_gen as link
import csg_new_gen_frame_gen as fg
from batch_core import build_ed_header_rows
from collapsible_section import (
    CollapsibleSection,
    apply_state,
    collapse_all,
    collect_state,
    expand_all,
)
from csg_new_gen_parser import CSGNewGenParser

# 参数名 → 位宽上限（未列出的按 16bit）
_FIELD_MAX: Dict[str, int] = {
    "band": 0xF,
    "node_count": 0x7,
    "ofdma_type": 0x1,
    "enable": 0x1,
    "frame_type": 0x3,
    "stream_count": 0x2,
    "proto_version": 0x3F,
    "header_len": 0x3F,
    "protocol_type": 0xF,
    "security_mode": 0xF,
    "phr_mcs": 0xF,
    "psdu_mcs": 0xF,
    "pb_size": 0xF,
    "tei": 0xFFF,
    "src_tei": 0xFFF,
    "dst_tei": 0xFFF,
    "value": 0xFFF,
    "mapping_mode": 0xFF,
    "subcarrier_group": 0xFF,
    "agg_count": 0xFF,
    "neg_version": 0xFF,
    "file_len": 0xFF,
    "cutoff_carrier": 0xFFFF,
    "bps": 0xFFFF,
    "physical_channel": 0xFF,
    "pb_count": 0xFF,
    "ctrl1": 0xFF,
    "ctrl2": 0xFF,
    "timestamp": 0xFFFFFFFF,
    "pb_len": 0xFFFF,
}

_PORT_OPTIONS = ((fg.MSG_PORT_MANAGE, "0x13 管理报文(模块)"), (fg.MSG_PORT_BUSINESS, "0x11 业务报文(转发)"))
_FRAME_TYPE_OPTIONS = (
    (fg.FRAME_TYPE_CMD, "0x2 命令帧"),
    (fg.FRAME_TYPE_DATA, "0x1 数据传输帧"),
    (fg.FRAME_TYPE_CONFIRM, "0x0 确认/否认"),
    (fg.FRAME_TYPE_REPORT, "0x3 主动上报"),
)
_WRAPPER_OPTIONS = (("plc2", "PLC2.0（9B 公共头）"), ("gx", "广西台体（8B 公共头）"))
_CS_OPTIONS = (("ff", "填 0xFF（文档当前口径）"), ("sum", "按字节和计算"))
#: 输出层次（前 3 档为 1.23.64 既有语义，不可改动/移除；mpdu 为本次新增）
_LAYER_OPTIONS = (
    ("ed", "ED 封装（推荐下发）"),
    ("app", "应用层帧"),
    ("bdu", "仅测试帧 BDU"),
    ("mpdu", "整帧 MPDU（FC + 物理块）"),
)

#: 帧类型（定界符类型）→ (link 常量, 显示名)；第一期支持 SOF / 信标 / SACK
_FRAME_KIND_OPTIONS = (
    ("sof", "SOF 帧（数据/管理帧，携带物理块）"),
    ("beacon", "信标帧（无物理块头，FC 后直接载荷）"),
    ("sack", "选择确认帧（仅 FC 头 16 字节）"),
)

#: 通道
_CHANNEL_OPTIONS = (("plc", "PLC 载波"), ("hrf", "HRF 无线（二期）"))

#: 物理块总大小候选 → 显示名（BPLC 仅前两项可用，由 _rebuild_link_fields 过滤）
_PB_SIZE_OPTIONS = ((136, "136 字节（默认，块体 128）"), (520, "520 字节（块体 512）"),
                    (264, "264 字节（块体 256，ISAC）"), (72, "72 字节（块体 64，ISAC）"),
                    (16, "16 字节（块体 8，ISAC）"))


@dataclass(frozen=True)
class LinkFieldSpec:
    """链路层表单字段（界面据此生成控件，避免在 UI 里硬编码几十个字段）。"""

    name: str
    label: str
    kind: str = "int"          # int | choice | hex | mac
    maximum: int = 0xFFF
    default: object = 0
    choices: Tuple[Tuple[object, str], ...] = ()
    help: str = ""
    kinds: Tuple[str, ...] = ()   # 适用的 frame_kind；空 = 全部


def _lk(name, label, maximum=0xFFF, default=0, help="", kinds=(), kind="int"):
    return LinkFieldSpec(name, label, kind=kind, maximum=maximum, default=default,
                         help=help, kinds=tuple(kinds))


#: ① FC 帧控制字段。
#: 注意：同一 ``name`` 只创建**一个**控件（对应 ``LinkFrameConfig`` 里的一个字段），
#: ``kinds`` 表示该控件在哪些帧类型下可见 —— 例如「源TEI」在 SOF 与信标帧都要填，
#: 但它们是同一个配置字段，故合并为一条（default 以首个出现者为准，用户可改）。
_FC_FIELDS: Tuple[LinkFieldSpec, ...] = (
    # —— 公共 ——
    _lk("snid", "短网络标识(SNID)", 31, 1, "5bit，有效 1~31；高位自动拆分到可变区域"),
    _lk("access_indicator", "接入指示", 1, 1,
        "必须为 1：解析器据此判定输入为 MPDU，置 0 则整帧不走 MPDU 路径"),
    _lk("src_tei", "源TEI", 0xFFF, 0x123, "12bit", kinds=("sof", "beacon")),
    _lk("dest_tei", "目的TEI", 0xFFF, 0x456, "12bit", kinds=("sof", "sack")),
    _lk("frame_len_10us", "帧长", 0xFFF, 100, "单位 10μs；回读显示为 帧长×10μs", kinds=("sof",)),
    # —— SOF（BPLC 专用）——
    _lk("link_id", "链路标识符（BPLC）", 0xFF, 0x37, "优先级/业务分类", kinds=("sof",)),
    _lk("ext_cmt_index", "扩展载波映射表索引（BPLC）", 0xF, 0,
        "仅当载波映射表索引=0xD 时有效", kinds=("sof",)),
    _lk("tei_filter", "TEI过滤标志位", 1, 1, "本规约固定为 1", kinds=("sof",)),
    _lk("retransmit", "重传标志位", 1, 0, "1 = 重传报文", kinds=("sof",)),
    _lk("symbol_count", "符号数", 0x1FF, 0x155, "OFDM 符号个数", kinds=("sof",)),
    # —— SOF（ISAC-PLC 专用）——
    _lk("bitloading", "Bitloading标识（ISAC）", 1, 0,
        "1 用 Bitloading（填物理块大小码）；0 用 TMI", kinds=("sof",)),
    _lk("streams", "流数（ISAC）", 3, 0, "0 → 1流 / 1 → 2流", kinds=("sof",)),
    _lk("tf_symbols_cfg", "TF符号数配置（ISAC）", 7, 0, "实际符号数 = (值+1)×2", kinds=("sof",)),
    _lk("pl_band", "PL频段标识（ISAC）", 7, 0, "见第3部分 5.1.9.5 表17", kinds=("sof",)),
    _lk("tf_ext_band", "TF扩展频段（ISAC）", 1, 0, "0 与PL同频段 / 1 扩展到0.7~12M", kinds=("sof",)),
    # —— 信标 ——
    _lk("beacon_timestamp", "信标时间戳", 0xFFFFFFFF, 0x11223344, "32bit", kinds=("beacon",)),
    _lk("beacon_cycle", "信标周期计数", 0xFFFFFFFF, 0x55667788, "32bit", kinds=("beacon",)),
    _lk("beacon_phase", "相线", 3, 0, "0 未知/1 A相/2 B相/3 C相", kinds=("beacon",)),
    # —— SACK ——
    _lk("sack_rx_result", "接收结果", 0xF, 0, "0 全部成功 / 1 存在PB校验失败", kinds=("sack",)),
    _lk("sack_rx_status", "接收状态", 0xF, 0x0F, "每 bit 一个 PB 校验结果", kinds=("sack",)),
    _lk("sack_rx_pb_count", "接收物理块个数", 0xF, 1, "含解析错误的 PB", kinds=("sack",)),
    _lk("sack_snr_type", "SNR类型", 3, 0, "0 不携带 / 1 当前帧SNR / 2 基础RU", kinds=("sack",)),
    _lk("sack_snr_value", "SNR值", 31, 0, "SNR类型=1 时使用（5bit，0~31）", kinds=("sack",)),
)

#: ③ MAC 帧头字段
_MAC_FIELDS: Tuple[LinkFieldSpec, ...] = (
    _lk("tx_seq", "发送序号", 0xFFF, 0x009, "12bit"),
    _lk("reboot_count", "重启次数", 0xF, 2, "0~15，达到上限从 0 重新递增"),
    _lk("hop_count", "路由跳数", 0xF, 0, "单播=0 / 本地广播=1 / 全网广播按实际"),
    _lk("max_send", "发送次数限值", 0x1F, 3, "0 = 使用本地默认重发次数"),
    _lk("msdu_seq", "MSDU序列号", 0xFFFF, 7, "递增序列号"),
)

#: ④ MSDU 头字段
_MSDU_FIELDS: Tuple[LinkFieldSpec, ...] = (
    _lk("vlan", "VLAN标签", 0xFFFF, 0, "优先级分组；0~3 或 0x8100"),
    _lk("msdu_dest_mac", "原始目的地址（长头）", kind="mac", default=b"\xFF" * 6),
    _lk("msdu_src_mac", "原始源地址（长头）", kind="mac", default=b"\xFF" * 6),
)

#: 组帧模式数量（唯一来源 = csg_new_gen_frame_gen.test_modes()，避免文案写死后与真实模式数漂移）
_MODE_COUNT = len(fg.test_modes())

#: MSDU 载荷来源
_PAYLOAD_SOURCE_OPTIONS = (("mode", f"测试模式（复用现有 {_MODE_COUNT} 个模式）"), ("hex", "手工 HEX（优先）"))

#: 仅 ISAC-PLC 版本出现的 FC 字段（BPLC 用另一组）
_ISAC_ONLY_FIELDS = {"bitloading", "streams", "tf_symbols_cfg", "pl_band", "tf_ext_band"}
#: 仅 BPLC 版本出现的 FC 字段
_BPLC_ONLY_FIELDS = {"link_id", "ext_cmt_index"}
#: 需要按 MAC 地址文本（`AA:BB:...`）解析的字段
_LINK_MAC_FIELDS = {"dest_mac", "msdu_dest_mac", "msdu_src_mac"}

#: 各层字段名**全集**：回填 / 模板按名字读写，不因当前帧类型切走了字段而丢键
#: （例如先存了信标帧模板，再加载时字段控件是按当前帧类型动态建的，故先在 apply 里
#: 切 frame_kind / 标准版本、把控件建出来，再逐字段写值）。
_FC_FIELD_NAMES: Tuple[str, ...] = tuple(spec.name for spec in _FC_FIELDS)
_MAC_FIELD_NAMES: Tuple[str, ...] = tuple(spec.name for spec in _MAC_FIELDS)
_MSDU_FIELD_NAMES: Tuple[str, ...] = tuple(spec.name for spec in _MSDU_FIELDS)
#: 模板 / 回填 state 的架构版本（字段口径变化时递增，旧模板仍尽力读）
_STATE_VERSION = 1


class _WideIntEdit(QLineEdit):
    """承载**装不进 QSpinBox** 的宽整数字段（32bit 时间戳/周期）。

    QSpinBox 的上限是 C++ int（``0x7FFFFFFF``），而 ED 时间戳是真实 Unix 秒量级
    （``0x68xxxxxx`` > ``0x7FFFFFFF``）、信标时间戳/周期是满 32bit —— 用 QSpinBox
    装不下：既填不进去，回填时 ``setValue`` 还会直接抛 ``OverflowError``
    （与 ① 区 32bit 字段同一类坑）。文本框接受十进制或 ``0x`` 十六进制。
    """

    def __init__(self, value: int = 0, parent: Optional[QWidget] = None):
        super().__init__(f"0x{int(value) & 0xFFFFFFFF:X}", parent)
        self.setMinimumWidth(110)
        self.setToolTip("32bit 字段：可填十进制或 0x 十六进制")

    def value(self) -> int:
        text = self.text().strip()
        if not text:
            return 0
        try:
            return int(text, 0) & 0xFFFFFFFF
        except ValueError:
            raise fg.FrameBuildError(
                f"32bit 字段取值非法：{text!r}（可填十进制或 0x 十六进制）") from None

    def value_or_text(self):
        """给 frame_state 用：能解析就给整数，否则原样给文本（不丢用户输入）。"""
        try:
            return self.value()
        except fg.FrameBuildError:
            return self.text()


def _write_widget_value(widget: QWidget, value) -> bool:
    """把值写进任意表单控件；返回是否写成功。

    QSpinBox 必须**先夹到控件范围**再 setValue：越界会抛 ``OverflowError``（C++ int），
    这正是"回填 32bit 时间戳直接崩"的根因。
    """
    if value is None:
        return False
    try:
        if isinstance(widget, _WideIntEdit):
            widget.setText(f"0x{int(value) & 0xFFFFFFFF:X}")
            return True
        if isinstance(widget, QComboBox):
            index = widget.findData(value)
            if index < 0:
                return False
            widget.setCurrentIndex(index)
            return True
        if isinstance(widget, QLineEdit):
            if isinstance(value, (bytes, bytearray)):
                widget.setText(bytes(value).hex(" ").upper())
            else:
                widget.setText(str(value))
            return True
        number = int(value)
        widget.setValue(max(widget.minimum(), min(number, widget.maximum())))
        return True
    except (TypeError, ValueError):
        return False


def _read_widget_value(widget: QWidget):
    """从表单控件读值（宽整数文本框给整数，不行就给文本）。"""
    if isinstance(widget, _WideIntEdit):
        return widget.value_or_text()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, QLineEdit):
        return widget.text()
    return widget.value()


def _mac_text_to_bytes(text: str) -> bytes:
    """把 ``AA:BB:CC:DD:EE:FF`` / ``AABBCCDDEEFF`` 文本转 6 字节 MAC 地址。

    空串或无法解析时回落到广播地址 ``FF×6``（与链路层默认值一致），
    不抛异常——否则用户少填一位就会让整个组帧按钮失效。
    """
    cleaned = "".join(ch for ch in str(text or "") if ch not in " :-_")
    if not cleaned:
        return b"\xFF" * 6
    try:
        data = bytes.fromhex(cleaned)
    except ValueError:
        return b"\xFF" * 6
    return data if len(data) == 6 else b"\xFF" * 6


class CsgTestFrameGenWidget(QWidget):
    """协议9 测试帧组帧面板（模式 + 参数 + 层次选择）。"""

    changed = Signal()

    def __init__(self, parent=None, link_layer_default: bool = False):
        super().__init__(parent)
        self._field_widgets: Dict[str, QWidget] = {}
        #: 「组装链路层」开关的初始值。独立使用时默认关闭（输出=应用层帧/ED 封装）；
        #: GUI 组帧页（FrameGenWidget）传 True —— 进协议9 组帧页即按 ①②③ 折叠区
        #: 参数组装完整 MPDU，SOF 帧是默认帧类型。
        self._link_layer_default = bool(link_layer_default)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # ---- 模式选择 ----
        mode_group = QGroupBox("测试模式（协议9 · 通感一体化）")
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(6, 4, 6, 4)
        mode_layout.setSpacing(6)
        mode_layout.addWidget(QLabel("测试模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(420)
        for mode in fg.test_modes():
            # 分组用文本前缀体现（不用 insertSeparator：PySide6 下会挤掉相邻项）
            self.mode_combo.addItem(f"{mode.group} · {mode.name}", mode.key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(QLabel("输出:"))
        self.layer_combo = QComboBox()
        for value, label in _LAYER_OPTIONS:
            self.layer_combo.addItem(label, value)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        mode_layout.addWidget(self.layer_combo)

        # 链路层开关：不勾选 → 行为与 1.23.64 完全一致（仅应用层帧/ED 封装）；
        # 勾选 → 按 ①~③ 折叠区参数组装完整 MPDU。
        self.link_enable_check = QCheckBox("组装链路层（FC + 物理块 + MAC 头）")
        self.link_enable_check.setToolTip(
            "勾选后按 ①FC / ②物理块 / ③MAC 头 的参数组装完整 MPDU 帧；\n"
            "不勾选则仅输出应用层帧 / ED 封装（与既有行为一致）")
        # setChecked 必须在 connect 之前：此处 ①②③ 折叠区尚未构建，
        # 提前发 toggled 会让 _apply_link_visibility 撞上不存在的 self.sections。
        self.link_enable_check.setChecked(self._link_layer_default)
        self.link_enable_check.toggled.connect(self._on_link_enable_toggled)
        mode_layout.addWidget(self.link_enable_check)

        mode_layout.addStretch()
        self.expand_all_btn = QPushButton("展开全部")
        self.expand_all_btn.clicked.connect(self._expand_all_sections)
        mode_layout.addWidget(self.expand_all_btn)
        self.collapse_all_btn = QPushButton("收起全部")
        self.collapse_all_btn.clicked.connect(self._collapse_all_sections)
        mode_layout.addWidget(self.collapse_all_btn)
        layout.addWidget(mode_group)

        # ---- 模式参数（按 ModeField 动态生成） ----
        self.form_group = QGroupBox("测试模式参数")
        self.form_layout = QFormLayout(self.form_group)
        self.form_layout.setContentsMargins(6, 4, 6, 4)
        self.form_layout.setSpacing(4)
        layout.addWidget(self.form_group)

        # ---- 应用层 / 业务报文头 ----
        hdr_group = QGroupBox("应用层 / 业务报文头")
        hdr_layout = QHBoxLayout(hdr_group)
        hdr_layout.setContentsMargins(6, 4, 6, 4)
        hdr_layout.setSpacing(6)

        hdr_layout.addWidget(QLabel("端口:"))
        self.hdr_port = QComboBox()
        for value, label in _PORT_OPTIONS:
            self.hdr_port.addItem(label, value)
        hdr_layout.addWidget(self.hdr_port)

        hdr_layout.addWidget(QLabel("帧类型:"))
        self.hdr_frame_type = QComboBox()
        for value, label in _FRAME_TYPE_OPTIONS:
            self.hdr_frame_type.addItem(label, value)
        hdr_layout.addWidget(self.hdr_frame_type)

        hdr_layout.addWidget(QLabel("方向:"))
        self.hdr_dir = QComboBox()
        self.hdr_dir.addItem("0-下行(CCO→STA)", 0)
        self.hdr_dir.addItem("1-上行(STA→CCO)", 1)
        hdr_layout.addWidget(self.hdr_dir)

        hdr_layout.addWidget(QLabel("PRM:"))
        self.hdr_prm = QComboBox()
        self.hdr_prm.addItem("1-启动站", 1)
        self.hdr_prm.addItem("0-从动站", 0)
        hdr_layout.addWidget(self.hdr_prm)

        hdr_layout.addWidget(QLabel("响应:"))
        self.hdr_response = QComboBox()
        self.hdr_response.addItem("1-需要应答", 1)
        self.hdr_response.addItem("0-不需要应答", 0)
        hdr_layout.addWidget(self.hdr_response)

        hdr_layout.addWidget(QLabel("优先级:"))
        self.hdr_priority = QSpinBox()
        self.hdr_priority.setRange(0, 0xF)
        hdr_layout.addWidget(self.hdr_priority)

        hdr_layout.addWidget(QLabel("版本:"))
        self.hdr_appver = QSpinBox()
        self.hdr_appver.setRange(0, 0xFF)
        self.hdr_appver.setValue(1)
        hdr_layout.addWidget(self.hdr_appver)

        hdr_layout.addWidget(QLabel("帧序号:"))
        self.hdr_seq = QSpinBox()
        self.hdr_seq.setRange(0, 0xFFFF)
        hdr_layout.addWidget(self.hdr_seq)

        for widget in (self.hdr_port, self.hdr_frame_type, self.hdr_dir, self.hdr_prm, self.hdr_response):
            widget.currentIndexChanged.connect(self._notify_changed)
        for widget in (self.hdr_priority, self.hdr_appver, self.hdr_seq):
            widget.valueChanged.connect(self._notify_changed)
        hdr_layout.addStretch()
        # 应用层/业务报文头参数始终可见：既有用法（调端口/帧类型/方向）不应被链路层开关影响，
        # 故留在顶层，不放进会被隐藏的 ④ 区。
        layout.addWidget(hdr_group)

        # ---- ED 封装参数（1.23.64 既有结构，改由 ⑤ 折叠区承载）----
        ed_group = QGroupBox("ED 封装（PLC2.0 收发机报文）")
        ed_layout = QHBoxLayout(ed_group)
        ed_layout.setContentsMargins(6, 4, 6, 4)
        ed_layout.setSpacing(6)

        self.ed_check = QCheckBox("生成 ED 封装")
        self.ed_check.setChecked(True)
        self.ed_check.toggled.connect(self._on_ed_toggled)
        ed_layout.addWidget(self.ed_check)

        ed_layout.addWidget(QLabel("包装:"))
        self.ed_wrapper = QComboBox()
        for value, label in _WRAPPER_OPTIONS:
            self.ed_wrapper.addItem(label, value)
        ed_layout.addWidget(self.ed_wrapper)

        ed_layout.addWidget(QLabel("CS:"))
        self.ed_cs = QComboBox()
        for value, label in _CS_OPTIONS:
            self.ed_cs.addItem(label, value)
        ed_layout.addWidget(self.ed_cs)

        ed_layout.addWidget(QLabel("物理信道:"))
        self.ed_channel = QSpinBox()
        self.ed_channel.setRange(0, 0xFF)
        self.ed_channel.setValue(0x01)
        self.ed_channel.setPrefix("0x")
        self.ed_channel.setDisplayIntegerBase(16)
        ed_layout.addWidget(self.ed_channel)

        ed_layout.addWidget(QLabel("时间戳:"))
        # 32bit 真实时间戳（0x68xxxxxx）装不进 QSpinBox（C++ int 上限 0x7FFFFFFF）
        self.ed_timestamp = _WideIntEdit(0)
        ed_layout.addWidget(self.ed_timestamp)

        ed_layout.addWidget(QLabel("物理块个数:"))
        self.ed_pbcount = QSpinBox()
        self.ed_pbcount.setRange(1, 0xFF)
        self.ed_pbcount.setValue(1)
        ed_layout.addWidget(self.ed_pbcount)

        ed_layout.addWidget(QLabel("物理块长度:"))
        self.ed_pblen = QSpinBox()
        self.ed_pblen.setRange(0, 0xFFFF)
        self.ed_pblen.setSpecialValueText("自动")
        ed_layout.addWidget(self.ed_pblen)

        for widget in (self.ed_wrapper, self.ed_cs):
            widget.currentIndexChanged.connect(self._notify_changed)
        for widget in (self.ed_channel, self.ed_pbcount, self.ed_pblen):
            widget.valueChanged.connect(self._notify_changed)
        # 时间戳是宽整数文本框（QLineEdit 系），信号是 textChanged
        self.ed_timestamp.textChanged.connect(self._notify_changed)
        ed_layout.addStretch()
        # ed_group 改由 ⑤ 折叠区承载（见下方 _build_link_sections）

        # ---- ①~⑤ 五层折叠区（链路层组帧）----
        self._build_link_sections(layout, ed_group)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #888;")
        layout.addWidget(self.hint_label)

        self._rebuild_fields()
        self._on_link_enable_toggled(self.link_enable_check.isChecked())

    # ------------------------------------------------------------------
    # 模式参数表单
    # ------------------------------------------------------------------
    def _on_mode_changed(self):
        self._rebuild_fields()
        self.changed.emit()

    def _on_ed_toggled(self, checked: bool):
        for widget in (
            self.ed_wrapper,
            self.ed_cs,
            self.ed_channel,
            self.ed_timestamp,
            self.ed_pbcount,
            self.ed_pblen,
        ):
            widget.setEnabled(bool(checked))
        self.changed.emit()

    def _clear_form(self):
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._field_widgets.clear()

    def _rebuild_fields(self):
        self._clear_form()
        mode = self.current_mode()
        if mode is None:
            return
        for field_def in mode.fields:
            widget = self._make_field_widget(field_def)
            self._field_widgets[field_def.name] = widget
            label = field_def.label
            if field_def.help:
                label = f"{field_def.label}（{field_def.help}）"
            self.form_layout.addRow(QLabel(label), widget)
        if not mode.fields:
            self.form_layout.addRow(QLabel("（该模式无附加参数）"), QLabel(""))
        self.hint_label.setText(
            f"当前模式：{mode.name}｜测试ID 0x{mode.test_id:02X}"
            + (f"｜扩展ID 0x{mode.ext_id:04X}" if mode.ext_id is not None else "")
            + ("｜表61 模式 " + str(mode.legacy_mode) if mode.legacy_mode is not None else "")
        )

    def _make_field_widget(self, field_def) -> QWidget:
        if field_def.kind == "choice" and field_def.choices:
            combo = QComboBox()
            for value, label in field_def.choices:
                combo.addItem(str(label), value)
            index = combo.findData(field_def.default)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.currentIndexChanged.connect(self._notify_changed)
            return combo
        if field_def.kind == "bytes":
            edit = QLineEdit()
            edit.setPlaceholderText("十六进制，可带空格，如 24 49 92")
            edit.setMinimumWidth(320)
            edit.textChanged.connect(self._notify_changed)
            return edit
        maximum = _FIELD_MAX.get(field_def.name, 0xFFFF)
        if maximum > 0x7FFFFFFF:
            # 同 _make_link_widget：满 32bit 模式参数（_FIELD_MAX 里的 timestamp=0xFFFFFFFF）
            # QSpinBox 装不下，setRange 会直接抛 OverflowError（当前模式表还没用到，属预留）
            edit = _WideIntEdit(int(field_def.default) if isinstance(field_def.default, int) else 0)
            edit.textChanged.connect(self._notify_changed)
            return edit
        spin = QSpinBox()
        spin.setRange(0, maximum)
        spin.setValue(int(field_def.default) if isinstance(field_def.default, int) else 0)
        if maximum > 0xFF:
            spin.setMaximum(0x7FFFFFFF if maximum > 0xFFFF else 0xFFFF)
        spin.valueChanged.connect(self._notify_changed)
        return spin

    # ------------------------------------------------------------------
    # 取值 / 组帧 / 预览
    # ------------------------------------------------------------------
    def current_mode(self):
        key = self.mode_combo.currentData()
        return fg.mode_by_key(key) if key else None

    def _params(self, mode) -> Dict[str, object]:
        params: Dict[str, object] = {}
        for field_def in mode.fields:
            widget = self._field_widgets.get(field_def.name)
            if widget is None:
                continue
            if isinstance(widget, _WideIntEdit):
                # 宽整数文本框（满 32bit）：取整数。**不能落到 QLineEdit 分支**按 HEX 文本
                # 转字节，否则 "0x68E1A2B3" 会被当成 4 个字节 68 E1 A2 B3
                params[field_def.name] = widget.value()
            elif isinstance(widget, QComboBox):
                params[field_def.name] = widget.currentData()
            elif isinstance(widget, QLineEdit):
                params[field_def.name] = fg.hex_to_bytes(widget.text())
            else:
                params[field_def.name] = widget.value()
        return params

    def _header(self) -> fg.BusinessHeader:
        return fg.BusinessHeader(
            frame_type=self.hdr_frame_type.currentData(),
            direction=self.hdr_dir.currentData(),
            prm=self.hdr_prm.currentData(),
            response=self.hdr_response.currentData(),
            priority=self.hdr_priority.value(),
            service_id=fg.SERVICE_TEST_FRAME,
            app_version=self.hdr_appver.value(),
            frame_seq=self.hdr_seq.value(),
        )

    def _ed_kwargs(self) -> Optional[Dict[str, object]]:
        """ED 封装参数。

        ⚠ 启用链路层时返回 ``None``：ED 封装的**对象要换成整帧 MPDU**（那才是能在信道
        收发的完整帧），由 :meth:`_attach_link_layer` 在 MPDU 组好后补做；若在此处就按
        应用层帧封装，ED 里包的就是不含 FC/MAC 的半截帧。未启用链路层时行为不变。
        """
        if not self.ed_check.isChecked() or self.link_enable_check.isChecked():
            return None
        kwargs: Dict[str, object] = {
            "wrapper": self.ed_wrapper.currentData(),
            "cs_mode": self.ed_cs.currentData(),
            "physical_channel": self.ed_channel.value(),
            "timestamp": self.ed_timestamp.value(),
            "pb_count": self.ed_pbcount.value(),
        }
        if self.ed_pblen.value() > 0:
            kwargs["pb_len"] = self.ed_pblen.value()
        return kwargs

    def _ed_kwargs_unconditional(self) -> Optional[Dict[str, object]]:
        """不受链路层开关影响的 ED 参数（供 MPDU 封装复用）。"""
        if not self.ed_check.isChecked():
            return None
        kwargs: Dict[str, object] = {
            "wrapper": self.ed_wrapper.currentData(),
            "cs_mode": self.ed_cs.currentData(),
            "physical_channel": self.ed_channel.value(),
            "timestamp": self.ed_timestamp.value(),
            "pb_count": self.ed_pbcount.value(),
        }
        if self.ed_pblen.value() > 0:
            kwargs["pb_len"] = self.ed_pblen.value()
        return kwargs

    def build(self) -> Optional[fg.FrameBuildResult]:
        """按当前配置组帧；参数非法时抛 ``FrameBuildError``。

        未勾选「组装链路层」时行为与 1.23.64 完全一致（仅应用层帧/ED 封装）；
        勾选后额外填充 FC / 物理块 / MAC 头 / MSDU / 整帧 MPDU。
        """
        mode = self.current_mode()
        if mode is None:
            return None
        result = fg.build_frame_from_mode(
            mode.key,
            self._params(mode),
            msg_port=self.hdr_port.currentData(),
            header=self._header(),
            ed=self._ed_kwargs(),
        )
        if self.link_enable_check.isChecked():
            self._attach_link_layer(result)
        return result

    def _attach_link_layer(self, result: fg.FrameBuildResult) -> None:
        """按 ①~④ 折叠区参数组装链路层，并把各层填进 ``result``。

        MSDU 载荷来源：手工 HEX 优先；否则用应用层帧（端口号+报文标识符+业务报文），
        这样解析器回读时能展开出「报文端口号 / 控制域 / 测试数据区」等字段。
        """
        cfg = self._link_config()
        manual = self.payload_hex_edit.text().strip()
        if cfg.frame_kind == "beacon":
            pass                                   # 信标载荷单独给（不走 MSDU）
        elif manual:
            cfg.msdu_payload = fg.hex_to_bytes(manual)
        else:
            cfg.msdu_payload = result.app_frame

        built = link.build_link_frame(cfg)
        result.fc = built.fc
        result.pb = built.pb or None
        result.mac_header = built.mac_header or None
        result.msdu = built.msdu or None
        result.mpdu = built.mpdu
        result.link_enabled = True
        if built.payload and not result.msdu:
            result.msdu = built.payload             # 信标帧：载荷即 MSDU 层内容

        # ED 封装改包**整帧 MPDU**（可在信道收发的完整帧），而不是应用层帧
        ed_kwargs = self._ed_kwargs_unconditional()
        if ed_kwargs is not None:
            result.ed_frame = fg.build_ed_frame(built.mpdu, **ed_kwargs)

    def output_layer(self) -> str:
        return self.layer_combo.currentData() or "ed"

    def output_bytes(self, result: fg.FrameBuildResult) -> Optional[bytes]:
        layer = self.output_layer()
        if layer == "bdu":
            return result.bdu
        if layer == "app":
            return result.app_frame
        if layer == "mpdu":
            return result.mpdu if result.has_link_layer() else result.app_frame
        if result.ed_frame is None:
            return result.app_frame
        return result.ed_frame

    def parse_rows(self, result: fg.FrameBuildResult) -> List[tuple]:
        """分层概览 + **整条应用层帧逐字段解析**（用协议9 解析器实测回读本帧）。

        预览主体是应用层帧的完整解析：报文端口号 → 报文标识符 → 保留 →
        控制域（含 6 个位域）→ 业务标识 → 应用版本号 → 帧序号 → 帧长 → 数据单元
        （测试帧再往下展开测试ID / 保留 / 数据区长度 / 测试数据区及其扩展字段）。
        带 ED 封装时，先展开 ED 头字段，再看其内层应用层帧。
        """
        rows: List[tuple] = []

        def add(name: str, raw: str, parsed: str, comment: str):
            rows.append((name, raw, parsed, comment))

        def extend(items):
            for item in items:
                it = tuple(item)
                add(
                    str(it[0]),
                    it[1] if len(it) > 1 else "",
                    it[2] if len(it) > 2 else "",
                    it[3] if len(it) > 3 else "",
                )

        add("【分层概览】", "", "", "")
        if result.has_link_layer():
            # 启用链路层时，按真实封装顺序补充 ①~④ 行（应用层与 ED 行保持既有文案）
            for name, key, desc in (
                ("① FC 帧控制", "fc", "定界符类型 + 接入指示 + SNID + 标准版本号 + FCCS(CRC-24 自动)"),
                ("② 物理块 PBH+PBCS", "pb", "物理块头(4B) + 块体(补零) + 保留 + PBCS(CRC-24 自动)"),
                ("③ MAC 帧头", "mac_header", "MAC 帧头 + MSDU长度 + TEI/跳数/发送类型 + 完整性校验(CRC-32 自动)"),
                ("④ MSDU", "msdu", "MSDU 头（随帧头类型 18/2 字节）+ 载荷"),
            ):
                value = getattr(result, key)
                if value is None:
                    continue
                add(name, value.hex(" ") if hasattr(value, "hex") else "", f"{len(value)} 字节", desc)
        add(
            "应用层帧",
            result.hex("app"),
            f"{len(result.app_frame)} 字节",
            "报文端口号 + 报文标识符 + 保留 + 业务报文",
        )
        add(
            "业务报文",
            result.hex("business"),
            f"{len(result.business_message)} 字节",
            "控制域 + 业务标识 + 应用版本号 + 帧序号 + 帧长 + 数据单元",
        )
        add(
            "测试帧 BDU",
            result.hex("bdu"),
            f"{len(result.bdu)} 字节",
            "业务标识 0xF0 的测试帧数据单元（测试ID + 保留 + 数据区长度 + 数据区）",
        )
        if result.has_link_layer():
            add(
                "整帧 MPDU",
                result.hex("mpdu"),
                f"{len(result.mpdu)} 字节",
                "FC + 物理块（+ 信标载荷 / 仅 FC 的 SACK）",
            )
        if result.ed_frame is not None:
            wrapper = self.ed_wrapper.currentData()
            wrapper_name = ("PLC2.0（9B 公共头）" if wrapper == "plc2"
                            else "广西台体（8B 公共头）")
            # 链路层开启时 ED 包的是**整帧 MPDU**（⑤），否则包应用层帧（④，1.23.64 既有文案）
            ed_name = "⑤ ED..EE 封装" if result.has_link_layer() else "④ ED 封装"
            ed_note = "，内含整帧 MPDU" if result.has_link_layer() else ""
            add(
                ed_name,
                result.hex("ed"),
                f"{len(result.ed_frame)} 字节",
                f"{wrapper_name}，CS={'0xFF' if self.ed_cs.currentData() == 'ff' else '按字节和'}"
                f"{ed_note}",
            )
            add("【ED 封装头字段】", "", "", "")
            try:
                extend(
                    build_ed_header_rows(
                        result.ed_frame,
                        protocol_index=9,
                        wrapper=self.ed_wrapper.currentData(),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 展开失败也必须可见，不能静默
                add("   ED 头解析失败", "", "", str(exc))

        if result.has_link_layer():
            add("【整帧 MPDU 逐字段回读】", "", "",
                "由协议9 解析器按 auto 级别回读整帧，核对组帧与解析是否同源一致")
            add("组帧与解析同源对拍", "", "", f"整帧 {len(result.mpdu)} 字节")
            try:
                extend(CSGNewGenParser().parse_to_table(result.mpdu, parse_level="auto"))
            except Exception as exc:  # noqa: BLE001
                add("❌ 整帧 MPDU 解析失败", "", "", str(exc))

        add("【应用层帧逐字段解析】", "", "", "由协议9 解析器回读本帧，用于核对组帧结果")
        try:
            extend(CSGNewGenParser().parse_to_table(result.app_frame))
        except Exception as exc:  # noqa: BLE001
            add("❌ 应用层解析失败", "", "", str(exc))
        return rows

    # ------------------------------------------------------------------
    # ①~⑤ 五层折叠区（链路层组帧）
    # ------------------------------------------------------------------
    def _build_link_sections(self, layout: QVBoxLayout, ed_group: QGroupBox) -> None:
        """构建 FC → 物理块 → MAC 头 → MSDU → ED 五层折叠区。

        层可见性由帧类型/标准版本/输出层次联动（见 :meth:`_apply_link_visibility`）：
        信标帧无物理块与 MAC 头，SACK 仅 FC 头，故它们的折叠区会整块隐藏。
        """
        self.link_field_widgets: Dict[str, QWidget] = {}
        self.sections: Dict[str, CollapsibleSection] = {}
        self._link_rows: Dict[str, List[Tuple[str, QWidget]]] = {}

        # ── ⓪ 仿照报文 / 模板（放在最前面：这是"从别人的帧出发"的入口动作）──
        self._build_mirror_section(layout)

        # ── ① FC 帧控制 ──
        fc_sec = CollapsibleSection("① FC 帧控制（16 字节，FCCS 自动计算）", key="fc")
        fc_sec.toggled.connect(self._notify_changed)
        top = QFormLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)

        self.fk_combo = QComboBox()
        for value, label in _FRAME_KIND_OPTIONS:
            self.fk_combo.addItem(label, value)
        self.fk_combo.currentIndexChanged.connect(self._on_frame_kind_changed)
        top.addRow(QLabel("帧类型:"), self.fk_combo)

        self.channel_combo = QComboBox()
        for value, label in _CHANNEL_OPTIONS:
            self.channel_combo.addItem(label, value)
        self.channel_combo.currentIndexChanged.connect(self._notify_changed)
        top.addRow(QLabel("通道:"), self.channel_combo)

        self.stdver_combo = QComboBox()
        for value, label in link.std_version_choices():
            self.stdver_combo.addItem(label, value)
        index = self.stdver_combo.findData(link.STD_VERSION_ISAC)
        self.stdver_combo.setCurrentIndex(index if index >= 0 else 0)
        self.stdver_combo.currentIndexChanged.connect(self._on_std_version_changed)
        top.addRow(QLabel("标准版本号:"), self.stdver_combo)
        fc_sec.content_layout().addLayout(top)

        # FC 变体字段（按帧类型 + 标准版本动态建）
        self.fc_form = QFormLayout()
        self.fc_form.setContentsMargins(0, 2, 0, 0)
        self.fc_form.setSpacing(4)
        fc_sec.content_layout().addLayout(self.fc_form)
        layout.addWidget(fc_sec)
        self.sections["fc"] = fc_sec

        # ── ② 物理块 ──
        pb_sec = CollapsibleSection("② 物理块 PBH（4 字节）+ PBCS", key="pb")
        pb_sec.toggled.connect(self._notify_changed)
        pb_form = QFormLayout()
        pb_form.setContentsMargins(0, 0, 0, 0)
        pb_form.setSpacing(4)

        self.pb_count_spin = QSpinBox()
        self.pb_count_spin.setRange(1, 4)
        self.pb_count_spin.setToolTip("物理块个数（1~4；无线信道仅支持 1 个）")
        self.pb_count_spin.valueChanged.connect(self._notify_changed)
        pb_form.addRow(QLabel("物理块个数:"), self.pb_count_spin)

        self.pb_size_combo = QComboBox()
        for value, label in _PB_SIZE_OPTIONS:
            self.pb_size_combo.addItem(label, value)
        self.pb_size_combo.setToolTip("物理块总大小；载波映射表索引/TMI 将按此自动反查")
        self.pb_size_combo.currentIndexChanged.connect(self._notify_changed)
        pb_form.addRow(QLabel("物理块大小:"), self.pb_size_combo)

        self.pb_seq_spin = QSpinBox()
        self.pb_seq_spin.setRange(0, 0xFFFF)
        self.pb_seq_spin.valueChanged.connect(self._notify_changed)
        pb_form.addRow(QLabel("起始序列号:"), self.pb_seq_spin)

        self.pb_agg_check = QCheckBox("聚合标志（级联头，二期支持）")
        self.pb_agg_check.setEnabled(False)
        pb_form.addRow(QLabel(""), self.pb_agg_check)
        pb_sec.content_layout().addLayout(pb_form)

        self.pb_cmt_label = QLabel("")
        self.pb_cmt_label.setStyleSheet("color: #888;")
        pb_sec.content_layout().addWidget(self.pb_cmt_label)
        layout.addWidget(pb_sec)
        self.sections["pb"] = pb_sec

        # ── ③ MAC 帧头 ──
        mac_sec = CollapsibleSection("③ MAC 帧头（32 或 12 字节）+ 完整性校验", key="mac")
        mac_sec.toggled.connect(self._notify_changed)
        mac_form = QFormLayout()
        mac_form.setContentsMargins(0, 0, 0, 0)
        mac_form.setSpacing(4)

        self.mac_hdr_combo = QComboBox()
        for value, label in link.mac_header_type_choices():
            self.mac_hdr_combo.addItem(label, value)
        self.mac_hdr_combo.setToolTip("帧头类型 0 = 32 字节长帧头（长 MSDU）/ 1 = 12 字节短帧头")
        self.mac_hdr_combo.currentIndexChanged.connect(self._on_mac_header_changed)
        mac_form.addRow(QLabel("帧头类型:"), self.mac_hdr_combo)

        self.mac_ver_combo = QComboBox()
        for value, label in link.mac_version_choices():
            self.mac_ver_combo.addItem(label, value)
        self.mac_ver_combo.setToolTip("标准帧协议（版本 2 单跳帧协议仅无线，二期支持）")
        self.mac_ver_combo.currentIndexChanged.connect(self._notify_changed)
        mac_form.addRow(QLabel("版本:"), self.mac_ver_combo)

        self.dest_mac_edit = self._make_mac_edit(bytes.fromhex("AABBCCDDEEFF"))
        mac_form.addRow(QLabel("目的MAC地址（长头）:"), self.dest_mac_edit)
        self._dest_mac_row = mac_form.rowCount() - 1

        self.bcast_combo = QComboBox()
        for value, label in link.broadcast_dir_choices():
            self.bcast_combo.addItem(label, value)
        self.bcast_combo.currentIndexChanged.connect(self._notify_changed)
        mac_form.addRow(QLabel("广播方向:"), self.bcast_combo)

        self.send_type_combo = QComboBox()
        for value, label in link.send_type_choices():
            self.send_type_combo.addItem(label, value)
        self.send_type_combo.currentIndexChanged.connect(self._notify_changed)
        mac_form.addRow(QLabel("发送类型:"), self.send_type_combo)

        for spec in _MAC_FIELDS:
            widget = self._make_link_widget(spec)
            self.link_field_widgets[spec.name] = widget
            self._link_rows.setdefault("mac", []).append((spec.name, widget))
            mac_form.addRow(QLabel(self._field_label(spec)), widget)
        mac_sec.content_layout().addLayout(mac_form)
        layout.addWidget(mac_sec)
        self.sections["mac"] = mac_sec

        # ── ④ MSDU ──
        msdu_sec = CollapsibleSection("④ MSDU（头 + 载荷）", key="msdu")
        msdu_sec.toggled.connect(self._notify_changed)
        msdu_form = QFormLayout()
        msdu_form.setContentsMargins(0, 0, 0, 0)
        msdu_form.setSpacing(4)

        self.payload_src_combo = QComboBox()
        for value, label in _PAYLOAD_SOURCE_OPTIONS:
            self.payload_src_combo.addItem(label, value)
        self.payload_src_combo.setToolTip(
            f"测试模式：复用应用层 {_MODE_COUNT} 个测试模式作为 MSDU 载荷；\n手工 HEX：直接粘贴十六进制（优先）")
        self.payload_src_combo.currentIndexChanged.connect(self._on_payload_source_changed)
        msdu_form.addRow(QLabel("载荷来源:"), self.payload_src_combo)

        self.msdu_type_combo = QComboBox()
        for value, label in link.msdu_type_choices():
            self.msdu_type_combo.addItem(label, value)
        self.msdu_type_combo.currentIndexChanged.connect(self._notify_changed)
        msdu_form.addRow(QLabel("MSDU类型:"), self.msdu_type_combo)
        for spec in _MSDU_FIELDS:
            widget = self._make_link_widget(spec)
            self.link_field_widgets[spec.name] = widget
            self._link_rows.setdefault("msdu", []).append((spec.name, widget))
            msdu_form.addRow(QLabel(self._field_label(spec)), widget)

        self.payload_hex_edit = QLineEdit()
        self.payload_hex_edit.setPlaceholderText(
            "手工 MSDU 载荷：十六进制，可带空格（如 11 01 01 00 …）；留空则用测试模式载荷")
        self.payload_hex_edit.setMinimumWidth(360)
        self.payload_hex_edit.textChanged.connect(self._notify_changed)
        msdu_form.addRow(QLabel("手工载荷 HEX:"), self.payload_hex_edit)

        self.beacon_payload_edit = QLineEdit()
        self.beacon_payload_edit.setPlaceholderText("信标帧载荷：十六进制（FC 之后的内容，无物理块头）")
        self.beacon_payload_edit.setMinimumWidth(360)
        self.beacon_payload_edit.textChanged.connect(self._notify_changed)
        msdu_form.addRow(QLabel("信标载荷 HEX:"), self.beacon_payload_edit)
        msdu_sec.content_layout().addLayout(msdu_form)
        # ⚠ form_group（测试模式参数）**不放进本区**：④ 区在链路层关闭时会隐藏，
        #    而「不启用链路层时改测试模式参数」是 1.23.64 的既有用法，故它留在顶层。
        layout.addWidget(msdu_sec)
        self.sections["msdu"] = msdu_sec

        # ── ⑤ ED 封装（承载既有分组框）──
        ed_sec = CollapsibleSection("⑤ ED..EE 封装（可选）", key="ed")
        ed_sec.toggled.connect(self._notify_changed)
        ed_sec.content_layout().addWidget(ed_group)
        layout.addWidget(ed_sec)
        self.sections["ed"] = ed_sec

        self._rebuild_fc_fields()

    def _field_label(self, spec: LinkFieldSpec) -> str:
        return f"{spec.label}（{spec.help}）" if spec.help else spec.label

    # ------------------------------------------------------------------
    # ⓪ 仿照报文 / 模板
    # ------------------------------------------------------------------
    def _build_mirror_section(self, layout: QVBoxLayout) -> None:
        """「仿照报文 / 模板」折叠区：粘贴一帧 → 反解回填参数；参数集可命名存到本地。

        设计口径（与用户确认过）：
        - 回填后**立刻用同一套参数重建一次并与原帧逐字节对比**，不让"看着对但字节不一致"
          的帧生成出来；
        - 对比不过时按「手工 HEX 保真」兜底（把原载荷填进 ④ 区手工载荷），并在提示里讲清楚
          "此时改应用层/测试模式参数不会影响载荷"；
        - 参考报文随模板一起存本地，便于日后对比差异。
        """
        sec = CollapsibleSection("⓪ 仿照报文 / 模板（粘贴一帧 → 自动回填参数）", key="mirror")
        sec.toggled.connect(self._notify_changed)
        content = sec.content_layout()

        tip = QLabel(
            "把官方测试系统里拷来的整帧报文粘进来（ED..EE 封装 / 整帧 MPDU / 应用层帧都能识别），"
            "点「解析并回填」即可把各层参数填成默认值，你只需微调要改的字段再生成。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888;")
        content.addWidget(tip)

        self.reverse_edit = QPlainTextEdit()
        self.reverse_edit.setPlaceholderText(
            "粘贴报文 HEX，可带空格：ED 1E 00 00 02 EF ... FF EE")
        self.reverse_edit.setFixedHeight(72)
        content.addWidget(self.reverse_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.reverse_apply_btn = QPushButton("解析并回填")
        self.reverse_apply_btn.setToolTip("反解各层参数并回填表单，随后自动做一次逐字节重建校验")
        self.reverse_apply_btn.clicked.connect(self._on_reverse_apply)
        btn_row.addWidget(self.reverse_apply_btn)
        self.reverse_compare_btn = QPushButton("对比当前输出")
        self.reverse_compare_btn.setToolTip(
            "用当前表单参数重建一次，与粘贴的报文逐字节对比，报告首个不一致的字节位置")
        self.reverse_compare_btn.clicked.connect(self._on_reverse_compare)
        btn_row.addWidget(self.reverse_compare_btn)
        self.reverse_clear_btn = QPushButton("清空")
        self.reverse_clear_btn.clicked.connect(lambda: self.reverse_edit.clear())
        btn_row.addWidget(self.reverse_clear_btn)
        btn_row.addStretch()
        content.addLayout(btn_row)

        self.reverse_hint = QLabel("")
        self.reverse_hint.setWordWrap(True)
        self.reverse_hint.setStyleSheet("color: #888;")
        content.addWidget(self.reverse_hint)

        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(6)
        tpl_row.addWidget(QLabel("模板:"))
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(300)
        tpl_row.addWidget(self.template_combo)
        self.template_load_btn = QPushButton("加载")
        self.template_load_btn.setToolTip("把模板里的全部参数套到表单上，再改关键字段即可生成新帧")
        self.template_load_btn.clicked.connect(self._on_template_load)
        tpl_row.addWidget(self.template_load_btn)
        self.template_save_btn = QPushButton("保存为模板…")
        self.template_save_btn.setToolTip("把当前表单参数（含参考报文）存到本地，供下次仿照")
        self.template_save_btn.clicked.connect(self._on_template_save)
        tpl_row.addWidget(self.template_save_btn)
        self.template_delete_btn = QPushButton("删除")
        self.template_delete_btn.clicked.connect(self._on_template_delete)
        tpl_row.addWidget(self.template_delete_btn)
        tpl_row.addStretch()
        content.addLayout(tpl_row)

        self.template_hint = QLabel("")
        self.template_hint.setWordWrap(True)
        self.template_hint.setStyleSheet("color: #888;")
        content.addWidget(self.template_hint)

        layout.addWidget(sec)
        self.sections["mirror"] = sec
        self._refresh_templates()

    # ---- 参数集读写（模板 / 回填共用） ----
    def _link_widget_of(self, name: str) -> Optional[QWidget]:
        return self.link_field_widgets.get(name) or self._fc_field_widgets.get(name)

    def _read_link_field(self, name: str):
        widget = self._link_widget_of(name)
        return None if widget is None else _read_widget_value(widget)

    def _write_link_field(self, name: str, value) -> bool:
        widget = self._link_widget_of(name)
        if widget is None:
            return False
        return _write_widget_value(widget, value)

    def _read_mode_params(self) -> Dict[str, object]:
        """按当前模式的字段读原值（**不做 hex→bytes 转换**，保证模板存取无损）。"""
        mode = self.current_mode()
        params: Dict[str, object] = {}
        if mode is None:
            return params
        for field_def in mode.fields:
            widget = self._field_widgets.get(field_def.name)
            if widget is None:
                continue
            params[field_def.name] = _read_widget_value(widget)
        return params

    def _write_mode_params(self, params: Dict[str, object]) -> List[str]:
        """返回未能写入的字段名（模式不匹配时字段控件不存在）。"""
        mode = self.current_mode()
        missed: List[str] = []
        if mode is None:
            return list(params)
        for field_def in mode.fields:
            if field_def.name not in params:
                continue
            widget = self._field_widgets.get(field_def.name)
            if widget is None or not _write_widget_value(widget, params[field_def.name]):
                missed.append(field_def.name)
        return missed

    def frame_state(self) -> Dict[str, object]:
        """当前表单的完整参数集（模板存储 / 回填都走这一份口径）。"""
        link_state: Dict[str, object] = {}
        for name in _FC_FIELD_NAMES + _MAC_FIELD_NAMES + _MSDU_FIELD_NAMES:
            value = self._read_link_field(name)
            if value is not None:
                link_state[name] = value
        link_state.update({
            "mac_hdr": self.mac_hdr_combo.currentData(),
            "mac_version": self.mac_ver_combo.currentData(),
            "bcast": self.bcast_combo.currentData(),
            "send_type": self.send_type_combo.currentData(),
            "dest_mac": self.dest_mac_edit.text(),
            "pb_count": self.pb_count_spin.value(),
            "pb_total": self.pb_size_combo.currentData(),
            "pb_seq": self.pb_seq_spin.value(),
            "pb_agg": 1 if self.pb_agg_check.isChecked() else 0,
            "payload_src": self.payload_src_combo.currentData(),
            "payload_hex": self.payload_hex_edit.text(),
            "beacon_payload": self.beacon_payload_edit.text(),
            "msdu_type": self.msdu_type_combo.currentData(),
        })
        mode = self.current_mode()
        return {
            "version": _STATE_VERSION,
            "frame": {
                "kind": self.frame_kind(),
                "channel": self.channel_combo.currentData(),
                "std_version": self.stdver_combo.currentData(),
                "link_enabled": self.link_enable_check.isChecked(),
                "output": self.layer_combo.currentData(),
            },
            "link": link_state,
            "header": {
                "port": self.hdr_port.currentData(),
                "frame_type": self.hdr_frame_type.currentData(),
                "dir": self.hdr_dir.currentData(),
                "prm": self.hdr_prm.currentData(),
                "response": self.hdr_response.currentData(),
                "priority": self.hdr_priority.value(),
                "appver": self.hdr_appver.value(),
                "seq": self.hdr_seq.value(),
            },
            "ed": {
                "enabled": self.ed_check.isChecked(),
                "wrapper": self.ed_wrapper.currentData(),
                "cs": self.ed_cs.currentData(),
                "channel": self.ed_channel.value(),
                "timestamp": _read_widget_value(self.ed_timestamp),
                "pb_count": self.ed_pbcount.value(),
                "pb_len": self.ed_pblen.value(),
            },
            "mode": {
                "key": self.mode_combo.currentData() if mode else "",
                "params": self._read_mode_params(),
            },
            "sections": collect_state(self.sections.values()),
        }

    def apply_frame_state(self, state: Dict[str, object]) -> List[str]:
        """套用参数集；返回「没能套上的项」说明列表（空=全部套上）。

        顺序很关键：帧类型/标准版本会**重建 ① 区字段控件**（`_rebuild_fc_fields`），
        模式切换会**重建模式参数字段**（`_rebuild_fields`），所以必须先切结构、
        再写字段值；否则刚写进去的控件会被下次重建丢掉。
        """
        problems: List[str] = []
        if not isinstance(state, dict) or not state:
            return ["参数集为空"]
        frame = state.get("frame") or {}
        link_state = state.get("link") or {}
        header = state.get("header") or {}
        ed = state.get("ed") or {}
        mode_state = state.get("mode") or {}

        # 1) 先切结构（帧类型 / 通道 / 标准版本 / 链路层开关 / 输出层次）
        self._select_combo(self.fk_combo, frame.get("kind"))
        self._select_combo(self.channel_combo, frame.get("channel"))
        self._select_combo(self.stdver_combo, frame.get("std_version"))
        if frame.get("link_enabled") is not None:
            self.link_enable_check.setChecked(bool(frame["link_enabled"]))
        self._select_combo(self.layer_combo, frame.get("output"))
        self._select_combo(self.mode_combo, mode_state.get("key"))

        # 2) 再写各层字段值（此时控件已按新的帧类型/标准版本/模式建好）
        for name, value in link_state.items():
            if name in ("payload_src", "payload_hex", "beacon_payload"):
                continue
            if name == "dest_mac":
                if value:
                    self.dest_mac_edit.setText(str(value))
                continue
            if name == "pb_count":
                self.pb_count_spin.setValue(int(value))
                continue
            if name == "pb_total":
                self._select_combo(self.pb_size_combo, value)
                continue
            if name == "pb_seq":
                self.pb_seq_spin.setValue(int(value))
                continue
            if name == "pb_agg":
                self.pb_agg_check.setChecked(bool(value))
                continue
            if name == "mac_hdr":
                self._select_combo(self.mac_hdr_combo, value)
                continue
            if name == "mac_version":
                self._select_combo(self.mac_ver_combo, value)
                continue
            if name == "bcast":
                self._select_combo(self.bcast_combo, value)
                continue
            if name == "send_type":
                self._select_combo(self.send_type_combo, value)
                continue
            if name == "msdu_type":
                self._select_combo(self.msdu_type_combo, value)
                continue
            if not self._write_link_field(name, value):
                problems.append(f"链路层字段 {name} 未能套用（当前帧类型下无此控件）")

        if "payload_src" in link_state:
            self._select_combo(self.payload_src_combo, link_state.get("payload_src"))
        if "payload_hex" in link_state:
            self.payload_hex_edit.setText(str(link_state.get("payload_hex") or ""))
        if "beacon_payload" in link_state:
            self.beacon_payload_edit.setText(str(link_state.get("beacon_payload") or ""))

        # 3) 应用层头
        for name, widget_name in (("port", "hdr_port"), ("frame_type", "hdr_frame_type"),
                                  ("dir", "hdr_dir"), ("prm", "hdr_prm"),
                                  ("response", "hdr_response")):
            if header.get(name) is not None:
                self._select_combo(getattr(self, widget_name), header[name])
        for name, widget_name in (("priority", "hdr_priority"), ("appver", "hdr_appver"),
                                  ("seq", "hdr_seq")):
            if header.get(name) is not None:
                if not _write_widget_value(getattr(self, widget_name), header[name]):
                    problems.append(f"应用层头 {name} 取值非法")

        # 4) ED 封装
        if ed:
            if ed.get("enabled") is not None:
                self.ed_check.setChecked(bool(ed["enabled"]))
            self._select_combo(self.ed_wrapper, ed.get("wrapper"))
            self._select_combo(self.ed_cs, ed.get("cs"))
            for name, widget_name in (("channel", "ed_channel"), ("timestamp", "ed_timestamp"),
                                      ("pb_count", "ed_pbcount"), ("pb_len", "ed_pblen")):
                if ed.get(name) is not None:
                    if not _write_widget_value(getattr(self, widget_name), ed[name]):
                        problems.append(f"ED 参数 {name} 取值非法")

        # 5) 模式参数（模式已切好）
        missed = self._write_mode_params(mode_state.get("params") or {})
        for name in missed:
            problems.append(f"测试模式参数 {name} 未能套用（当前模式无此字段）")

        # 6) 折叠状态（可缺省）
        sections = state.get("sections")
        if isinstance(sections, dict):
            apply_state(self.sections.values(), sections)

        self._apply_link_visibility()
        self.changed.emit()
        return problems

    @staticmethod
    def _select_combo(combo: QComboBox, value) -> bool:
        if value is None:
            return False
        index = combo.findData(value)
        if index < 0:
            return False
        combo.setCurrentIndex(index)
        return True

    # ---- 仿照回填 / 保真校验 ----
    def _set_reverse_hint(self, text: str, level: str = "info") -> None:
        color = {"info": "#888", "ok": "#2e7d32", "warn": "#c62828"}.get(level, "#888")
        self.reverse_hint.setStyleSheet(f"color: {color};")
        self.reverse_hint.setText(text)

    def _output_layer_for(self, layer: str) -> str:
        """输入层次 → 输出层次（ed→ed / mpdu→mpdu / app→app）。"""
        return layer if layer in ("ed", "mpdu", "app") else "mpdu"

    def _rebuilt_bytes(self) -> Tuple[bool, bytes, str]:
        """按当前表单重建一次，返回 (成功, 字节, 失败原因)。"""
        try:
            result = self.build()
        except Exception as exc:  # noqa: BLE001 - 组帧失败要变成可读提示
            return False, b"", str(exc)
        if result is None:
            return False, b"", "未选择测试模式"
        out = self.output_bytes(result)
        if not out:
            return False, b"", "当前输出层次为空"
        return True, out, ""

    @staticmethod
    def _first_diff(left: bytes, right: bytes) -> str:
        limit = min(len(left), len(right))
        for index in range(limit):
            if left[index] != right[index]:
                return (f"首个不一致在偏移 {index}：重建 {left[index]:02X} "
                        f"≠ 原帧 {right[index]:02X}")
        if len(left) != len(right):
            return f"长度不一致：重建 {len(left)} 字节 ≠ 原帧 {len(right)} 字节"
        return ""

    def _verify_against(self, result: rev.ReverseResult) -> Tuple[bool, str, str]:
        """重建并与原帧逐字节对比；不一致时按「手工 HEX 保真」兜底再比一次。

        返回 ``(是否逐字节一致, 模式, 说明)``，模式为 ``structural`` / ``fidelity`` / ``failed``。
        """
        target = bytes.fromhex(result.input_hex)
        ok, rebuilt, reason = self._rebuilt_bytes()
        if ok and rebuilt == target:
            return True, "structural", ""
        structural_diff = self._first_diff(rebuilt, target) if ok else reason

        payload = result.payload.get("msdu_payload") or result.app_hex
        if payload and result.layer in ("ed", "mpdu"):
            self._select_combo(self.payload_src_combo, "hex")
            self.payload_hex_edit.setText(payload)
            ok2, rebuilt2, reason2 = self._rebuilt_bytes()
            if ok2 and rebuilt2 == target:
                return True, "fidelity", structural_diff
            detail = self._first_diff(rebuilt2, target) if ok2 else reason2
            return False, "failed", f"结构化：{structural_diff}；保真载荷：{detail}"
        return False, "failed", structural_diff

    def _on_reverse_apply(self) -> None:
        """解析粘贴的报文 → 回填参数 → 立刻重建校验（不一致则手工载荷保真兜底）。"""
        result = rev.reverse_frame(self.reverse_edit.toPlainText())
        if not result.ok:
            self._set_reverse_hint(f"❌ {result.error}", "warn")
            return

        self._select_combo(self.layer_combo, self._output_layer_for(result.layer))
        problems = self.apply_frame_state(result.state)
        identity, mode, detail = self._verify_against(result)

        lines = [f"✅ 已回填：{rev.state_summary(result.state)}",
                 f"识别层次：{result.layer.upper()}"
                 + (f"（{result.wrapper} 公共头已剥离）" if result.wrapper else "")]
        if identity and mode == "structural":
            lines.append("逐字节校验：与粘贴的报文**完全一致**，可放心微调后重新生成。")
            level = "ok"
        elif identity and mode == "fidelity":
            lines.append("结构化还原不完整，已按「手工 HEX 保真」兜底：**仍能逐字节复现原帧**，"
                         "但此时改应用层/测试模式参数不会影响载荷（要改载荷请直接改 ④ 区手工载荷）。")
            if detail:
                lines.append(f"（结构化差异：{detail}）")
            level = "info"
        else:
            lines.append(f"⚠ 无法逐字节复现：{detail}。链路层字段已按原帧回填，请核对下方未识别项。")
            level = "warn"
        if result.unmapped:
            lines.append("本工具表单表达不了、已按原样保真的字段：" + "；".join(result.unmapped[:5])
                         + ("…" if len(result.unmapped) > 5 else ""))
        if result.notes:
            lines.append("解析摘要：" + "；".join(result.notes))
        if problems:
            lines.append("未套上的项：" + "；".join(problems[:5]))
        self._set_reverse_hint("\n".join(lines), level)
        self.changed.emit()

    def _on_reverse_compare(self) -> None:
        """只对比：用当前表单重建，与粘贴的报文逐字节对比。"""
        result = rev.reverse_frame(self.reverse_edit.toPlainText())
        if not result.ok:
            self._set_reverse_hint(f"❌ {result.error}", "warn")
            return
        target = bytes.fromhex(result.input_hex)
        layer = self._output_layer_for(result.layer)
        self._select_combo(self.layer_combo, layer)
        ok, rebuilt, reason = self._rebuilt_bytes()
        if not ok:
            self._set_reverse_hint(f"❌ 重建失败：{reason}", "warn")
            return
        if rebuilt == target:
            self._set_reverse_hint(
                f"✅ 当前输出与粘贴报文逐字节一致（{len(rebuilt)} 字节，层次 {layer.upper()}）。", "ok")
            return
        self._set_reverse_hint(
            f"⚠ 当前输出与粘贴报文不一致（重建 {len(rebuilt)} 字节 / 原帧 {len(target)} 字节）："
            f"{self._first_diff(rebuilt, target)}", "warn")

    # ---- 模板 ----
    def _suggest_template_name(self) -> str:
        """按「帧类型 + 模式」给个默认名，省得每次手打。"""
        mode = self.current_mode()
        kind = {"sof": "SOF", "beacon": "信标", "sack": "SACK"}.get(self.frame_kind(), "帧")
        tail = f"{mode.group}·{mode.name}" if mode else "未选模式"
        return tpl.normalize_name(f"{kind}-{tail}")

    def _refresh_templates(self, select: str = "") -> str:
        """重载模板下拉；返回读取告警（空串=正常）。"""
        items, warn = tpl.load_templates()
        current = select or self.template_combo.currentText()
        self.template_combo.clear()
        for item in items:
            label = str(item.get("label") or "")
            text = f"{item['name']}" + (f"｜{label}" if label else "")
            self.template_combo.addItem(text, item["name"])
        if current:
            index = self.template_combo.findData(current)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)
        if items:
            self.template_hint.setText(f"本地共 {len(items)} 个模板：{tpl.store_path()}")
        else:
            self.template_hint.setText(f"尚未保存模板（将存到 {tpl.store_path()}）")
        if warn:
            self.template_hint.setText(warn)
        return warn

    def _on_template_save(self) -> None:
        state = self.frame_state()
        reference = self.reverse_edit.toPlainText().strip()
        name, ok = QInputDialog.getText(
            self, "保存为模板", "模板名（下次直接加载这套参数）：",
            QLineEdit.Normal, self._suggest_template_name())
        if not ok:
            return
        error = tpl.save_template(
            name, state, reference_hex=reference, label=rev.state_summary(state))
        if error:
            QMessageBox.warning(self, "保存失败", error)
            self._set_reverse_hint(f"❌ {error}", "warn")
            return
        self._refresh_templates(select=tpl.normalize_name(name))
        self._set_reverse_hint(
            f"✅ 模板「{tpl.normalize_name(name)}」已保存"
            + ("（含参考报文）" if reference else "（未含参考报文）")
            + "。下次选它 → 加载 → 改关键字段即可生成新帧。", "ok")

    def _on_template_load(self) -> None:
        name = self.template_combo.currentData()
        if not name:
            self._set_reverse_hint("请先选择模板", "warn")
            return
        item = tpl.get_template(str(name))
        if not item:
            self._set_reverse_hint(f"模板「{name}」不存在，可能已被删除", "warn")
            self._refresh_templates()
            return
        problems = self.apply_frame_state(item.get("state") or {})
        reference = str(item.get("reference_hex") or "")
        if reference:
            self.reverse_edit.setPlainText(reference)
        lines = [f"✅ 已加载模板「{item['name']}」" + (f"（{item.get('label')}）" if item.get("label") else ""),
                 "现在只需修改要变的字段（如 TEI / 帧序号 / 频段），再点「生成帧」即可。"]
        if reference:
            lines.append("参考报文已放回粘贴框，可用「对比当前输出」核对改动后的差异。")
        if problems:
            lines.append("未套上的项：" + "；".join(problems[:5]))
        self._set_reverse_hint("\n".join(lines), "ok" if not problems else "info")
        self.changed.emit()

    def _on_template_delete(self) -> None:
        name = self.template_combo.currentData()
        if not name:
            self._set_reverse_hint("请先选择要删除的模板", "warn")
            return
        answer = QMessageBox.question(
            self, "删除模板", f"确定删除模板「{name}」？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        error = tpl.delete_template(str(name))
        if error:
            self._set_reverse_hint(f"❌ {error}", "warn")
            return
        self._refresh_templates()
        self._set_reverse_hint(f"已删除模板「{name}」。", "info")

    def _make_mac_edit(self, default: bytes) -> QLineEdit:
        edit = QLineEdit(":".join(f"{b:02X}" for b in default))
        edit.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        edit.setMinimumWidth(200)
        edit.textChanged.connect(self._notify_changed)
        return edit

    def _make_link_widget(self, spec: LinkFieldSpec) -> QWidget:
        if spec.kind == "mac":
            return self._make_mac_edit(bytes(spec.default or b"\xFF" * 6))
        if spec.kind == "choice" and spec.choices:
            combo = QComboBox()
            for value, label in spec.choices:
                combo.addItem(str(label), value)
            combo.currentIndexChanged.connect(self._notify_changed)
            return combo
        spin = QSpinBox()
        # QSpinBox 的上限是 C++ int（0x7FFFFFFF）：信标时间戳/周期是 32bit 字段
        # （maximum=0xFFFFFFFF），直接 setRange 会抛 OverflowError，把
        # _rebuild_fc_fields 整个打断 —— 表现为「切到信标帧后 FC 区还是 SOF 的样子、
        # 输出也仍是上一帧类型的 MPDU」。故先夹到 int 上限再设。
        upper = int(spec.maximum) if spec.maximum > 0 else 0xFFFF
        if upper > 0x7FFFFFFF:
            # 满 32bit 字段（信标时间戳/周期）QSpinBox 装不下，用宽整数文本框
            edit = _WideIntEdit(int(spec.default) if isinstance(spec.default, int) else 0)
            edit.setToolTip(spec.help or "")
            edit.textChanged.connect(self._notify_changed)
            return edit
        wide = upper > 0xFFFF
        spin.setRange(0, min(upper, 0x7FFFFFFF))
        if wide:
            spin.setDisplayIntegerBase(16)
            spin.setPrefix("0x")
        spin.setValue(int(spec.default) if isinstance(spec.default, int) else 0)
        spin.setToolTip(spec.help or "")
        spin.valueChanged.connect(self._notify_changed)
        return spin

    def _rebuild_fc_fields(self) -> None:
        """按当前帧类型 + 标准版本重建 ① 区字段（只显示该变体适用的项）。"""
        while self.fc_form.count():
            item = self.fc_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._fc_field_widgets: Dict[str, QWidget] = {}

        kind = self.frame_kind()
        for spec in _FC_FIELDS:
            if spec.kinds and kind not in spec.kinds:
                continue
            widget = self._make_link_widget(spec)
            if spec.name in self._fc_field_widgets:   # 同名只建一次
                continue
            self._fc_field_widgets[spec.name] = widget
            self.fc_form.addRow(QLabel(self._field_label(spec)), widget)
        self._apply_link_visibility()

    @staticmethod
    def _spec_by_name(name: str) -> Optional[LinkFieldSpec]:
        for spec in _FC_FIELDS:
            if spec.name == name:
                return spec
        return None

    # ------------------------------------------------------------------
    # 链路层联动
    # ------------------------------------------------------------------
    def frame_kind(self) -> str:
        return self.fk_combo.currentData() or "sof"

    def std_version(self) -> int:
        return int(self.stdver_combo.currentData() or link.STD_VERSION_ISAC)

    def _on_frame_kind_changed(self) -> None:
        self._rebuild_fc_fields()
        self._notify_changed()

    def _on_std_version_changed(self) -> None:
        self._rebuild_fc_fields()
        self._notify_changed()

    def _on_mac_header_changed(self) -> None:
        self._apply_link_visibility()
        self._notify_changed()

    def _on_payload_source_changed(self) -> None:
        self._apply_link_visibility()
        self._notify_changed()

    def _on_layer_changed(self) -> None:
        """输出层次变化：决定是否组装链路层（仅应用层/BDU 时隐藏 ①②③）。"""
        self._apply_link_visibility()
        self._notify_changed()

    def _on_link_enable_toggled(self, checked: bool) -> None:
        """链路层开关：决定 ①~④ 是否参与组帧（⑤ ED 独立，不受影响）。"""
        enabled = bool(checked)
        for key in ("fc", "pb", "mac", "msdu"):
            self.sections[key].setEnabled(enabled)
        self._apply_link_visibility()
        self._notify_changed()

    def _apply_link_visibility(self) -> None:
        """按帧类型 / 标准版本 / MAC 头类型 / 载荷来源联动各字段与整层可见性。"""
        kind = self.frame_kind()
        std = self.std_version()
        link_on = self.link_enable_check.isChecked()
        layer = self.output_layer()

        # —— ① 区字段：BPLC / ISAC 互斥 ——
        for name, widget in getattr(self, "_fc_field_widgets", {}).items():
            if name in _ISAC_ONLY_FIELDS:
                self._set_row_visible(widget, std == link.STD_VERSION_ISAC)
            elif name in _BPLC_ONLY_FIELDS:
                self._set_row_visible(widget, std == link.STD_VERSION_BPLC)

        # —— ②③④ 整层：信标无物理块/MAC，SACK 仅 FC ——
        show_pb = kind == "sof"
        show_mac = kind == "sof"
        # 仅应用层/BDU 输出时不组装链路层，隐藏 ①②③
        if layer in ("bdu", "app"):
            show_pb = show_mac = False
        self.sections["pb"].setVisible(show_pb)
        self.sections["mac"].setVisible(show_mac)
        # ④ 区含手工载荷/MSDU 头（链路层专属），按开关显隐
        self.sections["msdu"].setVisible(link_on)
        self.sections["fc"].setVisible(link_on)

        # —— ③ 目的MAC 仅长头；④ MSDU 的 MAC 字段仅长头 ——
        long_mac = int(self.mac_hdr_combo.currentData() or 0) == link.MAC_HDR_TYPE_LONG
        self._set_row_visible(self.dest_mac_edit, long_mac)
        for name in ("msdu_dest_mac", "msdu_src_mac"):
            widget = self.link_field_widgets.get(name)
            if widget is not None:
                self._set_row_visible(widget, long_mac)

        # —— ④ 载荷来源联动（手工 HEX 优先；信标帧只填信标载荷）——
        src = self.payload_src_combo.currentData()
        self._set_row_visible(self.payload_hex_edit, src == "hex")
        beacon_mode = kind == "beacon"
        self._set_row_visible(self.beacon_payload_edit, beacon_mode)
        self.payload_src_combo.setEnabled(not beacon_mode)
        for name in ("msdu_type", "vlan", "msdu_dest_mac", "msdu_src_mac"):
            widget = (self.msdu_type_combo if name == "msdu_type"
                      else self.link_field_widgets.get(name))
            if widget is not None:
                self._set_row_visible(widget, not beacon_mode)

        # —— ② 物理块提示（索引反查结果）——
        if show_pb:
            try:
                cfg = self._link_config()
                self.pb_cmt_label.setText(
                    f"载波映射表索引/TMI 自动反查 = {cfg.cmt_index}"
                    if cfg.cmt_index is not None else "")
            except Exception as exc:  # noqa: BLE001 - 提示失败不应影响可用性
                self.pb_cmt_label.setText(f"参数待修正：{exc}")

    @staticmethod
    def _set_row_visible(widget: Optional[QWidget], visible: bool) -> None:
        """隐藏/显示控件所在整行（QFormLayout 的行标签也要一起隐藏）。"""
        if widget is None:
            return
        widget.setVisible(bool(visible))
        parent = widget.parentWidget()
        layout = parent.layout() if parent is not None else None
        if isinstance(layout, QFormLayout):
            label = layout.labelForField(widget)
            if label is not None:
                label.setVisible(bool(visible))

    def _expand_all_sections(self) -> None:
        expand_all(self.sections.values())

    def _collapse_all_sections(self) -> None:
        collapse_all(self.sections.values())

    def link_state(self) -> Dict[str, bool]:
        """折叠状态（供父控件持久化到 config.json）。"""
        return collect_state(self.sections.values())

    def apply_link_state(self, state) -> List[str]:
        return apply_state(self.sections.values(), state)

    # ------------------------------------------------------------------
    # 链路层取值 / 组装
    # ------------------------------------------------------------------
    def _link_field_value(self, name: str, default=0):
        widget = self.link_field_widgets.get(name) or self._fc_field_widgets.get(name)
        if widget is None:
            return default
        # 宽整数文本框必须先判断：它是 QLineEdit 子类，否则会把整数当文本传下去
        if isinstance(widget, _WideIntEdit):
            return widget.value()
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QComboBox):
            return widget.currentData()
        return widget.value()

    def _link_config(self) -> link.LinkFrameConfig:
        """把界面取值收进 ``LinkFrameConfig``；非法值由组帧器报可读错误。"""
        kind = self.frame_kind()
        delim = {"sof": link.DELIM_SOF, "beacon": link.DELIM_BEACON,
                 "sack": link.DELIM_SACK}[kind]
        # 帧类型决定 MSDU 载荷来源：手工 HEX 优先
        manual = self.payload_hex_edit.text().strip()
        payload = fg.hex_to_bytes(manual) if manual else b""
        beacon_payload = fg.hex_to_bytes(self.beacon_payload_edit.text())

        return link.LinkFrameConfig(
            frame_kind=kind,
            delimiter_type=delim,
            std_version=self.std_version(),
            channel=self.channel_combo.currentData() or "plc",
            access_indicator=int(self._link_field_value("access_indicator", 1)),
            snid=int(self._link_field_value("snid", 1)),
            src_tei=int(self._link_field_value("src_tei", 0)),
            dest_tei=int(self._link_field_value("dest_tei", 1)),
            link_id=int(self._link_field_value("link_id", 0)),
            streams=int(self._link_field_value("streams", 0)),
            tf_symbols_cfg=int(self._link_field_value("tf_symbols_cfg", 0)),
            pl_band=int(self._link_field_value("pl_band", 0)),
            tf_ext_band=int(self._link_field_value("tf_ext_band", 0)),
            bitloading=int(self._link_field_value("bitloading", 0)),
            frame_len_10us=int(self._link_field_value("frame_len_10us", 0)),
            tei_filter=int(self._link_field_value("tei_filter", 1)),
            retransmit=int(self._link_field_value("retransmit", 0)),
            symbol_count=int(self._link_field_value("symbol_count", 0)),
            ext_cmt_index=int(self._link_field_value("ext_cmt_index", 0)),
            beacon_timestamp=int(self._link_field_value("beacon_timestamp", 0)),
            beacon_cycle=int(self._link_field_value("beacon_cycle", 0)),
            beacon_phase=int(self._link_field_value("beacon_phase", 0)),
            beacon_payload=beacon_payload,
            sack_rx_result=int(self._link_field_value("sack_rx_result", 0)),
            sack_rx_status=int(self._link_field_value("sack_rx_status", 0)),
            sack_rx_pb_count=int(self._link_field_value("sack_rx_pb_count", 1)),
            sack_snr_type=int(self._link_field_value("sack_snr_type", 0)),
            sack_snr_value=int(self._link_field_value("sack_snr_value", 0)),
            pb_count=self.pb_count_spin.value(),
            pb_total=int(self.pb_size_combo.currentData() or 136),
            pb_seq_start=self.pb_seq_spin.value(),
            pb_agg_flag=1 if self.pb_agg_check.isChecked() else 0,
            mac_header_type=int(self.mac_hdr_combo.currentData() or 0),
            mac_version=int(self.mac_ver_combo.currentData() or link.MAC_VERSION_STD),
            tx_seq=int(self._link_field_value("tx_seq", 0)),
            reboot_count=int(self._link_field_value("reboot_count", 0)),
            hop_count=int(self._link_field_value("hop_count", 0)),
            broadcast_dir=int(self.bcast_combo.currentData() or 0),
            send_type=int(self.send_type_combo.currentData() or 0),
            max_send=int(self._link_field_value("max_send", 0)),
            msdu_seq=int(self._link_field_value("msdu_seq", 0)),
            dest_mac=_mac_text_to_bytes(self.dest_mac_edit.text()),
            vlan=int(self._link_field_value("vlan", 0)),
            msdu_type=int(self.msdu_type_combo.currentData() or link.MSDU_TYPE_APP),
            msdu_dest_mac=_mac_text_to_bytes(self._link_field_value("msdu_dest_mac", "")),
            msdu_src_mac=_mac_text_to_bytes(self._link_field_value("msdu_src_mac", "")),
            msdu_payload=payload,
        )

    def _notify_changed(self, *_args):
        """信号适配：Qt 的 currentIndexChanged/valueChanged 都带参数，本控件的 changed 不带。"""
        self.changed.emit()
