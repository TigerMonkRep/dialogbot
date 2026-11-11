"""The Pakker app: track-and-trace numbers the user gives, followed through 17TRACK (PostNord, GLS, DAO, Bring, …).

Only the tracking number goes to 17TRACK. Saved (`private_app_data` «pakker»: `parcels` = [{number, label, status,
event, location, updated_at, done}]). The worker asks 17TRACK at most every POLL_MINUTES for parcels that are not
delivered and tells the user (push or e-mail) when the status changes to on the way, ready for pickup, out for delivery,
delivered or a problem. Without TRACK17_API_KEY the app is «Kommer snart» (addons.Addon.needs_setting).

17TRACK API v2.2 (api.17track.net/en/doc, read 5/11 2026 – NOT externally verified against a live key):
POST /track/v2.2/register [{"number": "..."}], POST /track/v2.2/gettrackinfo [{"number": "..."}], header «17token».
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import PrivateAddonEnabled, PrivateAppData, PrivateProfile, User
from app.modules.privat import addons, appdata, rules

ADDON = "pakker"
BASE = "https://api.17track.net/track/v2.2"
POLL_MINUTES = 120
POLL_NEW_MINUTES = 15      # not found yet (the carrier has not reported it to 17TRACK): ask more often
REFRESH_MINUTES = 10       # «Opdater nu» at most this often per parcel
MAX_PARCELS = 30
STATUS_TEXT = {"NotFound": "ikke registreret hos fragtfirmaet endnu", "InfoReceived": "afsenderen har meldt den",
               "InTransit": "på vej", "OutForDelivery": "ude til levering", "AvailableForPickup": "klar til afhentning",
               "Delivered": "leveret", "DeliveryFailure": "kunne ikke leveres", "Exception": "har et problem",
               "Expired": "ikke længere sporet"}
NOTIFY = {"InTransit", "OutForDelivery", "AvailableForPickup", "Delivered", "DeliveryFailure", "Exception"}
FINAL = {"Delivered", "Expired"}


class TrackError(Exception):
    pass


class Tracker(Protocol):
    def register(self, number: str) -> None: ...
    def info(self, number: str) -> dict: ...


class Track17:
    def __init__(self, key: str):
        self.key = key

    def _post(self, path: str, body: list[dict]) -> dict:
        import httpx

        try:
            r = httpx.post(f"{BASE}/{path}", json=body, headers={"17token": self.key, "content-type": "application/json"},
                           timeout=15.0)
        except httpx.HTTPError as e:
            raise TrackError("Sporingstjenesten kunne ikke nås") from e
        if r.status_code != 200:
            raise TrackError(f"Sporingstjenesten svarede {r.status_code}")
        out = r.json()
        if out.get("code") not in (0, None):
            raise TrackError(f"Sporingstjenesten svarede kode {out.get('code')}")
        return out.get("data") or {}

    def register(self, number: str) -> None:
        data = self._post("register", [{"number": number}])
        rejected = [x for x in data.get("rejected") or [] if (x.get("error") or {}).get("code") not in (-18019901,)]
        if rejected:  # -18019901 = already registered, which is fine
            raise TrackError((rejected[0].get("error") or {}).get("message") or "Nummeret blev afvist")

    def info(self, number: str) -> dict:
        data = self._post("gettrackinfo", [{"number": number}])
        for x in data.get("accepted") or []:
            ti = x.get("track_info") or {}
            latest = (ti.get("latest_status") or {})
            ev = (ti.get("latest_event") or {})
            carrier = ((ti.get("tracking") or {}).get("providers") or [{}])[0].get("provider", {}).get("name")
            return {"status": latest.get("status") or "NotFound", "event": (ev.get("description") or "")[:300],
                    "location": (ev.get("location") or "")[:200], "carrier": (carrier or "")[:100]}
        return {"status": "NotFound", "event": "", "location": "", "carrier": ""}


class FakeTracker:
    """Test double: statuses come from `FakeTracker.world[number]` (a list consumed one per info call)."""

    world: dict[str, list[dict]] = {}
    registered: list[str] = []

    def register(self, number: str) -> None:
        FakeTracker.registered.append(number)

    def info(self, number: str) -> dict:
        seq = FakeTracker.world.get(number) or [{"status": "InfoReceived", "event": "Afsender har oprettet forsendelsen"}]
        cur = seq.pop(0) if len(seq) > 1 else seq[0]
        return {"event": "", "location": "", "carrier": "PostNord", **cur}


def tracker() -> Tracker:
    key = get_settings().track17_api_key
    if key == "fake":
        return FakeTracker()
    if not key:
        raise TrackError("Pakkesporing er ikke sat op")
    return Track17(key)


def clean_number(raw: str) -> str | None:
    n = re.sub(r"[\s-]", "", raw or "").upper()
    return n if re.fullmatch(r"[A-Z0-9]{8,40}", n) else None


def parcels(db: OrmSession, ws_id: uuid.UUID) -> list[dict]:
    return list(appdata.get(db, ws_id, ADDON).get("parcels", []))


def _save(db: OrmSession, ws_id: uuid.UUID, items: list[dict]) -> None:
    appdata.update(db, ws_id, ADDON, parcels=items)


def text_of(p: dict) -> str:
    what = p.get("label") or p["number"]
    st = STATUS_TEXT.get(p.get("status") or "", p.get("status") or "ukendt")
    extra = f" ({p['location']})" if p.get("location") else ""
    return f"{what}: {st}{extra}"


def add(db: OrmSession, ws_id: uuid.UUID, *, number: str, label: str | None = None) -> dict:
    n = clean_number(number)
    if n is None:
        raise ValidationFailed("Forsendelsesnummeret kunne ikke læses", field_errors=[{"field": "number"}])
    items = parcels(db, ws_id)
    if any(p["number"] == n for p in items):
        return next(p for p in items if p["number"] == n)
    if len([p for p in items if not p.get("done")]) >= MAX_PARCELS:
        raise ValidationFailed(f"Du kan højst følge {MAX_PARCELS} pakker ad gangen")
    t = tracker()
    try:
        t.register(n)
        info = t.info(n)
    except TrackError as e:
        raise ValidationFailed(f"Pakken kunne ikke følges: {e}", field_errors=[{"field": "number"}]) from e
    p = {"number": n, "label": (label or "").strip()[:100] or None, **info, "updated_at": rules.now().isoformat(),
         "done": info["status"] in FINAL}
    _save(db, ws_id, [p, *items])
    return p


def remove(db: OrmSession, ws_id: uuid.UUID, number_or_label: str) -> dict | None:
    key = (number_or_label or "").strip().lower()
    num = clean_number(key)
    items = parcels(db, ws_id)
    hit = next((p for p in items if num and p["number"] == num), None) \
        or next((p for p in items if (p.get("label") or "").lower() == key), None)
    if hit is None:
        return None
    _save(db, ws_id, [p for p in items if p is not hit])
    return hit


def poll(db: OrmSession, now: datetime | None = None) -> int:
    """Worker schedule: refresh parcels not delivered, at most every POLL_MINUTES; tell the user when the status
    changes to one worth knowing. Returns the number of notifications."""
    from app.modules.integrations import email_templates as tpl
    from app.modules.integrations import privat_mails
    from app.modules.privat import push

    if addons.CATALOG.get(ADDON) is None or addons.CATALOG[ADDON].live_status == "coming_soon":
        return 0
    now = now or rules.now()
    url = f"{get_settings().frontend_base_url.rstrip('/')}/privat/pakker"
    rows = list(db.scalars(select(PrivateAppData).join(
        PrivateAddonEnabled, (PrivateAddonEnabled.workspace_id == PrivateAppData.workspace_id)
        & (PrivateAddonEnabled.key == ADDON)).where(PrivateAppData.app_key == ADDON)))
    t = tracker()
    n = 0
    for row in rows:
        items, changed = list(row.data.get("parcels", [])), False
        owner = None
        for i, p in enumerate(items):
            wait = POLL_NEW_MINUTES if p.get("status") in (None, "NotFound", "InfoReceived") else POLL_MINUTES
            if p.get("done") or now - datetime.fromisoformat(p["updated_at"]) < timedelta(minutes=wait):
                continue
            try:
                info = t.info(p["number"])
            except TrackError:
                continue
            new = {**p, **info, "updated_at": now.isoformat(), "done": info["status"] in FINAL}
            if info["status"] != p.get("status") and info["status"] in NOTIFY:
                owner = owner or db.scalar(select(User).join(PrivateProfile, PrivateProfile.user_id == User.id)
                                           .where(PrivateProfile.workspace_id == row.workspace_id))
                if owner is not None:
                    text = text_of(new) + "."
                    mail = privat_mails.parcel(text, info.get("event") or "", url, owner.interface_language)
                    push.notify(db, owner.id, title="Din pakke", body=text, url=url,
                                dedupe=f"parcel:{row.workspace_id}:{p['number']}:{info['status']}",
                                email={"to_email": owner.email, "email": tpl.to_payload(mail)}, workspace_id=row.workspace_id)
                    n += 1
            items[i], changed = new, True
        if changed:
            appdata.put(db, row.workspace_id, ADDON, {**row.data, "parcels": items})
    return n


def refresh(db: OrmSession, ws_id: uuid.UUID, number: str) -> dict | None:
    """«Opdater nu»: ask 17TRACK for one parcel, at most every REFRESH_MINUTES. None if the user does not follow it."""
    items = parcels(db, ws_id)
    num = clean_number(number)
    i = next((k for k, p in enumerate(items) if p["number"] == num), None)
    if i is None:
        return None
    p = items[i]
    now = rules.now()
    if now - datetime.fromisoformat(p["updated_at"]) < timedelta(minutes=REFRESH_MINUTES):
        return p
    try:
        info = tracker().info(p["number"])
    except TrackError as e:
        raise ValidationFailed(f"Status kunne ikke hentes: {e}") from e
    items[i] = {**p, **info, "updated_at": now.isoformat(), "done": info["status"] in FINAL}
    _save(db, ws_id, items)
    return items[i]
