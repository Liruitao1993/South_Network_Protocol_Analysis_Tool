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
from typing import Any, Optional

# 确保项目根目录在路径中
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# 桌面/Web 共用批量核心：测试类报文摘要片段（协议9 表61 / 协议10 检测扩展命令）
# 必须放在 sys.path 注入之后（batch_core 在仓库根目录）
from batch_core import TEST_MODE_SENTINELS, extract_test_mode_content  # noqa: E402

# 协议13（依瓦定制645）批量提取：**单一来源** = 桌面线格式模块 yw645_wire，
# 严禁在 Web 侧复刻 hex 游标提取逻辑（AGENTS 陷阱 31/55/61 的同一个教训）。
from yw645_wire import extract_yw645_frames  # noqa: E402


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


def hex_to_bytes_strict(text: str) -> bytes:
    """清洗 hex 并转 bytes；奇数长度/空输入直接报错（不静默截断）。

    与桌面 main_gui._clean_hex_input + 奇数长度弹窗（main_gui.py:5307-5311）同口径：
    输入少一个字符时必须让用户看到错误，而不是把半字节砍掉后解析出另一帧。
    """
    cleaned = clean_hex_input(text)
    if not cleaned:
        raise ValueError("报文为空")
    if len(cleaned) % 2 != 0:
        raise ValueError("输入长度为奇数，十六进制字符串必须是偶数长度！")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as e:  # 与桌面同文案前缀
        raise ValueError(f"十六进制格式错误: {e}")


def strip_frame_bytes(frame_bytes: bytes, head: int, tail: int) -> bytes:
    """剔除报文头/尾指定字节数（协议9/10 的「剔除前/尾」）。

    纯函数：同一输入恒定得到同一输出。调用方每次用**原始**输入重新计算，
    因此重复点击解析不会二次裁剪（桌面用「回写输入框 + 缓存键」达到同一效果，
    main_gui.py:5322-5346；Web 不回写输入框，改用纯粹重算，等价且不打断编辑）。
    """
    if head <= 0 and tail <= 0:
        return frame_bytes
    total = len(frame_bytes)
    tail_end = total - tail if tail > 0 else total
    if head >= tail_end:
        raise ValueError(f"剔除字节数过多（前{head}+尾{tail}），超出总长{total}")
    return frame_bytes[head:tail_end]


def batch_frame_outcome(rows, ok_type_name: str) -> tuple:
    """批量解析单帧结果 → (status, 类型列, 摘要列)。

    规则（与桌面口径统一，桌面见 main_gui.py:7516-7530 与 _get_frame_type_name:9766-9772）：
      - 空表 → 失败（解析器未产出任何字段）
      - 结果表中存在字段名以 "❌" 开头的行 → 失败（失败行可能写在**表中途**，
        如协议9 mac_only：csg_new_gen_parser.py:843 先写「解析模式」行，
        `_parse_mac_frame` 再追加 ❌ —— 只看首行会误判成功）
      - 其余 → 成功，类型/摘要列由调用方给出的 ok_type_name 填充
    """
    if not rows:
        return "失败", "解析失败", "解析无结果（未产出字段）"
    for item in rows:
        if item and str(item[0]).startswith("❌"):
            reason = str(item[3]) if len(item) >= 4 and item[3] else "解析失败"
            return "失败", "解析失败", reason
    return "成功", ok_type_name, ok_type_name


def parse_kwargs_for(protocol_index: int, parse_level: str = "auto",
                     pb_frame_type: str = "sof", gw_frame_type: int = 1,
                     channel: str = "plc") -> dict:
    """按协议构造 parse_to_table 的解析级别相关 kwargs（单帧与批量共用）。

    - 协议9：parse_level + channel + pb_frame_type（pb 帧类型在 mac_only/pb_only 有意义）
    - 协议10/11：parse_level + channel，仅 pb_only 下发 frame_type
      （gw_new_gen_parser.py:159/231-241 无 frame_type 会落「未知帧类型」；
       hdc10_parser.py:261 缺省恒 SOF）
    - 其余协议：无附加参数
    """
    if protocol_index == 9:
        return {
            "parse_level": parse_level,
            "channel": channel,
            "pb_frame_type": pb_frame_type,
        }
    if protocol_index in (10, 11):
        kwargs = {"parse_level": parse_level, "channel": channel}
        if parse_level == "pb_only":
            kwargs["frame_type"] = gw_frame_type
        return kwargs
    return {}


def _as_int(value, default: int = 0) -> int:
    """容错整数转换。

    Web State 里的值可能来自前端 JSON（字符串/None），直接 int() 会抛 ValueError 并
    中断整页渲染；这里统一回落默认值。正常路径（int 入参）行为与 int() 完全一致。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# 批量摘要状态筛选：下拉值 → 结果表状态字面量
BATCH_STATUS_FILTERS = (
    ("all", "全部"),
    ("success", "成功"),
    ("fail", "失败"),
    ("error", "异常"),
)
_STATUS_BY_KEY = dict(BATCH_STATUS_FILTERS[1:])


def filter_batch_summaries(summaries: list, keyword: str = "", status: str = "all") -> list:
    """批量摘要过滤（与桌面 `_on_batch_filter_changed` 同口径）。

    - 状态：all / success(成功) / fail(失败) / error(异常)
    - 关键词：大小写不敏感，匹配 **摘要 + 协议类型 + 帧 HEX + 序号(#N)**
      （桌面即「摘要 + 协议/类型 + 原始HEX」，这里多给 #N 便于按序号定位）
    """
    kw = (keyword or "").strip().lower()
    want = _STATUS_BY_KEY.get(status)
    out = []
    for row in summaries or []:
        if want and row.get("status") != want:
            continue
        if kw:
            hay = " ".join(
                (
                    str(row.get("summary", "")),
                    str(row.get("proto", "")),
                    str(row.get("hex", "")),
                    "#" + str(_as_int(row.get("id", 0)) + 1),
                )
            ).lower()
            if kw not in hay:
                continue
        out.append(row)
    return out


def paginate(items: list, page: int, page_size: int) -> tuple:
    """列表分页 → (当前页切片, 总页数)。

    - `page` 越界自动夹取到 [0, page_count-1]（翻页按钮不传非法值时也不会空屏）
    - 空列表 → ([], 1)
    - `page_size <= 0` 视为 1
    用途：批量摘要只把「当前页」放进 Reflex State，避免整个结果集经 WebSocket 下发。
    """
    if page_size is None or page_size <= 0:
        page_size = 1
    total = len(items or [])
    page_count = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(_as_int(page or 0), page_count - 1))
    start = page * page_size
    return (items or [])[start:start + page_size], page_count


def page_of(page: int, page_count: int) -> int:
    """把页码夹取到合法范围（与 paginate 同一规则，供 State 单独校正页码用）。"""
    if page_count <= 0:
        return 0
    return max(0, min(_as_int(page or 0), page_count - 1))


# ═══════════════════════════════════════════════════════════════
# 解析级别 / 物理块帧类型选项（UI 与逻辑共用单一来源）
# ═══════════════════════════════════════════════════════════════

# 协议9 解析级别（与桌面 main_gui.py:1446-1452 同集合，含 mac_only）
CSG_PARSE_LEVEL_OPTIONS = [
    {"label": "自动识别", "value": "auto"},
    {"label": "FC+PB解析(完整MPDU)", "value": "fc_pb"},
    {"label": "FC+eFC解析", "value": "fc_efc"},
    {"label": "仅FC解析", "value": "fc_only"},
    {"label": "仅物理块PB", "value": "pb_only"},
    {"label": "仅MAC帧", "value": "mac_only"},
    {"label": "应用层报文", "value": "app"},
]

# 协议10/11 解析级别（与桌面 main_gui.py:1535-1543 同集合）
GW_PARSE_LEVEL_OPTIONS = [
    {"label": "自动识别", "value": "auto"},
    {"label": "FC+PB解析(完整MPDU)", "value": "fc_pb"},
    {"label": "仅FC解析", "value": "fc_only"},
    {"label": "仅MAC帧", "value": "mac_only"},
    {"label": "仅物理块PB", "value": "pb_only"},
    {"label": "FC+MAC头", "value": "fc_mac"},
    {"label": "应用层报文", "value": "app"},
]

# 物理块帧类型：协议9 用 sof/beacon/sack/net（csg_new_gen_parser.py:800），
# 协议10/11 用 1/0/2/3（gw_new_gen_parser.py:234），语义一致：0=信标 1=SOF 2=SACK 3=NET
CSG_PB_FRAME_TYPE_OPTIONS = [
    {"label": "SOF帧", "value": "sof"},
    {"label": "信标帧", "value": "beacon"},
    {"label": "选择确认帧", "value": "sack"},
    {"label": "网间协调帧", "value": "net"},
]

GW_PB_FRAME_TYPE_OPTIONS = [
    {"label": "SOF帧", "value": "1"},
    {"label": "信标帧", "value": "0"},
    {"label": "选择确认帧(SACK)", "value": "2"},
    {"label": "网间协调帧(NET)", "value": "3"},
]


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

        # PLC2.0/测试装置 ED..EE 包装帧交给 CSGNewGenParser 统一解析；
        # 不能按 FC 起始特征扫描，否则控制类 ED 数据会被整行丢弃。
        if hex_clean.startswith("ED"):
            out_lines.append(hex_clean)
            continue

        if parse_level in ("pb_only", "mac_only"):
            # 输入即物理块 / MAC 帧（界面已按层级提示），无 FC 可扫 → 直接保留
            # （桌面 _strip_csg_new_gen_frame_prefix 同口径，main_gui.py:4942）
            pass
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
            # 台体工装板/功能驱动板控制帧（FE×n + 05 …，功能驱动板以 AA 0D 0A 结尾）：
            # 不是载波 FC/PB 业务帧、没有 FC 起始签名，但它**是**能被解析器完整识别的帧
            # （parse_to_table 优先判它）⇒ 原样保留；否则会被下面的 FC 扫描整行丢弃，
            # 现场表现为「同一帧单帧解析正常、批量却报『预处理后未保留有效报文内容！』」。
            # 判据复用解析器（单一来源，桌面 main_gui / 共享 batch_core 同口径）。
            from csg_new_gen_parser import is_test_device_control_frame

            if is_test_device_control_frame(hex_clean):
                out_lines.append(hex_clean)
                continue

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


# ── 国网新一代(索引10) / HDC 1.0(索引11) 应用层端口号 ─────────────────────
# 依据《双模通信互联互通技术规范 第4-3部分：应用层通信协议》§5.2.2「报文端口号」：
#   升级业务取值为 0x12，其他业务取值为 0x11；鉴权安全为 0x1A。
# 权威来源是**解析器端口表**（hdc10_parser.APP_PORTS / gw_new_gen_parser.PORT_NAMES），
# 这里只在 import 失败时回落；桌面 `main_gui._gw_app_port_prefixes` 同口径同来源。
# （AGENTS §8 陷阱 43：app 判据只认 '11' 会整批丢掉 0x12 开头的升级业务帧）
_GW_APP_PORT_PREFIXES_FALLBACK = ("11", "12", "1A")


def gw_app_port_prefixes(protocol_index: int = 10) -> tuple:
    """按协议返回应用层端口号（大写 hex 字符串）集合，取自解析器端口表。

    Args:
        protocol_index: 10=国网新一代 / 11=HDC 1.0

    Returns:
        tuple[str, ...]：如 ("11", "12", "1A")
    """
    try:
        if protocol_index == 11:
            import hdc10_parser

            ports = hdc10_parser.APP_PORTS
        else:
            import gw_new_gen_parser

            ports = gw_new_gen_parser.GWNewGenParser.PORT_NAMES
        return tuple(f"{port:02X}" for port in ports)
    except Exception:
        return _GW_APP_PORT_PREFIXES_FALLBACK


def strip_gw_new_gen_prefix(
    text: str, parse_level: str = "auto", protocol_index: int = 10
) -> str:
    """剥离国网新一代双模协议日志前缀

    - 找到最后一个冒号，其后为 hex
    - app 级别扫描应用层端口（0x11/0x12/0x1A，按 protocol_index 取解析器端口表）
      定位应用层起始

    Args:
        text: 原始日志文本（可含多行）
        parse_level: 解析级别（auto / app / pb_only / mac_only ...）
        protocol_index: 10=国网新一代 / 11=HDC 1.0（决定应用层端口集合）
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
            # ED..EE 监控包装行不参与 app 端口扫描：包装头/业务数据里偶然出现的
            # 0x11/0x12/0x1A 字节会把整帧截断（解包由 extract_frames_for_protocol 负责）。
            import batch_core
            if batch_core.ed_wrapper_prefix_len(hex_clean):
                out_lines.append(hex_clean)
                continue
            app_prefixes = gw_app_port_prefixes(protocol_index)
            found = False
            i = 0
            while i < len(hex_clean) - 1:
                if hex_clean[i:i+2] in app_prefixes and len(hex_clean) - i >= 8:
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

def extract_68_frames(clean: str) -> list[str]:
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


def extract_69845_frames(clean: str) -> list[str]:
    """提取 698.45 格式帧

    帧总长度 = L + 2（DL/T 698.45-2017 6.2.2 a：L 是不含起始/结束字符的数据长度，
    且含两个长度域字节）。标准附录 H.1.1 示例：``68 1E 00 81 … 16`` 共 32B、L=30。
    """
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
        total_len = length + 2
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


def extract_hdlc_frames(clean: str) -> list[str]:
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


def extract_wrapper_frames(text: str) -> list[str]:
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


def extract_csg_new_gen_frames(text: str) -> list[str]:
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


def extract_68_from_raw(text: str) -> list[str]:
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


def extract_generic_frames(clean: str, min_len: int = 4, max_len: int = 256) -> list[str]:
    """通用帧提取（整段 hex 作为单帧判断）

    与 GUI 版 _extract_generic_frames 行为一致：
    输入为已清洗的纯 hex 字符串，若总长度在 [min_len, max_len] 字节范围内
    且长度为偶数，则作为单帧返回，否则返回空列表。
    """
    if len(clean) >= min_len * 2 and len(clean) <= max_len * 2:
        return [clean] if len(clean) % 2 == 0 else []
    return []


def extract_frames_for_protocol(text: str, protocol_index: int) -> list[str]:
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
    elif protocol_index == 8:  # 698.45：68 开头、16 结束，帧总长 = L + 2（6.2.2 a）
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return extract_69845_frames(clean)
    elif protocol_index == 9:  # 新一代载波协议(通感一体化)：按行提取，过滤无效短帧
        return extract_csg_new_gen_frames(text)
    elif protocol_index == 13:  # 依瓦定制645：委托 yw645_wire（桌面同源，含自证式切帧）
        return extract_yw645_frames(text)
    elif protocol_index == 14:  # 南网上行通信规约：68 + L(2B 重复一次) + 68 定长切帧（桌面同源）
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        from csg_uplink_wire import extract_csg_uplink_frames
        return [f.hex().upper() for f in extract_csg_uplink_frames(bytes.fromhex(clean))]
    elif protocol_index == 10 or protocol_index == 11:  # 国网新一代双模：按行提取，每行一帧
        # ED..EE 监控包装帧先解包（可能一行拼多帧）——与桌面 batch_core 同源，
        # 否则首字节 0xED 会被当成应用层端口号解析（用户报障：协议11 ED 帧解析成
        # 「应用层报文」）。
        import batch_core
        frames = []
        for line in text.splitlines():
            f = line.strip()
            if not f or len(f) < 4:
                continue
            unwrapped = batch_core.unwrap_ed_line(f, protocol_index)
            if unwrapped is not None:
                frames.extend(frame_hex for frame_hex, _ed in unwrapped)
                continue
            frames.append(f)
        return frames
    else:
        return [f.strip() for f in text.splitlines() if f.strip()]


# ═══════════════════════════════════════════════════════════════
# 摘要提取
# ═══════════════════════════════════════════════════════════════

def _find_field(table_data: list, field_keyword: str) -> tuple | None:
    """在表格数据中查找含关键字的字段行"""
    for row in table_data:
        if len(row) >= 4 and row[0] and field_keyword in str(row[0]):
            return row
    return None


def _append_test_mode_segment(table_data: list, summary: str) -> str:
    """测试类报文摘要片段收口（与桌面 main_gui._get_gw_new_gen_summary 第 9 步同口径）。

    桌面协议10/11 的摘要入口一律经过该步；Web 侧协议10 的检测扩展命令帧（没有
    「报文端口号」/「报文ID」行）会路由到本文件的新一代载波摘要函数，因此这里
    也必须补上同一片段，否则同一帧两端摘要不一致（见任务 09-17-web-gui-parity-sync R3）。

    去重守卫：协议9 测试帧的核心内容分支已经带出该片段，此时不再重复追加。
    片段本身来自桌面/Web 共用单源 batch_core.extract_test_mode_content。
    """
    if not any(
        row and str(row[0]).strip() in TEST_MODE_SENTINELS for row in table_data
    ):
        return summary
    text = extract_test_mode_content(table_data)
    if not text or text in summary:
        return summary
    if not summary or summary == "空":
        return text
    return f"{summary} | {text}"


def get_csg_new_gen_summary(table_data: list) -> str:
    """新一代载波协议摘要提取（含测试类报文片段收口）"""
    return _append_test_mode_segment(table_data, _csg_summary_core(table_data))


def _csg_summary_core(table_data: list) -> str:
    """新一代载波协议摘要主体（不含测试模式片段收口，见 get_csg_new_gen_summary）"""
    if not table_data:
        return "空"

    # 解析失败
    first_field = str(table_data[0][0]) if table_data[0] else ""
    if "❌" in first_field or "失败" in first_field:
        return str(table_data[0][3]) if len(table_data[0]) >= 4 else "解析失败"

    # ED 包装 / 测试装置控制协议（标题含「监控包装头」；文案按标题推断）
    if "监控包装头" in first_field:
        ctrl1 = _find_field(table_data, "控制域1")
        ctrl2 = _find_field(table_data, "控制域2")
        from batch_core import ed_wrapper_display
        if "HDC" in first_field or "国网" in first_field:
            parts = [ed_wrapper_display(11, "gx")["summary_web"]]
        elif "广西" in first_field:
            parts = ["广西台体监控包装"]
        else:
            parts = ["ED监控包装"]
        if ctrl1:
            parts.append(str(ctrl1[2]))
        if ctrl2:
            parts.append(str(ctrl2[2]))
        for key in ("CCO仓模块电源状态", "STA仓模块电源位图", "工装板220V电源状态",
                    "CCO仓引脚控制", "STA仓引脚控制", "衰减器A衰减值",
                    "衰减器B衰减值", "衰减器C衰减值", "8762A连接方式"):
            row = _find_field(table_data, key)
            if row:
                parts.append(str(row[2]))
                return " | ".join(parts)
        return " | ".join(parts)

    if "测试装置" in first_field:
        cmd_row = _find_field(table_data, "命令码")
        for key in ("CCO仓模块电源状态", "STA仓模块电源位图", "工装板220V电源状态",
                    "CCO仓引脚控制", "STA仓引脚控制", "衰减器A衰减值",
                    "衰减器B衰减值", "衰减器C衰减值", "8762A连接方式"):
            row = _find_field(table_data, key)
            if row:
                return f"测试装置控制 | {cmd_row[2] if cmd_row else ''} | {row[2]}".strip(" |")
        return f"测试装置控制 | {cmd_row[2]}" if cmd_row else "测试装置控制"

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


def extract_csg_core_content(table_data: list) -> str:
    """提取新一代载波核心内容"""
    # 帧类型
    # ── 测试帧（业务标识 0xF0）：优先体现测试模式/测试ID ──
    # 与桌面 main_gui._extract_csg_core_content 的**首个分支**逐字同口径：
    # 必须放在否认/确认/命令帧分支之前，否则测试帧（帧类型域是「命令帧」）
    # 的测试模式信息会被通用命令帧分支淹没。测试模式片段来自桌面/Web 共用的
    # frame_summary.extract_test_mode_content（单源）。
    for _row in table_data:
        if not _row or str(_row[0]).strip() != "业务标识":
            continue
        _svc_raw = str(_row[1]) if len(_row) >= 2 and _row[1] is not None else ""
        _svc_val = str(_row[2]).strip() if len(_row) >= 3 and _row[2] is not None else ""
        _svc_cmt = str(_row[3]) if len(_row) >= 4 and _row[3] is not None else ""
        if _svc_val == "240" or "F0" in _svc_raw.upper() or "测试帧" in _svc_cmt:
            _mode_text = extract_test_mode_content(table_data)
            if _mode_text:
                return _mode_text
        break
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


# ══════════════════════════════════════════════════════════════
# 应用层报文摘要：业务名 + 关键业务字段（与桌面 main_gui 同规则、同口径）
#
# 为什么不复用 `_find_field`：它是**子串包含**匹配（`keyword in row[0]`），
# 会把「业务报文ID」当成「报文ID」、也拿不到业务数据区的业务名；
# 桌面 `_get_gw_new_gen_summary` 的 `val()` 是「去缩进后字段名精确相等」，
# 这里用 `_field_value` / `_field_comment` 保持同语义，两端才能逐字符对拍一致。
# 规则细节（业务名两优先级、扫描窗口、元数据黑名单、关键字段双约束）见
# main_gui._gw_app_biz_summary 注释与 AGENTS §8 陷阱 44。
_GW_APP_META_FIELDS = (
    "报文端口号",
    "报文ID",
    "安全模式",
    "安全机制",
    "业务报文ID",
    "报文控制字",
    "协议版本号",
    "报文头长度",
    "控制/保留",
    "数据长度",
    "转发数据规约类型",
    "转发数据长度",
    "报文序号",
    "规约类型",
    "发送类型",
    "MSDU类型",
    "⚠ 安全保护",
)
_GW_APP_SUMMARY_KEY_FIELDS = 2


def _field_value(table_data: list, name: str) -> str:
    """按「去缩进后字段名精确相等」取首个匹配行的解析值（与桌面 `val()` 同语义）"""
    for row in table_data:
        if len(row) >= 3 and row[0] is not None and str(row[0]).strip() == name:
            value = row[2]
            return str(value).strip() if value not in (None, "") else ""
    return ""


def _field_comment(table_data: list, name: str) -> str:
    """按「去缩进后字段名精确相等」取首个匹配行的说明（与桌面 `cmt()` 同语义）"""
    for row in table_data:
        if len(row) >= 4 and row[0] is not None and str(row[0]).strip() == name:
            value = row[3]
            return str(value).strip() if value not in (None, "") else ""
    return ""


def _gw_app_biz_summary(table_data: list) -> tuple:
    """从应用层报文表中提取 (业务名, [关键业务字段…])。规则与桌面逐字一致。

    扫描窗口：起点 = `── 业务数据` 行 +1（协议11 布局，优先）；无该区头时 = 顶层
    「应用层报文」行 +1（协议10/auto 布局）；终点 = 起点之后首个**顶层行**或表尾。
    **不能全表扫描**：真实 MPDU 在 auto/fc_pb 级别下 FC/MAC 字段（`版本`/`原始源TEI`/
    `定界符类型`/`网络类型`）排在应用层之前，会被当成业务字段。
    """
    if not table_data:
        return "", []

    def _raw_name(item):
        return str(item[0]) if item and item[0] is not None else ""

    def _name(item):
        return _raw_name(item).strip()

    def _parsed(item):
        if not item or len(item) <= 2 or item[2] in (None, ""):
            return ""
        return str(item[2]).strip()

    def _is_meta(name):
        return any(
            name == meta or name.startswith(meta) for meta in _GW_APP_META_FIELDS
        )

    def _is_skippable(name):
        return (
            not name
            or name.startswith("──")
            or name.startswith("❌")
            or name.startswith("⚠")
        )

    # ── 扫描窗口：限定在「业务数据 / 应用层报文」段内 ──
    window_start, window_end, from_biz_section = -1, -1, False
    # ① 优先：业务数据区（协议11 布局——业务名与业务字段都在区内；
    #    必须先于「应用层报文」区头检查：两个区头在同一表里按先后出现）
    for i, item in enumerate(table_data):
        if _name(item).startswith("── 业务数据"):
            window_start, from_biz_section = i + 1, True
            break
    # ② 回退：顶层「应用层报文」行（协议10/auto 布局，无业务数据区）
    if window_start < 0:
        for i, item in enumerate(table_data):
            name, raw_name = _name(item), _raw_name(item)
            if not raw_name.startswith(" ") and "应用层报文" in name:
                window_start = i + 1
                break
    if window_start < 0:
        return "", []
    for j in range(window_start, len(table_data)):
        if not _raw_name(table_data[j]).startswith(" "):  # 下一个顶层行 = 段结束
            window_end = j
            break
    window = table_data[window_start : window_end if window_end >= 0 else len(table_data)]

    # ── 业务名 ──
    biz_name = ""
    biz_row_idx = -1
    if from_biz_section:
        for k, item in enumerate(window):
            if not _raw_name(item).startswith(" ") or _is_skippable(_name(item)):
                continue
            biz_name, biz_row_idx = _name(item), window_start + k
            break
    if not biz_name:
        for item in table_data:
            if _name(item) != "报文ID":
                continue
            parsed = _parsed(item)
            if parsed and not re.fullmatch(r"(0[xX])?[0-9A-Fa-f]+", parsed):
                biz_name = parsed
            break

    # ── 关键业务字段（只在窗口内扫描）──
    fields = []
    for i, item in enumerate(window):
        raw_name = _raw_name(item)
        name, parsed = _name(item), _parsed(item)
        if window_start + i == biz_row_idx or not parsed:
            continue
        if not raw_name.startswith(" "):
            continue
        if _is_skippable(name) or _is_meta(name):
            continue
        if re.fullmatch(r"\d+字节", parsed):
            continue
        fields.append(f"{name}:{parsed}")
        if len(fields) >= _GW_APP_SUMMARY_KEY_FIELDS:
            break

    return biz_name, fields


def get_hdc10_summary(table_data: list) -> str:
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

    # 网络管理消息（MME）——字段名两协议不同构：
    # 协议10=`管理消息类型(MMTYPE)`，协议11=`消息类型(MMTYPE)`；子串匹配两者均可命中。
    # pb_only 批量时网络层帧必须带出 MMTYPE，否则摘要无法区分关联请求/发现列表等。
    mmtype_row = _find_field(table_data, "MMTYPE")
    if mmtype_row:
        code = str(mmtype_row[2]).strip() if len(mmtype_row) >= 3 and mmtype_row[2] else ""
        name = str(mmtype_row[3]).strip() if len(mmtype_row) >= 4 and mmtype_row[3] else code
        if name.startswith("MMTYPE:"):
            name = name[7:].strip()
        if code and name and code not in name:
            parts.append(f"MMTYPE:{code}({name})")
        elif name:
            parts.append(f"MMTYPE:{name}")

    # 网络层 MAC 字段：与桌面 `_get_gw_new_gen_summary` 同口径，便于 pb_only 批量扫读
    src = _field_value(table_data, "原始源TEI") or _field_value(table_data, "源TEI")
    dst = _field_value(table_data, "原始目的TEI") or _field_value(table_data, "目的TEI")
    if src or dst:
        tei_txt = f"{src or '?'}→{dst or '?'}"
        if tei_txt not in " | ".join(parts):
            parts.append(tei_txt)
    seq = _field_value(table_data, "MSDU序列号")
    if seq:
        parts.append(f"msduSeq:{seq}")
    send_cmt = _field_comment(table_data, "发送类型")
    if send_cmt and "保留" not in send_cmt and send_cmt not in " | ".join(parts):
        parts.append(send_cmt)

    # 应用层报文：端口号 + 报文ID(含方向) + 业务名 + 关键业务字段 + 序号/规约/数据长度
    # （与桌面 `main_gui._get_gw_new_gen_summary` 逐段同口径；对拍见
    #   test/test_gw_app_summary_detail.py。原实现取 comment 整句，
    #   会得到 `端口:升级业务`、`报文ID:安全模式: …`，与桌面不一致）
    port = _field_value(table_data, "报文端口号")
    if port:
        parts.append(f"端口:{port}")
    msg_id = _field_value(table_data, "报文ID")
    if msg_id:
        app_cmt = _field_comment(table_data, "应用层报文")
        direction = ""
        for d in ("下行", "上行"):
            if d in app_cmt:
                direction = d
                break
        parts.append(f"报文:{msg_id}({direction})" if direction else f"报文:{msg_id}")
    # 仅应用层报文（端口号/报文ID 解析值非空）才提取业务段：网络层/物理层帧没有业务语义
    if port or msg_id:
        biz_name, biz_fields = _gw_app_biz_summary(table_data)
        if biz_name and biz_name != msg_id and biz_name not in " | ".join(parts):
            parts.append(biz_name)
        parts.extend(biz_fields)
    msg_seq = _field_value(table_data, "报文序号")
    if msg_seq:
        parts.append(f"序号:{msg_seq}")
    rule_type = _field_value(table_data, "规约类型")
    if rule_type:
        parts.append(f"规约:{rule_type.replace('DL/T ', '')}")
    data_len = _field_value(table_data, "转发数据长度")
    if data_len:
        parts.append(f"数据:{data_len}")

    # 测试类报文（通信测试/检测扩展命令）：体现测试模式/配置操作
    # 与桌面 main_gui._get_gw_new_gen_summary 第 9 步同口径：仅在三个哨兵行
    # 之一存在时才调用（协议10 无 0xF0 概念，避免 helper 对同名字段误提取），
    # 片段来自桌面/Web 共用的 frame_summary.extract_test_mode_content（单源）。
    if any(
        str(row[0]).strip() in TEST_MODE_SENTINELS for row in table_data if row
    ):
        test_mode_text = extract_test_mode_content(table_data)
        if test_mode_text:
            parts.append(test_mode_text)

    # 兜底：取前几个非冗余字段
    if not parts:
        for row in table_data[:8]:
            if len(row) >= 4 and row[0] and row[3]:
                field_name = str(row[0]).strip()
                if field_name not in ("原始值", "解析值", "说明") and len(parts) < 4:
                    parts.append(str(row[3]))
    return " | ".join([p for p in parts if p]) if parts else (str(table_data[0][0]) if table_data[0] else "空")


def get_frame_summary(
    table_data: list, protocol_index: int, frame_bytes: Optional[bytes] = None
) -> str:
    """统一摘要提取入口。

    ``frame_bytes``（可选）：协议13（依瓦定制645）的摘要**单一来源**是解析器的
    ``YW645Parser.get_summary(frame)``，需要原始帧字节；批量链路（``parse_batch``）
    会传入。其余协议忽略该参数（保持既有 2 参调用兼容）。
    """
    if not table_data:
        return "空"

    # 测试装置（工装板/功能驱动板）控制帧：核心内容是**命令专属解析值**（衰减器X衰减值 /
    # CCO·STA 仓电源与引脚 / 220V 状态），与桌面 `_get_csg_new_gen_summary` 同走
    # `batch_core.test_device_summary` 单源实现（非该类报文返回空串，直接落回下方分派）。
    from batch_core import test_device_summary

    device_summary = test_device_summary(table_data)
    if device_summary:
        return device_summary

    if protocol_index == 13:
        # 依瓦定制645：摘要委托解析器 get_summary（**不在 Web 侧另写字段拼接**）。
        # 未传帧字节时（仅非常规调用/测试）落回下方通用兜底，避免复制第二份实现。
        if frame_bytes:
            from yw645_parser import YW645Parser

            return YW645Parser().get_summary(frame_bytes)

    if protocol_index == 9:
        return get_csg_new_gen_summary(table_data)

    if protocol_index == 11:
        return get_hdc10_summary(table_data)

    # 协议10（国网新一代）：**应用层报文**（本任务增强范围）走与协议11 同一实现
    # （两协议应用层字段同构）；物理层/网络层帧保持既有行为——它们原先走协议9
    # 摘要函数，而该函数对 TEI/发送类型等段的覆盖比 get_hdc10_summary 更全，
    # 直接整包切换会让这些摘要丢信息（复核实测 104/120 张真实表内容变化）。
    # 两端物理层段全量对齐属 09-15-web-shared-parse-core。
    if protocol_index == 10:
        if any(
            row
            and row[0] is not None
            and str(row[0]).strip() in ("报文端口号", "报文ID")
            and len(row) > 2
            and row[2] not in (None, "")
            for row in table_data
        ):
            return get_hdc10_summary(table_data)
        return get_csg_new_gen_summary(table_data)

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

def _parse_hex(text: str) -> list[int]:
    """从文本中解析字节列表，容忍空格/逗号/0x前缀"""
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
    if len(cleaned) % 2 != 0:
        cleaned = cleaned[:-1]
    return [int(cleaned[i:i+2], 16) for i in range(0, len(cleaned), 2)]


def _bytes_to_hex(data: list[int], sep: str = " ") -> str:
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
        # rev 必须与协议9/10/11 解析器及桌面报文工具一致（rev=True）：
        # csg_new_gen_parser.py:20 / gw_new_gen_parser.py:22 / hdc10_parser.py:22 /
        # message_tool_widget.py:24
        crc_func = crcmod.Crc(0x1800063, initCrc=0, rev=True, xorOut=0)
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

def _result_row_to_dict(item: dict[str, Any]) -> dict[str, Any]:
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


def export_frames_to_json(batch_results: list[dict[str, Any]]) -> str:
    """批量结果 → JSON 字符串"""
    import json
    data = [_result_row_to_dict(item) for item in batch_results]
    return json.dumps(data, ensure_ascii=False, indent=2)


def export_frames_to_csv(batch_results: list[dict[str, Any]]) -> str:
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

# ═══════════════════════════════════════════════════════════════
# 对外 URL（下载地址）—— 与主机/端口解耦
# ═══════════════════════════════════════════════════════════════
#
# 背景（1.23.14 修复）：下载地址曾用 `rx.config.get_config()` 的 frontend_port/backend_port
# 拼绝对 URL。那两个是**构建期**配置（rxconfig.py: 3000/8000），而 run_app.py 是单端口部署
# （如 8091）⇒ 地址被改写成 `host:8000` 并写进 version.json，首页「下载客户端」就跳错了。
# 现在：**对外发出去的地址只允许用「当前请求的真实 host」或「同源相对路径」**。

DOWNLOAD_ROUTE = "/download/"
DEFAULT_EXE_NAME = "南网协议解析工具.exe"


def release_download_path(exe_name: str) -> str:
    """下载路由的同源相对路径（URL 编码文件名）。"""
    from urllib.parse import quote

    name = (exe_name or "").strip() or DEFAULT_EXE_NAME
    return f"{DOWNLOAD_ROUTE}{quote(name)}"


def release_absolute_url(host: str, exe_name: str) -> str:
    """发布到 version.json 的绝对地址（GUI 客户端自动更新要用绝对地址直连）。

    `host` 为空（拿不到请求上下文）时回落相对路径——宁可不完整，也不要写一个猜来的主机端口。
    """
    path = release_download_path(exe_name)
    host = (host or "").strip()
    return f"http://{host}{path}" if host else path


def is_same_origin_serving(env: dict | None = None) -> bool:
    """当前是否「单端口同源」部署（前端静态与 API/下载路由同端口）。

    `run_app.py` 会设置 `REFLEX_ENV=prod` 与 `__REFLEX_MOUNT_FRONTEND_COMPILED_APP=true`；
    `reflex run --env dev` 下前端(3000)/后端(8000)分端口 ⇒ 不是同源，下载必须带后端主机。
    """
    e = env if env is not None else __import__("os").environ
    prod = str(e.get("REFLEX_ENV", "")).strip().lower() == "prod"
    mounted = str(e.get("__REFLEX_MOUNT_FRONTEND_COMPILED_APP", "")).strip().lower() == "true"
    return prod or mounted


def _hostname_of(url_or_host: str) -> str:
    """取主机名（忽略协议、端口、用户信息、路径）。"""
    s = (url_or_host or "").strip()
    if not s:
        return ""
    if "//" in s:
        s = s.split("//", 1)[1]
    s = s.split("/", 1)[0].split("@")[-1]
    if s.startswith("["):  # IPv6 字面量 [::1]:8091
        return s.split("]", 1)[0].lstrip("[").lower()
    return s.split(":", 1)[0].lower()


def resolve_download_target(
    stored_url: str, exe_name: str, *, host: str = "", same_origin_serving: bool = False
) -> str:
    """浏览器点击「下载客户端」时的目标地址。

    规则（按优先级）：
      1. version.json 里的地址指向**别的主机** → 原样使用（exe 托管在外部服务器，尊重管理员配置）；
      2. 同源单端口部署，或拿不到当前 host → 相对路径 `/download/<名>`
         （任意 host/port 都对；也顺带修正历史 version.json 里写死的错误端口，如 `:8000`）；
      3. 开发态（前端 3000 / 后端 8000 分端口）→ `http://<host>/download/<名>`（host 为后端）。
    """
    stored = (stored_url or "").strip()
    stored_host = _hostname_of(stored)
    current_host = _hostname_of(host)
    if stored and stored_host and current_host and stored_host != current_host:
        return stored
    path = release_download_path(exe_name)
    if same_origin_serving or not current_host:
        return path
    return f"http://{host.strip()}{path}"
