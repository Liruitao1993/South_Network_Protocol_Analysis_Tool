# Design：协议7（国网）福建增补 + EB 数据标识扩展

## 1. 目标与范围

在现有协议7（Q/GDW 10376.2—2024）基础上增加：
1. **376.2 福建增补规约**（附件3）：AFN=50H~56H 帧的识别、信息域/地址域解析、各 AFN/Fn 数据单元解析、组帧。
2. **通信模块扩展协议**（附件1）：EBXXXXXX 数据标识（645 承载）的识别与深度解析。

## 2. 现状（已分析）

| 模块 | 现状 |
|---|---|
| `gdw10376_parser.py` GDW10376Parser | AFN_MAP 0x00~0xF1，FN_MAP 各 AFN 下 Fn；`parse_to_table` 解析 68+L+C+R+A+AFN+DT+CS+16；信息域按 2024 国网 6B 结构解析；地址域含 A1+A2+A3 |
| `gdw10376_tool.py` GDWControlField | 控制域 C（DIR/PRM/通信方式） |
| `gdw_send_frame_lib.py` GDWFrameGenerator | `generate_frame(afn, fn, field_values, info_config, src_addr, dst_addr, relay_addrs)`；schema 驱动 |
| `gdw_frame_generator_schema.py` GDW_AFNFN_SCHEMA | (afn, fn) → {name, direction, fields, doc}；**无 50H~56H** |
| `validator/gdw_validator.py` GDWValidator | AFN_VALID_RANGE = range(0x00, 0xF2)；长度/起始/结束/校验和/AFN 值域 |
| `gdw_afn_lookup.py` GDWAFNLookup | 复用 parser.get_afn_fn_list() |
| GUI `main_gui.py` | 协议7 parser/validator/查询页/组帧页（frame_gen_widget） |

## 3. 关键差异：福建增补 vs 2024 国网帧结构

### 3.1 信息域 R
| | 2024 国网下行（表4） | 福建增补下行（附件3 §5.2） |
|---|---|---|
| 字节0 | 路由/附属/通信模块/冲突/中继级别 | **保留（兼容原报文格式）** |
| 字节1 | 信道标识+纠错 | 保留 |
| 字节2 | 预计应答字节数 | 保留 |
| 字节3-4 | 通信速率 | 保留 |
| 字节5 | 报文序列号 | **报文序列号** |
| 总长 | 6B | 6B |

| | 2024 国网上行（表5） | 福建增补上行（附件3 §5.2） |
|---|---|---|
| 字节0-3 | 路由/通信模块/中继/信道/相位/通道特征/品质/事件 | **保留（BS 4B）** |
| 字节4 | 事件标志 | **事件标志（BS1：D0）** |
| 字节5 | 报文序列号 | **报文序列号** |
| 总长 | 6B | 6B |

**识别策略**：不能仅凭信息域字节区分（结构相似）。采用**AFN 驱动**：当 AFN ∈ {0x50,0x51,0x52,0x53,0x55,0x56} 时按福建增补 R 结构解析；否则按 2024 国网。这是最可靠的判别——福建增补功能码全部从 0x50 起（附件3 修订日志 V1.1："将增补规约所有功能码均增加 50H"）。

### 3.2 地址域 A
| | 2024 国网 | 福建增补 |
|---|---|---|
| 结构 | A1(6B) + A2(中继, 6×中继级别) + A3(6B) | **A1(6B) + A3(6B)，无 A2** |
| 触发 | 通信模块标识=1 | **信息域无通信模块标识位**（保留），需按帧长/剩余字节判断 |

福建增补地址域始终存在（附件3 §5.3 明确"取消中继地址 A2，主节点下行时源地址 A1 是主节点 MAC，目的地址 A3 是从节点 MAC；广播时 A3=999999999999"）。解析时：福建增补帧用户数据 = R(6B) + A1(6B) + A3(6B) + AFN + DT + 数据单元。

### 3.3 数据单元标识 DT
两协议相同：DT1 + DT2，`_dt_to_fn` 复用。

## 4. 设计

### 4.1 GDW10376Parser 扩展（gdw10376_parser.py）

**AFN_MAP/FN_MAP 新增（福建增补）：**
```
0x50: "确认/否认"  → F1 确认, F2 否认, F3 确认且还有后续任务
0x51: "初始化"     → F1 硬件初始化, F2 参数区初始化, F3 数据区初始化
0x52: "数据转发"   → F1 转发通信协议数据帧, F2 任务队列_智能补采, F3 任务队列_本地定时,
                     F11 并发抄表_福建, F12 清空并发抄表队列
0x53: "查询数据"   → F1 本地模块参数配置请求, F2 主节点地址, F4 厂商代码和版本信息,
                     F5 通信信道信息, F6 串口当前通信参数, F10 模块通信协议模式切换
0x55: "控制命令"   → F1 设置主节点地址, F2 允许/禁止从节点上报, F3 启动广播(不修正),
                     F4 启动广播(修正), F6 启动从节点主动注册, F7 结束当前任务,
                     F8 启动预告任务执行, F9 预告抄读对象, F10 模式切换,
                     F11 串口通信速率协商, F12 自动恢复默认速率时长, F13 允许协商最高速率,
                     F18 启动预告任务执行(2字节长度模式)
0x56: "主动上报"   → F1 主动注册从节点信息, F2 从节点主动上报事件内容, F3 通信对象具体抄读内容请求,
                     F4 预告的通信对象响应报文, F5 信道延时信息报文, F6 广播任务完成,
                     F13 抄读内容请求(2B长度), F14 预告响应报文(2B长度), F15 带任务信息的事件上报
```

**parse_to_table 改动：**
- 读取 AFN 后判断 `is_fujian = afn in FUJIAN_AFNS`（{0x50,0x51,0x52,0x53,0x55,0x56}）。
- 信息域解析分支：`is_fujian` 时走福建增补 R 结构（下行：保留5+序列号；上行：保留4+事件标志+序列号）。
- 地址域解析分支：`is_fujian` 时固定 A1+A3=12B（从信息域后直接取 12B，若剩余字节足够），且无论"通信模块标识"位。
- `_parse_data_unit` 新增 `elif afn in (0x50, 0x51, 0x52, 0x53, 0x55, 0x56)` 分支，按各 Fn 解析数据单元（上行/下行方向由 `is_upstream` 区分）。

**新方法 `_parse_fujian_afn(afn, fn_list, data_bytes, table_data, base_offset, is_upstream)`** 集中处理福建增补 6 个 AFN 的数据单元解析，避免 `_parse_data_unit` 过度膨胀。

### 4.2 EB 数据标识（附件1）

EB 数据标识的 645 帧结构：
```
68H A0..A5 68H 控制码(91/81/11/14...) 数据域长度L DI3 DI2 DI1 DI0 数据 CS 16H
```
- DI = EB XX XX XX（小端，数据标识字节序 DI3 DI2 DI1 DI0 = 帧中顺序 03 00 01 EB → EB030001）
- 附件1 表 1.1 定义了全部 EB 数据项（EB0300XX 事件、EB0301XX 台区识别、EB0302XX 设备基础、EB0303XX 相位/NTB、EB0305XX 时钟、EB0311XX 档案、EB0312XX 抄控器、EB0320XX 主节点地址、EB0321XX 精准停电、EB0402XX 复位/停电次数、EB0403XX 停上电记录、EB0405XX 上报路径/通信接口/网络状态、EB0406XX 任务队列、EB55XX 功能映射、EBE0XX 冻结、EBEEEEEE 多数据项）

**实现位置**：新建 `gdw_eb_di_lookup.py`（EB 数据标识 → 名称/格式/长度/单位/功能），仿照 `gdw_afn_lookup.py` 模式；解析器 `_parse_data_unit` 中 AFN=52H-F1（透明转发）/56H-F2（主动上报事件内容）内嵌 645 帧时，检测 DI 前缀 EB 后调用 `_parse_eb_di` 深度解析。

**新增 `_parse_eb_di(di_bytes, data_bytes, base_offset)`**：按附件1 各 EB 项的数据格式（BIN/BCD/ASCII/BS8/组合）解析内容。

注意：645 帧深度解析在协议6（DLT645）有现成 `DLT645Parser.parse()`，但它是独立 JSON 驱动的，EB 数据标识不在 `dlt645_di.json`。选择在协议7 侧新增 EB 映射，**不改动 dlt645_di.json**（生成文件勿手改）。

### 4.3 组帧（gdw_frame_generator_schema.py + gdw_send_frame_lib.py）

**schema 新增** 福建增补各下行 AFN/Fn 字段（对应附件3 §5.5 数据单元格式）：
- (0x50,*) 上行无下行字段
- (0x51,1/2/3) 无数据单元
- (0x52,1) 通信对象类型(enum) + 通信对象地址(BCD 6B) + 透明转发控制字(BS8) + 接收等待报文超时(BS8) + 接收等待字节超时(BIN) + 报文长度(2B) + 报文内容(bytes)
- (0x52,2/3/11) 任务方案号(2B) + 具体任务序号(2B) + 通信对象类型 + 通信对象地址(6B) + 规约类型 + 保留 + 报文长度(2B) + 报文内容
- (0x52,12) 无数据单元
- (0x53,1/2/4/5/6/10) 下行无数据单元 或 查询参数
- (0x55,1) 主节点地址(6B BCD)
- (0x55,2) 设置对象数量n + n×[通信对象类型+地址+事件上报状态标志]
- (0x55,3) 通信对象类型 + 广播时长 + 广播报文长度n + 广播请求内容
- (0x55,4) 通信对象类型 + 广播时长
- (0x55,6) 允许执行时间(2B 分钟)
- (0x55,8) 无数据单元
- (0x55,9) 本次预告对象数量(2B) + 通信延时修正标志 + n×[预告对象序号(2B)+通信对象类型+地址(6B)]
- (0x55,10/11/12/13) 模式切换/速率协商
- (0x55,18) 无数据单元
- (0x56,*) 上行主动上报，无下行字段（下行是确认）

**gdw_send_frame_lib.py 改动**：`generate_frame` 需支持福建增补帧的 R 结构（保留+序列号）与 A 结构（无中继 A2）。新增参数或由 afn 自动切换：
- `info_config` 增加 `"增补"` 标志或检测 afn ∈ FUJIAN_AFNS 自动用增补 R/A 结构。
- 福建增补 R 下行 = 5×0x00 + 序列号；上行 = 4×0x00 + 事件标志 + 序列号（组帧以下行为主）。
- 福建增补 A = A1 + A3（12B），忽略 relay_addrs。

### 4.4 校验（validator/gdw_validator.py）

- AFN_VALID_RANGE 保持覆盖，但 AFN 值域检查需放宽：福建增补 AFN 0x50~0x56 已在 range(0x00,0xF2) 内，天然支持。
- 信息域/地址域解析逻辑在解析器内，validator 主要做帧级校验（起始/长度/校验和/结束符），兼容福建增补帧（帧结构相同 68+L+C+...+CS+16）。
- 补充：福建增补帧长度校验——用户数据长度 = R(6)+A(12)+AFN(1)+DT(2)+数据单元。

### 4.5 GUI 集成

- 查询页：`get_afn_fn_list()` 自动包含新 AFN/Fn（GDWAFNLookup 复用），无需改查询页代码。可新增 EB 数据标识查询区块（仿 `_create_hdc10_lookup_content` 模式，但 EB 查询做成协议7 内新 tab 或列表）。
- 组帧页：`frame_gen_widget.py` 的 `afn_fn_combo` 从 `gdw_generator.get_supported_afn_fn()` 填充（自动含新 schema）。福建增补帧的 R/A 结构由 generate_frame 内部根据 afn 切换，**GUI 无需新增控件**（可选：在国网帧配置加"增补模式"复选框以明确切换，但默认自动识别更省事）。
- 校验：`_run_validation` 的 validators dict 已注册 7 → GDWValidator，无需改。

## 5. 兼容性与风险

| 风险 | 缓解 |
|---|---|
| 福建增补 AFN 0x50~0x56 与现有国网冲突 | 现有国网 AFN_MAP 无 0x50~0x56，无冲突；解析按 AFN 判定 |
| 信息域解析错位 | AFN 驱动判定，福建增补帧 AFN 必在增补集合内 |
| 地址域判定 | 福建增补帧固定 A1+A3=12B，按剩余字节量判断（剩余 ≥ 12+3+尾部），可靠 |
| EB 数据标识识别 | 645 帧 DI 首字节 0x03/0x04/0x55/0xE0/0xEE + 前缀 EB 判定；不影响普通 645 DI |
| 组帧回归 | generate_frame 仅对增补 AFN 切换 R/A 结构，原 AFN 路径不变 |
| dlt645_di.json | 不修改（生成文件），EB 映射独立成新模块 |

## 6. 文件清单

- 新增：`gdw_eb_di_lookup.py`（EB 数据标识映射）、`test/test_gdw_fujian.py`
- 修改：`gdw10376_parser.py`（AFN/FN 映射 + 信息域/地址域分支 + _parse_fujian_afn + _parse_eb_di）、`gdw_frame_generator_schema.py`（福建增补 schema）、`gdw_send_frame_lib.py`（增补 R/A 结构）、`validator/gdw_validator.py`（可选：长度校验细化）、`main_gui.py`（可选：EB 查询区块）、`AGENTS.md`、`README.md`、CHANGELOG
