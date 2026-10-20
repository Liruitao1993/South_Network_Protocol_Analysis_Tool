# Gitee 镜像与国内分发

> **这一节可能是整个推广里对「实际使用人数」影响最大的一步。**
> 最新版 exe 约 100 MB，从 GitHub 在国内经常只有几十 KB/s、或者直接断连。
> 一个想试用的工程师，下载失败两次就不会再来第三次 —— 这一步不通，前面所有内容都白做。

---

## 一、为什么要镜像

| 渠道 | 国内下载体验 | 是否需要 |
| --- | --- | --- |
| GitHub Release | 慢 / 常断 / 部分网络完全不可达 | 保留（国际用户 + 开发者） |
| Gitee 仓库 + Release | 快、稳定 | **强烈建议** |
| 网盘（123 云盘 / 蓝奏云） | 最快，适合发给不熟悉 git 的人 | 建议（群内转发用） |

---

## 二、Gitee 镜像怎么建（10 分钟）

### 1. 导入仓库

1. 登录 [gitee.com](https://gitee.com) → 右上角 `+` → **新建仓库** → 选择 **导入已有仓库**
2. 填 GitHub 地址：`https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool.git`
3. 仓库名建议：`South_Network_Protocol_Analysis_Tool`（与 GitHub 一致，便于记忆）
4. 设为**开源**，许可证选 **MIT**

> 注意：Gitee 对单仓库大小有限制。当前仓库约 96 MB，**应该能通过**，
> 但如果导入失败，多半是历史大文件（PDF/MD 协议文档）导致 —— 见下方「常见阻塞」。

### 2. 配置同步

Gitee 的「导入」是一次性的，之后需要手动或自动同步：

- **手动**：仓库页 → `+` → **强制同步**（pull GitHub 最新）
- **自动**：仓库 → 管理 → **仓库镜像管理** → 添加 `Pull` 镜像，填 GitHub 地址 + 你的 token

> 如果你更习惯命令行，也可以在本地加一个 remote：
> ```bash
> git remote add gitee https://gitee.com/<你的用户名>/South_Network_Protocol_Analysis_Tool.git
> git push gitee main
> git push gitee --tags
> ```

### 3. 上传 Release 包（关键）

Gitee 的 Release 附件有大小限制（免费版通常单文件 ≤ 100 MB）。
当前 exe 约 **100 MB**，**正好卡在边界**，可能失败。三个应对方案：

| 方案 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| A. 分卷压缩 | 用 7-Zip 按 90 MB 分卷，上传 2 个包 | 一定能传 | 用户要下两个包再解压 |
| B. 网盘外链 | Release 里只写说明，正文放网盘直链 | 最快 | 依赖网盘稳定性 |
| C. 精简体积 | 去掉 `reflex` / `scapy` 等可选依赖另出「精简版」 | 包小、启动快 | 少功能 |

> 推荐 **B 为主 + A 为备**：Release 正文写「国内用户请用网盘」，附件放分卷包。
> 网盘建议：123 云盘（免登录下载）或蓝奏云（≤100 MB 限制注意）。

### 4. 同步更新 README

在 Gitee 仓库的 README 顶部加一行（Gitee 不会自动改你的 README，需要单独维护或接受它与 GitHub 一致）：

```markdown
> 国内用户请使用 **[Gitee 镜像](https://gitee.com/<你的用户名>/South_Network_Protocol_Analysis_Tool)**，下载更快；
> GitHub 为源码主仓库，Issue/PR 请提到 GitHub。
```

---

## 三、网盘直链怎么放

发给行业群 / 微信时，**不要发 GitHub 链接**，发网盘：

```
电力报文解析工具（Windows 免安装，双击即用）
下载：https://xxxx
解压后直接运行 exe，不需要装 Python
有问题把报文 hex 发我
```

建议在网盘目录里同时放一份 `使用说明.pdf`（仓库里已有 `协议解析工具使用指南.pdf`）。

---

## 四、自动更新要怎么配

仓库里 `auto_updater.py` 已支持 **GitHub / Gitee / 私有源** 三种更新源。
如果主仓库迁到 Gitee，建议把更新源改成 Gitee，否则国内用户的自动更新会一直超时：

- 检查 `config.json` / 设置页里的更新源配置
- 确认 Release 的 tag 格式与 `auto_updater.py` 解析逻辑一致（当前是 `1.23.86` 这种纯版本号）

> 这一项属于**功能验证**而不是推广：如果更新源指向 GitHub，国内用户会每天看到「检查更新失败」，
> 体验比没有更新更差。上线前务必实测一次。

---

## 五、常见阻塞

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Gitee 导入卡在 90% | 仓库含大文件历史 | 用 `git gc` 压缩，或对协议文档改用 Git LFS / 外链 |
| Release 上传失败 | 单文件超限 | 分卷压缩，或改网盘 |
| 镜像后 star/issue 分散 | 两个仓库都有入口 | 在 README 明确写「Issue 统一提到 GitHub」，Gitee 关掉 Issue |
| 同步冲突 | 在 Gitee 上直接改了文件 | 约定只读镜像，所有改动只在 GitHub |

---

## 六、做完后的检查

- [ ] Gitee 仓库能打开，README 正常显示（注意图片路径，Gitee 支持相对路径）
- [ ] Gitee Release 有可下载的包，**用手机热点实测下载一次**
- [ ] README 顶部有 Gitee 链接
- [ ] 网盘链接可用，且没设提取码（或提取码写在文案里）
- [ ] 自动更新源已指向国内可达的地址，并实测通过
