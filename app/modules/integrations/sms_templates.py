"""The fixed texts the assistant may send as SMS (app/modules/integrations/connectors/sms.py fills them).

One tone for all of them, so a customer's phone shows the same kind of message every time:
- short: one SMS segment (≤ 160 characters) for a normal business name, no emoji, no links the customer did not ask for;
- plain: what the customer needs first, no greeting boilerplate;
- signed by the business: the sender name is the business (≤ 11 characters) and every text ends with the sign-off
  ("Vh {business}" in Danish).

The texts belong to the customer's business, not to Dialogbot, so they carry the business's name and never Dialogbot's
brand. They are written in the language the business serves its callers in (the workspace's
`default_conversation_language`; Danish is the source). German, French, Italian and Spanish use the formal register
(Sie, vous, Lei, usted). `samples()` lists one example of each for the preview and the tests.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.languages import DEFAULT, normalize

SEGMENT = 160  # characters in one SMS (GSM-7; Danish æ, ø, å are in the alphabet)

TEXTS: dict[str, dict[str, str]] = {
    "da": {
        "sign": "{text} Vh {business}",
        "greeting": "Hej {first}. ",
        "booking": "{greeting}Din tid hos {business}: {what} {when}.",
        "call_back": "Tak for din henvendelse til {business}. En medarbejder ringer tilbage på dette nummer.",
        "opening_hours": "Åbningstider hos {business}: {hours}.",
        "address": "{business} ligger på {address}.",
        "contact": "Kontakt {business}: {details}.",
        "phone": "tlf. {phone}",
        "when": "{weekday} {day}. {month} kl. {hh}.{mm}",
    },
    "en": {
        "sign": "{text} Kind regards, {business}",
        "greeting": "Hi {first}. ",
        "booking": "{greeting}Your appointment at {business}: {what}, {when}.",
        "call_back": "Thank you for contacting {business}. A member of our team will call you back on this number.",
        "opening_hours": "Opening hours at {business}: {hours}.",
        "address": "{business} is at {address}.",
        "contact": "Contact {business}: {details}.",
        "phone": "tel. {phone}",
        "when": "{weekday} {day} {month} at {hh}:{mm}",
    },
    "de": {
        "sign": "{text} Freundliche Grüße, {business}",
        "greeting": "Hallo {first}. ",
        "booking": "{greeting}Ihr Termin bei {business}: {what}, {when}.",
        "call_back": "Vielen Dank für Ihre Anfrage an {business}. Wir rufen Sie unter dieser Nummer zurück.",
        "opening_hours": "Öffnungszeiten von {business}: {hours}.",
        "address": "Adresse von {business}: {address}.",
        "contact": "So erreichen Sie {business}: {details}.",
        "phone": "Tel. {phone}",
        "when": "{weekday}, {day}. {month} um {hh}:{mm} Uhr",
    },
    "es": {
        "sign": "{text} Saludos, {business}",
        "greeting": "Hola, {first}. ",
        "booking": "{greeting}Su cita en {business}: {what}, {when}.",
        "call_back": "Gracias por contactar con {business}. Le devolveremos la llamada a este número.",
        "opening_hours": "Horario de {business}: {hours}.",
        "address": "Dirección de {business}: {address}.",
        "contact": "Contacto de {business}: {details}.",
        "phone": "tel. {phone}",
        "when": "{weekday} {day} de {month} a las {hh}:{mm}",
    },
    "fr": {
        "sign": "{text} Cordialement, {business}",
        "greeting": "Bonjour {first}. ",
        "booking": "{greeting}Votre rendez-vous chez {business} : {what}, {when}.",
        "call_back": "Merci d'avoir contacté {business}. Nous vous rappellerons à ce numéro.",
        "opening_hours": "Horaires d'ouverture de {business} : {hours}.",
        "address": "Adresse de {business} : {address}.",
        "contact": "Pour contacter {business} : {details}.",
        "phone": "tél. {phone}",
        "when": "{weekday} {day} {month} à {hh}h{mm}",
    },
    "it": {
        "sign": "{text} Cordiali saluti, {business}",
        "greeting": "Buongiorno {first}. ",
        "booking": "{greeting}Il Suo appuntamento presso {business}: {what}, {when}.",
        "call_back": "Grazie per aver contattato {business}. La richiameremo a questo numero.",
        "opening_hours": "Orari di apertura di {business}: {hours}.",
        "address": "Indirizzo di {business}: {address}.",
        "contact": "Contatti di {business}: {details}.",
        "phone": "tel. {phone}",
        "when": "{weekday} {day} {month} alle {hh}:{mm}",
    },
    "no": {
        "sign": "{text} Mvh {business}",
        "greeting": "Hei {first}. ",
        "booking": "{greeting}Din time hos {business}: {what} {when}.",
        "call_back": "Takk for henvendelsen til {business}. En medarbeider ringer deg tilbake på dette nummeret.",
        "opening_hours": "Åpningstider hos {business}: {hours}.",
        "address": "Adresse til {business}: {address}.",
        "contact": "Kontakt {business}: {details}.",
        "phone": "tlf. {phone}",
        "when": "{weekday} {day}. {month} kl. {hh}.{mm}",
    },
    "sv": {
        "sign": "{text} Mvh {business}",
        "greeting": "Hej {first}. ",
        "booking": "{greeting}Din tid hos {business}: {what} {when}.",
        "call_back": "Tack för att du kontaktade {business}. En medarbetare ringer upp dig på det här numret.",
        "opening_hours": "Öppettider hos {business}: {hours}.",
        "address": "Adress till {business}: {address}.",
        "contact": "Kontakta {business}: {details}.",
        "phone": "tel. {phone}",
        "when": "{weekday} {day} {month} kl. {hh}.{mm}",
    },
}

# Monday first. Short day names are used for opening hours ("man–fre 07:00–16:00").
DAYS_SHORT: dict[str, tuple[str, ...]] = {
    "da": ("man", "tir", "ons", "tor", "fre", "lør", "søn"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
    "fr": ("lun", "mar", "mer", "jeu", "ven", "sam", "dim"),
    "it": ("lun", "mar", "mer", "gio", "ven", "sab", "dom"),
    "no": ("man", "tir", "ons", "tor", "fre", "lør", "søn"),
    "sv": ("mån", "tis", "ons", "tor", "fre", "lör", "sön"),
}
DAYS_LONG: dict[str, tuple[str, ...]] = {
    "da": ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "it": ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"),
    "no": ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"),
    "sv": ("måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"),
}
MONTHS: dict[str, tuple[str, ...]] = {
    "da": ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november",
           "december"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
           "December"),
    "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
           "Dezember"),
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
           "diciembre"),
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
           "décembre"),
    "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
           "novembre", "dicembre"),
    "no": ("januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
           "desember"),
    "sv": ("januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november",
           "december"),
}


def _t(lang: str | None, key: str, **values) -> str:
    table = TEXTS.get(normalize(lang)) or TEXTS[DEFAULT]
    return table[key].format(**values)


def sign(text: str, business: str, lang: str = "da") -> str:
    return _t(lang, "sign", text=text.rstrip(), business=business)


def when(start: datetime, tz: str, lang: str = "da") -> str:
    """A booking's start as the caller reads it: "tirsdag 3. november kl. 10.00" / "Tuesday 3 November at 10:00".
    Danish is the same as app.modules.bookings.service.label."""
    lang = normalize(lang)
    local = start.astimezone(ZoneInfo(tz))
    return _t(lang, "when", weekday=DAYS_LONG[lang][local.weekday()], day=local.day,
              month=MONTHS[lang][local.month - 1], hh=f"{local:%H}", mm=f"{local:%M}")


def day_short(day_index: int, lang: str = "da") -> str:
    """Short day name, Monday = 0."""
    return DAYS_SHORT[normalize(lang)][day_index]


def phone(number: str, lang: str = "da") -> str:
    return _t(lang, "phone", phone=number)


def booking(business: str, contact_name: str, what: str, when: str, lang: str = "da") -> str:
    first = (contact_name or "").strip().split(" ")[0]
    greeting = _t(lang, "greeting", first=first) if first else ""
    return sign(_t(lang, "booking", greeting=greeting, business=business, what=what, when=when), business, lang)


def call_back(business: str, lang: str = "da") -> str:
    return sign(_t(lang, "call_back", business=business), business, lang)


def opening_hours(business: str, hours: str, lang: str = "da") -> str:
    return sign(_t(lang, "opening_hours", business=business, hours=hours), business, lang)


def address(business: str, address_line: str, lang: str = "da") -> str:
    return sign(_t(lang, "address", business=business, address=address_line), business, lang)


def contact(business: str, details: str, lang: str = "da") -> str:
    return sign(_t(lang, "contact", business=business, details=details), business, lang)


def samples(lang: str = "da") -> dict[str, str]:
    b = "Hansen VVS"
    lang = normalize(lang)
    d = DAYS_SHORT[lang]
    start = datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("UTC"))  # Tuesday 3 November, 10:00 in Copenhagen
    return {
        "booking": booking(b, "Mette Nielsen", "Besigtigelse",
                           "tirsdag 3. nov. kl. 10.00" if lang == "da" else when(start, "Europe/Copenhagen", lang), lang),
        "ring_tilbage": call_back(b, lang),
        "aabningstider": opening_hours(b, f"{d[0]}–{d[4]} 07:00–16:00, {d[5]} 09:00–12:00", lang),
        "adresse": address(b, "Vesterbrogade 12 8000 Aarhus C", lang),
        "kontakt": contact(b, f"{phone('93 70 34 33', lang)}, hansenvvs.dk", lang),
    }
