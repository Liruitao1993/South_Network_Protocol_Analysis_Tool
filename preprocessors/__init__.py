# -*- coding: utf-8 -*-
"""CLI 预处理脚本注册表

自动发现 preprocessors/ 目录下的所有预处理脚本。
每个脚本需定义 META dict 提供名称/描述/参数信息。
"""
import os
import json
import importlib.util
from typing import Dict, List, Any


def _discover_scripts() -> Dict[str, Dict[str, Any]]:
    """扫描 preprocessors/ 目录，加载每个脚本的 META 定义"""
    pkg_dir = os.path.dirname(__file__)
    scripts = {}
    for fname in os.listdir(pkg_dir):
        if fname.startswith("pp_") and fname.endswith(".py"):
            script_path = os.path.join(pkg_dir, fname)
            try:
                spec = importlib.util.spec_from_file_location(fname[:-3], script_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                meta = getattr(mod, "META", None)
                if meta and isinstance(meta, dict):
                    meta["script"] = script_path
                    meta["module"] = fname[:-3]
                    scripts[meta.get("id", fname)] = meta
            except Exception as e:
                print(f"[preprocessors] 加载 {fname} 失败: {e}")
    return scripts


# 全局注册表（惰性加载）
_registry = None


def get_registry() -> Dict[str, Dict[str, Any]]:
    """获取预处理脚本注册表（单例）"""
    global _registry
    if _registry is None:
        _registry = _discover_scripts()
    return _registry


def list_scripts() -> List[Dict[str, Any]]:
    """返回所有可用预处理脚本的列表（按 order 排序）"""
    reg = get_registry()
    items = sorted(reg.values(), key=lambda m: m.get("order", 99))
    return items


def get_script(script_id: str) -> Dict[str, Any]:
    """按 ID 获取脚本元信息"""
    return get_registry().get(script_id, {})
