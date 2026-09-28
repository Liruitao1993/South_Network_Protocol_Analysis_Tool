"""协议8（DL/T 698.45-2017）帧长公式 L + 2 回归 — 真实帧 / 附录 H.1.1 示例 / 三处提取器同源。

背景：协议 6.2.2 a) 定义长度域 L 为「传输帧中**不包含**起始字符和结束字符的数据长度」，
且 L 本身含两个长度域字节 ⇒ **整帧 = L + 2**。历史上三处提取器都写成 `L + 4`、串口分帧
写成 `L + 3`，并按「第 4 字节是第二个 68H」判定 698.45 —— 真实 698.45 链路帧没有第二个
68H（`68 | L(2B) | C | … | FCS | 16`），两个错误叠加导致：
  - 桌面/共享/Web 的协议8 批量提取**恒返回空**（末字节自证必然失败）；
  - 串口工具选「协议8」时 698 分帧策略**恒不命中**，退化为时间聚合。

覆盖：
  [1] 帧长公式的协议依据（6.2.2 a + 附录 H.1.1 逐字节自证 + 解析器 HCS/FCS 双通过）
  [2] 桌面 / 共享(batch_core) / Web 三处提取器同源对拍（单帧 / 多帧 / 噪声 / 末字节不符）
  [3] 桌面分派 _extract_frames_for_protocol(text, 8) 与共享 extract_frames_for_protocol 端到端
  [4] 串口工具 698 分帧策略（frame_length_for / declared_frame_len / 不误判南网·645 / 错误公式反例）
  [5] 串口工具接收端到端（逐字节交付 → 整帧一行）

运行: QT_QPA_PLATFORM=offscreen python -u test/test_dl_t698_45_extract.py
"""

import os

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, staticmethod(lambda *a, **k: 0)).start()

_config_sandbox.install()

import batch_core  # noqa: E402
import serial_tool_widget as stw  # noqa: E402
from dl_t698_45_parser import DLT69845Parser  # noqa: E402
from reflex_web import web_utils  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n{title}")


def hexs(b) -> str:
    return bytes(b).hex().upper()


# 现场实测帧（服务器上行 GET-Response，OI=0x2004 属性2 特征0 索引1）
USER_FRAME = bytes.fromhex(
    "681F00C3260231310400009001" "7F8D" "850109200402010105FFFF9ED00000" "6D17" "16"
)
# 标准附录 H.1.1「登录」请求（HCS/FCS 用占位 00 00，只验证帧长公式与字节布局）
DOC_LOGIN = bytes.fromhex(
    "681E0081" "0507091905162000" "0000" "01000000B407E005130408050000A4" "0000" "16"
)
# 南网真实形帧（L = 整帧，14 字节）与 645 构造帧（L + 12 = 16 字节）
NW_FRAME = bytes.fromhex("680E00000000010001E80005EF16")
F645 = bytes.fromhex("6812345678901268110433333333AA16")


def main():
    print("=" * 66)
    print("协议8 帧长公式 L + 2 回归（桌面 / 共享 / Web / 串口）")
    print("=" * 66)

    section("[1] 帧长公式的协议依据")
    check("现场帧 33 字节", len(USER_FRAME) == 33, str(len(USER_FRAME)))
    check("现场帧 L = 31，整帧 = L + 2",
          int.from_bytes(USER_FRAME[1:3], "little") == 31
          and 31 + 2 == len(USER_FRAME))
    check("附录 H.1.1 示例 32 字节、L = 30、整帧 = L + 2",
          len(DOC_LOGIN) == 32 and int.from_bytes(DOC_LOGIN[1:3], "little") == 30
          and 30 + 2 == len(DOC_LOGIN),
          f"{len(DOC_LOGIN)} / {int.from_bytes(DOC_LOGIN[1:3], 'little')}")
    check("两帧均以 16H 收尾", USER_FRAME[-1] == 0x16 and DOC_LOGIN[-1] == 0x16)
    check("现场帧第 4 字节是控制域、不是第二个 68H",
          USER_FRAME[3] != 0x68 and DOC_LOGIN[3] != 0x68,
          f"{USER_FRAME[3]:02X} / {DOC_LOGIN[3]:02X}")
    r = DLT69845Parser().parse(USER_FRAME)
    check("解析器自证：解析成功 + HCS/FCS 双通过（字节布局正确）",
          r.get("解析状态") == "成功"
          and r["帧头校验HCS"]["校验结果"] == "通过"
          and r["帧校验FCS"]["校验结果"] == "通过",
          str(r.get("错误信息", "")))

    section("[2] 桌面 / 共享 / Web 三处提取器同源对拍")
    from main_gui import MainWindow  # 延迟导入（构造开销大）

    extractors = [
        ("桌面", lambda c: MainWindow._extract_69845_frames(None, c)),
        ("共享", batch_core._extract_69845_frames),
        ("Web", web_utils.extract_69845_frames),
    ]
    two = hexs(USER_FRAME) + hexs(DOC_LOGIN)
    cases = [
        ("单帧（现场 33B）", hexs(USER_FRAME), [hexs(USER_FRAME)]),
        ("单帧（附录 H.1.1 32B）", hexs(DOC_LOGIN), [hexs(DOC_LOGIN)]),
        ("两帧拼接", two, [hexs(USER_FRAME), hexs(DOC_LOGIN)]),
        ("前置噪声 + 换行", "AABB\n" + hexs(USER_FRAME) + "\nCC", [hexs(USER_FRAME)]),
        ("末字节非 16H → 丢弃", hexs(USER_FRAME)[:-2] + "17", []),
        ("尾部缺 1 字节 → 丢弃", hexs(USER_FRAME)[:-2], []),
        ("长度域偏小、末字节对不上 → 丢弃",
         hexs(USER_FRAME)[:2] + "1E00" + hexs(USER_FRAME)[6:], []),
    ]
    for label, text, want in cases:
        for who, fn in extractors:
            got = fn(text)
            check(f"{who}：{label}", got == want, f"{got!r} != {want!r}")

    section("[3] 端到端分派（桌面 + 共享）")
    app = QApplication.instance() or QApplication([])
    mw = MainWindow()
    try:
        got = mw._extract_frames_for_protocol(hexs(USER_FRAME), 8)
        check("桌面 _extract_frames_for_protocol(…, 8) 出 1 帧",
              got == [hexs(USER_FRAME)], str(got))
        got2 = mw._extract_frames_for_protocol(two, 8)
        check("桌面协议8：两帧拼接出 2 帧",
              got2 == [hexs(USER_FRAME), hexs(DOC_LOGIN)], str(got2))
        shared = batch_core.extract_frames_for_protocol(hexs(USER_FRAME), 8)
        check("共享 extract_frames_for_protocol(…, 8) 出 1 帧且三元组契约成立",
              len(shared) == 1 and shared[0][0] == hexs(USER_FRAME)
              and shared[0][1] == "" and shared[0][2] == 0, str(shared))
    finally:
        mw.close()
        app.processEvents()

    section("[4] 串口工具 698 分帧策略")
    check("dlt698_45 现场帧 → 33（L + 2）",
          stw.frame_length_for("dlt698_45", USER_FRAME) == 33,
          str(stw.frame_length_for("dlt698_45", USER_FRAME)))
    check("dlt698_45 附录 H.1.1 → 32（L + 2）",
          stw.frame_length_for("dlt698_45", DOC_LOGIN) == 32,
          str(stw.frame_length_for("dlt698_45", DOC_LOGIN)))
    check("declared_frame_len 现场帧 → 33",
          stw.declared_frame_len(USER_FRAME) == 33,
          str(stw.declared_frame_len(USER_FRAME)))
    check("declared_frame_len 附录 H.1.1 → 32",
          stw.declared_frame_len(DOC_LOGIN) == 32,
          str(stw.declared_frame_len(DOC_LOGIN)))
    check("未收全（前 31 字节）也判 33，不会按 31 切",
          stw.declared_frame_len(USER_FRAME[:31]) == 33,
          str(stw.declared_frame_len(USER_FRAME[:31])))
    check("ft12_68 遇 698 帧 → 0（按南网口径到齐却非 16H）",
          stw.frame_length_for("ft12_68", USER_FRAME) == 0,
          str(stw.frame_length_for("ft12_68", USER_FRAME)))
    check("dlt698_45 遇南网帧 → 0（末字节自证是南网）",
          stw.frame_length_for("dlt698_45", NW_FRAME) == 0,
          str(stw.frame_length_for("dlt698_45", NW_FRAME)))
    check("dlt698_45 遇 645 帧 → 0",
          stw.frame_length_for("dlt698_45", F645) == 0,
          str(stw.frame_length_for("dlt698_45", F645)))
    check("南网帧仍按 L = 整帧（回归不变）",
          stw.frame_length_for("ft12_68", NW_FRAME) == 14
          and stw.declared_frame_len(NW_FRAME) == 14,
          f"{stw.frame_length_for('ft12_68', NW_FRAME)} / {stw.declared_frame_len(NW_FRAME)}")
    check("645 帧仍按 L + 12（回归不变）",
          stw.frame_length_for("dlt645", F645) == 16
          and stw.declared_frame_len(F645) == 16)
    # 错误公式反例：旧口径（整帧 = L 或 L + 3 / L + 4）必须与真实值不同
    check("反例：整帧 ≠ L（31）", stw.declared_frame_len(USER_FRAME) != 31)
    check("反例：整帧 ≠ L + 3（34）",
          stw.frame_length_for("dlt698_45", USER_FRAME) != 34)
    check("反例：整帧 ≠ L + 4（35）",
          len(USER_FRAME) != int.from_bytes(USER_FRAME[1:3], "little") + 4)

    section("[5] 串口工具接收端到端（逐字节交付）")
    w = stw.SerialToolWidget()
    try:
        w._last_tx_protocol = 8
        for b in bytes(USER_FRAME) + bytes(DOC_LOGIN):
            w._on_raw_data(bytes([b]))
            w._flush_raw_display()
        lines = [t for k, t in w._rx_log_queue if k == "raw"]
        check("逐字节交付两帧 → 两行，且每行是完整帧",
              lines == [stw.bytes_to_hex(USER_FRAME), stw.bytes_to_hex(DOC_LOGIN)],
              str(lines))
        check("RX 帧数 = 2", w._rx_frames == 2, str(w._rx_frames))
        # 南网帧在协议8 下不得被切坏（末字节自证 → 交回时间聚合，不做错误切分）
        w._reset_stats()
        w._rx_log_queue.clear()
        w._raw_buffer.clear()
        w._on_raw_data(NW_FRAME)
        w._flush_raw_display()
        check("协议8 收到南网帧：不产生切分（缓冲原样留给时间聚合）",
              bytes(w._raw_buffer) == NW_FRAME, hexs(w._raw_buffer))
    finally:
        w.cleanup()
        w.deleteLater()
        app.processEvents()

    print(f"\nPASS={PASS} FAIL={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
