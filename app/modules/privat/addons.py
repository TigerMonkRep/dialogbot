"""The add-on shop of Dialogbot Privat.

The core (chat, Min dag, private lists and reminders, quota/credits/account) is always on. Everything else is an
add-on: ONE `Addon` object registered in CATALOG below. An add-on brings its own chat tools (`tools`, each pointing at
a handler "module:function" that is imported only when called) and its endpoints call `require(db, ws_id, key)`.
Adding a feature = `register(Addon(...))` here (or from the feature's own module) – the shop endpoint, the chat's tool
list, the gating and the «Slå … til» offer in the chat all read the catalog; nothing else changes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import PrivateAddonEnabled
from app.modules.privat import rules


@dataclass(frozen=True)
class AddonTool:
    """A chat tool owned by an add-on. `handler` is "module:function" with signature (chat_ctx, args) -> str."""

    name: str
    description: str
    input_schema: dict
    handler: str


@dataclass(frozen=True)
class Addon:
    key: str
    name: str
    tagline: str
    description: str
    icon: str
    category: str
    price_text: str
    pricing: str = "free"  # free | credits | monthly
    monthly_price_minor: int | None = None
    status: str = "available"  # available | beta | coming_soon
    permissions: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    tools: tuple[AddonTool, ...] = ()
    # Words that show a request belongs to this add-on (given to the model with suggest_addon, and used by the fake).
    keywords: tuple[str, ...] = ()
    # Called as fn(db, workspace_id) when the user switches it off ("module:function"); data is always kept.
    on_disable: str | None = None
    # Shareable add-ons get the generic invitation (app/modules/privat/invites.py): link, public preview, accept,
    # referral reward. `resource_hooks` is an optional module with authorize/preview/accept for its resource_type;
    # without it the invite simply invites the person to the add-on itself.
    shareable: bool = False
    resource_type: str | None = None
    resource_hooks: str | None = None
    extra: dict = field(default_factory=dict)


CATALOG: dict[str, Addon] = {}


def register(addon: Addon) -> Addon:
    if addon.pricing not in ("free", "credits", "monthly") or addon.status not in ("available", "beta", "coming_soon"):
        raise ValueError(f"invalid add-on {addon.key}")
    CATALOG[addon.key] = addon
    return addon


def unregister(key: str) -> None:
    CATALOG.pop(key, None)


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


_STR_LIST = {"type": "array", "items": {"type": "string"}}

# --------------------------------------------------------------------------- the catalog

register(Addon(
    key="ring-for-mig", name="Ring for mig", tagline="Assistenten ringer til virksomheder for dig",
    description="Bed assistenten ringe til fx værkstedet, frisøren eller boligforeningen. Du godkender hvert opkald, "
                "før der bliver ringet, og ser præcis hvad assistenten må spørge om og sige ja til. Et opkald "
                "reserverer 3 credits; tager ingen telefonen, får du dem igen.",
    icon="phone", category="opkald", price_text="3 credits pr. besvaret opkald", pricing="credits",
    permissions=("Ringer til virksomheder, du har godkendt", "Siger dit navn til virksomheden",
                 "Deler kun dit mobilnummer, hvis du siger ja"),
    keywords=("ring", "ringe", "opkald", "telefon"),
    tools=(AddonTool(
        "propose_call",
        "Foreslå et opkald til en virksomhed. Der bliver ALDRIG ringet, før brugeren har godkendt forslaget. Opfind "
        "aldrig et telefonnummer: brug kun et nummer, brugeren selv har skrevet, eller en virksomhed fra listen, du "
        "får tilbage (fixture_id). Kender du ikke nummeret, så send kun business_name/category.",
        _obj({"business_name": {"type": "string"}, "phone": {"type": "string", "description": "Kun hvis brugeren skrev det"},
              "category": {"type": "string", "description": "Fx cykelværksted, frisør, tandlæge"},
              "fixture_id": {"type": "string"}, "purpose": {"type": "string"},
              "window": {"type": "string", "description": "Hvornår brugeren kan, fx 'torsdag efter kl. 15'"},
              "may_ask": {"type": "string"}, "may_agree": {"type": "string"}, "may_not": {"type": "string"}},
             ["purpose"]),
        "app.modules.privat.chat:tool_propose_call"),),
))

register(Addon(
    key="delte-lister", name="Delte lister", tagline="Fælles lister, hvor alle kan tilføje",
    description="Del en indkøbsliste eller to-do-liste med familien. Alle kan tilføje og krydse af, og I kan se, "
                "hvem der gjorde hvad.",
    icon="users", category="lister", price_text="Gratis", pricing="free",
    permissions=("Deler en liste via et link, du selv sender", "Viser dit fornavn for dem, du deler med"),
    keywords=("del ", "dele", "delt", "fælles"),
    tools=(AddonTool(
        "share_list",
        "Foreslå at dele en af brugerens lister via et invitationslink. Intet bliver delt eller sendt, før brugeren "
        "siger ja. mode: group (alle tilføjer/krydser af) eller wishlist (ønskeliste med hemmelige reservationer).",
        _obj({"task_id": {"type": "string"}, "with_name": {"type": "string"},
              "mode": {"type": "string", "enum": ["group", "wishlist"]},
              "role": {"type": "string", "enum": ["editor", "viewer"]}}),
        "app.modules.privat.chat:tool_share_list"),
        AddonTool(
            "share_with_group",
            "Foreslå at dele en liste med en gemt gruppe («Mine folk», fx Familien). Intet deles før brugeren siger ja.",
            _obj({"group_name": {"type": "string"}, "task_id": {"type": "string"},
                  "mode": {"type": "string", "enum": ["group", "wishlist"]}}, ["group_name"]),
            "app.modules.privat.chat:tool_share_with_group"),
        AddonTool(
            "create_group",
            "Foreslå at gemme en gruppe af personer (navn + evt. nummer, som brugeren selv har skrevet). Gemmes først, "
            "når brugeren siger ja. Opfind aldrig numre.",
            _obj({"name": {"type": "string"},
                  "members": {"type": "array", "items": _obj({"name": {"type": "string"}, "phone": {"type": "string"}},
                                                             ["name"])}}, ["name"]),
            "app.modules.privat.chat:tool_create_group")),
    on_disable="app.modules.privat.sharing:pause_sharing",
    shareable=True, resource_type="list", resource_hooks="app.modules.privat.sharing",
))

register(Addon(
    key="oenskelister", name="Ønskelister", tagline="Del ønsker – andre reserverer i hemmelighed",
    description="Del din ønskeliste. Dem, du deler med, kan skrive «Jeg køber den», så to ikke køber det samme – "
                "og du ser aldrig, hvad der er reserveret. Overraskelsen holdes.",
    icon="gift", category="lister", price_text="Gratis", pricing="free",
    permissions=("Deler en ønskeliste via et link, du selv sender", "Viser dit fornavn for dem, du deler med"),
    keywords=("ønskeliste", "ønsker", "fødselsdag", "gave"),
    on_disable="app.modules.privat.sharing:pause_sharing",
    shareable=True, resource_type="list", resource_hooks="app.modules.privat.sharing",
))

register(Addon(
    key="kalender", name="Kalender", tagline="Læg aftaler i din Google- eller Outlook-kalender",
    description="Aftaler, assistenten laver for dig, kommer automatisk i din egen kalender.",
    icon="calendar", category="aftaler", price_text="Kommer snart", pricing="free", status="coming_soon",
    permissions=("Skriver aftaler i din kalender",), keywords=("kalender",),
))

register(Addon(
    key="pakker", name="Pakker", tagline="Følg dine forsendelser",
    description="Få besked, når en pakke er på vej, og hvor du kan hente den.",
    icon="package", category="hverdag", price_text="Kommer snart", pricing="free", status="coming_soon",
    permissions=("Læser forsendelsesnumre, du giver assistenten",), keywords=("pakke", "forsendelse"),
))

# Which add-on a shared list needs, per share mode.
SHARE_MODE_ADDON = {"group": "delte-lister", "wishlist": "oenskelister"}


# --------------------------------------------------------------------------- state

def enabled_keys(db: OrmSession, ws_id: uuid.UUID) -> set[str]:
    keys = set(db.scalars(select(PrivateAddonEnabled.key).where(PrivateAddonEnabled.workspace_id == ws_id)))
    return {k for k in keys if k in CATALOG and CATALOG[k].status != "coming_soon"}


def is_enabled(db: OrmSession, ws_id: uuid.UUID, key: str) -> bool:
    return key in enabled_keys(db, ws_id)


def require(db: OrmSession, ws_id: uuid.UUID, key: str) -> None:
    if not is_enabled(db, ws_id, key):
        a = CATALOG.get(key)
        raise Forbidden(f"Slå tilføjelsen «{a.name if a else key}» til først", code="addon_disabled",
                        extra={"addon": key})


def get(key: str) -> Addon:
    a = CATALOG.get(key)
    if a is None:
        raise NotFound("Tilføjelsen findes ikke")
    return a


def out(db: OrmSession, ws_id: uuid.UUID, a: Addon) -> dict:
    row = db.get(PrivateAddonEnabled, (ws_id, a.key))
    on = row is not None and a.status != "coming_soon"
    return {"key": a.key, "name": a.name, "tagline": a.tagline, "description": a.description, "icon": a.icon,
            "category": a.category, "price_text": a.price_text, "pricing": a.pricing,
            "monthly_price_minor": a.monthly_price_minor, "status": a.status, "permissions": list(a.permissions),
            "requires": list(a.requires), "enabled": on, "enabled_at": row.enabled_at.isoformat() if on else None}


def catalog_out(db: OrmSession, ws_id: uuid.UUID) -> list[dict]:
    return [out(db, ws_id, a) for a in CATALOG.values()]


def enable(db: OrmSession, ws_id: uuid.UUID, key: str) -> Addon:
    a = get(key)
    if a.status == "coming_soon":
        raise Conflict(f"«{a.name}» kommer snart", code="coming_soon", extra={"addon": key})
    for dep in a.requires:
        if not is_enabled(db, ws_id, dep):
            enable(db, ws_id, dep)
    if db.get(PrivateAddonEnabled, (ws_id, key)) is None:
        db.add(PrivateAddonEnabled(workspace_id=ws_id, key=key, enabled_at=rules.now()))
        db.flush()
    return a


def disable(db: OrmSession, ws_id: uuid.UUID, key: str) -> Addon:
    a = get(key)
    for other in CATALOG.values():  # add-ons that need this one go off too
        if key in other.requires and is_enabled(db, ws_id, other.key):
            disable(db, ws_id, other.key)
    row = db.get(PrivateAddonEnabled, (ws_id, key))
    if row is not None:
        db.delete(row)
        db.flush()
        if a.on_disable:
            _call(a.on_disable)(db, ws_id)
    return a


def enable_defaults(db: OrmSession, ws_id: uuid.UUID) -> None:
    for key in (k.strip() for k in get_settings().privat_default_addons.split(",")):
        if key in CATALOG and CATALOG[key].status != "coming_soon":
            enable(db, ws_id, key)


def tools_for(db: OrmSession, ws_id: uuid.UUID) -> list[AddonTool]:
    keys = enabled_keys(db, ws_id)
    return [t for a in CATALOG.values() if a.key in keys for t in a.tools]


def offerable(db: OrmSession, ws_id: uuid.UUID) -> list[Addon]:
    """Add-ons the user could switch on (available, not on): what the chat may offer instead of doing it."""
    keys = enabled_keys(db, ws_id)
    return [a for a in CATALOG.values() if a.status != "coming_soon" and a.key not in keys]


def tool_owner(name: str) -> str | None:
    for a in CATALOG.values():
        if any(t.name == name for t in a.tools):
            return a.key
    return None


def _call(path: str):
    import importlib

    mod, fn = path.split(":")
    return getattr(importlib.import_module(mod), fn)


def hooks(a: Addon):
    import importlib

    return importlib.import_module(a.resource_hooks) if a.resource_hooks else None


def handler(tool: AddonTool):
    return _call(tool.handler)
