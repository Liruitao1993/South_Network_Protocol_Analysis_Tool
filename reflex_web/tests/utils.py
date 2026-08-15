"""Utility helpers for Reflex browser tests."""
import time
from typing import List


def switch_tab(page, label: str):
    """Click a tab button by its visible label."""
    page.get_by_text(label, exact=False).first.click()
    # allow Reflex state to settle
    time.sleep(0.2)


def get_console_errors(page) -> List[str]:
    """Return console messages with level 'error'."""
    return page.context.pages[0].evaluate("() => window.__console_errors || []")
