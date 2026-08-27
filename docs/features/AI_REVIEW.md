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
or Google Gemini - the user's own key). "Explain this" appears on a trust
grade ("Why is this grade C?"), an individual finding, a scan result, or a
marketplace listing's security position - never on a decorative element.

## Architecture

`backend/api/aevrin_api/services/ai/`:

- **`evidence.py`** - builds a structured evidence document from a fixed
  allow-list of real fields (findings, grade + factors, declared tools,
  permission types, credential *metadata*, attack paths, coverage). The
  scanner's raw payload never enters it (TruffleHog/Gitleaks put the
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
  contract above, made explicit to the model); caches a response against a
  hash of the *exact* evidence shown; provider fallback is deliberately
  shallow (try the next configured provider in order, stop - no health
  scoring, no silent reordering, because "which vendor saw my
  infrastructure details" needs a predictable answer).
- **`provider_sync.py`** - the weekly model-catalogue refresh (see below).

## Cache correctness

Cached against `evidence_hash()` - a canonical-JSON SHA-256 of the exact
document shown to the model. Two people viewing the same public listing
are asking the identical question and share one answer; evidence built
from a private scan hashes differently by construction, so nothing crosses
a tenant boundary through the cache. A rescan changes the evidence, changes
the hash, and the next reader gets a fresh explanation - there's nothing to
invalidate by hand. A forced rescan additionally clears cached explanations
for that subject.

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
Aevrin's own credential rather than a customer's.

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

`backend/api/tests/services/test_ai_providers.py` (no response model can
carry a key; Gemini's key is never in a URL; output/input caps enforced),
`test_marketplace_hardening.py`'s evidence-redaction and
prompt-injection-bounding tests. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`../security/SECURITY.md`](../security/SECURITY.md),
[`MCP_MARKETPLACE.md`](MCP_MARKETPLACE.md) (a listing's security position
can carry an explanation), `DECISIONS.md` ADR-004 (the LiteLLM decision,
recorded at the time it was made).
