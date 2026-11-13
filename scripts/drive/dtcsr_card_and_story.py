"""Acceptance drive for `task-card-and-story-redesign` (TCSR-1; FR-3, FR-5, FR-6, FR-7, FR-9, FR-10):
the new task card, its failed-check marker, the folded Story and the Work view, read in a real
Chromium in both themes.

Starts its own Hub from source on :8113 with a fresh database, from the checkout named by `--root`
(default: this one), so the same script runs on master for the baseline and on the build for the
pass. It never touches :8000, and leaves :8010's projects alone: the trial Hub is the one running
the build this drive belongs to, and seeding a scratch project into it would put fixture tasks on
the operator's board. The Hub serves the committed UI bundle (`hub/hub/static/ui`) of that checkout,
which is what reaches the operator.

Every check prints one line

    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>

`reached` is whether the drive got the situation set up and could look (the card on the board, the
task's dialog open); `failed_at_assertion` is whether the behaviour was then absent. Rows the Hub
only writes from inside (runs, check runs, questions, landings, integrations) are seeded through the
models; the requirement document and its accepted evidence go through the operator's routes, so the
Work view's evidence state comes from the real coverage read.

    py -3.11 scripts/drive/dtcsr_card_and_story.py [--root PATH] [--theme dark|light|both] [--port N]
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=str(HERE.parents[1]))
ap.add_argument("--theme", default="both", choices=("dark", "light", "both"))
# Two agents driving at once each need their own Hub; a second Hub on a taken port fails to bind and
# this drive would read the other agent's Hub (its code, not this checkout's).
ap.add_argument("--port", type=int, default=8113)
ARGS = ap.parse_args()
ROOT = pathlib.Path(ARGS.root).resolve()

import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = ARGS.port
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.REPO = ROOT
d.TMP = pathlib.Path(tempfile.gettempdir()) / "dtcsr" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"

sys.path.insert(0, str(ROOT / "hub"))
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from hub.db.models import Question, Run, TaskCheckRun, TaskIntegration, TaskLanding  # noqa: E402

THEMES = ("dark", "light") if ARGS.theme == "both" else (ARGS.theme,)
VIEWPORT = {"width": 1440, "height": 900}  # the board's default width on the operator's screen
AXE_VERSION = "4.10.2"
AXE_CACHE = pathlib.Path(tempfile.gettempdir()) / "dtcsr-axe" / AXE_VERSION
# The longest names AGENT_NAME_RE admits are 32 characters; these are close to it.
BUILDER = "DeveloperSonnetWithALongName2"
REVIEWER = "QualityReviewerWithALongName9"
LONG_QUESTION = (
    "Should the migration keep the old column for one release so that rollbacks on the operator's "
    "live database stay possible, or drop it now and accept that a rollback needs a restore?"
)

LINES = []
_n = iter(range(1, 10_000))


def line(key, reached, failed, detail):
    LINES.append(f"check {key}: reached={'yes' if reached else 'no'} "
                 f"failed_at_assertion={'yes' if (failed or not reached) else 'no'} -- {detail}")
    print(LINES[-1], flush=True)


# ── seeding ──────────────────────────────────────────────────────────────


def engine():
    return create_engine(f"sqlite:///{d.DB.as_posix()}")


def seed(*rows):
    eng = engine()
    with Session(eng) as s:
        s.add_all(rows)
        s.commit()
    eng.dispose()


def sql(statement, **params):
    eng = engine()
    with eng.begin() as c:
        c.execute(text(statement), params)
    eng.dispose()


def uid(prefix):
    return f"{prefix}-tcsr-{next(_n)}"


def make_task(base, title, **body):
    code, made = d.api("POST", f"{base}/tasks", {"title": title, **body})
    assert code in (200, 201), (code, made)
    return made["id"]


def set_status(tid, status, **extra):
    sets = ", ".join(["status = :status"] + [f"{k} = :{k}" for k in extra])
    sql(f"update tasks set {sets} where id = :id", id=tid, status=status, **extra)


def check_result(name, ok, seconds=4.0):
    return {"name": name, "exit_code": 0 if ok else 1, "timed_out": False,
            "duration_seconds": seconds, "output_tail": "" if ok else f"{name}: 1 failed"}


def check_run(pid, tid, state, results, at):
    seed(TaskCheckRun(id=uid("checks"), project_id=pid, task_id=tid, main_sha="a" * 40,
                      target_shas=["b" * 40], state=state, results=results,
                      started_at=at, ended_at=at + timedelta(seconds=30)))


def requirements_doc(base):
    """An approved change document with two requirements, through the operator's routes."""
    path = "spec/changes/tcsr-drive/spec.json"
    quoted = urllib.parse.quote(path)
    payload = {
        "schema_version": 1, "kind": "change-spec", "title": "Drive fixture",
        "summary": "Two requirements.", "problem": "The Work view needs something to show.",
        "scope": {"in_scope": ["fixture"], "non_goals": ["Anything else"]},
        "requirements": [
            {"key": "first", "modal": "MUST", "statement": "The first thing MUST hold."},
            {"key": "second", "modal": "MUST", "statement": "The second thing MUST hold."},
        ],
        "acceptance_criteria": [
            {"key": "c-first", "requirement": "first", "given": "the fixture", "when": "read",
             "then": "the first criterion text is visible", "how_to_check": "drive",
             "checked_by": "agent"},
            {"key": "c-second", "requirement": "second", "given": "the fixture", "when": "read",
             "then": "the second criterion text is visible", "how_to_check": "drive",
             "checked_by": "agent"},
        ],
        "tasks": [{"key": "t1", "title": "Fixture", "requirements": ["first", "second"],
                   "files": ["x"], "description": "Fixture."}],
        "delivery": {"mode": "none", "reasons": {"mode": "A drive fixture."}},
    }
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": "Drive fixture", "kind": "change-spec", "path": path})
    assert code == 201, (code, out)
    code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": payload})
    assert code == 200, (code, str(out)[:600])
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    assert code == 200, (code, str(out)[:600])
    return path


def axe_source():
    """axe-core's browser bundle, fetched once with `npm pack` into its own cache directory."""
    target = AXE_CACHE / "package" / "axe.min.js"
    if not target.exists():
        AXE_CACHE.mkdir(parents=True, exist_ok=True)
        npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
        subprocess.run([npm, "pack", f"axe-core@{AXE_VERSION}", "--silent"], cwd=AXE_CACHE,
                       check=True, capture_output=True, shell=sys.platform == "win32")
        tgz = next(AXE_CACHE.glob("axe-core-*.tgz"))
        with tarfile.open(tgz) as tar:
            tar.extract("package/axe.min.js", AXE_CACHE)
    return target.read_text(encoding="utf-8")


# ── in-page measurements ─────────────────────────────────────────────────

# The card is the element holding the task's open button (the button's parent: today's card and
# the redesigned <article> alike). Its text below the title is every visible text node outside the
# title, counted in line boxes.
CARD_LINES_JS = r"""
([id, title]) => {
  const btn = document.querySelector(`[data-testid="task-open-${id}"]`)
  if (!btn) return null
  const card = btn.parentElement
  const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT)
  // The title: the smallest element whose whole text is the task's title (with its id prefix).
  let titleEl = null
  for (const el of card.querySelectorAll('*')) {
    const t = (el.textContent || '').trim()
    if (t.endsWith(title) && t.length <= title.length + 16) titleEl = el
  }
  const tops = []
  const texts = []
  let node
  while ((node = walker.nextNode())) {
    if (!node.textContent.trim()) continue
    if (titleEl && titleEl.contains(node)) continue
    const parent = node.parentElement
    const style = parent && getComputedStyle(parent)
    if (!style || style.visibility === 'hidden' || style.display === 'none') continue
    const range = document.createRange()
    range.selectNodeContents(node)
    for (const r of range.getClientRects()) {
      if (r.width < 1 || r.height < 1) continue
      texts.push(node.textContent.trim().slice(0, 40))
      if (!tops.some((t) => Math.abs(t - (r.top + r.height / 2)) < 5)) tops.push(r.top + r.height / 2)
    }
  }
  return { lines: tops.length, texts: [...new Set(texts)], width: card.getBoundingClientRect().width,
           titleFound: Boolean(titleEl) }
}
"""

# Whether a text is rendered whole in the card. Range rects report where the text is laid out
# whether or not it is painted, so the text is clipped (cut, or ellipsized) exactly when its rect
# runs past the rect of an element between it and the page that clips its overflow. A scrollWidth
# walk misses this (an inline-flex name inside an overflow-hidden line reports no overflow of its
# own), and inner_text returns the full string even when CSS paints an ellipsis (TCSR-1 send-back).
TEXT_WHOLE_JS_BODY = r"""
  const textWhole = (root, text) => {
    if (!root) return { shown: false, whole: false, why: 'element not in the card' }
    const nodes = []
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    let n, all = ''
    while ((n = walker.nextNode())) { nodes.push([n, all.length]); all += n.textContent }
    const want = text == null ? all.trim() : text
    const at = all.indexOf(want)
    if (!want || at < 0) return { shown: false, whole: false, why: 'text not in the element' }
    const pos = (i) => {
      for (let k = nodes.length - 1; k >= 0; k--) if (nodes[k][1] <= i) return [nodes[k][0], i - nodes[k][1]]
    }
    const range = document.createRange()
    range.setStart(...pos(at))
    range.setEnd(...pos(at + want.length - 1)); range.setEnd(range.endContainer, range.endOffset + 1)
    const rects = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0)
    if (!rects.length) return { shown: false, whole: false, why: 'text has no rendered box' }
    const left = Math.min(...rects.map((r) => r.left)), right = Math.max(...rects.map((r) => r.right))
    const top = Math.min(...rects.map((r) => r.top)), bottom = Math.max(...rects.map((r) => r.bottom))
    let el = range.commonAncestorContainer
    if (el.nodeType !== 1) el = el.parentElement
    for (; el && el !== document.documentElement; el = el.parentElement) {
      const st = getComputedStyle(el)
      if (st.display === 'none' || st.visibility === 'hidden')
        return { shown: false, whole: false, why: `hidden by <${el.tagName.toLowerCase()} class="${el.className}">` }
      // Chromium clips a <button>'s content whatever its overflow says; contain and clip-path clip too.
      const forced = el.tagName === 'BUTTON' || /paint|strict|content/.test(st.contain) || st.clipPath !== 'none'
      const clipX = forced || st.overflowX !== 'visible', clipY = forced || st.overflowY !== 'visible'
      if (!clipX && !clipY) continue
      const b = el.getBoundingClientRect()
      const cut = (clipX && (left < b.left - 1 || right > b.right + 1)) || (clipY && (top < b.top - 1 || bottom > b.bottom + 1))
      if (cut) return { shown: true, whole: false,
        why: `clipped by <${el.tagName.toLowerCase()} class="${el.className}">: text ${Math.round(left)}-${Math.round(right)}px, box ${Math.round(b.left)}-${Math.round(b.right)}px` }
    }
    // Laid out inside every clip, but something else may be painted over it (an action button).
    for (const r of rects) {
      for (const f of [0.02, 0.5, 0.98]) {
        const x = r.left + r.width * f, y = r.top + r.height / 2
        const top = document.elementFromPoint(x, y)
        if (top && !top.contains(range.startContainer) && !(range.commonAncestorContainer.contains && range.commonAncestorContainer.contains(top)))
          return { shown: true, whole: false,
            why: `covered at ${Math.round(x)}px by <${top.tagName.toLowerCase()} class="${top.className && top.className.baseVal !== undefined ? top.className.baseVal : top.className}">` }
      }
    }
    const host = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement
    return { shown: true, whole: true, why: `text ${Math.round(left)}-${Math.round(right)}px in <${host.tagName.toLowerCase()} class="${host.className}">` }
  }
"""

# Whether *name* is shown whole in the card: the smallest element holding the full name, with the
# name's rendered text inside every clipping ancestor.
NAME_WHOLE_JS = r"""
([id, name]) => {
""" + TEXT_WHOLE_JS_BODY + r"""
  const btn = document.querySelector(`[data-testid="task-open-${id}"]`)
  if (!btn) return null
  const card = btn.parentElement
  let best = null
  for (const el of card.querySelectorAll('*')) {
    if ((el.textContent || '').includes(name) && (!best || best.contains(el))) best = el
  }
  if (!best) return { shown: false, whole: false, why: 'name not in the card' }
  return textWhole(best, name)
}
"""

# The waits-on line and the time at stage: whether each shows, and whether waits-on is whole.
# FR-3: when both do not fit, waits-on is kept and time at stage gives way.
WAITS_JS = r"""
(id) => {
""" + TEXT_WHOLE_JS_BODY + r"""
  const btn = document.querySelector(`[data-testid="task-open-${id}"]`)
  if (!btn) return null
  const card = btn.parentElement
  const waitsEl = document.querySelector(`[data-testid="task-stage-waits-on-${id}"]`) || card.querySelector('.aw-tcard-waits')
  const ageEl = document.querySelector(`[data-testid="task-stage-age-${id}"]`) || card.querySelector('.aw-tcard-age')
  const waits = waitsEl ? textWhole(waitsEl, null) : { shown: false, whole: false, why: 'no waits-on element' }
  const age = ageEl ? textWhole(ageEl, null) : { shown: false, whole: false, why: 'no time-at-stage element' }
  return { waitsText: waitsEl ? (waitsEl.textContent || '').trim() : '', waits,
           ageText: ageEl ? (ageEl.textContent || '').trim() : '', ageShown: age.shown, ageWhole: age.whole }
}
"""

# Starts recording animations and transitions in the card from now on.
MOTION_ARM_JS = r"""
(id) => {
  const inCard = (el) => {
    const btn = document.querySelector(`[data-testid="task-open-${id}"]`)
    const card = btn && btn.parentElement
    return Boolean(card && el && (card.contains(el) || el.contains(card)))
  }
  const before = new Set(document.getAnimations())
  window.__tcsr = { events: [], anims: [], t0: performance.now() }
  for (const type of ['animationstart', 'transitionrun']) {
    document.addEventListener(type, (e) => {
      if (inCard(e.target)) window.__tcsr.events.push({ type, at: performance.now(), name: e.animationName || e.propertyName })
    }, true)
  }
  const seen = new Set()
  const tick = () => {
    for (const a of document.getAnimations()) {
      if (before.has(a) || seen.has(a)) continue
      const target = a.effect && a.effect.target
      if (!inCard(target)) continue
      seen.add(a)
      const t = a.effect.getComputedTiming()
      const onStage = Boolean(target.closest && target.closest(`[data-testid="task-stage-${id}"], .aw-thread`))
      const where = target.getAttribute('data-testid') || (typeof target.className === 'string' ? target.className : '') || target.tagName
      window.__tcsr.anims.push({ name: (a.animationName || a.transitionProperty || 'animation') + '@' + where.slice(0, 50),
                                 total: (t.delay || 0) + (t.activeDuration === Infinity ? Infinity : t.activeDuration),
                                 iterations: t.iterations, onStage })
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
  return true
}
"""

STORY_HEADS_JS = r"""
(id) => {
  const root = document.querySelector(`[data-testid="task-story-events-${id}"]`)
  if (!root) return null
  return [...root.querySelectorAll(':scope > .aw-tl-item')].map((item) => {
    const head = item.querySelector('.aw-tl-head')
    if (!head) return { id: item.dataset.testid || '', label: '' }
    const clone = head.cloneNode(true)
    clone.querySelectorAll('.aw-tl-aside').forEach((n) => n.remove())
    return { id: item.dataset.testid || '', label: clone.textContent.replace(/\s+/g, ' ').trim() }
  })
}
"""

STAGE_SIGNATURE_JS = r"""
(id) => {
  const el = document.querySelector(`[data-testid="task-stage-${id}"]`)
  if (!el) return null
  const glyph = el.querySelector('svg, [data-icon], .material-symbols-outlined, .material-icons')
  const glyphSig = glyph ? (glyph.getAttribute('data-icon') || glyph.textContent || glyph.innerHTML).slice(0, 200) : ''
  const word = (el.querySelector('.aw-tcard-word') || el).textContent.trim().slice(0, 40)
  return { glyph: glyphSig, word }
}
"""


# ── the drive ────────────────────────────────────────────────────────────


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "tcsr-drive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    now = datetime.now(timezone.utc)

    code, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    assert code in (200, 201), (code, runner)
    for name in (BUILDER, REVIEWER):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        assert code in (200, 201), (code, out)
    doc = requirements_doc(base)
    t = {}

    # ac-budget: waiting on a long question, long builder and reviewer names.
    t["budget"] = make_task(base, "Decide the migration rollback", builder=BUILDER, checker=REVIEWER,
                            assignee=BUILDER)
    set_status(t["budget"], "in_progress")  # the open blocking question below makes it wait
    seed(Question(id=uid("q"), project_id=pid, from_agent=BUILDER, question=LONG_QUESTION,
                  blocking=True, blocked_task_id=t["budget"]))

    # ac-checks: completed, latest checks failed two of five.
    t["checks"] = make_task(base, "Failing checks before review", builder=BUILDER, checker=REVIEWER)
    set_status(t["checks"], "completed")
    failed_names = ("lint-tcsr", "types-tcsr")
    check_run(pid, t["checks"], "failed",
              [check_result("format-tcsr", True), check_result(failed_names[0], False),
               check_result("unit-tcsr", True), check_result(failed_names[1], False),
               check_result("build-tcsr", True)], now - timedelta(minutes=5))

    # ac-story: six consecutive runs, an answered question, a landing, in time order.
    t["story"] = make_task(base, "A task with a long story", builder=BUILDER, checker=REVIEWER)
    set_status(t["story"], "approved")
    start = now - timedelta(hours=3)
    run_ids = []
    for i in range(6):
        rid = uid("run")
        run_ids.append(rid)
        seed(Run(id=rid, project_id=pid, agent=BUILDER if i % 2 == 0 else REVIEWER,
                 status="completed", task_id=t["story"], conversation_id=uid("conv"),
                 started_at=start + timedelta(minutes=10 * i),
                 ended_at=start + timedelta(minutes=10 * i + 5)))
    question_id = uid("q")
    seed(Question(id=question_id, project_id=pid, from_agent=BUILDER, question=LONG_QUESTION,
                  blocking=True, blocked_task_id=t["story"], answered=True,
                  answer="Keep it for one release.", created_at=start + timedelta(minutes=70)))
    integration_id = uid("integration")
    seed(TaskIntegration(id=integration_id, project_id=pid, task_id=t["story"],
                         commit_sha="c" * 40, outcome="merged", actor_kind="operator",
                         actor="operator", source_branch="agentweave/task/x", target_branch="main",
                         created_at=start + timedelta(minutes=80)))

    # ac-work: two requirements, one accepted, a previous failed run then a passing one.
    t["work"] = make_task(base, "Work view fixture", builder=BUILDER, checker=REVIEWER,
                          requirement_ids=["FR-1", "FR-2"], spec_document=doc,
                          acceptance_criteria=["CRIT-ONE the first criterion text is visible",
                                               "CRIT-TWO the second criterion text is visible"])
    set_status(t["work"], "completed")
    code, ev = d.api("POST", f"{base}/project/spec/evidence",
                     {"identifier": "FR-1", "document": doc, "kind": "manual_observation",
                      "summary": "Seen.", "task_id": t["work"], "locator": "drive"})
    work_evidence = (code, (ev or {}).get("review_state") if isinstance(ev, dict) else str(ev)[:200])
    check_run(pid, t["work"], "failed", [check_result("old-lint-tcsr", False),
                                         check_result("old-unit-tcsr", True)],
              now - timedelta(hours=2))
    check_run(pid, t["work"], "passed", [check_result("new-lint-tcsr", True),
                                         check_result("new-unit-tcsr", True)],
              now - timedelta(minutes=20))

    # ac-a11y: one task in each stage the board tells apart.
    stage_tasks = {}
    for status, stage_hint in (("pending", "not_started"), ("completed", "waiting_for_review"),
                               ("revision_needed", "sent_back"), ("approved", "approved_waiting"),
                               ("rejected", "closed")):
        tid = make_task(base, f"stage {stage_hint}", builder=BUILDER, checker=REVIEWER)
        set_status(tid, status)
        stage_tasks[stage_hint] = tid
    for state, hint, extra in (("checking", "checking", {}),
                               ("landed", "on_main", {"landed_sha": "d" * 40}),
                               ("held", "landing_held", {"reason": "check lint is failing"}),
                               ("not_landed", "did_not_land", {"reason": "uncommitted changes"})):
        tid = make_task(base, f"stage {hint}", builder=BUILDER, checker=REVIEWER)
        set_status(tid, "approved")
        seed(TaskLanding(id=uid("landing"), project_id=pid, task_id=tid, state=state,
                         order_key=float(next(_n)), **extra))
        stage_tasks[hint] = tid
    stage_tasks["waiting_for_answer"] = t["budget"]

    # ac-motion: one card per theme and motion setting, at checking, moved to on main live.
    motion_tasks = {}
    for theme in THEMES:
        for reduced in (False, True):
            tid = make_task(base, f"motion {theme} {'reduced' if reduced else 'allowed'}",
                            builder=BUILDER, checker=REVIEWER)
            set_status(tid, "approved")
            lid = uid("landing")
            seed(TaskLanding(id=lid, project_id=pid, task_id=tid, state="checking",
                             order_key=float(next(_n))))
            motion_tasks[(theme, reduced)] = (tid, lid)

    rows = {r["id"]: r for r in d.api("GET", f"{base}/tasks")[1]["tasks"]}
    print("  seeded stages:", {k: rows.get(v, {}).get("stage") for k, v in stage_tasks.items()})
    print("  work evidence:", work_evidence, " budget stage:", rows.get(t["budget"], {}).get("stage"),
          "waits_on:", rows.get(t["budget"], {}).get("stage_waits_on"))
    print("  checks card: failed_checks field =",
          {k: v for k, v in rows.get(t["checks"], {}).items() if "check" in k})

    axe = axe_source()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in THEMES:
            board_checks(browser, pid, theme, t, stage_tasks, motion_tasks, failed_names,
                         run_ids, question_id, integration_id, axe)
        browser.close()


def open_board(browser, pid, theme, reduced=False):
    context = browser.new_context(viewport=VIEWPORT, reduced_motion="reduce" if reduced else "no-preference")
    page = context.new_page()
    page.add_init_script(
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        "localStorage.setItem('agentweave-prefs', JSON.stringify({mode: %s}));"
        # Finished cards (on main, closed) are hidden by default; the stage and motion checks need them.
        "localStorage.setItem('aw.boardShowFinished.' + %s, 'true');"
        % (json.dumps(d.KEY), json.dumps(d.HUB), json.dumps(pid), json.dumps(theme), json.dumps(pid)))
    page.goto(f"{d.HUB}/?project={pid}", wait_until="domcontentloaded")
    page.get_by_test_id("project-tab-tasks").first.click()
    return context, page


def on_board(page, tid, secs=30):
    return d.poll(lambda: page.get_by_test_id(f"task-open-{tid}").count() >= 1, secs)


def open_task(page, tid):
    page.get_by_test_id(f"task-open-{tid}").first.click()
    return d.poll(lambda: page.get_by_role("dialog").count() >= 1
                  or page.get_by_test_id(f"task-story-{tid}").count() >= 1, 15)


def close_task(page):
    page.keyboard.press("Escape")
    d.poll(lambda: page.get_by_role("dialog").count() == 0, 5)


def open_work(page, tid):
    """The Work view: its switch by test id, else a button named Work in the dialog."""
    switch = page.get_by_test_id(f"task-view-work-{tid}")
    if switch.count() == 0:
        switch = page.get_by_role("dialog").get_by_role("button", name=re.compile(r"^\s*Work\s*$"))
    if switch.count() == 0:
        return False
    switch.first.click()
    return d.poll(lambda: page.get_by_test_id(f"task-serves-{tid}").count() >= 1, 10)


def axe_contrast(page, axe, selector, card_ids=None):
    """axe-core colour-contrast violations inside `selector`, or around the cards `card_ids`."""
    if not page.evaluate("() => typeof window.axe !== 'undefined'"):
        page.add_script_tag(content=axe)
    return page.evaluate(
        """async ([selector, ids]) => {
             const include = selector
               ? [...document.querySelectorAll(selector)]
               : ids.map((id) => document.querySelector(`[data-testid="task-open-${id}"]`)?.parentElement).filter(Boolean)
             if (!include.length) return null
             const r = await axe.run({ include }, { runOnly: { type: 'rule', values: ['color-contrast'] } })
             return r.violations.flatMap((v) => v.nodes.map((n) => n.target.join(' ') + ' :: ' + (n.any[0]?.message || '').slice(0, 120)))
           }""", [selector, card_ids or []])


def distinct_violations(found):
    """One line per failing element kind (its last selector part and contrast), with a count."""
    kinds = {}
    for v in found or []:
        target, _, message = v.partition(" :: ")
        ratio = re.search(r"contrast of ([\d.]+) \(foreground color: (#\w+), background color: (#\w+)", message)
        key = target.split(" > ")[-1].split(":nth")[0] + (" %s %s on %s" % ratio.groups() if ratio else "")
        kinds[key] = kinds.get(key, 0) + 1
    return [f"{k} x{n}" for k, n in kinds.items()]


def board_checks(browser, pid, theme, t, stage_tasks, motion_tasks, failed_names, run_ids,
                 question_id, integration_id, axe):
    tag = f"[{theme}]"
    context, page = open_board(browser, pid, theme)
    board = on_board(page, t["budget"])

    # ── ac-budget (FR-3)
    m = page.evaluate(CARD_LINES_JS, [t["budget"], "Decide the migration rollback"]) if board else None
    reviewer = page.evaluate(NAME_WHOLE_JS, [t["budget"], REVIEWER]) if board else None
    w = page.evaluate(WAITS_JS, t["budget"]) if board else None
    waits_ok = bool(w) and w["waits"]["shown"] and w["waits"]["whole"]
    # Time at stage gives way first: it may only show while waits-on is shown whole.
    age_ok = bool(w) and (waits_ok or not w["ageShown"])
    ok = (bool(m) and m["lines"] <= 2 and waits_ok and age_ok
          and bool(reviewer) and reviewer["whole"])
    line(f"ac-budget{tag}", board and bool(m) and m["titleFound"], not ok,
         f"lines below title={m and m['lines']} (max 2) at card width {m and round(m['width'])}px; "
         f"waits-on={(w or {}).get('waitsText')!r} shown={w and w['waits']['shown']} "
         f"whole={w and w['waits']['whole']} {(w or {}).get('waits', {}).get('why', '')}; "
         f"time at stage={(w or {}).get('ageText')!r} shown={w and w['ageShown']} whole={w and w['ageWhole']} "
         f"(gives way first: {age_ok}); "
         f"reviewer {REVIEWER!r} whole={reviewer and reviewer['whole']} "
         f"{(reviewer or {}).get('why', '')}; texts={m and m['texts'][:8]}")

    # ── ac-checks (FR-5)
    reached = on_board(page, t["checks"], 10)
    marker = page.get_by_test_id(f"task-failed-checks-{t['checks']}")
    marker_text = marker.first.inner_text().strip() if marker.count() else ""
    named = []
    work_open = False
    if reached and open_task(page, t["checks"]):
        work_open = open_work(page, t["checks"])
        if work_open:
            view = page.get_by_test_id(f"task-serves-{t['checks']}").locator("xpath=..")
            body = view.inner_text()
            named = [n for n in failed_names if n in body]
        close_task(page)
    ok = re.fullmatch(r"\D*2\D*", marker_text or "x") is not None and len(named) == 2
    line(f"ac-checks{tag}", reached, not ok,
         f"marker={marker_text!r} (want 2); Work view open={work_open}, failed checks named={named}")

    # ── ac-story (FR-6)
    reached = on_board(page, t["story"], 10) and open_task(page, t["story"])
    story_violations = None
    heads, folds, fold_text, links_missing, unfolded = None, 0, "", [], {}
    if reached:
        d.poll(lambda: page.get_by_test_id(f"task-story-events-{t['story']}").count() >= 1, 15)
        heads = page.evaluate(STORY_HEADS_JS, t["story"]) or []
        fold_items = [h for h in heads if h["id"].startswith("story-fold-")]
        folds = len(fold_items)
        fold_text = fold_items[0]["label"] if fold_items else ""
        unfolded = {"question": any(h["id"] == f"story-event-{question_id}" for h in heads),
                    "landing": any(h["id"] == f"story-event-{integration_id}" for h in heads)}
        long_labels = [h["label"] for h in heads if len(h["label"].split()) > 6]
        opener = page.locator("[data-testid^='story-fold-open-']")
        if opener.count():
            opener.first.click()
            page.wait_for_timeout(400)
        for rid in run_ids:
            for kind in ("trace", "conversation"):
                if page.get_by_test_id(f"story-run-{kind}-{rid}").count() == 0:
                    links_missing.append(f"{kind}:{rid}")
        # FR-9 covers story text too: axe colour-contrast on the open Story, fold opened.
        story_violations = axe_contrast(page, axe, f'[data-testid="task-story-{t["story"]}"]')
        close_task(page)
        ok = folds == 1 and "6" in fold_text and all(unfolded.values()) and not long_labels \
            and not links_missing
        line(f"ac-story{tag}", True, not ok,
             f"folded entries={folds} (want 1, of 6) label={fold_text!r}; unfolded={unfolded}; "
             f"labels over six words={long_labels[:4]}; links missing after opening={links_missing[:4]}")
    else:
        line(f"ac-story{tag}", False, True, "the story task's dialog did not open")

    # ── ac-work (FR-10)
    reached = on_board(page, t["work"], 10) and open_task(page, t["work"])
    if reached:
        work_open = open_work(page, t["work"])
        detail, ok = "the opened task offers no Work view", False
        if work_open:
            serves = page.get_by_test_id(f"task-serves-{t['work']}")
            rows = serves.locator("li")
            states = {}
            for i in range(rows.count()):
                txt = rows.nth(i).inner_text()
                key = "FR-1" if "FR-1" in txt else "FR-2" if "FR-2" in txt else f"row{i}"
                states[key] = txt.replace("\n", " ")[:80]
            container = serves.locator("xpath=..").inner_text()
            criteria = all(c in container for c in ("CRIT-ONE", "CRIT-TWO"))
            latest = all(c in container for c in ("new-lint-tcsr", "new-unit-tcsr"))
            earlier = page.get_by_role("button", name=re.compile(r"earlier runs", re.I))
            revealed = False
            if earlier.count():
                earlier.first.click()
                revealed = d.poll(lambda: "old-lint-tcsr" in serves.locator("xpath=..").inner_text(), 5)
            accepted = re.search(r"accepted", states.get("FR-1", ""), re.I) is not None
            none = re.search(r"no evidence", states.get("FR-2", ""), re.I) is not None
            ok = accepted and none and criteria and latest and revealed
            detail = (f"FR-1={states.get('FR-1')!r} accepted={accepted}; FR-2={states.get('FR-2')!r} "
                      f"none={none}; criteria={criteria}; latest checks={latest}; "
                      f"Earlier runs control={earlier.count()} reveals old run={revealed}")
        close_task(page)
        line(f"ac-work{tag}", True, not ok, detail)
    else:
        line(f"ac-work{tag}", False, True, "the work task's dialog did not open")

    # ── ac-a11y (FR-9): axe colour-contrast on the cards, then the stages without colour.
    reached = all(on_board(page, tid, 10) for tid in stage_tasks.values())
    violations, sigs = None, {}
    if reached:
        violations = axe_contrast(page, axe, None, list(stage_tasks.values()))
        page.add_style_tag(content="html { filter: grayscale(1) !important; }")
        page.wait_for_timeout(300)
        shot = d.TMP / f"board-greyscale-{theme}.png"
        page.screenshot(path=str(shot), full_page=True)
        for stage, tid in stage_tasks.items():
            sigs[stage] = page.evaluate(STAGE_SIGNATURE_JS, tid)
    glyphed = {k: bool(v and v["glyph"]) for k, v in sigs.items()}
    distinct = len({(v or {}).get("glyph", "") + "|" + (v or {}).get("word", "") for v in sigs.values()})
    ok = (violations == [] and story_violations == [] and all(glyphed.values())
          and distinct == len(stage_tasks))
    missing = [k for k, v in stage_tasks.items() if page.get_by_test_id(f"task-open-{v}").count() == 0] if not reached else []
    line(f"ac-a11y{tag}", reached, not ok,
         (f"stage cards not on the board: {missing}; " if missing else "") + f"axe color-contrast violations={len(violations) if violations is not None else None} "
         f"{(violations or [])[:3]}; open Story axe color-contrast violations="
         f"{len(story_violations) if story_violations is not None else None} {distinct_violations(story_violations)}; greyscale: {distinct}/{len(stage_tasks)} stages distinct by "
         f"glyph and word, without a glyph={[k for k, v in glyphed.items() if not v]}; "
         f"screenshot {d.TMP / f'board-greyscale-{theme}.png'}")
    filters_click_through(page, t, stage_tasks, tag)
    context.close()

    # ── ac-motion (FR-7): checking -> on main, live, with motion allowed and with reduced motion.
    outcome = {}
    for reduced in (False, True):
        tid, lid = motion_tasks[(theme, reduced)]
        ctx, pg = open_board(browser, pid, theme, reduced)
        here = on_board(pg, tid)
        if not here:
            outcome[reduced] = None
            ctx.close()
            continue
        pg.wait_for_timeout(800)  # let mount animations finish before arming
        before = pg.get_by_test_id(f"task-stage-{tid}")
        before = before.first.inner_text()[:30] if before.count() else ""
        pg.evaluate(MOTION_ARM_JS, tid)
        sql("update task_landings set state='landed', landed_sha=:sha where id=:id", sha="e" * 40, id=lid)
        d.api("PATCH", f"/projects/{pid}/tasks/{tid}", {"notes": f"landed {time.time()}"})

        def stage_now():
            loc = pg.get_by_test_id(f"task-stage-{tid}")
            return loc.first.inner_text() if loc.count() else ""
        changed = d.poll(lambda: "on main" in stage_now().lower(), 10)
        pg.wait_for_timeout(700)
        rec = pg.evaluate("window.__tcsr")
        # The app's reduced-motion reset (index.css) shortens every animation to 0.01 ms rather than
        # removing it; one of a millisecond or less shows nothing, so it is not counted as playing.
        playing = [a for a in rec["anims"] if a["total"] is None or a["total"] > 1]
        stage = [a for a in playing if a["onStage"]]
        finite = [a["total"] for a in stage if a["total"] not in (None, float("inf"))]
        outcome[reduced] = {"changed": changed, "before": before, "stage": stage_now()[:30],
                            "stage_anims": sorted({a["name"] for a in stage})[:4],
                            "longest_stage_ms": max(finite or [0]),
                            "endless_stage": [a["name"] for a in stage if a["total"] in (None, float("inf"))],
                            "other_playing": sorted({f"{a['name']}={a['total']}ms" for a in playing if not a["onStage"]})[:4],
                            "playing": len(playing)}
        ctx.close()
    allowed, still = outcome.get(False), outcome.get(True)
    reached = allowed is not None and still is not None
    # The change is the stage, so the stage line or the thread must animate it; a colour transition
    # on the card's frame alone is not the stage animating (it is reported under other_playing).
    ok = reached and allowed["changed"] and bool(allowed["stage_anims"]) \
        and allowed["longest_stage_ms"] <= 300 and not allowed["endless_stage"] \
        and still["changed"] and still["playing"] == 0
    line(f"ac-motion{tag}", reached, not ok,
         f"motion allowed: {allowed}; reduced motion: {still} "
         "(want the stage line or thread animated, ending within 300 ms; nothing playing under "
         "reduced motion; the stage changed in both)")


def filters_click_through(page, t, stage_tasks, tag):
    """The operator's constraint for this change: click the agent chips and the spec picker once
    with the new card in place. Printed as a note, not a check: no criterion of the document names it."""
    visible = lambda tid: page.get_by_test_id(f"task-open-{tid}").count() >= 1  # noqa: E731
    others = [tid for tid in stage_tasks.values() if tid != t["budget"]]
    chips = page.get_by_role("group", name="Filter by agent")
    chips.get_by_role("button", name=re.compile(BUILDER)).first.click()
    only_builder = d.poll(lambda: visible(t["budget"]) and not any(visible(x) for x in others), 5)
    chips.get_by_role("button", name="Everyone").first.click()
    everyone = d.poll(lambda: all(visible(x) for x in stage_tasks.values()), 5)
    page.get_by_test_id("board-scope").first.click()
    options = page.locator("[data-testid^='board-scope-option-']")
    keys = [options.nth(i).get_attribute("data-testid") for i in range(options.count())]
    spec_key = next((k for k in keys if "spdoc-" in k), None)
    only_spec = back = None
    if spec_key:
        page.get_by_test_id(spec_key).first.click()
        only_spec = d.poll(lambda: visible(t["work"]) and not any(visible(x) for x in others), 5)
        page.get_by_test_id("board-scope").first.click()
        page.get_by_test_id(keys[0]).first.click()
        back = d.poll(lambda: all(visible(x) for x in stage_tasks.values()), 5)
    else:
        page.keyboard.press("Escape")
    print(f"note filters{tag}: builder chip shows only its task={only_builder}; Everyone restores "
          f"all={everyone}; scope options={keys}; spec scope shows only its task={only_spec}; "
          f"first option restores all={back}", flush=True)


d.drive = drive

if __name__ == "__main__":
    try:
        d.main()
    except SystemExit:
        pass  # d.main() exits on its own setup results; this drive's verdict is its check lines
    finally:
        print("\n".join(LINES))
    failing = [x for x in LINES if "failed_at_assertion=yes" in x]
    print(f"\n{len(LINES) - len(failing)} of {len(LINES)} checks pass")
    sys.exit(1 if failing or not LINES else 0)
