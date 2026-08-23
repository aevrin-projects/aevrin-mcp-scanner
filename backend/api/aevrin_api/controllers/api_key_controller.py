"""API key issue, list and revoke. Plaintext is returned exactly once, at
creation; only the peppered hash is ever stored."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.core.security import generate_api_key
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeyOut


async def create_api_key(
    body: ApiKeyCreateRequest, user_id: str, db: SupabaseRest, settings: Settings
) -> ApiKeyCreatedResponse:
    plaintext, hashed = generate_api_key(settings.api_key_pepper)
    rows = await db.insert("api_keys", {"user_id": user_id, "name": body.name, "hashed_key": hashed})
    return ApiKeyCreatedResponse(id=rows[0]["id"], name=rows[0]["name"], plaintext_key=plaintext)


async def list_api_keys(user_id: str, db: SupabaseRest) -> list[ApiKeyOut]:
    rows = await db.select("api_keys", {"user_id": user_id}, order="created_at.desc")
    return [ApiKeyOut(**r) for r in rows]


async def revoke_api_key(key_id: int, user_id: str, db: SupabaseRest) -> None:
    existing = await db.select("api_keys", {"id": str(key_id), "user_id": user_id})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await db.update(
        "api_keys",
        {"id": str(key_id), "user_id": user_id},
        {"revoked_at": datetime.now(UTC).isoformat()},
    )
