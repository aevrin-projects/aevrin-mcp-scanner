# Agent posture

**Status: implemented** (Claude Code and Codex discovery; posture scoring;
attack paths). Other agent adapters: **planned**, not built - see
`ROADMAP.md`.

## Purpose

Answer "how much can the AI coding agents on this machine already do" -
separately from "does this MCP server have problems," because they're
different questions with different consequences. See the four-numbers
distinction documented directly in `scanner-core/agents/posture.py`:

| Number | Question | Computed by |
|---|---|---|
| MCP scan score | How many problems does this server have | `classification/scoring.py` |
| MCP trust grade | Should I let this server run | `agents/grade.py` |
| Agent posture | How much can this agent already do on this machine | `agents/posture.py` |
| Blast radius | What does misuse reach | Part of posture, surfaced as its own deduction factors |

## User workflow

`aevrin agent scan [--project .] [--json] [--verbose] [--upload]` - reads
local configuration only (Claude Code `settings.json`, managed settings,
`.mcp.json`; Codex `config.toml`). Nothing is executed and no agent is
started. Local-only by default; `--upload` sends a posture snapshot to the
dashboard, and even then it carries no credential values - only
credential *metadata*. The dashboard's Agents / Devices / Skills /
Permissions / Attack paths views (`frontend/src/views/agents/`,
`attack-paths/`, `permissions/`, `skills/`, `devices/`) render whatever's
been uploaded.

## Architecture

`scanner-core/agents/`: `claude_code.py` and `codex.py` discover
per-vendor configuration; `common.py`/`identity.py`/`models.py` hold the
shared `Capability`/`Level`/`DiscoveredAgent` shapes; `posture.py` computes
the score; `grade.py` converts it to a letter alongside the MCP trust
grade; `attack_paths.py` derives concrete "agent X can reach credential Y
via capability Z" chains from the same discovered data, rather than a
separate analysis pass.

The per-server MCP trust grade shown alongside a configured agent
(`api/controllers/agent_controller.py::_trust_by_identity`) is matched by
identity against a `live_mcp_server` scan of the same target, never
against a source-repository scan of it. `Scan.mcp_capabilities` for that
scan now comes from `analysis/remote_mcp.py::inspect_remote_signatures` -
the same live `list_tools()` handshake that already produced the rug-pull
signature hash also feeds `capability_summary()` (ADR-022), so an
execute-capable live server is graded on real, established evidence rather
than carrying a permanent "could not be established" penalty
(`UNKNOWN_CAPABILITY_WEIGHT`, ADR-021) purely because no source repository
was ever read. That penalty still applies, correctly, when the live
handshake itself fails (network error, protocol error) - a target that
genuinely could not be checked stays distinguishable from one confirmed
clean, the same rule the rest of this rubric already follows.

## Scoring

Deterministic: start at 100, deduct named amounts, and every deduction
carries the sentence that earned it - never a black-box number. Two rules
override the arithmetic rather than averaging into it:

- **`UNATTENDED` (-15)**: no human confirmation in front of anything the
  agent does. The single largest non-capability deduction - it doesn't add
  a capability, it removes the check on every capability already granted.
- **`CREDENTIALS_WITH_SHELL` (+15 deduction)**: a credential reachable by
  an agent that can also run commands. The blast-radius principle made
  concrete - the credential alone isn't the risk; the combination is.

Capability deductions (`SHELL_FULL` 15, `WRITE_FULL` 10, `NETWORK_FULL`
10, `READ_FULL` 3, and `_LIMITED` variants at roughly a third of the full
cost) are named constants specifically so the rubric can be read and
argued with in one place, not buried in conditionals.

**An unreadable capability costs what its worst plausible grant would
have cost - never less.** This is the rule the module's own docstring
calls out as catching a real bug: an unreadable configuration initially
scored *better* (74) than a fully-known permissive one (32), rewarding
opacity over transparency. `UNKNOWN_CAPABILITY_COST` fixes this by
charging the worst-case cost for anything that couldn't be established,
with a `UNKNOWN_CAPABILITY_DEFAULT` for anything not in that table.

A server this agent can call that was independently graded `D` costs 20;
graded `C` costs 8 - but only from a **real** grade. An unscanned server
contributes nothing to this deduction and is accounted for separately as
missing evidence, never assumed safe or assumed risky by default.

## Data

`AgentSnapshot` (Supabase table `agent_snapshots`, migration
`0029_agent_snapshots.sql`) is the uploaded unit. Deleting an agent
(`DELETE /agents/{id}`) requires the `agents.delete` permission.

## Security

Credential metadata carries kind/source/presence, never a value - see
[`../security/SECURITY.md`](../security/SECURITY.md). Tenant isolation on
agent snapshots is covered by
`backend/api/tests/controllers/test_agent_tenant_isolation.py`.

## Limitations (stated, not hidden)

- Discovery covers Claude Code and Codex specifically. A different agent
  or IDE extension with its own configuration format isn't recognized
  today - see `ROADMAP.md`.
- Discovery is config-based, the same as MCP-server detection: it reads
  what's declared, not what the agent has actually done at runtime. An
  agent that's been granted a capability but never used it, and one that's
  used it constantly, score identically.
- Posture reflects the machine it was run on at the moment it was run -
  it's a snapshot, not a continuously monitored value, unless re-run.

## Testing

`backend/scanner-core/tests/test_agent_posture_risk.py`,
`test_attack_paths.py`, `test_claude_code_discovery.py`,
`test_codex_discovery.py`, `test_mcp_identity.py`. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`MCP_SCANNING.md`](MCP_SCANNING.md) (the "grade a called server" input to
posture), [`../reference/CLI.md`](../reference/CLI.md#aevrin-agent-scan).
