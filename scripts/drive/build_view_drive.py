"""Acceptance drive for `a-build-view-showing-every-task-and-run-of-a-build` (BVSET-1), 2026-11-17:
ac-address, ac-totals, ac-timeline, ac-fold-checks-loop, ac-trace, ac-open-from-drawer and ac-live,
written failing first, before the view is wired (BVSET-2 reads, BVSET-3 wires). BVSET-3 runs it
green, and fixes only the drive where the wiring legitimately renamed something.

Where the real builds come from. The criteria ask for a real finished two-pass build, a task the
mender touched and a task bounced by the landing checks four times in a row. The trial Hub's
database holds none of those (queried 2026-11-17: 115 drive-made builds, no mender run, no checks
loop); the project's real history does. So by default the drive takes a consistent snapshot of a
source database (SQLite's backup API on a `mode=ro` connection, the way `.claude/reference/hubs.md`
allows -- the source is never written, and no Hub serving it is called), makes the copy inert, and
starts a Hub from THIS checkout's `hub/` on the copy, on a scratch port (default :8017, never :8000;
:8010 only with --hub, below). Making it inert, on the copy only:
  - every job and manager job off, the scheduler's stored jobs dropped, undelivered input withdrawn;
  - every run still `running` ended as `interrupted` with no pid, so nothing is signalled or awaited;
  - every project re-pointed at an empty scratch directory holding a copy of its `spec/`, with no
    main branch, no checks and no PR landing, so no git, check or landing work can reach a real
    checkout;
  - a fresh operator credential the drive signs in with.
The copy and the scratch directories are deleted at the end unless --keep.

`--hub URL --db PATH --key KEY` drives an already-running Hub instead (the trial :8010 when it holds
such builds); the drive then only reads its database, and the live check adds one scratch project.

Which builds and tasks. Picked from the snapshot by the mock's own recorder
(`hub/ui/mock/record_builds.py`, read-only), which restates `work_tally`'s run set and roles and
returns the `BuildRead` the view draws; the expected timeline is `timelineOf`
(`hub/ui/src/components/builds/buildViewModel.ts`) ported below and self-tested. ac-timeline also
checks that run set against a plain SELECT of the task's runs and the runs in its stalls'
conversations, so the recorder cannot hide a run.

The page contract (the design's accessible names; BVSET-3 may rename, and then fixes the drive):
  address        `/?project=<id>&tab=spec&view=build&focus=<build>&task=<ref>&run=<run>` (ADDRESS below)
  the view       `[data-testid=build-view][data-build-id=<build>]`, section "Tasks"
  task row       button "Open runs of <ref>" (aria-expanded), row `li#build-task-<task id>`
  timeline       list "Runs of <ref>"; run button "Open trace: <Role> <n>"; folded row
                 "Show <Role> ×<n>: <detail>"; send-backs `li[data-kind=send-back]`
  trace          the drawer named "Trace", whose head names the run; "Open the conversation"
  totals         `build-runs`, `build-cost`, `build-cost-note`, `build-send-backs` test ids, and the
                 "<duration> of agent work" line
  links          "Open in its build" in the task drawer (`task-drawer-<id>`) and on Overview

ac-live spends Haiku turns: a scratch git repository opened as a project with a Haiku runner, a
Builder that builds both tasks of an approved two-task document (so the flow can start only one at a
time) and a Checker; the operator builds it as a flow at Reviewed, and the drive fires the flow
itself (its cron fires once a year). The first task is built before the view opens; the second
task's run starting and its move to completed are then timed against the view. The build is stopped
at the end.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/build-view-drive/<HHMMSS>/.

    py -3.11 scripts/drive/build_view_drive.py                        # snapshot of the real data
    py -3.11 scripts/drive/build_view_drive.py --only ac-totals,ac-trace
    py -3.11 scripts/drive/build_view_drive.py --skip-live            # no agent turns
    py -3.11 scripts/drive/build_view_drive.py --self-test            # the drive's own logic only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
STAMP = time.strftime("%H%M%S")
OUT = REPO / "testbed" / "build-view-drive" / STAMP
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-build-view" / STAMP
SOURCE_DB = pathlib.Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"
PROJECT = "proj-d85a82bf4216"
HAIKU = "claude-haiku-4-5-20251001"
ORDER = ["ac-totals", "ac-address", "ac-timeline", "ac-fold-checks-loop", "ac-trace",
         "ac-open-from-drawer", "ac-summaries-open", "ac-unpriced", "ac-no-fold-pairs", "ac-seeded", "ac-matches-mock", "ac-live"]
ADDRESS = "{hub}/?project={pid}&tab=spec&view=build&focus={build}{query}"
LIVE_LIMIT = 10.0  # seconds, FR-9
TURN_WAIT = 10 * 60

HUB = ""
KEY = ""
DB = pathlib.Path()
checks: dict[str, tuple[bool, bool, str]] = {}


class Setup(Exception):
    """The scenario could not be built: the check was not reached."""


def record(key, ok, detail, reached=True):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)
    return ok


# --------------------------------------------------------------------------- the view model, ported
# `timelineOf`, `moveOf`, `sendBackText` and the cost cell from buildViewModel.ts, so the drive
# knows what the view must draw for a recorded task without asking the view.

ROLE_LABEL = {"build": "Build", "review": "Review", "mender": "Mender", "lead": "Lead"}
REASON_CLASS = {"defect": "Defect", "broken-check": "Broken check", "evidence-only": "Evidence only",
                "flaky": "Flaky", "merge-needed": "Needs a merge", "regression": "Regression"}


def hub_ms(value):
    if not value:
        return 0
    when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return int(when.timestamp() * 1000)


def reason_class_label(value):
    if not value:
        return None
    return REASON_CLASS.get(value) or value[:1].upper() + value[1:].replace("-", " ")


def sent_back_by(by):
    if by["kind"] == "agent":
        return by["agent"]
    return "the landing checks" if by["kind"] == "checks" else "you"


def send_back_text(sb):
    reason = re.sub(r"^Sent back( as [\w-]+)?:\s*", "", sb.get("reason") or "", flags=re.I).strip()
    text = re.sub(r"\s+on check run chk-[0-9a-f]+", "", reason or (sb.get("note") or "").strip(), flags=re.I)
    return text[:1].upper() + text[1:]


def move_of(run):
    if run["status"] == "running":
        return "Working now"
    mend = run.get("mend")
    if mend:
        return {"fixed": "Fixed the stall", "gave_up": "Gave up on the stall",
                "resolved": "Stall cleared itself"}.get(mend.get("outcome"), "Looked at a stall")
    if run["status"] in ("failed", "error"):
        return "Failed"
    if run["status"] in ("stopped", "cancelled", "interrupted"):
        return "Stopped"
    if not run.get("moves"):
        return "Made no decision" if run["role"] == "review" else "Made no move"
    return {"completed": "Handed in for review", "approved": "Approved", "revision_needed": "Sent it back",
            "rejected": "Rejected it", "in_progress": "Started, not handed in",
            "under_review": "Took it for review", "assigned": "Let it go unfinished",
            "pending": "Let it go unfinished"}.get(run["moves"][-1]["to"], "Moved it")


def format_money(usd):
    return f"${round(usd):,}" if abs(usd) >= 100 else f"${usd:.2f}"


def format_cost(usd):
    return "<$0.01" if 0 < usd < 0.01 else format_money(usd)


def format_duration(seconds):
    s = max(0, round(seconds))
    if s < 60:
        return f"{s}s"
    m = s // 60
    return f"{m}m {s % 60}s" if m < 60 else f"{m // 60}h {m % 60}m"


def run_cost_text(run):
    if run.get("cost_state") == "measured" and run.get("cost_usd_micros") is not None:
        return format_cost(run["cost_usd_micros"] / 1_000_000)
    return "unpriced" if run.get("cost_state") == "unpriced" else None


def run_seconds(run):
    if not run.get("ended_at"):
        return 0
    return max(0, round((hub_ms(run["ended_at"]) - hub_ms(run["started_at"])) / 1000))


def flat_timeline(runs, send_backs):
    events = [(hub_ms(r["started_at"]), i, "run", r) for i, r in enumerate(runs)]
    events += [(hub_ms(s["at"]), len(runs) + i, "send-back", s) for i, s in enumerate(send_backs)]
    events.sort(key=lambda e: (e[0], e[1]))
    counts, flat = {}, []
    for _, _, kind, item in events:
        if kind == "run":
            counts[item["role"]] = counts.get(item["role"], 0) + 1
            flat.append({"kind": "run", "run": item, "label": f"{ROLE_LABEL[item['role']]} {counts[item['role']]}"})
        else:
            counts["sb"] = counts.get("sb", 0) + 1
            flat.append({"kind": "send-back", "sb": item, "label": f"Send-back {counts['sb']}",
                         "by": sent_back_by(item["by"]), "text": send_back_text(item)})
    return flat


def signature(item):
    if item["kind"] == "run":
        return f"run:{item['run']['role']}:{item['run']['agent']}"
    by = item["sb"]["by"]
    return f"sb:{by['kind']}:{by.get('agent', '')}:{item['sb'].get('reason_class') or ''}:{item['text']}"


def repeat_at(flat, i):
    sig = [signature(x) for x in flat]

    def times_of(period):
        times = 1
        while (i + (times + 1) * period <= len(flat)
               and all(sig[i + times * period + k] == sig[i + k] for k in range(period))):
            times += 1
        return times
    best = None
    for period in (1, 2):
        pattern = flat[i:i + period]
        if len(pattern) < period or not any(p["kind"] == "run" for p in pattern):
            continue
        if period == 2 and sig[i] == sig[i + 1]:
            continue
        times = times_of(period)
        mender = period == 1 and pattern[0]["kind"] == "run" and pattern[0]["run"]["role"] == "mender"
        if times < (2 if mender else 3):
            continue
        if not best or period * times > best[0] * best[1]:
            best = (period, times)
    return best


def timeline(runs, send_backs):
    """What the expanded task draws, in order: runs, send-backs and folded groups."""
    flat, out, i = flat_timeline(runs, send_backs), [], 0
    while i < len(flat):
        found = repeat_at(flat, i)
        if found:
            items = flat[i:i + found[0] * found[1]]
            grs = [x for x in items if x["kind"] == "run"]
            sbs = [x for x in items if x["kind"] == "send-back"]
            span = f"{grs[0]['label']} to {grs[-1]['label']}" if len(grs) > 1 else grs[0]["label"]
            if sbs:
                detail = f"{span}, each sent back by {sbs[0]['by']}"
            elif grs[0]["run"]["role"] == "mender":
                detail = "repeated mender turns, shown as one"
            else:
                detail = f"{span}, each by {grs[0]['run']['agent']}"
            out.append({"kind": "group", "label": f"{ROLE_LABEL[grs[0]['run']['role']]} ×{found[1]}",
                        "detail": detail, "items": items, "times": found[1], "send_backs": len(sbs),
                        "reason": sbs[0]["text"] if sbs and len({s["text"] for s in sbs}) == 1 else None})
            i += found[0] * found[1]
        else:
            out.append(flat[i])
            i += 1
    return out


def lines_of(items):
    """Every line, groups opened: what "expanding the row shows all lines" means."""
    return [x for it in items for x in (it["items"] if it["kind"] == "group" else [it])]


def checks_loop_group(items):
    """The first folded build/landing-checks pair repeated three or more times, with its index."""
    for n, it in enumerate(items):
        if (it["kind"] == "group" and it["send_backs"] and it["items"][0]["kind"] == "run"
                and it["items"][0]["run"]["role"] == "build" and "landing checks" in it["detail"]):
            return n, it
    return None


def self_test():
    def run(i, role="build", agent="A", minute=0, status="completed", to=None, usd=None):
        return {"id": f"r{i}", "role": role, "agent": agent, "model": "m", "status": status,
                "started_at": f"2026-11-01T10:{minute:02d}:00+00:00",
                "ended_at": f"2026-11-01T10:{minute:02d}:30+00:00", "conversation_id": "c",
                "moves": [{"from": None, "to": to}] if to else [], "mend": None,
                "cost_state": "measured" if usd is not None else "unpriced",
                "cost_usd_micros": None if usd is None else int(usd * 1e6)}

    def sb(seq, minute, kind="checks", agent=None, reason="Failed on check run chk-ab12: lint", cls=None):
        by = {"kind": kind, **({"agent": agent} if agent else {})}
        return {"sequence": seq, "at": f"2026-11-01T10:{minute:02d}:40+00:00", "to": "revision_needed",
                "by": by, "reason_class": cls, "reason": reason, "note": ""}

    # ac-fold-checks-loop: Build 1..4 each bounced by the checks for one reason, then Build 5 passes.
    runs = [run(i, minute=i * 2, to="completed", usd=0.5) for i in range(1, 6)]
    sbs = [sb(i, i * 2, reason=f"Sent back: failed on check run chk-{i:04x}: lint") for i in range(1, 5)]
    folded = timeline(runs, sbs)
    group = checks_loop_group(folded)
    # ac-timeline's shape: build, defect send-back by Q, build, review approves, mender once.
    two_pass = timeline([run(1, to="completed"), run(2, to="completed", minute=4),
                         run(3, role="review", agent="Q", minute=6, to="approved"),
                         run(4, role="mender", agent="mender", minute=8)],
                        [sb(1, 2, kind="agent", agent="Q", reason="Sent back as defect: x is wrong", cls="defect")])
    cases = [
        (len(folded), 2),
        (group and group[1]["label"], "Build ×4"),
        (group and group[1]["detail"], "Build 1 to Build 4, each sent back by the landing checks"),
        (group and group[1]["reason"], "Failed: lint"),
        (group and len(group[1]["items"]), 8),
        (folded[1]["kind"] == "run" and folded[1]["label"], "Build 5"),
        ([x["label"] for x in lines_of(folded)][:3], ["Build 1", "Send-back 1", "Build 2"]),
        ([x["label"] for x in two_pass], ["Build 1", "Send-back 1", "Build 2", "Review 1", "Mender 1"]),
        (two_pass[1]["by"], "Q"),
        (two_pass[1]["text"], "X is wrong"),
        # ac-no-fold-pairs: two builds in a row by one agent stay two lines.
        ([x["kind"] for x in timeline([run(1), run(2, minute=2)], [])], ["run", "run"]),
        (len(timeline([run(i, role="mender", agent="mender", minute=i) for i in range(2)], [])), 1),
        (move_of(runs[0]), "Handed in for review"),
        (run_cost_text(runs[0]), "$0.50"),
        (format_duration(3725), "1h 2m"),
        (format_duration(75), "1m 15s"),
        (format_money(1234.4), "$1,234"),
        (parse_money("$1,234 +2 unpriced"), 1234.0),
        (parse_unpriced("$4.20 +2 unpriced"), 2),
        (parse_unpriced("Leaves out 3 unpriced runs"), 3),
        (figure_leaves({"a": {"send_backs": 3}, "b": [1]}, "send"), [("a.send_backs", 3)]),
        (ADDRESS.format(hub="h", pid="p", build="b", query="&task=T"), "h/?project=p&tab=spec&view=build&focus=b&task=T"),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


def parse_money(text):
    found = re.search(r"\$([\d,]+(?:\.\d+)?)", text or "")
    return float(found.group(1).replace(",", "")) if found else None


def parse_unpriced(text):
    found = re.search(r"(\d+)\s+(?:unpriced|runs? (?:were |was )?not (?:included|priced))", text or "")
    return int(found.group(1)) if found else 0


def figure_leaves(value, word, path=""):
    """`(path, number)` for each numeric leaf whose path names `word`."""
    out = []
    if isinstance(value, dict):
        for k, v in value.items():
            out += figure_leaves(v, word, f"{path}.{k}" if path else k)
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and word in path.lower():
        out.append((path, value))
    return out


# --------------------------------------------------------------------------- Hub, snapshot, oracle


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HUB + "/api/v1" + path, data,
                                 {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception:  # noqa: BLE001 -- a row not yet written, a page mid-render
            pass
        time.sleep(every)
    return None


def now_sql():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


SEEDED = {}  # what seed_cases put into the scratch copy: the build and the task of each case

BUILD_FOR_SEEDS = ""  # set by seed_cases: the build the seeded cases sit in


def seed_cases(dst, now):
    """Cases the real data lacks, written into the scratch copy only (`dst` is never the source DB):
    a task whose runs are all unpriced, a task awaiting the operator (an open question), two
    mender turns in a row, and a Hub-filed fix task added after the declared ones."""
    global BUILD_FOR_SEEDS
    pid = PROJECT
    dst.row_factory = sqlite3.Row
    counts, usable = {}, []
    # The newest finished build with several tasks that ran: the Running tab lists the recent ones.
    for b in dst.execute("select id from builds where project_id=? and state='finished' "
                         "order by created_at desc limit 12", (pid,)).fetchall():
        tasks = dst.execute("select id, readable_id from tasks where build_id=? and spec_task_key is not null "
                            "order by created_at", (b["id"],)).fetchall()
        counts = {t["id"]: [r["id"] for r in dst.execute(
            "select id from runs where task_id=? order by started_at, id", (t["id"],))] for t in tasks}
        usable = [t for t in tasks if counts[t["id"]]]
        if len(usable) >= 4:
            BUILD_FOR_SEEDS = b["id"]
            break
    else:
        return {}
    by_runs = sorted(usable, key=lambda t: len(counts[t["id"]]))
    seeded = {}
    # 1. only unpriced runs: the smallest task, its usage rows left without a price.
    unpriced = by_runs[0]
    for rid in counts[unpriced["id"]]:
        dst.execute("update turn_usage set api_equivalent_usd_micros=null where run_id=?", (rid,))
    seeded["unpriced_only"] = unpriced["id"]
    others = [t for t in usable if t["id"] != unpriced["id"]]
    # 2. two mender turns in a row on the task with the most runs.
    mender_name = None
    for (name, config) in dst.execute("select name, config from agents where project_id=?", (pid,)).fetchall():
        try:
            if (json.loads(config or "{}") or {}).get("hub_role") == "mender":
                mender_name = name
                break
        except ValueError:
            continue
    mend, pair = None, None
    for t in sorted(others, key=lambda t: -len(counts[t["id"]])):
        ids = counts[t["id"]]
        for x, y in zip(ids, ids[1:]):
            between = dst.execute(
                "select count(*) from task_transitions where task_id=? and to_status in ('revision_needed', 'rejected') "
                "and created_at > (select started_at from runs where id=?) "
                "and created_at <= (select started_at from runs where id=?)", (t["id"], x, y)).fetchone()[0]
            if not between:
                mend, pair = t, (x, y)
                break
        if mend:
            break
    if mender_name and mend:
        for rid in pair:
            dst.execute("update runs set agent=? where id=?", (mender_name, rid))
        seeded["mender"] = mend["id"]
    else:
        mend = others[0]
    # 3. a task awaiting the operator: not done, with an unanswered question.
    wait = next(t for t in others if t["id"] != mend["id"])
    dst.execute("update tasks set status='under_review' where id=?", (wait["id"],))
    dst.execute(
        "insert into questions (id, project_id, from_agent, question, answered, blocking, options, "
        "answer_labels, multi_select, batch_index, batch_size, created_at, blocked_task_id, declined) "
        "values ('q-seeded-1', ?, 'Developer', 'Seeded: which of the two should it be?', 0, 1, '[]', '[]', "
        "0, 0, 1, ?, ?, 0)", (pid, now, wait["id"]))
    seeded["needs_operator"] = wait["id"]
    # 4. a Hub-filed fix task: in the build, declared by no key, made after the rest.
    src = dst.execute("select * from tasks where id=?", (wait["id"],)).fetchone()
    row = dict(src)
    row.update(id="task-seeded-fix", readable_id="SEEDFIX-1", title="Seeded: a Hub-filed fix task",
               spec_task_key=None, status="pending", created_at=now, updated=now)
    cols = list(row)
    dst.execute(f"insert into tasks ({', '.join(cols)}) values ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols])
    seeded["fix_task"] = "task-seeded-fix"
    dst.row_factory = None
    return seeded


def snapshot(source, copy):
    """A consistent copy of `source`, read through a `mode=ro` connection, made inert."""
    copy.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=60)
    dst = sqlite3.connect(copy.as_posix())
    try:
        src.backup(dst)
    finally:
        src.close()
    print(f"snapshot of {source} -> {copy} in {time.time() - started:.0f}s", flush=True)
    key = "aw_live_" + secrets.token_hex(16)
    now = now_sql()
    try:
        cols = {t: {r[1] for r in dst.execute(f"pragma table_info('{t}')")}
                for (t,) in dst.execute("select name from sqlite_master where type='table'")}
        dst.execute("update ai_jobs set enabled=0")
        if "apscheduler_jobs" in cols:
            dst.execute("delete from apscheduler_jobs")
        if "manager_jobs" in cols:
            dst.execute("update manager_jobs set enabled=0" + (", automatic=0" if "automatic" in cols["manager_jobs"] else ""))
        dst.execute("update inbound_queue_entries set state='withdrawn', withdrawn_at=? "
                    "where state not in ('delivered', 'withdrawn')", (now,))
        dst.execute("update runs set status='interrupted', pid=null, ended_at=coalesce(ended_at, ?) "
                    "where status in ('running', 'queued', 'starting')", (now,))
        for pid, workdir in dst.execute("select id, working_directory from projects").fetchall():
            mirror = SCRATCH / "mirror" / pid
            mirror.mkdir(parents=True, exist_ok=True)
            spec = pathlib.Path(workdir or "") / "spec"
            if spec.is_dir():
                shutil.copytree(spec, mirror / "spec", dirs_exist_ok=True)
            # The marker the Hub asks for, so a project's spec page opens on the copy.
            (mirror / ".agentweave").mkdir(exist_ok=True)
            (mirror / ".agentweave" / "project.json").write_text(
                json.dumps({"version": 1, "project_id": pid}), encoding="utf-8")
            dst.execute("update projects set working_directory=?, path_key=?, main_branch=null, checks=null, "
                        "pr_landing=0 where id=?", (str(mirror), "windows:" + str(mirror).lower(), pid))
        dst.execute("insert into operator_credentials (id, label, revoked, created_at) values (?, 'drive', 0, ?)",
                    (key, now))
        SEEDED.update(seed_cases(dst, now))
        dst.commit()
    finally:
        dst.close()
    return key


def start_hub(port, db, key):
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                  if "tool-server" not in p.replace("\\", "/"))
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = key
    log = open(SCRATCH / f"hub-{port}.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | 0x08000000)
    if not poll(lambda: api("GET", "/projects")[0] == 200, 300, every=1):
        proc.kill()
        raise Setup(f"the Hub on :{port} did not come up; see {SCRATCH / f'hub-{port}.log'}")
    print(f"started a Hub on :{port} from {REPO / 'hub'} on {db}", flush=True)
    return proc


def stop_hub(proc):
    if proc is not None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def oracle(pid, build_id):
    """The `BuildRead` the view must draw, from the mock's read-only recorder."""
    sys.path.insert(0, str(REPO / "hub" / "ui" / "mock"))
    import record_builds  # noqa: PLC0415 -- the mock's recorder, imported on demand

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        (workdir,) = con.execute("select working_directory from projects where id=?", (pid,)).fetchone()
        return record_builds.record(con, pid, build_id, pathlib.Path(workdir))
    finally:
        con.close()


def finished_builds(pid):
    return [r["id"] for r in ro("select id from builds where project_id=? and state='finished' "
                                "order by created_at desc", (pid,))]


def pick(pid, want, limit=40, smallest=False):
    """The first finished build (newest first) and task where `want(read, task, n)` holds; with
    `smallest`, the matching task with the fewest runs among the newest `limit` builds."""
    best = (None, None)
    for build_id in finished_builds(pid)[:limit]:
        try:
            read = oracle(pid, build_id)
        except Exception as exc:  # noqa: BLE001 -- a build the recorder cannot read is skipped
            print(f"  oracle skipped {build_id}: {exc}", flush=True)
            continue
        for n, task in enumerate(read["tasks"]):
            if want(read, task, n):
                if not smallest:
                    return read, task
                if best[1] is None or len(task["runs"]) < len(best[1]["runs"]):
                    best = (read, task)
    return best


# --------------------------------------------------------------------------- the page


def new_page(browser, pid, width=1440, height=940):
    context = browser.new_context(viewport={"width": width, "height": height})
    context.add_init_script(
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s); } catch (e) {}"
        % (json.dumps(KEY), json.dumps(HUB), json.dumps(pid)))
    return context.new_page()


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception:  # noqa: BLE001 -- a screenshot is evidence, not a step
        pass


def address(pid, build_id, task=None, run=None):
    q = urllib.parse.urlencode({k: v for k, v in (("task", task), ("run", run)) if v})
    return ADDRESS.format(hub=HUB, pid=pid, build=build_id, query=f"&{q}" if q else "")


def view(page, build_id=None):
    sel = "[data-testid=build-view]" + (f"[data-build-id='{build_id}']" if build_id else "")
    return page.locator(sel)


def open_view(page, pid, build_id, **kw):
    page.goto(address(pid, build_id, **kw), wait_until="domcontentloaded")
    try:
        view(page, build_id).first.wait_for(timeout=20000)
        page.locator("[data-slot=build-task-row], .aw-bv-empty").first.wait_for(timeout=20000)
    except Exception:  # noqa: BLE001 -- absence is what the checks report
        return False
    page.wait_for_timeout(500)
    return True


def what_is_there(page):
    if view(page).count():
        return f"a build view of {view(page).first.get_attribute('data-build-id')}"
    body = page.locator("body").inner_text()[:160].replace("\n", " | ")
    return f"no build view at {page.url[len(HUB):][:120]}; the page reads {body!r}"


def tasks_region(page):
    return page.get_by_role("region", name="Tasks")


def row_button(page, ref):
    return tasks_region(page).get_by_role("button", name=f"Open runs of {ref}", exact=True)


def row(page, task_id):
    return page.locator(f"li#build-task-{task_id}")


def expand(page, ref):
    button = row_button(page, ref)
    if not button.count():
        return False
    if button.first.get_attribute("aria-expanded") != "true":
        button.first.click()
        page.wait_for_timeout(600)
    return button.first.get_attribute("aria-expanded") == "true"


def timeline_list(page, ref):
    return page.get_by_role("list", name=f"Runs of {ref}", exact=True)


def run_button(page, label, ref=None):
    scope = timeline_list(page, ref) if ref else page
    return scope.get_by_role("button", name=f"Open trace: {label}", exact=True)


def open_groups(page, ref):
    groups = timeline_list(page, ref).get_by_role("button", name=re.compile(r"^Show .+ ×\d+: "))
    for _ in range(groups.count()):
        groups.first.click()
        page.wait_for_timeout(300)


def drawn_lines(page, ref):
    """The lines the task's timeline draws, top to bottom: ('run', label, text) / ('send-back', '', text)
    / ('group', name, text)."""
    out = []
    for li in timeline_list(page, ref).locator("li").all():
        kind = li.get_attribute("data-kind") or ""
        text = li.inner_text()
        if kind == "run":
            name = li.get_by_role("button").first.get_attribute("aria-label") or ""
            out.append(("run", name.removeprefix("Open trace: "), text))
        elif kind == "send-back":
            out.append(("send-back", "", text))
        elif kind == "group":
            name = li.get_by_role("button").first.get_attribute("aria-label") or ""
            out.append(("group", name, text))
    return out


def trace_drawer(page):
    return page.get_by_role("dialog", name="Trace")


def trace_open_on(page, label):
    drawer = trace_drawer(page)
    return bool(drawer.count() and drawer.first.is_visible() and label in drawer.first.inner_text())


def task_row_runs(page, task_id):
    cells = row(page, task_id).locator(".aw-bv-row > .aw-bv-num")
    return int(cells.first.inner_text().strip() or -1) if cells.count() else None


def task_row_status(page, task_id):
    status = row(page, task_id).locator("[data-status]")
    return (status.first.get_attribute("data-status") if status.count()
            else row(page, task_id).get_attribute("data-status") if row(page, task_id).count() else None)


# --------------------------------------------------------------------------- the checks


def check_totals(browser, state):
    key, pid = "ac-totals", state["pid"]
    build_id = finished_builds(pid)[0]
    page = new_page(browser, pid)
    code, figures = api("GET", f"/projects/{pid}/project/builds/{build_id}/figures")
    if code != 200:
        raise Setup(f"figures of {build_id}: {code} {str(figures)[:200]}")
    opened = open_view(page, pid, build_id)
    shot(page, "totals")
    if not opened:
        return record(key, False, f"build {build_id}: {what_is_there(page)}")
    code2, figures2 = api("GET", f"/projects/{pid}/project/builds/{build_id}/figures")

    def text(test_id):
        found = page.get_by_test_id(test_id)
        return found.first.inner_text().strip() if found.count() else ""
    runs, cost, note, send_backs = text("build-runs"), text("build-cost"), text("build-cost-note"), text("build-send-backs")
    work = re.search(r"(\d+h \d+m|\d+m \d+s|\d+s) of agent work", view(page).first.inner_text())
    priced = [v for v in (figures.get("cost") or {}).values() if v is not None]
    want_cost = format_money(sum(priced)) if priced else "unpriced"
    sb_leaves = figure_leaves(figures, "send")
    time_leaves = [(p, v) for p, v in figure_leaves(figures, "seconds")
                   if re.search(r"run|agent|work", p, re.I) and not p.startswith("checks")]
    parts = [
        ("runs", runs == str(figures.get("runs")), f"view {runs!r} figures {figures.get('runs')}"),
        ("cost", (parse_money(cost) == parse_money(want_cost)) if priced else "unpriced" in cost,
         f"view {cost!r} figures {want_cost}"),
        ("unpriced", parse_unpriced(f"{cost} {note}") == (figures.get("unpriced") or 0) or not priced,
         f"view {cost!r}/{note!r} figures unpriced={figures.get('unpriced')}"),
        ("run time", bool(work and time_leaves and any(work.group(1) == format_duration(v) for _, v in time_leaves)),
         f"view {work.group(1) if work else None!r} figures {time_leaves or 'carry no run-time figure'}"),
        ("send-backs", bool(sb_leaves) and any(send_backs == str(v) for _, v in sb_leaves),
         f"view {send_backs!r} figures {sb_leaves or 'carry no send-back count'}"),
        ("same moment", code2 == 200 and figures2 == figures, "the figures did not move while the view was read"),
    ]
    record(key, all(ok for _, ok, _ in parts), f"build {build_id}: " + "; ".join(
        f"{n} {'ok' if ok else 'DIFFERS'} ({d})" for n, ok, d in parts))


def check_address(browser, state):
    key, pid = "ac-address", state["pid"]

    def want(read, task, n):
        return n == 1 and sum(1 for x in timeline(task["runs"], task["send_backs"])[:6] if x["kind"] == "run") >= 3
    read, task = pick(pid, want)
    if not task:
        raise Setup("no finished build whose task 2 has three runs before any fold")
    build_id, ref = read["build"]["id"], task["ref"]
    third = [x for x in timeline(task["runs"], task["send_backs"]) if x["kind"] == "run"][2]
    page = new_page(browser, pid)
    if not open_view(page, pid, build_id):
        shot(page, "address-first")
        return record(key, False, f"build {build_id} task 2 {ref}: {what_is_there(page)}")
    if not expand(page, ref):
        return record(key, False, f"no row button 'Open runs of {ref}' that expands")
    button = run_button(page, third["label"], ref)
    if not button.count():
        return record(key, False, f"no 'Open trace: {third['label']}' in {ref}'s timeline: {drawn_lines(page, ref)[:6]}")
    button.first.click()
    opened = poll(lambda: trace_open_on(page, third["label"]), 10)
    copied = page.url
    shot(page, "address-first")
    other = new_page(browser, pid)
    other.goto(copied, wait_until="domcontentloaded")
    same = bool(poll(lambda: view(other, build_id).count(), 20))
    # The open trace is modal, so the page behind it is out of the accessibility tree: ask for hidden too.
    hidden_row = row(other, task["id"]).locator(f'button[aria-label="Open runs of {ref}"]')
    expanded = bool(poll(lambda: hidden_row.count() and hidden_row.first.get_attribute("aria-expanded") == "true", 15))
    trace = bool(poll(lambda: trace_open_on(other, third["label"]), 15))
    current = row(other, task["id"]).locator(f'button[aria-label="Open trace: {third["label"]}"]')
    marked = bool(current.count() and current.first.get_attribute("aria-current") == "true")
    shot(other, "address-copied")
    ok = bool(opened) and same and expanded and trace and marked
    record(key, ok, f"build {build_id}, task 2 {ref}, {third['label']} ({third['run']['id']}): trace opened={bool(opened)}; "
                    f"copied {copied[len(HUB):]!r}; new window: same build={same}, {ref} expanded={expanded}, "
                    f"that trace open={trace}, its run marked current={marked}")


def check_timeline(browser, state):
    key, pid = "ac-timeline", state["pid"]

    def want(read, task, n):
        roles = [r["role"] for r in task["runs"]]
        defect = [s for s in task["send_backs"] if s["reason_class"] == "defect" and s["by"]["kind"] == "agent"
                  and send_back_text(s)]
        return (task["status"] == "approved" and roles.count("build") >= 2 and "review" in roles
                and "mender" in roles and defect)
    read, task = pick(pid, want, limit=80, smallest=True)
    if not task:
        raise Setup("no finished build with a task built, sent back as a defect with a note, rebuilt, "
                    "reviewed, approved and touched by the mender")
    build_id, ref = read["build"]["id"], task["ref"]
    # The run set, by plain SELECT: the runs naming the task and the runs in its stalls' conversations.
    sql_runs = {r["id"] for r in ro("select id from runs where task_id=?", (task["id"],))}
    sql_runs |= {r["id"] for r in ro("select r.id from runs r join stalls s on s.conversation_id=r.conversation_id "
                                     "where s.task_id=? and r.started_at>=s.first_seen_at", (task["id"],))}
    oracle_runs = {r["id"] for r in task["runs"]}
    sql_sbs = [r["sequence"] for r in ro("select sequence from task_transitions where task_id=? and to_status in "
                                         "('revision_needed','rejected') order by sequence", (task["id"],))]
    if not oracle_runs <= sql_runs or sorted(s["sequence"] for s in task["send_backs"]) != sql_sbs:
        raise Setup(f"the recorder's run set disagrees with SELECT: extra {sorted(oracle_runs - sql_runs)}, "
                    f"send-backs {sql_sbs}")
    expected = lines_of(timeline(task["runs"], task["send_backs"]))
    page = new_page(browser, pid)
    if not open_view(page, pid, build_id):
        shot(page, "timeline")
        return record(key, False, f"build {build_id} task {ref}: {what_is_there(page)}")
    if not expand(page, ref):
        return record(key, False, f"no row button 'Open runs of {ref}' that expands")
    open_groups(page, ref)
    drawn = drawn_lines(page, ref)
    shot(page, "timeline")
    problems = []
    if [k for k, _, _ in drawn] != [x["kind"] for x in expected]:
        problems.append(f"lines {[(k, n) for k, n, _ in drawn][:12]} != expected "
                        f"{[(x['kind'], x['label'] if x['kind'] == 'run' else '') for x in expected][:12]}")
    for (kind, name, text), want_line in zip(drawn, expected):
        if kind != want_line["kind"]:
            break
        if kind == "run":
            run = want_line["run"]
            needed = [want_line["label"], run["agent"], run.get("model") or "model not reported",
                      format_duration(run_seconds(run)), move_of(run)]
            cost = run_cost_text(run)
            needed += [cost] if cost else []
            missing = [n for n in needed if n not in f"{name}\n{text}"]
            if missing:
                problems.append(f"{want_line['label']} ({run['id']}) lacks {missing}")
        else:
            sb = want_line["sb"]
            needed = [want_line["by"], reason_class_label(sb["reason_class"]) or "", want_line["text"][:60]]
            missing = [n for n in needed if n and n not in text]
            if missing:
                problems.append(f"send-back {sb['sequence']} lacks {missing}")
    runs_drawn = sum(1 for k, _, _ in drawn if k == "run")
    if runs_drawn != len(task["runs"]):
        problems.append(f"{runs_drawn} runs drawn, the task has {len(task['runs'])}")
    times = timeline_list(page, ref).locator("[data-kind=run] time[datetime]").count()
    if times < len(task["runs"]):
        problems.append(f"{times} run start times drawn for {len(task['runs'])} runs")
    defect = next(x for x in expected if x["kind"] == "send-back" and x["sb"]["reason_class"] == "defect")
    at = expected.index(defect)
    builds_before = [x for x in expected[:at] if x["kind"] == "run" and x["run"]["role"] == "build"]
    builds_after = [x for x in expected[at + 1:] if x["kind"] == "run" and x["run"]["role"] == "build"]
    between = bool(builds_before and builds_after)
    record(key, not problems and between,
           f"build {build_id} task {ref}: {len(task['runs'])} runs, {len(task['send_backs'])} send-backs; "
           f"the defect send-back by {defect['by']} sits between "
           f"{builds_before[-1]['label'] if builds_before else None} and "
           f"{builds_after[0]['label'] if builds_after else None}; "
           + ("; ".join(problems[:6]) if problems else "every line, its fields and its order as recorded"))


def check_fold(browser, state):
    key, pid = "ac-fold-checks-loop", state["pid"]

    def want(read, task, n):
        found = checks_loop_group(timeline(task["runs"], task["send_backs"]))
        if found is None or not found[1]["reason"]:
            return False
        items = timeline(task["runs"], task["send_backs"])
        # The line after the loop is the build that passes, as its own line (not a fold of its own).
        return found[0] + 1 < len(items) and items[found[0] + 1]["kind"] == "run"
    read, task = pick(pid, want, limit=80)
    if not task:
        raise Setup("no finished build with a task bounced three or more times running by the landing checks "
                    "for one reason")
    build_id, ref = read["build"]["id"], task["ref"]
    items = timeline(task["runs"], task["send_backs"])
    n, group = checks_loop_group(items)
    after = items[n + 1] if n + 1 < len(items) else None
    page = new_page(browser, pid)
    if not open_view(page, pid, build_id):
        shot(page, "fold")
        return record(key, False, f"build {build_id} task {ref}: {what_is_there(page)}")
    if not expand(page, ref):
        return record(key, False, f"no row button 'Open runs of {ref}' that expands")
    runs_before = task_row_runs(page, task["id"])
    cost_before = row(page, task["id"]).locator(".aw-bv-row > .aw-bv-num").nth(2).inner_text()
    name = f"Show {group['label']}: {group['detail']}"
    button = timeline_list(page, ref).get_by_role("button", name=name, exact=True)
    shot(page, "fold-folded")
    if not button.count():
        drawn = [(k, nm) for k, nm, _ in drawn_lines(page, ref)]
        return record(key, False, f"build {build_id} task {ref}: no folded row {name!r}; drawn {drawn[:10]}")
    # Chosen by what it holds, not by its button's name: the name flips to "Hide ..." once it is open.
    li = timeline_list(page, ref).locator('li[data-kind="group"]').filter(has_text=group["detail"]).first
    folded_text = li.inner_text()
    parts = [
        ("says sent back N times", f"Sent back {group['send_backs']} times" in folded_text),
        ("reason once", folded_text.count(group["reason"][:80]) == 1),
    ]
    drawn = drawn_lines(page, ref)
    top = [x for x in drawn if x[0] != "send-back" or True]
    at = next((i for i, x in enumerate(top) if x[0] == "group" and x[1] == name), None)
    if after is not None and at is not None:
        nxt = top[at + 1] if at + 1 < len(top) else None
        want_next = after["label"] if after["kind"] == "run" else ""
        parts.append(("next line its own", bool(nxt and nxt[0] == after["kind"] and nxt[1] == want_next)))
    button.first.click()
    page.wait_for_timeout(600)
    inner = li.locator("ol li")
    inner_lines = [(x.get_attribute("data-kind"),
                    (x.get_by_role("button").first.get_attribute("aria-label") or "").removeprefix("Open trace: ")
                    if x.get_attribute("data-kind") == "run" else "") for x in inner.all()]
    want_lines = [(x["kind"], x["label"] if x["kind"] == "run" else "") for x in group["items"]]
    parts.append((f"opens to its {len(want_lines)} lines in order", inner_lines == want_lines))
    parts.append(("every folded run opens its trace", all(
        run_button(page, x["label"], ref).count() for x in group["items"] if x["kind"] == "run")))
    runs_after = task_row_runs(page, task["id"])
    cost_after = row(page, task["id"]).locator(".aw-bv-row > .aw-bv-num").nth(2).inner_text()
    parts.append(("run count and cost unchanged", runs_before == runs_after == len(task["runs"]) and cost_before == cost_after))
    shot(page, "fold-opened")
    record(key, all(ok for _, ok in parts),
           f"build {build_id} task {ref}: {name!r}; " + "; ".join(f"{p} {'ok' if ok else 'FAILED'}" for p, ok in parts)
           + f"; runs {runs_before}->{runs_after} of {len(task['runs'])}, cost {cost_before!r}->{cost_after!r}; "
           f"inner {inner_lines[:6]}")


def check_trace(browser, state):
    key, pid = "ac-trace", state["pid"]

    def want(read, task, n):
        return any(r["role"] == "review" and r.get("conversation_id") for r in task["runs"])
    read, task = pick(pid, want)
    if not task:
        raise Setup("no finished build with a review run that names its conversation")
    build_id, ref = read["build"]["id"], task["ref"]
    lines = lines_of(timeline(task["runs"], task["send_backs"]))
    review = next(x for x in lines if x["kind"] == "run" and x["run"]["role"] == "review" and x["run"].get("conversation_id"))
    run = review["run"]
    page = new_page(browser, pid)
    if not open_view(page, pid, build_id):
        shot(page, "trace")
        return record(key, False, f"build {build_id} task {ref}: {what_is_there(page)}")
    if not expand(page, ref):
        return record(key, False, f"no row button 'Open runs of {ref}' that expands")
    open_groups(page, ref)
    button = run_button(page, review["label"], ref)
    if not button.count():
        return record(key, False, f"no 'Open trace: {review['label']}' in {ref}'s timeline")
    button.first.click()
    opened = bool(poll(lambda: trace_open_on(page, review["label"]), 10))
    in_address = f"run={run['id']}" in page.url
    shot(page, "trace-open")
    link = trace_drawer(page).get_by_role("button", name=re.compile(r"Open the conversation")) if opened else None
    if not link or not link.count():
        link = trace_drawer(page).get_by_role("link", name=re.compile(r"Open the conversation")) if opened else None
    if not link or not link.count():
        return record(key, False, f"build {build_id} {review['label']} of {ref}: trace open={opened}, "
                                  f"run in the address={in_address}; no 'Open the conversation' in the trace")
    link.first.click()
    moved = bool(poll(lambda: f"conversation={run['conversation_id']}" in page.url, 10))
    pane = bool(poll(lambda: page.get_by_test_id("conversation-pane").count(), 15))
    shot(page, "trace-conversation")
    record(key, opened and in_address and moved and pane,
           f"build {build_id} {review['label']} of {ref} ({run['id']}, {run['agent']}): trace open={opened}, "
           f"run in the address={in_address}; conversation {run['conversation_id']} opened={moved} "
           f"(url {page.url[len(HUB):][:120]}), pane drawn={pane}")


def check_open_from_drawer(browser, state):
    key, pid = "ac-open-from-drawer", state["pid"]
    read, task = pick(pid, lambda read, task, n: n == 0 and task["status"] == "approved")
    if not task:
        raise Setup("no finished build with an approved first task")
    build_id, ref, doc = read["build"]["id"], task["ref"], read["build"]["document_id"]
    page = new_page(browser, pid)
    page.add_init_script("try { localStorage.setItem(%s, %s); localStorage.setItem(%s, 'true'); } catch (e) {}" % (
        json.dumps(f"aw.boardScope.{pid}"), json.dumps(json.dumps({"kind": "spec", "id": doc})),
        json.dumps(f"aw.boardShowFinished.{pid}")))
    page.goto(f"{HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
    card = page.get_by_test_id(f"task-open-{task['id']}")
    if not poll(lambda: card.count(), 20):
        raise Setup(f"the Tasks board scoped to {doc} draws no card for {ref}")
    card.first.click()
    drawer = page.get_by_test_id(f"task-drawer-{task['id']}")
    if not poll(lambda: drawer.count(), 10):
        raise Setup(f"{ref}'s card opened no task drawer")
    link = drawer.get_by_role("link", name="Open in its build").or_(
        drawer.get_by_role("button", name="Open in its build"))
    poll(lambda: link.count(), 10)
    shot(page, "drawer")
    parts = []
    if not link.count():
        parts.append(("drawer offers Open in its build", False))
    else:
        link.first.click()
        at_build = bool(poll(lambda: view(page, build_id).count(), 20))
        expanded = bool(poll(lambda: row_button(page, ref).first.get_attribute("aria-expanded") == "true", 10))
        parts.append((f"opens {build_id} with {ref} expanded", at_build and expanded))
        shot(page, "drawer-opened")
    # Overview lists running turns, and an inert snapshot has none: its link is driven in ac-live, on a
    # build that really runs.
    record(key, all(ok for _, ok in parts), f"task {ref} of {build_id}: " + "; ".join(
        f"{p} {'ok' if ok else 'FAILED'}" for p, ok in parts))


# --------------------------------------------------------------------------- summaries, parity, unpriced


def figures_of(root, prefix):
    out = {}
    for name in ("approved", "cost", "send-backs", "needs"):
        found = root.get_by_test_id(f"{prefix}-{name}")
        out[name] = re.sub(r"\s+", " ", found.first.inner_text()).strip() if found.count() else None
    return out


def digits(text):
    return re.findall(r"\d+(?:[.,]\d+)?", text or "")


def check_summaries(browser, state):
    key, pid = "ac-summaries-open", state["pid"]
    code, listing = api("GET", f"/projects/{pid}/project/builds")
    builds = (listing or {}).get("builds", []) if code == 200 else []
    running = [b for b in builds if b.get("state") == "running"]
    finished = [b for b in builds if b.get("state") == "finished"]
    if not running or not finished:
        raise Setup(f"needs one running and one finished build ({len(running)} running, {len(finished)} finished)")
    parts, parity, notes_of = [], [], {}
    for kind, b in (("running", running[0]), ("finished", finished[0])):
        bid, doc = b["id"], b.get("document_path")
        page = new_page(browser, pid)
        if not open_view(page, pid, bid):
            parts.append((f"{kind} {bid} opens its view", False))
            continue
        in_view = figures_of(page, "build")
        note_el = page.get_by_test_id("build-cost-note")
        notes_of[kind] = re.sub(r"\s+", " ", note_el.first.inner_text()).strip() if note_el.count() else ""
        # The spec page's strip.
        page.goto(f"{HUB}/?project={pid}&tab=spec&document={urllib.parse.quote(doc or '')}", wait_until="domcontentloaded")
        strip = page.locator(f'[data-testid=build-summary][data-build-id="{bid}"]')
        poll(lambda: strip.count(), 20)
        shot(page, f"summary-strip-{kind}")
        if not strip.count():
            parts.append((f"{kind} {bid}: spec page shows its summary", False))
        else:
            on_page = figures_of(strip.first, "summary")
            parity.append((f"{kind} spec page", on_page, in_view, notes_of.get(kind, "")))
            strip.first.get_by_role("link", name="Open build").first.click()
            parts.append((f"{kind} spec-page summary opens its view", bool(poll(lambda: view(page, bid).count(), 20))))
            page.go_back()
            chip = strip.first.locator("a[href*='task=']").first
            poll(lambda: chip.count(), 10)
            if chip.count():
                href = chip.get_attribute("href")
                chip.click()
                opened = poll(lambda: view(page, bid).count(), 20)
                task_ref = (re.search(r"[?&]task=([^&]+)", href or "") or [None, None])[1]
                at = bool(opened and task_ref and poll(lambda: page.locator(
                    f'button[aria-label="Open runs of {urllib.parse.unquote(task_ref)}"][aria-expanded="true"]').count(), 10))
                parts.append((f"{kind} spec-page task chip opens the view at {task_ref}", at))
            else:
                parts.append((f"{kind} spec-page summary has a task to choose", False))
        # The side panel's Running tab.
        page.goto(f"{HUB}/?project={pid}&agent=Developer", wait_until="domcontentloaded")
        page.get_by_test_id("conversation-more").first.click()
        if page.get_by_test_id("conversation-toggle-panel").count():
            if "Show" in page.get_by_test_id("conversation-toggle-panel").first.inner_text():
                page.get_by_test_id("conversation-toggle-panel").first.click()
            else:
                page.keyboard.press("Escape")
        tab = page.get_by_role("tab", name=re.compile("^Running")).or_(page.get_by_role("button", name=re.compile("^Running")))
        poll(lambda: tab.count(), 15)
        if tab.count():
            tab.first.click()
            page.wait_for_timeout(800)
        card = page.locator(f'[data-testid=build-summary][data-build-id="{bid}"]')
        poll(lambda: card.count(), 10)
        shot(page, f"summary-panel-{kind}")
        if card.count():
            parity.append((f"{kind} Running tab", figures_of(card.first, "summary"), in_view, notes_of.get(kind, "")))
            card.first.get_by_role("link", name="Open build").first.click()
            parts.append((f"{kind} Running-tab summary opens its view", bool(poll(lambda: view(page, bid).count(), 20))))
        elif kind == "running":
            parts.append((f"running {bid}: Running tab shows its summary", False))
        page.context.close()
    record(key, all(ok for _, ok in parts) and bool(parity), "; ".join(f"{p} {'ok' if ok else 'FAILED'}" for p, ok in parts))
    ok_all, notes = True, []
    for where, got, want, cost_note in parity:
        # A surface is compared on the figures it carries: the spec page's strip is the narrow form
        # (send-backs and who is needed), the Running tab's card carries all four. The card states its
        # unpriced runs inside the cost ("$X +N unpriced"); the view states them in its cost note.
        def agrees(k):
            if k == "cost":
                return digits(got[k])[:1] == digits(want[k])[:1]
            return digits(got[k]) == digits(want[k]) or (k == "needs" and not digits(got[k]) and not digits(want[k])
                   and ("nothing" in got[k].lower()) == ("nothing" in want[k].lower()))
        same = all(agrees(k) for k in got if got[k] is not None)
        if got.get("cost") and "unpriced" in got["cost"]:
            same &= digits(got["cost"])[1:2] == digits(cost_note)[:1]
        ok_all &= same
        notes.append(f"{where}: {got} vs view {want} (cost note {cost_note!r}) {'equal' if same else 'DIFFER'}")
    record("ac-parity", ok_all and bool(parity), "; ".join(notes) or "no surface to compare")


def check_unpriced_and_pairs(browser, state):
    pid = state["pid"]

    def mixed(read, task, n):
        states = [r["cost_state"] for r in task["runs"]]
        return "measured" in states and "unpriced" in states and len(task["runs"]) <= 12

    def only_unpriced(read, task, n):
        return task["runs"] and all(r["cost_state"] == "unpriced" for r in task["runs"]) and len(task["runs"]) <= 12
    parts = []
    for label, want in (("priced and unpriced runs", mixed), ("only unpriced runs", only_unpriced)):
        read, task = pick(pid, want, limit=80, smallest=True)
        if not task:
            parts.append((f"{label}: NOT DRIVEN, no such task in the data (a fixture covers it in buildView.test.tsx)", True))
            continue
        page = new_page(browser, pid)
        if not open_view(page, pid, read["build"]["id"]):
            parts.append((f"{label}: view did not open", False))
            continue
        ref = task["ref"]
        expand(page, ref)
        open_groups(page, ref)
        cost_cell = row(page, task["id"]).locator(".aw-bv-row > .aw-bv-num").nth(2).inner_text().replace("\n", " ")
        lines = [x.inner_text() for x in timeline_list(page, ref).locator('li[data-kind="run"]').all()]
        unpriced_lines = [x for x in lines if "unpriced" in x.lower()]
        n_unpriced = sum(1 for r in task["runs"] if r["cost_state"] == "unpriced")
        if label.startswith("priced"):
            ok = (len(unpriced_lines) >= 1 and re.search(rf"\+\s*{n_unpriced}\s+unpriced", cost_cell) is not None
                  and "$" in cost_cell)
        else:
            ok = (len(unpriced_lines) == len(task["runs"]) and cost_cell.strip().lower().startswith("unpriced")
                  and "$" not in cost_cell)
        shot(page, f"unpriced-{label.split()[0]}")
        parts.append((f"{ref} ({label}): row total {cost_cell!r}, {len(unpriced_lines)} run lines read unpriced "
                      f"of {len(task['runs'])}", ok))
        page.context.close()
    record("ac-unpriced", all(ok for _, ok in parts), "; ".join(f"{p} {'ok' if ok else 'FAILED'}" for p, ok in parts))

    def two_in_a_row(items):
        for a, b in zip(items, items[1:]):
            if (a["kind"] == "run" and b["kind"] == "run" and a["run"]["role"] == b["run"]["role"] == "build"
                    and a["run"]["agent"] == b["run"]["agent"]):
                return a, b
        return None

    def pair(read, task, n):
        return len(task["runs"]) <= 12 and two_in_a_row(timeline(task["runs"], task["send_backs"])) is not None
    read, task = pick(pid, pair, limit=80, smallest=True)
    if not task:
        return record("ac-no-fold-pairs", False, "no finished task with two builds in a row by one agent")
    a, b = two_in_a_row(timeline(task["runs"], task["send_backs"]))
    page = new_page(browser, pid)
    if not open_view(page, pid, read["build"]["id"]):
        return record("ac-no-fold-pairs", False, what_is_there(page))
    expand(page, task["ref"])
    own = []
    for it in (a, b):
        li = timeline_list(page, task["ref"]).locator('li[data-kind="run"]').filter(
            has=page.locator(f'button[aria-label="Open trace: {it["label"]}"]'))
        own.append(bool(li.count()))
    shot(page, "no-fold-pairs")
    record("ac-no-fold-pairs", all(own),
           f"{task['ref']}: {a['label']} and {b['label']} by {a['run']['agent']}, each its own line: {own}")


def open_running_panel(page, pid, show="Finished"):
    page.goto(f"{HUB}/?project={pid}&agent=Developer", wait_until="domcontentloaded")
    page.get_by_test_id("conversation-more").first.click()
    if page.get_by_test_id("conversation-toggle-panel").count():
        if "Show" in page.get_by_test_id("conversation-toggle-panel").first.inner_text():
            page.get_by_test_id("conversation-toggle-panel").first.click()
        else:
            page.keyboard.press("Escape")
    tab = page.get_by_role("tab", name=re.compile("^Running")).or_(page.get_by_role("button", name=re.compile("^Running")))
    poll(lambda: tab.count(), 15)
    if tab.count():
        tab.first.click()
        page.wait_for_timeout(800)
    finished = page.get_by_role("radio", name=re.compile(f"^{show}")).or_(
        page.get_by_role("button", name=re.compile(f"^{show}")))
    if finished.count():
        finished.first.click()
        page.wait_for_timeout(600)


def check_seeded(browser, state):
    """The cases the real data lacks, seeded into the scratch copy: FR-2 fix task, FR-4 only-unpriced,
    FR-14 mender fold, FR-11 a non-zero needs-you count on all three surfaces, FR-10 the Finished
    filter's card in the Running tab."""
    pid, bid = state["pid"], BUILD_FOR_SEEDS
    if len(SEEDED) < 4:
        raise Setup(f"the scratch copy was not seeded ({SEEDED}); drive a snapshot, not --hub")
    page = new_page(browser, pid)
    if not open_view(page, pid, bid):
        return record("ac-seeded", False, what_is_there(page))
    ids = [x.get_attribute("id") for x in page.locator("li[id^='build-task-']").all()]
    in_db = [r["id"] for r in ro("select id from tasks where build_id=?", (bid,))]
    fix = "build-task-" + SEEDED["fix_task"]
    declared_first = bool(ids) and ids[-1] == fix and ids.count(fix) == 1 and len(set(ids)) == len(ids)
    record("ac-tasks-once-in-order", declared_first and len(ids) == len(in_db),
           f"{len(ids)} rows for {len(in_db)} tasks in the data, the seeded Hub-filed fix {SEEDED['fix_task']} last "
           f"and once: {declared_first}; rows read: {[i[len('build-task-'):][:14] for i in ids]}")
    shot(page, "seeded-order")
    # FR-4: the task with only unpriced runs.
    unp = SEEDED["unpriced_only"]
    ref = ro("select readable_id from tasks where id=?", (unp,))[0]["readable_id"]
    expand(page, ref)
    cost_cell = row(page, unp).locator(".aw-bv-row > .aw-bv-num").nth(2).inner_text().replace("\n", " ")
    lines = [x.inner_text() for x in timeline_list(page, ref).locator('li[data-kind="run"]').all()]
    unp_lines = [x for x in lines if "unpriced" in x.lower()]
    record("ac-unpriced-only", cost_cell.strip().lower().startswith("unpriced") and "$" not in cost_cell
           and lines and len(unp_lines) == len(lines),
           f"{ref}: total reads {cost_cell!r}; {len(unp_lines)} of {len(lines)} run lines read unpriced")
    shot(page, "seeded-unpriced-only")
    # FR-14: the two mender turns fold.
    mend = SEEDED["mender"]
    mref = ro("select readable_id from tasks where id=?", (mend,))[0]["readable_id"]
    runs_before = task_row_runs(page, mend)
    expand(page, mref)
    group_text = next((n for k, n, _ in drawn_lines(page, mref) if k == "group" and "Mender ×" in n), "")
    folded = bool(group_text)
    open_groups(page, mref)
    runs_after = task_row_runs(page, mend)
    n_lines = timeline_list(page, mref).locator('li[data-kind="run"]').count()
    n_runs = ro("select count(*) c from runs where task_id=?", (mend,))[0]["c"]
    shot(page, "seeded-mender-fold")
    record("ac-mender-fold", folded and runs_before == runs_after and n_lines >= n_runs - 0,
           f"{mref}: group row reads {group_text!r}; run count {runs_before} before and {runs_after} after expanding; "
           f"{n_lines} run lines drawn for {n_runs} runs; first lines {[(k, n) for k, n, _ in drawn_lines(page, mref)]}")
    in_view = figures_of(page, "build")
    unpriced_note = re.sub(r"\s+", " ", page.get_by_test_id("build-cost-note").first.inner_text()).strip()
    page.context.close()
    # FR-11 / FR-10: the needs-you count on the three surfaces, and the Running tab's Finished card.
    b = next((x for x in (api("GET", f"/projects/{pid}/project/builds")[1] or {}).get("builds", []) if x["id"] == bid), {})
    parts, parity = [], []
    page = new_page(browser, pid)
    page.goto(f"{HUB}/?project={pid}&tab=spec&document={urllib.parse.quote(b.get('document_path') or '')}",
              wait_until="domcontentloaded")
    strip = page.locator(f'[data-testid=build-summary][data-build-id="{bid}"]')
    poll(lambda: strip.count(), 20)
    if strip.count():
        parity.append(("finished spec page", figures_of(strip.first, "summary"), in_view))
    open_running_panel(page, pid)
    card = page.locator(f'[data-testid=build-summary][data-build-id="{bid}"]')
    poll(lambda: card.count(), 6)
    if not card.count():  # a finished build that still needs the operator sits outside the Finished filter
        open_running_panel(page, pid, show="All")
        poll(lambda: card.count(), 10)
    shot(page, "seeded-running-finished-card")
    if not card.count():
        parts.append(("Finished filter lists the build's card", False))
    else:
        parity.append(("finished Running tab card", figures_of(card.first, "summary"), in_view))
        chip = card.first.locator("a[href*='task=']").first
        href = chip.get_attribute("href") if chip.count() else None
        card.first.get_by_role("link", name="Open build").first.click()
        parts.append(("Finished Running-tab summary opens its view", bool(poll(lambda: view(page, bid).count(), 20))))
        if href:
            open_running_panel(page, pid, show="All")
            card = page.locator(f'[data-testid=build-summary][data-build-id="{bid}"]')
            poll(lambda: card.count(), 10)
            card.first.locator("a[href*='task=']").first.click()
            task_ref = (re.search(r"[?&]task=([^&]+)", href) or [None, None])[1]
            at = bool(poll(lambda: page.locator(
                f'button[aria-label="Open runs of {urllib.parse.unquote(task_ref or "")}"][aria-expanded="true"]').count(), 15))
            parts.append((f"Finished Running-tab task chip opens the view at {task_ref}", at))
    page.context.close()
    record("ac-summaries-open-finished-card", all(ok for _, ok in parts) and bool(parts),
           "; ".join(f"{p} {'ok' if ok else 'FAILED'}" for p, ok in parts))
    notes, ok_all = [], True
    needs_view = digits(in_view["needs"])
    for where, got, want in parity:
        same = all((digits(got[k])[:1] == digits(want[k])[:1]) if k == "cost" else digits(got[k]) == digits(want[k])
                   for k in got if got[k] is not None)
        if got["cost"] and "unpriced" in got["cost"]:
            same &= digits(got["cost"])[1:2] == digits(unpriced_note)[:1]
        ok_all &= same
        notes.append(f"{where}: {got} vs view {want} (cost note {unpriced_note!r}) {'equal' if same else 'DIFFER'}")
    record("ac-parity-needs", ok_all and bool(parity) and bool(needs_view) and needs_view[0] != "0",
           f"needs-you count in the view {in_view['needs']!r} (non-zero required); " + "; ".join(notes))
    # The wired error state: a build the Hub does not have reads as an error with its message, not as empty.
    page = new_page(browser, pid)
    page.goto(address(pid, "build-doesnotexist00"), wait_until="domcontentloaded")
    poll(lambda: page.get_by_role("alert").count() or page.locator(".aw-bv-empty").count(), 20)
    page.wait_for_timeout(500)
    alert = page.get_by_role("alert")
    shot(page, "wired-error-state")
    record("ac-error-state", alert.count() > 0 and not page.locator("[data-slot=build-task-row]").count(),
           f"a build the Hub does not have: {alert.first.inner_text()[:120]!r}" if alert.count() else "no alert drawn")
    page.context.close()
    parts_of = ("ac-tasks-once-in-order", "ac-unpriced-only", "ac-mender-fold", "ac-summaries-open-finished-card",
                "ac-parity-needs", "ac-error-state")
    record("ac-seeded", all(checks.get(k, (0, True))[1] is False for k in parts_of),
           "seeded cases (Hub-filed fix task, unpriced-only task, mender fold, needs-you parity, Finished card): "
           + ", ".join(f"{k}={'ok' if checks.get(k, (0, True))[1] is False else 'FAILED'}" for k in parts_of))


def check_matches_mock(browser, state):
    """Shots of the wired view in light and dark, wide and narrow, named for the mock's shoot.py."""
    pid = state["pid"]
    build_id = "build-04e780a89c1c"  # the mock's DEFAULT_BUILD, recorded from this project's real history
    if build_id not in finished_builds(pid):
        raise Setup(f"{build_id}, the mock's recorded build, is not in the data")
    for mode in ("dark", "light"):
        for width in (1440, 960):
            page = new_page(browser, pid, width=width, height=900)
            page.add_init_script(f"try {{ document.documentElement.dataset.mode = '{mode}' }} catch (e) {{}}")
            if not open_view(page, pid, build_id):
                shot(page, f"wired_{mode}_{width}_failed")
                return record("ac-matches-mock", False, f"{mode} {width}: {what_is_there(page)}")
            page.evaluate(f"document.documentElement.dataset.mode = '{mode}'")
            page.wait_for_timeout(900)
            shot(page, f"wired_{mode}_{width}")
            page.context.close()
    record("ac-matches-mock", True, f"shots of {build_id} in {OUT}: wired_{{dark,light}}_{{1440,960}}.png (compared with the mock's by eye, see the task's evidence)")


# --------------------------------------------------------------------------- ac-live


def live_payload():
    def task(key, word):
        return {"key": key, "title": f"Add {word}.txt", "requirements": [word], "files": [f"{word}.txt"],
                "description": f"Create the file {word}.txt at the repository root holding the single line "
                               f"`{word}`. Change nothing else.",
                "builder": "Builder", "checker": "Checker"}
    words = ("hello", "bye")
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Two notes",
        "summary": "Two one-line files.", "problem": "The repository has no notes.",
        "scope": {"in_scope": ["hello.txt", "bye.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": w, "modal": "MUST", "statement": f"The repository MUST hold {w}.txt reading {w}."}
                         for w in words],
        "acceptance_criteria": [{"key": f"says-{w}", "requirement": w, "given": "the repository checked out",
                                 "when": f"{w}.txt is read", "then": f"it reads {w}", "how_to_check": f"cat {w}.txt",
                                 "checked_by": "agent"} for w in words],
        "tasks": [task("t1", "hello"), task("t2", "bye")],
        "delivery": {"mode": "flow", "agent": "Builder", "stop_when_queue_empties": True, "cron": "0 0 1 1 *",
                     "reasons": {"mode": "Two tasks.", "agent": "Builder builds both."}},
    }


def live_setup(state):
    root = SCRATCH / "live"
    root.mkdir(parents=True, exist_ok=True)

    def git(*args):
        subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                       cwd=root, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the build view drive.\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"buildview-{STAMP}"})
    if code not in (200, 201):
        raise Setup(f"open the live project: {code} {project}")
    pid = project["id"]
    base = f"/projects/{pid}"
    api("PATCH", base, {"main_branch": "main"})
    api("PUT", f"{base}/settings", {"allow_agent_jobs": True})
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    if code not in (200, 201):
        raise Setup(f"a Haiku runner: {code} {runner}")
    for name in ("Builder", "Checker"):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        if code not in (200, 201):
            raise Setup(f"agent {name}: {code} {out}")
    doc = "spec/changes/two-notes/spec.json"
    quoted = urllib.parse.quote(doc)
    for method, path, body in (("POST", f"{base}/project/documents", {"title": "Two notes", "kind": "change-spec", "path": doc}),
                               ("PUT", f"{base}/project/documents/{doc}/content", {"document": live_payload()})):
        code, out = api(method, path, body)
        if code not in (200, 201):
            raise Setup(f"{method} {path}: {code} {str(out)[:400]}")
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True,
                     "content_version": read.get("content_version") if isinstance(read, dict) else None})
    if code != 200:
        raise Setup(f"approve: {code} {str(out)[:400]}")
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builders": ["Builder"], "landing": "main"})
    if code != 200:
        raise Setup(f"build: {code} {str(out)[:400]}")
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    rows = ro("select t.id, t.readable_id, t.spec_task_key, t.loop_id from tasks t join spec_documents d "
              "on d.id=t.spec_document_id where d.project_id=? and d.path=?", (pid, doc))
    tasks = {r["spec_task_key"]: dict(r) for r in rows}
    loop = tasks["t1"]["loop_id"] if "t1" in tasks else None
    job = ro("select job_id from loops where id=?", (loop,))[0]["job_id"] if loop else None
    if not (build_id and job and len(tasks) == 2):
        raise Setup(f"the build runs no flow over both tasks: build={build_id} job={job} tasks={list(tasks)}")
    state.update(live_pid=pid, live_base=base, live_build=build_id, live_job=job, live_tasks=tasks)
    print(f"  live project {pid}, build {build_id}, job {job}, tasks "
          f"{ {k: v['readable_id'] for k, v in tasks.items()} }", flush=True)
    return pid, base, build_id, job, tasks


def live_runs(pid, task_id=None):
    sql = "select id, agent, task_id, status, started_at from runs where project_id=?"
    args = [pid]
    if task_id:
        sql += " and task_id=?"
        args.append(task_id)
    return [dict(r) for r in ro(sql + " order by started_at", args)]


def busy(pid):
    return [r for r in live_runs(pid) if r["status"] in ("running", "queued", "starting")]


def task_status(task_id):
    return ro("select status from tasks where id=?", (task_id,))[0]["status"]


def fire(base, job):
    code, out = api("POST", f"{base}/jobs/{job}/run")
    print(f"  fired {job}: {code} {str(out)[:160]}", flush=True)


SCROLLER_JS = """(el) => {
  let node = el;
  while (node && node !== document.body) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 20) break;
    node = node.parentElement;
  }
  if (!node || node === document.body) node = document.scrollingElement;
  node.setAttribute('data-drive-scroller', 'true');
  return [node.scrollHeight, node.clientHeight];
}"""


def scroll_top(page):
    return page.evaluate("() => (document.querySelector('[data-drive-scroller]') || document.scrollingElement).scrollTop")


def check_live(browser, state):
    key = "ac-live"
    pid, base, build_id, job, tasks = live_setup(state)
    fire(base, job)
    first = poll(lambda: next((t for t in tasks.values() if live_runs(pid, t["id"])), None), 90, every=2)
    if not first:
        raise Setup("the first firing started no builder run")
    second = next(t for t in tasks.values() if t["id"] != first["id"])
    if not poll(lambda: task_status(first["id"]) in ("completed", "under_review", "approved") and not busy(pid),
                TURN_WAIT, every=3):
        raise Setup(f"{first['readable_id']} was not built within {TURN_WAIT}s ({task_status(first['id'])})")
    if live_runs(pid, second["id"]):
        raise Setup(f"{second['readable_id']} was started before the view opened; the drive needs it unstarted")
    first_run = live_runs(pid, first["id"])[0]
    page = new_page(browser, pid, height=560)
    if not open_view(page, pid, build_id):
        shot(page, "live")
        return record(key, False, f"build {build_id} (running): {what_is_there(page)}")
    if not expand(page, first["readable_id"]):
        return record(key, False, f"no row button 'Open runs of {first['readable_id']}' that expands")
    if not run_button(page, "Build 1", first["readable_id"]).count():
        return record(key, False, f"{first['readable_id']}'s timeline has no 'Open trace: Build 1' ({first_run['id']})")
    run_button(page, "Build 1", first["readable_id"]).first.click()
    if not poll(lambda: trace_open_on(page, "Build 1"), 10):
        return record(key, False, "the trace of Build 1 did not open")
    height, client = view(page).first.evaluate(SCROLLER_JS)
    page.evaluate("() => { const n = document.querySelector('[data-drive-scroller]'); n.scrollTop = n.scrollHeight; }")
    page.wait_for_timeout(400)
    top, url = scroll_top(page), page.url
    if top <= 0:
        raise Setup(f"the view does not scroll at 560px high (scrollHeight {height}, clientHeight {client})")
    runs_seen = task_row_runs(page, second["id"])
    shot(page, "live-before")
    fire(base, job)
    started = poll(lambda: live_runs(pid, second["id"]), 120, every=0.25)
    if not started:
        raise Setup(f"the second firing started no run on {second['readable_id']}")
    # FR-15 on a build that is really running: Overview offers its view while the builder's turn runs.
    ov = new_page(browser, pid)
    ov.goto(f"{HUB}/?project={pid}&tab=overview", wait_until="domcontentloaded")
    ov_link = ov.get_by_role("link", name="Open in its build")
    poll(lambda: ov_link.count(), 20)
    ov_opened = None
    if ov_link.count():
        ov_link.first.click()
        ov_opened = poll(lambda: view(ov).first.get_attribute("data-build-id"), 20)
    shot(ov, "live-overview")
    ov.close()
    t0 = time.time()
    shown_run = poll(lambda: (task_row_runs(page, second["id"]) or 0) > (runs_seen or 0), LIVE_LIMIT + 5, every=0.25)
    run_latency = time.time() - t0
    moved = poll(lambda: task_status(second["id"]) in ("completed", "under_review", "approved"), TURN_WAIT, every=0.25)
    t1 = time.time()
    shown_move = poll(lambda: task_row_status(page, second["id"]) in ("completed", "under_review", "approved"),
                      LIVE_LIMIT + 5, every=0.25)
    move_latency = time.time() - t1
    kept_top, kept_url = scroll_top(page), page.url
    # The open trace is modal: the rows behind it are out of the accessibility tree, so ask the DOM.
    expanded = page.locator(f'button[aria-label="Open runs of {first["readable_id"]}"]').first.get_attribute("aria-expanded") == "true"
    trace = trace_open_on(page, "Build 1")
    reloaded = page.evaluate("() => performance.getEntriesByType('navigation').length") != 1
    shot(page, "live-after")
    parts = [
        (f"run shown in {run_latency:.1f}s", bool(shown_run) and run_latency <= LIVE_LIMIT),
        (f"move to completed shown in {move_latency:.1f}s", bool(moved) and bool(shown_move) and move_latency <= LIVE_LIMIT),
        (f"scroll kept ({top}->{kept_top})", abs(kept_top - top) <= 2),
        (f"{first['readable_id']} still expanded", expanded),
        ("trace still open", trace and kept_url == url),
        ("no reload", not reloaded),
        (f"Overview's Open in its build opens the running build ({ov_opened})", ov_opened == build_id),
    ]
    record(key, all(ok for _, ok in parts), f"build {build_id}, {second['readable_id']} run {started[0]['id']}: "
           + "; ".join(f"{p} {'ok' if ok else 'FAILED'}" for p, ok in parts))


def tidy_live(state):
    if state.get("live_build"):
        code, _ = api("POST", f"{state['live_base']}/project/builds/{state['live_build']}/stop")
        print(f"stopped the live build {state['live_build']}: {code}", flush=True)
        poll(lambda: not busy(state["live_pid"]), 120, every=3)


# --------------------------------------------------------------------------- main


def guarded(key, fn, *args):
    try:
        fn(*args)
    except Setup as exc:
        print(f"SETUP {key}: {exc}", flush=True)
        checks.setdefault(key, (False, False, f"not reached: {exc}"))
    except Exception as exc:  # noqa: BLE001 -- a step that broke before its assertion
        print(f"BROKE {key}: {exc!r}", flush=True)
        checks.setdefault(key, (False, False, f"broke before its assertion: {str(exc)[:240]}"))


def main():
    global HUB, KEY, DB
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="the drive's own logic only; no Hub")
    parser.add_argument("--only", default="", help="comma-separated check keys")
    parser.add_argument("--skip-live", action="store_true", help="leave out ac-live (no agent turns)")
    parser.add_argument("--source-db", default=os.environ.get("AW_DRIVE_SOURCE_DB") or str(SOURCE_DB))
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--port", type=int, default=int(os.environ.get("AW_DRIVE_PORT") or 8017))
    parser.add_argument("--hub", default="", help="drive this running Hub instead of a snapshot")
    parser.add_argument("--db", default="", help="with --hub: the database it serves (read only)")
    parser.add_argument("--key", default="", help="with --hub: an operator key")
    parser.add_argument("--keep", action="store_true", help="keep the snapshot and scratch directories")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    wanted = [k for k in ORDER if (not only or k in only) and not (args.skip_live and k == "ac-live")]

    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = None
    if args.hub:
        if args.hub.rstrip("/").endswith(":8000"):
            sys.exit("REFUSING: :8000 is the operator's real instance")
        HUB, KEY, DB = args.hub.rstrip("/"), args.key, pathlib.Path(args.db)
    else:
        if args.port in (8000, 8010):
            sys.exit("REFUSING: the snapshot Hub never takes :8000 or :8010 (use --hub for a running one)")
        HUB, DB = f"http://127.0.0.1:{args.port}", SCRATCH / "snapshot.db"
        if api("GET", "/projects")[0] != 0:
            sys.exit(f"REFUSING: something already answers on :{args.port}; pick another --port")
        KEY = snapshot(pathlib.Path(args.source_db), DB)
    from playwright.sync_api import sync_playwright

    state = {"pid": args.project}
    steps = {"ac-totals": check_totals, "ac-address": check_address, "ac-timeline": check_timeline,
             "ac-fold-checks-loop": check_fold, "ac-trace": check_trace,
             "ac-open-from-drawer": check_open_from_drawer, "ac-summaries-open": check_summaries,
             "ac-unpriced": check_unpriced_and_pairs, "ac-no-fold-pairs": lambda *a: None, "ac-matches-mock": check_matches_mock, "ac-seeded": check_seeded, "ac-live": check_live}
    setup_error = None
    try:
        if not args.hub:
            proc = start_hub(args.port, DB, KEY)
        print(f"output {OUT}", flush=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for key in wanted:
                    guarded(key, steps[key], browser, state)
            finally:
                tidy_live(state)
                browser.close()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        stop_hub(proc)
        if not args.keep and not args.hub:
            # The Hub's and the agents' processes let go of their files a moment after they die.
            for _ in range(5):
                time.sleep(3)
                shutil.rmtree(SCRATCH, ignore_errors=True)
                if not SCRATCH.exists():
                    break
            else:
                print(f"left behind (delete by hand): {SCRATCH}")
    print("\n== drive_baseline")
    failed = False
    for key in wanted:
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if failed_here else 'no'} -- {detail}")
    print(f"output: {OUT}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
