# Implement：国网协议 7 组帧 GUI 测试与修复

## 步骤

1. **代码阅读** ✅
   - 找到 `frame_gen_widget.py` 中国网协议 7 组帧 UI 代码。
   - 理解字段收集、实时预览、生成按钮逻辑。

2. **测试发现问题** ✅
   - 通过脚本测试所有 76 个国网 AFN+Fn 命令，均可生成帧。
   - 发现非法输入会导致崩溃：
     - uint 字段输入 "abc" → `_collect_values` 抛出 ValueError
     - bytes 字段输入非 hex → `bytes.fromhex` 抛出 ValueError
     - `_generate_gdw_frame` 未捕获异常，直接崩溃
   - 发现输入校验缺失：
     - 序列号/信道/应答字节数无限制
     - 地址字段无格式提示，用户易误输入 hex

3. **修复问题** ✅
   - `_generate_gdw_frame` 增加 try/except，组帧失败弹 QMessageBox。
   - 预定义字段 uint8/16/32 添加 `QIntValidator`。
   - 预定义字段 bytes 添加 hex-only `QRegularExpressionValidator`。
   - 国网源/目的地址输入框：placeholder 提示"12位十进制BCD"，并添加 digit-only validator。
   - `gdw_seq`、`gdw_channel`、`gdw_resp_bytes` 添加 `QIntValidator` 并连接 `textChanged` 实时更新。
   - 地址字段连接 `textChanged` 实时更新。

4. **验证** ✅
   - 所有 76 个国网命令均可正常生成。
   - 非法输入不再崩溃，而是弹出警告或无法接受。

## 变更文件

- `frame_gen_widget.py`

## 未涉及

- 未修改 `gdw_send_frame_lib.py`、`gdw10376_parser.py` 等后端逻辑。
- 未涉及南网/698.45 组帧核心逻辑（仅共享字段 widget 增加校验）。
