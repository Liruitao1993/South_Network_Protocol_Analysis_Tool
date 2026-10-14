# -*- coding: utf-8 -*-
"""前导 FE 唤醒字节（协议8 / 协议6）——解析、表格偏移、校验一致性

规范依据（仓库内可复核）：
  - DL/T 698.45-2017 §6.3.1 字节规则 b)
    「在有效数据帧前加 4 个 FEH 作为前导码；」
    （协议文档/8.698.45协议/面向对象的用电信息数据交换协议(20210910).md:509）
    同节 c)「数据链路层帧的字节之间无线路空闲间隔；两帧之间的线路空闲间隔至少 33 位。」
  - DL/T 645-2007 §5.3.1 前导字节
    「在主站发送帧信息之前，建议先发送 4 个字节 FEH，以唤醒接收方。」
    （DLT645-2007.md:486）

本工具此前把首字节当起始符判据 ⇒ 带 FE 的**合法**帧一律报 `起始字符错误: 0xFE`
（用户现场：协议8 回包 `FE FE FE FE 68 21 00 C3 … 5D A0 16`，39 字节）。

本测试钉住：
  [1] wakeup_prefix 纯逻辑（只剥帧首连续 0xFE；无 FE 恒等）
  [2] 协议8：报障帧 golden、表格首行 + 偏移整体位移、无 FE 帧逐行不变、局部/全 FE 边界
  [3] 协议6：合法帧 + FE → valid / CS / 表格偏移 +4；无 FE 逐行不变；虚拟表不受影响
  [4] 校验器：带 FE 帧全 PASS（含「前导」项），无 FE 帧结果与改动前一致
  [5] 护栏：协议 0/7/9/10/11/12/13 **不**获得前导容忍（行为与改动前一致）
  [6] 批量/Web 帧提取：带 FE 的行仍能提取出正确的 68 帧
  [7] offscreen GUI：单帧页粘贴报障帧 → 解析成功且首行为前导行；解析回调（串口/蓝牙共用）非失败
  [8] 判据自检（反例）：判据确实会失败而非恒真；单一来源源码守卫

运行: QT_QPA_PLATFORM=offscreen python -u test/test_wakeup_fe_prefix.py
（GUI 用例在本机必须经 pwsh 间接启动 python，见 AGENTS.md §8 陷阱 62）
"""

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

import os
import pathlib
import re
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# 构造 MainWindow 之前必须屏蔽模态框，否则 offscreen 下永久阻塞
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

app = QApplication.instance() or QApplication([])

import app_paths  # noqa: E402
import batch_core  # noqa: E402
import main_gui  # noqa: E402
import parser_registry  # noqa: E402
import protocol_registry as pr  # noqa: E402
import wakeup_prefix  # noqa: E402
from dlt645_frame_gen import DLT645FrameGenerator  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402
from dl_t698_45_parser import DLT69845Parser  # noqa: E402
from protocol_registry import DLT645GuiParser  # noqa: E402
from reflex_web import web_utils  # noqa: E402
from validator.dlt645_validator import DLT645Validator  # noqa: E402
from validator.dl_t698_45_validator import DLT69845Validator  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


def section(title):
    print(f"\n{title}")


# ── 夹具 ────────────────────────────────────────────────────────────────────

# 用户现场报障帧（蓝牙工具页 [RX·0xFFE1]，39 字节；协议8 GET-Response，OAD 40010200=通信地址）
REPORT_FE_HEX = ("FEFEFEFE682100C30511111111111100848485010140010200010906"
                 "11111111111100005DA016")
REPORT_FE = bytes.fromhex(REPORT_FE_HEX)
REPORT_BODY = REPORT_FE[4:]
FE4 = b"\xFE" * 4

P698 = DLT69845Parser()
GUI645 = DLT645GuiParser(DLT645Parser())
GEN645 = DLT645FrameGenerator()
LEGAL645 = GEN645.build_frame("123456789012", 0x91, bytes.fromhex("0101E602") + b"\x00" * 6)


def row_named(table, name):
    for row in table:
        if row and row[0] == name:
            return row
    return None


def first_names(table, n=3):
    return [row[0] for row in table[:n]]


# ══════════════════════════════════════════════════════════════════════════
# [1] 纯逻辑
# ══════════════════════════════════════════════════════════════════════════


def test_wakeup_prefix_logic():
    section("[1] wakeup_prefix 纯逻辑（只剥帧首连续 0xFE）")
    wp = wakeup_prefix
    check("无 FE → 0 且恒等",
          wp.wakeup_prefix_len(b"\x68\x01") == 0
          and wp.strip_wakeup_prefix(b"\x68\x01") == (b"\x68\x01", 0))
    check("FE×1 / FE×2 / FE×4 计数正确",
          [wp.wakeup_prefix_len(FE4[:k] + b"\x68") for k in (1, 2, 4)] == [1, 2, 4])
    check("FE×8 也按实际个数",
          wp.wakeup_prefix_len(b"\xFE" * 8 + b"\x68") == 8)
    check("只剥**帧首**：帧内的 0xFE 不动",
          wp.strip_wakeup_prefix(b"\x68\xFE\xFE\x68") == (b"\x68\xFE\xFE\x68", 0))
    check("空输入不炸", wp.strip_wakeup_prefix(b"") == (b"", 0))
    check("全 FE → 剥空（交给上层报错）",
          wp.strip_wakeup_prefix(b"\xFE" * 6) == (b"", 6))
    check("wakeup_display 渲染", wp.wakeup_display(2) == "FE FE")
    check("make_wakeup_row 形状（6 列，偏移 0..n-1）",
          wp.make_wakeup_row(4, "x") == ("唤醒前导字节", "FE FE FE FE", "-", "x", 0, 3))
    check("shift_row_offsets 只位移双 int 偏移行",
          wp.shift_row_offsets([("a", "1", "1", "", 0, 0), ("b", "2", "2", "", None, None)], 4)
          == [("a", "1", "1", "", 4, 4), ("b", "2", "2", "", None, None)])
    check("shift_row_offsets delta=0 恒等",
          wp.shift_row_offsets([("a", "1", "1", "", 3, 5)], 0) == [("a", "1", "1", "", 3, 5)])


# ══════════════════════════════════════════════════════════════════════════
# [2] 协议8
# ══════════════════════════════════════════════════════════════════════════


def test_698_report_frame():
    section("[2] 协议8：报障帧（FE×4）解析与表格偏移")
    res = P698.parse(REPORT_FE)
    check("带 FE 报障帧解析成功", res.get("解析状态") == "成功", str(res.get("错误信息")))
    check("HCS / FCS 均通过",
          res["帧头校验HCS"]["校验结果"] == "通过"
          and res["帧校验FCS"]["校验结果"] == "通过")
    check("APDU = GET-Response 且 OAD = 通信地址",
          res["链路用户数据"]["APDU"]["APDU类型"] == "GET-Response"
          and "0x4001" in str(res["链路用户数据"]["APDU"]))
    check("唤醒前导记录 4 字节且原文可读",
          res.get("唤醒前导", {}).get("字节数") == 4
          and res["唤醒前导"]["原始值"] == "FE FE FE FE")
    check("`原始数据` 保留用户输入（含 FE）",
          res["原始数据"] == REPORT_FE.hex().upper())

    table = P698.parse_to_table(REPORT_FE)
    head = table[0]
    check("表格首行 = 唤醒前导字节（0..3）",
          head[0] == "唤醒前导字节" and head[1] == "FE FE FE FE"
          and (head[4], head[5]) == (0, 3), str(head))
    check("首行说明引规范（§6.3.1）", "6.3.1" in head[3], head[3])
    check("起始字符偏移 = (4,4)（与输入框原文对齐）",
          tuple(row_named(table, "起始字符")[4:6]) == (4, 4),
          str(row_named(table, "起始字符")))
    check("结束符偏移 = (38,38)（= 39 字节末位）",
          tuple(row_named(table, "结束符")[4:6]) == (38, 38),
          str(row_named(table, "结束符")))
    check("HCS / FCS 偏移同步位移（16/17、36/37）",
          tuple(row_named(table, "帧头校验HCS")[4:6]) == (16, 17)
          and tuple(row_named(table, "帧校验FCS")[4:6]) == (36, 37))
    check("表格无 ❌ 行", not any("❌" in str(r[0]) for r in table))


def test_698_no_fe_unchanged():
    section("[2] 协议8：无 FE 帧输出不变（硬约束锚点）")
    table = P698.parse_to_table(REPORT_BODY)
    check("不含唤醒前导行", not any("唤醒" in str(r[0]) for r in table))
    check("行数与 FE 版只差 1 行（FE 版多首行）",
          len(P698.parse_to_table(REPORT_FE)) == len(table) + 1,
          f"{len(P698.parse_to_table(REPORT_FE))} vs {len(table)}")
    check("起始字符偏移回落到 (0,0)", tuple(row_named(table, "起始字符")[4:6]) == (0, 0))
    check("结束符偏移 = (34,34)", tuple(row_named(table, "结束符")[4:6]) == (34, 34))
    check("长度域 / 控制域 / HCS / FCS 关键行冻结不变",
          row_named(table, "长度域")[1] == "2100"
          and row_named(table, "控制域")[1] == "0xC3"
          and row_named(table, "帧头校验HCS")[1] == "0x8484"
          and row_named(table, "帧校验FCS")[1] == "0xA05D")
    check("末行 = 结束符（表格尾未被位移弄乱）", table[-1][0] == "结束符")


def test_698_boundaries():
    section("[2] 协议8：局部前缀 / 全 FE / 非 68 收尾")
    sizes = {}
    for k in (1, 2, 4, 8):
        frame = b"\xFE" * k + REPORT_BODY
        res = P698.parse(frame)
        table = P698.parse_to_table(frame)
        sizes[k] = (res.get("解析状态"), (table[0][4], table[0][5]))
    check("FE×1/2/4/8 均解析成功且首行偏移 = (0, k-1)",
          all(v[0] == "成功" and v[1] == (0, k - 1) for k, v in sizes.items()),
          str(sizes))
    allfe = P698.parse_to_table(FE4)
    check("全 FE：首行仍给出前导，其后为 ❌ 失败（不臆造）",
          allfe[0][0] == "唤醒前导字节" and "❌" in str(allfe[1][0]), str(first_names(allfe)))
    not68 = b"\xFE\xFE\xFF\x00"
    t = P698.parse_to_table(not68)
    check("FE 之后非 0x68：报失败且前导行偏移正确（不把 FF 当帧头）",
          t[0][0] == "唤醒前导字节" and (t[0][4], t[0][5]) == (0, 1)
          and "❌" in str(t[1][0]), str(first_names(t)))


# ══════════════════════════════════════════════════════════════════════════
# [3] 协议6
# ══════════════════════════════════════════════════════════════════════════


def test_645_parse_and_offsets():
    section("[3] 协议6：合法帧 + FE 前导")
    fe = FE4 + LEGAL645
    check("无 FE 基线：check_frame / valid 均通过",
          DLT645Parser.check_frame(LEGAL645) and DLT645Parser.parse(LEGAL645)["valid"])
    check("带 FE：check_frame / valid 仍通过",
          DLT645Parser.check_frame(fe) and DLT645Parser.parse(fe)["valid"])
    check("CS 与前导无关（= 无 FE 值 = 帧内值）",
          DLT645Parser.calc_checksum(fe) == DLT645Parser.calc_checksum(LEGAL645)
          == LEGAL645[-2])
    res = DLT645Parser.parse(fe)
    check("wakeup_len = 4 且 raw_hex 保留原始输入（含 FE）",
          res.get("wakeup_len") == 4 and res["raw_hex"] == fe.hex().upper())
    check("地址/控制码/DI 不受前导影响",
          res["address"] == DLT645Parser.parse(LEGAL645)["address"]
          and res["control"] == DLT645Parser.parse(LEGAL645)["control"])

    base = GUI645.parse_to_table(LEGAL645)
    shifted = GUI645.parse_to_table(fe)
    check("表格首行 = 唤醒前导（0..3）",
          shifted[0][0] == "唤醒前导字节" and (shifted[0][4], shifted[0][5]) == (0, 3))
    check("其余行整体 +4（逐行）",
          len(shifted) == len(base) + 1
          and all(bx[4] == ax[4] + 4 and bx[5] == ax[5] + 4
                  for ax, bx in zip(base, shifted[1:])))
    check("校验和 / 帧结束符落到正确字节",
          tuple(row_named(shifted, "校验和")[4:6]) == (24, 24)
          and tuple(row_named(shifted, "帧结束符")[4:6]) == (25, 25))


def test_645_no_fe_unchanged():
    section("[3] 协议6：无 FE 输出不变（硬约束锚点）")
    base = GUI645.parse_to_table(LEGAL645)
    check("无唤醒行", not any("唤醒" in str(r[0]) for r in base))
    check("行数 = 13（既有基线）", len(base) == 13, str(len(base)))
    check("关键偏移冻结：帧起始符 1 (0,0) / 校验和 (20,20) / 结束符 (21,21)",
          tuple(row_named(base, "帧起始符 1")[4:6]) == (0, 0)
          and tuple(row_named(base, "校验和")[4:6]) == (20, 20)
          and tuple(row_named(base, "帧结束符")[4:6]) == (21, 21))
    check("`fields` 不含前导行（前导只在表格层，字段形状守卫不被破坏）",
          not any(wakeup_prefix.WAKEUP_FIELD_NAME in str(x[0]) for x in DLT645Parser.parse(LEGAL645)["fields"]))


def test_645_sim_unaffected():
    section("[3] 协议6：虚拟表从站引擎不受影响")
    from dlt645_frame_gen import encode_di
    from dlt645_sim import DLT645MeterSim
    from dlt645_sim.engine import extract_645_frames

    addr = "260526000028"
    gen = DLT645FrameGenerator()
    req = gen.build_frame(addr, gen.build_control(0x11, dir_bit=0), encode_di("00010000"))
    sim = DLT645MeterSim(address=addr)
    resp = sim.handle_frame(req)
    check("主站读请求仍正常应答（末字节 16H）",
          bool(resp) and resp[0][-1] == 0x16, str(resp)[:80])
    # 前导 FE 不参与切帧（切帧器本来就跳过 68 之前的杂字节）
    got = extract_645_frames(b"\xFE" * 4 + req)
    check("虚拟表侧切帧跳过 FE 且拿到同一帧", bool(got) and got[0] == req, str(got)[:80])


# ══════════════════════════════════════════════════════════════════════════
# [4] 校验器
# ══════════════════════════════════════════════════════════════════════════


def test_validator_consistency():
    section("[4] 校验器：带 FE 帧全 PASS（与解析同预处理）")
    v698 = DLT69845Validator().verify(REPORT_FE)
    check("698 带 FE：整体通过", v698.valid, [(c.name, c.level) for c in v698.checks])
    check("698 带 FE：首项为前导说明且 PASS",
          "前导" in v698.checks[0].name and v698.checks[0].level.value == "pass",
          str(v698.checks[0]))
    v698b = DLT69845Validator().verify(REPORT_BODY)
    check("698 无 FE：项与结论与改动前一致（首项仍是起始字符）",
          v698b.valid and v698b.checks[0].name == "起始字符"
          and [c.name for c in v698b.checks] == ["起始字符", "长度域一致性", "帧头校验HCS",
                                                 "帧校验FCS", "结束字符"],
          str([c.name for c in v698b.checks]))

    fe645 = FE4 + LEGAL645
    v645 = DLT645Validator().verify(fe645)
    check("645 带 FE：整体通过且含前导项",
          v645.valid and "前导" in v645.checks[0].name,
          [(c.name, c.level) for c in v645.checks])
    v645b = DLT645Validator().verify(LEGAL645)
    check("645 无 FE：无前导项，结论不变",
          v645b.valid and not any("前导" in c.name for c in v645b.checks))
    bad = DLT645Validator().verify(FE4 + _corrupt_cs(LEGAL645))
    check("645 带 FE 但 CS 错：仍 FAIL（前导不掩盖坏帧）",
          not bad.valid and any(c.name == "校验和" and c.level.value == "fail" for c in bad.checks),
          [(c.name, c.level) for c in bad.checks])


def _corrupt_cs(frame: bytes) -> bytes:
    b = bytearray(frame)
    b[-2] ^= 0xFF
    return bytes(b)


# ══════════════════════════════════════════════════════════════════════════
# [5] 护栏：其它协议不变
# ══════════════════════════════════════════════════════════════════════════

NW_FRAME = bytes.fromhex("680E000000000100 01E80005EF16".replace(" ", ""))


def _gui_table(protocol_index):
    spec = pr.get_protocol(protocol_index)
    parser = pr.build_gui_parser(protocol_index, parser_registry.get_parser(spec.parser_key))
    return parser


def test_other_protocols_unaffected():
    section("[5] 护栏：协议 0/7/9/10/11/12/13 不获得前导容忍")
    p0 = _gui_table(0)
    base0 = p0.parse_to_table(NW_FRAME)
    fe0 = p0.parse_to_table(FE4 + NW_FRAME)
    check("协议0 无 FE 正常解析", not any("❌" in str(r[0]) for r in base0))
    check("协议0 带 FE 仍失败（未越界放宽）",
          not any("唤醒" in str(r[0]) for r in fe0)
          and any("❌" in str(r[0]) for r in fe0), str(first_names(fe0)))

    for idx in (7, 9, 10, 11, 12, 13):
        try:
            table = _gui_table(idx).parse_to_table(FE4 + bytes(range(1, 25)))
            ok = not any(wakeup_prefix.WAKEUP_FIELD_NAME in str(r[0]) for r in table)
            detail = str(first_names(table))
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        check(f"协议{idx} 不产生前导行且不抛异常", ok, detail)


# ══════════════════════════════════════════════════════════════════════════
# [6] 批量 / Web 帧提取
# ══════════════════════════════════════════════════════════════════════════


def test_frame_extraction_tolerates_fe():
    section("[6] 批量/Web 提取：带 FE 的行仍提取出正确 68 帧")
    want = REPORT_BODY.hex().upper()
    desktop = batch_core._extract_69845_frames(REPORT_FE_HEX)
    check("共享核心（batch_core）提取到 1 帧且与无 FE 帧相同",
          desktop == [want], str(desktop)[:80])
    web = web_utils.extract_69845_frames(REPORT_FE_HEX)
    check("Web（web_utils）与共享核心同结果", web == desktop, str(web)[:80])
    mixed = REPORT_FE_HEX + "00" * 4 + REPORT_FE_HEX
    check("两帧粘连（含 FE）仍提取 2 帧",
          len(batch_core._extract_69845_frames(mixed)) == 2,
          str(len(batch_core._extract_69845_frames(mixed))))


# ══════════════════════════════════════════════════════════════════════════
# [7] offscreen GUI
# ══════════════════════════════════════════════════════════════════════════


class Sandbox:
    """config.json 沙箱：隔离 app_paths.data_path 与 main_gui.data_path（AGENTS §8 陷阱 42）。"""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="nw_fe_prefix_")
        self._real_app = app_paths.data_path
        self._real_gui = main_gui.data_path

        def _data_path(name):
            return pathlib.Path(os.path.join(self.tmp, name))

        app_paths.data_path = _data_path
        main_gui.data_path = _data_path
        return self

    def __exit__(self, *exc):
        app_paths.data_path = self._real_app
        main_gui.data_path = self._real_gui
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def test_gui_paths():
    section("[7] offscreen GUI：单帧页 + 解析回调（串口/蓝牙共用）")
    with Sandbox():
        win = main_gui.MainWindow()
        try:
            win.current_protocol = 8
            win.single_input.setPlainText(" ".join(f"{b:02X}" for b in REPORT_FE))
            win.parse_single()
            tbl = win.result_table_widget
            check("单帧页粘贴报障帧后出表", tbl.rowCount() > 0, f"{tbl.rowCount()} 行")
            first = tbl.item(0, 0).text() if tbl.item(0, 0) else ""
            check("首行 = 唤醒前导字节", first == "唤醒前导字节", first)
            check("表内无 ❌ 失败行",
                  not any("❌" in (tbl.item(r, 0).text() if tbl.item(r, 0) else "")
                          for r in range(tbl.rowCount())))
            check("输入框仍显示原始报文（含 FE）",
                  win.single_input.toPlainText().replace(" ", "").upper() == REPORT_FE_HEX,
                  win.single_input.toPlainText()[:40])

            summary, table = win._serial_parse_provider(REPORT_FE, 8)
            check("解析回调返回非失败表",
                  bool(table) and not any("❌" in str(r[0]) for r in table), str(first_names(table)))
            check("解析回调摘要非空且非失败占位",
                  bool(summary) and summary != "-" and "❌" not in summary, str(summary))

            win.verify_single()
            check("单帧页校验（带 FE）通过",
                  bool(win.verify_label.text()) and "❌" not in win.verify_label.text(),
                  win.verify_label.text())
        finally:
            win.close()


# ══════════════════════════════════════════════════════════════════════════
# [8] 判据自检 + 单一来源守卫
# ══════════════════════════════════════════════════════════════════════════


def test_negative_controls_and_single_source():
    section("[8] 反例自检 + 单一来源源码守卫")
    # 反例 1：判据会失败（不是恒真）——把 FE 去掉时不得解释为「成功且带前导」
    nofe = P698.parse_to_table(REPORT_BODY)
    check("反例：无 FE 输入不得产生前导行",
          not any(wakeup_prefix.WAKEUP_FIELD_NAME in str(r[0]) for r in nofe))
    # 反例 2：前缀之后必须仍是 68H —— 拿合法帧改首字节为 0xFE 内部错位也不得被「救活」
    trick = b"\xFE" + bytes([0xFE]) + REPORT_BODY[1:]
    check("反例：FE×2 + 69H 起始 → 仍失败",
          P698.parse(trick).get("解析状态") == "失败",
          str(P698.parse(trick).get("错误信息")))

    # 单一来源：前导判定只允许被白名单文件**导入**（文档/CHANGELOG 里提到名字不算使用）
    allow_import = {
        "wakeup_prefix.py",              # 定义处
        "dl_t698_45_parser.py",
        "dlt645_parser.py",
        "protocol_registry.py",          # 表格位移/行构造
        "dl_t698_45_validator.py",
        "dlt645_validator.py",
        # 串口工具分帧层（1.23.78）：68 家族分帧同样认前导 FEH（`_wakeup_base`），
        # 刻意**复用**同一实现而不是另写扫描 —— 长度返回值含前导，见 AGENTS §8 陷阱 59/75。
        # 分帧族已抽到 `frame_deframe`（单一来源），`serial_tool_widget` 仅 re-export；
        # 两者都保留在白名单：`serial_tool_widget.fix_frame_text` 仍顶层 import wakeup_prefix。
        "frame_deframe.py",
        "serial_tool_widget.py",
    }
    import_re = re.compile(r"^\s*(?:from\s+wakeup_prefix\s+import|import\s+wakeup_prefix\b)", re.M)
    # 反例：文档式提及（如 CHANGELOG 文案）不得被判为「第二份实现」
    check("反例：文档里提到名字不算使用（判据按 import 锚定）",
          not import_re.search('新增 `wakeup_prefix.py` / strip_wakeup_prefix 作为唯一实现'))
    offenders = []
    for path in (list(ROOT.glob("*.py"))
                 + list((ROOT / "validator").glob("*.py"))
                 + list((ROOT / "reflex_web" / "reflex_web").glob("*.py"))):
        if path.name in allow_import or path.name == pathlib.Path(__file__).name:
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if import_re.search(src):
            offenders.append(path.name)
    check("前导判定无第二份实现/引用（白名单之外无 import）", not offenders, str(offenders))

    # 单一来源：两个表格构建方都必须用同一位移函数
    reg_src = (ROOT / "protocol_registry.py").read_text(encoding="utf-8")
    p698_src = (ROOT / "dl_t698_45_parser.py").read_text(encoding="utf-8")
    check("协议6/8 表格均走 shift_row_offsets（禁用各自手写位移）",
          "shift_row_offsets(table" in reg_src and "shift_row_offsets(table_data" in p698_src)


def main():
    print("=" * 74)
    print("前导 FE 唤醒字节（协议8/6）回归：解析 / 表格偏移 / 校验一致性")
    print("=" * 74)
    test_wakeup_prefix_logic()
    test_698_report_frame()
    test_698_no_fe_unchanged()
    test_698_boundaries()
    test_645_parse_and_offsets()
    test_645_no_fe_unchanged()
    test_645_sim_unaffected()
    test_validator_consistency()
    test_other_protocols_unaffected()
    test_frame_extraction_tolerates_fe()
    test_gui_paths()
    test_negative_controls_and_single_source()
    print()
    print("=" * 74)
    if FAILURES:
        print(f"✗ 失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for name in FAILURES:
            print(f"   - {name}")
    else:
        print(f"全部通过（{PASS} 项）✓")
    print("=" * 74)
    sys.stdout.flush()          # os._exit 不冲刷 stdio（AGENTS §8 陷阱 73）
    os._exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
