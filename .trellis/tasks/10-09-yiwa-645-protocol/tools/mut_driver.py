"""变异反证驱动（任务级工具，随任务归档，不进仓库运行时）。

用法（项目根执行）::

    python .trellis/tasks/10-09-yiwa-645-protocol/tools/mut_driver.py [变异标签子串...]

对每个变异：备份原始字节 → 替换 → 跑测试 → 记录 PASS/FAIL → 还原 → 校验 sha256。
FAIL=0 表示**测试没锁住该逻辑**（假绿），必须补断言；再用变异确认断言真的会红。

⚠ **必须清 `__pycache__` 并禁写 pyc**（`PYTHONDONTWRITEBYTECODE=1`）：
pyc 失效判据是「源文件 mtime（整秒）+ 字节数」。本脚本在同一秒内反复「变异→还原」，
而变异前后字符串往往等长（实测 `d = MASK if invert else -MASK` 与
`d = -MASK if invert else MASK` 都是 33 字节）⇒ Python 会继续用上一次的旧字节码，
使变异「看起来未变红」或 FAIL 数偏小（实测 M6 脏 pyc 下 FAIL=1，清缓存后 FAIL=26）。
判据：某变异的 FAIL 数与「该逻辑涉及的断言条数」明显不相称时，先怀疑 pyc 陈旧。
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

# 本文件在 <repo>/.trellis/tasks/<task>/tools/ 下 ⇒ 项目根 = parents[4]
ROOT = pathlib.Path(__file__).resolve().parents[4]

# (标签, 目标文件, 原文(唯一), 替换为, 需要跑的测试[空格分隔])
MUTATIONS = [
    # ── 阶段 1/2：线格式 + 解析器 ───────────────────────────────────────
    (
        "M1 地址域改小端（字节反转）",
        "yw645_wire.py",
        "    return bcd_to_digits(raw)",
        "    return bcd_to_digits(bytes(reversed(raw)))",
        "test/test_yw645_wire.py test/test_yw645_parse.py",
    ),
    (
        "M2 CS 范围错（漏掉第一个 68H）",
        "yw645_parser.py",
        "        cs_expected = W.calc_cs(data[:cs_pos]) if cs_pos >= 0 else 0",
        "        cs_expected = W.calc_cs(data[1:cs_pos]) if cs_pos >= 0 else 0",
        "test/test_yw645_parse.py test/test_yw645_validator.py",
    ),
    (
        "M3 长度拼接丢高 4 位（只取 L）",
        "yw645_wire.py",
        "    return ((cmd & 0x0F) << 8) | (low & 0xFF)",
        "    return low & 0xFF",
        "test/test_yw645_wire.py test/test_yw645_parse.py",
    ),
    (
        "M4 行末偏移改开区间（去掉闭区间 -1）",
        "yw645_parser.py",
        "        payload_end = W.HEADER_LEN + len(payload) - 1 if payload else W.HEADER_LEN",
        "        payload_end = W.HEADER_LEN + len(payload) if payload else W.HEADER_LEN",
        "test/test_yw645_parse.py test/test_yw645_validator.py",
    ),
    (
        "M5 帧长不足时返回空表（违反容错铁律）",
        "yw645_parser.py",
        '        if len(data) < W.MIN_FRAME_LEN:\n'
        '            meta["structure_error"] = f"帧长不足（{len(data)} < {W.MIN_FRAME_LEN}）"\n'
        '            meta["errors"].append(meta["structure_error"])',
        '        if len(data) < W.MIN_FRAME_LEN:\n'
        '            meta["structure_error"] = f"帧长不足（{len(data)} < {W.MIN_FRAME_LEN}）"\n'
        '            meta["errors"].append(meta["structure_error"])\n'
        "            self.last_meta = meta\n"
        "            return []",
        "test/test_yw645_parse.py test/test_yw645_validator.py",
    ),
    (
        "M6 0x33 方向反转（接收端反而加）",
        "yw645_wire.py",
        "    d = MASK if invert else -MASK",
        "    d = -MASK if invert else MASK",
        "test/test_yw645_wire.py test/test_yw645_parse.py",
    ),
    # ── 阶段 4：组帧 + 预设 ───────────────────────────────────────
    (
        "P1 with_fl 推导反转（请求/返回搞反）",
        "yw645_frame_gen.py",
        "    if mode in _RESPONSE_MODES:\n        return True",
        "    if mode in _REQUEST_MODES:\n        return True",
        "test/test_yw645_frame_gen.py",
    ),
    (
        "P2 数据域 12bit 长度上限校验失效",
        "yw645_frame_gen.py",
        "    if len(payload) > W.MAX_DATA_LEN:",
        "    if False and len(payload) > W.MAX_DATA_LEN:",
        "test/test_yw645_frame_gen.py",
    ),
    (
        "P3 preset yw645 分支失效（兜底写 GW_command.json）",
        "preset_buttons.py",
        '    if protocol == "yw645":\r\n        return YW645_COMMAND_PATH',
        '    if protocol == "__yw645_off__":\r\n        return YW645_COMMAND_PATH',
        "test/test_yw645_frame_gen.py test/test_yw645_gui.py",
    ),
    (
        "P4 build_from_template 忽略模板 body（透传帧变空数据域）",
        "yw645_frame_gen.py",
        '    if item.get("body"):\n        kwargs.setdefault("body", item["body"])',
        '    if False and item.get("body"):\n        kwargs.setdefault("body", item["body"])',
        "test/test_yw645_frame_gen.py",
    ),
]


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def purge_pycache() -> None:
    for d in ROOT.rglob("__pycache__"):
        if d.is_dir():
            try:
                shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass


def run_tests(spec: str) -> tuple[int, int, str]:
    """返回 (pass 合计, fail 合计, 最后一行摘要)。每次运行前清 pyc + 禁写 pyc。"""
    total_p = total_f = 0
    last = ""
    env = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": os.environ.get("PATH", ""),
    }
    for t in spec.split():
        purge_pycache()
        cp = subprocess.run(
            [sys.executable, t], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env,
        )
        out = cp.stdout or ""
        line = next((ln for ln in reversed(out.splitlines()) if "结果:" in ln), "")
        if not line:
            # 没有汇总行 = 测试崩溃/中止（不是「未变红」）—— 按 1 个失败计，
            # 否则变异会把「把测试跑崩了」误报成「测试未锁住」。
            total_f += 1
            last = f"{t}: 无汇总行 rc={cp.returncode}（测试崩溃/中止）"
            continue
        last = line.strip()
        for part in line.replace("结果:", "").split():
            if part.startswith("PASS="):
                total_p += int(part[5:])
            elif part.startswith("FAIL="):
                total_f += int(part[5:])
    return total_p, total_f, last


def main(argv: list[str]) -> int:
    wanted = [m for m in MUTATIONS if not argv or any(a in m[0] for a in argv)]
    if not wanted:
        print(f"没有匹配的变异（共 {len(MUTATIONS)} 条）")
        return 2

    saved: dict[str, tuple[str, bytes]] = {}
    for rel in {m[1] for m in wanted}:
        p = ROOT / rel
        if not p.exists():
            print(f"!! 目标文件不存在：{rel}")
            return 2
        saved[rel] = (sha256(p), p.read_bytes())

    def apply_bytes(rel: str, text: str) -> None:
        """按原始字节写回——禁用换行翻译，否则 LF 会被写成 CRLF。"""
        (ROOT / rel).write_bytes(text.encode("utf-8"))

    print("=== 变异反证 ===")
    bad: list[str] = []
    for label, rel, old, new, spec in wanted:
        src = saved[rel][1].decode("utf-8")
        if old not in src:
            print(f"  [ANCHOR-MISS] {label} —— 锚点在 {rel} 中不存在，本变异无效")
            bad.append(label)
            continue
        if src.count(old) != 1:
            print(f"  [ANCHOR-AMBIG] {label} —— 锚点在 {rel} 中出现 {src.count(old)} 次")
            bad.append(label)
            continue
        apply_bytes(rel, src.replace(old, new))
        try:
            passed, failed, _ = run_tests(spec)
        finally:
            (ROOT / rel).write_bytes(saved[rel][1])
            if sha256(ROOT / rel) != saved[rel][0]:
                print(f"  [RESTORE-FAIL] {label} —— {rel} 还原后哈希不一致（中止）")
                return 3
        mark = "变红 ✓" if failed > 0 else "★ 未变红（测试未锁住）"
        print(f"  {label:44s} PASS={passed:<5} FAIL={failed:<5} {mark}")
        if failed == 0:
            bad.append(label)

    print("\n=== 还原核对 ===")
    all_ok = True
    for rel, (want, _raw) in sorted(saved.items()):
        got = sha256(ROOT / rel)
        ok = got == want
        all_ok &= ok
        print(f"  {rel:24s} sha256 {'一致 ✓' if ok else '不一致 ✗'}  {got[:16]}…")
    if bad:
        print(f"\n!! {len(bad)} 个变异未变红：{bad}")
    return 0 if (all_ok and not bad) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
