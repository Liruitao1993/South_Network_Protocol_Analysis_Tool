# 执行计划：DLT645 通用组帧器与 GUI/Web 集成

> 契约与集成点见 `design.md`；验收见 `prd.md`。本文件是有序执行清单 + 验证命令 + 回滚点。
> 每个 Step 结束都必须跑该步的验证命令并确认输出，未通过不得进入下一步。

## 环境注意（本机实测）

- Shell 是 **PowerShell 7**：不支持 `head` / `grep` / `cd /d`，用 `Select-Object` / `Select-String` / `Set-Location`
- 读取含中文的 git 输出**不要经 PowerShell 管道**（会按 GBK 解码产生二次编码乱码）；需字节级核验时用 `python -c` 捕获 stdout 以 `'wb'` 落盘
- 运行 Python 输出中文时加 `-X utf8`，避免控制台乱码影响判读
- 长命令（>500 字符）先写脚本文件再执行；临时脚本用完即删，勿留在仓库根

---

## Step 1：口径核对与掩码枚举（纯调研，不改产品代码）

- [ ] 1.1 枚举全部 `data_type` 掩码：`python -X utf8 -c "import json;m=json.load(open('dlt645_di.json',encoding='utf-8'))['di_map'];print(sorted({v['data_type'] for v in m.values()}))"`，把结果补进 `design.md` §2.3 表格（补齐剩余 3 种）
- [ ] 1.2 从 `DLT645-2007.md` 核对控制码位定义与各功能码数据域结构，与 `dlt645_parser.py` 现有口径（`func = ctrl & 0x1F`、`DIR = ctrl >> 7`、异常置 D6）交叉验证；冲突处以真实抓包 + parser 为准，并在 `design.md` §2.1 追加结论
- [ ] 1.3 核对 `XX.XXXX,MDHM` 掩码的字段序（查该掩码对应 DI 的文档定义）；确认不了则该掩码在 Step 3 回退裸 hex
- [ ] 1.4 用真实抓包 3 帧（见 `../09-07-eb-645-standard-fix/research/cs-and-scramble-evidence.md` §1）验算 `build_frame` 的目标口径，作为 golden sample 记入测试计划

**验证**：1.1 命令输出 17 项掩码；1.2/1.3 结论已写入 design.md
**回滚点**：无（未改代码）

---

## Step 2：`dlt645_data_codec.py` 新增 encode 系列（纯逻辑）

- [ ] 2.1 `encode_bcd_digits(text, mask) -> bytes`：十进制串 → BCD nibble → 低字节在前；非数字字符抛 `ValueError` 带中文消息
- [ ] 2.2 `encode_value(value, data_type, unit, di_name) -> bytes`：按掩码分派（bcd / bcd_date / bcd_mdhm / bitstring / ascii / raw / none）
- [ ] 2.3 `pack_write_request` / `pack_change_password` / `pack_clear_command`：严格作为既有 `split_*` 的逆运算实现，字段序对照 `dlt645_data_codec.py:211-262`
- [ ] 2.4 每个 encode 函数**紧邻**其 decode  counterpart 放置，docstring 标注「与 xxx 互为逆运算」

**验证**：
```
python -X utf8 -c "from dlt645_data_codec import encode_value, decode_value; v='123456.78'; b=encode_value(v,'XXXXXX.XX','kWh',''); print(b.hex(' '), decode_value(b,'XXXXXX.XX','kWh',''))"
python -m py_compile dlt645_data_codec.py
```
期望：`78 56 34 12` 且 decode 回读含 `123456.78`
**回滚点**：`git checkout dlt645_data_codec.py`（纯新增函数，不影响既有 decode）

---

## Step 3：新建 `dlt645_frame_gen.py` + `dlt645_frame_schema.py`（纯逻辑，无 Qt）

- [ ] 3.1 `DLT645FrameGenerator.build_control` / `build_frame` / `generate_frame`，签名严格按 `design.md` §2.1
- [ ] 3.2 地址处理：12 位十进制字符串 → 左补 0 → 反转 → 6B；非法输入（非数字/超 12 位）抛中文 `ValueError`
- [ ] 3.3 `DLT645_CMD_SCHEMA`（`design.md` §2.4）+ `build_di_fields(di_code)`（§2.3 掩码推导）；未识别掩码回退 `raw`
- [ ] 3.4 LME：`lme_info_entry_parser.py` 新增 `pack_query_request_header(cat, data_id) -> bytes`（数据ID 6bit / 分类ID 3bit / 保留 7bit，小端 2B），作为既有 `tlv_header` 的姊妹函数

**验证**（新建 `test/test_dlt645_frame_gen.py`，遵循项目约定：纯脚本 + `check()` 计数 + `import _path_setup` + UTF-8 stdout 兜底）：
```
python test/test_dlt645_frame_gen.py
```
必须覆盖：
- 与 `test/test_dlt645_lme.py:31` `build_frame` **逐字节一致**（AC2）
- 真实抓包 3 帧 golden sample 逐字节复现（Step 1.4）
- 17 种掩码 encode→decode **往返测试**（每种至少 1 例，含边界值 0 与最大值）
- 写数据/改密码/清零 `pack_*` → 既有 `split_*` 往返
- 非法输入分支（奇数 hex、地址超长、BCD 含非数字）
**回滚点**：删除两个新文件 + 测试文件

---

## Step 4：GUI 集成（`frame_gen_widget.py` + `main_gui.py`）

- [ ] 4.1 G1-G2：`set_protocol_mode` 白名单加 `"dlt645"`，隐藏面板列表补齐
- [ ] 4.2 G3-G4：命令下拉（请求/应答分组）+ DI 搜索下拉（**必须支持搜索过滤**，1099 项，沿用 `main_gui.py:3767` EB 查询区块交互模式）+ 动态字段容器 + `dlt645_config_group`（表地址 + 广播勾选 + 控制码只读展示）
- [ ] 4.3 G5-G7：生成分派 + `_generate_dlt645_frame` + 实时预览
- [ ] 4.4 M1-M3：`main_gui.py:3052` 可见性加 6、mode 映射加 `elif index == 6`、预设 tab 加 6
- [ ] 4.5 DI 长度不符时显示 WARN 文案但**不阻断**生成（prd OQ2）

**验证**：
```
python -m py_compile frame_gen_widget.py main_gui.py
$env:QT_QPA_PLATFORM="offscreen"; python test/test_frame_gen_dlt645_gui.py   # 新建，offscreen 冒烟
$env:QT_QPA_PLATFORM="offscreen"; python test/test_web_frame_gen_utils.py     # 既有回归
$env:QT_QPA_PLATFORM="offscreen"; python test/test_quick_parse_panel.py       # MainWindow 集成回归
```
offscreen 冒烟必须覆盖：协议切到 6 → 组帧 tab 可见 → 选命令 → DI 下拉可搜索 → 生成 → hex 与 Step 3 纯逻辑输出一致 → 切回协议 0/7/8 面板不串
**回滚点**：`git checkout frame_gen_widget.py main_gui.py`（**高风险**：M1/G5 写错会影响协议 0/7/8，回滚后必须重跑既有组帧回归）

---

## Step 5：预设命令库（`preset_buttons.py` + `DLT645_command.json`）

- [ ] 5.1 新建 `DLT645_command.json`（结构与 `DLT698_command.json` 一致）
- [ ] 5.2 P1：`set_protocol` 支持 `"dlt645"`——**注意 1.14.4 的教训**：698 曾因 `set_protocol` 静默忽略导致预设页看不到按钮，勿重犯
- [ ] 5.3 P2：`AddPresetDialog` 协议行显示「DLT645-2007 电表协议」；加载时按 protocol 过滤历史混入条目
- [ ] 5.4 M5：`main_gui.py` `_file_paths` 注册 `dlt645_command`，走 `app_paths.data_path`；frozen 下缺失时从 `_MEIPASS` 复制种子（沿用 `custom_di.json` 模式）
- [ ] 5.5 S1：`南网协议解析工具.spec` `datas` 增加 `DLT645_command.json`

**验证**：
```
python -m py_compile preset_buttons.py main_gui.py
$env:QT_QPA_PLATFORM="offscreen"; python test/test_preset_dlt645.py   # 新建：保存/加载/过滤/协议隔离
```
必须断言：dlt645 预设不会写进 `NW_command.json`/`GW_command.json`/`DLT698_command.json`（防串档，AC8 相关）
**回滚点**：删除新 json + `git checkout preset_buttons.py main_gui.py 南网协议解析工具.spec`

---

## Step 6：Web 集成（`reflex_web.py`）

- [ ] 6.1 W3：State 新增 `gen_dlt645_*` 变量（命名沿用 `gen_*` 约定）
- [ ] 6.2 W1：`_build_frame_bytes` 在 L2514 的 `raise ValueError` 之前加 `if p == 6:` 分支，**调用与 GUI 同一个 `DLT645FrameGenerator`**
- [ ] 6.3 W2/W4：预览分支 + 命令/DI 下拉数据源
- [ ] 6.4 W5：如需 645 专用辅助函数，放 `reflex_web/frame_gen_utils.py`，GUI 侧从同一文件导入（禁止第三份实现）

**验证**：
```
python test/test_web_frame_gen_utils.py     # 既有 63+ 项回归，必须全过
python test/test_dlt645_frame_gen.py        # 新增 Web/GUI 同输入同输出断言（AC7）
python reflex_web/run_app.py                # 手工：协议切 6 → 组帧 → 与 GUI 逐字节比对
```
**回滚点**：`git checkout reflex_web/reflex_web/reflex_web.py`

---

## Step 7：文档与版本

- [ ] 7.1 `main_gui.py:90-91`：`APP_VERSION` bump（功能变更）+ `BUILD_DATE` 改为打包当日
- [ ] 7.2 `main_gui.py` CHANGELOG 顶部新增条目，写明：协议 6 组帧（混合式命令组织 / 双向 / 真 BCD / LME 查询模板 / 不校验可写性）
- [ ] 7.3 `AGENTS.md`：§2 依赖与打包（新增 `DLT645_command.json` 资源）、§3 架构树（新增两个模块 + 数据文件）、§4.5 持久化表格
- [ ] 7.4 `README.md`：协议 6 组帧使用说明

**验证**：`python -c "import main_gui"` 不报错；CHANGELOG 首条版本号与 `APP_VERSION` 一致
**回滚点**：`git checkout` 对应文件

---

## Step 8：全量验收（对应 prd AC1-AC12）

```
python test/test_dlt645_frame_gen.py
python test/test_dlt645_lme.py
python test/test_web_frame_gen_utils.py
python test/test_gdw_fujian.py
python test/test_quick_parse_panel.py
python -m py_compile dlt645_frame_gen.py dlt645_frame_schema.py dlt645_data_codec.py lme_info_entry_parser.py frame_gen_widget.py main_gui.py preset_buttons.py reflex_web/reflex_web/reflex_web.py
```

- [ ] AC1-AC12 逐条核对并在 `prd.md` 勾选
- [ ] GUI 人工核验：协议 6 组帧页可用、DI 可搜索、广播勾选生效、发送/存预设/加测试方案三条路径通
- [ ] 打包冒烟（如需发版）：`pyinstaller 南网协议解析工具.spec --noconfirm`，确认 `DLT645_command.json` 被打进 `dist/`

---

## 提交策略

按 `design.md` §8 的粒度分 4 个提交，每个提交独立可验证：

1. `feat(dlt645): 帧生成器与 encode 系列（纯逻辑 + 单元测试）` — Step 2、3
2. `feat(dlt645): GUI 协议6 组帧页（混合式命令 + DI 驱动字段）` — Step 4
3. `feat(dlt645): 预设命令库与 Web 组帧分派` — Step 5、6
4. `docs(dlt645): 版本号/CHANGELOG/AGENTS/README 同步` — Step 7

**禁止**把格式化重排与功能改动混在同一提交（1.21.1 的教训：700+ 行格式化噪声淹没真实改动）。
