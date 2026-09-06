# MCP scanning

How Aevrin decides whether an MCP server is safe to install.

## Purpose

Aevrin answers one question: *if I let my agent use this MCP server, what can
it do to me?*

The thing being assessed is the **running server**, not the repository that
happens to contain its source. A repository is only ever a way of finding out
which server to start. That distinction is the whole architecture: a
repository can be MIT-licensed, well tested and beautifully documented while
the package it publishes exposes a tool that runs arbitrary shell commands,
and only one of those facts matters when the agent calls the tool.

## User workflow

| Surface | Entry point |
|---|---|
| Dashboard | New scan → GitHub URL or live server |
| CLI | `aevrin scan <target>`, or `aevrin scan mcp "npx -y @playwright/mcp"` |
| Claude Code hook | `PreToolUse`, via the cached grade |
| Marketplace | Admin-triggered scan of a catalogued listing |

Every one of these produces the same findings, the same grade and the same
policy for the same server. They are invocation channels, not separate
engines; `Scan.invocation_channel` records which was used, and it never
changes the result.

## Architecture

```
target
  ↓  resolving     work out the command that starts this server
  ↓  launching     start it, in a container that assumes it is hostile
  ↓  enumerating   complete the MCP handshake and read its tools
  ↓  analyzing     run the rules over those tool definitions
  ↓  grading       roll per-tool verdicts up, write the summary
Scan
```

Five stages, because those are the five things that actually happen. The
previous seven existed because seven different tools ran over a cloned
repository.

A scan that stops early stops **at a named stage with a reason attached**. It
is never completed-with-zero-findings, because that is indistinguishable from
a clean server. See [Failure is a result](#failure-is-a-result).

## The engine

The security engine is the [ToolTrust Scanner](https://github.com/AgentSafe-AI/tooltrust-scanner),
pinned by version and SHA-256 and executed as a subprocess inside the sandbox
container. Aevrin does not decide what is a vulnerability, how severe it is,
or what grade a tool earns.

`mcp/tooltrust.py` is the whole integration. It runs one command:

```
mcp-scanner scan --server "<command>" --output json
```

and turns `policies[]` into `Finding` objects. Nothing about a severity, a
rule id, a score or a grade is adjusted on the way through.

There is no second grader, no second risk model, and no severity-weight table
anywhere in this repository. See `DECISIONS.md` ADR-033 and
`backend/scanner-core/EXTERNAL_SCANNERS.md`.

### What Aevrin adds, and why the engine cannot

Four gaps, none of which involve re-deciding what the engine found:

**A server-level grade.** The engine grades per tool. Its only roll-up is
`summary.avg_grade`, and that average cannot be shown to anyone. On a real
run, a five-tool server whose `run_shell` tool carried a Critical
tool-poisoning finding summarised as `avg_grade: A` - four unremarkable tools
outvoted it. You install the whole server, so the **worst tool** decides the
grade, taken from the engine unchanged.

**Prose.** A finding arrives with `rule_id`, `severity`, `code`,
`description`, `location` and `evidence`, and nothing that says why it matters
or what to change. `mcp/catalog.py` supplies the title, impact and fix, keyed
by rule id. A rule id the catalogue does not recognise still produces a
finding using the engine's own description - dropping a real finding for want
of a title would mean an engine upgrade quietly reduced coverage.

**Target resolution.** The engine takes a command. Turning a GitHub URL into
one is Aevrin's job. See [Resolution](#resolution).

**Grouping.** AS-014 fires on every tool that exposes no dependency
inventory, which on a 24-tool server is 24 identical Info cards.
`classification/grouping.py` folds one rule's identical verdict into a single
card carrying every affected tool. Criticals are never grouped: a critical is
read individually, by name.

## Resolution

`mcp/resolve.py` turns a target into a launch command, in this order:

1. An explicit command from the user (`aevrin scan mcp "..."`). Being told
   how to start a server is better evidence than inferring it.
2. `package.json` — `name` plus a `bin`, giving `npx -y <name>`.
3. `pyproject.toml` — `name` plus `[project.scripts]`, giving `uvx <name>`.
4. Otherwise: **refuse**, with a reason that goes into the scan's incomplete
   message.

**The command is never derived from the repository name.** This is the
load-bearing rule of the whole file.
`https://github.com/microsoft/playwright-mcp` publishes as `@playwright/mcp`;
its `bin` is what is called `playwright-mcp`. A *different* package named
`playwright-mcp` exists on npm, by a different author, last touched months
earlier. Guessing from the slug would install that one, scan it, and
attribute the grade to Microsoft — and the scan would succeed while the
report looked entirely normal. That is precisely the impersonation the
engine's own typosquatting rule exists to catch.

A package name becomes a command argument, so shell-shaped names, private
packages, libraries with no entry point, and the names of runtimes (`npx`,
`node`, `uvx`) are rejected outright rather than escaped.

Unresolvable targets are common and legitimate: remote-only servers, servers
that need credentials to start, and anything never published. A confident
wrong answer from a security tool is worse than an honest refusal.

## The sandbox

Enumerating a server's tools requires **starting** it, which means executing
code chosen by whoever published the package — and npm runs that publisher's
`preinstall`/`postinstall` scripts before any scanning begins.

The API process holds the Supabase service-role key, which bypasses RLS and
is therefore the entire tenancy boundary. So the server runs in a one-shot
sibling container with:

- no Aevrin environment (`env` is an explicit allow-list)
- a read-only rootfs, with `nosuid` tmpfs scratch
- uid 10002, every capability dropped, `no-new-privileges`
- memory, CPU and pid ceilings, and a hard wall-clock timeout
- no bind mounts, and `--rm`

Two things this does not solve, stated rather than glossed:

- **Network egress cannot be removed** — the package has to be downloaded. On
  the deployed host, EC2 IMDSv2 with `HttpPutResponseHopLimit=1` is what
  refuses a request from behind Docker's NAT. That is a deployment
  precondition, not something this code enforces.
- **`noexec` is not set** on the tmpfs mounts, because npx installs shim
  scripts into its prefix and execs them. Isolation comes from the container
  holding no credentials and being destroyed, not from that mount option.

There is no non-Docker fallback. An unavailable sandbox is an unavailable
scan, never a scan performed without one. See `DECISIONS.md` ADR-034 and
`backend/scanner-image/Dockerfile`.

## Risk, grade, and policy

The engine assigns a risk score (0-100, higher is worse) and an A-F grade per
tool. Aevrin displays the worst tool's.

| Grade | Policy |
|---|---|
| A, B | `ALLOW` |
| C, D | `REQUIRE_APPROVAL` |
| F | `BLOCK` |
| *(none)* | `REQUIRE_APPROVAL` |

**A missing grade is a state, not a default.** A scan that could not launch
the server, or that launched it and got no tools, is `INCOMPLETE` and carries
no letter — a grade is a claim about evidence, and there is none. It is never
`ALLOW`: nothing was established, so the only honest recommendation is that a
human look.

`mcp/risk.py` turns that verdict into the report's five-part summary
(headline, explanation, potential impact, recommended action, suggested
policy). It chooses wording and policy; it does not compute a score.

## Failure is a result

| What happened | Stage | Result |
|---|---|---|
| No published, executable package | `resolving` | `INCOMPLETE`, no grade |
| Package will not install, or the server will not start | `launching` | `INCOMPLETE`, no grade |
| Server started, returned no tools | `enumerating` | `INCOMPLETE`, no grade |
| Engine output unreadable | `analyzing` | `INCOMPLETE`, no grade |

Every one carries a reason. "Scan incomplete" with no explanation is not
actionable, and every path is pinned in
`backend/scanner-core/tests/test_pipeline_honesty.py`.

## A scan always ends

A scan row is only ever advanced by the worker that owns it, so once that
worker stops the row must be in a terminal state. Three things enforce that,
because a scan stuck at `running` is the one failure mode a user cannot act on:

- writes that decide the outcome raise instead of being logged and swallowed
  (`WriteRejected`);
- the worker reads the row back in a `finally` and forces `failed` if it is
  still open;
- `POST /scans/{id}/cancel` ends it by hand, and
  `POST /scheduler/reap-stuck-scans` sweeps ones whose worker is gone.

A cancelled or reaped scan is `failed` with no grade and no score. See
`DECISIONS.md` ADR-042.

## Data

A scan row records what was assessed and what produced the assessment:
`risk_score`, `grade`, `mcp_tools_declared`, `server_command`,
`scanner_name`, `scanner_version`, `invocation_channel`, `unreliable_stages`.

`server_command` is the one that matters most for support: a grade attributed
to the wrong package is the failure resolution exists to prevent, and this is
where it stays visible after the fact.

Findings carry `rule_id`, `evidence`, `affected_tools` and `occurrence_count`.
The prose is read from the catalogue at render time, so rewording a rule never
requires rewriting stored findings.

## Limitations (stated, not hidden)

- **Only servers that can be started can be graded.** A server needing API
  keys, a browser, or a private registry is reported as unassessed.
- **A grade describes one version at one moment.** Reinstalling later can get
  different code; Aevrin no longer tracks tool-set drift between scans.
- **Static tool definitions, not runtime behaviour.** The rules read what a
  tool declares. A tool that declares nothing alarming and behaves badly at
  call time is not caught by this.
- **The engine's own coverage is the ceiling.** AS-004 supply-chain checks
  need the server to expose `metadata.dependencies` or a `repo_url`; most do
  not, which is why AS-014 (Info) appears so often.
- **A CLI upload is client-reported.** The API cannot recompute a grade,
  because recomputing means launching the server. Two refusals still apply,
  and neither one scores anything - both compare the client's claims against
  the client's own evidence: a grade with no enumerated tools is refused, and
  so is an ALLOW-band letter (A/B) submitted alongside a Critical or High
  finding. A client that under-reports its findings *and* its grade
  consistently is not caught; closing that needs a signed attestation or a
  server-side rescan, and neither exists.

## Testing

| File | Covers |
|---|---|
| `tests/test_tooltrust_normalisation.py` | Engine JSON → findings, against real recorded output |
| `tests/test_target_resolution.py` | Manifest-driven resolution, and every refusal |
| `tests/test_sandbox_isolation.py` | The `docker run` argv: no credentials, no mounts, limits, timeout |
| `tests/test_pipeline_honesty.py` | Every failure path ends ungraded |
| `tests/fixtures/scanner/*.json` | Real engine output, captured by running it |

The fixtures are genuine scanner output rather than hand-written examples. A
normaliser tested against its author's idea of the format keeps passing after
the format moves.

## Related docs

- `backend/scanner-core/EXTERNAL_SCANNERS.md` — provenance and licence
- `DECISIONS.md` ADR-033 to ADR-036
- `docs/security/SECURITY.md` — the sandbox in the wider security model
- `docs/architecture/DEPLOYMENT.md` — the scanner image and IMDSv2
