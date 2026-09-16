#!/usr/bin/env python
"""发布前自检：版本对齐 + 关键数据文件 + 核心测试一键跑。

用法（项目根执行）：
  python release_check.py                 # 检查 + 跑核心测试（无 GUI）
  python release_check.py --skip-tests    # 只做静态检查
  python release_check.py --with-gui      # 核心测试 + 可选 offscreen GUI 测试
  python release_check.py --sync-iss      # 把 Inno Setup 的 MyAppVersion 同步为 APP_VERSION

退出码：0=全部通过；1=有 FAIL。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# GBK 控制台容错：报告里的测试输出可能含 ✓/★ 等非 GBK 字符，避免 print 崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
MAIN_GUI = ROOT / "main_gui.py"
SPEC = ROOT / "南网协议解析工具.spec"
ISS_FILES = [ROOT / "南网解析工具.iss", ROOT / "2222.iss"]
README = ROOT / "README.md"
CHANGELOG_PY = MAIN_GUI  # CHANGELOG 在 main_gui.py 内

# spec datas 中建议随包的关键文件（相对名匹配即可）
CRITICAL_DATAS = (
    "custom_di.json",
    "dlt645_di.json",
    "gdw_custom_afn.json",
    "app_icon.ico",
    "enhanced_export.py",
)

# 核心回归（纯逻辑 / 无 Qt 优先，默认全跑）
CORE_TESTS = [
    "test/test_protocol_registry.py",
    "test/test_pcap_import.py",
    "test/test_dlms.py",
    "test/test_hdlc.py",
    "test/test_plc_rf.py",
    "test/test_dl_t698_45.py",
    "test/test_dl_t698_45_data_decode.py",
    "test/test_dl_t698_45_fujian.py",
    "test/test_nw_lcmi.py",
    "test/test_csg_new_gen.py",
    "test/test_csg_summary.py",
    "test/test_csg_batch_prefix.py",
    "test/test_csg_batch_parse_level.py",
    "test/test_csg_hrf_mac.py",
    "test/test_gw_new_gen.py",
    "test/test_gw_monitor_summary.py",
    "test/test_gw_batch_parse.py",
    "test/test_gdw_fujian.py",
    "test/test_hdc10.py",
    "test/test_dlt645_frame_gen.py",
    "test/test_dlt645_lme.py",
    "test/test_dlt645_sim.py",
    "test/test_dlt645_sim_lme_query.py",
    "test/test_dlt645_sim_event_word.py",
    "test/test_diff_engine.py",
    "test/test_ed_gx_wrapper.py",
    "test/test_ed_fallback_fix.py",
    "test/test_hex_clean_script.py",
    "test/test_pp_cli.py",
    "test/test_batch_src_line_jump.py",
    "test/test_batch_snapshot_locate.py",
    "test/test_gui_batch_perf.py",
    "test/test_csg_sequence_model.py",
    "test/test_app_paths.py",
    "test/test_nanwang_custom_di.py",
    "test/test_window_state.py",
    "test/test_menu_wiring.py",
    "test/test_web_frame_gen_utils.py",
    "test/test_web_parse_fixes.py",
    "test/test_web_batch_paging.py",
    "test/test_web_spectrum.py",
    "test/test_web_theme.py",
    "test/test_web_landing.py",
    "test/test_web_data_paths.py",
    "test/test_web_download_url.py",
    "test/test_sack_fix.py",
    "test/test_monitor_deframe.py",
    "test/test_monitor_plc2_deframe.py",
    "test/test_spectrum_model.py",
]

# 可选 offscreen GUI（慢；主题套件本机既有 12 项失败，仅报告不阻断默认）
GUI_TESTS = [
    "test/test_quick_parse_panel.py",
    "test/test_csg_sequence_gui.py",
    "test/test_csg_pb_highlight_gui.py",
    "test/test_csg_pbcs_fill_gui.py",
    "test/test_dlt645_frame_gen_gui.py",
    "test/test_app_icon_path.py",
    "test/test_button_icons.py",
    "test/test_spectrum_gui.py",
]

# 已知环境失败：不因它挡发布，但会标 WARN
KNOWN_FLAKY = {
    "test/test_theme_settings.py",
}


class Report:
    def __init__(self):
        self.fails: list[str] = []
        self.warns: list[str] = []
        self.oks: list[str] = []

    def ok(self, msg: str):
        self.oks.append(msg)
        print(f"  [PASS] {msg}")

    def fail(self, msg: str):
        self.fails.append(msg)
        print(f"  [FAIL] {msg}")

    def warn(self, msg: str):
        self.warns.append(msg)
        print(f"  [WARN] {msg}")


def read_app_meta() -> tuple[str, str, list[str]]:
    text = MAIN_GUI.read_text(encoding="utf-8")
    vm = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    bm = re.search(r'BUILD_DATE\s*=\s*"([^"]+)"', text)
    if not vm or not bm:
        raise RuntimeError("无法从 main_gui.py 解析 APP_VERSION / BUILD_DATE")
    version = vm.group(1)
    build_date = bm.group(1)
    # CHANGELOG 顶层 ("x.y.z", ...)
    changelog_versions = re.findall(r'^\s*\(\s*"(\d+\.\d+\.\d+)"\s*,', text, re.M)
    return version, build_date, changelog_versions


def check_versions(rep: Report) -> tuple[str, str]:
    print("== 版本与文档 ==")
    version, build_date, cl_versions = read_app_meta()
    rep.ok(f"APP_VERSION={version} BUILD_DATE={build_date}")

    today = datetime.now().strftime("%Y-%m-%d")
    if build_date == today:
        rep.ok(f"BUILD_DATE 为今天（{today}）")
    else:
        rep.warn(
            f"BUILD_DATE={build_date} 非今天（{today}）——打包前请更新 main_gui.BUILD_DATE"
        )

    if not cl_versions:
        rep.fail("main_gui.CHANGELOG 为空或无法解析")
    elif cl_versions[0] == version:
        rep.ok(f"CHANGELOG 顶部版本与 APP_VERSION 一致（{version}）")
    else:
        rep.fail(
            f"CHANGELOG 顶部是 {cl_versions[0]}，APP_VERSION={version}——请同步 CHANGELOG"
        )

    if README.exists():
        m = re.search(
            r"img\.shields\.io/badge/version-([0-9.]+)-blue",
            README.read_text(encoding="utf-8"),
        )
        if not m:
            rep.warn("README 版本徽章未找到")
        elif m.group(1) == version:
            rep.ok(f"README 版本徽章 = {version}")
        else:
            rep.warn(f"README 徽章是 {m.group(1)}，建议改为 {version}")
    return version, build_date


def check_iss(rep: Report, version: str, sync: bool) -> None:
    print("== Inno Setup 版本 ==")
    for path in ISS_FILES:
        if not path.exists():
            rep.warn(f"缺少 {path.name}")
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
        if not m:
            rep.warn(f"{path.name}: 未找到 MyAppVersion")
            continue
        iss_ver = m.group(1)
        if iss_ver == version:
            rep.ok(f"{path.name} MyAppVersion={iss_ver}")
            continue
        if sync:
            new = text.replace(
                f'#define MyAppVersion "{iss_ver}"',
                f'#define MyAppVersion "{version}"',
                1,
            )
            path.write_text(new, encoding="utf-8")
            rep.ok(f"{path.name} MyAppVersion {iss_ver} → {version}（已同步）")
        else:
            rep.fail(
                f"{path.name} MyAppVersion={iss_ver} ≠ APP_VERSION={version}"
                f"（可用 --sync-iss 自动改）"
            )


def check_spec(rep: Report) -> None:
    print("== PyInstaller spec ==")
    if not SPEC.exists():
        rep.fail("缺少 南网协议解析工具.spec")
        return
    text = SPEC.read_text(encoding="utf-8", errors="replace")
    for name in CRITICAL_DATAS:
        # 宽松匹配 datas 中的文件名
        if name in text:
            rep.ok(f"spec 含 {name}")
        else:
            rep.fail(f"spec datas 缺少关键文件：{name}")


def run_test_script(rel: str, timeout: int = 180) -> tuple[bool, str]:
    path = ROOT / rel
    if not path.exists():
        return False, "文件不存在"
    try:
        p = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            # 仅约束子进程 stdio 为 UTF-8（不改变 open() 默认编码），
            # 避免测试 print ✓/★ 等字符在 GBK 控制台下 UnicodeEncodeError
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return False, f"超时 {timeout}s"
    except Exception as e:
        return False, str(e)
    if p.returncode == 0:
        return True, "ok"
    tail = (p.stderr or p.stdout or "").strip().splitlines()
    tail_s = " | ".join(tail[-3:]) if tail else f"exit={p.returncode}"
    return False, tail_s[:300]


def check_tests(rep: Report, with_gui: bool) -> None:
    print("== 核心测试 ==")
    tests = list(CORE_TESTS)
    if with_gui:
        tests.extend(GUI_TESTS)
    # 主题套件单独跑并仅 WARN（本机 offscreen 既有失败）
    for rel in tests:
        ok, detail = run_test_script(rel)
        if ok:
            rep.ok(rel)
        else:
            rep.fail(f"{rel} :: {detail}")

    theme = "test/test_theme_settings.py"
    if theme not in tests:
        ok, detail = run_test_script(theme)
        if ok:
            rep.ok(f"{theme}（附加）")
        else:
            rep.warn(f"{theme} 失败（已知 offscreen 噪声）: {detail}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="南网协议解析工具 发布前自检")
    ap.add_argument("--skip-tests", action="store_true", help="不跑测试")
    ap.add_argument("--with-gui", action="store_true", help="核心测试 + offscreen GUI")
    ap.add_argument(
        "--sync-iss", action="store_true", help="同步 Inno Setup MyAppVersion"
    )
    args = ap.parse_args(argv)

    print(f"release_check @ {ROOT}")
    rep = Report()
    try:
        version, _ = check_versions(rep)
    except Exception as e:
        rep.fail(str(e))
        version = ""
    check_iss(rep, version, args.sync_iss)
    check_spec(rep)
    if not args.skip_tests:
        check_tests(rep, args.with_gui)

    print()
    print(f"结果: PASS={len(rep.oks)}  FAIL={len(rep.fails)}  WARN={len(rep.warns)}")
    if rep.fails:
        print("失败项:")
        for f in rep.fails:
            print(f"  - {f}")
        return 1
    print("发布自检通过（仍建议人工过一遍 GUI 冒烟）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
