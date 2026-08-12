# 实施计划：协议9 通道自动识别

## 前置

- [x] 文档核对：表20（BPLC）/ 表23（ISAC 数据帧）/ 表45（HRF）SOF 可变区域布局、表44（HRF PB大小）、表6（版本2 仅无线）
- [x] 判别算法实测：用户 PLC 帧（152B）→ BPLC 命中；合成 HRF 帧（152B）→ HRF 命中

## 执行清单

1. **`csg_new_gen_parser.py`**
   - [ ] 新增 `_detect_channel(frame_bytes, frame_len)`（见 design.md，只读无副作用）
   - [ ] `parse_to_table` 签名 `channel="auto"`；入口 `if channel == "auto" and (frame_bytes[0]>>3)&1 == 1: self._channel = self._detect_channel(...)`；记录 `self._detected_channel`
   - [ ] `_parse_mpdu_frame` FC 解析末尾追加「通道判定」行（`self._detected_channel` → 载波/无线）
2. **`main_gui.py`**
   - [ ] `csg_channel_combo` 首位加「自动识别」(data="auto")，默认 index 0
   - [ ] `_load_app_config` / `__init__` 缺省 `"auto"`（L6843 与 L599 `getattr(self, '_csg_channel', 'plc')` → `'auto'`）
3. **测试**（`test_csg_hrf_mac.py` 追加）
   - [ ] T5：用户 PLC 帧 `channel="auto"` → 通道判定=plc，源TEI/目的TEI 与显式 plc 一致
   - [ ] T6：合成 HRF MPDU `channel="auto"` → 通道判定=hrf，源TEI/MCS 与显式 hrf 一致
   - [ ] T7：PB大小=40 的 HRF 帧 → 判定 hrf（强信号）
   - [ ] T8：显式 plc/hrf 行为不变断言
4. **文档**：AGENTS.md §10 变更日志 + §8 陷阱（可选）

## 验证命令

```bash
cd E:/python/南网解析工具
python test_csg_hrf_mac.py        # 4既有 + 4新增
python test_csg_new_gen.py        # 回归
python -c "import ast; ast.parse(open('csg_new_gen_parser.py',encoding='utf-8').read())"
```

## 审查门

- 实现 → 全量验证 → AGENTS.md → commit（Phase 3.4）
- 回滚：先 `git stash`（main_gui.py 有其它未提交改动）