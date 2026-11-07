"""Write the market price table for the website: `python -m scripts.export_prices web/src/lib/prices.json`.

The website (Vercel builds only web/) cannot import Python, so it reads this generated JSON. CI regenerates it and
fails if the committed file differs, so a price is changed in app/modules/billing/markets.py and nowhere else."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.modules.billing.markets import export


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "web/src/lib/prices.json")
    out.write_text(json.dumps(export(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
