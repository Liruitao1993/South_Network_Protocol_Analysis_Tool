# PRD：协议8 虚拟表（DL/T 698.45 从站模拟器）Tab

## 背景

项目根目录新增开源项目 `Meter698-45Simulator-master/`（PyQt5，DL/T 698.45 虚拟电表模拟器 V1.35）：串口监听主站请求，按档案数据（`config.ini` 中 194 个 OI 数据项）自动构造 698 响应帧，支持多表通配、黑白名单、电能量递增、冻结时标、曲线漏点、明文 MAC，并附带 645 模拟。

用户要求：**理解开源项目后重写**（不是代码搬运/集成），在主程序（PySide6）协议 8（DL/T 698.45）下新增「虚拟表」tab，遵循本项目架构规范（独立 widget 文件、字节操作、复用现有 698 A-XDR 编解码器与组帧器、app_paths 持久化、ZoomableTableWidget/主题/图标规范）。

## 目标

1. **离线模拟**：粘贴/输入主站请求帧 hex → 虚拟表生成响应帧，表格展示响应字段，响应帧可复制、可一键送单帧解析器回读验证（自组帧自解析闭环）。
2. **串口实时从站**：tab 内独立选择串口（端口/波特率/校验/停止位），持续监听 698 请求帧（`68...16`），自动组帧回复；收发日志窗口显示。支持 FE 前缀等杂滤。
3. **档案可编辑**：开源 `config.ini` 的 194 条 OI 数据迁移为项目 JSON 数据文件（`meter_sim_data.json`，经 app_paths 定位、frozen 自愈种子），tab 内表格增删改（OI/属性/索引/名称/数据 hex），数据 hex 用 AXDRCoder 实时解码预览业务值；支持导入/导出 JSON。
4. **动态数据**：通信地址（4001/4002/202a）按请求 SA 回应、当前时间（4000）实时生成、正向有功电能（00100200）随运行时间递增、日/月/曲线冻结时标按请求 Selector 时间或系统时间生成。
5. **高级特性**（开源已有，全部纳入）：通配地址多表模拟（数量可配，表号递增）、黑白名单（SA 地址过滤，`/` 分隔）、曲线冻结漏点时段（起止时间内返回空数据）、明文回复附加 MAC（`0A0B0C0D`，安全 APdu 10 00 封装）。
6. **645 模拟**：开源附带 Meter645_core（功能小）。本期作为**可选收尾项**：698 链路收到 645 帧（68...68 结构/非 68 起始）时识别并回 645 响应；若工作量超预期可拆二期，不阻塞 698 主体验收。

## 服务覆盖（重写后必须支持的请求类型）

- GET-Request Normal（05 01）：单 OAD → Get-Response Normal（85 01）；事件类 OAD（OI 3xxx，如 3320）走事件记录特殊响应
- GET-Request NormalList（05 02）：多 OAD → Get-Response NormalList（85 02），逐项 OAD+Get-Result
- GET-Request Record（05 03）：记录型（冻结 5002 曲线/5004 日/5006 月）→ Get-Response Record（85 03），解析 RSD Selector（01/02/09）与 RCSD/CSD，按档案 `50040200_<OI>` 等键生成记录行
- 安全请求（10 00 明文）：解封装内层 APDU，响应按 `90 00 len + APDU + 01 00 04 0a0b0c0d` 封装（MAC 开关开启时）
- 链接管理（01/02 预连接/应用链接请求）→ 对应响应（81/82）
- SET（06）/ACTION（07）请求：回标准响应（86/87）带 DAR（成功/对象不存在），不修改档案（只读模拟；写操作可选项）
- 未支持服务/未知 OI：Get-Result 返回 DAR（对象不存在 0x09），不崩溃、不回空（遵守 AGENTS.md 容错显示原则）

## 约束

- 纯 Python 3.8+、PySide6；核心逻辑**不依赖 Qt**（可独立测试），UI 在独立 `meter_sim_widget.py`
- 字节操作，禁止开源项目那种 hex 字符串手工拼接；A-XDR 编解码统一走 `dl_t698_45_axdr.py` AXDRCoder；链路帧/HCS/FCS 走 `dl_t698_45_frame_gen.py` DLT69845FrameGenerator
- 数据文件一律 app_paths.data_path 定位；新增 JSON 种子需进 spec datas
- 表格用 ZoomableTableWidget；按钮走 set_btn/set_btn_icon 图标规范
- tab 仅协议 8 可见（参考组帧 tab 可见性控制）
- 测试放 `test/test_meter_sim.py`，含 `import _path_setup`；核心断言用 DLT69845Parser 回读自生成响应帧形成闭环
- 不修改开源目录 `Meter698-45Simulator-master/`（仅作参考，不打包进 spec）

## 验收标准

1. 离线模式：对开源 config.ini 档案中 ≥20 个典型 OI（电能 array、电压 long-unsigned、需量 structure+date_time_s、冻结记录、时间、地址、事件）构造请求帧，响应帧经 DLT69845Parser 回读字段正确、HCS/FCS 校验通过。
2. NormalList 多 OAD、Record 冻结（Selector 01/02/09 三种）、安全明文+MAC、链接请求、未知 OI DAR、多表通配（SA=AA..AA 时回 `05+递增表号`）各有测试用例通过。
3. 动态特性：电能量随时间递增（两次回复值递增）、冻结时标取请求时间/系统时间、漏点时段内返回空记录、黑名单 SA 不回复，均有可观察行为与测试。
4. 串口模式：用虚拟串口对（或环回）验证收到 `68...16` 请求后自动回帧；FE 前缀与分片粘包能正确组帧；开始/停止按钮状态正确，关闭 tab/软件时线程退出无残留（遵守线程回收要求）。
5. 档案表格：增删改行后持久化到 JSON，重启后生效；数据 hex 列解码预览正确；导入导出 JSON 可用。
6. GUI：协议切到 8 时「虚拟表」tab 可见，切其他协议隐藏；主题切换/字体缩放/Ctrl+滚轮缩放正常；按钮带图标。
7. `python test/test_meter_sim.py` 全过；`py_compile` 全部新增/修改文件通过；698 既有测试（test_dl_t698_45*.py）无回归。
8. spec 打包包含 meter_sim_data.json；AGENTS.md §1/§3/§5.6/§6/§10 与 CHANGELOG 同步。

## 非目标（本期不做）

- 真实电能表逻辑仿真（功率曲线物理建模）——数据来自档案静态值+有限动态规则
- SET/ACTION 写档案持久化（回 DAR 即可，写操作二期）
- 密文/ESAM 安全认证（仅明文+MAC 封装）
- Reflex Web 版虚拟表（本期仅 PySide6 主程序；Web 版后续同步）
