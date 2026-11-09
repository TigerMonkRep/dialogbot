"""«Mine apps»: what each app is holding for the user, in one short line («Syn om 34 dage · 12. dec.»), plus the per-app
state the app shell remembers (setup progress, switched off with data kept, «Giv mig besked»).

`summary_line` is best effort and read-only: an app without data, or a reader that fails, gives None and the web
shows the app's tagline instead. Nothing here changes whether an app is on – that is addons.enable/disable.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict, ValidationFailed
from app.models import PrivateAddonState
from app.modules.privat import rules

log = logging.getLogger(__name__)

MONTHS = ("jan.", "feb.", "mar.", "apr.", "maj", "jun.", "jul.", "aug.", "sep.", "okt.", "nov.", "dec.")
LINE_MAX = 90


# --------------------------------------------------------------------------- per-app state

def state(db: OrmSession, ws_id: uuid.UUID, key: str, *, create: bool = False) -> PrivateAddonState | None:
    row = db.get(PrivateAddonState, (ws_id, key))
    if row is None and create:
        row = PrivateAddonState(workspace_id=ws_id, key=key, setup_done=0, updated_at=rules.now())
        db.add(row)
        db.flush()
    return row


def states(db: OrmSession, ws_id: uuid.UUID) -> dict[str, PrivateAddonState]:
    return {r.key: r for r in db.scalars(select(PrivateAddonState).where(PrivateAddonState.workspace_id == ws_id))}


def on_enabled(db: OrmSession, ws_id: uuid.UUID, key: str) -> None:
    row = state(db, ws_id, key, create=True)
    row.disabled_at, row.updated_at = None, rules.now()


def on_disabled(db: OrmSession, ws_id: uuid.UUID, key: str) -> None:
    row = state(db, ws_id, key, create=True)
    row.disabled_at, row.updated_at = rules.now(), rules.now()


def set_setup(db: OrmSession, ws_id: uuid.UUID, key: str, done: int) -> PrivateAddonState:
    """How many of the app's setup steps the user has finished (0 … len(steps)). Only for an app that is on."""
    from app.modules.privat import addons

    a = addons.get(key)
    if not addons.is_enabled(db, ws_id, key):
        raise Conflict(f"Slå «{a.name}» til først", code="addon_disabled", extra={"addon": key})
    if done < 0 or done > len(a.steps):
        raise ValidationFailed("Ugyldigt trin", field_errors=[{"field": "done"}])
    row = state(db, ws_id, key, create=True)
    row.setup_done, row.updated_at = done, rules.now()
    return row


def request_notify(db: OrmSession, ws_id: uuid.UUID, key: str) -> PrivateAddonState:
    """«Giv mig besked», when a «Kommer snart» app arrives (stored per account instead of in the browser)."""
    from app.modules.privat import addons

    addons.get(key)
    row = state(db, ws_id, key, create=True)
    row.notify_requested_at = row.notify_requested_at or rules.now()
    row.updated_at = rules.now()
    return row


# --------------------------------------------------------------------------- deleting an app's data

def _data_tables(key: str):
    """(model, filter-builder) for the rows that hold this app's data, or None when its data is not the app's alone
    (shared lists, wishlists and calls live in tasks, which the user deletes in Opgaver)."""
    from app.models import PrivateAppData, PrivateBill, PrivateBirthday

    if key == "regninger":
        return [(PrivateBill, lambda ws: PrivateBill.workspace_id == ws)]
    if key == "foedselsdage":
        return [(PrivateBirthday, lambda ws: PrivateBirthday.workspace_id == ws)]
    if key in ("ring-for-mig", "delte-lister", "oenskelister", "kalender", "rejser"):
        return None
    return [(PrivateAppData, lambda ws: (PrivateAppData.workspace_id == ws) & (PrivateAppData.app_key == key))]


def deletable(key: str) -> bool:
    return _data_tables(key) is not None


def delete_data(db: OrmSession, ws_id: uuid.UUID, key: str) -> int:
    """Delete what an app has saved – only while it is switched off, so nothing running loses its data by surprise.
    Returns how many rows went. Photos in storage go with the household apps' rows (files are keyed per item)."""
    from sqlalchemy import delete

    from app.modules.privat import addons, files

    a = addons.get(key)
    if addons.is_enabled(db, ws_id, key):
        raise Conflict(f"Slå «{a.name}» fra, før du sletter dens data", code="addon_enabled", extra={"addon": key})
    tables = _data_tables(key)
    if tables is None:
        raise Conflict(f"«{a.name}» gemmer sine ting i dine lister og opgaver – slet dem dér", code="not_deletable",
                       extra={"addon": key})
    from app.models import PrivateAppData

    n = 0
    for model, where in tables:
        if model is PrivateAppData:
            for row in db.scalars(select(PrivateAppData).where(where(ws_id))):
                for it in (row.data or {}).get("items", []) if isinstance(row.data, dict) else []:
                    if isinstance(it, dict) and it.get("photo"):
                        files.delete(it["photo"])
        n += db.execute(delete(model).where(where(ws_id))).rowcount or 0
    st = state(db, ws_id, key)
    if st is not None:
        st.setup_done, st.disabled_at, st.updated_at = 0, None, rules.now()  # nothing kept any more
    db.flush()
    return n


# --------------------------------------------------------------------------- the one line per app

def _d(iso_or_date) -> str:
    d = iso_or_date if isinstance(iso_or_date, date) else date.fromisoformat(str(iso_or_date)[:10])
    return f"{d.day}. {MONTHS[d.month - 1]}"


def _days(iso: str, today: date) -> int:
    return (date.fromisoformat(str(iso)[:10]) - today).days


def _in(n: int) -> str:
    return "i dag" if n == 0 else "i morgen" if n == 1 else f"om {n} dage" if n > 1 else f"for {-n} dage siden"


def _first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    s = text.strip().split("\n")[0]
    for sep in (". ", " – "):
        if sep in s:
            s = s.split(sep)[0]
            break
    s = s.rstrip(".")
    return (s[: LINE_MAX - 1] + "…") if len(s) > LINE_MAX else s


def _car(db, ws_id, today):
    from app.modules.privat import appdata

    d = appdata.get(db, ws_id, "bil-og-syn")
    nxt = sorted(((_days(d[k], today), label, d[k]) for k, label in (("inspection_due", "Syn"), ("service_due", "Service"))
                  if d.get(k)), key=lambda x: x[0])
    if nxt:
        n, label, iso = nxt[0]
        return f"{label} {_in(n)} · {_d(iso)}"
    return f"{d['plate']} gemt" if d.get("plate") else None


def _bills(db, ws_id, today):
    from app.modules.privat import bills

    ov = bills.month_overview(db, ws_id, today)
    if not ov["items"]:
        return None
    n = len(ov["items"])
    return f"{n} {'regning' if n == 1 else 'regninger'} i {ov['month'].split()[0]}" + \
        (f" · {ov['total_text']}" if ov["total_minor"] else "")


def _birthdays(db, ws_id, today):
    from app.modules.privat import birthdays

    rows = birthdays.all_for(db, ws_id)
    if not rows:
        return None
    b = min(rows, key=lambda r: birthdays.next_date(r, today))
    return birthdays.summary(b, today)


def _calendar(db, ws_id, today):
    from app.modules.privat import appointments

    up = appointments.upcoming(db, ws_id, limit=1)
    if not up:
        return None
    a = up[0]
    return f"{a.title} · {rules.lower_first(rules.when_text(a.starts_at))}"


def _calls(db, ws_id, today):
    from app.modules.privat import subscriptions

    e = subscriptions.entitlements(db, ws_id)
    if not e.get("calls_quota"):
        return None
    return f"{e['calls_left']} af {e['calls_quota']} opkald tilbage i {rules.month_name()}"


def _lists(mode: str):
    def fn(db, ws_id, today):
        from app.models import PrivateTask

        n = db.scalar(select(func.count()).select_from(PrivateTask).where(
            PrivateTask.workspace_id == ws_id, PrivateTask.share_mode == mode)) or 0
        if not n:
            return None
        word = ("delt liste", "delte lister") if mode == "group" else ("delt ønskeliste", "delte ønskelister")
        return f"{n} {word[0] if n == 1 else word[1]}"
    return fn


def _meals(db, ws_id, today):
    from app.modules.privat import appdata

    d = appdata.get(db, ws_id, "madplan")
    if d.get("last_plan_at"):
        return f"Ugeplan lavet {_d(d['last_plan_at'])}"
    return f"Til {d['people']} personer" if d.get("people") else None


def _health(db, ws_id, today):
    from app.modules.privat import health

    got = [health.KINDS.get(k, k) for k in health.contacts(db, ws_id)]
    return (" og ".join(got).capitalize() + " gemt") if got else None


def _packing(db, ws_id, today):
    from app.modules.privat import appdata

    n = len(appdata.get(db, ws_id, "pakkeliste").get("lists", []))
    return f"{n} {'pakkeliste' if n == 1 else 'pakkelister'} gemt" if n else None


def _overview(module: str):
    def fn(db, ws_id, today):
        import importlib

        ov = importlib.import_module(f"app.modules.privat.{module}").overview(db, ws_id)
        text = _first_sentence(ov.get("summary"))
        empty = ("ingen ", "der er ikke", "du har ikke", "intet ", "ikke noget", "sig fx", "fortæl ")
        return None if not text or text.lower().startswith(empty) else text
    return fn


READERS = {
    "bil-og-syn": _car, "regninger": _bills, "foedselsdage": _birthdays, "kalender": _calendar, "ring-for-mig": _calls,
    "delte-lister": _lists("group"), "oenskelister": _lists("wishlist"), "madplan": _meals,
    "laege-og-tandlaege": _health, "pakkeliste": _packing,
    "abonnementer": _overview("subs_app"), "haandvaerker": _overview("quotes"), "faelles-udgifter": _overview("expenses"),
    "garanti": _overview("warranty"), "fest": _overview("party"), "flytning": _overview("moving"),
    "kaeledyr": _overview("pets"), "hus-og-vedligehold": _overview("home"), "fitness-og-sundhed": _overview("fitness"),
}


def summary_line(db: OrmSession, ws_id: uuid.UUID, key: str) -> str | None:
    fn = READERS.get(key)
    if fn is None:
        return None
    try:
        with db.begin_nested():  # a failing reader must not poison the request's transaction
            line = fn(db, ws_id, rules.local().date())
    except Exception:  # noqa: BLE001 – the line is a nicety; the tagline takes its place
        log.warning("app_status: summary for %s failed", key, exc_info=True)
        return None
    if not line:
        return None
    line = " ".join(str(line).split())
    return (line[: LINE_MAX - 1] + "…") if len(line) > LINE_MAX else line
