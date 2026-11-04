"""The add-on shop of Dialogbot Privat.

The core (chat, Min dag, private lists and reminders, quota/credits/account) is always on. Everything else is an
add-on: ONE `Addon` object registered in CATALOG below. An add-on brings its own chat tools (`tools`, each pointing at
a handler "module:function" that is imported only when called) and its endpoints call `require(db, ws_id, key)`.
Adding a feature = `register(Addon(...))` here (or from the feature's own module) – the shop endpoint, the chat's tool
list, the gating and the «Slå … til» offer in the chat all read the catalog; nothing else changes.

Plans: an add-on with `included_in` (plan keys) can only be switched on with the trial or one of those plans
(409 needs_plan, see subscriptions.py). Once on, it stays on; calls fall back to credits when the plan lapses.
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
    # The Shop texts: what it does (1–2 sentences), what you say to Peter, and the setup steps shown before enable.
    what: str = ""
    example: str = ""
    steps: tuple[str, ...] = ()
    # Plans whose rights include this app (the trial counts as Plus). Empty = free for everyone, plan or not.
    # Non-empty: enable() answers 409 needs_plan unless the account is entitled to one of them.
    included_in: tuple[str, ...] = ()
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
                "før der bliver ringet, og ser præcis hvad assistenten må spørge om og sige ja til. Opkald er med i "
                "din plan (prøveperioden tæller som Plus); ud over månedens opkald koster et ekstra opkald 3 credits, "
                "som du får igen, hvis ingen tager telefonen.",
    icon="phone", category="opkald", price_text="Med i alle planer – ekstra opkald for 3 credits", pricing="credits",
    what="Peter ringer til værkstedet, frisøren eller lægen for dig og aftaler en tid. Du godkender hvert opkald, "
         "før der bliver ringet, og ser bagefter, hvad virksomheden svarede.",
    example="«Ring til cykelværkstedet og find en tid torsdag efter klokken tre»",
    steps=("Bekræft dit mobilnummer, så Peter kan sige, hvem han ringer for",
           "Fortæl Peter, hvem han skal ringe til, og hvad han må sige ja til",
           "Godkend forslaget – først da ringer Peter"),
    included_in=("basis", "plus", "familie"),
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
    what="Del en indkøbs- eller to-do-liste med dem, du bor med. Alle kan tilføje og krydse af fra deres egen "
         "telefon, og I kan se, hvem der gjorde hvad.",
    example="«Del indkøbslisten med Anna»",
    steps=("Lav en liste, eller vælg en du har", "Bed Peter dele den – du får et link",
           "Send linket fra din egen telefon; de andre er med, når de trykker"),
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
    what="Lav en ønskeliste og del den. Dem, du deler med, kan reservere en gave i hemmelighed, så to ikke køber det "
         "samme – og du ser aldrig, hvad der er taget.",
    example="«Lav en ønskeliste med en ny cykelhjelm og den bog, jeg talte om»",
    steps=("Sig dine ønsker til Peter – han samler dem på en liste",
           "Del listen med familien eller vennerne via et link",
           "De reserverer i hemmelighed; du får bare gaverne"),
    permissions=("Deler en ønskeliste via et link, du selv sender", "Viser dit fornavn for dem, du deler med"),
    keywords=("ønskeliste", "ønsker", "fødselsdag", "gave"),
    on_disable="app.modules.privat.sharing:pause_sharing",
    shareable=True, resource_type="list", resource_hooks="app.modules.privat.sharing",
))

register(Addon(
    key="kalender", name="Kalender", tagline="Læg aftaler i din Google- eller Outlook-kalender",
    description="Aftaler, assistenten laver for dig, kommer automatisk i din egen kalender.",
    icon="calendar", category="aftaler", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="De tider, Peter aftaler for dig, lander automatisk i din egen Google- eller Outlook-kalender – med adresse "
         "og det, I aftalte.",
    example="«Læg tiden hos frisøren i min kalender»",
    steps=("Forbind din Google- eller Outlook-kalender", "Vælg hvilken kalender aftaler skal i",
           "Peter skriver aftalerne ind, når de er bekræftet"),
    included_in=("plus", "familie"),
    permissions=("Skriver aftaler i din kalender",), keywords=("kalender",),
))

register(Addon(
    key="pakker", name="Pakker", tagline="Følg dine forsendelser",
    description="Få besked, når en pakke er på vej, og hvor du kan hente den.",
    icon="package", category="hverdag", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="Giv Peter dit track-and-trace-nummer, så holder han øje med pakken og siger til, når den er klar til "
         "afhentning – og hvor.",
    example="«Følg pakken med nummer 00340434…»",
    steps=("Sig eller indsæt forsendelsesnummeret til Peter", "Peter følger pakken hos fragtfirmaet",
           "Du får besked, når den er på vej og kan hentes"),
    included_in=("plus", "familie"),
    permissions=("Læser forsendelsesnumre, du giver assistenten",), keywords=("pakke", "forsendelse"),
))

register(Addon(
    key="foedselsdage", name="Fødselsdage", tagline="Glem aldrig en fødselsdag igen",
    description="Peter husker familiens og vennernes fødselsdage og minder dig om dem i god tid – med et forslag til en gave.",
    icon="cake", category="hverdag", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="Fortæl Peter, hvem der har fødselsdag hvornår. Han minder dig om det nogle dage før, så du kan nå at købe "
         "en gave eller sende en hilsen.",
    example="«Mors fødselsdag er den 14. marts – mind mig om det en uge før»",
    steps=("Sig navnene og datoerne til Peter – én ad gangen eller mange på én gang",
           "Vælg hvor mange dage før, du vil mindes om det",
           "Peter minder dig om det hvert år"),
    included_in=("plus", "familie"),
    permissions=("Gemmer navne og fødselsdatoer, du giver assistenten",), keywords=("fødselsdag", "fylder år"),
))

register(Addon(
    key="madplan", name="Madplan", tagline="Ugens aftensmad – og indkøbslisten følger med",
    description="Peter laver en madplan for ugen ud fra det, I kan lide, og skriver indkøbslisten til den.",
    icon="utensils", category="hverdag", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="Sig hvor mange I er, og hvad I kan lide, så foreslår Peter aftensmad for ugen. Siger du ja, bliver "
         "ingredienserne til en indkøbsliste, du kan dele med husstanden.",
    example="«Lav en madplan for næste uge – vi er fire, og børnene spiser ikke fisk»",
    steps=("Fortæl Peter, hvor mange I er, og hvad I ikke spiser",
           "Få et forslag til ugen og ret det, der ikke passer",
           "Sig ja – indkøbslisten laves automatisk"),
    included_in=("plus", "familie"),
    permissions=("Gemmer jeres madvaner og allergier, som du selv skriver dem",), keywords=("madplan", "aftensmad"),
))

register(Addon(
    key="bil-og-syn", name="Bil & syn", tagline="Syn, service og dæk – Peter holder styr på bilen",
    description="Peter husker, hvornår bilen skal til syn og service, og ringer til værkstedet og aftaler en tid, når det er ved at være tid.",
    icon="car", category="hverdag", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="Giv Peter bilens nummerplade, så kender han næste synsdato. Han minder dig om syn, service og skift til "
         "vinterdæk – og kan ringe til dit værksted og aftale tiden for dig.",
    example="«Bilen skal til syn i maj – find en tid hos mit værksted i uge 18»",
    steps=("Sig nummerpladen til Peter", "Vælg dit værksted (eller lad Peter foreslå et i nærheden)",
           "Peter minder dig om syn og service og aftaler tiden, når du siger ja"),
    included_in=("plus", "familie"),
    permissions=("Slår bilens synsdato op på nummerpladen", "Ringer til dit værksted, når du har godkendt det"),
    keywords=("bil", "syn", "værksted", "dæk"),
))

register(Addon(
    key="regninger", name="Regninger", tagline="Bliv mindet om regninger, før de forfalder",
    description="Peter husker faste regninger og abonnementer og minder dig om dem, før de skal betales – så du undgår rykkere.",
    icon="receipt", category="hverdag", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="Fortæl Peter om dine faste regninger – husleje, forsikring, streaming – og hvornår de forfalder. Han "
         "minder dig om dem i tide og viser dig månedens overblik. Peter betaler aldrig noget selv.",
    example="«Mind mig om bilforsikringen den 1. hver måned – den er 640 kr.»",
    steps=("Sig regningerne og deres dato til Peter", "Vælg hvor mange dage før, du vil have besked",
           "Se månedens regninger samlet på Min dag"),
    included_in=("plus", "familie"),
    permissions=("Gemmer regningernes navn, beløb og dato, som du selv skriver dem", "Har aldrig adgang til din bank"),
    keywords=("regning", "regninger", "abonnement", "forfalder"),
))

register(Addon(
    key="laege-og-tandlaege", name="Læge & tandlæge", tagline="Tider hos læge og tandlæge – uden at hænge i telefonen",
    description="Peter ringer til lægen eller tandlægen og booker tiden for dig, og minder dig om det årlige tandeftersyn.",
    icon="heart", category="aftaler", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="Sig hvad det drejer sig om, og hvornår du kan, så ringer Peter til din læge eller tandlæge, når de åbner, "
         "og aftaler en tid. Han fortæller aldrig mere, end du har sagt god for.",
    example="«Book et tandeftersyn hos min tandlæge – helst en morgen i næste måned»",
    steps=("Gem din læge og tandlæge (navn og nummer)", "Sig til Peter, hvad du skal, og hvornår du kan",
           "Godkend opkaldet – Peter ringer og lægger tiden i din kalender"),
    included_in=("plus", "familie"),
    permissions=("Ringer til din læge eller tandlæge, når du har godkendt det",
                 "Siger kun dit navn og det, du selv har skrevet"),
    keywords=("læge", "tandlæge", "tandeftersyn", "lægetid"),
))

register(Addon(
    key="pakkeliste", name="Pakkeliste", tagline="Pakkelister til rejser og ture, der kan genbruges",
    description="Peter laver en pakkeliste til turen – ud fra vejret, hvor længe I er væk, og hvem der skal med – og husker den til næste gang.",
    icon="suitcase", category="lister", price_text="Med i Plus og Familie", pricing="free", status="coming_soon",
    what="Sig hvor I skal hen, hvor længe, og hvem der skal med, så skriver Peter en pakkeliste, som I krydser af. "
         "Næste gang starter han fra den, I brugte sidst.",
    example="«Lav en pakkeliste til en uge i sommerhus med to børn»",
    steps=("Fortæl Peter om turen – sted, længde og hvem", "Ret listen til, og del den med rejsefællerne",
           "Kryds af, mens I pakker"),
    included_in=("plus", "familie"),
    permissions=("Gemmer dine pakkelister til næste tur",), keywords=("pakkeliste", "pakke til", "rejse", "ferie"),
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


def included(db: OrmSession, ws_id: uuid.UUID, a: Addon, ent: dict | None = None) -> bool:
    """Whether the account's current rights let it switch this add-on on (free, or entitled to a listed plan)."""
    if not a.included_in:
        return True
    from app.modules.privat import subscriptions

    return subscriptions.covers(ent or subscriptions.entitlements(db, ws_id), a.included_in)


def out(db: OrmSession, ws_id: uuid.UUID, a: Addon, ent: dict | None = None) -> dict:
    row = db.get(PrivateAddonEnabled, (ws_id, a.key))
    on = row is not None and a.status != "coming_soon"
    return {"key": a.key, "name": a.name, "tagline": a.tagline, "description": a.description, "icon": a.icon,
            "category": a.category, "price_text": a.price_text, "pricing": a.pricing,
            "monthly_price_minor": a.monthly_price_minor, "status": a.status, "permissions": list(a.permissions),
            "requires": list(a.requires), "enabled": on, "enabled_at": row.enabled_at.isoformat() if on else None,
            "what": a.what, "example": a.example, "steps": list(a.steps), "included_in": list(a.included_in),
            "included": included(db, ws_id, a, ent), "requires_plan": bool(a.included_in)}


def catalog_out(db: OrmSession, ws_id: uuid.UUID) -> list[dict]:
    from app.modules.privat import subscriptions

    ent = subscriptions.entitlements(db, ws_id)
    return [out(db, ws_id, a, ent) for a in CATALOG.values()]


def enable(db: OrmSession, ws_id: uuid.UUID, key: str) -> Addon:
    a = get(key)
    if a.status == "coming_soon":
        raise Conflict(f"«{a.name}» kommer snart", code="coming_soon", extra={"addon": key})
    if not included(db, ws_id, a):
        names = [n for n in ("Plus", "Familie", "Basis") if n.lower() in a.included_in]
        raise Conflict(f"«{a.name}» er med i {' og '.join(names[:2]) if names else 'et abonnement'} – start 14 dage "
                       "gratis eller vælg en plan", code="needs_plan", extra={"addon": key, "plans": list(a.included_in)})
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
