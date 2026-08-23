"""Claude Code PreToolUse hook: cache lookups and install-anyway overrides."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from aevrin_scanner_core.execution.network_safety import public_https_url_error
from pydantic import BaseModel, Field, model_validator


class HookCacheResponse(BaseModel):
    decision: str  # "allow_clean" | "block" | "block_incomplete" | "allow_override" | "allow_unscanned" | "quota_exceeded"
    score: int | None = None
    scan_id: UUID | None = None
    checked_at: datetime | None = None
    findings_summary: list[dict[str, Any]] = Field(default_factory=list)
    quota_resets_at: datetime | None = None
    upgrade_url: str | None = None
    target_key: str | None = None
    autofix_hint: str | None = None


class HookCacheRequest(BaseModel):
    target: str = Field(min_length=1, max_length=8000)
    target_type: Literal["github_repo", "live_mcp_server", "config_paste"] = "github_repo"

    @model_validator(mode="after")
    def _safe_live_target(self) -> HookCacheRequest:
        if self.target_type == "live_mcp_server":
            error = public_https_url_error(self.target, resolve_dns=False)
            if error:
                raise ValueError(error)
        return self


class HookOverrideRequest(BaseModel):
    target: str = Field(min_length=1, max_length=8000)


class HookOverrideResponse(BaseModel):
    expires_at: datetime
