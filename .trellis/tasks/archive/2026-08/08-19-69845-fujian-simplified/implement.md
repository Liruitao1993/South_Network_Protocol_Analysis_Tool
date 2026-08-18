# Implement: 协议8 福建简化698（choice=0x02 List 结构）解析扩展

## 阶段

### ① EB OI/数据内容解码辅助（dl_t698_45_apdu_parser.py）
1. 新增 `_enrich_eb_oad(oad_dict)`：OAD/OMD 4 字节 hex 查 `gdw_eb_di_lookup.get`，说明追加 EB 名称
2. 新增 `_decode_eb_data_content(di_hex, data_dict)`：按 `gdw_eb_di_fields.EB_DI_FIELDS` 字段 schema 解码 octet-string 数据字节
3. `_parse_oad_raw`/`_parse_omd_raw` 结果经 `_enrich_oad`/`_enrich_omd` 后调用 `_enrich_eb_oad`

### ② List 分支（dl_t698_45_apdu_parser.py）
4. `_parse_set_request`: choice==0x02 → PIID + count + [OAD + Data]×count
5. `_parse_set_response`: choice==0x02 → PIID-ACD + count + [OAD + 结果]×count
6. `_parse_action_request`: choice==0x02 → PIID + count + [OMD + Data]×count
7. `_parse_action_response`: choice==0x02 → PIID-ACD + count + [OMD + DAR + [响应数据]]×count
8. `_parse_report_notification`: choice==0x01 带 count → PIID-ACD + count + [OAD + Data]×count
9. `_parse_report_response`: choice==0x01 带 count → PIID-ACD + count + [OAD + 结果]×count

### ③ 测试（test/test_dl_t698_45_fujian.py 新增）
10. 文档示例帧：SET 配置 / SET 确认 / SET 否认 / ACTION 读取 / ACTION 响应 / REPORT 上报 / REPORT 确认
11. 用户实测帧：`07 02 00 01 EB 03 03 07 09 08 1C 07 E8 0B 1B 0A 20 00 00`（ACTION-Request List，OMD=EB030307）
12. 断言：choice/子类型、PIID、count、OAD/OMD 中文名、Data A-XDR 类型、数据业务字段

### ④ 验证 + 回归
13. `python test/test_dl_t698_45.py`（含现有 REPORT 用例）
14. `python test/test_dl_t698_45_data_decode.py`
15. `python test/test_web_frame_gen_utils.py`（62 项，Web 生成器字节断言）
16. GUI 冒烟：main_gui 导入 + Web 浏览器实测用户帧

### ⑤ 收尾
17. CHANGELOG 1.14.2 + AGENTS.md §10/§11 + README
18. 提交 + 归档 Trellis 任务
