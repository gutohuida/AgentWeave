"""Least-privilege application API exposed to authenticated agent runs.

Capability routers are added here phase-by-phase. Keeping a distinct namespace makes it
impossible to accidentally apply the project-key dependency to an agent operation.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/agent-actions", tags=["agent-actions"])

