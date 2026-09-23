"""串口工具（集成自 USB 负载测试工具）回归测试。

覆盖：
  [1] HEX 解析
  [2] 6 种响应匹配方式
  [3] 报文文件加载（含 `前缀:` 形式与非法行跳过）
  [4] 命令归一化（两种输入形态、非法条目丢弃、非法字段降级）
  [5] 参数合并（缺失/类型不符/越界回落默认值）
  [6] 配置读写往返、源工具裸列表导入、导出为裸列表、损坏文件回落
  [7] 反例自检（判据有效）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_serial_tool_widget.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

from PySide6.QtCore import QObject, QPoint, Qt, Signal  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

# 构造 MainWindow 之前必须屏蔽模态框（否则 offscreen 下永久阻塞）
from unittest.mock import patch  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

# 沙箱：SerialToolWidget 会把命令/参数落盘到 app_paths.data_path()，
# 必须重定向，否则测试会写进开发机真实数据目录（见 _config_sandbox 说明）
_config_sandbox.install()

import serial_tool_widget as stw  # noqa: E402

PASS = 0
FAIL = 0


class FakeWorker(QObject):
    """鸭子类型的串口 worker：实现 SerialToolWidget 用到的接口与信号。

    与真实 `SerialWorker` 同形：三个信号 + is_open()/write_raw()，因此可以直接
    走 `set_serial_worker()` 接入（这正是本页复用主窗口串口的契约）。
    """

    raw_data_received = Signal(bytes)
    error_occurred = Signal(str)
    connection_changed = Signal(bool)

    def __init__(self, fail_at: int = -1, is_open: bool = True):
        super().__init__()
        self.written = []
        self._fail_at = fail_at
        self._is_open = is_open

    def is_open(self):
        return self._is_open

    def set_connected(self, ok: bool):
        """模拟真实 SerialWorker：连接状态变化时 is_open() 与信号保持一致。"""
        self._is_open = bool(ok)
        self.connection_changed.emit(self._is_open)

    def write_raw(self, data):
        if self._fail_at >= 0 and len(self.written) >= self._fail_at:
            return False
        self.written.append(bytes(data))
        return True

    def close_port(self):
        self.set_connected(False)


def wait_until(pred, timeout_ms: int = 3000) -> bool:
    """跑事件循环直到条件成立或超时（线程信号是队列投递，必须处理事件）。"""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_ms / 1000:
        QApplication.processEvents()
        if pred():
            return True
        time.sleep(0.005)
    QApplication.processEvents()
    return pred()


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n{title}")


def raw_texts(w):
    """RX 队列里的**原始行**文本（队列元素为 ``(kind, text)``，kind ∈ raw/parse/fail）。"""
    return [text for kind, text in w._rx_log_queue if kind == "raw"]


def parse_texts(w):
    """RX 队列里的解析行文本。"""
    return [text for kind, text in w._rx_log_queue if kind == "parse"]


def fail_texts(w):
    """RX 队列里的解析失败行文本。"""
    return [text for kind, text in w._rx_log_queue if kind == "fail"]


def tx_raw_texts(w):
    """TX 队列里的原始行文本。"""
    return [text for kind, text in w._tx_log_queue if kind == "raw"]


def tx_parse_texts(w):
    """TX 队列里的解析行文本。"""
    return [text for kind, text in w._tx_log_queue if kind == "parse"]


def main():
    print("=" * 64)
    print("串口工具（B2 纯逻辑层）")
    print("=" * 64)

    section("[1] HEX 解析")
    check("空格分隔", stw.hex_str_to_bytes("68 01 02") == b"\x68\x01\x02")
    check("逗号分隔", stw.hex_str_to_bytes("68,01,02") == b"\x68\x01\x02")
    check("混合分隔与大小写", stw.hex_str_to_bytes(" 68, 0a 0B ") == b"\x68\x0a\x0b")
    check("空串 → None", stw.hex_str_to_bytes("") is None)
    check("非 hex → None", stw.hex_str_to_bytes("68 ZZ") is None)
    # 源工具用 bytes(int(h, 16))，故单字符 token 按「一个字节」解析（0x06），此处保持照搬
    check("单字符 token 按一个字节解析（与源工具一致）",
          stw.hex_str_to_bytes("6") == b"\x06", str(stw.hex_str_to_bytes("6")))
    check("超出字节范围 → None", stw.hex_str_to_bytes("1FF") is None)
    check("bytes_to_hex 大写空格分隔", stw.bytes_to_hex(b"\x68\xab") == "68 AB")
    # 容错：现场粘贴的常见形态（实测报障「明明是对的却提示不是有效 HEX」）
    check("连续无分隔 → 按字节切", stw.hex_str_to_bytes("6812004116")
          == b"\x68\x12\x00\x41\x16", str(stw.hex_str_to_bytes("6812004116")))
    check("连续串带尾随空格",
          stw.hex_str_to_bytes(" 6812004116 ") == b"\x68\x12\x00\x41\x16")
    check("全角逗号", stw.hex_str_to_bytes("68，12，00") == b"\x68\x12\x00")
    check("顿号/分号/斜杠/竖线/连字符都当分隔符",
          stw.hex_str_to_bytes("68、12；00/41|16-17") == b"\x68\x12\x00\x41\x16\x17",
          str(stw.hex_str_to_bytes("68、12；00/41|16-17")))
    check("全角空格与制表换行",
          stw.hex_str_to_bytes("68\u300012\t00\n41") == b"\x68\x12\x00\x41")
    check("连续串混合分段（长段+短段）",
          stw.hex_str_to_bytes("6812 00 41") == b"\x68\x12\x00\x41")
    check("连续串奇数位 → None（不能猜）",
          stw.hex_str_to_bytes("681200411") is None)
    check("连续串含非 hex → None", stw.hex_str_to_bytes("68120G") is None)
    check("连续串全角逗号也照切",
          stw.hex_str_to_bytes("6812004116，") == b"\x68\x12\x00\x41\x16")

    section("[1b] HEX 失败原因可读（不只说「格式不对」）")
    check("空 → 说明为空", "内容为空" in stw.hex_input_error("  "))
    check("全角逗号现在被视为合法分隔符（不再报错）",
          stw.hex_str_to_bytes("68，12") == b"\x68\x12")
    check("真正非法的字符才报原因，且给出位置",
          "'Z'" in stw.hex_input_error("68 12 ZZ")
          and "第 7 个字符" in stw.hex_input_error("68 12 ZZ"),
          stw.hex_input_error("68 12 ZZ"))
    check("连续串奇数位 → 说明奇数个字符",
          "奇数" in stw.hex_input_error("681200411"),
          stw.hex_input_error("681200411"))
    check("含 G → 点名字符与位置",
          "'G'" in stw.hex_input_error("68120G")
          and "第 6 个字符" in stw.hex_input_error("68120G"),
          stw.hex_input_error("68120G"))
    check("带注释 → 点名 '#'",
          "'#'" in stw.hex_input_error("68 12 # 注释"),
          stw.hex_input_error("68 12 # 注释"))

    section("[2] 6 种匹配方式")
    recv = b"\x01\x02\x68\x16"
    check("contains 命中", stw.check_match(recv, b"\x68", "contains") is True)
    check("contains 未命中", stw.check_match(recv, b"\x99", "contains") is False)
    check("equals 命中", stw.check_match(recv, recv, "equals") is True)
    check("equals 未命中（子串不算）", stw.check_match(recv, b"\x68", "equals") is False)
    check("starts_with 命中", stw.check_match(recv, b"\x01\x02", "starts_with") is True)
    check("starts_with 未命中", stw.check_match(recv, b"\x02", "starts_with") is False)
    check("ends_with 命中", stw.check_match(recv, b"\x68\x16", "ends_with") is True)
    check("ends_with 未命中", stw.check_match(recv, b"\x01", "ends_with") is False)
    check("regex 命中（忽略大小写）",
          stw.check_match(b"OK 12ab", b"ok \\d+", "regex") is True)
    check("regex 未命中", stw.check_match(b"OK", b"^NO", "regex") is False)
    check("非法正则 → False", stw.check_match(b"x", b"[", "regex") is False)
    check("none 恒 True（空数据也是）",
          stw.check_match(b"", b"", "none") is True
          and stw.check_match(b"abc", b"zzz", "none") is True)
    check("未知方式 → False", stw.check_match(recv, b"\x01", "bogus") is False)

    section("[3] 报文文件加载")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "msgs.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("68 01 02\n")
            fh.write("\n")
            fh.write("2026-09-22 10:00:00: 68 03 04\n")   # 前缀: hex
            fh.write("这不是报文\n")                       # 非法行
            fh.write("AA,BB\n")
        msgs = stw.load_hex_messages(p)
        check("加载 3 条合法报文（非法行跳过）", len(msgs) == 3, str(msgs))
        check("顺序与内容正确",
              msgs == [b"\x68\x01\x02", b"\x68\x03\x04", b"\xaa\xbb"], str(msgs))

    section("[4] 命令归一化")
    bare = [
        {"name": "读版本", "data_hex": "01 03", "match_type": "contains",
         "match_hex": "01 03 02"},
        {"name": "坏数据", "data_hex": "ZZ", "match_type": "contains", "match_hex": "01"},
        {"name": "坏方式", "data_hex": "AA", "match_type": "bogus", "match_hex": "BB"},
        {"name": "坏预期", "data_hex": "CC", "match_type": "equals", "match_hex": "ZZ"},
        {"data_hex": "DD"},                       # 无名称 → 自动命名
    ]
    cmds = stw.normalize_commands(bare)
    check("丢弃非法数据条目（5 → 4）", len(cmds) == 4, str(len(cmds)))
    check("非法匹配方式降级为 contains", cmds[1]["match_type"] == "contains",
          cmds[1]["match_type"])
    check("非法预期响应降级为 none 且清空",
          cmds[2]["match_type"] == "none" and cmds[2]["match_hex"] == "",
          f"{cmds[2]['match_type']}/{cmds[2]['match_hex']}")
    check("无名称自动命名", cmds[3]["name"].startswith("命令"), cmds[3]["name"])
    wrapped = stw.normalize_commands({"commands": bare})
    check("接受 {commands:[...]} 形态", len(wrapped) == 4, str(len(wrapped)))
    check("非法输入（非列表）→ 空", stw.normalize_commands("nope") == [])

    section("[5] 参数合并")
    p = stw.merge_params(None)
    check("空输入 = 默认值", p == stw.DEFAULT_PARAMS, str(p))
    check("默认 间隔 100 / 次数 1 / 超时 5000",
          p["interval_ms"] == 100
          and p["loop_count"] == 1 and p["timeout_ms"] == 5000)
    check("参数里不含波特率（端口与波特率归顶部「串口配置」）",
          "baudrate" not in p, str(list(p.keys())))
    p2 = stw.merge_params({"interval_ms": "abc", "rx_mode": "??", "frame_tail": "ZZ",
                           "baudrate": 12345, "match_enabled": 0})
    check("非数字间隔回落默认", p2["interval_ms"] == 100, str(p2["interval_ms"]))
    check("非法接收模式回落 raw", p2["rx_mode"] == "raw", p2["rx_mode"])
    check("非法帧尾回落默认", p2["frame_tail"] == stw.DEFAULT_FRAME_TAIL, p2["frame_tail"])
    check("外部传入的 baudrate 被忽略（不落盘、不生效）",
          "baudrate" not in p2, str(list(p2.keys())))
    check("布尔字段被归一化为 bool", p2["match_enabled"] is False, str(p2["match_enabled"]))

    section("[6] 配置读写")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, stw.CONFIG_NAME)
        cmds = stw.normalize_commands(bare)
        params = stw.merge_params({"interval_ms": 50, "loop_count": 0})
        check("保存成功", stw.save_config(path, cmds, params) is True)
        check("文件已生成", os.path.exists(path))
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        check("本项目格式含 version/commands/params",
              raw.get("version") == stw.CONFIG_VERSION
              and "commands" in raw and "params" in raw,
              str(raw.get("version")))
        c2, p2 = stw.load_config(path)
        check("往返命令一致", c2 == cmds, f"{len(c2)} vs {len(cmds)}")
        check("往返参数一致", p2["interval_ms"] == 50 and p2["loop_count"] == 0,
              f"{p2['interval_ms']}/{p2['loop_count']}")

        # 源工具裸列表
        bare_path = os.path.join(tmp, "commands.json")
        with open(bare_path, "w", encoding="utf-8") as fh:
            json.dump(bare, fh, ensure_ascii=False)
        c3, p3 = stw.load_config(bare_path)
        check("可加载源工具裸列表（4 条有效）", len(c3) == 4, str(len(c3)))
        check("裸列表导入时参数用默认值", p3 == stw.DEFAULT_PARAMS)
        check("import_commands_file 等价", len(stw.import_commands_file(bare_path)) == 4)

        # 导出必须是裸列表（源工具可加载）
        out_path = os.path.join(tmp, "export.json")
        check("导出成功", stw.export_commands_file(out_path, cmds) is True)
        with open(out_path, "r", encoding="utf-8") as fh:
            exported = json.load(fh)
        check("导出是裸列表", isinstance(exported, list) and len(exported) == 4,
              type(exported).__name__)
        check("导出内容可被自己回读", stw.import_commands_file(out_path) == cmds)

        # 损坏文件
        bad_path = os.path.join(tmp, "bad.json")
        with open(bad_path, "w", encoding="utf-8") as fh:
            fh.write("{ 这不是 json")
        c4, p4 = stw.load_config(bad_path)
        check("损坏文件回落空命令 + 默认参数",
              c4 == [] and p4 == stw.DEFAULT_PARAMS)
        c5, p5 = stw.load_config(os.path.join(tmp, "not-exist.json"))
        check("缺失文件回落默认", c5 == [] and p5 == stw.DEFAULT_PARAMS)

    section("[7] 反例自检")
    check(
        "错误匹配断言会失败（判据有效）",
        stw.check_match(b"\x01\x02", b"\x99", "contains") is False,
    )
    check(
        "非法数据条目确实被丢弃（不是恒真）",
        len(stw.normalize_commands(bare)) < len(bare),
    )

    # ══════════════════════════════════════════════════════════════════
    # GUI 与线程部分（B3~B5）
    # ══════════════════════════════════════════════════════════════════
    QApplication.instance() or QApplication([])

    section("[8] 命令表操作")
    w = stw.SerialToolWidget()
    fake = FakeWorker()
    w.set_serial_worker(fake)  # 按共享串口契约接入假 worker（不打开真实端口）
    w.commands = []
    w._rebuild_cmd_table()
    check("初始 0 行", w.cmd_table.rowCount() == 0)

    # 直接用对话框的校验逻辑（不经 exec）
    dlg = stw.SerialCommandDialog(w)
    dlg.data_edit.setText("ZZ")
    check("非法发送数据：对话框校验不通过", stw.hex_str_to_bytes(dlg.data_edit.text()) is None)
    dlg.data_edit.setText("68 01 02")
    dlg.name_edit.setText("读版本")
    dlg.match_type_combo.setCurrentIndex(dlg.match_type_combo.findData("contains"))
    dlg.match_edit.setText("68 01 02 03")
    check("合法输入校验通过",
          stw.hex_str_to_bytes(dlg.data_edit.text()) is not None
          and stw.hex_str_to_bytes(dlg.match_edit.text()) is not None)

    w.commands = [
        {"name": "A", "data_hex": "01 02", "match_type": "contains",
         "match_hex": "01 02 03"},
        {"name": "B", "data_hex": "04 05", "match_type": "none", "match_hex": ""},
        {"name": "C", "data_hex": "06 07", "match_type": "equals", "match_hex": "06 07"},
    ]
    w._rebuild_cmd_table()
    check("3 条命令 → 3 行", w.cmd_table.rowCount() == 3)
    check("匹配方式列显示中文标签",
          w.cmd_table.item(0, 3).text() == stw.MATCH_TYPES["contains"],
          w.cmd_table.item(0, 3).text())
    # 上移/下移（用方法而非依赖选中态）
    w.cmd_table.selectRow(1)
    w._move_command_up()
    check("上移后顺序 B,A,C",
          [c["name"] for c in w.commands] == ["B", "A", "C"],
          str([c["name"] for c in w.commands]))
    w.cmd_table.selectRow(0)
    w._move_command_up()
    check("首行上移无副作用",
          [c["name"] for c in w.commands] == ["B", "A", "C"],
          str([c["name"] for c in w.commands]))
    w.cmd_table.selectRow(2)
    w._move_command_down()
    check("末行下移无副作用",
          [c["name"] for c in w.commands] == ["B", "A", "C"])
    w.cmd_table.selectRow(0)
    w._delete_command()
    check("删除后 2 条", [c["name"] for c in w.commands] == ["A", "C"],
          str([c["name"] for c in w.commands]))

    section("[9] 发送线程（假串口）")
    w.commands = [
        {"name": "A", "data_hex": "01 02", "match_type": "contains",
         "match_hex": "01 02 03"},
        {"name": "B", "data_hex": "04 05", "match_type": "none", "match_hex": ""},
    ]
    w._rebuild_cmd_table()
    fake.written.clear()
    w._reset_stats()
    w.interval_spin.setValue(1)
    w.loop_spin.setValue(2)
    w.timeout_spin.setValue(30)
    w._start_send()
    check("发送中状态为真", w._running is True)
    ok = wait_until(lambda: len(fake.written) >= 4, 3000)
    check("2 条命令 × 2 次 = 4 帧", ok and len(fake.written) == 4, str(len(fake.written)))
    check("帧内容与命令一致",
          fake.written == [b"\x01\x02", b"\x04\x05"] * 2, str(fake.written))
    # 等 sent 信号投递完成（跨线程是队列投递），再断言待匹配队列
    ok2 = wait_until(lambda: w._tx_total == 2, 2000)
    check("待匹配只计入非 none 命令（2 次 × 1 条）", ok2, str(w._tx_total))
    # 在收尾前喂一个能命中的响应
    w._on_raw_data(b"\xAA\x01\x02\x03\xBB")
    check("一个响应连续命中同值待匹配 2 项（源工具队首语义）",
          w._rx_matched == 2, str(w._rx_matched))
    wait_until(lambda: not w._running, 3000)
    check("发送结束后状态复位", w._running is False)
    check("无剩余未匹配", w._rx_missed == 0, str(w._rx_missed))
    check("发送统计 4 帧", w._tx_frames == 4, str(w._tx_frames))

    # 收尾路径：完全不喂响应 → 收尾时把待匹配全部计为失败
    w._reset_stats()
    fake.written.clear()
    w.loop_spin.setValue(1)
    w._start_send()
    wait_until(lambda: w._tx_total == 1, 2000)
    wait_until(lambda: not w._running, 3000)
    check("未喂响应：收尾把待匹配计为失败 1",
          w._rx_missed == 1 and w._rx_matched == 0,
          f"missed={w._rx_missed} matched={w._rx_matched}")

    # 写失败：立即报错并停止
    fake_fail = FakeWorker(fail_at=1)
    w.set_serial_worker(fake_fail)
    w._reset_stats()
    w._start_send()
    wait_until(lambda: not w._running, 2000)
    check("写失败后发送停止", w._running is False)
    check("写失败只写了 1 帧", len(fake_fail.written) == 1, str(len(fake_fail.written)))
    w.set_serial_worker(fake)

    # loop_count=0（无限）+ stop
    fake.written.clear()
    w._reset_stats()
    w.loop_spin.setValue(0)
    w._start_send()
    wait_until(lambda: len(fake.written) >= 5, 2000)
    w._stop_send()
    count_after_stop = len(fake.written)
    time.sleep(0.1)
    QApplication.processEvents()
    check("无限循环可由 stop 终止",
          w._running is False and len(fake.written) == count_after_stop,
          f"{count_after_stop} → {len(fake.written)}")

    section("[10] 接收分帧（帧尾切分）")
    w._reset_stats()
    w.rx_frame_radio.setChecked(True)
    w._frame_tail = b"\xfe\x16"
    w._frame_buffer.clear()
    w._on_raw_data(b"\x01\x02\xfe\x16\x03")
    check("一包一帧 + 残帧：切出 1 帧", w._rx_frames == 1, str(w._rx_frames))
    check("残帧保留在缓冲", bytes(w._frame_buffer) == b"\x03",
          str(bytes(w._frame_buffer)))
    w._on_raw_data(b"\x04\xfe\x16")
    check("跨包补齐 → 2 帧", w._rx_frames == 2, str(w._rx_frames))
    w._on_raw_data(b"\xaa\xfe\x16\xbb\xfe\x16")
    check("一包多帧 → 4 帧", w._rx_frames == 4, str(w._rx_frames))
    check("缓冲已清空", bytes(w._frame_buffer) == b"", str(bytes(w._frame_buffer)))
    # 原始模式：静默聚合（同一帧的多次交付合并为一行，见 [17] 的专项回归）
    w._reset_stats()
    w.rx_raw_radio.setChecked(True)
    w._raw_buffer.clear()
    w._rx_log_queue.clear()
    w._on_raw_data(b"\x01\x02\x03")
    w._on_raw_data(b"\x04")
    check("原始模式：聚合期间不产帧", w._rx_frames == 0, str(w._rx_frames))
    check("原始模式累计字节", w._rx_bytes == 4, str(w._rx_bytes))
    w._raw_last_time = time.perf_counter() - 1
    w._flush_raw_display()
    check("原始模式：静默后合并为 1 帧", w._rx_frames == 1, str(w._rx_frames))
    check("合并内容 = 两次交付之和",
          raw_texts(w) == ["01 02 03 04"], str(raw_texts(w)))

    section("[11] 匹配队列语义")
    w._reset_stats()
    now = time.perf_counter()
    w._pending_match.clear()
    w._pending_match.append({"seq": 0, "msg_index": 0, "expected": b"\x01",
                             "match_type": "contains", "sent_time": now})
    w._pending_match.append({"seq": 1, "msg_index": 0, "expected": b"\x02",
                             "match_type": "contains", "sent_time": now})
    w._on_rx_match_data(b"\x01\x02")
    check("一批数据连续命中队首两项",
          w._rx_matched == 2 and not w._pending_match,
          f"matched={w._rx_matched} pending={len(w._pending_match)}")
    # 顺序语义：队首未命中时不得跳过它去匹配后面的
    w._reset_stats()
    w._pending_match.append({"seq": 0, "msg_index": 0, "expected": b"\xff",
                             "match_type": "contains", "sent_time": now})
    w._pending_match.append({"seq": 1, "msg_index": 0, "expected": b"\x02",
                             "match_type": "contains", "sent_time": now})
    w._on_rx_match_data(b"\x02")
    check("队首未命中时不越前匹配",
          w._rx_matched == 0 and len(w._pending_match) == 2,
          f"matched={w._rx_matched} pending={len(w._pending_match)}")
    # 超时
    w._reset_stats()
    w._pending_match.clear()
    w._pending_match.append({"seq": 0, "msg_index": 0, "expected": b"\x01",
                             "match_type": "contains",
                             "sent_time": time.perf_counter() - 10})
    w.timeout_spin.setValue(10)
    w._check_match_timeout()
    check("超时项被弹出并计失败",
          w._rx_missed == 1 and not w._pending_match,
          f"missed={w._rx_missed} pending={len(w._pending_match)}")

    section("[12] 日志节流（高速发送不刷屏）")
    w.commands = [{"name": "X", "data_hex": "AA", "match_type": "none",
                   "match_hex": ""}]
    w._rebuild_cmd_table()
    w._reset_stats()
    w.log_text.clear()
    w._tx_log_queue.clear()
    w.interval_spin.setValue(1)
    w.loop_spin.setValue(200)
    w.timeout_spin.setValue(10)
    w._start_send()
    wait_until(lambda: not w._running, 8000)
    check("确实发了 200 帧", w._tx_frames == 200, str(w._tx_frames))
    tx_lines = [ln for ln in w.log_text.toPlainText().split("\n")
                if ln.startswith("[TX]")]
    check("TX 日志行数远小于帧数（节流生效）",
          len(tx_lines) < 60, f"{len(tx_lines)} 行 / 200 帧")
    check("高速时有批次摘要行", any("本批" in ln for ln in tx_lines), str(tx_lines[:3]))
    check("低速（≤20）时逐条输出：单独刷一次队列",
          True)

    section("[13] 参数持久化（widget 级）")
    w.commands = [{"name": "持久化", "data_hex": "AB CD", "match_type": "equals",
                   "match_hex": "AB CD"}]
    w._rebuild_cmd_table()
    w.interval_spin.setValue(37)
    w.loop_spin.setValue(0)
    w.timeout_spin.setValue(1234)
    w.rx_frame_radio.setChecked(True)
    w.frame_tail_edit.setText("AA BB")
    w.chk_show_rx.setChecked(False)
    w._save_persisted()

    w2 = stw.SerialToolWidget()
    w2.set_serial_worker(FakeWorker())
    check("间隔恢复 37", w2.interval_spin.value() == 37, str(w2.interval_spin.value()))
    check("次数恢复 0（无限）", w2.loop_spin.value() == 0, str(w2.loop_spin.value()))
    check("超时恢复 1234", w2.timeout_spin.value() == 1234, str(w2.timeout_spin.value()))
    check("接收模式恢复 frame", w2.rx_frame_radio.isChecked())
    check("帧尾恢复 AA BB", w2._frame_tail == b"\xaa\xbb", str(w2._frame_tail))
    check("显示接收开关恢复 False", w2.chk_show_rx.isChecked() is False)
    check("命令恢复 1 条", len(w2.commands) == 1 and w2.commands[0]["name"] == "持久化",
          str(w2.commands))
    check("落盘文件在沙箱（不是真实数据目录）",
          os.path.dirname(w._config_path) != os.getcwd(), w._config_path)

    section("[14] 收尾幂等")
    w.cleanup()
    w.cleanup()
    w2.cleanup()
    check("cleanup 幂等且不崩", True)

    section("[15] 主窗口集成（懒加载标签页）")
    import main_gui  # noqa: E402

    mw = main_gui.MainWindow()
    QApplication.processEvents()
    idx = getattr(mw, "_serial_tool_tab_index", -1)
    check("存在「串口工具」标签页", idx >= 0, str(idx))
    check("标签标题正确", mw.tab_widget.tabText(idx) == "串口工具",
          mw.tab_widget.tabText(idx))
    check("标签图标非空", not mw.tab_widget.tabIcon(idx).isNull())
    check("标签始终可见", mw.tab_widget.isTabVisible(idx))
    check("懒加载：切过去之前页面尚未创建", not hasattr(mw, "serial_tool_tab"))
    mw.tab_widget.setCurrentIndex(idx)
    QApplication.processEvents()
    check("切过去后页面已创建", hasattr(mw, "serial_tool_tab"))
    page = getattr(mw, "serial_tool_tab", None)
    if page is not None:
        check("页面含命令表/日志/统计控件",
              page.cmd_table.columnCount() == 7
              and page.log_text is not None
              and page.lbl_match is not None)
        check("命令表首列为「选择」勾选列",
              page.cmd_table.horizontalHeaderItem(0).text() == "选择",
              page.cmd_table.horizontalHeaderItem(0).text())
        check("命令表第 6 列为「协议」",
              page.cmd_table.horizontalHeaderItem(5).text() == "协议",
              page.cmd_table.horizontalHeaderItem(5).text())
        check("命令表第 7 列为「次数」",
              page.cmd_table.horizontalHeaderItem(6).text() == "次数",
              page.cmd_table.horizontalHeaderItem(6).text())
        check("含全选 / 全不选 / 反选与已选计数",
              page.lbl_cmd_sel is not None
              and "已选" in page.lbl_cmd_sel.text(),
              page.lbl_cmd_sel.text())
        check("接收模式含「显示解析」开关与解析行数上限",
              page.chk_show_parse is not None
              and page.parse_lines_spin is not None)
        check("页面落盘路径在沙箱",
              os.path.dirname(page._config_path) != os.getcwd(),
              page._config_path)
        page.cleanup()
    check("重复切回不重建（复用同一实例）",
          mw._ensure_serial_tool_tab() is page)
    if page is not None:
        check("页面接入的是主窗口共享的 serial_worker",
              page._serial_worker is mw.serial_worker,
              f"{page._serial_worker!r}")
        check("主窗口共享 worker 已创建且未连接",
              mw.serial_worker is not None and mw.serial_worker.is_open() is False)
    mw.close()
    QApplication.processEvents()
    check("关闭主窗口不崩（cleanup 已接线）", True)

    section("[16] 共享串口契约（复用主窗口 serial_worker）")
    w3 = stw.SerialToolWidget()
    check("未接入 worker 时发送按钮禁用", w3.btn_start.isEnabled() is False)
    check("页面不再自带端口/波特率/连接控件（避免与顶栏争抢同一串口）",
          not hasattr(w3, "port_combo") and not hasattr(w3, "baud_combo")
          and not hasattr(w3, "btn_connect"))
    fake3 = FakeWorker(is_open=False)
    w3.set_serial_worker(fake3)
    check("接入未连接的 worker：按钮仍禁用", w3.btn_start.isEnabled() is False)
    fake3.set_connected(True)
    check("顶部连上后按钮可用", w3.btn_start.isEnabled() is True)
    fake3.set_connected(False)
    check("顶部断开后按钮禁用", w3.btn_start.isEnabled() is False)
    # 未连接时点发送 → 不启动、不写串口
    w3.commands = [{"name": "A", "data_hex": "01", "match_type": "none",
                    "match_hex": ""}]
    w3._rebuild_cmd_table()
    fake3.written.clear()
    w3._start_send()
    check("未连接时拒绝启动发送", w3._running is False and fake3.written == [],
          f"running={w3._running} written={fake3.written}")
    # 换绑 worker：旧 worker 的迟到信号必须被忽略
    fake4 = FakeWorker(is_open=False)
    w3.set_serial_worker(fake4)
    check("换绑后按钮跟随新 worker（禁用）", w3.btn_start.isEnabled() is False)
    fake3.connection_changed.emit(True)
    check("旧 worker 迟到信号被忽略（仍禁用）", w3.btn_start.isEnabled() is False)
    # cleanup 不得关闭共享串口（端口归主窗口）
    fake5 = FakeWorker(is_open=True)
    w3.set_serial_worker(fake5)
    w3.cleanup()
    check("cleanup 不关闭共享串口（端口生命周期归主窗口）",
          fake5.is_open() is True)

    section("[17] 原始模式：一帧必须输出为一行（帧结构优先，回归）")
    # 场景 0（真实报障报文）：国网 208 字节帧，驱动按 77+92+36+3 四块交付，
    # 实测被打印成 4 行。长度域 68 D0 00 → 0x00D0 = 208。
    rx_chunks = [
        "68 D0 00 83 00 00 10 00 00 12 10 40 00 71 00 0F 21 53 32 05 00 10 8F 20 20 01 02 "
        "FF 35 00 09 25 24 06 8F 20 20 01 02 FF 88 16 03 25 24 06 8F 20 20 01 02 FF 01 03 "
        "00 14 07 25 00 48 4C 0B 01 01 00 00 00 00 00 00 00 00 00 10 71 12 29",
        "05 00 10 8F 20 20 01 02 FF 65 69 21 34 00 10 8F 20 20 01 02 FF 86 86 84 34 00 10 "
        "8F 20 20 01 02 FF 18 73 21 01 70 00 8F 20 20 01 02 FF 93 58 40 01 70 00 8F 20 20 "
        "01 02 FF 36 12 24 01 70 00 8F 20 20 01 02 FF 90 31 20 01 70 00 8F 20 20 01 02 FF "
        "76 39 43 02 70 00 8F 20 20 01 02",
        "FF 30 58 24 01 70 00 8F 20 20 01 02 FF 74 39 43 02 70 00 8F 20 20 01 02 FF 15 41 "
        "49 03 70 00 8F 20 20 01 02",
        "FF B5 16",
    ]
    rx_frame = b"".join(stw.hex_str_to_bytes(c) for c in rx_chunks)
    check("真实报文拼回整帧 = 208 字节", len(rx_frame) == 208, str(len(rx_frame)))
    check("长度域 68 D0 00 解析 = 208",
          stw.SerialToolWidget._declared_frame_len(rx_frame) == 208,
          str(stw.SerialToolWidget._declared_frame_len(rx_frame)))
    w.rx_raw_radio.setChecked(True)
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    for _i, _c in enumerate(rx_chunks):     # 模拟驱动分 4 块交付（块间隔 > 10ms）
        w._on_raw_data(stw.hex_str_to_bytes(_c))
        w._flush_raw_display()
        if _i < len(rx_chunks) - 1:
            check(f"交付第 {_i + 1} 块后仍不输出（未收全）",
                  len(w._rx_log_queue) == 0, str(len(w._rx_log_queue)))
    check("真实报文 4 块交付 → 只输出 1 行", len(w._rx_log_queue) == 1,
          f"{len(w._rx_log_queue)} 行")
    check("输出内容 = 完整 208 字节整帧",
          raw_texts(w)[0] == stw.bytes_to_hex(rx_frame),
          f"{len(raw_texts(w)[0].split())} 字节")
    check("RX 帧数只加 1（不再虚增）", w._rx_frames == 1, str(w._rx_frames))

    # 场景 1（合成帧）：帧体内含 16H 也不得被误切（按长度域而非扫帧尾）
    # 构造 208 字节帧：与实测报文同形（68 D0 00 = 长度域 208）
    body = bytes(range(256))[:204]
    frame208 = b"\x68\xD0\x00" + body + b"\x16"
    check("构造帧长度 = 长度域声明值 208", len(frame208) == 208, str(len(frame208)))
    check("帧体内确实含 16H（若按帧尾扫会被误切）", b"\x16" in body)
    check("长度域解析 = 208",
          stw.SerialToolWidget._declared_frame_len(frame208) == 208,
          str(stw.SerialToolWidget._declared_frame_len(frame208)))

    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    premature = 0
    for i in range(len(frame208)):          # 逐字节交付（最坏情况）
        w._on_raw_data(frame208[i:i + 1])
        w._flush_raw_display()
        if i < len(frame208) - 1 and w._rx_log_queue:
            premature += 1
    check("逐字节交付期间不输出（未收全不刷）", premature == 0, str(premature))
    check("收全后只输出 1 行", len(w._rx_log_queue) == 1,
          f"{len(w._rx_log_queue)} 行")
    check("输出内容 = 整帧（顺序与内容不变）",
          raw_texts(w)[0] == stw.bytes_to_hex(frame208))
    check("RX 帧数只加 1（不再虚增）", w._rx_frames == 1, str(w._rx_frames))

    # 场景 2：缺末字节 → 按长度域等待，不刷出；补齐后立即刷出
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(frame208[:-1])
    w._raw_last_time = time.perf_counter()          # idle≈0，静默窗口不满足
    w._raw_first_time = time.perf_counter()
    w._flush_raw_display()
    check("未收全（缺末字节）不刷出（按长度域等待，不靠静默猜）",
          len(w._rx_log_queue) == 0, str(raw_texts(w)))
    w._on_raw_data(frame208[-1:])
    w._flush_raw_display()
    check("补齐末字节后立即刷出 1 行",
          raw_texts(w) == [stw.bytes_to_hex(frame208)])

    # 场景 3：两帧连在一次交付里 → 按结构切成两行
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(frame208 + frame208)
    w._flush_raw_display()
    check("两帧连在一起 → 两行",
          raw_texts(w) == [stw.bytes_to_hex(frame208)] * 2,
          f"{len(w._rx_log_queue)} 行")
    check("RX 帧数 = 2", w._rx_frames == 2, str(w._rx_frames))

    # 场景 4：645 结构（68 A6 68 C L … CS 16，整帧 = L + 12）同样按结构切
    f645 = bytes.fromhex("6812345678901268110433333333AA16")
    check("645 帧长度 = 数据长度 + 12", len(f645) == 4 + 12, str(len(f645)))
    check("645 长度域解析 = 16",
          stw.SerialToolWidget._declared_frame_len(f645) == 16,
          str(stw.SerialToolWidget._declared_frame_len(f645)))
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    for i in range(len(f645)):
        w._on_raw_data(f645[i:i + 1])
        w._flush_raw_display()
    check("645 逐字节交付也只输出 1 行",
          raw_texts(w) == [stw.bytes_to_hex(f645)],
          str(raw_texts(w)))

    # 场景 4b：698.45 结构（68 L(2B 小端) 68 … FCS 16，整帧 = L + 3）按特征字段判别
    l698 = 17
    f698 = b"\x68" + bytes([l698 & 0xFF, l698 >> 8]) + b"\x68" + b"\x20" * 15 + b"\x16"
    check("698.45 帧长度 = 长度域 + 3", len(f698) == l698 + 3, str(len(f698)))
    check("698.45 长度域解析 = 20",
          stw.SerialToolWidget._declared_frame_len(f698) == 20,
          str(stw.SerialToolWidget._declared_frame_len(f698)))
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    for i in range(len(f698)):
        w._on_raw_data(f698[i:i + 1])
        w._flush_raw_display()
    check("698.45 逐字节交付也只输出 1 行",
          raw_texts(w) == [stw.bytes_to_hex(f698)],
          str(raw_texts(w)))

    # 场景 4c：不足 8 字节时不判别（宁可交给时间聚合，也不猜错结构）
    check("不足 8 字节不推断结构",
          stw.SerialToolWidget._declared_frame_len(b"\x68\x11\x00\x68") == 0)
    check("非 68H 开头不推断结构",
          stw.SerialToolWidget._declared_frame_len(b"\x01\x02\x03" + bytes(9)) == 0)

    # 场景 5：非 68 数据仍走时间聚合（静默窗口 + 最长持有）
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(b"\x01\x02")
    w._flush_raw_display()
    check("非 68 数据：静默窗口未到不刷出", len(w._rx_log_queue) == 0)
    w._raw_last_time = time.perf_counter() - (stw.RAW_FLUSH_DELAY_MS + 5) / 1000.0
    w._flush_raw_display()
    w._on_raw_data(b"\x03\x04")
    w._raw_last_time = time.perf_counter() - (stw.RAW_FLUSH_DELAY_MS + 5) / 1000.0
    w._flush_raw_display()
    check("非 68 数据：两段之间有间隔 → 两行",
          raw_texts(w) == ["01 02", "03 04"], str(raw_texts(w)))
    check("RX 帧数 = 2", w._rx_frames == 2, str(w._rx_frames))

    # 场景 6：持续流式（非 68）读间隔始终小于静默窗口 → 最长持有兜底强制刷出
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(b"\x11\x22")
    w._raw_last_time = time.perf_counter()          # 刚收到 → idle≈0
    w._raw_first_time = time.perf_counter() - (stw.RAW_MAX_HOLD_MS - 50) / 1000.0
    w._flush_raw_display()
    check("持有未超上限：仍不刷出（不误切帧）", len(w._rx_log_queue) == 0,
          str(raw_texts(w)))
    w._raw_first_time = time.perf_counter() - (stw.RAW_MAX_HOLD_MS + 20) / 1000.0
    w._flush_raw_display()
    check("持续流：超过最长持有上限强制刷出（缓冲不无界增长）",
          raw_texts(w) == ["11 22"], str(raw_texts(w)))
    check("强制刷出后缓冲已清空", len(w._raw_buffer) == 0)
    w._on_raw_data(b"\x33")
    check("刷出后起始时刻重置（新一轮从零计时）",
          time.perf_counter() - w._raw_first_time < 0.05)
    w._raw_buffer.clear()
    w._rx_log_queue.clear()

    # 场景 7：已声明长度的残帧等待有绝对上限（设备中途断流不得一直挂着）
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(frame208[:-1])
    w._raw_last_time = time.perf_counter()
    w._raw_first_time = time.perf_counter() - (stw.FRAME_HOLD_MAX_MS + 50) / 1000.0
    w._flush_raw_display()
    check("残帧超过绝对等待上限 → 强制刷出（不丢数据）",
          raw_texts(w) == [stw.bytes_to_hex(frame208[:-1])],
          str(len(raw_texts(w))))
    w._rx_log_queue.clear()

    # 场景 8：切换模式 / cleanup 时缓冲不得丢
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(b"\xAA\xBB")
    w.rx_frame_radio.setChecked(True)      # 切模式 → 立即刷出
    check("切模式时把聚合缓冲刷出（不丢数据）",
          raw_texts(w) == ["AA BB"], str(raw_texts(w)))
    w.rx_raw_radio.setChecked(True)
    w._rx_log_queue.clear()
    w.log_text.clear()
    w._on_raw_data(b"\xCC\xDD")
    # 1.23.54 起 cleanup 会把残留队列刷进日志窗口（并进日志文件），
    # 所以断言改看窗口内容 —— 这才是「不丢数据」的端到端证据
    # （旧版只把数据留在队列里，退出即丢）
    w.chk_show_rx.setChecked(True)
    w.cleanup()                            # cleanup → 立即刷出
    check("cleanup 时把聚合缓冲刷出（不丢数据）",
          "CC DD" in w.log_text.toPlainText(), str(raw_texts(w)))
    w._rx_log_queue.clear()
    w._on_raw_data(frame208[:-1])          # 残帧在切模式时也必须落地
    w.rx_frame_radio.setChecked(True)
    check("切模式时未收全的残帧也刷出（不丢数据）",
          raw_texts(w) == [stw.bytes_to_hex(frame208[:-1])],
          str(len(raw_texts(w))))
    w.rx_raw_radio.setChecked(True)

    section("[18] 构造顺序：落盘定时器必须先于 _build_ui/_load_persisted（回归）")
    # 载入持久化参数会触发控件 toggled → `_schedule_save()`；若此时 `_save_timer`
    # 尚未创建，信号槽里会抛 AttributeError（Qt 静默吞掉，配置保存随之失效）。
    order = {}
    _orig_build = stw.SerialToolWidget._build_ui
    _orig_load = stw.SerialToolWidget._load_persisted

    def _spy_build(self):
        order["build"] = hasattr(self, "_save_timer")
        return _orig_build(self)

    def _spy_load(self):
        order["load"] = hasattr(self, "_save_timer")
        return _orig_load(self)

    stw.SerialToolWidget._build_ui = _spy_build
    stw.SerialToolWidget._load_persisted = _spy_load
    try:
        w4 = stw.SerialToolWidget()
        check("_build_ui 执行时 _save_timer 已就绪", order.get("build") is True)
        check("_load_persisted 执行时 _save_timer 已就绪", order.get("load") is True)
        w4._schedule_save()                # 构造后立即调度不得抛异常
        check("构造后 _schedule_save 正常（定时器在跑）",
              w4._save_timer.isActive() is True)
        w4.cleanup()
    finally:
        stw.SerialToolWidget._build_ui = _orig_build
        stw.SerialToolWidget._load_persisted = _orig_load

    section("[19] 按命令协议断帧（协议锁存 + 策略分帧）")
    # 各协议的构造帧（与 test_serial_proto_frame.py 同源）
    f645 = bytes.fromhex("6812345678901268110433333333AA16")            # 645：L+12
    f698 = b"\x68\x11\x00\x68" + b"\x20" * 15 + b"\x16"                # 698.45：L+3
    fhdlc = b"\x7E\x10\x11\x12\x13\x7E"                                # HDLC 7EH 定界
    fwrap = bytes.fromhex("000100000000000A") + bytes(10)              # Wrapper：8+L
    w.rx_raw_radio.setChecked(True)
    w.chk_show_parse.setChecked(False)      # 本段只看断帧，先关解析
    # 国网（7）：68 + L(2B 小端)，L = 整帧字节数
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 7
    for _i in range(len(frame208)):         # 逐字节交付
        w._on_raw_data(frame208[_i:_i + 1])
    w._flush_raw_display()
    check("协议 7：逐字节交付 → 1 行整帧",
          raw_texts(w) == [stw.bytes_to_hex(frame208)], str(len(raw_texts(w))))
    check("协议 7：RX 帧数 = 1", w._rx_frames == 1, str(w._rx_frames))
    # 协议 7 但数据是 698 结构（第 4 字节 68H）→ 策略拒绝 → 回落时间聚合（不误切）
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(f698)
    w._flush_raw_display()
    check("协议 7 遇 698 结构不按国网切（未收全判定 → 不产出）",
          w._rx_frames == 0, str(w._rx_frames))
    w._raw_last_time = time.perf_counter() - 1     # 静默后按时间聚合刷出，不丢数据
    w._flush_raw_display()
    check("回落时间聚合后原样刷出（不丢字节）",
          raw_texts(w) == [stw.bytes_to_hex(f698)], str(len(raw_texts(w))))
    # 协议 8（698.45）：同一段数据必须按 698 结构切成整帧
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 8
    for _i in range(len(f698)):
        w._on_raw_data(f698[_i:_i + 1])
    w._flush_raw_display()
    check("协议 8：698 结构 → 1 行整帧",
          raw_texts(w) == [stw.bytes_to_hex(f698)], str(len(raw_texts(w))))
    # 协议 6（645）
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 6
    for _i in range(len(f645)):
        w._on_raw_data(f645[_i:_i + 1])
    w._flush_raw_display()
    check("协议 6：645 结构 → 1 行整帧",
          raw_texts(w) == [stw.bytes_to_hex(f645)], str(len(raw_texts(w))))
    # 协议 2（HDLC 7E 定界）：两帧连发 + 共享标志位
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 2
    w._on_raw_data(fhdlc + fhdlc)
    w._flush_raw_display()
    check("协议 2：两帧连发 → 2 行（含首尾 7EH）",
          raw_texts(w) == [stw.bytes_to_hex(fhdlc)] * 2, str(len(raw_texts(w))))
    check("协议 2：RX 帧数 = 2", w._rx_frames == 2, str(w._rx_frames))
    # 协议 4（DLMS Wrapper 长度头）
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 4
    w._on_raw_data(fwrap)
    w._flush_raw_display()
    check("协议 4：Wrapper 长度头 → 1 行整帧",
          raw_texts(w) == [stw.bytes_to_hex(fwrap)], str(len(raw_texts(w))))
    # 协议 1（无自证分帧依据）→ 走启发式/时间聚合，不按 68 结构强切
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 1
    w._on_raw_data(b"\x11\x22\x33")
    check("协议 1（无策略）：未收全时不产出", w._rx_frames == 0, str(w._rx_frames))
    w._raw_last_time = time.perf_counter() - 1
    w._flush_raw_display()
    check("协议 1（无策略）：静默后整体 1 行",
          raw_texts(w) == ["11 22 33"], str(raw_texts(w)))
    # 场景 7b（1.23.43 实测报障）：首片只有 1 字节 68，块间隔 > 10ms →
    # 旧逻辑把 68 单独刷出，缓冲从下一片起不再以 68 开头 → 整帧切成 4 行
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 7
    # 用户现场 F112 响应拆成 1+22+9+21 = 53 字节（长度域 0x0035）
    f53_chunks = [
        b"\x68",
        bytes.fromhex("35 00 83 00 00 10 00 00 00 10 80 0D 02 00 01 00 01 14 38 18 80 00"),
        bytes.fromhex("80 02 07 EA 9D E6 2E 93 6E"),
        bytes.fromhex("3C DF C0 A1 00 00 32 41 48 4C 03 FB C1 01 9C 02 01 54 05 78 16"),
    ]
    f53 = b"".join(f53_chunks)
    check("复现帧长度 = 长度域 53", len(f53) == 0x35, str(len(f53)))
    check("复现帧末字节 16H", f53[-1] == 0x16, hex(f53[-1]))
    for _i, _c in enumerate(f53_chunks):
        w._on_raw_data(_c)
        w._flush_raw_display()
        # 模拟块间隔 > RAW_FLUSH_DELAY_MS（旧 bug：首片 68 会被 10ms 窗口刷出）
        w._raw_last_time = time.perf_counter() - (stw.RAW_FLUSH_DELAY_MS + 5) / 1000.0
        if _i < len(f53_chunks) - 1:
            w._flush_raw_display()
            check(f"第 {_i + 1} 片后仍不输出（长度域未收全/未收齐）",
                  len(w._rx_log_queue) == 0, str(raw_texts(w)))
    check("首片仅 68 的 4 块交付 → 只输出 1 行整帧",
          raw_texts(w) == [stw.bytes_to_hex(f53)],
          f"{len(raw_texts(w))} 行: {raw_texts(w)[:3]}")
    check("RX 帧数只加 1", w._rx_frames == 1, str(w._rx_frames))
    w._last_tx_protocol = None
    w._raw_buffer.clear()
    w._rx_log_queue.clear()
    # 未指定协议（不解析）→ 行为与 1.23.46 一致
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = None
    for _i in range(len(frame208)):
        w._on_raw_data(frame208[_i:_i + 1])
    w._flush_raw_display()
    check("不解析：启发式仍按 68 结构切 1 行",
          raw_texts(w) == [stw.bytes_to_hex(frame208)], str(len(raw_texts(w))))

    section("[20] 按协议解析输出（假 provider）")
    calls = []

    def fake_provider(frame, proto):
        calls.append((frame, proto))
        return "摘要A", [
            ("起始字符", "0x68", "68H", "帧起始标志", 0, 0),
            ("长度域", "0xD0 0x00", "208", "小端序", 1, 2),
            ("空行", "", "", "", None, None),
        ]

    w.set_parse_provider(fake_provider)
    w.chk_show_parse.setChecked(True)
    w._last_tx_protocol = 7
    w._reset_stats()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._on_raw_data(frame208)
    w._flush_raw_display()
    check("provider 被调用（帧 + 协议）",
          calls and calls[-1][1] == 7 and calls[-1][0] == frame208, str(len(calls)))
    check("原始行仍在", raw_texts(w) == [stw.bytes_to_hex(frame208)])
    pts = parse_texts(w)
    check("解析摘要行含协议短名与摘要",
          pts[0] == "[解析·国网协议] 摘要A", pts[0] if pts else "-")
    check("字段行缩进 + 名=值 + 说明",
          pts[1] == "    起始字符 = 68H  帧起始标志", pts[1] if len(pts) > 1 else "-")
    check("空值行被跳过（解析行共 3 行：摘要 + 2 字段）", len(pts) == 3, str(len(pts)))
    check("解析行不计入 RX 帧数（仍为 1）", w._rx_frames == 1, str(w._rx_frames))
    check("无失败行", fail_texts(w) == [], str(fail_texts(w)))

    # 行数上限
    def big_provider(frame, proto):
        return "大表", [("字段%d" % i, "", str(i), "") for i in range(10)]

    w.set_parse_provider(big_provider)
    w.parse_lines_spin.setValue(3)
    w._rx_log_queue.clear()
    w._on_raw_data(frame208)
    w._flush_raw_display()
    pts = parse_texts(w)
    check("超上限截断：摘要 + 3 字段 + 1 提示 = 5 行", len(pts) == 5, str(len(pts)))
    check("截断提示行含总数与省略数",
          pts[-1] == "    …（共 10 行，已省略 7 行）", pts[-1])
    w.parse_lines_spin.setValue(stw.DEFAULT_PARSE_MAX_LINES)

    # 解析失败不伪造
    def boom_provider(frame, proto):
        raise ValueError("模拟解析器异常")

    w.set_parse_provider(boom_provider)
    w._rx_log_queue.clear()
    w._on_raw_data(frame208)
    w._flush_raw_display()
    check("provider 抛异常 → 只有失败行，无解析行",
          parse_texts(w) == [] and len(fail_texts(w)) == 1, str(fail_texts(w)))
    check("失败行含异常类型与原因",
          "ValueError" in fail_texts(w)[0] and "模拟解析器异常" in fail_texts(w)[0],
          fail_texts(w)[0])
    check("失败行带协议短名", "[解析·国网协议]" in fail_texts(w)[0], fail_texts(w)[0])
    check("失败时原始行仍完整输出",
          raw_texts(w) == [stw.bytes_to_hex(frame208)])

    def empty_provider(frame, proto):
        return "-", []

    w.set_parse_provider(empty_provider)
    w._rx_log_queue.clear()
    w._on_raw_data(frame208)
    w._flush_raw_display()
    check("provider 返回空表 → 失败行",
          parse_texts(w) == [] and len(fail_texts(w)) == 1
          and "解析结果为空" in fail_texts(w)[0], str(fail_texts(w)))

    # 「显示解析」关闭 → 零解析开销（provider 不被调用）
    calls.clear()
    w.set_parse_provider(fake_provider)
    w.chk_show_parse.setChecked(False)
    w._rx_log_queue.clear()
    w._on_raw_data(frame208)
    w._flush_raw_display()
    check("关闭显示解析 → provider 零调用", calls == [], str(len(calls)))
    check("关闭显示解析 → 只有原始行",
          raw_texts(w) == [stw.bytes_to_hex(frame208)] and parse_texts(w) == [])
    w.chk_show_parse.setChecked(True)

    # 未注入 provider → 安全降级（不抛异常、无解析行）
    w.set_parse_provider(None)
    w._rx_log_queue.clear()
    w._on_raw_data(frame208)
    w._flush_raw_display()
    check("未注入 provider → 安全降级（无解析行、原始行仍在）",
          parse_texts(w) == [] and fail_texts(w) == []
          and raw_texts(w) == [stw.bytes_to_hex(frame208)])

    section("[21] burst 策略：只对原始行计数，同批解析明细整批丢弃")
    w.set_parse_provider(fake_provider)
    w._last_tx_protocol = 2                 # HDLC 7EH 定界：一包 30 帧
    w.chk_show_rx.setChecked(True)          # [13] 曾关闭「显示接收」，这里复原
    w._rx_log_queue.clear()
    w._on_raw_data(fhdlc * 30)              # 30 帧 → 超 LOG_FLUSH_BURST(20)
    w._flush_raw_display()
    check("30 帧原始行全部入队", len(raw_texts(w)) == 30, str(len(raw_texts(w))))
    check("同批解析行也已入队（flush 时才决定是否展开）",
          len(parse_texts(w)) == 30 * 3, str(len(parse_texts(w))))
    shown = []
    _orig_log = w._log

    def _capture(text, color=None):
        shown.append(text)
        return _orig_log(text, color)

    w._log = _capture
    try:
        w._flush_log_queues()
    finally:
        w._log = _orig_log
    check("burst 只输出摘要 + 首末帧 3 行", len(shown) == 3, str(shown))
    check("摘要行含批帧数", "本批 30 帧" in shown[0], shown[0])
    check("首帧/末帧均为原始行（不含解析明细）",
          shown[1].startswith("[RX] ") and shown[2].startswith("[RX] "), str(shown))
    check("队列已清空（解析明细整批丢弃）", len(w._rx_log_queue) == 0)
    check("解析明细未出现在日志里",
          all("起始字符" not in line for line in shown), str(shown))

    section("[22] 协议字段：对话框默认 / 落盘读回 / 导入导出")
    dlg = stw.SerialCommandDialog()
    check("对话框默认协议 = 不解析", dlg.get_command()["protocol"] is None)
    check("对话框协议选项 = 1 + 注册表协议数",
          dlg.protocol_combo.count() == 1 + stw.protocol_count(),
          str(dlg.protocol_combo.count()))
    dlg.name_edit.setText("查询从节点")
    dlg.data_edit.setText("68 12 00 41 16")
    dlg.protocol_combo.setCurrentIndex(8)          # 第 8 项 = 索引 7（国网）
    got = dlg.get_command()
    check("对话框回传协议索引 7", got["protocol"] == 7, str(got["protocol"]))
    dlg2 = stw.SerialCommandDialog(command={**got, "match_type": "none"})
    check("编辑时回显已选协议",
          dlg2.get_command()["protocol"] == 7, str(dlg2.get_command()["protocol"]))
    dlg3 = stw.SerialCommandDialog(command={"name": "旧", "data_hex": "68 16",
                                            "protocol": 99})
    check("编辑非法协议 → 回落不解析",
          dlg3.get_command()["protocol"] is None, str(dlg3.get_command()["protocol"]))

    # 落盘 → 读回：协议字段不丢
    w5 = stw.SerialToolWidget()
    w5.commands = [
        {"name": "国网命令", "data_hex": "68 12 00 41 16", "match_type": "none",
         "match_hex": "", "protocol": 7},
        {"name": "无协议", "data_hex": "68 16", "match_type": "none",
         "match_hex": "", "protocol": None},
    ]
    w5._save_persisted()
    w6 = stw.SerialToolWidget()
    check("落盘读回：协议字段保留",
          [c["protocol"] for c in w6.commands] == [7, None],
          str([c.get("protocol") for c in w6.commands]))
    check("落盘读回：命令名保留",
          [c["name"] for c in w6.commands] == ["国网命令", "无协议"],
          str([c["name"] for c in w6.commands]))
    check("命令表第 6 列显示协议短名",
          w6.cmd_table.item(0, 5).text() == "国网协议"
          and w6.cmd_table.item(1, 5).text() == "不解析",
          f"{w6.cmd_table.item(0, 5).text()} / {w6.cmd_table.item(1, 5).text()}")
    # 解析参数也落盘读回
    w5.chk_show_parse.setChecked(False)
    w5.parse_lines_spin.setValue(7)
    w5._save_persisted()
    w7 = stw.SerialToolWidget()
    check("落盘读回：显示解析开关",
          w7.chk_show_parse.isChecked() is False, str(w7.chk_show_parse.isChecked()))
    check("落盘读回：解析行数上限",
          w7.parse_lines_spin.value() == 7, str(w7.parse_lines_spin.value()))
    w5.chk_show_parse.setChecked(True)
    w5.parse_lines_spin.setValue(stw.DEFAULT_PARSE_MAX_LINES)
    w5._save_persisted()
    for _w in (w5, w6, w7):
        _w.cleanup()

    # 导出/导入：协议字段随裸列表往返（源工具可读）
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "cmds.json")
        check("导出成功", stw.export_commands_file(path, w.commands))
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        check("导出为裸列表（源工具兼容）", isinstance(raw, list), type(raw).__name__)
        check("导出保留 protocol 键", "protocol" in raw[0], str(sorted(raw[0])))
        back = stw.import_commands_file(path)
        check("导入往返：协议字段一致",
              [c["protocol"] for c in back]
              == [c.get("protocol") for c in w.commands],
              str([c["protocol"] for c in back]))
        # 源工具格式（无 protocol 键）导入 → 不解析
        legacy = os.path.join(td, "legacy.json")
        with open(legacy, "w", encoding="utf-8") as fh:
            json.dump([{"name": "老命令", "data_hex": "68 16",
                        "match_type": "none", "match_hex": ""}], fh)
        old_cmds = stw.import_commands_file(legacy)
        check("旧格式（无 protocol 键）导入 → 不解析",
              old_cmds[0]["protocol"] is None, str(old_cmds[0].get("protocol")))

    section("[23] 真实解析器联调（main_gui 分派，端到端冒烟）")
    try:
        import main_gui
        mw2 = main_gui.MainWindow()
        QApplication.processEvents()
        try:
            summary, table = mw2._serial_parse_provider(rx_frame, 7)
            check("国网 208 字节帧：解析表非空", len(table) > 0, str(len(table)))
            check("国网 208 字节帧：摘要非空",
                  bool(summary) and summary != "-", str(summary)[:60])
            check("国网 208 字节帧：含长度域字段",
                  any("长度域" in str(r[0]) for r in table), str(table[0])[:40])
            rows = stw.format_parse_rows(table, 30)
            check("国网帧：日志文字行非空且带缩进",
                  bool(rows) and all(r.startswith("    ") for r in rows),
                  f"{len(rows)} 行")
            rows_all = stw.format_parse_rows(
                table, int(w.parse_lines_spin.value())
            )
            check("默认「不限制」→ 输出完整 113 行（不截断、无省略提示）",
                  len(rows_all) == len(table) and "省略" not in "".join(rows_all),
                  f"{len(rows_all)} / {len(table)}")
            check("国网帧：节点地址行 = 15（= 本次应答数量，不是从节点总数量 113）",
                  sum(1 for r in rows_all if "从节点" in r and "地址" in r) == 15,
                  str(sum(1 for r in rows_all if "从节点" in r and "地址" in r)))
            _s645, t645 = mw2._serial_parse_provider(f645, 6)
            check("645 构造帧：解析表非空", len(t645) > 0, str(len(t645)))
            _s698, t698 = mw2._serial_parse_provider(f698, 8)
            check("698.45 构造帧：解析表非空", len(t698) > 0, str(len(t698)))
        finally:
            mw2.close()
            QApplication.processEvents()
    except Exception as exc:               # 真解析器不可用不应让整轮失败
        check("真实解析器联调可用", False, f"{type(exc).__name__}: {exc}")

    section("[24] 发送也解析（TX 与 RX 对称）")
    tx_calls = []

    def tx_provider(frame, proto):
        tx_calls.append((frame, proto))
        return "发送摘要", [("应用功能码(AFN)", "16", "AFN=10H", "路由查询", 15, 15)]

    w.set_parse_provider(tx_provider)
    w.chk_show_parse.setChecked(True)
    w.chk_show_tx.setChecked(True)
    w.commands = [{"name": "查询从节点ID信息",
                   "data_hex": "68 12 00 41 08 00 00 00 00 12 10 40 00 01 00 0F BB 16",
                   "match_type": "none", "match_hex": "", "protocol": 7}]
    w._rebuild_cmd_table()
    w._tx_log_queue.clear()
    w._rx_log_queue.clear()
    w._reset_stats()
    tx_bytes = stw.hex_str_to_bytes(w.commands[0]["data_hex"])
    w._on_sent(0, 0, tx_bytes)
    check("TX 原始行入队（含序号与命令名）",
          tx_raw_texts(w) == [f"#1 查询从节点ID信息 {stw.bytes_to_hex(tx_bytes)}"],
          str(tx_raw_texts(w)))
    check("TX 解析行入队（同一条命令的协议）",
          tx_parse_texts(w)[0] == "[解析·国网协议] 发送摘要",
          str(tx_parse_texts(w)[:1]))
    check("TX 字段行格式与 RX 一致",
          tx_parse_texts(w)[1] == "    应用功能码(AFN) = AFN=10H  路由查询",
          str(tx_parse_texts(w)[1:2]))
    check("provider 收到的是发送字节与协议 7",
          tx_calls and tx_calls[-1][0] == tx_bytes and tx_calls[-1][1] == 7,
          str(tx_calls[-1][1]))
    check("TX 解析不污染 RX 队列", raw_texts(w) == [] and parse_texts(w) == [])
    check("发送锁存协议供接收使用", w._last_tx_protocol == 7, str(w._last_tx_protocol))

    # 关闭「显示解析」→ TX 也不解析（零开销）
    tx_calls.clear()
    w.chk_show_parse.setChecked(False)
    w._tx_log_queue.clear()
    w._on_sent(1, 0, tx_bytes)
    check("关闭显示解析 → TX provider 零调用", tx_calls == [], str(len(tx_calls)))
    check("关闭显示解析 → TX 只有原始行",
          len(tx_raw_texts(w)) == 1 and tx_parse_texts(w) == [])
    w.chk_show_parse.setChecked(True)

    # 命令无协议 → 只出原始行
    w.commands = [{"name": "无协议命令", "data_hex": "68 16",
                   "match_type": "none", "match_hex": "", "protocol": None}]
    w._rebuild_cmd_table()
    tx_calls.clear()
    w._tx_log_queue.clear()
    w._on_sent(0, 0, b"\x68\x16")
    check("命令协议为「不解析」→ TX 不解析",
          tx_calls == [] and tx_parse_texts(w) == [] and len(tx_raw_texts(w)) == 1)

    # TX 解析失败同样不伪造
    def tx_boom(frame, proto):
        raise RuntimeError("TX 解析炸了")

    w.set_parse_provider(tx_boom)
    w.commands = [{"name": "国网命令", "data_hex": "68 16", "match_type": "none",
                   "match_hex": "", "protocol": 7}]
    w._rebuild_cmd_table()
    w._tx_log_queue.clear()
    w._on_sent(0, 0, b"\x68\x16")
    check("TX 解析异常 → 失败行进 TX 队列（不进 RX）",
          len([1 for k, t in w._tx_log_queue if k == "fail"]) == 1
          and tx_parse_texts(w) == [] and fail_texts(w) == [],
          str([t for k, t in w._tx_log_queue if k == "fail"]))
    check("TX 失败行含异常信息",
          "TX 解析炸了" in [t for k, t in w._tx_log_queue if k == "fail"][0])

    # 两个队列都被 flush 时按各自配色与前缀输出
    w.set_parse_provider(tx_provider)
    w._tx_log_queue.clear()
    w._rx_log_queue.clear()
    w._raw_buffer.clear()
    w._last_tx_protocol = 7
    w._on_sent(0, 0, b"\x68\x16")           # TX：按命令协议 7 解析
    w._on_raw_data(frame208)                # RX：完整整帧（才会解析）
    w._flush_raw_display()
    shown2 = []
    _orig_log2 = w._log

    def _capture2(text, color=None):
        shown2.append((text, color))
        return _orig_log2(text, color)

    w._log = _capture2
    try:
        w._flush_log_queues()
    finally:
        w._log = _orig_log2
    check("TX 原始行带 [TX] 前缀", any(t.startswith("[TX] ") for t, _ in shown2),
          str(shown2[:2]))
    check("TX/RX 原始行分别用 tx / rx 配色",
          ("tx" in [c for t, c in shown2 if t.startswith("[TX] ")])
          and ("rx" in [c for t, c in shown2 if t.startswith("[RX] ")]),
          str([(t[:6], c) for t, c in shown2]))
    check("两侧解析行都存在且用 sys 配色",
          len([1 for t, c in shown2 if t.startswith("[解析·") and c == "sys"]) == 2,
          str([(t[:10], c) for t, c in shown2]))
    check("两个队列都已清空", not w._tx_log_queue and not w._rx_log_queue)

    section("[25] 端到端复现：v1 配置里的 30 不得让新版继续截断（回归）")
    # 实测报障路径：1.23.47 运行后配置里存了旧默认值 30，1.23.48 改默认却不生效。
    w8 = stw.SerialToolWidget()
    cfg = w8._config_path
    w8.cleanup()                                # 先让 cleanup 的落盘动作做完，
    with open(cfg, "w", encoding="utf-8") as fh:  # 再覆盖成 v1 配置（否则被覆盖回去）
        json.dump({"version": 1,
                   "commands": [{"name": "查询", "data_hex": "68 16",
                                 "match_type": "none", "match_hex": "",
                                 "protocol": 7}],
                   "params": {"parse_max_lines": 30, "rx_mode": "raw",
                              "parse_enabled": True}}, fh)
    w9 = stw.SerialToolWidget()                 # 重新构造 → 走 load_config 迁移
    check("v1 配置里的 30 → 页面显示「不限制」(0)",
          w9.parse_lines_spin.value() == 0, str(w9.parse_lines_spin.value()))
    check("「不限制」有可见文案",
          w9.parse_lines_spin.specialValueText() == "不限制",
          w9.parse_lines_spin.specialValueText())
    check("迁移后命令仍在（未被清空）",
          len(w9.commands) == 1 and w9.commands[0]["protocol"] == 7,
          str(w9.commands))
    # 用真实解析器跑完整链路：默认设置下必须 113 行全出
    try:
        import main_gui
        mw3 = main_gui.MainWindow()
        QApplication.processEvents()
        try:
            w9.set_parse_provider(mw3._serial_parse_provider)
            w9.chk_show_parse.setChecked(True)
            w9._last_tx_protocol = 7
            w9._rx_log_queue.clear()
            w9._raw_buffer.clear()
            w9._on_raw_data(rx_frame)
            w9._flush_raw_display()
            check("端到端：默认设置下 113 行全出、无省略提示",
                  len(parse_texts(w9)) == 114 and "省略" not in "".join(parse_texts(w9)),
                  f"{len(parse_texts(w9))} 行（应为 摘要 1 + 字段 113）")
        finally:
            mw3.close()
            QApplication.processEvents()
    except Exception as exc:
        check("端到端真实解析可用", False, f"{type(exc).__name__}: {exc}")
    w9.cleanup()
    # 复原沙箱配置，避免影响后续/重复运行
    with open(cfg, "w", encoding="utf-8") as fh:
        json.dump({"version": stw.CONFIG_VERSION, "commands": [],
                   "params": dict(stw.DEFAULT_PARAMS)}, fh)

    section("[26] 匹配：跨交付块比对 + 失败诊断日志（实测报障）")
    # 报障：预期填整帧时永远匹配不上 —— 因为原来按**单次交付的块**比对，
    # 而串口驱动把一帧拆成 77+92+36+3 四块。
    w.set_parse_provider(None)
    w.chk_show_parse.setChecked(False)
    w.chk_match.setChecked(True)
    w.rx_raw_radio.setChecked(True)
    w._last_tx_protocol = None
    exp_hex = stw.bytes_to_hex(rx_frame)
    w.commands = [{"name": "查询从节点ID信息",
                   "data_hex": "68 12 00 41 08 00 00 00 00 12 10 40 00 01 00 0F BB 16",
                   "match_type": "contains", "match_hex": exp_hex,
                   "protocol": None}]
    w._rebuild_cmd_table()
    w._reset_stats()
    w._rx_log_queue.clear()
    w._tx_log_queue.clear()
    w._raw_buffer.clear()
    tx_bytes = stw.hex_str_to_bytes(w.commands[0]["data_hex"])
    w._on_sent(0, 0, tx_bytes)
    check("发送时日志给出「在等什么」的规则行",
          any("等待响应" in t for _, t in w._tx_log_queue),
          str([t for k, t in w._tx_log_queue if k == "match"]))
    check("规则行含匹配方式与预期预览",
          any("包含(contains)" in t and "…（共 208 字节）" in t
              for _, t in w._tx_log_queue),
          str([t for k, t in w._tx_log_queue if k == "match"]))
    check("发送清空了累积接收缓冲", bytes(w._match_buffer) == b"")
    # 按实测的 4 块交付（77+92+36+3）
    for _c in rx_chunks:
        w._on_raw_data(stw.hex_str_to_bytes(_c))
    check("跨交付块的「包含」现在能匹配上（核心回归）",
          w._rx_matched == 1, f"matched={w._rx_matched}")
    check("未误判失败", w._rx_missed == 0, str(w._rx_missed))
    shown = []
    _orig_log3 = w._log

    def _capture3(text, color=None):
        shown.append((text, color))
        return _orig_log3(text, color)

    w._log = _capture3
    try:
        w._flush_log_queues()
    finally:
        w._log = _orig_log3
    check("成功日志含匹配方式与预期",
          any("[匹配✓]" in t and "包含(contains)" in t and "预期" in t
              for t, _ in shown), str([t for t, _ in shown if "匹配" in t]))
    check("成功日志用 ok 配色",
          any("[匹配✓]" in t and c == "ok" for t, c in shown),
          str([(t[:8], c) for t, c in shown]))

    # 失败路径：预期值不在数据里 → 超时后必须给出可比对的诊断
    w._reset_stats()
    w._rx_log_queue.clear()
    w._tx_log_queue.clear()
    w._raw_buffer.clear()
    w.commands = [{"name": "错预期", "data_hex": "68 12 00 41 08 00 00 00 00 12 10 40 00 01 00 0F BB 16",
                   "match_type": "equals", "match_hex": "AA BB CC",
                   "protocol": None}]
    w._rebuild_cmd_table()
    w._on_sent(0, 0, tx_bytes)
    w._on_raw_data(b"\x01\x02")
    w.timeout_spin.setValue(10)
    w._pending_match[0]["sent_time"] = time.perf_counter() - 10
    w._check_match_timeout()
    shown.clear()
    w._log = _capture3
    try:
        w._flush_log_queues()
    finally:
        w._log = _orig_log3
    fail_lines = [t for t, c in shown if c == "fail"]
    check("失败日志给出 4 行诊断（标题 + 方式 + 预期 + 期间收到 + 诊断）",
          len(fail_lines) == 5, str(len(fail_lines)))
    check("诊断行含匹配方式",
          any("匹配方式 = 完全相等(equals)" in t for t in fail_lines),
          str(fail_lines[:2]))
    check("诊断行含预期响应",
          any("预期响应 = AA BB CC" in t for t in fail_lines), str(fail_lines[:3]))
    check("诊断行含期间收到的数据与字节数",
          any("期间收到 = 01 02" in t and "共 2 字节" in t for t in fail_lines),
          str(fail_lines[:4]))
    check("诊断结论点明长度不一致",
          any("长度不一致" in t and "预期 3 字节" in t and "收到 2 字节" in t
              for t in fail_lines), str(fail_lines[-1:]))
    check("失败项已计入统计", w._rx_missed == 1, str(w._rx_missed))
    check("队列清空后累积缓冲也清空（不会用上次响应误判）",
          bytes(w._match_buffer) == b"" and w._match_rx_bytes == 0,
          f"{bytes(w._match_buffer)!r}/{w._match_rx_bytes}")

    # 「预期填成了发送值」必须点名（最常见误填）
    w._reset_stats()
    w._rx_log_queue.clear()
    w._tx_log_queue.clear()
    w.commands = [{"name": "误填", "data_hex": "68 12 00 41 16",
                   "match_type": "contains",
                   "match_hex": "68 12 00 41 16", "protocol": None}]
    w._rebuild_cmd_table()
    w._on_sent(0, 0, stw.hex_str_to_bytes("68 12 00 41 16"))
    w._on_raw_data(b"\x68\xD0\x00")
    w._pending_match[0]["sent_time"] = time.perf_counter() - 10
    w._check_match_timeout()
    check("预期 == 发送值 → 诊断点名常见误填",
          any("误填" in t and "发送数据完全相同" in t for _, t in w._rx_log_queue),
          str([t for k, t in w._rx_log_queue if k == "fail"]))

    # 两次发送之间不得用上一次响应的字节误判
    w._reset_stats()
    w._rx_log_queue.clear()
    w._tx_log_queue.clear()
    w._match_buffer.clear()
    w.commands = [{"name": "A", "data_hex": "01", "match_type": "contains",
                   "match_hex": "AA", "protocol": None}]
    w._rebuild_cmd_table()
    w._on_sent(0, 0, b"\x01")
    w._on_raw_data(b"\xAA")
    check("第 1 次按累积数据匹配成功", w._rx_matched == 1, str(w._rx_matched))
    w.commands = [{"name": "B", "data_hex": "02", "match_type": "contains",
                   "match_hex": "AA", "protocol": None}]
    w._rebuild_cmd_table()
    w._on_sent(1, 0, b"\x02")
    w._on_raw_data(b"\xBB")                 # 本窗口没有 AA
    check("第 2 次不得拿上一次的 AA 误判成功",
          w._rx_matched == 1, str(w._rx_matched))
    w.chk_match.setChecked(True)
    w.timeout_spin.setValue(5000)

    section("[27] 双击命令行直接进入编辑窗口")
    w.commands = [
        {"name": "A", "data_hex": "01", "match_type": "none", "match_hex": "",
         "protocol": 7},
        {"name": "B", "data_hex": "02", "match_type": "contains",
         "match_hex": "AA", "protocol": None},
    ]
    w._rebuild_cmd_table()
    seen = []
    _orig_init = stw.SerialCommandDialog.__init__
    _orig_exec = stw.SerialCommandDialog.exec

    def _spy_init(self, parent=None, command=None):
        seen.append(dict(command) if command else None)
        _orig_init(self, parent, command)

    stw.SerialCommandDialog.__init__ = _spy_init
    # 模态框在 offscreen 下会永久阻塞 → 直接让它返回「取消」
    stw.SerialCommandDialog.exec = lambda self: stw.QDialog.DialogCode.Rejected
    try:
        w._on_cmd_double_clicked(1, 2)
        check("双击第 2 行 → 用该行命令打开编辑框",
              len(seen) == 1 and seen[-1] and seen[-1]["name"] == "B", str(seen))
        # 走真实信号（验证 cellDoubleClicked 确实连上了处理函数）
        seen.clear()
        w.cmd_table.cellDoubleClicked.emit(0, 2)
        check("cellDoubleClicked 信号真正连上处理函数（走信号路径）",
              len(seen) == 1 and seen[-1] and seen[-1]["name"] == "A", str(seen))
        seen.clear()
        w._on_cmd_double_clicked(1, 2)
        check("双击带出的字段完整（含协议）",
              seen[-1]["data_hex"] == "02" and seen[-1]["match_type"] == "contains"
              and seen[-1]["match_hex"] == "AA" and seen[-1]["protocol"] is None,
              str(seen[-1]))
        check("双击后该行被选中（视觉与编辑目标一致）",
              w._selected_row() == 1, str(w._selected_row()))
        # 双击第 1 行 → 编辑的是第 1 行（不能因为按钮的 bool 参数串行）
        seen.clear()
        w._on_cmd_double_clicked(0, 3)
        check("双击第 1 行 → 编辑第 1 行（任意列都行）",
              len(seen) == 1 and seen[-1]["name"] == "A", str(seen))
        check("双击第 1 行后选中第 1 行", w._selected_row() == 0,
              str(w._selected_row()))
        # 越界行号（空表/异常调用）不得抛异常、不得弹框
        seen.clear()
        w._on_cmd_double_clicked(99, 2)
        w._on_cmd_double_clicked(-1, 2)
        check("越界行号被安全忽略（不弹编辑框）", seen == [], str(seen))
        # 第 0 列（勾选框）双击不弹编辑框（只切换勾选）
        seen.clear()
        w._on_cmd_double_clicked(1, 0)
        check("双击勾选列不弹编辑框（避免与切换勾选打架）",
              seen == [], str(seen))
        # 取消编辑不改动原命令
        check("取消编辑不改动命令", w.commands[1]["name"] == "B",
              str(w.commands[1]))
    finally:
        stw.SerialCommandDialog.__init__ = _orig_init
        stw.SerialCommandDialog.exec = _orig_exec

    section("[28] 勾选命令 + 全选/全不选/反选 + 只发勾选项（实测诉求）")
    w.set_parse_provider(None)
    w.chk_show_parse.setChecked(False)
    w.chk_match.setChecked(False)
    w.commands = [
        {"name": "A", "data_hex": "01", "match_type": "none", "match_hex": "",
         "protocol": 0, "enabled": False},
        {"name": "B", "data_hex": "02", "match_type": "none", "match_hex": "",
         "protocol": 7, "enabled": True},
        {"name": "C", "data_hex": "03", "match_type": "none", "match_hex": "",
         "protocol": 8, "enabled": False},
        {"name": "D", "data_hex": "04", "match_type": "none", "match_hex": "",
         "protocol": 6, "enabled": True},
    ]
    w._rebuild_cmd_table()
    check("勾选列按 enabled 渲染",
          [w.cmd_table.item(r, 0).checkState() == stw.Qt.CheckState.Checked
           for r in range(4)] == [False, True, False, True],
          str([w.cmd_table.item(r, 0).checkState() for r in range(4)]))
    check("勾选项可被用户点击（ItemIsUserCheckable + ItemIsEnabled）",
          bool(w.cmd_table.item(0, 0).flags() & stw.Qt.ItemFlag.ItemIsUserCheckable)
          and bool(w.cmd_table.item(0, 0).flags() & stw.Qt.ItemFlag.ItemIsEnabled))
    check("已选计数正确（2 / 4）", w.lbl_cmd_sel.text() == "已选 2 / 4 条",
          w.lbl_cmd_sel.text())
    check("_checked_rows 按表内顺序", w._checked_rows() == [1, 3],
          str(w._checked_rows()))
    # 勾选变化 → 回写 commands + 落盘
    w.cmd_table.item(0, 0).setCheckState(stw.Qt.CheckState.Checked)
    check("勾选变化回写到 commands[0].enabled",
          w.commands[0]["enabled"] is True, str(w.commands[0]))
    check("勾选变化后计数刷新", w.lbl_cmd_sel.text() == "已选 3 / 4 条",
          w.lbl_cmd_sel.text())
    w.cmd_table.item(0, 0).setCheckState(stw.Qt.CheckState.Unchecked)
    check("取消勾选同样回写", w.commands[0]["enabled"] is False, str(w.commands[0]))
    # 全选 / 全不选 / 反选
    w._set_all_checkboxes(True)
    check("全选 → 4 / 4", w._checked_rows() == [0, 1, 2, 3], str(w._checked_rows()))
    check("全选回写 enabled", all(c["enabled"] for c in w.commands),
          str([c["enabled"] for c in w.commands]))
    w._invert_checkboxes()
    check("反选 → 0 / 4", w._checked_rows() == [], str(w._checked_rows()))
    w._invert_checkboxes()
    check("再反选 → 4 / 4", w._checked_rows() == [0, 1, 2, 3], str(w._checked_rows()))
    w._set_all_checkboxes(False)
    check("全不选 → 0 / 4", w._checked_rows() == [], str(w._checked_rows()))
    # 一条都没勾 → 提示且不发送
    fake = FakeWorker(is_open=True)
    w.set_serial_worker(fake)
    w._start_send()
    check("未勾选任何命令 → 不启动发送", w._running is False and fake.written == [],
          f"running={w._running} written={len(fake.written)}")
    # 只发勾选的命令，且 index_map 回指原下标（名称/协议不得错位）
    w._set_all_checkboxes(False)
    w.cmd_table.item(1, 0).setCheckState(stw.Qt.CheckState.Checked)
    w.cmd_table.item(3, 0).setCheckState(stw.Qt.CheckState.Checked)
    w.interval_spin.setValue(1)
    w.loop_spin.setValue(1)
    w._tx_log_queue.clear()
    w.log_text.clear()
    w._start_send()
    wait_until(lambda: not w._running, 5000)
    QApplication.processEvents()
    w._flush_log_queues()                  # 把残留队列刷到日志框再断言
    QApplication.processEvents()
    check("只发勾选的 2 条（B / D）", fake.written == [b"\x02", b"\x04"],
          str(fake.written))
    logged = w.log_text.toPlainText().split("\n")
    tx_names = [ln for ln in logged if ln.startswith("[TX] #")]
    check("TX 日志名称不错位（#1 B、#2 D）",
          len(tx_names) == 2 and tx_names[0].startswith("[TX] #1 B")
          and tx_names[1].startswith("[TX] #2 D"), str(tx_names))
    check("协议锁存取的是勾选项的协议（D = 6）",
          w._last_tx_protocol == 6, str(w._last_tx_protocol))
    check("发送日志标明「已勾选」范围",
          any("2/4 条命令（已勾选）" in ln for ln in logged),
          str([ln for ln in logged if "开始" in ln]))
    # enabled 随配置落盘读回；旧配置无该键 → 全选
    w10 = stw.SerialToolWidget()
    w10.commands = [
        {"name": "勾", "data_hex": "01", "match_type": "none", "match_hex": "",
         "protocol": None, "enabled": False},
        {"name": "未勾", "data_hex": "02", "match_type": "none", "match_hex": "",
         "protocol": None, "enabled": True},
    ]
    w10._save_persisted()
    w11 = stw.SerialToolWidget()
    check("落盘读回：勾选状态保留",
          [c["enabled"] for c in w11.commands] == [False, True],
          str([c.get("enabled") for c in w11.commands]))
    check("落盘读回：表格勾选列一致",
          w11.cmd_table.item(0, 0).checkState() == stw.Qt.CheckState.Unchecked
          and w11.cmd_table.item(1, 0).checkState() == stw.Qt.CheckState.Checked)
    check("旧配置（无 enabled 键）→ 全选",
          stw.coerce_enabled(None) is True
          and stw.normalize_command({"name": "x", "data_hex": "01"})["enabled"] is True)
    check("coerce_enabled 反例",
          stw.coerce_enabled(False) is False
          and stw.coerce_enabled(0) is False
          and stw.coerce_enabled("false") is False
          and stw.coerce_enabled("off") is False
          and stw.coerce_enabled(True) is True
          and stw.coerce_enabled(1) is True
          and stw.coerce_enabled("yes") is True
          and stw.coerce_enabled("乱码") is True,
          "见断言")
    check("导出保留 enabled 键",
          all("enabled" in c for c in stw.export_commands(w.commands)))
    # 编辑命令不得改动勾选状态
    w12 = stw.SerialToolWidget()
    w12.commands = [{"name": "E", "data_hex": "01", "match_type": "none",
                     "match_hex": "", "protocol": None, "enabled": False}]
    w12._rebuild_cmd_table()
    _o_init2 = stw.SerialCommandDialog.__init__
    _o_exec2 = stw.SerialCommandDialog.exec

    def _init2(self, parent=None, command=None):
        _o_init2(self, parent, command)

    stw.SerialCommandDialog.__init__ = _init2
    stw.SerialCommandDialog.exec = lambda self: stw.QDialog.DialogCode.Accepted
    try:
        w12._on_cmd_double_clicked(0, 2)
    finally:
        stw.SerialCommandDialog.__init__ = _o_init2
        stw.SerialCommandDialog.exec = _o_exec2
    check("编辑命令后勾选状态不被重置",
          w12.commands[0]["enabled"] is False, str(w12.commands[0]))
    for _w in (w10, w11, w12):
        _w.cleanup()
    w.set_serial_worker(None)

    # 真鼠标点击勾选框：NoEditTriggers 下必须仍能切换（这是用户交互的核心，
    # 只断言 flags 不够 —— 真点一下才算验证）
    w13 = stw.SerialToolWidget()
    w13.commands = [{"name": "K", "data_hex": "01", "match_type": "none",
                     "match_hex": "", "protocol": None, "enabled": False}]
    w13._rebuild_cmd_table()
    w13.resize(900, 500)
    w13.show()
    QApplication.processEvents()
    _item = w13.cmd_table.item(0, 0)
    _rect = w13.cmd_table.visualItemRect(_item)
    _pos = QPoint(_rect.left() + 8, _rect.center().y())
    check("勾选框有可点击区域（列宽 > 0）", _rect.width() > 10, str(_rect))
    QTest.mouseClick(w13.cmd_table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, _pos)
    QApplication.processEvents()
    check("真鼠标点击勾选框 → 切换为选中（NoEditTriggers 不阻碍）",
          _item.checkState() == stw.Qt.CheckState.Checked, str(_item.checkState()))
    check("点击后回写 commands[0].enabled", w13.commands[0]["enabled"] is True,
          str(w13.commands[0]))
    QTest.mouseClick(w13.cmd_table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, _pos)
    QApplication.processEvents()
    check("再点一次 → 取消勾选",
          _item.checkState() == stw.Qt.CheckState.Unchecked,
          str(_item.checkState()))
    check("再点后同样回写", w13.commands[0]["enabled"] is False,
          str(w13.commands[0]))
    w13.cleanup()

    section("[29] 正则匹配方式：预期是正则文本，不是 HEX（修复）")
    # 旧实现把「预期响应」一律按 HEX 校验 → 任何正则都被降级成「不匹配」，
    # 匹配永远不发生（且现场只会看到「超时未匹配」）。
    cmd = stw.normalize_command({"name": "正则", "data_hex": "68 16",
                                 "match_type": "regex",
                                 "match_hex": r"68\s*D0"})
    check("normalize 不把合法正则降级成 none",
          cmd["match_type"] == "regex", str(cmd["match_type"]))
    check("normalize 保留正则原文", cmd["match_hex"] == r"68\s*D0",
          str(cmd["match_hex"]))
    bad = stw.normalize_command({"name": "坏正则", "data_hex": "68 16",
                                 "match_type": "regex", "match_hex": "["})
    check("非法正则才降级为「不匹配」",
          bad["match_type"] == "none", str(bad["match_type"]))
    empty = stw.normalize_command({"name": "空正则", "data_hex": "68 16",
                                   "match_type": "regex", "match_hex": ""})
    check("空正则也降级（否则会匹配一切）",
          empty["match_type"] == "none", str(empty["match_type"]))
    check("非正则方式仍按 HEX 校验（非法 → 降级）",
          stw.normalize_command({"name": "x", "data_hex": "68 16",
                                 "match_type": "equals",
                                 "match_hex": "ZZ"})["match_type"] == "none")
    check("expected_display 正则是文本（不加 repr 转义）、其余是 HEX",
          stw.expected_display("regex", b"68\\s*D0") == "正则 68\\s*D0"
          and stw.expected_display("contains", b"\x68") == "68",
          f"{stw.expected_display('regex', b'68')!r} / "
          f"{stw.expected_display('contains', b'\\x68')!r}")
    check("正则不参与「预期=发送值」误填提示",
          "误填" not in stw.match_failure_reason("regex", b"abc", b"xyz", b"abc"))
    # 端到端：正则方式真的能命中
    w14 = stw.SerialToolWidget()
    w14.set_parse_provider(None)
    w14.chk_show_parse.setChecked(False)
    w14.chk_match.setChecked(True)
    w14.commands = [{"name": "正则", "data_hex": "68 16", "match_type": "regex",
                     "match_hex": r"68\s*D0", "protocol": None,
                     "enabled": True}]
    w14._rebuild_cmd_table()
    w14._reset_stats()
    w14._tx_log_queue.clear()
    w14._rx_log_queue.clear()
    w14._on_sent(0, 0, b"\x68\x16")
    check("正则方式的待匹配项已入队（旧实现这里根本不会入队）",
          len(w14._pending_match) == 1, str(len(w14._pending_match)))
    check("规则行展示正则文本而非 HEX",
          any("正则" in t and r"68\s*D0" in t
              for _, t in w14._tx_log_queue),
          str([t for k, t in w14._tx_log_queue if k == "match"]))
    w14._on_raw_data(b"68 D0 00 83")
    check("正则命中（\\s* 跨空格）", w14._rx_matched == 1, str(w14._rx_matched))
    check("命中日志用 ok 配色且含正则",
          any(k == "ok" and "正则" in t for k, t in w14._rx_log_queue),
          str([t for k, t in w14._rx_log_queue if k == "ok"]))
    w14.cleanup()

    section("[30] HEX 通配匹配（XX = 任意字节，与「测试方案」同一约定）")
    check("匹配方式下拉含「HEX 通配」",
          "hex_wildcard" in stw.MATCH_TYPES
          and "XX" in stw.MATCH_TYPES["hex_wildcard"],
          stw.MATCH_TYPES.get("hex_wildcard", "-"))
    # 解析模式
    check("空格分隔 + XX",
          stw.parse_hex_wildcard("68 D0 XX XX 16")
          == [0x68, 0xD0, None, None, 0x16],
          str(stw.parse_hex_wildcard("68 D0 XX XX 16")))
    check("连续串内嵌 XX（68D0XXXX16）",
          stw.parse_hex_wildcard("68D0XXXX16")
          == [0x68, 0xD0, None, None, 0x16],
          str(stw.parse_hex_wildcard("68D0XXXX16")))
    check("?? 是等价别名", stw.parse_hex_wildcard("68 ?? 16")
          == [0x68, None, 0x16])
    check("全角逗号也当分隔符",
          stw.parse_hex_wildcard("68，D0，XX") == [0x68, 0xD0, None])
    check("小写 xx 也认", stw.parse_hex_wildcard("68xx16") == [0x68, None, 0x16])
    check("奇数位 → None", stw.parse_hex_wildcard("68 D0 X") is None)
    check("非 hex 字符 → None", stw.parse_hex_wildcard("68 ZZ") is None)
    check("空模式 → None", stw.parse_hex_wildcard("  ") is None)
    check("单独的 X 不算通配（必须 XX）",
          stw.parse_hex_wildcard("68 X 16") is None)
    # 匹配语义（包含 + 锚点）
    rx = bytes.fromhex("68D00083000010000012")
    check("包含式：默认任意位置（D0 在偏移 1，XX 跳过 00）",
          stw.hex_wildcard_match(rx, "D0 XX 83") == 1,
          str(stw.hex_wildcard_match(rx, "D0 XX 83")))
    check("^ 锚定开头：命中返回 0",
          stw.hex_wildcard_match(rx, "^68 D0 XX XX") == 0,
          str(stw.hex_wildcard_match(rx, "^68 D0 XX XX")))
    check("^ 锚定开头：不在开头则不命中",
          stw.hex_wildcard_match(rx, "^D0") is None)
    check("$ 锚定结尾：命中",
          stw.hex_wildcard_match(rx, "XX XX 00 12$") == 6,
          str(stw.hex_wildcard_match(rx, "XX XX 00 12$")))
    check("$ 锚定结尾：不在结尾则不命中",
          stw.hex_wildcard_match(rx, "68 D0$") is None)
    check("^…$ 全长匹配",
          stw.hex_wildcard_match(rx, "^68 D0 XX XX XX XX 10 00 00 12$") == 0,
          str(stw.hex_wildcard_match(rx, "^68 D0 XX XX XX XX 10 00 00 12$")))
    check("全长匹配长度不符 → None",
          stw.hex_wildcard_match(rx, "^68 D0 XX XX$") is None)
    check("XX 真的跳过（改字节仍命中）",
          stw.hex_wildcard_match(bytes.fromhex("68AA00"), "^68 XX 00$") == 0,
          str(stw.hex_wildcard_match(bytes.fromhex("68AA00"), "^68 XX 00$")))
    check("非通配位必须逐字节相等",
          stw.hex_wildcard_match(bytes.fromhex("68AA00"), "^68 99 00$") is None)
    check("模式比数据长 → None",
          stw.hex_wildcard_match(b"\x68", "68 16") is None)
    check("非法模式 → None", stw.hex_wildcard_match(rx, "68 ZZ") is None)
    check("check_match 也支持 hex_wildcard",
          stw.check_match(rx, b"68 D0 XX", "hex_wildcard") is True
          and stw.check_match(rx, b"99 XX", "hex_wildcard") is False)
    check("match_offset 返回偏移（contains 也给位置）",
          stw.match_offset("hex_wildcard", rx, b"D0 XX") == 1
          and stw.match_offset("contains", rx, b"\x00\x10") == 5
          and stw.match_offset("contains", rx, b"\x99") is None,
          f"{stw.match_offset('hex_wildcard', rx, b'D0 XX')} / "
          f"{stw.match_offset('contains', rx, b'\\x00\\x10')}")
    # normalize / 展示 / 诊断
    ok_cmd = stw.normalize_command({"name": "通配", "data_hex": "68 16",
                                    "match_type": "hex_wildcard",
                                    "match_hex": "68 D0 XX XX"})
    check("normalize 不把合法通配模式降级",
          ok_cmd["match_type"] == "hex_wildcard", str(ok_cmd["match_type"]))
    bad_cmd = stw.normalize_command({"name": "坏通配", "data_hex": "68 16",
                                     "match_type": "hex_wildcard",
                                     "match_hex": "68 ZZ"})
    check("非法通配模式才降级为「不匹配」",
          bad_cmd["match_type"] == "none", str(bad_cmd["match_type"]))
    check("expected_display 通配模式按文本展示",
          stw.expected_display("hex_wildcard", b"68 D0 XX") == "通配模式 68 D0 XX",
          stw.expected_display("hex_wildcard", b"68 D0 XX"))
    check("诊断：模式比数据长",
          "比收到的数据长" in stw.match_failure_reason(
              "hex_wildcard", b"68 D0 XX XX", b"\x68"),
          stw.match_failure_reason("hex_wildcard", b"68 D0 XX XX", b"\x68"))
    check("诊断：未匹配到",
          "未在收到的数据中匹配到" in stw.match_failure_reason(
              "hex_wildcard", b"99 XX", b"\x68\xD0"),
          stw.match_failure_reason("hex_wildcard", b"99 XX", b"\x68\xD0"))
    check("通配不参与「预期=发送值」误填提示",
          "误填" not in stw.match_failure_reason(
              "hex_wildcard", b"68 16", b"68 16", b"68 16"))
    # 端到端：用实测国网帧
    w15 = stw.SerialToolWidget()
    w15.set_parse_provider(None)
    w15.chk_show_parse.setChecked(False)
    w15.chk_match.setChecked(True)
    w15.commands = [{"name": "通配校验", "data_hex": "68 16",
                     "match_type": "hex_wildcard",
                     "match_hex": "68 D0 XX XX XX XX", "protocol": None,
                     "enabled": True}]
    w15._rebuild_cmd_table()
    w15._reset_stats()
    w15._tx_log_queue.clear()
    w15._rx_log_queue.clear()
    w15._on_sent(0, 0, b"\x68\x16")
    check("通配方式的待匹配项已入队", len(w15._pending_match) == 1,
          str(len(w15._pending_match)))
    check("规则行展示通配模式",
          any("通配模式 68 D0 XX XX XX XX" in t for _, t in w15._tx_log_queue),
          str([t for k, t in w15._tx_log_queue if k == "match"]))
    for _c in rx_chunks:                    # 四块交付（跨块累积）
        w15._on_raw_data(stw.hex_str_to_bytes(_c))
    check("跨交付块命中（帧头 68 D0 + 4 个通配字节）",
          w15._rx_matched == 1, str(w15._rx_matched))
    check("命中日志给出偏移 0",
          any(k == "ok" and "命中偏移 0" in t for k, t in w15._rx_log_queue),
          str([t for k, t in w15._rx_log_queue if k == "ok"]))
    # 不命中时给出通配专用诊断
    w15._reset_stats()
    w15._rx_log_queue.clear()
    w15.commands[0]["match_hex"] = "99 XX XX"
    w15._rebuild_cmd_table()
    w15._on_sent(1, 0, b"\x68\x16")
    w15._on_raw_data(stw.hex_str_to_bytes(rx_chunks[0]))
    w15._pending_match[0]["sent_time"] = time.perf_counter() - 10
    w15.timeout_spin.setValue(10)
    w15._check_match_timeout()
    check("未命中 → 诊断说明通配未匹配到",
          any("未在收到的数据中匹配到" in t for _, t in w15._rx_log_queue),
          str([t for k, t in w15._rx_log_queue if k == "fail"][-1:]))
    w15.timeout_spin.setValue(5000)
    w15.cleanup()

    # 交叉验证：与「测试方案」的 _match_frame 约定必须一致（用户明确要求参考它）
    try:
        from test_plan_widget import TestPlanWidget

        agree = []
        for rule, actual in (
            ("68 D0 XX XX 16", "68D0008316"),
            ("68 D0 00 83 16", "68D0008316"),
            ("68 D0 XX XX 16", "68D0008317"),
            ("68D0XXXX16", "68D0008316"),
            ("68 D0 XX", "68D0008316"),
        ):
            plan_ok = TestPlanWidget._match_frame(rule, actual, "HEX")
            mine_ok = stw.hex_wildcard_match(
                bytes.fromhex(actual), "^" + rule + "$"
            ) is not None
            agree.append((rule, actual, plan_ok, mine_ok, plan_ok == mine_ok))
        check("与「测试方案」_match_frame 结论逐例一致（全长语义下）",
              all(a[4] for a in agree), str([a for a in agree if not a[4]]))
        check("交叉验证里确实有 True 与 False 两种结论（判据有效）",
              any(a[2] for a in agree) and any(not a[2] for a in agree),
              str([(a[2], a[3]) for a in agree]))
        check("长度不等时两边都判 False（_match_frame 要求等长）",
              TestPlanWidget._match_frame("68 D0 XX", "68D0008316", "HEX") is False
              and stw.hex_wildcard_match(b"\x68\xD0\x00\x83\x16",
                                         "^68 D0 XX$") is None)
    except Exception as exc:
        check("交叉验证可运行", False, f"{type(exc).__name__}: {exc}")

    section("[31] 日志自动保存到文件")
    from datetime import datetime as _dt  # noqa: E402  时间戳注入用
    # ── 纯函数 ──
    _stamp = stw.format_log_time(_dt(2026, 9, 22, 15, 30, 0, 123456))
    check("时间戳格式（毫秒精度）", _stamp == "2026-09-22 15:30:00.123", _stamp)
    check("文件名带秒级时间戳",
          stw.log_file_name(_dt(2026, 9, 22, 15, 30, 0))
          == "serial_log_20260922_153000.log",
          stw.log_file_name(_dt(2026, 9, 22, 15, 30, 0)))
    check("默认日志目录 = <数据目录>/Output",
          os.path.normpath(stw.default_log_dir(r"C:\x"))
          == os.path.normpath(r"C:\x\Output"),
          stw.default_log_dir(r"C:\x"))
    with tempfile.TemporaryDirectory() as _tmp:
        _name = "serial_log_20260922_153000.log"
        open(os.path.join(_tmp, _name), "w", encoding="utf-8").close()
        _p1 = stw.unique_log_path(_tmp, _name)
        open(_p1, "w", encoding="utf-8").close()
        _p2 = stw.unique_log_path(_tmp, _name)
        check("同名不覆盖（_1 / _2 递增）",
              os.path.basename(_p1) == "serial_log_20260922_153000_1.log"
              and os.path.basename(_p2) == "serial_log_20260922_153000_2.log",
              f"{os.path.basename(_p1)} / {os.path.basename(_p2)}")
        _manual0 = os.path.join(_tmp, "manual.log")
        check("write_log_text 写入成功", stw.write_log_text(_manual0, "a\nb") is True)
        with open(_manual0, encoding="utf-8") as _fh:
            check("write_log_text 末尾补换行", _fh.read() == "a\nb\n")
        check("write_log_text 目标是目录 → False 且不抛",
              stw.write_log_text(_tmp, "x") is False)

    class _FakePort:
        _port = "COM7"
        _baudrate = 115200

    check("日志头串口上下文取到端口/波特率",
          stw.serial_context_text(_FakePort()) == "COM7 @ 115200",
          stw.serial_context_text(_FakePort()))
    check("取不到串口信息时有可读说明（不报错）",
          "未连接" in stw.serial_context_text(None)
          and "未获取" in stw.serial_context_text(object()),
          f"{stw.serial_context_text(None)} / {stw.serial_context_text(object())}")

    # ── LogFileWriter（纯逻辑）──
    with tempfile.TemporaryDirectory() as _tmp:
        _now = _dt(2026, 9, 22, 15, 30, 0, 123456)
        wr = stw.LogFileWriter(timestamp=True)
        check("open 成功且文件已建",
              wr.open(_tmp, header=["# 头"], now=_now) is True
              and wr.is_open and os.path.exists(wr.path), wr.path)
        wr.write_line("hello", now=_now)
        wr.write_line("多行1\n多行2", now=_now)
        with open(wr.path, encoding="utf-8") as _fh:
            _lines = _fh.read().splitlines()
        check("文件头按原文写（无时间戳前缀）", _lines[0] == "# 头", _lines[0])
        check("日志行带毫秒时间戳前缀",
              _lines[1] == "2026-09-22 15:30:00.123 | hello", _lines[1])
        check("多行文本按物理行逐行加前缀（不产生无前缀行）",
              _lines[2] == "2026-09-22 15:30:00.123 | 多行1"
              and _lines[3] == "2026-09-22 15:30:00.123 | 多行2", str(_lines[2:4]))
        check("写一行即落盘（未 close 也能从磁盘读到）",
              "hello" in open(wr.path, encoding="utf-8").read())
        check("行数统计含文件头", wr.line_count == 4, str(wr.line_count))
        check("字节统计 > 0", wr.byte_count > 0, str(wr.byte_count))
        check("close 幂等", wr.close() is True and wr.close() is True)
        check("close 后 is_open False", wr.is_open is False)

        wr2 = stw.LogFileWriter()
        wr2.open(_tmp, now=_now)
        check("同一秒再开 → 不覆盖前一个文件",
              wr2.path != wr.path and os.path.exists(wr.path)
              and os.path.basename(wr2.path).endswith("_1.log"),
              os.path.basename(wr2.path))
        wr2.close()

        wr3 = stw.LogFileWriter(timestamp=False)
        wr3.open(_tmp, now=_now)
        wr3.write_line("[RX] 68 16", now=_now)
        wr3.close()
        with open(wr3.path, encoding="utf-8") as _fh:
            check("关掉时间戳则写原文（与窗口显示逐字符一致）",
                  _fh.read() == "[RX] 68 16\n")

        _blocked = os.path.join(_tmp, "not_a_dir")
        open(_blocked, "w", encoding="utf-8").close()
        wr4 = stw.LogFileWriter()
        check("目录位置是文件时 open 返回 False（不抛）",
              wr4.open(_blocked) is False and wr4.is_open is False
              and bool(wr4.error), wr4.error)

        wr5 = stw.LogFileWriter()
        wr5.open(_tmp, now=_now)
        wr5._fh.close()                     # 模拟句柄失效（目录被删/磁盘满 同类）
        _ok5 = wr5.write_line("x")
        check("句柄失效时 write_line 返回 False 且自关（不抛）",
              _ok5 is False and bool(wr5.error) and wr5.is_open is False,
              f"{_ok5} / {wr5.error}")

    # ── Widget 级：勾选 → 实时写文件（且落在沙箱里）──
    fake16 = FakeWorker()
    fake16._port = "COM9"
    fake16._baudrate = 9600
    w16 = stw.SerialToolWidget()
    w16.set_serial_worker(fake16)
    w16.chk_show_parse.setChecked(False)          # 本段不牵扯解析回调
    check("未勾选时不建目录、不建文件",
          w16._log_writer is None and not os.path.exists(w16.log_dir()),
          w16.log_dir())
    check("默认日志目录落在沙箱（不写开发机真实数据目录）",
          os.path.dirname(w16._config_path) != os.getcwd()
          and w16.log_dir().startswith(os.path.dirname(w16._config_path)),
          w16.log_dir())
    _before = w16.log_text.toPlainText().splitlines()
    w16.chk_auto_save_log.setChecked(True)
    QApplication.processEvents()
    check("勾选后文件已创建",
          w16._log_writer is not None and os.path.exists(w16._log_writer.path),
          str(w16._log_writer))
    path16 = w16._log_writer.path if w16._log_writer else ""
    with open(path16, encoding="utf-8") as _fh:
        _body = _fh.read()
    check("文件头含标题 / 开始时间 / 串口",
          "# 串口工具日志" in _body and "# 开始时间:" in _body
          and "COM9 @ 9600" in _body, str(_body.splitlines()[:3]))
    check("开始保存时打过路径日志（面板可见、可复制）",
          any("开始保存到" in ln
              for ln in w16.log_text.toPlainText().splitlines()))
    check("状态标签显示「保存中」与行数",
          "保存中" in w16.lbl_log_state.text()
          and ".log" in w16.lbl_log_state.text(),
          w16.lbl_log_state.text())
    check("状态标签 tooltip 给出完整路径",
          path16 in w16.lbl_log_state.toolTip(), w16.lbl_log_state.toolTip())

    # TX / RX 原始行都进文件（写入点挂在 _log 单一出口上）
    w16.commands = [{"name": "读版本", "data_hex": "68 16", "match_type": "none",
                     "match_hex": "", "protocol": None, "enabled": True}]
    w16._rebuild_cmd_table()
    _mark = len(w16.log_text.toPlainText().splitlines())
    w16._on_sent(0, 0, b"\x68\x16")
    w16._on_raw_data(b"\x68\x16")
    w16._flush_raw_display_now()
    w16._flush_log_queues()
    with open(path16, encoding="utf-8") as _fh:
        _body = _fh.read()
    check("发送原始行进文件", "[TX] #1 读版本 68 16" in _body,
          str([ln for ln in _body.splitlines() if "[TX]" in ln]))
    check("接收原始行进文件", "[RX] 68 16" in _body,
          str([ln for ln in _body.splitlines() if "[RX]" in ln]))
    _new_lines = w16.log_text.toPlainText().splitlines()[_mark:]
    check("面板新增的每一行都在文件里（文件 = 面板镜像）",
          bool(_new_lines) and all(ln in _body for ln in _new_lines),
          str(_new_lines))

    # 「显示发送」关掉 → 行不进面板也不进文件（不存在第二套过滤规则）
    w16.chk_show_tx.setChecked(False)
    w16._on_sent(1, 0, b"\xAA\xBB")
    w16._flush_log_queues()
    with open(path16, encoding="utf-8") as _fh:
        check("「显示发送」关闭 → 该行不进文件（与面板同规则）",
              "[TX] #2" not in _fh.read())
    w16.chk_show_tx.setChecked(True)

    # 行首时间戳开关立即生效
    w16.chk_log_timestamp.setChecked(False)
    check("时间戳开关立即作用于当前文件",
          w16._log_writer is not None and w16._log_writer.timestamp is False)
    w16._log("[系统] 无前缀行")
    with open(path16, encoding="utf-8") as _fh:
        check("关掉后写入的行无时间戳前缀",
              "[系统] 无前缀行" in _fh.read().splitlines())
    w16.chk_log_timestamp.setChecked(True)

    w16.chk_auto_save_log.setChecked(False)
    QApplication.processEvents()
    with open(path16, encoding="utf-8") as _fh:
        _body = _fh.read()
    check("取消勾选 → 写统计尾并关闭",
          w16._log_writer is None and "# 停止时间:" in _body
          and "# 收发统计:" in _body, str(_body.splitlines()[-2:]))
    check("统计尾为真实计数（发送 2 帧 / 4 B，接收 1 帧 / 2 B）",
          "发送 2 帧 / 4 B" in _body and "接收 1 帧 / 2 B" in _body,
          str([ln for ln in _body.splitlines() if "统计" in ln]))
    check("状态标签转为已停止",
          "已停止" in w16.lbl_log_state.text(), w16.lbl_log_state.text())
    check("停止后不再写文件（粒度：文件大小不变）",
          w16._log_writer is None
          and os.path.getsize(path16) == len(_body.encode("utf-8")),
          f"{os.path.getsize(path16)} vs {len(_body.encode('utf-8'))}")
    w16.cleanup()

    # ── 写失败：必须告知用户并自动关闭（不静默丢日志）──
    w17 = stw.SerialToolWidget()
    w17.set_serial_worker(FakeWorker())
    w17.chk_show_parse.setChecked(False)
    w17.chk_auto_save_log.setChecked(True)
    check("w17 已开始保存", w17._log_writer is not None)
    w17._log_writer._fh.close()            # 模拟句柄失效（目录被删/磁盘满同类）
    w17._log("[系统] 触发写失败")
    check("写失败后自动保存被关闭",
          w17._log_writer is None and w17.chk_auto_save_log.isChecked() is False)
    check("写失败在面板给出可读提示（不静默）",
          any("写入文件失败" in ln
              for ln in w17.log_text.toPlainText().splitlines()),
          str(w17.log_text.toPlainText().splitlines()[-1:]))
    check("失败提示只出现一次（不走递归）",
          sum(1 for ln in w17.log_text.toPlainText().splitlines()
              if "写入文件失败" in ln) == 1)
    w17.cleanup()

    # ── 目录不可用：勾选回弹 + 弹窗 ──
    _crit = {"n": 0}
    _orig_critical = stw.QMessageBox.critical
    stw.QMessageBox.critical = staticmethod(
        lambda *a, **k: _crit.__setitem__("n", _crit["n"] + 1) or 0
    )
    try:
        w18 = stw.SerialToolWidget()
        w18.set_serial_worker(FakeWorker())
        _blocked_dir = os.path.join(tempfile.mkdtemp(), "blocked_file")
        open(_blocked_dir, "w", encoding="utf-8").close()   # 是文件，不能当目录
        w18._params["log_dir"] = _blocked_dir
        w18.chk_auto_save_log.setChecked(True)
        QApplication.processEvents()
    finally:
        stw.QMessageBox.critical = _orig_critical
    check("目录不可用时勾选回弹为未勾选",
          w18.chk_auto_save_log.isChecked() is False)
    check("目录不可用时弹窗告知（不静默）", _crit["n"] >= 1, str(_crit))
    check("目录不可用时没有开启写入", w18._log_writer is None)
    check("目录不可用时面板有失败说明",
          any("无法创建日志文件" in ln
              for ln in w18.log_text.toPlainText().splitlines()),
          str(w18.log_text.toPlainText().splitlines()[-1:]))
    w18.cleanup()

    # ── 偏好持久化：勾选状态 / 目录 / 时间戳开关 ──
    _new_dir = tempfile.mkdtemp(prefix="nw_logdir_")
    _orig_dir_dlg = stw.QFileDialog.getExistingDirectory
    stw.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: _new_dir)
    w19 = stw.SerialToolWidget()
    w19.set_serial_worker(FakeWorker())
    try:
        w19._choose_log_dir()
    finally:
        stw.QFileDialog.getExistingDirectory = _orig_dir_dlg
    w19._save_persisted()                  # 落盘是 500ms 去抖，测试里直接触发
    with open(w19._config_path, encoding="utf-8") as _fh:
        _saved = json.load(_fh)["params"]
    check("选择目录后生效并落盘",
          w19.log_dir() == _new_dir and _saved["log_dir"] == _new_dir,
          f"{w19.log_dir()} / {_saved.get('log_dir')}")
    w19.chk_log_timestamp.setChecked(False)
    w19.chk_auto_save_log.setChecked(True)
    w19._save_persisted()
    with open(w19._config_path, encoding="utf-8") as _fh:
        _saved = json.load(_fh)["params"]
    check("自动保存勾选 + 时间戳偏好已落盘",
          _saved["log_auto_save"] is True and _saved["log_timestamp"] is False,
          str({k: _saved[k] for k in ("log_auto_save", "log_timestamp")}))
    w19.cleanup()

    w20 = stw.SerialToolWidget()
    check("重启后自动开始保存（偏好记住）",
          w20.chk_auto_save_log.isChecked() is True
          and w20._log_writer is not None
          and os.path.dirname(w20._log_writer.path) == _new_dir,
          str(w20._log_writer))
    check("重启后目录与时间戳偏好一致",
          w20.log_dir() == _new_dir and w20.chk_log_timestamp.isChecked() is False)
    w20._log("[系统] 无前缀持久化")
    with open(w20._log_writer.path, encoding="utf-8") as _fh:
        check("重启后的文件沿用「无时间戳」偏好",
              "[系统] 无前缀持久化" in _fh.read().splitlines())

    # ── 手动「保存当前日志…」──
    _snapshot = w20.log_text.toPlainText()
    _manual2 = os.path.join(tempfile.mkdtemp(prefix="nw_manual_"), "manual.log")
    _orig_save_dlg = stw.QFileDialog.getSaveFileName
    stw.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_manual2, ""))
    try:
        w20._save_log_now()
    finally:
        stw.QFileDialog.getSaveFileName = _orig_save_dlg
    with open(_manual2, encoding="utf-8") as _fh:
        check("手动保存内容 = 日志窗口内容",
              _fh.read().rstrip("\n") == _snapshot.rstrip("\n"),
              f"{os.path.getsize(_manual2)} B")
    check("手动保存不影响自动保存（仍在写）", w20._log_writer is not None)
    w20.cleanup()

    # ── cleanup：残留队列也进文件（不丢最后几帧）──
    w21 = stw.SerialToolWidget()
    w21.chk_auto_save_log.setChecked(True)
    check("w21 已开始保存", w21._log_writer is not None)
    path21 = w21._log_writer.path
    w21._rx_log_queue.append(("raw", "68 16"))
    w21.cleanup()
    with open(path21, encoding="utf-8") as _fh:
        _body = _fh.read()
    check("cleanup 把残留队列刷进文件", "[RX] 68 16" in _body,
          str(_body.splitlines()[-3:]))
    check("cleanup 后文件已关闭", w21._log_writer is None)
    check("cleanup 保留勾选（当作偏好，下次启动仍自动保存）",
          w21.chk_auto_save_log.isChecked() is True)
    w21.cleanup()
    check("cleanup 幂等不崩", True)
    w20.cleanup()

    section("[32] 命令状态图标（名称列：PASS/FAIL/发送中/错误）")
    check("状态字典覆盖 5 态（待测/发送中/通过/失败/错误）",
          set(stw.CMD_STATUS_STYLES) == {"", "running", "pass", "fail", "error"},
          str(sorted(stw.CMD_STATUS_STYLES)))
    check("每态都有图标名与颜色",
          all(len(v) == 2 and v[0] and v[1].startswith("#")
              for v in stw.CMD_STATUS_STYLES.values()),
          str(stw.CMD_STATUS_STYLES))
    check("状态中文文案", [stw.status_text(s) for s in
                          ("", "running", "pass", "fail", "error")]
          == ["待测", "发送中", "通过", "失败", "错误"],
          str([stw.status_text(s) for s in ("", "running", "pass", "fail", "error")]))
    check("未知状态文案回落「待测」", stw.status_text("bogus") == "待测")

    def _icon_colors(icon, size=14):
        img = icon.pixmap(size, size).toImage()
        out = set()
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c.alpha() > 200:
                    out.add((c.red(), c.green(), c.blue()))
        return out

    def _near(cols, hex_color, tol=3):
        want = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
        return any(all(abs(a - b) <= tol for a, b in zip(c, want)) for c in cols)

    for _st, (_icon_name, _color) in stw.CMD_STATUS_STYLES.items():
        _ic = stw.status_icon(_st)
        check(f"状态「{stw.status_text(_st)}」图标非空且按状态上色（{_color}）",
              not _ic.isNull() and _near(_icon_colors(_ic), _color),
              f"null={_ic.isNull()} colors={sorted(_icon_colors(_ic))[:3]}")
    check("未知状态回落「待测」图标（不空、不上错色）",
          not stw.status_icon("bogus").isNull()
          and _near(_icon_colors(stw.status_icon("bogus")), "#9E9E9E"))
    check("图标有缓存（同一状态返回同一对象）",
          stw.status_icon("pass") is stw.status_icon("pass"))
    check("五态图标两两不同（形状可区分）",
          len({stw.CMD_STATUS_STYLES[s][0] for s in stw.CMD_STATUS_STYLES}) == 5,
          str([stw.CMD_STATUS_STYLES[s][0] for s in stw.CMD_STATUS_STYLES]))

    # 表格渲染：名称列带图标 + 配色 + tooltip
    w18 = stw.SerialToolWidget()
    w18.set_parse_provider(None)
    w18.chk_show_parse.setChecked(False)
    w18.commands = [
        {"name": "待测项", "data_hex": "01", "match_type": "none",
         "match_hex": "", "protocol": None, "enabled": True},
        {"name": "通过项", "data_hex": "02", "match_type": "none",
         "match_hex": "", "protocol": None, "enabled": True,
         "_status": "pass"},
        {"name": "失败项", "data_hex": "03", "match_type": "none",
         "match_hex": "", "protocol": None, "enabled": True,
         "_status": "fail"},
    ]
    w18._rebuild_cmd_table()
    check("名称列（第 1 列）带状态图标",
          not w18.cmd_table.item(0, 1).icon().isNull()
          and not w18.cmd_table.item(1, 1).icon().isNull())
    check("通过/失败项图标颜色不同（按不透明像素比较）",
          _icon_colors(w18.cmd_table.item(1, 1).icon())
          != _icon_colors(w18.cmd_table.item(2, 1).icon())
          and _near(_icon_colors(w18.cmd_table.item(1, 1).icon()), "#008000")
          and _near(_icon_colors(w18.cmd_table.item(2, 1).icon()), "#C00000"),
          f"{sorted(_icon_colors(w18.cmd_table.item(1, 1).icon()))[:2]} / "
          f"{sorted(_icon_colors(w18.cmd_table.item(2, 1).icon()))[:2]}")
    check("tooltip 说明状态",
          "通过" in w18.cmd_table.item(1, 1).toolTip()
          and "失败" in w18.cmd_table.item(2, 1).toolTip()
          and "待测" in w18.cmd_table.item(0, 1).toolTip(),
          f"{w18.cmd_table.item(0, 1).toolTip()} / {w18.cmd_table.item(1, 1).toolTip()}")
    check("名称文字未被图标覆盖", w18.cmd_table.item(1, 1).text() == "通过项")
    check("状态机读回正确", [w18._cmd_status(i) for i in range(3)]
          == ["", "pass", "fail"], str([w18._cmd_status(i) for i in range(3)]))

    # 状态迁移：发送 → 发送中/通过；匹配成功 → 通过；超时 → 失败；发送失败 → 错误
    w18.chk_match.setChecked(True)
    w18.commands = [
        {"name": "要匹配", "data_hex": "01", "match_type": "contains",
         "match_hex": "AA", "protocol": None, "enabled": True},
        {"name": "不匹配", "data_hex": "02", "match_type": "none",
         "match_hex": "", "protocol": None, "enabled": True},
    ]
    w18._rebuild_cmd_table()
    w18._reset_stats()
    w18._tx_log_queue.clear()
    w18._rx_log_queue.clear()
    w18._on_sent(0, 0, b"\x01")
    check("发出后进入「发送中」", w18._cmd_status(0) == "running",
          w18._cmd_status(0))
    check("表格已同步刷新（不用整表重建）",
          "发送中" in w18.cmd_table.item(0, 1).toolTip())
    w18._on_raw_data(b"\xAA")
    check("匹配成功 → 通过", w18._cmd_status(0) == "pass", w18._cmd_status(0))
    w18._on_sent(1, 1, b"\x02")
    check("无需匹配的命令 → 直接「通过」", w18._cmd_status(1) == "pass",
          w18._cmd_status(1))
    # 超时 → 失败
    w18._reset_stats()
    w18.commands = [{"name": "会超时", "data_hex": "03",
                     "match_type": "contains", "match_hex": "ZZ".replace("Z", "F"),
                     "protocol": None, "enabled": True}]
    w18._rebuild_cmd_table()
    w18._on_sent(0, 0, b"\x03")
    check("等待中", w18._cmd_status(0) == "running", w18._cmd_status(0))
    w18._pending_match[0]["sent_time"] = time.perf_counter() - 10
    w18.timeout_spin.setValue(10)
    w18._check_match_timeout()
    check("超时未匹配 → 失败", w18._cmd_status(0) == "fail", w18._cmd_status(0))
    check("失败图标已上到名称列",
          "失败" in w18.cmd_table.item(0, 1).toolTip())
    w18.timeout_spin.setValue(5000)
    # 发送失败 → 错误
    w18.commands = [{"name": "写失败", "data_hex": "04",
                     "match_type": "contains", "match_hex": "AA",
                     "protocol": None, "enabled": True}]
    w18._rebuild_cmd_table()
    w18._on_sent(0, 0, b"\x04")
    check("等待中（准备写失败）", w18._cmd_status(0) == "running")
    w18._on_send_failed("模拟写串口失败")
    check("发送失败 → 仍在等待的记为「错误」", w18._cmd_status(0) == "error",
          w18._cmd_status(0))
    # 每轮开始重置
    w18.commands = [{"name": "A", "data_hex": "05", "match_type": "none",
                     "match_hex": "", "protocol": None, "enabled": True,
                     "_status": "fail"},
                    {"name": "B", "data_hex": "06", "match_type": "none",
                     "match_hex": "", "protocol": None, "enabled": True,
                     "_status": "pass"}]
    w18._rebuild_cmd_table()
    w18._clear_cmd_statuses()
    check("每轮开始清空状态（回到待测）",
          [w18._cmd_status(i) for i in range(2)] == ["", ""],
          str([w18._cmd_status(i) for i in range(2)]))
    # 运行时状态不落盘 / 不导出
    check("export_commands 剔除 _status（运行态不落盘）",
          all("_status" not in c for c in stw.export_commands(w18.commands)),
          str(stw.export_commands(w18.commands)[0]))
    check("normalize_command 不产生 _status（读回即待测）",
          "_status" not in stw.normalize_command(
              {"name": "x", "data_hex": "01", "match_type": "none",
               "match_hex": "", "_status": "pass"}))
    check("图例文案包含五种状态",
          all(k in ("○ 待测  ↻ 发送中  ✓ 通过  ✗ 失败  ⚠ 错误")
              for k in ("待测", "发送中", "通过", "失败", "错误")))
    w18.cleanup()

    section("[33] 命令状态可手动清理")
    w19 = stw.SerialToolWidget()
    w19.set_parse_provider(None)
    w19.chk_show_parse.setChecked(False)
    w19.commands = [
        {"name": "甲", "data_hex": "01", "match_type": "contains",
         "match_hex": "AA", "protocol": 7, "enabled": True, "_status": "pass"},
        {"name": "乙", "data_hex": "02", "match_type": "none",
         "match_hex": "", "protocol": None, "enabled": False, "_status": "fail"},
        {"name": "丙", "data_hex": "03", "match_type": "none",
         "match_hex": "", "protocol": None, "enabled": True, "_status": "running"},
    ]
    w19._rebuild_cmd_table()
    check("清除状态按钮存在且带图标",
          w19.btn_clear_status.text() == "清除状态"
          and not w19.btn_clear_status.icon().isNull(),
          w19.btn_clear_status.text())
    check("清除前三种状态都在",
          [w19._cmd_status(i) for i in range(3)] == ["pass", "fail", "running"],
          str([w19._cmd_status(i) for i in range(3)]))
    check("清除前图标配色各异（通过/失败/发送中）",
          _near(_icon_colors(w19.cmd_table.item(0, 1).icon()), "#008000")
          and _near(_icon_colors(w19.cmd_table.item(1, 1).icon()), "#C00000")
          and _near(_icon_colors(w19.cmd_table.item(2, 1).icon()), "#1565C0"))
    w19.btn_clear_status.click()               # 走真实按钮信号
    QApplication.processEvents()
    check("点击后全部回到「待测」",
          [w19._cmd_status(i) for i in range(3)] == ["", "", ""],
          str([w19._cmd_status(i) for i in range(3)]))
    check("图标全部变成「待测」灰",
          all(_near(_icon_colors(w19.cmd_table.item(i, 1).icon()), "#9E9E9E")
              for i in range(3)),
          str([sorted(_icon_colors(w19.cmd_table.item(i, 1).icon()))[:1]
               for i in range(3)]))
    check("tooltip 同步为「待测」",
          all("待测" in w19.cmd_table.item(i, 1).toolTip() for i in range(3)),
          str([w19.cmd_table.item(i, 1).toolTip() for i in range(3)]))
    check("命令内容不被清除影响",
          [c["name"] for c in w19.commands] == ["甲", "乙", "丙"]
          and w19.commands[0]["data_hex"] == "01"
          and w19.commands[0]["match_hex"] == "AA"
          and w19.commands[0]["protocol"] == 7,
          str(w19.commands[0]))
    check("勾选状态不被清除影响",
          [c["enabled"] for c in w19.commands] == [True, False, True],
          str([c["enabled"] for c in w19.commands]))
    check("名称文字仍在", w19.cmd_table.item(1, 1).text() == "乙")
    check("清除后 _status 键被移除（运行态不残留）",
          all(stw.CMD_STATUS_KEY not in c for c in w19.commands))
    check("清除后导出里没有 _status",
          all("_status" not in c for c in stw.export_commands(w19.commands)))
    check("重复清除幂等（不抛、仍全待测）",
          w19._clear_cmd_statuses() is None
          and [w19._cmd_status(i) for i in range(3)] == ["", "", ""])
    # 发送中禁止清除（与「清除统计」同一口径）
    w19._set_cmd_status(0, "pass")
    w19._running = True
    w19.btn_clear_status.click()
    QApplication.processEvents()
    check("发送中点清除 → 不生效（状态保持）", w19._cmd_status(0) == "pass",
          w19._cmd_status(0))
    w19._running = False
    w19.btn_clear_status.click()
    QApplication.processEvents()
    check("停止后可清除", w19._cmd_status(0) == "", w19._cmd_status(0))
    # 空命令表也安全
    w19.commands = []
    w19._rebuild_cmd_table()
    w19.btn_clear_status.click()
    QApplication.processEvents()
    check("空命令表点清除不抛异常", w19.cmd_table.rowCount() == 0)
    w19.cleanup()

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）✓")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
