# 拓扑自动刷新组网完成时间统计设计文档

## 背景

拓扑信息页面现有自动刷新功能，通过 QTimer 周期性发送拓扑查询帧。需要在自动刷新过程中统计从启动查询到组网完成所消耗的时间。

## 组网完成的定义

1. 先通过查询 CCO 从节点数量获取总节点数（南网 DI=(0xE8,0x00,0x03,0x05)；国网 AFN=0x10, FN=1）。
2. 该数量只读取一次，后续周期中冻结该值。
3. 周期性读取网络拓扑，累积拓扑节点数。
4. 当 `拓扑节点数 / CCO 从节点总数 >= 98%` 时，认为组网完成，冻结消耗时间。

## 状态模型

在 `TopologyWidget` 中新增 4 个状态变量：

| 变量 | 类型 | 说明 |
|------|------|------|
| `_formation_start_time` | `float \| None` | 勾选自动刷新时 `time.time()` |
| `_formation_node_count` | `int \| None` | CCO 上报的从节点总数，查询一次后冻结 |
| `_formation_done` | `bool` | 是否已达成 ≥98% |
| `_formation_elapsed_seconds` | `float \| None` | 达成后冻结的耗时 |

## 生命周期

1. **勾选自动刷新** → `_start_auto_refresh()` 重置所有状态，记录开始时间，发送一次"查询从节点数量"帧。
2. **收到从节点数量响应** → 记录 `_formation_node_count`。
3. **每次完整拓扑查询分页完成后** → 计算比例 `len(self.nodes) / _formation_node_count`，达到 98% 时冻结 `_formation_elapsed_seconds`。
4. **停止自动刷新** → 状态保留，UI 继续显示当前结果。
5. **再次勾选自动刷新** → 回到步骤 1，重新计时。

## 帧发送与响应处理流程

勾选自动刷新后的帧序列：

```
[查询从节点数量] ──→ [响应: 记录总数] ──→ [周期性拓扑查询] ──→ [响应: 累积节点] ──→ ...
```

### 南网协议响应处理

在 `_handle_south_response()` 中新增 `DI = (0xE8, 0x00, 0x03, 0x05)` 分支：

```python
if di_key == (0xE8, 0x00, 0x03, 0x05):
    if len(user_data) >= 2:
        count = int.from_bytes(user_data[0:2], 'little')
        self._formation_node_count = count
        self._log(f"[组网] CCO 从节点总数: {count}")
    return
```

### 国网协议响应处理

在 `_handle_gdw_response()` 中新增 `AFN=0x10, FN=1` 分支，从 `table_data` 中提取"从节点总数量"：

```python
if afn == 0x10 and fn == 1:
    for name, raw, parsed, comment, bs, be in table_data:
        if "从节点总数量" in name or "从节点数量" in name:
            try:
                self._formation_node_count = int(parsed)
                self._log(f"[组网] CCO 从节点总数: {parsed}")
            except (ValueError, TypeError):
                pass
            break
    return
```

### 拓扑分页完成检查

南网和国网各自的 `_pending_query = False` 分支中调用 `_check_formation_complete()`：

```python
def _check_formation_complete(self):
    if self._formation_done or not self._formation_node_count:
        return
    ratio = len(self.nodes) / self._formation_node_count
    if ratio >= 0.98:
        self._formation_done = True
        self._formation_elapsed_seconds = time.time() - self._formation_start_time
        self._update_formation_ui()
        self._log(f"[组网完成] 拓扑节点{len(self.nodes)} / 总数{self._formation_node_count} = {ratio*100:.1f}%, 耗时 {self._formation_elapsed_seconds:.1f} 秒")
```

## UI 展示

在现有 `stats_label` 下方新增一个 `formation_label`（QLabel），显示三种状态：

- **未开始**：`组网状态: 未开始`
- **进行中**：`组网状态: 进行中 | 已耗时: 12.5秒`
- **完成**：`组网状态: 完成 | 耗时: 45.3秒`

"进行中"的耗时利用现有 `_refresh_timer` 的 timeout 事件顺带更新（与拓扑查询同周期），刷新周期内的显示误差可接受。

### 辅助方法

```python
def _update_formation_ui(self):
    if self._formation_done and self._formation_elapsed_seconds is not None:
        text = f"组网状态: 完成 | 耗时: {self._formation_elapsed_seconds:.1f} 秒"
    elif self._formation_start_time:
        elapsed = time.time() - self._formation_start_time
        text = f"组网状态: 进行中 | 已耗时: {elapsed:.1f} 秒"
    else:
        text = "组网状态: 未开始"
    self.formation_label.setText(text)
```

在 `_on_refresh_timeout()` 中追加调用 `_update_formation_ui()`，确保进行中的耗时持续刷新。

## 修改文件

- `topology_widget.py`
