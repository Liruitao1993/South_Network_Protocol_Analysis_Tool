# 技术设计：AOCI 认知层接入（阶段 A）

## 1. 目标布局（官方 Volumes v1，Code-only）

```text
E:\python\南网解析工具\
├── aoci.txt              # Root 清单：cognition-volumes/v1（声明的卷列表 + 全局不变量）
├── aoci.meta.txt         # Meta 卷（meta-v1）：仓库级语义
├── aoci.code.txt         # Code 卷（object-fras-v2）：**每文件一行 Entry**（阶段 B 填充）
├── .aoci/                # 治理状态（init 自带 .gitignore：只跟踪 baseline.json / config.json）
│   ├── .gitignore
│   ├── config.json       # exclude_dirs/exclude_files/managed_scope/budget/transport
│   └── baseline.json     # scan 建立的受治理基线（SHA256 指纹，官方：设计上被跟踪）
├── .gitattributes        # init 可能新增（* text=auto eol=lf；官方：从不重写已有文件）
├── AGENTS.md             # init 追加受管块（附加式；与 TRELLIS 块并存）
└── .pi/mcp.json          # 手工接入的 pi MCP 配置（.gitignore 已忽略，机器绑定、不入库）
```

`.aoci/` 下的 ledger / drafts / transactions / recovery 证据由 init 写入的
`.aoci/.gitignore` 自动忽略（以本机 `C:\Users\lirt3\aoci-code\.aoci\.gitignore` 为同版本实证：
该仓库只跟踪 `.aoci/.gitignore`、`.aoci/baseline.json`、`.aoci/config.json` 三个文件）。

## 2. 命令契约（全部来自 rc18 实测 `--help`，非推测）

| 阶段 | 命令 | 契约要点 |
|---|---|---|
| 初始化 | `aoci --repo . init --locale zh-CN` | 可选项 `--agent`（claude/codex/cursor/opencode/qoder/all）、`--hooks`、`--here`、`--scope-profile production\|full\|custom`。**本任务不传 `--agent`** |
| 探查 | `aoci scope rule list` / `scope show` / `scope explain <path>` | `explain` 返回「获胜规则 + 安全边界」，是判定单路径角色的唯一权威 |
| 定范围 | `aoci scope rule add <rule-id> --action index\|observe\|exclude --pattern <p> --pattern-kind file\|directory\|glob --reason <r> [--order N]` | `--reason` 必填；同优先级下**最后匹配者胜**；项目规则**任何 order 都覆盖** profile 内置规则 |
| 定范围（自证） | `aoci scope preview --json` | 返回 role 计数与 `estimated_whole_index_tokens`（公式 `1800 + index_count × 110`） |
| 基线 | `aoci scan [--dry-run] [--force]` | 清单来自 **Git**；**角色在首次 scan 冻结**；`--force` 仅用于重建 |
| 校验 | `aoci verify` / `aoci check` / `aoci status [--deep]` / `aoci doctor [--net]` | `verify` 退出码：0=治理完成、1=存在未解决漂移、2=索引格式非法、3=未初始化/配置错误 |
| MCP | `aoci mcp` | stdio JSON-RPC server，暴露 9 工具 |
| 作者化（阶段 B） | MCP `aoci_maintain` → `aoci_update_entry`（逐条）→ 重复至 `aligned` | 官方定位：`status --deep` / `index score` / `index agent plan` 属 **Legacy 单体索引** 工作流，**不是** Volumes 新仓库路径 |

## 3. Managed Scope 决策矩阵（代码优先口径）

角色冻结机制决定：**这些规则必须在第一次 `scan` 之前写入**（官方 `managed-scope-and-budget.md`
「Order matters」；后补需 TTY `scope approve`）。量化依据用官方预算公式。

| 路径 | 目标角色 | 依据 | 量化影响（`index_count × 110`） |
|---|---|---|---|
| `icons/**` | `exclude` | 2052 个文件、2050 个 svg 图标，无语义 | −225,720 预估 tokens |
| `协议文档/**` | `exclude` | 14 个 md ≈ **2.40 MB** 协议正文 + 16 个二进制文档；是**参考材料**不是代码 | 文档正文不可能进 200K 预算 |
| `国网新一代协议/**` | `exclude` | 11 个 md ≈ 195 KB | 同上 |
| `南网新一代20260226校对/**` | `exclude` | 12 个 md ≈ 69 KB | 同上 |
| `.trellis/**` | `exclude` | 683 个文件，其中 552 个 `tasks/archive`（历史任务记录） | −75,130 预估 tokens |
| `.claude/**` `.agents/**` `.omc/**` `.gitnexus/**` `.spec-workflow/**` `.sisyphus/**` `.qwen/**` | `exclude` | 宿主工具脚手架与技能库（~198 个） | −21,780 预估 tokens |
| `Meter698-45Simulator-master/**` | `exclude` | 第三方模拟器整包（vendored） | 14 个文件 |
| `docs/**` `blog/**` `preprocessors/**`? | `exclude`（`preprocessors/` 若含产品代码则改 `index`） | 设计长文 326 KB / 博客 | 待 `explain` 实测定 |
| 根目录协议参考 md（`1.md`/`1-1.md`/`2.md`/`4.md`/`DLMS_Protocol.md`/`DLT645-2007.md`/`HDLC.md`/`HDLC解析说明.md`/`LME*.md`/`PLUZ*.md`/`低压*.md`/`集中器*.md`/`面向对象*.md`/`QWEN.md`/`work_list.md`） | `exclude`（保留 `AGENTS.md`/`README.md`/`CLAUDE.md` 为 `index`） | 协议正文与过期内文（`QWEN.md` 官方定位「部分内容可能滞后」） | ~3 MB |
| `_tmp_test/**` | `exclude` | 临时测试残留 | 2 个文件 |
| `test/**` | **不动**（保留 profile 判定） | 官方警告：项目 `index` 规则会**覆盖 profile**并把测试/夹具拉进 Whole-Index；`exclude **` + `index a/**` 是明确反例 | 由 profile 决定 |
| 产品 Python 源码 + 契约型根文件 | `index`（profile 默认，必要时补显式规则） | 本任务的价值所在 | ~190~220 文件 → **≈23K~26K tokens** |

**预期结论**：`estimated_whole_index_tokens` 落在 **20K~30K**，远低于新项目默认预算
（target 200000 / max 300000，由 `init` 写入 `.aoci/config.json`），无需调预算。

## 4. pi MCP 接线（唯一的宿主配置改动）

官方支持的宿主是 claude / codex / cursor / opencode / qoder；**pi 不在其中**，走的正是官方为
「不写项目配置的宿主」规定的路径：**给出配置由操作方自行粘贴**，且「手工配置的宿主文件必须在
第一次 `scan` 之前被忽略」——本项目 `.gitignore:51` 已有 `.pi/` 规则，`git check-ignore -v .pi/mcp.json`
实测命中（`rc=0`），天然满足。

配置形态取官方 Claude/Qoder 的 `mcpServers` 形状（与 pi 现有 `.pi/mcp.json` 的 `mcpServers` 结构一致，
可与既有 `powershell` server 并存）：

```json
{
  "mcpServers": {
    "aoci": {
      "command": "C:\\Users\\lirt3\\bin\\aoci.exe",
      "args": ["--repo", "E:\\python\\南网解析工具", "mcp"]
    }
  }
}
```

两条硬要求（官方 `agent-integrations.md`）：宿主配置必须使用**绝对**二进制路径与**绝对**仓库根，
且二者身份须与实际核验一致。pi 在会话启动时读取该文件 → **需要重启 pi 会话**才能加载（官方：
「Refresh or reopen that project session only when it has not loaded the new server」）。

## 5. 阶段边界：为何本任务不能顺手把索引建完

官方 Quick start 的三步指令明确要求：**init + scan 后停下，重启 Agent**，然后才发第二条指令建索引。
理由在官方文档中也有对应说明——MCP 未加载时，唯一替代路径是「手工分段读 `aoci.txt`」，
而官方明确定其为 **manual fallback / diagnostic，不等于 acceptance**（缺少 Chunk 链证明、治理与
Baseline 状态、待处理事务保护、模型 Attestation）。

因此阶段 A 的完成态是：**Baseline 就位 + 9 工具可握手 + 认知层 0 条 Entry**。
此时 `aoci verify` 因 `ActionableMissing` 返回 **1 是预期状态**（官方退出码语义），
阶段 B 的 `aoci_maintain` 批次完成后才应转为 0。

阶段 B 交接物（写入本任务 PRD/交接说明，另开任务执行）：
`aoci_maintain`（无参，MCP）→ 机器批次内逐条 `aoci_update_entry`（`--path` + `--entry` +
`--source-sha256`，来自 maintain 返回的候选指纹）→ 非末批回 Maintain → 末批后 `verify` + `check` + Guide。
批大小由 `code_cognition_batch_entries` 与 `maintain_transport_budget_bytes`（默认 24 KiB）决定。

## 6. 兼容性风险与处置

| 风险 | 事实依据 | 处置 |
|---|---|---|
| `init` 改动 `AGENTS.md`（1538 行权威文档 + Trellis 受管块） | `init` 帮助文本「…and AGENTS.md」；官方：只追加、从不重写维护者内容 | 动前 `cp AGENTS.md` 备份；动后 `diff` 对拍，断言 `<!-- TRELLIS:START -->` 块与正文除 aoci 块外零差异（AC4） |
| `init` 新增/追加 `.gitattributes`、`.gitignore` | 官方：`init` 为新仓库写 `* text=auto eol=lf`，**从不重写已有文件**；按标记块追加忽略项 | 先读现状再动；改动逐行记录（AC4）。**注意**：`*.ps1`/大量中文 md 的 CRLF 现状与 `text=auto eol=lf` 的交互需实测确认（`.aoci/config.json` 默认 `line_ending_tolerance: true`，纯 CRLF/LF 差异只算 informational） |
| 认知资产被 Git 忽略 → scan 静默跳过 | 官方：被忽略的资产会被静默跳过、索引无法建立 | AC2 用 `git check-ignore -v` 逐项自证 |
| Windows 中文仓库路径（`南网解析工具`） | 全项目路径含非 ASCII | 走 `pwshu`（强制 UTF-8）+ 所有命令显式 `--repo`；MCP 握手测试直接覆盖该路径（AC3） |
| PowerShell 文本管道重编码中文 | 官方 `windows-host-agent.md` §566 记录真实事故链（批次过大 → 宿主落盘 → 模型改写 Python → GBK/UTF-8 互读 + bash 吞引号） | 需要传 JSON 只用 `--request-file`（UTF-8 无 BOM）；不用 Python 搬运 Entry 文本；万一必须用 Python 则 `PYTHONUTF8=1` + 显式 `encoding='utf-8'` |
| 项目 `index` 规则覆盖 profile 把测试/夹具拉进索引 | 官方明确反例 | 不写 `test/**` 规则；改动后以 `scope preview` 的 tokens 与 role 计数复核（AC5） |
| 收窄范围发生在首次 scan 之后 | 官方：角色冻结、收窄需真实 TTY 审批 | 顺序强约束：规则 → `preview` → `scan`（implement.md 步骤顺序不可调换） |
| 误改解析器/协议行为 | 本任务是工具链改动 | 实施期零源码改动；`git status` 只允许出现配置/文档/测试文件（AC9） |

## 7. 回滚设计（书面可执行）

```text
1) cp AGENTS.md 备份（实施前，落到 .pi/ 或 %TEMP% 等不入库位置）
2) 出错需回到 init 前：删 aoci.txt / aoci.meta.txt / aoci.code.txt / .aoci/
3) git checkout -- AGENTS.md .gitignore .gitattributes   # 恢复被 init 追加/新增的改动
4) .pi/mcp.json 删除 aoci 段（或整文件还原）
5) 复核：git status 只剩预期文件；aoci doctor 报未初始化（预期）
```

官方另有 `docs/uninstall.md` 的卸载路径，实施时读取并按需引用（不取代上面的最小回滚）。

## 8. 验证设计（三层，全部可自证）

1. **环境层** `aoci doctor`（离线）→ 仓库资产 / Agent 集成 / AI 层 / 平台特性四组结论（AC1）。
2. **策略层** `aoci scope preview --json` + `aoci scope explain <代表路径>`（`icons/x.svg`、
   `协议文档/x.md`、`.trellis/spec/x.md`、`main_gui.py`、`test/test_dlms.py`）→ 角色与 tokens 判据（AC5）。
   `scan` 后 `aoci status` 复核无治理阻塞（AC6）。
3. **通道层** 以 stdio 实拉 `mcp` 做 `initialize` + `tools/list` 往返，断言 9 工具（AC3）。
   **这是「接通」的唯一证据**——写配置文件本身不构成验证。
4. **回归层** `test/test_aoci_integration.py`（AC7）把上述关键事实固化为断言，
   防后续会话把配置改坏（二进制缺失时 SKIP + 0 退出，跨机器安全）。

## 9. 实施时必须用实测填掉的未决项（TBD，禁止凭推测写文档）

- `TBD-1` `init` 不带 `--agent` 时的实际产物清单（是否只写骨架 + AGENTS.md 块？是否写
  `.gitattributes`/`.gitignore`？）—— 以 `git status --porcelain` 前后对拍为准。
- `TBD-2` `scope rule list` 在 `--scope-profile production` 下的**内置规则全集与各自角色**
  （已知会带 7 条 `starter-vendored-*` observe 规则；本项目无 `static/**/libs`，预期不命中，
  仅 `**/*.min.js`、`**/*.map`、`**/fonts/**` 可能命中，需实测）。
- `TBD-3` `preprocessors/`、`docs/`、`blog/`、根目录 `*.json` 的实际角色与是否需显式规则
  —— 以 `scope explain` 为准逐条判定。
- `TBD-4` `verify` 在本阶段的准确退出码与信息（预期 1 = ActionableMissing），
  以及 `scope status` 是否报 `scope_change_required`（若报，按官方 `scope activate` 处理）。
- `TBD-5` pi 会话重启后 `tools/list` 是否以 `aoci_*` 前缀暴露、9 工具是否全部可见
  —— 阶段 A 以手工 stdio 握手为准，重启后的宿主可见性在阶段 B 开头复核。
