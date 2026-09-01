"""SWEEP ROW 12 — PERMISSIONS. The manual posture, driven where nothing has driven it before.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_sweep_row12_permissions.py
    AW_HUB=... AW_KEY=... py -3.11 t_sweep_row12_permissions.py --teardown

**Prior coverage was read first, and is deliberately not re-ploughed.** `t_row13_row14.py` drives
the happy path once — a card appears under `overrides.permission_mode = "manual"`, the operator
allows it, the card clears. `t_row19_crash_card.py` drives the crash: a card on screen when the Hub
dies, and what `expire_pending_for_run` leaves behind. Between them they cover *allow* and
*Hub-killed*.

What neither touches, and what this file is about:

* **Deny.** Nobody has ever pressed Deny in a drive. The route writes a `permission_denied` event,
  and `record_permission_decision` then *deliberately suppresses* the run's own report of the same
  refusal by joining on a card already sitting at `denied` (`agent_actions.py:_operator_already_
  refused`). One operator action, two reporters, one event — asserted here by counting.
* **Expiry by the agent's own timeout.** `Agent.permission_timeout_seconds` is carried to the
  spawned process as `AW_DECISION_TIMEOUT` (`agent_trigger.py:1027`) and read back by
  `mcp_server._configured_wait`. Nothing has ever checked that the number an operator types is the
  number the run waits. This measures it: the wait is set to its floor, the card is left alone, and
  the run's own refusal sentence — which quotes the timeout — is read back out of the timeline.
* **Dismiss.** Shipped in migration `0062`, and never driven at all.
* **The decided history.** Every terminal card is kept on purpose ("that the operator was asked ...
  is exactly what the record is for"). This asks which screen can show it.

One agent, FOUR real `claude-haiku-4-5` turns per run -- deny, expiry, allow, and the default-posture
comparison in leg 6. No job is created, so there is nothing to
leave enabled. Both fixture projects are created by this script and removed by `--teardown`.
"""

import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the other trial Hub.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-row12")
DIR_OTHER = DIR + "-other"
NAME = os.path.basename(DIR.rstrip("\\/"))
NAME_OTHER = os.path.basename(DIR_OTHER.rstrip("\\/"))
AGENT = "asker"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")

PASS, FAIL = [], []


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


# ---------------------------------------------------------------------------- fixture


def find_project(name):
    code, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return next((p["id"] for p in rows if p.get("name") == name), None)


def project_count():
    code, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return len(rows)


def ensure_repo(path):
    """A fixture directory that is a git repository WITH A COMMIT IN IT.

    Not decoration. A project whose repository has no commits cannot run a turn: `git worktree add
    ... HEAD` fails with "invalid reference: HEAD", and `POST /agent/trigger` answers an honest 200
    with `run_id: null` and the reason in `waiting_reason`. That cost a whole harness run on
    2026-09-01 before it was written down, and `--teardown` removes these directories, so the next
    run of THIS file would have hit it too if the setup were left to the operator.
    """
    os.makedirs(path, exist_ok=True)
    run = lambda *a: subprocess.run(a, cwd=path, capture_output=True, text=True)  # noqa: E731
    if run("git", "rev-parse", "--git-dir").returncode != 0:
        run("git", "init")
    if run("git", "rev-parse", "HEAD").returncode != 0:
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("row 12 permissions fixture" + chr(10))
        run("git", "add", "README.md")
        run("git", "-c", "user.email=drive@local", "-c", "user.name=drive",
            "commit", "-m", "fixture: initial commit so a worktree can be added")
    head = run("git", "rev-parse", "--short", "HEAD")
    print(f"fixture repo {path} -> HEAD {head.stdout.strip() or head.stderr.strip()}")


def ensure_project(path, name):
    found = find_project(name)
    if found:
        return found
    ensure_repo(path)
    code, body = api("POST", "/projects/open", {"path": path, "name": name})
    if code >= 300:
        sys.exit(f"could not open project {name}: {code} {body}")
    return body["id"]


def ensure_runner(project):
    code, body = api("GET", f"/projects/{project}/runners")
    rows = body if isinstance(body, list) else (body or {}).get("runners") or []
    for r in rows:
        if r.get("name") == "Haiku (cheap)":
            return r["id"]
    code, body = api(
        "POST",
        f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    return body["id"]


def ensure_agent(project, name, runner):
    code, body = api("POST", f"/projects/{project}/agents", {"name": name, "runner_id": runner})
    if code < 300:
        return name
    code, body = api("GET", f"/projects/{project}/agents")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    if any(a.get("name") == name for a in rows):
        return name
    sys.exit(f"could not create or find agent {name}: {body}")


def teardown():
    for name in (NAME, NAME_OTHER):
        pid = find_project(name)
        if pid:
            code, body = api("DELETE", f"/projects/{pid}")
            print(f"deleted {name} ({pid}) -> {code}")
    for path in (DIR, DIR_OTHER):
        if os.path.isdir(path):
            # `ignore_errors=True` alone leaves `.git` behind on Windows: git marks its loose
            # objects read-only, and `os.remove` on a read-only file raises PermissionError.
            # Measured -- the first teardown of this fixture reported `exists=True` with nothing
            # but `.git/objects` left. Clearing the read-only bit and retrying is the remedy.
            def _force(func, target, _exc):
                os.chmod(target, stat.S_IWRITE)
                func(target)

            shutil.rmtree(path, onerror=_force)
            print(f"removed {path} -> exists={os.path.isdir(path)}")
    print(f"projects now: {project_count()}")


if "--teardown" in sys.argv:
    teardown()
    sys.exit(0)


P = ensure_project(DIR, NAME)
P2 = ensure_project(DIR_OTHER, NAME_OTHER)
RUNNER = ensure_runner(P)
ensure_agent(P, AGENT, RUNNER)
A = f"/projects/{P}"
A2 = f"/projects/{P2}"
print(f"fixture: {NAME}={P}  other={NAME_OTHER}={P2}  agent={AGENT}  tag={TAG}")

WORKTREE = os.path.join(DIR, ".agentweave", "worktrees", AGENT)


# ---------------------------------------------------------------------------- helpers


def cards(**q):
    query = "&".join(f"{k}={v}" for k, v in q.items())
    code, body = api("GET", f"{A}/permission-requests" + (f"?{query}" if query else ""))
    rows = body if isinstance(body, list) else (body or {}).get("permission_requests") or []
    return code, rows


def card(request_id):
    """One card by id, read through the widest listing this router offers."""
    _, rows = cards(pending_only="false")
    return next((r for r in rows if r["id"] == request_id), None)


def wait_for(label, predicate, timeout=180, interval=2):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    print(f"  ..   TIMED OUT waiting for {label} after {timeout}s")
    return None


def agent_status():
    _, body = api("GET", f"{A}/agents")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    row = next((a for a in rows if a.get("name") == AGENT), None)
    return (row or {}).get("status")


def wait_idle(timeout=240):
    return wait_for("the agent to go idle", lambda: agent_status() == "idle", timeout=timeout)


def events(limit=200):
    code, body = api("GET", f"{A}/events/history?limit={limit}")
    rows = body if isinstance(body, list) else (body or {}).get("events") or []
    return rows


def denied_events(tool_use_id):
    """Every `permission_denied` event naming this exact tool call.

    Counting is the assertion: the operator's decision route writes one, and the run reports its
    own decision separately. `_operator_already_refused` is what stops the operator seeing the
    same refusal twice, and it can only be checked by counting.
    """
    out = []
    for e in events():
        if e.get("type") != "permission_denied":
            continue
        data = e.get("data") or {}
        if data.get("tool_use_id") == tool_use_id:
            out.append(e)
    return out


def trigger_manual(message):
    code, body = api(
        "POST",
        f"{A}/agent/trigger",
        {"agent": AGENT, "message": message, "overrides": {"permission_mode": "manual"}},
    )
    return code, body


def open_cards():
    _, rows = cards()
    return [r for r in rows if r.get("status") == "pending"]


# =============================================================================================
leg(1, "The router before any card exists — shape, refusals, and what the query says")

wait_idle(timeout=120)
code, rows = cards()
ok("GET /permission-requests answers 200", code == 200, f"{code}")
ok("  ... and it is a bare list, not an envelope", isinstance(rows, list), str(rows)[:200])
note("cards already in this project", len(rows))

for q in ({"pending_only": "false"}, {"include_expired": "true"},
          {"pending_only": "false", "include_expired": "true"}):
    c, _ = cards(**q)
    ok(f"  ... GET with {q} answers 200", c == 200, str(c))

c, _ = api("GET", f"{A}/permission-requests?pending_only=maybe")
ok("a non-boolean pending_only is refused rather than guessed at", c == 422, str(c))
c, _ = api("GET", f"{A}/permission-requests?nonsense=1")
ok("an undeclared query parameter is ignored (FastAPI's documented behaviour)", c == 200, str(c))

c, b = api("POST", f"{A}/permission-requests/perm-nosuchthing/decide", {"allow": True})
ok("deciding an unknown id is a 404", c == 404, f"{c} {str(b)[:120]}")
c, b = api("POST", f"{A}/permission-requests/perm-nosuchthing/dismiss")
ok("dismissing an unknown id is a 404", c == 404, f"{c} {str(b)[:120]}")

c, b = api("POST", f"{A}/permission-requests/perm-nosuchthing/decide", {"decision": "allow"})
ok(
    "the old spelling {'decision': 'allow'} is refused, naming both fields",
    c == 422 and "allow" in json.dumps(b),
    f"{c} {str(b)[:200]}",
)
# `"banana"`, not `"yes"`: Pydantic's lax bool interprets "yes"/"true"/1 as True, so those reach
# the route and answer 404 on the unknown id. Measured, not assumed -- and it is framework-wide
# behaviour on every RequestModel in the app, not something this router chose.
c, b = api("POST", f"{A}/permission-requests/perm-nosuchthing/decide", {"allow": "banana"})
ok("an uninterpretable allow is refused", c == 422, f"{c} {str(b)[:160]}")
c, b = api("POST", f"{A}/permission-requests/perm-nosuchthing/decide", {"allow": None})
ok("a null allow is refused", c == 422, f"{c} {str(b)[:160]}")
c_yes, _ = api("POST", f"{A}/permission-requests/perm-nosuchthing/decide", {"allow": "yes"})
note("`allow: 'yes'` is coerced to True by Pydantic and reaches the route", c_yes)


# =============================================================================================
leg(2, "The per-agent permission timeout — what the operator may set, and what is stored")

c, b = api("PATCH", f"{A}/agents/{AGENT}", {"permission_timeout_seconds": 5})
ok("a wait below the 10s floor is refused", c in (400, 422), f"{c} {str(b)[:160]}")
note("refusal for 5s", str(b)[:200])
c, b = api("PATCH", f"{A}/agents/{AGENT}", {"permission_timeout_seconds": 601})
ok("a wait above the 600s ceiling is refused", c in (400, 422), f"{c} {str(b)[:160]}")
c, b = api("PATCH", f"{A}/agents/{AGENT}", {"permission_timeout_seconds": 10})
ok("the floor itself is accepted", c == 200, f"{c} {str(b)[:200]}")
stored = (b or {}).get("permission_timeout_seconds") if isinstance(b, dict) else None
ok("  ... and the response states what was stored", stored == 10, str(stored))


# =============================================================================================
leg(3, "DENY — the operator refuses, and the refusal reaches the agent exactly once")

NOTE_DENY = f"row12-deny-{TAG}.txt"
before_cards = {r["id"] for r in cards(pending_only="false")[1]}
code, body = trigger_manual(
    f"Write the single line 'row 12 deny drive' to a new file named {NOTE_DENY} in the "
    "project root using the Write tool. If the write is refused, do NOT retry it and do not "
    "try any other tool: reply with the refusal message you were given and stop."
)
ok("a manual-posture turn starts", code in (200, 201, 202) and body.get("run_id"), str(body)[:200])
RUN_DENY = (body or {}).get("run_id")
note("run", RUN_DENY)

deny_card = wait_for(
    "a permission card",
    lambda: next((r for r in open_cards() if r["id"] not in before_cards), None),
    timeout=180,
)
ok("the run stops and asks the operator", bool(deny_card), "no card ever appeared")
if not deny_card:
    print("\nNo card: the rest of leg 3 cannot be driven.")
else:
    note("card", json.dumps({k: deny_card.get(k) for k in
                             ("id", "agent", "run_id", "tool_name", "status",
                              "decided_at", "decided_by", "dismissed")}))
    note("tool_input", json.dumps(deny_card.get("tool_input"))[:300])
    ok("  ... the card names the run that is waiting", deny_card.get("run_id") == RUN_DENY,
       f"{deny_card.get('run_id')} != {RUN_DENY}")
    ok("  ... and the agent that asked", deny_card.get("agent") == AGENT, str(deny_card.get("agent")))
    ok("  ... it carries the tool call the operator is deciding",
       bool(deny_card.get("tool_name")) and bool(deny_card.get("tool_use_id")),
       str(deny_card)[:200])
    ok("  ... nothing is decided yet", deny_card.get("decided_at") is None
       and deny_card.get("decided_by") is None, str(deny_card)[:200])
    ok("  ... and the file the tool wants to write is named in tool_input",
       NOTE_DENY in json.dumps(deny_card.get("tool_input") or {}),
       json.dumps(deny_card.get("tool_input"))[:200])

    # Isolation and refusals, while the card is live. Every one of these must leave it PENDING,
    # which is asserted immediately afterwards -- a probe that quietly decided the card would
    # make everything below it meaningless.
    c, b = api("POST", f"{A2}/permission-requests/{deny_card['id']}/decide", {"allow": True})
    ok("another project cannot decide this card", c == 404, f"{c} {str(b)[:140]}")
    c, b = api("POST", f"{A2}/permission-requests/{deny_card['id']}/dismiss")
    ok("another project cannot dismiss it either", c == 404, f"{c} {str(b)[:140]}")
    c, b = api("GET", f"{A2}/permission-requests?pending_only=false")
    ok("  ... and it is not in the other project's list",
       deny_card["id"] not in json.dumps(b), str(b)[:200])
    # `decide` requires a body, so a bodyless call is the probe. `dismiss` takes NO body, so
    # calling it bodyless is its NORMAL call and must never be folded in here -- it would
    # decide the card this leg is about to assert on.
    c, b = api("POST", f"{A}/permission-requests/{deny_card['id']}/decide")
    ok("decide with no body at all is refused", c == 422, f"{c} {str(b)[:140]}")
    c, b = api("POST", f"{A}/permission-requests/{deny_card['id']}/dismiss")
    ok(
        "dismissing a PENDING card is refused -- clearing it would deny it by neglect",
        c == 409,
        f"{c} {str(b)[:200]}",
    )
    note("refusal sentence", str(b)[:200])
    live = card(deny_card["id"])
    ok("  ... and after all four probes the card is still pending",
       (live or {}).get("status") == "pending", str(live)[:200])

    c, decided = api("POST", f"{A}/permission-requests/{deny_card['id']}/decide", {"allow": False})
    ok("the operator can refuse it", c == 200, f"{c} {str(decided)[:200]}")
    ok("  ... the card records denied", (decided or {}).get("status") == "denied",
       str(decided)[:200])
    ok("  ... decided_by names the operator", (decided or {}).get("decided_by") == "operator",
       str(decided)[:200])
    ok("  ... and decided_at is set, which is what distinguishes an answer from a timeout",
       bool((decided or {}).get("decided_at")), str(decided)[:200])

    c, b = api("POST", f"{A}/permission-requests/{deny_card['id']}/decide", {"allow": True})
    ok("deciding it a second time is a 409, not a silent re-answer", c == 409, f"{c} {str(b)[:200]}")
    note("second-decision refusal", str(b)[:200])

    ok("a denied card leaves the default (pending-only) list",
       deny_card["id"] not in json.dumps(cards()[1]), "still listed")
    ok("  ... and is still retrievable with pending_only=false",
       bool(card(deny_card["id"])), "not retrievable at all")

    # What the shipped route says about itself: "Only an expired request may be dismissed."
    c, b = api("POST", f"{A}/permission-requests/{deny_card['id']}/dismiss")
    ok(
        "dismissing a DENIED card is refused, as the route's own contract states",
        c == 409,
        f"{c} {str(b)[:200]}",
    )
    note("dismiss on a decided card answered", f"{c} {str(b)[:160]}")

    status_deny = wait_idle(timeout=240)
    ok("the refused run ends rather than hanging", bool(status_deny), f"agent={agent_status()}")
    wrote = os.path.exists(os.path.join(WORKTREE, NOTE_DENY)) or os.path.exists(
        os.path.join(DIR, NOTE_DENY)
    )
    ok("the refused write did NOT land", not wrote, f"{NOTE_DENY} exists")

    time.sleep(4)
    evs = denied_events(deny_card.get("tool_use_id") or "no-such-tool-use-id")
    ok(
        "one operator refusal produces exactly ONE permission_denied event, not two",
        len(evs) == 1,
        f"{len(evs)} events: {[str(e.get('data'))[:120] for e in evs]}",
    )
    for e in evs:
        note("event", f"{e.get('type')} {json.dumps(e.get('data'))[:220]}")


# =============================================================================================
leg(4, "EXPIRY — nobody answers, and the agent's own timeout is the one the operator set")

NOTE_EXP = f"row12-expire-{TAG}.txt"
before_cards = {r["id"] for r in cards(pending_only="false")[1]}
code, body = trigger_manual(
    f"Write the single line 'row 12 expiry drive' to a new file named {NOTE_EXP} in the "
    "project root using the Write tool. If the write is refused, do NOT retry it and do not "
    "try any other tool: reply with the refusal message you were given and stop."
)
ok("a second manual-posture turn starts", code in (200, 201, 202) and body.get("run_id"),
   str(body)[:200])
RUN_EXP = (body or {}).get("run_id")

exp_card = wait_for(
    "a second permission card",
    lambda: next((r for r in open_cards() if r["id"] not in before_cards), None),
    timeout=180,
)
ok("the run asks again", bool(exp_card), "no second card")
if exp_card:
    opened_at = time.time()
    note("card", exp_card["id"])
    gone = wait_for(
        "the card to stop waiting",
        lambda: (lambda r: r if r and r.get("status") == "expired" else None)(card(exp_card["id"])),
        timeout=90,
    )
    waited = time.time() - opened_at
    ok("an unanswered card expires rather than waiting forever", bool(gone), str(card(exp_card["id"]))[:200])
    note("observed wait before it expired", f"~{waited:.0f}s (the agent's setting is 10s)")
    ok(
        "  ... and it expires on the operator's 10s setting, not the 120s default",
        waited < 60,
        f"{waited:.0f}s -- AW_DECISION_TIMEOUT may not have reached the run",
    )
    ok("  ... decided_at stays NULL: nobody answered", (gone or {}).get("decided_at") is None,
       str(gone)[:200])
    ok("  ... and decided_by stays NULL too", (gone or {}).get("decided_by") is None,
       str(gone)[:200])

    ok("an expired card is NOT in the default list",
       exp_card["id"] not in json.dumps(cards()[1]), "still in the default list")
    ok("  ... but include_expired=true shows it, which is what the UI asks for",
       exp_card["id"] in json.dumps(cards(include_expired="true")[1]), "not shown even then")

    c, b = api("POST", f"{A}/permission-requests/{exp_card['id']}/decide", {"allow": True})
    ok("deciding an expired card is refused -- the run has gone", c == 409, f"{c} {str(b)[:200]}")
    note("refusal", str(b)[:200])

    c, b = api("POST", f"{A}/permission-requests/{exp_card['id']}/dismiss")
    ok("the operator can dismiss it once they have seen it", c == 200, f"{c} {str(b)[:200]}")
    ok("  ... dismissed is recorded", (b or {}).get("dismissed") is True, str(b)[:200])
    ok("  ... the terminal status is kept, not overwritten", (b or {}).get("status") == "expired",
       str(b)[:200])
    first_dismiss = json.dumps(b, sort_keys=True, default=str)
    c, b2 = api("POST", f"{A}/permission-requests/{exp_card['id']}/dismiss")
    ok("dismissing twice is idempotent, not a conflict", c == 200, f"{c} {str(b2)[:160]}")
    ok("  ... and the second dismiss does not move anything",
       json.dumps(b2, sort_keys=True, default=str) == first_dismiss,
       f"{first_dismiss[:160]} vs {json.dumps(b2, default=str)[:160]}")
    ok("a dismissed card leaves even the include_expired list",
       exp_card["id"] not in json.dumps(cards(include_expired="true")[1]), "still shown")

    status_exp = wait_idle(timeout=240)
    ok("the run that was never answered ends anyway", bool(status_exp), f"agent={agent_status()}")
    wrote = os.path.exists(os.path.join(WORKTREE, NOTE_EXP)) or os.path.exists(
        os.path.join(DIR, NOTE_EXP)
    )
    ok("the unanswered write did NOT land", not wrote, f"{NOTE_EXP} exists")

    time.sleep(4)
    evs = denied_events(exp_card.get("tool_use_id") or "no-such-tool-use-id")
    ok(
        "the operator is told their agent gave up, in an event of its own",
        len(evs) >= 1,
        f"{len(evs)} events",
    )
    reasons = [str((e.get("data") or {}).get("reason") or "") for e in evs]
    note("reason the run reported", reasons[:2])
    ok(
        "  ... and the sentence quotes the 10s the operator configured",
        any("10s" in r for r in reasons),
        f"{reasons}",
    )
    ok(
        "  ... an expiry is NOT attributed to an operator who never answered",
        all("operator refused" not in r for r in reasons),
        f"{reasons}",
    )


# =============================================================================================
leg(5, "ALLOW — the operator agrees, the work lands, and then the record goes where?")

# Back to the built-in wait first. `None` clears the setting, which is worth driving on its own:
# F219 is the same shape on the runner route (`PATCH {"model": null}` answers 200 and changes
# nothing). Here the loop is `if field in body`, so a null really does clear.
c, b = api("PATCH", f"{A}/agents/{AGENT}", {"permission_timeout_seconds": None})
ok("the per-agent wait can be cleared back to the default", c == 200, f"{c} {str(b)[:160]}")
ok(
    "  ... and clearing it really clears it (F219's shape is ABSENT on this route)",
    (b or {}).get("permission_timeout_seconds") is None,
    str((b or {}).get("permission_timeout_seconds")),
)

# An ABSOLUTE path in the project root, which is *outside* this agent's own worktree
# (`.agentweave/worktrees/asker`, the directory the run is given as AW_WORKSPACE_DIR). Spelled out
# rather than left as "the project root" because the first two runs of this harness said that and
# the agent resolved it to its cwd once and to the real root the next time -- the assertion moved
# under the model's feet. Leg 6 then asks for the same path under the default posture, so the two
# postures are compared on one path rather than on two.
NOTE_OK = f"row12-allow-{TAG}.txt"
ABS_OK = os.path.join(DIR, NOTE_OK)
before_cards = {r["id"] for r in cards(pending_only="false")[1]}
code, body = trigger_manual(
    f"Write the single line 'row 12 allow drive' to a new file at the absolute path {ABS_OK} "
    "using the Write tool. Use exactly that path. Then stop."
)
ok("a third manual-posture turn starts", code in (200, 201, 202) and body.get("run_id"),
   str(body)[:200])

allow_card = wait_for(
    "a third permission card",
    lambda: next((r for r in open_cards() if r["id"] not in before_cards), None),
    timeout=180,
)
ok("the run asks before writing", bool(allow_card), "no third card")
if allow_card:
    c, decided = api("POST", f"{A}/permission-requests/{allow_card['id']}/decide", {"allow": True})
    ok("the operator can allow it", c == 200 and (decided or {}).get("status") == "allowed",
       f"{c} {str(decided)[:200]}")
    ok("  ... decided_by names the operator", (decided or {}).get("decided_by") == "operator",
       str(decided)[:160])
    landed = wait_for(
        "the approved write to land",
        lambda: os.path.exists(ABS_OK) or os.path.exists(os.path.join(WORKTREE, NOTE_OK)),
        timeout=180,
    )
    ok("an allowed write actually happens", bool(landed), f"{ABS_OK} never appeared")
    where = "the project root, OUTSIDE the agent's worktree" if os.path.exists(ABS_OK) else (
        "the agent's own worktree" if os.path.exists(os.path.join(WORKTREE, NOTE_OK)) else "nowhere"
    )
    note("the approved write landed in", where)
    ok(
        "  ... and the operator's Allow reached outside the agent's workspace",
        os.path.exists(ABS_OK),
        f"the agent wrote to its worktree instead; the card path was "
        f"{json.dumps((card(allow_card['id']) or {}).get('tool_input'))[:160]}",
    )
    # What the card could have told the operator, and what it carries. The Hub knows this run's
    # workspace -- it sets AW_WORKSPACE_DIR itself -- but the card schema has no field for it, so
    # no client can mark a path as inside or outside. Read from the live OpenAPI, not from source.
    import urllib.request

    with urllib.request.urlopen(HUB + "/openapi.json", timeout=20) as fh:
        schema = json.load(fh)
    props = sorted(
        schema["components"]["schemas"]["PermissionRequestResponse"]["properties"]
    )
    note("PermissionRequestResponse fields", props)
    ok(
        "the card carries NO workspace/boundary field, so no screen can mark the path",
        not any("workspace" in f or "boundary" in f or "outside" in f for f in props),
        str(props),
    )
    wait_idle(timeout=240)
    time.sleep(4)

    # Now the question this leg exists for. The row is kept -- the route says so -- but every
    # query the product issues excludes it, and no event was written for an approval.
    ok(
        "an approval writes no event at all",
        len(denied_events(allow_card.get("tool_use_id") or "no-such-tool-use-id")) == 0,
        "an event was written after all",
    )
    types = {e.get("type") for e in events()}
    ok(
        "  ... and nothing else records that the operator was even asked",
        "permission_requested" not in types and "permission_allowed" not in types,
        str(sorted(types)),
    )
    note("event types in this project", sorted(types))
    ok(
        "an allowed card is gone from the default list",
        allow_card["id"] not in json.dumps(cards()[1]),
        "still listed",
    )
    ok(
        "  ... and gone from include_expired=true, which is the ONLY query the UI issues",
        allow_card["id"] not in json.dumps(cards(include_expired="true")[1]),
        "still listed",
    )
    ok(
        "  ... while the row itself is kept, and pending_only=false returns it",
        bool(card(allow_card["id"])) and card(allow_card["id"]).get("status") == "allowed",
        str(card(allow_card["id"]))[:200],
    )


# =============================================================================================
leg(6, "The same path under the DEFAULT posture — what the operator's click stood in for")

NOTE_DEF = f"row12-default-{TAG}.txt"
ABS_DEF = os.path.join(DIR, NOTE_DEF)
before_evs = len(events())
code, body = api(
    "POST",
    f"{A}/agent/trigger",
    # No overrides at all: the built-in posture, where `mcp_server._decide` answers instead of the
    # operator. Same directory, same tool, same kind of path as leg 5.
    {
        "agent": AGENT,
        "message": (
            f"Write the single line 'row 12 default posture' to a new file at the absolute path "
            f"{ABS_DEF} using the Write tool. Use exactly that path. If it is refused, do NOT "
            "retry and do not try another tool or another path: reply with the refusal message "
            "and stop."
        ),
    },
)
ok("a default-posture turn starts", code in (200, 201, 202) and body.get("run_id"), str(body)[:200])
wait_idle(timeout=240)
time.sleep(4)
new_evs = [e for e in events() if e.get("type") == "permission_denied"]
reasons = [str((e.get("data") or {}).get("reason") or "") for e in new_evs]
boundary = [r for r in reasons if "workspace" in r.lower()]
note("refusal reasons now in the timeline", reasons[-3:])
ok(
    "the same write is refused by the Hub itself under the default posture",
    bool(boundary),
    f"no workspace refusal among {reasons[-3:]}",
)
ok(
    "  ... and the file the operator allowed in leg 5 does NOT exist under it",
    not os.path.exists(ABS_DEF),
    f"{ABS_DEF} was written anyway",
)
ok(
    "  ... no card is raised for it: the default posture never asks",
    not [r for r in cards()[1] if NOTE_DEF in json.dumps(r.get("tool_input") or {})],
    "a card was raised under the default posture",
)


# =============================================================================================
leg(7, "The decided record — which screen can show what the operator agreed to?")

c, all_rows = cards(pending_only="false")
terminal = [r for r in all_rows if r.get("status") in ("allowed", "denied", "expired")]
ok("every terminal card is kept, as the route says it is", len(terminal) >= 1, str(len(terminal)))
note("terminal cards in this project", [(r["id"], r["status"]) for r in terminal])

# Anchored on the repository root, NOT on the process's cwd. The first run of this harness was
# started from `scripts/drive/`, so both relative paths resolved to nothing, every grep returned
# zero, and leg 5 read as "the whole router is missing from the bundle" -- a fabricated F215/F225.
# Row 10 nearly filed the same shape of false finding for the same kind of reason.
REPO = pathlib.Path(__file__).resolve().parents[2]
src = REPO / "hub" / "ui" / "src"
bundle = REPO / "hub" / "hub" / "static" / "ui"
assert src.is_dir() and bundle.is_dir(), f"missing {src} / {bundle}"


def hits(root, needle, suffixes=(".ts", ".tsx", ".js", ".css", ".html")):
    found = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in suffixes:
            try:
                if needle in path.read_text(encoding="utf-8", errors="replace"):
                    found.append(str(path))
            except OSError:
                pass
    return found


for needle, label in (
    ("permission-requests", "the list/decide route"),
    ("include_expired", "the widening flag the card list depends on"),
    ("/dismiss", "the dismiss route"),
):
    s, b = hits(src, needle), hits(bundle, needle)
    ok(f"{label} is in the SERVED bundle, not only in source",
       len(b) >= 1, f"source={len(s)} bundle={len(b)}")
    note(f"'{needle}'", f"source={len(s)} bundle={len(b)}")

s_pending = hits(src, "pending_only")
ok(
    "NO screen asks for the decided history (pending_only is never sent by the UI)",
    len(s_pending) == 0,
    f"call sites: {s_pending}",
)
note("pending_only call sites under hub/ui/src", s_pending)

s_denied = hits(src, "permission_denied")
note("permission_denied handled in the UI at", s_denied)
ok("a refusal at least reaches the timeline", len(s_denied) >= 1, str(s_denied))


# =============================================================================================
print("\n" + "=" * 78)
print(f"PASS {len(PASS)}   FAIL {len(FAIL)}")
for f in FAIL:
    print("  FAIL " + f)
print(f"\nprojects on this Hub now: {project_count()} (fixtures still present; run --teardown)")
_, jobs = api("GET", f"{A}/jobs")
jobs = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs") or []
print(f"jobs in the fixture project: {len(jobs)} enabled={sum(1 for j in jobs if j.get('enabled'))}")
