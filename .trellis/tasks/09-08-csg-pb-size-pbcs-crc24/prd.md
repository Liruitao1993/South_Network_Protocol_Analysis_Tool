# 协议9多物理块帧PB大小推断与PBCS CRC-24校验修复

## Goal

协议9（新一代载波/通感一体化 SPLC）单帧解析在处理多物理块 MPDU 帧时存在两个缺陷：
物理块大小推导错误导致 PB 切片整体错位；物理块检查序列（PBCS）只回显原始字节、
从不计算 CRC-24。本任务修复这两点，使多 PB 帧的切片与逐 PB 传输校验结论可信。

## Background（实测证据）

真实抓包帧（4 个物理块，样本存于 `_tmp_test/probe_frame.hex`，2096 字节）：

- FC：byte0=0x09（SOF+接入指示），byte7=0x14（物理块个数=4、CMT=1），byte12=0x10（BPLC 版本），
  FCS CRC-24 校验通过（0x95F2D8）。
- 帧总长 2096 = 16 + 4×520；偏移 16/536/1056/1576 处 PBH 序列号恰为 0/1/2/3。
  即真实 PB 大小为 520 字节。
- 现行 `_get_pb_size()` 的 BPLC 分支（CMT 0x0-0x7、0xE → 136）给出 136，
  导致 `物理块头[1..3]` 序列号显示为 11896/108/20992（PB 体中间的随机载荷），
  `物理块检查序列[0..3]` 显示的是各 PB 体偏移 133 处的载荷字节而非 PBCS 字段。
- 协议依据：第4部分表20 的 CMT 指向物理层 ROBO 表；本规约物理层表13（SPLC 载荷数据 ROBO 模式）
  中 TMI=1 → PB 520（BPSK 1/2、copy=4、PB 块数 1~4），与抓包一致。
- 按 520 切片后，每个 PB 末尾 3 字节 PBCS 均为 00 00 00，而 CRC-24(PBH+PB体+保留)
  计算值为 0xE8976A / 0xC178D2 / 0x8C0F7E / 0x1512FB：该采集接口未提供 PBCS（置零），
  校验结论必须能区分"置零未携带"与"真正校验失败"。

## Requirements

- R1 多 PB 帧切片正确：MPDU/pb_only 输入下，PB 大小优先取 FC 显式值（HRF/Bitloading 的
  `_pb_size`），其次用"帧长一致性"在候选集 {520, 264, 136, 72, 40, 16} 中唯一确定
  （`PB起始偏移 + 物理块个数 × PB大小 == 帧总长`）；CMT 映射值满足该等式时保持现状不变。
- R2 CMT 映射与帧长不一致时，表格中必须给出一行显式提示（CMT 映射值 / 推断值 / 推断依据），
  不允许静默改判。
- R3 无法由帧长唯一确定时（截断日志、SOF 带尾字节等）回退到 CMT 映射值，行为与现状一致。
- R4 逐 PB 计算 CRC-24（poly=0x1800063、init=0、rev=True、xorOut=0），
  计算范围 = 物理块头 + 物理块体 + 保留字节（即该 PB 的前 `PB大小-3` 字节），
  与存储的 3 字节 PBCS（小端）比对，解析值列显示 `0x......` 而非"3字节"。
- R5 PBCS 三态结论：计算值==存储值 → "校验通过"；存储值==0 且计算值!=0 →
  "PBCS 置零/采集接口未提供"告警文案（不算校验失败）；其余 → "校验失败(计算值=0x......)"。
- R6 PBCS 字段不足 3 字节（帧截断）时显示"PBCS 缺失(帧截断)"，不做计算、不抛异常。
- R7 每个 PB 的保留字节（PBCS 前 1 字节）单独成行展示，便于核对 CRC 计算范围。
- R8 修复对批量解析、监控器解帧等复用 `parse_to_table` 的路径同时生效，不新增入口参数。

## Acceptance Criteria

- [ ] 用 `_tmp_test/probe_frame.hex` 解析（parse_level=fc_pb）：`物理块头[0..3]` 序列号为 0/1/2/3；
      出现 PB 大小推断提示行（CMT 映射 136 → 推断 520）；4 行 `物理块检查序列[i]` 均为
      "置零/采集接口未提供"告警且解析值为 0x000000。
- [ ] 构造 4×136 PB 且 PBCS 填正确 CRC-24 的合成帧：切片仍为 136（无推断提示行），
      4 行 PBCS 均显示"校验通过"。
- [ ] 构造 PBCS 填错误非零值的合成帧：对应行显示"校验失败(计算值=...)"。
- [ ] 截断帧（去掉最后一个 PB 的尾部 4 字节）：不抛异常，末 PB 显示"PBCS 缺失(帧截断)"。
- [ ] 新增回归测试 `test/test_csg_pb_size_pbcs.py` 覆盖上述四条，全部通过。
- [ ] 既有测试 `test/test_csg_new_gen.py`、`test/test_csg_hrf_mac.py`、
      `test/test_csg_batch_parse_level.py`、`test/test_csg_batch_prefix.py`、
      `test/test_csg_summary.py`、`test/test_csg_test_device_control.py` 全部通过（无回归）。

## Non-Goals

- 不重写字 `_get_pb_size()` 的 BPLC CMT 映射表（表13 语义的 4bit 子集重映射属协议口径再解释，
  留作后续独立任务）；本任务只用帧长一致性做覆盖判据。
- 不补 eFC UL-trigger / UL-SACK 的 CRC-24 行、信标帧 BPCS(CRC-32) 校验行（另立任务）。
- 不改 `_detect_channel()` 的通道判别逻辑（本帧通道判定结果已正确）。
- 不支持"1×136 + 1×520"混合 PB 大小（协议缺省形态）；混合形态下帧长等式无唯一解，回退 CMT 值。

## Notes

- 样本与探针脚本：`_tmp_test/probe_frame.hex`、`_tmp_test/probe_pb_crc24.py`、
  `_tmp_test/probe_pb_crc24_b.py`（分析证据，回归测试自嵌 hex，不依赖 _tmp_test）。
