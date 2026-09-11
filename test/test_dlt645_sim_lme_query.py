# -*- coding: utf-8 -*-
"""645 虚拟表 LME 自定义下发测试（手册 V2.4 §4.2/4.6/4.7 + §5.1.1）

覆盖：
- 纯逻辑组帧：4.2 手册 golden 逐字节、4.6（M=0/M=1/M=2）数据域、4.7 TLV 数据域
- 参数校验：地址/条目格式/数据 hex/5bit 长度上限/分类与数据 ID 范围
- 回包解析：手册 §5.1.1 接收帧（135B，CS=0x56）字段逐项 + 截断帧提示
- offscreen GUI：分组控件、4.2 隐藏条目框、一键按钮 → 帧框、失败不覆盖帧框、
  DIR=1 回包 → 结果表、离线 DIR=1 直解
- 串口回环（有 COM1↔COM2 虚拟串口对时）：真实下发 + 真实回包解析

运行：python test/test_dlt645_sim_lme_query.py
"""

import os
import sys
import time

import _path_setup  # noqa: E402  （把项目根加入 sys.path 并切 cwd）

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dlt645_frame_gen import DLT645FrameGenerator  # noqa: E402
from dlt645_sim import lme_query as L  # noqa: E402

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(f"{name} :: {detail}")
        print(f"[FAIL] {name} :: {detail}")


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    except Exception:
        return False
    return False


#: 手册 §5.1.1 发送示例（虚拟电表上位机「内外部版本」）
GOLDEN_4_2 = "68 AA AA AA AA AA AA 68 11 04 2C DD 32 37 53 16"

#: 手册 §5.1.1 接收示例（135 字节，L=0x7B，CS=0x56；已程序化验算自洽）
GOLDEN_4_2_RX = (
    "68 03 00 00 00 00 00 68 91 7B 2C DD 32 37 7B 7F 63 69 35 34 43 44 53 77 35 34 68 34 81 "
    "63 35 83 3B 53 5B 73 88 77 98 96 53 63 6B 53 65 63 65 63 64 63 6D 67 68 6D 64 65 B7 46 "
    "61 35 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 "
    "33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 "
    "33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 56 16 "
)


def hx(s):
    return bytes.fromhex("".join(s.split()))


def fields_of(parsed):
    """(字段名去缩进, 解析值) 映射，兼容 3/4 元组。"""
    out = {}
    for _f, _raw, value, _desc in L.reply_rows(parsed):
        out[_f.replace("└", "").strip()] = value.strip()
    return out


# ---------------------------------------------------------------------------
# 1. 4.2 读模块版本（手册 golden）
# ---------------------------------------------------------------------------

def t_42_golden():
    print("\n== 1. 4.2 读模块版本（手册 §5.1.1 golden）==")
    frame = L.build_single_sta_query()
    check("4.2 帧与手册发送示例逐字节一致",
          frame.hex(" ").upper() == GOLDEN_4_2, frame.hex(" ").upper())
    check("4.2 帧长 16 字节", len(frame) == 16, str(len(frame)))
    check("4.2 控制码 C=11H 主站读", frame[8] == 0x11, hex(frame[8]))
    check("4.2 L=04H 仅 DI", frame[9] == 0x04 and frame[10:14] == hx("2C DD 32 37"),
          f"L={frame[9]} DI={frame[10:14].hex()}")
    check("4.2 CS=0x53", frame[-2] == 0x53, hex(frame[-2]))
    # 自定义地址（低字节在前）
    f2 = L.build_single_sta_query("123456789012")
    check("4.2 自定义地址低字节在前", f2[1:7] == hx("12 90 78 56 34 12"), f2[1:7].hex(" "))
    check("4.2 describe_frame 含控制码说明",
          "C=11H" in L.describe_frame(frame) and "读数据" in L.describe_frame(frame),
          L.describe_frame(frame))
    check("4.2 地址非法报错", raises(lambda: L.build_single_sta_query("XYZ")))
    check("4.2 地址长度不符报错", raises(lambda: L.build_single_sta_query("1234")))
    check("4.2 不需要条目参数", L.KIND_NEEDS_ENTRIES[L.KIND_SINGLE_STA] is False)


# ---------------------------------------------------------------------------
# 2. 4.6 读内部详细信息
# ---------------------------------------------------------------------------

def t_46_query():
    print("\n== 2. 4.6 读内部详细信息 ==")
    d = lambda f: DLT645FrameGenerator.descramble(f[10:-2])  # noqa: E731

    f0 = L.build_dual_query(entries="")
    check("4.6 留空 = M=0 读全量（数据域 DI+00+00）",
          d(f0).hex().upper() == "01DD00FF0000", d(f0).hex().upper())
    check("4.6 控制码 C=11H", f0[8] == 0x11, hex(f0[8]))

    f1 = L.build_dual_query(entries="0/15")
    check("4.6 M=1 请求头 = 数据ID15|分类0",
          d(f1).hex().upper() == "01DD00FF00010F00", d(f1).hex().upper())

    f2 = L.build_dual_query(entries="0/15,7/1")
    check("4.6 M=2 请求头含分类7<<6",
          d(f2).hex().upper() == "01DD00FF00020F00C101", d(f2).hex().upper())

    p = L.decode_reply(f1)
    check("4.6 请求回读接口名", "4.6" in str(p.get("di_desc")), str(p.get("di_desc")))
    fmap = fields_of(p)
    check("4.6 回读 M=1", fmap.get("条目数 M") == "1", str(fmap.get("条目数 M")))
    check("4.6 回读条目名=本地接口默认信息",
          any("本地接口默认信息" in k for k in fmap), str(list(fmap)[:6]))

    pm0 = fields_of(L.decode_reply(f0))
    desc0 = " ".join(r[3] for r in L.reply_rows(L.decode_reply(f0)))
    check("4.6 M=0 回读=读全部支持条目",
          pm0.get("条目数 M") == "0" and "全部" in desc0, str(pm0)[:200] + " | " + desc0[:120])

    check("4.6 条目格式缺 / 报错", raises(lambda: L.build_dual_query(entries="abc")))
    check("4.6 分类超范围报错", raises(lambda: L.build_dual_query(entries="9/1")))
    check("4.6 数据ID超范围报错", raises(lambda: L.build_dual_query(entries="0/99")))
    check("4.6 条目列表直传也可用",
          d(L.build_dual_query(entries=[(0, 15)])).hex().upper() == "01DD00FF00010F00")


# ---------------------------------------------------------------------------
# 3. 4.7 设置
# ---------------------------------------------------------------------------

def t_47_set():
    print("\n== 3. 4.7 设置 ==")
    d = lambda f: DLT645FrameGenerator.descramble(f[10:-2])  # noqa: E731

    f = L.build_dual_set(items="0/15:0500")
    check("4.7 控制码 C=14H", f[8] == 0x14, hex(f[8]))
    check("4.7 数据域 = DI+00+M+TLV头+数据",
          d(f).hex().upper() == "01DD00FF00010F140500", d(f).hex().upper())
    # TLV 头位域：数据ID15 | 分类0<<6 | 编码BIN(2)<<9 | 长度2<<11
    hdr = int.from_bytes(d(f)[6:8], "little")
    check("4.7 TLV 头位域（ID6/分类3/编码2/长度5）",
          (hdr & 0x3F) == 15 and ((hdr >> 6) & 0x07) == 0
          and ((hdr >> 9) & 0x03) == L.ENC_BIN and ((hdr >> 11) & 0x1F) == 2, hex(hdr))
    check("4.7 条目编码取定义（0/15 = BIN）",
          L.entry_encoding(0, 15) == L.ENC_BIN, str(L.entry_encoding(0, 15)))
    check("4.7 条目名（0/15 本地接口默认信息）",
          L.entry_name(0, 15) == "本地接口默认信息", L.entry_name(0, 15))

    f2 = L.build_dual_set(items="0/15:0500,1/3:010203")
    dd = d(f2)
    check("4.7 M=2", dd[5] == 2, str(dd[5]))
    check("4.7 第二条 TLV 头长度=3",
          ((int.from_bytes(dd[10:12], "little") >> 11) & 0x1F) == 3, dd.hex().upper())
    check("4.7 第二条数据 010203", dd[12:15] == hx("01 02 03"), dd[12:15].hex())

    p = L.decode_reply(f)
    check("4.7 请求回读接口名=设置请求",
          "4.7" in str(p.get("di_desc")) and "设置请求" in str(p.get("di_desc")),
          str(p.get("di_desc")))
    p2 = L.decode_reply(f2)
    fmap = fields_of(p2)
    check("4.7 回读 M=2", fmap.get("条目数 M") == "2", str(fmap.get("条目数 M")))

    # 长度超 5bit 上限（模块资产编码 32B）
    check("4.7 长度超 31 报错",
          raises(lambda: L.build_dual_set(items="2/17:" + "AB" * 32)))
    check("4.7 恰好 31 字节可用",
          L.build_dual_set(items="2/17:" + "AB" * 31)[8] == 0x14)
    check("4.7 长度 32 的报错文案含上限",
          "31" in _err(lambda: L.build_dual_set(items="2/17:" + "AB" * 32)))
    check("4.7 缺冒号报错", raises(lambda: L.build_dual_set(items="0/15")))
    check("4.7 数据非 hex 报错", raises(lambda: L.build_dual_set(items="0/15:0G")))
    check("4.7 奇数位数据报错", raises(lambda: L.build_dual_set(items="0/15:050")))
    check("4.7 空条目报错", raises(lambda: L.build_dual_set(items="")))
    check("4.7 空条目列表报错", raises(lambda: L.build_dual_set(items=[])))
    check("4.7 未定义条目按 BIN 编码",
          L.entry_encoding(6, 63) == L.ENC_BIN, str(L.entry_encoding(6, 63)))

    check("4.7 确认框条目描述含名称与字节数",
          L.describe_items("0/15:0500") == ["分类0/数据15 本地接口默认信息（2 字节）"],
          str(L.describe_items("0/15:0500")))


def _err(fn):
    try:
        fn()
    except ValueError as e:
        return str(e)
    return ""


# ---------------------------------------------------------------------------
# 4. 回包解析（手册 §5.1.1 接收帧）
# ---------------------------------------------------------------------------

def t_reply_parse():
    print("\n== 4. 回包解析（手册 §5.1.1 接收帧）==")
    rx = hx(GOLDEN_4_2_RX)
    check("接收帧 135 字节且自洽", len(rx) == 135 and rx[9] == 0x7B and rx[-2] == 0x56
          and (sum(rx[:10 + rx[9]]) & 0xFF) == 0x56,
          f"len={len(rx)} L={rx[9]} CS={hex(rx[-2])}")

    p = L.decode_reply(rx)
    check("接收帧 解析有效", p.get("valid"), str(p.get("error")))
    check("接收帧 接口名=4.2 应答",
          "4.2" in str(p.get("di_desc")) and "应答" in str(p.get("di_desc")),
          str(p.get("di_desc")))
    fm = fields_of(p)
    expect = {
        "外部厂商代码": "LH", "外部芯片代码": "60", "外部版本号": "V0102",
        "外部版本日期": "2020-11-10", "MCU内部版本号": "v0244",
        "网络层(NWK)版本号": "N0230",
        "物理层(PHY)版本号": "P2008", "DSP版本号": "V4028",
        "硬件信息长度": "0 字节",
    }
    for k, v in expect.items():
        check(f"接收帧 {k}={v}", fm.get(k) == v, str(fm.get(k)))
    # APS 层：本帧层级标志字节为 0x01（不可打印，手册示例显示为 □），解析器原样带出
    check("接收帧 应用层(APS)版本号含 0135",
          str(fm.get("应用层(APS)版本号") or "").endswith("0135"),
          repr(fm.get("应用层(APS)版本号")))
    check("接收帧 无「数据不完整」提示", not any("不完整" in k for k in fm),
          str([k for k in fm if "不完整" in k]))
    check("接收帧 reply_summary 含外部版本号", "V0102" in L.reply_summary(p),
          L.reply_summary(p)[:120])

    # 截断帧：同一数据单元砍到 40 字节后重新封帧（L/CS 合法）→ 应提示不完整且不崩
    gen = DLT645FrameGenerator()
    dtu = DLT645FrameGenerator.descramble(rx[10:10 + rx[9]])
    cut_frame = gen.build_frame(rx[1:7], 0x91, dtu[:40])
    pc = L.decode_reply(cut_frame)
    fmc = fields_of(pc)
    check("截断帧 解析有效（帧结构合法）", pc.get("valid"), str(pc.get("error")))
    check("截断帧 提示「数据不完整」",
          any("不完整" in k for k in fmc), str([k for k in fmc])[:160])
    check("截断帧 仍尽力给出已解析字段（外部厂商代码=LH）",
          fmc.get("外部厂商代码") == "LH", str(fmc.get("外部厂商代码")))

    check("reply_rows 兼容 3 元组", L.reply_rows(
        {"fields": [("A", "1", "说明")]}) == [("A", "1", "", "说明")],
        str(L.reply_rows({"fields": [("A", "1", "说明")]})))
    check("reply_rows 空 fields 安全", L.reply_rows({}) == []

          and L.reply_rows(None) == [])


# ---------------------------------------------------------------------------
# 5. offscreen GUI
# ---------------------------------------------------------------------------

class _FakeMB:
    """替换模块内 QMessageBox，收集调用并避免模态阻塞。"""

    warned = []
    criticals = []
    questions = 0
    answer = True

    class StandardButton:
        Yes = 1
        No = 0

    @classmethod
    def warning(cls, *a, **k):
        cls.warned.append(a[2] if len(a) > 2 else "")

    @classmethod
    def critical(cls, *a, **k):
        cls.criticals.append(a[2] if len(a) > 2 else "")

    @classmethod
    def question(cls, *a, **k):
        cls.questions += 1
        return cls.StandardButton.Yes if cls.answer else cls.StandardButton.No

    @classmethod
    def reset(cls):
        cls.warned, cls.criticals, cls.questions = [], [], 0
        cls.answer = True


def t_gui():
    print("\n== 5. offscreen GUI ==")
    from PySide6.QtWidgets import QApplication

    import dlt645_meter_sim_widget as mw

    app = QApplication.instance() or QApplication([])
    real_mb = mw.QMessageBox
    mw.QMessageBox = _FakeMB
    w = mw.Dlt645VirtualMeterWidget()
    try:
        _FakeMB.reset()
        check("分组存在（模块版本查询）",
              any("模块版本查询" in g.title() for g in w.findChildren(mw.QGroupBox)),
              str([g.title() for g in w.findChildren(mw.QGroupBox)]))

        def btn(text):
            for b in w.findChildren(mw.QPushButton):
                if b.text() == text:
                    return b
            return None

        for text in ("读模块版本(4.2)", "读内部详细信息(4.6)", "设置(4.7)",
                     "下发到串口", "复制hex"):
            check(f"按钮存在：{text}", btn(text) is not None)

        check("默认目标地址 = AA×6", w.lme_addr_edit.text() == L.DEFAULT_ADDR,
              w.lme_addr_edit.text())
        check("默认条目框可见（当前 4.6）", w.lme_entry_edit.isVisibleTo(w))

        # 点 4.2 → 帧框 = 手册 golden；未监听仅日志、无弹窗
        btn("读模块版本(4.2)").click()
        check("4.2 按钮 → 帧框 = 手册 golden",
              w.lme_frame_edit.text() == GOLDEN_4_2, w.lme_frame_edit.text())
        check("4.2 按钮 → 条目框隐藏且清空",
              (not w.lme_entry_edit.isVisibleTo(w)) and w.lme_entry_edit.text() == "",
              f"visible={w.lme_entry_edit.isVisibleTo(w)} text={w.lme_entry_edit.text()!r}")
        check("4.2 未监听无弹窗", not _FakeMB.warned and not _FakeMB.criticals,
              f"warned={_FakeMB.warned} crit={_FakeMB.criticals}")
        check("4.2 日志含未下发提示",
              "串口未监听" in w.log_view.toPlainText(), w.log_view.toPlainText()[-160:])

        # 点 4.6（条目框恢复可见）
        w.lme_entry_edit.setText("0/15")
        _FakeMB.reset()
        btn("读内部详细信息(4.6)").click()
        want46 = L.build_dual_query(L.DEFAULT_ADDR, "0/15").hex(" ").upper()
        check("4.6 按钮 → 帧框 = 期望帧",
              w.lme_frame_edit.text() == want46, w.lme_frame_edit.text())
        check("4.6 按钮 → 条目框恢复可见", w.lme_entry_edit.isVisibleTo(w))
        check("4.6 日志含控制码说明",
              "C=11H" in w.log_view.toPlainText(), w.log_view.toPlainText()[-200:])

        # 生成失败：不覆盖帧框 + 弹 warning
        _FakeMB.reset()
        before = w.lme_frame_edit.text()
        w.lme_entry_edit.setText("abc")
        btn("读内部详细信息(4.6)").click()
        check("条目格式错 → warning", bool(_FakeMB.warned), str(_FakeMB.warned))
        check("条目格式错 → 不覆盖帧框", w.lme_frame_edit.text() == before,
              w.lme_frame_edit.text())

        # 4.7：确认框（默认 Yes）→ 帧框 + 未监听日志
        w.lme_entry_edit.setText("0/15:0500")
        _FakeMB.reset()
        btn("设置(4.7)").click()
        check("4.7 弹确认框", _FakeMB.questions == 1, str(_FakeMB.questions))
        check("4.7 按钮 → 帧框 = 期望帧",
              w.lme_frame_edit.text()
              == L.build_dual_set(L.DEFAULT_ADDR, "0/15:0500").hex(" ").upper(),
              w.lme_frame_edit.text())

        # 4.7 取消：仍生成帧但不下发
        _FakeMB.reset()
        _FakeMB.answer = False
        btn("设置(4.7)").click()
        check("4.7 取消 → 日志留痕且无下发",
              "取消" in w.log_view.toPlainText(), w.log_view.toPlainText()[-200:])
        _FakeMB.answer = True

        # 「下发到串口」未监听 → 弹提示
        _FakeMB.reset()
        btn("下发到串口").click()
        check("未监听点「下发到串口」弹提示", bool(_FakeMB.warned), str(_FakeMB.warned))

        # 已监听但写串口失败 → critical + 日志（R3；假串口线程只实现写失败路径）
        class _FailingSerial:
            @staticmethod
            def isRunning():
                return True

            @staticmethod
            def write_frame(data):
                return "模拟写失败"

        _FakeMB.reset()
        w._serial_thread = _FailingSerial()
        btn("下发到串口").click()
        check("写失败 → critical + 日志",
              bool(_FakeMB.criticals) and "❌ 下发失败" in w.log_view.toPlainText(),
              f"crit={_FakeMB.criticals} log={w.log_view.toPlainText()[-120:]!r}")
        w._serial_thread = None

        # 回包：直接调 _on_slave_frame（串口线程 emit 的同一入口）
        w.resp_table.setRowCount(0)
        w._on_slave_frame(GOLDEN_4_2_RX)
        texts = [w.resp_table.item(r, 2).text() for r in range(w.resp_table.rowCount())
                 if w.resp_table.item(r, 2)]
        check("回包 → 结果表填充（含 V0102）", "V0102" in texts, str(texts[:8]))
        check("回包 → 日志含模块回包摘要",
              "模块回包解析" in w.log_view.toPlainText(), w.log_view.toPlainText()[-200:])

        # 回包 hex 非法：不崩
        _FakeMB.reset()
        w._on_slave_frame("ZZ")
        check("回包 hex 非法不崩且有日志",
              "非法" in w.log_view.toPlainText(), w.log_view.toPlainText()[-120:])

        # 离线 DIR=1 直解
        w.resp_table.setRowCount(0)
        w.req_input.setPlainText(GOLDEN_4_2_RX)
        w._offline_generate()
        texts2 = [w.resp_table.item(r, 2).text() for r in range(w.resp_table.rowCount())
                  if w.resp_table.item(r, 2)]
        check("离线 DIR=1 → 直接解析出 外部版本号",
              "V0102" in texts2, str(texts2[:8]))
        check("离线 DIR=1 → 日志含「检测到从站回包」",
              "检测到从站回包" in w.log_view.toPlainText(),
              w.log_view.toPlainText()[-200:])
        check("离线 DIR=1 不算作请求（无「解析失败」异常）", not _FakeMB.criticals,
              str(_FakeMB.criticals))

        # 离线 DIR=0 原行为保持不变
        w.req_input.setPlainText(GOLDEN_4_2)      # C=11H 读请求
        w._offline_generate()
        check("离线 DIR=0 仍走从站应答（无响应=无该 DI）",
              "请求" in w.log_view.toPlainText(), w.log_view.toPlainText()[-200:])
    finally:
        w.shutdown()
        mw.QMessageBox = real_mb
        app.processEvents()


# ---------------------------------------------------------------------------
# 6. 串口回环（需本机 COM1↔COM2 虚拟串口对）
# ---------------------------------------------------------------------------

def _ports():
    try:
        import serial.tools.list_ports as lp
        return {p.device.upper() for p in lp.comports()}
    except Exception:
        return set()


def t_serial_loopback():
    print("\n== 6. 串口回环（COM1↔COM2，可选）==")
    ports = _ports()
    if not {"COM1", "COM2"} <= ports:
        print(f"[SKIP] 本机缺少 COM1/COM2 虚拟串口对（现有：{sorted(ports)}）")
        return
    import serial
    from PySide6.QtWidgets import QApplication

    import dlt645_meter_sim_widget as mw

    app = QApplication.instance() or QApplication([])
    real_mb = mw.QMessageBox
    mw.QMessageBox = _FakeMB
    w = mw.Dlt645VirtualMeterWidget()
    peer = None
    try:
        w.port_combo.clear()
        w.port_combo.addItem("COM1", "COM1")
        w.port_combo.setCurrentIndex(0)
        w._toggle_serial()
        th = w._serial_thread
        t0 = time.time()
        while th is not None and th._ser is None and time.time() - t0 < 3:
            app.processEvents()
            time.sleep(0.05)
        check("串口从站已打开 COM1", th is not None and th._ser is not None,
              "COM1 未打开")

        peer = serial.Serial("COM2", 9600, timeout=0.3)
        peer.reset_input_buffer()

        # 一键下发 4.2 请求（已监听 → 自动写串口）
        w.lme_entry_edit.clear()
        w.lme_addr_edit.setText(L.DEFAULT_ADDR)
        w.btn_lme_42.click()
        t0 = time.time()
        got = b""
        while time.time() - t0 < 3 and len(got) < 16:
            got += peer.read(64)
        check("串口收到 4.2 请求帧（逐字节 == golden）",
              got == hx(GOLDEN_4_2), got.hex(" ").upper())

        # 回环注入模块回包 → 串口线程 DIR=1 分流 → GUI 结果表
        w.resp_table.setRowCount(0)
        peer.write(hx(GOLDEN_4_2_RX))
        t0 = time.time()
        ok = False
        while time.time() - t0 < 5:
            app.processEvents()
            texts = [w.resp_table.item(r, 2).text()
                     for r in range(w.resp_table.rowCount())
                     if w.resp_table.item(r, 2)]
            if "V0102" in texts:
                ok = True
                break
            time.sleep(0.05)
        check("模块回包经串口自动解析进结果表（V0102）", ok,
              str([w.resp_table.item(r, 2).text() for r in range(w.resp_table.rowCount())
                   if w.resp_table.item(r, 2)])[:200])
        check("日志含「模块回包」", "模块回包" in w.log_view.toPlainText(),
              w.log_view.toPlainText()[-200:])
    finally:
        if peer is not None:
            try:
                peer.close()
            except Exception:
                pass
        w.shutdown()
        mw.QMessageBox = real_mb
        app.processEvents()


def main():
    t_42_golden()
    t_46_query()
    t_47_set()
    t_reply_parse()
    t_gui()
    t_serial_loopback()
    print(f"\n=== {PASS} 项通过，{len(FAILURES)} 项失败 ===")
    for f in FAILURES:
        print("  ✗", f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
