"""Private object storage for voice material: reference clips, speaker agreements, preview cache.

Keys are validated server-side (no absolute paths, no '..', fixed character set) and always start with a
scope: `platform/…` or `ws/<workspace_id>/…`. Nothing here is ever exposed as a public URL; the browser
only receives audio through authorised API responses.

- local: files under VOICE_STORAGE_DIR (dev/test)
- supabase: a *private* Supabase Storage bucket, called server-side with the service-role key
  (the key never reaches the browser).
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import get_settings
from app.core.errors import ApiError, ValidationFailed

KEY = re.compile(r"^(platform|ws/[0-9a-f-]{36}|cache/(platform|ws/[0-9a-f-]{36}))/[a-z0-9][a-z0-9/_.-]{0,240}$")


class StorageFailed(ApiError):
    status_code = 502
    code = "voice_storage_failed"


def check_key(key: str) -> str:
    if not KEY.match(key or "") or ".." in key or "//" in key:
        raise ValidationFailed("Ugyldig lagernøgle", field_errors=[{"field": "key"}])
    return key


def workspace_prefix(workspace_id: uuid.UUID | None) -> str:
    return f"ws/{workspace_id}" if workspace_id else "platform"


def _local_path(key: str) -> Path:
    root = Path(get_settings().voice_storage_dir).resolve()
    p = (root / check_key(key)).resolve()
    if root not in p.parents:
        raise ValidationFailed("Ugyldig lagernøgle", field_errors=[{"field": "key"}])
    return p


def _sb(path: str) -> tuple[str, dict]:
    s = get_settings()
    return (f"{s.supabase_url.rstrip('/')}/storage/v1/object/{path}",
            {"authorization": f"Bearer {s.supabase_service_role_key}", "apikey": s.supabase_service_role_key})


def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    check_key(key)
    s = get_settings()
    if s.voice_storage == "local":
        p = _local_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)
        return key
    import httpx

    url, h = _sb(f"{s.voice_bucket}/{key}")
    r = httpx.post(url, content=data, headers=h | {"content-type": content_type, "x-upsert": "true"}, timeout=60.0)
    if r.status_code >= 400:
        raise StorageFailed(f"Lagring fejlede ({r.status_code})")
    return key


def get(key: str) -> bytes | None:
    check_key(key)
    s = get_settings()
    if s.voice_storage == "local":
        p = _local_path(key)
        return p.read_bytes() if p.exists() else None
    import httpx

    url, h = _sb(f"authenticated/{s.voice_bucket}/{key}")
    r = httpx.get(url, headers=h, timeout=60.0)
    if r.status_code in (400, 404):
        return None
    if r.status_code >= 400:
        raise StorageFailed(f"Hentning fejlede ({r.status_code})")
    return r.content


def delete_prefix(prefix: str) -> int:
    """Remove cached objects under a prefix (used for cache invalidation). Local backend only walks files."""
    s = get_settings()
    if s.voice_storage == "local":
        root = Path(s.voice_storage_dir).resolve()
        base = (root / prefix).resolve()
        if root not in base.parents and base != root:
            return 0
        n = 0
        if base.exists():
            for f in base.rglob("*"):
                if f.is_file():
                    f.unlink()
                    n += 1
        return n
    return 0  # Supabase: cache keys include the version id, so stale entries are never read again
