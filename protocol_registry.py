"""协议能力注册表（capability registry）。

把 GUI 下拉索引 0~11 的展示名、别名、占位符、Tab 可见性、查询页、
校验器、批量帧提取策略、解析级别族等元数据集中到一处。
main_gui 只查表分派，新增协议时优先改本文件而不是散落 8+ 处 if。

与 parser_registry.py 的分工：
- parser_registry：按名字懒加载 parser 类/实例（模块级缓存）
- protocol_registry：按协议索引描述「这个协议能干什么」
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple


@dataclass(frozen=True)
class ProtocolSpec:
    index: int
    # protocol_combo 显示名（含 [i] 前缀在 build 时拼接）
    name: str
    # 短名（用于日志/提示）
    short_name: str
    # parser_registry 键
    parser_key: str
    # 单帧输入框 placeholder
    placeholder: str
    # 协议名别名（命令行/CLI 解析用，精确匹配优先）
    aliases: Tuple[str, ...] = ()
    # 查询页类型：di_nw | command_plc | obis | di_dlt645 | afn | oad | csg | gw | hdc10 | None
    lookup_kind: Optional[str] = None
    lookup_tab_title: Optional[str] = None
    # 组帧模式：south | dlt645 | gdw | dlt698 | None
    frame_gen_mode: Optional[str] = None
    # Tab / 附属能力
    has_archive: bool = False
    has_topology: bool = False
    has_virtual_meter: bool = False  # 698 虚拟表（协议8）
    has_dlt645_sim: bool = False  # DLT645 虚拟表（协议6）
    has_monitor: bool = False
    monitor_wrapper: Optional[str] = None  # plc2 | hplc
    has_sequence_diagram: bool = False
    # 解析级别族：None | csg | gw | hdc10（GUI 控件共用/复用）
    parse_level_family: Optional[str] = None
    # ED..EE 监控包装：单帧「ED监控协议」勾选 + 包装头格式下拉 + 字节剔除
    # （协议9 原生能力；1.23.31 起 10/11 同步，现场日志常带 ED 封装）
    has_ed_monitor: bool = False
    # 单帧输入 hex 按 4 字节一组端序翻转后再解析
    has_reverse_4byte: bool = False
    # 批量提取策略
    extract_strategy: str = "line"  # ft12_68 | dlt698_45 | generic | hdlc | line | wrapper | csg_line | gw_line_min4
    # 校验器类路径（延迟 import）
    validator_class: Optional[str] = None
    # _get_current_parser 包装方式
    parser_wrapper: str = "direct"  # direct | apdu_guowang | wrapper | apdu | dlt645 | csg | gw | hdc10
    # 预设命令 mode（与 frame_gen 对齐；None 表示不参与 preset set_protocol）
    preset_mode: Optional[str] = None


_PROTOS: Tuple[ProtocolSpec, ...] = (
    ProtocolSpec(
        index=0,
        name="[0] 南网协议 (Q/CSG1209021-2019)",
        short_name="南网协议",
        parser_key="south",
        placeholder="请输入十六进制报文，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
        aliases=("南网协议", "南网"),
        lookup_kind="di_nw",
        lookup_tab_title="DI查询",
        frame_gen_mode="south",
        has_archive=True,
        has_topology=True,
        preset_mode="south",
        extract_strategy="ft12_68",
        validator_class="validator.nw_validator:NWValidator",
        parser_wrapper="direct",
    ),
    ProtocolSpec(
        index=1,
        name="[1] PLC RF协议 (万胜海外 V1_04)",
        short_name="PLC RF协议",
        parser_key="plc_rf",
        placeholder="请输入PLC RF报文，例如：02 00 05 C0 20 01 00 99",
        aliases=("PLC RF协议", "PLC RF", "PLC"),
        lookup_kind="command_plc",
        lookup_tab_title="命令字查询",
        extract_strategy="generic",
        validator_class="validator.plc_rf_validator:PLCRFValidator",
        parser_wrapper="direct",
    ),
    ProtocolSpec(
        index=2,
        name="[2] HDLC/国网DLMS (IEC 62056-46)",
        short_name="HDLC/国网DLMS",
        parser_key="hdlc",
        placeholder="请输入HDLC报文，例如：7E A0 07 01 01 93 ... 7E",
        aliases=("HDLC", "HDLC/DLMS"),
        lookup_kind="obis",
        lookup_tab_title="OBIS查询",
        extract_strategy="hdlc",
        validator_class="validator.hdlc_validator:HDLCValidator",
        parser_wrapper="direct",
    ),
    ProtocolSpec(
        index=3,
        name="[3] DLMS-APDU(国网)",
        short_name="DLMS-APDU(国网)",
        parser_key="hdlc",
        placeholder="请输入国网DLMS APDU报文，例如：C0 01 C1 00 ...",
        aliases=("DLMS-APDU国网", "APDU国网"),
        lookup_kind="obis",
        lookup_tab_title="OBIS查询",
        extract_strategy="line",
        validator_class="validator.hdlc_validator:HDLCValidator",
        parser_wrapper="apdu_guowang",
    ),
    ProtocolSpec(
        index=4,
        name="[4] DLMS Wrapper裸报文",
        short_name="DLMS Wrapper",
        parser_key="hdlc",
        placeholder="请输入Wrapper报文，例如：00 01 00 02 00 1E ...",
        aliases=("DLMS Wrapper", "Wrapper"),
        lookup_kind="obis",
        lookup_tab_title="OBIS查询",
        extract_strategy="wrapper",
        validator_class="validator.hdlc_validator:HDLCValidator",
        parser_wrapper="wrapper",
    ),
    ProtocolSpec(
        index=5,
        name="[5] DLMS-APDU裸报文",
        short_name="DLMS-APDU裸",
        parser_key="hdlc",
        placeholder="请输入APDU报文，例如：C0 01 C1 00 ...",
        aliases=("DLMS-APDU裸", "APDU"),
        lookup_kind="obis",
        lookup_tab_title="OBIS查询",
        extract_strategy="line",
        validator_class="validator.hdlc_validator:HDLCValidator",
        parser_wrapper="apdu",
    ),
    ProtocolSpec(
        index=6,
        name="[6] DLT645-2007 电表协议",
        short_name="DLT645-2007",
        parser_key="dlt645",
        placeholder="请输入DLT645报文，例如：68 AA AA AA AA AA AA 68 11 04 33 33 33 33 CS 16",
        aliases=("DLT645", "DLT645-2007", "645"),
        lookup_kind="di_dlt645",
        lookup_tab_title="DI查询",
        frame_gen_mode="dlt645",
        # 1.22.0 起协议6 组帧/预设已开放；preset set_protocol 需同步 mode
        preset_mode="dlt645",
        has_dlt645_sim=True,
        extract_strategy="line",
        validator_class="validator.dlt645_validator:DLT645Validator",
        parser_wrapper="dlt645",
    ),
    ProtocolSpec(
        index=7,
        name="[7] 国网协议 (Q/GDW 10376.2-2024)",
        short_name="国网协议",
        parser_key="gdw",
        placeholder="请输入国网报文，例如：68 0F 00 43 00 00 00 00 00 00 00 00 00 03 01 00 48 16",
        aliases=("国网协议", "国网"),
        lookup_kind="afn",
        lookup_tab_title="AFN查询",
        frame_gen_mode="gdw",
        has_archive=True,
        has_topology=True,
        preset_mode="gdw",
        extract_strategy="ft12_68",
        validator_class="validator.gdw_validator:GDWValidator",
        parser_wrapper="direct",
    ),
    ProtocolSpec(
        index=8,
        name="[8] 698.45协议 (DL/T 698.45-2017)",
        short_name="698.45协议",
        parser_key="dl_t698_45",
        placeholder="请输入698.45报文，例如：68 0E 00 41 01 07 08 09 AE C6 01 00 00 00 00 34 87 16",
        aliases=("698.45", "698"),
        lookup_kind="oad",
        lookup_tab_title="OAD查询",
        frame_gen_mode="dlt698",
        has_virtual_meter=True,
        preset_mode="dlt698",
        extract_strategy="dlt698_45",
        validator_class="validator.dl_t698_45_validator:DLT69845Validator",
        parser_wrapper="direct",
    ),
    ProtocolSpec(
        index=9,
        name="[9] 新一代载波协议 (通感一体化)",
        short_name="新一代载波协议",
        parser_key="csg_new_gen",
        placeholder="请输入新一代载波报文，例如：11 01 01 00 00 00 00 01 00 01 00 00",
        aliases=("新一代载波", "载波"),
        lookup_kind="csg",
        lookup_tab_title="业务标识查询",
        has_monitor=True,
        monitor_wrapper="plc2",
        has_sequence_diagram=True,
        parse_level_family="csg",
        has_ed_monitor=True,
        has_reverse_4byte=True,
        extract_strategy="csg_line",
        validator_class="validator.csg_new_gen_validator:CSGNewGenValidator",
        parser_wrapper="csg",
    ),
    ProtocolSpec(
        index=10,
        name="[10] 国网新一代双模通信互联互通",
        short_name="国网新一代",
        parser_key="gw_new_gen",
        placeholder="请输入国网新一代报文，例如：ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00",
        aliases=("国网新一代", "双模"),
        lookup_kind="gw",
        lookup_tab_title="报文ID查询",
        has_monitor=True,
        monitor_wrapper="hplc",
        has_sequence_diagram=True,
        parse_level_family="gw",
        has_ed_monitor=True,
        has_reverse_4byte=True,
        extract_strategy="gw_line_min4",
        validator_class="validator.gw_new_gen_validator:GWNewGenValidator",
        parser_wrapper="gw",
    ),
    ProtocolSpec(
        index=11,
        name="[11] HDC 1.0 双模互联互通",
        short_name="HDC 1.0 双模互联互通",
        parser_key="hdc10",
        placeholder="请输入HDC 1.0报文，例如：01 00 01 00 00 10 00 11 ...",
        aliases=("HDC1.0", "HDC 1.0", "hdc10", "旧版双模"),
        lookup_kind="hdc10",
        lookup_tab_title="报文ID查询",
        has_sequence_diagram=True,
        parse_level_family="hdc10",
        has_ed_monitor=True,
        has_reverse_4byte=True,
        extract_strategy="line",
        validator_class="validator.hdc10_validator:HDC10Validator",
        parser_wrapper="hdc10",
    ),
    ProtocolSpec(
        index=12,
        name="[12] 模组化终端功能模块接口",
        short_name="模组化接口",
        parser_key="modular",
        placeholder="请输入模组化接口报文，例如：68 … 16",
        aliases=(
            "模组化",
            "模组化接口",
            "模组化终端",
            "modular",
            "modular_iface",
            "functional module",
        ),
        frame_gen_mode="modular",
        preset_mode="modular",
        lookup_kind="modular",
        lookup_tab_title="信息类查询",
        extract_strategy="modular",
        validator_class="validator.modular_iface_validator:ModularIfaceValidator",
        parser_wrapper="direct",
    ),
)

_BY_INDEX = {p.index: p for p in _PROTOS}
_INDEX_BY_ALIAS: dict = {}
for _p in _PROTOS:
    for _a in _p.aliases:
        _INDEX_BY_ALIAS[_a] = _p.index


def all_protocols() -> Tuple[ProtocolSpec, ...]:
    return _PROTOS


def get_protocol(index: int) -> ProtocolSpec:
    try:
        return _BY_INDEX[index]
    except KeyError as exc:
        raise KeyError(f"Unknown protocol index: {index}") from exc


def protocol_count() -> int:
    return len(_PROTOS)


def combo_labels() -> Tuple[str, ...]:
    return tuple(p.name for p in _PROTOS)


def placeholder_for(index: int) -> str:
    return get_protocol(index).placeholder


def name_to_index(name: str) -> Optional[int]:
    """协议名 → 索引（支持纯数字、精确别名、子串模糊匹配）。"""
    name = str(name).strip()
    # 别名优先（"645" 是 DLT645 别名，不是索引）
    if name in _INDEX_BY_ALIAS:
        return _INDEX_BY_ALIAS[name]
    if name.isdigit():
        # 与旧实现一致：纯数字直接作索引（超范围由调用方处理）
        return int(name)
    for alias, idx in _INDEX_BY_ALIAS.items():
        if alias in name or name in alias:
            return idx
    return None


def protocols_with_frame_gen() -> Tuple[int, ...]:
    return tuple(p.index for p in _PROTOS if p.frame_gen_mode)


def protocols_with_sequence_diagram() -> Tuple[int, ...]:
    return tuple(p.index for p in _PROTOS if p.has_sequence_diagram)


def protocols_with_monitor() -> Tuple[int, ...]:
    return tuple(p.index for p in _PROTOS if p.has_monitor)


def frame_gen_mode_for(index: int) -> Optional[str]:
    return get_protocol(index).frame_gen_mode


def preset_mode_for(index: int) -> Optional[str]:
    return get_protocol(index).preset_mode


def make_validator(index: int):
    """按索引实例化校验器；无校验器返回 None。"""
    spec = get_protocol(index)
    if not spec.validator_class:
        return None
    path = spec.validator_class
    if ":" not in path:
        raise ValueError(f"validator_class must be 'module:Class', got {path!r}")
    mod_name, cls_name = path.split(":", 1)
    import importlib

    mod = importlib.import_module(mod_name)
    return getattr(mod, cls_name)()


def build_validator_map() -> dict:
    """构建 {index: validator_instance}，供单帧校验与快捷小窗共用。"""
    out = {}
    for p in _PROTOS:
        if p.validator_class:
            out[p.index] = make_validator(p.index)
    return out


# ── GUI 解析器包装（无 Qt，仅依赖 base parser 对象）────────────────

class _APDUParserGuowang:
    def __init__(self, hdlc_parser):
        self.hdlc_parser = hdlc_parser

    def parse_to_table(self, data):
        return self.hdlc_parser.parse_apdu_to_table(data)


class _WrapperParser:
    def __init__(self, hdlc_parser):
        self.hdlc_parser = hdlc_parser

    def parse_to_table(self, data):
        return self.hdlc_parser.parse_wrapper_to_table(data)


class _APDUParser:
    def __init__(self, hdlc_parser):
        self.hdlc_parser = hdlc_parser

    def parse_to_table(self, data):
        return self.hdlc_parser.parse_apdu_to_table(data)


class DLT645GuiParser:
    def __init__(self, parser):
        self.parser = parser

    def parse_to_table(self, data):
        result = self.parser.parse(data)
        table = []
        data_len = result.get("data_length", 0)
        # 字节偏移一律以**实际帧长**为准：1.23.22 起「声明长度与实际不符」的帧也会走到
        # 这里（不再拒解析），用声明长度推出来的偏移会越界（见 AGENTS §8 陷阱 49）。
        # 合法帧满足 frame_len == 10 + data_len + 2，此时以下三式与旧公式完全相同
        # ⇒ 合法帧输出逐行不变（硬约束）。
        frame_len = len(data)
        data_end = max(0, min(10 + data_len - 1, frame_len - 3))
        cs_pos = max(0, frame_len - 2)
        end_pos = max(0, frame_len - 1)

        for item in result["fields"]:
            if len(item) == 4:
                field, raw, lme_parsed, desc = item
            else:
                field, raw, desc = item
                lme_parsed = ""
            byte_start = 0
            byte_end = 0
            parsed_value = lme_parsed

            if "帧起始符 1" in field:
                byte_start, byte_end = 0, 0
            elif "从站地址" in field:
                byte_start, byte_end = 1, 6
            elif "帧起始符 2" in field:
                byte_start, byte_end = 7, 7
            elif "控制码" in field:
                byte_start, byte_end = 8, 8
                parsed_value = result.get("control_parsed", "")
            elif "数据长度" in field:
                byte_start, byte_end = 9, 9
            elif "数据标识 DI" in field:
                byte_start, byte_end = 10, 13
                di_code = result.get("di_code", "")
                di_desc = result.get("di_desc", "")
                parsed_value = (
                    f"{di_code} ({di_desc})" if di_code and di_desc else di_code
                )
            elif "数据内容" in field:
                byte_start, byte_end = 14, data_end
            elif "数据域" in field:
                byte_start, byte_end = 10, data_end
            elif "校验和" in field:
                byte_start, byte_end = cs_pos, cs_pos
            elif "帧结束符" in field:
                byte_start, byte_end = end_pos, end_pos

            table.append((field, raw, parsed_value, desc, byte_start, byte_end))

        return table


class CSGGenGuiParser:
    def __init__(self, parser, level, ftype=None, channel="plc"):
        self.parser = parser
        self.level = level
        self.frame_type = ftype
        self.channel = channel

    def parse_to_table(self, data):
        kwargs = {"parse_level": self.level, "channel": self.channel}
        if self.frame_type is not None:
            kwargs["pb_frame_type"] = self.frame_type
        return self.parser.parse_to_table(data, **kwargs)


class GWGenGuiParser:
    def __init__(self, parser, level, ftype=None, channel="plc"):
        self.parser = parser
        self.level = level
        self.frame_type = ftype
        self.channel = channel

    def parse_to_table(self, data):
        kwargs = {"parse_level": self.level, "channel": self.channel}
        if self.frame_type is not None:
            kwargs["frame_type"] = self.frame_type
        return self.parser.parse_to_table(data, **kwargs)


class HDC10GuiParser:
    def __init__(self, parser, level, ftype=None, channel="plc"):
        self.parser = parser
        self.level = level
        self.frame_type = ftype
        self.channel = channel

    def parse_to_table(self, data):
        kwargs = {"parse_level": self.level, "channel": self.channel}
        if self.frame_type is not None:
            kwargs["frame_type"] = self.frame_type
        return self.parser.parse_to_table(data, **kwargs)


def build_gui_parser(
    index: int,
    base_parser,
    *,
    parse_level: Optional[str] = None,
    frame_type=None,
    channel: str = "plc",
):
    """按注册表包装 base_parser，返回具备 parse_to_table 的对象。

    channel/parse_level/frame_type 由 MainWindow 传入（可覆盖弹窗场景）。
    """
    spec = get_protocol(index)
    wrap = spec.parser_wrapper
    if wrap == "direct":
        return base_parser
    if wrap == "apdu_guowang":
        return _APDUParserGuowang(base_parser)
    if wrap == "wrapper":
        return _WrapperParser(base_parser)
    if wrap == "apdu":
        return _APDUParser(base_parser)
    if wrap == "dlt645":
        return DLT645GuiParser(base_parser)
    if wrap == "csg":
        return CSGGenGuiParser(base_parser, parse_level or "auto", frame_type, channel)
    if wrap == "gw":
        return GWGenGuiParser(base_parser, parse_level or "auto", frame_type, channel)
    if wrap == "hdc10":
        return HDC10GuiParser(base_parser, parse_level or "auto", frame_type, channel)
    raise ValueError(f"Unknown parser_wrapper: {wrap}")


def lookup_builder_method(kind: Optional[str]) -> Optional[str]:
    """查询页 builder 方法名（MainWindow 方法）。"""
    mapping = {
        "di_nw": "_create_di_lookup_content",
        "command_plc": "_create_command_lookup_content",
        "obis": "_create_obis_lookup_content",
        "di_dlt645": "_create_dlt645_di_lookup_content",
        "afn": "_create_gdw_lookup_content",
        "oad": "_create_oad_lookup_content",
        "csg": "_create_csg_new_gen_lookup_content",
        "gw": "_create_gw_new_gen_lookup_content",
        "hdc10": "_create_hdc10_lookup_content",
        "modular": "_create_modular_iface_lookup_content",
    }
    if not kind:
        return None
    return mapping.get(kind)


__all__ = [
    "ProtocolSpec",
    "all_protocols",
    "get_protocol",
    "protocol_count",
    "combo_labels",
    "placeholder_for",
    "name_to_index",
    "protocols_with_frame_gen",
    "protocols_with_sequence_diagram",
    "protocols_with_monitor",
    "frame_gen_mode_for",
    "preset_mode_for",
    "make_validator",
    "build_validator_map",
    "build_gui_parser",
    "lookup_builder_method",
    "DLT645GuiParser",
    "CSGGenGuiParser",
    "GWGenGuiParser",
    "HDC10GuiParser",
]
