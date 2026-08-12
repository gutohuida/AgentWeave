"""Minting stable requirement identifiers.

The agent supplies a `key` — a handle scoped to one document. The Hub supplies
the identifier, and the identifier is what tasks, evidence and gates point at.
Keeping those separate is the whole point: an agent that invented identifiers
would reintroduce the drift they exist to remove, while correlating by position
would renumber every requirement below an insertion and silently re-target every
link into it.

The high-water mark is persisted rather than derived from the current document,
because an identifier must not be reused **after its requirement is removed**.
Deriving the next number from `max(current)` would hand `FR-4` to a new
requirement the moment the old `FR-4` was deleted, and every historical
reference to it would then point at something else.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Hub-owned block inside the stored payload. Written on every save and never
# read from a submission — an agent that supplies one is ignored, which is what
# "the Hub mints identifiers" means in practice.
IDENTITY_FIELD = "aw_identity"

IDENTIFIER_PREFIX = "FR-"
_IDENTIFIER_RE = re.compile(r"^FR-(\d+)$")


def read_identity(stored: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], int]:
    """The key→identifier map and high-water mark carried by a stored payload."""
    if not isinstance(stored, dict):
        return {}, 0
    block = stored.get(IDENTITY_FIELD)
    if not isinstance(block, dict):
        return {}, 0

    raw_map = block.get("requirements")
    mapping: Dict[str, str] = {}
    if isinstance(raw_map, dict):
        for key, identifier in raw_map.items():
            if isinstance(key, str) and isinstance(identifier, str):
                mapping[key] = identifier

    high_water = block.get("high_water")
    if not isinstance(high_water, int) or high_water < 0:
        high_water = 0

    # A high-water mark below an identifier already in use would mint a
    # duplicate on the next save. Trust the larger of the two.
    for identifier in mapping.values():
        match = _IDENTIFIER_RE.match(identifier)
        if match:
            high_water = max(high_water, int(match.group(1)))

    return mapping, high_water


def mint(
    keys: List[str],
    previous: Optional[Dict[str, str]] = None,
    high_water: int = 0,
) -> Tuple[Dict[str, str], int]:
    """Identifiers for `keys`, preserving any a key already holds.

    Order of `keys` does not affect what an existing key receives — that is the
    property that makes inserting a requirement safe.
    """
    previous = previous or {}
    mapping: Dict[str, str] = {}
    mark = high_water

    for key in keys:
        existing = previous.get(key)
        if existing is not None:
            mapping[key] = existing
            continue
        mark += 1
        mapping[key] = f"{IDENTIFIER_PREFIX}{mark}"

    return mapping, mark


def retained(previous: Dict[str, str], current_keys: List[str]) -> Dict[str, str]:
    """Identifiers whose keys are gone from the document.

    Kept so the high-water mark is not the only thing standing between a removed
    identifier and its reuse, and so a later change can offer "was this a
    rename?" instead of guessing at one now.
    """
    live = set(current_keys)
    return {key: value for key, value in previous.items() if key not in live}


def identity_block(
    mapping: Dict[str, str], high_water: int, retired: Dict[str, str]
) -> Dict[str, Any]:
    return {
        "requirements": dict(mapping),
        "high_water": high_water,
        "retired": dict(retired),
    }
