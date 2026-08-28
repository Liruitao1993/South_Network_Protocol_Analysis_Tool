# Design — 协议0本地通信模块接口协议核心完善

## 变更边界

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `protocol_parser.py` | 修改 | DI_COMBINATION_MAP +15 条；DI 分派表（~L1098）+新解析函数；修 4 处冲突 |
| `frame_generator_schema.py` | 修改 | DI_FIELD_SCHEMA +8 个下行条目 |
| `test/test_nw_lcmi.py` | 新增 | 回归测试（含 `import _path_setup`） |
| `main_gui.py` | 修改 | APP_VERSION bump + CHANGELOG 条目 |
| `AGENTS.md` | 修改 | §5.1 文档映射、§10 变更日志、§11 摘要 |
| `protocol_tool.py` / `send_frame_lib.py` / `validator/nw_validator.py` | **不改** | 帧骨架/校验与新文档完全一致 |

## 现有契约（实现必须遵守）

1. **DI 名称表**：`DI_COMBINATION_MAP: Dict[Tuple[int,int,int,int], str]`（protocol_parser.py L518+），
   键为 (DI3, DI2, DI1, DI0) 原始字节值。查询页 `_load_di_map_data` 直接读此表。
2. **深度解析分派**：protocol_parser.py ~L1098 的 dict `{(0xE8,...): self._parse_xxx_data}`，
   函数签名 `_parse_xxx_data(self, data: bytes) -> Dict[str, Any]`，返回嵌套 dict，
   键名用中文（§4.2：原始值/十进制/解析值/说明），列表型数据逐项展开。
3. **组帧 schema**：`DI_FIELD_SCHEMA: Dict[Tuple[int,int,int,int], Dict]`
   （frame_generator_schema.py L20+），条目含 `doc`（HTML 说明）、`direction="down"`、
   `fields=[...]`（字段类型参照现有条目：uint8/uint16 小端、bytes、bcd、ascii、list、
   length_field、enum 等）。组帧核心 `protocol_tool.py::Frame.build()` 支持任意 DI，无需改。
4. **字节序**：多字节字段一律小端（`int.from_bytes(x, 'little')` 显式写参）；
   地址 6B 显示时反转（沿用现状）；BCD 时间 6B = 秒分时日月年。
5. **容错显示原则**（AGENTS.md §8-23）：数据不足/声明不符时 `valid=False` + `⚠` 行，
   仍尽力解析可见字段，禁止返回空白。

## 新增解析（15 个 DI）

按文档行号取字段定义（`协议文档/0.南网协议/13 计量自动化终端本地通信模块接口协议.md`）：

| DI | 名称 | 文档锚点 | 数据内容要点 |
|---|---|---|---|
| E8 02 04 A0 | 设置即插即用功能开关 | L1678 | 开关状态 2B BIN |
| E8 02 04 A1 | 添加黑名单节点 | L1691 | 数量 1B + 地址 6B×n |
| E8 02 04 A2 | 删除黑名单节点 | L1705 | 数量 1B + 地址 6B×n |
| E8 02 04 A3 | 设置CCO时钟 | L1719 | BCD 6B（秒分时日月年） |
| E8 03 03 15 | 批量查询模块特征信息 | L1122 | 按文档字段（实现时读原文） |
| E8 03 03 16 | 查询指定模块特征信息 | L1138 | 按文档字段 |
| E8 03 03 A0 | 查询即插即用功能开关 | L1156 | 无内容 |
| E8 03 03 A1 | 查询黑名单节点信息 | L1160 | 按文档字段 |
| E8 04 03 15 | 批量返回模块特征信息 | L1481 | 列表逐项展开 |
| E8 04 03 16 | 返回指定模块特征信息 | L1510 | 按文档字段 |
| E8 04 03 A0 | 返回即插即用功能开关 | L1538 | 开关状态 |
| E8 04 03 A1 | 返回黑名单节点信息 | L1549 | 列表展开 |
| E8 05 05 A0 | 上报未识别节点信息 | L1836 | 按文档字段 |
| E8 05 05 11 | 上报组合多帧任务数据 | L1851 | 任务ID 2B + 报文长度 **2B** + 内容 |
| E8 05 05 12 | 上报从节点事件扩展 | L1879 | 长度 **2B** + 内容 |

实现时先读对应 md 行号确认字段表，再写解析函数；不确定的字段在代码中标注文档行号。

## 冲突修正（4 处，容错兼容策略）

1. **返回未完成任务列表**（`_parse_return_incomplete_task_list_data` L1372）：
   双格式自动检测——数据前 2B 小端值 n 满足 `2 + 2*n == len(data)` 时按新文档格式
   （数量 2B + ID 2B×n）；否则回退现有 PLUZ 格式（总数2B+返回数1B+列表）。
2. **添加多播任务**（`_parse_add_multicast_task_data` L1460）：任务模式字 bit4(D4)=1
   时报文长度读 2B，否则 1B（对齐添加任务的既有自动检测做法）。
3. **启动/暂停任务**（`_parse_start_task_data`/`_parse_pause_task_data` L1518-1534`）：
   数据为空时不生成字段行（文档定义无内容）；数据≥2B 时仍解析任务ID（PLUZ 兼容）。
4. **任务模式字位定义**（`_parse_add_task_data` L1259+）：保留现有 D6=转发标识
   （标注 PLUZ 扩展），新增显示 D4=组合多帧标志；优先级维持现有低 3 位显示，
   说明中补充「新文档定义为 D3~D0 4位」注释，不改数值提取以免破坏存量帧显示。

## 组帧新增（8 个下行 DI）

E8 02 04 A0（开关 2B BIN）/ A1（数量+地址列表，list 字段复用添加从节点模式）/
A2（同 A1）/ A3（BCD 6B 时间，参照现有时间字段 bcd_time 类型）；
E8 03 03 15 / 16 / A0（fields 为空或按文档查询参数）/ A1。
每条含 `doc` HTML（复制文档表格语义）。组帧产物由 `Frame.build()` 自动算长度域/CS。

## 测试设计（test/test_nw_lcmi.py）

- 每个新 DI：手工构造最小合法帧（68 L C 地址 DI 内容 CS 16）→ parse → 断言关键字段名/值
- 8 个组帧 DI：使用南网 `ProtocolFrameGenerator`（send_frame_lib）
  按 schema 组帧 → 解析器回读 → 断言 DI 名称与字段一致（round-trip）
- 冲突点双格式用例：新文档格式帧 + PLUZ 旧格式帧各断言
- 存量回归：NW_command.json 的 14 条预设帧解析结果关键字段不回归
- 文件头 `import _path_setup`；直接 `python test/test_nw_lcmi.py` 运行

## 兼容性与回滚

- 全部修改向后兼容（双格式检测/条件解析），存量 PLUZ 实测帧行为不变
- 单一功能提交；如回归发生，revert 该提交即可，无数据迁移/配置变更
