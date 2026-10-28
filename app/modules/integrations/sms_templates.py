"""The fixed Danish texts the assistant may send as SMS (app/modules/integrations/connectors/sms.py fills them).

One tone for all of them, so a customer's phone shows the same kind of message every time:
- short: one SMS segment (≤ 160 characters) for a normal business name, no emoji, no links the customer did not ask for;
- plain: what the customer needs first, no greeting boilerplate;
- signed by the business: the sender name is the business (≤ 11 characters) and every text ends "Vh {business}".

The texts belong to the customer's business, not to Dialogbot, so they carry the business's name and never Dialogbot's
brand. `samples()` lists one example of each for the preview and the tests.
"""
from __future__ import annotations

SEGMENT = 160  # characters in one SMS (GSM-7; Danish æ, ø, å are in the alphabet)


def sign(text: str, business: str) -> str:
    return f"{text.rstrip()} Vh {business}"


def booking(business: str, contact_name: str, what: str, when: str) -> str:
    first = (contact_name or "").strip().split(" ")[0]
    greeting = f"Hej {first}. " if first else ""
    return sign(f"{greeting}Din tid hos {business}: {what} {when}.", business)


def call_back(business: str) -> str:
    return sign(f"Tak for din henvendelse til {business}. En medarbejder ringer tilbage på dette nummer.", business)


def opening_hours(business: str, hours: str) -> str:
    return sign(f"Åbningstider hos {business}: {hours}.", business)


def address(business: str, address_line: str) -> str:
    return sign(f"{business} ligger på {address_line}.", business)


def contact(business: str, details: str) -> str:
    return sign(f"Kontakt {business}: {details}.", business)


def samples() -> dict[str, str]:
    b = "Hansen VVS"
    return {
        "booking": booking(b, "Mette Nielsen", "Besigtigelse", "tirsdag 3. nov. kl. 10.00"),
        "ring_tilbage": call_back(b),
        "aabningstider": opening_hours(b, "man–fre 07:00–16:00, lør 09:00–12:00"),
        "adresse": address(b, "Vesterbrogade 12 8000 Aarhus C"),
        "kontakt": contact(b, "tlf. 93 70 34 33, hansenvvs.dk"),
    }
