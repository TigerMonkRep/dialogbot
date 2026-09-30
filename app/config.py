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
    # Stripe (card payment and monthly invoices). Test-mode keys (sk_test_…) until the owner goes live.
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    # Outbound campaign calls: Vapi private API key (server-only). Without it campaigns cannot be started.
    vapi_api_key: str | None = Field(default=None, alias="VAPI_API_KEY")
    vapi_api_url: str = Field(default="https://api.vapi.ai", alias="VAPI_API_URL")
    # Webhooks must come from Dialogbot's own Vapi org when set (call.orgId); unknown orgs are rejected.
    vapi_org_id: str | None = Field(default=None, alias="VAPI_ORG_ID")
    # Platform-managed telephony: Dialogbot's own Twilio main account (sub-accounts per workspace) + Vapi.
    telephony_provider: Literal["none", "fake", "live"] = Field(default="none", alias="TELEPHONY_PROVIDER")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_api_key_sid: str | None = Field(default=None, alias="TWILIO_API_KEY_SID")
    twilio_api_key_secret: str | None = Field(default=None, alias="TWILIO_API_KEY_SECRET")
    telephony_number_country: str = Field(default="DK", alias="TELEPHONY_NUMBER_COUNTRY")
    telephony_number_type: Literal["local", "mobile"] = Field(default="local", alias="TELEPHONY_NUMBER_TYPE")
    # Vapi phone-number id of a platform number used only to place verification calls (reads a code aloud).
    telephony_verify_number_id: str | None = Field(default=None, alias="TELEPHONY_VERIFY_NUMBER_ID")
    vapi_model_provider: str = Field(default="anthropic", alias="VAPI_MODEL_PROVIDER")
    vapi_model: str | None = Field(default=None, alias="VAPI_MODEL")  # default: AI_MODEL_ID
    # Optional JSON objects passed through to Vapi's assistant config (e.g. a Danish voice/transcriber).
    vapi_voice_json: str | None = Field(default=None, alias="VAPI_VOICE_JSON")
    vapi_transcriber_json: str | None = Field(default=None, alias="VAPI_TRANSCRIBER_JSON")
    # Server-side only: lets owners hear a chosen ElevenLabs voice before calls go live.
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    # CVR register (Erhvervsstyrelsen "system-til-system"): free credentials via cvrselvbetjening@erst.dk.
    cvr_username: str | None = Field(default=None, alias="CVR_USERNAME")
    cvr_password: str | None = Field(default=None, alias="CVR_PASSWORD")
    cvr_url: str = Field(default="http://distribution.virk.dk/cvr-permanent/virksomhed/_search", alias="CVR_URL")
    # Sales demo calls ("Ring mig op nu" on the website and the seller flow): Dialogbot's own workspace, whose
    # approved knowledge describes Dialogbot and whose outbound-approved number places the calls. Unset = off.
    sales_workspace_id: str | None = Field(default=None, alias="SALES_WORKSPACE_ID")
    sales_call_from: str = Field(default="08:00", alias="SALES_CALL_FROM")  # website requests, Copenhagen time
    sales_call_to: str = Field(default="20:00", alias="SALES_CALL_TO")
    sales_max_calls_per_hour: int = Field(default=20, alias="SALES_MAX_CALLS_PER_HOUR")
    # Actions in the customer's own systems (app/modules/integrations/connectors). Stored credentials are envelope-
    # encrypted with CREDENTIALS_KEY (base64url, 32 random bytes; `python -m scripts.credentials_key` prints one).
    # Without it in staging/prod, connectors that store secrets are reported as not available; dev/test derive a
    # process key from SECRET_KEY. CREDENTIALS_KEY_PREVIOUS keeps old
    # rows readable during rotation.
    credentials_key: str | None = Field(default=None, alias="CREDENTIALS_KEY")
    credentials_key_previous: str | None = Field(default=None, alias="CREDENTIALS_KEY_PREVIOUS")
    # OAuth clients Dialogbot registers with the providers (customers never see these). Without a client id the
    # connector is reported as not implemented. Redirect URI: {PUBLIC_BASE_URL}/api/v1/integrations/oauth/{key}/callback
    google_oauth_client_id: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_SECRET")
    microsoft_oauth_client_id: str | None = Field(default=None, alias="MICROSOFT_OAUTH_CLIENT_ID")
    microsoft_oauth_client_secret: str | None = Field(default=None, alias="MICROSOFT_OAUTH_CLIENT_SECRET")
    microsoft_oauth_tenant: str = Field(default="common", alias="MICROSOFT_OAUTH_TENANT")
    # live = real provider calls; fake = deterministic in-memory doubles (dev/test only, every result is simulated)
    connectors_provider: Literal["live", "fake"] = Field(default="live", alias="CONNECTORS_PROVIDER")
    # Twilio SMS: alphanumeric sender used when a workspace has no SMS-capable number (max 11 chars, Denmark
    # allows it without pre-registration). Empty = SMS actions are not offered.
    sms_default_sender: str = Field(default="", alias="SMS_DEFAULT_SENDER")
    # Danish voice library. The speech engine is a separate service (tts_service/), never the API process.
    # TTS_ENGINE: none | http (the real service at TTS_SERVICE_URL) | fake (dev/test double; audio is a tone
    # and every result is labelled simulated).
    tts_engine: Literal["none", "http", "fake"] = Field(default="none", alias="TTS_ENGINE")
    # Model new voices (own voices) are created for; must match the TTS host's MODEL_REPO/MODEL_REVISION.
    voice_model_repo: str = Field(default="CoRal-project/roest-v3-chatterbox-500m", alias="VOICE_MODEL_REPO")
    voice_model_revision: str = Field(default="7ce205cea6b3b36d9f60f18abb88ff21fa04ea0d", alias="VOICE_MODEL_REVISION")
    tts_service_url: str | None = Field(default=None, alias="TTS_SERVICE_URL")
    tts_service_token: str | None = Field(default=None, alias="TTS_SERVICE_TOKEN")
    tts_timeout_seconds: float = Field(default=20.0, alias="TTS_TIMEOUT_SECONDS")
    # Calls: send audio to Vapi while it is generated (tts_service /v1/synthesize/stream) instead of per sentence
    tts_streaming: bool = Field(default=True, alias="TTS_STREAMING")
    # Private object storage for reference clips, agreements and preview cache: local (dev/test) | supabase
    voice_storage: Literal["local", "supabase"] = Field(default="local", alias="VOICE_STORAGE")
    voice_storage_dir: str = Field(default="var/voice-store", alias="VOICE_STORAGE_DIR")
    voice_bucket: str = Field(default="voice-private", alias="VOICE_BUCKET")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    voice_preview_daily_limit: int = Field(default=40, alias="VOICE_PREVIEW_DAILY_LIMIT")
    voice_preview_max_chars: int = Field(default=200, alias="VOICE_PREVIEW_MAX_CHARS")
    voice_call_daily_char_limit: int = Field(default=400_000, alias="VOICE_CALL_DAILY_CHAR_LIMIT")
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
        if self.tts_engine == "fake" and self.app_env not in ("dev", "test"):
            raise ValueError(f"TTS_ENGINE=fake is a test double and is not allowed when APP_ENV={self.app_env}")
        if self.telephony_provider == "fake" and self.app_env not in ("dev", "test"):
            raise ValueError(f"TELEPHONY_PROVIDER=fake is a test double and is not allowed when APP_ENV={self.app_env}")
        if self.connectors_provider == "fake" and self.app_env not in ("dev", "test"):
            raise ValueError(f"CONNECTORS_PROVIDER=fake is a test double and is not allowed when APP_ENV={self.app_env}")
        if self.tts_engine == "http" and not (self.tts_service_url and self.tts_service_token):
            raise ValueError("TTS_ENGINE=http requires TTS_SERVICE_URL and TTS_SERVICE_TOKEN")
        if self.voice_storage == "supabase" and not (self.supabase_url and self.supabase_service_role_key):
            raise ValueError("VOICE_STORAGE=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
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
