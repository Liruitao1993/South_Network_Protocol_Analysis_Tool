# -*- coding: utf-8 -*-
"""scripts/hex_clean.py 回归测试（1.23.0 回退模式）+ 脚本列表判重

背景：hex_clean 原实现只识别监控日志 'ED ... 'O 标记，协议9批量解析输入
若是裸 hex 行则逐行跳过、输出为空，GUI 弹「脚本输出为空，未修改输入内容」
看似运行无变化。修复：全文无 'ED 标记时回退到逐行通用清洗（剥离行首时间戳/
日志标签、去非 hex、保留长度≥16 且偶数的行）。

运行：python test/test_hex_clean_script.py
"""
import _path_setup  # noqa: E402

import importlib.util
import json
import os
import tempfile
from pathlib import Path

_ROOT = Path(_path_setup.__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "hex_clean_under_test", _ROOT / "scripts" / "hex_clean.py"
)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

PASS = 0


def check(cond, msg):
    global PASS
    assert cond, f"FAIL: {msg}"
    PASS += 1
    print(f"  ok: {msg}")


# ── 1. 回退模式：裸 hex 输入（原 bug 场景） ──────────────────────
print("[1] 回退模式（无 'ED 标记）")

plain = "ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16\nED 0F 00 00 00 00 01 00 01 E8 00 06 F0 17\n"
check(
    hc.process(plain, {})
    == "ED0700000000010001E80005EF16\nED0F00000000010001E80006F017",
    "空格分隔 hex 行 → 逐行归一化连续大写 hex",
)

check(
    hc.process("ed0700000000010001e80005ef16\n", {}) == "ED0700000000010001E80005EF16",
    "小写连续 hex 行 → 大写化",
)

ts_line = "2026-08-05 20:40:29:713 ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16\n"
check(hc.process(ts_line, {}) == "ED0700000000010001E80005EF16", "行首时间戳剥离后再清洗")

label_ts = "流程日志：2026-08-05 20:40:29:713 ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16\n"
check(hc.process(label_ts, {}) == "ED0700000000010001E80005EF16", "行首标签+时间戳：数字不混入帧")

monitor_noise = (
    "2026-09-10 10:00:00 -> 接收机 Has Get\n"
    "ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16\n"
)
check(
    hc.process(monitor_noise, {}) == "ED0700000000010001E80005EF16",
    "中文/箭头噪声行被过滤，hex 行保留",
)

noise = "start of log\nED0700000000010001E80005EF16\n======\nE800\n"
check(
    hc.process(noise, {}) == "ED0700000000010001E80005EF16",
    "短 hex(<8字节)/纯噪声行被过滤",
)

check(hc.process("EDEDEDEDEDEDEDE\n", {}) == "", "奇数长度残行被丢弃")
check(hc.process("", {}) == "", "空输入 → 空输出")
check(hc.process("   \n\n  \n", {}) == "", "全空白输入 → 空输出")

# ── 2. 标记模式（原用途不回退） ──────────────────────────────────
print("[2] 标记模式（含 'ED ... 'O）")

marked = "流程日志：'ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16'O\n"
check(
    hc.process(marked, {}) == "ED0700000000010001E80005EF16",
    "单行 'ED...'O 帧提取保持原行为",
)

cross = (
    "2026-08-05 20:40:29:713 'ED 07 00 00 00 00\n"
    "2026-08-05 20:40:29:800 01 00 01 E8 00 05 EF 16'O\n"
)
check(hc.process(cross, {}) == "ED0700000000010001E80005EF16", "跨行帧拼接闭合")

label_cont = (
    "'ED 07 00 00 00 00\n"
    "流程日志：2026-08-05 20:40:29:800 01 00 01 E8 00 05 EF 16'O\n"
)
check(
    hc.process(label_cont, {}) == "ED0700000000010001E80005EF16",
    "续帧行首标签+时间戳剥离",
)

truncated = "2026-08-05 20:40:29:713 'ED 07 00 00 00 00 01 00 01\n"
check(hc.process(truncated, {}) == "", "'O 未闭合的截断帧丢弃（标记模式优先，不退回逐行）")

two_frames = (
    "'ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16'O "
    "'ED 0F 00 00 00 00 01 00 01 E8 00 06 F0 17'O\n"
)
check(
    hc.process(two_frames, {})
    == "ED0700000000010001E80005EF16\nED0F00000000010001E80006F017",
    "同行两帧拆分",
)

# ── 3. 混合输入：有标记 → 走标记模式，裸行不参与 ─────────────────
print("[3] 混合输入")

mixed = (
    "ED 07 00 00 00 00 01 00 01 E8 00 05 EF 16\n"
    "'ED 0F 00 00 00 00 01 00 01 E8 00 06 F0 17'O\n"
)
check(
    hc.process(mixed, {}) == "ED0F00000000010001E80006F017",
    "任一行含 'ED 即按标记模式处理（与旧行为一致）",
)

# ── 4. 脚本列表判重（main_gui._script_key / _load_py_scripts 去重回填+自愈） ──
print("[4] 脚本列表判重")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

from main_gui import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])  # noqa: F841

fwd = str(_ROOT / "scripts" / "hex_clean.py").replace("\\", "/")
back = fwd.replace("/", "\\")
check(MainWindow._script_key(fwd) == MainWindow._script_key(back), "正/反斜杠同一路径 → 同键")
check(
    MainWindow._script_key(fwd)
    != MainWindow._script_key(str(_ROOT / "scripts" / "tcp_payload_extract.py")),
    "不同文件 → 不同键",
)


class _DummyWin:
    """只带 _load_py_scripts 所需属性的最小宿主（不构造 MainWindow）"""

    _resolve_script_path = MainWindow._resolve_script_path
    _script_key = staticmethod(MainWindow._script_key)
    _load_py_scripts = MainWindow._load_py_scripts
    _persist_py_scripts = MainWindow._persist_py_scripts

    def __init__(self, config_path):
        self._config_path = config_path
        self._py_script_combo = QComboBox()
        self._py_builtin_scripts = []


with tempfile.TemporaryDirectory() as td:
    cfg = Path(td) / "config.json"
    dup = {"path": "scripts/hex_clean.py", "name": "hex_clean"}
    cfg.write_text(
        json.dumps(
            {
                "py_scripts": [
                    {"path": "scripts/hex_clean.py", "name": "Hex 清洗（示例）"},
                    dup,
                    dict(dup),
                    dict(dup),
                ]
            }
        ),
        encoding="utf-8",
    )
    d = _DummyWin(cfg)
    d._load_py_scripts()
    names = [d._py_script_combo.itemText(i) for i in range(d._py_script_combo.count())]
    check(
        names == ["Hex 清洗（示例）", "hex_clean"],
        f"config.json 同名同路径重复条目回填去重 → {names}",
    )
    # 自愈：真实 _persist_py_scripts 已把去重后的列表写回 config.json
    rewritten = json.loads(cfg.read_text(encoding="utf-8"))["py_scripts"]
    check(
        len(rewritten) == 2
        and rewritten[0]["path"] == "scripts/hex_clean.py"
        and rewritten[1]["name"] == "hex_clean",
        f"自愈写回 config.json → {rewritten}",
    )

print(f"\n全部通过：{PASS} 项")
