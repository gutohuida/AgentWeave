from typing import Optional

from pydantic import BaseModel


class WorkspaceFileResponse(BaseModel):
    path: str
    binary: bool
    size: int
    content: Optional[str]
