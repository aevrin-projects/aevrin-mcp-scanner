from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # frozen=True makes Settings hashable (all fields are str/int/None), which
    # get_redis()/get_r2_client() rely on, both are @lru_cache'd on a
    # `settings` argument to reuse one connection/client per process.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # Supabase. No JWT secret needed: auth tokens are verified against the
    # project's JWKS endpoint (see security.py), which handles both current
    # asymmetric signing keys and legacy HS256 tokens during rotation.
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Server-side pepper for HMAC-hashing CLI API keys before storage.
    api_key_pepper: str

    # Upstash Redis
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str
    # A second instance, used only when the primary refuses; see
    # redis_client.get_fallback_redis. These were read through getattr() on a
    # Settings that never declared them, so the lookup always returned None
    # and the failover the code documents could not engage at all. Unset is
    # still fine: with no spare, callers fall back to failing open.
    upstash_fallback_redis_rest_url: str | None = None
    upstash_fallback_redis_rest_token: str | None = None

    # Cloudflare R2 (S3-compatible)
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str = "aevrin-report"
    r2_s3_endpoint: str

    # GitHub (Scorecard + OSV rate limits + private clone), a plain PAT,
    # distinct from the GitHub App identity below.
    github_token: str | None = None

    # GitHub App ("Connect GitHub"), JWT-based installation-token auth for
    # reading a private repository the person has granted. Architecturally
    # separate from both github_token above (a PAT) and Supabase's GitHub
    # OAuth identity provider (Sign in with GitHub, configured directly in
    # the Supabase dashboard, not here). None means repo connect is
    # disabled, and the picker says so rather than erroring.
    # Exactly three values are needed, and all three come from the App's
    # settings page on github.com; see README, Connecting GitHub.
    github_app_id: str | None = None
    github_app_private_key: str | None = None
    # The App's public slug (from its github.com/apps/<slug> URL), needed to
    # build the "Connect GitHub for Auto-Fix" install link. Not a secret.
    github_app_slug: str | None = None

    # How many reverse proxies in front of this app append to
    # X-Forwarded-For. 1 behind a bare AWS ALB or Azure Application
    # Gateway; 2 with CloudFront or Front Door in front of that. Getting
    # this wrong in the high direction reads a proxy's own address as the
    # client; in the low direction it trusts a client-supplied value.
    trusted_proxy_hops: int = 1

    # DefectDojo
    defectdojo_url: str | None = None
    defectdojo_api_key: str | None = None

    # Razorpay billing: Standard Checkout (Orders API), one-time payments
    # per cycle rather than Subscriptions (see razorpay_client.py). None
    # means "billing disabled", not an error, same as defectdojo_url below.
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    # Powers LLM triage (triage.py). None means triage is unconfigured; it
    # fails open, keeping the deterministic scanner result rather than
    # erroring.
    deepseek_api_key: str | None = None

    # Fernet key (44-char urlsafe-base64, `Fernet.generate_key()`) used to
    # encrypt secrets this server holds on a user's behalf -- today only
    # admin TOTP secrets; see crypto.py. None means secret storage is
    # disabled, which is a refusal at the point of use, not an error here.
    byok_encryption_key: str | None = None

    # Admin panel. The allowlist is an explicit comma-separated list of
    # auth.users IDs rather than a role column; see admin_auth.py for why.
    admin_user_ids: str | None = None
    admin_session_idle_minutes: int = 30

    # ---------------------------------------------------------------- marketplace
    # The Supabase user id catalogue scans are attributed to. A marketplace
    # scan has no customer: it is Aevrin scanning a public server once so
    # every user can read the result. Attributing it to a real customer would
    # put a catalogue scan in their history and against their quota, so a
    # dedicated account is used instead. None disables catalogue scanning,
    # which is a refusal at the point of use rather than an error here.
    marketplace_scan_user_id: str | None = None
    # Token protecting the scheduled-job endpoints. The weekly sync and
    # provider refresh are triggered by an external scheduler (EventBridge,
    # cron, a container task) rather than by a signed-in human, so they
    # authenticate with this rather than with a session.
    scheduler_token: str | None = None

    # ---------------------------------------------------------------- AI providers
    # Aevrin's own provider credentials, used *only* to refresh the public
    # model catalogue. Every one of the four providers requires a key to list
    # models -- none of them publish that list anonymously -- and borrowing a
    # customer's key for Aevrin's own bookkeeping would bill them for it.
    #
    # All optional. A provider with no catalogue key simply is not refreshed:
    # its previously synced models keep working and the admin page shows why
    # the sync did not run. It never wipes what it cannot re-fetch.
    groq_catalog_api_key: str | None = None
    openai_catalog_api_key: str | None = None
    anthropic_catalog_api_key: str | None = None
    gemini_catalog_api_key: str | None = None

    # CORS. `web_origin` is also used to build links *back into* the
    # authenticated app (device-pairing URLs, quota-exceeded upgrade links,
    # the GitHub App post-install redirect) - it means "the app's own
    # origin," not "every origin CORS should allow." `public_web_origin` is
    # purely additive: the public marketing site (frontend-public/) calls
    # this API too (status-page health checks, pageview tracking) from a
    # different origin, and needs CORS to allow it without ever being where
    # an app-internal link points.
    web_origin: str = "http://localhost:3000"
    public_web_origin: str | None = None

    # Rate limits
    scans_per_user_per_hour: int = 10
    scans_per_ip_per_hour: int = 20
    cli_uploads_per_key_per_hour: int = 30

    port: int = Field(default=8000, alias="PORT")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
