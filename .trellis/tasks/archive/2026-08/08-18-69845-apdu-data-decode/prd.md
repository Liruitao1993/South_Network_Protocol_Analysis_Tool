# PRD：完善协议8（698.45）APDU 数据内容深度解析

## 背景

协议8（DL/T 698.45-2017）解析器当前存在缺口：**APDU 的数据内容（DATA）只做 A-XDR 原始解码**（如 `octet-string 12345678`），未按 698.45 数据项的业务格式解析（如电压应为 `220.5 V`、电能量应为 `123.45 kWh`、需量应含发生时间）。用户实测发现"只解析了部分内容，没有解析 APDU 的数据内容"。

## 目标

让协议8 的 GET-Response / SET-Request / ACTION / REPORT 中的 APDU 数据内容按 698.45 对象属性定义**深度解码为业务值**（数值+单位、时间、枚举说明等）。

## 现状分析（已完成）

| 层 | 现状 | 缺口 |
|---|---|---|
| 链路层（68 LL C SA CA HCS APDU FCS 16） | ✅ 完整 + CRC 校验 | 无 |
| APDU 结构（GET/SET/ACTION/REPORT） | ✅ 服务码/PIID/OAD/DAR 解析 | 无 |
| OAD 语义（OI→类→属性名） | ✅ `电压 (分相变量类) - 属性0` | 无 |
| **APDU 数据内容** | ❌ 仅 A-XDR 原始解码 | **未按属性格式解码业务值** |

关键资产：
- `dl_t698_45_axdr.py` AXDRCoder 已支持全部基础类型（array/structure/octet-string/double-long/Scaler_Unit/date_time_s/enum 等）
- `dl_t698_45_oi_lookup.py` OILookup 有 OI_NAME_MAP（OI→名称）、OI_TO_CLASS_ID、CLASS_ID_MAP（类→属性名）
- `extracted_classes.json` 29 个类，但**只含属性名，缺属性数据类型**
- 文档 `面向对象的用电信息数据交换协议(20210910).md` §8.2 定义各接口类属性数据类型（如电能量类属性2 = `array 电能量`）

## 需求

### R1 属性数据类型映射（核心）
- [ ] 从文档 §8.2 抽取**常用接口类**（电能量/最大需量/分相变量/功率/谐波变量/数据变量/事件对象/参数变量/冻结数据/采集/集合/控制等）的属性 → 数据类型映射
- [ ] 关键业务类型定义：
  - 电能量数组：`array 电能量`（double-long-unsigned，属性3 Scaler_Unit 换算）
  - 需量数组：`array 最大需量及发生时间`（structure { 需量值, date_time_s }）
  - 分相数值数组：`array 分相数值`（instance-specific，属性3 Scaler_Unit）
  - 功率数组：`array 数值`（总+分相）
  - date_time / date_time_s / date / time 时间类型格式化
  - 枚举类型转说明（如 DAR、单位等）
- [ ] 映射表数据结构：OI/属性 → {业务名称, 数据类型, 单位, 换算(Scaler_Unit), 说明}

### R2 数据内容深度解码
- [ ] 新增解码模块：给定 OAD + A-XDR 原始数据 → 业务值
  - 电能量：double-long-unsigned 值 + Scaler_Unit 换算 → `1234.56 kWh`
  - 电压/电流/功率：数值数组 + Scaler_Unit → 各相 `220.5 V`
  - 需量：值 + 发生时间 date_time_s → `12.34 kW @ 2024-05-01 12:00:00`
  - 时间类：date_time/date_time_s/date/time 格式化为可读字符串
  - 枚举：值 → 文档说明
- [ ] 解码结果与原始 A-XDR 解码**并存**（原始 hex + 业务值），不破坏现有结构

### R3 APDU 解析器接入
- [ ] GET-Response 数据（GetResponseNormal 的 Data）
- [ ] SET-Request 数据（SetRequestNormal 的 Data）
- [ ] ACTION-Request 参数 / ACTION-Response 响应数据
- [ ] REPORT-Notification 数据
- [ ] 多对象列表（NormalList）逐对象解码

### R4 GUI 展示
- [ ] `parse_to_table` 递归展示业务值（表格"解析值"列显示 `220.5 V`、`2024-05-01 12:00:00` 等）
- [ ] 不破坏现有字段（保留原始 A-XDR 行）

### R5 测试
- [ ] `test/test_dl_t698_45.py` 新增数据解码用例（硬编码帧 + 预期业务值）
- [ ] 覆盖：电能量读取、电压/电流读取、需量（含时间）、时间类型、枚举、多对象列表

## 验收标准

1. `python test/test_dl_t698_45.py` 全部通过（含新增用例）
2. 构造 GET-Response 电能量帧 → 解析值显示 `1234.56 kWh`（或按 Scaler_Unit 正确换算）
3. 构造 GET-Response 电压帧 → 解析值显示 `220.5 V`（分相数组逐相）
4. 构造需量帧 → 显示需量值 + 发生时间
5. 时间字段显示为可读日期时间
6. GUI 单帧解析（协议8）表格显示业务值，原始 hex 仍可见
7. 现有协议8 解析功能无回归

## 非目标
- 698.45 安全（SECURITY-APDU 密文解密）——需 ESAM 密钥，超出范围
- 全部 29 个接口类的完整数据格式——先覆盖常用测量/需量/事件/参数类，其余保留原始解码
- 冻结数据/记录型对象（GetRequestRecord）完整分页解析——先做 Normal/NormalList
