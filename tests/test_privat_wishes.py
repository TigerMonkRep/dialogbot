"""Dialogbot Privat: wishes with product details, «Indsæt link» / «Søg efter produkt», group gifts and the wishlist's
design. Integration tests against PostgreSQL; network fetches are replaced (safe_fetch._open / resolve)."""
from __future__ import annotations

import io
import json
import threading

import pytest
from fastapi.testclient import TestClient

from app.models import PrivateGiftPledge, PrivateGroupGift, PrivateTask, PrivateTaskEvent, PrivateTaskItem
from app.modules.privat import product_meta, safe_fetch, wish_design, wishes


def _share(api, tok, tid, mode="wishlist"):
    r = api.post(tok, f"/privat/tasks/{tid}/share", {"mode": mode, "role": "editor"})
    assert r.status_code == 200, r.text
    return r.json()


def _accept(api, tok, token):
    r = api.post(tok, f"/privat/invites/{token}/accept")
    assert r.status_code == 200, r.text
    return r.json()


def _item(task, text):
    return next(i for i in task["items"] if i["text"] == text)


def _wishlist(api, pv, *, share=True):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    out = pv.say(mette, "Lav en ønskeliste med bog")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    if not share:
        return mette, None, None, tid
    inv = _share(api, mette, tid)
    ole, anna = pv.user("ole@testmail.dk", "Ole Berg"), pv.user("anna@testmail.dk", "Anna Holm")
    _accept(api, ole, inv["token"])
    _accept(api, anna, inv["token"])
    return mette, ole, anna, tid


def _gift_wish(api, mette, tid, target=300000, **extra):
    body = {"text": "Cykel", "price_minor": 349900, "currency": "DKK", "group_gift_enabled": True,
            "group_gift_target_minor": target, **extra}
    r = api.post(mette, f"/privat/tasks/{tid}/wishes", body)
    assert r.status_code == 200, r.text
    return _item(r.json(), "Cykel")["id"]


def _pledge(api, tok, tid, iid, amount, **headers):
    return api.c.put(f"/api/v1/privat/tasks/{tid}/items/{iid}/gift/pledge", json={"amount_minor": amount},
                     headers=api.h(tok, **headers))


def _gift(api, tok, tid, iid):
    return _item_by_id(api.get(tok, f"/privat/tasks/{tid}").json(), iid)["group_gift"]


def _item_by_id(task, iid):
    return next(i for i in task["items"] if i["id"] == iid)


def _png(w=400, h=300, color=(200, 30, 30)) -> bytes:
    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


# --------------------------------------------------------------------------- the wish form / data model

def test_manual_wish_without_link_and_with_own_photo(api, pv, db):
    mette, _o, _a, tid = _wishlist(api, pv, share=False)
    r = api.c.post("/api/v1/privat/wishes/images", content=_png(), headers=api.h(mette, **{"content-type": "image/png"}))
    assert r.status_code == 200, r.text
    key = r.json()["image_key"]
    assert r.json()["image"]["url"].startswith("local://privat-files/") and "/oensker-lg/" in key
    body = {"text": "En dag i Tivoli med mig", "note": "En oplevelse – ingen link", "image_key": key,
            "image_origin": "upload", "quantity": 2}
    t = api.post(mette, f"/privat/tasks/{tid}/wishes", body).json()
    w = _item(t, "En dag i Tivoli med mig")
    assert (w["link"], w["price_minor"], w["quantity"], w["image_origin"]) == (None, None, 2, "upload")
    assert w["image"]["url_sm"] and "/oensker-sm/" in w["image"]["url_sm"]
    assert w["group_gift"] == {"enabled": False, "target_minor": None, "currency": None}
    # the old list endpoint and old items keep working (backward compatible)
    t = api.post(mette, f"/privat/tasks/{tid}/items", {"text": "Ur", "note": "sort", "link": "https://ur.dk/x"}).json()
    assert (_item(t, "Ur")["quantity"], _item(t, "Ur")["image"], _item(t, "Bog")["price_minor"]) == (1, None, None)
    # a key from another workspace (or kind) is refused
    other = pv.account("x@testmail.dk", "X")
    k2 = api.c.post("/api/v1/privat/wishes/images", content=_png(), headers=api.h(other, **{"content-type": "image/png"})).json()
    r = api.patch(mette, f"/privat/tasks/{tid}/wishes/{w['id']}", {"image_key": k2["image_key"]})
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "image_key"


def test_image_validation(api, pv):
    mette = pv.account("mette@testmail.dk")
    h = api.h(mette, **{"content-type": "image/png"})
    assert api.c.post("/api/v1/privat/wishes/images", content=b"<svg onload=alert(1)>" * 10, headers=h).status_code == 422
    assert api.c.post("/api/v1/privat/wishes/images", content=_png(20, 20), headers=h).status_code == 422
    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", (100, 100)).save(b, "GIF")
    assert api.c.post("/api/v1/privat/wishes/images", content=b.getvalue(), headers=h).json()["code"] == "validation_failed"


def test_price_defaults_and_edit(api, pv):
    mette, _o, _a, tid = _wishlist(api, pv, share=False)
    t = api.post(mette, f"/privat/tasks/{tid}/wishes", {"text": "Sko", "price_minor": 79900, "size": "str. 42",
                                                       "color": "mørkeblå"}).json()
    w = _item(t, "Sko")
    assert (w["currency"], w["price_source"], w["size"], w["color"]) == ("DKK", "user", "str. 42", "mørkeblå")
    t = api.patch(mette, f"/privat/tasks/{tid}/wishes/{w['id']}", {"price_minor": None}).json()
    assert _item(t, "Sko")["price_minor"] is None and _item(t, "Sko")["price_source"] is None
    r = api.patch(mette, f"/privat/tasks/{tid}/wishes/{w['id']}", {"currency": "kr"})
    assert r.status_code == 422


# --------------------------------------------------------------------------- import and search

PAGE = """<html><head><title>Cykel X | Shop</title>
<meta property="og:site_name" content="Cykelshoppen">
<meta property="og:image" content="/img/x.png">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"ProductGroup","name":"Cykel X",
 "brand":{"@type":"Brand","name":"Velo"},"image":"https://shop.example.com/img/x.png",
 "hasVariant":[
  {"@type":"Product","name":"Cykel X – 54 cm, rød","size":"54 cm","color":"Rød","sku":"X54R",
   "offers":{"@type":"Offer","url":"https://shop.example.com/cykel-x?variant=54r","price":"3499.00","priceCurrency":"DKK",
   "availability":"https://schema.org/InStock"}},
  {"@type":"Product","name":"Cykel X – 58 cm, blå","size":"58 cm","color":"Blå","sku":"X58B",
   "offers":{"@type":"Offer","url":"https://shop.example.com/cykel-x?variant=58b","price":"3699.00","priceCurrency":"DKK",
   "availability":"https://schema.org/OutOfStock"}}]}</script>
<script>window.evil = true; fetch('http://169.254.169.254/')</script></head><body>Læg i kurv 3.499 kr.</body></html>"""


@pytest.fixture
def web(monkeypatch):
    """A fake internet: public hosts resolve to a public address; pages and images are served from `pages`."""
    pages: dict[str, tuple[int, dict, bytes]] = {}
    calls: list[str] = []

    def resolve(host):
        return {"shop.example.com": ["93.184.216.34"], "evil.example.com": ["10.0.0.5"],
                "rebind.example.com": ["93.184.216.35", "127.0.0.1"]}.get(host, ["93.184.216.36"])

    def _open(url, *, max_bytes, accept):
        safe_fetch.check_url(url)
        calls.append(url)
        status, headers, body = pages.get(url, (404, {"content-type": "text/html"}, b"<html>nej</html>"))
        if len(body) > max_bytes:
            raise safe_fetch.FetchFailed("too large")
        return status, headers, body

    monkeypatch.setattr(safe_fetch, "resolve", resolve)
    monkeypatch.setattr(safe_fetch, "_open", _open)
    pages["https://shop.example.com/img/x.png"] = (200, {"content-type": "image/png"}, _png())
    return pages, calls


def test_import_reads_structured_data_and_keeps_the_variant(api, pv, web):
    pages, _calls = web
    pages["https://shop.example.com/cykel-x?variant=54r"] = (200, {"content-type": "text/html; charset=utf-8"},
                                                            PAGE.encode())
    mette, _o, _a, tid = _wishlist(api, pv, share=False)
    r = api.post(mette, "/privat/wishes/import",
                 {"link": "https://shop.example.com/cykel-x?variant=54r&utm_source=nyhedsbrev&fbclid=abc"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["readable"] is True and p["link"] == "https://shop.example.com/cykel-x?variant=54r"  # variant kept
    assert (p["title"], p["price_minor"], p["currency"], p["shop"]) == ("Cykel X", 349900, "DKK", "Cykelshoppen")
    assert (p["size"], p["color"], p["variant"]) == ("54 cm", "Rød", "Cykel X – 54 cm, rød")
    assert p["options"]["sizes"] == ["54 cm", "58 cm"] and p["details"]["availability"] == "in_stock"
    assert p["image_key"] and p["image"]["url"]  # downloaded, validated and stored by us
    body = {k: p[k] for k in ("title", "link", "price_minor", "currency", "shop", "size", "color", "variant",
                              "image_key", "details")}
    body["text"] = body.pop("title")
    body |= {"price_source": "shop", "price_fetched_at": p["fetched_at"], "image_origin": "shop"}
    t = api.post(mette, f"/privat/tasks/{tid}/wishes", body).json()
    w = _item(t, "Cykel X")
    assert (w["price_source"], w["price_fetched_at"][:10], w["details"]["brand"]) == ("shop", "2026-11-04", "Velo")


def test_import_unreadable_keeps_link_and_never_guesses(api, pv, web):
    pages, _ = web
    pages["https://shop.example.com/tekst"] = (200, {"content-type": "text/html"},
                                               b"<html><title>Fin vase</title><body>Kun 299 kr. Pa lager!</body></html>")
    mette, _o, _a, tid = _wishlist(api, pv, share=False)
    p = api.post(mette, "/privat/wishes/import", {"link": "shop.example.com/tekst"}).json()
    assert p["link"] == "https://shop.example.com/tekst"
    assert p.get("price_minor") is None and p.get("currency") is None  # a price in running text is NOT used
    p = api.post(mette, "/privat/wishes/import", {"link": "https://shop.example.com/findes-ikke"}).json()
    assert (p["readable"], p["reason"], p["link"]) == (False, "unreachable", "https://shop.example.com/findes-ikke")
    t = api.post(mette, f"/privat/tasks/{tid}/wishes", {"text": "Vase", "link": p["link"]}).json()  # still saved
    assert _item(t, "Vase")["link"] == "https://shop.example.com/findes-ikke"


@pytest.mark.parametrize("link", ["http://127.0.0.1/admin", "http://localhost/", "https://evil.example.com/",
                                  "https://rebind.example.com/", "file:///etc/passwd", "http://[::1]/",
                                  "http://169.254.169.254/latest/meta-data", "https://shop.example.com:8443/",
                                  "https://user:pw@shop.example.com/", "http://[::ffff:10.0.0.1]/"])
def test_import_ssrf_is_refused(api, pv, web, link):
    _pages, calls = web
    mette = pv.account("mette@testmail.dk")
    r = api.post(mette, "/privat/wishes/import", {"link": link})
    if link.startswith("file:"):
        assert r.status_code == 422  # «https://file:///…» is not a web address either
    else:
        assert r.status_code == 422 and r.json()["code"] == "validation_failed", r.text
    assert calls == []


def test_redirect_to_internal_address_is_blocked(api, pv, web):
    pages, calls = web
    pages["https://shop.example.com/r"] = (302, {"location": "http://10.0.0.7/secret"}, b"")
    mette = pv.account("mette@testmail.dk")
    p = api.post(mette, "/privat/wishes/import", {"link": "https://shop.example.com/r"}).json()
    assert (p["readable"], p["reason"]) == (False, "blocked") and calls == ["https://shop.example.com/r"]


def test_body_size_limit(api, pv, web):
    pages, _ = web
    pages["https://shop.example.com/stor"] = (200, {"content-type": "text/html"}, b"a" * (safe_fetch.HTML_MAX_BYTES + 1))
    mette = pv.account("mette@testmail.dk")
    assert api.post(mette, "/privat/wishes/import", {"link": "https://shop.example.com/stor"}).json()["readable"] is False


def test_public_address_check():
    for ip in ("10.1.2.3", "192.168.1.1", "172.16.0.1", "127.0.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
               "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "224.0.0.1"):
        import ipaddress

        assert not safe_fetch._public(ipaddress.ip_address(ip)), ip
    import ipaddress

    assert safe_fetch._public(ipaddress.ip_address("93.184.216.34"))


def test_search_unavailable_without_web_search(api, pv):
    mette = pv.account("mette@testmail.dk")
    r = api.get(mette, "/privat/wishes/search?q=cykel")
    assert r.status_code == 503 and r.json()["code"] == "search_unavailable"


def test_search_reads_real_pages(api, pv, web, monkeypatch):
    pages, _ = web
    from app.modules.privat import links

    pages["https://shop.example.com/cykel-x?variant=54r"] = (200, {"content-type": "text/html"}, PAGE.encode())
    monkeypatch.setattr(wishes, "search_available", lambda: True)
    monkeypatch.setattr(links, "search_candidates", lambda q, city: ([
        {"url": "https://shop.example.com/cykel-x?variant=54r", "shop": "X", "price": "1 kr.", "title": "Opdigtet"},
        {"url": "https://shop.example.com/findes-ikke", "shop": "Y", "price": "2 kr.", "title": "Y"},
        {"url": "https://shop.example.com/search?q=cykel", "shop": "Z", "price": None, "title": "Z"}], None))
    mette = pv.account("mette@testmail.dk")
    r = api.get(mette, "/privat/wishes/search?q=cykel")
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert len(res) == 1 and (res[0]["title"], res[0]["price_minor"]) == ("Cykel X", 349900)  # the page's, not the model's


def test_product_meta_units():
    assert product_meta.to_minor("1.299,00", "DKK") == 129900
    assert product_meta.to_minor("1299.5", "DKK") == 129950
    assert product_meta.to_minor("1,299.00", "EUR") == 129900
    assert product_meta.to_minor("2.000", "DKK") == 200000
    assert product_meta.to_minor(-5, "DKK") is None and product_meta.to_minor("gratis", "DKK") is None
    og = product_meta.parse('<meta property="og:title" content="Lampe"><meta property="product:price:amount" '
                            'content="499"><meta property="product:price:currency" content="DKK">', "https://a.dk/l")
    assert (og["title"], og["price_minor"], og["currency"]) == ("Lampe", 49900, "DKK")
    nocur = product_meta.parse('<script type="application/ld+json">{"@type":"Product","name":"P","offers":{"price":"9"}}'
                               '</script>', "https://a.dk/p")
    assert "price_minor" not in nocur  # never a price without its currency


# --------------------------------------------------------------------------- group gifts

def test_group_gift_3000_with_750_and_500(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    g = _gift(api, ole, tid, iid)
    assert (g["status"], g["target_minor"], g["remaining_minor"], g["participants"]) == ("open", 300000, 300000, 0)
    assert _pledge(api, ole, tid, iid, 75000).status_code == 200
    assert _pledge(api, anna, tid, iid, 50000).status_code == 200
    g = _gift(api, anna, tid, iid)
    assert (g["pledged_minor"], g["remaining_minor"], g["participants"], g["my_pledge_minor"]) == (125000, 175000, 2, 50000)
    assert _gift(api, ole, tid, iid)["my_pledge_minor"] == 75000  # each sees only their own amount
    assert "50000" not in json.dumps(_gift(api, ole, tid, iid)["my_pledge_minor"])


def test_change_cancel_double_click_and_idempotency(api, pv, db):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    for _ in range(3):  # double click / retry: one pledge, same total
        assert _pledge(api, ole, tid, iid, 75000).status_code == 200
    assert _gift(api, ole, tid, iid)["pledged_minor"] == 75000
    assert db.query(PrivateGiftPledge).count() == 1
    assert _pledge(api, ole, tid, iid, 100000, **{"Idempotency-Key": "k1"}).status_code == 200
    assert _pledge(api, ole, tid, iid, 100000, **{"Idempotency-Key": "k1"}).status_code == 200
    assert _pledge(api, ole, tid, iid, 20000, **{"Idempotency-Key": "k1"}).json()["code"] == "idempotency_payload_mismatch"
    _pledge(api, anna, tid, iid, 50000)
    assert _gift(api, anna, tid, iid)["pledged_minor"] == 150000
    r = api.delete(ole, f"/privat/tasks/{tid}/items/{iid}/gift/pledge")
    assert r.status_code == 200 and api.delete(ole, f"/privat/tasks/{tid}/items/{iid}/gift/pledge").status_code == 200
    g = _gift(api, anna, tid, iid)
    assert (g["pledged_minor"], g["participants"], g["remaining_minor"]) == (50000, 1, 250000)
    _pledge(api, ole, tid, iid, 10000)  # re-join reuses the row
    assert db.query(PrivateGiftPledge).count() == 2 and _gift(api, ole, tid, iid)["pledged_minor"] == 60000


def test_over_remaining_is_refused_not_silently_changed(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    _pledge(api, ole, tid, iid, 250000)
    r = _pledge(api, anna, tid, iid, 80000)
    assert r.status_code == 409 and r.json()["code"] == "pledge_exceeds_remaining" and r.json()["remaining_minor"] == 50000
    assert _gift(api, anna, tid, iid)["pledged_minor"] == 250000 and _gift(api, anna, tid, iid)["my_pledge_minor"] is None
    assert _pledge(api, anna, tid, iid, 50000).status_code == 200  # the confirmed proposal
    g = _gift(api, anna, tid, iid)
    assert (g["status"], g["remaining_minor"]) == ("full", 0)
    r = _pledge(api, pv.user("bo@testmail.dk", "Bo"), tid, iid, 100)
    assert r.status_code == 404  # not a member at all
    for bad in (0, -5):
        assert _pledge(api, ole, tid, iid, bad).status_code == 422


def test_concurrent_pledges_never_exceed_target(api, pv, app):
    mette, ole, anna, tid = _wishlist(api, pv)
    givers = [ole, anna] + [pv.user(f"g{i}@testmail.dk", f"G{i}") for i in range(4)]
    inv = _share(api, mette, tid)
    for g in givers[2:]:
        _accept(api, g, inv["token"])
    iid = _gift_wish(api, mette, tid, target=100000)
    barrier = threading.Barrier(len(givers))
    codes: list[int] = []

    def go(tok):
        c = TestClient(app)
        barrier.wait()
        r = c.put(f"/api/v1/privat/tasks/{tid}/items/{iid}/gift/pledge", json={"amount_minor": 30000},
                  headers={"Authorization": f"Bearer {tok}"})
        codes.append(r.status_code)

    threads = [threading.Thread(target=go, args=(t,)) for t in givers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 200, 200, 409, 409, 409], codes
    g = _gift(api, ole, tid, iid)
    assert (g["pledged_minor"], g["participants"], g["remaining_minor"]) == (90000, 3, 10000)


def test_owner_and_outsiders_cannot_see_or_touch_the_agreement(api, pv, db):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    before = db.get(PrivateTask, __import__("uuid").UUID(tid)).updated_at
    n_events = db.query(PrivateTaskEvent).count()
    _pledge(api, ole, tid, iid, 75000)
    api.post(ole, f"/privat/tasks/{tid}/items/{iid}/gift/coordinator", {"action": "take"})
    own = api.get(mette, f"/privat/tasks/{tid}").json()
    w = _item_by_id(own, iid)
    assert w["group_gift"] == {"enabled": True, "target_minor": 300000, "currency": "DKK"}
    blob = json.dumps(own, ensure_ascii=False).lower()
    for secret in ("75000", "pledged", "participants", "coordinator", "ole berg\", \"role\": \"coord", "remaining"):
        assert secret not in blob, secret
    db.expire_all()
    assert db.get(PrivateTask, __import__("uuid").UUID(tid)).updated_at == before
    assert db.query(PrivateTaskEvent).count() == n_events
    for method, path, body in (("put", "gift/pledge", {"amount_minor": 100}), ("delete", "gift/pledge", None),
                               ("post", "gift/coordinator", {"action": "take"}), ("post", "gift/bought", {"bought": True})):
        r = api.c.request(method.upper(), f"/api/v1/privat/tasks/{tid}/items/{iid}/{path}", json=body, headers=api.h(mette))
        assert r.status_code == 403 and r.json()["code"] == "owner_cannot_give", (path, r.text)
        assert "75000" not in r.text
    stranger = pv.account("x@testmail.dk", "X")
    assert api.get(stranger, f"/privat/tasks/{tid}").status_code == 404
    assert _pledge(api, stranger, tid, iid, 100).status_code == 404
    # bootstrap and day of the owner do not carry it either
    assert "75000" not in json.dumps(api.get(mette, "/privat/bootstrap").json())


def test_one_giver_cannot_change_another_ones_pledge(api, pv, db):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    _pledge(api, ole, tid, iid, 75000)
    _pledge(api, anna, tid, iid, 10000)
    api.delete(anna, f"/privat/tasks/{tid}/items/{iid}/gift/pledge")  # only her own
    assert _gift(api, ole, tid, iid)["my_pledge_minor"] == 75000
    rows = {p.amount_minor: p.status for p in db.query(PrivateGiftPledge)}
    assert rows == {75000: "active", 10000: "cancelled"}


def test_coordinator_role_handover_and_bought(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    co = lambda tok, **b: api.post(tok, f"/privat/tasks/{tid}/items/{iid}/gift/coordinator", b)  # noqa: E731
    assert co(ole, action="take").json()["code"] == "gift_not_started"
    _pledge(api, ole, tid, iid, 200000)
    _pledge(api, anna, tid, iid, 100000)
    assert _gift(api, ole, tid, iid)["status"] == "full"  # the sum never marks it bought
    assert co(ole, action="take").status_code == 200
    assert co(anna, action="take").json()["code"] == "has_coordinator"  # cannot just grab it
    assert api.post(anna, f"/privat/tasks/{tid}/items/{iid}/gift/bought", {"bought": True}).status_code == 403
    ref = _gift(api, ole, tid, iid)["participant_names"][0]["user_ref"]
    assert co(ole, action="transfer", to=ref).status_code == 200
    assert _gift(api, anna, tid, iid)["pending_coordinator_is_me"] is True
    assert _gift(api, ole, tid, iid)["coordinator"]["is_me"] is True  # still Ole until Anna accepts
    assert co(anna, action="accept").status_code == 200
    g = _gift(api, anna, tid, iid)
    assert g["is_coordinator"] is True and _gift(api, ole, tid, iid)["coordinator"]["name"] == "Anna"
    assert api.post(anna, f"/privat/tasks/{tid}/items/{iid}/gift/bought", {"bought": True}).status_code == 200
    assert _gift(api, ole, tid, iid)["status"] == "bought"
    assert _pledge(api, ole, tid, iid, 1000).json()["code"] == "gift_bought"
    assert api.delete(ole, f"/privat/tasks/{tid}/items/{iid}/gift/pledge").json()["code"] == "gift_bought"
    assert "bought" not in json.dumps(_item_by_id(pv.task(mette, tid).json(), iid))


def test_target_is_frozen_after_first_pledge(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    api.patch(mette, f"/privat/tasks/{tid}/wishes/{iid}", {"group_gift_target_minor": 200000})  # before: follows
    assert _gift(api, ole, tid, iid)["target_minor"] == 200000
    _pledge(api, ole, tid, iid, 75000)
    r = api.patch(mette, f"/privat/tasks/{tid}/wishes/{iid}", {"group_gift_target_minor": 500000, "price_minor": 999900})
    assert r.status_code == 200
    assert _gift(api, ole, tid, iid)["target_minor"] == 200000  # the agreement stays put
    assert _item_by_id(r.json(), iid)["group_gift"]["target_minor"] == 500000  # the owner sees their own setting only


def test_group_gift_needs_positive_target(api, pv):
    mette, _o, _a, tid = _wishlist(api, pv, share=False)
    r = api.post(mette, f"/privat/tasks/{tid}/wishes", {"text": "X", "group_gift_enabled": True})
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "group_gift_target_minor"


def test_reservations_and_group_gifts_exclude_each_other(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    bog = _item(pv.task(ole, tid).json(), "Bog")["id"]
    # 1) a pledge blocks a separate reservation
    _pledge(api, ole, tid, iid, 1000)
    r = api.post(anna, f"/privat/tasks/{tid}/items/{iid}/reserve")
    assert r.status_code == 409 and r.json()["code"] == "group_gift_active"
    # 2) a reservation blocks a group gift (the owner switched it on after someone reserved)
    api.post(anna, f"/privat/tasks/{tid}/items/{bog}/reserve")
    api.patch(mette, f"/privat/tasks/{tid}/wishes/{bog}", {"group_gift_enabled": True, "group_gift_target_minor": 30000})
    assert _gift(api, ole, tid, bog)["can_join"] is False
    assert _pledge(api, ole, tid, bog, 1000).json()["code"] == "already_reserved"
    assert _gift(api, anna, tid, bog)["reserved_by_me"] is True
    api.post(anna, f"/privat/tasks/{tid}/items/{bog}/unreserve")
    assert _pledge(api, ole, tid, bog, 1000).status_code == 200


def test_owner_removing_the_wish_archives_the_agreement(api, pv, db):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    _pledge(api, ole, tid, iid, 75000)
    r = api.delete(mette, f"/privat/tasks/{tid}/items/{iid}")
    assert r.status_code == 200 and all(i["id"] != iid for i in r.json()["items"])  # gone for the owner
    g = _gift(api, ole, tid, iid)
    assert (g["status"], g["cancel_reason"], g["my_pledge_minor"]) == ("cancelled", "wish_removed", 75000)
    assert _item_by_id(pv.task(ole, tid).json(), iid)["archived"] is True
    assert all(i["id"] != iid for i in pv.task(anna, tid).json()["items"])  # Anna had no pledge on it
    assert db.query(PrivateTaskItem).count() == 2 and db.query(PrivateGroupGift).one().status == "cancelled"
    assert _pledge(api, ole, tid, iid, 100).json()["code"] == "group_gift_off"
    # a wish without an agreement is really deleted
    bog = _item(pv.task(mette, tid).json(), "Bog")["id"]
    api.delete(mette, f"/privat/tasks/{tid}/items/{bog}")
    assert db.query(PrivateTaskItem).count() == 1


def test_owner_switching_off_cancels_open_agreement(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    _pledge(api, ole, tid, iid, 75000)
    api.patch(mette, f"/privat/tasks/{tid}/wishes/{iid}", {"group_gift_enabled": False})
    assert _gift(api, ole, tid, iid)["status"] == "cancelled"
    assert _gift(api, anna, tid, iid) is None
    api.patch(mette, f"/privat/tasks/{tid}/wishes/{iid}", {"group_gift_enabled": True, "group_gift_target_minor": 100000})
    g = _gift(api, anna, tid, iid)
    assert (g["status"], g["target_minor"], g["pledged_minor"]) == ("open", 100000, 0)  # a fresh agreement


def test_member_leaving_ends_their_pledge(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid)
    _pledge(api, ole, tid, iid, 75000)
    me = next(m for m in pv.task(ole, tid).json()["members"] if m["is_me"])
    api.delete(ole, f"/privat/tasks/{tid}/members/{me['id']}")
    assert _gift(api, anna, tid, iid)["pledged_minor"] == 0


# --------------------------------------------------------------------------- design

def test_design_save_reload_reset_and_same_for_givers(api, pv, db):
    mette, ole, anna, tid = _wishlist(api, pv)
    t0 = pv.task(mette, tid).json()
    assert t0["design"]["theme"] == "neutral" and t0["design"]["customized"] is False
    up = api.c.post(f"/api/v1/privat/tasks/{tid}/design/cover", content=_png(1600, 900),
                    headers=api.h(mette, **{"content-type": "image/png"}))
    assert up.status_code == 200, up.text
    body = {"title": "Mettes 40 års fødselsdag", "design": {
        "theme": "foedselsdag", "accent": "#7A1F45", "subtitle": "Tak fordi du kigger", "date": "2026-12-12",
        "font": "serif", "decorations": False, "cover": {"key": up.json()["key"], "zoom": 1.4, "x": 30, "y": 60}}}
    r = api.put(mette, f"/privat/tasks/{tid}/design", body)
    assert r.status_code == 200, r.text
    for tok in (mette, ole):  # reloaded, the same for owner and givers
        d = pv.task(tok, tid).json()["design"]
        assert (d["theme"], d["accent"], d["background"], d["font"], d["decorations"]) == \
            ("foedselsdag", "#7A1F45", "#FFF8EC", "serif", False)
        assert d["cover"]["zoom"] == 1.4 and d["cover"]["url"] and d["subtitle"] == "Tak fordi du kigger"
    assert pv.task(ole, tid).json()["title"] == "Mettes 40 års fødselsdag"
    n_items = len(pv.task(mette, tid).json()["items"])
    r = api.put(mette, f"/privat/tasks/{tid}/design", {"design": None})  # «Nulstil til tema» → saved
    assert r.json()["design"]["theme"] == "neutral" and len(r.json()["items"]) == n_items
    assert len(r.json()["members"]) == 3
    # givers cannot change it; another list is untouched
    assert api.put(ole, f"/privat/tasks/{tid}/design", body).status_code == 403
    other = pv.make_list(mette, "Lav en ønskeliste med te")
    assert pv.task(mette, other).json()["design"]["customized"] is False


def test_design_validation(api, pv):
    mette, _o, _a, tid = _wishlist(api, pv, share=False)
    put = lambda d: api.put(mette, f"/privat/tasks/{tid}/design", {"design": d})  # noqa: E731
    assert put({"theme": "hacker"}).status_code == 422
    assert put({"theme": "jul", "text": "red; background:url(x)"}).status_code == 422
    assert put({"theme": "jul", "text": "#FAF6EE"}).json()["field_errors"][0]["field"] == "text"  # unreadable
    assert put({"theme": "jul", "accent": "#FFE680"}).json()["field_errors"][0]["field"] == "accent"
    assert put({"theme": "jul", "font": "Comic Sans"}).status_code == 422
    assert put({"theme": "jul", "cover": {"key": "../../etc/passwd"}}).status_code == 422
    shop = pv.make_list(mette)
    assert api.put(mette, f"/privat/tasks/{shop}/design", {"design": {"theme": "jul"}}).json()["code"] == "not_a_wishlist"


def test_every_theme_is_readable():
    for key, th in wish_design.THEMES.items():
        assert wish_design.contrast(th["text"], th["background"]) >= 4.5, key
        assert wish_design.contrast("#FFFFFF", th["accent"]) >= 4.5, key
        assert wish_design.contrast(th["accent"], th["background"]) >= 3, key
    assert len(wish_design.THEMES) >= 10


def test_web_theme_palette_matches_backend():
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "web", "src", "lib", "privat", "wish-themes.json")
    web = json.load(open(path, encoding="utf-8"))
    assert {k: {kk: v[kk] for kk in ("accent", "background", "text", "font")} for k, v in web["themes"].items()} \
        == wish_design.THEMES
    assert set(web["fonts"]) == set(wish_design.FONTS)


def test_existing_wishlist_and_invite_still_work(api, pv):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    out = pv.say(mette, "Lav en ønskeliste med cykel")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    inv = _share(api, mette, tid)
    ole = pv.user("ole@testmail.dk", "Ole")
    t = _accept(api, ole, inv["token"])
    cykel = _item(t, "Cykel")
    assert cykel["group_gift"] is None and cykel["quantity"] == 1
    assert api.post(ole, f"/privat/tasks/{tid}/items/{cykel['id']}/reserve").status_code == 200
    p = api.c.get(f"/api/v1/privat/invites/by-code/{inv['short_code']}").json()
    assert p["item_count"] == 1 and p["group_gift_count"] == 0
