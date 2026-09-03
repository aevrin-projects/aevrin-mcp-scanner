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
CLONING -> STATIC_ANALYSIS -> SECRETS -> DEPENDENCIES -> MCP_ANALYSIS ->
TOOL_DESCRIPTION_CHECK -> AGGREGATING
```

| Stage | Tools |
|---|---|
| Static analysis | Semgrep, Bandit |
| Secrets | Gitleaks, TruffleHog |
| Dependencies | OSV-Scanner, Trivy, OpenSSF Scorecard |
| MCP behavior analysis | Aevrin's own Semgrep taint rule pack |
| Tool description check | mcp-shield, Aevrin's own manifest rules |

Each adapter (`scanner-core/adapters/`) normalizes its tool's raw output
into the shared `Finding` model - a finding from Semgrep and a finding
from Gitleaks are indistinguishable in shape to everything downstream.
Cross-scanner agreement on the same advisory is folded into one `Finding`
with `corroborated_by` populated, not left as duplicate rows.

**MCP behavior analysis** (`adapters/mcp_behavior.py`,
`ToolName.AEVRIN_MCP_BEHAVIOR`) is Aevrin's own Semgrep taint rule pack
(`rules/mcp/*.yaml`), a separate adapter from `SemgrepAdapter` because its
rules declare their own OWASP MCP category and capability per finding
(`aevrin-owasp`/`aevrin-capability` in each rule's `metadata`), rather than
every result landing in one hardcoded bucket. It answers "does an MCP
tool's own argument reach a dangerous sink" - `subprocess.run`, a
filesystem write, an outbound request, a credential-shaped path - using
the tool handler's declared parameters as the taint source, which is real
dataflow evidence rather than a name/description guess a poisoned
description could defeat. Verified empirically against real Semgrep during
development (a tainted argument fires exactly at the sink's line, a safe
twin with the identical shape does not fire, a helper-function indirection
does not fire either); not exercised by an automated test that invokes the
real binary, the same convention every other adapter's test suite already
follows - see `docs/testing/TESTING.md`.

Each of the four rule files (`shell_execution.yaml`, `filesystem.yaml`,
`network.yaml`, `credentials.yaml`) now carries both a `languages: [python]`
rule and a `languages: [typescript, javascript]` sibling with the same
`aevrin-capability`/`aevrin-owasp` metadata - `adapters/mcp_behavior.py`
itself needed no change, since it already reads a rule's declared metadata
per-finding rather than assuming a language. The TS/JS source pattern
matches a tool handler passed to `server.registerTool(name, opts, handler)`
or the older `server.tool(name, desc, schema, handler)`, both `async` and
not; taint propagates through the handler's parameter whether it's
destructured (`({ command }) => ...`) or accessed by property
(`(args) => ... args.command ...`) - both verified empirically, the same
way as the Python rules, against real Semgrep 1.174.0 (true positive at the
exact tainted line for every handler shape above; true negative on a
same-shaped safe twin; true negative across a function boundary, the
identical intra-procedural limit as Python). `analysis.capability_map`'s
attribution (`Finding.mcp_tool`) is **not** extended to these findings -
that would need locating a JS/TS function's real body range without a real
parser, which was evaluated and rejected as too fragile to trust (see
`DECISIONS.md`); `Finding.capability` is still set directly from the rule's
own metadata regardless, and `declared_vs_observed.py` correctly skips a
finding with no attributed tool rather than guessing one.

**Sanitizer modeling** (`DECISIONS.md` ADR-024): the filesystem rules
(Python and TS/JS, all three severities) treat a tool argument passed
through `os.path.basename(...)` / `path.basename(...)` as clean - the
standard path-traversal defense, reducing a tainted path to a name with no
directory component - and the Python shell rule treats `shlex.quote(...)`
the same way, the standard shell-escaping function. Only these specific,
unambiguous, standard-library functions are modeled, never a control-flow
pattern (an allowlist check, a conditional): Semgrep's taint mode cannot
model that reliably enough to trust for something that silently suppresses
a real finding if wrong. No sanitizer exists for the network rules (URL
encoding does not address SSRF, what those rules actually target) or
credentials rules (there is no "escape this and it's safe" operation for a
credential access), and TS/JS shell execution has no sanitizer either - no
standard-library equivalent to `shlex.quote` exists in Node, and anchoring
on a third-party package's escaping function would be a guess about
whether it's used correctly. Verified empirically the same way as every
rule in this pack: a sanitized value's line stops firing, an
otherwise-identical unsanitized twin still fires.

**Semgrep's open-source engine cannot track taint across a function
boundary.** Every rule here is intra-procedural: a tool whose argument
reaches a sink only through a helper function it calls is a real gap this
pack will miss, stated rather than hidden. Aevrin evaluated both routes to
closing it - the paid Semgrep Pro engine and CodeQL - and rejected both:
CodeQL's licence forbids analysing a non-open-source codebase or
generating a database during automated analysis/CI without a paid GitHub
Advanced Security entitlement Aevrin does not have (see `DECISIONS.md`),
and Semgrep Pro requires `semgrep login` and a proprietary binary fetch
inside the scan path, which breaks the offline CLI. Closing this gap
honestly needs a bounded reachability graph Aevrin builds itself - future
work, not yet built.

**Capability join** (`analysis/capability_map.py`) attributes a behavior
finding to the specific declared tool whose handler contains it, via
`Finding.mcp_tool` (migration `0042`). This deliberately does **not** use
`DiscoveredTool.line_start`/`line_end` (the declaration span, above): for
Python that span ends at the docstring, and a real sink lives in the
function body that starts *after* it - confirmed concretely during
development (a tool's own declared span was lines 2-4; its actual
`subprocess.run(...)` sink was on line 5, outside it). Instead this module
parses the source with Python's own `ast` module for an exact function-body
range (`end_lineno`, Python 3.8+) - not a regex guess, not an indentation
heuristic. Scoped to Python only: the JS/TS registration forms either need
a parser this codebase doesn't have, or (`_TOOL_OBJECT`, a tools-array
literal) describe metadata with no code body to have a range at all. A
sink outside every known tool's range - or in a file whose functions
couldn't be parsed - is left with `mcp_tool` unset, never guessed at the
nearest tool.

**Wired into the pipeline as `StageName.MCP_ANALYSIS`**, between
`DEPENDENCIES` and `TOOL_DESCRIPTION_CHECK`. `discover_tools()` now runs
once, in `run_pipeline` itself rather than inside the tool-description
stage, precisely because both this stage and that one need the identical
list - reading the source tree twice to answer the same question would be
the exact waste `_walk()`'s own docstring already warns against. Skipped
(not failed) when there is no source repository for this target type, or
when no MCP tools were declared in it - running Semgrep against a
repository with nothing to check tool arguments against would be pure
cost. Not one of `_CORE_STAGES`: a Docker/binary failure here means this
one additional analysis did not run, the same reasoning that already keeps
`TOOL_DESCRIPTION_CHECK` out of that set.

**Declared vs observed** (`analysis/declared_vs_observed.py`), run
immediately after the capability join above, in the same stage. Compares
each attributed finding's `Finding.capability` (observed - what the code
does) against its tool's own `DiscoveredTool.capabilities` (declared -
what the name/description says). A capability the tool's own words gave no
hint of is upweighted one severity tier (`original_severity` preserved,
the same auditable pattern `severity_utils.downweight_one_tier` already
uses in the other direction) and its description states why. This never
creates a second finding for the same evidence - two findings describing
one fact would inflate the count without adding information - and it never
runs in reverse: a tool that declares more than was ever observed earns no
finding at all, because over-description is not a security event.
`Finding.capability` (migration `0044`) is the normalized vocabulary term
a behavior finding is about; previously only recoverable, unreliably, from
`raw` (documented as debug output, not a contract).

**Tool name shadowing** (`analysis/manifest_rules.py::check_tool_name_shadowing`,
`OwaspMcpCategory.CROSS_ORIGIN_ESCALATION`) runs inside `_run_source_mcp_analysis`,
alongside `check_excessive_agency` - same stage, same source-derived tool
list. Compares every declared tool's name against every other's with
`difflib.SequenceMatcher` and flags a pair whose names are >=82% similar
but not identical: close enough for a human skimming a list, or an agent's
own fuzzy name matching, to pick the wrong one. Severity is `HIGH` when the
pair's declared capabilities differ on `execute`/`delete`/`credential` (the
wrong pick changes what actually runs), `MEDIUM` otherwise. Names under 4
characters are excluded (trivially "similar" by ratio alone) and the
comparison is skipped entirely past 200 candidate tools (an O(n^2) cost
guard, not expected to bind on a real server). This is a naming check
only - it cannot and does not claim to know intent from static text - and
is the static-analysis counterpart to `mcp-shield`'s live-connection
shadowing detection (`adapters/mcp_shield.py`, which flags the same OWASP
category from a real handshake's tool descriptions); this one runs for a
source repository with no reachable endpoint to connect to at all.

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

**Component detection** answers a narrower, additional question:
*where* inside this repository. A monorepo's `frontend/` and `backend/`
share a clone with `mcp-server/` but carry no MCP signal of their own;
`McpComponent` (same module) independently scores every directory that
owns a manifest of its own and only reports the ones that clear `low`
confidence *by themselves*, on their own files - not because they happen
to share a repository with a directory that does. `Scan.mcp_components`
carries these as `{root, confidence, evidence}`. This is additive, never a
replacement for the whole-repository verdict above: that verdict is scored
globally on purpose, because a real server's evidence can legitimately
split across directories (an SDK dependency declared in one package, its
registration decorator reachable only through a shared internal library in
another) in a way that would under-detect if scoped to whichever single
directory scores highest alone. A monorepo can correctly score `high`
overall while contributing zero, one, or several entries to
`mcp_components`.

**Tool discovery from source** - a server's own repository has no reason
to contain a *client* config, so a purely config-based scan of an MCP
server's own repo previously produced almost no MCP-specific analysis of
the highest-value target. `discover_tools()` reads the server's own
registration sites directly and feeds the same manifest rules used for a
client-side config. Each `DiscoveredTool` also carries `line_start`/
`line_end` - the registration site's own declaration span (for Python, the
decorator through the end of the docstring; a *declaration* location, not
a function-body range, so it never claims to cover logic past the
docstring - it exists to point a report at where a tool is registered, not
to bound its behaviour). Not yet surfaced on `Scan` - `mcp_tools_declared`
stays a flat list of names for now. Deliberately **not** what "Capability
join" above uses: that needs the real function body, which starts after
this span already ends, and computes its own range independently rather
than stretching this one to cover a job it wasn't built for.

**Declared capability summary** (`analysis/mcp_detection.py::capability_summary`,
`Scan.mcp_capabilities`, migration `0045`) rolls a tool's own declared
capability classification (`_classify`, above) up into the five booleans
the trust grade weighs: `can_execute`, `can_write`, `can_read`,
`handles_credentials`, `makes_network_calls` - declared surface, not
observed behavior. Takes `(name, description)` pairs rather than
`DiscoveredTool` objects specifically so both sources of tool data feed it:
`discover_tools()`'s static reading of a repository, and (below)
`remote_mcp.py`'s live `list_tools()` handshake, which has no
`file_path`/line info to offer. `capability_summary()` existed with its own
passing unit test long before migration `0045`, computed by the pipeline on
every source scan, and discarded on every single one: nothing wrote its
result anywhere. Set to `None` - never a dict of all-`False` - when neither
source ran at all (a repository that isn't an MCP server, or a live
handshake that itself failed), because "never established" and "confirmed
no capability" are different claims and the marketplace grade is the
consumer that cares most about telling them apart - see
[`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md) and `DECISIONS.md` ADR-020.

**Live capability summary** (`analysis/remote_mcp.py`, `DECISIONS.md`
ADR-022): a live MCP server's own `list_tools()` handshake was already
being read, in full, to compute the rug-pull signature hash
(`RemoteToolSignature.signature_hash`) - the same response now also feeds
`capability_summary()` (`RemoteToolSignature.capabilities`), rather than
being discarded right after hashing. `orchestrator.py::_probe_remote_servers`
merges every configured server's live summary into `scan.mcp_capabilities`
via `merge_capability_summaries()` (an OR across sources - a capability is
real if *any* surface confirms it - `None` only when every source given is
`None`), on top of whatever the source path already set rather than
overwriting it. This is what lets a `live_mcp_server` scan - previously
always `None` here, since there is no repository for `discover_tools()` to
read - carry real, established capability evidence instead of a permanent
"could not be established" penalty (`DECISIONS.md` ADR-021).

`ToolName.MCP_SCAN` is not the Invariant Labs `mcp-scan` CLI - no such
tool runs in this pipeline. It is the label attached to findings produced
by Aevrin's own rug-pull signature diff (`analysis/rug_pull.py`), kept
under that name because that is the category (MCP04) it reports against.
`ToolName.MCP_CONTEXT_PROTECTOR` was removed: it was declared in the tool
enum and the stage's tool list with no adapter ever emitting it.

### Rug pull, source repositories {#rug-pull-source-repositories}

`analysis/rug_pull.py`'s `hash_signature`/`PinnedSignature`/`diff_signatures`
were already generic - built for the live-connection path
(`_probe_remote_servers`, one hash per *server*, its whole tool list
hashed together after a real `list_tools()` handshake) but nothing in
their shape is specific to a live connection. `_run_source_mcp_analysis`
reuses them unchanged for a source repository: one signature per
*declared tool* (`_tool_signature_pins`, `orchestrator.py`), hashing its
name, description, and declared capability labels - deliberately not
`DiscoveredTool.line_start`/`line_end`, which shift on every unrelated
edit earlier in the file and would fire a false rug-pull on a commit that
never touched the tool at all.

Both paths share one persisted keyspace - `PipelineConfig.previous_signatures`/
`computed_signatures`, backed by the single `rug_pull_signatures` table
keyed `(user_id, target, server_name)` - rather than a second table for
what is, underneath, the same question asked from a different vantage
point: "did this target's declared surface change since the last scan of
it." A source tool's key is prefixed `tool:{name}` (e.g. `tool:run_command`)
so it can't collide with a live server's own name in that same column; no
migration, no new API code, no new persistence path needed for this -
`services/scan.py`'s existing read/write of that table already round-trips
whatever strings show up in it. First scan of a target has nothing to
diff against and produces no finding, the same as the live path.

Granularity is deliberately different between the two paths: the live
path hashes a whole server's tool list as one blob (a JSON-RPC
`list_tools()` call already returns everything at once, so that was the
natural unit); the source path hashes per tool, because static discovery
already enumerates tools individually and a per-tool key pinpoints which
declared tool actually changed rather than saying only "something in this
target did."

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

`mcp_detection_confidence`, `mcp_detection_evidence`, `mcp_tools_declared`
(migration `0040`) and `mcp_components` (migration `0041`, see "Component
detection" above) are computed by every scan and reach `GET /scans/{id}`
(`ScanOut`) and the CLI's `--json` output. The dashboard UI does not yet
render any of them - the boolean `mcp_detected` chip they would sit beside
isn't rendered there either - so today they are visible to anyone reading
the API response or the CLI report, not yet to someone only looking at the
scan-detail page.

## Security

- Every scanned target is untrusted input - see
  [`../security/SECURITY.md#ssrf-protection`](../security/SECURITY.md#ssrf-protection)
  for what stops a live-server check from becoming an SSRF proxy.
- No cloned repository's install scripts, postinstall hooks, or declared
  MCP commands are executed as part of scanning - analysis is static
  (source/manifest reading), never "run it and see."
- `excluded_path` marks findings under a fixtures/tests/examples-style
  directory - kept in the report, but excluded from scoring, so a security
  test fixture doesn't tank a real project's grade. This promise depends on
  the finding existing at all: `SemgrepAdapter`/`McpBehaviorAdapter` both
  write an empty `.semgrepignore` into the target before scanning
  (`execution/semgrep_ignore.py`, unless the target already ships its own),
  because Semgrep's own default ignore patterns otherwise silently skip
  any path containing a directory literally named `tests` - a real gap
  found and closed in the same piece of work (`DECISIONS.md` ADR-025/026),
  which would have made a real vulnerability under such a path simply
  never surface for `excluded_path` to act on.

## Limitations (stated, not hidden)

- Runtime/dynamic MCP behavior is not tested - a tool's declared
  description and manifest are analyzed; what the tool actually does when
  invoked at runtime is not exercised.
- A scan is a snapshot. A dependency graded clean today can have a new CVE
  published tomorrow; see the marketplace's rescan-on-evidence model in
  [`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md) for how staleness is handled
  there specifically.
- Detection confidence below `high`/`medium` means MCP-specific findings
  may be incomplete for that target, and the API/CLI report says so via
  `mcp_detection_confidence` and `mcp_detection_evidence` rather than
  silently running the same analysis regardless (see Data, above, for
  where this is and isn't surfaced yet).

## Testing

`backend/scanner-core/tests/` - adapters, pipeline reliability/fallback,
MCP detection (including the underscore-boundary and repository-naming
regression tests), grading, rug-pull, EPSS/KEV, network safety. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`../architecture/DATA_FLOWS.md`](../architecture/DATA_FLOWS.md),
[`AGENT_POSTURE.md`](AGENT_POSTURE.md) (posture reads real scan grades for
servers an agent can call), [`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md).
