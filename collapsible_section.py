# -*- coding: utf-8 -*-
"""可折叠区组件（标题栏 + 内容区）—— 供字段非常多的表单分层收纳。

用途与动机
==========
协议9 链路层组帧有几十个字段（FC 可变区域随帧类型/版本变化、物理块、MAC 头、MSDU、ED 封装），
全部平铺会让页面长到无法使用。本组件把每层收进一个可折叠区，标题栏实时显示该层字节数与
HEX 缩略，便于逐层核对。

设计要点
========
1. **不写死任何宽度**（AGENTS 陷阱 63）：标题栏按钮用 ``QToolButton`` + 自适应尺寸策略，
   只设下限不设上限；字号随主题变化时 ``sizeHint`` 自然增长，无需重算。
2. **不内联颜色**：全部交给 QSS 主题；标题按钮设 ``objectName="CollapsibleSectionHeader"``
   便于主题按名定制。
3. **状态可持久化**：``key`` 标识折叠区，配合模块级 :func:`collect_state` / :func:`apply_state`
   存入 ``config.json``。
4. **折叠判据用 ``isHidden()``**：``isVisible()`` 在父窗口未 show 时恒为 False（offscreen 测试会误判）。
"""

from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import app_icons

__all__ = [
    "CollapsibleSection",
    "expand_all",
    "collapse_all",
    "collect_state",
    "apply_state",
    "DEFAULT_MAX_TEXT",
]

#: 标题按钮的 objectName（主题 QSS 可据此定制）
HEADER_OBJECT_NAME = "CollapsibleSectionHeader"

#: 折叠/展开指示图标（icons/lucide/*.svg）；缺失时回退为文字箭头
_ICON_EXPANDED = "chevron-down"
_ICON_COLLAPSED = "chevron-right"
_TEXT_EXPANDED = "▼ "
_TEXT_COLLAPSED = "▶ "

#: 标题栏「标题 + 后缀」的总显示字符数上限。
#: 只限后缀不够——标题本身也可能很长（如「① FC 帧控制（16 字节，含 FCCS 自动计算）」），
#: 二者相加仍会把按钮 sizeHint 撑到超过窗口宽度，窄窗口下即表现为文字被裁。
#: 超出部分截断为 "…"，完整后缀放 tooltip（内容层面可控，不是被布局挤压裁掉）。
DEFAULT_MAX_TEXT = 48


class CollapsibleSection(QWidget):
    """一个可折叠区：标题栏（整条可点击）+ 内容区。

    用法::

        sec = CollapsibleSection("① FC 帧控制", key="fc")
        sec.content_layout().addWidget(some_form)
        sec.set_title_suffix("16 字节 · 59 23 61 45 …")
        layout.addWidget(sec)

    内容区初始为空（无任何子控件），由调用方填充。
    """

    #: 折叠状态变化（True = 展开）
    toggled = Signal(bool)

    def __init__(self, title: str, parent: Optional[QWidget] = None,
                 expanded: bool = True, key: Optional[str] = None,
                 max_text: int = DEFAULT_MAX_TEXT):
        super().__init__(parent)
        self._title = str(title)
        self._suffix = ""
        self._max_text = max(0, int(max_text))
        self.key = key

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # ── 标题栏（整条可点击）──
        self.header_button = QToolButton(self)
        self.header_button.setObjectName(HEADER_OBJECT_NAME)
        self.header_button.setCheckable(True)
        self.header_button.setChecked(bool(expanded))
        self.header_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header_button.setAutoRaise(True)
        self.header_button.setCursor(Qt.CursorShape.PointingHandCursor)
        # 只设下限、不设上限：字号变化时 sizeHint 增长仍能被布局满足（陷阱 63）
        self.header_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.header_button.clicked.connect(self._on_header_clicked)
        layout.addWidget(self.header_button)

        # ── 内容区 ──
        self.content = QWidget(self)
        self.content_layout_ = QVBoxLayout(self.content)
        self.content_layout_.setContentsMargins(10, 2, 2, 4)
        self.content_layout_.setSpacing(4)
        layout.addWidget(self.content)

        self._refresh_header()
        self.content.setVisible(bool(expanded))

    # ------------------------------------------------------------------
    # 标题栏
    # ------------------------------------------------------------------

    def _on_header_clicked(self, checked: bool) -> None:
        """标题栏被点击（QToolButton.clicked 会带 checked 实参，此处按 checked 处理）。"""
        self._apply_expanded(bool(checked), emit=True)

    def _apply_expanded(self, expanded: bool, emit: bool) -> None:
        self.content.setVisible(expanded)
        self._refresh_header()
        if emit:
            self.toggled.emit(expanded)

    def _suffix_display(self) -> str:
        """标题栏实际显示的后缀：按「标题+后缀」总长上限截断（完整内容见 tooltip）。"""
        if not self._suffix:
            return ""
        budget = self._max_text - len(self._title) - 2   # 2 = 标题与后缀间的分隔空格
        if self._max_text <= 0 or budget >= len(self._suffix):
            return self._suffix
        if budget <= 1:
            return ""                                     # 标题已占满，宁可不显示后缀
        return self._suffix[: budget - 1] + "…"

    def _refresh_header(self) -> None:
        expanded = self.header_button.isChecked()
        icon = app_icons.load_icon(_ICON_EXPANDED if expanded else _ICON_COLLAPSED)
        shown_suffix = self._suffix_display()
        text = f"{self._title}  {shown_suffix}" if shown_suffix else self._title
        if icon.isNull():
            # 图标缺失时回退为文字箭头（组件仍可用，不影响功能）
            self.header_button.setText(
                (_TEXT_EXPANDED if expanded else _TEXT_COLLAPSED) + text)
        else:
            self.header_button.setIcon(icon)
            self.header_button.setText(text)
        tip = f"{self._title}（点击{'收起' if expanded else '展开'}）"
        if self._suffix and shown_suffix != self._suffix:
            tip += f"\n{self._suffix}"        # 完整后缀放 tooltip，避免截断丢信息
        self.header_button.setToolTip(tip)

    def set_title_suffix(self, text: object) -> None:
        """设置标题栏后缀（用于显示该层字节数 / HEX 缩略）。

        超长后缀按 ``max_suffix`` 截断（防 sizeHint 撑爆容器导致文字被裁），
        完整内容仍可从 tooltip 查看。
        """
        self._suffix = str(text or "")
        self._refresh_header()

    def title_suffix(self) -> str:
        return self._suffix

    def header_text(self) -> str:
        """当前标题栏实际显示的文字（含后缀；供测试断言）。"""
        return self.header_button.text()

    def set_title(self, title: str) -> None:
        self._title = str(title)
        self._refresh_header()

    def title(self) -> str:
        return self._title

    # ------------------------------------------------------------------
    # 折叠状态
    # ------------------------------------------------------------------

    def content_layout(self) -> QVBoxLayout:
        """内容区布局：调用方往这里加控件。"""
        return self.content_layout_

    def set_expanded(self, expanded: bool) -> None:
        """程序化设置折叠状态（会发 ``toggled``；不触发 ``clicked``，无递归风险）。"""
        expanded = bool(expanded)
        if self.header_button.isChecked() != expanded:
            # QAbstractButton.setChecked 不发 clicked 信号，故不会重入
            self.header_button.setChecked(expanded)
        self._apply_expanded(expanded, emit=True)

    def set_expanded_quiet(self, expanded: bool) -> None:
        """程序化设置折叠状态但**不发信号**（用于批量恢复持久化状态）。"""
        expanded = bool(expanded)
        if self.header_button.isChecked() != expanded:
            self.header_button.setChecked(expanded)
        self._apply_expanded(expanded, emit=False)

    def is_expanded(self) -> bool:
        return bool(self.header_button.isChecked())

    def is_content_hidden(self) -> bool:
        """内容区是否被显式隐藏。

        用 ``isHidden()`` 而非 ``isVisible()``：后者在父窗口尚未 show 时恒为 False，
        offscreen 测试会误判为「已折叠」。
        """
        return self.content.isHidden()

    def toggle(self) -> None:
        self.set_expanded(not self.is_expanded())


# ----------------------------------------------------------------------
# 批量操作与状态持久化
# ----------------------------------------------------------------------


def expand_all(sections: Iterable[CollapsibleSection]) -> None:
    for section in sections:
        section.set_expanded(True)


def collapse_all(sections: Iterable[CollapsibleSection]) -> None:
    for section in sections:
        section.set_expanded(False)


def collect_state(sections: Iterable[CollapsibleSection]) -> Dict[str, bool]:
    """收集折叠状态为 ``{key: expanded}``（无 key 的区跳过）。"""
    state: Dict[str, bool] = {}
    for section in sections:
        if section.key:
            state[str(section.key)] = section.is_expanded()
    return state


def apply_state(sections: Iterable[CollapsibleSection],
                state: Optional[Dict[str, object]]) -> List[str]:
    """按 ``{key: expanded}`` 恢复折叠状态，返回**实际被套用**的 key 列表。

    容错：state 为空/非字典、key 不存在、值非布尔（只认 True/False 与 "true"/"false"）
    一律跳过该区（保持当前状态），不抛异常——配置损坏不应导致界面打不开。
    """
    if not isinstance(state, dict):
        return []
    applied: List[str] = []
    for section in sections:
        if not section.key:
            continue
        key = str(section.key)
        if key not in state:
            continue
        raw = state[key]
        if isinstance(raw, bool):
            expanded = raw
        elif isinstance(raw, str) and raw.strip().lower() in ("true", "false"):
            expanded = raw.strip().lower() == "true"
        else:
            continue
        section.set_expanded_quiet(expanded)
        applied.append(key)
    return applied
