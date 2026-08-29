# -*- coding: utf-8 -*-
"""一次性离线脚本：把开源模拟器 Meter698-45Simulator-master/config.ini 的档案
迁移为项目数据种子 meter_sim_data.json。

用法（项目根）：python scripts/gen_meter_sim_data.py
不打包进 exe。
"""
import configparser
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_INI = os.path.join(ROOT, "Meter698-45Simulator-master", "config.ini")
DST_JSON = os.path.join(ROOT, "meter_sim_data.json")


def parse_key(key: str):
    """返回 (oi, attr, idx, frozen)。冻结键形如 50040200_20210200。"""
    if "_" in key:
        frozen_part, orig = key.split("_", 1)
        # frozen_part = 冻结OAD(8 hex)，orig = 原 OAD(8 hex)
        return (orig[0:4], orig[4:6], orig[6:8], frozen_part[0:4])
    return (key[0:4], key[4:6], key[6:8], None)


def main():
    conf = configparser.ConfigParser()
    conf.read(SRC_INI, encoding="utf-8")
    items = []
    for key, raw in conf.items("MeterData"):
        parts = raw.split()
        if len(parts) < 2:
            print(f"跳过无数据项: {key}")
            continue
        name = " ".join(parts[:-1])
        data = parts[-1].strip()
        oi, attr, idx, frozen = parse_key(key)
        items.append({
            "key": key,
            "oi": oi,
            "attr": attr,
            "idx": idx,
            "frozen": frozen,
            "name": name,
            "data": data,
        })
    out = {"version": 1, "items": items}
    with open(DST_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"生成 {DST_JSON}: {len(items)} 条")
    # 抽查
    for spot in ("00000200", "20000200", "10100200", "50040200_20210200", "40000200"):
        m = [it for it in items if it["key"] == spot]
        if m:
            it = m[0]
            print(f"  抽查 {spot}: {it['name']} | {it['data'][:40]}{'...' if len(it['data'])>40 else ''}")


if __name__ == "__main__":
    sys.exit(main())
