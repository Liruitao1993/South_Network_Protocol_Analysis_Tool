# 光伏升级：发送通道（串口/蓝牙）+ 按 ATT 上限自动算每包最大字节数

## Goal

用户需求（原文）：

> 「光伏升级，有一个发送通道的选项，默认是串口通道进行收发，还有一个通道是蓝牙通道，当选择蓝牙通道的时候，
> 则复用蓝牙工具页面中建立的蓝牙连接，同时还应该将包的最大传输限制ATT的限制截取过来作为蓝牙通道中文件传输
> 包数据内容包大小的限制，这个是需要计算的，如果ATT限制是512字节，则升级包大小应该不能超过480字节，
> 因为698协议有报文头和校验等字节占着字节数，当我勾选了蓝牙通道时，每包的数据大小会自动的帮我计算好最大的输入限制。」

三件事：① 新增**发送通道**（串口默认 / 蓝牙）；② 蓝牙**复用「蓝牙工具」页的连接**；③ 蓝牙下按 ATT 上限
**自动算出每包数据上限**并收敛输入框。

## Requirements

1. **发送通道下拉**（参数区第一行，`combo_channel`：`serial`/`bluetooth`）：落盘（`channel`），传输中与其它计划输入一起冻结。
   串口口径不变（走顶部「串口配置」的连接，本页只借用）。
2. **蓝牙复用蓝牙工具页的连接**：升级页**不建、不断**连接 —— 经 `main_gui._upgrade_bluetooth_source()`
   注入的**取值回调**拿 worker（蓝牙 worker 是蓝牙页惰性创建的，注入时可能还不存在；换 worker 要**先断旧信号**）。
   发送走 `_BleSendPort`（`is_open`/`write_raw` 与串口同构）→ `worker.send_data(frame, single_write=True)`。
3. **接收**：订阅 `notification_received` → 本页 `_on_raw_data`（698 分帧归本页，**不依赖**蓝牙页的静默切帧）；
   且只在传输中吃通知（空闲时不吃设备主动上报，免得刷日志）。
4. **每包上限自动算**（核心）：
   - 一次 ATT 写能承载的字节数 = `worker.single_write_limit()`（= 目标特征码免响应写上限，或 `MTU − 3`；
     **不叠**蓝牙页那个 200 字节 `_max_chunk` —— 单一实现 `_limit_plan`，蓝牙页 `_chunk_plan` 也用它）；
   - 用**真实组帧**反推块长：`dl_t698_45_upgrade.max_block_bytes_for_frame_limit(limit, sa, ca)`
     （二分，开销随地址域/BER 长度域自动算准 —— **不写死「减 32」**）；
   - `spin_block.setMaximum(cap)` + 当前值超了就夹到 cap + 通道标签写明「MTU / 一次写上限 / 每包最大」；
   - 重算时机：通道切换 / 连接变化 / `mtu_updated` / SA 配置变化；上限缓存进 `_bt_cap`，
     蓝牙通道下 `_worker()` **要求缓存非 None**（算不出上限就不放行，免得块长超限半途失败）。
5. **算不出上限时不设假上限**：未连接 / `mtu_is_unnegotiated`（仍是 ATT 默认 23）/ 一次写放不下 698 帧头
   ⇒ `spin_block` 上限回到 `BLOCK_SIZE_MAX`，**禁用「开始升级」**并把原因写进标签（点击也给日志）。
6. **一整帧一次 ATT 写**：`send_data(single_write=True)` 超上限**拒发 + 报错**（绝不静默分包），
   且超限时**一个字节都不写**。

## Acceptance Criteria

- [ ] `max_block_bytes_for_frame_limit`：509 ⇒ 475、512 ⇒ 478（≤480，用户口径成立）；每档都满足
      「整帧 ≤ 上限」且「再大 1 字节就超」；广播 SA(1B) 比通配多 6 字节；上限 ≤32 ⇒ 0；非法输入 ⇒ 0
- [ ] `single_write_limit()`（MTU 512 / 无特征码信息）== 509，**不受** `_max_chunk=200` 影响；
      蓝牙页的 `_chunk_plan` 仍按 200 分包（两种语义并存）
- [ ] `send_data(超限, single_write=True)` 返回 False、给出可读错误、`client.writes == []`
- [ ] GUI：默认串口（上限 8192）；蓝牙未连接/MTU 23 ⇒ 不设假上限 + 开始禁用 + 标签写明原因；
      连上 MTU 512 ⇒ 上限 475、值 600 被夹、标签含「MTU 512 / 509 / 475」、开始可用
- [ ] GUI：蓝牙通道整轮跑通（TX 全走 `single_write=True`、RX 走通知信号、`done`/100%、`rejected == 0`）
- [ ] GUI：掉线 ⇒ 开始禁用；重连 ⇒ 恢复且上限重算；MTU 变小 ⇒ 上限下调且仍紧致
- [ ] GUI：通道选择落盘读回；切回串口 ⇒ 上限 8192 且后续发送走串口 worker（蓝牙不再收帧）
- [ ] wiring：真 MainWindow 注入了取值回调，且回调取到的就是蓝牙工具页的 worker（同源、不自建）
- [ ] 回归：`test_dl698_upgrade_gui.py` / `test_bluetooth_worker.py` / `test_dl698_upgrade.py` /
      `test_dl698_upgrade_tab_wiring.py` 全绿 + `release_check` 无新增 FAIL

## Notes

- 落点：`dl_t698_45_upgrade.py`（纯逻辑反推函数）、`bluetooth_worker.py`（`single_write_limit` + `single_write` 发送）、
  `dlt698_upgrade_widget.py`（通道 + 适配器 + 上限自动收敛）、`main_gui.py`（注入取值回调）。
- 用户给的例子「ATT 512 ⇒ 每包 ≤ 480」：本实现按**真实 698 组帧**算得更准（512 ⇒ 478；若把 512 当 MTU，
  一次写 509 ⇒ 475），**都在 480 以内**。
- 蓝牙页的 200 字节 `_max_chunk` 是它对「连续写」的保护值，与升级页要的「整帧一次写出」是两件事：
  前者不动，后者走 `single_write=True` 绕过它（**不改蓝牙页行为**）。
