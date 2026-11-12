"""A Hub started inside an agent's run drops that run's variables (F1160).

`trigger_agent` gives every run its identity, its credential and its Hub's address in the run's
environment. A Hub started from that run's shell -- an agent testing the product does exactly this
-- inherited all of it, and passed it on: `trigger_agent` builds each run's environment from the
Hub's own, and prefers an explicit `HUB_URL` over the address it observed. Driven 2026-11-11: a
scratch Hub on :8030 started inside an :8000 run launched a Codex agent whose `aw-tool` calls went
to :8000 and were refused as an invalid run credential.

None of these names is configuration a Hub is ever given on purpose, except `HUB_URL`, the
documented override for a Hub reached at another address (Docker, a reverse proxy). That one is
dropped only when it arrived with a run's credential, which says whose address it is.
"""

from __future__ import annotations

import logging
import os
from typing import List, MutableMapping, Optional

logger = logging.getLogger(__name__)

#: What `trigger_agent` writes into a run's environment (`hub/hub/api/v1/agent_trigger.py`), less
#: `HUB_URL`, which is handled on its own below.
RUN_ENVIRONMENT_NAMES = (
    "AW_RUN_TOKEN",
    "AW_RUN_ID",
    "AW_AGENT_IDENTITY",
    "AW_WORKSPACE_DIR",
    "AW_REACH_GRANTS",
    "AW_PERMISSION_POSTURE",
    "AW_DECISION_TIMEOUT",
    "AW_QUESTION_TIMEOUT",
    "AW_TURN_DEPTH",
    "AW_CAN_ADMIN_SPECS",
)


def drop_inherited_run_environment(
    environ: Optional[MutableMapping[str, str]] = None,
) -> List[str]:
    """Remove a parent run's variables from *environ* (the process's own by default), and return
    the names removed. Called first in `lifespan()`, before the startup re-drain can start a run."""
    target = os.environ if environ is None else environ
    inside_a_run = bool(target.get("AW_RUN_TOKEN"))
    removed = [name for name in RUN_ENVIRONMENT_NAMES if target.pop(name, None) is not None]
    if inside_a_run and target.pop("HUB_URL", None) is not None:
        removed.append("HUB_URL")
    if removed:
        logger.warning(
            "This Hub was started inside an agent's run; dropped the run's variables it "
            "inherited, so its own runs are never handed them: %s",
            ", ".join(removed),
        )
    return removed
