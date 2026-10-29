"""The evidence rules a task's approval is judged by, and the digest of what governed a decision.

Document rigor retired (`amendments-main-watch-and-the-next-slice`, D3): no route, tool or control
sets or shows a document's rigor any more, and the `rigor` column, `spec_rigor_events` and
`spec_edit_proposals` stay in the database, unread. The three names below survive as the evidence
*rules* a build's level implies (`builds.rigor_for_level`): `sketch` is silent, `contract` reports
what is missing and never refuses, `gate` refuses until evidence is accepted. A task with no level
is judged by `sketch`'s rule (`requirement_gate._enforced_requirements`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List

from .spec_lifecycle import digest

SKETCH = "sketch"
CONTRACT = "contract"
GATE = "gate"


@dataclass(frozen=True)
class PolicySnapshot:
    """What governed one decision, reduced to something comparable later."""

    entries: List[Dict[str, Any]]

    @property
    def digest(self) -> str:
        return digest(json.dumps(sorted_entries(self.entries), sort_keys=True))


def sorted_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(entries, key=lambda entry: (entry.get("identifier", ""), entry.get("state", "")))


def policy_digest(entries: List[Dict[str, Any]]) -> str:
    """A stable digest of the evidence rules and coverage that governed a transition."""
    return hashlib.sha256(
        json.dumps(sorted_entries(entries), sort_keys=True).encode("utf-8")
    ).hexdigest()
