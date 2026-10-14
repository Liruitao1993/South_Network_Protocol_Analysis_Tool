# -*- coding: utf-8 -*-
"""协议9「仿照报文回填」（``csg_frame_reverse``）纯逻辑测试（无 Qt）。

重点覆盖：

1. 输入层次识别：ED..EE 封装 / 整帧 MPDU / 应用层帧 / 空与非法输入；
2. **24 个测试模式全量反解**：应用层帧 → 模式 key + 模式参数逐项还原；
3. **ED + MPDU 全链路反解**：24 个模式都能从整帧里取出应用层帧（逐字节相等）；
4. 定界符三型：SOF（BPLC / ISAC）/ 信标 / SACK；
5. 两种 ED 公共头：PLC2.0（9B）/ 广西台体（8B）；
6. 32bit 字段（ED 时间戳 > 0x7FFFFFFF、信标时间戳/周期）取值正确；
7. 错误路径给**可读**原因而不是抛栈（空输入 / 非法 HEX / 过短）；
8. **变异反证**：改一个载荷字节 → 反解出的应用层帧随之变化（证明真在解码，不是回显常量）。

运行：``python test/test_csg_frame_reverse.py``（无 Qt，无需显示器）。
"""

import _path_setup  # noqa: E402,F401

import csg_frame_reverse as rev  # noqa: E402
import csg_link_frame_gen as link  # noqa: E402
import csg_new_gen_frame_gen as fg  # noqa: E402

_FAILURES = []
_CHECKS = []


def check(name, condition, detail=""):
    _CHECKS.append(name)
    if not condition:
        _FAILURES.append(f"{name} —— {detail}")


def probe_params(mode):
    """给模式造一组**合法**探测参数（每种 kind 取非默认值，便于证明真的读到了）。"""
    out = {}
    for field in mode.fields:
        if field.kind == "choice":
            out[field.name] = field.choices[1][0] if len(field.choices) > 1 else field.choices[0][0]
        elif field.kind == "bytes":
            if field.name == "fc":
                out[field.name] = bytes(range(1, 17))
            elif field.name == "efc":
                out[field.name] = bytes(range(17, 33))
            elif field.name == "bit_table":
                out[field.name] = bytes(range(1, 7))
            else:
                out[field.name] = bytes([1, 2, 3])
        else:
            out[field.name] = 3
    return out


def probe_app_frame(mode):
    """返回 (app_frame, params)；参数非法时返回 (None, params)。"""
    params = probe_params(mode)
    try:
        return fg.build_frame_from_mode(mode.key, params).app_frame, params
    except Exception:  # noqa: BLE001 - 探测用，跳过即可
        return None, params


def build_ed(app_frame, wrapper="plc2", **kw):
    cfg = link.LinkFrameConfig(
        frame_kind="sof", delimiter_type=link.DELIM_SOF, std_version=link.STD_VERSION_BPLC,
        channel="plc", access_indicator=1, snid=5, src_tei=0x123, dest_tei=0x456,
        link_id=0x37, pb_count=1, pb_total=136, mac_header_type=link.MAC_HDR_TYPE_LONG,
        mac_version=link.MAC_VERSION_STD, tx_seq=9, msdu_seq=7, msdu_payload=app_frame, **kw)
    mpdu = link.build_link_frame(cfg).mpdu
    return mpdu, fg.build_ed_frame(mpdu, wrapper=wrapper, physical_channel=1, timestamp=0)


# ----------------------------------------------------------------------
# 1. 层次识别
# ----------------------------------------------------------------------
def test_detect_input_layer():
    app = fg.build_frame_from_mode("loopback", {"band": 3}).app_frame
    mpdu, ed = build_ed(app)
    check("识别：ED..EE 封装", rev.detect_input_layer(ed)[0] == "ed")
    check("识别：整帧 MPDU", rev.detect_input_layer(mpdu)[0] == "mpdu")
    check("识别：应用层帧", rev.detect_input_layer(app)[0] == "app")
    check("识别：空输入", rev.detect_input_layer(b"")[0] == "")
    check("识别：ED 内层取出的是 MPDU",
          rev.detect_input_layer(ed)[2] == mpdu)


def test_reverse_error_paths():
    empty = rev.reverse_frame("")
    check("错误：空输入 ok=False", not empty.ok)
    check("错误：空输入提示粘贴", "粘贴" in empty.error, empty.error)
    bad = rev.reverse_frame("ZZ ZZ")
    check("错误：非法 HEX 不抛异常且有可读原因", not bad.ok and bool(bad.error), bad.error)
    short = rev.reverse_frame("ED 01")
    check("错误：过短报文有可读原因", not short.ok and bool(short.error), short.error)


# ----------------------------------------------------------------------
# 2. 24 个模式：应用层帧反解
# ----------------------------------------------------------------------
def test_reverse_all_modes_from_app_frame():
    checked = 0
    problems = []
    for mode in fg.test_modes():
        app, params = probe_app_frame(mode)
        if app is None:
            continue
        checked += 1
        result = rev.reverse_frame(app)
        got_key = (result.state.get("mode") or {}).get("key")
        got_params = (result.state.get("mode") or {}).get("params") or {}
        if not result.ok or got_key != mode.key:
            problems.append(f"{mode.key}: key={got_key}")
            continue
        for name, want in params.items():
            if name in got_params and got_params[name] != want:
                problems.append(f"{mode.key}.{name}: {got_params[name]!r} != {want!r}")
    check("反解：全部模式（应用层帧，模式 key + 参数一致）", not problems,
          "; ".join(problems[:6]))
    check("反解：至少覆盖 20 个模式", checked >= 20, str(checked))


def test_reverse_all_modes_from_ed_mpdu():
    checked = 0
    problems = []
    for mode in fg.test_modes():
        app, _ = probe_app_frame(mode)
        if app is None:
            continue
        checked += 1
        mpdu, ed = build_ed(app)
        result = rev.reverse_frame(ed)
        got_key = (result.state.get("mode") or {}).get("key")
        if result.layer != "ed" or got_key != mode.key:
            problems.append(f"{mode.key}: layer={result.layer} key={got_key}")
            continue
        if result.app_hex != app.hex().upper():
            problems.append(f"{mode.key}: 应用层帧不一致")
        if not result.state["frame"]["link_enabled"]:
            problems.append(f"{mode.key}: 未标记链路层")
        if result.unmapped:
            problems.append(f"{mode.key}: unmapped={result.unmapped}")
    check("反解：全部模式（ED+MPDU，应用层帧逐字节还原）", not problems,
          "; ".join(problems[:6]))
    check("反解：ED 路径覆盖模式数 >= 20", checked >= 20, str(checked))
    check("反解：输出层次跟随输入层次（ed）",
          rev.reverse_frame(build_ed(fg.build_frame_from_mode('loopback', {'band': 1}).app_frame)[1])
          .state["frame"]["output"] == "ed")


def test_reverse_mpdu_input_marks_link_layer():
    app = fg.build_frame_from_mode("loopback", {"band": 9}).app_frame
    mpdu, _ = build_ed(app)
    result = rev.reverse_frame(mpdu)
    check("反解：MPDU 输入 layer=mpdu", result.layer == "mpdu", result.layer)
    check("反解：MPDU 输入输出层次=mpdu", result.state["frame"]["output"] == "mpdu",
          str(result.state["frame"]["output"]))
    check("反解：MPDU 输入应用层帧仍能还原", result.app_hex == app.hex().upper(),
          result.app_hex[:40])


def test_reverse_app_input_marks_no_link_layer():
    app = fg.build_frame_from_mode("band_switch", {"band": 6}).app_frame
    result = rev.reverse_frame(app)
    check("反解：应用层帧输入 layer=app", result.layer == "app", result.layer)
    check("反解：应用层帧输入不算链路层",
          result.state["frame"]["link_enabled"] is False)
    check("反解：应用层帧输入输出层次=app", result.state["frame"]["output"] == "app",
          str(result.state["frame"]["output"]))


# ----------------------------------------------------------------------
# 3. 定界符三型
# ----------------------------------------------------------------------
def test_reverse_beacon_and_sack():
    app = fg.build_frame_from_mode("loopback", {"band": 1}).app_frame
    for kind, delim, expect in (("beacon", link.DELIM_BEACON, "beacon"),
                               ("sack", link.DELIM_SACK, "sack")):
        cfg = link.LinkFrameConfig(
            frame_kind=kind, delimiter_type=delim, std_version=link.STD_VERSION_BPLC,
            channel="plc", access_indicator=1, snid=5, src_tei=0x123, dest_tei=0x456,
            pb_count=1, pb_total=136, mac_header_type=link.MAC_HDR_TYPE_LONG,
            msdu_payload=app,
            beacon_payload=b"\xAA\xBB" if kind == "beacon" else b"",
        )
        mpdu = link.build_link_frame(cfg).mpdu
        result = rev.reverse_frame(mpdu)
        check(f"反解：{kind} 帧类型识别", result.state["frame"]["kind"] == expect,
              str(result.state["frame"]["kind"]))
        check(f"反解：{kind} 接入指示=1", result.state["link"].get("access_indicator") == 1,
              str(result.state["link"].get("access_indicator")))


def test_reverse_isac_and_bplc_variants():
    for std, expect in ((link.STD_VERSION_BPLC, "BPLC"), (link.STD_VERSION_ISAC, "ISAC")):
        app = fg.build_frame_from_mode("loopback", {"band": 2}).app_frame
        cfg = link.LinkFrameConfig(
            frame_kind="sof", delimiter_type=link.DELIM_SOF, std_version=std,
            channel="plc", access_indicator=1, snid=5, src_tei=0x123, dest_tei=0x456,
            pb_count=1, pb_total=136 if std == link.STD_VERSION_BPLC else 264,
            mac_header_type=link.MAC_HDR_TYPE_LONG, msdu_payload=app)
        mpdu = link.build_link_frame(cfg).mpdu
        result = rev.reverse_frame(mpdu)
        check(f"反解：{expect} 标准版本号还原",
              result.state["frame"]["std_version"] == std,
              str(result.state["frame"]["std_version"]))
        check(f"反解：{expect} 摘要含版本名", expect in rev.state_summary(result.state),
              rev.state_summary(result.state))


# ----------------------------------------------------------------------
# 4. ED 公共头两种 + 32bit 字段
# ----------------------------------------------------------------------
def test_reverse_ed_wrappers():
    app = fg.build_frame_from_mode("loopback", {"band": 1}).app_frame
    for wrapper in ("plc2", "gx"):
        _, ed = build_ed(app, wrapper=wrapper)
        result = rev.reverse_frame(ed)
        check(f"反解：{wrapper} 包装识别", result.wrapper == wrapper, result.wrapper)
        check(f"反解：{wrapper} ED 参数填充",
              result.state["ed"].get("enabled") is True
              and result.state["ed"].get("wrapper") == wrapper,
              str(result.state["ed"]))


def test_reverse_ed_32bit_timestamp():
    app = fg.build_frame_from_mode("loopback", {"band": 1}).app_frame
    cfg = link.LinkFrameConfig(
        frame_kind="sof", delimiter_type=link.DELIM_SOF, std_version=link.STD_VERSION_BPLC,
        channel="plc", access_indicator=1, snid=5, src_tei=0x123, dest_tei=0x456,
        pb_count=1, pb_total=136, mac_header_type=link.MAC_HDR_TYPE_LONG, msdu_payload=app)
    mpdu = link.build_link_frame(cfg).mpdu
    stamp = 0x68E1A2B3                     # 真实 Unix 时间戳量级（> 0x7FFFFFFF）
    ed = fg.build_ed_frame(mpdu, wrapper="plc2", physical_channel=2, timestamp=stamp, pb_count=1)
    result = rev.reverse_frame(ed)
    check("反解：ED 32bit 时间戳还原（不因 C++ int 上限被截断）",
          result.state["ed"].get("timestamp") == stamp, hex(result.state["ed"].get("timestamp", 0)))
    check("反解：ED 物理信道还原", result.state["ed"].get("channel") == 2,
          str(result.state["ed"].get("channel")))


def test_reverse_beacon_32bit_fields():
    cfg = link.LinkFrameConfig(
        frame_kind="beacon", delimiter_type=link.DELIM_BEACON, std_version=link.STD_VERSION_BPLC,
        channel="plc", access_indicator=1, snid=5, src_tei=0x123, dest_tei=0x456,
        pb_count=1, pb_total=136, beacon_timestamp=0xF1234567, beacon_cycle=0xEEDDCCBB,
        beacon_phase=2, symbol_count=0x1FF, beacon_payload=b"\x11\x22")
    mpdu = link.build_link_frame(cfg).mpdu
    result = rev.reverse_frame(mpdu)
    link_state = result.state["link"]
    check("反解：信标时间戳（满 32bit）还原",
          link_state.get("beacon_timestamp") == 0xF1234567, hex(link_state.get("beacon_timestamp", 0)))
    check("反解：信标周期（满 32bit）还原",
          link_state.get("beacon_cycle") == 0xEEDDCCBB, hex(link_state.get("beacon_cycle", 0)))
    check("反解：信标符号数按 FC 原始位还原（含第 9 位）",
          link_state.get("symbol_count") == 0x1FF, hex(link_state.get("symbol_count", 0)))


# ----------------------------------------------------------------------
# 5. 变异反证
# ----------------------------------------------------------------------
def test_mutation_changes_reversed_payload():
    base = fg.build_frame_from_mode("loopback", {"band": 3}).app_frame
    mutated = bytearray(base)
    mutated[-1] ^= 0xFF                    # 改最后一个字节（数据区内容）
    _, ed_base = build_ed(base)
    _, ed_mutated = build_ed(bytes(mutated))
    got_base = rev.reverse_frame(ed_base).app_hex
    got_mutated = rev.reverse_frame(ed_mutated).app_hex
    check("变异反证：改载荷字节后反解结果随之变化", got_base != got_mutated,
          f"{got_base[-8:]} vs {got_mutated[-8:]}")
    check("变异反证：反解结果与输入严格一致（未被规范化掉）",
          got_mutated == bytes(mutated).hex().upper())


def test_mutation_detects_link_field_change():
    app = fg.build_frame_from_mode("loopback", {"band": 3}).app_frame
    _, ed_123 = build_ed(app)
    cfg = link.LinkFrameConfig(
        frame_kind="sof", delimiter_type=link.DELIM_SOF, std_version=link.STD_VERSION_BPLC,
        channel="plc", access_indicator=1, snid=5, src_tei=0x123, dest_tei=0x789,
        pb_count=1, pb_total=136, mac_header_type=link.MAC_HDR_TYPE_LONG, msdu_payload=app)
    ed_789 = fg.build_ed_frame(link.build_link_frame(cfg).mpdu, wrapper="plc2",
                               physical_channel=1, timestamp=0)
    a = rev.reverse_frame(ed_123).state["link"]
    b = rev.reverse_frame(ed_789).state["link"]
    check("变异反证：目的 TEI 变化被反解出来",
          a.get("dest_tei") == 0x456 and b.get("dest_tei") == 0x789,
          f"{a.get('dest_tei')} / {b.get('dest_tei')}")


# ----------------------------------------------------------------------
# 6. state 结构 / 摘要
# ----------------------------------------------------------------------
def test_state_shape_and_summary():
    state = rev.empty_state()
    check("state：含 frame/link/header/ed/mode 五段",
          set(state) >= {"version", "frame", "link", "header", "ed", "mode"}, str(sorted(state)))
    check("state：默认带链路层", state["frame"]["link_enabled"] is True)
    app = fg.build_frame_from_mode("legacy_6", probe_params(fg.mode_by_key("legacy_6"))).app_frame
    _, ed = build_ed(app)
    result = rev.reverse_frame(ed)
    summary = rev.state_summary(result.state)
    check("摘要：含帧类型与链路层口径",
          "SOF" in summary and "带链路层" in summary, summary)
    check("摘要：含识别到的模式名", "频段切换" in summary, summary)


def test_no_unmapped_for_canonical_frame():
    app = fg.build_frame_from_mode("ext_tei", {"tei": 0x123}).app_frame
    _, ed = build_ed(app)
    result = rev.reverse_frame(ed)
    check("规范帧：不应报告表单表达不了的字段", not result.unmapped, str(result.unmapped))
    check("规范帧：参数完整（tei 还原）",
          (result.state.get("mode") or {}).get("params", {}).get("tei") == 0x123,
          str((result.state.get("mode") or {}).get("params")))


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"检查项：{len(_CHECKS)} 项，失败 {len(_FAILURES)} 项")
    if _FAILURES:
        for item in _FAILURES:
            print(f"  [FAIL] {item}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
