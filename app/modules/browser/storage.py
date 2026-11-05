"""Evidence storage for browser runs: a PRIVATE Supabase Storage bucket (BROWSER_EVIDENCE_BUCKET, default
`browser-evidence`), reached with the server-side service key. Objects are never public: callers only ever get a
short-lived signed link (`sign`). Without Supabase credentials (dev/test) files go to a local directory and `sign` returns
an HMAC-signed `local://` link that only proves the shape and the expiry.

Keys are `<workspace_id>/<run_id>/<kind>-<n>.<ext>`: a run's evidence never shares a prefix with another workspace's.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.core.errors import ApiError

SIGNED_URL_SECONDS = 300
_KEY_RE = re.compile(r"^[0-9a-f-]{36}/[0-9a-f-]{36}/[a-z_]+-\d{1,4}\.(png|webm|pdf|mp4)$")


class StorageFailed(ApiError):
    status_code = 502
    code = "storage_failed"


def evidence_key(workspace_id: uuid.UUID, run_id: uuid.UUID, kind: str, n: int, ext: str) -> str:
    return f"{workspace_id}/{run_id}/{kind}-{n}.{ext}"


def check_key(key: str) -> str:
    if not _KEY_RE.match(key or ""):
        raise StorageFailed("Ugyldig lagernøgle")
    return key


def _remote() -> bool:
    s = get_settings()
    return bool(s.supabase_url and s.supabase_service_role_key)


def _local_root() -> Path:
    return Path(get_settings().voice_storage_dir).resolve() / "browser-evidence"


def _sb(path: str) -> tuple[str, dict]:
    s = get_settings()
    return (f"{s.supabase_url.rstrip('/')}/storage/v1/{path}",
            {"authorization": f"Bearer {s.supabase_service_role_key}", "apikey": s.supabase_service_role_key})


def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    check_key(key)
    s = get_settings()
    if not _remote():
        if s.app_env in ("staging", "prod"):
            raise StorageFailed("Bevis-lageret er ikke konfigureret")
        p = _local_root() / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key
    import httpx

    url, h = _sb(f"object/{s.browser_evidence_bucket}/{key}")
    r = httpx.post(url, content=data, headers=h | {"content-type": content_type, "x-upsert": "true"}, timeout=60.0)
    if r.status_code >= 400:
        raise StorageFailed(f"Lagring fejlede ({r.status_code})")
    return key


def sign(key: str, seconds: int = SIGNED_URL_SECONDS) -> str | None:
    """A link that works for `seconds` and then stops working. None when the link cannot be made (never raises: a
    missing screenshot must not break the run page)."""
    check_key(key)
    s = get_settings()
    if not _remote():
        exp = int(time.time()) + seconds
        sig = hmac.new(s.secret_key.encode(), f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"local://browser-evidence/{key}?exp={exp}&sig={sig}"
    import httpx

    url, h = _sb(f"object/sign/{s.browser_evidence_bucket}/{key}")
    try:
        r = httpx.post(url, json={"expiresIn": seconds}, headers=h, timeout=15.0)
        if r.status_code >= 400:
            return None
        rel = r.json().get("signedURL") or ""
    except (httpx.HTTPError, ValueError):
        return None
    if not rel:
        return None
    return f"{s.supabase_url.rstrip('/')}/storage/v1{rel if rel.startswith('/') else '/' + rel}"


def delete(keys: list[str]) -> int:
    keys = [check_key(k) for k in keys]
    if not keys:
        return 0
    s = get_settings()
    if not _remote():
        n = 0
        for k in keys:
            p = _local_root() / k
            if p.exists():
                p.unlink()
                n += 1
        return n
    import httpx

    url, h = _sb(f"object/{s.browser_evidence_bucket}")
    r = httpx.request("DELETE", url, json={"prefixes": keys}, headers=h, timeout=60.0)
    if r.status_code >= 400:
        raise StorageFailed(f"Sletning fejlede ({r.status_code})")
    return len(keys)
