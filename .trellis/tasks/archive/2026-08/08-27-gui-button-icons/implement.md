# 执行计划：GUI 按钮添加图标

## 前置

- 任务状态：planning（待命令环境恢复后 `task.py start` 转 in_progress 再实施）。
- 依赖：上一任务「统一按钮风格」已完成（`set_btn` / `btnKind` 体系存在）。

## 实施清单（顺序执行）

### 1. gui_utils.py — 新增图标辅助
- [ ] 新增 `_STANDARD_ICON_MAP`（icon_key → QStyle.StandardPixmap）。
- [ ] 新增 `set_btn_icon(btn, icon_key, icon_only=False)`：未知 key 静默跳过；设图标 + setIconSize(QSize(16,16))；icon_only 时隐藏文字（默认 False）。
- [ ] 顶部 import `QStyle, QIcon, QSize`。

### 2. main_gui.py — 主界面按钮
- [ ] 单帧解析按钮行：解析→play、校验→play、发送→play。
- [ ] 批量解析工具栏：★保存→save、×删除→delete、?帮助→help、导出/导出选中→export、清空→clear、载入→open、刷新→refresh。
- [ ] 串口控制：打开串口→open、停止→stop。
- [ ] 更新下载对话框：下载选中版本→apply、取消→cancel。
- [ ] 其余主弹窗主操作按钮就近映射（apply/ok/cancel）。

### 3. frame_gen_widget.py — 组帧
- [ ] 生成帧→apply、发送→play、添加预设→apply、添加测试方案→apply、清空日志→clear、命令说明→help、A-XDR +→add、A-XDR −→delete、清空响应→clear、模板字段→apply。

### 4. diff_widget.py — 报文对比
- [ ] 开始对比→play、交换→refresh、载入A/B→open、导出→export、关闭→cancel、最大化按钮保留 ghost。

### 5. monitor/tcp_monitor.py — TCP 监控
- [ ] 开始抓包→play、停止→stop、刷新→refresh、清空→clear、暂停→pause、加载历史→open、CSV 记录→save（success↔danger 切换逻辑保持）。

### 6. monitor/frame_monitor.py — 帧监控
- [ ] 添加到测试→apply、校验→play、清空→clear、导出→export。

### 7. preset_buttons.py — 预设命令
- [ ] 确定→ok、预设命令按钮→apply。

### 8. test_plan_widget.py — 测试方案
- [ ] 确定→ok、开始→play、停止→stop、清空后台→clear、导出报告→export、迷你发送按钮→play（sm）。

### 9. monitor_widget.py / archive_widget.py / topology_widget.py / lookup_pages.py / message_tool_widget.py / llm_* / system_settings.py
- [ ] 给语义明确的主操作按钮就近配图（查询→search、清除→clear、导出→export、定位→search、添加→add、删除→delete、注册/注销→apply）。

## 验证

- [ ] 全部改动文件 `python -m py_compile` 语法检查通过（bash 恢复后执行）。
- [ ] offscreen 三主题（default/dark/glass）启动主窗口无异常、无按钮崩溃。
- [ ] 遍历主要 tab 按钮图标可见、文字完整。
- [ ] `set_btn_icon` 传入未知 key 不崩溃（单元断言）。
- [ ] 若存在 test 脚本，运行相关 GUI 组件测试。

## 回滚点

- 每文件改动独立可回滚；如某图标视觉异常，仅移除该按钮的 `set_btn_icon` 调用即可，不影响其余。

## 交付后

- 更新 `main_gui.py` CHANGELOG（新增条目：按钮添加 Qt 内置标准图标）+ AGENTS.md §10。
- 若命令环境已恢复，运行 `task.py archive` 收尾。
