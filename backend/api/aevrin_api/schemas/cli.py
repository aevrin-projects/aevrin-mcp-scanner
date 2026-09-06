"""The `aevrin scan --upload` payload."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CliUploadFinding(BaseModel):
    id: UUID
    tool: str
    owasp_category: str
    severity: str
    title: str
    description: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    manifest_field: str | None = None
    tool_name_in_manifest: str | None = None
    remediation: str
    raw: dict[str, Any] | None = None
    created_at: datetime | None = None


class CliUploadStage(BaseModel):
    name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class CliUploadRequest(BaseModel):
    scan_id: UUID | None = None
    target_type: str
    target: str = Field(min_length=1, max_length=8000)
    # 0-100, higher is worse. Client-reported: the engine produced it on the
    # machine that ran the scan, and the API cannot re-derive it without
    # launching the server itself. Checked for self-consistency, not recomputed.
    risk_score: int | None = None
    # "A".."F", or null for an incomplete scan. Client-reported, and refused
    # when it contradicts the findings uploaded alongside it.
    grade: str | None = None
    status: str = "completed"
    created_at: datetime | None = None
    completed_at: datetime | None = None
    mcp_detected: bool | None = None
    mcp_tools_declared: list[str] = Field(default_factory=list)
    unreliable_stages: list[str] = Field(default_factory=list)
    stages: list[CliUploadStage] = Field(default_factory=list)
    findings: list[CliUploadFinding]

    @field_validator("target_type")
    @classmethod
    def _valid_cli_target_type(cls, v: str) -> str:
        allowed = {"github_repo", "live_mcp_server", "local_path"}
        if v not in allowed:
            raise ValueError(f"target_type must be one of {sorted(allowed)}")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        allowed = {"completed", "incomplete", "failed"}
        if v not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v
