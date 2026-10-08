"""One-off connection of Dialogbot's TikTok account (Meta needs no script: its long-lived Page token goes in the
environment, see docs/social-media.md).

    python -m scripts.social_connect tiktok-url  <redirect-uri>          # prints the page to open while logged in as the account
    python -m scripts.social_connect tiktok-code <redirect-uri> <code>   # exchanges the ?code=... TikTok sends back
    python -m scripts.social_connect status                              # what is connected, nothing secret

Run in the API/worker service shell (Render → Shell). The refresh token is stored encrypted in the database and
rotates by itself every time it is used; TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set.
"""
from __future__ import annotations

import sys
from urllib.parse import urlencode

from app.config import get_settings
from app.db import get_session_factory
from app.modules.social import publishers


def main(argv: list[str]) -> int:
    s = get_settings()
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "status":
        with get_session_factory()() as db:
            for platform, ok in publishers.live_configured(db).items():
                print(f"{platform}: {'forbundet' if ok else 'ikke forbundet'}")
        return 0
    if cmd in ("tiktok-url", "tiktok-code") and not (s.tiktok_client_key and s.tiktok_client_secret):
        print("TIKTOK_CLIENT_KEY og TIKTOK_CLIENT_SECRET skal være sat", file=sys.stderr)
        return 1
    if cmd == "tiktok-url" and len(argv) == 3:
        print("https://www.tiktok.com/v2/auth/authorize/?" + urlencode(
            {"client_key": s.tiktok_client_key, "scope": s.tiktok_scopes, "response_type": "code", "redirect_uri": argv[2],
             "state": "dialogbot"}))
        return 0
    if cmd == "tiktok-code" and len(argv) == 4:
        try:
            body = publishers._tiktok("/v2/oauth/token/", data={
                "client_key": s.tiktok_client_key, "client_secret": s.tiktok_client_secret, "code": argv[3],
                "grant_type": "authorization_code", "redirect_uri": argv[2]})
        except publishers.PublishError as e:
            print(f"TikTok afviste koden: {e}", file=sys.stderr)
            return 1
        if not body.get("refresh_token"):
            print("TikTok udleverede intet refresh-token", file=sys.stderr)
            return 1
        with get_session_factory()() as db:
            publishers.store_tiktok_refresh_token(db, body["refresh_token"])
            db.commit()
        print("TikTok er forbundet. Refresh-tokenet er gemt krypteret i databasen.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
