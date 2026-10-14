# 设计：蓝牙工具 · 自定义按钮批量替换地址

## 1. 模块边界

| 文件 | 改动 | 说明 |
|---|---|---|
| `frame_addr_fix.py` | **+2 个纯函数** | `addr_lengths_for_frame(frame)`、`check_values(protocol, values, frame)` —— 把现在只活在界面里的「按帧定地址长度 + 逐字段解析校验」收进纯逻辑层（单一来源） |
| `bluetooth_tool_widget.py` | 新增 `BatchAddressDialog`；`ButtonEditDialog` 的三段地址逻辑改调共享函数；工具栏加 1 个按钮；新增 `_on_custom_batch_address()` | 界面只做「收集作用域 + 展示预检结果 + 写回按钮列表」 |
| `bluetooth_core.py` | **不动** | 按钮字典结构不变；无新增配置键 ⇒ `CONFIG_VERSION` 不变 |
| `test/test_bluetooth_addr_fix.py` | +纯逻辑用例 | `addr_lengths_for_frame` / `check_values` 的边界（SA 长度来自帧、非法长度、空值） |
| `test/test_bluetooth_widget.py` | +`[16]` 段 | 对话框直测 + 端到端 + 落盘往返 |

不动的：`_apply_button_address`（发送时替换）、`frame_addr_fix.apply`（帧级替换）、导出/导入、空间治理。

## 2. 共享纯逻辑（先抽取，避免第二份实现）

现状（1.23.81）：`ButtonEditDialog` 里有三段重复的地址处理
——`_addr_lengths()`（staticmethod，由帧推 698.45 的 SA 长度）、`_refresh_addr_hint()`、`_check_addr_on_accept()`。
批量对话框要的是同一套判据，因此先搬到 `frame_addr_fix`：

```python
def addr_lengths_for_frame(frame: bytes) -> Dict[str, int]:
    """由帧内容决定的地址长度（当前只有 698.45 的 SA：地址特征字节低 4 位 + 1）。
    帧不合法/不足 → {}（调用方回落到字段声明长度）。"""

def check_values(protocol_index, values, frame: bytes = b"") -> Tuple[List[str], List[str]]:
    """逐字段解析并给出 (可读回显项, 错误项)。
    - 未填的字段跳过；
    - 698.45 的 SA 在「帧里拿不到长度」时不算错（回显「长度按帧内确定」）—— 这是既有界面的口径；
    - 其余非法一律进错误项（含长度不符、字符非法）。"""
```

两个函数都是纯逻辑、零 Qt、可单测；`ButtonEditDialog` 改为调用它们（**行为与文案逐字符不变**，由既有
`[13]` 段 + `test_bluetooth_addr_fix.py` 守）。

## 3. 对话框契约 `BatchAddressDialog(QDialog)`

```python
BatchAddressDialog(parent, buttons: List[dict], current_protocol: Optional[int] = None)
```

| 属性/方法 | 契约 |
|---|---|
| `combo_protocol` | 第 0 项 `("（清除协议与地址）", None)`，其余来自 `frame_addr_fix.supported_choices()`；初值 = `current_protocol`（拿不到则第 0 项） |
| `list_buttons` | `QListWidget`，一行一个按钮（ItemIsUserCheckable）；文本 = `名称　—　现状摘要`；`UserRole` 存按钮下标 |
| `_rebuild_rows()` | 重建列表并把「已绑定所选协议」的行设为勾选（切协议/切模式后重算；用户在本次会话里手改的勾选不跨模式保留 —— 简单可预期） |
| `_addr_edits` | `{字段 key: QLineEdit}`，按协议动态重建（与 `ButtonEditDialog` 同款实现，字段声明取自 `frame_addr_fix`） |
| `_precheck()` | 对每个**勾选**按钮：解析其报文（`parse_plain_text`）→ `addr_lengths_for_frame` → `check_values` → `frame_addr_fix.apply()` 帧级确认；返回 `[(index, ok, reason)]` |
| `result_patches()` | `{按钮下标: {"protocol": int|None, "addr": dict}}`；「清除」模式下 `protocol=None, addr={}`（widget 侧据此删键） |
| `_on_accept()` | 无勾选 → 提示；有勾选但无地址（非清除模式）→ 提示；存在预检失败且被勾选 → 二次确认（列出跳过项）→ 只保留可应用者 |

预检的三个判据（与发送时同源，避免「编辑时能过、发送时失败」）：
1. 报文能解析成字节（否则「报文不是合法 HEX」）；
2. 每个地址字段能按**该按钮自己的帧**解析（长度/写法）；
3. `frame_addr_fix.apply()` 能成功（帧结构含地址域、替换后长度不变）。

## 4. 数据流

```mermaid
flowchart TD
  A[工具栏「批量地址…<br/>btn_custom_batch_addr"] --> B[BatchAddressDialog<br/>buttons=self._buttons]
  B --> C{协议下拉}
  C -->|supported_choices| D[地址输入行<br/>frame_addr_fix.fields_for]
  B --> E[预检 _precheck<br/>逐按钮用自己的帧]
  E --> F[列表行标注 ⚠ 原因<br/>失败项默认不勾]
  F --> G[确定]
  G -->|有失败项被强行勾选| H[二次确认<br/>列出将跳过项]
  G --> I[result_patches]
  I --> J[_on_custom_batch_address<br/>写回 _buttons 副本]
  J --> K[_set_buttons<br/>重建网格 + 落盘 + 日志]
```

## 5. 与既有约定的对齐

- **单一来源**：协议字段/长度/校验算法只在 `frame_addr_fix`；界面不硬编码任何协议细节（陷阱 31/55/61 的教训）。
- **失败不静默**（陷阱 23 精神）：预检失败必须显示原因；跳过的项在日志里逐条列出；没有可应用者时不改任何按钮。
- **按钮宽度**（陷阱 63）：新按钮走 `fit_btn_width()`（只设下限）；文案与提示标签的取舍见 §6，判据是
  `btn.width() >= btn.sizeHint().width()`（`show()` 之后量）。
- **不发不存在的字节**：应用只改按钮元数据，发送路径不变（`_apply_button_address` 仍在发送时替换）。
- **无配置迁移**：不新增配置键 ⇒ `CONFIG_VERSION` 不动（陷阱 58 末条）。

## 6. 取舍（含实测依据）

1. **批量一次性写入 vs 协议共享模板**：用户明确选择前者。共享模板会让「某个按钮想用别的地址」变得需要先解绑，
   属隐藏耦合；一次性写入后各按钮仍是普通值，导出/导入/配置都是普通数据。
2. **默认勾选 = 已绑定本协议**：让「换地址」动作的默认作用域就是「本协议的全部按钮」，
   同时把预检失败的行排除在默认之外（用户不动勾选 = 天然全或无）。
3. **失败项跳过需二次确认**（而非直接全批失败）：批量场景里个别按钮报文损坏不应阻塞其余几十个；
   但**必须**让用户看见跳过谁、为什么（拒绝确认则完全不动）。
4. **工具栏只加 1 个按钮**（宽度实测，1200×800 offscreen）：
   现 5 个按钮各 94px（合计 470）+ 行内提示标签 288px ≈ `sizeHint` 788px，可用宽度 960px；
   加第 6 个（+94）后 882px 仍放得下。为留出大字号余量，**把行内提示标签「提示：报文按钮上点右键可编辑 /
   删除 / 移位」删掉**（该信息已在每个按钮的 tooltip 末行「单击发送；右键可编辑 / 删除 / 移位」里，
   属冗余文案），换成空态占位提示已有说明。
5. **不做 FlowLayout 换行**：该项目级布局类在 `main_gui.py`（蓝牙页按契约不得 import main_gui），
   抽公共模块要动 `main_gui.py`（并发会话在改）⇒ 本次不引入跨模块重构，改为「删冗余标签腾宽度」+ 实测判据。
   若将来字号继续变大导致裁字，再单独立项抽 `flow_layout.py`。

## 7. 兼容 / 回滚

- 兼容：按钮字典不加新键；导入的旧 JSON 缺 `protocol`/`addr` 时界面显示「未绑定」，批量对话框可给它们补上。
- 回滚：还原 `frame_addr_fix.py` / `bluetooth_tool_widget.py` 的本次 hunk（对话框与按钮一处接线），
  按钮数据无需迁移（`protocol`/`addr` 是 1.23.81 就有的键）。
