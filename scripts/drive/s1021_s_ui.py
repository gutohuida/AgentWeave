"""2026-10-21 spec sweep, browser: Delete document from the phase bar on an approved change whose
task kept an unmerged commit (F829 + F828), in real Chromium on the served bundle (:8150).

    AW_E2E_STATE=... py -3.11 s1021_s_ui.py <project-id> <doc-path>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, DOC = sys.argv[1:3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


seen, after = [], {"deleted": False}


def on_response(resp):
    if "/documents" in resp.url and resp.request.method == "DELETE":
        after["deleted"] = True
        try:
            seen.append(("DELETE-BODY", resp.status, resp.text()[:800]))
        except Exception as exc:  # noqa: BLE001
            seen.append(("DELETE-BODY", resp.status, repr(exc)))
    elif after["deleted"] and DOC.split("/")[2] in resp.url:
        seen.append(("AFTER", resp.request.method, resp.status, resp.url[-140:]))


with Judge("s1021-spec", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec&document=" + DOC)
    page.on("response", on_response)
    page.wait_for_timeout(5000)
    print("title on page:", txt(page.locator("main h1, main h2")))
    page.get_by_test_id("spec-delete").first.click()
    page.wait_for_timeout(800)
    dlg = page.get_by_role("dialog")
    print("confirm dialog:", txt(dlg))
    print("focused on open:", page.evaluate("document.activeElement && document.activeElement.textContent.trim().slice(0,40)"))
    j.shot(page, "01_confirm")
    page.get_by_role("button", name="Delete document").click()
    page.wait_for_timeout(4000)
    print("url after:", page.url[-160:])
    print("note:", txt(page.get_by_test_id("spec-deleted-note")))
    body = " ".join((page.locator("body").text_content() or "").split())
    for w in ("kept", "branch", "unmerged", "commit", "checkout"):
        print(f"  page mentions {w!r}:", w in body.lower())
    print("main (start):", txt(page.locator("main"))[:400])
    j.shot(page, "02_after_delete", full_page=True)
    for s in seen:
        print(" ", s)
    for w in ("could not", "no specification document", "failed"):
        print(f"  page mentions {w!r}:", w in body.lower())
    if page.get_by_test_id("spec-deleted-note-dismiss").count():
        page.get_by_test_id("spec-deleted-note-dismiss").first.click()
        page.wait_for_timeout(500)
        print("note after Dismiss:", txt(page.get_by_test_id("spec-deleted-note")))
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    print("after reload url:", page.url[-120:], "| note:", txt(page.get_by_test_id("spec-deleted-note")))
    print("console errors:", len(j.errors))
