# -*- coding: utf-8 -*-
"""虚拟表动态数据：当前时间、通信地址、电能量递增、冻结时标、漏点判定。"""
from datetime import datetime
from typing import Optional, Tuple


def date_time_s(dt: Optional[datetime] = None) -> bytes:
    """date_time_s（tag 0x1C，7 字节：年 2B 大端 BCD 风格十六进制 + 月日时分秒）。"""
    dt = dt or datetime.now()
    return bytes([0x1C, (dt.year >> 8) & 0xFF, dt.year & 0xFF,
                  dt.month, dt.day, dt.hour, dt.minute, dt.second])


def current_time_data() -> bytes:
    """OI 4000 属性 02（日期时间）实时值。"""
    return date_time_s()


def meter_number_from_archive(addr_item_data: str) -> int:
    """从档案 40020200/202a0200 数据（'550705' + 12 位 BCD 串）提取表号整数。"""
    digits = addr_item_data[6:6 + 12]
    try:
        return int(digits)
    except ValueError:
        return 0


def comm_address_data(meter_no: int) -> bytes:
    """4001/4002/202a 通信地址：55 07 05 + 6 字节 BCD 表号（帧顺序，同档案）。"""
    digits = str(meter_no).zfill(12)
    bcd = bytes.fromhex(digits)
    return bytes([0x55, 0x07, 0x05]) + bcd


#: 组地址默认 000000000000（用户口径：虚拟表可把组地址设成全 0）
GROUP_ADDRESS = "000000000000"


def group_address_data(addr: str = GROUP_ADDRESS) -> bytes:
    """OI 4005 属性 02「组地址」——协议定义是 **array octet-string**。

    A-XDR 编码 = `01`(array) + 元素个数 + 每个元素 `09`(octet-string) + 长度 + 数据。
    默认返回 1 个元素、6 字节 BCD 的 ``000000000000``：
    ``01 01 09 06 00 00 00 00 00 00``。

    被测 CCO 读组地址（OAD 40050200）时，虚拟表必须能正常应答——不然会回
    「对象不存在」，CCO 侧拿不到组地址。
    """
    from dl_t698_45_axdr import AXDRCoder

    text = "".join(ch for ch in str(addr or "") if ch.isdigit()).rjust(12, "0")[:12]
    bcd = bytes.fromhex(text)
    return AXDRCoder().encode([{"tag": 0x09, "value": bcd}], 0x01)


def normalize_address(text) -> str:
    """把用户输入的虚拟表地址规范成 12 位十进制数字串（BCD）。

    非法（含非数字字符、超 12 位）返回空串；不足 12 位左补 0。
    """
    raw = "".join(str(text or "").split()).upper()
    if not raw:
        return ""
    if not raw.isdigit() or len(raw) > 12:
        return ""
    return raw.zfill(12)


def address_sa(addr_str: str) -> bytes:
    """本机地址 → 响应 SA：特征字节 0x05（单地址，长度 6）+ 反转 BCD 表号。"""
    digits = normalize_address(addr_str) or "000000000000"
    bcd = list(bytes.fromhex(digits))
    bcd.reverse()
    return bytes([0x05]) + bytes(bcd)


def wildcard_sa_bytes(meter_no: int) -> bytes:
    """通配响应 SA：特征字节 0x05（单地址，长度6）+ 反转 BCD 表号（对齐开源）。"""
    return address_sa(str(meter_no).zfill(12))


def sa_body_reversed_hex(sa: bytes) -> str:
    """黑白名单比对用：SA 地址体（去特征字节）按字节反转后的 hex 串。"""
    body = list(sa[1:])
    body.reverse()
    return bytes(body).hex()


def increase_energy(base_hex: str, elapsed_sec: int) -> str:
    """正向有功电能（00100200，array 5 个 double-long-unsigned）随运行时间递增。

    规则对齐开源：总费率 A += 秒数*2+10；B/C/D/E += 秒数+4/3/2/1。
    """
    b = bytes.fromhex(base_hex)
    # 01 05 + 5×(06 + 4字节值)
    vals = [int.from_bytes(b[3 + i * 5:3 + i * 5 + 4], "big") for i in range(5)]
    deltas = [elapsed_sec * 2 + 10, elapsed_sec + 4, elapsed_sec + 3,
              elapsed_sec + 2, elapsed_sec + 1]
    out = bytes([0x01, 0x05])
    for v, d in zip(vals, deltas):
        out += bytes([0x06]) + (v + d).to_bytes(4, "big")
    return out.hex()


def leak_in_window(window: Optional[Tuple[int, int]],
                   dt: Optional[datetime] = None) -> bool:
    """曲线漏点时段判定：window=(起分钟, 止分钟)，当前时间在区间内返回 True。"""
    if not window:
        return False
    dt = dt or datetime.now()
    cur = dt.hour * 60 + dt.minute
    start, end = window
    if start <= end:
        return start < cur < end
    # 跨零点区间
    return cur > start or cur < end
