"""Acceptance drive for `reference-a-spec-in-a-sentence-from-the-composer`: the app's real Composer,
mounted alone by `spec_reference_box/` (no Hub), driven in Chromium with real key presses.

    py -3.11 scripts/drive/spec_reference_box.py

Prints one line per check, `check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`,
and exits 1 when any check fails. The harness feeds the Composer the project's documents in the
order the documents route returns them (insertion order, not update time).

The composer's content is read as text with each box written `[[<title>]]` and the caret as `|`.
On the pre-build textarea Composer there is no Specs group and no box, so each check reaches the
composer and fails at its own assertion.
"""

import json
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[2]
UI = REPO / "hub" / "ui"
HARNESS = pathlib.Path(__file__).resolve().parent / "spec_reference_box"
FIELD = "[data-testid=composer-input], textarea.composer-textarea"
DRAFT_KEY = "proj-harness::alpha::conv-harness"
REF_C, REF_A, REF_B = "Ref C: newest reference", "Ref A: reference boxes", "Ref B: older reference"
REF_B_ID = "spdoc-000000000003"
HEADER = "The spec header, redesigned"

# Text with each box as [[title]] and the caret as |, for a textarea or a contenteditable field.
READ = """(el) => {
  if (el.tagName === 'TEXTAREA') {
    const v = el.value, s = el.selectionStart, e = el.selectionEnd
    return s === e ? v.slice(0, s) + '|' + v.slice(s) : v.slice(0, s) + '[' + v.slice(s, e) + ']' + v.slice(e)
  }
  const sel = getSelection(); let out = ''
  const caret = (node, off) => sel.rangeCount && sel.isCollapsed && sel.anchorNode === node && sel.anchorOffset === off
  const walk = (node) => {
    for (let i = 0; i <= node.childNodes.length; i++) {
      if (caret(node, i)) out += '|'
      const c = node.childNodes[i]; if (!c) break
      if (c.nodeType === 3) {
        const t = c.textContent
        for (let j = 0; j <= t.length; j++) { if (caret(c, j)) out += '|'; if (j < t.length) out += t[j] }
      } else if (c.dataset && c.dataset.specBox !== undefined) out += '[[' + (c.dataset.title || c.textContent.trim()) + ']]'
      else if (c.tagName === 'BR') { if (c.nextSibling) out += '\\n' }
      else walk(c)
    }
  }
  walk(el); return out
}"""

# The open menu as a list of ('group', name) and ('option', label, kind, active) in DOM order.
MENU = """() => {
  const menu = document.querySelector('[role=listbox]')
  if (!menu) return null
  return [...menu.querySelectorAll('[data-testid=composer-menu-group], [role=option]')].map((el) =>
    el.getAttribute('role') === 'option'
      ? ['option', el.dataset.label || el.textContent.trim(), el.dataset.kind || 'text', el.getAttribute('aria-selected') === 'true']
      : ['group', el.textContent.trim()])
}"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_harness():
    port = free_port()
    cmd = f"npx vite --config {HARNESS / 'vite.config.mjs'} --port {port} --strictPort --host 127.0.0.1"
    proc = subprocess.Popen(cmd, cwd=UI, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/index.html"
    for _ in range(120):
        try:
            urllib.request.urlopen(url, timeout=1)
            return proc, url
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("harness did not start: " + proc.stdout.read().decode(errors="replace")[-2000:])


def stop(proc):
    subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)


def field(page):
    return page.locator(FIELD).first


def read(page):
    return field(page).evaluate(READ)


def menu(page):
    return page.evaluate(MENU)


def groups(entries):
    """{group: [labels]} from a MENU reading; options before any heading go under ''."""
    out, current = {}, ""
    for entry in entries or []:
        if entry[0] == "group":
            current = entry[1]
            out.setdefault(current, [])
        else:
            out.setdefault(current, []).append(entry[1])
    return out


def active(entries):
    return next((e for e in entries or [] if e[0] == "option" and e[3]), None)


def clear(page):
    field(page).click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.press("Escape")


def stored_draft(page):
    page.wait_for_timeout(450)  # the draft is written 300 ms after the last change
    drafts = page.evaluate("() => localStorage.getItem('aw.composer.drafts.v1')")
    return json.loads(drafts or "{}").get(DRAFT_KEY, "")


def insert_reference(page, query):
    """Put a reference at the caret by the composer's own route: type @query and pick the spec it
    finds first. Picking leaves a space after the box."""
    page.keyboard.type("@" + query)
    page.keyboard.press("Enter")


def check_menu_has_both_groups(page):
    clear(page)
    page.keyboard.type("@head")
    entries = menu(page)
    found = groups(entries)
    specs, files = found.get("Specs", []), found.get("Files", [])
    detail = f"menu {found!r}"
    if HEADER not in specs or not files or not all("head" in f.lower() for f in files):
        return False, detail + f" (want Specs holding {HEADER!r} and a Files group of matching paths)"
    for _ in range(len(specs)):
        page.keyboard.press("ArrowDown")
    landed = active(menu(page))
    page.keyboard.press("Escape")
    after = read(page)
    closed = menu(page) is None
    ok = landed is not None and landed[1] == files[0] and closed and after == "@head|"
    return ok, detail + f"; ArrowDown from the last spec landed on {landed!r} (want {files[0]!r}); Escape: menu closed={closed}, text {after!r}"


def check_specs_by_recency(page):
    clear(page)
    page.keyboard.type("@")
    alone = groups(menu(page)).get("Specs", [])
    page.keyboard.type("ref")
    filtered = groups(menu(page)).get("Specs", [])
    want_alone = ["SPEC-1", REF_C, REF_A, HEADER, REF_B, "Thread chapters", "Model record",
                  "Brand identity", "Flow distribution", "Dashboards"]
    # An edit to B makes it the most recently updated, so it moves to the top.
    page.evaluate(f"() => window.__touch && window.__touch('{REF_B_ID}')")
    page.keyboard.press("Backspace")
    page.keyboard.type("f")
    touched = groups(menu(page)).get("Specs", [])
    page.reload()  # put the documents back as the route reported them, for the checks after this
    field(page).wait_for(timeout=30000)
    ok = alone == want_alone and filtered == [REF_C, REF_A, REF_B] and touched == [REF_B, REF_C, REF_A]
    return ok, (
        f"@ alone: {len(alone)} specs {alone!r}; @ref: {filtered!r} (want {[REF_C, REF_A, REF_B]!r}); "
        f"after B is edited: {touched!r} (want {[REF_B, REF_C, REF_A]!r})"
    )


def check_pick_makes_a_box(page):
    clear(page)
    page.keyboard.type("The spec ")
    page.keyboard.type("@ref")
    page.keyboard.press("Enter")
    got = read(page)
    # The spec icon is a masked span: present, and drawn (a mask image, a non-zero size).
    icons = field(page).evaluate(
        "el => [...el.querySelectorAll('[data-spec-box]')].map(b => { const i = b.querySelector('.composer-spec-box-icon');"
        " if (!i) return false; const s = getComputedStyle(i);"
        " return (s.maskImage || s.webkitMaskImage || 'none') !== 'none' && i.getBoundingClientRect().width > 0 })"
    )
    want = f"The spec [[{REF_C}]] |"
    ok = got == want and icons == [True] and "@" not in got
    return ok, f"composer {got!r} (want {want!r}); boxes with an icon: {icons!r}"


def check_backspace_removes_whole_box(page):
    clear(page)
    page.keyboard.type("see ")
    insert_reference(page, "SPEC-1")
    page.keyboard.type("now")
    for _ in range(4):  # 'now' and the space the pick left: the caret is right after the box
        page.keyboard.press("ArrowLeft")
    before = read(page)
    page.keyboard.press("Backspace")
    after_bs = read(page)
    clear(page)
    page.keyboard.type("see ")
    insert_reference(page, "SPEC-1")
    page.keyboard.type("now")
    for _ in range(4):
        page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    after_left = read(page)
    page.keyboard.press("Delete")
    after_del = read(page)
    ok_bs = after_bs == "see | now"
    ok_left = after_left == "see |[[SPEC-1]] now"
    ok_del = after_del == "see | now"
    detail = (
        f"before {before!r}; Backspace gave {after_bs!r} (want 'see | now'); "
        f"one ArrowLeft gave {after_left!r} (want 'see |[[SPEC-1]] now'); Delete then gave {after_del!r}"
    )
    return ok_bs and ok_left and ok_del, detail


def check_visible_control_opens_menu(page):
    control = page.locator("[data-testid=composer-reference-control]")
    clear(page)
    if control.count() == 0:
        return False, "the composer shows no reference control"
    control.click()
    opened = groups(menu(page))
    page.locator("[role=option]", has_text="SPEC-1").first.click()
    by_control = stored_draft(page)
    shown_control = read(page)
    clear(page)
    page.keyboard.type("@")
    page.locator("[role=option]", has_text="SPEC-1").first.click()
    by_typing = stored_draft(page)
    ok = "Specs" in opened and by_control == by_typing and "[spec: SPEC-1](" in by_control
    return ok, (
        f"control opened {list(opened)!r}; composer {shown_control!r}; stored by control {by_control!r}, "
        f"by typing @ {by_typing!r}"
    )


def check_draft_and_copy(page):
    clear(page)
    page.keyboard.type("Compare ")
    insert_reference(page, "boxes")
    page.keyboard.type("with ")
    insert_reference(page, "older")
    page.keyboard.type("today")
    before = read(page)
    stored_draft(page)
    page.reload()
    field(page).wait_for(timeout=30000)
    restored = field(page).evaluate(READ).replace("|", "")
    field(page).click()
    page.keyboard.press("Control+a")
    # What a copy puts on the clipboard as text/plain, read off the copy event the composer filled.
    page.evaluate("() => document.addEventListener('copy', (e) => { window.__copied = e.clipboardData.getData('text/plain') })")
    page.keyboard.press("Control+c")
    copied = page.evaluate("() => window.__copied ?? ''")
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    sent = page.evaluate("() => window.__sent.at(-1) || ''")
    want = f"Compare [[{REF_A}]] with [[{REF_B}]] today"
    readable = REF_A in copied and REF_B in copied and "<" not in copied
    ok = restored == want and readable and sent == copied.strip()
    return ok, f"before reload {before!r}; after reload {restored!r} (want {want!r}); copied {copied!r}; sent {sent!r}"


def check_delivered_text_from_composer(page):
    """The composer's half of delivered-text: what it submits. The Hub's half (the operator_input
    entry and the runner's prompt) is task RSSC-3's check."""
    clear(page)
    page.keyboard.type("The spec ")
    insert_reference(page, "newest")
    page.keyboard.type("has issues")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    sent = page.evaluate("() => window.__sent.at(-1) || ''")
    refs = re.findall(r"\[spec: ([^\]]*)\]\((spdoc-[0-9a-f]+)\)", sent)
    ok = refs == [(REF_C, "spdoc-000000000005")] and not re.search(r"(^|\s)@", sent)
    return ok, f"sent {sent!r}; references {refs!r}"


def check_keeps_composer_behaviour(page):
    """What the box must not break: a file pick still inserts @path text, Shift+Enter a new line."""
    clear(page)
    insert_reference(page, "SPEC-1")
    page.keyboard.type("and ")
    page.keyboard.type("@README")
    page.keyboard.press("Enter")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("next")
    got = read(page)
    want = "[[SPEC-1]] and @README.md\nnext|"
    return got == want, f"composer {got!r} (want {want!r})"


CHECKS = [
    ("menu-has-both-groups", check_menu_has_both_groups),
    ("specs-by-recency", check_specs_by_recency),
    ("pick-makes-a-box", check_pick_makes_a_box),
    ("backspace-removes-whole-box", check_backspace_removes_whole_box),
    ("visible-control-opens-menu", check_visible_control_opens_menu),
    ("draft-and-copy", check_draft_and_copy),
    ("delivered-text", check_delivered_text_from_composer),
    ("keeps-composer-behaviour", check_keeps_composer_behaviour),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    proc, url = start_harness()
    failed = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context()
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url.rsplit("/", 1)[0])
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.goto(url)
            page.evaluate("() => localStorage.clear()")
            page.reload()
            try:
                field(page).wait_for(timeout=30000)
            except Exception:
                raise SystemExit(f"the harness never showed the composer; page errors: {errors[:5]}")
            print("browser:", browser.version, "| field:", field(page).evaluate("e => e.tagName"))
            for key, fn in CHECKS:
                try:
                    ok, detail = fn(page)
                    reached, at_assertion = "yes", "no" if ok else "yes"
                except Exception as exc:  # noqa: BLE001 - a crash is reported as not reached
                    ok, reached, at_assertion, detail = False, "no", "no", f"{type(exc).__name__}: {exc}"
                failed += not ok
                print(f"check {key}: reached={reached} failed_at_assertion={at_assertion} -- {detail}")
            if errors:
                print("page errors:", errors[:3])
            browser.close()
    finally:
        stop(proc)
    print(f"{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
