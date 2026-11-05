"""Look up a company in the Danish CVR register (Erhvervsstyrelsen's system-to-system Elasticsearch).

Only fields whose paths are documented in public client code are read: name, address, main industry,
status and "reklamebeskyttet" (the company has asked not to be contacted for marketing; sellers must respect
it). Credentials are free but must be requested from Erhvervsstyrelsen (cvrselvbetjening@erst.dk); without them
the lookup answers 501. NOT externally verified from this repository.
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
    "Vrvirksomhed.reklamebeskyttet",
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
        # None = the register did not say; treat as unknown, never as "may be contacted"
        "advertising_protected": v["reklamebeskyttet"] if isinstance(v.get("reklamebeskyttet"), bool) else None,
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


# --- search by name (used by the Privat assistant's booking, app/modules/browser/lookup.py) -----------------------------
# NOT externally verified: the query shape follows the register's documented Elasticsearch fields (the same paths the
# lookup above and app/modules/social/prospects.py read); run against the real register before relying on it.
SEARCH_SOURCE = [*SOURCE, "Vrvirksomhed.virksomhedMetadata.nyesteKontaktoplysninger"]


def search_by_name(name: str, city: str | None = None, size: int = 5) -> list[dict]:
    """Active-looking candidates whose name matches every word of `name` (optionally in the given city). Each hit is the
    parsed company plus `contacts` (the register's list of phone numbers, e-mails and websites)."""
    import httpx

    name = " ".join((name or "").split())[:120]
    if not name:
        raise ValidationFailed("Skriv virksomhedens navn", field_errors=[{"field": "name"}])
    if not configured():
        raise NotImplementedYet("CVR-opslag kræver adgang til CVR-registret (CVR_USERNAME/CVR_PASSWORD)",
                                code="cvr_not_configured")
    s = get_settings()
    must = [{"match": {"Vrvirksomhed.virksomhedMetadata.nyesteNavn.navn": {"query": name, "operator": "and"}}}]
    if city and city.strip():
        must.append({"match": {"Vrvirksomhed.virksomhedMetadata.nyesteBeliggenhedsadresse.postdistrikt": city.strip()[:60]}})
    body = {"_source": SEARCH_SOURCE, "size": size, "query": {"bool": {"must": must}}}
    try:
        r = httpx.post(s.cvr_url, json=body, auth=(s.cvr_username, s.cvr_password), timeout=15.0)
    except httpx.HTTPError as e:
        raise ApiError("CVR-registret svarede ikke", code="cvr_unavailable", status_code=502) from e
    if r.status_code >= 400:
        raise ApiError(f"CVR-registret afviste opslaget ({r.status_code})", code="cvr_unavailable", status_code=502)
    out = []
    for h in ((r.json() or {}).get("hits") or {}).get("hits") or []:
        p = parse(h)
        meta = (((h.get("_source") or {}).get("Vrvirksomhed") or {}).get("virksomhedMetadata")) or {}
        p["contacts"] = [str(c) for c in (meta.get("nyesteKontaktoplysninger") or [])]
        out.append(p)
    return out
