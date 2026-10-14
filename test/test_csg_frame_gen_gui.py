# -*- coding: utf-8 -*-
"""协议9（南网新一代载波）链路层组帧 GUI 端到端测试（offscreen）。

走**真实 GUI 路径**验证本次集成（main_gui → FrameGenWidget → CsgTestFrameGenWidget
→ csg_link_frame_gen → CSGNewGenParser 回读），而不是直接调组帧器：

1. 协议注册：协议9 ``frame_gen_mode="csg"``，``preset_mode=None``；协议0/6/7/8/12 不受影响；
2. 主窗口页签可见性：协议9 下「协议组帧」页可见、「预设命令」页**不可见**
   （预设页可见性已从 frame_gen_mode 改为 preset_mode —— 否则协议9 会露出空预设页，
   且「添加到预设」会经 preset_buttons 的兜底分支误写 GW_command.json）；
3. 组帧页结构：左栏切到协议9 组帧页（栈索引 1），DI/AFN/字段模式/EB 区全部隐藏，
   五个折叠区 fc/pb/mac/msdu/ed 齐备，默认帧类型 = SOF，默认勾选「组装链路层」；
4. SOF 帧闭环：组帧 → 解析器 ``parse_level="auto"`` 回读，FCCS / PBCS / CRC-32 三处
   「校验通过」、接入指示=1、TEI 语义不变量（原始源TEI/目的TEI 与 FC 源TEI/目的TEI 一致）；
5. 信标帧：回归「切到信标帧时 32bit 字段 QSpinBox 溢出（OverflowError）导致 FC 区重建中断、
   输出仍是上一帧类型」以及「载波映射表索引 4bit 超界（ISML 反查 16 未按信标 BPLC 语义）」；
6. SACK 帧：回归「``FrameBuildResult.hex()`` 在 mac_header/msdu 为 None 时 TypeError
   让整块预览空掉」；
7. 24 个测试模式全部能组出**带链路层**的帧；
8. 输出层次 ed/app/bdu/mpdu 四档取值正确（mpdu 以 FC 起头、ED 封装以 ED…EE 收尾）；
9. 折叠区状态收集/恢复（link_state / apply_link_state）与「展开全部 / 收起全部」；
10. 其他协议（南网/645/国网/698.45/模组化）切回去后左栏回到第 0 页、「添加到预设」恢复；
11. 按钮不裁字：``show()`` 之后 ``width() >= sizeHint().width()`` 且未写死上限（AGENTS 陷阱 63）；
12. **⓪ 仿照报文 / 模板**：粘贴一帧 → 反解回填 → 逐字节重建校验（含 32bit ED 时间戳回填）；
    改一个字段后重新生成 → 校验和自动重算；表单表达不了的字段 → 「手工 HEX 保真」兜底；
13. 「响应帧解析」开关：协议9 默认收起、其它协议保持现状、勾回可随时显示。

运行：``python test/test_csg_frame_gen_gui.py``（offscreen，无需显示器）。
"""

import _path_setup  # noqa: E402,F401

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import csg_frame_reverse as rev  # noqa: E402
import csg_frame_templates as tpl  # noqa: E402
import csg_link_frame_gen as link  # noqa: E402
import csg_new_gen_frame_gen as fg  # noqa: E402
import protocol_registry as registry  # noqa: E402
from csg_new_gen_frame_gen import FrameBuildError  # noqa: E402
from csg_test_frame_gen_widget import CsgTestFrameGenWidget  # noqa: E402
from csg_new_gen_parser import CSGNewGenParser  # noqa: E402

_FAILURES = []
_CHECKS = []


def check(name, condition, detail=""):
    _CHECKS.append(name)
    if not condition:
        _FAILURES.append(f"{name} —— {detail}")


def field_of(table, label):
    """取解析表某字段的「解析值」列。"""
    for row in table:
        if row[0] == label:
            return row[2]
    return None


def raw_of(table, label):
    for row in table:
        if row[0] == label:
            return row[1]
    return None


def desc_of(table, label):
    for row in table:
        if row[0] == label:
            return row[3]
    return ""


def _layer_index(combo, value):
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            return i
    return -1


def _select(combo, value):
    idx = _layer_index(combo, value)
    if idx < 0:
        raise AssertionError(f"下拉里没有 {value!r}")
    combo.setCurrentIndex(idx)


class _Ctx:
    """一次 MainWindow 的惰性构造，供所有用例复用。"""

    win = None
    app = None


def _app():
    from PySide6.QtWidgets import QApplication

    _Ctx.app = QApplication.instance() or QApplication([])
    return _Ctx.app


def _main_window():
    if _Ctx.win is None:
        import main_gui

        _Ctx.win = main_gui.MainWindow()
        _app().processEvents()
    return _Ctx.win


def _frame_gen_tab():
    """返回主窗口的组帧页；顺带保证它已被创建。

    组帧页是**懒创建**的（``_ensure_lazy_tab`` 在用户真正切到该页签时才建），
    所以要先 ``_on_protocol_changed(9)`` 把 ``_pending_frame_gen_mode`` 设成 "csg"，
    再显式 ``_ensure_frame_gen_tab()``。
    """
    win = _main_window()
    win._on_protocol_changed(9)
    _app().processEvents()
    return win._ensure_frame_gen_tab()


def _gen():
    """进入协议9 组帧页并返回 CsgTestFrameGenWidget。"""
    return _frame_gen_tab().csg_gen


def _fresh_gen():
    """独立（不依赖 MainWindow）的组帧页，用于纯控件层用例。

    必须先把 QApplication 建出来：Qt 里「没有 QApplication 就构造 QWidget」是
    **致命错误**，进程直接以 0xC0000409 中止且 stdout 一个字都不输出
    （排查时极像环境问题，实则用例自身漏了 app）。
    """
    _app()
    return CsgTestFrameGenWidget(link_layer_default=True)


# ----------------------------------------------------------------------
# 1. 协议注册
# ----------------------------------------------------------------------
def test_registry_protocol_9_registers_csg_frame_gen():
    spec = registry.get_protocol(9)
    check("协议9 frame_gen_mode = csg", spec.frame_gen_mode == "csg", str(spec.frame_gen_mode))
    check("协议9 preset_mode 仍为 None（无预设库）",
          spec.preset_mode is None, str(spec.preset_mode))
    check("frame_gen_mode_for(9) = csg", registry.frame_gen_mode_for(9) == "csg",
          str(registry.frame_gen_mode_for(9)))
    check("9 出现在 protocols_with_frame_gen()",
          9 in registry.protocols_with_frame_gen(),
          str(registry.protocols_with_frame_gen()))


def test_registry_other_protocols_unchanged():
    for idx, mode in ((0, "south"), (6, "dlt645"), (7, "gdw"),
                      (8, "dlt698"), (12, "modular")):
        check(f"协议{idx} frame_gen_mode 仍为 {mode}",
              registry.frame_gen_mode_for(idx) == mode,
              str(registry.frame_gen_mode_for(idx)))
        check(f"协议{idx} preset_mode 非空", registry.preset_mode_for(idx) is not None,
              str(registry.preset_mode_for(idx)))
    # 协议9 无预设库，不得因新增组帧页而被塞进预设页
    check("协议9 无 preset_mode", registry.preset_mode_for(9) is None,
          str(registry.preset_mode_for(9)))


# ----------------------------------------------------------------------
# 2. 主窗口页签可见性
# ----------------------------------------------------------------------
def test_tabs_visible_for_protocol_9():
    win = _main_window()
    win._on_protocol_changed(9)
    _app().processEvents()
    tab = _frame_gen_tab()
    check("协议9 组帧页可见",
          win.tab_widget.isTabVisible(win._frame_gen_tab_index))
    check("协议9 预设命令页不可见（preset_mode=None）",
          not win.tab_widget.isTabVisible(win._preset_tab_index))
    check("协议9 frame_gen_tab.protocol_mode = csg",
          tab.protocol_mode == "csg", tab.protocol_mode)


def test_tabs_visible_for_protocol_0():
    win = _main_window()
    win._on_protocol_changed(0)
    _app().processEvents()
    check("协议0 组帧页可见",
          win.tab_widget.isTabVisible(win._frame_gen_tab_index))
    check("协议0 预设命令页可见",
          win.tab_widget.isTabVisible(win._preset_tab_index))
    win._on_protocol_changed(9)
    _app().processEvents()


# ----------------------------------------------------------------------
# 3. 组帧页结构
# ----------------------------------------------------------------------
def test_csg_page_structure():
    gen = _gen()
    tab = _main_window().frame_gen_tab
    check("左栏切到组帧页（栈索引 1）", tab.left_stack.currentIndex() == 1,
          str(tab.left_stack.currentIndex()))
    check("DI/AFN 命令选择组隐藏", not tab.cmd_select_group.isVisible())
    check("字段模式组隐藏（mode_group 不在栈内，必须显式隐藏）",
          not tab.mode_group.isVisible())
    check("EB 生成器组隐藏", not tab.eb_gen_group.isVisible())
    check("「添加到预设」隐藏（协议9 无预设库）",
          not tab.add_preset_btn.isVisible())
    check("六个折叠区齐备（⓪ 仿照报文/模板 + ①~⑤ 五层）",
          set(gen.sections) == {"mirror", "fc", "pb", "mac", "msdu", "ed"},
          str(sorted(gen.sections)))
    check("默认帧类型 = SOF", gen.frame_kind() == "sof", gen.frame_kind())
    check("默认勾选「组装链路层」", gen.link_enable_check.isChecked())
    check("测试模式 >= 24 个", gen.mode_combo.count() >= 24, str(gen.mode_combo.count()))


# ----------------------------------------------------------------------
# 4. SOF 帧闭环
# ----------------------------------------------------------------------
def test_sof_frame_roundtrip_via_gui():
    win = _main_window()
    win._on_protocol_changed(9)
    _app().processEvents()
    tab = win.frame_gen_tab
    gen = tab.csg_gen
    _select(gen.fk_combo, "sof")
    _select(gen.layer_combo, "mpdu")

    tab._do_realtime_update()
    _app().processEvents()
    hex_text = tab.result_hex.toPlainText().strip()
    check("SOF：实时预览写出 hex", bool(hex_text))
    check("SOF：一键预览表已填充", tab.preview_table.rowCount() > 0,
          str(tab.preview_table.rowCount()))

    res = gen.build()
    check("SOF：组帧结果带链路层", res is not None and res.has_link_layer())
    out = gen.output_bytes(res)
    check("SOF：MPDU 非空且以 FC 起头", bool(out) and out[0] == 0x19,
          out.hex(" ").upper() if out else "None")

    table = CSGNewGenParser().parse_to_table(out, parse_level="auto")
    check("SOF：定界符类型回读为 SOF", field_of(table, "定界符类型") == "1",
          str(field_of(table, "定界符类型")))
    check("SOF：接入指示回读为 1（解析器据此判定 MPDU）",
          field_of(table, "接入指示") == "1", str(field_of(table, "接入指示")))
    check("SOF：FC 的 FCCS 校验通过", "校验通过" in desc_of(table, "FC校验序列(FCS)"),
          desc_of(table, "FC校验序列(FCS)"))
    check("SOF：PBCS 校验通过", "校验通过" in desc_of(table, "物理块检查序列"),
          desc_of(table, "物理块检查序列"))
    check("SOF：CRC-32 完整性校验通过",
          "校验通过" in desc_of(table, "完整性校验(CRC-32)"),
          desc_of(table, "完整性校验(CRC-32)"))
    # 语义不变量（AGENTS 陷阱 54 的判据）：MAC 头原始 TEI 必须等于 FC 里的源/目的 TEI
    check("SOF：原始源TEI = FC 源TEI(0x123)",
          raw_of(table, "原始源TEI") == raw_of(table, "源TEI") == "0x123",
          f"{raw_of(table, '原始源TEI')} vs {raw_of(table, '源TEI')}")
    check("SOF：原始目的TEI = FC 目的TEI(0x456)",
          raw_of(table, "原始目的TEI") == raw_of(table, "目的TEI") == "0x456",
          f"{raw_of(table, '原始目的TEI')} vs {raw_of(table, '目的TEI')}")
    msdu_len = field_of(table, "MSDU长度")
    check("SOF：MSDU 长度与实际 MSDU 一致",
          msdu_len == f"{len(res.msdu)}字节",
          f"{msdu_len} vs {len(res.msdu)}字节")


# ----------------------------------------------------------------------
# 5. 信标帧（回归 QSpinBox 32bit 溢出 + 载波映射表索引 4bit 超界）
# ----------------------------------------------------------------------
def test_beacon_frame_switch_rebuilds_fc_fields():
    gen = _fresh_gen()
    _select(gen.fk_combo, "beacon")
    _app().processEvents()
    check("信标：FC 区重建后仍有字段（32bit 字段不再抛 OverflowError）",
          gen.fc_form.rowCount() > 0, str(gen.fc_form.rowCount()))
    for name in ("beacon_timestamp", "beacon_cycle", "src_tei"):
        check(f"信标：{name} 控件已建立", name in gen._fc_field_widgets)


def test_beacon_frame_builds_and_parses():
    gen = _fresh_gen()
    _select(gen.fk_combo, "beacon")
    _select(gen.layer_combo, "mpdu")
    res = gen.build()          # 回归：曾抛「载波映射表索引 超出 4bit 范围：16」
    check("信标：组帧成功并带链路层", res is not None and res.has_link_layer())
    out = gen.output_bytes(res)
    check("信标：MPDU 以 0x18 起头", bool(out) and out[0] == 0x18,
          out.hex(" ").upper() if out else "None")
    table = CSGNewGenParser().parse_to_table(out, parse_level="auto")
    check("信标：定界符类型回读为信标", field_of(table, "定界符类型") == "0",
          str(field_of(table, "定界符类型")))
    check("信标：FCCS 校验通过", "校验通过" in desc_of(table, "FC校验序列(FCS)"),
          desc_of(table, "FC校验序列(FCS)"))
    check("信标：回读的载波映射表索引 <= 15（不得出现 16）",
          (lambda v: v is not None and int(str(v), 16) <= 15 if str(v).startswith("0x")
           else True)(field_of(table, "载波映射表索引")),
          str(field_of(table, "载波映射表索引")))


def test_beacon_preview_not_empty_via_gui():
    tab = _frame_gen_tab()
    gen = tab.csg_gen
    _select(gen.fk_combo, "beacon")
    _select(gen.layer_combo, "mpdu")
    tab._do_realtime_update()
    _app().processEvents()
    check("信标：GUI 预览表非空（回归：异常导致整块预览空掉）",
          tab.preview_table.rowCount() > 0, str(tab.preview_table.rowCount()))
    check("信标：GUI 生成结果以 18 起头",
          tab.result_hex.toPlainText().strip().startswith("18"),
          tab.result_hex.toPlainText().strip()[:20])
    # 复位：本用例用的是 MainWindow 里那个**共享**组帧页，别把状态漏给后面的用例
    _select(gen.fk_combo, "sof")
    tab._do_realtime_update()
    _app().processEvents()


# ----------------------------------------------------------------------
# 6. SACK 帧（回归 FrameBuildResult.hex() 的 mac_frame NoneType）
# ----------------------------------------------------------------------
def test_sack_frame_builds_and_parses():
    gen = _fresh_gen()
    _select(gen.fk_combo, "sack")
    _select(gen.layer_combo, "mpdu")
    res = gen.build()
    check("SACK：组帧成功并带链路层", res is not None and res.has_link_layer())
    out = gen.output_bytes(res)
    check("SACK：仅 16 字节 FC", bool(out) and len(out) == 16 and out[0] == 0x1A,
          out.hex(" ").upper() if out else "None")
    # 回归：mac_header / msdu 均为 None 时 hex() 曾 TypeError
    try:
        app_hex = res.hex("app")
        crashed = ""
    except Exception as exc:  # noqa: BLE001
        app_hex, crashed = "", repr(exc)
    check("SACK：FrameBuildResult.hex() 不再抛 TypeError", not crashed, crashed)
    check("SACK：hex('app') 非空", bool(app_hex), app_hex)
    try:
        mac_hex = res.hex("mac_frame")
        mac_ok, mac_detail = False, f"未抛异常（返回 {mac_hex!r}）"
    except FrameBuildError as exc:
        mac_ok, mac_detail = True, str(exc)
    except TypeError as exc:  # 回归目标：不能再是 TypeError
        mac_ok, mac_detail = False, f"TypeError: {exc}"
    check("SACK：无 MAC 帧时 hex('mac_frame') 抛可读 FrameBuildError 而非 TypeError",
          mac_ok, mac_detail)
    table = CSGNewGenParser().parse_to_table(out, parse_level="auto")
    check("SACK：定界符类型回读为选择确认帧",
          field_of(table, "定界符类型") == "2"
          and "选择确认" in desc_of(table, "定界符类型"),
          f"{field_of(table, '定界符类型')} / {desc_of(table, '定界符类型')}")
    check("SACK：FCCS 校验通过", "校验通过" in desc_of(table, "FC校验序列(FCS)"),
          desc_of(table, "FC校验序列(FCS)"))


def test_sack_preview_not_empty_via_gui():
    tab = _frame_gen_tab()
    gen = tab.csg_gen
    _select(gen.fk_combo, "sack")
    _select(gen.layer_combo, "mpdu")
    tab._do_realtime_update()
    _app().processEvents()
    check("SACK：GUI 预览表非空（回归：hex() 崩掉整块预览）",
          tab.preview_table.rowCount() > 0, str(tab.preview_table.rowCount()))
    _select(gen.fk_combo, "sof")
    _select(gen.layer_combo, "mpdu")


# ----------------------------------------------------------------------
# 7. 24 个测试模式全都能组出带链路层的帧
# ----------------------------------------------------------------------
def test_all_test_modes_build_linked_frames():
    gen = _fresh_gen()
    _select(gen.fk_combo, "sof")
    _select(gen.layer_combo, "mpdu")
    total = gen.mode_combo.count()
    bad = []
    for i in range(total):
        gen.mode_combo.setCurrentIndex(i)
        _app().processEvents()
        name = gen.mode_combo.itemText(i)
        try:
            res = gen.build()
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{name}: {exc}")
            continue
        if res is None or not res.has_link_layer():
            bad.append(f"{name}: 未带链路层")
            continue
        out = gen.output_bytes(res)
        if not out or out[0] != 0x19:
            bad.append(f"{name}: 输出异常 {out.hex() if out else 'None'}")
            continue
        table = CSGNewGenParser().parse_to_table(out, parse_level="auto")
        if "校验通过" not in desc_of(table, "完整性校验(CRC-32)"):
            bad.append(f"{name}: CRC-32 未通过")
    check(f"{total} 个测试模式全部组出带链路层且校验通过的 SOF 帧", not bad,
          "; ".join(bad))
    check("测试模式数量 >= 24", total >= 24, str(total))
    gen.mode_combo.setCurrentIndex(0)


# ----------------------------------------------------------------------
# 8. 输出层次
# ----------------------------------------------------------------------
def test_output_layers():
    gen = _fresh_gen()
    _select(gen.fk_combo, "sof")
    res = gen.build()
    sizes = {}
    for layer in ("bdu", "app", "ed", "mpdu"):
        _select(gen.layer_combo, layer)
        out = gen.output_bytes(res)
        sizes[layer] = len(out) if out else 0
    check("输出层次：四档均非空", all(sizes.values()), str(sizes))
    check("输出层次：bdu <= app < mpdu", sizes["bdu"] <= sizes["app"] < sizes["mpdu"],
          str(sizes))
    check("输出层次：ED 封装比 MPDU 长（含 ED 头尾）",
          sizes["ed"] > sizes["mpdu"], str(sizes))
    _select(gen.layer_combo, "ed")
    ed = gen.output_bytes(res)
    check("输出层次：ED 封装以 ED 起头、FF EE 收尾",
          ed is not None and ed[0] == 0xED and ed[-2:] == b"\xFF\xEE",
          ed.hex(" ").upper() if ed else "None")
    _select(gen.layer_combo, "mpdu")
    mpdu = gen.output_bytes(res)
    check("输出层次：MPDU 去 ED 后与 classic 链路口径一致",
          mpdu == res.mpdu, mpdu.hex(" ").upper()[:40] if mpdu else "None")


# ----------------------------------------------------------------------
# 9. 折叠区状态 + 展开/收起
# ----------------------------------------------------------------------
def test_collapsible_state_and_buttons():
    gen = _fresh_gen()
    check("默认全部展开",
          all(sec.is_expanded() for sec in gen.sections.values()),
          str({k: s.is_expanded() for k, s in gen.sections.items()}))
    gen.collapse_all_btn.click()
    state = gen.link_state()
    check("收起全部后 link_state 全 False",
          set(state) == set(gen.sections) and not any(state.values()), str(state))
    gen.expand_all_btn.click()
    check("展开全部后 link_state 全 True",
          all(gen.link_state().values()), str(gen.link_state()))
    # 容错恢复
    restored = gen.apply_link_state({"fc": False, "不存在的区": True, "pb": "非法值"})
    check("apply_link_state 容错：仅应用已知且合法的键",
          gen.sections["fc"].is_expanded() is False
          and gen.sections["pb"].is_expanded() is True,
          str(restored))


# ----------------------------------------------------------------------
# 10. 其他协议切回去不受影响
# ----------------------------------------------------------------------
def test_protocol_switch_back_restores_left_pane():
    win = _main_window()
    tab = _frame_gen_tab()
    for index in (0, 6, 7, 8, 12):
        win._on_protocol_changed(index)
        _app().processEvents()
        check(f"协议{index}：左栏回到第 0 页", tab.left_stack.currentIndex() == 0,
              str(tab.left_stack.currentIndex()))
        check(f"协议{index}：预设按钮恢复可见（非 csg 模式）",
              tab.add_preset_btn.isVisible())
    win._on_protocol_changed(9)
    _app().processEvents()
    check("切回协议9：左栏回到组帧页", tab.left_stack.currentIndex() == 1,
          str(tab.left_stack.currentIndex()))
    check("切回协议9：字段模式组保持隐藏", not tab.mode_group.isVisible())


def test_reset_keeps_csg_page_on_stack():
    win = _main_window()
    tab = win.frame_gen_tab
    win._on_protocol_changed(9)
    _app().processEvents()
    tab.reset()                  # reset 不改协议模式，但会走 _rebuild_form(None)
    _app().processEvents()
    check("reset 后左栏仍在组帧页", tab.left_stack.currentIndex() == 1,
          str(tab.left_stack.currentIndex()))
    check("reset 后字段模式组仍隐藏（mode_group 是栈外兄弟节点）",
          not tab.mode_group.isVisible())


# ----------------------------------------------------------------------
# 11. 配置快照往返
# ----------------------------------------------------------------------
def test_config_snapshot_carries_collapse_state():
    win = _main_window()
    win._on_protocol_changed(9)
    _app().processEvents()
    tab = win.frame_gen_tab
    gen = tab.csg_gen
    gen.collapse_all_btn.click()
    snap = tab.get_config_snapshot()
    check("快照带 csg.link_state", "csg" in snap and "link_state" in snap["csg"],
          str(snap.get("csg")))
    gen.expand_all_btn.click()
    tab.apply_config_snapshot(snap)
    check("apply_config_snapshot 恢复折叠状态",
          not any(gen.link_state().values()), str(gen.link_state()))
    gen.expand_all_btn.click()


# ----------------------------------------------------------------------
# 12. 生成按钮路径 + 按钮不裁字
# ----------------------------------------------------------------------
def test_generate_button_writes_result():
    win = _main_window()
    win._on_protocol_changed(9)
    _app().processEvents()
    tab = win.frame_gen_tab
    gen = tab.csg_gen
    _select(gen.fk_combo, "sof")
    _select(gen.layer_combo, "mpdu")
    tab._on_generate()
    _app().processEvents()
    text = tab.result_hex.toPlainText().strip()
    check("「生成帧」把 hex 写进生成结果", bool(text) and text.startswith("19"), text[:24])
    check("「生成帧」同时刷新右侧预览表", tab.preview_table.rowCount() > 0,
          str(tab.preview_table.rowCount()))


def test_csg_buttons_not_clipped():
    win = _main_window()
    win.tab_widget.setCurrentIndex(win._frame_gen_tab_index)
    win._on_protocol_changed(9)
    win.show()
    _app().processEvents()
    win._on_protocol_changed(9)
    _app().processEvents()
    gen = win.frame_gen_tab.csg_gen
    buttons = [gen.expand_all_btn, gen.collapse_all_btn]
    for name in dir(gen):
        widget = getattr(gen, name)
        if widget.__class__.__name__ == "QPushButton" and widget not in buttons:
            buttons.append(widget)
    clipped = []
    for btn in buttons:
        if btn.width() < btn.sizeHint().width():
            clipped.append(f"{btn.text()}({btn.width()}<{btn.sizeHint().width()})")
    check("协议9 组帧页无按钮裁字（show() 之后按 sizeHint 量）", not clipped,
          "; ".join(clipped))
    check("协议9 组帧页按钮未写死宽度上限（陷阱 63）",
          all(btn.maximumWidth() > 100000 for btn in buttons),
          str([(b.text(), b.maximumWidth()) for b in buttons]))


# ----------------------------------------------------------------------
# 13. ⓪ 仿照报文 / 模板
# ----------------------------------------------------------------------
_LEGACY_PARAMS = {
    "proto_version": 1,
    "header_len": 3,
    "header_len_layout": "parser",
    "protocol_type": 1,
    "value": 0x0123,
    "security_mode": 0,
    "phr_mcs": 2,
    "psdu_mcs": 3,
    "pb_size": 2,
}
#: 32bit 真实时间戳量级（> 0x7FFFFFFF）——锁死「QSpinBox 装不下 → OverflowError」回归
_REF_TIMESTAMP = 0x68E1A2B3


def _reference_app_frame() -> bytes:
    return fg.build_frame_from_mode("legacy_6", dict(_LEGACY_PARAMS)).app_frame


def _reference_ed_frame(payload: bytes = None) -> str:
    """造一帧「官方风格」的 ED 封装 SOF 帧（1.0测试·频段切换）作为仿照样本。"""
    cfg = link.LinkFrameConfig(
        frame_kind="sof", delimiter_type=link.DELIM_SOF, std_version=link.STD_VERSION_BPLC,
        channel="plc", access_indicator=1, snid=7, src_tei=0x111, dest_tei=0x222,
        link_id=0x2A, pb_count=1, pb_total=136, mac_header_type=link.MAC_HDR_TYPE_LONG,
        mac_version=link.MAC_VERSION_STD, tx_seq=5, msdu_seq=3,
        msdu_payload=payload if payload is not None else _reference_app_frame())
    mpdu = link.build_link_frame(cfg).mpdu
    return fg.build_ed_frame(mpdu, wrapper="plc2", physical_channel=1,
                             timestamp=_REF_TIMESTAMP, pb_count=1).hex(" ").upper()


def test_mirror_panel_fills_every_layer():
    gen = _fresh_gen()
    reference = _reference_ed_frame()
    gen.reverse_edit.setPlainText(reference)
    gen._on_reverse_apply()
    _app().processEvents()
    hint = gen.reverse_hint.text()
    check("仿照：提示报告与原文一致", "完全一致" in hint, hint[:200])
    check("仿照：帧类型识别为 SOF", gen.frame_kind() == "sof", gen.frame_kind())
    check("仿照：标准版本识别为 BPLC",
          gen.stdver_combo.currentData() == link.STD_VERSION_BPLC)
    check("仿照：SNID 回填", gen._link_field_value("snid") == 7,
          str(gen._link_field_value("snid")))
    check("仿照：源/目的 TEI 回填",
          (gen._link_field_value("src_tei"), gen._link_field_value("dest_tei")) == (0x111, 0x222),
          f"{gen._link_field_value('src_tei')}/{gen._link_field_value('dest_tei')}")
    check("仿照：链路标识符回填", gen._link_field_value("link_id") == 0x2A,
          str(gen._link_field_value("link_id")))
    check("仿照：MAC 发送序号 / MSDU 序列号回填",
          (gen._link_field_value("tx_seq"), gen._link_field_value("msdu_seq")) == (5, 3),
          f"{gen._link_field_value('tx_seq')}/{gen._link_field_value('msdu_seq')}")
    check("仿照：ED 包装与物理信道回填",
          (gen.ed_wrapper.currentData(), gen.ed_channel.value()) == ("plc2", 1))
    check("仿照：ED 32bit 时间戳回填（> 0x7FFFFFFF 也不溢出）",
          gen.ed_timestamp.value() == _REF_TIMESTAMP,
          hex(gen.ed_timestamp.value()))
    check("仿照：测试模式识别为 legacy_6（表61 模式号 6）",
          gen.mode_combo.currentData() == "legacy_6", str(gen.mode_combo.currentData()))
    check("仿照：模式参数回填",
          gen._read_mode_params() == _LEGACY_PARAMS, str(gen._read_mode_params()))
    check("仿照：结构化还原成功时载荷来源保持「测试模式」",
          gen.payload_src_combo.currentData() == "mode",
          str(gen.payload_src_combo.currentData()))


def test_mirror_tweak_then_regenerate():
    gen = _fresh_gen()
    reference = _reference_ed_frame()
    gen.reverse_edit.setPlainText(reference)
    gen._on_reverse_apply()
    _app().processEvents()
    gen._write_link_field("dest_tei", 0x333)
    out = gen.output_bytes(gen.build())
    check("仿照：改字段后输出变化", out.hex(" ").upper() != reference)
    check("仿照：改字段后帧长不变（同长度替换）",
          len(out) == len(bytes.fromhex(reference.replace(" ", ""))),
          f"{len(out)} vs {len(reference.split())}")
    table = CSGNewGenParser().parse_to_table(out, parse_level="auto")
    check("仿照：改字段后 FCCS 自动重算并通过",
          "校验通过" in desc_of(table, "FC校验序列(FCS)"), desc_of(table, "FC校验序列(FCS)"))
    check("仿照：改字段后 CRC-32 自动重算并通过",
          "校验通过" in desc_of(table, "完整性校验(CRC-32)"),
          desc_of(table, "完整性校验(CRC-32)"))
    check("仿照：新目的 TEI 生效", field_of(table, "原始目的TEI") == "819",
          str(field_of(table, "原始目的TEI")))


def test_mirror_fidelity_fallback_on_unmodeled_field():
    """报文标识符不是本工具固定的 0x0101 ⇒ 结构化还原不成 ⇒ 必须走手工载荷保真。"""
    payload = bytearray(_reference_app_frame())
    payload[1:3] = b"\x02\x02"          # 应用层「报文标识符」改成表单表达不了的值
    reference = _reference_ed_frame(bytes(payload))
    gen = _fresh_gen()
    gen.reverse_edit.setPlainText(reference)
    gen._on_reverse_apply()
    _app().processEvents()
    hint = gen.reverse_hint.text()
    check("保真：提示说明走了手工 HEX 兜底", "保真" in hint, hint[:240])
    check("保真：载荷来源切到「手工 HEX」", gen.payload_src_combo.currentData() == "hex",
          str(gen.payload_src_combo.currentData()))
    check("保真：手工载荷非空", bool(gen.payload_hex_edit.text().strip()))
    gen._on_reverse_compare()
    _app().processEvents()
    check("保真：对比当前输出报告逐字节一致",
          "逐字节一致" in gen.reverse_hint.text(), gen.reverse_hint.text()[:200])


def test_mirror_compare_reports_first_diff():
    gen = _fresh_gen()
    reference = _reference_ed_frame()
    gen.reverse_edit.setPlainText(reference)
    gen._on_reverse_apply()
    _app().processEvents()
    gen._write_link_field("dest_tei", 0x333)      # 故意改一个字段，制造差异
    gen._on_reverse_compare()
    _app().processEvents()
    hint = gen.reverse_hint.text()
    check("对比：报告不一致", "不一致" in hint, hint[:200])
    check("对比：给出首个不一致的偏移", "偏移" in hint, hint[:200])


def test_mirror_rejects_bad_input():
    gen = _fresh_gen()
    gen.reverse_edit.setPlainText("")
    gen._on_reverse_apply()
    check("仿照：空输入给出可读提示", "粘贴" in gen.reverse_hint.text(),
          gen.reverse_hint.text()[:120])
    gen.reverse_edit.setPlainText("ZZ GG")
    gen._on_reverse_apply()
    check("仿照：非法 HEX 给出可读提示", "❌" in gen.reverse_hint.text(),
          gen.reverse_hint.text()[:120])


def test_template_store_path_contract():
    path = tpl.store_path()
    check("模板落盘在应用数据目录", path.parent == app_paths_dir(), str(path))
    check("模板文件名固定", path.name == "csg_frame_templates.json", path.name)


def app_paths_dir():
    import app_paths
    return app_paths.app_data_dir()


def test_template_save_load_delete_roundtrip():
    """模板存档往返：save → load（参数被套回）→ delete。用独立临时文件，不污染数据目录。"""
    import tempfile
    from pathlib import Path

    original_store = tpl.store_path
    tmp = Path(tempfile.mkdtemp(prefix="csg_tpl_")) / "templates.json"
    tpl.store_path = lambda: tmp
    try:
        gen = _fresh_gen()
        reference = _reference_ed_frame()
        gen.reverse_edit.setPlainText(reference)
        gen._on_reverse_apply()
        _app().processEvents()
        gen._write_link_field("dest_tei", 0x3AB)
        state_before = gen.frame_state()

        # 保存（绕过会阻塞的 QInputDialog）
        from PySide6.QtWidgets import QInputDialog

        original_get_text = QInputDialog.getText
        QInputDialog.getText = staticmethod(lambda *a, **k: ("自测模板", True))
        try:
            gen._on_template_save()
        finally:
            QInputDialog.getText = original_get_text
        _app().processEvents()
        check("模板：保存后下拉里出现", gen.template_combo.findData("自测模板") >= 0,
              str([gen.template_combo.itemData(i) for i in range(gen.template_combo.count())]))
        item = tpl.get_template("自测模板")
        check("模板：存档带参考报文", bool(item and item.get("reference_hex")), "")
        check("模板：存档带完整参数集", bool(item and item.get("state", {}).get("link")), "")
        check("模板：label 是状态摘要", bool(item and item.get("label")), "")

        # 把表单改掉，再加载回来
        gen.apply_frame_state(rev.empty_state())
        gen._write_link_field("dest_tei", 0x001)
        gen.template_combo.setCurrentIndex(gen.template_combo.findData("自测模板"))
        gen._on_template_load()
        _app().processEvents()
        check("模板：加载后字段被套回（dest_tei=0x3AB）",
              gen._link_field_value("dest_tei") == 0x3AB,
              hex(gen._link_field_value("dest_tei") or 0))
        check("模板：加载后参数集与存档一致", gen.frame_state() == state_before,
              "参数集往返不一致")
        check("模板：加载后参考报文回到粘贴框",
              gen.reverse_edit.toPlainText().strip() == reference, "")

        # 删除（绕过确认框）
        from PySide6.QtWidgets import QMessageBox

        original_question = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        try:
            gen._on_template_delete()
        finally:
            QMessageBox.question = original_question
        _app().processEvents()
        check("模板：删除后从下拉消失", gen.template_combo.findData("自测模板") < 0, "")
        check("模板：删除后文件里也没有", tpl.get_template("自测模板") is None, "")
    finally:
        tpl.store_path = original_store
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def test_template_name_validation():
    check("模板名：空名被拒", tpl.validate_name("   ") != "", "")
    check("模板名：超长被拒", tpl.validate_name("x" * 80) != "", "")
    check("模板名：非法字符被拒", tpl.validate_name("a/b") != "", "")
    check("模板名：正常名通过", tpl.validate_name("  频段切换  002 ") == "", "")
    check("模板名：清洗多余空白", tpl.normalize_name("  a   b  ") == "a b",
          tpl.normalize_name("  a   b  "))


# ----------------------------------------------------------------------
# 14. 「响应帧解析」开关（协议9 默认收起）
# ----------------------------------------------------------------------
def test_response_pane_default_hidden_for_protocol_9():
    win = _main_window()
    win._on_protocol_changed(9)
    _app().processEvents()
    tab = _frame_gen_tab()
    check("协议9：响应解析默认收起", not tab.resp_group.isVisible())
    check("协议9：开关处于未勾选", not tab.show_resp_check.isChecked())
    tab.show_resp_check.setChecked(True)
    _app().processEvents()
    check("协议9：勾上后响应解析显示", tab.resp_group.isVisible())
    # 协议9 用户偏好被记住：切到别的协议仍是显示
    win._on_protocol_changed(0)
    _app().processEvents()
    check("协议0：响应解析仍显示（用户偏好）", tab.resp_group.isVisible())
    win._on_protocol_changed(9)
    _app().processEvents()
    check("回到协议9：仍按纯组帧口径收起", not tab.resp_group.isVisible())
    win._on_protocol_changed(0)
    _app().processEvents()
    check("再回协议0：偏好恢复显示", tab.resp_group.isVisible())
    win._on_protocol_changed(9)
    _app().processEvents()


def test_real_time_preview_takes_full_height():
    win = _main_window()
    win.tab_widget.setCurrentIndex(win._frame_gen_tab_index)
    win._on_protocol_changed(9)
    win.show()
    _app().processEvents()
    win._on_protocol_changed(9)
    _app().processEvents()
    tab = _frame_gen_tab()
    check("协议9：预览表高度大于响应表收起时的高度（空间让给实时解析预览）",
          tab.preview_table.height() > 200, str(tab.preview_table.height()))


def main():
    _app()  # 任何 QWidget 之前必须先有 QApplication
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    try:
        for test in tests:
            test()
    finally:
        win = _Ctx.win
        if win is not None:
            win.close()
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
