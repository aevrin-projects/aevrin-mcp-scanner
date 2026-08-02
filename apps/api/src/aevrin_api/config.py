from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # frozen=True makes Settings hashable (all fields are str/int/None), which
    # get_redis()/get_r2_client() rely on — both are @lru_cache'd on a
    # `settings` argument to reuse one connection/client per process.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # Supabase. No JWT secret needed — auth tokens are verified against the
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

    # GitHub (Scorecard + OSV rate limits + private clone)
    github_token: str | None = None

    # DefectDojo
    defectdojo_url: str | None = None
    defectdojo_api_key: str | None = None

    # Razorpay billing (prep-only until the user supplies real values — see
    # razorpay_client.py; None means "billing disabled", not an error).
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    razorpay_plan_hobby_monthly: str | None = None
    razorpay_plan_hobby_annual: str | None = None
    razorpay_plan_team_monthly: str | None = None
    razorpay_plan_team_annual: str | None = None

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
