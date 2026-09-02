# v1.21.1 版本号更新与 exe 打包

## 需求

1. `main_gui.py`：`APP_VERSION` 1.21.0 → 1.21.1；`BUILD_DATE` → 2026-09-02。
2. changelog 1.21.1 条目（未提交，含 Web 分享管理员删除功能）追加今天两个 UI 修复：
   - 测试方案表格超时列 SpinBox 遮挡数字，改纯文本直接填写（非法/越界自动还原）。
   - 懒加载 tab（TCP监控/协议组帧/档案管理/拓扑信息）首次点击替换占位 widget 后图标丢失，`_replace_lazy_tab` 保留 tabIcon。
3. `pyinstaller 南网协议解析工具.spec --noconfirm` 打包。
4. 验证 dist 下 exe 生成且关于页版本为 v1.21.1 (2026-09-02)。

## 注意

- 1.21.1 分享删除功能代码（reflex_web/share_dialog 等）为在途未提交工作，版本号提交与其同批，本次不单独 commit 用户在途文件，打包后由用户随功能一起提交。

## 验收

- `dist/南网协议解析工具/南网协议解析工具.exe`（spec 约定产物）存在且时间戳为本次构建。
- 版本常量与 changelog 一致。
