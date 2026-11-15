"""Acceptance drive for `the-side-panel-s-watch-tab-follows-another-agent-s-conversation-live`
(SPSWT-1), 2026-11-15: the five browser criteria of FR-5..FR-9, written failing first, before the
tab is wired (SPSWT-2). SPSWT-3 runs it green and fixes only the drive.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default
:8019 and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), listening on 127.0.0.1, and refuses
a port something already answers on. Never :8000 or :8010. Real agent turns bind Haiku. The Hub,
project and turn helpers are the Terminal drive's (`panel_terminal_drive.py`).

The scenario. A scratch git repository on branch `main`, Haiku agents A, B and D, conversations
renamed by the operator so their titles are stable, each opened by a quiet turn whose message
carries a marker word, so which conversation the Watch tab draws is read from its text:
  A  C1 "Watch C1" (MARK-ALPHA), C2 "Watch C2" (MARK-BRAVO)
  B  C3 "Watch C3" (MARK-CHARLIE), C4 "Watch C4" (MARK-DELTA)
  D  D1 "Watch D1" (MARK-ECHO)

The checks, in the order they run (survives-switch-and-reload last: it archives B):
  in-this-conversation        watch A's C2 from C1; main view to C2: no C2 timeline, "in this
                              conversation", C1 offered; back to C1: C2 drawn again.
  streams-live                watch B's C3 from C1; B told to answer a question only its output
                              holds (PARIS) and then sleep 25 s: PARIS is in the tab while the run
                              is still running; no textarea, editable box, send/answer/stop/queue
                              button inside the tab.
  state-shown                 B told to call ask_user (blocking); the tab's status is sampled
                              without a reload: working, then waiting for your answer, then (after
                              the drive answers through the questions route) idle, in that order.
  talk-to-switches            a draft typed in C1's composer, Talk to B: the main view is C3 with
                              its composer; back to C1 through the rail: the draft is intact.
  survives-switch-and-reload  watch B's C3 by hand from C1; main view to D's D1 through the rail,
                              then a reload: B and C3 both times. C3 archived: B's default (C4).
                              B archived (the Hub deletes no agent; archiving is its removal): the
                              tab asks which agent to watch.

The page contract the drive probes (the presentational WatchTab, hub/ui/src/components/panel/
WatchTab.tsx; SPSWT-2 may rename these and SPSWT-3 then fixes the drive, not the behaviour):
`[data-testid=watch-tab]`, opened by `panel-tab-watch` / `panel-launch-watch` / the "Add a tab"
menu's "Watch"; the menus are MenuSelect triggers named "Agent to watch" and "Conversation" whose
options are menuitemradio rows; `.aw-watch-status` reads "<agent> is <state>"; `.aw-watch-body`
holds the timeline; the button "Talk to <agent>". The states are matched as the criteria word them:
"working", "waiting for your answer", "idle".

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/watch-drive/<HHMMSS>/.

    py -3.11 scripts/drive/watch_tab_drive.py                 # own Hub on :8019
    py -3.11 scripts/drive/watch_tab_drive.py --only streams-live,state-shown
    py -3.11 scripts/drive/watch_tab_drive.py --self-test     # the drive's own logic, no Hub
"""

import argparse
import json
import os
import pathlib
import re
import sys
import tempfile
import time

STAMP = time.strftime("%H%M%S")
os.environ.setdefault("AW_DRIVE_PORT", "8019")
os.environ.setdefault(
    "AW_DRIVE_DB", str(pathlib.Path(tempfile.gettempdir()) / "drive-watch" / STAMP / "hub.db"))
os.environ.setdefault("AW_DRIVE_HOST", "127.0.0.1")
if os.environ["AW_DRIVE_PORT"] in ("8000", "8010"):
    sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")

ORDER = ["in-this-conversation", "streams-live", "state-shown", "talk-to-switches",
         "survives-switch-and-reload"]
MARKS = {"C1": "MARK-ALPHA", "C2": "MARK-BRAVO", "C3": "MARK-CHARLIE", "C4": "MARK-DELTA",
         "D1": "MARK-ECHO"}
OWNER = {"C1": "A", "C2": "A", "C3": "B", "C4": "B", "D1": "D"}
QUESTION = "Should the watch drive go on?"
STREAM_TURN = ("First reply with the capital of France, in upper case letters, on a line of its "
               "own. Then run this shell command and wait for it to finish: "
               "python -c \"import time; time.sleep(25)\" . Then reply with the single word DONE. "
               "Do not create, edit or delete any file, and do not run git.")
ASK_TURN = (f"Before anything else, call the AgentWeave ask_user tool once, blocking, with the single "
            f"question \"{QUESTION}\" (header \"Go on\", options \"Yes\" and \"No\"), and wait for the "
            "answer. Then reply with the single word FINISHED. Do not create, edit or delete any file.")
FORBIDDEN_BUTTON = re.compile(r"^\s*(send|stop|answer|submit|queue|cancel run|interrupt)\b", re.I)

checks = {}  # key -> (reached, failed, detail)


def record(key, reached, ok, detail):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


# --------------------------------------------------------------------------- pure logic (self-tested)


def classify_state(status):
    """The watched agent's state, as the tab words it, or None."""
    text = (status or "").lower()
    if "waiting for your answer" in text:
        return "waiting"
    if re.search(r"\bworking\b", text):
        return "working"
    if re.search(r"\bidle\b", text):
        return "idle"
    return None


def collapse(seen):
    """Consecutive repeats dropped, unknowns dropped: the sequence of states the tab showed."""
    out = []
    for state in seen:
        if state and (not out or out[-1] != state):
            out.append(state)
    return out


def in_order(seen, wanted):
    """`wanted` occurs in `seen` as a subsequence."""
    it = iter(seen)
    return all(any(s == w for s in it) for w in wanted)


def shows(text, key):
    """Whether a conversation's marker is in the tab's text."""
    return MARKS[key] in (text or "")


def forbidden_controls(buttons):
    return [b for b in buttons if FORBIDDEN_BUTTON.search(b or "")]


def self_test():
    cases = [
        (classify_state("B is working"), "working"),
        (classify_state("B is waiting for your answer"), "waiting"),
        (classify_state("B is idle"), "idle"),
        (classify_state(""), None),
        (collapse(["working", "working", None, "waiting", "waiting", "idle"]),
         ["working", "waiting", "idle"]),
        (in_order(["idle", "working", "waiting", "working", "idle"], ["working", "waiting", "idle"]), True),
        (in_order(["waiting", "working", "idle"], ["working", "waiting", "idle"]), False),
        (shows("hello MARK-CHARLIE there", "C3"), True),
        (shows("hello MARK-DELTA", "C3"), False),
        (forbidden_controls(["Talk to B", "Send", "Stop run", "Agent to watch"]), ["Send", "Stop run"]),
        (len(set(MARKS.values())) == len(MARKS) and set(MARKS) == set(OWNER), True),
        (ORDER[-1], "survives-switch-and-reload"),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


# --------------------------------------------------------------------------- scenario


def build_scenario(t, d):
    t.seed_repo(t.ROOT)
    pid, base, runner = t.new_project(t.ROOT, f"watch-{STAMP}")
    for agent in ("A", "B", "D"):
        t.add_agent(base, runner, agent)
    state = {"pid": pid, "base": base, "conv": {}}
    for key in ("C1", "C2", "C3", "C4", "D1"):
        agent = OWNER[key]
        conv, _ = t.run_turn(d.DB, pid, base, agent,
                             f"Reply with the single word OK. (Marker {MARKS[key]}.) Do not create, "
                             "edit or delete any file, and do not run git.")
        if conv in state["conv"].values():
            raise t.Setup(f"{key}'s turn reused conversation {conv}; a new one was expected")
        state["conv"][key] = conv
        code, out = t.call("PATCH", f"{base}/agent/{agent}/conversations/{conv}", {"title": f"Watch {key}"})
        if code != 200:
            raise t.Setup(f"rename {key}: {code} {str(out)[:200]}")
    print(f"  conversations {state['conv']}", flush=True)
    return state


def runs_of(t, d, pid, agent):
    return t.ro(d.DB, "select id, status from runs where project_id=? and agent=? order by started_at",
                (pid, agent))


def is_live(status):
    return status in ("running", "queued", "starting")


def open_question(t, d, pid, agent):
    rows = t.ro(d.DB, "select id from questions where project_id=? and from_agent=? and answered=0 "
                      "and question like ?", (pid, agent, "%watch drive%"))
    return rows[0][0] if rows else None


# --------------------------------------------------------------------------- the page


def goto(page, t, d, state, key, reload=False):
    if reload:
        page.reload(wait_until="domcontentloaded")
    else:
        page.goto(f"{d.HUB}/?project={state['pid']}&agent={OWNER[key]}&conversation={state['conv'][key]}",
                  wait_until="domcontentloaded")
    page.get_by_test_id("conversation-pane").wait_for(timeout=20000)
    page.wait_for_timeout(1500)


def switch_main(page, d, state, key):
    """Move the main view to `key` inside the app, from the rail, as the operator does."""
    conv = state["conv"][key]
    row = page.get_by_test_id(f"rail-conversation-{conv}")
    if not row.count():
        page.get_by_test_id(f"rail-agent-{state['pid']}-{OWNER[key]}").first.click()
        page.wait_for_timeout(600)
        row = page.get_by_test_id(f"rail-conversation-{conv}")
    if not row.count():
        raise RuntimeError(f"no rail row for {key} ({conv})")
    row.first.click()
    if not d.poll(lambda: conv in page.url, 10, every=0.3):
        raise RuntimeError(f"the main view did not move to {key}; url {page.url}")
    page.get_by_test_id("conversation-pane").wait_for(timeout=20000)
    page.wait_for_timeout(1500)


def watch_tab(page):
    return page.get_by_test_id("watch-tab")


def open_watch(page):
    """Open the panel and its Watch tab; returns whether the tab is there."""
    if watch_tab(page).count():
        return True
    if not page.get_by_test_id("panel-shell").count():
        more = page.get_by_role("button", name="More conversation actions")
        if more.count():
            more.first.click()
            page.get_by_test_id("conversation-toggle-panel").click()
            page.wait_for_timeout(800)
    for opener in (page.get_by_test_id("panel-tab-watch"), page.get_by_test_id("panel-launch-watch")):
        if opener.count():
            opener.first.click()
            break
    else:
        add = page.get_by_test_id("panel-tab-add")
        if add.count():
            add.first.click()
            page.wait_for_timeout(300)
            item = page.get_by_role("menuitem", name=re.compile(r"^\s*Watch", re.I))
            if item.count():
                item.first.click()
            else:
                page.keyboard.press("Escape")
    try:
        watch_tab(page).wait_for(timeout=8000)
    except Exception:  # noqa: BLE001 -- absence is what the checks report
        pass
    page.wait_for_timeout(800)
    return bool(watch_tab(page).count())


def what_is_there(page):
    if watch_tab(page).count():
        return f"watch tab: {tab_text(page)[:160]!r}"
    if page.get_by_test_id("panel-shell").count():
        return "no Watch tab in the panel (the app has none)"
    return "no side panel"


def tab_text(page):
    tab = watch_tab(page)
    return tab.first.inner_text() if tab.count() else ""


def body_text(page):
    body = watch_tab(page).locator(".aw-watch-body")
    return body.first.inner_text() if body.count() else tab_text(page)


def status_text(page):
    status = watch_tab(page).locator(".aw-watch-status")
    return status.first.inner_text() if status.count() else tab_text(page)


def trigger_label(page, name):
    trigger = watch_tab(page).get_by_role("button", name=name)
    return trigger.first.inner_text().strip() if trigger.count() else ""


def menu_options(page, name):
    """Open the tab's `name` menu and return its rows' text, closing it again."""
    trigger = watch_tab(page).get_by_role("button", name=name)
    if not trigger.count():
        return []
    trigger.first.click()
    page.wait_for_timeout(400)
    rows = [r.inner_text() for r in page.get_by_role("menuitemradio").all()]
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    return rows


def choose(page, name, label):
    trigger = watch_tab(page).get_by_role("button", name=name)
    if not trigger.count():
        return False
    trigger.first.click()
    page.wait_for_timeout(400)
    item = page.get_by_role("menuitemradio", name=re.compile(rf"^\s*{re.escape(label)}\b"))
    if not item.count():
        page.keyboard.press("Escape")
        return False
    item.first.click()
    page.wait_for_timeout(1200)
    return True


def watch(page, agent, key=None):
    """Pick `agent` and, by hand, the conversation `key`. Returns what failed, or ''."""
    if not choose(page, "Agent to watch", agent):
        return f"could not pick {agent} from the agent menu ({menu_options(page, 'Agent to watch')})"
    # One open conversation draws no menu: the tab's text names the one shown.
    if key and not choose(page, "Conversation", f"Watch {key}") and f"Watch {key}" not in tab_text(page):
        return f"could not pick Watch {key} from the conversation menu ({menu_options(page, 'Conversation')})"
    return ""


NEWEST_IN_VIEW_JS = """(body) => {
  let el = body;
  while (el.lastElementChild) el = el.lastElementChild;
  if (el === body) return [false, 'the body has no entries'];
  const r = el.getBoundingClientRect(), b = body.getBoundingClientRect();
  const inside = r.top >= b.top - 1 && r.bottom <= b.bottom + 1;
  return [inside, `newest entry ${Math.round(r.top)}..${Math.round(r.bottom)}, body ${Math.round(b.top)}..${Math.round(b.bottom)}`];
}"""


def newest_in_view(page):
    """Whether the newest entry's box lies inside the Watch body's visible rect (not DOM text)."""
    body = watch_tab(page).locator(".aw-watch-body")
    if not body.count():
        return False, "no .aw-watch-body"
    ok, where = body.first.evaluate(NEWEST_IN_VIEW_JS)
    return bool(ok), where


def composer(page):
    return page.get_by_test_id("conversation-pane").locator("textarea")


def shot(page, t, name):
    t.OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(t.OUT / f"{name}.png"))


# --------------------------------------------------------------------------- the checks


def check_in_this_conversation(page, t, d, state):
    key = "in-this-conversation"
    goto(page, t, d, state, "C1")
    if not open_watch(page):
        return record(key, True, False, f"no Watch tab to watch from: {what_is_there(page)}")
    failed = watch(page, "A", "C2")
    if failed:
        return record(key, True, False, failed)
    d.poll(lambda: shows(body_text(page), "C2"), 20, every=0.5)
    before = shows(body_text(page), "C2")
    switch_main(page, d, state, "C2")
    page.wait_for_timeout(1500)
    there, body = tab_text(page), body_text(page)
    said = bool(re.search(r"in this conversation", there, re.I))
    offered = "Watch C1" in there or any("Watch C1" in r for r in menu_options(page, "Conversation"))
    drawn_twice = shows(body, "C2")
    shot(page, t, "in-this-conversation-in-C2")
    switch_main(page, d, state, "C1")
    again = d.poll(lambda: shows(body_text(page), "C2"), 20, every=0.5)
    shot(page, t, "in-this-conversation-back-in-C1")
    ok = before and said and offered and not drawn_twice and again
    record(key, True, ok, f"C2 drawn from C1={before}; in C2: timeline drawn again={drawn_twice}, "
                          f"says in this conversation={said}, offers C1={offered} ({there[:120]!r}); "
                          f"back in C1 C2 drawn={again}")


def check_streams_live(page, t, d, state):
    key, pid = "streams-live", state["pid"]
    goto(page, t, d, state, "C1")
    if not open_watch(page):
        return record(key, True, False, f"no Watch tab to watch from: {what_is_there(page)}")
    failed = watch(page, "B", "C3")
    if failed:
        return record(key, True, False, failed)
    earlier = "PARIS" in body_text(page)
    before = len(runs_of(t, d, pid, "B"))
    t.turn(state["base"], "B", STREAM_TURN, state["conv"]["C3"])
    if not d.poll(lambda: len(runs_of(t, d, pid, "B")) > before, 60, every=0.5):
        raise t.Setup("B's turn did not start within 60s")
    run_id = runs_of(t, d, pid, "B")[-1][0]

    def run_status():
        return t.ro(d.DB, "select status from runs where id=?", (run_id,))[0][0]
    seen_live, status_then = False, None
    deadline = time.time() + t.TURN_WAIT
    while time.time() < deadline:
        status = run_status()
        if "PARIS" in body_text(page):
            seen_live, status_then = is_live(status), status
            break
        if not is_live(status):
            status_then = status
            break
        page.wait_for_timeout(500)
    shot(page, t, "streams-live-during")
    tab = watch_tab(page)
    boxes = tab.locator("textarea, input[type=text], [contenteditable=true]").count()
    buttons = [b.inner_text() or (b.get_attribute("aria-label") or "") for b in tab.get_by_role("button").all()]
    bad = forbidden_controls(buttons)
    d.poll(lambda: not is_live(run_status()), t.TURN_WAIT, every=1)
    page.wait_for_timeout(1500)
    in_view, where = newest_in_view(page)
    shot(page, t, "streams-live-after")
    ok = not earlier and seen_live and boxes == 0 and not bad and in_view
    record(key, True, ok, f"PARIS before the turn={earlier}; PARIS drawn while the run was live={seen_live} "
                          f"(run status then {status_then}); text boxes in the tab={boxes}; "
                          f"forbidden controls={bad}; buttons={buttons[:8]}; "
                          f"newest entry inside the visible body={in_view} ({where})")


def check_state_shown(page, t, d, state):
    key, pid = "state-shown", state["pid"]
    if not watch_tab(page).count():
        goto(page, t, d, state, "C1")
        if not open_watch(page):
            return record(key, True, False, f"no Watch tab to watch from: {what_is_there(page)}")
    failed = watch(page, "B", "C3")
    if failed:
        return record(key, True, False, failed)
    before = len(runs_of(t, d, pid, "B"))
    t.turn(state["base"], "B", ASK_TURN, state["conv"]["C3"])
    seen, answered, question = [], None, None
    deadline = time.time() + t.TURN_WAIT
    while time.time() < deadline:
        seen.append(classify_state(status_text(page)))
        question = question or open_question(t, d, pid, "B")
        if question and answered is None and (collapse(seen)[-1:] == ["waiting"] or len(seen) > 120):
            shot(page, t, "state-shown-waiting")
            code, out = t.call("PATCH", f"{state['base']}/questions/{question}", {"answer": "Yes", "labels": ["Yes"]})
            answered = code
        runs = runs_of(t, d, pid, "B")
        if answered and len(runs) > before and not is_live(runs[-1][1]) and collapse(seen)[-1:] == ["idle"]:
            break
        page.wait_for_timeout(250)
    shown = collapse(seen)
    shot(page, t, "state-shown-end")
    ok = in_order(shown, ["working", "waiting", "idle"])
    record(key, True, ok, f"states the tab showed, in order={shown}; question={question} answered={answered}; "
                          f"status now {status_text(page)[:80]!r}")


def check_talk_to(page, t, d, state):
    key = "talk-to-switches"
    draft = f"DRAFT-KEEP-{STAMP}"
    goto(page, t, d, state, "C1")
    box = composer(page)
    if not box.count():
        raise RuntimeError("C1 has no composer to type a draft into")
    box.first.fill(draft)
    page.wait_for_timeout(1200)
    if not open_watch(page):
        return record(key, True, False, f"no Watch tab to watch from: {what_is_there(page)}")
    failed = watch(page, "B", "C3")
    if failed:
        return record(key, True, False, failed)
    talk = watch_tab(page).get_by_role("button", name=re.compile(r"Talk to B\b"))
    if not talk.count():
        return record(key, True, False, f"no Talk to B button: {tab_text(page)[:160]!r}")
    talk.first.click()
    moved = d.poll(lambda: state["conv"]["C3"] in page.url, 10, every=0.3)
    page.wait_for_timeout(1200)
    has_composer = composer(page).count() > 0 and composer(page).first.is_editable()
    shot(page, t, "talk-to-in-C3")
    switch_main(page, d, state, "C1")
    kept = composer(page).first.input_value() if composer(page).count() else None
    ok = moved and has_composer and kept == draft
    record(key, True, ok, f"main view on C3={moved} (url {page.url[-60:]}); C3 composer editable={has_composer}; "
                          f"C1's draft back={kept!r}")


def check_survives(page, t, d, state):
    key, base = "survives-switch-and-reload", state["base"]
    goto(page, t, d, state, "C1")
    if not open_watch(page):
        return record(key, True, False, f"no Watch tab to watch from: {what_is_there(page)}")
    failed = watch(page, "B", "C3")
    if failed:
        return record(key, True, False, failed)
    d.poll(lambda: shows(body_text(page), "C3"), 20, every=0.5)
    parts = [("from C1", trigger_label(page, "Agent to watch") == "B" and shows(body_text(page), "C3"))]
    switch_main(page, d, state, "D1")
    open_watch(page)
    d.poll(lambda: shows(body_text(page), "C3"), 15, every=0.5)
    parts.append(("in D1", trigger_label(page, "Agent to watch") == "B" and shows(body_text(page), "C3")))
    goto(page, t, d, state, "D1", reload=True)
    open_watch(page)
    d.poll(lambda: shows(body_text(page), "C3"), 15, every=0.5)
    parts.append(("after reload", trigger_label(page, "Agent to watch") == "B" and shows(body_text(page), "C3")))
    shot(page, t, "survives-after-reload")
    code, out = t.call("POST", f"{base}/agent/B/conversations/{state['conv']['C3']}/archive")
    if code != 200:
        raise t.Setup(f"archive C3: {code} {str(out)[:200]}")
    if not d.poll(lambda: shows(body_text(page), "C4"), 8, every=0.5):
        goto(page, t, d, state, "D1", reload=True)
        open_watch(page)
        d.poll(lambda: shows(body_text(page), "C4"), 15, every=0.5)
    parts.append(("C3 closed -> C4", shows(body_text(page), "C4") and not shows(body_text(page), "C3")))
    shot(page, t, "survives-c3-closed")
    for conv in ("C4",):
        t.call("POST", f"{base}/agent/B/conversations/{state['conv'][conv]}/archive")
    code, out = t.call("POST", f"{base}/agents/B/archive")
    if code != 200:
        raise t.Setup(f"archive B: {code} {str(out)[:200]}")
    goto(page, t, d, state, "D1", reload=True)
    open_watch(page)
    page.wait_for_timeout(1500)
    text = tab_text(page)
    asks = bool(re.search(r"which agent|choose an agent|pick an agent", text, re.I)) \
        or trigger_label(page, "Agent to watch") in ("", "Choose…")
    parts.append(("B gone -> asks which agent", asks and not shows(text, "C4") and not shows(text, "C3")))
    shot(page, t, "survives-b-gone")
    record(key, True, all(ok for _, ok in parts),
           "; ".join(f"{n}: {'ok' if ok else 'FAILED'}" for n, ok in parts) + f"; tab now {text[:100]!r}")


def guarded(key, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001 -- a step that broke before its assertion
        print(f"BROKE {key}: {exc}", flush=True)
        checks.setdefault(key, (False, False, f"broke before its assertion: {str(exc)[:200]}"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="check the drive's own logic only; no Hub")
    parser.add_argument("--only", default="", help="comma-separated check keys to run (iteration)")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    only = {k.strip() for k in args.only.split(",") if k.strip()}

    import d1029_build_plan_in_spec as d
    import panel_terminal_drive as t
    from playwright.sync_api import sync_playwright

    t.OUT = d.REPO / "testbed" / "watch-drive" / STAMP
    t.ROOT = pathlib.Path(tempfile.gettempdir()) / "drive-watch" / STAMP / "proj"
    if t.call("GET", "/projects")[0] != 0:
        sys.exit(f"REFUSING: something already answers on :{d.PORT}; this drive starts its own Hub "
                 "from this checkout. Pick another AW_DRIVE_PORT.")
    hub = t.start_hub(d.PORT, d.DB)
    print(f"output {t.OUT}", flush=True)
    setup_error = None
    steps = [("in-this-conversation", check_in_this_conversation), ("streams-live", check_streams_live),
             ("state-shown", check_state_shown), ("talk-to-switches", check_talk_to),
             ("survives-switch-and-reload", check_survives)]
    try:
        state = build_scenario(t, d)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = t.new_page(browser, state)
            for key, fn in steps:
                if not only or key in only:
                    guarded(key, fn, page, t, d, state)
            browser.close()
        t.OUT.mkdir(parents=True, exist_ok=True)
        (t.OUT / "checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    except t.Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        t.stop_hub(hub)
    print("\n== drive_baseline")
    failed = False
    for key in ORDER:
        if only and key not in only:
            continue
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if failed_here else 'no'} -- {detail}")
    print(f"output: {t.OUT}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
