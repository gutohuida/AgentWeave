"""Model catalog response schemas — served read-only, no request body."""

from typing import List, Optional

from pydantic import BaseModel

from ..model_catalog import CatalogSource, ProviderDescriptor


class ModelDescriptorResponse(BaseModel):
    id: str
    label: str
    aliases: List[str]
    context_window: Optional[int]
    default: bool


class ControlValueResponse(BaseModel):
    id: str
    label: str


class ApplySpecResponse(BaseModel):
    style: str
    template: str


class ControlDescriptorResponse(BaseModel):
    id: str
    label: str
    kind: str
    values: List[ControlValueResponse]
    default: Optional[str]
    apply: ApplySpecResponse


class CatalogSourceResponse(BaseModel):
    kind: str  # "cli_cache" | "built_in"
    fetched_at: Optional[str] = None
    client_version: Optional[str] = None
    reason: Optional[str] = None

    @classmethod
    def from_source(cls, source: CatalogSource) -> "CatalogSourceResponse":
        return cls(
            kind=source.kind,
            fetched_at=source.fetched_at,
            client_version=source.client_version,
            reason=source.reason,
        )


#: A provider whose models are declared literals, never a runtime cache — Claude, and any future
#: provider that does not publish its own catalog (design D2: "Claude is always built_in with no
#: reason").
_BUILT_IN_SOURCE = CatalogSourceResponse(kind="built_in")


class ProviderDescriptorResponse(BaseModel):
    provider: str
    label: str
    models: List[ModelDescriptorResponse]
    controls: List[ControlDescriptorResponse]
    source: CatalogSourceResponse

    @classmethod
    def from_descriptor(
        cls, descriptor: ProviderDescriptor, source: Optional[CatalogSource] = None
    ) -> "ProviderDescriptorResponse":
        return cls(
            provider=descriptor.provider,
            label=descriptor.label,
            source=(
                CatalogSourceResponse.from_source(source)
                if source is not None
                else _BUILT_IN_SOURCE
            ),
            models=[
                ModelDescriptorResponse(
                    id=m.id,
                    label=m.label,
                    aliases=list(m.aliases),
                    context_window=m.context_window,
                    default=m.default,
                )
                for m in descriptor.models
            ],
            controls=[
                ControlDescriptorResponse(
                    id=c.id,
                    label=c.label,
                    kind=c.kind,
                    values=[ControlValueResponse(id=v.id, label=v.label) for v in c.values],
                    default=c.default,
                    apply=ApplySpecResponse(style=c.apply.style, template=c.apply.template),
                )
                for c in descriptor.controls
            ],
        )


class ModelCatalogResponse(BaseModel):
    providers: List[ProviderDescriptorResponse]
