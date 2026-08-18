# PRD: 协议8 福建简化698（choice=0x02 List 结构）解析扩展

## 问题

用户反馈：协议8（DL/T 698.45）解析福建新增的 698.45 协议定义（`协议文档/8.698.45协议/【CCO和STA要求】本地通信模块扩展协议V3.42-20260514.md`）时，只解析出 APDU 类型/子类型码，**没有解析 PIID/OAD/OMD/数据内容**。

实测帧（ACTION-Request）：
```
07 02 00 01 EB 03 03 07 09 08 1C 07 E8 0B 1B 0A 20 00 00
```
当前解析结果：`{APDU类型: ACTION-Request, 子类型码: 0x02}`，其余全丢。

## 根因

福建「本地通信模块扩展协议」V3.3 起要求 698 承载采用「简化698」格式（A.2 说明 + A.2.2 示例），其 GET/SET/ACTION/REPORT 服务**使用 choice=0x02 的 List 结构**（标准 `ActionRequestNormalList` / `SetRequestNormalList`，SEQUENCE OF {OMD/OAD, Data}，带 count 前缀），而 `dl_t698_45_apdu_parser.py`：

- `_parse_set_request` 仅实现 choice=0x01（SetRequestNormal），缺 0x02 List
- `_parse_set_response` 仅实现 choice=0x01，缺 0x02 List
- `_parse_action_request` 仅实现 choice=0x01，缺 0x02 List
- `_parse_action_response` 仅实现 choice=0x01，缺 0x02 List
- `_parse_report_notification` / `_parse_report_response` 的 choice=0x01 分支**无 count 前缀支持**（文档示例 `88 01 00 01 EB 03 00 02 ...` 在 PIID-ACD 后有 count=01），解析错位

对照文档示例：
|服务|福建 698 示例|结构|
|---|---|---|
|SET 配置|`06 02 00 01 EB 03 01 10 09 03 00 00 05 00`|choice=02, PIID=00, count=01, OAD=EB030110, Data|
|ACTION 读取|`07 02 00 01 EB 03 01 10 00 00`|choice=02, PIID=00, count=01, OMD=EB030110, Data|
|ACTION 响应|`87 02 00 01 EB 03 01 10 00 09 03 01 00 05 00 00`|choice=02, PIID-ACD=00, count=01, OMD, DAR=00, 响应数据|
|SET 确认|`86 02 00 01 EB 03 01 10 00 00 00`|choice=02, PIID-ACD=00, count=01, OAD, 结果=00|
|REPORT 上报|`88 01 00 01 EB 03 00 02 01 09 08 ...`|choice=01, PIID-ACD=00, count=01, OAD=EB030002, Data|
|REPORT 确认|`08 01 00 01 EB 03 00 02 00`|choice=01, PIID-ACD=00, count=01, OAD, 结果=00|

## 目标

1. 补全 SET/ACTION 的 choice=0x02（NormalList）分支：解析 PIID、count、SEQUENCE OF {OAD/OMD, Data}、DAR/结果
2. REPORT-Notification/Response 的 Normal 分支支持 count 前缀（SEQUENCE OF OAD，count 后逐项）
3. EB OI（0xEB03 等）数据标识识别：OAD/OMD 中的 EB 数据标识给出中文名（复用 `gdw_eb_di_lookup.py` 57 项映射），EB 数据内容按 `gdw_eb_di_fields.py` 字段 schema 解码业务值
4. 全部走 GUI/Web 表格展示（`_add_apdu_to_table` 通用递归，无需改 GUI）
5. 新增测试用例（文档示例帧 + 用户实测帧）

## 非目标

- 不改 GET-Request（0x02 List 已有）
- 不做 PROXY/SECURITY 等服务的 List 扩展（福建文档未涉及）
- 不改组帧生成器（`frame_gen_utils.py` 已能生成 choice=0x02 帧）
- 不重建部署包（如需要另行处理）

## 验收标准

1. 用户帧 `07 02 00 01 EB 03 03 07 09 08 1C 07 E8 0B 1B 0A 20 00 00` 解析出：PIID=0、count=1、OMD=EB030307（过零NTB值数据更新周期）、Data（octet-string）+ 数据业务
2. 文档示例 SET/ACTION/REPORT 各帧解析出 OAD/OMD 中文名 + 数据内容
3. `test/test_dl_t698_45.py` 与 `test/test_dl_t698_45_data_decode.py` 回归通过
