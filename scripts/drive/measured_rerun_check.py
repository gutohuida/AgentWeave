"""Acceptance drive of `spec/changes/the-measured-re-run` (slice H of "Flows that do not stall").

The measurement builds one candidate change twice on the operator's Hub (Fast, then Gated) and
records a four-column comparison in the vault. This script is the check that the measurement is
sound and that the comparison says what the Hub's own views say. It exists first so that it FAILS
while the builds, the note, or the views it needs do not exist, and passes only when they do.

GET requests only. Every Hub call goes through `get`, the one request helper, which refuses any
other method, so it is safe to point at the operator's :8000. It never writes a file either.

    py -3.11 scripts/drive/measured_rerun_check.py [--hub URL] [--project ID] [--document PATH]
        [--candidate | --windows | --budget | --note | --defects | --re-recording | --vault]...

With no mode flag it runs the builds-match check (FR-2). Several mode flags run several checks.
Exit code 0 only when every selected check passed. A route the Hub does not have, or a number no
view shows, is a FAIL with the reason, never a crash (FR-10: such a gap is a finding).

Auth: AW_KEY if set, else the loopback-only GET /setup/token. The project: --project or AW_PROJECT,
default this repository's project on :8000.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DOCUMENT = "spec/changes/every-same-file-overlap-reaches-the-operator/spec.json"
DEFAULT_PROJECT = "proj-d85a82bf4216"
CAP_USD = 30.0
WINDOW = timedelta(hours=8)
TOTAL_CEILING_USD = 65.0

#: The columns the note's table must have (FR-6), matched case-insensitively by substring.
COLUMNS = ("2026-10-25", "2026-10-26", "fast", "gated")
#: (row keyword(s), what the routes answer or None for "no route", label). FR-6 then FR-7.
ROWS = [
    (("tasks",), "tasks", "tasks"),
    (("wall", "total"), "wall.total", "wall time in total"),
    (("wall", "per task"), "wall.per_task", "wall time per task"),
    (("building",), "wall.building", "wall: building"),
    (("waiting for review",), "wall.review", "wall: waiting for review"),
    (("checks",), "wall.checks", "wall: checks"),
    (("handed out",), "wall.waiting", "wall: waiting to be handed out"),
    (("cost", "total"), "cost.total", "cost in total"),
    (("cost", "per task"), "cost.per_task", "cost per task"),
    (("cost", "build"), "cost.build", "cost: building"),
    (("cost", "review"), "cost.review", "cost: reviewing"),
    (("cost", "mend"), "cost.mend", "cost: mender"),
    (("send-back",), "sendbacks", "send-backs"),
    (("real defect",), None, "real defects caught (check/reviewer/operator)"),
    (("escaped",), None, "escaped defects"),
    (("operator action",), None, "operator actions during the build"),
    (("review", "failed"), "beside.count", "L: review turns begun beside a failed check"),
    (("approval", "waited"), None, "M: hours an approval waited on a failure not the task's"),
    (("mender turns",), "mend.runs", "N: mender turns"),
    (("mender cost",), "mend.cost", "N: mender cost"),
    (("mender model",), None, "N: mender model"),
    (("wakes",), None, "N: mender wakes with no stalled work"),
    (("expired",), None, "N: mender questions that expired unanswered"),
]
CLASSES = ("defect", "not the task", "hub")
#: The Gated build's twin of the candidate (F1058); set from --gated-document.
GATED_DOCUMENT: Optional[str] = None

_results: List[Tuple[str, bool, str]] = []


# --- reporting ----------------------------------------------------------------------------------


def report(name: str, ok: bool, why: str) -> bool:
    _results.append((name, ok, why))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {why}")
    return ok


def info(text: str) -> None:
    print(f"  [info] {text}")


# --- the one request helper ---------------------------------------------------------------------


class Hub:
    """GET only. `get` is the single place a request is made, and it refuses any other method."""

    def __init__(self, base: str, project: str) -> None:
        self.base = base.rstrip("/")
        self.project = project
        self._key: Optional[str] = None

    def _request(self, method: str, path: str, auth: bool) -> Tuple[int, Any]:
        if method != "GET":  # the hard rule: this script reads, nothing else
            raise RuntimeError(f"refusing {method}: this drive makes GET requests only")
        req = urllib.request.Request(self.base + path, method="GET")
        if auth:
            req.add_header("Authorization", f"Bearer {self.key()}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw, status = r.read(), r.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read(), exc.code
        except (urllib.error.URLError, OSError) as exc:
            return 0, f"cannot reach {self.base}: {exc}"
        try:
            return status, json.loads(raw or b"null")
        except ValueError:
            return status, raw.decode("utf-8", "replace")

    def key(self) -> str:
        if self._key is None:
            self._key = os.environ.get("AW_KEY") or ""
            if not self._key:
                status, body = self._request("GET", "/api/v1/setup/token", auth=False)
                if status != 200 or not isinstance(body, dict) or "api_key" not in body:
                    raise RuntimeError(f"no AW_KEY and /setup/token answered {status}")
                self._key = body["api_key"]
        return self._key

    def get(self, route: str, /, **query: Any) -> Tuple[int, Any]:
        """GET /api/v1/projects/{project}{path}. Returns (status, body); never raises on HTTP."""
        q = {k: v for k, v in query.items() if v is not None}
        suffix = ("?" + urllib.parse.urlencode(q)) if q else ""
        return self._request("GET", f"/api/v1/projects/{self.project}{route}{suffix}", auth=True)


def ok_body(result: Tuple[int, Any]) -> Optional[Any]:
    return result[1] if result[0] == 200 else None


def why_not(result: Tuple[int, Any]) -> str:
    return f"HTTP {result[0]}: {str(result[1])[:160]}"


# --- reading the app ----------------------------------------------------------------------------


def document_page(hub: Hub, path: str) -> Tuple[Optional[dict], str]:
    """GET /project/spec?path= : the page, whose `builds` lists every build newest first."""
    result = hub.get("/project/spec", path=path)
    body = ok_body(result)
    return (body, "") if isinstance(body, dict) else (None, why_not(result))


def document_row(hub: Hub, path: str) -> Optional[dict]:
    body = ok_body(hub.get("/project/documents"))
    for row in (body or {}).get("documents", []):
        if row.get("path") == path:
            return row
    return None


def figures(hub: Hub, build_id: str) -> Optional[dict]:
    return ok_body(hub.get(f"/project/builds/{build_id}/figures"))


def stats(hub: Hub) -> Optional[dict]:
    return ok_body(hub.get("/stats"))


def build_row(whole: Optional[dict], build_id: str) -> Optional[dict]:
    return ((whole or {}).get("builds") or {}).get(build_id)


def finished_builds(page: dict) -> List[dict]:
    return [b for b in page.get("builds", []) if b.get("state") != "running"]


def by_level(page: dict) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for b in finished_builds(page):
        out.setdefault(b.get("level") or "?", []).append(b)
    return out


def parse_time(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def end_of(b: dict) -> Optional[datetime]:
    return parse_time(b.get("stopped_at")) or parse_time(b.get("window_end"))


def load_two(hub: Hub, path: str, name: str) -> Optional[Tuple[dict, dict, dict]]:
    """(page, fast, gated) or a FAIL naming why not."""
    page, why = document_page(hub, path)
    if page is None:
        report(
            name,
            False,
            f"cannot read the document {path} from the app ({why}); no build of it can exist",
        )
        return None
    if GATED_DOCUMENT and GATED_DOCUMENT != path:
        # A document's build covers only its open tasks, so the Gated build runs on a twin of the
        # candidate with the same payload and fresh tasks (F1058); its builds join the Fast ones.
        twin, why = document_page(hub, GATED_DOCUMENT)
        if twin is None:
            report(name, False, f"cannot read the Gated twin {GATED_DOCUMENT} from the app ({why})")
            return None
        page = {**page, "builds": [*page.get("builds", []), *twin.get("builds", [])]}
    levels = by_level(page)
    fast, gated = levels.get("fast", []), levels.get("gated", [])
    if len(fast) != 1 or len(gated) != 1 or len(finished_builds(page)) != 2:
        found = [f"{b.get('id')}:{b.get('level')}:{b.get('state')}" for b in page.get("builds", [])]
        report(
            name,
            False,
            f"need exactly two finished builds, one fast and one gated; the app lists {len(found)}: "
            f"{found or 'none'}",
        )
        return None
    return page, fast[0], gated[0]


# --- checks -------------------------------------------------------------------------------------


def check_candidate(hub: Hub, path: str) -> None:
    """FR-1: two to four tasks, files under hub/hub and hub/ui (read from the tracked file)."""
    name = "candidate-is-slice-sized"
    file = REPO / path
    if not file.is_file():
        report(name, False, f"{path} does not exist in the checkout yet")
        return
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
    except ValueError as exc:
        report(name, False, f"{path} is not JSON: {exc}")
        return
    tasks = doc.get("tasks") or []
    files = [f.replace("\\", "/") for t in tasks for f in (t.get("files") or [])]
    hub_hub = [f for f in files if f.startswith("hub/hub")]
    hub_ui = [f for f in files if f.startswith("hub/ui")]
    report(name, 2 <= len(tasks) <= 4, f"{len(tasks)} tasks (need 2-4)")
    report(
        name,
        bool(hub_hub) and bool(hub_ui),
        f"{len(hub_hub)} hub/hub and {len(hub_ui)} hub/ui task files",
    )
    row = document_row(hub, path)
    report(
        name, row is not None, "the app tracks the document" if row else "the app does not track it"
    )


def models_by_agent(hub: Hub, build: dict) -> Optional[Dict[str, List[str]]]:
    """The model of each turn in the build's span, from GET /accounting `recent_turns` (a window
    of the latest turns only; the build view names no per-run models)."""
    body = ok_body(hub.get("/accounting"))
    if not isinstance(body, dict):
        return None
    start, end = parse_time(build.get("created_at")), end_of(build) or datetime.now(timezone.utc)
    out: Dict[str, set] = {}
    for turn in body.get("recent_turns", []):
        t = parse_time(turn.get("observed_at"))
        if t and start and start <= t <= end:
            out.setdefault(turn.get("agent") or "?", set()).add(turn.get("model") or "unrecorded")
    return {a: sorted(m) for a, m in out.items()}


def check_builds_match(hub: Hub, path: str) -> None:
    """FR-2."""
    name = "builds-match"
    two = load_two(hub, path, name)
    if two is None:
        return
    _, fast, gated = two
    report(
        name,
        fast.get("driver") == gated.get("driver"),
        f"driver fast={fast.get('driver')!r} gated={gated.get('driver')!r}",
    )
    fb, gb = sorted(fast.get("builders") or []), sorted(gated.get("builders") or [])
    report(name, bool(fb) and fb == gb, f"builders fast={fb} gated={gb}")
    report(name, not (fast.get("reviewers") or []), f"fast reviewers={fast.get('reviewers')}")
    report(name, bool(gated.get("reviewers")), f"gated reviewers={gated.get('reviewers')}")
    # The base commit. The build view (builds.view) carries no such field today.
    bf, bg = fast.get("base_commit"), gated.get("base_commit")
    report(
        name,
        bool(bf) and bf == bg,
        f"base commit fast={bf!r} gated={bg!r}"
        + (
            ""
            if bf or bg
            else " (the build record names no base commit: FR-2 needs one on the build view)"
        ),
    )
    mf, mg = models_by_agent(hub, fast), models_by_agent(hub, gated)
    if mf is None or mg is None:
        report(name, False, "no per-run models: GET /accounting did not answer")
        return
    roles = set(fb) | set(gb)
    same = all(mf.get(a) == mg.get(a) and mf.get(a) for a in roles)
    report(
        name,
        same,
        f"per-agent models of the builders (from /accounting recent_turns, which is the latest turns "
        f"only, not tied to a build) fast={ {a: mf.get(a) for a in roles} } gated={ {a: mg.get(a) for a in roles} }",
    )


def python_processes() -> str:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
        return f"{len([l for l in out.splitlines() if 'python' in l.lower()])} python.exe now"
    except (OSError, subprocess.SubprocessError):
        return "process list unavailable"


def check_windows(hub: Hub, path: str) -> None:
    """FR-3: builds do not overlap; no foreign turn in either window."""
    name = "nothing-overlaps"
    two = load_two(hub, path, name)
    if two is None:
        return
    _, fast, gated = two
    spans = {}
    for label, b in (("fast", fast), ("gated", gated)):
        s, e = parse_time(b.get("created_at")), end_of(b)
        spans[label] = (s, e)
    (fs, fe), (gs, ge) = spans["fast"], spans["gated"]
    if None in (fs, fe, gs, ge):
        report(name, False, f"a build lacks a start or an end: {spans}")
        return
    first, second = sorted([("fast", fs, fe), ("gated", gs, ge)], key=lambda x: x[1])
    report(
        name,
        first[2] <= second[1],
        f"{first[0]} {first[1]:%F %T}..{first[2]:%T}; {second[0]} starts {second[1]:%F %T}",
    )
    report(
        name,
        first[0] == "fast",
        "Fast ran first" if first[0] == "fast" else "Gated ran first (FR-3 says Fast first)",
    )
    body = ok_body(hub.get("/accounting")) or {}
    for label, b in (("fast", fast), ("gated", gated)):
        allowed = set(b.get("builders") or []) | set(b.get("reviewers") or []) | {b.get("lead")}
        s, e = spans[label]
        foreign = {
            t["agent"]
            for t in body.get("recent_turns", [])
            if (when := parse_time(t.get("observed_at")))
            and s <= when <= e
            and t.get("agent") not in allowed
            and "mender" not in (t.get("agent") or "").lower()
        }
        report(
            name,
            not foreign,
            f"{label} window: turns by agents outside the build and the mender: {sorted(foreign) or 'none'} (/accounting recent_turns; no route lists every run)",
        )
    info(
        f"process list (only a snapshot of now; FR-3 needs one saved at each start): {python_processes()}"
    )


def check_budget(hub: Hub, path: str) -> None:
    """FR-5."""
    name = "cap-stops-a-build"
    two = load_two(hub, path, name)
    if two is None:
        return
    page, fast, gated = two
    total = 0.0
    for label, b in (("fast", fast), ("gated", gated)):
        cap, spent = b.get("budget_cap_usd"), b.get("spent_usd") or 0.0
        s, e = parse_time(b.get("window_start")), parse_time(b.get("window_end"))
        report(name, cap == CAP_USD, f"{label} cap ${cap} (need ${CAP_USD:g})")
        report(name, bool(s and e and e - s == WINDOW), f"{label} window {s}..{e} (need {WINDOW})")
        report(name, cap is not None and spent <= cap, f"{label} spent ${spent} against cap ${cap}")
        report(
            name,
            b.get("state") in ("finished", "stopped"),
            f"{label} state={b.get('state')} reason={b.get('stop_reason')!r}",
        )
        total += spent
    same_level = [b for b in page.get("builds", []) if b.get("level") in ("fast", "gated")]
    report(
        name,
        len(same_level) == 2,
        f"{len(same_level)} fast/gated builds in the app (a stopped build is never restarted)",
    )
    report(
        name,
        total <= TOTAL_CEILING_USD,
        f"measurement total ${total:.2f} (inconclusive past ${TOTAL_CEILING_USD:g})",
    )


# --- the note -----------------------------------------------------------------------------------


def find_note(hub: Hub) -> Tuple[Optional[str], str]:
    notes = sorted((REPO / ".agentweave" / "vault-notes").glob("*the-measured-re-run*.md"))
    if notes:
        return notes[-1].read_text(encoding="utf-8"), str(notes[-1])
    return None, "no .agentweave/vault-notes/<date>-the-measured-re-run.md in the checkout"


def parse_table(text: str) -> Tuple[List[str], Dict[str, List[str]]]:
    """The first Markdown table with a header naming Fast and Gated: (header cells, label -> cells)."""
    lines = [l.strip() for l in text.splitlines()]
    for i, line in enumerate(lines):
        if line.startswith("|") and "fast" in line.lower() and "gated" in line.lower():
            header = [c.strip() for c in line.strip("|").split("|")]
            rows: Dict[str, List[str]] = {}
            for row in lines[i + 2 :]:
                if not row.startswith("|"):
                    break
                cells = [c.strip() for c in row.strip("|").split("|")]
                rows[cells[0]] = cells
            return header, rows
    return [], {}


def number(cell: str) -> Optional[float]:
    m = re.search(r"-?\d+(?:\.\d+)?", cell.replace(",", ""))
    return float(m.group()) if m else None


def seconds_of(cell: str) -> Optional[float]:
    t = cell.lower()
    h = re.search(r"(\d+(?:\.\d+)?)\s*h", t)
    m = re.search(r"(\d+(?:\.\d+)?)\s*min", t)
    s = re.search(r"(\d+(?:\.\d+)?)\s*s\b", t)
    if h or m or s:
        return sum(float(x.group(1)) * k for x, k in ((h, 3600), (m, 60), (s, 1)) if x)
    n = number(cell)
    return None if n is None else n * 60  # a bare number in a time row reads as minutes


def route_values(hub: Hub, page: dict, build: dict) -> Dict[str, Optional[float]]:
    """What the app's views answer for one build, keyed like ROWS (seconds / dollars / counts)."""
    fig, row = figures(hub, build["id"]) or {}, build_row(stats(hub), build["id"]) or {}
    tasks = (
        ok_body(
            hub.get(
                "/tasks",
                spec_document_id=(document_row(hub, page.get("path", "")) or {}).get("id"),
                limit=1000,
            )
        )
        or {}
    ).get("tasks")
    n = len(tasks) if tasks is not None else None
    t, c = fig.get("time") or {}, fig.get("cost") or {}
    total_cost = sum(v for v in c.values() if v is not None) if c else None
    wall = {k: t.get(k) for k in ("building", "reviewing", "checks", "held", "review", "waiting")}
    wall_total = sum(v for v in wall.values() if v is not None) if t else None
    sb = (row.get("send_backs") or {}).get("received")
    mend_cost = (row.get("cost_micros") or {}).get("mending")
    return {
        "tasks": n,
        "wall.total": wall_total,
        "wall.per_task": (wall_total / n) if wall_total is not None and n else None,
        "wall.building": wall["building"],
        "wall.review": wall["review"],
        "wall.checks": wall["checks"],
        "wall.waiting": wall["waiting"],
        "cost.total": total_cost,
        "cost.per_task": (total_cost / n) if total_cost is not None and n else None,
        "cost.build": c.get("build"),
        "cost.review": c.get("review"),
        "cost.mend": c.get("mend"),
        "sendbacks": sb,
        "beside.count": (row.get("beside_failing") or {}).get("count"),
        "mend.runs": (row.get("runs") or {}).get("mending"),
        "mend.cost": None if mend_cost is None else mend_cost / 1_000_000,
    }


def check_note(hub: Hub, path: str) -> None:
    """FR-6 and FR-7: the table's columns and rows, and Fast/Gated equal to the routes."""
    name = "columns-complete"
    text, where = find_note(hub)
    if text is None:
        report(name, False, where)
        report("lmn-rows-present", False, "no note to parse")
        return
    info(f"note: {where}")
    header, rows = parse_table(text)
    if not header:
        report(name, False, "no comparison table whose header names Fast and Gated")
        return
    lowered = [h.lower() for h in header]
    col = {}
    for key in COLUMNS:
        idx = next((i for i, h in enumerate(lowered) if key in h and i > 0), None)
        col[key] = idx
        report(
            name,
            idx is not None,
            f"column {key!r}: {'at ' + str(idx) if idx is not None else 'missing from ' + str(header)}",
        )
    labels = {l.lower(): l for l in rows}
    found: Dict[str, str] = {}
    for words, _src, label in ROWS:
        hit = next((orig for low, orig in labels.items() if all(w in low for w in words)), None)
        report(
            "lmn-rows-present" if label[:2] in ("L:", "M:", "N:") else name,
            hit is not None,
            f"row {label!r}: {'present' if hit else 'missing'}",
        )
        if hit:
            found[label] = hit
    for words, _src, label in ROWS:
        if label not in found:
            continue
        for key in COLUMNS:
            i = col.get(key)
            cell = rows[found[label]][i] if i is not None and i < len(rows[found[label]]) else ""
            if not cell.strip() or cell.strip() in ("-", "--", "n/a", "tbd", "TBD"):
                report(name, False, f"row {label!r} has an empty {key!r} cell")
    # Fast/Gated against the routes.
    two = load_two(hub, path, "lmn-rows-present")
    if two is None:
        return
    page, fast, gated = two
    page.setdefault("path", path)
    for key, build in (("fast", fast), ("gated", gated)):
        vals = route_values(hub, page, build)
        i = col.get(key)
        for words, src, label in ROWS:
            if label not in found or i is None:
                continue
            cell = rows[found[label]][i] if i < len(rows[found[label]]) else ""
            group = "lmn-rows-present"
            if src is None or vals.get(src) is None:
                marked = "query" in cell.lower()
                report(
                    group,
                    marked,
                    f"{key} {label!r}: no view shows it"
                    + (
                        " and the cell says 'from a query'"
                        if marked
                        else "; the cell does not say 'from a query' (FR-10: file a finding against the view)"
                    ),
                )
                continue
            routed = vals[src]
            if src.startswith("wall"):
                got, want, tol = seconds_of(cell), routed, 60.0
            elif src.startswith("cost") or src == "mend.cost":
                got, want, tol = number(cell), routed, 0.01
            else:
                got, want, tol = number(cell), routed, 0.0
            report(
                group,
                got is not None and abs(got - want) <= tol,
                f"{key} {label!r}: note {cell!r} ({got}) vs route {want}",
            )


def check_defects(hub: Hub, path: str) -> None:
    """FR-8: every send-back and failed check run listed once, with link, class, reason."""
    name = "every-failure-listed"
    two = load_two(hub, path, name)
    if two is None:
        return
    page, fast, gated = two
    doc = document_row(hub, path) or {}
    tasks = (ok_body(hub.get("/tasks", spec_document_id=doc.get("id"), limit=1000)) or {}).get(
        "tasks"
    ) or []
    failures: List[str] = []
    for t in tasks:
        moves = (ok_body(hub.get(f"/tasks/{t['id']}/transitions")) or {}).get("transitions", [])
        failures += [
            f"{t['id']}:sent-back"
            for m in moves
            if m.get("to_status") in ("revision_needed", "rejected")
        ]
        runs = (ok_body(hub.get(f"/tasks/{t['id']}/checks")) or {}).get("runs", [])
        failures += [f"{t['id']}:check" for r in runs if r.get("state") in ("failed", "error")]
    info(
        f"the app shows {len(failures)} send-backs and failed check runs across {len(tasks)} tasks of the document"
    )
    text, where = find_note(hub)
    if text is None:
        report(name, False, where)
        return
    rows = [
        l
        for l in text.splitlines()
        if l.strip().startswith("|") and re.search(r"task-[0-9a-f]+", l)
    ]
    report(
        name,
        len(rows) == len(failures),
        f"note lists {len(rows)} failures with a task link; the app shows {len(failures)}",
    )
    bad = [l for l in rows if not any(c in l.lower() for c in CLASSES) or len(l.split("|")) < 5]
    report(name, not bad, f"{len(rows) - len(bad)} of {len(rows)} rows carry a class and a reason")
    real = sum(1 for l in rows if re.search(r"\|\s*defect\b", l.lower()))
    m = re.search(r"real defects[^\n]*?(\d+)", text, re.I)
    report(
        name,
        bool(m) and int(m.group(1)) == real,
        f"note says real defects {m.group(1) if m else 'nothing'}; rows classed as defects: {real}",
    )


def check_rerecording(hub: Hub, path: str) -> None:
    """FR-11: recompute the carry-forward rule from the evidence routes."""
    name = "recommendation-follows-rule"
    result = hub.get("/project/spec/evidence")
    body = ok_body(result)
    if not isinstance(body, dict):
        report(name, False, f"GET /project/spec/evidence did not answer ({why_not(result)})")
        return
    pieces = body.get("evidence", [])
    rejudged = failed = 0
    run_ids: set = set()
    for p in pieces:
        reviews = (ok_body(hub.get(f"/project/spec/evidence/{p['id']}/reviews")) or {}).get(
            "reviews", []
        )
        held_at = next((i for i, r in enumerate(reviews) if r.get("decision") == "held"), None)
        if held_at is None or len(reviews) <= held_at + 1:
            continue
        later = reviews[held_at + 1 :]
        rejudged += 1
        failed += 1 if later[-1].get("decision") == "rejected" else 0
        run_ids |= {r["run_id"] for r in later if r.get("run_id")}
    acct = ok_body(hub.get("/accounting")) or {}
    turns = acct.get("recent_turns", [])
    cost = (
        sum((t.get("api_equivalent_usd_micros") or 0) for t in turns if t.get("run_id") in run_ids)
        / 1e6
    )
    total_review = (((stats(hub) or {}).get("total") or {}).get("cost_micros") or {}).get(
        "reviewing"
    )
    info(
        f"{len(pieces)} pieces; judged again after being held: {rejudged}; failed: {failed}; their review cost (latest turns only) ${cost:.2f}"
    )
    if not total_review:
        report(
            name, False, "no project review cost in GET /stats; the 10% share cannot be computed"
        )
        return
    share = cost * 1e6 / total_review
    rule = (
        "keep re-recording"
        if failed
        else ("carry forward" if rejudged >= 5 and share >= 0.10 else "too thin")
    )
    text, where = find_note(hub)
    if text is None:
        report(name, False, f"rule gives {rule!r} (share {share:.0%}); {where}")
        return
    said = next(
        (k for k in ("carry forward", "too thin", "keep re-recording") if k in text.lower()), None
    )
    report(
        name,
        said == rule,
        f"rule gives {rule!r} ({rejudged} re-judged, {failed} failed, share {share:.0%}); note says {said!r}",
    )


def check_vault(hub: Hub, path: str) -> None:
    """FR-12: the note is a dated document source in the map, distilled, and committed."""
    name = "note-in-vault"
    body = ok_body(hub.get("/vault/map"))
    if not isinstance(body, dict):
        report(name, False, "GET /vault/map did not answer")
        return
    entries = body.get("entries", [])
    hit = [
        e
        for e in entries
        if e.get("kind") == "source" and "measured-re-run" in json.dumps(e).lower()
    ]
    if not hit:
        report(
            name, False, f"no entry mentions the measured re-run among {len(entries)} vault entries"
        )
    else:
        e = hit[0]
        info(
            f"entry: { {k: e.get(k) for k in ('id', 'type', 'dated', 'distilled', 'state', 'facts') if k in e} }"
        )
        report(name, e.get("type") == "document", f"type={e.get('type')!r}")
        report(
            name,
            bool(e.get("dated") or e.get("date")),
            f"dated={e.get('dated') or e.get('date')!r}",
        )
        # The map lists facts as entries of their own, each naming the source it cites; a
        # source entry carries no count of them.
        citing = [f for f in entries if f.get("kind") == "fact" and e.get("id") in json.dumps(f)]
        report(
            name,
            bool(citing),
            (
                f"distillation produced {len(citing)} facts that cite it"
                if citing
                else "no facts cite it"
            ),
        )
    out = subprocess.run(
        ["git", "ls-files", "knowledge/sources"], cwd=REPO, capture_output=True, text=True
    ).stdout
    sid = hit[0].get("id") if hit else None
    report(
        name,
        bool(sid)
        and f"knowledge/sources/{sid}.md" in out
        and f"knowledge/sources/{sid}.json" in out,
        f"git tracks .md and .json for {sid!r}" if sid else "no source id to look up",
    )


# --- main ---------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hub", default=os.environ.get("AW_HUB", "http://127.0.0.1:8000"))
    ap.add_argument("--project", default=os.environ.get("AW_PROJECT", DEFAULT_PROJECT))
    ap.add_argument("--document", default=DEFAULT_DOCUMENT)
    ap.add_argument(
        "--gated-document", default=DEFAULT_DOCUMENT.replace("/spec.json", "-at-gated/spec.json")
    )
    modes = ["candidate", "windows", "budget", "note", "defects", "re-recording", "vault"]
    for m in modes:
        ap.add_argument(f"--{m}", action="store_true")
    args = ap.parse_args()
    global GATED_DOCUMENT
    GATED_DOCUMENT = args.gated_document
    hub = Hub(args.hub, args.project)
    chosen = [m for m in modes if getattr(args, m.replace("-", "_"))] or ["builds-match"]
    table = {
        "builds-match": check_builds_match,
        "candidate": check_candidate,
        "windows": check_windows,
        "budget": check_budget,
        "note": check_note,
        "defects": check_defects,
        "re-recording": check_rerecording,
        "vault": check_vault,
    }
    print(f"measured re-run drive: {args.hub} project {args.project}\n  document {args.document}")
    for mode in chosen:
        print(f"-- {mode}")
        try:
            table[mode](hub, args.document)
        except Exception as exc:  # noqa: BLE001 -- a broken check is a failed check, legibly
            report(mode, False, f"check raised {type(exc).__name__}: {exc}")
    failed = [r for r in _results if not r[1]]
    print(f"\n{len(_results) - len(failed)} passed, {len(failed)} failed")
    return 0 if _results and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
