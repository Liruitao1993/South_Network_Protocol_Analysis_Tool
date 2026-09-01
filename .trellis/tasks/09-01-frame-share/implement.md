# 实施计划 — 报文分享

## 执行顺序

### Step 1: share_model.py（新文件，纯逻辑）

- [ ] `reflex_web/reflex_web/share_model.py`：
  - `ShareItem(rx.Model, table=True)`（created_at/frame_hex/protocol/sharer/note/source）
  - `data_dir()`（FRAMESHARE_DATA_DIR 覆盖）+ `db_path()` + `uploads` 无
  - `ShareStore` 单例：add / list_page(page, per_page, keyword) / get
  - `normalize_hex()` / `submit_share()` / `share_config()` 纯函数
  - 复用 feedback_model.FeedbackRateLimiter（import）
- 验证：`python -c "import reflex_web.share_model"`（Windows python.exe）

### Step 2: Web 路由 + /share 页面 + 主页集成

- [ ] reflex_web.py：
  - ShareState（sh_*列表态 + sf_* 表单态，独立 State）
  - dev 路由：POST /api/frameshare + GET /api/frameshare/config + OPTIONS（频率限制 10/60s）
  - share_page() 组件 → add_page(route="/share")；header() 加「报文分享」链接
  - 主页：分享弹窗（sf_open 受控三件套）+ State.last_hex/last_protocol_name 缓存 + 解析按钮行加「分享此帧」
  - 详情「去解析」：/share 详情弹窗链接 /?parse_hex=&protocol= → 主页 on_load 读取并自动填入解析
- [ ] run_app.py：`_handle_frameshare_api`（JSON 读 body ≤64KB / json.loads / 响应 / OPTIONS 204）
- 验证：`python -c "import reflex_web.reflex_web as rw; rw.share_page()"` 组件渲染；dev 服务热重载无错

### Step 3: GUI share_dialog.py + main_gui 集成

- [ ] `share_dialog.py`（新）：ShareDialog(QDialog)——只读 hex、协议下拉、分享人（config share.last_sharer 记忆）、说明、JSON POST（复用 feedback server_url 配置）、成功跳转 /share
- [ ] main_gui.py：按钮行加「分享此帧」（current_result 空则提示）+ `_show_share_dialog`（懒 import）
- 验证：`python -c "import share_dialog"` + offscreen 创建

### Step 4: 测试 test/test_frame_share.py

- [ ] normalize_hex 边界 / submit_share 校验分支 / ShareStore CRUD+分页+搜索（含无空格 hex 匹配）/ 频率限制 / GUI payload + offscreen 冒烟
- [ ] 回归：test_web_feedback(49) / test_feedback_api(31) / test_feedback_dialog(30) / test_quick_parse_panel(84) / test_web_frame_gen_utils(63)
- 验证：`PYTHONUTF8=1 python.exe test/test_frame_share.py` 退出码 0

### Step 5: 文档 + 提交归档

- [ ] AGENTS.md（架构树 share_model.py/share_dialog.py、测试清单、§6 顶部导航说明）、README、CHANGELOG 1.21.0（版本 bump + BUILD_DATE）
- [ ] 真机 e2e：dev 服务起 → curl POST /api/frameshare → /share 页可见 → GUI 对话框提交 → source=gui 落库
- [ ] git 提交 feat(frame-share) → task.py archive

## 验证命令汇总

```bash
PYTHONUTF8=1 python.exe test/test_frame_share.py
PYTHONUTF8=1 python.exe test/test_web_feedback.py        # 回归
PYTHONUTF8=1 python.exe test/test_feedback_dialog.py     # 回归
cd reflex_web && python -c "import reflex_web.reflex_web as rw; rw.share_page()"
```

## 回滚点

- Step 1/3 纯新增文件，删除即回滚
- reflex_web.py / main_gui.py 改动均为增量块，git checkout 可还原
