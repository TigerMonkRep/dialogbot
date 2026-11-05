"""Photos a Privat user adds to an app (the receipt in Garanti & kvitteringer), in a PRIVATE Supabase Storage bucket
(PRIVAT_FILES_BUCKET, default `privat-files`) reached with the server-side service key. Nothing is public: the app gets a
5-minute signed link. Without Supabase credentials (dev/test) files go to a local directory.

Keys are `<workspace_id>/<app>/<item>.<ext>`: one workspace never shares a prefix with another. Only JPEG, PNG, WebP and
HEIC up to 6 MB; the type is read from the file's first bytes, never trusted from the browser."""
from __future__ import annotations

import hashlib
import hmac
import re
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.core.errors import ApiError, ValidationFailed

MAX_BYTES = 6 * 1024 * 1024
SIGNED_SECONDS = 300
_KEY = re.compile(r"^[0-9a-f-]{36}/[a-z-]{2,40}/[0-9a-f]{6,40}\.(jpg|png|webp|heic)$")


class StorageFailed(ApiError):
    status_code = 502
    code = "storage_failed"


def sniff(data: bytes) -> tuple[str, str]:
    """(extension, content type) from the magic bytes, or ValidationFailed."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypmsf1"):
        return "heic", "image/heic"
    raise ValidationFailed("Det skal være et billede (JPEG, PNG, WebP eller HEIC)", field_errors=[{"field": "file"}])


def key_for(ws_id: uuid.UUID, app: str, item_id: str, ext: str) -> str:
    key = f"{ws_id}/{app}/{item_id}.{ext}"
    if not _KEY.match(key):
        raise ValidationFailed("Ugyldigt filnavn", field_errors=[{"field": "file"}])
    return key


def _remote() -> bool:
    s = get_settings()
    return bool(s.supabase_url and s.supabase_service_role_key)


def _local(key: str) -> Path:
    return Path(get_settings().voice_storage_dir).resolve() / "privat-files" / key


def _sb(path: str) -> tuple[str, dict]:
    s = get_settings()
    return (f"{s.supabase_url.rstrip('/')}/storage/v1/{path}",
            {"authorization": f"Bearer {s.supabase_service_role_key}", "apikey": s.supabase_service_role_key})


def put(key: str, data: bytes, content_type: str) -> str:
    if not _KEY.match(key):
        raise StorageFailed("Ugyldig lagernøgle")
    if len(data) > MAX_BYTES:
        raise ValidationFailed("Billedet er for stort (højst 6 MB)", field_errors=[{"field": "file"}])
    s = get_settings()
    if not _remote():
        if s.app_env in ("staging", "prod"):
            raise StorageFailed("Billeder kan ikke gemmes endnu – lageret er ikke sat op")
        p = _local(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key
    import httpx

    url, h = _sb(f"object/{s.privat_files_bucket}/{key}")
    r = httpx.post(url, content=data, headers=h | {"content-type": content_type, "x-upsert": "true"}, timeout=60.0)
    if r.status_code >= 400:
        raise StorageFailed(f"Billedet kunne ikke gemmes ({r.status_code})")
    return key


def sign(key: str | None, seconds: int = SIGNED_SECONDS) -> str | None:
    """A short-lived link, or None (never raises: a missing photo must not break the app)."""
    if not key or not _KEY.match(key):
        return None
    s = get_settings()
    if not _remote():
        exp = int(time.time()) + seconds
        sig = hmac.new(s.secret_key.encode(), f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"local://privat-files/{key}?exp={exp}&sig={sig}"
    import httpx

    url, h = _sb(f"object/sign/{s.privat_files_bucket}/{key}")
    try:
        r = httpx.post(url, json={"expiresIn": seconds}, headers=h, timeout=15.0)
        rel = r.json().get("signedURL") if r.status_code < 400 else None
    except (httpx.HTTPError, ValueError):
        return None
    return f"{s.supabase_url.rstrip('/')}/storage/v1{rel if rel.startswith('/') else '/' + rel}" if rel else None


def delete(key: str | None) -> None:
    """Best effort: a photo left behind is removed with the workspace prefix later; never blocks the user."""
    if not key or not _KEY.match(key):
        return
    if not _remote():
        p = _local(key)
        if p.exists():
            p.unlink()
        return
    import httpx

    s = get_settings()
    url, h = _sb(f"object/{s.privat_files_bucket}")
    try:
        httpx.request("DELETE", url, json={"prefixes": [key]}, headers=h, timeout=30.0)
    except httpx.HTTPError:
        pass
