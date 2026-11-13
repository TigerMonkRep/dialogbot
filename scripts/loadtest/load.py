"""Load generator (QA 2026-11-13): N concurrent simulated inbound calls + webchat visitors + logged-in dashboards.

ONLY for a temporary or local environment running with fakes (TELEPHONY_PROVIDER/CONNECTORS_PROVIDER/AI_PROVIDER=fake).
It refuses the production host. Every call is a sequence of signed Vapi webhooks (the e2e test secret), nothing is
dialled and no model is called.

Per simulated call: assistant-request -> status-update(in-progress) -> tool-calls -> status-update(ended) ->
end-of-call-report, with think time in between; on a share of calls the report is sent twice at once (Vapi retries)
to check that nothing is processed twice.

Usage:
  LOADTEST_PASSWORD=... VAPI_SERVER_SECRET=... python -m scripts.loadtest.load --base http://localhost:8200 \
      --workspaces 50 --calls 10 --chat 50 --dash 50 --duration 300 --out result.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import httpx

LABEL = "loadtest-2026-11-13"
FORBIDDEN_HOSTS = ("dialogbot-api-staging.onrender.com", "api.dialogbot.dk", "api.dialogbot.app", "dialogbot.app",
                   "dialogbot.dk", "dialogbot-public-api.onrender.com")


class Stats:
    def __init__(self) -> None:
        self.lat: dict[str, list[float]] = defaultdict(list)
        self.status: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.errors: list[str] = []
        self.call_ids: list[str] = []
        self.dup_sent: int = 0
        self.calls_done = 0
        self.chat_msgs = 0

    def rec(self, kind: str, ms: float, code: int | str) -> None:
        self.lat[kind].append(ms)
        self.status[kind][str(code)] += 1

    def summary(self) -> dict:
        out = {}
        allv: list[float] = []
        tot = err = 0
        for k, v in sorted(self.lat.items()):
            v2 = sorted(v)
            allv += v2
            n = len(v2)
            bad = sum(c for s, c in self.status[k].items() if not s.startswith("2"))
            tot += n
            err += bad
            out[k] = {"n": n, "p50": pct(v2, 50), "p95": pct(v2, 95), "p99": pct(v2, 99), "max": round(v2[-1], 1),
                      "errors": bad, "status": dict(self.status[k])}
        allv.sort()
        out["_all"] = {"n": tot, "p50": pct(allv, 50), "p95": pct(allv, 95), "p99": pct(allv, 99),
                       "error_rate": round(err / tot, 4) if tot else None}
        return out


def pct(v: list[float], p: float) -> float | None:
    if not v:
        return None
    k = min(len(v) - 1, max(0, round(p / 100 * (len(v) - 1))))
    return round(v[k], 1)


async def req(st: Stats, c: httpx.AsyncClient, kind: str, method: str, url: str, **kw) -> httpx.Response | None:
    t = time.perf_counter()
    try:
        r = await c.request(method, url, **kw)
        st.rec(kind, (time.perf_counter() - t) * 1000, r.status_code)
        if r.status_code >= 500 and len(st.errors) < 200:
            st.errors.append(f"{kind} {r.status_code} {r.text[:200]}")
        return r
    except Exception as e:  # timeouts, connection resets
        st.rec(kind, (time.perf_counter() - t) * 1000, type(e).__name__)
        if len(st.errors) < 200:
            st.errors.append(f"{kind} {type(e).__name__}: {str(e)[:150]}")
        return None


def vapi_msg(kind: str, i: int, call_id: str, caller: str, **extra) -> dict:
    msg = {"type": kind, "call": {"id": call_id, "type": "inboundPhoneCall", "phoneNumberId": f"lt-pn-{i:03d}",
                                  "customer": {"number": caller}},
           "phoneNumber": {"id": f"lt-pn-{i:03d}", "number": f"+4570990{i:03d}"}}
    msg.update(extra)
    return {"message": msg}


async def call_loop(st: Stats, c: httpx.AsyncClient, base: str, secret: str, n_ws: int, stop: float, slot: int,
                    think: float, dup_share: float) -> None:
    h = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    url = f"{base}/api/v1/webhooks/vapi"
    rnd = random.Random(slot)
    while time.monotonic() < stop:
        i = rnd.randint(1, n_ws)
        call_id = f"{LABEL}-{uuid.uuid4()}"
        caller = f"+452{rnd.randint(1000000, 9999999)}"
        started = datetime.now(UTC)
        r = await req(st, c, "call.assistant-request", "POST", url, headers=h,
                      json=vapi_msg("assistant-request", i, call_id, caller))
        if r is not None and r.status_code == 200 and "assistant" not in r.json():
            st.errors.append(f"assistant-request without assistant: {r.text[:150]}")
        await asyncio.sleep(think * rnd.uniform(0.5, 1.5))
        await req(st, c, "call.status-update", "POST", url, headers=h,
                  json=vapi_msg("status-update", i, call_id, caller, status="in-progress"))
        await asyncio.sleep(think * rnd.uniform(0.5, 1.5))
        tc = {"toolCallList": [{"id": f"tc-{uuid.uuid4().hex[:8]}", "type": "function",
                                "function": {"name": "create_callback_request",
                                             "arguments": {"name": "Test Testesen", "phone": caller}}}]}
        await req(st, c, "call.tool-calls", "POST", url, headers=h, json=vapi_msg("tool-calls", i, call_id, caller, **tc))
        await asyncio.sleep(think * rnd.uniform(0.5, 1.5))
        await req(st, c, "call.status-update", "POST", url, headers=h,
                  json=vapi_msg("status-update", i, call_id, caller, status="ended", endedReason="customer-ended-call"))
        ended = datetime.now(UTC)
        report = vapi_msg("end-of-call-report", i, call_id, caller, startedAt=started.isoformat(),
                          endedAt=ended.isoformat(), durationSeconds=int((ended - started).total_seconds()) + 60,
                          endedReason="customer-ended-call", cost=0.12,
                          analysis={"summary": f"Kunden vil gerne ringes op om et tilbud ({LABEL})."},
                          artifact={"messages": [
                              {"role": "bot", "message": "Hej, du har ringet til os. Hvad kan jeg hjælpe med?"},
                              {"role": "user", "message": "Hej, jeg vil gerne have et tilbud på en opgave i næste uge."},
                              {"role": "bot", "message": "Det kan vi godt. Må vi ringe dig op på det nummer du ringer fra?"},
                              {"role": "user", "message": "Ja tak, det er fint."},
                              {"role": "bot", "message": "Tak for opkaldet, hav en god dag."}]})
        if rnd.random() < dup_share:  # Vapi retry: the same report twice at once
            st.dup_sent += 1
            await asyncio.gather(req(st, c, "call.end-of-call-report", "POST", url, headers=h, json=report),
                                 req(st, c, "call.end-of-call-report", "POST", url, headers=h, json=report))
        else:
            await req(st, c, "call.end-of-call-report", "POST", url, headers=h, json=report)
        st.call_ids.append(call_id)
        st.calls_done += 1


async def chat_loop(st: Stats, c: httpx.AsyncClient, base: str, key: str, stop: float, slot: int, think: float) -> None:
    rnd = random.Random(1000 + slot)
    h = {"Origin": base, "Content-Type": "application/json"}
    texts = ["Hvad koster det?", "Hvornår har I åbent?", "Kan I komme i dag?", "Dækker I mit område?",
             "Hvad koster et akut udkald?", "Tak for hjælpen"]
    await asyncio.sleep(rnd.uniform(0, think))
    while time.monotonic() < stop:
        await req(st, c, "chat.status", "GET", f"{base}/api/v1/public/webchat/{key}/status",
                  headers={"Origin": "https://kunde.loadtest.example"})
        r = await req(st, c, "chat.start", "POST", f"{base}/api/v1/public/webchat/{key}/conversations", headers=h,
                      json={"host_origin": "https://kunde.loadtest.example"})
        if r is None or r.status_code != 201:
            await asyncio.sleep(think)
            continue
        d = r.json()
        hv = dict(h, **{"X-Visitor-Token": d["visitor_token"]})
        for _ in range(rnd.randint(2, 4)):
            if time.monotonic() >= stop:
                break
            await asyncio.sleep(think * rnd.uniform(0.5, 1.5))
            await req(st, c, "chat.message", "POST",
                      f"{base}/api/v1/public/webchat/{key}/conversations/{d['conversation_id']}/messages",
                      headers=hv, json={"text": rnd.choice(texts)})
            st.chat_msgs += 1
        await asyncio.sleep(think * rnd.uniform(1, 3))


async def dash_loop(st: Stats, c: httpx.AsyncClient, base: str, token: str, ws_id: str, stop: float, slot: int,
                    think: float) -> None:
    rnd = random.Random(2000 + slot)
    h = {"Authorization": f"Bearer {token}"}
    w = f"{base}/api/v1/workspaces/{ws_id}"
    pages = [("dash.overview", f"{w}/overview"), ("dash.notifications", f"{w}/notifications"),
             ("dash.feed", f"{w}/conversations/feed"), ("dash.calls", f"{w}/calls"),
             ("dash.reception", f"{w}/reception/overview"), ("dash.conversations", f"{w}/conversations"),
             ("dash.me", f"{base}/api/v1/auth/me")]
    await asyncio.sleep(rnd.uniform(0, think))
    while time.monotonic() < stop:
        for kind, u in rnd.sample(pages, 3):
            await req(st, c, kind, "GET", u, headers=h)
        await asyncio.sleep(think * rnd.uniform(0.5, 1.5))


async def setup_clients(st: Stats, c: httpx.AsyncClient, base: str, n: int, pw: str) -> list[tuple[str, str, str]]:
    """Log in each owner; returns (token, workspace_id, widget_key)."""
    out = []
    sem = asyncio.Semaphore(5)

    async def one(i: int):
        async with sem:
            r = await req(st, c, "setup.login", "POST", f"{base}/api/v1/auth/login",
                          json={"email": f"owner{i:03d}@{LABEL}.example", "password": pw})
            if r is None or r.status_code != 200:
                raise SystemExit(f"login {i} failed: {r.status_code if r else 'n/a'} {r.text[:200] if r else ''}")
            tok = r.json()["access_token"]
            h = {"Authorization": f"Bearer {tok}"}
            ws = (await c.get(f"{base}/api/v1/workspaces", headers=h)).json()
            wid = ws[0]["id"]
            wc = (await c.get(f"{base}/api/v1/workspaces/{wid}/webchat", headers=h)).json()
            key = wc.get("widget_key") or (wc.get("settings") or {}).get("widget_key")
            out.append((tok, wid, key))
    await asyncio.gather(*(one(i) for i in range(1, n + 1)))
    return out


async def main_async(a) -> dict:
    base = a.base.rstrip("/")
    if any(h in base for h in FORBIDDEN_HOSTS):
        raise SystemExit("Refusing: that is production")
    secret = os.environ["VAPI_SERVER_SECRET"]
    pw = os.environ["LOADTEST_PASSWORD"]
    st = Stats()
    limits = httpx.Limits(max_connections=a.calls * 2 + a.chat + a.dash + 20)
    async with httpx.AsyncClient(timeout=a.timeout, limits=limits) as c:
        r = await c.get(f"{base}/health/ready")
        print("ready:", r.status_code, file=sys.stderr)
        clients = await setup_clients(st, c, base, a.workspaces, pw)
        if any(not k for _, _, k in clients):
            raise SystemExit("missing widget key in /webchat response")
        t0 = datetime.now(UTC)
        stop = time.monotonic() + a.duration
        tasks = [call_loop(st, c, base, secret, a.workspaces, stop, s, a.call_think, a.dup_share) for s in range(a.calls)]
        tasks += [chat_loop(st, c, base, clients[s % len(clients)][2], stop, s, a.chat_think) for s in range(a.chat)]
        tasks += [dash_loop(st, c, base, clients[s % len(clients)][0], clients[s % len(clients)][1], stop, s, a.dash_think)
                  for s in range(a.dash)]
        await asyncio.gather(*tasks)
        t1 = datetime.now(UTC)
    st.lat.pop("setup.login", None)
    st.status.pop("setup.login", None)
    s = st.summary()
    rps = s["_all"]["n"] / a.duration
    return {"label": LABEL, "base_kind": "local" if "localhost" in base else "remote", "started": t0.isoformat(),
            "ended": t1.isoformat(), "params": {k: v for k, v in vars(a).items() if k != "out"}, "rps": round(rps, 1),
            "calls_completed": st.calls_done, "dup_reports_sent": st.dup_sent, "chat_messages": st.chat_msgs,
            "call_ids_file": a.out + ".callids", "summary": s, "first_errors": st.errors[:40],
            "_call_ids": st.call_ids}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--workspaces", type=int, default=50)
    ap.add_argument("--calls", type=int, default=10, help="concurrent simulated calls")
    ap.add_argument("--chat", type=int, default=50, help="concurrent webchat visitors")
    ap.add_argument("--dash", type=int, default=50, help="concurrent logged-in dashboards")
    ap.add_argument("--duration", type=int, default=300)
    ap.add_argument("--call-think", type=float, default=3.0, help="seconds between webhooks of one call")
    ap.add_argument("--chat-think", type=float, default=4.0)
    ap.add_argument("--dash-think", type=float, default=10.0)
    ap.add_argument("--dup-share", type=float, default=0.2)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = asyncio.run(main_async(a))
    ids = res.pop("_call_ids")
    with open(a.out + ".callids", "w") as f:
        f.write("\n".join(ids))
    with open(a.out, "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: res[k] for k in ("rps", "calls_completed", "dup_reports_sent", "chat_messages")}))
    print(json.dumps(res["summary"]["_all"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
