# 实施计划 — Web版问题反馈页面

## 执行顺序

> 前置：Phase 1 完成审查，`task.py start` 后才动手。

### Step 1: feedback_model.py（新文件，纯逻辑）

- [ ] `reflex_web/feedback_model.py`：
  - `FeedbackItem(rx.Model, table=True)`（字段见 design.md §2）
  - `data_dir() -> Path`（基于 `__file__` 定位 `reflex_web/data/`，支持 `FEEDBACK_DATA_DIR` 环境变量覆盖供测试）
  - `get_store() -> FeedbackStore`（单例，懒加载，create_all 幂等）
  - `FeedbackStore`: add / list_all / count_pending / update_status / delete
  - `save_screenshot(data, orig_name) -> str`（扩展名+魔数+大小校验，重生成文件名）
  - `delete_screenshots(names) -> int`（防穿越）
- 验证：`python -c "import reflex_web.feedback_model"`（Windows 侧 python.exe，Reflex 已装）

### Step 2: reflex_web.py 集成

- [ ] 新增 `FeedbackState`（表单字段、上传处理、提交、管理页事件）
- [ ] 新增 `feedback_page()` 组件 → `app.add_page(feedback_page, route="/feedback", ...)`
- [ ] 新增 `feedback_admin_page()` → route `/feedback-admin`（口令卡 + 列表 + 详情弹窗 + 分页）
- [ ] `header()` 加「问题反馈」入口链接
- [ ] dev 模式截图路由 `/fbimg/{path}`（镜像 `_dev_download_handler`）
- 验证：`cd reflex_web && reflex export --frontend-only --env prod --no-zip` 前端编译通过（或 dev 模式起服务冒烟）

### Step 3: run_app.py 截图路由

- [ ] `_serve_fbimg`（生产 ASGI 中间件 `/fbimg/` 前缀 → `data/uploads/feedback/`，防穿越、图片内联）
- [ ] `env_rewrite_middleware` 分发接入
- 验证：代码审查 + Step 4 测试

### Step 4: 测试 test/test_web_feedback.py

- [ ] 按 design.md §7 编写（文件头含 `import _path_setup  # noqa: E402`）
- [ ] 运行：`PYTHONUTF8=1 python.exe test/test_web_feedback.py`（项目根）
- [ ] 回归：`PYTHONUTF8=1 python.exe test/test_web_frame_gen_utils.py`
- [ ] `cp936` 控制台注意：测试输出避免直接 print 特殊字符（用 ASCII 标记 OK/FAIL）

### Step 5: 部署脚本持久化

- [ ] `build_embedded_deploy.py`：`PRESERVED_DIRS` 机制（python/data，完整+增量模式都保留 data/）
- [ ] `build_offline_deploy.py`：rmtree 前 data/ 移出重建后移回
- [ ] 抽 `_preserve_data_dirs`/`_restore_data_dirs` 纯函数供测试
- 验证：测试脚本模拟目录往返；真实 `--skip-deps` 构建后人工确认 `dist/reflex_web_embedded/reflex_web/data/feedback.db` 存在

### Step 6: 收尾

- [ ] `.gitignore` 加 `reflex_web/data/`
- [ ] 文档：AGENTS.md（§2 依赖/部署、§3 架构树 feedback_model.py、§10 CHANGELOG 摘要）、README.md、`reflex_web/离线部署.md`（data/ 保留说明）、main_gui.py CHANGELOG（版本 bump 到 1.19.0？——主程序无功能变更则仅记 Web 版条目，版本号不变，CHANGELOG 加 Web 条目说明）
- [ ] `trellis-check` 全量检查 → commit

## 验证命令汇总

```bash
PYTHONUTF8=1 python.exe test/test_web_feedback.py
PYTHONUTF8=1 python.exe test/test_web_frame_gen_utils.py
cd reflex_web && reflex export --frontend-only --env prod --no-zip   # 前端编译冒烟
python reflex_web/build_embedded_deploy.py --skip-deps               # 增量部署验证 data/ 保留
```

## 回滚点

- 每步独立可回滚；Step 1/4 为纯新增文件，直接删除即可。
- 部署脚本改动小而集中（两处 move 逻辑），异常时 git checkout 还原。
