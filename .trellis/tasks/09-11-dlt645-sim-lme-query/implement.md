# 实施计划：645虚拟表 LME 模块版本查询下发

## 顺序清单（每步可独立验证）

1. **纯逻辑模块** `dlt645_sim/lme_query.py`（新）
   - 常量：`QUERY_SINGLE_STA/QUERY_DUAL_STA/SET_DUAL_STA`、DI 依赖 `lme_info_entry_parser.DI_STA_VERSION_SINGLE/DI_DUAL_ENTRY`。
   - `parse_entry_items(text)`（`分类/数据ID` → `[(cat,id)]`）、`parse_set_items(text)`（`分类/数据ID:hex` → `[(cat,id,bytes)]`）。
   - `build_single_sta_query` / `build_dual_query` / `build_dual_set` / `build_query(kind,...)` / `decode_reply(frame)` / `reply_rows(parsed)`。
   - `dlt645_sim/__init__.py` 导出（`DLT645MeterSim` 既有导出不动）。
   - 校验与中文异常见 design「错误信息」。
2. **测试（先跑纯逻辑）** `test/test_dlt645_sim_lme_query.py`（新；`import _path_setup` + utf-8 stdout 兜底 + `check()` 计数风格）
   - 4.2 golden 逐字节；4.6 M=0/M=1 数据域断言 + 解析回读；4.7 TLV 编码/长度/超限报错/格式错；`decode_reply` 对手册 §5.1.1 接收示例（123B）。
   - 命令：`set PYTHONIOENCODING=utf-8 && python test/test_dlt645_sim_lme_query.py`
3. **串口线程回包**（`dlt645_meter_sim_widget.py`）
   - `Dlt645SerialSlaveThread.slave_frame = Signal(str)`；`run()` 中按 `ctrl & 0x80` 分流（DIR=1 → emit + 日志，DIR=0 → 原引擎路径）；`_toggle_serial` 处连接信号。
   - 回归：既有 `test/test_dlt645_sim.py`（引擎不变）应全过。
4. **GUI 分组**（同文件）
   - `_build_run_tab()` 中在「串口从站」与「离线模拟」之间插入 `_build_lme_query_group()`：目标地址 `QLineEdit`（默认 `AAAAAAAAAAAA`）+ 三个一键按钮（`读模块版本(4.2)` / `读内部详细信息(4.6)` / `设置(4.7)`）+ 一行「条目」`QLineEdit`（4.2 隐藏清空）+ 只读帧框（等宽 NoWrap）+ `下发到串口` / `复制hex`。
   - 处理函数：`_lme_read_version` / `_lme_read_dual` / `_lme_set_dual`（三者共用 `_lme_build_and_maybe_send(kind)`：组帧→填帧框→日志→已监听则下发，未监听仅日志）/ `_lme_send_frame`（重发帧框内容）/ `_lme_copy` / `_on_slave_frame(hex)`（parse → `_fill_resp_table` + 日志）。
   - 4.7 走 `QMessageBox.question` 确认（列出 `分类c/数据d 名称`），取消则帧框保留、不下发；4.7 的 `_lme_send_frame` 同样确认。
   - 条目框 hint/tooltip 随当前按钮切换（`分类/数据ID` 留空=读全量 ↔ `分类/数据ID:hex数据`）。
   - 组帧失败（地址/条目格式/长度>31）走 `QMessageBox.warning`，不覆盖帧框、不下发。
5. **离线 DIR=1 直解**：`_offline_generate` 开头判断 `ctrl & 0x80`（帧足够长时）→ `_on_slave_frame(hex)` + 日志「检测到从站回包，直接解析」并 return；DIR=0 走原路径。
6. **offscreen GUI 用例 + 串口回环用例**（并入第 2 步测试文件）
   - offscreen：控件存在/显隐、生成结果非空、未监听提示、slave_frame→结果表、离线 DIR=1→结果表。
   - 回环（可选，检测 COM1/COM2 是否都存在；不存在则跳过并打印）：widget 监听 COM1 → 测试端 `serial.Serial("COM2")` 读生成帧 → 写回手册接收示例 → 断言结果表出现解析行。
7. **文档**：`main_gui.py` 顶部 `CHANGELOG` 加 **1.23.7** 条目（1.23.6 已被云母主题占用）并 bump `APP_VERSION = "1.23.7"`；`AGENTS.md` §3 树补 `dlt645_sim/lme_query.py`、§7 测试清单补 `test/test_dlt645_sim_lme_query.py`。

## 验证命令（每次改动后按序跑）

```bash
set PYTHONIOENCODING=utf-8 && python test/test_dlt645_sim_lme_query.py
python test/test_dlt645_sim.py
python test/test_dlt645_lme.py
python test/test_dlt645_frame_gen.py
python test/test_dlt645_frame_gen_gui.py
```

（本机 Python 3.13 + PySide6；GUI 用例一律 offscreen：`QT_QPA_PLATFORM=offscreen`。）

## 风险文件与回退点

| 回退点 | 位置 | 恢复方式 |
|---|---|---|
| R1 后 | `dlt645_sim/lme_query.py`、`dlt645_sim/__init__.py` | 删除导出与文件（其余代码未依赖） |
| R3 后 | `dlt645_meter_sim_widget.py`（新增分组/信号/处理函数） | 移除分组构造调用、`slave_frame` 连接与信号定义；DIR=0 路径未改 |
| R5 后 | `main_gui.py:CHANGELOG`、`AGENTS.md` | 删除条目（纯文本） |

不改动的边界（改动即偏离设计）：`dlt645_parser.py`、`lme_info_entry_parser.py` 既有函数签名、`dlt645_frame_schema.py`、`dlt645_frame_gen.py`、`dlt645_sim/engine.py`、`reflex_web/`。

## 提交前检查

- [ ] 新测试与 4 个既有 645 测试全过（贴出实际输出）
- [ ] 4.2 golden 帧与手册 §5.1.1 示例逐字节一致（测试断言即可复现）
- [ ] 4.7 未确认时串口无写入（测试/手工核对日志无 `⇱ 已下发`）
- [ ] CHANGELOG / AGENTS.md 已更新；`git status` 无运行时数据文件（`dlt645_sim_data.json`）被误提交
