"""Keeping Aevrin's model catalogue current, without touching a customer's key.

The point of this job is that when Groq, Gemini, Anthropic or OpenAI adds,
changes or retires a model, Aevrin notices on its own. Nobody edits a hardcoded
list in the frontend, and nobody redeploys to make a new model selectable.

A correction worth stating plainly, because the brief assumed otherwise:
**every one of these four providers requires an API key to list models.** None
of them serve a model list anonymously. So "provider catalogue metadata is
public information that needs no credential" is not true in practice.

That leaves two options, and only one of them is acceptable. Using customers'
keys would bill them for Aevrin's bookkeeping and would leak which vendors
Aevrin is polling into their usage dashboards. So this job uses Aevrin's own
credentials, supplied by environment variable, and never reads
`ai_provider_credentials` at all.

When a provider has no catalogue credential configured, its models are simply
not refreshed. The previously synced catalogue keeps working, the admin page
shows the reason, and nothing is deleted. That is the fail-safe rule: a failed
sync must never leave a user with an empty model dropdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.ai_providers import (
    PROVIDER_KEYS,
    SPECS,
    ModelInfo,
    ProviderError,
    list_models,
)

logger = logging.getLogger("aevrin.ai.provider_sync")


def catalog_key(settings: Settings, provider: str) -> str | None:
    """Aevrin's own credential for one provider, if configured."""
    return {
        "groq": settings.groq_catalog_api_key,
        "openai": settings.openai_catalog_api_key,
        "anthropic": settings.anthropic_catalog_api_key,
        "gemini": settings.gemini_catalog_api_key,
    }.get(provider)


@dataclass
class ProviderSyncReport:
    provider: str
    ok: bool = False
    models_seen: int = 0
    added: int = 0
    updated: int = 0
    deprecated: int = 0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "models_seen": self.models_seen,
            "added": self.added,
            "updated": self.updated,
            "deprecated": self.deprecated,
            "error": self.error,
        }


@dataclass
class SyncAllReport:
    started_at: datetime
    providers: list[ProviderSyncReport] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "providers": [p.as_dict() for p in self.providers],
            "ok": any(p.ok for p in self.providers),
        }


async def sync_all_providers(db: SupabaseRest, settings: Settings) -> SyncAllReport:
    """Refresh every provider that has a catalogue credential.

    Providers are independent: one vendor being down or unconfigured has no
    effect on the others' catalogues.
    """
    report = SyncAllReport(started_at=datetime.now(UTC))
    logger.info("provider_update_started")
    for provider in PROVIDER_KEYS:
        report.providers.append(await sync_provider(db, settings, provider))
    logger.info("provider_update_completed")
    return report


async def sync_provider(
    db: SupabaseRest, settings: Settings, provider: str
) -> ProviderSyncReport:
    """One provider. Never raises, never deletes."""
    result = ProviderSyncReport(provider=provider)
    now = datetime.now(UTC).isoformat()

    api_key = catalog_key(settings, provider)
    if not api_key:
        result.error = (
            f"No catalogue credential configured for {SPECS[provider].label}. "
            "Set the corresponding *_CATALOG_API_KEY to enable automatic model discovery."
        )
        await _record_state(db, provider, attempted_at=now, error=result.error)
        return result

    try:
        models = await list_models(provider, api_key)
    except ProviderError as exc:
        result.error = str(exc)
        # Only the attempt timestamp and the error are written. The previous
        # successful sync time, and every model row it produced, are left
        # exactly as they are.
        await _record_state(db, provider, attempted_at=now, error=result.error)
        logger.warning("provider sync failed for %s: %s", provider, exc)
        return result
    except Exception:
        result.error = f"unexpected error contacting {SPECS[provider].label}"
        await _record_state(db, provider, attempted_at=now, error=result.error)
        logger.warning("provider sync crashed for %s", provider, exc_info=True)
        return result

    if not models:
        # An empty list from a successful call is treated as a failure, not as
        # "this provider has no models". Believing it would mark every model
        # deprecated and empty the dropdown on the strength of one odd
        # response.
        result.error = f"{SPECS[provider].label} returned an empty model list; keeping previous catalogue"
        await _record_state(db, provider, attempted_at=now, error=result.error)
        return result

    result.models_seen = len(models)
    existing = {
        row["model_id"]: row
        for row in await db.select("ai_provider_models", {"provider": provider}, limit=1000)
    }
    seen_ids: set[str] = set()

    for model in models:
        seen_ids.add(model.model_id)
        previous = existing.get(model.model_id)
        if previous is None:
            await _insert_model(db, provider, model, now)
            await _record_change(db, provider, model.model_id, "added", new_value=model.display_name)
            result.added += 1
        elif _has_changed(previous, model):
            await _update_model(db, provider, model, now)
            await _record_change(
                db,
                provider,
                model.model_id,
                "updated",
                old_value=previous.get("display_name"),
                new_value=model.display_name,
            )
            result.updated += 1
        else:
            # Unchanged, but seen: refresh the timestamp so the admin page can
            # distinguish "still offered" from "last seen three months ago".
            await db.update(
                "ai_provider_models",
                {"provider": provider, "model_id": model.model_id},
                {"last_checked_at": now, "status": "deprecated" if model.deprecated else "active"},
            )

    # Anything previously known and no longer offered is marked, never
    # deleted. ai_explanations rows reference the model that produced them,
    # and that reference has to keep resolving after the model is gone.
    for model_id, row in existing.items():
        if model_id in seen_ids or row.get("status") == "unavailable":
            continue
        await db.update(
            "ai_provider_models",
            {"provider": provider, "model_id": model_id},
            {"status": "unavailable", "last_checked_at": now},
        )
        await _record_change(db, provider, model_id, "unavailable", old_value=row.get("status"))
        result.deprecated += 1

    result.ok = True
    await _record_state(
        db, provider, attempted_at=now, succeeded_at=now, model_count=len(models)
    )
    return result


def _has_changed(previous: dict[str, Any], model: ModelInfo) -> bool:
    expected_status = "deprecated" if model.deprecated else "active"
    return (
        previous.get("display_name") != model.display_name
        or previous.get("context_window") != model.context_window
        or previous.get("max_output_tokens") != model.max_output_tokens
        or previous.get("status") != expected_status
    )


async def _insert_model(
    db: SupabaseRest, provider: str, model: ModelInfo, now: str
) -> None:
    await db.insert(
        "ai_provider_models",
        {
            "provider": provider,
            "model_id": model.model_id,
            "display_name": model.display_name,
            "status": "deprecated" if model.deprecated else "active",
            "context_window": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "capabilities": model.capabilities,
            "documentation_url": SPECS[provider].docs_url,
            "from_provider_api": True,
            "last_checked_at": now,
        },
        upsert_on="provider,model_id",
    )


async def _update_model(
    db: SupabaseRest, provider: str, model: ModelInfo, now: str
) -> None:
    await db.update(
        "ai_provider_models",
        {"provider": provider, "model_id": model.model_id},
        {
            "display_name": model.display_name,
            "status": "deprecated" if model.deprecated else "active",
            "context_window": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "capabilities": model.capabilities,
            "from_provider_api": True,
            "last_checked_at": now,
        },
    )


async def _record_state(
    db: SupabaseRest,
    provider: str,
    *,
    attempted_at: str,
    succeeded_at: str | None = None,
    error: str | None = None,
    model_count: int | None = None,
) -> None:
    """Update the per-provider sync state.

    Built as a partial patch on purpose: on failure only `last_attempted_sync`
    and `sync_error` are set, so `last_successful_sync` keeps pointing at the
    last time this genuinely worked.
    """
    patch: dict[str, Any] = {
        "provider": provider,
        "last_attempted_sync": attempted_at,
        "sync_error": error,
        "updated_at": attempted_at,
    }
    if succeeded_at:
        patch["last_successful_sync"] = succeeded_at
    if model_count is not None:
        patch["model_count"] = model_count
    try:
        await db.insert("ai_provider_sync_state", patch, upsert_on="provider")
    except Exception:
        logger.warning("could not record sync state for %s", provider, exc_info=True)


async def _record_change(
    db: SupabaseRest,
    provider: str,
    model_id: str,
    change_type: str,
    *,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    try:
        await db.insert(
            "ai_provider_model_changes",
            {
                "provider": provider,
                "model_id": model_id,
                "change_type": change_type,
                "old_value": old_value,
                "new_value": new_value,
                "source": "provider_api",
            },
        )
    except Exception:
        logger.debug("could not record model change", exc_info=True)


async def list_catalog(
    db: SupabaseRest, *, provider: str | None = None, include_retired: bool = False
) -> list[dict[str, Any]]:
    """The models a dashboard may offer.

    Deprecated and unavailable models are excluded by default. A deprecated
    model is not a normal choice: offering it in a plain dropdown invites
    someone to select something that will stop working, and the failure would
    arrive later, at the moment they actually needed an explanation.
    """
    filters: dict[str, str] = {}
    if provider:
        filters["provider"] = f"eq.{provider}"
    if not include_retired:
        filters["status"] = "eq.active"
    return await db.select(
        "ai_provider_models", filters, order="provider.asc,display_name.asc", limit=1000
    )


async def provider_status(db: SupabaseRest, settings: Settings) -> list[dict[str, Any]]:
    """What the admin panel shows: one row per provider, healthy or not."""
    states = {
        row["provider"]: row
        for row in await db.select("ai_provider_sync_state", limit=20)
    }
    models = await db.select("ai_provider_models", columns="provider,status", limit=1000)

    counts: dict[str, int] = {}
    for row in models:
        if row.get("status") == "active":
            counts[row["provider"]] = counts.get(row["provider"], 0) + 1

    result = []
    for provider in PROVIDER_KEYS:
        state = states.get(provider, {})
        spec = SPECS[provider]
        configured = bool(catalog_key(settings, provider))
        result.append({
            "provider": provider,
            "label": spec.label,
            "console_url": spec.console_url,
            "docs_url": spec.docs_url,
            "catalog_credential_configured": configured,
            "active_models": counts.get(provider, 0),
            "last_successful_sync": state.get("last_successful_sync"),
            "last_attempted_sync": state.get("last_attempted_sync"),
            "sync_error": state.get("sync_error"),
            # "Healthy" means the catalogue is usable, which is not the same
            # as "the last sync worked". A provider whose refresh failed today
            # but has models from last week is still perfectly serviceable.
            "healthy": counts.get(provider, 0) > 0 and not state.get("sync_error"),
        })
    return result


async def recent_changes(db: SupabaseRest, *, limit: int = 50) -> list[dict[str, Any]]:
    return await db.select(
        "ai_provider_model_changes", order="created_at.desc", limit=min(limit, 200)
    )
