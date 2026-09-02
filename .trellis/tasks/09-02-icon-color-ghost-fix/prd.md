# 修复：浅色主题图标白色不可见 + 状态栏/分隔区域重影

## Bug 1：图标颜色读错 palette

现象：默认浅色主题下图标为白色（不可见）；深色主题下图标为浅色可见。

根因（实测）：`app_icons` 引擎从 `QApplication.palette()` 取 ButtonText。
ThemeManager 只设 QSS 不改 app palette；但 Fusion 样式在 Windows 深色模式下
app palette 的 ButtonText 为浅色。QSS 经 QStyleSheetStyle polish 写入的
**widget palette** 才是正确的前景色（实测 dark 主题 QTabBar ButtonText=#e0e0e0，
default 浅色主题为 #000000）。

修：取色链 = 绘制目标 widget palette（painter.device()）→ QApplication
.activeWindow() palette → app palette；Disabled 模式取 Disabled 组。
pixmap() 回退路径（device 是 QPixmap）也走该链。

## Bug 2：状态栏文本重影 + 分隔条附近残影

现象：截图中底部状态栏「CPU/内存/线程」文本叠影；监控页 QSplitter 分隔条
附近有半透明旧文字残影。

根因：QStatusBar 常驻 QLabel 每次 setText + setStyleSheet（4s/1s 刷新）
触发布局重排，Windows 合成层下旧矩形区域未失效；splitter 拖动/窗口尺寸
变化后子控件新位置已绘而旧位置未被父级覆盖（offscreen 无法复现，真实
DWM 合成可见）。

修（强制失效，不改视觉）：
- `_refresh_cpu_mem`、线程数刷新、更新状态链接文本/显隐变化后调用
  `self.statusBar().update()`（4s/1s 级开销可忽略）。
- MainWindow UI 构建末尾对所有 QSplitter 挂 `splitterMoved → 父容器
  .update()`（覆盖监控页左右/上下分隔残影）。

## Acceptance Criteria

- [ ] 浅色（default）真实 MainWindow：标签图标像素为深色（黑/深灰线）。
- [ ] 深色（dark QSS）：图标像素为浅色。
- [ ] test/test_app_icons.py 覆盖新取色链（活动窗口 palette 优先）并通过。
- [ ] offscreen 冒烟：状态栏更新、splitter 挂接均无异常。
- [ ] test_frame_share / theme_settings 回归不新增失败（theme_settings
      既有 12 项失败为预存）。
