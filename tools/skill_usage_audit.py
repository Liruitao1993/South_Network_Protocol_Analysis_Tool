#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能(SKILL)使用情况审计工具
================================
pi 不记录技能加载遥测，但技能每次被调用都会在会话 JSONL 中留下
读取 ``<技能名>/SKILL.md`` 的痕迹（read 工具参数 / 正文中的 skills 路径引用）。
本脚本：

1. 收集三个技能根目录下的所有技能：
   - 用户全局:  ~/.agents/skills   （C:/Users/<u>/.agents/skills，198 个）
   - pi 用户:   ~/.pi/agent/skills
   - 项目级:    <repo>/.agents/skills
2. 扫描 ~/.pi/agent/sessions/**/*.jsonl 全部历史会话，统计每个技能的
   「SKILL.md 被读取次数」与「技能名被提及次数」。
3. 输出报告：已使用 / 从未使用（含 -2/-3 重复副本识别）。
4. --archive 把从未使用的技能移动到 skills/_unused_archive/<日期>/ 而非删除，
   可随时找回；--delete 才真正删除（默认 dry-run，不动文件）。

用法：
    python tools/skill_usage_audit.py                # 只出报告
    python tools/skill_usage_audit.py --archive      # 归档未使用(移动)
    python tools/skill_usage_audit.py --delete       # 彻底删除未使用
    python tools/skill_usage_audit.py --min-use 1    # 读次数<1 视为未使用(默认)
    python tools/skill_usage_audit.py --scope user   # 只审计 ~/.agents/skills
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
SKILL_ROOTS = {
    "user-agents": HOME / ".agents" / "skills",
    "pi-user":     HOME / ".pi" / "agent" / "skills",
}
SESSIONS_DIR = HOME / ".pi" / "agent" / "sessions"
# 备份根：必须在 skills 扫描目录【之外】。pi 启动扫描 ~/.agents/skills/ 与
# ~/.pi/agent/skills/ 下的 <name>/SKILL.md 注入上下文；移到 ~/.agents/skill_archive/
# （与 skills/ 同级、不同名）后不再被发现，上下文立即不再加载，且随时可移回恢复。
ARCHIVE_ROOT = HOME / ".agents" / "skill_archive"

# 技能名规范：小写字母数字、连字符
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")
# 会话里技能文件/路径引用：skills/<name>/SKILL.md 或 skills/<name>
SKILL_PATH_RE = re.compile(r"skills[\\/]+([A-Za-z0-9_.\-]+?)(?:[\\/]+SKILL\.md)?(?=[\\/\s\"',\]})]|$)", re.IGNORECASE)
SKILL_MD_RE = re.compile(r"[\\/]([A-Za-z0-9_.\-]+?)[\\/]+SKILL\.md", re.IGNORECASE)


def discover_skills(extra_project: Path = None):
    """返回 {skill_dir: (scope, name)}。name 为目录名。

    自动探测脚本所在项目根（tools/ 的上一级）的 .agents/skills，
    避免从不同 shell/不同 CWD 调用时项目根解析不到（如 WSL 下 /mnt/e 路径
    在 Windows Python 中不可用）。
    """
    roots = dict(SKILL_ROOTS)
    auto_project = Path(__file__).resolve().parent.parent
    cand = [extra_project] if extra_project else []
    cand.append(auto_project)
    for proj in cand:
        if proj is None:
            continue
        pj = proj / ".agents" / "skills"
        if pj.is_dir():
            roots.setdefault("project", pj)
    out = {}
    for scope, root in roots.items():
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                out[child.resolve()] = (scope, child.name)
    return out


def base_name(name: str) -> str:
    """autoplan-2 -> autoplan；grill-me-3 -> grill-me（去掉 -数字 副本后缀）。"""
    return re.sub(r"-\d+$", "", name)


def scan_sessions():
    """统计每个技能名在会话中的使用痕迹。

    两类信号：
    - reads:    SKILL.md 被 read 工具读取（最直接的技能加载证据）
    - mentions: 技能名（去 -N 副本后缀的基名）在会话中整词出现，含钩子自动注入
      的技能列表、斜杠命令、工作流状态提示等——这类技能（如 trellis-*）由框架
      自动激活，不会产生 read SKILL.md 调用。用整词边界并要求名称含连字符，
      避免普通单词（review/qa/path 等）误判。
    """
    reads = Counter()
    mentions = Counter()
    files = 0
    if not SESSIONS_DIR.is_dir():
        return reads, mentions, 0
    for jf in SESSIONS_DIR.rglob("*.jsonl"):
        files += 1
        try:
            text = jf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in SKILL_MD_RE.finditer(text):
            reads[m.group(1)] += 1
        for m in SKILL_PATH_RE.finditer(text):
            mentions[m.group(1)] += 1
        # 技能名整词出现（钩子注入列表/斜杠命令），仅统计含连字符的小写名
        token_re = re.compile(
            r"(?<![A-Za-z0-9_\-])([a-z][a-z0-9]*-[a-z0-9][a-z0-9_\-]*)(?![A-Za-z0-9_\-])")
        for m in token_re.finditer(text):
            mentions[m.group(1)] += 1
    return reads, mentions, files


def name_blob_count(blob: str, name: str) -> int:
    """技能名在整段会话文本中整词出现次数（含无连字符的通用名，调用方先去重）。"""
    pat = re.compile(r"(?<![A-Za-z0-9_\-])" + re.escape(base_name(name))
                     + r"(?![A-Za-z0-9_\-])")
    return len(pat.findall(blob))


def usage_for(name: str, reads: Counter, mentions: Counter):
    """合并 精确名 + 去副本后缀的基名 的计数（autoplan-2 与 autoplan 视为同一技能）。"""
    r = reads.get(name, 0) + reads.get(base_name(name), 0)
    m = mentions.get(name, 0) + mentions.get(base_name(name), 0)
    return r, m


def main():
    ap = argparse.ArgumentParser(description="技能使用情况审计")
    ap.add_argument("--project", default=".", help="项目根（用于项目级 .agents/skills）")
    ap.add_argument("--scope", choices=["all", "user", "pi", "project"], default="all")
    ap.add_argument("--min-use", type=int, default=1, help="读取次数<该值视为未使用")
    ap.add_argument("--archive", action="store_true", help="移动未使用技能到 skills 目录外的备份(不加载、可恢复)")
    ap.add_argument("--delete", action="store_true", help="彻底删除未使用技能（危险）")
    ap.add_argument("--only-duplicates", action="store_true", help="仅处理 -N 重复副本")
    ap.add_argument("--include-project", action="store_true",
                    help="允许移动项目级 .agents/skills 技能（默认不动，它们随 git 共享、多为工作流核心）")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    skills = discover_skills(project)
    reads, mentions, nfiles = scan_sessions()

    # 过滤 scope
    if args.scope == "user":
        skills = {k: v for k, v in skills.items() if v[0] == "user-agents"}
    elif args.scope == "pi":
        skills = {k: v for k, v in skills.items() if v[0] == "pi-user"}
    elif args.scope == "project":
        skills = {k: v for k, v in skills.items() if v[0] == "project"}

    used, unused = [], []
    for path, (scope, name) in sorted(skills.items(), key=lambda kv: (kv[1][0], kv[1][1])):
        r, m = usage_for(name, reads, mentions)
        dup = bool(re.search(r"-\d+$", name))
        rec = (name, scope, r, m, dup, path)
        # 使用判据：SKILL.md 被读取，或技能名在会话中被引用（自动注入类技能）
        (used if (r >= args.min_use or m >= args.min_use) else unused).append(rec)

    # 项目级技能默认保护（随 git 共享、trellis 工作流核心），不参与归档/删除
    protected = [rec for rec in unused if rec[1] == "project" and not args.include_project]
    if protected:
        unused = [rec for rec in unused if not (rec[1] == "project" and not args.include_project)]

    print("=" * 72)
    print(f"技能使用审计  |  会话文件 {nfiles} 个  |  技能总数 {len(skills)}")
    print("=" * 72)
    print(f"\n【已使用】{len(used)} 个（SKILL.md 读取次数 ≥ {args.min_use}）：")
    print(f"  {'读取':>4} {'提及':>5}  {'作用域':<12} 技能名")
    for name, scope, r, m, dup, path in sorted(used, key=lambda x: -x[2]):
        flag = "  (重复副本)" if dup else ""
        print(f"  {r:>4} {m:>5}  {scope:<12} {name}{flag}")

    print(f"\n【从未使用】{len(unused)} 个（可清理）：")
    print(f"  {'作用域':<12} 技能名")
    for name, scope, r, m, dup, path in unused:
        flag = "  (重复副本 -N)" if dup else ""
        print(f"  {scope:<12} {name}{flag}")

    if protected:
        print(f"\n【保护】{len(protected)} 个项目级技能未动（加 --include-project 才处理）：")
        for name, scope, r, m, dup, path in protected:
            print(f"  {scope:<12} {name}")

    if args.only_duplicates:
        unused = [rec for rec in unused if rec[4]]
        print(f"\n--only-duplicates：仅处理 {len(unused)} 个 -N 重复副本")

    if not (args.archive or args.delete):
        print("\n[dry-run] 未改动文件。加 --archive 移出扫描目录(不再加载上下文)，或 --delete 彻底删除。")
        return

    action = "删除" if args.delete else "归档(移出上下文)"
    dest_root = None
    manifest = []
    if args.archive:
        sub = "duplicates" if args.only_duplicates else "unused"
        dest_root = ARCHIVE_ROOT / datetime.date.today().isoformat() / sub
        dest_root.mkdir(parents=True, exist_ok=True)

    print(f"\n开始{action} {len(unused)} 个未使用技能……")
    for name, scope, r, m, dup, path in unused:
        try:
            if args.delete:
                shutil.rmtree(path)
                print(f"  [删除] {scope}/{name}")
            else:
                dest = dest_root / f"{scope}__{name}"
                shutil.move(str(path), str(dest))
                manifest.append({"scope": scope, "name": name,
                                 "from": str(path), "to": str(dest)})
                print(f"  [移出] {scope}/{name}")
        except Exception as e:
            print(f"  [失败] {scope}/{name}: {e}")
    if args.archive and manifest:
        import json as _json
        mf = dest_root / "MANIFEST.json"
        _json.dump(manifest, io_open(mf), ensure_ascii=False, indent=2)
        print(f"\n已移出 {len(manifest)} 个技能到：{dest_root}")
        print("这些技能不再被 pi 扫描/注入上下文。恢复方法：把对应目录移回原 skills 根即可")
        print(f"（原路径见 {mf}）。")


def io_open(p):
    import io
    return io.open(p, "w", encoding="utf-8")


if __name__ == "__main__":
    main()
