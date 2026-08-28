# PRD: 完整实现 0x0005 OFDMA多用户下发 三帧类型解析

## Goal

按通感一体物联版文档完整实现 0x0005（OFDMA多用户下发）解析：字节3为帧类型(2bit) + 保留(6bit)，其后为可变区域（FC公共域 + 根据帧类型解析eFC）。

## Background

- 之前版本错误地把字节3解析为"OFDMA类型(1bit) + 调度节点数(3bit) + 保留(4bit)" + 每站点TEI(2字节)。
- 实际文档定义（3.1.1.4.5 OFMDA多用户下发）：
  - 字节3 bit0-1: 帧类型（0=DL_OFDMA立即发送, 1=UL_OFDMA等待触发, 2=UL_OFDMA trigger立即发送, 3=保留）
  - 字节3 bit2-7: 保留
  - 字节4起: 可变区域 = OFDMA帧的完整FC域 + 可选eFC域
- OFDMA帧FC域（表26，13字节，字节号1-13相对于OFDMA帧起始，即数据区字节4-16）：
  - 源TEI(12bit), 目的TEI(12bit), 多站点标识(1bit), OFDMA帧类型(2bit), 频段标识(3bit),
  - 站点数(2bit), eFC符号个数(2bit), PL符号数(9bit), 帧长(12bit), SNID高1位等
- eFC根据帧类型不同：
  - 类型0 (DL-OFDMA): eFC表27 — TF个数 + 每站(PB数+TEI+TMI+RU+SACK RU)，最多4站, 16字节含CRC
  - 类型1 (UL-OFDMA / DL SACK): 无eFC
  - 类型2 (UL-OFDMA trigger): eFC表28 — TF个数 + 每站(PB数+TEI+TMI+RU+Tx功率回退)，最多4站, 16字节含CRC
  - 类型3 (UL-OFDMA SACK): eFC表29 — 每站(TEI+接收状态)，最多4站

## Requirements

1. 字节3解析：帧类型(2bit) + 保留(6bit)
2. FC公共域解析（表26，对应数据字节4-16）：源TEI、目的TEI、多站点标识、OFDMA帧类型、频段标识、站点数、eFC符号个数、PL符号数、帧长、SNID
3. 根据帧类型解析eFC：
   - 类型0 (DL-OFDMA): 解析表27格式eFC（最多4站点，每站PB数/TEI/TMI/RU/SACK RU）
   - 类型1: 无eFC
   - 类型2 (UL-OFDMA trigger): 解析表28格式eFC（最多4站点，每站PB数/TEI/TMI/RU/Tx功率回退）
   - 类型3 (UL-OFDMA SACK): 解析表29格式eFC（最多4站点，每站TEI/接收状态）
4. 数据不足时给出明确提示，不崩溃
5. eFC CRC 24bit 暂不校验（只显示原始值）

## Acceptance Criteria

- [x] 输入0x0005数据 `02 09 01 F0 FF 1D 02 FF 01 FF 0F 00 00 20 F4 0F 58 13 80 98...`：
  - 帧类型 = UL_OFDMA的trigger (2)
  - FC域正确解析（源TEI=0x001 / 目的TEI=0xFFF / 多站点=1 / OFDMA帧类型=2 / 站点数=1 / PL符号数 / 帧长 / SNID）
  - eFC按trigger帧格式解析（TF个数 / 每站PB数/TEI/TMI/RU/Tx功率回退）
- [x] 三种帧类型（DL/UL/trigger/SACK）都能正确分派
- [x] 数据不足时不崩溃
- [x] 其他扩展ID不受影响

## Out of Scope

- eFC CRC校验（只显示原始值）
- PB数据内容解析
- 修改其他扩展ID

## Technical Notes

- 修改文件: `csg_new_gen_cmd_payloads.py` `_parse_test_ext_0005`
- 字节偏移基准：data[0] = 文档字节3（帧类型字节）
- data[1] = 文档字节4（FC起始），即FC域的"字节1"是data[1]
- eFC从data[1+13] = data[14]开始（FC占13字节：文档字节1-13）
- 使用现有 `_bits` 工具函数（小端位序，bit_start从最低位算起）
