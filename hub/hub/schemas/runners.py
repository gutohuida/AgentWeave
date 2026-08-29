"""Runner schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..db.models import RUNNER_CLIS
from ..model_catalog import get_provider
from .common import RequestModel


class RunnerCreate(RequestModel):
    name: str = Field(max_length=256)
    cli: str = Field(max_length=16)
    model: Optional[str] = Field(default=None, max_length=256)
    flags: Optional[List[str]] = None

    @field_validator("cli")
    @classmethod
    def validate_cli(cls, v: str) -> str:
        if v not in RUNNER_CLIS:
            raise ValueError(f"cli must be one of {RUNNER_CLIS}")
        return v


class RunnerUpdate(RequestModel):
    name: Optional[str] = Field(default=None, max_length=256)
    model: Optional[str] = Field(default=None, max_length=256)
    flags: Optional[List[str]] = None


class RunnerResponse(BaseModel):
    id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    name: str = Field(max_length=256)
    cli: str = Field(max_length=16)
    model: Optional[str] = None
    flags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
    # True when `model` is set but the catalog does not declare it for `cli` — a runner
    # created before this catalog existed, or naming a model a newer CLI release added.
    # Existing runners stay fully readable and usable; this only flags it for the
    # operator when editing (runner-registry spec: "Existing runners keep working").
    model_unrecognised: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _flag_unrecognised_model(self) -> "RunnerResponse":
        if self.model is None:
            return self
        provider_entry = get_provider(self.cli)
        recognised = provider_entry is not None and provider_entry.model(self.model) is not None
        if not recognised:
            self.model_unrecognised = True
        return self
