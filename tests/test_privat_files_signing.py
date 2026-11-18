"""Signed links for Privat pictures: one request to Supabase for a whole list, reused for ten minutes.

Before this every response that showed a wishlist signed each picture and size with its own request on a new
connection, so saving or deleting one wish took seconds. Supabase is replaced by a fake client that counts calls."""
from __future__ import annotations

import uuid

import pytest

from app.config import get_settings
from app.modules.privat import files, wish_images

WS = uuid.UUID("11111111-1111-4111-8111-111111111111")


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class _Supabase:
    def __init__(self):
        self.signs: list[list[str]] = []
        self.deletes: list[list[str]] = []
        self.missing: set[str] = set()

    def post(self, url, json, headers):
        assert url.endswith("/storage/v1/object/sign/privat-files") and headers["authorization"].startswith("Bearer ")
        assert json["expiresIn"] == files.SIGN_FOR
        self.signs.append(list(json["paths"]))
        return _Resp(200, [{"path": p, "error": "not found", "signedURL": None} if p in self.missing else
                           {"path": p, "error": None, "signedURL": f"/object/sign/privat-files/{p}?token=t{len(self.signs)}"}
                           for p in json["paths"]])

    def request(self, method, url, json, headers):
        assert method == "DELETE" and url.endswith("/storage/v1/object/privat-files")
        self.deletes.append(list(json["prefixes"]))
        return _Resp(200, [])


@pytest.fixture
def sb(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "abcdefgh.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    get_settings.cache_clear()
    fake = _Supabase()
    monkeypatch.setattr(files, "_http", lambda: fake)
    files._signed.clear()
    yield fake
    files._signed.clear()
    get_settings.cache_clear()


def _key(n: int) -> str:
    return f"{WS}/oensker-lg/{n:012x}.webp"


def test_a_whole_list_is_signed_with_one_request_and_then_served_from_the_cache(sb):
    keys = [_key(n) for n in range(14)]
    wish_images.prime(keys)
    assert len(sb.signs) == 1 and len(sb.signs[0]) == 28  # both sizes of all 14 pictures
    out = [wish_images.urls(k) for k in keys]
    assert len(sb.signs) == 1  # writing the list out asks Supabase nothing more
    assert out[0]["url"] == f"https://abcdefgh.supabase.co/storage/v1/object/sign/privat-files/{keys[0]}?token=t1"
    assert "/oensker-sm/" in out[0]["url_sm"]
    wish_images.prime(keys)  # the next response (after a save, a delete …)
    assert len(sb.signs) == 1


def test_only_new_pictures_are_asked_for_and_an_expired_link_is_renewed(sb, monkeypatch):
    wish_images.prime([_key(1)])
    wish_images.prime([_key(1), _key(2)])
    assert sb.signs[1] == [_key(2), wish_images.small_key(_key(2))]
    clock = files.time.monotonic()
    monkeypatch.setattr(files.time, "monotonic", lambda: clock + files.CACHE_FOR + 1)
    assert files.sign(_key(1)).endswith("token=t3")  # past the cache time: a fresh link, never a stale one
    assert files.SIGN_FOR - files.CACHE_FOR >= files.SIGNED_SECONDS  # a cached link always has 5 minutes left


def test_delete_is_one_request_and_forgets_the_links(sb):
    wish_images.prime([_key(1)])
    wish_images.delete(_key(1))
    assert sb.deletes == [[_key(1), wish_images.small_key(_key(1))]]
    assert _key(1) not in files._signed and wish_images.small_key(_key(1)) not in files._signed


def test_missing_small_size_falls_back_and_bad_keys_never_reach_supabase(sb):
    sb.missing.add(wish_images.small_key(_key(3)))
    u = wish_images.urls(_key(3))
    assert u["url_sm"] == u["url"]
    assert files.sign("../../etc/passwd") is None and files.sign(None) is None
    assert files.sign_many(["not a key"]) == {}
    assert all(p.startswith(str(WS)) for call in sb.signs for p in call)
