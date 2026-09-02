# 设计：管理员删除报文分享记录

## 边界与契约

### 存储层（share_model.py）

```python
def delete(self, item_id: int) -> bool:
    """按 id 删除分享记录；不存在返回 False 不抛错。"""
    with sqlmodel.Session(self._engine) as session:
        obj = session.get(ShareItem, int(item_id))
        if obj is None:
            return False
        session.delete(obj)
        session.commit()
        return True
```

纯逻辑可单测（同 add/get/list_page 模式）。删除不存在的 id 返回 False（幂等安全）。

### 权限模型

- **复用** `AdminConfig`（admin_release.py）与主 `State.admin_logged_in`。
- **ShareState 改为继承主 State**（`class ShareState(State)`）——与 FeedbackState 同款模式（记忆 #61 铁律：跨 State 访问只能继承）。继承后可读 `self.admin_logged_in`（后端 handler 内）与前端 `ShareState.admin_logged_in`（Var 渲染）。
- 删除入口状态：
  - 未登录：列表不渲染删除按钮。
  - 已登录：每行卡片右侧显示「删除」。

### ShareState 新增

```python
# 管理员删除
sh_delete_id: int = 0          # 待确认删除的记录 id
sh_confirm_open: bool = False  # 删除确认弹窗
sh_admin_msg: str = ""         # 删除操作结果提示（错误/成功）

def sh_ask_delete(self, item_id):   # 点删除 → 打开确认弹窗
    self.sh_delete_id = item_id
    self.sh_confirm_open = True

def sh_cancel_delete(self):
    self.sh_confirm_open = False
    self.sh_delete_id = 0

def sh_confirm_delete(self):   # 确认 → 删除 + 刷新
    if not self.admin_logged_in:
        self.sh_admin_msg = "请先登录管理员"
        self.sh_confirm_open = False
        return
    ok = sm.ShareStore.instance().delete(self.sh_delete_id)
    self.sh_confirm_open = False
    self.sh_delete_id = 0
    if ok:
        self.sh_msg = "已删除该记录"
        self.sh_load()   # 刷新当前页；若当前页删空自动回退页数（list_page 已处理 page min）
    else:
        self.sh_msg = "删除失败：记录不存在或已被删除"
```

> `sh_load` 已有 `self.sh_page = min(self.sh_page, pages)` 兜底——删空当前页后自动回退，不会出现空页。

### 前端（share_page /_sh_item_card）

- `_sh_item_card` 的 hstack 尾部（chevron 前）插入：

```python
rx.cond(
    ShareState.admin_logged_in,
    rx.button(
        rx.hstack(rx.icon("trash", size=14), "删除", spacing="1"),
        size="1",
        color_scheme="red",
        variant="soft",
        on_click=lambda: ShareState.sh_ask_delete(item["id"]),
    ),
),
```

> `on_click` 与卡片 `on_click=lambda: ShareState.sh_open_detail(item)` 会冲突（点击删除也触发开详情）。需在删除按钮上 `on_click` 事件里阻止冒泡——Reflex 中给按钮 `on_click=...` 同时外层卡片也有 on_click，事件会冒泡。**方案：删除按钮的 on_click 用 `rx.stop_propagation` 或把删除按钮放在卡片 on_click 之外**。Reflex 提供 `on_click=rx.stop_propagation` 吗？需核实——若不可用，改为把删除按钮置于卡片可点击区外（卡片 on_click 只包在主要内容区，删除按钮单独一行）。

  更稳妥方案：**卡片 on_click 移到"内容区"而非整个卡片**——删除按钮在卡片右上角独立位置，其 on_click 与卡片 on_click 分属不同容器，避免冒泡。参照 _sh_detail_dialog 的关闭按钮做法（显式 on_click 即可）。

- 确认弹窗 `_sh_delete_confirm_dialog()`：受控三件套（记忆 #61 ⑦：rx.dialog.root 挂 on_open_change 同步 State + 关闭按钮显式 on_click），内容为「确认删除该条分享记录？」+ 确认/取消。

### 页面挂载

share_page 的 vstack 末尾追加 `_sh_delete_confirm_dialog()`（与 `_sh_detail_dialog()` 并列）。

## 兼容性

- ShareState 从 `rx.State` 改继承 `State`：继承链上主 State 变量前后端均可见（记忆 #61 ⑥），主页分享弹窗内 `last_parsed_hex`（此前通过什么访问？）——需检查现有 sf_* 是否已用继承访问主 State 变量。若 sf_open_dialog 已用 self.last_parsed_hex，说明**当前 ShareState 其实已依赖继承**但声明是 rx.State——需核实。若现有代码直接访问了主 State 变量而 ShareState(rx.State) 未继承，那现在就是坏的吗？需检查。**检查点：sf_open_dialog 中的 self.last_parsed_hex / self.last_protocol_name 来源**。
- `_item_dict` 返回 id（int），前端 `item["id"]` 可直接传给 sh_ask_delete。
- 测试：ShareStore.delete 单测 + ShareState 删除事件（TestClient 或直接 handler 调用）+ 页面渲染（登录/未登录条件）。

## 风险

- 事件冒泡：删除按钮与卡片 on_click 冲突（见上，用布局隔离）。
- ShareState 改继承：确认不影响主页分享弹窗（若当前能正常工作，改继承只会增强，不破坏）。
