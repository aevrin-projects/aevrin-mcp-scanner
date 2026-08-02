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
    decision: str  # "allow_clean" | "block" | "allow_unscanned" | "quota_exceeded"
    score: int | None = None
    scan_id: UUID | None = None
    checked_at: datetime | None = None
    findings_summary: list[dict[str, Any]] = Field(default_factory=list)
    quota_resets_at: datetime | None = None
    upgrade_url: str | None = None


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


class DeviceCodeRequest(BaseModel):
    client_kind: str
    machine_id_hash: str | None = None

    @field_validator("client_kind")
    @classmethod
    def _valid_client_kind(cls, v: str) -> str:
        if v not in {"cli", "hook"}:
            raise ValueError("client_kind must be one of ['cli', 'hook']")
        return v


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DeviceTokenRequest(BaseModel):
    device_code: str


class DeviceTokenResponse(BaseModel):
    # RFC 8628 §3.5 error codes when not yet approved; on success, api_key is set.
    status: str  # "authorization_pending" | "slow_down" | "expired_token" | "access_denied" | "approved"
    api_key: str | None = None


class DeviceApproveRequest(BaseModel):
    user_code: str
    fingerprint: str | None = None


class BucketUsageOut(BaseModel):
    bucket: str
    used: int
    limit: int | None
    resets_at: datetime


class AccountUsageResponse(BaseModel):
    tier: str
    buckets: list[BucketUsageOut]


class CheckoutRequest(BaseModel):
    tier: str
    cycle: str

    @field_validator("tier")
    @classmethod
    def _valid_tier(cls, v: str) -> str:
        if v not in {"hobby", "team"}:
            raise ValueError("tier must be one of ['hobby', 'team']")
        return v

    @field_validator("cycle")
    @classmethod
    def _valid_cycle(cls, v: str) -> str:
        if v not in {"monthly", "annual"}:
            raise ValueError("cycle must be one of ['monthly', 'annual']")
        return v


class CheckoutResponse(BaseModel):
    subscription_id: str
    razorpay_key_id: str


class SubscriptionResponse(BaseModel):
    tier: str
    subscription_status: str | None
    razorpay_subscription_id: str | None
    downgrade_effective_at: datetime | None = None
