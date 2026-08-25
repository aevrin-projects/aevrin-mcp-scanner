# External scanner provenance

The dependency record required before any third-party scanner is integrated.
One row per candidate, recording what it is, what its licence permits, and how
Aevrin is allowed to use it.

Verified 2026-08-26 against the GitHub licence API and each repository's own
files. Re-verify before adding a scanner or changing how one is consumed;
a licence can change between releases.

## Candidates

| Project | Licence | Language | Verified | Integration verdict |
|---|---|---|---|---|
| [snyk/agent-scan](https://github.com/snyk/agent-scan) | Apache-2.0 | Python | API + README | External executable only |
| [L3G5/mcp-scan](https://github.com/L3G5/mcp-scan) | Apache-2.0 | Python | API | External executable; overlaps existing coverage |
| [affaan-m/agentshield](https://github.com/affaan-m/agentshield) | MIT | — | API | Reference; adaptation permitted with attribution |
| [aiconnai/agentshield](https://github.com/aiconnai/agentshield) | MIT **or** Apache-2.0 (dual) | Rust | `LICENSE-MIT` + `LICENSE-APACHE` present | External executable; adaptation permitted |

None are copyleft. Nothing here forces Aevrin's own source to be
redistributed, and every one of them can be shelled out to. Adapting code
into Aevrin is permitted for all four, but requires preserving the original
copyright notice and licence text — Apache-2.0 additionally requires stating
what was changed.

## snyk/agent-scan — read this before depending on it

The README states plainly:

> Agent Scan is closed to contributions.
> Agent Scan does not accept external contributions at this time.

Pull requests are technically enabled on the repository, which contradicts
the README at a glance. The README is the operative statement: treat this as
a vendored tool that cannot be influenced, not a base to build on. Bugs go to
their issue tracker and may never be fixed on our schedule.

Consequences for how Aevrin uses it:

- Invoke it as a pinned executable (`uvx snyk-agent-scan@<version>`), never
  import it and never fork it as a collaborative base.
- **Pin the version.** Its JSON schema has already changed shape between
  releases: v0.5.x emits path-keyed `ScanPathResult`, v0.6+ emits
  `scan_path_responses`. An unpinned dependency here silently changes the
  meaning of parsed output.
- The adapter owns that schema difference. Nothing above the adapter should
  know which version produced a result.

## Rules these findings impose

1. Aevrin's normalised finding model stays canonical. A third-party result is
   converted at the adapter boundary and never rendered raw.
2. Every finding records `source_scanner` and `source_version`. A scanner that
   did not run is reported as unavailable, never as a clean result — the same
   rule the MCP scanner already applies to incomplete coverage.
3. Agreement between scanners is a confidence signal, not a count. Three
   scanners reporting one underlying issue is one risk detected three times.
4. Adding a scanner means adding a row here first, with the licence checked
   against its repository rather than assumed from a previous entry.
