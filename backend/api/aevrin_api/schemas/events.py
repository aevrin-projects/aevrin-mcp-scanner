from __future__ import annotations

from pydantic import BaseModel, Field


class PageViewIn(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    referrer: str | None = Field(default=None, max_length=512)
    country: str | None = Field(default=None, max_length=8)
