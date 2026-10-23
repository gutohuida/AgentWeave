"""F945 drive: the Spec header's requirements fact names each unfinished state.

An approved change whose requirements nobody has started, and a proposed change with no task,
opened in Chromium against the served bundle; prints the requirements fact of each.

  AW_E2E_STATE=... AW_P=proj-... py -3.11 scripts/drive/f945_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_sp_lib import DOCS, P, e2e, payload, req  # noqa: E402
from uiharness import Judge  # noqa: E402

norm = lambda s: " ".join((s or "").split())  # noqa: E731


def make(name, approve):
    path = f"spec/changes/{name}/spec.json"
    req("POST", DOCS, {"path": path, "title": name})
    doc = payload(name, name, keys=("alpha", "beta"))
    if not approve:
        doc["tasks"] = []
    print("PUT", req("PUT", f"{DOCS}/{path}/content", {"document": doc})[0])
    req("POST", f"{DOCS}/close-exploration?path={path}")
    print("propose", req("POST", f"{DOCS}/propose?path={path}")[0])
    if approve:
        s, r = req("POST", f"{DOCS}/phase?path={path}&to=approved", {"reason": "drive", "approve_anyway": True})
        print("approve", s)
    return path


paths = [make("hdr-main", True), make("hdr-proposed", False)]
with Judge("f945", hub=e2e.hub(), key=e2e.key()) as j:
    for path in paths:
        page = j.page(P, mode="light", width=1440, query="tab=spec")
        page.wait_for_timeout(4000)
        row = page.locator(f"[data-testid='spec-list-row-{path}']")
        print("row", row.count())
        if row.count():
            row.first.click()
        page.wait_for_timeout(3500)
        fact = page.get_by_test_id("spec-health-requirements")
        print(path, "FACT:", norm(fact.text_content()) if fact.count() else None,
              "tone:", fact.get_attribute("data-tone") if fact.count() else None)
        j.shot(page, "header_" + path.split("/")[2])
    print("console errors:", j.errors[:5])
