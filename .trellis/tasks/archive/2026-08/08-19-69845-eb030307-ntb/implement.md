# Implement: 协议8 EB030307 过零NTB值上行数据解析

## 阶段

### ① ACTION-Response 数据个数兼容（dl_t698_45_apdu_parser.py）
1. 新增 `_parse_axdr_items_or_single(data, offset)`：兼容「数据个数N + N×A-XDR」与「直接单 A-XDR」
2. `_parse_action_response` choice=0x02 每项 DAR 后改用该辅助，响应数据列表存「响应数据」（单项时直接挂值）

### ② EB030307 schema（gdw_eb_di_fields.py）
3. 新增 EB030307 字段定义（bcd_time/enum/uint8/list<uint32×3>）
4. bcd_time 解码改进为可读日期时间（YYYY-MM-DD hh:mm:ss）

### ③ 测试（test/test_dl_t698_45_fujian.py 追加）
5. 用户真实帧：解析成功 + 数据业务含 数据开始时间/边沿/周期/点数/相线 NTB 数组
6. 文档示例回归：`87 02 00 01 EB 03 01 10 00 09 03 01 00 05 00 00`（无数据个数路径）
7. bcd_time 可读格式断言

### ④ 验证 + 回归
8. test_dl_t698_45.py / test_dl_t698_45_data_decode.py / test_gdw_fujian.py / test_web_frame_gen_utils.py
9. Web 浏览器实测用户帧

### ⑤ 收尾
10. CHANGELOG 1.14.3 + AGENTS.md + README
11. 提交 + 归档
