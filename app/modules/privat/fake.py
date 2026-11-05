"""Deterministic stand-in for the private assistant (AI_PROVIDER=fake, dev/test only).

It maps the prototype's Danish phrasings to the same tool calls a real model would make, using only the tools it was
offered – so a switched-off add-on leads to suggest_addon, exactly like with the real model."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from app.modules.ai.provider import Completion, ToolCall, Usage

DAYS = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
WORD_HOURS = {"tre": 15, "fire": 16, "fem": 17, "to": 14, "et": 13}


def _done(model: str, text: str) -> Completion:
    return Completion(text=text, stop_reason="end_turn", requested_model=model, served_model=model,
                      usage=Usage(input_tokens=10, output_tokens=5), request_id="fake-req")


def _call(model: str, name: str, args: dict) -> Completion:
    c = ToolCall(id=f"toolu_fake_{name}", name=name, input=args)
    return Completion(text="", stop_reason="tool_use", requested_model=model, served_model=model,
                      usage=Usage(input_tokens=10, output_tokens=5), request_id="fake-req", tool_calls=[c],
                      assistant_content=[{"type": "tool_use", "id": c.id, "name": name, "input": args}])


def _now(system: str) -> datetime:
    m = re.search(r"Nu er det (\d{4}-\d\d-\d\dT\d\d:\d\d)", system)
    return datetime.fromisoformat(m.group(1)) if m else datetime(2026, 11, 4, 10, 0)


def _items(s: str) -> list[str]:
    s = re.sub(r"[.!]+$", "", s or "")
    return [x.strip()[:1].upper() + x.strip()[1:] for x in re.split(r",|\sog\s", s, flags=re.I) if x.strip()]


def _when(low: str, now: datetime) -> datetime:
    day = now.date()
    if "i morgen" in low:
        day = day + timedelta(days=1)
    else:
        for i, d in enumerate(DAYS):
            if re.search(rf"\b{d}\b", low):
                day = day + timedelta(days=(i - now.weekday()) % 7 or 7)
                break
    hm = re.search(r"kl\.?\s*(\d{1,2})(?:[.:](\d{2}))?", low)
    h, m = (int(hm.group(1)), int(hm.group(2) or 0)) if hm else (9, 0)
    return datetime(day.year, day.month, day.day, h, m)


def respond(model: str, system: str, messages: list[dict], tools: list[dict] | None) -> Completion:
    last = messages[-1]["content"] if messages else ""
    if system.startswith("PRIVAT_CALL_OUTCOME"):
        return _outcome(model, str(last))
    if isinstance(last, list):  # tool results: the handlers already wrote the messages (or the error is shown)
        failed = any(str(b.get("content") or "").startswith("Fejl:") for b in last if isinstance(b, dict))
        return _done(model, "" if failed else "Klaret.")
    names = {t["name"] for t in tools or []}
    offer = next((t for t in tools or [] if t["name"] == "suggest_addon"), None)
    offerable = set(offer["input_schema"]["properties"]["key"]["enum"]) if offer else set()
    text = str(last).strip()
    low = text.lower()
    now = _now(system)

    def suggest(key: str) -> Completion | None:
        return _call(model, "suggest_addon", {"key": key}) if key in offerable else None

    if "hvad venter" in low:
        return _call(model, "list_waiting", {})
    g = re.search(r"\b(?:[Ll]av|[Oo]pret|[Gg]em)\s+(?:en\s+)?gruppe(?:n)?\s+([A-ZÆØÅ]\w*)\s+med\s+(.+)$", text)
    if g and "create_group" in names:
        people = [{"name": n} for n in _items(g.group(2))]
        return _call(model, "create_group", {"name": g.group(1), "members": people})
    grp = re.search(r"\bmed\s+([a-zæøå]+)\s*[.!]?$", text)
    if re.search(r"\bdel\b|\bdele\b", low) and "liste" in low and grp and "share_with_group" in names:
        return _call(model, "share_with_group", {"group_name": grp.group(1)})
    if re.search(r"\bdel\b|\bdele\b", low) and "liste" in low:
        if "share_list" in names:
            who = re.search(r"\bmed\s+([A-ZÆØÅ][a-zæøå]+)", text)
            return _call(model, "share_list", {"with_name": who.group(1) if who else "",
                                               **({"mode": "wishlist"} if "ønske" in low else {})})
        return suggest("oenskelister" if "ønske" in low else "delte-lister") or _done(model, "Det kan jeg ikke endnu.")
    if re.search(r"\bregning|\bforfald", low):
        if "add_bills" not in names:
            return suggest("regninger") or _done(model, "Regninger er ikke slået til.")
        if re.search(r"\b(fjern|slet)\b", low):
            who = re.search(r"\b(?:fjern|slet)\s+(?:regningen\s+)?(?:for\s+)?(.+?)\s*[.!]?$", text, re.I)
            return _call(model, "remove_bill", {"name": (who.group(1) if who else "").strip("«»")})
        m = re.search(r"(?:regning(?:en)?\s+(?:for|til)\s+)?([A-ZÆØÅ][\wæøåÆØÅ-]*(?:\s+[a-zæøå][\wæøå-]*)?)\s+"
                      r"(?:den|d\.)\s+(\d{1,2})\.?\s+(hver måned|hvert kvartal|hvert år)", text)
        if not m:
            return _call(model, "bills_overview", {})
        freq = {"hver måned": "monthly", "hvert kvartal": "quarterly", "hvert år": "yearly"}[m.group(3)]
        item: dict = {"name": m.group(1), "due_day": int(m.group(2)), "frequency": freq}
        amt = re.search(r"(\d[\d.]*(?:,\d{1,2})?)\s*kr", text)
        if amt:
            item["amount"] = amt.group(1) + " kr."
        return _call(model, "add_bills", {"items": [item]})
    if re.search(r"fødselsdag|fylder\s+\d|fylder år", low):
        if "add_birthdays" not in names:
            return suggest("foedselsdage") or _done(model, "Fødselsdage er ikke slået til.")
        if re.search(r"\b(fjern|slet)\b", low):
            who = re.search(r"\b(?:fjern|slet)\s+(.+?)(?:s)?\s+fødselsdag", text, re.I)
            return _call(model, "remove_birthday", {"name": who.group(1) if who else ""})
        date_rx = (r"(\d{1,2}\.?\s*(?:januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)"
                   r"(?:\s+\d{4})?|\d{1,2}[./]\d{1,2}(?:[./]\d{4})?)")
        items = []
        for m in re.finditer(r"([A-ZÆØÅ][\wæøåÆØÅ]*(?:\s+[A-ZÆØÅ][\wæøåÆØÅ]*)?)(?:s\s+fødselsdag\s+er|\s+har\s+fødselsdag|\s+fylder\s+\d+)"
                             r"\s+(?:den\s+|d\.\s*)?" + date_rx, text):
            items.append({"name": m.group(1), "date": m.group(2)})
        if not items:
            return _call(model, "list_birthdays", {})
        uge = 7 if "en uge før" in low else None
        n = re.search(r"(\d+)\s+dage\s+før", low)
        days = int(n.group(1)) if n else uge
        for it in items:
            if days is not None:
                it["remind_days_before"] = days
        return _call(model, "add_birthdays", {"items": items})
    if "kalender" in low:
        if re.search(r"\blæg\b", low) and re.search(r"kl\.?\s*\d", low) and "add_to_calendar" in names:
            what = re.sub(r"^.*?\blæg\s+(?:tiden\s+)?(?:hos\s+)?", "", text, flags=re.I)
            what = re.sub(r"\s*(i morgen|i dag|på \w+dag|\w+dag|kl\.?|i min kalender).*$", "", what, flags=re.I).strip()
            return _call(model, "add_to_calendar", {"title": (what[:1].upper() + what[1:]) or "Aftale",
                                                    "starts_at": _when(low, now).isoformat(timespec="minutes")})
        if "calendar_status" in names:
            return _call(model, "calendar_status", {})
        return suggest("kalender") or _done(model, "Kalender er ikke slået til.")
    if re.search(r"(rejse|ferie\b|fly til|flybillet)", low) and "pakkeliste" not in low:
        if "search_trips" not in names:
            return suggest("rejser") or _done(model, "Rejser er ikke slået til.")
        origin = re.search(r"\bfra\s+([A-ZÆØÅ]{3})\b", text)
        dests = re.findall(r"\btil\s+([A-ZÆØÅ]{3})\b", text) or (["BCN", "LIS", "AGP"] if "strand" in low else [])
        month = re.search(r"(20\d\d-\d\d)(?!-)", text)
        dd = re.search(r"(20\d\d-\d\d-\d\d)", text)
        budget = re.search(r"højst\s+([\d.]+)\s*kr", low)
        adults = re.search(r"(\d+)\s+voksne", low)
        kids = re.search(r"(\d+)\s+børn", low)
        nights = re.search(r"(\d+)\s+nætter", low)
        args = {"origin": origin.group(1) if origin else "", "destinations": dests,
                **({"depart_date": dd.group(1)} if dd else {"month": month.group(1)} if month else {}),
                **({"budget_dkk": int(budget.group(1).replace(".", ""))} if budget else {}),
                **({"adults": int(adults.group(1))} if adults else {}), **({"children": int(kids.group(1))} if kids else {}),
                **({"nights": int(nights.group(1))} if nights else {}), **({"direct_only": True} if "direkte" in low else {})}
        return _call(model, "search_trips", args)
    if "pakkeliste" in low:
        if "create_packing_list" not in names:
            return suggest("pakkeliste") or _done(model, "Pakkeliste er ikke slået til.")
        if "sidst" in low:
            return _call(model, "reuse_packing_list", {})
        trip = re.search(r"pakkeliste\s+til\s+(?:en\s+|et\s+)?(.+?)(?:\s+med\s+|[.!]?$)", text, re.I)
        m = re.search(r"\smed\s(.+)$", text, re.I)
        return _call(model, "create_packing_list", {"trip": trip.group(1) if trip else "turen",
                                                    "items": _items(m.group(1)) if m else ["Tandbørste", "Opladere", "Regntøj"]})
    if "madplan" in low or re.search(r"spiser ikke|vi er \d", low):
        if "save_meal_plan" not in names:
            return suggest("madplan") or _done(model, "Madplan er ikke slået til.")
        if re.search(r"spiser ikke|vi er \d", low) and "madplan" not in low:
            ppl = re.search(r"vi er (\d+)", low)
            avoid = re.search(r"spiser ikke ([^.,]+)", low)
            return _call(model, "save_food_preferences", {**({"people": int(ppl.group(1))} if ppl else {}),
                                                          **({"avoid": avoid.group(1).strip()} if avoid else {})})
        return _call(model, "save_meal_plan", {"title": "Madplan", "days": [
            {"day": "mandag", "dish": "Lasagne", "ingredients": ["500 g hakket oksekød", "Lasagneplader", "Tomatsauce"]},
            {"day": "tirsdag", "dish": "Kylling i karry", "ingredients": ["Kyllingebryst", "Ris", "tomatsauce"]}]})
    phone_m = re.search(r"(\+?\d[\d ]{7,13}\d)", text)
    if re.search(r"\b(læge|tandlæge)", low) and ("gem" in low or "book" in low):
        if "book_health_appointment" not in names:
            return suggest("laege-og-tandlaege") or _done(model, "Læge & tandlæge er ikke slået til.")
        kind = "tandlaege" if "tandlæge" in low else "laege"
        if "gem" in low and phone_m:
            nm = re.search(r"(?:hedder|er)\s+([A-ZÆØÅ][\wæøåÆØÅ ]+?)(?:,|\s+på|\s+nummer|\s+tlf)", text)
            return _call(model, "save_health_contact", {"kind": kind, "name": nm.group(1) if nm else "", "phone": phone_m.group(1)})
        return _call(model, "book_health_appointment", {"kind": kind, "purpose": "tandeftersyn" if kind == "tandlaege" else "lægetid",
                                                        "window": "en morgen i næste uge"})
    car_shop = re.search(r"\bværksted", low) and re.search(r"\b(gem|book)\b", low)
    if re.search(r"\bsyn\b|nummerplade|\bbilen\b", low) or car_shop:
        if "save_car" not in names:
            return suggest("bil-og-syn") or _done(model, "Bil & syn er ikke slået til.")
        if "værksted" in low and "gem" in low and phone_m:
            nm = re.search(r"værksted(?:et)?\s+(?:hedder|er)\s+([A-ZÆØÅ][\wæøåÆØÅ ]+?)(?:,|\s+på|\s+nummer)", text)
            return _call(model, "save_workshop", {"name": nm.group(1) if nm else "Værkstedet", "phone": phone_m.group(1)})
        if "book" in low:
            return _call(model, "book_workshop", {"purpose": "syn", "window": "uge 18"})
        plate = re.search(r"\b([A-ZÆØÅ]{2}\s?\d{2}\s?\d{3})\b", text)
        due = re.search(r"(20\d\d-\d\d-\d\d)", text)
        if plate or due:
            return _call(model, "save_car", {**({"plate": plate.group(1)} if plate else {}),
                                             **({"inspection_due": due.group(1)} if due else {}),
                                             **({"tire_reminders": True} if "dæk" in low else {})})
        return _call(model, "car_status", {})
    parcel_num = re.search(r"\b([A-Z0-9]{8,40})\b", text)
    if re.search(r"\bpakke|forsendelse", low) and "pakkeliste" not in low and "mind mig" not in low \
            and (parcel_num or re.search(r"\b(følg|spor|mine pakker)", low)):
        if "track_parcel" not in names:
            return suggest("pakker") or _done(model, "Pakker er ikke slået til.")
        num = re.search(r"\b([A-Z0-9]{8,40})\b", text)
        if "stop" in low and num:
            return _call(model, "stop_tracking", {"number": num.group(1)})
        if num:
            return _call(model, "track_parcel", {"number": num.group(1)})
        return _call(model, "parcels_status", {})
    if re.search(r"tilføj|husk også|sæt .+ på", low) and "liste med" not in low:
        raw = re.sub(r"^.*?(tilføj|husk også|sæt)\s*", "", text, flags=re.I)
        raw = re.sub(r"\s*(på listen|til listen|på)\s*[.!]?$", "", raw, flags=re.I)
        return _call(model, "add_items", {"items": _items(raw)})
    if re.search(r"flyt|ændr|skub", low) and re.search(r"kl\.?\s*\d", low):
        if not re.search(r"i morgen|i dag|mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag", low):
            hm = re.search(r"kl\.?\s*(\d{1,2})(?:[.:](\d{2}))?", low)
            return _call(model, "move_reminder", {"remind_at": f"{int(hm.group(1)):02d}:{hm.group(2) or '00'}"})
        return _call(model, "move_reminder", {"remind_at": _when(low, now).isoformat(timespec="minutes")})
    if "mind mig om" in low:
        what = re.sub(r"^.*?mind mig om\s*(at\s+)?", "", text, flags=re.I)
        what = re.sub(r"\s*(i morgen|i dag|på \w+dag|\w+dag)\b.*$", "", what, flags=re.I)
        what = re.sub(r"\s*kl\.?.*$", "", what, flags=re.I).strip()
        return _call(model, "create_reminder", {"title": what[:1].upper() + what[1:] or "Påmindelse",
                                                "remind_at": _when(low, now).isoformat(timespec="minutes")})
    if re.search(r"\bring", low):
        if "propose_call" not in names:
            return suggest("ring-for-mig") or _done(model, "Opkald er ikke slået til.")
        return _call(model, "propose_call", _call_args(text, low))
    if "liste" in low:
        m = re.search(r"\smed\s(.+)$", text, re.I)
        lt = "wishlist" if "ønske" in low else "shopping" if "indkøb" in low else "todo"
        title = {"wishlist": "Ønskeliste", "shopping": "Indkøbsliste"}.get(lt, "Liste")
        return _call(model, "create_list", {"title": title, "type": lt, "items": _items(m.group(1)) if m else []})
    return _call(model, "ask_clarifying", {"question": "Skal jeg lave en påmindelse, en liste eller ringe for dig?",
                                           "options": [{"label": "Mind mig om …", "sub": "En besked på et bestemt tidspunkt"},
                                                       {"label": "Lav en liste", "sub": "Med punkter, du kan krydse af"},
                                                       {"label": "Ring for mig", "sub": "Du godkender, før jeg ringer"}]})


def _call_args(text: str, low: str) -> dict:
    args: dict = {"purpose": "Aflever cyklen" if "cykel" in low else "Aftal en tid"}
    k = re.search(r"(mandag|tirsdag|onsdag|torsdag|fredag)\s+efter\s+(?:kl\.?|klokken)\s*(\d{1,2}|tre|fire|fem|to|et)", low)
    if k:
        h = WORD_HOURS.get(k.group(2)) or int(k.group(2))
        args["window"] = f"{k.group(1)} efter kl. {h + 12 if h < 8 else h}"
    if "cykel" in low:
        args["category"] = "cykelværksted"
    phone = re.search(r"(\+?\d[\d ]{7,13}\d)", text)
    if phone:
        args["phone"] = phone.group(1)
    name = re.search(r"[Rr]ing\w*\s+(?:til\s+)?([A-ZÆØÅ][\wæøåÆØÅ]*(?:\s+[A-ZÆØÅ][\wæøåÆØÅ]*)*)", text)
    if name:
        args["business_name"] = name.group(1)
    return args


def _outcome(model: str, transcript: str) -> Completion:
    low = transcript.lower()
    t = re.search(r"((?:mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag)\s+kl\.?\s*\d{1,2}(?:[.:]\d{2})?)", low)
    price = re.search(r"(\d[\d.]*\s*kr\.?[^.]*)", transcript)
    if t:
        data = {"outcome": "confirmed", "confirmed_text": t.group(1)[:1].upper() + t.group(1)[1:]}
    elif "ringer tilbage" in low:
        data = {"outcome": "callback", "confirmed_text": None}
    elif re.search(r"\bnej\b|kan ikke", low):
        data = {"outcome": "declined", "confirmed_text": None}
    else:
        data = {"outcome": "info", "confirmed_text": None}
    data["price_text"] = price.group(1).strip() if price else None
    data["summary"] = f"Testdobbelt: {data['outcome']}."
    return _done(model, json.dumps(data, ensure_ascii=False))
