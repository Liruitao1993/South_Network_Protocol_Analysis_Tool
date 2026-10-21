# -*- coding: utf-8 -*-
"""生产测试架 —— 纯逻辑层（不依赖 Qt，可 offscreen / 无界面单测）。

本模块只做三件事：

1. **测试架参数帧组帧**：47 项参数（+ 帧头 2 项测试开关 = 现场参数表 49 项）
   → 53 字节参数区 → 75 字节整帧。
   现场样例帧逐字节复现在 :data:`ORACLE_FRAME_HEX`，``test/test_production_testbench.py``
   断其相等（任何字段顺序 / 字节数 / 校验范围改动都会让它变红）。
2. **checksum8**：8 位位组算术和（累加不溢出，``sum(bytes) & 0xFF``），
   支持「追加到末尾 / 覆盖末字节 / 插在 16H 前」三种落位方式。
3. **串口助手的文本编解码**：HEX / ASCII 双向、时间戳、显示渲染、配置读写。

帧结构（现场样例反推，逐字段已与参数表对齐）::

    68 | A(6) | 68 | 14(控制域) | 35(参数区长度=53) | 55 AA 55 AA(命令标识)
       | 测试STA(1) | 测试无线(1) | 参数区(53) | 保留(4×00) | CS8(1) | 16

    CS8 = 从首字节 68H 起、到 CS8 前一字节为止的 8 位算术和（含保留 4 字节）。

参数区字段顺序即 :data:`BODY_FIELDS` 的顺序，长度合计必须等于 53（模块导入即断言）。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Mapping, Optional, Sequence, Tuple

# ── 帧常量 ──────────────────────────────────────────────────────────────

FRAME_HEAD = 0x68
FRAME_END = 0x16
BENCH_CTRL = 0x14
BENCH_CMD = bytes.fromhex("55AA55AA")
BENCH_RESERVED = b"\x00\x00\x00\x00"
DEFAULT_ADDR_HEX = "AAAAAAAAAAAA"     # 广播地址（现场样例）
BODY_LEN = 53
FRAME_LEN = 75

#: 现场样例报文（协议基准，改动必须保持逐字节一致）
ORACLE_FRAME_HEX = (
    "68AAAAAAAAAAAA68143555AA55AA0100600E120818132F05FE0101000100000001"
    "0100010101010104200404900200090800900200000602300803B4107AA52A700F"
    "010005000000003916"
)


# ── 字段定义（唯一来源：界面生成、组帧、持久化都读它）────────────────────


@dataclass(frozen=True)
class FieldSpec:
    """一个参数的元信息。

    - ``size``：字节数（1/2/3/4）
    - ``default``：默认值（HEX 字符串，无分隔，长度 = size*2）
    - ``choices``：``((值, 文案), ...)``；非空 ⇒ 界面用下拉框（值写入 1 字节），否则用 HEX 输入框
    - ``tip``：输入框提示 / 下拉框说明
    """

    key: str
    label: str
    size: int = 1
    default: str = "00"
    choices: Tuple[Tuple[int, str], ...] = ()
    tip: str = ""

    @property
    def digits(self) -> int:
        return self.size * 2


def _f(key: str, label: str, default: str = "00", size: int = 1,
       choices: Sequence[Tuple[int, str]] = (), tip: str = "") -> FieldSpec:
    return FieldSpec(key=key, label=label, size=size, default=default,
                     choices=tuple(choices), tip=tip)


#: 帧头里的两字节测试项（不在 53 字节参数区内，但同属本页参数表）
HEADER_FIELDS: Tuple[FieldSpec, ...] = (
    _f("test_sta", "是否测试STA管脚", "01",
       choices=((0, "00 不测试"), (1, "01 测试STA（不测12V电源）")),
       tip="01=测试STA管脚、不测试12V电源；00=都不测"),
    _f("test_wireless", "是否测试无线", "00",
       choices=((0, "00 不测试"), (1, "01 测试")),
       tip="00=不测试无线；01=测试无线"),
)

#: 参数区 47 项（顺序 = 报文顺序，长度合计 = 53 字节）
BODY_FIELDS: Tuple[FieldSpec, ...] = (
    _f("charge_time", "充电时间", "60", tip="1 字节；现场样例 60H"),
    _f("discharge_time", "放电时间", "0E", tip="1 字节；现场样例 0EH"),
    _f("wireless_ver_date", "无线模块版本日期", "120818", size=3,
       tip="年-月-日（BCD），样例 12-08-18"),
    _f("static_current_hi", "静态电流上限", "13", tip="样例 13H"),
    _f("static_current_lo", "静态电流下限", "2F", tip="样例 2FH"),
    _f("dynamic_current_max", "动态电流最大值（保留）", "05FE", size=2,
       tip="2 字节保留位；现场样例 05FE"),
    _f("module_type", "测试模块类型", "01", tip="01=单相（样例）"),
    _f("has_capacitor", "是否带电容", "01",
       choices=((0, "00 带电容"), (1, "01 不带电容")),
       tip="01=不带电容；00=带电容"),
    _f("qa_mode", "QA测试 / 正常测试", "00",
       choices=((0, "00 正常测试"), (1, "01 QA测试")), tip="00=正常测试"),
    _f("id_storage", "ID 写 FLASH / OTP", "01",
       choices=((0, "00 OTP"), (1, "01 FLASH")), tip="01=FLASH；00=OTP"),
    _f("id_write", "是否进行ID设置", "00",
       choices=((0, "00 不进行"), (1, "01 进行")), tip="00=不进行ID设置"),
    _f("id_only", "测试架只测读ID", "00",
       choices=((0, "00 正常测试"), (1, "01 只测读ID")), tip="00=测试架正常测试"),
    _f("id_mask", "屏蔽读ID对比", "00",
       choices=((0, "00 不屏蔽"), (1, "01 屏蔽")), tip="00=不屏蔽读ID对比"),
    _f("cco_freq", "抄控器当前工作频率", "01", tip="01/04=2.2M；00=10M（样例 01=2.2M）"),
    _f("zero_cross", "是否测试过零电路", "01",
       choices=((0, "00 不测试"), (1, "01 测试")), tip="01=测试过零"),
    _f("second_freq_test", "第二频点测试", "00",
       choices=((0, "00 不进行"), (1, "01 进行")), tip="00=不进行第二频点测试"),
    _f("compat_old", "兼容旧版本测试", "01",
       choices=((0, "00 兼容"), (1, "01 不兼容")), tip="01=不兼容旧版本"),
    _f("meter_addr_hi", "表号高位地址", "01010101", size=4,
       tip="4 字节，样例 01 01 01 01"),
    _f("cco_freq_1", "第一次抄控器工作频率", "04", tip="04=2.2M"),
    _f("cco_pow_dsp_1", "第一次抄控器底层发射功率", "20", tip="样例 20H"),
    _f("cco_pow_3450_1", "第一次抄控器3450发射功率", "04", tip="样例 04H"),
    _f("module_freq_1", "第一次模块工作频率", "04", tip="04=2.2M"),
    _f("module_pow_dsp_1", "第一次模块底层发射功率", "90", tip="样例 90H"),
    _f("module_pow_3450_1", "第一次模块3450发射功率", "02", tip="样例 02H"),
    _f("cco_freq_2", "第二次抄控器工作频率", "00", tip="00=10M"),
    _f("cco_pow_dsp_2", "第二次抄控器底层发射功率", "09", tip="样例 09H"),
    _f("cco_pow_3450_2", "第二次抄控器3450发射功率", "08", tip="样例 08H"),
    _f("module_freq_2", "第二次模块工作频率", "00", tip="00=10M"),
    _f("module_pow_dsp_2", "第二次模块底层发射功率", "90", tip="样例 90H"),
    _f("module_pow_3450_2", "第二次模块3450发射功率", "02", tip="样例 02H"),
    _f("hw_reset", "是否测试硬件复位管脚", "00",
       choices=((0, "00 不测试"), (1, "01 测试")), tip="00=不测试"),
    _f("char_current", "特征电流标志位对比测试", "00",
       choices=((0, "00 不测试"), (1, "01 测试")), tip="00=不测试"),
    _f("meter_timeout", "读表超时配置", "06", tip="06=2S"),
    _f("wl1_bw", "无线1带宽配置", "02", tip="样例 02H"),
    _f("wl1_channel", "无线1信道号", "30", tip="样例 30H"),
    _f("wl1_power", "无线1发射功率", "08", tip="样例 08H"),
    _f("wl2_bw", "无线2带宽配置", "03", tip="样例 03H"),
    _f("wl2_channel", "无线2信道号", "B4", tip="样例 B4H"),
    _f("wl2_power", "无线2发射功率", "10", tip="样例 10H"),
    _f("rssi_rx_lo", "无线RSSI下限（接收）", "7A", tip="样例 7AH"),
    _f("rssi_rx_hi", "无线RSSI上限（接收）", "A5", tip="样例 A5H"),
    _f("rssi_tx_lo", "无线RSSI下限（发送）", "2A", tip="样例 2AH"),
    _f("rssi_tx_hi", "无线RSSI上限（发送）", "70", tip="样例 70H"),
    _f("discharge_delay", "烧录后放电延时", "0F", tip="样例 0FH"),
    _f("program_flash", "是否进行程序烧录", "01",
       choices=((0, "00 不烧录"), (1, "01 烧录")), tip="01=烧录"),
    _f("flash_erase", "是否进行FLASH擦除", "00",
       choices=((0, "00 不擦除"), (1, "01 擦除")), tip="00=不擦除"),
    _f("erase_delay", "FLASH擦除延时", "05", tip="样例 05H"),
)

FIELD_MAP: Dict[str, FieldSpec] = {s.key: s for s in (*HEADER_FIELDS, *BODY_FIELDS)}

#: 参数区分组（界面按组排布；顺序即显示顺序，键必须都在 BODY_FIELDS 内）
FIELD_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("① 基本测试项", (
        "module_type", "has_capacitor", "qa_mode", "id_storage", "id_write",
        "id_only", "id_mask", "cco_freq", "zero_cross", "second_freq_test",
        "compat_old", "hw_reset", "char_current", "meter_timeout",
    )),
    ("② 电流 / 版本 / 表号", (
        "charge_time", "discharge_time", "wireless_ver_date",
        "static_current_hi", "static_current_lo", "dynamic_current_max",
        "meter_addr_hi",
    )),
    ("③ 频率与发射功率（两轮）", (
        "cco_freq_1", "cco_pow_dsp_1", "cco_pow_3450_1",
        "module_freq_1", "module_pow_dsp_1", "module_pow_3450_1",
        "cco_freq_2", "cco_pow_dsp_2", "cco_pow_3450_2",
        "module_freq_2", "module_pow_dsp_2", "module_pow_3450_2",
    )),
    ("④ 无线 / RSSI", (
        "wl1_bw", "wl1_channel", "wl1_power",
        "wl2_bw", "wl2_channel", "wl2_power",
        "rssi_rx_lo", "rssi_rx_hi", "rssi_tx_lo", "rssi_tx_hi",
    )),
    ("⑤ 烧录", (
        "discharge_delay", "program_flash", "flash_erase", "erase_delay",
    )),
)

assert sum(f.size for f in BODY_FIELDS) == BODY_LEN, "参数区长度必须为 53 字节"


# ── 异常 ────────────────────────────────────────────────────────────────


class ParamError(ValueError):
    """参数非法（长度/非法字符/超范围）。``field`` 为字段 key（可能为空）。"""

    def __init__(self, message: str, field: str = ""):
        super().__init__(message)
        self.field = field


# ── HEX / 文本工具 ──────────────────────────────────────────────────────

_HEX_CLEAN_RE = re.compile(r"[\s,;:_\-]|0[xX]")


def clean_hex(text: str) -> str:
    """去掉空白 / 逗号 / 分号 / ``0x`` 前缀，返回纯 HEX 字符串（保留大小写）。"""
    return _HEX_CLEAN_RE.sub("", str(text or ""))


def parse_hex_text(text: str) -> bytes:
    """把用户输入的 HEX 文本转字节；非法输入抛 :class:`ParamError`（中文原因）。"""
    cleaned = clean_hex(text)
    if not cleaned:
        raise ParamError("报文为空")
    if len(cleaned) % 2:
        raise ParamError(f"HEX 长度为奇数（{len(cleaned)} 位），每个字节需要两位")
    if not re.fullmatch(r"[0-9A-Fa-f]+", cleaned):
        bad = sorted({c for c in cleaned if c not in "0123456789abcdefABCDEF"})
        raise ParamError("含非法 HEX 字符：" + " ".join(bad))
    return bytes.fromhex(cleaned)


def format_hex(data: bytes, sep: str = " ") -> str:
    """字节 → 大写 HEX（默认空格分隔）。"""
    return sep.join(f"{b:02X}" for b in bytes(data))


def format_hex_field(data: bytes) -> str:
    """字节 → 紧凑大写 HEX（持久化 / 输入框回填用）。"""
    return bytes(data).hex().upper()


def parse_ascii_text(text: str) -> bytes:
    """ASCII 模式的发送内容 → 字节（UTF-8；``\\r``/``\\n`` 原样发送）。"""
    return str(text or "").encode("utf-8")


def render_display(data: bytes, mode: str = "hex") -> str:
    """串口助手显示渲染：HEX 用空格分隔；ASCII 把不可打印字节显示成 ``.``。"""
    raw = bytes(data)
    if str(mode).lower() == "ascii":
        return "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
    return format_hex(raw)


def timestamp_text(moment: Optional[datetime] = None, with_ms: bool = True) -> str:
    """日志行时间戳：``YYYY-MM-DD HH:MM:SS.mmm``（默认带毫秒）。"""
    moment = moment or datetime.now()
    if with_ms:
        return moment.strftime("%Y-%m-%d %H:%M:%S.") + f"{moment.microsecond // 1000:03d}"
    return moment.strftime("%Y-%m-%d %H:%M:%S")


# ── checksum8 ───────────────────────────────────────────────────────────

CS_MODE_APPEND = "append"        # 追加到末尾
CS_MODE_REPLACE_LAST = "replace_last"   # 覆盖最后一个字节
CS_MODE_BEFORE_END = "before_end"       # 插在末尾 16H 之前（68 家族）

CS_MODES: Tuple[Tuple[str, str], ...] = (
    (CS_MODE_APPEND, "追加到末尾"),
    (CS_MODE_REPLACE_LAST, "覆盖末字节"),
    (CS_MODE_BEFORE_END, "插在 16H 前"),
)


def checksum8(data: bytes) -> int:
    """8 位位组算术和：逐字节累加，只保留低 8 位（不溢出）。"""
    return sum(bytes(data)) & 0xFF


def apply_checksum8(data: bytes, mode: str = CS_MODE_APPEND) -> bytes:
    """按指定落位方式写入 checksum8。

    - ``append``：校验覆盖全部字节，结果追加在末尾
    - ``replace_last``：校验覆盖除末字节外的全部字节，结果覆盖末字节
    - ``before_end``：末字节应为 ``16H``（68 家族收尾）；校验覆盖它之前的全部字节，
      插在它与前一字节之间。末字节不是 ``16H`` 时按 ``append`` 处理（不猜）
    """
    raw = bytes(data)
    if not raw:
        return raw
    mode = str(mode)
    if mode == CS_MODE_REPLACE_LAST:
        return raw[:-1] + bytes([checksum8(raw[:-1])])
    if mode == CS_MODE_BEFORE_END and raw[-1] == FRAME_END:
        return raw[:-1] + bytes([checksum8(raw[:-1])]) + raw[-1:]
    return raw + bytes([checksum8(raw)])


# ── 测试架参数帧 ────────────────────────────────────────────────────────


def default_values() -> Dict[str, str]:
    """全部参数的默认值（HEX 字符串，紧凑大写）。现场样例帧的复现值。"""
    return {spec.key: spec.default.upper() for spec in (*HEADER_FIELDS, *BODY_FIELDS)}


def _field_bytes(spec: FieldSpec, raw: object) -> bytes:
    """单个字段的输入 → 定长字节（下拉框字段允许传 int / "1" / "01"）。"""
    if spec.choices:
        if isinstance(raw, int):
            value = raw
        else:
            text = clean_hex(str(raw if raw is not None else ""))
            if not text:
                value = int(spec.default, 16)
            elif re.fullmatch(r"[0-9A-Fa-f]{1,2}", text):
                value = int(text, 16)
            else:
                raise ParamError(f"{spec.label}：取值格式非法（{raw!r}）", spec.key)
        allowed = {v for v, _ in spec.choices}
        if value not in allowed:
            raise ParamError(
                f"{spec.label}：{value:02X} 不在可选范围（{'/'.join(f'{v:02X}' for v in sorted(allowed))}）",
                spec.key,
            )
        return bytes([value])

    text = clean_hex(str(raw if raw is not None else ""))
    if not text:
        text = spec.default
    if not re.fullmatch(r"[0-9A-Fa-f]+", text):
        raise ParamError(f"{spec.label}：含非法 HEX 字符（{text}）", spec.key)
    if len(text) != spec.digits:
        raise ParamError(
            f"{spec.label}：需要 {spec.size} 字节（{spec.digits} 位 HEX），当前 {len(text)} 位",
            spec.key,
        )
    return bytes.fromhex(text)


def normalize_addr(addr_hex: str) -> bytes:
    """地址域 6 字节（``AA AA AA AA AA AA`` = 广播）。"""
    text = clean_hex(addr_hex)
    if len(text) != 12 or not re.fullmatch(r"[0-9A-Fa-f]{12}", text):
        raise ParamError("地址域需要 6 字节（12 位 HEX），例如 AAAAAAAAAAAA")
    return bytes.fromhex(text)


def encode_body(values: Mapping[str, object]) -> bytes:
    """47 项参数 → 53 字节参数区（顺序 = :data:`BODY_FIELDS`）。"""
    out = bytearray()
    for spec in BODY_FIELDS:
        out += _field_bytes(spec, values.get(spec.key, spec.default))
    if len(out) != BODY_LEN:            # 防御：字段表被改动时立刻暴露
        raise ParamError(f"参数区长度异常：{len(out)}（应为 {BODY_LEN}）")
    return bytes(out)


def build_bench_frame(values: Optional[Mapping[str, object]] = None,
                      addr_hex: str = DEFAULT_ADDR_HEX) -> bytes:
    """按参数表组出完整的测试架参数帧（含 checksum8 与 16H 收尾）。

    结构见模块 docstring；参数区长度写进长度域（恒 53），校验覆盖首字节到保留位末字节。
    """
    vals = dict(default_values())
    if values:
        vals.update({k: v for k, v in values.items() if k in FIELD_MAP})
    addr = normalize_addr(addr_hex)
    sta = _field_bytes(FIELD_MAP["test_sta"], vals.get("test_sta", "01"))
    wireless = _field_bytes(FIELD_MAP["test_wireless"], vals.get("test_wireless", "00"))
    body = encode_body(vals)

    data = bytearray()
    data.append(FRAME_HEAD)
    data += addr
    data.append(FRAME_HEAD)
    data.append(BENCH_CTRL)
    data.append(len(body))
    data += BENCH_CMD
    data += sta + wireless
    data += body
    data += BENCH_RESERVED
    data.append(checksum8(data))
    data.append(FRAME_END)
    return bytes(data)


# ── 发送框 ──────────────────────────────────────────────────────────────

SEND_MODE_HEX = "hex"
SEND_MODE_ASCII = "ascii"
SEND_BOX_COUNT = 5
CS8_LABELS = dict(CS_MODES)


@dataclass
class SendBoxConfig:
    """一条发送配置（界面 5 个框共用同一结构，便于落盘与单测）。"""

    name: str = ""
    text: str = ""
    mode: str = SEND_MODE_HEX
    cs8: bool = False
    cs8_mode: str = CS_MODE_APPEND

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "text": self.text,
            "mode": self.mode if self.mode in (SEND_MODE_HEX, SEND_MODE_ASCII) else SEND_MODE_HEX,
            "cs8": bool(self.cs8),
            "cs8_mode": self.cs8_mode if self.cs8_mode in CS8_LABELS else CS_MODE_APPEND,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "SendBoxConfig":
        raw = data if isinstance(data, Mapping) else {}
        return cls(
            name=str(raw.get("name", "") or ""),
            text=str(raw.get("text", "") or ""),
            mode=str(raw.get("mode", SEND_MODE_HEX) or SEND_MODE_HEX),
            cs8=bool(raw.get("cs8", False)),
            cs8_mode=str(raw.get("cs8_mode", CS_MODE_APPEND) or CS_MODE_APPEND),
        )


def build_send_payload(cfg: SendBoxConfig) -> bytes:
    """发送框内容 → 真正写到串口的字节（已按需算好 checksum8）。"""
    if cfg.mode == SEND_MODE_ASCII:
        data = parse_ascii_text(cfg.text)
    else:
        data = parse_hex_text(cfg.text)
    if not data:
        raise ParamError("没有可发送的内容")
    return apply_checksum8(data, cfg.cs8_mode) if cfg.cs8 else data


def frame_payload(frame: bytes, mode: str = SEND_MODE_HEX) -> bytes:
    """生成好的报文的**发送形态**（与发送框的 HEX / ASCII 同一语义）。

    - ``hex``：原样发送二进制帧（默认；现场测试架走这条）
    - ``ascii``：把报文的**大写紧凑 HEX 文本**按 ASCII 字符发出去
      （例如 75 字节帧 → 150 个字符 ``68AAAAAAAA…916``）；
      接 ASCII 文本协议的工装才用，不会把二进制「猜」成字符
    """
    raw = bytes(frame)
    if str(mode).lower() == SEND_MODE_ASCII:
        return format_hex_field(raw).encode("ascii")
    return raw


# ── 配置持久化（纯逻辑，路径由调用方给）──────────────────────────────────

CONFIG_VERSION = 1

#: 三栏默认宽度（左发送配置 / 中接收日志 / 右测试架参数）——界面与落盘默认值共用
DEFAULT_LAYOUT_SIZES = (380, 640, 500)


def default_config() -> dict:
    return {
        "version": CONFIG_VERSION,
        "params": default_values(),
        "addr_hex": DEFAULT_ADDR_HEX,
        "send_boxes": [SendBoxConfig(name=f"发送 {i + 1}").to_dict()
                       for i in range(SEND_BOX_COUNT)],
        "display": {"mode": "hex", "timestamp": True, "autoscroll": True},
        # 「发送参数帧」的发送形态（与发送框同一语义：hex=二进制帧 / ascii=HEX 文本）
        "params_mode": "hex",
        "layout": {"left_collapsed": False, "right_collapsed": False,
                   "sizes": list(DEFAULT_LAYOUT_SIZES)},
    }


def merge_config(raw: object) -> dict:
    """把落盘内容并进默认结构（缺键/脏值一律回落默认，绝不抛）。"""
    cfg = default_config()
    if not isinstance(raw, Mapping):
        return cfg
    if isinstance(raw.get("params"), Mapping):
        for spec in (*HEADER_FIELDS, *BODY_FIELDS):
            value = raw["params"].get(spec.key)
            if value is None:
                continue
            text = clean_hex(str(value)).upper()
            if not text:
                continue
            if not re.fullmatch(r"[0-9A-F]+", text):
                continue                      # 脏值（非 HEX）直接回落默认
            if spec.choices:
                if len(text) <= 2 and int(text, 16) in {v for v, _ in spec.choices}:
                    cfg["params"][spec.key] = f"{int(text, 16):02X}"
                continue
            if len(text) == spec.digits:
                cfg["params"][spec.key] = text
    addr = clean_hex(str(raw.get("addr_hex", "") or ""))
    if len(addr) == 12 and re.fullmatch(r"[0-9A-Fa-f]{12}", addr):
        cfg["addr_hex"] = addr.upper()
    boxes = raw.get("send_boxes")
    if isinstance(boxes, (list, tuple)):
        merged = [SendBoxConfig.from_dict(b) for b in boxes[:SEND_BOX_COUNT]]
        while len(merged) < SEND_BOX_COUNT:
            merged.append(SendBoxConfig(name=f"发送 {len(merged) + 1}"))
        cfg["send_boxes"] = [b.to_dict() for b in merged]
    display = raw.get("display")
    if isinstance(display, Mapping):
        mode = str(display.get("mode", "hex"))
        if mode in (SEND_MODE_HEX, SEND_MODE_ASCII):
            cfg["display"]["mode"] = mode
        cfg["display"]["timestamp"] = bool(display.get("timestamp", True))
        cfg["display"]["autoscroll"] = bool(display.get("autoscroll", True))
    params_mode = str(raw.get("params_mode", "hex") or "hex")
    if params_mode in (SEND_MODE_HEX, SEND_MODE_ASCII):
        cfg["params_mode"] = params_mode
    layout = raw.get("layout")
    if isinstance(layout, Mapping):
        for key in ("left_collapsed", "right_collapsed"):
            if key in layout:
                cfg["layout"][key] = bool(layout[key])
        sizes = layout.get("sizes")
        if isinstance(sizes, (list, tuple)) and len(sizes) == 3:
            try:
                values = [int(v) for v in sizes]
            except (TypeError, ValueError):
                values = []
            if values and all(1 <= v <= 8000 for v in values):
                cfg["layout"]["sizes"] = values
    return cfg


def load_config(path: str) -> dict:
    """读配置（文件不存在/损坏一律回落默认）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return merge_config(json.load(fh))
    except (OSError, ValueError):
        return default_config()


def save_config(path: str, data: Mapping[str, object]) -> bool:
    """写配置（原子替换：先写 .tmp 再 replace，避免半截 JSON）。"""
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merge_config(data), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


__all__ = [
    "BENCH_CMD", "BENCH_CTRL", "BENCH_RESERVED", "BODY_FIELDS", "BODY_LEN",
    "CS8_LABELS", "CS_MODES", "CS_MODE_APPEND", "CS_MODE_BEFORE_END",
    "CS_MODE_REPLACE_LAST", "DEFAULT_ADDR_HEX", "FIELD_GROUPS", "FIELD_MAP",
    "FRAME_END", "FRAME_HEAD", "FRAME_LEN", "FieldSpec", "HEADER_FIELDS",
    "ORACLE_FRAME_HEX", "ParamError", "SEND_BOX_COUNT", "SEND_MODE_ASCII",
    "SEND_MODE_HEX", "SendBoxConfig", "apply_checksum8", "build_bench_frame",
    "build_send_payload", "checksum8", "clean_hex", "default_config",
    "default_values", "encode_body", "format_hex", "format_hex_field",
    "frame_payload", "load_config", "merge_config", "normalize_addr",
    "parse_ascii_text", "parse_hex_text", "render_display", "save_config",
    "timestamp_text",
]
