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
    # «Du skal bruge»: the few things the user needs at hand to get going (shown on the app's shop page).
    needs: tuple[str, ...] = ()
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
    # A setting (Settings attribute) the app needs to work, e.g. an API key. Without it the app is «coming_soon».
    # A tuple means: at least one of them.
    needs_setting: str | tuple[str, ...] | None = None
    # "module:function" returning whether the app is really set up (when one setting alone does not decide it).
    needs_check: str | None = None

    @property
    def live_status(self) -> str:
        if self.needs_setting:
            names = (self.needs_setting,) if isinstance(self.needs_setting, str) else self.needs_setting
            if not any(getattr(get_settings(), n, None) for n in names):
                return "coming_soon"
        if self.needs_check:
            import importlib

            mod, fn = self.needs_check.split(":")
            if not getattr(importlib.import_module(mod), fn)():
                return "coming_soon"
        return self.status


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
    needs=("Virksomhedens navn eller nummer", "Dit mobilnummer, hvis de skal kunne ringe tilbage"),
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
        "aldrig et telefonnummer: send kun phone, hvis brugeren selv har skrevet det. Ellers send business_name eller "
        "category (og city, hvis brugeren nævnte en by) – så slår Dialogbot virksomheden op og lader brugeren vælge.",
        _obj({"business_name": {"type": "string"}, "phone": {"type": "string", "description": "Kun hvis brugeren skrev det"},
              "category": {"type": "string", "description": "Fx cykelværksted, frisør, tandlæge"},
              "city": {"type": "string"}, "purpose": {"type": "string"},
              "window": {"type": "string", "description": "Hvornår brugeren kan, fx 'torsdag efter kl. 15'"},
              "may_ask": {"type": "string"}, "may_agree": {"type": "string"}, "may_not": {"type": "string"}},
             ["purpose"]),
        "app.modules.privat.chat:tool_propose_call"),
        AddonTool(
            "find_business",
            "Slå en virksomhed op (CVR-registret og Google), før du booker hos den. Send navn og gerne by. Svaret har et "
            "business_id, som start_booking bruger. Opfind aldrig navn, nummer eller hjemmeside.",
            _obj({"name": {"type": "string"}, "city": {"type": "string"}}, ["name"]),
            "app.modules.browser.assistant:tool_find_business"),
        AddonTool(
            "start_booking",
            "Book en tid hos en virksomhed, du har fundet med find_business. Du vælger IKKE selv, om der ringes, eller om det "
            "bookes på hjemmesiden: Dialogbot vælger efter faste regler og fortæller brugeren hvilket. Send "
            "user_said_track KUN hvis brugeren selv skrev, at du skal ringe («ring») eller booke på hjemmesiden («skriv»). "
            "service og preferred_windows skal komme fra brugeren (konkrete datoer, evt. med klokkeslæt); gæt aldrig. Der "
            "bliver hverken ringet eller booket uden brugerens godkendelse.",
            _obj({"business_id": {"type": "string"}, "intent": {"type": "string", "enum": ["book", "flyt", "aflys"]},
                  "service": {"type": "string", "description": "Fx herreklip, tandrensning"},
                  "preferred_windows": {"type": "array", "items": _obj(
                      {"date": {"type": "string", "description": "YYYY-MM-DD"}, "from": {"type": "string", "description": "HH:MM"},
                       "to": {"type": "string", "description": "HH:MM"}}, ["date"])},
                  "user_said_track": {"type": "string", "enum": ["ring", "skriv"]}},
                 ["business_id", "intent"]),
            "app.modules.browser.assistant:tool_start_booking"),
        AddonTool(
            "switch_to_phone",
            "Brug, når brugeren siger «ring i stedet» (eller lignende), mens en booking på en hjemmeside kører. Stopper "
            "bookingen og laver et forslag til et opkald, som brugeren godkender.",
            _obj({"task_id": {"type": "string"}}),
            "app.modules.browser.assistant:tool_switch_to_phone"),),
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
    key="kalender", name="Kalender", tagline="Læg aftaler i din Google-, Outlook- eller iPhone-kalender",
    needs=("En Google- eller Outlook-konto", "– eller bare din iPhone-kalender"),
    description="Aftaler, du har godkendt, kommer automatisk i din egen kalender.",
    icon="calendar", category="aftaler", price_text="Med i Plus og Familie", pricing="free",
    what="De tider, Peter aftaler for dig, og dem du selv fortæller ham, lander i din egen kalender – med adresse og "
         "det, I aftalte. Google og Outlook får dem med det samme; alle andre kalendere via et privat link.",
    example="«Læg tiden hos frisøren i min kalender»",
    steps=("Forbind Google eller Outlook – eller abonnér på dit private kalenderlink (iPhone og alle andre)",
           "Peter lægger aftaler ind, når de er bekræftet, og når du selv fortæller ham om en tid",
           "Flyttes eller fjernes en aftale, opdateres din kalender også"),
    included_in=("plus", "familie"),
    permissions=("Skriver aftaler, du har godkendt, i din kalender", "Læser ikke dine andre aftaler"),
    keywords=("kalender", "kalenderen", "google kalender", "outlook"),
    tools=(AddonTool(
        "add_to_calendar",
        "Læg en aftale, brugeren selv har fortalt om, i brugerens kalender (fx «tandlæge tirsdag kl. 9»). Brug kun en "
        "tid, brugeren selv har skrevet; gæt aldrig. Aftaler fra opkald og bookinger lægges i kalenderen af sig selv.",
        _obj({"title": {"type": "string"}, "starts_at": {"type": "string", "description": "Lokal tid, fx 2026-11-12T09:00"},
              "minutes": {"type": "integer", "description": "Varighed, hvis brugeren sagde den"},
              "location": {"type": "string"}}, ["title", "starts_at"]),
        "app.modules.privat.chat:tool_add_to_calendar"),
        AddonTool(
            "calendar_status",
            "Fortæl om brugerens kalender: hvilke kalendere der er forbundet, og hvordan man forbinder Google, Outlook "
            "eller iPhone. Brug den, når brugeren beder om at få sin kalender tilføjet eller forbundet.",
            _obj({}),
            "app.modules.privat.chat:tool_calendar_status")),
))

register(Addon(
    key="pakker", name="Pakker", tagline="Følg dine forsendelser",
    description="Få besked, når en pakke er på vej, og hvor du kan hente den.",
    icon="package", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    needs_setting="track17_api_key",
    what="Giv Peter dit track-and-trace-nummer, så holder han øje med pakken og siger til, når den er klar til "
         "afhentning – og hvor.",
    example="«Følg pakken med nummer 00340434…»",
    steps=("Sig eller indsæt forsendelsesnummeret til Peter", "Peter følger pakken hos fragtfirmaet",
           "Du får besked, når den er på vej og kan hentes"),
    included_in=("plus", "familie"),
    permissions=("Læser forsendelsesnumre, du giver assistenten",
                 "Sender kun forsendelsesnummeret til sporingstjenesten 17TRACK"),
    keywords=("pakke", "forsendelse", "track", "sporing"),
    tools=(AddonTool(
        "track_parcel",
        "Følg en pakke: number er track-and-trace-nummeret, præcis som brugeren skrev det; label er hvad det er "
        "(fx «nye sko»), hvis brugeren sagde det.",
        _obj({"number": {"type": "string"}, "label": {"type": "string"}}, ["number"]),
        "app.modules.privat.chat:tool_track_parcel"),
        AddonTool("parcels_status", "Vis status for de pakker, brugeren følger.", _obj({}),
                  "app.modules.privat.chat:tool_parcels_status"),
        AddonTool("stop_tracking", "Stop med at følge en pakke (nummer eller label).",
                  _obj({"number": {"type": "string"}}, ["number"]), "app.modules.privat.chat:tool_stop_tracking")),
))

register(Addon(
    key="foedselsdage", name="Fødselsdage", tagline="Glem aldrig en fødselsdag igen",
    needs=("Navne og datoer",),
    description="Peter husker familiens og vennernes fødselsdage og minder dig om dem i god tid.",
    icon="cake", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Fortæl Peter, hvem der har fødselsdag hvornår. Han minder dig om det nogle dage før, så du kan nå at købe "
         "en gave eller sende en hilsen.",
    example="«Mors fødselsdag er den 14. marts – mind mig om det en uge før»",
    steps=("Sig navnene og datoerne til Peter – én ad gangen eller mange på én gang",
           "Vælg hvor mange dage før, du vil mindes om det",
           "Peter minder dig om det hvert år"),
    included_in=("plus", "familie"),
    permissions=("Gemmer navne og fødselsdatoer, du giver assistenten",), keywords=("fødselsdag", "fylder år"),
    tools=(AddonTool(
        "add_birthdays",
        "Gem en eller flere fødselsdage, brugeren har fortalt om. date er fx «14. marts», «14.03.1946» eller "
        "«1946-03-14» – kun det brugeren skrev; gæt aldrig et år. Samme navn igen retter datoen.",
        _obj({"items": {"type": "array", "items": _obj(
            {"name": {"type": "string"}, "date": {"type": "string"},
             "remind_days_before": {"type": "integer", "description": "Kun hvis brugeren sagde det (0 = på dagen)"}},
            ["name", "date"])}}, ["items"]),
        "app.modules.privat.chat:tool_add_birthdays"),
        AddonTool(
            "list_birthdays",
            "Vis de kommende fødselsdage (de næste 45 dage, ellers den næste).",
            _obj({}), "app.modules.privat.chat:tool_list_birthdays"),
        AddonTool(
            "remove_birthday",
            "Fjern en gemt fødselsdag (navnet som brugeren skrev det).",
            _obj({"name": {"type": "string"}}, ["name"]), "app.modules.privat.chat:tool_remove_birthday")),
))

register(Addon(
    key="madplan", name="Madplan", tagline="Ugens aftensmad – og indkøbslisten følger med",
    needs=("Hvor mange I er", "Det, I ikke spiser"),
    description="Peter laver en madplan for ugen ud fra det, I kan lide, og skriver indkøbslisten til den.",
    icon="utensils", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Sig hvor mange I er, og hvad I kan lide, så foreslår Peter aftensmad for ugen – med ingredienser til hver "
         "ret. Siger du ja, bliver mængderne regnet om til jeres antal og lagt sammen på én indkøbsliste, du kan dele "
         "med husstanden.",
    example="«Lav en madplan for næste uge – vi er fire, og børnene spiser ikke fisk»",
    steps=("Fortæl Peter, hvor mange I er, og hvad I ikke spiser",
           "Få et forslag til ugen og ret det, der ikke passer",
           "Sig ja – indkøbslisten laves automatisk"),
    included_in=("plus", "familie"),
    permissions=("Gemmer jeres madvaner og allergier, som du selv skriver dem",), keywords=("madplan", "aftensmad"),
    tools=(AddonTool(
        "save_food_preferences",
        "Gem husstandens madvaner, som brugeren selv har skrevet dem: antal personer, hvad de ikke spiser (allergier, "
        "fx fisk eller nødder) og hvad de kan lide.",
        _obj({"people": {"type": "integer"}, "avoid": {"type": "string"}, "likes": {"type": "string"}}),
        "app.modules.privat.chat:tool_save_food_preferences"),
        AddonTool(
            "get_food_preferences", "Hent husstandens gemte madvaner, før du foreslår en madplan.", _obj({}),
            "app.modules.privat.chat:tool_get_food_preferences"),
        AddonTool(
            "save_meal_plan",
            "Gem en madplan, når brugeren har sagt ja til dit forslag (foreslå den først i tekst). days: én pr. dag med "
            "retten, servings (ALTID: hvor mange personer netop dine mængder er til – også krydderier, smør og grønt) og ingredienserne med mængde og enhed først (fx "
            "«500 g hakket oksekød», «1 dåse hakkede tomater», «2 løg»). people: hvor mange planen er til (brugerens "
            "tal, ellers husstandens) – mængderne regnes om og lægges sammen på indkøbslisten. Respekter altid det, "
            "husstanden ikke spiser. shopping_list: lav indkøbslisten (standard ja).",
            _obj({"title": {"type": "string", "description": "Fx «Madplan uge 46»"},
                  "people": {"type": "integer"},
                  "days": {"type": "array", "items": _obj(
                      {"day": {"type": "string"}, "dish": {"type": "string"}, "servings": {"type": "integer"},
                       "ingredients": {"type": "array", "items": {"type": "string"}}}, ["dish", "servings"])},
                  "shopping_list": {"type": "boolean"}}, ["days"]),
            "app.modules.privat.chat:tool_save_meal_plan")),
))

register(Addon(
    key="bil-og-syn", name="Bil & syn", tagline="Syn, service og dæk – Peter holder styr på bilen",
    needs=("Nummerpladen", "Datoen for næste syn"),
    description="Peter husker, hvornår bilen skal til syn og service, og ringer til værkstedet og aftaler en tid, når det er ved at være tid.",
    icon="car", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Fortæl Peter, hvornår bilen skal til syn og service. Han minder dig om det i god tid og om skift til "
         "vinterdæk – og kan ringe til dit værksted og aftale tiden for dig.",
    example="«Bilen skal til syn i maj – find en tid hos mit værksted i uge 18»",
    steps=("Sig nummerpladen og datoen for næste syn til Peter", "Gem dit værksted (navn og nummer)",
           "Peter minder dig om syn og service og aftaler tiden, når du siger ja"),
    included_in=("plus", "familie"),
    permissions=("Gemmer nummerplade og datoer for syn og service, som du selv skriver dem",
                 "Ringer til dit værksted, når du har godkendt det"),
    keywords=("bil", "syn", "værksted", "dæk"),
    requires=("ring-for-mig",),
    tools=(AddonTool(
        "save_car",
        "Gem bilens oplysninger, som brugeren selv har skrevet dem: nummerplade, næste syn og service (YYYY-MM-DD) og om "
        "brugeren vil mindes om dækskifte. Slå aldrig noget op og gæt aldrig en dato.",
        _obj({"plate": {"type": "string"}, "inspection_due": {"type": "string"}, "service_due": {"type": "string"},
              "tire_reminders": {"type": "boolean"}}),
        "app.modules.privat.chat:tool_save_car"),
        AddonTool(
            "save_workshop", "Gem brugerens værksted: navn og det nummer, brugeren selv har skrevet.",
            _obj({"name": {"type": "string"}, "phone": {"type": "string"}}, ["name", "phone"]),
            "app.modules.privat.chat:tool_save_workshop"),
        AddonTool(
            "book_workshop",
            "Foreslå et opkald til det gemte værksted for at booke syn, service eller dækskifte. Der ringes ALDRIG før "
            "brugeren godkender. window: hvornår brugeren kan.",
            _obj({"purpose": {"type": "string"}, "window": {"type": "string"}}, ["purpose"]),
            "app.modules.privat.chat:tool_book_workshop"),
        AddonTool("car_status", "Vis de gemte oplysninger om bilen.", _obj({}), "app.modules.privat.chat:tool_car_status")),
))

register(Addon(
    key="regninger", name="Regninger", tagline="Bliv mindet om regninger, før de forfalder",
    needs=("Navn, beløb og forfaldsdag",),
    description="Peter husker faste regninger og abonnementer og minder dig om dem, før de skal betales – så du undgår rykkere.",
    icon="receipt", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Fortæl Peter om dine faste regninger – husleje, forsikring, streaming – og hvornår de forfalder. Han "
         "minder dig om dem i tide og viser dig månedens overblik. Peter betaler aldrig noget selv.",
    example="«Mind mig om bilforsikringen den 1. hver måned – den er 640 kr.»",
    steps=("Sig regningerne og deres dato til Peter", "Vælg hvor mange dage før, du vil have besked",
           "Se månedens regninger samlet i appen – eller spørg Peter"),
    included_in=("plus", "familie"),
    permissions=("Gemmer regningernes navn, beløb og dato, som du selv skriver dem", "Har aldrig adgang til din bank"),
    keywords=("regning", "regninger", "forfalder"),
    tools=(AddonTool(
        "add_bills",
        "Gem en eller flere faste regninger, brugeren har fortalt om. Peter betaler ALDRIG selv. Send due_day (dag i "
        "måneden, fx 1) eller due_date (næste forfaldsdato, YYYY-MM-DD), amount kun hvis brugeren sagde beløbet, og "
        "frequency: monthly | quarterly | half_yearly | yearly | once. Samme navn igen retter regningen.",
        _obj({"items": {"type": "array", "items": _obj(
            {"name": {"type": "string"}, "amount": {"type": "string", "description": "Fx «640 kr.»"},
             "frequency": {"type": "string", "enum": ["monthly", "quarterly", "half_yearly", "yearly", "once"]},
             "due_day": {"type": "integer"}, "due_date": {"type": "string"},
             "remind_days_before": {"type": "integer", "description": "Kun hvis brugeren sagde det"}},
            ["name"])}}, ["items"]),
        "app.modules.privat.chat:tool_add_bills"),
        AddonTool("bills_overview", "Vis månedens regninger med datoer og samlet beløb.", _obj({}),
                  "app.modules.privat.chat:tool_bills_overview"),
        AddonTool("remove_bill", "Fjern en gemt regning (navnet som brugeren skrev det).",
                  _obj({"name": {"type": "string"}}, ["name"]), "app.modules.privat.chat:tool_remove_bill")),
))

register(Addon(
    key="laege-og-tandlaege", name="Læge & tandlæge", tagline="Tider hos læge og tandlæge – uden at hænge i telefonen",
    needs=("Klinikkens navn og nummer",),
    description="Peter ringer til lægen eller tandlægen og booker tiden for dig, og minder dig om det årlige tandeftersyn.",
    icon="heart", category="aftaler", price_text="Med i Plus og Familie", pricing="free",
    what="Sig hvad det drejer sig om, og hvornår du kan, så ringer Peter til din læge eller tandlæge, når de åbner, "
         "og aftaler en tid. Han fortæller aldrig mere, end du har sagt god for.",
    example="«Book et tandeftersyn hos min tandlæge – helst en morgen i næste måned»",
    steps=("Gem din læge og tandlæge (navn og nummer)", "Sig til Peter, hvad du skal, og hvornår du kan",
           "Godkend opkaldet – Peter ringer og lægger tiden i din kalender"),
    included_in=("plus", "familie"),
    permissions=("Ringer til din læge eller tandlæge, når du har godkendt det",
                 "Siger kun dit navn og det, du selv har skrevet", "Gemmer kun klinikkens navn og nummer – ikke helbredsoplysninger"),
    requires=("ring-for-mig",),
    tools=(AddonTool(
        "save_health_contact",
        "Gem brugerens læge eller tandlæge: kind (laege | tandlaege), navn og det nummer, brugeren selv har skrevet.",
        _obj({"kind": {"type": "string", "enum": ["laege", "tandlaege"]}, "name": {"type": "string"},
              "phone": {"type": "string"}}, ["kind", "name", "phone"]),
        "app.modules.privat.chat:tool_save_health_contact"),
        AddonTool(
            "book_health_appointment",
            "Foreslå et opkald til brugerens gemte læge eller tandlæge for at få en tid. Der ringes ALDRIG før brugeren "
            "godkender. purpose: kun det, brugeren selv har skrevet (fx «tandeftersyn»); window: hvornår brugeren kan. "
            "Til en årlig påmindelse bruger du create_reminder.",
            _obj({"kind": {"type": "string", "enum": ["laege", "tandlaege"]}, "purpose": {"type": "string"},
                  "window": {"type": "string"}}, ["kind", "purpose"]),
            "app.modules.privat.chat:tool_book_health_appointment")),
    keywords=("læge", "tandlæge", "tandeftersyn", "lægetid"),
))

register(Addon(
    key="pakkeliste", name="Pakkeliste", tagline="Pakkelister til rejser og ture, der kan genbruges",
    description="Peter laver en pakkeliste til turen – ud fra vejret, hvor længe I er væk, og hvem der skal med – og husker den til næste gang.",
    icon="suitcase", category="lister", price_text="Med i Plus og Familie", pricing="free",
    what="Sig hvor I skal hen, hvor længe, og hvem der skal med, så skriver Peter en pakkeliste, som I krydser af. "
         "Næste gang starter han fra den, I brugte sidst.",
    example="«Lav en pakkeliste til en uge i sommerhus med to børn»",
    steps=("Fortæl Peter om turen – sted, længde og hvem", "Ret listen til, og del den med rejsefællerne",
           "Kryds af, mens I pakker"),
    included_in=("plus", "familie"),
    permissions=("Gemmer dine pakkelister til næste tur",), keywords=("pakkeliste", "pakke til", "rejse", "ferie"),
    tools=(AddonTool(
        "create_packing_list",
        "Lav en pakkeliste til en tur: trip er turen (fx «uge i sommerhus»), items de ting, der skal med – tilpasset "
        "sted, længde, årstid og hvem der skal med. Vil brugeren starte fra sidst, så brug reuse_packing_list.",
        _obj({"trip": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}}, ["trip", "items"]),
        "app.modules.privat.chat:tool_create_packing_list"),
        AddonTool(
            "reuse_packing_list",
            "Lav en ny pakkeliste ud fra den, brugeren brugte sidst (alt er ikke krydset af igen).",
            _obj({"trip": {"type": "string", "description": "Den nye tur, hvis brugeren nævnte den"}}),
            "app.modules.privat.chat:tool_reuse_packing_list")),
))

register(Addon(
    key="rejser", name="Rejser", tagline="Rejseforslag med rigtige priser – og book hos udbyderen",
    description="Peter finder rejser ud fra budget, antal personer, hvor I vil hen og hvilken slags rejse, med priser "
                "direkte fra flyselskaber og rejsesider.",
    icon="plane", category="aftaler", price_text="Med i Plus og Familie", pricing="free",
    needs_setting=("duffel_access_token", "travelpayouts_token"),
    needs_check="app.modules.privat.travel:configured",  # Travelpayouts needs the token AND the marker
    what="Sig hvor I rejser fra, hvor mange I er, hvad det må koste, og hvad slags rejse I drømmer om – eller hvor I "
         "vil hen. Peter finder flyrejser med rigtige priser, billigst først, og med «Book» bestiller du hos udbyderen.",
    example="«Find en strandferie i februar til to voksne og to børn fra Billund for højst 12.000 kr.»",
    steps=("Fortæl Peter om rejsen – eller udfyld søgningen i appen",
           "Se forslagene med priser for hele selskabet, billigst først",
           "Tryk «Book» – du bestiller og betaler hos udbyderen"),
    included_in=("plus", "familie"),
    permissions=("Sender kun rejsens fra, til, datoer og antal personer til prisudbyderne",
                 "Booker og betaler aldrig noget i Dialogbot"),
    keywords=("rejse", "rejser", "ferie", "fly", "flybillet", "storbyferie", "strandferie", "skiferie"),
    tools=(AddonTool(
        "search_trips",
        "Find flyrejser med RIGTIGE priser (fra Duffel/Travelpayouts – opfind aldrig en pris). origin og destinations er "
        "IATA-lufthavnskoder (fx CPH, BLL, AAL; BCN, LIS, CDG). Nævner brugeren ikke et sted, men en rejsetype "
        "(strand, storby, ski, natur …), så vælg selv 3-5 passende destinationer, der kan nås fra origin. depart_date "
        "(YYYY-MM-DD) eller month (YYYY-MM), nights, adults, children, budget_dkk (samlet for alle) og direct_only kun "
        "hvis brugeren sagde det. Spørg kort, hvis hvorfra eller hvornår mangler.",
        _obj({"origin": {"type": "string"}, "destinations": {"type": "array", "items": {"type": "string"}},
              "depart_date": {"type": "string"}, "month": {"type": "string"}, "nights": {"type": "integer"},
              "adults": {"type": "integer"}, "children": {"type": "integer"}, "budget_dkk": {"type": "integer"},
              "trip_type": {"type": "string"}, "direct_only": {"type": "boolean"}, "wishes": {"type": "string"}},
             ["origin", "destinations"]),
        "app.modules.privat.chat:tool_search_trips"),),
))

# --------------------------------------------------------------------------- household apps (app_kit.py)
# Revenue is designed in: leads to businesses (Håndværker & tilbud, and Flytning/Hus & vedligehold through it), disclosed
# partner links (brand.offer, «Annonce»), and Dialogbot's name on every call, letter, invitation and summary
# (brand.footer). Fælles udgifter and Fest & invitationer are free: every summary and invitation reaches new people.

_H = "app.modules.privat.chat:"

register(Addon(
    key="abonnementer", name="Abonnementer & opsigelse", tagline="Se hvad I betaler for – og opsig det, I ikke bruger",
    description="Peter holder styr på streaming, mobil, internet, fitness og forsikringer: hvad det koster, hvornår "
                "bindingen slutter – og skriver opsigelsen eller ringer, når du vil ud.",
    icon="repeat", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Fortæl Peter, hvad I betaler for. Han viser, hvad det koster om måneden og året, minder dig om den sidste "
         "dag at opsige, før en binding fornyes – og skriver opsigelsen eller ringer for dig, når du siger til.",
    example="«Jeg har Netflix til 139 kr. om måneden og Telia til 199 kr. med binding til 1. marts»",
    steps=("Sig dine abonnementer og hvad de koster", "Peter minder dig om den sidste dag at opsige",
           "Sig «opsig Netflix» – du får opsigelsen klar til at sende, eller Peter ringer, når du godkender"),
    included_in=("plus", "familie"),
    permissions=("Gemmer abonnementer, priser og datoer, som du selv skriver dem", "Har aldrig adgang til din bank",
                 "Opsiger kun, når du selv sender opsigelsen eller godkender opkaldet"),
    keywords=("abonnement", "abonnementer", "opsig", "opsige", "binding", "streaming"),
    requires=("ring-for-mig",),
    tools=(AddonTool(
        "add_subscriptions",
        "Gem abonnementer, som brugeren selv har nævnt: name, price (fx «139 kr.»), period monthly/quarterly/yearly, "
        "category (streaming, mobil, internet, el, forsikring, fitness, avis, andet), binding_until og renews_on "
        "(YYYY-MM-DD), notice_days (opsigelsesvarsel i dage). Gæt aldrig en pris eller dato.",
        _obj({"items": {"type": "array", "items": _obj({
            "name": {"type": "string"}, "price": {"type": "string"},
            "period": {"type": "string", "enum": ["monthly", "quarterly", "yearly"]}, "category": {"type": "string"},
            "binding_until": {"type": "string"}, "renews_on": {"type": "string"}, "notice_days": {"type": "integer"}},
            ["name"])}}, ["items"]),
        _H + "tool_add_subscriptions"),
        AddonTool("subscriptions_overview", "Vis brugerens abonnementer og hvad de koster i alt.", _obj({}),
                  _H + "tool_subscriptions_overview"),
        AddonTool("remove_subscription", "Fjern et abonnement fra oversigten (ikke en opsigelse).",
                  _obj({"name": {"type": "string"}}, ["name"]), _H + "tool_remove_subscription"),
        AddonTool(
            "cancel_subscription",
            "Hjælp med at opsige et abonnement. how=letter: skriv opsigelsen, brugeren selv sender. how=call: foreslå "
            "et opkald til firmaet (kun med et nummer, brugeren selv har skrevet) – der ringes ALDRIG før brugeren "
            "godkender. customer_no kun hvis brugeren skrev det.",
            _obj({"name": {"type": "string"}, "how": {"type": "string", "enum": ["letter", "call"]},
                  "phone": {"type": "string"}, "customer_no": {"type": "string"}}, ["name"]),
            _H + "tool_cancel_subscription")),
))

register(Addon(
    key="haandvaerker", name="Håndværker & tilbud", tagline="Peter henter 3 tilbud – du vælger",
    description="Sig hvad der skal laves, og hvor. Peter finder tre lokale håndværkere, ringer og spørger om pris og "
                "hvornår de kan – og viser svarene side om side.",
    icon="wrench", category="opkald", price_text="Med i Plus og Familie – opkald som i Ring for mig", pricing="free",
    what="Peter finder op til tre håndværkere i nærheden, ringer og spørger om pris og hvornår de kan, og viser "
         "svarene side om side. Du vælger – så ringer Peter og siger ja tak. Han siger aldrig ja til en pris selv.",
    example="«Find 3 malere i Aarhus og hent tilbud på at male stuen»",
    steps=("Sig hvad der skal laves, og hvor", "Godkend opkaldene – Peter spørger om pris og tid",
           "Se tilbuddene side om side og vælg – Peter siger ja tak for dig"),
    included_in=("plus", "familie"),
    permissions=("Ringer kun til håndværkere, du har godkendt", "Siger dit navn og opgaven – aldrig din adresse",
                 "Siger aldrig ja til en pris eller en aftale"),
    keywords=("håndværker", "tilbud", "tømrer", "maler", "elektriker", "vvs", "murer", "flyttefirma", "gartner",
              "rengøring"),
    requires=("ring-for-mig",),
    tools=(AddonTool(
        "request_quotes",
        "Find op til 3 lokale virksomheder og foreslå et opkald til hver for at få et tilbud. job: opgaven med brugerens "
        "egne ord (fx «male stuen, ca. 30 m²»), trade: søgeord for virksomheden (fx «maler», «flyttefirma»), city: by "
        "eller postnummer. address: KUN hvis brugeren selv har skrevet adressen og sagt, at håndværkerne må få den (til "
        "en besigtigelse). Der ringes ALDRIG før brugeren godkender hvert opkald.",
        _obj({"job": {"type": "string"}, "trade": {"type": "string"}, "city": {"type": "string"},
              "window": {"type": "string"}, "address": {"type": "string"}}, ["job", "trade"]),
        _H + "tool_request_quotes"),
        AddonTool("compare_quotes", "Vis tilbuddene side om side (seneste opgave, eller den med job).",
                  _obj({"job": {"type": "string"}}), _H + "tool_compare_quotes"),
        AddonTool("choose_quote",
                  "Brugeren vælger en af virksomhederne: gem valget og foreslå et opkald, hvor Peter siger ja tak og "
                  "beder dem kontakte brugeren. Der ringes ALDRIG før brugeren godkender.",
                  _obj({"business": {"type": "string"}, "job": {"type": "string"}}, ["business"]),
                  _H + "tool_choose_quote")),
))

register(Addon(
    key="faelles-udgifter", name="Fælles udgifter", tagline="Hvem lagde ud – og hvem skylder hvem",
    description="Til ferien, sommerhuset eller bofællesskabet: skriv hvem der betalte hvad, og Peter regner ud, hvem "
                "der skal betale hvem – med færrest mulige overførsler.",
    icon="coin", category="lister", price_text="Gratis", pricing="free",
    what="Sig hvem der lagde ud for hvad, og Peter regner ud, hvem der skylder hvem – med færrest mulige "
         "overførsler. Du får en opgørelse, du kan sende til de andre. Peter flytter aldrig penge.",
    example="«Jeg betalte 1.200 kr. for mad i sommerhuset – vi er Anna, Bo og mig»",
    steps=("Sig hvem der er med, og hvem der betalte hvad", "Se hvem der skylder hvem",
           "Send opgørelsen til de andre – de betaler med MobilePay"),
    permissions=("Gemmer fornavne og beløb, som du selv skriver dem", "Flytter aldrig penge"),
    keywords=("lagde ud", "skylder", "dele regningen", "fælles udgifter", "udlæg", "betalte"),
    tools=(AddonTool(
        "add_expense",
        "Gem en udgift: group (fx «Sommerhus»), paid_by (fornavn, eller «mig»), amount (fx «1.200 kr.»), text (hvad), "
        "among (hvem den deles mellem – tom = alle i gruppen), people (alle i gruppen, hvis brugeren nævnte dem).",
        _obj({"group": {"type": "string"}, "paid_by": {"type": "string"}, "amount": {"type": "string"},
              "text": {"type": "string"}, "among": _STR_LIST, "people": _STR_LIST}, ["amount"]),
        _H + "tool_add_expense"),
        AddonTool("expenses_balance", "Vis hvem der skylder hvem i en gruppe. share=true: en opgørelse til at sende.",
                  _obj({"group": {"type": "string"}, "share": {"type": "boolean"}}), _H + "tool_expenses_balance")),
))

register(Addon(
    key="garanti", name="Garanti & kvitteringer", tagline="Husk reklamationsretten – og få hjælp, når noget går i stykker",
    description="Peter husker, hvad du har købt og hvor, og hvornår reklamationsretten udløber – og skriver "
                "reklamationen til butikken, når noget går i stykker.",
    icon="shield", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Fortæl Peter, når du køber noget dyrt. Han husker butik og dato, minder dig om det, før de 2 års "
         "reklamationsret udløber, og skriver reklamationen, når noget går i stykker. Tilføj gerne et foto af "
         "kvitteringen ved tingen.",
    example="«Jeg købte en vaskemaskine i Elgiganten den 3. maj til 4.999 kr.»",
    steps=("Sig hvad du købte, hvor og hvornår", "Peter minder dig om det, før reklamationsretten udløber",
           "Går noget i stykker, skriver Peter reklamationen til butikken"),
    included_in=("plus", "familie"),
    # PC-APP-01: the app DOES keep a receipt photo when the user adds one (POST apps/garanti/items/{id}/photo).
    permissions=("Gemmer ting, butik, dato og pris, som du selv skriver dem",
                 "Gemmer et foto af kvitteringen, hvis du selv tilføjer ét – det slettes med tingen eller appens data"),
    keywords=("garanti", "kvittering", "reklamation", "reklamere", "gået i stykker", "virker ikke"),
    tools=(AddonTool(
        "add_purchase",
        "Gem et køb: product, shop, bought (YYYY-MM-DD), price, warranty_years (kun en ekstra garanti, brugeren nævner).",
        _obj({"product": {"type": "string"}, "shop": {"type": "string"}, "bought": {"type": "string"},
              "price": {"type": "string"}, "warranty_years": {"type": "integer"}}, ["product", "bought"]),
        _H + "tool_add_purchase"),
        AddonTool("purchases_overview", "Vis de gemte køb og hvor længe der er reklamationsret.", _obj({}),
                  _H + "tool_purchases_overview"),
        AddonTool("write_complaint",
                  "Skriv en reklamation til butikken om en gemt ting: product og problem (fejlen med brugerens ord). "
                  "remedy kun hvis brugeren har sagt, hvad de vil have: repair, replace, refund eller discount.",
                  _obj({"product": {"type": "string"}, "problem": {"type": "string"},
                        "remedy": {"type": "string", "enum": ["repair", "replace", "refund", "discount"]}},
                       ["product", "problem"]),
                  _H + "tool_write_complaint")),
))

register(Addon(
    key="fest", name="Fest & invitationer", tagline="Gæsteliste, svar, hvem tager hvad med – og allergier",
    description="Planlæg festen med Peter: han skriver invitationen, holder styr på hvem der kommer, hvem der tager "
                "hvad med, og hvem der ikke tåler hvad.",
    icon="balloon", category="lister", price_text="Gratis", pricing="free",
    what="Sig hvad det er for en fest, hvornår og hvem der skal med. Peter skriver invitationen, holder styr på "
         "svarene, hvem der tager hvad med og allergier – og minder dig om dem, der ikke har svaret.",
    example="«Lav en fest: Idas 10-års fødselsdag den 6. marts kl. 14 med Emma, Noah og Alma»",
    steps=("Sig festen, datoen og gæsterne", "Send invitationen, Peter har skrevet",
           "Fortæl Peter svarene – han holder styr på resten"),
    permissions=("Gemmer gæsternes fornavne, svar og allergier, som du selv skriver dem",
                 "Sender intet – du sender selv invitationen"),
    keywords=("fest", "invitation", "invitere", "gæster", "gæsteliste", "fødselsdagsfest", "kommer"),
    tools=(AddonTool(
        "save_party",
        "Opret eller ret en fest: title, date (YYYY-MM-DD), time (fx 14:00), place, guests (fornavne).",
        _obj({"title": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"},
              "place": {"type": "string"}, "guests": _STR_LIST}, ["title"]),
        _H + "tool_save_party"),
        AddonTool("update_guest",
                  "Ret en gæst: name, status (yes/no/maybe), bring (hvad de tager med), diet (allergier/kost). party: "
                  "festens titel (tom = den nyeste).",
                  _obj({"party": {"type": "string"}, "name": {"type": "string"},
                        "status": {"type": "string", "enum": ["yes", "no", "maybe"]}, "bring": {"type": "string"},
                        "diet": {"type": "string"}}, ["name"]),
                  _H + "tool_update_guest"),
        AddonTool("party_status",
                  "Vis festen: hvem kommer, hvem tager hvad med, allergier. Vil brugeren have maden til festen, så brug "
                  "save_meal_plan (appen Madplan) med people = antal, der kommer, og respektér allergierne.",
                  _obj({"party": {"type": "string"}}), _H + "tool_party_status"),
        AddonTool("write_invitation", "Skriv invitationen til festen, som brugeren selv sender. note: ekstra tekst.",
                  _obj({"party": {"type": "string"}, "note": {"type": "string"}}), _H + "tool_write_invitation")),
))

register(Addon(
    key="flytning", name="Flytning", tagline="Flyttetjeklisten med datoer – og hjælp til opkaldene",
    description="Sig hvornår I flytter, og Peter laver tjeklisten med datoer: opsigelse, el, internet, forsikring, "
                "flyttefirma og adresseændring – og minder dig om hvert punkt i tide.",
    icon="truck", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Sig flyttedagen, og Peter laver tjeklisten med datoer – fra opsigelse og flyttefirma til el, internet og "
         "adresseændring – og minder dig om hvert punkt. Flyttefirmaer kan han hente tilbud fra.",
    example="«Vi flytter til Odense den 1. april»",
    steps=("Sig flyttedagen og hvor I flytter hen", "Få tjeklisten med datoer – del den med dem, I flytter med",
           "Peter minder dig om hvert punkt og kan hente tilbud fra flyttefirmaer"),
    included_in=("plus", "familie"),
    permissions=("Gemmer flyttedagen og byen, som du selv skriver dem",
                 "Melder aldrig flytning for dig – det gør du selv på borger.dk"),
    keywords=("flytte", "flytning", "flytter", "flyttedag", "ny adresse"),
    tools=(AddonTool(
        "plan_move", "Lav flyttetjeklisten: moving_day (YYYY-MM-DD) og to (by/adresse, som brugeren skrev).",
        _obj({"moving_day": {"type": "string"}, "to": {"type": "string"}}, ["moving_day"]),
        _H + "tool_plan_move"),
        AddonTool("moving_status", "Vis flytningen og hvad der mangler.", _obj({}), _H + "tool_moving_status")),
))

register(Addon(
    key="kaeledyr", name="Kæledyr", tagline="Dyrlæge, vaccinationer, ormekur og forsikring",
    description="Peter husker vaccinationer, ormekur, loppemiddel og forsikring for jeres dyr – og ringer til "
                "dyrlægen og finder en tid, når du siger til.",
    icon="paw", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Fortæl Peter om jeres dyr og datoerne. Han minder dig om vaccination, ormekur, loppemiddel og forsikring – "
         "og kan ringe til dyrlægen og finde en tid, når du godkender.",
    example="«Vores hund Bella skal vaccineres 1. marts og have ormekur hver 3. måned»",
    steps=("Sig dyrets navn og datoerne", "Gem dyrlægen (navn og nummer)",
           "Peter minder dig om det – og booker dyrlægen, når du siger ja"),
    included_in=("plus", "familie"),
    permissions=("Gemmer dyrenes navne og datoer, som du selv skriver dem",
                 "Ringer til din dyrlæge, når du har godkendt det"),
    keywords=("hund", "kat", "kæledyr", "dyrlæge", "ormekur", "loppe", "vaccin"),
    requires=("ring-for-mig",),
    tools=(AddonTool(
        "save_pet",
        "Gem et dyr: name, kind (hund, kat …), vaccination_due og insurance_renews (YYYY-MM-DD), worming_every_months og "
        "flea_every_months, last_treatment (YYYY-MM-DD). Gæt aldrig en dato.",
        _obj({"name": {"type": "string"}, "kind": {"type": "string"}, "vaccination_due": {"type": "string"},
              "insurance_renews": {"type": "string"}, "worming_every_months": {"type": "integer"},
              "flea_every_months": {"type": "integer"}, "last_treatment": {"type": "string"},
              "chip": {"type": "string", "description": "Chipnummeret (15 cifre), kun som brugeren skrev det"}}, ["name"]),
        _H + "tool_save_pet"),
        AddonTool("save_vet", "Gem dyrlægen: navn og det nummer, brugeren selv har skrevet.",
                  _obj({"name": {"type": "string"}, "phone": {"type": "string"}}, ["name", "phone"]),
                  _H + "tool_save_vet"),
        AddonTool("book_vet",
                  "Foreslå et opkald til den gemte dyrlæge for at booke en tid. Der ringes ALDRIG før brugeren "
                  "godkender. pet: dyrets navn, purpose: hvad, window: hvornår brugeren kan.",
                  _obj({"pet": {"type": "string"}, "purpose": {"type": "string"}, "window": {"type": "string"}},
                       ["purpose"]),
                  _H + "tool_book_vet"),
        AddonTool("pets_status", "Vis dyrene og deres datoer.", _obj({}), _H + "tool_pets_status")),
))

register(Addon(
    key="hus-og-vedligehold", name="Hus & vedligehold", tagline="Røgalarm, filtre, tagrender og fyr – til tiden",
    description="Peter husker de små faste opgaver i hjemmet – røgalarmen, emhættefilteret, tagrenderne, service på "
                "fyret – og finder en håndværker, når der skal en til.",
    icon="home", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Vælg de faste opgaver i hjemmet – eller tilføj dine egne. Peter minder dig om dem til tiden, og når der "
         "skal en håndværker til, henter han tilbud.",
    example="«Tilføj alle de faste opgaver i huset»",
    steps=("Vælg opgaverne, eller sig dine egne og hvor tit", "Peter minder dig om dem til tiden",
           "Sig «færdig» – så rykker opgaven til næste gang"),
    included_in=("plus", "familie"),
    permissions=("Gemmer kun de opgaver og datoer, du vælger",),
    keywords=("røgalarm", "tagrende", "emhætte", "vedligehold", "fyr", "varmepumpe", "skorsten"),
    tools=(AddonTool(
        "add_home_tasks",
        "Tilføj faste opgaver i hjemmet. names: standardopgaver (fx «røgalarm», «tagrender», «fyr», eller «alle» – så "
        "vælges dem, der passer til boligen). custom + every_months (+ next_due YYYY-MM-DD): en egen opgave. Boligen, "
        "hvis brugeren har fortalt om den: home (hus/lejlighed/rækkehus/sommerhus), heating (fyr/varmepumpe/fjernvarme/"
        "elvarme), chimney (true/false).",
        _obj({"names": _STR_LIST, "custom": {"type": "string"}, "every_months": {"type": "integer"},
              "next_due": {"type": "string"}, "home": {"type": "string"}, "heating": {"type": "string"},
              "chimney": {"type": "boolean"}}),
        _H + "tool_add_home_tasks"),
        AddonTool("home_task_done", "Brugeren har gjort en opgave: ryk den til næste gang.",
                  _obj({"name": {"type": "string"}}, ["name"]), _H + "tool_home_task_done"),
        AddonTool("home_status", "Vis hjemmets faste opgaver og hvornår de skal gøres.", _obj({}),
                  _H + "tool_home_status")),
))

register(Addon(
    key="fitness-og-sundhed", name="Fitness & sundhed", tagline="Ugens træning, en enkel log – og et puf på dagen",
    description="Sig hvornår du vil træne, og hvad dit mål er. Peter minder dig om det på dagen, noterer hvad du har "
                "nået og viser ugen – og kan ringe og booke et hold, en PT eller fysioterapeuten.",
    icon="dumbbell", category="hverdag", price_text="Med i Plus og Familie", pricing="free",
    what="Fortæl Peter dit mål og hvornår du vil træne. Han minder dig om det på dagen, noterer det, du har nået, og "
         "viser hver mandag, hvordan ugen gik. Han kan også ringe og booke et hold eller en tid, når du godkender.",
    example="«Jeg vil løbe tirsdag og torsdag kl. 17 og styrketræne lørdag – målet er 5 km i maj»",
    steps=("Sig dit mål og dine træningsdage", "Få et puf på dagen – sig «færdig med løb», så noterer Peter det",
           "Se hver mandag, hvordan ugen gik"),
    included_in=("plus", "familie"),
    permissions=("Gemmer dit mål, din træningsplan og hvad du har trænet",
                 "Gemmer aldrig vægt, sygdom, skader, medicin eller andre helbredsoplysninger"),
    keywords=("træne", "træning", "løbe", "løb", "fitness", "motion", "styrketræning", "yoga", "cykle"),
    tools=(AddonTool(
        "plan_workouts",
        "Gem træningsplanen: workouts med day (mandag…søndag), activity, time (fx 17:00) og minutes. goal: brugerens mål "
        "med egne ord. replace=true erstatter hele planen. Gem ALDRIG vægt, sygdom, skader, medicin eller andre "
        "helbredsoplysninger – heller ikke hvis brugeren nævner dem.",
        _obj({"workouts": {"type": "array", "items": _obj({"day": {"type": "string"}, "activity": {"type": "string"},
                                                           "time": {"type": "string"}, "minutes": {"type": "integer"}},
                                                          ["day", "activity"])},
              "goal": {"type": "string"}, "replace": {"type": "boolean"}}),
        _H + "tool_plan_workouts"),
        AddonTool("log_workout", "Notér en træning, brugeren har lavet: activity, minutes, date (YYYY-MM-DD, standard i dag).",
                  _obj({"activity": {"type": "string"}, "minutes": {"type": "integer"}, "date": {"type": "string"}},
                       ["activity"]),
                  _H + "tool_log_workout"),
        AddonTool("fitness_status", "Vis målet, ugens træning og planen.", _obj({}), _H + "tool_fitness_status")),
))

# Which add-on a shared list needs, per share mode.
SHARE_MODE_ADDON = {"group": "delte-lister", "wishlist": "oenskelister"}


# --------------------------------------------------------------------------- state

def enabled_keys(db: OrmSession, ws_id: uuid.UUID) -> set[str]:
    """The apps that RUN: switched on, live, and – for an app that needs a plan – the plan still applies. Decision
    Fürster 2026-11-10 (PC-ENT-02/03): when the plan lapses (period over after cancelling, trial ended, unpaid) such an
    app stops – no tools, no reminders, no scheduled calls – but stays switched on with its data kept, and runs again
    the moment the plan is back. Free apps are never affected."""
    keys = set(db.scalars(select(PrivateAddonEnabled.key).where(PrivateAddonEnabled.workspace_id == ws_id)))
    keys = {k for k in keys if k in CATALOG and CATALOG[k].live_status != "coming_soon"}
    if any(_stops_without_plan(CATALOG[k]) for k in keys):
        from app.modules.privat import subscriptions

        ent = subscriptions.entitlements(db, ws_id)
        keys = {k for k in keys if not _stops_without_plan(CATALOG[k]) or subscriptions.covers(ent, CATALOG[k].included_in)}
    return keys


def _stops_without_plan(a: Addon) -> bool:
    """Needs a plan to RUN. Not the free apps, and not a pay-per-use app («Ring for mig»: without a plan each call
    reserves 3 credits – that path is the product, tests/test_privat.py credits path)."""
    return bool(a.included_in) and a.pricing != "credits"


def needs_plan_again(db: OrmSession, ws_id: uuid.UUID, key: str, ent: dict | None = None) -> bool:
    """Switched on, but stopped because its plan no longer applies (data kept; «Kræver plan»)."""
    a = CATALOG.get(key)
    if a is None or not _stops_without_plan(a) or db.get(PrivateAddonEnabled, (ws_id, key)) is None:
        return False
    return not included(db, ws_id, a, ent)


def running_rows(db: OrmSession, rows: list, key: str) -> list:
    """Worker jobs: keep only the rows (with a workspace_id) whose app runs for that workspace right now."""
    cache: dict = {}
    out = []
    for r in rows:
        ws = r.workspace_id
        if ws not in cache:
            cache[ws] = key in enabled_keys(db, ws)
        if cache[ws]:
            out.append(r)
    return out


def is_enabled(db: OrmSession, ws_id: uuid.UUID, key: str) -> bool:
    return key in enabled_keys(db, ws_id)


def require(db: OrmSession, ws_id: uuid.UUID, key: str) -> None:
    if not is_enabled(db, ws_id, key):
        a = CATALOG.get(key)
        if needs_plan_again(db, ws_id, key):
            names = [n for n in ("Plus", "Familie", "Basis") if n.lower() in a.included_in]
            raise Forbidden(f"«{a.name}» kræver {' eller '.join(names[:2]) if names else 'et abonnement'} – dine data "
                            "er gemt og kommer tilbage, når planen er aktiv igen", code="needs_plan",
                            extra={"addon": key, "plans": list(a.included_in)})
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
    """The shop card. Its texts say the name (and han/hun/den) the user gave the assistant."""
    from app.models import PrivateProfile
    from app.modules.privat import naming

    prof = db.get(PrivateProfile, ws_id)
    name, pron = naming.of(prof), naming.pronoun_of(prof)

    def p(x):
        return naming.personalize(x, name, pron)

    from app.modules.privat import app_status

    row = db.get(PrivateAddonEnabled, (ws_id, a.key))
    on = row is not None and a.live_status != "coming_soon"
    st = app_status.state(db, ws_id, a.key)
    return {"needs": p(list(a.needs)), "summary_line": app_status.summary_line(db, ws_id, a.key) if on else None,
            "setup": {"done": min(st.setup_done if st else 0, len(a.steps)), "total": len(a.steps)},
            "disabled_at": st.disabled_at.isoformat() if st and st.disabled_at and not on else None,
            "notify_requested": bool(st and st.notify_requested_at), "data_deletable": app_status.deletable(a.key),
            "key": a.key, "name": a.name, "tagline": p(a.tagline), "description": p(a.description), "icon": a.icon,
            "category": a.category, "price_text": a.price_text, "pricing": a.pricing,
            "monthly_price_minor": a.monthly_price_minor, "status": a.live_status, "permissions": p(list(a.permissions)),
            "requires": list(a.requires), "enabled": on, "enabled_at": row.enabled_at.isoformat() if on else None,
            "what": p(a.what), "example": p(a.example), "steps": p(list(a.steps)), "included_in": list(a.included_in),
            "included": included(db, ws_id, a, ent), "requires_plan": bool(a.included_in),
            # switched on, data kept, but stopped until the plan is back (PC-ENT-02/03) – the card says «Kræver plan»
            "needs_plan": bool(on and _stops_without_plan(a) and not included(db, ws_id, a, ent))}


def catalog_out(db: OrmSession, ws_id: uuid.UUID) -> list[dict]:
    from app.modules.privat import subscriptions

    ent = subscriptions.entitlements(db, ws_id)
    return [out(db, ws_id, a, ent) for a in CATALOG.values()]


def enable(db: OrmSession, ws_id: uuid.UUID, key: str) -> Addon:
    a = get(key)
    if a.live_status == "coming_soon":
        raise Conflict(f"«{a.name}» kommer snart", code="coming_soon", extra={"addon": key})
    from app.modules.privat import subscriptions

    ent = subscriptions.entitlements(db, ws_id)
    if not included(db, ws_id, a, ent):
        names = [n for n in ("Plus", "Familie", "Basis") if n.lower() in a.included_in]
        where = ' og '.join(names[:2]) if names else 'et abonnement'
        # Already in a trial or on a plan (e.g. Basis): «start 14 dage gratis» would be wrong – they need another
        # plan (F-UX-01).
        msg = (f"«{a.name}» er med i {where} – skift plan under Konto" if ent.get("entitled")
               else f"«{a.name}» er med i {where} – start 14 dage gratis eller vælg en plan")
        raise Conflict(msg, code="needs_plan", extra={"addon": key, "plans": list(a.included_in),
                                                      "upgrade": bool(ent.get("entitled"))})
    for dep in a.requires:
        if not is_enabled(db, ws_id, dep):
            enable(db, ws_id, dep)
    if db.get(PrivateAddonEnabled, (ws_id, key)) is None:
        db.add(PrivateAddonEnabled(workspace_id=ws_id, key=key, enabled_at=rules.now()))
        db.flush()
        from app.modules.privat import app_status

        app_status.on_enabled(db, ws_id, key)
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
        from app.modules.privat import app_status

        app_status.on_disabled(db, ws_id, key)
        if a.on_disable:
            _call(a.on_disable)(db, ws_id)
    return a


def enable_defaults(db: OrmSession, ws_id: uuid.UUID) -> None:
    """The default add-ons – those the account's rights allow. Called at account creation (the free tier gets the
    free ones) and again when the trial or a plan arrives from Stripe (then the plan's ones come on)."""
    for key in (k.strip() for k in get_settings().privat_default_addons.split(",")):
        if key in CATALOG and CATALOG[key].live_status != "coming_soon" and included(db, ws_id, CATALOG[key]):
            was_on = db.get(PrivateAddonEnabled, (ws_id, key)) is not None
            enable(db, ws_id, key)
            if not was_on:  # switched on for the user, not by them: no «Trin 1 af 3» prompt on Mine apps
                from app.modules.privat import app_status

                app_status.set_setup(db, ws_id, key, len(CATALOG[key].steps))


def tools_for(db: OrmSession, ws_id: uuid.UUID) -> list[AddonTool]:
    keys = enabled_keys(db, ws_id)
    return [t for a in CATALOG.values() if a.key in keys for t in a.tools]


def offerable(db: OrmSession, ws_id: uuid.UUID) -> list[Addon]:
    """Add-ons the user could switch on (available, not on): what the chat may offer instead of doing it."""
    keys = enabled_keys(db, ws_id)
    return [a for a in CATALOG.values() if a.live_status != "coming_soon" and a.key not in keys]


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
