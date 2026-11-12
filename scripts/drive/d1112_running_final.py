"""Acceptance drive for the Running tab (SPSRT-3), part 6: each item once, Look, and the final look.

  ac-once         with All selected, the rows are exactly the project's builds, its loops that are no
                  build's, and its jobs that are no loop's (from the Hub's own lists), each title once,
                  and no build's loop or flow job appears as a row of its own
  ac-ended-builds Finished lists "Finished notes" (ended 1d ago) and "Stopped notes" under Stopped early
  ac-stall        "Stalled loop" is under Needs you with the Hub's stall reason, and Look opens its record
  ac-looks        dark and light screenshots at the narrowest width, Now and All, nothing scrolling sideways

    py -3.11 scripts/drive/d1112_running_final.py
"""

import json
import sys

import d1029_build_plan_in_spec as d
import d1112_running_look as look
from playwright.sync_api import sync_playwright

ROWS = ("() => [...document.querySelectorAll('[data-testid=running-tab] li.aw-run-item')].map(li => "
        "({phase: li.dataset.phase, title: li.querySelector('.aw-run-title')?.textContent, "
        "kind: li.querySelector('.aw-run-kind')?.textContent, text: li.innerText.replace(/\\n/g, ' / ')}))")
SIDEWAYS = ("() => { const t = document.querySelector('[data-testid=running-tab]'); const out = [];"
            " for (const el of [t, ...t.querySelectorAll('*')]) { const s = getComputedStyle(el);"
            "  if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1 && !['hidden', 'clip'].includes(s.overflowX))"
            "   out.push((el.className || el.tagName) + ' ' + el.scrollWidth + '>' + el.clientWidth); }"
            " return out.concat(document.documentElement.scrollWidth > window.innerWidth ? ['page'] : []); }")


def main():
    state = json.loads((look.OUT / "state.json").read_text(encoding="utf-8"))
    base = state["base"]
    _, builds = d.api("GET", f"{base}/project/builds")
    _, loops = d.api("GET", f"{base}/loops?include_archived=true")
    _, jobs = d.api("GET", f"{base}/jobs")
    builds = builds["builds"]
    build_docs = {b["document_id"] for b in builds}
    build_loops = {b["loop_id"] for b in builds if b["loop_id"]}
    plain_loops = [lp for lp in loops if lp["id"] not in build_loops and lp.get("spec_document_id") not in build_docs]
    plain_jobs = [j for j in jobs if not j.get("loop")]
    expected = sorted([b["document_title"] for b in builds] + [lp["label"] for lp in plain_loops]
                      + [j["name"] for j in plain_jobs])
    print(f"Hub: {len(builds)} builds, {len(loops)} loops ({len(plain_loops)} plain), {len(jobs)} jobs "
          f"({len(plain_jobs)} plain) -> {len(expected)} items expected")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for mode in ("dark", "light"):
            page = browser.new_page(viewport={"width": 1280, "height": 1400})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            box = look.open_narrow(page, state, mode)
            width = round(box["width"]) if box else None
            page.get_by_test_id("running-tab").screenshot(path=str(look.OUT / f"final-now-{mode}.png"))
            now_sideways = page.evaluate(SIDEWAYS)
            page.get_by_role("radio", name="All").first.click()
            page.wait_for_timeout(500)
            rows = page.evaluate(ROWS)
            page.get_by_test_id("running-tab").screenshot(path=str(look.OUT / f"final-all-{mode}.png"))
            all_sideways = page.evaluate(SIDEWAYS)
            d.check(f"ac-looks ({mode}): panel at the narrowest width, nothing scrolls sideways (Now, All)",
                    width == look.NARROWEST and not now_sideways and not all_sideways,
                    f"{width}px, Now {now_sideways}, All {all_sideways}")
            if mode == "dark":
                titles = sorted(r["title"] for r in rows)
                d.check("ac-once: All lists exactly the Hub's builds, plain loops and plain jobs, each once",
                        titles == expected and len(set(titles)) == len(titles),
                        f"{len(titles)} rows: {titles}" + ("" if titles == expected else f" expected {expected}"))
                doubled = [r for r in rows if r["kind"] != "Build" and r["title"] in {b["document_title"] for b in builds}]
                d.check("ac-once: no build's loop or job is a row of its own", not doubled, str(doubled))
                stall = next((r for r in rows if r["title"] == "Stalled loop"), None)
                hub_reason = next(lp["stall_reason"] for lp in loops if lp["label"] == "Stalled loop")
                d.check("ac-stall: Stalled loop is under Needs you with the Hub's stall reason and Look",
                        stall and stall["phase"] == "needs-you" and hub_reason and hub_reason in stall["text"]
                        and stall["text"].endswith("Look"), f"{stall} / Hub: {hub_reason!r}")
                page.get_by_role("radio", name="Finished").first.click()
                page.wait_for_timeout(500)
                fin = page.evaluate(ROWS)
                page.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "final-finished-dark.png"))
                done = next((r for r in fin if r["title"] == "Finished notes"), None)
                early = next((r for r in fin if r["title"] == "Stopped notes"), None)
                headings = page.locator("[data-testid=running-tab] .aw-run-group-title").all_inner_texts()
                d.check("ac-ended-builds: Finished notes under Finished, ended 1d ago; Stopped notes under Stopped early, with when",
                        done and done["phase"] == "finished" and "ended 1d ago" in done["text"]
                        and early and early["phase"] == "stopped" and "ended" in early["text"],
                        f"{headings} | {done} | {early}")
                page.get_by_role("radio", name="Now").first.click()
                item = page.locator("li.aw-run-item", has=page.locator(".aw-run-title", has_text="Stalled loop"))
                item.get_by_role("button", name="Look").click()
                page.wait_for_timeout(2000)
                page.screenshot(path=str(look.OUT / "final-look-pressed.png"))
                loop_id = next(lp["id"] for lp in loops if lp["label"] == "Stalled loop")
                strip = page.evaluate("() => [...document.querySelectorAll('[aria-label=Panel] [role=tab], [aria-label=Panel] button')]"
                                      ".map(e => e.innerText.trim()).filter(Boolean)")
                body = page.locator("body").inner_text()
                d.check("ac-stall: Look opens the loop's record (its tab in the panel)",
                        page.get_by_test_id("running-tab").count() == 0 and "Stalled loop" in " ".join(strip)
                        and "Write the eta note" in body,
                        f"strip {strip[:8]}; loop {loop_id}")
            d.check(f"no page errors ({mode})", not errors, str(errors[:3]))
            page.close()
        browser.close()
    bad = [n for n, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
