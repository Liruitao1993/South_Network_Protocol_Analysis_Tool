# -*- coding: utf-8 -*-
"""
协议8（DL/T 698.45）预设命令保存/显示修复测试（test_dlt698_preset.py）

运行：python test/test_dlt698_preset.py
覆盖：
- 模块级 _get_path：south→NW / gdw→GW / dlt698→DLT698_command.json（此前 dlt698 误落 GW）
- PresetButtonManager.add_command("dlt698", ..., path=tmp) 写入独立 DLT698 文件
- PresetButtonWidget.set_protocol 支持 dlt698（此前静默忽略）
- 加载时按 protocol 过滤：GW 文件中历史混入的 dlt698 条目不在国网页显示；
  无 protocol 键的老数据按文件归属正常显示
- AddPresetDialog 协议行显示「698.45 协议」
- 右键删除对应的 remove_command 从 DLT698 文件移除条目

全部使用临时目录文件，不污染真实 NW/GW/DLT698 JSON。offscreen 平台，无需显示器。
"""

import _path_setup  # noqa: E402

import os
import sys
import json
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

import preset_buttons  # noqa: E402
from preset_buttons import (  # noqa: E402
    PresetButtonManager, PresetButtonWidget, AddPresetDialog,
    NW_COMMAND_PATH, GW_COMMAND_PATH, DLT698_COMMAND_PATH, _get_path,
)

app = QApplication(sys.argv)

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


def section(title):
    print(f"\n== {title} ==")


def btn_texts(widget):
    return sorted(btn.text() for btn in widget._buttons.values())


# ---------------- 1. 模块级路径映射 ----------------
section("模块级 _get_path 路径映射")
check("south → NW_command.json", _get_path("south") == NW_COMMAND_PATH,
      str(_get_path("south")))
check("gdw → GW_command.json", _get_path("gdw") == GW_COMMAND_PATH,
      str(_get_path("gdw")))
check("dlt698 → DLT698_command.json（不再误落 GW）",
      _get_path("dlt698") == DLT698_COMMAND_PATH, str(_get_path("dlt698")))
check("DLT698 预设文件名为 DLT698_command.json",
      DLT698_COMMAND_PATH.name == "DLT698_command.json", DLT698_COMMAND_PATH.name)
check("DLT698 预设文件位于项目根", DLT698_COMMAND_PATH.parent == NW_COMMAND_PATH.parent)

# ---------------- 2. Manager 写入独立 DLT698 文件 ----------------
section("PresetButtonManager 写入/读取/删除（临时文件）")
tmp_dir = tempfile.mkdtemp(prefix="dlt698_preset_test_")
tmp_nw = Path(tmp_dir) / "tmp_nw_command.json"
tmp_gw = Path(tmp_dir) / "tmp_gw_command.json"
tmp_dlt698 = Path(tmp_dir) / "tmp_dlt698_command.json"

dlt698_cmd = {
    "protocol": "dlt698",
    "button_name": "698测试命令",
    "group_name": "测试分组",
    "frame_hex": "68 0E 00 41 01 07 08 09 AE C6 01 00 00 00 00 34 87 16",
    "description": "测试用 698 帧",
}
ok = PresetButtonManager.add_command("dlt698", dict(dlt698_cmd), path=tmp_dlt698)
check("add_command 写入成功", ok)
check("临时 DLT698 文件已生成", tmp_dlt698.exists())
with open(tmp_dlt698, "r", encoding="utf-8") as f:
    saved = json.load(f)
check("文件结构为 {\"commands\": [...]}", "commands" in saved and len(saved["commands"]) == 1)
check("条目 protocol=dlt698", saved["commands"][0].get("protocol") == "dlt698")
check("条目自动分配 id", bool(saved["commands"][0].get("id")))
dlt698_id = saved["commands"][0]["id"]

cmds = PresetButtonManager.load_commands("dlt698", path=tmp_dlt698)
check("load_commands 读回 1 条", len(cmds) == 1, f"n={len(cmds)}")

# ---------------- 3. Widget 加载与 protocol 过滤 ----------------
section("PresetButtonWidget 加载 / 协议切换 / 过滤")

# 南网临时文件：1 条带 protocol=south + 1 条无 protocol 键的老数据
nw_data = {"commands": [
    {"protocol": "south", "button_name": "南网命令A", "group_name": "常用查询",
     "frame_hex": "68 01 16", "id": "nw0001"},
    {"button_name": "南网老数据无protocol", "group_name": "常用查询",
     "frame_hex": "68 02 16", "id": "nw0002"},
]}
with open(tmp_nw, "w", encoding="utf-8") as f:
    json.dump(nw_data, f, ensure_ascii=False)

# 国网临时文件：2 条 gdw + 1 条历史混入的 dlt698 条目
gw_data = {"commands": [
    {"protocol": "gdw", "button_name": "国网命令B", "group_name": "常用查询",
     "frame_hex": "68 03 16", "id": "gw0001"},
    {"protocol": "gdw", "button_name": "国网命令C", "group_name": "常用设置",
     "frame_hex": "68 04 16", "id": "gw0002"},
    {"protocol": "dlt698", "button_name": "混入的698条目", "group_name": "福建扩展",
     "frame_hex": "68 05 16", "id": "gw0003"},
]}
with open(tmp_gw, "w", encoding="utf-8") as f:
    json.dump(gw_data, f, ensure_ascii=False)

widget = PresetButtonWidget(nw_path=tmp_nw, gw_path=tmp_gw)

# 默认 south
check("默认协议 south", widget._protocol == "south")
check("南网页显示 2 条（含无 protocol 老数据）",
      btn_texts(widget) == ["南网命令A", "南网老数据无protocol"], str(btn_texts(widget)))
check("南网统计 label 为过滤后数量", "共 2 个" in widget.stats_label.text(),
      widget.stats_label.text())

# 切到 gdw：混入的 dlt698 条目必须被过滤
widget.set_protocol("gdw")
check("set_protocol(gdw) 生效", widget._protocol == "gdw")
check("国网页显示 2 条 gdw 命令",
      btn_texts(widget) == ["国网命令B", "国网命令C"], str(btn_texts(widget)))
check("国网页不含混入的 dlt698 条目", "混入的698条目" not in btn_texts(widget))
check("国网统计 label 为过滤后数量 2", "共 2 个" in widget.stats_label.text(),
      widget.stats_label.text())

# 切到 dlt698：monkeypatch 模块默认路径指向临时文件（不污染真实 DLT698_command.json）
_orig_dlt698_path = preset_buttons.DLT698_COMMAND_PATH
try:
    preset_buttons.DLT698_COMMAND_PATH = tmp_dlt698
    widget.set_protocol("dlt698")
    check("set_protocol(dlt698) 生效（此前被静默忽略）", widget._protocol == "dlt698")
    check("实例 _get_path() 返回 None（回退模块默认路径，无自定义路径配置）",
          widget._get_path() is None, str(widget._get_path()))
    check("有效默认路径为 DLT698_command.json",
          preset_buttons._get_path(widget._protocol) == tmp_dlt698
          and preset_buttons._get_path(widget._protocol).name == tmp_dlt698.name)
    check("698 页显示 DLT698 文件条目", btn_texts(widget) == ["698测试命令"],
          str(btn_texts(widget)))
    check("698 页不显示 gdw/south 条目",
          "国网命令B" not in btn_texts(widget) and "南网命令A" not in btn_texts(widget))
    check("切换日志含 698.45", "698.45" in widget.log_text.toPlainText())

    # 切回 south 验证来回切换
    widget.set_protocol("south")
    check("切回 south 正常", widget._protocol == "south"
          and btn_texts(widget) == ["南网命令A", "南网老数据无protocol"])

    # ---------------- 4. AddPresetDialog 协议行 ----------------
    section("AddPresetDialog 协议行文案")
    dlg698 = AddPresetDialog("68 00 16", "dlt698")
    labels698 = [lb.text() for lb in dlg698.findChildren(QLabel)]
    check("dlt698 对话框显示「698.45 协议」",
          any("698.45 协议" in t for t in labels698), str(labels698))
    dlg698.close()

    dlg_south = AddPresetDialog("68 00 16", "south")
    labels_south = [lb.text() for lb in dlg_south.findChildren(QLabel)]
    check("south 对话框显示「南网协议」",
          any("南网协议" in t for t in labels_south), str(labels_south))
    dlg_south.close()

    dlg_gdw = AddPresetDialog("68 00 16", "gdw")
    labels_gdw = [lb.text() for lb in dlg_gdw.findChildren(QLabel)]
    check("gdw 对话框显示「国网协议」",
          any("国网协议" in t for t in labels_gdw), str(labels_gdw))
    dlg_gdw.close()

    # ---------------- 5. 删除条目（右键删除的数据层） ----------------
    section("remove_command 从 DLT698 文件移除")
    ok = PresetButtonManager.remove_command("dlt698", dlt698_id, path=tmp_dlt698)
    check("remove_command 成功", ok)
    check("删除后 DLT698 文件为空",
          PresetButtonManager.load_commands("dlt698", path=tmp_dlt698) == [])
finally:
    preset_buttons.DLT698_COMMAND_PATH = _orig_dlt698_path
    widget.close()
    # 清理临时文件
    for p in (tmp_nw, tmp_gw, tmp_dlt698):
        try:
            p.unlink()
        except OSError:
            pass
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

check("模块默认路径已还原", preset_buttons.DLT698_COMMAND_PATH == DLT698_COMMAND_PATH)

print(f"\n结果: {passed} 通过, {failed} 失败")
sys.exit(1 if failed else 0)
