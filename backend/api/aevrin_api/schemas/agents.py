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


class McpServerInventoryOut(BaseModel):
    """One MCP server as configured for one agent on one device.

    Keyed by where it is configured, not by name: the same server present
    globally and in a project is two installations with two different
    answers to "who can reach this", and collapsing them hides that.
    """

    name: str
    scope: ConfigScope
    transport: str
    command: str | None
    url: str | None
    auto_approved: bool
    source_path: str
    project_root: str | None
    agent_id: UUID
    agent_type: AgentKind
    agent_name: str
    hostname: str
    reported_at: datetime
