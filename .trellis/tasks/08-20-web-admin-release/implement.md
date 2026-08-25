# 执行计划 - Reflex Web 版本发布管理

## 阶段概览
预估修改：2 个文件 + 1 个新模块。复杂度中等。

## 步骤

### 1. 创建后端模块 `admin_release.py`
- 文件：`reflex_web/reflex_web/admin_release.py`
- 内容：
  - `AdminConfig` 类：密码哈希校验、读写 admin_config.json、默认密码初始化
  - `ReleaseManager` 类：发布、回滚、版本列表、SHA-256 计算
- 纯逻辑，无 UI 依赖，可独立测试
- 验证：写一个简单脚本调用 `ReleaseManager` 测试发布/回滚流程

### 2. 在 State 中追加管理员认证字段和方法
- 文件：`reflex_web/reflex_web/reflex_web.py`
- 追加到 `State` 类：
  - `admin_logged_in: bool = False`
  - `admin_show_login_dialog: bool = False`
  - `admin_password_input: str = ""`
  - `admin_is_default: bool = False`
  - 方法：`admin_login(password)`、`admin_logout()`、`admin_change_password(old, new)`
- 所有写操作首行校验 `admin_logged_in`

### 3. 在 State 中追加发布管理状态字段和方法
- 追加字段：
  - `release_version: str = ""`
  - `release_notes: str = ""`
  - `release_url: str = ""`
  - `release_current_info: Dict[str, str] = {}`
  - `release_history: List[Dict[str, str]] = []`
  - `release_status: str = ""`（操作反馈）
  - `release_progress: int = 0`
- 追加方法：
  - `load_release_info()`：加载当前版本 + 历史版本
  - `publish_release(files)`：发布新版本
  - `rollback_version(version)`：回滚到指定版本
  - `_compute_sha256_progress(filepath)`：带进度的 SHA-256

### 4. 新增 UI 组件
- `admin_login_dialog()`：登录对话框（密码输入 + 登录按钮）
- `release_tab()`：发布管理主页面
  - 当前版本信息卡片
  - 上传发布表单（upload 组件 + 版本号 + 更新说明 + URL + 发布按钮）
  - 历史版本列表（表格 + 回滚按钮）
  - 密码修改区域
- tab 栏条件渲染"发布管理"按钮（用 `rx.cond(State.admin_logged_in, ...)`）
- tab 内容链追加 release 分支
- `set_tab` 追加 `release` 分支调用 `load_release_info()`

### 5. 处理 URL 自动填充
- 发布表单的 URL 字段默认值：页面加载时从 `window.location` 推导
- 通过 `rx.call_script` 获取 host 后设置 `release_url` 默认值
- 格式：`http://<host>/download/<exe文件名>`

### 6. 更新 `run_app.py`（如需要）
- 检查 downloads 目录权限
- 确保 archive 目录可写
- 如 `/download/archive/` 不应公开访问，在中间件中拦截（设计上 archive 不在下载路由内，因为 _serve_download 直接读 downloads/ 下的文件，archive 是子目录，而目录穿越防护会拦截 `..`，但 archive 内文件可通过 `/download/archive/xxx.exe` 直接访问 → 需在 `_serve_download` 中加判断：路径含 `archive/` 时返回 403）

### 7. `.gitignore` 更新
- 忽略 `reflex_web/admin_config.json`
- 忽略 `reflex_web/downloads/archive/`

### 8. 测试验证
- [ ] 启动 Reflex，确认现有所有 tab 正常
- [ ] 登录功能：正确密码进入，错误密码被拒
- [ ] 上传一个小 exe（或测试用 PE 文件），发布成功
- [ ] 检查 downloads/ 下生成的 version.json 格式正确、url 是完整 URL
- [ ] 历史版本列表正确显示
- [ ] 回滚功能正常
- [ ] 密码修改正常
- [ ] 刷新页面后登录状态消失（预期行为）
- [ ] 未登录状态看不到发布管理 tab
- [ ] 直接调用发布事件（通过浏览器控制台）因未登录而失败

### 9. 更新文档
- 在 `reflex_web/` 下的部署文档中说明管理员功能和默认密码
- 更新 `build_embedded_deploy.py` 和 `build_offline_deploy.py` 相关说明（如需要）
