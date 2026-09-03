"""Scan lifecycle: creating a scan and reading back its stages and findings."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from aevrin_scanner_core.execution.network_safety import public_https_url_error
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
    # How confidently mcp_detected was established, and the evidence lines
    # behind it - "high"/"medium"/"low"/"none", null where MCP-ness is by
    # construction (live_mcp_server, config_paste targets never set these).
    mcp_detection_confidence: str | None = None
    mcp_detection_evidence: list[str] = Field(default_factory=list)
    # Tool names read out of the repository's own registration sites. Empty
    # means none found, not "this server exposes nothing" - see
    # docs/features/MCP_SCANNING.md.
    mcp_tools_declared: list[str] = Field(default_factory=list)
    mcp_components: list[dict[str, Any]] = Field(default_factory=list)
    # capability_summary() over mcp_tools_declared's own tools - the declared
    # surface, not observed behavior. Null (not a dict of all-false) when
    # tool discovery never ran for this target, same reasoning as
    # mcp_detection_confidence above.
    mcp_capabilities: dict[str, bool] | None = None
    unreliable_stages: list[str] = Field(default_factory=list)
    # Set when AI review covered only part of the findings, so a capped scan
    # never reads as fully reviewed.
    triage_note: str | None = None
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
    # Which declared MCP tool this finding's sink was found inside
    # (analysis.capability_map). Null when not applicable or not
    # established - never a guess at the nearest tool.
    mcp_tool: str | None = None
    # The normalized capability vocabulary term this finding is about
    # (adapters/mcp_behavior.py). Null for every other tool.
    capability: str | None = None
    remediation: str
    verified: bool | None = None
    not_tested: bool
    triage_status: str
    triage_reason: str | None = None
    triaged_at: datetime | None = None
    created_at: datetime
    # Deterministic accuracy layer (addendum §1): always present, every tier.
    excluded_path: bool = False
    confidence: str | None = None
    original_severity: str | None = None
    epss_score: float | None = None
    in_kev: bool = False
    dependency_scope: str | None = None
    corroborated_by: list[str] = Field(default_factory=list)
    occurrence_count: int = 1
    additional_locations: list[dict[str, Any]] = Field(default_factory=list)
    # AI review layer (addendum §2): runs on every tier, None when not run.
    # `llm_model` is stored on the row for auditability (knowing which model
    # produced a verdict matters when investigating a bad one) but is
    # deliberately not exposed here: which vendor sits behind the review is
    # an implementation detail, not part of the product's contract.
    llm_classification: str | None = None
    llm_severity: str | None = None
    llm_reasoning: str | None = None
    llm_remediation: str | None = None
    llm_triaged_at: datetime | None = None


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
