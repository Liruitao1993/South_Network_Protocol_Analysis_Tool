# 客户端下载目录

> 本目录（`reflex_web/downloads/`）只放**随部署包分发的静态资源**；运行时的发布产物在**数据根**里。

## 随包静态资源（进部署包，随代码更新）

| 文件 | 用途 |
| --- | --- |
| `client_screenshot.png` | 首页 Hero 截图 |
| `client_readme.md` | 「客户端说明」正文（版本号 / 协议表 / 更新记录） |
| `README.md` | 本说明 |

清单的单一来源是 `reflex_web/reflex_web/app_data.py::PACKAGED_DOWNLOAD_ASSETS`，构建脚本
（`deploy_common.DOWNLOADS_ASSETS`）按同一清单拷贝 —— **新增随包资源必须两边同步**，
`test/test_web_data_paths.py` 会盯着。

## 运行时发布产物（**不**进部署包，位于数据根）

| 文件 | 说明 |
| --- | --- |
| `version.json` | 当前发布的版本号 / 下载地址 / sha256 / 更新说明 |
| `*.exe` | 对应版本的安装包 |
| `archive/` | 历史版本 |

数据根解析顺序见 `app_data.downloads_dir()`：`NW_WEB_DATA_DIR`（启动脚本注入）→ 冻结态
exe 同级 `nw_web_data/` → 回落代码目录（仅开发态）。

- **正式发布**用 Web 的「发布管理」页上传 exe 与版本信息，会写进数据根，**无需改代码**；
- 升级部署目录不影响数据根，因此已发布的版本号与安装包会保留；
- 不要在代码目录里手工堆 exe：既不进部署包，也会让本地开发态显示成旧版本。
