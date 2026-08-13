"""Where a specification document's path comes from.

Two jobs, and the reason they live together is that they are the same job at two
moments. When a document is created nobody knows what it is about — the exploring
phase exists precisely because the subject is not yet established — so it gets a
name that obviously means nothing. When the interview settles what it is, the
agent supplies a subject in prose and the Hub derives a real path from it.

The placeholder is random on purpose. Anything reproducible from the title, the
conversation or a counter would be treated as identity inside a week, and
identity is `SpecDocument.id`.

The slug rule is a port of `hub/ui/src/lib/specDocumentName.ts`, which used to be
the only implementation and ran in the browser. It is here because the rename
arrives over MCP and never touches a browser, and two slug implementations in two
languages drift.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from typing import Callable, Optional

from .spec_manifest import SPEC_PATH_MAX_LENGTH, validate_spec_path

#: Where explorations live. Matches `EXPLORATION_ROOT` in the UI.
EXPLORATION_ROOT = "spec/changes"
DOCUMENT_FILENAME = "spec.html"

#: How many distinct placeholders to try before falling back to a suffix. The
#: bound is not an optimisation: a namespace that has filled up must produce an
#: answer or a refusal, never an unbounded search.
_MINT_ATTEMPTS = 24


class NamingExhaustedError(RuntimeError):
    """Every candidate placeholder was taken, including the suffixed ones."""


#: Lowercase ASCII single words, no hyphens, so a minted path satisfies the path
#: contract by construction rather than by being validated and rejected.
COLOURS = (
    "amber",
    "azure",
    "cobalt",
    "coral",
    "crimson",
    "emerald",
    "golden",
    "indigo",
    "ivory",
    "jade",
    "lilac",
    "magenta",
    "maroon",
    "olive",
    "onyx",
    "opal",
    "russet",
    "saffron",
    "sapphire",
    "scarlet",
    "silver",
    "teal",
    "umber",
    "violet",
)

MYTHIC_ANIMALS = (
    "basilisk",
    "chimera",
    "dragon",
    "fenrir",
    "garuda",
    "griffin",
    "hydra",
    "kelpie",
    "kirin",
    "kraken",
    "leviathan",
    "manticore",
    "minotaur",
    "pegasus",
    "phoenix",
    "roc",
    "salamander",
    "selkie",
    "sphinx",
    "sylph",
    "thunderbird",
    "unicorn",
    "wyvern",
    "yeti",
)

_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TRAILING_HYPHENS_RE = re.compile(r"-+$")

#: The longest slug that still fits inside the path contract, derived from the
#: contract rather than chosen. The UI's old bound of 64 was measured against
#: neither the prefix nor the suffix.
MAX_SLUG_LENGTH = SPEC_PATH_MAX_LENGTH - len(f"{EXPLORATION_ROOT}/") - len(f"/{DOCUMENT_FILENAME}")


def slugify(subject: str) -> str:
    """A path segment derived from prose, or ``""`` when there is nothing usable.

    Not every string contains a name. `"???"` slugifies to nothing, and the
    caller is expected to refuse rather than substitute something.
    """
    if not isinstance(subject, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", subject)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    slug = _NON_SLUG_RE.sub("-", folded.lower()).strip("-")
    if len(slug) > MAX_SLUG_LENGTH:
        slug = slug[:MAX_SLUG_LENGTH]
    return _TRAILING_HYPHENS_RE.sub("", slug)


def path_for_slug(slug: str) -> str:
    """The document path a slug occupies."""
    return f"{EXPLORATION_ROOT}/{slug}/{DOCUMENT_FILENAME}"


def document_path_for(subject: str) -> Optional[str]:
    """The path a subject names, or ``None`` when the subject yields no slug."""
    slug = slugify(subject)
    if not slug:
        return None
    return validate_spec_path(path_for_slug(slug))


def _placeholder_slug() -> str:
    return f"{secrets.choice(COLOURS)}-{secrets.choice(MYTHIC_ANIMALS)}"


def mint_placeholder_path(is_taken: Callable[[str], bool]) -> str:
    """A free path whose name says nothing about the document.

    `is_taken` is asked about a whole path and must account for both the
    documents a project has recorded and the files already on disk — a name is
    only free if nothing at all occupies it.

    Exhausting the attempts appends a short random suffix rather than searching
    on, and that fallback is bounded too. A caller that cannot be given a free
    name is told so — an unbounded search against a full namespace does not
    return, and hanging is worse than refusing.
    """
    for _ in range(_MINT_ATTEMPTS):
        candidate = path_for_slug(_placeholder_slug())
        if not is_taken(candidate):
            return validate_spec_path(candidate)
    for _ in range(_MINT_ATTEMPTS):
        candidate = path_for_slug(f"{_placeholder_slug()}-{secrets.token_hex(3)}")
        if not is_taken(candidate):
            return validate_spec_path(candidate)
    raise NamingExhaustedError(
        "could not mint a free document name; the exploration root is unusually full"
    )
