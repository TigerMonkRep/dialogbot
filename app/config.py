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

    @property
    def browser_engines(self) -> set[str]:
        return {e.strip().lower() for e in self.browser_allowed_engines.split(",") if e.strip()}

    app_env: AppEnv = Field(default="dev", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL")
    # Application schema. On Supabase the app lives in its own schema, kept out of the Data API.
    db_schema: str = Field(default="public", alias="DB_SCHEMA")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, alias="DB_MAX_OVERFLOW")
    secret_key: str | None = Field(default=None, alias="SECRET_KEY")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")
    frontend_base_url: str = Field(default="http://localhost:5173", alias="FRONTEND_BASE_URL")
    # H01/M06: a new support ticket is announced here (number, subject and workspace only – Fürster 13/11)
    support_inbox_email: str = Field(default="info@dialogbot.dk", alias="SUPPORT_INBOX_EMAIL")

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
    # Dialogbot Privat's chat answers a person who is waiting with the phone in hand: its own (faster) model and a low
    # effort. Unset = AI_MODEL_ID. The chat may also search the web (Anthropic's server-side web_search tool) for
    # links to where something can be bought, prices and opening hours – off with PRIVAT_WEB_SEARCH=false.
    privat_ai_model_id: str | None = Field(default=None, alias="PRIVAT_AI_MODEL_ID")
    privat_ai_effort: Literal["low", "medium", "high"] = Field(default="low", alias="PRIVAT_AI_EFFORT")
    privat_web_search: bool = Field(default=True, alias="PRIVAT_WEB_SEARCH")
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
    # Conversation pacing overrides (JSON with the keys of telephony.vapi.PACING) – for comparing settings on the demo
    # number without a deploy. Unset = the tuned defaults.
    vapi_pacing_json: str | None = Field(default=None, alias="VAPI_PACING_JSON")
    vapi_transcriber_json: str | None = Field(default=None, alias="VAPI_TRANSCRIBER_JSON")
    # Speechmatics Agent STT (Linden) through our own transcriber bridge: VAPI_TRANSCRIBER_JSON={"provider":
    # "custom-transcriber"} sends every call's audio to /webhooks/vapi/transcriber, which forwards it to Speechmatics.
    speechmatics_api_key: str | None = Field(default=None, alias="SPEECHMATICS_API_KEY")
    speechmatics_rt_url: str | None = Field(default=None, alias="SPEECHMATICS_RT_URL")  # default: the EU endpoint
    speechmatics_customer_channel: int = Field(default=0, alias="SPEECHMATICS_CUSTOMER_CHANNEL")  # Vapi: 0 = customer
    # Per-company recogniser for the bridge, e.g. {"<workspace-uuid>": "soniox"}. Only listed workspaces change; every
    # other call keeps the production transcriber. Remove the entry (and restart) to roll one company back. Unset = off.
    vapi_stt_by_workspace_json: str | None = Field(default=None, alias="VAPI_STT_BY_WORKSPACE_JSON")
    # Stemmetest (docs/voice/stemmetest.md): the extra recognisers compared against Speechmatics. ElevenLabs Scribe uses
    # ELEVENLABS_API_KEY below. Server-side only; never returned by any endpoint.
    soniox_api_key: str | None = Field(default=None, alias="SONIOX_API_KEY")
    # Soniox real-time model for every use (bridge, own engine, Stemmetest), e.g. "stt-rt-v6". Unset = stt-rt-v5.
    soniox_model: str | None = Field(default=None, alias="SONIOX_MODEL")
    # TEST-ONLY: the Soniox model the Stemmetest's profile E replays with (e.g. "stt-rt-v6" to measure v6 before
    # SONIOX_MODEL is changed for real calls). Only the replay reads it; the bridge and the engine never do.
    stemmetest_soniox_model: str | None = Field(default=None, alias="STEMMETEST_SONIOX_MODEL")
    stemmetest_audio_dir: str | None = Field(default=None, alias="STEMMETEST_AUDIO_DIR")  # human recordings per case
    # Optional USD per audio hour per recogniser, e.g. {"soniox": 0.12}: filled in from the provider's own price page.
    # Unset = the run reports audio seconds and says "pris ikke angivet" rather than guessing a price.
    stemmetest_prices_json: str | None = Field(default=None, alias="STEMMETEST_PRICES_JSON")
    # Server-side only: lets owners hear a chosen ElevenLabs voice before calls go live.
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    # ElevenLabs Agents trial (an alternative call engine to Vapi): a shared secret ElevenLabs sends as the
    # X-Dialogbot-Secret header on the conversation-initiation webhook, and the HMAC secret of its post-call webhook.
    elevenlabs_agent_secret: str | None = Field(default=None, alias="ELEVENLABS_AGENT_SECRET")
    elevenlabs_webhook_secret: str | None = Field(default=None, alias="ELEVENLABS_WEBHOOK_SECRET")
    # CVR register (Erhvervsstyrelsen "system-til-system"): free credentials via cvrselvbetjening@erst.dk.
    cvr_username: str | None = Field(default=None, alias="CVR_USERNAME")
    cvr_password: str | None = Field(default=None, alias="CVR_PASSWORD")
    cvr_url: str = Field(default="http://distribution.virk.dk/cvr-permanent/virksomhed/_search", alias="CVR_URL")
    # Sales demo calls ("Ring mig op nu" on the website and the seller flow): Dialogbot's own workspace, whose
    # approved knowledge describes Dialogbot and whose outbound-approved number places the calls. Unset = off.
    # Website statistics shown under Operator → Admin → Hjemmeside. Vercel Web Analytics is read with a Vercel API
    # token (vercel.com/account/tokens); Google Analytics 4 with a Google service account that is a Viewer on the
    # property (its JSON key, as one line) plus the numeric property id. Unset = that half shows "ikke sat op".
    vercel_api_token: str | None = Field(default=None, alias="VERCEL_API_TOKEN")
    vercel_project_id: str = Field(default="prj_RF84xHv5FEIocLvXLIiM4PJgKWA4", alias="VERCEL_PROJECT_ID")
    vercel_team_id: str = Field(default="team_Ob5jVmkpiG3ZRJjCxzpqVyz9", alias="VERCEL_TEAM_ID")
    ga4_property_id: str | None = Field(default=None, alias="GA4_PROPERTY_ID")
    ga_service_account_json: str | None = Field(default=None, alias="GA_SERVICE_ACCOUNT_JSON")
    sales_workspace_id: str | None = Field(default=None, alias="SALES_WORKSPACE_ID")
    sales_max_calls_per_hour: int = Field(default=20, alias="SALES_MAX_CALLS_PER_HOUR")
    # The voice of "Peter", who rings visitors and prospects. Unset = the catalogue's Peter (app/modules/voices/standard.py).
    # An ElevenLabs Voice Library id (Vapi → Integrations holds the platform's ElevenLabs key); a Danish male voice.
    sales_agent_voice_id: str | None = Field(default=None, alias="SALES_AGENT_VOICE_ID")
    # Dialogbot's internal sales channel (operator-only, /operator/salg): find companies via Google Places, research
    # their own website, build a profile and a personal script for Peter, simulate or (later phases) ring.
    # off = every /operator/salg route except the status page answers 501; research = search, research, profile and
    # script; simulation = also simulated conversations; test = also calls to SALES_TEST_NUMBERS; live = real calls
    # that the contact policy allows. Nothing ever starts a live campaign by itself.
    sales_outbound_mode: Literal["off", "research", "simulation", "test", "live"] = Field(
        default="off", alias="SALES_OUTBOUND_MODE")
    sales_test_numbers: str = Field(default="", alias="SALES_TEST_NUMBERS")  # comma-separated E.164
    sales_research_max_pages: int = Field(default=8, alias="SALES_RESEARCH_MAX_PAGES")
    sales_research_per_host_concurrency: int = Field(default=2, alias="SALES_RESEARCH_PER_HOST_CONCURRENCY")
    sales_research_page_bytes: int = Field(default=1_500_000, alias="SALES_RESEARCH_PAGE_BYTES")
    sales_research_timeout_seconds: float = Field(default=10.0, alias="SALES_RESEARCH_TIMEOUT_SECONDS")
    sales_research_page_pause_seconds: float = Field(default=2.0, alias="SALES_RESEARCH_PAGE_PAUSE_SECONDS")
    sales_search_max_results: int = Field(default=200, alias="SALES_SEARCH_MAX_RESULTS")
    # Google Places API (New), project "Dialogbot" (dialogbot-513209), key restricted to the Places API. Unset = the
    # search runs on clearly fictitious demo data and the UI says so.
    google_places_api_key: str | None = Field(default=None, alias="GOOGLE_PLACES_API_KEY")
    google_places_url: str = Field(default="https://places.googleapis.com/v1/places:searchText", alias="GOOGLE_PLACES_URL")
    google_places_details_url: str = Field(default="https://places.googleapis.com/v1/places",
                                           alias="GOOGLE_PLACES_DETAILS_URL")
    # Hard cap on Places requests per Copenhagen day across all search jobs; a job that hits it is paused.
    sales_search_daily_request_cap: int = Field(default=500, alias="SALES_SEARCH_DAILY_REQUEST_CAP")
    # Google's terms: everything except the place id may be cached at most 30 days, then refreshed or deleted.
    google_places_cache_days: int = Field(default=30, alias="GOOGLE_PLACES_CACHE_DAYS")
    sales_max_concurrent_calls: int = Field(default=2, alias="SALES_MAX_CONCURRENT_CALLS")
    sales_max_attempts_per_contact: int = Field(default=2, alias="SALES_MAX_ATTEMPTS_PER_CONTACT")
    # Call recordings (phase 4): none | supabase (a private bucket in the Supabase project VOICE_STORAGE also uses).
    sales_recording_storage: Literal["none", "supabase"] = Field(default="none", alias="SALES_RECORDING_STORAGE")
    sales_recording_bucket: str = Field(default="sales-recordings", alias="SALES_RECORDING_BUCKET")
    # Retention per data type, for the owner to approve (configuration, not a legal requirement).
    sales_retention_transcript_days: int = Field(default=90, alias="SALES_RETENTION_TRANSCRIPT_DAYS")
    sales_retention_audio_days: int = Field(default=30, alias="SALES_RETENTION_AUDIO_DAYS")
    sales_retention_summary_days: int = Field(default=365, alias="SALES_RETENTION_SUMMARY_DAYS")
    # Lets the safe fetcher reach private/loopback addresses. Local tests against a site on this machine only;
    # refused outside dev/test.
    allow_private_fetch: bool = Field(default=False, alias="ALLOW_PRIVATE_FETCH")
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
    # Browser worker (browser_worker/, docs/ADR-004-browser-worker.md): books on external public booking pages after a
    # human yes in the Privat app. Off by default. Evidence (screenshots, video, receipt PDF) goes to a PRIVATE bucket
    # in the Supabase project above and is only ever handed out as short-lived signed links.
    browser_worker_enabled: bool = Field(default=False, alias="BROWSER_WORKER_ENABLED")
    browser_max_steps: int = Field(default=25, ge=1, le=100, alias="BROWSER_MAX_STEPS")
    browser_max_seconds: int = Field(default=180, ge=10, le=900, alias="BROWSER_MAX_SECONDS")
    browser_approval_ttl_seconds: int = Field(default=600, ge=30, le=3600, alias="BROWSER_APPROVAL_TTL_SECONDS")
    browser_allowed_engines: str = Field(default="onlinebooq", alias="BROWSER_ALLOWED_ENGINES")
    browser_evidence_bucket: str = Field(default="browser-evidence", alias="BROWSER_EVIDENCE_BUCKET")
    # Photos the Privat user adds (receipts in Garanti & kvitteringer): a PRIVATE Supabase Storage bucket.
    privat_files_bucket: str = Field(default="privat-files", alias="PRIVAT_FILES_BUCKET")
    # Lead loop (docs/sales/privat-opkald-leads.md): at the end of a Privat call to a business that is not a customer, ONE fixed,
    # honest sentence about Dialogbot, when every rule allows it. Off by default; a lawyer must confirm the legal view first.
    lead_pitch_enabled: bool = Field(default=False, alias="LEAD_PITCH_ENABLED")
    lead_pitch_cooldown_days: int = Field(default=90, ge=1, le=3650, alias="LEAD_PITCH_COOLDOWN_DAYS")
    voice_preview_daily_limit: int = Field(default=40, alias="VOICE_PREVIEW_DAILY_LIMIT")
    voice_preview_max_chars: int = Field(default=200, alias="VOICE_PREVIEW_MAX_CHARS")
    voice_call_daily_char_limit: int = Field(default=400_000, alias="VOICE_CALL_DAILY_CHAR_LIMIT")
    # Spend guard: max AI replies per workspace per 24 h in the public web widget.
    webchat_daily_reply_limit: int = Field(default=300, alias="WEBCHAT_DAILY_REPLY_LIMIT")

    # Social media autoposting (app/modules/social): Dialogbot's own Facebook page, Instagram business account and TikTok.
    # none = nothing is generated or posted; fake = deterministic double (dev/test only); live = real Graph/TikTok calls.
    social_provider: Literal["none", "fake", "live"] = Field(default="none", alias="SOCIAL_PROVIDER")
    # false = posts publish by themselves at their slot; true = they wait as drafts until an operator approves them.
    social_require_approval: bool = Field(default=False, alias="SOCIAL_REQUIRE_APPROVAL")
    social_weekdays: str = Field(default="0,2,4", alias="SOCIAL_WEEKDAYS")  # Monday=0 ... Sunday=6, Copenhagen time
    social_plan_days_ahead: int = Field(default=3, alias="SOCIAL_PLAN_DAYS_AHEAD")  # drafts exist this long before posting
    social_platforms: str = Field(default="facebook,instagram,tiktok", alias="SOCIAL_PLATFORMS")
    # A slot older than this when the worker finds it is skipped instead of posted at a strange hour.
    social_max_late_minutes: int = Field(default=360, alias="SOCIAL_MAX_LATE_MINUTES")
    meta_graph_version: str = Field(default="v23.0", alias="META_GRAPH_VERSION")
    meta_page_id: str | None = Field(default=None, alias="META_PAGE_ID")
    meta_page_access_token: str | None = Field(default=None, alias="META_PAGE_ACCESS_TOKEN")  # long-lived Page token
    meta_instagram_user_id: str | None = Field(default=None, alias="META_INSTAGRAM_USER_ID")
    tiktok_client_key: str | None = Field(default=None, alias="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: str | None = Field(default=None, alias="TIKTOK_CLIENT_SECRET")
    # First refresh token, from the one-off authorisation (scripts/social_connect.py); afterwards the rotated
    # token lives encrypted in the database and this value is no longer used.
    tiktok_refresh_token: str | None = Field(default=None, alias="TIKTOK_REFRESH_TOKEN")
    # Scopes asked for when connecting TikTok. user.info.stats and video.list give the operator dashboard the
    # follower and engagement numbers; the TikTok app must have those scopes (sandbox or an approved revision).
    tiktok_scopes: str = Field(default="user.info.basic,video.publish,user.info.stats,video.list", alias="TIKTOK_SCOPES")
    # Public site used in captions and as link target.
    social_site_url: str = Field(default="https://www.dialogbot.dk", alias="SOCIAL_SITE_URL")

    # Dialogbot Privat (app/modules/privat): a personal assistant for private consumers. Off by default.
    # PRIVAT_ALLOWED_EMAILS: comma list of e-mails that may use it during the pilot; empty = everyone (when enabled).
    privat_enabled: bool = Field(default=False, alias="PRIVAT_ENABLED")
    privat_allowed_emails: str = Field(default="", alias="PRIVAT_ALLOWED_EMAILS")
    # Platform numbers that place private calls and receive call-backs: comma list of E.164, each optionally with its
    # Vapi phone-number id ("+4589871234=3f2a…"); without an id the number must exist as a phone_numbers row.
    # Dialogbot never buys these automatically.
    privat_pool_numbers: str = Field(default="", alias="PRIVAT_POOL_NUMBERS")
    # Unused since 2026-11-11 (the credit pack became Opkaldssaldo top-ups of 50/100/200 kr., always inline price_data).
    # Kept so an existing env var does not break settings; remove it with the env var.
    privat_stripe_price_id: str | None = Field(default=None, alias="PRIVAT_STRIPE_PRICE_ID")
    # Optional Stripe Price ids for the subscriptions (app/modules/privat/subscriptions.py), one per plan and interval.
    # Unset = inline price_data with the amounts from app/modules/billing/prices.py (incl. VAT).
    privat_stripe_price_basis_month: str | None = Field(default=None, alias="PRIVAT_STRIPE_PRICE_BASIS_MONTH")
    privat_stripe_price_basis_year: str | None = Field(default=None, alias="PRIVAT_STRIPE_PRICE_BASIS_YEAR")
    privat_stripe_price_plus_month: str | None = Field(default=None, alias="PRIVAT_STRIPE_PRICE_PLUS_MONTH")
    privat_stripe_price_plus_year: str | None = Field(default=None, alias="PRIVAT_STRIPE_PRICE_PLUS_YEAR")
    privat_stripe_price_familie_month: str | None = Field(default=None, alias="PRIVAT_STRIPE_PRICE_FAMILIE_MONTH")
    privat_stripe_price_familie_year: str | None = Field(default=None, alias="PRIVAT_STRIPE_PRICE_FAMILIE_YEAR")
    # VAT on Privat (B2C) sales to EU consumers outside Denmark (docs/markets.md): "danish" = 25 % Danish VAT (allowed
    # while cross-border B2C sales in the EU stay under 10.000 EUR a year); "destination" = the consumer's own
    # country's rate (needs OSS registration at Skattestyrelsen first).
    privat_eu_vat_mode: Literal["danish", "destination"] = Field(default="danish", alias="PRIVAT_EU_VAT_MODE")
    # True once Dialogbot is VOEC-registered in Norway (required above 50.000 NOK a year to Norwegian consumers):
    # Privat checkouts for Norway then carry 25 % Norwegian VAT. False = no VAT on Norwegian consumers.
    no_voec_registered: bool = Field(default=False, alias="NO_VOEC_REGISTERED")
    # Stripe Tax (Stripe's automatic tax) decides all VAT when true: Erhverv invoices and Privat checkouts are sent with
    # automatic_tax and SaaS tax codes, and no tax rates of our own. False = the manual rules in
    # app/modules/billing/markets.py with fixed Stripe tax rates. Turn on only after Stripe Tax is activated in the
    # Stripe account (docs/markets.md, "Stripe Tax setup") – Stripe rejects automatic_tax otherwise.
    stripe_tax_enabled: bool = Field(default=False, alias="STRIPE_TAX_ENABLED")
    # Short invitation links people text from their own phone: <base><code>, resolved by the web route /i/{code}.
    privat_short_url_base: str = Field(default="https://dialogbot.app/i/", alias="PRIVAT_SHORT_URL_BASE")
    privat_group_url_base: str = Field(default="https://dialogbot.app/g/", alias="PRIVAT_GROUP_URL_BASE")
    # The caller's IP for the per-IP limits (lookup_limits.client_ip, F-PS-02). CLIENT_IP_SECRET is shared with the web
    # BFF (same value on Vercel): the BFF signs the visitor's IP with it. Once set, an unsigned request is counted by
    # the X-Forwarded-For entry TRUSTED_PROXY_HOPS from the right – the address Render's edge appended, which a client
    # cannot forge. Unset = the old behaviour (first X-Forwarded-For entry), so BFF traffic is never lumped on Vercel's
    # few egress IPs before the web side signs.
    client_ip_secret: str | None = Field(default=None, alias="CLIENT_IP_SECRET")
    trusted_proxy_hops: int = Field(default=1, ge=1, le=5, alias="TRUSTED_PROXY_HOPS")
    # Web Push (VAPID) for Dialogbot Privat. `python -m scripts.generate_vapid` prints a new pair. Without the keys,
    # notifications go by e-mail. VAPID_SUBJECT is a mailto: or https: contact for the push services.
    vapid_public_key: str | None = Field(default=None, alias="VAPID_PUBLIC_KEY")
    vapid_private_key: str | None = Field(default=None, alias="VAPID_PRIVATE_KEY")
    vapid_subject: str = Field(default="mailto:info@dialogbot.dk", alias="VAPID_SUBJECT")
    # Add-ons (app/modules/privat/addons.py) switched on when a private account is created.
    privat_default_addons: str = Field(default="ring-for-mig,delte-lister,oenskelister", alias="PRIVAT_DEFAULT_ADDONS")
    # Pakker app (app/modules/privat/parcels.py): 17TRACK tracking API key (api.17track.net). Without it the app is
    # «Kommer snart». Only the tracking number is sent to 17TRACK.
    track17_api_key: str | None = Field(default=None, alias="TRACK17_API_KEY")
    # Rejser app (app/modules/privat/travel.py): real prices only. Duffel (flight offers, later booking) and/or
    # Travelpayouts (cached fares + affiliate booking links; the marker is Dialogbot's partner id). Without either the
    # app is «Kommer snart».
    duffel_access_token: str | None = Field(default=None, alias="DUFFEL_ACCESS_TOKEN")
    travelpayouts_token: str | None = Field(default=None, alias="TRAVELPAYOUTS_TOKEN")
    travelpayouts_marker: str | None = Field(default=None, alias="TRAVELPAYOUTS_MARKER")
    # Partner links shown in the Privat apps (app/modules/privat/brand.py), always marked «Annonce». JSON:
    # {"mobil": {"name": "…", "url": "https://…", "text": "Find et billigere mobilabonnement"}, …}. Categories:
    # mobil, internet, el, streaming, forsikring, dyreforsikring, flyttefirma, fest, hjem, garanti, dagligvarer,
    # fitness. Empty = none shown.
    privat_partner_links: str = Field(default="", alias="PRIVAT_PARTNER_LINKS")

    # Which HTTP surface this process serves (docs/public-api.md). internal = /api/v1 for the apps; public = only
    # api.dialogbot.app/v1 (API keys, no sessions, no provider webhooks); all = both (dev, tests, a single-process setup).
    app_surface: Literal["internal", "public", "all"] = Field(default="all", alias="APP_SURFACE")
    public_api_base_url: str = Field(default="https://api.dialogbot.app", alias="PUBLIC_API_BASE_URL")
    # Per API key, per minute. In-process token buckets (one bucket per key and class per process); a shared backend
    # can replace app/modules/public_api/ratelimit.LIMITER without touching the routes.
    public_api_read_rpm: int = Field(default=600, ge=1, alias="PUBLIC_API_READ_RPM")
    public_api_write_rpm: int = Field(default=60, ge=1, alias="PUBLIC_API_WRITE_RPM")
    # A webhook endpoint is switched off after this many consecutive failed deliveries (re-enabled by the customer).
    public_api_webhook_disable_after: int = Field(default=20, ge=1, alias="PUBLIC_API_WEBHOOK_DISABLE_AFTER")

    # Dev tooling: the simulated mailbox and test identities are gated on this.
    enable_dev_tools: bool = Field(default=False, alias="ENABLE_DEV_TOOLS")

    worker_poll_seconds: float = Field(default=1.0, alias="WORKER_POLL_SECONDS")
    worker_lease_seconds: int = Field(default=60, alias="WORKER_LEASE_SECONDS")
    worker_max_attempts: int = Field(default=5, alias="WORKER_MAX_ATTEMPTS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Cold e-mail outreach for Dialogbot's own sales (app/modules/outreach, docs/sales/cold-outreach.md) ----------
    # off = nothing runs · dry_run = leads are checked, researched, written and audited, nothing is ever sent ·
    # live = audited e-mails go to the sending provider. Live refuses to start without the settings below.
    outreach_mode: Literal["off", "dry_run", "live"] = Field(default="off", alias="OUTREACH_MODE")
    claude_research_model: str = Field(default="claude-sonnet-4-6", alias="CLAUDE_RESEARCH_MODEL")
    claude_writer_model: str = Field(default="claude-sonnet-4-6", alias="CLAUDE_WRITER_MODEL")
    claude_auditor_model: str = Field(default="claude-haiku-4-5", alias="CLAUDE_AUDITOR_MODEL")
    outreach_ai_max_retries: int = Field(default=4, alias="OUTREACH_AI_MAX_RETRIES")  # SDK backoff on 429/5xx
    outreach_web_search: bool = Field(default=True, alias="OUTREACH_WEB_SEARCH")
    outreach_min_confidence: float = Field(default=0.6, alias="OUTREACH_MIN_CONFIDENCE")
    # resend | smtp are implemented; instantly | smartlead are reserved and fail closed (never a green stub).
    outreach_provider: Literal["resend", "smtp", "instantly", "smartlead"] = Field(default="resend", alias="OUTREACH_PROVIDER")
    outreach_resend_api_key: str | None = Field(default=None, alias="OUTREACH_RESEND_API_KEY")
    outreach_smtp_host: str | None = Field(default=None, alias="OUTREACH_SMTP_HOST")
    outreach_smtp_port: int = Field(default=587, alias="OUTREACH_SMTP_PORT")
    outreach_smtp_username: str | None = Field(default=None, alias="OUTREACH_SMTP_USERNAME")
    outreach_smtp_password: str | None = Field(default=None, alias="OUTREACH_SMTP_PASSWORD")
    # Sender identity. Inboxes: comma-separated addresses the e-mails rotate over, each with its own daily limit.
    outreach_sender_name: str = Field(default="Dialogbot", alias="OUTREACH_SENDER_NAME")
    outreach_sender_inboxes: str = Field(default="", alias="OUTREACH_SENDER_INBOXES")
    outreach_legal_name: str = Field(default="Dialogbot, CVR 25632710", alias="OUTREACH_LEGAL_NAME")
    # CAN-SPAM and CASL ask for a full postal address (street, postal code). Unset = the short «Aarhus, Denmark»
    # line, which is fine for a dry run and refused in live mode.
    outreach_postal_address: str | None = Field(default=None, alias="OUTREACH_POSTAL_ADDRESS")
    outreach_privacy_url: str = Field(default="https://dialogbot.app/privatliv", alias="OUTREACH_PRIVACY_URL")
    outreach_daily_limit_per_inbox: int = Field(default=30, alias="OUTREACH_DAILY_LIMIT_PER_INBOX")
    outreach_daily_limit_per_domain: int = Field(default=150, alias="OUTREACH_DAILY_LIMIT_PER_DOMAIN")
    # Markets the matrix holds back until a lawyer has signed them off (ES, PL): comma-separated country codes.
    outreach_signed_off_markets: str = Field(default="", alias="OUTREACH_SIGNED_OFF_MARKETS")
    # Blocked markets whose valid B2B leads go to the manual call list instead of being dropped.
    outreach_call_queue_countries: str = Field(default="DK", alias="OUTREACH_CALL_QUEUE_COUNTRIES")
    # Countries whose phone numbers the callback demo on dialogbot.app actually rings. Live sending to a country
    # outside this list is refused: the e-mail's only call to action would not work for the reader.
    outreach_demo_callback_countries: str = Field(default="DK", alias="OUTREACH_DEMO_CALLBACK_COUNTRIES")
    # Local number the demo rings from, per market. Unset = the copy may not mention a local number.
    outreach_callback_number_us: str | None = Field(default=None, alias="OUTREACH_CALLBACK_NUMBER_US")
    outreach_callback_number_uk: str | None = Field(default=None, alias="OUTREACH_CALLBACK_NUMBER_UK")
    # A demo LINE: a local number in that market that Dialogbot's own assistant answers, in the caller's language.
    # Where one is set the e-mail invites the reader to ring it (they ring us: no consent question, no SMS code),
    # and the market counts as having a working demo. E.164, e.g. +16283773337.
    outreach_demo_line_us: str | None = Field(default=None, alias="OUTREACH_DEMO_LINE_US")
    outreach_demo_line_uk: str | None = Field(default=None, alias="OUTREACH_DEMO_LINE_UK")
    # Display prices in the e-mail. GBP is not a billing currency (a UK company is billed in EUR), so the UK text is
    # set here; every other market, the US included, reads its list price from billing/markets.py.
    outreach_price_us: str | None = Field(default=None, alias="OUTREACH_PRICE_US")  # unset = the USD list price
    outreach_price_uk: str = Field(default="£275/mo", alias="OUTREACH_PRICE_UK")
    # Shared secret for POST /webhooks/events from providers that do not sign with Svix (header X-Outreach-Secret).
    outreach_webhook_secret: str | None = Field(default=None, alias="OUTREACH_WEBHOOK_SECRET")
    # A person reads replies: a copy of every reply to an outreach inbox is sent here (Resend receives for the
    # inbox domain; see outreach/replies.py). Unset = replies stop the sequence but are only visible in Resend.
    outreach_reply_forward_to: str | None = Field(default=None, alias="OUTREACH_REPLY_FORWARD_TO")

    @property
    def outreach_inboxes(self) -> list[str]:
        return [x.strip().lower() for x in self.outreach_sender_inboxes.split(",") if x.strip()]

    @staticmethod
    def _codes(raw: str) -> set[str]:
        return {"UK" if x.strip().upper() == "GB" else x.strip().upper() for x in raw.split(",") if x.strip()}

    @property
    def outreach_signed_off(self) -> set[str]:
        return self._codes(self.outreach_signed_off_markets)

    @property
    def outreach_call_queue(self) -> set[str]:
        return self._codes(self.outreach_call_queue_countries)

    @property
    def outreach_demo_lines(self) -> dict[str, str]:
        lines = {"US": self.outreach_demo_line_us, "UK": self.outreach_demo_line_uk}
        return {c: n.strip() for c, n in lines.items() if n and n.strip()}

    @property
    def outreach_demo_countries(self) -> set[str]:
        """Markets where the e-mail's call to action works: the callback demo rings them, or they have a demo line."""
        return self._codes(self.outreach_demo_callback_countries) | set(self.outreach_demo_lines)

    @model_validator(mode="after")
    def _fail_closed(self) -> Settings:
        if self.app_env in ("staging", "prod"):
            if not self.secret_key or len(self.secret_key) < 32:
                raise ValueError(f"SECRET_KEY (>=32 chars) is required when APP_ENV={self.app_env}")
            if self.enable_dev_tools:
                raise ValueError(f"ENABLE_DEV_TOOLS must be false when APP_ENV={self.app_env}")
        if self.app_env == "prod" and self.email_adapter == "simulated" and self.app_surface != "public":
            # The public API process sends no mail (deliveries run in the worker), so it needs no mail adapter.
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
        for name, value in (("TRACK17_API_KEY", self.track17_api_key), ("DUFFEL_ACCESS_TOKEN", self.duffel_access_token),
                            ("TRAVELPAYOUTS_TOKEN", self.travelpayouts_token)):
            # the value "fake" switches in a test double (invented parcel statuses, «Testair» fares)
            if (value or "").strip().lower() == "fake" and self.app_env not in ("dev", "test"):
                raise ValueError(f"{name}=fake is a test double and is not allowed when APP_ENV={self.app_env}")
        if self.social_provider == "fake" and self.app_env not in ("dev", "test"):
            raise ValueError(f"SOCIAL_PROVIDER=fake is a test double and is not allowed when APP_ENV={self.app_env}")
        if self.social_provider == "live" and not (self.meta_page_access_token or self.tiktok_client_key):
            raise ValueError("SOCIAL_PROVIDER=live requires META_PAGE_ACCESS_TOKEN and/or TIKTOK_CLIENT_KEY")
        if self.tts_engine == "http" and not (self.tts_service_url and self.tts_service_token):
            raise ValueError("TTS_ENGINE=http requires TTS_SERVICE_URL and TTS_SERVICE_TOKEN")
        if self.voice_storage == "supabase" and not (self.supabase_url and self.supabase_service_role_key):
            raise ValueError("VOICE_STORAGE=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        if self.browser_worker_enabled and self.app_env in ("staging", "prod") and not (
                self.supabase_url and self.supabase_service_role_key):
            raise ValueError("BROWSER_WORKER_ENABLED=true requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY "
                             "(private evidence bucket) when APP_ENV is staging or prod")
        if self.allow_private_fetch and self.app_env not in ("dev", "test"):
            raise ValueError(f"ALLOW_PRIVATE_FETCH is for local tests only and is not allowed when APP_ENV={self.app_env}")
        if self.sales_recording_storage == "supabase" and not (self.supabase_url and self.supabase_service_role_key):
            raise ValueError("SALES_RECORDING_STORAGE=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        if self.sales_outbound_mode == "live":
            missing = [n for n, v in (("SALES_WORKSPACE_ID", self.sales_workspace_id), ("VAPI_API_KEY", self.vapi_api_key),
                                      ("VAPI_SERVER_SECRET", self.vapi_server_secret)) if not v]
            if self.telephony_provider != "live":
                missing.append("TELEPHONY_PROVIDER=live")
            if missing:
                raise ValueError("SALES_OUTBOUND_MODE=live requires " + ", ".join(missing))
        if self.outreach_provider in ("instantly", "smartlead") and self.outreach_mode == "live":
            raise ValueError(f"OUTREACH_PROVIDER={self.outreach_provider} is not implemented; use resend or smtp")
        if self.outreach_mode == "live":
            missing = [n for n, ok in (
                ("OUTREACH_SENDER_INBOXES", bool(self.outreach_inboxes)),
                ("OUTREACH_POSTAL_ADDRESS", bool(self.outreach_postal_address)),
                ("OUTREACH_RESEND_API_KEY", self.outreach_provider != "resend" or bool(self.outreach_resend_api_key)),
                ("OUTREACH_SMTP_HOST", self.outreach_provider != "smtp" or bool(self.outreach_smtp_host)),
                ("AI_PROVIDER=anthropic", self.ai_provider == "anthropic"),
            ) if not ok]
            if missing:
                raise ValueError("OUTREACH_MODE=live requires " + ", ".join(missing))
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
