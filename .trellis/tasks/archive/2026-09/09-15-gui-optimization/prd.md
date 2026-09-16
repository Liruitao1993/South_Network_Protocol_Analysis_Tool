# GUI 版优化批次（批量解析性能 / 死代码清理 / 窗口状态持久化）

## Goal

把 PySide6 桌面版（`main_gui.py`）中**有实测证据**的三类问题落地修复：批量解析主线程卡顿与内存占用、MainWindow 内重复/死方法与根目录临时脚本、窗口与表格布局状态不持久化。

来源：一轮「GUI 版还有什么可以优化」的体检咨询（2026-09-15）。该轮否掉了两个未经证实的假设（启动慢 / 表格填充慢），只保留实测到的三项，用户选定这三项作为一个批次。

父任务只承载需求集合、子任务映射与跨子任务验收，**不直接实现**。

## Background — 体检实测数据（2026-09-15，PySide6 6.9.2，offscreen）

样本：仓库内真实监控日志 `CCO-2-COM3-260628-124120 - 复制.log`（33 MB / 316,671 行 / GBK），协议 9，`auto` 级别 → **49,532 帧**。

| 环节 | 实测 | 结论 |
| --- | --- | --- |
| `import main_gui` + `QApplication` | 0.26s | 启动不是问题 |
| `MainWindow()` 构造（全 Tab） | 0.70s | 启动不是问题 |
| 12 个协议逐个切换 | ≤ 0.022s | 切换不是问题 |
| 监控前缀剥离 | 1.26s | 可接受 |
| 帧提取 | 0.20s | 可接受 |
| **逐帧解析** | **19.33s（0.39 ms/帧，主线程）** | **问题 1：卡死** |
| **`batch_results` 保留内存** | **229.4 MB** | **问题 2：内存** |
| 摘要表填充 49,532 行 × 5 列 | 1.49s | 可接受，**不必分页** |
| 摘要表自身内存 | 13.3 MB | 内存问题不在控件 |
| **过滤一次（现状 `setRowHidden` 全表）** | **0.87s / 每次按键** | **问题 3：过滤慢** |
| 同上，`setUpdatesEnabled(False)` 包裹 | **0.02s** | 一行修复即可 |
| 纯 Python 索引过滤 49k 条 | 0.007s | 分页收益来源，但非必需 |
| 数据查询表（DI/OBIS/AFN/命令字） | 均在实例内缓存，无重复读盘 | **不是问题** |

结论：**内存与卡顿都能在「数据层」修掉，摘要表分页不是必需品。**

## 子任务映射

| 子任务目录 | 交付物 | 优先级 |
| --- | --- | --- |
| `09-15-gui-batch-parse-perf` | 批量解析后台化 + 进度 + 取消 + 详情按需重解析（去 229MB）+ 过滤提速 | P0 |
| `09-15-gui-dead-code-cleanup` | 删除 5 组重复方法、7 个零引用方法、13 个根目录临时脚本 | P2 |
| `09-15-gui-window-state-persist` | 窗口几何 / 分栏 / 表格列宽持久化 | P2 |

## 跨子任务验收标准

1. 三个子任务各自独立验收，互不阻塞；不新增任何第三方依赖。
2. `python release_check.py` 无 FAIL / WARN（基线以实现前实测记录为准）。
3. 涉及批量链路的既有回归必须全过：`test/test_batch_snapshot_locate.py`、`test/test_csg_summary.py`、`test/test_gw_monitor_summary.py`、`test/test_app_exit.py`。
4. 不改任何协议的解析语义（字节序 / CRC 范围 / 帧结构判定）。
5. 每项完成后同步 `main_gui.py:CHANGELOG`；涉及约定变更时同步 `AGENTS.md`。

## Out of Scope（整批）

- 不动 Web（Reflex）侧代码与共享逻辑边界。
- 不做主题 / 视觉重做，不新增标签页。
- 不重构 `main_gui.py` 的 Tab 拆分（10,991 行 / 246 方法的结构性拆分另开任务）。
- 不改协议注册表的表驱动收口（36 处 `current_protocol ==` 硬编码分支另开）。
- 不把 `config.json` 里的明文 API Key 改为凭据存储（另开，属安全议题）。

## Open Questions

- 无（子任务各自的开放问题记录在子任务 `prd.md`）。

---

## 跨子任务验收结果（归档记录，2026-09-16）

三个子任务均已完成并归档：

| 子任务 | 状态 | 版本 | 提交 |
| --- | --- | --- | --- |
| `09-15-gui-batch-parse-perf` | ✅ 已完成 / 已归档 | 1.23.15 | `560df22`（步骤 2+3+4）、`41a9935`（步骤 5 登记）、`1c5b13a`（DoD 收口）；步骤 1 被并行任务 `b1aecdc` 顺带纳入 |
| `09-15-gui-window-state-persist` | ✅ 已完成 / 已归档 | 1.23.16 | `adb7064` |
| `09-15-gui-dead-code-cleanup` | ✅ 已完成 / 已归档 | 1.23.16 | `58f9ad6` |
| 本文档（容器） | ✅ 已归档 | — | — |

**跨子任务验收标准逐条核对：**

1. ✅ 三者各自独立验收、互不阻塞；**未新增任何第三方依赖**（测试新文件仅用标准库与 PySide6；`_config_sandbox.py` 用 `unittest.mock`）。
2. ✅ `python release_check.py` → **PASS=61 / FAIL=0 / WARN=0**（“零 WARN”在 `0f010a6` 才字面达成：之前两个 WARN 为 `BUILD_DATE` 非今天与 README 徽章滞后）。
3. ✅ 四个既有回归在门槛内全过：`test_batch_snapshot_locate.py`（47 项）、`test_csg_summary.py`、`test_gw_monitor_summary.py`（18 项）、`test_app_exit.py`。
4. ✅ 未改任何协议的解析语义（字节序 / CRC 范围 / 帧结构判定）——批量后台化只改执行位置与去/重建详情的时机，并有「协议9 真实日志 49,532 帧 + 协议11 13,763 帧」的 HEAD-vs-当前全量对拍（0 差异）为证。
5. ✅ 三项均同步 `main_gui.py:CHANGELOG`（1.23.15 / 1.23.16）；约定变更同步 `AGENTS.md`（§1 版本、§3 架构树、§7 `_path_setup` 的 F401 约定与测试清单、§8 陷阱 40/41/42）。

**新增测试（均登记 `release_check.py:CORE_TESTS`）**：`test/test_gui_batch_perf.py`（99 项）、
`test/test_window_state.py`（93 项）、`test/test_menu_wiring.py`（13 项）；另新增共享助手
`test/_config_sandbox.py`、`test/_batch_wait.py`。

**复核阶段另发现并修掉的 3 个真实缺陷**（均不在原子任务计划内）：

1. **取消丢结果**（P0 内）：取消落在分片中途时，最多 199 帧已解析结果被静默丢弃 → 状态栏「已解析 N」大于表格行数。已修，并以反例对照钉死回归（修复前：计数 250 / 实际回传 200）。
2. **测试污染真实配置**（窗口状态任务**引入**）：跑测试会把 offscreen 合成的 684×666 几何写进开发机真实 `config.json`，用户下次启动即被套用 → `closeEvent` 加 `_window_shown_once` 守卫（从未显示过的窗口不写盘）+ 共享沙箱 `test/_config_sandbox.py`。实测 5 个测试 + 整轮门槛后真实配置顶层键仍为 11 个、无 `window` 残留。
3. **菜单项点了没反应**（死代码清理时发现，已潜伏近一个月）：`配置→模型API管理` 的 `.triggered.connect` 被 `e1dd85e`（2026-08-21）误删；该方法的「零引用」正是此 bug 的**症状**——差点被当死代码删掉。已恢复接线 + 新增 `test/test_menu_wiring.py` 行为式守卫（变异反证：拿掉 connect → 变红）。

**已知偏差与遗留（未做）：**

- 子任务的 `prd.md` 曾把 `enhanced_batch_export.py` 列为 `_table_data` 消费方——实为 **被 `.gitignore` 排除的孤立副本**（无任何运行时 import 方），属该 prd 的误判；实际导出走 `enhanced_export.py`。
- **解析器入口未重置跳帧可变状态**（`_efc_symbol_count` / `_ofdma_frame_type` / `_ofdma_station_count`）：批量侧现用 `_ctx` 锁存 + `apply_cross_frame_state` 在重解析前复原，只在详情侧兜住一致性；根治会改变批量结果本身（实测影响 934/49,532 帧）→ 建议单独立项（已记 `AGENTS.md §8` 陷阱 41）。
- 协议10 / 协议0~8 **无真实日志对拍**（仅协议9、11 各做了一份全量对拍）。
- 根目录仍有 5 个被 git 跟踪的临时产物（`_cfg_test.json`、`_gw_*_tables.txt` 等）与两条已失效的 `.gitignore` 规则 → 建议「根目录治理」小任务。
- 真实人眼验收（拖动窗口 / 进度条 / 取消手感）与真机串口验证（无 COM 设备）未做，只有 offscreen 断言与心跳计时。
- 未实际打包（`BUILD_DATE` 已更新为 2026-09-16，发版前需再核一次并在 
  `python release_check.py` 确认无 WARN）。
