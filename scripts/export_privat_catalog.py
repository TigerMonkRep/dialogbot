"""Write the Privat app catalog for the web's simulation: `python -m scripts.export_privat_catalog
web/src/lib/privat/addons-catalog.json`.

The web's fake API (web/src/lib/privat/fake.ts, used for demos and the e2e journeys) shows the SAME apps as the backend
– keys, names, texts, prices and plan rules come from app/modules/privat/addons.py and nowhere else. CI regenerates it
and fails if the committed file differs. Status is the catalog's own (an app waiting for an API key is «coming_soon»)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.modules.privat import addons


def export() -> list[dict]:
    out = []
    for a in addons.CATALOG.values():
        status = "coming_soon" if a.needs_setting else a.status  # without its key/config an app is «Kommer snart»
        out.append({"key": a.key, "name": a.name, "tagline": a.tagline, "description": a.description, "icon": a.icon,
                    "category": a.category, "price_text": a.price_text, "pricing": a.pricing,
                    "monthly_price_minor": a.monthly_price_minor, "status": status, "what": a.what,
                    "example": a.example, "steps": list(a.steps), "needs": list(a.needs),
                    "permissions": list(a.permissions), "requires": list(a.requires),
                    "included_in": list(a.included_in), "requires_plan": bool(a.included_in)})
    return out


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "web/src/lib/privat/addons-catalog.json")
    out.write_text(json.dumps(export(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
