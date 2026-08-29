# 小窗模式核验提交与后续开发 — 执行计划

## 前置

- 本机控制台 GBK：所有 Python 命令用 `PYTHONIOENCODING=utf-8 python -X utf8`。
- 目标：核验小窗现状 → 3 个主题提交 → 复验。

## 执行清单

### 1. 核验（对应 prd R1）

- [x] 1.1 py_compile 六个文件：
  ```bash
  PYTHONIOENCODING=utf-8 python -X utf8 -m py_compile \
    system_integration/quick_parse_panel.py system_integration/acrylic_effect.py \
    system_integration/global_hotkey.py system_integration/system_settings.py \
    test/test_quick_parse_panel.py main_gui.py
  ```
- [x] 1.2 跑小窗测试（offscreen，63 项断言）：
  ```bash
  PYTHONIOENCODING=utf-8 python -X utf8 test/test_quick_parse_panel.py
  ```
  - 记录断言数与退出码；fastfail(0xC0000409) 与历史注记一致则接受。
- [x] 1.3 集成点抽查：
  - grep main_gui.py：`QuickParsePanel(` 注入参数（clean/parse/validate/open_full/is_dark）、`_on_global_hotkey`、`quick_panel` 唤出路径
  - grep system_settings.py / global_hotkey.py：热键提示文案（Ctrl+Alt+X）
- [x] 1.4 若 1.2 失败或 1.3 发现断裂 → 修到全过，行为变更补 CHANGELOG 条目（此时才动代码，小修）。（核验全过，无需修改）

### 2. 提交（对应 prd R2/R3）

- [x] 2.0 提交前快照：`git status --short` + `git diff --stat`（确认无新增意外文件）
- [x] 2.1 Commit 1（小窗+系统集成）：→ b43460f
  ```bash
  git add system_integration/quick_parse_panel.py system_integration/acrylic_effect.py \
          system_integration/global_hotkey.py system_integration/system_settings.py \
          test/test_quick_parse_panel.py
  git commit -m "feat(quick-panel): 快捷解析小窗 1.17.0~1.18.1（双卡/毛玻璃/空态精简/高度保持）"
  ```
  - 提交后 `git status --short` 确认这 5 个文件不再出现。
- [x] 2.2 Commit 2（主程序+打包）：→ c24a3b3
  ```bash
  git add main_gui.py "南网协议解析工具.spec" AGENTS.md
  git commit -m "feat(main): 1.18.1 主程序集成（1.15.0~1.18.1 全部未提交功能入库）"
  ```
  - AGENTS.md：先 diff 检查 §10 是否已含 1.18.1，缺则补（版本/毛玻璃要点）再 add。
  - spec：确认 hiddenimports 已含 quick_parse_panel/acrylic_effect（含 proc_stats/thread_registry 若有引用）。
- [x] 2.3 Commit 3（其余功能）：→ a4bf623（49 文件）按 prd R2 清单 `git add` 剩余全部功能文件（逐个列出，不用通配符扫目录；monitor/ 用 `git add monitor/` 整目录确认只含功能文件）
  ```bash
  git commit -m "feat(misc): 虚拟表/状态栏统计/线程注册表/协议修复/Web 等 1.15~1.18 功能"
  ```
- [x] 2.4 排除项自检：`git status --short` 中不应出现 `_tmp_grep.txt`、`repomix-output.md`、`Meter698-45Simulator-master/`、`tools/`、`test/_probe_qp_cards.py` 的已跟踪状态。
- [x] 2.5 `git log --oneline -4` 检查 3 个提交消息与内容（`git show --stat` 抽查）。

### 3. 复验（对应 prd R4）

- [x] 3.1 复跑 `PYTHONIOENCODING=utf-8 python -X utf8 test/test_quick_parse_panel.py` 仍全过（2026-08-29：62 项断言全过，退出码 0，无 fastfail）
- [x] 3.2 `git status --short` 仅剩有意保留的 untracked（R3 排除项 + 任务工件 + journal；另有与任务无关的 .claude/skills/grill-with-docs 旧 D 状态待用户确认）

## 验证命令汇总

```bash
PYTHONIOENCODING=utf-8 python -X utf8 -m py_compile <files...>
PYTHONIOENCODING=utf-8 python -X utf8 test/test_quick_parse_panel.py
git status --short && git log --oneline -4
```

## 回滚点

- 任一 commit 出错：`git reset --soft HEAD~1` 撤提交但保留暂存/工作树（未推送，安全）。
- 测试失败（1.2）：不提交，先修（1.4）。

## 审查门（task.py start 前）

- prd.md 已评审：R1~R4 + 验收标准与用户选定策略一致。
- implement.md 覆盖：核验命令、3 提交分组、排除项、复验。
