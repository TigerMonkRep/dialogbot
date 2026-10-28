"""One offer, written once: the subscription from 2.495 kr./md. and 4 kr. per outbound campaign call, both excl. VAT.
These tests keep the old prices (1.495 kr., 149 kr. per approved enquiry, 9 kr. per contact) from creeping back into
any text a customer, a visitor, a salesperson or an AI can read."""
from __future__ import annotations

import re
from pathlib import Path

from app.modules.billing import agreements, prices

ROOT = Path(__file__).resolve().parent.parent

# Where old prices legitimately still appear: code that keeps old agreements and old months readable, and history.
ALLOWED = {
    "app/modules/billing/agreements.py", "app/modules/billing/statement.py", "app/modules/billing/money.py",
    "app/modules/leads/service.py", "app/models/domain.py", "app/modules/leads/router.py",
    "app/modules/voices/danish.py",  # a number-reading example in a comment, not a price statement

    "web/src/app/app/(admin)/leads/client.tsx", "web/src/app/app/(admin)/billing/page.tsx",
    "web/src/app/app/(admin)/settings/agreement/client.tsx",  # shows an old model-B agreement honestly
}
SCANNED = ["app", "web/src", "web/public/materiale", "web/public/llms.txt", "design-reference/byggevejledning",
           "docs/social-media.md", "docs/sales", "docs/ambassadors", "docs/telephony"]
OLD = re.compile(r"1\.495|\b149 kr|\b149,00|pr\. godkendt henvendelse|[Mm]odel [AB]\b|kontaktpakke|9 kr\. pr\. kontakt|9,00 kr")
SUFFIXES = {".py", ".ts", ".tsx", ".html", ".txt", ".md"}


def _files():
    for entry in SCANNED:
        p = ROOT / entry
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and f.suffix in SUFFIXES and "node_modules" not in f.parts and ".next" not in f.parts \
                    and "__pycache__" not in f.parts:
                yield f


def test_list_prices():
    assert prices.SUBSCRIPTION_MONTHLY_NET_MINOR == 249_500 and prices.CAMPAIGN_CALL_NET_MINOR == 400
    assert (prices.kr(249_500), prices.kr(400), prices.kr(450)) == ("2.495", "4", "4,50")
    assert agreements.TAX_BASIS_POINTS == 2500


def test_the_old_prices_are_gone_everywhere_a_person_or_an_ai_can_read():
    hits = []
    for f in _files():
        rel = f.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if OLD.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:110]}")
    assert not hits, "old price or price model found:\n" + "\n".join(hits)


def test_the_public_pages_state_both_prices():
    pricing = (ROOT / "web/src/app/priser/page.tsx").read_text(encoding="utf-8")
    llms = (ROOT / "web/public/llms.txt").read_text(encoding="utf-8")
    for text in (pricing, llms):
        assert "2.495 kr." in text and "4 kr. pr." in text and "ekskl. moms" in text
    assert "Fra 2.495 kr./md." in (ROOT / "web/src/app/byggevejledning/page.tsx").read_text(encoding="utf-8")
    assert "Fra 2.495 kr./md." in (ROOT / "web/src/app/(public)/page.tsx").read_text(encoding="utf-8")
