from s1018_B_lib import e2e, P
from uiharness import Judge
with Judge("s1018-sweepB-dbg", hub="http://127.0.0.1:8032", key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec")
    page.get_by_test_id("spec-page").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    ids = page.eval_on_selector_all("[data-testid^='spec-tree']", "els => els.map(e => e.dataset.testid)")
    print(ids)
    page.get_by_test_id("spec-tree-directory-spec/changes").first.click()
    page.wait_for_timeout(1000)
    ids = page.eval_on_selector_all("[data-testid^='spec-tree']", "els => els.map(e => e.dataset.testid)")
    print(ids)
