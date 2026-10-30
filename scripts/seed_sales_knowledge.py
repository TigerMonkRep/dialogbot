"""Move the product facts in app/modules/sales/script.FEATURES into the sales workspace as knowledge DRAFTS.

Run in the API service shell (Render → Shell):

    python -m scripts.seed_sales_knowledge          # create the drafts that do not exist yet
    python -m scripts.seed_sales_knowledge --dry-run

Nothing is approved here: an operator reviews and approves each draft under Viden in the sales workspace. Until
then (no approved public knowledge) Peter's script falls back to FEATURES. Running it twice creates nothing new.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.core.audit import record_audit
from app.db import get_session_factory
from app.models import KnowledgeItem, KnowledgeVersion
from app.modules.billing import prices
from app.modules.knowledge.service import _key
from app.modules.sales.service import sales_workspace

# (kind, title, text, audience). Every sentence is a statement that is true of the product today (script.FEATURES).
ITEMS: list[tuple[str, str, str, str]] = [
    ("fact", "Telefonpasning døgnet rundt",
     "Dialogbot tager telefonen på dansk med en naturlig stemme, døgnet rundt, når virksomheden er optaget eller har "
     "lukket.", "public"),
    ("fact", "Svarer kun ud fra godkendt viden",
     "Assistenten svarer kun ud fra den viden, virksomheden selv har godkendt: ydelser, priser, åbningstider og regler. "
     "Den gætter aldrig.", "public"),
    ("fact", "Besked til virksomheden",
     "Assistenten afklarer kundens behov, noterer navn og nummer og sender en kort opsummering, så virksomheden ringer "
     "tilbage til en varm kunde.", "public"),
    ("fact", "Booking i kalenderen",
     "Assistenten kan booke, flytte og aflyse tider i kalenderen og sende en bekræftelse på SMS.", "public"),
    ("fact", "Chat på hjemmesiden", "Chatten på hjemmesiden bruger den samme viden som telefonen.", "public"),
    ("fact", "Beholde nummeret",
     "Virksomheden kan beholde sit nummer og viderestille til Dialogbot, når de er optaget eller har lukket, eller få "
     "et nyt nummer.", "public"),
    ("fact", "Opsætning",
     "Virksomheden kan sætte assistenten op selv efter byggevejledningens tre trin på cirka en halv time; det er med i "
     "abonnementet. Vil de hellere have det gjort, sætter Dialogbots specialister den op for "
     f"{prices.kr(prices.SPECIALIST_SETUP_NET_MINOR)} kr. én gang ekskl. moms.", "public"),
    ("fact", "Priser",
     f"Abonnementet koster {prices.kr(prices.SUBSCRIPTION_MONTHLY_NET_MINOR)} kr. om måneden ekskl. moms, uden binding "
     f"og uden pris pr. henvendelse. {prices.INBOUND_INCLUDED_MINUTES} minutters indgående opkald om måneden er med; "
     f"derefter {prices.kr(prices.INBOUND_EXTRA_MINUTE_NET_MINOR)} kr. pr. påbegyndt minut. Udgående kampagneopkald "
     f"koster {prices.kr(prices.CAMPAIGN_CALL_NET_MINOR)} kr. pr. opkald plus {prices.kr(prices.CAMPAIGN_MINUTE_NET_MINOR)} "
     "kr. pr. påbegyndt samtaleminut, alt ekskl. moms.", "public"),
    ("fact", "Samtaler og opsummeringer for kunder",
     "Kunder ser deres samtaler og opsummeringer i indbakken i Dialogbot.", "customer_docs"),
]


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    with get_session_factory()() as db:
        ws = sales_workspace(db)
        if ws is None:
            print("SALES_WORKSPACE_ID er ikke sat eller peger ikke på et arbejdsrum", file=sys.stderr)
            return 1
        created = 0
        for kind, title, text, audience in ITEMS:
            key = _key(kind, title)
            if db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.workspace_id == ws.id, KnowledgeItem.kind == kind,
                                                        KnowledgeItem.key == key)):
                print(f"findes allerede: {title}")
                continue
            print(f"{'(tørkørsel) ' if dry else ''}opretter udkast: {title} [{audience}]")
            if dry:
                continue
            item = KnowledgeItem(workspace_id=ws.id, kind=kind, key=key)
            db.add(item)
            db.flush()
            v = KnowledgeVersion(item_id=item.id, workspace_id=ws.id, version_no=1, status="draft", title=title,
                                 content={"text": text}, source_type="import", source_ref="script.FEATURES",
                                 audience=audience)
            db.add(v)
            db.flush()
            record_audit(db, workspace_id=ws.id, actor_user_id=None, action="knowledge.draft_created",
                         object_type="knowledge_version", object_id=v.id,
                         after={"title": title, "audience": audience, "via": "scripts.seed_sales_knowledge"})
            created += 1
        if not dry:  # Peter books intro meetings on this booking type (sales/tools.py)
            from app.modules.sales.tools import ensure_meeting_type

            bt = ensure_meeting_type(db, ws)
            print(f"bookingtype: {bt.name}")
        db.commit()
        print(f"{created} udkast oprettet. Godkend dem under Viden i salgsarbejdsrummet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
