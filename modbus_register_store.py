# -*- coding: utf-8 -*-
"""Modbus 寄存器列表存储（纯逻辑，无 Qt）。

一份配置文件 ``modbus_registers.json`` 记录「每种品牌电表的寄存器列表」，
单帧 / 批量解析时按当前选中的那份翻译地址与取值：

.. code-block:: json

    {
      "version": 1,
      "selected": "example-single-phase",
      "profiles": [
        {
          "id": "example-single-phase",
          "name": "示例：单相智能电表（通用）",
          "brand": "示例",
          "transport": "auto",
          "byte_order": "big",
          "word_order": "big",
          "start_addr": 0,
          "note": "",
          "registers": [
            {"addr": 0, "name": "A相电压", "type": "uint16",
             "count": 1, "scale": 0.1, "unit": "V", "note": ""}
          ]
        }
      ]
    }

约定
----
- ``selected`` 为空或指向不存在的 ID ⇒ **通用解析**（不指定寄存器列表），
  与需求「没有选择则按通用方式解析」一致；
- ``start_addr`` 是**读响应**的起始地址（响应帧本身不带地址）。留空/``null``
  时取寄存器列表里的最小地址；
- ``byte_order`` 控制单个寄存器内字节序（``big`` = 高字节在前，
  ``little`` = 字节交换）；``word_order`` 控制 32/64 位值的寄存器顺序
  （``big`` = 高字在前，``little`` = 低字在前，即常说的 CDAB 之外的另一半）；
- 文件在 ``app_paths.data_path``（frozen → exe 同级；开发态 → 项目根），
  写入走 ``atomic_io.atomic_write_json``，损坏时回落到内置示例，绝不抛异常
  打断解析。
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import app_paths
from atomic_io import atomic_write_json, read_json

#: 数据文件名
STORE_FILE = "modbus_registers.json"

#: 数据结构版本（升级 schema 时递增，读取端按需兼容旧版本）
STORE_VERSION = 1

#: 支持的数据类型（与 modbus_core.REG_TYPES 同源，这里只做展示顺序）
DATA_TYPES: Tuple[str, ...] = (
    "uint16",
    "int16",
    "uint32",
    "int32",
    "uint64",
    "int64",
    "float32",
    "float64",
    "bit",
    "hex",
    "ascii",
)

#: 传输说明（仅展示用；解析时自动识别）
TRANSPORTS: Tuple[str, ...] = ("auto", "rtu", "tcp")

#: 32/64 位值的寄存器顺序
WORD_ORDERS: Tuple[str, ...] = ("big", "little")

#: 字节序
BYTE_ORDERS: Tuple[str, ...] = ("big", "little")

#: 内置示例（首次使用没有配置文件时作为初始内容；用户可任意修改）
DEFAULT_PROFILES: List[dict] = [
    {
        "id": "example-single-phase",
        "name": "示例：单相智能电表（通用）",
        "brand": "示例",
        "transport": "auto",
        "byte_order": "big",
        "word_order": "big",
        "start_addr": 0,
        "note": "示例数据，仅用于演示格式；实际地址/系数请按厂家 Modbus 协议手册修改",
        "registers": [
            {"addr": 0x0000, "name": "A相电压", "type": "uint16", "count": 1, "scale": 0.1, "unit": "V", "note": ""},
            {"addr": 0x0001, "name": "A相电流", "type": "uint16", "count": 1, "scale": 0.01, "unit": "A", "note": ""},
            {"addr": 0x0002, "name": "有功功率", "type": "int16", "count": 1, "scale": 1.0, "unit": "W", "note": "带符号：负值表示反向"},
            {"addr": 0x0003, "name": "无功功率", "type": "int16", "count": 1, "scale": 1.0, "unit": "var", "note": ""},
            {"addr": 0x0004, "name": "功率因数", "type": "int16", "count": 1, "scale": 0.001, "unit": "", "note": ""},
            {"addr": 0x0005, "name": "频率", "type": "uint16", "count": 1, "scale": 0.01, "unit": "Hz", "note": ""},
            {"addr": 0x0006, "name": "正向有功总电能", "type": "uint32", "count": 2, "scale": 0.01, "unit": "kWh", "note": "占 0x0006~0x0007"},
            {"addr": 0x0008, "name": "反向有功总电能", "type": "uint32", "count": 2, "scale": 0.01, "unit": "kWh", "note": "占 0x0008~0x0009"},
        ],
    },
    {
        "id": "example-three-phase",
        "name": "示例：三相多功能电表",
        "brand": "示例",
        "transport": "auto",
        "byte_order": "big",
        "word_order": "big",
        "start_addr": 0,
        "note": "示例数据，仅用于演示格式；实际地址/系数请按厂家 Modbus 协议手册修改",
        "registers": [
            {"addr": 0x0000, "name": "A相电压", "type": "uint16", "count": 1, "scale": 0.1, "unit": "V", "note": ""},
            {"addr": 0x0001, "name": "B相电压", "type": "uint16", "count": 1, "scale": 0.1, "unit": "V", "note": ""},
            {"addr": 0x0002, "name": "C相电压", "type": "uint16", "count": 1, "scale": 0.1, "unit": "V", "note": ""},
            {"addr": 0x0003, "name": "A相电流", "type": "uint16", "count": 1, "scale": 0.001, "unit": "A", "note": ""},
            {"addr": 0x0004, "name": "B相电流", "type": "uint16", "count": 1, "scale": 0.001, "unit": "A", "note": ""},
            {"addr": 0x0005, "name": "C相电流", "type": "uint16", "count": 1, "scale": 0.001, "unit": "A", "note": ""},
            {"addr": 0x0006, "name": "总有功功率", "type": "int32", "count": 2, "scale": 0.001, "unit": "kW", "note": "占 0x0006~0x0007"},
            {"addr": 0x0008, "name": "总无功功率", "type": "int32", "count": 2, "scale": 0.001, "unit": "kvar", "note": "占 0x0008~0x0009"},
            {"addr": 0x000A, "name": "总功率因数", "type": "int16", "count": 1, "scale": 0.001, "unit": "", "note": ""},
            {"addr": 0x000B, "name": "频率", "type": "uint16", "count": 1, "scale": 0.01, "unit": "Hz", "note": ""},
            {"addr": 0x000C, "name": "正向有功总电能", "type": "uint32", "count": 2, "scale": 0.01, "unit": "kWh", "note": "占 0x000C~0x000D"},
            {"addr": 0x000E, "name": "反向有功总电能", "type": "uint32", "count": 2, "scale": 0.01, "unit": "kWh", "note": "占 0x000E~0x000F"},
        ],
    },
]


# ── 路径 / 缓存 ────────────────────────────────────────────────────

#: 测试或 Web 版可显式指定文件路径（None = 走 app_paths.data_path）
_PATH_OVERRIDE: Optional[Path] = None

_CACHE: Optional[dict] = None
_CACHE_MTIME: Optional[float] = None


def store_path() -> Path:
    """寄存器列表配置文件路径。"""
    if _PATH_OVERRIDE is not None:
        return Path(_PATH_OVERRIDE)
    return app_paths.data_path(STORE_FILE)


def set_store_path(path: Optional[Path]) -> None:
    """显式指定配置文件路径（测试 / 多数据根场景）；传 None 恢复默认。"""
    global _PATH_OVERRIDE, _CACHE, _CACHE_MTIME
    _PATH_OVERRIDE = Path(path) if path is not None else None
    _CACHE = None
    _CACHE_MTIME = None


def default_store() -> dict:
    """内置初始内容（深拷贝，调用方可随意修改）。"""
    return {
        "version": STORE_VERSION,
        "selected": "",
        "profiles": copy.deepcopy(DEFAULT_PROFILES),
    }


# ── 归一化 / 校验 ──────────────────────────────────────────────────


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    text = _text(value)
    if not text:
        return default
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(text, 10)
    except ValueError:
        return default


def _to_float(value: Any, default: float = 1.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        if value is None or _text(value) == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def new_profile_id() -> str:
    """生成唯一 ID（时间戳 + 随机后缀，便于排序与阅读）。"""
    return f"p{int(time.time() * 1000):x}-{uuid.uuid4().hex[:6]}"


def normalize_register(raw: Any) -> Optional[dict]:
    """单个寄存器条目归一化；非法（地址缺失/非数字）返回 None。"""
    if not isinstance(raw, dict):
        return None
    addr = _to_int(raw.get("addr"))
    if addr is None or not 0 <= addr <= 0xFFFF:
        return None
    dtype = _text(raw.get("type") or "uint16").lower() or "uint16"
    if dtype not in DATA_TYPES:
        dtype = "uint16"
    count = _to_int(raw.get("count"), 1) or 1
    count = max(1, min(int(count), 120))
    return {
        "addr": int(addr),
        "name": _text(raw.get("name")),
        "type": dtype,
        "count": count,
        "scale": _to_float(raw.get("scale"), 1.0),
        "unit": _text(raw.get("unit")),
        "note": _text(raw.get("note")),
    }


def normalize_profile(raw: Any) -> Optional[dict]:
    """寄存器列表（profile）归一化；非 dict 返回 None。"""
    if not isinstance(raw, dict):
        return None
    registers: List[dict] = []
    seen = set()
    for item in raw.get("registers") or []:
        entry = normalize_register(item)
        if entry is None or entry["addr"] in seen:
            continue
        seen.add(entry["addr"])
        registers.append(entry)
    registers.sort(key=lambda e: e["addr"])
    start_addr = _to_int(raw.get("start_addr"))
    if start_addr is not None and not 0 <= start_addr <= 0xFFFF:
        start_addr = None
    if start_addr is None:
        start_addr = registers[0]["addr"] if registers else 0
    byte_order = _text(raw.get("byte_order") or "big").lower()
    if byte_order not in BYTE_ORDERS:
        byte_order = "big"
    word_order = _text(raw.get("word_order") or "big").lower()
    if word_order not in WORD_ORDERS:
        word_order = "big"
    transport = _text(raw.get("transport") or "auto").lower()
    if transport not in TRANSPORTS:
        transport = "auto"
    return {
        "id": _text(raw.get("id")) or new_profile_id(),
        "name": _text(raw.get("name")) or "未命名寄存器列表",
        "brand": _text(raw.get("brand")),
        "transport": transport,
        "byte_order": byte_order,
        "word_order": word_order,
        "start_addr": int(start_addr),
        "note": _text(raw.get("note")),
        "registers": registers,
    }


def validate_profile(profile: Any) -> Tuple[bool, str]:
    """校验一份寄存器列表，返回 ``(ok, error)``；error 可直接展示给用户。"""
    if not isinstance(profile, dict):
        return False, "寄存器列表必须是一个对象"
    if not _text(profile.get("name")):
        return False, "名称不能为空"
    registers = profile.get("registers")
    if not isinstance(registers, list) or not registers:
        return False, "至少需要一个寄存器条目"
    seen = set()
    for index, item in enumerate(registers, start=1):
        if not isinstance(item, dict):
            return False, f"第 {index} 行不是有效条目"
        addr = _to_int(item.get("addr"))
        if addr is None:
            return False, f"第 {index} 行地址非法（应为 0~65535，支持 0x 前缀）"
        if not 0 <= addr <= 0xFFFF:
            return False, f"第 {index} 行地址 {addr} 超出 0~65535"
        if addr in seen:
            return False, f"第 {index} 行地址 0x{addr:04X} 重复（同一地址只能出现一次）"
        seen.add(addr)
        dtype = _text(item.get("type") or "uint16").lower()
        if dtype not in DATA_TYPES:
            return False, f"第 {index} 行数据类型 {dtype!r} 不受支持"
        count = _to_int(item.get("count"), 1) or 1
        if not 1 <= count <= 120:
            return False, f"第 {index} 行寄存器数量应在 1~120 之间"
        scale_text = _text(item.get("scale"))
        if scale_text:
            try:
                float(scale_text)
            except ValueError:
                return False, f"第 {index} 行系数 {scale_text!r} 不是数字"
    return True, ""


# ── 读写 ────────────────────────────────────────────────────────────


def _normalize_store(raw: Any) -> dict:
    """整份存储归一化；结构非法时回落到内置示例。"""
    if not isinstance(raw, dict):
        return default_store()
    profiles: List[dict] = []
    ids = set()
    for item in raw.get("profiles") or []:
        profile = normalize_profile(item)
        if profile is None:
            continue
        if profile["id"] in ids:
            profile["id"] = new_profile_id()
        ids.add(profile["id"])
        profiles.append(profile)
    if not profiles:
        profiles = normalize_store_profiles(default_store())
    selected = _text(raw.get("selected"))
    if selected and selected not in ids:
        selected = ""
    return {
        "version": STORE_VERSION,
        "selected": selected,
        "profiles": profiles,
    }


def normalize_store_profiles(store: dict) -> List[dict]:
    """从存储对象取归一化后的 profiles（内部辅助，避免递归）。"""
    out: List[dict] = []
    for item in store.get("profiles") or []:
        profile = normalize_profile(item)
        if profile is not None:
            out.append(profile)
    return out


def _file_mtime(path: Path) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def load_store(force: bool = False) -> dict:
    """读取并缓存配置；文件缺失/损坏时返回内置示例（不写盘）。"""
    global _CACHE, _CACHE_MTIME
    path = store_path()
    mtime = _file_mtime(path)
    if (
        not force
        and _CACHE is not None
        and (mtime is None or mtime == _CACHE_MTIME)
    ):
        return _CACHE
    raw = read_json(path, None) if path.exists() else None
    if raw is None:
        _CACHE = default_store() if _CACHE is None else _CACHE
        _CACHE_MTIME = mtime
        return _CACHE
    _CACHE = _normalize_store(raw)
    _CACHE_MTIME = mtime
    return _CACHE


def reload() -> dict:
    """强制重新读盘（外部编辑文件后调用）。"""
    return load_store(force=True)


def save_store(store: dict) -> dict:
    """归一化后原子写盘，并刷新缓存；返回实际写入的结构。"""
    global _CACHE, _CACHE_MTIME
    normalized = _normalize_store(store)
    path = store_path()
    atomic_write_json(path, normalized)
    _CACHE = normalized
    _CACHE_MTIME = _file_mtime(path)
    return normalized


def ensure_store_file() -> dict:
    """配置文件不存在时创建一份（含内置示例）；已存在则直接返回内容。"""
    path = store_path()
    if not path.exists():
        try:
            return save_store(default_store())
        except OSError:
            return load_store(force=True)
    return load_store(force=True)


# ── 查询 / 增删改 ──────────────────────────────────────────────────


def profiles() -> List[dict]:
    """全部寄存器列表（只读视图；修改请走 upsert_profile）。"""
    return load_store().get("profiles") or []


def get_profile(profile_id: str) -> Optional[dict]:
    """按 ID 取一份寄存器列表的深拷贝（找不到返回 None）。"""
    target = _text(profile_id)
    if not target:
        return None
    for profile in profiles():
        if profile.get("id") == target:
            return copy.deepcopy(profile)
    return None


def selected_id() -> str:
    """当前选中的寄存器列表 ID（空串 = 通用解析）。"""
    return _text(load_store().get("selected"))


def set_selected(profile_id: str) -> dict:
    """设置当前选中的寄存器列表（空串/不存在的 ID ⇒ 通用解析）。"""
    store = load_store()
    target = _text(profile_id)
    if target and not any(p.get("id") == target for p in store.get("profiles") or []):
        target = ""
    updated = {
        "version": STORE_VERSION,
        "selected": target,
        "profiles": copy.deepcopy(store.get("profiles") or []),
    }
    return save_store(updated)


def selected_profile() -> Optional[dict]:
    """当前选中的寄存器列表（只读引用；无选择 ⇒ None = 通用解析）。"""
    target = selected_id()
    if not target:
        return None
    for profile in profiles():
        if profile.get("id") == target:
            return profile
    return None


def upsert_profile(profile: dict) -> str:
    """新增或按 ID 覆盖一份寄存器列表；返回其 ID。"""
    normalized = normalize_profile(profile)
    if normalized is None:
        raise ValueError("寄存器列表格式非法")
    ok, error = validate_profile(normalized)
    if not ok:
        raise ValueError(error)
    store = load_store()
    items = [copy.deepcopy(p) for p in store.get("profiles") or []]
    replaced = False
    for index, item in enumerate(items):
        if item.get("id") == normalized["id"]:
            items[index] = normalized
            replaced = True
            break
    if not replaced:
        items.append(normalized)
    save_store(
        {
            "version": STORE_VERSION,
            "selected": store.get("selected") or "",
            "profiles": items,
        }
    )
    return normalized["id"]


def delete_profile(profile_id: str) -> bool:
    """删除一份寄存器列表（若正被选中，选中项自动清空 = 通用解析）。"""
    target = _text(profile_id)
    if not target:
        return False
    store = load_store()
    items = [p for p in store.get("profiles") or [] if p.get("id") != target]
    if len(items) == len(store.get("profiles") or []):
        return False
    selected = store.get("selected") or ""
    if selected == target:
        selected = ""
    save_store(
        {"version": STORE_VERSION, "selected": selected, "profiles": items}
    )
    return True


def duplicate_profile(profile_id: str, name: str = "") -> Optional[str]:
    """复制一份寄存器列表（用于「新建自某品牌」）；返回新 ID。"""
    source = get_profile(profile_id)
    if source is None:
        return None
    source["id"] = new_profile_id()
    source["name"] = _text(name) or f"{source.get('name', '未命名')}（副本）"
    try:
        return upsert_profile(source)
    except ValueError:
        return None


# ── 导入 / 导出（JSON 文本）─────────────────────────────────────────


def profile_to_json(profile: dict) -> str:
    """单份寄存器列表 → 格式化 JSON 文本（导出用）。"""
    return json.dumps(normalize_profile(profile) or profile, ensure_ascii=False, indent=2)


def parse_profiles(text: str) -> List[dict]:
    """从 JSON 文本解析寄存器列表（支持单份或数组，也支持整份存储）。

    非法条目会被跳过；没有任何合法条目时抛 ``ValueError``（带中文原因）。
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"JSON 解析失败：{exc}") from exc
    if isinstance(data, dict) and "profiles" in data:
        candidates = data.get("profiles") or []
    elif isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        candidates = [data]
    else:
        raise ValueError("JSON 顶层应为对象或数组")
    profiles_out: List[dict] = []
    for item in candidates:
        normalized = normalize_profile(item)
        if normalized is None:
            continue
        ok, error = validate_profile(normalized)
        if not ok:
            continue
        profiles_out.append(normalized)
    if not profiles_out:
        raise ValueError("文件中没有合法的寄存器列表（检查 name / registers / addr 字段）")
    return profiles_out


def import_profiles(text: str) -> List[str]:
    """导入 JSON 文本里的寄存器列表；ID 冲突时自动重新分配，返回导入后的 ID 列表。"""
    incoming = parse_profiles(text)
    existing = {p.get("id") for p in profiles()}
    imported: List[str] = []
    for profile in incoming:
        if profile.get("id") in existing:
            profile["id"] = new_profile_id()
        imported.append(upsert_profile(profile))
    return imported


__all__ = [
    "STORE_FILE",
    "STORE_VERSION",
    "DATA_TYPES",
    "TRANSPORTS",
    "BYTE_ORDERS",
    "WORD_ORDERS",
    "DEFAULT_PROFILES",
    "store_path",
    "set_store_path",
    "default_store",
    "new_profile_id",
    "normalize_register",
    "normalize_profile",
    "validate_profile",
    "load_store",
    "reload",
    "save_store",
    "ensure_store_file",
    "profiles",
    "get_profile",
    "selected_id",
    "set_selected",
    "selected_profile",
    "upsert_profile",
    "delete_profile",
    "duplicate_profile",
    "profile_to_json",
    "parse_profiles",
    "import_profiles",
]
