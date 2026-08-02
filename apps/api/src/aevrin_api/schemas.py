from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateScanRequest(BaseModel):
    target_type: str
    target: str

    @field_validator("target_type")
    @classmethod
    def _valid_target_type(cls, v: str) -> str:
        allowed = {"github_repo", "live_mcp_server", "config_paste"}
        if v not in allowed:
            raise ValueError(f"target_type must be one of {sorted(allowed)}")
        return v

    @field_validator("target")
    @classmethod
    def _non_empty_target(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("target must not be empty")
        if len(v) > 8000:
            raise ValueError("target too long")
        return v


class ScanOut(BaseModel):
    id: UUID
    target_type: str
    target: str
    status: str
    score: int | None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ScanStageOut(BaseModel):
    name: str
    status: str
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FindingOut(BaseModel):
    id: UUID
    scan_id: UUID
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
    verified: bool | None = None
    not_tested: bool
    triage_status: str
    created_at: datetime


class TriageRequest(BaseModel):
    triage_status: str

    @field_validator("triage_status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        allowed = {"open", "fixed", "false_positive"}
        if v not in allowed:
            raise ValueError(f"triage_status must be one of {sorted(allowed)}")
        return v


class HookCacheResponse(BaseModel):
    decision: str  # "allow_clean" | "block" | "allow_unscanned"
    score: int | None = None
    scan_id: UUID | None = None
    checked_at: datetime | None = None
    findings_summary: list[dict[str, Any]] = Field(default_factory=list)


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
    verified: bool | None = None
    not_tested: bool = False
    raw: dict[str, Any] | None = None


class CliUploadRequest(BaseModel):
    target_type: str
    target: str
    score: int
    findings: list[CliUploadFinding]
