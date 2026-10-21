# -*- coding: utf-8 -*-
"""P0 加固回归：原子写 / 升级回滚脚本 / 诊断包 / 主程序接线静态守卫。

对应 `docs/产品级优化评估-2026-10-20.md` 的 P0-1/2/4：

1. `atomic_io` —— 配置写入必须「要么完整、要么保持旧文件」，且失败不留临时文件
2. `auto_updater.UPDATE_BAT_TEMPLATE` —— 备份 / 大小校验 / 15 秒健康检查 / 回滚
3. `diagnostics` —— 一键诊断包：脱敏、截断、缺文件不失败
4. 静态守卫 —— main_gui 不再有非原子 config 写入；帮助菜单挂了诊断包入口

运行: python test/test_p0_hardening.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import atomic_io  # noqa: E402
from atomic_io import (atomic_write_bytes, atomic_write_json, atomic_write_text,  # noqa: E402
                       read_json)
from auto_updater import build_update_bat  # noqa: E402
from diagnostics import REDACTED, build_diagnostics, redact  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# ── 1. 原子写 ────────────────────────────────────────────────
def test_atomic_write_creates_and_overwrites():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sub" / "config.json"
        atomic_write_text(path, "第一版")
        assert path.read_text(encoding="utf-8") == "第一版"
        atomic_write_text(path, "第二版")
        assert path.read_text(encoding="utf-8") == "第二版"
        # 不残留临时文件
        leftovers = [p.name for p in path.parent.iterdir() if p.name != "config.json"]
        assert leftovers == [], leftovers


def test_atomic_write_failure_keeps_old_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text('{"old": 1}', encoding="utf-8")
        with patch.object(atomic_io.os, "replace", side_effect=OSError("locked")):
            try:
                atomic_write_json(path, {"new": 2}, retries=1, delay=0)
                assert False, "应当抛出 OSError"
            except OSError:
                pass
        # 旧内容完好，临时文件已清理
        assert json.loads(path.read_text(encoding="utf-8")) == {"old": 1}
        leftovers = [p.name for p in Path(tmp).iterdir() if p.name.startswith(".")]
        assert leftovers == [], leftovers


def test_atomic_write_json_roundtrip_unicode():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        payload = {"协议": "南网", "值": [1, 2, {"nested": "中文"}]}
        atomic_write_json(path, payload)
        assert json.loads(path.read_text(encoding="utf-8")) == payload
        # 与 json.dump(ensure_ascii=False) 口径一致：中文不转义
        assert "南网" in path.read_text(encoding="utf-8")


def test_atomic_write_binary_and_read_json_default():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "blob.bin"
        atomic_write_bytes(path, b"\x00\x01\xff")
        assert path.read_bytes() == b"\x00\x01\xff"
        assert read_json(Path(tmp) / "missing.json", default={"d": 1}) == {"d": 1}
        bad = Path(tmp) / "bad.json"
        bad.write_text("{ 坏", encoding="utf-8")
        assert read_json(bad, default=None) is None


# ── 2. 升级脚本兜底 ──────────────────────────────────────────
def test_update_bat_has_backup_verify_and_rollback():
    bat = build_update_bat(Path(r"C:\tmp\new.exe"), Path(r"D:\tools\app.exe"))
    # 旧断言仍要成立（轮询 / 复制 / 启动）
    assert "tasklist" in bat and "copy /y /b" in bat and 'start ""' in bat
    # 新兜底：备份、大小校验、健康检查、回滚
    assert "%OLD%.bak" in bat, "必须先把旧版备份成 .bak"
    assert "move /y" in bat, "备份要用移动（旧文件被占用时能立刻发现）"
    assert "SZ_NEW" in bat and "SZ_OLD" in bat, "覆盖后要比对文件大小"
    assert "ping 127.0.0.1 -n 16" in bat, "启动后要等 15 秒做健康检查"
    assert ":rollback" in bat and ":rb_move" in bat, "失败要回滚"
    assert "GEQ 10" in bat, "回滚删除要重试（文件可能仍被占用）"
    # 占位符全部替换
    for token in ("__NEW__", "__OLD__", "__IMG__"):
        assert token not in bat


def test_update_bat_rollback_restores_before_start():
    bat = build_update_bat(Path(r"C:\tmp\new.exe"), Path(r"C:\tools\app.exe"))
    rb = bat.split(":rollback", 1)[1]
    assert "move /y" in rb, "回滚必须先还原备份"
    assert 'start ""' in rb, "回滚后要重新启动旧版"


# ── 3. 诊断包 ────────────────────────────────────────────────
def test_diagnostics_redacts_secrets_and_collects():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "config.json").write_text(json.dumps({
            "llm": {"api_key": "sk-secret-value", "model": "gpt"},
            "feedback": {"token": "tk-123", "server_url": "http://x"},
            "window": {"w": 1280},
        }, ensure_ascii=False), encoding="utf-8")
        (base / "serial_tool_config.json").write_text(
            json.dumps({"password": "p@ss", "baud": 9600}), encoding="utf-8")
        (base / "Output").mkdir()
        (base / "Output" / "serial_log_1.txt").write_bytes(b"A" * 300_000)
        (base / "logs").mkdir()
        (base / "logs" / "crash_20261020_1.log").write_text("boom", encoding="utf-8")

        out = base / "diag.zip"
        res = build_diagnostics(out, base, "1.23.88", "2026-10-19")
        assert out.exists() and res["bytes"] > 0

        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
            cfg = zf.read("配置/config.json").decode("utf-8")
            env = json.loads(zf.read("环境信息.json").decode("utf-8"))
            log = zf.read("日志/serial_log_1.txt.tail.txt")

        assert "南网解析诊断包_说明.txt" in names
        assert "配置/config.json" in names and "配置/serial_tool_config.json" in names
        assert "sk-secret-value" not in cfg and "tk-123" not in cfg
        assert REDACTED in cfg
        assert '"model": "gpt"' in cfg, "非敏感字段必须保留原值"
        assert '"w": 1280' in cfg
        assert env["软件版本"] == "1.23.88"
        assert len(log) <= 200_000, len(log)
        assert "配置/dlt698_upgrade_config.json" not in names
        assert "日志/crash_20261020_1.log.tail.txt" in names, "崩溃日志也要收进诊断包"


def test_diagnostics_missing_files_are_skipped_not_fatal():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        out = base / "diag.zip"
        res = build_diagnostics(out, base, "1.0.0", config_names=("none.json",))
        assert out.exists()
        assert "none.json" in res["skipped"]


def test_diagnostics_total_size_cap_drops_logs():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "Output").mkdir()
        (base / "Output" / "big.txt").write_bytes(b"B" * 100_000)
        out = base / "diag.zip"
        res = build_diagnostics(out, base, "1.0.0", max_total_bytes=1000)
        assert any("总大小上限" in s for s in res["skipped"]), res["skipped"]


def test_redact_nested_structures():
    data = {"a": {"api_key": "x"}, "b": [{"token": "y"}, {"ok": 1}]}
    red = redact(data)
    assert red["a"]["api_key"] == REDACTED
    assert red["b"][0]["token"] == REDACTED
    assert red["b"][1]["ok"] == 1


# ── 4. 主程序静态守卫 ────────────────────────────────────────
def test_main_gui_uses_atomic_config_write():
    src = (ROOT / "main_gui.py").read_text(encoding="utf-8")
    assert "from atomic_io import atomic_write_json" in src
    assert "atomic_write_json(self._config_path, config)" in src
    # 旧的「先截断再 dump」写法必须清零
    assert "json.dump(config, f, ensure_ascii=False, indent=2)" not in src


def test_main_gui_has_diagnostics_entry():
    src = (ROOT / "main_gui.py").read_text(encoding="utf-8")
    assert "生成诊断包" in src
    assert "def _export_diagnostics" in src
    assert "build_diagnostics(" in src


#: 所有「应用状态」写入点：必须走 atomic_write_json，禁止直接 open(w)+json.dump
STATE_WRITERS = (
    "main_gui.py", "custom_di_store.py", "dlt645_di_lookup.py", "command_lookup.py",
    "obis_lookup.py", "preset_buttons.py", "archive_widget.py", "llm_api_manager.py",
    "llm_preprocess_widget.py", "frame_gen_widget.py", "meter_sim_widget.py",
)


def test_state_writers_use_atomic_io():
    missing = [name for name in STATE_WRITERS
               if "atomic_write_json" not in (ROOT / name).read_text(encoding="utf-8")]
    assert not missing, f"这些模块还在直接写 JSON：{missing}"
    still_direct = [name for name in STATE_WRITERS
                    if "json.dump(" in (ROOT / name).read_text(encoding="utf-8")]
    assert not still_direct, f"这些模块仍有非原子 json.dump：{still_direct}"


def test_diagnostics_module_is_qt_free():
    src = (ROOT / "diagnostics.py").read_text(encoding="utf-8")
    assert "PySide6" not in src.split("def environment_info")[0], "模块头部不应依赖 Qt"
    assert "zipfile" in src


def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
