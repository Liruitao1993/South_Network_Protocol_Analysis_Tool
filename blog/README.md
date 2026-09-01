# CSDN 版本博客流程（每版本一篇）

## 何时写

版本完成并提交（`feat(all)/feat(gui)/fix` 批次，`main_gui.py:CHANGELOG` 出现新条目）后，写一篇。

## 怎么写

1. 复制 `_TEMPLATE.md` → `blog/YYYY-MM-DD-v<版本>-<slug>.md`
2. 素材：
   - `main_gui.py:CHANGELOG` 对应版本条目（功能清单）
   - `.trellis/tasks/archive/<月份>/<任务>/design.md`（技术细节）
   - 实际源码（代码片段必须与真实代码一致，不虚构）
3. 按模板结构写：亮点 → 深挖 1~2 个技术点（方案/代码/踩坑）→ 结语
4. front-matter 填标题、建议标签（python/pyside6/reflex/电力物联网 等按内容选）

## 怎么发（用户手动，约 1 分钟）

1. 打开 CSDN 创作中心 → 写文章 → 「导入 Markdown」→ 选择 blog/ 下的 .md 文件
2. 补封面图、检查预览 → 发布
3. 文章开头若需加"本文同步发布于我的 CSDN"类说明，在导入后编辑器里加

## 风格约束（技术深度风）

- 面向开发者；不出现内部路径（.trellis/ 等）与 AI 工具链叙事
- 踩坑记录写"现象 → 根因 → 修复"三段，有代码佐证
- 1500~3000 字；标题克制不标题党
