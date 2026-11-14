from typing import Dict, List, Optional

from pydantic import BaseModel


class WorkspaceFileResponse(BaseModel):
    path: str
    binary: bool
    size: int
    content: Optional[str]


class WorkspaceListing(BaseModel):
    """The Files tab's answer for a conversation: which location, and why it is not the checkout."""

    #: The location `paths` belongs to: "worktree" (the agent's checkout) or "root".
    location: str
    #: "ok", or "no_checkout" when the agent has none (read-only, or not created yet).
    state: str = "ok"
    #: Plain words for `no_checkout`; never an error code.
    message: Optional[str] = None
    #: Whether the agent has a checkout to switch to.
    has_checkout: bool = False
    branch: Optional[str] = None
    paths: List[str] = []
    #: Path -> A, M, D (R) for what the branch changed since main; only for the checkout.
    changed: Dict[str, str] = {}
