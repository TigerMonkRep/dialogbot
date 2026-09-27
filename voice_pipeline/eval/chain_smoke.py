"""End-to-end smoke test of the voice chain through the real HTTP boundaries.

    python -m voice_pipeline.eval.chain_smoke --api http://localhost:8001 --email owner@… --password … \
        --model-revision <40-hex, same as the TTS service> --reference ref.wav --vapi-secret … [--dev-grant]

Steps: log in → (dev only) grant operator → rights records reviewed → workspace-private pilot voice →
reference upload → immutable version → automatic checks → submit/approve/activate → choose as workspace
standard → preview (WAV) → phone number + assistant-request (custom-voice pinned session) → voice-request
(raw PCM) with time to first byte. Prints a JSON report; `simulated` is taken from the service's own header.
Against staging, run with an operator account and without --dev-grant.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import httpx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--model-revision", required=True)
    ap.add_argument("--reference", required=True, type=Path)
    ap.add_argument("--vapi-secret", required=True)
    ap.add_argument("--dev-grant", action="store_true")
    a = ap.parse_args(argv)
    base = a.api.rstrip("/") + "/api/v1"
    report: dict = {"api": a.api}
    with httpx.Client(timeout=120) as c:
        tok = c.post(f"{base}/auth/login", json={"email": a.email, "password": a.password}).json()["access_token"]
        h = {"authorization": f"Bearer {tok}"}

        def post(path, body=None, **kw):
            r = c.post(f"{base}{path}", headers=h | kw.pop("headers", {}), json=body, **kw)
            if r.status_code >= 400:
                raise SystemExit(f"{path} → {r.status_code} {r.text}")
            return r

        ws = c.get(f"{base}/workspaces", headers=h).json()[0]["id"]
        if a.dev_grant:
            post("/dev/operator/self")
        rights = []
        for kind, subject in (("code", "chatterbox-tts 0.1.7 (smoke)"), ("model", "ResembleAI/chatterbox (smoke)"),
                              ("dataset", "CoRal-project/coral-tts (smoke)")):
            r = post("/operator/voice-rights", {"kind": kind, "subject": f"{subject} {uuid.uuid4().hex[:6]}"}).json()
            post(f"/operator/voice-rights/{r['id']}/review", {"status": "verified", "notes": "Smoke-test i udviklingsmiljø"})
            rights.append(r["id"])
        slug = f"smoke-{uuid.uuid4().hex[:8]}"
        p = post("/operator/voices", {"slug": slug, "display_name": "Smoke", "visibility": "workspace", "workspace_id": ws}).json()
        ref = c.post(f"{base}/operator/voices/{p['id']}/references?source_id=smoke", headers=h, content=a.reference.read_bytes()).json()
        v = post(f"/operator/voices/{p['id']}/versions", {"model_repo": "ResembleAI/chatterbox", "model_revision": a.model_revision,
                                                          "references": [ref], "rights_record_ids": rights}).json()["versions"][0]
        checks = post(f"/operator/voice-versions/{v['id']}/checks/run").json()["versions"][0]["checks"]
        report["checks"] = {k: x.get("status") for k, x in checks.items()}
        for step in ("submit", "approve", "activate"):
            post(f"/operator/voice-versions/{v['id']}/{step}")
        s = c.get(f"{base}/workspaces/{ws}/voices", headers=h).json()["settings"]
        c.put(f"{base}/workspaces/{ws}/voices/settings", headers=h, json=s | {"expected_version": s["version"], "default_profile_id": p["id"]})
        t0 = time.monotonic()
        prev = post(f"/workspaces/{ws}/voices/{p['id']}/preview", {"text": "Det koster 1.495 kroner om måneden."})
        report["preview"] = {"ms": int((time.monotonic() - t0) * 1000), "bytes": len(prev.content),
                             "content_type": prev.headers["content-type"], "simulated": prev.headers.get("x-simulated")}
        pn = f"pn_{slug}"
        post(f"/workspaces/{ws}/phone-numbers", {"e164": f"+4570{int(time.time()) % 1000000:06d}", "provider_number_id": pn})
        ar = c.post(f"{base}/webhooks/vapi", headers={"authorization": f"Bearer {a.vapi_secret}"},
                    json={"message": {"type": "assistant-request", "call": {"id": f"call_{slug}", "phoneNumberId": pn}}}).json()
        voice = ar.get("assistant", {}).get("voice", {})
        report["assistant_voice_provider"] = voice.get("provider") or ar
        if voice.get("provider") == "custom-voice":
            url = base + voice["server"]["url"].split("/api/v1", 1)[1]
            t0 = time.monotonic()
            first = None
            n = 0
            with c.stream("POST", url, headers={"x-vapi-secret": a.vapi_secret},
                          json={"message": {"type": "voice-request", "text": "Hej. Din tid er den 28. oktober kl. 10.30.",
                                            "sampleRate": 16000}}) as r:
                for chunk in r.iter_bytes():
                    first = first or int((time.monotonic() - t0) * 1000)
                    n += len(chunk)
                report["voice_request"] = {"status": r.status_code, "first_byte_ms": first, "bytes": n,
                                           "audio_seconds": round(n / 2 / 16000, 2), "simulated": r.headers.get("x-simulated")}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
