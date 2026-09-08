# Research: DI 数据源可用性（能否驱动组帧下拉与字段模板）

- **Query**: `dlt645_di.json` 条目结构、`dlt645_di_lookup.py` 与自定义 json 接口/优先级；能否直接驱动组帧命令下拉与字段模板
- **Scope**: internal
- **Date**: 2026-09-07
- **来源**: `dlt645_di.json`（6600 行 / 1099 条 DI）、`dlt645_di_lookup.py`（212 行，全文）、`generate_dlt645_di.py`、`dlt645_di_custom.json`、`custom_di.json`

---

## 1. `dlt645_di.json` 条目结构（实测）

顶层（`:1-4`）：
```json
{ "description": "DLT645-2007 电表协议数据标识(DI)映射表 (含国网补遗扩展)",
  "version": "1.2.0",
  "di_map": { "00010000": {...}, ... } }
```

- **DI 条目总数：1099**（`di_map` 键数，实测 `len==1099`）。
- 键 = 8 位 hex DI 码（高字节在前写法，如 `"00010000"`）。
- **每条值仅含 4 个键**（实测 `{'data_type','length','unit','name'}）`：
```json
"00010000": { "name": "当前正向有功总电能", "unit": "kWh",
              "data_type": "XXXXXX.XX", "length": 4 }
```

### data_type 分布（实测 17 种）
| data_type | 条数 | 含义 |
|---|---|---|
| `XXXXXX.XX` | 740 | BCD 计量值（2 位小数） |
| `XXXXXX.XXXX` | 130 | BCD（4 位小数） |
| `XXX.X` | 129 | BCD（1 位小数） |
| `XX.XXXX,MDHM` | 32 | BCD + 月日时分后缀 |
| `XX.XXXX` | 22 | BCD |
| `X.XXX` | 8 | BCD |
| `''`（空） | 8 | 无格式 |
| `XXX.XXX` | 7 | BCD |
| `BS32` | 7 | 位串 32（状态字） |
| `XXXXXX` | 6 | BCD 整数 |
| `XX` | 2 | BCD |
| `BS96` | 2 | 位串 96 |
| `XX...XX` | 2 | BCD 变体 |
| `YYYYMMDD` | 1 | 日期 |
| `hhmmss` | 1 | 时间 |
| `NNNNNNNNNNNN` | 1 | 设定值 |
| `BS64` | 1 | 位串 64 |

### ⚠️ 缺失字段（实测确认）
- **无「读写属性」**（表 A.1 的读/写 `*` 列未被提取）。
- **无「分类/category」**（如 电能量/最大需量/变量/事件/参变量 等 645 分类）。
- **无「数据格式说明文本」**（仅 data_type 缩写 + unit）。

`generate_dlt645_di.py` 生成时只写入 name/unit/data_type/length 四字段，未解析表 A.1 的读写列。

---

## 2. `dlt645_di_lookup.py` 接口与优先级

类 `DLT645DILookup`（`:12`），单例 `get_dlt645_di_lookup()`（`:207`）。

### 加载与合并（优先级）
- `_load_di_map()`（`:21-42`）：
  - 标准 DI：`dlt645_di.json` 的 `di_map`（`:23,31`）。
  - 自定义 DI：`_load_custom_di()`（`:44-65`）读 `data_path('dlt645_di_custom.json')`（`:18`）。
  - **合并（`:39`）：`self._di_map = {**standard_dis, **custom_dis}`** → **自定义优先级高，同名 DI 覆盖标准**。
- `_load_custom_di`（`:52-62`）：自定义文件是**列表**，每项 `{di_code, name, unit, data_type, length}`（`di_code` upper）。

### 对外接口
| 方法 | 行号 | 用途 |
|---|---|---|
| `search(keyword)` | `:98-110` | 按 DI 码/名称/data_type 子串搜索，返回 `_data` 元组列表 |
| `get_di_info(di_code)` | `:112-114` | 取单条 dict（name/unit/data_type/length） |
| `data`（property） | `:116-119` | 全部 `(di_code, di_name, unit, data_type, desc, is_custom)` 6 元组列表 |
| `add_custom_di(di_code,name,unit,data_type,length)` | `:121-170` | 写自定义文件（校验 8 位 hex） |
| `delete_custom_di(di_code)` | `:172-200` | 删自定义条目 |

- `_rebuild_data_list()`（`:67-96`）：desc 拼 `数据类型: {data_type}, 长度: {length}字节[, 单位: {unit}]`；`is_custom` 标记。

### 与 `custom_di.json` 的区别（勿混淆）
- 根目录 `custom_di.json` 是**南网协议**用的不同格式：列表 `[{di3,di2,di1,di0,desc}]`（十进制分量），**与 dlt645 无关**。
- dlt645 的自定义文件是 `dlt645_di_custom.json`（经 `data_path` 定位到用户数据目录）。

---

## 3. 结论：能否直接驱动组帧下拉与字段模板？

### ✅ 能（读类命令）
`dlt645_di.json`（1099 条 + 自定义）**足以驱动**：
- **命令下拉/DI 选择**：`get_dlt645_di_lookup().data` 直接提供 (di_code, name, unit, data_type) 供下拉展示，`search()` 供检索。
- **读数据 11H / 读后续 12H 组帧**：只需 DI 4 字节（+SEQ），无需 data_type。
- **字段模板生成**：data_type + length 可推导应答数据域的 BCD 小数点/单位（复用 `decode_value` 逻辑做预览）。

**字段映射方案（读类）**：
| 组帧 UI 字段 | 数据源 |
|---|---|
| DI 下拉项文本 | `f"{di_code} {name}"`（来自 lookup.data） |
| DI 帧内字节 | `bytes.fromhex(di_code)[::-1]`（低字节在前） |
| 单位/格式提示 | `unit` / `data_type`（只读展示） |
| 数据长度校验 | `length` |

### ❌ 不能（写类命令 14H，需补读写属性）
**写数据 14H 组帧需要判断「哪些 DI 可写」**，而 json **无读写属性字段**：
- 缺口来源：`generate_dlt645_di.py` 未提取表 A.1 的读/写 `*` 列。
- 影响：无法自动过滤可写 DI；写数据的目标 DI 与写入值格式（data_type 反向 encode）需用户手填或另建可写白名单。

**补齐选项（需用户决定，见摘要）**：
1. 回 `DLT645-2007 多功能电表通信协议.pdf` 表 A.1 补「读写属性」列到 json（改 `generate_dlt645_di.py`，属产品代码改动，research 不做）。
2. 组帧写数据时不校验可写性，允许用户对任意 DI 组写帧（由用户负责）。
3. 新建独立「可写 DI 白名单」配置。

### 参变量/需量等特殊写目标
写数据常针对参变量类 DI（如密码、费率、需量周期），这些在 1099 条中混在一起且无分类标记，**无法自动区分**——同样依赖读写属性/分类补齐。

---

## Caveats

- 实测 version 为 **1.2.0**（含国网补遗扩展），非早期 1.1.0。
- data_type 有 8 条为空串、2 条为 `XX...XX` 变体，encode 时需容错回退（参照 `decode_value` 返回 None 时回退 hex 的处理）。
- `dlt645_di_custom.json` 走 `app_paths.data_path`（用户数据目录），非仓库根；打包/测试时注意路径。
- DI 分类（电能量/需量/变量/事件/参变量）若组帧 UI 需分组展示，json 无此信息，须从 DI 码高位规则推断或补数据。
