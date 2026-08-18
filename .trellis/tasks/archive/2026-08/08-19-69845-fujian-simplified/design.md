# Design: 协议8 福建简化698（choice=0x02 List 结构）解析扩展

## 1. 现状

`dl_t698_45_apdu_parser.py` (DLT69845APDUParser) 的服务解析方法：
- `_parse_set_request`: choice=0x01 (SetRequestNormal) 已实现；**0x02 (SetRequestNormalList) 缺失**
- `_parse_set_response`: choice=0x01 已实现；**0x02 缺失**
- `_parse_action_request`: choice=0x01 (ActionRequestNormal) 已实现；**0x02 (ActionRequestNormalList) 缺失**
- `_parse_action_response`: choice=0x01 已实现；**0x02 缺失**
- `_parse_report_notification`: choice=0x01 Normal 无 count 前缀支持；choice=0x02 Simplify 循环 A-XDR 解码
- `_parse_report_response`: choice=0x01/0x02 是 while 循环读 OAD，**无 count 前缀语义**
- `_decode_oad_business` (1.14.1 新增)：按 class_id+attr 模板解码业务值，但对 EB OI（0xEB03 等）无 class 映射 → 返回 None

资源：
- `gdw_eb_di_lookup.py` EBDILookup：`get('EB030110')` → {名称/格式/长度/单位/功能}，57 项
- `gdw_eb_di_fields.py` EB_DI_FIELDS：42 项数据内容字段 schema（enum/uint/bcd/bcd_time/ascii/hex/list），`encode_eb_di_data` 编码
- `dl_t698_45_axdr.py` AXDRCoder：A-XDR 解码（octet-string/array/structure 等）

## 2. 结构定义（依据 V3.42 文档 A.2 + 标准 698.45 表45/61/69）

### 2.1 SET-Request choice=0x02 SetRequestNormalList
```
服务码(06) + choice(02) + PIID(1) + count(1) + [OAD(4) + Data(A-XDR)] × count
```
文档示例：`06 02 00 01 EB 03 01 10 09 03 00 00 05 00`
→ choice=02, PIID=00, count=01, OAD=EB030110, Data=octet-string(09 03 00 00 05)

### 2.2 SET-Response choice=0x02 SetResponseNormalList
```
服务码(86) + choice(02) + PIID-ACD(1) + count(1) + [OAD(4) + 结果(1: 00确认/FF否认)] × count
```
文档示例：`86 02 00 01 EB 03 01 10 00 00 00` → OAD=EB030110, 结果=00
否认：`86 02 00 01 EB 03 01 10 FF 00 00` → 结果=FF

### 2.3 ACTION-Request choice=0x02 ActionRequestNormalList
```
服务码(07) + choice(02) + PIID(1) + count(1) + [OMD(4) + Data(A-XDR, 可空)] × count
```
文档示例（读取）：`07 02 00 01 EB 03 01 10 00 00` → OMD=EB030110, Data=空
用户实测：`07 02 00 01 EB 03 03 07 09 08 1C 07 E8 0B 1B 0A 20 00 00`
→ choice=02, PIID=00, count=01, OMD=EB030307, Data=octet-string(09 08 1C 07 E8 0B 1B 0A 20 00)

### 2.4 ACTION-Response choice=0x02 ActionResponseNormalList
```
服务码(87) + choice(02) + PIID-ACD(1) + count(1) + [OMD(4) + DAR(1) + [响应数据(A-XDR)]] × count
```
文档示例：`87 02 00 01 EB 03 01 10 00 09 03 01 00 05 00 00`
→ OMD=EB030110, DAR=00(成功), 响应数据=octet-string(09 03 01 00 05)

### 2.5 REPORT-Notification choice=0x01 带 count
```
服务码(88) + choice(01) + PIID-ACD(1) + count(1) + [OAD(4) + Data(A-XDR)] × count
```
文档示例：`88 01 00 01 EB 03 00 02 01 09 08 00 01 11 22 33 44 55 66 00 00`
→ PIID-ACD=00, count=01, OAD=EB030002, Data=octet-string(09 08 00 01 11 22 33 44 55 66)

### 2.6 REPORT-Response choice=0x01 带 count
```
服务码(08) + choice(01) + PIID-ACD(1) + count(1) + [OAD(4) + 结果(1)] × count
```
文档示例：`08 01 00 01 EB 03 00 02 00` → PIID-ACD=00, count=01, OAD=EB030002, 结果=00

## 3. 实现方案

### 3.1 APDU 解析器（dl_t698_45_apdu_parser.py）

新增统一辅助方法（减少重复）：

```python
def _parse_eb_oad(self, oad_dict: dict) -> dict:
    """EB OI（0xEB00~0xEBFF）附加中文名：OAD 4字节原样即 EB 数据标识 DI3DI2DI1DI0"""
    # oad_dict 已含 解析值.OI/属性编号/元素索引；若 OI 高字节 0xEB →
    # 原样 4 字节 hex 查 gdw_eb_di_lookup，说明 += EB 名称/格式/单位

def _enrich_eb_data(self, oad: dict, data: dict) -> Optional[dict]:
    """EB 数据内容解码：按 EB_DI_FIELDS 字段 schema 解 octet-string 数据字节"""
    # 提取 OAD 4 字节 hex → DI 键（如 EB030110）→ EB_DI_FIELDS 字段列表
    # data.解析值 为 hex 字符串时按字段 schema 逐个解码（enum→名称/uint→值/bcd→BCD）
    # 返回 {字段名: 值}，失败返回 None
```

各方法扩展：

|方法|改动|
|---|---|
|`_parse_set_request`|choice==0x02 分支：PIID + count + [OAD + Data]×count，每项 `_enrich_eb_data` → `数据业务`|
|`_parse_set_response`|choice==0x02 分支：PIID-ACD + count + [OAD + 结果]×count|
|`_parse_action_request`|choice==0x02 分支：PIID + count + [OMD + Data]×count，OMD 含 EB 名，Data 业务解码|
|`_parse_action_response`|choice==0x02 分支：PIID-ACD + count + [OMD + DAR + [响应数据]]×count|
|`_parse_report_notification`|choice==0x01 改带 count：PIID-ACD + count + [OAD + Data]×count|
|`_parse_report_response`|choice==0x01/0x02 改带 count：PIID-ACD + count + [OAD + 结果]×count|

### 3.2 EB 数据内容解码（dl_t698_45_data_decode.py 或新方法）

方案：在 `dl_t698_45_apdu_parser.py` 内新增 `_decode_eb_data_content(di_hex, data_dict)`：

1. `di_hex = oad 4 字节 hex.upper()`（EB 数据标识）
2. `schema = EB_DI_FIELDS.get(di_hex)` — 42 项字段定义（gdw_eb_di_fields.py）
3. 数据字节 = A-XDR octet-string 的 解析值 hex → bytes
4. 按字段顺序逐个解码：enum（码→名称）、uintN（小端→值）、bcd（BCD→数字）、bcd_time（→日期时间）、ascii（→字符串）、hex（原样）、bs8（位说明）
5. 返回 `{字段名: 解码值}` dict；失败返回 None

补充：EB_DI_FIELDS 中无 schema 的 EB 项（如 EB030307 组合格式），返回原始 hex + EB 名称（`gdw_eb_di_lookup.get_name`），保证用户可见内容。

### 3.3 OAD/OMD 中文名增强

`_parse_oad_raw` / `_parse_omd_raw` 在 `_enrich_oad`/`_enrich_omd` 之后：若 OI 高字节 == 0xEB，用 OAD/OMD 4 字节原样 hex 查 `gdw_eb_di_lookup.get`，`说明` 追加 EB 名称。

实现位置：`_decode_oad_business` 中扩展，或新方法 `_enrich_eb_oad(oad_dict)`。

## 4. 兼容性

- 标准 698.45 帧（choice=0x01 Normal）解析路径不变——仅新增 choice==0x02 分支
- REPORT 带 count 是**行为变更**：现有无 count 的简化处理改为严格按 count 解析。检查 `test_dl_t698_45.py` 现有 REPORT 用例是否受影响（EB 上报帧 `88 01 00 01 EB 03 00 02 01 09 08...` 本身带 count，当前解析会错位，修复后正确）
- `_add_apdu_to_table` 通用递归自动展示新键（列表 → 逐项展开），无需改 GUI

## 5. 风险

- REPORT 现有行为若被其他用例依赖（无 count 的 REPORT Normal 帧），需回归确认。标准 ReportNotificationNormal 无 count；福建带 count。处理：count 语义按文档（福建）实现，标准无 count 帧仍能解析（count 字节 = OAD 高字节场景不冲突？）——**验证：`88 01 00 01 EB 03 00 02 01 09...` 中 PIID-ACD=00 后 count=01，若标准帧无 count 则 PIID-ACD 后直接 OAD=00 EB 03 00 → OI=0x00EB**。福建示例 count 位取值 01，标准 OAD 高字节 0x00→OI=0x00EB 与 0xEB00 区分；以文档示例为准实现 count。
- EB_DI_FIELDS 字段解码对变长字段（list/多段）需要长度协商逻辑
