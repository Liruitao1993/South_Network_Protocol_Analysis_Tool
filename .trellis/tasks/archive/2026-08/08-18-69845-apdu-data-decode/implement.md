# Implement：协议8（698.45）APDU 数据内容深度解析

## 阶段 1：数据格式映射（dl_t698_45_data_decode.py 新建）

### 1.1 类属性模板
- [ ] `CLASS_ATTR_TEMPLATES`：按 (class_id, attr_id) 定义数据格式模板
  - 电能量类(1): (1,2) energy_array, (1,4) extended, (1,30) energy_array_q
  - 最大需量类(2): (2,2) demand_array
  - 分相变量类(3): (3,2) phase_array, (3,31) phase_array_q
  - 功率类(4): (4,2) phase_array
  - 数据变量类(7): (7,2) data_value
  - 谐波变量类(5): (5,2) phase_array（谐波含量）

### 1.2 OI 单位提示
- [ ] `OI_UNIT_HINT`：常用 OI → (单位, 默认scaler)
  - 0x0000~0x004F 电能量 OI：kWh, -3
  - 0x0100~0x01FF 需量 OI：W/kW, scaler 依对象
  - 0x2000~0x20FF 分相变量（电压/电流/相角）：V/A/°，-1/-3
  - 0x3000~0x30FF 功率：W/kW/VA/var
  - 从 OI_NAME_MAP 名称反推（"电压"→V，"电流"→A，"功率"→W）

### 1.3 解码器
- [ ] `decode_oad_data(oi, attr_id, data_dict)` → 业务解读（dict/str）或 None
- [ ] `_decode_energy_array`：array 元素换算 → `1234.56 kWh`
- [ ] `_decode_demand_array`：structure {需量值, date_time_s} → `值 @ 时间`
- [ ] `_decode_phase_array`：array 逐相 → `A:220.5V B:220.3V C:220.1V`
- [ ] `_decode_data_value`：单数值 + scaler
- [ ] `_apply_scaler(value, scaler)`：×10^scaler，格式化小数
- [ ] `_decode_time`：date_time/date_time_s/date/time → 字符串
- [ ] `_decode_quality`：VQDS 品质位 → 说明

## 阶段 2：APDU 解析器接入（dl_t698_45_apdu_parser.py）

- [ ] `_parse_get_response`：GetResponseNormal 的 Data 后调 decode_oad_data，结果存 `数据业务`
- [ ] `_parse_get_response` NormalList：逐 item 解码
- [ ] `_parse_set_request`：Data 业务解码
- [ ] `_parse_action_request` / `_parse_action_response`：参数/响应数据解码
- [ ] `_parse_report_notification`：数据/数据列表解码
- [ ] 解码失败 try/except 回退（不破坏解析）

## 阶段 3：GUI 展示（dl_t698_45_parser.py）

- [ ] `_add_apdu_to_table` 处理 `数据业务` 键：
  - dict → 递归展开（如 {总: 1234.56, 费率1: ...}）
  - str → 单行（如 `1234.56 kWh`）
  - list → 逐项
- [ ] 保留原始 `数据` 行（A-XDR 原始值）

## 阶段 4：测试（test/test_dl_t698_45.py）

- [ ] `test_get_response_energy_decode`：电能量 GET-Response → `1234.56 kWh`
- [ ] `test_get_response_voltage_decode`：分相电压 → `A:220.5V ...`
- [ ] `test_get_response_demand_decode`：需量 → 值 + 发生时间
- [ ] `test_set_request_data_decode`：SET-Request 数据业务解码
- [ ] `test_action_data_decode`：ACTION 参数/响应
- [ ] `test_report_data_decode`：REPORT-Notification
- [ ] `test_unknown_oad_keeps_raw`：无模板 OAD 保持原始
- [ ] 回归：现有用例全过

## 阶段 5：验证

- [ ] `python -m py_compile dl_t698_45_data_decode.py dl_t698_45_apdu_parser.py dl_t698_45_parser.py`
- [ ] `python test/test_dl_t698_45.py` 全过
- [ ] `python test/test_web_frame_gen_utils.py` 回归（698 组帧相关）
- [ ] GUI 冒烟：协议8 单帧解析显示业务值

## 阶段 6：收尾

- [ ] main_gui.py CHANGELOG 条目
- [ ] AGENTS.md §5.6/§10 同步
- [ ] README 同步
- [ ] task.py archive
