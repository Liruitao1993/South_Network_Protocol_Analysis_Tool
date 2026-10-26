# -*- coding: utf-8 -*-
"""协议6「645协议测试」页（`dlt645_test_core` + `dlt645_test_widget`）回归。

覆盖：
  [1] 分类库：顶层大项与顺序、1765 条 DI 全覆盖且不重复、结算日分桶、光伏扩展分离、
      DI 表 16 条 7 位残键不进树、名称/长度与 DI 表一致、筛选
  [2] 命令库：覆盖 schema 的全部请求命令、分组、固定地址（13H/15H AA×6、08H 99×6）
  [3] 组帧黄金：读 A 相电压(11H) / 写日期(14H) / 读·写通信地址(13H/15H) / 广播校时(08H) /
      冻结(16H) / 事件清零(1BH) / 读后续(12H) —— 逐字节 + CS 自洽 + 解析器回读一致
  [4] 响应判定：正常/异常应答(D1H+ERR)/方向错/功能码错/DI 不符/13H 回填地址/08H 无需应答/坏校验
  [5] 页面（offscreen）：三分页与分类树、筛选、当前项与帧预览、动态字段（写数据/特殊命令）
  [6] 发送队列：勾选多条顺序下发、超时继续、停止复位、读地址回填表地址
  [7] 落盘往返 + cleanup 不关端口不断订阅、主题、RX 自组帧（前导 FE/噪声重同步）
  [8] 共享渲染层：645 与 698 用同一份 `testpage_render`（禁止第二份）
  [9] 源码护栏：不 import main_gui、不自建串口、不用 send_frame、不订阅 frame_received

运行: python test/test_dlt645_testbench.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

SANDBOX = _config_sandbox.install()      # 落盘重定向，别碰用户真实配置
# 沙箱把**只读**的 DI 表也指到了空目录 ⇒ 复制一份真实表进去（否则页面/解析器都无 DI 可查）
import pathlib  # noqa: E402
import shutil  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parent.parent
for _name in ("dlt645_di.json",):
    _src = _ROOT / _name
    if _src.is_file() and not (SANDBOX / _name).is_file():
        shutil.copyfile(_src, SANDBOX / _name)

# 构造页面之前屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import dlt645_test_core as C  # noqa: E402
import testpage_render  # noqa: E402
from dlt645_frame_gen import DLT645FrameGenerator  # noqa: E402
from dlt645_test_widget import Dlt645TestWidget  # noqa: E402

FAILED = []
CHECKS = [0]
GEN = DLT645FrameGenerator()


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        return True
    FAILED.append(f"{name}" + (f"\n    {detail}" if detail else ""))
    return False


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 60 - len(title)))


def app():
    return QApplication.instance() or QApplication([])


class FakeWorker(QObject):
    """共享串口的替身：记录发送、可注入接收。"""

    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.sent = []
        self._open = True

    def is_open(self):
        return self._open

    def write_raw(self, data):
        self.sent.append(bytes(data))
        return True


def logical_data(frame: bytes) -> bytes:
    """帧数据域 → 未加扰的逻辑字节（-0x33）。"""
    length = frame[9]
    payload = frame[10:10 + length]
    return bytes((b - 0x33) & 0xFF for b in payload)


def find_leaf(tree, predicate, item=None):
    """递归找叶子（读/写页三层、特殊命令页两层）。"""
    if item is None:
        for i in range(tree.topLevelItemCount()):
            found = find_leaf(tree, predicate, tree.topLevelItem(i))
            if found is not None:
                return found
        return None
    if item.childCount() == 0:
        return item if predicate(item.text(0)) else None
    for i in range(item.childCount()):
        found = find_leaf(tree, predicate, item.child(i))
        if found is not None:
            return found
    return None


# ── [1] 分类库 ──────────────────────────────────────────────────────────────

def test_catalog():
    section("[1] 分类库（按协议大项）")
    cats = C.catalog()
    names = [c.name for c in cats]
    check("顶层分类与顺序",
          names == ["电能量", "最大需量", "电压 / 电流", "功率 / 功率因数 / 谐波",
                    "参变量", "结算日电能", "记录", "冻结次数", "LME 自定义", "光伏扩展"],
          str(names))
    total = C.item_count()
    merged = C._load_merged()
    malformed = C.malformed_di_keys()
    check("叶子数 = 合并 DI − 7 位残键",
          total == len(merged) - len(malformed) and total == 1765,
          f"{total} vs {len(merged)}-{len(malformed)}")
    check("16 条残键都是 `0090` 开头的 7 位键",
          len(malformed) == 16 and all(k.startswith("0090") and len(k) == 7
                                      for k in malformed), str(malformed[:3]))
    all_di = [it.di for it in C.all_items()]
    check("叶子 DI 不重复", len(set(all_di)) == len(all_di),
          f"{len(all_di)} vs {len(set(all_di))}")

    nw = next(c for c in cats if c.name == "电能量")
    check("电能量首个子类 = 正向有功电能（16 条）",
          nw.subgroups[0].name == "正向有功电能" and len(nw.subgroups[0].items) == 16,
          f"{nw.subgroups[0].name}/{len(nw.subgroups[0].items)}")

    settle = next(c for c in cats if c.name == "结算日电能")
    check("结算日 254 天按 20 天分桶 = 13 组",
          len(settle.subgroups) == 13 and settle.item_count == 508,
          f"{len(settle.subgroups)}/{settle.item_count}")
    check("结算日首/末桶标签",
          settle.subgroups[0].name == "结算日 1~20"
          and settle.subgroups[-1].name == "结算日 241~254",
          f"{settle.subgroups[0].name} / {settle.subgroups[-1].name}")
    check("结算日 230（DI2=E6）仍在结算日类、没被当成光伏",
          any(it.di == "05E60100" for s in settle.subgroups for it in s.items))

    pv = next(c for c in cats if c.name == "光伏扩展")
    check("光伏扩展三个子类 77/433/172",
          [(s.name, len(s.items)) for s in pv.subgroups]
          == [("光伏变量", 77), ("光伏事件", 433), ("光伏参数", 172)],
          str([(s.name, len(s.items)) for s in pv.subgroups]))
    check("光伏叶子 pv=True、常规叶子 pv=False",
          all(it.pv for s in pv.subgroups for it in s.items)
          and not any(it.pv for it in nw.subgroups[0].items))

    item = C.find_di("02010100")
    check("find_di(A相电压)", item is not None and item.name == "A相电压"
          and item.data_type == "XXX.X" and item.length == 2,
          str(item))
    check("find_di 未知 → None", C.find_di("DEADBEEF") is None)
    hits = C.filter_items("电压")
    check("筛选「电压」非空且命中名称",
          hits and all("电压" in it.name for it in hits), str(len(hits)))
    check("筛选「0310」按子串命中 DI",
          C.filter_items("0310")
          and all("0310" in it.di or "0310" in it.name
                  for it in C.filter_items("0310")))

    info = C.di_info("02010100")
    check("di_info 与 DI 表同源（名称/单位）",
          info.get("name") == "A相电压" and info.get("unit") == "V", str(info))


# ── [2] 命令库 ──────────────────────────────────────────────────────────────

def test_commands():
    section("[2] 特殊命令库（来自 schema）")
    funcs = {cmd.func for cmd in C.all_commands()}
    check("覆盖全部请求命令",
          funcs == {0x13, 0x15, 0x08, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x12},
          str(sorted(hex(f) for f in funcs)))
    groups = C.command_groups()
    check("五个分组且非空",
          len(groups) == 5 and all(g.commands for g in groups),
          str([g.name for g in groups]))
    check("读/写通信地址固定地址 AA×6",
          C.find_command(0x13).addr_default == C.BROADCAST_AA
          and C.find_command(0x15).addr_default == C.BROADCAST_AA)
    check("广播校时固定地址 99×6",
          C.find_command(0x08).addr_default == C.BROADCAST_99)
    check("冻结/清零用页面表地址",
          not C.find_command(0x16).addr_is_fixed
          and not C.find_command(0x1B).addr_is_fixed)
    check("事件清零字段含「事件标识」",
          any(f["name"] == "事件标识" for f in C.find_command(0x1B).fields))
    check("写通信地址字段含「新通信地址」",
          any(f["name"] == "新通信地址" for f in C.find_command(0x15).fields))
    check("command_effective_addr：固定地址优先于页面地址",
          C.command_effective_addr(C.find_command(0x13), "112233445566") == C.BROADCAST_AA
          and C.command_effective_addr(C.find_command(0x1B), "112233445566")
          == "112233445566")


# ── [3] 组帧黄金 ────────────────────────────────────────────────────────────

def test_frames():
    section("[3] 组帧（逐字节 + CS + 解析回读）")
    read = C.build_read("02010100")
    check("读 A 相电压 11H 逐字节",
          read.hex(" ").upper()
          == "68 00 00 00 00 00 00 68 11 04 33 34 34 35 B5 16",
          read.hex(" ").upper())
    parsed = C.parse_frame(read)
    check("读请求回读：C=0x11 / DI=02010100 / 结构+校验通过",
          parsed.get("control") == 0x11 and parsed.get("di_code") == "02010100"
          and parsed.get("structure_valid") and parsed.get("checksum_valid"),
          str({k: parsed.get(k) for k in ("control", "di_code", "checksum_valid")}))

    addr_read = C.quick_read_address()
    check("读通信地址 13H：地址 AA×6、L=0",
          addr_read.hex(" ").upper()
          == "68 AA AA AA AA AA AA 68 13 00 DF 16"
          and addr_read[9] == 0,
          addr_read.hex(" ").upper())

    addr_write = C.quick_write_address("112233445566")
    check("写通信地址 15H：新地址低字节在前",
          logical_data(addr_write) == bytes.fromhex("665544332211"),
          logical_data(addr_write).hex(" ").upper())

    when = datetime(2026, 10, 26, 12, 34, 56)
    clock = C.build_broadcast_time(when)
    check("广播校时 08H：地址 99×6 + 线序 ss mm hh DD MM YY",
          clock[1:7] == b"\x99" * 6 and clock[8] == 0x08
          and logical_data(clock) == bytes.fromhex("563412261026"),
          f"addr={clock[1:7].hex()} data={logical_data(clock).hex()}")

    freeze = C.build_command(0x16, {"冻结时间": "01-01-00-00"})
    # 线上低字节在前：MM=01 DD=01 hh=00 mm=00 ⇒ 字节序 mm hh DD MM
    check("冻结 16H：MM-DD-hh-mm 低字节在前（mm hh DD MM）",
          freeze[8] == 0x16 and logical_data(freeze) == bytes.fromhex("00000101"),
          logical_data(freeze).hex(" ").upper())

    clear = C.build_command(0x1B, {
        "密码权限 PA": "02", "密码 P0P1P2": "000000",
        "操作者代码 C0~C3": "00000000", "事件标识": "FFFFFFFF",
    })
    check("事件清零 1BH：PA+PWD+C0~C3+FFFFFFFF（无 DI 前缀）",
          logical_data(clear) == bytes.fromhex("02000000" + "00000000" + "FFFFFFFF"),
          logical_data(clear).hex(" ").upper())

    write = C.build_write("04000101", {
        "日期": "2026-10-26", "密码权限 PA": "02",
        "密码 P0P1P2": "000000", "操作者代码 C0~C3": "00000000",
    })
    expect = (bytes.fromhex("01010004") + bytes.fromhex("02" + "000000" + "00000000")
              + bytes.fromhex("261026"))
    check("写日期 14H：DI + 密码组 + 26 10 26",
          write[8] == 0x14 and logical_data(write) == expect,
          logical_data(write).hex(" ").upper())
    check("写日期时给「声明 4 字节 / 实际 3 字节」提示（不阻断）",
          "4 字节" in C.length_warning("04000101", {"日期": "2026-10-26"}))

    nxt = C.build_read_next("00010000", extra=b"\x01\x02")
    check("读后续 12H：DI + 附加数据",
          nxt[8] == 0x12
          and logical_data(nxt) == bytes.fromhex("00000100" + "0102"),
          logical_data(nxt).hex(" ").upper())

    frames = [read, addr_read, addr_write, clock, freeze, clear, write, nxt]
    check("所有帧末字节 16H", all(f[-1] == 0x16 for f in frames))
    check("所有帧 CS 自洽（sum(frame[:-2]) & 0xFF）",
          all((sum(f[:-2]) & 0xFF) == f[-2] for f in frames))

    try:
        C.format_address("11223344556")           # 11 位：补零
        check("format_address 补齐 12 位", C.format_address("11223344556") == "011223344556")
    except ValueError as exc:
        check("format_address 补齐 12 位", False, str(exc))
    bad = False
    try:
        C.format_address("ZZ")
    except ValueError:
        bad = True
    check("format_address 非法 → 可读 ValueError", bad)


# ── [4] 响应判定 ────────────────────────────────────────────────────────────

def test_evaluate():
    section("[4] 响应判定（不冒充成功）")
    rsp = GEN.generate_frame(("rsp", 0x11),
                             {"数据标识 DI": "02010100", "数据值": "220.5"},
                             "000000000001")
    out = C.evaluate_response(rsp, {"func": 0x11, "di": "02010100", "kind": "read"})
    check("正常读应答：成功 + 值 + DI",
          out["status"] == C.RESULT_OK and out["value_text"] == "220.5 V"
          and out["di"] == "02010100" and "A相电压" in out["summary"],
          str({k: out[k] for k in ("status", "value_text", "summary")}))
    check("正常应答附带逐字段明细", len(out["lines"]) > 1, str(len(out["lines"])))

    mismatch = C.evaluate_response(rsp, {"func": 0x11, "di": "02010200", "kind": "read"})
    check("DI 不符 → 失败",
          mismatch["status"] == C.RESULT_FAIL and "不一致" in mismatch["summary"],
          mismatch["summary"])

    wrong_func = C.evaluate_response(rsp, {"func": 0x14, "di": "02010100", "kind": "read"})
    check("功能码不符 → 失败",
          wrong_func["status"] == C.RESULT_FAIL and "0x14" in wrong_func["summary"],
          wrong_func["summary"])

    req = C.build_read("02010100")
    not_rsp = C.evaluate_response(req, {"func": 0x11, "di": "02010100", "kind": "read"})
    check("方向位 D7=0 → 失败「不是从站应答」",
          not_rsp["status"] == C.RESULT_FAIL and "不是从站应答" in not_rsp["summary"],
          not_rsp["summary"])

    err = GEN.generate_frame(("err", 0x11), {"错误信息字 ERR": "02"})
    err_out = C.evaluate_response(err, {"func": 0x11, "di": "02010100", "kind": "read"})
    check("异常应答 D1H：失败 + ERR 位解释",
          err_out["status"] == C.RESULT_FAIL and "无请求数据" in err_out["summary"],
          err_out["summary"])

    bad_cs = bytearray(rsp)
    bad_cs[-2] = (bad_cs[-2] + 1) & 0xFF
    bad_out = C.evaluate_response(bytes(bad_cs),
                                  {"func": 0x11, "di": "02010100", "kind": "read"})
    check("校验和坏 → 失败并给出应为值",
          bad_out["status"] == C.RESULT_FAIL and "校验和" in bad_out["summary"],
          bad_out["summary"])

    addr_rsp = GEN.generate_frame(("rsp", 0x13), {"通信地址": "112233445566"},
                                  "AAAAAAAAAAAA")
    addr_out = C.evaluate_response(addr_rsp, {"func": 0x13, "kind": "address"})
    check("13H 应答 → 成功 + 地址（书写序）",
          addr_out["status"] == C.RESULT_OK and addr_out["address"] == "112233445566",
          str(addr_out))
    check("address_from_frame 与 13H 数据域同源",
          C.address_from_frame(addr_rsp) == "AAAAAAAAAAAA")

    no_reply = C.evaluate_response(b"", {"func": 0x08, "kind": "command",
                                        "no_reply": True})
    check("08H 无需应答 → 已发送（不判失败）",
          no_reply["status"] == C.RESULT_NO_REPLY, str(no_reply))

    w_rsp = GEN.generate_frame(("rsp", 0x14), {"数据标识 DI": "04000101"},
                               "000000000001")
    w_out = C.evaluate_response(w_rsp, {"func": 0x14, "di": "04000101", "kind": "write"})
    check("写数据应答：DI 回显 → 成功",
          w_out["status"] == C.RESULT_OK and "日期" in w_out["summary"],
          w_out["summary"])


# ── [5]~[7] 页面 ────────────────────────────────────────────────────────────

def test_gui_pages():
    section("[5] 页面：分页 / 分类树 / 预览 / 动态字段")
    app()
    widget = Dlt645TestWidget()
    worker = FakeWorker()
    widget.set_serial_worker(worker)
    widget.show()
    app().processEvents()
    try:
        check("初始只构建「读数据」页（其余懒加载）",
              list(widget._pages) == ["read"], str(list(widget._pages)))
        read_tree = widget._pages["read"]["tree"]
        check("读数据页 10 个顶层分类", read_tree.topLevelItemCount() == 10,
              str(read_tree.topLevelItemCount()))

        leaf = find_leaf(read_tree, lambda t: "02010100" in t)
        check("树里能找到 A 相电压", leaf is not None)
        read_tree.setCurrentItem(leaf)
        app().processEvents()
        check("选中 → 帧预览 = 11H 读该 DI",
              widget._pages["read"]["preview"].text()
              == "68 00 00 00 00 00 00 68 11 04 33 34 34 35 B5 16",
              widget._pages["read"]["preview"].text())

        widget.edit_addr.setText("112233445566")
        app().processEvents()
        check("改表地址 → 预览地址域随之变化",
              widget._pages["read"]["preview"].text().startswith(
                  "68 66 55 44 33 22 11 68 11 04"),
              widget._pages["read"]["preview"].text())
        widget.edit_addr.setText("000000000000")

        widget._apply_filter("read", "02010100")
        visible = sum(
            1 for i in range(read_tree.topLevelItemCount())
            if not read_tree.topLevelItem(i).isHidden() and any(
                not read_tree.topLevelItem(i).child(j).isHidden()
                for j in range(read_tree.topLevelItem(i).childCount()))
        )
        check("筛选后只剩命中分支（1 个顶层）", visible == 1, str(visible))
        widget._apply_filter("read", "")

        # 写数据页
        widget.tabs.setCurrentIndex(1)
        app().processEvents()
        wtree = widget._pages["write"]["tree"]
        wleaf = find_leaf(wtree, lambda t: "04000101" in t)
        check("写数据页可选中「日期」", wleaf is not None)
        wtree.setCurrentItem(wleaf)
        app().processEvents()
        check("写数据页动态字段 = 日期",
              list(widget._pages["write"]["fields"]) == ["日期"],
              str(list(widget._pages["write"]["fields"])))
        widget._pages["write"]["fields"]["日期"].setText("2026-10-26")
        app().processEvents()
        check("写数据帧预览为 14H",
              " 68 14 " in widget._pages["write"]["preview"].text(),
              widget._pages["write"]["preview"].text())
        check("长度提示可见（声明 4 / 实际 3）",
              "4 字节" in widget._pages["write"]["warn"].text(),
              widget._pages["write"]["warn"].text())

        # 特殊命令页
        widget.tabs.setCurrentIndex(2)
        app().processEvents()
        ctree = widget._pages["command"]["tree"]
        check("特殊命令页 5 个分组", ctree.topLevelItemCount() == 5,
              str(ctree.topLevelItemCount()))
        nxt_leaf = find_leaf(ctree, lambda t: "读后续" in t)
        ctree.setCurrentItem(nxt_leaf)
        app().processEvents()
        check("12H 提供「数据标识 DI」输入框",
              "数据标识 DI" in widget._pages["command"]["fields"],
              str(list(widget._pages["command"]["fields"])))
        widget._pages["command"]["fields"]["数据标识 DI"].setText("02010100")
        app().processEvents()
        check("12H 帧预览带 DI",
              widget._pages["command"]["preview"].text().startswith(
                  "68 00 00 00 00 00 00 68 12 04 33 34 34 35"),
              widget._pages["command"]["preview"].text())

        # 13H 固定地址（忽略页面表地址）
        widget.edit_addr.setText("112233445566")
        addr_leaf = find_leaf(ctree, lambda t: "读通信地址" in t)
        ctree.setCurrentItem(addr_leaf)
        app().processEvents()
        check("13H 预览用 AA×6（忽略页面表地址）",
              widget._pages["command"]["preview"].text()
              == "68 AA AA AA AA AA AA 68 13 00 DF 16",
              widget._pages["command"]["preview"].text())
    finally:
        widget.close()

    section("[6] 发送队列 / 超时 / 停止 / 读地址回填")
    widget = Dlt645TestWidget()
    worker = FakeWorker()
    widget.set_serial_worker(worker)
    widget.show()
    app().processEvents()
    try:
        widget.spin_timeout.setValue(2000)
        read_tree = widget._pages["read"]["tree"]
        leaves = [find_leaf(read_tree, lambda t, di=di: di in t)
                  for di in ("00010000", "00010100", "00010200")]
        for leaf in leaves:
            leaf.setCheckState(0, Qt.Checked)
        widget._on_send()
        app().processEvents()
        check("首条立即发出", len(worker.sent) == 1, str(len(worker.sent)))
        for index, leaf in enumerate(leaves):
            di = widget._current["ident"] if widget._current else ""
            rsp = GEN.generate_frame(("rsp", 0x11),
                                     {"数据标识 DI": di, "数据值": "1.0"},
                                     "000000000000")
            worker.raw_data_received.emit(rsp)
            QTest.qWait(80)
        check("三条按顺序全部发出（等应答再发下一条）",
              len(worker.sent) == 3, str(len(worker.sent)))
        check("三条信息表都成功",
              widget.table_info.rowCount() == 3
              and all(widget.table_info.item(r, 4).text() == "成功" for r in range(3)),
              str([widget.table_info.item(r, 4).text()
                   for r in range(widget.table_info.rowCount())]))
        check("发送结束按钮复位",
              widget.btn_send.isEnabled() and not widget.btn_stop.isEnabled())
        check("最近读数已记录", bool(widget._last_values.get("00010000")),
              str(widget._last_values.get("00010000")))

        # 超时 → 记「超时」并继续
        widget._set_all_checked("read", False)
        widget.spin_timeout.setValue(300)
        read_tree.setCurrentItem(leaves[0])
        widget._on_send()
        QTest.qWait(700)
        last = widget.table_info.rowCount() - 1
        check("无应答 → 超时（不卡死）",
              widget.table_info.item(last, 4).text() == "超时",
              widget.table_info.item(last, 4).text())

        # 停止
        widget.spin_timeout.setValue(3000)
        for leaf in leaves:
            leaf.setCheckState(0, Qt.Checked)
        widget._on_send()
        app().processEvents()
        widget._on_stop()
        check("停止后按钮复位且状态为失败（用户停止）",
              widget.btn_send.isEnabled()
              and widget.table_info.item(widget.table_info.rowCount() - 1, 4).text()
              == "失败")

        # 读地址回填
        widget.edit_addr.setText("000000000000")
        widget._on_read_address()
        app().processEvents()
        check("读地址发出 13H（AA×6）",
              worker.sent[-1].hex(" ").upper()
              == "68 AA AA AA AA AA AA 68 13 00 DF 16",
              worker.sent[-1].hex(" ").upper())
        worker.raw_data_received.emit(
            GEN.generate_frame(("rsp", 0x13), {"通信地址": "AABBCCDDEEFF"},
                               "AAAAAAAAAAAA"))
        QTest.qWait(60)
        check("93H 应答 → 表地址回填 12 位", widget.edit_addr.text() == "AABBCCDDEEFF",
              widget.edit_addr.text())

        # 报文表双击 → 单帧解析信号
        got = []
        widget.frame_to_single_parse.connect(got.append)
        widget._on_raw_row_activated(0, 3)
        row_hex = widget.table_raw.item(0, 3).text().replace(" ", "")
        check("报文表双击发出该行整帧 hex",
              got and got[0] == row_hex, f"{got[:1]} vs {row_hex}")
    finally:
        widget.close()

    section("[7] 落盘 / cleanup / 主题 / RX 自组帧")
    widget = Dlt645TestWidget()
    worker = FakeWorker()
    widget.set_serial_worker(worker)
    widget.edit_addr.setText("010203040506")
    widget.edit_write_addr.setText("0A0B0C0D0E0F")
    widget.edit_pa.setText("04")
    widget.spin_timeout.setValue(1500)
    widget._save_config()
    widget.cleanup()
    check("cleanup 不关端口", worker.is_open() is True)
    rx_before = widget._rx_count
    worker.raw_data_received.emit(
        GEN.generate_frame(("rsp", 0x11), {"数据标识 DI": "02010100", "数据值": "1"},
                           "000000000000"))
    check("cleanup 后不再进帧（信号已断）", widget._rx_count == rx_before)

    widget2 = Dlt645TestWidget()
    check("落盘往返：表地址/写地址/PA/超时",
          widget2.edit_addr.text() == "010203040506"
          and widget2.edit_write_addr.text() == "0A0B0C0D0E0F"
          and widget2.edit_pa.text() == "04"
          and widget2.spin_timeout.value() == 1500,
          f"{widget2.edit_addr.text()}/{widget2.spin_timeout.value()}")

    widget2.restyle_for_theme(True)
    check("深色主题：日志底色跟随（无写死白底）",
          "#1E1E1E" in widget2.log_view.styleSheet(),
          widget2.log_view.styleSheet())

    worker2 = FakeWorker()
    widget2.set_serial_worker(worker2)
    rsp = GEN.generate_frame(("rsp", 0x11),
                             {"数据标识 DI": "02010100", "数据值": "2.0"},
                             "000000000000")
    worker2.raw_data_received.emit(b"\xfe\xfe\xfe\xfe" + rsp[:4])
    app().processEvents()
    worker2.raw_data_received.emit(rsp[4:])
    app().processEvents()
    check("前导 FEH + 半帧分两次交付 → 合成 1 帧", widget2._rx_count == 1,
          str(widget2._rx_count))
    worker2.raw_data_received.emit(b"\x00\x11")
    worker2.raw_data_received.emit(b"\xfe\xfe\x99" + rsp + rsp)
    app().processEvents()
    check("噪声 + FE 噪声 + 两帧连发 → 全部解出（+2）", widget2._rx_count == 3,
          str(widget2._rx_count))
    widget2.cleanup()
    widget2.close()


# ── [8] 共享渲染层 ──────────────────────────────────────────────────────────

def test_shared_renderer():
    section("[8] 四列渲染单源（698/645 共用）")
    import dlt698_test_core as C698

    check("698 与 645 用的是同一个 format_table_rows",
          C698.format_table_rows is testpage_render.format_table_rows
          and C.format_table_rows is testpage_render.format_table_rows)
    check("698 私有别名仍指向共享实现（既有测试 [10b] 依赖）",
          C698._display_width is testpage_render.display_width)
    rows = [("帧起始符", "68H", "", "起始符"), (" 控制码", "91H", "", "读数据应答")]
    lines = testpage_render.format_table_rows(rows, header="头")
    check("四列输出带表头与前导空格", lines[0] == "头"
          and lines[1].startswith("  帧起始符") and "  " in lines[2])
    check("CJK 宽度按 2 列", testpage_render.display_width("地址") == 4)
    check("长 hex 压缩", "共 80 字符" in testpage_render.compact_hex_like("AB" * 40))


# ── [9] 源码护栏 ────────────────────────────────────────────────────────────

def test_source_guards():
    section("[9] 源码护栏")
    src = open("dlt645_test_widget.py", encoding="utf-8").read()
    check("不 import main_gui", "import main_gui" not in src)
    check("不自建 SerialWorker", "SerialWorker(" not in src)
    check("不使用 send_frame（逐帧日志会刷屏）", "send_frame(" not in src)
    check("不订阅 frame_received（645 走 raw_data_received 自组帧）",
          "frame_received.connect" not in src)
    core = open("dlt645_test_core.py", encoding="utf-8").read()
    check("core 不 import Qt", "PySide6" not in core)
    check("core 不手拼 68…16（帧封装只走 DLT645FrameGenerator）",
          "0x68" not in core and "b\"\\x68\"" not in core)


def main():
    tests = [
        ("[1] 分类库", test_catalog),
        ("[2] 命令库", test_commands),
        ("[3] 组帧", test_frames),
        ("[4] 响应判定", test_evaluate),
        ("[5]-[7] 页面/队列/落盘", test_gui_pages),
        ("[8] 共享渲染", test_shared_renderer),
        ("[9] 源码护栏", test_source_guards),
    ]
    for name, fn in tests:
        before = len(FAILED)
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            import traceback

            FAILED.append(f"{name} 抛异常：{type(exc).__name__}: {exc}\n"
                          f"{traceback.format_exc()}")
        print(("OK   " if len(FAILED) == before else "FAIL ") + name)

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 共 {CHECKS[0]} 项检查")
        for item in FAILED:
            print(" - " + item)
        return 1
    print(f"全部通过：{CHECKS[0]} 项检查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
