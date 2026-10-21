# -*- coding: utf-8 -*-
"""诊断包：把排障所需信息打成一个 zip（纯逻辑、无 Qt）。

用户报「解析不对 / 连不上 / 升级失败」时，最耗时的是来回索要：版本、配置、日志、系统信息。
本模块一键收集成一个 zip，**配置里的密钥类字段会脱敏**，不收集报文内容与用户文件。

内容结构::

    南网解析诊断包_说明.txt      ← 采集范围与脱敏声明
    环境信息.json                ← 版本 / 构建日期 / Python / 系统 / 是否打包
    配置/config.json             ← 已脱敏
    配置/<其他配置文件>.json      ← 已脱敏（存在才收）
    日志/<原文件名>.tail.txt      ← 最近 5 个日志的尾部（单文件截断）

设计约束：
- 任何单个文件失败都**只跳过不抛**（诊断包不能因为少一个配置就生成失败）；
- 总大小有上限（默认 5 MB），超了先砍日志；
- 不接受任意目录遍历：只读固定的配置名与 ``Output/`` 下的日志。
"""

from __future__ import annotations

import json
import os
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

#: 键名里出现这些片段即视为敏感值（大小写不敏感）
SECRET_HINTS = ("api_key", "apikey", "api-key", "token", "secret", "password",
                "passwd", "cookie", "authorization", "access_key")

#: 默认收集的配置文件名（都存在 app_data_dir 下）
DEFAULT_CONFIG_NAMES = ("config.json", "serial_tool_config.json",
                        "production_testbench.json", "dlt698_upgrade_config.json",
                        "bluetooth_tool_config.json")

MAX_LOGS = 5
MAX_LOG_BYTES = 200_000
MAX_TOTAL_BYTES = 5_000_000
REDACTED = "***已脱敏***"


def _is_secret_key(key: object) -> bool:
    text = str(key).lower()
    return any(hint in text for hint in SECRET_HINTS)


def redact(obj: Any) -> Any:
    """递归脱敏：字典里键名命中敏感词的 value 直接替换，不保留长度/前缀。"""
    if isinstance(obj, Mapping):
        return {k: (REDACTED if _is_secret_key(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def environment_info(app_version: str, build_date: str = "",
                     extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """采集环境信息（不含用户名/主机名等可识别个人的字段）。"""
    info: Dict[str, Any] = {
        "采集时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "软件版本": app_version,
        "编译日期": build_date,
        "Python": sys.version.split()[0],
        "操作系统": f"{platform.system()} {platform.release()} ({platform.version()})",
        "架构": platform.machine(),
        "是否打包": bool(getattr(sys, "frozen", False)),
        "可执行文件": sys.executable if getattr(sys, "frozen", False) else "",
        "工作目录": os.getcwd(),
    }
    try:
        import PySide6  # noqa: F401  (仅取版本，失败不影响诊断包)

        from PySide6 import __version__ as pyside_version
        info["PySide6"] = pyside_version
    except Exception:  # noqa: BLE001 - 诊断信息缺失不致命
        info["PySide6"] = "（未安装或版本未知）"
    for name in ("pyserial", "crcmod", "openpyxl"):
        try:
            module = __import__(name)
            info[name] = getattr(module, "__version__", "已安装")
        except Exception:  # noqa: BLE001
            info[name] = "未安装"
    if extra:
        for key, value in extra.items():
            info[str(key)] = value
    return info


def _tail_bytes(path: Path, limit: int) -> bytes:
    """读文件尾部最多 ``limit`` 字节（避免把几十 MB 日志塞进诊断包）。"""
    size = path.stat().st_size
    with open(path, "rb") as fh:
        if size > limit:
            fh.seek(size - limit)
        return fh.read(limit)


def _recent_logs(log_dir: Path, limit: int, pattern: str = "*.txt") -> List[Path]:
    if not log_dir.is_dir():
        return []
    files: List[Tuple[float, Path]] = []
    for path in log_dir.glob(pattern):
        try:
            files.append((path.stat().st_mtime, path))
        except OSError:
            continue
    files.sort(key=lambda item: item[0], reverse=True)
    return [p for _mtime, p in files[:max(0, limit)]]


def _recent_logs_multi(base: Path, specs: Iterable[Tuple[str, str]],
                       limit: int) -> List[Path]:
    """跨多个目录/通配符收集最近的日志（按 mtime 统一排序）。"""
    files: List[Tuple[float, Path]] = []
    for sub, pattern in specs:
        directory = base / sub
        if not directory.is_dir():
            continue
        for path in directory.glob(pattern):
            try:
                files.append((path.stat().st_mtime, path))
            except OSError:
                continue
    files.sort(key=lambda item: item[0], reverse=True)
    return [p for _mtime, p in files[:max(0, limit)]]


def build_diagnostics(out_zip: Path | str, data_dir: Path | str,
                      app_version: str, build_date: str = "",
                      extra: Optional[Mapping[str, Any]] = None,
                      config_names: Iterable[str] = DEFAULT_CONFIG_NAMES,
                      log_dir_name: str = "Output",
                      max_logs: int = MAX_LOGS,
                      max_log_bytes: int = MAX_LOG_BYTES,
                      max_total_bytes: int = MAX_TOTAL_BYTES) -> Dict[str, Any]:
    """生成诊断包，返回 ``{"path", "included", "skipped", "bytes"}``。

    不抛异常（除磁盘写失败）：缺配置、坏 JSON、日志目录不存在都只是少收文件。
    """
    target = Path(out_zip)
    target.parent.mkdir(parents=True, exist_ok=True)
    base = Path(data_dir)
    included: List[str] = []
    skipped: List[str] = []
    written = 0

    readme = (
        "南网协议解析工具 · 诊断包\n"
        "==========================\n\n"
        "本包由软件「帮助 → 生成诊断包」自动生成，用于排查问题。\n\n"
        "包含：\n"
        "  1. 环境信息.json —— 软件版本 / 编译日期 / Python / 系统信息\n"
        "  2. 配置/ —— 各配置文件（API Key、Token 等敏感字段已替换为「***已脱敏***」）\n"
        "  3. 日志/ —— 最近若干日志的末尾片段（单文件最多 200 KB）\n\n"
        "不包含：报文原文、表档案、导出文件、任何个人身份信息。\n"
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )

    try:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            data = readme.encode("utf-8")
            zf.writestr("南网解析诊断包_说明.txt", data)
            written += len(data)
            included.append("南网解析诊断包_说明.txt")

            env = json.dumps(environment_info(app_version, build_date, extra),
                             ensure_ascii=False, indent=2).encode("utf-8")
            zf.writestr("环境信息.json", env)
            written += len(env)
            included.append("环境信息.json")

            for name in config_names:
                path = base / name
                if not path.is_file():
                    skipped.append(name)
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    payload = json.dumps(redact(raw), ensure_ascii=False,
                                         indent=2).encode("utf-8")
                except (OSError, ValueError, UnicodeDecodeError):
                    try:                      # 坏 JSON 也收进去（原始文本），便于定位
                        payload = path.read_bytes()[:200_000]
                    except OSError:
                        skipped.append(name)
                        continue
                zf.writestr(f"配置/{name}", payload)
                written += len(payload)
                included.append(f"配置/{name}")

            log_specs = ((log_dir_name, "*.txt"), ("logs", "crash_*.log"))
            for path in _recent_logs_multi(base, log_specs, max_logs):
                if written >= max_total_bytes:
                    skipped.append(f"日志/{path.name}（超出总大小上限）")
                    continue
                try:
                    tail = _tail_bytes(path, max_log_bytes)
                except OSError:
                    skipped.append(f"日志/{path.name}")
                    continue
                if written + len(tail) > max_total_bytes:
                    # 单个日志就可能撑爆上限：直接跳过（不要写进去再超）
                    skipped.append(f"日志/{path.name}（超出总大小上限）")
                    continue
                zf.writestr(f"日志/{path.name}.tail.txt", tail)
                written += len(tail)
                included.append(f"日志/{path.name}.tail.txt")
    except OSError:
        raise
    return {
        "path": str(target),
        "included": included,
        "skipped": skipped,
        "bytes": target.stat().st_size if target.exists() else 0,
    }


__all__ = ["SECRET_HINTS", "DEFAULT_CONFIG_NAMES", "REDACTED", "redact",
           "environment_info", "build_diagnostics", "MAX_LOGS", "MAX_LOG_BYTES",
           "MAX_TOTAL_BYTES"]
