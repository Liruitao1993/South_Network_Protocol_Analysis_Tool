# Design：GUI 自动升级检查 + 全自动替换

## 模块结构

### 新增 `auto_updater.py`（无 PySide 依赖，可独立测试）
纯逻辑 + 可注入的 HTTP 回调，方便测试。核心：

```python
class VersionChecker:
    def __init__(self, source_config: dict)          # {"type": "gitee"|"private", "url":..., "owner":..., "repo":..., "sha256":bool}
    def fetch_latest(self, http_get=None) -> dict     # 拉取版本信息 → {"version":..., "url":..., "notes":..., "sha256":...}
    def compare(self, local: str, remote: str) -> int # 语义化比较：<0 本地旧 / 0 相同 / >0 本地新（返回是否需要更新布尔）

class Opdater:
    def download(self, url, dest, progress_cb=None) -> Path   # 流式下载到临时目录，校验大小
    def verify_sha256(self, dest, expected) -> bool            # 可选校验
    def stage_and_replace(self, exe_path, new_path) -> None    # 写 update.bat + 分离启动
    def build_update_bat(self, exe_path, new_path) -> str      # 生成 bat 内容（等主进程退出→覆盖→重启）
```

### `update.bat` 生成（全自动替换核心）
```bat
@echo off
set "NEW=%~1"
set "OLD=%~2"
:wait
tasklist /fi "IMAGENAME eq %OLD_BASENAME%" 2>nul | find /i "%OLD_BASENAME%" >nul
if not errorlevel 1 (
  ping 127.0.0.1 -n 2 >nul
  goto :wait
)
copy /y /b "%NEW%" "%OLD%" >nul
start "" "%OLD%"
del "%NEW%" 2>nul
exit
```
- 主程序 Popen bat 后立即退出 → bat 轮询等待原 exe 进程消失 → copy 覆盖 → start 重启
- 用 `ping -n 2` 等待（~1s），避免 `timeout` 依赖 cmd 交互

### 版本比较器（语义化）
- 拆 `1.14.4` 按 `.` 分段，每段 int 比较；支持 `1.2.0` 三段到 `1.14.4`
- 拒绝非数字字段回退为字符串比较

## 配置（config.json `update` 段）

```json
"update": {
  "enabled": true,
  "check_on_start": true,
  "source_type": "gitee",           // gitee | private
  "gitee_owner": "",
  "gitee_repo": "",
  "private_url": "",                 // 私有源 version.json 地址
  "sha256_verify": true,             // 远程带 sha256 时校验
  "last_check": "2026-08-20"
}
```

## GUI 接入（main_gui.py）

- **启动检查**：主窗口 `setup_ui` 完成后，用 `QTimer.singleShot` 延迟启动后台线程（`QThread`）跑 `VersionChecker.fetch_latest`，不阻塞 UI；结果回到主线程：
  - 有新版 → `QMessageBox` 询问是否更新（显示 本地版本→最新版本 + 更新说明摘要）
  - 无新版/网络失败 → 静默（状态栏可显示"已是最新"）
- **手动入口**：帮助菜单 "检查更新(&C)" → 立即检查
- **配置入口**：配置菜单 "更新设置(&U)..." → 编辑 config.json `update` 段（对话框）
- **下载进度**：下载时弹进度对话框（QProgressDialog），QThread 线程回调更新
- **替换确认**：下载+校验完成 → 提示"更新完成，正在重启应用" → Popen bat → `QCoreApplication.quit()`

## 线程模型
- 用独立 `UpdateWorker(QThread)` 承载检查/下载（网络 IO 不进 GUI 线程）
- 通过 signal 回主线程更新 UI；用 `QAbortButton` 支持取消下载

## 安全
- 下载 URL 限 http/https；校验路径合法（防更新的新 exe 路径写入恶意）
- SHA-256 优先校验（远程提供时）；不提供则按文件大小非 0 + 后缀 .exe 兜底
- 替换前可 copy 当前 exe 到 `%TEMP%` 备份（可选保留）

## 验收映射
见 PRD §验收标准。重点：exe 自替换链路必须实测——本地模拟发布一个"新版"（改版本号 + 构造 fake 服务器返回 json + 真实 exe 文件）跑通 下载→校验→bat 替换→重启 全链路。