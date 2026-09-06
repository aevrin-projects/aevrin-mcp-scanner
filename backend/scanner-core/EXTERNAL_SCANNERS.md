# External scanner provenance

The dependency record required before any third-party scanner is integrated,
and the record of every one that was removed. One row per project: what it
is, what its licence permits, and how Aevrin is allowed to use it.

Re-verify before adding a scanner or changing how one is consumed; a licence
can change between releases.

This file is an engineering record, not a product surface. Aevrin's users see
"Aevrin Security Scan" and are not told which engine produced their findings
(`DECISIONS.md` ADR-036). That is a decision about the dashboard, the CLI and
the API - it does not extend to attribution, which is a licence obligation
and is discharged here and in the vendored licence text.

## In use today

| Project | Licence | Verified | How Aevrin uses it |
|---|---|---|---|
| [ToolTrust Scanner](https://github.com/AgentSafe-AI/tooltrust-scanner) | MIT | 2026-09-06 | **The MCP security engine.** Pinned release binary, executed as a subprocess inside a disposable container. Never imported, never linked, never modified. |

Full licence text is vendored at
`aevrin_scanner_core/mcp/data/TOOLTRUST-LICENSE.txt`. Copyright (c) 2026
AgentSafe-AI. The binary is redistributed inside
`backend/scanner-image`, which is distribution, so retaining that notice is
required rather than courteous.

### How it is consumed

`v0.3.19`, pinned by version **and** SHA-256 in
`backend/scanner-image/Dockerfile`. The upstream one-line installer
(`curl -sfL … | bash`) is deliberately not used: it resolves "latest" at build
time, so two builds of the same Dockerfile could ship different security
engines, and it executes a remote script unverified. A scanner that cannot
say which version produced a finding cannot support that finding.

Aevrin runs one command:

```
mcp-scanner scan --server "<command>" --output json
```

and reads `policies[]` and `summary` from the result. Nothing about a
severity, a score, a grade or a rule id is adjusted on the way through -
see `mcp/tooltrust.py` and `DECISIONS.md` ADR-033.

### What Aevrin adds around it, and why

The engine does not emit everything a report needs. These are the gaps, and
none of them involve re-deciding what it found:

- **A server-level grade.** It grades per tool and offers only an average.
  The average is unusable: a real run summarised a server containing a
  Critical arbitrary-code-execution tool as `avg_grade: A`. Aevrin displays
  the worst tool's grade and score, unchanged. A selection, not a rubric.
- **Prose.** Findings carry `rule_id`, `severity`, `code`, `description`,
  `location` and `evidence` - no title, no impact, no fix. `mcp/catalog.py`
  supplies those, keyed by the same ids.
- **Target resolution.** The engine takes a command. Turning a GitHub URL
  into one is Aevrin's job, and is done from the project's own manifest -
  never from the repository name (`mcp/resolve.py`, ADR-035).
- **A sandbox.** The engine starts the target server; it does not isolate
  it. Aevrin runs both inside a credential-free, disposable container
  (ADR-034).
- **Grouping.** One rule firing on twenty-four tools is one card with
  twenty-four affected tools, not twenty-four cards.

### The earlier adaptation, and why it was reversed

An earlier iteration ported the AS- rules to Python rather than executing the
binary, because the Go scanner cannot enumerate tools from a repository's
source and repository scanning was then the main path. Making the live server
the security target removed that constraint, and the port went with it: two
implementations of one rule set eventually disagree, and a port drifts
silently when upstream moves. `mcp/rules.py`, `mcp/supply_chain.py` and
`mcp/tools.py` are deleted.

## Removed, and why

Recorded because "why doesn't Aevrin scan for X" is a question that keeps
being asked. See `DECISIONS.md` ADR-027 and ADR-033.

| Project | Verdict | Reason |
|---|---|---|
| Semgrep (engine + Aevrin's MCP taint pack) | **REMOVE** | The engine analyses live tool definitions, which is where MCP risk actually is. A source-level taint pack answers a different question about a repository that may not even be the code the server runs. |
| Bandit | **REMOVE** | Generic Python SAST with no MCP-specific rules at all. |
| Gitleaks | **REMOVE** | Duplicated TruffleHog over the same tree without its live credential verification. |
| TruffleHog | **REMOVE** | Committed-credential scanning is repository security, not MCP security. It produced real findings, and losing them is a real cost - stated here rather than glossed. |
| Trivy | **REMOVE** | Duplicated OSV-Scanner for CVEs, and emitted Dockerfile/CI misconfiguration findings - the loudest single source of non-MCP noise. |
| OSV-Scanner | **REMOVE** | Repository-wide dependency CVEs. Attaching unrelated `hono`/`qs`/`body-parser` advisories to an MCP result is a dependency dump, not a security assessment. CVE coverage is not lost: AS-004 does OSV lookups scoped to the scanned server's own dependencies. |
| OpenSSF Scorecard | **REMOVE** | Produced only repository-practice findings: badges, fuzzing status, branch protection, code-review percentage. |
| MCP-Shield | **REPLACE** | Tool-description scanning, superseded by AS-001/AS-002/AS-013. |
| Aevrin rug-pull / tool-drift tracking | **REMOVE** | Aevrin's own cross-scan check. Upstream evaluates AS-012 in its directory pipeline; Aevrin no longer tracks drift at all, and `rug_pull_signatures` is dropped. |

EPSS enrichment, CISA KEV lookup and dependency-scope classification went
with OSV-Scanner: all three describe a CVE in a dependency tree, and there is
no longer a repository-wide dependency tree to describe.

## Evaluated, not integrated

| Project | Licence | Verified | Verdict |
|---|---|---|---|
| [snyk/agent-scan](https://github.com/snyk/agent-scan) | Apache-2.0 | API + README | External executable only; closed to contributions, see below. |
| [L3G5/mcp-scan](https://github.com/L3G5/mcp-scan) | Apache-2.0 | API | Overlaps coverage the engine already provides. |
| [affaan-m/agentshield](https://github.com/affaan-m/agentshield) | MIT | API | Reference; adaptation permitted with attribution. |
| [aiconnai/agentshield](https://github.com/aiconnai/agentshield) | MIT **or** Apache-2.0 | `LICENSE-MIT` + `LICENSE-APACHE` present | External executable; adaptation permitted. |

None are copyleft in a way that reaches Aevrin's own source.

### snyk/agent-scan - read this before depending on it

The README states plainly:

> Agent Scan is closed to contributions.
> Agent Scan does not accept external contributions at this time.

Pull requests are technically enabled on the repository, which contradicts
the README at a glance. The README is the operative statement: treat this as
a vendored tool that cannot be influenced, not a base to build on.

## Rules these findings impose

1. There is one MCP security engine. A second one would eventually disagree
   with the first about the same server, and two grades is worse than either.
2. A scanner that did not run is reported as unavailable, never as a clean
   result. An unavailable sandbox is an unavailable scan.
3. Adding a scanner means adding a row here first, with the licence checked
   against its repository rather than assumed from a previous entry.
4. Redistributing a binary requires vendoring its licence text beside the
   image that ships it, whatever the product surface shows the user.
