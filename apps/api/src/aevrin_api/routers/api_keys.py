from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import get_current_user, get_db
from ..schemas import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeyOut
from ..security import AuthenticatedUser, generate_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreateRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiKeyCreatedResponse:
    plaintext, hashed = generate_api_key(settings.api_key_pepper)
    rows = await db.insert(
        "api_keys", {"user_id": user.id, "name": body.name, "hashed_key": hashed}
    )
    return ApiKeyCreatedResponse(id=rows[0]["id"], name=rows[0]["name"], plaintext_key=plaintext)


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> list[ApiKeyOut]:
    rows = await db.select("api_keys", {"user_id": user.id}, order="created_at.desc")
    return [ApiKeyOut(**r) for r in rows]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> None:
    existing = await db.select("api_keys", {"id": str(key_id), "user_id": user.id})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await db.update(
        "api_keys", {"id": str(key_id)}, {"revoked_at": datetime.now(UTC).isoformat()}
    )
