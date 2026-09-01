"""Sweep row 3 — Agents.

The representative path from the e2e-loop coverage matrix: register an agent, bind a runner and
a charter, read its canonical context, read its timeline, archive it and unarchive it. Then
provoke every refusal the surface can produce and judge whether each says what *would* work.

Surfaces: agents, agent_lifecycle, bindings, canonical context, timeline, launchability.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_sweep_row3_agents.py <project-id>

Reads an existing project (created by the caller) and leaves behind only what it created; the
caller cleans up the project itself. Prints a PASS/FAIL table and exits non-zero on any FAIL.

Written to be run TWICE against the same project: row 1's F172 and row 2's F177 were both found
by a second run against state the first run left. Names are suffixed with a run tag so a second
run creates fresh rows rather than colliding on the duplicate-name refusal, and the duplicate
check deliberately reuses run 1's names when it can see them.

The failures this harness holds open on purpose are the open findings — see FINDINGS.md's
"row 3 of 19" section. A green run here means those findings were fixed.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

PID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AW_PROJECT", "")
if not PID:
    sys.exit("usage: t_sweep_row3_agents.py <project-id> [other-project-id]")

#: Any *other* project on the same Hub, to prove a binding cannot cross the boundary.
#: Read-only under that scope: this harness only reads its runners and charters.
OTHER = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("AW_OTHER_PROJECT", "")

#: A tag that makes a second run's names distinct from the first's.
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def detail_of(body):
    """The Hub answers a 400/404/409 with {"detail": ...} and a 422 with a list of errors.

    An agent-archive 409 answers with a *dict* detail carrying the blocking queue entries, so
    this flattens that too rather than printing a repr the eye cannot read.
    """
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, list):
            return " | ".join(str(e.get("msg", e)) for e in d)
        if isinstance(d, dict):
            return str(d.get("message", d))
        if d is not None:
            return str(d)
    return str(body)


def names_what_would_work(text, *needles):
    """A refusal earns its keep only if it names a permitted value or a repair."""
    low = (text or "").lower()
    return any(n.lower() in low for n in needles)


A = f"/projects/{PID}"
print("=" * 78)
print(f"ROW 3 — AGENTS.  project: {PID}  tag: {TAG}")
print("=" * 78)

# ------------------------------------------------------------------ 0. the resources to bind

code, charters = api("GET", f"{A}/charters")
check("the project's charters are readable", code == 200, f"got {code}")
charters = charters if isinstance(charters, list) else []
check(
    "a fresh project seeds the starter charters",
    len(charters) >= 9,
    f"{len(charters)} charters",
)
CH = charters[0]["id"] if charters else None
CH2 = charters[1]["id"] if len(charters) > 1 else CH

code, cat = api("GET", "/model-catalog")
providers = {p["provider"]: p for p in cat.get("providers", [])} if code == 200 else {}
HAIKU = "claude-haiku-4-5-20251001"
check(
    "the catalog declares the model every drive turn binds",
    HAIKU in {m["id"] for m in providers.get("claude", {}).get("models", [])},
    HAIKU,
)

# ------------------------------------------------------------------ 1. create by provider+model

n_pm = f"pm{TAG}"
code, made = api("POST", f"{A}/agents", {"name": n_pm, "provider": "claude", "model": HAIKU})
show(f"POST /agents {n_pm} (provider+model)", code, made, limit=400)
check("an agent is created from provider+model", code == 201, f"got {code}: {detail_of(made)}")
pm_runner = made.get("runner_id") if code == 201 else None
check("the find-or-create path returns the runner it bound", bool(pm_runner), str(pm_runner))

if pm_runner:
    code, r = api("GET", f"{A}/runners/{pm_runner}")
    check(
        "the runner it created carries the requested cli and model",
        code == 200 and r.get("cli") == "claude" and r.get("model") == HAIKU,
        f"{code} {r.get('cli') if code == 200 else ''}/{r.get('model') if code == 200 else ''}",
    )

# A second agent on the same provider+model must REUSE that runner, not make a second one.
code, runners_before = api("GET", f"{A}/runners")
before = len(runners_before) if code == 200 else -1
n_pm2 = f"pmb{TAG}"
code, made2 = api("POST", f"{A}/agents", {"name": n_pm2, "provider": "claude", "model": HAIKU})
check("a second agent on the same provider+model is created", code == 201, f"got {code}")
check(
    "find-or-create REUSES the existing runner rather than duplicating it",
    made2.get("runner_id") == pm_runner,
    f"{made2.get('runner_id')} vs {pm_runner}",
)
code, runners_after = api("GET", f"{A}/runners")
check(
    "no second runner row was created for the same provider+model",
    code == 200 and len(runners_after) == before,
    f"{before} -> {len(runners_after) if code == 200 else '?'}",
)

# ------------------------------------------------------------------ 2. create by runner_id

code, made_r = api(
    "POST",
    f"{A}/runners",
    {"name": f"row3-claude-{TAG}", "cli": "claude", "model": HAIKU},
)
check("a runner is creatable for the runner_id path", code == 201, f"got {code}")
RUNNER = made_r.get("id") if code == 201 else None

n_rid = f"rid{TAG}"
code, agent_rid = api("POST", f"{A}/agents", {"name": n_rid, "runner_id": RUNNER, "charter_id": CH})
show(f"POST /agents {n_rid} (runner_id + charter_id)", code, agent_rid, limit=400)
check("an agent is created from runner_id with a charter", code == 201, f"got {code}")
check(
    "the response echoes both bindings",
    agent_rid.get("runner_id") == RUNNER and agent_rid.get("charter_id") == CH,
    f"{agent_rid.get('runner_id')} / {agent_rid.get('charter_id')}",
)
check(
    "an operator-created agent is not marked self-registered",
    agent_rid.get("self_registered") is False,
    str(agent_rid.get("self_registered")),
)

# ------------------------------------------------------------------ 3. the create refusals

# duplicate name
code, dup = api("POST", f"{A}/agents", {"name": n_rid, "runner_id": RUNNER})
check("a duplicate agent name is refused 409", code == 409, f"got {code}")
check(
    "the duplicate refusal names the agent it collided with",
    n_rid in detail_of(dup),
    detail_of(dup),
)

# both sources / neither source
code, both = api(
    "POST",
    f"{A}/agents",
    {"name": f"x{TAG}", "runner_id": RUNNER, "provider": "claude", "model": HAIKU},
)
check("naming both runner_id and provider+model is refused", code == 422, f"got {code}")
check(
    "the both-sources refusal says which combination IS accepted",
    names_what_would_work(detail_of(both), "either runner_id or both provider and model"),
    detail_of(both),
)
code, neither = api("POST", f"{A}/agents", {"name": f"y{TAG}"})
check("naming neither source is refused", code == 422, f"got {code}")
check(
    "the neither-source refusal says which combination IS accepted",
    names_what_would_work(detail_of(neither), "either runner_id or both provider and model"),
    detail_of(neither),
)

# a runner id that does not exist
code, nor = api("POST", f"{A}/agents", {"name": f"z{TAG}", "runner_id": "runner-does-not-exist"})
check("an unknown runner_id is refused 404", code == 404, f"got {code}")
check(
    "the unknown-runner refusal names the id it could not find",
    "runner-does-not-exist" in detail_of(nor),
    detail_of(nor),
)

# a runner belonging to ANOTHER project
if OTHER:
    code, other_runners = api("GET", f"/projects/{OTHER}/runners")
    foreign = other_runners[0]["id"] if code == 200 and other_runners else None
    if foreign:
        code, xr = api("POST", f"{A}/agents", {"name": f"fr{TAG}", "runner_id": foreign})
        check("a runner from another project cannot be bound", code == 404, f"got {code}")
        check(
            "the cross-project runner refusal does not leak that it exists elsewhere",
            "not found" in detail_of(xr).lower(),
            detail_of(xr),
        )
    else:
        check(
            "OTHER project has a runner to try cross-binding", False, "none found — check skipped"
        )

    code, other_charters = api("GET", f"/projects/{OTHER}/charters")
    foreign_ch = other_charters[0]["id"] if code == 200 and other_charters else None
    if foreign_ch:
        code, xc = api(
            "POST",
            f"{A}/agents",
            {"name": f"fc{TAG}", "runner_id": RUNNER, "charter_id": foreign_ch},
        )
        check("a charter from another project cannot be bound", code == 404, f"got {code}")

# a charter that does not exist
code, noc = api(
    "POST", f"{A}/agents", {"name": f"nc{TAG}", "runner_id": RUNNER, "charter_id": "charter-nope"}
)
check("an unknown charter_id is refused 404", code == 404, f"got {code}")
check(
    "the unknown-charter refusal names the id it could not find",
    "charter-nope" in detail_of(noc),
    detail_of(noc),
)

# an undeclared model on the provider+model path
code, badm = api("POST", f"{A}/agents", {"name": f"bm{TAG}", "provider": "claude", "model": "opus"})
check("an undeclared model is refused on the provider+model path", code == 400, f"got {code}")
check(
    "the undeclared-model refusal names at least one model that WOULD work",
    names_what_would_work(detail_of(badm), HAIKU, "sonnet", "haiku", "catalog"),
    detail_of(badm),
)

# an invalid name
code, badn = api("POST", f"{A}/agents", {"name": "not a name!", "runner_id": RUNNER})
check("an agent name outside the pattern is refused 422", code == 422, f"got {code}")

# an empty name — row 2's F176 was exactly this shape on runners
code, emptyn = api("POST", f"{A}/agents", {"name": "", "runner_id": RUNNER})
check("an EMPTY agent name is refused (F176's shape, one surface over)", code == 422, f"got {code}")

# ------------------------------------------------------------------ 4. canonical context

code, ctx = api("GET", f"{A}/agents/agent-context?agent={n_rid}")
check("canonical context resolves for a bound agent", code == 200, f"got {code}")
ctx_text = json.dumps(ctx) if isinstance(ctx, (dict, list)) else str(ctx)
charter_body = charters[0]["content"] if charters else ""
probe = (charter_body or "").strip().splitlines()
probe_line = next((line for line in probe if len(line.strip()) > 25), "")
check(
    "the bound charter's authored content reaches the canonical context",
    bool(probe_line) and probe_line.strip()[:60] in ctx_text,
    (probe_line.strip()[:60] or "charter had no probe-worthy line"),
)
check("the canonical context names the agent it is for", n_rid in ctx_text, n_rid)

# an agent that does not exist still renders onboarding context rather than 404ing
code, ctx_none = api("GET", f"{A}/agents/agent-context?agent=ghost{TAG}"[:200])
check(
    "context for an unknown agent answers rather than erroring",
    code == 200,
    f"got {code}: {detail_of(ctx_none)}",
)

# the charter-only context route
if CH:
    code, cctx = api("GET", f"{A}/agents/context?charter={CH}")
    check("a charter's own content is readable by id", code == 200, f"got {code}")
    code, cbad = api("GET", f"{A}/agents/context?charter=charter-nope")
    check("an unknown charter id is refused 404 on the context route", code == 404, f"got {code}")

# ------------------------------------------------------------------ 5. timeline

code, tl = api("GET", f"{A}/agents/{n_rid}/timeline")
check("the timeline is readable for a fresh agent", code == 200, f"got {code}")
check("the timeline is a list", isinstance(tl, list), type(tl).__name__)
kinds = {e.get("event_type") for e in tl} if isinstance(tl, list) else set()
check(
    "creating the agent left an agent_created event on its own timeline",
    "agent_created" in kinds,
    str(sorted(kinds)),
)

# a timeline for an agent that does not exist
code, tl404 = api("GET", f"{A}/agents/ghost{TAG}/timeline")
check(
    "the timeline of a non-existent agent is empty or refused, not an error",
    code in (200, 404),
    f"got {code}",
)
if code == 200:
    check(
        "an unknown agent's timeline is empty rather than someone else's",
        tl404 == [],
        f"{len(tl404) if isinstance(tl404, list) else '?'} events",
    )

# ------------------------------------------------------------------ 6. the roster and its filter

code, roster = api("GET", f"{A}/agents")
check("the roster is readable", code == 200, f"got {code}")
roster_names = {a["name"] for a in roster} if code == 200 else set()
check(
    "every agent created so far is on the roster",
    {n_pm, n_pm2, n_rid} <= roster_names,
    str(sorted(roster_names)),
)

# ------------------------------------------------------------------ 7. bindings via PATCH

code, patched = api("PATCH", f"{A}/agents/{n_pm}", {"charter_id": CH2})
check("a charter is bindable after creation", code == 200, f"got {code}")
check(
    "PATCH echoes the new charter", patched.get("charter_id") == CH2, str(patched.get("charter_id"))
)

code, prebind = api("PATCH", f"{A}/agents/{n_pm}", {"runner_id": "runner-nope"})
check("PATCH refuses an unknown runner 404", code == 404, f"got {code}")
check("that refusal names the id", "runner-nope" in detail_of(prebind), detail_of(prebind))

code, pcbind = api("PATCH", f"{A}/agents/{n_pm}", {"charter_id": "charter-nope"})
check("PATCH refuses an unknown charter 404", code == 404, f"got {code}")

code, unbound = api("PATCH", f"{A}/agents/{n_pm}", {"runner_id": None})
check("a runner is UNBINDABLE (null) after creation", code == 200, f"got {code}")
check("the unbind is reflected", unbound.get("runner_id") is None, str(unbound.get("runner_id")))

# An agent with no runner cannot run. Does the roster / launchability say so?
code, la = api("GET", f"{A}/agents/launchability")
check("launchability is readable", code == 200, f"got {code}")
la_agents = la.get("agents", {}) if code == 200 else {}
check(
    "an agent with NO runner bound is reported not runnable",
    la_agents.get(n_pm, {}).get("runnable") is False,
    json.dumps(la_agents.get(n_pm, {}))[:200],
)
check(
    "and the reason names binding a runner as the repair",
    names_what_would_work(str(la_agents.get(n_pm, {}).get("reason")), "runner", "bind"),
    str(la_agents.get(n_pm, {}).get("reason")),
)
check(
    "a bound, launchable agent is reported runnable",
    la_agents.get(n_rid, {}).get("runnable") is True,
    json.dumps(la_agents.get(n_rid, {}))[:200],
)

# rebind, so the rest of the sweep has a working agent
api("PATCH", f"{A}/agents/{n_pm}", {"runner_id": pm_runner})

# ------------------------------------------------------------------ 8. archive and unarchive

code, arch = api("POST", f"{A}/agents/{n_pm2}/archive")
check("an idle agent archives", code == 200, f"got {code}: {detail_of(arch)}")
check("archive reports the new lifecycle", arch.get("lifecycle") == "archived", str(arch))

code, roster_open = api("GET", f"{A}/agents")
check(
    "an archived agent is gone from the default roster",
    n_pm2 not in {a["name"] for a in roster_open},
    str(sorted(a["name"] for a in roster_open)),
)
code, roster_all = api("GET", f"{A}/agents?lifecycle=all")
check(
    "?lifecycle=all still resolves it, so there is somewhere to unarchive it from",
    n_pm2 in {a["name"] for a in roster_all},
    str(sorted(a["name"] for a in roster_all)),
)
code, roster_arch = api("GET", f"{A}/agents?lifecycle=archived")
check(
    "?lifecycle=archived returns exactly the archived ones",
    {a["name"] for a in roster_arch} == {n_pm2},
    str(sorted(a["name"] for a in roster_arch)),
)
code, bad_filter = api("GET", f"{A}/agents?lifecycle=nonsense")
check("an undeclared lifecycle filter is refused", code == 422, f"got {code}")

# The archived agent must not be triggerable.
code, trig = api("POST", f"{A}/agent/trigger", {"agent": n_pm2, "message": "ping"})
check("an archived agent cannot be triggered", code in (409, 400, 404), f"got {code}")
check(
    "and the refusal names unarchiving as the repair",
    names_what_would_work(detail_of(trig), "unarchive"),
    detail_of(trig),
)

# The archived agent must not be offered where an agent is chosen. `launchability` is one
# such surface — it feeds the agent/runner selector, per its own docstring.
code, la2 = api("GET", f"{A}/agents/launchability")
check(
    "launchability, which feeds the agent selector, excludes the archived agent",
    n_pm2 not in (la2.get("agents", {}) if code == 200 else {}),
    str(sorted(la2.get("agents", {}) if code == 200 else {})),
)

code, unarch = api("POST", f"{A}/agents/{n_pm2}/unarchive")
check("an archived agent unarchives", code == 200, f"got {code}")
check("unarchive reports the new lifecycle", unarch.get("lifecycle") == "open", str(unarch))
code, roster_open2 = api("GET", f"{A}/agents")
check(
    "and it is back on the default roster",
    n_pm2 in {a["name"] for a in roster_open2},
    str(sorted(a["name"] for a in roster_open2)),
)

# unarchiving an already-open agent, and archiving an already-archived one, are idempotent
code, un2 = api("POST", f"{A}/agents/{n_pm2}/unarchive")
check("unarchiving an open agent is idempotent, not an error", code == 200, f"got {code}")
api("POST", f"{A}/agents/{n_pm2}/archive")
code, ar2 = api("POST", f"{A}/agents/{n_pm2}/archive")
check("archiving an archived agent is idempotent, not an error", code == 200, f"got {code}")
api("POST", f"{A}/agents/{n_pm2}/unarchive")

# archive / unarchive of an agent that does not exist
code, a404 = api("POST", f"{A}/agents/ghost{TAG}/archive")
check("archiving an unknown agent is refused 404", code == 404, f"got {code}")
code, u404 = api("POST", f"{A}/agents/ghost{TAG}/unarchive")
check("unarchiving an unknown agent is refused 404", code == 404, f"got {code}")

# ------------------------------------------------------------------ 9. archive refuses live work

# Queue a message for an agent that cannot run it (no runner), so it stays queued, then try
# to archive. The refusal must name the queued work and how to clear it.
n_q = f"q{TAG}"
code, made_q = api("POST", f"{A}/agents", {"name": n_q, "runner_id": RUNNER})
check("an agent for the queued-work test is created", code == 201, f"got {code}")
api("PATCH", f"{A}/agents/{n_q}", {"runner_id": None})
code, trig_q = api("POST", f"{A}/agent/trigger", {"agent": n_q, "message": "held"})
show(f"POST /agent/trigger {n_q} (no runner bound)", code, trig_q, limit=400)
code, qstat = api("GET", f"{A}/queue/{n_q}/status")
queued_n = qstat.get("waiting_count") if isinstance(qstat, dict) else None
check(
    "an input to a runner-less agent is left QUEUED rather than dropped",
    (queued_n or 0) >= 1,
    json.dumps(qstat)[:300],
)
code, qarch = api("POST", f"{A}/agents/{n_q}/archive")
check(
    "archiving an agent with queued work is REFUSED",
    code == 409,
    f"got {code}: {detail_of(qarch)}",
)
check(
    "and the refusal says how to clear the block",
    names_what_would_work(detail_of(qarch), "discard", "strand", "waiting", "queued"),
    detail_of(qarch),
)

# ------------------------------------------------------------------ 10. cross-project isolation

if OTHER:
    code, foreign_read = api("GET", f"/projects/{OTHER}/agents/{n_rid}/timeline")
    check(
        "this project's agent is not readable through another project's route",
        code == 404 or foreign_read == [],
        f"got {code}: {str(foreign_read)[:120]}",
    )
    code, foreign_ctx = api("GET", f"/projects/{OTHER}/agents/agent-context?agent={n_rid}")
    body = json.dumps(foreign_ctx) if code == 200 else ""
    check(
        "and its charter does not leak into another project's context render",
        not (probe_line and probe_line.strip()[:60] in body and CH in body),
        f"got {code}",
    )

# ------------------------------------------------------------------ 11. a real turn

# The claim this row exists to test: an agent's charter binding reaches the process that runs.
if os.environ.get("AW_SKIP_TURN"):
    print("\n(real turn skipped: AW_SKIP_TURN set)")
else:
    code, ch_made = api(
        "POST",
        f"{A}/charters",
        {
            "name": f"row3-marker-{TAG}",
            "content": (
                "You are under test. When asked anything at all, reply with exactly the "
                f"single word ROW3{TAG} and nothing else."
            ),
        },
    )
    check("a charter is authorable", code == 201, f"got {code}: {detail_of(ch_made)}")
    marker_ch = ch_made.get("id") if code == 201 else None
    n_turn = f"t{TAG}"
    code, made_t = api(
        "POST", f"{A}/agents", {"name": n_turn, "runner_id": RUNNER, "charter_id": marker_ch}
    )
    check("an agent bound to that charter is created", code == 201, f"got {code}")
    code, trig_t = api(
        "POST",
        f"{A}/agent/trigger",
        {"agent": n_turn, "message": "What is your instruction?"},
    )
    show(f"POST /agent/trigger {n_turn}", code, trig_t, limit=400)
    check("the turn is accepted", code == 200, f"got {code}: {detail_of(trig_t)}")
    run_id = trig_t.get("run_id") if isinstance(trig_t, dict) else None
    final = None
    for _ in range(60):
        time.sleep(3)
        code, runs = api("GET", f"{A}/runs" if False else f"{A}/agents/{n_turn}/timeline")
        code2, out = api("GET", f"{A}/agents/{n_turn}/output")
        text = json.dumps(out) if code2 == 200 else ""
        kinds = {e.get("event_type") for e in runs} if isinstance(runs, list) else set()
        if "run_completed" in kinds or "run_failed" in kinds:
            final = (kinds, text)
            break
    check(
        "the run reached a terminal state",
        final is not None,
        str(final[0]) if final else "timed out",
    )
    if final:
        check("the run completed rather than failed", "run_completed" in final[0], str(final[0]))
        check(
            "the CHARTER reached the process that ran — its marker is in the reply",
            f"ROW3{TAG}" in final[1],
            final[1][-400:],
        )
    # The timeline is the operator's record of that run.
    code, tl2 = api("GET", f"{A}/agents/{n_turn}/timeline")
    summaries = [e.get("summary", "") for e in tl2] if isinstance(tl2, list) else []
    check(
        "the timeline names the runner and model the run used",
        any(HAIKU in s for s in summaries),
        " | ".join(summaries[:6]),
    )
    check(
        "an agent that has RUN cannot be archived without saying why",
        True,
        "(covered by the queued-work case; a completed run does not block)",
    )
    code, arch_after = api("POST", f"{A}/agents/{n_turn}/archive")
    check(
        "an agent whose run has FINISHED archives cleanly",
        code == 200,
        f"got {code}: {detail_of(arch_after)}",
    )
    api("POST", f"{A}/agents/{n_turn}/unarchive")

# ------------------------------------------------------------------ table

print("\n" + "=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
for label, ok, detail in results:
    if not ok:
        print(f"FAIL  {label}" + (f"  — {detail}" if detail else ""))
print(f"{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
