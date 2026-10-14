# -*- coding: utf-8 -*-
"""南网上行通信规约（协议14）—— **网络管理（深化应用）扩展**（文档第 4 章）。

数据来源：``协议文档/14.南网上行通信规约/新一代计量自动化主站通信网络管理技术要求.docx``
（同目录 ``.md`` 为 markitdown 转换版；第 4 章「终端上行规约（针对网络管理扩展）」）。

由文档中的**实帧**（send/rec 成对、CS 全部自洽）确认的两条线格式事实：

1. 长度域 **4 字节**：``68H | L(2B 小端) | L(同值) | 68H | …``（例 ``68 10 00 10 00 68``）——
   与 1.23.69 的长度域修正一致；
2. **数据标识 DI 线上低字节在前**：表 ``E1 00 60 12`` → 线上 ``12 60 00 E1``
   （与协议0/645 同族约定一致；见 ``csg_uplink_di.to_semantic_di``）。

另注意 4.14（``E1 00 60 16`` 远程通信模块网管信息）文档备注：**报文字段高位在前、低位在后**，
故其多字节数值字段按**大端**解析（与全局「低字节在前」相反）。

本模块是网管扩展 DI / 枚举 / 结构化解码的**唯一事实来源**，由 ``csg_uplink_di`` 合并进 DI 索引
（禁止在解析器/查询页再写一份，见 AGENTS.md 陷阱 48/55/61）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

__all__ = [
    "NM_APPX",
    "NM_APPX_NAME",
    "NM_DIS",
    "NM_PREFIX_RULES",
    "ENUMS",
    "TOPO_UNIT",
    "CHANNEL_UNIT",
    "is_nm_di",
    "resolve_prefix",
    "content_length",
    "subrows",
    "decode",
]

#: 附录/归属标识（查询页「归属表」列显示 ``N``，前端另有中文名）
NM_APPX = "N"
NM_APPX_NAME = "网管扩展（深化应用第4章）"

#: 网管扩展 DI 清单（字段与 ``csg_uplink_di_data.DI_ENTRIES`` 同形）
NM_DIS: List[dict] = [
    {"di": "E08004FF", "name": "电能表通信模块信息（通信模块信息数据项集合，DI0=通信模块序号）",
     "fmt": "65 字节集合", "nbytes": "65", "unit": "", "read": True, "write": False,
     "group": "4.1 · AFN=0A"},
    {"di": "E1006012", "name": "入网从节点信息（节点在线状态：从节点地址列表）",
     "fmt": "NNNN, NN, NNNNNNNNNNNN…", "nbytes": "", "unit": "", "read": True, "write": False,
     "group": "4.2 · AFN=0C"},
    {"di": "E1800052", "name": "台区组网成功率（BCD，保留两位小数，模块上报扩大 100 倍）",
     "fmt": "NNNN.NN", "nbytes": "3", "unit": "%", "read": True, "write": False,
     "group": "4.3 · AFN=0C"},
    {"di": "E1006009", "name": "周边节点信道信息（节点与代理节点上下行通信成功率）",
     "fmt": "NNNN, NN, 16 字节×n", "nbytes": "", "unit": "", "read": True, "write": False,
     "group": "4.4 · AFN=0C"},
    {"di": "E1006004", "name": "网络拓扑信息（节点地址 + 13 字节拓扑数据单元）",
     "fmt": "NNNN, NNNN, NN, 19 字节×n", "nbytes": "", "unit": "", "read": True, "write": False,
     "group": "4.5 · AFN=0C"},
    {"di": "E1006014", "name": "网络拓扑信息（4.5 **示例实帧**使用的 DI0；表列 DI0=04，两值并存待确认）",
     "fmt": "NNNN, NNNN, NN, 19 字节×n", "nbytes": "", "unit": "", "read": True, "write": False,
     "group": "4.5 · AFN=0C（示例）"},
    {"di": "E1006015", "name": "模块类型 + 节点离线时长",
     "fmt": "NN, NN…NN", "nbytes": "5", "unit": "s", "read": True, "write": False,
     "group": "4.6 · AFN=0C"},
    {"di": "E2000033", "name": "设备掉电（模块停电告警）",
     "fmt": "", "nbytes": "", "unit": "", "read": True, "write": False, "group": "4.7 · AFN=13"},
    {"di": "E2000034", "name": "设备上电（模块上电告警）",
     "fmt": "", "nbytes": "", "unit": "", "read": True, "write": False, "group": "4.7 · AFN=13"},
    {"di": "E1006005", "name": "多网络信息（本网络及邻居网络 SNID、本网络主节点地址）",
     "fmt": "NN, NN, NNNNNNNNNNNN, NN…", "nbytes": "", "unit": "", "read": True, "write": False,
     "group": "4.8 · AFN=0C"},
    {"di": "E0000040", "name": "宽带载波频段（0：1.953~11.96MHz；1：2.441~5.615MHz；2：0.781~2.930MHz）",
     "fmt": "NN", "nbytes": "1", "unit": "", "read": True, "write": True,
     "group": "4.9 · AFN=04"},
    {"di": "E1006008", "name": "从节点入网被拒信息（被拒节点地址列表）",
     "fmt": "NNNN, NN, NNNNNNNNNNNN…", "nbytes": "", "unit": "", "read": True, "write": False,
     "group": "4.10 · AFN=0C"},
    {"di": "E1006010", "name": "节点自检信息（过零自检 / 串口485 / 上次离网原因 / 复位原因）",
     "fmt": "NN, NN, NN, NN", "nbytes": "4", "unit": "", "read": True, "write": False,
     "group": "4.11 · AFN=0C"},
    {"di": "E0000041", "name": "从节点重启（NN：0=重启，其他保留）",
     "fmt": "NN", "nbytes": "1", "unit": "", "read": False, "write": True,
     "group": "4.12 · AFN=04"},
    {"di": "E1006013", "name": "并发数",
     "fmt": "NN", "nbytes": "1", "unit": "", "read": True, "write": False,
     "group": "4.13 · AFN=0C"},
    {"di": "E1006016", "name": "远程通信模块网络通信管理信息（21 项，报文字段高位在前）",
     "fmt": "8,15,32,1,15,64,4,64,64,4,4,4,4,1,2,2,1,4,64,64,64",
     "nbytes": "", "unit": "", "read": True, "write": False, "group": "4.14 · AFN=0C"},
]
for _e in NM_DIS:
    _e["appx"] = NM_APPX

#: DI 前缀规则：表中末字节以 ``FF``/``NN`` 占位（表示序号）的 DI，按**前 3 字节**匹配
NM_PREFIX_RULES: Dict[str, str] = {
    "E08004": "E08004FF",   # 4.1 DI0 = 通信模块序号（示例实帧用 02）
}

# ── 枚举（第 4 章各表）─────────────────────────────────────────────────

ENUMS: Dict[str, Dict[int, str]] = {
    # 4.6 模块类型（表 17）
    "模块类型": {
        0x1: "抄控器", 0x2: "集中器通信模块", 0x3: "单相电表通信模块", 0x4: "中继器",
        0x5: "II 型采集器", 0x6: "I 型采集器", 0x7: "三相表通信模块",
    },
    # 4.9 宽带载波频段
    "宽带载波频段": {
        0: "1.953～11.96MHz", 1: "2.441～5.615MHz", 2: "0.781～2.930MHz",
    },
    # 4.14 模组当前制式
    "模组当前制式": {
        0x01: "EDGE（移动/联通 2G）", 0x02: "CDMA（电信 2G）", 0x03: "WCDMA（联通 3G）",
        0x04: "TD-SCDMA（移动 3G）", 0x05: "CDMA2000（电信 3G）", 0x06: "FDD-LTE（联通/电信 4G）",
        0x07: "TDD-LTE（移动 4G）", 0x08: "LTE-1.8GHz（4G 专网）", 0x09: "LTE-230MHz（4G 专网）",
        0x10: "HSPA+（H+ 3.75G）",
    },
    # 4.14 运营商名称
    "运营商名称": {0x01: "中国移动", 0x02: "中国联通", 0x03: "中国电信", 0x04: "其它"},
    # 4.14 上一次掉线原因
    "上一次掉线原因": {
        0x01: "SIM 卡读取错误", 0x02: "掉电", 0x03: "无法附着网络", 0x04: "无法联网",
        0x05: "通信模块异常", 0x06: "信号强度低",
    },
    # 4.11 过零自检结果（注释 1：与节点类型相关）
    "过零自检结果(主节点/三相表模块)": {
        0: "未知", 1: "三相相序为 ABC", 2: "三相相序错误", 3: "存在断相", 4: "存在相同相位",
    },
    "过零自检结果(单相表模块)": {0: "不支持过零", 1: "支持过零"},
    # 4.11 串口/485 不通状态（注释 2）
    "串口485不通状态": {0: "正常", 1: "历史上出现过不通现象", 2: "目前不通"},
    # 4.11 上次离网原因（注释 3）
    "上次离网原因": {
        0: "未离网", 1: "组网序列号变化", 2: "2 个路由周期收不到信标帧",
        3: "与代理节点连续四个路由周期的通信成功率都是 0", 4: "站点所在层级超过 15 级",
        5: "收到离线指示",
    },
    # 4.11 复位原因（注释 4）
    "复位原因": {
        0: "掉电复位", 1: "复位引脚复位", 2: "升级完成复位", 3: "CCO 控制从节点重启",
    },
    # 4.5/4.4 节点信息 D4~D7 节点角色
    "节点角色": {0x0: "无效", 0x1: "末梢节点（STA）", 0x2: "代理节点（PCO）", 0x3: "保留",
               0x4: "主节点（CCO）"},
}

#: 4.5 网络拓扑信息数据单元（13 字节，与本地接口一致）：(名称, 字节数, 类型)
TOPO_UNIT: List[Tuple[str, int, str]] = [
    ("节点标识（TEI）", 2, "bin_le"),
    ("代理节点标识（TEI）", 2, "bin_le"),
    ("节点加入网络时间", 4, "sec4"),
    ("代理变更次数", 2, "bin_le"),
    ("离线次数", 2, "bin_le"),
    ("节点信息", 1, "node_info"),
]

#: 4.4 周边节点信道信息数据单元（16 字节）：(名称, 字节数, 类型)
CHANNEL_UNIT: List[Tuple[str, int, str]] = [
    ("节点地址", 6, "addr6"),
    ("节点标识（TEI）", 2, "bin_le"),
    ("代理节点标识（TEI）", 2, "bin_le"),
    ("节点层级", 1, "bin"),
    ("上行通信成功率", 1, "pct"),
    ("下行通信成功率", 1, "pct"),
    ("上下行通信成功率", 1, "pct"),
    ("信噪比", 1, "bin"),
    ("衰减", 1, "bin"),
]

#: 4.1 通信模块信息数据项集合（65 字节，表 9）：(名称, 字节数, 类型, 说明)
LEDGER_FIELDS: List[Tuple[str, int, str, str]] = [
    ("模块资产编号", 32, "ascii", "不足 32 位则在高位补 0"),
    ("厂商代码", 2, "ascii", "文档「厂商代码」表"),
    ("软件版本信息（模块）", 2, "bcd", "BCD"),
    ("Bootloader 版本号", 1, "hex", "BIN"),
    ("芯片厂商代码", 2, "ascii", "文档「芯片厂商代码」表"),
    ("固件发布日期（模块）", 3, "date3", "BIN 3 字节"),
    ("模块出厂 MAC 地址", 6, "mac", "BIN"),
    ("硬件版本信息（模块）", 2, "bcd", "BCD"),
    ("硬件发布日期（模块）", 3, "date3", "BIN 3 字节"),
    ("软件版本号（芯片）", 2, "bcd", "BCD"),
    ("软件发布日期（芯片）", 3, "date3", "BIN 3 字节"),
    ("硬件版本号（芯片）", 2, "bcd", "BCD"),
    ("硬件发布日期（芯片）", 3, "date3", "BIN 3 字节"),
    ("应用程序版本号", 2, "bcd", "BCD；深化应用手册版本填写 0001"),
]

#: 4.14 远程通信模块网管信息（21 项；文档备注：报文字段**高位在前**）
REMOTE_MODULE_FIELDS: List[Tuple[str, int, str, str]] = [
    ("模组厂商编号", 8, "ascii", "内外置前缀 2B + 厂商 OUI 6B（DL/QR）"),
    ("模组序列号", 15, "ascii", ""),
    ("模组版本号", 32, "ascii", "厂商代码4+软件版本4+软件日期6+硬件版本4+硬件日期6+扩展8"),
    ("模组当前制式", 1, "enum_char:模组当前制式", "1 字节"),
    ("模组 IMEI 号", 15, "ascii", ""),
    ("模组型号", 64, "ascii_var", "长度小于 64 字节"),
    ("无线蜂窝 IP 地址", 4, "ip_be", "0xFFFFFFFF 表示 255.255.255.255"),
    ("SIM 卡 ICCID", 64, "ascii_var", "单个 20 字节，多个逗号分隔"),
    ("IMSI", 64, "ascii_var", "单个 15 字节，多个逗号分隔"),
    ("当前小区 ID", 4, "bin_be", ""),
    ("业务流量统计", 4, "bin_be", "单位 KB"),
    ("网管流量统计", 4, "bin_be", "单位 KB"),
    ("无线流量统计", 4, "bin_be", "单位 KB"),
    ("运营商名称", 1, "enum:运营商名称", ""),
    ("模组温度", 2, "bin_be", "文档未给字节数，按字段长度序列取 2 字节"),
    ("信噪比", 2, "bin_be", "取值范围 0~34dB（多通道以逗号分隔）"),
    ("上一次掉线原因", 1, "enum:上一次掉线原因", ""),
    ("上一次掉线时间", 4, "bin_be", "时间戳"),
    ("APN 名称", 64, "ascii", ""),
    ("APN 用户名", 64, "ascii", ""),
    ("APN 密码", 64, "ascii", ""),
]


# ── 基础解码工具 ──────────────────────────────────────────────────────


def _hex(raw: bytes) -> str:
    return raw.hex(" ").upper()


def _ascii(raw: bytes) -> str:
    """ASCII 解码（去首尾 NUL/空格）；含不可打印字符时回退为 HEX。"""
    text = raw.split(b"\x00")[0].decode("ascii", errors="replace").strip()
    if not text or any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in text):
        return f"{text}（HEX {_hex(raw)}）" if text else f"（HEX {_hex(raw)}）"
    return text


def _bcd(raw: bytes, decimals: int = 0) -> Optional[str]:
    """BCD（线上低字节在前）→ 十进制串；非 BCD 返回 None。"""
    from csg_uplink_di import decode_bcd_number
    return decode_bcd_number(raw, decimals)


def _enum(name: str, value: int) -> str:
    table = ENUMS.get(name, {})
    if value in table:
        return table[value]
    if name == "上次离网原因" and 0x80 <= value <= 0xEF:
        return f"厂家自定义（0x{value:02X}）"
    if name in ("上次离网原因", "复位原因") and value >= 0xF0:
        return f"保留（0x{value:02X}）"
    if name == "复位原因" and 0x80 <= value <= 0xEF:
        return f"厂家自定义（0x{value:02X}）"
    if name == "模块类型":
        return "保留"
    if name == "宽带载波频段":
        return "保留（3~255）"
    return f"未定义（0x{value:02X}）"


def _mac(raw: bytes) -> str:
    return ":".join(f"{b:02X}" for b in raw)


def _date3(raw: bytes) -> str:
    bcd = _bcd(raw)
    if bcd and len(bcd) == 6:
        return f"BCD 20{bcd[0:2]}-{bcd[2:4]}-{bcd[4:6]}（HEX {_hex(raw)}）"
    return f"BIN {int.from_bytes(raw, 'little')}（HEX {_hex(raw)}）"


def _sec4(raw: bytes) -> str:
    sec = int.from_bytes(raw, "little")
    if sec == 0:
        return "0 秒（未记录）"
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h >= 24:
        return f"{sec} 秒（约 {h // 24} 天 {h % 24} 时 {m} 分 {s} 秒）"
    return f"{sec} 秒（{h} 时 {m} 分 {s} 秒）"


def _addr6(raw: bytes) -> str:
    """节点地址（6 字节 BCD，线上低字节在前）→ 12 位十进制；非 BCD 回退 HEX。"""
    bcd = _bcd(raw)
    return bcd if bcd is not None else f"HEX {_hex(raw)}"


def _node_info(value: int) -> Tuple[str, str]:
    """4.5 节点信息（1B）：D0~D3 层级、D4~D7 角色。"""
    level = value & 0x0F
    role = (value >> 4) & 0x0F
    return (f"0x{value:02X}",
            f"层级={level}（0 级=CCO） 角色=0x{role:X} {_enum('节点角色', role)}")


_IP_PLACEHOLDER = 0xFFFFFFFF


def _ip_be(raw: bytes) -> str:
    v = int.from_bytes(raw, "big")
    if v == _IP_PLACEHOLDER:
        return "255.255.255.255（无效/未分配）"
    return ".".join(str(b) for b in raw)


# ── 数据单元解码（逐字段 subrows）─────────────────────────────────────


def _unit_rows(unit: List[Tuple[str, int, str]], raw: bytes, prefix: str,
               offset: int) -> List[dict]:
    """按数据单元定义逐字段展开（``{{n}}`` 占位替换为序号）。"""
    rows: List[dict] = []
    pos = 0
    for idx, (name, size, kind) in enumerate(unit, 1):
        chunk = raw[pos:pos + size]
        if len(chunk) < size:
            rows.append({"名称": f"{prefix}{name.format(n=idx)} · 截断", "原始值": _hex(chunk),
                         "解析值": "", "说明": f"⚠ 期望 {size} 字节，实得 {len(chunk)} 字节",
                         "偏移": offset + pos, "长度": len(chunk)})
            break
        label = prefix + name.format(n=idx)
        rows.append({"名称": label, "原始值": _hex(chunk),
                     "解析值": _scalar(kind, chunk), "说明": _kind_note(kind),
                     "偏移": offset + pos, "长度": size})
        pos += size
    return rows


def _scalar(kind: str, chunk: bytes) -> str:
    if kind == "ascii":
        return _ascii(chunk)
    if kind == "ascii_var":
        return _ascii(chunk)
    if kind == "bcd":
        bcd = _bcd(chunk)
        return f"{bcd}（BCD）" if bcd is not None else f"HEX {_hex(chunk)}"
    if kind == "date3":
        return _date3(chunk)
    if kind == "sec4":
        return _sec4(chunk)
    if kind == "mac":
        return _mac(chunk)
    if kind == "addr6":
        return _addr6(chunk)
    if kind in ("bin", "hex"):
        return f"{int.from_bytes(chunk, 'little')}（0x{int.from_bytes(chunk, 'little'):X}）" \
            if kind == "bin" else f"0x{int.from_bytes(chunk, 'little'):X}"
    if kind == "bin_le":
        return str(int.from_bytes(chunk, "little"))
    if kind == "bin_be":
        return str(int.from_bytes(chunk, "big"))
    if kind == "ip_be":
        return _ip_be(chunk)
    if kind == "pct":
        return f"{chunk[0]}%"
    if kind == "node_info":
        return _node_info(chunk[0])[1]
    if kind.startswith("enum:"):
        return _enum(kind.split(":", 1)[1], chunk[0])
    if kind.startswith("enum_char:"):
        val = chunk[0]
        return f"{_enum(kind.split(':', 1)[1], val)}（0x{val:02X}）"
    return f"HEX {_hex(chunk)}"


def _kind_note(kind: str) -> str:
    notes = {
        "bin_le": "BIN（低字节在前）", "bin_be": "BIN（高位在前，见 4.14 备注）",
        "bin": "BIN", "hex": "HEX", "ascii": "ASCII", "ascii_var": "ASCII（变长）",
        "bool": "", "ip_be": "IPv4（高位在前）", "pct": "百分比",
        "node_info": "D0~D3 层级 / D4~D7 角色",
    }
    return notes.get(kind, "")


def _count_rows(content: bytes, head: int, unit: List[Tuple[str, int, str]], unit_bytes: int,
                total_label: str, count_label: str, offset_base: int) -> Tuple[List[dict], str]:
    """公共：``总数(2B) + 本次数量(1B) + n×数据单元`` 类内容的展开（内容不足时只给告警行）。"""
    rows: List[dict] = []
    if len(content) < 3:
        rows.append({"名称": "⚠ 长度校验", "原始值": _hex(content), "解析值": "",
                     "说明": f"⚠ 内容不足 3 字节（总数量 2B + 本次数量 1B），实得 {len(content)} 字节",
                     "偏移": offset_base, "长度": len(content)})
        return rows, ""
    total = int.from_bytes(content[0:2], "little")
    n = content[2]
    rows.append({"名称": total_label, "原始值": _hex(content[0:2]), "解析值": str(total),
                 "说明": "BIN（低字节在前）", "偏移": offset_base, "长度": 2})
    rows.append({"名称": count_label, "原始值": f"{n:02X}", "解析值": str(n),
                 "说明": "本次应答的节点数量", "偏移": offset_base + 2, "长度": 1})
    warn = ""
    payload = content[head:]
    for i in range(n):
        chunk = payload[i * unit_bytes:(i + 1) * unit_bytes]
        if len(chunk) < unit_bytes:
            warn = f"⚠ 第 {i + 1} 条数据单元截断（期望 {unit_bytes} 字节，实得 {len(chunk)}）"
            break
        for r in _unit_rows(unit, chunk, f"节点{i + 1} · ", offset_base + head + i * unit_bytes):
            rows.append(r)
    if not warn:
        rest = len(payload) - n * unit_bytes
        if rest > 0:
            warn = f"⚠ 内容尾部多出 {rest} 字节（与「总数/本次数量」推算不符，原文见右侧）"
    return rows, warn


def _addr_list_rows(content: bytes, offset_base: int, total_label: str) -> Tuple[List[dict], str]:
    rows, warn = _count_rows(content, 3, [("从节点地址", 6, "addr6")], 6, total_label,
                             "本次应答的从节点数量 n", offset_base)
    return rows, warn


# ── 各 DI 的结构化解码 ────────────────────────────────────────────────


def _decode_ledger(content: bytes, offset: int) -> Tuple[List[dict], str, str]:
    """4.1 E0 80 04 xx → 65 字节通信模块信息数据项集合。"""
    rows = []
    pos = 0
    for name, size, kind, note in LEDGER_FIELDS:
        chunk = content[pos:pos + size]
        if len(chunk) < size:
            rows.append({"名称": name, "原始值": _hex(chunk), "解析值": "",
                         "说明": f"⚠ 期望 {size} 字节，实得 {len(chunk)} 字节",
                         "偏移": offset + pos, "长度": len(chunk)})
            break
        rows.append({"名称": name, "原始值": _hex(chunk), "解析值": _scalar(kind, chunk),
                     "说明": note or _kind_note(kind), "偏移": offset + pos, "长度": size})
        pos += size
    warn = "" if pos == 65 else f"⚠ 台账应为 65 字节，实得 {len(content)} 字节"
    summary = "；".join(f"{r['名称']}={r['解析值']}" for r in rows[:3]) + " …" if rows else ""
    return rows, warn, summary


def _decode_ard2(content: bytes, offset: int) -> Tuple[List[dict], str, str]:
    """4.7 E2 00 00 33/34 → ARD2（附 D.2）：告警状态 + 告警发生时间(YYMMDDhhmmss) + 发生时数据。"""
    rows: List[dict] = []
    if len(content) >= 1:
        rows.append({"名称": "告警状态", "原始值": f"{content[0]:02X}",
                     "解析值": f"0x{content[0]:02X}", "说明": "附 D.2（字节数以厂家填充为准）",
                     "偏移": offset, "长度": 1})
    if len(content) >= 7:
        t = content[1:7]
        bcd = _bcd(t)
        tstr = (f"20{bcd[0:2]}-{bcd[2:4]}-{bcd[4:6]} {bcd[6:8]}:{bcd[8:10]}:{bcd[10:12]}"
                if bcd and len(bcd) == 12 else f"HEX {_hex(t)}")
        rows.append({"名称": "告警发生时间", "原始值": _hex(t), "解析值": tstr,
                     "说明": "BCD YYMMDDhhmmss（线上低字节在前）", "偏移": offset + 1, "长度": 6})
    if len(content) > 7:
        rows.append({"名称": "发生时数据", "原始值": _hex(content[7:]), "解析值": "",
                     "说明": "ARD2 发生时数据（按告警类型取附 D.2 数据项，本版未逐项展开）",
                     "偏移": offset + 7, "长度": len(content) - 7})
    if len(content) < 7:
        return rows, f"⚠ ARD2 至少 7 字节（状态 1 + 发生时间 6），实得 {len(content)} 字节", ""
    return rows, "", rows[1]["解析值"] if len(rows) > 1 else ""


def _decode_remote_module(content: bytes, offset: int) -> Tuple[List[dict], str, str]:
    """4.14 E1 00 60 16 → 远程通信模块网管信息（21 项，报文字段高位在前）。

    固定前缀 71 字节（厂商编号 8 + 序列号 15 + 版本号 32 + 制式 1 + IMEI 15）后为
    **变长字段区**（型号/IP/ICCID/IMSI）与固定尾部（26 字节数值 + 3×64 字节 APN），
    故尾部按「自尾向前」定位，变长区按「ASCII 串 + 4 字节 IP + ASCII 串 + 剩余」尽力解析。
    """
    rows: List[dict] = []
    head_specs = REMOTE_MODULE_FIELDS[0:5]
    pos = 0
    for name, size, kind, note in head_specs:
        chunk = content[pos:pos + size]
        if len(chunk) < size:
            return rows, f"⚠ 内容不足固定前缀 71 字节（实得 {len(content)} 字节）", ""
        rows.append({"名称": name, "原始值": _hex(chunk), "解析值": _scalar(kind, chunk),
                     "说明": note or _kind_note(kind), "偏移": offset + pos, "长度": size})
        pos += size

    tail_specs = REMOTE_MODULE_FIELDS[13:]            # 运营商名称 … APN 密码（固定 202 字节）
    tail_bytes = sum(s for _, s, _, _ in tail_specs)  # 1+2+2+1+4+64+64+64 = 202
    mid_specs = REMOTE_MODULE_FIELDS[9:13]            # 小区ID + 3 个流量（固定 16 字节）
    mid_bytes = sum(s for _, s, _, _ in mid_specs)    # 4×4 = 16
    if len(content) < 71 + mid_bytes + tail_bytes:
        warn = (f"⚠ 内容不足（固定前缀 71 + 数值区 {mid_bytes} + 尾部 {tail_bytes}，"
                f"实得 {len(content)} 字节）")
        return rows, warn, ""
    tail = content[-tail_bytes:]
    mid = content[-(tail_bytes + mid_bytes):-tail_bytes]
    var_area = content[71:-(tail_bytes + mid_bytes)]   # 型号(≤64) + IP(4) + ICCID(≤64) + IMSI(≤64)

    def _take_ascii(buf: bytes, limit: int = 64) -> Tuple[bytes, bytes]:
        """取开头连续可打印 ASCII 串（长度上限 limit）→ (串, 余下)。"""
        k = 0
        while k < len(buf) and k < limit and 0x20 <= buf[k] <= 0x7E:
            k += 1
        return buf[:k], buf[k:]

    if len(var_area) >= 64 + 4 + 64 + 64:              # 变长字段按上限填充 → 按最大长度切分
        model, ip, iccid, imsi = (var_area[:64], var_area[64:68],
                                  var_area[68:132], var_area[132:196])
        extra = var_area[196:]
        pad_note = "按上限填充切分"
    else:                                              # 未填充 → 按 ASCII 串 + 4B IP 尽力解析
        model, rest = _take_ascii(var_area, 64)
        ip = rest[:4]
        rest = rest[4:]
        iccid, rest = _take_ascii(rest, 64)
        imsi, extra = _take_ascii(rest, 64)
        pad_note = "变长字段尽力解析"
    var_rows = [
        ("模组型号", model, "ascii_var", "长度小于 64 字节"),
        ("无线蜂窝 IP 地址", ip, "ip_be", "0xFFFFFFFF 表示 255.255.255.255"),
        ("SIM 卡 ICCID", iccid, "ascii_var", "单个 20 字节，多个逗号分隔"),
        ("IMSI", imsi, "ascii_var", "单个 15 字节，多个逗号分隔"),
    ]
    for name, chunk, kind, note in var_rows:
        rows.append({"名称": name, "原始值": _hex(chunk), "解析值": _scalar(kind, chunk),
                     "说明": f"{note}（{pad_note}）", "偏移": offset + 71,
                     "长度": len(chunk)})
    if extra:
        rows.append({"名称": "变长区剩余字节", "原始值": _hex(extra), "解析值": "",
                     "说明": "⚠ 未归入任何字段（变长字段填充方式与文档假设不一致，请对照原文）",
                     "偏移": offset + 71, "长度": len(extra)})
    # 小区 ID + 3 个流量统计（固定 4 字节整，高位在前）
    mid_off = offset + 71 + len(var_area)
    for k, (name, size, kind, note) in enumerate(mid_specs):
        chunk = mid[k * size:(k + 1) * size]
        rows.append({"名称": name, "原始值": _hex(chunk), "解析值": _scalar(kind, chunk),
                     "说明": note or _kind_note(kind), "偏移": mid_off + k * size,
                     "长度": len(chunk)})
    # 尾部（运营商 … APN 密码）
    acc = 0
    for name, size, kind, note in tail_specs:
        chunk = tail[acc:acc + size]
        note_txt = note or _kind_note(kind)
        if kind in ("bin_be", "ip_be"):
            note_txt += "（高位在前）"
        rows.append({"名称": name, "原始值": _hex(chunk), "解析值": _scalar(kind, chunk),
                     "说明": note_txt, "偏移": offset + len(content) - tail_bytes + acc,
                     "长度": len(chunk)})
        acc += size
    return rows, "", ""


def subrows(di: str, content: bytes) -> List[dict]:
    """网管扩展 DI + 内容 → 逐字段行 ``{名称,原始值,解析值,说明,偏移,长度}``（偏移相对内容起点）。"""
    d = (di or "").upper()
    if d not in _NM_INDEX and resolve_prefix(d) is None:
        return []
    d = resolve_prefix(d) or d
    content = bytes(content)
    rows: List[dict] = []
    warn = ""
    if d == "E08004FF":
        rows, warn, _ = _decode_ledger(content, 0)
    elif d in ("E1006012", "E1006008"):
        label = "入网从节点数量" if d == "E1006012" else "从节点总数量"
        rows, warn = _addr_list_rows(content, 0, label)
    elif d == "E1800052":
        bcd = _bcd(content)
        pct = ""
        if bcd is not None:
            num = int(bcd)
            pct = f"{num / 100:.2f}%"
        rows.append({"名称": "台区组网成功率", "原始值": _hex(content), "解析值": pct or _hex(content),
                     "说明": "BCD，模块上报扩大 100 倍（10000 → 100.00%）", "偏移": 0,
                     "长度": len(content)})
    elif d == "E1006009":
        rows, warn = _count_rows(content, 3, CHANNEL_UNIT, 16, "周边节点总数量",
                                 "本次应答的节点数量 n", 0)
    elif d in ("E1006004", "E1006014"):
        if len(content) >= 5:
            rows, warn = _count_rows(content[2:], 3, TOPO_UNIT, 19, "节点总数量",
                                     "本次应答的节点数量 n", 2)
            rows.insert(0, {"名称": "节点起始序号", "原始值": _hex(content[2:4]),
                            "解析值": str(int.from_bytes(content[2:4], "little")),
                            "说明": "BIN（低字节在前）", "偏移": 2, "长度": 2})
        else:
            warn = f"⚠ 内容不足 5 字节（节点总数量 2 + 起始序号 2 + 本次数量 1），实得 {len(content)} 字节"
    elif d == "E1006015":
        mt = content[0] if content else 0
        rows.append({"名称": "模块类型", "原始值": f"{mt:02X}", "解析值": _enum("模块类型", mt),
                     "说明": "0x1 抄控器 / 0x2 集中器通信模块 / …（表 17）", "偏移": 0, "长度": 1})
        dur = content[1:5]
        rows.append({"名称": "节点离线时长", "原始值": _hex(dur), "解析值": _sec4(dur),
                     "说明": "BIN 4 字节，单位秒（从节点最后一次离线时长）", "偏移": 1,
                     "长度": len(dur)})
    elif d in ("E2000033", "E2000034"):
        rows, warn, _ = _decode_ard2(content, 0)
    elif d == "E1006005":
        n = content[0] if content else 0
        rows.append({"名称": "多网络节点总数量 n", "原始值": f"{n:02X}", "解析值": str(n),
                     "说明": "BIN", "偏移": 0, "长度": 1})
        rows.append({"名称": "本节点网络标识号", "原始值": f"{content[1]:02X}" if len(content) > 1 else "",
                     "解析值": str(content[1]) if len(content) > 1 else "",
                     "说明": "BIN（SNID）", "偏移": 1, "长度": 1})
        addr = content[2:8]
        rows.append({"名称": "本节点主节点地址", "原始值": _hex(addr), "解析值": _addr6(addr),
                     "说明": "BCD（线上低字节在前）", "偏移": 2, "长度": len(addr)})
        for i in range(n):
            chunk = content[8 + i:9 + i]
            if not chunk:
                warn = f"⚠ 邻居节点网络标识号截断（声明 {n} 个，实得 {i} 个）"
                break
            rows.append({"名称": f"邻居节点{i + 1}网络标识号", "原始值": f"{chunk[0]:02X}",
                         "解析值": str(chunk[0]), "说明": "BIN（SNID）", "偏移": 8 + i, "长度": 1})
    elif d == "E0000040":
        band = content[0] if content else 0
        rows.append({"名称": "宽带载波频段", "原始值": f"{band:02X}",
                     "解析值": _enum("宽带载波频段", band),
                     "说明": "BIN，0/1/2 定义见 4.9，3~255 保留", "偏移": 0, "长度": 1})
    elif d == "E1006010":
        kinds = [("过零自检结果", "过零自检结果(单相表模块)", "主节点/三相表模块另见 4.11 注释 1"),
                 ("串口/485不通状态", "串口485不通状态", ""),
                 ("上次离网原因", "上次离网原因", ""),
                 ("复位原因", "复位原因", "")]
        for i, (name, enum_name, note) in enumerate(kinds):
            if i >= len(content):
                warn = f"⚠ 自检信息应为 4 字节，实得 {len(content)} 字节"
                break
            val = content[i]
            rows.append({"名称": name, "原始值": f"{val:02X}", "解析值": _enum(enum_name, val),
                         "说明": note, "偏移": i, "长度": 1})
    elif d == "E0000041":
        val = content[0] if content else 0xFF
        rows.append({"名称": "从节点重启", "原始值": f"{val:02X}",
                     "解析值": "重启" if val == 0 else f"保留（0x{val:02X}）",
                     "说明": "NN：0=表示重启，其他保留", "偏移": 0, "长度": 1})
    elif d == "E1006013":
        val = content[0] if content else 0
        rows.append({"名称": "并发数", "原始值": f"{val:02X}", "解析值": str(val), "说明": "BIN",
                     "偏移": 0, "长度": 1})
    elif d == "E1006016":
        rows, warn, _ = _decode_remote_module(content, 0)
    if warn:
        rows.append({"名称": "⚠ 长度校验", "原始值": _hex(content), "解析值": "",
                     "说明": warn, "偏移": 0, "长度": len(content)})
    return rows


def _summary(rows: List[dict], di: str) -> str:
    """把 subrows 压成一行摘要（内容解析行用）。"""
    d = (di or "").upper()
    if d == "E08004FF":
        head = [r for r in rows if r["名称"] in ("模块资产编号", "厂商代码", "应用程序版本号")]
        return "；".join(f"{r['名称']}={r['解析值']}" for r in head)
    if d == "E1006016":
        keep = ("模组厂商编号", "模组序列号", "模组当前制式", "模组 IMEI 号")
        return "；".join(f"{r['名称']}={r['解析值']}" for r in rows if r["名称"] in keep)
    if d == "E1006015":
        return "；".join(f"{r['名称']}={r['解析值']}" for r in rows)
    counts = [r for r in rows if ("数量" in r["名称"] or "总数量" in r["名称"])]
    if counts and d not in ("E1006005",):
        return "；".join(f"{r['名称']}={r['解析值']}" for r in counts)
    # 通用兜底：单字段 DI 直接给值，多字段给「名称=解析值；…」（跳过 ⚠ 行）
    body = [r for r in rows if r.get("解析值") and not r["名称"].startswith("⚠")]
    if len(body) == 1:
        return str(body[0]["解析值"])
    return "；".join(f"{r['名称']}={r['解析值']}" for r in body)


def decode(di: str, content: bytes) -> Dict[str, object]:
    """网管扩展 DI → ``{解析值, 说明, 子项}``；非网管扩展 DI 返回空 dict。"""
    d = resolve_prefix((di or "").upper())
    if d is None:
        return {}
    rows = subrows(d, content)
    warn = next((r["说明"] for r in rows if r["名称"].startswith("⚠")), "")
    summary = _summary(rows, d)
    name = _NM_INDEX.get(d, {}).get("name", "")
    note = f"{name}" + (f"；{warn}" if warn else "")
    return {"解析值": summary, "说明": note, "子项": rows}


# ── 内容长度（变长列表 DI 依内容推算）────────────────────────────────


def content_length(di: str, data: bytes = b"") -> Optional[int]:
    """网管扩展 DI 的内容字节数；变长列表按内容推算，不足返回 None。"""
    d = resolve_prefix((di or "").upper())
    if d is None:
        return None
    fixed = {"E08004FF": 65, "E1800052": 3, "E1006015": 5, "E1006010": 4,
             "E0000040": 1, "E0000041": 1, "E1006013": 1}
    if d in fixed:
        return fixed[d]
    data = bytes(data)
    if d in ("E1006012", "E1006008"):
        return 3 + 6 * data[2] if len(data) >= 3 else None
    if d == "E1006009":
        return 3 + 16 * data[2] if len(data) >= 3 else None
    if d == "E1006004" or d == "E1006014":
        return 5 + 19 * data[4] if len(data) >= 5 else None
    if d == "E1006005":
        return 8 + data[0] if len(data) >= 1 else None
    return None


def resolve_prefix(di: str) -> Optional[str]:
    """按前缀规则把「含序号的 DI」归一到索引条目 DI（如 ``E0800402`` → ``E08004FF``）。"""
    d = (di or "").upper()
    if d in _NM_INDEX:
        return d
    for prefix, target in NM_PREFIX_RULES.items():
        if d.startswith(prefix) and len(d) == 8:
            return target
    return None


def is_nm_di(di: str) -> bool:
    """是否属于网管扩展（含前缀规则命中）。"""
    return resolve_prefix(di) is not None


_NM_INDEX: Dict[str, dict] = {e["di"]: e for e in NM_DIS}
