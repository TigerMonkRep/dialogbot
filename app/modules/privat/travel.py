"""The Rejser app (step 1): trip ideas with REAL prices, and «Book» that hands the user over to the seller.

What the user gives: from where, where to (or a trip type, then the assistant picks destinations), dates or a flexible
month, nights, adults and children, a total budget, direct flights only. Prices come only from the providers:
- Duffel (api.duffel.com, `DUFFEL_ACCESS_TOKEN`): flight offers for the exact dates, total for all passengers.
- Travelpayouts / Aviasales (api.travelpayouts.com, `TRAVELPAYOUTS_TOKEN` + `TRAVELPAYOUTS_MARKER`): cached cheapest
  fares per route and month, with a booking link that carries Dialogbot's affiliate marker.
The app is «Kommer snart» until at least one is set. Nothing is booked or paid in Dialogbot in step 1: «Book» opens
the seller's own page. Booking inside Dialogbot (Duffel orders) is step 2, after the legal check (Rejsegarantifonden).

Provider APIs read 5/11 2026 from their public docs – NOT externally verified against live keys:
- Duffel: POST /air/offer_requests?return_offers=true, headers «Duffel-Version: v2», Bearer token.
- Travelpayouts: GET /aviasales/v3/prices_for_dates?origin&destination&departure_at&return_at&currency&token.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Protocol
from urllib.parse import quote

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.modules.privat import appdata, rules

ADDON = "rejser"
MAX_DESTINATIONS = 5
MAX_RESULTS = 12
TRIP_TYPES = ("strand", "storby", "ski", "natur", "kultur", "familie", "romantik", "eventyr", "wellness", "golf")


class TravelError(Exception):
    pass


# --------------------------------------------------------------------------- the search the user asked for

def _iata(v) -> str | None:
    s = str(v or "").strip().upper()
    return s if re.fullmatch(r"[A-Z]{3}", s) else None


def validate(params: dict, today: date) -> dict:
    """The search, cleaned and checked. Raises ValidationFailed with a plain Danish message."""
    origin = _iata(params.get("origin"))
    if origin is None:
        raise ValidationFailed("Hvorfra? Skriv lufthavnens kode, fx CPH eller BLL", field_errors=[{"field": "origin"}])
    dests = [d for d in (_iata(x) for x in (params.get("destinations") or [])) if d and d != origin][:MAX_DESTINATIONS]
    if not dests:
        raise ValidationFailed("Hvorhen? Vælg mindst én destination (lufthavnskode)", field_errors=[{"field": "destinations"}])
    adults = int(params.get("adults") or 1)
    children = int(params.get("children") or 0)
    if not 1 <= adults <= 9 or not 0 <= children <= 8:
        raise ValidationFailed("Antal rejsende skal være 1–9 voksne og 0–8 børn", field_errors=[{"field": "adults"}])
    depart = params.get("depart_date")
    month = params.get("month")
    if depart:
        try:
            d = date.fromisoformat(str(depart)[:10])
        except ValueError as e:
            raise ValidationFailed("Afrejsedatoen kunne ikke læses", field_errors=[{"field": "depart_date"}]) from e
        if d < today or d > today + timedelta(days=360):
            raise ValidationFailed("Afrejse skal ligge inden for det næste år", field_errors=[{"field": "depart_date"}])
        depart = d.isoformat()
    elif month:
        if not re.fullmatch(r"20\d\d-\d\d", str(month)):
            raise ValidationFailed("Måned skrives som 2027-03", field_errors=[{"field": "month"}])
    else:
        raise ValidationFailed("Hvornår? Vælg en afrejsedato eller en måned", field_errors=[{"field": "depart_date"}])
    nights = params.get("nights")
    nights = int(nights) if nights not in (None, "") else None
    if nights is not None and not 1 <= nights <= 60:
        raise ValidationFailed("Antal nætter skal være 1–60", field_errors=[{"field": "nights"}])
    budget = params.get("budget_dkk")
    budget = int(budget) if budget not in (None, "") else None
    if budget is not None and budget < 100:
        raise ValidationFailed("Budgettet er for lavt", field_errors=[{"field": "budget_dkk"}])
    ttype = str(params.get("trip_type") or "").strip().lower() or None
    return {"origin": origin, "destinations": dests, "adults": adults, "children": children,
            "depart_date": depart if depart else None, "month": None if depart else str(month), "nights": nights,
            "budget_dkk": budget, "direct_only": bool(params.get("direct_only")), "trip_type": ttype,
            "wishes": str(params.get("wishes") or "").strip()[:300] or None}


def _return_date(p: dict) -> str | None:
    if p["depart_date"] and p["nights"]:
        return (date.fromisoformat(p["depart_date"]) + timedelta(days=p["nights"])).isoformat()
    return None


# --------------------------------------------------------------------------- providers

class Provider(Protocol):
    name: str

    def search(self, p: dict, dest: str) -> list[dict]: ...


# Common airlines by IATA code (the providers answer with codes); anything else is shown as the code.
AIRLINES = {"SK": "SAS", "DY": "Norwegian", "D8": "Norwegian", "DX": "DAT", "FR": "Ryanair", "RK": "Ryanair UK",
            "U2": "easyJet", "EC": "easyJet Europe", "W6": "Wizz Air", "W4": "Wizz Air Malta", "LH": "Lufthansa",
            "LX": "Swiss", "OS": "Austrian", "SN": "Brussels Airlines", "EW": "Eurowings", "KL": "KLM", "AF": "Air France",
            "BA": "British Airways", "IB": "Iberia", "VY": "Vueling", "I2": "Iberia Express", "UX": "Air Europa",
            "TP": "TAP Air Portugal", "AY": "Finnair", "LO": "LOT", "TK": "Turkish Airlines", "PC": "Pegasus",
            "AZ": "ITA Airways", "A3": "Aegean", "EI": "Aer Lingus", "FI": "Icelandair", "BT": "airBaltic",
            "EK": "Emirates", "QR": "Qatar Airways", "EY": "Etihad", "DE": "Condor", "X3": "TUI fly", "BY": "TUI Airways",
            "HV": "Transavia", "TO": "Transavia France", "LS": "Jet2", "V7": "Volotea", "ZB": "Air Albania",
            "ZZ": "Duffel Airways (test)"}

# EUR per unit, from the ECB's daily reference rates; refreshed at most every 12 hours. Used ONLY to show a price a
# provider gave in another currency in kroner (marked «omregnet»); never to make a price up.
_FX: dict = {"at": None, "rates": {}}


def _rates() -> dict[str, float]:
    import xml.etree.ElementTree as ET

    import httpx

    now = rules.now()
    if _FX["at"] and now - _FX["at"] < timedelta(hours=12) and _FX["rates"]:
        return _FX["rates"]
    try:
        r = httpx.get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml", timeout=10.0)
        root = ET.fromstring(r.text)
        rates = {"EUR": 1.0}
        for el in root.iter():
            if el.get("currency") and el.get("rate"):
                rates[el.get("currency")] = float(el.get("rate"))
        if "DKK" in rates:
            _FX.update(at=now, rates=rates)
    except Exception:  # noqa: BLE001 – no rate means the foreign price is not shown, never guessed
        pass
    return _FX["rates"]


def to_dkk(amount: float, currency: str) -> float | None:
    cur = currency.upper()
    if cur == "DKK":
        return amount
    rates = _rates()
    if cur not in rates or "DKK" not in rates:
        return None
    return amount / rates[cur] * rates["DKK"]


def _offer(provider: str, dest: str, total: float | None, currency: str, *, airline: str = "", depart_at: str = "",
           return_at: str = "", stops: int | None = None, book_url: str = "", per_person: bool = False, p: dict) -> dict:
    travellers = p["adults"] + p["children"]
    total_dkk, note = None, "pris pr. person × antal rejsende (cache)" if per_person else "samlet pris for alle rejsende"
    if total is not None and currency:
        dkk = to_dkk(total * travellers if per_person else total, currency)
        if dkk is not None:
            total_dkk = round(dkk)
            if currency.upper() != "DKK":
                note += f", omregnet fra {currency.upper()} (ECB-kurs)"
    code = (airline or "").strip()
    return {"id": uuid.uuid4().hex[:10], "provider": provider, "origin": p["origin"], "destination": dest,
            "total_dkk": total_dkk, "currency": currency.upper(), "airline": AIRLINES.get(code.upper(), code)[:80],
            "depart_at": depart_at[:25], "return_at": return_at[:25], "stops": stops, "book_url": book_url[:1000],
            "price_note": note}


class Duffel:
    name = "duffel"
    BASE = "https://api.duffel.com"
    MAX_OFFERS = 20  # cheapest first; the search keeps at most MAX_RESULTS across destinations anyway

    def __init__(self, token: str):
        self.token = token

    def search(self, p: dict, dest: str) -> list[dict]:
        import httpx

        if not p["depart_date"]:
            return []  # Duffel prices exact dates; a flexible month comes from Travelpayouts
        slices = [{"origin": p["origin"], "destination": dest, "departure_date": p["depart_date"]}]
        ret = _return_date(p)
        if ret:
            slices.append({"origin": dest, "destination": p["origin"], "departure_date": ret})
        pax = [{"type": "adult"}] * p["adults"] + [{"age": 10}] * p["children"]
        body = {"data": {"slices": slices, "passengers": pax, "cabin_class": "economy",
                         **({"max_connections": 0} if p["direct_only"] else {})}}
        headers = {"Authorization": f"Bearer {self.token}", "Duffel-Version": "v2",
                   "Accept": "application/json", "Content-Type": "application/json"}
        # Two calls on purpose: an offer request *with* `return_offers=true` answers with every offer Duffel found
        # (routinely hundreds, tens of MB of JSON with every segment), which the API box cannot hold in memory.
        # Creating the request without offers and then listing the cheapest few keeps the response small.
        try:
            r = httpx.post(f"{self.BASE}/air/offer_requests?return_offers=false&supplier_timeout=15000", json=body,
                           headers=headers, timeout=30.0)
            if r.status_code < 400:
                req_id = (r.json().get("data") or {}).get("id")
                r = httpx.get(f"{self.BASE}/air/offers", headers=headers, timeout=30.0,
                              params={"offer_request_id": req_id, "limit": self.MAX_OFFERS, "sort": "total_amount"})
        except httpx.HTTPError as e:
            raise TravelError("Duffel kunne ikke nås") from e
        if r.status_code >= 400:
            raise TravelError(f"Duffel svarede {r.status_code}")
        out = []
        for o in (r.json().get("data") or [])[:self.MAX_OFFERS]:
            segs = (o.get("slices") or [{}])[0].get("segments") or []
            back = (o.get("slices") or [{}, {}])[-1].get("segments") or [] if ret else []
            route = _google_flights(p, dest, ret)
            out.append(_offer("duffel", dest, float(o["total_amount"]) if o.get("total_amount") else None,
                              o.get("total_currency") or "", airline=(o.get("owner") or {}).get("name") or "",
                              depart_at=segs[0].get("departing_at", "") if segs else "",
                              return_at=back[0].get("departing_at", "") if back else "",
                              stops=max(len(segs) - 1, 0), book_url=route, p=p))
        return out


def _google_flights(p: dict, dest: str, ret: str | None) -> str:
    """Duffel has no public booking page, so «Book» opens the same trip in Google Flights: route, both dates and
    the passengers, so the seller's page shows the same journey the price was for."""
    q = f"Flights from {p['origin']} to {dest} on {p['depart_date']}"
    if ret:
        q += f" returning {ret}"
    q += f" for {p['adults']} adult{'s' if p['adults'] != 1 else ''}"
    if p["children"]:
        q += f" and {p['children']} child{'ren' if p['children'] != 1 else ''}"
    return "https://www.google.com/travel/flights?q=" + quote(q)


def _dedupe(offers: list[dict]) -> list[dict]:
    """The same flight often comes back more than once (several fares, or both providers): one line per route,
    dates, airline and price. `offers` is sorted cheapest first, so the one kept is the best of its kind."""
    seen, out = set(), []
    for o in offers:
        key = (o["destination"], o["depart_at"][:16], o["return_at"][:16], (o.get("airline") or "").lower(), o["total_dkk"])
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out


class Travelpayouts:
    name = "travelpayouts"
    BASE = "https://api.travelpayouts.com"

    def __init__(self, token: str, marker: str):
        self.token, self.marker = token, marker

    def search(self, p: dict, dest: str) -> list[dict]:
        import httpx

        # The fare cache rarely has the exact day: ask for the month and keep fares within FLEX_DAYS of the chosen
        # date (the user sees the real date of each fare). The stay length is kept by the nights filter below.
        month = (p["depart_date"] or "")[:7] or p["month"]
        q = {"origin": p["origin"], "destination": dest, "currency": "dkk", "sorting": "price", "limit": 30,
             "one_way": "false" if p["nights"] else "true", "direct": str(p["direct_only"]).lower(),
             "departure_at": month, "token": self.token}
        if p["nights"]:
            q["return_at"] = month if not p["depart_date"] else \
                (date.fromisoformat(p["depart_date"]) + timedelta(days=p["nights"])).isoformat()[:7]
        try:
            r = httpx.get(f"{self.BASE}/aviasales/v3/prices_for_dates", params=q, timeout=20.0)
        except httpx.HTTPError as e:
            raise TravelError("Travelpayouts kunne ikke nås") from e
        if r.status_code >= 400:
            raise TravelError(f"Travelpayouts svarede {r.status_code}")
        out = []
        for x in r.json().get("data") or []:
            if not _fits(x.get("departure_at"), x.get("return_at"), p):
                continue
            link = _with_passengers(x.get("link") or "", p)
            url = f"https://www.aviasales.com{link}{'&' if '?' in link else '?'}marker={quote(self.marker)}" if link else ""
            out.append(_offer("travelpayouts", dest, float(x["price"]) if x.get("price") is not None else None, "DKK",
                              airline=x.get("airline") or "", depart_at=x.get("departure_at") or "",
                              return_at=x.get("return_at") or "", stops=x.get("transfers"), book_url=url,
                              per_person=True, p=p))
        return out


FLEX_DAYS = 3


def _fits(depart: str | None, ret: str | None, p: dict) -> bool:
    """A cached fare fits when it leaves within FLEX_DAYS of the chosen date and stays about the chosen nights."""
    try:
        d = date.fromisoformat(str(depart)[:10])
    except ValueError:
        return False
    if p["depart_date"] and abs((d - date.fromisoformat(p["depart_date"])).days) > FLEX_DAYS:
        return False
    if p["nights"] and ret:
        try:
            stay = (date.fromisoformat(str(ret)[:10]) - d).days
        except ValueError:
            return False
        if abs(stay - p["nights"]) > 2:
            return False
    return True


def _with_passengers(link: str, p: dict) -> str:
    """Aviasales search paths end with the passenger digits (adults, children): «/search/CPH0312BCN10121» is one adult.
    Put the travellers of this search there, so «Book» opens the same trip for the whole party."""
    m = re.match(r"^(/search/[A-Z]{3}\d{4}[A-Z]{3}(?:\d{4})?)(\d{1,3})(\?.*)?$", link)
    if not m:
        return link
    pax = f"{p['adults']}{p['children']}" if p["children"] else f"{p['adults']}"
    return f"{m.group(1)}{pax}{m.group(3) or ''}"


class FakeProvider:
    """Test double: `FakeProvider.prices[(dest)] = [total_dkk, …]`; never calls the internet."""

    name = "fake"
    prices: dict[str, list[int]] = {}

    def search(self, p: dict, dest: str) -> list[dict]:
        return [_offer("fake", dest, float(v), "DKK", airline="Testair", depart_at=(p["depart_date"] or p["month"] + "-10"),
                       stops=0, book_url=f"https://example.invalid/book/{dest}/{v}", p=p)
                for v in FakeProvider.prices.get(dest, [])]


def providers() -> list[Provider]:
    s = get_settings()
    out: list[Provider] = []
    if s.duffel_access_token == "fake" or s.travelpayouts_token == "fake":
        return [FakeProvider()]
    if s.duffel_access_token:
        out.append(Duffel(s.duffel_access_token))
    if s.travelpayouts_token and s.travelpayouts_marker:
        out.append(Travelpayouts(s.travelpayouts_token, s.travelpayouts_marker))
    return out


def configured() -> bool:
    return bool(providers())


# --------------------------------------------------------------------------- searching and keeping the result

def search(db, ws_id: uuid.UUID, params: dict) -> dict:
    """Ask every provider for every destination; keep only real prices, filter by the total budget, cheapest first.
    The search and its offers are kept (the latest 5) so «Book» can find the offer again."""
    p = validate(params, rules.local().date())
    provs = providers()
    if not provs:  # honest: «not set up», never «no trips found»
        from app.core.errors import NotImplementedYet

        raise NotImplementedYet("Rejser er ikke sat op hos Dialogbot endnu", code="travel_not_configured")
    offers, errors = [], []
    for prov in provs:
        for dest in p["destinations"]:
            try:
                offers += prov.search(p, dest)
            except TravelError as e:
                errors.append(str(e))
    priced = [o for o in offers if o["total_dkk"] is not None and o["book_url"]]
    within = [o for o in priced if p["budget_dkk"] is None or o["total_dkk"] <= p["budget_dkk"]]
    within.sort(key=lambda o: (o["total_dkk"], o["stops"] if o["stops"] is not None else 9))
    within = _dedupe(within)
    result = {"id": uuid.uuid4().hex[:12], "at": rules.now().isoformat(), "params": p, "offers": within[:MAX_RESULTS],
              "over_budget": len(priced) - len(within), "errors": sorted(set(errors))}
    data = appdata.get(db, ws_id, ADDON)
    searches = [result, *[s for s in data.get("searches", [])][:4]]
    appdata.put(db, ws_id, ADDON, {**data, "searches": searches})
    return result


def latest(db, ws_id: uuid.UUID) -> dict | None:
    s = appdata.get(db, ws_id, ADDON).get("searches") or []
    return s[0] if s else None


def find_offer(db, ws_id: uuid.UUID, offer_id: str) -> dict | None:
    for s in appdata.get(db, ws_id, ADDON).get("searches") or []:
        for o in s.get("offers") or []:
            if o["id"] == offer_id:
                return o
    return None


def kr(v: int | None) -> str:
    return f"{v:,} kr.".replace(",", ".") if v is not None else "ukendt pris"


def _when(o: dict) -> str:
    try:
        d = datetime.fromisoformat(o["depart_at"].replace("Z", "+00:00")) if "T" in o["depart_at"] else \
            datetime.fromisoformat(o["depart_at"][:10])
        return f"{d.day}/{d.month}"
    except ValueError:
        return o["depart_at"][:10]


def summary(result: dict) -> str:
    p, offers = result["params"], result["offers"]
    who = f"{p['adults']} voksne" + (f" og {p['children']} børn" if p["children"] else "")
    if not offers:
        why = (f" {result['over_budget']} lå over budgettet på {kr(p['budget_dkk'])}." if result["over_budget"] else "")
        return f"Jeg fandt ingen rejser med pris fra {p['origin']} for {who}.{why} Prøv andre datoer eller destinationer."
    lines = [f"{i + 1}. {o['origin']}→{o['destination']} {_when(o)}: {kr(o['total_dkk'])} i alt"
             + (f", {o['airline']}" if o["airline"] else "")
             + (", direkte" if o["stops"] == 0 else f", {o['stops']} skift" if o["stops"] else "")
             for i, o in enumerate(offers[:6])]
    head = f"Billigste fly for {who}" + (f" inden for {kr(p['budget_dkk'])}" if p["budget_dkk"] else "") + ":"
    return head + "\n" + "\n".join(lines) + "\nPriserne er fra udbyderne lige nu og kan ændre sig. Tryk «Book» for at bestille hos udbyderen."
