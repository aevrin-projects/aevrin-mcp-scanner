"""CLI API keys."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreateRequest(BaseModel):
    name: str = "CLI key"


class ApiKeyCreatedResponse(BaseModel):
    id: int
    name: str
    plaintext_key: str  # shown exactly once


class ApiKeyOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
