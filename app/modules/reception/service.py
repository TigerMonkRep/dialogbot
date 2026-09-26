"""Reception manuscript (R05): how the assistant greets, what it asks for, when it hands over.

The script is owner/admin configuration and applies to every channel. It shapes behaviour only –
facts, prices and hours still come exclusively from approved knowledge."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session as OrmSession

from app.models import ReceptionScript, Workspace  # noqa: F401 (re-exported for callers)

FIELDS = ("persona_name", "address_form", "greeting", "collect", "escalation", "avoid", "closing")
AI_DISCLOSURE = re.compile(r"digital assistent|ai-assistent|kunstig intelligens|\bAI\b", re.I)


def get(db: OrmSession, ws: Workspace) -> ReceptionScript:
    s = db.get(ReceptionScript, ws.id)
    if s is None:
        s = ReceptionScript(workspace_id=ws.id, version=0, address_form="du", collect=[])
    return s


def is_empty(s: ReceptionScript) -> bool:
    return not any([s.greeting, s.collect, s.escalation, s.avoid, s.closing, s.persona_name])


def prompt_section(s: ReceptionScript | None) -> str:
    """Instructions appended to the system prompt. Empty when nothing is configured."""
    if s is None or is_empty(s):
        return ""
    lines = ["Receptionsmanuskript fra virksomheden (følg det; det ændrer aldrig fakta eller reglerne ovenfor):"]
    if s.persona_name:
        lines.append(f"- Du præsenterer dig som {s.persona_name}, virksomhedens digitale assistent.")
    lines.append("- Tiltal kunden med " + ("De/Dem." if s.address_form == "De" else "du."))
    if s.collect:
        lines.append("- Når kunden vil have et tilbud, en tid eller et opkald, så spørg ind til (ét spørgsmål ad gangen): "
                     + "; ".join(str(c) for c in s.collect) + ".")
    if s.escalation:
        lines.append(f"- Giv straks videre til en medarbejder (lov et hurtigt opkald) når: {s.escalation}")
    if s.avoid:
        lines.append(f"- Undgå eller afvis høfligt: {s.avoid}")
    if s.closing:
        lines.append(f"- Afslut samtalen sådan: {s.closing}")
    return "\n".join(lines)


def spoken_greeting(s: ReceptionScript | None, ws: Workspace) -> str | None:
    """Phone greeting from the script, always with AI disclosure (the caller must know it is a machine)."""
    if s is None or not s.greeting.strip():
        return None
    g = s.greeting.strip().replace("{virksomhed}", ws.name)
    if not AI_DISCLOSURE.search(g):
        g += " Du taler med en digital assistent."
    return g
