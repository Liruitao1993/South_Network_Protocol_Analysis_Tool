# 设计：测试帧摘要体现测试模式

## 1. 边界

**修改**
- `main_gui.py`：
  - 新增 `MainWindow._extract_test_mode_content(table_data) -> str`（`@staticmethod`，纯函数，供协议9/10/11 摘要共用）；
  - `_extract_csg_core_content`：新增**首个分支**——测试帧优先返回测试模式内容；
  - `_get_gw_new_gen_summary`：末尾追加测试模式片段（非空时）。
- `test/test_csg_summary.py`：去掉文件内复刻的摘要逻辑，改为调用 `main_gui.MainWindow` 未绑定方法 + 新增测试帧用例。
- `test/test_gw_monitor_summary.py`：新增检测扩展命令（测试模式）用例。
- `main_gui.py:CHANGELOG`、`AGENTS.md`、`README.md`（功能描述）。

**不动**：解析器（`csg_new_gen_*` / `gw_new_gen_*`）字段名与语义、摘要表格结构、其它帧类型摘要分支、协议注册表。

## 2. 关键决定

| 决定 | 理由 |
|---|---|
| 提取逻辑放 `main_gui.MainWindow` 的 **staticmethod** | 摘要逻辑已在 `main_gui`（两个 `_get_*_summary` 是 MainWindow 方法）；staticmethod 不触碰 `self` → 测试可 `MainWindow._extract_test_mode_content(rows)` 直接调用，无需 QApplication（沿用 `test_gw_monitor_summary.py` 范式），避免新建模块或复制实现 |
| 协议9 走 `_extract_csg_core_content` 的**首个分支** | 测试帧的帧类型域是「命令帧」，若不提前返回，会落到通用「命令帧」分支拼出一堆无关字段（设备地址、转发数据长度…），测试模式信息丢失 |
| 协议10/11 在既有片段**之后追加** | 国网新一代摘要以网络层/应用层关键字段为主线（NID/MMTYPE/端口/报文ID…），测试模式是补充信息，追加不破坏既有顺序与断言 |
| 协议9 用「业务标识=240/0xF0」判定，协议10 用「字段存在性」判定 | 协议9 有明确的 0xF0 测试帧业务标识；协议10 的检测扩展命令挂在通信测试报文下（无 0xF0 概念），只能按解析产出的字段判定 |
| 无 `测试模式/配置操作` 的测试帧回退到 `测试ID`/`扩展ID`/`通信频段` | 真实抓包帧（`test_csg_batch_parse_level.py` 的 TCP 帧）就是这种：`测试ID=2 频段切换命令`，没有测试模式字段；若不回退，该帧摘要仍是一片空白 |

## 3. 契约

```python
@staticmethod
def _extract_test_mode_content(table_data: list) -> str:
    """测试帧/检测扩展命令 → 摘要片段（非测试类报文返回空串）。

    输入: table_data 行元组 (字段名, raw, parsed, comment, start, end[, is_child])
    输出: 形如
        "测试模式:PLC物理层透传测试模式(3)"
        "测试模式:安全测试模式(13) | 安全测试模式:SHA256签名"
        "测试ID:频段切换命令 | 通信频段:0x02"
        "测试帧上行（确认/否认，无数据单元）"
        ""（无任何测试模式痕迹）
    """
```

字段消费表（按优先级；**名称/数值双槽探测**，见下）：

| 行名（去缩进后精确匹配） | 取值 | 片段 |
|---|---|---|
| `测试模式/配置操作` | 名称=parsed 非数值则 parsed 否则 comment；数值=parsed/raw 中的数值者 | `测试模式:{名称}({数值})`（名称自带括号时省略数值） |
| `安全测试模式` | 同上 | `安全测试模式:{名称}` |
| `新一代测试模式` | 同上（如 `CCO信标机制切换`） | `新一代测试模式:{名称}` |
| `测试ID` | 同上（仅当无 `测试模式/配置操作` 时） | `测试ID:{名称}` |
| `扩展ID` | 同上（仅当无 `测试模式/配置操作` 时） | `扩展ID:{名称}` |
| `测试数据区` | comment 含 `通信频段` 时取 `0x..` | `通信频段:0x02` |
| `上行负载`（且表内 `业务标识` 自证为测试帧） | — | `测试帧上行（确认/否认，无数据单元）` |

- 行名匹配统一 `str(name).strip()`（协议10 的 table_data 有缩进/子行）。
- 占位行过滤：comment 含「仅测试模式」的（协议9 表61 恒定输出的 `安全测试模式（仅测试模式13生效）`）跳过。
- 空值兜底：名称候选为空 → 只输出字段名；数值缺失 → 只输出 `测试模式:{名称}`。
- **不做描述文本黑名单**：早期版本用黑名单剔除描述串（如「标识不同的安全测试模式」），漏掉模式15 的描述句导致 `新一代测试模式` 取到描述而不是子模式名；改为「非数值者即名称」的槽位探测后，两个协议与所有模式（0~15）统一收敛。

**协议9 判定**（在 `_extract_csg_core_content` 内）：`业务标识` 行 parsed 值 == `240`，或 raw 含 `F0`，或 comment 含 `测试帧`。判定成立后调用 helper；helper 返回空串时**继续走原有分支**（保持兜底行为）。

**协议10/11 接入**：`parts.append(text)`（非空时），位置在既有片段之后、`return " | ".join(parts)` 之前。

## 4. 测试设计

`test/test_csg_summary.py`（重构 + 新增）
- 删除文件内 `get_csg_new_gen_summary` / `extract_csg_core_content` 复刻，改为：
  ```python
  class Host:
      _get_csg_new_gen_summary = main_gui.MainWindow._get_csg_new_gen_summary
      _extract_csg_core_content = main_gui.MainWindow._extract_csg_core_content
  ```
- 保留既有 6 个断言语义（确认帧/否认帧/管理消息/TEI列表/可读性/完整MAC帧 MSDU 类型），改用真实方法验证。
- 新增：
  1. 真实抓包 0xF0 帧（TCP EDA5 帧剥 15 字节 → `CSGNewGenParser().parse_to_table(app)`）→ 摘要含 `业务标识:测试帧(0xF0)` + `测试ID:频段切换命令`；
  2. 构造 1.0 测试帧 payload（`测试ID=3` + 表61 8 字节数据区，`测试模式=3`）→ `parse_command_payload(..., service_id=0xF0)` 出真实行 → 摘要含 `测试模式:PLC物理层透传测试模式(3)`；
  3. 上行测试帧（`parse_command_payload(..., direction=1)`）→ 摘要含 `测试帧上行`；
  4. 非测试帧调用 helper 返回空串（确认帧 table_data）。

`test/test_gw_monitor_summary.py`（新增）
- 构造检测扩展命令 payload（`协议版本/头长度` 字节0、`测试模式=3` 在字节1高4位、字节2/3 配置值、字节4/5 保留）→ `gw_new_gen_cmd_payloads._parse_comm_test(payload, 0, 0)` 出行 → `Host._get_gw_new_gen_summary(rows)` 含 `测试模式:HPLC物理层透传测试模式(3)`；
- 模式 13 额外含 `安全测试模式:`。

## 5. 兼容性 / 回滚

- 纯增量：新增 staticmethod + 两处接线；非测试帧路径不变（协议9 仅在业务标识=测试帧时走新分支；协议10 仅在 helper 非空时追加）。
- 回滚：删 helper、两处接线与新增测试即可。
- 无 GUI 结构变化，无打包变化（无新文件、无新依赖）。
