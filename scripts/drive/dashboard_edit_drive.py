"""Acceptance drive for `change-a-dashboard-by-asking` (spdoc-8b630b916bcf).

The change's `acceptance-drive` task (CDA-1), written and recorded failing on today's code before
anything of the feature is built; the change's last task (`run-acceptance-drive`) runs it green.
It checks every acceptance criterion of the document, each as its own check, and ends by printing
one line per check in the drive-baseline form the Hub reads:

    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>

A missing route or tool never stops a check early: each check reads the dashboards before and
after, and judges what the Hub answered, so on today's code every check reaches its assertion and
fails there, its detail naming the missing tool (`edit_dashboard`, `undo_dashboard`,
`run_dashboard`) or route. An agent turn whose tool the checkout does not declare is not spent.

It starts its own Hub from this checkout on a free port with a throwaway database and bootstrap key
(never :8000, never the shared trial :8010), with the real `claude` on PATH; every agent is bound to
Haiku, one agent per conversation that must not see another's (so "the dashboard", unnamed, cannot
be resolved from an earlier turn). Two projects, seeded with slice first-dashboard's helpers
(scripts/drive/dashboards_drive.py: the Hub, the seed, turns and their tool calls).

    py -3.11 scripts/drive/dashboard_edit_drive.py [--no-browser]

Exit 0 only when every check passes. AW_DRIVE_KEEP=1 leaves the Hub running.

THE CONTRACT this drive assumes (the document's design; a build that names something differently
changes this file, not the spec). Slice 1's routes, panels and tools as in dashboards_drive.py, and:
  View (read, list summary, run, edit responses) gains `version` (int, 1 when created),
  `edited_by` (agent or `operator`), `edited_at` (ISO 8601), `can_undo` (bool).
  PATCH /agent-actions/dashboards/{id} {"base_version", "operations": [...]} -> 200 view at
        version+1. Operations: add_panel {panel, position}, remove_panel {panel_id}, change_panel
        {panel_id, title?, query?, kind?}, move_panel {panel_id, position}, rename {name},
        set_description {description}.
  POST  /agent-actions/dashboards/{id}/undo, POST /projects/{pid}/dashboards/{id}/undo -> view at
        version+1; 409 {"detail": {"code": "nothing_to_undo"}}
  GET   /agent-actions/dashboards/{id}/run -> slice 1's run result
  POST  /agent-actions/dashboards (save) and PUT /projects/{pid}/dashboards/{id} take base_version.
  Refusals: 409 stale_version {message, current: <view>}; 422 operation_refused {operation_index
        (zero-based), reason: invalid_chart_kind|not_queryable|invalid_panel|unknown_panel};
        409 dashboard_name_taken; 404 dashboard_not_found for another project's dashboard.
  Table `dashboard_versions` (dashboard_id primary key, project_id, ...): one kept version.
  Agent tools: edit_dashboard(dashboard_id, base_version, operations), undo_dashboard(dashboard_id),
        run_dashboard(dashboard_id); save_dashboard gains base_version.

The screen's test ids added by the screen task (slice 1's are in dashboards_drive.py):
  dashboard-undo                     on the open dashboard only when it can be undone
  dashboard-edited-by                who last edited it and when (data-edited-at, ISO 8601); absent
                                     on a dashboard never edited
  dashboard-ask-to-change            opens the agent picker
  dashboard-ask-agent                one per agent in the picker (data-agent); choosing one opens its
                                     conversation with the composer (`textarea.composer-textarea`,
                                     sent by the button labelled "Send message") holding
                                     `Change the dashboard "<name>" (<id>): `
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dashboards_drive as dd  # noqa: E402 -- slice first-dashboard's helpers
from dashboards_drive import (  # noqa: E402
    CHECKS, Check, api, dashboards_list, detail_code, p, panels_of_run, parsed_result, poll, ro,
    rows_of, run_check, said, tool_calls,
)

# This drive's own scratch, set on the helpers' module so its Hub, database and seed use it.
dd.TMP = dd.TMP.parent.parent / "drive-dashboard-edit" / dd.STAMP
dd.DB = dd.TMP / "hub" / "agentweave.db"
dd.SHOTS = dd.TMP / "shots"
TMP, DB, SHOTS, STAMP, HAIKU = dd.TMP, dd.DB, dd.SHOTS, dd.STAMP, dd.HAIKU

NEW_TOOLS = ("edit_dashboard", "undo_dashboard", "run_dashboard")
TOOLS = NEW_TOOLS + ("save_dashboard", "list_dashboards", "read_dashboard")
ANALYST = "analyst"  # the edits the criteria name an agent for
#: One agent per conversation that must start knowing no dashboard.
AGENTS = (ANALYST, "fixer", "runner", "amb-both", "amb-none", "amb-unnamed", "picker")
PREFIX = 'Change the dashboard "{name}" ({id}): '


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


# ----------------------------------------------------------------------------------- the checkout


def contract_in_checkout() -> Dict[str, Any]:
    """What this checkout declares: the dashboard tools and their parameters, and its routes."""
    code = (
        "import inspect, json\n"
        "from hub import mcp_server as m\n"
        "from hub.main import app\n"
        f"tools = {list(TOOLS)!r}\n"
        "out = {'tools': {t: sorted(inspect.signature(m._CALLABLE_TOOLS[t]).parameters)\n"
        "                 for t in tools if t in m._CALLABLE_TOOLS},\n"
        "       'routes': sorted({m2 + ' ' + r.path for r in app.routes if 'dashboard' in getattr(r, 'path', '')\n"
        "                         for m2 in (getattr(r, 'methods', None) or ())})}\n"
        "print('CONTRACT ' + json.dumps(out))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP / 'contract.db').as_posix()}"
    r = subprocess.run(["py", "-3.11", "-c", code], cwd=str(dd.REPO / "hub"), env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("CONTRACT ")]
    if not line:
        raise RuntimeError("could not read the checkout's tools and routes: " + (r.stderr or r.stdout)[-800:])
    return json.loads(line[-1][len("CONTRACT "):])


# ------------------------------------------------------------------------------- agent-plane calls


def hold(pid: str, agent: str) -> Tuple[str, str]:
    """A running run of *agent*, as the Hub tests seed one; answers its id and credential."""
    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = "run-dedit-" + secrets.token_hex(4)
    dd.rw([("insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
            "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
            (run_id, pid, agent, dd.ts(now()), hashlib.sha256(token.encode()).hexdigest()))])
    return run_id, token


def as_agent(pid: str, agent: str, method: str, path: str, body: Any = None) -> Tuple[int, Any]:
    """One agent-plane call as *agent*, with a credential that lives for the call."""
    run_id, token = hold(pid, agent)
    try:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            dd.HUB + "/api/v1" + path, data,
            {"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:8000]
            try:
                return exc.code, json.loads(text)
            except ValueError:
                return exc.code, text
    finally:
        dd.rw([("update runs set status='completed', ended_at=? where id=?", (dd.ts(now()), run_id))])


def patch(pid: str, dash_id: str, base: Any, operations: List[Dict[str, Any]], agent: str = ANALYST
          ) -> Tuple[int, Any]:
    return as_agent(pid, agent, "PATCH", f"/agent-actions/dashboards/{dash_id}",
                    {"base_version": base, "operations": operations})


# ---------------------------------------------------------------------------------- the dashboards


def create(pid: str, name: str, panels: List[Tuple[str, str, str]], description: str = "") -> Dict[str, Any]:
    code, out = api("POST", f"/projects/{pid}/dashboards", {
        "name": name, "description": description or f"seeded by the edit drive: {name}",
        "panels": [{"title": t, "query": q, "kind": k} for t, q, k in panels]})
    if code not in (200, 201) or not isinstance(out, dict):
        raise SystemExit(f"setup error: dashboard {name}: {said(code, out)}")
    return out


def read(pid: str, dash_id: str) -> Dict[str, Any]:
    code, out = api("GET", f"/projects/{pid}/dashboards/{dash_id}")
    return out if code == 200 and isinstance(out, dict) else {}


def shape(view: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    """A dashboard's panels as (id, title, query, kind), in order."""
    return [(x.get("id"), x.get("title"), x.get("query"), x.get("kind")) for x in view.get("panels") or []]


def print_of(view: Dict[str, Any]) -> Tuple[Any, ...]:
    """Everything an edit could change, version included."""
    return (view.get("version"), view.get("name"), view.get("description"), tuple(shape(view)),
            view.get("updated_at"), view.get("edited_at"))


def everything(pid: str) -> Dict[str, Tuple[Any, ...]]:
    """Every dashboard of the project, read whole, by id."""
    _, listed = dashboards_list(pid)
    return {d["id"]: print_of(read(pid, d["id"])) for d in listed if d.get("id")}


def view_fields(view: Dict[str, Any]) -> str:
    return (f"version={view.get('version')!r} edited_by={view.get('edited_by')!r} "
            f"edited_at={view.get('edited_at')!r} can_undo={view.get('can_undo')!r}")


def detail_of(out: Any) -> Dict[str, Any]:
    """A refusal's `detail` object, or {} when it is not one (a 404 or 405 says a string)."""
    detail = out.get("detail") if isinstance(out, dict) else None
    return detail if isinstance(detail, dict) else {}


def missing(contract: Dict[str, Any], *names: str) -> List[str]:
    return [n for n in names if n not in contract["tools"]]


def lacking(gone: List[str]) -> str:
    return f"tools missing from the checkout: {gone}; " if gone else ""


# --------------------------------------------------------------------------------------- the turns


def turn(pid: str, agent: str, message: str) -> Dict[str, Any]:
    """One real Haiku turn of *agent*. Ends with the run, or as soon as it asks the operator a
    question (which is then declined, so the turn ends rather than waiting). Answers the run id,
    its start and end, its reply text and any question it asked."""
    started = now()
    code, res = api("POST", f"/projects/{pid}/agent/trigger", {"agent": agent, "message": message})
    out: Dict[str, Any] = {"run_id": None, "started": started, "ended": None, "reply": "", "questions": []}
    if code >= 300 or not isinstance(res, dict) or not res.get("run_id"):
        p(f"  {agent}'s turn did not start: {said(code, res)}")
        return out
    run_id = out["run_id"] = res["run_id"]
    live = ("running", "queued", "starting", "pending")

    def done() -> bool:
        asked = ro("select id, question from questions where project_id=? and from_agent=? and answered=0 "
                   "and created_at >= ?", (pid, agent, dd.ts(started - timedelta(seconds=5))))
        for qid, text in asked:
            out["questions"].append(text)
            api("POST", f"/projects/{pid}/questions/{qid}/decline")
        return ro("select status from runs where id=?", (run_id,))[0][0] not in live

    poll(done, 600, 3)
    out["ended"] = now()
    time.sleep(3)  # the last spans and output land after the run row moves
    out["reply"] = "\n".join(c for k, c in ro(
        "select kind, content from agent_outputs where run_id=? order by sequence", (run_id,))
        if k not in ("tool_use", "tool_result") and c)
    status = ro("select status from runs where id=?", (run_id,))[0][0]
    p(f"  {agent}'s turn {run_id} ended {status}; asked {len(out['questions'])}; reply {out['reply'][-200:]!r}")
    return out


def asks_which(t: Dict[str, Any]) -> bool:
    """The turn asked the operator which dashboard: through ask_user, or in its reply."""
    text = (" ".join(t["questions"]) + "\n" + t["reply"]).lower()
    return bool(t["run_id"]) and "?" in text and "dashboard" in text and (
        bool(t["questions"]) or "which" in text)


def writes(run_id: Optional[str]) -> int:
    """The run's dashboard write calls, less those the Hub refused.

    A refused call (the call command's `{"ok": false, ...}`, as the write guard after an
    unanswered question answers) wrote nothing, and the criterion is that nothing changed; any
    other call is counted, since a result with output around it cannot be read as a view.
    """
    def refused(call: Dict[str, Any]) -> bool:
        return re.search(r'"ok":\s*false', str(call.get("result") or "")) is not None
    return sum(not refused(c) for n in ("edit_dashboard", "save_dashboard", "undo_dashboard")
               for c in tool_calls(run_id, n))


# ------------------------------------------------------------------------------------------ queries

Q_TASKS = "select count(*) as tasks from tasks"
Q_STATUS = "select status, count(*) as n from tasks group by status order by status"
Q_TITLES = "select title, status from tasks order by title"
Q_DAYS = "select date(started_at) as day, count(*) as runs from runs group by day order by day"
Q_BROKEN = "select no_such_column from tasks"


class Drive:
    def __init__(self, browser: bool) -> None:
        self.browser = browser
        self.hub = dd.SubprocessHub()
        self.a = self.b = ""
        self.contract: Dict[str, Any] = {"tools": {}, "routes": []}
        self.d: Dict[str, Dict[str, Any]] = {}  # the seeded dashboards, by role
        self.edit_turn: Dict[str, Any] = {}

    def setup(self) -> None:
        TMP.mkdir(parents=True, exist_ok=True)
        self.contract = contract_in_checkout()
        p(f"checkout declares tools {self.contract['tools']}\n  and dashboard routes {self.contract['routes']}")
        self.hub.start()
        self.a, _ = dd.open_project("A")
        self.b, _ = dd.open_project("B")
        dd.seed_project("A", self.a)
        dd.seed_project("B", self.b)
        for pid, agents in ((self.a, AGENTS), (self.b, (ANALYST,))):
            code, runner = api("POST", f"/projects/{pid}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
            if code not in (200, 201):
                raise SystemExit(f"setup error: runner: {said(code, runner)}")
            for name in agents:
                code, out = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner["id"]})
                if code not in (200, 201):
                    raise SystemExit(f"setup error: agent {name}: {said(code, out)}")
        three = [("Tasks", Q_TASKS, "number"), ("By status", Q_STATUS, "bar"), ("Titles", Q_TITLES, "table")]
        seeds = {
            "weekly": (f"Weekly delivery {STAMP}", three),
            "cost": (f"Cost watch {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "review": (f"Review load {STAMP}", [("By status", Q_STATUS, "bar")]),
            "north": (f"Team health North {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "south": (f"Team health South {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "four": (f"Four panels {STAMP}", three + [("Runs by day", Q_DAYS, "line")]),
            "broken": (f"Broken board {STAMP}", [("Tasks", Q_TASKS, "number"), ("Open work", Q_BROKEN, "table"),
                                                 ("By status", Q_STATUS, "bar")]),
            "never": (f"Never edited {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "undo": (f"Undo board {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "restart": (f"Restart board {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "stale": (f"Stale board {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "atomic": (f"Atomic board {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "ask": (f"Ask board {STAMP}", [("Tasks", Q_TASKS, "number")]),
            "history": (f"History board {STAMP}", [("Tasks", Q_TASKS, "number")]),
        }
        for role, (name, panels) in seeds.items():
            self.d[role] = create(self.a, name, panels)
        self.d["b"] = create(self.b, f"B board {STAMP}", [("Tasks", Q_TASKS, "number")])
        p(f"project A {self.a}, project B {self.b}; {len(self.d)} dashboards; agents {AGENTS} on {HAIKU}")

    def id(self, role: str) -> str:
        return self.d[role]["id"]

    def name(self, role: str) -> str:
        return self.d[role]["name"]

    # -- FR-1

    def ac_edit_in_place(self, c: Check) -> None:
        dash = self.id("weekly")
        before_all = everything(self.a)
        before = read(self.a, dash)
        gone = missing(self.contract, "edit_dashboard", "list_dashboards")
        self.edit_turn = t = turn(self.a, ANALYST, (
            f"Add a fourth panel to the dashboard \"{self.name('weekly')}\": titled \"Runs per agent\", kind bar, "
            "counting runs per agent. Keep the other three panels as they are.")) if not gone else {}
        _, listed = dashboards_list(self.a)
        same_name = [d for d in listed if d.get("name") == self.name("weekly")]
        after = read(self.a, dash)
        c.judge("the project still lists one such dashboard, with the same identifier, and no more dashboards",
                len(same_name) == 1 and same_name[0].get("id") == dash and len(listed) == len(before_all),
                lacking(gone) + f"{len(before_all)} dashboards before, {len(listed)} after; named alike {len(same_name)}")
        c.judge("now with four panels, the first three unchanged",
                len(shape(after)) == 4 and shape(after)[:3] == shape(before),
                lacking(gone) + f"panels before {len(shape(before))}, after {len(shape(after))}")
        edited_at = parse_ts(after.get("edited_at"))
        in_turn = bool(t.get("ended")) and edited_at is not None and \
            t["started"] - timedelta(seconds=5) <= edited_at <= t["ended"] + timedelta(seconds=5)
        c.judge("edited-by names the agent and edited-at the time of its turn",
                after.get("edited_by") == ANALYST and in_turn,
                lacking(gone) + view_fields(after) + f"; turn {t.get('started')}..{t.get('ended')}")
        c.judge("the agent edited it with edit_dashboard, not a second save",
                bool(tool_calls(t.get("run_id"), "edit_dashboard")),
                lacking(gone) + f"edit_dashboard calls {len(tool_calls(t.get('run_id'), 'edit_dashboard'))}, "
                f"save_dashboard calls {len(tool_calls(t.get('run_id'), 'save_dashboard'))}")

    # -- FR-2

    def ac_by_name(self, c: Check) -> None:
        cost, review = self.id("cost"), self.id("review")
        before_cost, before_review = print_of(read(self.a, cost)), read(self.a, review)
        gone = missing(self.contract, "edit_dashboard", "list_dashboards")
        if not gone:
            turn(self.a, ANALYST, f"In the dashboard \"{self.name('review')}\", add a panel titled \"Open tasks\", "
                                  "kind number, counting tasks that are not approved.")
        after_review = read(self.a, review)
        c.judge("the dashboard named changed, and its version moved",
                len(shape(after_review)) == 2 and isinstance(after_review.get("version"), int)
                and after_review.get("version") > (before_review.get("version") or 0),
                lacking(gone) + f"panels {len(shape(before_review))} -> {len(shape(after_review))}; "
                f"{view_fields(before_review)} -> {view_fields(after_review)}")
        c.judge("the other did not", print_of(read(self.a, cost)) == before_cost, lacking(gone) + "cost watch compared whole")

    def ac_ambiguous(self, c: Check) -> None:
        gone = missing(self.contract, "edit_dashboard", "list_dashboards")
        asks = {
            "amb-both": "Add a panel counting runs to the team health dashboard.",
            "amb-none": "Add a panel counting runs to the Inventory dashboard.",
            "amb-unnamed": "Add a panel counting runs to the dashboard.",
        }
        for agent, ask in asks.items():
            before = everything(self.a)
            t = turn(self.a, agent, ask) if not gone else {"run_id": None, "questions": [], "reply": ""}
            after = everything(self.a)
            c.judge(f"{agent}: the agent asks which dashboard", asks_which(t),
                    lacking(gone) + f"questions {t['questions']}; reply {t['reply'][-300:]!r}")
            c.judge(f"{agent}: no dashboard changed and none was created",
                    before == after and writes(t["run_id"]) == 0,
                    lacking(gone) + f"{len(before)} dashboards before, {len(after)} after; "
                    f"changed {[k for k in before if before[k] != after.get(k)]}; write calls {writes(t['run_id'])}")

    # -- FR-3

    def ac_keep_the_rest(self, c: Check) -> None:
        dash = self.id("four")
        before = read(self.a, dash)
        gone = missing(self.contract, "edit_dashboard")
        if not gone:
            turn(self.a, ANALYST, f"In the dashboard \"{self.name('four')}\", change the panel \"Runs by day\" "
                                  "to a bar chart. Change nothing else.")
        after = read(self.a, dash)
        old, new = shape(before), shape(after)
        changed = len(new) == 4 and new[3][3] == "bar" and new[3][:3] == old[3][:3]
        c.judge("the asked panel's kind changed", changed, lacking(gone) + f"last panel {old[3:]} -> {new[3:]}")
        c.judge("the other three panels (id, title, query, kind, position), the name and description are as before",
                new[:3] == old[:3] and (after.get("name"), after.get("description"))
                == (before.get("name"), before.get("description")) and after.get("version") != before.get("version"),
                lacking(gone) + f"{old[:3]} vs {new[:3]}; {view_fields(after)}")

    # -- FR-4

    def ac_all_or_nothing(self, c: Check) -> None:
        dash = self.id("atomic")
        before = read(self.a, dash)
        base = before.get("version")
        code, out = patch(self.a, dash, base, [
            {"op": "add_panel", "panel": {"title": "Runs", "query": "select count(*) as n from runs", "kind": "number"},
             "position": None},
            {"op": "change_panel", "panel_id": shape(before)[0][0], "kind": "pie"}])
        detail = detail_of(out)
        c.judge("an add then a chart kind outside the set is refused naming operation 1, invalid_chart_kind",
                code == 422 and detail.get("code") == "operation_refused"
                and detail.get("operation_index") == 1 and detail.get("reason") == "invalid_chart_kind",
                said(code, out))
        c.judge("and the dashboard, its version included, is unchanged", print_of(read(self.a, dash)) == print_of(before)
                and base is not None, view_fields(read(self.a, dash)))
        code, out = patch(self.a, dash, base, [{"op": "rename", "name": self.name("cost")}])
        c.judge("a rename to another dashboard's name is refused as a taken name",
                code == 409 and detail_code(out) == "dashboard_name_taken", said(code, out))
        c.judge("and the dashboard is unchanged again", print_of(read(self.a, dash)) == print_of(before),
                view_fields(read(self.a, dash)))

    # -- FR-5

    def ac_stale(self, c: Check) -> None:
        dash = self.id("stale")
        v = read(self.a, dash).get("version")
        code, out = patch(self.a, dash, v, [{"op": "set_description", "description": "the other edit"}])
        newer = read(self.a, dash)
        c.judge("another edit moves the dashboard on a version", code == 200 and isinstance(v, int)
                and newer.get("version") == v + 1, said(code, out) + "; " + view_fields(newer))
        code, out = patch(self.a, dash, v, [{"op": "set_description", "description": "stale edit"}])
        current = detail_of(out).get("current")
        c.judge("an edit naming the old version is refused stale, with the current dashboard",
                code == 409 and detail_code(out) == "stale_version" and isinstance(current, dict)
                and current.get("version") == newer.get("version"), said(code, out))
        code, out = as_agent(self.a, ANALYST, "POST", "/agent-actions/dashboards", {
            "dashboard_id": dash, "base_version": v, "name": self.name("stale"), "description": "stale replace",
            "panels": [{"title": "Replaced", "query": Q_TASKS, "kind": "number"}]})
        c.judge("a whole replace naming the old version is refused stale too",
                code == 409 and detail_code(out) == "stale_version", said(code, out))
        c.judge("the newer content is intact", print_of(read(self.a, dash)) == print_of(newer)
                and newer.get("description") == "the other edit", view_fields(read(self.a, dash)))
        code, out = patch(self.a, dash, newer.get("version"), [{"op": "set_description", "description": "current edit"}])
        c.judge("an edit naming the current version is accepted",
                code == 200 and read(self.a, dash).get("description") == "current edit", said(code, out))

    # -- FR-6

    def ac_undo_none(self, c: Check) -> None:
        dash = self.id("never")
        view = read(self.a, dash)
        c.judge("a dashboard never edited reads can_undo false", view.get("can_undo") is False, view_fields(view))
        code, out = api("POST", f"/projects/{self.a}/dashboards/{dash}/undo")
        c.judge("and its undo answers nothing_to_undo, changing nothing",
                code == 409 and detail_code(out) == "nothing_to_undo" and print_of(read(self.a, dash)) == print_of(view),
                said(code, out))
        if self.browser:
            offered, opened = self.with_page("light", lambda page: (
                page.wait_for_timeout(2000), page.get_by_test_id("dashboard-undo").count())[1], dash)
            c.judge("the screen offers no Undo on it", opened and offered == 0, f"opened {opened}; undo shown {offered}")

    def ac_undo(self, c: Check) -> None:
        dash = self.id("undo")
        original = read(self.a, dash)
        code, out = patch(self.a, dash, original.get("version"), [
            {"op": "add_panel", "panel": {"title": "Runs", "query": "select count(*) as n from runs", "kind": "number"},
             "position": None}])
        edited = read(self.a, dash)
        c.judge("edited once, it can be undone", code == 200 and edited.get("can_undo") is True and len(shape(edited)) == 2,
                said(code, out) + "; " + view_fields(edited))
        if self.browser:
            def press(page: Any) -> Any:
                button = page.get_by_test_id("dashboard-undo")
                if not poll(lambda: button.count(), 10, 0.5):
                    return False
                button.first.click()
                return bool(poll(lambda: len(shape(read(self.a, dash))) == 1, 20, 0.5))
            pressed, opened = self.with_page("dark", press, dash)
            p(f"  Undo pressed on the screen: opened {opened}, restored {pressed}")
        else:
            api("POST", f"/projects/{self.a}/dashboards/{dash}/undo")
        undone = read(self.a, dash)
        c.judge("Undo restores the panels before the edit, at a higher version",
                shape(undone) == shape(original) and isinstance(undone.get("version"), int)
                and undone.get("version") > (edited.get("version") or 0), view_fields(undone) + f"; panels {shape(undone)}")
        code, out = api("POST", f"/projects/{self.a}/dashboards/{dash}/undo")
        c.judge("and Undo then restores the edited panels", code == 200 and shape(read(self.a, dash)) == shape(edited),
                said(code, out))

    def ac_undo_survives_restart(self, c: Check) -> None:
        dash = self.id("restart")
        original = read(self.a, dash)
        code, out = patch(self.a, dash, original.get("version"), [
            {"op": "change_panel", "panel_id": shape(original)[0][0], "title": "Renamed by the edit"}])
        edited_ok = code == 200
        self.hub.restart()
        code2, out2 = api("POST", f"/projects/{self.a}/dashboards/{dash}/undo")
        c.judge("after a Hub restart Undo restores the earlier version",
                edited_ok and code2 == 200 and shape(read(self.a, dash)) == shape(original),
                f"edit {said(code, out, 150)}; undo {said(code2, out2, 150)}")

    # -- FR-7

    def ac_run_for_agent(self, c: Check) -> None:
        dash = self.id("broken")
        code, screen = api("GET", f"/projects/{self.a}/dashboards/{dash}/run")
        want = [(x.get("id"), bool(x.get("error")), rows_of(x)) for x in panels_of_run(screen)]
        p(f"  the screen's run: {[(i, e, len(r)) for i, e, r in want]}")
        acode, agent_run = as_agent(self.a, "runner", "GET", f"/agent-actions/dashboards/{dash}/run")
        got_route = [(x.get("id"), bool(x.get("error")), rows_of(x)) for x in panels_of_run(agent_run)]
        c.judge("the agent run route answers what the screen's run does",
                code == 200 and len(want) == 3 and want[1][1] and not want[0][1] and not want[2][1]
                and acode == 200 and got_route == want, said(acode, agent_run))
        gone = missing(self.contract, "run_dashboard")
        t = turn(self.a, "runner", f"Run the dashboard \"{self.name('broken')}\" ({dash}) once with your AgentWeave "
                                   "tool run_dashboard and tell me what each panel returned. Change nothing.") \
            if not gone else {"run_id": None}
        calls = tool_calls(t["run_id"], "run_dashboard")
        result = parsed_result(calls[-1]["result"]) if calls else None
        got_tool = [(x.get("id"), bool(x.get("error")), rows_of(x)) for x in panels_of_run(result)]
        c.judge("through run_dashboard the agent receives the broken panel's error and the other two panels' rows",
                bool(calls) and got_tool == want,
                lacking(gone) + f"calls {len(calls)}; got {[(i, e, len(r)) for i, e, r in got_tool]}")

    def ac_repair(self, c: Check) -> None:
        dash = self.id("broken")
        before = read(self.a, dash)
        gone = missing(self.contract, "run_dashboard", "edit_dashboard")
        t = turn(self.a, "fixer", f"The panel \"Open work\" on the dashboard \"{self.name('broken')}\" is broken. "
                                  "Fix it so it lists the tasks' titles and statuses.") if not gone else {"run_id": None}
        after = read(self.a, dash)
        old, new = shape(before), shape(after)
        c.judge("the broken panel's query changed, its id, title and kind kept",
                len(new) == 3 and new[1][2] != old[1][2] and (new[1][0], new[1][1], new[1][3]) == (old[1][0], old[1][1], old[1][3]),
                lacking(gone) + f"{old[1:2]} -> {new[1:2]}")
        c.judge("the other two panels are unchanged", len(new) == 3 and (new[0], new[2]) == (old[0], old[2]),
                lacking(gone) + f"{[old[0], old[2]]} vs {new[0::2]}")
        code, run = api("GET", f"/projects/{self.a}/dashboards/{dash}/run")
        panels = panels_of_run(run)
        c.judge("the panel draws on the next run: no error, no warning, rows",
                len(panels) == 3 and not panels[1].get("error") and not panels[1].get("warning") and rows_of(panels[1]),
                lacking(gone) + said(code, run, 300) + f"; run_dashboard calls {len(tool_calls(t['run_id'], 'run_dashboard'))}")
        if self.browser:
            def drawn(page: Any) -> Any:
                panel = page.get_by_test_id("dashboard-panel").nth(1)
                poll(lambda: panel.count(), 20, 0.5)
                page.wait_for_timeout(1500)
                return bool(panel.locator("svg, table, [data-testid=dashboard-number]").count()) and not \
                    panel.locator("[data-testid=dashboard-panel-error], [data-testid=dashboard-panel-warning]").count()
            ok, opened = self.with_page("dark", drawn, dash, shot="repaired")
            c.judge("and on the screen the panel draws", opened and ok, f"opened {opened}")

    # -- FR-8

    def ac_edit_boundary(self, c: Check) -> None:
        mine, theirs = self.id("atomic"), self.id("b")
        before_a, before_b = print_of(read(self.a, mine)), print_of(read(self.b, theirs))
        base = read(self.a, mine).get("version")
        code, out = patch(self.a, mine, base, [
            {"op": "change_panel", "panel_id": shape(read(self.a, mine))[0][0], "query": "select * from api_keys"}])
        detail = detail_of(out)
        c.judge("an edit naming credentials is refused not_queryable",
                code == 422 and detail.get("reason") == "not_queryable", said(code, out))
        b_version = read(self.b, theirs).get("version")
        for label, method, path, body in (
                ("edit", "PATCH", f"/agent-actions/dashboards/{theirs}",
                 {"base_version": b_version, "operations": [{"op": "set_description", "description": "from A"}]}),
                ("undo", "POST", f"/agent-actions/dashboards/{theirs}/undo", None),
                ("run", "GET", f"/agent-actions/dashboards/{theirs}/run", None)):
            code, out = as_agent(self.a, ANALYST, method, path, body)
            c.judge(f"project A's agent naming B's dashboard to {label} is not found",
                    code == 404 and detail_code(out) == "dashboard_not_found", said(code, out))
        c.judge("both dashboards are unchanged",
                print_of(read(self.a, mine)) == before_a and print_of(read(self.b, theirs)) == before_b, "")

    # -- FR-9

    def versions(self, where: str, arg: str) -> Any:
        try:
            return ro(f"select count(*) from dashboard_versions where {where}=?", (arg,))[0][0]
        except sqlite3.OperationalError as exc:
            return f"({exc})"

    def ac_history_delete(self, c: Check) -> None:
        dash = self.id("history")
        code, out = patch(self.a, dash, read(self.a, dash).get("version"),
                          [{"op": "set_description", "description": "edited, so a version is kept"}])
        kept = self.versions("dashboard_id", dash)
        code_del, _ = api("DELETE", f"/projects/{self.a}/dashboards/{dash}")
        c.judge("deleting an edited dashboard removes its kept version",
                code == 200 and kept == 1 and code_del in (200, 204) and self.versions("dashboard_id", dash) == 0,
                f"edit {said(code, out, 150)}; kept {kept}; delete {code_del}; after {self.versions('dashboard_id', dash)}")
        theirs = self.id("b")
        code, out = patch(self.b, theirs, read(self.b, theirs).get("version"),
                          [{"op": "set_description", "description": "edited in B"}])
        kept = self.versions("project_id", self.b)
        code_del, _ = api("DELETE", f"/projects/{self.b}")
        c.judge("deleting the project removes its dashboards' kept versions",
                code == 200 and kept == 1 and code_del in (200, 204) and self.versions("project_id", self.b) == 0,
                f"edit {said(code, out, 150)}; kept {kept}; delete {code_del}; after {self.versions('project_id', self.b)}")

    # -- FR-10

    def ac_edited_by(self, c: Check) -> None:
        dash = self.id("weekly")
        view = read(self.a, dash)
        c.judge("the view names the agent that last edited it and when",
                view.get("edited_by") == ANALYST and parse_ts(view.get("edited_at")) is not None,
                lacking(missing(self.contract, "edit_dashboard")) + view_fields(view))
        if not self.browser:
            return
        for scheme in ("light", "dark"):
            def line(page: Any) -> Any:
                el = page.get_by_test_id("dashboard-edited-by")
                if not poll(lambda: el.count(), 10, 0.5):
                    return None
                return el.first.inner_text(), el.first.get_attribute("data-edited-at")
            shown, opened = self.with_page(scheme, line, dash, shot=f"edited-by-{scheme}")
            c.judge(f"in the {scheme} theme the screen shows the agent's name and the edit time (screenshot for the operator)",
                    opened and bool(shown) and ANALYST in shown[0] and parse_ts(shown[1]) is not None,
                    f"opened {opened}; shown {shown}; shot {SHOTS / f'edited-by-{scheme}.png'}")

    # -- FR-11

    def ac_ask_to_change(self, c: Check) -> None:
        dash, name = self.id("ask"), self.name("ask")
        if not self.browser:
            c.judge("Ask to change is driven in the browser", False, "--no-browser given")
            return
        before = everything(self.a)
        prefix = PREFIX.format(name=name, id=dash)
        state: Dict[str, Any] = {}

        def ask(page: Any) -> Any:
            button = page.get_by_test_id("dashboard-ask-to-change")
            if not poll(lambda: button.count(), 10, 0.5):
                state["step"] = "no dashboard-ask-to-change on the open dashboard"
                return False
            button.first.click()
            choice = page.locator("[data-testid=dashboard-ask-agent][data-agent='picker']")
            if not poll(lambda: choice.count(), 10, 0.5):
                state["step"] = "no dashboard-ask-agent for 'picker' in the picker"
                return False
            clicked = now()
            choice.first.click()
            box = page.locator("textarea.composer-textarea")
            poll(lambda: box.count() and box.first.input_value(), 20, 0.5)
            state["composer"] = box.first.input_value() if box.count() else None
            page.wait_for_timeout(3000)
            state["sent_early"] = ro("select count(*) from runs where project_id=? and agent='picker'", (self.a,))[0][0] \
                + ro("select count(*) from messages where project_id=? and recipient='picker'", (self.a,))[0][0]
            box.first.click()
            box.first.press("End")
            box.first.type("add a panel of runs per day")
            page.get_by_label("Send message").first.click()
            run = poll(lambda: ro("select id from runs where project_id=? and agent='picker' and started_at >= ?",
                                  (self.a, dd.ts(clicked - timedelta(seconds=5)))), 60, 1)
            state["run_id"] = run[0][0] if run else None
            if state["run_id"]:
                poll(lambda: ro("select status from runs where id=?", (state["run_id"],))[0][0]
                     not in ("running", "queued", "starting", "pending"), 600, 3)
                time.sleep(3)
            return True

        ok, opened = self.with_page("light", ask, dash, shot="ask-to-change")
        after = everything(self.a)
        c.judge("the agent's conversation opened with the dashboard's name and id in the composer",
                opened and ok and isinstance(state.get("composer"), str) and state["composer"].startswith(prefix),
                f"opened {opened}; {state.get('step', '')}; composer {state.get('composer')!r}; want {prefix!r}")
        c.judge("nothing was sent before the operator sent it", ok and state.get("sent_early") == 0,
                f"runs+messages to picker before Send: {state.get('sent_early')}")
        moved = [k for k in before if before[k] != after.get(k)]
        c.judge("after the turn that dashboard, and no other, changed",
                bool(state.get("run_id")) and moved == [dash] and len(after) == len(before),
                f"turn {state.get('run_id')}; changed {moved}; {len(before)} -> {len(after)} dashboards")

    # -- browser

    def with_page(self, scheme: str, fn: Any, dash: str, shot: str = "") -> Tuple[Any, bool]:
        """Opens *dash* on the Dashboards screen and answers (fn(page), opened)."""
        from playwright.sync_api import sync_playwright

        SHOTS.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            chromium = pw.chromium.launch()
            ctx = chromium.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
            ctx.add_init_script(
                "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
                "localStorage.setItem('agentweave-selected-project', %r);"
                "localStorage.setItem('agentweave-theme', %r);" % (dd.KEY, dd.HUB, self.a, scheme))
            page = ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            page.goto(f"{dd.HUB}/?project={self.a}&tab=dashboards", wait_until="domcontentloaded")
            row = page.locator(f"[data-testid=dashboard-row][data-dashboard-id='{dash}']")
            opened = False
            if poll(lambda: row.count(), 20, 0.5):
                row.first.click()
                view = page.locator(f"[data-testid=dashboard-view][data-dashboard-id='{dash}']")
                opened = bool(poll(lambda: view.count(), 20, 0.5))
            result = fn(page) if opened else None
            if shot:
                page.screenshot(path=str(SHOTS / f"{shot}.png"), full_page=True)
                p(f"  screenshot {SHOTS / f'{shot}.png'}")
            chromium.close()
        return result, opened

    # -- order

    def run(self) -> None:
        try:
            self.setup()
            # Agent turns first, each agent's conversation knowing only what its own asks name.
            run_check("ac-run-for-agent", self.ac_run_for_agent)
            run_check("ac-repair", self.ac_repair)
            run_check("ac-edit-in-place", self.ac_edit_in_place)
            run_check("ac-edited-by", self.ac_edited_by)
            run_check("ac-by-name", self.ac_by_name)
            run_check("ac-keep-the-rest", self.ac_keep_the_rest)
            run_check("ac-ask-to-change", self.ac_ask_to_change)
            run_check("ac-all-or-nothing", self.ac_all_or_nothing)
            run_check("ac-stale", self.ac_stale)
            run_check("ac-undo-none", self.ac_undo_none)
            run_check("ac-undo", self.ac_undo)
            run_check("ac-edit-boundary", self.ac_edit_boundary)
            run_check("ac-undo-survives-restart", self.ac_undo_survives_restart)
            run_check("ac-history-delete", self.ac_history_delete)
            # Last: an agent that guesses instead of asking edits some dashboard, and a check run
            # after it would read that edit as its own failure (ac-edit-in-place did, CDA-4).
            run_check("ac-ambiguous", self.ac_ambiguous)
        finally:
            if os.environ.get("AW_DRIVE_KEEP"):
                p(f"AW_DRIVE_KEEP: Hub left on {dd.HUB}, key {dd.KEY}, database {DB}")
            else:
                self.hub.stop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    p(f"dashboard edit drive {STAMP}; scratch {TMP}")
    Drive(browser=not args.no_browser).run()

    p("\n== drive baseline")
    for key, check in CHECKS.items():
        failed = check.reached and not check.ok
        detail = "passed" if check.ok and check.reached else ("; ".join(check.details) or "no detail")
        p(f"check {key}: reached={'yes' if check.reached else 'no'} "
          f"failed_at_assertion={'yes' if failed else 'no'} -- {detail[:700]}")
    bad = [k for k, ch in CHECKS.items() if not (ch.reached and ch.ok)]
    p(f"\n{len(CHECKS) - len(bad)} of {len(CHECKS)} checks pass" + (f"; failing: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
