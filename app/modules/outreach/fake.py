"""A stand-in for the Anthropic client with the SDK's `messages.create(**kwargs)` shape: deterministic answers, no
network. Used by the tests and by the offline dry run (`--fake-ai`, dev/test only). It records every call, which is how
the tests prove that blocked leads never reach the model."""
from __future__ import annotations

import json
import re
from types import SimpleNamespace as NS

_PAIN = re.compile(r"[^.\n]*\b(voicemail|no one (answers|picks up)|never (answered|called back|picked up)|on hold|"
                   r"couldn'?t get through|didn'?t (answer|call back|pick up)|missed (my )?calls?)\b[^.\n]*\.?", re.I)


class FakeClaude:
    def __init__(self, overrides: dict[str, dict] | None = None):
        self.calls: list[dict] = []
        self.overrides = overrides or {}     # tool name → the exact tool input to answer with
        self.messages = NS(create=self._create)

    def by_tool(self, name: str) -> list[dict]:
        return [c for c in self.calls if c["tool_choice"].get("name") == name or any(t.get("name") == name for t in c["tools"][:1])]

    def _create(self, **kw):
        self.calls.append(kw)
        name = kw["tools"][0]["name"]
        user = kw["messages"][0]["content"]
        data = self.overrides.get(name) or getattr(self, "_" + name)(user)
        return NS(model=kw["model"], stop_reason="tool_use", _request_id="req_fake",
                  usage=NS(input_tokens=len(str(kw["messages"])) // 4, output_tokens=len(json.dumps(data)) // 4),
                  content=[NS(type="tool_use", id="toolu_fake", name=name, input=data)])

    @staticmethod
    def _lead(user: str) -> dict:
        m = re.search(r"<(?:lead|business)>(.*?)</(?:lead|business)>", user, re.S)
        return json.loads(m.group(1)) if m else {}

    def _submit_lead_brief(self, user: str) -> dict:
        lead = self._lead(user)
        material = user.split("<material>", 1)[-1]
        hit = _PAIN.search(material)
        quote = hit.group(0).strip() if hit else ""
        return {
            "business_summary": f"{lead.get('company')} – {lead.get('niche')} in {lead.get('city')}",
            "is_business": True,
            "call_handling": "voicemail" if "voicemail" in material.lower() else "unknown",
            "call_handling_evidence": "Their material mentions voicemail." if "voicemail" in material.lower() else "",
            "review_snippets": [{"quote": quote, "source_type": "provided_context", "source_url": None}] if quote else [],
            "ticket_value": {"low": 150, "high": 600, "currency": "USD", "basis": "typical job in this niche"},
            "personalization_hook": (f'A reviewer of {lead.get("company")} wrote: "{quote}"' if quote
                                     else f"{lead.get('niche')} in {lead.get('city')}"),
            "confidence_score": 0.85 if quote else 0.3,
        }

    def _submit_email(self, user: str) -> dict:
        b = self._lead(user)
        brief = json.loads(re.search(r"<brief>(.*)</brief>", user, re.S).group(1))
        quote = (brief["review_snippets"] or [{"quote": ""}])[0]["quote"]
        from app.modules.outreach import localization

        line = localization.locale_for(b["country"]).demo_line if b.get("country") else None
        line3 = (f"You can hear it yourself in 90 seconds: call our demo line on {line}, any hour. No signup, no "
                 f"credit card. Details at {localization.demo_url(b['country'])}." if line else
                 "You can hear it yourself in 90 seconds: enter your number at https://dialogbot.app and it calls "
                 "you right away. No signup, no credit card.")
        return {
            "subject": f"calls at {b.get('company')}",
            "line1": f'One of your reviewers wrote: "{quote}" Calls like that usually go to the next {b.get("niche")} on the list.',
            "line2": "Dialogbot answers every call in under 2 seconds, books straight into Google Calendar or "
                     "Microsoft 365 and texts the caller an SMS confirmation.",
            "line3": line3,
        }

    def _submit_audit(self, user: str) -> dict:
        return {"verdict": "pass", "issues": []}
