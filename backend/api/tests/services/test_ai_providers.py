"""Provider adapters, credential handling, and the catalogue sync fail-safe."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from cryptography.fernet import Fernet

from aevrin_api.config import Settings
from aevrin_api.integrations.ai_providers import (
    PROVIDER_KEYS,
    SPECS,
    ProviderError,
    complete,
    list_models,
)
from aevrin_api.schemas.ai import ProviderCredentialOut
from aevrin_api.services.ai.credentials import _hint, public_view
from aevrin_api.services.ai.provider_sync import catalog_key


@pytest.fixture
def settings_with_key() -> Settings:
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        api_key_pepper="pepper",
        upstash_redis_rest_url="https://r.upstash.io",
        upstash_redis_rest_token="t",
        r2_account_id="a",
        r2_access_key_id="b",
        r2_secret_access_key="c",
        r2_s3_endpoint="https://r2",
        byok_encryption_key=Fernet.generate_key().decode(),
    )


# --------------------------------------------------------------------------
# The key must never come back


def test_no_response_model_can_carry_an_api_key():
    """Enforced by shape rather than by remembering to strip a field."""
    assert "api_key" not in ProviderCredentialOut.model_fields
    assert "encrypted_api_key" not in ProviderCredentialOut.model_fields


def test_public_view_is_an_allowlist_not_a_denylist():
    """A denylist would need updating every time a column is added, and the
    failure mode of forgetting is that the new column ships to the browser."""
    row = {
        "provider": "groq",
        "encrypted_api_key": "gAAAAAB-ciphertext",
        "key_hint": "9f2a",
        "model_id": "llama-3.3-70b",
        "some_future_internal_column": "should not leak",
    }
    view = public_view(row)
    assert view["key_present"] is True
    assert view["key_hint"] == "9f2a"
    assert "encrypted_api_key" not in view
    assert "some_future_internal_column" not in view


def test_the_hint_is_four_characters_and_short_keys_get_none():
    assert _hint("sk-abcdefghijklmnop") == "mnop"
    assert _hint("short") == ""


# --------------------------------------------------------------------------
# Adapters


@pytest.mark.asyncio
@respx.mock
async def test_groq_and_openai_share_the_openai_model_shape():
    for provider in ("groq", "openai"):
        respx.get(f"{SPECS[provider].base_url}/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "model-a", "context_window": 128000, "active": True},
                        {"id": "model-retired", "active": False},
                    ]
                },
            )
        )
        models = await list_models(provider, "test-key")
        assert [m.model_id for m in models] == ["model-a", "model-retired"]
        assert models[0].context_window == 128000
        assert models[1].deprecated is True


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_uses_display_name():
    respx.get(f"{SPECS['anthropic'].base_url}/models").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "claude-x", "display_name": "Claude X"}]}
        )
    )
    (model,) = await list_models("anthropic", "test-key")
    assert model.model_id == "claude-x"
    assert model.display_name == "Claude X"


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_sends_the_version_header_not_a_bearer_token():
    route = respx.get(f"{SPECS['anthropic'].base_url}/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    await list_models("anthropic", "secret-key")
    headers = route.calls.last.request.headers
    assert headers["x-api-key"] == "secret-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in headers


@pytest.mark.asyncio
@respx.mock
async def test_gemini_sends_the_key_as_a_header_never_a_query_parameter():
    """Query strings end up in access logs and referrer headers."""
    route = respx.get(f"{SPECS['gemini'].base_url}/models").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    await list_models("gemini", "secret-key")
    request = route.calls.last.request
    assert request.headers["x-goog-api-key"] == "secret-key"
    assert "key" not in request.url.params
    assert "secret-key" not in str(request.url)


@pytest.mark.asyncio
@respx.mock
async def test_gemini_embedding_models_are_filtered_out():
    """Offering an embedding model under "explain this finding" would fail at
    the moment somebody actually needed the explanation."""
    respx.get(f"{SPECS['gemini'].base_url}/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-x",
                        "displayName": "Gemini X",
                        "supportedGenerationMethods": ["generateContent"],
                        "inputTokenLimit": 1000000,
                    },
                    {
                        "name": "models/text-embedding-004",
                        "displayName": "Embedding",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )
    )
    models = await list_models("gemini", "k")
    assert [m.model_id for m in models] == ["gemini-x"]


@pytest.mark.asyncio
@respx.mock
async def test_groq_and_openai_non_chat_models_are_filtered_out():
    """whisper/tts/embedding/moderation/image/legacy-completion/guard models
    live on the same /v1/models list as the chat models but 400 (or answer
    uselessly) against /chat/completions, the only endpoint complete() calls.
    Offering one in the "explain this finding" dropdown fails at the moment
    somebody actually needed the explanation -- the exact bug this guards."""
    for provider in ("groq", "openai"):
        respx.get(f"{SPECS[provider].base_url}/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "llama-3.3-70b-versatile"},
                        {"id": "whisper-large-v3"},
                        {"id": "tts-1"},
                        {"id": "text-embedding-3-small"},
                        {"id": "omni-moderation-latest"},
                        {"id": "dall-e-3"},
                        {"id": "gpt-image-1"},
                        {"id": "davinci-002"},
                        {"id": "babbage-002"},
                        {"id": "computer-use-preview"},
                        {"id": "meta-llama/llama-prompt-guard-2-22m"},
                        {"id": "openai/gpt-oss-safeguard-20b"},
                    ]
                },
            )
        )
        models = await list_models(provider, "test-key")
        assert [m.model_id for m in models] == ["llama-3.3-70b-versatile"]


@pytest.mark.asyncio
@respx.mock
async def test_an_auth_failure_produces_an_actionable_message_without_the_body():
    respx.get(f"{SPECS['groq'].base_url}/models").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad key sk-leaked123456"}})
    )
    with pytest.raises(ProviderError) as caught:
        await list_models("groq", "sk-leaked123456")
    message = str(caught.value)
    assert "Settings" in message
    # The provider's body can echo request content, and request content is one
    # careless log line away from being the key.
    assert "sk-leaked123456" not in message


@pytest.mark.asyncio
@respx.mock
async def test_rate_limits_are_marked_retryable():
    respx.get(f"{SPECS['groq'].base_url}/models").mock(return_value=httpx.Response(429))
    with pytest.raises(ProviderError) as caught:
        await list_models("groq", "k")
    assert caught.value.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_completion_output_is_capped_regardless_of_configuration():
    route = respx.post(f"{SPECS['groq'].base_url}/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "answer"}}], "usage": {}}
        )
    )
    await complete("groq", "k", model="m", system="s", user="u", max_tokens=999_999)
    body = json.loads(route.calls.last.request.content)
    assert body["max_tokens"] == 4096


@pytest.mark.asyncio
@respx.mock
async def test_oversized_input_is_truncated_before_leaving_the_process():
    route = respx.post(f"{SPECS['groq'].base_url}/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "a"}}], "usage": {}}
        )
    )
    await complete("groq", "k", model="m", system="s", user="x" * 200_000)
    assert len(route.calls.last.request.content) < 120_000


# --------------------------------------------------------------------------
# Catalogue sync: never uses a customer's key, never wipes on failure


def test_catalog_keys_come_from_settings_not_from_user_credentials(settings_with_key):
    """Borrowing a customer's key for Aevrin's own bookkeeping would bill
    them for it and leak which vendors Aevrin polls into their dashboard."""
    for provider in PROVIDER_KEYS:
        # Unset in the test settings, so every provider reports "no catalogue
        # credential" rather than silently reaching for a user's.
        assert catalog_key(settings_with_key, provider) is None


def test_every_provider_has_a_catalog_key_setting():
    settings_fields = Settings.model_fields
    for provider in PROVIDER_KEYS:
        assert f"{provider}_catalog_api_key" in settings_fields


# --------------------------------------------------------------------------
# Catalogue refresh with an explicitly supplied key
#
# The dropdown was empty for every provider because this deployment has never
# had a *_CATALOG_API_KEY, so nothing ever populated ai_provider_models and
# "add a provider, then pick a model" dead-ended at step two. Saving a key now
# refreshes the catalogue with that key.


class _CatalogDb:
    """Enough of SupabaseRest for sync_provider's write path."""

    def __init__(self) -> None:
        self.inserted: list[dict] = []
        self.updated: list[tuple[str, dict]] = []

    async def select(self, table: str, filters=None, **kwargs):
        return []

    async def insert(self, table: str, rows, **kwargs):
        if table == "ai_provider_models":
            self.inserted.append(rows)
        return [rows] if isinstance(rows, dict) else rows

    async def update(self, table: str, filters, patch, **kwargs):
        self.updated.append((table, patch))
        return []


@pytest.mark.asyncio
@respx.mock
async def test_an_explicit_key_populates_the_catalogue_without_a_catalog_credential(
    settings_with_key,
):
    from aevrin_api.services.ai.provider_sync import sync_provider

    respx.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]}
        )
    )

    db = _CatalogDb()
    # settings_with_key deliberately has no openai_catalog_api_key, so without
    # the explicit key this would report "no catalogue credential" and write
    # nothing -- which is exactly the state that produced the empty dropdown.
    report = await sync_provider(db, settings_with_key, "openai", api_key="sk-user-key")

    assert report.ok, report.error
    assert {row["model_id"] for row in db.inserted} == {"gpt-4o-mini", "gpt-4o"}
    # Learned from a real provider call, not seeded, so the admin page can
    # tell the difference.
    assert all(row["from_provider_api"] is True for row in db.inserted)


@pytest.mark.asyncio
async def test_without_any_key_the_catalogue_is_left_alone(settings_with_key):
    """The failure must be recorded, never turned into an empty catalogue."""
    from aevrin_api.services.ai.provider_sync import sync_provider

    db = _CatalogDb()
    report = await sync_provider(db, settings_with_key, "openai")

    assert not report.ok
    assert "CATALOG_API_KEY" in (report.error or "")
    assert db.inserted == []
