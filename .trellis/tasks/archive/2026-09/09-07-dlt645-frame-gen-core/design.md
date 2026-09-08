# 技术设计：DLT645 通用组帧器与 GUI/Web 集成

> 需求与验收见 `prd.md`；事实证据见 `research/`。本文件只记录技术设计：边界、契约、数据流、取舍、兼容与回滚。

## 1. 架构与模块边界

```
dlt645_frame_gen.py        ← 新建：帧封装唯一实现（地址序/控制码/+0x33/L/CS/68…16）
  └─ dlt645_data_codec.py  ← 扩展：新增 encode_* 系列，与既有 decode_* 成对同居
  └─ dlt645_di_lookup.py   ← 只读复用：DI → name/unit/data_type/length
  └─ lme_info_entry_parser.py ← 只读复用：CATEGORY_NAMES / LME_INFO_ENTRIES

dlt645_frame_schema.py     ← 新建：命令 schema + 掩码→字段模板推导（纯数据/纯函数，无 Qt）

frame_gen_widget.py        ← 扩展：新增 "dlt645" 模式（UI 层，只做取值与调用）
main_gui.py                ← 扩展：tab 可见性 + mode 映射 + 文件路径注册
preset_buttons.py          ← 扩展：set_protocol 支持 "dlt645"
DLT645_command.json        ← 新建：协议 6 预设命令库（运行时可写，app_paths 定位）

reflex_web/reflex_web/reflex_web.py ← 扩展：p==6 分派 + gen_dlt645_* 状态 + 命令下拉
```

**边界铁律**：帧字节的全部封装逻辑只存在于 `dlt645_frame_gen.py`。GUI 与 Web 都是它的调用方，**不得各自手写 +0x33 / CS / 地址反转**——这正是 EB 645 生成器出问题的根因（同一规则在 `frame_gen_widget.py:961`、`reflex_web.py:1591`、`archive_widget.py:849`、`test_dlt645_lme.py:31` 各写一遍，其中两份口径错误）。

## 2. 核心契约

### 2.1 `dlt645_frame_gen.py`

```python
class DLT645FrameGenerator:
    BROADCAST_ADDR = "999999999999"

    def build_control(self, dir_bit: int, func_code: int, err: bool = False) -> int:
        """控制码组装。dir_bit=D7；func_code 为 5 位（D4~D0）；err=True 置 D6。"""

    def build_frame(self, addr: str, ctrl: int, data: bytes, scramble: bool = True) -> bytes:
        """唯一封装入口。
        addr: 12 位十进制字符串（如 "000000000033"），内部反转为低字节在前的 6B BCD；
              不足 12 位左补 0；"999999999999" 即广播。
        data: **未加扰**的逻辑数据域（DI + 值）。
        scramble: True 时对 data 逐字节 +0x33（默认）；保留 False 仅用于测试对照，
                  UI 不暴露该参数。
        返回: 68 A0..A5 68 C L DATA(+0x33) CS 16，CS = sum(帧首…数据域末) & 0xFF。
        """

    def generate_frame(self, cmd_key, field_values, addr=None, broadcast=False) -> bytes:
        """与三套既有范本对齐的统一入口，供 GUI/Web 共用。
        cmd_key: (direction, func_code)，direction ∈ {"req", "rsp"}。
        field_values: dict，由 schema 字段名 → 用户输入字符串。
        """
```

**控制码口径**（禁止凭记忆，实施第一步必须交叉核对）：以 `dlt645_parser.py` 现有解析口径为准——`func = ctrl & 0x1F`（5 位功能码，D4~D0）、`DIR = ctrl >> 7`、异常应答置 D6。核对样本：`0x11` 读请求 / `0x91` 读应答 / `0xD1` 读异常应答（见 `test_dlt645_lme.py:327-332`）/ `0x14`·`0x94` 写 / `0x08` 广播校时 / `0x13`·`0x15` 地址。文档 `DLT645-2007.md` 5.2.3 控制码表为图片，若与上述冲突，**以真实抓包与 parser 为准并在代码注释标注差异**。

### 2.2 `dlt645_data_codec.py` 扩展（encode 与 decode 同文件成对）

新增函数必须与既有 decode 函数**互为逆运算**并成对测试：

| 新增 | 对应既有 decode | 说明 |
| --- | --- | --- |
| `encode_value(value, data_type, unit, di_name) -> bytes` | `decode_value(data, data_type, unit, di_name)` | 掩码驱动的值编码主入口 |
| `encode_bcd_digits(text, mask) -> bytes` | `_bcd_digits(b)` | 十进制串 → BCD nibble，按掩码定位小数点，低字节在前 |
| `encode_err(bits) -> bytes` | `decode_err(b)` | 本次仅需裸字节透传（见 prd OQ4 决定），保留函数位不实现下拉 |
| `pack_write_request(fields) -> bytes` | `split_write_request(data)` | 写数据 14H：DI + 密码权限 + P0P1P2 + 操作者代码 + 写入数据 |
| `pack_change_password(fields) -> bytes` | `split_change_password(data)` | 改密码 18H：DI + 旧密码组 + 新密码组 |
| `pack_clear_command(fields) -> bytes` | `split_clear_command(data)` | 清零 1AH/1BH：DI + 密码权限 + P0P1P2 + 操作者代码 + 清零对象 |

**关键差异（不可照抄范本）**：三套既有范本的 `bcd` 字段类型实为 `bytes.fromhex()`（`send_frame_lib.py:471-482`、`gdw_send_frame_lib.py:271-282`），把用户输入当已编码 hex；645 必须是**真 BCD**——输入 `123456.78`、掩码 `XXXXXX.XX` → 数字串 `12345678` → nibble → `78 56 34 12`（低字节在前）。

### 2.3 掩码 → 字段模板推导（`dlt645_frame_schema.py`）

1099 条 DI 只用 17 种 `data_type` 掩码（已实测统计）。推导规则：

| 掩码 | 编码类型 | 位数/小数点 | length | UI 控件 |
| --- | --- | --- | --- | --- |
| `XXXXXX.XX` | bcd | 8 位 / dp=2 | 4 | 十进制输入 + 单位标签 |
| `XXXXXX.XXXX` | bcd | 10 位 / dp=4 | 5 | 同上 |
| `XXX.X` | bcd | 4 位 / dp=1 | 2 | 同上 |
| `XX.XXXX` | bcd | 6 位 / dp=4 | 3 | 同上 |
| `X.XXX` | bcd | 4 位 / dp=3 | 2 | 同上 |
| `XXX.XXX` | bcd | 6 位 / dp=3 | 3 | 同上 |
| `XXXXXX` | bcd | 6 位 / dp=0 | 3 | 整数输入 |
| `XX` | bcd | 2 位 / dp=0 | 1 | 整数输入 |
| `YYYYMMDD` | bcd_date | 年月日 | 3 | 日期输入 |
| `XX.XXXX,MDHM` | bcd_mdhm | 月日时分（需查文档确认字段序） | 8 | 日期时间输入 |
| `BS32` | bitstring | 32 位 | 4 | hex 输入（4 字节） |
| `BS96` | bitstring | 96 位 | 12 | hex 输入（12 字节） |
| `XX...XX` | raw | 变长 | 251/255 | 裸 hex（LME 两个 DI 走结构化模板，见 §4） |
| `''`（空） | none | 无数据域 | 0 | 无输入 |
| 其余 3 种 | — | — | — | **实施第一步先枚举全部 17 种**（`set(v['data_type'] for v in di_map.values())`），逐一实现；未识别掩码一律回退 `raw` 裸 hex 并在 UI 标注「未识别格式，按裸字节填写」 |

`build_di_fields(di_code) -> list[dict]` 返回与既有范本同构的字段字典（键沿用 `name`/`type`/`default`/`unit`/`length`/`sub_fields`），使 `reflex_web/frame_gen_utils.py::collect_field_values` 可直接复用。

### 2.4 命令 schema

```python
DLT645_CMD_SCHEMA: dict[tuple[str, int], dict] = {
    ("req", 0x11): {"name": "读数据", "has_di": True,  "fields": [...]},
    ("req", 0x08): {"name": "广播校时", "has_di": False, "fields": [秒,分,时,日,月,星期]},
    ("req", 0x14): {"name": "写数据", "has_di": True,  "fields": [密码权限,P0,P1,P2,操作者代码,写入数据]},
    ("req", 0x18): {"name": "修改密码", ...}, ("req", 0x1A): {...}, ("req", 0x1B): {...},
    ("req", 0x13): {...}, ("req", 0x15): {...}, ("req", 0x16): {...}, ("req", 0x17): {...},
    ("req", 0x19): {...}, ("req", 0x12): {...},
    ("rsp", 0x91): {"name": "读数据应答", "has_di": True, "fields": [数据值]},
    ("rsp", 0x94): {"name": "写数据应答", "has_di": True, "fields": []},
    ("rsp", 0x93): {"name": "读地址应答", ...}, ("rsp", 0xD1): {"name": "异常应答", "fields": [ERR 裸字节]},
}
```

- `has_di=True` 的命令：DI 由下拉选择（1099 条，显示 `DI 名称`，支持搜索），选中后调 `build_di_fields` 动态生成字段表单
- `has_di=False` 的命令：固定字段模板
- 广播校时（08H）勾选「广播」时地址自动填 `999999999999`
- **不校验 DI 可写性**（prd OQ2 已决）：14H 允许任意 DI；仅当填入数据字节数 ≠ DI 声明 `length` 时给 WARN 文案，不阻断生成

## 3. 数据流

```
GUI:  命令下拉 → (dir,func) → schema → 字段表单
      DI 下拉 → dlt645_di_lookup → data_type 掩码 → build_di_fields → 动态字段
      用户输入 → _collect_values() → field_values dict
      → DLT645FrameGenerator.generate_frame(cmd_key, field_values, addr)
        → encode_value / pack_* → 逻辑数据域
        → build_frame(addr, ctrl, data) → +0x33 → L → CS → 68…16
      → result_hex → 预览/发送/存预设/加测试方案

Web:  同一条链路，State 存 gen_dlt645_* 变量，_build_frame_bytes 的 p==6 分支调同一生成器
```

**GUI 与 Web 必须调同一个生成器实例**，禁止在任一侧重新实现封装（AC7 用「同输入同输出」测试锁死）。

## 4. LME 查询请求结构化模板（prd OQ3 已决：仅 11H 查询）

- `04FFAAF9`：无数据单元 → 数据域仅 DI 4 字节
- `FF00DD01`：数据域 = 条目信息(1B=0) + M(1B) + M×2B 请求头
  - 请求头位域：**数据ID 6bit / 分类ID 3bit / 保留 7bit**（注意与应答头的 `数据ID 6bit / 分类ID 3bit / 编码 2bit / 长度 5bit` **不同**，不可复用同一打包函数）
  - UI：分类下拉（`CATEGORY_NAMES` 0~5）+ 条目多选（`LME_INFO_ENTRIES[分类]` 的条目名），M 自动 = 选中条目数；M=0 时标注「读取模块全部支持信息」
  - 打包函数放 `lme_info_entry_parser.py` 并命名 `pack_query_request_header(cat, data_id) -> bytes`，与既有解码逻辑同文件，作为 `tlv_header` 逆运算的姊妹函数
- **不做** LME 设置请求 14H（切后续任务）、**不做** `04FFAAF9` 应答反造

## 5. 集成点清单（逐处，含行号）

| # | 文件:位置 | 改动 |
| --- | --- | --- |
| G1 | `frame_gen_widget.py:3763-3766` | `set_protocol_mode` 白名单加 `"dlt645"`，docstring 同步 |
| G2 | `frame_gen_widget.py:3769-3777` | 隐藏面板列表加 `dlt645_combo` / `dlt645_config_group` |
| G3 | `frame_gen_widget.py` 命令选择区 | 新增 `dlt645_combo`（分组：请求/应答）+ DI 搜索下拉 + 动态字段容器 |
| G4 | `frame_gen_widget.py` config group | 新增 `dlt645_config_group`：表地址（12 位十进制）+「广播」勾选 + 控制码只读展示（DIR/功能码/异常位） |
| G5 | `frame_gen_widget.py:3141-3149` | 生成分派加 `elif self.protocol_mode == "dlt645": self._generate_dlt645_frame()` |
| G6 | `frame_gen_widget.py` 新增 `_generate_dlt645_frame` | 取值 → 生成器 → `result_hex`；异常走既有 `QMessageBox` 口径 |
| G7 | `frame_gen_widget.py` 实时预览 | 与既有模式一致的预览刷新 |
| M1 | `main_gui.py:3052` | `show_frame_gen = index in (0, 6, 7, 8)` |
| M2 | `main_gui.py:3055-3061` | mode 映射加 `elif index == 6: mode = "dlt645"` |
| M3 | `main_gui.py:3068` | 预设 tab 可见性加 6 |
| M4 | `main_gui.py:1058` 附近 | `_pending_frame_gen_mode` 默认值不变（`"south"`） |
| M5 | `main_gui.py` `_file_paths` / ConfigDialog | 注册 `dlt645_command` 路径（走 `app_paths.data_path`） |
| M6 | `main_gui.py:90-91` + CHANGELOG | 版本号与 CHANGELOG（发版时 `BUILD_DATE` 一并更新） |
| P1 | `preset_buttons.py` `set_protocol` | 支持 `"dlt645"`（此前 698 曾因静默忽略导致预设页看不到按钮，勿重犯） |
| P2 | `preset_buttons.py` `AddPresetDialog` | 协议行显示「DLT645-2007 电表协议」 |
| P3 | `DLT645_command.json` | 新建；加载时按 protocol 过滤，防串档 |
| W1 | `reflex_web.py:2514` 前 | `_build_frame_bytes` 加 `if p == 6:` 分支 |
| W2 | `reflex_web.py:2237-2252` | 组帧预览加 p==6 分支 |
| W3 | `reflex_web.py` State | 新增 `gen_dlt645_cmd` / `gen_dlt645_di` / `gen_dlt645_addr` / `gen_dlt645_broadcast` / 字段值列表，命名沿用 `gen_*` 约定 |
| W4 | `reflex_web.py` 命令下拉 | 数据源来自 `DLT645_CMD_SCHEMA` + `dlt645_di_lookup` |
| W5 | `reflex_web/frame_gen_utils.py` | 复用 `collect_field_values`，如需 645 专用辅助函数则加在此处（GUI 侧同文件导入，避免第三份实现） |
| S1 | `南网协议解析工具.spec` | `datas` 增加 `DLT645_command.json`；如新增模块被动态导入则补 `hiddenimports` |
| S2 | `reflex_web/requirements.in` | 无新增依赖（纯标准库 + 既有模块），确认后不改 |

## 6. 重要取舍

| 取舍 | 选择 | 理由 | 被拒方案 |
| --- | --- | --- | --- |
| 字段模板来源 | 掩码推导（17 种） | 1099 条 DI 零手写；掩码已含位数与小数点 | 手写 1099 份 schema（不可维护） |
| encode 函数位置 | 与 decode 同放 `dlt645_data_codec.py` | 强制成对维护，往返测试天然可写 | 新建 `dlt645_encode.py`（易与 decode 漂移） |
| 帧封装实现份数 | 唯一（`dlt645_frame_gen.py`） | EB 生成器的教训：多份实现导致口径分裂 | GUI/Web 各写一份 |
| 命令 key 形态 | `(direction, func_code)` 二元组 | 与 698 的 `(apdu_type, sub_type)` 同构，`collect_field_values` 可复用 | 字符串 key（丢失结构） |
| DI 可写性 | 不校验，长度不符给 WARN | prd OQ2 已决 | 补 1099 条读写属性 / 白名单 |
| 地址输入 | 单个 12 位十进制 + 广播勾选 | 645 只有单从站地址，无 src/dst 双地址 | 照抄南网/国网的双地址 config |

## 7. 兼容性与迁移

- **不改协议 0/7/8 任何路径**：`set_protocol_mode` 对未知模式已有 early return（`frame_gen_widget.py:3765-3766`），新增模式不影响既有分支
- **既有数据文件向后兼容**：`NW_command.json` / `GW_command.json` / `DLT698_command.json` / `test_plan.json` 结构不变；新增 `DLT645_command.json` 走 `app_paths.data_path`，frozen 下缺失时从 `_MEIPASS` 复制种子（沿用 `custom_di.json` 的既有模式）
- **`dlt645_di.json` 只读**：本任务不修改它（它由 `generate_dlt645_di.py` 生成，AGENTS.md §4.5 明令勿手改）
- **与兄弟任务 B 的关系**：B 建议在本任务之后实施并复用 `DLT645FrameGenerator`，避免第三份 645 封装实现

## 8. 回滚

- 新增文件（`dlt645_frame_gen.py`、`dlt645_frame_schema.py`、`DLT645_command.json`、`test/test_dlt645_frame_gen.py`）删除即回滚主体
- 集成点改动（G1-G7 / M1-M6 / P1-P3 / W1-W5 / S1）均为**加法**，回滚 = revert 单提交
- 高风险改动点：`main_gui.py:3052`（tab 可见性）与 `frame_gen_widget.py:3141`（生成分派）——这两处若写错会影响协议 0/7/8，实施后必须跑既有组帧回归
- 提交粒度建议：① 生成器 + codec encode + 单元测试（纯逻辑，无 UI）② schema + GUI 集成 ③ Web 集成 + 预设 ④ spec/版本/文档。每步独立可验证、可回滚

## 9. 遗留风险（实施时需处理，不改变 MVP 行为）

1. `XX.XXXX,MDHM` 掩码的字段序（月日时分 vs 分时日月）需查 `DLT645-2007.md` 对应 DI 定义确认；确认前该掩码回退裸 hex
2. 控制码 D4/D5 位语义文档为图片，以 parser + 真实抓包交叉验证（§2.1）
3. 剩余 3 种未列举掩码需在实施第一步枚举补齐
4. 1099 条 DI 下拉的 GUI 性能：需支持搜索过滤（沿用 EB 查询区块 `eb_di_search_input` 的既有交互模式，`main_gui.py:3767`），避免一次性渲染 1099 项卡顿
