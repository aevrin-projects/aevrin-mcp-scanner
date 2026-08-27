"""AI provider settings and explanation endpoints.

Nothing in this file returns an API key. The response models in schemas/ai.py
have no field that could carry one, which is a stronger guarantee than
remembering to strip it in each handler.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import ai_controller as ctl
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import enforce_rate_limit, get_current_user, get_db
from aevrin_api.schemas.ai import (
    ModelOut,
    ProviderCredentialOut,
    SaveProviderRequest,
    UpdateProviderRequest,
)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/providers", response_model=list[ProviderCredentialOut])
async def list_providers(
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Your configured AI providers.

    Reports whether a key is present and its last four characters. The key
    itself is never returned, on this endpoint or any other.
    """
    return await ctl.list_providers(db, user_id=user.id)


@router.put("/providers", response_model=ProviderCredentialOut)
async def save_provider(
    body: SaveProviderRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Add or rotate a provider API key.

    The key is encrypted at rest before it is stored, and the response carries
    only a masked hint of it.
    """
    return await ctl.save_provider(db, settings, user_id=user.id, body=body)


@router.patch("/providers/{provider}", response_model=ProviderCredentialOut)
async def update_provider(
    provider: str,
    body: UpdateProviderRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Change the model or generation settings for a provider, without
    touching its key."""
    return await ctl.update_provider(db, user_id=user.id, provider=provider, body=body)


@router.delete("/providers/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider: str,
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> None:
    """Remove a provider and its stored key."""
    await ctl.delete_provider(db, user_id=user.id, provider=provider)


@router.get("/models", response_model=list[ModelOut])
async def list_models(
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    provider: Annotated[str | None, Query(max_length=20)] = None,
) -> Any:
    """Currently available models, from Aevrin's own synced catalogue.

    Deprecated and withdrawn models are excluded, so a dropdown cannot offer a
    choice that will fail later at the moment somebody actually needs it.
    """
    return await ctl.list_models(db, provider=provider)


@router.post("/explain")
async def explain(
    body: Any,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Explain a finding, grade, or scan in plain language.

    Returns 200 with `available: false` and a reason when no provider could
    answer. An AI outage does not invalidate the security result being
    explained, so it is not reported as a request failure.

    The explanation is generated from structured evidence only. It cannot
    introduce a vulnerability that the scanners did not find, and it never
    changes a score, a grade, or a finding.
    """
    from aevrin_api.schemas.ai import ExplainRequest

    parsed = ExplainRequest.model_validate(body)
    if parsed.refresh:
        # Only the cache-bypassing path is limited. A cached read costs
        # nothing and should never be throttled.
        enforce_rate_limit(
            settings,
            "ai_explain_refresh",
            user.id,
            limit=30,
            detail="Too many fresh AI explanations requested. Try again shortly.",
        )
    return await ctl.explain_subject(db, settings, user_id=user.id, body=parsed)
