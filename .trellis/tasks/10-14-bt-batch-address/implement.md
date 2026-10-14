# 实现计划：蓝牙工具 · 自定义按钮批量替换地址

## 0. 前置

- 只改 `frame_addr_fix.py` / `bluetooth_tool_widget.py` / 两个测试 + 文档；`bluetooth_core.py` 不动。
- **并发提醒**：本仓库有其它会话在改 `main_gui.py` / `reflex_web/`；本任务不得编辑这两个位置。

## 1. `frame_addr_fix.py`：抽取共享纯逻辑

- [x] 新增 `addr_lengths_for_frame(frame) -> Dict[str, int]`：把 `ButtonEditDialog._addr_lengths` 的逻辑原样搬来
      （`len<12` 或首字节非 `0x68` 或末字节非 `0x16` → `{}`；否则按 698.45 地址特征字节低 4 位算 `sa` 长度）。
- [x] 新增 `check_values(protocol_index, values, frame=b"") -> (ok_items, error_items)`：
      遍历 `fields_for(protocol_index)`，对已填字段调 `parse_address(text, spec, lengths.get(key, spec.length))`；
      `err and spec.kind == KIND_SA698 and "sa" not in lengths` → 回显「长度按帧内确定」（不报错）；
      未填字段跳过；返回两组可读字符串（`ok_items` 用「· 标签：说明」，`error_items` 用「⚠ 标签：原因」）。
- [x] 纯逻辑自测：`python -c "import frame_addr_fix as f; ..."` 快速验证两个函数（随后写进测试）。

## 2. `bluetooth_tool_widget.py`：对话框 + 接线

- [x] `ButtonEditDialog`：
      - [x] 删本地 `_addr_lengths` staticmethod，改调 `frame_addr_fix.addr_lengths_for_frame`；
      - [x] `_refresh_addr_hint()` / `_check_addr_on_accept()` 的逐字段循环改调 `frame_addr_fix.check_values`
            （**文案逐字符不变**：`· 标签：说明` / `⚠ 标签：原因` / 「长度按帧内确定」）；
      - [x] 跑 `test_bluetooth_widget.py` 的 `[13]` 段确认零回归（这一步必须在写新对话框**之前**做）。
- [x] 新增 `BatchAddressDialog(QDialog)`（放在 `BatchButtonDialog` 之后）：
      - [x] 协议下拉（第 0 项「（清除协议与地址）」，data=None）+ 说明标签；
      - [x] 列表（`QListWidget` + 勾选）+「全选 / 全不选 / 只选本协议」三个小按钮；
      - [x] 地址输入行（按协议动态重建 + `lbl_addr_hint` 实时回显，复用 §1 的 `check_values`）；
      - [x] `_precheck()` 逐按钮用自己的帧预检（报文解析 → `addr_lengths_for_frame` → `check_values` →
            `frame_addr_fix.apply`），把结果写进行文本后缀与行 tooltip，失败项默认不勾；
      - [x] `_on_accept()`：无勾选 / 未填地址（非清除模式）→ 提示并留在对话框；
            有失败项被勾选 → `QMessageBox.question` 二次确认（列出跳过项），拒绝则 return；
      - [x] `result_patches()` 返回 `{index: {"protocol": int|None, "addr": dict}}`。
- [x] 工具栏（`_build_custom_group`）：加 `btn_custom_batch_addr = QPushButton("批量地址…")`
      （`set_btn(..., "secondary", "sm")` + `set_btn_icon(..., "apply")`），紧挨「批量新增…」之后；
      删掉行内提示标签（理由见 design §6.4），`fit_btn_width(...)` 加入新按钮。
- [x] `_on_custom_batch_address()`：
      - [x] 无按钮 → 提示「先新增按钮」；否则打开对话框（`current_protocol` 取 `self._protocol_provider()`，异常回落 None）；
      - [x] 拿到 patches 后：拷 `list(self._buttons)`，逐项写 `protocol`/`addr` 或删两键；
      - [x] `_set_buttons(buttons, announce)`：announce = `[地址] 批量替换：<协议名> · N 个按钮（源=… 目的=…）`
            或 `[地址] 批量清除绑定：N 个按钮`；被跳过项逐条 `self._log(..., "warn")`。

## 3. 测试

- [x] `test/test_bluetooth_addr_fix.py`（现 96 项）新增：
      - `addr_lengths_for_frame`：合法 698.45 帧（地址特征字节 → SA 长度）、短帧/首末字节不符 → `{}`；
      - `check_values`：全对、长度不符、非法字符、空值跳过、SA 无帧长度时「按帧内确定」；
      - 与 `apply()` 的一致性：`check_values` 无错 ⇔ `apply()` 成功（对同一帧/同一组值抽样）。
- [x] `test/test_bluetooth_widget.py` 新增 `[16]` 段：
      - [x] 对话框直测：协议下拉项来自 `supported_choices`；默认勾选 = 已绑定本协议；
            「只选本协议」/「全不选」；清除模式隐藏地址区；未填地址点确定被拒；
            坏 HEX 按钮默认不勾且行内标 ⚠；强行勾上 → 二次确认（打桩 `QMessageBox.question`）→ 跳过；
            `result_patches()` 形状（含清除模式的 `protocol=None`）；
      - [x] 端到端：`tab.btn_custom_batch_addr.click()`（打桩对话框返回值）→ tooltip 更新、`_buttons[i]` 有键、
            日志汇总、`_schedule_save` 后新页面读回；
      - [x] 清除绑定端到端：导出 JSON 里不再有 `protocol`/`addr` 键，点按钮发送的字节 = 原始内容（逐字节）；
      - [x] 按钮宽度判据（陷阱 63）：`show()` 后 6 个按钮 `width >= sizeHint`（10 / 14 / 16 号字各量一次）。
- [x] `[14]` 段（空间治理）与 `[13]` 段（单按钮地址）必须保持全绿。

## 4. 验证命令

```bash
PYTHONIOENCODING=utf-8 python test/test_bluetooth_addr_fix.py
PYTHONIOENCODING=utf-8 python test/test_bluetooth_widget.py
PYTHONIOENCODING=utf-8 python test/test_bluetooth_core.py
PYTHONIOENCODING=utf-8 python test/test_bluetooth_worker.py
PYTHONIOENCODING=utf-8 python test/test_bluetooth_tab_wiring.py
PYTHONIOENCODING=utf-8 python -c "import frame_addr_fix, bluetooth_tool_widget"   # 语法/导入
bash: 用 pwsh 包一层跑 release_check.py --with-gui（陷阱 62）
```

## 5. 冒烟（offscreen 子进程，勿在长驻内核里 import 模块 —— 会命中 sys.modules 旧对象）

- [x] 造 20 个南网按钮 + 3 个 645 按钮 + 1 个坏 HEX 按钮：批量替换地址 → 打印每个按钮的 tooltip/键值；
      对照「不勾坏按钮」与「强行勾上」两条路径的日志。
- [x] 清除绑定 → 打印导出 JSON 键集合 + `worker.sent` 逐字节对照。

## 6. 变异反证（≥3 条，逐条实测变红 + 逐字节还原 md5 一致）

1. 默认勾选改成「全勾」→ 坏 HEX 按钮被默认勾上（应有断言变红）。
2. 「只选本协议」实现改成全选 → 红。
3. 跳过失败项时不弹二次确认（静默跳过）→ 红。
4. 清除模式只删 `protocol` 不删 `addr` → 红（导出 JSON 残留）。

## 7. 文档与提交（Phase 3）

- [x] spec：`.trellis/spec/frontend/component-guidelines.md` 新增 `7h. 蓝牙自定义按钮的批量地址替换`（含 §6 取舍与实测宽度）。
- [x] AGENTS：陷阱 69 的蓝牙契约条目追加批量地址一节（默认作用域 / 二次确认 / 逐按钮用自己的帧校验）。
- [x] README：蓝牙功能条目 + 更新记录；`main_gui.py`：`APP_VERSION` → `1.23.83` + CHANGELOG 条目 + `BUILD_DATE`。
- [x] 提交：**只提交本任务文件**（`frame_addr_fix.py` / `bluetooth_tool_widget.py` / 两个测试 / spec / 任务产物）；
      版本与文档四件套（`main_gui.py`、`AGENTS.md`、`README.md`、两个 `.iss`）留在工作区随发版批次。
- [x] `task.py archive` + `add_session.py --commit <真实 hash>`。

## 8. 完成情况（2026-10-14）

- 全部步骤已完成；测试：`test_bluetooth_addr_fix.py` 111 项、`test_bluetooth_widget.py` 268 项（全绿）。
- 变异反证 4 条逐条实测变红（9 / 5 / 2 / 1 项）后逐字节还原（md5 一致）。
- 文档：spec §7i、AGENTS §3 + 陷阱 69、README 功能表 + 1.23.84、main_gui APP_VERSION 1.23.84 + CHANGELOG。
- 版本取 1.23.84：1.23.83 已被并行的「串口工具批量替换通信地址」占用。
