# -*- coding: utf-8 -*-
"""由 yw645_frame_gen.FRAME_TEMPLATES 生成 YW645_command.json 预设种子（与模板同源）。

用法（项目根执行）::

    python .trellis/tasks/10-09-yiwa-645-protocol/tools/gen_yw645_seed.py

预设条目与 ``yw645_frame_gen.FRAME_TEMPLATES`` **同源**：帧 hex 由 ``build_from_template``
重算，config 快照由 ``template_state`` 产出 —— 改模板后重跑本脚本即可同步种子，
**不要手写 frame_hex**（test/test_yw645_frame_gen.py 有「种子与模板同源」对拍断言）。

⚠ 本文件在 ``<repo>/.trellis/tasks/<task>/tools/`` 下 ⇒ 项目根 = ``parents[4]``
（与同目录 mut_driver.py 同款约定）。
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import yw645_frame_gen as fg  # noqa: E402

GROUP_BY_KEY = {
    "read_dev_type": "读模式",
    "read_dev_id": "读模式",
    "read_batch": "读模式",
    "read_rsp_sample": "读模式",
    "pass_req": "透传模式",
    "pass_rsp": "透传模式",
}


def build_commands():
    commands = []
    for idx, tmpl in enumerate(fg.FRAME_TEMPLATES):
        key = tmpl["key"]
        frame = fg.build_from_template(key)
        state = fg.template_state(key)
        commands.append(
            {
                "id": f"yw{idx:02d}_{key}",
                "button_name": tmpl["label"],
                "group_name": GROUP_BY_KEY.get(key, tmpl.get("group", "默认分组")),
                "description": tmpl.get("description", ""),
                "protocol": "yw645",
                "frame_hex": " ".join(f"{b:02X}" for b in frame),
                "config": {"protocol_mode": "yw645", "yw645": state},
            }
        )
    return commands


def main() -> int:
    commands = build_commands()
    out = ROOT / "YW645_command.json"
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"commands": commands}, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as exc:  # pragma: no cover - 工具脚本
        print("写入失败:", exc)
        return 1
    print("written", out, len(commands), "entries")
    for c in commands:
        print(" ", c["id"], c["frame_hex"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
