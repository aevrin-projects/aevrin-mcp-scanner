-- The MCP marketplace: a security-aware catalogue built on top of the
-- official MCP Registry.
--
-- Three ideas decide this schema, and everything else follows from them.
--
-- 1. The official registry is upstream metadata, not our data. We ingest it
--    and enrich it; we never fork it. `registry_name` is the upstream
--    identity (reverse-DNS, e.g. io.github.user/weather) and is what makes a
--    re-sync an update rather than a duplicate. It is nullable, because an
--    admin or a user may list a server the registry has never heard of.
--
-- 2. Security belongs to a *version*, never to a listing. A grade earned by
--    v1.4.2 says nothing about v1.5.0. That is why versions are their own
--    table and the listing carries no score of its own: there is nowhere to
--    write a number that would outlive the evidence for it.
--
-- 3. A scan is referenced, never copied. mcp_listing_versions.scan_id points
--    at the same public.scans row the dashboard, the CLI and the hook read.
--    One scan, one set of findings, every surface reading the same evidence.
--
-- Popularity lives on the listing as plain columns rather than in a table of
-- its own: it is one row per listing, always read with the listing, and
-- always overwritten wholesale by the metadata refresh. A separate table
-- would be a join that never returns a different number of rows.

-- --------------------------------------------------------------------------
-- Categories
--
-- A table rather than a bare enum so the marketplace can list them with
-- counts and an admin can add one without a migration. Deliberately not a
-- taxonomy service: a listing carries category slugs in a text[], and this
-- table is the display name and ordering for those slugs.

create table if not exists public.mcp_categories (
  slug text primary key check (slug ~ '^[a-z0-9-]+$'),
  name text not null,
  description text,
  sort_order int not null default 100,
  created_at timestamptz not null default now()
);

insert into public.mcp_categories (slug, name, sort_order) values
  ('developer-tools', 'Developer Tools', 10),
  ('databases',       'Databases',       20),
  ('cloud',           'Cloud',           30),
  ('search',          'Search',          40),
  ('productivity',    'Productivity',    50),
  ('communication',   'Communication',   60),
  ('business',        'Business',        70),
  ('finance',         'Finance',         80),
  ('analytics',       'Analytics',       90),
  ('devops',          'DevOps',         100),
  ('security',        'Security',       110),
  ('browser-web',     'Browser / Web',  120),
  ('files-storage',   'Files / Storage',130),
  ('marketing',       'Marketing',      140),
  ('ai-ml',           'AI / ML',        150),
  ('research',        'Research',       160),
  ('other',           'Other',          999)
on conflict (slug) do update set name = excluded.name, sort_order = excluded.sort_order;

-- --------------------------------------------------------------------------
-- Listings

create table if not exists public.mcp_listings (
  id uuid primary key default gen_random_uuid(),

  -- Upstream identity. Unique when present, so a re-sync updates in place.
  registry_name text unique,
  -- Where this listing came from. Provenance is shown, never hidden.
  source text not null default 'registry'
    check (source in ('registry', 'admin', 'user_submission')),

  -- server.json carries `name` (reverse-DNS) and an optional `title`. Slug is
  -- ours: a stable, readable URL segment.
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]*$'),
  title text not null check (length(trim(title)) between 1 and 120),
  description text not null default '',
  -- The publisher's own README, kept for the detail page. Rendered as text,
  -- never as HTML: it is attacker-controlled content.
  readme text,

  repository_url text,
  homepage_url text,
  -- The upstream registry entry, when there is one.
  registry_url text,
  publisher text,
  -- The MCP publisher's licence, e.g. 'MIT'. Nothing to do with the licence
  -- of Aevrin's own dependencies.
  license text,

  categories text[] not null default '{}',
  tags text[] not null default '{}',

  -- Free / paid. Aevrin processes no money for third-party servers; the most
  -- this ever does is link out to the publisher.
  price_type text not null default 'unknown'
    check (price_type in ('free', 'freemium', 'paid', 'open_source', 'commercial', 'unknown')),
  price_amount numeric(12,2),
  price_currency text check (price_currency is null or price_currency ~ '^[A-Z]{3}$'),
  billing_period text check (billing_period is null or billing_period in ('month', 'year', 'once', 'usage')),
  pricing_url text,

  -- Which agents this can actually be installed into, derived from the
  -- server's own package/transport metadata. Never assumed.
  install_targets text[] not null default '{}',
  -- The normalised installation recipe (packages[], remotes[]) as ingested.
  -- A document because it is passed through to the client verbatim and never
  -- queried by field.
  installation jsonb not null default '{}'::jsonb,

  -- Popularity signals, each labelled as what it is. Null means "not
  -- available", which is never rendered as zero.
  github_stars int,
  github_forks int,
  github_open_issues int,
  github_last_commit_at timestamptz,
  github_latest_release text,
  github_default_branch text,
  github_language text,
  github_created_at timestamptz,
  github_metadata_updated_at timestamptz,
  npm_downloads_last_month int,
  pypi_downloads_last_month int,
  marketplace_views int not null default 0,
  favorite_count int not null default 0,

  -- Deterministic ranking. Recomputed by the sync job; the weights live in
  -- the API so they can be changed without a migration.
  ranking_score numeric(6,2) not null default 0,

  -- Moderation and reach.
  status text not null default 'draft'
    check (status in ('draft', 'submitted', 'scanning', 'review', 'approved', 'rejected', 'published', 'suspended')),
  visibility text not null default 'public'
    check (visibility in ('public', 'private', 'unlisted')),
  featured boolean not null default false,
  -- Set only for visibility='private': an organisation's own internal server,
  -- which the official registry has no way to hold.
  org_id uuid references public.organizations (id) on delete cascade,
  created_by uuid references auth.users (id) on delete set null,

  -- Mirrors server.json's own version field: the newest version we know of,
  -- which is NOT necessarily the version that was scanned.
  latest_version text,
  registry_updated_at timestamptz,

  -- A maintained projection of the newest *scanned* row in
  -- mcp_listing_versions. Denormalised for one reason only: sorting and
  -- filtering the catalogue by security without a per-row join.
  --
  -- Written exclusively by services/marketplace/grading.py, immediately after
  -- it writes the version row these values are copied from. Nothing else may
  -- set them, and nothing may set them by hand.
  --
  -- `current_version` is the load-bearing column: it records which version
  -- the grade actually belongs to. When it differs from latest_version the
  -- scan is stale, and the UI must present it as stale rather than applying
  -- an old letter to a new release.
  current_version text,
  current_trust_grade text check (current_trust_grade is null or current_trust_grade in ('A', 'B', 'C', 'D')),
  current_security_score int check (current_security_score is null or current_security_score between 0 and 100),
  current_coverage_complete boolean,
  current_scanned_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- A private listing without an owning organisation would be invisible to
  -- everyone, including its author. A public listing with one implies a
  -- tenancy that public browsing does not honour.
  constraint mcp_listings_private_has_org check (
    (visibility = 'private' and org_id is not null)
    or (visibility <> 'private' and org_id is null)
  )
);

create index if not exists mcp_listings_status_idx on public.mcp_listings (status, visibility);
create index if not exists mcp_listings_ranking_idx on public.mcp_listings (ranking_score desc);
create index if not exists mcp_listings_org_idx on public.mcp_listings (org_id) where org_id is not null;
create index if not exists mcp_listings_categories_idx on public.mcp_listings using gin (categories);
create index if not exists mcp_listings_tags_idx on public.mcp_listings using gin (tags);
create index if not exists mcp_listings_updated_idx on public.mcp_listings (registry_updated_at desc nulls last);
-- Sorting by security. Ordered so that A sorts first and unscanned sorts
-- last: 'D' < 'A' alphabetically, so the letter alone would put high-risk
-- servers at the top of a "most secure" list.
create index if not exists mcp_listings_grade_idx on public.mcp_listings (current_trust_grade, current_security_score desc);

-- array_to_string() is marked STABLE, not IMMUTABLE, in Postgres (a
-- consequence of its polymorphic anyarray signature, not of anything it
-- actually depends on for text[] with a text separator). A generated
-- column requires every function in its expression to be IMMUTABLE, so
-- the wrapper below re-declares the same call as immutable -- the
-- standard, Postgres-documented way around this specific limitation.
create or replace function public.immutable_array_to_string(text[], text)
returns text
language sql
immutable
parallel safe
as $$ select array_to_string($1, $2) $$;

-- Full-text search across the fields the marketplace searches. A generated
-- column rather than an expression index so the same vector is used for
-- ranking and for matching, and so the weights (title beats description
-- beats tags) are declared once here instead of in every query.
alter table public.mcp_listings
  add column if not exists search_vector tsvector
  generated always as (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(publisher, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('english', public.immutable_array_to_string(coalesce(tags, '{}'), ' ')), 'C') ||
    setweight(to_tsvector('english', public.immutable_array_to_string(coalesce(categories, '{}'), ' ')), 'C')
  ) stored;

create index if not exists mcp_listings_search_idx on public.mcp_listings using gin (search_vector);

-- --------------------------------------------------------------------------
-- Versions: where security actually lives
--
-- One row per version we have seen. `scan_id` references the canonical Aevrin
-- scan; grade/score/coverage are denormalised from it so the marketplace can
-- sort and filter without joining findings, but they are written only by the
-- code that reads that scan, never by hand.

create table if not exists public.mcp_listing_versions (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.mcp_listings (id) on delete cascade,
  version text not null,

  -- Whatever pins this version's source: a commit SHA, a package integrity
  -- hash, or server.json's fileSha256. Null means we could not establish one,
  -- which is why a rescan cannot be skipped on the strength of it.
  source_hash text,
  package_registry text,
  package_identifier text,

  scan_id uuid references public.scans (id) on delete set null,
  -- 'A' | 'B' | 'C' | 'D', from aevrin_scanner_core.agents.grade.
  trust_grade text check (trust_grade is null or trust_grade in ('A', 'B', 'C', 'D')),
  security_score int check (security_score is null or security_score between 0 and 100),
  -- False when a core scanner stage did not run. An empty finding list from a
  -- stage that never executed is not a clean result, and the UI must not
  -- render it as one.
  coverage_complete boolean,
  -- Per-surface sub-grades, so a user can see which part earned the overall
  -- letter.
  code_score int,
  mcp_score int,
  dependency_score int,
  -- Which tool versions produced this. Provenance for the grade.
  scanner_versions jsonb not null default '{}'::jsonb,
  scan_status text,
  scanned_at timestamptz,
  first_seen_at timestamptz not null default now(),

  unique (listing_id, version)
);

create index if not exists mcp_listing_versions_listing_idx
  on public.mcp_listing_versions (listing_id, first_seen_at desc);

-- --------------------------------------------------------------------------
-- Submissions, reports, events, favourites

create table if not exists public.mcp_submissions (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid references public.mcp_listings (id) on delete set null,
  submitted_by uuid not null references auth.users (id) on delete cascade,
  org_id uuid references public.organizations (id) on delete set null,
  -- What the submitter actually pasted.
  source_url text not null,
  note text,
  status text not null default 'submitted'
    check (status in ('draft', 'submitted', 'scanning', 'review', 'approved', 'rejected', 'published')),
  -- Why an admin decided what they decided. Shown to the submitter.
  review_reason text,
  reviewed_by uuid references auth.users (id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists mcp_submissions_status_idx on public.mcp_submissions (status, created_at desc);
create index if not exists mcp_submissions_user_idx on public.mcp_submissions (submitted_by, created_at desc);

create table if not exists public.mcp_reports (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.mcp_listings (id) on delete cascade,
  reporter_id uuid references auth.users (id) on delete set null,
  kind text not null check (kind in ('listing', 'security')),
  reason text not null,
  description text,
  status text not null default 'open' check (status in ('open', 'reviewing', 'dismissed', 'actioned')),
  resolution_note text,
  resolved_by uuid references auth.users (id) on delete set null,
  resolved_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists mcp_reports_status_idx on public.mcp_reports (status, created_at desc);
create index if not exists mcp_reports_listing_idx on public.mcp_reports (listing_id);

-- Every change worth telling someone about: a new version, a grade that
-- moved, an admin override. One table, because these are all the same shape
-- and are always read together as a timeline.
create table if not exists public.mcp_events (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid references public.mcp_listings (id) on delete cascade,
  event_type text not null check (event_type in (
    'listing_added', 'listing_updated', 'version_added', 'source_changed',
    'scan_completed', 'grade_changed', 'popularity_changed',
    'admin_override', 'status_changed', 'report_actioned'
  )),
  -- Free-form on purpose: 'B' -> 'D' for a grade, a category list for an
  -- override. Rendered as text, never interpreted.
  old_value text,
  new_value text,
  reason text,
  -- Null for anything the sync job did on its own.
  actor_id uuid references auth.users (id) on delete set null,
  severity text not null default 'info' check (severity in ('info', 'warning', 'critical')),
  created_at timestamptz not null default now()
);

create index if not exists mcp_events_listing_idx on public.mcp_events (listing_id, created_at desc);
create index if not exists mcp_events_type_idx on public.mcp_events (event_type, created_at desc);

create table if not exists public.mcp_favorites (
  user_id uuid not null references auth.users (id) on delete cascade,
  listing_id uuid not null references public.mcp_listings (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, listing_id)
);

-- --------------------------------------------------------------------------
-- Organisation policy
--
-- Structured rules, not a DSL: what to do at each grade.

create table if not exists public.org_mcp_policies (
  org_id uuid primary key references public.organizations (id) on delete cascade,
  -- Exactly four keys, each one of allow | require_approval | block.
  grade_actions jsonb not null default
    '{"A":"allow","B":"allow","C":"require_approval","D":"block"}'::jsonb,
  -- Unscanned is its own case: it is not a grade, and defaulting it to
  -- "allow" would make "we have no evidence" the safest-looking state.
  unscanned_action text not null default 'require_approval'
    check (unscanned_action in ('allow', 'require_approval', 'block')),
  updated_by uuid references auth.users (id) on delete set null,
  updated_at timestamptz not null default now()
);

-- --------------------------------------------------------------------------
-- Row-level security
--
-- Reads are public for published public listings, because a marketplace that
-- needs a login to browse is not a marketplace. Everything else is scoped.
-- Every write goes through the API's service role.

alter table public.mcp_categories enable row level security;
alter table public.mcp_listings enable row level security;
alter table public.mcp_listing_versions enable row level security;
alter table public.mcp_submissions enable row level security;
alter table public.mcp_reports enable row level security;
alter table public.mcp_events enable row level security;
alter table public.mcp_favorites enable row level security;
alter table public.org_mcp_policies enable row level security;

create policy mcp_categories_public_select on public.mcp_categories
  for select to authenticated, anon using (true);

-- Published + public to everyone; private only to the owning organisation.
-- 'unlisted' is readable but excluded from listing queries by the API, which
-- is what unlisted means: reachable by link, absent from the index.
create policy mcp_listings_public_select on public.mcp_listings
  for select to authenticated, anon
  using (visibility in ('public', 'unlisted') and status = 'published');

create policy mcp_listings_org_select on public.mcp_listings
  for select to authenticated
  using (org_id is not null and public.is_org_member(org_id));

-- A submitter can always see their own listing, whatever state it is in.
create policy mcp_listings_author_select on public.mcp_listings
  for select to authenticated
  using (created_by = (select auth.uid()));

create policy mcp_listing_versions_select on public.mcp_listing_versions
  for select to authenticated, anon
  using (exists (
    select 1 from public.mcp_listings l
    where l.id = listing_id
      and (
        (l.visibility in ('public', 'unlisted') and l.status = 'published')
        or (l.org_id is not null and public.is_org_member(l.org_id))
        or l.created_by = (select auth.uid())
      )
  ));

create policy mcp_events_select on public.mcp_events
  for select to authenticated, anon
  using (exists (
    select 1 from public.mcp_listings l
    where l.id = listing_id
      and l.visibility = 'public' and l.status = 'published'
  ));

create policy mcp_submissions_own_select on public.mcp_submissions
  for select to authenticated using (submitted_by = (select auth.uid()));

create policy mcp_reports_own_select on public.mcp_reports
  for select to authenticated using (reporter_id = (select auth.uid()));

create policy mcp_favorites_own on public.mcp_favorites
  for select to authenticated using (user_id = (select auth.uid()));

create policy org_mcp_policies_member_select on public.org_mcp_policies
  for select to authenticated using (public.is_org_member(org_id));

-- --------------------------------------------------------------------------
-- Marketplace entitlements
--
-- Added to the existing tier_limits config table rather than a new billing
-- concept. Null means unlimited, matching every other column here.

alter table public.tier_limits add column if not exists ai_explanations_per_month int default 0;
alter table public.tier_limits add column if not exists private_mcp_listings int default 0;
alter table public.tier_limits add column if not exists marketplace_policies boolean not null default false;

update public.tier_limits set ai_explanations_per_month = 20,   private_mcp_listings = 0,    marketplace_policies = false where tier = 'free';
update public.tier_limits set ai_explanations_per_month = 300,  private_mcp_listings = 10,   marketplace_policies = false where tier = 'hobby';
update public.tier_limits set ai_explanations_per_month = null, private_mcp_listings = null, marketplace_policies = true  where tier = 'team';

-- --------------------------------------------------------------------------
-- Counters
--
-- Both of these are maintained in the database rather than in the API, for
-- the same reason: they are read-modify-write on a hot row, and doing that in
-- application code loses increments whenever two requests overlap.

create or replace function public.increment_listing_views(p_listing_id uuid)
returns void
language sql
security definer
set search_path = public
as $$
  update public.mcp_listings
     set marketplace_views = marketplace_views + 1
   where id = p_listing_id;
$$;

revoke all on function public.increment_listing_views(uuid) from public, anon;
grant execute on function public.increment_listing_views(uuid) to authenticated, service_role;

-- favorite_count follows the mcp_favorites table exactly, so it cannot drift
-- from the rows it counts.
create or replace function public.sync_favorite_count()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'INSERT' then
    update public.mcp_listings
       set favorite_count = favorite_count + 1
     where id = new.listing_id;
    return new;
  else
    update public.mcp_listings
       set favorite_count = greatest(favorite_count - 1, 0)
     where id = old.listing_id;
    return old;
  end if;
end;
$$;

drop trigger if exists mcp_favorites_count_insert on public.mcp_favorites;
create trigger mcp_favorites_count_insert after insert on public.mcp_favorites
  for each row execute function public.sync_favorite_count();

drop trigger if exists mcp_favorites_count_delete on public.mcp_favorites;
create trigger mcp_favorites_count_delete after delete on public.mcp_favorites
  for each row execute function public.sync_favorite_count();

comment on table public.mcp_listings is
  'Marketplace catalogue. Security never lives here: it lives on mcp_listing_versions, which references a real scan.';
comment on column public.mcp_listings.github_stars is
  'Stars. Not users, not installs, not a security signal.';
