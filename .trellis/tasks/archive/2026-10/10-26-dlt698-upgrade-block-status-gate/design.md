# 设计：传输块状态字校验闸门

> PRD 见 `prd.md`。协议事实：F001 属性4 = `bit-string`，bitN=1 表示第 N 块传输成功
> （N 从 0…总块数-1）。组帧/解析一律复用既有实现（`build_read_version`、`check_get_response`、
> `DLT69845Parser`），**不新增第二套 698 组帧或解析**。

## 1. 改动点

| 文件 | 改动 |
|---|---|
| `dl_t698_45_upgrade.py` | `OAD_BLOCK_STATUS` / `build_read_block_status` / `parse_block_status` / `check_block_status`；`check_get_response` 返回值加 `apdu`/`data_node` |
| `dlt698_upgrade_widget.py` | 新阶段 `PHASE_STATUS`；`_send_current_step` / `_on_frame` / `_on_ack` / `_step_label` 接线 |
| `test/test_dl698_upgrade.py` | golden + 位图解析/判定矩阵 |
| `test/test_dl698_upgrade_gui.py` | `status_ack_for` + `run_to_end` 支持新阶段 + 5 个场景 |
| 文档 | AGENTS §5.6/§8、spec §7j、CHANGELOG（版本批次留工作区） |

## 2. 纯逻辑契约

```python
OAD_BLOCK_STATUS = bytes.fromhex("F0010400")

def build_read_block_status(sa, ca, piid) -> bytes:      # 复用 build_read_version(oad=...)
def parse_block_status(node: dict) -> dict:
    """bit-string 节点 → {valid, bits, raw, bytes, set_msb, set_lsb}"""
def check_block_status(frame: bytes, expect_blocks: int) -> dict:
    """返回 {ok, matched, reason, dar, bits, raw, order, missing, expect,
             apdu, data_node}"""
```

- **位序**：A-XDR/BER 口径 MSB-first（bit0 = 首字节 bit7）。同标准「文件属性 bit0..2」实帧 `0xE0`
  自证。判定同时尝试 LSB-first：命中则 `ok=True, order="lsb"`（页面记警告），避免反向设备误杀。
- **完整性判据**（`n = expect_blocks`）：
  1. `bits >= n`（位数不足直接失败）；
  2. `0..n-1` 全 1；
  3. `n..bits-1` 全 0（允许设备按字节补齐，但**不允许**多报块）；
  4. 两种位序任一满足即通过；都不满足 → `missing` 列出缺的块号（取缺得少的那种口径）。
- `matched`：`check_get_response.ok` 或拿到 DAR ⇒ 是本次响应（页面据此「重试」而不是「忽略」）。
- 坏帧/非 GET/异常：`ok=False, matched=False`，永不抛。

## 3. 状态机改动

```
PHASE_BLOCKS 末包确认
   └─► PHASE_STATUS（发 GET F00104，state=finishing）
          ├─ 位图完整 ─┬─ chk_auto_exec ✔ → PHASE_EXEC → …
          │             └─ ✘ → _begin_reset_wait(…未发送执行…)
          └─ 未通过/DAR/超时 → _retry_or_fail（重发同一 GET，PIID 自增）
                 └─ 重试用尽 → state=failed，弹框「状态位图未通过，未发送执行升级命令」
```

- `_expected_omd` 不参与状态阶段（GET 无 OMD）；`_on_frame` 显式分支。
- `_retry_or_fail` 对 STATUS 的文案经 `_step_label()` 自动变为「读取传输块状态字 …
  已停止（原因：…）」，无需特判（但 `_pending_blocks` 为 0）。
- 进度条不变（状态字不增加已确认字节；末包确认时已到 100%）。

## 4. 测试要点

- `status_ack_for(tx, blocks)`：从 tx 取 SA/CA/PIID/OAD，构造 `85 01 PIID F0010400 01 04 <bits> <bytes>`；
  按 MSB-first 置满 `blocks` 位（如 3 → `E0`，9 → `FF 80`）。
- `run_to_end` 增加分支：`tab._phase == PHASE_STATUS` → `status_ack_for(tx, tab._num_blocks())`；
  其余保持（VER → `ver_ack_for`，EXEC 分块交付）。
- 新增场景用 2 包小文件，`spin_retries` 控制重试次数；断言「没有任何执行升级帧」时扫
  `w.sent` 的 APDU OMD（`07 01 … F0 01 0D 00`）而不是只数条数。

## 5. 风险

- 位序若在目标设备上是反的：LSB 兼容分支接受并记警告（现场可据此反馈）。
- 设备把状态字声明位数为「字节×8」：允许补 0（判据 3），不会误杀。
- 设备状态字含额外块：判失败（多报块意味块数不匹配，执行升级不安全）。
