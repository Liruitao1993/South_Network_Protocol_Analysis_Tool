# PRD: 修复勾选「ED监控协议」后 ED 帧解析失败仍回退为 FC 起始解析的 bug

## 背景
用户粘贴一条 PLC2.0 ED..EE 监控包装报文，明确勾选单帧解析页「ED监控协议」复选框后解析。当 `_parse_ed_monitor_header` 因报文不完整（帧长声明长度 > 实际长度、缺 EE 结束符等）校验失败时，`parse_single` **静默回退**，把以 ED 开头的原始报文直接交给 `CSGNewGenParser`，导致 ED 第一字节被当成南网新一代 FC 起始符解析，产出错误结果。

## 根因（已定位）
- `main_gui.py::parse_single`（~L2989-3000）：ED 头解析返回 None 时不做任何处理，`frame_bytes` 保持为原始 ED 报文继续走 `current_parser.parse_to_table`。
- `main_gui.py::_parse_and_show_dialog` 内 `_preprocess`（~L3786-3796）：同样的静默回退。
- `main_gui.py` 批量解析循环（~L4146-4172）：`_extract_csg_new_gen_frames` 对 ED 提取失败（返回 `("","")`）的行保留原始 ED hex，后续 `else` 分支直接送解析器。

CSG FC 起始字节低 4 位 ∈ {0x8,0x9,0xA,0xB}，0xED（低 4 位 D）永远不是合法 FC 起始，因此协议 9 下 ED 开头的输入只能是 ED 包装帧（或垃圾数据），绝不能按 FC 解析。

## 需求
勾选「ED监控协议」（或弹窗「剥离ED监控头」）且报文首字节为 0xED 时：
1. ED 头解析成功 → 前置监控头信息 + 业务帧解析（现状不变）。
2. ED 头解析失败 → **明确报错**（提示 ED 监控帧不完整/格式错误），绝不回退为把 ED 当 FC 起始解析。

## 改动范围
1. `parse_single`：引入 `ed_mode` 判定，失败时 `QMessageBox.critical` 报错并 return。
2. `_parse_and_show_dialog._preprocess`：失败时返回标记，`do_parse` 用 error_label 展示错误而非继续解析。
3. 批量解析循环：协议 9 下 `frame_hex.startswith("ED")` 且 `ed_data_type == ""`（提取失败）→ 生成「ED 帧格式错误」结果行，不送解析器。

## 验收标准
- [x] 勾选 ED监控协议，粘贴完整合法 ED 帧 → 正常前置监控头 + 业务帧解析（回归不破坏）。
- [x] 勾选 ED监控协议，粘贴不完整 ED 帧（如用户报文的截断形态：帧长声明 549 但仅 135 字节）→ 弹出明确错误提示，不出现「起始符(FC)=ED」类错误解析。
- [x] 不勾选 ED监控协议 → 行为与现状一致（按用户选择不剥离）。
- [x] 弹窗解析（热键/命令行/剪贴板）勾选剥离 ED 头时，不完整 ED 帧显示错误提示。
- [x] 批量解析：ED 提取失败的行标记为 ED 帧格式错误。
- [x] 运行 `python test_monitor_plc2_deframe.py` 及新增验证脚本通过（14/14 + 回归全绿）。
