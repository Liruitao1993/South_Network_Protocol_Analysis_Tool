# 蓝牙自定义报文按钮：按协议替换地址域 + 重算校验（发送时生效）

## Goal

蓝牙页「自定义报文」按钮目前只能存「名称 + 内容 + HEX/ASCII」，发给不同表计时要手工改地址并重算校验（改错一位就整帧无效）。
本次让每个按钮可以绑定**协议**与**地址参数**：点按钮发送时，工具按该协议**替换地址域**并**重算校验**，界面明确告知改了什么。

用户已确认的四条口径（本轮问答）：

| 项 | 决定 |
|---|---|
| 任务 | 建立 Trellis 任务并推进 |
| 协议范围 | **6（DL/T645）/ 8（698.45）+ sum 族 0（南网）/ 7（国网）/ 13（依瓦645）/ 14（南网上行）**；9/10/11/12 不做 |
| 地址写法 | 两种都认：12 位数字/协议地址 → 按协议编码；hex → 按**帧内在线顺序**原样写入 |
| 应用时机 | **只在发送时替换与重算**；发送框保持原始模板；日志列出「地址域 → …；校验 0xAA → 0xBB」 |

## 现状证据（实现必须与此一致）

- 按钮数据结构 `{name, data, isHex}`：`bluetooth_core.normalize_button`（`bluetooth_core.py:235-248`）、落盘 `save_settings`（`:278-304`）、对话框 `ButtonEditDialog`（`bluetooth_tool_widget.py:588-692`）、批量导入 `parse_button_lines`（`:539-582`）、发送 `_on_custom_clicked`（`:2574-2585`）、「填入发送框」右键项（`:2605-2607`）。
- 仓库**没有**「改地址 + 重算校验并写回」的通用功能（全仓 grep 0 命中）；校验器只能读（`validator/base.py:94-101` `verify(frame_bytes) -> ValidationResult`，无「返回新帧」实现）。
- `protocol_registry.ProtocolSpec`（`protocol_registry.py:20-60`）**没有**地址偏移/长度或校验覆盖字段 ⇒ 需新增一层按协议适配（本次落在新模块，不改注册表结构）。
- 各协议既有可复用实现（**必须复用，不得另写第二份口径**）：

| 协议 | 地址 | 校验 |
|---|---|---|
| 0 南网 | `protocol_tool.Frame`：地址 = 源[::-1]+目的[::-1]，仅当控制域 **D5(add)**（`protocol_tool.py:38-54`） | `Frame.calculate_checksum = sum(...) & 0xFF`，覆盖 `packed_frame[3:]`（`:46-48,73`）。**帧内无第二个 68H**：`68 L L C … CS 16` |
| 6 645 | `dlt645_frame_gen.encode_addr`（12 位→6B 低字节在前；也接受 6B 原样） | `DLT645FrameGenerator.build_frame(addr, ctrl, data, scramble=False)` 内部算 CS（`:131-149`） |
| 7 国网 | 地址域存在 ⟺ 信息域 byte0 **bit2=通信模块标识**；长度 = **12 + 6×中继级别(byte0 高 4 位)**；布局 = 源(6B)+中继(6B×n)+目的(6B)，BCD **字节逆序**（`gdw_send_frame_lib.py:124-185`；`gdw10376_parser.py:444-457`） | `GDWFrame.calculate_checksum = sum(frame[3:-2]) & 0xFF`（`gdw10376_tool.py:94-96,119`） |
| 8 698.45 | SA（含地址特征字节，可变长）+ CA(1B)：`_assemble_frame(sa, ca, control, apdu)` | HCS = crc16(x-25)(长度域+控制域+SA+CA)；FCS = crc16(…+HCS+APDU)（`dl_t698_45_frame_gen.py:16-48`） |
| 13 依瓦645 | `yw645_wire.encode_addr12`（**高字节在前**，仅数字，>12 取低 12 位） | `yw645_wire.encode_frame(addr, mode, data)`（CS = `sum(body) & 0xFF`，`:218-224,510-523`） |
| 14 南网上行 | `csg_uplink_wire.encode_addr(a1, a2, a3)` → 7B（A1 3B 低字节在前 + A2 3B 小端 + A3 1B） | `csg_uplink_wire.encode_frame(c, addr, apdu, form)`（CS 覆盖**控制域+地址域+用户数据**，不含长度域，`:439-449`） |

## Requirements

### R1 纯逻辑适配层（新模块 `frame_addr_fix.py`，无 Qt）

- R1.1 `fields_for(protocol_index) -> Tuple[AddrField, ...]`：返回该协议需要用户填的地址字段（0/7 = 源地址+目的地址；6/8/13 = 表地址/SA(+CA)；14 = 终端地址），每个字段带**标签**与**写法提示**（长度、进制、示例）。
- R1.2 `apply(frame: bytes, protocol_index: int, values: Mapping[str, str]) -> FixResult`：
  - 先按该协议的**结构自证**判定输入帧合法（如 645 双 68H + 末 16H；0/7 长度域自洽；13 同 645 但地址高字节在前；14 三种长度域形态；8 长度域/末 16H），不合法 → `ok=False` + 可读原因（**不得**返回空结果或猜）；
  - 地址域**不存在**（南网 D5=0 / 国网 bit2=0）→ `ok=False`，说明「该帧不含地址域」；
  - 替换地址后**必须**重算校验，且**复用**上表既有实现（能整帧重建的走整帧重建：6/8/13/14；0/7 走字节拼接 + 复用其校验函数）；
  - `notes` 逐条给出「地址域 xx → yy」与「校验和 0xAA → 0xBB」（多校验帧列出每项，如 698 的 HCS/FCS）。
- R1.3 地址编码两条规则（用户口径）：
  - 输入是 **hex**（含 `0x`/空格分隔，长度为该字段在线字节数）→ **按在线顺序原样写入**；
  - 输入是**协议地址**（纯数字，如 645/依瓦 的 12 位表号、14 的终端地址十进制）→ 调该协议既有编码函数（自动处理字节序/BCD/低位在前）。
  - 两种都不匹配 → `ok=False` + 可读原因（例如「645 表地址应为 12 位十六进制或 6 字节 HEX」）。
- R1.4 **长度必须与帧内一致**：地址字段在线字节数必须等于原帧该字段长度，否则 `ok=False`（长度变了要改 L / HCS / FCS 布局，v1 不做，明确告知）。
- R1.5 支持的协议集合与不支持项的报错：`SUPPORTED_PROTOCOLS = (0, 6, 7, 8, 13, 14)`；其余（9/10/11/12 与 1/2/3/4/5）→ `ok=False`「该协议暂不支持地址替换（v1 支持 0/6/7/8/13/14）」。

### R2 GUI（`bluetooth_tool_widget.ButtonEditDialog`）

- R2.1 对话框新增「协议」下拉：`不处理` + `fields_for` 支持的协议（名称取自 `protocol_registry`，**不硬编码**）；选 `不处理` 时隐藏地址输入区。
- R2.2 地址输入区**按所选协议动态生成 1~2 个输入框**（标签/提示来自 `AddrField`），并实时提示「将写入 N 字节：`xx xx …`」或具体错误。
- R2.3 保存进按钮 dict 的新键 `protocol`（int|None）与 `addr`（dict[字段 key → str]）；`bluetooth_core.normalize_button` 宽容保留这两个键（坏值回落 `None`，旧配置无该键 → 无处理，行为与现在完全一致）。
- R2.4 按钮 tooltip / 批量导入导出 / 落盘回读都不丢新键；`parse_button_lines` 仍按 3 字段解析（v1 不扩批量格式），但**不可**把已有按钮的地址参数清掉。

### R3 发送路径（唯一改动点 `_on_custom_clicked`）

- R3.1 无协议/无地址 → 行为与现在逐字节一致（`parse_plain_text` → `_send_payload`）。
- R3.2 有协议+地址 → 先 `parse_plain_text` 得原始字节 → `frame_addr_fix.apply(...)`；失败 **弹框 + 日志、且一个字节都不发**；成功 → 日志输出 `notes`（含旧/新校验值），发送**处理后的帧**。
- R3.3 **发送框保持原始模板**（用户口径）：不写回 `edit_send`；「填入发送框」右键项也仍填原始模板。
- R3.4 `frame_addr_fix` 的任何异常都不得让按钮「点了没反应」：捕获异常 → 弹框 + 日志（同「弹框必留日志」契约）。

### R4 测试

- R4.1 新 `test/test_bluetooth_addr_fix.py`（纯逻辑）：
  - 每协议**真实帧 oracle**：替换地址后 ① 地址字节 = 期望（含字节序）；② **该协议校验器 0 fail**（`NWValidator`/`DLT645Validator`/`GDWValidator`/`DLT69845Validator`/`YW645Validator`/`CSGUplinkValidator`）；③ 其它字节未被改动；
  - 边界/错误：结构不符、无地址域、长度不符、hex 写错、协议不支持、空输入；
  - 反例自检（把校验重算去掉 → 校验器必红）。
- R4.2 `test/test_bluetooth_widget.py`：对话框协议联动（字段数量/标签）、保存回读、发送时替换（假 worker 断言**实际写出的字节**）、失败不发、发送框不被改写。
- R4.3 `test/test_bluetooth_core.py`：`normalize_button` 对新键的保留/回落/坏值宽容。
- R4.4 四份蓝牙测试 + `release_check.py --with-gui` FAIL=0（既有环境红除外）。

## Acceptance Criteria

- A1 建一个绑定「协议6 + 表地址 `000000000033`」的按钮，内容为现场帧 `68 33 00 00 00 00 00 68 11 04 …E5 16`：点按钮发送，实际写出帧的地址域变为目标地址且 **CS 正确**（校验器 0 fail），发送框内容不变，日志有 `地址域 … → …` 与 `校验和 0x… → 0x…`。
- A2 同一按钮把地址写成非法值（位数不对/非 hex/长度不符）→ 弹框说明原因，**不发送任何字节**（假 worker 写入列表为空）。
- A3 不绑定协议的按钮行为与 1.23.80 逐字节一致（回归断言）。
- A4 南网/国网帧在地址域不存在（D5=0 / 模块标识=0）时报「该帧不含地址域」，不静默发送原帧。
- A5 6 个协议各有一条真实帧用例，替换后校验器 0 fail；变异反证（去掉校验重算）逐条变红。

## 非目标

- 不做 9/10/11/12（FCCS/PBCS/ICV、PPP FCS 与多层地址）——v1 明确不支持并给可读提示。
- 不做「批量导入时带地址列」（v1 只保证不丢已有参数）。
- 不做地址长度改变（会连带改 L/HCS/FCS 布局）。
- 不改 Web 版（Reflex 无蓝牙）。
