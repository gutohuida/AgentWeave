"""The docs vocabulary check: do the current docs describe profiles, threads and builds?

One command, from a plain checkout:

    py -3.11 scripts/checks/docs_vocabulary_check.py
    py -3.11 scripts/checks/docs_vocabulary_check.py --docs DIR   # another docs tree, e.g. an old one

Spec `profiles-threads-and-builds-everywhere`, FR-12 (criterion docs-cover-profiles). It reads every
Markdown page under docs/ except docs/archive/ and docs/snippets/, and checks:

  * one-turn       no page describes an agent (or profile) as an identity that runs one turn at a
                   time: "one turn at a time", "busy in another conversation", "when it is free"
                   and the like. The project setting that switches parallel runs off is described
                   without those words, so nothing is allowlisted;
  * old-sidebar    no page describes the retired sidebar: the agent tree, the recent-conversations
                   view, or an agent's row and its menu;
  * topics         the agents guide and the conversations guide each describe the topics FR-12
                   lists, every one found as a phrase in its guide.

It exits 1 and prints each failure as `path:line: what`, 0 when every check passes. It reads files
only: no Hub, no network. `mkdocs build --strict` is the other half of the criterion and is run
separately.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
# Not current documentation: the archive is history and snippets are fragments the pages include.
EXCLUDED = ("archive", "snippets")

# An agent described as one worker taking one turn after another (FR-12's last sentence).
ONE_TURN = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bone (turn|run) at a time\b",
        r"\bone (turn|run) after (another|the other)\b",
        r"\bbusy in another (conversation|thread)\b",
        r"\b(agent|profile) is busy\b",
        r"\bwhen (it|the agent|the profile) is free\b",
        r"\buntil (it|the agent|the profile) is free\b",
        r"\b(agent|profile)'s (one|single|only) run\b",
    )
]

# The sidebar this change retired (FR-1).
OLD_SIDEBAR = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bagent tree\b",
        r"\brecent conversations\b",
        r"\bagent's row\b",
        r"\bagent row\b",
        r"\bAdd agent\b",
        r"\bAgent settings\*\* from\b",
    )
]

# What each main guide must describe, as (topic, phrase) pairs; a phrase is a case-insensitive regex.
TOPICS: Dict[str, List[Tuple[str, str]]] = {
    "guides/agents.md": [
        ("profile", r"\bprofile\b"),
        ("charter", r"\bcharter\b"),
        ("grants", r"\bgrants\b"),
        ("posture", r"\bposture\b"),
        ("pool of runners and models", r"\bpool\b"),
        ("several runs at once", r"parallel runs"),
        ("folding", r"\bfold"),
        ("a profile's runs", r"a profile's runs"),
        ("the new-project setup offer", r"Add a\s+builder and a\s+checker"),
    ],
    "guides/conversations.md": [
        ("threads", r"\bthreads?\b"),
        ("runs", r"\bruns?\b"),
        ("the sidebar's threads", r"^### Threads"),
        ("the sidebar's builds", r"^### Builds"),
        ("a build needing you", r"needs you"),
        ("the collapsed sidebar", r"collapsed sidebar"),
        ("a flow's runs", r"flow's page"),
        ("a profile's runs", r"profile's settings, under \*\*Runs\*\*"),
        ("starting a thread with a profile", r"^## Starting a thread"),
    ],
}


def current_pages(docs: Path) -> List[Path]:
    pages = []
    for path in sorted(docs.rglob("*.md")):
        rel = path.relative_to(docs)
        if rel.parts and rel.parts[0] in EXCLUDED:
            continue
        pages.append(path)
    return pages


def scan(docs: Path, pages: List[Path]) -> List[str]:
    failures: List[str] = []
    for path in pages:
        rel = "docs/" + path.relative_to(docs).as_posix()
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            for kind, patterns in (("one-turn", ONE_TURN), ("old-sidebar", OLD_SIDEBAR)):
                for pattern in patterns:
                    match = pattern.search(line)
                    if match:
                        failures.append(f"{rel}:{number}: {kind}: {match.group(0)!r}")
    return failures


def topics(docs: Path) -> List[str]:
    failures: List[str] = []
    for page, wanted in TOPICS.items():
        path = docs / page
        if not path.is_file():
            failures.append(f"docs/{page}: topics: the page is missing")
            continue
        text = path.read_text(encoding="utf-8")
        for topic, phrase in wanted:
            if not re.search(phrase, text, re.IGNORECASE | re.MULTILINE):
                failures.append(
                    f"docs/{page}: topics: does not describe {topic} ({phrase!r} not found)"
                )
    return failures


def main(argv: List[str]) -> int:
    docs = DOCS
    if argv[:1] == ["--docs"] and len(argv) == 2:
        docs = Path(argv[1]).resolve()
    elif argv:
        print("usage: docs_vocabulary_check.py [--docs DIR]")
        return 2
    pages = current_pages(docs)
    failures = scan(docs, pages) + topics(docs)
    if failures:
        print(f"docs vocabulary: {len(failures)} failure(s) in {len(pages)} page(s)")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"docs vocabulary: ok, {len(pages)} page(s) outside docs/archive")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
