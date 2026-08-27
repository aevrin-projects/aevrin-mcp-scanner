# MCP tool usage

Two different things share the name "MCP" in this document, and it matters
which one is meant: the **Model Context Protocol** is Aevrin's product
domain (what it scans); the **MCP servers listed below** are tools
available to an AI agent working on this repository. Don't confuse a
finding about a scanned server with a decision about which tool to use
while coding.

## What's actually configured

`.mcp.json` at the repository root registers exactly one project-level MCP
server: **shadcn** (`npx shadcn@latest mcp`), for component lookup.
Beyond that, an agent's host environment (Claude Code, this assistant)
typically also provides Context7, Sequential Thinking, a filesystem
server, and a parallel-search/web tool - available regardless of this
repository's own `.mcp.json`, and listed here because they're what this
project's workflow actually relies on. If a tool named below isn't present
in a given session, fall back to the manual equivalent (Grep/Glob for
filesystem search, reading vendor docs directly for library behavior) -
don't block on a missing tool.

## Decision tree

**A library, framework, or API's current behavior** - FastAPI, Pydantic,
Next.js 16, Supabase (`@supabase/ssr`, `@supabase/supabase-js`), httpx,
Tailwind v4, a provider's REST API (Groq/OpenAI/Anthropic/Gemini),
Cloudflare Workers/OpenNext, Razorpay →
**Context7**. `resolve-library-id` first with the library name and your
actual question, then `query-docs` with the full question (not a single
keyword). Use even when the answer seems obvious - training data goes
stale and this project pins specific versions (`next@16.2.12`,
`fastapi>=0.115`) where behavior has genuinely changed release to release.
Not for: refactoring, debugging this codebase's own business logic, or
general programming concepts Context7 has no special authority over.

**A large or ambiguous change, or planning before touching multiple
files** - a new marketplace field that touches schema + service +
schema-model + route + frontend entity, a scoring-rubric change, anything
where the scope isn't obvious from the first file you open → **Sequential
Thinking**. Break it into ordered steps, surface dependencies and edge
cases, before writing code. This project's own history is full of bugs
that a planning pass would have caught before they shipped (the
underscore-boundary regex bug in `mcp_detection.py`, the docstring-capture
regex bug - both found only after the code was written and tested).

**Where something lives, or whether it already exists** - before adding a
service, a table, a component, a utility → **Grep/Glob**, or a wider
`filesystem`-server sweep for an unfamiliar area. This project's
[anti-overengineering rule](../../CLAUDE.md#anti-overengineering-rules)
depends on actually checking first; skipping this step is how duplicate
functionality gets written.

**Current external facts the codebase can't answer** - UX conventions,
accessibility guidance current as of today, a vendor's current pricing or
rate limits, the current MCP specification text, current security
advisories → **parallel-search** (web_search first; only web_fetch a
specific URL when you need exact wording, or search results conflict).
Never a substitute for reading Aevrin's own source - external research
documents an external contract, not what this codebase does.

**A UI component need** - dialogs, forms, tables, dropdowns, cards →
**shadcn MCP**. Check the registry for an existing primitive, and check
`frontend/src/shared/ui/` first - most of what shadcn would generate
already exists there, composed for this product's design system.

## Pre-feature research protocol

Before implementing a feature that touches a new UI pattern, a new
external API, or a new integration:

1. Grep/Glob for whether something equivalent already exists.
2. Context7 for the current documented behavior of any library/API
   involved.
3. Sequential Thinking to plan the implementation if it touches more than
   one layer.
4. Parallel-search only for what neither of the above can answer (current
   UX convention, a vendor fact not in their API docs).

This isn't a ritual for every one-line fix - a copy change or an obvious
bug fix skips straight to implementation. It's for the class of change
`CLAUDE.md`'s reading-order guidance calls "non-trivial."
