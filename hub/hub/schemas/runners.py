"""Runner schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..db.models import RUNNER_CLIS
from ..model_catalog import get_provider
from ..runner_provider import is_provider_model
from .common import RequestModel, VisibleName


class RunnerCreate(RequestModel):
    name: VisibleName
    cli: str = Field(max_length=16)
    model: Optional[str] = Field(default=None, max_length=256)
    flags: Optional[List[str]] = None
    # `{type, base_url, api_key_var}` for a Copilot runner on a model provider (design D7). Typed
    # `Any` on purpose: the route checks it and answers 400 with a sentence that never repeats a
    # value, where a schema check would answer 422 with a pasted key in `detail[].input`.
    provider_config: Optional[Any] = None

    @field_validator("cli")
    @classmethod
    def validate_cli(cls, v: str) -> str:
        if v not in RUNNER_CLIS:
            raise ValueError(f"cli must be one of {RUNNER_CLIS}")
        return v


class RunnerUpdate(RequestModel):
    name: Optional[VisibleName] = None
    model: Optional[str] = Field(default=None, max_length=256)
    flags: Optional[List[str]] = None
    # As on create. Absent and explicit `null` differ, as for `model`: `null` removes the provider.
    provider_config: Optional[Any] = None


class ProviderConfig(BaseModel):
    """A stored provider: the address and the *name* of the variable holding its key."""

    type: str
    base_url: str
    api_key_var: str


class RunnerResponse(BaseModel):
    id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    name: str = Field(max_length=256)
    cli: str = Field(max_length=16)
    model: Optional[str] = None
    flags: Optional[List[str]] = None
    provider_config: Optional[ProviderConfig] = None
    created_at: datetime
    updated_at: datetime
    # True when `model` is set but the catalog does not declare it for `cli` — a runner
    # created before this catalog existed, or naming a model a newer CLI release added.
    # Existing runners stay fully readable and usable; this only flags it for the
    # operator when editing (runner-registry spec: "Existing runners keep working").
    model_unrecognised: bool = False

    model_config = {"from_attributes": True}

    @field_validator("provider_config", mode="before")
    @classmethod
    def _read_stored_provider(cls, value: Any) -> Optional[Dict[str, Any]]:
        # A damaged row must not 500 the whole runner list; it reads as no provider here, and
        # launchability reports the runner unlaunchable (design D7).
        if not isinstance(value, dict):
            return None
        if not all(isinstance(value.get(k), str) for k in ProviderConfig.model_fields):
            return None
        return {k: value[k] for k in ProviderConfig.model_fields}

    @model_validator(mode="after")
    def _flag_unrecognised_model(self) -> "RunnerResponse":
        if self.provider_config is not None:
            # A provider runner's model comes from the Claude API ids, not its CLI's catalog.
            self.model_unrecognised = not is_provider_model(self.model)
            return self
        if self.model is None:
            return self
        provider_entry = get_provider(self.cli)
        recognised = provider_entry is not None and provider_entry.model(self.model) is not None
        if not recognised:
            self.model_unrecognised = True
        return self
