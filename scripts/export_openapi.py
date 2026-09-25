"""Export the OpenAPI document: python -m scripts.export_openapi [path]"""
from __future__ import annotations

import json
import os
import sys

# The committed contract never includes the dev-only simulated mailbox routes.
os.environ["ENABLE_DEV_TOOLS"] = "false"
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/dialogbot")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
from app.main import create_app  # noqa: E402


def main(path: str = "docs/openapi.json") -> int:
    spec = create_app().openapi()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {path} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
