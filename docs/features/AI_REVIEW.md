# AI review (explanations)

**Status: implemented.** Optional - every scan and every grade is complete
and correct with no AI provider configured.

User-facing product documentation:
`frontend/content/(ai)/{providers,explanations}.mdx` (published at
`docs.mcp.aevrin.net`). This document covers the engineering structure and
the guarantees behind those user-facing claims.

## Purpose

Turn a security finding into plain language. **Interpretation, never
detection.** The scanners decide what's true; the model explains it. This
single sentence is the contract the rest of the feature is built to
enforce structurally, not just by policy.

## User workflow

Configure a provider at Settings → AI providers (Groq, OpenAI, Anthropic,
or Google Gemini - the user's own key). "Explain with AI" appears on a scan
result, next to its grade ("Why is this grade C?", subject `scan`), on
an individual finding (subject `finding`), and on an agent next to its
safety score ("Why is this agent high risk?", subject `agent_posture`) -
never on a decorative element.
Both are scans the caller may read: `ai_controller._owned_scan` reads the
scan, and its findings, through `membership.ReadScope`, so it allows the
scan's creator or a current member of the workspace it is stamped with and
answers 404 otherwise. It is the same scope the scans API reads through,
and the scan id is never taken as proof of access. An agent's evidence is
read through `agent_controller.get_agent`, the same call and the same
`ReadScope` the agent page uses, so the explanation can never describe an
agent the page would not show the caller, and it explains the same score
the page shows. It carries the posture deductions with their points, each
capability with the rule text that granted it, the rules as written,
credential kinds and presence, skill names, coverage, and the score, risk
level and confidence. It leaves out every file path (a home directory
names a person) and every credential location.

The registry has no explanation. Before `DECISIONS.md` ADR-049 a listing's
grade could be explained (subjects `trust_grade` and `listing`); the
registry no longer carries a grade, so those subjects were removed and
migration `0049` deletes their cached rows and narrows the
`ai_explanations.subject_type` check.

## Architecture

`backend/api/aevrin_api/services/ai/`:

- **`evidence.py`** - builds a structured evidence document from a fixed
  allow-list of real fields (findings, grade + factors, declared tools,
  permission types, credential *metadata*, attack paths, coverage). The
  scanner's raw payload never enters it (it can carry the
  secret they found directly in `raw`). Every credential-shaped string is
  stripped even from fields that "shouldn't" contain one. Free-text fields
  are length-bounded. An absent section is *omitted*, not sent as an empty
  list - `[]` for "no attack paths exist" and `[]` for "attack paths
  weren't part of this question" read identically to a model, and only
  the first is a safety claim.
- **`credentials.py`** - Fernet-encrypted storage, decrypted only
  in-process at call time. `public_view()` is an allow-list (key present +
  last four characters), not a deny-list that could accidentally grow a
  leak.
- **`explain.py`** - the system prompt carries five numbered rules (the
  contract above, made explicit to the model, including that it never
  states a different grade, score, severity or risk level and never adds,
  removes or softens a finding) and asks for everyday words a reader with
  no security background can follow, the dashboard's plain-language
  standard (`docs/writing/STANDARDS.md`); caches a response against a
  hash of the *exact* evidence shown; provider fallback is deliberately
  shallow (try the next configured provider in order, stop - no health
  scoring, no silent reordering, because "which vendor saw my
  infrastructure details" needs a predictable answer).
- **`provider_sync.py`** - the weekly model-catalogue refresh (see below).

## Cache correctness

Cached against `evidence_hash()` - a canonical-JSON SHA-256 of the exact
document shown to the model, plus whether the long form was asked for and
`PROMPT_VERSION`. The version is bumped whenever the system prompt changes
what an answer says or how it says it; without it, a rewritten prompt
would keep serving every answer cached under the old one. Two members of a workspace viewing the same
scan are asking the identical question and share one answer; evidence built
from a different scan hashes differently by construction, so nothing crosses
a tenant boundary through the cache. A rescan is a new scan with new
evidence, so the next reader gets a fresh explanation - there's nothing to
invalidate by hand.

## Model catalogue

A weekly job (`POST /scheduler/provider-sync`) asks each provider for its
current model list, using **Aevrin's own catalogue credentials**
(`GROQ_CATALOG_API_KEY`, etc.) - never a customer's key, and this is a
deliberate correction to an initial assumption that a model list could be
fetched anonymously: all four providers require a credential to list
models, so borrowing a customer's key for Aevrin's own bookkeeping would
have billed them for it. Withdrawn models are marked, **never deleted** -
an existing cached explanation references the model that produced it, and
that reference must keep resolving. A failed sync keeps the previous
catalogue rather than emptying the dropdown.

**Saving a provider key also refreshes that provider's catalogue, using the
key just saved.** The weekly job still never touches a customer credential;
this is the opposite situation, and the distinction is the point. A
scheduled poll on Aevrin's behalf would bill a customer for Aevrin's
bookkeeping and leak which vendors Aevrin polls into their usage dashboard.
A refresh triggered by that customer, with their key, to populate the
dropdown they are looking at, does none of those things - it happens once,
at their request, for their benefit. The model names it learns are public
catalogue facts about the vendor, not the customer's data, which is why they
can be written to the shared catalogue at all.

This exists because the weekly job is only as good as its credential, and
this deployment has never had one: with no `*_CATALOG_API_KEY` set,
`ai_provider_models` stayed empty, so "add a provider, then choose a model"
dead-ended with an empty dropdown and no explanation. The refresh is
best-effort and never fails the save - the credential is stored either way,
and a vendor being briefly unreachable must not read as a rejected key.

## Provider APIs

Called with the user's own credential, from the backend only. No vendor
SDK is installed for any of them; each is plain HTTP against the vendor's
documented REST endpoint, in `integrations/ai_providers.py`.

| Provider | Model list endpoint | Auth | Documentation |
|---|---|---|---|
| Groq | `GET https://api.groq.com/openai/v1/models` | `Authorization: Bearer` | console.groq.com/docs/models |
| OpenAI | `GET https://api.openai.com/v1/models` | `Authorization: Bearer` | platform.openai.com/docs/models |
| Anthropic | `GET https://api.anthropic.com/v1/models` | `x-api-key` + `anthropic-version` | docs.claude.com/en/docs/about-claude/models |
| Google Gemini | `GET https://generativelanguage.googleapis.com/v1beta/models` | `x-goog-api-key` | ai.google.dev/gemini-api/docs/models |

Two facts cost real time to establish and are recorded here so they don't
have to be rediscovered: Gemini's OpenAI-compatibility shim
(`/v1beta/openai/models`) does not serve a working model list under
API-key auth - it answers 401, so the native `v1beta` endpoint is used
instead. And the key is sent as a header on every provider, including
Gemini, never as a `?key=` query parameter - query strings end up in
access logs and referrer headers, and a credential must not.

**Every one of these four endpoints requires a credential.** There is no
anonymous model list, which is why the weekly catalogue sync (above) uses
Aevrin's own credential rather than a customer's - and why, when no such
credential is configured, the only key available to populate the catalogue
at all is the one the customer just saved.

**Reasoning models.** GPT-OSS on Groq (`openai/gpt-oss-*`) reasons before
it answers, and the reasoning counts against the same output budget
(console.groq.com/docs/reasoning). `complete` sends it `reasoning_effort:
"low"` and `include_reasoning: false`: an explanation of structured
evidence needs little reasoning, and the reasoning text is never shown or
stored. When any provider stops at its output limit with no answer
(`finish_reason: length`, Anthropic's `stop_reason: max_tokens`, Gemini's
`finishReason: MAX_TOKENS`), the reason says so and points at Max tokens
in Settings, AI Providers, rather than "empty response".

### Why LiteLLM was evaluated and not adopted

LiteLLM's licence is acceptable (MIT outside `enterprise/`, which Aevrin
would not touch), but it was rejected on weight rather than licence. The
actual need is two HTTP calls - list models, complete a prompt - against
four vendors, three of which already share a wire format. LiteLLM brings a
large transitive dependency tree, its own retry/caching/routing behaviour,
and a fast release cadence, all of which would sit directly in the path of
a security product's explanation feature and would need tracking for
their own vulnerabilities. `integrations/ai_providers.py` implements the
same surface in one readable module whose only dependency, httpx, already
existed - the vendor differences live in a table rather than in branches.

This decision is reversible (see `DECISIONS.md` ADR-004): if Aevrin ever
needs many more providers, streaming, or per-model cost accounting,
LiteLLM becomes the right answer, and the current adapter interface is
narrow enough to swap behind without touching every call site.

## Pricing claims

Aevrin does not state that any provider is free. Free tiers, rate limits,
and developer allowances change without notice, and a security tool that
told a user an API was free when it had started charging would have
caused a real problem for no benefit. The UI shows the provider, the
model, and that the credential is user-supplied, and links to the
vendor's own pricing page rather than asserting a cost.

## Cost and failure control

- Hard ceiling on output tokens (`MAX_OUTPUT_TOKENS_CEILING`) and input
  size (`MAX_INPUT_CHARS`), independent of what a user configures.
- Identical evidence is never paid for twice (the cache).
- **No provider configured, or every provider unreachable, is HTTP 200
  with `available: false` - never a 500.** An AI-layer failure rendered
  the same as a scanner failure would make an unrelated outage look like a
  security-scanning problem, which is the one confusion this product
  cannot afford anywhere.
- **Every failure the button shows says what happened.** A reason from the
  API (no provider, a key the vendor rejected, an output limit) is shown
  as given, with a link to the provider settings when that is where the
  fix is, and a retry. A request the API refused is told apart by status:
  401 sign in, 402 plan limit, 404 nothing to explain any more, 429 too
  many requests, any other 4xx "reload and try again", and only a network
  failure or a 5xx is "unavailable right now". A failed "Explain more"
  keeps the explanation already shown. Until 2026-09-29 every failure was
  one generic sentence, and it hid that `POST /ai/explain` declared its
  body as `body: Any`, which FastAPI reads as a required query parameter:
  every request was refused with 422 before any code ran, so no
  explanation had ever been produced in production.

## Prompt injection

Covered in full in
[`../security/SECURITY.md#prompt-injection`](../security/SECURITY.md#prompt-injection) -
the short version: a hostile tool description or README is data under a
named key, bounded in length, read by a model with no tools and no write
access, so the worst outcome is a misleading sentence next to a finding
that stays unchanged.

## Limitations (stated, not hidden)

- No provider guarantees zero cost - Aevrin makes no claim about what any
  provider charges; free tiers and rate limits change without notice, and
  a security tool that told a user an API was free when it started
  charging would have caused a real problem for no benefit.
- Fallback is intentionally shallow - it will not automatically route
  around a vendor that's degraded but still nominally responding.
- An explanation is only as good as the evidence built for it; it does not
  see anything the evidence document excludes by design (raw scanner
  output, source code, environment variables, the full conversation).

## Testing

`backend/api/tests/controllers/test_agent_explanation.py` (an agent the
caller cannot read is not found, through the route too; the deductions in
the evidence add up to the page's score; no path or credential location
leaves; a new prompt version is a new cache key),
`backend/api/tests/routes/test_ai_explain_route.py` posts real JSON
through the app (the layer the `body: Any` bug lived in, which the older
tests called past), `backend/api/tests/services/test_ai_providers.py` (no
response model can carry a key; Gemini's key is never in a URL;
output/input caps enforced; GPT-OSS reasons at low effort; an answer cut
off by the output limit says how to fix it),
`test_marketplace_hardening.py`'s evidence-redaction and
prompt-injection-bounding tests. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`../security/SECURITY.md`](../security/SECURITY.md),
[`MCP_SCANNING.md`](MCP_SCANNING.md) (the scan and finding being
explained), `DECISIONS.md` ADR-004 (the LiteLLM decision,
recorded at the time it was made).
