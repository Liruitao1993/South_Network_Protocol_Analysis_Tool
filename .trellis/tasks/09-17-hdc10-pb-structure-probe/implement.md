# 实施计划：协议11 PB 结构探测

> 顺序执行；每阶段有验证命令与通过标准。**阶段 0 必须在改代码之前完成**（基线指纹）。

## 阶段 0 · 采集回归基线（改代码前）

- [ ] 0.1 用 `test/hdc10_real_frames.pkl` 的 60 帧在 `pb_only` 下生成**逐行指纹**基线文件：

```bash
cd /mnt/e/python/南网解析工具 && PYTHONPATH=. python3 - <<'EOF' > /tmp/hdc10_pb_baseline.txt
import pickle, hashlib
from hdc10_parser import HDC10Parser
p = HDC10Parser()
for fi, fb, key in pickle.load(open("test/hdc10_real_frames.pkl","rb")):
    rows = p._parse_pb_only(fb, 1)
    txt = "\n".join(repr(r) for r in rows)
    print(fi, key, len(rows), hashlib.sha256(txt.encode()).hexdigest()[:16])
EOF
```

- [ ] 0.2 记录现场帧改动前基线（协议11 `auto` = 17 行、协议10 = 54 行）——用于「改前 vs 改后」对照

**通过标准**：基线文件生成成功，60 行记录可读（后续 A4 对拍用）

## 阶段 1 · 实现 `_probe_pb_form`（新增）

- [ ] 1.1 在 `hdc10_parser.py` 的 `_parse_pb_block` 之后新增
  `HDC10Parser._probe_pb_form(self, data: bytes) -> Tuple[int, int]`，
  返回 `(pbh_len, score)`；判据 C1~C6 与阈值按 `design.md` §2 实现
- [ ] 1.2 判据中的常量全部取自模块现有单一来源：`APP_PORTS`（`:144`）、
  `APP_MSDU_TYPES`/`IPV4_MSDU_TYPES`（`:138` 附近）、`MSG_ID_NAMES`、`_crc32`（`:228`）
  —— **不得新写第二份清单**
- [ ] 1.3 MAC 头长度判定复用 `_parse_mac_header`（`:1694`）返回的 `header_len`，
  禁止硬编码 16/28（AGENTS §8 陷阱 28）

**通过标准**：现场帧调用 `_probe_pb_form(data[16:])` 返回 `(0, score>=2)`；
且对合法 PBH 帧（`pbh=0xC0`）返回 `(1, ...)`（或不被调用）

## 阶段 2 · 改 `_parse_pb_block` 的 else 分支

- [ ] 2.1 `hdc10_parser.py:988` 附近「非帧起始PB」分支改为：
  先 `pbh_len, score = self._probe_pb_form(data)`；`pbh_len == 0 and score >= 2`
  → 输出形态提示行 + `self._parse_mac_frame(data, base_offset)`；
  否则保持现有 raw hex 行为
- [ ] 2.2 形态提示行文案含「未检测到合法物理块头(PBH)」与判据摘要，并给正确偏移
- [ ] 2.3 尾部 3 字节若构成合法 PBCS（`crc24(data[:-3]) == int.from_bytes(data[-3:],'little')`）
  额外输出一行标注（不影响主流程）

**通过标准**：现场帧 `auto` 输出含应用层报文段；`pb_only` 同样可用；合法 PBH 帧输出不变

## 阶段 3 · 改 `_parse_pb_and_mac_header`（`fc_mac` 同源）

- [ ] 3.1 `hdc10_parser.py:3026` 改为调用同一 `_probe_pb_form`
- [ ] 3.2 `pbh_len == 0` 时不输出「PB头」行，MAC 头从 `data[0:]` 解

**通过标准**：现场帧在 `fc_mac` 下 MAC 头字段与 `auto`/`pb_only` 一致（不得错位 1 字节）

## 阶段 4 · 测试与登记

- [ ] 4.1 新建 `test/test_hdc10_pb_probe.py`（文件头含 `import _path_setup  # noqa: E402,F401`），
  至少覆盖：
  - 现场帧 golden：`auto`/`fc_pb`/`fc_mac`/`pb_only` 四入口（A1/A5）
  - 关键字段断言：TEI/MSDU类型/MSDU长度/MAC 地址/端口/报文ID/规约类型/转发数据长度/ICV ✓（A1/A2）
  - 双协议对拍：与 `GWNewGenParser` 同帧字段逐项相等（A2）
  - 形态标注行存在（A3）
  - 60 帧指纹与阶段 0 基线逐行一致（A4）
  - 合法 PBH 帧（`0x40/0x80/0xC0`）分类正确（探测不触发）
  - 真中间 PB（`pbh=0x10` 且内容不自洽的构造帧）**仍走 raw hex**（防误判）
  - **弱判据不足阈值**用例：只满足 C2/C4 的构造数据不得触发回退
- [ ] 4.2 在 `release_check.py` 的 `CORE_TESTS` 列表登记新测试

**通过标准**：`python test/test_hdc10_pb_probe.py` 全过、退出码 0

## 阶段 5 · 变异反证（A7）

- [ ] 5.1 变异 M1：把 `_probe_pb_form` 首行改为 `return (1, 99)`（等价还原硬判）
  → 期望：A1/A2/A5 断言**变红**
- [ ] 5.2 变异 M2：把阈值 `>= 2` 改为 `>= 0`（任何输入都回退）
  → 期望：「真中间 PB 仍走 raw hex」用例**变红**
- [ ] 5.3 每条变异逐条实测、记录红项数，**改回后测试复绿**

**通过标准**：两条变异均观察到变红；还原后全绿

## 阶段 6 · 版本链与文档

- [ ] 6.1 `main_gui.py`：`APP_VERSION` → `1.23.24`、`BUILD_DATE` → 当日；`CHANGELOG` 头部新增条目
- [ ] 6.2 `README.md` 更新记录追加 1.23.24
- [ ] 6.3 `AGENTS.md`：§5.9 补 PB 形态探测说明；§8 新增陷阱条目
  （「协议11 的 PBH 硬判 → 内容驱动探测」含现场帧证据与方法论）；§10 摘要
- [ ] 6.4 `python release_check.py --sync-iss` 同步 Inno Setup 版本号

## 阶段 7 · 全量验证与收尾

```bash
python test/test_hdc10_pb_probe.py       # 新增
python test/test_hdc10.py                # 既有 20 项
python test/test_hdc10_real.py           # 真实帧夹具
python test/test_hdc10_app_dispatch.py   # 94 项
python test/test_hdc10_meter_reading.py  # 13 项
python test/test_gw_new_gen.py           # 协议10 回归 44 项
```

- [ ] 7.1 上述全部测试通过（记录各测试项数）
- [ ] 7.2 `python release_check.py` → `FAIL=0`（记录 PASS/WARN 数）
- [ ] 7.3 回填 `implement.md`：实测探针结论、与设计的差异、变异结果、预期差异清单
- [ ] 7.4 提交（feat 提交 + 任务归档）

**通过标准**：A1~A7 全部满足；git 工作区干净

## 预期差异清单（改动后必须能解释每一处变化）

| 输入 | 改动前 | 改动后（预期） |
| --- | --- | --- |
| 现场帧（PBH 缺失） | 协议11 `auto` 17 行、无业务内容 | 新增形态提示行 + MAC 帧段 + 应用层报文段 + ICV ✓；**业务内容与协议10 一致** |
| 合法 PBH 完整帧（`pbh` bit6/bit7 置位） | 正常 | **逐行不变** |
| 60 帧夹具（`pb_only`，`0xC0` 开头） | 正常 | **逐行不变**（sha256 对拍） |
| 信标帧（`dt=0`） | 正常 | **逐行不变**（不经过探测） |
| 真中间 PB（PBH 合法但 `sof=eof=0`，内容不自洽） | raw hex | **raw hex 不变**（分数不足阈值） |

## 回滚点

- 阶段 1~3 任一阶段验证失败 → `git checkout -- hdc10_parser.py` 回到基线
- 阶段 6/7 前若回归异常 → `git revert` 本次提交；无数据迁移负担
