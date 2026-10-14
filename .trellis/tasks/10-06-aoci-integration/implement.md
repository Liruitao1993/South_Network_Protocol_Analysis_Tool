# 实施计划：AOCI 认知层接入（阶段 A）

> **顺序不可调换**：规则写入必须在 `scan` 之前完成（Safe Inventory 角色在首次 `scan` 冻结，
> 之后收窄需真实 TTY 审批）。每个 Step 末尾的「判据」是**门禁**，不通过就停下修复，不得进入下一步。
>
> 所有命令在 WSL bash 内经 `pwshu '...'` 执行（本机 bash 处在 WSL，无 python/node/aoci）。
> 仓库根 = `E:\python\南网解析工具`（含中文，pwshu 已强制 UTF-8）。aoci 二进制 =
> `C:\Users\lirt3\bin\aoci.exe`（v0.1.0-rc18）。

## Step 0 — 前置取证与备份

```bash
cd /mnt/e/python/南网解析工具
cp AGENTS.md "$TMPDIR/AGENTS.md.before-aoci" 2>/dev/null || cp AGENTS.md /tmp/AGENTS.md.before-aoci
cp .gitignore /tmp/.gitignore.before-aoci
ls -la .gitattributes || echo "NO .gitattributes"
pwshu 'git status --porcelain' > /tmp/git-status.before-aoci.txt
wc -l /tmp/git-status.before-aoci.txt
```

**判据**：备份文件存在；`.gitattributes` 存在性已知；`git status --porcelain` 的既有改动清单已落盘
（本仓库当前有 ~27 项未提交改动，实施后必须能区分「我引入的」与「既有的」）。

**回滚点 R0**：无需动作（尚未改动）。

## Step 1 — 初始化（不带 `--agent`）

```bash
pwshu 'aoci --repo "E:\python\南网解析工具" init --locale zh-CN'
```

**判据**
- 退出码 0；输出中确认生成了 Root / Meta / Code 卷与治理配置。
- `pwshu 'git status --porcelain'` 与 Step 0 的落盘清单对比，**逐条列出新增改动**（预期：
  `?? aoci.txt`、`?? aoci.meta.txt`、`?? aoci.code.txt`、`?? .aoci/`，外加 `M AGENTS.md`
  与可能的 `.gitattributes` / `.gitignore`）→ 这份清单同时填入 `TBD-1` 的答案。
- **未写出** `.mcp.json` / `.codex/config.toml` / `opencode.json`（本任务不传 `--agent` 的目的）。
  若意外出现，停下评估并回滚该文件。

**回滚点 R1**：`rm -f aoci.txt aoci.meta.txt aoci.code.txt; rm -rf .aoci; git checkout -- AGENTS.md .gitignore; rm -f .gitattributes`

## Step 2 — AGENTS.md / .gitignore / .gitattributes 逐块核对（门禁）

```bash
diff /tmp/AGENTS.md.before-aoci AGENTS.md | head -60
grep -n "TRELLIS:START\|aoci" AGENTS.md | head -20
diff /tmp/.gitignore.before-aoci .gitignore
cat .gitattributes 2>/dev/null
```

**判据**
- `AGENTS.md` 的差异**只包含 aoci 受管块**；`<!-- TRELLIS:START -->` 块与原有正文零差异。
- `.gitignore` 若被追加，逐行说明追加内容与理由（预期无：本任务不写宿主配置）。
- `.gitattributes` 若为新增，记录全文并评估对既有 CRLF 文件的影响（`.aoci/config.json` 默认
  `line_ending_tolerance: true`，纯 CRLF/LF 差异只算 informational）。

**不通过处置**：手工把 aoci 块挪到不破坏 Trellis 块的位置，或按 R1 回滚后改用其他 `init` 参数重来。

## Step 3 — 探查内置规则与实际角色

```bash
pwshu 'aoci --repo "E:\python\南网解析工具" scope rule list'
pwshu 'aoci --repo "E:\python\南网解析工具" scope show'
pwshu 'aoci --repo "E:\python\南网解析工具" scope preview --json'   # 基线快照，留档
```

**判据**：拿到 production profile 的内置规则全集（填 `TBD-2`）与当前 `index` 角色文件数
（作为 Step 4 修改后的对照基线）。确认 7 条 `starter-vendored-*` 在本仓库的命中情况。

## Step 4 — 写入项目级 Scope 规则（代码优先）

按 `design.md` §3 矩阵逐条写入（`--reason` 必填，写清依据而不是「不需要」）：

```bash
R="E:\python\南网解析工具"
# 图标（2052 个，其中 2050 svg）
pwshu "aoci --repo \"$R\" scope rule add icons-svg --action exclude --pattern icons --pattern-kind directory --reason \"2050 svg 图标无语义，实测 2052 文件若进 index 会让预估 tokens 达 227K\""
# 三大协议文档目录（120 个 md ≈ 2.67MB 正文 + 二进制文档）
pwshu "aoci --repo \"$R\" scope rule add doc-protocol --action exclude --pattern 协议文档 --pattern-kind directory --reason \"协议正文参考材料非代码，14 个 md 已 2.4MB\""
pwshu "aoci --repo \"$R\" scope rule add doc-gw-newgen --action exclude --pattern 国网新一代协议 --pattern-kind directory --reason \"协议正文参考材料非代码\""
pwshu "aoci --repo \"$R\" scope rule add doc-csg-newgen --action exclude --pattern 南网新一代20260226校对 --pattern-kind directory --reason \"协议正文参考材料非代码\""
# Trellis 工作区（683 个，其中 552 个历史任务归档）
pwshu "aoci --repo \"$R\" scope rule add trellis-workspace --action exclude --pattern .trellis --pattern-kind directory --reason \"任务/journals/归档属流程工件，非产品语义\""
# 宿主工具目录
pwshu "aoci --repo \"$R\" scope rule add agent-tooling --action exclude --pattern \".claude,.agents,.omc,.gitnexus,.spec-workflow,.sisyphus,.qwen\" --pattern-kind glob --reason \"宿主工具脚手架与技能库，非产品代码\""
# 第三方整包 / 临时残留 / 设计长文
pwshu "aoci --repo \"$R\" scope rule add vendored-simulator --action exclude --pattern Meter698-45Simulator-master --pattern-kind directory --reason \"第三方 698.45 模拟器整包\""
pwshu "aoci --repo \"$R\" scope rule add tmp-residue --action exclude --pattern _tmp_test --pattern-kind directory --reason \"临时测试残留\""
```

根目录协议参考 md 与 `docs/`/`blog/`/`preprocessors/`：**先不要批量写规则**，
用 `scope explain` 逐一实测后按需补（避免误伤 `AGENTS.md`/`README.md`/产品代码）：

```bash
for p in "AGENTS.md" "README.md" "main_gui.py" "test/test_dlms.py" "icons/x.svg" "协议文档/x.md" ".trellis/spec/x.md" "docs/x.md" "blog/x.md" "preprocessors/x.py" "1.md" "QWEN.md" "work_list.md" "LME产品相关信息生产运维接口手册_V2.4_251115.md" "custom_di.json" "config.json"; do
  echo "--- $p"; pwshu "aoci --repo \"$R\" scope explain \"$p\"" 2>&1 | head -12
done
```

**判据**
- `AGENTS.md` / `README.md` / 产品 `.py` / 契约型 `.json` → **index**。
- `icons/**`、协议文档目录、`.trellis/**`、宿主工具目录、第三方整包 → **exclude**。
- `test/**` → 保持 profile 判定（**禁止**为它写任何 `index` 规则，官方明确反例）。
- `preprocessors/` 若属产品代码则**不排除**（代码优先口径的含义就是产品代码必须进索引）。
- 每条 `--reason` 均已写入，且 `scope rule list` 能看到（填 `TBD-3`）。

**回滚点 R2**：`aoci scope rule remove <rule-id>`（同一优先级下最后匹配者胜，规则可逐条撤）。

## Step 5 — 预算门禁：`scope preview`（关键门禁，不通过不得 scan）

```bash
pwshu 'aoci --repo "E:\python\南网解析工具" scope preview --json' > /tmp/aoci-preview-after.json
python3 -c "import json;d=json.load(open('/tmp/aoci-preview-after.json'));print(json.dumps(d,ensure_ascii=False)[:3000])"
```

**判据（AC5）**
- role 计数证明 `icons/**`、三大文档目录、`.trellis/**`、宿主工具目录**均不在 index 角色**。
- `estimated_whole_index_tokens` **< 60000**（预期 20K~30K；公式 `1800 + index_count × 110`）。
- `index` 角色文件数与 Step 3 的基线相比是**显著下降**（若反而上升，说明规则口径写错，停下排查）。

**不通过处置**：不要 scan。回到 Step 4 修正规则；确认是「规则没生效」还是「路径口径写错」
（用 `scope explain` 看获胜规则）。

## Step 6 — 建立 Baseline

```bash
pwshu 'aoci --repo "E:\python\南网解析工具" git check-ignore -v aoci.txt aoci.meta.txt aoci.code.txt AGENTS.md; echo "rc=$?"'   # 期望：无命中
pwshu 'aoci --repo "E:\python\南网解析工具" scan'
pwshu 'aoci --repo "E:\python\南网解析工具" status'
pwshu 'aoci --repo "E:\python\南网解析工具" verify' ; echo "verify_rc=$?"
pwshu 'aoci --repo "E:\python\南网解析工具" scope status'
```

**判据（AC2 / AC6）**
- `git check-ignore -v` 对四类认知资产**全部无命中**（认知资产被忽略 = scan 静默跳过 = 索引废掉）。
- `scan` 退出码 0，`.aoci/baseline.json` 生成。
- `verify` 退出码**预期为 1**（`ActionableMissing`：认知层尚无 Entry，属阶段 A 的预期态，不是缺陷）；
  若返回 2/3 必须修（索引格式非法 / 未初始化）。
- `scope status` 无 `scope_change_required` 之类治理阻塞（填 `TBD-4`）。

**回滚点 R3**：`rm -rf .aoci/baseline.json`（或用 `scan --force` 重建）。

## Step 7 — pi MCP 接入 + stdio 握手自证

7.1 合并 `.pi/mcp.json`（保留既有 `powershell` server，只新增 `aoci` 键；UTF-8 无 BOM）：

```json
"aoci": {
  "command": "C:\\Users\\lirt3\\bin\\aoci.exe",
  "args": ["--repo", "E:\\python\\南网解析工具", "mcp"]
}
```

7.2 写 `test/test_aoci_integration.py`（项目约定：位于 `test/`，文件头
`import _path_setup  # noqa: E402,F401`）。**握手探针只在这一处实现**，供 Step 7.3 与后续回归共用：

- `mcp_handshake()`：`subprocess.Popen([aoci, "--repo", repo, "mcp"], stdin/stdout=PIPE)`，
  发送 `initialize`（`protocolVersion`/`clientInfo`）→ 发送 `initialized` 通知 →
  发送 `tools/list` → 断言返回 **9 个工具**：
  `aoci_rules`、`aoci_overview`、`aoci_search`、`aoci_get_entries`、`aoci_maintain`、
  `aoci_update_entry`、`aoci_remove_entry`、`aoci_report`、`aoci_header`。
  超时保护（如 20s）+ 结束时 kill 子进程；**aoci 二进制不存在 → 打印 SKIP 并以 0 退出**。
- 其余断言：`.pi/mcp.json` 的 aoci server 存在、`command` 指向的文件 `os.path.isfile`、`--repo`
  为绝对路径且等于仓库根；认知资产未被忽略（`git check-ignore`）；`AGENTS.md` 同时含 aoci 块与
  `<!-- TRELLIS:START -->`；卷文件存在且 Root 清单声明的 `path=` 实际存在。

```bash
pwshu 'cd "E:\python\南网解析工具"; python test/test_aoci_integration.py'
```

**判据（AC3 / AC7 部分）**：9 个工具断言通过；中文仓库路径无编码错误。
**这是「MCP 已接通」的唯一证据**——只写配置文件不构成验证。

## Step 8 — 登记门禁 + 沉淀用法文档

```bash
grep -n "CORE_TESTS" -A 30 release_check.py | head -40   # 找到清单位置后追加一行 test/test_aoci_integration.py
pwshu 'cd "E:\python\南网解析工具"; python release_check.py --skip-tests'
```

- 新增 `docs/AOCI认知层使用指南.md`：AOCI 是什么（`F/R/A/S` + `[CG4L]` 标签）、本仓库实际配置
  （scope 规则清单 + 理由 + 预算实测值 + 卷文件位置）、日常手册（Maintain 循环 / `scope explain` /
  `verify` / `check` / `status` / `ui` / `doctor` 的用途与退出码语义）、接线清单（`.pi/mcp.json` 原文 +
  换机器要改的两处绝对路径）、故障与回滚（含官方 `--request-file` 与 UTF-8 契约）。
  **文档里出现的每条命令都必须是本任务实际执行过的**（AC8）。
- `AGENTS.md` §12「其他参考文档」追加一行指针（最小改动，避免与 aoci 受管块冲突）。

**判据**：`release_check.py` FAIL 数不比改动前增加；新增测试被清单收录。

## Step 9 — 收尾审计

```bash
pwshu 'git status --porcelain'
pwshu 'git check-ignore -v .pi/mcp.json'      # 期望命中 .gitignore:51（机器绑定文件不入库）
pwshu 'aoci --repo "E:\python\南网解析工具" doctor'
```

**判据（AC1 / AC9）**
- 改动清单只含预期文件：`aoci.txt`、`aoci.meta.txt`、`aoci.code.txt`、`.aoci/`、`AGENTS.md`、
  可能的 `.gitattributes`/`.gitignore`、`docs/AOCI认知层使用指南.md`、`test/test_aoci_integration.py`、
  `release_check.py`；**无任何解析器/协议行为改动**；**无 `.pi/mcp.json`**（它被忽略）。
- `aoci doctor`（离线）四组结论无未解释异常。
- 把「阶段 B 交接物」（`design.md` §5 的 Maintain 循环要点 + 本任务实测的批大小/transport 预算）
  写入任务 notes，供阶段 B 任务直接接手。

## 阶段 B（另开任务，本任务只交接）

重启 pi 会话 → 确认 9 个 `aoci_*` 工具可见 → `aoci_maintain` → 逐条 `aoci_update_entry`
（`--path` + `--entry` + `--source-sha256`）→ 非末批回 Maintain → 末批后 `verify` + `check` + Guide
（此时 `verify` 才应转为退出码 0）。
