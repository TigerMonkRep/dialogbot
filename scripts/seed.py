"""Deterministic demo seed: two isolated workspaces.

Refuses to run when APP_ENV=prod. The demo password comes from
SEED_DEMO_PASSWORD; if unset, a random one is generated and printed ONCE, so a
known default password is never installed anywhere.

Usage: python -m scripts.seed
"""
from __future__ import annotations

import os
import secrets
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password, normalize_email
from app.db import get_session_factory
from app.models import (
    BusinessProfile,
    GoalSelection,
    KnowledgeItem,
    KnowledgeVersion,
    LanguageSettings,
    Membership,
    User,
    Workspace,
    WorkspaceCategory,
)

NS = uuid.UUID("2b9f3a5e-0d3c-4c7e-9c8f-1e1f2f3a4b5c")


def fixed(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, name)


USERS = [  # email, name, role in ws A, role in ws B
    ("owner@fjordgulv.example", "Mads Fjord", "owner", None),
    ("admin@fjordgulv.example", "Signe Holm", "admin", None),
    ("staff@fjordgulv.example", "Jonas Bech", "staff", None),
    ("reader@fjordgulv.example", "Revisor Kim", "reader", None),
    ("owner@havnebord.example", "Lene Havn", None, "owner"),
]

# Fixture from canonical-demo-data.json (fictional; not production terms)
FJORD_KNOWLEDGE = [
    ("service", "Standard gulvafslibning inkl. 2x klar lak",
     {"description": "Afslibning af fyrretræ og egeparket", "unit": "m2", "price_net_minor": 14500, "currency": "DKK",
      "note": "Vejledende pris ekskl. moms"}),
    ("service", "Hvidpigmenteret lud- og sæbebehandling",
     {"description": "Behandling til lyse plankegulve", "unit": "m2", "price_net_minor": 19000, "currency": "DKK"}),
    ("opening_hours", "Telefontider",
     {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri"], "open": "07:30", "close": "16:00"}],
      "closed_note": "Weekend og helligdage: tager kun imod besked"}),
    ("coverage_area", "Dækningsområde", {"zones": ["Hovedstadsområdet", "Nordsjælland"]}),
    ("unknown_answer", "Bærende undergulve og asbestlim",
     {"rule": "Assistenten udtaler sig ikke om bærende undergulve, asbestlim eller faste priser over 50.000 kr uden godkendelse"}),
    ("offer", "Efterårsrabat på gulvafslibning",
     {"discount_percent": 15, "condition": {"area_operator": "gte", "area_threshold_m2": 40},
      "starts_on": "2026-10-01", "ends_on_inclusive": "2026-11-30",
      "applies_to_platform_prices": False}),
]


def main() -> int:
    s = get_settings()
    if s.app_env == "prod":
        print("Refusing to seed demo data in prod", file=sys.stderr)
        return 2
    password = os.environ.get("SEED_DEMO_PASSWORD")
    generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True
    db = get_session_factory()()
    now = datetime.now(UTC)
    users: dict[str, User] = {}
    for email, name, _, _ in USERS:
        u = db.get(User, fixed(f"user:{email}"))
        if u is None:
            u = User(id=fixed(f"user:{email}"), email=email, email_normalized=normalize_email(email),
                     password_hash=hash_password(password), display_name=name, email_verified_at=now,
                     signup_intent="both" if "fjord" in email else "reception")
            db.add(u)
        else:
            u.password_hash = hash_password(password)
        users[email] = u
    db.flush()

    def ws(name: str, slug: str, intent: str, owner: User, profile: dict, cats: list, booking: bool) -> Workspace:
        w = db.get(Workspace, fixed(f"ws:{slug}"))
        if w is None:
            w = Workspace(id=fixed(f"ws:{slug}"), name=name, slug=slug, product_intent=intent, created_by=owner.id)
            db.add(w)
            db.flush()
            db.add(BusinessProfile(workspace_id=w.id, legal_name=name, version=2, **profile))
            db.add(GoalSelection(workspace_id=w.id, product_intent=intent, version=2,
                                 inbound_phone=intent != "campaigns", callback=intent != "campaigns",
                                 booking=booking))
            db.add(LanguageSettings(workspace_id=w.id, version=2, enabled_conversation_languages=["da", "en"]))
            for i, (slug_, label, custom) in enumerate(cats):
                db.add(WorkspaceCategory(workspace_id=w.id, slug=slug_, label=label, is_custom=custom,
                                         is_primary=i == 0, position=i))
        return w

    ws_a = ws("Fjord Gulvservice ApS", "fjord-gulvservice", "both", users["owner@fjordgulv.example"],
              {"description": "Professionel gulvafslibning, lakering og rådgivning i Storkøbenhavn og Nordsjælland",
               "cvr": "38291044", "city": "København", "postal_code": "2100", "country": "DK",
               "timezone": "Europe/Copenhagen", "manual_setup": True},
              [("haandvaerk-gulvservice", "Håndværk & Gulvservice", False),
               ("overfladebehandling-traepleje", "Overfladebehandling & Træpleje", False),
               ("poolservice", "Poolservice og vedligeholdelse", True)], booking=True)
    ws_b = ws("Havnebord Café & Catering", "havnebord-cafe", "reception", users["owner@havnebord.example"],
              {"description": "Bordreservation, selskabsforespørgsler og menu-assistent på havnen i Hundested",
               "city": "Hundested", "postal_code": "3390", "country": "DK", "timezone": "Europe/Copenhagen",
               "manual_setup": True},
              [("restaurant-catering", "Restaurant og catering", False)], booking=False)

    for email, _name, role_a, role_b in USERS:
        for w, role in ((ws_a, role_a), (ws_b, role_b)):
            if role and not db.scalar(select(Membership).where(Membership.workspace_id == w.id,
                                                                 Membership.user_id == users[email].id)):
                db.add(Membership(workspace_id=w.id, user_id=users[email].id, role=role))

    owner_a = users["owner@fjordgulv.example"]
    revision = 0
    for kind, title, content in FJORD_KNOWLEDGE:
        key = f"{kind}:{title.lower().replace(' ', '-')[:80]}"
        item = db.scalar(select(KnowledgeItem).where(KnowledgeItem.workspace_id == ws_a.id,
                                                     KnowledgeItem.kind == kind, KnowledgeItem.key == key))
        if item is None:
            item = KnowledgeItem(id=fixed(f"ki:{key}"), workspace_id=ws_a.id, kind=kind, key=key)
            db.add(item)
            db.flush()
            db.add(KnowledgeVersion(item_id=item.id, workspace_id=ws_a.id, version_no=1, status="approved",
                                    title=title, content=content, source_type="manual", created_by=owner_a.id,
                                    approved_by=owner_a.id, approved_at=now, submitted_at=now))
            revision += 1
    if revision:
        ws_a.knowledge_revision = (ws_a.knowledge_revision or 0) + revision
    # Workspace B: one open draft (in review) so the plan shows a real pending action
    key_b = "service:bordreservation"
    if not db.scalar(select(KnowledgeItem).where(KnowledgeItem.workspace_id == ws_b.id, KnowledgeItem.key == key_b)):
        item = KnowledgeItem(id=fixed(f"ki:{key_b}"), workspace_id=ws_b.id, kind="service", key=key_b)
        db.add(item)
        db.flush()
        db.add(KnowledgeVersion(item_id=item.id, workspace_id=ws_b.id, version_no=1, status="in_review",
                                title="Bordreservation", content={"description": "Reservation af borde til 2-12 personer"},
                                source_type="manual", created_by=users["owner@havnebord.example"].id, submitted_at=now))
    db.commit()
    print("Seed complete. Workspaces:", ws_a.slug, "/", ws_b.slug)
    print("Demo users:", ", ".join(e for e, *_ in USERS))
    if generated:
        print(f"Generated demo password (shown once, not stored anywhere else): {password}")
    else:
        print("Demo password: taken from SEED_DEMO_PASSWORD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
