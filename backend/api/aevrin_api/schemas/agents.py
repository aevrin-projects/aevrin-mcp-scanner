"""Agent posture: upload and read models.

The uploaded document is scanner-core's `DiscoveredAgent` verbatim. Re-declaring
it here would create a second definition of the same contract that could drift
from the one the CLI actually produces, and the point of a versioned snapshot
is that there is exactly one shape.
"""

from __future__ import annotations

from datetime import datetime
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


class AgentSummaryOut(BaseModel):
    id: UUID
    agent_type: AgentKind
    agent_name: str
    agent_version: str | None
    device_id: str
    hostname: str
    platform: str | None
    reported_at: datetime
    risk: str
    risk_reasons: list[str]
    mcp_server_count: int
    skill_count: int
    plugin_count: int
    hook_count: int
    coverage_complete: bool


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
