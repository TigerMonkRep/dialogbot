"""Fetch a reference clip from private storage and verify its checksum.

Same storage layout as the API (app/modules/voices/storage.py): local directory or a private Supabase bucket,
read with the service-role key held only by the server processes. Keys are validated; files are cached by
checksum in a temp dir.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

KEY = re.compile(r"^(platform|ws/[0-9a-f-]{36})/[a-z0-9][a-z0-9/_.-]{0,240}$")


def fetch(key: str, sha256: str, dest_dir: Path) -> Path:
    if not KEY.match(key) or ".." in key:
        raise ValueError("invalid reference key")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256 or ""):
        raise ValueError("invalid checksum")
    out = dest_dir / f"{sha256}.wav"
    if out.exists():
        return out
    backend = os.environ.get("VOICE_STORAGE", "local")
    if backend == "local":
        root = Path(os.environ.get("VOICE_STORAGE_DIR", "var/voice-store")).resolve()
        src = (root / key).resolve()
        if root not in src.parents:
            raise ValueError("invalid reference key")
        data = src.read_bytes()
    else:
        import httpx

        base, secret = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        bucket = os.environ.get("VOICE_BUCKET", "voice-private")
        r = httpx.get(f"{base}/storage/v1/object/authenticated/{bucket}/{key}", timeout=60.0,
                      headers={"authorization": f"Bearer {secret}", "apikey": secret})
        r.raise_for_status()
        data = r.content
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("reference checksum mismatch")
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(out)
    return out
