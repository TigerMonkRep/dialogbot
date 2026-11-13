"""W04 in tests: prove a phone number in the chat's «Bliv kontaktet» with the SMS code (simulated SMS, read back from
the fake world like a person reads their phone)."""
from __future__ import annotations

import re

PUB = "/api/v1/public/webchat"
FRAME_ORIGIN = "http://localhost:8000"


def last_code(e164: str) -> str:
    from app.modules.integrations.connectors.fakes import WORLD
    from app.worker import runner

    runner.drain()  # the code SMS is sent by the worker (app/modules/integrations/sms_codes.py)
    sms = [m for m in WORLD.sms if m["to"] == e164]
    assert sms, f"no SMS to {e164}"
    return re.search(r"\b(\d{6})\b", sms[-1]["body"]).group(1)


def request_code(client, key: str, conv: dict, phone: str, *, send: bool = True):
    """POST the code request; `send` lets the worker deliver the queued SMS right after (as it does within a second)."""
    from app.worker import runner

    r = client.post(f"{PUB}/{key}/conversations/{conv['conversation_id']}/contact/code", json={"phone": phone},
                    headers={"origin": FRAME_ORIGIN, "x-visitor-token": conv["visitor_token"]})
    if send:
        runner.drain()
    return r


def submit_code(client, key: str, conv: dict, verification_id: str, code: str):
    return client.post(f"{PUB}/{key}/conversations/{conv['conversation_id']}/contact/verify",
                       json={"verification_id": verification_id, "code": code},
                       headers={"origin": FRAME_ORIGIN, "x-visitor-token": conv["visitor_token"]})


def verify_phone(client, key: str, conv: dict, phone: str, e164: str) -> None:
    r = request_code(client, key, conv, phone)
    assert r.status_code == 202, r.text
    v = submit_code(client, key, conv, r.json()["verification_id"], last_code(e164))
    assert v.status_code == 200, v.text


def prove_phone(client, key: str, conversation_id, headers: dict, phone: str) -> None:
    """W04 before the booking door (F-VER1113-04): the visitor proves `phone` with the SMS code in this conversation,
    using the request's own headers (origin + x-visitor-token)."""
    from app.modules.customer.service import normalize
    from app.worker import runner

    base = f"{PUB}/{key}/conversations/{conversation_id}"
    r = client.post(f"{base}/contact/code", json={"phone": phone}, headers=headers)
    assert r.status_code == 202, r.text
    runner.drain()
    v = client.post(f"{base}/contact/verify", json={"verification_id": r.json()["verification_id"],
                                                     "code": last_code(normalize(phone))}, headers=headers)
    assert v.status_code == 200, v.text
