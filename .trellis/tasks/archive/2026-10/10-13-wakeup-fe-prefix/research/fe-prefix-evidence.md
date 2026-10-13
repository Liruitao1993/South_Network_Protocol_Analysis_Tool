# 证据档：前导 FE 与蓝牙分包（可复现）

> 本文件是 10-13-wakeup-fe-prefix 的事实基线。所有结论均由脚本对**仓库现状**重算得出，不凭阅读整理。

## E1 报障帧逐字节复核（协议8）

输入（用户现场，蓝牙工具页 `[RX·0xFFE1]`，39 字节）：

```
FEFEFEFE682100C3051111111111110084848501014001020001090611111111111100005DA016
```

复现脚本（项目根执行）：

```python
import sys, os; sys.path.insert(0, r"E:\python\南网解析工具"); os.chdir(r"E:\python\南网解析工具")
from dl_t698_45_parser import DLT69845Parser
raw = bytes.fromhex("FEFEFEFE6821 00C3051111111111110084848501014001020001090611111111111100005DA016".replace(" ", ""))
p = DLT69845Parser()
print(len(raw), p.parse(raw)["解析状态"], p.parse(raw).get("错误信息"))
print(len(raw[4:]), p.parse(raw[4:])["解析状态"])
for r in p.parse_to_table(raw[4:])[:6]: print(r)
```

实测输出（现状）：

```
39 失败 起始字符错误: 0xFE, 期望 0x68
35 成功 None
('起始字符', '0x68', '-', '帧起始标志', 0, 0)
('长度域', '2100', '33', 'bit0~13=33, bit14=0, 单位=字节', 1, 2)
('控制域', '0xC3', '-', '', 3, 3)
('  DIR', '1', '服务器→客户机', '传输方向', 3, 3)
('  PRM', '1', '客户机发起', '启动标志', 3, 3)
```

剥离 4 字节后：**35 = L(0x21=33) + 2** ⇒ 与 §6.2.2 a)「整帧 = L + 2」自洽；
`帧头校验HCS 84 84 通过`、`帧校验FCS A0 5D 通过`、`GET-Response`、`OAD 40010200` → 通信地址、数据 `111111111111`。

## E2 规范依据（原文行号，仓库内可复核）

| 协议 | 出处 | 原文 |
|---|---|---|
| 698.45 | `协议文档/8.698.45协议/面向对象的用电信息数据交换协议(20210910).md:509`（§6.3.1 字节规则） | `b) 在有效数据帧前加 4 个 FEH 作为前导码；` |
| 698.45 | 同文件 `:511` | `c） 数据链路层帧的字节之间无线路空闲间隔；两帧之间的线路空闲间隔至少 33 位。` |
| 645-2007 | `DLT645-2007.md:486`（§5.3.1 前导字节） | `在主站发送帧信息之前，建议先发送 4 个字节 FEH，以唤醒接收方。` |
| 645-2007 | `DLT645-2007.md:498`（§5.3.3） | `字节之间停顿时间 Tb ≤ 500ms。` |

⇒ 协议8 是**必须**（「加 4 个 FEH 作为前导码」），协议6 是**建议**。本工具此前把首字节当起始符判据 ⇒ 不合规。

## E3 调用路径地图（为什么必须改在解析器层）

`parser.parse_to_table(frame_bytes)` 的直接调用方（RE 全仓，去掉 test/dist）：

| 调用方 | 文件 | 是否经过剥离 |
|---|---|---|
| 单帧解析 | `main_gui.py:7191` `parse_single` | 否（仅 ED 头部有处理） |
| 串口工具/蓝牙工具解析回调 | `main_gui.py:4403` `_serial_parse_provider` | 否 |
| 快捷解析小窗 | `main_gui.py:8872` `do_parse`（`_preprocess` 只处理 ED） | 否 |
| 批量解析（worker / 详情重解析） | `batch_parse_worker.parse_one_frame`、`MainWindow._get_frame_table_data` | 批量提取已从 `68` 起同步 |
| Web 单帧/批量 | `reflex_web/reflex_web/reflex_web.py:634`、`web_utils.extract_69845_frames` | 提取已从 `68` 起同步 |

⇒ 若在调用点剥离，需要改 ≥5 处且新增调用方会漏；改在解析器层一次覆盖全部。

协议6 的表格构建方是 `protocol_registry.DLT645GuiParser.parse_to_table`（桌面与 Web 共用的唯一实现，
由 `test_dlt645_tolerant_parse.py` A9 的源码守卫钉住），其偏移是**字面常量 + 帧长推导**，
故前导剥离后必须整体位移（见 design §3.3）。

## E4 蓝牙分包复核（报障 2）

```
bluetooth_worker._write_coro
  └─ _chunk_size_for(targets)
       ├─ 命中特征码 max_write（max_write_without_response_size）→ max(20, min(200, max_write))
       └─ 否则 → bluetooth_core.chunk_size_for_mtu(mtu, 200) = clamp(mtu - 3, 20, 200)
```

现场两包 20 + 5 ⇒ 单包上限 20 ⇒ **协商 MTU = 23**（= BLE 规范最小默认 ATT MTU）。
`bluetooth_core.MIN_CHUNK = 20`、`DEFAULT_MAX_CHUNK = 200`、`DEFAULT_SEND_PACKET_DELAY = 0.02`。

结论：25 字节 > 20 字节单包上限 ⇒ 分包**不可消除**（应用层无法一次写出）；可做的只有
① 日志说明原因；② 文档说明「帧内 20ms 间隙 vs 698 §6.3.1 c) 无空闲间隔 ⇒ 建议包间延迟设 0」；
③ 提示设备端支持更大 MTU 才能减少分包。源工具硬编码 200 字节在 MTU=23 设备上反而会直接写失败。

## E5 既有行为锚点（回归判据）

- 无 FE 帧必须逐行不变：`test_dlt645_tolerant_parse.py`（A4「字段数 = 13」、A8 `check_frame` 语义、
  「calc_checksum 与既有公式一致」）、`test_dlt645_table_offsets.py`（40 项）、`test_dl_t698_45.py`、
  `test_dl_t698_45_extract.py`（46 项）。
- `calc_checksum(f) == sum(f[0:-2]) & 0xFF` 对无 FE 帧必须继续成立（剥离是恒等操作）。
- `dlt645_sim` 读 `parsed.get("valid", True)` ⇒ `valid` 语义不变是硬约束。
