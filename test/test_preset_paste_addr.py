# -*- coding: utf-8 -*-
"""预设命令页「粘贴报文添加按钮 + 一键批量替换地址」回归测试。

任务：10-26-preset-paste-addr-batch（预设页自足：不再绕到组帧页才能在预设防问新增/改地址）。

覆盖：
  [1] preset_protocol_index：与 protocol_registry.preset_mode 逐条对拍 + 未知/空
  [2] batch_fix_presets：南网/645 **真帧 oracle**（地址字节 + 该协议校验器 0 fail +
      非地址/非校验字节不变）、前导 FEH 保留、空帧/坏帧/混合批次、**不修改入参**
  [3] AddPresetDialog 编辑模式：可编辑 / 归一化 / 非法拒绝 / 剪贴板带入 / 非编辑模式逐字节不变
  [4] PresetButtonWidget offscreen：地址区按协议生成（south 两字段 / modular 禁用+提示）、
      一键替换端到端（写回 + 一次落盘 + 刷新 + 日志）、坏帧跳过并列原因、空地址拦截、按协议暂存输入
  [5] PresetButtonWidget offscreen：添加命令端到端（替身对话框）→ JSON 多一条 + 按钮出现
  [6] 按钮不裁字（show() 后 width >= sizeHint，且未设 maximumWidth）

运行: python test/test_preset_paste_addr.py
"""

import _path_setup  # noqa: E402,F401

import copy  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QDialog  # noqa: E402

import preset_buttons as pb  # noqa: E402
import protocol_registry  # noqa: E402

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {detail}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


def hx(text):
    return bytes.fromhex(str(text).replace(" ", ""))


def unhex(text):
    return bytes.fromhex(str(text).replace(" ", ""))


def validator_fail(index, frame):
    """该协议校验器的失败项数量（0 = 通过）。"""
    return protocol_registry.make_validator(index).verify(frame).fail_count


_app_instance = None


def app():
    global _app_instance
    if _app_instance is None:
        _app_instance = QApplication.instance() or QApplication([])
    return _app_instance


# ── 真帧夹具（南网/645 取自 test_serial_addr_fix.py 的 oracle 帧，逐字节已验证）──

#: 南网（协议0）带地址域（控制域 D5=1）：源 00×6，目的 22 00 00 00 00 00
SOUTH_ADDR = ("68 28 00 20 00 00 00 00 00 00 22 00 00 00 00 00 02 00 01 02 02 "
              "E8 00 00 00 1E 00 09 00 01 02 03 04 05 06 07 08 09 85 16")
#: 645（协议6）读正向有功总电能（表地址 00×6）
DLT645 = "68 00 00 00 00 00 00 68 11 04 33 33 34 33 B2 16"
FE4 = "FE FE FE FE "

#: 与 load_buttons 同判据的过滤（本测试自己算，避免用产品函数当期望）
def in_scope(cmd, protocol):
    return cmd.get("protocol", protocol) == protocol


# ── [1] 协议映射 ────────────────────────────────────────────────────────────

def test_protocol_index():
    section("[1] preset_protocol_index（唯一来源 protocol_registry.preset_mode）")
    expected = {"south": 0, "gdw": 7, "dlt698": 8, "dlt645": 6,
                "modular": 12, "yw645": 13, "csg_uplink": 14}
    for key, index in expected.items():
        got = pb.preset_protocol_index(key)
        check(f"{key} → {index}", got == index, f"got={got}")
    check("未知协议 → None", pb.preset_protocol_index("nope") is None)
    check("空串 → None", pb.preset_protocol_index("") is None)
    check("None → None", pb.preset_protocol_index(None) is None)

    # 与注册表逐条对拍（注册表加协议 / 改 preset_mode 时这里会提醒）
    drift = []
    for spec in protocol_registry.all_protocols():
        if not spec.preset_mode:
            continue
        if pb.preset_protocol_index(spec.preset_mode) != spec.index:
            drift.append((spec.preset_mode, spec.index))
    check("每个 preset_mode 都能反查出正确索引", not drift, str(drift))


# ── [2] batch_fix_presets（纯逻辑）──────────────────────────────────────────

def test_batch_fix_presets():
    section("[2] batch_fix_presets 纯逻辑（真帧 oracle）")

    commands = [{"button_name": "南网读数据", "frame_hex": SOUTH_ADDR, "id": "s1"}]
    snapshot = copy.deepcopy(commands)
    items = pb.batch_fix_presets(commands, 0, {"src": "000000000005",
                                               "dst": "000000000006"})
    check("单条成功", len(items) == 1 and items[0].status == pb.ADDR_STATUS_OK,
          str([(i.status, i.error) for i in items]))
    check("不修改入参（逐键深比较）", commands == snapshot)
    if items and items[0].status == pb.ADDR_STATUS_OK:
        item = items[0]
        new = unhex(item.frame_hex)
        old = unhex(SOUTH_ADDR)
        check("源地址写入 05 00 00 00 00 00（书写序逆序上线的期望值）",
              new[4:10] == bytes([5, 0, 0, 0, 0, 0]), new[4:10].hex(" "))
        check("目的地址写入 06 00 00 00 00 00",
              new[10:16] == bytes([6, 0, 0, 0, 0, 0]), new[10:16].hex(" "))
        check("整帧长度不变", len(new) == len(old))
        check("该协议校验器 0 fail（地址改了、校验已重算）", validator_fail(0, new) == 0,
              f"fail={validator_fail(0, new)}")
        touched = set(range(4, 16)) | {len(old) - 2}
        changed = {i for i in range(len(old)) if old[i] != new[i]}
        check("只有地址域与校验字节变化", changed <= touched, str(sorted(changed)))
        notes = "；".join(item.notes)
        check("notes 含「地址域」与「校验和」",
              "地址域" in notes and "校验和" in notes, notes)
        check("items.index 指向传入列表下标", item.index == 0, str(item.index))

    # 645 + 前导 FEH：剥离并**原样恢复**（DL/T 645 §5.3.1）
    fe_cmd = [{"button_name": "645带前导", "frame_hex": FE4 + DLT645}]
    fe_items = pb.batch_fix_presets(fe_cmd, 6, {"addr": "000000000033"})
    check("645 带前导：成功", fe_items[0].status == pb.ADDR_STATUS_OK,
          fe_items[0].error)
    if fe_items[0].status == pb.ADDR_STATUS_OK:
        tokens = fe_items[0].frame_hex.split()
        body = unhex(" ".join(tokens[4:]))
        check("前导 FE×4 保留", tokens[:4] == ["FE", "FE", "FE", "FE"], str(tokens[:4]))
        check("645 表地址写入 33 00 00 00 00 00",
              body[1:7] == bytes([0x33, 0, 0, 0, 0, 0]), body[1:7].hex(" "))
        check("645 校验器 0 fail", validator_fail(6, body) == 0,
              f"fail={validator_fail(6, body)}")

    # 空帧 / 坏帧 / 混合批次（失败不中断整批）
    mixed = [
        {"button_name": "空报文", "frame_hex": "   "},
        {"button_name": "坏帧", "frame_hex": "68 01 16"},
        {"button_name": "好帧", "frame_hex": SOUTH_ADDR},
    ]
    items = pb.batch_fix_presets(mixed, 0, {"src": "000000000001"})
    statuses = [(i.name, i.status) for i in items]
    check("空报文 → skipped 且原因可读",
          items[0].status == pb.ADDR_STATUS_SKIPPED and "空" in items[0].error,
          str(statuses))
    check("坏帧 → skipped 且原因可读",
          items[1].status == pb.ADDR_STATUS_SKIPPED and bool(items[1].error),
          str(statuses))
    check("同一批里的好帧仍成功（失败不中断整批）",
          items[2].status == pb.ADDR_STATUS_OK, str(statuses))
    check("skipped 的 frame_hex 保持原值",
          items[0].frame_hex == "   " and items[1].frame_hex == "68 01 16",
          f"{items[0].frame_hex!r} / {items[1].frame_hex!r}")

    # 协议不支持（modular=12）：可读原因，不抛
    unsupported = pb.batch_fix_presets(
        [{"button_name": "模组化", "frame_hex": "68 00 00 16"}], 12, {"addr": "1"})
    check("不支持的协议 → skipped + 可读原因",
          unsupported[0].status == pb.ADDR_STATUS_SKIPPED
          and "不支持" in unsupported[0].error, unsupported[0].error)

    # 反例自检：改地址但不重算校验 ⇒ 校验器必红（证明 oracle 有效）
    broken = bytearray(unhex(SOUTH_ADDR))
    broken[4:10] = bytes([5, 0, 0, 0, 0, 0])
    check("反例自检：只改地址不重算校验 → 校验器必红",
          validator_fail(0, bytes(broken)) > 0)


# ── [3] AddPresetDialog 编辑模式 ────────────────────────────────────────────

def test_add_dialog():
    section("[3] AddPresetDialog 编辑模式 / 归一化 / 剪贴板")
    app()

    # 剪贴板带入连续写法
    QApplication.clipboard().setText("6812004116")
    dlg = pb.AddPresetDialog("", "south", editable_frame=True)
    check("编辑模式：报文框可编辑", not dlg.frame_preview.isReadOnly())
    check("编辑模式：有「从剪贴板粘贴」按钮", hasattr(dlg, "paste_btn"))
    check("打开时自动带入剪贴板 HEX（归一化为空格分隔）",
          dlg.frame_preview.toPlainText() == "68 12 00 41 16",
          dlg.frame_preview.toPlainText())

    dlg.name_input.setText("粘贴命令")
    dlg._on_ok()
    result = dlg.get_result() or {}
    check("确定后存归一化 HEX", result.get("frame_hex") == "68 12 00 41 16",
          str(result.get("frame_hex")))
    check("protocol 仍是当前协议", result.get("protocol") == "south",
          str(result.get("protocol")))

    # 非法 HEX：警告 + 不 accept（result 仍为空）
    dlg_bad = pb.AddPresetDialog("", "south", editable_frame=True)
    dlg_bad.name_input.setText("非法")
    dlg_bad.frame_preview.setPlainText("68 12 0G")
    with mock.patch.object(QMessageBox, "warning") as warn:
        dlg_bad._on_ok()
    check("非法 HEX 弹警告", warn.called)
    check("非法 HEX 不产出结果（不落盘）", dlg_bad.get_result() is None,
          str(dlg_bad.get_result()))

    # 空报文同样拒绝
    dlg_empty = pb.AddPresetDialog("", "south", editable_frame=True)
    dlg_empty.name_input.setText("空")
    dlg_empty.frame_preview.setPlainText("   ")
    with mock.patch.object(QMessageBox, "warning") as warn_empty:
        dlg_empty._on_ok()
    check("空报文被拒", warn_empty.called and dlg_empty.get_result() is None)

    # 从剪贴板粘贴按钮：剪贴板不是 HEX → 警告
    QApplication.clipboard().setText("这不是报文")
    dlg_paste = pb.AddPresetDialog("", "south", editable_frame=True)
    dlg_paste.frame_preview.setPlainText("")
    with mock.patch.object(QMessageBox, "warning") as warn_paste:
        dlg_paste._on_paste_clicked()
    check("剪贴板非 HEX → 明确提示", warn_paste.called)

    # 非编辑模式（组帧页既有调用方）：只读 + 报文原样
    QApplication.clipboard().setText("68 99 99 16")
    dlg_ro = pb.AddPresetDialog("68 00 16", "gdw")
    check("非编辑模式：报文框只读", dlg_ro.frame_preview.isReadOnly())
    check("非编辑模式：不读剪贴板", dlg_ro.frame_preview.toPlainText() == "68 00 16",
          dlg_ro.frame_preview.toPlainText())
    dlg_ro.name_input.setText("组帧页命令")
    dlg_ro._on_ok()
    check("非编辑模式：frame_hex 原样保存",
          (dlg_ro.get_result() or {}).get("frame_hex") == "68 00 16",
          str((dlg_ro.get_result() or {}).get("frame_hex")))

    for d in (dlg, dlg_bad, dlg_empty, dlg_paste, dlg_ro):
        d.close()


# ── [4] offscreen GUI：地址区 + 一键替换 ────────────────────────────────────

def _write_commands(path, commands):
    path.write_text(json.dumps({"commands": commands}, ensure_ascii=False),
                    encoding="utf-8")


def test_batch_addr_gui():
    section("[4] PresetButtonWidget offscreen：地址区 / 一键替换")
    app()
    tmp_dir = Path(tempfile.mkdtemp(prefix="preset_addr_test_"))
    tmp_nw = tmp_dir / "tmp_nw_command.json"
    tmp_gw = tmp_dir / "tmp_gw_command.json"
    # gdw 条目排在**前面**：若写回用相对下标，就会改错条目（本段的核心护栏）
    _write_commands(tmp_nw, [
        {"protocol": "gdw", "button_name": "混入国网", "group_name": "混入",
         "frame_hex": "68 03 16", "id": "g1"},
        {"protocol": "south", "button_name": "南网好帧", "group_name": "常用查询",
         "frame_hex": SOUTH_ADDR, "id": "s1"},
        {"protocol": "south", "button_name": "南网坏帧", "group_name": "常用查询",
         "frame_hex": "68 01 16", "id": "s2"},
    ])
    _write_commands(tmp_gw, [])
    widget = pb.PresetButtonWidget(nw_path=tmp_nw, gw_path=tmp_gw)
    try:
        # 字段按协议生成
        check("south 地址区字段 = src/dst",
              set(widget._addr_edits) == {"src", "dst"}, str(list(widget._addr_edits)))
        check("分组框标题带协议名",
              "南网" in widget.addr_group.title(), widget.addr_group.title())
        check("替换按钮可用", widget.batch_addr_btn.isEnabled())

        # 空地址 → 警告且文件不变
        before = tmp_nw.read_bytes()
        with mock.patch.object(QMessageBox, "warning") as warn:
            widget._on_batch_addr_clicked()
        check("未填地址 → 警告", warn.called)
        check("未填地址 → 文件字节不变", tmp_nw.read_bytes() == before)

        # 真正执行
        widget._addr_edits["src"].setText("000000000005")
        widget._addr_edits["dst"].setText("000000000006")
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information") as info, \
                mock.patch.object(QMessageBox, "warning") as warn2:
            widget._on_batch_addr_clicked()
        check("执行未弹警告", not warn2.called,
              str([c.args for c in warn2.call_args_list]))
        check("执行后有汇总弹框", info.called)
        info_text = str(info.call_args_list[0].args) if info.called else ""
        check("汇总里写明成功 1 / 跳过 1",
              "已替换 1 条" in info_text and "跳过 1 条" in info_text, info_text)
        check("汇总里列出坏帧原因（南网坏帧）",
              "南网坏帧" in info_text, info_text)

        saved = json.loads(tmp_nw.read_text(encoding="utf-8"))["commands"]
        by_id = {c["id"]: c for c in saved}
        new_frame = unhex(by_id["s1"]["frame_hex"])
        check("好帧已写回新地址（src=05…）",
              new_frame[4:10] == bytes([5, 0, 0, 0, 0, 0]), new_frame[4:10].hex(" "))
        check("好帧校验器 0 fail", validator_fail(0, new_frame) == 0,
              f"fail={validator_fail(0, new_frame)}")
        check("坏帧保持原样", by_id["s2"]["frame_hex"] == "68 01 16",
              by_id["s2"]["frame_hex"])
        check("同文件里非本协议条目保持原样（写回下标已映射回原表）",
              by_id["g1"]["frame_hex"] == "68 03 16", by_id["g1"]["frame_hex"])
        check("其它键未丢（id/group_name/description 原样）",
              by_id["s1"].get("group_name") == "常用查询" and by_id["s1"].get("id") == "s1")

        log_text = widget.log_text.toPlainText()
        check("日志有汇总行", "[地址替换] 成功 1 条，跳过 1 条" in log_text, log_text[-300:])
        check("日志逐条给出地址/校验变化",
              "南网好帧" in log_text and "校验和" in log_text, log_text[-300:])
        check("日志写明跳过原因",
              "南网坏帧：跳过（" in log_text, log_text[-300:])
        check("按钮已重建（tooltip 为新报文）",
              new_frame.hex(" ").upper() in widget._buttons["s1"].toolTip(),
              widget._buttons["s1"].toolTip())

        # 按协议暂存输入：切到 modular（不支持）再切回 south，值仍在
        widget.set_protocol("modular")
        check("modular 无地址字段", widget._addr_edits == {}, str(widget._addr_edits))
        check("modular 替换按钮禁用", not widget.batch_addr_btn.isEnabled())
        check("modular 提示「暂不支持」",
              "暂不支持" in widget.addr_hint.text(), widget.addr_hint.text())
        widget.set_protocol("south")
        check("切回南网：输入值被回填",
              widget._addr_edits["src"].text() == "000000000005",
              widget._addr_edits["src"].text())

        # 地址写法非法 → 警告、不弹确认、文件不变
        widget._addr_edits["src"].setText("ZZ")
        before_bad_text = tmp_nw.read_bytes()
        with mock.patch.object(QMessageBox, "warning") as warn_bad_text, \
                mock.patch.object(QMessageBox, "question") as ask_bad_text:
            widget._on_batch_addr_clicked()
        check("地址写法非法 → 警告且不弹确认",
              warn_bad_text.called and not ask_bad_text.called)
        check("地址写法非法 → 文件字节不变", tmp_nw.read_bytes() == before_bad_text)

        # 全部失败 → 明确告知且一个字节都不写（另开一个只有坏帧的文件）
        tmp_nw_bad = tmp_dir / "tmp_nw_bad.json"
        _write_commands(tmp_nw_bad, [
            {"protocol": "south", "button_name": "只有坏帧", "group_name": "常用查询",
             "frame_hex": "68 01 16", "id": "b1"},
        ])
        widget_bad = pb.PresetButtonWidget(nw_path=tmp_nw_bad, gw_path=tmp_gw)
        try:
            before_all_bad = tmp_nw_bad.read_bytes()
            widget_bad._addr_edits["src"].setText("000000000005")
            with mock.patch.object(QMessageBox, "warning") as warn_all, \
                    mock.patch.object(QMessageBox, "question") as ask_all:
                widget_bad._on_batch_addr_clicked()
            check("全部失败 → 明确告知", warn_all.called)
            check("全部失败 → 不弹确认", not ask_all.called)
            check("全部失败 → 一个字节都不写", tmp_nw_bad.read_bytes() == before_all_bad)
            check("全部失败 → 提示里带坏帧原因",
                  "只有坏帧" in str(warn_all.call_args_list),
                  str(warn_all.call_args_list))
        finally:
            widget_bad.close()
            try:
                tmp_nw_bad.unlink()
            except OSError:
                pass
    finally:
        widget.close()
        for p in (tmp_nw, tmp_gw):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


# ── [5] offscreen GUI：添加命令 ────────────────────────────────────────────

class _FakeAddDialog:
    """替身对话框（offscreen 下真 ``exec()`` 会阻塞）。"""

    result = {
        "protocol": "south",
        "button_name": "粘贴新增按钮",
        "group_name": "常用查询",
        "frame_hex": "68 12 00 41 16",
        "description": "端到端测试",
    }

    def __init__(self, frame_hex="", protocol="south", parent=None, **kwargs):
        self.kwargs = dict(kwargs)
        self.protocol = protocol

    def exec(self):
        return QDialog.Accepted

    def get_result(self):
        return dict(self.result)


def test_add_command_gui():
    section("[5] PresetButtonWidget offscreen：添加命令（粘贴报文）")
    app()
    tmp_dir = Path(tempfile.mkdtemp(prefix="preset_add_test_"))
    tmp_nw = tmp_dir / "tmp_nw_command.json"
    tmp_gw = tmp_dir / "tmp_gw_command.json"
    _write_commands(tmp_nw, [])
    _write_commands(tmp_gw, [])
    widget = pb.PresetButtonWidget(nw_path=tmp_nw, gw_path=tmp_gw)
    try:
        check("有「添加命令」按钮", widget.add_btn.text() == "添加命令")
        with mock.patch.object(pb, "AddPresetDialog", _FakeAddDialog):
            widget._on_add_clicked()
        saved = json.loads(tmp_nw.read_text(encoding="utf-8"))["commands"]
        check("JSON 多一条", len(saved) == 1, str(len(saved)))
        check("落盘报文为对话框给的值（已归一化）",
              saved[0].get("frame_hex") == "68 12 00 41 16",
              str(saved[0].get("frame_hex")))
        check("protocol 写当前协议", saved[0].get("protocol") == "south")
        new_id = saved[0].get("id", "")
        check("按钮立即出现",
              widget._buttons.get(new_id) is not None
              and widget._buttons[new_id].text() == "粘贴新增按钮",
              f"id={new_id!r} keys={list(widget._buttons)}")
        check("日志记录添加", "已添加预设" in widget.log_text.toPlainText(),
              widget.log_text.toPlainText()[-200:])
        check("统计已刷新", "共 1 个预设命令" in widget.stats_label.text(),
              widget.stats_label.text())

        # 保存失败必须外显（不静默）
        with mock.patch.object(pb, "AddPresetDialog", _FakeAddDialog), \
                mock.patch.object(pb.PresetButtonManager, "add_command",
                                  return_value=False), \
                mock.patch.object(QMessageBox, "warning") as warn:
            widget._on_add_clicked()
        check("保存失败 → 弹警告", warn.called)
    finally:
        widget.close()
        for p in (tmp_nw, tmp_gw):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


# ── [6] 按钮不裁字 ──────────────────────────────────────────────────────────

def test_buttons_not_clipped():
    section("[6] 按钮宽度（陷阱 63：不许写死、按 sizeHint 判定）")
    app()
    tmp_dir = Path(tempfile.mkdtemp(prefix="preset_fit_test_"))
    tmp_nw = tmp_dir / "tmp_nw_command.json"
    tmp_gw = tmp_dir / "tmp_gw_command.json"
    _write_commands(tmp_nw, [])
    _write_commands(tmp_gw, [])
    widget = pb.PresetButtonWidget(nw_path=tmp_nw, gw_path=tmp_gw)
    try:
        widget.resize(900, 640)
        widget.show()
        app().processEvents()
        for label, btn in (("添加命令", widget.add_btn),
                           ("一键替换地址", widget.batch_addr_btn)):
            need = btn.sizeHint().width()
            check(f"{label}：width >= sizeHint（不裁字）", btn.width() >= need,
                  f"width={btn.width()} need={need}")
            check(f"{label}：未写死宽度（maximumWidth 不构成上限）",
                  btn.maximumWidth() > 10000, str(btn.maximumWidth()))
    finally:
        widget.close()
        for p in (tmp_nw, tmp_gw):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


def main():
    test_protocol_index()
    test_batch_fix_presets()
    test_add_dialog()
    test_batch_addr_gui()
    test_add_command_gui()
    test_buttons_not_clipped()
    print()
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
