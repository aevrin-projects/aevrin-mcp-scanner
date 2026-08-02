# aevrin-web

Next.js 16 (App Router) website: Screens 1–4 of the master build spec (new scan, scan progress, results dashboard, finding detail), Supabase Auth (magic link), talks to `apps/api`.

Built against Next.js 16.2.12, which has real breaking changes from older Next versions (`middleware.ts` → `src/proxy.ts`, async `params`/`searchParams`, Turbopack by default) — see `node_modules/next/dist/docs/01-app/02-guides/upgrading/version-16.md` before assuming older-Next patterns still apply.

## Run locally

```bash
cp .env.local.example .env.local   # already has real Supabase URL/publishable key checked in as example values
npm install
npm run dev
```

Requires `apps/api` running locally too (defaults to `http://localhost:8000`).

## Test / lint / build

```bash
npx eslint .
npx tsc --noEmit
npm run build
```

## Structure

- `src/lib/supabase/{client,server,proxy}.ts` — Supabase SSR client setup (current `@supabase/ssr` pattern, verified against live Supabase docs for this Next.js version).
- `src/lib/api.ts` — typed fetch client for `apps/api`, attaches the Supabase access token as a Bearer header.
- `src/app/page.tsx` — Screen 1 (new scan).
- `src/app/scans/[id]/` — Screens 2+3 (progress → results, same URL, polls every 2s).
- `src/app/scans/[id]/findings/[findingId]/` — Screen 4 (finding detail + triage).
- Severity colors (`--severity-critical/high/medium/low` in `globals.css`) are dedicated tokens, not reused destructive/primary colors, so severity is visually meaningful nowhere else in the UI.
