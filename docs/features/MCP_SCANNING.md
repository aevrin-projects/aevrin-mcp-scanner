# MCP scanning

**Status: implemented.**

## Purpose

Scan an MCP server - via its source repository, a local path, a live server
URL, or a pasted client config - for MCP-specific security problems, and
report what could not be checked as clearly as what was.

Aevrin is an MCP and AI-agent security product. It is **not** a
general-purpose source-code scanner: there is no SAST stage, no repository
hygiene scoring, and no findings about Dockerfile style, CI configuration,
branch protection, or repository badges. That surface was removed
deliberately (see `DECISIONS.md` ADR-027); it was not MCP security, and
mixing it into an MCP report is what made earlier reports unreadable.

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
CLONING -> DISCOVERY -> MCP_RULES -> MCP_BEHAVIOR -> SECRETS ->
DEPENDENCIES -> AGGREGATING
```

| Stage | What runs | Where |
|---|---|---|
| Tool discovery | MCP-server detection, tool enumeration | `analysis/mcp_detection.py`, `analysis/discovery.py` |
| MCP tool rules | the AS-* catalogue, AV-001..AV-003 | `mcp/rules.py`, `mcp/supply_chain.py`, `analysis/manifest_rules.py`, `analysis/rug_pull.py` |
| MCP behavior analysis | Aevrin's own Semgrep taint rule pack | `adapters/mcp_behavior.py` |
| Credential exposure | TruffleHog | `adapters/trufflehog.py` |
| Supply chain | OSV-Scanner | `adapters/osv_scanner.py` |

Two external scanners, down from eight. What was removed and why is in
`EXTERNAL_SCANNERS.md` and `DECISIONS.md` ADR-027; the short version is
that Semgrep's generic rulesets and Bandit were code security rather than
MCP security, Gitleaks duplicated TruffleHog without its live verification,
Trivy duplicated OSV-Scanner and additionally produced the Dockerfile
misconfiguration noise, OpenSSF Scorecard produced only repository-practice
findings, and MCP-Shield is superseded by the rule engine below.

## The rule engine

`mcp/rules.py` is the centre of the product. Every rule reads one `McpTool`
(or, for the two set-level rules, the whole list) and emits an Aevrin
`Finding`. There is no separate issue model, no rule registry, and no
plugin loader: `run_rules` is a list of function calls, because that is
what a fixed set of rules actually needs.

The `AS-` rules are adapted from the
[ToolTrust Scanner](https://github.com/AgentSafe-AI/tooltrust-scanner)
(MIT, Copyright (c) 2026 AgentSafe-AI). Ids match upstream so an Aevrin
finding and a tooltrust.dev finding refer to the same check. Rules
prefixed `AV-` are Aevrin's own, with no upstream equivalent.

**AS-019 (unauthenticated MCP HTTP route) is deliberately not in the
catalogue.** It needs route-level source analysis of an embedded MCP HTTP
server, which Aevrin does not do yet. A rule id present with nothing
emitting it is claimed coverage that does not exist, which is worse than an
admitted gap; `ROADMAP.md` carries it as one.

**AS-018 is emitted by the pipeline rather than by `run_rules`**, because it
is the one rule about the *absence* of tools - there is nothing to iterate.
It exists so the ungraded state arrives with a finding explaining itself
rather than an empty list beside a bare "?".

| Id | Severity | Detects |
|---|---|---|
| AS-001 | Critical | Tool poisoning: instruction-shaped text in a tool description |
| AS-002 | Info / Medium / Low | Declared capability surface; execution combined with reach; over-broad input schema |
| AS-003 | High / Medium | Scope mismatch between a tool's name and its permissions |
| AS-004 | from CVSS | Published CVE in a production dependency (OSV-Scanner) |
| AS-005 | High | Privilege escalation: broad OAuth scopes, sudo/impersonation language |
| AS-006 | Critical / Info | Arbitrary code execution (Info when unconfirmed by capability) |
| AS-007 | Info | Insufficient tool metadata: no description |
| AS-008 | Critical | Known-compromised package version, from a vendored offline catalogue |
| AS-009 | Medium | Typosquatted tool name |
| AS-010 | Low / Medium | Credential-shaped input; insecure credential handling in the description |
| AS-011 | Low | No declared rate limit, timeout, or retry on a network/exec tool |
| AS-012 | Critical | Tool definition changed since the last scan of this target (rug pull) |
| AS-013 | High | Tool shadowing: two tools answering to the same normalized name |
| AS-014 | Info | Dependency inventory unavailable (live servers only) |
| AS-015 | Medium / High | Install-time npm lifecycle script |
| AS-016 | Critical | Known malicious indicator in a dependency or install script |
| AS-017 | Medium | Data-exfiltration language in a tool description |
| AS-018 | Info | Confirmed MCP server whose tools could not be enumerated |
| AV-001 | Critical / High | Dangerous stdio launch command |
| AV-002 | High / Medium | Plaintext transport; no declared authentication |
| AV-003 | Info | No audit logging found in source |
| AV-004 | from the rule | MCP tool input reaches a dangerous sink (taint pack) |
| AV-005 | Critical / Medium | Credential committed in source (TruffleHog) |

`mcp/catalog.py` is the **only** place that says what a rule id means. A
stored finding carries the id and its evidence; every renderer - the
dashboard, the CLI, the exported HTML report, the AI prompt - looks the
prose up from the catalogue. Rewording a rule therefore lands everywhere at
once and never requires rewriting stored rows.

### Evidence

Every finding carries `Finding.evidence`: the specific facts that made the
rule fire - the matched text, the capability, the input property name, the
package version. A finding with no evidence is an assertion, and this
product does not ship assertions. Where a rule fired on a name or
description heuristic that nothing independently confirmed, `confidence` is
`"low"` and the severity drops to Info so the guess never inflates a grade
(AS-006 is the canonical case: `browser_evaluate` with no exec capability
and no code-shaped argument is reported, at Info).

### Grouping

Identical rule verdicts across different tools become one card
(`classification/grouping.py::group_by_rule`), carrying every affected tool
name and an `occurrence_count`. A server with twenty-four tools that all
lack a dependency inventory has one problem, not twenty-four. The grouping
key includes the description with the tool's own name stripped, so AS-002
still separates "network access" from "code execution, filesystem write"
rather than collapsing every capability disclosure into one line. Criticals
are never grouped: a critical is read individually, by name.

The score is unaffected by grouping - `occurrence_count` multiplies the
severity weight - so five tools missing a timeout is five tools' worth of
risk, shown once. Grouping is a presentation decision, not a discount.

## The tool model

`mcp/tools.py` defines `McpTool`, and there is exactly one tool model in
this codebase. Before it there were three shapes for the same thing (a
source-discovered `DiscoveredTool`, a name/description-only
`ToolDescriptor`, and the untyped dicts a live handshake returned), so a
rule written against one was unavailable to the others. `McpTool` is what
all discovery paths now produce, which is why every rule applies
identically to a repository, a live server, and a pasted config.

`Permission` is likewise the single capability vocabulary: `EXEC`,
`FS_READ`, `FS_WRITE`, `NETWORK`, `DB`, `ENV`, `HTTP`, `CREDENTIAL`.
Inference reads three independent signal sources per permission - input
property names, description keywords, tool-name keywords - because a tool
that hides one usually still leaks another. Aevrin's variant of upstream's
inference splits filesystem access into read and write (the two are weighed
differently and collapsing them threw that away) and adds `CREDENTIAL`,
because "what secrets does this tool see" is a first-class question here.

A tool whose name *starts* with a write verb infers `FS_WRITE` whatever its
description says - `delete_repository`, `create_branch`, `remove_user`.
This is matched on the leading segment only, so `get_update_status` stays a
read. It is the single highest-value inference in the module: destructive
MCP tools are named this way almost universally, and matching only
`delete_file`-shaped names missed every one of them that does not operate
on a literal file.

## Discovery

**MCP-server detection** (`analysis/mcp_detection.py`) decides whether the
target actually looks like an MCP server, and how confidently, from real
evidence (SDK dependency, registry manifest, SDK import, registration call,
transport declaration, server init) - never from the repository's name.
Naming a repository `mcp-something` is not evidence. Confidence is `high` /
`medium` / `low` / `none` and is shown in the report rather than collapsed
into a bare boolean.

A repository that is **not** an MCP server now ends the scan there, with a
plain statement that Aevrin does not audit general source code. Previously
it received the full generic code-security treatment and a scored report
with MCP-labelled categories, which was a number about the wrong thing.

**Component detection** answers the narrower question of *where* inside a
repository. A monorepo's `frontend/` and `backend/` share a clone with
`mcp-server/` but carry no MCP signal of their own; `McpComponent`
independently scores every directory that owns a manifest and reports only
those clearing `low` confidence *by themselves*. This is additive, never a
replacement for the whole-repository verdict, which is scored globally
because a real server's evidence can legitimately split across directories.

**Tool discovery** (`analysis/discovery.py`) reads a server's own
registration sites from source: the Python `@mcp.tool()` decorator form,
TypeScript `registerTool`/`tool` calls, and tools-array object literals.
Input schemas are read where the registration site makes them readable - a
Python handler's own signature *is* its schema, since both FastMCP and the
reference SDK derive one from it; for JS/TS a bounded window after the
registration is searched for a JSON Schema `properties` object or a Zod
field list. Half the rules get materially better answers with property
names than without, and an unreadable schema yields no properties rather
than invented ones.

Static analysis of declarations, never execution: nothing here imports,
runs, or connects to the code it reads. That restraint is what makes it
safe against an unvetted repository, and it is also the bound on the claim
- a tool registered through indirection these patterns cannot see is a tool
this will miss.

**A live handshake** (`analysis/remote_mcp.py`) returns the same `McpTool`,
so a live-server target gets the identical rule set with no second code
path. Only validated public HTTPS URLs reach it; stdio entries are never
executed.

## Behavior analysis

`adapters/mcp_behavior.py` (`ToolName.AEVRIN_MCP_BEHAVIOR`, rule `AV-004`)
is Aevrin's own Semgrep taint rule pack (`rules/mcp/*.yaml`). It is the
only place in the product that produces *observed* evidence rather than
declared evidence: it answers "does an MCP tool's own argument reach a
dangerous sink" - `subprocess.run`, a filesystem write, an outbound
request, a credential-shaped path - using the handler's declared parameters
as the taint source. That is real dataflow, not a name/description guess a
poisoned description could defeat.

This is why Semgrep the *engine* survives the removal of Semgrep the
generic ruleset. The rules here are Aevrin's own, local files, and need no
network.

Each of the four rule files (`shell_execution.yaml`, `filesystem.yaml`,
`network.yaml`, `credentials.yaml`) carries both a `languages: [python]`
rule and a `languages: [typescript, javascript]` sibling with the same
`aevrin-capability`/`aevrin-owasp` metadata, read per-finding rather than
assumed once for the whole tool.

**Sanitizer modeling** (`DECISIONS.md` ADR-024): the filesystem rules treat
an argument passed through `os.path.basename(...)` / `path.basename(...)`
as clean, and the Python shell rule treats `shlex.quote(...)` the same way.
Only specific, unambiguous standard-library functions are modeled, never a
control-flow pattern: Semgrep's taint mode cannot model that reliably
enough to trust for something that silently suppresses a real finding if
wrong.

**Semgrep's open-source engine cannot track taint across a function
boundary.** Every rule here is intra-procedural: a tool whose argument
reaches a sink only through a helper it calls is a real gap this pack will
miss, stated rather than hidden. Both routes to closing it were evaluated
and rejected - CodeQL's licence forbids the analysis Aevrin would need, and
Semgrep Pro requires a login and a proprietary binary fetch inside the scan
path, which breaks the offline CLI (see `DECISIONS.md`).

**Capability join** (`analysis/capability_map.py`) attributes a behavior
finding to the specific declared tool whose handler contains it, via
`Finding.mcp_tool`. This deliberately does not use `McpTool`'s
`line_start`/`line_end`, which is a *declaration* span: for Python that
span ends at the docstring, and a real sink lives in the body that starts
after it. Instead this module parses the source with Python's own `ast`
module for an exact function-body range - not a regex guess, not an
indentation heuristic. Scoped to Python only; a sink outside every known
tool's range is left unattributed rather than guessed at the nearest tool.

**Declared vs observed** (`analysis/declared_vs_observed.py`) compares an
attributed finding's observed `capability` against its tool's own inferred
`Permission` set. A capability the tool's own declaration gave no hint of
is upweighted one severity tier, `original_severity` preserved, with the
reason stated in the description. It never creates a second finding for the
same evidence, and never runs in reverse: over-description is not a
security event.

## Supply chain

Two paths, deliberately separate.

`mcp/supply_chain.py` reads the repository's own manifests for AS-008
(known-compromised package versions), AS-015 (install-time npm lifecycle
scripts) and AS-016 (known malicious indicators). It needs no network and
no execution. The threat-intelligence data files under `mcp/data/` are
vendored from the ToolTrust Scanner (MIT; full licence text in
`mcp/data/TOOLTRUST-LICENSE.txt`) - the format is theirs, the matching is
Aevrin's.

A manifest that could not be **opened** is reported as missing coverage,
not skipped in silence. That is not theoretical: on a machine with endpoint
protection, reading a `package.json` whose install script contains
`curl … | bash` can fail with a hard `OSError` - precisely the manifest
these rules most need to see. Losing it quietly would turn the most
dangerous file in the tree into a clean result.

`adapters/osv_scanner.py` covers AS-004, published CVEs in the dependency
tree, and is the only dependency scanning left. Findings are scoped to
production dependencies in `pipeline/postprocess.py`: an advisory the
owning manifest itself marks development-only is dropped, because an agent
does not run it. Only a *proven* development scope is dropped - `UNKNOWN`
is kept, since a dependency whose scope could not be established has not
been shown to be dev-only. The count of what was excluded is reported as
its own Info finding rather than vanishing.

## Risk, grade, and policy

`mcp/risk.py` is the one risk model in the product. It replaced two:
`classification/scoring.compute_score` counted *down* from 100 with its own
weights and tier caps, and `agents/grade.grade_mcp_server` counted *up*
with a different set to produce a letter, so "score" meant the opposite
thing depending on the surface and the two could disagree about the same
scan.

**Risk counts up: 0 is clean, 100 is "do not use."** Weights are
Critical 25, High 15, Medium 8, Low 2, Info 0, capped at 100 so volume
cannot out-score severity. Grade boundaries follow the ToolTrust Directory
methodology so an Aevrin grade and a tooltrust.dev grade are comparable:

| Risk | Grade | Label | Suggested policy |
|---|---|---|---|
| 0-9 | A | Trusted | ALLOW |
| 10-24 | B | Generally safe | ALLOW |
| 25-49 | C | Caution | REQUIRE_APPROVAL |
| 50-74 | D | High risk | REQUIRE_APPROVAL |
| 75-100 | F | Do not use | BLOCK |

The policy is a recommendation, never an automatic action.

**Coverage does not fold into the number.** A scan that could not read a
server's tools - or where a stage that should have run did not - gets **no
grade at all**: not an A, not an F. `GradeResult.grade` is `None` and
`incomplete` is true. This is the single most important behaviour in the
module: an empty finding list from a server nobody could enumerate looks
exactly like a perfect result, and saying so out loud is the difference
between a security product and a green badge. Every renderer shows it as
its own state ("?", "Not graded", "Scan Incomplete"), never as an absent
field.

**The risk summary** (`RiskSummary`) answers the five questions a report
has to answer, in order: what is wrong, why care, what could happen, what
to change, what policy to apply. It is generated from the findings that
actually drove the score, ranked by the risk points each rule contributed
rather than by how many times it fired - a server with one critical
execution hole and twenty-four informational notes is about the execution
hole. The impact sentence comes from the catalogue entry for the rule that
fired, never generic filler.

**Permission recommendations** (`permission_recommendation`) produce a
concrete before/after with a projected risk score. The projection is not an
estimate: the rules are pure functions of a tool list, so the recommendation
is applied to a copy of the tools and the rules are simply run again. The
number that comes back is what the scan would actually have produced.
Advice the rules cannot score (scoping a filesystem tool to an allowed
directory, allow-listing network destinations) is listed separately rather
than folded into a projection it did not earn.

Enrichment (`enrichment/epss.py`, `enrichment/kev.py`) can lower a CVE's
effective severity using FIRST.org's exploit-prediction score, but a CISA
Known Exploited Vulnerabilities match always overrides that downweighting -
a confirmed real-world exploit is never treated as merely predicted.

## OWASP MCP categories

Every finding also carries one `OwaspMcpCategory`
(`classification/owasp.py`), which is the product's public vocabulary
alongside the rule id:

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

## Rug pull {#rug-pull-source-repositories}

`analysis/rug_pull.py` diffs this scan's declared surface against the last
scan of the same target, emitting AS-012. Both discovery paths share one
persisted keyspace - `PipelineConfig.previous_signatures` /
`computed_signatures`, backed by the `rug_pull_signatures` table keyed
`(user_id, target, server_name)` - rather than a second table for what is
underneath the same question. A source tool's key is prefixed
`tool:{name}` so it cannot collide with a live server's own name.

Signatures cover a tool's name, description, and inferred permissions -
deliberately **not** line numbers, which shift on any unrelated edit
earlier in the file and would fire on every commit rather than on an
actual change to what the tool claims to do. A first scan has nothing to
diff against and produces no finding.

## Data

`Scan`, `ScanStage`, `Finding` (`scanner-core/models.py`) - see
[`../architecture/DATA_FLOWS.md`](../architecture/DATA_FLOWS.md) for how
they reach storage. `Scan.risk_score` and `Scan.grade` are written by the
pipeline; `Scan.unreliable_stages` and an empty `mcp_tools_declared` are
the two things that withhold the grade.

`Finding.rule_id`, `Finding.evidence` and `Finding.affected_tools`
(migration `0046`) are the report contract. `impact` is **not** stored: it
is looked up from the catalogue at serialization time, so one place owns
the prose and the frontend needs no copy of it.

## Security

- Every scanned target is untrusted input - see
  [`../security/SECURITY.md#ssrf-protection`](../security/SECURITY.md#ssrf-protection)
  for what stops a live-server check from becoming an SSRF proxy.
- No cloned repository's install scripts, postinstall hooks, or declared
  MCP commands are executed - analysis is static, never "run it and see."
  A stdio launch command is *inspected* (AV-001) and never invoked.
- Tool descriptions and evidence lines are attacker-controlled text on
  their way into a report and possibly an AI prompt; both are collapsed and
  length-bounded at the point they are read.
- `excluded_path` marks findings under a fixtures/tests/examples-style
  directory - kept in the report, excluded from scoring. This depends on
  the finding existing at all: `McpBehaviorAdapter` writes an empty
  `.semgrepignore` into the target first (`execution/semgrep_ignore.py`),
  because Semgrep's own default ignore patterns otherwise silently skip any
  path containing a directory literally named `tests` (`DECISIONS.md`
  ADR-025/026).

## Limitations (stated, not hidden)

- Runtime/dynamic MCP behavior is not tested. MCP08 is reported as an
  explicit not-tested placeholder in every scan rather than omitted.
- Taint analysis is intra-procedural (above).
- A transitive dependency's own install script lives in that package's
  registry metadata, not in the repository, so AS-015/AS-016 cover what the
  clone contains. AS-014 is what says so for a live server.
- A scan is a snapshot. A dependency graded clean today can have a CVE
  published tomorrow; see
  [`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md) for how staleness is handled.
- Detection confidence below `high`/`medium` means MCP-specific findings
  may be incomplete, and the report says so via `mcp_detection_confidence`
  and `mcp_detection_evidence`.

## Testing

`backend/scanner-core/tests/` - `test_mcp_rules.py` (the rules, weighted
toward false-positive suppression), `test_risk.py` (score direction, grade
boundaries, the ungraded state), `test_supply_chain.py`,
`test_discovery.py`, `test_grouping.py`, `test_pipeline_reliability.py`
(the two incompleteness conditions, end to end). See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`../architecture/DATA_FLOWS.md`](../architecture/DATA_FLOWS.md),
[`AGENT_POSTURE.md`](AGENT_POSTURE.md) (posture reads real scan grades for
servers an agent can call), [`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md),
[`../../backend/scanner-core/EXTERNAL_SCANNERS.md`](../../backend/scanner-core/EXTERNAL_SCANNERS.md).
