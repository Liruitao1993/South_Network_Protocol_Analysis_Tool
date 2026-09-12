# 设计：645虚拟表 事件状态字随机变化

## 架构与边界

```
┌── dlt645_sim/dynamic_data.py（新增，纯逻辑无 Qt）───────────────────────┐
│ EVENT_WORD_DI   = "04001501"      # 主动上报状态字（=模块轮询的"事件状态字"）│
│ EVENT_WORD_BYTES= 12              # BS96 → 12 字节                        │
│ class RandomEventWord:                                                    │
│     __init__(nbytes=12, rng=None)     # rng 可注入（测试播种/碰撞桩）       │
│     next_value() -> str               # 24 位 hex，保证 != 上一次           │
└──────────────────────────────────────────────────────────────────────────┘
        │ next_value()（GUI 持有一个实例 → 跨帧状态在 GUI 侧，不在引擎）
        ▼
┌── dlt645_sim/engine.py（改）───────────────────────────────────────────┐
│ DLT645MeterSim.__init__(..., event_word_source=None)                   │
│ _data_type_for(di) → 优先 dlt645_frame_schema.get_di_info(di)          │
│                      （data_type + length），失败回落既有快表           │
│ _handle_one 11H 分支：                                                 │
│     if di == EVENT_WORD_DI and event_word_source:                      │
│         value = source()          # 绕过档案；异常→回落档案 + last_error │
│         self.last_note = "随机事件状态字"                                │
│     value_bytes = encode_value(value, dt, nbytes=length or None)        │
└────────────────────────────────────────────────────────────────────────┘
        │ 每帧 _make_engine()（串口线程循环内 / 离线每次）
        ▼
┌── dlt645_meter_sim_widget.py（改）─────────────────────────────────────┐
│ 运行页新增「模拟设置」小节（串口从站 与 模块版本查询 之间）               │
│   [ ] 随机产生事件   说明：不勾=档案值(12B 全 0 不变化)；勾=每次读 04001501 │
│                        返回新的随机 12 字节值                          │
│ _make_engine(): event_word_source = self._event_word.next_value         │
│                                    if 勾选 else None                    │
│ 勾选持久化 dlt645_sim_data.json: {"address", "values", "random_event"}   │
│ 日志：随机生效时输出「（随机事件状态字 04001501 = <24hex>）」             │
└────────────────────────────────────────────────────────────────────────┘
        ▼
dlt645_parser / dlt645_data_codec（零改动，只读回验证）
```

**不碰**：`dlt645_parser.py`、`dlt645_data_codec.py`、`dlt645_frame_gen.py`、`dlt645_frame_schema.py`、`dlt645_sim/archive.py` 的类接口（只加一条默认值）、LME 下发链路。

## 契约

### 事件状态字读取应答

| 项 | 值 |
|---|---|
| 请求 | `68 <addr> 68 11 04 <DI 线上序: 01 15 00 04> CS 16`（DI 码 `04001501`） |
| 应答数据域（未加扰） | `01 15 00 04`（DI 线上序）+ **12 字节数据**（BS96） |
| 长度域 | `L = 0x10`（16 = 4 + 12）；**修复前为 0x08（4 字节，缺陷）** |
| 默认值 | 档案 `"04001501": "00"×12` → 应答数据 12 个 `00`，读 N 次完全一致 |
| 随机模式 | 每次读返回 `os.urandom` 级 12 字节新值，且与上一次不同 |

### 纯逻辑 API（`dlt645_sim/dynamic_data.py`）

```python
EVENT_WORD_DI = "04001501"
EVENT_WORD_BYTES = 12

class RandomEventWord:
    def __init__(self, nbytes: int = EVENT_WORD_BYTES, rng=None) -> None
    def next_value(self) -> str          # 24 位大写 hex；保证与上次不同
    def reset(self) -> None              # 清「上次值」（便于测试/切表）
```

- 内部用 `random.Random`（默认自带实例，可用 `rng=` 注入常量桩验证碰撞重抽）。
- 12 字节碰撞概率 2^-96，重抽上限 8 次后放弃保证（返回最后一次）——避免死循环。

### 引擎 API

```python
DLT645MeterSim(address, archive, generator, parser,
               on_address_written=None,
               event_word_source: Optional[Callable[[], str]] = None)
# 新增实例属性
self.last_note: Optional[str] = None     # 每帧重置，GUI 用作日志标注
```

- 仅 11H 读数据分支生效；`di_code != EVENT_WORD_DI` 或 `event_word_source is None` → 走档案（行为不变）。
- `source()` 抛异常 / 返回非法 hex → `last_error = "随机事件状态字产生失败: …"`，回落档案值。

### 持久化

```json
{ "address": "000000000000",
  "values": { "...": "..." },
  "random_event": false }
```

- 写：`_archive_save` / `_archive_save_quiet`；读：`_load_archive_file`；导出/导入：`_archive_export` / `_archive_import`（缺失字段按 `False`，不报错）。

## UI

```
┌ 模拟设置 ─────────────────────────────────────────────────────────────┐
│ [ ] 随机产生事件   每次读取 04001501（主动上报状态字）返回新的随机 12 字节值 │
│                    不勾选时读档案值（默认 12 字节全 0，每次相同）          │
└───────────────────────────────────────────────────────────────────────┘
```

- 位置：`_build_run_tab()` 中「串口从站」组之后、「模块版本查询」组之前。
- `QCheckBox.setChecked(False)` 为默认；`toggled` 直接改 `self._random_event`（无需重启监听：`_make_engine()` 每次读最新值）。
- 勾选/取消时写一行日志说明当前语义。

## 关键取舍

1. **跨帧状态放 GUI 侧（`RandomEventWord` 实例），不放引擎**：引擎每帧重建（串口线程收帧循环内 `_engine_factory()`），放引擎里「保证与上次不同」会失效。备选：模块级单例——被否（测试间串味、多表实例共享）。
2. **「保证与上次不同」而不是纯随机**：用户要求"状态字每次读取都随机变化"；纯随机有 2^-96 概率相同（可忽略），但测试/人工核对时"连续两次一样"会被误判为没生效，故显式保证。
3. **`get_di_info` 作为类型权威**：与 GUI/Web 组帧路径同一数据源（`dlt645_di.json`），避免再维护一份快表；既有快表仅作 DI 表缺失时的兜底。
4. **随机值不写回档案**：避免污染用户档案与「档案数据」页表格（随机值只出现在应答帧与日志）。
5. **默认值取 12 字节全 0 而不是"空"**：全 0 = 无事件，既满足"默认不变化"，又保证不勾选时 11H 读必成功（空值会回 ERR 无请求数据异常，反而不便对照）。

## 兼容 / 回退

- 回退点 1：`DEFAULT_ARCHIVE` 去掉 `04001501` 一条 → 档案恢复原状（引擎/类型修复保留则 DI 缺失走异常应答，与修复前一致的"读不出"）。
- 回退点 2：`_make_engine()` 不传 `event_word_source` → 随机功能整体失效（引擎参数默认 `None`，行为与修复前一致）。
- 回退点 3：`_data_type_for` 保留原探测顺序，仅追加 `get_di_info` 与 `nbytes`——若发现某 DI 回归，`git revert` 单文件即可。
- 持久化新增字段向后兼容：旧 JSON 无 `random_event` → `False`；新 JSON 被旧版本读 → 旧代码忽略未知键。

## 测试（`test/test_dlt645_sim_event_word.py`）

| 组 | 断言点 |
|---|---|
| 引擎默认 | 04001501 应答 `L=0x10`、DI 正确、数据 12 字节全 0；连读 3 次字节完全相同；`DLT645Parser` 读回 12 字节 |
| 引擎随机 | 注入随机源连读 20 次：长度合法、相邻不同、至少一次非全 0 |
| 产生器 | 24 位 hex / 12 字节 / 与上次不同；注入"必定碰撞"桩 → 验证重抽后仍不同 |
| 异常容错 | 源抛异常 → 回落档案、`last_error` 说明、不抛栈 |
| GUI（offscreen） | 小节与勾选框存在、默认不勾；勾选后 `_make_engine().event_word_source is not None`；离线两次「生成响应」响应不同；保存/重载保持勾选 |
| 串口回环（可选） | COM1 监听 + COM2 连发两次读 04001501 → 两次应答数据不同；无串口对则 `[SKIP]` |
| 回归 | `test_dlt645_sim.py` / `test_dlt645_sim_lme_query.py` / `test_dlt645_lme.py` / `test_dlt645_frame_gen.py` / `test_dlt645_frame_gen_gui.py` |
