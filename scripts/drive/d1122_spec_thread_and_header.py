"""Acceptance drive: starting a spec from a thread, and a spec page that agrees with itself.

spec/changes/starting-a-spec-from-a-thread-and-a-spec-page-that-agrees-with-itself, task
acceptance-drive (F1205, F1206, F1208).

Starts a fresh Hub from this checkout's hub/ (AW_DRIVE_PORT, default 8042, a new database in a
temp directory outside the repository; or reuses one named by AW_HUB, AW_KEY and AW_DB -- never
:8000 or :8010), opens three scratch projects beside it, and measures every row the criteria
name. Prints one line per row and one verdict line per criterion (`check <key>: reached=...
failed_at_assertion=...`), and exits 1 on any failure. `--shots <prefix>` also writes
testbed/drive1122-spec-thread/shots/<prefix>-*.png in dark, light and narrow (ac-screens, which
the operator judges). Five short real turns on Haiku 5.5; roughly 10 minutes.

    py -3.11 scripts/drive/d1122_spec_thread_and_header.py [--shots after]

The setup:
  project "spt-start"  no task, no spec: the starter pressed and sent unchanged (ac-starter-arms,
                       ac-starter-no-offer); one real turn
  project "spt-off"    no task, no spec: the starter pressed, Explore turned off, sent
                       (ac-starter-off); one real turn
  project "spt-main"   thread A: the agent creates a change spec (turn 1), then advances it (turn 2):
                       the offer line, its staying put, then Open here. Thread B: the agent creates
                       one (turn 3), then dismiss. Specs written through the routes, no turns:
                         S1  a 40-character title, Markdown summary and problem, acronym ASFGP,
                             one task checked by QA; walked Intake -> Build -> approved -> building
                         S2  two tasks checked by QA and Architect, building
                         S3  saved with two open gaps (no non-goals, no capability named)

What the rows assume of the built change, where the criteria leave it open (the tasks that turn
this green may adjust a selector, never an assertion):
  - the offer line is `[data-testid=spec-created-note]`, carrying `data-path=<spec path>`, with a
    button named "Open here" (or "Open <title> in this thread") and a button whose name says
    dismiss (or Not now, or "Do not open <title> here");
  - the old card is `[data-testid=conversation-spec-offer]` (today's ConversationSpecOffers);
  - the composer's Explore control is `[data-testid=composer-start-exploration]` with aria-pressed,
    and an open spec shows `[data-testid=composer-spec-control]`;
  - the spec page's phase badge is `.aw-sp-head-row2 .aw-sp-phase`, its message badge
    `[data-testid=spec-notice-count]` opening `[data-testid=spec-notices]` of `.aw-notice` rows,
    the flow chip `[data-testid=spec-flow-link]`, the task-id fact `[data-testid=spec-acronym]`.
"""
import datetime
import json
import os
import pathlib
import re
import secrets
import sys
import time
import urllib.parse

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

SHOTS = "testbed/drive1122-spec-thread/shots"
STARTER = "Describe a change you want"
# Exactly 40 characters (ac-header-lines).
S1_TITLE = "Add a shout flag to the greeting command"
S1_PATH = "spec/changes/shout-flag/spec.json"
S2_PATH = "spec/changes/two-checkers/spec.json"
S3_PATH = "spec/changes/two-gaps/spec.json"
STEP_WORDS = ("Intake", "Requirements", "Acceptance", "Approach", "Tasks", "Build", "Review",
              "Test", "Reconcile")
LINE = "[data-testid=spec-created-note]"
CARD = "[data-testid=conversation-spec-offer]"
EXPLORE = "[data-testid=composer-start-exploration]"
# SpecCreatedNote.tsx (master c3937a1) labels its buttons "Open <title> in this thread" and
# "Do not open <title> here"; the visible text is "Open here" and a dismiss mark.
OPEN_NAME = re.compile(r"^Open (here|.+ in this thread)")
DISMISS_NAME = re.compile(r"dismiss|not now|do not open", re.I)

# The on-screen box of the transcript's copy of a message: the text node holding `marker` that
# sits furthest right (the rail's truncated thread title sits left of the transcript).
FIND_TEXT = r"""(marker) => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let best = null;
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.nodeValue || !n.nodeValue.includes(marker)) continue;
    const e = n.parentElement;
    if (!e || e.closest('nav, aside, [contenteditable=true], [data-testid=conversation-header]')) continue;
    const r = e.getBoundingClientRect();
    if (!r.width) continue;
    if (!best || r.left > best.left) best = {top: r.top, bottom: r.bottom, left: r.left};
  }
  return best;
}"""

# The header's rows from the title row to the facts row: visible leaf boxes, merged where they
# overlap vertically. Each merged band is one row.
HEADER_ROWS = r"""() => {
  const head = document.querySelector('[data-testid=spec-document-header]');
  if (!head) return null;
  const title = head.querySelector('.aw-sp-title');
  if (!title) return null;
  const top = title.getBoundingClientRect().top;
  const boxes = [];
  for (const e of head.querySelectorAll('*')) {
    if (e.children.length && [...e.children].some(c => c.getClientRects().length)) continue;
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || r.bottom <= top + 1) continue;
    if (getComputedStyle(e).visibility === 'hidden') continue;
    boxes.push([r.top, r.bottom]);
  }
  boxes.sort((a, b) => a[0] - b[0]);
  const bands = [];
  for (const [t, b] of boxes) {
    const last = bands[bands.length - 1];
    if (last && t < last[1] - 2) last[1] = Math.max(last[1], b);
    else bands.push([t, b]);
  }
  return {rows: bands.length, bands: bands.map(b => b.map(Math.round))};
}"""


class Drive:
    def __init__(self, d, projects, shots):
        self.d, self.projects, self.shots = d, projects, shots
        self.rows = {}
        self.ids = {}

    # -- plumbing -----------------------------------------------------------------------------
    def api(self, method, path, body=None, timeout=60):
        return self.d.api(method, path, body, timeout=timeout)

    def row(self, crit, label, reached, ok, detail=""):
        self.rows.setdefault(crit, []).append((label, bool(reached), bool(reached and ok), detail))
        state = "PASS" if reached and ok else ("FAIL" if reached else "NOT REACHED")
        print(f"  {state:11} {crit} [{label}] {str(detail)[:600]}", flush=True)

    def guard(self, crit, label, fn):
        """Runs one row; an exception the row did not expect is a failure at that row."""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 -- one row's break must not hide the others
            self.row(crit, label, True, False, f"raised {type(exc).__name__}: {str(exc)[:400]}")

    def pid(self, name):
        return self.projects[name][0]

    def url(self, project, **params):
        return f"{self.d.HUB}/?{urllib.parse.urlencode({'project': self.pid(project), **params})}"

    def spec_url(self, project, path):
        return self.url(project, tab="spec", document=path)

    def goto(self, pg, url, wait=2500):
        pg.goto(url)
        pg.wait_for_timeout(wait)

    def shot(self, pg, name):
        if self.shots:
            pg.screenshot(path=f"{SHOTS}/{self.shots}-{name}.png")

    def conversations(self, project):
        return [c for (c,) in self.d.ro("select id from conversations where project_id=? order by created_at",
                                        (self.pid(project),))]

    def entries(self, conv):
        return self.d.ro("select sequence, spec_document, delivered_in_run_id from inbound_queue_entries "
                         "where conversation_id=? order by sequence", (conv,))

    def documents(self, project):
        return self.d.ro("select path, kind, step, phase from spec_documents where project_id=?",
                         (self.pid(project),))

    def thread_specs(self, project, conv):
        code, out = self.api("GET", f"/projects/{self.pid(project)}/conversations/{conv}/spec-documents")
        return out if code == 200 else {"attached": None, "offers": [], "error": f"{code} {out}"}

    def step(self, project, path):
        rows = self.d.ro("select step, phase from spec_documents where project_id=? and path=?",
                         (self.pid(project), path))
        return rows[0] if rows else (None, None)

    def content_version(self, project, path):
        _, read = self.api("GET", f"/projects/{self.pid(project)}/project/spec?path={urllib.parse.quote(path)}")
        return read.get("content_version") if isinstance(read, dict) else None

    def turn(self, project, message, conv=None, agent="Architect"):
        """One chat turn by the API; waits for it. Returns the conversation id, or None."""
        body = {"agent": agent, "message": message, **({"conversation_id": conv} if conv else {})}
        code, out = self.api("POST", f"/projects/{self.pid(project)}/agent/trigger", body)
        if code != 200:
            print(f"  (turn refused: {code} {str(out)[:300]})", flush=True)
            return None
        self.d.wait_idle(self.pid(project), 6 * 60)
        return out.get("conversation_id")

    # -- the starter --------------------------------------------------------------------------
    def press_starter(self, pg, project):
        self.goto(pg, self.url(project, agent="Architect", conversation="__new__"), 3500)
        starter = pg.locator("[data-slot=conversation-starter]").filter(has_text=STARTER)
        if not starter.count():
            return False
        starter.first.click()
        pg.wait_for_timeout(800)
        return True

    @staticmethod
    def explore_on(pg):
        control = pg.locator(EXPLORE)
        if not control.count():
            return None
        return control.first.get_attribute("aria-pressed") == "true"

    def send_composer(self, pg, project, before):
        """Sends what the composer holds; returns the new conversation id once its entry exists."""
        box = pg.get_by_test_id("composer-input").first
        box.click()
        pg.keyboard.press("End")
        box.press("Enter")
        found = {}

        def new_conv():
            fresh = [c for c in self.conversations(project) if c not in before]
            if fresh and self.entries(fresh[0]):
                found["conv"] = fresh[0]
                return True
            return False
        self.d.poll(new_conv, 60, 0.25)
        return found.get("conv")

    def starter_rows(self, b):
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        conv = None

        def arms():
            nonlocal conv
            project = "spt-start"
            if not self.press_starter(pg, project):
                self.row("ac-starter-arms", "the starter in a project with no work", False, False,
                         "no 'Describe a change you want' starter")
                return
            armed = self.explore_on(pg)
            self.shot(pg, "starter-pressed")
            docs_before = self.documents(project)
            conv = self.send_composer(pg, project, set(self.conversations(project)))
            if conv is None:
                self.row("ac-starter-arms", "starter sent", True, False, f"Explore on={armed}; no thread was created")
                return
            first = self.entries(conv)[0]
            specs = self.thread_specs(project, conv)
            attached = specs.get("attached") or {}
            path = attached.get("path")
            self.ids["starter_spec"] = path
            step, _ = self.step(project, path) if path else (None, None)
            self.d.wait_idle(self.pid(project), 6 * 60)
            first = self.entries(conv)[0]
            kind = next((k for p, k, _, _ in self.documents(project) if p == path), None)
            bad = []
            if armed is not True:
                bad.append(f"Explore after pressing the starter: aria-pressed={armed}")
            if not path:
                bad.append("the thread has no spec of its own")
            elif kind != "change-spec" or step != "intake":
                bad.append(f"the thread's spec {path} is {kind} at {step}")
            if path and first[1] != path:
                bad.append(f"the first turn's entry carried spec {first[1]!r}, not {path!r}")
            elif not path:
                bad.append(f"the first turn's entry carried spec {first[1]!r}")
            if not first[2]:
                bad.append("the first turn did not run")
            self.row("ac-starter-arms", "starter pressed, sent unchanged", True, not bad,
                     "; ".join(bad) or f"Explore on; {path} at intake; first turn {first[2]} ran with it"
                     f" (documents before {docs_before})")
        self.guard("ac-starter-arms", "starter arms", arms)

        def no_offer():
            if conv is None:
                self.row("ac-starter-no-offer", "after the first turn", False, False, "no starter thread")
                return
            project = "spt-start"
            self.d.wait_idle(self.pid(project), 6 * 60)
            self.goto(pg, self.url(project, agent="Architect", conversation=conv), 3500)
            # "That spec" is the thread's own, the one the starter made. An agent may write another
            # spec in the same turn (Haiku did on master, 2026-11-22); an offer of that one is not
            # this criterion's.
            own = (self.thread_specs(project, conv).get("attached") or {}).get("path") or self.ids.get("starter_spec")
            lines = pg.locator(f"{LINE}[data-path='{own}']").count() if own else 0
            cards = pg.locator(f"{CARD}[data-path='{own}']").count() if own else 0
            offers = self.thread_specs(project, conv).get("offers")
            offered_own = any(o.get("path") == own for o in offers or []) if own else False
            self.shot(pg, "starter-after-turn")
            self.row("ac-starter-no-offer", "the starter's thread after its first turn", True,
                     lines == 0 and cards == 0 and not offered_own,
                     f"the thread's own spec {own!r}: offer lines {lines}, cards {cards}, offered by the Hub="
                     f"{offered_own}; all lines {pg.locator(LINE).count()}, all cards {pg.locator(CARD).count()}, "
                     f"the Hub offers {[o.get('path') for o in offers or []]}")
        self.guard("ac-starter-no-offer", "starter no offer", no_offer)

        def off():
            project = "spt-off"
            if not self.press_starter(pg, project):
                self.row("ac-starter-off", "the starter in a project with no work", False, False,
                         "no 'Describe a change you want' starter")
                return
            if self.explore_on(pg):
                pg.locator(EXPLORE).first.click()
                pg.wait_for_timeout(400)
            if self.explore_on(pg) is not False:
                self.row("ac-starter-off", "Explore turned off", False, False,
                         f"Explore control state {self.explore_on(pg)}")
                return
            conv_off = self.send_composer(pg, project, set(self.conversations(project)))
            docs_at_send = self.documents(project)
            if conv_off is None:
                self.row("ac-starter-off", "starter sent with Explore off", True, False, "no thread was created")
                return
            first = self.entries(conv_off)[0]
            self.d.wait_idle(self.pid(project), 6 * 60)
            first = self.entries(conv_off)[0]
            attached = self.thread_specs(project, conv_off).get("attached")
            ok = not docs_at_send and first[1] is None and attached is None and bool(first[2])
            self.row("ac-starter-off", "starter pressed, Explore off, sent", True, ok,
                     f"documents when the entry was queued {docs_at_send}; the turn's spec {first[1]!r}; "
                     f"thread spec {attached}; run {first[2]}")
        self.guard("ac-starter-off", "starter off", off)
        ctx.close()

    # -- the offer line -----------------------------------------------------------------------
    def make_offer(self, title, marker):
        """A thread in spt-main where the agent's turn created a change spec. Returns (conv, path)."""
        message = (f"{marker} Call the create_spec_document tool once, with title \"{title}\" and kind "
                   "change-spec. Do nothing else, then reply with just the word done.")
        conv = self.turn("spt-main", message)
        if conv is None:
            return None, None
        offers = self.thread_specs("spt-main", conv).get("offers") or []
        mine = [o for o in offers if o.get("title") == title] or offers
        return conv, (mine[0]["path"] if mine else None)

    def line_facts(self, pg, path, marker, next_marker=None):
        lines = pg.locator(LINE)
        n = lines.count()
        if not n:
            return {"count": 0}
        line = pg.locator(f"{LINE}[data-path='{path}']")
        line = line.first if line.count() else lines.first
        box = line.bounding_box() or {}
        mine = pg.evaluate(FIND_TEXT, marker)
        nxt = pg.evaluate(FIND_TEXT, next_marker) if next_marker else None
        under = bool(mine and box and box["y"] >= mine["bottom"] - 1)
        before_next = nxt is None or bool(box and box["y"] + box["height"] <= nxt["top"] + 1)
        return {"count": n, "text": " ".join(line.inner_text().split()), "under": under,
                "before_next": before_next, "y": box.get("y"), "line": line}

    def offer_rows(self, b):
        a_conv, a_path = self.make_offer("Add a shout flag", "[d1122-a1]")
        reached = bool(a_conv and a_path)
        print(f"  (thread A {a_conv}: offered {a_path})", flush=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        first = {}

        def line():
            self.goto(pg, self.url("spt-main", agent="Architect", conversation=a_conv), 3500)
            facts = self.line_facts(pg, a_path, "[d1122-a1]")
            first.update(facts)
            card = pg.locator(CARD).count()
            dock = pg.get_by_test_id("conversation-composer-area")
            dock_text = dock.inner_text() if dock.count() else ""
            self.shot(pg, "offer-line")
            bad = []
            if facts["count"] != 1:
                bad.append(f"{facts['count']} offer lines")
            else:
                if not re.search(r"Architect created Add a shout flag", facts["text"]):
                    bad.append(f"line reads {facts['text']!r}")
                if not facts["line"].get_by_role("button", name=OPEN_NAME).count():
                    bad.append("no Open here")
                if not facts["line"].get_by_role("button", name=DISMISS_NAME).count():
                    bad.append("no dismiss")
                if not facts["under"]:
                    bad.append("the line is not under the creating turn")
            if card or "Add a shout flag" in dock_text:
                bad.append(f"above the composer: {card} offer cards; composer area mentions it="
                           f"{'Add a shout flag' in dock_text}")
            self.row("ac-offer-line", "thread A after the agent created a spec", reached, not bad,
                     "; ".join(bad) or f"one line {facts['text']!r} under the turn")
        if reached:
            self.guard("ac-offer-line", "line", line)
        else:
            self.row("ac-offer-line", "thread A", False, False, "the agent's turn offered no spec")

        def stays_put():
            step_before = self.step("spt-main", a_path)[0]
            self.turn("spt-main", f"[d1122-a2] Call the advance_spec_step tool once, with path \"{a_path}\". "
                                  "Do nothing else, then reply with just the word done.", a_conv)
            step_after = self.step("spt-main", a_path)[0]
            moved = step_after != step_before
            self.goto(pg, self.url("spt-main", agent="Architect", conversation=a_conv), 3500)
            facts = self.line_facts(pg, a_path, "[d1122-a1]", "[d1122-a2]")
            self.shot(pg, "offer-line-after-step")
            bad = []
            if facts["count"] != 1:
                bad.append(f"{facts['count']} offer lines")
            else:
                if facts["text"] != first.get("text"):
                    bad.append(f"text {first.get('text')!r} -> {facts['text']!r}")
                if not (facts["under"] and facts["before_next"]):
                    bad.append(f"not under the first turn's message (under={facts['under']}, "
                               f"before the second={facts['before_next']})")
                said = [w for w in ("Started",) + STEP_WORDS if re.search(rf"\b{w}\b", facts["text"])]
                if said:
                    bad.append(f"the line says {said}")
            self.row("ac-offer-stays-put", f"a second turn moved the spec {step_before} -> {step_after}",
                     moved, not bad, "; ".join(bad) or f"still one line {facts['text']!r}")
        if reached:
            self.guard("ac-offer-stays-put", "stays put", stays_put)
        else:
            self.row("ac-offer-stays-put", "thread A", False, False, "no offer to watch")

        def open_here():
            self.goto(pg, self.url("spt-main", agent="Architect", conversation=a_conv), 3500)
            line = pg.locator(LINE)
            button = line.get_by_role("button", name=OPEN_NAME)
            if not button.count():
                self.row("ac-offer-open", "Open here", True, False,
                         f"no Open here on an offer line ({line.count()} lines, {pg.locator(CARD).count()} cards)")
                return
            button.first.click()
            pg.wait_for_timeout(1500)
            control = pg.get_by_test_id("composer-spec-control")
            shown = control.count() > 0
            pg.reload()
            pg.wait_for_timeout(3500)
            attached = (self.thread_specs("spt-main", a_conv).get("attached") or {}).get("path")
            gone = pg.locator(LINE).count() == 0
            ok = attached == a_path and shown and gone
            self.row("ac-offer-open", "Open here, then reload", True, ok,
                     f"thread spec {attached!r} (want {a_path!r}); composer shows it={shown}; line gone={gone}")
        if reached:
            self.guard("ac-offer-open", "open", open_here)
        else:
            self.row("ac-offer-open", "thread A", False, False, "no offer to open")

        b_conv, b_path = self.make_offer("Add a whisper flag", "[d1122-b1]")
        print(f"  (thread B {b_conv}: offered {b_path})", flush=True)

        def dismiss():
            before = (self.content_version("spt-main", b_path), self.step("spt-main", b_path))
            self.goto(pg, self.url("spt-main", agent="Architect", conversation=b_conv), 3500)
            line = pg.locator(LINE)
            button = line.get_by_role("button", name=DISMISS_NAME)
            if not button.count():
                self.row("ac-offer-dismiss", "dismiss", True, False,
                         f"no dismiss on an offer line ({line.count()} lines, {pg.locator(CARD).count()} cards)")
                return
            button.first.click()
            pg.wait_for_timeout(1200)
            pg.reload()
            pg.wait_for_timeout(3500)
            gone = pg.locator(LINE).count() == 0
            attached = self.thread_specs("spt-main", b_conv).get("attached")
            after = (self.content_version("spt-main", b_path), self.step("spt-main", b_path))
            ok = gone and attached is None and before == after
            self.row("ac-offer-dismiss", "dismiss, then reload", True, ok,
                     f"line gone={gone}; thread spec {attached}; content/step {before} -> {after}")
        if b_conv and b_path:
            self.guard("ac-offer-dismiss", "dismiss", dismiss)
        else:
            self.row("ac-offer-dismiss", "thread B", False, False, "the agent's turn offered no spec")
        ctx.close()

    # -- the spec page header -----------------------------------------------------------------
    def badge(self, pg):
        e = pg.locator("[data-testid=spec-document-header] .aw-sp-head-row2 .aw-sp-phase")
        return " ".join(e.first.inner_text().split()) if e.count() else None

    def header_text(self, pg):
        e = pg.get_by_test_id("spec-document-header")
        return " ".join(e.first.inner_text().split()) if e.count() else ""

    def badge_row(self, pg, label, want):
        self.goto(pg, self.spec_url("spt-main", S1_PATH), 3000)
        got = self.badge(pg)
        self.shot(pg, f"badge-{label}")
        return got == want, f"{label}: {got!r} (want {want!r})"

    def header_rows(self, b):
        pid = self.pid("spt-main")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        s1 = self.ids.get("s1") or {}

        def badges():
            results = []
            for label, want in (("intake", "Writing · Intake"), ("build", "Writing · Build")):
                step = self.step("spt-main", S1_PATH)[0]
                if label == "build" and step != "build":
                    self.d.as_agent(pid, "Architect", "POST", "/spec/documents/advance",
                                    {"path": S1_PATH, "to": "build"})
                    step = self.step("spt-main", S1_PATH)[0]
                if step != label:
                    results.append((False, False, f"{label}: the spec is at {step}"))
                    continue
                results.append((True,) + self.badge_row(pg, label, want))
            ok_approve = approve_s1(self.d, pid)
            results.append((ok_approve,) + self.badge_row(pg, "approved", "Approved"))
            s1.update(build_s1(self.d, pid))
            results.append((bool(s1.get("build")),) + self.badge_row(pg, "building", "Building"))
            for reached, ok, detail in results:
                self.row("ac-badge-step", detail.split(":")[0], reached, ok, detail)
        self.guard("ac-badge-step", "badges", badges)
        building = bool(s1.get("build"))

        def checker_single():
            self.goto(pg, self.spec_url("spt-main", S1_PATH), 3000)
            text = self.header_text(pg)
            facts = re.findall(r"(?:check|review)\w*[^·|]{0,40}", text, re.I)
            names_qa = any(re.search(r"\bQA\b", f) for f in facts)
            free = re.search(r"any free profile", text, re.I) is not None
            self.row("ac-checker-single", "S1 building, its task checked by QA, no default", building,
                     names_qa and not free,
                     f"build default checker {s1.get('default_checker')!r}; header facts {facts}; "
                     f"'any free profile'={free}")
        self.guard("ac-checker-single", "single", checker_single)

        def checker_mixed():
            s2 = self.ids.get("s2") or {}
            self.goto(pg, self.spec_url("spt-main", S2_PATH), 3000)
            text = self.header_text(pg)
            per_task = re.search(r"per task", text, re.I) is not None
            self.row("ac-checker-mixed", "S2 building, tasks checked by QA and Architect", bool(s2.get("build")),
                     per_task, f"task checkers {s2.get('checkers')}; header {text[:300]!r}")
        self.guard("ac-checker-mixed", "mixed", checker_mixed)

        def task_id():
            self.goto(pg, self.spec_url("spt-main", S1_PATH), 3000)
            fact = pg.get_by_test_id("spec-acronym")
            text = " ".join(fact.first.inner_text().split()) if fact.count() else ""
            real = s1.get("readable") or "ASFGP-1"
            ok = bool(text) and (real in text or "ASFGP-1" in text) and "-N" not in text
            self.row("ac-task-id", "S1, acronym ASFGP", building and s1.get("acronym") == "ASFGP", ok,
                     f"task-id fact {text!r}; first task {real!r}")
        self.guard("ac-task-id", "task id", task_id)

        def lines():
            for width, height, most in ((1440, 900, 2), (1024, 800, 3)):
                c = b.new_context(viewport={"width": width, "height": height})
                p = c.new_page()
                self.goto(p, self.spec_url("spt-main", S1_PATH), 3000)
                chip = p.get_by_test_id("spec-flow-link")
                chip_text = " ".join(chip.first.inner_text().split()) if chip.count() else ""
                measured = p.evaluate(HEADER_ROWS)
                self.shot(p, f"header-{width}")
                rows = (measured or {}).get("rows")
                ok = measured is not None and S1_TITLE not in chip_text and rows <= most
                self.row("ac-header-lines", f"S1 building at {width}x{height}", building and len(S1_TITLE) == 40, ok,
                         f"flow chip {chip_text!r}; {rows} rows (at most {most}): {(measured or {}).get('bands')}")
                c.close()
        self.guard("ac-header-lines", "lines", lines)

        def markdown():
            self.goto(pg, self.spec_url("spt-main", S1_PATH), 3000)
            got = pg.evaluate("""() => {
              const s = document.getElementById('section-summary'), p = document.getElementById('section-problem');
              if (!s || !p) return null;
              const lists = [...p.querySelectorAll('ul, ol')];
              return {s_code: s.querySelectorAll('code').length, s_strong: s.querySelectorAll('strong').length,
                      s_text: s.innerText, p_items: lists.map(l => l.querySelectorAll(':scope > li').length),
                      p_text: p.innerText};
            }""")
            if got is None:
                self.row("ac-markdown", "S1's summary and problem", True, False, "no summary or problem section")
                return
            bad = []
            if not got["s_code"] or not got["s_strong"]:
                bad.append(f"summary: {got['s_code']} code, {got['s_strong']} strong")
            if "`" in got["s_text"] or "**" in got["s_text"]:
                bad.append(f"summary shows {got['s_text'][:120]!r}")
            if 2 not in got["p_items"]:
                bad.append(f"problem lists {got['p_items']}")
            if any(ln.strip().startswith("- ") for ln in got["p_text"].splitlines()):
                bad.append(f"problem shows {got['p_text'][:160]!r}")
            self.row("ac-markdown", "S1's summary and problem", True, not bad, "; ".join(bad) or "rendered")
        self.guard("ac-markdown", "markdown", markdown)

        def message_count():
            s3 = self.ids.get("s3") or {}
            gaps = s3.get("gaps") or []
            reached = len(gaps) == 2
            self.goto(pg, self.spec_url("spt-main", S3_PATH), 3000)
            badge = pg.get_by_test_id("spec-notice-count")
            if not badge.count():
                self.row("ac-message-count", "S3 with two open gaps", reached, False,
                         f"no message badge; the save reported {gaps}")
                return
            number = re.findall(r"\d+", badge.first.inner_text())
            badge.first.click()
            pg.wait_for_timeout(600)
            panel = pg.get_by_test_id("spec-notices")
            text = " ".join(panel.first.inner_text().split()) if panel.count() else ""
            entries = panel.locator(".aw-notice").count() if panel.count() else 0
            self.shot(pg, "message-panel")
            listed = [g for g in gaps if g["match"].search(text)]
            ok = number == ["2"] and entries == 2 and len(listed) == 2
            self.row("ac-message-count", "S3 with two open gaps", reached, ok,
                     f"badge {number}; panel entries {entries}; save reported {[g['code'] for g in gaps]}; "
                     f"listed {[g['code'] for g in listed]}; panel {text[:300]!r}")
        self.guard("ac-message-count", "messages", message_count)
        ctx.close()

    # -- screenshots --------------------------------------------------------------------------
    def screenshots(self, b):
        """ac-screens: the operator's shots, dark, light and narrow."""
        if not self.shots:
            return
        a_conv = self.ids.get("a_conv")
        for theme, width in (("dark", 1440), ("light", 1440), ("narrow", 760)):
            ctx = b.new_context(viewport={"width": width, "height": 900})
            pg = ctx.new_page()
            if theme == "light":
                self.goto(pg, self.url("spt-main"), 1500)
                t = pg.get_by_role("button", name="Switch to light mode")
                if t.count():
                    t.first.click()
            # A fresh offer line for the shots: thread A's was opened by now.
            if self.ids.get("shot_conv"):
                self.goto(pg, self.url("spt-main", agent="Architect", conversation=self.ids["shot_conv"]), 3500)
                self.shot(pg, f"offer-line-{theme}")
            elif a_conv:
                self.goto(pg, self.url("spt-main", agent="Architect", conversation=a_conv), 3500)
                self.shot(pg, f"thread-{theme}")
            for name, path in (("s1", S1_PATH), ("s2", S2_PATH), ("s3", S3_PATH)):
                self.goto(pg, self.spec_url("spt-main", path), 3000)
                self.shot(pg, f"header-{name}-{theme}")
            ctx.close()

    CRITERIA = ("ac-starter-arms", "ac-starter-no-offer", "ac-starter-off", "ac-offer-line",
                "ac-offer-stays-put", "ac-offer-open", "ac-offer-dismiss", "ac-badge-step",
                "ac-checker-single", "ac-checker-mixed", "ac-task-id", "ac-header-lines", "ac-markdown",
                "ac-message-count")

    def report(self):
        failed = False
        print("\nverdict, one line per check:")
        for crit in self.CRITERIA:
            rows = self.rows.get(crit, [])
            reached = bool(rows) and all(r[1] for r in rows)
            ok = reached and all(r[2] for r in rows)
            failed |= not ok
            worst = next((r for r in rows if not r[2]), None)
            detail = f"{worst[0]}: {worst[3]}" if worst else f"{len(rows)} rows pass"
            print(f"check {crit}: reached={'yes' if reached else 'no'} "
                  f"failed_at_assertion={'yes' if reached and not ok else 'no'} -- {str(detail)[:500]}")
        print("check ac-screens: operator -- shots in", SHOTS if self.shots else "(run with --shots)")
        print("RESULT:", "FAIL" if failed else "PASS")
        return 1 if failed else 0


# -- the documents the header rows read ---------------------------------------------------------
def s1_payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": S1_TITLE,
        "summary": "Adds a `--shout` flag so the greeting says **HELLO** in capitals.",
        "problem": "The greeting is always quiet.\n\n- It has no flag to shout\n- It cannot say HELLO",
        "scope": {"in_scope": ["greet.py"], "non_goals": ["Other greetings"]},
        "requirements": [{"key": "shout", "modal": "MUST", "statement": "greet.py MUST shout with --shout."}],
        "acceptance_criteria": [{"key": "shouts", "requirement": "shout", "given": "greet.py",
                                 "when": "it runs with --shout", "then": "it prints HELLO",
                                 "how_to_check": "py greet.py --shout", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Add --shout", "requirements": ["shout"], "files": ["greet.py"],
                   "description": "A drive: change no file.", "builder": "Developer", "checker": "QA",
                   "builder_reason": "Developer builds.", "checker_reason": "QA checks."}],
        "delivery": {"mode": "flow", "agent": "Developer", "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "One task.", "agent": "Developer."}},
    }


def s2_payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Two checkers",
        "summary": "Two files.", "problem": "Neither file exists.",
        "scope": {"in_scope": ["a.txt", "b.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "a", "modal": "MUST", "statement": "The repository MUST hold a.txt."},
                         {"key": "b", "modal": "MUST", "statement": "The repository MUST hold b.txt."}],
        "acceptance_criteria": [
            {"key": "has-a", "requirement": "a", "given": "the repository", "when": "a.txt is read",
             "then": "it exists", "how_to_check": "cat a.txt", "checked_by": "agent"},
            {"key": "has-b", "requirement": "b", "given": "the repository", "when": "b.txt is read",
             "then": "it exists", "how_to_check": "cat b.txt", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Add a.txt", "requirements": ["a"], "files": ["a.txt"],
                   "description": "A drive: change no file.", "builder": "Developer", "checker": "QA",
                   "builder_reason": "Developer builds.", "checker_reason": "QA checks."},
                  {"key": "t2", "title": "Add b.txt", "requirements": ["b"], "files": ["b.txt"],
                   "description": "A drive: change no file.", "builder": "Developer", "checker": "Architect",
                   "builder_reason": "Developer builds.", "checker_reason": "Architect checks."}],
        "delivery": {"mode": "flow", "agent": "Developer", "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "Two tasks.", "agent": "Developer."}},
    }


def s3_payload():
    # Complete but for two things: no non-goals, and no capability named.
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Two gaps",
        "summary": "One file.", "problem": "The file does not exist.",
        "scope": {"in_scope": ["c.txt"], "non_goals": []},
        "requirements": [{"key": "c", "modal": "MUST", "statement": "The repository MUST hold c.txt."}],
        "acceptance_criteria": [{"key": "has-c", "requirement": "c", "given": "the repository",
                                 "when": "c.txt is read", "then": "it exists",
                                 "how_to_check": "cat c.txt", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Add c.txt", "requirements": ["c"], "files": ["c.txt"],
                   "description": "A drive: change no file.", "builder": "Developer", "checker": "QA",
                   "builder_reason": "Developer builds.", "checker_reason": "QA checks."}],
        "delivery": {"mode": "flow", "agent": "Developer", "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "One task.", "agent": "Developer."}},
    }


def write_doc(d, pid, path, title, payload, criteria, before_resave=None):
    base = f"/projects/{pid}"
    code, out = d.api("POST", f"{base}/project/documents", {"title": title, "kind": "change-spec", "path": path})
    d.check(f"setup: {path} is created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": payload})
    d.check(f"setup: {path} saves", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    code, out = d.as_agent(pid, "QA", "POST", "/spec/documents/confirm-criteria", {
        "path": path, "confirmations": [{"criterion": c, "kind": "new"} for c in criteria]})
    d.check(f"setup: {path}'s criteria are confirmed", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    if before_resave:
        before_resave()
    # Saved again so the answer reports the gaps with the confirmations in place.
    code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": payload})
    return out if code == 200 else {}


def approve(d, pid, path):
    quoted = urllib.parse.quote(path)
    _, read = d.api("GET", f"/projects/{pid}/project/spec?path={quoted}")
    version = read.get("content_version") if isinstance(read, dict) else None
    code, out = d.api("POST", f"/projects/{pid}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True, "content_version": version})
    return d.check(f"setup: {path} is approved", code == 200, f"{code} {str(out)[:400]}")


def build(d, pid, path, task_checkers):
    quoted = urllib.parse.quote(path)
    code, out = d.api("POST", f"/projects/{pid}/project/documents/build?path={quoted}",
                      {"driver": "flow", "level": "reviewed", "builders": ["Developer"], "landing": "main",
                       "checker": "", "task_checkers": task_checkers})
    d.check(f"setup: {path} is built as a flow", code == 200, f"{code} {str(out)[:400]}")
    (doc_id,) = d.ro("select id from spec_documents where project_id=? and path=?", (pid, path))[0]
    rows = d.ro("select id, people from builds where document_id=? and state='running'", (doc_id,))
    if not rows:
        return {"build": None, "default_checker": None, "checkers": {}}
    people = json.loads(rows[0][1] or "{}")
    return {"build": rows[0][0], "default_checker": people.get("checker"),
            "checkers": {k: v.get("checker") for k, v in (people.get("tasks") or {}).items()}}


def approve_s1(d, pid):
    return approve(d, pid, S1_PATH)


def build_s1(d, pid):
    got = build(d, pid, S1_PATH, {"t1": "QA"})
    (doc_id,) = d.ro("select id from spec_documents where project_id=? and path=?", (pid, S1_PATH))[0]
    rows = d.ro("select readable_id from tasks where spec_document_id=? order by created_at", (doc_id,))
    got["readable"] = rows[0][0] if rows else None
    d.check("setup: S1's build has no default checker", got["default_checker"] in (None, ""), str(got))
    return got


GAP_WORDS = {"non": re.compile(r"non-?goal|not in this change|out of scope", re.I),
             "capab": re.compile(r"capabilit", re.I)}


def setup_specs(drive):
    d, pid = drive.d, drive.pid("spt-main")
    write_doc(d, pid, S1_PATH, S1_TITLE, s1_payload(), ["shouts"])
    code, out = d.api("POST", f"/projects/{pid}/project/documents/acronym?path={urllib.parse.quote(S1_PATH)}",
                      {"acronym": "ASFGP"})
    d.check("setup: S1's acronym is ASFGP", code == 200, f"{code} {str(out)[:200]}")
    code, out = d.as_agent(pid, "Architect", "POST", "/spec/documents/size",
                           {"path": S1_PATH, "size": "small", "reason": "drive"})
    d.check("setup: S1 is sized small", code == 200, f"{code} {str(out)[:200]}")
    if drive.step("spt-main", S1_PATH)[0] != "intake":
        d.as_agent(pid, "Architect", "POST", "/spec/documents/advance", {"path": S1_PATH, "to": "intake"})
    (acronym,) = d.ro("select acronym from spec_documents where project_id=? and path=?", (pid, S1_PATH))[0]
    drive.ids["s1"] = {"acronym": acronym}
    print(f"  (S1 at {drive.step('spt-main', S1_PATH)}, acronym {acronym})", flush=True)

    write_doc(d, pid, S2_PATH, "Two checkers", s2_payload(), ["has-a", "has-b"])
    s2 = build(d, pid, S2_PATH, {"t1": "QA", "t2": "Architect"}) if approve(d, pid, S2_PATH) else {}
    drive.ids["s2"] = s2
    print(f"  (S2 {s2})", flush=True)

    def s3_at_build():
        d.as_agent(pid, "Architect", "POST", "/spec/documents/size", {"path": S3_PATH, "size": "small", "reason": "drive"})
        code, out = d.api("POST", f"/projects/{pid}/project/documents/journey?path={urllib.parse.quote(S3_PATH)}",
                          {"step": "build"})
        d.check("setup: S3 is at build", code == 200, f"{code} {str(out)[:200]}")
    saved = write_doc(d, pid, S3_PATH, "Two gaps", s3_payload(), ["has-c"], s3_at_build)
    reported = list(saved.get("blocking") or []) + list(saved.get("warnings") or [])
    gaps = []
    for g in reported:
        text = json.dumps(g)
        for word, match in GAP_WORDS.items():
            if match.search(text) or word in text.lower():
                gaps.append({"code": (g.get("code") if isinstance(g, dict) else str(g)), "match": match})
                break
    print(f"  (S3 save reported {[g.get('code') if isinstance(g, dict) else g for g in reported]})", flush=True)
    d.check("setup: S3's save reports exactly the two gaps", len(reported) == 2 and len(gaps) == 2,
            json.dumps(reported)[:600])
    drive.ids["s3"] = {"gaps": gaps if len(reported) == 2 else []}


# -- the Hub and its projects -----------------------------------------------------------------
def setup_hub():
    import d1029_build_plan_in_spec as d

    # Outside the repository: agents in these projects must not read AgentWeave's CLAUDE.md.
    d.TMP = d.TMP.parent.parent / "drive1122-spec-thread" / d.STAMP
    if os.environ.get("AW_HUB"):
        d.HUB, d.KEY, d.DB = os.environ["AW_HUB"].rstrip("/"), os.environ["AW_KEY"], pathlib.Path(os.environ["AW_DB"])
        proc = None
    else:
        d.PORT = int(os.environ.get("AW_DRIVE_PORT") or 8042)
        d.HUB, d.KEY, d.DB = f"http://127.0.0.1:{d.PORT}", "aw_live_" + secrets.token_hex(16), d.TMP / "agentweave.db"
        proc = d.start_hub()
    if any(f":{port}" in d.HUB for port in (8000, 8010)):
        sys.exit("never the operator's or the trial Hub")
    repo = pathlib.Path(__file__).resolve().parents[2]
    if repo in d.TMP.resolve().parents:
        sys.exit(f"the scratch projects must sit outside the repository, not in {d.TMP}")
    try:
        return d, proc, _setup_projects(d)
    except BaseException:
        d.stop_hub(proc)
        raise


def _setup_projects(d):
    projects = {}
    for name in ("spt-start", "spt-off", "spt-main"):
        root = d.TMP / name
        root.mkdir(parents=True, exist_ok=True)
        d.git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("A scratch project with one script, greet.py.\n", encoding="utf-8")
        (root / "greet.py").write_text("print('hello')\n", encoding="utf-8")
        (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
        d.git(root, "add", ".")
        d.git(root, "commit", "-q", "-m", "seed")
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"{name}-{d.STAMP}"})
        d.check(f"setup: project {name} opens", code in (200, 201), f"{code} {project}", fatal=True)
        pid = project["id"]
        projects[name] = (pid, root)
        d.api("PATCH", f"/projects/{pid}", {"main_branch": "main"})
        code, haiku = d.api("POST", f"/projects/{pid}/runners",
                            {"name": "Haiku", "cli": "claude", "model": "claude-haiku-5-5"})
        d.check(f"setup: {name} has a Haiku 5.5 runner", code in (200, 201), f"{code} {haiku}", fatal=True)
        for agent in ("Architect", "Developer", "QA"):
            code, out = d.api("POST", f"/projects/{pid}/agents", {"name": agent, "runner_id": haiku["id"]})
            d.check(f"setup: {name} profile {agent}", code in (200, 201), f"{code} {out}", fatal=True)
    return projects


def main():
    shots = None
    if "--shots" in sys.argv:
        shots = sys.argv[sys.argv.index("--shots") + 1]
        os.makedirs(SHOTS, exist_ok=True)
    d, proc, projects = setup_hub()
    drive = Drive(d, projects, shots)
    started = time.time()
    try:
        print(f"Hub {d.HUB}, projects { {k: v[0] for k, v in projects.items()} }", flush=True)
        setup_specs(drive)
        with sync_playwright() as p:
            b = p.chromium.launch()
            drive.header_rows(b)
            drive.starter_rows(b)
            drive.offer_rows(b)
            if shots:
                drive.ids["shot_conv"], _ = drive.make_offer("Add a quiet flag", "[d1122-c1]")
            drive.screenshots(b)
            b.close()
    finally:
        print(f"(artefacts: {d.TMP}; {int(time.time() - started)}s; finished "
              f"{datetime.datetime.now():%H:%M:%S})", flush=True)
        d.stop_hub(proc)
    return drive.report()


if __name__ == "__main__":
    sys.exit(main())
