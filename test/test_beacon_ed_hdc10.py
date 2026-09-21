# -*- coding: utf-8 -*-
"""协议11 TCP/ED：信标帧现场样本（帧长域与 EE 不一致时仍可解出中央信标）

现场帧（2026-09-20 用户提供）:
    ED A4 ... FF EE，共 292 字节；帧长域 0x00A4=164（声明整包 168），
    但第 167 字节不是 EE，真正的 EE 在缓冲区末尾 → 旧实现解包失败，
    业务被当成「应用层 报文ID 0x0A4 配电信息上报」。

修复:
    batch_core._ed_frame_parts / extract_business_from_ed_frame：
    帧长域与 EE 不一致且缓冲区以 EF..EE 结尾时，按末尾 EE 重算整包。
    extract 未指定 wrapper 时 resolve 带上 protocol_index（10/11 优先 gx）。
    HDC10 auto：FCCS 失败时若 DT=0 且版本位为 0，按信标帧继续解析（带提示）。

期望（协议11）:
    ED 头 = 国网HDC监控包装头 / FC+Payload / HPLC / pb_len=136
    业务 = DT=0 信标帧 + FCCS✓ + 信标类型=中央信标 + 时隙分配条目

运行: python -X utf8 -u test/test_beacon_ed_hdc10.py
"""

import os
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])
for _name in ("warning", "information", "critical", "question"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import _config_sandbox  # noqa: E402
from batch_core import (  # noqa: E402
    unwrap_ed_for_parse,
    extract_business_from_ed_frame,
    ed_wrapper_summary_name,
)
from hdc10_parser import HDC10Parser  # noqa: E402
import main_gui  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass
_config_sandbox.install()

BEACON_HEX = (
    "ED A4 00 00 02 EF 88 26 15 0E 01 00 88 00 00 03 00 00 17 76 18 0E 01 40 6B "
    "03 00 1D 16 BB C2 02 00 00 90 98 01 63 01 00 00 00 00 00 00 00 00 00 00 00 "
    "03 00 0F 01 00 00 64 00 00 90 98 01 63 04 64 00 01 0A 14 00 00 00 02 00 02 "
    "00 C0 23 00 00 33 00 00 64 05 00 00 00 00 59 DD 16 0E 98 08 00 00 00 00 F4 "
    "01 00 01 F4 01 00 02 F4 01 00 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 3E AC 12 B5 C5 75 86 FF EE"
)
DATA = bytes.fromhex("".join(BEACON_HEX.split()))

PASS = 0
FAIL = 0
FAILED = []


def section(t):
    print(f"\n{t}")


def check(d, c, detail=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print(f"  ✓ {d}")
    else:
        FAIL += 1
        FAILED.append(d)
        print(f"  ✗ {d}" + (f"\n      {detail}" if detail else ""))


def _val(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return str(r[2]).strip()
    return None


def _cmt(rows, name):
    for r in rows:
        if str(r[0]).strip() == name:
            return str(r[3]).strip() if r[3] else ""
    return None


def main():
    section("[1] 帧结构")
    check("长度 292", len(DATA) == 292, str(len(DATA)))
    check("首 ED 尾 EE", DATA[0] == 0xED and DATA[-1] == 0xEE)
    flen = DATA[1] | (DATA[2] << 8)
    check("帧长域 164（与末尾 EE 不一致）", flen == 164, str(flen))
    check("第167字节不是 EE", DATA[flen + 3] != 0xEE, hex(DATA[flen + 3]))

    section("[2] extract / unwrap 协议11")
    hex_clean = "".join(BEACON_HEX.split())
    biz_hex, dtype = extract_business_from_ed_frame(hex_clean, None, 11)
    check("extract(None) 得到业务", bool(biz_hex), dtype)
    check("业务以 00 03 开头（DT=0 信标 FC）",
          biz_hex.upper().startswith("00030000"), biz_hex[:20])
    ed_rows, biz = unwrap_ed_for_parse(DATA, 11)
    check("unwrap ED 行非空", len(ed_rows) >= 8, str(len(ed_rows)))
    check("ED 标题=国网HDC", ed_rows and "国网HDC" in ed_rows[0][0], str(ed_rows[:1]))
    check("ED 控制域2=FC+Payload", any(r[0] == "控制域2" and "FC+Payload" in str(r[2])
                                      for r in ed_rows))
    check("业务长度 276", len(biz) == 276, str(len(biz)))

    section("[3] HDC10Parser auto 业务 = 中央信标")
    rows = HDC10Parser().parse_to_table(biz, parse_level="auto", channel="plc")
    check("定界符=信标帧", _val(rows, "定界符类型(DT)") == "0"
          or (_cmt(rows, "定界符类型(DT)") or "").find("信标") >= 0,
          f"{_val(rows, '定界符类型(DT)')} / {_cmt(rows, '定界符类型(DT)')}")
    check("NID=3", _val(rows, "网络标识(NID)") == "3", _val(rows, "网络标识(NID)"))
    check("FCCS 校验正确", "校验正确" in (_cmt(rows, "帧控制校验序列(FCCS)") or ""),
          _cmt(rows, "帧控制校验序列(FCCS)"))
    check("信标类型=中央信标", _val(rows, "信标类型") == "2"
          or "中央信标" in (_cmt(rows, "信标类型") or ""),
          f"{_val(rows, '信标类型')} / {_cmt(rows, '信标类型')}")
    check("存在信标管理信息", any("信标管理信息" in str(r[0]) for r in rows))
    check("存在时隙分配/信标周期", any("信标周期" in str(r[0]) or "时隙" in str(r[0])
                                    for r in rows))

    section("[4] TCP 摘要")
    Host = type("H", (), {
        "_get_gw_new_gen_summary": main_gui.MainWindow._get_gw_new_gen_summary,
        "_TEST_MODE_SENTINELS": main_gui.MainWindow._TEST_MODE_SENTINELS,
        "_extract_test_mode_content": staticmethod(
            main_gui.MainWindow._extract_test_mode_content
        ),
    })()
    s = Host._get_gw_new_gen_summary(rows)
    full = (ed_wrapper_summary_name(ed_rows[0][0]) + " | " + s) if ed_rows else s
    print("  摘要:", full)
    check("摘要含国网HDC", "国网HDC" in full, full)
    check("摘要含信标", "信标" in full, full)
    check("摘要含 NID", "NID:3" in full, full)
    check("摘要不再误判为配电信息上报", "配电信息" not in full, full)

    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    if FAILED:
        for n in FAILED:
            print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
