from typing import Optional

from pydantic import BaseModel


class DialogAvailabilityResponse(BaseModel):
    available: bool
    reason: Optional[str] = None


class DialogOpenResponse(BaseModel):
    outcome: str
    path: Optional[str] = None
    detail: Optional[str] = None
