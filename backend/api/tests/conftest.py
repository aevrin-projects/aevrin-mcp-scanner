from __future__ import annotations

import os

import pytest

from aevrin_api.config import Settings

# --- Hermetic settings -----------------------------------------------------
# A test run must not depend on the machine it runs on. Two things would
# otherwise leak in: backend/api/.env, which pydantic-settings reads by
# default, and any matching variable exported in the developer's shell.
#
# That is not hypothetical. Every test below that builds a partial
# `Settings(...)` was quietly having the rest of its required fields filled
# from a real .env, so the suite passed on a developer machine and failed the
# moment CI ran it in a clean checkout.
#
# Mutating model_config affects only this (test) process. Optional fields are
# deliberately left unset, so features like the GitHub App and Razorpay report
# themselves unconfigured, which is what the tests asserting that behaviour
# expect.
Settings.model_config["env_file"] = None

for _field, _info in Settings.model_fields.items():
    os.environ.pop((_info.alias or _field).upper(), None)

os.environ.update(
    {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
        "API_KEY_PEPPER": "test-pepper",
        "UPSTASH_REDIS_REST_URL": "https://test-redis.upstash.io",
        "UPSTASH_REDIS_REST_TOKEN": "redis-token",
        "R2_ACCOUNT_ID": "account-id",
        "R2_ACCESS_KEY_ID": "access-key",
        "R2_SECRET_ACCESS_KEY": "secret-key",
        "R2_S3_ENDPOINT": "https://account-id.r2.cloudflarestorage.com",
    }
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="anon-key",
        supabase_service_role_key="service-role-key",
        api_key_pepper="test-pepper",
        upstash_redis_rest_url="https://test-redis.upstash.io",
        upstash_redis_rest_token="redis-token",
        r2_account_id="account-id",
        r2_access_key_id="access-key",
        r2_secret_access_key="secret-key",
        r2_s3_endpoint="https://account-id.r2.cloudflarestorage.com",
        web_origin="http://localhost:3000",
    )
