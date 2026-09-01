# 集成点研究 — GUI 反馈接入 Web 服务

> 调查时间：2026-09-01。来源：代码审查。

## 1. GUI 菜单位置（main_gui.py）

- 菜单栏创建在 `_create_menus` 区域，L5639 `menubar = self.menuBar()`。
- 帮助菜单 L5653：`help_menu = menubar.addMenu("帮助(&H)")`，现有项：
  - L5655 `检查更新(&C)` → `self._check_update_manual`
  - L5659 `关于(&A)` → `self._show_about_dialog`
- **插入点**：检查更新与关于之间加「问题反馈(&F)...」。

## 2. GUI 配置结构（config.json）

- 顶层键：serial / file_paths / ui / system / llm / llm_profiles / py_scripts / parse / update
- `update` 段已有跨服务器 URL 先例：`private_url: "http://10.1.10.172:8091/download/version.json"`（读写模式见 main_gui.py L5663 `_load_update_settings` / L5668 `_save_update_settings`——读 self._app_config、写回整个 json 文件）。
- **新增**：`"feedback": {"server_url": "http://127.0.0.1:8000"}`。对话框内自实现读写（模板参考 _save_update_settings：读现有 json → 改键 → 整体写回，ensure_ascii=False, indent=2）。

## 3. Web 路由既有模式（本次直接复用）

- 开发模式注册：`reflex_web.py` 尾部 `app._api.routes.insert(0, Route(...))`——`/download/`、`/api/download/`、`/fbimg/`、`/api/fbimg/` 四条已存在。`/api/*` 前缀会被开发模式 Vite 代理到后端。
- 生产模式：`run_app.py` `env_rewrite_middleware`（L264 附近）按 path 前缀分发——`/download/`、`/api/download/` → `_serve_download`；`/fbimg/`、`/api/fbimg/` → `_serve_fbimg`。新增 `/api/feedback` 分支同理。
- `_send_download_error(send, status, message)` 可复用作 JSON 错误响应模板（改造为 json body）。

## 4. 数据落盘链路

- `feedback_model.FeedbackStore.instance()` 单例；`uploads_dir()` = `FEEDBACK_DATA_DIR` 环境变量可覆盖（测试用）。
- `save_screenshot(data, orig_name)`：扩展名+魔数(≥12B)+大小(≤5MB)校验 → 重生成 `fb_YYYYmmdd_HHMMSS_<8hex>.<ext>`。
- Web 提交入口：`FeedbackState.submit_feedback`（reflex_web.py），构造 FeedbackItem 需补 `source="web"`。

## 5. Qt 网络栈要点

- `QNetworkAccessManager` + `QHttpMultiPart`（PySide6 自带，无需新依赖）。
- `QNetworkRequest.setTransferTimeout(15000)`（Qt 5.15+ 支持）。
- 异步 finished 回调 → `QJsonDocument.fromJson(reply.readAll())`。
- multipart 文本 part 需要 `Content-Type: text/plain` 头 + `Content-Disposition: form-data; name="xxx"`；文件 part 加 filename。

## 6. 风险与注意

- **旧库迁移**：现有 `reflex_web/data/feedback.db` 无 source 列——create_all 不会补列，必须 PRAGMA+ALTER TABLE（FeedbackStore.**init**）。
- **Granian 生产服务器**：run_app.py 用 granian（ASGI），中间件分支处理 multipart 需 `await` 读 body（scope/receive 流），注意大 body（截图最大 15MB）分块读取。
- **GUI exe 打包**：feedback_dialog.py 放项目根，自动被打包；QNetworkAccessManager 模块级单例注意父对象回收（对话框关闭时 deleteLater）。
- 反馈对话框不 import 任何 web/reflex 模块（GUI 独立运行时 reflex 可能未安装）。
