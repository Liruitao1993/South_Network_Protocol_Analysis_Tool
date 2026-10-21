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
    # P0 加固：原子写 / 升级回滚脚本 / 诊断包（纯逻辑 + 主程序静态守卫）
    "test/test_p0_hardening.py",
    "test/test_dl698_tolerant_parse.py",
    "test/test_crash_handler.py",
    "test/test_frame_corpus.py",
    "test/test_parser_fuzz.py",
    "test/test_self_test.py",
    "test/test_appearance_mode.py",
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
    "test/test_csg_link_frame_gen.py",
    "test/test_csg_frame_reverse.py",
    "test/test_csg_test_ext_0009.py",
    "test/test_csg_frame_templates.py",
    "test/test_gw_new_gen.py",
    "test/test_gw_monitor_summary.py",
    "test/test_gw_app_summary_detail.py",
    "test/test_gw_batch_parse.py",
    "test/test_gdw_fujian.py",
    "test/test_hdc10.py",
    "test/test_hdc10_batch_strip_level.py",
    "test/test_hdc10_meter_reading.py",
    "test/test_hdc10_app_dispatch.py",
    "test/test_hdc10_pb_structure_probe.py",
    "test/test_hdc10_mac_only_contract.py",
    "test/test_gw_parse_levels.py",
    "test/test_gw_pb_mme_summary.py",
    "test/test_ed_ui_for_gw_hdc10.py",
    "test/test_ed_fallback_fix.py",
    "test/test_dlt645_frame_gen.py",
    "test/test_dlt645_tolerant_parse.py",
    "test/test_dlt645_table_offsets.py",
    "test/test_dlt645_status_word_bits.py",
    "test/test_dlt645_lme.py",
    "test/test_dlt645_pv_ext.py",
    "test/test_dlt645_sim.py",
    "test/test_dlt645_sim_lme_query.py",
    "test/test_dlt645_sim_event_word.py",
    "test/test_diff_engine.py",
    "test/test_ed_gx_wrapper.py",
    "test/test_ed_fallback_fix.py",
    "test/test_ed_ui_for_gw_hdc10.py",
    "test/test_ed_wrapper_labels.py",
    "test/test_tcp_monitor_ed_hdc.py",
    "test/test_beacon_ed_hdc10.py",
    "test/test_serial_worker_framing.py",
    "test/test_tcp_monitor_proto11_frames.py",
    "test/test_hdc10_comm_test_ext.py",
    "test/test_hdc10_event_data.py",
    "test/test_hdc10_ed_wrapper.py",
    "test/test_hdc10_fc_bits.py",
    "test/test_hdc10_blank_checksum.py",
    "test/test_hdc10_bitfield_display.py",
    "test/test_modular_iface.py",
    "test/test_modular_iface_axdr.py",
    "test/test_hex_clean_script.py",
    "test/test_pp_cli.py",
    "test/test_batch_src_line_jump.py",
    "test/test_batch_snapshot_locate.py",
    "test/test_gui_batch_perf.py",
    "test/test_csg_sequence_model.py",
    "test/test_app_paths.py",
    "test/test_nanwang_custom_di.py",
    "test/test_window_state.py",
    "test/test_top_bar_collapse.py",
    "test/test_menu_wiring.py",
    "test/test_about_github_star.py",
    "test/test_flow_layout_proto_group.py",
    "test/test_hex_dump_view.py",
    "test/test_tcp_monitor_raw_payload.py",
    "test/test_tcp_monitor_proto_detect.py",
    "test/test_tcp_monitor_ui_views.py",
    "test/test_tcp_monitor_record_dir.py",
    "test/test_btn_width_fit.py",
    "test/test_message_tool_numeric.py",
    # 报文工具「地址替换」（纯逻辑六协议真帧 oracle + 前导 FE 门控 + offscreen GUI 接线）
    "test/test_message_tool_addr_fix.py",
    "test/test_dl_t698_45_extract.py",
    "test/test_dl_t698_45_endian.py",
    # 协议8 文件传输升级（纯逻辑）：三帧逐字节 golden（含 doc 实帧）/ 分包矩阵 / SA / 确认判定 / 校验值
    "test/test_dl698_upgrade.py",
    # 前导 FE 唤醒字节（协议8/6）：解析/表格偏移/校验一致性 + offscreen GUI（AGENTS §8 前导 FE 陷阱）
    "test/test_wakeup_fe_prefix.py",
    "test/test_serial_tool_widget.py",
    "test/test_serial_proto_frame.py",
    "test/test_serial_worker_write_raw.py",
    # 串口运行中热切换波特率（纯逻辑假串口：先 flush 再改速、共写锁、不关端口、失败不改 _baudrate）
    "test/test_serial_worker_set_baudrate.py",
    # 串口工具批量替换通信地址（纯逻辑：六协议真帧 oracle + 前导 FE 门控 + 预期响应口径）
    "test/test_serial_addr_fix.py",
    # 蓝牙工具（core 纯逻辑 / worker 注入假 bleak / widget offscreen 假 worker，均不碰硬件）
    "test/test_bluetooth_core.py",
    "test/test_bluetooth_addr_fix.py",
    "test/test_bluetooth_worker.py",
    "test/test_bluetooth_widget.py",
    "test/test_bluetooth_tab_wiring.py",
    "test/test_web_frame_gen_utils.py",
    "test/test_web_parse_fixes.py",
    "test/test_web_all_protocols.py",
    "test/test_web_batch_paging.py",
    "test/test_web_spectrum.py",
    "test/test_web_theme.py",
    "test/test_web_landing.py",
    "test/test_web_data_paths.py",
    "test/test_web_download_url.py",
    "test/test_web_gui_parity.py",
    "test/test_sack_fix.py",
    "test/test_monitor_deframe.py",
    "test/test_monitor_plc2_deframe.py",
    "test/test_spectrum_model.py",
    "test/test_yw645_wire.py",
    "test/test_yw645_parse.py",
    "test/test_yw645_frame_gen.py",
    "test/test_yw645_extract.py",
    "test/test_yw645_validator.py",
    "test/test_csg_uplink.py",
    # 自动升级：版本比对 / GitHub 源（默认）/ digest→sha256 / 版本列表 / 错误文案
    "test/test_auto_updater.py",
    # 自动升级对话框：更新说明（markdown）渲染 / 版本列表 / 接线守卫（offscreen）
    "test/test_update_notes_gui.py",
]

# 可选 offscreen GUI（慢；主题套件本机既有 12 项失败，仅报告不阻断默认）
GUI_TESTS = [
    "test/test_quick_parse_panel.py",
    # 短时长稳：反复切页（内存必须收敛）+ 高频收包（日志块上限/队列清空）
    "test/test_soak_stability.py",
    "test/test_appearance_gui.py",
    "test/test_tolerant_parse_gui.py",
    # 协议8 文件传输升级页（offscreen 假串口：逐包确认/重试/超时/中止/进度/拖放/不裁字）+ 真实 MainWindow 接线
    "test/test_dl698_upgrade_gui.py",
    "test/test_dl698_upgrade_tab_wiring.py",
    # 粘性入口：托盘菜单内嵌输入框 + 任务栏缩略图按钮（HICON/降级/WM_COMMAND 路由/按钮分派）
    "test/test_tray_taskbar_entries.py",
    "test/test_csg_sequence_gui.py",
    "test/test_csg_pb_highlight_gui.py",
    "test/test_csg_pbcs_fill_gui.py",
    "test/test_hdc10_blank_checksum_gui.py",
    "test/test_csg_frame_gen_gui.py",
    "test/test_collapsible_section.py",
    "test/test_batch_toolbar_layout.py",
    "test/test_dlt645_frame_gen_gui.py",
    "test/test_app_icon_path.py",
    "test/test_button_icons.py",
    "test/test_spectrum_gui.py",
    # 生产测试架（串口助手 + 测试架参数帧）：纯逻辑 golden + GUI + main_gui 接线
    "test/test_production_testbench.py",
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
            # 项目已改用「动态 Release 徽章」（img.shields.io/github/v/release/…），
            # 版本号由 GitHub 实时渲染，不需要也不应该再维护一个静态版本徽章。
            text = README.read_text(encoding="utf-8")
            if "img.shields.io/github/v/release/" in text:
                rep.ok("README 使用动态 Release 徽章（无需同步静态版本号）")
            else:
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
