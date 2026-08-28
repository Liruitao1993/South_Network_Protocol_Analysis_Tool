# PRD：GUI 自动升级检查 + 全自动替换

## 需求

主程序（PySide6 GUI）集成**启动时自动检查更新** + **程序内全自动下载替换新版本**：
- 启动时后台静默检查最新版本（不阻塞主窗口）
- 本地版本低于最新版 → 弹提示框，用户确认后**全自动**下载新 exe 并替换
- 替换流程自动处理 Windows exe 自替换锁（运行中的 exe 无法覆盖自身）

## 范围

- 新增更新检查模块 `auto_updater.py`（版本比对 + 下载 + 替换编排）
- `main_gui.py` 启动流程接入（非阻塞后台检查 + 提示框）
- 更新源可配置（默认 Gitee Releases，可切私有 HTTP），存入 `config.json` 的 `update` 段
- 新增系统集成子项：升级配置弹窗（更新源 URL、是否自动检查）

## 约束

- **更新源默认 Gitee Releases**（国内容户友好），API：`https://gitee.com/api/v5/repos/{owner}/{repo}/releases/latest`
  - 返回 JSON：`tag_name`（版本号）、`assets`（含 `browser_download_url` 指向 exe）
- 私有源也支持：一个静态 `version.json`（`{"version":"1.14.4","url":"https://.../exe"}`），便于内网
- **版本比对**：语义化比较（主.次.修订），用 `packaging.version` 或手写比较器，数字逐段比较
- **全自动替换流程**（Windows exe 自替换）：
  1. 下载新 exe → 临时目录（`%TEMP%/升级工具` 或用户缓存目录）
  2. 校验下载成功（大小非 0、可选的 SHA-256 校验从 version 源带）
  3. 写一个 `update.bat`：`timeout /t 1` 等主进程退出 → `copy /Y` 新 exe 覆盖 → 冷启动新 exe
  4. `subprocess.Popen(update.bat, detached=True, shell=False, close_fds=True)` 分离启动
  5. 提示用户"更新下载完成，正在替换重启"→ 应用正常退出
- 下载失败/校验失败 → 不破坏现有 exe，仅提示错误，可重试
- 检查网络失败 → 静默跳过（离线/内网无源也能正常运行）

## 验收标准

1. 启动时自动检查：本地 < 最新版 → 弹更新提示（含版本号/更新说明）
2. 用户确认 → 下载新 exe 到临时目录，进度可见
3. 下载成功 + SHA-256 校验通过 → 启动独立 update.bat，退出现有实例
4. update.bat 等主进程退出后覆盖 exe 并重启新版本
5. 本地已最新 → 静默，无提示
6. 网络异常/下载失败 → 提示错误不崩溃，现有版本不受影响
7. 更新源可配置（config.json `update` 段），GUI 菜单可改
8. 全量回归测试通过；打包后 exe 实测（模拟新版本发布验证替换链路）