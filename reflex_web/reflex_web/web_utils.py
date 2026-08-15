# -*- coding: utf-8 -*-
"""Reflex Web 版工具函数

纯函数工具集，供 State 类调用。包括：
- 帧提取（各协议）
- 前缀剥离（监控日志、TCP包装头）
- 摘要提取
- 报文工具函数（字节倒序、CRC、HEX/ASCII转换等）
"""
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# 确保项目根目录在路径中
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════
# HEX 输入清洗
# ═══════════════════════════════════════════════════════════════

def clean_hex_input(text: str, keep_newlines: bool = False) -> str:
    """预处理报文输入：去除空格、逗号、换行等分隔符，支持 0x 前缀，仅保留十六进制字符

    支持的输入格式：
      - 纯 hex: 6811010101
      - 空格分隔: 68 11 01 01 01
      - 逗号分隔: 68,11,01,01,01
      - 混合分隔: 68, 11, 01 - 01. 01
      - 0x 前缀: 0x68 0x11 0x01 或 0x68,0x11,0x01
      - 换行分隔(多帧): 每行一帧
    """
    # 先处理 0x/0X 前缀：将 0x68 转为 68，避免 0x 被误清洗导致字节对齐错误
    text = re.sub(r'0[xX]([0-9A-Fa-f])', r'\1', text)
    pattern = r'[^0-9A-Fa-f\n]' if keep_newlines else r'[^0-9A-Fa-f]'
    return re.sub(pattern, '', text)


# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

CSG_MONITOR_PREFIX = "> 接收机 Has Get"
CSG_MONITOR_HEADER_BYTES = 15  # 监控头字节数


# ═══════════════════════════════════════════════════════════════
# 前缀剥离
# ═══════════════════════════════════════════════════════════════

def strip_csg_monitor_prefix(text: str) -> str:
    """剥离新一代载波协议监控日志前缀

    仅保留含 "> 接收机 Has Get" 标记的行，
    跳过标记后前 15 字节监控头。
    """
    prefix = CSG_MONITOR_PREFIX
    prefix_len = len(prefix)

    out_lines = []
    for line in text.splitlines():
        pos = line.find(prefix)
        if pos == -1:
            continue
        after = line[pos + prefix_len:]
        tokens = re.findall(r'[0-9A-Fa-f]{1,2}', after)
        payload_tokens = tokens[CSG_MONITOR_HEADER_BYTES:]
        if payload_tokens:
            out_lines.append(' '.join(payload_tokens))
    return '\n'.join(out_lines)


def strip_csg_new_gen_prefix(text: str, parse_level: str = "auto") -> str:
    """南网新一代通感一体化批量解析预处理

    - 含监控日志标记 → 用 strip_csg_monitor_prefix
    - 否则按行处理：取最后一个冒号后 hex，按解析级别定位帧起始
    """
    if CSG_MONITOR_PREFIX in text:
        return strip_csg_monitor_prefix(text)

    out_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 取最后一个冒号后的 hex
        last_colon = line.rfind(':')
        if last_colon >= 0:
            hex_part = line[last_colon + 1:].strip()
        else:
            hex_part = line
        hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part).upper()
        if len(hex_clean) < 4:
            continue
        if len(hex_clean) % 2 != 0:
            hex_clean = hex_clean[:-1]

        # TCP 包装前缀 EDA5
        if parse_level != "pb_only" and hex_clean.startswith("EDA5"):
            if len(hex_clean) >= 62:
                hex_clean = hex_clean[30:]
                out_lines.append(hex_clean)
            continue

        if parse_level == "pb_only":
            pass  # 直接保留
        elif parse_level == "app":
            # 扫描端口 0x11
            found = False
            i = 0
            while i < len(hex_clean) - 1:
                if hex_clean[i:i+2] == '11' and len(hex_clean) - i >= 8:
                    hex_clean = hex_clean[i:]
                    found = True
                    break
                i += 2
            if not found:
                continue
        else:
            # fc_pb / fc_only / fc_efc / auto: 扫描 FC 起始特征
            # 低4位 ∈ {0x8, 0x9, 0xA, 0xB} 即 bit3=1 且 bit0-2<=3
            found = False
            i = 0
            while i < len(hex_clean) - 1:
                byte_val = int(hex_clean[i:i+2], 16)
                low_nibble = byte_val & 0x0F
                if low_nibble in (0x8, 0x9, 0xA, 0xB) and len(hex_clean) - i >= 32:
                    hex_clean = hex_clean[i:]
                    found = True
                    break
                i += 2
            if not found:
                continue  # 该行无有效 FC 起始，丢弃

        out_lines.append(hex_clean)
    return '\n'.join(out_lines)


def strip_gw_new_gen_prefix(text: str, parse_level: str = "auto") -> str:
    """剥离国网新一代双模协议日志前缀

    - 找到最后一个冒号，其后为 hex
    - app 级别扫描 '11' 定位应用层
    """
    out_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        last_colon = line.rfind(':')
        if last_colon >= 0:
            hex_part = line[last_colon + 1:].strip()
        else:
            hex_part = line
        hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part).upper()
        if len(hex_clean) < 4:
            continue

        if parse_level == 'app':
            found = False
            i = 0
            while i < len(hex_clean) - 1:
                if hex_clean[i:i+2] == '11' and len(hex_clean) - i >= 8:
                    hex_clean = hex_clean[i:]
                    found = True
                    break
                i += 2
            if not found:
                continue
        out_lines.append(hex_clean)
    return '\n'.join(out_lines)


# ═══════════════════════════════════════════════════════════════
# 帧提取
# ═══════════════════════════════════════════════════════════════

def extract_68_frames(clean: str) -> List[str]:
    """提取 68 格式帧（南网/国网 FT1.2）"""
    frames = []
    i = 0
    while i < len(clean) - 7:
        pos = clean.find('68', i)
        if pos == -1:
            break
        if pos + 6 > len(clean):
            i = pos + 2
            continue
        try:
            low_byte = int(clean[pos + 2:pos + 4], 16)
            high_byte = int(clean[pos + 4:pos + 6], 16)
            length = low_byte | (high_byte << 8)
        except ValueError:
            i = pos + 2
            continue
        if length < 8 or length > 2048:
            i = pos + 2
            continue
        frame_hex_len = length * 2
        if pos + frame_hex_len > len(clean):
            i = pos + 2
            continue
        candidate = clean[pos:pos + frame_hex_len]
        if candidate[-2:] != '16':
            i = pos + 2
            continue
        frames.append(candidate)
        i = pos + frame_hex_len
    return frames


def extract_69845_frames(clean: str) -> List[str]:
    """提取 698.45 格式帧"""
    frames = []
    i = 0
    while i < len(clean) - 7:
        pos = clean.find('68', i)
        if pos == -1:
            break
        if pos + 6 > len(clean):
            i = pos + 2
            continue
        try:
            low_byte = int(clean[pos + 2:pos + 4], 16)
            high_byte = int(clean[pos + 4:pos + 6], 16)
            length = low_byte | (high_byte << 8)
        except ValueError:
            i = pos + 2
            continue
        if length < 8 or length > 2048:
            i = pos + 2
            continue
        total_len = length + 4
        frame_hex_len = total_len * 2
        if pos + frame_hex_len > len(clean):
            i = pos + 2
            continue
        candidate = clean[pos:pos + frame_hex_len]
        if candidate[-2:] != '16':
            i = pos + 2
            continue
        frames.append(candidate)
        i = pos + frame_hex_len
    return frames


def extract_hdlc_frames(clean: str) -> List[str]:
    """提取 HDLC 帧（7E 开头 7E 结束）"""
    frames = []
    i = 0
    while i < len(clean) - 3:
        pos = clean.find('7E', i)
        if pos == -1:
            break
        end = clean.find('7E', pos + 2)
        if end == -1:
            end = min(pos + 512, len(clean))
        candidate = clean[pos:end + 2]
        if len(candidate) >= 6:
            frames.append(candidate)
        i = end + 2
    return frames


def extract_wrapper_frames(text: str) -> List[str]:
    """提取 DLMS Wrapper 帧"""
    frames = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        hex_matches = re.findall(r'[0-9A-Fa-f]{16,}', line)
        if not hex_matches:
            continue
        for hex_pattern in hex_matches:
            hex_pattern = hex_pattern.upper()
            i = 0
            while i <= len(hex_pattern) - 16:
                if hex_pattern[i:i+4] == '0001':
                    apdu_len = int(hex_pattern[i+12:i+16], 16)
                    if 0 <= apdu_len <= 8192:
                        frame_len = 16 + apdu_len * 2
                        if i + frame_len <= len(hex_pattern):
                            frames.append(hex_pattern[i:i+frame_len])
                            i += frame_len
                            continue
                        else:
                            frames.append(hex_pattern[i:])
                            break
                i += 2
    return frames if frames else [re.sub(r'[^0-9A-Fa-f]', '', text).upper()]


def extract_csg_new_gen_frames(text: str) -> List[str]:
    """提取新一代载波协议帧（按行）"""
    frames = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        clean_line = ''.join(c for c in line if c in '0123456789ABCDEFabcdef').upper()
        if len(clean_line) < 8:
            continue
        if len(clean_line) % 2 != 0:
            clean_line = clean_line[:-1]
        frames.append(clean_line)
    return frames


def extract_68_from_raw(text: str) -> List[str]:
    """从原始文本中直接匹配 68...16 帧模式"""
    frames = []
    seen = set()
    for line in text.splitlines():
        for m in re.finditer(r'(68[0-9A-Fa-f]{10,}16)', line):
            candidate = m.group(1).upper()
            if len(candidate) % 2 != 0:
                candidate = candidate[:-1]
            if len(candidate) < 16:
                continue
            try:
                low = int(candidate[2:4], 16)
                high = int(candidate[4:6], 16)
                length = low | (high << 8)
                if 8 <= length <= 2048 and candidate not in seen:
                    seen.add(candidate)
                    frames.append(candidate)
            except ValueError:
                pass
    return frames


def extract_generic_frames(clean: str, min_len: int = 4, max_len: int = 256) -> List[str]:
    """通用帧提取（整段 hex 作为单帧判断）

    与 GUI 版 _extract_generic_frames 行为一致：
    输入为已清洗的纯 hex 字符串，若总长度在 [min_len, max_len] 字节范围内
    且长度为偶数，则作为单帧返回，否则返回空列表。
    """
    if len(clean) >= min_len * 2 and len(clean) <= max_len * 2:
        return [clean] if len(clean) % 2 == 0 else []
    return []


def extract_frames_for_protocol(text: str, protocol_index: int) -> List[str]:
    """根据协议类型提取帧（与 GUI 版 _extract_frames_for_protocol 行为一致）

    调用前建议先用 clean_hex_input(text, keep_newlines=True) 清洗输入，
    但协议 9/10 的前缀剥离必须在清洗之前完成。
    """
    if protocol_index in (0, 7):  # 南网 / 国网：68开头，16结束，FT1.2帧格式
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return extract_68_frames(clean)
    elif protocol_index == 1:  # PLC RF协议：通用提取（整段作为一帧）
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return extract_generic_frames(clean, min_len=4, max_len=256)
    elif protocol_index == 2:  # HDLC/DLMS协议：7E开头，7E结束
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return extract_hdlc_frames(clean)
    elif protocol_index in (3, 5):  # DLMS-APDU：按行分割，每行一帧
        return [f.strip() for f in text.splitlines() if f.strip()]
    elif protocol_index == 4:  # DLMS Wrapper裸报文：识别Wrapper头部并分割
        return extract_wrapper_frames(text)
    elif protocol_index == 6:  # DLT645-2007：按行分割，每行一帧
        return [f.strip() for f in text.splitlines() if f.strip()]
    elif protocol_index == 8:  # 698.45：68开头，16结束，长度域定义不同（总长度 = L + 4）
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return extract_69845_frames(clean)
    elif protocol_index == 9:  # 新一代载波协议(通感一体化)：按行提取，过滤无效短帧
        return extract_csg_new_gen_frames(text)
    elif protocol_index == 10:  # 国网新一代双模：按行提取，每行一帧
        return [f.strip() for f in text.splitlines() if f.strip() and len(f.strip()) >= 4]
    elif protocol_index == 11:  # HDC 1.0 双模互联互通：按行提取，每行一帧
        return [f.strip() for f in text.splitlines() if f.strip() and len(f.strip()) >= 4]
    else:
        return [f.strip() for f in text.splitlines() if f.strip()]


# ═══════════════════════════════════════════════════════════════
# 摘要提取
# ═══════════════════════════════════════════════════════════════

def _find_field(table_data: List, field_keyword: str) -> Optional[tuple]:
    """在表格数据中查找含关键字的字段行"""
    for row in table_data:
        if len(row) >= 4 and row[0] and field_keyword in str(row[0]):
            return row
    return None


def get_csg_new_gen_summary(table_data: List) -> str:
    """新一代载波协议摘要提取"""
    if not table_data:
        return "空"

    # 解析失败
    first_field = str(table_data[0][0]) if table_data[0] else ""
    if "❌" in first_field or "失败" in first_field:
        return str(table_data[0][3]) if len(table_data[0]) >= 4 else "解析失败"

    # MMTYPE（网络管理消息）
    mmtype_row = _find_field(table_data, "MMTYPE")
    if mmtype_row:
        name = str(mmtype_row[3]) if len(mmtype_row) >= 4 and mmtype_row[3] else str(mmtype_row[2])
        msdu_row = _find_field(table_data, "MSDU类型")
        msdu = str(msdu_row[3]) if msdu_row and len(msdu_row) >= 4 else ""
        version_row = _find_field(table_data, "版本号")
        ver = str(version_row[2]) if version_row and len(version_row) >= 3 else ""
        parts = [p for p in [msdu, f"MMTYPE:{name}", f"版本{ver}" if ver else ""] if p]
        return " | ".join(parts)

    # 定界符类型（MPDU/MAC 物理层帧）
    delim_row = _find_field(table_data, "定界符类型")
    if delim_row:
        msdu_row = _find_field(table_data, "MSDU类型")
        msdu = str(msdu_row[3]) if msdu_row and len(msdu_row) >= 4 else ""
        delim_name = str(delim_row[3]) if len(delim_row) >= 4 and delim_row[3] else str(delim_row[2])
        parts = [msdu, delim_name]

        # 源/目的 TEI
        src_tei = _find_field(table_data, "源TEI")
        dst_tei = _find_field(table_data, "目的TEI")
        if src_tei and dst_tei:
            parts.append(f"源TEI={src_tei[2]}→目的TEI={dst_tei[2]}")

        # 信标类型
        beacon_type = _find_field(table_data, "信标类型")
        if beacon_type:
            parts.append(str(beacon_type[3]) if len(beacon_type) >= 4 and beacon_type[3] else str(beacon_type[2]))

        return " | ".join([p for p in parts if p])

    # 业务标识（应用层）
    service_row = _find_field(table_data, "业务标识")
    if service_row:
        msdu_row = _find_field(table_data, "MSDU类型")
        msdu = str(msdu_row[3]) if msdu_row and len(msdu_row) >= 4 else ""
        frame_type_row = _find_field(table_data, "帧类型")
        ft = str(frame_type_row[3]) if frame_type_row and len(frame_type_row) >= 4 else ""
        svc = str(service_row[3]) if len(service_row) >= 4 and service_row[3] else str(service_row[2])
        dir_row = _find_field(table_data, "传输方向")
        direction = str(dir_row[3]) if dir_row and len(dir_row) >= 4 else ""

        core = extract_csg_core_content(table_data)
        parts = [p for p in [msdu, ft, f"业务标识:{svc}", direction, core] if p]
        return " | ".join(parts)

    # 兜底：取前 4 个非冗余字段
    parts = []
    for row in table_data[:8]:
        if len(row) >= 4 and row[0] and row[3]:
            field_name = str(row[0]).strip()
            if field_name not in ("原始值", "解析值", "说明") and len(parts) < 4:
                parts.append(str(row[3]))
    return "; ".join(parts) if parts else (str(table_data[0][0]) if table_data[0] else "空")


def extract_csg_core_content(table_data: List) -> str:
    """提取新一代载波核心内容"""
    # 帧类型
    frame_type_row = _find_field(table_data, "帧类型")
    if not frame_type_row:
        return ""
    ft_val = str(frame_type_row[2]) if len(frame_type_row) >= 3 else ""

    # 否认帧：否认原因
    if "否认" in str(frame_type_row[3]) if len(frame_type_row) >= 4 else False:
        reason_row = _find_field(table_data, "否认原因")
        if reason_row:
            return f"原因:{reason_row[3] if len(reason_row) >= 4 else reason_row[2]}"

    # 确认帧
    if "确认" in str(frame_type_row[3]) if len(frame_type_row) >= 4 else False:
        return "确认报文"

    # 数据传输帧
    if "数据传输" in str(frame_type_row[3]) if len(frame_type_row) >= 4 else False:
        src = _find_field(table_data, "源地址")
        dst = _find_field(table_data, "目的地址")
        data_len = _find_field(table_data, "数据长度")
        parts = []
        if src:
            parts.append(f"源:{src[2]}")
        if dst:
            parts.append(f"目的:{dst[2]}")
        if data_len:
            parts.append(f"长度:{data_len[2]}")
        return ", ".join(parts)

    # 命令帧
    if "命令" in str(frame_type_row[3]) if len(frame_type_row) >= 4 else False:
        cmd_row = _find_field(table_data, "命令标识")
        dev_addr = _find_field(table_data, "设备地址")
        parts = []
        if cmd_row:
            parts.append(str(cmd_row[3]) if len(cmd_row) >= 4 and cmd_row[3] else str(cmd_row[2]))
        if dev_addr:
            parts.append(f"设备:{dev_addr[2]}")
        # 取几个参数字段
        count = 0
        for row in table_data:
            if len(row) >= 4 and row[0] and row[3]:
                name = str(row[0]).strip()
                if name and "保留" not in name and "控制域" not in name and "业务" not in name:
                    if count >= 4:
                        break
                    parts.append(f"{name}:{row[3]}")
                    count += 1
        return ", ".join(parts)

    return ""


def get_hdc10_summary(table_data: List) -> str:
    """HDC 1.0 双模互联互通摘要提取"""
    if not table_data:
        return "空"

    first_field = str(table_data[0][0]) if table_data[0] else ""
    if "❌" in first_field or "失败" in first_field:
        return str(table_data[0][3]) if len(table_data[0]) >= 4 else "解析失败"

    parts = []

    # 定界符类型（物理层帧）
    delim_row = _find_field(table_data, "定界符类型")
    if delim_row:
        delim_name = str(delim_row[3]) if len(delim_row) >= 4 and delim_row[3] else str(delim_row[2])
        parts.append(delim_name)

    # 信标帧：信标类型
    if delim_row and "信标" in (str(delim_row[3]) if len(delim_row) >= 4 else ""):
        beacon_type = _find_field(table_data, "信标类型")
        if beacon_type:
            parts.append(str(beacon_type[3]) if len(beacon_type) >= 4 and beacon_type[3] else str(beacon_type[2]))

    # MSDU 类型（MAC 帧）
    msdu_row = _find_field(table_data, "MSDU类型")
    if msdu_row:
        msdu = str(msdu_row[3]) if len(msdu_row) >= 4 and msdu_row[3] else str(msdu_row[2])
        parts.append(msdu)

    # 网络管理消息（MME）
    mmtype_row = _find_field(table_data, "MMTYPE")
    if mmtype_row:
        name = str(mmtype_row[3]) if len(mmtype_row) >= 4 and mmtype_row[3] else str(mmtype_row[2])
        parts.append(f"MME:{name}")

    # 应用层报文：端口号 + 报文ID + 业务类型ID
    port_row = _find_field(table_data, "报文端口号")
    if port_row:
        port = str(port_row[3]) if len(port_row) >= 4 and port_row[3] else str(port_row[2])
        parts.append(f"端口:{port}")
    msg_id_row = _find_field(table_data, "报文ID")
    if msg_id_row:
        name = str(msg_id_row[3]) if len(msg_id_row) >= 4 and msg_id_row[3] else str(msg_id_row[2])
        parts.append(f"报文ID:{name}")
    biz_row = _find_field(table_data, "业务类型ID")
    if biz_row:
        biz = str(biz_row[3]) if len(biz_row) >= 4 and biz_row[3] else str(biz_row[2])
        parts.append(f"业务:{biz}")
    proto_row = _find_field(table_data, "转发数据规约类型")
    if proto_row:
        proto = str(proto_row[3]) if len(proto_row) >= 4 and proto_row[3] else str(proto_row[2])
        parts.append(proto)

    # 兜底：取前几个非冗余字段
    if not parts:
        for row in table_data[:8]:
            if len(row) >= 4 and row[0] and row[3]:
                field_name = str(row[0]).strip()
                if field_name not in ("原始值", "解析值", "说明") and len(parts) < 4:
                    parts.append(str(row[3]))
    return " | ".join([p for p in parts if p]) if parts else (str(table_data[0][0]) if table_data[0] else "空")


def get_frame_summary(table_data: List, protocol_index: int) -> str:
    """统一摘要提取入口"""
    if not table_data:
        return "空"

    if protocol_index in (9, 10):
        return get_csg_new_gen_summary(table_data)

    if protocol_index == 11:
        return get_hdc10_summary(table_data)

    # 其他协议：找 AFN/帧类型/功能码/业务标识 字段
    for row in table_data:
        if len(row) >= 4 and row[0]:
            field = str(row[0])
            if any(k in field for k in ("AFN", "帧类型", "业务标识", "功能码", "命令字")):
                return str(row[3]) if row[3] else str(row[2])

    # 兜底
    for row in table_data[:3]:
        if len(row) >= 4 and row[3]:
            return str(row[3])
    return str(table_data[0][0]) if table_data[0] else "空"


# ═══════════════════════════════════════════════════════════════
# 报文工具函数
# ═══════════════════════════════════════════════════════════════

def _parse_hex(text: str) -> List[int]:
    """从文本中解析字节列表，容忍空格/逗号/0x前缀"""
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
    if len(cleaned) % 2 != 0:
        cleaned = cleaned[:-1]
    return [int(cleaned[i:i+2], 16) for i in range(0, len(cleaned), 2)]


def _bytes_to_hex(data: List[int], sep: str = " ") -> str:
    """字节列表转空格分隔 HEX"""
    return sep.join(f"{b:02X}" for b in data)


def tool_byte_reverse(text: str) -> str:
    """按字节倒序"""
    data = _parse_hex(text)
    data.reverse()
    return _bytes_to_hex(data)


def tool_byte_normal(text: str) -> str:
    """字节正序（格式化输出）"""
    data = _parse_hex(text)
    return _bytes_to_hex(data)


def tool_hex_add_33(text: str) -> str:
    """每字节 +0x33"""
    data = _parse_hex(text)
    return _bytes_to_hex([(b + 0x33) & 0xFF for b in data])


def tool_hex_sub_33(text: str) -> str:
    """每字节 -0x33"""
    data = _parse_hex(text)
    return _bytes_to_hex([(b - 0x33) & 0xFF for b in data])


def tool_reverse_add_33(text: str) -> str:
    """倒序 + 0x33"""
    data = _parse_hex(text)
    data.reverse()
    return _bytes_to_hex([(b + 0x33) & 0xFF for b in data])


def tool_reverse_sub_33(text: str) -> str:
    """倒序 - 0x33"""
    data = _parse_hex(text)
    data.reverse()
    return _bytes_to_hex([(b - 0x33) & 0xFF for b in data])


def tool_hex_to_ascii(text: str) -> str:
    """HEX 转 ASCII，不可打印字符显示为 ."""
    data = _parse_hex(text)
    chars = []
    for b in data:
        if 32 <= b < 127:
            chars.append(chr(b))
        else:
            chars.append('.')
    return ''.join(chars)


def tool_ascii_to_hex(text: str) -> str:
    """ASCII 转 HEX"""
    return _bytes_to_hex([ord(c) & 0xFF for c in text])


def tool_byte_length(text: str) -> str:
    """字节长度"""
    data = _parse_hex(text)
    return f"{len(data)} 字节 (0x{len(data):02X})"


def tool_char_count(text: str) -> str:
    """字符个数"""
    return f"{len(text)} 个字符"


def tool_to_upper(text: str) -> str:
    """转大写"""
    return text.upper()


def tool_to_lower(text: str) -> str:
    """转小写"""
    return text.lower()


def tool_remove_spaces(text: str) -> str:
    """去所有空白"""
    return re.sub(r'\s+', '', text)


def tool_add_spaces(text: str) -> str:
    """字节间加空格"""
    data = _parse_hex(text)
    return _bytes_to_hex(data)


def tool_msg_to_pn(text: str) -> str:
    """报文转 Pn（每字节 -0x33）"""
    return tool_hex_sub_33(text)


def tool_pn_to_msg(text: str) -> str:
    """Pn 转报文（每字节 +0x33）"""
    return tool_hex_add_33(text)


def tool_msg_to_fn(text: str) -> str:
    """报文转 Fn（每字节 -0x33）"""
    return tool_hex_sub_33(text)


def tool_fn_to_msg(text: str) -> str:
    """Fn 转报文（每字节 +0x33）"""
    return tool_hex_add_33(text)


def tool_checksum8(text: str) -> str:
    """8 位累加和校验"""
    data = _parse_hex(text)
    cs = sum(data) & 0xFF
    return f"0x{cs:02X}\n十进制: {cs}"


def tool_hex_to_bitstring(text: str) -> str:
    """HEX 转 bitstring"""
    data = _parse_hex(text)
    return " ".join(f"{b:08b}" for b in data)


def tool_bitstring_to_hex(text: str) -> str:
    """bitstring 转 HEX"""
    cleaned = re.sub(r'[^01]', '', text)
    # 补零对齐到字节
    while len(cleaned) % 8 != 0:
        cleaned = '0' + cleaned
    data = []
    for i in range(0, len(cleaned), 8):
        data.append(int(cleaned[i:i+8], 2))
    return _bytes_to_hex(data)


def tool_crc16_698(text: str) -> str:
    """CRC-16 (698.45, X-25 算法)"""
    try:
        import crcmod
        data = bytes(_parse_hex(text))
        crc_func = crcmod.predefined.Crc('x-25')
        crc_func.update(data)
        crc_val = crc_func.crcValue
        low_byte = crc_val & 0xFF
        high_byte = (crc_val >> 8) & 0xFF
        return (
            f"CRC值: 0x{crc_val:04X}\n"
            f"低字节在前: {low_byte:02X} {high_byte:02X}\n"
            f"高字节在前: {high_byte:02X} {low_byte:02X}"
        )
    except ImportError:
        return "错误: 未安装 crcmod 库"
    except Exception as e:
        return f"错误: {e}"


def tool_crc32_newgen(text: str) -> str:
    """CRC-32 (新一代载波, IEEE 802.3)"""
    try:
        import crcmod
        data = bytes(_parse_hex(text))
        crc_func = crcmod.predefined.Crc('crc-32')
        crc_func.update(data)
        crc_val = crc_func.crcValue
        # 小端
        le = bytes([
            crc_val & 0xFF,
            (crc_val >> 8) & 0xFF,
            (crc_val >> 16) & 0xFF,
            (crc_val >> 24) & 0xFF,
        ])
        # 大端
        be = bytes([
            (crc_val >> 24) & 0xFF,
            (crc_val >> 16) & 0xFF,
            (crc_val >> 8) & 0xFF,
            crc_val & 0xFF,
        ])
        return (
            f"CRC值: 0x{crc_val:08X}\n"
            f"小端: {le.hex().upper()}\n"
            f"大端: {be.hex().upper()}"
        )
    except ImportError:
        return "错误: 未安装 crcmod 库"
    except Exception as e:
        return f"错误: {e}"


def tool_crc24_newgen(text: str) -> str:
    """CRC-24 (新一代载波, 多项式 0x1800063)"""
    try:
        import crcmod
        data = bytes(_parse_hex(text))
        # CRC-24 多项式: x^24 + x^23 + x^6 + x + 1 → 0x1800063
        crc_func = crcmod.Crc(0x1800063, initCrc=0, rev=False, xorOut=0)
        crc_func.update(data)
        crc_val = crc_func.crcValue & 0xFFFFFF
        # 小端（3字节）
        le = bytes([
            crc_val & 0xFF,
            (crc_val >> 8) & 0xFF,
            (crc_val >> 16) & 0xFF,
        ])
        # 大端
        be = bytes([
            (crc_val >> 16) & 0xFF,
            (crc_val >> 8) & 0xFF,
            crc_val & 0xFF,
        ])
        return (
            f"CRC值: 0x{crc_val:06X}\n"
            f"小端: {le.hex().upper()}\n"
            f"大端: {be.hex().upper()}"
        )
    except ImportError:
        return "错误: 未安装 crcmod 库"
    except Exception as e:
        return f"错误: {e}"


def tool_hex_to_decimal(text: str, little_endian: bool = True) -> str:
    """HEX 转十进制（支持大端/小端）"""
    data = _parse_hex(text)
    if not data:
        return "错误: 无有效 HEX 数据"
    value = int.from_bytes(bytes(data), 'little' if little_endian else 'big')
    return (
        f"十进制: {value}\n"
        f"十六进制: 0x{value:X}\n"
        f"字节序: {'小端(低字节在前)' if little_endian else '大端(高字节在前)'}")


# 工具定义（供 UI 层使用）
TOOL_GROUPS = [
    {
        "name": "基础转换",
        "tools": [
            ("字节正序", "byte_normal", "格式化HEX输出"),
            ("按字节倒序", "byte_reverse", "反转字节顺序"),
            ("HEX→ASCII", "hex_to_ascii", "十六进制转可读字符"),
            ("ASCII→HEX", "ascii_to_hex", "文本转十六进制"),
            ("HEX→bitstring", "hex_to_bitstring", "转二进制位串"),
            ("bitstring→HEX", "bitstring_to_hex", "位串转十六进制"),
            ("转大写", "to_upper", "全部转大写"),
            ("转小写", "to_lower", "全部转小写"),
            ("去空格", "remove_spaces", "去除所有空白字符"),
            ("加空格", "add_spaces", "字节间插入空格"),
        ],
    },
    {
        "name": "DLT645 偏移",
        "tools": [
            ("+0x33H", "hex_add_33", "每字节加0x33（DLT645编码）"),
            ("-0x33H", "hex_sub_33", "每字节减0x33（DLT645解码）"),
            ("倒序+0x33H", "reverse_add_33", "先倒序再加0x33"),
            ("倒序-0x33H", "reverse_sub_33", "先倒序再减0x33"),
            ("报文转Pn", "msg_to_pn", "报文转Pn格式（减0x33）"),
            ("Pn转报文", "pn_to_msg", "Pn转报文（加0x33）"),
            ("报文转Fn", "msg_to_fn", "报文转Fn格式（减0x33）"),
            ("Fn转报文", "fn_to_msg", "Fn转报文（加0x33）"),
        ],
    },
    {
        "name": "统计与校验",
        "tools": [
            ("字节长度", "byte_length", "统计字节数"),
            ("字符个数", "char_count", "统计字符数"),
            ("和校验(8位)", "checksum8", "8位累加和校验"),
            ("CRC-16(X-25)", "crc16_698", "698.45 CRC16校验"),
            ("CRC-24", "crc24_newgen", "新一代载波CRC24"),
            ("CRC-32", "crc32_newgen", "新一代载波CRC32"),
        ],
    },
]

# 工具函数映射
TOOL_FUNCTIONS = {
    "byte_reverse": tool_byte_reverse,
    "byte_normal": tool_byte_normal,
    "hex_add_33": tool_hex_add_33,
    "hex_sub_33": tool_hex_sub_33,
    "reverse_add_33": tool_reverse_add_33,
    "reverse_sub_33": tool_reverse_sub_33,
    "hex_to_ascii": tool_hex_to_ascii,
    "ascii_to_hex": tool_ascii_to_hex,
    "byte_length": tool_byte_length,
    "char_count": tool_char_count,
    "to_upper": tool_to_upper,
    "to_lower": tool_to_lower,
    "remove_spaces": tool_remove_spaces,
    "add_spaces": tool_add_spaces,
    "msg_to_pn": tool_msg_to_pn,
    "pn_to_msg": tool_pn_to_msg,
    "msg_to_fn": tool_msg_to_fn,
    "fn_to_msg": tool_fn_to_msg,
    "checksum8": tool_checksum8,
    "hex_to_bitstring": tool_hex_to_bitstring,
    "bitstring_to_hex": tool_bitstring_to_hex,
    "crc16_698": tool_crc16_698,
    "crc24_newgen": tool_crc24_newgen,
    "crc32_newgen": tool_crc32_newgen,
}


def run_tool(tool_id: str, input_text: str) -> str:
    """执行工具函数"""
    func = TOOL_FUNCTIONS.get(tool_id)
    if func is None:
        return f"未知工具: {tool_id}"
    try:
        return func(input_text)
    except Exception as e:
        return f"执行失败: {e}"


# ═══════════════════════════════════════════════════════════════
# 批量结果导出
# ═══════════════════════════════════════════════════════════════

def _result_row_to_dict(item: Dict[str, Any]) -> Dict[str, Any]:
    """将批量结果条目转换为可序列化 dict"""
    return {
        "序号": (item.get("id", 0) or 0) + 1,
        "状态": item.get("status", ""),
        "长度(字节)": item.get("len", 0),
        "摘要": item.get("proto", ""),
        "帧(HEX)": (item.get("frame_bytes") or b"").hex().upper() if item.get("frame_bytes") else "",
        "字段数": len(item.get("result", []) or []),
        "字段详情": [
            {
                "字段": str(r[0]) if len(r) >= 1 else "",
                "原始值": str(r[1]) if len(r) >= 2 else "",
                "解析值": str(r[2]) if len(r) >= 3 else "",
                "说明": str(r[3]) if len(r) >= 4 else "",
            }
            for r in (item.get("result", []) or []) if r
        ],
    }


def export_frames_to_json(batch_results: List[Dict[str, Any]]) -> str:
    """批量结果 → JSON 字符串"""
    import json
    data = [_result_row_to_dict(item) for item in batch_results]
    return json.dumps(data, ensure_ascii=False, indent=2)


def export_frames_to_csv(batch_results: List[Dict[str, Any]]) -> str:
    """批量结果 → CSV 字符串（UTF-8 BOM，Excel 可直接打开）"""
    import csv
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["序号", "状态", "长度(字节)", "摘要", "帧(HEX)", "字段数"])
    for item in batch_results:
        writer.writerow([
            (item.get("id", 0) or 0) + 1,
            item.get("status", ""),
            item.get("len", 0),
            item.get("proto", ""),
            (item.get("frame_bytes") or b"").hex().upper() if item.get("frame_bytes") else "",
            len(item.get("result", []) or []),
        ])
    return "\ufeff" + buf.getvalue()
