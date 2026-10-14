# AOCI 认知层接入本项目（init + Managed Scope + Baseline + pi MCP）

## Goal

用本机已安装的 **AOCI-CODE**（`C:\Users\lirt3\bin\aoci.exe`，v0.1.0-rc18）为 `E:\python\南网解析工具`
（Git 根，3500 个跟踪文件）建立一份**版本化、可 Git 评审、由 Agent 维护的仓库认知层**，
并把它接到 **pi** 的 MCP 通道上，使后续会话不必反复重读整个仓库。

参考实现与权威文档来自本机同版本的 AOCI 自身仓库 `C:\Users\lirt3\aoci-code`
（`README.md` / `docs/getting-started.md` / `docs/agent-integrations.md` /
`docs/managed-scope-and-budget.md` / `docs/cognition-volumes.md` / `docs/windows-host-agent.md`）。

**官方规定的路径顺序（不可颠倒，`docs/getting-started.md` + `README.md` Quick start）**：

```text
init  →（本轮）定 Scope 规则 →（本轮）scan  → 重启宿主 Agent  → Maintain 作者化  → verify/check/Guide
                                              └── 阶段 B（本任务范围外）──┘
```

README 的官方指令原文即要求「**init + scan 后先停下，重启 Agent**，再开始建索引」，因此本任务
= **阶段 A**（init / scope / scan / pi MCP 接入 / 握手验证 / 用法沉淀）；**阶段 B**（Maintain 批量
作者化 ~200 条 Entry）必须在 pi 重启后另开任务。

## Requirements

- **R1｜初始化（init）**：在仓库根执行 `aoci --repo . init --locale zh-CN`，
  生成 Root 清单 `aoci.txt` + Meta 卷 `aoci.meta.txt` + 空 Code 卷 `aoci.code.txt` +
  `.aoci/`（`config.json` + `.gitignore` + Baseline）以及 `AGENTS.md` 的受管块。
  **不传 `--agent`**：官方 `--agent` 只支持 claude / codex / cursor / opencode / qoder / all，
  pi 不在其中，且它写出的宿主配置（`.mcp.json` / `.codex/config.toml` / `opencode.json`）
  是**机器绑定**文件；本项目 `.codex/` 由 Trellis 管理、`.codex/config.toml` 已被 Git 跟踪
  （官方明确：已跟踪的宿主配置 `init` 不会代为忽略），故一律不写，改走 R2 的手工接入。
- **R2｜pi MCP 手工接入**：把 aoci 作为 **stdio MCP server** 合并进项目级 `.pi/mcp.json`
  （已由 `.gitignore:51` 的 `.pi/` 规则忽略，官方要求「手工配置的宿主文件必须在首次 scan 前
  忽略掉」已天然满足）。形态取官方 Claude/Qoder 的 `mcpServers` 形状：
  `{"command": "<绝对路径 aoci.exe>", "args": ["--repo", "<绝对路径仓库根>", "mcp"]}`；
  **两个路径都必须绝对**（官方硬要求：宿主配置必须使用身份已核验的同一绝对二进制与仓库根）。
- **R3｜Managed Scope 先于首次 scan**：`scan` 的文件清单来自 Git，且 **Safe Inventory 角色在首次
  `scan` 时冻结**，之后收窄属 coverage reduction，需要真实 TTY 的 `scope approve`
  （官方 `docs/managed-scope-and-budget.md`「Order matters」，并给出「先 exclude 再 scan」的范例）。
  因此本任务必须在 `scan` **之前**用 `aoci scope rule add` 一组项目级 `exclude` / `observe` 规则，
  范围口径 = **代码优先**（用户 2026-10-06 决策）：
  - 进 `index`：产品 Python 源码（根目录解析器/GUI、`validator/`、`system_integration/`、
    `meter_sim/`、`dlt645_sim/`、`monitor/`、`report/`、`templates/`、`visual_editor/`、
    `preprocessors/`、`scripts/`、`reflex_web/**/*.py`）与**契约型文档/配置**
    （`AGENTS.md`、`README.md`、根目录 schema/config JSON）。
  - `exclude`：`icons/**`（2052 个文件，其中 2050 个 svg）、三大协议文档目录
    （`协议文档/**`、`国网新一代协议/**`、`南网新一代20260226校对/**`，共 120 个 md ≈ 2.67 MB 正文）、
    `.trellis/**`（683 个，含 552 个 `tasks/archive`）、Agent 工具目录
    （`.claude/`、`.agents/`、`.omc/`、`.gitnexus/`、`.spec-workflow/`、`.sisyphus/`、`.qwen/`）、
    第三方 `Meter698-45Simulator-master/**`、`docs/**` 与 `blog/**` 设计长文、
    根目录的协议参考 md（`1.md`/`1-1.md`/`2.md`/`4.md`/`DLMS_Protocol.md`/`DLT645-2007.md`/`HDLC*.md`/
    `LME*.md`/`PLUZ*.md`/`QWEN.md` 等）、`_tmp_test/**`。
  - **不得**把 `test/**` 纳入排除（production profile 自带的 test/fixture 规则优先于项目规则，
    官方警告 `exclude **` + `index xxx` 的组合会把测试与夹具错误拉进 Whole-Index）；
    执行时以 `aoci scope rule list` / `scope explain <path>` 的实际判定为准修正。
  - 判据用**官方预算公式** `estimated_whole_index_tokens = 1800 + index_count × 110`：
    2052 个图标若进 index 角色 → ≈227K，顶穿新项目默认预算（target 200000 / max 300000）；
    代码优先口径的预期值应 **< 60000**。
- **R4｜Baseline（scan）**：规则就位后执行 `aoci scan` 建立受治理 Baseline
  （`.aoci/baseline.json`；官方：「scan 不是可选项」，缺 Baseline 时 Guide 报 `blocked`）。
  认知资产（`aoci.txt` / `aoci.meta.txt` / `aoci.code.txt` / `AGENTS.md`）**必须不被 Git 忽略**，
  否则 scan 会静默跳过、索引无法建立——须以 `git check-ignore` 逐项自证。
- **R5｜MCP 握手自证**：不能只写配置就宣布接通。必须直接以 stdio 拉起
  `<aoci.exe> --repo <仓库根> mcp`，完成 `initialize` + `tools/list` JSON-RPC 往返，
  断言返回 **9 个工具**（`aoci_rules`/`aoci_overview`/`aoci_search`/`aoci_get_entries`/
  `aoci_maintain`/`aoci_update_entry`/`aoci_remove_entry`/`aoci_report`/`aoci_header`），
  并覆盖中文仓库路径（`南网解析工具`）在 Windows 下的实际可用性。
- **R6｜改动可逆、可审计**：`init` 会**修改仓库根 `AGENTS.md`**（受管块，附加式）、可能新增
  `.gitattributes`（官方：`init` 为新仓库写 `* text=auto eol=lf`，**且从不重写已存在的**）、
  可能追加 `.gitignore` 标记块。要求：改动前留备份（`AGENTS.md` 等）→ 改后逐块核对
  （Trellis 受管块 `<!-- TRELLIS:START -->` 与本文件原有 1538 行正文不得受损）→
  记录一份「改动前/后」清单，并给出**回滚步骤**（删除 `aoci*.txt` + `.aoci/` +
  `git checkout -- AGENTS.md .gitignore .gitattributes`）。
- **R7｜零外发**：不配置 AI endpoint（用户 2026-10-06 决策：保持离线、由宿主模型作者化），
  `aoci ai setup --disable --local` 显式固化该状态；语义一律由宿主模型（pi / Codex / Claude）
  经 MCP `aoci_maintain` → `aoci_update_entry` 写出（官方数据边界：本机只读源码、不联网、只写
  `.aoci/` 与正式卷文件）。
- **R8｜用法沉淀**：新增 `docs/AOCI认知层使用指南.md`（本项目第一个 AOCI 使用文档），内容覆盖：
  AOCI 是什么（Entry 的 `F/R/A/S` + `[CG4L]` 标签含义）、本仓库的实际配置（scope 规则清单与
  理由、预算实际值、卷文件位置）、日常操作手册（维护循环、`scope explain`/`verify`/`check`/
  `status`/`ui` 的用途与退出码语义）、**接线清单**（pi 手工接入的原文 JSON、换机器要改哪两处）、
  故障与回滚；并在 `AGENTS.md` §12「其他参考文档」加一行指针。
- **R9｜回归守卫**：新增 `test/test_aoci_integration.py`（项目测试约定：位于 `test/`，
  文件头含 `import _path_setup  # noqa: E402,F401`），断言：
  (a) `.pi/mcp.json` 存在且含 `aoci` server，`command` 指向的二进制**实际存在**、
      `args` 的 `--repo` 指向仓库根且绝对；(b) 认知资产未被 Git 忽略；
  (c) `AGENTS.md` 同时含 aoci 受管块与 Trellis 受管块；(d) 卷文件存在且 Root 清单
  声明的卷路径与实际文件一致；(e) `aoci` 二进制缺失时**整体跳过并以 0 退出**（跨机器安全）。
  并登记进 `release_check.py` 的门禁清单。

## 非目标（本任务不做）

- **不做阶段 B（Maintain 批量作者化）**：官方顺序要求 `scan` 后先重启宿主再建索引，本任务止于
  「Baseline 已就位 + MCP 已接通 + 索引为 0 条 Entry（`verify` 因 ActionableMissing 返回 1 是
  **预期状态**，不是缺陷）」。首次 Index 构建（约 190~220 条 Entry、1~2 批）另开任务。
- 不配置 AI endpoint、不引入新的 Python 依赖、不改任何解析器/协议行为。
- 不改 `release_check.py` 既有门禁语义（仅追加一条测试项）。
- 不为 `.claude` / `.codex` / `.mcp.json` 装 AOCI（用户 2026-10-06 决策：仅 pi）。
- 不把 `test/**` 移出/移入 index 角色（交由 production profile 判定）。

## Acceptance Criteria

- [ ] **AC1** `aoci --repo . doctor`（离线，不加 `--net`）报告仓库已初始化、认知资产齐备、
      无配置/结构错误；异常项必须逐条给出解释或修复记录。
- [ ] **AC2** 仓库根存在 `aoci.txt` / `aoci.meta.txt` / `aoci.code.txt`，且
      `git check-ignore -v` 对四类认知资产（含 `AGENTS.md`）**全部无命中**（未被忽略）。
- [ ] **AC3** `.pi/mcp.json` 中的 aoci server 指向存在的绝对 `aoci.exe` 与绝对仓库根；
      以 stdio 实拉 `mcp` 并完成 `initialize`+`tools/list`，断言 **9 个工具**齐全；
      含中文路径参数无编码错误。
- [ ] **AC4** `AGENTS.md` 同时存在 aoci 受管块与 `<!-- TRELLIS:START -->` 受管块，
      且原有正文（备份对拍）**除 aoci 块外零差异**；`.gitattributes`/`.gitignore` 的改动
      逐行列出并说明（若有）。
- [ ] **AC5** `aoci scope preview --json` 的 role 统计证明：`icons/**`、三大协议文档目录、
      `.trellis/**`、Agent 工具目录**均不在 index 角色**；
      `estimated_whole_index_tokens` **< 60000**（代码优先口径的量化判据）。
- [ ] **AC6** `aoci scan` 成功且 `.aoci/baseline.json` 生成；`aoci scope status` /
      `aoci status` 无治理阻塞（`scope_change_required` 之类必须为零或已按官方流程消除）。
- [ ] **AC7** `python test/test_aoci_integration.py` 全绿；无 aoci 二进制时以 0 退出并打印 SKIP；
      `release_check.py` 的门禁清单已含该测试且 `python release_check.py --skip-tests` 无 FAIL 增加。
- [ ] **AC8** `docs/AOCI认知层使用指南.md` 存在，且其中每条命令都在本机**实际执行过**
      （文档不得出现未验证的命令/参数）；`AGENTS.md` §12 有指向它的条目。
- [ ] **AC9** 回滚步骤经书面验证可行（列出确切命令），且**未提交任何机器绑定文件**
      （`git status` 中不得出现 `.pi/mcp.json`）。

## Notes

- 全部命令必须经 `pwshu '...'`（WSL bash 内无 python/node/aoci，见 `~/.pi/agent/AGENTS.md`）。
- Windows 契约（`docs/windows-host-agent.md`）：`--json` 输出是 ASCII-safe，可直接捕获；
  需要传 JSON 请求时**只用** `--request-file`（UTF-8 无 BOM），**禁止**经 PowerShell 文本管道；
  若必须用 Python 处理，设 `PYTHONUTF8=1` 并在每个 `open()` 显式 `encoding='utf-8'`。
