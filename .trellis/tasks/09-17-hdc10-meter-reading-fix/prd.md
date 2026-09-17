# 修复 HDC 1.0 抄表报文解析 NameError（proto_ver 未定义）

## Goal

协议11（HDC 1.0）在「应用层报文(app)」解析级别下解析抄表类报文（报文ID 0x001/0x002/0x003）时，
`hdc10_parser._parse_meter_reading` 引用**从未赋值的局部名** `proto_ver`，抛 `NameError`，
GUI 弹「解析失败：name 'proto_ver' is not defined」——该帧完全无法解析。

## 现象与复现（实测）

- 现场帧（用户提供，88 字节，终端主动并发抄表 `0x0003`）：

  ```text
  11 03 00 00 01 02 B3 04 87 44 19 0A 68 49 00 43 05 02 66 00 05 00 20 02 69 4A 10 00 25 05 03 02 50
  04 02 00 01 20 21 02 00 1C 07 EA 09 10 00 00 00 03 00 20 21 02 00 00 00 10 02 00 00 00 20 02 00 00 00
  01 10 DA F7 12 94 1E 1C 22 38 49 D8 94 65 87 90 87 6A 34 40 16
  ```

- 复现：`HDC10Parser().parse_to_table(frame, parse_level="app")`
  → `NameError: name 'proto_ver' is not defined`
- 同一帧 `parse_level="auto"` **不报错**（走 MAC 帧路径，不经过该函数）→ 缺陷长期潜伏

## 根因

`hdc10_parser.py:2130-2132`（`_parse_meter_reading`，服务 0x001/0x002/0x003）三处引用 `proto_ver`：

```python
    table.append((
        "    协议版本号",
        f"0x{proto_ver:02X}",      # ← 从未赋值
        str(proto_ver),
        f"协议版本: {proto_ver}",
        offset, offset,
    ))
```

该函数内只赋值了 `b0`/`b1`/`b2`/`b3`/`hdr_len`/`hdr_bytes`/`cfg`/`proto_type`/`data_len`/`seq`。
同文件另外 6 个 `_parse_*`（`_parse_confirm:2222`、`_parse_timesync:2253`、`_parse_event`、
`_parse_comm_test`、`_parse_registration`、`_parse_upgrade`）都写有 `proto_ver = b0 & 0x3F`，
**唯独本函数漏写**。

静态扫描：`ruff check --select F821` 全仓仅此一处（3 个引用指向同一变量）。

## 触发条件（四条同时满足，故长期未被发现）

1. 协议索引 **11**（HDC 1.0 双模互联互通）
2. 解析级别 = **应用层报文（`app`）**——默认「自动识别」不触发
3. 报文ID ∈ **{0x001 终端主动抄表, 0x002 路由主动抄表, 0x003 终端主动并发抄表}**
4. 报文端口号 = **0x11**

## 协议依据（HDC 1.0 第 4-3 部分 §5.3.1.2 / 表3）

- 表3「下行抄表报文」：字节0 bit0-5 = **协议版本号**（即该函数的 `b0`）
- §5.3.1.2 原文：「协议版本号是 6 比特的字段，指从 CCO 发送给 STA 的应用层数据的协议版本。
  考虑兼容性，**本版本取值固定为 1**」
- 用户帧实测 `b0 = 0x01` ✓ 与文档一致

## Requirements

1. 补 `proto_ver = b0 & 0x3F`（与同文件 6 处同款写法）——**一行修复，不改其他逻辑**。
2. 该函数其余字段公式**保持不变**（实测与文档、帧长自洽，见验收项）。
3. 新增回归测试套件，钉住：
   - 用户现场帧的完整 golden 输出
   - 0x001 / 0x002 / 0x003 三类抄表报文均可解析（不再 NameError）
   - `app` 与 `auto` 双级别（auto 行为不得改变）
4. 测试文件放 `test/`，含 `import _path_setup  # noqa: E402,F401`，登记 `release_check.py:CORE_TESTS`。

## Acceptance Criteria

- [ ] 用户现场帧在 app 级别解析出且**不再有任何 NameError**：
      端口 `0x11` / 报文ID `0x0003`「终端主动并发抄表」/ 协议版本号 `1` / 报文头长度 `2×4B=8B` /
      配置字 `0`（未应答重试0 否认重试0 最大重试0）/ 转发数据规约类型 `3`=DL/T698.45 /
      转发数据长度 `75字节` / 报文序号 `17543` / 数据(DATA) 起始 `68 49 00 43 …`
- [ ] 转发数据长度 `75` 与实际字节数吻合（DATA 起于偏移 12、长 75，帧长 88 时帧尾偏移 87 = `0x16`）
- [ ] 0x001 / 0x002 / 0x003 三类报文均解析成功
- [ ] `parse_level="auto"` 对该帧输出与修复前逐行一致（回归零变化）
- [ ] `ruff check --select F821` 全仓 0 命中
- [ ] `python release_check.py` FAIL=0 / WARN=0
- [ ] **变异反证**：把 `proto_ver` 赋值删掉 → 新测试变红（证明测试真的覆盖该缺陷）

## Out of Scope（本次不做，用户已确认「最小修复」）

- DATA 域内嵌 698.45 / DL/T645 报文的深度解析（当前仅显示前 16 字节 hex）
- 文档 §5.3.1.9 表8 的「报文间间隔」（并发抄表 bit7~0，单位 10ms）与上行「报文应答状态」（16bit）
- app 级别下其他报文 ID 分支的动态排查（已用 F821 静态扫全仓，动态排查属另案）
- Web 端无额外工作：`reflex_web` 复用同一 `hdc10_parser.py`，自动获得修复

## Notes

- 复现命令、字段逐项核对与执行结论记录在 `implement.md`「执行结果」。
- 本次改动文件仅 `hdc10_parser.py`（+ 测试 + release_check 清单 + 文档），
  **不触碰** `main_gui.py` / `reflex_web/reflex_web/web_utils.py`。
