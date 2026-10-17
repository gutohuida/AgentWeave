"""Baseline screenshots of today's task drawer and evidence surfaces on the Terra replica, so the
visibility roadmap's screens are judged against what they replace.

    py -3.11 scripts/drive/terra_replica.py --up 8130
    py -3.11 scripts/drive/d1017_ui_baseline.py
"""

import sys

from uiharness import Judge

TERRA = "proj-cd006955cbe2"
TASK = "task-87ce01a67b0c"


def open_task(page):
    page.get_by_test_id("project-tab-tasks").first.wait_for(timeout=30000)
    page.get_by_test_id("project-tab-tasks").first.click()
    page.get_by_test_id(f"task-open-{TASK}").first.wait_for(timeout=20000)
    page.get_by_test_id(f"task-open-{TASK}").first.click()
    page.get_by_test_id(f"task-drawer-{TASK}").wait_for(timeout=15000)
    page.wait_for_timeout(1200)


def open_coverage(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.get_by_test_id("project-tab-spec").first.wait_for(timeout=30000)
    page.get_by_test_id("project-tab-spec").first.click()
    page.wait_for_timeout(2500)


with Judge("d1017-baseline") as j:
    j.shots(TERRA, "task_drawer", open_task)
    page = j.page(TERRA, mode="dark")
    open_task(page)
    j.shot(page, "task_drawer_full", locator=page.get_by_test_id(f"task-drawer-body-{TASK}"))
    open_coverage(page)
    j.shot(page, "spec_tab_dark", full_page=True)
    sys.exit(1 if j.errors else 0)
