# 协议9 链路层组帧 —— 执行计划

对应 `prd.md` + `design.md`。**每个阶段可独立提交与回退**；纯逻辑先行的顺序保证每步都能单独验证。

> ⚠ 运行环境提醒（AGENTS 陷阱 62）：本项目 GUI 测试从 cmd.exe 直接启动会 `0xC0000409` 假红。
> 本会话的 shell 已是 PowerShell，**直接运行即可**；若从 cmd 侧批量跑，务必套一层 pwsh。

---

## S0. 基线（改任何代码之前）

```powershell
python test/test_csg_new_gen_frame_gen.py     # 期望 144 项全绿
python test/test_csg_frame_gen_gui.py         # 期望 117 项全绿
python test/test_csg_new_gen.py               # 解析侧主回归
python release_check.py --skip-tests          # 期望 FAIL=0
```

- [ ] 记录三项基线的**实际项数与结论**（写进本文件下方的「基线记录」）
- [ ] 若基线非全绿 → **停下来先报告**，不要在此基础上开工

**回滚点 R0**：此处是干净起点。

---

## S1. 纯逻辑：`csg_link_frame_gen.py`（不碰 UI）

### S1.1 实现

1. `put_bits_le(buf, start_bit, width, value)` + `crc24_le` / `crc32_le` 薄封装（复用 `CSGNewGenParser._crc24` / `_crc32_ieee`）
2. `build_fc(...)`：固定部分 + 4 个变体装配（SOF-BPLC / SOF-ISAC 数据帧 / 信标 / SACK）
3. `build_pb(...)`：PBH + 块体（零填充）+ 保留 + PBCS
4. `build_mac_header(...)` / `build_mac_frame(...)`：长头 32B / 短头 12B + MSDU + CRC-32
5. `build_msdu(...)`：MSDU 头（18B/2B，随帧头类型）+ 载荷
6. `build_link_frame(...)`：按定界符类型编排 S3 的数据流（SOF/信标/SACK 三种帧尾）
7. `LinkFrameBuildResult` dataclass：`fc / pb / mac / msdu / mpdu / ed_frame` + `hex(layer)`
8. PB 大小 ↔ cmt_index/TMI 双向映射（按 `_get_pb_size` 反查）；Bitloading 走 `ISAC_BL_PB_SIZE_MAP`
9. 所有取值下拉候选**从解析器常量派生**（`DELIMITER_TYPE_MAP` / `MPDU_VERSION_MAP` / `MAC_HEADER_TYPE_MAP` / `MAC_VERSION_MAP` / `MSDU_TYPE_MAP` / `SEND_TYPE_MAP` / `BROADCAST_DIR_MAP` / `BEACON_PHASE_MAP` / `SACK_SNR_TYPE_MAP`）——**不新建第二份协议取值表**

### S1.2 测试 `test/test_csg_link_frame_gen.py`

- [ ] `import _path_setup  # noqa: E402,F401`（文件头，AGENTS §7 强制）
- [ ] **位打包互逆**：`_extract_bits(bytes(buf), s, w) == value`（随机/边界多组）
- [ ] **TEI 位序 oracle**：目的TEI=0x123、源TEI=0x456 → 帧内 `23 61 45`（文档表8 自带）
- [ ] **逐层回读**：`fc_only` 断言 FC 全部字段「解析值 == 输入值」；`pb_only` 断言 PBH 序列号/聚合标志 + PBCS「校验通过」；`mac_only` 断言 MAC 头 + MSDU 头
- [ ] **整帧回读**：`auto` 断言「定界符类型」行存在（**专门抓 C1 接入指示漏置**）、源/目的TEI、物理块个数、MSDU长度、「完整性校验(CRC-32)…校验通过」
- [ ] 4 个变体各至少 1 例；SOF 多 PB（2~4）1 例；长头/短头各 1 例
- [ ] 越界/非法值报 `FrameBuildError` 且有可读中文原因（PB 大小非法、TEI 超 12bit、SNR 类型超 2bit 等）
- [ ] PB 大小与 cmt_index 自洽：按大小反查后再组帧，回读**不出现**「PB大小推断」行
- [ ] 手工 HEX 载荷与测试模式载荷两条路径

### S1.3 变异反证（必须实测变红后还原）

- [ ] 把 C1 接入指示默认改为 0 → e2e 断言变红
- [ ] 把 FCCS 覆盖范围改成全 16 字节 → FCCS「校验通过」断言变红
- [ ] 把 MAC CRC-32 改成含 MAC 头 → 「完整性校验(CRC-32)」断言变红

**验证命令**
```powershell
python test/test_csg_link_frame_gen.py
```

**评审门 G1**：逐层 + 整帧回读全绿、变异反证三条实测变红并已还原、未触碰 `csg_new_gen_parser.py`。
**回滚点 R1**：删 `csg_link_frame_gen.py` + 该测试文件即可，无副作用。

---

## S2. 可复用折叠组件 `collapsible_section.py`

### S2.1 实现
1. `CollapsibleSection(QWidget)`：标题栏（`QToolButton` 可折叠 + 箭头）、内容布局、`set_title_suffix()`、`toggled` 信号
2. `expand_all()` / `collapse_all()`（供页面的「展开全部/收起全部」）
3. 状态可读写（供页面持久化）

### S2.2 测试
- [ ] 折叠/展开切换内容 `isVisible`；`toggled` 信号发射；`set_title_suffix` 生效
- [ ] **布局判据按 AGENTS 陷阱 63**：`show()` 之后再量，避免 headless 默认宽度 640 的假绿
- [ ] 按钮文字不裁字：`width() >= sizeHint().width()` 且未设 `maximumWidth` 上限

**验证命令**
```powershell
python test/test_collapsible_section.py
```

**评审门 G2**：组件独立可用、可被页面复用、测试含 show() 后的真实几何断言。
**回滚点 R2**：删该文件即可。

---

## S3. 页面改造（`csg_test_frame_gen_widget.py` + `frame_gen_widget.py`）

### S3.1 页面（`csg_test_frame_gen_widget.py`）
1. 顶层选择器：定界符类型 / 通道 / 标准版本号 / 输出层次（**旧三档保留 + 追加 `mpdu`**）
2. 五个 `CollapsibleSection`，标题后缀实时显示「N 字节 + HEX 缩略」
3. 按 `design.md` §6.3 实现联动可见性（逐条对照，尤其信标隐藏 ②③、SACK 隐藏 ②③④）
4. ④ 载荷来源二选一（测试模式 / 手工 HEX，手工优先）；模式表单沿用现有 `ModeField` 动态生成机制
5. `build()` 改走 `build_link_frame`；`output_bytes()` 支持 `mpdu`；`parse_rows()` 改为「分层概览 + 按输出层次回读」
6. **所有新增按钮走 `gui_utils.fit_btn_width`**（陷阱 63：写死宽度必裁字）
7. 折叠状态持久化 → `config.json`

### S3.2 接线（`frame_gen_widget.py`）
- `_do_realtime_update_csg` / `_generate_csg_frame`：改调新 `build()` / `output_bytes()`
- `_csg_parse_to_table(frame)`：按输出层次决定是否剥 ED（整帧时直接 `auto`）
- 保持 `CsgTestFrameGenWidget` 的公开接口与信号签名不变

### S3.3 测试
- [ ] 扩展 `test/test_csg_frame_gen_gui.py`：五层折叠存在/可折叠、联动可见性逐条、切变体后字段重建、输出层次各档（含 `mpdu`）、按钮不裁字
- [ ] **沙箱**：offscreen 测试必须同时 patch `main_gui.data_path` **与** `app_paths.data_path`（陷阱 42；只 patch 前者会把真实 `config.json` 写掉）
- [ ] 既有 117 项 + 144 项全绿

**验证命令**
```powershell
python test/test_csg_frame_gen_gui.py
python test/test_csg_new_gen_frame_gen.py
python test/test_gui_batch_perf.py
```

**评审门 G3**：联动规则逐条有断言；旧测试全绿；不裁字断言通过。
**回滚点 R3**：`git revert` 该阶段提交（页面 + 接线两文件回退）。

---

## S4. 文档与版本

- [ ] `main_gui.py:CHANGELOG` 头部新增条目（版本 / 日期 / 要点）
- [ ] `APP_VERSION` bump；`BUILD_DATE` 更新为当天
- [ ] `AGENTS.md`：§5.7 协议9 组帧段补链路层组帧说明；§8 新增陷阱条目（**接入指示必须为 1**、MSDU 头长度随帧头类型联动、三大校验覆盖范围）
- [ ] `README.md` 功能列表同步（如涉协议9 组帧描述）
- [ ] `release_check.py`：新测试登记进 `CORE_TESTS` / `GUI_TESTS`

**验证命令**
```powershell
python release_check.py --sync-iss
python release_check.py
```

**评审门 G4**：`release_check` FAIL=0（WARN 允许 BUILD_DATE 提醒）。
**回滚点 R4**：仅文档与版本号，可单独 revert。

---

## S5. 全量回归与收尾

```powershell
python release_check.py
python test/test_csg_new_gen.py
python test/test_csg_summary.py
python test/test_protocol_registry.py
python test/test_ed_ui_for_gw_hdc10.py
git diff --check
git status --short
```

- [ ] `release_check.py` FAIL=0
- [ ] 受影响的既有测试全绿（尤其解析侧与注册表）
- [ ] `git diff --check` 无空白错误
- [ ] 工作区无临时/调试残留文件（**调试脚本一律写 `$env:TEMP`，不入库**）
- [ ] 最终 diff 逐文件过一遍：只含本任务预期改动

---

## 基线记录

| 测试 | 基线项数 | 基线结论 | 完成后结论 |
| --- | --- | --- | --- |
| `test_csg_new_gen_frame_gen.py` | 待 S0 填写 | | |
| `test_csg_frame_gen_gui.py` | 待 S0 填写 | | |
| `test_csg_new_gen.py` | 待 S0 填写 | | |
| `release_check.py --skip-tests` | — | | |

## 风险与应对（执行期）

| 风险 | 应对 |
| --- | --- |
| 页面改造打破既有 117 项 GUI 测试 | S0 先跑基线；保留旧三档层次与控件对象名；每改一处立即跑该测试 |
| 大文件编辑误伤 | 用 `edit_file` 定向替换，不整文件重写 `csg_test_frame_gen_widget.py` |
| 沙箱漏 patch 写脏真实配置 | S3.3 明确双 patch；跑完检查 `git status` 无 `config.json` 变更 |
| 字段多易漏 | 逐表对照 `research/01`、`research/02`；测试逐字段断言回读值 |
| 卡住超过 2 轮 | 按 Trellis 流程转 `trellis-break-loop`，不要反复试同一手法 |
