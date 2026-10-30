"""Split FINDINGS.md into sources the knowledge vault can hold, and say where each finding stands.

The vault takes at most 1 MiB per text source and FINDINGS.md is over 3 MB, so this writes:

    findings-00-index.md          one line per section: id, severity, state, title, which file
    findings-01-open.md           everything not closed, with the ones that need a look on top
    findings-02-closed-N.md       closed findings, in number order
    findings-03-drive-notes.md    what is not a finding: baselines, "what held", drive accounts

It reads FINDINGS.md and never changes it, and it refuses to write anything unless every byte of
FINDINGS.md landed in exactly one section. State comes from each section's own `**Status:**` line;
`stale?` is only a hint that a commit subject on master names the finding as fixed.

    py -3.11 scripts/drive/findings_to_vault.py [output-dir]
"""

from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "FINDINGS.md"
DEFAULT_OUT = HERE.parents[1] / ".agentweave" / "vault-sources" / "findings"
MAX_BYTES = 1_000_000

HEADING = re.compile(r"^## ")
FINDING = re.compile(r"^## (F\d+)\b")
SEVERITY = re.compile(r"^## F\d+\s*\(([A-D][+-]?)")
STATUS = re.compile(r"^\*\*Status:\*\*\s*(.*)$", re.M)
FIX_WORD = re.compile(r"\b(fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)\b", re.I)


def sections(text: str) -> list[str]:
    """Cut at `## ` headings outside code fences; a quoted heading stays with its finding."""
    out: list[str] = []
    current: list[str] = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and HEADING.match(line) and current:
            out.append("".join(current))
            current = []
        current.append(line)
    out.append("".join(current))
    return out


def state_of(section: str) -> str:
    if re.search(r"\b(RETIRED|RETRACTED)\b", section.split("\n", 1)[0]):
        return "closed"
    match = STATUS.search(section)
    if match is None:
        return "none"
    status = match.group(1).lstrip("~*` ").lower()
    if re.match(r"(fixed|closed|built|retired|superseded|won|resolved|done)", status):
        return "closed"
    if status.startswith("open"):
        return "open"
    if re.match(r"(part|still)", status):
        return "partly"
    return "unclear"


def fix_commits() -> dict[str, list[str]]:
    """Commit subjects on master that name a finding beside a word for fixing it."""
    log = subprocess.run(
        ["git", "log", "master", "--format=%h %s"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        cwd=HERE,
    ).stdout
    named: dict[str, list[str]] = collections.defaultdict(list)
    for line in log.splitlines():
        if FIX_WORD.search(line) and not re.search(r"\b(file|files|filed)\b", line, re.I):
            for finding in re.findall(r"\bF\d+\b", line):
                named[finding].append(line.split(" ", 1)[0])
    return named


def title_of(section: str) -> str:
    return section.split("\n", 1)[0][3:].strip().replace("|", "\\|")[:150]


def split_parts(items: list[str], name: str) -> dict[str, list[str]]:
    parts: dict[str, list[str]] = {}
    size = 0
    current: list[str] = []
    for item in items:
        length = len(item.encode("utf-8"))
        if current and size + length > MAX_BYTES:
            parts[f"{name}-{len(parts) + 1}.md"] = current
            current, size = [], 0
        current.append(item)
        size += length
    if current:
        parts[f"{name}-{len(parts) + 1}.md"] = current
    return parts


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    text = SOURCE.read_text(encoding="utf-8")
    pieces = sections(text)
    if "".join(pieces) != text:
        print("refused: the sections do not add back up to FINDINGS.md", file=sys.stderr)
        return 1

    fixed = fix_commits()
    with_status = {
        m.group(1) for piece in pieces if (m := FINDING.match(piece)) and state_of(piece) != "none"
    }

    rows: list[dict[str, str]] = []
    last_finding = "the top of the file"
    for piece in pieces:
        match = FINDING.match(piece)
        if match is None:
            rows.append(
                {"id": "", "sev": "", "state": "note", "after": last_finding, "text": piece}
            )
            continue
        fid = match.group(1)
        last_finding = fid
        severity = SEVERITY.match(piece)
        state = state_of(piece)
        if state == "none" and fid in with_status:
            state = "addendum"
        hint = ""
        if state in ("open", "partly", "unclear", "none") and fid in fixed:
            hint = "stale? " + " ".join(fixed[fid][:3])
        rows.append(
            {
                "id": fid,
                "sev": severity.group(1) if severity else "",
                "state": state,
                "hint": hint,
                "text": piece,
            }
        )

    def is_open(row: dict[str, str]) -> bool:
        return row["state"] in ("open", "partly", "unclear", "none")

    open_rows = [r for r in rows if r["id"] and is_open(r)]
    closed_rows = [r for r in rows if r["id"] and not is_open(r)]
    note_rows = [r for r in rows if not r["id"]]

    # What a reader must look at first: no clear state, or a commit that says it was fixed.
    open_rows.sort(key=lambda r: (not (r["hint"] or r["state"] != "open"), r["sev"] or "Z"))

    notes = [f"<!-- followed {r['after']} in FINDINGS.md -->\n{r['text']}" for r in note_rows]
    files: dict[str, list[str]] = {
        "findings-01-open.md": [r["text"] for r in open_rows],
        **split_parts([r["text"] for r in closed_rows], "findings-02-closed"),
        "findings-03-drive-notes.md": notes,
    }
    where = {item: name for name, items in files.items() for item in items}

    counts = collections.Counter(r["state"] for r in rows)
    lines = [
        "# Findings index\n\n",
        f"Generated from scripts/drive/FINDINGS.md: {len(rows)} sections. "
        + ", ".join(f"{k} {v}" for k, v in counts.most_common())
        + ".\n\n`stale?` means a commit subject on master names the finding as fixed while its "
        "own status does not. It is a hint, not a verdict.\n\n",
        "| Finding | Sev | State | Hint | Title | File |\n|---|---|---|---|---|---|\n",
    ]
    for row in rows:
        if row["id"]:
            lines.append(
                f"| {row['id']} | {row['sev']} | {row['state']} | {row.get('hint', '')} "
                f"| {title_of(row['text'])} | {where[row['text']]} |\n"
            )
    files = {"findings-00-index.md": lines, **files}

    out.mkdir(parents=True, exist_ok=True)
    for name, items in files.items():
        body = "".join(items)
        size = len(body.encode("utf-8"))
        if size > 1_048_576:
            print(f"refused: {name} is {size} bytes, over the vault's limit", file=sys.stderr)
            return 1
        (out / name).write_text(body, encoding="utf-8", newline="")
        print(f"{name}\t{size}")
    print(dict(counts))
    print("stale hints", sum(1 for r in rows if r.get("hint")))
    for row in open_rows:
        if row["hint"] or row["state"] != "open":
            print(row["id"], row["sev"], row["state"], row["hint"], title_of(row["text"])[:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
