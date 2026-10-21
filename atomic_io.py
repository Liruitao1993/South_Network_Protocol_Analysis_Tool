# -*- coding: utf-8 -*-
"""原子写文件工具（纯标准库，无 Qt）。

为什么需要：`open(path, "w") + json.dump()` 在写入过程中崩溃 / 断电 / 被强杀时，
目标文件会留下**半截内容**。对 `config.json` 这类"启动就要读"的文件，后果是
用户所有设置（协议、串口、窗口布局、更新设置）直接丢失，且下次启动可能连窗口都开不出来。

做法：同目录写临时文件 → `flush + fsync` → `os.replace()` 原子替换。
- `os.replace` 在同一分区上是原子的（Windows 上底层是 MoveFileEx + REPLACE_EXISTING）；
- 失败时**旧文件保持原样**，临时文件清理掉；
- Windows 上目标文件可能被杀软 / 索引服务短暂占用 → 带几次退避重试。

本模块只依赖标准库，`main_gui`、`diagnostics` 与各配置模块都可以直接复用。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Union

PathLike = Union[str, Path]

#: os.replace 的重试次数与退避基数（Windows 文件占用多为毫秒级）
REPLACE_RETRIES = 4
REPLACE_DELAY = 0.05


def atomic_write_bytes(path: PathLike, data: bytes, *,
                       retries: int = REPLACE_RETRIES,
                       delay: float = REPLACE_DELAY) -> None:
    """把 ``data`` 原子写到 ``path``：要么写完整，要么保持旧文件不动。

    临时文件与目标同目录（跨分区 rename 不是原子操作），写完 fsync 再 replace。
    失败时抛原始异常，调用方可以决定提示方式；临时文件不会残留。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                    dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        last_error: Optional[OSError] = None
        for attempt in range(max(1, int(retries))):
            try:
                os.replace(tmp, target)
                return
            except OSError as exc:          # 目标被占用 / 权限不足：退避重试
                last_error = exc
                time.sleep(delay * (attempt + 1))
        raise last_error or OSError(f"无法替换目标文件：{target}")
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def atomic_write_text(path: PathLike, text: str, encoding: str = "utf-8", **kwargs) -> None:
    """文本版原子写（默认 UTF-8，不做换行转换）。"""
    atomic_write_bytes(path, str(text).encode(encoding), **kwargs)


def atomic_write_json(path: PathLike, obj: Any, *, indent: int = 2,
                      ensure_ascii: bool = False, **kwargs) -> None:
    """JSON 版原子写：与原先 `json.dump(..., ensure_ascii=False, indent=2)` 内容一致。"""
    payload = json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, payload, **kwargs)


def read_json(path: PathLike, default: Any = None) -> Any:
    """读 JSON；文件不存在 / 损坏 / 不是对象时返回 ``default``（不抛）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


__all__ = ["atomic_write_bytes", "atomic_write_text", "atomic_write_json",
           "read_json", "REPLACE_RETRIES", "REPLACE_DELAY"]
