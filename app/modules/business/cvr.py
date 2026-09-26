"""Look up a company in the Danish CVR register (Erhvervsstyrelsen's system-to-system Elasticsearch).

Only fields whose paths are documented in public client code are read: name, address, main industry and
status. Credentials are free but must be requested from Erhvervsstyrelsen (cvrselvbetjening@erst.dk);
without them the lookup answers 501. NOT externally verified from this repository.
"""
from __future__ import annotations

from app.config import get_settings
from app.core.errors import ApiError, NotFound, NotImplementedYet, ValidationFailed
from app.modules.knowledge.importer import cvr_valid

SOURCE = [
    "Vrvirksomhed.cvrNummer",
    "Vrvirksomhed.virksomhedMetadata.nyesteNavn",
    "Vrvirksomhed.virksomhedMetadata.nyesteBeliggenhedsadresse",
    "Vrvirksomhed.virksomhedMetadata.nyesteHovedbranche",
    "Vrvirksomhed.virksomhedMetadata.sammensatStatus",
]


def configured() -> bool:
    s = get_settings()
    return bool(s.cvr_username and s.cvr_password)


def _address(a: dict) -> str:
    street = " ".join(str(x) for x in (a.get("vejnavn"), a.get("husnummerFra")) if x)
    letter = a.get("bogstavFra") or ""
    return f"{street}{letter}".strip()


def parse(hit: dict) -> dict:
    v = (hit.get("_source") or {}).get("Vrvirksomhed") or {}
    meta = v.get("virksomhedMetadata") or {}
    addr = meta.get("nyesteBeliggenhedsadresse") or {}
    branch = meta.get("nyesteHovedbranche") or {}
    return {
        "cvr": str(v.get("cvrNummer") or ""),
        "legal_name": (meta.get("nyesteNavn") or {}).get("navn") or "",
        "address_line": _address(addr) or None,
        "postal_code": str(addr["postnummer"]) if addr.get("postnummer") else None,
        "city": addr.get("postdistrikt") or None,
        "industry": branch.get("branchetekst") or None,
        "status": meta.get("sammensatStatus") or None,
    }


def lookup(cvr: str) -> dict:
    import httpx

    cvr = "".join(ch for ch in cvr if ch.isdigit())
    if not cvr_valid(cvr):
        raise ValidationFailed("Ugyldigt CVR-nummer (8 cifre med gyldigt kontrolciffer)", field_errors=[{"field": "cvr"}])
    if not configured():
        raise NotImplementedYet("CVR-opslag kræver adgang til CVR-registret (CVR_USERNAME/CVR_PASSWORD)",
                                code="cvr_not_configured")
    s = get_settings()
    body = {"_source": SOURCE, "query": {"term": {"Vrvirksomhed.cvrNummer": int(cvr)}}, "size": 1}
    try:
        r = httpx.post(s.cvr_url, json=body, auth=(s.cvr_username, s.cvr_password), timeout=15.0)
    except httpx.HTTPError as e:
        raise ApiError("CVR-registret svarede ikke", code="cvr_unavailable", status_code=502) from e
    if r.status_code >= 400:
        raise ApiError(f"CVR-registret afviste opslaget ({r.status_code})", code="cvr_unavailable", status_code=502)
    hits = ((r.json() or {}).get("hits") or {}).get("hits") or []
    if not hits:
        raise NotFound("CVR-nummeret findes ikke i CVR-registret", code="cvr_not_found")
    return parse(hits[0])
