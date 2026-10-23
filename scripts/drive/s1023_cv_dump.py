"""Dump the side panel's markup (specs index, files index, add-tab menu) to find its controls.

    py -3.11 scripts/drive/s1023_cv_dump.py
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def slim(html):
    html = re.sub(r'class="[^"]*"', "", html)
    html = re.sub(r'style="[^"]*"', "", html)
    html = re.sub(r"<svg.*?</svg>", "<svg/>", html, flags=re.S)
    return html


with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="agent=alpha")
    page.wait_for_timeout(5000)
    page.get_by_test_id("conversation-more").click()
    page.wait_for_timeout(400)
    page.get_by_test_id("conversation-toggle-panel").click()
    page.wait_for_timeout(1500)
    if page.get_by_test_id("panel-launch-specs").count():
        page.get_by_test_id("panel-launch-specs").click()
        page.wait_for_timeout(1500)
    print("SPECS:", slim(page.get_by_test_id("panel-tab-content").inner_html())[:3000])
    page.get_by_test_id("panel-tab-add").click()
    page.wait_for_timeout(500)
    print("MENU:", slim(page.get_by_role("menu").inner_html())[:1500])
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.get_by_test_id("panel-tab-files").click() if page.get_by_test_id("panel-tab-files").count() else None
    page.wait_for_timeout(1000)
    print("FILES:", slim(page.get_by_test_id("panel-tab-content").inner_html())[:3000])
