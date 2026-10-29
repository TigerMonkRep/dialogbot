"""Site documents (/public/pages, /operator/pages): the Gastro Hall manuscript page reads its encrypted blob here and
only Dialogbot operators may replace it."""


def test_pages_are_public_to_read_and_operator_only_to_write(api):
    r = api.c.get(f"{api.base}/public/pages/gastrohall")
    assert r.status_code == 404 and r.json()["code"] == "page_empty"
    assert api.c.get(f"{api.base}/public/pages/noget-andet").status_code == 404

    blob = {"v": 1, "salt": "c2FsdA==", "iv": "aXY=", "ct": "Y3Q=", "updatedAt": "2026-10-29T10:00:00Z"}
    customer = api.user("kunde@testmail.dk")
    assert api.put(customer, "/operator/pages/gastrohall", {"blob": blob}).status_code == 403
    assert api.c.put(f"{api.base}/operator/pages/gastrohall", json={"blob": blob}).status_code == 401

    op = api.operator()
    r = api.put(op, "/operator/pages/gastrohall", {"blob": blob})
    assert r.status_code == 200 and r.json()["blob"] == blob
    assert api.put(op, "/operator/pages/ukendt", {"blob": blob}).status_code == 404

    r = api.c.get(f"{api.base}/public/pages/gastrohall")
    assert r.status_code == 200 and r.json()["blob"] == blob and r.json()["updated_at"]

    blob2 = dict(blob, ct="bnk=", updatedAt="2026-10-29T11:00:00Z")
    assert api.put(op, "/operator/pages/gastrohall", {"blob": blob2}).status_code == 200
    assert api.c.get(f"{api.base}/public/pages/gastrohall").json()["blob"]["ct"] == "bnk="
