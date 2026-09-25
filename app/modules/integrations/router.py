from fastapi import APIRouter, Depends

from app.core.auth import get_current_principal
from app.modules.integrations.registry import capabilities

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/capabilities")
def list_capabilities(_=Depends(get_current_principal)):
    return {"items": [c.__dict__ for c in capabilities()]}
