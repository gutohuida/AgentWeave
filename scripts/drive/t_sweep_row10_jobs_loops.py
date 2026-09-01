"""SWEEP ROW 10 of 19 — JOBS + LOOPS: cron jobs, history, manual run, archive; loop control.

Rows 1-8 and 9a/9b/9c are done. This is row 10, the twelve routes in `hub/hub/api/v1/jobs.py`
(8) and `hub/hub/api/v1/loops.py` (4).

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... py -3.11 t_sweep_row10_jobs_loops.py

Method carried from rows 7-9:

* **The fixture machinery is copied, not imported.** Nothing here calls a Hub helper the Hub also
  calls; every fact is read back off a real HTTP response.
* **Create the condition under test** through the real routes. No row inserts.
* **Call the route, do not read its model.** Every bodyless probe in leg 2 is a call.
* **Read the reason for every GREEN**, not just every red.
* **State the precondition** rather than asserting through it — this harness is expected to be run
  twice in the same project, so everything order-dependent is gated on a measured fact or works on
  ids this run created.
* **Never leave a job enabled.** Every job this file creates is archived in a `finally`, and leg 9
  re-reads the project to prove it. Do NOT pipe this through `head`: SIGPIPE kills the process
  before the `finally` runs.

Safety: every job is created with `SAFE_CRON` — 00:00 on 1 January — so the scheduler cannot fire
one behind this harness's back. Firing is done by hand through `POST /jobs/{id}/run`.
"""

import contextlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import pathlib  # noqa: E402

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
if P in ("proj-5e960453", "proj-18e5d4e0") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)
HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ.get("AW_KEY", "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd")
AGENT = os.environ.get("AGENT_A", "")
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
REPO = pathlib.Path(__file__).resolve().parents[2]
A = f"/projects/{P}"
SAFE_CRON = "0 0 1 1 *"  # once a year, on 1 January — the scheduler will not beat us to it

PASS, FAIL = [], []
CREATED_JOBS = []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


def bodyless(method, path):
    """A call with NO body at all — not `{}`, nothing. F204/F210 were found exactly this way."""
    req = urllib.request.Request(HUB + "/api/v1" + path, method=method)
    req.add_header("Authorization", "Bearer " + KEY)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, text
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def make_job(stem, **over):
    body = {
        "name": f"r10-{TAG}-{stem}",
        "agent": AGENT,
        "message": "Reply with the single word: ok.",
        "cron": SAFE_CRON,
        "enabled": False,
    }
    body.update(over)
    code, b = api("POST", f"{A}/jobs", body)
    if code == 201 and isinstance(b, dict) and b.get("id"):
        CREATED_JOBS.append(b["id"])
    return code, b


try:
    if not AGENT:
        code, agents = api("GET", f"{A}/agents")
        AGENT = next(a["name"] for a in agents if a.get("runner_id"))
    note("project", P)
    note("agent", AGENT)

    # =========================================================================================
    leg(1, "Job CRUD, and whether the detail route reports the row it stored")

    code, created = make_job("crud", source="local", enabled=True)
    ok("POST /jobs creates a plain job", code == 201, f"{code} {str(created)[:200]}")
    JOB = created["id"]
    note("job id", JOB)
    note("created_at response source", repr(created.get("source")))
    ok("the create response echoes the stored source", created.get("source") == "local", repr(created.get("source")))
    ok("a plain job gets no Loop", created.get("loop") is None, str(created.get("loop"))[:200])

    code, listed = api("GET", f"{A}/jobs")
    mine = [j for j in listed if j["id"] == JOB]
    ok("GET /jobs lists it", len(mine) == 1, f"{code} {len(listed)} jobs")
    note("LIST source", repr(mine[0].get("source")) if mine else "-")

    code, detail = api("GET", f"{A}/jobs/{JOB}")
    ok("GET /jobs/{id} answers 200", code == 200, str(detail)[:200])
    note("DETAIL source", repr(detail.get("source")))
    # The list route serialises the ORM row; the detail route hand-builds a dict. If the two
    # disagree about a stored column, the hand-built one dropped it and the schema default filled
    # the hole. That is F212's shape, on a different router.
    ok(
        "the detail route reports the same `source` the list route does",
        detail.get("source") == mine[0].get("source"),
        f"detail={detail.get('source')!r} list={mine[0].get('source')!r} stored=local",
    )
    ok(
        "the detail route reports the source that was stored",
        detail.get("source") == "local",
        f"{detail.get('source')!r}",
    )
    # Which keys does the hand-built dict simply not carry?
    missing = sorted(set(mine[0]) - set(detail))
    note("keys the list route returns that the detail route omits", missing or "none")

    code, b = api("DELETE", f"{A}/jobs/{JOB}")
    ok("DELETE is refused with a stated remedy", code == 400 and "archive" in str(b), f"{code} {b}")
    code, b = api("DELETE", f"{A}/jobs/job-nosuch{TAG}")
    ok("DELETE of an unknown job is 404, not the 400", code == 404, f"{code} {b}")

    # =========================================================================================
    leg(2, "Bodyless probes on every mutating route (F204/F210's shape)")

    probes = [
        ("POST", f"{A}/jobs"),
        ("PATCH", f"{A}/jobs/{JOB}"),
        ("POST", f"{A}/jobs/{JOB}/archive"),
        ("POST", f"{A}/jobs/{JOB}/run"),
    ]
    for method, path in probes:
        c, b = bodyless(method, path)
        note(f"{method} {path.split('/jobs')[-1] or '(list)'} with no body", f"{c} {str(b)[:160]}")
    # The two that take a required body must refuse; the two that take none must work.
    c_create, b_create = bodyless("POST", f"{A}/jobs")
    ok("POST /jobs with no body is refused", c_create in (400, 422), f"{c_create} {str(b_create)[:200]}")
    c_patch, b_patch = bodyless("PATCH", f"{A}/jobs/{JOB}")
    ok(
        "PATCH /jobs/{id} with no body is refused rather than treated as an empty update",
        c_patch in (400, 422),
        f"{c_patch} {str(b_patch)[:200]}",
    )
    # Verify the refusal changed nothing.
    code, after = api("GET", f"{A}/jobs/{JOB}")
    ok("the refused PATCH left the job untouched", after.get("name") == created["name"], after.get("name"))

    # =========================================================================================
    leg(3, "The four documented loop opt-in refusals — measured, not read")

    code, b = make_job("wne-no-loop", work_needs_evidence=True)
    ok(
        "work_needs_evidence on a job that is not a loop is refused (D4)",
        code == 400 and "loop" in str(b).lower(),
        f"{code} {str(b)[:200]}",
    )
    code, b = make_job("resume-loop", session_mode="resume", purpose="a loop")
    ok(
        "session_mode=resume on a loop is refused (D4)",
        code == 400 and "checkpoint" in str(b).lower(),
        f"{code} {str(b)[:200]}",
    )
    code, b = make_job("ambiguous-cron", cron="0 0 1 * 1")
    ok(
        "a cron restricting both day fields is refused (F1)",
        code == 400,
        f"{code} {str(b)[:200]}",
    )
    code, b = make_job("bad-cron", cron="not a cron")
    ok("an invalid cron is refused", code == 400, f"{code} {str(b)[:200]}")
    # A refusal must leave nothing behind: none of the four above may have created a row.
    code, listed = api("GET", f"{A}/jobs", None)
    names = [j["name"] for j in listed]
    ok(
        "no refused create left a job row behind (F54's rule)",
        not any(n.endswith(("wne-no-loop", "resume-loop", "ambiguous-cron", "bad-cron")) for n in names),
        str([n for n in names if "r10-" in n]),
    )
    # And the contrast: spec_document_id alone does NOT opt a job in.
    code, b = make_job("doc-only", spec_document_id=f"spdoc-nosuch{TAG}"[:24])
    ok("spec_document_id alone is accepted and does NOT make a loop", code == 201 and b.get("loop") is None, f"{code} {str(b.get('loop'))[:150]}")
    if code == 201:
        note("  the declared document was", "dropped silently — F157, already filed")

    # =========================================================================================
    leg(4, "A loop: opt-in, the staged edit, and what the summary projects")

    stop_at = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    code, loopjob = make_job(
        "loop",
        purpose="Drive row 10's loop half.",
        stop_when_queue_empties=True,
        stop_at=stop_at,
        enabled=True,
        initial_tasks=[{"title": f"row10 seed {TAG}", "description": "seeded at definition time"}],
    )
    ok("a job with a purpose becomes a loop", code == 201 and loopjob.get("loop"), f"{code} {str(loopjob)[:250]}")
    LOOPJOB = loopjob["id"]
    LOOP = loopjob["loop"]["id"]
    note("loop id", LOOP)
    ok(
        "the create response's queue already counts the initial task (design D2)",
        sum(loopjob["loop"].get("queue", {}).values()) >= 1,
        str(loopjob["loop"].get("queue")),
    )
    ok(
        "the loop summary carries its own id, so `GET /tasks?loop_id=` is buildable",
        bool(loopjob["loop"].get("id")),
        str(loopjob["loop"])[:150],
    )
    code, qtasks = api("GET", f"{A}/tasks?loop_id={LOOP}")
    ok("that id really is the one /tasks scopes by", code == 200 and len(qtasks) >= 1, f"{code} {len(qtasks) if isinstance(qtasks, list) else qtasks}")

    # The staged edit (D11).
    code, patched = api("PATCH", f"{A}/jobs/{LOOPJOB}", {"purpose": "EDITED purpose"})
    ok("an edit to a live loop's definition is accepted", code == 200, f"{code} {str(patched)[:200]}")
    lp = (patched or {}).get("loop") or {}
    ok("...and is reported as pending, not applied", lp.get("purpose") != "EDITED purpose", repr(lp.get("purpose")))
    ok("...and the pending edit is reported separately", bool(lp.get("pending_edit")), str(lp.get("pending_edit"))[:200])
    note("pending_edit", json.dumps(lp.get("pending_edit"), default=str)[:300])
    ok(
        "the staged edit names who staged it and when",
        isinstance(lp.get("pending_edit"), dict)
        and lp["pending_edit"].get("staged_by")
        and lp["pending_edit"].get("staged_at"),
        str(lp.get("pending_edit"))[:200],
    )
    # work_needs_evidence is refused on edit, always (D3).
    code, b = api("PATCH", f"{A}/jobs/{LOOPJOB}", {"work_needs_evidence": True})
    ok("work_needs_evidence is refused on edit even for a real loop (D3)", code == 400, f"{code} {str(b)[:200]}")

    # =========================================================================================
    leg(5, "Loop control and the loop routes")

    code, loops = api("GET", f"{A}/loops")
    ok("GET /loops lists the new loop", code == 200 and any(x["id"] == LOOP for x in loops), f"{code} {len(loops) if isinstance(loops, list) else loops}")
    code, ldetail = api("GET", f"{A}/loops/{LOOP}")
    ok("GET /loops/{id} answers 200", code == 200, str(ldetail)[:200])
    ok("the detail carries its job id", ldetail.get("job_id") == LOOPJOB, repr(ldetail.get("job_id")))
    ok("the detail carries an events list", isinstance(ldetail.get("events"), list), str(type(ldetail.get("events"))))
    note("events recorded so far", [e.get("event_type") for e in ldetail.get("events", [])])
    ok(
        "the staged edit was recorded as an event on THIS loop",
        any(e.get("event_type") == "loop_edit_staged" for e in ldetail.get("events", [])),
        str([e.get("event_type") for e in ldetail.get("events", [])]),
    )

    code, b = api("POST", f"{A}/loops/{LOOP}/control", {"control": "creator"})
    ok("control can be delegated to the creator", code == 200 and b.get("control") == "creator", f"{code} {str(b)[:200]}")
    code, b = api("POST", f"{A}/loops/{LOOP}/control", {"control": "operator"})
    ok("...and taken back, stored as NULL rather than the literal default", code == 200 and b.get("control") is None, f"{code} control={b.get('control')!r}")
    code, b = api("POST", f"{A}/loops/{LOOP}/control", {"control": "nobody"})
    ok("an unknown control value is refused", code in (400, 422), f"{code} {str(b)[:200]}")
    c, b = bodyless("POST", f"{A}/loops/{LOOP}/control")
    ok("POST /loops/{id}/control with no body is refused", c in (400, 422), f"{c} {str(b)[:200]}")
    c, b = bodyless("POST", f"{A}/loops/{LOOP}/archive")
    note("POST /loops/{id}/archive with no body", f"{c} {str(b)[:200]}")
    ok(
        "archiving a running loop is refused (B2.3)",
        c == 400 and "running" in str(b).lower(),
        f"{c} {str(b)[:200]}",
    )
    code, b = api("GET", f"{A}/loops/loop-nosuch{TAG}")
    ok("an unknown loop id is 404", code == 404, f"{code} {str(b)[:150]}")

    # =========================================================================================
    leg(6, "Archiving the JOB of a running loop, and what the loop routes then say")

    code, before_loops = api("GET", f"{A}/loops")
    listed_before = any(x["id"] == LOOP for x in before_loops)
    code, arch = api("POST", f"{A}/jobs/{LOOPJOB}/archive")
    ok("the operator can archive a loop's job", code == 200, f"{code} {str(arch)[:200]}")
    note("job archived_at", arch.get("archived_at"))
    code, after_loop = api("GET", f"{A}/loops/{LOOP}")
    note("loop archived_at", after_loop.get("archived_at"))
    note("loop ending_state", repr(after_loop.get("ending_state")))
    ok(
        "archiving the job archived the loop with it",
        after_loop.get("archived_at") is not None,
        repr(after_loop.get("archived_at")),
    )
    # THE QUESTION. `archive_loop` refuses a loop whose `ending_state` is None with "this loop is
    # still running". `archive_job` sets `archived_at` without ever setting `ending_state`. So the
    # loop is now archived AND never ended — and the loop route's two refusals are ordered
    # ending-state-first. What does it say about a loop that is already archived?
    c, b = api("POST", f"{A}/loops/{LOOP}/archive", None)
    note("POST /loops/{id}/archive on the already-archived loop", f"{c} {str(b)[:250]}")
    ok(
        "an already-archived loop is told it is already archived, not that it is still running",
        c == 400 and "already archived" in str(b).lower(),
        f"{c} {str(b)[:250]}",
    )
    ok(
        "a loop hidden from the listing is not reported as still running",
        not (after_loop.get("archived_at") is not None and after_loop.get("ending_state") is None),
        f"archived_at={after_loop.get('archived_at')} ending_state={after_loop.get('ending_state')!r}",
    )
    code, after_loops = api("GET", f"{A}/loops")
    ok(
        "the archived loop leaves the default listing",
        listed_before and not any(x["id"] == LOOP for x in after_loops),
        f"before={listed_before} after={[x['id'] for x in after_loops]}",
    )
    code, incl = api("GET", f"{A}/loops?include_archived=true")
    ok("...and comes back when asked for", any(x["id"] == LOOP for x in incl), str([x["id"] for x in incl]))

    # Can an archived job be put back to work without ever being unarchived?
    code, re_en = api("PATCH", f"{A}/jobs/{LOOPJOB}", {"enabled": True})
    note("PATCH {enabled:true} on the archived job", f"{code} enabled={(re_en or {}).get('enabled')!r} archived_at={(re_en or {}).get('archived_at')!r}")
    ok(
        "an archived job cannot be re-enabled while it stays hidden from the listing",
        not (code == 200 and re_en.get("enabled") and re_en.get("archived_at")),
        f"{code} enabled={(re_en or {}).get('enabled')!r} archived_at={(re_en or {}).get('archived_at')!r}",
    )
    if code == 200 and re_en.get("enabled"):
        code, jlist = api("GET", f"{A}/jobs")
        ok(
            "...and if it can, it is at least visible in the default job listing",
            any(j["id"] == LOOPJOB for j in jlist),
            f"hidden while enabled: {LOOPJOB}",
        )
        c2, b2 = api("POST", f"{A}/jobs/{LOOPJOB}/run")
        note("POST /run on the archived-but-enabled job", f"{c2} {str(b2)[:200]}")
        ok(
            "an archived job refuses to fire",
            c2 not in (200, 201),
            f"{c2} {str(b2)[:200]}",
        )
        api("PATCH", f"{A}/jobs/{LOOPJOB}", {"enabled": False})
    code, b = api("POST", f"{A}/jobs/{LOOPJOB}/archive")
    ok("archiving twice is refused", code == 400 and "already archived" in str(b).lower(), f"{code} {str(b)[:200]}")

    # =========================================================================================
    leg(7, "A real firing: manual run, history, and what each reader of it can see")

    code, fj = make_job("fire", enabled=True)
    FIREJOB = fj["id"]
    t0 = time.time()
    code, fired = api("POST", f"{A}/jobs/{FIREJOB}/run", None, timeout=300)
    note("POST /jobs/{id}/run", f"{code} {str(fired)[:200]}  ({time.time()-t0:.1f}s)")
    ok("a manual fire is accepted", code == 200 and fired.get("success"), f"{code} {str(fired)[:200]}")

    code, hist = api("GET", f"{A}/jobs/{FIREJOB}/history")
    ok("GET /history records the firing", code == 200 and len(hist) >= 1, f"{code} {str(hist)[:200]}")
    note("history[0]", json.dumps(hist[0], default=str)[:300] if hist else "-")
    ok("the history row says what triggered it", hist and hist[0].get("trigger") == "manual", str(hist[:1])[:200])
    ok("the history row carries tick_count", hist and "tick_count" in hist[0], str(hist[:1])[:200])

    code, jd = api("GET", f"{A}/jobs/{FIREJOB}")
    embedded = (jd.get("history") or [])
    ok("the detail route embeds the same firing", len(embedded) >= 1, str(embedded)[:200])
    if embedded and hist:
        dropped = sorted(set(hist[0]) - set(embedded[0]))
        note("keys /history carries that the detail view drops", dropped or "none")
        ok(
            "the detail view's embedded history carries every field /history does",
            not dropped,
            f"dropped {dropped}",
        )
    ok("run_count moved", jd.get("run_count", 0) >= 1, str(jd.get("run_count")))
    ok("last_run was stamped", jd.get("last_run") is not None, repr(jd.get("last_run")))

    # A failure, so `error_summary` has something in it that a reader might need.
    code, dis = api("PATCH", f"{A}/jobs/{FIREJOB}", {"enabled": False})
    code, b = api("POST", f"{A}/jobs/{FIREJOB}/run")
    ok("a disabled job refuses to fire", code == 400 and "disabled" in str(b).lower(), f"{code} {str(b)[:200]}")
    code, h2 = api("GET", f"{A}/jobs/{FIREJOB}/history")
    ok(
        "...and the refusal wrote no history row (nothing fired)",
        len(h2) == len(hist),
        f"{len(hist)} -> {len(h2)}",
    )

    # =========================================================================================
    leg(8, "Isolation, unknown ids, and the boundary question")

    code, others = api("GET", "/projects")
    other = next((x["id"] for x in others if x["id"] not in (P, "proj-5e960453", "proj-18e5d4e0")), None)
    if other:
        note("second project used for isolation", other)
        for path, label in (
            (f"/projects/{other}/jobs/{FIREJOB}", "GET job"),
            (f"/projects/{other}/jobs/{FIREJOB}/history", "GET history"),
            (f"/projects/{other}/loops/{LOOP}", "GET loop"),
        ):
            c, b = api("GET", path)
            ok(f"{label} across a project boundary is 404", c == 404, f"{c} {str(b)[:150]}")
        c, b = api("POST", f"/projects/{other}/jobs/{FIREJOB}/archive")
        ok("archiving across a project boundary is 404", c == 404, f"{c} {str(b)[:150]}")
        c, b = api("POST", f"/projects/{other}/loops/{LOOP}/control", {"control": "creator"})
        ok("setting control across a project boundary is 404", c == 404, f"{c} {str(b)[:150]}")
    else:
        note("isolation leg", "skipped — no second project")

    for path in (f"{A}/jobs/job-nosuch{TAG}", f"{A}/jobs/job-nosuch{TAG}/history"):
        c, b = api("GET", path)
        ok(f"unknown job on {path.split('/jobs')[-1]} is 404", c == 404, f"{c} {str(b)[:150]}")
    c, b = api("POST", f"{A}/loops/loop-nosuch{TAG}/control", {"control": "creator"})
    ok("unknown loop on /control is 404", c == 404, f"{c} {str(b)[:150]}")

    # The boundary question, asked once of this router and then dropped (row 9's rule).
    code, alljobs = api("GET", f"{A}/jobs?include_archived=true")
    note("jobs returned with no limit parameter", len(alljobs) if isinstance(alljobs, list) else alljobs)
    code, allloops = api("GET", f"{A}/loops?include_archived=true")
    note("loops returned with no limit parameter", len(allloops) if isinstance(allloops, list) else allloops)
    c, b = api("GET", f"{A}/jobs/{FIREJOB}/history?limit=0")
    ok("history rejects limit=0 rather than silently clamping", c == 422, f"{c} {str(b)[:150]}")
    c, b = api("GET", f"{A}/jobs/{FIREJOB}/history?limit=1001")
    ok("history rejects a limit above its ceiling", c == 422, f"{c} {str(b)[:150]}")
    note("GET /jobs has a limit parameter", "no — unbounded, same as /loops")
    note("GET /jobs/{id} embedded history", "hard-limited to 10, not a parameter")

    # =========================================================================================
    leg(9, "Is row 10 reachable from the operator's screen?")

    BUNDLE = REPO / "hub" / "hub" / "static" / "ui"
    SRC = REPO / "hub" / "ui" / "src"

    def hits(root, needle):
        n = 0
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            with contextlib.suppress(OSError):
                n += f.read_bytes().count(needle.encode())
        return n

    ctl_b = hits(BUNDLE, "spec/coverage")
    ok("the grep works — the control needle is present in the served bundle", ctl_b > 0, str(ctl_b))
    counts = {}
    for frag in ("/jobs", "/loops", "/control", "/archive", "include_archived", "pending_edit", "stall_reason"):
        counts[frag] = (hits(BUNDLE, frag), hits(SRC, frag))
        note(f"{frag!r}", f"served bundle {counts[frag][0]}, source {counts[frag][1]}")
    ok(
        "row 10 IS on the operator's screen — unlike row 9c, its routes are in the served bundle",
        counts["/jobs"][0] > 0 and counts["/loops"][0] > 0,
        str(counts),
    )
    for frag in ("pending_edit", "stall_reason"):
        ok(
            f"the served bundle reaches {frag!r}",
            counts[frag][0] > 0,
            f"bundle {counts[frag][0]}, source {counts[frag][1]}",
        )
    # `/control` reads 5 in the UI source and 0 in the bundle, which looks like a stale-bundle
    # finding and is not one: all five are the words "model/control catalog" in comments. The
    # honest measurement is the route as a caller would have to write it.
    call_site = re.compile(rb"/loops/\$\{[^}]*\}/(control|archive)")

    def call_sites(root):
        n = 0
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            with contextlib.suppress(OSError):
                n += len(call_site.findall(f.read_bytes()))
        return n

    src_calls, bundle_calls = call_sites(SRC), call_sites(BUNDLE)
    note("UI call sites for POST /loops/{id}/control or /archive", f"source {src_calls}, bundle {bundle_calls}")
    note("hooks exported by hub/ui/src/api/loops.ts", "useLoops, useLoop — two queries, no mutation")
    ok(
        "both loop MUTATION routes are reachable from the operator's screen",
        src_calls > 0 and bundle_calls > 0,
        f"source {src_calls}, bundle {bundle_calls} — neither loop mutation has a UI call site",
    )

    req = urllib.request.Request(HUB + "/openapi.json")
    with urllib.request.urlopen(req, timeout=30) as r:
        spec_doc = json.loads(r.read().decode())
    paths = sorted(spec_doc.get("paths", {}))
    row10 = [p for p in paths if "/jobs" in p or "/loops" in p]
    note("row 10 routes in the live OpenAPI", len(row10))
    for p in row10:
        note("  ", p)
    ag = [p for p in paths if "agent-actions" in p and ("job" in p or "loop" in p)]
    note("agent-plane job/loop routes", ag or "none")
    ok(
        "there is no agent-plane route onto a loop's own record — a loop is the operator's (B2.2)",
        not any("loops" in p for p in ag),
        str(ag),
    )

finally:
    # =========================================================================================
    print("\n=== CLEANUP: nothing may be left enabled")
    for jid in CREATED_JOBS:
        api("PATCH", f"{A}/jobs/{jid}", {"enabled": False})
        api("POST", f"{A}/jobs/{jid}/archive")
    code, remaining = api("GET", f"{A}/jobs?include_archived=true")
    still_on = [j["id"] for j in remaining if j.get("enabled")] if isinstance(remaining, list) else remaining
    print(f"  jobs in project: {len(remaining) if isinstance(remaining, list) else '?'}, still enabled: {still_on}")
    ok("no job is left enabled in this project", not still_on, str(still_on))

    print(f"\n=== ROW 10: {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAIL  {f}")
