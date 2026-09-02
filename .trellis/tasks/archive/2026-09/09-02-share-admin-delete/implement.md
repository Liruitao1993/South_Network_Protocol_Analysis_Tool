# 实施：管理员删除报文分享记录

## 步骤

1. **share_model.py**：`ShareStore.delete(item_id) -> bool`（不存在返回 False）。
2. **reflex_web.py**：
   - `ShareState(rx.State)` → `ShareState(State)`（继承主 State，顺带修复 sf_open_dialog 访问 last_parsed_hex 的现存 bug）。
   - ShareState 新增：`sh_delete_id: int`、`sh_confirm_open: bool`、`sh_admin_msg: str`。
   - 新增事件：`sh_ask_delete` / `sh_cancel_delete` / `sh_confirm_delete`。
   - `_sh_item_card`：管理员登录态显示「删除」按钮（rx.stop_propagation + sh_ask_delete 事件链）。
   - 新增 `_sh_delete_confirm_dialog()`：受控确认弹窗（on_open_change 同步 + 显式关闭按钮）。
   - `share_page` 挂载确认弹窗。
3. **测试** `test/test_frame_share.py`：
   - ShareStore.delete：删除存在/不存在/重复删除。
   - ShareState 删除事件：未登录拒绝、登录后删除成功刷新、删除不存在。
   - 页面渲染：登录/未登录删除按钮显隐。
4. **验证**：`python test/test_frame_share.py` 全过 + `test_web_feedback` 回归 + Web 服务重启真机验证。

## 验证命令

```bash
python.exe test/test_frame_share.py
python.exe test/test_web_feedback.py
python.exe test/test_feedback_api.py
```

## 回滚点

- 改 ShareState 继承前：`git stash` 或记录原始声明 `class ShareState(rx.State)`。
- 若继承引入意外（主页分享弹窗行为变化），可回退仅保留 delete 存储层。

## 检查点

- [ ] ShareState 继承后 `hasattr(ShareState, 'last_parsed_hex')` 为 True。
- [ ] 删除按钮点击不触发卡片 on_click（详情不弹出）。
- [ ] 确认弹窗可正常开关（受控三件套）。
- [ ] 删除后 sh_load 刷新，页码正确。
