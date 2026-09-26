"""AI provider interface and adapters.

The rest of the app talks to `AIProvider.complete()` only; the concrete vendor is chosen by
AI_PROVIDER. Adapters return the text, the stop reason and the token usage so that every call
can be logged per workspace (see app/modules/ai/service.py). No adapter ever sees drafts: the
caller builds the prompt from approved knowledge only.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from app.config import Settings, get_settings
from app.core.errors import ApiError, NotImplementedYet

# Anthropic beta header for the scalar `fallbacks: "default"` form.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIProviderError(ApiError):
    status_code = 502
    code = "ai_provider_error"


class AIRateLimited(ApiError):
    status_code = 503
    code = "ai_rate_limited"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class Completion:
    text: str
    # end_turn | max_tokens | refusal | stop_sequence | ... (provider vocabulary, stored as-is)
    stop_reason: str
    requested_model: str
    served_model: str
    usage: Usage = field(default_factory=Usage)
    request_id: str | None = None
    refusal_category: str | None = None
    latency_ms: int = 0


class AIProvider(Protocol):
    name: str
    model: str

    def complete(self, *, system: str, messages: list[dict], max_tokens: int) -> Completion: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings, client=None):
        import anthropic

        self._anthropic = anthropic
        self.model = settings.ai_model_id
        self.effort = settings.ai_effort
        self.fallbacks = settings.ai_server_fallbacks
        # Retries on 429/5xx are handled by the SDK (default 2); keep the request bounded.
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0)

    def complete(self, *, system: str, messages: list[dict], max_tokens: int) -> Completion:
        a = self._anthropic
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            # One stable system block (instructions + approved knowledge) marked for prompt caching.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {"effort": self.effort},
        }
        if self.fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        started = time.monotonic()
        try:
            resp = self.client.beta.messages.create(**kwargs)
        except a.RateLimitError as e:
            raise AIRateLimited("AI-udbyderen er midlertidigt overbelastet. Prøv igen om lidt.") from e
        except a.APIStatusError as e:
            raise AIProviderError(f"AI-udbyderen svarede med fejl {e.status_code}",
                                  extra={"provider_request_id": getattr(e, "request_id", None)}) from e
        except a.APIConnectionError as e:
            raise AIProviderError("AI-udbyderen kunne ikke nås") from e
        latency_ms = int((time.monotonic() - started) * 1000)

        u = resp.usage
        served = str(resp.model)
        # A fallback model that served the turn shows up as a `fallback_message` iteration.
        for it in getattr(u, "iterations", None) or []:
            if getattr(it, "type", None) == "fallback_message":
                served = str(it.model)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        details = getattr(resp, "stop_details", None)
        return Completion(
            text=text,
            stop_reason=str(resp.stop_reason or "unknown"),
            requested_model=self.model,
            served_model=served,
            usage=Usage(input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
                        cache_creation_input_tokens=u.cache_creation_input_tokens or 0,
                        cache_read_input_tokens=u.cache_read_input_tokens or 0),
            request_id=getattr(resp, "_request_id", None),
            refusal_category=getattr(details, "category", None) if details else None,
            latency_ms=latency_ms,
        )


class FakeProvider:
    """Deterministic test double (dev/test only). Echoes which knowledge titles it was given."""

    name = "fake"

    def __init__(self, settings: Settings):
        self.model = settings.ai_model_id
        self.last_system: str | None = None
        self.last_messages: list[dict] | None = None

    def complete(self, *, system: str, messages: list[dict], max_tokens: int) -> Completion:
        self.last_system, self.last_messages = system, messages
        question = messages[-1]["content"] if messages else ""
        if system.startswith("WEBSITE_EXTRACTION"):
            return self._extract(question)
        refused = "AFVIS" in question
        return Completion(
            text="" if refused else f"[fake] svar på: {question}",
            stop_reason="refusal" if refused else "end_turn",
            requested_model=self.model,
            served_model=self.model,
            usage=Usage(input_tokens=len(system) // 4 + len(question) // 4, output_tokens=12),
            request_id="fake-req",
            refusal_category="general_harms" if refused else None,
        )


    def _extract(self, text: str) -> Completion:
        """Deterministic 'extraction': every '## ' heading after a page's first becomes a service
        (description = the next line); the first page's first paragraph becomes a fact."""
        import json
        import re

        services, facts, url = [], [], ""
        for page in re.findall(r'<side url="([^"]*)"[^>]*>\n(.*?)\n</side>', text, re.S):
            url, body = page
            lines = body.split("\n")
            heads = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
            for i in heads[1:]:
                nxt = next((ln for ln in lines[i + 1:] if ln and not ln.startswith("## ")), "")
                price = re.search(r"\d[\d.]*\s*kr[^\n]*", nxt)
                services.append({"title": lines[i][3:], "description": nxt, "unit": "m2" if "m²" in nxt else None,
                                 "price_text": price.group(0) if price else None, "source_url": url})
            if not facts:
                para = next((ln for ln in lines if ln and not ln.startswith(("## ", "- "))), "")
                if para:
                    facts.append({"title": "Om virksomheden", "text": para, "source_url": url})
        def find(pattern: str, group: int = 1) -> str | None:
            m = re.search(pattern, text)
            return m.group(group).strip() if m else None

        place = re.search(r"\b(\d{4}) ([A-ZÆØÅ][a-zæøå]+)", text)
        profile = {"description": facts[0]["text"] if facts else None, "cvr": find(r"CVR\D{0,5}(\d{8})"),
                   "phone": find(r"(?:Tlf\.?|Telefon|Ring på)[:\s]*(\+?\d[\d ]{6,14}\d)"),
                   "address_line": find(r"([A-ZÆØÅ][a-zæøå]+(?:vej|gade|allé|stræde|plads) \d+\w?)"),
                   "postal_code": place.group(1) if place else None, "city": place.group(2) if place else None}
        h = re.search(r"hverdage (\d{1,2})-(\d{1,2})", text)
        hours = {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri"], "open": f"{int(h.group(1)):02d}:00",
                             "close": f"{int(h.group(2)):02d}:00"}], "note": None} if h else None
        out = json.dumps({"services": services, "facts": facts, "faq": [], "profile": profile, "opening_hours": hours},
                         ensure_ascii=False)
        return Completion(text=out, stop_reason="end_turn", requested_model=self.model, served_model=self.model,
                          usage=Usage(input_tokens=len(text) // 4, output_tokens=len(out) // 4), request_id="fake-req")


_override: AIProvider | None = None


def set_provider_override(p: AIProvider | None) -> None:
    """Test hook: force a provider instance (e.g. AnthropicProvider with a stubbed client)."""
    global _override
    _override = p


def get_provider() -> AIProvider:
    if _override is not None:
        return _override
    s = get_settings()
    if s.ai_provider == "anthropic":
        return AnthropicProvider(s)
    if s.ai_provider == "fake":
        return FakeProvider(s)
    raise NotImplementedYet("AI-assistenten er ikke konfigureret i dette miljø (AI_PROVIDER=none)",
                            code="ai_not_configured")
