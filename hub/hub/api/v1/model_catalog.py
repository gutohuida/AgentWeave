"""GET /api/v1/model-catalog — the provider/model/control descriptors, read-only.

Not project-scoped (see model_catalog.py's module docstring and design.md): the catalog is
static and identical for every project, so this only requires operator authentication, the same
as the project-listing endpoint.
"""

from fastapi import APIRouter, Depends

from ...auth import get_operator
from ...db.models import OperatorCredential
from ...model_catalog import codex_catalog_source, providers
from ...schemas.model_catalog import ModelCatalogResponse, ProviderDescriptorResponse

router = APIRouter(tags=["model-catalog"])


@router.get("/model-catalog", response_model=ModelCatalogResponse)
async def get_model_catalog(
    operator: OperatorCredential = Depends(get_operator),
):
    del operator
    return ModelCatalogResponse(
        providers=[
            ProviderDescriptorResponse.from_descriptor(
                p, source=codex_catalog_source() if p.provider == "codex" else None
            )
            for p in providers()
        ]
    )
