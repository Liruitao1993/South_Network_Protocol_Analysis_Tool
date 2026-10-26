# -*- coding: utf-8 -*-
"""
TCP 流量监控器 Widget

基于 scapy 的 TCP 流量捕获 + 流重组 + 应用层协议解析。

支持国网新一代（协议10）/ 南网新一代（协议9）/ HDC 1.0（协议11）解析。
在协议下拉框显式选择「HDC 1.0」时，可解析 ED..EE 监控封装头、网络层
（FC/PB）与应用层（MAC/MSDU/MME）字段，并按定界符类型区分信标帧 / SOF 帧 /
选择确认帧(SACK) / 网间协调帧。

「自动识别」的范围与上述**不同**：它只在拿到 CRC-24 自证的帧控制证据时把
HDC 1.0 候选提前，因此覆盖信标帧 / SOF 帧 / SACK / 网间协调帧四类；
MAC/应用层帧需显式选择协议（原因见 ``hdc_fc_evidence`` 的 docstring）。
"""

import time
import csv
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QLineEdit, QSplitter, QMessageBox, QGroupBox, QMenu,
    QTabWidget, QCheckBox, QTreeWidget, QTreeWidgetItem, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QGuiApplication, QColor
from gui_utils import ZoomableTableWidget, set_btn, set_btn_icon, fit_btn_width
from hex_dump_view import HexDumpView
import parse_result_view
import app_paths
import thread_registry

# scapy 可选依赖 — 用 find_spec 轻量探测是否安装；scapy.all 首次导入耗时数秒，
# 禁止在模块级/GUI 线程导入，实际符号由 _load_scapy() 在后台线程惰性加载
import importlib.util

SCAPY_AVAILABLE = importlib.util.find_spec("scapy") is not None
_SCAPY_LOADED = False

sniff = IP = TCP = get_if_list = get_if_addr = None


def _load_scapy():
    """惰性加载 scapy 符号（首次导入很慢，切勿在 GUI 主线程调用）"""
    global _SCAPY_LOADED, sniff, IP, TCP, get_if_list, get_if_addr
    if not SCAPY_AVAILABLE:
        return False
    if _SCAPY_LOADED:
        return True
    from scapy.all import sniff, IP, TCP, get_if_list, get_if_addr
    _SCAPY_LOADED = True
    return True


# ── 记录位置（CSV 落盘目录，纯逻辑无 Qt，可脱离 GUI 单测）────────────
#
# 现场诉求：记录下来的 CSV 找不到、也不知道去哪找。故：
#   ① 目录可配置（``record_dir`` 存 tcp_monitor_config.json，空 = 默认）；
#   ② 「打开位置」按钮一键在文件管理器中**定位并选中**当前记录文件（无文件时打开目录）。
# 默认目录与串口工具日志目录同一约定（数据目录下的 ``Output/``）。
#
# 配置路径一律经 ``app_paths.data_path`` **属性访问**（不是 ``from ... import``），
# 否则测试的沙箱 patch 挡不住，会把开发机真实数据目录写脏（同 AGENTS §8 陷阱 60）。

TCP_MONITOR_CONFIG_NAME = "tcp_monitor_config.json"
DEFAULT_RECORD_DIR_NAME = "Output"


def default_record_dir(data_dir=None) -> str:
    """默认记录目录：``<数据目录>/Output``（``data_dir`` 仅供测试注入）。"""
    base = Path(app_paths.app_data_dir()) if data_dir is None else Path(data_dir)
    return str(base / DEFAULT_RECORD_DIR_NAME)


def load_record_config(path=None) -> dict:
    """读取 TCP 监控配置；缺失/损坏/非对象一律回落空配置（绝不抛异常）。"""
    p = Path(path) if path is not None else Path(app_paths.data_path(TCP_MONITOR_CONFIG_NAME))
    try:
        with open(p, "r", encoding="utf-8-sig") as f:  # 容 BOM（编辑器另存常见）
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_record_config(cfg: dict, path=None) -> bool:
    """原子写 TCP 监控配置（临时文件 + ``os.replace``）；失败返回 False。"""
    p = Path(path) if path is not None else Path(app_paths.data_path(TCP_MONITOR_CONFIG_NAME))
    tmp = p.with_name(p.name + ".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def resolve_record_dir(configured: Optional[str], default_dir: str) -> str:
    """记录目录：用户配置优先（非空才算），否则默认目录。"""
    return (configured or "").strip() or default_dir


def open_in_file_manager(path: str, directory: str) -> str:
    """在系统文件管理器中打开：有 ``path`` 则定位并选中该文件，否则打开目录。

    返回实际打开的目标（供状态栏与测试断言）；失败抛 ``OSError`` 由调用方提示。
    Windows 用 ``explorer /select,``（定位文件）；其它平台回落 ``xdg-open``。
    """
    if path and os.path.exists(path) and hasattr(os, "startfile"):
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        return path
    if hasattr(os, "startfile"):
        os.startfile(directory)  # Windows
    else:
        subprocess.Popen(["xdg-open", directory])
    return directory


# ── 国网 HDC 帧归属证据（协议11/10 自动识别用，纯函数）──────────
#
# 背景（实测）：TCP 监控「自动识别」原先按 南网→国网新一代→HDC 1.0 顺序试解析，
# 而南网新一代解析器对 HDC 帧只返回 1 行退化结果（「未识别的MSDU类型」）却算
# 「成功」→ 先行接管。TMI 真实日志 748 个 ED 帧（DT=0/1/2/3 四类齐全）与
# 合成 MAC 帧全部被误判为南网新一代。

def _strip_wrapper_common_header(frame: bytes, wrapper: str) -> bytes:
    """剥掉 ED 包装头(6B) + 数据域公共头（gx=8B / plc2=9B），返回业务帧字节。"""
    hdr = 8 if wrapper == "gx" else 9
    frame_len = frame[1] | (frame[2] << 8)
    return frame[6:6 + frame_len - 4][hdr:]


def _ed_frame_business_candidates(frame: bytes):
    """ED..EE 帧 → 两种公共头读法下的 ``(wrapper, 业务字节)``；帧不合法则空。

    公共头有 gx(8B)/plc2(9B) 两种，布局判别可能出错，故两种读法都要给出，
    由调用方用**自证判据**挑选（见 :func:`hdc_fc_evidence`）。
    """
    if not frame or frame[0] != 0xED or len(frame) < 16 or frame[5] != 0xEF:
        return
    frame_len = frame[1] | (frame[2] << 8)
    if frame_len < 4 or frame_len + 4 != len(frame) or frame[-1] != 0xEE:
        return
    for wrapper in ("gx", "plc2"):
        yield wrapper, _strip_wrapper_common_header(frame, wrapper)


def hdc_fc_evidence(frame: bytes) -> bool:
    """ED 包装帧是否为国网 HDC 1.0 的 **MPDU 帧控制**（信标/SOF/SACK/网间协调）。

    判据为 ``hdc10_parser.looks_like_hdc_fc``：定界符 0~3 + 网络类型=0 +
    标准版本号=0 + FCCS(CRC-24) 校验通过。这是**互斥证据**：

      - 南网新一代 FC 的「网络类型」域（bit3~7）含接入指示位，恒 ≥1 → 被排除；
      - 协议10 的 HDC 2.0 标准版本号 ≠0 → 被排除；
      - 误判概率 1/2^24。

    为什么只用这一条判据（而不用「像 HDC MAC 帧」这类结构启发式）：ED 包装布局
    判别本身可能出错，错位 1 字节的垃圾业务帧**恰好能通过** HDC MAC 的结构检查
    （版本=0、MSDU 长度自洽）——实测南网新一代帧因此被误重排到 HDC 1.0，且真实
    HDC 帧的第二字节 0x3A 也会反过来撞上「南网 MPDU」特征。只有 CRC 自证的读法
    才同时排除这两种误判。

    gx 与 plc2 两种读法都试，任一自证即命中。
    """
    try:
        from hdc10_parser import looks_like_hdc_fc
    except Exception:
        return False
    for _wrapper, business in _ed_frame_business_candidates(frame):
        try:
            if looks_like_hdc_fc(business):
                return True
        except Exception:
            continue
    return False


def evidenced_ed_wrapper(frame: bytes, protocol_index=None) -> str:
    """ED 包装布局判别：协议10/11 用**权威 FCCS 证据**，其余沿用原打分实现。

    为什么不能只用 ``batch_core.resolve_ed_wrapper``：它的协议10/11 打分基于
    「HDC MAC 版本号」启发式（首字节低 4 位 ∈{0,1} 加 2 分），对 DT∈{2,3}
    （SACK / 网间协调）的 16 字节 FC 帧，一旦 NID 最低字节低 4 位 ∈{0,1}，
    错位一字节的 plc2 结果反而得分更高（穷举 NID 最低字节实测误判 32/256），
    业务帧整体错位 1 字节后 DT 判据失效，被降级成「应用层报文」垃圾解析。

    这里改用 ``looks_like_hdc_fc``（CRC-24，互斥证据）试剥 gx/plc2，命中即返回
    （gx 优先，协议10/11 的公共头与 gx 同构为 8 字节）；都不命中再退回原实现。
    """
    from batch_core import resolve_ed_wrapper

    def _fallback():
        return resolve_ed_wrapper(frame, "auto", protocol_index=protocol_index)

    if protocol_index not in (10, 11):
        return _fallback()
    try:
        from hdc10_parser import looks_like_hdc_fc
    except Exception:
        return _fallback()
    for wrapper, business in _ed_frame_business_candidates(frame):
        try:
            if looks_like_hdc_fc(business):
                return wrapper
        except Exception:
            continue
    return _fallback()


# ── 流重组器 ──────────────────────────────────────────────

class FlowBuffer:
    """
    单方向 TCP 字节流缓冲区，负责切出完整应用帧。

    切帧格式：监控器协议封装（ED..EE，PLC2.0 / 国网HDC 等）
      ED + 帧长(2B小端) + 控制域1(1B) + 控制域2(1B) + EF + 数据域 + CS + EE
    帧长 = 数据域长度 + 4

    **保留完整 ED 帧**（不在此处剥公共头）：解析阶段按所选协议
    （南网 PLC2 / 国网新一代 / HDC 1.0）用 batch_core 解包并生成包装头字段。
    公共头布局：PLC2.0=9B / 国网HDC·广西=8B，由 resolve_ed_wrapper 判别。

    切帧策略 ``mode``（1.23.45 起）：

      - ``"ed"``：只切 ED..EE（改动前的旧行为）；
      - ``"raw"``：完全不切，**一个 append（= 一个 TCP segment）= 一个原始载荷帧**；
      - ``"auto"``（默认）：先按 ED..EE 切。某方向只要出现过 ED 帧就固定走 ED 路径
        （行为与 ``"ed"`` 等价，不产生原始帧）；若判定该方向不是 ED 封装，则回退为
        ``"raw"`` 行为，把该方向的载荷按 segment 逐包产出，**不再丢弃字节**。

    为什么需要 raw 回退：非 ED 封装的 TCP 载荷（DLMS / 698.45 / 645 等直接跑在 TCP 上）
    原先被逐字节跳过、`pending_bytes` 归零 —— 界面上既没有帧可点，也就无从解析显示。

    判定规则（避免把普通字节误判成 ED 帧）：
      只有既有**完整定界校验**全部通过（``buf[i]==0xED`` + 帧长 ∈ [4, 4096] +
      ``buf[i+5]==0xEF`` + ``buf[i+total-1]==0xEE``）才算 ED 命中；缓冲区里存在
      「未收全的 ED 候选」时先等收全（跨包 ED 帧），但最多等 ``MAX_WAIT_SEGMENTS``
      个 segment，超限即判定 raw（原始流里偶然出现的 ``ED xx xx`` 会伪装成候选，
      不设上限会让该方向长时间不出行）。raw 方向仍会在每段里检测**完整 ED 帧**，
      命中即升级回 ED 模式（应对「抓包从 ED 连接中途开始」的场景），ED 帧之前的
      字节仍按原始载荷产出，保证同一字节只上报一次。
    """

    SOF = 0xED
    EF = 0xEF
    EE = 0xEE
    MAX_FRAME_LEN = 4096
    # 存在「未收全的 ED 候选」时最多等几个 segment 再判定 raw。
    # 实测 ED 帧（现场形态 ~168B）远小于一个 MSS(1460)，跨包最多跨 2 段；
    # 而原始流里偶然出现的 `ED xx xx` 也会被当成候选 —— 若无上限，该方向要攒到
    # 4KB 才回退，界面会长时间不出行。上限 2 段同时覆盖两种情形。
    MAX_WAIT_SEGMENTS = 2

    def __init__(self, mode: str = "auto"):
        if mode not in ("auto", "ed", "raw"):
            raise ValueError(f"未知切帧模式: {mode!r}（应为 auto/ed/raw）")
        self._mode = mode
        self._buf = bytearray()
        self._frames: List[Tuple[float, bytes]] = []  # (时间戳, 完整帧字节)
        # 方向判定结果：None=未定 / "ed"=ED 封装 / "raw"=原始载荷
        self._decided: Optional[str] = "raw" if mode == "raw" else None
        # 每个 append 在缓冲中的起点与时间戳，用于 raw 回退时按 segment 逐包产出
        self._seg_marks: List[Tuple[int, float]] = []
        # 已连续等待的 segment 数（ED 候选未收全）
        self._wait_segments = 0

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def decided(self) -> Optional[str]:
        """该方向的切帧判定结果（auto 模式下才会从 None 变为 ed/raw）。"""
        return self._decided

    def append(self, data: bytes, timestamp: float):
        """追加数据并尝试切帧"""
        if not data:
            # 空载荷（纯 ACK）：不产帧、不建 segment 标记
            return
        if self._decided == "raw":
            self._append_in_raw_mode(data, timestamp)
            return
        self._seg_marks.append((len(self._buf), timestamp))
        self._buf.extend(data)
        self._deframe(timestamp)

    def _append_in_raw_mode(self, data: bytes, timestamp: float):
        """原始载荷方向：一个 segment 一帧；若本段出现**完整 ED 帧**则升级回 ED 模式。

        为什么允许升级：抓包可能从一条 ED 连接的中途开始（首个载荷段只是某帧的尾巴），
        若判定 raw 后永不回头，该方向此后所有 ED 帧都不再被切分 —— 相对改动前是功能回退。
        升级时把 ED 帧之前的字节仍按原始载荷产出，保证同一字节只被上报一次。
        """
        if self.SOF in data:
            hits, _consumed, _waiting = self._scan_ed_bytes(data, timestamp)
            if hits:
                first_off = hits[0][0]
                if first_off > 0:
                    self._frames.append((timestamp, bytes(data[:first_off])))
                # 升级为 ED 模式：从 ED 帧起点起交给常规切帧路径处理
                self._decided = "ed"
                self._buf = bytearray(data[first_off:])
                self._seg_marks = [(0, timestamp)]
                self._deframe(timestamp)
                return
        self._frames.append((timestamp, bytes(data)))

    def _scan_ed_bytes(self, buf, timestamp: float):
        """扫描给定字节序列里的完整 ED..EE 帧。

        返回 ``(hits, consumed, waiting)``：
          - ``hits``：``[(帧起始偏移, (时间戳, 帧字节)), ...]``；
          - ``consumed``：可安全丢弃的前缀长度（非 ED 字节 + 已产出帧）；
          - ``waiting``：存在**未收全**的 ED 候选（需等后续字节）。
        """
        hits = []
        i = 0
        n = len(buf)
        waiting = False
        while i < n:
            if buf[i] != self.SOF:
                i += 1
                continue
            # 至少 6 字节头：ED + 帧长(2) + ctrl1 + ctrl2 + EF
            if i + 6 > n:
                waiting = True
                break
            frame_len = buf[i + 1] | (buf[i + 2] << 8)
            if frame_len < 4 or frame_len > self.MAX_FRAME_LEN:
                i += 1
                continue
            # 总长度 = ED(1) + 帧长字段(2) + [ctrl1+ctrl2+EF+数据域+CS = frame_len] + EE(1)
            total = frame_len + 4
            if i + total > n:
                waiting = True
                break
            # 强定界校验
            if buf[i + 5] != self.EF or buf[i + total - 1] != self.EE:
                i += 1
                continue
            # 保留完整 ED 帧（含包装头），供协议相关解析/文案使用
            hits.append((i, (timestamp, bytes(buf[i:i + total]))))
            i += total
            continue
        return hits, i, waiting

    def _deframe(self, timestamp: float):
        """从缓冲区切出完整帧（业务解析在 _parse_and_summarize）"""
        hits, consumed, waiting = self._scan_ed_bytes(self._buf, timestamp)

        if hits:
            # ED 命中：丢弃非 ED 前缀（与改动前一致），该方向固定为 ED 封装
            if consumed:
                del self._buf[:consumed]
                self._drop_seg_marks(consumed)
            self._decided = "ed"
            self._wait_segments = 0
            self._seg_marks.clear()
            self._frames.extend(frame for _off, frame in hits)
            return

        if self._mode == "ed" or self._decided == "ed":
            # 旧行为：只丢弃已扫过的非 ED 字节，继续等后续字节（ED 方向不设等待上限）
            if consumed:
                del self._buf[:consumed]
                self._drop_seg_marks(consumed)
            return

        if waiting and len(self._buf) <= self.MAX_FRAME_LEN + 4:
            # 可能是跨包的 ED 帧（或长度可疑的候选），先等收全
            self._wait_segments += 1
            if self._wait_segments <= self.MAX_WAIT_SEGMENTS:
                return

        # 判定：该方向不是 ED 封装 → 原始载荷模式，按 segment 补发已缓冲字节
        self._decided = "raw"
        self._wait_segments = 0
        self._emit_raw_frames()
        self._buf.clear()
        self._seg_marks.clear()

    def _drop_seg_marks(self, consumed: int):
        """缓冲区前缀被丢弃后，同步收缩 segment 标记。"""
        if consumed <= 0:
            return
        self._seg_marks = [
            (off - consumed, ts) for off, ts in self._seg_marks if off >= consumed
        ]

    def _emit_raw_frames(self):
        """按 segment 边界把缓冲区内容产出为原始载荷帧（一个 append = 一帧）。"""
        if not self._buf:
            self._seg_marks.clear()
            return
        marks = sorted(self._seg_marks) or [(0, 0.0)]
        for idx, (off, ts) in enumerate(marks):
            end = marks[idx + 1][0] if idx + 1 < len(marks) else len(self._buf)
            if end > off:
                self._frames.append((ts, bytes(self._buf[off:end])))

    def pop_frames(self) -> List[Tuple[float, bytes]]:
        """取出所有已切分的帧并清空"""
        frames = self._frames
        self._frames = []
        return frames

    @property
    def pending_bytes(self) -> int:
        return len(self._buf)

class TCPFlow:
    """一条 TCP 流（双向）"""

    def __init__(self, flow_id: int, src_ip: str, src_port: int, dst_ip: str, dst_port: int):
        self.flow_id = flow_id
        self.endpoint_a = (src_ip, src_port)
        self.endpoint_b = (dst_ip, dst_port)
        self.packet_count = 0
        self.byte_count = 0
        self.last_seen = 0.0
        # 两个方向的缓冲区
        self._a_to_b = FlowBuffer()
        self._b_to_a = FlowBuffer()
        # 已切出的帧：(时间戳, 方向(0=a→b/1=b→a), 帧数据)
        self._frames: List[Tuple[float, int, bytes]] = []
        # 原始 TCP segment：(时间戳, 方向, payload bytes)
        self._segments: List[Tuple[float, int, bytes]] = []
        self._new_segment_count = 0  # 自上次取出后的新增段数

    def add_packet(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int,
                   payload: bytes, timestamp: float):
        self.packet_count += 1
        self.byte_count += len(payload)
        self.last_seen = timestamp

        if (src_ip, src_port) == self.endpoint_a and (dst_ip, dst_port) == self.endpoint_b:
            direction = 0
            buf = self._a_to_b
        else:
            direction = 1
            buf = self._b_to_a

        # 存原始 segment
        self._segments.append((timestamp, direction, payload))
        self._new_segment_count += 1

        if payload:
            buf.append(payload, timestamp)
            new_frames = buf.pop_frames()
            for ts, frame in new_frames:
                self._frames.append((ts, direction, frame))

    @property
    def segments(self) -> List[Tuple[float, int, bytes]]:
        """所有原始 TCP segment"""
        return self._segments

    @property
    def new_segment_count(self) -> int:
        return self._new_segment_count

    def reset_new_segment_count(self):
        self._new_segment_count = 0

    def pop_new_frames(self) -> List[Tuple[float, int, bytes]]:
        """取出新帧并清空"""
        frames = self._frames
        self._frames = []
        return frames

    @property
    def total_frames(self) -> int:
        return len(self._frames)

    @property
    def display_key(self) -> str:
        a = f"{self.endpoint_a[0]}:{self.endpoint_a[1]}"
        b = f"{self.endpoint_b[0]}:{self.endpoint_b[1]}"
        return f"{a} ↔ {b}"


class TCPFlowReassembler:
    """TCP 流重组管理器"""

    def __init__(self):
        self._flows: Dict[Tuple, TCPFlow] = {}
        self._flow_list: List[TCPFlow] = []  # 按加入顺序
        self._next_id = 1
        self._new_flows: List[TCPFlow] = []  # 自上次取出后的新流
        self._updated_flow_ids: set = set()  # 自上次取出后有更新的流

    def _normalize_key(self, ip1: str, port1: int, ip2: str, port2: int) -> Tuple:
        """流 key 归一化（按 IP:Port 排序，双向同一条流）"""
        a = (ip1, port1)
        b = (ip2, port2)
        if a > b:
            a, b = b, a
        return (a[0], a[1], b[0], b[1])

    def process_packet(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int,
                       payload: bytes, timestamp: float):
        key = self._normalize_key(src_ip, src_port, dst_ip, dst_port)
        flow = self._flows.get(key)
        if flow is None:
            flow = TCPFlow(self._next_id, key[0], key[1], key[2], key[3])
            self._flows[key] = flow
            self._flow_list.append(flow)
            self._new_flows.append(flow)
            self._next_id += 1

        flow.add_packet(src_ip, src_port, dst_ip, dst_port, payload, timestamp)
        self._updated_flow_ids.add(flow.flow_id)

    def pop_new_flows(self) -> List[TCPFlow]:
        """取出新增流"""
        flows = self._new_flows
        self._new_flows = []
        return flows

    def pop_updated_ids(self) -> set:
        """取出有更新的流 ID 集合"""
        ids = self._updated_flow_ids
        self._updated_flow_ids = set()
        return ids

    def get_flow(self, flow_id: int) -> Optional[TCPFlow]:
        """按 ID 取流"""
        for f in self._flow_list:
            if f.flow_id == flow_id:
                return f
        return None

    @property
    def all_flows(self) -> List[TCPFlow]:
        return list(self._flow_list)

    def clear(self):
        self._flows.clear()
        self._flow_list.clear()
        self._new_flows.clear()
        self._updated_flow_ids.clear()
        self._next_id = 1


# ── 抓包线程 ──────────────────────────────────────────────

class PacketSniffer(QThread):
    """scapy 抓包线程"""

    packet_received = Signal(str, int, str, int, bytes, float)  # src_ip, src_port, dst_ip, dst_port, payload, timestamp
    error_occurred = Signal(str)

    def __init__(self, iface: str, bpf_filter: str = ""):
        super().__init__()
        thread_registry.track(self, "PacketSniffer")
        self._iface = iface
        self._bpf = bpf_filter
        self._running = False

    def run(self):
        if not SCAPY_AVAILABLE:
            self.error_occurred.emit("scapy 未安装，请先 pip install scapy")
            return

        self._running = True
        try:
            if not _load_scapy():
                self.error_occurred.emit("scapy 加载失败")
                return
            # 用 timeout=1 循环抓包，确保 stop() 能在 1 秒内响应
            # 直接 stop_filter 在无流量时会一直阻塞
            while self._running:
                sniff(
                    iface=self._iface if self._iface else None,
                    filter=self._bpf if self._bpf else None,
                    prn=self._handle_packet,
                    store=False,
                    timeout=1,
                )
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _handle_packet(self, pkt):
        if not self._running:
            return
        if IP not in pkt or TCP not in pkt:
            return
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        ts = float(pkt.time)
        self.packet_received.emit(
            ip.src, tcp.sport, ip.dst, tcp.dport, payload, ts
        )

    def stop(self):
        self._running = False


class IfaceListWorker(QThread):
    """后台枚举网卡列表（scapy 导入 + get_if_list 均耗时数秒，禁止主线程执行）"""

    result_ready = Signal(list)  # [(显示名, iface)]
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        thread_registry.track(self, "IfaceListWorker")

    def run(self):
        try:
            if not _load_scapy():
                self.failed.emit("scapy 未安装，请先 pip install scapy")
                return
            items = []
            for iface in get_if_list():
                try:
                    addr = get_if_addr(iface)
                except Exception:
                    addr = ""
                display = f"{iface}" + (f" ({addr})" if addr else "")
                items.append((display, iface))
            self.result_ready.emit(items)
        except Exception as e:
            self.failed.emit(str(e))


# ── 主 Widget ────────────────────────────────────────────

class TCPMonitorWidget(QWidget):
    """TCP 流量监控器主控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gw_parser = None
        self._csg_parser = None
        self._hdc10_parser = None
        self._sniffer: Optional[PacketSniffer] = None
        self._reassembler = TCPFlowReassembler()
        self._current_flow_id: Optional[int] = None
        self._flow_rows: Dict[int, int] = {}  # flow_id -> 表格行号
        self._frame_cache: List[dict] = []  # 当前流的所有帧：{ts, direction, frame, protocol, summary, parsed}
        self._auto_scroll = True  # 应用层帧列表自动滚动
        self._gw_summary_fn = None
        self._csg_summary_fn = None
        self._hdc10_summary_fn = None
        # CSV 实时记录
        self._csv_file = None
        self._csv_writer = None
        self._csv_path = ""
        self._csv_count = 0
        # 记录位置配置（目录可配 + 一键打开；读写见模块级 load/save_record_config）
        self._record_cfg = load_record_config()
        self._record_dir_cfg = str(self._record_cfg.get("record_dir") or "")
        # 已加载的历史记录流数据 {flow_id: {frames, ...}}
        self._loaded_flows = None

        self._build_ui()
        self._iface_worker = None
        self._refresh_interfaces()

        # UI 节流定时器（100ms 批量刷新）
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._flush_ui_updates)
        self._pending_flow_updates = False

    def set_parsers(
        self,
        gw_parser,
        csg_parser,
        gw_summary_fn=None,
        csg_summary_fn=None,
        hdc10_parser=None,
        hdc10_summary_fn=None,
    ):
        """注入协议解析器和摘要生成函数（国网新一代 / 南网新一代 / HDC 1.0）"""
        self._gw_parser = gw_parser
        self._csg_parser = csg_parser
        self._hdc10_parser = hdc10_parser
        self._gw_summary_fn = gw_summary_fn
        self._csg_summary_fn = csg_summary_fn
        self._hdc10_summary_fn = hdc10_summary_fn or gw_summary_fn

    # ── UI 构建 ────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        toolbar.addWidget(QLabel("网卡："))
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(200)
        toolbar.addWidget(self.iface_combo)

        refresh_btn = QPushButton("刷新")
        set_btn(refresh_btn, "secondary")
        set_btn_icon(refresh_btn, "refresh")
        refresh_btn.clicked.connect(self._refresh_interfaces)
        toolbar.addWidget(refresh_btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("过滤："))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("BPF 过滤，如 tcp port 8080 或 host 192.168.1.1")
        self.filter_edit.setToolTip(
            "BPF 过滤语法示例：\n"
            "  tcp port 8080              — 单个端口\n"
            "  host 192.168.1.100        — 单个IP\n"
            "  src host 192.168.1.100    — 源IP\n"
            "  dst host 192.168.1.1      — 目的IP\n"
            "  tcp port 8080 or tcp port 9090  — 多个端口\n"
            "  tcp portrange 8080-8090   — 端口范围\n"
            "  host 192.168.1.100 and tcp port 8080  — IP+端口组合\n"
            "\n"
            "留空 = 抓取所有 TCP 流量"
        )
        toolbar.addWidget(self.filter_edit, 1)

        self.start_btn = QPushButton("开始抓包")
        set_btn(self.start_btn, "success")
        set_btn_icon(self.start_btn, "play")
        self.start_btn.clicked.connect(self._toggle_capture)
        toolbar.addWidget(self.start_btn)

        clear_btn = QPushButton("清空")
        set_btn(clear_btn, "secondary")
        set_btn_icon(clear_btn, "clear")
        clear_btn.clicked.connect(self._clear_all)
        toolbar.addWidget(clear_btn)

        self.pause_btn = QPushButton("暂停刷新")
        set_btn(self.pause_btn, "secondary")
        set_btn_icon(self.pause_btn, "pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self._toggle_pause)
        toolbar.addWidget(self.pause_btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("协议："))
        self.proto_combo = QComboBox()
        # itemData = 协议索引（None = 自动识别）。用 itemData 而不是位置索引，
        # 这样扩展协议列表时解析分派逻辑无需再改。
        # 顺序：自动识别 → 原始载荷常用协议（注册表短名为单一来源）→ ED 三协议
        #（后三者名称保持既有文案，既有测试用 findText 定位）
        import protocol_registry as _pr

        self.proto_combo.addItem("自动识别", None)
        for _pindex in (0, 4, 5, 6, 7, 8):
            self.proto_combo.addItem(_pr.get_protocol(_pindex).short_name, _pindex)
        for _label, _pindex in (
            ("国网新一代", 10),
            ("南网新一代", 9),
            ("HDC 1.0", 11),
        ):
            self.proto_combo.addItem(_label, _pindex)
        self.proto_combo.setToolTip(
            "原始载荷按所选协议解析（显式选择优先）：\n"
            "  自动识别 → 只对**可自证**的形态判定（DLMS Wrapper / DLMS-APDU /\n"
            "            DLT645-2007 / 698.45）；南网 / 国网 需显式选择\n"
            "  其余项 → 只按该协议解析，不匹配时按「原始数据」显示\n"
            "ED..EE 监控封装帧不受影响：按封装语义解析（国网新一代 / 南网新一代 / HDC 1.0）"
        )
        self.proto_combo.currentIndexChanged.connect(self._reparse_current_flow)
        toolbar.addWidget(self.proto_combo)

        # 过滤（R8）：只影响显示，不清缓存
        self.unrecognized_only_cb = QCheckBox("仅未识别")
        self.unrecognized_only_cb.setToolTip("只显示未识别出具体协议的帧（协议列为「原始数据」等）")
        self.unrecognized_only_cb.toggled.connect(self._apply_frame_filter)
        toolbar.addWidget(self.unrecognized_only_cb)

        self.proto_filter_combo = QComboBox()
        self.proto_filter_combo.addItem("全部协议", None)
        self.proto_filter_combo.addItem("原始数据", "原始数据")
        for _pindex in (0, 4, 5, 6, 7, 8, 9, 10, 11):
            _spec = _pr.get_protocol(_pindex)
            self.proto_filter_combo.addItem(_spec.short_name, _spec.short_name)
        self.proto_filter_combo.currentIndexChanged.connect(self._apply_frame_filter)
        toolbar.addWidget(self.proto_filter_combo)

        toolbar.addStretch()

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.status_label)

        layout.addLayout(toolbar)

        # 主分割：上 = 流列表，下 = 帧列表 + 解析详情
        main_splitter = QSplitter(Qt.Vertical)

        # 上：TCP 流列表
        flow_group = QGroupBox("TCP 流列表")
        flow_layout = QVBoxLayout(flow_group)
        flow_layout.setContentsMargins(6, 8, 6, 6)

        self.flow_table = ZoomableTableWidget()
        self.flow_table.setColumnCount(6)
        self.flow_table.setHorizontalHeaderLabels(
            ["流ID", "源地址", "目的地址", "包数", "字节数", "最新时间"]
        )
        self.flow_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.flow_table.setSelectionMode(QTableWidget.SingleSelection)
        self.flow_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.flow_table.setAlternatingRowColors(True)
        self.flow_table.verticalHeader().hide()
        hdr = self.flow_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        self.flow_table.setColumnWidth(0, 50)
        self.flow_table.setColumnWidth(3, 60)
        self.flow_table.setColumnWidth(4, 80)
        self.flow_table.setColumnWidth(5, 140)
        f = QFont()
        f.setPointSize(8)
        self.flow_table.setFont(f)
        self.flow_table.verticalHeader().setDefaultSectionSize(20)
        self.flow_table.cellClicked.connect(self._on_flow_selected)
        self._setup_table_copy_menu(self.flow_table)
        flow_layout.addWidget(self.flow_table)

        main_splitter.addWidget(flow_group)

        # 下：帧列表 + 解析详情
        detail_splitter = QSplitter(Qt.Horizontal)

        # 左下：应用层帧列表
        frame_group = QGroupBox("应用层帧")
        frame_layout = QVBoxLayout(frame_group)
        frame_layout.setContentsMargins(6, 8, 6, 6)
        frame_layout.setSpacing(4)

        # 帧列表顶部工具栏：记录/加载/自动滚动
        frame_toolbar = QHBoxLayout()
        frame_toolbar.setSpacing(6)
        self.csv_record_btn = QPushButton("开始记录")
        self.csv_record_btn.setCheckable(True)
        set_btn(self.csv_record_btn, "success")
        set_btn_icon(self.csv_record_btn, "save")
        self.csv_record_btn.toggled.connect(self._on_csv_record_toggled)
        frame_toolbar.addWidget(self.csv_record_btn)

        load_btn = QPushButton("加载记录")
        set_btn(load_btn, "secondary")
        set_btn_icon(load_btn, "open_file")
        load_btn.clicked.connect(self._load_csv_recording)
        frame_toolbar.addWidget(load_btn)

        # 记录位置：一键打开（定位文件）+ 目录可配（现场：记录下来的 CSV 找不到）
        self.open_record_btn = QPushButton("打开位置")
        set_btn(self.open_record_btn, "secondary")
        set_btn_icon(self.open_record_btn, "open")
        self.open_record_btn.clicked.connect(self._open_record_location)
        frame_toolbar.addWidget(self.open_record_btn)

        self.record_dir_btn = QPushButton("记录目录")
        set_btn(self.record_dir_btn, "secondary")
        set_btn_icon(self.record_dir_btn, "folder")
        dir_menu = QMenu(self.record_dir_btn)
        dir_menu.addAction("选择记录目录…", self._choose_record_dir)
        dir_menu.addAction("打开记录目录", self._open_record_location)
        dir_menu.addAction("恢复默认目录", self._reset_record_dir)
        self.record_dir_btn.setMenu(dir_menu)
        frame_toolbar.addWidget(self.record_dir_btn)

        # 宽度：4 个按钮都是「16px 图标 + 4 个汉字」，**不得写死宽度**——实测 QSS 下
        # sizeHint 已需 92px（带菜单下拉箭头的「记录目录」104px），字号调大后更多
        # （12 号 104/116、14 号 116/128）。原先写死的 80px 在**默认字号**就裁字。
        # 统一取下限（minimumWidth）而非固定宽度，切主题/改字号后无需重算。
        fit_btn_width(self.csv_record_btn, load_btn,
                      self.open_record_btn, self.record_dir_btn)

        self.csv_status_label = QLabel("未记录")
        self.csv_status_label.setStyleSheet("color: #888; font-size: 11px;")
        frame_toolbar.addWidget(self.csv_status_label)
        self._update_record_dir_hint()

        frame_toolbar.addStretch()
        self.frame_autoscroll_cb = QCheckBox("自动滚动")
        self.frame_autoscroll_cb.setChecked(True)
        self.frame_autoscroll_cb.toggled.connect(self._toggle_frame_autoscroll)
        frame_toolbar.addWidget(self.frame_autoscroll_cb)
        frame_layout.addLayout(frame_toolbar)

        self.frame_table = ZoomableTableWidget()
        self.frame_table.setColumnCount(6)
        # 列序固定为：时间/方向/源→目的/长度/协议/摘要（R6；改动列序需同步
        # _refresh_frame_list、_reparse_current_flow、_apply_frame_filter 与 CSV 往返测试）
        self.frame_table.setHorizontalHeaderLabels(
            ["时间", "方向", "源 → 目的", "长度", "协议", "摘要"]
        )
        self.frame_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.frame_table.setSelectionMode(QTableWidget.SingleSelection)
        self.frame_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.frame_table.setAlternatingRowColors(True)
        self.frame_table.verticalHeader().hide()
        fhdr = self.frame_table.horizontalHeader()
        fhdr.setSectionResizeMode(0, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(1, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(2, QHeaderView.Interactive)
        fhdr.setSectionResizeMode(3, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(4, QHeaderView.Fixed)
        fhdr.setSectionResizeMode(5, QHeaderView.Stretch)
        self.frame_table.setColumnWidth(0, 100)
        self.frame_table.setColumnWidth(1, 50)
        self.frame_table.setColumnWidth(2, 240)
        self.frame_table.setColumnWidth(3, 55)
        self.frame_table.setColumnWidth(4, 90)
        self.frame_table.setFont(f)
        self.frame_table.verticalHeader().setDefaultSectionSize(20)
        self.frame_table.cellClicked.connect(self._on_frame_selected)
        self._setup_table_copy_menu(self.frame_table)
        frame_layout.addWidget(self.frame_table)

        detail_splitter.addWidget(frame_group)

        # 右下：TabWidget — 原始报文 / 解析结果
        self.detail_tabs = QTabWidget()

        # --- Tab 1: 原始 TCP 报文 ---
        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        raw_layout.setContentsMargins(4, 4, 4, 4)
        raw_layout.setSpacing(4)

        self.segment_table = ZoomableTableWidget()
        self.segment_table.setColumnCount(3)
        self.segment_table.setHorizontalHeaderLabels(["时间", "方向", "长度"])
        self.segment_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.segment_table.setSelectionMode(QTableWidget.SingleSelection)
        self.segment_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.segment_table.setAlternatingRowColors(True)
        self.segment_table.verticalHeader().hide()
        shdr = self.segment_table.horizontalHeader()
        shdr.setSectionResizeMode(0, QHeaderView.Fixed)
        shdr.setSectionResizeMode(1, QHeaderView.Fixed)
        shdr.setSectionResizeMode(2, QHeaderView.Stretch)
        self.segment_table.setColumnWidth(0, 100)
        self.segment_table.setColumnWidth(1, 50)
        self.segment_table.setFont(f)
        self.segment_table.verticalHeader().setDefaultSectionSize(20)
        self.segment_table.cellClicked.connect(self._on_segment_selected)
        self._setup_table_copy_menu(self.segment_table)
        raw_layout.addWidget(self.segment_table, 1)

        # 字节视图（偏移 + 16 进制 + ASCII，支持按字段高亮）。保留旧属性名
        # segment_hex 以免既有引用断裂（R4）
        self.segment_hex = HexDumpView(max_height=120)
        raw_layout.addWidget(self.segment_hex)

        self.detail_tabs.addTab(raw_tab, "原始报文")

        # --- Tab 2: 解析结果 ---
        parse_tab = QWidget()
        parse_layout = QVBoxLayout(parse_tab)
        parse_layout.setContentsMargins(4, 4, 4, 4)
        parse_layout.setSpacing(4)

        # 视图切换行：表 / 字段树（与主窗口 result_view_combo 语义一致，R5）
        parse_toolbar = QHBoxLayout()
        parse_toolbar.setSpacing(6)
        parse_toolbar.addWidget(QLabel("视图："))
        self.parse_view_combo = QComboBox()
        self.parse_view_combo.addItem("表", "table")
        self.parse_view_combo.addItem("字段树", "tree")
        self.parse_view_combo.setToolTip(
            "解析结果的展示方式：\n"
            "  表 —— 字段 / 原始值 / 解析值 / 说明 四列\n"
            "  字段树 —— Wireshark 风格层级字段（与主窗口一致），叶子显示解析值"
        )
        self.parse_view_combo.currentIndexChanged.connect(self._on_parse_view_changed)
        parse_toolbar.addWidget(self.parse_view_combo)
        parse_toolbar.addStretch()
        parse_layout.addLayout(parse_toolbar)

        self.frame_byte_view = HexDumpView(max_height=60)
        parse_layout.addWidget(self.frame_byte_view)
        # 旧属性名保留（原 parse_hex 为帧字节预览）
        self.parse_hex = self.frame_byte_view

        self.parse_tree = QTreeWidget()
        self.parse_tree.setColumnCount(2)
        self.parse_tree.setHeaderLabels(["字段", "值"])
        self.parse_tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.parse_tree.setAlternatingRowColors(True)
        self.parse_tree.setFont(f)
        self.parse_tree.setVisible(False)
        parse_layout.addWidget(self.parse_tree, 1)

        self.parse_table = ZoomableTableWidget()
        self.parse_table.setColumnCount(4)
        self.parse_table.setHorizontalHeaderLabels(
            ["字段", "原始值", "解析值", "说明"]
        )
        phdr = self.parse_table.horizontalHeader()
        phdr.setStretchLastSection(True)
        phdr.setSectionResizeMode(QHeaderView.Interactive)
        self.parse_table.setColumnWidth(0, 140)
        self.parse_table.setColumnWidth(1, 100)
        self.parse_table.setColumnWidth(2, 120)
        self.parse_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.parse_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.parse_table.setAlternatingRowColors(True)
        self.parse_table.verticalHeader().hide()
        self.parse_table.setFont(f)
        self.parse_table.verticalHeader().setDefaultSectionSize(18)
        self._setup_table_copy_menu(self.parse_table)
        self.parse_table.currentCellChanged.connect(self._on_parse_row_selected)
        self.parse_tree.itemSelectionChanged.connect(self._on_parse_tree_selected)
        parse_layout.addWidget(self.parse_table, 1)

        self.detail_tabs.addTab(parse_tab, "解析结果")

        detail_splitter.addWidget(self.detail_tabs)
        detail_splitter.setSizes([350, 450])

        main_splitter.addWidget(detail_splitter)
        main_splitter.setSizes([180, 400])

        layout.addWidget(main_splitter, 1)

        if not SCAPY_AVAILABLE:
            self.status_label.setText("scapy 未安装，无法抓包")
            self.status_label.setStyleSheet("color: #f44336;")
            self.start_btn.setEnabled(False)

    # ── 网卡管理 ──────────────────────────────────────

    def _refresh_interfaces(self):
        """刷新网卡列表（后台线程执行，避免阻塞 GUI）"""
        self.iface_combo.clear()
        if not SCAPY_AVAILABLE:
            return
        if self._iface_worker is not None and self._iface_worker.isRunning():
            return
        self.status_label.setText("正在加载网卡列表…")
        self.status_label.setStyleSheet("color: #888;")
        self.start_btn.setEnabled(False)
        self._iface_worker = IfaceListWorker()
        self._iface_worker.result_ready.connect(self._on_ifaces_loaded)
        self._iface_worker.failed.connect(self._on_ifaces_failed)
        self._iface_worker.start()

    def _on_ifaces_loaded(self, items):
        self.iface_combo.clear()
        for display, iface in items:
            self.iface_combo.addItem(display, iface)
        if items:
            self.status_label.setText("就绪")
            self.status_label.setStyleSheet("color: #888;")
            self.start_btn.setEnabled(True)
        else:
            self.status_label.setText("未找到可用网卡")
            self.status_label.setStyleSheet("color: #f44336;")
            self.start_btn.setEnabled(False)

    def _on_ifaces_failed(self, msg):
        self.status_label.setText(f"获取网卡失败: {msg}")
        self.status_label.setStyleSheet("color: #f44336;")
        self.start_btn.setEnabled(False)

    # ── 抓包控制 ──────────────────────────────────────

    def _toggle_capture(self):
        if self._sniffer and self._sniffer.isRunning():
            self._stop_capture()
        else:
            self._start_capture()

    def _start_capture(self):
        if not SCAPY_AVAILABLE:
            QMessageBox.warning(self, "提示", "scapy 未安装，无法抓包。\n请运行: pip install scapy")
            return

        iface_data = self.iface_combo.currentData()
        if not iface_data:
            QMessageBox.warning(self, "提示", "请选择网卡")
            return

        bpf_filter = self.filter_edit.text().strip()
        if bpf_filter:
            # 确保只抓 TCP（用户输入已有 tcp 开头就不加）
            if not bpf_filter.lower().startswith("tcp"):
                bpf_filter = f"tcp and ({bpf_filter})"
        else:
            bpf_filter = "tcp"

        self._sniffer = PacketSniffer(iface_data, bpf_filter)
        self._sniffer.packet_received.connect(self._on_packet_received)
        self._sniffer.error_occurred.connect(self._on_sniffer_error)
        self._sniffer.finished.connect(self._on_sniffer_finished)
        self._sniffer.start()

        self.start_btn.setText("停止抓包")
        set_btn(self.start_btn, "danger")
        self.iface_combo.setEnabled(False)
        self.filter_edit.setEnabled(False)
        self.status_label.setText("抓包中…")
        self.status_label.setStyleSheet("color: #4CAF50;")
        self._ui_timer.start()

    def _stop_capture(self):
        if self._sniffer:
            self._sniffer.stop()
            self._sniffer.wait(2000)

    # ── 主题 ────────────────────────────────────────────────────────────
    def restyle_for_theme(self, dark: bool) -> None:
        """切深浅主题：字节视图（字符格式里显式设过前后景）跟着换，其余颜色由 QSS 负责。"""
        for view in (getattr(self, "segment_hex", None),
                     getattr(self, "frame_byte_view", None)):
            if view is not None:
                try:
                    view.restyle_for_theme(dark)
                except RuntimeError:
                    pass

    def cleanup(self):
        """关闭时统一回收：停 UI 刷新定时器与抓包线程。"""
        try:
            self._ui_timer.stop()
        except Exception:
            pass
        if self._iface_worker is not None and self._iface_worker.isRunning():
            self._iface_worker.wait(3000)
        self._stop_capture()

    def _on_sniffer_finished(self):
        self.start_btn.setText("开始抓包")
        set_btn(self.start_btn, "success")
        self.iface_combo.setEnabled(True)
        self.filter_edit.setEnabled(True)
        self.status_label.setText(f"已停止（共 {len(self._reassembler.all_flows)} 条流）")
        self.status_label.setStyleSheet("color: #888;")
        self._ui_timer.stop()
        self._flush_ui_updates()  # 最后刷一次

    def _toggle_pause(self):
        """暂停/继续 UI 刷新"""
        if self.pause_btn.isChecked():
            self.pause_btn.setText("继续刷新")
            self._ui_timer.stop()
            self.status_label.setText("已暂停刷新")
        else:
            self.pause_btn.setText("暂停刷新")
            if self._sniffer and self._sniffer.isRunning():
                self._ui_timer.start()
                self.status_label.setText("抓包中…")
            else:
                self.status_label.setText("就绪")

    def _toggle_frame_autoscroll(self, checked: bool):
        """应用层帧列表自动滚动开关"""
        self._auto_scroll = checked

    def _on_sniffer_error(self, msg: str):
        msg_lower = msg.lower()
        if "npcap" in msg_lower or "winpcap" in msg_lower or "no available pcap device" in msg_lower:
            QMessageBox.critical(
                self, "抓包错误",
                f"无法抓包：\n{msg}\n\n"
                "请确认：\n"
                "1. 已安装 npcap（https://npcap.com/）\n"
                "2. 安装时勾选了 \"WinPcap API-compatible Mode\"\n"
                "3. 以管理员权限运行本程序"
            )
        elif "filter" in msg_lower or "syntax" in msg_lower:
            QMessageBox.critical(self, "过滤错误", f"过滤表达式语法错误：\n{msg}")
        else:
            QMessageBox.critical(self, "抓包错误", f"抓包失败：\n{msg}")

    # ── 包处理 ────────────────────────────────────────

    def _on_packet_received(self, src_ip, src_port, dst_ip, dst_port, payload, timestamp):
        """抓包线程发来的包（主线程）"""
        self._reassembler.process_packet(src_ip, src_port, dst_ip, dst_port, payload, timestamp)
        self._pending_flow_updates = True

    def _flush_ui_updates(self):
        """批量刷新 UI（节流）"""
        if not self._pending_flow_updates:
            return
        self._pending_flow_updates = False

        # 新增流
        new_flows = self._reassembler.pop_new_flows()
        for flow in new_flows:
            row = self.flow_table.rowCount()
            self.flow_table.insertRow(row)
            self.flow_table.setItem(row, 0, QTableWidgetItem(str(flow.flow_id)))
            self.flow_table.setItem(row, 1, QTableWidgetItem(f"{flow.endpoint_a[0]}:{flow.endpoint_a[1]}"))
            self.flow_table.setItem(row, 2, QTableWidgetItem(f"{flow.endpoint_b[0]}:{flow.endpoint_b[1]}"))
            self.flow_table.setItem(row, 3, QTableWidgetItem(str(flow.packet_count)))
            self.flow_table.setItem(row, 4, QTableWidgetItem(str(flow.byte_count)))
            self.flow_table.setItem(row, 5, QTableWidgetItem(self._fmt_time(flow.last_seen)))
            self._flow_rows[flow.flow_id] = row

        # 更新流统计
        updated_ids = self._reassembler.pop_updated_ids()
        for fid in updated_ids:
            flow = self._reassembler.get_flow(fid)
            if flow and fid in self._flow_rows:
                row = self._flow_rows[fid]
                self.flow_table.setItem(row, 3, QTableWidgetItem(str(flow.packet_count)))
                self.flow_table.setItem(row, 4, QTableWidgetItem(str(flow.byte_count)))
                self.flow_table.setItem(row, 5, QTableWidgetItem(self._fmt_time(flow.last_seen)))

        # 如果当前关注的流有更新，刷新帧列表和 segment 列表
        if self._current_flow_id is not None and self._current_flow_id in updated_ids:
            self._refresh_frame_list(self._current_flow_id)
            # segment 列表增量追加
            flow = self._reassembler.get_flow(self._current_flow_id)
            if flow and flow.new_segment_count > 0:
                segs = flow.segments
                start_idx = len(segs) - flow.new_segment_count
                for i in range(start_idx, len(segs)):
                    ts, direction, payload = segs[i]
                    row = self.segment_table.rowCount()
                    self.segment_table.insertRow(row)
                    self.segment_table.setItem(row, 0, QTableWidgetItem(self._fmt_time(ts)))
                    dir_text = "→" if direction == 0 else "←"
                    self.segment_table.setItem(row, 1, QTableWidgetItem(dir_text))
                    self.segment_table.setItem(row, 2, QTableWidgetItem(str(len(payload))))
                self.segment_table.scrollToBottom()
                flow.reset_new_segment_count()

    # ── 流/帧选择 ─────────────────────────────────────

    def _on_flow_selected(self, row: int, col: int):
        item = self.flow_table.item(row, 0)
        if not item:
            return
        try:
            flow_id = int(item.text())
        except ValueError:
            return
        self._current_flow_id = flow_id
        # 刷新应用帧列表
        self._frame_cache.clear()
        self.frame_table.setRowCount(0)

        # 加载模式：从 _loaded_flows 读
        if self._loaded_flows and flow_id in self._loaded_flows:
            info = self._loaded_flows[flow_id]
            for frame_info in info["frames"]:
                self._frame_cache.append(frame_info)
                self._fill_frame_row(
                    self.frame_table.rowCount(), frame_info,
                    len(self._frame_cache) - 1,
                )
            # 清空 segment（加载模式无原始 TCP 段）
            self.segment_table.setRowCount(0)
        else:
            # 实时模式
            self._refresh_frame_list(flow_id)
            self._refresh_segment_list(flow_id)

        # 清空解析结果
        self.parse_table.setRowCount(0)
        if hasattr(self, "parse_tree"):
            self.parse_tree.clear()
        self.frame_byte_view.set_bytes(b"")
        self.segment_hex.set_bytes(b"")

    def _refresh_frame_list(self, flow_id: int):
        """刷新当前流的帧列表（增量追加，解析并生成详细摘要）"""
        flow = self._reassembler.get_flow(flow_id)
        if not flow:
            return

        new_frames = flow.pop_new_frames()
        if not new_frames:
            return

        src_addr = f"{flow.endpoint_a[0]}:{flow.endpoint_a[1]}"
        dst_addr = f"{flow.endpoint_b[0]}:{flow.endpoint_b[1]}"

        for ts, direction, frame in new_frames:
            # 解析 + 生成摘要
            proto_name, summary, parsed = self._parse_and_summarize(frame)
            info = {
                "ts": ts,
                "direction": direction,
                "frame": frame,
                "protocol": proto_name,
                "summary": summary,
                "parsed": parsed,
                # 源/目的按方向推导（R6：帧表「源 → 目的」列）
                "src": src_addr if direction == 0 else dst_addr,
                "dst": dst_addr if direction == 0 else src_addr,
            }
            self._frame_cache.append(info)
            # 过滤开启时整表重建（保证行与缓存一致）；否则增量追加（性能优先）
            if self._frame_filter_active():
                self._apply_frame_filter()
            elif self._frame_matches_filter(info):
                self._fill_frame_row(
                    self.frame_table.rowCount(), info, len(self._frame_cache) - 1
                )

            # CSV 记录（全量、所有流、不受过滤影响）
            if self._csv_writer is not None:
                self._write_csv_record(
                    flow_id, ts, direction, info["src"], info["dst"],
                    len(frame), proto_name, summary, frame
                )

        # 自动滚动
        if self._auto_scroll and new_frames:
            self.frame_table.scrollToBottom()

    # ── 帧表行填充 / 过滤（R6 / R8）──────────────────────────────

    @staticmethod
    def _is_recognized_protocol(name) -> bool:
        """协议列是否识别出具体协议（「原始数据」等视为未识别）。"""
        return bool(name) and str(name) not in ("原始数据", "未知", "ED封装", "-")

    def _fill_frame_row(self, row: int, info: dict, cache_index: int = -1):
        """按缓存条目填充一行。

        列序见 `_build_ui`：时间 / 方向 / 源→目的 / 长度 / 协议 / 摘要。
        第 0 列写入 UserRole = 缓存下标，供过滤后仍能正确定位解析结果。
        """
        self.frame_table.insertRow(row)
        ts_item = QTableWidgetItem(
            info.get("time_str") or self._fmt_time(info.get("ts", 0.0))
        )
        ts_item.setData(Qt.ItemDataRole.UserRole, cache_index)
        self.frame_table.setItem(row, 0, ts_item)
        dir_text = "→" if info.get("direction", 0) == 0 else "←"
        self.frame_table.setItem(row, 1, QTableWidgetItem(dir_text))
        self.frame_table.setItem(
            row, 2,
            QTableWidgetItem(f"{info.get('src', '')} → {info.get('dst', '')}"),
        )
        self.frame_table.setItem(
            row, 3, QTableWidgetItem(str(len(info.get("frame", b""))))
        )
        proto_item = QTableWidgetItem(str(info.get("protocol", "")))
        summary_item = QTableWidgetItem(str(info.get("summary", "")))
        if not self._is_recognized_protocol(info.get("protocol", "")):
            # 未识别帧视觉弱化（AC6.2）
            for item in (proto_item, summary_item):
                item.setForeground(QColor("#999999"))
        self.frame_table.setItem(row, 4, proto_item)
        self.frame_table.setItem(row, 5, summary_item)

    def _row_cache_index(self, row: int) -> int:
        """帧表行 → `_frame_cache` 下标（过滤后行号与缓存下标不再一一对应）。"""
        item = self.frame_table.item(row, 0)
        if item is not None:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, int) and not isinstance(data, bool):
                return data
        return row

    def _frame_filter_active(self) -> bool:
        """是否启用了过滤（启用时帧表需按缓存整表重建）。"""
        if not hasattr(self, "unrecognized_only_cb"):
            return False
        return bool(self.unrecognized_only_cb.isChecked()) or (
            self.proto_filter_combo.currentData() is not None
        )

    def _frame_matches_filter(self, info: dict) -> bool:
        if not hasattr(self, "unrecognized_only_cb"):
            return True
        if self.unrecognized_only_cb.isChecked() and self._is_recognized_protocol(
            info.get("protocol", "")
        ):
            return False
        wanted = self.proto_filter_combo.currentData()
        if wanted is not None and str(info.get("protocol", "")) != str(wanted):
            return False
        return True

    def _apply_frame_filter(self):
        """按当前过滤条件重建帧表（只影响显示，`_frame_cache` 保持全量）。"""
        if not hasattr(self, "frame_table"):
            return
        self._rebuild_frame_table()
        if self._auto_scroll and self.frame_table.rowCount():
            self.frame_table.scrollToBottom()


    def _refresh_segment_list(self, flow_id: int):
        """刷新当前流的原始 TCP segment 列表"""
        flow = self._reassembler.get_flow(flow_id)
        if not flow:
            return
        segments = flow.segments
        self.segment_table.setRowCount(len(segments))
        for i, (ts, direction, payload) in enumerate(segments):
            self.segment_table.setItem(i, 0, QTableWidgetItem(self._fmt_time(ts)))
            dir_text = "→" if direction == 0 else "←"
            self.segment_table.setItem(i, 1, QTableWidgetItem(dir_text))
            self.segment_table.setItem(i, 2, QTableWidgetItem(str(len(payload))))
        # 滚动到底部
        if segments:
            self.segment_table.scrollToBottom()

    def _on_segment_selected(self, row: int, col: int):
        """选中原始 TCP segment 时显示字节（Wireshark 风格字节视图）"""
        if self._current_flow_id is None:
            return
        flow = self._reassembler.get_flow(self._current_flow_id)
        if not flow or row < 0 or row >= len(flow.segments):
            return
        _ts, _direction, payload = flow.segments[row]
        self.segment_hex.set_bytes(payload or b"")

    def _on_frame_selected(self, row: int, col: int):
        if row < 0:
            return
        cache_index = self._row_cache_index(row)
        if cache_index < 0 or cache_index >= len(self._frame_cache):
            return
        info = self._frame_cache[cache_index]
        frame = info["frame"]
        # 字节视图（R4）：帧字节 + 清掉上一次的高亮
        self.frame_byte_view.set_bytes(frame)
        # 用缓存的解析结果填充表格/字段树（R5）
        self._fill_parse_table(info.get("parsed") or [])

    def _on_parse_view_changed(self, _index: int = 0):
        """解析结果视图切换：表 / 字段树（R5）"""
        mode = self.parse_view_combo.currentData()
        is_tree = mode == "tree"
        if hasattr(self, "parse_tree"):
            self.parse_tree.setVisible(is_tree)
        self.parse_table.setVisible(not is_tree)

    def _on_parse_row_selected(self, row: int, col: int, prev_row: int = -1, prev_col: int = -1):
        """选中解析行 → 高亮字节视图中对应字节范围（AC4.2）"""
        item = self.parse_table.item(row, 0)
        if item is None:
            return
        start = item.data(Qt.ItemDataRole.UserRole)
        end = item.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(start, int) and isinstance(end, int):
            self.frame_byte_view.highlight_range(start, end)
        else:
            self.frame_byte_view.clear_highlight()

    def _reparse_current_flow(self, _index: int = 0):
        """协议下拉变化 → 重解析当前流已抓帧（R7）。

        只重算协议/摘要/解析结果；帧的数量、顺序与字节内容不变（AC7.2）。
        分批处理（每批 200 帧 + `singleShot(0)` 让出事件循环），避免阻塞 UI（AC7.3）。
        """
        if not self._frame_cache:
            return
        self._reparse_queue = list(range(len(self._frame_cache)))
        self._reparse_step()

    def _reparse_step(self, batch: int = 200):
        """重解析一批；还有剩余则让出事件循环后继续。"""
        queue = list(getattr(self, "_reparse_queue", []))
        if not queue:
            self._refresh_after_reparse()
            return
        for idx in queue[:batch]:
            info = self._frame_cache[idx]
            proto_name, summary, parsed = self._parse_and_summarize(info["frame"])
            info["protocol"] = proto_name
            info["summary"] = summary
            info["parsed"] = parsed
        self._reparse_queue = queue[batch:]
        if self._reparse_queue:
            QTimer.singleShot(0, self._reparse_step)
        else:
            self._refresh_after_reparse()

    def _refresh_after_reparse(self):
        """重解析结束后刷新显示（帧表 + 当前选中帧的解析视图）。"""
        self._rebuild_frame_table()
        row = self.frame_table.currentRow()
        if row >= 0:
            self._on_frame_selected(row, 0)

    def _rebuild_frame_table(self):
        """整表重建（重解析后必须走这里，行→缓存映射随之刷新）。"""
        self.frame_table.setRowCount(0)
        for cache_index, info in enumerate(self._frame_cache):
            if self._frame_matches_filter(info):
                self._fill_frame_row(self.frame_table.rowCount(), info, cache_index)

    def _unwrap_ed_for_parse(
        self, frame: bytes, protocol_index=None
    ) -> Tuple[list, bytes]:
        """ED..EE 帧 → (ed_rows, business)，包装布局判别用**权威 FCCS 证据**。

        与 ``batch_core.unwrap_ed_for_parse`` 同构，仅把布局判别换成
        :func:`evidenced_ed_wrapper`：后者对协议11 的 DT∈{2,3}（SACK/网间协调）
        帧不会被 batch_core 的「HDC MAC 版本号」启发式误判成 plc2（穷举 NID
        最低字节实测误判 32/256），从而避免业务帧整体错位 1 字节、DT 判据失效
        后被降级成「应用层报文」垃圾解析。
        """
        from batch_core import build_ed_header_rows, extract_business_from_ed_frame

        if not frame or frame[0] != 0xED:
            return [], frame
        wrapper = evidenced_ed_wrapper(frame, protocol_index)
        ed_rows = build_ed_header_rows(frame, protocol_index, wrapper)
        business_hex, _dtype = extract_business_from_ed_frame(
            frame.hex(),
            wrapper=wrapper,
            protocol_index=protocol_index if protocol_index is not None else 9,
        )
        if business_hex:
            return ed_rows, bytes.fromhex(business_hex)
        if ed_rows:
            return ed_rows, b""
        return [], frame

    def _parse_and_summarize(self, frame: bytes) -> Tuple[str, str, list]:
        """解析帧并生成摘要，返回 (协议名, 摘要, 解析结果列表)。

        - **合法** ``ED..EE`` 监控封装帧 → :meth:`_parse_ed_frame`（判据与改动前逐字一致）；
        - 其余（原始 TCP 载荷）→ :meth:`_parse_raw_payload`（1.23.45 起）。

        路由判据不能只看首字节：原始载荷恰好以 0xED 开头很常见，若一律进 ED 路径
        会得到「无法识别协议」+ 空表（等于把数据藏起来），与 R3 相悖。
        """
        if self._looks_like_ed_frame(frame):
            return self._parse_ed_frame(frame)
        return self._parse_raw_payload(frame)

    @staticmethod
    def _looks_like_ed_frame(frame: bytes) -> bool:
        """是否为 FlowBuffer 切出的**合法** ED..EE 封装帧（非「首字节恰好 0xED」）。"""
        if len(frame) < 10 or frame[0] != FlowBuffer.SOF or frame[5] != FlowBuffer.EF:
            return False
        frame_len = frame[1] | (frame[2] << 8)
        return (
            4 <= frame_len <= FlowBuffer.MAX_FRAME_LEN
            and frame_len + 4 == len(frame)
            and frame[-1] == FlowBuffer.EE
        )

    def _parse_ed_frame(self, frame: bytes) -> Tuple[str, str, list]:
        """ED..EE 监控封装帧解析（原 ``_parse_and_summarize`` 主体，判据未改）。

        proto_combo: 显式选择 → 只试该协议族；自动识别 → 三族依次尝试
        ED..EE 监控封装：先按协议语义生成包装头字段，再解析业务帧。
        """
        from batch_core import (
            ed_wrapper_display,
            ed_wrapper_summary_name,
        )

        # 显式选择以 itemData 的协议索引为准（10/9/11），None=自动识别
        selected = self._selected_protocol_index()
        # (parser, proto_name, summary_fn, protocol_index_for_ed)
        candidates = []
        if selected == 10 and self._gw_parser:
            candidates = [(self._gw_parser, "国网新一代", self._gw_summary_fn, 10)]
        elif selected == 9 and self._csg_parser:
            candidates = [(self._csg_parser, "南网新一代", self._csg_summary_fn, 9)]
        elif selected == 11 and self._hdc10_parser:
            candidates = [(self._hdc10_parser, "HDC 1.0", self._hdc10_summary_fn, 11)]
        else:
            # 自动识别：南网 → 国网新一代 → HDC 1.0
            if self._csg_parser:
                candidates.append(
                    (self._csg_parser, "南网新一代", self._csg_summary_fn, 9)
                )
            if self._gw_parser:
                candidates.append(
                    (self._gw_parser, "国网新一代", self._gw_summary_fn, 10)
                )
            if self._hdc10_parser:
                candidates.append(
                    (self._hdc10_parser, "HDC 1.0", self._hdc10_summary_fn, 11)
                )


        # 自动识别：先用**互斥证据**判定输入是否国网 HDC 1.0 的 MPDU 帧控制
        # （信标/SOF/SACK/网间协调），是则把国网候选提到南网新一代之前。
        #
        # 实测（TMI 真实日志 748 个 ED 帧，DT=0/1/2/3 四类齐全）：南网新一代
        # 解析器对这些帧只返回 1 行退化结果（「未识别的MSDU类型」）却算「成功」
        # → 先行接管，四类帧全部被误判为南网新一代。国网新一代解析器亦不可
        # 先行——它把 HDC 1.0 的 MAC 帧误读成「信标帧 FC」（假阳性）。
        #
        # 判据只用 hdc_fc_evidence（CRC-24 自证）；不采用「像 HDC MAC 帧」这类
        # 结构启发式，因为 ED 布局错位 1 字节的垃圾业务帧能骗过它（实测会把
        # 南网新一代帧误重排到 HDC 1.0）。MAC/应用层帧在自动识别下不重排，
        # 需在协议下拉框显式选择「HDC 1.0」。
        if selected is None and len(candidates) > 1 and hdc_fc_evidence(frame):
            _rank = {"HDC 1.0": 0, "国网新一代": 1, "南网新一代": 2}
            candidates.sort(key=lambda c: _rank.get(c[1], 9))
        if not candidates:
            return ("未知", "无法识别协议", [])

        def _try_one(parser, proto_name, summary_fn, ed_proto):
            ed_rows, business = self._unwrap_ed_for_parse(frame, ed_proto)
            parse_target = business if business else (frame if not ed_rows else b"")
            biz_rows = []
            if parse_target and parser is not None:
                try:
                    biz_rows = parser.parse_to_table(parse_target) or []
                except Exception as e:
                    if ed_rows:
                        return (
                            proto_name,
                            f"{ed_wrapper_summary_name(ed_rows[0][0])} | 业务解析错误: {e}",
                            ed_rows,
                        )
                    raise
            if not ed_rows and not biz_rows:
                return None
            rows = list(ed_rows) + list(biz_rows)
            if ed_rows and not biz_rows:
                wrap_name = ed_wrapper_summary_name(ed_rows[0][0])
                ctrl1 = next((r[2] for r in ed_rows if r[0] == "控制域1"), "")
                ctrl2 = next((r[2] for r in ed_rows if r[0] == "控制域2"), "")
                dlen = next((r[2] for r in ed_rows if r[0] == "数据域长度"), "")
                summary = " | ".join(
                    p for p in (wrap_name, str(ctrl1), str(ctrl2),
                                f"数据:{dlen}" if dlen else "") if p
                )
                return (proto_name, summary, rows)
            # 有业务：包装名前缀 + 业务摘要
            biz_summary = ""
            if summary_fn:
                try:
                    biz_summary = summary_fn(biz_rows)
                except Exception:
                    biz_summary = self._fallback_summary(biz_rows)
            else:
                biz_summary = self._fallback_summary(biz_rows)
            if ed_rows:
                wrap_name = ed_wrapper_summary_name(ed_rows[0][0])
                # 业务摘要若已含包装名则不重复
                if wrap_name not in (biz_summary or ""):
                    biz_summary = f"{wrap_name} | {biz_summary}"
            return (proto_name, biz_summary or "-", rows)

        last_err = "无法识别协议"
        for parser, proto_name, summary_fn, ed_proto in candidates:
            try:
                result = _try_one(parser, proto_name, summary_fn, ed_proto)
            except Exception as e:
                last_err = f"解析错误: {e}"
                result = None
            if result is not None:
                return result
        if frame and frame[:1] == b"\xed":
            # ED 帧但业务未能用任一解析器展开：仍按当前显式选择给包装头
            # （自动识别时沿用 HDC 布局，与改动前 mode_map 的 0→11 一致）
            ed_proto = selected if selected in (9, 10, 11) else 11
            ed_rows, _biz = self._unwrap_ed_for_parse(frame, ed_proto)
            if ed_rows:
                wrap_name = ed_wrapper_summary_name(ed_rows[0][0])
                return ("ED封装", wrap_name, ed_rows)
        return ("未知", last_err, [])

    # ── 原始 TCP 载荷解析（1.23.45 起）─────────────────────────────
    #
    # 与 ED 路径的区别：ED 路径只有三个协议族，原始载荷则可能承载任何协议，且
    # **必须先证明它属于某协议**再解析 —— 各协议解析器对不匹配的字节流会返回
    # 「退化结果却算成功」（ED 路径的既有教训，见 hdc_fc_evidence docstring），
    # 只凭「解析器返回非空」必然误判。
    #
    # 判据按**校准实测**收敛为三层（样本与交叉验证见 test/test_tcp_monitor_raw_payload.py）：
    #   1) 字节结构前置检查 `_raw_structural_hint`：不符合帧形直接跳过；
    #   2) 非退化：解析行数 >= 2；
    #   3) 自证 `_raw_evidence_ok`：645 用校验器 0 fail；698.45 用 HCS/FCS 双通过
    #      （CRC 自证，同 HDC 的 CRC-24 思路）；Wrapper/DLMS-APDU 用帧头结构。
    #
    # **已声明边界**：南网 / 国网 同为 0x68 起头、链路层结构相近，校准实测两者
    # 校验器互判 0 fail（无法区分：南网样本对南网/国网校验器都是 0 fail），
    # 故**不参与自动识别**（错解析比不解析更糟），需在协议下拉显式选择。
    # 这与既有「HDC MAC/应用层帧不在自动识别覆盖范围」的边界声明同源。

    # 自动识别候选顺序（只放可自证的形态，越靠前越不易误判）
    _RAW_DETECT_ORDER = (4, 5, 6, 8)
    # 原始载荷路径的协议显示名（ED 三协议沿用既有文案，其余取注册表短名）
    _RAW_PROTO_NAMES = {
        4: "DLMS Wrapper",
        5: "DLMS-APDU",
        6: "DLT645-2007",
        8: "698.45",
    }

    def _selected_protocol_index(self) -> Optional[int]:
        """协议下拉里显式选择的协议索引；「自动识别」返回 None。

        以 itemData 为准；缺失时按显示名与注册表名/别名回退匹配，
        保证旧调用点（含既有测试的 findText + setCurrentIndex 用法）不受影响。
        """
        combo = getattr(self, "proto_combo", None)
        if combo is None:
            return None
        data = combo.currentData()
        if isinstance(data, int) and not isinstance(data, bool):
            return data
        text = (combo.currentText() or "").strip()
        if not text or text == "自动识别":
            return None
        try:
            import protocol_registry as pr

            for spec in pr._PROTOS:
                if text in (spec.name, spec.short_name) or text in tuple(spec.aliases):
                    return spec.index
        except Exception:
            pass
        return None

    def _payload_parser_for(self, index: int):
        """按协议索引取（并缓存）可用于原始载荷的解析器。

        ED 三协议复用 `set_parsers` 注入的实例，保证摘要文案与 ED 路径一致；
        其余协议走 `protocol_registry.build_gui_parser`（与 GUI 单帧解析同一入口）。
        """
        cache = getattr(self, "_payload_parser_cache", None)
        if cache is None:
            cache = self._payload_parser_cache = {}
        if index in cache:
            return cache[index]
        parser = None
        if index == 10 and self._gw_parser is not None:
            parser = self._gw_parser
        elif index == 9 and self._csg_parser is not None:
            parser = self._csg_parser
        elif index == 11 and self._hdc10_parser is not None:
            parser = self._hdc10_parser
        else:
            try:
                import protocol_registry as pr
                from parser_registry import get_parser

                spec = pr.get_protocol(index)
                parser = pr.build_gui_parser(index, get_parser(spec.parser_key))
            except Exception:
                parser = None
        cache[index] = parser
        return parser

    def _payload_validator(self, index: int):
        """按协议索引取（并缓存）校验器实例（取不到返回 None）。"""
        cache = getattr(self, "_payload_validator_cache", None)
        if cache is None:
            cache = self._payload_validator_cache = {}
        if index in cache:
            return cache[index]
        validator = None
        try:
            import protocol_registry as pr

            spec = pr.get_protocol(index)
            if spec.validator_class:
                mod_name, cls_name = spec.validator_class.split(":")
                mod = __import__(mod_name, fromlist=[cls_name])
                validator = getattr(mod, cls_name)()
        except Exception:
            validator = None
        cache[index] = validator
        return validator

    @staticmethod
    def _raw_structural_hint(index: int, payload: bytes) -> bool:
        """字节结构前置检查：明显不符合该协议帧形的候选直接跳过。"""
        if not payload:
            return False
        if index == 4:
            # DLMS Wrapper：版本 00 01 + Wrapper 长度与总长自洽
            if len(payload) < 8 or payload[0] != 0x00 or payload[1] != 0x01:
                return False
            wlen = int.from_bytes(payload[2:4], "big")
            return 0 < wlen <= len(payload)
        if index == 5:
            # DLMS-APDU 裸报文：首字节必须是已知 APDU 标签
            # （APDU_TYPES 是 HDLCParser 的类属性，不是模块级常量）
            try:
                from hdlc_parser import HDLCParser

                return payload[0] in HDLCParser.APDU_TYPES
            except Exception:
                return False
        if index == 6:
            # DLT645：68 + 6 字节从站地址 + 68
            return payload[0] == 0x68 and len(payload) >= 12 and payload[7] == 0x68
        if index == 8:
            # 698.45：68 起头、16H 结束（HCS/FCS 由 _raw_evidence_ok 自证）
            return payload[0] == 0x68 and payload[-1] == 0x16 and len(payload) >= 12
        return True

    @staticmethod
    def _rows_have_passing_crc(rows) -> bool:
        """解析行里是否 HCS 与 FCS 都「通过」（698.45 的 CRC 自证）。"""
        hcs_ok = fcs_ok = False
        for r in rows:
            name = str(r[0])
            desc = str(r[3] if len(r) > 3 else "")
            if "通过" not in desc:
                continue
            if "HCS" in name:
                hcs_ok = True
            elif "FCS" in name:
                fcs_ok = True
        return hcs_ok and fcs_ok

    def _raw_evidence_ok(self, index: int, payload: bytes, rows: list) -> bool:
        """自证判据：不同形态的可靠证据不同（校准实测结论）。"""
        if index == 6:
            # 645：校验器 0 fail（帧形已由结构检查保证）
            validator = self._payload_validator(6)
            if validator is None:
                return True
            try:
                return validator.verify(payload).fail_count == 0
            except Exception:
                return False
        if index == 8:
            return self._rows_have_passing_crc(rows)
        # DLMS Wrapper / DLMS-APDU：帧头结构已足够
        # （其校验器对自身帧形也报 fail —— 校准记录见 design.md §4）
        return True

    def _parse_with_protocol(self, index: int, payload: bytes):
        """用指定协议解析载荷；无解析器或异常返回 None。"""
        parser = self._payload_parser_for(index)
        if parser is None:
            return None
        try:
            rows = parser.parse_to_table(payload) or []
        except Exception:
            return None
        return rows or None

    def _raw_proto_name(self, index: int) -> str:
        name = self._RAW_PROTO_NAMES.get(index)
        if name:
            return name
        try:
            import protocol_registry as pr

            return pr.get_protocol(index).short_name
        except Exception:
            return f"协议{index}"

    def _raw_summary(self, index: int, rows: list) -> str:
        """命中协议后的摘要：ED 三协议复用既有摘要函数，其余用通用摘要。"""
        summary_fn = None
        if index == 10:
            summary_fn = self._gw_summary_fn
        elif index == 9:
            summary_fn = self._csg_summary_fn
        elif index == 11:
            summary_fn = self._hdc10_summary_fn
        if summary_fn:
            try:
                text = summary_fn(rows)
                if text and text != "-":
                    return text
            except Exception:
                pass
        return self._generic_rows_summary(rows)

    @staticmethod
    def _generic_rows_summary(rows, limit: int = 3) -> str:
        """通用摘要：优先取含类型/标识/命令语义的字段，否则取前几行解析值。"""
        key_words = ("类型", "标识", "APDU", "控制", "命令", "地址", "长度", "校验")
        picked = []
        for r in rows:
            name = str(r[0]).strip()
            val = str(r[2] if len(r) > 2 else "").strip()
            if not val or val == "-":
                continue
            if any(k in name for k in key_words):
                picked.append(f"{name[:14]}:{val[:16]}")
            if len(picked) >= limit:
                break
        if not picked:
            for r in rows:
                val = str(r[2] if len(r) > 2 else "").strip()
                if val and val != "-":
                    picked.append(val[:20])
                if len(picked) >= limit:
                    break
        return " | ".join(picked) if picked else "-"

    @staticmethod
    def _apdu_tag_hint(first: int):
        """首字节命中 698.45 / DLMS 的 APDU 标签表时返回 (疑似协议+名称, 说明)。

        标签表复用解析器既有实现（不新增第二份）。
        """
        try:
            from dl_t698_45_apdu_parser import DLT69845APDUParser

            info = DLT69845APDUParser.APDU_TYPE_MAP.get(first)
            if info:
                return (f"疑似 698.45 APDU: {info[0]}", str(info[1] or ""))
        except Exception:
            pass
        try:
            from hdlc_parser import HDLCParser

            name = HDLCParser.APDU_TYPES.get(first)
            if name:
                return (f"疑似 DLMS APDU: {name}", "")
        except Exception:
            pass
        return (None, None)

    def _raw_fallback_summary(self, payload: bytes) -> str:
        """未识别载荷的摘要：长度 + APDU 标签提示（若有）。"""
        parts = [f"TCP 载荷 {len(payload)} 字节"]
        if payload:
            tag, _desc = self._apdu_tag_hint(payload[0])
            if tag:
                parts.append(tag)
        return " | ".join(parts)

    def _raw_fallback_rows(self, payload: bytes) -> list:
        """未识别载荷的「原始数据」解析行（AC3.1/AC3.2：至少 3 行）。"""
        n = len(payload)
        rows = [
            [
                "TCP 载荷",
                f"{n} 字节",
                f"{n}",
                "原始数据：未匹配到已知协议（可在协议下拉显式选择）",
            ]
        ]
        if n:
            first = payload[0]
            tag, desc = self._apdu_tag_hint(first)
            rows.append(
                [
                    "首字节",
                    f"0x{first:02X}",
                    tag or "-",
                    desc or "APDU 标签表未命中",
                ]
            )
            rows.append(
                [
                    "原始数据",
                    payload[:32].hex(" ").upper(),
                    "",
                    f"共 {n} 字节，完整字节见「原始报文」视图",
                ]
            )
        return rows

    def _parse_raw_payload(self, payload: bytes) -> Tuple[str, str, list]:
        """原始 TCP 载荷解析：先证明协议再解析，都不成立则按 APDU/原始数据显示。"""
        if not payload:
            return ("原始数据", "空载荷", self._raw_fallback_rows(b""))

        selected = self._selected_protocol_index()
        if selected is not None:
            # 显式选择：只试该协议。但解析器对不匹配字节流会返回「退化行」（各协议
            # 都偏宽容），故要求「行数 >= 2 且摘要非空非 '-'」才算真命中，否则如实
            # 回落到原始数据显示 —— 不拿退化结果冒充解析成功。
            rows = self._parse_with_protocol(selected, payload)
            if rows and len(rows) >= 2:
                summary = self._raw_summary(selected, rows)
                if summary and summary != "-":
                    return (self._raw_proto_name(selected), summary, rows)
            name = self._raw_proto_name(selected)
            return (
                "原始数据",
                f"TCP 载荷 {len(payload)} 字节 | {name} 未匹配",
                self._raw_fallback_rows(payload),
            )

        # 自动识别：只放可自证的形态
        for index in self._RAW_DETECT_ORDER:
            if not self._raw_structural_hint(index, payload):
                continue
            rows = self._parse_with_protocol(index, payload)
            if not rows or len(rows) < 2:
                continue
            if not self._raw_evidence_ok(index, payload, rows):
                continue
            return (self._raw_proto_name(index), self._raw_summary(index, rows), rows)

        return (
            "原始数据",
            self._raw_fallback_summary(payload),
            self._raw_fallback_rows(payload),
        )

    def _fallback_summary(self, table_data: list) -> str:
        """无 summary_fn 时的简易摘要"""
        if not table_data:
            return "-"
        # 找几个关键字段（兼容协议10/11 两种 MMTYPE 字段名）
        fields = {str(item[0]).strip(): item for item in table_data}
        parts = []
        # 帧类型：协议10 字段名「定界符类型」（comment 形如 "DT=1: SOF帧"），
        # 协议11 为「定界符类型(DT)」（comment 即「信标帧/SOF帧/选择确认帧(SACK)/
        # 网间协调帧」，无冒号）——两种都认，否则协议11 四类帧摘要只剩 "-"。
        delim = fields.get("定界符类型") or fields.get("定界符类型(DT)")
        if delim is not None:
            dtext = str(delim[3] or delim[2])[:24]
            parts.append(
                dtext.split(":", 1)[1].strip() if ":" in dtext else dtext
            )
        if "MSDU类型" in fields:
            parts.append(str(fields["MSDU类型"][3])[:24])
        for mm_name in ("管理消息类型(MMTYPE)", "消息类型(MMTYPE)"):
            if mm_name in fields:
                cmt = str(fields[mm_name][3] or fields[mm_name][2])[:24]
                if cmt:
                    parts.append(f"MMTYPE:{cmt}")
                break
        if "业务标识" in fields:
            parts.append(str(fields["业务标识"][2])[:20])
        return " | ".join(parts) if parts else "-"

    def _fill_parse_table(self, table_data: list):
        """用解析结果填充解析表格 + 字段树（R5），并记录字节范围供高亮（R4）。

        table_data 行沿用项目约定：前 4 项固定为 字段/原始值/解析值/说明，
        第 5、6 项（若有）为字节范围 —— 与主窗口 `_populate_table_from_data` 一致。
        """
        self.parse_table.setRowCount(0)
        if not table_data:
            if hasattr(self, "parse_tree"):
                self.parse_tree.clear()
            self.frame_byte_view.clear_highlight()
            return
        for i, row_data in enumerate(table_data):
            self.parse_table.insertRow(i)
            field = str(row_data[0])
            raw = str(row_data[1])
            parsed = str(row_data[2])
            desc = str(row_data[3])
            start = row_data[4] if len(row_data) > 4 else None
            end = row_data[5] if len(row_data) > 5 else None
            field_item = QTableWidgetItem(field)
            field_item.setData(
                Qt.ItemDataRole.UserRole, start if isinstance(start, int) else None
            )
            field_item.setData(
                Qt.ItemDataRole.UserRole + 1, end if isinstance(end, int) else None
            )
            self.parse_table.setItem(i, 0, field_item)
            self.parse_table.setItem(i, 1, QTableWidgetItem(raw))
            self.parse_table.setItem(i, 2, QTableWidgetItem(parsed))
            self.parse_table.setItem(i, 3, QTableWidgetItem(desc))
        self._populate_parse_tree(table_data)

    def _populate_parse_tree(self, table_data: list):
        """填充 Wireshark 风格字段树（复用 parse_result_view，与主窗口同构）。"""
        if not hasattr(self, "parse_tree"):
            return
        self.parse_tree.clear()
        try:
            nodes = parse_result_view.build_tree_from_table_data(table_data)
        except Exception:
            return

        def _add(node, parent):
            item = QTreeWidgetItem()
            item.setText(0, str(node.display_name))
            item.setText(1, str(node.display_value))
            if node.comment:
                item.setToolTip(0, str(node.comment))
                item.setToolTip(1, str(node.comment))
            start, end = node.byte_range
            item.setData(0, Qt.ItemDataRole.UserRole, start)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, end)
            if parent is None:
                self.parse_tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.children:
                _add(child, item)

        for node in nodes:
            _add(node, None)
        self.parse_tree.expandAll()

    def _on_parse_tree_selected(self):
        """字段树选中 → 高亮对应字节（AC5.3）"""
        items = self.parse_tree.selectedItems()
        if not items:
            return
        item = items[0]
        start = item.data(0, Qt.ItemDataRole.UserRole)
        end = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if isinstance(start, int) and isinstance(end, int):
            self.frame_byte_view.highlight_range(start, end)
        else:
            self.frame_byte_view.clear_highlight()

    def _try_parse(self, parser, frame: bytes) -> bool:
        """尝试解析，成功返回 True"""
        try:
            result = parser.parse_to_table(frame)
            return len(result) > 0
        except Exception:
            return False

    # ── CSV 记录与加载 ────────────────────────────────

    def _on_csv_record_toggled(self, checked: bool):
        """开始/停止 CSV 记录"""
        if checked:
            self._start_csv_recording()
            self.csv_record_btn.setText("停止记录")
            set_btn(self.csv_record_btn, "danger")
        else:
            self._stop_csv_recording()
            self.csv_record_btn.setText("开始记录")
            set_btn(self.csv_record_btn, "success")

    def _start_csv_recording(self):
        """开始 CSV 记录（写入当前记录目录，见 ``record_dir()``）"""
        try:
            output_dir = self.record_dir()
            os.makedirs(output_dir, exist_ok=True)
            filename = f"tcp_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self._csv_path = os.path.join(output_dir, filename)
            self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8-sig")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "流ID", "时间", "方向", "源地址", "目的地址",
                "长度", "协议", "摘要", "原始HEX"
            ])
            self._csv_count = 0
            self.csv_status_label.setText(f"记录中: {filename} (0帧)")
            self.csv_status_label.setToolTip(f"记录文件：{self._csv_path}")
            self.csv_status_label.setStyleSheet("color: #C00000; font-size: 11px; font-weight: bold;")
        except Exception as e:
            QMessageBox.critical(self, "CSV 记录失败", f"无法创建日志文件:\n{e}")
            self.csv_record_btn.setChecked(False)

    def _stop_csv_recording(self):
        """停止 CSV 记录"""
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except Exception:
                pass
            self._csv_file = None
            self._csv_writer = None
            basename = os.path.basename(self._csv_path) if self._csv_path else ""
            self.csv_status_label.setText(f"已停止: {basename} ({self._csv_count}帧)")
            self.csv_status_label.setToolTip(f"记录文件：{self._csv_path}")
            self.csv_status_label.setStyleSheet("color: #888; font-size: 11px;")

    def _write_csv_record(self, flow_id: int, ts: float, direction: int,
                          src_addr: str, dst_addr: str, length: int,
                          proto_name: str, summary: str, frame: bytes):
        """写入一条 CSV 记录"""
        if self._csv_writer is None:
            return
        try:
            time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            dir_str = "→" if direction == 0 else "←"
            hex_str = ' '.join(f'{b:02X}' for b in frame)
            self._csv_writer.writerow([
                flow_id, time_str, dir_str, src_addr, dst_addr,
                length, proto_name, summary, hex_str
            ])
            self._csv_file.flush()
            self._csv_count += 1
            if self._csv_count % 10 == 0:
                basename = os.path.basename(self._csv_path)
                self.csv_status_label.setText(f"记录中: {basename} ({self._csv_count}帧)")
        except Exception:
            pass

    # ── 记录位置（目录可配 + 一键打开）─────────────────────────────

    def record_dir(self) -> str:
        """当前记录目录：用户选择优先，默认 = 数据目录下的 ``Output/``。"""
        return resolve_record_dir(self._record_dir_cfg, default_record_dir())

    def _update_record_dir_hint(self):
        """刷新「记录目录」与「打开位置」按钮的 tooltip（当前目录 + 配置来源）。"""
        cur = self.record_dir()
        src = "用户设置" if (self._record_dir_cfg or "").strip() else "默认"
        self.record_dir_btn.setToolTip(
            f"记录目录（{src}）：{cur}\n\n点开菜单：选择记录目录 / 打开记录目录 / 恢复默认目录"
        )
        self.open_record_btn.setToolTip(
            f"在文件管理器中打开记录位置（有记录文件时定位选中）\n当前目录：{cur}"
        )

    def _open_record_location(self):
        """打开记录位置：有当前记录文件则**定位并选中**它，否则打开记录目录。"""
        target_dir = self.record_dir()
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "打开记录位置失败", f"无法创建记录目录：\n{exc}")
            return
        try:
            open_in_file_manager(self._csv_path, target_dir)
        except OSError as exc:
            QMessageBox.warning(self, "打开记录位置失败", f"{exc}\n\n位置：{target_dir}")

    def _choose_record_dir(self):
        """选择记录目录并记住（写入 ``tcp_monitor_config.json``，重启后仍生效）。"""
        path = QFileDialog.getExistingDirectory(self, "选择记录目录", self.record_dir())
        if not path:
            return
        self._record_dir_cfg = path
        cfg = dict(self._record_cfg)
        cfg["record_dir"] = path
        self._record_cfg = cfg
        if not save_record_config(cfg):
            QMessageBox.warning(
                self, "保存失败",
                f"记录目录已生效，但配置写入失败（重启后会回到默认目录）：\n{path}",
            )
        self._update_record_dir_hint()

    def _reset_record_dir(self):
        """恢复默认记录目录（数据目录下的 ``Output/``）。"""
        self._record_dir_cfg = ""
        cfg = dict(self._record_cfg)
        cfg.pop("record_dir", None)
        self._record_cfg = cfg
        save_record_config(cfg)
        self._update_record_dir_hint()

    def _load_csv_recording(self):
        """加载历史 CSV 记录（默认从当前记录目录起选）"""
        path, _ = QFileDialog.getOpenFileName(
            self, "加载 TCP 监控记录", self.record_dir(), "CSV文件 (*.csv)"
        )
        if not path:
            return

        try:
            # 清空现有数据
            self._clear_all(confirm=False)
            # 停止抓包
            if self._sniffer and self._sniffer.isRunning():
                self._stop_capture()

            flows_map = {}  # flow_id -> (src, dst, packets, bytes, frames list)
            seq = 0

            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    flow_id = int(row.get("流ID", 0))
                    time_str = row.get("时间", "")
                    dir_str = row.get("方向", "→")
                    src_addr = row.get("源地址", "")
                    dst_addr = row.get("目的地址", "")
                    length = int(row.get("长度", 0))
                    proto_name = row.get("协议", "")
                    summary = row.get("摘要", "")
                    hex_str = row.get("原始HEX", "")
                    frame = bytes.fromhex(hex_str.replace(" ", "")) if hex_str else b''
                    direction = 0 if dir_str == "→" else 1

                    # 解析帧（为了填充缓存和摘要）——复用 _parse_and_summarize（含 ED）。
                    # 「原始数据」与「未知」同等对待：不覆盖旧记录里已存的具体协议名，
                    # 避免用新版本加载旧 CSV 时把历史协议标签抹成「原始数据」。
                    proto_name2, summary2, parsed = self._parse_and_summarize(frame)
                    if proto_name2 not in ("未知", "原始数据") or not proto_name:
                        if proto_name2 not in ("未知", "原始数据"):
                            proto_name = proto_name2
                    if summary2 and summary2 not in ("-", "无法识别协议"):
                        summary = summary2

                    # 加入流
                    if flow_id not in flows_map:
                        parts = src_addr.split(":")
                        dst_parts = dst_addr.split(":")
                        flows_map[flow_id] = {
                            "src": src_addr,
                            "dst": dst_addr,
                            "packets": 0,
                            "bytes": 0,
                            "frames": [],
                            "last_time": time_str,
                        }
                    flows_map[flow_id]["packets"] += 1
                    flows_map[flow_id]["bytes"] += length
                    flows_map[flow_id]["last_time"] = time_str
                    flows_map[flow_id]["frames"].append({
                        "ts": 0.0,  # 简化，不做时间戳
                        "time_str": time_str,
                        "direction": direction,
                        "frame": frame,
                        "protocol": proto_name,
                        "summary": summary,
                        "parsed": parsed,
                    })
                    seq += 1

            # 填充流列表
            flow_ids = sorted(flows_map.keys())
            for fid in flow_ids:
                info = flows_map[fid]
                row = self.flow_table.rowCount()
                self.flow_table.insertRow(row)
                self.flow_table.setItem(row, 0, QTableWidgetItem(str(fid)))
                self.flow_table.setItem(row, 1, QTableWidgetItem(info["src"]))
                self.flow_table.setItem(row, 2, QTableWidgetItem(info["dst"]))
                self.flow_table.setItem(row, 3, QTableWidgetItem(str(info["packets"])))
                self.flow_table.setItem(row, 4, QTableWidgetItem(str(info["bytes"])))
                self.flow_table.setItem(row, 5, QTableWidgetItem(info["last_time"]))
                # 存入 reassembler 模拟结构（直接用 widget 侧的 cache）
                self._flow_rows[fid] = row

            # 存帧数据到一个专门的 loaded_flows dict
            self._loaded_flows = flows_map

            self.status_label.setText(f"已加载 {len(flow_ids)} 条流，共 {seq} 帧")
            self.csv_status_label.setText(f"已加载: {os.path.basename(path)}")
            self.csv_status_label.setToolTip(f"记录文件：{path}")
            self.csv_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")

        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载 CSV 文件:\n{e}")

    # ── 清空 ──────────────────────────────────────────

    def _clear_all(self, confirm: bool = True):
        if confirm:
            ret = QMessageBox.question(
                self, "确认清空", "确定要清空所有捕获数据吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                return
        self._reassembler.clear()
        self._flow_rows.clear()
        self._frame_cache.clear()
        self._current_flow_id = None
        self._loaded_flows = None
        self.flow_table.setRowCount(0)
        self.frame_table.setRowCount(0)
        self.segment_table.setRowCount(0)
        self.parse_table.setRowCount(0)
        if hasattr(self, "parse_tree"):
            self.parse_tree.clear()
        self.frame_byte_view.set_bytes(b"")
        self.segment_hex.set_bytes(b"")
        if not (self._sniffer and self._sniffer.isRunning()):
            self.status_label.setText("已清空")

    # ── 工具方法 ──────────────────────────────────────

    def _fmt_time(self, ts: float) -> str:
        """格式化时间戳"""
        import datetime
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S.%f")[:-3]

    # ── 表格复制功能 ──────────────────────────────────

    def _setup_table_copy_menu(self, table: QTableWidget):
        """为表格设置右键复制菜单和 Ctrl+C 快捷键"""
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_table_copy_menu(t, pos)
        )
        shortcut = QShortcut(QKeySequence.Copy, table)
        shortcut.setContext(Qt.WidgetShortcut)
        shortcut.activated.connect(lambda t=table: self._copy_table_rows(t, all_rows=False))

    def _show_table_copy_menu(self, table: QTableWidget, pos):
        menu = QMenu(table)
        has_selection = len(table.selectedItems()) > 0

        copy_sel = menu.addAction("复制选中行")
        copy_sel.setEnabled(has_selection)
        copy_sel.triggered.connect(lambda: self._copy_table_rows(table, all_rows=False))

        copy_all = menu.addAction("复制全部")
        copy_all.triggered.connect(lambda: self._copy_table_rows(table, all_rows=True))

        menu.exec(table.mapToGlobal(pos))

    def _copy_table_rows(self, table: QTableWidget, all_rows: bool = False):
        col_count = table.columnCount()
        row_count = table.rowCount()

        if all_rows:
            rows = list(range(row_count))
        else:
            selected = table.selectedIndexes()
            if not selected:
                rows = list(range(row_count))
            else:
                rows = sorted({idx.row() for idx in selected})

        if not rows:
            return

        headers = []
        for c in range(col_count):
            item = table.horizontalHeaderItem(c)
            headers.append(item.text() if item else "")
        lines = ["\t".join(headers)]

        for r in rows:
            cells = []
            for c in range(col_count):
                item = table.item(r, c)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        text = "\n".join(lines)
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
