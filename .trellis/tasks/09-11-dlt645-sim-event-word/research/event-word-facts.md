# Research：事件状态字（04001501）事实与实测缺陷证据

- **日期**：2026-09-11
- **来源**：`dlt645_di.json`（DI 表）、`DLT645-2007.md` 附录C、`山东和兑智能.txt`（真实 645 抓包）、本会话实测引擎行为

## 1. 「事件状态字」到底是哪个 DI

`dlt645_di.json` 中 `BS96`（=12 字节）的状态字只有两条：

| DI | 名称 | data_type | length |
|---|---|---|---|
| `04001501` | 主动上报状态字 | BS96 | 12 |
| `04001503` | 复位主动上报状态字 | BS96 | 12 |

`04000501~04000507` 电表运行状态字 1~7 为 `BS32` / 4 字节（`DLT645-2007.md:1660-1719` 附录C 逐字给位定义）。

**语义印证**：`协议文档/7.国网本地接口协议/附件1.md:214`「模块检测到引脚有事件时，**主动读取电能表的事件状态字**上报给集中器」→ 模块侧轮询的「事件状态字」即 `04001501`。用户确认取该 DI、12 字节。

## 2. 真实抓包：模块正在反复轮询 04001501

`山东和兑智能.txt`（2026-06-25，约每 20~30 秒一次，L577/677/777/877 四处相同）：

```
316) 接收： 长度=16, 数据=68 33 00 00 00 00 00 68 11 04 34 48 33 37 FE 16
		0-智能电能表 请求地址[1]：000000000033
		参数：04001501，数据：010000000000000000000000AA01AA
318) 发送： 长度=31, 数据=68 33 00 00 00 00 00 68 91 13 34 48 33 37 DD 34 DD 33 33 33 33 33 33 33 33 33 33 33 34 E0 16
```

- 请求数据域去扰：`34 48 33 37` − 0x33 → `01 15 00 04` → DI 码 **04001501** ✓
- 应答：`L=0x13=19 = DI 4 + 数据 15`；去扰后 `01 15 00 04 | AA 01 AA 00×11 01`。**该表数据 15 字节**（厂商扩展），与本仓库 DI 表的 `BS96=12` 不一致 → 本任务按 12 字节实现（用户确认），15 字节记入风险项。

## 3. 本会话实测：当前虚拟表对 04001501 的应答是错的

```python
sim = DLT645MeterSim(address="000000000033", archive=DLT645Archive({"04001501": "00"*12}))
sim.handle_frame(bytes.fromhex("6833000000006833110434483337FE16".replace("6833","68 33")))  # 略
```

实测输出：

```
data_type_for: None              # ← 缺陷根因
rsp: 68 33 00 00 00 00 00 68 91 08 34 48 33 37 33 33 33 33 4E 16
                                    ^^ L=0x08 → 只有 4 字节数据（应为 0x10 = 4+12）
parser: 数据值 = 00000000（4 字节），说明「主动上报状态字；格式BS96」
```

**根因**：`engine._data_type_for` 依次探测 `get_info` / `get` / `lookup`，而 `dlt645_di_lookup.DLT645DILookup` 的真实方法名是 **`get_di_info`**（`dlt645_di_lookup.py:112`）→ 全部探测失败 → 回落快表（无此项）→ `None` → `encode_value(value, "XXXXXX.XX")` 编成 4 字节。

**正确数据源**：`dlt645_frame_schema.get_di_info("04001501")` → `{'name': '主动上报状态字', 'unit': '', 'data_type': 'BS96', 'length': 12}`（实测）。组帧路径 `_encode_di_value` 已用 `nbytes=info["length"] or nbytes`，引擎应对齐同一口径。

## 4. 编码/解析口径

- 编码：`dlt645_data_codec.encode_value(value, "BS96", nbytes=12)` → `parse_hex(value, 12)`；档案值应为 **24 位 hex**（12 字节）。
- 解析：`decode_value(data, "BS96", di_name="主动上报状态字")` → 位串展开（`dlt645_data_codec.py:140-144` 仅对含「状态字」的名称走附录C位表；`主动上报状态字` 无位表 → 走通用位串 hex 展开）。
- 本会话实测：修好类型后应为 `L=0x10`、12 字节数据，`dlt645_parser` 读回 12 字节。

## 5. 引擎生命周期（决定随机状态放哪）

- 串口线程在收帧循环内**每帧**新建：`engine = self._engine_factory()`（`dlt645_meter_sim_widget.py:118`）。
- 离线路径每次点按钮新建：`_offline_generate` → `self._make_engine()`。
- `_make_engine()` 读的是 `self.address` / `self.archive` /（本次新增）`self._event_word`。
- ⇒ 「保证与上次随机值不同」的状态**必须由 GUI 持有的对象承载**（`RandomEventWord` 实例），放引擎实例上必然失效。

## 6. 持久化现状

`dlt645_sim_data.json` = `{"address": str, "values": {DI: value}}`；写：`_archive_save`（有日志/弹窗）与 `_archive_save_quiet`（15H 写地址后静默）；读：`_load_archive_file`；导出/导入：`_archive_export` / `_archive_import`。`DLT645Archive.__init__` 先铺 `DEFAULT_ARCHIVE` 再用入参覆盖 → 往默认表加一项对老档案自动生效。
