# -*- coding: utf-8 -*-
"""虚拟表档案数据：meter_sim_data.json 的加载/查询/增删改/保存。

数据项格式：
  {"key": "00100200", "oi": "0010", "attr": "02", "idx": "00",
   "frozen": null, "name": "正向有功电能", "data": "010506..."}
冻结档案 key = "50040200_20210200"（冻结OAD_原OAD），frozen 字段为冻结 OI（"5004"）。
"""
import json
import os
from typing import Dict, List, Optional

import app_paths

DATA_FILE = "meter_sim_data.json"


def _load_seed_path() -> Optional[str]:
    """开发模式/打包资源里的种子文件路径。"""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(here, DATA_FILE)
    return p if os.path.exists(p) else None


class Archive:
    """档案数据内存模型。items 为 list[dict]，_index 按 key 快速查找。"""

    def __init__(self, items: List[dict]):
        self.items: List[dict] = items
        self._index: Dict[str, dict] = {it["key"].lower(): it for it in items}

    # ── 查询 ──────────────────────────────────────────────
    def lookup(self, oi: str, attr: str = "02", idx: str = "00",
               frozen: Optional[str] = None) -> Optional[dict]:
        """按 OI/属性/索引查数据项。frozen 非空时查冻结档案（frozen OI 形如 '5004'）。

        冻结 key 规则：f'{frozen}0200_{oi}{attr}{idx}'（对齐开源命名）。
        """
        oi = oi.lower().replace("_", "")
        if frozen:
            key = f"{frozen.lower()}0200_{oi}{attr.lower()}{idx.lower()}"
        else:
            key = f"{oi}{attr.lower()}{idx.lower()}"
        return self._index.get(key)

    def lookup_key(self, key: str) -> Optional[dict]:
        return self._index.get(key.lower())

    # ── 增删改 ────────────────────────────────────────────
    @staticmethod
    def make_item(key: str, name: str, data: str) -> dict:
        key = key.lower().strip()
        if "_" in key:
            frozen_part, orig = key.split("_", 1)
            oi, attr, idx = orig[0:4], orig[4:6], orig[6:8]
            frozen = frozen_part[0:4]
        else:
            oi, attr, idx = key[0:4], key[4:6], key[6:8]
            frozen = None
        return {"key": key, "oi": oi, "attr": attr, "idx": idx,
                "frozen": frozen, "name": name.strip(), "data": data.strip()}

    def upsert(self, item: dict) -> None:
        key = item["key"].lower()
        if key in self._index:
            self._index[key].update(item)
        else:
            self.items.append(item)
            self._index[key] = item

    def remove(self, key: str) -> bool:
        key = key.lower()
        it = self._index.pop(key, None)
        if it is not None:
            self.items = [x for x in self.items if x["key"].lower() != key]
            return True
        return False

    # ── 持久化 ────────────────────────────────────────────
    def save(self) -> str:
        path = str(app_paths.data_path(DATA_FILE))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "items": self.items}, f,
                      ensure_ascii=False, indent=1)
        return path

    def to_json(self) -> str:
        return json.dumps({"version": 1, "items": self.items},
                          ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "Archive":
        obj = json.loads(text)
        items = obj.get("items", obj if isinstance(obj, list) else [])
        return cls(items)


def load_archive() -> Archive:
    """从 app_paths 数据目录加载档案；缺失时 ensure_data_file 复制种子。"""
    path = app_paths.ensure_data_file(DATA_FILE)
    with open(str(path), "r", encoding="utf-8") as f:
        obj = json.load(f)
    return Archive(obj.get("items", []))
