# 实施计划：协议12 组帧接线 + 查询页覆盖 + 解析器对齐

对应 `prd.md`（R1~R7）与 `design.md`（契约 A~I）。
**每个 Block 完成后跑该 Block 的验证命令并全绿，才进入下一 Block。**

> 所有 Python 命令在 **WSL 里没有 python**，必须显式走 Windows PowerShell：
> `pwshu 'python -u test/xxx.py'`（本机全局规则）。
> GUI 测试统一 `pwshu '$env:QT_QPA_PLATFORM="offscreen"; python -u test/xxx.py'`。

---

## B0 基线冻结与备份（改代码前）

```bash
cd /mnt/e/python/南网解析工具
git status --short                      # 记录当前未提交状态（含两条无关改动线）
pwshu 'python -u test/test_modular_iface.py'        # 记录：46 项现状
pwshu 'python release_check.py --skip-tests'        # 记录基线 FAIL/WARN
mkdir -p .trellis/tasks/09-23-modular-iface-protocol/baseline
cp modular_iface_parser.py modular_iface_frame_gen.py \
   .trellis/tasks/09-23-modular-iface-protocol/baseline/
```

**门禁**：基线结果记录完毕；两个待重写文件已备份（备份目录**不进仓库**，`baseline/` 加入该任务目录但不提交）。

**清理**（本任务自带，不属其它线）：
```bash
rm -f test/_tmp_*.py test/_tmp_*.txt test/out*.txt
```
> 先逐个 `git log --oneline -1 -- <file>` 确认这些是调试残留、未被跟踪 ⇒ 直接删。
> `test/out*.txt` 若已被跟踪则不能用 `rm`，须 `git rm`。实测它们在 `git status` 里是 `??`（未跟踪）。

---

## B1 A-XDR 单源模块（契约 A）

新增 `modular_iface_axdr.py`：

1. `AxdrType` dataclass + `AXDR_TYPES` 表（`design.md` §2.1，**25 类，逐条抄表4**）
2. `AXDR_LENGTH_FOR_FIXED_IN_CHOICE = False`、`AXDR_VAR_LENGTH_BYTES = 1` 两个假设开关
3. `tag_of` / `type_of_tag` / `encode_value` / `decode_value` / `decode_choice` /
   `encode_sequence` / `decode_sequence`
4. `AxdrError`（唯一异常类型，消息含字段名与偏移）
5. 专用结构：`date_time`/`date_time_s`/`date`/`time`（表6~9，含 `FFFFH`/`FFH` 无效与 `day_of_week` 0=周日）、
   `Scaler_Unit`（表12）、`bit-string`、`array`/`structure` 递归
6. `verify_frame(frame) -> dict`（`design.md` §2.5，含 `axdr_tail`）

**测试第 1 段**（先写测试再写实现，TDD）：
- 表4 逐条：`tag_of` 全部 25 类与文档一致（含 `DT=0x50`、`Scaler_Unit=0x51`）
- **铁证 oracle**：`decode_value(bytes.fromhex("07E005130408 0500 00A4"), 0, "date_time")`
  → 2016-05-19 周四 08:05:00.164（与 698 附录 H.1.1 逐字节对齐）
- `encode_value` 的**大端**断言（`180` → `00B4`；`2016` → `07E0`）
- `Scaler_Unit`：换算 `0xFF`（-1）→ `10^-1`；单位 5 → 附录 M 的名称
- 越界 → `AxdrError`（含偏移），不返回半成品

```bash
pwshu 'python -u test/test_modular_iface_axdr.py'    # 新增测试文件
```

---

## B2 静态表模块（契约 C）

新增 `modular_iface_data.py`。**从文档现场抄录**（禁止从其它协议搬）：

1. `DTA1_NAMES`（0x0~0x9）、`DTA2_NAMES`（0/1/2）、`DT_NAMES`（附录 C 12 条 + 附录 G/J/K/L 11 条）
2. `DAR_NAMES` = **表11 只 4 项**（0 成功 / 1 拒绝读写 / 2 信息类未定义 / 255 其它）
3. `APDU_NAMES`（表13）、`CTRL_CODE_NAMES`（表2）、`DIR_PRM_MEANINGS`（表1）
4. `PHYSICAL_UNITS`（附录 M 表31 逐条）
5. `DEVICE_SUBIFACES`（附录 D/E/F/G/J/K/L 子接口表）、`VENDOR_ID`（附录 B）
6. `LINK_RESPONSE_FUNC_CONFIG`（表18 注）、`IFACE_TYPE_NAMES`（表18）
7. `decode_dt(raw2)` → 含 `dta1/dta2/dtb/名称`，**大端**

**测试第 2 段**：每张表**逐条对拍**（从文档现场抄的条数写进断言）：
- 附录 C 12 条 DT 码与名称逐一相等
- 附录 G/J/K/L 的 DT 逐一相等
- 附录 M 单位条数与若干代表项（V / A / W / kW·h / 单位 254 / 255）
- `DAR_NAMES` **恰为** `{0,1,2,255}`（这条专门抓「从别处搬表」的旧错）
- 附录 D~L 子接口各模块行数

```bash
pwshu 'python -u test/test_modular_iface.py'
```

---

## B3 解析器 APDU/DT 层重写（契约 B、D）

改 `modular_iface_parser.py`：

1. **删除** `DAR_NAMES`、`_take_axdr_uint`、`_take_axdr_string`
2. APDU 8 类改走 `modular_iface_axdr`（`design.md` §5 的布局表逐字实现）
3. `decode_dt` 走 `modular_iface_data.decode_dt`（大端）
4. `Get-Result` CHOICE：`00H`→DAR 查表11；`01H`→递归 `decode_choice(Data)`（25 分支）
5. 控制域逐字段行（表1+表2+FID）
6. `parse()` 收尾写**真实 meta**（`valid`/`fcs_ok`/`structure_ok`），删掉 `{...} if False else None`
7. `get_summary` 收口冗余判断
8. 表格行保留 `原始值`/`解析值`/`说明`/`偏移`/`长度` 五列

**测试第 3 段**：
- 组帧→解析闭环（走 B4 的 generator，缺则先用内联 hex）
- `axdr_tail == 0` 断言（编码假设自洽）
- L 与实际不符 / FCS 不符 / 截断帧 → **仍输出已解析字段** + 醒目错误行（§8 陷阱 23），不空白
- 控制域 4 种 DIR/PRM 组合的意义文案
- `parse()` meta 的 `fcs_ok` 真值可被读到（抓死代码回归）

```bash
pwshu 'python -u test/test_modular_iface.py'
```

---

## B4 组帧重写（契约 E）

改 `modular_iface_frame_gen.py`：

1. `build_control` / `build_frame` / `build_ack` / `build_nak` / `build_info`
2. 8 类 APDU builder（走 `modular_iface_axdr`）
3. `FRAME_TEMPLATES` ≥ 8 条 + `build_from_template`
4. 数据域 > 4095 → 可读错误（不截断）

**测试第 4 段**：
- 逐模板：`parse(build(t))` 字段与原参数一致、`axdr_tail == 0`、`fcs_ok is True`
- ACK：数据域空、L=0、整帧 = 8 字节
- NAK：L=2、错误码 2 字节
- 超长数据域报错

```bash
pwshu 'python -u test/test_modular_iface.py'
```

---

## B5 校验器收口

改 `validator/modular_iface_validator.py`：FCS 判定、L 一致性、保留位非 0 提示、
`structure_ok` 与解析器 meta 同源。

```bash
pwshu 'python -u test/test_modular_iface.py'
pwshu 'python -u test/test_protocol_registry.py'
```

---

## B6 注册表 + 组帧页接线（契约 F / R1）

1. `protocol_registry.py`：index 12 的 `frame_gen_mode="modular"`、`preset_mode="modular"`
2. `frame_gen_widget.py`：按 `design.md` §7 的 **12 个分派点逐处**加 modular 分支
3. 新增 modular 专属控件容器（控制域组 / APDU 组 / 结果区），按 `protocol_mode` 显隐
4. 预览用 `ModularIfaceParser.parse_to_table`；串口回包解析走 `ModularIfaceParser`

**测试第 5 段**（offscreen）：
- `FrameGenWidget` + `set_protocol_mode("modular")` → 点「生成帧」（真实 `btn.click()`）→ 输出非空且自解析通过
- 4 个既有模式**逐一**冒烟：切模式后字段模板可见性与改动前一致（抓「第 5 模式污染」）
- 未指定协议时默认态不变
- 串口回包分派：modular 输入喂给解析器后不落到国网/南网（断言表头/行名特征）

```bash
pwshu 'python -u test/test_dlt645_frame_gen_gui.py'   # 既有回归
pwshu 'python -u test/test_modular_iface.py'
```

---

## B7 预设命令（契约 G / R5）

改 `preset_buttons.py`：modular 模式 + `data_path("modular_command.json")` + 5 条种子。

**测试第 6 段**：种子文件缺失时写入并可读回；条目往返不丢字段；点条目填入输入框（offscreen）。

```bash
pwshu 'python -u test/test_modular_iface.py'
```

---

## B8 查询页重做（契约 H / R2）

重做 `main_gui._create_modular_iface_lookup_content` 为 7 组（`design.md` §9），
数据只来自 `modular_iface_data.py`；搜索匹配所有列并显示「匹配 N / 共 M 条」。

**测试第 7 段**（offscreen 构建 MainWindow）：
- 切到协议12 → 查询页出现 7 组
- 每组行数 = `modular_iface_data` 的条数（对拍）
- 搜索 `0000` / `V` / `0x50` 命中数与预期一致；清空搜索恢复全量
- 表格控件类型为 `ZoomableTableWidget`（风格约定）

```bash
pwshu 'python -u test/test_modular_iface.py'
```

---

## B9 批量摘要（契约 I / R4）

`main_gui._get_summary_from_table_data` 加 `proto == 12` 分支走 `get_summary`；
空结果兜底 `协议12 帧(长度 N)`。

**测试第 8 段**：ACK / NAK / GetRequest / GetResponse 四种帧的摘要非空且含方向+控制码名+APDU 名；
兜底分支在空表时也不返回空串。

```bash
pwshu 'python -u test/test_modular_iface.py'
```

---

## B10 打包与文档收尾（R6 / R3.x）

1. `南网协议解析工具.spec` `hiddenimports` 补 `modular_iface_parser`、`modular_iface_frame_gen`、
   `modular_iface_axdr`、`modular_iface_data`、`validator.modular_iface_validator`
   （`make_validator` 走 importlib，打包器看不到）
2. `AGENTS.md`：§1 协议表（补校验算法说明）、§2/§3 文件清单（新增 2 个文件）、
   **§5 新增「协议12」小节**（文档路径 + 已实现范围 + `frame_gen_mode` + 查询页 + 测试 +
   **A-XDR 依据与切换方法** + 文档矛盾记录）、§7 测试清单、§8 新增陷阱条目、§10 版本摘要
3. `main_gui.py`：`CHANGELOG` 新条目、`APP_VERSION` 递增、`BUILD_DATE` 更新
4. `pwshu 'python release_check.py --sync-iss'`
5. 清理 B0 之外的临时产物；确认 `git status` 只剩预期文件

**新的 AGENTS.md 陷阱条目必须写入的内容**（避免后续会话再犯）：
- 协议12 的 A-XDR 是**大端**，链路层是**小端**（两者不可互相套用）
- 定长类型在 SEQUENCE 内无 tag/无长度（附 698 附录 H.1.1 实证）
- `DAR` 只有表11 的 4 个值，**不要**从其它协议借 DAR 表
- 文档**无示例帧** ⇒ 编码假设集中在 `modular_iface_axdr.py` 的两个开关；
  拿到真实帧先用 `verify_frame()['axdr_tail']` 判定，再决定是否翻转开关
- 文档自身矛盾：§6.3.9 写「单位见附录 L」（实为附录 M）；附录 K.2/L.2 互相引用「见 K.3」

---

## 顺序与回滚点

| Block | 依赖 | 可独立回滚 | 回滚方式 |
| --- | --- | --- | --- |
| B0 | — | 是 | 从 `baseline/` 恢复两个文件 |
| B1 | B0 | 是 | 删 `modular_iface_axdr.py` |
| B2 | B0 | 是 | 删 `modular_iface_data.py` |
| B3 | B1 B2 | 是 | 从 `baseline/` 恢复 `modular_iface_parser.py` |
| B4 | B1 | 是 | 从 `baseline/` 恢复 `modular_iface_frame_gen.py` |
| B5 | B3 B4 | 是 | `git checkout -- validator/modular_iface_validator.py`（未跟踪则删） |
| B6 | B4 | 是（纯增量） | `frame_gen_mode=None` + `git checkout -- frame_gen_widget.py` |
| B7 | B4 | 是（纯增量） | `preset_mode=None` + `git checkout -- preset_buttons.py` |
| B8 | B2 | 是 | `git checkout -- main_gui.py` 后重做（注意该文件另有无关改动，**不要整体 checkout**；用逐 hunk 回退） |
| B9 | B3 | 是 | 同上，逐 hunk |
| B10 | 全部 | 部分 | spec/AGENTS 可逐个文件回退；版本号回退需与 CHANGELOG 同步 |

> ⚠ `main_gui.py` / `test/test_protocol_registry.py` 等文件含**其它两条改动线**的内容，
> **禁止** `git checkout -- <file>` 整体回退；只用精确 hunk 撤销。

## `task.py start` 前的最终检查

- [x] `prd.md` / `design.md` / `implement.md` 已产出（待用户评审）
- [ ] B0 基线已记录
- [ ] 三条铁证已在 `design.md` §0 固化（A-XDR 大端 / 文档无示例帧 / 链路层小端）
- [ ] 备份目录 `baseline/` 已建立
- [ ] 确认 `main_gui.py` 的无关改动线不会被误回退（§13 回滚表已注明）
