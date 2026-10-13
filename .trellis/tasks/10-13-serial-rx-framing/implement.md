# 执行计划：串口工具断帧（前导 FE + 可调超时）

> 目标版本 `APP_VERSION 1.23.77 → 1.23.78`。
> 环境铁律：批量/GUI 测试从 cmd 侧发起要套 pwsh（AGENTS §8 陷阱 62），命令统一带 `PYTHONIOENCODING=utf-8`。
> 并发铁律：`main_gui.py` / `reflex_web/` 有其它会话在改；提交只挑本任务文件，禁止 `git add -A`。

## 阶段 0 · 证据固化（已完成）

- [x] `research/serial-framing-facts.md`：现场帧逐字节、复现数据（含 FE 判 0 / 剥离后 35）、
      现有常量与函数锚点、相关陷阱（49/58/59/60/63/75）、受影响测试。**实现不得与之冲突。**

## 阶段 1 · 分帧函数认前导 FE（纯逻辑，无 Qt）

- [ ] `serial_tool_widget.py` 顶部 `import wakeup_prefix`（模块级纯逻辑，无 Qt 依赖）。
- [ ] 新增 `FE_WAKEUP_STRATEGIES = frozenset({"ft12_68", "dlt645", "dlt698_45"})`
      与 `_wakeup_base(strategy, buf) -> int`（未列策略返回 0）。
- [ ] `frame_length_for`：先算 `base`；`ft12_68` / `dlt645` / `dlt698_45` 三条分支的下标一律 `+base`，
      仍按「剥离后结构长度」做 `RAW_MIN/MAX` 合理性检查，**返回 `base + 结构长度`**。
- [ ] `declared_frame_len`（无协议启发式）：同样先算 `base`，`len(buf) - base < 8` 才判「不足以分辨」，
      645/南网国网/698 三种口径的下标 `+base`，返回 `base + n`。
- [ ] **审查点 A**：`python -c` 跑现场帧 —— 含 4 个 FE 的 14 B 首片 → `frame_length_for("dlt698_45", …) == 39`；
      无 FE 的等价帧返回值与改动前**逐字节相同**（`base == 0` 恒等）。

## 阶段 2 · 参数化（4 个超时 + 断帧方式）

- [ ] 模块级新增 `FRAME_TIMEOUT_RANGES`（键 → (min, max)）与 `FRAMING_MODE_OPTIONS = (("auto", "自动（协议特征优先）"), ("timeout_only", "仅按字节超时"))`。
- [ ] `DEFAULT_PARAMS` 追加 5 键（默认值引用现有常量，**不写魔数**）：
      `rx_byte_idle_ms` / `rx_raw_max_hold_ms` / `rx_frame_idle_ms` / `rx_frame_hold_max_ms` / `rx_framing_mode`。
- [ ] `merge_params` 里对 5 个新键做**夹紧 + 类型宽容**（非 int → 默认；越界 → 夹到边界；未知 mode → `auto`）。
- [ ] `CONFIG_VERSION` **不变**（只新增键，未改既有默认值）—— 在代码注释里写明理由。
- [ ] UI：「接收模式」分组下方新增 `QGroupBox("断帧设置")`，2 行 `QGridLayout`：
      行1 = `断帧方式` 下拉 + `字节静默超时` spin；行2 = `协议帧等待静默` + `协议帧等待上限` + `聚合最长持有`。
      每个控件带 tooltip（作用 + 调大/调小代价）；`valueChanged` → `_schedule_save()` + `_log_framing_summary()`。
- [ ] `_collect_params` / `_load_persisted` 双向绑定新键（载入时 `blockSignals` 防重入保存）。
- [ ] **审查点 B**：老配置（无新键）载入 → 5 个控件显示默认值；改值落盘 → 新建 widget 读回一致；越界值夹紧。

## 阶段 3 · 分帧链路接线

- [ ] 新增 `_framing_mode()` / `_timeouts()` 两个取值方法（直接读控件，无缓存不一致）。
- [ ] `_on_raw_data`：`timeout_only` 时**不调用**结构切帧（只进聚合缓冲）。
- [ ] `_flush_raw_display` / `_flush_raw_display_now`：`timeout_only` 跳过结构路径；时间路径改用
      `_timeouts()` 的四个值替代模块常量。
- [ ] `_frame_incomplete`：68 家族（含无协议启发式）先算 `base`；`base >= len(buf)`（只有 FE）→ True；
      `buf[base] == 0x68` 且剩余不足 `min_hdr` → True；其余保持。
- [ ] `_on_rx_mode_changed` / 切「断帧方式」→ 先 `_flush_raw_display_now()` 再清缓冲（同既有口径）。
- [ ] **审查点 C**：现场帧按 `14 B + 25 B` 两块交付、间隔 20 ms → 恰好 1 条 `[RX]`（共 39 B）；
      无 FE 的既有帧输出与改动前逐行相同。

## 阶段 4 · 说明行（现场自查）

- [ ] `_log_framing_summary()`：输出 `[断帧] 方式=…；超时 字节静默 10ms / 帧等待静默 300ms / 帧等待上限 5000ms / 聚合最长持有 200ms；当前协议=698.45协议（策略=698.45 结构(68 L L C…)，前导 FE 自动跳过）`。
      `timeout_only` 或协议无策略时的文案要说清「按字节超时」/「该协议无自证分帧依据」。
- [ ] 调用点：断帧设置变更（`valueChanged`/下拉切换）、每轮 `_start_send` 开始处各一次（**不**逐帧打印）。
- [ ] **审查点 D**：切方式/改超时/每轮开始各恰好一行；关闭「显示接收」时不在日志窗口刷屏（但仍进文件？——
      与既有 `_log` 过滤口径一致，不额外造第二套过滤）。

## 阶段 5 · 测试

- [ ] `test/test_serial_proto_frame.py` 扩段：
      [11] 前导 FE 矩阵（0/1/2/4 个 FE × 4 种入口：3 策略 + 无协议）、纯 FE 缓冲返回 0 不抛异常、
           带 FE 的非 68 数据不误判、645/698 互斥判定在带 FE 时仍成立；
      [12] 新参数：默认值 == 常量、缺失键回落、越界夹紧、非法类型回落、`rx_framing_mode` 非法值→`auto`。
- [ ] `test/test_serial_tool_widget.py` 加第 [34] 段：
      ① **现场 39 B 帧 14+25 两块交付（间隔 > 静默窗口）→ 恰好 1 条 RX**（修前 2 条，用同一断言序列自证）；
      ② `timeout_only`：同输入按字节超时聚合（结构不再切帧）；
      ③ 4 个参数 + 断帧方式持久化往返（沙箱 `_config_sandbox` 内）；
      ④ `[断帧]` 说明行出现且不刷屏。
- [ ] **变异反证 ≥3 条**（跑完必须还原）：
      ① `_wakeup_base` 恒返回 0（不跳前导）→ FE 用例变红；
      ② 返回 `结构长度` 而非 `base + 结构长度` → 末字节自证/整帧长度断言变红；
      ③ `_framing_mode()` 恒返回 `"auto"` → `timeout_only` 用例变红。
- [ ] **审查点 E**：新老测试全绿 + 3 条反证变红；既有套件 `test_serial_tool_widget.py` / `test_serial_proto_frame.py` /
      `test_serial_worker_write_raw.py` 全绿。

## 阶段 6 · 文档与版本

- [ ] `main_gui.py:CHANGELOG` 头部新增 1.23.78 条目；`APP_VERSION` → `1.23.78`；`--sync-iss`；README 徽章/版本行。
- [ ] `AGENTS.md`：§8 陷阱 59 补「前导 FE 已由分帧层跳过（串口工具）」；**陷阱 75 中「串口分帧策略表也不变」改写**；
      §5.8 串口工具章节补「断帧设置（4 个超时 + 断帧方式）」；§10 追加 1.23.78 摘要。
- [ ] `README.md`：串口工具功能行补「协议特征断帧（含前导 FE）/可调断帧超时」。
- [ ] `python release_check.py --with-gui` → **FAIL=0**。
- [ ] **审查点 F**：提交只挑本任务文件（`serial_tool_widget.py` + 两个测试 + `.trellis/` 产物 + spec 条目），
      版本/文档四件套按上一轮结论留在工作区随发版批次；提交前 `git diff --cached --stat` 复核。

## 审查点汇总

| 审查点 | 时机 | 判据 |
|---|---|---|
| A | 阶段 1 后 | 带 FE 首片可算出 39；无 FE 恒等 |
| B | 阶段 2 后 | 参数默认/夹紧/往返正确 |
| C | 阶段 3 后 | 现场帧 1 条 RX；既有帧零回归 |
| D | 阶段 4 后 | 说明行有且不刷屏 |
| E | 阶段 5 后 | 全绿 + 3 条变异反证变红 |
| F | 提交前 | release_check FAIL=0、文档齐、只提交本任务文件 |

## 回滚点

1. 阶段 1~4 任一失败 → `git checkout serial_tool_widget.py`。
2. 阶段 5 失败 → 移除新增测试段（两个既有文件按 hunk 回退）。
3. 配置只新增键 ⇒ 回滚不需要清理运行时数据；若已把带新键的配置写盘，旧版本读到时忽略未知键。
