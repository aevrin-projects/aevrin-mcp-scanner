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
    # encrypt a BYOK account's own model API key before it's stored in
    # accounts.byok_key_encrypted; see crypto.py. None means BYOK key
    # storage is disabled (accounts can still buy the add-on, just can't
    # save a key yet), not an error.
    byok_encryption_key: str | None = None

    # Admin panel. The allowlist is an explicit comma-separated list of
    # auth.users IDs rather than a role column; see admin_auth.py for why.
    admin_user_ids: str | None = None
    admin_session_idle_minutes: int = 30

    # CORS
    web_origin: str = "http://localhost:3000"

    # Rate limits
    scans_per_user_per_hour: int = 10
    scans_per_ip_per_hour: int = 20
    cli_uploads_per_key_per_hour: int = 30

    port: int = Field(default=8000, alias="PORT")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
