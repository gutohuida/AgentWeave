"""2026-10-22 vault sweep, browser: the rebuilt Vault screens and Project settings -> Manager on the
served bundle of the scratch Hub (hub-up vt1022 8115), after s1022_vt_drive.py setup..agent.

  py -3.11 scripts/drive/s1022_vt_ui.py <step,...>
    lib      library rows, folders, counts, duplicates, side filters
    reader   Export note A: facts and cited lines; the PDF and the PNG inline
    add      Add dialog: a .docx through the picker, a folder through the picker, text with bad dates
    drop     page drop of a file, and of a hidden one only
    storage  storage dialog: a location inside the repo, then cancel
    review   contradictions: resolve one; reports: close the referred one
    manager  Project settings -> Manager: jobs, firings, the runner/model selects
"""

import json
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import s1022_vt_drive as d  # noqa: E402
from uiharness import Judge  # noqa: E402

P = d.S["P"]
DIR = pathlib.Path(d.S["DIR"])


def txt(loc):
    return " ".join((loc.text_content() or "").split())


def drop_files(page, target, files):
    """Dispatch a real DataTransfer drop of in-memory files on *target* (a locator)."""
    handle = page.evaluate_handle(
        """(files) => { const dt = new DataTransfer();
             for (const f of files) dt.items.add(new File([f.text], f.name, {type: f.type}));
             return dt; }""",
        files,
    )
    for kind in ("dragenter", "dragover", "drop"):
        target.dispatch_event(kind, {"dataTransfer": handle})


def vault(j):
    page = j.page(P, mode="light", query="tab=vault")
    page.wait_for_selector("[data-testid=vault-page]", timeout=20000)
    page.wait_for_timeout(1500)
    return page


def step_lib(j):
    page = vault(j)
    print("SIDE:", txt(page.get_by_label("Vault filters"))[:900])
    rows = page.locator("[data-testid^=vault-entry-]")
    print("ROWS", rows.count())
    for i in range(rows.count()):
        print("  ROW", txt(rows.nth(i))[:160])
    j.shot(page, "lib", full_page=True)


def step_reader(j):
    page = vault(j)
    page.get_by_text("Export note A", exact=True).first.click()
    page.wait_for_timeout(2500)
    reader = page.locator("article.vault-reader").first
    print("READER:", txt(reader)[:1500])
    print("LINES:", page.locator("[data-testid^=vault-line-]").count(),
          "FACTS:", page.locator("[data-testid^=vault-fact-fct]").count())
    j.shot(page, "reader_note_a")
    page.keyboard.press("Escape")
    for name, testid in (("docs/retention.pdf", "vault-file-pdf"), ("docs/owner.png", "vault-file-image")):
        hit = page.get_by_text(name.rsplit(".", 1)[0], exact=False)
        print(name, "matches", hit.count())
        if hit.count():
            hit.first.click()
            page.wait_for_timeout(2500)
            print(" ", testid, page.get_by_test_id(testid).count(), "|", txt(page.locator("article.vault-reader").first)[:700])
            j.shot(page, "reader_" + testid)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)


def step_add(j):
    page = vault(j)
    page.get_by_test_id("vault-upload-open").click()
    page.wait_for_timeout(800)
    dialog = page.get_by_role("dialog")
    print("DIALOG:", txt(dialog)[:500])
    try:
        page.get_by_test_id("vault-upload-file").set_input_files(str(DIR / "docs"))
        print("FOLDER via picker accepted:", txt(dialog)[:300])
    except Exception as exc:  # noqa: BLE001
        print("FOLDER via picker refused by the browser:", str(exc).splitlines()[0][:300])
    page.get_by_test_id("vault-upload-file").set_input_files(str(DIR / "docs" / "minutes.docx"))
    page.wait_for_timeout(500)
    print("WITH DOCX:", txt(dialog)[:400])
    page.get_by_test_id("vault-upload-submit").click()
    page.wait_for_timeout(3000)
    print("AFTER ADD DOCX: dialog open", page.get_by_role("dialog").count(), "|", txt(page.locator("body"))[:200])
    j.shot(page, "add_docx")
    if page.get_by_role("dialog").count():
        page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    # The text form: a bad date, then a date in the format that is not a day.
    page.get_by_test_id("vault-upload-open").click()
    page.wait_for_timeout(500)
    page.get_by_role("radio", name="Paste text").click() if page.get_by_role("radio", name="Paste text").count() \
        else page.get_by_text("Paste text").first.click()
    page.get_by_test_id("vault-upload-name").fill("Dated probe")
    page.get_by_test_id("vault-upload-content").fill("A note for the date probe.")
    page.get_by_test_id("vault-upload-dated").fill("12/10/2026")
    page.wait_for_timeout(300)
    dialog = page.get_by_role("dialog")
    print("BAD DATE:", txt(dialog)[-300:], "| submit enabled", page.get_by_test_id("vault-upload-submit").is_enabled())
    page.get_by_test_id("vault-upload-dated").fill("2026-02-30")
    page.get_by_test_id("vault-upload-submit").click()
    page.wait_for_timeout(1500)
    print("NOT A DAY:", txt(dialog)[-400:])
    j.shot(page, "add_not_a_day")
    page.keyboard.press("Escape")


def step_drop(j):
    page = vault(j)
    target = page.get_by_test_id("vault-page")
    drop_files(page, target, [{"name": "dropped note.md", "text": "Dropped: exports go to the shared drive.", "type": "text/markdown"}])
    page.wait_for_timeout(800)
    print("DROP ONE:", txt(page.get_by_role("dialog"))[:400])
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    drop_files(page, target, [{"name": ".env", "text": "TOKEN=abc", "type": "text/plain"}])
    page.wait_for_timeout(800)
    dlg = page.get_by_role("dialog")
    print("DROP HIDDEN ONLY: dialog", dlg.count(), "|", txt(dlg)[:400] if dlg.count() else "")
    j.shot(page, "drop_hidden")
    page.keyboard.press("Escape")


def step_storage(j):
    page = vault(j)
    page.get_by_label("Vault storage").first.click()
    page.wait_for_timeout(800)
    dialog = page.get_by_role("dialog")
    print("STORAGE:", txt(dialog)[:500])
    page.get_by_test_id("vault-settings-location").fill(str(DIR / "inside"))
    page.get_by_test_id("vault-settings-save").click()
    page.wait_for_timeout(1500)
    print("INSIDE REPO:", txt(dialog)[:700])
    j.shot(page, "storage_inside")
    page.get_by_role("button", name="Cancel").click()


def step_review(j):
    page = vault(j)
    side = page.get_by_label("Vault filters")
    side.get_by_text("Disagreements").first.click()
    page.wait_for_timeout(1000)
    cards = page.locator("[data-testid^=vault-contradiction-ctr]")
    print("CONTRADICTIONS", cards.count())
    for i in range(cards.count()):
        print("  CARD", txt(cards.nth(i))[:600])
    j.shot(page, "contradictions", full_page=True)
    ctr = d.api("GET", "~/vault/contradictions")[1]["contradictions"]
    names = next(c for c in ctr if "hash" in json.dumps(c))
    cid, later = names["id"], names["presumed"]
    page.get_by_test_id(f"vault-resolve-{cid}-stand-{later}").click()
    page.get_by_test_id(f"vault-resolve-{cid}-note").fill("Note B is the later decision; names are hashed.")
    page.get_by_test_id(f"vault-resolve-{cid}-submit").click()
    page.wait_for_timeout(2500)
    print("AFTER RESOLVE:", txt(page.get_by_test_id(f"vault-contradiction-{cid}"))[:600])
    j.shot(page, "resolved")
    side.get_by_text("Reports").first.click()
    page.wait_for_timeout(1000)
    reps = page.locator("article.vault-report")
    for i in range(reps.count()):
        print("  REPORT", txt(reps.nth(i))[:900])
    rid = d.api("GET", "~/vault/reports")[1]["reports"][0]["id"]
    note = page.get_by_test_id(f"vault-report-{rid}-note")
    if note.count():
        note.fill("Resolved in the vault: note B holds.")
        page.get_by_test_id(f"vault-report-{rid}-close").click()
        page.wait_for_timeout(2000)
        print("AFTER CLOSE:", txt(page.get_by_test_id(f"vault-report-{rid}"))[:600])
    j.shot(page, "report_closed")


def step_manager(j):
    page = j.page(P, mode="light", query="tab=environment&section=manager")
    page.wait_for_timeout(3500)
    for key in d.JOBS:
        card = page.get_by_test_id(f"manager-job-{key}")
        print("JOB", key, card.count(), "|", txt(card)[:400] if card.count() else "")
    firings = page.locator("[data-testid^=manager-firing-]")
    print("FIRINGS", firings.count())
    for i in range(min(firings.count(), 12)):
        print("  FIRING", txt(firings.nth(i))[:260])
    j.shot(page, "manager", full_page=True)



def step_more(j):
    """The long entry's pages, the private entry, and the spec page's Vault warnings."""
    page = vault(j)
    if "spec" in sys.argv[2:]:
        page.close()
        return spec_warnings(j)
    page.get_by_text("Long export log", exact=True).first.click()
    page.wait_for_timeout(2500)
    reader = page.locator("article.vault-reader").first
    body = txt(reader)
    print("LONG: chars shown", len(body), "| has FINAL", "FINAL LINE" in body, "| tail", body[-200:])
    more = reader.get_by_role("button", name="Load more")
    if not more.count():
        more = reader.get_by_text("more", exact=False)
    print("LOAD MORE controls:", more.count())
    for _ in range(3):
        if not more.count() or "FINAL LINE" in txt(reader):
            break
        more.first.click()
        page.wait_for_timeout(2000)
    print("AFTER MORE: has FINAL", "FINAL LINE" in txt(reader))
    j.shot(page, "long_entry")
    page.keyboard.press("Escape")
    page.get_by_text("Private pay rates", exact=True).first.click()
    page.wait_for_timeout(2000)
    print("PRIVATE:", txt(page.locator("article.vault-reader").first)[:500])
    j.shot(page, "private_entry")
    spec_warnings(j)


def spec_warnings(j):
    spec = j.page(P, mode="light", query="tab=spec")
    spec.wait_for_timeout(3000)
    row = spec.get_by_test_id(f"spec-tree-document-{d.S['doc']}")
    (row if row.count() else spec.get_by_text("Export names", exact=True)).first.click()
    spec.wait_for_timeout(3000)
    link = spec.get_by_text("vault conflicts", exact=False)
    print("HEALTH LINK", link.count(), txt(link.first) if link.count() else "")
    if link.count():
        link.first.click()
        spec.wait_for_timeout(1500)
    again = spec.get_by_text("Check against the vault again")
    if again.count():
        again.first.click()
        spec.wait_for_timeout(2500)
        print("AFTER CHECK AGAIN:", txt(spec.locator("body"))[:300], "| toasts:",
              [txt(t) for t in spec.locator("[data-sonner-toast], [role=alert], [role=status]").all()][:6])
        j.shot(spec, "check_again")
        link.first.click()
        spec.wait_for_timeout(800)
    details = spec.get_by_text("Show details")
    if details.count():
        details.first.click()
        spec.wait_for_timeout(1500)
    panel = spec.get_by_test_id("spec-vault-warnings")
    print("WARNINGS PANEL", panel.count(), "|", txt(panel)[:1500] if panel.count() else "")
    check = spec.get_by_test_id("spec-vault-warnings-check")
    if check.count():
        check.click()
        spec.wait_for_timeout(2000)
        print("CHECK NOW (job off):", txt(panel)[-500:], "|", txt(spec.locator("[data-sonner-toaster], [role=status]"))[:400])
    j.shot(spec, "spec_vault_warnings", full_page=True)

if __name__ == "__main__":
    with Judge("s1022-vault", hub=d.e2e.hub(), key=d.e2e.key()) as judge:
        for step in sys.argv[1].split(","):
            print(f"===== {step}")
            try:
                globals()[f"step_{step}"](judge)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
