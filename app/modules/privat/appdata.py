"""Per-app JSON settings of a personal workspace (`private_app_data`): read, change, write – nothing else."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.models import PrivateAppData
from app.modules.privat import rules


def get(db: OrmSession, ws_id: uuid.UUID, app_key: str) -> dict:
    row = db.get(PrivateAppData, (ws_id, app_key))
    return dict(row.data) if row is not None else {}


def put(db: OrmSession, ws_id: uuid.UUID, app_key: str, data: dict) -> dict:
    row = db.get(PrivateAppData, (ws_id, app_key), with_for_update=True)
    if row is None:
        row = PrivateAppData(workspace_id=ws_id, app_key=app_key, data=data)
        db.add(row)
    else:
        row.data = data
    row.updated_at = rules.now()
    db.flush()
    return data


def update(db: OrmSession, ws_id: uuid.UUID, app_key: str, **changes) -> dict:
    data = get(db, ws_id, app_key)
    data.update({k: v for k, v in changes.items() if v is not None})
    return put(db, ws_id, app_key, data)
