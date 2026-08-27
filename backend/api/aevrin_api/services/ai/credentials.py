"""Storing and reading a user's AI provider API keys.

An API key here belongs to the customer and pays the customer's bill. That
makes it one of the most sensitive things this server holds, and the rules
around it are absolute rather than best-effort:

* Encrypted at rest, with the same Fernet envelope the admin TOTP secrets use.
  There is no plaintext column and no code path that creates one.
* Never returned to a browser. Not on save, not on read, not in an error. What
  the dashboard receives is `key_present`, a four-character hint, and the
  configuration around the key.
* Never logged. No log line in this module interpolates a key, and the
  provider layer's errors are constructed without the request body for the
  same reason.
* Decrypted only in-process, at the moment of a call, and never persisted in
  its decrypted form.

The catalogue sync job does not use any of this. Model metadata is public
provider information, and borrowing a customer's key to fetch it would bill
them for Aevrin's bookkeeping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.ai_providers import PROVIDER_KEYS, SPECS
from aevrin_api.utils.crypto import EncryptionUnavailable, decrypt_secret, encrypt_secret

logger = logging.getLogger("aevrin.ai.credentials")


@dataclass(frozen=True)
class ProviderCredential:
    """A usable credential: decrypted, in priority order, ready to call with.

    Constructed only inside this process and never serialised. If you find
    yourself putting one of these in a response model, stop.
    """

    provider: str
    api_key: str
    model_id: str | None
    temperature: float | None
    max_tokens: int | None
    system_prompt: str | None
    priority: int


def _hint(api_key: str) -> str:
    """The last four characters, for telling two keys apart in a list.

    Four is enough to disambiguate and far too few to reconstruct. Keys
    shorter than eight characters get no hint at all rather than most of
    themselves.
    """
    return api_key[-4:] if len(api_key) >= 8 else ""


async def save_credential(
    db: SupabaseRest,
    settings: Settings,
    *,
    user_id: str,
    org_id: str | None,
    provider: str,
    api_key: str,
    model_id: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    system_prompt: str | None = None,
    priority: int = 1,
) -> dict[str, Any]:
    """Store or rotate one provider credential.

    Upserts on (user_id, provider): rotating a key replaces it rather than
    accumulating rows, so there is never an old key lying around that nobody
    remembers granting.
    """
    if provider not in PROVIDER_KEYS:
        raise ValueError(f"unknown provider {provider!r}")
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("API key is required")

    try:
        ciphertext = encrypt_secret(settings, api_key)
    except EncryptionUnavailable as exc:
        # Refusing is the only correct answer. Storing it in plaintext
        # "temporarily" is how plaintext credentials end up in a database
        # permanently.
        raise ValueError(
            "Secret storage is not configured on this server, so the key cannot be stored safely."
        ) from exc

    row = {
        "user_id": user_id,
        "org_id": org_id,
        "provider": provider,
        "encrypted_api_key": ciphertext,
        "key_hint": _hint(api_key),
        "model_id": model_id,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": (system_prompt or "").strip()[:4000] or None,
        "priority": max(1, min(int(priority), 5)),
        "enabled": True,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    saved = await db.insert("ai_provider_credentials", row, upsert_on="user_id,provider")
    return public_view(saved[0] if saved else row)


async def update_settings(
    db: SupabaseRest,
    *,
    user_id: str,
    provider: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    """Change the configuration around a key without touching the key.

    The allowlist is the point: a PATCH body cannot reach `encrypted_api_key`
    or `key_hint` from here, so no request shape can overwrite a stored key
    with attacker-supplied ciphertext or blank it out.
    """
    allowed = {"model_id", "temperature", "max_tokens", "system_prompt", "priority", "enabled"}
    clean = {k: v for k, v in patch.items() if k in allowed}
    if not clean:
        return None
    if "priority" in clean and clean["priority"] is not None:
        clean["priority"] = max(1, min(int(clean["priority"]), 5))
    clean["updated_at"] = datetime.now(UTC).isoformat()

    rows = await db.update(
        "ai_provider_credentials", {"user_id": user_id, "provider": provider}, clean
    )
    return public_view(rows[0]) if rows else None


async def delete_credential(db: SupabaseRest, *, user_id: str, provider: str) -> None:
    await db.delete("ai_provider_credentials", {"user_id": user_id, "provider": provider})


def public_view(row: dict[str, Any]) -> dict[str, Any]:
    """The only shape of a credential that may leave this server.

    Written as an allowlist rather than by deleting the secret fields. A
    denylist would need updating every time a column is added, and the failure
    mode of forgetting is that the new column ships to the browser.
    """
    provider = row.get("provider", "")
    spec = SPECS.get(provider)
    return {
        "provider": provider,
        "label": spec.label if spec else provider,
        "console_url": spec.console_url if spec else None,
        "docs_url": spec.docs_url if spec else None,
        "key_present": bool(row.get("encrypted_api_key")),
        "key_hint": row.get("key_hint") or "",
        "model_id": row.get("model_id"),
        "temperature": row.get("temperature"),
        "max_tokens": row.get("max_tokens"),
        "system_prompt": row.get("system_prompt"),
        "priority": row.get("priority", 1),
        "enabled": row.get("enabled", True),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_for_user(db: SupabaseRest, *, user_id: str) -> list[dict[str, Any]]:
    """Every provider this user has configured, redacted for display."""
    rows = await db.select(
        "ai_provider_credentials", {"user_id": user_id}, order="priority.asc"
    )
    return [public_view(row) for row in rows]


async def load_credentials(
    db: SupabaseRest, settings: Settings, *, user_id: str
) -> list[ProviderCredential]:
    """Decrypted credentials, in the order they should be tried.

    A credential whose ciphertext will not decrypt is skipped, not raised on.
    That happens when the server's encryption key has been rotated without
    re-entering the provider keys, and the right behaviour is to fall through
    to the next provider and let the user re-save the broken one -- not to
    take the explanation feature down for everybody in that state.
    """
    rows = await db.select(
        "ai_provider_credentials", {"user_id": user_id, "enabled": "true"}, order="priority.asc"
    )

    credentials: list[ProviderCredential] = []
    for row in rows:
        provider = row.get("provider")
        if provider not in PROVIDER_KEYS:
            continue
        api_key = decrypt_secret(settings, row.get("encrypted_api_key") or "")
        if not api_key:
            logger.warning(
                "stored credential for provider %s could not be decrypted; skipping", provider
            )
            continue
        credentials.append(
            ProviderCredential(
                provider=provider,
                api_key=api_key,
                model_id=row.get("model_id"),
                temperature=_as_float(row.get("temperature")),
                max_tokens=_as_int(row.get("max_tokens")),
                system_prompt=row.get("system_prompt"),
                priority=int(row.get("priority") or 1),
            )
        )
    return credentials


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
