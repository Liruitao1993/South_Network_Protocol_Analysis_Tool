# -*- coding: utf-8 -*-
"""DL/T645-2007 标准数据域编解码

- BCD 数值解码：按 DI 映射表的 data_type（如 XXXXXX.XX）解析小数点与单位
- 日期 YYYYMMDD（线序 DD MM YY）、时间 hhmmss（线序 ss mm hh）
- 状态字 BS32/BS96：位串展开
- 错误信息字 ERR：标准错误码表
- 写数据帧结构拆分：密码(PA权限+P0P1P2)、操作者代码(C0~C3)

约定：输入数据均为减 0x33 后的真实字节，低字节在前（DLT645 BCD 低字节传输在前）。
"""

from typing import List, Tuple, Optional

# 错误信息字 ERR（DL/T645-2007 附录C）—— 位域字节，某位=1 表示对应错误发生
ERR_BITS = {
    0: "其他错误",
    1: "无请求数据",
    2: "密码错/未授权",
    3: "通信速率不能更改",
    4: "日时段数超",
    5: "费率数超",
    6: "年时区数超",
    # bit7 保留
}

# 电表运行状态字 1~7（DL/T645-2007 附录C，DI 04000501~04000507，BS32）
# 每个为 {bit位: 含义}；bit0 为最低位，状态字取前 2 字节（bit0~15）
STATUS_WORD_BITS = {
    1: {
        7: "无功功率方向(0正1反)", 6: "有功功率方向(0正1反)",
        5: "停电抄表电池(0正常1欠压)", 4: "时钟电池(0正常1欠压)",
        3: "需量积算方式(0滑差1区间)",
    },
    2: {
        7: "C相无功方向(0正1反)", 6: "B相无功方向(0正1反)", 5: "A相无功方向(0正1反)",
        4: "C相有功方向(0正1反)", 3: "B相有功方向(0正1反)", 2: "A相有功方向(0正1反)",
    },
    3: {
        7: "继电器状态(0通1断)", 6: "编程允许(0禁止1许可)",
        5: "供电方式(配合bit4)", 4: "当前运行时段(0第一套1第二套)",
    },
    4: {  # A相故障
        7: "断相", 6: "过载", 5: "过流", 4: "失流", 3: "过压",
        2: "欠压", 1: "潮流方向异常", 0: "失压", 8: "断流",
    },
    5: {  # B相故障，位定义同 A 相
        7: "断相", 6: "过载", 5: "过流", 4: "失流", 3: "过压",
        2: "欠压", 1: "潮流方向异常", 0: "失压", 8: "断流",
    },
    6: {  # C相故障，位定义同 A 相
        7: "断相", 6: "过载", 5: "过流", 4: "失流", 3: "过压",
        2: "欠压", 1: "潮流方向异常", 0: "失压", 8: "断流",
    },
    7: {  # 合相故障
        6: "需量超限", 5: "掉电", 4: "电压不平衡", 3: "辅助电源失电",
        2: "电流不平衡", 1: "电流逆相序", 0: "电压逆相序",
    },
}

# 状态字 N 对应的相位标签（4=A相 5=B相 6=C相，故障类）
STATUS_WORD_PHASE = {4: "A相", 5: "B相", 6: "C相"}

STATUS_WORD_NAME_RE = {
    "状态字1": 1, "状态字2": 2, "状态字3": 3,
    "状态字4": 4, "状态字5": 5, "状态字6": 6, "状态字7": 7,
}


def decode_status_word(name: str, data: bytes) -> Optional[str]:
    """按附录C位定义展开电表运行状态字；不匹配返回 None"""
    word_no = None
    for key, no in STATUS_WORD_NAME_RE.items():
        if key in name:
            word_no = no
            break
    if word_no is None or not data:
        return None
    bits = int.from_bytes(data[:2], "little")
    table = STATUS_WORD_BITS[word_no]
    phase = STATUS_WORD_PHASE.get(word_no, "")
    set_flags, clear_flags = [], []
    for bit, meaning in table.items():
        label = (phase + meaning) if phase and word_no in (4, 5, 6) else meaning
        (set_flags if bits & (1 << bit) else clear_flags).append(label)
    parts = [f"bit位值={bits & 0xFFFF:016b}"]
    parts.append("置位: " + ("；".join(set_flags) if set_flags else "无"))
    # 故障类状态字：0=无故障，仅列置位项即可，省略未置位长列表
    if word_no not in (4, 5, 6):
        parts.append("未置位: " + "；".join(clear_flags))
    elif not set_flags:
        parts.append("无故障")
    return " | ".join(parts)


# 功能码标签（D4~D0）
FUNC_NAMES = {
    0x11: "读数据",
    0x12: "读后续数据",
    0x13: "读通信地址",
    0x14: "写数据",
    0x15: "写通信地址",
    0x16: "冻结命令",
    0x17: "更改通信速率",
    0x08: "广播校时",
    0x18: "修改密码",
    0x19: "最大需量清零",
    0x1A: "电表清零",
    0x1B: "事件清零",
}


def _bcd_digits(b: bytes) -> Optional[str]:
    """字节组 → BCD 数字串；含非BCD nibble 返回 None。

    DL/T645 多字节 BCD 低字节在前（线上 78 56 34 12 表示 123456.78），
    故先反转字节序再拼数字。
    """
    digits = ""
    for x in reversed(b):
        hi, lo = x >> 4, x & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits += f"{hi}{lo}"
    return digits


def decode_value(data: bytes, data_type: str, unit: str = "",
                 di_name: str = "") -> Optional[str]:
    """按 data_type 解码标准 DI 数据体（不含 DI 本身的 4 字节）

    返回可读字符串；无法按类型解码时返回 None（调用方回退裸 hex）。
    di_name 用于 BS 状态字按附录C位定义展开。
    """
    if not data or not data_type:
        return None

    dt = data_type.strip()

    # 状态字/位串：BS32、BS96 等
    if dt.upper().startswith("BS"):
        # 电表运行状态字 1~7：按附录C位定义展开
        if di_name and "状态字" in di_name:
            sw = decode_status_word(di_name, data)
            if sw:
                return sw
        bits = "".join(f"{b:08b}" for b in data)
        n = len(data) * 8
        return (f"二进制({n}位)：{bits}；状态字位定义见DL/T645-2007附录C"
                f"{'；原始hex=' + data.hex().upper() if len(data) > 12 else ''}")

    # 日期：YYYYMMDD，线序 DD MM YY
    if "YYYYMMDD" in dt.upper():
        d = _bcd_digits(data)
        if d and len(data) >= 3:
            # 低字节在前：data[0]=日 data[1]=月 data[2]=年
            yy, mm, dd = data[2] & 0xFF, data[1] & 0xFF, data[0] & 0xFF
            if all(0x00 <= v <= 0x99 for v in (yy, mm, dd)):
                return f"20{yy:02X}-{mm:02X}-{dd:02X}"
        return None

    # 时间：hhmmss，线序 ss mm hh
    if "hhmmss" in dt.lower():
        if len(data) >= 3 and all((x >> 4) <= 9 and (x & 0x0F) <= 9 for x in data[:3]):
            ss, mm, hh = data[0], data[1], data[2]
            return f"{hh:02X}:{mm:02X}:{ss:02X}"
        return None

    # BCD 数值：形如 XXXXXX.XX / XXX.X / XXXXXX（可能带 ,MDHM 等后缀）
    base = dt.split(",")[0].strip()
    if set(base) <= set("Xx.") and ("X" in base or "x" in base):
        if "." in base:
            decimals = len(base) - base.index(".") - 1
        else:
            decimals = 0
        digits = _bcd_digits(data)
        if digits is None:
            return None
        digits = digits.lstrip("0") or "0"
        if decimals > 0:
            if len(digits) <= decimals:
                digits = digits.zfill(decimals + 1)
            value = digits[:-decimals] + "." + digits[-decimals:]
        else:
            value = digits
        # 去掉多余前导零（保留小数点前一位）
        if "." in value:
            int_part, frac_part = value.split(".")
            int_part = int_part.lstrip("0") or "0"
            value = f"{int_part}.{frac_part}"
        unit_text = f" {unit}" if unit else ""
        suffix = f"（{dt.split(',', 1)[1]}）" if "," in dt else ""
        return f"{value}{unit_text}{suffix}"

    return None


def decode_err(b: bytes) -> Optional[str]:
    """异常应答错误信息字 ERR（1 字节位域，附录C）：某位=1 表示对应错误发生"""
    if len(b) != 1:
        return None
    code = b[0]
    if code == 0:
        return "无错误（ERR=0）"
    errs = [meaning for bit, meaning in ERR_BITS.items() if code & (1 << bit)]
    if not errs:
        return f"未知错误（ERR=0x{code:02X}）"
    return "；".join(errs) + f"（ERR=0x{code:02X}）"


def split_write_request(data: bytes) -> List[Tuple[str, str, str, str]]:
    """写数据请求帧（FUNC=14H，主站）数据域拆分

    结构：DI(4) + 密码PA P0 P1 P2(4) + 操作者代码C0~C3(4) + 数据(m)
    返回 (字段, 原始hex, 解析值, 说明) 行列表。
    """
    rows: List[Tuple[str, str, str, str]] = []
    if len(data) < 12:
        return rows
    pa, p0, p1, p2 = data[4], data[5], data[6], data[7]
    c = data[8:12]
    payload = data[12:]
    rows.append(("  └ 密码权限 PA", f"{pa:02X}",
                 f"权限级别 {pa:02X}（00最高，02=清零级，04=写数据级）",
                 "密码PA，00~09，数值越大权限越低"))
    rows.append(("  └ 密码 P0P1P2",
                 bytes([p0, p1, p2]).hex().upper(),
                 "".join(f"{b:02X}" for b in (p0, p1, p2)),
                 "3字节密码（BCD字符）"))
    rows.append(("  └ 操作者代码 C0~C3",
                 c.hex().upper(),
                 "".join(f"{b:02X}" for b in c),
                 "操作者代码，记录操作人员信息"))
    if payload:
        rows.append(("  └ 写入数据", payload.hex().upper(), payload.hex().upper(),
                     f"待写入数据，{len(payload)}字节（按对应DI格式解读）"))
    return rows


def split_change_password(data: bytes) -> List[Tuple[str, str, str, str]]:
    """修改密码请求帧（FUNC=18H，主站）：DI(4)+旧密码组(4)+新密码组(4)"""
    rows: List[Tuple[str, str, str, str]] = []
    if len(data) < 12:
        return rows

    def pwd_group(off: int, label: str):
        pa, p0, p1, p2 = data[off], data[off + 1], data[off + 2], data[off + 3]
        return [
            (f"  └ {label} 权限 PA", f"{pa:02X}", f"权限级别 {pa:02X}", "密码权限，00最高"),
            (f"  └ {label} 密码 P0P1P2",
             bytes([p0, p1, p2]).hex().upper(),
             "".join(f"{b:02X}" for b in (p0, p1, p2)),
             "3字节密码"),
        ]

    rows.extend(pwd_group(4, "原密码"))
    rows.extend(pwd_group(8, "新密码"))
    return rows


def split_clear_command(data: bytes) -> List[Tuple[str, str, str, str]]:
    """清零类命令请求帧（FUNC=1AH电表清零/1BH事件清零，主站）

    结构（无DI前缀）：密码PA P0 P1 P2(4) + 操作者代码C0~C3(4) + 数据标识(4，全FF=全部)
    """
    rows: List[Tuple[str, str, str, str]] = []
    if len(data) < 8:
        return rows
    pa, p0, p1, p2 = data[0], data[1], data[2], data[3]
    rows.append(("  └ 密码权限 PA", f"{pa:02X}", f"权限级别 {pa:02X}", "密码权限，00最高"))
    rows.append(("  └ 密码 P0P1P2",
                 bytes([p0, p1, p2]).hex().upper(),
                 "".join(f"{b:02X}" for b in (p0, p1, p2)),
                 "3字节密码"))
    if len(data) >= 12:
        c = data[4:8]
        rows.append(("  └ 操作者代码 C0~C3", c.hex().upper(),
                     "".join(f"{b:02X}" for b in c), "操作者代码"))
    if len(data) >= 12:
        di = data[8:12]
        all_flag = di == b"\xFF\xFF\xFF\xFF"
        rows.append(("  └ 操作对象标识", di.hex().upper(),
                     "全部对象（FFFFFFFF）" if all_flag else di.hex().upper(),
                     "事件清零时DI0用FF表示分项/全部"))
    return rows
