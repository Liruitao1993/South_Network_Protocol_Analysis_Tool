# 实施计划：645虚拟表 事件状态字随机变化

## 顺序清单（每步可独立验证）

1. **纯逻辑产生器** `dlt645_sim/dynamic_data.py`（新）
   - `EVENT_WORD_DI = "04001501"`、`EVENT_WORD_BYTES = 12`、`class RandomEventWord`（`next_value()` 保证与上次不同，重抽上限 8 次；`rng` 可注入；`reset()`）。
   - `dlt645_sim/__init__.py` 追加导出 `dynamic_data`。
2. **引擎修复 + 随机源**（`dlt645_sim/engine.py`）
   - `_data_type_for` 改为先 `from dlt645_frame_schema import get_di_info` → `info["data_type"]`；同时返回/缓存 `length` 供 `encode_value(nbytes=…)`（把 `_data_type_for` 拆成 `_di_info_for(di) -> (data_type, length)`，保留 `_data_type_for` 兼容旧调用）。
   - `__init__` 增 `event_word_source=None`；`last_note` 每帧重置；11H 分支接入（异常回落档案 + `last_error`）。
3. **档案默认项**（`dlt645_sim/archive.py`）：`DEFAULT_ARCHIVE["04001501"] = "00"*12`（注释：主动上报状态字 / 事件状态字，BS96 12 字节，全 0 = 无事件）。
4. **先跑纯逻辑测试** `test/test_dlt645_sim_event_word.py`（新；`import _path_setup` + utf-8 stdout 兜底 + `check()` 计数）：
   - 引擎默认（L=0x10、12 字节全 0、连续 3 次一致）、引擎随机（20 次相邻不同）、产生器单测与碰撞桩、异常容错。
   - 命令：`python test/test_dlt645_sim_event_word.py`
5. **GUI**（`dlt645_meter_sim_widget.py`）
   - `_build_run_tab()` 在串口从站组后插入 `self._build_sim_settings_group()`（勾选框 + 说明标签）。
   - `__init__`：`self._event_word = RandomEventWord()`、`self._random_event = False`（随后由 `_load_archive_file()` 覆盖）；`_load_archive_file` 读 `random_event` 并同步勾选框。
   - `_make_engine()` 注入 `event_word_source`；`_archive_save` / `_archive_save_quiet` / `_archive_export` 写出 `random_event`，`_archive_import` 读取（缺失按 False）。
   - 日志标注：离线 `_offline_generate` 与串口（`engine.last_note` 经 `frame_exchanged`/日志）在随机生效时输出「（随机事件状态字 0401510… = <24hex>）」。
6. **offscreen GUI 用例 + 串口回环**（并入第 4 步测试文件）
   - offscreen：小节/勾选框存在且默认不勾；勾选 → `_make_engine().event_word_source` 非空；离线连点两次「生成响应」响应不同；保存后新建 widget 仍勾选。
   - 回环（有 COM1/COM2 时）：勾选后经 COM2 连发两次读请求 → 两次应答数据不同；否则 `[SKIP]`。
7. **文档**：`main_gui.py` `APP_VERSION` → `1.23.8` + CHANGELOG 顶部 1.23.8 条目；`python release_check.py --sync-iss`；`AGENTS.md` §3 树补 `dlt645_sim/dynamic_data.py`、§5.4 补事件状态字段、§7 补测试脚本。

## 验证命令（按序）

```bash
set PYTHONIOENCODING=utf-8 && python test/test_dlt645_sim_event_word.py
python test/test_dlt645_sim.py
python test/test_dlt645_sim_lme_query.py
python test/test_dlt645_lme.py
python test/test_dlt645_frame_gen.py
python test/test_dlt645_frame_gen_gui.py
python release_check.py --skip-tests
```

## 风险文件与回退点

| 回退点 | 位置 | 恢复方式 |
|---|---|---|
| R3 后 | `dlt645_sim/dynamic_data.py`、`dlt645_sim/__init__.py` | 删文件与导出（无人依赖） |
| R2 后 | `dlt645_sim/engine.py` | `event_word_source` 默认 None；`_data_type_for` 追加逻辑可单文件 revert |
| R1 后 | `dlt645_sim/archive.py` | 删除 `04001501` 默认项 |
| R5 后 | `dlt645_meter_sim_widget.py` | 移除小节构造调用、`_make_engine` 参数、`random_event` 读写 |
| R7 后 | `main_gui.py` / `AGENTS.md` / 两个 `.iss` | 文本回滚（`--sync-iss` 可再跑） |

不改动的边界（改动即偏离设计）：`dlt645_parser.py`、`dlt645_data_codec.py`、`dlt645_frame_gen.py`、`dlt645_frame_schema.py`、`dlt645_sim/lme_query.py`、698 虚拟表、`reflex_web/`。

## 提交前检查

- [ ] 新测试与 5 个既有 645 测试全过（贴实际输出）
- [ ] 修复前后对照：04001501 应答 `L` 由 `0x08` → `0x10`（贴帧 hex）
- [ ] 随机模式连续 20 次相邻不同（测试断言复现）
- [ ] 运行时数据文件（`dlt645_sim_data.json`）不被测试污染
- [ ] `APP_VERSION`/CHANGELOG/iss/AGENTS.md 同步
