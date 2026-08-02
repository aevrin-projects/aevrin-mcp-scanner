"""Shared data model for a scan and its findings.

Every surface (backend API, CLI, hook) constructs and reads these same
Pydantic models so a finding described on the website reads identically in
the CLI and in a hook block message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .owasp import OwaspMcpCategory


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ToolName(str, Enum):
    SEMGREP = "semgrep"
    BANDIT = "bandit"
    GITLEAKS = "gitleaks"
    TRUFFLEHOG = "trufflehog"
    OSV_SCANNER = "osv-scanner"
    TRIVY = "trivy"
    OPENSSF_SCORECARD = "openssf-scorecard"
    MCP_SHIELD = "mcp-shield"
    MCP_SCAN = "mcp-scan"
    MCP_CONTEXT_PROTECTOR = "mcp-context-protector"
    AEVRIN_MANIFEST_RULES = "aevrin-manifest-rules"  # our own rule-lookup checks, not a model


class TargetType(str, Enum):
    GITHUB_REPO = "github_repo"
    LIVE_MCP_SERVER = "live_mcp_server"
    CONFIG_PASTE = "config_paste"
    LOCAL_PATH = "local_path"  # CLI-only — website Screen 1 doesn't expose this mode


class ScanStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageName(str, Enum):
    """Exact stage list and order from Section 6, Screen 2."""

    CLONING = "cloning"
    STATIC_ANALYSIS = "static_analysis"
    SECRETS = "secrets"
    DEPENDENCIES = "dependencies"
    TOOL_DESCRIPTION_CHECK = "tool_description_check"
    AGGREGATING = "aggregating"


STAGE_LABELS: dict[StageName, str] = {
    StageName.CLONING: "Cloning",
    StageName.STATIC_ANALYSIS: "Static analysis",
    StageName.SECRETS: "Secrets",
    StageName.DEPENDENCIES: "Dependencies",
    StageName.TOOL_DESCRIPTION_CHECK: "Tool description check",
    StageName.AGGREGATING: "Aggregating",
}

# Which tools run within which stage, in execution order. Used by the runner
# to drive stage transitions and by the frontend/CLI to render consistent
# stage->tool grouping.
STAGE_TOOLS: dict[StageName, list[ToolName]] = {
    StageName.CLONING: [],
    StageName.STATIC_ANALYSIS: [ToolName.SEMGREP, ToolName.BANDIT],
    StageName.SECRETS: [ToolName.GITLEAKS, ToolName.TRUFFLEHOG],
    StageName.DEPENDENCIES: [ToolName.OSV_SCANNER, ToolName.TRIVY, ToolName.OPENSSF_SCORECARD],
    StageName.TOOL_DESCRIPTION_CHECK: [
        ToolName.MCP_SHIELD,
        ToolName.MCP_SCAN,
        ToolName.MCP_CONTEXT_PROTECTOR,
        ToolName.AEVRIN_MANIFEST_RULES,
    ],
    StageName.AGGREGATING: [],
}


class TriageStatus(str, Enum):
    OPEN = "open"
    FIXED = "fixed"
    FALSE_POSITIVE = "false_positive"


class Location(BaseModel):
    """Where a finding was found. Exactly one style is populated depending on
    whether this came from source-code analysis or a manifest/config check.
    """

    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    manifest_field: str | None = None
    tool_name_in_manifest: str | None = None


class Finding(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scan_id: UUID
    tool: ToolName
    owasp_category: OwaspMcpCategory
    severity: Severity
    title: str
    description: str
    location: Location = Field(default_factory=Location)
    remediation: str
    verified: bool | None = None  # e.g. TruffleHog's live credential verification
    not_tested: bool = False  # true only for the synthetic MCP08 placeholder
    raw: dict[str, Any] | None = None  # original tool output, for debugging/audit
    triage_status: TriageStatus = TriageStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScanStage(BaseModel):
    scan_id: UUID
    name: StageName
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class Scan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID | None = None
    target_type: TargetType
    target: str
    status: ScanStatus = ScanStatus.QUEUED
    score: int | None = None
    stages: list[ScanStage] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
