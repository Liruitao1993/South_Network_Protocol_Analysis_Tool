# -*- coding: utf-8 -*-
"""多线程分段下载器（纯逻辑，无 Qt，可独立测试）。

为什么需要
----------
原来的自动升级走单流 ``urllib`` 下载 100 MB 的 exe，实测慢到用户受不了
（现场反馈「下载太慢」）。本模块把下载改成 **HTTP Range 分段 + 线程池并发**：

- **分段**：先拿总长度，把文件切成 N 段，每段一个 ``Range: bytes=a-b`` 请求；
- **并发**：最多 32 个线程同时拉不同分段（``MAX_THREADS``），跑满带宽；
- **断点续传**：已完成的分段记录在 ``.progress.json`` 边车文件里，**重跑时只补没下完的段**；
- **暂停 / 继续**：``DownloadControl.pause()`` 让各线程在块边界停下并保存进度，
  ``resume()`` 后从断点继续（复用续传机制，不是重新开始）；
- **取消**：``DownloadControl.cancel()`` 立即停下并**清理已下载缓存**（``.part`` 与进度文件）；
- **回落**：服务端不支持 Range（返回 200 而不是 206）时**自动退回单流下载**。

安全与兼容
----------
- **只写 ``.part`` 临时文件，合并完成后才改名为目标文件** ⇒ 中断/崩溃不会留下
  一个「看起来下载完了其实是半截」的 exe（自动升级拿它去覆盖自己会出事）；
- **合并时按段序拼接**，每段长度与计划严格核对，少一个字节都算失败；
- 校验（SHA-256 / PE 魔数）仍由 ``auto_updater`` 负责，本模块只管把字节**完整**搬回来。

并发写入的关键约束
------------------
**每个线程必须用自己的文件句柄**。``seek()`` + ``write()`` 不是原子操作，
多线程共用一个句柄会互相踩掉偏移 —— 实测表现为「下载出来的文件字节错位」，
错位点正好落在 64 KB（``READ_BLOCK``）边界。各线程用独立 fd 各自 seek 才安全。

测试：test/test_downloader.py（纯逻辑 + 本地 HTTP 服务端端到端）。
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

#: 线程数上限（用户口径：最高 32 线程）
MAX_THREADS = 32
#: 默认线程数上限（自适应时的天花板）
DEFAULT_MAX_THREADS = 16
#: 单段最小尺寸：用于决定「开几个线程」（太小则请求开销占比过高）
MIN_CHUNK_SIZE = 1 << 20          # 1 MB
#: 单段最大尺寸（保留常量供调用方参考）
MAX_CHUNK_SIZE = 16 << 20         # 16 MB
#: 读缓冲（同时决定暂停响应的最大延迟）
READ_BLOCK = 1 << 16              # 64 KB
#: 单段重试次数
CHUNK_RETRIES = 3
#: 重试退避基数（秒）
RETRY_BACKOFF = 0.8
#: `Retry-After` 的单次等待上限（秒）：再长不如直接报错让用户重试
RETRY_AFTER_MAX = 10.0
#: 单次请求超时（秒）
DEFAULT_TIMEOUT = 30.0
#: 进度上报节流间隔（秒）
PROGRESS_INTERVAL = 0.15
#: 速率计算的滑动窗口（秒）
SPEED_WINDOW = 3.0

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jiexigongju-updater"

#: 边车文件名后缀（分段数据）
PART_SUFFIX = ".part"
#: 进度文件后缀（记录各段已完成字节与布局）
PROGRESS_SUFFIX = ".progress.json"


class DownloadError(Exception):
    """下载失败（网络错误 / 合并校验不过）。"""


class DownloadCancelled(DownloadError):
    """用户主动取消（与「失败」区分：不弹错误框，缓存已被清理）。"""


class _SegmentPaused(Exception):
    """内部信号：用户在下载中按下暂停（不是错误）。"""


class _RangeUnsupported(DownloadError):
    """该下载源无法按段提供数据（忽略 Range / 偏移不符 / 缺 Content-Range）。

    这是**能力缺失**而不是失败：调用方应丢弃分段缓存并回落单流下载。
    与普通 ``DownloadError`` 区分开，是为了「不重试、不重试加重偏移」。
    """


# ── 控制句柄（暂停 / 继续 / 取消） ───────────────────────────────

class DownloadControl:
    """跨线程的下载控制：暂停 / 继续 / 取消。

    - ``pause()`` 后各线程**在下一个 64 KB 块边界停下**（响应延迟 ≈ 一块的下载耗时），
      已完成的字节都保留在 ``.part`` 里；
    - ``resume()`` 让后续的下载调用从断点继续（复用续传机制）；
    - ``cancel()`` 立即中止，调用方负责清理缓存（或由 ``download_multithreaded`` 自动清理）。
    """

    def __init__(self):
        self._pause = threading.Event()
        self._cancel = threading.Event()
        # 「未暂停」事件：让等待方**真正的阻塞等**，而不是 ``sleep(0.1)`` 轮询。
        # 置位 = 允许继续跑；清零 = 已暂停。
        self._resume_evt = threading.Event()
        self._resume_evt.set()

    # 暂停
    def pause(self) -> None:
        self._pause.set()
        self._resume_evt.clear()

    def resume(self) -> None:
        self._pause.clear()
        self._resume_evt.set()

    def wait_resumed(self, timeout: Optional[float] = None) -> bool:
        """阻塞直到「继续」或「取消」；返回是否已不再暂停。

        取消必须能**穿透暂停**（否则 UI 卡在暂停里退不出来）。取消后调用方
        应再检查 :attr:`cancelled`。
        """
        if not self.paused:
            return True
        self._resume_evt.wait(timeout)
        return not self.paused

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    # 取消
    def cancel(self) -> None:
        self._cancel.set()
        self._pause.clear()          # 取消要能穿透「已暂停」，不能卡住
        self._resume_evt.set()       # 唤醒正在 wait_resumed() 的线程

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def reset(self) -> None:
        """复用同一个 control 开新一轮下载前调用。"""
        self._pause.clear()
        self._cancel.clear()
        self._resume_evt.set()


# ── 数据模型 ─────────────────────────────────────────────────────

@dataclass
class Segment:
    """一个待下载的分段。"""

    index: int
    start: int          # 起始字节（含）
    end: int            # 结束字节（含）
    done: int = 0       # 该段已完成字节数（续传用）

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def complete(self) -> bool:
        return self.done >= self.length

    @property
    def percent(self) -> float:
        if self.length <= 0:
            return 100.0
        return min(100.0, self.done * 100.0 / self.length)

    @property
    def range_header(self) -> str:
        """续传时的 Range 头：从已完成的下一字节开始。"""
        return f"bytes={self.start + self.done}-{self.end}"


@dataclass
class DownloadPlan:
    """一次下载的完整计划。"""

    url: str
    total_size: int
    segments: List[Segment] = field(default_factory=list)
    supports_range: bool = True
    etag: str = ""
    last_modified: str = ""

    @property
    def completed_bytes(self) -> int:
        return sum(s.done for s in self.segments)

    @property
    def percent(self) -> float:
        if not self.total_size:
            return 0.0
        return min(100.0, self.completed_bytes * 100.0 / self.total_size)

    @property
    def all_complete(self) -> bool:
        return all(s.complete for s in self.segments)


@dataclass(frozen=True)
class SegmentSnapshot:
    """单段的进度快照（供 GUI 逐线程展示）。"""

    index: int
    start: int
    end: int
    done: int
    length: int

    @property
    def percent(self) -> float:
        if self.length <= 0:
            return 100.0
        return min(100.0, self.done * 100.0 / self.length)

    @property
    def complete(self) -> bool:
        return self.done >= self.length


@dataclass(frozen=True)
class DownloadProgress:
    """一次进度快照（GUI 用它画总进度、速率、逐线程明细）。"""

    percent: float
    completed_bytes: int
    total_size: int
    speed_bps: float                 # 当前速率（字节/秒）
    threads: int                     # 并发线程数
    segments: Tuple[SegmentSnapshot, ...] = ()
    state: str = "running"           # running / paused / completed / cancelled


# ── 进度回调适配（兼容旧的 float 回调） ──────────────────────────

def _emit(progress_cb, stats_cb, snap: DownloadProgress) -> None:
    """同时支持旧契约（``progress_cb(percent)``）与新契约（``stats_cb(snapshot)``）。"""
    if stats_cb is not None:
        try:
            stats_cb(snap)
        except Exception:            # noqa: BLE001 - 回调异常不能带崩下载
            pass
    if progress_cb is not None:
        try:
            progress_cb(snap.percent)
        except Exception:            # noqa: BLE001
            pass


class _SpeedMeter:
    """滑动窗口速率计（字节/秒）。"""

    def __init__(self, window: float = SPEED_WINDOW):
        self.window = window
        self._samples: deque = deque()

    def update(self, completed_bytes: int, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        self._samples.append((now, completed_bytes))
        cutoff = now - self.window
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.popleft()
        if len(self._samples) < 2:
            return 0.0
        t0, b0 = self._samples[0]
        dt = now - t0
        if dt <= 0:
            return 0.0
        return max(0.0, (completed_bytes - b0) / dt)


def _snapshot(plan: DownloadPlan, threads: int, speed: float,
              state: str = "running") -> DownloadProgress:
    return DownloadProgress(
        percent=plan.percent,
        completed_bytes=plan.completed_bytes,
        total_size=plan.total_size,
        speed_bps=speed,
        threads=threads,
        segments=tuple(
            SegmentSnapshot(s.index, s.start, s.end, s.done, s.length)
            for s in plan.segments
        ),
        state=state,
    )


# ── 规划 ─────────────────────────────────────────────────────────

def choose_thread_count(total_size: int, max_threads: Optional[int] = None,
                        cpu_count: Optional[int] = None) -> int:
    """按文件大小与 CPU 核数选线程数（上限 32）。

    分段下载是 **IO 密集**（等网络），CPU 核数只是「别开太多线程把自己拖慢」的上界参考，
    真正的收益来自并发连接数。小文件开 32 线程纯属浪费（每段一个 HTTP 往返）。
    """
    # 「自动」= ``DEFAULT_MAX_THREADS``（16），用户显式配置时才用 1..MAX_THREADS。
    # 此前这里用 MAX_THREADS 兜底，导致常量 DEFAULT_MAX_THREADS 成了死代码、
    # 「自动」实际等于 32 线程（小文件白白开一堆连接）。
    limit = DEFAULT_MAX_THREADS if max_threads is None else max(1, int(max_threads))
    limit = min(limit, MAX_THREADS)
    if total_size <= 0:
        return 1
    by_size = max(1, total_size // MIN_CHUNK_SIZE)
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 4)
    by_cpu = max(1, min(MAX_THREADS, cpus * 4))
    return max(1, min(limit, by_size, by_cpu))


def plan_segments(total_size: int, threads: int) -> List[Segment]:
    """把 total_size 切成最多 threads 段（尽量均分，段与段首尾相接）。

    **不按 MIN_CHUNK_SIZE 二次收敛段数** —— 段数只由 ``threads`` 决定。
    （MIN_CHUNK_SIZE 只用于 `choose_thread_count` 决定**开几个线程**。）
    """
    if total_size <= 0:
        return []
    threads = max(1, int(threads))
    base = total_size // threads
    extra = total_size % threads
    segments: List[Segment] = []
    offset = 0
    for i in range(threads):
        size = base + (1 if i < extra else 0)
        if size <= 0:
            break
        end = offset + size - 1
        segments.append(Segment(index=i, start=offset, end=end))
        offset = end + 1
    return segments


# ── 探测 ─────────────────────────────────────────────────────────

def _open_url(url: str, headers: Dict[str, str], timeout: float):
    """打开 url（跟随重定向）。GitHub 资产直链是 302 → S3，必须跟随。"""
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def probe_size(url: str, timeout: float = DEFAULT_TIMEOUT,
               http_head=None) -> Tuple[int, bool, str, str]:
    """探测资源大小与是否支持 Range。

    返回 ``(total_size, supports_range, etag, last_modified)``。
    用 ``Range: bytes=0-0`` 探测：只有 206 才算支持分段。
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/octet-stream, */*"}
    if http_head is not None:
        size, supports, etag, lm = http_head(url)
        return int(size), bool(supports), str(etag or ""), str(lm or "")

    try:
        with _open_url(url, {**headers, "Range": "bytes=0-0"}, timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            crange = resp.headers.get("Content-Range") or ""
            etag = resp.headers.get("ETag") or ""
            lm = resp.headers.get("Last-Modified") or ""
            total = 0
            if "/" in crange:
                tail = crange.rsplit("/", 1)[-1].strip()
                if tail.isdigit():
                    total = int(tail)
            supports = status == 206
            if not total:
                clen = resp.headers.get("Content-Length")
                if clen and clen.isdigit() and not supports:
                    total = int(clen)
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"无法获取下载信息：HTTP {getattr(exc, 'code', 0)}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(f"网络请求失败：{getattr(exc, 'reason', exc)}") from exc
    except (TimeoutError, OSError) as exc:
        raise DownloadError(f"网络请求失败：{exc}") from exc

    if not total:
        return 0, False, "", ""
    return total, supports, etag, lm


def _parse_content_range(value: Optional[str]):
    """解析 ``bytes 0-0/12345`` → ``(start, end, total|None)``；解析不了返回 ``None``。"""
    try:
        unit, _, rest = str(value or "").strip().partition(" ")
        if unit.lower() != "bytes":
            return None
        span, _, total_part = rest.partition("/")
        start_s, _, end_s = span.partition("-")
        start, end = int(start_s), int(end_s)
        total = int(total_part.strip()) if total_part.strip().isdigit() else None
        return start, end, total
    except (ValueError, AttributeError):
        return None


def _verify_segment_response(status: int, resp_headers, seg: Segment,
                             plan: DownloadPlan) -> None:
    """分段响应自证（单一实现）：不通过则抛 ``_RangeUnsupported`` / ``DownloadError``。

    三条判据，缺一不可：

    1. ``200`` = 服务端**忽略了 Range**（把整个文件发回来）⇒ 只有「单段且从 0 起」可接受，
       否则绝不按段偏移写入（否则会越过本段尾部污染下一段，且重试会把 ``seg.done`` 越推越大）；
    2. ``206`` 必须给出**可解析的** ``Content-Range``；
    3. ``Content-Range`` 的起点必须等于本次请求的起点 ``seg.start + seg.done``；
       总长若与计划不符 ⇒ 资源已变化，不可重试。

    为什么必须自证：``seek`` + ``write`` 落到错误偏移上产出的文件**大小是对的、内容是错的**；
    而 SHA-256 校验在「更新设置」里可以被关掉，那时只剩 PE 魔数闸，会把坏 exe 装上去。
    """
    if status == 200:
        if seg.start == 0 and seg.done == 0 and len(plan.segments) == 1:
            return
        raise _RangeUnsupported(
            "服务器忽略了 Range 请求（返回 200 而不是 206），该下载源不支持分段")
    if status != 206:
        raise DownloadError(f"分段下载返回 HTTP {status}")

    parsed = _parse_content_range((resp_headers or {}).get("Content-Range") or "")
    if parsed is None:
        raise _RangeUnsupported("分段响应缺少可解析的 Content-Range，无法自证偏移")
    start, _end, total = parsed
    expected = seg.start + seg.done
    if start != expected:
        raise _RangeUnsupported(
            f"分段响应偏移不符（请求从 {expected} 开始，服务端返回 {start}）")
    if total is not None and total != plan.total_size:
        raise DownloadError(
            f"资源大小已变化（计划 {plan.total_size} 字节，服务端 {total} 字节），请重新下载")


def _retry_delay(exc: BaseException, attempt: int) -> float:
    """重试前的等待时间：默认线性退避，``429`` / ``503`` 时尊重 ``Retry-After``。"""
    delay = RETRY_BACKOFF * (attempt + 1)
    headers = getattr(exc, "headers", None)
    if (isinstance(exc, urllib.error.HTTPError)
            and getattr(exc, "code", 0) in (429, 503) and headers is not None):
        raw = headers.get("Retry-After")
        if raw and str(raw).strip().isdigit():
            delay = min(float(str(raw).strip()), RETRY_AFTER_MAX)
    return delay


def _describe_os_error(exc: OSError, need_bytes: int = 0) -> str:
    """把磁盘 / 文件系统 ``OSError`` 翻成可读中文（不再把英文原文抛给用户）。"""
    import errno as _errno

    if getattr(exc, "errno", None) == _errno.ENOSPC:
        return (f"磁盘空间不足：需要至少 {format_bytes(need_bytes)} 可用空间"
                f"（{exc}）")
    return f"无法读写临时文件：{exc}"


# ── 进度边车 ──────

def _load_progress(path: Path, plan: DownloadPlan) -> List[Segment]:
    """读取边车进度文件，把已完成字节还原到各段上。

    **段布局必须与进度文件记录的一致**才复用：段边界变了（线程数变化）而 done
    计数还按老布局走 ⇒ 拼出来的文件字节错位。对不上就整份作废、从头下。
    """
    segments = plan.segments
    if not path.exists():
        return segments
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return segments
    if not isinstance(data, dict):
        return segments
    # 换了下载地址（不同版本 / 不同源）⇒ 旧的 done 计数与 .part 字节都不可信。
    # 旧文件缺 ``url`` 键时保持兼容（老版本写出的进度文件仍可复用）。
    if data.get("url") and str(data.get("url")) != plan.url:
        return segments
    if data.get("etag") and plan.etag and data.get("etag") != plan.etag:
        return segments
    total_field = data.get("total")
    try:
        if total_field is not None and int(total_field) != plan.total_size:
            return segments
    except (TypeError, ValueError):
        return segments
    layout = data.get("layout")
    if not isinstance(layout, dict):
        return segments
    for seg in segments:
        item = layout.get(str(seg.index))
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            return segments
        if int(item[0]) != seg.start or int(item[1]) != seg.end:
            return segments
    done_map = data.get("done") or {}
    for seg in segments:
        value = done_map.get(str(seg.index))
        if isinstance(value, int) and value > 0:
            seg.done = min(value, seg.length)
    return segments


def _save_progress(path: Path, plan: DownloadPlan) -> None:
    """保存进度（原子写：断电/崩溃不留半截 JSON）。"""
    payload = {
        "url": plan.url,
        "total": plan.total_size,
        "etag": plan.etag,
        "last_modified": plan.last_modified,
        "layout": {str(s.index): [s.start, s.end] for s in plan.segments},
        "done": {str(s.index): s.done for s in plan.segments if s.done},
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def cleanup_partial(dest_path: Path) -> bool:
    """清理某文件已下载的缓存（``.part`` / ``.progress.json`` / ``.merge``）。

    取消下载、或用户主动「清理缓存」时调用。返回是否清掉过东西。
    """
    dest = Path(dest_path)
    removed = False
    for suffix in (PART_SUFFIX, PROGRESS_SUFFIX, PROGRESS_SUFFIX + ".tmp", ".merge"):
        target = dest.with_name(dest.name + suffix)
        try:
            if target.exists():
                target.unlink()
                removed = True
        except OSError:
            pass
    return removed


def partial_size(dest_path: Path) -> int:
    """已下载的缓存字节数（``.part`` 大小；没有则 0）。"""
    part = Path(dest_path).with_name(Path(dest_path).name + PART_SUFFIX)
    try:
        return part.stat().st_size if part.exists() else 0
    except OSError:
        return 0


# ── 单段下载 ─────────────────────────────────────────────────────

def _wait_workers_idle(active, lock, timeout: float) -> bool:
    """最多等 ``timeout`` 秒让活动 worker 归零；返回是否已归零。

    取消后清理缓存前的前置条件：不能删了 ``.part`` 而 worker 还在往里写。
    """
    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        with lock:
            if not active[0]:
                return True
        time.sleep(0.02)
    with lock:
        return not active[0]


def _download_segment(url: str, seg: Segment, part_path: Path, plan: DownloadPlan,
                      timeout: float, headers: Dict[str, str],
                      control: Optional[DownloadControl] = None,
                      on_bytes=None) -> None:
    """下载单段到 ``.part`` 的对应偏移；失败自动重试。

    断点续传：Range 头从 ``seg.start + seg.done`` 起算，**只补没下完的部分**。

    **每线程独立文件句柄**（见模块 docstring：共用句柄会踩掉偏移导致字节错位）。

    暂停/取消在**每个 64 KB 块**之后检查 —— 响应延迟就是「一块的下载耗时」，
    同时保证停下时 ``seg.done`` 与 ``.part`` 里的数据严格一致（不会半块）。
    """
    last_error: Optional[Exception] = None
    for attempt in range(CHUNK_RETRIES):
        if seg.complete:
            return
        try:
            req_headers = dict(headers)
            req_headers["Range"] = seg.range_header
            with _open_url(url, req_headers, timeout) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                # 响应必须自证「确实是我要的那一段」才允许写盘（R1 + R5）
                _verify_segment_response(status, resp.headers, seg, plan)
                offset = seg.start + seg.done
                with open(part_path, "r+b") as handle:
                    while True:
                        if control is not None:
                            if control.cancelled:
                                raise DownloadCancelled("已取消")
                            if control.paused:
                                raise _SegmentPaused()
                        block = resp.read(READ_BLOCK)
                        if not block:
                            break
                        handle.seek(offset)
                        handle.write(block)
                        seg.done += len(block)
                        offset += len(block)
                        if seg.done > seg.length:
                            raise DownloadError("分段数据超出预期长度")
                        if on_bytes:
                            on_bytes()
            if not seg.complete:
                raise DownloadError("分段数据不完整")
            return
        except _RangeUnsupported:
            seg.done = 0                 # 丢弃不可信的段内进度，交由调用方回落单流
            raise
        except (DownloadCancelled, _SegmentPaused):
            raise                        # 控制信号不是错误，不参与重试
        except Exception as exc:         # noqa: BLE001 - 其余按可重试处理
            last_error = exc
            if attempt < CHUNK_RETRIES - 1:
                time.sleep(_retry_delay(exc, attempt))
    raise DownloadError(f"分段 {seg.index} 下载失败：{last_error}")


# ── 主入口 ───────────────────────────────────────────────────────

def download_multithreaded(
    url: str,
    dest_path: Path,
    progress_cb: Optional[Callable[[float], None]] = None,
    max_threads: Optional[int] = None,
    timeout: float = DEFAULT_TIMEOUT,
    resume: bool = True,
    http_head=None,
    stats_cb: Optional[Callable[[DownloadProgress], None]] = None,
    control: Optional[DownloadControl] = None,
    on_cancel: str = "clean",
) -> Path:
    """多线程分段下载 url → dest_path。

    - 服务端支持 Range ⇒ 分段并发；不支持 ⇒ **自动回落单流**；
    - ``resume=True``（默认）复用 ``.part`` 进度，**只补未完成的段**；
    - ``progress_cb(percent)`` 兼容旧契约；``stats_cb(DownloadProgress)`` 给 GUI 画明细；
    - ``control`` 提供暂停 / 取消；
    - **暂停**是**正常返回**，调用方看 ``control.paused`` 就知道是「暂停」而不是「完成/失败」；
    - **取消**抛 ``DownloadCancelled``；临时文件留不留由 ``on_cancel`` 决定（``"keep"`` / ``"clean"``）；
    - 分段与最终合并都**只写 ``.part``**，全部段完成并核对长度后才 ``os.replace`` 到 dest_path。
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest.with_name(dest.name + PART_SUFFIX)
    progress_path = dest.with_name(dest.name + PROGRESS_SUFFIX)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/octet-stream, */*"}

    if control is not None and control.cancelled:
        raise DownloadCancelled("已取消")

    total, supports, etag, lm = probe_size(url, timeout=timeout)
    if total <= 0 or not supports:
        # 拿不到长度 / 服务端不认 Range ⇒ 单流兜底（内部自带暂停/取消/续传处理）
        return _download_single_stream(
            url, dest, progress_cb, timeout, headers,
            stats_cb=stats_cb, control=control, resume=resume,
            on_cancel=on_cancel)

    threads = choose_thread_count(total, max_threads)
    plan = DownloadPlan(url=url, total_size=total, supports_range=True,
                        etag=etag, last_modified=lm)
    plan.segments = plan_segments(total, threads)
    if resume:
        plan.segments = _load_progress(progress_path, plan)
    else:
        cleanup_partial(dest)
        _save_progress(progress_path, plan)

    meter = _SpeedMeter()
    meter.update(plan.completed_bytes)
    _emit(progress_cb, stats_cb, _snapshot(plan, threads, 0.0))

    pending = [s for s in plan.segments if not s.complete]
    if not pending:
        _merge_segments(part_path, dest, plan)
        cleanup_partial(dest)
        _emit(progress_cb, stats_cb, _snapshot(plan, threads, 0.0, "completed"))
        return dest

    # 预分配 .part 到总长（各线程按偏移写，需要文件先够大）。
    # 失败给中文原因：磁盘满时用户至少知道该清哪里，而不是看到 WinError 112。
    try:
        mode = "r+b" if part_path.exists() else "w+b"
        with open(part_path, mode) as handle:
            if handle.seek(0, os.SEEK_END) < total:
                handle.truncate(total)
    except OSError as exc:
        raise DownloadError(_describe_os_error(exc, total)) from exc

    lock = threading.Lock()
    last_report = [0.0]
    paused_flag = [False]
    cancelled_flag = [False]
    range_unsupported = [False]
    active = [0]

    def report(force: bool = False):
        now = time.time()
        if not force and now - last_report[0] < PROGRESS_INTERVAL:
            return
        last_report[0] = now
        with lock:
            speed = meter.update(plan.completed_bytes, now)
            snap = _snapshot(plan, threads, speed)
        _emit(progress_cb, stats_cb, snap)

    def worker(seg: Segment):
        with lock:
            active[0] += 1
        try:
            try:
                _download_segment(url, seg, part_path, plan, timeout, headers,
                                  control=control, on_bytes=report)
            except _SegmentPaused:
                paused_flag[0] = True
            except _RangeUnsupported:
                range_unsupported[0] = True
            except DownloadCancelled:
                cancelled_flag[0] = True
        finally:
            with lock:
                active[0] -= 1
                _save_progress(progress_path, plan)
            report(force=True)

    errors: List[str] = []
    # 不用 ``with ThreadPoolExecutor(...)``：取消时要能「不等待卡住的分段」立即返回（R16）。
    # ``with`` 的 ``__exit__`` 会对所有 worker 做 ``join``，于是一个卡在 socket read 上的段
    # 就能把「取消」拖到超时（30s）甚至更久。
    pool = ThreadPoolExecutor(max_workers=max(1, threads))
    futures = [pool.submit(worker, seg) for seg in pending]
    try:
        for fut in as_completed(futures):
            exc = fut.exception()
            if exc is not None:
                errors.append(str(exc))
            if control is not None and control.cancelled:
                break                    # 取消：立即停止等待其余分段
    finally:
        was_cancelled = control is not None and control.cancelled
        # 已经 queued 但未开始的段不必再跑（``cancel_futures``），也不 join
        pool.shutdown(wait=not was_cancelled, cancel_futures=was_cancelled)
        if was_cancelled:
            workers_stopped = _wait_workers_idle(active, lock, 2.0)
        else:
            workers_stopped = True

    with lock:
        _save_progress(progress_path, plan)

    if cancelled_flag[0] or (control is not None and control.cancelled):
        # 仍在校验活动的 worker 时**不删**临时文件：删了而 worker 还在写，会把
        # ``.part`` 一半抹掉一半重建（下次续传拼出坏文件）。"keep" 本来就安全。
        if on_cancel == "clean" and workers_stopped:
            cleanup_partial(dest)
        _emit(progress_cb, stats_cb, _snapshot(plan, threads, 0.0, "cancelled"))
        if on_cancel == "clean" and workers_stopped:
            raise DownloadCancelled("下载已取消，临时文件已清理")
        raise DownloadCancelled("下载已取消（进度已保留，下次可续传）")

    if paused_flag[0] or (control is not None and control.paused):
        with lock:
            snap = _snapshot(plan, threads, 0.0, "paused")
        _emit(progress_cb, stats_cb, snap)
        # 暂停：正常返回「未完成」的 dest 不存在，调用方据 control.paused 判断
        return dest

    if range_unsupported[0]:
        # 该源不可分段（忽略 Range / 偏移不符 / 缺 Content-Range）。
        # 分段缓存里的字节全部作废 → 清掉 .part，整体回落单流（R1）。
        cleanup_partial(dest)
        return _download_single_stream(
            url, dest, progress_cb, timeout, headers, stats_cb=stats_cb,
            control=control, resume=False, on_cancel=on_cancel)

    if errors:
        raise DownloadError("；".join(errors[:3]) or "分段下载失败")

    _merge_segments(part_path, dest, plan)
    cleanup_partial(dest)
    _emit(progress_cb, stats_cb, _snapshot(plan, threads, 0.0, "completed"))
    return dest


def _merge_segments(part_path: Path, dest: Path, plan: DownloadPlan) -> None:
    """按段序把 ``.part`` 合并成目标文件，并核对每段长度。

    **长度不符直接失败** —— 半截文件绝不落到目标路径（自动升级会拿它覆盖 exe）。
    """
    total = plan.total_size
    try:
        size = part_path.stat().st_size
    except OSError as exc:
        raise DownloadError(f"分段文件不可读：{exc}") from exc
    if size < total:
        raise DownloadError(f"分段文件不完整（{size} / {total} 字节）")
    tmp = dest.with_name(dest.name + ".merge")
    try:
        with open(part_path, "rb") as src, open(tmp, "wb") as out:
            for seg in plan.segments:
                remaining = seg.length
                src.seek(seg.start)
                while remaining > 0:
                    block = src.read(min(READ_BLOCK, remaining))
                    if not block:
                        raise DownloadError("合并时遇到数据缺口")
                    out.write(block)
                    remaining -= len(block)
            out.flush()
            os.fsync(out.fileno())
        if tmp.stat().st_size != total:
            raise DownloadError("合并后大小与预期不符")
        os.replace(tmp, dest)
    except OSError as exc:
        raise DownloadError(f"合并失败：{exc}") from exc
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _download_single_stream(url: str, dest: Path, progress_cb, timeout: float,
                            headers: Dict[str, str], stats_cb=None,
                            control: Optional[DownloadControl] = None,
                            resume: bool = True,
                            on_cancel: str = "clean") -> Path:
    """单流下载（服务端不支持 Range 时的兜底，也是分段不可用时的回退路径）。

    三条行为契约：

    * **能续传就续传**（R6）：``.part`` 已有 N 字节时发 ``Range: bytes=N-``，
      拿到 ``206`` 就追加写；服务端回 ``200``（不认 Range）时从 0 重写，
      并通过 ``state="restart"`` 明告用户「进度会从头开始」（否则进度条突然
      从 80% 跳回 0%，看起来像 bug）。
    * **暂停是正常返回**（``state="paused"`` 后 return）。
    * **取消根据 ``on_cancel`` 决定留不留缓存**（``"keep"`` / ``"clean"``）。
    """
    part = dest.with_name(dest.name + PART_SUFFIX)
    if not resume:
        cleanup_partial(dest)

    off = 0
    try:
        if part.exists():
            off = max(0, int(part.stat().st_size))
    except OSError:
        off = 0

    meter = _SpeedMeter()
    done = 0
    total = 0
    req_headers = dict(headers)
    if off > 0:
        req_headers["Range"] = f"bytes={off}-"
    try:
        with _open_url(url, req_headers, timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            crange = _parse_content_range(resp.headers.get("Content-Range") or "")
            if status == 206 and crange is not None:
                total = crange[2] or 0
                mode = "ab"
                done = off
            else:
                # 200（或 206 但 Content-Range 不可解析）⇒ 整文件从头来
                total = int(resp.headers.get("Content-Length") or 0) or 0
                mode = "wb"
                done = 0
                if off > 0:
                    _emit(progress_cb, stats_cb, DownloadProgress(
                        percent=0.0, completed_bytes=0, total_size=total,
                        speed_bps=0.0, threads=1, segments=(),
                        state="restart"))
            meter.update(done)
            with open(part, mode) as fh:
                while True:
                    if control is not None:
                        if control.cancelled:
                            raise DownloadCancelled("已取消")
                        if control.paused:
                            raise _SegmentPaused()
                    block = resp.read(READ_BLOCK)
                    if not block:
                        break
                    fh.write(block)
                    done += len(block)
                    if stats_cb is not None:
                        speed = meter.update(done)
                        _emit(progress_cb, stats_cb, DownloadProgress(
                            percent=(min(100.0, done * 100.0 / total) if total else 0.0),
                            completed_bytes=done,
                            total_size=total or done,
                            speed_bps=speed,
                            threads=1,
                            segments=(),
                            state="running",
                        ))
                    elif progress_cb and total:
                        progress_cb(min(100.0, done * 100.0 / total))
    except _SegmentPaused:
        _emit(progress_cb, stats_cb, DownloadProgress(
            percent=(min(100.0, done * 100.0 / total) if total else 0.0),
            completed_bytes=done, total_size=total or done,
            speed_bps=0.0, threads=1, segments=(), state="paused"))
        return dest                     # 暂停 = 正常返回（.part 保留）
    except DownloadCancelled:
        if on_cancel == "clean":
            cleanup_partial(dest)
        raise
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        if code == 416 and off > 0:
            # 服务器认为 Range 不可满足 ⇒ ``.part`` 已经到齐（或已超过总长）
            try:
                os.replace(part, dest)
            except OSError as w_exc:
                raise DownloadError(f"保存下载文件失败：{w_exc}") from w_exc
            done = off
            total = total or done
        else:
            raise DownloadError(f"下载失败：HTTP {code}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(f"下载失败：{getattr(exc, 'reason', exc)}") from exc
    except (TimeoutError, OSError) as exc:
        raise DownloadError(f"下载失败：{exc}") from exc
    try:
        if part.exists():
            os.replace(part, dest)
    except OSError as exc:
        raise DownloadError(_describe_os_error(exc, done)) from exc
    _emit(progress_cb, stats_cb, DownloadProgress(
        percent=100.0, completed_bytes=done, total_size=total or done,
        speed_bps=0.0, threads=1, segments=(), state="completed"))
    return dest


def format_speed(bps: float) -> str:
    """速率转人话：``1.24 MB/s`` / ``512 KB/s`` / ``—``。"""
    try:
        value = float(bps)
    except (TypeError, ValueError):
        return "—"
    if value <= 0:
        return "—"
    for unit, scale in (("MB/s", 1024 * 1024), ("KB/s", 1024)):
        if value >= scale:
            return f"{value / scale:.2f} {unit}"
    return f"{value:.0f} B/s"


def format_bytes(size: float) -> str:
    """字节数转人话：``100.0 MB`` / ``512 KB`` / ``0 B``。"""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "0 B"
    if value <= 0:
        return "0 B"
    for unit, scale in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if value >= scale:
            return f"{value / scale:.1f} {unit}"
    return f"{value:.0f} B"


__all__ = [
    "MAX_THREADS",
    "DEFAULT_MAX_THREADS",
    "MIN_CHUNK_SIZE",
    "MAX_CHUNK_SIZE",
    "CHUNK_RETRIES",
    "PART_SUFFIX",
    "PROGRESS_SUFFIX",
    "DownloadError",
    "DownloadCancelled",
    "DownloadControl",
    "Segment",
    "DownloadPlan",
    "SegmentSnapshot",
    "DownloadProgress",
    "choose_thread_count",
    "plan_segments",
    "probe_size",
    "download_multithreaded",
    "cleanup_partial",
    "partial_size",
    "format_speed",
    "format_bytes",
]
