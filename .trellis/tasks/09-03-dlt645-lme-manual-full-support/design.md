# Design：DLT645 LME 自定义接口解析

## 数据契约

DLT645 数据域每个字节传输时 = 真实值 + 0x33。`DLT645Parser.parse` 已完成减 0x33，`result['data']` 为真实数据域，前 4 字节为 DI（小端：线上 DI0..DI3，`int.from_bytes(..., 'little')` 得到手册写法的 DI）。

- 单模 STA 版本：线上 `F9 AA FF 04` → DI 码 `04FFAAF9`
- 双模 STA 条目：线上 `01 DD 00 FF` → DI 码 `FF00DD01`

方向/功能由控制码决定（ctrl）：
- D7=DIR：0=主站请求，1=从站应答
- D0~D4=FUNC：0x11=读数据，0x14=写数据

分派矩阵：

| DI | DIR | FUNC | 数据体形态 | 解析函数 |
| --- | --- | --- | --- | --- |
| 04FFAAF9 | 1 | 0x11 | 251B 固定布局（4.2 表） | `parse_sta_version_single()` |
| 04FFAAF9 | 0 | 0x11 | 无数据体（请求只有 DI） | 标注"读请求，无数据单元" |
| FF00DD01 | 0 | 0x11 | 1B 条目信息(=0) + M + M×2B 请求头 | `parse_dual_entry_query_request()` |
| FF00DD01 | 1 | 0x11 | 1B(=0) + M + M×(2B TLV 头 + L 字节) | `parse_dual_entry_response()`（复用/重构现有 `parse_lme_info_entries`） |
| FF00DD01 | 0 | 0x14 | 1B(=0) + M + M×(2B TLV 头 + L 字节) | `parse_dual_entry_set_request()` |
| FF00DD01 | 1 | 0x14 | M + M×2B（数据ID6/分类ID3/结果7） | `parse_dual_entry_set_response()` |

位域定义（2 字节头，小端）：
- 请求头：bit0~5 数据ID(0~64)，bit6~8 分类ID(0~7)，bit9~15 保留(填0)
- TLV 头：bit0~5 数据ID，bit6~8 分类ID，bit9~10 编码格式(1 ASCII/2 BIN/3 BCD)，bit11~15 长度 L(0~31)
- 设置结果头：bit0~5 数据ID，bit6~8 分类ID，bit9~15 设置结果(0 成功/1 不支持/2 格式错/3 保存失败)

## 模块布局

全部 LME 645 扩展逻辑集中在已存在的 `lme_info_entry_parser.py`（archive_widget 已依赖，spec 打包已覆盖隐式 import）。新增/修改：

### `lme_info_entry_parser.py`（扩展）

保留现有公共函数 `parse_lme_info_entries()`、`format_lme_info_summary()`、`LME_INFO_ENTRIES` 不破坏签名。

新增：
- 常量 `DI_STA_VERSION_SINGLE = "04FFAAF9"`、`DI_DUAL_ENTRY = "FF00DD01"`
- 枚举 MAP：`BAUD_MAP`（4.3.3，0~12 → BR_300…BR_921600）、`PARITY_MAP`（0 无校验/1 奇/2 偶）、`PROVINCE_MAP`（手册 4.1 注 2）、`FUNC_SWITCH_BITS`（b0 即装即采/b1 万年历/b2 低功耗/b3 白名单）、`BAND_MAP`（0=10M/1=3M/2=2.2M/3=1.2M）、`SET_RESULT_MAP`
- `parse_sta_version_single(data: bytes) -> list[tuple[str,str,str]]`
  - 输入：减 0x33 后完整数据域（含 4B DI）；从 idx=4 开始按 4.2 表顺序切字段
  - 硬件信息段：先读 1B 长度 N，再读 N 字节 ASCII（正序），其后 2B CRC-16（展示 hex，说明"硬件信息 CRC-16，多项式手册未定义，仅展示"），再 1B Flash 容量
  - 字段值示例对齐手册：外部版本号 BIN 逆序 2B → `VXXYY`；版本日期 BCD 日月年 → `YY-MM-DD`；MCU BCD（次,主）→ `vXXXX`；应用层 1B ASCII 主版本 + 2B BCD 网省小版本 → 按手册注 2 拆平台/国网版本/APS/省份/次版本；N/P 层：1B 标志字符校验（应为 N/P，不符则提示）+ 2B BCD → `N XX.YY`
  - 频率：u16 小端 ×0.01Hz；占空比：u16 小端 ×0.1%
  - Flash 容量 n：n=255→未知；否则 `2^(n+1)` 字节（按 KB/MB/GB 友好显示）
  - 每字节不足时停止并追加 `⚠ 数据不完整（期望 N 字节，实际 M 字节）`
- `parse_dual_entry_query_request(data)`：跳过 4B DI + 1B 条目信息（校验=0，非 0 提示）+ M；循环 M 次读 2B 请求头，输出（条目名 或 `分类c 数据d`，值=`分类c/数据d`，说明含 ID 与名称）
- `parse_dual_entry_response(data)`：重构现有 `parse_lme_info_entries` 逻辑为返回 3 元组（名称、值、说明），说明列写编码格式(ASCII/BIN/BCD)+长度+原始 hex 片段；未知条目按头部编码解码（ASCII 尝试解码、BCD 转数字串、BIN hex）；条目名前缀分类名（基本信息/程序信息/硬件信息/网络信息/运行信息/CCO运行信息）
- `parse_dual_entry_set_request(data)`：同 TLV 结构，值显示同响应
- `parse_dual_entry_set_response(data)`：跳过 4B DI，读 M，循环 M 次 2B 结果头，输出条目名 + 结果码中文
- 语义格式化函数：`_format_semantic(category_id, data_id, encoding, data) -> str|None`，在现有 `_format_value` 之后做二次增强：
  - 分类0/数据15 本地接口默认信息：B0 波特率 MAP、B1 校验位 MAP
  - 分类0/数据9 功能开关：8B 逐位（手册仅定义低 4 位，其余标注保留）
  - 分类0/数据7 省份 MAP；数据8 应用方案；数据16 频段 MAP
  - 分类0/数据11 模块类型（已有 module_type MAP，保留）
  - 分类2/数据20 过零检测信息 13B：1B 标志（bit0~2 下降沿 A/B/C，bit3~5 上升沿 A/B/C）+ 6×2B（三相下降沿/上升沿频率 0.01Hz、占空比 0.1%）
  - 分类5/数据6 组网完成标识（0 未完成/1 阶段完成/2 白名单全部入网）
  - 其余条目维持现有 hex/数值显示
- 总入口 `parse_lme_dlt645(di_code: str, ctrl: int, data: bytes) -> tuple[list[tuple[str,str,str]], str]`：按分派矩阵返回 (fields 行, 接口名)；非 LME DI 返回 (None, "")。fields 行名称统一加缩进前缀（如 `"  ├ 外部厂商代码"`），与其他解析器子字段风格一致。

### `dlt645_parser.py`（修改）

- 顶部 `from lme_info_entry_parser import parse_lme_dlt645`（文件同目录，与 archive_widget 相同导入方式）
- DI 解析完成后（约现有 line 88 后），若 DI 命中两个 LME 码：
  - `di_desc` 使用 LME 接口中文名
  - try/except 调 `parse_lme_dlt645(di_code, ctrl, result['data'])`，将返回行 `extend` 进 `result['fields']`（替换/补充现有"数据内容"裸 hex 行：LME 帧不再追加裸 hex 行，改为解析行 + 一行原始数据 hex 备查）
  - 异常时回退现状（裸 hex + 备注"LME 解析异常: ..."），不影响 valid 判定
- 非 LME DI 路径零改动。

### `dlt645_di.json`（数据）

新增两条（与现有条目同结构）：
- `"04FFAAF9"`：name="查询HPLC单模STA详细信息(LME自定义)"，data_type="XX...XX"，length=255，备注 4.2
- `"FF00DD01"`：name="查询/设置HPLC双模STA详细信息(LME自定义)"，data_type="XX...XX"，length=255

### `validator/dlt645_validator.py`（修改）

长度合理性 WARN：data_len>200 时，解析数据域前 4B（减 0x33、小端）判 DI；若为两个 LME DI 之一则 PASS（消息"LME 自定义接口，数据域 N 字节"），否则维持原 WARN。

## 测试向量

手册 4.2 示例帧（数据域 58=0x3A 字节，线上原文）：

```
68 10 00 00 00 00 68 91 3A
2C DD 32 37 7B 7F 63 69 34 3D 5C 43 4C 34 34 74 35 34 81 38
35 83 34 43 45 73 88 82 96 A7 53 65 6C 53 65 63 64 6C 64 63
6D 64 63 6D 40 65 BB 43 33 65 BB 43 33 65 BB 43 33 65
CS 16
```

减 0x33 后手册期望值：厂商 LH、芯片 60、外部版本 V0A01、日期 191029、MCU V0101、APS A0102、NWK N0205、PHY P1001、DSP V4012、过零 07、三相频率 50Hz、占空比 50%。CS 由测试脚本按累加和计算后组帧。

双模 FF00DD01 用构造帧：查询请求(M=1, 分类0/数据15)、查询应答(M=1, TLV 波特率+校验位)、设置请求(M=1)、设置应答(结果=0)，脚本内组帧（加 0x33、算 CS）。

## 风险与回退

- `lme_info_entry_parser.py` 公共函数保持签名，archive_widget 路径零行为变化。
- 手册 4.3 条目表 HTML 残缺，现有 `LME_INFO_ENTRIES` 字典来源为"附录C/E"且更完整，以现有字典为准；仅做增量语义增强，不重排编号。
- CRC-16 多项式手册未定义 → 只展示不验算，避免误报。
- 回退点：所有新逻辑在 try/except 内，异常回退裸 hex 显示；删除 dlt645_parser.py 中分派块即完全恢复旧行为。
