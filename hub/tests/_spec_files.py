"""Building stored specification files in tests, the way the Hub writes them.

A document is stored as `spec.json`: its payload plus the Hub block (`spec_documents.serialize`).
Tests that used to put a rendered page with an embedded payload on disk build the file here
instead, so a fixture never holds a shape the Hub does not write.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from hub.spec_documents import serialize


def stored_text(
    payload: Dict[str, Any],
    *,
    phase: Optional[str] = "exploring",
    rigor: str = "sketch",
    step: Optional[str] = None,
    size: Optional[str] = None,
) -> str:
    """The text of a stored file holding `payload`, with a hub block naming `phase`.

    `phase=None` writes a file with no hub block at all (a file that arrived from elsewhere).
    """
    if phase is None:
        return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    return serialize(payload, {"phase": phase, "rigor": rigor, "step": step, "size": size})
