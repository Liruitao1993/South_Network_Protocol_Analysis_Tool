# 实施：串口工具批量替换通信地址

> 依赖顺序：纯逻辑（1）→ 单测（2）→ 对话框（3）→ 接线（4）→ GUI 测试（5）→ 反证（6）→ 冒烟（7）→ 文档（8）→ 门禁与提交（9）。
> 每个 gate 都要**跑命令看输出**，不许「看起来对」。

## 0. 前置阅读（改代码前）

- [ ] `.trellis/spec/frontend/component-guidelines.md` §7c（串口工具断帧契约/单一来源）、
      §7f（`frame_addr_fix` 复用契约 + 变异反证口径）、§7g（按钮区空间治理）
- [ ] `frame_addr_fix.py` 全文（`fields_for` / `parse_address` / `apply` / `notes` 语义）
- [ ] AGENTS §8 陷阱 58（串口工具契约）、59（按协议断帧/参数默认值迁移）、63（按钮不得写死宽度）、75（前导 FEH 只对 6/8）
- [ ] `bluetooth_tool_widget.ButtonEditDialog` 的地址区实现（`:675-815`）—— 复用其「动态字段 + 实时提示」写法

## 1. 纯逻辑层（`serial_tool_widget.py` ≤948 行区域）

- [ ] `HEX_MATCH_TYPES = ("contains", "equals", "starts_with", "ends_with")`（放在 `MATCH_TYPES` 附近，注释写明「只有这四种的预期响应是纯 HEX」）
- [ ] `AddrBatchItem` dataclass（`index/name/status/data_hex/protocol/match_hex/match_changed/notes/error`）
- [ ] `batch_fix_commands(...)`：
  - [ ] `indices` 去重/排序保护（越界下标跳过，不抛）
  - [ ] `data_hex` 非法 → `skipped`
  - [ ] 协议 6/8 剥前导（`wakeup_prefix.strip_wakeup_prefix`）→ `apply` → 恢复前导
  - [ ] `apply` 失败 → `kept`（原值 + `error`）
  - [ ] `write_protocol` → `protocol = int(protocol_index)`
  - [ ] `fix_match` → 仅 `HEX_MATCH_TYPES` 且可解析时尝试；不适用/失败都保持原样并进 `notes`
  - [ ] `try/except` 兜底（`apply` 内部已兜底，这里再兜一层防 `bytes`/`int` 转换类异常）
- [ ] **不修改入参**（只读 `commands[i]`，不做任何 `cmd[...] = ...`）

## 2. 单测 `test/test_serial_addr_fix.py`（纯逻辑）

- [ ] 文件头 `import _path_setup  # noqa: E402,F401`（此前踩过：`noqa` 少了 `F401` 会被 ruff 删行）
- [ ] 六协议真帧 oracle（帧样本取自既有测试的常量，勿自造）：替换后 ① 地址 = 期望 ② 该协议校验器 0 fail ③ 非地址字节不变
- [ ] 前导 FE：协议 8/6 → 保留前导 + 校验 0 fail；协议 0/7/13/14 → `kept`
- [ ] `write_protocol` 开/关；`fix_match` 五类（整帧 OK / 片段 kept / 通配不改 / 正则不改 / 非法 HEX）
- [ ] 作用范围：`indices` 子集、越界下标、空 `indices`、混合协议、`protocol=None`、协议 9/10/11/12
- [ ] 入参未被修改（深拷贝快照对拍）
- [ ] **Gate**：`python test/test_serial_addr_fix.py` 全绿、退出码 0

## 3. `BatchAddrDialog`（GUI 段）

- [ ] 协议下拉 + `_rebuild_addr_fields()`（保输入值；末行提示保留）
- [ ] 作用范围下拉（默认勾选；`_checked_rows()` 为空时默认「全部」并注明）
- [ ] 两个复选（默认勾选）
- [ ] `_refresh_hint()`：`将写入 N 字节：…` + 首条样例的 `apply` 预览（成功给 notes，失败给 error）
- [ ] `_on_accept()`：地址必填 + 逐字段 `parse_address`；长度优先按帧内推导（698 SA 由地址特征字节决定），推导不到用字段声明长度
- [ ] `values()` / `scope_indices()` / 两个复选值的读取接口
- [ ] **Gate**：offscreen 构造对话框（六协议逐一切换）不抛异常

## 4. 接线（`SerialToolWidget`）

- [ ] `cmd_btns` 里新增「替换地址」按钮（`fit_btn_width` 只设下限；图标用 `app_icons`/`gui_utils` 的**合法键**）
- [ ] `_on_batch_addr_clicked()`：构造对话框 → 取作用范围/协议/values → 空范围提示返回
- [ ] `_apply_addr_batch(items)`：抓快照 → 写回 3 个键 → `_rebuild_cmd_table()` → `_schedule_save()` → 日志 + 汇总
- [ ] `_undo_addr_batch()`（汇总弹框按钮调用）
- [ ] 汇总弹框：成功/保留/跳过计数 + 每类前 3 条原因；无改动时不给撤销按钮
- [ ] 日志明细上限 20 行 + 「另有 N 条」汇总行；全部走 `_log()`
- [ ] **Gate**：offscreen 手工跑一遍（子进程！长驻内核有 `sys.modules` 缓存，见既往教训）

## 5. GUI 测试 `test/test_serial_tool_widget.py` 新增段 [35]

- [ ] 按钮存在、`width() >= sizeHint().width()`、`maximumWidth == QWIDGETSIZE_MAX`（**`show()` 之后**量）
- [ ] 对话框：切协议 → 字段行数/标签变化；预览提示文案
- [ ] 端到端：3 条 645 报文（`protocol=None`）→ 全选 → 替换 → 表内 `data_hex` 地址域变化 + 协议列变化 + `commands[i]["protocol"] == 6`
- [ ] `fix_match`：可自证预期响应被替换；通配/正则保持原样
- [ ] 撤销：逐字节恢复；其它命令不受影响
- [ ] 落盘：`save_config` 后 `load_config` 读回一致
- [ ] **Gate**：`python test/test_serial_tool_widget.py` 全绿

## 6. 变异反证（每条：改坏 → 跑 → 断言变红 → 逐字节还原 → md5 比对）

- [ ] ① 去掉校验重算（`apply` 结果直接用原帧的校验字节）→ 期望若干条红
- [ ] ② 不恢复前导 FE（`data_hex` 丢掉 `FE×n`）→ 期望协议 6/8 用例红
- [ ] ③ 无条件覆盖 `match_hex`（不判 `HEX_MATCH_TYPES`）→ 期望通配/正则用例红
- [ ] ④ 修改入参（就地写 `commands[i]["data_hex"]`）→ 期望「入参未被修改」断言红
- [ ] 记录每条的红项数（写进 CHANGELOG 的测试段）
- [ ] **工具卫生**：改源码用 `path.write_bytes(...)`（不是 `write_text`，CRLF 会被翻译毁掉续行）；
      锚点纯 ASCII；还原后 `md5` 逐字节核对

## 7. 冒烟（真实路径，不是测试）

- [ ] offscreen 端到端：构造真实 `SerialToolWidget` → 注入 3 条真帧 → 走 `_on_batch_addr_clicked` 的真实分支（对话框用 `_on_accept`/`values()` 直调）→ 检查表内 HEX、日志、汇总文案
- [ ] 目视（可选但推荐）：默认平台 `QApplication` + `widget.grab()` 存 PNG，确认按钮行没有裁字
- [ ] **Gate**：`python test/test_serial_addr_fix.py` + `test_serial_tool_widget.py` + `test_serial_proto_frame.py` + `test_wakeup_fe_prefix.py`（前导单一来源守卫）全绿

## 8. 文档与版本（**留在工作区，随发版批次提交，不进本任务提交**）

- [ ] `main_gui.py`：`APP_VERSION` `1.23.82 → 1.23.83` + `CHANGELOG` 头部新增条目（功能 + 测试 + 变异反证红项数）
- [ ] AGENTS.md：§8 陷阱 58（串口工具契约）追加「批量替换地址」条目；§8 陷阱 75 的 4 条路径补「批量替换层同样剥/恢复前导」
- [ ] README.md：功能表/模块表补一行
- [ ] `.trellis/spec/frontend/component-guidelines.md`：新增 **§7h 串口工具批量替换地址（复用 `frame_addr_fix`）**（Scope/Signatures/契约/错误矩阵/Good-Base-Bad/测试/变异反证）
- [ ] 两个 `.iss` 版本（`python release_check.py --sync-iss`）

## 9. 门禁与提交

- [ ] `PYTHONIOENCODING=utf-8 python release_check.py --with-gui` → **FAIL=0**（已知环境红：COM1/COM2 回环被运行中的 GUI 占用；`test_modular_iface.py` 偶发 Qt 析构 fastfail）
- [ ] 提交**只含本任务文件**：`serial_tool_widget.py`、`test/test_serial_addr_fix.py`、`test/test_serial_tool_widget.py`、
      `.trellis/spec/frontend/component-guidelines.md`、`.trellis/tasks/10-14-serial-batch-addr/`
      —— **绝不 `git add -A`**（有并发会话在改 `main_gui.py` / `reflex_web/` 等）
- [ ] `release_check.py` 只暂存自己那一行（索引 blob 手术：`git show HEAD:file` → 文本替换 → `hash-object -w` → `update-index --cacheinfo` → `git diff --cached` 复核）
- [ ] 提交信息：`feat(串口工具): 批量替换通信地址（按协议替换地址域 + 重算校验 + 撤销）` + 测试/反证证据 + 「版本与文档留在工作区」
- [ ] 归档后写 journal：**先记功能提交 hash**（`git rev-parse --short HEAD`），再 `task.py archive`，最后 `add_session.py --commit <功能提交 hash>`（archive 会自己产生一个 chore 提交，顺序错了 hash 就错）

## 回滚点

| 阶段 | 回滚方式 |
|---|---|
| 1~2（纯逻辑 + 单测） | 还原 `serial_tool_widget.py` 的纯逻辑 hunk + 删测试文件（无副作用，GUI 未接线） |
| 3~5（GUI + 测试） | 同上 + 删按钮行那一行接线 |
| 6（反证） | 逐条 `write_bytes` 还原 + md5 比对（反证脚本自带 `finally` 还原） |
| 8（文档） | 文档四件套未提交，`git checkout -- <file>` 或手工删条目 |
| 9（提交后） | `git revert <hash>`（只影响本任务文件，不动他人 hunk） |
