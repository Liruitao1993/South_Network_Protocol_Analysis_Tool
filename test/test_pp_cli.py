"""通用文本预处理命令链 pp_cli 的拆分与执行测试

覆盖：
- 纯逻辑：split_commands 半角基准（回归，不能被归一化逻辑破坏）
- 纯逻辑：全角空格 / 全角引号 / 弯引号 / NBSP / 零宽空格 → 归一化后正确拆分
- 纯逻辑：半角分隔符下「参数里刻意保留全角字符」不被改写
- 纯逻辑：错误提示（未知命令附码位 + 半角提示、参数不足、引号不闭合）
- 端到端：用户场景「find　＂CSG＂」全角命令 → 与半角命令产出逐字相同
- GUI（offscreen）：MainWindow._run_cli_preprocessor 走真实按钮回调，
  全角命令不再弹「预处理失败」，且非法命令仍会弹出错误（反例）

背景：中文输入法全角状态下打出的空格不是 U+0020、引号不是 U+0022，
shlex 既不把它们当分隔符也不当引号 → 整串被当成一个命令名，
表现为「未知命令: find　＂CSG＂」。

运行：python test/test_pp_cli.py
"""

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from pp_cli import (  # noqa: E402
    COMMANDS,
    normalize_command_text,
    parse_and_run,
    split_commands,
)

PASS = 0
FAILURES = []

FS = "\u3000"  # 全角空格
FW_DQ = "\uff02"  # 全角双引号 ＂
FW_SQ = "\uff07"  # 全角单引号 ＇
CURLY_L, CURLY_R = "\u201c", "\u201d"
NBSP = "\u00a0"
ZWSP = "\u200b"


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(f"{name} :: {detail}")
        print(f"[FAIL] {name} :: {detail}")


def section(title):
    print(f"\n== {title} ==")


LOG_LINES = [
    "260915-110449-066: 224] NWK: 接收帧长度,fcLen=390,len=390,rev,Chnnl:HPLC[0],rssi=27,snr=31,0000,0018,4372,0FFF,0080,0FFF",
    "260915-110449-066: A5] CSG: 查找入节点信息.",
    "260915-110449-066: E1A] NWK: 收到发现列表,TEI=128",
    "260915-110449-066: A6] CSG: 查找入节点信息.",
    "260915-110449-066: 224] NWK: 接收帧长度,fcLen=242",
]
EXPECTED_CSG = [LOG_LINES[1], LOG_LINES[3]]


# ── 1. 半角基准（回归） ───────────────────────────────────────────────


def t_halfwidth_baseline():
    section("1. split_commands 半角基准（一直可用的写法）")
    cases = [
        ('find "CSG"', ["find", "CSG"]),
        ("find CSG", ["find", "CSG"]),
        (
            'find "tcp data:" excluding "len:\\d+: "',
            ["find", "tcp data:", "excluding", "len:\\d+: "],
        ),
        ("hex_extract dedup", ["hex_extract", "dedup"]),
        (
            'find "60F0" excluding "mrd:" dedup',
            ["find", "60F0", "excluding", "mrd:", "dedup"],
        ),
        (
            'find "nwk:" replace ".*nwk:" "NWK:" head 20',
            ["find", "nwk:", "replace", ".*nwk:", "NWK:", "head", "20"],
        ),
        ("", []),
        ("   ", []),
    ]
    for text, want in cases:
        got = split_commands(text)
        check(f"{text!r} → {want}", got == want, f"{got}")

    check(
        "normalize_command_text 对纯半角串是恒等",
        normalize_command_text('find "CSG"') == 'find "CSG"',
    )


# ── 2. 全角 / 异体分隔符与引号（本次修复的 bug） ─────────────────────


def t_fullwidth_variants():
    section("2. 全角空格/全角引号 → 归一化后正常拆分")
    cases = {
        "全角空格 + 全角双引号": f"find{FS}{FW_DQ}CSG{FW_DQ}",
        "全角空格 + 弯引号": f"find{FS}{CURLY_L}CSG{CURLY_R}",
        "全角空格 + 半角引号": f'find{FS}"CSG"',
        "NBSP + 半角引号": f'find{NBSP}"CSG"',
        "NBSP + 半角引号(排除命令)": f'excluding{NBSP}"len:"',
        "零宽空格 + 半角空格 + 引号": f'find{ZWSP} "CSG"',
        "全角单引号": f"find{FS}{FW_SQ}CSG{FW_SQ}",
        "无引号参数": f"find{FS}CSG",
        "全角空格分隔的多命令": f"hex_extract{FS}dedup",
        "全角空格的多参数命令": f"find{FS}{FW_DQ}CSG{FW_DQ}{FS}dedup",
    }
    for label, text in cases.items():
        want = {
            "NBSP + 半角引号(排除命令)": ["excluding", "len:"],
            "全角空格分隔的多命令": ["hex_extract", "dedup"],
            "全角空格的多参数命令": ["find", "CSG", "dedup"],
        }.get(label, ["find", "CSG"])
        got = split_commands(text)
        check(label, got == want, f"{got!r} != {want!r}")

    # 归一化映射本身的边界：不应把普通中文当分隔符
    check("中文字符不被归一化", normalize_command_text("查找 CSG") == "查找 CSG")
    check("全角空格映射为半角", normalize_command_text(f"a{FS}b") == "a b")
    check("BOM 被剥离", normalize_command_text("\ufefffind CSG") == "find CSG")


# ── 3. 参数内容不被误改（取舍的保护面） ───────────────────────────────


def t_argument_content_preserved():
    section("3. 半角分隔符下参数里的全角字符原样保留")
    text = f'find "A{FS}B"'
    got = split_commands(text)
    check("参数含全角空格时不被改写", got == ["find", f"A{FS}B"], f"{got!r}")

    text2 = 'replace "　" "_"'
    got2 = split_commands(text2)
    check("全角空格作为替换目标时保留", got2 == ["replace", FS, "_"], f"{got2!r}")

    got3 = split_commands('find "数据 表"')
    check("参数内半角空格仍被引号保护", got3 == ["find", "数据 表"], f"{got3!r}")


# ── 4. 错误提示 ───────────────────────────────────────────────────────


def _raises(fn):
    try:
        fn()
    except ValueError as e:
        return str(e)
    except Exception as e:  # pragma: no cover - 便于定位
        return f"__OTHER__{type(e).__name__}: {e}"
    return ""


def t_error_messages():
    section("4. 错误提示（未知命令 / 参数不足 / 引号不闭合）")
    msg = _raises(lambda: parse_and_run("x", ["no_such_cmd"]))
    check("未知命令报错", "未知命令: no_such_cmd" in msg, msg)
    check("未知命令附可用命令", "可用命令" in msg and "hex_extract" in msg, msg)
    check("未知命令附半角提示", "半角空格" in msg, msg)

    msg_cjk = _raises(lambda: parse_and_run("x", ["查找"]))
    check("非 ASCII 命令名附码位", "U+67E5" in msg_cjk and "U+627E" in msg_cjk, msg_cjk)
    check("非 ASCII 命令名带转义形式", "\\u67e5" in msg_cjk, msg_cjk)

    msg_args = _raises(lambda: parse_and_run("x", ["replace", "a"]))
    check(
        "参数不足报错含命令名与数量",
        "replace" in msg_args and "2" in msg_args,
        msg_args,
    )

    msg_quote = _raises(lambda: split_commands('find "CSG'))
    check("引号不闭合抛 ValueError", "quotation" in msg_quote.lower(), msg_quote)

    check(
        "COMMANDS 含用户可用命令",
        {
            "find",
            "excluding",
            "replace",
            "head",
            "tail",
            "skip",
            "hex_extract",
            "tcp_extract",
            "dedup",
            "merge_payloads",
        }
        <= set(COMMANDS),
        str(sorted(COMMANDS)),
    )


# ── 5. 端到端：用户上报场景 ───────────────────────────────────────────


def t_end_to_end_user_case():
    section("5. 端到端：全角 find 命令产出与半角逐字相同")
    text = "\n".join(LOG_LINES)
    half = parse_and_run(text, split_commands('find "CSG"'))
    for label, cmd in [
        ("全角空格+全角双引号", f"find{FS}{FW_DQ}CSG{FW_DQ}"),
        ("全角空格+弯引号", f"find{FS}{CURLY_L}CSG{CURLY_R}"),
        ("NBSP", f'find{NBSP}"CSG"'),
    ]:
        out = parse_and_run(text, split_commands(cmd))
        check(f"{label} 与半角结果一致", out == half, f"{out!r}")
    check(
        "结果只保留 CSG 行", half.splitlines() == EXPECTED_CSG, repr(half.splitlines())
    )

    chain = parse_and_run(text, split_commands(f"find{FS}{FW_DQ}CSG{FW_DQ}{FS}dedup"))
    check("全角多命令链可用", chain.splitlines() == EXPECTED_CSG, repr(chain))


# ── 6. GUI（offscreen）：真实按钮回调路径 ─────────────────────────────


class FakeMessageBox:
    """记录 main_gui 里弹出的提示框（不阻塞）。"""

    def __init__(self):
        self.calls = []

    def _rec(self, kind, args):
        title = args[1] if len(args) > 1 else ""
        text = args[2] if len(args) > 2 else ""
        self.calls.append((kind, title, str(text)))

    def warning(self, *args, **kwargs):
        self._rec("warning", args)

    def critical(self, *args, **kwargs):
        self._rec("critical", args)

    def information(self, *args, **kwargs):
        self._rec("information", args)

    def question(self, *args, **kwargs):
        self._rec("question", args)
        return None

    def kind(self, kind):
        return [c for c in self.calls if c[0] == kind]


def t_gui_run_preprocessor():
    section("6. GUI（offscreen）：_run_cli_preprocessor 全角命令不再失败")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    import app_paths
    import main_gui

    real_file = Path(str(app_paths.data_path("config.json")))
    real_md5 = (
        hashlib.md5(real_file.read_bytes()).hexdigest() if real_file.exists() else ""
    )

    tmp = tempfile.mkdtemp(prefix="pp_cli_gui_")
    cfg = Path(tmp) / "config.json"
    if real_file.exists():
        shutil.copyfile(real_file, cfg)
    else:  # pragma: no cover - 开发目录一般都有
        cfg.write_text("{}", encoding="utf-8")

    real_data_path = main_gui.data_path
    real_app_data_path = app_paths.data_path
    real_mb = main_gui.QMessageBox
    fake = FakeMessageBox()

    def _sandbox_path(name):
        return Path(tmp) / name

    # 沙箱需同时盖住两条路径解析：`main_gui` 直接 import 的那份，与
    # `llm_preprocess_widget.save_config()` 内部 `from app_paths import data_path`
    # 解析出的那份。否则退出保存（`_save_app_config` 会连带调用它）会把
    # 真实 config.json 写掉，本函数末尾的反污染断言即失败。
    main_gui.data_path = _sandbox_path
    app_paths.data_path = _sandbox_path
    main_gui.QMessageBox = fake

    windows = []
    try:
        w = main_gui.MainWindow()
        windows.append(w)
        app.processEvents()
        combo = w._pp_cmd_combo
        check("预处理命令框可编辑", combo.isEditable())

        def run_with(text):
            fake.calls.clear()
            combo.setEditText(text)
            w._run_cli_preprocessor()
            app.processEvents()

        log = "\n".join(LOG_LINES)
        w.batch_input.setPlainText(log)
        run_with(f"find{FS}{FW_DQ}CSG{FW_DQ}")
        check("全角命令未弹「预处理失败」", not fake.kind("critical"), str(fake.calls))
        check(
            "全角命令结果回填为 CSG 行",
            w.batch_input.toPlainText().splitlines() == EXPECTED_CSG,
            repr(w.batch_input.toPlainText()),
        )

        # 反例：非法命令仍要有明确错误（不能因为归一化把错误吞掉）
        w.batch_input.setPlainText(log)
        run_with("no_such_cmd")
        crit = fake.kind("critical")
        check("非法命令仍弹错误", len(crit) == 1, str(fake.calls))
        check(
            "错误提示含未知命令与半角提示",
            crit and "未知命令" in crit[0][2] and "半角" in crit[0][2],
            str(crit),
        )

        # 反例：引号不闭合走「命令解析错误」警告
        w.batch_input.setPlainText(log)
        run_with('find "CSG')
        warn = fake.kind("warning")
        check("引号不闭合弹解析错误", len(warn) == 1, str(fake.calls))
        check("解析错误提示含半角说明", warn and "半角" in warn[0][2], str(warn))

        # 半角命令走同一路径（回归）
        w.batch_input.setPlainText(log)
        run_with('find "CSG"')
        check(
            "半角命令同样正常",
            not fake.kind("critical")
            and w.batch_input.toPlainText().splitlines() == EXPECTED_CSG,
            str(fake.calls),
        )
    finally:
        for win in windows:
            try:
                win.close()
            except Exception:
                pass
        main_gui.data_path = real_data_path
        app_paths.data_path = real_app_data_path
        main_gui.QMessageBox = real_mb
        shutil.rmtree(tmp, ignore_errors=True)

    now_md5 = (
        hashlib.md5(real_file.read_bytes()).hexdigest() if real_file.exists() else ""
    )
    check("真实 config.json 未被测试改写", now_md5 == real_md5)


def main():
    t_halfwidth_baseline()
    t_fullwidth_variants()
    t_argument_content_preserved()
    t_error_messages()
    t_end_to_end_user_case()
    t_gui_run_preprocessor()
    print(f"\n=== {PASS} 项通过，{len(FAILURES)} 项失败 ===")
    for item in FAILURES:
        print("  ✗", item)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
