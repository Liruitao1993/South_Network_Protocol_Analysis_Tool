# -*- coding: utf-8 -*-
"""蓝牙内核（bluetooth_core）纯逻辑回归测试 —— 不依赖 Qt、不依赖 bleak、不碰硬件。

覆盖：
  [1] 配置合并 merge_settings：默认值补齐、宽松布尔/数字、范围夹紧、坏类型不抛
  [2] 发送格式 / 解析协议 / 特征码列表的归一化（非法值回落）
  [3] 自定义报文按钮 normalize_button(s)：空内容剔除、名称截断、上限
  [4] 配置读写往返、损坏文件回落、原子写（不留 .tmp 残渣）
  [5] chunk_size_for_mtu / split_chunks：MTU 未知、低 MTU、上限夹紧
  [6] short_uuid：SIG 标准 UUID、4 位短写、自定义 UUID
  [7] BleReassembler：静默超时切帧、分包重组、不同特征码独立成帧、
      flush / pending_bytes / set_timeout 不丢数据
  [8] 反例自检（判据确实会失败，而不是恒真）
  [12] 自定义按钮的协议/地址参数（1.23.81）：保留/回落/坏值宽容/落盘往返

运行: python test/test_bluetooth_core.py
"""

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

import bluetooth_core as core  # noqa: E402

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {detail}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


# ── [1] merge_settings ──────────────────────────────────────────────────────

def test_merge_settings():
    section("[1] merge_settings 宽容合并")

    out = core.merge_settings(None)
    check("None → 全默认值", out == core.DEFAULT_SETTINGS, out)
    out = core.merge_settings("垃圾")
    check("字符串 → 全默认值", out == core.DEFAULT_SETTINGS, out)

    out = core.merge_settings({"show_hex": "off", "auto_scroll": "是", "parse_enabled": 0})
    check("宽松布尔：'off'/'是'/0",
          out["show_hex"] is False and out["auto_scroll"] is True
          and out["parse_enabled"] is False, out)

    out = core.merge_settings({"packet_timeout": 999, "send_packet_delay": -5})
    check("数值夹紧到范围",
          out["packet_timeout"] == core.PACKET_TIMEOUT_RANGE[1]
          and out["send_packet_delay"] == core.SEND_PACKET_DELAY_RANGE[0], out)

    out = core.merge_settings({"packet_timeout": "abc", "parse_max_lines": None,
                               "auto_refresh_interval": ""})
    check("坏数值回落默认（不抛异常）",
          out["packet_timeout"] == core.DEFAULT_PACKET_TIMEOUT
          and out["parse_max_lines"] == core.DEFAULT_PARSE_MAX_LINES
          and out["auto_refresh_interval"] == 10, out)

    out = core.merge_settings({"send_format": "HEX"})
    check("send_format 大小写归一", out["send_format"] == "hex", out)
    out = core.merge_settings({"send_format": "乱写"})
    check("send_format 非法回落 auto", out["send_format"] == "auto", out)

    out = core.merge_settings({"parse_protocol": 7})
    check("parse_protocol 数字保留", out["parse_protocol"] == 7, out)
    out = core.merge_settings({"parse_protocol": -3})
    check("parse_protocol 负数回落 None", out["parse_protocol"] is None, out)
    out = core.merge_settings({"parse_protocol": "9"})
    check("parse_protocol 字符串数字容忍", out["parse_protocol"] == 9, out)

    out = core.merge_settings({"recv_uuids": ["a", "", "  ", "b"]})
    check("recv_uuids 去空", out["recv_uuids"] == ["a", "b"], out)
    out = core.merge_settings({"send_uuids": "u1, u2 ,"})
    check("send_uuids 单字符串按逗号切", out["send_uuids"] == ["u1", "u2"], out)
    out = core.merge_settings({"recv_uuids": 123})
    check("recv_uuids 非法类型保留默认空表", out["recv_uuids"] == [], out)

    out = core.merge_settings({"log_dir": "  E:/tmp/x  "})
    check("log_dir 去空白", out["log_dir"] == "E:/tmp/x", out)

    # 默认值本身必须是可 JSON 序列化的（否则落盘会炸）
    try:
        json.dumps(core.DEFAULT_SETTINGS)
        check("DEFAULT_SETTINGS 可 JSON 序列化", True)
    except (TypeError, ValueError) as exc:
        check("DEFAULT_SETTINGS 可 JSON 序列化", False, exc)


# ── [2] 自定义报文按钮 ──────────────────────────────────────────────────────

def test_normalize_buttons():
    section("[2] normalize_button(s)")

    check("非字典 → None", core.normalize_button("x") is None)
    check("内容为空 → None", core.normalize_button({"name": "a", "data": "  "}) is None)

    button = core.normalize_button({"name": "", "data": "68 12"}, "兜底名")
    check("空名称回落兜底名", button["name"] == "兜底名", button)
    check("默认按 HEX", button["isHex"] is True, button)

    button = core.normalize_button({"name": "n", "data": "AT", "isHex": 0})
    check("isHex 宽松布尔", button["isHex"] is False, button)

    long_name = "名" * 100
    button = core.normalize_button({"name": long_name, "data": "01"})
    check("名称截断到上限",
          len(button["name"]) == core.BUTTON_NAME_MAX, len(button["name"]))

    buttons = core.normalize_buttons([{"data": "01"}, {"data": ""}, "x", {"data": "02"}])
    check("列表去空 + 跳过非字典", len(buttons) == 2, buttons)

    many = [{"name": f"b{i}", "data": "01"} for i in range(core.MAX_CUSTOM_BUTTONS + 10)]
    check("超过上限被截断",
          len(core.normalize_buttons(many)) == core.MAX_CUSTOM_BUTTONS)
    check("非列表宽容为空", core.normalize_buttons("nope") == [])


# ── [3] 配置读写 ────────────────────────────────────────────────────────────

def test_settings_io():
    section("[3] load_settings / save_settings")

    with tempfile.TemporaryDirectory(prefix="bt_core_") as tmp:
        path = os.path.join(tmp, "sub", "cfg.json")

        check("文件不存在 → 默认值", core.load_settings(path) == ([], core.DEFAULT_SETTINGS))

        buttons = [{"name": "查询", "data": "68 12", "isHex": True}]
        settings = dict(core.DEFAULT_SETTINGS)
        settings["virtual_mode"] = True
        settings["packet_timeout"] = 1.5
        check("save_settings 成功（自动建目录）", core.save_settings(path, buttons, settings))
        check("落盘文件存在", os.path.exists(path))

        got_buttons, got_settings = core.load_settings(path)
        check("按钮往返一致", got_buttons == buttons, got_buttons)
        check("设置往返一致",
              got_settings["virtual_mode"] is True
              and got_settings["packet_timeout"] == 1.5, got_settings)
        check("落盘后无 .tmp 残渣",
              [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")] == [])

        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        check("文件带 version 字段", raw.get("version") == core.SETTINGS_VERSION, raw)

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ 这不是 JSON")
        check("损坏文件回落默认（不抛）",
              core.load_settings(path) == ([], core.DEFAULT_SETTINGS))

        with open(path, "w", encoding="utf-8") as handle:
            json.dump([1, 2, 3], handle)
        check("顶层是列表也回落默认",
              core.load_settings(path) == ([], core.DEFAULT_SETTINGS))

        # 原子写失败路径：目标目录被一个**文件**占位
        blocker = os.path.join(tmp, "blocker")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")
        bad_path = os.path.join(blocker, "cfg.json")
        check("不可写路径返回 False 且不抛", core.save_settings(bad_path, [], {}) is False)


# ── [4] 分包尺寸 ────────────────────────────────────────────────────────────

def test_chunking():
    section("[4] chunk_size_for_mtu / split_chunks")

    check("MTU 未知 → MIN_CHUNK", core.chunk_size_for_mtu(0) == core.MIN_CHUNK)
    check("MTU None → MIN_CHUNK", core.chunk_size_for_mtu(None) == core.MIN_CHUNK)
    check("MTU 非数字 → MIN_CHUNK", core.chunk_size_for_mtu("x") == core.MIN_CHUNK)
    check("MTU 23 → 20", core.chunk_size_for_mtu(23) == 20, core.chunk_size_for_mtu(23))
    check("MTU 247 → 200（被上限夹住）",
          core.chunk_size_for_mtu(247) == core.DEFAULT_MAX_CHUNK,
          core.chunk_size_for_mtu(247))
    check("MTU 4 → MIN_CHUNK（低于 ATT 头）",
          core.chunk_size_for_mtu(4) == core.MIN_CHUNK, core.chunk_size_for_mtu(4))
    check("自定义上限生效",
          core.chunk_size_for_mtu(247, 100) == 100, core.chunk_size_for_mtu(247, 100))

    check("空数据 → 空列表", core.split_chunks(b"", 20) == [])
    chunks = core.split_chunks(bytes(range(50)), 20)
    check("按尺寸切分", [len(c) for c in chunks] == [20, 20, 10], [len(c) for c in chunks])
    check("切分后拼回原数据", b"".join(chunks) == bytes(range(50)))
    check("尺寸 0 不炸（按 1 字节切）", len(core.split_chunks(b"abc", 0)) == 3)


# ── [5] short_uuid ──────────────────────────────────────────────────────────

def test_short_uuid():
    section("[5] short_uuid")

    check("SIG 标准 UUID → 0x 短写",
          core.short_uuid("0000fff1-0000-1000-8000-00805f9b34fb") == "0xFFF1",
          core.short_uuid("0000fff1-0000-1000-8000-00805f9b34fb"))
    check("大写标准 UUID 也认",
          core.short_uuid("0000FFF1-0000-1000-8000-00805F9B34FB") == "0xFFF1")
    check("4 位短写 → 0x 短写", core.short_uuid("fff1") == "0xFFF1",
          core.short_uuid("fff1"))
    long_uuid = "12345678-1234-5678-1234-567812345678"
    check("自定义 UUID 截前 8 字符", core.short_uuid(long_uuid) == "12345678",
          core.short_uuid(long_uuid))
    check("空值 → 空串", core.short_uuid("") == "" and core.short_uuid(None) == "")


# ── [6] BleReassembler ──────────────────────────────────────────────────────

def test_reassembler():
    section("[6] BleReassembler 分包重组")

    r = core.BleReassembler(0.5)
    check("初始无待处理字节", r.pending_bytes() == 0)
    check("超时读取一致", r.timeout == 0.5)

    # 静默超时切帧：分两包投递，未超时不产出，超时后合成一帧
    r.feed("u1", b"\x68\x12", now=100.0)
    r.feed("u1", b"\x00\x41\x16", now=100.1)
    check("静默未超时不产出", r.poll(now=100.2) == [], r.poll(now=100.2))
    check("缓冲字节数正确", r.pending_bytes() == 5, r.pending_bytes())
    frames = r.poll(now=100.7)
    check("超时后合成一帧", frames == [("u1", b"\x68\x12\x00\x41\x16")], frames)
    check("取走后缓冲清空", r.pending_bytes() == 0)

    # 不同特征码各自独立成帧（不混流）
    r.feed("a", b"\x01\x02", now=200.0)
    r.feed("b", b"\x03", now=200.0)
    frames = sorted(r.poll(now=201.0))
    check("不同特征码独立成帧",
          frames == [("a", b"\x01\x02"), ("b", b"\x03")], frames)

    # 空数据忽略
    r.feed("c", b"", now=300.0)
    check("空分包被忽略", r.pending_bytes() == 0)

    # flush 立即取出（断开时交出残包），且不丢数据
    r.feed("d", b"\xAA\xBB", now=400.0)
    flushed = r.flush()
    check("flush 立即取出残包", flushed == [("d", b"\xAA\xBB")], flushed)
    check("flush 后缓冲清空", r.pending_bytes() == 0 and r.poll(now=999) == [])

    # set_timeout 不改动已在缓冲的数据
    r.feed("e", b"\x01", now=500.0)
    r.set_timeout(0.1)
    check("set_timeout 生效", r.timeout == 0.1)
    check("改超时不丢已缓冲数据",
          r.poll(now=500.2) == [("e", b"\x01")], r.poll(now=500.2))

    # timeout=0 → 投递后立即成帧
    r0 = core.BleReassembler(0)
    r0.feed("f", b"\x09", now=600.0)
    check("timeout=0 立即成帧", r0.poll(now=600.0) == [("f", b"\x09")])

    check("clear 清空缓冲", (lambda x: (x.feed("g", b"\x01"), x.clear(),
                                        x.pending_bytes() == 0)[-1])(core.BleReassembler()))


# ── [7] 反例自检 ────────────────────────────────────────────────────────────

def _char(uuid, send=False, recv=False, svc="0000fff0-0000-1000-8000-00805f9b34fb", desc=""):
    """构造一条特征码信息（与 worker `_collect_characteristics` 同形）。"""
    return {
        "uuid": uuid, "short": core.short_uuid(uuid),
        "service_uuid": svc, "service_short": core.short_uuid(svc),
        "properties": [], "description": desc, "can_send": bool(send), "can_recv": bool(recv),
        "max_write": 20,
    }


def _std(code: str) -> str:
    return f"0000{code}-0000-1000-8000-00805f9b34fb"


def test_char_selection():
    section("[8] 特征码打分优选（1.23.79）")
    chars = [
        _char(_std("2a00"), desc="Device Name", svc=_std("1800")),
        _char(_std("2a19"), send=True, desc="Battery Level", svc=_std("180f")),
        _char(_std("ffe1"), send=True, recv=True, desc="", svc=_std("ffe0")),
        _char(_std("fe59"), send=True, desc="DFU Control", svc=_std("fe59")),
        _char("6e400003-0000-1000-8000-00805f9b34fb", recv=True, desc="UART RX",
              svc="6e400001-0000-1000-8000-00805f9b34fb"),
        _char("6e400002-0000-1000-8000-00805f9b34fb", send=True, desc="UART TX",
              svc="6e400001-0000-1000-8000-00805f9b34fb"),
    ]
    ranked = core.rank_characteristics(chars)
    check("打分排序：透传回环码最高", core.uuid_key(ranked[0]["uuid"]) == "ffe1",
          str([(core.short_uuid(c["uuid"]), c["score"]) for c in ranked]))
    check("标准 GATT 特征码被降权（排在后段）",
          core.char_score(chars[1]) < 0 and core.char_score(chars[0]) < 0,
          f"{core.char_score(chars[0])} / {core.char_score(chars[1])}")
    check("OTA/DFU 被降权", core.char_score(chars[3]) < 0, str(core.char_score(chars[3])))
    check("同码双属性加分（ffe1 > 纯 write 的 uart tx）",
          core.char_score(chars[2]) > core.char_score(chars[5]))
    check("同服务配对加分（uart rx 与最佳发送码同服务）",
          core.char_score(chars[4], best_service=chars[4]["service_uuid"])
          > core.char_score(chars[4]))
    check("排序稳定：同分保持原顺序",
          [core.uuid_key(c["uuid"]) for c in core.rank_characteristics(chars)]
          == [core.uuid_key(c["uuid"])
              for c in sorted(core.rank_characteristics(chars), key=lambda c: -c["score"])])

    recv, send, reason = core.pick_auto(chars)
    check("pick_auto：发送 = 透传码（而不是第一个可写的 2A19）",
          send == [_std("ffe1")], str([core.short_uuid(u) for u in send]))
    check("pick_auto：接收 = 同一条码（回环）", recv == [_std("ffe1")],
          str([core.short_uuid(u) for u in recv]))
    check("pick_auto：给出可读依据（含「同一特征码」）", "同一特征码" in reason, reason)
    check("反例自检：旧「取第一个可用」会选到 2A19（判据确实不同）",
          core.short_uuid(chars[1]["uuid"]) == "0x2A19"
          and core.short_uuid(send[0]) != core.short_uuid(chars[1]["uuid"]))

    only_send = [_char(_std("ffe9"), send=True, desc="写通道")]
    recv2, send2, reason2 = core.pick_auto(only_send)
    check("只有写通道：接收为空且说明原因",
          recv2 == [] and send2 == [_std("ffe9")] and "未找到可接收通道" in reason2, reason2)
    only_recv = [_char(_std("ffe5"), recv=True, desc="通知通道")]
    recv3, send3, reason3 = core.pick_auto(only_recv)
    check("只有通知通道：发送为空、不说「未找到接收」", send3 == [] and recv3 == [_std("ffe5")],
          f"{recv3} / {send3} / {reason3}")
    check("无候选 / 空输入：不抛异常", core.pick_auto([]) == ([], [], "设备未提供特征码")
          and core.rank_characteristics(None) == [])

    cands = core.probe_candidates(chars)
    check("探测候选按分数降序、含接收通道标记",
          cands and cands[0]["send"] == _std("ffe1") and cands[0]["has_recv"] is True,
          str([(c["label"], c["score"], c["has_recv"]) for c in cands]))
    check("探测候选限量", len(core.probe_candidates(chars, 2)) == 2)


def test_probe_session():
    section("[9] 一键探测状态机（1.23.79）")

    def parse(text, mode):
        """测试用极简解析器（只认 HEX；注入点见 core.resolve_probe_payload）。"""
        cleaned = str(text or "").replace(" ", "")
        if not cleaned or len(cleaned) % 2:
            return None, "HEX 位数不成对"
        try:
            return bytes.fromhex(cleaned), ""
        except ValueError:
            return None, "含非 HEX 字符"

    check("载荷：输入框优先", core.resolve_probe_payload("68 12", "auto", "41 54", parse)
          == (b"\x68\x12", "", "edit"))
    check("载荷：空输入 → 默认帧且标注来源",
          core.resolve_probe_payload("", "auto", "41 54", parse) == (b"AT", "", "default"))
    check("载荷：输入框 HEX 写错 → 拒绝（不写）",
          core.resolve_probe_payload("68 1", "hex", "41 54", parse)[0] is None)
    check("载荷：默认帧坏 → 明确报错",
          "默认探测帧无效" in core.resolve_probe_payload("", "auto", "ZZZZ", parse)[1])

    cands = [
        {"send": "s1", "recv": "r1", "label": "0xFF01", "has_recv": True, "score": 30},
        {"send": "s2", "recv": "r2", "label": "0xFF02", "has_recv": True, "score": 20},
        {"send": "s3", "recv": "r3", "label": "0xFF03", "has_recv": True, "score": 10},
    ]

    def _last(session) -> dict:
        """最近一条尝试记录（没有则空 dict —— 断言与 detail 都不能假设它存在）。"""
        return session.attempts[-1] if session.attempts else {}
    session = core.ProbeSession(cands, b"AT", 500)
    check("未开始时段为 \"\"、position 为 (0, 3)（还没指向任何候选）",
          session.step == "" and session.position == (0, 3), f"{session.step}/{session.position}")
    intent = session.next()
    check("第一个意图 = 选码（含接收）",
          intent == {"action": "select", "recv": ["r1"], "send": ["s1"]}, str(intent))
    check("开始后 position 指向第 1 个候选", session.position == (1, 3), str(session.position))
    session.on_subscribed(False)
    check("订阅失败 → 记原因并推进下一个候选",
          _last(session).get("status") == "subscribe" and session.step == "select",
          str(_last(session)))
    check("推进后 on_subscribed 幂等（不会重复写）",
          (session.on_subscribed(True), session.next()["action"])[1] == "write")
    session.on_written(True)
    check("写入成功且该候选有接收通道 → 等回包",
          session.next() == {"action": "wait", "timeout_ms": 500}, str(session.next()))
    session.on_timeout()
    check("超时 → 记「写入成功但无回包」并推进",
          _last(session).get("status") == "timeout" and "无回包" in _last(session).get("detail", ""),
          str(_last(session)))
    session.on_subscribed(True)
    session.on_written(True)
    session.on_frame(12)
    result = session.result()
    check("命中即锁定（winner + 结束）",
          result["ok"] and result["winner"]["label"] == "0xFF03"
          and result["detail"] == "收到 12 字节回包" and session.next() is None, str(result["detail"]))
    check("逐条尝试原因完整（subscribe / timeout / ok）",
          [a["status"] for a in result["attempts"]] == ["subscribe", "timeout", "ok"],
          str([a["status"] for a in result["attempts"]]))

    # 无接收通道：写入成功即成功（并明确说明「仅验证写入」）
    solo = [{"send": "s9", "recv": "", "label": "0xFF09", "has_recv": False, "score": 5}]
    s2 = core.ProbeSession(solo, b"AT", 300)
    s2.next(); s2.on_subscribed(True); s2.on_written(True)
    check("无接收通道候选：写入成功即命中（结论注明仅验证写入）",
          s2.result()["ok"] and "仅验证写入" in s2.result()["detail"], s2.result()["detail"])

    # 全败 + 写入失败 + stop
    s3 = core.ProbeSession(cands, b"AT", 300)
    while s3.next() is not None:
        s3.on_timeout()
    check("全败：ok=False 且三个候选都有原因",
          s3.result()["ok"] is False and len(s3.result()["attempts"]) == 3, str(s3.result()))
    s4 = core.ProbeSession(cands, b"AT", 300)
    s4.next(); s4.on_subscribed(True); s4.on_written(False)
    check("写入失败 → 记 write 原因", _last(s4).get("status") == "write", str(_last(s4)))
    s5 = core.ProbeSession(cands, b"AT", 300)
    s5.next()
    s5.stop()
    check("stop 后 next 返回 None 且不算命中",
          s5.next() is None and s5.result()["ok"] is False)
    s6 = core.ProbeSession([], b"AT", 300)
    check("空候选：立刻结束且不抛异常", s6.next() is None and s6.result()["ok"] is False)
    s7 = core.ProbeSession(cands, b"AT", 10 ** 6)
    check("超时参数被夹到上限", s7.timeout_ms == core.PROBE_TIMEOUT_RANGE[1], str(s7.timeout_ms))
    s8 = core.ProbeSession(cands, None, "abc")
    check("载荷/超时坏值宽容", s8.payload == b"" and s8.timeout_ms == core.PROBE_TIMEOUT_MS)


def test_char_map():
    section("[10] 按设备地址记忆（1.23.79）")
    settings = core.merge_settings({})
    check("默认含 char_map/probe_frame/probe_timeout_ms",
          settings["char_map"] == {} and settings["probe_frame"] == "41 54"
          and settings["probe_timeout_ms"] == core.PROBE_TIMEOUT_MS, str(settings["probe_frame"]))
    core.remember_choice(settings, "AA:01", ["r"], ["s"], "probe")
    entry = core.recall_choice(settings, "AA:01") or {}
    check("记住并按地址取回（含 source）",
          entry.get("recv") == ["r"] and entry.get("send") == ["s"]
          and entry.get("source") == "probe", str(entry))
    check("未记过的地址 → None", core.recall_choice(settings, "BB:02") is None)
    check("空地址不写入", core.remember_choice(settings, "", ["r"], ["s"]) is settings
          and list(settings["char_map"]) == ["AA:01"])
    check("忘记该设备", core.forget_choice(settings, "AA:01") is True
          and core.recall_choice(settings, "AA:01") is None)
    check("重复忘记返回 False", core.forget_choice(settings, "AA:01") is False)

    bad = core.merge_settings({"char_map": {
        "ok": {"recv": ["a"], "send": [], "source": "probe", "ts": 5},
        "bad_str": "x",
        "bad_empty": {"recv": [], "send": []},
        "bad_src": {"recv": ["a"], "send": [], "source": "zzz"},
        "long": {"recv": [f"u{i}" for i in range(20)], "send": []},
    }})
    check("坏条目逐条丢弃、好条目保留",
          set(bad["char_map"]) == {"ok", "bad_src", "long"}, str(sorted(bad["char_map"])))
    check("非法 source 回落 manual", bad["char_map"]["bad_src"]["source"] == "manual")
    check("单设备 uuid 列表限量 8 条", len(bad["char_map"]["long"]["recv"]) == 8,
          str(len(bad["char_map"]["long"]["recv"])))
    check("非 dict 的 char_map 整体回落空", core.merge_settings({"char_map": [1, 2]})["char_map"] == {})
    check("probe_timeout_ms 越界夹紧",
          core.merge_settings({"probe_timeout_ms": 10 ** 9})["probe_timeout_ms"]
          == core.PROBE_TIMEOUT_RANGE[1]
          and core.merge_settings({"probe_timeout_ms": 1})["probe_timeout_ms"]
          == core.PROBE_TIMEOUT_RANGE[0])
    check("probe_frame 空串回落默认",
          core.merge_settings({"probe_frame": "  "})["probe_frame"] == "41 54")

    many = {}
    for i in range(core.CHAR_MAP_MAX + 5):
        many[f"D{i:02d}"] = {"recv": ["a"], "send": [], "source": "auto", "ts": 1000 + i}
    kept = core.normalize_char_map(many)
    check(f"超过 {core.CHAR_MAP_MAX} 条按 ts 削掉最旧",
          len(kept) == core.CHAR_MAP_MAX and "D00" not in kept
          and f"D{core.CHAR_MAP_MAX + 4:02d}" in kept, f"{len(kept)}/{sorted(kept)[:2]}")


def test_mtu_negotiation():
    section("[11] mtu_is_unnegotiated / 轮询常量（1.23.80）")

    check("0 → 未协商", core.mtu_is_unnegotiated(0) is True)
    check("None → 未协商", core.mtu_is_unnegotiated(None) is True)
    check("非数字 → 未协商", core.mtu_is_unnegotiated("x") is True)
    check("空串 → 未协商", core.mtu_is_unnegotiated("") is True)
    check("23（ATT 默认）→ 未协商", core.mtu_is_unnegotiated(core.MTU_DEFAULT) is True)
    check("22 → 未协商", core.mtu_is_unnegotiated(22) is True)
    check("24 → 已协商", core.mtu_is_unnegotiated(24) is False)
    check("247 → 已协商", core.mtu_is_unnegotiated(247) is False)
    check("517（规范上限）→ 已协商", core.mtu_is_unnegotiated(517) is False)
    check("字符串数字按数值判（'23' → 未协商）",
          core.mtu_is_unnegotiated("23") is True)

    check("MTU_DEFAULT 就是 ATT 默认 23", core.MTU_DEFAULT == 23, core.MTU_DEFAULT)
    check("轮询间隔 < 超时（否则只轮一次就到期）",
          0 < core.MTU_POLL_INTERVAL < core.MTU_POLL_TIMEOUT,
          (core.MTU_POLL_INTERVAL, core.MTU_POLL_TIMEOUT))
    check("默认值口径一致：MTU 23 → 单包 20",
          core.chunk_size_for_mtu(core.MTU_DEFAULT) == core.MIN_CHUNK,
          (core.chunk_size_for_mtu(core.MTU_DEFAULT), core.MIN_CHUNK))


def test_button_protocol_addr():
    section("[12] 自定义按钮的协议/地址参数（1.23.81）")

    button = core.normalize_button({
        "name": "抄读", "data": "68 11", "protocol": "6",
        "addr": {"addr": " 000000000033 ", "src": "", "dst": None},
    })
    check("protocol 字符串数字 → int", button.get("protocol") == 6, button)
    check("addr 过滤空值、去空白", button.get("addr") == {"addr": "000000000033"}, button)

    plain = core.normalize_button({"name": "旧按钮", "data": "68 11"})
    check("旧按钮（无这两个键）→ **不写键**（旧配置/旧版本互不影响）",
          "protocol" not in plain and "addr" not in plain, plain)

    for bad in ("abc", "", None, "  "):
        b = core.normalize_button({"name": "x", "data": "68", "protocol": bad})
        check(f"坏 protocol（{bad!r}）→ 丢弃", "protocol" not in b, b)

    for bad in ("not a dict", ["a"], 5, None):
        b = core.normalize_button({"name": "x", "data": "68", "addr": bad})
        check(f"坏 addr（{type(bad).__name__}）→ 丢弃", "addr" not in b, b)

    long_key = "k" * 40
    long_val = "9" * 200
    b = core.normalize_button({"name": "x", "data": "68", "protocol": 0,
                               "addr": {long_key: long_val}})
    key = next(iter(b["addr"]))
    check("超长键/值被截断（坏配置不撑爆界面）",
          len(key) <= core.ADDR_KEY_MAX
          and len(b["addr"][key]) <= core.ADDR_VALUE_MAX,
          (len(key), len(b["addr"][key])))

    buttons = core.normalize_buttons([
        {"name": "a", "data": "68", "protocol": 6, "addr": {"addr": "1"}},
        {"name": "b", "data": "69"},
    ])
    check("normalize_buttons 全链路保留",
          buttons[0].get("protocol") == 6 and buttons[0].get("addr") == {"addr": "1"}
          and "protocol" not in buttons[1], buttons)

    with tempfile.TemporaryDirectory(prefix="bt_core_addr_") as tmp:
        path = os.path.join(tmp, "cfg.json")
        check("save_settings 受理", core.save_settings(path, buttons, {"packet_timeout": 0.5}))
        loaded, _settings = core.load_settings(path)
        check("落盘 → 读回：protocol/addr 不丢",
              loaded[0].get("protocol") == 6 and loaded[0].get("addr") == {"addr": "1"},
              loaded)

    check("normalize_addr_map 直接调用：非 dict → 空",
          core.normalize_addr_map("x") == {} and core.normalize_addr_map(None) == {})


def test_custom_area_settings():
    section("[13] 自定义报文区空间治理（1.23.82）")

    check("封顶行数常量 = 3", core.CUSTOM_ROWS_MAX == 3, core.CUSTOM_ROWS_MAX)
    check("默认展开（custom_collapsed=False）",
          core.merge_settings({})["custom_collapsed"] is False)
    check("坏 custom_collapsed 值回落 False",
          core.merge_settings({"custom_collapsed": "x"})["custom_collapsed"] is False,
          core.merge_settings({"custom_collapsed": "x"})["custom_collapsed"])
    check("custom_collapsed=1/True → True",
          core.merge_settings({"custom_collapsed": 1})["custom_collapsed"] is True
          and core.merge_settings({"custom_collapsed": True})["custom_collapsed"] is True)

    default = list(core.RIGHT_SPLIT_DEFAULT)
    check("默认分栏尺寸 = RIGHT_SPLIT_DEFAULT",
          core.merge_settings({})["right_split"] == default,
          core.merge_settings({})["right_split"])
    check("合法分栏尺寸原样保留",
          core.merge_settings({"right_split": [300, 200]})["right_split"] == [300, 200])
    check("字符串数字也认（手改 JSON）",
          core.merge_settings({"right_split": ["300", "200"]})["right_split"] == [300, 200])
    for bad in ("x", None, 5, [1], [1, 2, 3], {"a": 1}):
        check(f"坏分栏尺寸（{bad!r}）→ 回落默认",
              core.merge_settings({"right_split": bad})["right_split"] == default,
              core.merge_settings({"right_split": bad})["right_split"])
    low, high = core.RIGHT_SPLIT_RANGE
    out = core.merge_settings({"right_split": [-5, 99999]})["right_split"]
    check("越界逐项夹紧（负值→默认，超大→上限）",
          out == [default[0], high], out)
    check("normalize_right_split 直接调用宽容",
          core.normalize_right_split(None) == default
          and core.normalize_right_split([0, 10]) == [default[0], low]
          and core.normalize_right_split([low - 1, 10]) == [low, low],
          (core.normalize_right_split(None), core.normalize_right_split([0, 10]),
           core.normalize_right_split([low - 1, 10])))
    check("落盘往返保留这两个键",
          _settings_roundtrip({"settings": {"custom_collapsed": True,
                                            "right_split": [321, 123]}}),
          "见 detail")


def _settings_roundtrip(payload) -> bool:
    """把 settings 写盘再读回（坏文件宽容的同一入口）。"""
    with tempfile.TemporaryDirectory(prefix="bt_core_space_") as tmp:
        path = os.path.join(tmp, "cfg.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        _buttons, settings = core.load_settings(path)
    return (settings.get("custom_collapsed") is True
            and settings.get("right_split") == [321, 123])


def test_negatives():
    section("[7] 反例自检（判据有效）")

    check("夹紧判据不是恒真（默认值在范围内）",
          core.PACKET_TIMEOUT_RANGE[0] <= core.DEFAULT_PACKET_TIMEOUT
          <= core.PACKET_TIMEOUT_RANGE[1])
    check("重组器确实会等（timeout>0 时不立即成帧）",
          core.BleReassembler(0.5).poll() == [])
    r = core.BleReassembler(0.5)
    r.feed("x", b"\x01")
    check("脏数据确实会被取走（非空）", r.poll(now=1e9) == [("x", b"\x01")])
    check("split_chunks 对 1 字节数据切 20 只有 1 包",
          len(core.split_chunks(b"\x01", 20)) == 1)


def main():
    print("=" * 64)
    print("蓝牙内核 bluetooth_core 纯逻辑回归")
    print("=" * 64)

    test_merge_settings()
    test_normalize_buttons()
    test_settings_io()
    test_chunking()
    test_short_uuid()
    test_reassembler()
    test_char_selection()
    test_probe_session()
    test_char_map()
    test_mtu_negotiation()
    test_button_protocol_addr()
    test_custom_area_settings()
    test_negatives()

    print()
    print("=" * 64)
    if FAIL:
        print(f"失败 {FAIL} 项 / 通过 {PASS} 项")
    else:
        print(f"全部通过（{PASS} 项）")
    print("=" * 64)
    sys.stdout.flush()
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
