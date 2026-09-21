# Web 与 GUI 同步审计（1.23.0 ~ 1.23.22）

> 审计方法（一句话）：以 `main_gui.py:CHANGELOG` 为唯一数据源，用脚本按 `ast` 精确抽取 **1.23.0~1.23.22 共 23 个版本、167 条**改动（不含 1.23.23~1.23.40），逐条对照 `reflex_web/` 现状（import 链 / 同一函数 / 同一标签页）判定 `继承`·`缺失`·`同错`·`N/A`；所有 `继承` 判定均给出 `文件:行号` 或 import 链依据，禁止凭印象。
>
> - 判定口径：`继承` = Web 走同一个类/函数或已有等价实现（改动自动生效）；`缺失` = Web 无对应能力；`同错` = 两端各有一份实现且都有同一缺陷；`N/A` = 纯桌面能力（托盘/串口/QSS 主题/窗口状态/监控器/档案/拓扑/虚拟表/时序图 UI 等）或测试/工程债，不影响 Web 运行链路。
> - Web 侧基线事实（本文件反复引用）：
>   - 解析器全部**直接 import 桌面同一模块**：`reflex_web/reflex_web/reflex_web.py:451-515`（协议0 `protocol_parser` / 6 `dlt645_parser` / 7 `gdw10376_parser` / 8 `dl_t698_45_parser` / 9 `csg_new_gen_parser` / 10 `gw_new_gen_parser` / 11 `hdc10_parser`）。
>   - 校验器与 645 转表走桌面注册表：`reflex_web.py:525`（`DLT645GuiParser`）、`:537-539`（`protocol_registry.make_validator`）。
>   - Web 标签页共 10 个：`single / batch / frame / diff / lookup / spectrum / tool / download / release / feedback`（`reflex_web.py:11906-12059`）——**无**时序图、虚拟表、实时监控、档案、拓扑。
>   - Web 批量/摘要/剥离的共享单源：`batch_core.py`（`extract_test_mode_content:1375`、`ed_wrapper_display:478`、`ed_wrapper_prefix_len:385`、`unwrap_ed_line:454`、`TEST_MODE_SENTINELS`）。

---

## 一、逐条判定总表（1.23.0 ~ 1.23.22）

> 版本行带日期与条目数；条目行 `判定` 四选一。末行为 1.23.22 派生的 645 转表偏移缺陷（`同错`）。

| 版本 | GUI 变更（精简） | 判定 | Web 对应物/依据 |
| --- | --- | --- | --- |
| **1.23.0** | *2026-09-09* · 共 15 条 | — | — |
| 1.23.0-01 | 新增「通信时序图」标签页（协议9） | 缺失 | Web 10 个标签页无时序图（`reflex_web.py:11906-12059`）；`reflex_web/` 下 `sequence_diagram` 0 命中 |
| 1.23.0-02 | 时序图交互（缩放/平移/导出 PNG/图↔表联动） | 缺失 | 同上（无时序图标签页） |
| 1.23.0-03 | 时序图广播与未入网节点画法修正 | 缺失 | 同上 |
| 1.23.0-04 | 时序图 SACK 方向与台体角色修正 | 缺失 | 同上 |
| 1.23.0-05 | 时序图物理实体视角重构 | 缺失 | 同上 |
| 1.23.0-06 | 时序图覆盖扩展至协议9/10/11 | 缺失 | 同上 |
| 1.23.0-07 | 新文件 `sequence_diagram_widget.py`（纯逻辑 + Qt 层） | 缺失 | 纯逻辑层（`SequenceModel`/`build_sequence_model`）无 Qt 可直接复用，但 Web 未接（`reflex_web/` 无引用） |
| 1.23.0-08 | 时序图测试（model/gui） | N/A | 测试文件，不影响 Web 运行链路 |
| 1.23.0-09 | 批量脚本预处理 `hex_clean` 回退模式修复 | 缺失 | 实现在 `scripts/hex_clean.py`（桌面脚本引擎 `py_script_engine.py`）；`reflex_web/` 全目录无 `scripts/`/`py_script` 引用 |
| 1.23.0-10 | 脚本列表去重（`config.json` py_scripts 规范化） | N/A | 桌面脚本列表持久化；Web 无脚本列表功能 |
| 1.23.0-11 | ED 包装头新增「广西台体(14 字节头)」 | 继承 | 解析侧单源：`csg_new_gen_parser._parse_ed_wrapper:574-591` 支持 plc2/gx + `batch_core.ed_wrapper_display:478`；Web 无手动下拉（恒自动识别，见 -12） |
| 1.23.0-12 | ED 包装头新增「自动识别(推荐)」默认 | 继承 | 单源 `csg_new_gen_parser.detect_ed_wrapper:34`（桌面委托该函数）；Web `_safe_parse_to_table`（`reflex_web.py:517-528`）不传 `ed_wrapper` → 自动识别；批量侧 `batch_core.ed_wrapper_prefix_len`（`web_utils.py:413`） |
| 1.23.0-13 | 批量结果→输入日志行回跳（`_src_line`） | 缺失 | Web 无 `_src_line` 字段、无输入行回跳；`select_batch_item`（`reflex_web.py:973`）只填详情表 |
| 1.23.0-14 | 右键「转到原始报文位置」+ 原始日志快照查看器 | 缺失 | Web 无快照/查看器（`batch_source_view.py` 仅桌面 `main_gui.py:70` import）；`reflex_web/` 下 `snapshot`/`batch_source` 0 命中 |
| 1.23.0-15 | 多物理块重组点击行偏移错位修复 | 继承 | 修复在 `csg_new_gen_parser`（`_concat_segments`/`_remap_concat_rows`）；Web `reflex_web.py:501` import `CSGNewGenParser` |
| **1.23.1** | *2026-09-11* · 共 3 条 | — | — |
| 1.23.1-01 | 新增协议能力注册表 `protocol_registry.py` | 继承 | Web 已消费同一模块：`reflex_web.py:525`（`DLT645GuiParser`）、`:537-539`（`make_validator`）；协议下拉仍为 Web 自有 `PROTOCOL_OPTIONS`（`:347`）——见「发现汇总·其他 A/B」 |
| 1.23.1-02 | `main_gui` 接线（下拉/占位符/Tab 可见性/解析器/校验器分派） | N/A | 桌面接线；Web 有独立实现（`set_protocol:363`、`_parse_kwargs:568`、`_get_validator:530`） |
| 1.23.1-03 | 协议6 预设命令页 `set_protocol("dlt645")` | 缺失 | Web 预设按钮仅协议 0/7：`reflex_web.py:2745` `if p not in (0, 7)` → 协议6 无预设入口 |
| **1.23.2** | *2026-09-11* · 共 2 条 | — | — |
| 1.23.2-01 | 批量解析新增「导入 pcap」三模式 | 缺失 | Web 无 pcap 入口（`reflex_web/` 下 `pcap` 0 命中） |
| 1.23.2-02 | 新增 `pcap_import.py`（纯逻辑无 Qt） | 缺失 | 仅被 `main_gui.py:7776` 调用；模块无 Qt 依赖，可复用但 Web 未接 |
| **1.23.3** | *2026-09-11* · 共 2 条 | — | — |
| 1.23.3-01 | 新增 `release_check.py` 发布前自检 | N/A | 桌面发版工程债 |
| 1.23.3-02 | 新增 `test/test_core_suite.py` | N/A | 测试工程 |
| **1.23.4** | *2026-09-11* · 共 2 条 | — | — |
| 1.23.4-01 | DLT645 从站模拟核心 `dlt645_sim/` | N/A | Web 无虚拟表/从站模拟（`reflex_web/` 下 `dlt645_sim` 0 命中） |
| 1.23.4-02 | GUI 虚拟表 tab 扩展 + 串口从站线程接入 | N/A | 同上（串口为桌面能力） |
| **1.23.5** | *2026-09-11* · 共 1 条 | — | — |
| 1.23.5-01 | 协议6 新增「645虚拟表」tab | N/A | Web 无该标签页（标签页清单 `reflex_web.py:11906-12059`） |
| **1.23.6** | *2026-09-11* · 共 7 条 | — | — |
| 1.23.6-01 | 第 7 套主题「云母（Mica · Win11）」 | N/A | 桌面 QSS/DWM 圆角；Web 主题为自研 token 层 `theme_web.py`（非等价能力） |
| 1.23.6-02 | `test_theme_settings` 修复过时断言并扩项 | N/A | 桌面主题测试 |
| 1.23.6-03 | 修复统一按钮 ghost 类白字隐形 | N/A | Qt 按钮 builder/调色板；Web 无该体系 |
| 1.23.6-04 | 修复 645虚拟表串口下拉永远为空 | N/A | 桌面控件 |
| 1.23.6-05 | 645虚拟表新增「表地址」预设定 | N/A | 虚拟表桌面能力 |
| 1.23.6-06 | 645虚拟表「下发响应到串口」 | N/A | 串口桌面能力 |
| 1.23.6-07 | 645虚拟表引擎补齐 13H/15H/08H 功能码 | N/A | `dlt645_sim` 仅桌面消费 |
| **1.23.7** | *2026-09-11* · 共 7 条 | — | — |
| 1.23.7-01 | 645虚拟表新增 LME 自定义下发（4.2/4.6/4.7） | N/A | 虚拟表桌面能力 |
| 1.23.7-02 | 新建 `dlt645_sim/lme_query.py` | N/A | Web 无引用 |
| 1.23.7-03 | 645虚拟表运行页新增分组与只读帧框 | N/A | 桌面 UI |
| 1.23.7-04 | 串口从站线程新增 `slave_frame` 信号 | N/A | 串口桌面能力 |
| 1.23.7-05 | 645虚拟表离线模拟支持 DIR=1 回包直解 | N/A | 虚拟表桌面能力 |
| 1.23.7-06 | 测试（95 项 + 真实串口端到端） | N/A | 测试 |
| 1.23.7-07 | spec hiddenimports 补 `dlt645_sim*` | N/A | 桌面打包（`南网协议解析工具.spec` 含 `dlt645_sim`，Web spec 不含） |
| **1.23.8** | *2026-09-12* · 共 5 条 | — | — |
| 1.23.8-01 | 645虚拟表「随机产生事件」 | N/A | 虚拟表桌面能力 |
| 1.23.8-02 | 修复事件状态字应答被截断（引擎取 `dlt645_frame_schema.get_di_info`） | N/A | 调用点在 `dlt645_sim/engine.py`（仅桌面）；被调模块 `dlt645_frame_schema` 本身两端共用 |
| 1.23.8-03 | 新增 `dlt645_sim/dynamic_data.py` | N/A | Web 无引用 |
| 1.23.8-04 | 修复 645虚拟表档案 JSON 读写失效（补 `import json`） | N/A | 桌面虚拟表 |
| 1.23.8-05 | 测试（66 项 + COM1↔COM2 回环） | N/A | 测试 |
| **1.23.9** | *2026-09-14* · 共 12 条 | — | — |
| 1.23.9-01 | 频谱图参数四字段双向联动/单位/检波 | 继承 | 复用 `spectrum_widget` 纯逻辑；Web `SpectrumState._sp_params:4033` / `sp_set_param:4057` / `_sp_apply_freq_link:4065` / `sp_set_select:4122` |
| 1.23.9-02 | trace 输入解析、非法 token 报错、越界裁剪 | 继承 | `spectrum_widget.parse_levels`/`build_trace`；Web `sp_set_trace_text:4145` / `sp_draw:4149` / `_sp_draw_if_ready:4189` |
| 1.23.9-03 | QPainter 仪器式屏幕 + 导出 PNG | 继承 | Qt 绘制换 SVG：`spectrum_web.py` + `reflex_web.py:_sp_render:4216` / `sp_export_png:4361` |
| 1.23.9-04 | 实现拆分 `spectrum_widget.py`（纯逻辑 + Qt 层） | 继承 | Web 直接 import 纯逻辑层：`reflex_web.py:3999/4011/4023/4035/4067/4096/4151/4201/4218/4270/4279/4304/4324` |
| 1.23.9-05 | 标记 M1~M6/十字光标/峰值搜索/标记表 | 继承 | `reflex_web.py:_sp_refresh_markers:4199` / `sp_plot_click:4302` / `sp_next_peak:4322` / `sp_del_marker:4349` |
| 1.23.9-06 | Δ 标注 `M?↔M?`、Δ 参考、峰值谷值、显著度 O(n) | 继承 | `spectrum_widget.markers_for`/`peak_indices`/`next_peak_index`（`reflex_web.py:4201/4324`）；`sp_set_ref_index:4137` |
| 1.23.9-07 | 积分带宽 IBW（两条点划线 + 填充带 + 标签） | 继承 | `reflex_web.py:_sp_refresh_ibw:4268`（`spectrum_widget.integration_band_for:4270`） |
| 1.23.9-08 | 积分功率计算（RBW 归一化/交集口径） | 继承 | 同一 `spectrum_widget` 实现（`_sp_refresh_ibw`） |
| 1.23.9-09 | trace 文本预处理（日志行尾取值与优先级） | 继承 | `spectrum_widget` 纯逻辑复用（`sp_set_trace_text` → `build_trace`） |
| 1.23.9-10 | 两处防误提取（分隔边界/时间戳/单位白名单） | 继承 | 同上（同一 `parse_levels`） |
| 1.23.9-11 | 清洗统计与提示（`TraceInput` 不变式） | 继承 | 同上（Web 状态行/提示同源） |
| 1.23.9-12 | 零新增依赖 + 测试 | 继承 | Web 侧同样零新增依赖（SVG 自绘 `spectrum_web.py`，不引入 matplotlib/QtCharts） |
| **1.23.10** | *2026-09-14* · 共 5 条 | — | — |
| 1.23.10-01 | 批量摘要体现测试帧的测试模式 | 缺失 | **本任务 R3 已修复**：桌面/Web 共用 `batch_core.extract_test_mode_content`；`web_utils.get_csg_new_gen_summary`（经 `_append_test_mode_segment:660`）与 `get_hdc10_summary:1094-1103` 已接入；对拍 `test/test_web_gui_parity.py` |
| 1.23.10-02 | 无测试模式字段时回退可读信息 | 缺失 | **本任务 R3 已修复**：同单源 `batch_core.extract_test_mode_content:1375`（回退分支含测试ID/扩展ID/通信频段/上行测试帧） |
| 1.23.10-03 | 新增 `MainWindow._extract_test_mode_content` | 缺失 | **本任务 R3 已修复**：桌面改为一行转发 `batch_core`（`main_gui.py:8539-8541`），Web 直接 `from batch_core import extract_test_mode_content`（`web_utils.py:22`） |
| 1.23.10-04 | 测试：`test_csg_summary` 去复刻、改复用未绑定方法 | N/A | 测试工程 |
| 1.23.10-05 | 复核修复①~④（槽位探测/括号去重/哨兵 gate/整帧用例） | 继承 | 规则落在 `batch_core.extract_test_mode_content`（两端单源）；Web gate 用 `TEST_MODE_SENTINELS`（`web_utils.py:670-673`、`:1098-1100`） |
| **1.23.11** | *2026-09-15* · 共 4 条 | — | — |
| 1.23.11-01 | `custom_di_store.py` 单源 + 三处读写委托 | 缺失 | **本任务 R4 已修复**：`reflex_web.py` `State.add_custom_di:3175` / `delete_custom_di:3221` + `lookup_tab` 表单与逐行删除按钮（`:10830` / `:10887`）；`custom_di_store` 支持 path 注入（`custom_di_store.py:107/133`）；测试同上 |
| 1.23.11-02 | 行为增强（覆盖确认/多选批量删除/合并进 `DI_COMBINATION_MAP`） | 缺失 | **本任务 R4 已修复**（覆盖 + 多选批量删除 + 逐行删除；勾选列与「删除选中」按钮见 `reflex_web.py:10855/11060`，事件 `delete_selected_custom:3247`；内置/标准条目忽略并计数）；`DI_COMBINATION_MAP` 经 `protocol_parser` 构造合并，Web 查询页复用（`lookup_utils.py:98-111`） |
| 1.23.11-03 | `lookup_pages.py` 简化版两枚死按钮改真实增删 | 缺失 | **本任务 R4 已修复**：Web 查询页增删入口（`reflex_web.py:10830` / `:10887`）；桌面简化页 `lookup_pages.py` |
| 1.23.11-04 | 新增 `test/test_nanwang_custom_di.py`（92 项） | N/A | 测试工程 |
| **1.23.12** | *2026-09-15* · 共 19 条 | — | — |
| 1.23.12-01 | Reflex Web 版解析 P0 缺陷修复（总述 10 条） | 继承 | 本次即 Web 改动本身；下列各条给出对应实现位置 |
| 1.23.12-02 | `_get_validator` 未定义变量 `p` → 复用 `protocol_registry.make_validator` | 继承 | `reflex_web.py:530-539`（单一来源注册表工厂） |
| 1.23.12-03 | 批量失败判定全表扫描 ❌ 行 + 空表语义 + 异常字面量 | 继承 | `web_utils.batch_frame_outcome:79-95`；调用点 `reflex_web.py:891` |
| 1.23.12-04 | 奇数长度 hex 改为直接报错 | 继承 | `web_utils.hex_to_bytes_strict:46-60`（文案与桌面一致） |
| 1.23.12-05 | `parse_kwargs_for` + 协议10/11「PB帧类型」下拉 + 协议9 `mac_only` | 继承 | `web_utils.parse_kwargs_for:98-120`；`reflex_web.py:384`（`set_csg_pb_frame_type`）/`:394`（`set_gw_pb_frame_type`）/`:568-597`（`_parse_kwargs`） |
| 1.23.12-06 | ED..EE 广西台体(gx) 错位 1 字节 → 判别下沉到解析器 | 继承 | `csg_new_gen_parser.detect_ed_wrapper:34`（单源，桌面改为委托）；Web 单帧/批量同走该解析器；摘要侧 `web_utils.py:698-707` 按「监控包装头」区分 |
| 1.23.12-07 | 南网 DI 查询 AFN 列算错 → 改 AFN = DI1 | 继承 | `lookup_utils._search_south_di:107-110`（`afn = di1` + `AFN_MAP`） |
| 1.23.12-08 | 协议10 查询页改读 `GWNewGenParser` 自有 7 类表 | 继承 | `lookup_utils._search_gw_newgen:361-400` |
| 1.23.12-09 | 协议8 查询页「属性/方法」列填充 | 继承 | `lookup_utils._search_698_oi:274-312` |
| 1.23.12-10 | 报文工具 CRC-24 参数改 `rev=True` | 继承 | `web_utils.tool_crc24_newgen:1361-1370` |
| 1.23.12-11 | 新增 `test/test_web_parse_fixes.py`（75 项） | N/A | 测试工程 |
| 1.23.12-12 | 批量链路同口径化（`mac_only` 直通/奇数长度/异常统计） | 继承 | `web_utils.strip_csg_new_gen_prefix:313-316`；`reflex_web.py:881-919`（异常分支 + 成功/失败/异常统计） |
| 1.23.12-13 | 审计勘误：`strip_frame_bytes` 幂等不变式 | 继承 | `web_utils.strip_frame_bytes:63-76`（纯函数 + 重复调用一致） |
| 1.23.12-14 | 复核修复：①快捷小窗 ED wrapper ②打包声明 ③文档 | 继承 | ①桌面调用点（解析器单源）②`reflex_web/reflex_web_exe.spec` 已含 `protocol_registry`/`parser_registry`/`hdc10_parser`/`validator.hdc10_validator` ③文档 |
| 1.23.12-15 | Web 版新增「频谱图」常驻标签页 | 继承 | `SpectrumState`（`reflex_web.py:3934-4374`）+ `spectrum_web.py`（SVG）+ 复用 `spectrum_widget`；标签页 `:11963` |
| 1.23.12-16 | Web 批量结果搜索/筛选 | 继承 | `reflex_web.py:1058`（`set_batch_search`）/`:1064`（`set_batch_status_filter`）/`:1040`（`_apply_batch_filter`）；`web_utils.filter_batch_summaries:145` |
| 1.23.12-17 | Web 主题系统（6 预设 + 5 强调色 + 3 模式 + token 化） | 继承 | `theme_web.py` + `ThemeState`（`reflex_web.py:4376-4490`） |
| 1.23.12-18 | 主题控件两处回归 + 分享卡 `str(Var)` 修复 | 继承 | `reflex_web.py` 顶栏/根容器与 `landing_web.py`；分享卡见 `:10621` 一带 |
| 1.23.12-19 | Web 批量解析摘要分页 | 继承 | `web_utils.paginate:173` / `page_of:190`；`reflex_web.py:1026-1097`（`_load_batch_page`/翻页/每页条数） |
| **1.23.13** | *2026-09-15* · 共 4 条 | — | — |
| 1.23.13-01 | 修复预处理命令链全角状态不可用 | 继承 | `pp_cli.split_commands:258` 两端共用；Web 调用点 `reflex_web.py:830` / `:1164` |
| 1.23.13-02 | 新增 `pp_cli.split_commands()`（全角归一化重试） | 继承 | `pp_cli.py:258-275`；Web `parse_batch:828` 与 `run_preprocess:1161` 均已改走该函数 |
| 1.23.13-03 | 未知命令报错增强（码位 + 半角书写提示） | 继承 | `pp_cli._describe_token:277-288`（两端同一函数） |
| 1.23.13-04 | 新增 `test/test_pp_cli.py`（47 项） | N/A | 测试工程 |
| **1.23.14** | *2026-09-15* · 共 16 条 | — | — |
| 1.23.14-01 | Web 新增独立产品首页（`/` 落地页、工具页迁 `/app`） | 继承 | `landing_web.py` + `reflex_web.py:24-30` import；路由见文件尾 `Route` 注册 |
| 1.23.14-02 | 新增 `reflex_web/reflex_web/landing_web.py`（约 1080 行） | 继承 | `reflex_web.py:26`（`from . import landing_web`） |
| 1.23.14-03 | 导航改造（4 处站内链接全部改指、无死链） | 继承 | `landing_web.INTERNAL_LINKS` + `test/test_web_landing.py` 死链白名单守卫 |
| 1.23.14-04 | 主题控件抽 `theme_controls_compact()` 共用 | 继承 | `theme_web.py`；工具页与首页顶栏共用 |
| 1.23.14-05 | State 新增 `download_exe_size_mb` / 保留 base64 截图通道 | 继承 | `reflex_web.py:3288-3419`（`load_download_info`） |
| 1.23.14-06 | 响应式修复（420px 横向溢出 → 窄屏换行） | 继承 | `landing_web.py` / `theme_web.py` CSS |
| 1.23.14-07 | 版本徽章改读 `downloads/version.json` | 继承 | `landing_web.version_badge` + `test_web_landing.py` 守卫断言 |
| 1.23.14-08 | `load_download_info` 复位块上提（清陈旧版本/截图） | 继承 | `reflex_web.py:3288-3300`（函数开头统一复位下载相关字段） |
| 1.23.14-09 | Web 运行时数据外置（`app_data.py` 唯一来源） | 继承 | `reflex_web/reflex_web/app_data.py`；`reflex_web.py:25` import；启动脚本注入 `NW_WEB_DATA_DIR` |
| 1.23.14-10 | 两个构建脚本新增共用 `deploy_common.py` | 继承 | `reflex_web/deploy_common.py`（忽略规则 + 启动脚本片段 + 迁移脚本） |
| 1.23.14-11 | 修复 onefile exe 数据清零（数据根 = exe 同级） | 继承 | `app_data.py` 冻结态解析（`Path(sys.executable).parent / "nw_web_data"`） |
| 1.23.14-12 | 新增 `test/test_web_data_paths.py` | N/A | 测试工程 |
| 1.23.14-13 | 修复下载地址端口错乱（同源相对路径 + 真实 host） | 继承 | `web_utils.resolve_download_target:1597` / `release_absolute_url:1562` / `is_same_origin_serving:1572`；`reflex_web.py:_download_target_url:3433` |
| 1.23.14-14 | 部署脚本新增 `--port` + 新增局域网部署教程 | 继承 | `reflex_web/build_embedded_deploy.py` / `build_offline_deploy.py`（`--port`）；`docs/Web版局域网部署教程.md` |
| 1.23.14-15 | 随包静态资源白名单 + `resolve_download_asset` | 继承 | `app_data.resolve_download_asset`（`load_download_info` 消费）；`deploy_common.DOWNLOADS_ASSETS` |
| 1.23.14-16 | 测试与文档（`test_web_landing.py` 100 项等） | N/A | 测试工程 |
| **1.23.15** | *2026-09-16* · 共 7 条 | — | — |
| 1.23.15-01 | 批量解析后台化 + 进度条 + 取消按钮 | 缺失 | Web 批量为 async 生成器分块 yield（`reflex_web.py:872`、`:936-939`）有进度，但**无取消事件**（全文件 `cancel` 仅 `cancel_edit_preset:2864`/分享删除/对话框） |
| 1.23.15-02 | 取消落在分片中途时结果不丢 | 缺失 | 同上（Web 无取消路径） |
| 1.23.15-03 | 详情按需 LRU（229.4 MB → 20.6 MB） | N/A | 桌面内存优化；Web 结果留后端 `_batch_all_results`（`reflex_web.py:942`），详情直取 |
| 1.23.15-04 | 修详情重解析与批量解析不一致（跟帧可变状态） | N/A | Web 详情直接复用批量产出的 `result`（`reflex_web.py:895-905`、`:973-1020`），无重解析路径 |
| 1.23.15-05 | 摘要过滤提速（重绘包裹 + 250 ms 去抖） | N/A | Qt 重绘/输入去抖优化；Web 过滤走纯函数 `web_utils.filter_batch_summaries:145` |
| 1.23.15-06 | `parse_batch` 拆分 / worker 自有解析器实例 / `parse_one_frame` | N/A | 桌面结构重构（`batch_parse_worker.py`）；Web 为单实例顺序解析（`reflex_web.py:868`） |
| 1.23.15-07 | 新增 `test/test_gui_batch_perf.py`（99 项） | N/A | 测试工程 |
| **1.23.16** | *2026-09-16* · 共 7 条 | — | — |
| 1.23.16-01 | 窗口/分栏/列宽状态持久化 | N/A | 桌面 `config.json` 顶层 `window` 段；Web 无窗口几何概念 |
| 1.23.16-02 | 存储归属与写盘时机（顶层 `window` 段、真实退出写） | N/A | 同上 |
| 1.23.16-03 | 修「测试污染真实配置」副作用（`_window_shown_once` + 沙箱） | N/A | 桌面测试沙箱 |
| 1.23.16-04 | 新增 `test/test_window_state.py`（93 项） | N/A | 测试工程 |
| 1.23.16-05 | 3 个测试文件补 `F401` 抑制约定 | N/A | 桌面测试/规范 |
| 1.23.16-06 | GUI 死代码清理（`main_gui.py` -301 行） | N/A | `main_gui` 内部重构 |
| 1.23.16-07 | 修「配置→模型API管理」菜单失效 | N/A | 桌面菜单（Web 无该菜单） |
| **1.23.17** | *2026-09-16* · 共 5 条 | — | — |
| 1.23.17-01 | 修复协议11 批量解析不出前场日志行 | 继承 | `web_utils.strip_gw_new_gen_prefix:381-428`（含 `protocol_index` 形参） |
| 1.23.17-02 | 根因：级别来源读错 + app 判据端口过窄 | 继承 | Web 级别分派本就按协议（`reflex_web.py:846-853` 分别传 `gw_parse_level`/`hdc10_parse_level`） |
| 1.23.17-03 | 修复：app 判据改为解析器端口表集合 | 继承 | `web_utils.gw_app_port_prefixes:358-378`（`hdc10_parser.APP_PORTS` / `GWNewGenParser.PORT_NAMES`）；`batch_core.gw_app_port_prefixes:58` |
| 1.23.17-04 | Web 端同步（strip 增 `protocol_index` + 两端对拍） | 继承 | `web_utils.py:381`；调用点 `reflex_web.py:847-853`；对拍 `test/test_hdc10_batch_strip_level.py` |
| 1.23.17-05 | 新增 `test/test_hdc10_batch_strip_level.py`（29 项） | N/A | 测试工程 |
| **1.23.18** | *2026-09-16* · 共 6 条 | — | — |
| 1.23.18-01 | 应用层批量摘要显示业务功能与关键业务字段 | 继承 | `web_utils.get_hdc10_summary:1062-1092`（业务名 + 关键字段） |
| 1.23.18-02 | 新增 `_gw_app_biz_summary`（两优先级业务名 + 前 2 关键字段） | 继承 | `web_utils._gw_app_biz_summary:909-1002`（`_GW_APP_SUMMARY_KEY_FIELDS = 2`，`:888`）；`batch_core.gw_app_biz_summary:1265` |
| 1.23.18-03 | 元数据黑名单 + 关键字段扫描限定段窗口 | 继承 | `web_utils._GW_APP_META_FIELDS:869-887`；段窗口逻辑 `:909-1002`（起点=区头+1，终点=首个顶层行） |
| 1.23.18-04 | 摘要效果（现场帧 `端口:18 \| 报文:0x0030 \| 开始升级 …`） | 继承 | 同一 `get_hdc10_summary`（两端逐字规则） |
| 1.23.18-05 | Web 协议10 按表类型分流（应用层走协议11 实现） | 继承 | `web_utils.get_frame_summary:1126-1141`（有端口/报文ID → `get_hdc10_summary`，否则 `get_csg_new_gen_summary`） |
| 1.23.18-06 | 新增 `test/test_gw_app_summary_detail.py`（42 项） | N/A | 测试工程 |
| **1.23.19** | *2026-09-17* · 共 7 条 | — | — |
| 1.23.19-01 | 修复协议11 抄表报文解析崩溃 | 继承 | `reflex_web.py:509` import `HDC10Parser`（同一模块，修复自动生效） |
| 1.23.19-02 | 根因：`_parse_meter_reading` 引用未赋值 `proto_ver` | 继承 | `hdc10_parser` 单源 |
| 1.23.19-03 | 触发条件四条（协议11 + app 级别 + 报文ID 001/002/003 + 端口 0x11） | 继承 | 同上 |
| 1.23.19-04 | 修复：补 `proto_ver = b0 & 0x3F` | 继承 | 同上 |
| 1.23.19-05 | 现场帧（88 字节）逐字段验证 | 继承 | 同上 |
| 1.23.19-06 | 新增 `test/test_hdc10_meter_reading.py`（13 项） | N/A | 测试工程 |
| 1.23.19-07 | lens/pyright 4 处既有告警按最小修复未改 | N/A | 静态分析说明 |
| **1.23.20** | *2026-09-17* · 共 11 条 | — | — |
| 1.23.20-01 | 协议11 应用层报文收口（总述） | 继承 | `hdc10_parser` 单源（Web `reflex_web.py:509`） |
| 1.23.20-02 | ① `0x00A0`/`0x00A4` 由 `MSG_ID_NAMES` 统一命名 | 继承 | `hdc10_parser` 单源 |
| 1.23.20-03 | ② 无字段格式章节业务只报业务名 + 原始数据 | 继承 | `hdc10_parser`（`MSG_ID_NO_FORMAT_DEFINED`） |
| 1.23.20-04 | ③ 措辞区分「未按业务格式解析」/「格式未定义」 | 继承 | 同上 |
| 1.23.20-05 | ④ 端口白名单不再挡在通用头之前 | 继承 | 同上（`_parse_app_only` / `_parse_msdu_payload`） |
| 1.23.20-06 | ⑤ 「是否应用层」改以 MAC 头声明为准（`APP_MSDU_TYPES`） | 继承 | 同上 |
| 1.23.20-07 | ⑥ `sec_mode != 0` 新增「⚠ 安全保护」行 + 两端黑名单 | 继承 | Web `_GW_APP_META_FIELDS` 已含 `"⚠ 安全保护"`（`web_utils.py:886`），与桌面同集合 |
| 1.23.20-08 | 新增 `test/test_hdc10_app_dispatch.py`（94 项） | N/A | 测试工程 |
| 1.23.20-09 | 基线对拍（60 帧全量快照，仅 3 帧允许变化） | N/A | 验证过程 |
| 1.23.20-10 | 变异反证 5 条 | N/A | 验证过程 |
| 1.23.20-11 | 范围外（MME 7 类/645·698 内嵌/IPv4/静默吞异常） | N/A | 明确范围外 |
| **1.23.21** | *2026-09-17* · 共 11 条 | — | — |
| 1.23.21-01 | 协议6 新增《光伏协议转换单元扩展协议》解析 | 继承 | `dlt645_parser` 单源（`reflex_web.py:489`）+ `dlt645_pv_ext` 单源 |
| 1.23.21-02 | 扩展数据标识三组共 682 个 DI 键 | 继承 | `dlt645_pv_ext.PV_DI_MAP`；Web 查询页经 `dlt645_di_lookup.merge_pv_di_map`（`dlt645_di_lookup.py:14/43`）→ `lookup_utils._search_dlt645_di:197` |
| 1.23.21-03 | 新增扩展控制码 `0FH`/`8FH`（无线转发透传） | 继承 | `dlt645_parser` 单源 |
| 1.23.21-04 | 解码规则（长度列/符号位/单相 FF/事件块/枚举/DI0 双语义） | 继承 | `dlt645_parser` + `dlt645_data_codec` 单源 |
| 1.23.21-05 | 单一来源 `dlt645_pv_ext.merge_pv_di_map` | 继承 | `dlt645_di_lookup.py:43` 调用同一函数（Web 经此合并）；未改生成物 `dlt645_di.json` |
| 1.23.21-06 | 桌面与 Web 同步（查询页 1781 条 + 关键字段对拍） | 继承 | `lookup_utils._search_dlt645_di:194-211`（同一 lookup 实例）；对拍 `test/test_dlt645_pv_ext.py` |
| 1.23.21-07 | 组帧侧错配守卫（`dlt645_frame_schema.build_di_fields`） | 继承 | 共用模块 `dlt645_frame_schema`；Web 组帧 `reflex_web.py:2058`（`build_di_fields`）+ `:2690`（`DLT645FrameGenerator`） |
| 1.23.21-08 | 新增 `test/test_dlt645_pv_ext.py`（156 项） | N/A | 测试工程 |
| 1.23.21-09 | 变异反证 6 条 | N/A | 验证过程 |
| 1.23.21-10 | 存疑不臆造（歧义行保留原始 hex） | 继承 | 同一解析器/查询单源 |
| 1.23.21-11 | 范围外（组帧下发/虚拟表/附录G/698.45 透传） | N/A | 明确范围外 |
| **1.23.22** | *2026-09-17* · 共 9 条 | — | — |
| 1.23.22-01 | 协议6 校验和错误时不再拒解析 | 继承 | `reflex_web.py:489` import `DLT645Parser`（同一模块） |
| 1.23.22-02 | 根因：`check_frame()` 把结构判据与校验判据混在一起 | 继承 | `dlt645_parser` 单源 |
| 1.23.22-03 | 判据拆为 `check_structure()`/`calc_checksum()` + 提示行 | 继承 | 同上；Web 转表走 `protocol_registry.DLT645GuiParser`（`reflex_web.py:525-527`） |
| 1.23.22-04 | 新增 `checksum_expected`/`structure_valid`/`structure_error` | 继承 | 同上 |
| 1.23.22-05 | `valid` 语义保持不变 | 继承 | 同上（消费方 `dlt645_sim` 仅桌面） |
| 1.23.22-06 | 长度 <12 给出「帧长不足」说明 + 原始 hex | 继承 | 同上 |
| 1.23.22-07 | 新增 `test/test_dlt645_tolerant_parse.py`（135 项） | N/A | 测试工程 |
| 1.23.22-08 | 行为变化：虚拟表从站对坏 CS 帧改正常应答 | N/A | 虚拟表为桌面能力（`dlt645_sim/engine.py`） |
| 1.23.22-09 | 消除 `hdc10_parser.py` 两处静态分析误报 | 继承 | `hdc10_parser` 单源，零行为变更 |
| （1.23.22 派生） | 645 转表偏移越界：声明长度 ≠ 实际帧长时「校验和」偏移 `[18,18]` 落在帧外 | 同错 | **本任务 R2 已修复**：唯一实现在 `protocol_registry.DLT645GuiParser`，`reflex_web._safe_parse_to_table` 改为 import 该实现（`reflex_web.py:517-528`）；守卫 `test/test_dlt645_table_offsets.py` |

**判定计数（167 条 CHANGELOG 条目）**：`继承` 88 · `缺失` 21 · `同错` 0 · `N/A` 58；另有 1 条 1.23.22 派生缺陷行判 `同错`（上表末行）→ 表内共 168 行。

---

## 二、发现汇总

> 除任务已确认的三项缺口（R2.2 偏移 `同错` / R3 测试模式摘要 `缺失` / R4 查询页自定义 DI `缺失`，均已在总表逐条标注修复位置与测试）之外，本轮新发现的缺口如下。

> 本 6 项已按 G1 评审决定**拆为后续子任务** `09-21-web-missing-capabilities`（PRD 见该任务目录），不在 `09-17-web-gui-parity-sync` 内实现。
### 2.1 新发现的「缺失」（7 项，均附证据）

1. **时序图能力整体缺失**（对应 1.23.0-01 ~ -08）
   - 证据：Web 10 个标签页固定为 `single/batch/frame/diff/lookup/spectrum/tool/download/release/feedback`（`reflex_web.py:11906-12059`）；`reflex_web/` 目录内 `sequence_diagram` 0 命中（`sequence` 的 6 处命中全是帧对比的 `diff_ignore_sequence` 序号字段）。
   - 可复用性：`sequence_diagram_widget.py` 的纯逻辑层（`SequenceNode`/`SequenceMessage`/`SequenceModel`/`build_sequence_model`）无 Qt 依赖，理论上可被 Web 直接 import。

2. **批量「原始日志快照 + 转到原始报文位置」缺失**（对应 1.23.0-13、-14）
   - 证据：`reflex_web/` 目录内 `snapshot`、`batch_source`、`_src_line` 均 0 命中；`select_batch_item`（`reflex_web.py:973`）只把后端 `result` 填进详情表，不定位输入行、不建快照。桌面侧对应实现为 `batch_source_view.py`（`main_gui.py:70` import）与 `_src_line` 行映射。

3. **脚本预处理（用户 py 脚本列表）缺失**（对应 1.23.0-09、-10）
   - 证据：`reflex_web/` 目录内 `scripts/`、`py_script` 0 命中；Web 预处理只有 `pp_cli` 管道（`reflex_web.py:828`、`:1161`），因此 `scripts/hex_clean.py` 的「无 'ED 标记回退」修复在 Web 端不可达（Web 用户无该命令入口）。

4. **pcap 导入缺失**（对应 1.23.2-01、-02）
   - 证据：`reflex_web/` 目录内 `pcap` 0 命中；`pcap_import.py` 仅被 `main_gui.py:7776-7832` 调用，且模块本身无 Qt 依赖（可复用）。

5. **批量解析无「取消」**（对应 1.23.15-01、-02）
   - 证据：Web 批量为 async 生成器分块 yield（`reflex_web.py:872` `CHUNK_SIZE = 100`、`:936-939`），有 `batch_progress` 但全文件无批量取消事件（`cancel` 命中仅 `cancel_edit_preset:2864`、分享删除确认、通用对话框）。

6. **协议6 预设命令缺失**（对应 1.23.1-03）
   - 证据：`reflex_web.py:2738-2748` `_load_preset_buttons` 仅 `p in (0, 7)`（南网 `NW_command.json` / 国网 `GW_command.json`），协议6 无预设按钮；桌面侧 1.23.1-03 正是修协议6 预设页 `set_protocol("dlt645")` 漏调。

7. **协议7 自定义 AFN 增删缺失**（prd R4 第二半；GUI 侧功能源自 1.14.7，落在本审计区间之外）
   - 证据：`reflex_web/` 目录内 `custom_afn`、`gdw_custom_afn` 0 命中；桌面单源为 `GDW10376Parser.add_custom_afn`（`gdw10376_parser.py:258`）/ `remove_custom_afn`（`:270`），落盘路径硬编码 `app_paths.data_path("gdw_custom_afn.json")`（`:211`、`:217`）——若要接 Web，须先按 design D5.2 加可选 `path` 注入，否则会写进 Web 代码目录、违反运行时数据外置约定（AGENTS §8 陷阱 39）。
   - 处置：**本任务 R4b 已按用户 G2 决定实现**（不降级）：`GDW10376Parser` 保持默认路径（`app_paths.data_path`，与 Web 解析器读的同一份文件），Web 侧 CRUD 逻辑放在 `lookup_utils.add_gdw_custom_fn` / `remove_gdw_custom_fns`（薄封装解析器既有 API，未新增第二份 JSON 读写），State 事件 `add_custom_afn:3196` / `delete_selected_custom:3247`，UI 见 `reflex_web.py:10968+`（协议7 表单）与查询表「选择/自定义」列；`gdw_afn_lookup.refresh()` 解决查询缓存不刷新问题；测试 `test/test_web_gui_parity.py` R4b 段（沙箱：`gdw10376_parser.data_path` + 清 `parser_registry._INSTANCES["gdw"]` + 清 `gdw_afn_lookup._LOOKUP_INSTANCE`） |

### 2.2 新发现的「同错」

- **无。** 除 1.23.22 派生的 645 转表偏移（R2.2，已修）外，本轮未发现其他两端各有一份实现且同款缺陷的条目：1.23.12~1.23.22 期间的解析器类修复全部经 `reflex_web.py:451-515` 的同一 import 链继承；1.23.12-06 / 1.23.17-04 两处历史上的两端漂移已在当时修好并留了对拍断言。

### 2.3 其他风险（非四分类，但需登记跟踪）

A. **摘要实现两份并存 + `batch_core` 摘要函数无调用方**
   - 桌面一份：`main_gui._get_csg_new_gen_summary:8544`、`_extract_csg_core_content:8733`、`_get_gw_new_gen_summary:8880`；Web 一份：`web_utils._csg_summary_core:687`、`extract_csg_core_content:788`、`get_hdc10_summary:1005`。
   - `batch_core` 内的同名实现（`get_csg_new_gen_summary:1632`、`get_gw_new_gen_summary:1819`、`get_summary_from_table_data:1944`、`extract_csg_core_content:1484`、`gw_app_biz_summary:1265`）**全仓无调用方**（`batch_core.<fn>` 命中清单只含 `TEST_MODE_SENTINELS`/`extract_test_mode_content`/`ed_wrapper_*`/`unwrap_ed_*`/`resolve_ed_wrapper`/`extract_frames_for_protocol`/`build_ed_header_rows`）。
   - `AGENTS.md:832`（§8 陷阱 31）已把「前缀剥离/帧提取/摘要/DLT645 转表/字段层级/查询数据源」的多份同义实现登记为待 `09-15-web-shared-parse-core` 收口；R2.1 已把 **645 转表**从该清单移除，但 AGENTS.md 该行文本尚未同步（属文档待办，不在本任务写入范围）。

B. **Web 工具页协议清单未走注册表**
   - `reflex_web.py:347-360` 的 `PROTOCOL_OPTIONS` 是 12 协议展示名的硬编码副本；`protocol_registry` 目前只被用于校验器与 645 转表（`:525`、`:537`）。落地页有与 `protocol_registry` 的对拍守卫（`test/test_web_landing.py`），但工具页下拉无对应守卫 → 1.23.1-01「新增协议优先改注册表」的目标在 Web 只部分达成。

C. **协议10 物理层/网络层帧摘要两端仍走不同实现**（已登记，不重复计为新增）
   - Web：`web_utils.get_frame_summary:1141` → `get_csg_new_gen_summary`（Web 自有 CSG 摘要）；桌面：`_get_gw_new_gen_summary`。1.23.18-05 与 `web_utils.py:1126-1130` 注释均明示该差异归 `09-15-web-shared-parse-core`。

---

## 三、未覆盖区间（1.23.23 ~ 1.23.40，仅列版本/日期/条目标题，不做判定）

> 以下 18 个版本（85 条）不在本任务审计范围，供后续按同一四分类补审。条目标题为原文前 52 字符截断。

- **1.23.40**（2026-09-21，6 条）
  - 协议6（DL/T645-2007）串口接收修复（用户报障：协议6 打开串口发送测试，只有发送没有接收）
  - 根因一：`SerialWorker._process_buffer` 只按 FT1.2 切帧（68H + 长…
  - 根因二：协议组帧页只连了 `frame_received`、未连 `raw_data_received`，故切帧…
  - 修：切帧按「首个 68H 之后偏移 +7 是否也是 68H」判别 DL/T645 双起始符（与 dlt6…
  - 修：`frame_gen_widget._on_serial_frame_received` 补 dlt64…
  - 测试：新增 `test/test_serial_worker_framing.py`（28 项）登记 COR…
- **1.23.39**（2026-09-20，7 条）
  - 协议11 应用层扩展（用户提供 HPLC技术应用手册 与 2024年2批HDC模块即装即采增补协议要求(…
  - 通信测试命令(0x006)：按 A-HS-11-03 表2 解析「检测扩展命令」——字节1 高4位为测试…
  - 事件上报(0x0008)：新增数据域字段级解析（原先只打印原始 hex）——位图方式（事件类型 1/2，…
  - 修 报文头长度 位拼接：事件上报与通信测试原按「低位在字节0」拼装（事件帧显示 192 字节头），改为与…
  - TCP 监控协议11 自动解析：ED 包装布局改用 CRC-24 自证（原「HDC MAC 版本号」启发…
  - TCP 监控自动识别排序：拿到帧控制证据时把 HDC 1.0 提到南网新一代之前（原先信标/SOF/SA…
  - 测试：新增 `test_tcp_monitor_proto11_frames.py`(55) / `test_…
- **1.23.38**（2026-09-20，6 条）
  - 协议11 TCP/ED 解析信标帧（用户提供现场帧：ED A4…FF EE，292 字节，帧长域=164…
  - `batch_core`：帧长域与 EE 不一致且缓冲区以 EF..EE 结尾时，按末尾 EE 重算整包（`…
  - HDC10 auto：FCCS 失败时若 DT=0 且 HDC1.0 版本位，按 FC+信标载荷继续解析…
  - 摘要：兼容协议11「定界符类型(DT)」字段名，并补「中央信标/发现信标」等信标类型
  - 该帧现解出：国网HDC包装头 + DT=0 信标 + FCCS✓ + 中央信标 + 时隙分配条目；摘要 …
  - 测试：新增 `test/test_beacon_ed_hdc10.py`（20 项）登记 CORE_TE…
- **1.23.37**（2026-09-20，4 条）
  - TCP 监控支持协议11 HDC 1.0：协议下拉新增「HDC 1.0」；选中后 ED..EE 封装按国…
  - `FlowBuffer` 改为保留完整 ED 帧（原先写死剥 9 字节 PLC2 公共头，HDC/gx 8B…
  - 主窗口 TCP 监控 tab 注入 hdc10 解析器；自动识别顺序：南网 → 国网新一代 → HDC …
  - 测试：新增 `test/test_tcp_monitor_ed_hdc.py`
- **1.23.36**（2026-09-20，4 条）
  - ED 包装头字段文案按协议分语义（用户：广西 ED 与国网 HDC 封装定义相同，但协议10/11 解析…
  - 单一来源 `batch_core.ed_wrapper_display(protocol_index, …`
  - 接线：`_parse_ed_monitor_header`、`csg_new_gen_parser._p…
  - 测试：新增 `test/test_ed_wrapper_labels.py`（19 项）；ed_gx_w…
- **1.23.35**（2026-09-20，6 条）
  - 协议10/11 单帧解析开放协议9 的 ED 工作流控件（用户：GUI 协议11 解析带 ED 封装报文…
  - 注册表 `ProtocolSpec` 新增 `has_ed_monitor` / `has_reverse_…
  - 协议10/11 工具栏可见：「ED监控协议」「ED包装格式」「4字节反转」「字节剔除头/尾」
  - 行为：勾选 ED → 与协议9 相同，解包失败明确报错；未勾选时 10/11 仍自动识别（业务帧 DT∈…
  - 解析弹窗「剥离ED监控头」同样适用于协议11，勾选后不完整 ED 帧报错
  - 测试：新增 `test/test_ed_ui_for_gw_hdc10.py`（25 项）；ed_fal…
- **1.23.34**（2026-09-20，5 条）
  - 修复协议11（HDC 1.0）FC 可变区域跨字节位域位序错误（用户报障：FC 源TEI 应为 002 …
  - 根因：FC 可变区域的跨字节位域按「首字节=高位」组装（如 src_tei=(b4<<4)/(b5&0x…
  - 判定依据（两条独立实证）：① 广播标志位=比特1 → (b11>>1)&1=1，该帧目的TEI 确为广播…
  - 修复：新增 `hdc10_parser._bits_lsb(data, byte_off, bit_off…`
  - 验证：现场 7 帧的 FC 源TEI/目的TEI 现与 MAC 头「原始源TEI」/「原始目的TEI」逐…
- **1.23.33**（2026-09-20，4 条）
  - 修复协议11（HDC 1.0）单帧解析/快捷弹窗仍把 ED..EE 监控包装帧当应用层解析（用户报障：单…
  - 根因：ED 解包在单帧路径被硬门控在协议9——parse_single 的 ed_mode 要求 cur…
  - 修复：两条单帧路径的 ED 识别扩到协议 9/10/11；协议10/11 无该复选框 → 自动识别，并新…
  - 回归：`test/test_hdc10_ed_wrapper.py` 扩到 30 项（新增单帧解析与快捷弹窗…
- **1.23.32**（2026-09-20，5 条）
  - 修复协议11（HDC 1.0）无法解析 ED..EE 监控包装帧（用户报障：现场日志帧贴入后被解析成「应…
  - 根因①：协议11 `extract_strategy="line"` 的默认分支「每行一帧」完全不做 ED …
  - 根因②：既有解包路径硬编码 `startswith("EDA5")` + 固定剥 15 字节；现场帧是 ED…
  - 修复：`batch_core` 新增通用 ED 解包三件套 `ed_wrapper_prefix_len`（按帧…
  - 验证：现场 7 帧（每帧 168B）现解出 7 条 152B 业务帧（FC16+PB136），FCCS/…
- **1.23.31**（2026-09-19，4 条）
  - 协议11（HDC 1.0）网络管理消息 MME 全 20 个类型字段级深解析补齐（依据第4-2部分表59…
  - 修复 0x000A 网络冲突上报分派调用不存在的 `_parse_network_conflict` 抛 N…
  - 所有变长列表/位图/12比特紧凑差值流均做截断容错（声明长度超实际给 ⚠ 不崩）；Web 端复用同一解析…
  - 新增 `test/test_hdc10_mme_full.py`（81 项，全类型 golden 断言 + …
- **1.23.30**（2026-09-18，5 条）
  - 协议10/11 批量/监控摘要：网络层（含仅PB级别）MME 帧体现管理消息 MMTYPE（用户报障：协…
  - 根因：桌面 `_get_gw_new_gen_summary` 只精确匹配协议10 字段名 `管理消息类…
  - 桌面摘要现兼容两种字段名 + 区头 comment（`MMTYPE: 0x0000 (关联请求)`），输…
  - Web `get_hdc10_summary` 同步：`MME:` 前缀改为与桌面一致的 `MMTYPE…
  - 测试：新增 `test/test_gw_pb_mme_summary.py`（13 项）登记 CORE_…
- **1.23.29**（2026-09-18，8 条）
  - 修复协议10/11「仅MAC帧(mac_only)」仍自动解析物理块头（用户报障：GUI 协议11 粘贴…
  - 契约与协议9对齐（AGENTS §8 陷阱19）：mac_only 输入即 MAC 帧，从字节0解析，不…
  - 协议10 `gw_new_gen_parser`：mac_only 原走 `_parse_pb_by_f…`
  - 协议11 `hdc10_parser._parse_mac_only`：去掉 data[0]&0x80 …
  - 协议11 MME 行偏移改为绝对帧偏移（原先相对 MSDU 切片，点击字节高亮错位）；`hdc10_mm…
  - GUI 解析级别下拉切换后自动重解析（与通道切换同口径）
  - 现场帧关键字段（协议10/11 一致）：版本0 / 源TEI0 / 目的TEI1 / MSDU类型0 /…
  - 测试：新增 `test/test_hdc10_mac_only_contract.py`（35 项，含 …
- **1.23.28**（2026-09-18，1 条）
  - 字段树增加「说明」列（字段 / 值 / 说明），中文含义直接可见；列宽 260/280，说明列伸展
- **1.23.27**（2026-09-18，1 条）
  - 字段树重做成 Wireshark 风格：两列「字段/值」而非表格四列；结构节点（有子级/位域/帧头等）可…
- **1.23.26**（2026-09-18，1 条）
  - 字段树与表格视觉对齐：主题 QSS 中 QTreeWidget 与 QTableWidget 同配色/交…
- **1.23.25**（2026-09-17，1 条）
  - 单帧解析结果新增「视图: 表格 / 字段树」切换（Wireshark 风格）：字段树按缩进还原父子层级，…
- **1.23.24**（2026-09-17，5 条）
  - 协议11（HDC 1.0）修复「无物理块头」帧整体错位（用户报障：同一帧协议10 能解析、协议11 只有…
  - 新增 `HDC10Parser._probe_pb_form(data)` 逐字节打分探测 PB 形态（…
  - 同时修复既有缺陷：`_parse_pb_and_mac_header` 把原帧绝对偏移当作 data 内…
  - 补齐抄表报文头的设备超时时间（字节6 ×100ms，§5.3.1.8）与选项字（字节7：方向位；终端主动…
  - 新增 `test/test_hdc10_pb_structure_probe.py`（39 项，含变异反…
- **1.23.23**（2026-09-17，12 条）
  - 协议6（DL/T645-2007）新增「主动上报状态字 / 主动上报模式字」位表解析（用户报障：读 `0…
  - 入库两张位表（逐位字面量，出处：第4号补遗「六、技术标准修改建议（一）」）：主动上报状态字（DI `04…
  - 保留位置位不再静默：输出「保留位（补遗未定义事件）: Bit76」这类明确标注（用户现场帧 `68 66…
  - 语义区分：模式字 1 = 该事件允许主动上报（使能），状态字 1 = 该事件已发生；全 0 时分别输出「…
  - 修正「电表运行状态字 1~7」位号（原表 8 个字无一正确）：`dlt645_data_codec.py…`
  - 输出变化（有意变更，逐条列出）：① 状态字1：Bit5 无功方向 / Bit4 有功方向 / Bit3 …
  - 补全附录C 明确声明的保留位占位（状态字 1/2/7 的 Bit8~Bit15、3 的 Bit8~Bit…
  - 兜底文案纠错：未收录位域不再给单一错误出处，改为并列「电表运行状态字见 DL/T645-2007 附录C…」
  - 单一来源：位表与格式化器仅落在 `dlt645_data_codec.py`（新增 `REPORT_ST…`
  - 新增 `test/test_dlt645_status_word_bits.py`（130 项，登记 C…
  - 变异反证 3 条全部实测变红后还原（状态字4 位号改回旧错位 9 红 / 去掉保留位标注 2 红 / 9…
  - 文档：新增《第4号补遗》MD（由同名 PDF 转换）至 `协议文档/6.645协议/`，位表依据可追溯（…

---

## 四、后续区间待办（1.22.x 及更早）

- **1.22.x 及更早全部版本尚未审计**（`CHANGELOG` 共 99 个版本，本次只覆盖 1.23.0~1.23.22）。建议按同一四分类与同一依据口径补审，并在本文件追加「1.22.x 区间」小节。
- 补审时的优先候选（本次审计途中发现、但归属早于 1.23.0，故未计入上方计数）：
  1. **协议7 自定义 AFN 增删**（桌面自 1.14.7 起有 `gdw_custom_afn.json`；Web 无）→ 见「发现汇总 2.1 第 7 条」，含路径注入前置条件。
  2. **数据文件内置种子自愈**（1.14.7：`custom_di.json` / `gdw_custom_afn.json` 等经 `ensure_data_file` 从打包资源落盘）在 Web 端是否成立——Web 数据根为 `nw_web_data/`（`app_data.py`），而 `app_data.PACKAGED_DOWNLOAD_ASSETS` 只覆盖 `downloads/` 静态资源，DI/AFN 类数据文件无对应「随包种子」机制，需核实。
  3. **1.23.1-01 的单源目标在 Web 只部分达成**（工具页 `PROTOCOL_OPTIONS` 未走注册表）→ 见「发现汇总 2.3 B」，若补审更早版本的注册表化改造，需一并核对。
- 本文件是**长期维护文档**：后续每完成一个含 Web 影响的版本，请在该版本对应分组追加条目行（保持 `| 1.23.x-NN | … |` 前缀，便于 `grep -c "^| 1\.23\."` 核对条数）。
