# 技术设计 - Reflex Web 版本发布管理

## 概述

在现有 Reflex 单页应用（tab 切换式）中新增"发布管理"tab，仅管理员可见。管理员认证通过服务端密码哈希校验 + Reflex State 会话实现。文件上传使用 Reflex 原生 upload 组件，后端保存到 `downloads/` 并自动生成 `version.json`。

## 文件结构

```
reflex_web/
├── admin_config.json          # 管理员密码配置（首次启动自动创建，不提交 git）
├── reflex_web/
│   ├── reflex_web.py          # 主应用（新增 AdminState + 发布管理 UI）
│   └── admin_release.py       # 发布管理后端逻辑（独立模块，便于维护）
└── downloads/
    ├── 南网协议解析工具.exe    # 当前发布的 exe
    ├── version.json           # 当前版本信息（auto_updater 读取）
    └── archive/               # 历史版本归档
        ├── 1.13.0.exe
        └── 1.14.0.exe
```

## 模块职责

### `admin_release.py`（新增）
纯后端逻辑，无 UI 依赖：
- `AdminConfig`：读写 `admin_config.json`，密码哈希校验
- `ReleaseManager`：
  - `publish(exe_bytes, filename, version, notes, base_url)` → 发布新版本
  - `rollback(version)` → 回滚到指定历史版本
  - `list_versions()` → 列出当前版本 + 历史版本
  - `get_current_version()` → 读取 version.json
  - `change_password(old_pwd, new_pwd)` → 修改密码

### `reflex_web.py`（修改）
- 新增 `AdminState(rx.State)` 子状态，或在现有 `State` 中追加字段（采用追加方式，与现有结构一致）
- 新增 `release_tab()` 组件函数
- 新增登录对话框/区域
- tab 栏条件显示"发布管理"按钮（仅登录后）
- `set_tab("release")` 时加载版本信息

### `run_app.py`（可选修改）
- `/download/` 路由已存在，无需修改
- 如需在中间件层保护 `/api/admin/` 路由，可在此添加。但 Reflex 的事件回调都走 WebSocket，HTTP API 路由较少，认证在 State 层做即可。

## 数据格式

### `admin_config.json`
```json
{
  "password_hash": "sha256哈希值",
  "password_salt": "随机盐",
  "created_at": "2026-08-20T00:00:00",
  "is_default_password": true
}
```
- 默认密码 `admin123`，首次登录后 `is_default_password` 设为 true，前端提示修改。
- 密码哈希：`sha256(salt + password)`。

### `version.json`（与现有格式一致）
```json
{
  "version": "1.14.0",
  "url": "http://10.1.10.172:8091/download/南网协议解析工具.exe",
  "notes": "更新说明...",
  "sha256": "abc123..."
}
```
**重要**：`url` 字段必须是完整 URL（含 scheme + host），不能是相对路径。客户端 `auto_updater.py` 用 urllib 直接请求此字段，相对路径会报 `unknown url type`。

发布时根据当前请求 host 自动拼接：`{scheme}://{host}/download/{filename}`。

## 认证设计

### 为什么不用 Reflex 内置 auth
Reflex 有 `rx.auth` 模块，但较重且依赖数据库。本项目是单用户内网场景，手写轻量认证更简单。

### 认证流程
1. 用户点击"管理员登录"按钮 → 弹出登录对话框
2. 输入密码 → 提交到 `State.admin_login(password)`
3. 后端用 salt + sha256 校验
4. 成功：设置 `admin_logged_in = True`，tab 栏显示"发布管理"
5. 失败：显示错误提示

### 会话管理
- 登录状态存在 `State` 的 `admin_logged_in: bool` 字段中
- Reflex State 是按浏览器 session 隔离的（基于 token cookie）
- 刷新页面后 State 重置 → 需要重新登录（可接受，内网场景）
- 发布操作前后端再校验一次 `admin_logged_in`（前端隐藏按钮不代表安全，后端必须校验）

## 上传设计

### Reflex Upload 组件
使用 `rx.upload()` 组件，配置：
- `accept = {".exe": ["application/octet-stream", "application/x-msdownload"]}`
- `max_files = 1`
- `max_size = 500 * 1024 * 1024`（500MB）

### 上传处理
- `State.handle_upload(files)` 回调获取上传文件列表
- 读取文件内容（后端），校验 PE 头 `MZ`
- 暂存到内存或临时文件，发布时才正式写入 `downloads/`

## 发布流程

```
用户填写表单 → 点击"发布"
  ↓
后端校验 admin_logged_in
  ↓
校验版本号格式（简单校验：数字+点）
  ↓
从上传文件列表获取 exe 数据
  ↓
校验 PE 头（前两字节 MZ）
  ↓
旧版本归档：如果 downloads/ 已有 exe，读取当前 version.json 版本号，移动到 archive/<version>.exe
  ↓
保存新 exe 到 downloads/ 目录
  ↓
计算 SHA-256（流式，大文件不爆内存）
  ↓
拼接下载 URL：{scheme}://{host}/download/{filename}
  ↓
生成 version.json 写入 downloads/
  ↓
返回成功，刷新当前版本显示
```

## 回滚流程

```
用户在历史版本列表点击"回滚到此版本"
  ↓
后端校验 admin_logged_in
  ↓
读取 archive/<version>.exe
  ↓
当前 exe 先归档（用当前 version.json 的版本号）
  ↓
复制 archive/<version>.exe → downloads/ 当前文件名
  ↓
重算 SHA-256，重写 version.json
  ↓
刷新显示
```

## URL 生成策略

发布时获取当前访问的 host 用于拼接完整 URL：

- 前端传递：`window.location.host` 通过 `rx.call_script` 获取后传回后端
- 或后端从 ASGI scope 的 `host` header 取（更可靠，因为 WebSocket 连接也有 host）

实现方式：在 `State` 中存 `_request_host: str`，页面加载时通过事件回调或中间件设置。

简化方案：管理员在发布表单中手动填写/确认下载 URL，默认值从当前页面 URL 自动推导。

## 与现有代码集成点

1. **State 类**：在 `State` 中追加管理员相关字段和方法
2. **tab 栏**：在 `index()` 的 tab 按钮列表末尾条件渲染"发布管理"按钮
3. **tab 内容**：在 `rx.cond` 链中追加 `State.active_tab == "release"` 分支
4. **`set_tab` 方法**：追加 `tab == "release"` 时加载版本信息

## 安全校验清单

所有写操作（上传、发布、回滚、改密码）后端首行必须：
```python
if not self.admin_logged_in:
    return  # 或设置错误消息
```

文件写入前：
- 校验文件名无路径分隔符（`/` `\` `..`）
- 校验 PE 头 `MZ`
- 校验后缀 `.exe`
- 写入路径用 `resolve()` 后确认在 `downloads_dir` 内

## 回滚方案

如发布功能出问题：
1. 删除 admin_config.json 重置密码
2. 手动替换 downloads/ 下的 exe 和 version.json
3. 功能不影响其他 tab，最坏情况可在前端隐藏发布管理入口

## 测试要点

- 错误密码无法登录
- 非 exe 文件上传被拒绝
- 发布后 version.json 格式正确、SHA-256 匹配
- 回滚后 version.json 和 exe 正确切换
- 未登录状态看不到发布管理 tab
- 中文文件名 exe 上传后下载 URL 正确编码
- 大文件（>100MB）上传不卡死、SHA-256 计算有进度
