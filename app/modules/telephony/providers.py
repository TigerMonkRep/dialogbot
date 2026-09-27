"""Provider adapters for platform-managed telephony (Dialogbot's own accounts, never the customer's).

Twilio: Dialogbot's main account (TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN, or an API key) creates one technical
sub-account per workspace (usage is billed to the main account) and buys the destination number in it. The main
account's credentials manage sub-account resources by SID, so no sub-account credential is stored by Dialogbot.

Vapi: Dialogbot's private API key imports each number (provider "twilio") with the server URL and Bearer secret of
our webhook, so calls reach `/api/v1/webhooks/vapi`. Endpoints and fields follow Vapi's OpenAPI (POST/GET
/phone-number, POST /call) as read on 27/9 2026.

Every create call is preceded by a lookup for a resource carrying the same idempotency name, so a timeout followed
by a retry adopts the existing resource instead of buying or creating a second one.

TELEPHONY_PROVIDER: none (not configured, honest status) · fake (dev/test only; deterministic, can simulate
timeouts after the side effect) · live.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field

from app.config import get_settings
from app.core.errors import ApiError

TWILIO_API = "https://api.twilio.com/2010-04-01"


class ProviderError(ApiError):
    status_code = 502
    code = "telephony_provider_failed"

    def __init__(self, message: str, *, retryable: bool = True, timeout: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.timeout = timeout


class ProviderUnavailable(ApiError):
    status_code = 503
    code = "telephony_not_configured"


@dataclass
class Number:
    sid: str
    e164: str
    friendly_name: str = ""


# --------------------------------------------------------------------------- live adapters

class TwilioClient:
    def __init__(self, account_sid: str, auth: tuple[str, str]):
        self.account_sid = account_sid
        self._auth = auth  # (user, password): never logged, never returned

    def _req(self, method: str, path: str, **kw) -> dict:
        import httpx

        try:
            r = httpx.request(method, f"{TWILIO_API}{path}", auth=self._auth, timeout=20.0, **kw)
        except httpx.TimeoutException as e:
            raise ProviderError("Twilio svarede ikke i tide", timeout=True) from e
        except httpx.HTTPError as e:
            raise ProviderError("Twilio kunne ikke nås") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", "")
            except ValueError:
                msg = ""
            raise ProviderError(f"Twilio afviste ({r.status_code}): {msg[:200]}",
                                retryable=r.status_code in (429,) or r.status_code >= 500)
        return r.json() if r.content else {}

    def find_subaccount(self, friendly_name: str) -> str | None:
        out = self._req("GET", "/Accounts.json", params={"FriendlyName": friendly_name, "PageSize": 20})
        for a in out.get("accounts", []):
            if a.get("friendly_name") == friendly_name and a.get("status") != "closed":
                return a["sid"]
        return None

    def create_subaccount(self, friendly_name: str) -> str:
        return self._req("POST", "/Accounts.json", data={"FriendlyName": friendly_name})["sid"]

    def subaccount_token(self, sub_sid: str) -> str:
        """Fetched only at the moment Vapi imports the number; never stored by Dialogbot."""
        return self._req("GET", f"/Accounts/{sub_sid}.json")["auth_token"]

    def find_number(self, sub_sid: str, friendly_name: str) -> Number | None:
        out = self._req("GET", f"/Accounts/{sub_sid}/IncomingPhoneNumbers.json",
                        params={"FriendlyName": friendly_name, "PageSize": 20})
        for n in out.get("incoming_phone_numbers", []):
            if n.get("friendly_name") == friendly_name:
                return Number(n["sid"], n["phone_number"], friendly_name)
        return None

    def available(self, sub_sid: str, country: str, number_type: str) -> list[str]:
        kind = {"local": "Local", "mobile": "Mobile"}[number_type]
        out = self._req("GET", f"/Accounts/{sub_sid}/AvailablePhoneNumbers/{country}/{kind}.json",
                        params={"VoiceEnabled": "true", "PageSize": 5})
        return [n["phone_number"] for n in out.get("available_phone_numbers", [])]

    def buy(self, sub_sid: str, e164: str, friendly_name: str, bundle_sid: str | None, address_sid: str | None) -> Number:
        data = {"PhoneNumber": e164, "FriendlyName": friendly_name}
        if bundle_sid:
            data["BundleSid"] = bundle_sid
        if address_sid:
            data["AddressSid"] = address_sid
        n = self._req("POST", f"/Accounts/{sub_sid}/IncomingPhoneNumbers.json", data=data)
        return Number(n["sid"], n["phone_number"], friendly_name)


class VapiClient:
    def __init__(self, api_key: str, base: str):
        self._key = api_key
        self.base = base.rstrip("/")

    def _req(self, method: str, path: str, **kw) -> dict | list:
        import httpx

        try:
            r = httpx.request(method, f"{self.base}{path}", headers={"authorization": f"Bearer {self._key}"},
                              timeout=20.0, **kw)
        except httpx.TimeoutException as e:
            raise ProviderError("Vapi svarede ikke i tide", timeout=True) from e
        except httpx.HTTPError as e:
            raise ProviderError("Vapi kunne ikke nås") from e
        if r.status_code >= 400:
            raise ProviderError(f"Vapi afviste ({r.status_code}): {r.text[:200]}",
                                retryable=r.status_code in (429,) or r.status_code >= 500)
        return r.json() if r.content else {}

    def find_number(self, e164: str) -> str | None:
        for n in self._req("GET", "/phone-number", params={"limit": 1000}) or []:
            if n.get("number") == e164:
                return n["id"]
        return None

    def import_twilio(self, *, e164: str, account_sid: str, auth_token: str, name: str, server_url: str,
                      server_secret: str) -> str:
        body = {"provider": "twilio", "number": e164, "twilioAccountSid": account_sid, "twilioAuthToken": auth_token,
                "name": name[:40], "smsEnabled": False,
                "server": {"url": server_url, "headers": {"Authorization": f"Bearer {server_secret}"}}}
        return self._req("POST", "/phone-number", json=body)["id"]

    def call(self, payload: dict) -> str:
        return str(self._req("POST", "/call", json=payload).get("id") or "")


# --------------------------------------------------------------------------- fake adapters (dev/test)

@dataclass
class FakeWorld:
    """In-memory provider state. `fail_after` makes the next matching call perform its side effect and then raise a
    timeout, like a real network timeout after the provider already acted."""
    subaccounts: dict = field(default_factory=dict)  # friendly -> sid
    numbers: dict = field(default_factory=dict)  # sid -> Number (+ sub)
    vapi: dict = field(default_factory=dict)  # vapi id -> e164
    calls: list = field(default_factory=list)
    purchases: int = 0
    fail_after: set = field(default_factory=set)
    available_count: int = 5
    seq: itertools.count = field(default_factory=lambda: itertools.count(1))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def _maybe_timeout(self, op: str) -> None:
        if op in self.fail_after:
            self.fail_after.discard(op)
            raise ProviderError(f"{op}: timeout (simuleret)", timeout=True)


WORLD = FakeWorld()


class FakeTwilio:
    account_sid = "ACfake00000000000000000000000000"

    def find_subaccount(self, friendly_name: str) -> str | None:
        return WORLD.subaccounts.get(friendly_name)

    def create_subaccount(self, friendly_name: str) -> str:
        with WORLD.lock:
            sid = WORLD.subaccounts.setdefault(friendly_name, f"ACsub{next(WORLD.seq):027d}")
        WORLD._maybe_timeout("create_subaccount")
        return sid

    def subaccount_token(self, sub_sid: str) -> str:
        return "fake-subaccount-token"

    def find_number(self, sub_sid: str, friendly_name: str) -> Number | None:
        for n in WORLD.numbers.values():
            if n["sub"] == sub_sid and n["n"].friendly_name == friendly_name:
                return n["n"]
        return None

    def available(self, sub_sid: str, country: str, number_type: str) -> list[str]:
        base = 70100000 if number_type == "local" else 50100000
        return [f"+45{base + next(WORLD.seq)}" for _ in range(WORLD.available_count)]

    def buy(self, sub_sid: str, e164: str, friendly_name: str, bundle_sid: str | None, address_sid: str | None) -> Number:
        with WORLD.lock:
            n = Number(f"PN{next(WORLD.seq):032d}", e164, friendly_name)
            WORLD.numbers[n.sid] = {"n": n, "sub": sub_sid}
            WORLD.purchases += 1
        WORLD._maybe_timeout("buy")
        return n


class FakeVapi:
    def find_number(self, e164: str) -> str | None:
        return next((i for i, n in WORLD.vapi.items() if n == e164), None)

    def import_twilio(self, *, e164: str, account_sid: str, auth_token: str, name: str, server_url: str,
                      server_secret: str) -> str:
        with WORLD.lock:
            vid = f"vapi-{next(WORLD.seq):08d}"
            WORLD.vapi[vid] = e164
        WORLD._maybe_timeout("import")
        return vid

    def call(self, payload: dict) -> str:
        WORLD.calls.append(payload)
        return f"call-{next(WORLD.seq)}"


def providers() -> tuple[object, object] | None:
    """(twilio, vapi) for the configured mode, or None when platform telephony is not configured."""
    s = get_settings()
    if s.telephony_provider == "fake":
        return FakeTwilio(), FakeVapi()
    if s.telephony_provider != "live":
        return None
    if not (s.twilio_account_sid and (s.twilio_auth_token or (s.twilio_api_key_sid and s.twilio_api_key_secret))):
        return None
    if not (s.vapi_api_key and s.vapi_server_secret):
        return None
    auth = ((s.twilio_api_key_sid, s.twilio_api_key_secret) if s.twilio_api_key_sid and s.twilio_api_key_secret
            else (s.twilio_account_sid, s.twilio_auth_token))
    return TwilioClient(s.twilio_account_sid, auth), VapiClient(s.vapi_api_key, s.vapi_api_url)


def configuration() -> dict:
    """What is configured, as booleans only (for the operator view). Never returns a value."""
    s = get_settings()
    return {"mode": s.telephony_provider, "twilio_account": bool(s.twilio_account_sid),
            "twilio_credentials": bool(s.twilio_auth_token or (s.twilio_api_key_sid and s.twilio_api_key_secret)),
            "vapi_api_key": bool(s.vapi_api_key), "vapi_server_secret": bool(s.vapi_server_secret),
            "vapi_org_id": bool(s.vapi_org_id), "verification_number": bool(s.telephony_verify_number_id),
            "number_country": s.telephony_number_country, "number_type": s.telephony_number_type,
            "ready": providers() is not None}
