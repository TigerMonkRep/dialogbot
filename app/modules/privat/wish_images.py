"""Pictures on wishlists: a wish's product image (imported from the shop, or the owner's own photo) and a wishlist's
cover. Stored in the existing private bucket (files.py) and shown only through short-lived signed links.

Every picture is validated and re-encoded here: the type is read from the bytes (JPEG, PNG or WebP – Pillow cannot
safely decode HEIC, so iPhones' «Mest kompatibel» or a screenshot works), at most 6 MB and 40 megapixels, sides between
MIN_SIDE and MAX_SIDE. EXIF orientation is applied and all metadata (GPS!) is dropped by re-encoding. Two sizes are
written as WebP: «lg» for the detail view / cover and «sm» for cards. Keys: <workspace>/<kind>-lg/<id>.webp and
<workspace>/<kind>-sm/<id>.webp – one workspace never shares a prefix with another.
"""
from __future__ import annotations

import io
import uuid

from app.core.errors import ValidationFailed
from app.modules.privat import files

KINDS = {"oensker": (1400, 560), "cover": (2000, 900)}
MAX_PIXELS = 40_000_000
MIN_SIDE, MAX_SIDE = 64, 12_000
TYPES = {"JPEG", "PNG", "WEBP"}


def _bad(msg: str) -> ValidationFailed:
    return ValidationFailed(msg, field_errors=[{"field": "file", "message": msg}])


def process(data: bytes, kind: str) -> tuple[bytes, bytes, tuple[int, int]]:
    """(large webp, small webp, (width, height) of the large one) or ValidationFailed in Danish."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(data) > files.MAX_BYTES:
        raise _bad("Billedet er for stort (højst 6 MB)")
    if len(data) < 32:
        raise _bad("Filen er tom eller ikke et billede")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        im = Image.open(io.BytesIO(data))
        fmt = (im.format or "").upper()
        if fmt not in TYPES:
            raise _bad("Brug et billede i JPEG, PNG eller WebP")
        w, h = im.size
        if min(w, h) < MIN_SIDE:
            raise _bad(f"Billedet er for lille (mindst {MIN_SIDE} × {MIN_SIDE} pixels)")
        if max(w, h) > MAX_SIDE or w * h > MAX_PIXELS:
            raise _bad("Billedet har for mange pixels")
        im.load()
    except ValidationFailed:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as e:
        raise _bad("Filen kunne ikke læses som et billede (JPEG, PNG eller WebP)") from e
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGBA") if ("A" in im.getbands() or im.mode == "P") else im.convert("RGB")
    big, small = KINDS[kind]
    return _webp(im, big), _webp(im, small), _fit(im.size, big)


def _fit(size: tuple[int, int], box: int) -> tuple[int, int]:
    w, h = size
    s = min(1.0, box / max(w, h))
    return max(1, round(w * s)), max(1, round(h * s))


def _webp(im, box: int) -> bytes:
    from PIL import Image

    c = im.copy()
    c.thumbnail((box, box), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    c.save(out, "WEBP", quality=82, method=4)
    return out.getvalue()


def store(ws_id: uuid.UUID, data: bytes, kind: str) -> dict:
    """Validate, resize and store. Returns {key, width, height}; `key` is the large one."""
    if kind not in KINDS:
        raise ValueError(kind)
    lg, sm, (w, h) = process(data, kind)
    ident = uuid.uuid4().hex
    key = files.key_for(ws_id, f"{kind}-lg", ident, "webp")
    files.put(key, lg, "image/webp")
    files.put(files.key_for(ws_id, f"{kind}-sm", ident, "webp"), sm, "image/webp")
    return {"key": key, "width": w, "height": h}


def owns(ws_id: uuid.UUID, key: str | None, kind: str) -> bool:
    """A key the client sends back must be one of OUR keys for this workspace and kind (never another list's)."""
    return bool(key) and key.startswith(f"{ws_id}/{kind}-lg/") and key.endswith(".webp") \
        and files._KEY.match(key) is not None


def small_key(key: str) -> str:
    head, ident = key.rsplit("/", 1)
    return head[:-3] + "-sm/" + ident


def urls(key: str | None) -> dict | None:
    if not key:
        return None
    lg = files.sign(key)
    if lg is None:
        return None
    return {"url": lg, "url_sm": files.sign(small_key(key)) or lg}


def delete(key: str | None) -> None:
    if key:
        files.delete(key)
        files.delete(small_key(key))
