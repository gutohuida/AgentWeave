"""Jobs & loops sweep 2026-10-22, UI (real Chromium, served bundle, scratch Hub :8117, lp1022).

jobs  -- the Jobs tab (JobsScreen/JobsView/JobDetails): the list, a blank-named job's row, the New job
         form (focus, Escape, a Hub refusal on submit, a created job), pause with Undo, Run now on a
         busy flow, the flow's details, archive confirm, the Archived list

py -3.11 scripts/drive/s1022_lp_ui.py <step>
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_lp_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def focused(page):
    return page.evaluate(
        "() => { const e = document.activeElement; return e ? (e.tagName + ' ' + (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 60)) : null }"
    )


def jobs_list(page):
    return norm(page.locator('ul[aria-label="Jobs"]').first.text_content() if page.locator('ul[aria-label="Jobs"]').count() else "<no Jobs list>")


def jobs():
    with Judge("s1022-lp", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="tab=jobs")
        page.wait_for_timeout(4000)
        print("LIST:", jobs_list(page)[:2500])
        j.shot(page, "01_jobs_list", full_page=True)
        rows = page.locator("li.aw-job-item")
        print("rows:", rows.count())
        for i in range(rows.count()):
            print("  ROW", i, norm(rows.nth(i).text_content())[:300])
        # The form: focus on open, Escape closes it, focus returns to New job.
        new = page.get_by_role("button", name=re.compile("New job"))
        new.first.click()
        page.wait_for_timeout(800)
        print("FORM focus on open:", focused(page))
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        print("after Escape: dialog open?", page.locator('[aria-labelledby="create-job-title"]').count(), "| focus:", focused(page))
        # A Hub refusal on submit: both day fields restricted.
        new.first.click()
        page.wait_for_timeout(800)
        dlg = page.locator('[aria-labelledby="create-job-title"]')
        dlg.locator("input").first.fill("ui probe")
        dlg.locator("select").first.select_option("alpha")
        dlg.locator("textarea").first.fill("Reply OK.")
        cron = dlg.locator('input[placeholder*="*"], input[value*="*"]').first
        cron.fill("0 4 13 * 5")
        page.wait_for_timeout(500)
        amb = page.locator('[data-testid="cron-ambiguity"]')
        print("CRON ambiguity:", norm(amb.first.text_content()) if amb.count() else "<none>")
        dlg.get_by_role("button", name=re.compile("^Create")).first.click()
        page.wait_for_timeout(2000)
        print("AFTER refused submit: dialog open?", dlg.count(), "| text:", norm(dlg.first.text_content())[-400:] if dlg.count() else "")
        j.shot(page, "02_form_refused", full_page=True)
        # A blank-after-trim name is refused by the form; fix the cron and create.
        cron.fill("0 4 1 1 *")
        page.wait_for_timeout(300)
        dlg.get_by_role("button", name=re.compile("^Create")).first.click()
        page.wait_for_timeout(2500)
        print("AFTER create: dialog open?", page.locator('[aria-labelledby="create-job-title"]').count(), "| focus:", focused(page))
        print("LIST:", jobs_list(page)[:2500])
        jobs_api = e2e.call("GET", f"/projects/{P}/jobs")
        probe = next((x for x in jobs_api if x["name"] == "ui probe"), None)
        print("API ui probe:", probe and {k: probe[k] for k in ("id", "enabled", "cron", "next_run")})
        if probe:
            sw = page.get_by_role("switch", name="Pause ui probe")
            sw.first.click()
            page.wait_for_timeout(1500)
            print("TOAST after pause:", norm(page.locator("[data-sonner-toast], [role=status]").all_text_contents().__str__())[:400])
            j.shot(page, "03_paused_toast", full_page=True)
            print("API enabled after pause:", next(x for x in e2e.call("GET", f"/projects/{P}/jobs") if x["id"] == probe["id"])["enabled"])
        # Run now on the flow while its agent is busy, then the flow's details.
        flow = next((x for x in jobs_api if x.get("loop")), None)
        if flow:
            row = page.locator("li.aw-job-item", has_text=flow["name"]).first
            row.get_by_role("button", name=re.compile("Run now")).click()
            page.wait_for_timeout(2500)
            note = page.locator(".aw-jobs-notice")
            print("RUN NOW notice:", norm(note.first.text_content()) if note.count() else "<none>")
            print("TOASTS:", [norm(t) for t in page.locator("[data-sonner-toast]").all_text_contents()][:3])
            row.get_by_role("button", name="Expand job details").click()
            page.wait_for_timeout(2500)
            print("DETAILS:", norm(row.text_content())[:2500])
            j.shot(page, "04_flow_details", full_page=True)
        # Archive the blank-named job through its confirm dialog.
        blank = [x for x in jobs_api if not x["name"].strip()]
        print("blank-named jobs:", [(x["id"], repr(x["name"])) for x in blank])
        if probe:
            row = page.locator("li.aw-job-item", has_text="ui probe").first
            row.get_by_role("button", name="More for ui probe").click()
            page.wait_for_timeout(500)
            page.get_by_role("menuitem", name=re.compile("Archive")).first.click()
            page.wait_for_timeout(700)
            print("ARCHIVE dialog focus:", focused(page), "| text:", norm(page.get_by_role("dialog").first.text_content())[:300])
            page.get_by_role("dialog").get_by_role("button", name="Archive").click()
            page.wait_for_timeout(2000)
            print("after archive focus:", focused(page))
            page.get_by_role("radio", name=re.compile("Archived")).first.click() if page.get_by_role("radio", name=re.compile("Archived")).count() else page.get_by_text("Archived", exact=True).first.click()
            page.wait_for_timeout(1500)
            arch = page.locator('ul[aria-label="Archived jobs"]')
            print("ARCHIVED:", norm(arch.first.text_content())[:1500] if arch.count() else "<none>")
            j.shot(page, "05_archived", full_page=True)
        print("console errors:", j.errors[:8])


def jobs2():
    """A loop whose stop time has passed: what the form shows for the Hub's 422; then the flow."""
    with Judge("s1022-lp", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="tab=jobs")
        page.wait_for_timeout(4000)
        page.get_by_role("button", name=re.compile("New job")).first.click()
        page.wait_for_timeout(800)
        dlg = page.locator('[aria-labelledby="create-job-title"]')
        dlg.locator("input").first.fill("past loop")
        dlg.locator("select").first.select_option("alpha")
        dlg.locator("textarea").first.fill("Work the queue.")
        dlg.get_by_text("Make this a loop").first.click()
        page.wait_for_timeout(500)
        tas = dlg.locator("textarea")
        print("textareas:", tas.count())
        if tas.count() > 1:
            tas.nth(1).fill("Drain the queue")
        dlg.locator('input[type="datetime-local"]').first.fill("2020-01-01T00:00")
        dlg.get_by_role("button", name=re.compile("^Create")).first.click()
        page.wait_for_timeout(2500)
        print("AFTER past-stop submit: dialog open?", dlg.count(), "| tail:", norm(dlg.first.text_content())[-300:] if dlg.count() else "")
        print("alerts:", [norm(t) for t in page.get_by_role("alert").all_text_contents()])
        j.shot(page, "06_past_stop_refused", full_page=True)
        print("jobs named past loop:", [x["id"] for x in e2e.call("GET", f"/projects/{P}/jobs?include_archived=true") if x["name"] == "past loop"])
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        jobs_api = e2e.call("GET", f"/projects/{P}/jobs")
        flow = next((x for x in jobs_api if x.get("loop")), None)
        row = page.locator("li.aw-job-item", has_text=flow["name"]).first
        row.get_by_role("button", name=re.compile("Run now")).click()
        page.wait_for_timeout(2500)
        print("RUN NOW notice:", [norm(t) for t in page.locator(".aw-jobs-notice").all_text_contents()])
        print("TOASTS:", [norm(t) for t in page.locator("[data-sonner-toast]").all_text_contents()][:3])
        row.get_by_role("button", name="Expand job details").click()
        page.wait_for_timeout(2500)
        print("DETAILS:", norm(row.text_content())[:2500])
        j.shot(page, "07_flow_details", full_page=True)
        for x in jobs_api:
            if x.get("loop") or x["enabled"]:
                continue
            label = x["name"]
            r = page.locator("li.aw-job-item").filter(has=page.get_by_role("button", name=f"More for {label}")).first
            r.get_by_role("button", name=f"More for {label}").click()
            page.wait_for_timeout(500)
            page.get_by_role("menuitem", name=re.compile("Archive")).first.click()
            page.wait_for_timeout(700)
            d = page.get_by_role("dialog").first
            print(f"ARCHIVE {label!r} dialog: focus", focused(page), "| title:", norm(d.text_content())[:200])
            d.get_by_role("button", name="Archive").click()
            page.wait_for_timeout(2000)
            print("  after: focus", focused(page), "| toasts", [norm(t) for t in page.locator("[data-sonner-toast]").all_text_contents()][:2])
        page.get_by_text("Archived", exact=False).first.click()
        page.wait_for_timeout(1500)
        arch = page.locator('ul[aria-label="Archived jobs"]')
        print("ARCHIVED:", norm(arch.first.text_content())[:1500] if arch.count() else "<none>")
        j.shot(page, "08_archived", full_page=True)
        print("console errors:", j.errors[:8])


if __name__ == "__main__":
    globals()[sys.argv[1]]()
