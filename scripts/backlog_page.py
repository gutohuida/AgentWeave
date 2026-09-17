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
CHANGES = ROOT / "openspec" / "changes"
QUEUE = ROOT / "spec-queue"
STATE_DIR = ROOT / ".claude" / "autonomous"
OUT = QUEUE / "BACKLOG.html"

SEV_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "?": 4}


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
        out.append(
            {
                "id": fid,
                "num": int(re.sub(r"\D", "", fid) or 0),
                "sev": recover_sev(m.group(2), title, body),
                "title": title,
                "status": raw,
                "state": classify(raw, title),
            }
        )
    return out


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
    """Change directories with at least one unticked task — the drain, as the playbook counts it."""
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
        prop = d / "proposal.md"
        if prop.exists():
            head = prop.read_text(encoding="utf-8", errors="replace")[:1500]
            stop = re.search(r"^##\s*(STOPPED[^\n]*)", head, re.M)
            if stop:
                note = stop.group(1).strip()
        out.append({"name": d.name, "done": done, "todo": todo, "note": note})
    return out


# --------------------------------------------------------------------------- spec-queue

def newest_section(path: Path) -> tuple[str, str]:
    """The newest `## YYYY-MM-DD` section of a spec-queue file: (date, body)."""
    if not path.exists():
        return ("", "")
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = list(re.finditer(r"^##\s*(\d{4}-\d{2}-\d{2})\s*$", text, re.M))
    if not hits:
        return ("", "")
    first = hits[0]
    end = hits[1].start() if len(hits) > 1 else len(text)
    return (first.group(1), text[first.end() : end].strip())


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
    """Returns (html, snapshot, findings, changes) — the snapshot is what the next run compares to."""
    findings = parse_findings()
    openf = [f for f in findings if f["state"] in ("open", "no-status")]
    openf.sort(key=lambda f: (SEV_ORDER.get(f["sev"], 9), -f["num"]))
    by_sev: dict[str, list[dict]] = {}
    for f in openf:
        by_sev.setdefault(f["sev"], []).append(f)

    counts = {k: len(v) for k, v in by_sev.items()}
    total_open = len(openf)
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

    loops = 2 if len(drain) == 0 else (1 if len(drain) == 1 else 0)
    loop_word = {0: "no spec loop", 1: "one spec loop", 2: "two spec loops"}[loops]

    # ---- fragments -------------------------------------------------------

    def sev_block(letter: str, label: str, blurb: str) -> str:
        items = by_sev.get(letter, [])
        if not items:
            return ""
        badge = '<span class="nostatus">no status line</span>'
        lis = "\n".join(
            '<li class="fnd"><span class="fid">{}</span><span class="ftitle">{}</span>{}</li>'.format(
                esc(f["id"]),
                esc(f["title"]),
                badge if f["state"] == "no-status" else "",
            )
            for f in items
        )
        return f"""
      <section class="sev" data-sev="{letter}">
        <header class="sev-head">
          <span class="sev-mark">{letter}</span>
          <h3>{esc(label)}</h3>
          <span class="sev-n">{len(items)}</span>
        </header>
        <p class="sev-blurb">{esc(blurb)}</p>
        <ul class="fnds">{lis}</ul>
      </section>"""

    change_rows = (
        "\n".join(
            f"""<div class="chg">
              <div class="chg-main">
                <code class="chg-name">{esc(c["name"])}</code>
                {f'<p class="chg-note">{esc(c["note"])}</p>' if c["note"] else ""}
              </div>
              <div class="chg-count"><b>{c["todo"]}</b><span>unticked</span></div>
            </div>"""
            for c in drain
        )
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

    newest = sorted(findings, key=lambda f: -f["num"])[:6]
    newest_html = "\n".join(
        f'<li class="fnd"><span class="fid">{esc(f["id"])}</span>'
        f'<span class="sev-tag" data-sev="{esc(f["sev"])}">{esc(f["sev"])}</span>'
        f'<span class="ftitle">{esc(f["title"])}</span></li>'
        for f in newest
    )

    snapshot = {
        "generated": now.isoformat(timespec="seconds"),
        "branch": branch,
        "sha": sha,
        "open": total_open,
        "fixed": total_fixed,
        "retired": total_retired,
        "filed": len(findings),
        "drain": len(drain),
        **{f"sev_{k}": counts.get(k, 0) for k in ("A", "B", "C", "D", "?")},
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
        total_fixed=total_fixed,
        total_retired=total_retired,
        total_all=len(findings),
        drain_n=len(drain),
        loop_word=esc(loop_word),
        a_count=counts.get("A", 0),
        bars=bars,
        change_rows=change_rows,
        approval_rows=approval_rows,
        ap_date=esc(ap_date or "none"),
        di_date=esc(di_date or "none"),
        order=esc(order) if order else "",
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
        sev_a=sev_block("A", "Wrong behaviour an operator will act on", "The queue the night window drains first. A finding with no proposal needs the day window before it can be built."),
        sev_b=sev_block("B", "Wrong or misleading surface", "Something the product shows, says or refuses that is not true of what it does."),
        sev_c=sev_block("C", "Friction and vestige", "Real, reproduced, and cheap to leave. Most of the ledger lives here."),
        sev_d=sev_block("D", "Minor", "Filed for completeness."),
        sev_q=sev_block("?", "No severity declared anywhere", "Neither the heading nor the body states one. Shown rather than hidden: an unrated finding is not a closed one, and dropping it is how a ledger comes to under-report itself."),
        newest_html=newest_html,
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
  --day:#DEAE52; --night:#8E9BDE;
  color-scheme:dark;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1120px;margin:0 auto;padding-inline:20px;padding-block:40px 72px}}
a{{color:var(--accent)}}
code{{font-family:var(--mono);font-size:.88em}}

.top{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap;margin-bottom:26px}}
h1{{font-size:clamp(28px,5vw,40px);font-weight:700;letter-spacing:-.025em;line-height:1.05;margin:0}}
.eyebrow{{font-family:var(--mono);font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}}
.stamp{{font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--ink-3);text-align:right}}
.stamp b{{color:var(--ink-2);font-weight:500}}

/* cycle clock */
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

/* figures */
.figs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:3px;margin-bottom:34px;overflow:hidden}}
.fig{{background:var(--surface);padding:16px 16px 14px}}
.fig b{{display:block;font-family:var(--mono);font-size:26px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.03em;line-height:1}}
.fig span{{display:block;margin-top:7px;font-size:11.5px;line-height:1.4;color:var(--ink-3)}}
.fig[data-t="a"] b{{color:var(--sevA)}}

h2.sec{{font-size:19px;font-weight:700;letter-spacing:-.015em;margin:0 0 4px;padding-bottom:10px;border-bottom:2px solid var(--ink)}}
.lede{{font-family:var(--serif);font-size:15.5px;line-height:1.6;color:var(--ink-2);max-width:68ch;margin:14px 0 20px}}
section.block{{margin-top:44px}}

/* two-up */
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

.chg{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:11px 0;border-bottom:1px solid var(--rule)}}
.chg:last-child{{border-bottom:0}}
.chg-main{{min-width:0}}
.chg-name{{font-size:13px;font-weight:600;overflow-wrap:anywhere}}
.chg-note{{margin:5px 0 0;font-size:11.5px;line-height:1.45;color:var(--sevB)}}
.chg-count{{text-align:right;flex-shrink:0}}
.chg-count b{{display:block;font-family:var(--mono);font-size:19px;font-variant-numeric:tabular-nums;line-height:1}}
.chg-count span{{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3)}}

/* bars */
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

/* severity groups */
.sev{{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--rule-2);border-radius:2px;padding:16px 18px 14px;margin-bottom:12px}}
.sev[data-sev="A"]{{border-left-color:var(--sevA)}}
.sev[data-sev="B"]{{border-left-color:var(--sevB)}}
.sev[data-sev="C"]{{border-left-color:var(--sevC)}}
.sev[data-sev="D"]{{border-left-color:var(--sevD)}}
.sev[data-sev="?"]{{border-left-color:var(--sevD);border-left-style:dashed}}
.sev[data-sev="?"] .sev-mark{{background:var(--sevD-soft);color:var(--sevD)}}
.sev-tag[data-sev="?"]{{background:var(--sevD-soft);color:var(--sevD)}}
.sev-head{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.sev-head h3{{font-size:15px;font-weight:600;margin:0;flex:1;min-width:0}}
.sev-mark{{font-family:var(--mono);font-size:12px;font-weight:600;width:22px;height:22px;display:grid;place-items:center;border-radius:2px;flex-shrink:0}}
.sev[data-sev="A"] .sev-mark{{background:var(--sevA-soft);color:var(--sevA)}}
.sev[data-sev="B"] .sev-mark{{background:var(--sevB-soft);color:var(--sevB)}}
.sev[data-sev="C"] .sev-mark{{background:var(--sevC-soft);color:var(--sevC)}}
.sev[data-sev="D"] .sev-mark{{background:var(--sevD-soft);color:var(--sevD)}}
.sev-n{{font-family:var(--mono);font-size:12px;font-variant-numeric:tabular-nums;color:var(--ink-3)}}
.sev-blurb{{font-size:12.5px;color:var(--ink-3);margin:7px 0 12px;max-width:70ch}}
.fnds{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:1px}}
.fnd{{display:flex;gap:10px;align-items:baseline;padding:5px 0;border-top:1px solid var(--rule);font-size:13px;line-height:1.45}}
.fnd:first-child{{border-top:0}}
.fid{{font-family:var(--mono);font-size:11.5px;font-weight:600;color:var(--accent);width:48px;flex-shrink:0}}
.ftitle{{min-width:0;overflow-wrap:anywhere}}
.nostatus{{font-family:var(--mono);font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--sevB);border:1px solid var(--sevB);padding:1px 4px;border-radius:2px;white-space:nowrap;flex-shrink:0;align-self:center}}
.sev-tag{{font-family:var(--mono);font-size:10px;font-weight:600;padding:1px 5px;border-radius:2px;flex-shrink:0}}
.sev-tag[data-sev="A"]{{background:var(--sevA-soft);color:var(--sevA)}}
.sev-tag[data-sev="B"]{{background:var(--sevB-soft);color:var(--sevB)}}
.sev-tag[data-sev="C"]{{background:var(--sevC-soft);color:var(--sevC)}}
.sev-tag[data-sev="D"]{{background:var(--sevD-soft);color:var(--sevD)}}

/* authority map */
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
}}
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
      regenerate: <b>py -3.11 scripts/backlog_page.py</b>
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
    <div class="fig"><b>{total_open}</b><span>open findings of {total_all} filed</span></div>
    <div class="fig"><b>{total_fixed}</b><span>fixed and recorded</span></div>
    <div class="fig"><b>{drain_n}</b><span>unbuilt changes — tomorrow runs {loop_word}</span></div>
  </div>

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
    <h2 class="sec">Unbuilt changes</h2>
    <p class="lede">
      A change directory with at least one unticked task. This count is the throttle: <b>2 or more</b>
      and no spec loop runs at all, <b>1</b> gives one loop, <b>0</b> gives two. It is what stops the
      proposing rate outrunning the building rate.
    </p>
    <div class="panel">{change_rows}</div>
  </section>

  <section class="block">
    <h2 class="sec">Findings</h2>
    <p class="lede">
      Severity <b>A</b> is wrong behaviour an operator will act on, <b>B</b> a wrong or misleading
      surface, <b>C</b> friction or vestige. The night window drains A before B before C — but
      <em>a finding with no proposal needs the day window first</em>, so an A here is not by itself
      buildable tonight. {total_retired} findings are retired and are not counted below.
    </p>
    <div class="bars">{bars}</div>

    <div class="panel" style="margin:20px 0 26px">
      <h3>Newest filed</h3>
      <ul class="fnds">{newest_html}</ul>
    </div>

    {sev_a}
    {sev_b}
    {sev_c}
    {sev_d}
    {sev_q}
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
    Sources: scripts/drive/FINDINGS.md · openspec/changes/ · spec-queue/{{APPROVALS,DIRECTION}}.md · .claude/autonomous/STATE-{{day,night}}.json<br>
    The cycle marker above is computed in your browser, so it stays true even when the counts are a day old.
  </footer>
</div>

<script>
(function () {{
  var track = document.getElementById('track');
  var line = document.getElementById('nowline');
  var label = document.getElementById('nowlabel');
  if (!track || !line || !label) return;

  function place() {{
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

    var name = current.querySelector('b').textContent;
    var pretty = now.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
    label.innerHTML = 'Now <b>' + pretty + '</b> — in the <b>' + name + '</b> window.';
  }}

  place();
  window.addEventListener('resize', place);
  setInterval(place, 60000);
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
