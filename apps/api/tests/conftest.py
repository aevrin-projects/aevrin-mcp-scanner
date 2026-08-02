from __future__ import annotations

import pytest

from aevrin_api.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="anon-key",
        supabase_service_role_key="service-role-key",
        supabase_jwt_secret="test-jwt-secret",
        api_key_pepper="test-pepper",
        upstash_redis_rest_url="https://test-redis.upstash.io",
        upstash_redis_rest_token="redis-token",
        r2_account_id="account-id",
        r2_access_key_id="access-key",
        r2_secret_access_key="secret-key",
        r2_s3_endpoint="https://account-id.r2.cloudflarestorage.com",
        web_origin="http://localhost:3000",
    )
