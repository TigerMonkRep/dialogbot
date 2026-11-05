"""The Læge & tandlæge app: the user's own doctor and dentist, and calls to them that the user approves.

Saved (`private_app_data` «laege-og-tandlaege»): only the practice's name and the number the user typed. A booking is
an ordinary call proposal (app «Ring for mig», which this app needs): nothing is dialled before the user approves, and
the assistant says only what the user wrote. Health details are never stored by this app.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.modules.privat import appdata

ADDON = "laege-og-tandlaege"
KINDS = {"laege": "læge", "tandlaege": "tandlæge"}


def contacts(db: OrmSession, ws_id: uuid.UUID) -> dict:
    return {k: v for k, v in appdata.get(db, ws_id, ADDON).items() if k in KINDS}


def save_contact(db: OrmSession, ws_id: uuid.UUID, *, kind: str, name: str, phone_e164: str) -> dict:
    data = appdata.get(db, ws_id, ADDON)
    data[kind] = {"name": " ".join(name.split())[:200], "phone": phone_e164}
    return appdata.put(db, ws_id, ADDON, data)


def remove_contact(db: OrmSession, ws_id: uuid.UUID, kind: str) -> None:
    data = appdata.get(db, ws_id, ADDON)
    data.pop(kind, None)
    appdata.put(db, ws_id, ADDON, data)
