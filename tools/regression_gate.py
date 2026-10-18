#!/usr/bin/env python
"""重构回归闸门：把 `test/` 下全部独立验证脚本跑一遍，落成**可比对的机器可读基线**。

## 为什么需要它

`release_check.py` 已经有权威测试清单（`CORE_TESTS` / `GUI_TESTS`）和 `run_test_script()`，
但它只往控制台打 PASS/FAIL，**不落盘、不可比对**。做代码搬迁 / 目录重构时，
"我确认没破坏东西"必须是可证明的：

    改前跑一次 → 存档基线A ； 改完再跑一次 → 存档B ； A vs B 逐项比对

只要 A 与 B 每个测试的通过/失败状态完全一致，就是零回归的**证据**，而不是口头保证。
本脚本只做这一件事，不重复实现测试逻辑。

## 与 release_check.py 的关系（刻意的分工）

- **测试清单**：直接 `from release_check import CORE_TESTS, GUI_TESTS`，**不复制**。
  单一来源，避免"改了一处漏了另一处"。
- **子进程参数**：与 `release_check.run_test_script()` 完全一致（cwd=项目根、
  `PYTHONIOENCODING=utf-8`、`text=True`、`errors="replace"`、同样的超时口径），
  保证两边跑出来的成败口径相同。本脚本额外多采集 rc / 耗时 / 文件哈希 / 输出尾部。

`release_check.py` 本轮**不做任何修改**（它是发布流程的一环，不为此承担风险）。

## 用法

    # 1) 改动前：采基线
    python tools/regression_gate.py --label phase0-before

    # 2) 改动后：采一次
    python tools/regression_gate.py --label phase0-after

    # 3) 比对（有回归则退出码 1）
    python tools/regression_gate.py --compare tools/reports/phase0-before.json \
                                             tools/reports/phase0-after.json

    # 只跑 release_check 的权威清单（快）
    python tools/regression_gate.py --scope listed --label quick

默认 `--scope all`：跑 `test/test_*.py` 全部脚本（约 186 个）。范围更大 = 更能发现
"清单外测试被搬坏"，代价是耗时。

## 附带的副作用检测

跑测试期间若有测试**改动了受版本控制的文件**（历史上有 GUI 测试把 offscreen 几何写进
真实 `config.json`），基线会记录 `side_effects` 字段 —— 用它判断这批测试是否"干净"。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "test"
REPORT_DIR = Path(__file__).resolve().parent / "reports"

# 采集测试输出尾部时保留的行数 / 字符数（够定位失败原因，又不把报告撑爆）
TAIL_LINES = 4
TAIL_CHARS = 400
TAIL_LINE_CHARS = 160

# GBK 控制台容错：测试输出常含 ✓/★/⚠ 等非 GBK 字符
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# --------------------------------------------------------------------------- #
# 测试发现
# --------------------------------------------------------------------------- #
def discover_all() -> list[str]:
    """test/ 下全部 `test_*.py`（相对项目根的 posix 路径，已排序）。"""
    if not TEST_DIR.is_dir():
        return []
    names = sorted(
        f"test/{p.name}" for p in TEST_DIR.glob("test_*.py") if p.is_file()
    )
    return names


def load_listed() -> tuple[list[str], list[str]]:
    """从 release_check 取权威清单（去重、保序），并回报哪些不在磁盘上。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from release_check import CORE_TESTS, GUI_TESTS  # 单一来源，不复制

    listed = list(dict.fromkeys([*CORE_TESTS, *GUI_TESTS]))
    missing = [t for t in listed if not (ROOT / t).exists()]
    return [t for t in listed if t not in missing], missing


def resolve_scope(
    scope: str, only: list[str] | None = None
) -> tuple[list[str], list[str], list[str]]:
    """返回 (要跑的测试, release_check 清单里磁盘缺失的项, 清单外但磁盘存在的项)。

    `only` 是子串过滤器（如 `--only csg --only hdc10`）：只跑名字命中的测试，
    用于小改动后快速复跑。注意过滤后的基线**不可**与全量基线比对 ——
    compare 会把未跑的测试判为"丢失"并返回非 0，这是刻意的防误用。
    """
    all_tests = discover_all()
    listed, missing = load_listed()
    selected = all_tests if scope == "all" else listed
    if only:
        selected = [t for t in selected if any(tok.lower() in t.lower() for tok in only)]
    return selected, missing, [t for t in all_tests if t not in set(listed)]


# --------------------------------------------------------------------------- #
# 执行
# --------------------------------------------------------------------------- #
def file_sha1(rel: str) -> str:
    """测试脚本内容哈希：比对时判断"测试本身被改过"，避免把假一致当证据。"""
    try:
        return hashlib.sha1((ROOT / rel).read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


def _tail(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    lines = [ln[:TAIL_LINE_CHARS] for ln in lines[-TAIL_LINES:]]
    return " | ".join(lines)[:TAIL_CHARS]


def run_one(rel: str, timeout: int) -> dict:
    """跑单个测试脚本。子进程参数与 release_check.run_test_script 保持一致。"""
    path = ROOT / rel
    started = time.perf_counter()
    rec = {
        "name": rel,
        "sha1": file_sha1(rel),
        "status": "FAIL",
        "ok": False,
        "rc": None,
        "duration_s": 0.0,
        "tail": "",
    }
    if not path.exists():
        rec["tail"] = "文件不存在"
        return rec

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        rec["status"] = "TIMEOUT"
        rec["tail"] = f"超时 {timeout}s"
        rec["duration_s"] = round(time.perf_counter() - started, 2)
        return rec
    except Exception as exc:  # noqa: BLE001 - 任何启动失败都记为 FAIL 并留痕
        rec["tail"] = f"启动失败: {exc}"
        rec["duration_s"] = round(time.perf_counter() - started, 2)
        return rec

    rec["rc"] = p.returncode
    rec["duration_s"] = round(time.perf_counter() - started, 2)
    if p.returncode == 0:
        rec["status"] = "PASS"
        rec["ok"] = True
    else:
        rec["tail"] = _tail(p.stderr) or _tail(p.stdout) or f"exit={p.returncode}"
    return rec


def git_info() -> dict:
    """当前 HEAD 与工作区状态（基线必须能对应到一个确切的代码版本）。"""
    def _git(*args: str) -> str:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            return out.stdout.strip()
        except Exception:  # noqa: BLE001 - 无 git 也不该让闸门崩
            return ""

    return {
        "head": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty_files": len([ln for ln in _git("status", "--porcelain").splitlines() if ln]),
    }


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def summarize(records: list[dict], duration_s: float) -> dict:
    counts = {"PASS": 0, "FAIL": 0, "TIMEOUT": 0}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "total": len(records),
        "passed": counts["PASS"],
        "failed": counts["FAIL"],
        "timeout": counts["TIMEOUT"],
        "duration_s": round(duration_s, 1),
    }


def write_report(report: dict, label: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "-", label).strip("-") or "run"
    path = REPORT_DIR / f"{ts}_{safe}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def capture(label: str, scope: str, timeout: int, only: list[str] | None = None) -> int:
    tests, missing, unlisted = resolve_scope(scope, only)
    print(f"回归闸门 @ {ROOT}")
    print(f"  范围 scope={scope}  测试数={len(tests)}  单项超时={timeout}s")
    if only:
        print(f"  过滤器 only={only}（结果不可与全量基线比对）")
    if missing:
        print(f"  [注意] release_check 清单中磁盘缺失 {len(missing)} 项（不计入本次范围）")
    if unlisted:
        print(f"  [注意] 清单未收录但磁盘存在 {len(unlisted)} 项（已按 scope 处理）")

    tree_before = git_info()
    started = time.perf_counter()
    records: list[dict] = []
    for i, rel in enumerate(tests, 1):
        rec = run_one(rel, timeout)
        records.append(rec)
        flag = {"PASS": "PASS", "FAIL": "FAIL", "TIMEOUT": "TIME"}[rec["status"]]
        extra = "" if rec["status"] == "PASS" else f" :: {rec['tail'][:120]}"
        print(f"  [{i:3d}/{len(tests)}] [{flag}] {rec['duration_s']:6.1f}s {rel}{extra}")
    duration = time.perf_counter() - started

    tree_after = git_info()
    dirty_delta = tree_after["dirty_files"] - tree_before["dirty_files"]

    report = {
        "schema": 2,
        "label": label,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": scope,
        "only": only or [],
        "timeout_s": timeout,
        "repo": {
            "root": str(ROOT),
            "head": tree_before["head"],
            "branch": tree_before["branch"],
            # 采集开始时的未提交改动数：对比两份基线时应一致，否则不是同一前提
            "dirty_files_before": tree_before["dirty_files"],
        },
        "env": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "summary": summarize(records, duration),
        "preexisting_failures": sorted(
            r["name"] for r in records if not r["ok"]
        ),
        "side_effects": {
            "dirty_files_before": tree_before["dirty_files"],
            "dirty_files_after": tree_after["dirty_files"],
            "delta": dirty_delta,
        },
        "tests": records,
    }
    path = write_report(report, label)

    s = report["summary"]
    print()
    print(f"结果: PASS={s['passed']}  FAIL={s['failed']}  TIMEOUT={s['timeout']}"
          f"  用时 {s['duration_s']}s")
    if dirty_delta:
        print(f"[警告] 本次运行改动了 {dirty_delta} 个受版本控制的文件"
              f"（{tree_before['dirty_files']} → {tree_after['dirty_files']}）"
              f"——请核对 side_effects，测试本该不污染工作区")
    print(f"基线已写入: {path}")
    return 1 if (s["failed"] or s["timeout"]) else 0


# --------------------------------------------------------------------------- #
# 比对
# --------------------------------------------------------------------------- #
def compare(a_path: str, b_path: str) -> int:
    a = json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(b_path).read_text(encoding="utf-8"))
    ta = {t["name"]: t for t in a["tests"]}
    tb = {t["name"]: t for t in b["tests"]}

    print(f"A（改动前）: {a_path}")
    print(f"   标号={a['label']}  HEAD={a['repo']['head'][:10]}  "
          f"PASS={a['summary']['passed']} FAIL={a['summary']['failed']} "
          f"TIMEOUT={a['summary']['timeout']}")
    print(f"B（改动后）: {b_path}")
    print(f"   标号={b['label']}  HEAD={b['repo']['head'][:10]}  "
          f"PASS={b['summary']['passed']} FAIL={b['summary']['failed']} "
          f"TIMEOUT={b['summary']['timeout']}")
    print()

    regressions, fixed, disappeared, appeared, changed_source = [], [], [], [], []
    for name, rb in sorted(tb.items()):
        ra = ta.get(name)
        if ra is None:
            appeared.append(name)
            continue
        if not ra["ok"] and rb["ok"]:
            fixed.append(name)
        elif ra["ok"] and not rb["ok"]:
            regressions.append((name, rb["status"], rb["tail"]))
        if ra["sha1"] != rb["sha1"]:
            changed_source.append(name)
    for name in sorted(ta):
        if name not in tb:
            disappeared.append(name)

    verdict_ok = True

    print("== 回归（改动前通过 → 改动后失败）==")
    if regressions:
        verdict_ok = False
        for name, status, tail in regressions:
            print(f"  [回归] {name}  ({status})")
            if tail:
                print(f"         {tail[:220]}")
    else:
        print("  无")

    print("== 从本轮范围消失的测试 ==")
    if disappeared:
        verdict_ok = False
        for name in disappeared:
            print(f"  [丢失] {name}")
    else:
        print("  无")

    print("== 新增进范围的测试 ==")
    print("  " + (", ".join(appeared) if appeared else "无"))

    print("== 改动前失败、改动后恢复 ==")
    print("  " + (", ".join(fixed) if fixed else "无"))

    print("== 两次运行仍在失败的测试（未修复，属既有问题）==")
    still = sorted(n for n in ta if n in tb and not ta[n]["ok"] and not tb[n]["ok"])
    print(f"  共 {len(still)} 项" + ("：" if still else ""))
    for n in still:
        print(f"  - {n}")

    print("== 测试脚本自身内容发生变化（比对前提被动摇）==")
    if changed_source:
        print(f"  共 {len(changed_source)} 项，请确认这些改动是有意的：")
        for n in changed_source:
            print(f"  - {n}")
    else:
        print("  无（两次运行基于同一批测试脚本）")

    print()
    if not verdict_ok:
        print("结论: 存在回归或测试丢失 —— 不允许通过")
        return 1
    print("结论: 无回归（前后每个测试的成败状态完全一致）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="重构回归闸门：采集 / 比对测试基线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--label", default="run", help="基线标号（写入报告文件名）")
    ap.add_argument(
        "--scope",
        choices=["all", "listed"],
        default="all",
        help="all=test/ 下全部脚本（默认）；listed=只用 release_check 权威清单",
    )
    ap.add_argument("--timeout", type=int, default=300, help="单个测试超时秒数")
    ap.add_argument(
        "--only",
        action="append",
        metavar="子串",
        help="只跑名字含该子串的测试（可重复）。结果不可与全量基线比对",
    )
    ap.add_argument(
        "--compare",
        nargs=2,
        metavar=("基线A", "基线B"),
        help="比对两份基线报告（A=改动前, B=改动后）",
    )
    args = ap.parse_args(argv)

    if args.compare:
        return compare(args.compare[0], args.compare[1])
    return capture(args.label, args.scope, args.timeout, args.only)


if __name__ == "__main__":
    sys.exit(main())
