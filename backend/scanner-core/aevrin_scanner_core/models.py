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

    One entry, down from eleven. There is exactly one MCP security engine and
    every finding in the product comes from it, so this field no longer
    distinguishes between scanners - it records that a finding is a scanner
    result rather than something Aevrin inferred on its own.

    The value is deliberately the generic `mcp-scanner` rather than the
    upstream project's name. It reaches API responses, CLI JSON and stored
    finding rows, and which engine Aevrin runs is an implementation detail
    rather than something a user needs to reason about. The engine's identity
    and pinned version are recorded per scan instead (`Scan.scanner_version`),
    which is what reproducing a result actually requires.
    """

    MCP_SCANNER = "mcp-scanner"


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
    """What actually happens during an MCP scan, in execution order.

    These are the real steps of scanning a live MCP server, not a list of
    scanners that happen to be installed. The previous seven stages existed
    because seven different tools ran over a cloned repository; with one
    engine and a live server, the honest breakdown is: work out what to run,
    run it, read its tools, analyse them, grade the result.

    `RESOLVING` is a stage rather than a preamble because it is where most
    scans legitimately stop: a server with no published package and no
    documented launch command cannot be enumerated, and the reason a scan
    ended there is exactly what the reader needs to see.
    """

    RESOLVING = "resolving"
    LAUNCHING = "launching"
    ENUMERATING = "enumerating"
    ANALYZING = "analyzing"
    GRADING = "grading"


STAGE_LABELS: dict[StageName, str] = {
    StageName.RESOLVING: "Resolving MCP server",
    StageName.LAUNCHING: "Launching server",
    StageName.ENUMERATING: "Enumerating tools",
    StageName.ANALYZING: "Analyzing tools",
    StageName.GRADING: "Calculating grade",
}


class InvocationChannel(str, Enum):
    """Which interface asked for this scan.

    Recorded for reproducibility, never to vary the result: the same server
    scanned through any of these must produce the same findings, grade and
    policy. A channel that changed the security assessment would mean the
    dashboard and CI could disagree about whether a server is safe.
    """

    DASHBOARD = "dashboard"
    CLI = "cli"
    HOOK = "hook"
    CI = "ci"
    MCP = "mcp"
    MARKETPLACE = "marketplace"


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
    # True when location.file_path falls under a fixtures/tests/examples-style
    # "low" when a rule fired on a name or description heuristic that nothing
    # independently confirmed. None when the rule had direct evidence.
    # Set when this finding's severity was changed from what the rule itself
    # assigned (low confidence, EPSS predicts negligible exploitation, the
    # dependency is dev-only, or a capability was observed that the tool never
    # declared). The original stays here so the change is auditable.
    # FIRST.org Exploit Prediction Scoring System probability (0-1) that this
    # CVE sees exploitation in the wild in the next 30 days. None means EPSS
    # had no data, the finding isn't CVE-bearing, or the fetch failed; never
    # a guessed score.
    # True when this CVE appears in CISA's Known Exploited Vulnerabilities
    # catalog - confirmed exploitation, not a prediction. Always wins over
    # any EPSS-driven downweighting.
    # Dev-only/prod split for dependency findings, from manifest parsing.
    # Other tools that independently reported this same advisory for this
    # same package. A non-empty list is a confidence signal, not noise.
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
    # The normalized capability this finding is about - "shell_execution",
    # "credential_access", etc; the vocabulary adapters/mcp_behavior.py sinks
    # are organised around. Set only by that adapter.
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
    # Every tool the running server returned from the MCP handshake. Empty
    # means the server exposed none or could not be reached, which is never
    # reported as "exposes nothing" - it forces the scan to end ungraded.
    mcp_tools_declared: list[str] = Field(default_factory=list)
    # The command that was actually run to start the server, e.g.
    # `npx -y @playwright/mcp`. Stored because it is the single most useful
    # thing for reproducing a result, and because it is the one place a
    # resolution mistake becomes visible: a grade attributed to the wrong
    # package is worse than no grade at all.
    server_command: str | None = None
    # Engine identity and pinned version (§20). Internal - the report does not
    # show a user which binary produced their findings, but a support request
    # cannot be answered without knowing.
    scanner_name: str | None = None
    scanner_version: str | None = None
    # Which surface requested this scan. Never changes the assessment.
    invocation_channel: InvocationChannel | None = None
    # Names of stages where every check in that category failed to execute.
    # Non-empty means the findings above are incomplete, not a clean bill of
    # health for those categories.
    unreliable_stages: list[StageName] = Field(default_factory=list)
    stages: list[ScanStage] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
