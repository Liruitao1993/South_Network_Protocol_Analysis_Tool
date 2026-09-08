# Design — 协议9 PB 大小推断与 PBCS CRC-24 校验

## 边界与改动面

仅改一个解析器文件 + 新增一个测试文件：

- `csg_new_gen_parser.py`：`CSGNewGenParser` 内新增 1 个类常量、1 个私有方法；
  修改 `_parse_pb_block()` 两处（PB 大小决策、PB 循环尾部 PBCS 行）。
- `test/test_csg_pb_size_pbcs.py`：新增回归测试（自嵌 hex，不依赖 `_tmp_test`）。
- `main_gui.py`：CHANGELOG 追加 + APP_VERSION patch 位 +1（发版约定）。

不改 GUI、不改 validator、不改监控器/批量解析调用方（它们都经 `parse_to_table` 自动受益）。

## 数据流

```
parse_to_table(frame, parse_level, ...)
  └─ is_mpdu → _parse_mpdu_frame()      # 读 byte7 → self._pb_count / self._cmt_index
       └─ (可选 eFC，offset 推进到 32)
       └─ _parse_pb_block(frame, offset, table, frame_len)
            ├─ PB 大小决策（本次修改点 1）
            │    self._pb_size 显式(HRF/Bitloading) ? 用它
            │    : cmt_size = _get_pb_size(_cmt_index, _std_version)
            │        → _infer_pb_size(offset, _pb_count, frame_len, cmt_size)
            │            等式: offset + pb_count * size == frame_len
            │            cmt_size 满足 → (cmt_size, False)   # 现状行为
            │            候选 {520,264,136,72,40,16} 唯一满足 → (s, True) + 提示行
            │            无解/多解不可能(候选互异) → 无解时 (cmt_size, False)  # 截断兜底
            └─ for i in range(pb_count):  PBH 行 / 体拼接 / 保留行 / PBCS 行（修改点 2）
```

## 关键决策

### D1 PB 大小：帧长一致性覆盖 CMT 先验，而非重写 CMT 表

- 证据：真实帧 CMT=1 但 PB=520；SPLC 物理层表13 的 TMI=1→520 与抓包一致，
  而代码 BPLC 分支套的是 GDW 老表（0-7→136）。但表13 是 5bit TMI(0-27)，
  BPLC 的 4bit CMT 如何映射到 16-27（136/72/16）需借助 cmt=0xD + 扩展CMT 的组合规则，
  协议文本未给出明确拼接公式 → **属协议口径再解释，不在本任务内猜**。
- 帧长等式 `offset + pb_count*size == frame_len` 是发送端必然满足的硬约束
  （SOF MPDU = FC [+eFC] + ΣPB，无尾字节），候选集互异 ⇒ 至多一个解，判据确定性强。
- 兼容性：凡当前切片正确的帧（cmt_size 满足等式）走原路径，零行为变化；
  截断日志/SOF 带尾字节 ⇒ 等式无解 ⇒ 回退 cmt_size，与现状一致（R3）。
- HRF / ISAC-Bitloading 已由 FC 显式给出 `_pb_size`（L1823/L2722/L2802），不参与推断。
- 混合 PB（1×136+1×520，协议缺省形态）等式无解 ⇒ 回退 cmt_size，行为不劣于现状；
  列为 Non-Goal。

### D2 PBCS 校验范围与字节序

- 范围 = 该 PB 的前 `pb_total-3` 字节（PBH 4 + PB体 + 保留 1），依据第4部分 8.1.3.2.1.3 /
  表49 行"物理块检查序列"：**以物理块头和物理块体以及保留字节三部分为目标**。
- 存储值小端读取（与 FC FCS、eFC FCS 的小端约定一致，见 §4.3 字节序约定）。
- 算法复用现有 `self._crc24()`（crcmod poly=0x1800063, init=0, rev=True, xorOut=0），
  不新增 crc 实例。
- 计算用**帧内真实字节**，不用零填充后的 body：截断 PB 走 R6 分支，不参与计算。

### D3 PBCS 三态结论（R5）

| 条件 | 解析值列 | 说明列 |
|---|---|---|
| calc == stored | `0x......，校验通过` | CRC-24(范围N字节)，校验通过 |
| stored == 0 且 calc != 0 | `0x000000(置零)` | 计算值=0x......，PBCS 置零/采集接口未提供，非校验失败 |
| 其余 | `0x......` | CRC-24(范围N字节)，校验失败(计算值=0x......) |
| 尾部不足 4 字节 | `PBCS缺失(帧截断)` | 保留1+PBCS3 不足，无法校验 |

置零单列一态的原因：监控/发射机接口抓包普遍不提供 PBCS（本帧四 PB 全零），
若并入"校验失败"会满屏误报；参考先例 `hdc10_parser.py` L890-914 的"无PBCS"降级分支。
注意 stored==0 且 calc==0（全零填充 PB）仍判"校验通过"，不误报。

### D4 表格行契约

- 新增行均为 6 元组 `(字段, 原始值, 解析值, 说明, start, end)`，与现有行同构；
  推断提示行偏移给 `(None, None)`（不可高亮），与"通道判别"行风格一致。
- 新增"保留(PB尾)"行（PBCS 前 1 字节）使 CRC 范围可在 UI 中逐字节核对（R7）；
  命名带 `(PB尾)` 后缀，避免与 PBH 的 15bit"保留"行重名。
- `物理块检查序列[i]` 解析值列由固定字符串"3字节"改为 `0x......` 结论（R4），
  GUI 表格/导出/批量 CSV 均直接读该列，无需适配。

## 兼容性与风险

- `test_csg_hrf_mac.py` 的合成帧：HRF 路径 `_pb_size` 显式 ⇒ 不进入推断；136/40 字节 PB
  合成帧帧长自洽 ⇒ 等式命中 cmt_size ⇒ 行为不变。
- 批量解析性能：每 PB 增加一次 ≤520 字节 CRC-24（crcmod C 实现），可忽略。
- 监控器 ED..EE 解帧、96..16 解帧后复用 `parse_to_table` ⇒ 同步修复，无额外改动。
- 风险点：若某真实帧 SOF 后带尾字节且 PB 为 136，等式无解回退 cmt_size=136 ⇒ 与现状相同，不引入新错误。

## 回滚

单文件逻辑改动：`git checkout -- csg_new_gen_parser.py` 即完全回滚；
测试文件与 CHANGELOG 为新增/追加，可独立删除。无数据文件、无配置迁移。
