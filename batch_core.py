# -*- coding: utf-8 -*-
"""batch_core.py — 批量解析共享核心（纯逻辑，无 Qt）

**单一来源**：PySide6 桌面版（``main_gui``）与 Reflex Web 版（``reflex_web``）都调用本模块，
不再各自维护一份「预处理 / 帧提取 / 摘要 / 测试模式」实现。历史上这些逻辑被复制了
2~3 份并已发生漂移（AGENTS §8 陷阱 31：协议10 摘要误用协议9 函数、645 转表复制体
两端同错、csg app 扫描阈值 8 vs 32 等）。

五组逻辑（全部为桌面既有实现的**逐字搬移**，不顺手改逻辑）：

1. 前缀剥离 —— ``strip_csg_monitor_prefix`` / ``strip_csg_new_gen_frame_prefix`` /
   ``strip_gw_new_gen_prefix``，返回 :class:`StripResult`（文本 + 行映射）
2. 帧提取 —— ``extract_frames_for_protocol``，统一返回 ``(hex, ed_type, line_no)`` 三元组
3. ED 包装业务提取 —— ``extract_business_from_ed_frame`` / ``resolve_ed_wrapper``
4. 摘要与类型列 —— ``get_summary_from_table_data`` / ``*_summary`` / ``get_frame_type_name``
5. 测试模式片段 —— ``extract_test_mode_content``

**禁止** import PySide6 / PyQt / ``main_gui``（Web 侧会 import 本模块）。
``protocol_registry`` 与解析器模块（``csg_new_gen_parser`` 等）均为无 Qt 模块，可按需惰性 import。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import protocol_registry

# ═══════════════════════════════════════════════════════════════
# 1. 前缀剥离
# ═══════════════════════════════════════════════════════════════

# 监控日志格式: "<时间> <序号> -> 接收机 Has Get <N字节监控头> <协议报文>"
# 实际报文从标记后的第 16 个字节（1-based）开始，即需要跳过 15 字节监控头
CSG_MONITOR_PREFIX = "> 接收机 Has Get"
CSG_MONITOR_HEADER_BYTES = 15  # 标记之后需跳过的监控头字节数

# 国网新一代(索引10) / HDC 1.0(索引11) 应用层端口号
# 依据《双模通信互联互通技术规范 第4-3部分：应用层通信协议》§5.2.2「报文端口号」：
#   升级业务取值为 0x12，其他业务取值为 0x11；鉴权安全为 0x1A。
# 权威来源是**解析器端口表**（hdc10_parser.APP_PORTS / gw_new_gen_parser.PORT_NAMES），
# 这里只在 import 失败时回落，避免再出现第三份硬编码端口副本（AGENTS §8 陷阱 43）。
_GW_APP_PORT_PREFIXES_FALLBACK = ("11", "12", "1A")


@dataclass(frozen=True)
class StripResult:
    """前缀剥离结果。

    ``line_map[i]`` = 输出第 i 行原文出现在输入文本的第几行（0-based），
    供结果回跳原始日志（桌面 ``_src_line``）。
    """

    text: str
    line_map: tuple = ()


def gw_app_port_prefixes(protocol_index: int) -> tuple:
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

            ports = gw_new_gen_parser.PORT_NAMES
        return tuple(f"{port:02X}" for port in ports)
    except Exception:
        # 解析器模块不可用（打包缺失等）时回落内置三元组，不让调用方抛异常
        return _GW_APP_PORT_PREFIXES_FALLBACK


def strip_csg_monitor_prefix(text: str) -> StripResult:
    """剥离新一代载波协议监控日志前缀

    监控日志格式示例:
        15:49:51 254  -> 接收机 Has Get ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 69 19 09 ...
                                                  ^^^^^^^^^^^^^^^ 15字节监控头 ^^^^^^^^^^^^^^^^
                                                                                  ^ 第16字节(69)开始为真实协议报文

    处理规则（逐行）:
      1. 仅保留含 "> 接收机 Has Get" 标记的行，其余行（时间戳、测试标记、
         纯文本日志、空行等）全部丢弃，避免被 hex 清洗误判成伪帧
      2. 对保留的行：定位标记，取其后内容，跳过前 15 字节监控头，
         从第 16 字节开始保留作为协议报文

    注意：必须在 hex 清洗之前调用，否则标记中的中文/箭头会被清洗掉，
    导致无法定位监控头边界。
    """
    prefix = CSG_MONITOR_PREFIX
    prefix_len = len(prefix)

    out_lines = []
    out_map = []
    for line_idx, line in enumerate(text.splitlines()):
        pos = line.find(prefix)
        if pos == -1:
            # 不含监控标记的行：直接丢弃（时间戳/测试标记/纯文本日志等）
            continue
        # 标记之后的内容
        after = line[pos + prefix_len :]
        # 提取连续 hex token（容忍空格/多空格/非hex分隔符）
        tokens = re.findall(r"[0-9A-Fa-f]{1,2}", after)
        # 跳过 15 字节监控头，从第 16 字节开始保留协议报文
        payload_tokens = tokens[CSG_MONITOR_HEADER_BYTES :]
        if payload_tokens:
            out_lines.append(" ".join(payload_tokens))
            out_map.append(line_idx)
    return StripResult("\n".join(out_lines), tuple(out_map))


def _split_hex_frames_with_lines(text: str) -> list:
    """按行提取「完整 hex 帧」，支持 ``fc_payload_data := '…'`` 跨行引号包裹。

    Returns:
        list[(hex_clean, src_line_idx)]
    """
    hex_frames = []
    in_payload = False  # 是否在引号包裹的 payload 内
    payload_hex = ""  # 当前 payload 累积的 hex
    payload_start_idx = -1  # 跨行 payload 的起始行号

    for line_idx, line in enumerate(text.splitlines()):
        line_s = line.strip()
        if not line_s:
            continue

        # ── 在 payload 引号内：收集 hex 直到闭合引号 ──
        if in_payload:
            # 查找闭合引号: ' 后跟空白或 } (如 '0 3", 'O }", 'O}")
            close_match = re.search(r"'\s*[}]?", line_s)
            if close_match:
                before_close = line_s[: close_match.start()]
                payload_hex += re.sub(r"[^0-9A-Fa-f]", "", before_close).upper()
                in_payload = False
                if len(payload_hex) >= 4:
                    hex_frames.append((payload_hex, payload_start_idx))
                payload_hex = ""
            else:
                # 无闭合引号：整行都是 hex 数据（可能还有下一行）
                payload_hex += re.sub(r"[^0-9A-Fa-f]", "", line_s).upper()
            continue

        # ── 检测 payload 起始：fc_payload_data := ' 或类似的引号开启 ──
        payload_start = re.search(r"fc_payload_data\s*:=\s*['\"]", line_s)
        if payload_start:
            after_quote = line_s[payload_start.end() :]
            # 同行内是否有闭合引号？
            close_match = re.search(r"'\s*[}]?", after_quote)
            if close_match:
                hex_clean = re.sub(
                    r"[^0-9A-Fa-f]", "", after_quote[: close_match.start()]
                ).upper()
                if len(hex_clean) >= 4:
                    hex_frames.append((hex_clean, line_idx))
            else:
                # 引号跨行
                payload_hex = re.sub(r"[^0-9A-Fa-f]", "", after_quote).upper()
                in_payload = True
                payload_start_idx = line_idx
            continue

        # ── 普通行：取最后一个冒号后的 hex ──
        last_colon = line_s.rfind(":")
        hex_part = line_s[last_colon + 1 :].strip() if last_colon >= 0 else line_s
        # 若行内含引号（闭合引号残留），只取引号前
        quote_pos = -1
        for q in ("'", '"'):
            p = hex_part.find(q)
            if p >= 0 and (quote_pos < 0 or p < quote_pos):
                quote_pos = p
        if quote_pos >= 0:
            hex_clean = re.sub(r"[^0-9A-Fa-f]", "", hex_part[:quote_pos]).upper()
        else:
            hex_clean = re.sub(r"[^0-9A-Fa-f]", "", hex_part).upper()
        if len(hex_clean) >= 4:
            hex_frames.append((hex_clean, line_idx))

    # 处理尾部残留（引号未闭合的不完整帧）
    if payload_hex and len(payload_hex) >= 4:
        hex_frames.append((payload_hex, payload_start_idx))

    return hex_frames


def strip_gw_new_gen_prefix(
    text: str, parse_level: str, protocol_index: int
) -> StripResult:
    """剥离国网新一代(索引10)/HDC 1.0(索引11)双模协议日志前缀

    日志格式示例:
        Line 339: 260718-111145-349: B1D[3] mrd:ar[75]:110300000132F303420D2305683D0043...

    处理规则:
      1. 以 fc_payload_data := ' 开头，' 后跟空白或 } 结尾为一个完整帧
      2. 帧可能跨多行，中间所有 hex 拼接为一个完整帧
      3. 无引号包裹的行：取最后一个冒号后的 hex
      4. 清理非 hex 字符，若解析级别为 app 则扫描应用层端口
         (0x11/0x12/0x1A，见 :func:`gw_app_port_prefixes`) 定位应用层起始
      5. 过短（<4 hex字符）的帧丢弃

    ``parse_level`` 必须由调用方显式给出（**不要**在本模块内读控件）：
    协议10 用 ``_gw_parse_level``、协议11 用 ``_hdc10_parse_level``，两者相互独立
    但界面共用同一下拉框——早期版本硬读 ``_gw_parse_level``，于是协议11 批量解析
    被协议10 的残留级别（如 app）过滤成空（AGENTS §8 陷阱 43）。

    注意：必须在 hex 清洗之前调用，否则前缀中的数字会被误当作 hex 数据。
    """
    # app 级别的帧起始判据：应用层端口集合（按当前协议取自解析器端口表）
    app_prefixes = gw_app_port_prefixes(protocol_index)
    hex_frames = _split_hex_frames_with_lines(text)

    out_lines = []
    out_map = []
    for hex_clean, src_idx in hex_frames:
        if parse_level == "app":
            # ED..EE 监控包装行不参与 app 端口扫描：包装头/业务数据里偶然出现的
            # 0x11/0x12/0x1A 字节会把整帧截断（解包统一由 _extract_line_frames 负责）
            if ed_wrapper_prefix_len(hex_clean):
                out_lines.append(hex_clean)
                out_map.append(src_idx)
                continue
            found = False
            i = 0
            while i < len(hex_clean) - 1:
                if hex_clean[i : i + 2] in app_prefixes and len(hex_clean) - i >= 8:
                    hex_clean = hex_clean[i:]
                    found = True
                    break
                i += 2
            if not found:
                continue
        out_lines.append(hex_clean)
        out_map.append(src_idx)

    return StripResult("\n".join(out_lines), tuple(out_map))


def strip_csg_new_gen_frame_prefix(text: str, parse_level: str = "auto") -> StripResult:
    """南网新一代通感一体化批量解析预处理（在 hex 清洗之前调用）

    主动定位帧起始并剔除非报文内容，依据南网帧结构与物理块头(4字节)特征：

    - 若文本含监控日志标记 ``> 接收机 Has Get``：沿用 :func:`strip_csg_monitor_prefix`，
      仅保留监控行并剥离 15 字节监控头。
    - 否则按行处理：取最后一个冒号后的 hex（兼容 "Line XXX: ...: hex" 日志），
      清洗为纯 hex，再按解析级别定位帧起始：
        * fc_pb / fc_only / fc_efc / auto  → 扫描 FC 起始特征字节
          (bit3=接入指示=1, bits0-2=定界符类型∈{0,1,2,3}，即低4位∈{0x8,0x9,0xA,0xB})
        * pb_only  → 输入即物理块本身，直接保留整行（无FC签名）
        * app      → 扫描端口 0x11 定位应用层报文起始
        * mac_only → 输入即 MAC 帧，直接保留整行
      过短的行（<4 hex字符）直接丢弃。
    - TCP 包装报文：检测 ``EDA5`` 固定前缀，从 ``ED`` 偏移 15 字节（30 hex字符）定位 FC 起始，
      剥离 15 字节 TCP 包装头后即为 FC+PB 帧数据（适用于除 pb_only 外的所有级别）。
    """
    # 监控日志格式：沿用已有逻辑（仅保留监控行，剥离监控头）
    if CSG_MONITOR_PREFIX in text:
        return strip_csg_monitor_prefix(text)

    hex_frames = _split_hex_frames_with_lines(text)

    # 测试装置工装板/功能驱动板控制帧的判据来自解析器（单一来源，见 csg_new_gen_parser）
    from csg_new_gen_parser import is_test_device_control_frame

    out_lines = []
    out_map = []
    for hex_clean, src_idx in hex_frames:
        # 检测 TCP 包装前缀 EDA5：从 ED 偏移 15 字节(30 hex)定位 FC 起始
        if parse_level != "pb_only" and hex_clean.startswith("EDA5"):
            if len(hex_clean) >= 62:
                hex_clean = hex_clean[30:]
                out_lines.append(hex_clean)
                out_map.append(src_idx)
            continue

        if parse_level in ("pb_only", "mac_only"):
            pass  # 直接保留
        elif parse_level == "app":
            found = False
            i = 0
            # 阈值 32 hex 字符（16 字节）：与桌面 _strip_csg_new_gen_frame_prefix 同口径。
            # 曾用 `i < len-1`（8 hex），会把不足 16 字节的尾部误当帧起始。
            while i + 32 <= len(hex_clean):
                if hex_clean[i : i + 2] == "11" and len(hex_clean) - i >= 8:
                    hex_clean = hex_clean[i:]
                    found = True
                    break
                i += 2
            if not found:
                continue
        else:
            if hex_clean.startswith("ED"):
                pass  # ED 包装帧直接保留
            elif is_test_device_control_frame(hex_clean):
                # 台体工装板/功能驱动板控制帧（FE×n + 05 …，功能驱动板以 AA 0D 0A 结尾）：
                # 不是载波 FC/PB 业务帧、没有 FC 起始签名，但它**是**能被解析器完整识别的帧
                # （parse_to_table 优先判它）⇒ 必须原样保留。否则会被下面的 FC 扫描判定为
                # 「无有效起始」整行丢弃 —— 现场表现是同一帧单帧解析正常、批量却报
                # 「预处理后未保留有效报文内容！」（1.23.87 修）。
                pass
            else:
                found = False
                i = 0
                while i + 32 <= len(hex_clean):
                    byte_val = int(hex_clean[i : i + 2], 16)
                    low = byte_val & 0x0F
                    if low in (0x08, 0x09, 0x0A, 0x0B):
                        hex_clean = hex_clean[i:]
                        found = True
                        break
                    i += 2
                if not found:
                    continue
        out_lines.append(hex_clean)
        out_map.append(src_idx)

    return StripResult("\n".join(out_lines), tuple(out_map))


# ═══════════════════════════════════════════════════════════════
# 2. ED 包装业务提取
# ═══════════════════════════════════════════════════════════════


def resolve_ed_wrapper(
    frame_bytes: bytes, mode: str = "auto", protocol_index=None
) -> str:
    """ED 包装格式判别：mode 为 "plc2"/"gx" 时直接用手动值。

    ``mode`` 为 ``auto``（或非法值）时逐帧打分识别：
      - 协议9 / 未指定：``csg_new_gen_parser.detect_ed_wrapper``（fallback=plc2）
      - 协议10/11（国网新一代 / HDC）：公共头与 gx 同构 **8 字节**，
        打分侧重「剥头后是否像 HDC MAC/FC」，平局优先 **gx**（不得再默认 plc2，
        否则业务帧整体错位 1 字节）。
    """
    if mode in ("plc2", "gx"):
        return mode
    if protocol_index not in (10, 11):
        from csg_new_gen_parser import detect_ed_wrapper
        return detect_ed_wrapper(frame_bytes, fallback="plc2")

    # ── 协议10/11 auto：HDC/gx 优先 ──────────────────────────
    n = len(frame_bytes)
    if n < 8 or frame_bytes[0] != 0xED or frame_bytes[5] != 0xEF:
        return "gx"
    frame_len = frame_bytes[1] | (frame_bytes[2] << 8)
    if frame_len < 4 or frame_len > 4096:
        return "gx"
    total = frame_len + 4
    if total > n or frame_bytes[total - 1] != 0xEE:
        return "gx"
    data = frame_bytes[6 : 6 + frame_len - 4]

    def _hdc_score(business: bytes) -> int:
        if not business:
            return 0
        score = 0
        ver = business[0] & 0x0F
        if ver in (0, 1):  # HDC MAC 版本
            score += 2
        if (business[0] & 0x08) and (business[0] & 0x07) <= 3:
            # CSG FC 接入指示 + 定界符（国网新一代完整 MPDU）
            score += 1
        if len(business) >= 10:
            msdu_len = business[8] | ((business[9] & 0x07) << 8)
            if 0 < msdu_len <= max(len(business) - 20, 0):
                score += 1
        return score

    score_gx = score_plc2 = -1
    for wrapper, hdr_len, _pb_off in (("gx", 8, 6), ("plc2", 9, 7)):
        if len(data) < hdr_len:
            continue
        s = _hdc_score(data[hdr_len:])
        if wrapper == "gx":
            s += 1  # HDC 同构布局，平局优先
            score_gx = s
        else:
            score_plc2 = s
    if score_plc2 > score_gx:
        return "plc2"
    return "gx"


def ed_wrapper_prefix_len(hex_str: str) -> int:
    """ED..EE 包装帧的「包装头(6B) + 数据域公共头」总字节数：plc2=15 / gx=14。

    非 ED 包装帧、或结构不完整（缺 EF/EE、帧长越界）时返回 0。

    用于替代早期 ``startswith("EDA5")`` + 固定剥 15 字节的硬编码：帧长字节随报文
    变化（EDA4/EDA5/ED1D… 都合法），且公共头有 plc2(9B)/gx(8B) 两种（见
    :func:`resolve_ed_wrapper`）——硬编码会把 gx 帧多剥 1 字节导致整帧错位。
    """
    s = hex_str.upper()
    if not s.startswith("ED") or len(s) < 16 or len(s) % 2:
        return 0
    try:
        fb = bytes.fromhex(s)
    except ValueError:
        return 0
    if len(fb) < 8 or fb[0] != 0xED or fb[5] != 0xEF:
        return 0
    frame_len = fb[1] | (fb[2] << 8)
    if frame_len < 4 or frame_len > 4096:
        return 0
    total = frame_len + 4
    # 帧尾判定：优先「EE 落在帧长算出的位置」；帧长字段不精确（日志截断 / 合成夹具）
    # 时退一步要求实际数据以 EE 结尾。两者都不满足 → 不是可剥的 ED 包装帧：保留原行，
    # 由提取函数明确报错，不得静默裁切（AGENTS §8 陷阱 22）。
    if total <= len(fb):
        if fb[total - 1] != 0xEE:
            return 0
    elif fb[-1] != 0xEE:
        return 0
    wrapper = resolve_ed_wrapper(fb, "auto")
    return 6 + (8 if wrapper == "gx" else 9)


def split_ed_frames(hex_str: str) -> list:
    """把一行 hex 里**连续拼接**的多个 ED..EE 包装帧切开（按帧长定长推进）。

    监控日志常把多帧拼在一行（``totalData 'EDA5…FFEEEDA5…FFEE'``），批量解析
    必须逐帧解包，否则只出第一帧。

    Returns:
        每个 ED 帧的 hex 列表；首字节非 ED / 结构不完整时返回 ``[]``（调用方回退）。
        尾部不完整残帧被丢弃（不产出半帧）。
    """
    s = hex_str.upper()
    if not s.startswith("ED") or len(s) % 2:
        return []
    out = []
    pos = 0
    n = len(s)
    while pos + 16 <= n:
        if s[pos:pos + 2] != "ED":
            break
        try:
            frame_len = int(s[pos + 2:pos + 4], 16) | (int(s[pos + 4:pos + 6], 16) << 8)
        except ValueError:
            break
        if frame_len < 4 or frame_len > 4096:
            break
        total = (frame_len + 4) * 2  # 整帧 hex 长度
        if pos + total > n:
            break  # 尾部残帧
        if s[pos + 10:pos + 12] != "EF" or s[pos + total - 2:pos + total] != "EE":
            break
        out.append(s[pos:pos + total])
        pos += total
    return out


def unwrap_ed_line(hex_str: str, protocol_index: int = 11) -> list:
    """把一行里的 0..N 个 ED 包装帧解包成业务帧（双模协议批量解析用）。

    Returns:
        ``None`` —— 不是 ED 包装行（调用方按原逻辑处理该行）
        ``[(frame_hex, ed_data_type), …]`` —— 解包结果；合法但无业务数据 /
        解包失败时保留原始 ED 帧 hex（沿用既有 ``ed_data_type`` 语义）。
    """
    ed_frames = split_ed_frames(hex_str)
    if not ed_frames:
        return None
    result = []
    for ed_frame in ed_frames:
        business_hex, data_type = extract_business_from_ed_frame(
            ed_frame, wrapper=None, protocol_index=protocol_index
        )
        if business_hex:
            result.append((business_hex, data_type))
        else:
            # 合法 ED 帧但无业务数据（控制报文/空数据）或解包失败：保留原始帧
            result.append((ed_frame, data_type if data_type.startswith("ED:") else ""))
    return result


def ed_wrapper_display(protocol_index, wrapper: str) -> dict:
    """ED..EE 包装头**展示文案**（单一来源）。

    广西台体(gx) 与 国网HDC 的数据域公共头同为 8 字节，字节布局一致；
    协议9 沿用「广西台体/PLC2.0」试验台语境，协议10/11 必须用「国网HDC」
    解释同一布局（用户：解析结果字段不应显示为广西台体监控包装头）。

    Args:
        protocol_index: 协议索引；9=南网新一代，10/11=国网新一代/HDC；
            其他或 None → 按协议9 传统命名
        wrapper: "plc2"（9B 公共头）| "gx"（8B 公共头）

    Returns:
        dict: title / header_desc / start_comment / end_comment /
              summary_name / summary_web / combo_label
    """
    gx = wrapper == "gx"
    if protocol_index in (10, 11):
        brand = "国网HDC"
        layout = "8字节公共头" if gx else "PLC2.0布局(9字节公共头)"
        # 标题一律用国网HDC；非 gx 布局在标题中标注布局，避免与试验台语境混淆
        title = (
            f"── {brand}监控包装头 ──"
            if gx
            else f"── {brand}监控包装头(PLC2.0布局) ──"
        )
        return {
            "title": title,
            "header_desc": f"ED..EE {brand}监控封装附加信息（不属于业务帧）；{layout}",
            "start_comment": f"{brand} 封装起始标识",
            "end_comment": f"{brand} 封装结束标识",
            "summary_name": f"{brand}监控包装帧",
            "summary_web": f"{brand}监控包装",
            "combo_label": (
                f"{brand}(8字节公共头)" if gx else "PLC2.0布局(9字节公共头)"
            ),
        }
    if gx:
        return {
            "title": "── 广西台体监控包装头 ──",
            "header_desc": "ED..EE 监控设备附加信息（不属于业务帧）",
            "start_comment": "广西台体发射机包装起始标识",
            "end_comment": "广西台体包装结束标识",
            "summary_name": "广西台体监控包装帧",
            "summary_web": "广西台体监控包装",
            "combo_label": "广西台体(14字节头)",
        }
    return {
        "title": "── PLC2.0 监控包装头 ──",
        "header_desc": "ED..EE 监控设备附加信息（不属于业务帧）",
        "start_comment": "PLC2.0 收发机包装起始标识",
        "end_comment": "PLC2.0 包装结束标识",
        "summary_name": "PLC2.0监控包装帧",
        "summary_web": "ED监控包装",
        "combo_label": "PLC2.0 台体(15字节头)",
    }


def ed_wrapper_summary_name(title: str) -> str:
    """从包装头标题行推断摘要用包装名（标题已含「监控包装头」时调用）。"""
    t = str(title or "")
    if "HDC" in t or "国网" in t:
        return "国网HDC监控包装帧"
    if "广西" in t:
        return "广西台体监控包装帧"
    return "PLC2.0监控包装帧"


# ── 测试装置（工装板/功能驱动板）控制帧摘要 ────────────────────────────────
# 用户口径：「摘要里居然没有衰减值」—— 这类帧的核心内容就是**命令专属的解析值**
# （衰减器X衰减值 / CCO·STA 仓电源与引脚 / 220V 电源状态），必须进摘要。
# 判定「命令专属行」用**排除法**（跳过帧头/地址/命令码/校验和/结束符与固定 6 字节
# 数据项），因此解析器新增命令时摘要自动跟随，**不需要在摘要层再维护一张命令表**。

#: 摘要要跳过的非业务行（固定结构行 + 无信息量的数据项字节）
_TEST_DEVICE_SKIP_ROWS = frozenset({
    "起始字符", "帧头", "地址", "命令码", "校验和", "结束符",
})


def is_test_device_table(table_data: list) -> bool:
    """该解析表是否为「测试装置工装板/功能驱动板控制协议」表（标题行判定）。

    性能：本函数在批量解析里**逐帧**走（协议9 摘要路径），而标题行必须形如
    ``── 测试装置…控制协议`` ⇒ 先用廉价的「``──``」前缀筛掉普通数据行，只对
    区块标题行做完整判定（真实 3.2 万行日志实测：把每帧约 40 行的
    ``str().startswith()`` 全量判定降为约 2 行的标题行判定）。
    """
    for row in table_data or ():
        if not row:
            continue
        name = row[0]
        if not isinstance(name, str):
            name = str(name)
        if not name.startswith("──"):
            continue  # 普通数据行不可能匹配标题，直接跳过（省掉两次字符串判定）
        if name.startswith("── 测试装置") and "控制协议" in name:
            return True
    return False


def test_device_summary(table_data: list) -> str:
    """测试装置控制帧摘要：``命令名 | 命令专属解析值…``（非该类报文返回空串）。

    例：功能驱动板「控制衰减器」→ ``衰减器C | 衰减器C衰减值=20 dB``；
    工装板引脚控制 → ``设置引脚状态/衰减器A | CCO仓引脚控制=…；STA仓引脚控制=…``。

    **ED..EE 包装帧不在此接管**：那类表里既有包装头行又有控制行，既有 ED 摘要分支
    已经给出「包装名 + 业务帧核心值」，抢过来反而丢掉包装上下文（回归见
    `reflex_web/tests/test_csg_ed_control.py::test_web_summary_contains_control_state`）。
    """
    if not is_test_device_table(table_data):
        return ""
    if any(row and "监控包装头" in str(row[0]) for row in table_data):
        return ""
    parts: list = []
    for row in table_data:
        if not row:
            continue
        name = str(row[0])
        if name == "命令码":
            # 命令名本身即核心信息（如「衰减器C」）：取解析值而非 name=value
            cmd = str(row[2] or "")
            if cmd:
                parts.append(cmd)
            continue
        if not name or name.startswith("──") or name in _TEST_DEVICE_SKIP_ROWS:
            continue
        if name.startswith("数据项字节"):
            continue
        parsed = row[2] if len(row) > 2 else ""
        if parsed in ("", None):
            continue
        parts.append(f"{name}={parsed}")
    return " | ".join(parts)


_CTRL1_NAMES = {0x00: "数据报文", 0x01: "控制报文"}
_CTRL2_DATA_NAMES = {
    0x01: "FC数据", 0x02: "FC+Payload数据", 0x03: "Payload数据",
    0x04: "发送完成", 0x05: "选择确认帧发送完成",
    0x06: "RF和HPLC同时发送FC+Payload", 0x07: "FC+Payload数据",
    0x08: "UL-OFDMA帧(DL-OFDMA的SACK帧)",
}


def _plc2_channel_name(ch: int) -> str:
    names = {0x01: "HPLC", 0x02: "RF", 0x03: "HPLC+RF", 0x20: "OFDMA"}
    if ch in names:
        return names[ch]
    if 0x10 <= ch <= 0x1C:
        return f"MIMO(0x{ch:02X})"
    return f"保留(0x{ch:02X})"


def _ed_frame_parts(frame_bytes: bytes, wrapper: str):
    """ED..EE 包装帧的数字域（结构 + 数据域公共头），供行渲染与 TCP 监控提示**共用**。

    结构非法（帧长越界 / 缺 EF / 缺 EE / 长度不足）返回 ``None``。

    返回 dict 键：frame_len / total / ctrl1 / ctrl2 / data_start / data_len / data /
    cs_offset / cs / cs_calc / cs_ok / hdr_len（公共头字节数，0=本帧无公共头）/
    ch / ts / pb_cnt / flag6 / pb_len / ts_off / ch_off / pb_off（hdr_len>0 时）。
    """
    n = len(frame_bytes)
    frame_len = frame_bytes[1] | (frame_bytes[2] << 8)
    if frame_len < 4 or frame_len > 4096:
        return None
    total = frame_len + 4
    # 帧长域与 EE 位置不一致（日志截断/多帧拼接/帧长写错）时：
    # 若缓冲区以 EF 开头、以 EE 结尾，按**实际末尾 EE** 重算整包长度。
    if total > n or frame_bytes[total - 1] != 0xEE:
        if n >= 8 and frame_bytes[5] == 0xEF and frame_bytes[-1] == 0xEE:
            total = n
            frame_len = total - 4
            if frame_len < 4:
                return None
        else:
            return None

    ctrl1, ctrl2 = frame_bytes[3], frame_bytes[4]
    data_start = 6
    data_len = frame_len - 4
    data = frame_bytes[data_start:data_start + data_len]
    cs_offset = data_start + data_len
    cs = frame_bytes[cs_offset]
    cs_calc = sum(frame_bytes[:cs_offset]) & 0xFF

    parts = {
        "frame_len": frame_len,
        "total": total,
        "ctrl1": ctrl1,
        "ctrl2": ctrl2,
        "data_start": data_start,
        "data_len": data_len,
        "data": data,
        "cs_offset": cs_offset,
        "cs": cs,
        "cs_calc": cs_calc,
        "cs_ok": cs == cs_calc,
        "hdr_len": 0,
    }

    hdr_len = 8 if wrapper == "gx" else 9
    if ctrl1 == 0x00 and ctrl2 in (0x01, 0x02, 0x03) and data_len >= hdr_len:
        if wrapper == "gx":
            ts = int.from_bytes(data[0:4], "little")
            ch = data[4]
            pb_cnt = data[5]
            flag6 = data[6]
            pb_len = int.from_bytes(data[6:8], "little")
            ts_off, ch_off, pb_off = 0, 4, 6
        else:
            ch = data[0]
            ts = int.from_bytes(data[1:5], "little")
            pb_cnt = data[5]
            flag6 = data[6]
            pb_len = int.from_bytes(data[7:9], "little")
            ts_off, ch_off, pb_off = 1, 0, 7
        parts.update(
            hdr_len=hdr_len, ch=ch, ts=ts, pb_cnt=pb_cnt, flag6=flag6,
            pb_len=pb_len, ts_off=ts_off, ch_off=ch_off, pb_off=pb_off,
        )
    return parts


def ed_wrapper_hints(frame_bytes: bytes, protocol_index=None, wrapper: str = None):
    """从 ED..EE 监控封装头取出**可驱动解析**的提示值（纯逻辑，无 Qt）。

    返回 dict（非 ED / 结构非法 → 空 dict）：
      wrapper / channel（"plc"/"hrf"，由「物理信道」字节推出：0x02=RF→hrf）/
      channel_code / channel_name / frame_len / data_len / hdr_len /
      business_offset（业务帧在整帧中的起始偏移）/ business_len / pb_size
      （「单个物理块长度」声明值）/ pb_count / has_business。

    用途（TCP 监控）：把「帧通道 / 帧长 / PB 大小」交给解析器——避免 RF 帧按载波
    可变区域表解析、避免多 PB 聚合靠猜测切分。
    """
    if not frame_bytes or frame_bytes[0] != 0xED or len(frame_bytes) < 8:
        return {}
    if wrapper not in ("plc2", "gx"):
        wrapper = resolve_ed_wrapper(frame_bytes, "auto", protocol_index=protocol_index)
    parts = _ed_frame_parts(frame_bytes, wrapper)
    if parts is None:
        return {}

    hdr_len = parts["hdr_len"]
    hints = {
        "wrapper": wrapper,
        "frame_len": parts["frame_len"],
        "data_len": parts["data_len"],
        "hdr_len": hdr_len,
        "business_offset": parts["data_start"] + hdr_len if hdr_len else 0,
        "business_len": parts["data_len"] - hdr_len,
        "channel": "plc",
        "channel_code": None,
        "channel_name": "",
        "pb_size": None,
        "pb_count": None,
        "has_business": parts["data_len"] - hdr_len > 0,
    }
    if hdr_len:
        ch = parts["ch"]
        hints.update(
            channel_code=ch,
            channel_name=_plc2_channel_name(ch),
            # 0x02=RF 单独使用 → 按无线的 FC 可变区域/PB 规格解析；
            # 0x01=HPLC / 0x03=HPLC+RF / 0x10~0x1C MIMO / 0x20 OFDMA 均含载波通路
            channel="hrf" if ch == 0x02 else "plc",
            pb_size=parts["pb_len"],
            pb_count=parts["pb_cnt"],
        )
    return hints


def build_ed_header_rows(
    frame_bytes: bytes, protocol_index=None, wrapper: str = None
) -> list:
    """构建 ED..EE 监控包装头**表格行**（字段文案按 protocol_index 分语义）。

    纯逻辑、无 Qt，供 TCP 监控 / 无 GUI 路径与桌面 `_parse_ed_monitor_header` 同源。
    非 ED 帧或结构非法时返回 []。

    protocol_index: 9→PLC2.0/广西台体；10/11→国网HDC（见 ed_wrapper_display）。
    wrapper: "plc2"/"gx"；None→resolve_ed_wrapper 自动识别。
    """
    if not frame_bytes or frame_bytes[0] != 0xED or len(frame_bytes) < 8:
        return []
    if wrapper not in ("plc2", "gx"):
        wrapper = resolve_ed_wrapper(frame_bytes, "auto", protocol_index=protocol_index)
    if protocol_index is None:
        protocol_index = 9
    lab = ed_wrapper_display(protocol_index, wrapper)

    parts = _ed_frame_parts(frame_bytes, wrapper)
    if parts is None:
        return []
    frame_len, total = parts["frame_len"], parts["total"]
    ctrl1, ctrl2 = parts["ctrl1"], parts["ctrl2"]
    data_start, data_len = parts["data_start"], parts["data_len"]
    cs_offset, cs = parts["cs_offset"], parts["cs"]
    cs_txt = "✓ 正确" if parts["cs_ok"] else (
        "保留(0xFF)" if cs == 0xFF else "✗ 错误"
    )
    ctrl1_name = _CTRL1_NAMES.get(ctrl1, f"保留(0x{ctrl1:02X})")
    ctrl2_name = (
        _CTRL2_DATA_NAMES if ctrl1 == 0x00 else {}
    ).get(ctrl2, f"保留(0x{ctrl2:02X})")

    rows = [
        (lab["title"], "", "", lab["header_desc"], None, None),
        ("起始符(ED)", f"0x{frame_bytes[0]:02X}", "ED",
         lab["start_comment"], 0, 0),
        ("帧长", f"{frame_bytes[1]:02X} {frame_bytes[2]:02X}",
         f"{frame_len} 字节", "控制域1+控制域2+EF+数据域+CS(小端)", 1, 2),
        ("控制域1", f"0x{ctrl1:02X}", ctrl1_name,
         "0x00-数据报文 0x01-控制报文", 3, 3),
        ("控制域2", f"0x{ctrl2:02X}", ctrl2_name, "报文子类型", 4, 4),
        ("数据域起始符(EF)", f"0x{frame_bytes[5]:02X}", "EF",
         "数据域起始标识", 5, 5),
        ("数据域长度", str(data_len), f"{data_len} 字节",
         f"字节 {data_start}~{cs_offset - 1}", data_start, cs_offset - 1),
    ]

    if parts["hdr_len"]:
        ch, ts, pb_cnt = parts["ch"], parts["ts"], parts["pb_cnt"]
        flag6, pb_len = parts["flag6"], parts["pb_len"]
        ts_off, ch_off, pb_off = parts["ts_off"], parts["ch_off"], parts["pb_off"]
        rows += [
            ("物理信道", f"0x{ch:02X}", _plc2_channel_name(ch),
             "0x01-HPLC 0x02-RF 0x03-HPLC+RF 0x10~0x1C-MIMO 0x20-OFDMA",
             data_start + ch_off, data_start + ch_off),
            ("时间戳", f"0x{ts:08X}", str(ts),
             "HW→PC 接收开始时间(小端)",
             data_start + ts_off,
             data_start + (ts_off + 3)),
            ("物理块个数", str(pb_cnt), str(pb_cnt), None,
             data_start + 5, data_start + 5),
        ]
        if wrapper != "gx":
            crc_txt = "错误" if (ctrl2 == 0x02 and flag6 == 1) else "正确/保留"
            rows.append(
                ("Payload CRC", f"0x{flag6:02X}", crc_txt,
                 "ctrl2=0x02时: 0-正确 1-错误；其余保留",
                 data_start + 6, data_start + 6)
            )
        rows.append(
            ("单个物理块长度", str(pb_len), f"{pb_len} 字节(小端)", None,
             data_start + pb_off, data_start + (pb_off + 1))
        )

    rows += [
        ("校验(CS)", f"0x{cs:02X}", cs_txt,
         "ED..数据域末所有字节求和取低8bit", cs_offset, cs_offset),
        ("结束符(EE)", f"0x{frame_bytes[total - 1]:02X}", "EE",
         lab["end_comment"], total - 1, total - 1),
    ]
    return rows


def unwrap_ed_for_parse(
    frame_bytes: bytes, protocol_index=None
) -> tuple:
    """ED..EE 帧 → (ed_rows, business_bytes)。

    非 ED / 解包失败：([], frame_bytes) —— 调用方按原样解析。
    解包成功但无业务数据（控制报文等）：(ed_rows, b"")。
    """
    if not frame_bytes or frame_bytes[0] != 0xED:
        return [], frame_bytes
    wrapper = resolve_ed_wrapper(
        frame_bytes, "auto", protocol_index=protocol_index
    )
    ed_rows = build_ed_header_rows(frame_bytes, protocol_index, wrapper)
    business_hex, _dtype = extract_business_from_ed_frame(
        frame_bytes.hex(), wrapper=wrapper,
        protocol_index=protocol_index if protocol_index is not None else 9,
    )
    if business_hex:
        return ed_rows, bytes.fromhex(business_hex)
    if ed_rows:
        return ed_rows, b""
    return [], frame_bytes


def extract_business_from_ed_frame(
    hex_str: str, wrapper: str = None, protocol_index: int = 9
) -> tuple:
    """从 ED..EE 监控包装帧中提取业务数据（PLC2.0 9B / 广西台体 8B 公共头）

    包结构: ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)
    数据域公共头(9字节): 物理信道(1)+时间戳(4,LE)+物理块个数(1)+保留(1)+物理块长度(2,LE)

    注意：监控日志可能在 ED 帧后附加 FF EE 标记，需要正确处理

    Args:
        wrapper: "plc2"/"gx"；None/非法 → 逐帧打分识别
        protocol_index: 协议9 时额外尝试「测试装置通信控制协议」展开

    Returns:
        (business_hex, data_type_desc) 成功时返回业务数据hex和类型描述
        ("", "") 解析失败
    """
    try:
        frame_bytes = bytes.fromhex(hex_str)
    except ValueError:
        return "", ""

    if wrapper not in ("plc2", "gx"):
        wrapper = resolve_ed_wrapper(
            frame_bytes, "auto", protocol_index=protocol_index
        )
    n = len(frame_bytes)
    if n < 8 or frame_bytes[0] != 0xED:
        return "", ""

    # 解析帧长字段
    frame_len = frame_bytes[1] | (frame_bytes[2] << 8)
    if frame_len < 4 or frame_len > 4096:
        return "", ""

    # 计算预期的整包长度
    expected_total = frame_len + 4  # ED(1) + 帧长(2) + [内容:frame_len字节] + EE(1)

    # 查找实际的 EE 终止符位置
    # 优先使用帧长计算的位置，如果该位置不是 EE，则搜索
    ee_pos = -1
    if expected_total <= n and frame_bytes[expected_total - 1] == 0xEE:
        ee_pos = expected_total - 1
    else:
        # 帧长字段可能不准确，或者后面有多余数据(如 FF EE 标记)
        # 从位置6后搜索第一个 EE
        for i in range(6, min(n, expected_total + 10)):  # 允许一定偏差
            if frame_bytes[i] == 0xEE:
                ee_pos = i
                break

    if ee_pos < 0:
        # 帧长域不准且 EE 不在 expected+10 窗口内：日志缓冲区末尾的 EE 兜底
        # （现场：整段 hex 以 FF EE 结尾，但帧长域写的是较小的值）
        if n >= 8 and frame_bytes[5] == 0xEF and frame_bytes[-1] == 0xEE:
            ee_pos = n - 1
        else:
            return "", ""  # 找不到 EE 终止符

    # 验证 EF 起始符
    if frame_bytes[5] != 0xEF:
        return "", ""

    # 计算实际的数据范围
    # ED帧结构: ED(0) + 帧长(1-2) + ctrl1(3) + ctrl2(4) + EF(5) + 数据域 + CS + EE(ee_pos)
    data_start = 6
    data_end = ee_pos - 1  # 排除 CS(ee_pos-1) 和 EE(ee_pos)

    ctrl1 = frame_bytes[3]
    ctrl2 = frame_bytes[4]

    # 数据域为空：合法 ED 帧但没有业务数据（控制报文、空数据报文等）
    if data_end <= data_start:
        if ctrl1 == 0x01:
            return "", f"ED:控制报文(0x{ctrl2:02X})"
        elif ctrl1 == 0x00:
            return "", f"ED:数据报文(空,0x{ctrl2:02X})"
        else:
            return "", f"ED:空数据(0x{ctrl1:02X}/0x{ctrl2:02X})"

    data = frame_bytes[data_start:data_end]
    data_len = len(data)

    # 控制报文或非标准数据子类型中可能携带测试装置通信控制协议。
    # 该协议不是载波 FC/PB 业务帧，但属于 ED 数据域的有效内容，应交给协议9解析器展开。
    if protocol_index == 9:
        from csg_new_gen_parser import CSGNewGenParser

        if CSGNewGenParser()._parse_test_device_control(data) is not None:  # noqa: SLF001
            return frame_bytes[
                : ee_pos + 1
            ].hex().upper(), f"测试装置控制(0x{ctrl2:02X})"

    # 非数据报文或数据域不足，返回空
    hdr_len = 8 if wrapper == "gx" else 9
    if ctrl1 != 0x00 or ctrl2 not in (0x01, 0x02, 0x03) or data_len < hdr_len:
        # 控制报文或非标准数据子类型但有数据域：仍然视为合法 ED 帧，无业务数据
        if ctrl1 == 0x01:
            return "", f"ED:控制报文(0x{ctrl2:02X})"
        else:
            return "", f"ED:非业务帧(0x{ctrl1:02X}/0x{ctrl2:02X})"

    # 跳过公共头（PLC2.0=9 字节 / 广西台体=8 字节），提取业务数据
    business = data[hdr_len:]
    if len(business) < 4:
        # 公共头完整但业务数据不足：仍按合法 ED 数据帧处理
        return "", f"ED:数据报文(业务不足,0x{ctrl2:02X})"

    # 根据 ctrl2 确定数据类型描述
    ctrl2_desc = {
        0x01: "FC数据",
        0x02: "FC+Payload数据",
        0x03: "Payload数据",
    }.get(ctrl2, f"未知(0x{ctrl2:02X})")

    return business.hex().upper(), ctrl2_desc


# ═══════════════════════════════════════════════════════════════
# 3. 帧提取（统一三元组契约）
# ═══════════════════════════════════════════════════════════════


def _extract_wrapper_frames(text: str) -> list:
    """从文本中提取Wrapper帧

    Wrapper格式: 版本(2B) + 源端口(2B) + 目的端口(2B) + 长度(2B) = 8字节头部
    版本固定为 0x0001
    支持处理带日志前缀的格式，如 "WRAPPER[1] Sent 0001000000010000003B ..."
    """
    frames = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # 提取连续的长串十六进制数据（至少16个字符）
        # 这样 WRAPPER 中的零散字母不会被误认为数据
        hex_matches = re.findall(r"[0-9A-Fa-f]{16,}", line)
        if not hex_matches:
            continue

        for hex_pattern in hex_matches:
            hex_pattern = hex_pattern.upper()

            # 扫描整个十六进制字符串，寻找Wrapper头部 (0001xxxx)
            i = 0
            while i <= len(hex_pattern) - 16:  # 至少需要8字节(16字符)头部
                # 检查是否是Wrapper头部: 版本=0001
                if hex_pattern[i : i + 4] == "0001":
                    # 解析Wrapper头部的长度字段
                    apdu_len = int(hex_pattern[i + 12 : i + 16], 16)

                    # 验证长度合理性（允许apdu_len=0，因为数据可能被截断）
                    if 0 <= apdu_len <= 8192:
                        # 计算完整帧长度: 8字节头部 + apdu_len
                        frame_len = 16 + apdu_len * 2

                        if i + frame_len <= len(hex_pattern):
                            # 提取完整帧
                            frame_hex = hex_pattern[i : i + frame_len]
                            frames.append(frame_hex)
                            i += frame_len
                            continue
                        else:
                            # 数据被截断，但仍提取可用的头部+部分数据
                            frame_hex = hex_pattern[i:]
                            frames.append(frame_hex)
                            break
                i += 2

    return frames if frames else [re.sub(r"[^0-9A-Fa-f]", "", text).upper()]


def _extract_hdlc_frames(clean: str) -> list:
    """提取HDLC帧（7E开头，7E结束）"""
    frames = []
    i = 0
    while i < len(clean) - 3:
        # 找下一个7E起始
        pos = clean.find("7E", i)
        if pos == -1:
            break
        # 找下一个7E结束
        end = clean.find("7E", pos + 2)
        if end == -1:
            # 如果没找到结束，直接取到结尾或者最大长度
            end = min(pos + 512, len(clean))
        candidate = clean[pos : end + 2]
        if len(candidate) >= 6:  # 至少3字节
            frames.append(candidate)
        i = end + 2
    return frames


def _extract_68_frames(clean: str) -> list:
    """提取南网68格式帧（Q/CSG1209021-2019 FT1.2）

    帧格式: 68H | L(2B小端) | C(1B) | 用户数据(L-6字节) | CS(1B) | 16H
    L = 帧总字节数（含起始符、长度域、控制域、校验和、结束符）
    验证规则:
      1. 起始字符 = 68H
      2. L >= 8（最小帧长度）
      3. 帧末尾 = 16H
    """
    frames = []
    i = 0
    while i < len(clean) - 7:
        # 找下一个 68 起始
        pos = clean.find("68", i)
        if pos == -1:
            break

        # 尝试按长度域解析帧边界
        if pos + 6 > len(clean):
            i = pos + 2
            continue

        try:
            low_byte = int(clean[pos + 2 : pos + 4], 16)
            high_byte = int(clean[pos + 4 : pos + 6], 16)
            length = low_byte | (high_byte << 8)
        except ValueError:
            i = pos + 2
            continue

        # L 至少为 8（起始1 + 长度2 + 控制1 + 校验1 + 结束1 + 用户数据至少3）
        if length < 8 or length > 2048:
            i = pos + 2
            continue

        frame_hex_len = length * 2

        # 检查数据是否足够
        if pos + frame_hex_len > len(clean):
            i = pos + 2
            continue

        candidate = clean[pos : pos + frame_hex_len]

        # 验证结束符 = 16H
        if candidate[-2:] != "16":
            i = pos + 2
            continue

        # 通过长度域和结束符验证，接受此帧（不校验CS，由解析器负责校验）
        frames.append(candidate)
        i = pos + frame_hex_len
        continue

    return frames


def _extract_69845_frames(clean: str) -> list:
    """提取698.45格式帧（DL/T 698.45-2017）

    帧格式: 68H | L(2B小端) | C(1B) | SA | CA | HCS(2B) | APDU | FCS(2B) | 16H
    **L 语义（协议文档 6.2.2 a）：帧数据长度值 = 传输帧中不包含起始字符和结束字符
    的数据长度 ⇒ 帧总长度 = L + 2**（L 本身含两个长度域字节）。标准附录 H.1.1
    「登录」示例自证：``68 1E 00 81 … FCS FCS 16`` 共 **32** 字节、L=0x001E=30。
    验证规则:
      1. 起始字符 = 68H
      2. L >= 8（最小有效长度）
      3. 帧末尾 = 16H
      4. 长度域一致性: 实际帧长 = L + 2
    """
    frames = []
    i = 0
    while i < len(clean) - 7:
        pos = clean.find("68", i)
        if pos == -1:
            break

        if pos + 6 > len(clean):
            i = pos + 2
            continue

        try:
            low_byte = int(clean[pos + 2 : pos + 4], 16)
            high_byte = int(clean[pos + 4 : pos + 6], 16)
            length = low_byte | (high_byte << 8)
        except ValueError:
            i = pos + 2
            continue

        # L 至少为 8（控制1 + SA至少1 + CA1 + HCS2 + FCS2 + APDU至少1）
        if length < 8 or length > 2048:
            i = pos + 2
            continue

        # 698.45: 帧总长度 = L + 2（6.2.2 a：L 不含首尾定界符，且含两个长度字节）
        total_len = length + 2
        frame_hex_len = total_len * 2

        if pos + frame_hex_len > len(clean):
            i = pos + 2
            continue

        candidate = clean[pos : pos + frame_hex_len]

        # 验证结束符 = 16H
        if candidate[-2:] != "16":
            i = pos + 2
            continue

        frames.append(candidate)
        i = pos + frame_hex_len
        continue

    return frames


def _extract_generic_frames(clean: str, min_len: int = 4, max_len: int = 512) -> list:
    """通用帧提取：整段 hex 作为单帧判断"""
    if len(clean) >= min_len * 2 and len(clean) <= max_len * 2:
        return [clean] if len(clean) % 2 == 0 else []
    return []


def _extract_csg_new_gen_frames(text: str, protocol_index: int = 9) -> list:
    """提取新一代载波协议帧（返回三元组）

    处理规则:
      - 按行分割（每行一帧，兼容多帧批量输入）
      - 去除空白后只保留偶数长度的有效 hex 行
      - 过滤过短的行（< 4 字节）
      - **ED 监控帧处理**：若帧以 ED 开头，解析 ED..EE 包装头，提取业务帧

    Returns:
        list of tuple: [(frame_hex, ed_data_type, line_no), ...]
          - frame_hex: 提取后的帧 hex 字符串
          - ed_data_type: ED 数据类型描述（如 "FC数据"、"FC+Payload数据"），非 ED 帧为空字符串
          - line_no: 该帧在输入文本中的行号（供结果回跳日志定位）
    """
    frames = []
    for line_no, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        # 仅保留 hex 字符（清洗后应已是纯 hex，此处兜底）
        clean_line = "".join(
            c for c in line if c in "0123456789ABCDEFabcdef"
        ).upper()
        if len(clean_line) < 8:  # 至少 4 字节
            continue
        if len(clean_line) % 2 != 0:
            # 奇数长度：丢弃末尾字符以保证字节对齐
            clean_line = clean_line[:-1]

        ed_data_type = ""
        # ED 监控帧处理：解析 ED..EE 包装头，提取业务帧
        if clean_line.startswith("ED"):
            business_hex, data_type = extract_business_from_ed_frame(
                clean_line,
                wrapper=resolve_ed_wrapper(bytes.fromhex(clean_line), "auto"),
                protocol_index=protocol_index,
            )
            if business_hex:
                clean_line = business_hex
                ed_data_type = data_type
            elif data_type.startswith("ED:"):
                # 合法 ED 帧但无业务数据（控制报文、空数据报文等）
                # 保留原始 ED hex，标记类型供后续解析识别
                ed_data_type = data_type
            # 其余情况（ED 解析失败）保留原始帧，ed_data_type 为空

        frames.append((clean_line, ed_data_type, line_no))
    return frames


# 双模协议（国网新一代 10 / HDC 1.0 11）：监控日志的 ED..EE 包装帧需先解包
_ED_WRAPPER_PROTOCOLS = (10, 11)


def _extract_line_frames(text: str, protocol_index: int, min_len: int = 1) -> list:
    """按行提取帧（每行一帧），并对双模协议的 ED..EE 包装行先解包。

    监控日志把 ED 包装帧（可能一行拼多帧）原样贴进来时，必须剥离
    ``ED(6B) + 数据域公共头(plc2 9B / gx 8B)`` 才是 FC+PB 业务帧；否则首字节
    0xED 会被当成应用层端口号解析（用户报障：协议11 下 ED 帧被解析成「应用层报文」）。
    协议9 走 ``csg_line`` 策略，其 ``_extract_csg_new_gen_frames`` 已含同等逻辑。
    """
    frames = []
    for i, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line or len(line) < min_len:
            continue
        if protocol_index in _ED_WRAPPER_PROTOCOLS:
            unwrapped = unwrap_ed_line(line, protocol_index)
            if unwrapped is not None:
                for frame_hex, ed_type in unwrapped:
                    frames.append((frame_hex, ed_type, i))
                continue
        frames.append((line, "", i))
    return frames


def extract_frames_for_protocol(text: str, protocol_index: int) -> list:
    """根据协议提取帧（策略选择由 ``protocol_registry`` 驱动）

    Returns:
        list[(frame_hex, ed_data_type, line_no)] —— 统一三元组契约。
        非行式策略（68/69845/generic/hdlc/wrapper）的 ed_data_type 为 ""、
        line_no 为该策略内部序号（这些策略不做行级定位，与桌面一致）。
    """
    strategy = protocol_registry.get_protocol(protocol_index).extract_strategy
    if strategy == "ft12_68":
        # 南网/国网：68开头，16结束，FT1.2帧格式
        clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
        return [(f, "", i) for i, f in enumerate(_extract_68_frames(clean))]
    if strategy == "dlt698_45":
        # 698.45：68开头，16结束，但长度域定义不同
        clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
        return [(f, "", i) for i, f in enumerate(_extract_69845_frames(clean))]
    if strategy == "generic":
        clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
        return [
            (f, "", i)
            for i, f in enumerate(_extract_generic_frames(clean, min_len=4, max_len=256))
        ]
    if strategy == "hdlc":
        clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
        return [(f, "", i) for i, f in enumerate(_extract_hdlc_frames(clean))]
    if strategy == "wrapper":
        return [
            (f, "", i) for i, f in enumerate(_extract_wrapper_frames(text))
        ]
    if strategy == "csg_line":
        # 监控前缀已由 strip_csg_monitor_prefix 剥离
        return _extract_csg_new_gen_frames(text, protocol_index)
    if strategy == "gw_line_min4":
        # 前缀已由 strip_gw_new_gen_prefix 剥离
        return _extract_line_frames(text, protocol_index, min_len=4)
    # line / 默认：每行一帧
    return _extract_line_frames(text, protocol_index, min_len=1)


# ═══════════════════════════════════════════════════════════════
# 4. 摘要与类型列
# ═══════════════════════════════════════════════════════════════

# 测试模式/子模式的解析行名（协议9 表61 与协议10 检测扩展命令共用）
TEST_MODE_SENTINELS = ("测试模式/配置操作", "安全测试模式", "新一代测试模式")

# 关键业务字段个数（用户选定 2；调这里即可改变摘要长度）
_GW_APP_SUMMARY_KEY_FIELDS = 2

# 应用层报文摘要的元数据字段（非业务语义，**不占**关键字段位）；
# 收两协议字段名的并集，避免漏排（如协议10 的「安全机制」vs 协议11 的「安全模式」）。
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
    "报文序号",
    "转发数据规约类型",
    "转发数据长度",
    "规约类型",
    "发送类型",
    "MSDU类型",
    "⚠ 安全保护",
)


def gw_app_biz_summary(table_data) -> tuple:
    """从应用层报文表中提取 (业务名, [关键业务字段…])。

    业务名（按优先级）：
      ① ``── 业务数据`` 区头之后的首个普通行字段名（协议11 布局，如 ``开始升级``）；
      ② 「报文ID」解析值——**仅当它不是 hex 形式**时视为业务名（协议10 布局）；
      都不命中时返回空串（摘要退化为现状，不报错）。

    关键业务字段：在**应用层/业务数据段窗口内**（见下），字段名带前导空格（业务/子字段层）、
    非元数据、非分隔行/业务名行、解析值非空且不是「N字节」占位符，按顺序取前
    ``_GW_APP_SUMMARY_KEY_FIELDS`` 个，格式 ``字段名:解析值``。

    扫描窗口：起点 = ``── 业务数据`` 行 +1（协议11 布局）；无该区头时 = 顶层
    「应用层报文」行 +1（协议10/auto 布局）；终点 = 起点之后首个**顶层行**（无缩进）
    或表尾。**不能全表扫描**：真实 MPDU 在 auto/fc_pb 级别下 FC/MAC 字段
    （``版本``/``原始源TEI``/``定界符类型``/``网络类型``）排在应用层之前，会被当成业务字段。
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

    # ── 扫描窗口：限定在「应用层报文 / 业务数据」段内 ──
    window_start, window_end, from_biz_section = -1, -1, False
    # ① 优先：业务数据区（协议11 布局——业务名与业务字段都在区内，
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
    window = table_data[
        window_start : window_end if window_end >= 0 else len(table_data)
    ]

    # ── 业务名 ──
    biz_name = ""
    biz_row_idx = -1
    if from_biz_section:
        # 协议11：`── 业务数据 ──` 之后首个带缩进的普通行，其字段名即业务名
        for k, item in enumerate(window):
            if not _raw_name(item).startswith(" ") or _is_skippable(_name(item)):
                continue
            biz_name, biz_row_idx = _name(item), window_start + k
            break
    if not biz_name:
        # 协议10：无业务数据区，业务名由「报文ID」解析值给出（非 hex 形式）
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
        # 只取带前导空格的字段行（顶层行不是业务字段）
        if not raw_name.startswith(" "):
            continue
        if _is_skippable(name) or _is_meta(name):
            continue
        if re.fullmatch(r"\d+字节", parsed):  # 字节数占位（区头/长度行）
            continue
        fields.append(f"{name}:{parsed}")
        if len(fields) >= _GW_APP_SUMMARY_KEY_FIELDS:
            break

    return biz_name, fields


def extract_test_mode_content(table_data: list) -> str:
    """测试帧/检测扩展命令 → 摘要片段（非测试类报文返回空串）。

    现场关注的「测试模式」来自解析器的两类字段：
      - 协议9 1.0测试（表61）/ 协议10 检测扩展命令 → ``测试模式/配置操作``
      - 协议10 子模式 → ``安全测试模式``(模式13) / ``新一代测试模式``(模式15)
    测试帧若没有上述字段（如协议9 测试ID=0x00/0x01/0x02 类），回退到
    ``测试ID``/``扩展ID``/测试数据区频段，避免这类帧的摘要一片空白。

    输出示例：
      "测试模式:PLC物理层透传测试模式(3)"
      "测试模式:安全测试模式(13) | 安全测试模式:SHA256签名"
      "测试ID:频段切换命令 | 通信频段:0x02"
      "测试帧上行（确认/否认，无数据单元）"
    """
    if not table_data:
        return ""

    fs = {}
    for item in table_data:
        key = str(item[0]).strip()
        if key:
            fs.setdefault(key, item)

    def _numeric(text: str) -> bool:
        text = text.strip()
        return bool(re.fullmatch(r"0[xX][0-9A-Fa-f]+|-?\d+(?:\.\d+)?", text))

    # 名称所在槽位两个协议相反，按「非数值者即名称」探测（不做描述文本黑名单）：
    #   协议9 表61：raw=0x03  parsed=3(数值)  comment=PLC物理层透传测试模式（高4位）
    #   协议10 检测扩展命令：raw=3  parsed=HPLC物理层透传测试模式  comment=检测扩展命令:…
    #   → parsed 非数值时名称在 parsed；否则名称在 comment；再退回 raw。
    def _name_of(item) -> str:
        for cand in (item[2], item[3], item[1]):
            text = str(cand).strip() if cand not in (None, "") else ""
            text = text.replace("（高4位）", "").strip()
            text = re.sub(r"^[^:：]*检测扩展命令[:：]?\s*", "", text)
            if not text or _numeric(text):
                continue
            if "仅测试模式" in text:
                continue  # 协议9 表61 恒定输出的占位子模式行
            return text
        return ""

    def _value_of(item) -> str:
        for cand in (item[2], item[1]):
            text = str(cand).strip() if cand not in (None, "") else ""
            if _numeric(text):
                return text
        return ""

    def _is_test_frame_rows() -> bool:
        """本 helper 只服务测试类报文：协议9 以业务标识 0xF0 自证。"""
        svc = fs.get("业务标识")
        if svc is None:
            return False
        return (
            str(svc[2]).strip() == "240"
            or "F0" in str(svc[1]).upper()
            or "测试帧" in str(svc[3])
        )

    parts = []

    mode_item = fs.get("测试模式/配置操作")
    if mode_item is not None:
        name = _name_of(mode_item)
        value = _value_of(mode_item)
        # 名称自带括号（`保留(14)`、`…测试模式(暂未使用)`）时不再重复追加模式号
        has_paren_suffix = bool(re.search(r"[（(][^（()）]*[)）]\s*$", name))
        if value and not has_paren_suffix:
            parts.append(f"测试模式:{name}({value})")
        elif name:
            parts.append(f"测试模式:{name}")

    for sub_name in ("安全测试模式", "新一代测试模式"):
        sub_item = fs.get(sub_name)
        if sub_item is None:
            continue
        sub_text = _name_of(sub_item)
        if sub_text:
            parts.append(f"{sub_name}:{sub_text}")

    if mode_item is None:
        # 没有「测试模式/配置操作」的测试帧（协议9 测试ID 0/1/2 或 2.0测试扩展ID）：
        # 回退到测试ID/扩展ID，避免这类帧摘要一片空白
        test_id = fs.get("测试ID")
        ext_id = fs.get("扩展ID")
        if test_id is not None:
            text = _name_of(test_id)
            if text:
                parts.append(f"测试ID:{text}")
        if ext_id is not None:
            text = _name_of(ext_id)
            if text:
                parts.append(f"扩展ID:{text}")

    data_item = fs.get("测试数据区")
    if data_item is not None:
        comment = str(data_item[3]) if data_item[3] not in (None, "") else ""
        if "通信频段" in comment:
            band = comment.split(":", 1)[1].strip() if ":" in comment else comment
            parts.append(f"通信频段:{band}")

    if not parts and "上行负载" in fs and _is_test_frame_rows():
        return "测试帧上行（确认/否认，无数据单元）"
    return " | ".join(parts)


def extract_csg_core_content(table_data: list, protocol_index: int = 9) -> str:
    """从新一代载波协议应用层报文中提取核心业务内容（用于摘要）

    根据帧类型+业务标识组合，提取最有信息量的字段：
      - 确认/否认：否认原因码
      - 数据传输帧：源/目的地址 + 数据长度
      - 命令帧：目标设备地址 + 命令参数
      - 其他：取业务数据单元中首个有意义的字段
    """
    fields = {item[0]: item for item in table_data}

    # ── 获取帧类型和业务标识 ──
    ft_desc = fields.get("  帧类型域(D3~D0)", ("", "", "", ""))[3]
    svc_desc = fields.get("业务标识", ("", "", "", ""))[3]
    # 从 "业务标识 N - 名称" 中提取业务名
    svc_name = svc_desc.split(" - ", 1)[1] if " - " in svc_desc else svc_desc

    # ── 测试帧（业务标识 0xF0）：优先体现测试模式/测试ID ──
    # 必须放在确认/否认、命令帧分支之前：测试帧的帧类型域是「命令帧」，
    # 否则会落到通用命令帧列表，测试模式信息被淹没。
    svc_item = fields.get("业务标识")
    if svc_item is not None and (
        str(svc_item[2]).strip() == "240"
        or "F0" in str(svc_item[1]).upper()
        or "测试帧" in str(svc_item[3])
    ):
        mode_text = extract_test_mode_content(table_data)
        if mode_text:
            return mode_text

    # ── 否认帧：显示否认原因 ──
    if "否认" in svc_name:
        deny_item = fields.get("否认原因码")
        if deny_item:
            return f"原因:{deny_item[3]}"
        return "否认"

    # ── 确认帧：显示确认状态 ──
    if "确认" in svc_name and "否认" not in svc_name:
        confirm_item = fields.get("确认/否认负载")
        if confirm_item:
            return confirm_item[3]  # "确认报文，无业务数据"
        return "确认"

    # ── 数据传输帧：源/目的地址 + 数据长度 ──
    if "数据传输" in ft_desc:
        parts = []
        src = fields.get("源地址")
        dst = fields.get("目的地址")
        if src:
            # 提取冒号后的实际地址值
            addr = src[3].split(": ", 1)[1] if ": " in src[3] else src[2]
            parts.append(f"源:{addr}")
        if dst:
            addr = dst[3].split(": ", 1)[1] if ": " in dst[3] else dst[2]
            parts.append(f"目的:{addr}")
        data_len = fields.get("转发数据长度")
        if data_len:
            parts.append(f"{data_len[2]}字节")
        return " | ".join(parts) if parts else svc_name

    # ── 命令帧：命令名 + 关键参数 ──
    if "命令" in ft_desc:
        parts = [svc_name]
        # 提取设备地址（若有）
        dev_addr = fields.get("设备地址")
        if dev_addr:
            addr = (
                dev_addr[3].split(": ", 1)[1]
                if ": " in dev_addr[3]
                else dev_addr[2]
            )
            parts.append(f"设备:{addr}")
        # 提取命令关键参数（非保留/非控制域的有意义字段）
        cmd_skip = {
            "帧类型域",
            "传输方向位",
            "启动标志",
            "响应标识",
            "业务扩展域",
            "任务优先级",
            "保留",
            "业务标识",
            "帧序号",
            "帧长",
            "报文端口号",
            "报文标识符",
            "应用版本号",
            "业务数据单元",
            "控制域",
        }
        for fn, item in fields.items():
            if fn.startswith("  "):
                continue  # 跳过控制域位域子字段
            if any(k in fn for k in cmd_skip):
                continue
            desc = item[3]
            val = item[2]
            if (
                desc
                and "保留" not in desc
                and "默认" not in desc
                and "未解析" not in desc
            ):
                if val and str(val) != "0" and str(val) != "0字节":
                    # 避免与 svc_name 重复
                    if desc[: len(svc_name)] != svc_name:
                        parts.append(f"{desc[:30]}")
        return " | ".join(parts[:4])  # 最多4段

    # ── 兜底：取业务数据单元中首个有意义的字段 ──
    skip_keys = [
        "控制域",
        "传输方向",
        "启动标志",
        "响应标识",
        "业务扩展域标识",
        "任务优先级",
        "保留(D",
        "帧类型域",
        "报文端口号",
        "报文标识符",
        "应用版本号",
        "帧序号",
        "帧长",
        "业务标识",
        "保留",
        "MSDU",
        "VLAN",
        "级联",
        "物理块",
        "MPDU",
        "MAC",
    ]
    for fn, item in fields.items():
        if any(k in fn for k in skip_keys):
            continue
        desc = item[3]
        if not desc or desc in ("保留", "保留字段", "保留位默认填0"):
            continue
        if any(k in desc for k in ["未解析", "可能为填充", "尚未实现"]):
            continue
        if fn in ("业务数据单元", "确认/否认负载", "管理消息数据"):
            continue
        return f"{fn.strip()}:{desc[:30]}"
    return svc_name if svc_name else ""


def get_csg_new_gen_summary(table_data: list, protocol_index: int = 9) -> str:
    """新一代载波协议(索引9)批量解析摘要生成

    区分报文类型并优先使用 MSDU 类型作为顶层分类：
    - 含 "管理消息类型(MMTYPE)" → "<MSDU类型> | MMTYPE:..."
    - 含 "定界符类型" (MPDU/MAC 物理层帧) → "<MSDU类型> | <定界符> | 源/目的TEI"
    - 含 "业务标识" (应用层) → "<MSDU类型> | <帧类型> | 业务标识:... | 方向 | 核心内容"

    table_data 格式: (field_name, raw_value, parsed_value, comment, byte_start, byte_end)
    """
    if not table_data:
        return "-"

    # ── 单次遍历同时完成三件事（协议9 摘要逐帧调用；原实现扫 table_data 3 遍）──
    #   ① 解析失败：提取失败原因（命中即返回）
    #   ② 字段索引：快速定位关键字段
    #   ③ ED 监控包装帧标题探测（原为对 fields 的键再扫一遍）
    # 结果与「先扫一遍找 ❌ → 再建 dict → 再扫键找包装头」逐字等价：dict 键保持
    # 插入序（同一键保留最后一条），ed_hdr 取首个命中（`is None` 守卫），
    # item[0] 在此处必为 str（否则原实现的 `item[0].startswith` 早已抛错）。
    fields = {}
    ed_hdr = None
    for item in table_data:
        name = item[0]
        if name.startswith("❌"):
            return item[3] if item[3] else "解析失败"
        fields[name] = item
        if ed_hdr is None and "监控包装头" in name:
            ed_hdr = name
    if ed_hdr:
        parts = [ed_wrapper_summary_name(ed_hdr)]
        ctrl1 = fields.get("控制域1")
        ctrl2 = fields.get("控制域2")
        if ctrl1:
            parts.append(str(ctrl1[2]))
        if ctrl2:
            parts.append(str(ctrl2[2]))
        data_len = fields.get("数据域长度")
        if data_len:
            dlen_val = data_len[2]
            if isinstance(dlen_val, int):
                parts.append(f"数据:{dlen_val}字节")
            else:
                parts.append(f"数据:{dlen_val}")
        # 有业务帧时提取业务帧类型（在"── 业务帧 ──"之后）
        business_found = False
        for item in table_data:
            if item[0].startswith("── 业务帧"):
                business_found = True
                continue
            if (
                business_found
                and item[0]
                and not item[0].startswith(" ")
                and "校验" not in item[0]
                and "结束符" not in item[0]
            ):
                parts.append(str(item[3] or item[2] or item[0]))
                break
        return " | ".join(parts)

    # ── 公共：MSDU 类型作为顶层分类（若存在）──
    msdu_type_prefix = ""
    if "MSDU类型" in fields:
        msdu_type_name = fields["MSDU类型"][3]  # 如 "应用层报文"/"网络管理消息"
        if msdu_type_name:
            msdu_type_prefix = msdu_type_name

    # ── 应用层报文：含业务标识字段（优先于定界符类型展示）──
    if "业务标识" in fields:
        summary_parts = [msdu_type_prefix if msdu_type_prefix else "应用层"]
        # 0. 附带上层定界符类型（如果有）
        if "定界符类型" in fields:
            delim_desc = fields["定界符类型"][3]
            summary_parts.append(delim_desc)
        # 1. 帧类型域（业务大类）
        frame_type_item = fields.get("  帧类型域(D3~D0)")
        if frame_type_item:
            ft_comment = frame_type_item[3]  # "0 - 确认/否认"
            ft_name = (
                ft_comment.split(" - ", 1)[1] if " - " in ft_comment else ft_comment
            )
            summary_parts.append(ft_name)
        # 2. 业务标识（名称 + 编号）
        svc_item = fields["业务标识"]
        svc_val = svc_item[2]
        svc_comment = svc_item[3]  # "业务标识 0 - 确认"
        svc_desc = (
            svc_comment.split(" - ", 1)[1] if " - " in svc_comment else svc_comment
        )
        try:
            summary_parts.append(f"业务标识:{svc_desc}(0x{int(svc_val):02X})")
        except (ValueError, TypeError):
            summary_parts.append(f"业务标识:{svc_desc}")
        # 3. 传输方向
        dir_item = fields.get("  传输方向位(D15)")
        if dir_item:
            dir_comment = dir_item[3]  # "0 - 下行(CCO→STA)"
            dir_name = (
                dir_comment.split(" - ", 1)[1]
                if " - " in dir_comment
                else dir_comment
            )
            summary_parts.append(dir_name)
        # 4. 源/目的TEI
        if "源TEI" in fields:
            summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
        if "目的TEI" in fields:
            summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
        # 5. 核心内容：从业务数据单元子字段提取关键信息
        core = extract_csg_core_content(table_data, protocol_index)
        if core:
            summary_parts.append(core)
        return " | ".join(summary_parts)

    # ── 网络层：含 MMTYPE 字段（管理消息）──
    if "管理消息类型(MMTYPE)" in fields:
        mmtype_item = fields["管理消息类型(MMTYPE)"]
        mmtype_comment = mmtype_item[3]  # "管理消息: 关联请求(MMeAssocReq)"
        mmtype_val = mmtype_item[2]
        # 提取冒号后的消息名称
        mmtype_name = (
            mmtype_comment.split(":", 1)[1].strip()
            if ":" in mmtype_comment
            else mmtype_comment
        )
        prefix = msdu_type_prefix if msdu_type_prefix else "网络管理消息"
        try:
            # MMTYPE 解析值为 '0x0030' 形式字符串，需先去 0x 前缀按 16 进制解析
            mm_val = (
                int(mmtype_val, 16)
                if str(mmtype_val).lower().startswith("0x")
                else int(mmtype_val)
            )
        except (ValueError, TypeError):
            mm_val = 0
        summary_parts = [f"{prefix} | MMTYPE:{mmtype_name}(0x{mm_val:04X})"]
        # 附带管理消息版本
        if "管理消息版本" in fields:
            ver = fields["管理消息版本"][2]
            summary_parts.append(f"版本{ver}")
        # 附带源/目的TEI
        if "源TEI" in fields:
            summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
        if "目的TEI" in fields:
            summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
        return " | ".join(summary_parts)

    # ── 网络层：MPDU/MAC 物理层帧（定界符类型字段）──
    if "定界符类型" in fields:
        delim_item = fields["定界符类型"]
        delim_desc = delim_item[3]  # "SOF帧" / "信标帧" / "选择确认帧(SACK)"
        prefix = msdu_type_prefix if msdu_type_prefix else "网络层"
        summary_parts = [f"{prefix} | {delim_desc}"]
        # 信标帧：额外显示信标类型（发现/代理/中央）
        if delim_desc == "信标帧":
            beacon_type = ""
            if "信标载荷头" in fields:
                beacon_head_item = fields["信标载荷头"]
                beacon_parsed = beacon_head_item[2]
                if isinstance(beacon_parsed, str) and "类型:" in beacon_parsed:
                    idx = beacon_parsed.index("类型:") + 3
                    beacon_type = beacon_parsed[idx:].split(",")[0].split(" ")[0]
            if not beacon_type and "信标类型" in fields:
                beacon_type = str(fields["信标类型"][3] or fields["信标类型"][2])
            if beacon_type:
                summary_parts.append(f"信标类型:{beacon_type}")
            # 信标帧附带网络标识
            if "网络标识(SNID)" in fields:
                summary_parts.append(f"SNID:{fields['网络标识(SNID)'][2]}")
        # SOF/SACK 帧附带源/目的TEI和帧序号
        if delim_desc in ("SOF帧", "选择确认帧(SACK)"):
            if "源TEI" in fields:
                summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
            if "目的TEI" in fields:
                summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
            if "发送序号" in fields:
                summary_parts.append(f"序号:{fields['发送序号'][2]}")
        return " | ".join(summary_parts)

    # ── 兜底：MSDU 负载等未分类报文，取前几个有效字段 ──
    parts = []
    for item in table_data[:4]:
        fn, pv, desc = item[0], item[2], item[3]
        if any(k in fn for k in ["帧起始", "格式", "长度", "校验", "结束"]):
            continue
        parts.append(str(desc) if desc else str(pv))
    return " | ".join(parts) if parts else "-"


def get_gw_new_gen_summary(table_data: list, protocol_index: int = 10) -> str:
    """国网新一代(索引10) / HDC 1.0(索引11) 监控/批量摘要生成

    体现监控工具关注的关键业务信息：
      网络标识(NID) | 帧类型(信标/SOF/选择确认/网间协调) | 管理消息类型(MMTYPE) |
      源→目的TEI | MSDU序列号 | 发送类型(单播/广播) | MSDU类型 |
      应用层端口/报文ID(方向)/报文序号/规约类型/数据长度

    table_data 格式: (field, raw, parsed, comment, byte_start, byte_end, is_child)
    """
    if not table_data:
        return "-"

    # 解析失败：直接返回失败原因
    for item in table_data:
        if str(item[0]).startswith("❌"):
            return item[3] if item[3] else "解析失败"

    # 以去除缩进的字段名建立索引（首个出现优先：FC 在 MAC/应用层之前）
    fs = {}
    for item in table_data:
        key = str(item[0]).strip()
        if key:
            fs.setdefault(key, item)

    def val(name):
        it = fs.get(name)
        return str(it[2]).strip() if it and it[2] not in (None, "") else ""

    def cmt(name):
        it = fs.get(name)
        return str(it[3]).strip() if it and it[3] not in (None, "") else ""

    parts = []

    # 1. 网络标识(NID)
    nid = val("网络标识(NID)")
    if nid:
        parts.append(f"NID:{nid}")

    # 2. 帧类型（定界符类型），comment 形如 "DT=1: SOF帧"
    delim = cmt("定界符类型")
    if delim:
        frame_type_name = delim.split(":", 1)[1].strip() if ":" in delim else delim
        sof_sub = val("帧类型")  # SOF帧子类型: 数据帧/信道探测帧
        if "SOF" in frame_type_name and sof_sub:
            parts.append(f"{frame_type_name}({sof_sub})")
        else:
            parts.append(frame_type_name)

    # 3. 管理消息类型(MMTYPE)：如 关联确认(MMeAssocCnf)/发现列表
    mmtype = cmt("管理消息类型(MMTYPE)")
    if mmtype:
        parts.append(f"MMTYPE:{mmtype}")

    # 4. 源→目的TEI：优先 FC 级，其次 MAC 级原始源/目的
    src = val("源TEI") or val("原始源TEI")
    dst = val("目的TEI") or val("原始目的TEI")
    if src or dst:
        parts.append(f"{src or '?'}→{dst or '?'}")

    # 5. MSDU序列号
    seq = val("MSDU序列号")
    if seq:
        parts.append(f"msduSeq:{seq}")

    # 6. 发送类型（单播/本地广播/...）
    send_type = cmt("发送类型")
    if send_type and "保留" not in send_type:
        parts.append(send_type)

    # 7. MSDU类型（非保留且未在别处体现）
    msdu_type = cmt("MSDU类型")
    if msdu_type and "保留" not in msdu_type and "网络管理" not in msdu_type:
        parts.append(msdu_type)

    # 8. 应用层：报文端口 + 报文ID(含方向) + 报文序号 + 规约类型 + 数据长度
    port = val("报文端口号")
    if port:
        parts.append(f"端口:{port}")
    msg_id = val("报文ID")
    if msg_id:
        # 方向(上行/下行)在"应用层报文"行 comment 中，如 "...报文ID=xxx 下行"
        app_cmt = cmt("应用层报文")
        direction = ""
        for d in ("下行", "上行"):
            if d in app_cmt:
                direction = d
                break
        parts.append(
            f"报文:{msg_id}({direction})" if direction else f"报文:{msg_id}"
        )
    # 业务名 + 关键业务字段：应用层报文的核心内容（协议11 的业务名在
    # 「── 业务数据 ──」区头行，协议10 已由「报文ID」解析值给出）——
    # 现场反馈：缺少这两段时同一批升级帧摘要完全相同，无法扫读。
    # 仅应用层报文（有端口号/报文ID）才提取：网络层/物理层帧没有业务语义。
    if port or msg_id:
        biz_name, biz_fields = gw_app_biz_summary(table_data)
        if biz_name and biz_name != msg_id and biz_name not in " | ".join(parts):
            parts.append(biz_name)
        parts.extend(biz_fields)
    # 报文序号（STA 应答时返回）
    msg_seq = val("报文序号")
    if msg_seq:
        parts.append(f"序号:{msg_seq}")
    # 规约类型（如 DL/T 698.45），精简展示
    proto = val("规约类型")
    if proto:
        parts.append(f"规约:{proto.replace('DL/T ', '')}")
    dlen = val("转发数据长度")
    if dlen:
        parts.append(f"数据:{dlen}")

    # 9. 测试类报文（通信测试/检测扩展命令）：体现测试模式/配置操作
    #    仅在三个哨兵行之一存在时才调用，避免 helper 对同名字段误提取（协议10 无 0xF0 概念）
    if any(
        str(item[0]).strip() in TEST_MODE_SENTINELS for item in table_data
    ):
        test_mode_text = extract_test_mode_content(table_data)
        if test_mode_text:
            parts.append(test_mode_text)

    return " | ".join(parts) if parts else "-"


def get_summary_from_table_data(
    table_data: list, protocol_index: int, empty_text: str = "-"
) -> str:
    """从表格数据中提取摘要信息，取重要的前几个字段拼接。

    ``protocol_index`` 由调用方显式给出（供后台线程/Web 传入参数快照）；
    本函数及其下游均**不读任何控件**。

    ``empty_text``：空表文案（桌面批量用 ``"-"``；Web 单帧展示沿用 ``"空"``）。
    """
    if not table_data:
        return empty_text

    proto = protocol_index
    summary_parts = []

    if proto == 0:
        # 南网协议：提取 AFN 名称（comment）、SEQ 值、DI 业务说明（comment）
        afn_val = None
        seq_val = None
        di_desc = None
        for item in table_data:
            field_name = item[0]
            parsed_val = item[2]
            comment = item[3]
            if field_name == "应用功能码 (AFN)":
                # AFN 的 parsed_val 为空，说明在 comment 中
                afn_val = comment if comment else parsed_val
            elif field_name == "帧序列号 (SEQ)":
                seq_val = parsed_val
            elif field_name == "数据标识 (DI)":
                # DI 的业务说明在 comment 中
                if comment and not di_desc:
                    di_desc = comment
        if di_desc:
            summary_parts.insert(0, f"DI:{di_desc}")
        if afn_val is not None:
            summary_parts.append(f"AFN:{afn_val}")
        if seq_val is not None:
            summary_parts.append(f"SEQ:{seq_val}")
        return " | ".join(summary_parts) if summary_parts else "-"

    elif proto == 7:
        # 国网协议：提取 AFN 名称、Fn 说明、传输方向
        afn_name = None
        fn_desc = None
        dir_desc = None
        for item in table_data:
            field_name = item[0]
            parsed_val = item[2]
            comment = item[3]
            if field_name == "应用功能码(AFN)":
                afn_name = comment if comment else parsed_val
            elif field_name == "数据单元标识(DT)":
                fn_desc = comment if comment else parsed_val
            elif "传输方向" in field_name:
                dir_desc = (
                    "下行"
                    if str(parsed_val).strip() == "0"
                    else "上行"
                    if str(parsed_val).strip() == "1"
                    else "-"
                )
        if dir_desc:
            summary_parts.append(dir_desc)
        if afn_name:
            summary_parts.append(f"AFN:{afn_name}")
        if fn_desc:
            summary_parts.append(fn_desc)
        return " | ".join(summary_parts) if summary_parts else "-"

    elif proto == 8:
        # 698.45：提取 APDU 类型、DIR+PRM、功能码
        apdu_type = None
        dir_prm = None
        func_desc = None
        for item in table_data:
            field_name = item[0]
            parsed_val = item[2]
            comment = item[3]
            if field_name == "  APDU类型":
                apdu_type = str(parsed_val) if parsed_val else comment
            elif field_name == "  DIR+PRM":
                dir_prm = str(parsed_val) if parsed_val else comment
            elif field_name == "  功能码":
                func_desc = str(parsed_val) if parsed_val else comment
        if dir_prm:
            summary_parts.append(dir_prm)
        if func_desc:
            summary_parts.append(func_desc)
        if apdu_type:
            summary_parts.append(apdu_type)
        return " | ".join(summary_parts) if summary_parts else "-"

    elif proto == 9:
        # 新一代载波协议：区分网络层报文(MPDU/MAC/MMTYPE)与应用层报文(业务标识)
        return get_csg_new_gen_summary(table_data, proto)

    elif proto in (10, 11):
        # 国网新一代/HDC 1.0：网络标识/帧类型/TEI/MSDU序列/发送类型/报文等关键信息
        return get_gw_new_gen_summary(table_data, proto)

    else:
        # 其他协议：取前几个非冗余字段
        for i, item in enumerate(table_data):
            if i >= 4:
                break
            field_name = item[0]
            parsed_val = item[2]
            if any(
                k in field_name
                for k in ["帧起始", "格式", "长度", "校验", "结束标志"]
            ):
                continue
            summary_parts.append(f"{parsed_val}")
        return " | ".join(summary_parts) if summary_parts else "-"


def get_frame_type_name(
    table_data: list, status: str, protocol_index: int
) -> str:
    """从解析表格数据中提取帧类型名称（用于摘要表的"协议/类型"列）。

    兜底分支读 ``protocol_registry``（不读任何控件），可在工作线程调用。
    """
    proto = protocol_index
    if status != "成功" or not table_data:
        if status == "失败":
            return "解析失败"
        elif status == "异常":
            return "异常"
        else:
            return "-"

    if proto == 0:  # 南网协议
        for item in table_data:
            field = str(item[0])
            if "AFN" in field and not field.startswith(" "):
                return str(item[3] or item[2] or "南网协议")
        return "南网协议"

    elif proto == 7:  # 国网协议
        for item in table_data:
            field = str(item[0])
            if "AFN" in field and not field.startswith(" "):
                return str(item[3] or item[2] or "国网协议")
        return "国网协议"

    elif proto == 8:  # 698.45
        for item in table_data:
            field = str(item[0])
            if (
                "APDU" in field or "功能码" in field or "服务" in field
            ) and not field.startswith(" "):
                return str(item[3] or item[2] or "698.45协议")
        return "698.45协议"

    elif proto in (2, 3, 4, 5):  # DLMS 族
        for item in table_data:
            field = str(item[0])
            if (
                "帧类型" in field or "服务" in field or "功能" in field
            ) and not field.startswith(" "):
                val = str(item[3] or item[2] or "")
                if val:
                    return val
        proto_names = {2: "HDLC", 3: "DLMS-APDU", 4: "DLMS-Wrapper", 5: "DLMS-APDU"}
        return proto_names[proto]

    elif proto == 9:  # 新一代载波
        for item in table_data:
            field = str(item[0])
            if (
                "帧类型" in field or field.strip() == "FC"
            ) and not field.startswith(" "):
                return str(item[3] or item[2] or "新一代载波")
        return "新一代载波"

    elif proto == 10:  # 国网新一代
        for item in table_data:
            field = str(item[0])
            if ("帧类型" in field or "MSDU类型" in field) and not field.startswith(
                " "
            ):
                return str(item[3] or item[2] or "国网新一代")
        return "国网新一代"

    elif proto == 11:  # HDC 1.0（Q/GDW 12087.42-2020）
        # 字段名与协议10 不同构：FC 定界符行叫「定界符类型(DT)」（协议10 为
        # 「定界符类型」）→ 两种都认，否则类型列恒为注册表名「HDC」而不是
        # 信标帧/SOF帧/选择确认帧(SACK)/网间协调帧（AGENTS §8 陷阱52 同类）。
        for item in table_data:
            field = str(item[0])
            if field.startswith(("定界符类型", "MSDU类型")):
                val = str(item[3] or item[2] or "")
                if val:
                    return val
        # 无 FC 的裸 MAC/应用层帧：优先取业务名（协议11 业务数据布局，如
        # “开始升级”），复用 gw_app_biz_summary 单一规则；取不到再退回
        # MSDU 类型 / 报文ID。曾误用「报文ID」行的**说明列**（“安全模式:…,
        # 业务ID:…”)作为类型名（9e60ba6 潜伏红测试根因）
        biz_name, _ = gw_app_biz_summary(table_data)
        if biz_name:
            return biz_name
        for item in table_data:
            field = str(item[0]).strip()
            if field in ("MSDU类型", "报文ID", "业务报文ID"):
                val = str(item[2] or item[3] or "")
                if val and not val.startswith("安全模式"):
                    return val
        return "HDC 1.0"

    elif proto == 6:  # DLT645
        for item in table_data:
            if "控制码" in str(item[0]) and not str(item[0]).startswith(" "):
                return str(item[3] or item[2] or "DLT645")
        return "DLT645协议"

    elif proto == 1:  # PLC RF
        for item in table_data:
            field = str(item[0])
            if ("命令字" in field or "功能" in field) and not field.startswith(" "):
                return str(item[3] or item[2] or "PLC RF")
        return "PLC RF协议"

    else:
        # 兜底：取注册表展示名首段
        return protocol_registry.get_protocol(proto).name.split(" ")[0]


__all__ = [
    "CSG_MONITOR_PREFIX",
    "CSG_MONITOR_HEADER_BYTES",
    "TEST_MODE_SENTINELS",
    "StripResult",
    "gw_app_port_prefixes",
    "strip_csg_monitor_prefix",
    "strip_csg_new_gen_frame_prefix",
    "strip_gw_new_gen_prefix",
    "resolve_ed_wrapper",
    "extract_business_from_ed_frame",
    "ed_wrapper_prefix_len",
    "ed_wrapper_hints",
    "build_ed_header_rows",
    "unwrap_ed_for_parse",
    "split_ed_frames",
    "unwrap_ed_line",
    "extract_frames_for_protocol",
    "extract_test_mode_content",
    "extract_csg_core_content",
    "gw_app_biz_summary",
    "get_csg_new_gen_summary",
    "get_gw_new_gen_summary",
    "get_summary_from_table_data",
    "get_frame_type_name",
]
