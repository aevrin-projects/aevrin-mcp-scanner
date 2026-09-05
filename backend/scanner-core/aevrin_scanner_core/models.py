"""Shared data model for a scan and its findings.

Every surface (backend API, CLI, hook) constructs and reads these same
Pydantic models so a finding described on the website reads identically in
the CLI and in a hook block message.

Aevrin scans MCP servers and the agents that install them. It is not a
general-purpose source-code scanner, and this model reflects that: there is
no stage for generic static analysis, no tool entry for a SAST engine, and
no place to put a repository-hygiene observation. Findings are about tools,
permissions, credentials, and the supply chain the MCP server itself pulls
in.
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
    """What produced a finding.

    Five entries, down from eleven. Semgrep's generic rulesets, Bandit,
    Gitleaks, Trivy, OpenSSF Scorecard and MCP-Shield were removed with the
    code-security product they belonged to; see DECISIONS.md ADR-027 for
    what each one was doing and why none of it was MCP security.
    """

    # Aevrin's MCP tool-definition rules (the AS-* catalogue and the
    # manifest-driven supply-chain checks): mcp/rules.py, mcp/supply_chain.py.
    AEVRIN_MCP_RULES = "aevrin-mcp-rules"
    # Aevrin's own Semgrep taint rule pack (adapters/mcp_behavior.py,
    # rules/mcp/*.yaml): does an MCP tool argument reach a dangerous sink,
    # not "does a dangerous API exist somewhere in the repository".
    AEVRIN_MCP_BEHAVIOR = "aevrin-mcp-behavior"
    # Launch-command inspection, transport authentication, audit-logging
    # presence, and tool-signature drift: analysis/manifest_rules.py,
    # analysis/rug_pull.py. Aevrin rules with no ToolTrust equivalent.
    AEVRIN_MANIFEST_RULES = "aevrin-manifest-rules"
    TRUFFLEHOG = "trufflehog"
    OSV_SCANNER = "osv-scanner"


class TargetType(str, Enum):
    GITHUB_REPO = "github_repo"
    LIVE_MCP_SERVER = "live_mcp_server"
    CONFIG_PASTE = "config_paste"
    LOCAL_PATH = "local_path"  # CLI-only: the dashboard's picker doesn't expose this mode


class ScanStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    # Set when a stage that should have produced evidence produced none
    # because it could not run - a missing binary, an unreachable network,
    # or tool registrations this could not parse. An empty findings list
    # from a check that never ran is indistinguishable from "nothing found"
    # unless this is tracked explicitly, so a scan in this state is never
    # presented as clean and never receives a letter grade.
    INCOMPLETE = "incomplete"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageName(str, Enum):
    """The pipeline, in execution order.

    `static_analysis` is gone: it ran Semgrep's generic rulesets and Bandit
    over the whole repository, which is code security, not MCP security.
    `tool_description_check` became `mcp_rules`, which is what it now
    actually is - the AS-rule engine over discovered tools rather than one
    external description scanner.
    """

    CLONING = "cloning"
    DISCOVERY = "discovery"
    MCP_RULES = "mcp_rules"
    MCP_BEHAVIOR = "mcp_behavior"
    SECRETS = "secrets"
    DEPENDENCIES = "dependencies"
    AGGREGATING = "aggregating"


STAGE_LABELS: dict[StageName, str] = {
    StageName.CLONING: "Cloning",
    StageName.DISCOVERY: "Tool discovery",
    StageName.MCP_RULES: "MCP tool rules",
    StageName.MCP_BEHAVIOR: "MCP behavior analysis",
    StageName.SECRETS: "Credential exposure",
    StageName.DEPENDENCIES: "Supply chain",
    StageName.AGGREGATING: "Aggregating",
}

# Which tools run within which stage. Used by the runner to drive stage
# transitions and by the frontend/CLI to render consistent stage-to-tool
# grouping.
STAGE_TOOLS: dict[StageName, list[ToolName]] = {
    StageName.CLONING: [],
    StageName.DISCOVERY: [],
    StageName.MCP_RULES: [ToolName.AEVRIN_MCP_RULES, ToolName.AEVRIN_MANIFEST_RULES],
    StageName.MCP_BEHAVIOR: [ToolName.AEVRIN_MCP_BEHAVIOR],
    StageName.SECRETS: [ToolName.TRUFFLEHOG],
    StageName.DEPENDENCIES: [ToolName.OSV_SCANNER],
    StageName.AGGREGATING: [],
}


class TriageStatus(str, Enum):
    OPEN = "open"
    FIXED = "fixed"
    FALSE_POSITIVE = "false_positive"


class DependencyScope(str, Enum):
    """Where a vulnerable dependency actually lives, per the owning
    manifest's own dependency/devDependency split."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    UNKNOWN = "unknown"


class Location(BaseModel):
    """Where a finding was found. Exactly one style is populated depending on
    whether this came from source analysis or a manifest/tool-definition check.
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
    # The rule that produced this, e.g. "AS-006". `mcp/catalog.py` is the
    # only place that says what an id means; a finding row carries the id and
    # the evidence, and every renderer reads the prose from the catalogue, so
    # rewording a rule never requires rewriting stored findings. None only
    # for a finding whose producing tool has no rule identity of its own.
    rule_id: str | None = None
    owasp_category: OwaspMcpCategory
    severity: Severity
    title: str
    description: str
    location: Location = Field(default_factory=Location)
    remediation: str
    # The specific facts that made this rule fire: the matched text, the
    # capability, the input property, the package version. Every non-trivial
    # finding must carry at least one - a finding with no evidence is an
    # assertion, and this product does not ship assertions.
    evidence: list[str] = Field(default_factory=list)
    # Every declared MCP tool this finding applies to. One entry for a
    # per-tool finding; several once `classification/grouping.py` has folded
    # an identical rule result across tools into one card.
    affected_tools: list[str] = Field(default_factory=list)
    verified: bool | None = None  # e.g. TruffleHog's live credential verification
    not_tested: bool = False  # true only for the synthetic MCP08 placeholder
    # True when location.file_path falls under a fixtures/tests/examples-style
    # directory (see fixture_paths.py). Excluded from scoring the same way
    # not_tested is, but never dropped, still a real finding worth showing.
    excluded_path: bool = False
    # "low" when a rule fired on a name or description heuristic that nothing
    # independently confirmed. None when the rule had direct evidence.
    confidence: str | None = None
    # Set when this finding's severity was changed from what the rule itself
    # assigned (low confidence, EPSS predicts negligible exploitation, the
    # dependency is dev-only, or a capability was observed that the tool never
    # declared). The original stays here so the change is auditable.
    original_severity: Severity | None = None
    # FIRST.org Exploit Prediction Scoring System probability (0-1) that this
    # CVE sees exploitation in the wild in the next 30 days. None means EPSS
    # had no data, the finding isn't CVE-bearing, or the fetch failed; never
    # a guessed score.
    epss_score: float | None = None
    # True when this CVE appears in CISA's Known Exploited Vulnerabilities
    # catalog - confirmed exploitation, not a prediction. Always wins over
    # any EPSS-driven downweighting.
    in_kev: bool = False
    # Dev-only/prod split for dependency findings, from manifest parsing.
    dependency_scope: DependencyScope | None = None
    # Other tools that independently reported this same advisory for this
    # same package. A non-empty list is a confidence signal, not noise.
    corroborated_by: list[ToolName] = Field(default_factory=list)
    # How many locations or tools this one logical finding was collapsed
    # from. 1 for everything that wasn't grouped. See grouping.py.
    occurrence_count: int = 1
    # The other locations folded into occurrence_count, beyond `location`
    # itself, so the report can still list every affected file even though
    # scoring only ever sees this one Finding for the whole group.
    additional_locations: list[Location] = Field(default_factory=list)
    raw: dict[str, Any] | None = None  # original tool output, for debugging/audit
    # Which declared MCP tool this finding's sink was found inside, from
    # analysis.capability_map.attribute_findings_to_tools. None means either
    # this finding isn't tool-shaped, or it is but no known tool's function
    # body could be shown to contain it - never a guess at the nearest one.
    mcp_tool: str | None = None
    # The normalized capability this finding is about - "shell_execution",
    # "credential_access", etc; the vocabulary adapters/mcp_behavior.py sinks
    # are organised around. Set only by that adapter.
    capability: str | None = None
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
    # 0-100, higher is worse. The inverse of the old `score`, which counted
    # down from 100 and meant the opposite thing - see mcp/risk.py and
    # DECISIONS.md ADR-028 for why there is now exactly one direction.
    risk_score: int | None = None
    # "A".."F", or None when coverage was incomplete. A missing letter is a
    # real state, not a default: a grade is a claim about evidence, and a
    # scan that could not read a server's tools has none to make it from.
    grade: str | None = None
    # Best-effort: does this target actually look like an MCP server? None
    # for target types where the question doesn't apply (a live server URL
    # or a pasted mcp.json *is* MCP by construction). False means Aevrin has
    # nothing to say about the target: it is not an MCP server, and this
    # product no longer scans anything else.
    mcp_detected: bool | None = None
    # How sure that answer is, and on what evidence. "high" | "medium" |
    # "low" | "none".
    mcp_detection_confidence: str | None = None
    # Short human-readable evidence lines, e.g. "sdk_dependency: depends on
    # fastmcp". Shown in the report so the claim can be checked rather than
    # taken on trust.
    mcp_detection_evidence: list[str] = Field(default_factory=list)
    # Tools read out of the repository's own registration sites, or returned
    # by a live handshake. Empty for a server that registers none and for one
    # whose registrations this could not parse -- which is why an empty list
    # is never reported as "exposes nothing", only as "none found", and why
    # it forces the scan to grade as incomplete.
    mcp_tools_declared: list[str] = Field(default_factory=list)
    # Which directories inside this repository independently look like a
    # self-contained MCP server, from analysis.mcp_detection.McpComponent.
    mcp_components: list[dict[str, Any]] = Field(default_factory=list)
    # mcp.tools.capability_summary() over the discovered tools' inferred
    # permissions: {"can_execute": bool, "can_write": bool, "can_read": bool,
    # "handles_credentials": bool, "makes_network_calls": bool} - the
    # declared surface, not observed behavior. None (not a dict of all-False)
    # for a target where tool discovery never ran at all, because "never
    # established" and "established as no capabilities" are different claims.
    mcp_capabilities: dict[str, bool] | None = None
    # Names of stages where every check in that category failed to execute.
    # Non-empty means the findings above are incomplete, not a clean bill of
    # health for those categories.
    unreliable_stages: list[StageName] = Field(default_factory=list)
    stages: list[ScanStage] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
