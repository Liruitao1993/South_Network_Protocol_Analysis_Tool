# -*- coding: utf-8 -*-
"""打包后自检（``exe --self-test``）：不启动界面、不读配置、不写任何文件。

用途：**验证交付物本身**。PyInstaller 少了 hiddenimport 时，界面往往要到用户点开某个
页面才崩；这个入口在命令行就能把「全部解析器能导入 + 关键纯逻辑能跑」验一遍，
返回码 0 才算打包合格（CI / 发布前 / 用户报障时都可跑）。

检查项：
1. 12 个协议解析器全部可导入并实例化；
2. 校验器 / 组帧 / 原子写 / 诊断包 / 崩溃兜底模块可导入；
3. 生产测试架组帧逐字节等于现场样例（顺带验证字段表与校验实现）。
"""

from __future__ import annotations

import sys
from typing import List, Optional, TextIO


def run(stream: Optional[TextIO] = None) -> int:
    # 打包后从 GBK 控制台启动时，中文输出会乱码；统一转 UTF-8（失败不影响自检）
    for _name in ("stdout", "stderr"):
        _obj = getattr(sys, _name, None)
        try:
            if _obj is not None and hasattr(_obj, "reconfigure"):
                _obj.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    out = stream if stream is not None else sys.stdout
    problems: List[str] = []

    def _say(text: str) -> None:
        try:
            if out is not None:
                out.write(text + "\n")
                out.flush()
        except Exception:  # noqa: BLE001 - 打包后 stdout 可能为 None
            pass

    # 1) 解析器
    try:
        import parser_registry as reg

        keys = sorted(reg._PARSER_SPECS)
        for key in keys:
            try:
                reg.get_parser(key)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"解析器 {key} 不可用：{type(exc).__name__}: {exc}")
        _say(f"[self-test] 解析器：{len(keys)} 个已加载")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"parser_registry 导入失败：{type(exc).__name__}: {exc}")

    # 2) 关键模块
    for name in ("atomic_io", "diagnostics", "crash_handler", "production_testbench_core"):
        try:
            __import__(name)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name} 导入失败：{type(exc).__name__}: {exc}")

    # 3) 组帧黄金样例
    try:
        import production_testbench_core as core

        frame = core.build_bench_frame()
        actual = core.format_hex_field(frame)
        if actual != core.ORACLE_FRAME_HEX:
            problems.append(f"测试架组帧不一致：{actual[:32]}…")
        else:
            _say("[self-test] 测试架组帧：75 字节样例一致")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"组帧自检失败：{type(exc).__name__}: {exc}")

    if problems:
        for item in problems:
            _say("[self-test] FAIL " + item)
        return 1
    _say("[self-test] OK")
    return 0


__all__ = ["run"]
