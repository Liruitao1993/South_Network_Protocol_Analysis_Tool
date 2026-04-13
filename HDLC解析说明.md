# HDLC协议解析功能说明

## 概述

基于 **IEC 62056-46** 国际标准（DLMS/COSEM数据链路层），为南网协议解析工具新增了HDLC协议解析能力。

## 功能特性

### 1. HDLC帧结构解析

完整解析HDLC Frame Format Type 3帧结构：

```
┌─────────┬──────────┬──────────┬──────────┬─────┬──────────┬─────┬──────────┐
│ 起始标志 │  格式域  │ 目的地址 │  源地址  │控制域│   HCS    │信息域│   FCS    │ 结束标志 │
│  1字节  │  2字节   │  可变    │  可变    │ 1字节│  2字节  │ 可变 │  2字节  │  1字节  │
│  0x7E   │ Type 3   │ 扩展地址 │ 扩展地址 │      │ 校验和  │      │ 校验和  │  0x7E   │
└─────────┴──────────┴──────────┴──────────┴─────┴──────────┴─────┴──────────┴──────────┘
```

### 2. 支持的HDLC帧类型

| 帧类型 | 控制域格式 | 说明 |
|--------|-----------|------|
| **I帧** | N(R) P/F N(S) 0 | 信息传输帧（带序号的数据帧） |
| **RR帧** | N(R) P/F 0 0 0 1 | 接收就绪（确认帧） |
| **RNR帧** | N(R) P/F 0 1 0 1 | 接收未就绪（忙状态） |
| **SNRM帧** | 1 0 0 P 0 0 1 1 | 设置正常响应模式（建立连接） |
| **DISC帧** | 0 1 0 P 0 0 1 1 | 断开连接 |
| **UA帧** | 0 1 1 F 0 0 1 1 | 无编号确认（响应SNRM/DISC） |
| **DM帧** | 0 0 0 F 1 1 1 1 | 断开模式 |
| **FRMR帧** | 1 0 0 F 0 1 1 1 | 帧拒绝（错误报告） |
| **UI帧** | 0 0 0 P/F 0 0 1 1 | 无编号信息（独立数据传输） |

### 3. 地址域解析

支持HDLC扩展地址机制：
- **1字节地址**：范围 0x00-0x7F
- **2字节地址**：范围 0x0000-0x3FFF
- **4字节地址**：范围 0x00000000-0x1FFFFFFF

特殊地址：
- `0x00`: NO_STATION（无站地址）
- `0x01`: 客户端管理进程
- `0x10`: 公共客户端（最低安全级）
- `0x7F`: ALL_STATION（广播地址）

### 4. DLMS数据解析

自动识别HDLC信息域中的DLMS/COSEM应用层数据：
- **AARQ** (0x01): 关联请求
- **AARE** (0x02): 关联响应
- **Get-Request** (0xC0): 读取请求
- **Get-Response** (0xC4): 读取响应
- **Set-Request** (0xC1): 写入请求
- **Set-Response** (0xC5): 写入响应
- **Action-Request** (0xC2): 操作请求
- **Action-Response** (0xC6): 操作响应

### 5. 校验计算

- **HCS** (Header Check Sequence): 头部校验，使用CCITT-CRC16多项式
- **FCS** (Frame Check Sequence): 帧校验，使用CCITT-CRC16多项式

## 使用方法

### GUI界面使用

1. 启动程序：
   ```bash
   python main_gui.py
   ```

2. 在协议下拉菜单中选择 **"HDLC/DLMS协议 (IEC 62056-46)"**

3. 在输入框中输入HDLC十六进制报文，例如：
   ```
   7E A0 07 01 01 93 00 00 00 00 7E
   ```

4. 点击"解析报文"按钮查看结果

### 编程使用

```python
from hdlc_parser import HDLCParser

# 创建解析器
parser = HDLCParser()

# 解析HDLC帧
frame_bytes = bytes([
    0x7E, 0xA0, 0x07, 0x01, 0x01, 0x93, 
    0x00, 0x00, 0x00, 0x00, 0x7E
])

# 表格格式解析
table = parser.parse_to_table(frame_bytes)
for row in table:
    print(f"{row[0]}: {row[1]} -> {row[2]}")

# 结构化字典解析
result = parser.parse(frame_bytes)
print(result)
```

### 测试脚本

运行测试脚本查看各种HDLC帧类型的解析示例：

```bash
python test_hdlc.py
```

## 典型应用示例

### 示例1: SNRM帧（建立连接）

```
7E A0 07 01 01 93 00 00 00 00 7E
```

解析结果：
- 起始标志: 0x7E
- 格式域: Type 3, 长度=7
- 目的地址: 0x01 (客户端管理进程)
- 源地址: 0x01
- 控制域: SNRM帧, P=是 (设置正常响应模式)
- HCS: 0x0000
- FCS: 0x0000
- 结束标志: 0x7E

### 示例2: I帧（携带DLMS Get-Request）

```
7E A0 15 01 01 00 00 00 C0 00 00 00 01 01 C0 01 01 00 00 28 00 00 FF 02 00 00 7E
```

解析结果：
- 控制域: I帧, N(S)=0, N(R)=0
- 信息域: 包含DLMS Get-Request APDU
  - DLMS控制字段: 0xC0 (长格式)
  - 目标地址: 0x00000001
  - 源地址: 0x01
  - APDU类型: Get-Request
  - 调用ID: 0x01
  - OBIS码: 1.0.1.8.0.255 (有功电能)

## 技术细节

### 控制域位映射

根据IEC 62056-46 Table 7：

| 帧类型 | Bit 7-5 | Bit 4 | Bit 3-0 |
|--------|---------|-------|---------|
| I帧 | N(R) | P/F | N(S) 0 |
| RR帧 | N(R) | P/F | 0001 |
| RNR帧 | N(R) | P/F | 0101 |
| SNRM帧 | 100 | P | 0011 |
| DISC帧 | 010 | P | 0011 |
| UA帧 | 011 | F | 0011 |
| DM帧 | 000 | F | 1111 |
| FRMR帧 | 100 | F | 0111 |
| UI帧 | 000 | P/F | 0011 |

### CRC16计算

使用CCITT-CRC16多项式：x^16 + x^12 + x^5 + 1 (0x8408)

```python
def calculate_fcs(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc ^ 0xFFFF
```

## 参考标准

- **IEC 62056-46**: Electricity metering – Data exchange for meter reading, tariff and load control – Part 46: Data link layer using HDLC protocol
- **ISO/IEC 13239**: High-level data link control (HDLC) procedures
- **DLMS/COSEM**: Device Language Message Specification / Companion Specification for Energy Metering

## 文件说明

- `hdlc_parser.py`: HDLC协议解析器核心实现
- `test_hdlc.py`: HDLC解析功能测试脚本
- `HDLC.md`: IEC 62056-46标准文档（英文）
- `main_gui.py`: 主GUI程序（已集成HDLC解析选项）

## 版本信息

- **版本**: 1.0
- **日期**: 2026-04-13
- **作者**: 基于南网协议解析工具扩展
