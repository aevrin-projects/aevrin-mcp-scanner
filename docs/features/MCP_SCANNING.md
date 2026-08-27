# MCP scanning

**Status: implemented.**

## Purpose

Scan an MCP server - via its source repository, a local path, or a live
server URL - for security problems, using established open-source
scanners rather than a proprietary detector, and report what could not be
checked as clearly as what was.

## User workflow

Three entry points, one engine (see
[`../architecture/DATA_FLOWS.md#scanning-three-surfaces-one-pipeline`](../architecture/DATA_FLOWS.md#scanning-three-surfaces-one-pipeline)):
the CLI (`aevrin scan`), the Claude Code hook (blocks a risky install
before it happens), and the dashboard ("New scan"). A CI pipeline is just
the CLI run non-interactively with `--fail-on` and a checked exit code.

## Architecture

`backend/scanner-core/aevrin_scanner_core/pipeline/orchestrator.py` drives
a fixed stage sequence:

```
CLONING -> STATIC_ANALYSIS -> SECRETS -> DEPENDENCIES ->
TOOL_DESCRIPTION_CHECK -> AGGREGATING
```

| Stage | Tools |
|---|---|
| Static analysis | Semgrep, Bandit |
| Secrets | Gitleaks, TruffleHog |
| Dependencies | OSV-Scanner, Trivy, OpenSSF Scorecard |
| Tool description check | mcp-shield, mcp-scan, mcp-context-protector, Aevrin's own manifest rules |

Each adapter (`scanner-core/adapters/`) normalizes its tool's raw output
into the shared `Finding` model - a finding from Semgrep and a finding
from Gitleaks are indistinguishable in shape to everything downstream.
Cross-scanner agreement on the same advisory is folded into one `Finding`
with `corroborated_by` populated, not left as duplicate rows.

**MCP-server detection**
(`scanner-core/analysis/mcp_detection.py`) decides whether the target
actually looks like an MCP server, and how confidently, from real evidence
(SDK dependency, registry manifest, SDK import, registration call,
transport declaration, server init) - never from the repository's name.
Naming a repository `mcp-something` is not evidence; the detection logic
explicitly excludes it. Confidence is `high` / `medium` / `low` / `none`,
and is itself shown in the report rather than collapsed into a bare
boolean, because "should I run MCP-specific analysis on this repo" needs
more resolution than "is this MCP or not."

**Tool discovery from source** - a server's own repository has no reason
to contain a *client* config, so a purely config-based scan of an MCP
server's own repo previously produced almost no MCP-specific analysis of
the highest-value target. `discover_tools()` reads the server's own
registration sites directly and feeds the same manifest rules used for a
client-side config.

## Classification and scoring

Every finding carries one `OwaspMcpCategory` (`classification/owasp.py`):

| Code | Category |
|---|---|
| MCP01 | Token Mismanagement & Secret Exposure |
| MCP02 | Tool Poisoning (Hidden Instructions) |
| MCP03 | Cross-Origin Escalation / Tool Shadowing |
| MCP04 | Rug Pull (Tool Drift After Install) |
| MCP05 | Command Injection, Path Traversal, SSRF, File Access |
| MCP06 | Missing/Weak Authentication |
| MCP07 | Supply Chain / Malicious or Typosquatted Dependencies |
| MCP08 | Prompt Injection via Live Tool Responses |
| MCP09 | Excessive Agency / Overprivileged Scope |
| MCP10 | Weak/Missing Audit Logging |

Scoring (`classification/scoring.py`) starts at 100 and deducts per
finding, capped per severity tier so a pile of low-severity noise can't
mathematically outweigh one critical finding; enrichment
(`enrichment/epss.py`, `enrichment/kev.py`) can lower a CVE's effective
severity using FIRST.org's exploit-prediction score, but a CISA Known
Exploited Vulnerabilities match always overrides that downweighting - a
confirmed real-world exploit is never treated as merely predicted.
`grade_mcp_server()` (`agents/grade.py`) converts the score plus a small
set of override conditions into the A/B/C/D trust grade used everywhere a
grade is shown - see
[`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md#the-letters) for the full
letter/override table, since the marketplace's documentation already
states it precisely and there's no reason to restate it with different
words here.

## Data

`Scan`, `ScanStage`, `Finding` (`scanner-core/models.py`) - see
[`../architecture/DATA_FLOWS.md`](../architecture/DATA_FLOWS.md) for how
they reach storage. `Scan.unreliable_stages` is the field that makes an
incomplete scan detectable; `ScanStatus.INCOMPLETE` is set whenever it's
non-empty.

## Security

- Every scanned target is untrusted input - see
  [`../security/SECURITY.md#ssrf-protection`](../security/SECURITY.md#ssrf-protection)
  for what stops a live-server check from becoming an SSRF proxy.
- No cloned repository's install scripts, postinstall hooks, or declared
  MCP commands are executed as part of scanning - analysis is static
  (source/manifest reading), never "run it and see."
- `excluded_path` marks findings under a fixtures/tests/examples-style
  directory - kept in the report, but excluded from scoring, so a security
  test fixture doesn't tank a real project's grade.

## Limitations (stated, not hidden)

- Runtime/dynamic MCP behavior is not tested - a tool's declared
  description and manifest are analyzed; what the tool actually does when
  invoked at runtime is not exercised.
- A scan is a snapshot. A dependency graded clean today can have a new CVE
  published tomorrow; see the marketplace's rescan-on-evidence model in
  [`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md) for how staleness is handled
  there specifically.
- Detection confidence below `high`/`medium` means MCP-specific findings
  may be incomplete for that target, and the report says so via
  `mcp_detection_confidence` and `mcp_detection_evidence` rather than
  silently running the same analysis regardless.

## Testing

`backend/scanner-core/tests/` - adapters, pipeline reliability/fallback,
MCP detection (including the underscore-boundary and repository-naming
regression tests), grading, rug-pull, EPSS/KEV, network safety. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`../architecture/DATA_FLOWS.md`](../architecture/DATA_FLOWS.md),
[`AGENT_POSTURE.md`](AGENT_POSTURE.md) (posture reads real scan grades for
servers an agent can call), [`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md).
