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
     f"og uden pris pr. henvendelse. {prices.INCLUDED_MINUTES} minutter om måneden er med – både indgående opkald og "
     "udgående kampagneopkald, brugt i den rækkefølge opkaldene sker. "
     f"Inden for pakken er der ingen pris pr. opkald. Er pakken brugt op, koster et udgående kampagneopkald "
     f"{prices.kr(prices.OUTBOUND_CALL_ANSWERED_NET_MINOR)} kr., hvis personen tager telefonen, "
     f"{prices.kr(prices.OUTBOUND_CALL_VOICEMAIL_NET_MINOR)} kr. ved telefonsvarer og "
     f"{prices.kr(prices.OUTBOUND_CALL_NO_ANSWER_NET_MINOR)} kr. ved ubesvaret eller optaget – plus "
     f"{prices.kr(prices.OUTBOUND_EXTRA_MINUTE_NET_MINOR)} kr. pr. påbegyndt samtaleminut; indgående opkald koster "
     f"{prices.kr(prices.INBOUND_EXTRA_MINUTE_NET_MINOR)} kr. pr. påbegyndt minut. Alt ekskl. moms.", "public"),
    ("fact", "Samtaler og opsummeringer for kunder",
     "Kunder ser deres samtaler og opsummeringer i indbakken i Dialogbot.", "customer_docs"),
    ("fact", "Sådan kommer man i gang",
     "Man opretter en konto på dialogbot.app og følger opsætningsguiden: først virksomhed (Dialogbot læser hjemmesiden og "
     "foreslår beskrivelse, åbningstider og ydelser som kladder), så viden, så telefon og/eller chat, så eventuelt "
     "kalender, og til sidst betaling. Hverken telefon eller chat går live uden et betalt abonnement; før det kan "
     "ejeren prøve chatten i en forhåndsvisning.", "public"),
    ("fact", "Viden og godkendelse",
     "Alt, assistenten ved om virksomheden, starter som en kladde. Kun en ejer eller administrator kan godkende, og først "
     "derefter bruger assistenten det. Slettes godkendt viden, holder assistenten straks op med at bruge den. Med "
     "\"Test mig som kunde\" kan ejeren prøve assistenten, før den taler med rigtige kunder. Ydelser og priser, åbningstider, "
     "kørselsområde, faste svar og emner, den ikke må svare på, kan lægges ind.", "public"),
    ("fact", "Telefon og viderestilling",
     "Virksomheden beholder sit eget nummer og teleselskab. Dialogbot giver et Dialogbot-nummer, som man viderestiller til: "
     "altid, eller kun når man er optaget eller ikke svarer. Nummeret bekræftes med et opkald, der læser en kode på 6 cifre "
     "op. Før man tænder, kan man ringe et prøveopkald. Alle opkald ses med udskrift og opsummering under Opkald.", "public"),
    ("fact", "Booking og kalender",
     "Assistenten kan booke, flytte og aflyse tider ud fra godkendte åbningstider og bookingregler (pause mellem aftaler, "
     "tidligste tid og hvor mange dage frem). Google Kalender eller Microsoft 365 kan forbindes, og Dialogbot skriver kun nye "
     "aftaler – eksisterende aftaler røres aldrig. Optaget tid kan også læses via kalenderens hemmelige iCal-adresse. "
     "Kunden kan få en bekræftelse på SMS.", "public"),
    ("fact", "Webchat på hjemmesiden",
     "Webchatten er med i abonnementet og bruger samme godkendte viden som telefonen. Man slår den til, godkender sine domæner "
     "og sætter én kodelinje ind på hjemmesiden. Den kan tage imod henvendelser, booke tider og overgive samtalen til en "
     "medarbejder. Den fungerer på dansk, engelsk, tysk, spansk, fransk, italiensk, norsk og svensk og siger, at den er "
     "en AI.", "public"),
    ("fact", "Stemmer og sprog",
     "Standardstemmerne er Camilla (kvinde, rolig rigsdansk) og Peter (mand, let jysk klang). Virksomheden kan også optage sin "
     "egen stemme; indtaleren giver samtykke, og Dialogbot gennemgår samtykket før brug. Forkert udtalte ord, fx firmanavnet, "
     "kan rettes. Samtalesprog: dansk, engelsk, tysk, spansk, fransk, italiensk, norsk og svensk.", "public"),
    ("fact", "Hilsen og manuskript",
     "Virksomheden bestemmer selv, hvad assistenten siger først, hvilket navn den præsenterer sig med, om den dyrker du eller De, "
     "hvad den spørger kunden om, hvornår en medarbejder skal overtage, og hvad den skal undgå. Hilsenen nævner altid, at det "
     "er en digital assistent.", "public"),
    ("fact", "Opsummeringer, rapporter og team",
     "Hver henvendelse får en kort skrevet opsummering. Der er en ugerapport og en dagsrapport på e-mail, som kan slås fra. "
     "Ejer og administrator godkender viden og ændrer indstillinger; medarbejdere arbejder med henvendelser; læsere kan kun "
     "se. Alle godkendelser og ændringer logges i en aktivitetslog.", "public"),
    ("fact", "Integrationer",
     "Assistenten kan booke i Google- eller Microsoft-kalender eller Dialogbots egen kalender, sende SMS-bekræftelser og sende "
     "hændelser til Zapier, Make eller virksomhedens eget system. Kun forbundne systemer bruges, og hver handling logges. "
     "Står et system ikke som forbundet under indstillingerne, virker det ikke endnu.", "public"),
    ("fact", "Når assistenten ikke kan svare",
     "Assistenten gætter aldrig. Kan den ikke svare ud fra godkendt viden, siger den det og tager en besked med navn, nummer og "
     "behov, så virksomheden kan ringe tilbage. Den siger altid ærligt, at den er en digital assistent.", "public"),
    ("fact", "Håndværkere",
     "Til håndværkere (VVS, el, tømrer, maler, murer m.fl.) tager Dialogbot telefonen, når mester står på stigen eller under "
     "en vask: den samler opgave, adresse og hvor meget det haster i én besked, kan booke besigtigelser i kalenderen og "
     "følge op på sendte tilbud. Kunden bliver ringet tilbage af virksomheden selv; Dialogbot erstatter ikke mester.",
     "public"),
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
