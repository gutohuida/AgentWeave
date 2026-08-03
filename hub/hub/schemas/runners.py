"""Runner schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from ..db.models import RUNNER_CLIS


class RunnerCreate(BaseModel):
    name: str = Field(max_length=256)
    cli: str = Field(max_length=16)
    model: Optional[str] = Field(default=None, max_length=256)
    flags: Optional[List[str]] = None

    model_config = {"extra": "forbid"}

    @field_validator("cli")
    @classmethod
    def validate_cli(cls, v: str) -> str:
        if v not in RUNNER_CLIS:
            raise ValueError(f"cli must be one of {RUNNER_CLIS}")
        return v


class RunnerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=256)
    model: Optional[str] = Field(default=None, max_length=256)
    flags: Optional[List[str]] = None

    model_config = {"extra": "forbid"}


class RunnerResponse(BaseModel):
    id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    name: str = Field(max_length=256)
    cli: str = Field(max_length=16)
    model: Optional[str] = None
    flags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
