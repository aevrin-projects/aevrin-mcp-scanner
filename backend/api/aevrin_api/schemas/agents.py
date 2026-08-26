"""Agent posture: upload and read models.

The uploaded document is scanner-core's `DiscoveredAgent` verbatim. Re-declaring
it here would create a second definition of the same contract that could drift
from the one the CLI actually produces, and the point of a versioned snapshot
is that there is exactly one shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from aevrin_scanner_core.agents.models import AgentKind, ConfigScope, DiscoveredAgent
from pydantic import BaseModel, Field


class AgentSnapshotUpload(BaseModel):
    # Absent when the platform's machine id could not be read; the API then
    # derives a stable id from the hostname instead, so a device without one
    # still has a single row rather than a new row per upload.
    device_id: str | None = None
    agents: list[DiscoveredAgent] = Field(min_length=1, max_length=16)


class AgentSnapshotUploadResponse(BaseModel):
    stored: int


class PolicyOutcomeOut(BaseModel):
    decision: str
    reasons: list[str]


class PostureFactorOut(BaseModel):
    points: int
    reason: str


class AgentSummaryOut(BaseModel):
    id: UUID
    agent_type: AgentKind
    agent_name: str
    agent_version: str | None
    device_id: str
    hostname: str
    platform: str | None
    reported_at: datetime
    # Distinct from the MCP scan score and the MCP trust grade, and kept that
    # way: this one answers how much the agent can already do here.
    posture_score: int
    risk: str
    confidence: str
    risk_factors: list[PostureFactorOut]
    mcp_server_count: int
    skill_count: int
    plugin_count: int
    hook_count: int
    coverage_complete: bool
    policy: PolicyOutcomeOut | None = None


class AgentDetailOut(AgentSummaryOut):
    snapshot: DiscoveredAgent


class GradeFactorOut(BaseModel):
    points: int
    reason: str


class McpTrustOut(BaseModel):
    """The Aevrin trust grade for one MCP server, from a scan that actually ran.

    Absent when no scan of that exact target exists. A grade is a claim about
    evidence, so inventing one from configuration alone would be the one thing
    a security product cannot do.
    """

    scan_id: UUID
    scanned_at: datetime
    scan_score: int | None
    grade: str
    label: str
    recommended_action: str
    factors: list[GradeFactorOut]


class McpInstallationOut(BaseModel):
    """One place a server is configured: one agent, on one device, at one scope.

    The unit of "where is this installed", which is what someone needs in
    order to change it. The same server configured globally and in a project
    is two installations with two different answers to who can reach it.
    """

    agent_id: UUID
    agent_type: AgentKind
    agent_name: str
    device_id: str
    hostname: str
    name: str
    scope: ConfigScope
    project_root: str | None
    source_path: str
    transport: str
    command: str | None
    url: str | None
    enabled: bool
    auto_approved: bool
    reported_at: datetime


class McpAssetOut(BaseModel):
    """One MCP server, however many places it is configured.

    Correlated on what the configuration actually pins down -- a URL, or the
    package a launcher fetches. `identity_confidence` is carried through
    rather than resolved: merging two unrelated servers would attach one
    server's findings to another, which is worse than listing one twice.
    """

    identity_key: str
    identity_kind: str
    identity_label: str
    identity_confidence: str
    name: str
    transport: str
    url: str | None
    command: str | None
    installation_count: int
    device_count: int
    agent_count: int
    project_count: int
    scopes: list[ConfigScope]
    enabled_everywhere: bool
    installations: list[McpInstallationOut]
    trust: McpTrustOut | None = None
    policy: PolicyOutcomeOut | None = None


class SkillOut(BaseModel):
    """One skill, on one agent, on one device.

    Not correlated the way MCP servers are: a skill is a folder of prose on a
    machine, with no URL or package to pin it to, so two skills sharing a name
    are not evidence of being the same skill.
    """

    name: str
    description: str | None
    scope: ConfigScope
    source_path: str
    agent_id: UUID
    agent_type: AgentKind
    hostname: str


class PermissionOut(BaseModel):
    """One vendor rule exactly as written, with where it came from.

    The normalised capability is what the product reasons about; this is what
    the person actually typed, and what they would edit to change it.
    """

    rule: str
    effect: str
    scope: ConfigScope
    source_path: str
    agent_id: UUID
    agent_type: AgentKind
    hostname: str


class AttackStepOut(BaseModel):
    label: str
    detail: str
    evidence: list[str]


class AttackPathOut(BaseModel):
    """A path with evidence behind every step, or it is not here at all.

    An agent that *might* reach a cloud that *might* reach production is three
    maybes chained together: it looks like a finding, is not one, and teaches
    people to ignore the product.
    """

    key: str
    title: str
    source: str
    target: str
    severity: str
    confidence: str
    steps: list[AttackStepOut]
    remediation: str
    agent_id: UUID
    agent_type: AgentKind
    hostname: str


class PoliciesOut(BaseModel):
    """Four switches, all off until someone turns them on."""

    block_grade_d: bool = False
    require_approval_grade_c: bool = False
    block_unattended_shell: bool = False
    block_unrestricted_network: bool = False


class PoliciesUpdate(PoliciesOut):
    """Every field is required on update, so a partial body cannot silently
    switch a policy off that the caller never mentioned."""


class PolicyAuditOut(BaseModel):
    id: int
    actor: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime
