from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.public_api.auth import PublicPrincipal, get_public_principal
from app.modules.public_api.schemas import v1

router = APIRouter(tags=["me"])


@router.get("/me", response_model=v1.Me, summary="Hvem er jeg – nøglens arbejdsrum og scopes")
def me(principal: PublicPrincipal = Depends(get_public_principal)) -> v1.Me:
    k, w = principal.key, principal.workspace
    return v1.Me(workspace=v1.MeWorkspace(id=w.id, name=w.name, kind=w.kind),
                 key=v1.MeKey(id=k.id, name=k.name, prefix=k.prefix, last4=k.last4, created_at=k.created_at,
                              expires_at=k.expires_at, last_used_at=k.last_used_at),
                 scopes=sorted(principal.scopes))
