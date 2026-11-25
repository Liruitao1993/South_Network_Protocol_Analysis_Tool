# -*- coding: utf-8 -*-
"""协议9 批量解析：日志里 ``setAttenuVal: 'FE…AA0D0A'`` 这类**测试装置控制帧**必须被解析。

现场日志（用户 2026-11-11 报障）::

    2026-11-11 07:00:01.123 setAttenuVal: 'FEFEFE05010300000000000004AA0D0A'O"

帧本身（功能驱动板控制协议）::

    FE FE FE | 05 | 01 地址 | 03 命令(设置衰减器A的衰减值) | 00×6 数据 | 04 校验 | AA 0D 0A

**报障根因**：批量预处理 `_split_hex_frames_with_lines` 的普通行分支是
「取最后一个冒号后 → 再截到第一个引号前」。对这种 ``key: 'HEX'`` 行，
截到第一个引号前正好是**空串** ⇒ 整行被丢弃 ⇒ 批量里看不到这条控制帧。
（``fc_payload_data := '…'`` 早有专门分支，其它 ``key: '…'`` 写法没覆盖。）

修法：新增单一来源 `batch_core.quoted_payload_hex()`（成对引号内的纯 hex），
**三处同源副本**（共享 `batch_core` / 桌面 `main_gui` / Web `web_utils`）统一调用。

运行：``python test/test_csg_batch_attenu_frame.py``
"""

import _path_setup  # noqa: E402,F401

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import batch_core  # noqa: E402
from csg_new_gen_parser import CSGNewGenParser, is_test_device_control_frame  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name} {detail}")
        FAILED.append(f"{name} {detail}")


FRAME_A = "FEFEFE05010300000000000004AA0D0A"      # 命令 03 衰减器A，值 0
FRAME_C = "FEFEFE0501051400000000001AAA0D0A"      # 命令 05 衰减器C，值 20

# ======================================================================
print("[1] quoted_payload_hex：成对引号内的 hex 单一来源")
# ======================================================================
check("单引号 key: 'HEX'",
      batch_core.quoted_payload_hex(f"setAttenuVal: '{FRAME_A}'") == FRAME_A,
      batch_core.quoted_payload_hex(f"setAttenuVal: '{FRAME_A}'"))
check("带时间戳与尾部垃圾",
      batch_core.quoted_payload_hex(
          f"2026-11-11 07:00:01.123 setAttenuVal: '{FRAME_A}'O\"") == FRAME_A)
check("双引号",
      batch_core.quoted_payload_hex(f'setAttenuVal: "{FRAME_A}"') == FRAME_A)
check("引号内带空格分隔",
      batch_core.quoted_payload_hex("x: 'FE FE FE 05 01 03 00 00 00 00 00 00 04 AA 0D 0A'")
      == FRAME_A)
check("非 hex 引号内容返回空（不猜）",
      batch_core.quoted_payload_hex("msg: 'hello world'") == "")
check("引号内奇数长度返回空",
      batch_core.quoted_payload_hex("x: 'FEFEFE05010300000000000004AA0D0'") == "")
check("引号内过短返回空", batch_core.quoted_payload_hex("x: 'FE05'") == "")
check("无反引号/未闭合引号返回空",
      batch_core.quoted_payload_hex("x: 'FEFEFE050103") == "")
check("普通冒号行不误判为引号负载",
      batch_core.quoted_payload_hex("Line 339: 260718-111145-349: 1103000001") == "")

# ======================================================================
print("[2] 批量预处理：三种写法都能保留控制帧（原来全被丢）")
# ======================================================================
CASES = {
    "时间戳+单引号+尾部": f"2026-11-11 07:00:01.123 setAttenuVal: '{FRAME_A}'O\"",
    "仅 key: 'HEX'": f"setAttenuVal: '{FRAME_A}'",
    "双引号": f'setAttenuVal: "{FRAME_A}"',
    "等号形式": f"setAttenuVal={FRAME_A}",
    "裸帧": FRAME_A,
    "工装板 10 字节": "FE05010300000000000004AA0D0A",
}
for label, line in CASES.items():
    res = batch_core.strip_csg_new_gen_frame_prefix(line, "auto")
    kept = res.text.splitlines()
    check(f"{label}：预处理后保留 1 行", len(kept) == 1, kept)
    if kept:
        check(f"{label}：保留的就是控制帧", kept[0] in (FRAME_A, "FE05010300000000000004AA0D0A"),
              kept)

# 多行混合：控制帧 + 普通业务帧 + 无帧行
mixed = "\n".join([
    f"2026-11-11 07:00:01.123 setAttenuVal: '{FRAME_A}'O\"",
    "2026-11-11 07:00:02.000 rx fc: '09010000000000000100010203040506070809'",
    "2026-11-11 07:00:03.000 无关日志",
    f"2026-11-11 07:00:04.000 setAttenuVal: '{FRAME_C}'O\"",
])
res = batch_core.strip_csg_new_gen_frame_prefix(mixed, "auto")
kept = res.text.splitlines()
check("多行混合：保留 3 行（2 控制帧 + 1 业务帧）", len(kept) == 3, kept)
check("多行混合：首行是衰减器A", kept and kept[0] == FRAME_A, kept)
check("多行混合：行号映射可用", len(res.line_map) == len(kept), res.line_map)

# ======================================================================
print("[3] 端到端：提取 → 解析 → 摘要（用户要的「也要解析」）")
# ======================================================================
stripped = batch_core.strip_csg_new_gen_frame_prefix(
    "\n".join([f"setAttenuVal: '{FRAME_A}'", f"setAttenuVal: '{FRAME_C}'"]), "auto")
frames = batch_core.extract_frames_for_protocol(stripped.text, 9)
check("提取到 2 帧", len(frames) == 2, frames)
parser = CSGNewGenParser()
parsed = []
for hex_frame, _ed_type, _line_no in frames:
    parsed.append(parser.parse_to_table(bytes.fromhex(hex_frame), parse_level="auto"))

check("两帧都判为测试装置控制帧",
      all(is_test_device_control_frame(f[0]) for f in frames), frames)
first_rows = [r[0] for r in parsed[0]]
check("第 1 帧解析出功能驱动板标题",
      any("测试装置功能驱动板控制协议" in str(n) for n in first_rows), first_rows[:3])
check("第 1 帧解析出命令码「设置衰减器A的衰减值」",
      any("设置衰减器A的衰减值" in str(r[2]) for r in parsed[0]), first_rows[:5])
check("第 1 帧解析出衰减值 0 dB",
      any(r[0] == "衰减器A衰减值" and "0 dB" in str(r[2]) for r in parsed[0]),
      [r[:3] for r in parsed[0] if "衰减" in str(r[0])])
check("第 2 帧解析出「衰减器C」与 20 dB",
      any(r[0] == "衰减器C衰减值" and "20 dB" in str(r[2]) for r in parsed[1]),
      [r[:3] for r in parsed[1] if "衰减" in str(r[0])])
check("第 1 帧摘要带衰减值",
      "衰减器A衰减值" in batch_core.test_device_summary(parsed[0]),
      batch_core.test_device_summary(parsed[0]))
check("第 2 帧摘要带衰减值",
      "衰减器C衰减值" in batch_core.test_device_summary(parsed[1]),
      batch_core.test_device_summary(parsed[1]))
check("校验和判为正确",
      any(r[0] == "校验和" and "正确" in str(r[2]) for r in parsed[1]),
      [r[:3] for r in parsed[1] if r[0] == "校验和"])

# ======================================================================
print("[4] 三处同源副本口径一致（共享 / 桌面 / Web）")
# ======================================================================
LINE = f"2026-11-11 07:00:01.123 setAttenuVal: '{FRAME_A}'O\""

shared = batch_core.strip_csg_new_gen_frame_prefix(LINE, "auto").text.splitlines()
check("共享 batch_core 保留控制帧", shared == [FRAME_A], shared)

try:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    import main_gui

    window = main_gui.MainWindow.__new__(main_gui.MainWindow)   # 不跑 __init__（避免开窗）
    window.CSG_MONITOR_PREFIX = main_gui.MainWindow.CSG_MONITOR_PREFIX
    desktop = main_gui.MainWindow._strip_csg_new_gen_frame_prefix(window, LINE, "auto")
    desktop_lines = desktop.split("\n") if isinstance(desktop, str) else list(desktop.text.splitlines())
    check("桌面 main_gui 保留控制帧（与共享一致）", desktop_lines == [FRAME_A], desktop_lines)
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    check("桌面 main_gui 保留控制帧", False, str(exc))

try:
    from reflex_web.web_utils import strip_csg_new_gen_prefix

    web = strip_csg_new_gen_prefix(LINE, "auto").split("\n")
    check("Web web_utils 保留控制帧（与共享一致）", web == [FRAME_A], web)
except Exception as exc:  # noqa: BLE001
    print(f"  · Web 侧不可用（跳过）：{exc}")

# ======================================================================
print("[5] 回归：既有写法不被影响")
# ======================================================================
# fc_payload_data 跨行引号（历史行为）
payload_log = "fc_payload_data := '0901000000000000010001\n0203040506070809'"
res = batch_core.strip_csg_new_gen_frame_prefix(payload_log, "auto")
check("fc_payload_data 跨行仍能拼帧",
      "09010000000000000100010203040506070809" in res.text.replace("\n", ""),
      res.text)
# Line XXX: ... : hex
res2 = batch_core.strip_csg_new_gen_frame_prefix(
    "Line 339: 260718-111145-349: 09010000000000000100010203040506070809", "auto")
check("Line XXX 前缀仍能取到帧",
      res2.text.splitlines() == ["09010000000000000100010203040506070809"], res2.text)
# ED 包装帧原样保留
ed_line = "rx: 'ED1E000002EF0100000000 0901000000000000010001'".replace(" ", "")
res3 = batch_core.strip_csg_new_gen_frame_prefix(ed_line, "auto")
check("ED 包装行仍原样保留", res3.text.upper().startswith("ED"), res3.text[:20])

# ======================================================================
print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败：")
    for item in FAILED:
        print("   -", item)
    sys.exit(1)
print("✅ 全部通过")
