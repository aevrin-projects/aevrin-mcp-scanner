# Writing standards

Observed from this codebase's actual UI copy, error messages, code
comments, and `frontend/content/` docs - not a generic style guide. Match
what's already here.

## Tone

Direct and specific. "Your login has expired or was revoked. Run
`aevrin login` again." - not "Something went wrong." An error message
names what happened and what to do about it
(`backend/cli/aevrin_cli/main.py`'s `output.print_error` calls are the
reference examples). No marketing language in product copy that describes
what something *is* or *does* - reserve enthusiasm for the actual public
marketing pages (`app/page.tsx`, `app/pricing/page.tsx`), never for a
dashboard state, an error, or a security finding.

## No emoji, ever

Not in code, not in UI copy, not in documentation, not as a status
indicator. Status is conveyed by label, color, and icon component
(`lucide-react` / the project's `BrandIcon`/`thesvg` wrapper for a missing
icon), never by an emoji character standing in for one.

## No em dashes

Use a hyphen ("-"), a comma, a colon, or a rephrased sentence instead -
whichever reads most naturally for the specific clause. Never an em dash
character, in documentation, UI copy, or code comments. This was corrected
after review: earlier engineering documentation in this repository used em
dashes routinely, on the mistaken assumption that existing content set the
house style; that content has since been rewritten, and no new writing
should reintroduce the character.

## Precision over hedging

State what's true plainly, and state uncertainty plainly too - this
codebase's own comments do both constantly ("an unreadable config
initially scored 74 against 32 for a fully-known permissive one" is a
precise claim about a real bug, not a vague "there was an issue"). Avoid
words that sound careful but say nothing ("may", "in some cases",
"generally") unless the uncertainty is the actual point being made (e.g.
"an unknown always counts against a grade, never for it" - that's a
precise statement *about* uncertainty, which is different from hedging).

## Security-critical distinctions are named explicitly, not implied

This is the most important local convention, and it shows up everywhere in
the product's own copy: "Verified finding" vs. "AI explanation." "GitHub
stars" vs. "users." "Not yet scanned" vs. "safe." "Partial coverage" vs.
"clean." When writing UI copy or documentation that touches a security
claim, name the distinction the same way the product already does - don't
invent a new phrasing for a concept that already has one.

## Terminology consistency

Use the vocabulary the code itself uses, not a paraphrase:

- **Finding**, not "issue" or "alert" (matches `Finding` the model).
- **Severity** (`critical`/`high`/`medium`/`low`/`info`), not "priority."
- **Trust grade** (A-F) for a scan's letter (the registry carries none),
  and **risk score** for the 0-100 number beside it, which counts up: 0 is
  clean, 100 is "do not use". The two are always shown together, never one
  standing in for the other. Agent posture has no letter: it is a **safety
  score** (0-100, higher is safer) and a **risk level** (low to critical).
- **OWASP MCP Top 10** category codes (`MCP01`-`MCP10`) with their full
  title on first reference in a document, code alone thereafter.
- **Workspace**, not "team" or "organization," in user-facing copy - even
  though the database table is literally `organizations` (that's schema
  history, not the product's vocabulary; see
  `frontend/src/views/workspace/`).

These are the terms for engineering documents, code, and technical
details. Dashboard copy a non-specialist reads first uses the plain words
below.

## Plain language on the dashboard

The scan result, finding, agent, rule, attack path, skill and device pages
are read by people who are not security engineers. Their first layer of
copy is written so an eight-year-old could follow it: short sentences,
everyday words, and every unavoidable technical word explained in the same
sentence. The exact technical data is never removed to get there. It sits
under a **Technical details** disclosure (`shared/ui/technical-details.tsx`)
on the same screen: simple first, technical second, never simple instead.

Plain text restates what the scanner established; it never softens it,
generalises it, or adds a claim of its own. So it is written beside the
data it describes, not in a separate copy of it:

- A finding's four answers (what is wrong, why it matters, what could
  happen, what to do) live in the rule catalogue (`mcp/catalog.py`,
  `PlainText`), next to the technical `impact` and `fix`.
- A posture deduction's everyday sentence lives beside its technical
  reason in `agents/posture.py` (`PostureFactor.plain`).
- What a rule does is built from the access discovery recorded for it
  (`PermissionOut.grants`), never from reading the rule's wording.
- The agent vocabulary is in one file, `entities/agent/model/labels.ts`,
  and finding severity and status meanings in
  `entities/finding/model/plain.ts`.

| Technical term | Plain word on the dashboard |
|---|---|
| Effective capabilities | What this agent can reach |
| Permission rules | Rules that give the agent access |
| Capability names | Read files, Change files, Run commands, Use the internet, Use MCP tools |
| Levels (none, ask, limited, full, unknown) | No, Only if you say yes, Some, Everything, Could not tell |
| Effect (allow, ask, deny) | Gives access, Asks you first, Limits or blocks |
| Agent posture score | Safety score (higher is safer) |
| Security posture | Overall safety |
| Finding | Problem found |
| Severity | How serious |
| Evidence | What we found |
| Affected tools | Tools with the problem |
| Potential impact | What could happen? |
| Recommended action / remediation | What should I do? |
| Coverage | What we could check |
| Triage status (open, fixed, false positive) | Not fixed yet, Fixed, Not a real problem |
| Unattended | Does not ask you before it acts |
| Credentials | Passwords and keys |
| Device | Computer |

"deny" is "Limits or blocks", not "Blocks": Codex records a sandbox that
narrows access (`sandbox_mode = workspace-write`) as a deny, and "Blocks"
would overstate it.

AI explanations follow the same standard (see
[`../features/AI_REVIEW.md`](../features/AI_REVIEW.md)).

## Tables for structured reference, prose for reasoning

A tier limit, an environment variable, a route list, a permission
catalogue - a table. Why a decision was made, what a security boundary
protects against, what a feature deliberately doesn't do - prose. Don't
force a table where the content is actually an argument, and don't write
a paragraph where a table would let someone scan it in five seconds.

## Code comments

Default to none. Write one only when the *why* isn't obvious from
well-named code: a hidden constraint, a bug it fixed, a decision that
looks wrong until you know the reason. This codebase's existing comments
are the model to match - most of them cite a concrete failure mode or
regression rather than restating what the next line does.
