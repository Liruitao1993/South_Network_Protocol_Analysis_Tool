# PRD：修复部署后特殊帧单帧解析行显示满

## 背景

用户在目标机器（内嵌 Python 部署 `dist/reflex_web_embedded`）解析特殊长数据帧时，单帧解析结果表格的行显示很满（长 hex 不换行、撑爆列宽）。

此前已在源码（`reflex_web/reflex_web/reflex_web.py` 的 `GLOBAL_CSS`）加过 `.rt-TableCell { white-space: normal; word-break: break-all }` 与 `.rt-TableCell code` 换行规则（commit `c6fa69e` / `6e15828`），**但部署机仍满**。

## 根因（已诊断证实）

部署包内嵌的前端 bundle 是**修复前构建**的陈旧产物：

- 换行修复 `6e15828` 提交于 `2026-08-18 15:19`
- `.web/build/client` bundle 构建于 `2026-08-18 10:13`（早 5 小时）
- 内嵌部署 `dist/reflex_web_embedded/reflex_web/.web` 是同一份 10:13 副本（mtime 一致）
- bundle 里只有 Radix 默认 `overflow-wrap: break-word`，**无**我们的 `word-break: break-all`（对超长连续 hex 不生效）

**构建脚本缺陷**：`reflex_web/build_embedded_deploy.py::ensure_frontend()` 只在 `.web/build/client` **缺失**时才执行 `reflex export`；已存在则无条件复用。CSS 存在于 `.py` 源码，编译器检测不到它「过期」，导致增量/重复构建把陈旧 bundle 打进部署包。

运行时从部署目录的 `.web/build/client` serve 前端（`run_app.py::_setup_frontend_static`），所以 bundle 旧 → 页面旧。

## 目标

1. **治本**：修复构建脚本，使前端产物在源码变更后能被正确刷新，不再复用陈旧 bundle。
2. **补包**：重新 export 前端并重打内嵌部署包，让当前发布立即生效。

## 范围

- 修改 `reflex_web/build_embedded_deploy.py` 的前端新鲜度判定逻辑。
- 重新构建内嵌部署包。
- 同步 `reflex_web/build_offline_deploy.py`（UV 方案同缺陷）。
- 不改动 `reflex_web.py` 的 CSS 本身（换行规则已是正确的，只是没进 bundle）。
- 更新 AGENTS.md / README / 离线部署文档的构建注意说明。

## 验收标准

1. `.web` bundle 重建后，`__reflex_global_styles-*.css` 含 `.rt-TableCell` 的 `word-break: break-all` / `white-space: normal`。
2. 重新构建的部署包副本 bundle 同样含修复。
3. 修改 `reflex_web.py` 后运行构建脚本，前端能自动重新 export（新鲜度判定生效）。
4. 特殊长帧（如 129 字节 octet-string）单帧解析在浏览器实测不再撑满行。