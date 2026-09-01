# 引入 Lucide 开源图标库到 icons/ 目录

## Goal

批量获取开源图标库 SVG 资源放入项目 `icons/` 目录，为后续 GUI 美化
（按钮/菜单/标签页/系统托盘图标）储备素材。本任务只做「下载 + 落盘 +
许可证合规」，GUI 集成（QIcon 替换）是后续独立任务。

## Why 不爬 iconfont.cn

- 官方批量下载需登录并加入项目；匿名只能拿搜索页预览，批量爬取触发风控
  且违反站点条款。
- 图标由用户上传，授权条款逐个不一，商业软件使用有版权风险。
- 风格不统一。

Lucide（https://lucide.dev，ISC 许可，可商用/修改/再分发，需保留版权声明）
约 1500+ 枚线性 SVG，风格统一，专为软件 UI 设计，Qt QIcon 原生支持 SVG。

## Requirements

- 通过 npm registry 下载 `lucide-static` tarball（纯静态资源包：icons/*.svg +
  字体 + LICENSE），不依赖 git clone 整个仓库。
- 解压后把 `icons/*.svg` 放到 `icons/lucide/`（与现有 `icons/refresh.svg` 隔离）。
- 复制 Lucide LICENSE 到 `icons/lucide/LICENSE`，并在 `icons/README.md` 写明
  来源、版本、许可、用途（保留版权声明义务）。
- 记录下载的 lucide-static 版本号（写进 README 与任务）。
- SVG 完整性校验：文件数 > 1000，随机抽样 XML 可解析、根元素为 `<svg>`。

## Acceptance Criteria

- [ ] `icons/lucide/` 存在且含 1000+ 个 `.svg` 文件。
- [ ] `icons/lucide/LICENSE` 存在（ISC 许可文本）。
- [ ] `icons/README.md` 记录来源 URL、版本号、许可、商用条件。
- [ ] 抽样 20 个 SVG 通过 XML 解析且根标签为 svg。
- [ ] 现有 `icons/refresh.svg` 不受影响。
- [ ] 下载用的临时文件（tarball/解压临时目录）清理干净。
- [ ] spec 打包文件 `南网协议解析工具.spec` 暂不改动（图标集成任务再评估
      datas 是否需要打包 icons/）。

## Notes

- 集成点（后续任务用）：`main_gui.py`、`diff_widget.py`、
  `system_integration/sys_tray.py` 当前使用 QIcon。
- GUI 常用图标候选：file/folder/save/download/upload/settings/tool/network/
  wifi/activity/database/terminal/copy/paste/search/refresh-cw/x/check/
  alert-triangle/info/zap/radio/cpu/clipboard-list 等。
