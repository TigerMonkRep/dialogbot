"""Load-test seed (QA 2026-11-13): N fictional, fully set-up business workspaces for the load test.

Each workspace gets an owner (+ a staff user), business profile, approved knowledge (services, opening hours, FAQ),
a confirmed subscription agreement (model A), an active platform phone number routed via a fake Vapi id
(`lt-pn-NNN`), an active telephony setup and an enabled webchat. Everything is labelled «loadtest-2026-11-13».

Refuses to run when APP_ENV=prod. Never touches anything but rows it creates (deterministic ids, idempotent).
The password comes from LOADTEST_PASSWORD (required).

Usage: LOADTEST_PASSWORD=... python -m scripts.loadtest.seed [--count 50] [--origin https://kunde.example]
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password, normalize_email
from app.db import get_session_factory
from app.models import (BusinessProfile, GoalSelection, KnowledgeItem, KnowledgeVersion, LanguageSettings, Membership,
                        PhoneNumber, TelephonySetup, User, WebchatSettings, Workspace)

LABEL = "loadtest-2026-11-13"
NS = uuid.UUID("7d1c0c55-2026-4111-8a13-10ad7e575eed")

TRADES = [
    ("VVS", "VVS-arbejde, badeværelser og akut vandskade"), ("Tømrer", "Tag, vinduer, døre og tilbygninger"),
    ("Frisør", "Klip, farve og bryllupsfrisurer"), ("Tandklinik", "Undersøgelse, tandrensning og akut tandpine"),
    ("Restaurant", "Bordbestilling, selskaber og take-away"), ("Elektriker", "El-installationer, ladestandere og fejlfinding"),
    ("Revisor", "Årsregnskab, moms og bogføring for små virksomheder"), ("Maler", "Indvendig og udvendig maling"),
    ("Fysioterapeut", "Behandling af ryg, nakke og idrætsskader"), ("Gulvservice", "Gulvafslibning, lak og olie"),
]
CITIES = [("Aarhus C", "8000"), ("Viby J", "8260"), ("Odense C", "5000"), ("Aalborg", "9000"), ("København Ø", "2100"),
          ("Vejle", "7100"), ("Esbjerg", "6700"), ("Randers", "8900"), ("Horsens", "8700"), ("Roskilde", "4000")]


def fixed(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, name)


def knowledge_for(trade: str, desc: str, city: str) -> list[tuple[str, str, dict]]:
    return [
        ("service", f"{trade} – standardopgave", {"description": desc, "unit": "time", "price_net_minor": 59500,
                                                  "currency": "DKK", "note": "Vejledende pris ekskl. moms"}),
        ("service", f"{trade} – akut udkald", {"description": "Hurtig hjælp samme dag, hvis muligt", "unit": "udkald",
                                               "price_net_minor": 89500, "currency": "DKK"}),
        ("opening_hours", "Åbningstider", {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri"], "open": "08:00",
                                                      "close": "16:00"}], "closed_note": "Weekend: vi ringer tilbage mandag"}),
        ("coverage_area", "Dækningsområde", {"zones": [city, "Omegn 30 km"]}),
        ("known_answer", "Kan I komme i dag?", {"question": "Kan I komme i dag?",
                                        "answer": "Ofte ja. Læg navn og nummer, så ringer vi inden for en time."}),
        ("unknown_answer", "Faste priser over 50.000 kr", {"rule": "Ingen faste priser over 50.000 kr uden besigtigelse"}),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--origin", default="https://kunde.loadtest.example")
    a = ap.parse_args()
    s = get_settings()
    if s.app_env == "prod":
        print("Refusing to seed load-test data in prod", file=sys.stderr)
        return 2
    password = os.environ.get("LOADTEST_PASSWORD")
    if not password:
        print("LOADTEST_PASSWORD is required", file=sys.stderr)
        return 2
    from app.modules.billing import agreements

    pw_hash = hash_password(password)
    db = get_session_factory()()
    now = datetime.now(UTC)
    for i in range(1, a.count + 1):
        trade, desc = TRADES[i % len(TRADES)]
        city, postal = CITIES[i % len(CITIES)]
        slug = f"lt-{i:03d}"
        name = f"{trade} {city} {i:03d} ApS ({LABEL})"
        owner_email = f"owner{i:03d}@{LABEL}.example"
        staff_email = f"staff{i:03d}@{LABEL}.example"
        users = {}
        for email, display, role in ((owner_email, f"Ejer {i:03d}", "owner"), (staff_email, f"Medarbejder {i:03d}", "staff")):
            u = db.get(User, fixed(f"user:{email}"))
            if u is None:
                u = User(id=fixed(f"user:{email}"), email=email, email_normalized=normalize_email(email),
                         password_hash=pw_hash, display_name=display, email_verified_at=now, signup_intent="reception")
                db.add(u)
            users[role] = u
        db.flush()
        w = db.get(Workspace, fixed(f"ws:{slug}"))
        if w is not None:
            continue
        w = Workspace(id=fixed(f"ws:{slug}"), name=name, slug=f"{slug}-{LABEL}", product_intent="reception",
                      created_by=users["owner"].id)
        db.add(w)
        db.flush()
        db.add(BusinessProfile(workspace_id=w.id, legal_name=name, version=1, description=desc, city=city,
                               postal_code=postal, country="DK", timezone="Europe/Copenhagen", manual_setup=True))
        db.add(GoalSelection(workspace_id=w.id, product_intent="reception", version=1, inbound_phone=True,
                             callback=True, booking=False))
        db.add(LanguageSettings(workspace_id=w.id, version=1, enabled_conversation_languages=["da"]))
        for role, u in users.items():
            db.add(Membership(workspace_id=w.id, user_id=u.id, role=role))
        for kind, title, content in knowledge_for(trade, desc, city):
            key = f"{kind}:{title.lower().replace(' ', '-')[:80]}"
            item = KnowledgeItem(id=fixed(f"ki:{slug}:{key}"), workspace_id=w.id, kind=kind, key=key)
            db.add(item)
            db.flush()
            db.add(KnowledgeVersion(item_id=item.id, workspace_id=w.id, version_no=1, status="approved", title=title,
                                    content=content, source_type="manual", created_by=users["owner"].id,
                                    approved_by=users["owner"].id, approved_at=now, submitted_at=now))
        w.knowledge_revision = 6
        agreements.create(db, w.id, "A", users["owner"].id)
        num = PhoneNumber(id=fixed(f"pn:{slug}"), workspace_id=w.id, e164=f"+4570990{i:03d}", provider="vapi",
                          provider_number_id=f"lt-pn-{i:03d}", label=LABEL, active=True, source="platform",
                          status="active")
        db.add(num)
        db.flush()
        db.add(TelephonySetup(workspace_id=w.id, business_number=f"+4588990{i:03d}", business_number_verified_at=now,
                              business_number_verified_by="loadtest", documents_status="not_required", state="active",
                              destination_number_id=num.id, verify_sent=[], company_name=name))
        db.add(WebchatSettings(workspace_id=w.id, enabled=True, widget_key=f"wk_lt{i:03d}_{uuid.uuid4().hex[:24]}",
                               allowed_origins=[a.origin], greeting=""))
        db.commit()
    db.commit()
    n = db.scalar(select(Workspace.id).where(Workspace.slug.like(f"lt-%-{LABEL}")).limit(1))
    print(f"Seed complete: {a.count} workspaces labelled {LABEL} (first id {n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
