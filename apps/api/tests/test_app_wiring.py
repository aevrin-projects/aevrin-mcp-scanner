"""Confirms the FastAPI app actually boots and every router is wired —
config.Settings is read once at import time, so required env vars must be
set before `aevrin_api.main` is imported."""

from __future__ import annotations

import pytest


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-that-is-long-enough")
    monkeypatch.setenv("API_KEY_PEPPER", "test-pepper")
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://test-redis.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "redis-token")
    monkeypatch.setenv("R2_ACCOUNT_ID", "account-id")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "access-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-key")
    monkeypatch.setenv("R2_S3_ENDPOINT", "https://account-id.r2.cloudflarestorage.com")
    monkeypatch.setenv("WEB_ORIGIN", "http://localhost:3000")

    from aevrin_api.config import get_settings

    get_settings.cache_clear()

    import importlib

    import aevrin_api.main as main_module

    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    with TestClient(main_module.app) as client:
        yield client

    get_settings.cache_clear()


def test_health_check(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_route_requires_auth(app_client):
    resp = app_client.get("/scans")
    assert resp.status_code == 401


def test_protected_route_rejects_garbage_token(app_client):
    resp = app_client.get("/scans", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_create_scan_rejects_invalid_body(app_client):
    resp = app_client.post(
        "/scans",
        json={"target_type": "not_real", "target": "x"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422)


def test_cors_headers_present_for_web_origin(app_client):
    resp = app_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_hook_endpoint_requires_api_key(app_client):
    resp = app_client.get("/hook/cache", params={"target": "github.com/a/b"})
    assert resp.status_code == 401


def test_cli_upload_requires_api_key(app_client):
    resp = app_client.post(
        "/cli/upload",
        json={"target_type": "github_repo", "target": "x", "score": 100, "findings": []},
    )
    assert resp.status_code == 401
