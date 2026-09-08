# Implement — 协议9 PB 大小推断与 PBCS CRC-24 校验

执行顺序即检查清单；每步完成后跑对应验证命令。上下文顺序：本文件 → `prd.md` → `design.md`。

## 检查清单

- [x] 1. `csg_new_gen_parser.py`：在 `CSGNewGenParser` 类内（`HRF_PB_SIZE_TABLE` 附近）
      新增类常量 `PB_SIZE_CANDIDATES = (520, 264, 136, 72, 40, 16)` 与静态/实例方法
      `_infer_pb_size(offset, pb_count, frame_len, cmt_size) -> Tuple[int, bool]`
      （实现见 design.md D1；pb_count<1 或 remain<=0 直接返回 (cmt_size, False)）。
- [x] 2. `_parse_pb_block()` L1226-1232 PB 大小决策改为：
      `self._pb_size` 显式 → 沿用；否则 `cmt_size = _get_pb_size(...)` 后调用
      `_infer_pb_size(offset, pb_count, frame_len, cmt_size)`；
      overridden=True 时追加提示行 `("PB大小推断", f"{cmt_size}", f"{pb_total_size}",
      "CMT映射PB={cmt_size}与帧长不符，按 offset+pb_count×size==frame_len 推断", None, None)`。
- [x] 3. `_parse_pb_block()` PB 循环 L1283-1293 替换为：
      a) 保留字节行 `f"  保留{tag}(PB尾)"`（偏移 pbcs_off，仅当 pbcs_off+1<=frame_len）；
      b) PBCS 三态行（design.md D3 表格文案），计算 `self._crc24(frame_bytes[pb_off:pbcs_off+1])`，
         存储值 `int.from_bytes(frame_bytes[pbcs_off+1:pbcs_off+4], 'little')`；
      c) `pbcs_off+4 > frame_len` 时输出 `PBCS缺失(帧截断)` 行，偏移 `(pbcs_off, frame_len-1)`。
- [x] 4. 验证命令 A（见下）：probe_frame.hex 输出核对 —— PBH seq 0/1/2/3、推断提示行、
      4 行 PBCS 置零告警、解析值 0x000000。
- [x] 5. 新增 `test/test_csg_pb_size_pbcs.py`：
      - 自嵌 2096 字节真实帧 hex（来源 `_tmp_test/probe_frame.hex`，复制进测试常量）；
      - `test_real_4pb_520_slice_and_zero_pbcs()`：断言 seq、推断行、置零告警；
      - `test_synthetic_4pb_136_pbcs_pass()`：构造 4×136、PBCS 填正确 CRC-24，
        断言无推断行且 4 行"校验通过"；
      - `test_synthetic_pbcs_mismatch()`：篡改某 PB 的 PBCS 为非零错误值，断言"校验失败(计算值="；
      - `test_truncated_pbcs_missing()`：截掉末 PB 尾 4 字节，断言不抛异常且出现"PBCS缺失(帧截断)"。
- [x] 6. 验证命令 B：新增测试全绿。（4 passed）
- [x] 7. 验证命令 C：6 个既有 csg 测试全绿（无回归）。（69 passed；合并复跑 73 passed）
- [x] 8. `main_gui.py`：CHANGELOG 顶部追加条目（PB 大小帧长一致性推断 + 逐 PB PBCS CRC-24 三态校验），
      APP_VERSION patch +1（1.22.0 → 1.22.1）；不动 BUILD_DATE（非打包）。
- [x] 9. Phase 3：协议9 PB/PBCS 口径已沉淀为项目记忆（development_code_specification +
      common_pitfalls_experience 各一条）；`.trellis/spec` 无解析器层 spec（仅 frontend/guides），
      指南层无需变更；任务归档见收尾步骤。

## 验证命令

```bash
# A. 真实帧输出核对（临时脚本，跑完即删或留 _tmp_test）
python -c "exec(open('_tmp_test/check_real_frame.py', encoding='utf-8').read())"

# B. 新增回归测试
python -m pytest test/test_csg_pb_size_pbcs.py -q

# C. 既有 csg 测试无回归
python -m pytest test/test_csg_new_gen.py test/test_csg_hrf_mac.py test/test_csg_batch_parse_level.py test/test_csg_batch_prefix.py test/test_csg_summary.py test/test_csg_test_device_control.py -q
```

## 审查门

- 步骤 3 完成后必须先跑命令 A 再看 GUI 语义（防止行元组 arity/偏移错误）。
- 步骤 7 全绿前不得进入步骤 8（CHANGELOG 只记录已验证行为）。

## 回滚点

- 步骤 1-3 任一失败：`git checkout -- csg_new_gen_parser.py`（仓库另有 5 处无关脏改，
  回滚仅限本文件路径，禁止整仓 reset）。
- 步骤 5-7 失败：删除 `test/test_csg_pb_size_pbcs.py` 不影响主程序。
