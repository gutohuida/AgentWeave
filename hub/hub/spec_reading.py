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

from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_documents, spec_identity, spec_payload
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
        payloads[row.id] = spec_payload.extract_payload(content) if content else None
    return payloads


def statements_by_key(payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """`{requirement key: {statement, modal, rationale, party}}` as the document states it."""
    if not isinstance(payload, dict):
        return {}
    indexed: Dict[str, Dict[str, Any]] = {}
    for entry in payload.get("requirements") or []:
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
    for entry in payload.get("acceptance_criteria") or []:
        if not isinstance(entry, dict):
            continue
        owner = entry.get("requirement")
        if not isinstance(owner, str) or not owner:
            continue
        grouped.setdefault(owner, []).append(
            {
                "key": entry.get("key"),
                "given": entry.get("given"),
                "when": entry.get("when"),
                "then": entry.get("then"),
            }
        )
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
