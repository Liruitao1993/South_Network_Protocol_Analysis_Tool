# 技术设计 — 报文分享（Web 页面 + GUI 提交，共享数据库）

## 1. 总体架构

```text
GUI 单帧解析页                 Web 服务端                      Web 浏览器
┌──────────────┐   JSON POST  ┌───────────────────┐   浏览    ┌─────────────┐
│ share_dialog │ ───────────▶ │ POST /api/frameshare│          │ /share 页面  │
│ (QDialog)    │              │ GET  /api/frameshare/config│    │ 列表+搜索+详情│
└──────────────┘              └─────────┬─────────┘          └─────────────┘
      Web 解析结果区「分享此帧」 ────────▶│  ShareStore（share_model.py）
                                        ▼
                         reflex_web/data/frameshare.db（SQLite）
```

- 存储层独立文件 `reflex_web/reflex_web/share_model.py`（不与 feedback_model 混合——表不同、库不同、生命周期独立；仅复用 `FeedbackRateLimiter`）。
- 部署脚本零改动：`data/` 目录整体保留逻辑已覆盖新库文件。

## 2. 数据模型（share_model.py）

```python
class ShareItem(rx.Model, table=True):
    created_at: str = ""     # "YYYY-MM-DD HH:MM:SS"
    frame_hex: str = ""      # 空格分隔大写 hex（服务端规范存储）
    protocol: str = ""       # 协议显示名（如 "[0] 南网协议 (Q/CSG1209021-2019)" 简化为 "南网协议"）
    sharer: str = ""         # 分享人 ≤50
    note: str = ""           # 说明 ≤500，选填
    source: str = "web"      # web/gui
```

`ShareStore`（单例，模式复刻 FeedbackStore）：

- `db_path()`：`Path(__file__).parent.parent / "data" / "frameshare.db"`（FEEDBACK_DATA_DIR 环境变量同款覆盖机制 → `FRAMESHARE_DATA_DIR`，测试隔离）
- `add(item) -> id`；`list_page(page, per_page, keyword) -> (items, total, pages)`（keyword 空则全量；SQL 用 `sqlmodel.or_(contains(...))`——hex 搜索额外做 `frame_hex.replace(" ","")` 去空格列？**否**：SQLite 不支持生成列写法复杂，改为**双 like**：`or_(ShareItem.frame_hex.contains(kw), ShareItem.frame_hex.contains(" ".join(kw[i:i+2] for i in range(0,len(kw),2))))` 处理无空格输入，简单可靠）
- `search(keyword)`：or_(frame_hex.contains, protocol.contains, sharer.contains, note.contains)
- `get(item_id) -> ShareItem | None`
- 纯函数：
  - `normalize_hex(hex_str) -> str | None`：清洗（去 0x/空格/逗号）→ 校验偶长+hex 字符+字节长 2~2048 → 返回空格分隔大写；非法返回 None
  - `submit_share(fields) -> (ok, id_or_error, status)`：protocol 白名单校验（GUI 传入 `config` 下发的列表或"不确定"）、sharer 必填 ≤50、note ≤500、source 白名单归一、normalize_hex 失败报"报文格式无效"
  - `share_config() -> dict`：{ok, protocols, max_note_len, max_frame_bytes, max_sharer_len}

## 3. Web 服务端路由（双模式，同反馈套路）

- **dev**（reflex_web.py 尾部 Starlette Route）：
  - `POST /api/frameshare`：`await request.json()` → `submit_share` → JSON 响应（CORS 反射 Origin，同反馈中间件）
  - `GET /api/frameshare/config`：share_config()
  - 频率限制：模块级 `FeedbackRateLimiter(max_calls=10, window=60)` 按客户端 IP
- **prod**（run_app.py 中间件）：`/api/frameshare` 前缀分支 `_handle_frameshare_api`——读 body ≤64KB、json.loads、异常兜底、JSON 响应（无 multipart，比反馈简单）
- OPTIONS 预检 204（反射 Origin）。

## 4. Web UI（reflex_web.py 内新增）

### 4.1 ShareState(rx.State) —— 独立 State（不继承主 State：分享页无管理操作，不需 admin_logged_in）

```python
class ShareState(rx.State):
    sh_items: list[dict] = []
    sh_page: int = 1
    sh_pages: int = 1
    sh_total: int = 0
    sh_keyword: str = ""
    sh_detail: dict = {}
    sh_detail_open: bool = False
    sh_msg: str = ""
    # 提交表单（web 端分享）
    sf_open: bool = False
    sf_hex: str = ""         # 主页解析后点击分享带入
    sf_protocol: str = ""
    sf_sharer: str = ""
    sf_note: str = ""
```

事件：

- `sh_load()`：list_page(sh_page, 20, sh_keyword) → sh_items/pages/total
- `sh_search(kw)`（输入框 on_change 防抖由前端 `on_change` 直接触发，Reflex 天然节流）→ 置 page=1 + sh_load
- `sh_next/sh_prev`：翻页 + sh_load
- `sh_open_detail(item)` / `sh_close` / `sh_on_open_change(is_open)`：受控弹窗三件套（feedback 同款）
- `sf_open_dialog(hex, protocol)`（主页解析结果区按钮触发，带当前帧与协议）→ sf_open=True
- `sf_submit()`：本地校验 sharer 非空 → submit_share({..., source:"web"}) → 成功关弹窗 + 提示"分享成功" + sh_load

### 4.2 页面 `/share`（app.add_page，路由 /share）

- 复用 `header(show_parse_controls=False)`（含新的「作者博客」「报文分享」链接）
- 布局：标题行（「报文分享」+ 计数 + 「主页解析后可分享」提示）→ 搜索框（`rx.input` on_change=ShareState.sh_search, placeholder="搜索 报文hex/协议/分享人/说明"）→ 列表（rx.foreach sh_items → 卡片：rx.badge 协议 + 来源徽章（rx.cond source=="gui" 青色「桌面端」）+ 分享人/时间 + hex（`rx.code` 等宽，`rx.text` 截断 via CSS ellipsis）+ note 摘要）→ 分页行（上一页/第x/y页/下一页）
- 详情弹窗（受控三件套）：完整 hex（rx.code + 复制按钮 `rx.clipboard`）+ 协议/分享人/时间/说明 + 「去解析」链接 → `/?parse_hex=...&protocol=...`（URL 带参，主页 on_load 读取 rx.router.params）
- 主页改造：
  - `State` 增加 `parse_hex_param` / `parse_protocol_param`；`index` 页 `on_load=State.check_parse_params`：URL 带 parse_hex 时 → 填入 single_input（通过已有关联机制：State 变量绑定输入框 default_value 或事件后 set）并自动 parse
  - 解析结果区（主页单帧解析 tab 的按钮行）：新增「分享此帧」按钮 → `ShareState.sf_open_dialog(State._last_hex, State._last_protocol_name)`——需要 State 在 parse 时缓存 hex/协议名：`State.last_hex: str = ""`、`State.last_protocol_name: str = ""`（parse_single 已有对应 Python 侧，Reflex State 侧在 `parse_frame` 事件里同步赋值）
  - 分享弹窗（sf_open 受控）：hex 只读展示 + 协议下拉（12 种 + 当前选中默认）+ 分享人输入（必填）+ 说明 textarea → 提交按钮 `on_click=ShareState.sf_submit`；错误提示条

### 4.3 导航

- header() 「作者博客」后加「报文分享」链接 href="/share"（data_testid="nav-share"）
- 主页 Tab 方案否决（反馈列表已在主页 Tab，分享页独立路由更清晰且避免主页过载）——用户需求"增加一个页面"即独立页面。

## 5. GUI 客户端（share_dialog.py 新文件）

```text
┌ 分享此帧 ────────────────────────────┐
│ 报文（只读，QPlainTextEdit 等宽 3 行） │
│ 协议 [当前协议 ▾]（12+不确定）        │
│ 分享人 * [________]（记住上次）       │
│ 说明 [________]（≤500，预填版本信息） │
│ 服务器: http://... （同 feedback.server_url）│
│ [提示条]                 [分享]      │
└─────────────────────────────────────┘
```

- `ShareDialog(QDialog, parent, frame_hex, protocol_name, app_version)`：
  - 构造期由 main_gui 传入 `self._last_parsed_hex`（空格 hex）与 `protocol_combo.currentText()`
  - JSON POST：`req.setHeader(ContentTypeHeader, "application/json"); req.setBody(json.dumps(payload, ensure_ascii=False).encode("utf-8"))`；20s 超时；finished 回调解析 JSON
  - 成功 → QMessageBox + 可选"打开分享页"（QDesktopServices /share URL）→ accept()
  - 服务器地址读写复用 feedback_dialog 的 `load/save_feedback_server_url`（同一配置段，GUI 只有一台服务器）
- main_gui.py 集成：
  - 按钮行「添加到测试方案」后加「分享此帧」（set_btn success, set_btn_icon share）→ `_show_share_dialog`
  - `_show_share_dialog`：`current_result` 为空时提示"请先解析报文"；懒 import share_dialog

## 6. 测试设计（test/test_frame_share.py）

1. `normalize_hex`：空格/0x/逗号清洗、大写化、偶长校验、2~2048 字节边界、非法字符拒绝
2. `submit_share`：正常（source=gui）、sharer 空/超长、note 超长、协议白名单外、hex 非法（400 系列）
3. `ShareStore` CRUD：临时目录 add/list_page 分页/get/搜索（hex 含无空格连续输入匹配、协议、分享人、说明）
4. 频率限制：10 条后 429 语义（复用 limiter 单测逻辑）
5. dev 路由回归：import 编译级验证 + submit JSON 序列化往返
6. GUI `ShareDialog` 纯逻辑：URL 规范化复用、config 读写（last_sharer 段）、payload 构造（json.dumps 结果含字段名与值）、offscreen 冒烟（控件存在/协议下拉项数/预填值）
7. 回归：feedback/api/dialog/qp/frame_gen 全套件

## 7. 安全与边界

- hex 服务端 normalize（规范存储），分享内容纯文本 → Reflex 默认转义无 XSS
- 频率限制 10/60s；body ≤64KB 上限（2048B hex ≈ 6KB 上限 + 字段余量）
- 无认证（内网信任）；分享人自报（不做账号体系）
