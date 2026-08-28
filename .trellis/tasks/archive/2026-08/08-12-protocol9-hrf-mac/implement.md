# 实施计划：协议9 无线单跳MAC帧解析

## 前置

- [x] 文档核对：表12（单跳MAC头4B）、表13（MSDU类型）、表139/140/142/143（无线发现列表）已逐项核对
- [x] 现状代码核对：`_parse_mac_frame` L2202-2212、`parse_to_table` L434-448、`_parse_pb_block` L872-888、`_parse_msdu_payload` L460-658

## 执行清单

1. **`_parse_mac_frame`**（L2202-2421）
   - [ ] header_size 计算：`version == 2 → 4`
   - [ ] version==2 分支：帧头类型/版本/保留/MSDU类型(表13)/MSDU长度 + 载荷内联分派（1→app / 2→RF发现列表 / 128→IPV4 / 其他→raw）+ CRC-32 收尾
2. **`parse_to_table`**（L434-448）
   - [ ] `is_mac_frame` 帧长下限按 version 放宽（v2 ≥ 8）
   - [ ] `mac_header_size = 4 if version == 2 else ...`；v2 时 `msdu_payload = b""`
3. **`_parse_pb_block`**（L872-888）
   - [ ] v2 → `mac_hdr_len = 4` 且 `msdu_payload = b""`
4. **新增 `_parse_rf_discover_node_list`**（表139/140/142/143）
   - [ ] MAC 6B + 统计序号 1B + TLV 链（类型+长度类型 / 长度 1|2B / 内容）
   - [ ] 类型0 站点属性 14B 展开（表142）
5. **测试**（新文件 `test_csg_hrf_mac.py`，硬编码帧 + assert）
   - [ ] T1 单跳MAC帧直入（v2 + 应用层）
   - [ ] T2 完整无线 MPDU（channel=hrf, fc_pb）
   - [ ] T3 无线发现列表（MSDU类型2 TLV）
   - [ ] T4 回归：`python test_csg_new_gen.py` 全绿
6. **文档**：AGENTS.md §10 变更日志 + §11 摘要（按 §9.8 惯例）

## 验证命令

```bash
cd E:/python/南网解析工具
python test_csg_hrf_mac.py        # 新增用例
python test_csg_new_gen.py        # 回归
python -c "import ast; ast.parse(open('csg_new_gen_parser.py',encoding='utf-8').read())"  # 语法
```

## 审查门

- 实现完成 → 运行全部验证 → 同步 AGENTS.md → commit（Phase 3.4）
- 回滚：`git stash`（HRF 可变区域为未提交工作区内容，勿直接 checkout 丢弃）