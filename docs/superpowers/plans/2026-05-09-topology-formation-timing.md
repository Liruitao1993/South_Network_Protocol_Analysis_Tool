# 拓扑自动刷新组网完成时间统计实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在拓扑自动刷新过程中，统计从启动查询到组网完成（拓扑节点数/CCO从节点总数 >= 98%）所消耗的时间，并在UI上展示。

**架构：** 在 `TopologyWidget` 内部新增组网计时状态（开始时间、CCO节点总数、完成标志、冻结耗时）。勾选自动刷新时先发送一次"查询从节点数量"帧获取总数，再按周期查询拓扑。每次完整拓扑分页完成后计算比例，达到阈值即冻结耗时。计时精度依赖 QTimer 周期（秒级），满足业务要求。

**技术栈：** PySide6, Python 3

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `topology_widget.py` | 唯一修改文件。新增组网状态变量、UI标签、帧发送/响应处理逻辑、完成检查与UI更新方法。 |

---

## 任务 1：添加组网状态变量

**文件：**
- 修改：`topology_widget.py`

在 `TopologyWidget.__init__` 中，`_refresh_timer` 初始化之后、`setup_ui()` 之前添加状态变量：

```python
        # 自动刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)

        # 组网计时状态
        self._formation_start_time: Optional[float] = None
        self._formation_node_count: Optional[int] = None
        self._formation_done = False
        self._formation_elapsed_seconds: Optional[float] = None

        self.setup_ui()
```

- [ ] **步骤 1：添加上述 4 行状态变量到 `__init__`**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): add network formation timing state variables"
```

---

## 任务 2：添加组网状态UI标签

**文件：**
- 修改：`topology_widget.py`

在 `setup_ui` 的统计信息部分，`_update_stats` 调用位置之后，添加 `formation_label`：

找到现有代码：
```python
        # 统计信息
        self.stats_label = QLabel("节点总数: 0 | CCO: 0 | PCO: 0 | STA: 0")
        self.stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.stats_label)
```

在其后追加：

```python
        self.formation_label = QLabel("组网状态: 未开始")
        self.formation_label.setStyleSheet("color: #2196F3; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.formation_label)
```

- [ ] **步骤 1：在 `setup_ui` 的 `stats_label` 下方添加 `formation_label`**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): add formation status UI label"
```

---

## 任务 3：修改自动刷新启动逻辑

**文件：**
- 修改：`topology_widget.py`

替换 `_start_auto_refresh` 方法：

```python
    def _start_auto_refresh(self):
        # 重置组网计时
        self._formation_start_time = time.time()
        self._formation_node_count = None
        self._formation_done = False
        self._formation_elapsed_seconds = None
        self._update_formation_ui()

        interval_ms = self.refresh_interval_sb.value() * 1000
        self._refresh_timer.start(interval_ms)
        self._log(f"[自动刷新] 已启动，间隔 {self.refresh_interval_sb.value()} 秒")

        # 立即查询一次从节点数量（用于组网完成判定）
        if self.protocol_mode == "south":
            frame = self._build_south_frame((0xE8, 0x00, 0x03, 0x05), {})
        else:
            frame = self._build_gdw_frame(0x10, 1, {})
        self._send_hex(frame.hex().upper(), "查询从节点数量(组网计时)")
```

- [ ] **步骤 1：替换 `_start_auto_refresh` 为上述代码**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): reset formation timer and query node count on auto-refresh start"
```

---

## 任务 4：添加南网从节点数量响应处理

**文件：**
- 修改：`topology_widget.py`

在 `_handle_south_response` 中，将现有的：

```python
        if di_key != (0xE8, 0x04, 0x03, 0x65):
            return
```

替换为：

```python
        # 查询从节点数量响应（组网计时用）
        if di_key == (0xE8, 0x00, 0x03, 0x05):
            if len(user_data) >= 2:
                count = int.from_bytes(user_data[0:2], 'little')
                self._formation_node_count = count
                self._log(f"[组网] CCO 从节点总数: {count}")
            return

        if di_key != (0xE8, 0x04, 0x03, 0x65):
            return
```

- [ ] **步骤 1：在 `_handle_south_response` 中添加 `DI=(0xE8,0x00,0x03,0x05)` 分支**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): handle south grid node count response for formation timing"
```

---

## 任务 5：添加国网从节点数量响应处理

**文件：**
- 修改：`topology_widget.py`

在 `_handle_gdw_response` 中，将现有的：

```python
        if afn != 0x10 or fn not in (20, 21):
            return
```

替换为：

```python
        # 查询从节点数量响应（组网计时用）
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

        if afn != 0x10 or fn not in (20, 21):
            return
```

- [ ] **步骤 1：在 `_handle_gdw_response` 中添加 `AFN=0x10, FN=1` 分支**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): handle GDW node count response for formation timing"
```

---

## 任务 6：添加组网完成检查与UI更新方法

**文件：**
- 修改：`topology_widget.py`

在 `TopologyWidget` 类中新增两个方法（建议放在 `_stop_auto_refresh` 之后、`_on_refresh_timeout` 之前）：

```python
    def _check_formation_complete(self):
        """检查是否组网完成（拓扑节点数 / CCO从节点总数 >= 98%）"""
        if self._formation_done or not self._formation_node_count:
            return
        ratio = len(self.nodes) / self._formation_node_count
        if ratio >= 0.98:
            self._formation_done = True
            self._formation_elapsed_seconds = time.time() - self._formation_start_time
            self._update_formation_ui()
            self._log(
                f"[组网完成] 拓扑节点{len(self.nodes)} / 总数{self._formation_node_count} = "
                f"{ratio * 100:.1f}%, 耗时 {self._formation_elapsed_seconds:.1f} 秒"
            )

    def _update_formation_ui(self):
        """更新组网状态标签"""
        if self._formation_done and self._formation_elapsed_seconds is not None:
            text = f"组网状态: 完成 | 耗时: {self._formation_elapsed_seconds:.1f} 秒"
        elif self._formation_start_time:
            elapsed = time.time() - self._formation_start_time
            text = f"组网状态: 进行中 | 已耗时: {elapsed:.1f} 秒"
        else:
            text = "组网状态: 未开始"
        self.formation_label.setText(text)
```

- [ ] **步骤 1：在 `TopologyWidget` 中添加 `_check_formation_complete` 和 `_update_formation_ui`**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): add formation completion check and UI update methods"
```

---

## 任务 7：在南网拓扑分页完成时调用组网检查

**文件：**
- 修改：`topology_widget.py`

在 `_handle_south_response` 中，找到南网分页完成的 `else` 分支：

```python
                else:
                    self._pending_query = False
                    self._log(f"[完成] 南网拓扑查询完成，共{len(self.nodes)}个节点")
```

替换为：

```python
                else:
                    self._pending_query = False
                    self._check_formation_complete()
                    self._log(f"[完成] 南网拓扑查询完成，共{len(self.nodes)}个节点")
```

- [ ] **步骤 1：在南网分页完成 else 分支中添加 `self._check_formation_complete()`**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): check formation complete on south grid topology finish"
```

---

## 任务 8：在国网拓扑分页完成时调用组网检查

**文件：**
- 修改：`topology_widget.py`

在 `_handle_gdw_response` 中，找到国网分页完成的 `else` 分支：

```python
            else:
                self._pending_query = False
                self._log(f"[完成] 国网拓扑查询完成，共{len(self.nodes)}个节点")
```

替换为：

```python
            else:
                self._pending_query = False
                self._check_formation_complete()
                self._log(f"[完成] 国网拓扑查询完成，共{len(self.nodes)}个节点")
```

- [ ] **步骤 1：在国网分页完成 else 分支中添加 `self._check_formation_complete()`**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): check formation complete on GDW topology finish"
```

---

## 任务 9：在刷新超时中更新进行中UI

**文件：**
- 修改：`topology_widget.py`

将 `_on_refresh_timeout` 替换为：

```python
    def _on_refresh_timeout(self):
        if self._pending_query:
            return
        if not self.serial_worker or not self.serial_worker.is_open():
            return
        self._on_query()
        self._update_formation_ui()
```

- [ ] **步骤 1：在 `_on_refresh_timeout` 末尾添加 `self._update_formation_ui()`**
- [ ] **步骤 2：Commit**

```bash
git add topology_widget.py
git commit -m "feat(topology): update formation UI on each refresh tick"
```

---

## 自检

**1. 规格覆盖度：**
- [x] 状态模型（4个变量）→ 任务1
- [x] 生命周期（勾选自动刷新时重置并查询数量）→ 任务3
- [x] 南网从节点数量响应 → 任务4
- [x] 国网从节点数量响应 → 任务5
- [x] 组网完成检查（比例 >= 98%）→ 任务6
- [x] 拓扑分页完成时调用检查 → 任务7、8
- [x] UI展示三种状态 → 任务2、6、9
- [x] 自动刷新继续运行 → 任务3中 `_refresh_timer.start` 未被移除

**2. 占位符扫描：**
- [x] 无 "TODO" / "待定" / "后续实现"
- [x] 无 "添加适当的错误处理" 类模糊描述
- [x] 每个步骤包含实际代码

**3. 类型一致性：**
- [x] `_formation_start_time` 始终为 `Optional[float]`
- [x] `_formation_node_count` 始终为 `Optional[int]`
- [x] `_formation_done` 始终为 `bool`
- [x] `_formation_elapsed_seconds` 始终为 `Optional[float]`
- [x] `self.formation_label` 在任务2中创建，在任务6、9中使用

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-05-09-topology-formation-timing.md`。

**执行方式选择：**

1. **子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代
2. **内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
