"""Generate `spec-queue/BACKLOG.html` — the standing orientation page.

Two readers, one page. An agent waking into this repository needs to know where authority lives
and what is already open before it proposes anything; the operator needs to know what the loop is
holding and what is waiting on them. Both questions are answered by files that already exist —
`scripts/drive/FINDINGS.md`, `openspec/changes/`, `spec-queue/` and the two `STATE-*.json` — so
this reads them rather than restating them.

**It is generated, never edited.** A hand-maintained backlog page is the failure mode
`night-window.md` already names: *"a backlog that cannot say what is done is read as a backlog of
everything."* The ledger has twice been measurably wrong about its own open list. Regenerate with:

    py -3.11 scripts/backlog_page.py

The cycle clock on the page is computed in the browser, not baked in, so the window marker stays
truthful even when the data behind it is a day old. The page states its own generation time for
exactly that reason.
"""

from __future__ import annotations

import html
import io
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "scripts" / "drive" / "FINDINGS.md"
REQUESTS = ROOT / "spec-queue" / "REQUESTS.md"
CHANGES = ROOT / "openspec" / "changes"
QUEUE = ROOT / "spec-queue"
STATE_DIR = ROOT / ".claude" / "autonomous"
OUT = QUEUE / "BACKLOG.html"

SEV_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "?": 4}

#: Where an item came from. The operator asked for the distinction between *"things found on the
#: run"* and *"improvements requested by me"*, and it is a real one: a defect found by driving is
#: evidence, a request is a preference, and the two earn their place in a queue differently.
SOURCES = {
    "operator": "you asked for it",
    "drive": "found by exercising the product",
    "audit": "found by reading code, routes or the bundle",
    "review": "found by an adversarial round on a proposal",
    "unknown": "the Status line does not say",
}

#: How close an item is to being workable. `proposed` is computed from `openspec/changes/`, the
#: rest are read off the ledger. The night window cannot build a finding with no proposal --
#: `night-window.md` is explicit -- so this column is what says whether an A is actually available.
READY = {
    "proposed": "a change directory names it",
    "ready": "measured, severity set — a spec loop could take it",
    "triage": "missing a Status line or a severity",
    "parked": "waiting on a decision",
    "thinking": "an idea, not yet worked out",
}

#: Theme keywords, scored against title (weight 3) and status/body head (weight 1); highest score
#: wins, ties broken by the order here. Deliberately a flat keyword map and not a taxonomy: it is a
#: reading aid for a 200-row page, and a wrong guess costs a reader one glance. `**Theme:**` in a
#: finding's body overrides it outright, which is the escape hatch for anything this misreads.
THEMES: dict[str, tuple[str, ...]] = {
    "Flows & loops": ("flow", "loop", "job", "scheduler", "firing", "cron", "window", "staffs", "staffed", "dispatch"),
    "Task ledger": ("task", "transition", "assignee", "dependency", "prerequisite", "under_review", "approval", "approved", "board", "ledger"),
    "Spec & requirements": ("spec", "document", "requirement", "phase", "proposal", "coverage", "drift", "rigor", "capability"),
    "Evidence": ("evidence", "digest", "footprint", "decide_evidence"),
    "Agents & runners": ("agent", "runner", "charter", "catalog", "roster", "model", "template", "launchability"),
    "Messaging & queue": ("message", "queue", "hop", "delivery", "delivered", "conversation", "inbound", "recipient", "sender"),
    "Workspace & permissions": ("workspace", "permission", "sandbox", "guard", "boundary", "posture", "outside your workspace", "allow"),
    "Git & worktrees": ("git", "worktree", "branch", "commit", "merge", "conflict", "checkout", "rebase"),
    "Operator surfaces": ("ui", "screen", "panel", "page", "button", "dialog", "renders", "surface", "operator surface", "no operator", "settings", "card", "badge"),
    "Runs & turns": ("run", "turn", "session", "checkpoint", "context", "transcript", "spawn", "pid", "heartbeat"),
    "Harness & CI": ("test", "suite", "ci", "harness", "lint", "flake", "mutation", "pytest", "fixture"),
    "Hub plumbing": ("sse", "event", "route", "api", "500", "database", "lock", "migration", "endpoint", "serialise", "pydantic"),
}


# --------------------------------------------------------------------------- findings

def parse_findings() -> list[dict]:
    """Every `## F<n>` section, with the state its Status line claims.

    **Two heading forms, and both must be read.** 349 sections carry `## F<n> (SEV) — title`; 28
    older ones carry `## F<n> — title` with no parenthetical, and matching only the first form drops
    them silently — which is precisely the defect this page exists to stop the ledger having. Where
    no severity is declared anywhere, the finding is bucketed under `?` and *shown*, never hidden.

    A handful of ids carry two `##` sections (a later re-measurement written as its own heading).
    The first is kept, because it is the one the Status line convention attaches to.
    """
    text = FINDINGS.read_text(encoding="utf-8", errors="replace")
    pat = re.compile(r"^##\s*(F\d+[a-z]?)\s*(?:\(([^)]*)\))?\s*.\s*(.+)$", re.M)
    hits = list(pat.finditer(text))
    out: list[dict] = []
    seen: set[str] = set()
    for i, m in enumerate(hits):
        fid = m.group(1)
        if fid in seen:
            continue
        seen.add(fid)
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = text[m.end() : end]
        status = re.search(r"\*\*Status:\*\*\s*(.+)", body)
        raw = status.group(1).strip() if status else ""
        title = m.group(3).strip()
        state = classify(raw, title)
        sev = recover_sev(m.group(2), title, body)
        out.append(
            {
                "kind": "finding",
                "id": fid,
                "num": int(re.sub(r"\D", "", fid) or 0),
                "sev": sev,
                "title": title,
                "status": raw,
                "state": state,
                "source": classify_source(body, raw),
                "theme": classify_theme(body, title, raw),
                "ready": classify_ready(body, raw, state, sev),
                "note": "",
            }
        )
    return out


def classify_source(body: str, status: str) -> str:
    """Where an item came from. An explicit `**Source:**` line wins; otherwise infer.

    Inference reads the Status line, which by convention names who filed it and how ("Filed
    2026-09-15 by the night window's drive of…", "found by an adversarial verification round…").
    It is a convention and not a schema, so this is a best guess and says `unknown` when it has
    none — never a confident wrong answer.
    """
    explicit = re.search(r"^\*\*Source:\*\*\s*(\w+)", body, re.M)
    if explicit and explicit.group(1).lower() in SOURCES:
        return explicit.group(1).lower()

    t = re.sub(r"[*_`]", "", status + " " + body[:1500]).lower()
    if "operator" in t[:200] and any(k in t[:200] for k in ("asked", "requested", "wants")):
        return "operator"

    # Read the body, not only the Status line. The Status line records *fix* state -- "open (no fix
    # commit references it)" -- and for most of the older corpus says nothing about how the finding
    # was found. The body does: a drive says it reproduced something, an audit says it measured a
    # count against a path. Scored, because a single keyword is not enough; `audit` and `review`
    # carry double weight because their phrases are specific while `drive`'s are ordinary words.
    scores = {
        "review": sum(2 for k in _REVIEW_WORDS if k in t),
        "audit": sum(2 for k in _AUDIT_WORDS if k in t),
        "drive": sum(1 for k in _DRIVE_WORDS if k in t),
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "unknown"


_DRIVE_WORDS = (
    "drove", "driven", "driving", "drive", "reproduc", "live", "real turn", "probe", "e2e",
    "measured on", "observed", "hub restarted", "from loopengine", "on :8000", "ran the",
    "watched", "fired",
)
_AUDIT_WORDS = (
    "measured against", "occurrences anywhere", "read, not driven", "code read", "grep",
    "sweep", "audit", "reachability", "row-9", "static", "bundle this hub actually serves",
    "substring hits",
)
_REVIEW_WORDS = (
    "adversarial", "verification round", "review round", "-r2", "-r3", "opus review",
)


def classify_theme(body: str, title: str, status: str) -> str:
    explicit = re.search(r"^\*\*Theme:\*\*\s*(.+)$", body, re.M)
    if explicit:
        return explicit.group(1).strip()
    hay_title = title.lower()
    hay_rest = (status + " " + body[:600]).lower()
    best, best_score = "Unclassified", 0
    for theme, words in THEMES.items():
        score = sum(3 for w in words if w in hay_title) + sum(1 for w in words if w in hay_rest)
        if score > best_score:
            best, best_score = theme, score
    return best


def classify_ready(body: str, status: str, state: str, sev: str) -> str:
    explicit = re.search(r"^\*\*Ready:\*\*\s*(\w+)", body, re.M)
    if explicit and explicit.group(1).lower() in READY:
        return explicit.group(1).lower()
    t = re.sub(r"[*_`]", "", status).lower()
    if state == "no-status" or sev == "?":
        return "triage"
    if any(k in t for k in ("parked", "deferred", "undecided", "operator's call", "operator's undecided")):
        return "parked"
    return "ready"


def parse_requests() -> list[dict]:
    """`spec-queue/REQUESTS.md` — what the operator asked for, which is not a defect ledger.

    A request naming a `Finding:` does **not** become its own row; it re-sources that finding as
    operator-originated and lends it the operator's own words. That is what keeps an ask that has
    already been measured into a finding from being counted twice.
    """
    if not REQUESTS.exists():
        return []
    text = REQUESTS.read_text(encoding="utf-8", errors="replace")
    pat = re.compile(r"^##\s*(R\d+)\s*.\s*(.+)$", re.M)
    hits = list(pat.finditer(text))
    out: list[dict] = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = text[m.end() : end]

        def field(name: str, default: str = "") -> str:
            f = re.search(rf"^\*\*{name}:\*\*\s*(.+)$", body, re.M)
            return f.group(1).strip() if f else default

        prose = re.sub(r"^\*\*\w+:\*\*.*$", "", body, flags=re.M).strip()
        prose = re.sub(r"\s+", " ", prose.split("---")[0]).strip()
        out.append(
            {
                "kind": "request",
                "id": m.group(1),
                "num": int(re.sub(r"\D", "", m.group(1)) or 0),
                "sev": "—",
                "title": m.group(2).strip(),
                "status": f"asked {field('Asked', 'date not given')}",
                "state": "open",
                "source": "operator",
                "theme": field("Theme", "Unclassified"),
                "ready": (field("Ready", "thinking").lower() if field("Ready") else "thinking"),
                "finding": field("Finding"),
                "note": prose[:400],
            }
        )
    return out


def proposed_findings() -> set[str]:
    """F-numbers named by a live (non-archived) change directory — those have a proposal already."""
    named: set[str] = set()
    if not CHANGES.is_dir():
        return named
    for d in CHANGES.iterdir():
        if not d.is_dir() or d.name == "archive":
            continue
        for f in d.rglob("*.md"):
            try:
                named.update(re.findall(r"\bF\d{1,3}\b", f.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                continue
    return named


def recover_sev(paren: str | None, title: str, body: str) -> str:
    """Severity from the heading, else the body's own declaration, else `?`."""
    if paren:
        letter = normalise_sev(paren)
        if letter != "?":
            return letter
    m = re.search(r"severity\s+([ABCD])\b", title, re.I) or re.search(
        r"\*\*Severity:?\*\*[:\s]*([ABCD])\b", body
    )
    return m.group(1).upper() if m else "?"


def normalise_sev(raw: str) -> str:
    """`A`, `A-`, `B, harness`, `C, bookkeeping` all reduce to their letter."""
    m = re.match(r"\s*([ABCD])", raw.strip())
    return m.group(1) if m else "?"


def classify(status: str, title: str) -> str:
    plain = re.sub(r"[*_`~]", "", status).strip().lower()
    if "retired" in plain[:80] or title.strip().upper().startswith("RETIRED"):
        return "retired"
    if not plain:
        return "no-status"
    if plain.startswith("fixed") or re.match(r"^\S*\s*fixed\b", plain):
        return "fixed"
    if "partially" in plain[:60]:
        return "open"
    if plain.startswith("open") or "still open" in plain[:60]:
        return "open"
    if "not a defect" in plain[:80] or "does not reproduce" in plain[:80]:
        return "closed"
    return "other"


# --------------------------------------------------------------------------- changes

def parse_changes() -> list[dict]:
    """Change directories with at least one unticked task — the drain, as the playbook counts it.

    Each entry also carries the **full proposal text** and the round log, so `BACKLOG.html` can
    render a proposal for the operator to read in place rather than only naming it. Asked for by
    the operator 2026-09-19: *"those should be linked in the backlog file and rendered there as
    well so I can easily read them"* — the point of the day window is to produce something they
    can read and approve, and a filename is not that.
    """
    out: list[dict] = []
    if not CHANGES.is_dir():
        return out
    for d in sorted(CHANGES.iterdir()):
        if not d.is_dir() or d.name == "archive":
            continue
        tasks = d / "tasks.md"
        done = todo = 0
        if tasks.exists():
            t = tasks.read_text(encoding="utf-8", errors="replace")
            done = len(re.findall(r"^\s*- \[x\]", t, re.M | re.I))
            todo = len(re.findall(r"^\s*- \[ \]", t, re.M))
        note = ""
        proposal = ""
        prop = d / "proposal.md"
        if prop.exists():
            proposal = prop.read_text(encoding="utf-8", errors="replace")
            stop = re.search(r"^##\s*(STOPPED[^\n]*)", proposal[:1500], re.M)
            if stop:
                note = stop.group(1).strip()

        # The round log lives in design.md under `## Rounds`. It is the single most useful thing
        # to read before approving: it records which arguments have already been refuted, and
        # this repo's round discipline exists because re-proposing a refuted one costs a window.
        rounds_md, rounds_n = "", 0
        design = d / "design.md"
        if design.exists():
            dt = design.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^##\s*Rounds\s*$(.*?)(?=^##\s|\Z)", dt, re.M | re.S)
            if m:
                rounds_md = m.group(1).strip()
                rounds_n = len(re.findall(r"^###?\s*R\d+\b", rounds_md, re.M)) or len(
                    re.findall(r"\bR(\d+)\b", rounds_md)
                ) and max(int(x) for x in re.findall(r"\bR(\d+)\b", rounds_md))

        specs = sorted(p.name for p in (d / "specs").glob("*/spec.md")) if (d / "specs").is_dir() else []
        out.append(
            {
                "name": d.name,
                "done": done,
                "todo": todo,
                "note": note,
                "proposal": proposal,
                "rounds_md": rounds_md,
                "rounds": rounds_n,
                "has_design": design.exists(),
                "has_tasks": tasks.exists(),
                "has_guide": (d / "test-guide.md").exists(),
                "spec_count": len(specs),
            }
        )
    return out


# --------------------------------------------------------------------------- spec-queue

def newest_section(path: Path) -> tuple[str, str]:
    """The newest `## YYYY-MM-DD` section of a spec-queue file: (date, body).

    **Newest by date, not by position.** These files declare "newest day first" and are written
    by hand, so the convention is a promise nobody enforces — and on 2026-09-19 it was found
    broken: the 09-18 and 09-19 sections had been appended at the *bottom*, so a positional read
    returned 09-16 and this page showed the operator a three-day-stale approvals section as
    "newest". Sorting by the date the heading actually carries cannot drift that way.
    """
    if not path.exists():
        return ("", "")
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = list(re.finditer(r"^##\s*(\d{4}-\d{2}-\d{2})\s*$", text, re.M))
    if not hits:
        return ("", "")
    bounds = [(h, (hits[i + 1].start() if i + 1 < len(hits) else len(text))) for i, h in enumerate(hits)]
    newest, end = max(bounds, key=lambda b: b[0].group(1))
    return (newest.group(1), text[newest.end() : end].strip())


def approvals_rows(body: str) -> list[tuple[str, str, str]]:
    rows = []
    for m in re.finditer(r"^-\s+(APPROVED|REVISING|REJECTED)\s+(\S+)\s*(.*)$", body, re.M):
        rows.append((m.group(1), m.group(2), m.group(3).strip()))
    return rows


def directive(body: str, word: str) -> str:
    m = re.search(rf"^{word}:\s*(.+)$", body, re.M)
    return m.group(1).strip() if m else ""


def load_state(name: str) -> dict:
    p = STATE_DIR / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------- render

def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def md(text: str, *, demote: int = 1) -> str:
    """Enough Markdown to read a proposal in a browser. Deliberately small.

    Handles headings, fenced code, blockquotes, bullet and numbered lists, tables, horizontal
    rules, paragraphs, and inline `code`/**bold**/*italic*/[links]. Everything is escaped first,
    so a proposal containing HTML renders as the text it is — these files are written by agents
    and the page must not become an injection surface for them.

    `demote` shifts heading levels so a proposal's own `#` does not compete with the page's `<h2>`.
    """
    src = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    lines = src.split("\n")
    i = 0
    list_stack: list[str] = []

    def close_lists(to: int = 0) -> None:
        while len(list_stack) > to:
            out.append(f"</{list_stack.pop()}>")

    def inline(s: str) -> str:
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(
            r"\[([^\]]+)\]\(([^)\s]+)\)",
            lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>',
            s,
        )
        return s

    while i < len(lines):
        ln = lines[i]

        if ln.startswith("```"):
            close_lists()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{esc(chr(10).join(buf))}</code></pre>")
            continue

        if re.match(r"^\s*(---+|\*\*\*+|___+)\s*$", ln):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if h:
            close_lists()
            lvl = min(6, len(h.group(1)) + demote)
            out.append(f"<h{lvl}>{inline(h.group(2).strip())}</h{lvl}>")
            i += 1
            continue

        # A table: a header row, a separator of dashes, then body rows.
        if "|" in ln and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            close_lists()

            def cells(r: str) -> list[str]:
                return [c.strip() for c in r.strip().strip("|").split("|")]

            head = cells(ln)
            i += 2
            body = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                body.append(cells(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tb = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body
            )
            out.append(f'<div class="scroll"><table class="md"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>')
            continue

        q = re.match(r"^>\s?(.*)$", ln)
        if q:
            close_lists()
            buf = []
            while i < len(lines) and re.match(r"^>\s?", lines[i]):
                buf.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{md(chr(10).join(buf), demote=demote)}</blockquote>")
            continue

        b = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", ln)
        if b:
            depth = len(b.group(1)) // 2 + 1
            tag = "ul" if b.group(2) in "-*+" else "ol"
            while len(list_stack) > depth:
                out.append(f"</{list_stack.pop()}>")
            while len(list_stack) < depth:
                out.append(f"<{tag}>")
                list_stack.append(tag)
            item = b.group(3)
            # A task checkbox reads better as a mark than as literal brackets.
            item = re.sub(r"^\[([ xX])\]\s*", lambda m: "☑ " if m.group(1).lower() == "x" else "☐ ", item)
            out.append(f"<li>{inline(item)}</li>")
            i += 1
            continue

        if not ln.strip():
            close_lists()
            i += 1
            continue

        close_lists()
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|>|\s*([-*+]|\d+[.)])\s)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")

    close_lists()
    return "\n".join(out)


def previous_snapshot() -> dict:
    """The counts the last generation embedded, so a regeneration can report what moved.

    Read from the page's own `<script type="application/json">` block rather than by scraping the
    rendered numbers: the markup is free to change, the snapshot's shape is not. Missing or
    unparseable means "no previous run", which is not an error — the first generation has nothing
    to compare against.
    """
    if not OUT.exists():
        return {}
    try:
        text = OUT.read_text(encoding="utf-8", errors="replace")
        m = re.search(
            r'<script type="application/json" id="backlog-data">(.*?)</script>', text, re.S
        )
        return json.loads(m.group(1)) if m else {}
    except Exception:
        return {}


#: Snapshot keys that say something about the ledger rather than about when the page was built.
#: `generated`, `sha` and `branch` move on every run and every commit, so comparing them makes
#: `--check` answer "has anything happened at all", which is not the question.
VOLATILE_KEYS = {"generated", "sha", "branch"}


def substantive(snap: dict) -> dict:
    return {k: v for k, v in snap.items() if k not in VOLATILE_KEYS}


def report_delta(prev: dict, now: dict) -> list[str]:
    """Plain lines naming what changed. Empty list means nothing moved."""
    if not prev:
        return ["no previous snapshot — first generation, nothing to compare"]
    lines: list[str] = []

    def moved(key: str, label: str, good_down: bool = True) -> None:
        a, b = prev.get(key), now.get(key)
        if a is None or b is None or a == b:
            return
        d = b - a
        arrow = "+" if d > 0 else ""
        flag = ""
        if good_down:
            flag = "  <-- grew" if d > 0 else "  <-- drained"
        lines.append(f"{label}: {a} -> {b} ({arrow}{d}){flag}")

    moved("open", "open findings")
    moved("fixed", "fixed", good_down=False)
    moved("filed", "total filed", good_down=False)
    moved("drain", "unbuilt changes")
    for sev in ("A", "B", "C", "D", "?"):
        moved(f"sev_{sev}", f"  severity {sev}")

    new_ids = sorted(set(now.get("ids", [])) - set(prev.get("ids", [])))
    if new_ids:
        lines.append(f"newly filed: {', '.join(new_ids)}")
    gone = sorted(set(prev.get("open_ids", [])) - set(now.get("open_ids", [])))
    if gone:
        lines.append(f"no longer open: {', '.join(gone)}")
    return lines or ["nothing moved since the last generation"]


def consistency_warnings(findings: list[dict], changes: list[dict]) -> list[str]:
    """Things the ledger says about itself that do not hold up.

    The night playbook calls the status sweep *"the step whose absence makes source 2 wrong"* — the
    ledger has twice under-reported its own open list. These are the cheap checks; none of them is
    conclusive on its own, which is why they are warnings and not failures.
    """
    warn: list[str] = []
    nostatus = [f["id"] for f in findings if f["state"] == "no-status"]
    if nostatus:
        warn.append(
            f"{len(nostatus)} of {len(findings)} findings have no **Status:** line, so nothing says "
            f"whether they are done (they are counted as open): {', '.join(nostatus[:12])}"
            f"{' ...' if len(nostatus) > 12 else ''}"
        )
    unrated = [f["id"] for f in findings if f["sev"] == "?"]
    if unrated:
        open_unrated = sum(1 for f in findings if f["sev"] == "?" and f["state"] in ("open", "no-status"))
        warn.append(
            f"{len(unrated)} of {len(findings)} findings declare no severity anywhere, so the night "
            f"window cannot order them ({open_unrated} of those are open — the page's '?' group): "
            f"{', '.join(unrated[:12])}{' ...' if len(unrated) > 12 else ''}"
        )
    # A finding whose status still reads `open` while naming a commit sha is the classic stale row.
    suspicious = [
        f["id"]
        for f in findings
        if f["state"] == "open" and re.search(r"\b[0-9a-f]{7,40}\b", f["status"] or "")
    ]
    if suspicious:
        warn.append(
            f"{len(suspicious)} findings read 'open' but name a commit sha — verify before "
            f"trusting the open count: {', '.join(suspicious[:12])}"
            f"{' ...' if len(suspicious) > 12 else ''}"
        )
    stopped = [c["name"] for c in changes if c["todo"] > 0 and c["note"]]
    if stopped:
        warn.append(
            f"{len(stopped)} unbuilt change(s) carry a STOPPED note and still count toward the "
            f"drain: {', '.join(stopped)}"
        )
    return warn
def build() -> tuple[str, dict, list[dict], list[dict]]:
    """Returns (html, snapshot, items, changes) — the snapshot is what the next run compares to."""
    findings = parse_findings()
    requests = parse_requests()

    # A request that names a finding re-sources that finding rather than adding a row (see
    # `parse_requests`). Its prose is lent to the finding so the operator's own words survive.
    by_id = {f["id"]: f for f in findings}
    standalone: list[dict] = []
    for r in requests:
        target = by_id.get(r.get("finding") or "")
        if target is not None:
            target["source"] = "operator"
            target["note"] = r["note"]
            target["request_id"] = r["id"]
            if r["ready"] in READY:
                target["ready"] = r["ready"]
            if r["theme"] and r["theme"] != "Unclassified":
                target["theme"] = r["theme"]
        else:
            standalone.append(r)

    # `proposed` is computed, never claimed: a change directory naming the finding is the only
    # thing that makes it buildable by the night window.
    proposed = proposed_findings()
    for f in findings:
        if f["id"] in proposed and f["state"] in ("open", "no-status"):
            f["ready"] = "proposed"

    openf = [f for f in findings if f["state"] in ("open", "no-status")]
    items = openf + standalone
    items.sort(key=lambda f: (SEV_ORDER.get(f["sev"], 9), -f["num"]))

    by_sev: dict[str, list[dict]] = {}
    for f in openf:
        by_sev.setdefault(f["sev"], []).append(f)
    counts = {k: len(v) for k, v in by_sev.items()}

    src_counts: dict[str, int] = {}
    ready_counts: dict[str, int] = {}
    theme_counts: dict[str, int] = {}
    for f in items:
        src_counts[f["source"]] = src_counts.get(f["source"], 0) + 1
        ready_counts[f["ready"]] = ready_counts.get(f["ready"], 0) + 1
        theme_counts[f["theme"]] = theme_counts.get(f["theme"], 0) + 1

    total_open = len(openf)
    total_items = len(items)
    total_fixed = sum(1 for f in findings if f["state"] == "fixed")
    total_retired = sum(1 for f in findings if f["state"] == "retired")

    changes = parse_changes()
    drain = [c for c in changes if c["todo"] > 0]

    ap_date, ap_body = newest_section(QUEUE / "APPROVALS.md")
    di_date, di_body = newest_section(QUEUE / "DIRECTION.md")
    rows = approvals_rows(ap_body)
    order = directive(ap_body, "ORDER")
    nothing = "NOTHING TONIGHT" in ap_body

    day, night = load_state("STATE-day.json"), load_state("STATE-night.json")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    sha = git("rev-parse", "--short", "HEAD")
    dirty = git("status", "--porcelain")
    now = datetime.now(timezone.utc).astimezone()

    # Which unbuilt changes are waiting on the OPERATOR, as opposed to waiting on a night.
    # Decided 2026-09-19 (`DECISIONS.md`, day-window-spec-gate): an APPROVED change waits on a
    # night, and must not suppress tomorrow's proposal. Counting every unbuilt change is what
    # starved 2026-09-16..09-19 — four days on which the window produced nothing to read.
    decided_names = {name for token, name, _ in rows if token in ("APPROVED", "REJECTED")}
    for c in changes:
        c["awaiting_operator"] = c["todo"] > 0 and c["name"] not in decided_names
        c["token"] = next((t for t, n, _ in rows if n == c["name"]), "")
    awaiting = [c for c in drain if c["awaiting_operator"]]

    loops = 2 if len(awaiting) == 0 else (1 if len(awaiting) == 1 else 0)
    loop_word = {0: "no spec loop", 1: "one spec loop", 2: "two spec loops"}[loops]

    # ---- rows ------------------------------------------------------------

    def row(f: dict) -> str:
        sev = f["sev"]
        note = (
            f'<p class="i-note">{esc(f["note"])}</p>'
            if f.get("note")
            else ""
        )
        req = (
            f'<span class="chip c-req">{esc(f["request_id"])}</span>'
            if f.get("request_id")
            else ""
        )
        return (
            f'<article class="item" data-sev="{esc(sev)}" data-source="{esc(f["source"])}" '
            f'data-ready="{esc(f["ready"])}" data-theme="{esc(f["theme"])}" '
            f'data-kind="{esc(f["kind"])}" '
            f'data-text="{esc((f["id"] + " " + f["title"] + " " + f["theme"]).lower())}">'
            f'<div class="i-head">'
            f'<span class="i-id">{esc(f["id"])}</span>'
            f'<span class="chip c-sev" data-sev="{esc(sev)}">{esc(sev)}</span>'
            f'<span class="chip c-src" data-source="{esc(f["source"])}">{esc(f["source"])}</span>'
            f'<span class="chip c-rdy" data-ready="{esc(f["ready"])}">{esc(f["ready"])}</span>'
            f"{req}"
            f"</div>"
            f'<p class="i-title">{esc(f["title"])}</p>'
            f"{note}"
            f"</article>"
        )

    theme_groups = []
    for theme in sorted(theme_counts, key=lambda t: (-theme_counts[t], t)):
        members = [f for f in items if f["theme"] == theme]
        inner = "\n".join(row(f) for f in members)
        theme_groups.append(
            f'<section class="group collapsed" data-group="{esc(theme)}">'
            f'<button class="g-head" type="button" aria-expanded="false">'
            f'<span class="g-caret" aria-hidden="true">▾</span>'
            f'<span class="g-name">{esc(theme)}</span>'
            f'<span class="g-n"><b class="g-shown">{len(members)}</b> of {len(members)}</span>'
            f"</button>"
            f'<div class="g-body">{inner}</div>'
            f"</section>"
        )

    sev_labels = {
        "A": "Wrong behaviour an operator will act on",
        "B": "Wrong or misleading surface",
        "C": "Friction and vestige",
        "D": "Minor",
        "?": "No severity declared",
        "—": "Requests (not defects)",
    }
    sev_groups = []
    for sev in sorted({f["sev"] for f in items}, key=lambda s: SEV_ORDER.get(s, 9)):
        members = [f for f in items if f["sev"] == sev]
        inner = "\n".join(row(f) for f in members)
        sev_groups.append(
            f'<section class="group collapsed" data-group="{esc(sev)}">'
            f'<button class="g-head" type="button" aria-expanded="false">'
            f'<span class="g-caret" aria-hidden="true">▾</span>'
            f'<span class="g-name">{esc(sev)} — {esc(sev_labels.get(sev, ""))}</span>'
            f'<span class="g-n"><b class="g-shown">{len(members)}</b> of {len(members)}</span>'
            f"</button>"
            f'<div class="g-body">{inner}</div>'
            f"</section>"
        )

    def filter_chips(name: str, counts_map: dict, order_keys, describe: dict) -> str:
        out = [f'<button class="f-chip is-on" data-filter="{name}" data-value="" type="button">all</button>']
        for k in order_keys:
            if not counts_map.get(k):
                continue
            out.append(
                f'<button class="f-chip" data-filter="{name}" data-value="{esc(k)}" '
                f'type="button" title="{esc(describe.get(k, ""))}">{esc(k)}'
                f'<span class="f-n">{counts_map[k]}</span></button>'
            )
        return "".join(out)

    source_chips = filter_chips("source", src_counts, ["operator", "drive", "audit", "review", "unknown"], SOURCES)
    ready_chips = filter_chips("ready", ready_counts, ["proposed", "ready", "parked", "triage", "thinking"], READY)
    sev_chips = filter_chips("sev", {k: len([f for f in items if f["sev"] == k]) for k in sev_labels},
                             ["A", "B", "C", "D", "?", "—"], sev_labels)

    def change_block(c: dict) -> str:
        base = f"../openspec/changes/{c['name']}"
        links = [f'<a href="{base}/proposal.md" target="_blank" rel="noopener">proposal.md</a>']
        if c["has_design"]:
            links.append(f'<a href="{base}/design.md" target="_blank" rel="noopener">design.md</a>')
        if c["has_tasks"]:
            links.append(f'<a href="{base}/tasks.md" target="_blank" rel="noopener">tasks.md</a>')
        if c["has_guide"]:
            links.append(f'<a href="{base}/test-guide.md" target="_blank" rel="noopener">test-guide.md</a>')

        if c["token"] == "APPROVED":
            badge = '<span class="chg-badge ok">approved — waiting on a night</span>'
        elif c["token"]:
            badge = f'<span class="chg-badge">{esc(c["token"].lower())}</span>'
        else:
            badge = '<span class="chg-badge want">waiting on you</span>'

        facts = " · ".join(
            x
            for x in (
                f'{c["todo"]} unticked' + (f' of {c["todo"] + c["done"]}' if c["done"] else ""),
                f'{c["rounds"]} rounds' if c["rounds"] else "",
                f'{c["spec_count"]} delta spec{"s" if c["spec_count"] != 1 else ""}'
                if c["spec_count"]
                else "",
            )
            if x
        )

        rounds = (
            f"""<details class="chg-rounds"><summary>The round log — what has already been argued and refuted</summary>
                 <div class="md-body">{md(c["rounds_md"], demote=3)}</div></details>"""
            if c["rounds_md"]
            else ""
        )
        body = (
            f'<div class="md-body">{md(c["proposal"], demote=3)}</div>'
            if c["proposal"]
            else '<p class="empty">No <code>proposal.md</code> in this directory.</p>'
        )

        return f"""<div class="chg">
          <div class="chg-head">
            <div class="chg-main">
              <code class="chg-name">{esc(c["name"])}</code>
              {badge}
              <p class="chg-facts">{esc(facts)}</p>
              {f'<p class="chg-note">{esc(c["note"])}</p>' if c["note"] else ""}
            </div>
            <div class="chg-links">{" · ".join(links)}</div>
          </div>
          {rounds}
          <details class="chg-read" open><summary>Read the proposal</summary>{body}</details>
        </div>"""

    change_rows = (
        "\n".join(change_block(c) for c in drain)
        or '<p class="empty">No unbuilt change directories. The drain is clear.</p>'
    )

    approval_rows = (
        "\n".join(
            f'<div class="apr" data-tok="{esc(tok)}"><span class="tok">{esc(tok)}</span>'
            f'<code>{esc(name)}</code><span class="apr-note">{esc(note)}</span></div>'
            for tok, name, note in rows
        )
        or '<p class="empty">No rows in the newest section — the FIX window spends the whole night on the backlog.</p>'
    )

    bars = "\n".join(
        f'<div class="bar-row"><span class="bar-lab">{k}</span>'
        f'<div class="bar-track"><div class="bar-fill" data-sev="{k}" '
        f'style="width:{(counts.get(k,0)/max(total_open,1))*100:.1f}%"></div></div>'
        f'<span class="bar-n">{counts.get(k,0)}</span></div>'
        for k in ("A", "B", "C", "D", "?")
        if counts.get(k)
    )

    snapshot = {
        "generated": now.isoformat(timespec="seconds"),
        "branch": branch,
        "sha": sha,
        "open": total_open,
        "items": total_items,
        "requests": len(standalone),
        "fixed": total_fixed,
        "retired": total_retired,
        "filed": len(findings),
        "drain": len(drain),
        **{f"sev_{k}": counts.get(k, 0) for k in ("A", "B", "C", "D", "?")},
        **{f"src_{k}": src_counts.get(k, 0) for k in SOURCES},
        **{f"rdy_{k}": ready_counts.get(k, 0) for k in READY},
        "ids": sorted(f["id"] for f in findings),
        "open_ids": sorted(f["id"] for f in openf),
    }

    page = TEMPLATE.format(
        snapshot=json.dumps(snapshot, indent=1),
        generated=esc(now.strftime("%Y-%m-%d %H:%M %Z")),
        branch=esc(branch or "?"),
        sha=esc(sha or "?"),
        tree=("uncommitted changes present" if dirty else "clean"),
        total_open=total_open,
        total_items=total_items,
        n_requests=len(standalone),
        total_fixed=total_fixed,
        total_retired=total_retired,
        total_all=len(findings),
        drain_n=len(drain),
        awaiting_n=len(awaiting),
        loop_word=esc(loop_word),
        a_count=counts.get("A", 0),
        n_proposed=ready_counts.get("proposed", 0),
        n_operator=src_counts.get("operator", 0),
        bars=bars,
        change_rows=change_rows,
        approval_rows=approval_rows,
        ap_date=esc(ap_date or "none"),
        di_date=esc(di_date or "none"),
        order_row=(
            f'<div class="directive"><span class="tok">ORDER</span><code>{esc(order)}</code></div>'
            if order
            else ""
        ),
        nothing_row=(
            '<div class="directive" data-stop="1"><span class="tok">NOTHING TONIGHT</span>'
            "<span>the FIX window stops before spending an invocation</span></div>"
            if nothing
            else ""
        ),
        night_iter=esc(night.get("iteration", "?")),
        night_branch=esc(night.get("branch", "?")),
        night_stop=esc(night.get("stop_at", "?")),
        day_iter=esc(day.get("iteration", "?")),
        day_branch=esc(day.get("branch", "?")),
        day_stop=esc(day.get("stop_at", "?")),
        source_chips=source_chips,
        ready_chips=ready_chips,
        sev_chips=sev_chips,
        theme_groups="\n".join(theme_groups),
        sev_groups="\n".join(sev_groups),
    )
    return page, snapshot, findings, changes


TEMPLATE = """<title>AgentWeave Backlog</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:ital,wght@0,400;1,400&display=swap">
<style>
:root {{
  --ground:#F4F5F8; --surface:#FFFFFF; --surface-2:#EAECF2; --sunk:#E1E4EC;
  --ink:#16181F; --ink-2:#4D5464; --ink-3:#787F90;
  --rule:#DCDFE8; --rule-2:#C2C7D6;
  --accent:#4A57A0; --accent-soft:#E7E9F6;
  --sevA:#A8372C; --sevA-soft:#F7E6E3;
  --sevB:#8A5F14; --sevB-soft:#F7EEDA;
  --sevC:#3F6E52; --sevC-soft:#E4EFE8;
  --sevD:#606878; --sevD-soft:#E9EBF0;
  --op:#7A3E86;   --op-soft:#F2E7F5;
  --day:#C8922E; --night:#4A57A0;
  --sans:'IBM Plex Sans',-apple-system,Segoe UI,system-ui,sans-serif;
  --serif:'IBM Plex Serif',Georgia,serif;
  --mono:'IBM Plex Mono',Consolas,monospace;
  color-scheme:light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#0E1014; --surface:#171A21; --surface-2:#1F232C; --sunk:#12151B;
    --ink:#E4E7EE; --ink-2:#A6ACBB; --ink-3:#7A8194;
    --rule:#262B35; --rule-2:#39404E;
    --accent:#8E9BDE; --accent-soft:#1D2238;
    --sevA:#E07E6E; --sevA-soft:#301C19;
    --sevB:#D5A64A; --sevB-soft:#2E2514;
    --sevC:#7FB795; --sevC-soft:#16261C;
    --sevD:#98A0B2; --sevD-soft:#1E222B;
    --op:#C79AD2;   --op-soft:#2A1B2E;
    --day:#DEAE52; --night:#8E9BDE;
    color-scheme:dark;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0E1014; --surface:#171A21; --surface-2:#1F232C; --sunk:#12151B;
  --ink:#E4E7EE; --ink-2:#A6ACBB; --ink-3:#7A8194;
  --rule:#262B35; --rule-2:#39404E;
  --accent:#8E9BDE; --accent-soft:#1D2238;
  --sevA:#E07E6E; --sevA-soft:#301C19;
  --sevB:#D5A64A; --sevB-soft:#2E2514;
  --sevC:#7FB795; --sevC-soft:#16261C;
  --sevD:#98A0B2; --sevD-soft:#1E222B;
  --op:#C79AD2;   --op-soft:#2A1B2E;
  --day:#DEAE52; --night:#8E9BDE;
  color-scheme:dark;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1120px;margin:0 auto;padding-inline:20px;padding-block:40px 72px}}
a{{color:var(--accent)}}
code{{font-family:var(--mono);font-size:.88em}}
:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}

.top{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap;margin-bottom:26px}}
h1{{font-size:clamp(28px,5vw,40px);font-weight:700;letter-spacing:-.025em;line-height:1.05;margin:0}}
.eyebrow{{font-family:var(--mono);font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}}
.stamp{{font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--ink-3);text-align:right}}
.stamp b{{color:var(--ink-2);font-weight:500}}

.clock{{background:var(--surface);border:1px solid var(--rule);border-radius:3px;padding:18px 20px 20px;margin-bottom:26px}}
.clock h2{{font-size:12px;font-family:var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);margin:0 0 14px;font-weight:500}}
.track{{position:relative;display:flex;height:42px;border-radius:2px;overflow:hidden;border:1px solid var(--rule)}}
.seg{{display:flex;flex-direction:column;justify-content:center;padding:0 10px;min-width:0;overflow:hidden}}
.seg b{{font-size:11px;font-weight:600;letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.seg span{{font-family:var(--mono);font-size:9.5px;color:var(--ink-3);white-space:nowrap}}
.seg[data-w="fill"]{{background:var(--sevB-soft);flex:8}}
.seg[data-w="fill"] b{{color:var(--day)}}
.seg[data-w="decide"]{{background:var(--accent-soft);flex:6}}
.seg[data-w="decide"] b{{color:var(--accent)}}
.seg[data-w="fix"]{{background:var(--sunk);flex:8}}
.seg[data-w="fix"] b{{color:var(--night)}}
.seg[data-w="margin"]{{background:var(--surface-2);flex:2}}
.seg[data-w="margin"] b{{color:var(--ink-3)}}
#nowline{{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--ink);z-index:2}}
#nowline::after{{content:'';position:absolute;top:-4px;left:-3px;width:8px;height:8px;border-radius:50%;background:var(--ink)}}
#nowlabel{{margin-top:9px;font-family:var(--mono);font-size:11.5px;color:var(--ink-2)}}
#nowlabel b{{color:var(--ink)}}

.figs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:3px;margin-bottom:34px;overflow:hidden}}
.fig{{background:var(--surface);padding:16px 16px 14px}}
.fig b{{display:block;font-family:var(--mono);font-size:26px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.03em;line-height:1}}
.fig span{{display:block;margin-top:7px;font-size:11.5px;line-height:1.4;color:var(--ink-3)}}
.fig[data-t="a"] b{{color:var(--sevA)}}
.fig[data-t="op"] b{{color:var(--op)}}

h2.sec{{font-size:19px;font-weight:700;letter-spacing:-.015em;margin:0 0 4px;padding-bottom:10px;border-bottom:2px solid var(--ink)}}
.lede{{font-family:var(--serif);font-size:15.5px;line-height:1.6;color:var(--ink-2);max-width:68ch;margin:14px 0 20px}}
section.block{{margin-top:44px}}

.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}
.panel{{background:var(--surface);border:1px solid var(--rule);border-radius:3px;padding:18px 18px 16px}}
.panel h3{{font-size:13px;font-family:var(--mono);letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3);margin:0 0 4px;font-weight:500}}
.panel .when{{font-family:var(--mono);font-size:11px;color:var(--accent);margin:0 0 12px}}
.empty{{font-size:13px;color:var(--ink-3);font-style:italic;margin:6px 0 0}}

.apr{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;padding:7px 0;border-bottom:1px solid var(--rule);font-size:13px}}
.apr:last-child{{border-bottom:0}}
.tok{{font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.06em;padding:2px 6px;border-radius:2px;background:var(--surface-2);color:var(--ink-2)}}
.apr[data-tok="APPROVED"] .tok{{background:var(--sevC-soft);color:var(--sevC)}}
.apr[data-tok="REVISING"] .tok{{background:var(--sevB-soft);color:var(--sevB)}}
.apr[data-tok="REJECTED"] .tok{{background:var(--sevA-soft);color:var(--sevA)}}
.apr-note{{font-size:12px;color:var(--ink-3)}}
.directive{{display:flex;align-items:baseline;gap:9px;margin-top:11px;padding-top:11px;border-top:1px dashed var(--rule-2);font-size:12.5px;flex-wrap:wrap}}
.directive[data-stop="1"] .tok{{background:var(--sevA-soft);color:var(--sevA)}}

.chg{{padding:16px 0;border-bottom:1px solid var(--rule)}}
.chg:last-child{{border-bottom:0}}
.chg-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}}
.chg-main{{min-width:0}}
.chg-name{{font-size:13px;font-weight:600;overflow-wrap:anywhere}}
.chg-note{{margin:5px 0 0;font-size:11.5px;line-height:1.45;color:var(--sevB)}}
.chg-facts{{margin:5px 0 0;font-size:11.5px;color:var(--ink-3);font-variant-numeric:tabular-nums}}
.chg-links{{flex-shrink:0;font-size:11.5px;color:var(--ink-3)}}
.chg-links a{{color:var(--ink-2)}}
.chg-badge{{display:inline-block;margin-left:8px;padding:1px 7px;border-radius:9px;font-size:10px;
  text-transform:uppercase;letter-spacing:.06em;background:var(--rule);color:var(--ink-2);vertical-align:1px}}
.chg-badge.want{{background:var(--sevA-soft);color:var(--sevA);font-weight:600}}
.chg-badge.ok{{background:var(--sevC-soft,var(--rule));color:var(--ink-3)}}
.chg-rounds,.chg-read{{margin-top:12px}}
.chg-rounds>summary,.chg-read>summary{{cursor:pointer;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink-3);padding:5px 0}}
.chg-rounds>summary:hover,.chg-read>summary:hover{{color:var(--ink)}}
.md-body{{margin-top:10px;padding:14px 18px;border-left:2px solid var(--rule);font-size:13.5px;line-height:1.62}}
.md-body h3{{font-size:15px;margin:20px 0 7px}}
.md-body h4,.md-body h5,.md-body h6{{font-size:13px;margin:16px 0 5px;color:var(--ink-2)}}
.md-body h3:first-child,.md-body h4:first-child{{margin-top:0}}
.md-body p{{margin:0 0 11px}}
.md-body li{{margin:0 0 5px}}
.md-body ul,.md-body ol{{margin:0 0 11px;padding-left:20px}}
.md-body pre{{background:var(--rule);padding:10px 12px;border-radius:5px;overflow-x:auto;font-size:12px;margin:0 0 11px}}
.md-body code{{font-family:var(--mono);font-size:.92em}}
.md-body pre code{{font-size:inherit}}
.md-body blockquote{{margin:0 0 11px;padding-left:13px;border-left:2px solid var(--rule);color:var(--ink-2)}}
.md-body blockquote p:last-child{{margin-bottom:0}}
.md-body table.md{{border-collapse:collapse;font-size:12.5px;width:100%}}
.md-body table.md th,.md-body table.md td{{border:1px solid var(--rule);padding:5px 9px;text-align:left;vertical-align:top}}
.md-body table.md th{{background:var(--rule);font-weight:600}}
.md-body hr{{border:0;border-top:1px solid var(--rule);margin:16px 0}}

.bars{{display:flex;flex-direction:column;gap:7px;margin:18px 0 8px}}
.bar-row{{display:flex;align-items:center;gap:11px}}
.bar-lab{{font-family:var(--mono);font-size:12px;font-weight:600;width:14px;flex-shrink:0}}
.bar-track{{flex:1;height:14px;background:var(--sunk);border-radius:2px;overflow:hidden}}
.bar-fill{{height:100%}}
.bar-fill[data-sev="A"]{{background:var(--sevA)}}
.bar-fill[data-sev="B"]{{background:var(--sevB)}}
.bar-fill[data-sev="C"]{{background:var(--sevC)}}
.bar-fill[data-sev="D"]{{background:var(--sevD)}}
.bar-fill[data-sev="?"]{{background:repeating-linear-gradient(45deg,var(--sevD),var(--sevD) 3px,var(--sunk) 3px,var(--sunk) 6px)}}
.bar-n{{font-family:var(--mono);font-size:12px;font-variant-numeric:tabular-nums;color:var(--ink-2);width:34px;text-align:right;flex-shrink:0}}

/* ---------------- controls ---------------- */
.controls{{position:sticky;top:0;z-index:5;background:var(--ground);border-bottom:1px solid var(--rule);padding-block:12px;margin-bottom:16px}}
.ctl-row{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}}
.ctl-row:last-child{{margin-bottom:0}}
.ctl-lab{{font-family:var(--mono);font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);width:54px;flex-shrink:0}}
.f-chip{{font-family:var(--mono);font-size:11px;padding:4px 9px;border-radius:2px;border:1px solid var(--rule-2);background:var(--surface);color:var(--ink-2);cursor:pointer;display:inline-flex;align-items:center;gap:6px}}
.f-chip:hover{{border-color:var(--accent);color:var(--ink)}}
.f-chip.is-on{{background:var(--accent);border-color:var(--accent);color:#fff}}
.f-n{{font-variant-numeric:tabular-nums;opacity:.65;font-size:10px}}
#q{{flex:1;min-width:180px;font-family:var(--mono);font-size:12.5px;padding:6px 10px;border:1px solid var(--rule-2);border-radius:2px;background:var(--surface);color:var(--ink)}}
#q::placeholder{{color:var(--ink-3)}}
.seg-toggle{{display:inline-flex;border:1px solid var(--rule-2);border-radius:2px;overflow:hidden}}
.seg-toggle button{{font-family:var(--mono);font-size:11px;padding:5px 11px;border:0;background:var(--surface);color:var(--ink-2);cursor:pointer}}
.seg-toggle button.is-on{{background:var(--accent);color:#fff}}
#count{{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);margin-left:auto;font-variant-numeric:tabular-nums}}
#count b{{color:var(--ink)}}
.linkish{{font-family:var(--mono);font-size:11px;background:none;border:0;color:var(--accent);cursor:pointer;text-decoration:underline;padding:0}}

/* ---------------- groups and items ---------------- */
.group{{margin-bottom:10px;border:1px solid var(--rule);border-radius:2px;background:var(--surface);overflow:hidden}}
.group[hidden]{{display:none}}
.g-head{{width:100%;display:flex;align-items:center;gap:10px;padding:11px 14px;background:var(--surface-2);border:0;border-bottom:1px solid var(--rule);cursor:pointer;text-align:left;font-family:inherit}}
.g-caret{{font-size:10px;color:var(--ink-3);transition:transform .12s ease}}
.group.collapsed .g-caret{{transform:rotate(-90deg)}}
.group.collapsed .g-body{{display:none}}
.g-name{{font-size:13.5px;font-weight:600;color:var(--ink);flex:1;min-width:0}}
.g-n{{font-family:var(--mono);font-size:11px;color:var(--ink-3);font-variant-numeric:tabular-nums}}
.g-n b{{color:var(--ink-2)}}
.g-body{{padding:2px 0}}

.item{{display:block;padding:9px 14px;border-bottom:1px solid var(--rule)}}
.item:last-child{{border-bottom:0}}
.item[hidden]{{display:none}}
.i-head{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:3px}}
.i-id{{font-family:var(--mono);font-size:11.5px;font-weight:600;color:var(--accent)}}
.i-title{{margin:0;font-size:13.5px;line-height:1.45;overflow-wrap:anywhere}}
.i-note{{margin:5px 0 0;font-family:var(--serif);font-size:12.5px;line-height:1.5;color:var(--ink-2);border-left:2px solid var(--op);padding-left:9px}}
.chip{{font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.05em;padding:2px 5px;border-radius:2px;white-space:nowrap}}
.c-sev[data-sev="A"]{{background:var(--sevA-soft);color:var(--sevA)}}
.c-sev[data-sev="B"]{{background:var(--sevB-soft);color:var(--sevB)}}
.c-sev[data-sev="C"]{{background:var(--sevC-soft);color:var(--sevC)}}
.c-sev[data-sev="D"]{{background:var(--sevD-soft);color:var(--sevD)}}
.c-sev[data-sev="?"]{{background:var(--sevD-soft);color:var(--sevD)}}
.c-sev[data-sev="—"]{{background:var(--op-soft);color:var(--op)}}
.c-src{{background:var(--surface-2);color:var(--ink-3)}}
.c-src[data-source="operator"]{{background:var(--op-soft);color:var(--op)}}
.c-src[data-source="drive"]{{background:var(--sevC-soft);color:var(--sevC)}}
.c-rdy{{border:1px solid var(--rule-2);color:var(--ink-3);background:transparent}}
.c-rdy[data-ready="proposed"]{{border-color:var(--sevC);color:var(--sevC)}}
.c-rdy[data-ready="triage"]{{border-color:var(--sevB);color:var(--sevB)}}
.c-req{{background:var(--op);color:#fff}}
#noresults{{padding:26px 14px;text-align:center;color:var(--ink-3);font-size:13px}}

.map{{width:100%;border-collapse:collapse;font-size:13px}}
.map th{{text-align:left;font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:500;padding:0 12px 8px 0;border-bottom:1px solid var(--rule-2)}}
.map td{{padding:9px 12px 9px 0;border-bottom:1px solid var(--rule);vertical-align:top}}
.map td:first-child{{white-space:nowrap}}
.map code{{font-size:12px}}
.scroll{{overflow-x:auto}}

footer{{margin-top:50px;padding-top:18px;border-top:1px solid var(--rule);font-family:var(--mono);font-size:11px;line-height:1.75;color:var(--ink-3)}}
@media (max-width:640px){{
  .top{{align-items:flex-start}} .stamp{{text-align:left}}
  .seg span{{display:none}}
  .ctl-lab{{width:auto}}
  #count{{margin-left:0;width:100%}}
}}
@media (prefers-reduced-motion: reduce){{ *{{transition:none!important}} }}
</style>

<div class="wrap">

  <div class="top">
    <div>
      <p class="eyebrow">AgentWeave · standing orientation</p>
      <h1>Backlog</h1>
    </div>
    <div class="stamp">
      generated <b>{generated}</b><br>
      branch <b>{branch}</b> @ <b>{sha}</b> · {tree}<br>
      regenerate: <b>/backlog</b>
    </div>
  </div>

  <div class="clock">
    <h2>The cycle</h2>
    <div class="track" id="track">
      <div class="seg" data-w="fill"   data-from="9"  data-to="17"><b>FILL</b><span>09–17 · day window proposes</span></div>
      <div class="seg" data-w="decide" data-from="17" data-to="23"><b>DECIDE</b><span>17–23 · you approve</span></div>
      <div class="seg" data-w="fix"    data-from="23" data-to="7"><b>FIX</b><span>23–07 · night window builds</span></div>
      <div class="seg" data-w="margin" data-from="7"  data-to="9"><b>margin</b><span>07–09</span></div>
      <div id="nowline" style="left:0"></div>
    </div>
    <p id="nowlabel">&nbsp;</p>
  </div>

  <div class="figs">
    <div class="fig" data-t="a"><b>{a_count}</b><span>open severity&nbsp;A</span></div>
    <div class="fig"><b>{total_items}</b><span>open items — {total_open} findings + {n_requests} requests</span></div>
    <div class="fig" data-t="op"><b>{n_operator}</b><span>you asked for</span></div>
    <div class="fig"><b>{n_proposed}</b><span>have a proposal, so the night can build them</span></div>
    <div class="fig" data-t="op"><b>{awaiting_n}</b><span>changes waiting on <b style="display:inline;font-size:inherit">you</b> — tomorrow runs {loop_word}</span></div>
    <div class="fig"><b>{drain_n}</b><span>unbuilt changes in total (the drain)</span></div>
  </div>

  <section class="block">
    <h2 class="sec">The backlog</h2>
    <p class="lede">
      Everything open, from both ledgers. <b>Source</b> says where an item came from — whether it
      was found by exercising the product or asked for by you — because those earn a place in a
      queue differently. <b>Ready</b> says whether anyone could pick it up: the night window cannot
      build a finding with no proposal, so an <code>A</code> that reads <code>ready</code> still
      needs a spec loop before it is available.
    </p>

    <div class="controls">
      <div class="ctl-row">
        <span class="ctl-lab">source</span>{source_chips}
      </div>
      <div class="ctl-row">
        <span class="ctl-lab">ready</span>{ready_chips}
      </div>
      <div class="ctl-row">
        <span class="ctl-lab">severity</span>{sev_chips}
      </div>
      <div class="ctl-row">
        <span class="ctl-lab">find</span>
        <input id="q" type="search" placeholder="filter by id, words in the title, or theme…" autocomplete="off">
        <span class="seg-toggle" role="group" aria-label="Group by">
          <button type="button" id="by-theme" class="is-on">by theme</button>
          <button type="button" id="by-sev">by severity</button>
        </span>
        <button type="button" class="linkish" id="toggle-all">expand all</button>
        <span id="count"></span>
      </div>
    </div>

    <div id="groups-theme">{theme_groups}</div>
    <div id="groups-sev" hidden>{sev_groups}</div>
    <p id="noresults" hidden>Nothing matches those filters.</p>
  </section>

  <section class="block">
    <h2 class="sec">What the windows are holding</h2>
    <p class="lede">
      Each window reads exactly one file to learn what you said, and only that file's newest dated
      section. Everything below the newest section is history and is not read.
    </p>
    <div class="two">
      <div class="panel">
        <h3>Tonight · FIX builds</h3>
        <p class="when">reads spec-queue/APPROVALS.md § {ap_date}</p>
        {approval_rows}
        {order_row}
        {nothing_row}
      </div>
      <div class="panel">
        <h3>Tomorrow · FILL proposes</h3>
        <p class="when">reads spec-queue/DIRECTION.md § {di_date}</p>
        <p style="font-size:13px;margin:0 0 10px">Drain is <b>{drain_n}</b>, so the day runs <b>{loop_word}</b>. A dated section overrides that shape in either direction.</p>
        <p class="empty">Read the section itself before composing — it is the only operator channel the day window has.</p>
      </div>
    </div>
  </section>

  <section class="block">
    <h2 class="sec">Unbuilt changes — read and approve here</h2>
    <p class="lede">
      A change directory with at least one unticked task, with its proposal rendered in place.
      <b>Marked <span class="chg-badge want">waiting on you</span></b> means it needs an
      <code>APPROVED</code>, <code>REVISING</code> or <code>REJECTED</code> token in
      <code>spec-queue/APPROVALS.md</code> before any night can build it.
      Only those count toward the throttle: <b>2 or more</b> waiting on you and no spec loop runs
      tomorrow, <b>1</b> gives one loop, <b>0</b> gives two. A change you have already approved is
      waiting on a night, not on you, and no longer suppresses tomorrow's proposal
      (decided 2026-09-19 — counting every unbuilt change starved four consecutive days).
    </p>
    <div class="panel">{change_rows}</div>
  </section>

  <section class="block">
    <h2 class="sec">Findings by severity</h2>
    <p class="lede">
      <b>A</b> is wrong behaviour an operator will act on, <b>B</b> a wrong or misleading surface,
      <b>C</b> friction or vestige. {total_fixed} are fixed and {total_retired} retired, of
      {total_all} ever filed; neither is counted here.
    </p>
    <div class="bars">{bars}</div>
  </section>

  <section class="block">
    <h2 class="sec">Where authority lives</h2>
    <p class="lede">
      For an agent orienting itself: these files disagree with each other sometimes, and when they
      do, this column is the tie-break. Nothing here is a summary of another file — each is the
      only writer of something.
    </p>
    <div class="scroll">
      <table class="map">
        <thead><tr><th>File</th><th>Is the authority for</th><th>Written by</th></tr></thead>
        <tbody>
          <tr><td><code>spec-queue/APPROVALS.md</code></td><td>what the FIX window may build tonight. The status token is the authority; there is deliberately no checkbox.</td><td>the DECIDE session, on the operator's instruction</td></tr>
          <tr><td><code>spec-queue/DIRECTION.md</code></td><td>what the FILL window does tomorrow. Overrides the drain-count shape in either direction. May not approve a change.</td><td>the operator, or DECIDE on their behalf</td></tr>
          <tr><td><code>spec-queue/DECISIONS.md</code></td><td>questions a window may not answer alone. Only the operator marks one DECIDED.</td><td>both windows append; operator decides</td></tr>
          <tr><td><code>spec-queue/REQUESTS.md</code></td><td>what the operator asked for. Not a defect ledger — a request naming a <code>Finding:</code> re-sources that finding instead of adding a row.</td><td>the operator</td></tr>
          <tr><td><code>scripts/drive/FINDINGS.md</code></td><td>every defect ever filed, and its <code>**Status:**</code> line. Findings live nowhere else.</td><td>any window that drives</td></tr>
          <tr><td><code>openspec/changes/&lt;name&gt;/</code></td><td>specs, design and tasks for work in flight. Never in two systems at once.</td><td>the FILL window's spec loop</td></tr>
          <tr><td><code>openspec/specs/</code></td><td>current shipped behaviour. The 30 accumulated capability documents stay here until the operator migrates them.</td><td>archive-change and sync-specs</td></tr>
          <tr><td><code>.claude/autonomous/STATE-*.json</code></td><td>a window's own position and queue. Rewritten every firing — never a backlog.</td><td>the window itself</td></tr>
          <tr><td><code>.claude/handoffs/DEAD-ENDS.md</code></td><td>what does not work on this machine. Read before debugging an environment problem; append rather than re-deriving.</td><td>any session</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="block">
    <h2 class="sec">Loop position</h2>
    <div class="two">
      <div class="panel">
        <h3>STATE-night.json</h3>
        <p class="when">iteration {night_iter}</p>
        <p style="font-size:13px;margin:0">branch <code>{night_branch}</code><br>stop_at <code>{night_stop}</code></p>
      </div>
      <div class="panel">
        <h3>STATE-day.json</h3>
        <p class="when">iteration {day_iter}</p>
        <p style="font-size:13px;margin:0">branch <code>{day_branch}</code><br>stop_at <code>{day_stop}</code></p>
      </div>
    </div>
  </section>

  <script type="application/json" id="backlog-data">
{snapshot}
  </script>

  <footer>
    Generated by scripts/backlog_page.py — do not edit this file by hand; edit the generator.<br>
    Sources: scripts/drive/FINDINGS.md · spec-queue/REQUESTS.md · openspec/changes/ · spec-queue/{{APPROVALS,DIRECTION}}.md · .claude/autonomous/STATE-{{day,night}}.json<br>
    The cycle marker is computed in your browser, so it stays true even when the counts are a day old.
  </footer>
</div>

<script>
(function () {{
  /* ---- cycle clock ---- */
  var track = document.getElementById('track');
  var line = document.getElementById('nowline');
  var label = document.getElementById('nowlabel');

  function place() {{
    if (!track || !line || !label) return;
    var segs = Array.prototype.slice.call(track.querySelectorAll('.seg'));
    var now = new Date();
    var h = now.getHours() + now.getMinutes() / 60;
    var total = track.clientWidth;
    var x = 0, current = null, acc = 0;
    for (var i = 0; i < segs.length; i++) {{
      var s = segs[i];
      var from = parseFloat(s.dataset.from), to = parseFloat(s.dataset.to);
      var span = to > from ? to - from : (24 - from) + to;
      var inside = to > from ? (h >= from && h < to) : (h >= from || h < to);
      var w = s.offsetWidth;
      if (inside) {{
        var into = h >= from ? h - from : (24 - from) + h;
        x = acc + (into / span) * w;
        current = s;
      }}
      acc += w;
    }}
    if (!current) {{ current = segs[segs.length - 1]; x = acc; }}
    line.style.left = Math.max(0, Math.min(x, total)) + 'px';
    var pretty = now.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
    label.innerHTML = 'Now <b>' + pretty + '</b> — in the <b>' + current.querySelector('b').textContent + '</b> window.';
  }}
  place();
  window.addEventListener('resize', place);
  setInterval(place, 60000);

  /* ---- filtering ---- */
  var filters = {{ source: '', ready: '', sev: '' }};
  var query = '';
  var panes = {{ theme: document.getElementById('groups-theme'), sev: document.getElementById('groups-sev') }};
  var mode = 'theme';
  var wasFiltered = false;
  var countEl = document.getElementById('count');
  var noResults = document.getElementById('noresults');
  var toggleAll = document.getElementById('toggle-all');

  function store(k, v) {{ try {{ localStorage.setItem('aw-backlog-' + k, v); }} catch (e) {{}} }}
  function recall(k) {{ try {{ return localStorage.getItem('aw-backlog-' + k); }} catch (e) {{ return null; }} }}

  function apply() {{
    var pane = panes[mode];
    var shown = 0, total = 0;
    var groups = pane.querySelectorAll('.group');
    for (var g = 0; g < groups.length; g++) {{
      var items = groups[g].querySelectorAll('.item');
      var visible = 0;
      for (var i = 0; i < items.length; i++) {{
        var el = items[i];
        var ok = (!filters.source || el.dataset.source === filters.source)
              && (!filters.ready || el.dataset.ready === filters.ready)
              && (!filters.sev || el.dataset.sev === filters.sev)
              && (!query || el.dataset.text.indexOf(query) !== -1);
        el.hidden = !ok;
        if (ok) visible++;
        total++;
      }}
      groups[g].hidden = visible === 0;
      var n = groups[g].querySelector('.g-shown');
      if (n) n.textContent = visible;
      shown += visible;
    }}
    countEl.innerHTML = '<b>' + shown + '</b> of ' + total + ' shown';
    noResults.hidden = shown !== 0;

    /* A filtered view that stays shut shows nothing, and a 217-row page that opens flat is a
       wall rather than an index. So: closed at rest, open automatically while a filter is live,
       closed again when it clears. Between those, a manual toggle is left alone. */
    var live = !!(filters.source || filters.ready || filters.sev || query);
    if (live !== wasFiltered) {{
      for (var k = 0; k < groups.length; k++) {{
        groups[k].classList.toggle('collapsed', !live);
        var hh = groups[k].querySelector('.g-head');
        if (hh) hh.setAttribute('aria-expanded', live ? 'true' : 'false');
      }}
      toggleAll.textContent = live ? 'collapse all' : 'expand all';
      wasFiltered = live;
    }}
  }}

  document.addEventListener('click', function (ev) {{
    var chip = ev.target.closest ? ev.target.closest('.f-chip') : null;
    if (chip) {{
      var f = chip.dataset.filter;
      filters[f] = chip.dataset.value;
      var siblings = chip.parentNode.querySelectorAll('.f-chip[data-filter="' + f + '"]');
      for (var i = 0; i < siblings.length; i++) siblings[i].classList.remove('is-on');
      chip.classList.add('is-on');
      apply();
      return;
    }}
    var head = ev.target.closest ? ev.target.closest('.g-head') : null;
    if (head) {{
      var grp = head.parentNode;
      var collapsed = grp.classList.toggle('collapsed');
      head.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }}
  }});

  var q = document.getElementById('q');
  q.addEventListener('input', function () {{ query = q.value.trim().toLowerCase(); apply(); }});

  function setMode(next) {{
    mode = next;
    panes.theme.hidden = next !== 'theme';
    panes.sev.hidden = next !== 'sev';
    document.getElementById('by-theme').classList.toggle('is-on', next === 'theme');
    document.getElementById('by-sev').classList.toggle('is-on', next === 'sev');
    store('mode', next);
    apply();
  }}
  document.getElementById('by-theme').addEventListener('click', function () {{ setMode('theme'); }});
  document.getElementById('by-sev').addEventListener('click', function () {{ setMode('sev'); }});

  toggleAll.addEventListener('click', function () {{
    var pane = panes[mode];
    var groups = pane.querySelectorAll('.group');
    var anyOpen = false;
    for (var i = 0; i < groups.length; i++) if (!groups[i].classList.contains('collapsed')) anyOpen = true;
    for (var j = 0; j < groups.length; j++) {{
      groups[j].classList.toggle('collapsed', anyOpen);
      var h = groups[j].querySelector('.g-head');
      if (h) h.setAttribute('aria-expanded', anyOpen ? 'false' : 'true');
    }}
    toggleAll.textContent = anyOpen ? 'expand all' : 'collapse all';
  }});

  var saved = recall('mode');
  if (saved === 'sev') setMode('sev'); else apply();
}})();
</script>
"""

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--check",
        action="store_true",
        help="report the delta and warnings without writing the page (exit 1 if it would change)",
    )
    ap.add_argument("--quiet", action="store_true", help="write the page, print only the path")
    args = ap.parse_args(argv)

    prev = previous_snapshot()
    page, snapshot, findings, changes = build()

    if args.check:
        # Compare the *data*, not the rendered bytes. Every generation stamps a fresh time and the
        # current HEAD, so a byte comparison reports STALE on every call and the flag means nothing.
        # The question --check answers is "has the ledger moved since this page was built".
        stale = not OUT.exists() or substantive(prev) != substantive(snapshot)
        print(f"{OUT.relative_to(ROOT)}: {'STALE' if stale else 'current'}")
        for line in report_delta(prev, snapshot):
            print(f"  {line}")
        return 1 if stale else 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)

    if args.quiet:
        print(OUT.relative_to(ROOT))
        return 0

    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    print()
    print("SINCE LAST GENERATION")
    for line in report_delta(prev, snapshot):
        print(f"  {line}")

    warn = consistency_warnings(findings, changes)
    if warn:
        print()
        print("LEDGER WARNINGS  (none of these is conclusive on its own)")
        for w in warn:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
