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


# ======================================================================
# 编码方向（组帧用）—— 每个函数与上方 decode_*/split_* 互为逆运算，
# 新增/修改任一侧时必须同步另一侧并跑 test_dlt645_frame_gen.py 的往返断言。
# ======================================================================

_HEX_DIGITS = set("0123456789abcdefABCDEF")


def parse_hex(text: str, expect_len: Optional[int] = None,
              label: str = "数据") -> bytes:
    """hex 字符串 → 字节；容忍空格与 0x 前缀。非法输入抛中文 ValueError。"""
    s = (text or "").replace(" ", "").replace("\t", "")
    if s.lower().startswith("0x"):
        s = s[2:]
    if not s:
        return b""
    if not set(s) <= _HEX_DIGITS:
        raise ValueError(f"{label}含非法十六进制字符：{text!r}")
    if len(s) % 2:
        raise ValueError(
            f"{label}十六进制字符数必须为偶数（当前 {len(s)} 个）")
    b = bytes.fromhex(s)
    if expect_len is not None and len(b) != expect_len:
        raise ValueError(
            f"{label}应为 {expect_len} 字节，当前 {len(b)} 字节")
    return b


def _digits_of(text: str, label: str, decimals: int) -> str:
    """十进制字符串（可含一个小数点）→ 纯数字串，并校验小数位不超掩码"""
    s = (text or "").strip().replace(" ", "")
    if not s:
        return ""
    if not set(s) <= set("0123456789."):
        raise ValueError(f"{label}只能包含数字与一个小数点（当前 {text!r}）")
    if s.count(".") > 1:
        raise ValueError(f"{label}最多只能有一个小数点（当前 {text!r}）")
    if "." in s and len(s.split(".")[1]) > decimals:
        raise ValueError(
            f"{label}小数位数超出格式允许的 {decimals} 位（当前 {text!r}）")
    return s.replace(".", "")


def bcd_pack(digits: str, nbytes: int, label: str = "数据") -> bytes:
    """数字串 → nbytes 字节 BCD，**低字节在前**（DLT645 线序）。

    入参约定：digits 一律按**逻辑高位在前**传入，本函数负责转成线上低字节在前。
    数值类：bcd_pack("12345678", 4) == b"\\x78\\x56\\x34\\x12"（即 123456.78）
    日期类：bcd_pack("260904", 3) == b"\\x04\\x09\\x26"（YYMMDD → 线上 日 月 年）
    与 _bcd_digits 互为逆运算。
    """
    digits = (digits or "").lstrip("0") or "0"
    if len(digits) > nbytes * 2:
        raise ValueError(
            f"{label}超出 {nbytes} 字节 BCD 容量（最多 {nbytes * 2} 位，"
            f"当前 {len(digits)} 位）")
    digits = digits.rjust(nbytes * 2, "0")
    hi_lo = bytes(int(digits[i:i + 2], 16) for i in range(0, len(digits), 2))
    return hi_lo[::-1]


def mask_shape(data_type: str) -> Tuple[int, int, int]:
    """掩码 → (总位数, 小数位数, 字节数)；非 BCD 掩码返回 (0, 0, 0)。

    例：'XXXXXX.XX' → (8, 2, 4)；'XX.XXXX,MDHM' 只取逗号前的数值部分。
    """
    base = (data_type or "").split(",")[0].strip()
    if not base or "..." in base or not set(base) <= set("Xx."):
        return (0, 0, 0)
    decimals = (len(base) - base.index(".") - 1) if "." in base else 0
    total = len(base.replace(".", ""))
    return (total, decimals, (total + 1) // 2)


def encode_value(value: str, data_type: str, unit: str = "",
                 di_name: str = "", nbytes: Optional[int] = None) -> bytes:
    """按 data_type 掩码把用户输入编成**未加扰**的数据字节（低字节在前）。

    与 decode_value 互为逆运算（decode_value(encode_value(v, dt), dt) 应还原 v）。
    nbytes 用于覆盖掩码推导的字节数（如 DI 表声明长度与掩码不一致时）。
    """
    dt = (data_type or "").strip()
    up = dt.upper()

    # 无数据域（如曲线数据块读请求）
    if not dt:
        return parse_hex(value, nbytes, di_name or "数据")

    # 位串 BS32/BS64/BS96：按裸 hex 填写，长度固定
    if up.startswith("BS"):
        want = nbytes if nbytes is not None else int(up[2:] or 0) // 8
        return parse_hex(value, want or None, di_name or "位串")

    # 变长裸字节（LME 自定义 DI 等，掩码形如 XX...XX）
    # 注意：必须用「三连点」判定，不能用 set(dt) <= set("Xx.")——
    # 后者会把带小数点的 BCD 掩码（如 XXXXXX.XX）误归为裸字节。
    if "..." in dt:
        return parse_hex(value, nbytes, di_name or "数据")

    # 通信地址 NNNNNNNNNNNN：12 位地址 → 6 字节，低字节在前
    if set(up) == {"N"}:
        s = (value or "").strip().replace(" ", "")
        if not s:
            return b""
        want = nbytes if nbytes is not None else (len(s) + 1) // 2
        if set(s) <= _HEX_DIGITS and len(s) % 2 == 0:
            return parse_hex(s, want, di_name or "通信地址")[::-1]
        return bcd_pack(_digits_of(s, di_name or "通信地址", 0), want,
                        di_name or "通信地址")

    # 日期 YYYYMMDD：线序 日 月 年（与 decode_value 的 data[0]=日 一致）
    if "YYYYMMDD" in up:
        s = (value or "").strip().replace("/", "-").replace(".", "-")
        parts = s.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            yy, mm, dd = parts[0][2:], parts[1], parts[2]
        elif len(parts) == 3:
            yy, mm, dd = parts[2], parts[1], parts[0]
        else:
            raise ValueError(f"{di_name or '日期'}格式应为 YYYY-MM-DD（当前 {value!r}）")
        return bcd_pack(yy + mm + dd, 3, di_name or "日期")

    # 时间 hhmmss：线序 秒 分 时
    if "hhmmss" in dt.lower():
        s = (value or "").strip().replace("：", ":")
        parts = s.split(":")
        if len(parts) != 3:
            raise ValueError(f"{di_name or '时间'}格式应为 hh:mm:ss（当前 {value!r}）")
        hh, mm, ss = parts
        return bcd_pack(hh + mm + ss, 3, di_name or "时间")

    # BCD 数值：XXXXXX.XX / XXX.X / XXXXXX / XX.XXXX,MDHM 的数值部分
    total, decimals, want = mask_shape(dt)
    if total:
        digits = _digits_of(value, di_name or "数据值", decimals)
        return bcd_pack(digits, nbytes if nbytes is not None else want,
                        di_name or "数据值")

    # 未识别掩码：回退裸 hex（UI 会标注「未识别格式，按裸字节填写」）
    return parse_hex(value, nbytes, di_name or "数据")


def encode_demand_with_time(demand: str, when: str,
                            di_name: str = "最大需量") -> bytes:
    """最大需量及发生时间（掩码 XX.XXXX,MDHM）：需量 XX.XXXX(3B) + MMDDhhmm(4B)。

    线序依据 DL/T645-2007 §7.7 冻结命令的 MMDDhhmm（mm hh DD MM）同款倒序。
    dlt645_di.json 对该掩码声明 length=8，与文档推导的 7 字节不符（疑为手写表笔误），
    此处以掩码/文档为准，长度不符由调用方给 WARN 而不阻断。
    """
    val = bcd_pack(_digits_of(demand, di_name + "需量", 4), 3, di_name + "需量")
    s = (when or "").strip().replace("/", "-").replace(".", "-").replace("：", ":")
    if not s:
        return val
    parts = [p for p in s.replace("-", ":").split(":") if p != ""]
    if len(parts) != 4:
        raise ValueError(
            f"{di_name}发生时间格式应为 MM-DD-hh-mm（当前 {when!r}）")
    mm, dd, hh, mi = parts
    stamp = bcd_pack(mm + dd + hh + mi, 4, di_name + "发生时间")
    return val + stamp


def pack_password(pa: int, pwd: str, label: str = "密码") -> bytes:
    """密码组：PA(1) + P0P1P2(3)，共 4 字节。与 split_* 中的密码组解析互逆。"""
    if not 0 <= int(pa) <= 0xFF:
        raise ValueError(f"{label}权限 PA 应在 00~FF（当前 {pa!r}）")
    p = parse_hex(pwd, 3, label + " P0P1P2") if (pwd or "").strip() else b"\x00" * 3
    return bytes([int(pa)]) + p


def pack_operator(code: str, label: str = "操作者代码") -> bytes:
    """操作者代码 C0~C3（4 字节）；留空填 00000000。"""
    if not (code or "").strip():
        return b"\x00" * 4
    return parse_hex(code, 4, label)


def pack_write_request(di: bytes, pa: int, pwd: str, operator: str,
                       payload: bytes) -> bytes:
    """写数据 14H 数据域：DI(4) + PA P0P1P2(4) + C0~C3(4) + 数据(m)。

    与 split_write_request 互为逆运算。
    """
    if len(di) != 4:
        raise ValueError(f"数据标识应为 4 字节（当前 {len(di)} 字节）")
    return di + pack_password(pa, pwd) + pack_operator(operator) + payload


def pack_change_password(di: bytes, old_pa: int, old_pwd: str,
                         new_pa: int, new_pwd: str) -> bytes:
    """修改密码 18H 数据域：DI(4) + 原密码组(4) + 新密码组(4)。

    与 split_change_password 互为逆运算。
    """
    if len(di) != 4:
        raise ValueError(f"数据标识应为 4 字节（当前 {len(di)} 字节）")
    return (di + pack_password(old_pa, old_pwd, "原密码")
            + pack_password(new_pa, new_pwd, "新密码"))


def pack_clear_command(pa: int, pwd: str, operator: str, di: bytes) -> bytes:
    """清零类 1AH/1BH 数据域：PA P0P1P2(4) + C0~C3(4) + 操作对象标识(4)。

    **无 DI 前缀**（与写数据帧不同）；di 传 FFFFFFFF 表示全部对象。
    与 split_clear_command 互为逆运算。
    """
    if len(di) != 4:
        raise ValueError(f"操作对象标识应为 4 字节（当前 {len(di)} 字节）")
    return pack_password(pa, pwd) + pack_operator(operator) + di
