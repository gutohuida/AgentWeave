"""The semantic digest of a requirement — the thing evidence is pinned against.

There is exactly one definition here, and both consumers call it: the document
row's `requirement_digests` and the requirement index. Two definitions would
disagree eventually, and the disagreement would be invisible — one surface
calling evidence stale while another calls the same evidence current.

**What is in the digest is what invalidates evidence.** Getting that boundary
wrong fails in two directions, and they are not symmetrical:

- *Too little* — a requirement's obligation moves from MUST to MAY, the digest
  does not change, and evidence accepted against the old obligation keeps
  reporting the requirement as verified. Silent, and wrong in the direction that
  says work is done when it is not.
- *Too much* — a rationale is reworded and every piece of evidence for that
  requirement goes stale. Noisy, visible, and recoverable by re-accepting.

So the line is drawn at **what a reader must satisfy**: the obligation, the
statement, the side of the boundary it binds, and the criteria that demonstrate
it. Explanatory prose is excluded — a rationale exists to make a rule survive an
edge case, not to state one.

The canonicalization version is stored with every indexed requirement. A later
change to this function is then a fact about a row rather than a silent
reinterpretation of every pin taken before it.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Dict, List, Optional

from .spec_payload import AcceptanceCriterion, Requirement, SpecPayload

# Bumped whenever the inputs to `semantic_digest` or their canonicalization
# change. Rows carry it so a digest taken under an older rule is recognisable as
# such instead of reading as a rewording.
CANONICALIZATION_VERSION = 1

# A separator no normalized field can contain: normalization collapses every
# whitespace run to a single space and control characters do not survive it.
_SEP = "\x1f"

_WHITESPACE = re.compile(r"\s+")


def normalize(text: Optional[str]) -> str:
    """Text reduced to what it says, not how it was typed.

    Unicode form, line endings and whitespace runs are presentation. A document
    round-tripped through a different editor must not read as a reworded
    requirement.
    """
    if not text:
        return ""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def _criterion_parts(criterion: AcceptanceCriterion) -> str:
    return _SEP.join(
        (normalize(criterion.given), normalize(criterion.when), normalize(criterion.then))
    )


def semantic_digest(
    requirement: Requirement,
    criteria: Optional[List[AcceptanceCriterion]] = None,
) -> str:
    """The digest of one requirement and the criteria that demonstrate it.

    Criteria are sorted by their canonical text rather than taken in document
    order: reordering two criteria changes nothing about what the requirement
    demands, and a digest that moved would report a rewording that did not
    happen.

    Algorithm clauses are named by the technical design as a fourth input and are
    **not** included, because the payload has no way to say which requirement an
    algorithm belongs to (`Algorithm` carries a name and steps, nothing else).
    Guessing at ownership would pin evidence to text the author never tied to
    that requirement. When that link exists, this function changes and
    `CANONICALIZATION_VERSION` is bumped.
    """
    parts = [
        f"v{CANONICALIZATION_VERSION}",
        normalize(requirement.modal),
        normalize(requirement.statement),
        # The side of a boundary a rule binds is part of the rule: the same
        # sentence read as producer and as consumer demands different work, and
        # `spec_payload` keeps them apart for exactly that reason.
        normalize(requirement.party),
    ]
    parts.extend(sorted(_criterion_parts(criterion) for criterion in (criteria or [])))
    return hashlib.sha256(_SEP.join(parts).encode("utf-8")).hexdigest()


def payload_digests(payload: SpecPayload, identifiers: Dict[str, str]) -> Dict[str, str]:
    """Every requirement's digest, keyed by minted identifier.

    A requirement whose key holds no identifier is skipped rather than keyed by
    something else — an identifier is minted for every key on save, so its
    absence means the caller passed a stale map, and inventing a key here would
    hide that.
    """
    by_requirement: Dict[str, List[AcceptanceCriterion]] = {}
    for criterion in payload.acceptance_criteria:
        by_requirement.setdefault(criterion.requirement, []).append(criterion)

    return {
        identifiers[requirement.key]: semantic_digest(
            requirement, by_requirement.get(requirement.key, [])
        )
        for requirement in payload.requirements
        if requirement.key in identifiers
    }
