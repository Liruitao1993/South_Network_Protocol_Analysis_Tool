"""蓝牙通信内核（纯逻辑，**不依赖 Qt / bleak**）。

**来源**：本项目的蓝牙能力集成自工程内的 `蓝牙转串口工具02`
（PySide6 版 `main_pyside6.py` + PyTauri 版 `pytauri/bridge.py`）。本模块只保留
与界面、与 ble 栈都无关的纯逻辑，因此可以脱离 GUI 与硬件直接单测
（见 `test/test_bluetooth_core.py`）：

- BLE 通知**分包重组**（静默超时切帧）
- BLE 写入**按 MTU 分包**的尺寸计算
- 配置与自定义报文按钮的**持久化**（原子写 + 坏文件宽容）

Qt/bleak 侧的收发线程见 `bluetooth_worker.py`，界面见 `bluetooth_tool_widget.py`。

约定（与 `serial_tool_widget.py` 对齐）：
  - 配置文件走 ``app_paths.data_path()``（frozen 下在 exe 所在目录），落盘**原子写**；
  - 读配置对坏文件宽容：解析失败回落默认值，**不抛异常**；
  - 时间一律用 ``time.monotonic()``（不受系统时间调整影响）。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── 参数默认值（口径来自原工具） ────────────────────────────────────────────

# BLE 通知静默多久算「一帧完整报文」（原工具 config.ini 默认 2.991s，
# 界面 SpinBox 默认 500ms；这里统一取界面默认值，配置可改）
DEFAULT_PACKET_TIMEOUT = 0.5
PACKET_TIMEOUT_RANGE = (0.05, 10.0)

# BLE 写入分包之间的间隔（秒）
DEFAULT_SEND_PACKET_DELAY = 0.02
SEND_PACKET_DELAY_RANGE = (0.0, 1.0)

# 一次扫描 / 一次连接的时长与重试次数（原工具口径：5s / 30s / 3 次）
DEFAULT_SCAN_TIMEOUT = 5.0
DEFAULT_CONNECT_TIMEOUT = 30.0
DEFAULT_CONNECT_RETRIES = 3

# BLE 单包写入上限：原工具硬编码 200 字节（未考虑协商 MTU），
# 这里改为「按 MTU 计算 + 上限 200」——低 MTU 设备不再写入失败，
# 高 MTU 设备仍保持原工具的 200 字节行为
DEFAULT_MAX_CHUNK = 200
MIN_CHUNK = 20  # ATT 默认 MTU 23 − 3

# MTU 协商是**操作系统异步完成**的（Windows 上应用层只能读、不能请求），
# 因此连接瞬间读到的可能还是 ATT 默认值 23 —— 必须**轮询等一会儿**再取。
# 现场依据：截图里同一台设备「有时 20 字节、有时 512 字节」；bleak 官方文档
# （backends/characteristic.py）也写明「可能先读到默认值 20，过一会儿再读才是更高值」，
# 并建议用「== 20 就 sleep 再读」的循环。
MTU_DEFAULT = 23                # ATT 默认 MTU（负载 = 23 − 3 = 20）
MTU_POLL_INTERVAL = 0.25        # 秒：轮询间隔
MTU_POLL_TIMEOUT = 3.0          # 秒：等协商结果的最长时间


def mtu_is_unnegotiated(value) -> bool:
    """MTU 是否仍处在「未协商 / 未知」状态（需要再等一会儿）。

    判据单一来源：**只看是否 ≤ ATT 默认值 23**。0 / ``None`` / 非法值同样视为未协商。
    注意「对端确实只支持 23」和「协商结果还没回报」在这里不可区分（都返回 True），
    所以调用方**超时后不得报错**，只提示一行（对端可能只支持默认值）。
    """
    try:
        mtu = int(value)
    except (TypeError, ValueError):
        return True
    return mtu <= MTU_DEFAULT

# 界面日志与解析输出
DEFAULT_LOG_LINES = 5000
LOG_LINE_TRIM_STEP = 500
DEFAULT_PARSE_MAX_LINES = 30
PARSE_MAX_LINES_RANGE = (0, 2000)

# ── 特征码优选 / 探测 / 按设备记忆（1.23.79）────────────────────────────────
#
# 现场：设备常暴露几十个特征码（设备名/电量/OTA/厂商私有…），让用户手挑体验很差。
# 这里用「属性 + 厂商命名」给每条特征码打分，默认选出的即最可能承载业务的那条。
# **唯一的自动选择实现**——界面/worker 不得再写「取第一个可用」的逻辑
# （历史实现正是那样，结果常落到 `2A00` 设备名 / `2A19` 电量 / DFU 上）。
PROBE_TIMEOUT_MS = 800          # 单个候选「写完等回包」的默认时长
PROBE_TIMEOUT_RANGE = (200, 5000)
PROBE_MAX_CANDIDATES = 6        # 一键探测最多尝试的候选数
CHAR_MAP_MAX = 20               # 按设备地址记忆的条数上限（超出按 ts 淘汰最旧）

#: 自定义报文按钮
MAX_CUSTOM_BUTTONS = 64
BUTTON_NAME_MAX = 32
#: 按钮「地址参数」的字段名/值长度上限（坏配置不得撑爆界面）
ADDR_KEY_MAX = 16
ADDR_VALUE_MAX = 64

# ── 自定义报文区的空间治理（1.23.82）──────────────────────────────────────
#: 按钮网格**最少**可见几行（滚动区高度下限；上限由界面按「内容需要多少」算，
#: 因此空间够时按钮会全部显示、不会白滚动）。
CUSTOM_MIN_ROWS = 1
#: 右栏竖向分栏（日志 ↔ 发送+自定义）的默认高度（px）与合法范围
RIGHT_SPLIT_DEFAULT = (420, 240)
RIGHT_SPLIT_RANGE = (60, 4000)

# 配置文件名（app_paths.data_path 下，与 serial_tool_config.json 同级）
SETTINGS_NAME = "bluetooth_tool_config.json"
SETTINGS_VERSION = 1

DEFAULT_SETTINGS: Dict[str, object] = {
    "show_hex": True,            # 日志/发送区按 HEX（关 = ASCII）
    "auto_scroll": True,         # 日志自动滚动到底
    "parse_enabled": True,       # 收到的完整帧按当前协议解析并输出文字
    "parse_max_lines": DEFAULT_PARSE_MAX_LINES,
    "parse_protocol": None,      # None = 跟随主窗口当前协议；数字 = 本页临时指定
    "virtual_mode": False,       # 蓝牙 ⇄ 串口双向透传
    "packet_timeout": DEFAULT_PACKET_TIMEOUT,
    "send_packet_delay": DEFAULT_SEND_PACKET_DELAY,
    "send_format": "auto",       # auto（HEX 优先）/ hex / ascii
    "filter_named_only": False,  # 设备表只显示带名称的设备
    "auto_refresh": False,       # 扫描完成后自动重新扫描
    "auto_refresh_interval": 10,
    "last_device": "",           # 上次连接的设备地址（下次启动高亮）
    "last_device_name": "",
    # 上次选择接收/发送特征码（UUID 全称；连接后自动回填，省去每次重选）
    "recv_uuids": [],
    "send_uuids": [],
    # 按**设备地址**记住的特征码选择（1.23.79）：{"<address>": {recv, send, source, ts}}
    # 命中该地址时直接用，省去重新优选；未命中才走打分优选。
    "char_map": {},
    # 一键探测：探测帧（HEX；发送框为空时用它）与单项等待时长
    "probe_frame": "41 54",           # "AT"（ASCII）
    "probe_timeout_ms": PROBE_TIMEOUT_MS,
    # 日志文件（自动保存）—— 默认**关闭**：不勾选行为与源工具一致
    "log_auto_save": False,      # 勾选即实时把日志写入文件
    "log_dir": "",               # 空 = 默认目录（数据目录下的 Output/）
    "log_timestamp": True,       # 文件里每行加毫秒时间戳前缀
    # 自定义报文区空间治理（1.23.82）：收起状态 + 右栏竖向分栏高度（日志, 下半区）
    "custom_collapsed": False,
    "right_split": list(RIGHT_SPLIT_DEFAULT),
}

SCAN_INTERVAL_RANGE = (3, 600)


# ── 配置与按钮：宽容读取 + 原子写 ──────────────────────────────────────────


def _as_bool(value, default: bool = False) -> bool:
    """宽松布尔：接受 bool / 数字 / "true"/"on"/"1" 等字面量。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on", "是"):
            return True
        if text in ("0", "false", "no", "off", "否"):
            return False
    return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def merge_settings(raw) -> dict:
    """把任意来源的配置合并到默认值上，并夹紧数值范围（坏值不抛异常）。"""
    out = dict(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return out
    for key in ("show_hex", "auto_scroll", "parse_enabled", "virtual_mode",
                "filter_named_only", "auto_refresh", "log_auto_save",
                "log_timestamp"):
        if key in raw:
            out[key] = _as_bool(raw[key], bool(DEFAULT_SETTINGS[key]))
    if "parse_max_lines" in raw:
        out["parse_max_lines"] = int(
            _clamp(_as_int(raw["parse_max_lines"], DEFAULT_PARSE_MAX_LINES),
                   *PARSE_MAX_LINES_RANGE)
        )
    if "auto_refresh_interval" in raw:
        out["auto_refresh_interval"] = int(
            _clamp(_as_int(raw["auto_refresh_interval"], 10), *SCAN_INTERVAL_RANGE)
        )
    if "packet_timeout" in raw:
        out["packet_timeout"] = round(
            _clamp(_as_float(raw["packet_timeout"], DEFAULT_PACKET_TIMEOUT),
                   *PACKET_TIMEOUT_RANGE), 3
        )
    if "send_packet_delay" in raw:
        out["send_packet_delay"] = round(
            _clamp(_as_float(raw["send_packet_delay"], DEFAULT_SEND_PACKET_DELAY),
                   *SEND_PACKET_DELAY_RANGE), 3
        )
    for key in ("last_device", "last_device_name", "log_dir"):
        if key in raw and raw[key] is not None:
            out[key] = str(raw[key]).strip()
    # 解析协议：None = 跟随主窗口；数字 = 本页临时指定（负数/非法一律回落 None）
    if "parse_protocol" in raw:
        value = raw["parse_protocol"]
        if value is None:
            out["parse_protocol"] = None
        else:
            parsed = _as_int(value, -1)
            out["parse_protocol"] = parsed if parsed >= 0 else None
    # 发送格式：只认已知取值，非法一律回落默认（auto）
    if "send_format" in raw:
        value = str(raw["send_format"] or "").strip().lower()
        out["send_format"] = value if value in ("auto", "hex", "ascii") else "auto"
    for key in ("recv_uuids", "send_uuids"):
        if key in raw:
            value = raw[key]
            if isinstance(value, (list, tuple)):
                out[key] = [str(u).strip() for u in value if str(u or "").strip()]
            elif isinstance(value, str) and value.strip():
                # 手改 JSON 时写成单个字符串（或逗号分隔）也认
                out[key] = [u.strip() for u in value.split(",") if u.strip()]
    # 特征码选择记忆（1.23.79）：逐条丢弃坏条目（不影响其它条目），并按 ts 限量
    if "char_map" in raw:
        out["char_map"] = normalize_char_map(raw["char_map"])
    # 探测帧：只做字符串清理（**HEX 合法性在使用时校验**：解析实现属界面侧，
    # 这里不引入第二份「什么算合法 HEX」；坏值在探测开始时提示并回落内置默认帧）
    if "probe_frame" in raw:
        text = str(raw["probe_frame"] or "").strip()
        out["probe_frame"] = text or str(DEFAULT_SETTINGS["probe_frame"])
    if "probe_timeout_ms" in raw:
        out["probe_timeout_ms"] = int(
            _clamp(_as_int(raw["probe_timeout_ms"], PROBE_TIMEOUT_MS), *PROBE_TIMEOUT_RANGE)
        )
    # 自定义报文区空间治理（1.23.82）
    if "custom_collapsed" in raw:
        out["custom_collapsed"] = _as_bool(raw["custom_collapsed"], False)
    if "right_split" in raw:
        out["right_split"] = normalize_right_split(raw["right_split"])
    return out


def normalize_right_split(raw) -> list:
    """右栏竖向分栏尺寸 ``[日志, 下半区]``（px）：长度/类型/越界一律宽容处理。

    坏值（非序列、长度≠2、非数字、越界）逐项回落/夹紧到 ``RIGHT_SPLIT_RANGE``，
    绝不抛异常——配置坏掉不该让蓝牙页打不开。
    """
    low, high = RIGHT_SPLIT_RANGE
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return list(RIGHT_SPLIT_DEFAULT)
    out = []
    for index, item in enumerate(raw):
        value = _as_int(item, -1)
        if value <= 0:
            value = RIGHT_SPLIT_DEFAULT[index]
        out.append(int(_clamp(value, low, high)))
    return out


def normalize_addr_map(raw) -> dict:
    """规范化按钮的**地址参数**：``{字段 key: 文本}``（非 dict / 空键空值一律丢弃）。

    「协议 + 地址」是 1.23.81 新增能力（发送前按协议替换地址并重算校验）；旧配置没有这两个键
    ⇒ 返回空 dict / 不写 protocol，行为与改动前完全一致。
    """
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key, value in raw.items():
        name = str(key or "").strip()[:ADDR_KEY_MAX]
        text = str(value or "").strip()[:ADDR_VALUE_MAX]
        if name and text:
            out[name] = text
    return out


def normalize_button(raw, fallback_name: str = "未命名") -> Optional[dict]:
    """规范化一个自定义报文按钮；内容为空的按钮返回 None（没有意义）。"""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip() or fallback_name
    data = str(raw.get("data") or "").strip()
    if not data:
        return None
    is_hex = raw.get("isHex", raw.get("is_hex", True))
    button = {
        "name": name[:BUTTON_NAME_MAX],
        "data": data,
        "isHex": _as_bool(is_hex, True),
    }
    # 协议 + 地址（可选；缺省不写键 ⇒ 旧文件/旧版本互不影响）
    protocol_raw = raw.get("protocol", raw.get("protocol_index"))
    if protocol_raw is not None and str(protocol_raw).strip() != "":
        try:
            button["protocol"] = int(protocol_raw)
        except (TypeError, ValueError):
            pass
    addr = normalize_addr_map(raw.get("addr", raw.get("address")))
    if addr:
        button["addr"] = addr
    return button


def normalize_buttons(raw, limit: int = MAX_CUSTOM_BUTTONS) -> List[dict]:
    """规范化自定义报文按钮列表（去空、限量、非列表宽容为空）。"""
    if not isinstance(raw, (list, tuple)):
        return []
    out: List[dict] = []
    for index, item in enumerate(raw):
        button = normalize_button(item, f"报文{index + 1}")
        if button is not None:
            out.append(button)
        if len(out) >= limit:
            break
    return out


def load_settings(path) -> Tuple[List[dict], dict]:
    """读取 ``(自定义按钮, 设置)``；文件缺失/损坏一律回落默认值。"""
    raw = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return normalize_buttons(raw.get("custom_buttons")), merge_settings(raw.get("settings"))


def save_settings(path, buttons, settings) -> bool:
    """原子写配置（同目录临时文件 + ``os.replace``）；失败返回 False 不抛异常。"""
    payload = {
        "version": SETTINGS_VERSION,
        "settings": merge_settings(settings),
        "custom_buttons": normalize_buttons(buttons),
    }
    target = Path(path)
    temp_path = ""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle_fd, temp_path = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
        )
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        return True
    except (OSError, TypeError, ValueError):
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        return False


# ── 显示用短名 ────────────────────────────────────────────────────────────

# 蓝牙 SIG 标准 UUID 的公共后缀（短 UUID 展开后的固定形式）
STANDARD_UUID_SUFFIX = "-0000-1000-8000-00805f9b34fb"


def short_uuid(uuid) -> str:
    """特征码 UUID 的短显示。

    标准 SIG UUID（``0000fff1-0000-1000-8000-00805f9b34fb``）显示为 ``0xFFF1``，
    4 位短写显示为 ``0xFFF1``，其它自定义 UUID 截前 8 字符（不截断成半截单词）。
    """
    text = str(uuid or "").strip().lower()
    if not text:
        return ""
    if len(text) == 36 and text.endswith(STANDARD_UUID_SUFFIX):
        return "0x" + text[4:8].upper()
    if len(text) == 4:
        return "0x" + text.upper()
    return text[:8]


# ── 特征码优选（打分）──────────────────────────────────────────────────────
#
# 打分要素与权重**只在这里定义**（界面不另写一份）：调参改这里即可。
CHAR_SCORE_BOTH = 50            # 同一条码同时可写可通知（透传回环最常见）
CHAR_SCORE_PASSTHROUGH = 40     # 命中厂商透传族谱
CHAR_SCORE_HINT = 20            # 名称/描述/服务名带 tx/rx/uart/串口 等提示词
CHAR_SCORE_SAME_SERVICE = 15    # 与「最佳发送码」同属一个 service（透传对通常同服务）
CHAR_SCORE_STANDARD_GATT = -60  # 标准 GATT（设备名/电量/固件版本…）不承载业务
CHAR_SCORE_OTA_DFU = -60        # OTA/DFU 误写有风险

# 厂商透传族谱（4 位短码，小写）：Nordic UART / HM-10 / 常见模块的透传对
PASSTHROUGH_UUIDS = frozenset({
    "6e400002", "6e400003",            # Nordic UART Service（写/通知）
    "ffe1", "ffe5", "ffe9", "ffe0",    # HM-10 / CC2540 / 通用透传
    "fff0", "fff1", "fff2", "fff6",    # 微雪 / 正点原子等
    "ff01", "ff02", "ff10", "ff11",
    "ae01", "ae02",
})
# 名称/描述里的提示词（小写匹配）
PASSTHROUGH_HINTS = ("tx", "rx", "uart", "serial", "write", "notify", "indicate",
                     "透传", "串口", "调试", "transparent")
# 标准 GATT 服务（4 位短码）与 OTA/DFU 短码
STANDARD_GATT_SERVICES = frozenset({"1800", "1801", "1805", "1809", "180a", "180f"})
OTA_DFU_UUIDS = frozenset({"fe59", "1530", "ffc0", "ffc1"})


def uuid_key(uuid) -> str:
    """UUID → 4 位小写短码（标准 128bit / 短写 / ``0000ffe1`` 都能归一）；识别不了返回 ""。"""
    text = str(uuid or "").strip().lower()
    if not text:
        return ""
    if len(text) == 36 and text.endswith(STANDARD_UUID_SUFFIX):
        return text[4:8]
    if len(text) == 4:
        return text
    if len(text) == 8:
        return text[4:8]
    return ""


def _is_standard_gatt_key(key: str) -> bool:
    """``2Axx`` 是标准 GATT 特征码（设备名/电量/固件版本…）。"""
    return bool(key) and len(key) == 4 and key.startswith("2a")


def _hits_hint(char) -> bool:
    text = " ".join(
        str(char.get(k) or "") for k in ("description", "service_short", "service_uuid")
    ).lower()
    return any(hint in text for hint in PASSTHROUGH_HINTS)


def char_score(char, best_service: str = "") -> int:
    """一条特征码「像业务透传通道」的打分（越大越像；不修改入参）。"""
    if not isinstance(char, dict):
        return 0
    score = 0
    if char.get("can_send") and char.get("can_recv"):
        score += CHAR_SCORE_BOTH
    key = uuid_key(char.get("uuid"))
    if key and key in PASSTHROUGH_UUIDS:
        score += CHAR_SCORE_PASSTHROUGH
    if _hits_hint(char):
        score += CHAR_SCORE_HINT
    if best_service and str(char.get("service_uuid") or "").lower() == str(best_service).lower():
        score += CHAR_SCORE_SAME_SERVICE
    if _is_standard_gatt_key(key) or uuid_key(char.get("service_uuid")) in STANDARD_GATT_SERVICES:
        score += CHAR_SCORE_STANDARD_GATT
    if key and key in OTA_DFU_UUIDS:
        score += CHAR_SCORE_OTA_DFU
    return score


def _score_reason(char) -> str:
    """给日志用的一句话依据（用户据此判断「凭什么选它」）。"""
    notes: List[str] = []
    if char.get("can_send") and char.get("can_recv"):
        notes.append("同时可写可通知")
    key = uuid_key(char.get("uuid"))
    if key and key in PASSTHROUGH_UUIDS:
        notes.append("厂商透传族谱")
    if _hits_hint(char):
        notes.append("名称含透传提示词")
    if _is_standard_gatt_key(key):
        notes.append("标准 GATT（已降权）")
    if key and key in OTA_DFU_UUIDS:
        notes.append("OTA/DFU（已降权）")
    return " + ".join(notes) if notes else "普通可写通道"


def rank_characteristics(chars) -> List[dict]:
    """按打分降序返回特征码**副本**（附 ``score``）；**同分保持设备枚举顺序**（稳定排序）。"""
    items = [dict(c) for c in (chars or [])
             if isinstance(c, dict) and str(c.get("uuid") or "").strip()]
    if not items:
        return []
    base = [(c, char_score(c)) for c in items]
    sends = [(c, s) for c, s in base if c.get("can_send")]
    best_service = str(max(sends, key=lambda t: t[1])[0].get("service_uuid") or "") if sends else ""
    ranked: List[dict] = []
    for char, _ in base:
        item = dict(char)
        item["score"] = char_score(char, best_service)
        ranked.append(item)
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked


def pick_auto(chars) -> Tuple[List[str], List[str], str]:
    """打分优选「接收 / 发送」通道；返回 ``(recv_uuids, send_uuids, reason)``。

    - 发送 = 分数最高的**可发送**码；
    - 接收优先取**同一条码**（透传回环），否则同 service 内分最高的可收码，再否则全局分最高的可收码。

    **唯一的自动选择实现**：界面不要再写「取第一个可用」——那正是历史实现，
    结果常落到设备名（`2A00`）/ 电量（`2A19`）/ DFU 上，用户仍得手挑。
    """
    ranked = rank_characteristics(chars)
    if not ranked:
        return [], [], "设备未提供特征码"
    send_c = next((c for c in ranked if c.get("can_send")), None)
    recv_c: Optional[dict] = None
    if send_c is not None and send_c.get("can_recv"):
        recv_c = send_c                                   # 同码回环：最常见
    if recv_c is None and send_c is not None:
        svc = str(send_c.get("service_uuid") or "")
        if svc:
            recv_c = next((c for c in ranked if c.get("can_recv")
                           and str(c.get("service_uuid") or "") == svc), None)
    if recv_c is None:
        recv_c = next((c for c in ranked if c.get("can_recv")), None)
    recv = [str(recv_c["uuid"])] if recv_c else []
    send = [str(send_c["uuid"])] if send_c else []
    parts: List[str] = []
    if send_c is not None:
        parts.append(f"发送 {short_uuid(send_c['uuid'])}（{_score_reason(send_c)}）")
    if recv_c is not None:
        if recv_c is send_c:
            parts.append(f"接收 {short_uuid(recv_c['uuid'])}（同一特征码，回环）")
        else:
            parts.append(f"接收 {short_uuid(recv_c['uuid'])}（同服务配对）")
    elif not send:
        return [], [], "没有可用特征码（既不可写也不可通知）"
    if not recv:
        parts.append("未找到可接收通道（只能发送）")
    return recv, send, "；".join(parts) if parts else "无"


def probe_candidates(chars, limit: int = PROBE_MAX_CANDIDATES) -> List[dict]:
    """一键探测的候选序列（按打分取前 N 个**可发送**码，并各配一个接收通道）。

    每项：``{send, recv, label, has_recv, score}``；``recv`` 为空表示该候选无法验证回包
    （只验证写入是否成功）。
    """
    ranked = rank_characteristics(chars)
    sends = [c for c in ranked if c.get("can_send")]
    out: List[dict] = []
    for char in sends[: max(1, int(limit))]:
        svc = str(char.get("service_uuid") or "")
        recv = char if char.get("can_recv") else None
        if recv is None and svc:
            recv = next((r for r in ranked if r.get("can_recv")
                         and str(r.get("service_uuid") or "") == svc), None)
        if recv is None:
            recv = next((r for r in ranked if r.get("can_recv")), None)
        out.append({
            "send": str(char.get("uuid")),
            "recv": str(recv.get("uuid")) if recv else "",
            "label": short_uuid(char.get("uuid")),
            "has_recv": bool(recv),
            "score": int(char.get("score") or 0),
        })
    return out


def resolve_probe_payload(edit_text: str, mode: str, default_hex: str,
                          parse) -> Tuple[Optional[bytes], str, str]:
    """探测载荷：**优先**用发送框内容，为空才用默认帧。

    ``parse(text, mode) -> (payload|None, error)`` **必须由调用方注入** —— 本模块是纯逻辑层，
    不 import 界面侧的解析实现（也避免出现第二份「什么算合法 HEX」的判据）。
    界面注入 ``bluetooth_tool_widget.parse_plain_text``；测试注入自己的 fake。

    返回 ``(payload|None, error, source)``，``source ∈ {"edit", "default"}``。
    解析失败时 **payload=None**（绝不「探测性地写出半截字节」）。
    """
    text = str(edit_text or "").strip()
    if text:
        payload, error = parse(text, mode)
        return (payload, "", "edit") if payload is not None else (None, error, "edit")
    payload, error = parse(str(default_hex or ""), "hex")
    if payload is None:
        return None, f"默认探测帧无效：{error}", "default"
    return payload, "", "default"


class ProbeSession:
    """特征码「一键探测」会话（纯逻辑：无 Qt / 无 bleak，可脱硬件单测）。

    界面按 :meth:`next` 返回的意图调用 worker，再把 worker 信号与超时喂回来：

        意图 ``{"action": "select", "recv": [...], "send": [...]}`` → worker.set_characteristics
        → 等 ``subscribe_finished`` → :meth:`on_subscribed`
        意图 ``{"action": "write", "payload": b".."}``              → worker.send_data
        → 成功 ``data_sent`` / 失败 → :meth:`on_written`
        意图 ``{"action": "wait", "timeout_ms": N}``                → 起定时器等回包
        → ``frame_received`` → :meth:`on_frame`；超时 → :meth:`on_timeout`
        ``None`` = 结束（用 :meth:`result` 取结论）

    候选无接收通道时：写入成功即判成功（结论里注明「仅验证写入」）。
    """

    def __init__(self, candidates, payload: bytes, timeout_ms: int = PROBE_TIMEOUT_MS):
        self.candidates = [dict(c) for c in (candidates or []) if isinstance(c, dict)]
        self.payload = bytes(payload or b"")
        self.timeout_ms = int(_clamp(_as_int(timeout_ms, PROBE_TIMEOUT_MS), *PROBE_TIMEOUT_RANGE))
        self.attempts: List[dict] = []
        self.winner: Optional[dict] = None
        self._index = -1
        self._step = ""            # "" → select → write → wait → done
        self._detail = ""

    # ── 内部 ──
    @property
    def step(self) -> str:
        """当前阶段（``""`` / ``select`` / ``write`` / ``wait`` / ``done``）。

        界面据此判断「这个事件有没有让会话前进」，避免把同一意图重复下发一次。
        """
        return self._step

    @property
    def position(self) -> Tuple[int, int]:
        """``(当前候选序号 1-based, 候选总数)`` —— 界面进度显示用。"""
        return (min(self._index + 1, len(self.candidates)), len(self.candidates))

    def _candidate(self) -> dict:
        return self.candidates[self._index]

    def _record(self, status: str, detail: str) -> None:
        char = self._candidate()
        self.attempts.append({
            "send": char.get("send"), "recv": char.get("recv"),
            "label": char.get("label"), "has_recv": bool(char.get("has_recv")),
            "status": status, "detail": detail,
        })

    def _goto(self, index: int) -> None:
        self._index = index
        self._step = "select" if index < len(self.candidates) else "done"

    def _fail(self, status: str, detail: str) -> None:
        self._record(status, detail)
        self._goto(self._index + 1)

    def _succeed(self, detail: str) -> None:
        self._record("ok", detail)
        self.winner = dict(self._candidate())
        self._detail = detail
        self._step = "done"

    # ── 外部 ──
    def next(self) -> Optional[dict]:
        """返回下一个意图；``None`` = 结束。首次调用自动进入第一个候选。"""
        if self._step == "":
            self._goto(0)
        if self._step == "done":
            return None
        char = self._candidate()
        if self._step == "select":
            recv = [char["recv"]] if char.get("recv") else []
            return {"action": "select", "recv": recv, "send": [char.get("send") or ""]}
        if self._step == "write":
            return {"action": "write", "payload": self.payload}
        if self._step == "wait":
            return {"action": "wait", "timeout_ms": self.timeout_ms}
        return None

    def on_subscribed(self, ok: bool) -> None:
        """收到 ``subscribe_finished``。无接收通道的候选项不会被订阅（``ok`` 视为 True）。"""
        if self._step != "select":
            return
        char = self._candidate()
        if char.get("recv") and not ok:
            self._fail("subscribe", f"订阅 {short_uuid(char.get('recv'))} 失败")
            return
        self._step = "write"

    def on_written(self, ok: bool) -> None:
        """写入结果（``data_sent`` / 写入失败）。"""
        if self._step != "write":
            return
        char = self._candidate()
        if not ok:
            self._fail("write", f"写入 {short_uuid(char.get('send'))} 失败")
            return
        if not char.get("recv"):
            self._succeed("写入成功（该候选无接收通道，仅验证写入）")
            return
        self._step = "wait"

    def on_frame(self, nbytes: int) -> None:
        """收到回包（``frame_received``）→ 命中，立即结束。"""
        if self._step != "wait":
            return
        self._succeed(f"收到 {int(nbytes)} 字节回包")

    def on_timeout(self) -> None:
        """界面定时器超时（选码/写/等回包三阶段都兜底）。"""
        if self._step == "select":
            self._fail("subscribe", f"订阅在 {self.timeout_ms} ms 内未完成")
        elif self._step == "write":
            self._fail("write", f"写入在 {self.timeout_ms} ms 内未确认")
        elif self._step == "wait":
            char = self._candidate()
            self._fail("timeout", f"写入成功但 {self.timeout_ms} ms 内无回包"
                                  f"（接收 {short_uuid(char.get('recv'))}）")

    def stop(self) -> None:
        """用户中途停止（已记录的尝试保留）。"""
        self._step = "done"

    def result(self) -> dict:
        return {
            "ok": self.winner is not None,
            "winner": dict(self.winner) if self.winner else None,
            "detail": self._detail,
            "attempts": list(self.attempts),
            "done": self._step == "done",
        }


# ── 按设备地址记忆特征码选择 ───────────────────────────────────────────────


def _clean_uuid_list(value) -> List[str]:
    if isinstance(value, (list, tuple)):
        out = [str(u).strip() for u in value if str(u or "").strip()]
    elif isinstance(value, str) and value.strip():
        out = [u.strip() for u in value.split(",") if u.strip()]
    else:
        out = []
    return out[:8]          # 防御：单个设备最多记 8 条


def normalize_char_map(raw) -> dict:
    """规范化 ``char_map``：逐条丢弃坏条目（不影响其它条目），超上限按 ``ts`` 淘汰最旧。"""
    out: Dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for address, entry in raw.items():
        key = str(address or "").strip()
        if not key or not isinstance(entry, dict):
            continue
        recv = _clean_uuid_list(entry.get("recv"))
        send = _clean_uuid_list(entry.get("send"))
        if not recv and not send:
            continue
        source = str(entry.get("source") or "").strip()
        if source not in ("auto", "probe", "manual", "recall"):
            source = "manual"
        out[key] = {"recv": recv, "send": send, "source": source,
                    "ts": _as_int(entry.get("ts"), 0)}
    if len(out) > CHAR_MAP_MAX:
        keep = sorted(out.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)
        out = dict(keep[:CHAR_MAP_MAX])
    return out


def recall_choice(settings, address) -> Optional[dict]:
    """取该设备地址记住的选择（没有/坏条目 → ``None``）。"""
    char_map = (settings or {}).get("char_map") if isinstance(settings, dict) else None
    if not isinstance(char_map, dict):
        return None
    entry = char_map.get(str(address or "").strip())
    return dict(entry) if isinstance(entry, dict) else None


def remember_choice(settings, address, recv, send, source: str = "auto") -> dict:
    """按设备地址记住选择（**就地更新** settings 并返回；空地址直接返回原值）。"""
    key = str(address or "").strip()
    if not key or not isinstance(settings, dict):
        return settings
    char_map = normalize_char_map(settings.get("char_map"))
    char_map[key] = {
        "recv": _clean_uuid_list(recv), "send": _clean_uuid_list(send),
        "source": source if source in ("auto", "probe", "manual", "recall") else "auto",
        "ts": int(time.time()),
    }
    settings["char_map"] = normalize_char_map(char_map)
    return settings


def forget_choice(settings, address) -> bool:
    """忘掉某设备的选择（返回是否真的删掉了）。"""
    if not isinstance(settings, dict):
        return False
    char_map = normalize_char_map(settings.get("char_map"))
    key = str(address or "").strip()
    if key not in char_map:
        return False
    del char_map[key]
    settings["char_map"] = char_map
    return True


# ── BLE 写入分包 ──────────────────────────────────────────────────────────


def chunk_size_for_mtu(mtu, limit: int = DEFAULT_MAX_CHUNK) -> int:
    """按协商 MTU 计算单包写入字节数。

    ``MTU − 3``（ATT 头 3 字节）为负载上限，再夹到 ``[MIN_CHUNK, limit]``。
    MTU 未知（0 / None / 非法值）时回落 ``MIN_CHUNK``（BLE 保证的最小可用值）。
    """
    try:
        value = int(mtu)
    except (TypeError, ValueError):
        value = 0
    if value <= 3:
        return max(MIN_CHUNK, min(int(limit), MIN_CHUNK))
    return max(MIN_CHUNK, min(int(limit), value - 3))


def split_chunks(data: bytes, chunk_size: int) -> List[bytes]:
    """把数据按 ``chunk_size`` 切成待逐包写入的列表（空数据返回空列表）。"""
    if not data:
        return []
    size = max(1, int(chunk_size))
    return [bytes(data[i:i + size]) for i in range(0, len(data), size)]


# ── BLE 通知分包重组 ──────────────────────────────────────────────────────


class BleReassembler:
    """按「静默超时」把 BLE 通知分包重组为完整报文。

    语义（与 PyTauri 版 `bridge.py` 一致，也是原工具 README 描述的行为）：
      - 同一特征码的通知字节按到达顺序累积；
      - 静默超过 ``timeout`` 秒 → 视为一帧完整报文；
      - **不同特征码各自独立成帧**（不混流）；
      - ``timeout`` 取 0 表示不等待，投递后立即成帧（测试/特殊设备用）。

    调用方只需 :meth:`feed` 投递分包，再周期性 :meth:`poll` 取帧。
    """

    def __init__(self, timeout: float = DEFAULT_PACKET_TIMEOUT):
        self._timeout = max(0.0, float(timeout))
        self._buffers: Dict[str, bytearray] = {}
        self._stamps: Dict[str, float] = {}

    @property
    def timeout(self) -> float:
        return self._timeout

    def set_timeout(self, timeout: float) -> None:
        """改超时值；**已在缓冲中的数据保持不动**（不会因此丢帧）。"""
        self._timeout = max(0.0, float(timeout))

    def feed(self, uuid: str, data: bytes, now: Optional[float] = None) -> None:
        """投递一个通知分包（空数据忽略；``now`` 仅测试注入）。"""
        if not data:
            return
        stamp = time.monotonic() if now is None else float(now)
        self._buffers.setdefault(str(uuid), bytearray()).extend(data)
        self._stamps[str(uuid)] = stamp

    def poll(self, now: Optional[float] = None) -> List[Tuple[str, bytes]]:
        """取出所有静默已超时的缓冲，返回 ``[(uuid, 完整报文), ...]``。"""
        stamp_now = time.monotonic() if now is None else float(now)
        frames: List[Tuple[str, bytes]] = []
        for uuid in list(self._buffers):
            if stamp_now - self._stamps.get(uuid, stamp_now) < self._timeout:
                continue
            frames.append((uuid, bytes(self._buffers.pop(uuid))))
            self._stamps.pop(uuid, None)
        return frames

    def flush(self) -> List[Tuple[str, bytes]]:
        """立即取出全部缓冲（断开连接 / 关闭页面时用，不计超时）。"""
        frames = [(uuid, bytes(buf)) for uuid, buf in self._buffers.items() if buf]
        self.clear()
        return frames

    def clear(self) -> None:
        self._buffers.clear()
        self._stamps.clear()

    def pending_bytes(self) -> int:
        """缓冲中尚未成帧的字节数（界面「等待重组」统计用）。"""
        return sum(len(buf) for buf in self._buffers.values())
