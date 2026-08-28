# Implement：协议8 虚拟表（698.45 从站模拟器）

> 执行顺序自上而下；每阶段结束运行对应验证命令。测试用 Windows Python：
> `cd /mnt/e/python/南网解析工具 && PYTHONUTF8=1 python.exe test/test_xxx.py`（bash/WSL 环境），
> 或 Windows PowerShell `python test/test_xxx.py`。

## 阶段 0：数据种子

- [ ] 0.1 写 `scripts/gen_meter_sim_data.py`（离线一次性，不打包）：解析 `Meter698-45Simulator-master/config.ini` `[MeterData]` 194 条 → `meter_sim_data.json`（格式见 design.md archive 节）；含下划线冻结键拆分 frozen/oi
- [ ] 0.2 运行生成 `meter_sim_data.json`，抽查 5 条（00000200 组合有功电能 array、20000200 电压、10100200 需量 structure、50040200_20210200 冻结、40000200 时间）与 ini 一致
- [ ] 0.3 `test/test_meter_sim.py` 加用例：load_archive 后条目数 = 194、lookup 命中/未命中行为

## 阶段 1：链路层（meter_sim/link_layer.py）

- [ ] 1.1 `extract_frames(buf)`：68 起、L 小端长度域定位、尾 16 校验、FE 前缀跳过、粘包/分片保留
- [ ] 1.2 `parse_header(frame)`：C 控制域位域、地址标志字节（地址类型 2bit/逻辑地址/长度 N=低5bit+1）、SA/CA 提取
- [ ] 1.3 验证：用开源收发帧（config 目录/日志中取真实 698 请求帧）解析字段；坏帧/分片用例
- [ ] 1.4 测试：extract 粘包两帧、半帧保留、FE 前缀、坏 FCS 丢弃

## 阶段 2：档案与动态数据

- [ ] 2.1 `archive.py`：load/save/lookup/add/update/remove（app_paths.data_path 定位、ensure_data_file 种子）
- [ ] 2.2 `dynamic_data.py`：current_time_item（date_time_s）、comm_address（55 07 05 + 表号）、increase_energy（5 费率递增规则）、freeze_timestamp（Selector 时间/系统时间）、leak_check
- [ ] 2.3 测试：时间项 tag=1c 且日期为当前；递增两次值单调；冻结时间取 RSD 时间与系统时间两路径

## 阶段 3：响应构造（response_builder.py）

- [ ] 3.1 build_get_response_normal（85 01，含 DAR 路径）——先与开源同输入帧比对响应 hex
- [ ] 3.2 build_get_response_normal_list（85 02，count + OAD/GetResult 序列）
- [ ] 3.3 build_get_response_record（85 03，0200/count/0101 行/0000 尾；Selector 01/02/09；冻结键 lookup）
- [ ] 3.4 链接响应（81/82）、SET/ACTION 回 86/87 DAR
- [ ] 3.5 事件（OI 3xxx）特殊结构；安全封装 wrap_security（90 00 + 变长 len + 0100040a0b0c0d）
- [ ] 3.6 链路帧统一走 DLT69845FrameGenerator._assemble_frame（control=0xC3）；HCS/FCS 由其计算
- [ ] 3.7 测试：≥20 典型 OI 请求→响应，**用 DLT69845Parser 回读断言**（OAD 名称/数据业务/HCS-FCS 校验通过）；NormalList、Record×3 Selector、安全+MAC、未知 OI DAR、链接各一条

## 阶段 4：引擎（engine.py）

- [ ] 4.1 MeterSimEngine.handle_frame：header→黑白名单→安全解封装→APDU 分派→响应
- [ ] 4.2 通配地址（AA..AA/类型1）：按 meter_count 多表序号响应（SA `05+表号小端`）；单播回原 SA
- [ ] 4.3 黑白名单命中返回 []；漏点时段曲线记录返回空
- [ ] 4.4 测试：黑/白名单、通配 3 表、漏点时段、非 698 帧（645/垃圾）不崩溃

## 阶段 5：离线 GUI（meter_sim_widget.py）

- [ ] 5.1 VirtualMeterWidget 骨架 + QTabWidget（运行/档案数据/模拟设置）
- [ ] 5.2 离线模式：请求帧输入（QPlainTextEdit 不折行）+「生成响应」+ 日志区 + 响应帧表格（调 DLT69845Parser.parse_to_table 展示）+「送解析器回读」
- [ ] 5.3 档案页：ZoomableTableWidget（key/OI/属性/索引/名称/数据hex/解码预览），增删改、导入导出 JSON、hex 编辑后 AXDRCoder.decode 刷新预览、保存
- [ ] 5.4 设置页：多表数量/黑白名单/递增/自动冻结/漏点时段/QTimeEdit/MAC 开关 → SimOptions
- [ ] 5.5 按钮全部 set_btn + set_btn_icon；表格 ZoomableTableWidget；主题/字体跟随

## 阶段 6：串口从站模式

- [ ] 6.1 独立串口配置（端口/波特率/校验/停止位下拉 + 刷新按钮）与监听 QThread（参考 SerialWorker：raw 字节信号）
- [ ] 6.2 收字节流 → extract_frames → engine.handle_frame → send_frame；日志（时间戳/方向/数据标识 OI 名称）
- [ ] 6.3 开始/停止状态机；停止时关闭串口 + wait 线程退出；closeEvent 兜底（线程回收）
- [ ] 6.4 测试/手测：虚拟串口对环回（或 com0com/VSPD），主站侧用本软件组帧页发 GET 请求验证回帧；粘包/FE 前缀手测

## 阶段 7：main_gui 集成

- [ ] 7.1 import + 创建 VirtualMeterWidget + addTab（"虚拟表"，~L1107 区）
- [ ] 7.2 `_on_protocol_changed`：仅协议 8 可见 tab，其余隐藏
- [ ] 7.3 py_compile：`python -m py_compile main_gui.py meter_sim_widget.py meter_sim/*.py`
- [ ] 7.4 offscreen/人工冒烟：启动 GUI、切协议 8 看到 tab、档案页加载 194 条、离线生成一帧响应显示

## 阶段 8：收尾

- [ ] 8.1 `南网协议解析工具.spec` datas 增加 meter_sim_data.json
- [ ] 8.2 `test/test_meter_sim.py` 全量通过；回归 test_dl_t698_45.py / test_dl_t698_45_data_decode.py / test_dl_t698_45_fujian.py / test_dlt698_preset.py 全过
- [ ] 8.3 main_gui.py CHANGELOG + APP_VERSION bump（1.16.0）+ BUILD_DATE；AGENTS.md §1/§3/§5.6/§6/§7/§10 同步
- [ ] 8.4 trellis-check 全量质量门；lsp_diagnostics 无新增错误
- [ ] 8.5 （可选）645 旁路：engine 中非 68-16 结构帧尝试 645 响应；时间不足拆二期并在 PRD 标注

## 验证命令汇总

```bash
# 单元/闭环测试
PYTHONUTF8=1 python.exe test/test_meter_sim.py
# 698 回归
PYTHONUTF8=1 python.exe test/test_dl_t698_45.py
PYTHONUTF8=1 python.exe test/test_dl_t698_45_data_decode.py
PYTHONUTF8=1 python.exe test/test_dl_t698_45_fujian.py
PYTHONUTF8=1 python.exe test/test_dlt698_preset.py
# 编译
python.exe -m py_compile main_gui.py meter_sim_widget.py meter_sim/*.py scripts/gen_meter_sim_data.py
```

## 回滚点

- 阶段 0-4 全为新增文件，不影响现有功能，可随时放弃
- 阶段 7 动 main_gui.py（仅 addTab + 可见性分支，小改动），集成前先 commit 阶段 0-6 成果
