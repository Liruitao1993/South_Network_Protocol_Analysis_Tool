# 技术设计：协议12 组帧接线 + 查询页覆盖 + 解析器对齐

对应 `prd.md`（R1~R7）。本文只写技术设计与契约。

---

## 0. 研究结论（决定实现方式的三条铁证）

### 铁证 1：A-XDR 层必须重写——上一轮实现把 A-XDR 编成了大端数组

同族标准 DL/T 698.45 的文档在仓库内：`面向对象的用电信息数据交换协议(20210910).md`，
其**附录 H.1.1 登录**给出真实编码示例（行 5572 起）：

```
05 07 09 19 05 16 20 ___ SA        （链路层，7 字节）
01 ___ [1] LINK-Request
00 ___ PID-ACD
00 —— 请求类型：建立连接（0）
00 B4 —— 心跳周期：180s                       ← 大端，裸字段无标签
07 E0 05 13 04 08 05 00 00 A4 —— 请求时间 date_time: 2016-05-19 08:05:00:0164
```

可推出三条规则：
1. **APDU 的 tag 字节 = 类型编号本身**（`[1]`→`01H`、`[129]`→`81H`），不是 `0x80|n`。
2. **定长类型在 SEQUENCE 内不带标签、不带长度域**：`year`(2B)=`07 E0`=2016（**大端**）、
   `月/日/星期/时/分/秒` 各 1 字节依次裸排、`milliseconds`(2B)=`00 A4`=164（大端）。
   字段顺序与协议12 表6 **完全一致**（year, month, day_of_month, day_of_week, hour, minute, second, ms）。
   校验：2016-05-19 是周四 → `day_of_week=04` ✓；`day_of_month=13H=19` ✓。
3. 由 2 反推：`毫秒=00A4` 而非 `A400`，`心跳周期=00B4` 而非 `B400` ⇒ **A-XDR 多字节一律大端**。

而 `modular_iface_parser.py` 现有实现（`_take_axdr_uint` 等）把这层当成了**小端裸字节数组**，
`modular_iface_frame_gen.py` 也照此组帧，且把 `LinkRequest` 的可见字符串当 1 字节等长固定域。
⇒ **该层（APDU/DT/A-XDR）不可修补，必须重写**；链路层（`calc_fcs` / `data_total_len` / 逐字段控制域）可保留。

### 铁证 2：文档没有任何示例帧

`grep -n "示例\|举例\|例如："` 在 `协议文档/12.模组化功能协议/模组化终端功能模块接口协议.md` 返回 **空**。
⇒ 协议12 的字节级布局**无法从文档自证**，必须靠 §6.1 明确引用的两个外部标准推导：

> 「APDU 的标记规则遵循 ASN.1 的抽象语法，详见 GB/T 16262.1—2006。APDU 的编码规则遵循
> A-XDR，详见 DL/T 790.6—2010。」—— §6.1

仓库内没有 DL/T 790.6-2010。因此设计上必须做到：**编码假设集中成单表 + 双开关**，
一旦拿到真实帧即可一处切换；并提供 `verify_frame()` 以便把真实帧锁成 golden。

### 铁证 3：链路层与文档一致，可保留

- §5.2.1 帧 = `68H | L(2B) | C(2B) | 数据域(L) | FCS(2B) | 16H` ⇒ **整帧 = L + 8**
- §5.2.2 图5：`L` 的 bit0~bit11 = **数据域信息字节数**，bit12~15 保留（**L 不是整帧长**）
- §5.1 图 →「低字节在前，高字节在后」⇒ L / C / FCS 均为**小端**
- §5.2.3.1 图6：控制域低字节 = `DIR(bit7) | PRM(bit6) | 控制码(bit5~0)`；高字节 = `FID`
- 表2：控制码 `00H` 确认 / `01H` 否认 / `02H` 信息
- 表3：否认帧数据域 = 错误信息码 BIN **2 字节**
- §5.2.5：FCS **2 字节，覆盖除起始符/结束符/FCS 自身外的所有字节** ⇒ 覆盖 `L + C + 数据域`
- 附录 A.1：`fcstab[256]` = 标准 PPP 表（`0x8408` 反射多项式）⇒ 等价 `CRC-16/X-25`（`crcmod` 的 `x-25`）

---

## 1. 模块边界

| 文件 | 动作 | 内容 |
| --- | --- | --- |
| `modular_iface_axdr.py` | **新增** | A-XDR 编解码单源：类型表、`encode_type()` / `decode_type()` / `decode_sequence()`；无 Qt、无其它项目模块依赖 |
| `modular_iface_parser.py` | **重写 APDU/DT 层** | 保留链路层与摘要骨架；APDU 8 类与 DT 解码改走 `modular_iface_axdr` |
| `modular_iface_frame_gen.py` | **重写 APDU 层** | 组帧改走 `modular_iface_axdr`；模板表保留并修正 |
| `modular_iface_data.py` | **新增** | 查询页与解析器共用的静态表：DT 名称（附录 C + 附录 G/J/K/L）、物理单位（附录 M）、DAR（表11）、APDU/控制码名、设备子接口（附录 D~L）、厂商标识（附录 B）、`REPORT_MODE_*` 等 |
| `validator/modular_iface_validator.py` | 小改 | FCS 判定改走 `modular_iface_axdr`/共用算法；补「L 与实际不一致」「保留位非 0」提示 |
| `protocol_registry.py` | 小改 | `frame_gen_mode="modular"`、`preset_mode="modular"` |
| `frame_gen_widget.py` | 小改 | 新增 modular 模式（见 §6 逐处分派点） |
| `preset_buttons.py` | 小改 | 新增 modular 模式 + 独立数据文件 |
| `main_gui.py` | 小改 | 查询页分组重做；`_get_summary_from_table_data` 加 `proto == 12` 分支；CHANGELOG；`APP_VERSION`/`BUILD_DATE` |
| `南网协议解析工具.spec` | 小改 | `hiddenimports` 补 3 个模块 |
| `test/test_modular_iface.py` | 扩展 | 见 R7 |

**复用（不新增第二份实现）**：`protocol_registry`、`parser_registry`、`gui_utils.set_btn/set_btn_icon`、
`gui_utils.ZoomableTableWidget` + `_setup_table_copy_menu`、`app_icons.load_icon`、
`apply_chinese_context_menus`、`thread_registry.track`、`app_paths.data_path`、`app_config.AppConfig`。

**删除**：`modular_iface_parser.py` 内的 `DAR_NAMES`（与表11 矛盾的 21 项表）、
`_take_axdr_uint` / `_take_axdr_string`（错误的小端探测式解析）。
调试残留 `test/_tmp_*.py|txt`、`test/out*.txt` 一并清理。

---

## 2. 契约 A：A-XDR 层（`modular_iface_axdr.py`）

### 2.1 类型表（唯一来源，来自协议12 表4）

```python
@dataclass(frozen=True)
class AxdrType:
    name: str
    tag: int              # 表4「标记」列；CHOICE 内作为 tag 字节
    fixed: Optional[int]  # 固定字节数；None = 变长（带长度域）
    multibyte: bool = False   # True 时多字节按大端解释
    signed: bool = False

AXDR_TYPES = {
    # name: AxdrType(name, tag, fixed, multibyte, signed)
    "NULL":                 AxdrType("NULL", 0x00, 0),
    "array":                AxdrType("array", 0x01, None),
    "structure":            AxdrType("structure", 0x02, None),
    "bool":                 AxdrType("bool", 0x03, 1),
    "bit-string":           AxdrType("bit-string", 0x04, None),
    "double-long":          AxdrType("double-long", 0x05, 4, True, True),
    "double-long-unsigned": AxdrType("double-long-unsigned", 0x06, 4, True),
    "octet-string":         AxdrType("octet-string", 0x09, None),
    "visible-string":       AxdrType("visible-string", 0x0A, None),
    "UTF8-string":          AxdrType("UTF8-string", 0x0C, None),
    "integer":              AxdrType("integer", 0x0F, 1, False, True),
    "long":                 AxdrType("long", 0x10, 2, True, True),
    "unsigned":             AxdrType("unsigned", 0x11, 1),
    "long-unsigned":        AxdrType("long-unsigned", 0x12, 2, True),
    "long64":               AxdrType("long64", 0x14, 8, True, True),
    "long64-unsigned":      AxdrType("long64-unsigned", 0x15, 8, True),
    "enum":                 AxdrType("enum", 0x16, 1),
    "float32":              AxdrType("float32", 0x17, 4, True),
    "float64":              AxdrType("float64", 0x18, 8, True),
    "date_time":            AxdrType("date_time", 0x19, 10),   # 表4: octet-string(SIZE(10))
    "date":                 AxdrType("date", 0x1A, 5),         # SIZE(5)
    "time":                 AxdrType("time", 0x1B, 3),         # SIZE(3)
    "date_time_s":          AxdrType("date_time_s", 0x1C, 7),  # SIZE(7)
    "DT":                   AxdrType("DT", 0x50, 2, True),     # DT ::= long-unsigned（表10）
    "Scaler_Unit":          AxdrType("Scaler_Unit", 0x51, 2),  # SEQUENCE{integer, enum}（表12）
}
```

### 2.2 编码规则（A-XDR / DL/T 790.6-2010，单点可切换）

| 场景 | 编码 |
| --- | --- |
| CHOICE 分支 | `tag(1B)` + 分支内容 |
| SEQUENCE | 成员依次编码，**外层无 tag**（命名类型出现在固定位置：APDU 本身就是 CHOICE 的分支） |
| 定长类型（`fixed is not None`）**在 SEQUENCE 内** | 裸字节，**无 tag、无长度域**（铁证 1 第 2 条） |
| 定长类型**作为 CHOICE 分支** | `tag(1B)` + 裸字节，**无长度域** |
| 变长类型（`octet-string`/`visible-string`/`UTF8-string`/`bit-string`/`array`/`structure`） | `tag(1B)` + `长度(1B)` + 内容（顶层出现时）；在 SEQUENCE 内为 `长度(1B)` + 内容 |
| 多字节数值 | **大端** |
| `bit-string` 内容 | 首字节 = 有效位数，其后为位组（见 §2.4） |

**三个必须显式化的假设开关**（模块常量，勿散落）：

```python
# ① SEQUENCE 内的定长成员是否发 tag。
#    默认 False —— 铁证 1 直接实证：698 的 LINK-Request 里 `请求时间 date_time`
#    （在表4 中带标记 25）在 SEQUENCE 内是**裸 10 字节**，没有 0x19。
#    ⇒ 同样地，GetRequestNormal 的 `信息类标识 DT` 在 SEQUENCE 内也是**裸 2 字节大端**，
#      只有出现在 Data（CHOICE）里时才带 0x50。
AXDR_TAG_IN_SEQUENCE = False

# ② 定长类型作为 CHOICE 分支时是否附带长度域。
#    默认 False —— 铁证 1：定长不带长度（`00 B4`=心跳周期，无长度字节）。
AXDR_LEN_FOR_FIXED_IN_CHOICE = False

# ③ 变长类型的长度域字节数。默认 1。
AXDR_VAR_LENGTH_BYTES = 1
```

> `verify_frame()`（§2.5）是这三个开关的裁决口：拿到真实帧后若 `axdr_tail != 0` 或解析失败，
> 逐一切换 ①②③ 重试（组合只有 8 种，写个脚本枚举即可），能过则改默认值并在 `AGENTS.md`
> 记录**实测依据**（帧来源 + `axdr_tail` 变化）。**不要**在解析函数里各写一份猜测。
>
> 对应到具体字段，当前假设下的实际字节布局（实现时按此写断言）：
> | 字段 | 假设下的编码 |
> | --- | --- |
> | `GetRequestNormal.信息类标识` | 裸 2 字节大端（如 DT=0x0000 → `00 00`） |
> | `SetRequest.信息类标识` | 裸 2 字节大端 |
> | `LinkRequest.协议版本号` | 裸 2 字节大端 |
> | `LinkRequest.终端设备型号` | `长度(1B)` + ASCII（变长，在 SEQUENCE 内**不发 tag**） |
> | `LinkResponse.虚拟通道工作模式` | `长度(1B)` + N × (`接口类型 enum 1B` + `功能配置 unsigned 1B`) |
> | `Data` 里的 `date_time` | `19` + 裸 10 字节 |
> | `Data` 里的 `DT` | `50` + 裸 2 字节大端 |
> | `Get-Result` | `00`+DAR(1B) 或 `01`+Data |
> | `SetResponse.设置执行结果` | 裸 1 字节 |

### 2.3 API

```python
def tag_of(type_name: str) -> int                     # 表4 标记
def type_of_tag(tag: int) -> Optional[AxdrType]
def encode_value(value, type_name: str, *, with_tag: bool) -> bytes
def decode_value(data: bytes, off: int, type_name: str, *, with_tag: bool) -> tuple[Any, int]
    """返回 (解析值, 新偏移)。越界抛 AxdrError（携带已消费偏移，便于容错显示）。"""
def decode_choice(data: bytes, off: int, table: dict[int, str]) -> tuple[str, Any, int]
    """tag → 类型名，再 decode_value(..., with_tag=False)。"""
def encode_sequence(fields: list[tuple[str, Any]], *, with_tag: bool = False) -> bytes
def decode_sequence(data: bytes, off: int, layout: list[tuple[str, str]]) -> tuple[dict, int]
```

`AxdrError(str)` 是唯一异常类型，消息面向用户（含字段名与偏移），便于按 §8 陷阱 23 在表里显式报错而不空白。

### 2.4 专用结构

- `date_time` / `date_time_s` / `date` / `time`：按表6~表9 的字段顺序解码，
  `FFFFH`（2B 字段）/`FFH`（1B 字段）= 无效 → 输出「无效」；`day_of_week` 0=周日、1~6=周一~周六。
- `Scaler_Unit`（表12）：`换算 integer`（**有符号 1B**，基数 10 的指数）+ `单位 enum`（1B，查附录 M）；
  显示形如 `单位: V（伏特）, 换算: 10^-1`；`换算=0` 时只显示单位。数值换算由调用方决定
  （本次**不**对信息类数值做缩放，只在行内给出「换算倍数/单位」提示，避免在未定义信息类的信息上臆造换算）。
- `bit-string`：首字节位宽 + 位组（按大端位序展开）。
- `array` / `structure`：长度域 + 逐个 `Data`（CHOICE）递归解码。

### 2.5 `verify_frame(bytes) -> dict`

给实现者/现场用的自检入口（同时被 `test_*` 与 GUI「校验」按钮使用）：

```python
{"ok": bool, "reason": str,
 "frame_len": int, "declared_l": int, "l_matches": bool,
 "fcs_ok": bool, "fcs_field": bytes, "fcs_calc": bytes,
 "control": {...}, "apdu_tag": int|None, "apdu_name": str|None,
 "axdr_consumed": int, "axdr_tail": int}   # axdr_tail != 0 ⇒ 编码假设可能不匹配
```

`axdr_tail` 是本设计的关键调试量：**APDU 解完后若仍有剩余字节（或不足），说明编码假设与真实帧不符**。
拿到真实帧时只需看这一个数就能判定假设对不对。GUI 把它显示在「帧校验」区域。

---

## 3. 契约 B：链路层（保留 + 收口，`modular_iface_parser.py`）

```python
FRAME_START = 0x68; FRAME_END = 0x16
HEADER_LEN = 9      # 68 + L(2) + C(2) + 数据域(L) + FCS(2) + 16  的固定部分 = 1+2+2+2+1
def calc_fcs(payload: bytes) -> int          # 覆盖 L + C + 数据域，PPP 表（保留现有实现）
def data_total_len(data_bytes: bytes) -> int # 整帧长 = L + 8（保留）
def is_frame(data: bytes) -> bool            # 保留
```

控制域（**逐字段**，不再只给一个值）：

| 行 | 取值 |
| --- | --- |
| 原始值 | 2 字节 hex（小端） |
| 码/值 | `DIR | PRM | 控制码` 的十进制/十六进制组合 |
| 说明 | 表1 的 4 种组合意义 + 表2 控制码名 + `帧序号 FID=n` |

表1 组合意义表（**单源常量**）：
`(0,0)` 终端对功能模块上报的响应 / `(0,1)` 终端发起的请求 / `(1,0)` 功能模块发起的请求或上报 /
`(1,1)` 功能模块对终端请求或通知的响应。

`parse()` 收尾**必须**如实写 meta（修掉 `{...} if False else None` 死代码）：
```python
meta = {"valid": bool(...), "fcs_ok": bool(...), "structure_ok": bool(...)}   # 不再是 None
```

---

## 4. 契约 C：DT 与静态表（`modular_iface_data.py`）

### 4.1 DT 命名（表22 + 附录 C + 附录 G/J/K/L）

```python
DTA1_NAMES = {0x0: "通用信息类", 0x1: "远程通信模块", 0x2: "本地通信模块",
              0x3: "RS-485通信模块", 0x4: "遥信脉冲模块", 0x5: "CAN通信模块",
              0x6: "M-Bus通信模块", 0x7: "控制模块", 0x8: "模拟量采集模块",
              0x9: "回路状态巡检模块"}      # 附录 D~L 模块名；0xA~0x1F 未定义
DTA2_NAMES = {0x0: "只读", 0x1: "读-写", 0x2: "只写"}   # §7.1
DT_NAMES = {0x0000: "模块信息", 0x0001: "链路协商信息", ...}   # 附录 C + G/J/K/L，逐条对拍
```

`decode_dt(raw2: bytes) -> dict` 返回 `{raw, dt, dta1, dta2, dtb, dta1_name, dta2_name, name}`
（**大端**取 DT，不再用 `int.from_bytes(..., "little")`——现行实现即此错）。

### 4.2 其余表

| 常量 | 来源 |
| --- | --- |
| `DAR_NAMES` | **表11：只 0/1/2/255 四个值**（推翻现有 21 项表） |
| `APDU_NAMES` | 表13：`{1:"链路协商请求",2:"数据读取请求",3:"设置请求",4:"上报通知",129:"链路协商响应",130:"数据读取响应",131:"设置响应",132:"上报通知响应"}` |
| `CTRL_CODE_NAMES` | 表2：`{0x00:"确认帧",0x01:"否认帧",0x02:"信息帧"}` |
| `DIR_PRM_MEANINGS` | 表1 |
| `PHYSICAL_UNITS` | **附录 M 表31 逐条**（代码→符号→名称；1~75 + 254 + 255） |
| `DEVICE_SUBIFACES` | 附录 D.1/E.1/F.1/G.1/J.1/K.1/L.1（虚拟通道号/接口形式/功能定义） |
| `VENDOR_ID` | 附录 B：`VID=0x3C93`、`PID=0xFFFF` |
| `LINK_RESPONSE_FUNC_CONFIG` | 表18 注：0 管理通道 / 1 远程通信 / 2 PLC/RF / 3 RS-485 / 4 遥信脉冲 / 5 CAN / 6 M-Bus / 7 控制 / 8 模拟量采集 / 9 RS232 |
| `IFACE_TYPE_NAMES` | 表18：`{1:"CDC-ACM",2:"CDC-ECM",3:"HID"}` |

**每张表都必须在测试里与文档逐条对拍**（`prd.md` AC2.2~AC2.5）；表格内容由实现者从文档现场抄录，
不允许从其它协议的记忆里搬（例如 DAR 曾是这类错误）。

---

## 5. 契约 D：8 类 APDU 的编解码

按表13~表21 的 ASN.1 逐字实现。字段布局（**这一节就是实现清单**）：

| APDU | tag | 布局 |
| --- | --- | --- |
| LinkRequest | 0x01 | `协议版本号 long-unsigned` + `终端设备型号 visible-string` + `终端设备ID visible-string` + `最大发送缓冲区长度 long-unsigned` + `最大接收缓冲区长度 long-unsigned` + `并发传输窗口数 unsigned` |
| GetRequest | 0x02 | `信息类标识 DT`（`GetRequestNormal`） |
| SetRequest | 0x03 | `信息类标识 DT` + `数据 Data` |
| ReportNotification | 0x04 | `A-ResultNormal`（即 `DT` + `Get-Result`） |
| LinkResponse | 0x81 | LinkRequest 六字段（末字段换成「功能模块设备型号/ID」）+ `虚拟通道工作模式 SEQUENCE OF { 接口类型 enum(1=CDC-ACM/2=CDC-ECM/3=HID), 功能配置 unsigned }` |
| GetResponse | 0x82 | `A-ResultNormal`：`DT` + `Get-Result CHOICE { [0] DAR(1B), [1] Data }` |
| SetResponse | 0x83 | `信息类标识 DT` + `设置执行结果 DAR(1B)` |
| ReportResponse | 0x84 | `对应上报的信息类标识 DT` |

`Get-Result` 的两个分支：`00H`(DAR) → 查表11 出中文；`01H` → 递归 `decode_choice(Data)`。

**Data（表5）25 个分支**按 §2.1 的 tag 表解码；`DT`(0x50) 与 `Scaler_Unit`(0x51) 用 §4.1 / §2.4 的专用解码。

**表格行输出**（`parse_to_table` 的列约定，沿用项目 §4.2）：

| 层级 | 行名示例 |
| --- | --- |
| 顶层 | `帧起始符` / `长度域` / `控制域` / `数据域` / `帧校验(FCS)` / `帧结束符` |
| 控制域 | `控制域`（含 DIR/PRM/控制码/FID 的子行） |
| APDU | `APDU 类型` / `链路协商请求` / `信息类标识(DT)` / `读取结果` / `数据` |
| 值行 | `原始值` / `解析值` / `说明` / `偏移` / `长度` |

`原始值`/`偏移`/`长度` 三列是 GUI 字节高亮与 `DLT645GuiParser` 式偏移映射的依据，必须逐行正确。

---

## 6. 契约 E：组帧（`modular_iface_frame_gen.py`）

```python
class ModularIfaceFrameGenerator:
    def build_control(self, control_code: int, *, dir_bit: int = 0, prm: int = 1, fid: int = 0) -> bytes
    def build_frame(self, control: bytes, data: bytes) -> bytes      # 68 + L + C + data + FCS + 16
    def build_ack(self, *, dir_bit=0, prm=0, fid=0) -> bytes          # 控制码 00H，数据域空
    def build_nak(self, error_code: int, *, ...) -> bytes             # 控制码 01H，数据域 = 2B
    def build_info(self, apdu: bytes, *, ...) -> bytes                # 控制码 02H
    # APDU 构造（走 modular_iface_axdr）
    def build_link_request(self, ...) -> bytes
    def build_link_response(self, ...) -> bytes
    def build_get_request(self, dt: int) -> bytes
    def build_get_response_data(self, dt: int, value, type_name: str) -> bytes
    def build_get_response_dar(self, dt: int, dar: int) -> bytes
    def build_set_request(self, dt: int, value, type_name: str) -> bytes
    def build_set_response(self, dt: int, dar: int) -> bytes
    def build_report_notification(self, dt: int, value, type_name: str) -> bytes
    def build_report_response(self, dt: int) -> bytes
```

`FRAME_TEMPLATES`：名字 → 默认参数 + 说明（至少 8 条：ACK / NAK / 读模块信息 / 读链路协商信息 /
读时钟 / 链路协商请求 / 设置请求示例 / 上报通知示例），每条模板都必须能被 `ModularIfaceParser` 回读成功
（`axdr_tail == 0` 且 `fcs_ok`）。

**组帧→解析闭环是硬门槛**：`parse(build_X(...))` 的每一个字段都要与原参数一致。

---

## 7. 契约 F：GUI 组帧页接线（`frame_gen_widget.py`）

这是 `prd.md` 的 R1（用户显式要求的「组帧能力」）。现有实现白名单硬编码 4 模式，
新增第 5 个模式必须触及以下**全部**分派点（`/trellis:before-dev` 已按实际内容逐处确认）：

| # | 位置 | 改动 |
| --- | --- | --- |
| 1 | `__init__`（`self.protocol_mode = "south"`，注释「south/gdw/dlt698」） | 注释加 `modular`；新增对应 generator 实例 |
| 2 | `set_protocol_mode()` 白名单 `("south","gdw","dlt698","dlt645")` | 加入 `"modular"` |
| 3 | 模式对应的生成器/解析器选择 | modular → `ModularIfaceFrameGenerator` / `ModularIfaceParser` |
| 4 | 命令/模板下拉的数据源 | modular → `FRAME_TEMPLATES` |
| 5 | 字段模式组（预定义/自定义/A-XDR 三选一）的可见性 | 只有 `south/gdw/dlt698` 用字段模板；`dlt645` 与 `modular` 用各自控件 ⇒ 按现有 `dlt645` 分支同样处理 |
| 6 | `_on_mode_changed()` 的三处互斥逻辑 | 加 modular 分支（同 dlt645：隐藏字段模板相关） |
| 7 | `_generate_frame()` 的模式分派 | 加 modular 分支 |
| 8 | 生成结果预览/解析 | 走 `ModularIfaceParser.parse_to_table` |
| 9 | 串口收包解析（回包用哪个解析器） | modular → `ModularIfaceParser`（**不得**落到国网/南网） |
| 10 | 「加入预设命令」按钮 | modular → `preset_buttons` 的 modular 模式 |
| 11 | 「加入测试方案」按钮 | 与 dlt645 同路径（无协议特化） |
| 12 | `_restyle_for_theme()` / 初始化时的默认态 | 按 `self.protocol_mode` 恢复；新增控件需一并重绘 |

**回归护栏**：`test/test_dlt645_frame_gen_gui.py` 必须全绿；切到其它协议后 `set_protocol_mode` 行为与改动前逐一比对。

### 7.1 组帧页新增控件（modular 模式专属容器）

- 控制域组：`DIR` 下拉（终端发出 0 / 模块发出 1）、`PRM` 下拉（模块发起 0 / 终端发起 1）、
  `控制码` 下拉（确认/否认/信息）、`FID` 数字框
- APDU 组：模板下拉 + 参数区（DT 输入、Data 类型下拉（表4 25 类）+ 值输入、DAR 下拉、缓冲区长度等）
- 结果区：hex 输出 + `ModularIfaceParser` 回读表格
- **只在 modular 模式可见**（与现有模式各自的控件组同一套 `setVisible` 机制）

---

## 8. 契约 G：预设命令（`preset_buttons.py`）

- 模式 `"modular"`，数据文件 `app_paths.data_path("modular_command.json")`
  （**不与** `NW_command.json` / `GW_command.json` / `DLT645_command.json` / 698 的文件混写）。
- 种子 5 条（文件缺失时写入）：读模块信息 / 读链路协商信息 / 读时钟 / 链路协商请求 / ACK 确认帧。
- 每条 = `{name, hex}`；`AppConfig` 往返不丢字段（照现有模式的读写路径）。
- 点条目 → 填入单帧页输入框并按协议12 解析（沿用既有 `preset` 接线，必要时在 `main_gui` 的
  `set_protocol` 分支加 `modular`）。

---

## 9. 契约 H：查询页（`main_gui._create_modular_iface_lookup_content`）

重做为 6 组（`QTabWidget` 或分组 `QComboBox` 切换 + 单张可搜索表）：

| 组 | 列 | 来源 |
| --- | --- | --- |
| 控制码 | 控制码 / 名称 / 说明 | 表2 |
| APDU | 标记 / 名称 / 字段 | 表13~表21 |
| 通用信息类 | DT / DTA1 / DTA2 / 名称 / 定义 | 附录 C |
| 模块信息类 | DT / 所属模块 / 名称 / 定义 | 附录 G/J/K/L |
| 物理单位 | 代码 / 符号 / 名称 | 附录 M |
| 设备子接口 | 模块 / 虚拟通道号 / 接口形式 / 功能定义 | 附录 D~L |
| 厂商标识 | 键 / 值 | 附录 B |

- 搜索框匹配所有列（含 DT 的十进制与 `0x` 形式、名称子串）；显示「匹配 N / 共 M 条」。
- 表格用 `ZoomableTableWidget` + `_setup_table_copy_menu`；不得自写 stylesheet。
- 数据**只来自** `modular_iface_data.py`（禁止在 `main_gui` 内联第二份表）。

---

## 10. 契约 I：批量摘要

`main_gui._get_summary_from_table_data` 新增 `proto == 12` 分支，调用
`ModularIfaceParser.get_summary(frame)`：

```
终端→模块 | 信息帧 | 信息类:模块信息(0000) | 数据读取请求      # 末段取实际 APDU 名
模块→终端 | 确认帧 | FID:3
模块→终端 | 否认帧 | 错误码:0x0002
```

空结果兜底为 `协议12 帧(长度 N)`，绝不返回空串（`prd.md` AC4.2）。

---

## 11. 兼容性与回归

| 既有契约 | 处理 |
| --- | --- |
| `test/test_modular_iface.py` 现有 46 项 | **允许**因 A-XDR 重写而修改期望值（原期望是自证闭环、无外部依据）；但**必须**新增文档对拍与真实编码依据断言 |
| 其它协议解析器/校验器 | 零改动 |
| `FrameGenWidget` 的 south/gdw/dlt698/dlt645 四模式 | 行为逐一不变（`test_dlt645_frame_gen_gui.py` + 新增四模式冒烟） |
| `PresetButtonWidget` 四模式 | 行为不变，modular 独立文件 |
| `config.json` / 既有数据文件 | 不读写；modular 用自己的文件 |
| `release_check.py:CORE_TESTS` | 已含 `test/test_modular_iface.py`；如拆分新测试文件需一并登记 |

---

## 12. 风险与缓解

| 风险 | 级别 | 缓解 |
| --- | --- | --- |
| **A-XDR 编码假设与实际不符**（文档无示例帧） | 高 | §2.2 双开关单点可切；`verify_frame()['axdr_tail']` 作为判据；`AGENTS.md` 记录「无文档示例 → 按 DL/T 790.6 + 698.45 附录H 推导」及切换方法；**交付时明确告知用户：拿到真实帧后先跑 `verify_frame`** |
| 附录 D~M 表格录入出错（量大、易抄错） | 中 | 逐条对拍测试；表格只在 `modular_iface_data.py` 一处；测试失败即指到具体行 |
| 组帧页第 5 模式污染既有 4 模式 | 中 | §7 逐处分派点清单 + 四模式回归测试；modular 控件独立容器、按 `protocol_mode` 显隐 |
| 文档自身矛盾（§6.3.9 指向附录 L、附录 K.2/L.2 互指） | 低 | 以实际定义所在附录为准（物理单位取附录 M），在 `AGENTS.md` 记录矛盾，不改文档、不臆造 |
| 重写 APDU 层导致既有 46 项测试大红 | 低 | 明确「原期望无外部依据」；按 §11 处理，逐个核对而非批量改期望 |
| 数据域长度 > 4095（L 只有 12 位） | 低 | 组帧时校验并给可读错误（超长必须报错，不得截断） |

---

## 13. 回滚

- 新增文件（`modular_iface_axdr.py` / `modular_iface_data.py`）：删文件即可。
- `modular_iface_parser.py` / `modular_iface_frame_gen.py`：重写前先把当前版本另存为
  `.trellis/tasks/09-23-modular-iface-protocol/baseline/`（**只做对照，不进仓库**），
  需要时可直接恢复。
- 注册表/GUI 接线：把 `frame_gen_mode` / `preset_mode` 改回 `None` 即回到「只有解析」的现状。
- `frame_gen_widget.py` / `preset_buttons.py` 的改动是**纯增量分支**，逐步 `git diff` 可单独撤销。

---

## 14. 验证策略

```bash
# 1) 纯逻辑层（无 Qt）：A-XDR / 表 / 组帧闭环
pwshu 'python -u test/test_modular_iface.py'

# 2) 组帧页与预设页 offscreen
pwshu 'python -u test/test_dlt645_frame_gen_gui.py'
pwshu 'python -u test/test_protocol_registry.py'
pwshu 'python -u test/test_web_landing.py'

# 3) 全量发布自检
pwshu 'python release_check.py'
```

**文档对拍必须能变红**：表格里逐条断言（DT/单位/子接口），抄错一条即失败；
A-XDR 断言用 698 附录 H.1.1 的 `07 E0 05 13 04 08 05 00 00 A4` 作独立 oracle
（断言 `decode_value(...) == 2016-05-19 08:05:00.164`，而不是断言自己 `encode` 出来的东西）。
