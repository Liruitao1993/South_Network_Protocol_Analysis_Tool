# DL/T 698.45 协议解析器设计规格

## 1. 概述

### 1.1 背景
本项目是一个多协议电力通信帧解析工具（PySide6 GUI），已支持南网（CSG）、国网（GDW 10376）、PLC RF、HDLC/DLMS、DLT645-2007 等协议。现需新增 **DL/T 698.45-2017 / Q/GDW 11778-2017**（面向对象的用电信息数据交换协议）的完整支持。

### 1.2 目标
- 实现 698.45 协议的**链路层 + 应用层全解析**，包括 APDU 服务类型识别、OAD/OMD 结构解析、数据类型解码。
- 提供**帧生成（组帧）**功能，支持通过 GUI 选择服务类型、填写参数后自动生成完整帧。
- 提供 **OAD/OMD 查询**功能，辅助理解对象标识含义。
- 基础支持 **SECURITY-APDU** 结构解析（不解密）。
- 遵循现有项目架构风格，保持与其他解析器一致的接口和行为。

### 1.3 参考文档
- `面向对象的用电信息数据交换协议(20210910).md` — 主协议规范
- CLAUDE.md — 项目架构指南

---

## 2. 需求规格

### 2.1 功能需求

| ID | 需求 | 优先级 |
|----|------|--------|
| F1 | 解析 698.45 链路层帧结构（68...16），提取各域值和校验结果 | P0 |
| F2 | 解析 APDU 骨架：识别 LINK/Client/Server/SECURITY 类型及服务子类型 | P0 |
| F3 | 解析 OAD（对象属性描述符）、OMD（对象方法描述符）结构 | P0 |
| F4 | A-XDR 数据类型解码：integer、long-unsigned、octet-string、date_time、enum、array、structure、float32、float64、Scaler_Unit 等 | P0 |
| F5 | 帧生成功能：根据服务类型和参数生成完整帧（含 HCS/FCS 计算） | P0 |
| F6 | OI 查询：输入 OI 查询接口类名称、属性列表、方法列表 | P1 |
| F7 | SECURITY-APDU 基础结构解析（安全类型、明文/密文长度、MAC 长度） | P1 |
| F8 | 协议验证器：校验起始字符、长度域、HCS、FCS | P1 |
| F9 | 集成到 main_gui.py：协议选择、单帧解析、批量解析、查找页 | P0 |

### 2.2 非功能需求
- 遵循现有 `parse_to_table()` 返回格式：`(字段名, 原始值, 解析值, 说明, byte_start, byte_end)`
- 遵循现有 `BaseValidator` 接口进行协议校验
- 保持与现有协议解析器一致的异常处理方式
- 新模块独立成文件，不污染已有解析器

---

## 3. 架构设计

### 3.1 分层架构

```
┌─────────────────────────────────────────┐
│  GUI (main_gui.py)                      │
│  - 协议选择 / 单帧解析 / 批量解析         │
│  - 帧生成页面 / OAD 查询页面              │
├─────────────────────────────────────────┤
│  dl_t698_45_parser.py                   │
│  链路层解析器：68...16 帧结构             │
│  (长度域 / 控制域 / 地址域 / HCS / FCS)  │
├─────────────────────────────────────────┤
│  dl_t698_45_apdu_parser.py              │
│  APDU 解析器：LINK / Client / Server     │
│  / SECURITY 服务识别与结构解析            │
├─────────────────────────────────────────┤
│  dl_t698_45_axdr.py                     │
│  A-XDR 编解码器：通用数据类型编解码        │
├─────────────────────────────────────────┤
│  dl_t698_45_oi_lookup.py                │
│  OI 语义查询：对象名称 / 属性 / 方法       │
├─────────────────────────────────────────┤
│  dl_t698_45_frame_gen.py                │
│  帧生成逻辑：根据参数组装完整帧            │
├─────────────────────────────────────────┤
│  dl_t698_45_frame_schema.py             │
│  帧生成 UI Schema 定义                   │
├─────────────────────────────────────────┤
│  validator/dl_t698_45_validator.py      │
│  协议验证器                              │
└─────────────────────────────────────────┘
```

### 3.2 数据流

```
输入: 十六进制字符串 / bytes
  ↓
_dl_t698_45_parser.parse_to_table(frame_bytes)
  → 链路层表格数据（起始符、长度域、控制域、地址域、HCS、链路用户数据、FCS、结束符）
  → 提取链路用户数据域作为 APDU 字节
  ↓
_dl_t698_45_apdu_parser.parse(apdu_bytes)
  → 识别 APDU 类型（LINK/Client/Server/SECURITY）
  → 根据服务类型递归调用 A-XDR 解码
  ↓
_dl_t698_45_axdr.decode(data, tag_hint=None)
  → 返回 (解码结果字典, 消耗字节数)
  → 支持嵌套 structure / array / choice
  ↓
_dl_t698_45_oi_lookup.get_oi_info(oi)
  → 返回 {class_name, attributes, methods} 或 None
```

---

## 4. 模块详细设计

### 4.1 dl_t698_45_parser.py — 链路层解析器

**职责**：解析 `68 ... 16` 格式的完整链路层帧。

**帧结构**（698.45 数据链路层）：

| 域 | 长度 | 说明 |
|----|------|------|
| 起始字符 | 1 | `0x68` |
| 长度域 L | 2 | BIN 编码，bit0~bit13 为长度值，bit14 为单位标志 |
| 控制域 C | 1 | DIR/PRM/分帧标志/SC/功能码 |
| 地址域 A | 变长 | SA（地址特征 + N 字节地址）+ CA（1 字节） |
| 帧头校验 HCS | 2 | X-25 FCS-16，覆盖起始字符后到 HCS 前的所有字节 |
| 链路用户数据 | 变长 | APDU 或 APDU 分帧片段 |
| 帧校验 FCS | 2 | X-25 FCS-16，覆盖起始字符后到 FCS 前的所有字节 |
| 结束字符 | 1 | `0x16` |

**核心方法**：

```python
class DLT69845Parser:
    def parse_to_table(self, frame_bytes: bytes) -> list:
        """解析为 (字段名, 原始值, 解析值, 说明, byte_start, byte_end) 列表"""

    def _parse_length(self, data: bytes) -> dict:
        """解析长度域 L"""

    def _parse_control(self, byte: int) -> dict:
        """解析控制域 C：DIR/PRM/分帧/SC/功能码"""

    def _parse_address(self, data: bytes, offset: int) -> tuple[dict, int]:
        """解析地址域 SA + CA，返回 (解析结果, 新偏移量)"""

    def _calc_hcs(self, data: bytes) -> int:
        """计算 HCS（X-25 CRC16）"""

    def _calc_fcs(self, data: bytes) -> int:
        """计算 FCS（X-25 CRC16）"""
```

**关键规则**：
- HCS 校验范围：从控制域开始到地址域结束的所有字节。
- FCS 校验范围：从控制域开始到链路用户数据结束的所有字节（即 HCS + 链路用户数据）。
- 校验算法使用 X-25 CRC-16（`crcmod` 的 `x25` 多项式）。
- 地址域 SA 的地址特征：bit0~bit3 表示地址字节数（0~15 对应 1~16 字节），bit4~bit5 逻辑地址，bit6~bit7 地址类型（0=单地址, 1=通配, 2=组地址, 3=广播）。
- 广播地址固定 1 字节 = `0xAA`。

### 4.2 dl_t698_45_axdr.py — A-XDR 编解码器

**职责**：实现 DL/T 790.6-2010 A-XDR 编码规则的编解码。

**Tag 编码规则**（A-XDR）：
- Tag 由 1 字节组成，高 3 位为 class（应用类=0b010），低 5 位为 tag number。
- 对于大于 30 的 tag number，使用多字节编码（本项目暂不涉及）。
- Length 使用 BER 长度编码：短形式（bit7=0）或长形式（bit7=1，后 7 位为长度字节数）。

**支持的数据类型**（完整列表）：

| 类型 | Tag | 编码说明 |
|------|-----|----------|
| NULL | 0 | 空值 |
| array | 1 | SEQUENCE OF Data，长度前缀 |
| structure | 2 | SEQUENCE OF Data，长度前缀 |
| bool | 3 | 1 字节，0/1 |
| bit-string | 4 | 长度前缀 + 字节 |
| double-long | 5 | 4 字节有符号整数，小端 |
| double-long-unsigned | 6 | 4 字节无符号整数，小端 |
| octet-string | 9 | 长度前缀 + 字节 |
| visible-string | 10 | 长度前缀 + ASCII |
| UTF8-string | 12 | 长度前缀 + UTF-8 |
| integer | 15 | 1 字节有符号 |
| long | 16 | 2 字节有符号，小端 |
| unsigned | 17 | 1 字节无符号 |
| long-unsigned | 18 | 2 字节无符号，小端 |
| long64 | 20 | 8 字节有符号，小端 |
| long64-unsigned | 21 | 8 字节无符号，小端 |
| enum | 22 | 1 字节枚举值 |
| float32 | 23 | 4 字节 IEEE 754，小端 |
| float64 | 24 | 8 字节 IEEE 754，小端 |
| date_time | 25 | 10 字节（年/月/日/星期/时/分/秒/毫秒高/毫秒低/偏移） |
| date | 26 | 5 字节（年/月/日/星期/偏移） |
| time | 27 | 4 字节（时/分/秒/偏移） |
| date_time_s | 28 | 7 字节（年/月/日/时/分/秒/偏移） |
| OI | 80 | 2 字节无符号（long-unsigned，语义特殊） |
| OAD | 81 | 4 字节（OI + 属性标识 + 元素索引） |
| ROAD | 82 | 变长（OAD + 关联 OAD 数组） |
| OMD | 83 | 4 字节（OI + 方法标识 + 操作模式） |
| TI | 84 | 3 字节（单位枚举 + 间隔值 long-unsigned） |
| TSA | 85 | 变长 octet-string（2~17 字节） |
| MAC | 86 | 变长 octet-string |
| RN | 87 | 变长 octet-string |
| Region | 88 | 变长（单位枚举 + 起始值 Data + 结束值 Data） |
| RSD | 89 | CHOICE（选择方法 0~11） |
| CSD | 90 | CHOICE（OAD / ROAD） |
| MS | 91 | CHOICE（无表计/全部/一组类型/一组地址...） |
| SID | 92 | 8 字节（标识 double-long-unsigned + 附加数据 octet-string） |
| SID_MAC | 93 | 变长（SID + MAC） |
| Scaler_Unit | 94 | 4 字节（换算 integer + 单位 enum） |
| RCS | 95 | array of CSD |

**核心方法**：

```python
class AXDRCoder:
    def decode(self, data: bytes, offset: int = 0, tag_hint: int = None) -> tuple[dict, int]:
        """从指定偏移量解码一个 A-XDR 数据项
        返回 (解码结果, 消耗字节数)
        解码结果格式：{"类型": str, "原始值": str, "解析值": Any, "说明": str}
        """

    def encode(self, value: Any, tag: int) -> bytes:
        """将 Python 值编码为 A-XDR 字节"""

    def decode_oad(self, data: bytes, offset: int) -> tuple[dict, int]:
        """专门解析 OAD：OI(2B) + 属性标识(1B) + 元素索引(1B) """

    def decode_omd(self, data: bytes, offset: int) -> tuple[dict, int]:
        """专门解析 OMD：OI(2B) + 方法标识(1B) + 操作模式(1B) """

    def decode_date_time(self, data: bytes, offset: int) -> tuple[dict, int]:
        """解析 date_time（10字节）或 date_time_s（7字节） """
```

**设计决策**：
- `structure` 和 `array` 递归调用 `decode()` 解析内部元素。
- `Data` 类型（APDU 中的通用数据占位符）需要通过上下文推断 tag，如果无法推断则尝试按 tag 字节自动识别。
- `date_time` 中的 "星期" 字段按规范 `0=星期日`，需正确转换显示。

### 4.3 dl_t698_45_apdu_parser.py — APDU 解析器

**职责**：根据 APDU 类型选择正确的解析逻辑，调用 A-XDR 解码器解析内容。

**APDU 类型映射**：

| APDU 首字节 | 类型 | 说明 |
|------------|------|------|
| 0x01 (1) | LINK-Request | 预连接请求 |
| 0x81 (129) | LINK-Response | 预连接响应 |
| 0x02 (2) | CONNECT-Request | 建立应用连接请求 |
| 0x82 (130) | CONNECT-Response | 建立应用连接响应 |
| 0x03 (3) | RELEASE-Request | 断开应用连接请求 |
| 0x83 (131) | RELEASE-Response | 断开应用连接响应 |
| 0x84 (132) | RELEASE-Notification | 断开应用连接通知 |
| 0x05 (5) | GET-Request | 读取请求 |
| 0x85 (133) | GET-Response | 读取响应 |
| 0x06 (6) | SET-Request | 设置请求 |
| 0x86 (134) | SET-Response | 设置响应 |
| 0x07 (7) | ACTION-Request | 操作请求 |
| 0x87 (135) | ACTION-Response | 操作响应 |
| 0x08 (8) | REPORT-Response | 上报应答 |
| 0x88 (136) | REPORT-Notification | 上报通知 |
| 0x09 (9) | PROXY-Request | 代理请求 |
| 0x89 (137) | PROXY-Response | 代理响应 |
| 0x45 (69) | COMPACT-GET-Request | 紧凑读取请求 |
| 0xC5 (197) | COMPACT-GET-Response | 紧凑读取响应 |
| 0x46 (70) | COMPACT-SET-Request | 紧凑设置请求 |
| 0xC6 (198) | COMPACT-SET-Response | 紧凑设置响应 |
| 0x49 (73) | COMPACT-PROXY-Request | 紧凑代理请求 |
| 0xC9 (201) | COMPACT-PROXY-Response | 紧凑代理响应 |
| 0x10 (16) | SECURITY-Request | 安全请求 |
| 0x90 (144) | SECURITY-Response | 安全响应 |
| 0x6E (110) | ERROR-Response (Client) | 异常响应（Client-APDU 中） |
| 0xEE (238) | ERROR-Response (Server) | 异常响应（Server-APDU 中） |

**核心方法**：

```python
class DLT69845APDUParser:
    def __init__(self, axdr_coder: AXDRCoder = None, oi_lookup: OILookup = None):
        pass

    def parse(self, apdu_bytes: bytes) -> dict:
        """解析 APDU 字节，返回嵌套字典"""

    def _parse_link_request(self, data: bytes) -> dict:
        """解析 LINK-Request：PIID + 请求类型 + 心跳周期 + 时间标签"""

    def _parse_link_response(self, data: bytes) -> dict:
        """解析 LINK-Response：PIID-ACD + 结果 + 心跳周期 + 时间标签"""

    def _parse_connect_request(self, data: bytes) -> dict:
        """解析 CONNECT-Request：PIID + 认证 + 时间标签"""

    def _parse_get_request(self, data: bytes) -> dict:
        """解析 GET-Request（Normal / Next / MD5 / Signature）"""

    def _parse_get_response(self, data: bytes) -> dict:
        """解析 GET-Response（Normal / MD5 / Signature）"""

    def _parse_set_request(self, data: bytes) -> dict:
        """解析 SET-Request（Normal / MD5 / Signature）"""

    def _parse_action_request(self, data: bytes) -> dict:
        """解析 ACTION-Request（Normal / MD5 / Signature）"""

    def _parse_report_notification(self, data: bytes) -> dict:
        """解析 REPORT-Notification（Normal / Simplify / List）"""

    def _parse_security(self, data: bytes, is_request: bool) -> dict:
        """解析 SECURITY-Request/Response：安全类型 + 明文/密文/MAC"""

    def _parse_error_response(self, data: bytes) -> dict:
        """解析 ERROR-Response：PIID-ACD + DAR + 时间标签"""
```

**GET-Request 子类型**（通过 A-XDR choice 识别）：
- `[1] GetRequestNormal`：OAD + Data（可选）
- `[2] GetRequestNormalList`：SEQUENCE OF OAD
- `[3] GetRequestNext`：long-unsigned（块序号）
- `[4] GetRequestMD5`：OAD + RSD + CSD
- `[5] GetRequestSignature`：OAD

**GET-Response 子类型**：
- `[1] GetResponseNormal`：OAD + GetResult（Data / DAR）
- `[2] GetResponseNormalList`：SEQUENCE OF (OAD + GetResult)
- `[3] GetResponseNext`：块序号 + Data
- `[4] GetResponseMD5`：OAD + MD5
- `[5] GetResponseSignature`：OAD + 签名数据

**REPORT-Notification 子类型**：
- `[1] ReportNotificationNormal`：RSD + CSD + 数据
- `[2] ReportNotificationSimplify`：简化格式
- `[3] ReportNotificationList`：列表格式

### 4.4 dl_t698_45_oi_lookup.py — OI 查询模块

**职责**：提供 OI 到对象语义信息的查询。

**数据来源**：
- 698.45 规范附录 A 中定义的标准 OI 列表（约数百个）。
- 规范 8.2 节中定义的接口类（class_id）列表。
- 每个接口类有固定属性（编号 0~N）和方法（编号 1~N）。

**实现策略**：
- 将标准 OI 和 class_id 映射表硬编码在 Python 字典中（参考 `obis_lookup.py` 模式）。
- 不依赖外部 JSON 文件（除非用户需要自定义扩展）。
- 提供 `get_class_name(class_id)`、`get_attribute_name(class_id, attr_id)`、`get_method_name(class_id, method_id)`。
- OAD 解析时自动关联 OI 对应的 class_id，展示 `对象名称` 和 `属性名称`。

**核心方法**：

```python
class OILookup:
    def get_oi_info(self, oi: int) -> dict:
        """返回 {class_id, class_name, attributes, methods}"""

    def get_oad_description(self, oad_bytes: bytes) -> str:
        """根据 OAD 字节返回语义描述字符串，如'电能表通信地址 (class_id=1, attr=2)'"""

    def get_omd_description(self, omd_bytes: bytes) -> str:
        """根据 OMD 字节返回语义描述字符串"""
```

### 4.5 dl_t698_45_frame_gen.py + dl_t698_45_frame_schema.py — 帧生成

**职责**：根据 GUI 表单参数生成完整的 698.45 帧。

**帧生成流程**：
1. 用户选择服务类型（如 GET-Request Normal）。
2. 填写 SA、CA、PIID、OAD 列表等参数。
3. 生成 APDU 字节（调用 A-XDR 编码器）。
4. 计算长度域（APDU 长度 + 地址域长度 + 控制域长度）。
5. 组装帧头（68 + L + C + SA + CA）。
6. 计算 HCS。
7. 追加 APDU 和 FCS。
8. 追加结束符 16。

**Schema 设计**（`dl_t698_45_frame_schema.py`）：
- 参考 `frame_generator_schema.py` 的 `FrameField` 模式。
- 定义各服务类型所需的表单字段。

```python
GET_REQUEST_NORMAL_FIELDS = [
    FrameField("服务器地址SA", "sa", "hex", required=True),
    FrameField("客户机地址CA", "ca", "hex", default="00"),
    FrameField("PIID", "piid", "hex", default="00"),
    FrameField("OAD", "oad", "hex", required=True, help="4字节，如 20004001"),
]
```

### 4.6 validator/dl_t698_45_validator.py — 协议验证器

**职责**：继承 `BaseValidator`，对 698.45 帧进行结构性校验。

**校验项**：
1. 起始字符 = 0x68
2. 长度域 L 值与实际帧数据长度一致
3. HCS 正确（覆盖范围：控制域到地址域）
4. FCS 正确（覆盖范围：控制域到链路用户数据）
5. 结束字符 = 0x16
6. 地址域长度不超出帧边界

### 4.7 GUI 集成方案

**main_gui.py 修改点**：

1. **协议索引扩展**：
   - 现有：`0=南网, 1=PLC RF, 2=HDLC, 3=Wrapper, 4=APDU, 5=DLT645, 6=国网`
   - 新增：`7=698.45`
   - 更新 `protocol_combo` 选项和 `current_protocol` 相关所有分支。

2. **`_get_current_parser()`**：
   - 索引 7 返回 `DLT69845Parser` 实例（包装为兼容 `parse_to_table` 接口）。

3. **`_extract_frames_for_protocol()`**：
   - 索引 7：使用 `68...16` 提取逻辑（与南网/国网相同，即 `_extract_68_frames`）。

4. **`_on_protocol_changed()`**：
   - 索引 7：显示帧生成页、预设页、档案页、拓扑页（视 698.45 需求而定，至少帧生成页需要）。
   - 更新输入框 placeholder 文本。
   - 更新查找页标题为 "OAD 查询"。

5. **`_update_protocol_lookup_tab()`**：
   - 索引 7：创建 OAD 查询内容（输入 OI 查询对象信息）。

6. **`_generate_summary()`**：
   - 索引 7：提取服务类型名称、OAD 信息作为摘要。

7. **`_get_current_validator()`**：
   - 索引 7 返回 `DLT69845Validator()`。

8. **校验器字典**：
   - 在 `validators = {...}` 中增加 `7: DLT69845Validator()`。

---

## 5. A-XDR 编码详解

### 5.1 Tag 编码
A-XDR 中，应用类 tag 的高 3 位固定为 `010`，低 5 位为 tag number。

示例：
- `structure` 的 tag number = 2，class = 0b010，tag byte = `0x22`
- `long-unsigned` 的 tag number = 18，tag byte = `0x12`
- `OAD` 的 tag number = 17（在 698.45 扩展中），注意与标准 A-XDR 的区别。

**重要**：698.45 规范中扩展了部分 tag（如 OI=80, OAD=81 等），这些不在标准 DL/T 790.6-2010 中，需要按规范单独处理。

### 5.2 Length 编码
BER 长度编码：
- 短形式：`0x00` ~ `0x7F`，直接表示长度值。
- 长形式：`0x81` 表示后面 1 字节为长度，`0x82` 表示后面 2 字节为长度。

### 5.3 Data 类型解码策略
APDU 中的 `Data` 是一个 CHOICE，通过读取第一个字节（tag）来决定类型，然后调用对应解码器。

对于嵌套 `structure` / `array`，递归解码直到遇到原子类型。

---

## 6. 测试策略

### 6.1 单元测试（test_dl_t698_45.py）
硬编码典型 698.45 帧进行解析验证：

1. **LINK-Request 登录帧**：
   `68 1E 00 81 05 07 09 19 05 16 20 00 [HCS] 01 00 00 00 [APDU] [FCS] 16`
   （参考规范附录 H.1.1）

2. **LINK-Response 登录响应帧**：
   验证 PIID-ACD、结果码、心跳周期解析。

3. **GET-Request Normal 帧**：
   `68 ... 43 05 ... [HCS] 05 00 01 00 [OAD] [FCS] 16`
   验证 OAD 解析。

4. **GET-Response Normal 帧**：
   验证 Data 返回值（如 date_time、Scaler_Unit）解析。

5. **SET-Request Normal 帧**：
   验证设置请求 + Data 参数解析。

6. **ACTION-Request Normal 帧**：
   验证 OMD + 参数解析。

7. **SECURITY-Request 帧**：
   验证安全类型、明文长度、密文长度解析。

8. **帧生成测试**：
   生成 GET-Request Normal 帧，手动验证 HCS/FCS。

### 6.2 集成测试
- 在 GUI 中切换协议到 698.45，输入测试帧，验证解析结果表格显示正确。
- 验证批量解析功能。
- 验证校验器输出。

---

## 7. 实现顺序建议

按依赖关系，建议分阶段实现：

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| 1 | 链路层解析器 + HCS/FCS 计算 | `dl_t698_45_parser.py` + `test_dl_t698_45.py`（LINK帧） |
| 2 | A-XDR 编解码器 | `dl_t698_45_axdr.py` + 基础类型测试 |
| 3 | APDU 解析器骨架 | `dl_t698_45_apdu_parser.py`（LINK + GET-Request/Response Normal） |
| 4 | OI 查询模块 | `dl_t698_45_oi_lookup.py` |
| 5 | 完整 APDU 类型支持 | 补充 SET/ACTION/REPORT/SECURITY/ERROR 等 |
| 6 | 帧生成 | `dl_t698_45_frame_schema.py` + `dl_t698_45_frame_gen.py` |
| 7 | GUI 集成 | `main_gui.py` 修改 + `validator/dl_t698_45_validator.py` |
| 8 | 全面测试 | 完整 `test_dl_t698_45.py` + GUI 集成测试 |

---

## 8. 风险与限制

| 风险 | 缓解措施 |
|------|----------|
| A-XDR 数据类型繁多，初期可能遗漏边缘类型 | 优先实现常用类型（integer/long-unsigned/octet-string/date_time/structure/array/enum/OAD/OMD），后续按需补充 |
| OI 映射表数据量大（数百个对象） | 采用增量构建：先实现核心对象（如电能表基本参数、通信地址等），后续逐步补全 |
| 698.45 协议规范文档为 OCR 转换，部分格式可能不准确 | 遇到歧义时以规范附录 H 的编码举例为准，辅以逻辑推断 |
| 分帧传输逻辑复杂 | 第一阶段仅解析分帧标志和分帧格式域，完整的分帧重组逻辑后续迭代 |
| 安全传输涉及 ESAM 加密，硬件依赖 | 仅解析结构，不进行实际加解密 |
| COMPACT 服务格式特殊 | 放到常规服务之后实现，作为扩展功能 |

---

## 9. 附录：与其他解析器的对比

| 特性 | 南网 (CSG) | 国网 (GDW) | 698.45 |
|------|-----------|-----------|--------|
| 帧起始符 | 0x68 | 0x68 | 0x68 |
| 帧结束符 | 0x16 | 0x16 | 0x16 |
| 长度域 | 2 字节，小端 | 2 字节，小端 | 2 字节，小端（bit0~13） |
| 控制域 | 1 字节（DIR/PRM/FCB/FCV/AFN） | 1 字节（DIR/PRM/FCB/FCV/功能码） | 1 字节（DIR/PRM/分帧/SC/功能码） |
| 地址域 | 5 字节固定 | 5/7 字节 | 变长（SA + CA） |
| 校验 | 累加和 | 累加和 | X-25 CRC-16（HCS + FCS） |
| 应用层 | DI + 数据块 | AFN + Fn + 数据块 | APDU（A-XDR 编码） |
| 数据编码 | BCD / BIN | BCD / BIN | A-XDR（ASN.1 子集） |
| 对象模型 | 无 | 无 | 面向对象（OI/OAD/OMD） |

---

*规格版本：v1.0*
*日期：2026-05-12*
*状态：待实现*
