"""Support attachments (H01): screenshots, PDFs and log files a customer adds to a ticket.

- Type by content, not by the name the browser sent: PNG, JPEG, PDF (magic bytes) or plain UTF-8 text without NUL
  bytes (.txt/.log/.csv). Anything else is refused.
- At most MAX_FILES per message and MAX_BYTES per file. The web app reaches the API through its BFF on Vercel, whose
  request body limit is 4.5 MB, so one file is capped at 4 MB.
- Stored in the private object store (app/modules/voices/storage: local dir in dev/test, a private Supabase bucket in
  production) under ws/<workspace_id>/support/<ticket_id>/<sha-prefix>.<ext>. Never a public URL: the bytes are only
  served by the authorised download endpoints, always as a download (Content-Disposition: attachment, nosniff)."""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from urllib.parse import quote

from fastapi import UploadFile
from fastapi.responses import Response

from app.core.errors import NotFound, ValidationFailed
from app.models import SupportAttachment
from app.modules.voices import storage

MAX_FILES = 3
MAX_BYTES = 4 * 1024 * 1024
_MAGIC: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"%PDF-", "application/pdf", "pdf"),
]


def _kind(data: bytes) -> tuple[str, str] | None:
    for magic, ctype, ext in _MAGIC:
        if data.startswith(magic):
            return ctype, ext
    if b"\x00" in data:
        return None
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text/plain", "txt"


def safe_name(name: str | None, ext: str) -> str:
    """A display name without paths, control characters or quotes; falls back to `fil.<ext>`."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in unicodedata.normalize("NFC", base) if unicodedata.category(ch)[0] != "C")
    base = re.sub(r'["<>;]', "", base).strip(" .")[:100]
    return base or f"fil.{ext}"


def read_files(files: list[UploadFile] | None) -> list[tuple[str, bytes, str, str]]:
    """Validate the uploads before anything is written. Returns (name, data, content_type, ext) per file.
    Synchronous (the spooled file object): called from `def` endpoints, which run in the threadpool."""
    files = [f for f in (files or []) if f is not None and (f.filename or f.size)]
    if len(files) > MAX_FILES:
        raise ValidationFailed(f"Højst {MAX_FILES} filer pr. besked", field_errors=[{"field": "files"}])
    out = []
    for f in files:
        data = f.file.read(MAX_BYTES + 1)
        if not data:
            raise ValidationFailed("Filen er tom", field_errors=[{"field": "files"}])
        if len(data) > MAX_BYTES:
            raise ValidationFailed("En fil må højst fylde 4 MB", field_errors=[{"field": "files"}])
        kind = _kind(data)
        if kind is None:
            raise ValidationFailed("Vedhæft PNG, JPG, PDF eller en tekst-/logfil", field_errors=[{"field": "files"}])
        out.append((safe_name(f.filename, kind[1]), data, kind[0], kind[1]))
    return out


def store(db, *, workspace_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID, uploaded_by: uuid.UUID | None,
          files: list[tuple[str, bytes, str, str]]) -> list[SupportAttachment]:
    rows = []
    for name, data, ctype, ext in files:
        digest = hashlib.sha256(data).hexdigest()
        key = f"ws/{workspace_id}/support/{ticket_id}/{message_id.hex[:12]}-{digest[:16]}.{ext}"
        storage.put(key, data, ctype)
        row = SupportAttachment(workspace_id=workspace_id, ticket_id=ticket_id, message_id=message_id, filename=name,
                                content_type=ctype, size_bytes=len(data), sha256=digest, storage_key=key,
                                uploaded_by=uploaded_by)
        db.add(row)
        rows.append(row)
    return rows


def download(row: SupportAttachment) -> Response:
    data = storage.get(row.storage_key)
    if data is None:
        raise NotFound("Filen findes ikke længere")
    ascii_name = row.filename.encode("ascii", "replace").decode().replace("?", "_")
    return Response(content=data, media_type=row.content_type, headers={
        "content-disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(row.filename)}",
        "x-content-type-options": "nosniff", "cache-control": "no-store, private"})


def out(a: SupportAttachment) -> dict:
    return {"id": str(a.id), "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes}
