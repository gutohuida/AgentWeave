"""Generate spec-queue/ROUNDS.html, the tracker for spec-queue/ROUNDS.md.

The page is derived, never authored. Which round a finding belongs to comes from ROUNDS.md; whether
it is fixed comes from scripts/drive/FINDINGS.md, through the same parser as BACKLOG.html. So
closing a finding (its `**Status:** fixed <sha>` line) and re-running this is all it takes to move
the page.

**Where a finding lives.** A finding counts toward exactly one round: the first that places it
*without striking it*. A hand-off is written in ROUNDS.md by striking the id where the finding left
(`| ~~F167~~ | ...` in a table, `~~F62~~ (D7)` in prose). The struck row stays on the page under the
round it left, marked *moved -> <where it lives now>*, and is counted only there. A finding placed
nowhere unstruck has left the plan (moved to a proposed change, say); it is listed, and counted in
no total. Unstruck later mentions are cross-references and say "also in".

    py -3.11 scripts/rounds_page.py          write the page and print the progress report
    py -3.11 scripts/rounds_page.py --quiet  write the page and print only its path
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backlog_page as bp  # noqa: E402

PLAN = bp.QUEUE / "ROUNDS.md"
OUT = bp.QUEUE / "ROUNDS.html"

_FID = re.compile(r"\bF\d+\b")
_DATE = re.compile(r"(20\d\d-\d\d-\d\d)")
_SHA = re.compile(r"\b([0-9a-f]{7,12})\b")
# "F192 (stop on an unknown agent)" or "F175 + F182 (one helper, two sites)" in a prose group.
_PROSE_ITEM = re.compile(
    r"((?:~~)?F\d+(?:~~)?(?:\s*\+\s*(?:~~)?F\d+(?:~~)?)*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
)
# `~~F167~~`: the finding was handed on from here (see the module docstring).
_STRUCK = re.compile(r"~~\s*(F\d+)\s*~~")
# Sections of ROUNDS.md that hold work, and how their rows are read.
_WORK_SECTION = re.compile(r"^## (Round \d+|UI-\d+|D |Spec tracks)")


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _group(label: str, note: str = "") -> dict:
    return {"label": label, "note": note, "items": [], "moved": set()}


def _add(group: dict, text: str, note: str) -> None:
    """Every id in *text* joins *group*; a struck one is recorded as handed on from here."""
    struck = set(_STRUCK.findall(text))
    for fid in _FID.findall(text):
        group["items"].append((fid, note))
        if fid in struck:
            group["moved"].add(fid)


def _target(groups: list[dict], current: dict | None) -> dict:
    if current is not None:
        return current
    if not groups:
        groups.append(_group(""))
    return groups[0]


def _prose_items(prose: list[str], groups: list[dict], current: dict | None) -> None:
    """A prose item's note can wrap onto the next line, so match the joined paragraph."""
    if not prose:
        return
    target = _target(groups, current)
    for m in _PROSE_ITEM.finditer(" ".join(prose)):
        _add(target, m.group(1), m.group(2))


def _parse_groups(kind: str, body: str) -> list[dict]:
    groups: list[dict] = []
    current: dict | None = None
    prose: list[str] = []
    for line in body.split("\n"):
        if not line.strip() or line.startswith(("|", "**")):
            if kind == "fix":
                _prose_items(prose, groups, current)
            prose = []
        bold = re.match(r"^\*\*(.+?)\*\*\s*$", line)
        if bold:
            current = _group(bold.group(1))
            groups.append(current)
            continue
        if line.startswith("|"):
            row = cells(line)
            if not row or set(row[0]) <= set("-: ") or row[0] in ("Finding", "#", "Round"):
                continue
            if kind == "decision":
                group = _group(f"{row[0]} · {row[1]}")
                _add(group, row[-1], "")
                groups.append(group)
            elif kind == "spec":
                group = _group(f"{row[0]} · {row[1]}", row[3] if len(row) > 3 else "")
                _add(group, row[2], "")
                groups.append(group)
            else:
                _add(_target(groups, current), row[0], row[-1])
            continue
        if line.strip():
            prose.append(line.strip())
    if kind == "fix":
        _prose_items(prose, groups, current)
    return [g for g in groups if g["items"]]


def parse_plan(text: str) -> list[dict]:
    """Rounds in document order: {key, title, kind, blurb, groups: [{label, note, items}]}."""
    rounds: list[dict] = []
    for sec in re.split(r"\n(?=## )", text):
        head, _, body = sec.partition("\n")
        if not _WORK_SECTION.match(head):
            continue
        title = head[3:].strip()
        kind = (
            "decision" if head.startswith("## D ") else "spec" if "Spec tracks" in head else "fix"
        )
        if kind == "decision":
            key = "D"
        elif kind == "spec":
            key = "S"
        elif title.startswith("Round"):
            key = "R" + title.split()[1]
        else:
            key = title.split(" ")[0]
        blurb = ""
        for para in body.strip().split("\n\n"):
            if para and not para.startswith(("|", "**")):
                blurb = " ".join(para.split())
                break
        # A round can be declared done while some of its findings stay open, because they were
        # handed on to a later round or to D. `**Status:** done YYYY-MM-DD ...` in the plan says so.
        done = re.search(r"^\*\*Status:\*\*\s*done\s+(\d{4}-\d{2}-\d{2})", body, re.M)
        rounds.append(
            {
                "key": key,
                "title": title,
                "kind": kind,
                "blurb": blurb,
                "closed_on": done.group(1) if done else "",
                "groups": _parse_groups(kind, body),
            }
        )
    return rounds


def fixed_on(status: str) -> str:
    m = _DATE.search(status or "")
    return m.group(1) if m else ""


def build() -> tuple[str, dict]:
    findings = {f["id"]: f for f in bp.parse_findings()}
    rounds = parse_plan(PLAN.read_text(encoding="utf-8"))
    # The plan covers B, C and D. A severity-A finding it names (a parked F325, tonight's F352) is a
    # cross-reference for context, not a member.
    for r in rounds:
        for g in r["groups"]:
            g["items"] = [
                (fid, note) for fid, note in g["items"] if findings.get(fid, {}).get("sev") != "A"
            ]
        r["groups"] = [g for g in r["groups"] if g["items"]]

    # A finding counts toward the first round that places it **unstruck**; a struck placement is a
    # hand-off (it left that round), and a later unstruck mention is a cross-reference.
    home: dict[str, str] = {}
    left_from: dict[str, str] = {}
    for r in rounds:
        for g in r["groups"]:
            for fid, _ in g["items"]:
                if fid in g["moved"]:
                    left_from.setdefault(fid, r["key"])
                else:
                    home.setdefault(fid, r["key"])
    # Handed on and placed nowhere else: it left the plan (to a proposed change, say).
    out_of_plan = sorted((fid for fid in left_from if fid not in home), key=lambda x: int(x[1:]))

    def state(fid: str) -> str:
        f = findings.get(fid)
        return f["state"] if f else "missing"

    placed = list(home)
    done = [fid for fid in placed if state(fid) in ("fixed", "retired")]
    current_key = ""
    for r in rounds:
        own = {
            fid
            for g in r["groups"]
            for fid, _ in g["items"]
            if fid not in g["moved"] and home.get(fid) == r["key"]
        }
        r["own"] = sorted(own, key=lambda x: int(x[1:]))
        r["done"] = [fid for fid in r["own"] if state(fid) in ("fixed", "retired")]
        if (
            not current_key
            and r["kind"] == "fix"
            and not r["closed_on"]
            and len(r["done"]) < len(r["own"])
        ):
            current_key = r["key"]

    recent = sorted(
        (
            (fixed_on(findings[fid]["status"]), fid)
            for fid in placed
            if fid in findings and findings[fid]["state"] == "fixed"
        ),
        reverse=True,
    )[:15]

    sha = bp.git("rev-parse", "--short", "HEAD")
    branch = bp.git("branch", "--show-current")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def chip(fid: str) -> str:
        st = state(fid)
        label = {"open": "open", "fixed": "fixed", "retired": "retired"}.get(st, st)
        return f'<span class="st st-{esc(st)}">{esc(label)}</span>'

    def item_html(fid: str, note: str, r: dict, moved: bool = False) -> str:
        f = findings.get(fid, {})
        sev = f.get("sev", "?")
        st = state(fid)
        status = f.get("status", "")
        m = _SHA.search(status) if st == "fixed" else None
        fix = f'<code class="sha">{esc(m.group(1))}</code>' if m else ""
        when = fixed_on(status) if st == "fixed" else ""
        xref = ""
        if moved:
            where = home.get(fid)
            dest = f'<a href="#{esc(where)}">{esc(where)}</a>' if where else "out of the plan"
            xref = f'<span class="xref moved">moved &rarr; {dest}</span>'
        elif home.get(fid) != r["key"]:
            xref = f'<span class="xref">also in {esc(home.get(fid, ""))}</span>'
        note_html = f'<div class="note">{inline(note)}</div>' if note else ""
        row_state = "moved" if moved else st
        return (
            f'<li class="it{" it-moved" if moved else ""}" data-state="{esc(row_state)}" '
            f'data-sev="{esc(sev)}" '
            f'data-text="{esc((fid + " " + f.get("title", "") + " " + note).lower())}">'
            f'<div class="row1">{chip(fid)}<span class="fid">{esc(fid)}</span>'
            f'<span class="sev sev-{esc(sev)}">{esc(sev)}</span>'
            f'<span class="ttl">{esc(f.get("title", "(not in the ledger)"))}</span>'
            f'{xref}{fix}<span class="when">{esc(when)}</span></div>{note_html}</li>'
        )

    sections = []
    for r in rounds:
        total, got = len(r["own"]), len(r["done"])
        pct = round(100 * got / total) if total else 0
        is_now = r["key"] == current_key
        groups_html = []
        for g in r["groups"]:
            label = f'<h4>{inline(g["label"])}</h4>' if g["label"] else ""
            gnote = f'<p class="gnote">{inline(g["note"])}</p>' if g["note"] else ""
            items = "".join(
                item_html(fid, note, r, moved=fid in g["moved"]) for fid, note in g["items"]
            )
            groups_html.append(f'<div class="grp">{label}{gnote}<ul>{items}</ul></div>')
        badge = '<span class="now">now</span>' if is_now else ""
        handed = {fid for g in r["groups"] for fid in g["moved"]}
        handed_txt = f", {len(handed)} moved out" if handed else ""
        if total and got == total:
            complete = f' <span class="donechip">complete{handed_txt}</span>'
        elif r["closed_on"]:
            complete = (
                f' <span class="donechip">done {esc(r["closed_on"])}, '
                f"{total - got} still open{handed_txt}</span>"
            )
        elif handed:
            complete = f' <span class="donechip">{len(handed)} moved out</span>'
        else:
            complete = ""
        sections.append(
            f'<details class="round kind-{r["kind"]}" id="{esc(r["key"])}"{" open" if is_now else ""}>'
            f'<summary><span class="rkey">{esc(r["key"])}</span>'
            f'<span class="rtitle">{inline(r["title"])}</span>{badge}{complete}'
            f'<span class="rcount">{got}/{total}</span>'
            f'<span class="bar"><i style="width:{pct}%"></i></span></summary>'
            f'<div class="rbody"><p class="blurb">{inline(r["blurb"])}</p>{"".join(groups_html)}</div>'
            "</details>"
        )

    recent_html = (
        "".join(
            f'<li><span class="when">{esc(d)}</span><a href="#{esc(home[fid])}">{esc(fid)}</a> '
            f'<span class="sev sev-{esc(findings[fid]["sev"])}">{esc(findings[fid]["sev"])}</span> '
            f'{esc(findings[fid]["title"])}</li>'
            for d, fid in recent
        )
        or '<li class="muted">Nothing placed in the plan is fixed yet.</li>'
    )

    total, got = len(placed), len(done)
    snapshot = {
        "generated": now,
        "sha": sha,
        "placed": total,
        "done": got,
        "rounds": {r["key"]: [len(r["done"]), len(r["own"])] for r in rounds},
        "current": current_key,
        "out_of_plan": out_of_plan,
    }
    page = TEMPLATE.format(
        now=esc(now),
        sha=esc(sha),
        branch=esc(branch),
        got=got,
        total=total,
        pct=round(100 * got / total) if total else 0,
        open_left=total - got,
        current=esc(current_key or "—"),
        sections="".join(sections),
        recent=recent_html,
        out_of_plan=(
            "".join(
                f'<li><span class="fid">{esc(fid)}</span> '
                f'<span class="sev sev-{esc(findings.get(fid, {}).get("sev", "?"))}">'
                f'{esc(findings.get(fid, {}).get("sev", "?"))}</span> '
                f'{esc(findings.get(fid, {}).get("title", ""))} '
                f'<a href="#{esc(left_from[fid])}">from {esc(left_from[fid])}</a></li>'
                for fid in out_of_plan
            )
            or '<li class="muted">Nothing has left the plan.</li>'
        ),
        data=esc(json.dumps(snapshot)),
    )
    return page, snapshot


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentWeave Rounds</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
:root {{
  --ground:#F4F5F8; --surface:#FFFFFF; --surface-2:#EAECF2;
  --ink:#16181F; --ink-2:#4D5464; --ink-3:#787F90;
  --rule:#DCDFE8; --accent:#4A57A0; --accent-soft:#E7E9F6;
  --sevA:#A8372C; --sevA-soft:#F7E6E3; --sevB:#8A5F14; --sevB-soft:#F7EEDA;
  --sevC:#3F6E52; --sevC-soft:#E4EFE8; --sevD:#606878; --sevD-soft:#E9EBF0;
  --ok:#2F7A4B; --ok-soft:#E1F1E6; --op:#7A3E86; --op-soft:#F2E7F5;
  --sans:'IBM Plex Sans',-apple-system,Segoe UI,system-ui,sans-serif;
  --mono:'IBM Plex Mono',Consolas,monospace;
  color-scheme:light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#0E1014; --surface:#171A21; --surface-2:#1F232C;
    --ink:#E4E7EE; --ink-2:#A6ACBB; --ink-3:#7A8194;
    --rule:#262B35; --accent:#8E9BDE; --accent-soft:#1D2238;
    --sevA:#E07E6E; --sevA-soft:#301C19; --sevB:#D5A64A; --sevB-soft:#2E2514;
    --sevC:#7FB795; --sevC-soft:#16261C; --sevD:#98A0B2; --sevD-soft:#1E222B;
    --ok:#7FC79A; --ok-soft:#15281D; --op:#C79AD2; --op-soft:#2A1B2E;
    color-scheme:dark;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0E1014; --surface:#171A21; --surface-2:#1F232C;
  --ink:#E4E7EE; --ink-2:#A6ACBB; --ink-3:#7A8194;
  --rule:#262B35; --accent:#8E9BDE; --accent-soft:#1D2238;
  --sevA:#E07E6E; --sevA-soft:#301C19; --sevB:#D5A64A; --sevB-soft:#2E2514;
  --sevC:#7FB795; --sevC-soft:#16261C; --sevD:#98A0B2; --sevD-soft:#1E222B;
  --ok:#7FC79A; --ok-soft:#15281D; --op:#C79AD2; --op-soft:#2A1B2E;
  color-scheme:dark;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:36px 16px 72px}}
a{{color:var(--accent)}}
code{{font-family:var(--mono);font-size:.86em}}
:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:22px}}
.eyebrow{{font-family:var(--mono);font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--accent);margin:0 0 8px}}
h1{{font-size:clamp(28px,5vw,38px);font-weight:700;letter-spacing:-.02em;line-height:1.05;margin:0}}
.stamp{{font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--ink-3);text-align:right}}
.stamp b{{color:var(--ink-2);font-weight:500}}
.hero{{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:18px 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin-bottom:18px}}
.fig .n{{font-size:28px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
.fig .l{{font-size:12px;color:var(--ink-3)}}
.bigbar{{grid-column:1/-1;height:8px;border-radius:4px;background:var(--surface-2);overflow:hidden}}
.bigbar i{{display:block;height:100%;background:var(--ok)}}
.tools{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:0 0 14px}}
.tools input[type=search]{{flex:1 1 220px;min-width:0;padding:8px 10px;border:1px solid var(--rule);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit}}
.tools label{{font-size:13px;color:var(--ink-2);display:flex;gap:6px;align-items:center;cursor:pointer}}
.chipbtn{{font:inherit;font-size:12px;padding:5px 10px;border-radius:999px;border:1px solid var(--rule);background:var(--surface);color:var(--ink-2);cursor:pointer}}
.chipbtn[aria-pressed=true]{{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}}
.layout{{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px;align-items:start}}
@media (max-width:860px){{.layout{{grid-template-columns:1fr}}}}
.round{{background:var(--surface);border:1px solid var(--rule);border-radius:10px;margin-bottom:10px}}
.round summary{{list-style:none;cursor:pointer;display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:4px 12px;align-items:center;padding:12px 16px}}
.round summary::-webkit-details-marker{{display:none}}
.rkey{{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--accent);min-width:36px}}
.rtitle{{font-weight:600;min-width:0}}
.rcount{{font-family:var(--mono);font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums}}
.bar{{grid-column:1/-1;height:5px;border-radius:3px;background:var(--surface-2);overflow:hidden}}
.bar i{{display:block;height:100%;background:var(--ok)}}
.now{{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.08em;background:var(--accent);color:var(--surface);padding:2px 7px;border-radius:999px}}
.donechip{{font-family:var(--mono);font-size:10px;text-transform:uppercase;background:var(--ok-soft);color:var(--ok);padding:2px 7px;border-radius:999px}}
.kind-decision .rkey{{color:var(--op)}} .kind-spec .rkey{{color:var(--ink-2)}}
.rbody{{padding:0 16px 14px;border-top:1px solid var(--rule)}}
.blurb{{color:var(--ink-2);font-size:14px;margin:12px 0}}
.grp h4{{font-size:13px;font-weight:600;margin:14px 0 4px;color:var(--ink)}}
.gnote{{font-size:13px;color:var(--ink-3);margin:0 0 6px}}
ul{{list-style:none;margin:0;padding:0}}
.it{{padding:8px 0;border-top:1px dashed var(--rule)}}
.it:first-child{{border-top:0}}
.row1{{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:baseline}}
.fid{{font-family:var(--mono);font-weight:600;font-size:13px}}
.ttl{{flex:1 1 280px;min-width:0;font-size:14px}}
.note{{font-size:13px;color:var(--ink-2);margin:3px 0 0 0;padding-left:2px}}
.st{{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;padding:2px 6px;border-radius:4px}}
.st-open{{background:var(--surface-2);color:var(--ink-2)}}
.st-fixed{{background:var(--ok-soft);color:var(--ok)}}
.st-retired{{background:var(--surface-2);color:var(--ink-3);text-decoration:line-through}}
.it-moved{{opacity:.62}}
.it-moved .fid{{text-decoration:line-through}}
.xref.moved{{font-weight:600}}
.st-missing{{background:var(--sevA-soft);color:var(--sevA)}}
.it[data-state=fixed] .ttl,.it[data-state=retired] .ttl{{color:var(--ink-3);text-decoration:line-through}}
.sev{{font-family:var(--mono);font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px}}
.sev-A{{background:var(--sevA-soft);color:var(--sevA)}} .sev-B{{background:var(--sevB-soft);color:var(--sevB)}}
.sev-C{{background:var(--sevC-soft);color:var(--sevC)}} .sev-D{{background:var(--sevD-soft);color:var(--sevD)}}
.sha{{color:var(--ok)}} .when{{font-family:var(--mono);font-size:11px;color:var(--ink-3)}}
.xref{{font-size:11px;color:var(--ink-3);font-style:italic}}
aside .card{{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;position:sticky;top:12px}}
aside h3{{font-size:13px;margin:0 0 8px;font-weight:600}}
aside li{{font-size:13px;padding:5px 0;border-top:1px dashed var(--rule)}}
aside li:first-child{{border-top:0}}
aside li .when{{display:block}}
.muted{{color:var(--ink-3)}}
.foot{{font-size:12px;color:var(--ink-3);margin-top:22px}}
.hidden{{display:none}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div><p class="eyebrow">spec-queue/ROUNDS.md, tracked</p><h1>Rounds</h1></div>
    <div class="stamp">generated <b>{now}</b><br>at <b>{sha}</b> on <b>{branch}</b></div>
  </div>
  <div class="hero">
    <div class="fig"><div class="n">{got} / {total}</div><div class="l">placed findings closed</div></div>
    <div class="fig"><div class="n">{open_left}</div><div class="l">still open</div></div>
    <div class="fig"><div class="n">{pct}%</div><div class="l">through the plan</div></div>
    <div class="fig"><div class="n">{current}</div><div class="l">current round</div></div>
    <div class="bigbar" role="img" aria-label="{pct}% closed"><i style="width:{pct}%"></i></div>
  </div>
  <div class="tools">
    <input type="search" id="q" placeholder="Filter by id, title or plan note" aria-label="Filter">
    <label><input type="checkbox" id="hideDone"> hide closed</label>
    <button class="chipbtn" data-sev="B" aria-pressed="false">B</button>
    <button class="chipbtn" data-sev="C" aria-pressed="false">C</button>
    <button class="chipbtn" data-sev="D" aria-pressed="false">D</button>
    <button class="chipbtn" id="expand">expand all</button>
  </div>
  <div class="layout">
    <main>{sections}</main>
    <aside><div class="card"><h3>Recently closed</h3><ul>{recent}</ul></div>
    <div class="card"><h3>Moved out of the plan</h3><p class="muted">Handed on to a change this
    plan does not track; counted in no total.</p><ul>{out_of_plan}</ul></div></aside>
  </div>
  <p class="foot">Derived from <code>spec-queue/ROUNDS.md</code> (which round) and
  <code>scripts/drive/FINDINGS.md</code> (whether it is fixed). Never edit this file; mark the
  finding's <code>**Status:** fixed &lt;sha&gt;</code> and run <code>py -3.11 scripts/rounds_page.py</code>.
  A finding counts toward the first round that places it unstruck. A struck id
  (<code>~~F167~~</code>) is a hand-off: it shows under the round it left as "moved &rarr;" and
  counts where it went; other later mentions say "also in".</p>
</div>
<script type="application/json" id="rounds-data">{data}</script>
<script>
(function () {{
  var q = document.getElementById('q'), hide = document.getElementById('hideDone');
  var sevBtns = Array.prototype.slice.call(document.querySelectorAll('.chipbtn[data-sev]'));
  function store(k, v) {{ try {{ localStorage.setItem('rounds.' + k, v); }} catch (e) {{}} }}
  function load(k) {{ try {{ return localStorage.getItem('rounds.' + k); }} catch (e) {{ return null; }} }}
  if (load('hideDone') === '1') hide.checked = true;
  function apply() {{
    var text = q.value.trim().toLowerCase();
    var sevs = sevBtns.filter(function (b) {{ return b.getAttribute('aria-pressed') === 'true'; }})
                      .map(function (b) {{ return b.dataset.sev; }});
    var filtering = text || sevs.length;
    document.querySelectorAll('.it').forEach(function (li) {{
      var show = (!text || li.dataset.text.indexOf(text) >= 0)
        && (!sevs.length || sevs.indexOf(li.dataset.sev) >= 0)
        && !(hide.checked && li.dataset.state !== 'open');
      li.classList.toggle('hidden', !show);
    }});
    document.querySelectorAll('.grp').forEach(function (g) {{
      g.classList.toggle('hidden', !g.querySelector('.it:not(.hidden)'));
    }});
    if (filtering) document.querySelectorAll('details.round').forEach(function (d) {{
      d.open = !!d.querySelector('.it:not(.hidden)');
    }});
  }}
  q.addEventListener('input', apply);
  hide.addEventListener('change', function () {{ store('hideDone', hide.checked ? '1' : '0'); apply(); }});
  sevBtns.forEach(function (b) {{ b.addEventListener('click', function () {{
    b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); apply();
  }}); }});
  document.getElementById('expand').addEventListener('click', function () {{
    var all = document.querySelectorAll('details.round'), anyClosed = false;
    all.forEach(function (d) {{ if (!d.open) anyClosed = true; }});
    all.forEach(function (d) {{ d.open = anyClosed; }});
  }});
  apply();
}})();
</script>
</body>
</html>
"""


def main() -> int:
    quiet = "--quiet" in sys.argv[1:]
    page, snap = build()
    OUT.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(bp.ROOT)} ({len(page.encode()):,} bytes)")
    if quiet:
        return 0
    print(
        f"\n{snap['done']}/{snap['placed']} placed findings closed; current round {snap['current']}"
    )
    for key, (got, total) in snap["rounds"].items():
        print(f"  {key:5} {got:3}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
