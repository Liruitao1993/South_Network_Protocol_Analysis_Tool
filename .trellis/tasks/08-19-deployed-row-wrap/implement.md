# 实施：修复部署后特殊帧单帧解析行显示满

## 目标
修复内嵌部署包前端 bundle 陈旧导致换行 CSS 未生效的问题。

## 根因
`build_embedded_deploy.py::ensure_frontend()` 只在 `.web/build/client` 缺失时执行 `reflex export`；已存在则无条件复用陈旧 bundle。CSS 写在 `.py` 源码（`GLOBAL_CSS` → `rx.el.style()`），编译器检测不到其「过期」，增量/重复构建把修复前的 bundle 打进部署包。运行时从部署目录 `.web/build/client` serve，故页面旧。

实证：换行修复 `6e15828` 提交于 08-18 15:19，bundle 构建于 08-18 10:13；bundle 仅含 Radix 默认 `overflow-wrap: break-word`，无 `word-break: break-all`。

## 修复
两个构建脚本（embedded + offline）同步：
- 新增 `_frontend_sources()`：返回会编译进 bundle 的源码（`reflex_web/reflex_web/*.py|pyx|txt|md` + `rxconfig.py`）。
- `ensure_frontend(*, force=False)` 增加新鲜度判定：任一源码 mtime > bundle 内最新文件 mtime → 强制重新 export。

## 重建
用 `python reflex_web/build_embedded_deploy.py --skip-deps` 增量重打部署包（保留 python/，44s）。本次构建输出「==> 前端产物已是最新」即新逻辑正确工作（bundle 已重建为较新）。

## 验证
- 新 bundle `_index-D2Ve9_b7.js`（新 hash）含 `.rt-TableCell` 换行规则；旧 bundle 无。
- 部署包 `dist/reflex_web_embedded/reflex_web/.web/build/client/assets/` 与工作区 bundle 全部 1971 个 asset 逐字节一致。
- 部署包 bundle 含 `word-break: break-all: True`。
- 运行服务 HTTP 200，页面引用新 entry.client，消费含修复 chunk。
- UI 视觉确认因 harness 的 browser/computer 工具环境不可用未能执行（与本次改动无关）；字节级 + 运行时证据已足够。

## 状态
完成。新增 `dist/reflex_web_embedded` 已可复制到目标机器复验。

## UI 视觉实测（补充，2026-08-19）
用真实浏览器（headless Chromium）驱动部署 bundle 起服后解析一帧含 136 字符长 hex 的南网帧：
- 解析结果表 12 个单元格计算样式全部为 `white-space: normal | word-break: break-all | overflow-wrap: anywhere`。
- 长 hex 单元格（`<td class="rt-TableCell"><code>…</code></td>`, 136 字符）同样应用 `break-all`，不再单行撑爆列宽。
主任务「部署后特殊帧行显示满」修复彻底验证通过。

## 调试中发现的旁路问题（run_app 端口重写 bug，与本任务无关但应关注）
`reflex_web/run_app.py` 的 `_rewrite_env_js` 用 `_HTTP_PREFIX="http://localhost:8000"` / `_WS_PREFIX="ws://localhost:8000"` 匹配并重写 env.js 里的硬编码 URL；但 reflex 0.9.8 导出前端时 `reflex-env-*.js` 实际硬编码的是 **`localhost:8002`**（非 8000）。匹配串与硬编码不符 → 重写永不生效 → 非默认端口启动时 WebSocket 连 `ws://localhost:8002/_event` 失败（浏览器实测复现：端口 8099/8080 启动后点解析报 "Cannot connect to server: websocket error"，端口 8002 启动则正常）。仅在 --port 恰为 8002 时可用。建议后续把匹配前缀改为 8002 或用正则泛化替换。