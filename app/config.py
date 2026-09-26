"""Application settings.

Every deployment-relevant value is read from the environment. The settings
object refuses to start a production process that is missing the secrets and
adapter decisions it needs; a missing secret never silently degrades to an open
or unauthenticated system.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "staging", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: AppEnv = Field(default="dev", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL")
    # Application schema. On Supabase the app lives in its own schema, kept out of the Data API.
    db_schema: str = Field(default="public", alias="DB_SCHEMA")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, alias="DB_MAX_OVERFLOW")
    secret_key: str | None = Field(default=None, alias="SECRET_KEY")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")
    frontend_base_url: str = Field(default="http://localhost:5173", alias="FRONTEND_BASE_URL")

    # Auth. "local" = maintained password hashing (argon2 via pwdlib) + opaque
    # server-side sessions. "external" is reserved for an OIDC provider and is
    # intentionally NOT implemented in this stage; selecting it fails closed.
    auth_provider: Literal["local", "external"] = Field(default="local", alias="AUTH_PROVIDER")
    session_ttl_hours: int = Field(default=24 * 14, alias="SESSION_TTL_HOURS")
    invitation_ttl_hours: int = Field(default=72, alias="INVITATION_TTL_HOURS")
    reset_ttl_minutes: int = Field(default=60, alias="RESET_TTL_MINUTES")
    verification_ttl_hours: int = Field(default=48, alias="VERIFICATION_TTL_HOURS")

    # Email adapter. "simulated" stores messages in the database and exposes them
    # through the dev-only mailbox endpoint. It never claims real delivery.
    email_adapter: Literal["simulated", "resend"] = Field(default="simulated", alias="EMAIL_ADAPTER")
    email_from: str = Field(default="Dialogbot <noreply@dialogbot.local>", alias="EMAIL_FROM")
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    # Signing secret of the Resend webhook endpoint ("whsec_..."). Without it the webhook answers 503.
    resend_webhook_secret: str | None = Field(default=None, alias="RESEND_WEBHOOK_SECRET")

    # AI provider behind app/modules/ai. "none" = no model is called (endpoints answer 501);
    # "fake" is a deterministic test double and is refused outside dev/test.
    ai_provider: Literal["none", "anthropic", "fake"] = Field(default="none", alias="AI_PROVIDER")
    ai_model_id: str = Field(default="claude-opus-5", alias="AI_MODEL_ID")
    ai_effort: Literal["low", "medium", "high"] = Field(default="medium", alias="AI_EFFORT")
    ai_max_output_tokens: int = Field(default=2048, alias="AI_MAX_OUTPUT_TOKENS")
    # Anthropic server-side refusal fallback ("fallbacks": "default", beta header server-side-fallback-2026-07-01):
    # on a policy decline the API re-runs the call on the model's default fallback model. Set false to pin one model
    # (required if AI_MODEL_ID names a model without a server-defined default fallback).
    ai_server_fallbacks: bool = Field(default=True, alias="AI_SERVER_FALLBACKS")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    # Voice (Vapi). The server secret authenticates Vapi → us (Bearer credential or legacy X-Vapi-Secret).
    # Without it the voice webhook answers 503 and inbound telephony is reported as not implemented.
    vapi_server_secret: str | None = Field(default=None, alias="VAPI_SERVER_SECRET")
    vapi_model_provider: str = Field(default="anthropic", alias="VAPI_MODEL_PROVIDER")
    vapi_model: str | None = Field(default=None, alias="VAPI_MODEL")  # default: AI_MODEL_ID
    # Optional JSON objects passed through to Vapi's assistant config (e.g. a Danish voice/transcriber).
    vapi_voice_json: str | None = Field(default=None, alias="VAPI_VOICE_JSON")
    vapi_transcriber_json: str | None = Field(default=None, alias="VAPI_TRANSCRIBER_JSON")
    # Server-side only: lets owners hear a chosen ElevenLabs voice before calls go live.
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    # Spend guard: max AI replies per workspace per 24 h in the public web widget.
    webchat_daily_reply_limit: int = Field(default=300, alias="WEBCHAT_DAILY_REPLY_LIMIT")

    # Dev tooling: the simulated mailbox and test identities are gated on this.
    enable_dev_tools: bool = Field(default=False, alias="ENABLE_DEV_TOOLS")

    worker_poll_seconds: float = Field(default=1.0, alias="WORKER_POLL_SECONDS")
    worker_lease_seconds: int = Field(default=60, alias="WORKER_LEASE_SECONDS")
    worker_max_attempts: int = Field(default=5, alias="WORKER_MAX_ATTEMPTS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @model_validator(mode="after")
    def _fail_closed(self) -> Settings:
        if self.app_env in ("staging", "prod"):
            if not self.secret_key or len(self.secret_key) < 32:
                raise ValueError(f"SECRET_KEY (>=32 chars) is required when APP_ENV={self.app_env}")
            if self.enable_dev_tools:
                raise ValueError(f"ENABLE_DEV_TOOLS must be false when APP_ENV={self.app_env}")
        if self.app_env == "prod" and self.email_adapter == "simulated":
            raise ValueError("EMAIL_ADAPTER=simulated is not allowed in prod; prod cannot claim mail delivery")
        if self.email_adapter == "resend" and not self.resend_api_key:
            raise ValueError("EMAIL_ADAPTER=resend requires RESEND_API_KEY")
        if self.ai_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("AI_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        if self.ai_provider == "fake" and self.app_env not in ("dev", "test"):
            raise ValueError(f"AI_PROVIDER=fake is a test double and is not allowed when APP_ENV={self.app_env}")
        if self.auth_provider == "external":
            raise ValueError(
                "AUTH_PROVIDER=external is reserved for a future OIDC integration and is not "
                "implemented; the process refuses to start rather than run unauthenticated"
            )
        if not self.secret_key:
            # Dev/test only: a per-process random secret. Sessions are opaque DB
            # tokens, so this secret is only used for defence in depth.
            import secrets

            object.__setattr__(self, "secret_key", secrets.token_urlsafe(48))
        return self

    @property
    def dev_tools_enabled(self) -> bool:
        return self.enable_dev_tools and self.app_env in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
