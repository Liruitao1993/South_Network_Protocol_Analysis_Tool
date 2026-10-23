# -*- coding: utf-8 -*-
"""多线程分段下载器回归（1.23.95）。

覆盖点：
  1. **分段规划** —— 段数上限、均分、每段长度守恒、边界（小文件/0 字节/超大文件）。
  2. **线程数选择** —— 上限 32、按文件大小收敛、CPU 核数只作上界参考。
  3. **端到端（本地 HTTP 服务端）** —— 并发多段下载出来的字节与源文件**逐字节一致**；
     服务端**不支持 Range**（恒返回 200）时**自动回落单流**且结果正确。
  4. **断点续传** —— 中断后重跑，**只补没下完的段**（服务端被请求次数可证），
     且最终字节完全正确；进度边车文件不残留。
  5. **失败路径** —— 全段失败抛 DownloadError；**目标文件不出现**（绝不留半截 exe）。
  6. **合并校验** —— 分段数据缺���时合并失败，不产出目标文件。
  7. **与 auto_updater 的衔接** —— Opdater 走新下载器；PE 魔数兜底仍然生效。

运行: python test/test_downloader.py
"""

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import downloader as dl  # noqa: E402


# ── 本地 HTTP 服务端（可控 Range 行为 + 计数） ────────────────────

class _Handler(BaseHTTPRequestHandler):
    payload = b""
    support_range = True
    requests = []          # (start, end) 或 (None, None) 表示整文件
    request_lock = threading.Lock()
    fail_after = None      # 前 N 个请求后开始返回 500
    block_delay = 0.0      # 每个 16 KB 块的延迟（模拟慢速网络，便于测暂停）
    honor_zero_range_only = False   # 仅 start==0 的 Range 才返回 206（模拟中途丢 Range）

    def log_message(self, *args):
        pass

    def _write_slow(self, chunk: bytes):
        """分块写出，块间可插延迟（让「暂停」有足够时间窗口可观测）。"""
        if not self.block_delay:
            self.wfile.write(chunk)
            return
        step = 16 * 1024
        for i in range(0, len(chunk), step):
            self.wfile.write(chunk[i:i + step])
            self.wfile.flush()
            time.sleep(self.block_delay)

    def _count(self):
        with self.request_lock:
            self.requests.append((self.headers.get("Range"), self._fail))
            if self.fail_after is not None and len(self.requests) > self.fail_after:
                return True
        return False

    def do_GET(self):
        self._fail = False
        if self._count():
            self.send_response(500)
            self.end_headers()
            return
        rng = self.headers.get("Range")
        data = self.payload
        zero_only = _Handler.honor_zero_range_only
        if rng and self.support_range and zero_only:
            try:
                _start = int(rng.split("=", 1)[1].split("-", 1)[0] or 0)
            except ValueError:
                _start = 0
            if _start > 0:
                rng = None       # 强制走 200 整文件分支
        if rng and self.support_range:
            spec = rng.split("=", 1)[1]
            start_s, _, end_s = spec.partition("-")
            start = int(start_s)
            end = int(end_s) if end_s else len(data) - 1
            end = min(end, len(data) - 1)
            chunk = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range",
                             f"bytes {start}-{end}/{len(data)}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self._write_slow(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges",
                             "bytes" if self.support_range else "none")
            self.end_headers()
            self._write_slow(data)


def _start_server(payload: bytes, support_range: bool = True,
                  block_delay: float = 0.0,
                  honor_zero_range_only: bool = False):
    _Handler.payload = payload
    _Handler.support_range = support_range
    _Handler.requests = []
    _Handler.fail_after = None
    _Handler.block_delay = block_delay
    _Handler.honor_zero_range_only = honor_zero_range_only
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/file.bin"


def _stop_server(server):
    server.shutdown()
    server.server_close()


# ── 1. 分段规划 ───────────────────────────────────────────────────

def test_plan_segments_covers_whole_file():
    total = 10 * 1024 * 1024
    segs = dl.plan_segments(total, 8)
    assert len(segs) == 8
    assert segs[0].start == 0
    assert segs[-1].end == total - 1
    assert sum(s.length for s in segs) == total, "各段长度之和必须等于总长"
    for a, b in zip(segs, segs[1:]):
        assert a.end + 1 == b.start, "段必须首尾相接、不能有缝也不能重叠"


def test_plan_segments_small_file():
    """小文件**也**按线程数切细段：并发能把一个大请求变成多个小请求并行等。

    （早期实现按 MIN_CHUNK_SIZE 把小文件压成 1 段，等于放弃了并发 —— 已修正。）
    """
    segs = dl.plan_segments(1000, 16)
    assert len(segs) == 16, "小文件也应按线程数切段（并发才有意义）"
    assert sum(s.length for s in segs) == 1000
    assert segs[0].start == 0 and segs[-1].end == 999
    for a, b in zip(segs, segs[1:]):
        assert a.end + 1 == b.start


def test_plan_segments_zero():
    assert dl.plan_segments(0, 8) == []


def test_plan_segments_even_split():
    segs = dl.plan_segments(100, 4)
    assert len(segs) == 4
    assert [s.length for s in segs] == [25, 25, 25, 25]


def test_segment_helpers():
    seg = dl.Segment(index=0, start=0, end=99)
    assert seg.length == 100
    assert not seg.complete
    assert seg.range_header == "bytes=0-99"
    seg.done = 40
    assert seg.range_header == "bytes=40-99", "续传 Range 必须从已完成处继续"
    seg.done = 100
    assert seg.complete


# ── 2. 线程数选择 ────────────────────────────────────────────────

def test_thread_count_never_exceeds_32():
    for size in (1, 1 << 20, 1 << 30, 1 << 40):
        for limit in (None, 4, 16, 32, 64, 999):
            n = dl.choose_thread_count(size, limit)
            assert 1 <= n <= dl.MAX_THREADS, (size, limit, n)
            assert n <= dl.MAX_THREADS


def test_thread_count_respects_user_limit():
    assert dl.choose_thread_count(1 << 30, 8) <= 8
    assert dl.choose_thread_count(1 << 30, 32) <= 32


def test_thread_count_small_file_gets_few():
    n = dl.choose_thread_count(2 * 1024 * 1024, 32)
    assert n <= 2, "小文件不该开一堆线程（每段一个 HTTP 往返）"


def test_thread_count_zero_size():
    assert dl.choose_thread_count(0) == 1


# ── 3. 端到端 ─────────────────────────────────────────────────────

def test_multithreaded_download_matches_source():
    import tempfile

    data = bytes((i * 7 + 13) % 256 for i in range(3 * 1024 * 1024))
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            progress = []
            got = dl.download_multithreaded(
                url, dest, progress_cb=progress.append, max_threads=8)
            assert got.exists()
            assert got.read_bytes() == data, "下载字节必须与源完全一致"
            assert progress and progress[-1] == 100.0
            # 边车文件不残留
            assert not dest.with_name(dest.name + dl.PROGRESS_SUFFIX).exists()
            assert not dest.with_name(dest.name + dl.PART_SUFFIX).exists()
    finally:
        _stop_server(server)


def test_multithreaded_uses_range_requests():
    import tempfile

    data = os.urandom(4 * 1024 * 1024)
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            dl.download_multithreaded(url, dest, max_threads=8)
            ranges = [r for r in _Handler.requests if r[0]]
            assert ranges, "应当发起 Range 请求（分段下载）"
            assert len(ranges) > 1, "应当有多段并发请求"
    finally:
        _stop_server(server)


def test_progress_reported_incrementally():
    """进度必须**按字节**实时推进（不能等整段下完才报 —— 大文件会长时间「进度不动」）。"""
    import tempfile

    data = os.urandom(4 * 1024 * 1024)
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            seen = []
            dl.download_multithreaded(url, dest, progress_cb=seen.append,
                                      max_threads=8)
            assert len(seen) > 2, f"应有多次进度上报，实际 {len(seen)} 次"
            assert seen == sorted(seen), "进度必须单调递增"
            assert seen[-1] == 100.0
            # 中途的进度应落在 (0, 100) 之间，不能一上来就 100
            assert any(0 < p < 100 for p in seen), "应有中间态进度"
    finally:
        _stop_server(server)


def test_falls_back_to_single_stream_when_no_range():
    """服务端不认 Range（恒 200）时自动回落单流，结果仍正确。"""
    import tempfile

    data = b"A" * (2 * 1024 * 1024)
    server, url = _start_server(data, support_range=False)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            got = dl.download_multithreaded(url, dest, max_threads=8)
            assert got.read_bytes() == data
    finally:
        _stop_server(server)


# ── 4. 断点续传 ───────────────────────────────────────────────────

def test_resume_only_downloads_missing_segments():
    import tempfile

    data = os.urandom(5 * 1024 * 1024)
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            prog = dest.with_name(dest.name + dl.PROGRESS_SUFFIX)

            # 第一次：人为让第 3 段失败 ⇒ 留下部分进度
            _Handler.fail_after = 3
            try:
                dl.download_multithreaded(url, dest, max_threads=4)
            except dl.DownloadError:
                pass
            assert prog.exists(), "失败的下载应留下进度边车文件（供续传）"

            # 第二次：服务端正常 ⇒ 只补没下完的段
            _Handler.fail_after = None
            _Handler.requests = []
            got = dl.download_multithreaded(url, dest, max_threads=4, resume=True)
            assert got.read_bytes() == data, "续传后字节必须与源完全一致"
            assert not prog.exists(), "成功后应清理进度文件"
            # 续传时请求的段数应少于总段数（说明复用了已完成的部分）
            assert len(_Handler.requests) < 5, "续传不应重下所有段"
    finally:
        _stop_server(server)


def test_resume_disabled_restarts_from_scratch():
    import tempfile

    data = os.urandom(3 * 1024 * 1024)
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            dl.download_multithreaded(url, dest, max_threads=4, resume=False)
            _Handler.requests = []
            dl.download_multithreaded(url, dest, max_threads=4, resume=False)
            assert len(_Handler.requests) > 1, "resume=False 应重新下载"
            assert dest.read_bytes() == data
    finally:
        _stop_server(server)


def test_progress_file_invalidated_when_resource_changes():
    import json
    import tempfile

    data = os.urandom(2 * 1024 * 1024)
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            prog = dest.with_name(dest.name + dl.PROGRESS_SUFFIX)
            prog.write_text(json.dumps({
                "url": url, "total": 999999, "etag": "other",
                "done": {"0": 5},
            }), encoding="utf-8")
            dl.download_multithreaded(url, dest, max_threads=4, resume=True)
            assert dest.read_bytes() == data, "资源变了必须从头下，不能拼出错文件"
    finally:
        _stop_server(server)


def test_content_range_parse():
    assert dl._parse_content_range("bytes 0-0/12345") == (0, 0, 12345)
    assert dl._parse_content_range("bytes 100-199/200") == (100, 199, 200)
    assert dl._parse_content_range("bytes 0-0/*") == (0, 0, None)
    assert dl._parse_content_range("bytes 0-0") == (0, 0, None)
    assert dl._parse_content_range(None) is None
    for bad in ("", "items 0-0/10", "bytes a-b/10"):
        assert dl._parse_content_range(bad) is None, bad


def test_segment_response_self_check():
    """分段响应必须自证偏移与总长，否则宁可回落单流（R1 + R5）。"""
    plan = dl.DownloadPlan(url="u", total_size=1000, supports_range=True)
    plan.segments = dl.plan_segments(1000, 2)
    seg = plan.segments[1]              # start = 500
    assert seg.start == 500

    # 1) 200 整文件回来，但本段不是「唯一的 0 起点段」=> 不可分段
    try:
        dl._verify_segment_response(200, {}, seg, plan)
        raise AssertionError("200 必须被判为不可分段")
    except dl._RangeUnsupported:
        pass

    # 2) 206 但 Content-Range 起点不对 => 不可分段（绝不按错位偏移写）
    try:
        dl._verify_segment_response(206, {"Content-Range": "bytes 0-999/1000"}, seg, plan)
        raise AssertionError("偏移不符必须拒绝")
    except dl._RangeUnsupported:
        pass

    # 3) 206 但缺 Content-Range => 不可分段
    try:
        dl._verify_segment_response(206, {}, seg, plan)
        raise AssertionError("缺 Content-Range 必须拒绝")
    except dl._RangeUnsupported:
        pass

    # 4) 正确响应 => 通过
    dl._verify_segment_response(206, {"Content-Range": "bytes 500-999/1000"}, seg, plan)

    # 5) 总长变化 => 普通错误（不可重试，但不属于「不可分段」）
    try:
        dl._verify_segment_response(206, {"Content-Range": "bytes 500-999/2000"}, seg, plan)
        raise AssertionError("资源变化必须报错")
    except dl._RangeUnsupported:
        raise AssertionError("资源变化不应被判为不可分段")
    except dl.DownloadError:
        pass


def test_retry_delay_honours_retry_after():
    import email.message
    import urllib.error

    msg = email.message.Message()
    msg["Retry-After"] = "3"
    exc = urllib.error.HTTPError("http://x/", 429, "Too Many", msg, None)
    assert dl._retry_delay(exc, 0) == 3.0

    msg2 = email.message.Message()
    msg2["Retry-After"] = "9999"
    exc2 = urllib.error.HTTPError("http://x/", 503, "Unavail", msg2, None)
    assert dl._retry_delay(exc2, 0) == dl.RETRY_AFTER_MAX, "Retry-After 必须夹上限"

    plain = urllib.error.HTTPError("http://x/", 500, "err", msg, None)
    assert dl._retry_delay(plain, 1) == dl.RETRY_BACKOFF * 2


def test_auto_thread_count_is_default_not_max():
    """「自动」= DEFAULT_MAX_THREADS（16），不是 MAX_THREADS（32）。"""
    n = dl.choose_thread_count(1 << 30, None)
    assert n <= dl.DEFAULT_MAX_THREADS, (n, dl.DEFAULT_MAX_THREADS)
    assert dl.choose_thread_count(1 << 30, 32) > dl.DEFAULT_MAX_THREADS, \
        "显式配置 32 时应当多于默认值，说明两者确实不同"


def test_progress_file_invalidated_when_url_changes():
    """换了下载地址，旧的 done 计数必须全部作废（R4）。"""
    import json
    import tempfile

    plan = dl.DownloadPlan(url="http://a/new.exe", total_size=1000, supports_range=True)
    plan.segments = dl.plan_segments(1000, 2)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "p.json"
        path.write_text(json.dumps({
            "url": "http://a/old.exe",
            "total": 1000,
            "layout": {"0": [0, 500], "1": [0, 500]},
        }), encoding="utf-8")
        segs = dl._load_progress(path, plan)
        assert [s.done for s in segs] == [0, 0], "url 变了必须丢弃旧进度"


def test_single_stream_resumes_from_part():
    """单流也能续传：已有 .part 时发 ``Range: bytes=N-`` 追加写（R6）。"""
    import tempfile

    data = bytes((i * 11 + 5) % 256 for i in range(300 * 1024))
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            part = dest.with_name(dest.name + dl.PART_SUFFIX)
            part.write_bytes(data[:100 * 1024])
            got = dl._download_single_stream(
                url, dest, None, 30.0, {"User-Agent": dl.USER_AGENT})
            assert Path(got).read_bytes() == data, "续传结果必须逐字节一致"
            assert any((r[0] or "").startswith("bytes=102400")
                       for r in _Handler.requests), \
                f"应当发 Range=bytes=102400-，实际 {_Handler.requests[:3]}"
            assert not part.exists()
    finally:
        _stop_server(server)


def test_single_stream_restart_is_announced():
    """服务端不认 Range 时从头写，并且**明告**进度会重来（不是静默跳回 0）。"""
    import tempfile

    data = bytes((i * 3 + 7) % 256 for i in range(200 * 1024))
    server, url = _start_server(data, support_range=False)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            dest.with_name(dest.name + dl.PART_SUFFIX).write_bytes(data[:50 * 1024])
            seen = []
            got = dl._download_single_stream(
                url, dest, None, 30.0, {"User-Agent": dl.USER_AGENT},
                stats_cb=seen.append)
            assert Path(got).read_bytes() == data
            states = [s.state for s in seen]
            assert "restart" in states, f"应当发出 restart 状态，实际 {states[:5]}"
    finally:
        _stop_server(server)


def test_fallback_when_range_lost_mid_download():
    """中途丢 Range（非 0 起点一律 200）时回落单流，且**不产出错位文件**（R1）。"""
    import tempfile

    data = bytes((i * 5 + 1) % 256 for i in range(1024 * 1024))
    server, url = _start_server(data, honor_zero_range_only=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            got = dl.download_multithreaded(url, dest, max_threads=4)
            assert Path(got).read_bytes() == data, "回落单流后字节必须完全正确"
            assert not dest.with_name(dest.name + dl.PART_SUFFIX).exists()
    finally:
        _stop_server(server)


def test_cancel_returns_promptly():
    """取消必须限时返回，并默认清理缓存（R16 / AC13/AC14）。"""
    import tempfile

    data = bytes((i * 13 + 9) % 256 for i in range(2 * 1024 * 1024))
    server, url = _start_server(data, block_delay=0.02)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            control = dl.DownloadControl()
            threading.Timer(0.3, control.cancel).start()
            t0 = time.time()
            try:
                dl.download_multithreaded(url, dest, max_threads=4, control=control)
                raise AssertionError("取消后必须抛 DownloadCancelled")
            except dl.DownloadCancelled:
                pass
            elapsed = time.time() - t0
            assert elapsed < 5.0, f"取消耗时过长：{elapsed:.2f}s"
            assert not dest.exists(), "取消后不应产出目标文件"
            assert not dest.with_name(dest.name + dl.PART_SUFFIX).exists(), \
                "默认 on_cancel=clean 必须清掉 .part"
    finally:
        _stop_server(server)


def test_cancel_keep_leaves_resumable_part():
    """``on_cancel="keep"``（关窗口/退出程序）保留 .part 供下次续传（R15）。"""
    import tempfile

    data = bytes((i * 17 + 3) % 256 for i in range(2 * 1024 * 1024))
    server, url = _start_server(data, block_delay=0.02)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            control = dl.DownloadControl()
            threading.Timer(0.3, control.cancel).start()
            try:
                dl.download_multithreaded(url, dest, max_threads=4,
                                          control=control, on_cancel="keep")
                raise AssertionError("取消后必须抛 DownloadCancelled")
            except dl.DownloadCancelled:
                pass
            part = dest.with_name(dest.name + dl.PART_SUFFIX)
            assert part.exists() and part.stat().st_size > 0, \
                "keep 模式下 .part 必须保留"
            assert not dest.exists()
    finally:
        _stop_server(server)


# ── 5. 暂停 / 继续 / 取消（端到端，慢速服务端） ──────────────────

def test_pause_then_resume_completes_correctly():
    """暂停后字节保留、继续后从断点接着下，最终与源**逐字节一致**。

    用「每 16 KB 延迟 5 ms」的慢速服务端制造可观测的暂停窗口。
    """
    import tempfile

    data = os.urandom(2 * 1024 * 1024)
    server, url = _start_server(data, block_delay=0.005)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            control = dl.DownloadControl()
            seen = []
            result = {}

            def run():
                try:
                    dl.download_multithreaded(
                        url, dest, max_threads=4, control=control,
                        stats_cb=lambda p: seen.append(p))
                    result["done"] = True
                except Exception as exc:          # noqa: BLE001
                    result["error"] = exc

            t = threading.Thread(target=run, daemon=True)
            t.start()
            # 等它真的下起来（有进度），再暂停
            deadline = time.time() + 10
            while time.time() < deadline:
                if seen and seen[-1].completed_bytes > 200 * 1024:
                    break
                time.sleep(0.05)
            control.pause()
            t.join(timeout=15)
            assert not t.is_alive(), "暂停后下载线程应能退出（不能卡住）"
            assert "error" not in result, f"暂停不应报错：{result.get('error')}"
            assert control.paused
            # 暂停时目标文件不该存在（只有 .part）
            assert not dest.exists(), "暂停时不得产出目标文件"
            part = dest.with_name(dest.name + dl.PART_SUFFIX)
            assert part.exists(), "暂停后应保留 .part（供续传）"
            paused_bytes = dl.partial_size(dest)
            assert 0 < paused_bytes <= len(data)

            # 继续：恢复速率并跑完
            _Handler.block_delay = 0.0
            control.resume()
            dl.download_multithreaded(url, dest, max_threads=4,
                                      control=control, resume=True)
            assert dest.read_bytes() == data, "续传后字节必须与源完全一致"
            assert not part.exists(), "完成后应清理 .part"
    finally:
        _stop_server(server)


def test_cancel_raises_and_cleans_cache():
    """取消必须抛 DownloadCancelled，并把 .part / 进度文件**都清理掉**。"""
    import tempfile

    data = os.urandom(2 * 1024 * 1024)
    server, url = _start_server(data, block_delay=0.005)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            control = dl.DownloadControl()
            seen = []
            caught = {}

            def run():
                try:
                    dl.download_multithreaded(
                        url, dest, max_threads=4, control=control,
                        stats_cb=lambda p: seen.append(p))
                except Exception as exc:          # noqa: BLE001
                    caught["exc"] = exc

            t = threading.Thread(target=run, daemon=True)
            t.start()
            deadline = time.time() + 10
            while time.time() < deadline:
                if seen and seen[-1].completed_bytes > 200 * 1024:
                    break
                time.sleep(0.05)
            control.cancel()
            t.join(timeout=15)
            assert not t.is_alive(), "取消后下载线程应能退出"

            assert isinstance(caught.get("exc"), dl.DownloadCancelled), \
                f"应抛 DownloadCancelled，实际 {caught.get('exc')!r}"
            assert not dest.exists(), "取消后不得产出目标文件"
            assert dl.partial_size(dest) == 0, "取消后必须清理 .part 缓存"
            assert not dest.with_name(
                dest.name + dl.PROGRESS_SUFFIX).exists(), "取消后必须清理进度文件"
    finally:
        _stop_server(server)


def test_cancel_works_on_single_stream_fallback():
    """**服务端不支持 Range 时**，取消也必须生效（否则点取消毫无反应）。"""
    import tempfile

    data = os.urandom(3 * 1024 * 1024)
    server, url = _start_server(data, support_range=False, block_delay=0.005)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            control = dl.DownloadControl()
            caught = {}

            def run():
                try:
                    dl.download_multithreaded(url, dest, control=control)
                except Exception as exc:      # noqa: BLE001
                    caught["exc"] = exc

            t = threading.Thread(target=run, daemon=True)
            t.start()
            time.sleep(0.6)                   # 给它下起来
            control.cancel()
            t.join(timeout=15)
            assert not t.is_alive(), "单流模式下取消也应能让线程退出"
            assert isinstance(caught.get("exc"), dl.DownloadCancelled), \
                f"单流模式应抛 DownloadCancelled，实际 {caught.get('exc')!r}"
            assert dl.partial_size(dest) == 0, "单流取消后也要清理 .part"
    finally:
        _stop_server(server)


def test_cancel_before_start():
    """一开始就处于取消态 ⇒ 立刻抛 DownloadCancelled，不发请求。"""
    import tempfile

    data = os.urandom(1024)
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            control = dl.DownloadControl()
            control.cancel()
            try:
                dl.download_multithreaded(url, Path(tmp) / "o.bin", control=control)
            except dl.DownloadCancelled:
                pass
            else:
                raise AssertionError("取消态应立刻抛 DownloadCancelled")
            assert not _Handler.requests, "取消态不应发起任何请求"
    finally:
        _stop_server(server)


# ── 6. 失败路径 ───────────────────────────────────────────────────

def test_failed_download_leaves_no_target_file():
    """全部请求失败时必须抛错，且**目标文件不出现**（绝不留半截 exe）。"""
    import tempfile

    data = os.urandom(2 * 1024 * 1024)
    server, url = _start_server(data)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            _Handler.fail_after = 0        # 立即开始全部 500
            try:
                dl.download_multithreaded(url, dest, max_threads=4)
            except dl.DownloadError:
                pass
            else:
                raise AssertionError("应当抛 DownloadError")
            assert not dest.exists(), "失败时不得产出目标文件"
    finally:
        _stop_server(server)


def test_probe_size_reports_range_support():
    data = os.urandom(1024)
    server, url = _start_server(data)
    try:
        total, supports, etag, lm = dl.probe_size(url)
        assert total == len(data)
        assert supports is True
    finally:
        _stop_server(server)

    server2, url2 = _start_server(data, support_range=False)
    try:
        total2, supports2, _, _ = dl.probe_size(url2)
        assert supports2 is False, "不支持 Range 时必须如实报告"
    finally:
        _stop_server(server2)


# ── 6. 合并校验 ───────────────────────────────────────────────────

def test_merge_detects_short_file():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        part = Path(tmp) / "x.bin.part"
        dest = Path(tmp) / "x.bin"
        part.write_bytes(b"12345")            # 故意短
        plan = dl.DownloadPlan(url="u", total_size=100,
                                segments=[dl.Segment(0, 0, 99)])
        try:
            dl._merge_segments(part, dest, plan)
        except dl.DownloadError:
            pass
        else:
            raise AssertionError("短文件合并必须失败")
        assert not dest.exists(), "合并失败不得产出目标文件"


def test_merge_writes_correct_bytes():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        part = Path(tmp) / "x.bin.part"
        dest = Path(tmp) / "x.bin"
        data = b"0123456789"
        part.write_bytes(data)
        plan = dl.DownloadPlan(url="u", total_size=10,
                               segments=[dl.Segment(0, 0, 9)])
        dl._merge_segments(part, dest, plan)
        assert dest.read_bytes() == data


# ── 7. 与 auto_updater 衔接 ──────────────────────────────────────

def test_opdater_uses_multithreaded_downloader():
    """Opdater.download 必须走多线程下载器（不再单流）。"""
    import auto_updater

    src = (Path(__file__).resolve().parent.parent / "auto_updater.py").read_text(
        encoding="utf-8")
    assert "download_multithreaded" in src, "Opdater 未接入多线程下载器"
    assert hasattr(auto_updater, "Opdater")


def test_pe_guard_still_active():
    """多线程下载不得削弱 PE 魔数兜底（AGENTS §8 陷阱 82 的最后一道闸）。"""
    import auto_updater

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.exe"
        bad.write_bytes(b'{"message":"Not Found"}')
        assert not auto_updater.is_pe_executable(bad)
        good = Path(tmp) / "good.exe"
        good.write_bytes(b"MZ" + b"\x00" * 2000)
        assert auto_updater.is_pe_executable(good)


def test_downloader_module_in_hiddenimports():
    """打包清单必须含 downloader（函数级 import，静态分析扫不到）。"""
    meta = Path(__file__).resolve().parent.parent / "pyinstaller_meta.py"
    text = meta.read_text(encoding="utf-8")
    assert "downloader" in text, "downloader 未登记进 spec hiddenimports"


# ── 8. GUI 接线（线程数配置贯通到 worker） ────────────────────────

def test_resolve_download_threads():
    """「更新设置 → 下载线程」的取值口径：0/缺省=自动，非法夹到 1..32。"""
    import main_gui

    fn = main_gui._resolve_download_threads
    assert fn({}) is None, "缺省应为自动"
    assert fn({"download_threads": 0}) is None, "0 应为自动"
    assert fn({"download_threads": 8}) == 8
    assert fn({"download_threads": 32}) == 32
    assert fn({"download_threads": 99}) == 32, "越界应夹到上限 32"
    assert fn({"download_threads": -5}) is None, "负数应为自动"
    assert fn({"download_threads": "abc"}) is None, "非法值应为自动"
    assert fn(None) is None


def test_update_config_knows_download_threads():
    """默认更新配置里要有 download_threads（0=自动）。"""
    import auto_updater

    assert "download_threads" in auto_updater.DEFAULT_UPDATE_CONFIG
    assert auto_updater.DEFAULT_UPDATE_CONFIG["download_threads"] == 0
    merged = auto_updater.merge_update_config({"download_threads": 16})
    assert merged["download_threads"] == 16, "用户配置必须能覆盖默认值"


def test_update_settings_dialog_has_threads_combo():
    """「更新设置」对话框里必须有「下载线程」下拉（且含 32 线程档）。"""
    import main_gui

    # 顺带守卫：改完下载器/面板后主程序仍能正常导入
    assert callable(main_gui._resolve_download_threads)
    src = (Path(__file__).resolve().parent.parent / "main_gui.py").read_text(
        encoding="utf-8")
    assert "下载线程" in src
    assert "32 线程" in src
    assert "_resolve_download_threads" in src


def test_opdater_accepts_max_threads():
    """Opdater 必须把 max_threads 透传给下载器。"""
    import auto_updater

    op = auto_updater.Opdater(max_threads=24)
    assert op.max_threads == 24
    # 默认（不传）= None = 自适应
    assert auto_updater.Opdater().max_threads is None


def test_disk_error_is_readable():
    """R7/AC7：`OSError(ENOSPC)` 必须翻成含「磁盘空间」的中文，不把英文原文抛给用户。"""
    import errno

    import downloader

    msg = downloader._describe_os_error(OSError(errno.ENOSPC, "No space left"), 5 << 20)
    assert "磁盘空间不足" in msg, msg
    assert "5.0 MB" in msg or "5 MB" in msg, msg        # 告诉用户需要多少
    # 其它 OSError 也要给可读前缀（不能只 str(exc)）
    assert "无法读写临时文件" in downloader._describe_os_error(OSError(13, "denied"))


def run_all():
    tests = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
