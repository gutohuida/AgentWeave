"""Translate the openspec corpus into AgentWeave specification payloads.

`openspec/specs/<capability>/spec.md` → a `submit_spec_document`-shaped payload, written to
`spec/capabilities/<capability>/spec.html` by the Hub. This script never writes HTML: it produces
structure and hands it to the Hub, which renders the document, mints the requirement identifiers
and owns the result. Writing markup here would produce a file the Hub does not treat as a document.

**Fidelity is the point.** Nothing is invented. Where the source has no counterpart for a field the
schema requires, the field is empty and the omission is recorded in the document's own `evidence.limits`
rather than being papered over with plausible prose. 1,270 of the corpus's 1,301 scenarios (97.6%)
state WHEN/THEN with no GIVEN; authoring a starting state for each would be 1,270 pieces of writing
that are not in the source and that nobody reviewed. `given` is therefore empty for those, which the
payload schema accepts.

Usage:

    # Convert only — write payloads to a staging directory and report what was lost
    py -3.11 scripts/migrate_openspec_corpus.py --out .migration/payloads

    # Convert and import into a running Hub
    py -3.11 scripts/migrate_openspec_corpus.py --hub http://127.0.0.1:8020 \
        --project proj-xxxx --key aw_live_xxx [--only agent-loops,task-lifecycle-governance]

Import is idempotent: the document is created if absent (409 is tolerated) and its content is
written with `PUT`, so an interrupted run is safe to repeat.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SOURCE_ROOT = Path("openspec/specs")
SCHEMA_VERSION = 1

#: A Purpose the archiver stubbed and nobody revisited. Importing this text would put a note about
#: openspec's own workflow into an AgentWeave document, where it means nothing.
TBD_PURPOSE = re.compile(r"^TBD\b.*created by archiving", re.I)

MODALS = ("SHALL NOT", "MUST NOT", "SHALL", "MUST", "SHOULD NOT", "SHOULD", "MAY")

#: `modal` is a single obligation, and the schema offers no negative form. A prohibition is still
#: that obligation — "MUST NOT" is a MUST — so the modal is recorded and the negation stays in the
#: statement prose, where it already is.
MODAL_CANONICAL = {
    "SHALL NOT": "SHALL",
    "MUST NOT": "MUST",
    "SHOULD NOT": "SHOULD",
}


@dataclass
class Limit:
    """Something the translation could not carry, recorded rather than smoothed over."""

    code: str
    detail: str

    def render(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass
class Capability:
    name: str
    title: str
    summary: str
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    acceptance_criteria: List[Dict[str, Any]] = field(default_factory=list)
    limits: List[Limit] = field(default_factory=list)

    @property
    def path(self) -> str:
        return f"spec/capabilities/{self.name}/spec.html"

    def payload(self, source: Path) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "capability",
            "title": self.title,
            "summary": self.summary,
            "problem": "",
            "scope": {"in_scope": [], "non_goals": []},
            "requirements": self.requirements,
            "acceptance_criteria": self.acceptance_criteria,
            "tasks": [],
            "algorithms": [],
            "design": "",
            "lifecycle": "",
            "open_questions": [],
            "evidence": {
                "checked": [
                    f"Translated from {source.as_posix()} "
                    f"({len(self.requirements)} requirements, {len(self.acceptance_criteria)} criteria). "
                    "Requirement text and scenario WHEN/THEN are carried verbatim; nothing was "
                    "rewritten."
                ],
                "limits": [limit.render() for limit in self.limits] or [
                    "No structure was lost in translation."
                ],
            },
        }


def slug(text: str, taken: set) -> str:
    """A stable lowercase-hyphenated key from a requirement's name.

    The key is how a requirement's permanent identifier survives a rewording, so it is derived from
    the source's own requirement name rather than from its position — a requirement that moves in
    the file keeps its key, and a re-import matches it to the identifier the Hub already minted.
    """
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "requirement"
    candidate, suffix = base, 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def find_modal(text: str) -> Optional[str]:
    """The obligation a requirement carries, taken from its own prose."""
    for modal in MODALS:
        if re.search(rf"\b{modal}\b", text):
            return MODAL_CANONICAL.get(modal, modal)
    return None


def _clean(lines: List[str]) -> str:
    """Join wrapped markdown prose into one paragraph, preserving the words exactly."""
    return " ".join(line.strip() for line in lines if line.strip())


def parse_scenario(name: str, body: str) -> Tuple[Dict[str, str], List[Limit]]:
    """One scenario's GIVEN/WHEN/THEN, with `AND` folded into whatever preceded it."""
    limits: List[Limit] = []
    parts: Dict[str, List[str]] = {"given": [], "when": [], "then": []}
    current: Optional[str] = None
    extra_cycles = 0

    for raw in body.splitlines():
        line = raw.strip()
        matched = re.match(r"^-\s*\*\*(GIVEN|WHEN|THEN|AND)\*\*\s*(.*)$", line)
        if not matched:
            if current and line.startswith("-"):
                # A bare bullet continuing the previous clause.
                parts[current].append(line.lstrip("- ").strip())
            continue
        label, text = matched.group(1), matched.group(2).strip()
        if label == "AND":
            if current is None:
                continue
            parts[current].append(text)
            continue
        target = label.lower()
        if parts[target] and target == "when":
            # A second WHEN in one scenario is a second scenario wearing one name. Rare (2 in the
            # corpus); recorded rather than silently flattened into an unreadable clause.
            extra_cycles += 1
        parts[target].append(text)
        current = target

    if extra_cycles:
        limits.append(
            Limit(
                "scenario-had-multiple-cycles",
                f"'{name}' states {extra_cycles + 1} WHEN/THEN cycles under one name; they are "
                "joined into one criterion because a criterion has one of each",
            )
        )

    criterion = {key: _clean(value) for key, value in parts.items()}
    if not criterion["given"]:
        # Deliberate and by far the common case. Not recorded per-scenario — 1,270 identical
        # entries would bury every other limit — but summarised once per document by the caller.
        pass
    return criterion, limits


def parse_capability(source: Path) -> Capability:
    text = source.read_text(encoding="utf-8")
    name = source.parent.name

    heading = re.search(r"^#\s+(.*?)\s*$", text, re.M)
    title = heading.group(1) if heading else name
    title = re.sub(r"\s+Specification$", "", title).strip()
    # `agent-loops Specification` is the archiver's slug, not a title anyone chose.
    if title == name:
        title = name.replace("-", " ").capitalize()

    limits: List[Limit] = []

    purpose_match = re.search(r"^##\s+Purpose\s*$(.*?)^##\s", text, re.M | re.S)
    purpose = _clean(purpose_match.group(1).splitlines()) if purpose_match else ""
    if TBD_PURPOSE.match(purpose):
        limits.append(
            Limit(
                "source-had-no-purpose",
                "the source's Purpose was an unedited archiving placeholder, so this document has "
                "no summary rather than a note about openspec's workflow",
            )
        )
        purpose = ""

    capability = Capability(name=name, title=title, summary=purpose, limits=limits)

    keys: set = set()
    blocks = re.split(r"^###\s+Requirement:\s*", text, flags=re.M)[1:]
    if not blocks:
        capability.limits.append(Limit("no-requirements", "the source declares no requirements"))
        return capability

    criterion_index = 0
    missing_given = 0

    for block in blocks:
        lines = block.splitlines()
        requirement_name = lines[0].strip()
        rest = "\n".join(lines[1:])

        scenario_split = re.split(r"^####\s+Scenario:\s*", rest, flags=re.M)
        prose = scenario_split[0]
        # `---` separates requirements in several documents; it is not part of the statement.
        prose = re.sub(r"^---\s*$", "", prose, flags=re.M)
        paragraphs = [p for p in re.split(r"\n\s*\n", prose) if p.strip()]

        statement = _clean(paragraphs[0].splitlines()) if paragraphs else requirement_name
        rationale = (
            " ".join(_clean(p.splitlines()) for p in paragraphs[1:]) if len(paragraphs) > 1 else None
        )

        modal = find_modal(statement) or find_modal(rationale or "")
        if modal is None:
            # The Hub refuses a requirement with no obligation, and the corpus's own rule is that
            # requirements use MUST/SHALL. A requirement stating neither is a source defect; SHALL
            # is assumed so the document can be imported, and the assumption is recorded.
            modal = "SHALL"
            capability.limits.append(
                Limit(
                    "requirement-had-no-modal",
                    f"'{requirement_name}' states no MUST/SHALL/SHOULD/MAY in the source; SHALL was "
                    "assumed so it could be imported — worth an operator's eye",
                )
            )

        key = slug(requirement_name, keys)
        capability.requirements.append(
            {
                "key": key,
                "statement": statement,
                "modal": modal,
                "rationale": rationale,
                "party": None,
            }
        )

        for scenario_block in scenario_split[1:]:
            scenario_lines = scenario_block.splitlines()
            scenario_name = scenario_lines[0].strip()
            criterion, scenario_limits = parse_scenario(
                scenario_name, "\n".join(scenario_lines[1:])
            )
            capability.limits.extend(scenario_limits)
            if not criterion["given"]:
                missing_given += 1
            if not criterion["when"] and not criterion["then"]:
                capability.limits.append(
                    Limit(
                        "scenario-had-no-clauses",
                        f"'{scenario_name}' states neither WHEN nor THEN and was dropped",
                    )
                )
                continue
            criterion_index += 1
            capability.acceptance_criteria.append(
                {
                    "key": f"ac{criterion_index}",
                    "requirement": key,
                    "given": criterion["given"],
                    "when": criterion["when"],
                    "then": criterion["then"],
                }
            )

    if missing_given:
        capability.limits.append(
            Limit(
                "scenarios-state-no-starting-state",
                f"{missing_given} of {len(capability.acceptance_criteria)} criteria have an empty "
                "GIVEN because the source scenario states only WHEN/THEN. Left empty rather than "
                "invented — a starting state written here would be new prose nobody reviewed",
            )
        )

    return capability


class Hub:
    def __init__(self, base: str, project: str, key: str) -> None:
        self.base = base.rstrip("/")
        self.project = project
        self.key = key

    def _call(self, method: str, path: str, payload: Optional[dict] = None) -> Tuple[int, Any]:
        request = urllib.request.Request(
            f"{self.base}/api/v1/projects/{self.project}/project{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw

    def import_capability(self, capability: Capability, payload: dict) -> Tuple[bool, str]:
        status, body = self._call(
            "POST",
            "/documents",
            {"path": capability.path, "title": capability.title, "kind": "capability"},
        )
        if status not in (201, 409):
            return False, f"create failed ({status}): {body}"

        status, body = self._call(
            "PUT", f"/documents/{capability.path}/content", {"document": payload}
        )
        if status != 200:
            return False, f"write failed ({status}): {body}"
        return True, f"{len(body.get('identifiers') or {})} identifiers"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write payloads here as JSON")
    parser.add_argument("--hub", help="base URL of a running Hub, e.g. http://127.0.0.1:8020")
    parser.add_argument("--project", help="project id to import into")
    parser.add_argument("--key", help="operator credential (aw_live_...)")
    parser.add_argument("--only", help="comma-separated capability names to convert")
    args = parser.parse_args()

    if not SOURCE_ROOT.is_dir():
        print(f"no corpus at {SOURCE_ROOT} — run from the repository root", file=sys.stderr)
        return 2

    wanted = {n.strip() for n in args.only.split(",")} if args.only else None
    sources = sorted(SOURCE_ROOT.glob("*/spec.md"))
    if wanted:
        sources = [s for s in sources if s.parent.name in wanted]

    hub = Hub(args.hub, args.project, args.key) if args.hub else None
    if hub and not (args.project and args.key):
        print("--hub also needs --project and --key", file=sys.stderr)
        return 2

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)

    total_requirements = total_criteria = 0
    all_limits: List[str] = []
    failures = 0

    for source in sources:
        capability = parse_capability(source)
        payload = capability.payload(source)
        total_requirements += len(capability.requirements)
        total_criteria += len(capability.acceptance_criteria)

        if args.out:
            (args.out / f"{capability.name}.json").write_text(
                json.dumps({"path": capability.path, "document": payload}, indent=2), encoding="utf-8"
            )

        note = ""
        if hub:
            ok, note = hub.import_capability(capability, payload)
            if not ok:
                failures += 1
                note = f"FAILED — {note}"

        print(
            f"{capability.name:34s} {len(capability.requirements):3d} req "
            f"{len(capability.acceptance_criteria):4d} ac  {note}"
        )
        for limit in capability.limits:
            all_limits.append(f"{capability.name}: {limit.render()}")

    print(
        f"\n{len(sources)} capabilities, {total_requirements} requirements, {total_criteria} criteria"
    )
    if all_limits:
        print(f"\n{len(all_limits)} recorded limits:")
        for entry in all_limits:
            print(f"  - {entry}")
    if failures:
        print(f"\n{failures} capabilities failed to import", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
