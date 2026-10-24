# 同步 Web 下载区版本信息到 1.24.0

## Goal

目标服务器已发布 1.24.0，但工程内 reflex_web/downloads/version.json（本地数据根，gitignore）仍是 1.14.13 的 LAN 地址，且随部署包分发的 client_readme.md 仍写 1.14.0 / 12 种协议。同步为 1.24.0 / 16 种协议 + GitHub Release 资产地址与 sha256，并用纯逻辑校验（与 protocol_registry 对拍）。

## Requirements

- `reflex_web/downloads/version.json`（本地数据根，gitignore + 部署排除）→ `1.24.0` + GitHub Release 资产绝对地址 + `ca7d9708…f15fce`
- `reflex_web/downloads/client_readme.md`（**随部署包分发**）→ 版本 1.24.0、16 种协议、协议表补 12~15 行、纠正已移除的 Textual TUI / NiceGUI Web 与主题数量、补 1.24.0 更新记录
- `reflex_web/downloads/README.md`（随包）→ 重写「随包静态资源 vs 运行时发布产物（数据根）」
- 不改部署逻辑、不改 `app_data` / `deploy_common` 白名单

## Acceptance Criteria（全部已验证）

- [x] 协议表与 `protocol_registry` 对拍：16 行、索引 0~15 连续、名称逐行对应
- [x] `client_readme.md` 中无 `1.14.0` 当前版本字样（仅历史标题）、无「12 种」、无过时的 TUI/NiceGUI 现状描述
- [x] `app_data.downloads_dir()/version.json` 读到 `1.24.0` / `v1.24.0_20261024160025.exe` / sha `ca7d97…`
- [x] `web_utils.resolve_download_target` 对 LAN host 与 dev host 都返回 GitHub Release 资产地址（外部主机优先）
- [x] Release 资产 URL 实测 HTTP 302 → 200，`Content-Length: 105030178`
- [x] `test_web_landing`(104) / `test_web_download_url`(35) / `test_web_data_paths`(126) 全绿
- [x] 提交 `328b665`（2 文件 +58/−15）

## Notes

- `version.json` 被 `reflex_web/.gitignore` 与 `deploy_common` 双重排除 ⇒ 只在本地工作区同步，
  **不会**随部署包下发，也不会覆盖目标服务器 `nw_web_data/` 里已发布的版本。
- 真正随包的是 `client_readme.md` / `README.md` / `client_screenshot.png`，所以本轮重点修的是它们。
