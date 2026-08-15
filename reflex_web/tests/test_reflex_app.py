# -*- coding: utf-8 -*-
"""Browser automation smoke tests for the Reflex web app."""
import pytest


SAMPLE_HEX = "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16"


TAB_TESTIDS = {
    "单帧解析": "tab-single",
    "批量解析": "tab-batch",
    "协议组帧": "tab-frame",
    "报文对比": "tab-diff",
    "查询": "tab-lookup",
    "报文工具": "tab-tool",
}


def switch_tab(page, label):
    """Click tab button by data-testid."""
    testid = TAB_TESTIDS[label]
    page.locator(f"[data-testid='{testid}']").click()
    page.wait_for_timeout(800)


def _fill_first_textarea(page, text):
    """Fill the first visible textarea in the active tab."""
    ta = page.locator("textarea >> visible=true").first
    ta.wait_for(state="visible")
    ta.fill(text)


def test_homepage(page, reflex_app):
    """Homepage loads and all tab buttons are visible."""
    page.goto(reflex_app)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("text=单帧解析")
    for label in ["单帧解析", "批量解析", "协议组帧", "报文对比", "查询", "报文工具"]:
        assert page.is_visible(f"text={label}")


def test_single_parse(page, reflex_app):
    """Single frame parse returns results."""
    page.goto(reflex_app)
    page.wait_for_load_state("networkidle")
    _fill_first_textarea(page, SAMPLE_HEX)
    page.locator("button:has-text('解析报文') >> visible=true").first.click()
    page.wait_for_selector("text=解析结果", timeout=15000)
    rows = page.locator("table tbody tr").count()
    assert rows > 0, "No parse rows"


def test_batch_parse(page, reflex_app):
    """Batch parse tab loads."""
    page.goto(reflex_app)
    page.wait_for_load_state("networkidle")
    switch_tab(page, "批量解析")
    assert page.is_visible("text=批量解析摘要")


def test_frame_gen(page, reflex_app):
    """Frame generation tab loads."""
    page.goto(reflex_app)
    page.wait_for_load_state("networkidle")
    switch_tab(page, "协议组帧")
    assert page.is_visible("text=协议组帧")


def test_diff(page, reflex_app):
    """Diff tab loads."""
    page.goto(reflex_app)
    page.wait_for_load_state("networkidle")
    switch_tab(page, "报文对比")
    assert page.is_visible("text=报文对比")


def test_lookup(page, reflex_app):
    """Lookup tab loads and returns results."""
    page.goto(reflex_app)
    page.wait_for_load_state("networkidle")
    switch_tab(page, "查询")
    page.locator("input >> visible=true").first.fill("E8")
    page.locator("button:has-text('搜索') >> visible=true").first.click()
    page.wait_for_selector("table tbody tr", timeout=15000)
    assert page.locator("table tbody tr").count() > 0


def test_message_tool(page, reflex_app):
    """Message tool produces correct output."""
    page.goto(reflex_app)
    page.wait_for_load_state("networkidle")
    switch_tab(page, "报文工具")
    textareas = page.locator("textarea >> visible=true")
    textareas.nth(0).fill("68 01 02 03")
    page.locator("button:has-text('按字节倒序') >> visible=true").first.click()
    page.wait_for_timeout(300)
    output = textareas.nth(1).input_value()
    assert "03 02 01 68" in output
