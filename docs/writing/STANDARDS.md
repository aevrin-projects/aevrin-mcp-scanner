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
- **Trust grade** (A/B/C/D) for the marketplace/agent-posture letter,
  **security score** for the 0-100 number underneath it - the two are
  always shown together, never one standing in for the other.
- **OWASP MCP Top 10** category codes (`MCP01`-`MCP10`) with their full
  title on first reference in a document, code alone thereafter.
- **Workspace**, not "team" or "organization," in user-facing copy - even
  though the database table is literally `organizations` (that's schema
  history, not the product's vocabulary; see
  `frontend/src/views/workspace/`).

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
