"""Reading what a specification document says, for the surfaces that need the words.

The requirement index holds no wording — deliberately, so that
`SpecRequirement` "cannot come to disagree with the document about what a requirement says". That
decision is right and this module is what makes it affordable: the wording is read from the file at
the moment somebody needs it, so there is exactly one place it can come from and it is the document.

Two callers, both of which used to make an identifier the *only* thing they could offer:

- a task, which carries requirement identifiers and until now nothing an implementer could read;
- an agent asking to read the document it was told to implement.

**Batched by document, never by requirement.** A board of a hundred tasks drawn from three documents
is three file reads. Reading per task would make a task board's cost a function of how thoroughly the
work was decomposed, which is exactly backwards.

**Nothing here raises.** A project directory that has moved, a file somebody deleted, a document
written before payloads existed — each yields "no wording available", never an error. A task board
that fails because a specification is unreadable has turned a missing convenience into an outage.
"""

from __future__ import annotations

import json
import os
import textwrap
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_documents, spec_identity
from .db.models import SpecDocument, SpecRequirement
from .project_workspace import ProjectWorkspace

#: Returned in place of a requirement list when the document carries no payload at all — a
#: hand-written file, or one from a version predating the block. "Unknown" is not "empty", and a
#: reader told a document has no requirements would draw the wrong conclusion from the right data.
PAYLOAD_MISSING = "payload_missing"


async def payloads_for_documents(
    session: AsyncSession,
    workspace: Optional[ProjectWorkspace],
    document_ids: Iterable[str],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """`{document_id: payload or None}`, one file read per distinct document."""
    wanted = [document_id for document_id in dict.fromkeys(document_ids) if document_id]
    if not wanted or workspace is None:
        return {}

    rows = (
        (await session.execute(select(SpecDocument).where(SpecDocument.id.in_(wanted))))
        .scalars()
        .all()
    )

    payloads: Dict[str, Optional[Dict[str, Any]]] = {}
    for row in rows:
        try:
            content = spec_documents.read_document(workspace, row.path)
        except Exception:
            # A path that no longer resolves, a directory that moved, a permission problem. The
            # wording is unavailable; that is all this means.
            content = None
        payloads[row.id] = spec_documents.parse_stored(content)
    return payloads


def statements_by_key(payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """`{requirement key: {statement, modal, rationale, party}}` as the document states it."""
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("requirements")
    if not isinstance(raw, list):
        return {}
    indexed: Dict[str, Dict[str, Any]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if isinstance(key, str) and key:
            indexed[key] = {
                "statement": entry.get("statement"),
                "modal": entry.get("modal"),
                "rationale": entry.get("rationale"),
                "party": entry.get("party"),
            }
    return indexed


def criteria_by_requirement_key(
    payload: Optional[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """`{requirement key: [criterion, ...]}`.

    Acceptance criteria arrive as a sibling list keyed by requirement *key*. Every reader wanting to
    show a requirement wants its criteria with it, so the join happens once here rather than being
    re-derived — wrongly, for a document whose criteria interleave — by each caller.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    if not isinstance(payload, dict):
        return grouped
    raw = payload.get("acceptance_criteria")
    if not isinstance(raw, list):
        return grouped
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        owner = entry.get("requirement")
        if not isinstance(owner, str) or not owner:
            continue
        criterion = {
            "key": entry.get("key"),
            "given": entry.get("given"),
            "when": entry.get("when"),
            "then": entry.get("then"),
        }
        # Only when set, so a read of a document without them is unchanged, and a resubmitted read
        # keeps them (F452's shape).
        for key in ("how_to_check", "checked_by"):
            if entry.get(key) is not None:
                criterion[key] = entry[key]
        grouped.setdefault(owner, []).append(criterion)
    return grouped


def requirement_view(
    payload: Optional[Dict[str, Any]], rows: List[SpecRequirement]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """`(requirements, diagnostics)` — the document's requirements with their minted identifiers.

    Driven by the **rows**, because they are what tasks, evidence and gates point at. A requirement
    the document declares but the index has never seen is still returned, with a diagnostic and a
    null identifier: dropping it would hide a document and an index that disagree, which is the one
    condition a reader most needs to know about.
    """
    diagnostics: List[Dict[str, Any]] = []
    if payload is None:
        return [], [{"problem": PAYLOAD_MISSING}]

    wording = statements_by_key(payload)
    criteria = criteria_by_requirement_key(payload)
    seen_keys = set()

    requirements: List[Dict[str, Any]] = []
    for row in sorted(rows, key=_identifier_order):
        seen_keys.add(row.key)
        stated = wording.get(row.key)
        if stated is None and row.state == "active":
            # An active requirement the document no longer words. Retired ones are expected to have
            # no wording — that is what retirement means — so only this case is worth reporting.
            diagnostics.append(
                {
                    "identifier": row.identifier,
                    "problem": "the document no longer states this requirement",
                }
            )
        requirements.append(
            {
                "identifier": row.identifier,
                "key": row.key,
                "state": row.state,
                "anchor": row.anchor,
                "statement": (stated or {}).get("statement"),
                "modal": (stated or {}).get("modal"),
                "rationale": (stated or {}).get("rationale"),
                "party": (stated or {}).get("party"),
                "acceptance_criteria": criteria.get(row.key, []),
            }
        )

    identities, _ = spec_identity.read_identity(payload)
    for key, stated in wording.items():
        if key in seen_keys:
            continue
        # Declared in the document and absent from the index. Returned rather than dropped, with
        # whatever identity the document itself claims, so the disagreement is visible.
        requirements.append(
            {
                "identifier": identities.get(key),
                "key": key,
                "state": "unindexed",
                "anchor": "",
                "statement": stated.get("statement"),
                "modal": stated.get("modal"),
                "rationale": stated.get("rationale"),
                "party": stated.get("party"),
                "acceptance_criteria": criteria.get(key, []),
            }
        )
        diagnostics.append(
            {
                "identifier": identities.get(key),
                "problem": "the document declares this requirement and the index has not seen it",
            }
        )

    return requirements, diagnostics


def _identifier_order(row: SpecRequirement) -> Tuple[int, str]:
    """`FR-2` before `FR-10`. Sorting identifiers as strings is how a reader loses the tenth."""
    identifier = row.identifier or ""
    _, _, number = identifier.partition("-")
    return (int(number), identifier) if number.isdigit() else (10**9, identifier)


# --------------------------------------------------------------------------- the read budget

#: The most a `read_spec_document` answer may serialise to inline, measured as
#: `len(json.dumps(view))` over the whole response (`a-specification-is-read-in-results-that-fit`
#: D1, D7). Claude Code spills a tool result to a `tool-results/` file the workspace guard may then
#: refuse (F363): above 50,000 characters for an MCP result, but above 30,000 for a shell tool's
#: output, which is how `aw-tool` delivers the same read (`BASH_MAX_OUTPUT_LENGTH`; on the
#: 2026-10-07 drive a 37.6 KB read spilled). 25,000 fits both with margin. A read that does not fit
#: is written to a file in the agent's workspace instead (`write_read`); this bound is what an
#: inline answer, and the fallback where there is no workspace, keep to.
READ_BUDGET_CHARS = 25_000

#: Offered on a first read only, each where it fits; a read naming `identifiers` leaves them out
#: (operator decision, 2026-09-24).
PREAMBLE_FIELDS = ("summary", "problem", "scope", "open_questions")

#: Added only where they fit whole, otherwise named in `omitted_sections`.
OPTIONAL_SECTIONS = ("design", "tasks", "algorithms", "evidence", "lifecycle", "slices", "roadmap")


def _size(value: Any) -> int:
    return len(json.dumps(value))


def _name_of(row: Dict[str, Any]) -> str:
    """How a requirement is asked for again: its identifier, or its key where it has none (D3)."""
    return str(row.get("identifier") or row.get("key") or "")


def _cut_text(text: str, room: int) -> str:
    """*text* cut so that its JSON encoding is at most *room* characters."""
    if _size(text) <= room:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _size(text[:middle]) <= room:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def _cut_value(value: Any, room: int) -> Any:
    """A string or a list cut to fit *room*; anything else is returned whole."""
    if isinstance(value, str):
        return _cut_text(value, room)
    if isinstance(value, list):
        kept: List[Any] = []
        for item in value:
            if _size([*kept, item]) > room:
                break
            kept.append(item)
        return kept
    return value


def _cut_requirement(row: Dict[str, Any], room: int) -> Dict[str, Any]:
    """The first requirement, made to fit: criteria dropped from the end, then the statement cut."""
    cut = {**row, "section_truncated": True}
    criteria = list(cut.get("acceptance_criteria") or [])
    while criteria and _size(cut) > room:
        criteria.pop()
        cut["acceptance_criteria"] = criteria
    if _size(cut) > room and isinstance(cut.get("statement"), str):
        over = _size(cut) - room
        cut["statement"] = _cut_text(cut["statement"], max(0, _size(cut["statement"]) - over - 2))
    return cut


def _continue_sentence(remaining: List[str], omitted: List[str]) -> str:
    parts = []
    if remaining:
        parts.append(
            "call read_spec_document again with identifiers=" + ",".join(remaining) + " (or fewer)"
        )
    if omitted:
        parts.append(
            "omitted sections can be read with include=<section> (" + ", ".join(omitted) + ")"
        )
    return "; ".join(parts) + "."


def fit_view(
    view: Dict[str, Any], *, budget: int = READ_BUDGET_CHARS, named: Optional[str] = None
) -> Dict[str, Any]:
    """*view* bounded to *budget* serialised characters, saying how to read what was left out (D2).

    A view that fits is returned unchanged. Otherwise the fixed fields always go in; the preamble
    fields each where they fit; requirements in the order given (the route's identifier order)
    while they fit; optional sections only whole. The first requirement always goes in, cut and
    marked if it alone is too large, and so does a section asked for by name (*named*), so every
    read makes progress. What was left out is named in `remaining_identifiers` and
    `omitted_sections`, with `continue_with` saying the call to make.
    """
    if _size(view) <= budget:
        return view

    requirements = list(view.get("requirements") or [])
    held_back = set(PREAMBLE_FIELDS) | set(OPTIONAL_SECTIONS) | {"requirements"}
    out: Dict[str, Any] = {k: v for k, v in view.items() if k not in held_back}
    if "requirements" in view:
        out["requirements"] = []
    omitted: List[str] = []

    # Room for the continuation fields, sized as if nothing were returned (their largest).
    every_name = [_name_of(row) for row in requirements]
    reserve = 2 * _size(every_name) + 400 + _size(list(PREAMBLE_FIELDS + OPTIONAL_SECTIONS))
    room = budget - reserve

    if named is not None and named in view:
        whole = view[named]
        if _size({**out, named: whole}) <= room:
            out[named] = whole
        else:
            spare = max(0, room - _size(out) - len(named) - 40)
            out[named] = _cut_value(whole, spare)
            out["section_truncated"] = named

    for name in PREAMBLE_FIELDS:
        if name in view and name != named:
            if _size({**out, name: view[name]}) <= room:
                out[name] = view[name]
            else:
                omitted.append(name)

    taken = 0
    for row in requirements:
        if _size({**out, "requirements": [*out["requirements"], row]}) > room:
            break
        out["requirements"].append(row)
        taken += 1
    if requirements and taken == 0:
        spare = max(0, room - _size(out))
        out["requirements"].append(_cut_requirement(requirements[0], spare))
        taken = 1

    for name in OPTIONAL_SECTIONS:
        if name in view and name != named:
            if _size({**out, name: view[name]}) <= room:
                out[name] = view[name]
            else:
                omitted.append(name)

    remaining = every_name[taken:]
    if remaining or omitted or "section_truncated" in out:
        out["truncated"] = True
        out["remaining_identifiers"] = remaining
        out["omitted_sections"] = omitted
        out["continue_with"] = _continue_sentence(remaining, omitted)

    # The reserve is an estimate; never answer over the budget while a requirement can be given back.
    while _size(out) > budget and len(out.get("requirements") or []) > 1:
        out["requirements"].pop()
        taken -= 1
        remaining = every_name[taken:]
        out["truncated"] = True
        out["remaining_identifiers"] = remaining
        out["continue_with"] = _continue_sentence(remaining, omitted)
    return out


# --------------------------------------------------------------------------- a read written to a file

#: Where a read too large to answer inline is written, relative to the agent's workspace (D7). Under
#: `.agentweave/`, which `repo_hygiene.EXCLUDE_PATTERNS` keeps out of every commit.
READS_DIR = (".agentweave", "reads")

#: Lines in the written read are wrapped to this width: the Read tool cuts a line over 2,000
#: characters, and a requirement's statement or a design section is one paragraph.
_WRAP = 100


def _wrapped(text: Any, indent: str = "") -> List[str]:
    lines: List[str] = []
    for paragraph in str(text if text is not None else "").splitlines() or [""]:
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(
                paragraph,
                width=_WRAP,
                initial_indent=indent,
                subsequent_indent=indent,
                break_long_words=True,
                break_on_hyphens=False,
            )
        )
    return lines


def _structured(value: Any) -> List[str]:
    """A dict or list section, as indented JSON with every line wrapped."""
    lines: List[str] = []
    for line in json.dumps(value, indent=2, ensure_ascii=False).splitlines():
        stripped = line.lstrip(" ")
        lines.extend(_wrapped(stripped, " " * (len(line) - len(stripped))) or [line])
    return lines


def render_read(view: Dict[str, Any]) -> str:
    """The read as plain text an agent pages through with its file-reading tool.

    Everything the inline answer would carry, in reading order: the document's facts, the preamble,
    each requirement with its criteria, then any other section. Every line is at most `_WRAP`
    characters plus its indentation, so no tool cuts one.
    """
    lines: List[str] = [f"# {view.get('title') or view.get('path')}", ""]
    for name in ("id", "path", "kind", "phase", "rigor", "diverged", "updated_at"):
        if name in view:
            lines.append(f"{name}: {view[name]}")
    if view.get("divergence"):
        lines.extend(["", "## Divergence", *_wrapped(view["divergence"].get("detail"))])
    if view.get("diagnostics"):
        lines.extend(["", "## Diagnostics", *_structured(view["diagnostics"])])
    for name in PREAMBLE_FIELDS:
        value = view.get(name)
        if value in (None, "", [], {}):
            continue
        lines.extend(["", f"## {name.replace('_', ' ').capitalize()}"])
        lines.extend(_wrapped(value) if isinstance(value, str) else _structured(value))
    requirements = view.get("requirements")
    if requirements:
        lines.extend(["", "## Requirements"])
        for row in requirements:
            heading = f"### {row.get('identifier') or '(no identifier)'} (key: {row.get('key')})"
            lines.extend(["", heading])
            facts = [f"{k}: {row[k]}" for k in ("modal", "state", "party") if row.get(k)]
            if facts:
                lines.append(" · ".join(facts))
            lines.extend(_wrapped(row.get("statement")))
            if row.get("rationale"):
                lines.extend(_wrapped(f"Rationale: {row['rationale']}"))
            for criterion in row.get("acceptance_criteria") or []:
                lines.append(f"- criterion {criterion.get('key')}:")
                for part in ("given", "when", "then"):
                    if criterion.get(part):
                        lines.extend(_wrapped(f"{part.capitalize()} {criterion[part]}", "    "))
                if criterion.get("how_to_check"):
                    who = f" ({criterion['checked_by']})" if criterion.get("checked_by") else ""
                    lines.extend(_wrapped(f"Check{who}: {criterion['how_to_check']}", "    "))
    for name in OPTIONAL_SECTIONS:
        value = view.get(name)
        if value in (None, "", [], {}):
            continue
        lines.extend(["", f"## {name.capitalize()}"])
        lines.extend(_wrapped(value) if isinstance(value, str) else _structured(value))
    if view.get("unknown_identifiers"):
        lines.extend(["", "unknown identifiers: " + ", ".join(view["unknown_identifiers"])])
    return "\n".join(lines) + "\n"


def reads_directory(workspace_dir: str) -> Optional[str]:
    """`<workspace>/.agentweave/reads`, made if absent, or None where it cannot safely be written.

    Refuses to write through a link, the rule `agent_trigger.prepare_calls_dir` keeps for the calls
    directory: a `.agentweave` or `reads` that resolves elsewhere would put the Hub's write where the
    agent chose. None means "answer inline instead".
    """
    root = os.path.realpath(workspace_dir)
    if not os.path.isdir(root):
        return None
    current = root
    for part in READS_DIR:
        current = os.path.join(current, part)
        if os.path.lexists(current):
            if os.path.normcase(os.path.realpath(current)) != os.path.normcase(current):
                return None
            if not os.path.isdir(current):
                return None
    try:
        os.makedirs(current, exist_ok=True)
    except OSError:
        return None
    return current


def write_read(
    view: Dict[str, Any], workspace_dir: str, *, name: str
) -> Optional[Tuple[str, str, int, int]]:
    """Write *view* as text into the agent's workspace.

    Returns (workspace-relative path, absolute path, lines, characters), or None where it could not
    be written, and the caller answers inline instead.
    """
    directory = reads_directory(workspace_dir)
    if directory is None:
        return None
    text = render_read(view)
    target = os.path.join(directory, name)
    try:
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError:
        return None
    return "/".join((*READS_DIR, name)), target, text.count("\n"), len(text)


_ANSWER_FIELDS = (
    "id",
    "path",
    "title",
    "kind",
    "phase",
    "rigor",
    "explore_closed",
    "updated_at",
    "diverged",
    "divergence",
    "diagnostics",
    "unknown_identifiers",
)


def written_answer(
    view: Dict[str, Any], *, relative: str, absolute: str, lines: int, chars: int
) -> Dict[str, Any]:
    """The short answer for a read written to a file: the document's facts, which requirements the
    file holds, and where it is."""
    answer = {k: view[k] for k in _ANSWER_FIELDS if k in view}
    answer["requirement_identifiers"] = [_name_of(row) for row in view.get("requirements") or []]
    answer["written_to"] = relative
    answer["written_to_absolute"] = absolute
    answer["lines"] = lines
    answer["characters"] = chars
    answer["read_with"] = (
        f"This read is too large for one tool result, so all of it is in {relative} in your "
        f"workspace ({lines} lines). Open it with your file-reading tool, a part at a time if your "
        "tool limits how much it shows. It is rewritten on every read of this document."
    )
    return answer
