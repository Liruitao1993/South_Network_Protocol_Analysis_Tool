# -*- coding: utf-8 -*-
"""串口工具（集成自「USB 负载测试工具」）。

能力（与源工具一致）：
  - 命令表：**选择（勾选框）** / 名称 / 发送数据(HEX) / 匹配方式 / 预期响应 / **协议**，可增删改与上下移；
    **只发勾选的命令**（全选 / 全不选 / 反选），按表内顺序
  - 发送：按毫秒级间隔循环发送，次数 0 = 无限；间隔用「先 sleep + 尾段忙等」保精度
  - 接收：原始数据（**协议特征断帧 + 时间聚合兜底**；68 家族自动跳过帧首前导 FEH）/
    按帧尾分割（帧尾可配）。**断帧设置**（1.23.78）：断帧方式（自动 / 仅按字节超时）
    + 4 个可调超时（字节静默 / 聚合最长持有 / 协议帧等待静默 / 协议帧等待上限）
  - 响应匹配：6 种方式，接收数据从待匹配**队首**连续比对（按**累积**接收数据，
    跨交付块也能命中），超时计失败并输出可比对的诊断
  - 统计：收发帧数/字节、匹配成功/失败/成功率、运行时长；彩色日志（可节流）
  - **按协议断帧与解析**（1.23.47+，源工具没有）：命令自带协议 → 接收按该协议用长度域/
    定界符精确切帧；**发送与接收都按各自协议解析**，在日志里输出摘要 + 缩进字段行
  - **日志自动保存到文件**（1.23.54+，源工具没有）：勾选「自动保存日志」即把
    **日志窗口的内容**实时写入文件 —— 文件是日志窗口的**完整镜像**（同样受
    「显示发送/显示接收/显示解析」控制），但**不截断**（窗口只保留最近 10000 行，
    文件一直追加）。每行带毫秒时间戳前缀、写一行 flush 一次（断电/崩溃也尽量保住），
    文件头写环境上下文、文件尾写收发与匹配统计；目录可选、可一键打开

与源工具（`E:\\python\\USB负载测试工具\\serial_load_test.py`）的差异（**有意为之**）：
  - 串口层复用本项目的 :class:`serial_worker.SerialWorker`（不另起一套 pyserial 封装），
    且**复用主窗口共享的那一个实例**（`set_serial_worker`）：端口/波特率只在顶部
    「串口配置」设置，本页只读跟随连接状态 —— 一个 COM 口只能被打开一次，各页各持
    句柄会互相抢口。发送走其 :meth:`SerialWorker.write_raw`（静默，不逐帧发日志信号）
  - 主题/样式走本项目主题系统（不带源工具自带的 4 套 stylesheet）
  - 形态是主窗口的一个标签页，不是独立 ``QMainWindow``

本模块**纯逻辑部分**（HEX/匹配/报文文件/配置持久化）不依赖串口与 GUI，
便于 offscreen 单测；GUI 与线程部分在下方。
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Tuple

import frame_addr_fix
import wakeup_prefix

# 分帧族的**单一来源**在 `frame_deframe`（纯逻辑、无 Qt）；这里 re-export 同名对象，
# 既有调用点与测试锚点（`stw.frame_length_for` / `stw.declared_frame_len` /
# `stw._wakeup_base` / `stw.RAW_MAX_FRAME_LEN` …）一律不变。
from frame_deframe import (  # noqa: F401  (F401: 纯逻辑族在此 re-export 供 GUI / 测试 import)
    END_CHAR_STRATEGIES,
    FE_WAKEUP_STRATEGIES,
    HDLC_MIN_FRAME_LEN,
    RAW_MAX_FRAME_LEN,
    RAW_MIN_FRAME_LEN,
    STRATEGY_BY_PROTOCOL,
    STRATEGY_NAMES,
    _sane_frame_len,
    _wakeup_base,
    declared_frame_len,
    frame_incomplete,
    frame_length_for,
    hdlc_frame_len,
)

# ── 常量（匹配方式照搬源工具）──────────────────────────────────────────

# 波特率**不在本页**：端口与波特率统一由顶部「串口配置」管理（见 set_serial_worker）

# 匹配方式：键与源工具一致（导入导出/配置兼容），值为界面中文标签
# 末尾新增的 hex_wildcard 是本项目扩展（源工具没有）；**与「测试方案」的 XX 通配
# 同一约定**（见 `test_plan_widget._match_frame`：HEX 模式逐字符走，遇 XX 跳过一个字节）
MATCH_TYPES: Dict[str, str] = {
    "contains": "包含",
    "equals": "完全相等",
    "starts_with": "开头匹配",
    "ends_with": "结尾匹配",
    "regex": "正则表达式",
    "hex_wildcard": "HEX 通配（XX=任意字节）",
    "none": "不匹配（全部成功）",
}

# 「HEX 通配」里的通配记号：`XX`（项目既有约定）与 `??`（等价别名）
HEX_WILDCARD_TOKENS = ("XX", "??")

# 只有这四种匹配方式的「预期响应」是**纯 HEX**（其余是通配 / 正则 / 不匹配）——
# 批量替换地址时只能对它们做「同步替换地址」（见 `batch_fix_commands`）
HEX_MATCH_TYPES = ("contains", "equals", "starts_with", "ends_with")

# 规范里定义了「帧前导 FEH 唤醒字节」的协议（DL/T 645-2007 §5.3.1、DL/T 698.45-2017 §6.3.1 b)）。
# 批量替换地址前要先剥离、替换后再**原样恢复**；其余协议规范里没有前导码，
# 带 FE 的帧就该报错，剥了等于「救活」错帧（见 AGENTS §8 陷阱 75）。
FE_WAKEUP_PROTOCOLS = (6, 8)

DEFAULT_FRAME_TAIL = "FE 16"

# 解析日志的字段行上限；**0 = 不限制**（默认不截断 —— 国网「查询从节点ID信息」
# 一条应答帧就有 113 行解析，截断会让现场看不到完整结果）
DEFAULT_PARSE_MAX_LINES = 0
PARSE_MAX_LINES_RANGE = (0, 2000)

# 断帧方式（1.23.78）：auto = 有协议按协议结构特征断帧/拼帧、无协议按字节超时聚合
# （并保留 68 结构自证增强）；timeout_only = 忽略协议结构与启发式，**纯按字节超时**聚合。
FRAMING_MODE_AUTO = "auto"
FRAMING_MODE_TIMEOUT = "timeout_only"
FRAMING_MODE_OPTIONS = (
    (FRAMING_MODE_AUTO, "自动（协议特征优先）"),
    (FRAMING_MODE_TIMEOUT, "仅按字节超时"),
)

# 断帧超时的**默认值**（毫秒）—— 唯一来源：既供 DEFAULT_PARAMS 取值，也供下方历史常量
# `RAW_FLUSH_DELAY_MS` / `RAW_MAX_HOLD_MS` / `FRAME_IDLE_MS` / `FRAME_HOLD_MAX_MS` 取值
# （老代码与既有测试仍引用那几个常量，故保留其名字）。
FRAME_TIMEOUT_DEFAULTS: Dict[str, int] = {
    "rx_byte_idle_ms": 10,          # 无结构可判时的字节静默窗口（「字节超时」本体）
    "rx_raw_max_hold_ms": 200,      # 持续流下强制刷出的最长持有（防缓冲无界）
    "rx_frame_idle_ms": 300,        # 已认出一帧但未收全时的静默容忍
    "rx_frame_hold_max_ms": 5000,   # 一帧的绝对等待上限（防中途断流挂死）
}

# 断帧超时的可调范围（毫秒）：UI spin 与参数夹紧**共用一份**，避免两处漂移。
FRAME_TIMEOUT_RANGES: Dict[str, Tuple[int, int]] = {
    "rx_byte_idle_ms": (1, 2000),
    "rx_raw_max_hold_ms": (10, 60000),
    "rx_frame_idle_ms": (10, 60000),
    "rx_frame_hold_max_ms": (100, 600000),
}

# 默认参数（默认值与源工具一致：100ms / 1 次 / 5000ms；波特率由顶部串口配置决定）
DEFAULT_PARAMS: Dict[str, object] = {
    "interval_ms": 100,
    "loop_count": 1,
    "timeout_ms": 5000,
    "match_enabled": True,
    "rx_mode": "raw",          # raw | frame
    "frame_tail": DEFAULT_FRAME_TAIL,
    "parse_enabled": True,     # 按命令协议解析并在日志输出文字
    "parse_max_lines": DEFAULT_PARSE_MAX_LINES,
    "show_tx": True,
    "show_rx": True,
    "auto_scroll": True,
    # 日志文件（自动保存）—— 默认**关闭**：不勾选行为与旧版本完全一致
    "log_auto_save": False,    # 勾选即实时把日志写入文件
    "log_dir": "",             # 空 = 默认目录（数据目录下的 Output/）
    "log_timestamp": True,     # 文件里每行加毫秒时间戳前缀
    # 断帧（1.23.78）：默认值 = 原模块常量（见 FRAME_TIMEOUT_DEFAULTS）⇒ 老配置
    # 零行为变化；只**新增键**，因此不需要 CONFIG_VERSION 迁移（改既有默认值才需要）。
    **FRAME_TIMEOUT_DEFAULTS,
    "rx_framing_mode": FRAMING_MODE_AUTO,
}

# 落盘文件名（app_paths.data_path 下）
CONFIG_NAME = "serial_tool_config.json"
# 配置版本：v2 起 `parse_max_lines` 的默认值由 30 改为 0（不限制）。
CONFIG_VERSION = 2
# v1 的「解析行数上限」默认值 —— 迁移时用它判断「存的是旧默认值还是用户特意选的」
LEGACY_PARSE_MAX_LINES_DEFAULT = 30

# 发送日志批量汇总间隔（毫秒）——高速发送时避免逐帧刷屏
LOG_FLUSH_MS = 100

# 日志文件（自动保存）默认值：目录落在数据目录下的 Output/（与监控器 CSV 一致，
# 已被 .gitignore 排除）；文件名带秒级时间戳
DEFAULT_LOG_DIR_NAME = "Output"
LOG_FILE_PREFIX = "serial_log"
LOG_HEADER_TITLE = "串口工具日志"


# ── 纯函数：HEX ──────────────────────────────────────────────────────

# HEX 输入里可接受的分隔符（现场粘贴常见：全角逗号/顿号/分号/斜杠/竖线/连字符）
HEX_SEPARATORS = ",，、;；/|-"


def _strip_hex_prefix(s: str) -> str:
    """去掉 ``0x`` / ``0X`` 前缀（只去掉真正跟了 hex 字符的那些）。"""
    return re.sub(r"0[xX](?=[0-9A-Fa-f])", "", s)


def hex_str_to_bytes(s: str) -> Optional[bytes]:
    """解析 hex 字符串（支持空格/逗号分隔），失败返回 None。

    容错范围（现场粘贴的常见形态；源工具只认「空格 / 半角逗号」分隔）：
      - **连续无分隔**：``6812004116`` → ``68 12 00 41 16``（实测报障：明明是对的
        却提示「不是有效的 HEX」，就是因为原实现把整串当一个 token → 越界）
      - 常见分隔符统一：半角/全角逗号、顿号、半角/全角分号、斜杠、竖线、连字符、
        制表/换行/全角空格
      - ``0x`` / ``0X`` 前缀
      - 单个 hex 字符的片段按一个字节解析（``4`` → ``0x04``，与源工具一致）
    仍拒绝：连续串的字符数为奇数、含非 hex 字符。
    """
    s = (s or "").strip()
    if not s:
        return None
    s = _strip_hex_prefix(s)
    parts = re.sub(r"[,，、;；/|-]+", " ", s).split()
    if not parts:
        return None
    out = bytearray()
    for p in parts:
        if len(p) <= 2:
            try:
                value = int(p, 16)
            except ValueError:
                return None
            if not 0 <= value <= 0xFF:
                return None
            out.append(value)
            continue
        if len(p) % 2 != 0:               # 连续 hex 必须偶数长度才能按字节切
            return None
        try:
            out.extend(bytes.fromhex(p))
        except ValueError:
            return None
    return bytes(out)


def hex_input_error(s: str) -> str:
    """「为什么不是有效 HEX」—— 给出可读原因，现场才能自查（不只说「格式不对」）。"""
    raw = (s or "").strip()
    if not raw:
        return "内容为空"
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch in "0123456789abcdefABCDEF" or ch in HEX_SEPARATORS or ch in " \t\r\n\u3000":
            i += 1
            continue
        if ch in "xX" and i > 0 and raw[i - 1] == "0":
            i += 1
            continue
        return f"含非 HEX 字符 {ch!r}（第 {i + 1} 个字符）"
    body = _strip_hex_prefix(raw)
    for p in re.sub(r"[,，、;；/|-]+", " ", body).split():
        if len(p) > 2 and len(p) % 2 != 0:
            return (f"片段 {p!r} 的字符数为奇数（{len(p)} 个），"
                    "无法按字节切分（每字节需要 2 个 hex 字符）")
        if len(p) > 2:
            try:
                bytes.fromhex(p)
            except ValueError:
                return f"片段 {p!r} 不是合法的 HEX"
    return "格式无法识别（HEX 每字节 2 个字符，可用空格 / 逗号分隔）"


def bytes_to_hex(data: bytes) -> str:
    """字节 → 空格分隔大写 HEX。"""
    return " ".join(f"{b:02X}" for b in data)


# ── 纯函数：响应匹配 ──────────────────────────────────────────────────

def check_match(received: bytes, expected: bytes, match_type: str) -> bool:
    """判断接收数据是否匹配预期（6 种方式，语义与源工具一致）。

    - ``none``：恒 True（"不匹配（全部成功）"）
    - ``equals`` / ``contains`` / ``starts_with`` / ``ends_with``：字节级比较
    - ``regex``：把双方按 latin-1 解码后 ``re.search(IGNORECASE)``；非法正则返回 False
    """
    if match_type == "none":
        return True
    if match_type == "equals":
        return received == expected
    if match_type == "contains":
        return expected in received
    if match_type == "starts_with":
        return received.startswith(expected)
    if match_type == "ends_with":
        return received.endswith(expected)
    if match_type == "regex":
        try:
            pattern = re.compile(expected.decode("latin-1"), re.IGNORECASE)
            return bool(pattern.search(received.decode("latin-1")))
        except (re.error, UnicodeDecodeError):
            return False
    if match_type == "hex_wildcard":
        return hex_wildcard_match(received, expected.decode("latin-1")) is not None
    return False


def parse_hex_wildcard(pattern: str) -> Optional[List[Optional[int]]]:
    """解析「HEX 通配」模式 → 字节列表（``None`` 元素 = 通配字节）；非法返回 None。

    与「测试方案」同一约定（`test_plan_widget._match_frame`）：去掉分隔符后**逐字符**
    走，遇到 ``XX`` 跳过一个字节。所以 ``XX`` 可以嵌在连续串里：``68D0XXXX16``。

    支持：``XX``（项目既有约定）与 ``??``（等价别名）；分隔符复用 HEX 容错那一套。
    拒绝：奇数个字符、非 hex 字符（``XX``/``??`` 除外）、空模式。
    """
    body = re.sub(r"[,，、;；/|-]+", " ", str(pattern or "")).strip().upper()
    body = body.replace(" ", "")
    if not body:
        return None
    out: List[Optional[int]] = []
    i = 0
    while i < len(body):
        pair = body[i:i + 2]
        if pair in HEX_WILDCARD_TOKENS:
            out.append(None)
            i += 2
            continue
        if len(pair) < 2:
            return None                       # 末尾落了单个字符
        if not re.fullmatch(r"[0-9A-F]{2}", pair):
            return None
        out.append(int(pair, 16))
        i += 2
    return out


def hex_wildcard_match(received: bytes, pattern: str) -> Optional[int]:
    """在接收数据里查找「HEX 通配」模式，命中返回**偏移**，否则 None。

    支持可选锚点（写在模式两端，便于表达开头/结尾/全长）：
      - ``^`` 开头：必须从数据开头匹配
      - ``$`` 结尾：必须匹配到数据结尾
      - 都不写：任意位置（包含语义）
    """
    text = str(pattern or "").strip()
    anchor_start = text.startswith("^")
    anchor_end = text.endswith("$")
    if anchor_start:
        text = text[1:]
    if anchor_end:
        text = text[:-1]
    spec = parse_hex_wildcard(text)
    if not spec:
        return None
    need = len(spec)
    data = bytes(received or b"")
    if need > len(data):
        return None
    starts = [0] if anchor_start else range(len(data) - need + 1)
    for start in starts:
        if anchor_end and start + need != len(data):
            continue
        for k, want in enumerate(spec):
            if want is None:
                continue
            if data[start + k] != want:
                break
        else:
            return start
    return None


def match_offset(match_type: str, received: bytes, expected: bytes) -> Optional[int]:
    """统一匹配入口：命中返回偏移（未命中返回 None）。

    ``expected`` 的含义随方式而定：字节类/包含类是**字节**；``regex`` 与
    ``hex_wildcard`` 是**文本**（前者正则、后者 HEX 通配模式）。
    """
    if match_type == "hex_wildcard":
        return hex_wildcard_match(received, expected.decode("latin-1"))
    if match_type == "contains":
        idx = bytes(received or b"").find(bytes(expected or b""))
        return idx if idx >= 0 else None
    return 0 if check_match(received, expected, match_type) else None


def match_type_label(match_type: str) -> str:
    """匹配方式的日志文案：``包含(contains)``。"""
    return f"{MATCH_TYPES.get(match_type, match_type)}({match_type})"


_STATUS_ICON_CACHE: Dict[tuple, "QIcon"] = {}


def status_icon(status: str) -> "QIcon":
    """命令状态图标：取 lucide 图标并**按状态上色**（`app_icons` 只出单色）。

    用 ``CompositionMode_SourceIn`` 给渲染好的 pixmap 整体染色（保留 alpha），
    因此状态一眼可辨：绿✓通过 / 红✗失败 / 蓝↻发送中 / 橙⚠错误 / 灰○待测。
    """
    icon_name, color = CMD_STATUS_STYLES.get(status, CMD_STATUS_STYLES[""])
    key = (icon_name, color)
    cached = _STATUS_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    base = app_icons.load_icon(icon_name)
    icon = QIcon()
    if not base.isNull():
        pixmap = base.pixmap(14, 14)
        painter = QPainter(pixmap)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()
        icon = QIcon(pixmap)
    _STATUS_ICON_CACHE[key] = icon
    return icon


def status_text(status: str) -> str:
    """状态中文文案。"""
    return CMD_STATUS_LABELS.get(status, CMD_STATUS_LABELS[""])


def first_diff_offset(expected: bytes, received: bytes) -> int:
    """首个不同字节的偏移（相同前缀时返回共同长度）。"""
    for i in range(min(len(expected), len(received))):
        if expected[i] != received[i]:
            return i
    return min(len(expected), len(received))


def hex_preview(data: bytes, limit: int = 96) -> str:
    """HEX 预览：超过 ``limit`` 字节就截断并标注总长度（日志用）。"""
    data = bytes(data or b"")
    if not data:
        return "（空）"
    if len(data) <= limit:
        return bytes_to_hex(data)
    return f"{bytes_to_hex(data[:limit])} …（共 {len(data)} 字节）"


def expected_display(match_type: str, expected: bytes) -> str:
    """日志里「预期」的展示：正则 / HEX 通配是文本，其余是 HEX 预览。

    正则**不用 repr**（否则 ``68\\s*D0`` 会显示成 ``'68\\\\s*D0'``，现场更难读）。
    """
    expected = bytes(expected or b"")
    if match_type == "regex":
        return f"正则 {expected.decode('latin-1')}"
    if match_type == "hex_wildcard":
        return f"通配模式 {expected.decode('latin-1')}"
    return hex_preview(expected)


def match_failure_reason(match_type: str, expected: bytes,
                         received: bytes, sent: bytes = None) -> str:
    """给出「为什么没匹配上」的一句话诊断（纯函数，可单测）。

    这是**匹配失败日志**的核心：现场只看「超时未匹配」无法定位，必须说明
    比的是什么、差在哪里。
    """
    expected = bytes(expected or b"")
    received = bytes(received or b"")
    if not received:
        return "期间未收到任何数据（设备无响应，或响应超时设得太短）"
    if (sent is not None and match_type not in ("regex", "hex_wildcard")
            and expected == bytes(sent)):
        return ("预期响应与**发送数据完全相同** —— 常见误填：把要发送的命令"
                "粘到了「预期响应」里（响应一般与命令不同）")
    if match_type == "hex_wildcard":
        spec = parse_hex_wildcard(expected.decode("latin-1"))
        if not spec:
            return "通配模式无效（每字节 2 个 hex 字符，XX 表示任意字节）"
        need = len(spec)
        if need > len(received):
            return (f"通配模式比收到的数据长：模式 {need} 字节，"
                    f"只收到 {len(received)} 字节")
        return (f"通配模式未在收到的数据中匹配到（模式 {need} 字节，"
                f"XX 为任意字节；数据 {len(received)} 字节）")
    if match_type == "contains":
        return (f"预期串未出现在收到的数据中（预期 {len(expected)} 字节，"
                f"收到 {len(received)} 字节）")
    if match_type == "equals":
        if len(expected) != len(received):
            return (f"长度不一致：预期 {len(expected)} 字节，收到 {len(received)} 字节"
                    "（完全相等要求长度也一致）")
        off = first_diff_offset(expected, received)
        return (f"长度一致但内容不同：首个不同字节在偏移 {off}"
                f"（预期 {expected[off]:02X}，实际 {received[off]:02X}）")
    if match_type == "starts_with":
        if len(received) < len(expected):
            return (f"收到的数据比预期短：预期开头 {len(expected)} 字节，"
                    f"只收到 {len(received)} 字节")
        off = first_diff_offset(expected, received)
        return f"开头不一致：首个不同字节在偏移 {off}（预期 {expected[off]:02X}，实际 {received[off]:02X}）"
    if match_type == "ends_with":
        if len(received) < len(expected):
            return (f"收到的数据比预期短：预期结尾 {len(expected)} 字节，"
                    f"只收到 {len(received)} 字节")
        return (f"结尾不一致：预期以 {hex_preview(expected[-8:])} 结尾，"
                f"实际以 {hex_preview(received[-8:])} 结尾")
    if match_type == "regex":
        return "正则表达式未匹配到收到的数据（检查正则语法与目标字节）"
    if match_type == "none":
        return "匹配方式为「不匹配（全部成功）」，本不应判失败"
    return f"未知匹配方式 {match_type!r}"


# ── 纯函数：报文文件 ──────────────────────────────────────────────────

def load_hex_messages(filepath: str) -> List[bytes]:
    """从 txt 加载 hex 报文（每行一条）。

    兼容源工具 ``load_hex_messages``：行内若含 ``:`` 只取冒号之后的部分
    （便于直接粘贴「时间: 报文」形式的日志）；空行与非法行跳过。

    比源工具**多一次兜底**：源工具只按**第一个**冒号切分，遇到带时间戳的行
    （``2026-09-22 10:00:00: 68 03 04``）会切成 ``10:00:00: 68 03 04`` 而解析失败；
    这里先按第一个冒号试、不成立再按**最后一个**冒号试，因此是源语义的超集。
    """
    messages: List[bytes] = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            candidate = line
            if ":" in line:
                for cand in (line.split(":", 1)[1].strip(),
                             line.rsplit(":", 1)[1].strip()):
                    if hex_str_to_bytes(cand) is not None:
                        candidate = cand
                        break
            msg = hex_str_to_bytes(candidate)
            if msg:
                messages.append(msg)
    return messages


# ══════════════════════════════════════════════════════════════════════
# 纯函数：批量替换通信地址（按协议替换地址域 + 重算校验）
#
# 复用 `frame_addr_fix`（纯逻辑无 Qt，1.23.81 起蓝牙页在用）—— 地址定位、字节序、
# 校验算法**只有一个来源**；这里只做「串口命令表」这层的编排：
#   ① 只写回发送数据，且只有替换成功才算（失败/不适用一律原样保留 + 可读原因）；
#   ② 可选把协议写进命令的 ``protocol`` 键（「加载报文文件」导入的报文是 None）；
#   ③ 可选同步替换「预期响应」里的地址（能自证才替换）。
# 写回由调用方负责（本层不修改入参），因此撤销点天然存在。
# ══════════════════════════════════════════════════════════════════════

# 一条命令的处理结果三态
ADDR_STATUS_OK = "ok"            # 替换成功：data_hex 是替换后的帧
ADDR_STATUS_KEPT = "kept"        # 尝试了但没换成：原样保留 + error
ADDR_STATUS_SKIPPED = "skipped"  # 不该处理（发送数据本身不是有效 HEX）

# 批量替换日志的明细上限（其余汇总一行 —— 几百条逐条刷会挤掉收发日志）
ADDR_BATCH_LOG_LIMIT = 20


@dataclass
class AddrBatchItem:
    """`batch_fix_commands` 对**一条命令**的处理结果（不修改原命令）。"""

    index: int                   #: commands 里的原下标
    name: str
    status: str                  #: ok | kept | skipped
    data_hex: str                #: status == ok 时为替换后的帧，否则是原值
    protocol: Optional[int]      #: 要写入协议列的值（None = 不改该键）
    match_hex: str               #: 预期响应（原值，或同步替换后的值）
    match_changed: bool
    notes: List[str] = field(default_factory=list)  #: 地址域/校验 旧→新
    error: str = ""              #: kept / skipped 的可读原因


def fix_frame_text(data_hex: str, protocol_index,
                   values: Mapping[str, str]) -> Tuple[str, List[str], str]:
    """按协议替换地址并重算校验 → ``(新 hex, notes, error)``；error 非空表示**未改动**。

    前导 FEH：只对协议 6 / 8 剥离并**原样恢复**（依据 DL/T 645-2007 §5.3.1、
    DL/T 698.45-2017 §6.3.1 b)，见 AGENTS §8 陷阱 75）；其余协议规范里没有前导码，
    带 FE 的帧本就该报错，剥了等于「救活」错帧。

    成功后 hex 统一成**空格分隔**格式（与「加载报文文件」/ 导出同格式）。
    """
    raw = hex_str_to_bytes(data_hex)
    if raw is None:
        return str(data_hex or ""), [], f"发送数据不是有效的 HEX：{hex_input_error(data_hex)}"
    prefix = b""
    body = raw
    if coerce_protocol(protocol_index) in FE_WAKEUP_PROTOCOLS:
        body, stripped = wakeup_prefix.strip_wakeup_prefix(raw)
        prefix = raw[:stripped]
    result = frame_addr_fix.apply(body, protocol_index, values)
    if not result.ok:
        return str(data_hex or ""), [], str(result.error or "地址替换失败")
    return bytes_to_hex(prefix + bytes(result.frame)), list(result.notes), ""


def batch_fix_commands(commands: List[dict], indices: List[int], protocol_index,
                       values: Mapping[str, str], write_protocol: bool = True,
                       fix_match: bool = True) -> List[AddrBatchItem]:
    """批量替换：逐条给出「新值 / 原因」，**不修改 `commands`**（写回交给调用方）。

    - ``indices``：作用范围（勾选行或全部），非 int / 越界下标一律忽略；
    - ``write_protocol``：把协议索引写进作用范围内**每条**命令的 ``protocol`` 键
      （与单条替换成败无关 —— 「这批报文属于协议 X」是用户声明，写进去接收侧才能
      按该协议断帧解析）；协议非法（None）时不写；
    - ``fix_match``：只在发送数据**替换成功**时，对 ``match_type ∈ HEX_MATCH_TYPES``
      且非空的预期响应尝试同步替换；通配 / 正则 / 不匹配 / 自证失败一律保持原样并记入 notes。
    """
    proto = coerce_protocol(protocol_index)
    items: List[AddrBatchItem] = []
    for index in list(indices or []):
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        if not (0 <= index < len(commands)):
            continue
        cmd = commands[index] if isinstance(commands[index], dict) else {}
        raw_hex = str(cmd.get("data_hex") or "")
        item = AddrBatchItem(
            index=index,
            name=str(cmd.get("name") or "") or f"命令{index + 1}",
            status=ADDR_STATUS_SKIPPED,
            data_hex=raw_hex,
            protocol=None,
            match_hex=str(cmd.get("match_hex") or ""),
            match_changed=False,
        )
        if hex_str_to_bytes(raw_hex) is None:
            item.error = f"发送数据不是有效的 HEX：{hex_input_error(raw_hex)}"
        else:
            try:
                new_hex, notes, error = fix_frame_text(raw_hex, protocol_index, values)
            except Exception as exc:                     # noqa: BLE001 - 一条出错不许中断整批
                new_hex, notes, error = raw_hex, [], f"{type(exc).__name__}: {exc}"
            if error:
                item.status = ADDR_STATUS_KEPT
                item.error = error
            else:
                item.status = ADDR_STATUS_OK
                item.data_hex = new_hex
                item.notes = notes
                _fix_expected_response(cmd, item, protocol_index, values, fix_match)
        if write_protocol and proto is not None:
            item.protocol = proto
        items.append(item)
    return items


def _fix_expected_response(cmd: dict, item: AddrBatchItem, protocol_index,
                           values: Mapping[str, str], fix_match: bool) -> None:
    """（内部）同步替换预期响应里的地址 —— 只动**纯 HEX 写法**，且能自证才写回。"""
    if not fix_match or not item.match_hex.strip():
        return
    match_type = str(cmd.get("match_type") or "none")
    if match_type not in HEX_MATCH_TYPES:
        item.notes.append(
            f"预期响应未替换（匹配方式「{match_type_label(match_type)}」不是纯 HEX 写法）"
        )
        return
    try:
        new_match, _notes, error = fix_frame_text(item.match_hex, protocol_index, values)
    except Exception as exc:                             # noqa: BLE001 - 同上
        new_match, error = item.match_hex, f"{type(exc).__name__}: {exc}"
    if error:
        item.notes.append(f"预期响应未替换（{error}）")
        return
    item.match_hex = new_match
    item.match_changed = True
    item.notes.append("预期响应已同步替换地址并重算校验")


def addr_batch_summary(items: List[AddrBatchItem]) -> Tuple[str, str]:
    """汇总文案 ``(首行, 明细)``（纯逻辑，便于单测 / 弹框复用）。"""
    ok = [it for it in items if it.status == ADDR_STATUS_OK]
    kept = [it for it in items if it.status == ADDR_STATUS_KEPT]
    skipped = [it for it in items if it.status == ADDR_STATUS_SKIPPED]
    changed = [it for it in items if it.match_changed]

    head = f"已替换 {len(ok)} 条"
    if kept:
        head += f" / 未替换（自证失败）{len(kept)} 条"
    if skipped:
        head += f" / 跳过 {len(skipped)} 条"
    if changed:
        head += f"；其中 {len(changed)} 条的预期响应也同步替换"
    if not items:
        head = "作用范围内没有命令"

    lines = [f"· {it.name}：{it.error}" for it in (kept + skipped)[:3]]
    rest = len(kept) + len(skipped) - len(lines)
    if rest > 0:
        lines.append(f"· …另有 {rest} 条未替换（原因见日志与命令表）")
    return head, "\n".join(lines)


# ── 纯函数：命令归一化与配置持久化 ────────────────────────────────────

# 「不解析」在 UI 与数据模型里的表示（协议字段取 None）
PROTOCOL_NONE_LABEL = "不解析"

_PROTOCOL_COUNT_CACHE: Optional[int] = None


def protocol_count() -> int:
    """协议总数（懒加载 `protocol_registry`，失败回落 0 = 只能选「不解析」）。"""
    global _PROTOCOL_COUNT_CACHE
    if _PROTOCOL_COUNT_CACHE is None:
        try:
            import protocol_registry as pr

            _PROTOCOL_COUNT_CACHE = int(pr.protocol_count())
        except Exception:
            _PROTOCOL_COUNT_CACHE = 0
    return _PROTOCOL_COUNT_CACHE


def protocol_short_name(index: Optional[int]) -> str:
    """协议索引 → 短名（表格显示用）；None / 非法 → ``不解析``。"""
    if index is None:
        return PROTOCOL_NONE_LABEL
    try:
        import protocol_registry as pr

        return str(pr.get_protocol(int(index)).short_name)
    except Exception:
        return PROTOCOL_NONE_LABEL


def protocol_options() -> List[tuple]:
    """协议下拉选项：``[(显示名, 索引或 None), ...]``，首项为「不解析」。"""
    options: List[tuple] = [(PROTOCOL_NONE_LABEL, None)]
    try:
        import protocol_registry as pr

        for spec in pr.all_protocols():
            options.append((str(spec.name), int(spec.index)))
    except Exception:
        pass
    return options


def coerce_protocol(value) -> Optional[int]:
    """协议字段归一化：非法值一律 ``None``（不解析）。

    - ``None`` / ``bool``（``isinstance(True, int)`` 为真，必须先排除）→ None
    - 字符串数字（手改 JSON 的常见情况）容忍转换
    - 越界 / 非数字 → None
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, int):
        try:
            value = int(str(value).strip())
        except (TypeError, ValueError):
            return None
    if value < 0 or value >= protocol_count():
        return None
    return value


def coerce_enabled(value) -> bool:
    """勾选字段归一化；缺失/非法一律 ``True``。

    **老配置没有这个键 → 全选**，行为与「只能全部发送」的旧版本一致。
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("0", "false", "no", "off"):
        return False
    return True


def coerce_send_count(value) -> int:
    """命令级发送次数：每轮对该命令连发 N 次。默认 1，范围 1~9999。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    if n < 1:
        return 1
    if n > 9999:
        return 9999
    return n


def normalize_command(raw: dict, fallback_name: str = "未命名") -> Optional[dict]:
    """把一条命令归一化为 ``{name, data_hex, match_type, match_hex, protocol, enabled, send_count}``。

    发送数据非法（无法解析成 hex）时返回 None（该条丢弃）。
    """
    if not isinstance(raw, dict):
        return None
    data_hex = str(raw.get("data_hex", "") or "").strip()
    if hex_str_to_bytes(data_hex) is None:
        return None
    match_type = str(raw.get("match_type", "contains") or "contains")
    if match_type not in MATCH_TYPES:
        match_type = "contains"
    match_hex = str(raw.get("match_hex", "") or "").strip()
    if match_type == "regex":
        # 正则方式下「预期响应」是**正则表达式文本**（不是 HEX）：语法不合法才降级，
        # 绝不能按 HEX 校验 —— 否则任何正则都会被降级成「不匹配」，匹配永远不发生
        try:
            if not match_hex:
                raise re.error("正则表达式为空")
            re.compile(match_hex)
        except re.error:
            match_type = "none"
            match_hex = ""
    elif match_type == "hex_wildcard":
        # 通配方式下「预期响应」是 **HEX + XX 通配**（同样不能按纯 HEX 校验）
        if not parse_hex_wildcard(match_hex):
            match_type = "none"
            match_hex = ""
    elif match_type != "none" and match_hex and hex_str_to_bytes(match_hex) is None:
        # 预期响应非法：保留命令但降级为「不匹配」，避免整条丢失
        match_type = "none"
        match_hex = ""
    name = str(raw.get("name", "") or "").strip() or fallback_name
    return {
        "name": name,
        "data_hex": data_hex,
        "match_type": match_type,
        "match_hex": match_hex,
        # 旧配置无该键 → None（不解析），不报错、不丢其余字段
        "protocol": coerce_protocol(raw.get("protocol")),
        # 旧配置无该键 → True（全选），与旧版本「只能全部发送」等价
        "enabled": coerce_enabled(raw.get("enabled")),
        # 命令级发送次数（旧配置无该键 → 1）
        "send_count": coerce_send_count(raw.get("send_count", 1)),
    }


def normalize_commands(raw) -> List[dict]:
    """兼容两种输入：裸列表 ``[...]``（源工具格式）或 ``{"commands": [...]}``。"""
    if isinstance(raw, dict):
        raw = raw.get("commands", [])
    if not isinstance(raw, list):
        return []
    out: List[dict] = []
    for i, item in enumerate(raw):
        cmd = normalize_command(item, fallback_name=f"命令{i + 1}")
        if cmd:
            out.append(cmd)
    return out


def export_commands(commands: List[dict]) -> List[dict]:
    """导出为**裸列表**（与源工具 commands.json 双向兼容）。

    统一补齐 ``protocol`` / ``enabled`` 键并归一化（程序内直接构造的命令可能缺它们），
    并**剔除下划线开头的运行时键**（如 `_status` 状态图标）—— 运行态不该落盘，
    否则下次打开会显示上一次的旧状态。
    """
    out: List[dict] = []
    for cmd in commands:
        item = {k: v for k, v in cmd.items() if not str(k).startswith("_")}
        item["protocol"] = coerce_protocol(item.get("protocol"))
        item["enabled"] = coerce_enabled(item.get("enabled"))
        item["send_count"] = coerce_send_count(item.get("send_count", 1))
        out.append(item)
    return out


def merge_params(params: Optional[dict]) -> dict:
    """参数与默认值合并（缺失/类型不符回落到默认值）。"""
    merged = dict(DEFAULT_PARAMS)
    if not isinstance(params, dict):
        return merged
    for key, default in DEFAULT_PARAMS.items():
        if key not in params:
            continue
        value = params[key]
        if isinstance(default, bool):
            merged[key] = bool(value)
        elif isinstance(default, int):
            try:
                merged[key] = int(value)
            except (TypeError, ValueError):
                pass
        else:
            merged[key] = str(value)
    if merged.get("rx_mode") not in ("raw", "frame"):
        merged["rx_mode"] = "raw"
    if hex_str_to_bytes(str(merged.get("frame_tail", ""))) is None:
        merged["frame_tail"] = DEFAULT_FRAME_TAIL
    lo, hi = PARSE_MAX_LINES_RANGE
    try:
        lines = int(merged.get("parse_max_lines", DEFAULT_PARSE_MAX_LINES))
    except (TypeError, ValueError):
        lines = DEFAULT_PARSE_MAX_LINES
    merged["parse_max_lines"] = max(lo, min(hi, lines))   # 0 = 不限制
    # 断帧参数（1.23.78）：夹到合法范围（与 UI 的 spin range 共用 FRAME_TIMEOUT_RANGES）
    for key, (lo, hi) in FRAME_TIMEOUT_RANGES.items():
        try:
            value = int(merged.get(key, DEFAULT_PARAMS[key]))
        except (TypeError, ValueError):
            value = int(DEFAULT_PARAMS[key])
        merged[key] = max(lo, min(hi, value))
    if merged.get("rx_framing_mode") not in (FRAMING_MODE_AUTO, FRAMING_MODE_TIMEOUT):
        merged["rx_framing_mode"] = FRAMING_MODE_AUTO
    return merged


def migrate_params(params, version: int) -> dict:
    """按**配置版本**迁移参数（返回新 dict，不改原对象）。

    为什么要迁移：默认值改动只对「配置里没有这个键」生效，而参数一旦被保存过就
    会把**当时的默认值**也写进文件 —— 于是「改了默认值」对老用户完全不生效
    （实测报障：1.23.48 已把默认改成不限制，日志里仍显示「已省略 83 行」，因为
    1.23.47 那次运行把 30 存进了 `serial_tool_config.json`）。

    v1 → v2：`parse_max_lines == 30`（= v1 的默认值，不是用户特意选的）→ 改为新默认。
    用户显式设过的**其他**值一律保留。
    """
    out = dict(params) if isinstance(params, dict) else {}
    if version < 2 and out.get("parse_max_lines") == LEGACY_PARSE_MAX_LINES_DEFAULT:
        out["parse_max_lines"] = DEFAULT_PARSE_MAX_LINES
    return out


def load_config(path: str) -> Tuple[List[dict], dict]:
    """读取配置文件；缺失/损坏时回落（空命令 + 默认参数），不抛异常。

    同时接受本项目格式 ``{"version", "commands", "params"}`` 与源工具的裸列表。
    本项目格式会先按 ``version`` 做参数迁移（见 :func:`migrate_params`）。
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return [], dict(DEFAULT_PARAMS)
    if isinstance(raw, list):
        return normalize_commands(raw), dict(DEFAULT_PARAMS)
    if not isinstance(raw, dict):
        return [], dict(DEFAULT_PARAMS)
    try:
        version = int(raw.get("version", 1))
    except (TypeError, ValueError):
        version = 1
    params = migrate_params(raw.get("params"), version)
    return normalize_commands(raw), merge_params(params)


def save_config(path: str, commands: List[dict], params: dict) -> bool:
    """原子写配置（临时文件 + ``os.replace``）；失败返回 False（不抛异常）。"""
    payload = {
        "version": CONFIG_VERSION,
        "commands": export_commands(commands),
        "params": merge_params(params),
    }
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def export_commands_file(path: str, commands: List[dict]) -> bool:
    """导出为裸列表 JSON（源工具可直接加载）。"""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(export_commands(commands), fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def import_commands_file(path: str) -> List[dict]:
    """从 JSON 导入命令（裸列表或本项目格式），非法条目丢弃。"""
    commands, _params = load_config(path)
    return commands


# ── 纯逻辑：日志文件（自动保存）────────────────────────────────────────
#
# 目标：把「日志窗口里看到的东西」**原样**落到文件，方便事后offline 分析
# （现场不带电脑、只看日志文件即可复盘）。因此写入点挂在 GUI 的 `_log()`
# 单一出口上 —— 面板看到什么，文件里就有什么，不存在第二套过滤规则。

def format_log_time(now: Optional[datetime] = None) -> str:
    """日志时间戳（毫秒精度）：``2026-09-22 15:30:00.123``。"""
    now = now or datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def default_log_dir(data_dir) -> str:
    """默认日志目录：``<data_dir>/Output``。

    ``data_dir`` 由调用方给（本页传 ``app_paths.data_path`` 所在目录）——
    这样测试沙箱重定向数据目录时，日志目录**自动**跟着进沙箱，不会污染开发机。
    """
    return os.path.join(str(data_dir or "."), DEFAULT_LOG_DIR_NAME)


def log_file_name(now: Optional[datetime] = None) -> str:
    """日志文件名：``serial_log_20260922_153000.log``（秒级时间戳）。"""
    now = now or datetime.now()
    return f"{LOG_FILE_PREFIX}_{now.strftime('%Y%m%d_%H%M%S')}.log"


def unique_log_path(dir_path: str, name: str) -> str:
    """不覆盖已有文件：同名时追加 ``_1`` / ``_2`` …

    为什么需要：文件名只精确到秒，而「停止再开始保存」很可能在同一秒内发生
    —— 直接 ``open(..., "w")`` 会把上一段日志覆盖掉。宁可多一个文件也不丢数据。
    """
    base, ext = os.path.splitext(str(name))
    path = os.path.join(str(dir_path or "."), str(name))
    index = 0
    while os.path.exists(path):
        index += 1
        path = os.path.join(str(dir_path or "."), f"{base}_{index}{ext}")
    return path


def write_log_text(path: str, text: str) -> bool:
    """把一段文本写入文件（手动「保存当前日志…」用）；失败返回 False（不抛异常）。"""
    try:
        parent = os.path.dirname(str(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        body = str(text or "")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(body)
            if body and not body.endswith("\n"):
                fh.write("\n")
        return True
    except OSError:
        return False


def serial_context_text(worker) -> str:
    """串口上下文（日志文件头用）：``COM3 @ 115200`` / ``未获取`` / ``未连接``。

    只读展示，取不到就明确标出来 —— 这一行只是给场外看日志时定位环境用，
    不允许因为取不到而让保存失败。
    """
    if worker is None:
        return "未连接（端口与波特率由顶部「串口配置」管理）"
    port = str(getattr(worker, "_port", "") or "")
    baud = getattr(worker, "_baudrate", "")
    if not port:
        return "未获取（端口与波特率由顶部「串口配置」管理）"
    return f"{port} @ {baud}" if baud else port


class LogFileWriter:
    """日志文件写入器（**纯逻辑、无 Qt**，便于单测）。

    约定：
      - **写一行 flush 一次**：高速发送时最多几百行/秒（burst 已限流），
        换来「崩溃/断电也尽量保住已写内容」
      - ``text`` 含换行时**按物理行逐行**加时间戳前缀（不产生没有前缀的行）
      - **任何 ``OSError`` 都不抛给调用方**：置 :attr:`error`、关闭文件、返回 False
        （GUI 据此提示用户并关掉自动保存，而不是让日志系统把主流程带崩）
      - ``header`` / :meth:`write_raw` 写**原文行**（不加时间戳前缀），
        用于文件头的环境信息与文件尾的统计
    """

    def __init__(self, timestamp: bool = True):
        self.timestamp = bool(timestamp)
        self.path = ""
        self.line_count = 0
        self.byte_count = 0
        self.error = ""
        self._fh = None

    @property
    def is_open(self) -> bool:
        return self._fh is not None

    def open(self, dir_path, header=None, now: Optional[datetime] = None,
             name: Optional[str] = None) -> bool:
        """建目录 + 打开文件（同名不覆盖）并写文件头；失败置 ``error`` 返回 False。"""
        self.close()
        self.path = ""
        self.line_count = 0
        self.byte_count = 0
        self.error = ""
        try:
            os.makedirs(str(dir_path or "."), exist_ok=True)
            path = unique_log_path(dir_path, name or log_file_name(now))
            self._fh = open(path, "w", encoding="utf-8", newline="")
        except OSError as exc:
            self._fh = None
            self.error = str(exc)
            return False
        self.path = path
        for line in header or []:
            self.write_raw(line)
        return True

    def _write(self, lines: List[str]) -> bool:
        """底层写入（已含换行）；失败关闭文件并记录原因。

        捕获 ``ValueError`` 是必需的：句柄被外部关掉时 Python 抛的是
        ``ValueError: I/O operation on closed file``（**不是 OSError**），
        不捕就会把异常抛进 GUI 线程。
        """
        if self._fh is None:
            return False
        try:
            for line in lines:
                self._fh.write(line + "\n")
                self.byte_count += len(line.encode("utf-8")) + 1
            self._fh.flush()
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            self.close()
            return False
        self.line_count += len(lines)
        return True

    def write_line(self, text, now: Optional[datetime] = None) -> bool:
        """写一条日志（带时间戳前缀）；失败返回 False。"""
        if self._fh is None:
            return False
        stamp = format_log_time(now) if self.timestamp else ""
        physical = str(text).splitlines() or [""]
        lines = [f"{stamp} | {line}" if stamp else line for line in physical]
        return self._write(lines)

    def write_raw(self, text) -> bool:
        """写原文行（文件头 / 统计尾用，不加时间戳前缀）。"""
        if self._fh is None:
            return False
        physical = str(text).splitlines() or [""]
        return self._write(physical)

    def close(self) -> bool:
        """flush + 关闭（幂等）；失败返回 False（错误原因见 :attr:`error`）。"""
        fh = self._fh
        self._fh = None
        if fh is None:
            return True
        try:
            fh.flush()
            fh.close()
            return True
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            return False


# ══════════════════════════════════════════════════════════════════════
# GUI 与线程部分
# ══════════════════════════════════════════════════════════════════════

import time  # noqa: E402
from collections import deque  # noqa: E402

from PySide6.QtCore import Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QIcon,
    QPainter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import app_icons  # noqa: E402
import app_paths  # noqa: E402
import thread_registry  # noqa: E402
from gui_utils import ZoomableTableWidget, set_btn, set_btn_icon  # noqa: E402

# 日志颜色（与项目其它日志页风格一致）
_LOG_COLORS = {
    "tx": "#C00000",
    "rx": "#008000",
    "ok": "#008000",
    "fail": "#C00000",
    "sys": "#1565C0",
}

# 命令状态：图标（lucide 名，见 `app_icons`）+ 颜色。
# 颜色与日志配色对齐（ok/fail/sys），一眼能对上日志里的同一件事。
CMD_STATUS_STYLES: Dict[str, tuple] = {
    "": ("circle", "#9E9E9E"),               # 待测
    "running": ("loader", "#1565C0"),        # 发送中 / 等待响应
    "pass": ("check-circle", "#008000"),     # 通过（发送成功 / 匹配成功）
    "fail": ("x-circle", "#C00000"),         # 失败（超时未匹配 / 匹配失败）
    "error": ("alert-triangle", "#EF6C00"),  # 错误（写串口失败 / 串口错误）
}
CMD_STATUS_LABELS: Dict[str, str] = {
    "": "待测",
    "running": "发送中",
    "pass": "通过",
    "fail": "失败",
    "error": "错误",
}
# 命令字典里的**运行时**键（不落盘、不导出）
CMD_STATUS_KEY = "_status"
# 每次日志刷新时，队列超过该条数就只输出「摘要 + 首末帧」（高速发送防刷屏）
LOG_FLUSH_BURST = 20

# 「原始数据」接收模式的显示聚合窗口（毫秒）。
# 串口驱动常把**同一帧**拆成多次 read 交付（低波特率甚至逐字节），若按每次
# read 输出一行，一帧会被打成多行、RX 帧数也被虚增（实测报障）。
# 源工具用 1ms 静默聚合；这里取 10ms，兼容低波特率下逐字节交付的情形。
RAW_FLUSH_DELAY_MS = FRAME_TIMEOUT_DEFAULTS["rx_byte_idle_ms"]
# 聚合窗口的检查间隔（毫秒）
RAW_FLUSH_TICK_MS = 5
# 聚合缓冲最长持有时间（毫秒）。设备**持续流式**发送时读间隔始终小于静默窗口，
# 只靠静默判定会让缓冲无界增长且永不显示；超过该时长强制刷出（作为一行）。
RAW_MAX_HOLD_MS = FRAME_TIMEOUT_DEFAULTS["rx_raw_max_hold_ms"]
# 已声明整帧长度、但还没收全时的容忍静默（毫秒）。实测串口驱动把一帧拆成多次交付时，
# 交付块间隔可 **大于 10ms 静默窗口**（208 字节的国网帧被拆成 4 行即为实例），
# 所以一旦长度域已给出整帧长度，就不必再靠猜——按结构等到收全为止。
FRAME_IDLE_MS = FRAME_TIMEOUT_DEFAULTS["rx_frame_idle_ms"]
# 已声明长度帧的绝对等待上限（毫秒），防设备中途断流导致缓冲一直挂着
FRAME_HOLD_MAX_MS = FRAME_TIMEOUT_DEFAULTS["rx_frame_hold_max_ms"]

# 匹配用「累积接收缓冲」上限（字节）。串口驱动会把一帧拆成多次交付（实测 208 字节
# 的国网帧被拆成 77+92+36+3 四块），按**单次交付**比对会让「预期 = 整帧」永远匹配
# 不上 —— 实测报障。故匹配改为按累积数据比对，本上限只防缓冲无界增长。
MATCH_BUFFER_MAX = 8192
# 匹配失败诊断日志里 HEX 预览的字节上限
MATCH_DIAG_HEX_MAX = 96


# ── 纯函数：按协议分帧 ────────────────────────────────────────────────
#
# 分帧族（策略表 + 长度推算 + 「已开始未收全」判定）**原样搬至 `frame_deframe`**
# （纯逻辑、无 Qt），本模块经顶部 `from frame_deframe import …` **保留同名 re-export**
# ⇒ `stw.frame_length_for` / `stw.declared_frame_len` / `stw._wakeup_base` 等既有测试锚点
# 与行为一字不变。改判据请改 frame_deframe，**不要**在这里再写一份。


def format_parse_rows(table_data, max_lines: int = DEFAULT_PARSE_MAX_LINES) -> List[str]:
    """解析表 → 日志文字行（缩进 4 空格）。

    每行 ``字段名 = 解析值``（解析值为空时用原始值），有说明时追加 ``  <说明>``；
    字段名或值全空的行跳过（避免出现 `` = `` 这种空行）。``max_lines <= 0`` 表示
    **不限制**；否则超过时截断并追加省略提示。
    """
    rows: List[str] = []
    for item in table_data or []:
        try:
            name = str(item[0] or "").strip()
            raw_val = str(item[1] or "").strip()
            parsed = str(item[2] or "").strip()
            note = str(item[3] or "").strip()
        except (IndexError, TypeError):
            continue
        value = parsed or raw_val
        if not name or not value:
            continue
        line = f"    {name} = {value}"
        if note:
            line += f"  {note}"
        rows.append(line)
    total = len(rows)
    if max_lines and max_lines > 0 and total > max_lines:
        rows = rows[:max_lines]
        rows.append(f"    …（共 {total} 行，已省略 {total - max_lines} 行）")
    return rows


class SerialSendWorker(QThread):
    """精确间隔发送线程（照搬源工具 SenderThread 的时序语义）。

    - ``loop_count == 0`` 表示无限循环，由 :meth:`stop` 终止
    - 间隔 > 5ms：先 ``sleep(interval - 2ms)``，再用忙等补足尾段，保证精度
    - 发送走 :meth:`SerialWorker.write_raw`（静默，不逐帧发日志信号）
    - ``index_map``：只发**勾选**的命令时，``messages`` 是筛选后的子集，
      但 ``sent`` 里的 ``msg_index`` 必须回指 ``commands`` 的**原下标**
      （名称 / 协议 / 匹配规则都按它取），否则会张冠李戴。
    """

    sent = Signal(int, int, bytes)   # seq（从 0 起）, msg_index, data
    done = Signal()
    failed = Signal(str)

    def __init__(self, worker, messages: List[bytes],
                 interval_ms: float = 1.0, loop_count: int = 1, parent=None,
                 index_map: Optional[List[int]] = None):
        super().__init__(parent)
        self._worker = worker
        self._messages = list(messages)
        self._index_map = list(index_map) if index_map is not None else None
        self._interval_s = max(0.0, float(interval_ms) / 1000.0)
        self._loop_count = int(loop_count)
        self._stop = False

    def stop(self):
        self._stop = True

    def _msg_index(self, i: int) -> int:
        """``messages`` 下标 → ``commands`` 原下标（无 index_map 时恒等）。"""
        if self._index_map is None:
            return i
        return self._index_map[i] if 0 <= i < len(self._index_map) else i

    def run(self):
        loop = 0
        seq = 0
        while True:
            if self._loop_count > 0 and loop >= self._loop_count:
                break
            loop += 1
            last_index = len(self._messages) - 1
            for i, msg in enumerate(self._messages):
                if self._stop:
                    self.done.emit()
                    return
                if not self._worker.write_raw(msg):
                    self.failed.emit(f"第 {seq + 1} 帧发送失败")
                    return
                # msg_index 回指 commands 的原下标（只发勾选项时两者不同）
                self.sent.emit(seq, self._msg_index(i), msg)
                seq += 1
                # 最后一条命令（且不是无限循环）后不再延时
                is_last = (i == last_index and self._loop_count > 0
                           and loop >= self._loop_count)
                if is_last or self._interval_s <= 0:
                    continue
                target = time.perf_counter() + self._interval_s
                if self._interval_s > 0.005:
                    sleep_time = self._interval_s - 0.002
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                while time.perf_counter() < target:
                    pass
        self.done.emit()


class SerialCommandDialog(QDialog):
    """添加/编辑一条串口命令。"""

    def __init__(self, parent=None, command: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("编辑命令" if command else "添加命令")
        self.setMinimumWidth(520)

        form = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("命令名称，如 读取版本")
        form.addRow("名称：", self.name_edit)

        self.data_edit = QLineEdit()
        self.data_edit.setPlaceholderText("HEX 数据，如 68 11 00 40 …（连续写 681100… 也可以）")
        form.addRow("发送数据 (HEX)：", self.data_edit)

        self.match_type_combo = QComboBox()
        for key, label in MATCH_TYPES.items():
            self.match_type_combo.addItem(label, key)
        self.match_type_combo.setCurrentIndex(
            self.match_type_combo.findData("contains")
        )
        self.match_type_combo.currentIndexChanged.connect(self._on_match_type_changed)
        form.addRow("匹配方式：", self.match_type_combo)

        self.match_edit = QLineEdit()
        self.match_edit.setPlaceholderText("预期响应的 HEX 数据（匹配方式选「正则表达式」时填正则文本）")
        form.addRow("预期响应 (HEX)：", self.match_edit)

        # 协议：提前告知该命令属于哪个协议 → 接收时按它断帧 + 解析（「不解析」= 不参与）
        self.protocol_combo = QComboBox()
        for label, index in protocol_options():
            self.protocol_combo.addItem(label, index)
        self.protocol_combo.setCurrentIndex(0)          # 默认「不解析」
        self.protocol_combo.setToolTip(
            "该命令的协议：接收到的响应会按它断帧并解析输出；\n"
            "「不解析」= 只显示原始 HEX（与旧版本行为一致）"
        )
        form.addRow("协议：", self.protocol_combo)

        self.send_count_spin = QSpinBox()
        self.send_count_spin.setRange(1, 99999)
        self.send_count_spin.setValue(1)
        self.send_count_spin.setFixedWidth(90)
        self.send_count_spin.setToolTip(
            "本条命令每轮连续发送的次数（表内「次数」列）。\n"
            "与底部「循环次数」相乘：例如次数=3、循环=2 → 本命令共发 6 次"
        )
        form.addRow("发送次数：", self.send_count_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if command:
            self.name_edit.setText(command.get("name", ""))
            self.data_edit.setText(command.get("data_hex", ""))
            idx = self.match_type_combo.findData(command.get("match_type", "contains"))
            if idx >= 0:
                self.match_type_combo.setCurrentIndex(idx)
            self.match_edit.setText(command.get("match_hex", ""))
            proto_idx = self.protocol_combo.findData(
                coerce_protocol(command.get("protocol"))
            )
            if proto_idx >= 0:
                self.protocol_combo.setCurrentIndex(proto_idx)
            self.send_count_spin.setValue(
                coerce_send_count(command.get("send_count", 1))
            )
        self._on_match_type_changed()

    def _on_match_type_changed(self):
        match_type = self.match_type_combo.currentData()
        self.match_edit.setEnabled(match_type != "none")
        if match_type == "hex_wildcard":
            self.match_edit.setPlaceholderText(
                "HEX + XX 通配，如 68 D0 XX XX 16（XX = 任意字节）"
            )
            self.match_edit.setToolTip(
                "「HEX 通配」写法（与「测试方案」的 XX 通配同一约定）：\n"
                "  · 每字节 2 个 hex 字符，空格可省（68D0XXXX16 也行）\n"
                "  · XX（或 ??）= 任意一个字节，跳过该字节的比较\n"
                "  · 默认在收到数据里**任意位置**查找\n"
                "  · 需要锚定：开头写 ^、结尾写 $（如 ^68D0XX 或 XX16$）"
            )
        elif match_type == "regex":
            self.match_edit.setPlaceholderText("正则文本，如 \\x68\\s*\\xD0")
            self.match_edit.setToolTip(
                "正则在**字节按 latin-1 解码后的字符流**上匹配（re.search，忽略大小写）：\n"
                "  · 字节要写 \\xNN，直接写 hex 数字匹配不上（68 ≠ 字节 0x68）\n"
                "  · . = 任意字节但**不匹配 0x0A**，请用 [\\s\\S]\n"
                "  · 忽略大小写会让 \\x68 也匹配 0x48、\\xD0 也匹配 0xF0\n"
                "  · 二进制帧建议改用「HEX 通配」"
            )
        else:
            self.match_edit.setPlaceholderText("预期响应的 HEX 数据")
            self.match_edit.setToolTip("")

    def _on_ok(self):
        data_text = self.data_edit.text()
        if hex_str_to_bytes(data_text) is None:
            QMessageBox.warning(
                self, "数据无效",
                f"发送数据不是有效的 HEX：{hex_input_error(data_text)}"
            )
            return
        match_type = self.match_type_combo.currentData()
        match_text = self.match_edit.text()
        if match_type == "hex_wildcard":
            if not parse_hex_wildcard(match_text):
                QMessageBox.warning(
                    self, "数据无效",
                    "HEX 通配模式无效：每字节需要 2 个 hex 字符，"
                    "XX（或 ??）表示任意字节"
                )
                return
        elif match_type == "regex":
            # 正则匹配方式下「预期响应」是**正则表达式文本**，不是 HEX
            if not match_text.strip():
                QMessageBox.warning(self, "数据无效", "正则表达式为空")
                return
            try:
                re.compile(match_text)
            except re.error as exc:
                QMessageBox.warning(self, "数据无效", f"正则表达式无效：{exc}")
                return
        elif match_type != "none" and hex_str_to_bytes(match_text) is None:
            QMessageBox.warning(
                self, "数据无效",
                f"预期响应不是有效的 HEX：{hex_input_error(match_text)}"
            )
            return
        self.accept()

    def get_command(self) -> dict:
        return {
            "name": self.name_edit.text().strip() or "未命名",
            "data_hex": self.data_edit.text().strip(),
            "match_type": self.match_type_combo.currentData(),
            "match_hex": self.match_edit.text().strip(),
            "protocol": coerce_protocol(self.protocol_combo.currentData()),
            "send_count": coerce_send_count(self.send_count_spin.value()),
        }


class BatchAddrDialog(QDialog):
    """批量替换通信地址：选协议 + 填地址 + 选作用范围。

    界面**不硬编码协议细节**：地址输入行按 `frame_addr_fix.fields_for(协议)` 动态生成，
    标签与占位提示都来自字段声明（与蓝牙页 `ButtonEditDialog` 的地址区同一范式）。

    长度校验的分工：这里只拦「空地址 / 写法非法」（698 的 SA 长度由帧内地址特征字节决定，
    此处无法推导，按「待定」放行）；**精确长度与帧结构自证由 `frame_addr_fix.apply` 负责**
    （预览行与执行结果都会给出可读结论）。
    """

    def __init__(self, parent=None, commands=None, checked_indices=None):
        super().__init__(parent)
        self.setWindowTitle("批量替换通信地址")
        self.setMinimumWidth(560)
        self._commands = list(commands or [])
        self._checked = [i for i in (checked_indices or [])
                         if isinstance(i, int) and not isinstance(i, bool)
                         and 0 <= i < len(self._commands)]
        self._addr_edits: Dict[str, QLineEdit] = {}
        self._addr_values: Dict[str, str] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_protocol = QComboBox()
        for label, index in frame_addr_fix.supported_choices():
            self.combo_protocol.addItem(label, index)
        self.combo_protocol.setToolTip(
            "按这个协议替换地址域并重算校验（地址位置/字节序/校验算法都取自该协议自身实现）"
        )
        self.combo_protocol.currentIndexChanged.connect(self._rebuild_addr_fields)
        form.addRow("协议：", self.combo_protocol)

        self.combo_scope = QComboBox()
        self.combo_scope.addItem(f"勾选的命令（{len(self._checked)} 条）", "checked")
        self.combo_scope.addItem(f"全部命令（{len(self._commands)} 条）", "all")
        # 没有勾选任何命令时默认「全部」（否则作用范围恒为空）
        self.combo_scope.setCurrentIndex(0 if self._checked else 1)
        self.combo_scope.currentIndexChanged.connect(self._refresh_hint)
        form.addRow("作用范围：", self.combo_scope)

        self.chk_write_protocol = QCheckBox("同时把该协议写入这些命令的「协议」列")
        self.chk_write_protocol.setChecked(True)
        self.chk_write_protocol.setToolTip(
            "「加载报文文件」导入的报文协议为空 → 写入后接收侧才能按该协议断帧并解析响应"
        )
        form.addRow("", self.chk_write_protocol)

        self.chk_fix_match = QCheckBox("同时替换「预期响应」中的地址")
        self.chk_fix_match.setChecked(True)
        self.chk_fix_match.setToolTip(
            "只处理纯 HEX 写法的预期响应（包含/完全相等/开头匹配/结尾匹配），"
            "且必须能通过结构+校验自证才替换；通配 / 正则 / 自证失败一律保持原样"
        )
        form.addRow("", self.chk_fix_match)
        layout.addLayout(form)

        self.addr_group = QGroupBox("地址参数（替换地址域并重算校验）")
        self.addr_form = QFormLayout(self.addr_group)
        self.addr_form.setSpacing(6)
        self.lbl_addr_hint = QLabel("")
        self.lbl_addr_hint.setWordWrap(True)
        self.addr_form.addRow(self.lbl_addr_hint)
        layout.addWidget(self.addr_group)

        self.lbl_preview = QLabel("")
        self.lbl_preview.setWordWrap(True)
        layout.addWidget(self.lbl_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._rebuild_addr_fields()

    # ── 取值接口 ────────────────────────────────────────────────────────

    def protocol_index(self) -> Optional[int]:
        data = self.combo_protocol.currentData()
        return int(data) if data is not None else None

    def scope(self) -> str:
        return str(self.combo_scope.currentData() or "checked")

    def scope_indices(self) -> List[int]:
        if self.scope() == "all":
            return list(range(len(self._commands)))
        return list(self._checked)

    def write_protocol(self) -> bool:
        return bool(self.chk_write_protocol.isChecked())

    def fix_match(self) -> bool:
        return bool(self.chk_fix_match.isChecked())

    def values(self) -> Dict[str, str]:
        return {key: edit.text().strip() for key, edit in self._addr_edits.items()}

    # ── 地址输入区 ──────────────────────────────────────────────────────

    def _rebuild_addr_fields(self):
        """按所选协议重建地址输入行（字段声明来自 `frame_addr_fix`）。"""
        for key, edit in list(self._addr_edits.items()):
            self._addr_values[key] = edit.text()
            edit.deleteLater()
        self._addr_edits = {}
        while self.addr_form.rowCount() > 1:          # 末行是提示，保留
            self.addr_form.removeRow(0)

        index = self.protocol_index()
        fields = frame_addr_fix.fields_for(index) if index is not None else ()
        self.addr_group.setVisible(bool(fields))
        if not fields:
            self.lbl_addr_hint.setText("")
            self._refresh_hint()
            return
        for position, spec in enumerate(fields):
            edit = QLineEdit(self._addr_values.get(spec.key, ""))
            edit.setPlaceholderText(spec.hint)
            edit.textChanged.connect(self._refresh_hint)
            self._addr_edits[spec.key] = edit
            self.addr_form.insertRow(position, f"{spec.label}：", edit)
        self._refresh_hint()

    def _refresh_hint(self):
        """回显「地址会写成什么字节」+ 作用范围内样例命令的替换预览。"""
        if not hasattr(self, "lbl_addr_hint"):
            return
        index = self.protocol_index()
        fields = frame_addr_fix.fields_for(index) if index is not None else ()
        values = self.values()
        filled = {key: text for key, text in values.items() if text}

        good, bad = [], []
        for spec in fields:
            text = values.get(spec.key, "")
            if not text:
                continue
            data, err = frame_addr_fix.parse_address(text, spec, spec.length)
            if err and spec.kind == frame_addr_fix.KIND_SA698:
                good.append(f"· {spec.label}：长度按帧内地址特征确定")
            elif err:
                bad.append(f"⚠ {spec.label}：{err}")
            else:
                good.append(f"· {spec.label} → {data.hex(' ').upper()}（{len(data)} 字节）")
        self.lbl_addr_hint.setText(
            "\n".join(good + bad)
            or "填写地址后：确定即替换作用范围内每条命令的地址并重算校验"
        )
        self.lbl_preview.setText(self._preview_text(index, filled))

    def _sample_command(self) -> Optional[dict]:
        """作用范围内第一条「发送数据能解析成 HEX」的命令（预览样例）。"""
        for i in self.scope_indices()[:20]:
            cmd = self._commands[i]
            if hex_str_to_bytes(str(cmd.get("data_hex") or "")) is not None:
                return cmd
        return None

    def _preview_text(self, index, filled: Dict[str, str]) -> str:
        if not filled:
            return ""
        sample = self._sample_command()
        if sample is None:
            return "预览：作用范围内没有可解析的发送数据"
        name = str(sample.get("name") or "样例")
        new_hex, notes, error = fix_frame_text(str(sample.get("data_hex") or ""), index, filled)
        if error:
            return f"预览（{name}）：⚠ 未替换 —— {error}"
        body = "\n  ".join(notes) if notes else new_hex
        return f"预览（{name}）：\n  {body}"

    # ── 确定 ────────────────────────────────────────────────────────────

    def _on_accept(self):
        index = self.protocol_index()
        values = self.values()
        if not values:
            QMessageBox.warning(self, "未选择协议", "请选择要替换的协议。")
            return
        if not any(values.values()):
            QMessageBox.warning(
                self, "未填地址", "请至少填写一个地址（地址为空时替换必然失败）。"
            )
            return
        if not self.scope_indices():
            QMessageBox.warning(
                self, "作用范围为空",
                "所选作用范围内没有命令：请先在命令表「选择」列勾选，或把范围改成「全部命令」。",
            )
            return
        fields = {spec.key: spec for spec in frame_addr_fix.fields_for(index)}
        for key, text in values.items():
            spec = fields.get(key)
            if spec is None or not text:
                continue
            _data, err = frame_addr_fix.parse_address(text, spec, spec.length)
            # 698 SA 的长度由帧内地址特征字节决定，这里推导不出 → 交给 apply 判定
            if err and spec.kind == frame_addr_fix.KIND_SA698:
                continue
            if err:
                QMessageBox.warning(self, "地址无效", f"{spec.label}：{err}")
                return
        self.accept()


class SerialToolWidget(QWidget):
    """串口工具页：命令发送 + 响应匹配 + 统计 + 彩色日志。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands: List[dict] = []
        self._params = dict(DEFAULT_PARAMS)
        # 重建命令表期间抑制 itemChanged 回写（否则逐行触发落盘）
        self._rebuilding_cmd_table = False
        # 用属性访问（不是 from ... import data_path）：便于测试用
        # `_config_sandbox` patch `app_paths.data_path` 把落盘重定向到沙箱
        self._config_path = str(app_paths.data_path(CONFIG_NAME))

        # 串口：**复用主窗口共享的 SerialWorker**（与组帧页/监控器页同一约定）。
        # 端口/波特率/校验只在顶部「串口配置」里设置；本页只订阅信号。
        # 为什么不在本页另起一套串口：一个 COM 口只能被打开一次，各页各持一个
        # worker 会互相抢口（顶栏连上后本页再连必失败），且波特率会出现两处配置。
        self._serial_worker = None

        # 解析：由 main_gui 注入回调（本页不 import main_gui，见 set_parse_provider）
        self._parse_provider = None
        # 最近一次发送命令的协议（接收断帧 + 解析都用它；None = 不解析）
        self._last_tx_protocol: Optional[int] = None

        # 发送
        self._sender: Optional[SerialSendWorker] = None
        self._running = False
        self._send_start_time = 0.0
        self._finalize_elapsed = 0.0
        # 发送代次：上一轮遗留的收尾定时器不得影响新一轮发送
        self._send_generation = 0

        # 批量替换通信地址的撤销点：[(原下标, (原 data_hex, 原 protocol, 原 match_hex)), …]
        # 只保留最近一次（再次替换即覆盖）；命令被删除/移动后越界条目会被自动忽略
        self._addr_batch_undo: List[tuple] = []

        # 匹配
        self._tx_total = 0
        self._rx_matched = 0
        self._rx_missed = 0
        self._pending_match: deque = deque()
        # 累积接收缓冲：串口驱动把一帧拆成多次交付，按单次交付比对会漏配（实测报障）。
        # 每次「发送」清空（一问一答的窗口从这里重新开始）；队列清空时也清空。
        self._match_buffer = bytearray()
        self._match_rx_bytes = 0        # 本窗口收到的总字节数（诊断用）

        # 接收分帧
        self._frame_buffer = bytearray()
        self._frame_tail = b"\xfe\x16"
        # 原始模式的显示聚合缓冲（静默 RAW_FLUSH_DELAY_MS 后作为一帧刷出）
        self._raw_buffer = bytearray()
        self._raw_last_time = 0.0
        # 当前聚合缓冲的起始时刻（用于 RAW_MAX_HOLD_MS 强制刷出，防持续流无界增长）
        self._raw_first_time = 0.0
        self._rx_frames = 0
        self._rx_bytes = 0
        self._tx_frames = 0
        self._tx_bytes = 0

        # 日志队列（批量刷出，防高速发送刷屏）
        self._tx_log_queue: deque = deque()
        self._rx_log_queue: deque = deque()

        # 日志文件（自动保存）：写入点挂在 _log() 上 —— 面板看到什么，文件就有什么
        self._log_writer: Optional[LogFileWriter] = None
        self._log_last_path = ""
        self._log_last_lines = 0

        # 落盘定时器必须**先于** `_build_ui()/_load_persisted()` 建好：
        # 载入持久化参数时会触发接收模式等控件的 `toggled` → `_schedule_save()`，
        # 那时若还没有 `_save_timer`，信号槽里会抛 AttributeError（Qt 会吞掉，
        # 但配置保存随之静默失效）。
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_persisted)

        self._build_ui()
        self._load_persisted()

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._poll_stats)
        self._stats_timer.start(200)

        self._match_timer = QTimer(self)
        self._match_timer.timeout.connect(self._check_match_timeout)
        self._match_timer.start(100)

        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._flush_log_queues)
        self._log_timer.start(LOG_FLUSH_MS)

        # 原始模式的静默聚合刷出（把同一帧的多次 read 合并成一行）
        self._raw_flush_timer = QTimer(self)
        self._raw_flush_timer.timeout.connect(self._flush_raw_display)
        self._raw_flush_timer.start(RAW_FLUSH_TICK_MS)

        self._on_connection_changed(False)   # 串口未接入前，发送按钮置灰
        self._log("[系统] 串口工具就绪：添加命令 → 在顶部「串口配置」连接串口 → 开始发送",
                  "sys")

    # ── UI ───────────────────────────────────────────────────────────

    def set_serial_worker(self, worker):
        """绑定主窗口共享的串口线程（与 `frame_gen_widget`/`monitor_widget` 同一约定）。

        只订阅信号，不负责打开/关闭端口：端口的生命周期归顶部「串口配置」。
        """
        old = getattr(self, "_serial_worker", None)
        if old is not None:
            for signal, slot in (
                (old.raw_data_received, self._on_raw_data),
                (old.error_occurred, self._on_serial_error),
                (old.connection_changed, self._on_connection_changed),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self._serial_worker = worker
        if worker is None:
            self._on_connection_changed(False)
            return
        worker.raw_data_received.connect(self._on_raw_data)
        worker.error_occurred.connect(self._on_serial_error)
        worker.connection_changed.connect(self._on_connection_changed)
        self._on_connection_changed(worker.is_open())

    def set_parse_provider(self, provider):
        """注入解析回调（由 `main_gui` 提供，与 `set_serial_worker` 同一约定）。

        ``provider(frame_bytes, protocol_index) -> (摘要, table_data)``，可为 None
        （此时「显示解析」不产生任何输出）。本页**不** import `main_gui`，避免
        与主窗口循环依赖。
        """
        self._parse_provider = provider

    def _on_connection_changed(self, connected: bool):
        """跟随顶部串口配置的连接状态（只读展示 + 控制发送按钮可用性）。"""
        if connected:
            self.lbl_conn.setText("已连接")
            self.lbl_conn.setStyleSheet("color: #008000;")
        else:
            self.lbl_conn.setText("未连接")
            self.lbl_conn.setStyleSheet("color: #888;")
        self.btn_start.setEnabled(bool(connected))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 串口控制
        # 串口状态（只读）：端口/波特率在顶部「串口配置」里设置，本页跟随其状态
        ctrl_group = QGroupBox("串口")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(6)
        ctrl_layout.addWidget(QLabel("连接状态："))
        self.lbl_conn = QLabel("未连接")
        self.lbl_conn.setStyleSheet("color: #888;")
        ctrl_layout.addWidget(self.lbl_conn)
        self.lbl_port = QLabel("")
        self.lbl_port.setStyleSheet("color: #888;")
        ctrl_layout.addWidget(self.lbl_port)
        ctrl_layout.addStretch()
        hint = QLabel("端口的连接/断开与波特率请在顶部「串口配置」中设置")
        hint.setStyleSheet("color: #888;")
        ctrl_layout.addWidget(hint)
        layout.addWidget(ctrl_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左：命令表 + 发送配置 + 接收模式
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        cmd_group = QGroupBox("命令列表")
        cmd_layout = QVBoxLayout(cmd_group)
        cmd_layout.setContentsMargins(6, 8, 6, 6)
        self.cmd_table = ZoomableTableWidget()
        self.cmd_table.setColumnCount(7)
        self.cmd_table.setHorizontalHeaderLabels(
            ["选择", "名称", "发送数据 (HEX)", "匹配方式", "预期响应", "协议", "次数"]
        )
        self.cmd_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cmd_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cmd_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cmd_table.setAlternatingRowColors(True)
        self.cmd_table.verticalHeader().hide()
        chdr = self.cmd_table.horizontalHeader()
        chdr.setSectionResizeMode(0, QHeaderView.Fixed)
        chdr.setSectionResizeMode(1, QHeaderView.Interactive)
        chdr.setSectionResizeMode(2, QHeaderView.Stretch)
        chdr.setSectionResizeMode(3, QHeaderView.Fixed)
        chdr.setSectionResizeMode(4, QHeaderView.Stretch)
        chdr.setSectionResizeMode(5, QHeaderView.Fixed)
        chdr.setSectionResizeMode(6, QHeaderView.Fixed)
        self.cmd_table.setColumnWidth(0, 50)
        self.cmd_table.setColumnWidth(1, 120)
        self.cmd_table.setColumnWidth(3, 90)
        self.cmd_table.setColumnWidth(5, 110)
        self.cmd_table.setColumnWidth(6, 52)
        self.cmd_table.verticalHeader().setDefaultSectionSize(20)
        # 勾选状态变化 → 回写命令并落盘（见 _on_cmd_item_changed）
        self.cmd_table.itemChanged.connect(self._on_cmd_item_changed)
        # 双击命令行 → 直接打开该条的编辑窗口（等价于选中后点「编辑」）
        self.cmd_table.setToolTip(
            "双击某一行可直接编辑该命令（含发送次数）；勾选「选择」列决定发送哪些命令"
        )
        self.cmd_table.cellDoubleClicked.connect(self._on_cmd_double_clicked)
        cmd_layout.addWidget(self.cmd_table, 1)

        # 勾选操作行：只发勾选的命令（按表内顺序）
        sel_row = QHBoxLayout()
        sel_row.setSpacing(6)
        for text, icon, slot in (
            ("全选", "ok", lambda: self._set_all_checkboxes(True)),
            ("全不选", "clear", lambda: self._set_all_checkboxes(False)),
            ("反选", "refresh", self._invert_checkboxes),
        ):
            btn = QPushButton(text)
            set_btn(btn, "secondary")
            set_btn_icon(btn, icon)
            btn.clicked.connect(slot)
            sel_row.addWidget(btn)
        self.lbl_cmd_sel = QLabel("已选 0 / 0 条")
        sel_row.addWidget(self.lbl_cmd_sel)
        sel_row.addStretch()
        legend = QLabel("状态图标：○ 待测  ↻ 发送中  ✓ 通过  ✗ 失败  ⚠ 错误")
        legend.setToolTip(
            "名称列前的图标表示该命令本轮的结果：\n"
            "  ○ 灰 = 待测（本轮尚未发出）\n"
            "  ↻ 蓝 = 发送中（已发出，等待响应匹配）\n"
            "  ✓ 绿 = 通过（发送成功；启用匹配时表示已匹配上）\n"
            "  ✗ 红 = 失败（响应超时未匹配）\n"
            "  ⚠ 橙 = 错误（写串口失败 / 发送出错）"
        )
        sel_row.addWidget(legend)
        self.btn_clear_status = QPushButton("清除状态")
        set_btn(self.btn_clear_status, "secondary")
        set_btn_icon(self.btn_clear_status, "clear")
        self.btn_clear_status.setToolTip(
            "把所有命令的状态图标重置为「待测」\n"
            "（只清运行态图标，不影响命令内容与勾选；每轮发送开始时也会自动重置）"
        )
        self.btn_clear_status.clicked.connect(self._clear_cmd_status_clicked)
        sel_row.addWidget(self.btn_clear_status)
        cmd_layout.addLayout(sel_row)

        cmd_btns = QHBoxLayout()
        cmd_btns.setSpacing(6)
        for text, icon, slot in (
            ("添加", "add", self._add_command),
            ("编辑", "edit", self._edit_command),
            ("删除", "delete", self._delete_command),
            ("上移", "up", self._move_command_up),
            ("下移", "down", self._move_command_down),
        ):
            btn = QPushButton(text)
            set_btn(btn, "secondary")
            set_btn_icon(btn, icon)
            btn.clicked.connect(slot)
            cmd_btns.addWidget(btn)
        cmd_btns.addStretch()
        for text, icon, slot in (
            ("保存配置", "save", self._export_commands),
            ("加载配置", "open", self._import_commands),
            ("加载报文文件", "open_file", self._load_message_file),
        ):
            btn = QPushButton(text)
            set_btn(btn, "secondary")
            set_btn_icon(btn, icon)
            btn.clicked.connect(slot)
            cmd_btns.addWidget(btn)
        # 批量替换通信地址（按协议替换地址域 + 重算校验 + 可撤销）
        self.btn_batch_addr = QPushButton("替换地址")
        set_btn(self.btn_batch_addr, "secondary")
        set_btn_icon(self.btn_batch_addr, "refresh")
        self.btn_batch_addr.setToolTip(
            "批量替换通信地址：按所选协议把作用范围内每条命令的地址域换成现场表计地址，\n"
            "并重算校验（改地址后校验必然变，否则对端直接丢帧）；\n"
            "可同时把协议写入命令的「协议」列、并同步替换「预期响应」中的地址；\n"
            "替换后记得核对命令表内容（一次批量替换可撤销一次）"
        )
        self.btn_batch_addr.clicked.connect(self._on_batch_addr_clicked)
        cmd_btns.addWidget(self.btn_batch_addr)
        cmd_layout.addLayout(cmd_btns)
        left_layout.addWidget(cmd_group, 1)

        # 发送配置
        send_group = QGroupBox("发送配置")
        send_layout = QHBoxLayout(send_group)
        send_layout.setSpacing(6)
        send_layout.addWidget(QLabel("发送间隔(ms)："))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 10000)
        self.interval_spin.setValue(DEFAULT_PARAMS["interval_ms"])
        self.interval_spin.setFixedWidth(70)
        send_layout.addWidget(self.interval_spin)

        send_layout.addWidget(QLabel("循环次数："))
        self.loop_spin = QSpinBox()
        self.loop_spin.setRange(0, 999999)
        self.loop_spin.setValue(DEFAULT_PARAMS["loop_count"])
        self.loop_spin.setSpecialValueText("无限")
        self.loop_spin.setFixedWidth(80)
        self.loop_spin.setToolTip(
            "整轮命令列表循环发送的次数；0=无限。\n"
            "与命令表「次数」列（单条连发）相乘：例如表内次数=3、循环=2 → 该命令共发 6 次"
        )
        send_layout.addWidget(self.loop_spin)

        send_layout.addWidget(QLabel("响应超时(ms)："))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 600000)
        self.timeout_spin.setValue(DEFAULT_PARAMS["timeout_ms"])
        self.timeout_spin.setFixedWidth(90)
        send_layout.addWidget(self.timeout_spin)

        self.chk_match = QCheckBox("启用响应匹配")
        self.chk_match.setChecked(DEFAULT_PARAMS["match_enabled"])
        send_layout.addWidget(self.chk_match)
        send_layout.addStretch()

        self.btn_start = QPushButton("开始发送")
        set_btn(self.btn_start, "success")
        set_btn_icon(self.btn_start, "play")
        self.btn_start.clicked.connect(self._toggle_send)
        send_layout.addWidget(self.btn_start)
        left_layout.addWidget(send_group)

        # 接收模式
        rx_group = QGroupBox("接收模式")
        rx_layout = QHBoxLayout(rx_group)
        rx_layout.setSpacing(6)
        self.rx_raw_radio = QRadioButton("原始数据")
        self.rx_frame_radio = QRadioButton("按帧尾分割")
        self.rx_raw_radio.setChecked(True)
        self.rx_raw_radio.toggled.connect(self._on_rx_mode_changed)
        rx_layout.addWidget(self.rx_raw_radio)
        rx_layout.addWidget(self.rx_frame_radio)
        rx_layout.addSpacing(8)
        rx_layout.addWidget(QLabel("帧尾 (HEX)："))
        self.frame_tail_edit = QLineEdit(DEFAULT_FRAME_TAIL)
        self.frame_tail_edit.setFixedWidth(90)
        self.frame_tail_edit.editingFinished.connect(self._on_frame_tail_changed)
        rx_layout.addWidget(self.frame_tail_edit)
        rx_layout.addSpacing(8)
        self.chk_show_parse = QCheckBox("显示解析")
        self.chk_show_parse.setChecked(bool(DEFAULT_PARAMS["parse_enabled"]))
        self.chk_show_parse.setToolTip(
            "按命令协议解析**发送与接收**帧，并在日志输出字段明细；\n"
            "关闭则只显示原始 HEX（零解析开销）"
        )
        self.chk_show_parse.toggled.connect(lambda _=False: self._schedule_save())
        rx_layout.addWidget(self.chk_show_parse)
        rx_layout.addWidget(QLabel("解析行数上限："))
        self.parse_lines_spin = QSpinBox()
        self.parse_lines_spin.setRange(*PARSE_MAX_LINES_RANGE)
        self.parse_lines_spin.setValue(int(DEFAULT_PARAMS["parse_max_lines"]))
        self.parse_lines_spin.setSpecialValueText("不限制")
        self.parse_lines_spin.setFixedWidth(80)
        self.parse_lines_spin.setToolTip(
            "0（不限制）= 输出完整解析；\n"
            "国网「查询从节点ID信息」一条应答帧就有 100+ 行，默认不截断"
        )
        self.parse_lines_spin.valueChanged.connect(lambda _=0: self._schedule_save())
        rx_layout.addWidget(self.parse_lines_spin)
        rx_layout.addStretch()
        left_layout.addWidget(rx_group)

        # 断帧设置（1.23.78）：断帧方式 + 4 个可调超时（UI 与参数夹紧共用 FRAME_TIMEOUT_RANGES）
        framing_group = QGroupBox("断帧设置")
        framing_grid = QGridLayout(framing_group)
        framing_grid.setContentsMargins(6, 4, 6, 4)
        framing_grid.setHorizontalSpacing(6)
        framing_grid.setVerticalSpacing(4)
        self.framing_mode_combo = QComboBox()
        for value, label in FRAMING_MODE_OPTIONS:
            self.framing_mode_combo.addItem(label, value)
        self.framing_mode_combo.setToolTip(
            "自动（推荐）：指定了命令协议时按该协议的**结构特征**断帧并拼接\n"
            "（68 家族自动跳过帧首前导 FEH）；未指定协议时按「字节静默超时」断帧，\n"
            "并叠加 68 结构自证（长度域到齐且末字节 16H 即立即成帧）\n"
            "仅按字节超时：忽略协议结构与自证，完全按超时聚合"
        )
        self.framing_mode_combo.currentIndexChanged.connect(self._on_framing_changed)
        framing_grid.addWidget(QLabel("断帧方式："), 0, 0)
        framing_grid.addWidget(self.framing_mode_combo, 0, 1)

        self.byte_idle_spin = self._framing_spin(
            "rx_byte_idle_ms",
            "字节静默超时：无结构可判时的静默窗口，读静默超过它就把已收数据刷成一行。\n"
            "调大 = 更不容易把一帧切成多行（代价：帧显示更晚）；\n"
            "调小 = 更实时（慢设备的一帧可能被切开）")
        framing_grid.addWidget(QLabel("字节静默超时："), 0, 2)
        framing_grid.addWidget(self.byte_idle_spin, 0, 3)

        self.frame_idle_spin = self._framing_spin(
            "rx_frame_idle_ms",
            "协议帧等待静默：已按协议认出「一帧已开始但没收到全」时的等待窗口。\n"
            "调大 = 慢设备/分片交付也能拼回整帧；调小 = 出错帧更快刷出")
        framing_grid.addWidget(QLabel("协议帧等待静默："), 1, 0)
        framing_grid.addWidget(self.frame_idle_spin, 1, 1)

        self.frame_hold_spin = self._framing_spin(
            "rx_frame_hold_max_ms",
            "协议帧等待上限：一帧的**绝对**等待上限（含持续未到齐），\n"
            "防设备中途断流把缓冲永久挂住（到点即按原样刷出，不丢字节）")
        framing_grid.addWidget(QLabel("协议帧等待上限："), 1, 2)
        framing_grid.addWidget(self.frame_hold_spin, 1, 3)

        self.raw_hold_spin = self._framing_spin(
            "rx_raw_max_hold_ms",
            "聚合最长持有：持续流式接收时的兜底 —— 读间隔始终小于静默窗口时，\n"
            "超过它就强制刷成一行，防止缓冲无界增长")
        framing_grid.addWidget(QLabel("聚合最长持有："), 2, 0)
        framing_grid.addWidget(self.raw_hold_spin, 2, 1)
        framing_grid.addWidget(QLabel("未指定协议 → 按字节静默超时断帧"), 2, 2, 1, 2)
        left_layout.addWidget(framing_group)
        splitter.addWidget(left)

        # 右：统计 + 日志
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        stats_group = QGroupBox("统计")
        stats_layout = QVBoxLayout(stats_group)
        row1 = QHBoxLayout()
        self.lbl_tx = QLabel("发送：0 帧 / 0 B")
        self.lbl_tx.setFont(self._mono_font())
        row1.addWidget(self.lbl_tx)
        self.lbl_rx = QLabel("接收：0 帧 / 0 B")
        self.lbl_rx.setFont(self._mono_font())
        row1.addWidget(self.lbl_rx)
        row1.addStretch()
        stats_layout.addLayout(row1)
        row2 = QHBoxLayout()
        self.lbl_match = QLabel("匹配：成功 0 / 失败 0 / 成功率 —")
        f = self._mono_font()
        f.setBold(True)
        self.lbl_match.setFont(f)
        row2.addWidget(self.lbl_match)
        row2.addStretch()
        self.lbl_time = QLabel("运行：0.0s")
        self.lbl_time.setFont(self._mono_font())
        row2.addWidget(self.lbl_time)
        self.btn_reset_stats = QPushButton("清除统计")
        set_btn(self.btn_reset_stats, "secondary")
        set_btn_icon(self.btn_reset_stats, "clear")
        self.btn_reset_stats.clicked.connect(self._reset_stats)
        row2.addWidget(self.btn_reset_stats)
        stats_layout.addLayout(row2)
        right_layout.addWidget(stats_group)

        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 8, 6, 6)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumBlockCount(10000)
        self.log_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log_text, 1)

        log_btns = QHBoxLayout()
        log_btns.setSpacing(6)
        btn_clear = QPushButton("清空日志")
        set_btn(btn_clear, "secondary")
        set_btn_icon(btn_clear, "clear")
        btn_clear.clicked.connect(self.log_text.clear)
        log_btns.addWidget(btn_clear)
        self.chk_auto_scroll = QCheckBox("自动滚动")
        self.chk_auto_scroll.setChecked(True)
        log_btns.addWidget(self.chk_auto_scroll)
        self.chk_show_tx = QCheckBox("显示发送")
        self.chk_show_tx.setChecked(True)
        log_btns.addWidget(self.chk_show_tx)
        self.chk_show_rx = QCheckBox("显示接收")
        self.chk_show_rx.setChecked(True)
        log_btns.addWidget(self.chk_show_rx)
        log_btns.addStretch()
        log_layout.addLayout(log_btns)

        # 日志文件（自动保存）：把日志**实时写入文件**（内容 = 上面日志窗口的内容，
        # 但窗口只保留最近 10000 行、文件不截断）。目录可换、可一键打开。
        # 单独一行：这一行控件较多，与上面那行挤在一起会把该分栏撑宽（见陷阱 56）。
        log_file_row = QHBoxLayout()
        log_file_row.setSpacing(6)
        self.chk_auto_save_log = QCheckBox("自动保存日志")
        self.chk_auto_save_log.setToolTip(
            "勾选后把日志**实时写入文件**：\n"
            "  · 内容与上面日志窗口一致（含发送 / 接收 / 解析 / 匹配 / 系统行，\n"
            "    同样受「显示发送 / 显示接收 / 显示解析」控制）\n"
            "  · 窗口只保留最近 10000 行，**文件不截断**（一直追加）\n"
            "  · 每行带毫秒时间戳前缀；写一行即落盘（断电/崩溃也尽量保住）\n"
            "  · 取消勾选即停止并写入收发统计尾；换目录在下次开始时生效"
        )
        self.chk_auto_save_log.toggled.connect(self._on_auto_save_toggled)
        log_file_row.addWidget(self.chk_auto_save_log)

        self.chk_log_timestamp = QCheckBox("行首时间戳")
        self.chk_log_timestamp.setChecked(bool(DEFAULT_PARAMS["log_timestamp"]))
        self.chk_log_timestamp.setToolTip(
            "文件里每行前加「写入时刻」前缀（毫秒精度）：\n"
            "2026-09-22 15:30:00.123 | [RX] 68 0E 00 …\n"
            "关闭则只写原文（与窗口显示逐字符一致）"
        )
        self.chk_log_timestamp.toggled.connect(self._on_log_timestamp_toggled)
        log_file_row.addWidget(self.chk_log_timestamp)

        self.btn_save_log = QPushButton("保存当前日志…")
        set_btn(self.btn_save_log, "secondary")
        set_btn_icon(self.btn_save_log, "save")
        self.btn_save_log.setToolTip(
            "把日志窗口当前内容另存为一个文件（不影响「自动保存日志」）\n"
            "注意：窗口只保留最近 10000 行，需要完整日志请用「自动保存日志」"
        )
        self.btn_save_log.clicked.connect(self._save_log_now)
        log_file_row.addWidget(self.btn_save_log)

        self.btn_log_dir = QPushButton("选择目录…")
        set_btn(self.btn_log_dir, "secondary")
        set_btn_icon(self.btn_log_dir, "open")
        self.btn_log_dir.clicked.connect(self._choose_log_dir)
        log_file_row.addWidget(self.btn_log_dir)

        self.btn_open_log_dir = QPushButton("打开目录")
        set_btn(self.btn_open_log_dir, "secondary")
        set_btn_icon(self.btn_open_log_dir, "open_file")
        self.btn_open_log_dir.setToolTip("在资源管理器中打开日志目录")
        self.btn_open_log_dir.clicked.connect(self._open_log_directory)
        log_file_row.addWidget(self.btn_open_log_dir)
        log_file_row.addStretch()
        log_layout.addLayout(log_file_row)

        # 状态行：显示当前/最近一次日志文件（路径在 tooltip，文本可选中复制）
        self.lbl_log_state = QLabel("未开启自动保存")
        self.lbl_log_state.setStyleSheet("color: #888; font-size: 11px;")
        self.lbl_log_state.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        log_layout.addWidget(self.lbl_log_state)
        self._update_log_state_label()
        right_layout.addWidget(log_group, 1)

        splitter.addWidget(right)
        splitter.setSizes([560, 640])
        layout.addWidget(splitter, 1)

    @staticmethod
    def _mono_font() -> QFont:
        f = QFont("Consolas")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(9)
        return f

    # ── 日志 ─────────────────────────────────────────────────────────

    def _log(self, text: str, color: str = None):
        """写一行日志（立即）。**日志文件的唯一写入入口**（见 `_save_log_line`）。"""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(_LOG_COLORS.get(color, color)))
        cursor.insertText(text + "\n", fmt)
        self._save_log_line(text)
        if self.chk_auto_scroll.isChecked():
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )

    def _flush_log_queues(self):
        """批量刷出 TX/RX 日志（两个队列元素都是 ``(kind, text)``）。

        ``kind`` ∈ ``raw`` / ``parse`` / ``fail``（决定配色与前缀）。条数 ≤
        ``LOG_FLUSH_BURST`` 时逐条输出（手工/低速场景，与源工具一致）；超过则只输出
        「摘要 + 首帧 + 末帧」—— **burst 只对 ``raw`` 计数**，同批的解析明细整批丢弃
        （防刷屏拖慢界面）。
        """
        for queue, enabled, prefix, raw_color in (
            (self._tx_log_queue, self.chk_show_tx, "[TX]", "tx"),
            (self._rx_log_queue, self.chk_show_rx, "[RX]", "rx"),
        ):
            if not queue:
                continue
            if not enabled.isChecked():
                queue.clear()
                continue
            raws = [text for kind, text in queue if kind == "raw"]
            if len(raws) > LOG_FLUSH_BURST:
                queue.clear()
                self._log(f"{prefix} 本批 {len(raws)} 帧（已省略逐帧明细）", "sys")
                self._log(f"{prefix} 首帧 {raws[0]}", raw_color)
                self._log(f"{prefix} 末帧 {raws[-1]}", raw_color)
                continue
            colors = {"raw": raw_color, "parse": "sys", "fail": "fail",
                      "match": "sys", "ok": "ok"}
            while queue:
                kind, text = queue.popleft()
                self._log(text if kind != "raw" else f"{prefix} {text}",
                          colors.get(kind, raw_color))

    # ── 日志文件（自动保存）────────────────────────────────────────────

    def log_dir(self) -> str:
        """当前日志目录：用户选择的优先，默认 = 数据目录下的 ``Output/``。

        默认目录由本页**配置文件所在目录**派生（而不是直接问 `app_paths`）：
        数据目录已被测试沙箱重定向，日志目录随之进沙箱，绝不会写到开发机的真实
        目录 —— 这是把「默认值」做成参数（`log_dir`）而不是写死的唯一理由。
        """
        chosen = str(self._params.get("log_dir") or "").strip()
        if chosen:
            return chosen
        return default_log_dir(os.path.dirname(self._config_path))

    def _log_header_lines(self) -> List[str]:
        """日志文件头（环境上下文，行首 ``#``，不加时间戳前缀）。"""
        return [
            f"# {LOG_HEADER_TITLE}",
            f"# 开始时间: {format_log_time()}",
            f"# 串口: {serial_context_text(self._serial_worker)}",
            "# 说明: 本文件是「串口工具」日志窗口内容的完整镜像；"
            "窗口只保留最近 10000 行，文件不截断（一直追加）",
        ]

    def _stats_comment(self) -> str:
        """日志文件尾的统计行。"""
        return (f"# 收发统计: 发送 {self._tx_frames} 帧 / {self._tx_bytes} B；"
                f"接收 {self._rx_frames} 帧 / {self._rx_bytes} B；"
                f"匹配 成功 {self._rx_matched} / 失败 {self._rx_missed}")

    def _on_auto_save_toggled(self, checked: bool):
        """勾选 → 开始写文件；取消 → 写统计尾并关闭。"""
        if checked:
            if not self._start_log_recording():
                # 开不了文件就回到未勾选（blockSignals 防重入 → 只提示一次）
                self.chk_auto_save_log.blockSignals(True)
                self.chk_auto_save_log.setChecked(False)
                self.chk_auto_save_log.blockSignals(False)
                self._update_log_state_label()
        else:
            self._stop_log_recording()
        self._schedule_save()

    def _start_log_recording(self) -> bool:
        """开始写日志文件；失败提示用户并返回 False（**不静默**）。"""
        if self._log_writer is not None:
            return True
        writer = LogFileWriter(timestamp=bool(self.chk_log_timestamp.isChecked()))
        if not writer.open(self.log_dir(), header=self._log_header_lines()):
            reason = writer.error or "未知错误"
            self._log(f"[日志] 无法创建日志文件：{reason}", "fail")
            self._update_log_state_label()
            QMessageBox.critical(
                self, "日志保存失败",
                f"无法创建日志文件：\n{reason}\n\n目录：{self.log_dir()}"
            )
            return False
        self._log_writer = writer
        self._log(f"[日志] 开始保存到 {writer.path}", "sys")
        self._update_log_state_label()
        return True

    def _stop_log_recording(self):
        """停止写日志文件：写统计尾 + 关闭（幂等）。"""
        writer = self._log_writer
        if writer is None:
            self._update_log_state_label()
            return
        # 先摘掉引用：下面 _log 写的「已保存」行不该再进这个（已收尾的）文件
        self._log_writer = None
        self._log_last_path = writer.path
        writer.write_raw(f"# 停止时间: {format_log_time()}")
        writer.write_raw(self._stats_comment())
        ok = writer.close()
        self._log_last_lines = writer.line_count
        if ok:
            self._log(f"[日志] 已保存 {writer.line_count} 行到 {writer.path}", "sys")
        else:
            self._log(f"[日志] 收尾写日志文件失败：{writer.error or '未知错误'}", "fail")
        self._update_log_state_label()

    def _on_log_timestamp_toggled(self, checked: bool):
        """「行首时间戳」开关：对当前已打开的文件**立即生效**（下一行起）。"""
        if self._log_writer is not None:
            self._log_writer.timestamp = bool(checked)
        self._schedule_save()

    def _save_log_line(self, text: str):
        """把一行日志写进文件（由 `_log()` 调用，是文件的**唯一**写入点）。

        写失败（目录被删 / 磁盘满 / 权限）：**必须告诉用户**并把自动保存关掉，
        否则日志会静默丢失（陷阱 23 的同一精神）。这里先把引用摘掉 —— 下面那条
        `_log` 提示不能再往这个坏文件里写（否则无限递归）。
        """
        writer = self._log_writer
        if writer is None or not writer.is_open:
            return
        if writer.write_line(text):
            return
        self._log_writer = None
        self._log_last_path = writer.path
        self._log_last_lines = writer.line_count
        reason = writer.error or "未知错误"
        writer.close()
        self.chk_auto_save_log.blockSignals(True)
        self.chk_auto_save_log.setChecked(False)
        self.chk_auto_save_log.blockSignals(False)
        self._update_log_state_label()
        self._log(f"[日志] 写入文件失败，已停止自动保存：{reason}", "fail")

    def _update_log_state_label(self):
        """刷新状态行（保存中 / 已停止 / 未开启）；路径信息放 tooltip。

        文本刻意保持**短**：这是 QLabel，长路径会把所在分栏撑宽（与陷阱 56 同因）。
        完整路径放 tooltip，且开始保存时日志里已打过一条 ``[日志] 开始保存到 <path>``。
        """
        label = getattr(self, "lbl_log_state", None)
        if label is None:
            return
        try:
            directory = self.log_dir()
        except Exception:
            directory = ""
        writer = self._log_writer
        if writer is not None:
            label.setText(f"保存中：{os.path.basename(writer.path)}"
                          f"（{writer.line_count} 行）")
            label.setToolTip(f"{writer.path}\n（每写一行即落盘）")
            label.setStyleSheet("color: #C00000; font-weight: bold; font-size: 11px;")
        elif self._log_last_path:
            label.setText(f"已停止：{os.path.basename(self._log_last_path)}"
                          f"（{self._log_last_lines} 行）")
            label.setToolTip(self._log_last_path)
            label.setStyleSheet("color: #888; font-size: 11px;")
        else:
            label.setText("未开启自动保存")
            label.setToolTip(f"勾选「自动保存日志」后，日志会实时写入：\n{directory}")
            label.setStyleSheet("color: #888; font-size: 11px;")
        for btn, tip in (
            (getattr(self, "btn_log_dir", None),
             f"当前日志目录：\n{directory}\n（点击更改，下次开始保存时生效）"),
            (getattr(self, "btn_open_log_dir", None),
             f"在资源管理器中打开：\n{directory}"),
        ):
            if btn is not None:
                btn.setToolTip(tip)

    def _choose_log_dir(self):
        """选择日志目录（下一次开始保存时生效）。"""
        path = QFileDialog.getExistingDirectory(self, "选择日志保存目录", self.log_dir())
        if not path:
            return
        self._params["log_dir"] = path
        if self._log_writer is not None:
            self._log(f"[日志] 保存目录已改为 {path}；当前文件仍写到 "
                      f"{os.path.basename(self._log_writer.path)}"
                      "（重新勾选「自动保存日志」即改用新目录）", "sys")
        else:
            self._log(f"[日志] 保存目录已设为 {path}", "sys")
        self._update_log_state_label()
        self._schedule_save()

    def _open_log_directory(self):
        """打开日志目录（Windows 资源管理器 / 其它平台各自的打开方式）。"""
        path = self.log_dir()
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "打开目录失败", f"无法创建目录：\n{exc}")
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)                  # Windows
            else:
                import subprocess

                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            QMessageBox.warning(self, "打开目录失败", f"{exc}\n\n目录：{path}")

    def _save_log_now(self):
        """手动把日志窗口当前内容另存为一个文件（与自动保存互不影响）。"""
        text = self.log_text.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "保存日志", "日志窗口当前没有内容")
            return
        default_path = os.path.join(self.log_dir(), log_file_name())
        path, _ = QFileDialog.getSaveFileName(
            self, "保存当前日志", default_path,
            "日志文件 (*.log);;文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        if write_log_text(path, text):
            self._log(f"[日志] 已保存日志窗口 {len(text.splitlines())} 行到 {path}", "sys")
        else:
            QMessageBox.critical(self, "保存失败", f"写入文件失败：\n{path}")

    # ── 串口（状态由顶部「串口配置」驱动，本页不持有端口）──────────────

    def _on_serial_error(self, msg: str):
        self._log(f"[串口错误] {msg}", "fail")

    # ── 接收 ─────────────────────────────────────────────────────────

    def _on_raw_data(self, data: bytes):
        """收到原始字节：**先**喂匹配（不受显示聚合影响），再进显示路径。"""
        if not data:
            return
        self._rx_bytes += len(data)
        if self.chk_match.isChecked():
            self._on_rx_match_data(data)
        if self.rx_frame_radio.isChecked():
            self._frame_buffer.extend(data)
            self._flush_frames()
            return
        # 原始模式：先进聚合缓冲，再按「命令协议分帧 → 启发式 → 时间聚合」刷出。
        # 不能按每次 read 直接输出：串口驱动会把一帧拆成多次交付。
        if not self._raw_buffer:
            self._raw_first_time = time.perf_counter()
        self._raw_buffer.extend(data)
        self._raw_last_time = time.perf_counter()
        if self._framing_mode() != FRAMING_MODE_TIMEOUT:
            strategy = STRATEGY_BY_PROTOCOL.get(self._last_tx_protocol)
            if strategy:
                self._emit_protocol_frames(strategy)

    @staticmethod
    def _declared_frame_len(buf) -> int:
        """未指定协议时的启发式分帧（实现见模块级 :func:`declared_frame_len`）。"""
        return declared_frame_len(buf)

    def _emit_rx_frame(self, frame: bytes, protocol) -> None:
        """产出一帧：原始行 +（协议非空且开启「显示解析」时）解析文字行。"""
        self._rx_frames += 1
        self._rx_log_queue.append(("raw", bytes_to_hex(frame)))
        if protocol is not None and self.chk_show_parse.isChecked():
            self._queue_parse(frame, protocol)

    def _queue_parse(self, frame: bytes, protocol: int, channel: str = "rx") -> None:
        """解析一帧并把文字结果入队（摘要行 + 缩进字段行）。

        ``channel`` = ``rx``（响应，入 RX 队列）或 ``tx``（发送，入 TX 队列）——
        两个方向都按各自命令的协议解析，日志里对称展示。

        失败不伪造：回调抛异常 / 返回空表时只输出失败行（fail 配色）。
        关闭「显示解析」或未注入回调时**零开销**（调用方已判定，这里再兜一层）。
        """
        if self._parse_provider is None:
            return
        queue = self._rx_log_queue if channel == "rx" else self._tx_log_queue
        name = protocol_short_name(protocol)
        try:
            summary, table_data = self._parse_provider(frame, protocol)
        except Exception as exc:
            queue.append(
                ("fail", f"[解析·{name}] 失败：{type(exc).__name__}: {exc}")
            )
            return
        rows = format_parse_rows(table_data, int(self.parse_lines_spin.value()))
        if not rows:
            queue.append(("fail", f"[解析·{name}] 失败：解析结果为空"))
            return
        summary = str(summary or "").strip()
        head = f"[解析·{name}] {summary}" if summary and summary != "-" \
            else f"[解析·{name}]"
        queue.append(("parse", head))
        for line in rows:
            queue.append(("parse", line))

    def _emit_protocol_frames(self, strategy: str) -> bool:
        """按**命令协议**的分帧策略把已收全的帧逐帧产出；返回是否产出过。

        68 家族额外要求末字节为 16H（长度域只给出长度，末字节才是自证）；
        HDLC 由 7EH 定界、DLMS Wrapper 由版本 + 长度域自证，无需额外校验。
        """
        emitted = False
        while True:
            need = frame_length_for(strategy, self._raw_buffer)
            if not need or len(self._raw_buffer) < need:
                break
            if strategy in END_CHAR_STRATEGIES and self._raw_buffer[need - 1] != 0x16:
                break
            frame = bytes(self._raw_buffer[:need])
            del self._raw_buffer[:need]
            self._emit_rx_frame(frame, self._last_tx_protocol)
            emitted = True
        if emitted:
            # 缓冲已被消费：时间基准重置，剩余残帧按新起点重新计时
            self._raw_last_time = time.perf_counter()
            self._raw_first_time = self._raw_last_time if self._raw_buffer else 0.0
        return emitted

    def _emit_structured_frames(self) -> bool:
        """**未指定协议时**的启发式：把缓冲中已收全且自证的 68 帧逐帧刷出。

        自证条件：长度域给出整帧长度，且该长度处的末字节确为 16H —— 否则说明这段
        数据不是本结构（例如 645 的地址域恰好凑出合理长度），交回时间聚合处理。
        """
        emitted = False
        while True:
            need = self._declared_frame_len(self._raw_buffer)
            if not need or len(self._raw_buffer) < need:
                break
            if self._raw_buffer[need - 1] != 0x16:
                break
            frame = bytes(self._raw_buffer[:need])
            del self._raw_buffer[:need]
            self._emit_rx_frame(frame, None)      # 未指定协议 → 只出原始行
            emitted = True
        if emitted:
            # 缓冲已被消费：时间基准重置，剩余残帧按新起点重新计时
            self._raw_last_time = time.perf_counter()
            self._raw_first_time = self._raw_last_time if self._raw_buffer else 0.0
        return emitted

    def _frame_incomplete(self, strategy: Optional[str]) -> bool:
        """缓冲里是否有一段**已开始但未收全**的协议帧（实现见 :func:`frame_incomplete`）。

        判据与常量都在 `frame_deframe`（纯逻辑单一来源，升级页复用同一实现）；此处只把
        widget 的 ``_raw_buffer`` 交给它 —— 行为与搬出前一字不变。
        """
        return frame_incomplete(strategy, self._raw_buffer)

    # ── 断帧设置（1.23.78）：方式 + 4 个超时 ─────────────────────────

    def _framing_mode(self) -> str:
        """断帧方式（取控件值；非法值回落 ``auto``）。"""
        data = self.framing_mode_combo.currentData()
        return data if data in (FRAMING_MODE_AUTO, FRAMING_MODE_TIMEOUT) else FRAMING_MODE_AUTO

    def _timeouts(self) -> Tuple[int, int, int, int]:
        """当前断帧超时（毫秒）：字节静默 / 聚合最长持有 / 协议帧等待静默 / 协议帧等待上限。"""
        return (
            int(self.byte_idle_spin.value()),
            int(self.raw_hold_spin.value()),
            int(self.frame_idle_spin.value()),
            int(self.frame_hold_spin.value()),
        )

    def _framing_summary_text(self) -> str:
        """一行「此刻按什么断帧」说明（现场自查；只在设置变更/每轮开始时输出）。"""
        mode = self._framing_mode()
        byte_idle, raw_hold, frame_idle, frame_hold = self._timeouts()
        proto = self._last_tx_protocol
        if mode == FRAMING_MODE_TIMEOUT:
            basis = "仅按字节超时（忽略协议结构与自证）"
        else:
            strategy = STRATEGY_BY_PROTOCOL.get(proto)
            if strategy:
                basis = f"协议特征 {strategy}（{STRATEGY_NAMES.get(strategy, strategy)}）"
                if strategy in FE_WAKEUP_STRATEGIES:
                    basis += "，前导 FE 自动跳过"
            elif proto is None:
                basis = "未指定协议 → 按字节超时（叠加 68 结构自证）"
            else:
                basis = f"当前协议（{protocol_short_name(proto)}）无自证分帧依据 → 按字节超时"
        return (
            f"[断帧] 方式={dict(FRAMING_MODE_OPTIONS).get(mode, mode)}；依据={basis}；"
            f"超时 字节静默 {byte_idle}ms / 聚合最长持有 {raw_hold}ms / "
            f"协议帧等待静默 {frame_idle}ms / 协议帧等待上限 {frame_hold}ms"
        )

    def _log_framing_summary(self) -> None:
        """输出断帧依据说明行（**不逐帧打印**：只在设置变更 / 每轮开始时调用）。"""
        self._log(self._framing_summary_text(), "sys")

    def _framing_spin(self, key: str, tooltip: str) -> QSpinBox:
        """按 ``FRAME_TIMEOUT_RANGES`` 造一个断帧超时 spin（UI 与参数夹紧同源）。"""
        lo, hi = FRAME_TIMEOUT_RANGES[key]
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(int(DEFAULT_PARAMS[key]))
        spin.setSuffix(" ms")
        # 只设下限、不设上限：QSS 主题与系统字号下「5000 ms」的 sizeHint 会变，
        # 写死宽度会让文字被裁（AGENTS §8 陷阱 63 的同类判据）。
        spin.setMinimumWidth(96)
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(lambda _=0: self._schedule_save())
        spin.editingFinished.connect(self._log_framing_summary)
        return spin

    def _on_framing_changed(self, _index: int = 0):
        """切换断帧方式：先按旧口径把缓冲刷出，避免两种口径的数据混在一行。"""
        self._flush_raw_display_now()
        self._schedule_save()
        self._log_framing_summary()

    def _emit_raw_chunk(self):
        """把当前聚合缓冲整体作为一行刷出（**不解析**：这不是一个完整帧）。"""
        chunk = bytes(self._raw_buffer)
        self._raw_buffer.clear()
        self._rx_frames += 1
        self._rx_log_queue.append(("raw", bytes_to_hex(chunk)))

    def _flush_raw_display(self):
        """原始模式刷出：**帧结构优先**，时间聚合兜底。

        指定了命令协议且该协议有自证分帧依据时，**只**按该协议切帧（不再用启发式，
        避免"你告诉了我协议却按另一种结构切"）；否则退回启发式。剩余部分再按
        「静默窗口 / 最长持有」决定是否作为一行刷出。

        「仅按字节超时」（``FRAMING_MODE_TIMEOUT``）时**跳过**前面两条结构路径，
        完全按字节超时聚合（用户显式选择的兜底口径）。
        四个时间窗都取自「断帧设置」（可调，默认 = 原常量）。
        """
        if not self._raw_buffer:
            return
        strategy = STRATEGY_BY_PROTOCOL.get(self._last_tx_protocol)
        auto = self._framing_mode() != FRAMING_MODE_TIMEOUT
        if auto:
            if strategy:
                if self._emit_protocol_frames(strategy):
                    return
            elif self._emit_structured_frames():
                return
        now = time.perf_counter()
        idle_ms = (now - self._raw_last_time) * 1000
        held_ms = (now - self._raw_first_time) * 1000
        byte_idle, raw_hold, frame_idle, frame_hold = self._timeouts()
        if auto and self._frame_incomplete(strategy):
            if idle_ms < frame_idle and held_ms < frame_hold:
                return
        elif idle_ms < byte_idle and held_ms < raw_hold:
            # 持续流式接收时读间隔始终小于静默窗口 → 最长持有兜底，防无界增长
            return
        self._emit_raw_chunk()

    def _flush_frames(self):
        """按帧尾切分缓冲区，逐帧产出（尾部残帧保留）。"""
        if not self._frame_tail:
            return
        while True:
            idx = self._frame_buffer.find(self._frame_tail)
            if idx == -1:
                break
            end = idx + len(self._frame_tail)
            frame = bytes(self._frame_buffer[:end])
            del self._frame_buffer[:end]
            self._emit_rx_frame(frame, self._last_tx_protocol)

    def _on_rx_mode_changed(self, _checked: bool = False):
        frame_mode = self.rx_frame_radio.isChecked()
        self.frame_tail_edit.setEnabled(frame_mode)
        # 切换模式前把两种缓冲都刷掉，避免旧数据混进新模式的显示
        self._flush_raw_display_now()
        self._frame_buffer.clear()
        self._schedule_save()

    def _flush_raw_display_now(self):
        """立即刷出原始聚合缓冲（忽略静默窗口；切模式/收尾时用）。"""
        if not self._raw_buffer:
            return
        if self._framing_mode() != FRAMING_MODE_TIMEOUT:
            strategy = STRATEGY_BY_PROTOCOL.get(self._last_tx_protocol)
            if strategy:
                self._emit_protocol_frames(strategy)   # 已收全的帧仍逐帧刷出
            else:
                self._emit_structured_frames()
        if self._raw_buffer:                # 残帧整体作为一行，不丢数据
            self._emit_raw_chunk()
        self._raw_first_time = 0.0

    def _on_frame_tail_changed(self):
        raw = self.frame_tail_edit.text()
        tail = hex_str_to_bytes(raw)
        if not tail:
            QMessageBox.warning(self, "帧尾无效", f"帧尾不是有效的 HEX：{raw}")
            self.frame_tail_edit.setText(bytes_to_hex(self._frame_tail))
            return
        self._frame_tail = tail
        self._log(f"[接收] 帧尾已设为 {bytes_to_hex(tail)}", "sys")
        self._schedule_save()

    # ── 命令管理 ─────────────────────────────────────────────────────

    def _cmd_status(self, index: int) -> str:
        """某条命令的运行时状态（``""`` = 待测）。"""
        if 0 <= index < len(self.commands):
            return str(self.commands[index].get(CMD_STATUS_KEY, "") or "")
        return ""

    def _set_cmd_status(self, index, status: str):
        """设置命令状态（运行时键 `_status`，**不落盘/不导出**）并只重画那一行。"""
        if not isinstance(index, int) or not (0 <= index < len(self.commands)):
            return
        if status not in CMD_STATUS_STYLES:
            status = ""
        self.commands[index][CMD_STATUS_KEY] = status
        self._refresh_cmd_row(index)

    def _clear_cmd_statuses(self):
        """清空所有命令状态（每轮发送开始时调用）。"""
        for i, cmd in enumerate(self.commands):
            cmd.pop(CMD_STATUS_KEY, None)
            self._refresh_cmd_row(i)

    def _clear_cmd_status_clicked(self):
        """「清除状态」按钮：手动把状态图标重置为「待测」。

        发送中禁止（与「清除统计」同一口径）—— 那时状态还在被实时改写，
        清了也会立刻被下一批信号填回来，徒增困惑。
        """
        if self._running:
            QMessageBox.information(self, "串口工具", "发送中不能清除状态")
            return
        self._clear_cmd_statuses()

    def _mark_running_as(self, status: str):
        """把仍在「发送中」的命令改成指定状态（发送失败 / 停止时用）。"""
        for i in range(len(self.commands)):
            if self._cmd_status(i) == "running":
                self._set_cmd_status(i, status)

    def _refresh_cmd_row(self, index: int):
        """只重画某一行的「名称」单元格（状态图标 + 配色），不整表重建。

        状态放在**名称列**（用户要求）：图标表状态、文字颜色同色系，一眼能对上
        日志里的同一件事。
        """
        if not (0 <= index < self.cmd_table.rowCount()):
            return
        item = self.cmd_table.item(index, 1)
        if item is None:
            return
        status = self._cmd_status(index)
        item.setText(str(self.commands[index].get("name", "")))
        item.setIcon(status_icon(status))
        _icon_name, color = CMD_STATUS_STYLES.get(status, CMD_STATUS_STYLES[""])
        item.setForeground(QColor(color))
        item.setToolTip(f"状态：{status_text(status)}")

    def _rebuild_cmd_table(self):
        self._rebuilding_cmd_table = True
        try:
            self.cmd_table.setRowCount(0)
            for cmd in self.commands:
                row = self.cmd_table.rowCount()
                self.cmd_table.insertRow(row)
                # 第 0 列：勾选框（决定是否参与发送）
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemFlag.ItemIsEnabled
                             | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Checked if coerce_enabled(
                    cmd.get("enabled")) else Qt.CheckState.Unchecked)
                self.cmd_table.setItem(row, 0, chk)
                self.cmd_table.setItem(row, 1, QTableWidgetItem(cmd.get("name", "")))
                # 名称列的状态图标 + 配色（见 _refresh_cmd_row）
                self._refresh_cmd_row(row)
                self.cmd_table.setItem(
                    row, 2, QTableWidgetItem(cmd.get("data_hex", ""))
                )
                self.cmd_table.setItem(
                    row, 3,
                    QTableWidgetItem(MATCH_TYPES.get(cmd.get("match_type", ""),
                                                     cmd.get("match_type", ""))),
                )
                self.cmd_table.setItem(
                    row, 4, QTableWidgetItem(cmd.get("match_hex", ""))
                )
                proto_item = QTableWidgetItem(
                    protocol_short_name(cmd.get("protocol"))
                )
                proto_item.setToolTip(
                    "该命令的协议：接收响应按它断帧并解析；「不解析」= 只显示原始 HEX"
                )
                self.cmd_table.setItem(row, 5, proto_item)
                n = coerce_send_count(cmd.get("send_count", 1))
                count_item = QTableWidgetItem(str(n))
                count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                count_item.setToolTip(
                    "发送次数：每轮对该命令连续发送的次数（默认 1）；双击本行可修改。"
                    "与底部「循环次数」相乘生效"
                )
                self.cmd_table.setItem(row, 6, count_item)
        finally:
            self._rebuilding_cmd_table = False
        self._update_cmd_sel_label()

    def _on_cmd_item_changed(self, item: QTableWidgetItem):
        """勾选列变化 → 回写 ``commands[row]["enabled"]`` 并落盘。"""
        if getattr(self, "_rebuilding_cmd_table", False) or item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.commands):
            self.commands[row]["enabled"] = (
                item.checkState() == Qt.CheckState.Checked
            )
        self._update_cmd_sel_label()
        self._schedule_save()

    def _set_all_checkboxes(self, checked: bool):
        """全选 / 全不选（直接写 commands，再重建表格，避免逐行触发信号）。"""
        for cmd in self.commands:
            cmd["enabled"] = bool(checked)
        self._rebuild_cmd_table()
        self._schedule_save()

    def _invert_checkboxes(self):
        """反选。"""
        for cmd in self.commands:
            cmd["enabled"] = not coerce_enabled(cmd.get("enabled"))
        self._rebuild_cmd_table()
        self._schedule_save()

    def _checked_rows(self) -> List[int]:
        """勾选的行号（表内顺序）。"""
        rows: List[int] = []
        for row in range(self.cmd_table.rowCount()):
            item = self.cmd_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        return rows

    def _update_cmd_sel_label(self):
        label = getattr(self, "lbl_cmd_sel", None)
        if label is None:
            return
        total = len(self.commands)
        checked = len(self._checked_rows()) if total else 0
        label.setText(f"已选 {checked} / {total} 条")

    def _selected_row(self) -> int:
        rows = self.cmd_table.selectionModel().selectedRows() \
            if self.cmd_table.selectionModel() else []
        return rows[0].row() if rows else -1

    def _add_command(self):
        dlg = SerialCommandDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cmd = dlg.get_command()
            cmd["enabled"] = True           # 新增命令默认勾选（参与发送）
            self.commands.append(cmd)
            self._rebuild_cmd_table()
            self._log(f"[命令] 已添加：{self.commands[-1]['name']}", "sys")
            self._schedule_save()

    def _on_cmd_double_clicked(self, row: int, column: int = 0):
        """双击命令行 → 直接打开该条的编辑窗口（等价于选中后点「编辑」）。

        独立于 `_edit_command` 的原因：按钮的 ``clicked`` 会带一个 bool 参数，
        若给 `_edit_command` 加位置参数会被那个 bool 当成行号（``False`` → 第 0 行）。
        这里先 `selectRow` 让视觉选中与编辑目标一致，再复用既有编辑流程。
        **第 0 列（勾选框）除外**：双击那里只切换勾选，不该弹编辑框。
        """
        if column == 0:
            return
        if not (0 <= row < len(self.commands)):
            return
        self.cmd_table.selectRow(row)
        self._edit_command()

    def _edit_command(self):
        row = self._selected_row()
        if row < 0:
            QMessageBox.information(self, "串口工具", "请先选择一条命令")
            return
        dlg = SerialCommandDialog(self, self.commands[row])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cmd = dlg.get_command()
            # 编辑不改动勾选状态（对话框只编辑内容字段）
            cmd["enabled"] = coerce_enabled(self.commands[row].get("enabled"))
            self.commands[row] = cmd
            self._rebuild_cmd_table()
            self._schedule_save()

    def _delete_command(self):
        row = self._selected_row()
        if row < 0:
            QMessageBox.information(self, "串口工具", "请先选择一条命令")
            return
        name = self.commands[row].get("name", "")
        del self.commands[row]
        self._rebuild_cmd_table()
        self._log(f"[命令] 已删除：{name}", "sys")
        self._schedule_save()

    def _move_command(self, delta: int):
        row = self._selected_row()
        if row < 0:
            return
        new_row = row + delta
        if new_row < 0 or new_row >= len(self.commands):
            return
        self.commands[row], self.commands[new_row] = (
            self.commands[new_row], self.commands[row]
        )
        self._rebuild_cmd_table()
        self.cmd_table.selectRow(new_row)
        self._schedule_save()

    def _move_command_up(self):
        self._move_command(-1)

    def _move_command_down(self):
        self._move_command(1)

    def _export_commands(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出命令配置", "commands.json", "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        if export_commands_file(path, self.commands):
            self._log(f"[命令] 已导出 {len(self.commands)} 条到 {os.path.basename(path)}",
                      "sys")
        else:
            QMessageBox.critical(self, "导出失败", "写入文件失败")

    def _import_commands(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入命令配置", "", "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        imported = import_commands_file(path)
        if not imported:
            QMessageBox.warning(self, "导入失败", "文件里没有可用命令（或格式不合法）")
            return
        self.commands.extend(imported)
        self._rebuild_cmd_table()
        self._log(f"[命令] 已导入 {len(imported)} 条", "sys")
        self._schedule_save()

    def _load_message_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "加载报文文件", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            messages = load_hex_messages(path)
        except OSError as e:
            QMessageBox.critical(self, "加载失败", str(e))
            return
        if not messages:
            QMessageBox.warning(self, "加载失败", "文件里没有可用报文")
            return
        base = len(self.commands)
        for i, msg in enumerate(messages):
            self.commands.append({
                "name": f"报文{base + i + 1}",
                "data_hex": bytes_to_hex(msg),
                "match_type": "none",
                "match_hex": "",
                "protocol": None,
                "enabled": True,
            })
        self._rebuild_cmd_table()
        self._log(f"[命令] 已从文件加载 {len(messages)} 条报文", "sys")
        self._schedule_save()

    # ── 批量替换通信地址 ─────────────────────────────────────────────────

    def _cmd_scope_indices(self, scope: str) -> List[int]:
        """作用范围 → 命令下标列表（``all`` = 全部，其余 = 勾选行）。"""
        if scope == "all":
            return list(range(len(self.commands)))
        return self._checked_rows()

    def _on_batch_addr_clicked(self):
        """「替换地址」按钮：对话框取值 → 纯逻辑批量替换 → 写回 + 汇总。"""
        if not self.commands:
            QMessageBox.information(self, "串口工具", "请先添加命令")
            return
        if self._running:
            QMessageBox.information(
                self, "串口工具", "发送中不能替换地址（命令内容正在被使用）"
            )
            return
        dlg = BatchAddrDialog(
            self, commands=self.commands, checked_indices=self._checked_rows()
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        items = batch_fix_commands(
            self.commands,
            self._cmd_scope_indices(dlg.scope()),
            dlg.protocol_index(),
            dlg.values(),
            write_protocol=dlg.write_protocol(),
            fix_match=dlg.fix_match(),
        )
        undo = self._apply_addr_batch(items)
        self._show_addr_batch_summary(items, undo)

    def _apply_addr_batch(self, items: List[AddrBatchItem]) -> List[tuple]:
        """把批量替换结果写回命令表（**不弹任何对话框**，便于测试与复用）。

        写回前记录撤销快照（每条命令的 ``data_hex`` / ``protocol`` / ``match_hex``），
        返回 ``[(原下标, 原值三元组), …]``（无实际改动则为空）。
        """
        undo: List[tuple] = []
        for item in items:
            if not (0 <= item.index < len(self.commands)):
                continue
            cmd = self.commands[item.index]
            before = (
                str(cmd.get("data_hex") or ""),
                cmd.get("protocol"),
                str(cmd.get("match_hex") or ""),
            )
            after = (
                item.data_hex,
                item.protocol if item.protocol is not None else cmd.get("protocol"),
                item.match_hex,
            )
            if before == after:
                continue
            undo.append((item.index, before))
            cmd["data_hex"] = item.data_hex
            if item.protocol is not None:
                cmd["protocol"] = item.protocol
            cmd["match_hex"] = item.match_hex

        self._addr_batch_undo = undo
        if undo:
            self._rebuild_cmd_table()
            self._schedule_save()
        self._log_addr_batch(items)
        return undo

    def _log_addr_batch(self, items: List[AddrBatchItem]):
        """逐条日志（明细上限 `ADDR_BATCH_LOG_LIMIT`，其余汇总一行）。"""
        head, detail = addr_batch_summary(items)
        self._log(f"[地址] 批量替换：{head}", "sys")
        shown = items[:ADDR_BATCH_LOG_LIMIT]
        for item in shown:
            if item.status == ADDR_STATUS_OK:
                self._log(f"[地址] {item.name}：{'；'.join(item.notes)}", "ok")
            else:
                self._log(f"[地址] {item.name}：未替换（{item.error}）", "fail")
        if len(items) > len(shown):
            self._log(f"[地址] …另有 {len(items) - len(shown)} 条（详见汇总）", "sys")
        for line in detail.splitlines():
            self._log(f"[地址] {line}", "sys")

    def _show_addr_batch_summary(self, items: List[AddrBatchItem], undo: List[tuple]):
        """汇总弹框（无实际改动时不提供「撤销本次替换」按钮）。"""
        head, detail = addr_batch_summary(items)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("批量替换通信地址")
        box.setText(head)
        if detail:
            box.setInformativeText(detail)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        undo_btn = None
        if undo:
            undo_btn = box.addButton(
                f"撤销本次替换（{len(undo)} 条）", QMessageBox.ButtonRole.ActionRole
            )
        box.exec()
        if undo_btn is not None and box.clickedButton() is undo_btn:
            self._undo_addr_batch()

    def _undo_addr_batch(self):
        """撤销**最近一次**批量替换（只恢复该批命令的 3 个键）。"""
        undo = list(self._addr_batch_undo or [])
        if not undo:
            QMessageBox.information(self, "串口工具", "没有可撤销的批量替换")
            return
        for index, (data_hex, protocol, match_hex) in undo:
            if not (0 <= index < len(self.commands)):
                continue
            self.commands[index]["data_hex"] = data_hex
            self.commands[index]["protocol"] = protocol
            self.commands[index]["match_hex"] = match_hex
        self._addr_batch_undo = []
        self._rebuild_cmd_table()
        self._schedule_save()
        self._log(f"[地址] 已撤销上一次批量替换（{len(undo)} 条）", "sys")

    # ── 持久化 ───────────────────────────────────────────────────────

    def _load_persisted(self):
        commands, params = load_config(self._config_path)
        self.commands = commands
        self._params = params
        self._apply_params()
        self._rebuild_cmd_table()

    def _apply_params(self):
        p = self._params
        self.interval_spin.setValue(int(p.get("interval_ms", 100)))
        self.loop_spin.setValue(int(p.get("loop_count", 1)))
        self.timeout_spin.setValue(int(p.get("timeout_ms", 5000)))
        self.chk_match.setChecked(bool(p.get("match_enabled", True)))
        self.chk_show_tx.setChecked(bool(p.get("show_tx", True)))
        self.chk_show_rx.setChecked(bool(p.get("show_rx", True)))
        self.chk_auto_scroll.setChecked(bool(p.get("auto_scroll", True)))
        self.chk_show_parse.setChecked(bool(p.get("parse_enabled", True)))
        self.parse_lines_spin.setValue(int(p.get("parse_max_lines",
                                                 DEFAULT_PARSE_MAX_LINES)))
        if p.get("rx_mode") == "frame":
            self.rx_frame_radio.setChecked(True)
        else:
            self.rx_raw_radio.setChecked(True)
        self.frame_tail_edit.setText(str(p.get("frame_tail", DEFAULT_FRAME_TAIL)))
        tail = hex_str_to_bytes(self.frame_tail_edit.text())
        if tail:
            self._frame_tail = tail
        self.frame_tail_edit.setEnabled(self.rx_frame_radio.isChecked())
        # 断帧设置（1.23.78）：载入时屏蔽信号，避免触发 _schedule_save / _log
        mode = str(p.get("rx_framing_mode", FRAMING_MODE_AUTO))
        if mode not in (FRAMING_MODE_AUTO, FRAMING_MODE_TIMEOUT):
            mode = FRAMING_MODE_AUTO
        self.framing_mode_combo.blockSignals(True)
        self.framing_mode_combo.setCurrentIndex(
            max(0, self.framing_mode_combo.findData(mode)))
        self.framing_mode_combo.blockSignals(False)
        for key, spin in (
            ("rx_byte_idle_ms", self.byte_idle_spin),
            ("rx_raw_max_hold_ms", self.raw_hold_spin),
            ("rx_frame_idle_ms", self.frame_idle_spin),
            ("rx_frame_hold_max_ms", self.frame_hold_spin),
        ):
            spin.blockSignals(True)
            spin.setValue(int(p.get(key, DEFAULT_PARAMS[key])))
            spin.blockSignals(False)
        # 日志文件：目录取自参数（无控件）；自动保存**放最后** —— 勾选会立刻创建
        # 日志文件，那时其它控件必须都已就绪（否则 _log 会碰到不存在的控件）
        self.chk_log_timestamp.setChecked(bool(p.get("log_timestamp", True)))
        self.chk_auto_save_log.setChecked(bool(p.get("log_auto_save", False)))
        self._update_log_state_label()

    def _collect_params(self) -> dict:
        return {
            "interval_ms": int(self.interval_spin.value()),
            "loop_count": int(self.loop_spin.value()),
            "timeout_ms": int(self.timeout_spin.value()),
            "match_enabled": bool(self.chk_match.isChecked()),
            "rx_mode": "frame" if self.rx_frame_radio.isChecked() else "raw",
            "frame_tail": self.frame_tail_edit.text().strip() or DEFAULT_FRAME_TAIL,
            "show_tx": bool(self.chk_show_tx.isChecked()),
            "show_rx": bool(self.chk_show_rx.isChecked()),
            "auto_scroll": bool(self.chk_auto_scroll.isChecked()),
            "parse_enabled": bool(self.chk_show_parse.isChecked()),
            "parse_max_lines": int(self.parse_lines_spin.value()),
            "rx_framing_mode": self._framing_mode(),
            "rx_byte_idle_ms": int(self.byte_idle_spin.value()),
            "rx_raw_max_hold_ms": int(self.raw_hold_spin.value()),
            "rx_frame_idle_ms": int(self.frame_idle_spin.value()),
            "rx_frame_hold_max_ms": int(self.frame_hold_spin.value()),
            "log_auto_save": bool(self.chk_auto_save_log.isChecked()),
            # 目录没有控件（只在「选择目录…」里改），直接取参数现值
            "log_dir": str(self._params.get("log_dir") or ""),
            "log_timestamp": bool(self.chk_log_timestamp.isChecked()),
        }

    def _schedule_save(self):
        """去抖落盘（500ms 合并）。"""
        self._save_timer.start(500)

    def _save_persisted(self):
        self._params = self._collect_params()
        save_config(self._config_path, self.commands, self._params)

    # ── 发送 ─────────────────────────────────────────────────────────

    def _toggle_send(self):
        if self._running:
            self._stop_send()
        else:
            self._start_send()

    def _start_send(self):
        if not self._serial_worker or not self._serial_worker.is_open():
            QMessageBox.information(
                self, "串口工具", "串口未连接：请在顶部「串口配置」中先连接串口"
            )
            return
        if not self.commands:
            QMessageBox.information(self, "串口工具", "请先添加命令")
            return
        # 只发**勾选**的命令（按表内顺序）；index_map 把「筛选后的下标」映射回
        # commands 的原下标 —— 名称/协议/匹配规则都按原下标取，否则会张冠李戴
        messages: List[bytes] = []
        index_map: List[int] = []
        for i, cmd in enumerate(self.commands):
            if not coerce_enabled(cmd.get("enabled")):
                continue
            msg = hex_str_to_bytes(cmd.get("data_hex", ""))
            if msg is None:
                QMessageBox.warning(
                    self, "命令无效",
                    f"命令「{cmd.get('name', '')}」的发送数据不是有效 HEX："
                    f"{hex_input_error(cmd.get('data_hex', ''))}"
                )
                return
            # 命令级发送次数：同一命令展开 N 帧，index_map 仍指回原下标
            n = coerce_send_count(cmd.get("send_count", 1))
            for _ in range(n):
                messages.append(msg)
                index_map.append(i)
        if not messages:
            QMessageBox.information(
                self, "串口工具",
                "没有勾选任何命令：请在命令表「选择」列勾选要发送的命令（或用「全选」）"
            )
            return

        self._tx_total = 0
        self._rx_matched = 0
        self._rx_missed = 0
        self._pending_match.clear()
        self._match_buffer.clear()
        self._match_rx_bytes = 0
        self._clear_cmd_statuses()          # 每轮开始重置状态图标（待测）

        self._sender = SerialSendWorker(
            self._serial_worker, messages,
            interval_ms=self.interval_spin.value(),
            loop_count=self.loop_spin.value(),
            parent=self,
            index_map=index_map,
        )
        # 用默认参数绑定发送器身份：停止/重开后，上一轮发送器迟到的信号必须被忽略
        sender = self._sender
        sender.sent.connect(lambda seq, idx, data: self._on_sent(seq, idx, data, sender))
        sender.done.connect(lambda: self._on_send_done(sender))
        sender.failed.connect(lambda msg: self._on_send_failed(msg, sender))
        thread_registry.track(sender, "SerialSendWorker")
        self._send_generation += 1
        self._running = True
        self._send_start_time = time.perf_counter()
        self.btn_start.setText("停止发送")
        set_btn(self.btn_start, "danger")
        self._sender.start()
        loops = "无限循环" if self.loop_spin.value() == 0 else f"{self.loop_spin.value()} 次"
        checked_cmds = [c for c in self.commands if coerce_enabled(c.get("enabled"))]
        multi = sum(
            1 for c in checked_cmds if coerce_send_count(c.get("send_count", 1)) > 1
        )
        if multi:
            scope = (
                f"{len(checked_cmds)} 条命令 → 展开 {len(messages)} 帧"
                f"（{multi} 条设置了连发次数）"
            )
        elif len(messages) != len(self.commands):
            scope = f"{len(messages)}/{len(self.commands)} 条命令（已勾选）"
        else:
            scope = f"{len(messages)} 条命令"
        self._log(f"[发送] 开始：{scope} × {loops}，间隔 "
                  f"{self.interval_spin.value()}ms", "sys")
        # 断帧依据（1.23.78）：每轮开始时输出一次，便于现场确认「按什么在断帧」
        self._log_framing_summary()

    def _stop_send(self):
        if self._sender:
            self._sender.stop()
            self._sender.wait(2000)
            self._sender = None
        if self._running:
            missed = len(self._pending_match)
            self._rx_missed += missed
            for _item in self._pending_match:        # 剩余待匹配 → 状态记失败
                self._set_cmd_status(_item.get("msg_index"), "fail")
            self._pending_match.clear()
            self._match_buffer.clear()
            self._match_rx_bytes = 0
            self._running = False
            self._log(f"[发送] 已停止（剩余 {missed} 项计为失败）", "sys")
        self.btn_start.setText("开始发送")
        set_btn(self.btn_start, "success")

    def _on_send_failed(self, msg: str, sender=None):
        if sender is not None and sender is not self._sender:
            return
        self._log(f"[发送错误] {msg}", "fail")
        self._mark_running_as("error")      # 仍在「发送中」的记为错误
        self._running = False
        self._sender = None
        self.btn_start.setText("开始发送")
        set_btn(self.btn_start, "success")

    def _on_sent(self, seq: int, msg_index: int, data: bytes, sender=None):
        if sender is not None and sender is not self._sender:
            return
        self._tx_frames += 1
        self._tx_bytes += len(data)
        name = ""
        if 0 <= msg_index < len(self.commands):
            name = self.commands[msg_index].get("name", "")
        # 锁存「最近发送命令的协议」：接收侧按它断帧 + 解析（串口是问答式，
        # RX 就是这条 TX 的响应）。同一批命令协议不同时，以**最后发出的**为准。
        proto = None
        if 0 <= msg_index < len(self.commands):
            proto = coerce_protocol(self.commands[msg_index].get("protocol"))
            if proto != self._last_tx_protocol:
                self._last_tx_protocol = proto
                # 断帧依据随协议变化 → 输出一条（不逐帧打印）
                self._log_framing_summary()
            else:
                self._last_tx_protocol = proto
        label = f"#{seq + 1} {name}".strip()
        self._tx_log_queue.append(("raw", f"{label} {bytes_to_hex(data)}"))
        # 状态：先记「通过（已发出）」；若这条命令还要等匹配，下面会改成「发送中」
        self._set_cmd_status(msg_index, "pass")
        # 发送也解析：命令自带协议，日志里与响应对称展示
        if proto is not None and self.chk_show_parse.isChecked():
            self._queue_parse(data, proto, channel="tx")
        # 入待匹配队列（源工具口径：启用匹配且该命令匹配方式非 none 才计入）
        if not self.chk_match.isChecked():
            return
        cmd = self.commands[msg_index] if msg_index < len(self.commands) else None
        if not cmd or cmd.get("match_type", "none") == "none":
            return
        match_type = cmd.get("match_type", "contains")
        if match_type in ("regex", "hex_wildcard"):
            # 这两种方式的「预期」是**文本**（正则 / HEX 通配模式），按 latin-1 编字节
            expected = cmd.get("match_hex", "").encode("latin-1", "replace")
        else:
            expected = hex_str_to_bytes(cmd.get("match_hex", ""))
        if expected is None:
            return
        self._tx_total += 1
        # 一问一答的窗口从这里重新开始：清空累积接收缓冲（避免用上一次响应的
        # 字节误判本次），并把「这次在等什么」写进日志 —— 匹配失败时才有的比对
        self._match_buffer.clear()
        self._match_rx_bytes = 0
        self._tx_log_queue.append(
            ("match",
             f"[匹配] #{seq + 1} {name} 等待响应："
             f"{match_type_label(match_type)}，"
             f"预期 = {expected_display(match_type, expected)}")
        )
        self._pending_match.append({
            "seq": seq,
            "msg_index": msg_index,
            "expected": expected,
            "match_type": cmd.get("match_type", "contains"),
            "sent": bytes(data),        # 诊断用：识别「预期填成了发送值」这类误填
            "sent_time": time.perf_counter(),
        })
        self._set_cmd_status(msg_index, "running")   # 等待响应中

    def _on_send_done(self, sender=None):
        """发送完成：等一个响应超时收尾剩余匹配（源工具语义）。

        ``sender`` 用于忽略上一轮发送器迟到的 ``done`` 信号（否则会把新一轮
        发送误判为已完成，提前收尾）。
        """
        if sender is not None and sender is not self._sender:
            return
        self._finalize_elapsed = time.perf_counter() - self._send_start_time
        generation = self._send_generation
        QTimer.singleShot(self.timeout_spin.value() + 100,
                          lambda: self._finalize_send(generation))

    def _finalize_send(self, generation: int = None):
        if generation is not None and generation != self._send_generation:
            return                      # 上一轮发送遗留的收尾定时器，忽略
        if not self._running:
            return
        missed = len(self._pending_match)
        self._rx_missed += missed
        for _item in self._pending_match:            # 剩余待匹配 → 状态记失败
            self._set_cmd_status(_item.get("msg_index"), "fail")
        self._pending_match.clear()
        self._match_buffer.clear()
        self._match_rx_bytes = 0
        self._running = False
        self._sender = None
        self.btn_start.setText("开始发送")
        set_btn(self.btn_start, "success")
        self._log(f"[发送] 全部完成，总耗时 {self._finalize_elapsed * 1000:.1f}ms", "sys")
        self._print_match_summary()

    def _print_match_summary(self):
        if self._tx_total <= 0 or not self.chk_match.isChecked():
            return
        rate = self._rx_matched / self._tx_total * 100
        self._log(
            f"[统计] 发送 {self._tx_total} 帧，成功 {self._rx_matched}，"
            f"失败/超时 {self._rx_missed}，成功率 {rate:.1f}%", "sys"
        )

    # ── 匹配 ─────────────────────────────────────────────────────────

    def _on_rx_match_data(self, data: bytes):
        """接收数据从待匹配**队首**连续比对（一批数据可连续命中多项）。

        比对对象是**累积接收缓冲**而不是单次交付的块：串口驱动会把一帧拆成多次
        交付，按单次交付比对时「预期 = 整帧」永远匹配不上（实测报障）。
        累积缓冲在**每次发送**时清空（一问一答的窗口重新开始），队列清空时也清空，
        避免用上一次响应的字节误判下一次。
        """
        self._match_rx_bytes += len(data)
        self._match_buffer.extend(data)
        if len(self._match_buffer) > MATCH_BUFFER_MAX:
            del self._match_buffer[: len(self._match_buffer) - MATCH_BUFFER_MAX]
        if not self._pending_match:
            return
        accumulated = bytes(self._match_buffer)
        while self._pending_match:
            item = self._pending_match[0]
            offset = match_offset(item["match_type"], accumulated,
                                  item["expected"])
            if offset is None:
                break
            self._rx_matched += 1
            self._pending_match.popleft()
            name = ""
            if 0 <= item["msg_index"] < len(self.commands):
                name = self.commands[item["msg_index"]].get("name", "")
            self._set_cmd_status(item["msg_index"], "pass")
            # 走 RX 队列（与响应紧挨着显示，且享受 burst 保护，防高速时刷屏）
            self._rx_log_queue.append((
                "ok",
                f"[匹配✓] #{item['seq'] + 1} {name} 匹配成功"
                f"（{match_type_label(item['match_type'])}，预期 = "
                f"{expected_display(item['match_type'], item['expected'])}，"
                f"命中偏移 {offset}）"
            ))

    def _check_match_timeout(self):
        if not self._pending_match:
            return
        timeout_s = self.timeout_spin.value() / 1000.0
        now = time.perf_counter()
        while self._pending_match:
            item = self._pending_match[0]
            if now - item["sent_time"] <= timeout_s:
                break
            self._pending_match.popleft()
            self._rx_missed += 1
            name = ""
            if 0 <= item["msg_index"] < len(self.commands):
                name = self.commands[item["msg_index"]].get("name", "")
            self._set_cmd_status(item["msg_index"], "fail")
            # 匹配失败必须给出**可比对**的信息，否则现场无从分析。
            # 走 RX 队列（与响应紧挨着显示 + burst 保护，防高速时刷屏）。
            self._rx_log_queue.append(
                ("fail", f"[匹配✗] #{item['seq'] + 1} {name} 超时未匹配")
            )
            self._rx_log_queue.append(
                ("fail", f"    匹配方式 = {match_type_label(item['match_type'])}")
            )
            self._rx_log_queue.append(
                ("fail", "    预期响应 = "
                 + expected_display(item["match_type"], item["expected"]))
            )
            self._rx_log_queue.append(
                ("fail",
                 f"    期间收到 = {hex_preview(bytes(self._match_buffer))}"
                 f"（共 {self._match_rx_bytes} 字节）")
            )
            self._rx_log_queue.append(
                ("fail",
                 "    诊断 = "
                 + match_failure_reason(item["match_type"], item["expected"],
                                        bytes(self._match_buffer),
                                        item.get("sent")))
            )
        if not self._pending_match:
            self._match_buffer.clear()
            self._match_rx_bytes = 0

    # ── 统计 ─────────────────────────────────────────────────────────

    def _poll_stats(self):
        self.lbl_tx.setText(f"发送：{self._tx_frames} 帧 / {self._tx_bytes} B")
        self.lbl_rx.setText(f"接收：{self._rx_frames} 帧 / {self._rx_bytes} B")
        # 日志文件状态（行数）随统计一起刷新，避免每写一行就 setText 触发重绘
        self._update_log_state_label()
        if self._tx_total > 0 and self.chk_match.isChecked():
            rate = self._rx_matched / self._tx_total * 100
            rate_text = f"{rate:.1f}%"
        else:
            rate_text = "—"
        self.lbl_match.setText(
            f"匹配：成功 {self._rx_matched} / 失败 {self._rx_missed} / 成功率 {rate_text}"
        )
        if self._running:
            elapsed = time.perf_counter() - self._send_start_time
        else:
            elapsed = self._finalize_elapsed
        self.lbl_time.setText(f"运行：{elapsed:.1f}s")

    def _reset_stats(self):
        if self._running:
            QMessageBox.information(self, "串口工具", "发送中不能清除统计")
            return
        self._tx_frames = self._tx_bytes = 0
        self._rx_frames = self._rx_bytes = 0
        self._tx_total = self._rx_matched = self._rx_missed = 0
        self._pending_match.clear()
        self._match_buffer.clear()
        self._match_rx_bytes = 0
        self._finalize_elapsed = 0.0
        self._poll_stats()

    # ── 收尾 ─────────────────────────────────────────────────────────

    def cleanup(self):
        """停止发送、刷出残留日志、收尾日志文件并落盘（幂等；主窗口关闭时调用）。

        **不关闭串口**：端口是主窗口共享的 `serial_worker` 的，生命周期归顶部
        「串口配置」与主窗口自身收尾逻辑（`main_gui.closeEvent`），本页只借用。

        自动保存的日志文件在这里**写统计尾并关闭**（不丢最后几帧）；勾选状态
        **保持不变**（当作偏好持久化，下次启动仍会自动保存）。
        """
        try:
            self._stop_send()
        except Exception:
            pass
        try:
            # 收尾前把聚合缓冲刷掉（源工具退出前也会 flush_raw）
            self._flush_raw_display_now()
        except Exception:
            pass
        try:
            # 队列里还没刷出的日志（最后几帧/最后几行解析）也刷出去，
            # 否则它们既不进日志窗口、也不进日志文件
            self._flush_log_queues()
        except Exception:
            pass
        try:
            self._stop_log_recording()      # 写统计尾 + 关闭文件
        except Exception:
            pass
        try:
            self._save_timer.stop()
            self._save_persisted()
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

