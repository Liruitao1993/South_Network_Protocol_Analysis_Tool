# -*- coding: utf-8 -*-
"""档案页「抄读数据项」：配置 + 组帧 + 点抄按项逐帧（协议7 / 国网 13H F1）。

跑法：``python test/test_gdw_archive_copy_items.py``（需要 offscreen Qt）。

锁住的口径：

- C1 698 单 OAD 组帧与现场实测报文**逐字节一致**（`05 01` GetRequestNormal）；
  645 单 DI 与既有实现逐字节一致。
- C2 698 多 OAD 用 GetRequestNormalList（`05 02`），解析器能回读成 OAD 列表。
- C3 STA 模块数据项（EB03xxxx）→ 698 映射 OAD（EB55 + DI1DI0），
  国网《附件1 V3.42》「通过 698 OAD EB55XXXX 映射」。
- C4 数据项配置读写：勾选/保存/读回、坏项跳过、恢复默认。
- C5 「从节点版本信息」必须在内置库里且默认勾选（用户明确要求）。
- C6 点抄按勾选项逐帧下发：645 表 N 项 → N 帧；698 表 N 项 → 合成 1 帧。
- C7 并发抄表每表只带一个报文内容（取第一个适用项）。
- C8 界面接线：按钮存在、对话框能载入配置。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import _config_sandbox

    SANDBOX = _config_sandbox.install()
except Exception:                                   # pragma: no cover
    SANDBOX = None

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import archive_copy_items as C  # noqa: E402
import gdw_meter_request as R  # noqa: E402
import archive_widget as A  # noqa: E402
from dl_t698_45_apdu_parser import DLT69845APDUParser  # noqa: E402

FAILED = []
CHECKS = [0]
ADDR = "000000000001"


def section(title):
    print(f"\n-- {title} " + "-" * max(0, 62 - len(title)))


def check(name, got, want):
    CHECKS[0] += 1
    if got == want:
        print(f"  [OK] {name}")
        return True
    FAILED.append(f"{name}\n    got  = {got!r}\n    want = {want!r}")
    print(f"  [NG] {name}  -> {got!r}")
    return False


def check_true(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        print(f"  [OK] {name}")
        return True
    FAILED.append(f"{name}\n    detail = {detail!r}")
    print(f"  [NG] {name}  detail={detail!r}")
    return False


class FakeSerial(QObject):
    frame_received = Signal(bytes)
    log_message = Signal(str)
    connection_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.sent = []

    def send_hex_string(self, hex_str):
        self.sent.append(str(hex_str))


def items_with(*keys):
    """按 key 取内置项并全部勾选，其余取消"""
    out = []
    for raw in C.BUILTIN_ITEMS:
        it = C.normalize_item(dict(raw))
        if it["key"] in keys:
            it["enabled"] = "1"
        else:
            it["enabled"] = "0"
        out.append(it)
    return out


def cell(w, row, col):
    """取表格单元格文本"""
    item = w.table.item(row, col)
    return item.text() if item else ""


def inner_frame_of(w, frame_hex):
    """从下行 13H F1 帧里取出内层报文（字段行 = (名称, 原始值, 解析值, ...)）"""
    rows = w.gdw_parser.parse_to_table(bytes.fromhex(frame_hex))
    for row in rows:
        if "报文内容" in str(row[0]):
            return str(row[1]).replace(" ", "").upper()
    return ""


# ══════════════════════════════════════════════════════════════════════
def test_frame_golden():
    section("C1 698 单 OAD / 645 单 DI 与现场口径逐字节一致")
    ours698 = C.build_698_get_list(ADDR, ["00100200"])
    ref698 = R.build_698_read_total_active(ADDR, "00100200")
    check("698 单 OAD 逐字节一致", ours698.hex().upper(), ref698.hex().upper())
    check("698 现场报文", ours698.hex().upper(),
          "68170043050100000000000036B30501010010020000922E16")

    ours645 = C.build_645_read(ADDR, "00010000")
    ref645 = R.build_645_read_total_active(ADDR, "00010000")
    check("645 单 DI 逐字节一致", ours645.hex().upper(), ref645.hex().upper())
    check("645 现场报文", ours645.hex().upper(),
          "6801000000000068110433333433B316")


def test_multi_oad():
    section("C2 698 多 OAD = GetRequestNormalList，解析器可回读")
    frame = C.build_698_get_list(ADDR, ["00100200", "EB550303"])
    apdu = frame[14:-3]
    res = DLT69845APDUParser().parse(apdu)
    check("子类型", res.get("子类型"), "GetRequestNormalList")
    check("OAD 数量", len(res.get("OAD列表") or []), 2)
    check("OAD1", res["OAD列表"][0]["原始值"], "00100200")
    check("OAD2", res["OAD列表"][1]["原始值"], "EB550303")
    check("时间标签=无", res.get("时间标签", {}).get("解析值"), 0)
    # 单 OAD 仍用 Normal（不是 NormalList）
    single = DLT69845APDUParser().parse(C.build_698_get_list(ADDR, ["00100200"])[14:-3])
    check("单 OAD 走 GetRequestNormal", single.get("子类型"), "GetRequestNormal")


def test_module_mapping():
    section("C3 STA 模块项：EB03xxxx 备查映射 + 从节点版本信息走公司扩展协议")
    check("EB030302 → EB550302", C.module_di_to_oad("EB030302"), "EB550302")
    check("EB030311 → EB550311", C.module_di_to_oad("EB030311"), "EB550311")
    check("非法 DI 返回空", C.module_di_to_oad("1234"), "")

    # 「从节点版本信息」= 查询从节点详细版本同一份报文，不区分表协议
    frame = C.build_module_version_frame(ADDR)
    check("版本信息内层帧逐字节（与详细版本命令同款）", frame.hex().upper(),
          "6801000000000068113C34103332334E3433353336333733383339333C337433753376"
          "337733783379337A337B337C337D337E337F33803381338733883389338A338B3391"
          "331D16")
    decoded = bytes((b - 0x33) & 0xFF for b in frame[10:-2])
    check("DI（低字节在前）", decoded[:4].hex().upper(), "01DD00FF")
    check("条目信息", decoded[4], 0)
    check("条目数 M", decoded[5], 27)
    check("长度域 = 0x3C(60)", frame[9], 0x3C)

    # 645 表与 698 表拿到的版本信息帧必须完全一样
    items = items_with("sta_version")
    f645, _ = C.frames_for_meter(ADDR, False, items)
    f698, _ = C.frames_for_meter(ADDR, True, items)
    check("版本信息项对 645 表下发 1 帧", len(f645), 1)
    check("版本信息项对 698 表也下发 1 帧（不区分协议）", len(f698), 1)
    check("两者报文完全一致", f645[0][1].hex().upper(), f698[0][1].hex().upper())
    check("两者通信协议类型都是 2(645)", (f645[0][2], f698[0][2]), (2, 2))


def test_items_persist():
    section("C4 数据项配置读写")
    items = items_with("sta_version", "645_total_active")
    path = C.save_items(items, os.path.join(os.environ.get("TEMP", "."), "ci_test.json"))
    back = C.load_items(path)
    check("读回条数", len(back), len([i for i in items if i]))
    enabled = [i["key"] for i in C.enabled_items(back)]
    check("勾选项", enabled, ["sta_version", "645_total_active"])
    check_true("保存文件存在", os.path.exists(path), path)
    # 坏项跳过
    bad = C.normalize_item({"name": "坏项", "proto": "645", "di": "12"})
    check("短 DI 视为非法", bad, None)
    # 缺 proto 按标识推断
    guessed = C.normalize_item({"name": "x", "di": "EB030303"})
    check("按 EB 前缀推断为模块项", guessed["proto"], C.PROTO_MODULE)
    check("模块项自动补 OAD", guessed["oad"], "EB550303")


def test_builtin_has_sta_version():
    section("C5 内置库必须含「从节点版本信息」且默认勾选（公司扩展协议）")
    names = [it["name"] for it in C.BUILTIN_ITEMS]
    check_true("含从节点版本信息", "从节点版本信息" in names, names)
    ver = [it for it in C.BUILTIN_ITEMS if it["name"] == "从节点版本信息"][0]
    check("标识 = FF00DD01（公司扩展协议 DI）", ver["di"], "FF00DD01")
    check("种类 = module_version", ver["kind"], C.KIND_MODULE_VERSION)
    check("默认勾选", ver["enabled"], "1")
    check("归属=模块项", ver["proto"], C.PROTO_MODULE)
    norm = C.normalize_item(dict(ver))
    check("规整后仍保留 kind", norm["kind"], C.KIND_MODULE_VERSION)
    check("规整后无 698 映射", norm["oad"], "")

    # 旧配置迁移：曾把版本信息存成 EB030303（645 扩展 DI）→ 自动升级为公司扩展协议
    old = C.normalize_item({"key": "sta_version", "name": "从节点版本信息",
                            "proto": C.PROTO_MODULE, "di": "EB030303", "enabled": "1"})
    check("旧 EB030303 迁移为 kind", old["kind"], C.KIND_MODULE_VERSION)
    check("旧 EB030303 迁移为 FF00DD01", old["di"], "FF00DD01")
    # 别名不影响其它 EB0303xx 项
    other = C.normalize_item({"name": "从节点所在相位", "di": "EB030302", "enabled": "1"})
    check("其它模块项不迁移", (other["kind"], other["di"]), (C.KIND_READ, "EB030302"))


def test_frames_for_meter():
    section("C6 按表协议 + 勾选项生成报文")
    items = items_with("sta_version", "sta_phase", "645_total_active", "698_total_active")
    ver_golden = C.build_module_version_frame(ADDR).hex().upper()

    frames645, skipped645 = C.frames_for_meter(ADDR, False, items)
    # 645 表：版本信息(公司扩展) + 相位(EB030302) + 正向有功 = 3 帧
    check("645 表帧数", len(frames645), 3)
    check("645 表协议类型全为 2", [f[2] for f in frames645], [2, 2, 2])
    check("第 1 帧是版本信息（公司扩展）", frames645[0][1].hex().upper(), ver_golden)
    check("645 表跳过纯 698 项", skipped645, ["正向有功电能"])

    frames698, skipped698 = C.frames_for_meter(ADDR, True, items)
    # 698 表：版本信息(645 帧) + 正向有功(698 帧) + 相位(645 扩展帧, 塞不进 698)
    check("698 表帧数", len(frames698), 3)
    check("698 表里有一帧是 698 协议",
          len([f for f in frames698 if f[2] == 3]), 1)
    check("698 表里版本信息仍是 645 帧",
          [f[1].hex().upper() for f in frames698 if f[2] == 2][0], ver_golden)
    check("698 表跳过纯 645 项", skipped698, ["正向有功总电能"])
    frame698 = [f for f in frames698 if f[2] == 3][0]
    apdu = DLT69845APDUParser().parse(frame698[1][14:-3])
    check("698 帧子类型（单 OAD 走 Normal）", apdu.get("子类型"), "GetRequestNormal")
    check("698 帧只含正向有功 OAD",
          apdu["OAD"]["原始值"], "00100200")


def test_copy_test_sends_items():
    section("C7 点抄按勾选项逐帧下发；并发每表只带一项")
    app = QApplication.instance() or QApplication([])
    w = A.ArchiveWidget()
    fake = FakeSerial()
    w.set_serial_worker(fake)
    w.set_protocol_mode("gdw")
    app.processEvents()
    w._clear_table()

    # 一块 645 表 + 一块 698 表
    w._add_meter_to_table({"meter_id": "000000000001", "protocol": "645",
                           "phase": "A相", "status": "在线", "extra": ""}, save=False)
    w._add_meter_to_table({"meter_id": "000000000002", "protocol": "698",
                           "phase": "A相", "status": "在线", "extra": ""}, save=False)

    w._copy_items = items_with("sta_version", "645_total_active")
    w.copy_count_input.setText("1")
    # 输入框宽度必须随位数增长：现场填 1000 只显示成 "100"（固定 40px 装不下）
    for _digits_text in ("1", "10", "100", "1000", "10000"):
        w.copy_count_input.setText(_digits_text)
        app.processEvents()
        _need = w.copy_count_input.fontMetrics().horizontalAdvance(_digits_text) + 16
        check_true(f"抄读次数 {_digits_text} 完整可见",
                   w.copy_count_input.width() >= _need,
                   f"宽={w.copy_count_input.width()} 需={_need}")
    w.copy_timeout_input.setText("10000")
    app.processEvents()
    check_true("超时 10000 完整可见",
               w.copy_timeout_input.width()
               >= w.copy_timeout_input.fontMetrics().horizontalAdvance("10000") + 16,
               f"宽={w.copy_timeout_input.width()}")
    w.copy_count_input.setText("1")
    w._start_copy_test([0], "sequential")
    app.processEvents()
    # 645 表：版本信息 + 正向有功 = 2 帧，先发第 1 帧
    check("645 表先发第 1 项", len(fake.sent), 1)
    inner1 = inner_frame_of(w, fake.sent[0])
    check_true("下行含内层报文", bool(inner1), inner1)
    check("第 1 帧内层 = 从节点版本信息（公司扩展协议 FF00DD01）",
          inner1, C.build_module_version_frame("000000000001").hex().upper())
    check("队列保留本轮全部项（应答后才推进），共 2 项",
          len(w._copy_test_queue[0]["frames"]) if w._copy_test_queue else 0, 2)

    # 698 表：勾了模块版本项 + 645 项 → 版本信息仍按 645 帧下发（不区分协议）
    w._copy_test_queue = []
    w._is_copy_testing = False
    fake.sent.clear()
    w._start_copy_test([1], "sequential")
    app.processEvents()
    check("698 表也发 1 帧（版本信息）", len(fake.sent), 1)
    inner2 = inner_frame_of(w, fake.sent[0])
    check("698 表拿到的仍是同一份 645 扩展帧",
          inner2, C.build_module_version_frame("000000000002").hex().upper())
    rows2 = {str(r[0]).strip(): r for r in w.gdw_parser.parse_to_table(
        bytes.fromhex(fake.sent[0]))}
    proto_row = rows2.get("  通信协议类型") or rows2.get("通信协议类型")
    check("通信协议类型=2(645，不区分表协议)", str(proto_row[2]), "2")

    w._is_copy_testing = False
    w.deleteLater()
    return app


def test_concurrent_one_item():
    section("C8 并发抄表每表一个报文内容")
    app = QApplication.instance() or QApplication([])
    w = A.ArchiveWidget()
    fake = FakeSerial()
    w.set_serial_worker(fake)
    w.set_protocol_mode("gdw")
    app.processEvents()
    w._clear_table()
    w._add_meter_to_table({"meter_id": "000000000001", "protocol": "645",
                           "phase": "A相", "status": "在线", "extra": ""}, save=False)
    w._copy_items = items_with("645_total_active", "sta_version")
    w.copy_count_input.setText("1")
    w._start_copy_test([0], "concurrent")
    app.processEvents()
    check("并发发 1 帧", len(fake.sent), 1)
    inner = inner_frame_of(w, fake.sent[0])
    # 第一个「适用」项：内置库顺序里模块版本项在前 → 公司扩展帧
    check("取第一个适用项（从节点版本信息）",
          inner, C.build_module_version_frame("000000000001").hex().upper())
    w._is_copy_testing = False
    w.deleteLater()
    return app


def test_channel_strength_item():
    section("C10 「通信信道信号强度」= 同一 FF00DD01 命令 + 现场条目清单")
    names = [it["name"] for it in C.BUILTIN_ITEMS]
    check_true("内置库含通信信道信号强度", "通信信道信号强度" in names, names)
    item = [it for it in C.BUILTIN_ITEMS if it["name"] == "通信信道信号强度"][0]
    check("标识 = FF00DD01（同版本信息命令）", item["di"], "FF00DD01")
    check("种类 = module_query", item["kind"], C.KIND_MODULE_QUERY)
    check("条目数 = 48（现场实测）", len(item["entries"]), 48)

    frame = C.build_module_query_frame(ADDR, [tuple(e) for e in item["entries"]])
    decoded = bytes((b - 0x33) & 0xFF for b in frame[10:-2])
    check("DI（低字节在前）", decoded[:4].hex().upper(), "01DD00FF")
    check("条目数 M", decoded[5], 48)
    hdr = decoded[6:]
    ents = [((hdr[i] | hdr[i + 1] << 8) >> 6, (hdr[i] | hdr[i + 1] << 8) & 0x3F)
            for i in range(0, len(hdr), 2)]
    check_true("含 分类2/数据22 载波接收信息（PLC 下行/上行）", (2, 22) in ents, ents[:5])
    check_true("含 分类0~2 全部条目与版本信息项同源",
               set(C.MODULE_VERSION_ENTRIES) <= set(ents),
               sorted(set(C.MODULE_VERSION_ENTRIES) - set(ents)))
    # 校验和自洽
    check("CS 自洽", frame[-2], sum(frame[:-2]) & 0xFF)
    # 不区分表协议
    items = items_with("sta_channel_strength")
    f645, _ = C.frames_for_meter(ADDR, False, items)
    f698, _ = C.frames_for_meter(ADDR, True, items)
    check("645 表下发 1 帧", len(f645), 1)
    check("698 表也下发 1 帧（不区分协议）", len(f698), 1)
    check("两表报文一致", f645[0][1].hex().upper(), f698[0][1].hex().upper())
    check("协议类型都是 2", (f645[0][2], f698[0][2]), (2, 2))
    # 旧配置里没有 entries 的 module_query 项 → 回退现场清单
    norm = C.normalize_item({"name": "自定义模块项", "kind": C.KIND_MODULE_QUERY})
    check("缺 entries 回退现场清单", len(norm["entries"]), 48)
    # pad_to 支持（现场工具会把数据域补到 240）
    padded = C.build_module_query_frame(
        ADDR, [tuple(e) for e in item["entries"]], pad_to=240)
    check("填充后数据域 = 240", len(padded) - 12, 240)

    # 老配置里没有该项时要自动补齐（否则升级后用户看不到）
    import json as _json
    import tempfile
    old_path = os.path.join(tempfile.gettempdir(), "ci_old.json")
    with open(old_path, "w", encoding="utf-8") as f:
        _json.dump({"items": [
            {"key": "sta_version", "name": "从节点版本信息",
             "proto": "module", "kind": "module_version", "di": "FF00DD01",
             "enabled": "1"},
        ]}, f, ensure_ascii=False)
    merged = C.load_items(old_path)
    keys = [it["key"] for it in merged]
    check_true("老配置自动补齐新内置项", "sta_channel_strength" in keys, keys)
    merged_item = [it for it in merged if it["key"] == "sta_channel_strength"][0]
    check("补齐项不擅自勾选", merged_item["enabled"], "0")
    check("原有项保留勾选", [it for it in merged if it["key"] == "sta_version"][0]["enabled"], "1")


def test_round_robin_schedule():
    section("C11 点抄次数 = 按表号顺序抄 N 轮（不是同一块表连抄 N 次）")
    app = QApplication.instance() or QApplication([])
    w = A.ArchiveWidget()
    fake = FakeSerial()
    w.set_serial_worker(fake)
    w.set_protocol_mode("gdw")
    app.processEvents()
    w._clear_table()
    for i in (1, 2, 3):
        w._add_meter_to_table({"meter_id": f"00000000000{i}", "protocol": "645",
                               "phase": "A相", "status": "在线", "extra": ""},
                              save=False)
    w._copy_items = items_with("645_total_active")
    w.copy_count_input.setText("2")
    w._start_copy_test([0, 1, 2], "sequential")
    app.processEvents()
    sched = [(t["round"], t["addr"]) for t in w._copy_test_queue]
    check("调度 = 3 表 × 2 轮，按表号顺序", sched,
          [(1, "000000000001"), (1, "000000000002"), (1, "000000000003"),
           (2, "000000000001"), (2, "000000000002"), (2, "000000000003")])
    check("统计 total = 轮数 2", w._copy_test_stats["000000000001"]["total"], 2)
    w._is_copy_testing = False
    w.deleteLater()
    return app


def test_copy_content_column():
    section("C12 抄读结果列之外，另出「抄读内容」列（解析后的关键字段）")
    app = QApplication.instance() or QApplication([])
    w = A.ArchiveWidget()
    fake = FakeSerial()
    w.set_serial_worker(fake)
    w.set_protocol_mode("gdw")
    app.processEvents()
    w._clear_table()
    check("表格 12 列", w.table.columnCount(), 12)
    check("第 12 列标题", w.table.horizontalHeaderItem(11).text(), "抄读内容")

    # 现场应答帧（LME FF00DD01，含载波接收信息/厂商/版本）
    inner = ("68 01 00 00 00 00 30 68 91 6D 34 10 33 32 33 47 C9 47 33 33 34 45 7B 7F "
             "35 45 63 6C 36 51 59 43 59 37 49 43 59 38 45 7B 7F 39 45 63 6C 3A 3F 47 "
             "3B 3F 33 3C 77 33 33 33 33 33 33 33 33 3E 3F 36 3F 69 32 32 32 32 32 32 "
             "40 69 32 32 32 32 32 32 41 57 47 DE 11 95 42 47 38 35 43 3F 35 44 47 32 "
             "32 45 47 6B 35 46 47 32 32 47 97 33 33 33 33 33 33 33 33 33 33 33 33 22 16")
    short, full = w._copy_content_from_inner(bytes.fromhex(inner.replace(" ", "")), 2)
    check_true("摘要含厂商", "外部厂商代码:LH" in short, short)
    check_true("摘要含版本", "外部版本号:26.10" in short, short)
    check_true("载波接收信息转成 RSSI/SNR 可读口径",
               "信号强度RSSI=" in short and "信噪比SNR=" in short, short)
    check_true("明细逐条给全", "外部版本日期: 261026" in full, full[:120])

    # ── 崩溃回归：645 普通 DI（行是 3/4 元组，不是 6 元组）──────────────
    # 现场：勾选「正向有功」等 645 数据项后点抄读测试 → ValueError:
    #   not enough values to unpack (expected 6, got 3)
    # 根因：_copy_content_from_inner 硬解 6 元组，而 645 parser 给 3 元组。
    from archive_widget import _field_triple
    check("_field_triple 兼容 3 元组", _field_triple(("n", "r", "p")), ("n", "r", "p"))
    check("_field_triple 兼容 4 元组", _field_triple(("n", "r", "p", "c")), ("n", "r", "p"))
    check("_field_triple 兼容 6 元组", _field_triple(("n", "r", "p", "c", 1, 2)), ("n", "r", "p"))
    check("_field_triple 兼容 1 元组", _field_triple(("only",)), ("only", "", ""))
    check("_field_triple 兼容 0 元组", _field_triple(()), ("", "", ""))

    # 645 正向有功总电能读应答（校验和正确）：DI=00010000，值 0.00 kWh
    zone645 = bytes.fromhex("680100000000006891063333343333339B16")
    short645, full645 = w._copy_content_from_inner(zone645, 2)
    check_true("645 正向有功不再崩溃且摘要取业务值",
               short645 == "当前正向有功总电能:0.00 kWh", short645)
    check_true("645 摘要不再取到「结束符」", "结束符" not in short645, short645)
    check_true("645 明细含数据值行", "数据值: 0.00 kWh" in full645, full645[:120])

    # LME 分支（DI=FF00DD01）仍正常：紧邻崩溃点，防「修 A 坏 B」
    short_lme, _ = w._copy_content_from_inner(bytes.fromhex(inner.replace(" ", "")), 2)
    check_true("LME 分支未受影响", "外部厂商代码:LH" in short_lme, short_lme)

    # ── 成功率判定回归：内层 645 带 FE 前导时旧实现判 False（成功率 0%）──────
    # 现场：抄读内容能解出（645 解析器支持 FE 前导），但成功率恒 0%
    inner_fe = ("FE 68 38 11 88 06 00 00 68 91 08 33 33 34 33 BC 54 33 33 83 16")
    inner_no_fe = inner_fe.replace("FE ", "")
    check("控制码定位跳过 FE 前导", w._dlt645_ctrl_of(bytes.fromhex(inner_fe.replace(" ", ""))), 0x91)
    check("控制码定位（无前导）", w._dlt645_ctrl_of(bytes.fromhex(inner_no_fe.replace(" ", ""))), 0x91)
    check("异常应答控制码 0xD1 可定位",
          w._dlt645_ctrl_of(bytes.fromhex("FE 68 38 11 88 06 00 00 68 D1".replace(" ", "")) + bytes(6)),
          0xD1)
    check("多级 FE 前导全跳过",
          A.ArchiveWidget._skip_prefix(bytes.fromhex("FEFEFE68"), (0xFE,)).hex().upper(), "68")

    class _FakeGdwParser:
        """只回放一行「报文内容」（模拟国网解析器 AFN=13 F1 上行）"""
        def __init__(self, content_hex):
            self._content = content_hex

        def parse_to_table(self, _frame):
            return [("  报文内容", self._content, "21字节", "原始报文数据", 10, 30)]

    judge = A.ArchiveWidget._parse_copy_inner_success
    w.gdw_parser = _FakeGdwParser(inner_fe)
    check("带 FE 前导 → 判成功（修复点）", judge(w, b"\x00" * 40, "645"), True)
    w.gdw_parser = _FakeGdwParser(inner_no_fe)
    check("无前导 → 判成功", judge(w, b"\x00" * 40, "645"), True)
    w.gdw_parser = _FakeGdwParser(
        "68 38 11 88 06 00 00 68 D1 08 33 33 34 33 BC 54 33 33 83 16")
    check("异常应答 D6=1 → 判失败（不再虚高）", judge(w, b"\x00" * 40, "645"), False)
    w.gdw_parser = _FakeGdwParser("")
    check("报文内容为空 → 判失败", judge(w, b"\x00" * 40, "645"), False)

    # 载入到表格：内容列写摘要 + tooltip 给明细
    w._copy_test_content["000000000001"] = short
    w._copy_test_content_full["000000000001"] = full
    w._copy_test_stats = {"000000000001": {"sent": 3, "success": 3, "total": 3,
                                          "elapsed_last": 0.6, "elapsed_sum": 1.8,
                                          "elapsed_n": 3}}
    w._add_meter_to_table({"meter_id": "000000000001", "protocol": "698",
                           "phase": "A相", "status": "在线", "extra": ""}, save=False)
    w._copy_test_queue = []
    w._update_copy_test_result(0, "000000000001")
    check("抄读结果列仍是成功率", cell(w, 0, 8), "抄读3次 成功3次 (100%)")
    check("抄读内容列 = 摘要", cell(w, 0, 11), short)
    check("内容列 tooltip = 明细", w.table.item(0, 11).toolTip(), full)
    check("耗时列仍在", cell(w, 0, 10), "单次600ms 平均600ms")
    w.deleteLater()
    return app


def test_ui_wiring():
    section("C9 界面接线：按钮 + 对话框可载入")
    app = QApplication.instance() or QApplication([])
    w = A.ArchiveWidget()
    app.processEvents()
    check_true("有「抄读数据项…」按钮", hasattr(w, "copy_items_btn"), None)
    dlg = A.CopyItemsDialog(w, C.load_items())
    check("对话框 3 个页签", dlg.tabs.count(), 3)
    check("模块页签行数>0", dlg._tables[C.PROTO_MODULE].rowCount() > 0, True)
    got = dlg._collect()
    check("collect 保留全部项", len(got), len(C.load_items()))
    dlg.deleteLater()
    w.deleteLater()
    return app


def main():
    tests = [
        test_frame_golden,
        test_multi_oad,
        test_module_mapping,
        test_items_persist,
        test_builtin_has_sta_version,
        test_frames_for_meter,
        test_copy_test_sends_items,
        test_concurrent_one_item,
        test_channel_strength_item,
        test_round_robin_schedule,
        test_copy_content_column,
        test_ui_wiring,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            FAILED.append(f"{t.__name__} 异常: {e}")
        print()

    print("=" * 70)
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 共 {CHECKS[0]} 项：")
        for f in FAILED:
            print(f"  - {f}")
        return 1
    print(f"全部通过（{CHECKS[0]} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
