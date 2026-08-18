# Implement：协议7（国网）福建增补 + EB 数据标识扩展

## 阶段 0：前置
- [x] 三份文档已转换 markdown（附件1.md / 附件3.md / 附件4.md）
- [ ] 备份要改的文件（gdw10376_parser.py 等 git 已跟踪，直接改）

## 阶段 1：解析器扩展（gdw10376_parser.py）

### 1.1 AFN_MAP / FN_MAP 新增福建增补
- [ ] 新增常量 `FUJIAN_AFNS = {0x50, 0x51, 0x52, 0x53, 0x55, 0x56}`
- [ ] AFN_MAP 增补 6 个 AFN 名称
- [ ] FN_MAP 增补各 AFN 下 Fn 名称（见 design §4.1）

### 1.2 parse_to_table 福建增补分支
- [ ] 读取 AFN 后 `is_fujian = afn in FUJIAN_AFNS`
- [ ] 信息域解析：`is_fujian` → 福建增补 R 结构（下行保留5+序列号；上行保留4+事件标志+序列号）
- [ ] 地址域解析：`is_fujian` → 固定 A1(6B)+A3(6B)=12B（剩余 ≥ 12+3+2 即解析）
- [ ] `_parse_data_unit` 末尾加 `elif afn in FUJIAN_AFNS: self._parse_fujian_afn(...)`

### 1.3 新增 `_parse_fujian_afn`（集中处理 6 个 AFN）
- [ ] 0x50：F1 确认（命令状态+信道状态）、F2 否认（错误状态字）、F3 确认且后续任务
- [ ] 0x51：F1/F2/F3 无数据单元说明
- [ ] 0x52：F1 透明转发（通信对象类型+地址+控制字+等待报文超时+等待字节超时+长度+内容）、F2/F3/F11 任务队列（方案号+任务序号+对象类型+地址+规约类型+保留+长度+内容）、F12 无数据单元；上行方向差异处理
- [ ] 0x53：F1 参数配置、F2 主节点地址、F4 厂商版本（厂商代码+芯片代码+版本日期+版本）、F5 信道信息（相位）、F6 串口当前通信参数（速率枚举+允许最高速率+恢复时长）、F10 模式切换
- [ ] 0x55：F1 主节点地址、F2 允许/禁止上报（n 个对象）、F3 启动广播（类型+时长+长度+内容）、F4 启动广播修正（类型+时长）、F6 启动注册（时长）、F7/F8 无数据、F9 预告抄读对象（数量+修正标志+n×[序号+类型+地址]）、F10 模式切换、F11 速率协商、F12 恢复时长、F13 允许最高速率、F18 无数据
- [ ] 0x56：F1 主动注册从节点信息（数量+n×地址）、F2 事件内容（对象类型+地址+长度+报文）、F3 抄读请求（类型+地址+延时）、F4 响应报文（方案号+序号+类型+地址+长度+内容）、F5 信道延时、F6 广播完成、F13/F14 2字节长度版、F15 带任务信息事件上报

### 1.4 EB 数据标识（附件1）
- [ ] 新建 `gdw_eb_di_lookup.py`：EB_DI_MAP = { "EB030002": {...}, ... }（名称/格式/长度/单位/说明）
- [ ] `_parse_data_unit` 中 0x52-F1 / 0x56-F2 的内嵌 645 帧检测 DI 前缀 EB → `_parse_eb_di`
- [ ] `_parse_eb_di(di_code, data_bytes, base_offset)` 按各 EB 项格式解析（BIN/BCD/ASCII/BS8）
- [ ] 特别处理：EBEEEEEE 多数据项（嵌套 数据项个数+[长度+内容]）、EB0403XX 停上电记录、EB030110 台区识别、EB030307~09 NTB、EB0406XX 任务队列

## 阶段 2：组帧（gdw_frame_generator_schema.py + gdw_send_frame_lib.py）
- [ ] schema 新增福建增补各下行 (afn, fn) 字段定义（design §4.3）
- [ ] gdw_send_frame_lib.py：`generate_frame` 检测 afn ∈ FUJIAN_AFNS → 增补 R 结构（保留+序列号）+ A1+A3（无中继）
- [ ] `_build_info_domain` 增加增补分支（若按结构差异实现）

## 阶段 3：校验（validator/gdw_validator.py）
- [ ] AFN 值域检查确认覆盖 0x50~0x56（range(0x00,0xF2) 已含）
- [ ] 可选：福建增补帧长度校验细化（R6+A12+AFN1+DT2+数据）

## 阶段 4：GUI 集成
- [ ] 查询页：`get_afn_fn_list()` 自动含新 AFN/Fn（无需改）；可选新增 EB 数据标识查询区块
- [ ] 组帧页：`afn_fn_combo` 自动含新 schema（无需改）；验证福建增补 AFN 可选可组帧
- [ ] 校验注册：已含 GDWValidator（无需改）

## 阶段 5：测试（test/test_gdw_fujian.py）
- [ ] 附件3 各 AFN/Fn 解析测试（构造 68+L+C+R+A+AFN+DT+数据+CS+16 帧）
  - 52H-F1 透明转发（含 EB030002 645 帧）
  - 52H-F2 任务队列智能补采
  - 53H-F4 厂商版本上行、53H-F6 串口参数
  - 55H-F9 预告抄读对象
  - 56H-F2 事件上报、56H-F4 响应报文
- [ ] 附件1 EB 数据标识解析测试（645 帧 91/81/14 控制码 + EB030002/EB030110/EB0403XX/EBEEEEEE）
- [ ] 福建增补组帧测试：generate_frame 生成字节 = 预期 hex
- [ ] 回归：现有国网帧（如 03H-F1）解析不受影响

## 阶段 6：验证
- [ ] `python -m py_compile gdw10376_parser.py gdw_send_frame_lib.py gdw_frame_generator_schema.py validator/gdw_validator.py gdw_eb_di_lookup.py`
- [ ] `python test/test_gdw_fujian.py` 全过
- [ ] GUI 冒烟：`python main_gui.py` 协议7 解析福建增补帧 + 组帧页选福建增补 AFN
- [ ] 无既有测试回归（test/ 下无 gdw 测试，检查其余核心测试不因 import 变更破坏）

## 阶段 7：收尾
- [ ] main_gui.py CHANGELOG 新增条目
- [ ] AGENTS.md §10/§11 同步（版本记录、协议表）
- [ ] README.md 同步
- [ ] task.py finish / archive
