# -*- coding: utf-8 -*-
"""协议9 组帧「仿照模板」本地存储（纯标准库，无 Qt）。

模板 = 一套完整组帧参数（:func:`csg_frame_reverse.empty_state` 结构）+ **原始参考报文**。
用途：从官方测试系统拷一帧 → 回填成参数 → 存成模板；下次直接加载模板、只改关键字段
（如 TEI / 帧序号 / 目标频段）即可生成新帧，不必重新填表。

落盘位置遵循 ``app_paths.data_path``（开发模式=项目根，打包后=exe 所在目录），
文件为 ``csg_frame_templates.json``，结构：

.. code-block:: json

    {"version": 1, "templates": [
        {"name": "...", "label": "SOF 帧 / BPLC / 带链路层 / 1.0测试·频段切换",
         "created": "2026-09-30 11:50", "updated": "...", "note": "",
         "reference_hex": "ED 1E ...", "state": { ... }}
    ]}

写入用「临时文件 + ``os.replace``」保证原子性；读取对损坏文件**宽容**（返回空表并给出
原因），绝不因一个坏文件让组帧页打不开。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import app_paths

FILENAME = "csg_frame_templates.json"
SCHEMA_VERSION = 1
#: 名称为空/过长都拒绝，避免写进无法在下拉里辨认的条目
MAX_NAME_LEN = 60
#: 上限保护：模板是"微调起点"，不需要无限堆积
MAX_TEMPLATES = 300


def store_path() -> Path:
    """模板文件路径（开发模式=项目根，frozen=exe 目录）。"""
    return Path(app_paths.data_path(FILENAME))


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _empty_payload() -> Dict[str, object]:
    return {"version": SCHEMA_VERSION, "templates": []}


def normalize_name(name: str) -> str:
    """清洗模板名（去首尾空白、压缩内部连续空白）。"""
    return " ".join(str(name or "").split())


def validate_name(name: str) -> str:
    """返回错误信息，空串表示合法。"""
    clean = normalize_name(name)
    if not clean:
        return "模板名不能为空"
    if len(clean) > MAX_NAME_LEN:
        return f"模板名过长（{len(clean)} > {MAX_NAME_LEN}）"
    if any(ch in clean for ch in '\\/:*?"<>|'):
        return "模板名不能包含 \\ / : * ? \" < > |"
    return ""


def _load_raw() -> Tuple[Dict[str, object], str]:
    """读文件；返回 (payload, 错误说明)。文件不存在不算错误。"""
    path = store_path()
    if not path.exists():
        return _empty_payload(), ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _empty_payload(), f"模板文件不可读：{exc}"
    if not text.strip():
        return _empty_payload(), ""
    try:
        data = json.loads(text)
    except ValueError as exc:
        return _empty_payload(), f"模板文件不是合法 JSON（{exc}），已按空表处理"
    if not isinstance(data, dict):
        return _empty_payload(), "模板文件结构异常（顶层不是对象），已按空表处理"
    items = data.get("templates")
    if not isinstance(items, list):
        items = []
    clean: List[Dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = normalize_name(item.get("name", ""))
        if not name:
            continue
        state = item.get("state")
        if not isinstance(state, dict):
            continue
        clean.append({
            "name": name,
            "label": str(item.get("label", "") or ""),
            "created": str(item.get("created", "") or ""),
            "updated": str(item.get("updated", "") or ""),
            "note": str(item.get("note", "") or ""),
            "reference_hex": str(item.get("reference_hex", "") or ""),
            "state": state,
        })
    return {"version": SCHEMA_VERSION, "templates": clean}, ""


def _write_raw(payload: Dict[str, object]) -> str:
    """原子写；返回错误信息，空串表示成功。"""
    path = store_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return f"模板保存失败：{exc}"
    return ""


def load_templates() -> Tuple[List[Dict[str, object]], str]:
    """全部模板（按写入顺序），第二项为读取告警（空串=正常）。

    读取告警只在**这里**返回（GUI 把它显示在模板提示行）；save/delete/rename
    只返回"写失败"原因，不把读取告警混进错误信息里。
    """
    payload, warn = _load_raw()
    return list(payload.get("templates", [])), warn


def template_names() -> List[str]:
    items, _ = load_templates()
    return [str(item["name"]) for item in items]


def get_template(name: str) -> Optional[Dict[str, object]]:
    target = normalize_name(name)
    items, _ = load_templates()
    for item in items:
        if item["name"] == target:
            return item
    return None


def save_template(name: str, state: Dict[str, object], reference_hex: str = "",
                  label: str = "", note: str = "") -> str:
    """新增或覆盖同名模板；返回错误信息，空串表示成功。"""
    error = validate_name(name)
    if error:
        return error
    if not isinstance(state, dict) or not state:
        return "参数集为空，未保存"
    clean = normalize_name(name)
    payload, _ = _load_raw()
    items = list(payload.get("templates", []))
    stamp = _now()
    entry = {
        "name": clean,
        "label": str(label or ""),
        "created": stamp,
        "updated": stamp,
        "note": str(note or ""),
        "reference_hex": str(reference_hex or ""),
        "state": state,
    }
    replaced = False
    for index, item in enumerate(items):
        if item["name"] == clean:
            entry["created"] = item.get("created") or stamp
            items[index] = entry
            replaced = True
            break
    if not replaced:
        if len(items) >= MAX_TEMPLATES:
            return f"模板数量已达上限 {MAX_TEMPLATES}，请先删除不再需要的模板"
        items.append(entry)
    payload["version"] = SCHEMA_VERSION
    payload["templates"] = items
    return _write_raw(payload)


def delete_template(name: str) -> str:
    """删除模板；返回错误信息，空串表示成功（不存在也视为成功）。"""
    clean = normalize_name(name)
    payload, _ = _load_raw()
    items = [item for item in payload.get("templates", []) if item["name"] != clean]
    payload["templates"] = items
    payload["version"] = SCHEMA_VERSION
    return _write_raw(payload)


def rename_template(old: str, new: str) -> str:
    """重命名；目标名已存在则拒绝（避免静默覆盖别人的模板）。"""
    error = validate_name(new)
    if error:
        return error
    src, dst = normalize_name(old), normalize_name(new)
    if src == dst:
        return ""
    payload, _ = _load_raw()
    items = list(payload.get("templates", []))
    if any(item["name"] == dst for item in items):
        return f"已存在同名模板「{dst}」"
    found = False
    for item in items:
        if item["name"] == src:
            item["name"] = dst
            item["updated"] = _now()
            found = True
            break
    if not found:
        return f"模板「{src}」不存在"
    payload["templates"] = items
    payload["version"] = SCHEMA_VERSION
    return _write_raw(payload)
