# -*- coding: utf-8 -*-
"""DL/T 645-2007 组帧命令 schema 与数据域拼装（纯逻辑，无 Qt）

命令组织采用**混合式**：12 个功能码作为命令骨架；其中带 DI 的命令（读 11H /
读后续 12H / 写 14H 及对应应答）由 `dlt645_di.json`（1099 条 DI）驱动，选中 DI
后按其 `data_type` 掩码自动推导字段模板；不带 DI 的功能命令（校时 08H / 地址
13H·15H / 冻结 16H / 速率 17H / 密码 18H / 清零 19H·1AH·1BH）使用固定字段模板。

cmd_key 约定：`(direction, func_code)`

- direction ∈ {"req", "rsp", "err"}：主站请求 / 从站正常应答 / 从站异常应答
- func_code 为 **5 位功能码（D4~D0）**，与 `dlt645_parser.py` 的 `ctrl & 0x1F` 同口径；
  传 0x91 这类完整控制码也可，:func:`get_command` 会自动 `& 0x1F` 归一化
- 控制码由 direction 决定：req → func；rsp → 0x80|func（如 91H）；
  err → 0xC0|func（如 D1H）

数据域长度依据 DL/T645-2007 §7.4~§7.12 实测确认：改密码 18H L=0CH（含 DI 前缀）、
最大需量清零 19H 与电表清零 1AH L=08H（无 DI）、事件清零 1BH L=0CH（含事件标识）、
冻结 16H L=04H（线序 mm hh DD MM）、广播校时 08H L=06H（线序 ss mm hh DD MM YY）、
更改通信速率 17H L=01H、写通信地址 15H L=06H、写地址应答 95H L=00H。
"""

from typing import Any, Dict, List, Optional

from dlt645_data_codec import (
    bcd_pack,
    encode_demand_with_time,
    encode_value,
    mask_shape,
    pack_change_password,
    pack_password,
    pack_operator,
    pack_write_request,
    parse_hex,
)
from dlt645_frame_gen import encode_addr, encode_di
from dlt645_pv_wireless_frame import (
    REQ_WITH_PAYLOAD_DI,
    build_wireless_fields,
    build_wireless_payload,
    wireless_di_info,
    wireless_request_extra,
)

REQ, RSP, ERR = "req", "rsp", "err"

# ---------------------------------------------------------------------------
# 字段类型（UI 据此渲染控件；本模块只负责取值与编码）
# ---------------------------------------------------------------------------
F_DI = "di"              # DI 下拉（dlt645_di.json 1099 条，支持搜索）
F_DI_VALUE = "di_value"  # 按所选 DI 的 data_type 掩码编码
F_DEMAND = "demand"      # 最大需量值（XX.XXXX）
F_DEMAND_TIME = "demand_time"   # 需量发生时间（MM-DD-hh-mm）
F_HEX = "hex"            # 裸 hex
F_PA = "pa"              # 密码权限 PA（1 字节）
F_PWD = "pwd"            # 密码 P0P1P2（3 字节）
F_OPERATOR = "operator"  # 操作者代码 C0~C3（4 字节）
F_DATETIME = "datetime"  # 年月日时分秒
F_TIME = "time"          # 月日时分
F_ADDR = "addr"          # 通信地址（6 字节）

#: 掩码 → 无法按掩码推导时的兜底类型
FALLBACK_TYPE = F_HEX


def fld(name: str, ftype: str, default: str = "", hint: str = "",
        length: Optional[int] = None) -> Dict:
    """构造一个字段定义（与既有三套 schema 的字段字典同构）。"""
    d: Dict[str, Any] = {"name": name, "type": ftype, "default": default, "hint": hint}
    if length is not None:
        d["length"] = length
    return d


def _di_field() -> Dict:
    return fld("数据标识 DI", F_DI, "00010000",
               "选择或输入 8 位 DI（如 00010000 当前正向有功总电能）")


def _pwd_fields(pa_label: str = "密码权限 PA",
                pwd_label: str = "密码 P0P1P2") -> List[Dict]:
    return [
        fld(pa_label, F_PA, "00", "00 最高权限，02=清零级，04=写数据级"),
        fld(pwd_label, F_PWD, "000000", "3 字节密码（hex），出厂默认 000000"),
        fld("操作者代码 C0~C3", F_OPERATOR, "00000000", "4 字节，记录操作人员信息"),
    ]


# ---------------------------------------------------------------------------
# 命令 schema
# ---------------------------------------------------------------------------
_ADDR_AA = "AAAAAAAAAAAA"
_ADDR_99 = "999999999999"
_ADDR_ZERO = "000000000000"

DLT645_CMD_SCHEMA: Dict[tuple, Dict] = {
    # ── 主站请求 ──────────────────────────────────────────────────────
    (REQ, 0x11): {
        "name": "读数据", "func": 0x11, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": 4,
        "fields": [_di_field()],
        "hint": "数据域仅 DI 4 字节（L=04H）",
    },
    (REQ, 0x12): {
        "name": "读后续数据", "func": 0x12, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": None,
        "fields": [_di_field(),
                   fld("附加数据", F_HEX, "", "选填，按裸 hex 追加在 DI 之后")],
        "hint": "用于读取超长数据项的后续帧",
    },
    (REQ, 0x13): {
        "name": "读通信地址", "func": 0x13, "dir": 0, "addr_default": _ADDR_AA,
        "has_di": False, "data_len": 0, "fields": [],
        "hint": "仅支持点对点；地址域填 AAH×6，数据域为空（L=00H）",
    },
    (REQ, 0x14): {
        "name": "写数据", "func": 0x14, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": None,
        "fields": [_di_field()] + _pwd_fields() + [
            fld("写入数据", F_DI_VALUE, "",
                "按所选 DI 的格式填写（如 XXXXXX.XX 填 123456.78）；"
                "留空则使用下方裸 hex"),
            fld("写入数据(裸hex)", F_HEX, "",
                "选填兜底：已按 +0x33 之前的逻辑字节填写"),
        ],
        "hint": "数据域 = DI(4) + PA P0P1P2(4) + C0~C3(4) + 数据(m)，L=0CH+m",
    },
    (REQ, 0x15): {
        "name": "写通信地址", "func": 0x15, "dir": 0, "addr_default": _ADDR_AA,
        "has_di": False, "data_len": 6,
        "fields": [fld("新通信地址", F_ADDR, "000000000001",
                      "12 位地址（高位在前的书写序），线上自动转为低字节在前")],
        "hint": "地址域填 AAH×6，数据域为待写入的 6 字节新地址（L=06H）；须配合编程键",
    },
    (REQ, 0x16): {
        "name": "冻结命令", "func": 0x16, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 4,
        "fields": [fld("冻结时间", F_TIME, "01-01-00-00",
                      "MM-DD-hh-mm（月-日-时-分），线序自动转为 mm hh DD MM")],
        "hint": "数据域 MMDDhhmm 4 字节（L=04H）",
    },
    (REQ, 0x17): {
        "name": "更改通信速率", "func": 0x17, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 1,
        "fields": [fld("速率特征字", F_HEX, "44",
                      "1 字节，取值见 DL/T645-2007 §7.8（44H 常见对应 9600bps）",
                      length=1)],
        "hint": "数据域 1 字节（L=01H）；速率在下一次通信生效",
    },
    (REQ, 0x08): {
        "name": "广播校时", "func": 0x08, "dir": 0, "addr_default": _ADDR_99,
        "has_di": False, "data_len": 6,
        "fields": [fld("校时时间", F_DATETIME, "",
                      "YYYY-MM-DD hh:mm:ss，留空则用当前电脑时间；"
                      "线序自动转为 ss mm hh DD MM YY")],
        "hint": "地址域填 99H×6，数据域 YYMMDDhhmmss 6 字节（L=06H）；不要求应答",
    },
    (REQ, 0x18): {
        "name": "修改密码", "func": 0x18, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": 12,
        "fields": [_di_field(),
                   fld("原密码权限 PA", F_PA, "00", ""),
                   fld("原密码 P0P1P2", F_PWD, "000000", ""),
                   fld("新密码权限 PA", F_PA, "00", ""),
                   fld("新密码 P0P1P2", F_PWD, "000000", "")],
        "hint": "数据域 = DI(4) + 原密码组(4) + 新密码组(4)，L=0CH",
    },
    (REQ, 0x19): {
        "name": "最大需量清零", "func": 0x19, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 8,
        "fields": _pwd_fields(),
        "hint": "数据域 = PA P0P1P2(4) + C0~C3(4)，L=08H（**无 DI 前缀**）",
    },
    (REQ, 0x1A): {
        "name": "电表清零", "func": 0x1A, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 8,
        "fields": _pwd_fields(),
        "hint": "数据域 = PA P0P1P2(4) + C0~C3(4)，L=08H（**无 DI 前缀**）",
    },
    (REQ, 0x1B): {
        "name": "事件清零", "func": 0x1B, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 12,
        "fields": _pwd_fields() + [
            fld("事件标识", F_HEX, "FFFFFFFF",
                "4 字节；FFFFFFFF 表示全部事件记录", length=4)],
        "hint": "数据域 = PA P0P1P2(4) + C0~C3(4) + 事件标识(4)，L=0CH",
    },

    # ── 从站正常应答（读类带数据，其余 L=00H）──────────────────────────
    (RSP, 0x11): {
        "name": "读数据应答", "func": 0x11, "dir": 1, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": None,
        "fields": [_di_field(),
                   fld("数据值", F_DI_VALUE, "",
                       "按所选 DI 的格式填写（如 XXXXXX.XX 填 123456.78）；"
                       "留空则使用下方裸 hex"),
                   fld("数据值(裸hex)", F_HEX, "", "选填兜底")],
        "hint": "C=91H；数据域 = DI(4) + 数据(m)",
    },
    (RSP, 0x12): {
        "name": "读后续数据应答", "func": 0x12, "dir": 1, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": None,
        "fields": [_di_field(), fld("数据值(裸hex)", F_HEX, "", "")],
        "hint": "C=92H（无后续）/ B1H（有后续）",
    },
    (RSP, 0x13): {
        "name": "读通信地址应答", "func": 0x13, "dir": 1, "addr_default": _ADDR_AA,
        "has_di": False, "data_len": 6,
        "fields": [fld("通信地址", F_ADDR, "000000000001", "")],
        "hint": "C=93H；数据域为 6 字节表地址",
    },
    (RSP, 0x14): {
        "name": "写数据应答", "func": 0x14, "dir": 1, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": 4,
        "fields": [_di_field()],
        "hint": "C=94H；数据域仅 DI（L=04H）",
    },
    (RSP, 0x15): {
        "name": "写通信地址应答", "func": 0x15, "dir": 1, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 0, "fields": [],
        "hint": "C=95H；地址域为新地址，数据域为空（L=00H）",
    },

    # ── 无线模组接口扩展（南网光伏协议转换单元 V1.6）：06H / 86H / 1EH / 9EH ──
    # 这四个功能码在 DL/T 645-2007 里**不存在**，是本手册 §4.0 表定义的扩展；
    # 86H 与 06H 的 ctrl & 0x1F 同为 0x06、方向相反，靠 DIR 位区分，不能合并。
    (REQ, 0x06): {
        "name": "上报确认应答（无线）", "func": 0x06, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": None,
        "fields": [_di_field(),
                   fld("确认数据", F_DI_VALUE, "",
                       "回带与上报帧相同的 DI + 数据；无线 DI 按手册字段自动编码"),
                   fld("确认数据(裸hex)", F_HEX, "", "选填兜底")],
        "hint": "C=06H；手册 §4.1.2：主站对 86H 主动上报的确认，数据域与上报帧同构（DI+DATA）",
    },
    (RSP, 0x06): {
        "name": "主动上报数据（无线）", "func": 0x06, "dir": 1, "addr_default": _ADDR_ZERO,
        "has_di": True, "data_len": None,
        "fields": [_di_field(),
                   fld("上报数据", F_DI_VALUE, "",
                       "按所选 DI 填写；无线 DI 按手册字段自动编码"),
                   fld("上报数据(裸hex)", F_HEX, "", "选填兜底")],
        "hint": "C=86H；手册 §4.1.2：从站主动上报，数据域 = DI + DATA（明文）",
    },
    (REQ, 0x1E): {
        "name": "在网状态上报（无线）", "func": 0x1E, "dir": 0, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 5,
        "fields": [fld("在网状态", F_HEX, "1",
                       "0=离网、1=在网；数据域固定为 028100FF + 状态（手册 §4.3.1）")],
        "hint": "C=1EH；地址域填无线接口转换器地址，L=05H，DI 固定 028100FF",
    },
    (RSP, 0x1E): {
        "name": "在网状态确认（无线）", "func": 0x1E, "dir": 1, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 0, "fields": [],
        "hint": "C=9EH；接口转换器对 1EH 的确认应答，数据域为空（L=00H）",
    },
}

#: 未在上表显式列出的正常应答（冻结/速率/密码/清零等）：数据域为空（L=00H）
_EMPTY_RSP_FUNCS = (0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x08)


def _empty_rsp(func: int) -> Dict:
    from dlt645_data_codec import FUNC_NAMES
    return {
        "name": f"{FUNC_NAMES.get(func, '命令%02X' % func)}应答",
        "func": func, "dir": 1, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 0, "fields": [],
        "hint": "正常应答数据域为空（L=00H）",
    }


def _err_rsp(func: int) -> Dict:
    from dlt645_data_codec import FUNC_NAMES
    return {
        "name": f"{FUNC_NAMES.get(func, '命令%02X' % func)}异常应答",
        "func": func, "dir": 1, "err": True, "addr_default": _ADDR_ZERO,
        "has_di": False, "data_len": 1,
        "fields": [fld("错误信息字 ERR", F_HEX, "01",
                       "1 字节位域（附录C）：bit0 其他错误 / bit1 无请求数据 / "
                       "bit2 密码错 / bit3 速率不能改 / bit4 日时段数超 / "
                       "bit5 费率数超 / bit6 年时区数超", length=1)],
        "hint": "C=0xC0|功能码（如读数据异常应答 D1H）；数据域为 ERR 1 字节",
    }


def _norm_key(cmd_key) -> tuple:
    direction, func = cmd_key
    if direction not in (REQ, RSP, ERR):
        raise ValueError(f"未知方向 {direction!r}（应为 req/rsp/err）")
    try:
        func_int = int(func) & 0x1F
    except (TypeError, ValueError) as e:
        # 保持原异常类型（ValueError），仅补充可读信息
        raise ValueError(f"未知功能码 {func!r}（应为形如 '11' 的十六进制数字串）") from e
    return (direction, func_int)


def get_command(cmd_key) -> Dict:
    """取命令 spec；未显式定义的应答/异常应答按通用规则合成。"""
    key = _norm_key(cmd_key)
    spec = DLT645_CMD_SCHEMA.get(key)
    if spec is not None:
        return spec
    direction, func = key
    if direction == ERR:
        return _err_rsp(func)
    if direction == RSP and func in _EMPTY_RSP_FUNCS:
        return _empty_rsp(func)
    from dlt645_data_codec import FUNC_NAMES
    raise ValueError(
        f"暂不支持该命令：direction={direction} func=0x{func:02X}"
        f"（{FUNC_NAMES.get(func, '未知功能码')}）")


def list_commands() -> List[tuple]:
    """命令下拉数据源：[(cmd_key, 分组标签, 显示文本)]，按 请求/应答/异常 分组。"""
    out = []
    for key, spec in DLT645_CMD_SCHEMA.items():
        if key[0] != REQ:
            continue
        out.append((key, "主站请求", f"{spec['name']}（C={spec['func']:02X}H）"))
    for func, group in ([(f, "从站应答")
                         for f in (0x11, 0x12, 0x13, 0x14, 0x15) + _EMPTY_RSP_FUNCS]
                        + [(0x06, "从站上报"), (0x1E, "从站上报")]):
        spec = get_command((RSP, func))
        ctrl = 0x80 | func
        out.append(((RSP, func), group, f"{spec['name']}（C={ctrl:02X}H）"))
    for func in (0x11, 0x14, 0x18, 0x1A, 0x1B):
        spec = get_command((ERR, func))
        out.append(((ERR, func), "异常应答", f"{spec['name']}（C={0xC0 | func:02X}H）"))
    return out


# ---------------------------------------------------------------------------
# DI 驱动的字段模板
# ---------------------------------------------------------------------------

def get_di_info(di_code: str) -> Dict:
    """DI → {name, unit, data_type, length}；查不到返回空壳（不抛异常）。

    本手册（光伏协议转换单元·无线模组接口 V1.6）扩展的 12 个 DI **优先**由
    :func:`dlt645_pv_wireless_frame.wireless_di_info` 给出 —— 否则 ``04E60001``
    会命中附件1 的旧口径（长度列 16），与本手册的 ``1+6×M`` 冲突并误报长度。
    """
    wl = wireless_di_info(di_code)
    if wl is not None:
        return wl
    try:
        from dlt645_di_lookup import get_dlt645_di_lookup
        info = get_dlt645_di_lookup().get_di_info(di_code)
    except Exception:
        info = None
    if not info:
        return {"name": "", "unit": "", "data_type": "", "length": 0}
    try:
        _nlen = int(info.get("length") or 0)
    except (TypeError, ValueError):
        _nlen = 0          # 表内 length 异常时安全降级（生成物正常为数字）
    return {"name": info.get("name", ""), "unit": info.get("unit", ""),
            "data_type": info.get("data_type", ""),
            "length": _nlen}


def _is_multivalue_dt(dt: str) -> bool:
    """多值数据块掩码判定（扩展协议用 `|` 分隔同一 DI 下的多个值）。

    例：`XXX.X|XXX.X|XXX.X`（光伏逆变器电压块 3 值）、
    `YYMMDDhhmmss|YYMMDDhhmmss|XX...XX|XX...XX`（开关机控制事件块）。
    这类 DI 的**单值**模板（数值/时间/日期/通信地址）一律不适用 —— 组帧按裸字节填写。

    零误伤依据（实测）：标准 DI 表 `dlt645_di.json` 1099 条中 **无任何** `|` 掩码；
    `|` 只出现在 `dlt645_pv_ext.py` 的扩展协议条目（682 键中 467 键）。
    组帧支持该扩展协议属范围外（见 AGENTS.md §5.4），此前模板会错配成
    时间/日期/通信地址字段，此处只做兜底、不实现结构化组帧。
    """
    return "|" in dt


def build_di_fields(di_code: str) -> List[Dict]:
    """按 DI 的 data_type 掩码推导数据值字段模板（混合式的核心）。

    - 数值掩码（XXXXXX.XX 等）→ 十进制输入框，提示带位数/小数点/单位
    - 最大需量掩码（XX.XXXX,MDHM）→ 拆成「需量值」+「发生时间」两个字段
    - 位串 BS32/BS64/BS96、变长 XX...XX、日期/时间 → 对应专用控件
    - 空掩码（length=0）→ 无数据域，返回空列表
    - 未识别掩码 → 回退裸 hex 并标注
    """
    wl = build_wireless_fields(di_code)
    if wl is not None:
        return wl       # 本手册扩展 DI：字段模板由 dlt645_pv_wireless_frame 提供

    info = get_di_info(di_code)
    dt = (info["data_type"] or "").strip()
    nlen = info["length"]
    label = info["name"] or di_code

    if not dt and not info["name"] and not nlen:
        # DI 不在 dlt645_di.json 映射表：无法推导格式，回退裸字节（仍可组帧）
        # 注意用 info["name"] 而非 label 判空——label 会回退成 di_code 而永不为空
        return [fld("数据内容", FALLBACK_TYPE, "",
                    f"DI {di_code} 不在映射表，格式未知，按裸字节填写")]

    if not dt and nlen == 0:
        return []

    # LME 自定义接口（手册 4.2/4.6）：查询请求的结构化模板
    if di_code == "FF00DD01":
        return [fld("条目列表", "lme_entries", "",
                    "格式 分类/数据ID 逗号分隔，如 0/1,2/3；"
                    "留空 = M=0 读取模块全部支持信息")]
    if di_code == "04FFAAF9":
        return []   # 手册 4.2 查询请求无数据单元

    if _is_multivalue_dt(dt):
        # 扩展协议的多值数据块：不套用任何单值模板（否则会被当成时间/日期/数值）
        return [fld("数据内容", FALLBACK_TYPE, "",
                    f"{label}：多值数据块（{dt}），{nlen} 字节，按裸字节填写"
                    "（组帧支持该扩展协议属范围外）")]

    if dt == "XX.XXXX,MDHM":
        return [
            fld("需量值", F_DEMAND, "", f"{label}：XX.XXXX（kW）"),
            fld("发生时间", F_DEMAND_TIME, "", "MM-DD-hh-mm（月-日-时-分）"),
        ]

    total, decimals, nbytes = mask_shape(dt)
    if total:
        tip = f"{label}：格式 {dt}"
        if decimals:
            tip += f"，{total - decimals} 位整数 + {decimals} 位小数"
        else:
            tip += f"，{total} 位整数"
        if info["unit"]:
            tip += f"，单位 {info['unit'].split(',')[0]}"
        return [fld("数据值", F_DI_VALUE, "", tip)]

    up = dt.upper()
    if up.startswith("BS"):
        _bits = None
        try:
            _bits = int(up[2:]) // 8      # 非数字/空串时保持 None（与原先 isdigit 判据等价）
        except ValueError:
            _bits = None
        want = nlen or _bits
        return [fld("位串内容", F_HEX, "", f"{label}：{dt}，{want} 字节 hex", want)]
    if "YYYYMMDD" in up:
        return [fld("日期", F_DI_VALUE, "", f"{label}：YYYY-MM-DD")]
    if "hhmmss" in dt.lower():
        return [fld("时间", F_DI_VALUE, "", f"{label}：hh:mm:ss")]
    if set(up) == {"N"} and len(up) >= 12:
        # 仅标准「通信地址」（掩码 NNNNNNNNNNNN，12 位）适用；
        # 扩展协议存在短全 N 掩码（如运行状态 `NN`，1 字节），套用会得到错误字段名
        return [fld("通信地址", F_ADDR, "", f"{label}：12 位地址")]
    if nlen:
        return [fld("数据内容", FALLBACK_TYPE, "",
                    f"{label}：{dt or '未声明格式'}，{nlen} 字节"
                    + ("（LME 自定义接口，按裸字节填写）" if dt == "XX...XX" else ""))]
    return [fld("数据内容", FALLBACK_TYPE, "", f"{label}：未识别格式 {dt!r}，按裸字节填写")]


# ---------------------------------------------------------------------------
# 数据域拼装
# ---------------------------------------------------------------------------

def _fv(fv: Dict, name: str, default: str = "") -> str:
    v = fv.get(name, None)
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    return str(v).strip()


def _encode_di_value(di_code: str, fv: Dict, value_key: str = "数据值") -> bytes:
    """按 DI 掩码把用户输入编成数据字节；掩码不适用时回退裸 hex 字段。

    value_key: 结构化值字段名——写数据命令为「写入数据」，应答为「数据值」。
    最大需量掩码（XX.XXXX,MDHM）不受此参数影响，固定读「需量值」+「发生时间」。
    """
    info = get_di_info(di_code)
    dt = (info["data_type"] or "").strip()
    label = info["name"] or di_code

    if dt == "XX.XXXX,MDHM":
        return encode_demand_with_time(_fv(fv, "需量值", "0"),
                                       _fv(fv, "发生时间", ""), label)
    up_dt = dt.upper()
    _is_addr = set(up_dt) == {"N"} and len(dt) >= 12
    if not _is_multivalue_dt(dt) and (
            _is_addr or "YYYYMMDD" in up_dt or "hhmmss" in dt.lower()):
        key = ("通信地址" if _is_addr
               else "日期" if "YYYYMMDD" in up_dt else "时间")
        return encode_value(_fv(fv, key), dt, info["unit"], label,
                            nbytes=info["length"] or None)
    total, _dec, nbytes = mask_shape(dt)
    if total:
        return encode_value(_fv(fv, value_key), dt, info["unit"], label,
                            nbytes=info["length"] or nbytes)
    # BS* / XX...XX / 未识别：裸 hex
    raw = _fv(fv, "数据内容") or _fv(fv, "数据值") or _fv(fv, "位串内容")
    return parse_hex(raw, info["length"] or None, label)


def _di_payload(fv: Dict) -> tuple:
    """取 DI 字段 → (线上 4 字节, DI 字符串)；未填抛中文 ValueError。"""
    di_code = _fv(fv, "数据标识 DI")
    if not di_code:
        raise ValueError("请先选择或输入数据标识 DI")
    return encode_di(di_code), di_code


#: 结构化值字段的候选名——GUI 用 DI 掩码推导字段时统一叫「数据值」，
#: 而 schema 的写数据命令叫「写入数据」，两者都要认
_VALUE_KEYS = ("写入数据", "数据值")
#: 掩码推导出的**专用**值字段名（`build_di_fields` 的产物）。
#: `_encode_di_value` 内部按 DI 的 data_type 自己去这些键取输入（日期/时间/通信地址/
#: 位串/裸字节/需量），因此它们也算「用户已填值」——否则 `写入数据` 为空时会被判成
#: 「写数据命令必须填写…」而拒绝组帧（日期/时间/位串类 DI 的 14H 帧曾因此无法组出）。
_DERIVED_VALUE_KEYS = ("日期", "时间", "通信地址", "位串内容", "数据内容")


def _value_or_raw(fv: Dict, di_code: str, raw_key: str) -> bytes:
    """优先用掩码编码的结构化值（候选字段名依次尝试）；为空时用裸 hex 兜底。"""
    for k in _VALUE_KEYS:
        if _fv(fv, k):
            return _encode_di_value(di_code, fv, k)
    if _fv(fv, "需量值"):
        return _encode_di_value(di_code, fv, _VALUE_KEYS[0])
    if any(_fv(fv, k) for k in _DERIVED_VALUE_KEYS):
        # 专用字段已填：交给 `_encode_di_value`（它按 data_type 去对应键取值）
        return _encode_di_value(di_code, fv, _VALUE_KEYS[0])
    raw = _fv(fv, raw_key)
    if raw:
        return parse_hex(raw, None, "数据")
    return b""


def _value_bytes(fv: Dict, di_code: str, raw_key: str) -> bytes:
    """DI 之后的数据字节：本手册扩展 DI 走专用编码，其余走掩码/裸 hex。

    无线 DI 的 ``data_type``（如 ``Z|C|T|DATA``）含 ``|``，会被
    :func:`_is_multivalue_dt` 判成多值块而落到裸 hex 分支；所以必须先分派。
    """
    wl = build_wireless_payload(di_code, fv)
    if wl is not None:
        return wl
    return _value_or_raw(fv, di_code, raw_key)


def build_data(cmd_key, fv: Dict) -> bytes:
    """按命令与字段值拼出**未加扰**的逻辑数据域（加扰由生成器统一负责）。"""
    direction, func = _norm_key(cmd_key)

    if direction == ERR:
        return parse_hex(_fv(fv, "错误信息字 ERR", "01"), 1, "错误信息字 ERR")

    if direction == RSP:
        if func in (0x11, 0x12):
            di_b, di_code = _di_payload(fv)
            return di_b + _value_bytes(fv, di_code, "数据值(裸hex)")
        if func == 0x06:
            # 主动上报（C=86H）：数据域 = DI + DATA，L=04H+m（手册 §4.1.2）
            di_b, di_code = _di_payload(fv)
            return di_b + _value_bytes(fv, di_code, "数据值(裸hex)")
        if func == 0x1E:
            # 在网状态确认应答（C=9EH）：L=00H（手册 §4.3.1）
            return b""
        if func == 0x13:
            return encode_addr(_fv(fv, "通信地址", "000000000000"), "通信地址")
        if func == 0x14:
            di_b, _ = _di_payload(fv)
            return di_b
        return b""                      # 95H 及其余正常应答：L=00H

    # ── 主站请求 ──
    if func in (0x11,):
        di_b, di_code = _di_payload(fv)
        if di_code == "FF00DD01":
            return di_b + _build_lme_query_payload(fv)
        extra = wireless_request_extra(di_code, fv)
        if extra:
            # 02EB0000 数据转发请求：数据域 = DI + Z + C + T + DATA（手册 §4.1.3）
            return di_b + extra
        return di_b
    if func == 0x06:
        # 上报确认应答（C=06H）：回带同一 DI + DATA（手册 §4.1.2）
        di_b, di_code = _di_payload(fv)
        return di_b + _value_bytes(fv, di_code, "数据值(裸hex)")
    if func == 0x1E:
        # 在网状态上报（C=1EH）：数据域 = 028100FF + 在网状态，L=05H（手册 §4.3.1）
        return encode_di("028100FF") + (build_wireless_payload("028100FF", fv) or b"")
    if func == 0x12:
        di_b, _ = _di_payload(fv)
        return di_b + parse_hex(_fv(fv, "附加数据"), None, "附加数据")
    if func == 0x13:
        return b""
    if func == 0x14:
        di_b, di_code = _di_payload(fv)
        payload = _value_or_raw(fv, di_code, "写入数据(裸hex)")
        if not payload:
            raise ValueError("写数据命令必须填写「写入数据」或「写入数据(裸hex)」")
        return pack_write_request(
            di_b, int(_fv(fv, "密码权限 PA", "00"), 16),
            _fv(fv, "密码 P0P1P2", "000000"),
            _fv(fv, "操作者代码 C0~C3", "00000000"), payload)
    if func == 0x15:
        return encode_addr(_fv(fv, "新通信地址"), "新通信地址")
    if func == 0x16:
        return _pack_mmddhhmm(_fv(fv, "冻结时间", "01-01-00-00"), "冻结时间")
    if func == 0x17:
        return parse_hex(_fv(fv, "速率特征字", "44"), 1, "速率特征字")
    if func == 0x08:
        return _pack_datetime(_fv(fv, "校时时间"), "校时时间")
    if func == 0x18:
        di_b, _ = _di_payload(fv)
        return pack_change_password(
            di_b,
            int(_fv(fv, "原密码权限 PA", "00"), 16), _fv(fv, "原密码 P0P1P2", "000000"),
            int(_fv(fv, "新密码权限 PA", "00"), 16), _fv(fv, "新密码 P0P1P2", "000000"))
    if func in (0x19, 0x1A):
        # L=08H：密码组(4) + 操作者代码(4)，**无 DI 前缀**
        return (pack_password(int(_fv(fv, "密码权限 PA", "00"), 16),
                              _fv(fv, "密码 P0P1P2", "000000"))
                + pack_operator(_fv(fv, "操作者代码 C0~C3", "00000000")))
    if func == 0x1B:
        # L=0CH：密码组(4) + 操作者代码(4) + 事件标识(4)
        return (pack_password(int(_fv(fv, "密码权限 PA", "00"), 16),
                              _fv(fv, "密码 P0P1P2", "000000"))
                + pack_operator(_fv(fv, "操作者代码 C0~C3", "00000000"))
                + parse_hex(_fv(fv, "事件标识", "FFFFFFFF"), 4, "事件标识"))
    raise ValueError(f"暂不支持的请求命令：func=0x{func:02X}")


def _build_lme_query_payload(fv: Dict) -> bytes:
    """FF00DD01 查询请求的条目部分：条目信息(0) + M + M×2B 请求头"""
    from lme_info_entry_parser import pack_lme_query_request
    return pack_lme_query_request(_fv(fv, "条目列表", ""))


def _pack_mmddhhmm(text: str, label: str) -> bytes:
    """MM-DD-hh-mm → 线上 4 字节，线序 mm hh DD MM（文档 §7.7 帧格式表）。"""
    s = (text or "").strip().replace("/", "-").replace(":", "-").replace(" ", "")
    parts = [p for p in s.split("-") if p != ""]
    if len(parts) != 4:
        raise ValueError(f"{label}格式应为 MM-DD-hh-mm（当前 {text!r}）")
    mm, dd, hh, mi = parts
    return bcd_pack(mm + dd + hh + mi, 4, label)


def _pack_datetime(text: str, label: str) -> bytes:
    """YYYY-MM-DD hh:mm:ss → 线上 6 字节，线序 ss mm hh DD MM YY（文档 §7.6）。

    留空时取当前电脑时间。注意**第 6 字节是年（YY），不是星期**。
    """
    s = (text or "").strip()
    if not s:
        from datetime import datetime
        now = datetime.now()
        yy, mm, dd = f"{now.year:04d}"[2:], f"{now.month:02d}", f"{now.day:02d}"
        hh, mi, ss = f"{now.hour:02d}", f"{now.minute:02d}", f"{now.second:02d}"
    else:
        date_part, _, time_part = s.replace("/", "-").replace("：", ":").partition(" ")
        d = [p for p in date_part.split("-") if p != ""]
        t = [p for p in time_part.split(":") if p != ""]
        if len(d) != 3 or len(t) != 3:
            raise ValueError(
                f"{label}格式应为 YYYY-MM-DD hh:mm:ss（当前 {text!r}）")
        yy = d[0][2:] if len(d[0]) == 4 else d[0]
        mm, dd = d[1], d[2]
        hh, mi, ss = t
    return bcd_pack(yy + mm + dd + hh + mi + ss, 6, label)


def length_warning(cmd_key, fv: Dict) -> str:
    """数据长度与 DI 声明 length 不符时返回中文警告文案（**不阻断**组帧）。

    依据决策：不校验 DI 可写性，长度不符仅提示。

    本手册（无线模组接口 V1.6）扩展 DI 用专用编码器计长；读请求（11H）里
    不带数据域的无线 DI 不校验 —— 否则表单里根本没有输入框，会平白报 0 字节。
    """
    spec = get_command(cmd_key)
    if not spec.get("has_di"):
        return ""
    di_code = _fv(fv, "数据标识 DI")
    if not di_code:
        return ""
    info = get_di_info(di_code)
    declared = info["length"]
    if not declared:
        return ""
    is_wl = build_wireless_fields(di_code) is not None
    try:
        if is_wl:
            direction, func = _norm_key(cmd_key)
            if direction == REQ and func in (0x11, 0x12) and di_code not in REQ_WITH_PAYLOAD_DI:
                return ""
            wl_payload = build_wireless_payload(di_code, fv)
            actual = len(wl_payload if wl_payload is not None else b"")
        else:
            value_key = next((k for k in _VALUE_KEYS if _fv(fv, k)), "数据值")
            actual = len(_encode_di_value(di_code, fv, value_key))
    except Exception:
        return ""
    if actual != declared:
        return (f"提示：{info['name'] or di_code} 声明数据长度 {declared} 字节，"
                f"当前填写 {actual} 字节（仍可生成，请自行确认）")
    return ""
