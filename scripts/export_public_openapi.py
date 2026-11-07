"""Export the public API's OpenAPI document: python -m scripts.export_public_openapi [path]

The document is the contract of api.dialogbot.app/v1 (docs/public-openapi.json, versioned in git). CI compares it
with the committed file, so a change to the public schemas is always a deliberate, reviewed diff.
"""
from __future__ import annotations

import json
import os
import sys

os.environ["ENABLE_DEV_TOOLS"] = "false"
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/dialogbot")
os.environ.setdefault("PUBLIC_API_BASE_URL", "https://api.dialogbot.app")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
from app.modules.public_api.app import create_public_app  # noqa: E402


def main(path: str = "docs/public-openapi.json") -> int:
    spec = create_public_app().openapi()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {path} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
