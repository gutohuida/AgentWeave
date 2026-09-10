"""Warn when two in-flight openspec changes touch the same requirement.

**The incident this exists for.** Applying a delta against the current corpus warns about
nothing when two changes both carry a `## MODIFIED` block for the same requirement. Archiving
the second **reverted the first**, dropping a qualification that had just landed. It was caught
only because the diff was read before committing — one collision in a batch of seven. Two
changes in flight against one requirement is not rare in this repository.

**What a collision is here.** A `(capability, requirement name)` pair named by more than one
change in the scanned set. The key is the pair, *not* the file path: the same requirement is
reached through `<change>/specs/<capability>/spec.md` in every change that touches it, so
comparing paths would find every collision and comparing whole files would find none.

**Why every section kind counts, not only MODIFIED.** The scanned set is the changes that have
*not yet been applied*, so their order is undecided and every pairing is order-dependent:

| pairing | what applying them in the wrong order does |
|---|---|
| MODIFIED + MODIFIED | the second silently reverts the first — **the incident above** |
| ADDED + MODIFIED | modifying a requirement the other change has not added yet |
| ADDED + ADDED | two changes create the same requirement; one text survives |
| anything + REMOVED | the other change's work is deleted, or applies to nothing |

The first is called out separately in the report because it is the one that fails *silently* —
the others tend to surface as an apply error or a visible duplicate.

**Pointing this at `openspec/changes/archive` is a demonstration, not a verdict.** The archive
is a historical *sequence* spanning months, so a requirement added by an old change and modified
by a recent one is the normal lifecycle rather than a collision. Only the concurrent set — the
unarchived changes, which is the default target — is a set whose order is still open.

Usage:

    # The default target: everything in flight, archive/ excluded
    py -3.11 scripts/check_openspec_collisions.py

    # Point it anywhere, including at the archive, to see it find real collisions
    py -3.11 scripts/check_openspec_collisions.py --changes-dir openspec/changes/archive

Exit codes: 0 no collisions, 1 collisions found, 2 the directory could not be scanned.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, NamedTuple, Tuple

DEFAULT_CHANGES_DIR = Path("openspec/changes")

#: The three section headers openspec deltas use. A `## ` header that is none of these is
#: reported rather than ignored — an unrecognised section is a parser that has fallen behind
#: the format, and this script going quiet is indistinguishable from a clean corpus.
SECTION_RE = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED)\s+Requirements\s*$")
REQUIREMENT_RE = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")

#: MODIFIED against MODIFIED is the pairing that produced the incident, and the only one that
#: leaves no trace when it fires.
SILENT_REVERT = "MODIFIED"


class Touch(NamedTuple):
    """One change naming one requirement in one section of one capability's delta."""

    change: str
    section: str
    path: Path
    line: int


class ParseWarning(NamedTuple):
    path: Path
    line: int
    text: str


def parse_delta(path: Path) -> Tuple[List[Tuple[str, str, int]], List[ParseWarning]]:
    """Return (section, requirement name, line number) triples found in one delta file.

    Fenced blocks are skipped: a `### Requirement:` line inside an example would otherwise be
    counted as a real one. A requirement that appears before any section header is *not*
    silently dropped — it comes back as a warning, because a delta this script cannot read is
    a delta whose collisions it cannot see.
    """
    found: List[Tuple[str, str, int]] = []
    warnings: List[ParseWarning] = []
    section: str | None = None
    in_fence = False

    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        header = SECTION_RE.match(line)
        if header:
            section = header.group(1)
            continue
        if line.startswith("## "):
            warnings.append(ParseWarning(path, number, f"unrecognised section header: {line.strip()}"))
            section = None
            continue

        requirement = REQUIREMENT_RE.match(line)
        if requirement:
            if section is None:
                warnings.append(
                    ParseWarning(path, number, f"requirement outside any section: {requirement.group(1)}")
                )
                continue
            found.append((section, requirement.group(1), number))

    return found, warnings


def scan(changes_dir: Path) -> Tuple[Dict[Tuple[str, str], List[Touch]], List[ParseWarning], int]:
    """Collect every requirement touched by every change under `changes_dir`.

    The change and capability are derived **relative to `changes_dir`**, never from absolute
    path positions: `<change>/specs/<capability>/spec.md` holds whether the root is
    `openspec/changes` or `openspec/changes/archive`. Hardcoding the indices for one layout
    makes the other scan report zero collisions, which reads exactly like a clean corpus.
    """
    touched: Dict[Tuple[str, str], List[Touch]] = defaultdict(list)
    warnings: List[ParseWarning] = []
    files = 0

    for path in sorted(changes_dir.glob("*/specs/*/spec.md")):
        relative = path.relative_to(changes_dir).parts
        change, capability = relative[0], relative[2]
        # Excluded only when it is a sibling of the changes being scanned. Naming the archive
        # as the root makes its children the changes, and none of those is called `archive`.
        if change == "archive":
            continue
        files += 1
        found, file_warnings = parse_delta(path)
        warnings.extend(file_warnings)
        for section, requirement, line in found:
            touched[(capability, requirement)].append(Touch(change, section, path, line))

    return touched, warnings, files


def collisions(
    touched: Dict[Tuple[str, str], List[Touch]],
) -> List[Tuple[Tuple[str, str], List[Touch]]]:
    """Keys named by more than one *change*. Two blocks in one change are that change's business."""
    found = [(key, sorted(hits)) for key, hits in touched.items() if len({h.change for h in hits}) > 1]
    # Silent reverts first, then by capability and requirement so the report is stable.
    found.sort(key=lambda item: (not is_silent_revert(item[1]), item[0]))
    return found


def is_silent_revert(hits: List[Touch]) -> bool:
    """True when two or more distinct changes MODIFY this requirement."""
    return len({h.change for h in hits if h.section == SILENT_REVERT}) > 1


def report(
    found: List[Tuple[Tuple[str, str], List[Touch]]],
    warnings: List[ParseWarning],
    files: int,
    changes_dir: Path,
    stream=None,
) -> None:
    # Resolved here, not as a default argument: a default binds the `sys.stdout` that existed
    # at import, so a caller using `redirect_stdout` (or pytest's `capsys`) would capture
    # nothing while the report went to the original stream.
    stream = sys.stdout if stream is None else stream
    silent = [item for item in found if is_silent_revert(item[1])]

    print(f"Scanned {files} delta file(s) under {changes_dir}.", file=stream)
    for warning in warnings:
        print(f"  parse warning: {warning.path}:{warning.line}: {warning.text}", file=stream)

    if not found:
        print("No requirement is touched by more than one change.", file=stream)
        return

    print(
        f"\n{len(found)} requirement(s) touched by more than one change; "
        f"{len(silent)} of them modified by two or more changes.",
        file=stream,
    )

    for (capability, requirement), hits in found:
        marker = "SILENT REVERT" if is_silent_revert(hits) else "ORDER-DEPENDENT"
        print(f"\n[{marker}] {capability} | {requirement}", file=stream)
        for hit in hits:
            print(f"    {hit.section:<8}  {hit.change}  ({hit.path}:{hit.line})", file=stream)

    if silent:
        print(
            "\nA SILENT REVERT pair is the incident this check exists for: applying the second"
            "\ndelta rewrites the requirement wholesale and drops whatever the first one landed,"
            "\nwith no warning from openspec. Reconcile the two blocks before archiving either.",
            file=stream,
        )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Warn when two openspec changes touch the same requirement.",
        epilog="Run this before archiving a change.",
    )
    parser.add_argument(
        "--changes-dir",
        type=Path,
        default=DEFAULT_CHANGES_DIR,
        help=f"directory holding <change>/specs/<capability>/spec.md (default: {DEFAULT_CHANGES_DIR})",
    )
    args = parser.parse_args(argv)

    changes_dir: Path = args.changes_dir
    if not changes_dir.is_dir():
        print(f"error: not a directory: {changes_dir}", file=sys.stderr)
        return 2

    touched, warnings, files = scan(changes_dir)
    found = collisions(touched)
    report(found, warnings, files, changes_dir)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
