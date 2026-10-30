"""What Peter may say about a system a prospect uses: the integration register.

Derived from the connector register (app/modules/integrations/connectors): a ready connector this deployment can
offer = AKTIV, a ready one that lacks configuration here (e.g. no OAuth client) = KRÆVER_OPSÆTNING, a "coming" one =
PLANLAGT, anything else = UKENDT. The operator can override per system in `sales_integration_notes`. Peter never
promises more than the status says.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.models import SalesIntegrationNote

STATUSES = ("AKTIV", "KRÆVER_OPSÆTNING", "PLANLAGT", "UKENDT")
SENTENCE = {
    "AKTIV": "Dialogbot kan kobles til {label}",
    "KRÆVER_OPSÆTNING": "koblingen til {label} kræver opsætning, før den virker",
    "PLANLAGT": "en kobling til {label} er planlagt, men ikke klar",
    "UKENDT": "en kobling til {label} er ikke afklaret",
}
# Names prospects use for systems the connector register knows under another label.
ALIASES = {"google calendar": "google_calendar", "google kalender": "google_calendar", "gmail kalender": "google_calendar",
           "outlook": "microsoft_calendar", "microsoft 365": "microsoft_calendar", "office 365": "microsoft_calendar",
           "outlook kalender": "microsoft_calendar", "sms": "twilio_sms", "zapier": "zapier", "make": "make"}


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9æøå]+", " ", (name or "").lower()).strip()


def register(db: OrmSession) -> list[dict]:
    from app.modules.integrations import connectors

    out: dict[str, dict] = {}
    for sp in connectors.all_specs():
        if sp.availability == "coming":
            status = "PLANLAGT"
        else:
            status = "AKTIV" if sp.unavailable_reason() is None else "KRÆVER_OPSÆTNING"
        out[sp.key] = {"system": sp.key, "label": sp.label, "status": status, "source": "connectors",
                       "note": sp.zapier_note or ""}
    for n in db.scalars(select(SalesIntegrationNote)):
        out[n.system] = {"system": n.system, "label": n.label, "status": n.status, "source": "operator", "note": n.note}
    return sorted(out.values(), key=lambda r: (STATUSES.index(r["status"]), r["label"]))


def lookup(db: OrmSession, name: str | None) -> dict:
    """Status for a system name as a prospect would say it. Unknown names are UKENDT, never assumed to work."""
    if not name:
        return {"system": None, "label": None, "status": "UKENDT", "source": "none", "note": ""}
    key = normalize(name)
    rows = register(db)
    target = ALIASES.get(key)
    for r in rows:
        if r["system"] == target or r["system"] == key.replace(" ", "_") or normalize(r["label"]) == key \
                or normalize(r["label"]).split(" ")[0] == key:
            return r
    return {"system": key.replace(" ", "_"), "label": name.strip()[:80], "status": "UKENDT", "source": "none", "note": ""}


def sentence(entry: dict) -> str:
    return SENTENCE[entry["status"]].format(label=entry["label"] or "systemet")


def set_note(db: OrmSession, *, system: str, label: str, status: str, note: str, user_id: uuid.UUID | None) -> SalesIntegrationNote:
    if status not in STATUSES:
        raise ValidationFailed("Ugyldig status", field_errors=[{"field": "status"}])
    key = normalize(system).replace(" ", "_")[:80]
    if not key:
        raise ValidationFailed("Angiv systemets navn", field_errors=[{"field": "system"}])
    row = db.get(SalesIntegrationNote, key) or SalesIntegrationNote(system=key)
    row.label, row.status, row.note, row.updated_by = label.strip()[:120] or system, status, note.strip()[:2000], user_id
    db.add(row)
    db.flush()
    return row
