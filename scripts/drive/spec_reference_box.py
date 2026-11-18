"""Acceptance drive for `reference-a-spec-in-a-sentence-from-the-composer`: the app's real Composer,
mounted alone by `spec_reference_box/` (no Hub), driven in Chromium with real key presses.

    py -3.11 scripts/drive/spec_reference_box.py

Prints one line per check, `check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`,
and exits 1 when any check fails. The harness feeds the Composer the project's documents in the
order the documents route returns them (insertion order, not update time).

The composer's content is read as text with each box written `[[<title>]]` and the caret as `|`.
On the pre-build textarea Composer there is no Specs group and no box, so each check reaches the
composer and fails at its own assertion.

Every reading taken after a key press or an edit waits, up to a few seconds, for the state the
check wants, and the check judges the last state it saw: React renders after the event, not during
it, so a reading taken at once is a race.

The last check, `edit-moves-to-top`, leaves the harness: it starts a throwaway Hub from this
checkout (its own database and scratch project; never :8000 or :8010), opens the app's conversation
view (AgentOutputPanel, whose composer reads its specs from the documents route through
useSpecDocuments), and edits one document through the Hub's own route. The `spec_updated` event
that write broadcasts is what moves the document to the top of the open menu.
"""

import json
import os
import pathlib
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
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
HAIKU = "claude-haiku-5-5"

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


def specs(page):
    return groups(menu(page)).get("Specs", [])


def settle(page, get, want, ms=4000):
    """`get()` once it gives `want` (a value, or a predicate on the value), or its last reading when
    `ms` runs out; the check judges that reading itself, so a timeout fails at its assertion."""
    test = want if callable(want) else (lambda got: got == want)
    end = time.time() + ms / 1000
    while True:
        got = get()
        if test(got) or time.time() > end:
            return got
        page.wait_for_timeout(50)


def clear(page):
    field(page).click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.press("Escape")
    settle(page, lambda: (read(page), menu(page)), ("|", None))


def stored_draft(page, want=lambda draft: True):
    """The stored draft once it satisfies `want`; the draft is written 300 ms after the last change."""

    def get():
        drafts = page.evaluate("() => localStorage.getItem('aw.composer.drafts.v1')")
        return json.loads(drafts or "{}").get(DRAFT_KEY, "")

    page.wait_for_timeout(450)
    return settle(page, get, want)


def sent_after(page, count):
    """What the composer submitted, once `window.__sent` holds more than `count` messages."""
    settle(page, lambda: page.evaluate("() => window.__sent.length"), lambda n: n > count)
    return page.evaluate("() => window.__sent.at(-1) || ''")


def submit(page):
    count = page.evaluate("() => window.__sent.length")
    page.keyboard.press("Enter")
    return sent_after(page, count)


def insert_reference(page, query):
    """Put a reference at the caret by the composer's own route: type @query and pick the spec it
    finds first. Picking leaves a space after the box."""
    page.keyboard.type("@" + query)
    settle(page, lambda: specs(page), lambda found: bool(found))
    page.keyboard.press("Enter")
    settle(page, lambda: menu(page), None)


def check_menu_has_both_groups(page):
    clear(page)
    page.keyboard.type("@head")
    entries = settle(
        page, lambda: menu(page), lambda e: HEADER in groups(e).get("Specs", []) and bool(groups(e).get("Files"))
    )
    found = groups(entries)
    specs_found, files = found.get("Specs", []), found.get("Files", [])
    detail = f"menu {found!r}"
    if HEADER not in specs_found or not files or not all("head" in f.lower() for f in files):
        return False, detail + f" (want Specs holding {HEADER!r} and a Files group of matching paths)"
    for _ in range(len(specs_found)):
        page.keyboard.press("ArrowDown")
    landed = settle(page, lambda: active(menu(page)), lambda a: a is not None and a[1] == files[0])
    page.keyboard.press("Escape")
    closed = settle(page, lambda: menu(page), None) is None
    after = settle(page, lambda: read(page), "@head|")
    ok = landed is not None and landed[1] == files[0] and closed and after == "@head|"
    return ok, detail + f"; ArrowDown from the last spec landed on {landed!r} (want {files[0]!r}); Escape: menu closed={closed}, text {after!r}"


def check_specs_by_recency(page):
    clear(page)
    want_alone = ["SPEC-1", REF_C, REF_A, HEADER, REF_B, "Thread chapters", "Model record",
                  "Brand identity", "Flow distribution", "Dashboards"]
    page.keyboard.type("@")
    alone = settle(page, lambda: specs(page), want_alone)
    page.keyboard.type("ref")
    filtered = settle(page, lambda: specs(page), [REF_C, REF_A, REF_B])
    # An edit to B makes it the most recently updated, so it moves to the top of the menu already
    # open, with no key pressed. `edit-moves-to-top` makes that edit through a real Hub.
    page.evaluate(f"() => window.__touch && window.__touch('{REF_B_ID}')")
    touched = settle(page, lambda: specs(page), [REF_B, REF_C, REF_A])
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
    settle(page, lambda: specs(page), lambda found: found[:1] == [REF_C])
    page.keyboard.press("Enter")
    want = f"The spec [[{REF_C}]] |"
    got = settle(page, lambda: read(page), want)
    # The spec icon is a masked span: present, and drawn (a mask image, a non-zero size).
    icons = field(page).evaluate(
        "el => [...el.querySelectorAll('[data-spec-box]')].map(b => { const i = b.querySelector('.composer-spec-box-icon');"
        " if (!i) return false; const s = getComputedStyle(i);"
        " return (s.maskImage || s.webkitMaskImage || 'none') !== 'none' && i.getBoundingClientRect().width > 0 })"
    )
    ok = got == want and icons == [True] and "@" not in got
    return ok, f"composer {got!r} (want {want!r}); boxes with an icon: {icons!r}"


def box_then_now(page):
    """'see ' + a box + ' now', with the caret right after the box."""
    clear(page)
    page.keyboard.type("see ")
    insert_reference(page, "SPEC-1")
    page.keyboard.type("now")
    for _ in range(4):  # 'now' and the space the pick left: the caret is right after the box
        page.keyboard.press("ArrowLeft")
    return settle(page, lambda: read(page), "see [[SPEC-1]]| now")


def check_backspace_removes_whole_box(page):
    before = box_then_now(page)
    page.keyboard.press("Backspace")
    after_bs = settle(page, lambda: read(page), "see | now")
    box_then_now(page)
    page.keyboard.press("ArrowLeft")
    after_left = settle(page, lambda: read(page), "see |[[SPEC-1]] now")
    page.keyboard.press("Delete")
    after_del = settle(page, lambda: read(page), "see | now")
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
    opened = groups(settle(page, lambda: menu(page), lambda e: "Specs" in groups(e)))
    page.locator("[role=option]", has_text="SPEC-1").first.click()
    by_control = stored_draft(page, lambda draft: "[spec: SPEC-1](" in draft)
    shown_control = read(page)
    clear(page)
    stored_draft(page, "")
    page.keyboard.type("@")
    settle(page, lambda: specs(page), lambda found: "SPEC-1" in found)
    page.locator("[role=option]", has_text="SPEC-1").first.click()
    by_typing = stored_draft(page, lambda draft: "[spec: SPEC-1](" in draft)
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
    want = f"Compare [[{REF_A}]] with [[{REF_B}]] today"
    before = settle(page, lambda: read(page).replace("|", ""), want)
    stored_draft(page, lambda draft: draft.endswith("today"))
    page.reload()
    field(page).wait_for(timeout=30000)
    restored = settle(page, lambda: read(page).replace("|", ""), want)
    field(page).click()
    page.keyboard.press("Control+a")
    # What a copy puts on the clipboard as text/plain, read off the copy event the composer filled.
    page.evaluate("() => document.addEventListener('copy', (e) => { window.__copied = e.clipboardData.getData('text/plain') })")
    page.keyboard.press("Control+c")
    copied = settle(page, lambda: page.evaluate("() => window.__copied ?? ''"), lambda text: bool(text))
    page.keyboard.press("End")
    sent = submit(page)
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
    settle(page, lambda: read(page), f"The spec [[{REF_C}]] has issues|")
    sent = submit(page)
    refs = re.findall(r"\[spec: ([^\]]*)\]\((spdoc-[0-9a-f]+)\)", sent)
    ok = refs == [(REF_C, "spdoc-000000000005")] and not re.search(r"(^|\s)@", sent)
    return ok, f"sent {sent!r}; references {refs!r}"


def check_keeps_composer_behaviour(page):
    """What the box must not break: a file pick still inserts @path text, Shift+Enter a new line."""
    clear(page)
    insert_reference(page, "SPEC-1")
    page.keyboard.type("and ")
    page.keyboard.type("@README")
    settle(page, lambda: groups(menu(page)).get("Files", []), lambda files: files[:1] == ["README.md"])
    page.keyboard.press("Enter")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("next")
    want = "[[SPEC-1]] and @README.md\nnext|"
    got = settle(page, lambda: read(page), want)
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


# --------------------------------------------------------------------------- a throwaway Hub


class Hub:
    """A Hub started from this checkout's `hub/` on a fresh database in a scratch folder. It serves
    this checkout's committed UI bundle (hub/hub/static/ui), so it is the app as it would ship."""

    def __init__(self):
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.key = "aw_live_" + secrets.token_hex(16)
        self.scratch = pathlib.Path(tempfile.mkdtemp(prefix="spec-reference-box-"))
        self.proc = None

    def __enter__(self):
        env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(self.scratch / 'hub.db').as_posix()}"
        env["AW_BOOTSTRAP_API_KEY"] = self.key
        self.log = open(self.scratch / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "hub.main:app", "--port", str(self.port), "--host", "127.0.0.1"],
            cwd=str(REPO / "hub"), env=env, stdout=self.log, stderr=subprocess.STDOUT,
        )
        end = time.time() + 120
        while self.api("GET", "/projects", timeout=5)[0] != 200:
            if time.time() > end or self.proc.poll() is not None:
                self.__exit__()
                raise RuntimeError(f"the throwaway Hub did not come up; see {self.scratch / 'hub.log'}")
            time.sleep(1)
        return self

    def __exit__(self, *exc):
        if self.proc is not None:
            stop(self.proc)
        self.log.close()

    def api(self, method, path, body=None, timeout=60):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.url + "/api/v1" + path, data,
            {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(errors="replace")[:1000]
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            return 0, str(exc)

    def need(self, method, path, body=None):
        code, out = self.api(method, path, body)
        if code not in (200, 201):
            raise RuntimeError(f"{method} {path}: {code} {out}")
        return out


def document_body(title):
    return {"schema_version": 1, "kind": "change-spec", "title": title, "summary": f"{title}, a drive fixture.",
            "problem": "The drive needs one.", "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]}}


def check_edit_moves_to_top(browser, hub):
    """FR-1's 'edit a document and it moves to the top', through the real app: the conversation
    view's composer, the documents route, and an edit made through the Hub's content route."""
    root = hub.scratch / "project"
    root.mkdir()
    (root / "README.md").write_text("A scratch project for the spec reference drive.\n", encoding="utf-8")
    project = hub.need("POST", "/projects/open", {"path": str(root), "name": "spec-reference-box"})
    base = f"/projects/{project['id']}"
    runner = hub.need("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    hub.need("POST", f"{base}/agents", {"name": "Alpha", "runner_id": runner["id"]})
    paths = {}
    for title in (REF_B, REF_A, REF_C):  # created oldest first: by update time C, A, B
        created = hub.need("POST", f"{base}/project/documents", {"title": title, "kind": "change-spec"})
        paths[title] = created.get("path") or (created.get("document") or {}).get("path")
        time.sleep(1.1)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script(
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s})) } catch (e) {}"
        % (json.dumps(hub.key), json.dumps(hub.url)))
    page = context.new_page()

    def edit_moves(title, before_want, after_want):
        """Open @ref, edit `title` through the Hub, and read the open menu before and after."""
        field(page).wait_for(timeout=30000)
        field(page).click()
        page.keyboard.type("@ref")
        before = settle(page, lambda: specs(page), before_want, ms=10000)
        code, out = hub.api("PUT", f"{base}/project/documents/{paths[title]}/content", {"document": document_body(title)})
        if code != 200:
            raise RuntimeError(f"editing {title!r} was refused: {code} {out}")
        after = settle(page, lambda: specs(page), after_want, ms=10000)
        page.keyboard.press("Escape")
        clear(page)
        return before == before_want and after == after_want, f"{before!r} -> {after!r} (want {before_want!r} -> {after_want!r})"

    try:
        # A new conversation: NewConversationSurface, mounted outside ConversationView.
        page.goto(f"{hub.url}/?project={project['id']}&agent=Alpha", wait_until="domcontentloaded")
        new_ok, new_detail = edit_moves(REF_B, [REF_C, REF_A, REF_B], [REF_B, REF_C, REF_A])
        # An existing conversation: ConversationView's AgentOutputPanel. One message (a Haiku turn)
        # makes the conversation; the menu is read whether or not that turn has ended.
        page.keyboard.type("Say hello, nothing else.")
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r"conversation=conv-"), timeout=30000)
        page.locator("[data-testid=conversation-header]").first.wait_for(timeout=30000)
        open_ok, open_detail = edit_moves(REF_A, [REF_B, REF_C, REF_A], [REF_A, REF_B, REF_C])
        listed = [(d.get("title"), d.get("updated_at")) for d in hub.need("GET", f"{base}/project/documents")["documents"]]
        return new_ok and open_ok, (
            f"throwaway Hub {hub.url}; editing B in a new conversation: {new_detail}; editing A in the open "
            f"conversation {page.url.split('conversation=')[-1]}: {open_detail}; the route lists {listed!r}"
        )
    finally:
        context.close()


def check_timeline_boxes(browser, hub):
    """timeline-box-opens and rename-and-missing, through the real app: a message with a box for a
    real document and one for an id the project does not list is sent, the box is clicked, the
    document is retitled through the Hub's content route, and the missing box is clicked."""
    root = hub.scratch / "timeline-project"
    root.mkdir()
    (root / "README.md").write_text("A scratch project for the timeline boxes.", encoding="utf-8")
    project = hub.need("POST", "/projects/open", {"path": str(root), "name": "spec-reference-timeline"})
    base = f"/projects/{project['id']}"
    runner = hub.need("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    hub.need("POST", f"{base}/agents", {"name": "Alpha", "runner_id": runner["id"]})
    old, new, gone = "Timeline Subject Alpha", "Timeline Subject Renamed", "Vanished Spec"
    created = hub.need("POST", f"{base}/project/documents", {"title": old, "kind": "change-spec"})
    path = created.get("path") or (created.get("document") or {}).get("path")
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script(
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s})) } catch (e) {}"
        % (json.dumps(hub.key), json.dumps(hub.url)))
    page = context.new_page()
    boxes = "[data-testid=timeline-spec-box]"

    def shown():
        return page.evaluate(
            "(sel) => [...document.querySelectorAll(sel)].map((e) => ({id: e.dataset.id, state: e.dataset.state, "
            "text: e.textContent.trim(), title: e.getAttribute('title'), tag: e.tagName}))", boxes)

    def panel_tabs():
        return page.locator("[data-testid^=panel-tab-close-]").count()

    try:
        page.goto(f"{hub.url}/?project={project['id']}&agent=Alpha", wait_until="domcontentloaded")
        field(page).wait_for(timeout=30000)
        field(page).click()
        page.keyboard.type("See ")
        insert_reference(page, "Timeline")
        page.keyboard.type(f"and [spec: {gone}](spdoc-ffffffffffff) now")
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r"conversation=conv-"), timeout=30000)
        found = settle(page, shown, lambda b: len(b) == 2, ms=15000)
        d = next((b for b in found if b["text"].startswith(old)), None)
        if len(found) != 2 or d is None:
            bubbles = page.evaluate("() => [...document.querySelectorAll('.timeline-bubble')].map((e) => e.innerHTML.slice(0, 400))")
            return False, f"timeline boxes {found!r}; wanted two, one reading {old!r}; bubbles {bubbles!r}"
        before_tabs = panel_tabs()
        page.locator(boxes).filter(has_text=old).first.click()
        opened = settle(page, panel_tabs, lambda n: n > before_tabs, ms=8000)
        opens_ok = opened > before_tabs
        timeline_detail = f"boxes {found!r}; clicking {old!r} took panel tabs {before_tabs} -> {opened}"
        code, out = hub.api("PUT", f"{base}/project/documents/{path}/content", {"document": document_body(new)})
        if code != 200:
            raise RuntimeError(f"retitling was refused: {code} {out}")
        page.reload(wait_until="domcontentloaded")
        after = settle(page, shown, lambda b: any(x["text"].startswith(new) for x in b), ms=15000)
        renamed = next((b for b in after if b["text"].startswith(new)), None)
        missing = next((b for b in after if gone in b["text"]), None)
        rename_ok = bool(renamed) and renamed["title"] == old
        missing_ok = bool(missing) and "no longer available" in missing["text"] and missing["state"] == "missing"
        tabs_before = panel_tabs()
        if missing:
            page.locator(boxes).filter(has_text=gone).first.click(force=True)
            page.wait_for_timeout(600)
        inert = missing is not None and panel_tabs() == tabs_before
        return (opens_ok, rename_ok, missing_ok, inert) == (True,) * 4, (
            f"{timeline_detail}; after the retitle {after!r}; clicking the missing box left panel tabs "
            f"{tabs_before} -> {panel_tabs()}; opens={opens_ok} renamed={rename_ok} missing={missing_ok} inert={inert}"
        )
    finally:
        context.close()


def check_panel_insert_not_open(browser, hub):
    """panel-insert-not-open, through the real app: the side panel's spec list and an open spec's
    header each insert a box at the composer's caret, and clicking a row's title opens the spec and
    adds no box."""
    root = hub.scratch / "insert-project"
    root.mkdir()
    (root / "README.md").write_text("A scratch project for inserting from the panel.", encoding="utf-8")
    project = hub.need("POST", "/projects/open", {"path": str(root), "name": "spec-reference-insert"})
    base = f"/projects/{project['id']}"
    runner = hub.need("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    hub.need("POST", f"{base}/agents", {"name": "Alpha", "runner_id": runner["id"]})
    first, second = "Insert Subject One", "Insert Subject Two"
    for title in (first, second):
        hub.need("POST", f"{base}/project/documents", {"title": title, "kind": "change-spec"})
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script(
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s})) } catch (e) {}"
        % (json.dumps(hub.key), json.dumps(hub.url)))
    page = context.new_page()

    def panel_tabs():
        return page.locator("[data-testid^=panel-tab-close-]").count()

    def boxes():
        return read(page).count("[[")

    try:
        page.goto(f"{hub.url}/?project={project['id']}&agent=Alpha", wait_until="domcontentloaded")
        field(page).wait_for(timeout=30000)
        field(page).click()
        page.keyboard.type("Say hello, nothing else.")
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r"conversation=conv-"), timeout=30000)
        page.locator("[data-testid=conversation-header]").first.wait_for(timeout=30000)
        field(page).click()
        page.keyboard.type("note ")
        page.get_by_test_id("conversation-more").click(timeout=15000)
        page.get_by_test_id("conversation-toggle-panel").click(timeout=15000)
        launch = page.locator("[data-testid=panel-launch-specs], [data-testid=panel-tab-specs]").first
        launch.click(timeout=15000)
        row = page.locator("[data-slot=spec-row]").filter(has_text=first).first
        row.wait_for(timeout=15000)
        insert = page.locator("[data-testid=spec-insert-row][aria-label*='%s']" % first)
        if insert.count() == 0:
            return False, f"the spec list shows {row.count()} row(s) for {first!r} and no insert action on any of them"
        insert.click(timeout=5000)
        after_row = settle(page, lambda: read(page), lambda t: t.count("[[") == 1, ms=5000)
        row_ok = boxes() == 1 and f"[[{first}]]" in after_row
        tabs_before = panel_tabs()
        focused = page.evaluate("() => document.activeElement && document.activeElement.matches('[data-testid=composer-input], textarea.composer-textarea')")
        page.locator("[data-slot=spec-row]").filter(has_text=second).first.click()
        opened = settle(page, panel_tabs, lambda n: n > tabs_before, ms=8000)
        open_ok = opened > tabs_before and boxes() == 1
        header_insert = page.locator("[data-testid=spec-insert-header]")
        try:
            header_insert.first.wait_for(timeout=15000)
        except Exception:  # noqa: BLE001 - the action is not there: fail at the assertion
            return False, f"the open spec's header has no insert action; the composer reads {read(page)!r}"
        header_insert.first.click(timeout=15000)
        after_header = settle(page, lambda: read(page), lambda t: t.count("[[") == 2, ms=5000)
        header_ok = f"[[{second}]]" in after_header
        return (row_ok, bool(focused), open_ok, header_ok) == (True,) * 4, (
            f"row insert -> {after_row!r}; composer focused after it={focused}; clicking {second!r} took panel tabs "
            f"{tabs_before} -> {opened} with {boxes() - (1 if header_ok else 0)} boxes; header insert -> {after_header!r}"
        )
    finally:
        context.close()


def report(key, fn, *args):
    try:
        ok, detail = fn(*args)
        reached, at_assertion = "yes", "no" if ok else "yes"
    except Exception as exc:  # noqa: BLE001 - a crash is reported as not reached
        ok, reached, at_assertion, detail = False, "no", "no", f"{type(exc).__name__}: {exc}"
    print(f"check {key}: reached={reached} failed_at_assertion={at_assertion} -- {detail}", flush=True)
    return ok


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
                failed += not report(key, fn, page)
            if errors:
                print("page errors:", errors[:3])
            context.close()
            stop(proc)
            proc = None
            try:
                with Hub() as hub:
                    failed += not report("edit-moves-to-top", check_edit_moves_to_top, browser, hub)
            except RuntimeError as exc:
                failed += 1
                print(f"check edit-moves-to-top: reached=no failed_at_assertion=no -- {exc}")
            try:
                with Hub() as hub:
                    failed += not report("timeline-boxes", check_timeline_boxes, browser, hub)
            except RuntimeError as exc:
                failed += 1
                print(f"check timeline-boxes: reached=no failed_at_assertion=no -- {exc}")
            try:
                with Hub() as hub:
                    failed += not report("panel-insert-not-open", check_panel_insert_not_open, browser, hub)
            except RuntimeError as exc:
                failed += 1
                print(f"check panel-insert-not-open: reached=no failed_at_assertion=no -- {exc}")
            browser.close()
    finally:
        if proc is not None:
            stop(proc)
    total = len(CHECKS) + 3
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
