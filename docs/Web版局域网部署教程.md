# Web 版局域网部署教程（Windows 服务器 · 端口 8091）

> 面向场景：内网 Windows 服务器，**只对外开放 8091 一个端口**，部署「多协议解析平台」Web 版（Reflex 单端口服务）。
> 部署包：`dist/reflex_web_embedded/`（**内嵌 Python，零安装**——目标机不需要装 Python、不需要 Node.js、不需要联网）。
> 下文用 `D:\nw\reflex_web_embedded` 作为示例部署路径，按你的实际路径替换即可。

---

## 0. 前置条件

| 项 | 要求 |
|---|---|
| 系统 | 64 位 Windows（Windows Server 2016+ / Windows 10/11 均可） |
| 依赖 | **无需安装任何东西**（Python、Node 都内置/已编译进包） |
| 磁盘 | 部署目录约 150MB；运行数据另约 50MB+（含上传的客户端 exe） |
| 权限 | 首次配置需要管理员权限（开放防火墙端口、注册开机自启） |
| 网络 | 服务器与访问者同一内网；**8091 已在网络策略/安全组放行**（本教程再补 Windows 防火墙这一步） |

---

## 1. 部署包里有什么（先认识目录）

```text
reflex_web_embedded/
├── python/                 # 内嵌 Python 3.12 + 全部依赖（不要动）
├── reflex_web/             # 程序代码 + 预编译前端（不要动）
│   └── downloads/          # 随包资源：首页截图、客户端说明（可替换）
├── start_web.cmd           # ← 启动入口（双击即可，已固化端口 8091）
├── start_web.ps1           # PowerShell 启动（等价）
├── 迁移数据.cmd             # 旧版本升级时用（首次全新部署不需要）
├── 部署说明.txt
└── nw_web_data/            # ← 运行数据（首次启动后出现在**上一级目录**，不在本目录内！）
```

> **关键概念**：运行数据（反馈库、分享库、上传的截图、已发布的客户端 exe、管理员口令）
> 都在**部署目录的上一级** `nw_web_data/`，不在部署目录里面。这样以后升级只替换
> `reflex_web_embedded/`，数据不会被动。
> 例：部署到 `D:\nw\reflex_web_embedded` → 数据在 `D:\nw\nw_web_data\`。

---

## 2. 第 1 步：把部署包放到服务器上

1. 把整个 `reflex_web_embedded` 目录（**整个目录，不是里面的文件**）拷到服务器，例如：

   ```text
   D:\nw\reflex_web_embedded\
   ```

2. 路径要求（踩过坑）：
   - **不要放 `C:\Program Files`**（受保护目录，程序写日志/数据可能被拒）；
   - 路径**不要带中文或空格**（如 `D:\我的 程序\`），避免个别工具链的转义问题；
   - 预留写权限（数据目录 `D:\nw\nw_web_data` 也要可写）。

---

## 3. 第 2 步：确认 8091 真的能进来（Windows 防火墙）

网络策略放开 ≠ 服务器本机防火墙放开，两层都要。以**管理员**身份打开 CMD/PowerShell 执行：

```bat
netsh advfirewall firewall add rule name="协议解析平台 8091" dir=in action=allow protocol=TCP localport=8091
```

查看/删除该规则：

```bat
netsh advfirewall firewall show rule name="协议解析平台 8091"
netsh advfirewall firewall delete rule name="协议解析平台 8091"
```

> 如果你的安全软件（360/火绒/EDR）有独立防火墙，也需要放行 8091。

---

## 4. 第 3 步：启动服务

**方式 A（推荐先这样验证）**：进入部署目录，双击 `start_web.cmd`。

**方式 B（能看到报错，排查更方便）**：在该目录打开 CMD 执行：

```bat
cd /d D:\nw\reflex_web_embedded
start_web.cmd
```

**方式 C**：PowerShell：

```powershell
cd D:\nw\reflex_web_embedded
.\start_web.ps1
```

启动成功的标志（控制台里会依次出现）：

```text
[data] 运行数据目录: D:\nw\nw_web_data
[data]   data/     -> D:\nw\nw_web_data\data
[data]   downloads/-> D:\nw\nw_web_data\downloads
INFO:     Uvicorn running on http://0.0.0.0:8091 (Press CTRL+C to quit)
```

- 第一次启动会多花几秒（建数据目录、初始化数据库），属正常。
- **端口已固化**：启动脚本里写的就是 8091，不加参数也是 8091。临时换端口可用
  `start_web.cmd --port 9000`（覆盖本次启动，不改文件）。
- 关闭这个控制台窗口 = 停止服务。常驻方案见第 6 步。

---

## 5. 第 4 步：验证清单

| # | 从哪访问 | 期望结果 |
|---|---|---|
| 1 | 服务器本机浏览器 `http://127.0.0.1:8091/` | 打开**产品首页**（标题：多协议解析平台，页脚有版本号） |
| 2 | 局域网内另一台电脑 `http://<服务器IP>:8091/` | 同上（打不开 → 回第 3 步查防火墙/网络策略；用 `ipconfig` 查服务器 IPv4） |
| 3 | 首页点「进入在线工具」 | 跳到 `/app`，出现「单帧解析 / 批量解析 / …」9 个标签页 |
| 4 | 在线工具 → 单帧解析，粘贴 `68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16` 点「解析报文」 | 结果表格出现分层解析行（说明后端与前端都正常） |
| 5 | 首页 → 客户端下载（或在工具页点该标签） | 显示「客户端 exe 未就绪」是**正常的**：还没发布过客户端。见第 6 步 |

> 页面能打开但点击「解析报文」没反应/一直转圈：多半是 WebSocket 被拦（见第 9 步排错）。

---

## 6. 第 5 步：首次配置

1. **管理员登录**：在线工具页顶栏「管理员登录」→ 输入口令。
   - 初始口令见 `部署说明.txt` 或项目文档（默认 `admin123`）；**登录后请立刻在「发布管理」里改口令**。
2. **发布客户端 exe**（让「客户端下载」可用）：管理员登录 → 发布管理 Tab → 上传 `南网协议解析工具_vX.Y.Z_*.exe` → 系统写入 `nw_web_data/downloads/` 并刷新 `version.json`。
3. **换首页截图（可选）**：发布管理 Tab 上传新的界面截图（固定文件名 `client_screenshot.png`，写入数据根，优先于随包那张）。
4. **核对数据目录**：确认 `D:\nw\nw_web_data\` 下出现 `data\feedback.db`、`data\frameshare.db`、`downloads\`、`admin_config.json`。

---

## 7. 第 6 步：常驻运行与开机自启

> 注意：以下两种方式都会把启动脚本的工作目录设为部署目录，并把 `NW_WEB_DATA_DIR`
> 指到部署目录上一级（脚本内部逻辑），所以**不要**把 `start_web.cmd` 挪出部署目录单独运行。

### 方案 A：任务计划程序（无需第三方工具，推荐）

以**管理员**身份执行（`/RU SYSTEM` 表示开机即起、无需登录）：

```bat
schtasks /Create /TN "协议解析平台8091" /TR "\"D:\nw\reflex_web_embedded\start_web.cmd\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
```

- 启动服务：`schtasks /Run /TN "协议解析平台8091"`
- 停止服务：先 `netstat -ano | findstr :8091` 找到 PID，再 `taskkill /PID <PID> /T /F`（或直接删任务：`schtasks /Delete /TN "协议解析平台8091" /F`）
- 需要「失败自动重启」「崩溃重启」：在「任务计划程序」图形界面里打开该任务 → 设置 选项卡 → 勾选「如果任务失败，按以下频率重新启动」，并在 条件 选项卡取消「只有在计算机使用交流电源时才启动」。

### 方案 B：注册成 Windows 服务（需 NSSM，可选）

NSSM 是免安装的单文件工具（内网机器请提前拷入），配置好后服务可自启、崩溃自动拉起：

```bat
nssm install 协议解析平台 "D:\nw\reflex_web_embedded\start_web.cmd"
nssm set 协议解析平台 AppDirectory "D:\nw\reflex_web_embedded"
nssm set 协议解析平台 AppStdout "D:\nw\nw_web_data\service_out.log"
nssm set 协议解析平台 AppStderr "D:\nw\nw_web_data\service_err.log"
nssm set 协议解析平台 Start SERVICE_AUTO_START
nssm start 协议解析平台
```

> 不建议用 `sc.exe create` 直接注册 `.cmd`（它要的是 exe，`cmd.exe /c` 包一层会导致停止/重启语义不可靠）。

---

## 8. 第 7 步：备份与恢复

- **备份**：停服 → 整体拷贝 `D:\nw\nw_web_data\` 即可（反馈库 + 分享库 + 截图 + 已发布客户端 + 管理员口令全在里面）。
- **恢复**：把备份内容放回原位置（或把 `NW_WEB_DATA_DIR` 指到备份目录）后启动。
- 建议做成每周计划任务：`robocopy D:\nw\nw_web_data E:\backup\nw_web_data /MIR`。

---

## 9. 第 8 步：升级到新版本

1. **旧版本 < 1.23.14 的情况**：旧数据在**部署目录内部**（`reflex_web\data` 等）。升级前先执行一次产物里的 `迁移数据.cmd`（在旧部署目录里运行也可以），把数据搬到 `nw_web_data\`；**确认搬完再删除旧目录**。
2. 停服。
3. 用新版本目录**替换** `reflex_web_embedded\`（`nw_web_data\` 在上一级，不会被影响）。
4. 启动 → 打开首页确认反馈/分享/已发布版本都还在。
5. 全新部署（没有任何旧数据）不需要第 1 步。

> ⚠️ **不要**把新版本部署到与旧版本不同盘/不同命名层级，否则 `nw_web_data` 位置会变，数据看起来「不见了」（实际在旧盘的同级目录）。换位置时把 `nw_web_data` 一起搬。

---

## 10. 排错表

| 现象 | 原因 / 处理 |
|---|---|
| 双击窗口一闪而过 | 用 CMD 运行看报错：`cd /d D:\nw\reflex_web_embedded && start_web.cmd`；常见原因是端口被占或目录无写权限 |
| 局域网打不开，本机可以 | Windows 防火墙没放行 8091（见第 3 步）；或安全软件拦截；或网络策略未生效 |
| 提示端口被占用 | `netstat -ano \| findstr :8091` 找 PID → `tasklist \| findstr <PID>` 看是谁；换端口启动 `start_web.cmd --port 8092`（同时要放行新端口） |
| 页面能打开，但点解析一直转圈 | WebSocket 被拦（代理/安全软件）；或用了 `localhost` 访问而服务在别的机器上——统一用 `http://<服务器IP>:8091`；必要时 Ctrl+F5 强刷 |
| 控制台出现 `[data] 数据目录不可写` | 数据目录所在盘不可写。显式指定到可写位置后重启：<br>`set NW_WEB_DATA_DIR=D:\nw_web_data` 再 `start_web.cmd`（`start_web.ps1` 用 `$env:NW_WEB_DATA_DIR = 'D:\nw_web_data'`） |
| 首页截图/客户端说明显示「待更新」 | 随包资源缺失（打包时被排除）；把图片放到 `D:\nw\nw_web_data\downloads\client_screenshot.png` 即可覆盖 |
| 客户端下载显示「未就绪」 | 还没发布客户端：管理员登录 → 发布管理 → 上传 exe |
| 控制台中文乱码 | 只是显示问题（CMD 代码页），不影响功能；可先执行 `chcp 936` 再启动 |
| 升级后数据「不见了」 | 检查是否换了部署目录层级/盘符：数据始终在部署目录的**上一级** `nw_web_data\` |
| 想确认服务实际监听 | `netstat -ano \| findstr :8091` 应看到 `0.0.0.0:8091 LISTENING` |

---

## 11. 常用命令速查

```bat
:: 启动 / 停止（手动方式）
cd /d D:\nw\reflex_web_embedded && start_web.cmd
taskkill /PID <netstat 查到的 PID> /T /F

:: 端口与进程
netstat -ano | findstr :8091

:: 防火墙
netsh advfirewall firewall add rule name="协议解析平台 8091" dir=in action=allow protocol=TCP localport=8091

:: 开机自启（任务计划）
schtasks /Create /TN "协议解析平台8091" /TR "\"D:\nw\reflex_web_embedded\start_web.cmd\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F

:: 数据目录
dir D:\nw\nw_web_data
```

---

## 12. 附：这个包是怎么构建出来的（需要再出包时用）

在有网、与目标机同架构的 Windows 机器上（仓库根目录执行）：

```bash
# 首次/换依赖：完整构建（会下载内嵌 Python 与依赖，10+ 分钟）
python reflex_web/build_embedded_deploy.py --python-version 3.12 --port 8091

# 日常迭代（只改了源码/数据文件）：增量构建，分钟级
python reflex_web/build_embedded_deploy.py --skip-deps --port 8091
```

- `--port 8091`：把端口固化进启动脚本（不加则默认 8080）。
- 产物：`dist/reflex_web_embedded/`，整体拷到目标机即可。
- 前端页面有改动时脚本会自动重新编译前端；源码改动后**重新构建一次**再升级。
- 相关文档：`reflex_web/离线部署.md`（部署机制与数据目录细节）、`AGENTS.md §2/§8`（维护者约定）。
