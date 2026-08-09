"""Model catalog response schemas — served read-only, no request body."""

from typing import List, Optional

from pydantic import BaseModel

from ..model_catalog import ProviderDescriptor


class WindowVariantResponse(BaseModel):
    id: str
    label: str
    context_window: Optional[int]
    default: bool


class ModelDescriptorResponse(BaseModel):
    id: str
    label: str
    aliases: List[str]
    context_window: Optional[int]
    default: bool
    # Empty for every model that offers one window, which is most of them. The interface renders a
    # window control only where there is more than one, because a control offering one choice is
    # not a choice.
    windows: List[WindowVariantResponse] = []


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


class ProviderDescriptorResponse(BaseModel):
    provider: str
    label: str
    models: List[ModelDescriptorResponse]
    controls: List[ControlDescriptorResponse]

    @classmethod
    def from_descriptor(cls, descriptor: ProviderDescriptor) -> "ProviderDescriptorResponse":
        return cls(
            provider=descriptor.provider,
            label=descriptor.label,
            models=[
                ModelDescriptorResponse(
                    id=m.id,
                    label=m.label,
                    aliases=list(m.aliases),
                    context_window=m.context_window,
                    default=m.default,
                    windows=[
                        WindowVariantResponse(
                            id=w.id,
                            label=w.label,
                            context_window=w.context_window,
                            default=w.default,
                        )
                        for w in m.windows
                    ],
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
