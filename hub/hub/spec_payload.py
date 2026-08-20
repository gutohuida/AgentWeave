"""The specification payload — what an agent submits, and what the Hub validates.

The agent emits structured data; the Hub renders the document. This module owns
the shape of that data, and it is deliberately the *only* statement of it on the
Hub side: the format contract used to be 713 lines of prose conventions carried
in every model's context on every turn, and it is now a schema the model is
shown by the tool protocol and cannot violate without a field-level error.

Two distinctions run through this file and are easy to lose:

**Shape versus completeness.** Validation here answers "is this a well-formed
payload?" — types, enums, referential integrity. It does *not* answer "is this
document finished?" A document being written is incomplete by definition, and
refusing to store it would make the explore phase impossible. Completeness is
checked at the transition to `proposed`, where being incomplete is what the
check is for.

**Keys versus identifiers.** The agent supplies a `key` per requirement: a
stable handle, scoped to this document, that never appears in a link. The Hub
mints the public identifier (`FR-1`) and maps it to that key. Rewording a
requirement or moving it keeps its key, and therefore its identifier; a key that
disappears retires its identifier permanently. An identifier supplied by an
agent is ignored — the agent chooses correlation, never identity.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# The contract is versioned rather than final. Gates and traceability have not
# yet stated their requirements on it, so freezing it now would ship a schema
# unable to express what they need and force every existing document to be
# migrated. Unknown fields survive a round trip precisely so a later change can
# add them to documents authored before they existed.
SCHEMA_VERSION = 1

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MODALS = ("MUST", "SHOULD", "MAY", "SHALL")
KINDS = ("baseline", "system-map", "roadmap", "change-spec", "capability")


class PayloadError(ValueError):
    """A payload that cannot be stored, with the field that made it so.

    The field path is the point. A refusal the author cannot act on produces a
    retry loop, which is the failure mode the prose contract had.
    """

    def __init__(self, message: str, *, field: str = "") -> None:
        self.field = field
        super().__init__(f"{field}: {message}" if field else message)


class _Part(BaseModel):
    # Unknown fields are kept, not rejected. This is the mechanism behind the
    # forward-compatibility requirement: a document written under a later schema
    # can be read and rewritten here without losing what this version cannot
    # name.
    model_config = ConfigDict(extra="allow")


class Requirement(_Part):
    key: str = Field(
        description="Stable handle for this requirement, unique within the document. Lowercase, hyphenated. Keep it across rewordings — it is how the requirement's permanent identifier survives an edit. It is not the identifier and never appears in a link."
    )
    statement: str = Field(
        description="What the system does, observable from outside. Specific enough to be wrong: 'a search returns within 200ms for a corpus under 10k documents', not 'the system is fast'."
    )
    modal: str = Field(
        description="The obligation this requirement carries: MUST, SHOULD, MAY, or SHALL. A requirement with no modal obligation cannot be satisfied or violated."
    )
    rationale: Optional[str] = Field(
        default=None,
        description="Why the rule exists, when that is not obvious. A rule with a stated reason survives contact with an edge case nobody listed; a bare rule gets argued away.",
    )
    party: Optional[str] = Field(
        default=None,
        description="'producer' for what a sender may emit, 'consumer' for what a receiver must do with it. Collapsing the two hides which side of a boundary a defect is on.",
    )


class AcceptanceCriterion(_Part):
    key: str = Field(description="Stable handle for this criterion, unique within the document.")
    requirement: str = Field(
        description="The key of the requirement this criterion demonstrates. Every requirement needs at least one before the document can be proposed."
    )
    given: str = Field(description="The starting state.")
    when: str = Field(description="The event or action.")
    then: str = Field(
        description="The observable outcome. Binary — it either happened or it did not."
    )


class Task(_Part):
    key: str = Field(description="Stable handle for this task, unique within the document.")
    title: str = Field(
        default="",
        max_length=200,
        description="What a task board should call this, in a few words. Optional: without it a name is derived from the description, which reads as prose rather than as a name.",
    )
    description: str = Field(description="One concrete unit of work, not 'build the whole thing'.")
    requirements: List[str] = Field(
        description="Keys of the requirements this task satisfies. At least one: a task tracing to nothing is work nobody asked for."
    )


class Algorithm(_Part):
    name: str = Field(description="What this procedure is called.")
    steps: List[str] = Field(
        description="Ordered steps. Conditional or multi-step behaviour belongs here rather than in a paragraph, where the order is guessed at."
    )


class Scope(_Part):
    in_scope: List[str] = Field(default_factory=list, description="What this document covers.")
    non_goals: List[str] = Field(
        default_factory=list,
        description="What it deliberately does not cover. A non-goal prevents more rework than a goal creates, and omission is not a non-goal — it is silence.",
    )


class Evidence(_Part):
    checked: List[str] = Field(
        default_factory=list,
        description="Tests, contracts, fixtures, migrations and configuration inspected, and what each helps validate.",
    )
    limits: List[str] = Field(
        default_factory=list,
        description="Behaviour that is untested, inferred, or contradictory. A green suite says the code satisfies the tests that exist — not that the tests correspond to the requirements.",
    )


class OpenQuestion(_Part):
    question: str = Field(description="Something genuinely undecided.")
    resolved: bool = Field(
        default=False,
        description="Whether it has been answered. An unresolved question blocks the document from being proposed — a guess written in the voice of a requirement is indistinguishable from a decision.",
    )


class SpecPayload(_Part):
    """What `submit_spec_document` accepts."""

    schema_version: int = Field(
        description=f"The payload contract version. Currently {SCHEMA_VERSION}."
    )
    kind: str = Field(description="One of: baseline, system-map, roadmap, change-spec, capability.")
    title: str = Field(description="The document's title.")
    summary: str = Field(default="", description="One paragraph: what this changes and why.")
    problem: str = Field(default="", description="What hurts today, who it affects, and why now.")
    scope: Scope = Field(default_factory=Scope)
    requirements: List[Requirement] = Field(default_factory=list)
    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    tasks: List[Task] = Field(default_factory=list)
    algorithms: List[Algorithm] = Field(default_factory=list)
    design: str = Field(
        default="",
        description="How it will be built, and the decisions with their reasoning. Requirements stay free of this so they survive an implementation change.",
    )
    evidence: Evidence = Field(default_factory=Evidence)
    lifecycle: str = Field(
        default="",
        description="Whether this updates a living document, records a one-off change, or needs a stated reconciliation after implementation.",
    )
    open_questions: List[OpenQuestion] = Field(default_factory=list)


def _field_path(location: tuple) -> str:
    parts: List[str] = []
    for item in location:
        parts.append(f"[{item}]" if isinstance(item, int) else (f".{item}" if parts else str(item)))
    return "".join(parts)


def _duplicate(values: List[str]) -> Optional[str]:
    seen = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def validate_payload(raw: Any) -> SpecPayload:
    """Parse and check a submitted payload, or raise `PayloadError` naming the field.

    Checks shape and referential integrity only. Whether the document is
    *finished* is the transition's question, not this one.
    """
    if not isinstance(raw, dict):
        raise PayloadError("payload must be an object", field="")

    # Stated before anything else, and by name. A missing version reported as a
    # downstream type error sends the author to fix the wrong thing.
    if "schema_version" not in raw:
        raise PayloadError(
            f"payload must declare schema_version (this Hub speaks {SCHEMA_VERSION})",
            field="schema_version",
        )
    if raw["schema_version"] != SCHEMA_VERSION:
        raise PayloadError(
            f"unsupported schema_version {raw['schema_version']!r}; this Hub speaks {SCHEMA_VERSION}",
            field="schema_version",
        )

    try:
        payload = SpecPayload.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise PayloadError(first["msg"], field=_field_path(first["loc"])) from exc

    if payload.kind not in KINDS:
        raise PayloadError(f"kind must be one of {', '.join(KINDS)}", field="kind")
    if not payload.title.strip():
        raise PayloadError("title must not be empty", field="title")

    for index, requirement in enumerate(payload.requirements):
        where = f"requirements[{index}]"
        if not KEY_RE.match(requirement.key):
            raise PayloadError(
                "key must be lowercase letters, digits and hyphens, up to 64 characters",
                field=f"{where}.key",
            )
        if requirement.modal not in MODALS:
            raise PayloadError(f"modal must be one of {', '.join(MODALS)}", field=f"{where}.modal")
        if requirement.party is not None and requirement.party not in ("producer", "consumer"):
            raise PayloadError("party must be 'producer' or 'consumer'", field=f"{where}.party")

    requirement_keys = [r.key for r in payload.requirements]
    duplicate = _duplicate(requirement_keys)
    if duplicate is not None:
        raise PayloadError(f"duplicate requirement key {duplicate!r}", field="requirements")
    known = set(requirement_keys)

    # A reference to a requirement that is not in the document is malformed, not
    # merely incomplete — nothing later can resolve it.
    for index, criterion in enumerate(payload.acceptance_criteria):
        if criterion.requirement not in known:
            raise PayloadError(
                f"names requirement {criterion.requirement!r}, which this document does not define",
                field=f"acceptance_criteria[{index}].requirement",
            )

    for index, task in enumerate(payload.tasks):
        for position, key in enumerate(task.requirements):
            if key not in known:
                raise PayloadError(
                    f"names requirement {key!r}, which this document does not define",
                    field=f"tasks[{index}].requirements[{position}]",
                )

    for collection, label in (
        (payload.acceptance_criteria, "acceptance_criteria"),
        (payload.tasks, "tasks"),
    ):
        duplicate = _duplicate([item.key for item in collection])
        if duplicate is not None:
            raise PayloadError(f"duplicate key {duplicate!r}", field=label)

    return payload


def payload_to_dict(payload: SpecPayload) -> Dict[str, Any]:
    """The payload as stored — including fields this version does not define."""
    return payload.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

PAYLOAD_ELEMENT_ID = "aw-spec-payload"
PAYLOAD_MIME = "application/agentweave-spec+json"

_PAYLOAD_BLOCK_RE = re.compile(
    r'<script[^>]*id="' + PAYLOAD_ELEMENT_ID + r'"[^>]*>(.*?)</script>',
    re.DOTALL,
)


def embed_payload(data: Dict[str, Any]) -> str:
    """The payload as a script block for the rendered document.

    Carried inside the document rather than in a sidecar file so that the
    document stays self-contained and the two cannot drift apart. The type is
    not a script type any browser executes, and `<` is escaped so no content can
    close the element early.
    """
    encoded = json.dumps(data, indent=2, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="{PAYLOAD_MIME}" id="{PAYLOAD_ELEMENT_ID}">\n{encoded}\n</script>'


def has_payload_block(document: str) -> bool:
    """Whether a payload block is present at all, however well or badly it parses.

    `extract_payload` returns None for two different situations — no block, or a
    block that is not readable JSON — and a caller that must tell the operator
    *which* cannot recover that from the None. This answers only the first half,
    so `extract_payload` stays the single interpretation of the block's contents.
    """
    return _PAYLOAD_BLOCK_RE.search(document) is not None


def extract_payload(document: str) -> Optional[Dict[str, Any]]:
    """The payload a rendered document carries, or None if it has none.

    A document without one was not produced by this Hub — hand-written, or
    written by a version that predates the payload block. The caller decides
    what that means; this function does not guess.
    """
    match = _PAYLOAD_BLOCK_RE.search(document)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(1).replace("\\u003c", "<"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
