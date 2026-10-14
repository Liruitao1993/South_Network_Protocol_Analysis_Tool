# -*- coding: utf-8 -*-
"""可折叠区组件（``collapsible_section``）offscreen 测试。

重点覆盖：
1. 折叠/展开语义与 ``isHidden()`` 判据（``isVisible()`` 在父窗口未 show 时恒 False，不能用）；
2. ``toggled`` 信号、``set_expanded`` 与 ``set_expanded_quiet`` 的差别；
3. 标题栏后缀（层字节数/HEX 缩略）与标题文字；
4. 批量展开/收起；
5. 状态收集与容错恢复（None / 非字典 / 未知 key / 非布尔值一律跳过，不抛异常）；
6. **按钮不裁字**：``show()`` 之后 ``width() >= sizeHint().width()`` 且未设 ``maximumWidth``
   上限（AGENTS 陷阱 63：只在 show 后量才有意义，headless 未 show 的 width 默认 640 会假绿）。

运行：``python test/test_collapsible_section.py``（offscreen，无需显示器）。
"""

import _path_setup  # noqa: E402,F401

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QVBoxLayout,
    QWidget,
)

import collapsible_section as cs  # noqa: E402

_FAILURES = []
_CHECKS = []


def check(name, condition, detail=""):
    _CHECKS.append(name)
    if not condition:
        _FAILURES.append(f"{name} —— {detail}")


def _app():
    return QApplication.instance() or QApplication([])


def _host() -> QWidget:
    """一个承载折叠区的顶层窗口（show 后才能量真实几何）。"""
    win = QWidget()
    win.setLayout(QVBoxLayout())
    return win


# ────────────────────────── 1. 构造与折叠语义 ──────────────────────────


def test_default_expanded():
    _app()
    sec = cs.CollapsibleSection("① FC 帧控制", key="fc")
    check("默认展开", sec.is_expanded())
    check("展开时内容未隐藏", not sec.is_content_hidden())
    check("key 被保留", sec.key == "fc", str(sec.key))
    check("标题栏文字含标题", "① FC 帧控制" in sec.header_text(), sec.header_text())
    check("按钮可勾选（折叠开关）", sec.header_button.isCheckable())


def test_collapse_and_expand():
    _app()
    sec = cs.CollapsibleSection("② 物理块", expanded=True)
    check("初始展开", sec.is_expanded() and not sec.is_content_hidden())

    sec.set_expanded(False)
    check("收起后 is_expanded=False", not sec.is_expanded())
    check("收起后内容隐藏", sec.is_content_hidden())

    sec.set_expanded(True)
    check("再展开", sec.is_expanded() and not sec.is_content_hidden())

    sec.toggle()
    check("toggle 折叠", sec.is_content_hidden())
    sec.toggle()
    check("toggle 展开", not sec.is_content_hidden())


def test_toggled_signal():
    _app()
    sec = cs.CollapsibleSection("③ MAC 帧头")
    events = []
    sec.toggled.connect(events.append)

    sec.set_expanded(False)
    check("set_expanded 发 toggled(False)", events == [False], str(events))
    sec.set_expanded(True)
    check("set_expanded 发 toggled(True)", events == [False, True], str(events))

    # 静默设置：不发信号（用于批量恢复持久化状态，避免反复触发布局重算）
    events.clear()
    sec.set_expanded_quiet(False)
    check("set_expanded_quiet 不发信号", events == [], str(events))
    check("set_expanded_quiet 仍生效", sec.is_content_hidden())


def test_header_click_toggles():
    """点击标题栏切换折叠（走 QToolButton.clicked）。"""
    _app()
    sec = cs.CollapsibleSection("④ MSDU")
    check("点击前展开", sec.is_expanded())
    sec.header_button.click()
    check("点击后折叠", sec.is_content_hidden())
    sec.header_button.click()
    check("再点击后展开", not sec.is_content_hidden())


def test_content_layout_receives_widgets():
    _app()
    sec = cs.CollapsibleSection("⑤ ED 封装")
    layout = sec.content_layout()
    check("content_layout 返回布局", isinstance(layout, QVBoxLayout))
    label = QLabel("字段占位")
    layout.addWidget(label)
    check("内容区可容纳子控件", label.parent() is not None)
    check("子控件计入内容区", layout.count() == 1, str(layout.count()))


# ────────────────────────── 2. 标题栏后缀 ──────────────────────────


def test_title_suffix():
    _app()
    sec = cs.CollapsibleSection("① FC 帧控制", key="fc")
    before = sec.header_text()
    sec.set_title_suffix("16 字节 · 59 23 61 45")
    check("后缀出现在标题栏", "16 字节 · 59 23 61 45" in sec.header_text(), sec.header_text())
    check("后缀改变标题栏文字", sec.header_text() != before)
    check("title_suffix getter", sec.title_suffix() == "16 字节 · 59 23 61 45", sec.title_suffix())

    sec.set_title_suffix("")
    check("清空后缀回到标题", sec.header_text().strip() == "① FC 帧控制", sec.header_text())
    check("清空后缀后 title_suffix 为空", sec.title_suffix() == "")

    sec.set_title("新标题")
    check("set_title 生效", sec.title() == "新标题" and "新标题" in sec.header_text(),
          sec.header_text())


# ────────────────────────── 3. 批量操作与状态持久化 ──────────────────────────


def test_expand_collapse_all():
    _app()
    secs = [cs.CollapsibleSection(f"层{i}", key=f"k{i}") for i in range(5)]
    cs.collapse_all(secs)
    check("collapse_all 全部收起", all(s.is_content_hidden() for s in secs))
    cs.expand_all(secs)
    check("expand_all 全部展开", all(not s.is_content_hidden() for s in secs))


def test_state_roundtrip():
    _app()
    secs = [cs.CollapsibleSection(f"层{i}", key=f"k{i}", expanded=True) for i in range(3)]
    secs[1].set_expanded(False)
    state = cs.collect_state(secs)
    check("collect_state 收集全部 key", set(state) == {"k0", "k1", "k2"}, str(state))
    check("collect_state 值正确", state["k0"] is True and state["k1"] is False, str(state))

    # 打乱后恢复
    cs.expand_all(secs)
    applied = cs.apply_state(secs, state)
    check("apply_state 返回套用的 key", sorted(applied) == ["k0", "k1", "k2"], str(applied))
    check("apply_state 恢复 k1 为收起", secs[1].is_content_hidden())
    check("apply_state 恢复 k0 为展开", not secs[0].is_content_hidden())

    check("无 key 的区不进状态", cs.collect_state([cs.CollapsibleSection("无名")]) == {})


def test_state_tolerance():
    """配置损坏不得导致界面打不开：各种非法输入静默跳过。"""
    _app()
    secs = [cs.CollapsibleSection("层0", key="k0", expanded=True),
            cs.CollapsibleSection("层1", key="k1", expanded=True)]
    for name, bad in (("None", None), ("非字典", ["k0"]), ("字符串", "k0")):
        applied = cs.apply_state(secs, bad)
        check(f"apply_state 容错 {name}", applied == [] and secs[0].is_expanded(),
              f"applied={applied}")
    applied = cs.apply_state(secs, {"k0": "true", "k1": False, "unknown": "x", "k2": 123})
    check("apply_state 认字符串布尔并跳过非法值", sorted(applied) == ["k0", "k1"], str(applied))
    check("apply_state 字符串 true 生效", not secs[0].is_content_hidden())
    check("apply_state 未知 key 被忽略", "unknown" not in applied)


# ────────────────────────── 4. 按钮不裁字（show() 之后量） ──────────────────────────


def test_header_button_not_clipped():
    """标题栏文字不得被裁：width >= sizeHint，且未设 maximumWidth 上限。

    超长后缀由组件自行截断（否则 sizeHint 会远超窗口宽度而裁字），完整内容进 tooltip。
    """
    _app()
    win = _host()
    sec = cs.CollapsibleSection("① FC 帧控制（16 字节，含 FCCS 自动计算）", key="fc")
    win.layout().addWidget(sec)
    win.resize(1000, 400)
    win.show()
    QApplication.processEvents()

    long_suffix = "138 字节 · " + " ".join(["FF"] * 30)
    sec.set_title_suffix(long_suffix)
    win.layout().activate()
    QApplication.processEvents()

    need = sec.header_button.sizeHint().width()
    have = sec.header_button.width()
    check("标题栏宽度不小于 sizeHint（不裁字）", have >= need, f"width={have} < sizeHint={need}")
    check("未设 maximumWidth 上限（字号变化仍可增长）",
          sec.header_button.maximumWidth() >= 16777215,
          str(sec.header_button.maximumWidth()))
    win.close()


def test_long_suffix_truncated_and_tooltip_keeps_full():
    """超长后缀在标题栏截断（防撑爆容器），完整内容保留在 tooltip。"""
    _app()
    sec = cs.CollapsibleSection("① FC 帧控制", key="fc", max_text=20)
    long_suffix = "138 字节 · " + " ".join(["FF"] * 30)
    sec.set_title_suffix(long_suffix)

    shown = sec.header_button.text()
    check("标题栏后缀被截断", "…" in shown and len(shown) < len(long_suffix), f"len={len(shown)}")
    check("截断后仍显示标题", "① FC 帧控制" in shown, shown)
    check("完整后缀进入 tooltip", long_suffix in sec.header_button.toolTip(),
          sec.header_button.toolTip()[:60])
    check("title_suffix 仍返回完整原文", sec.title_suffix() == long_suffix)

    # 短后缀不截断
    sec.set_title_suffix("16 字节")
    check("短后缀原样显示", "16 字节" in sec.header_button.text(), sec.header_button.text())
    check("短后缀不进 tooltip 附加段", "\n16 字节" not in sec.header_button.toolTip())


def test_header_visible_region_non_empty():
    """标题栏确实被绘制（visibleRegion 非空 —— 比 grab() 更能暴露「控件在但没画」）。"""
    _app()
    win = _host()
    sec = cs.CollapsibleSection("② 物理块 PBH（4 字节）+ PBCS")
    win.layout().addWidget(sec)
    win.resize(900, 300)
    win.show()
    QApplication.processEvents()

    region = sec.header_button.visibleRegion()
    check("标题栏有可见绘制区域", not region.isEmpty(),
          f"visibleRegion={region.boundingRect()}")
    check("标题栏高度合理（>0）", sec.header_button.height() > 0, str(sec.header_button.height()))
    win.close()


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"检查项：{len(_CHECKS)} 项，失败 {len(_FAILURES)} 项")
    if _FAILURES:
        for item in _FAILURES:
            print(f"  [FAIL] {item}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
