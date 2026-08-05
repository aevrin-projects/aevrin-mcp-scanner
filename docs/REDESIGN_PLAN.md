# Aevrin Full Product Redesign — Working Plan & Context

**Branch:** `redesign/full-product-ui` (branched from `master` @ `6fbba3d`)
**Status:** Phase 2 in progress
**Last updated:** 2026-08-05

This file is the resumable source of truth. If a session ends mid-work, read
this top-to-bottom before touching code — it carries the full context, the
decisions already made, and exactly what is done vs. pending.

---

## 0. Hard constraints (do not violate)

- **No production deploys.** No `railway up`, no Railway env var changes.
- **No `git push`.** No PRs, no merges to `master`.
- **No commits unless the user explicitly asks.** When asked, author as
  `aevrin-projects <underdogs.exe@gmail.com>`, no AI/Claude mentions anywhere
  in the message.
- **No production migrations.** Local/derived state only. (The onboarding
  flow deliberately derives completion from real GitHub installations +
  localStorage rather than adding a DB column, so no migration is needed.)
- Never commit: `docs-personal/`, `strix-design/`, `*.pem`, `env.txt`,
  `githubapp.txt`. All already in `.gitignore`.

## 1. Local run

```bash
# API  — from apps/api
uv run uvicorn aevrin_api.main:app --host 0.0.0.0 --port 8000 --reload

# Web  — from apps/web
npm run dev
```

- Web: http://localhost:3000
- API: http://localhost:8000 (`/health` → `{"status":"ok"}`)

Local env already present at `apps/web/.env.local` and `apps/api/.env`.
`NEXT_PUBLIC_API_URL=http://localhost:8000` locally.

**Test account (created 2026-08-05 via Supabase admin API, pre-confirmed):**

```
qa+redesign@aevrin.net  /  AevrinQA!redesign2026
```

Free tier, id `3f1ac359-1868-493f-b79a-7a96167511c0`, in the **production**
Supabase project `onwijviiwtuwldjmqoam` (there is no separate local DB).
Delete it when the redesign ships.

> ⚠️ **Port 8000 gotcha:** if `/github/status` (or any newer route) 404s
> locally, a *stale* uvicorn from an earlier session is still holding the
> port and `--reload` never picked up new routers. `uv run uvicorn …` prints
> "Address already in use" and exits. Fix:
> `lsof -ti:8000 | xargs kill -9` then restart. This cost real debugging time
> — check it first before assuming a routing bug.

## 2. Design direction (decided with the user)

Reference: `strix-design/` skill (a reverse-engineered capture of strix.ai)
plus two screen recordings the user supplied in `docs-personal/`.

**User's instruction, verbatim intent:** match the theme, colors, and design
language; keep Aevrin's own logo and branding; drop the previous lime/green
accent; adapt the user flow to Aevrin's real features.

**What we match:** palette, density, spacing rhythm, layout patterns, flow
sequence, component style, motion feel.

**What we do NOT copy** (settled — do not re-litigate, and do not add later):
- Their marketing copy verbatim. Aevrin's product is MCP-server security, not
  API pentesting; the copy could not transfer honestly anyway.
- Their testimonial. The captured screenshot names a real person at a real
  company — reproducing it on Aevrin would be a fabricated endorsement.
- Their GitHub star count, customer logos, or any other social proof Aevrin
  has not earned.
- Their name/logo.

> ⚠️ The `strix-design` skill's `DESIGN.md` claims a **light** theme with a
> `#ffffff` background. **That is wrong** — its static analysis misread the
> stylesheet. The real product (and the user's screenshots/recordings) is
> **dark**. Trust the screenshots, not the token dump.

### Token reference (already applied in `apps/web/src/app/globals.css`)

| Role | Value | OKLCH |
|---|---|---|
| Background | `#000000` | `oklch(0 0 0)` |
| Card | `#0a0a0a` | `oklch(0.1448 0 0)` |
| Sidebar | — | `oklch(0.0645 0 0)` |
| Border | `#1a1a1a` | `oklch(0.2178 0 0)` |
| Text | `#fcfdff` | `oklch(0.9939 0.0029 264.54)` |
| Muted text | `#a1a4a5` | `oklch(0.7166 0.0037 219.55)` |
| Accent (links, focus, active nav) | `#79c0ff` | `oklch(0.7857 0.1153 246.66)` |
| Primary CTA | white on black | `oklch(1 0 0)` / `oklch(0 0 0)` |
| Radius | 8px | `--radius: 0.5rem` |

Accent-on-white fails 4.5:1, so light mode uses a darkened sibling
(`oklch(0.55 0.15 246.66)`) for text/links. Dark is the default theme.

### Onboarding flow shape observed in the user's recording

1. Centered card, progress dots top-center, "Back" link top-left.
2. Step: workspace/name setup (single input + Continue).
3. Step: "get started" path selection — 3 cards, each with an icon, a short
   description, a 4–5 item feature list, and its own CTA.
4. Subsequent steps continue the same centered, one-decision-per-screen shape.

**Aevrin adaptation** (Aevrin has no workspace/org model — do **not** invent a
fake "name your workspace" step that stores nothing):
1. Path selection — "Scan a repository" / "Scan a live server or config" /
   "Set up CLI + Claude Code hook". All three map to real existing features.
2. Connect GitHub (skippable, honest about what it unlocks).
3. First scan hand-off → dashboard.

---

## 3. User-reported issues (must all be resolved)

| # | Issue | Status |
|---|---|---|
| 1 | Billing add-on buried at page bottom — undiscoverable | ✅ Fixed — moved directly under plan summary |
| 2 | Fix It buried in sidebar below triage — nobody sees it | ✅ Fixed — now primary action in page header |
| 3 | Must re-auth constantly; `/` shows landing instead of app when signed in | ✅ Fixed — proxy redirects signed-in users `/` and `/login` → `/dashboard` |
| 4 | Repeated sign-outs (refresh-token race) | ✅ Fixed earlier — proxy is now the single `getClaims()` caller |
| 5 | Icons should match the reference set | ⬜ Pending — Phase 4 |
| 6 | Whole user flow feels unconsidered | 🔄 In progress — Phases 2–3 |
| 7 | CLI bugs (sync, version) | ⬜ Pending — Phase 6 |
| 8 | Docs need word-by-word verification | ⬜ Pending — Phase 7 |
| 9 | Backend: live server, MCP config, PR flow review | ⬜ Pending — Phase 6 |

---

## 4. Phases

Each phase ends with: `npx tsc --noEmit`, `npm run build`, and a live
Playwright pass at **1440 / 1024 / 390** with the console checked. Do not mark
a phase done until its verification column actually passed.

### ✅ Phase 1 — Design foundation (DONE)
- Dark-first token system in `globals.css`; `defaultTheme="dark"`.
- Removed hardcoded lime gradient in `app/page.tsx`.
- `MetricCard` densified with optional `suffix`.
- Sidebar: compact nav rows, account/plan header, real tier badge.
- **Verified:** build clean, 0 console errors, landing + pricing at desktop/mobile.

### ✅ Phase 2 — Onboarding wizard (CODE DONE, VISUAL VERIFY PENDING)
- [x] `/onboarding` route + guard; all 4 sign-in entry points redirect there.
- [x] Skip-for-now, derived completion (no migration).
- [x] True multi-step wizard: progress dots, Back, Skip, path selection
      (3 cards), conditional GitHub step, completion hand-off.
- [x] GitHub step only appears for the repository path — nobody is asked for
      repo access to check a pasted config.
- [ ] Verify each step at 3 widths + keyboard nav. **Blocked:** needs a real
      test account to get past the auth gate.

### ✅ Phase 2b — Billing add-ons (DONE)
Dedicated "Add-ons" card, placed directly under the plan summary (was buried
at page bottom — the user's explicit complaint). Lists all four:
- Auto-fix PRs (+10 / $4) — **functional**
- BYOK (+$3/mo) — **functional**, shows Active / Purchased-needs-key state
- Extra scan credits (Hobby +25/$4, Pro +100/$10) — **honestly marked "Not
  available yet"** with a disabled control. Backend not built: needs bonus
  scan counters on `accounts` + a checkout path, i.e. a schema migration,
  which the no-prod-migration constraint currently forbids.
- GitHub connection — **functional**, shows connected account.

### ✅ Phase 3 — Dashboard + landing (DONE)
- [x] Stat row (5-up), top findings, top affected targets, severity breakdown
      — all real data, no fabricated charts.
- [x] First-use dashboard: stateful 3-step setup checklist (account / connect
      GitHub / first scan) driven by real `getGithubStatus()`, replacing the
      generic card wall. Verified live at 1440 and 390.
- [x] Dashboard layout rebuilt on one consistent grid rhythm (was 5-col →
      3-col → 1.4/0.92fr → full-width with three different card styles, which
      read as "randomly placed"). Now: one stat strip, then every row on the
      same 3-column grid.
- [x] Stat strip: five borderless cells sharing one bordered container with
      hairline dividers, container-query responsive. Five separate bordered
      cards read as five unrelated widgets and wrapped raggedly at mid widths.
- [x] `MethodologySection` added to the landing (`components/methodology-
      section.tsx`): OWASP MCP Top 10 mapping, the eight real scanner names +
      what each does, an honest coverage-by-target-type matrix, and the six
      real pipeline stages. All from actual product constants
      (`OWASP_CATEGORY_LABELS`, `STAGE_ORDER`, `STAGE_LABELS`) — no invented
      capability claims, and the matrix states plainly what *cannot* be
      covered for live-server and pasted-config targets.

**Seeded QA data** (production Supabase, delete with the test account):
3 scans + 10 findings + 18 stage rows for `qa+redesign@aevrin.net`, covering
complete / partial(failed-stage) / skipped-stage cases so the populated
dashboard and its coverage math can actually be seen. Scan ids:
`767effae…`, `6424a836…`, `2bd163f4…`.

### ✅ Phase 4 — Component + icon consistency (DONE)
- Icons were already clean: lucide-only, inline `<svg>` limited to the four
  brand marks lucide doesn't ship (Google, GitHub, LinkedIn, YouTube).
- **Real problem was radius**: 47 `rounded-2xl` + 13 `rounded-3xl` + 1
  `rounded-4xl` vs only 14 `rounded-xl`. The base `Card` component already
  standardises on `rounded-xl`, so every large radius was an ad-hoc override
  fighting the component default — this is why new sections looked unlike the
  legacy pages. Normalised across 15 files → 75 `rounded-xl`, zero competing
  values. Arbitrary `rounded-[28px]`-style hero art left intentionally alone.

### ✅ Phase 5 — Route QA (public + key authed routes DONE)
- All 10 public routes return correct codes; 404 genuinely 404s;
  `/integrations` correctly 307s when signed out.
- Signed in as the QA account and walked dashboard, scan history, scan
  detail, pricing, login. **Console clean on every route.**
- Remaining: `/scans/new`, `/settings/api-keys`, `/device`, `/docs` deep
  pages, and a 1024px pass.

### ✅ Phase 5b — Landing page redesign (DONE)
Full rewrite of `app/page.tsx` plus new `components/result-preview-section.tsx`.
- Hero: single-column centred. Dropped the giant "AEVRIN" wordmark (already
  in the navbar, ate ~200px of vertical space) and the mock product panel,
  which competed with the real output now shown below it.
- New "The risk" section: four concrete MCP failure modes, each tagged with
  the real OWASP category the scanner checks — replaces the abstract "why
  teams adopt it" / "questions users ask" copy blocks.
- New `ResultPreviewSection`: a finding card using the product's real field
  shape (tool, category, severity, file:line, why, remediation, Fix It) beside
  a real CLI transcript with the actual command and output format.
- "Honest coverage" gets its own section — it's the genuine differentiator.
- Section order now: hero → risk → real result → honest coverage →
  methodology → pricing → install → footer.
- No fabricated social proof anywhere: no customer logos, star counts,
  testimonials, or invented metrics.

### ✅ Phase 6 — CLI + backend (DONE)
**All 236 tests pass** (scanner-core 115, CLI 23, API 101).

**Shipped bug found and fixed — CLI-breaking version desync.** `0.1.9` had
*two different contents*: commit `5f57640` shipped scanner-core 0.1.9, then
`a1e8258` added new public API (`is_autofix_eligible`, `FIXABLE_TOOLS`,
`ADAPTER_BY_TOOL`) **without bumping the version**. Meanwhile `output.py`
imports `is_autofix_eligible` while `pyproject.toml` declared only
`aevrin-scanner-core>=0.1.8`. A real `pipx install aevrin` resolving 0.1.8 or
published-0.1.9 gets **ImportError at startup** — the CLI dies, it doesn't
degrade. Invisible locally because `[tool.uv.sources]` uses an editable
workspace path, so dev and CI always get the newest code.

Fix: scanner-core → **0.1.10**, CLI → **0.1.11**, floor → `>=0.1.10`.
Plus `packages/cli/tests/test_dependency_contract.py` (3 tests) guarding the
whole class: declared floor ≥ workspace version, every imported symbol
resolves in its *originating module* (submodule-aware), and the specific
autofix symbols exist. **Verified the guard actually fails on the old floor**
(`(0,1,8) >= (0,1,10)` → False) rather than trusting it passes.

### ✅ Phase 7 — Docs verification (DONE)
Checked docs against the live `tier_limits` table, not against memory.

- `concepts.mdx` tier table was **missing Pro entirely** and claimed Team was
  "Unlimited" scans. Corrected against real DB values and added the auto-fix
  PR column: Free 5/2/5 · Hobby 50/20/50 · Pro 200/100/200 (1yr, 15 PRs) ·
  Team usage-based (unlimited history, 15 PRs/seat).
- `api.mdx` + `reports.mdx` said PDF export was "Hobby/Team only" — **Pro
  customers would read that and think they don't get a feature they pay
  for.** Now "Hobby, Pro, and Team".
- **`aevrin fix` was shipped with zero documentation.** Added a full `cli.mdx`
  section covering the generate → re-verify → draft-PR flow, the
  allowance-decrement-only-on-success rule, ineligible finding types, the
  `autofix_eligible` JSON field, and the GitHub prerequisite.

### ⬜ Phase 8 — Accessibility + performance
- WCAG 2.2 AA: keyboard-only, visible focus, landmarks, labels, contrast,
  200% zoom, reduced motion, non-color severity indicators.
- LCP ≤ 2.5s, INP ≤ 200ms, CLS ≤ 0.1.

---

## 4b. Bugs found by live testing (signed in as the QA account)

All found by actually clicking through, not by reading code:

| Bug | Fix |
|---|---|
| Marketing navbar stacked on top of `/onboarding` — double header, plus escape links that drop people out of setup | `BARE_ROUTE_PREFIXES` in `layout-chrome.tsx`; onboarding renders chrome-free |
| `Button render={<Link/>}` threw a Base UI a11y error — non-native element stripped button semantics | Added `nativeButton={false}` at all 11 call sites |
| Usage meter labels collided at narrow widths — rendered `Dashboard0 / 5` | `gap-3`, `truncate`, `shrink-0 tabular-nums` on the count |
| `capitalize` mangled "CLI scans" → "Cli Scans" | Explicit labels in `BUCKET_LABEL`, dropped the utility class |
| Add-ons hidden entirely from Free users — undiscoverable | Always rendered; unavailable ones show "Requires Pro" + upgrade path |
| Usage meters crushed to `CLI s… Hook … Dash…` inside the dashboard's ~360px sidebar column — `lg:grid-cols-4` fires on *viewport* width, ignoring the actual container | Switched to Tailwind container queries (`@container` on the wrapper, `@md:`/`@3xl:` on the inner grid) so the grid only widens when the box genuinely has room |

## 5. Change log (this branch)

| File | Change |
|---|---|
| `app/globals.css` | Dark-first token system; strix palette in OKLCH |
| `app/layout.tsx` | `defaultTheme="dark"`, system following off |
| `app/page.tsx` | Lime gradient → accent blue |
| `app/onboarding/page.tsx` | **New** — GitHub connect step |
| `app/dashboard/page.tsx` | Stat row + 3-card insight row (real data) |
| `components/product-ui.tsx` | `MetricCard` density + `suffix` |
| `components/authenticated-app-shell.tsx` | Sidebar density, plan badge, drawer fix |
| `lib/supabase/proxy.ts` | Single `getClaims()`; signed-in `/`→`/dashboard` |
| `app/login/actions.ts`, `auth/callback`, `auth/confirm` | Redirect → `/onboarding` |
| `scans/[id]/findings/[findingId]/finding-detail-client.tsx` | Fix It → header |
| `settings/billing/page.tsx` | Auto-fix section moved up |
| `components/dashboard-charts.tsx` | **New** — score gauge, severity trend bars, donut (hand-rolled SVG, no chart lib) |
| `components/usage-bucket-meta.tsx` | **New** — one shared label/icon/hue per usage bucket, plus state-color rule |
| `components/auth-preview-visual.tsx` | **New** — sample scan result for the split auth page |
| `app/login/page.tsx` | Split screen: form left, product visual right |
| `components/install-docs-section.tsx` | Prompt walls → 4-step overview + Copy, full text behind a disclosure |
| `components/hero-scan-visual.tsx` | Language text marks → threat-class icons |
| `app/usage/page.tsx`, `settings/billing/page.tsx`, `components/usage-meters.tsx` | Per-bucket color, real bars, credit-split chart |

### Phase 5c — Dashboard visual redesign (DONE)

Driven by "all the containers are just randomly placed" and "use graphs
wherever needed, bold colours, subtle animations".

- **One 3-column rhythm for the whole page.** Every row is 2+1 or a full-width
  span on the same tracks. The old page mixed 5-col, 3-col and
  `1.4fr/0.92fr` — inconsistent track counts are what read as "scattered",
  not the individual cards.
- **Three real charts**, all hand-rolled SVG/CSS: a 270° score gauge colored
  by risk band, a stacked severity-per-scan bar chart on a labelled scale, and
  an open-findings donut. No charting library — ~90kB for three shapes we
  fully control isn't a trade worth making.
- **Color now carries meaning.** Severity colors on findings; per-bucket hues
  on usage that are overridden by amber/red as a meter nears its limit.
- **Motion is one-shot and quiet**: `panel-rise` staggers the grid on mount,
  bars grow, the gauge sweeps. Nothing loops — this is a page people read.
  All of it collapses to a static end state under `prefers-reduced-motion`.

Two things were deliberately **removed** during this pass:
- A sparkline on the "Targets" stat that plotted severity counts. A chart
  whose shape has nothing to do with its label is worse than no chart.
- The idea of a headline "vulnerabilities caught" number on the auth page —
  that's a claim about Aevrin's track record we can't substantiate, so it
  shows a representative scan result instead.

## 6. Known gaps / honest limitations

- Auth-gated routes are **unverified visually** — no test account exists yet.
  Everything behind `/login` has been type-checked and build-verified but not
  seen rendered. This is the single biggest verification hole.
- No fabricated charts anywhere. Score-over-time and open-vs-fixed trends are
  *possible* from real data (scan history + `triage_status`) but are not yet
  built; do not add decorative ones.
- Anthropic API key has **no credit balance** — Fix It fails closed and
  Pro/Team routed triage silently falls back to Gemini. Not a code bug.
- `GITHUB_APP_PRIVATE_KEY` is set in production only; local `.env` may lack
  it, so local Fix It will report "not configured".
