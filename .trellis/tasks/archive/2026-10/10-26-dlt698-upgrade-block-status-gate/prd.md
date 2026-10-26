# 光伏升级：全部块确认后先校验传输块状态字（F00104）再执行升级

## Goal

用户：「光伏升级需要在所有文件传输完成后，查询一下设备的升级状态位图，使用如下这个帧
`68 17 00 43 05 11 11 11 11 11 11 10 6A 36 05 01 00 F0 01 04 00 00 B0 8B 16`，
然后确认回复内容是否完整，然后再发送执行升级命令。」

现状：`dlt698_upgrade_widget._on_ack(PHASE_BLOCKS)` 在末包确认后**直接**发执行升级
（勾了自动执行）或进入收尾（未勾）——中间没有校验设备是否真的收全了所有块。

## 协议依据（已核对文档，不是猜）

- 《面向对象的用电信息数据交换协议（20210910）》F001 类（文件分块传输管理，class_id=18）：
  **属性4 = 传输块状态字（只读）::= bit-string** ——「按 bit 位标识每个数据块的传输状态。
  bitN=0 表示未传输，bitN=1 表示传输成功（N 从 0…总传输块数-1）」。
- 用户给的帧 = **GET-Request Normal**，OAD `F0 01 04 00`（SA=单地址+`11×6`、CA=`0x10`、PIID=0）。
  用现有组帧器逐字节复现成功（含 HCS/FCS）：
  `68 17 00 43 05 11 11 11 11 11 11 10 6A 36 05 01 00 F0 01 04 00 00 B0 8B 16`。
- **位序**：A-XDR bit-string 按 ASN.1/BER 口径——bit0 = 首字节最高位。本仓同一标准下的
  「文件属性 bit-string(SIZE(3))，bit0 读 / bit1 写 / bit2 执行」在实帧里是 `04 03 E0`
  （`build_file_info` 默认 `attr_byte=0xE0`）⇒ 自证「bit0=MSB」。为兼容个别反向编码设备，
  判定时同时尝试低位在前解释，命中则**接受并警告**（避免把能升级的固件误判为失败）。

## Requirements

### R1 纯逻辑（`dl_t698_45_upgrade.py`）

- R1.1 `OAD_BLOCK_STATUS = F0010400`；`build_read_block_status(sa, ca, piid)`（GET Normal，
  末尾 TimeTag `00`；复用 `build_read_version(..., oad=...)`，不新增第二套组帧）。
- R1.2 `parse_block_status(node) -> dict`：把 Get-Response 的 `数据`（bit-string 节点）解成
  `{valid, bits, raw(hex), bytes[:], set_bits, missing(order)}`；非 bit-string/空 → `valid=False`。
- R1.3 `check_block_status(frame, expect_blocks) -> dict`：
  - 复用 `check_get_response(frame, OAD_BLOCK_STATUS)`（解析器判定 + OAD 回显 + DAR 分流）；
  - `matched`：OAD 回显正确（是本次状态字响应）——用于页面区分「杂帧忽略」与「未通过重试」；
  - 完整性：`bits >= 块数`、`0..块数-1` 位全为 1、`块数..bits-1` 位全为 0（允许设备按字节补齐）；
    两种位序（MSB/LSB）任一满足即 `ok=True`，`order` 标明；都不满足给 `missing`（缺哪几块）；
  - `bits < 块数`、位数与本地块数不符、错误 DAR、非 bit-string 一律 `ok=False` + 可读原因。
- R1.4 `check_get_response` 返回值追加 `apdu` / `data_node`（向后兼容，不影响既有调用）。

### R2 页面（`dlt698_upgrade_widget.py`）

- R2.1 新阶段 `PHASE_STATUS = "status"`：末包确认后**不再直接执行**，而是先读状态字；
  `_step_label` = 「读取传输块状态字」。
- R2.2 `_on_frame` 对 `PHASE_STATUS` 走 `check_block_status`：
  - `ok` → 日志给出 `状态字 0x..（N 位，全部成功）`（LSB 命中再补一条警告），`_on_ack()`；
  - DAR≠0 / `matched` 但未通过 → `_retry_or_fail(原因)`（沿用既有重试次数与超时）；
  - 非本步帧（OAD 不符/非 GET）→ 忽略并 warn（不计确认）。
- R2.3 `_on_ack(PHASE_STATUS)`：通过后——勾「自动执行」→ `PHASE_EXEC`；未勾 →
  `_begin_reset_wait("文件传输完成且状态字校验通过（未发送执行升级命令）", …)`（保持既有语义）。
- R2.4 用尽重试 → 状态 `failed`、弹框/日志明确「状态位图未通过，**未发送执行升级命令**」，
  绝不静默放行；「中止/清除」等既有收尾不变。
- R2.5 状态位图信息进日志（原始 hex + 位数 + 位序），便于现场核对。

### R3 测试

- R3.1 `test/test_dl698_upgrade.py`（core）：
  - 用户现场帧**逐字节**复现（同上）；
  - `parse_block_status`：3 位 `E0`（MSB 全 1）/ `07`（LSB 全 1）/ 位数不足 / 非 bit-string；
  - `check_block_status`：完整（MSB）、完整（LSB，order=lsb）、缺块（missing 列表）、
    `bits < 块数`、`bits > 块数` 且补位为 0（接受）、补位为 1（拒绝）、DAR 错误、
    OAD 不符（matched=False）、坏帧不抛异常。
- R3.2 `test/test_dl698_upgrade_gui.py`（offscreen）：
  - helper `status_ack_for(tx, blocks)`，`run_to_end` 识别 `PHASE_STATUS` 并回完整位图
    （既有流程用例继续通过）；
  - 新增用例：① 末包后下一帧是 **F00104 GET**（APDU 断言），完整位图后才发执行升级；
    ② 位图缺块 → 重试同一 GET（不超过配置次数）→ 用尽后 `failed`，**全程没有执行升级帧**；
    ③ 未勾自动执行：仍读状态字，通过后直接收尾（不发执行）；
    ④ DAR 错误 → 重试后失败且不发执行；
    ⑤ 非本步帧（别的 OAD GET）在状态阶段被忽略。
- R3.3 既有 `run_to_end` 相关用例全部保持通过（状态阶段对旧断言透明）。

### R4 文档

- AGENTS §5.6（光伏升级页步骤补「传输块状态字校验」）与 §8 陷阱（位序/两种解释）；
- spec frontend §7j 增补；
- CHANGELOG（版本批次留工作区）。

## Acceptance Criteria

- A1 传输完所有块后，日志出现 `[TX] … 05 01 … F0 01 04 00 00 …（读取传输块状态字）`，
  帧与用户给的现场帧**同构**（SA/CA/PIID 由页面参数决定）。
- A2 回复位图显示全部块成功 → 日志给位数/位序，随后才发执行升级（勾自动执行时）。
- A3 位图缺块/取不到 → 重试；用尽后状态「失败」，**没有发出任何执行升级帧**，弹框说明原因。
- A4 未勾「自动执行」时仍会读状态字并在通过后正常收尾。
- A5 `release_check.py --with-gui` → FAIL=0（既有环境红除外）。

## 非目标

- 不改文件传输（方法7/8/13）的组帧与判定；
- 不改状态字以外的其它 F001 属性（文件信息/下载方标识/块大小/执行时间）；
- 不做「自动重传缺失块」（只报缺块并停止，重传由用户决定）；
- 不改 Web 版。
