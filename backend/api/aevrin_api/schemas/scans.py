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


class RiskSummaryOut(BaseModel):
    """The five questions a scan report has to answer, in order.

    Computed by scanner-core's one grader rather than reassembled here or in
    the client: there is a single place that turns findings into a verdict,
    and every surface reads its output.
    """

    headline: str
    explanation: str
    potential_impact: str
    recommended_action: str
    suggested_policy: str


class ScanOut(BaseModel):
    id: UUID
    target_type: str
    target: str
    status: str
    source: str = "dashboard"
    # 0-100, higher is worse. See mcp/risk.py: this replaced a score that
    # counted down from 100 and meant the opposite thing.
    risk_score: int | None = None
    # "A".."F", or null when coverage was incomplete. Null is a state the UI
    # must render - "not graded" - not a missing field to hide.
    grade: str | None = None
    error: str | None = None
    mcp_detected: bool | None = None
    # How confidently mcp_detected was established, and the evidence lines
    # behind it - "high"/"medium"/"low"/"none", null where MCP-ness is by
    # construction (live_mcp_server, config_paste targets never set these).
    # Tool names read out of the repository's own registration sites. Empty
    # means none found, not "this server exposes nothing" - see
    # docs/features/MCP_SCANNING.md.
    mcp_tools_declared: list[str] = Field(default_factory=list)
    # mcp.tools.capability_summary() over the discovered tools - the declared
    # surface, not observed behavior. Null (not a dict of all-false) when
    # tool discovery never ran for this target, same reasoning as
    unreliable_stages: list[str] = Field(default_factory=list)
    # Set when AI review covered only part of the findings, so a capped scan
    # never reads as fully reviewed.
    triage_note: str | None = None
    # Populated only by the single-scan endpoint, which loads the findings it
    # is derived from. Null in list responses because computing it there
    # would mean loading every finding of every scan to render a table.
    risk_summary: RiskSummaryOut | None = None
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
    # The rule that produced this, e.g. "AS-006".
    rule_id: str | None = None
    # "Why this matters", looked up from the rule catalogue at serialization
    # time rather than stored per finding. One place owns the prose, so
    # rewording a rule never requires rewriting stored rows - and the
    # frontend never needs its own copy of the catalogue.
    impact: str | None = None
    # The specific facts that made the rule fire. A finding with no evidence
    # is an assertion, and this product does not ship assertions.
    evidence: list[str] = Field(default_factory=list)
    # Every declared MCP tool this finding applies to; more than one once
    # identical rule verdicts have been folded into a single card.
    affected_tools: list[str] = Field(default_factory=list)
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
    # The normalized capability vocabulary term this finding is about
    # (adapters/mcp_behavior.py). Null for every other tool.
    remediation: str
    triage_status: str
    triage_reason: str | None = None
    triaged_at: datetime | None = None
    created_at: datetime
    # Deterministic accuracy layer (addendum §1): always present, every tier.
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
