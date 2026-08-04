from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from aevrin_scanner_core.network_safety import public_https_url_error
from pydantic import BaseModel, Field, field_validator, model_validator


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

    @model_validator(mode="after")
    def _safe_live_target(self) -> CreateScanRequest:
        if self.target_type == "live_mcp_server":
            error = public_https_url_error(self.target, resolve_dns=False)
            if error:
                raise ValueError(error)
        return self


class ScanOut(BaseModel):
    id: UUID
    target_type: str
    target: str
    status: str
    source: str = "dashboard"
    score: int | None
    error: str | None = None
    mcp_detected: bool | None = None
    unreliable_stages: list[str] = Field(default_factory=list)
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
    triage_reason: str | None = None
    triaged_at: datetime | None = None
    created_at: datetime
    # Deterministic accuracy layer (addendum §1) — always present, every tier.
    excluded_path: bool = False
    confidence: str | None = None
    original_severity: str | None = None
    epss_score: float | None = None
    in_kev: bool = False
    dependency_scope: str | None = None
    corroborated_by: list[str] = Field(default_factory=list)
    occurrence_count: int = 1
    additional_locations: list[dict[str, Any]] = Field(default_factory=list)
    # LLM triage layer (addendum §2) — paid tiers only, None when not run.
    llm_classification: str | None = None
    llm_severity: str | None = None
    llm_reasoning: str | None = None
    llm_remediation: str | None = None
    llm_model: str | None = None
    llm_triaged_at: datetime | None = None
    # Auto-fix lifecycle (V5 prompt §7) — Pro/Team only, "none" everywhere else.
    autofix_status: str = "none"
    autofix_pr_url: str | None = None
    autofix_failure_reason: str | None = None


class TriageRequest(BaseModel):
    triage_status: str
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("triage_status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        allowed = {"open", "fixed", "false_positive"}
        if v not in allowed:
            raise ValueError(f"triage_status must be one of {sorted(allowed)}")
        return v

    @model_validator(mode="after")
    def _false_positive_requires_reason(self) -> TriageRequest:
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        if self.triage_status == "false_positive" and not self.reason:
            raise ValueError("reason is required when reporting a false positive")
        return self


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
    score: int | None
    status: str = "completed"
    created_at: datetime | None = None
    completed_at: datetime | None = None
    mcp_detected: bool | None = None
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


class UsageActivityOut(BaseModel):
    id: UUID
    source: str
    target_type: str
    target: str
    status: str
    score: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AccountUsageResponse(BaseModel):
    tier: str
    paid_until: datetime | None = None
    buckets: list[BucketUsageOut]
    activity: list[UsageActivityOut]


class CheckoutRequest(BaseModel):
    tier: str
    cycle: str
    seats: int = 1
    byok: bool = False

    @field_validator("tier")
    @classmethod
    def _valid_tier(cls, v: str) -> str:
        if v not in {"hobby", "pro", "team"}:
            raise ValueError("tier must be one of ['hobby', 'pro', 'team']")
        return v

    @field_validator("cycle")
    @classmethod
    def _valid_cycle(cls, v: str) -> str:
        if v not in {"monthly", "annual"}:
            raise ValueError("cycle must be one of ['monthly', 'annual']")
        return v

    @model_validator(mode="after")
    def _valid_seats(self) -> CheckoutRequest:
        # 3-seat minimum on Team (addendum §5: "do not allow a Team
        # subscription to be created below 3 seats"); every other tier is
        # single-seat — seats is a Team-only billing quantity, not a
        # multi-user access model these tiers otherwise share.
        if self.tier == "team":
            if self.seats < 3:
                raise ValueError("Team requires a minimum of 3 seats")
        elif self.seats != 1:
            raise ValueError(f"{self.tier} does not support multiple seats")
        return self


class CheckoutResponse(BaseModel):
    order_id: str
    amount_paise: int
    currency: str
    razorpay_key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    status: str
    tier: str
    paid_until: datetime


class SubscriptionResponse(BaseModel):
    tier: str
    effective_tier: str
    paid_until: datetime | None = None


class AccountLookupResponse(BaseModel):
    exists: bool
    providers: list[str]
    has_password: bool


class ByokStatusResponse(BaseModel):
    enabled: bool  # whether the account has purchased the BYOK add-on
    provider: str | None = None
    has_key: bool  # whether a key has actually been saved yet


class ByokKeyRequest(BaseModel):
    provider: str
    api_key: str = Field(min_length=8, max_length=500)

    @field_validator("provider")
    @classmethod
    def _valid_provider(cls, v: str) -> str:
        if v not in {"anthropic", "google"}:
            raise ValueError("provider must be one of ['anthropic', 'google']")
        return v


class GithubStatusResponse(BaseModel):
    connected: bool
    account_login: str | None = None


class GithubInstallUrlResponse(BaseModel):
    url: str


class AutofixResponse(BaseModel):
    status: str  # "fixed" | "failed" | "needs_github_connection"
    pr_url: str | None = None
    failure_reason: str | None = None
    install_url: str | None = None
