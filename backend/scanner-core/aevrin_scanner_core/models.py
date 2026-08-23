"""Shared data model for a scan and its findings.

Every surface (backend API, CLI, hook) constructs and reads these same
Pydantic models so a finding described on the website reads identically in
the CLI and in a hook block message.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .classification.owasp import OwaspMcpCategory


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
    LOCAL_PATH = "local_path"  # CLI-only: website Screen 1 doesn't expose this mode


class ScanStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    # Set when a core tool category (static analysis, secrets, or
    # dependencies) had zero tools actually execute, e.g. Docker wasn't
    # running, a binary was missing, or the network was unreachable. An
    # empty findings list from a category that never ran is indistinguishable
    # from "nothing found" unless this is tracked explicitly, so a scan in
    # this state must never be presented as "clean" (see Scan.unreliable_stages).
    INCOMPLETE = "incomplete"


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


class DependencyScope(str, Enum):
    """Where a vulnerable dependency actually lives, per the owning
    manifest's own dependency/devDependency split. Set only when a finding's
    package could be matched against a parsed manifest; most findings have
    no scope signal available and stay UNKNOWN, not a guessed PRODUCTION."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    UNKNOWN = "unknown"


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
    # True when location.file_path falls under a fixtures/tests/examples-style
    # directory (see fixture_paths.py). Excluded from scoring the same way
    # not_tested is, but never dropped, still a real finding worth showing.
    excluded_path: bool = False
    # Semgrep's per-rule HIGH/MEDIUM/LOW confidence, verbatim from its JSON
    # metadata. None for every other tool (nothing else in this pipeline
    # emits a comparable per-finding confidence label).
    confidence: str | None = None
    # Set when this finding's severity was lowered from what the tool
    # itself assigned (low scanner confidence, EPSS predicts negligible
    # exploitation likelihood, or the dependency is dev-only), the
    # original value stays here so the downgrade is auditable, never silent.
    original_severity: Severity | None = None
    # FIRST.org Exploit Prediction Scoring System probability (0-1) that this
    # CVE sees exploitation in the wild in the next 30 days. None means EPSS
    # had no data for this CVE, the finding isn't CVE-bearing, or the EPSS
    # fetch failed; never a guessed/defaulted score.
    epss_score: float | None = None
    # True when this CVE appears in CISA's Known Exploited Vulnerabilities
    # catalog, confirmed real-world exploitation, not a prediction. Always
    # checked, and always wins over any EPSS-driven downweighting.
    in_kev: bool = False
    # Dev-only/prod split for dependency findings, from manifest parsing.
    dependency_scope: DependencyScope | None = None
    # Other tools (Trivy/OSV-Scanner/Scorecard) that independently reported
    # this same advisory for this same package, populated by cross-scanner
    # dedup, which keeps one Finding and folds the rest in here rather than
    # listing near-duplicates. A non-empty list is a confidence signal, not
    # noise: multiple independent tools agreeing on the same CVE.
    corroborated_by: list[ToolName] = Field(default_factory=list)
    # How many locations this one logical finding was collapsed from (e.g.
    # the same unpinned Action tag repeated across 44 workflow files). 1 for
    # everything that wasn't grouped. See grouping.py.
    occurrence_count: int = 1
    # The other locations folded into occurrence_count, beyond `location`
    # itself, so the UI/API can still list every affected file even though
    # scoring only ever sees this one Finding for the whole group.
    additional_locations: list[Location] = Field(default_factory=list)
    raw: dict[str, Any] | None = None  # original tool output, for debugging/audit
    triage_status: TriageStatus = TriageStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    # Best-effort: does this target actually look like an MCP server? None
    # for target types where the question doesn't apply (a live server URL
    # or a pasted mcp.json *is* MCP by construction). False means the
    # findings below are still real, but they're generic code-security
    # findings, not an MCP-specific risk assessment, surfaced prominently
    # rather than silently, confirmed live: scanning pallets/flask (zero MCP
    # relation) produced a full scored report with MCP-labeled OWASP
    # categories and no indication anywhere that this wasn't an MCP server.
    mcp_detected: bool | None = None
    # Names of stages (static_analysis, secrets, dependencies) where every
    # tool in that category failed to execute, e.g. Docker down, a binary
    # missing, network unreachable. Non-empty means the findings/score above
    # are incomplete, not a clean bill of health for those categories.
    unreliable_stages: list[StageName] = Field(default_factory=list)
    stages: list[ScanStage] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
