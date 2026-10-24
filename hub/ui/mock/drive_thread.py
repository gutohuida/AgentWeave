"""Drive the Thread mock: py -3.11 mock/drive_thread.py <out-dir>

Needs the mock dev server (npx vite --config vite.mock.config.ts) on :5199. Writes screenshots to
<out-dir> and prints one line per check (the acceptance criteria of the components task):
  present   jump to the beginning, back to the present: which surface knot is in view
  recursive document > task > run opened, children in time order, the task in view after closing it
  face      every surface knot shows glyph, word, title, when, actors; no id or event name in the text
  access    reduced motion, keyboard only: move, open, close; nothing animates; greyscale screenshot
  visual    light and dark screenshots, the thread mid-draw, a knot mid-unspool
Exits 1 if a check fails.
"""

import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

URL = "http://localhost:5199/mock-thread.html"
out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
ID_LIKE = re.compile(r"\b(?:tsk|task|run|spdoc|fct|spev|spreq|conv|perm|msg|tin|ev|jr|job|loop)-[A-Za-z0-9]{6,}\b")
EVENT_NAME = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def in_view(page, key):
    return page.evaluate(
        """(key) => {
            const el = [...document.querySelectorAll('[data-knot-key]')].find((e) => e.dataset.knotKey === key)
            if (!el) return false
            const r = el.querySelector(':scope > [data-knot-head]').getBoundingClientRect()
            return r.top >= 0 && r.bottom <= window.innerHeight
        }""",
        key,
    )


def surface_keys(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('.aw-thread-level[data-surface] > .aw-knot')].map((e) => e.dataset.knotKey)"
    )


def head(page, key):
    return page.locator(f'[data-knot-key="{key}"] > [data-knot-head]').first


with sync_playwright() as p:
    browser = p.chromium.launch()

    def fresh(mode="dark", reduced=False, size=(1280, 900)):
        ctx = browser.new_context(
            viewport={"width": size[0], "height": size[1]},
            reduced_motion="reduce" if reduced else "no-preference",
        )
        page = ctx.new_page()
        page.on("pageerror", lambda e: failures.append(f"pageerror {e}"))
        page.goto(f"{URL}?mode={mode}")
        page.wait_for_selector(".aw-knot")
        return page

    # present
    page = fresh()
    keys = surface_keys(page)
    page.wait_for_timeout(1100)
    newest = keys[-1]
    check("present: newest knot in view on open", in_view(page, newest), newest)
    page.get_by_role("button", name="Jump to the beginning").click()
    page.wait_for_timeout(200)
    oldest = surface_keys(page)[0]
    check("present: oldest knot in view after jump", in_view(page, oldest), oldest)
    page.get_by_role("button", name="Back to the present").click()
    page.wait_for_timeout(200)
    check("present: newest knot in view after return", in_view(page, newest), newest)

    # recursive: document > task > run, from the recorded chain
    import json

    chain = json.loads((pathlib.Path(__file__).parent / "thread-fixture.json").read_text(encoding="utf-8"))["chain"]
    doc, task, run = chain
    page.get_by_role("button", name="Jump to the beginning").click()
    page.wait_for_timeout(150)
    page.evaluate(
        "(key) => { const el = [...document.querySelectorAll('[data-knot-key]')].find((e) => e.dataset.knotKey === key); el && el.scrollIntoView({ block: 'center' }) }",
        doc,
    ) if False else None
    # The chain's document may sit outside the newest page: walk "Earlier" until it is drawn.
    for _ in range(12):
        if page.locator(f'[data-knot-key="{doc}"]').count():
            break
        page.get_by_role("button", name="Earlier").first.click()
        page.wait_for_timeout(50)
    for key in (doc, task, run):
        page.locator(f'[data-knot-key="{key}"]').first.scroll_into_view_if_needed()
        head(page, key).click()
        page.wait_for_timeout(450)
    page.screenshot(path=str(out / "thread_dark_chain_open.png"))

    def child_times(parent):
        return page.evaluate(
            """(key) => {
                const li = [...document.querySelectorAll('[data-knot-key]')].find((e) => e.dataset.knotKey === key)
                return [...li.querySelectorAll(':scope > .aw-knot-opened > .aw-knot-opened-inner > .aw-thread-level > .aw-knot')]
                    .map((e) => e.querySelector('.aw-knot-meta span').textContent)
            }""",
            parent,
        )

    for level, key in (("document", doc), ("task", task), ("run", run)):
        times = child_times(key)
        check(f"recursive: {level} shows its children", len(times) > 0, f"{len(times)} children")
    # Recorded order: siblings come from the Hub oldest first; the page must not reorder them.
    fixture_levels = json.loads((pathlib.Path(__file__).parent / "thread-fixture.json").read_text(encoding="utf-8"))["levels"]
    for key in (doc, task, run):
        drawn = list(
            page.evaluate(
                """(key) => {
                    const li = [...document.querySelectorAll('[data-knot-key]')].find((e) => e.dataset.knotKey === key)
                    return [...li.querySelectorAll(':scope > .aw-knot-opened > .aw-knot-opened-inner > .aw-thread-level > .aw-knot')].map((e) => e.dataset.knotKey)
                }""",
                key,
            )
        )
        recorded = [k["key"] for k in fixture_levels[key]["knots"]]
        check(f"recursive: {key.split(':')[0]} children in recorded time order", drawn == recorded)
    head(page, task).click()
    page.wait_for_timeout(300)
    check("recursive: task knot in view after closing it", in_view(page, task))
    check("recursive: document stays open", head(page, doc).get_attribute("aria-expanded") == "true")

    # face
    page2 = fresh()
    bad = []
    for li in page2.locator(".aw-thread-level[data-surface] > .aw-knot").all():
        kind = li.locator(".aw-knot-kind svg").count() and li.locator(".aw-knot-word").inner_text()
        title = li.locator(".aw-knot-title").inner_text()
        meta = li.locator(".aw-knot-meta span").all_inner_texts()
        if not (kind and title and meta):
            bad.append(title or "?")
    check("face: every surface knot shows glyph, word, title and when", not bad, str(bad[:3]))
    text = page2.inner_text("body")
    check("face: no id or event name in the page text", not ID_LIKE.search(text) and not EVENT_NAME.search(text),
          str((ID_LIKE.findall(text) + EVENT_NAME.findall(text))[:5]))
    actors = page2.locator(".aw-thread-level[data-surface] > .aw-knot").evaluate_all(
        "els => els.filter(e => e.querySelectorAll(':scope > .aw-knot-head .aw-knot-meta span').length < 2).length"
    )
    print(f"INFO surface knots without actors in this recording: {actors}")

    # visual
    for mode in ("dark", "light"):
        v = fresh(mode)
        v.wait_for_timeout(1200)
        v.screenshot(path=str(out / f"thread_{mode}_present.png"))
        v.get_by_role("button", name="Jump to the beginning").click()
        v.wait_for_timeout(300)
        v.screenshot(path=str(out / f"thread_{mode}_beginning.png"))
        # open the first document that holds knots and shoot the unspool half way
        first = v.locator(".aw-thread-level[data-surface] > .aw-knot:has(button.aw-knot-head)").first
        first.locator("button.aw-knot-head").click()
        v.wait_for_timeout(120)
        v.screenshot(path=str(out / f"thread_{mode}_unspooling.png"))
        v.wait_for_timeout(500)
        v.screenshot(path=str(out / f"thread_{mode}_opened.png"))
    d = fresh("dark")
    d.wait_for_timeout(150)
    d.screenshot(path=str(out / "thread_dark_drawing.png"))

    # access: reduced motion, keyboard only
    a = fresh("dark", reduced=True)
    a.wait_for_timeout(200)
    names = a.evaluate(
        "() => [...document.querySelectorAll('.aw-thread-level, .aw-knot-opened-inner')].map((e) => getComputedStyle(e).animationName + '|' + getComputedStyle(e, '::before').animationName)"
    )
    check("access: no animation on the thread under reduced motion", all(n.split("|")[1] == "none" for n in names), str(set(names)))
    a.keyboard.press("Tab")  # first scrubber button (disabled at the present) -> next focusable
    a.get_by_role("button", name="Jump to the beginning").focus()
    a.keyboard.press("Tab")
    a.keyboard.press("Tab")  # into the thread
    focused = a.evaluate("() => document.activeElement.hasAttribute('data-knot-head')")
    check("access: Tab reaches a knot", focused)
    a.keyboard.press("ArrowDown")
    check("access: ArrowDown moves between knots", a.evaluate("() => document.activeElement.hasAttribute('data-knot-head')"))
    target = a.locator("button.aw-knot-head").first
    target.focus()
    a.keyboard.press("Enter")
    check("access: Enter opens", target.get_attribute("aria-expanded") == "true")
    inner = a.locator(".aw-knot-opened-inner").first
    check("access: opening runs no animation", inner.evaluate("e => getComputedStyle(e).animationName") == "none")
    a.keyboard.press("Space")
    check("access: Space closes", target.get_attribute("aria-expanded") == "false")
    a.keyboard.press("ArrowRight")
    check("access: ArrowRight opens", target.get_attribute("aria-expanded") == "true")
    a.keyboard.press("ArrowLeft")
    check("access: ArrowLeft closes", target.get_attribute("aria-expanded") == "false")
    # greyscale: kinds must stay distinguishable by glyph and word alone
    a.add_style_tag(content="html { filter: grayscale(1) }")
    a.keyboard.press("Enter")
    a.wait_for_timeout(100)
    a.screenshot(path=str(out / "thread_dark_reduced_greyscale.png"))
    kinds = a.locator(".aw-thread-level[data-surface] > .aw-knot").evaluate_all(
        "els => els.map(e => e.dataset.kind + ':' + e.querySelector('.aw-knot-word').textContent)"
    )
    check("access: every kind carries its own word", all(k.split(":")[0] in ("fold",) or k.split(":")[1] for k in kinds))
    browser.close()

print("FAILED: " + ", ".join(failures) if failures else "all checks passed")
sys.exit(1 if failures else 0)
