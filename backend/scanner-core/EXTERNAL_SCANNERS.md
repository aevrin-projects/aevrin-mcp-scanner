# External scanner provenance

The dependency record required before any third-party scanner is integrated,
and the record of every one that was removed. One row per project: what it
is, what its licence permits, and how Aevrin is allowed to use it.

Re-verify before adding a scanner or changing how one is consumed; a licence
can change between releases.

## In use today

| Project | Licence | Verified | How Aevrin uses it |
|---|---|---|---|
| [TruffleHog](https://github.com/trufflesecurity/trufflehog) | AGPL-3.0 (CLI) | 2026-08-26 | Pinned executable, invoked as a subprocess or container. Never imported, never linked. |
| [OSV-Scanner](https://github.com/google/osv-scanner) | Apache-2.0 | 2026-08-26 | Pinned executable, same boundary. |
| [Semgrep OSS](https://github.com/semgrep/semgrep) | LGPL-2.1 | 2026-08-26 | Pinned executable, running **only** Aevrin's own rule pack (`rules/mcp/*.yaml`). None of Semgrep's registry rulesets are used. |
| [ToolTrust Scanner](https://github.com/AgentSafe-AI/tooltrust-scanner) | MIT | 2026-09-03 | **Adapted**, not executed. See below. |

TruffleHog's CLI is AGPL: it is invoked across a process boundary as a
separate program and its source is neither imported nor modified, so
Aevrin's own source is unaffected. That boundary is the reason it stays a
subprocess and is never vendored.

## ToolTrust Scanner - the one project whose code was adapted

`https://github.com/AgentSafe-AI/tooltrust-scanner`, MIT, Copyright (c) 2026
AgentSafe-AI. Full licence text is vendored at
`aevrin_scanner_core/mcp/data/TOOLTRUST-LICENSE.txt`.

Shelling out to it was evaluated and rejected. ToolTrust is a Go binary
whose repository scan can detect an embedded MCP implementation but cannot
enumerate tools from source - it needs a live handshake or a JSON tool list.
Aevrin's own `analysis/discovery.py` *can* read tools out of a repository,
which is the highest-value target in this product, so shelling out would
have produced almost nothing for exactly the case that matters most.

What was taken:

- **Rule ids and detection logic** for the AS- rules, ported to Python in
  `mcp/rules.py`. Ids match upstream so a finding here and a finding on
  tooltrust.dev refer to the same check. AS-019 was *not* ported: it needs
  route-level source analysis Aevrin does not do, and a rule id sitting in
  the catalogue with nothing emitting it is claimed coverage that does not
  exist. `ROADMAP.md` carries it as a known gap instead.
- **The false-positive suppressions**, which are the hard-won part: the
  `.gitignore` exemption on AS-001, the defensive-security-tool exemption
  on the bare `jailbreak` keyword, the cloud-CLI-wrapper exemption on
  AS-003, the safe-name lists on AS-006, the pagination-cursor allow-list
  on AS-010, and the entropy floors on AS-009.
- **Permission inference** from a tool's schema, name and description.
- **The risk weights and grade boundaries**, so an Aevrin grade and a
  ToolTrust Directory grade are comparable rather than coincidentally
  similar.
- **Threat-intelligence data files** (`mcp/data/compromised_packages.json`,
  `mcp/data/npm_iocs.json`), format unchanged; the matching code is
  Aevrin's.

What is Aevrin's own, and where this deliberately differs:

- The finding shape (one `Finding` model, no separate issue type), the
  OWASP MCP category mapping, and the evidence lines.
- `Permission` splits filesystem access into read and write, and adds
  `CREDENTIAL`.
- AS-002 additionally scores execution combined with reach; upstream leaves
  the capability surface entirely unscored.
- AS-006 additionally fires at Critical when a tool holds `EXEC` **and**
  takes a caller-supplied code argument, regardless of keywords. Gating that
  behind a vocabulary match meant `run_command(command: str)` - the single
  most dangerous shape an MCP tool takes - reported as nothing worse than a
  capability disclosure.
- AS-014 does not fire for a source-scanned repository, because the
  manifests were read directly. Upstream fires on any tool without
  `metadata.dependencies`, which is correct for a live handshake and wrong
  for a repository: it put an identical Info card on every tool in the
  server and claimed coverage was incomplete when it was not.
- The `AV-` rules (launch command, transport auth, audit logging, the taint
  pack, committed credentials) have no upstream equivalent.

## Removed, and why

Recorded because "why doesn't Aevrin scan for X" is a question that keeps
being asked. See `DECISIONS.md` ADR-027.

| Project | Verdict | Reason |
|---|---|---|
| Semgrep registry rulesets (`p/security-audit`, `p/owasp-top-ten`, `p/python`) | **REMOVE** | Generic SAST. Code security, not MCP security. The engine stays for Aevrin's own MCP taint pack. |
| Bandit | **REMOVE** | Generic Python SAST with no MCP-specific rules at all. |
| Gitleaks | **REMOVE** | Duplicated TruffleHog over the same tree without its live credential verification. A verified credential is a materially different finding from a string that looks like one. |
| Trivy | **REMOVE** | Duplicated OSV-Scanner for CVEs, and additionally emitted Dockerfile/CI misconfiguration findings - the loudest single source of non-MCP noise in a report. |
| OpenSSF Scorecard | **REMOVE** | Produced only repository-practice findings: badges, fuzzing status, branch protection, code-review percentage. None of it is MCP security. |
| MCP-Shield | **REPLACE** | Tool-description scanning, superseded by AS-001/AS-002/AS-013, which need no binary, no Node runtime, and no network. |

## Evaluated, not integrated

| Project | Licence | Verified | Verdict |
|---|---|---|---|
| [snyk/agent-scan](https://github.com/snyk/agent-scan) | Apache-2.0 | API + README | External executable only; closed to contributions, see below. |
| [L3G5/mcp-scan](https://github.com/L3G5/mcp-scan) | Apache-2.0 | API | Overlaps coverage the rule engine now provides directly. |
| [affaan-m/agentshield](https://github.com/affaan-m/agentshield) | MIT | API | Reference; adaptation permitted with attribution. |
| [aiconnai/agentshield](https://github.com/aiconnai/agentshield) | MIT **or** Apache-2.0 | `LICENSE-MIT` + `LICENSE-APACHE` present | External executable; adaptation permitted. |

None are copyleft in a way that reaches Aevrin's own source. Adapting code
from any of them is permitted, but requires preserving the original
copyright notice and licence text - Apache-2.0 additionally requires stating
what was changed.

### snyk/agent-scan - read this before depending on it

The README states plainly:

> Agent Scan is closed to contributions.
> Agent Scan does not accept external contributions at this time.

Pull requests are technically enabled on the repository, which contradicts
the README at a glance. The README is the operative statement: treat this as
a vendored tool that cannot be influenced, not a base to build on. Bugs go
to their issue tracker and may never be fixed on our schedule.

## Rules these findings impose

1. Aevrin's normalised finding model stays canonical. A third-party result
   is converted at the adapter boundary and never rendered raw.
2. A scanner that did not run is reported as unavailable, never as a clean
   result - the same rule the pipeline already applies to incomplete
   coverage.
3. Agreement between scanners is a confidence signal, not a count. Two
   scanners reporting one underlying issue is one risk detected twice.
4. Adding a scanner means adding a row here first, with the licence checked
   against its repository rather than assumed from a previous entry.
5. Adapting code, rather than executing it, additionally requires vendoring
   the licence text beside what was adapted and stating what changed - as
   the ToolTrust section above does.
