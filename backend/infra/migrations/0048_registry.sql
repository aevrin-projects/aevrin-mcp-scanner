-- The marketplace becomes the Aevrin Registry: an admin-curated catalogue of
-- every kind of capability an agent can use, not only MCP servers.
--
-- EXPAND-ONLY. Every statement adds or widens; nothing the currently deployed
-- API reads is removed or renamed. Apply this BEFORE deploying the build that
-- uses it - the reverse order is the one that fails (see 0047's header for
-- what that looked like). The /health gate lists `item_type` and `content`,
-- so a deploy against a database without this migration rolls back rather
-- than shipping.
--
-- One table, not a second one beside it. `mcp_listings` already has
-- everything a registry needs - full-text search, versions, an events
-- timeline, favourites, categories, visibility and tenancy, RLS - and a
-- parallel `registry_items` table would be a second source of truth for the
-- same catalogue with the same search, which is exactly what the registry must
-- not have. The name is now narrower than the contents; renaming it would
-- touch every query for no change in behaviour. See DECISIONS.md.
--
-- Security still belongs to a version, and only an MCP server has a scanner.
-- Every other item type carries no grade, and the API reports its security
-- state as "not applicable" rather than letting an empty grade read as clean.

-- ------------------------------------------------------------ item types
--
-- The kinds of thing the registry holds. A check rather than an enum type,
-- consistent with every other status column here, so adding a type later is a
-- constraint swap rather than an `alter type` that cannot run in a
-- transaction.
alter table public.mcp_listings
  add column if not exists item_type text not null default 'mcp_server';

alter table public.mcp_listings drop constraint if exists mcp_listings_item_type_check;
alter table public.mcp_listings add constraint mcp_listings_item_type_check
  check (item_type in (
    'mcp_server', 'skill', 'prompt', 'tool', 'agent', 'component', 'template',
    'workflow', 'library', 'cli', 'backend', 'frontend', 'infrastructure',
    'product', 'repository', 'integration', 'dataset', 'documentation', 'other'
  ));

create index if not exists mcp_listings_item_type_idx
  on public.mcp_listings (item_type, status, visibility);

-- --------------------------------------------------------------- metadata
--
-- `publisher` already names the organisation; `author` is the person. The
-- three arrays are what an agent filters on when it searches by intent - "a
-- skill for AWS deployment" is item_type + technologies + use_cases - so they
-- are columns with GIN indexes rather than keys inside a document.
alter table public.mcp_listings add column if not exists author text;
alter table public.mcp_listings add column if not exists repository_ref text;
alter table public.mcp_listings add column if not exists technologies text[] not null default '{}';
alter table public.mcp_listings add column if not exists capabilities text[] not null default '{}';
alter table public.mcp_listings add column if not exists use_cases text[] not null default '{}';

create index if not exists mcp_listings_technologies_idx on public.mcp_listings using gin (technologies);
create index if not exists mcp_listings_capabilities_idx on public.mcp_listings using gin (capabilities);
create index if not exists mcp_listings_use_cases_idx on public.mcp_listings using gin (use_cases);

-- The body an item exists to deliver: a prompt's text, a skill's
-- instructions, usage, examples, inputs and outputs. Admin-authored and
-- validated by the API (`services/marketplace/items.py`) before it is written.
-- A document because it is read whole and its keys differ by item type.
--
-- Deliberately separate from `readme`. The README belongs to the upstream
-- repository and is refreshed from it; `content` belongs to the admin and is
-- never overwritten by a refresh. Mixing them would let a metadata refresh
-- silently replace what an administrator wrote.
alter table public.mcp_listings add column if not exists content jsonb not null default '{}'::jsonb;

-- ---------------------------------------------------------------- status
--
-- `archived` joins the lifecycle: hidden like a draft, but distinguishable
-- from one, so "retired on purpose" and "not ready yet" do not look alike in
-- the admin list. Restoring an archived item returns it to draft, never
-- straight to published.
alter table public.mcp_listings drop constraint if exists mcp_listings_status_check;
alter table public.mcp_listings add constraint mcp_listings_status_check
  check (status in (
    'draft', 'submitted', 'scanning', 'review', 'approved', 'rejected',
    'published', 'suspended', 'archived'
  ));

-- ---------------------------------------------------------------- search
--
-- The generated column is the index, so it cannot drift from the row it
-- describes and never becomes a source of truth of its own. Rebuilt here to
-- cover the new fields. Weights: the name first; who made it and what it says
-- it does second; the vocabulary an agent searches with third; the body last.
--
-- `item_type` has its underscore replaced so "mcp server" matches: the
-- default parser does not split `mcp_server` into the words a person types.
alter table public.mcp_listings drop column if exists search_vector;
alter table public.mcp_listings
  add column if not exists search_vector tsvector
  generated always as (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(publisher, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(author, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('english', replace(item_type, '_', ' ')), 'C') ||
    setweight(to_tsvector('english', public.immutable_array_to_string(coalesce(tags, '{}'), ' ')), 'C') ||
    setweight(to_tsvector('english', public.immutable_array_to_string(coalesce(categories, '{}'), ' ')), 'C') ||
    setweight(to_tsvector('english', public.immutable_array_to_string(coalesce(technologies, '{}'), ' ')), 'C') ||
    setweight(to_tsvector('english', public.immutable_array_to_string(coalesce(capabilities, '{}'), ' ')), 'C') ||
    setweight(to_tsvector('english', public.immutable_array_to_string(coalesce(use_cases, '{}'), ' ')), 'C') ||
    setweight(to_tsvector('english', coalesce(content ->> 'instructions', '')), 'D') ||
    setweight(to_tsvector('english', coalesce(content ->> 'usage', '')), 'D')
  ) stored;

create index if not exists mcp_listings_search_idx on public.mcp_listings using gin (search_vector);

-- ----------------------------------------------------------------- links
--
-- "This skill uses that prompt", "see also". A table rather than an array of
-- ids so deleting an item removes every link to it: an array would keep
-- pointing at rows that no longer exist until something noticed.
create table if not exists public.mcp_listing_links (
  listing_id uuid not null references public.mcp_listings (id) on delete cascade,
  related_id uuid not null references public.mcp_listings (id) on delete cascade,
  relation text not null default 'related' check (relation in ('uses', 'related')),
  created_at timestamptz not null default now(),
  primary key (listing_id, related_id),
  check (listing_id <> related_id)
);

create index if not exists mcp_listing_links_related_idx on public.mcp_listing_links (related_id);

alter table public.mcp_listing_links enable row level security;

-- A link is readable when the item it hangs off is. The API additionally
-- filters the *target* to published, visible items, so a public page never
-- names a draft through a link.
drop policy if exists mcp_listing_links_select on public.mcp_listing_links;
create policy mcp_listing_links_select on public.mcp_listing_links
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

-- ------------------------------------------------------------ categories
--
-- The seeded seventeen describe MCP servers. A registry that also holds UI
-- components, templates and workflows needs somewhere to put them. Admins can
-- add more from /admin; these are the ones the existing set plainly lacks.
insert into public.mcp_categories (slug, name, sort_order) values
  ('frontend',   'Frontend',   170),
  ('backend',    'Backend',    180),
  ('testing',    'Testing',    190),
  ('design',     'Design',     200),
  ('automation', 'Automation', 210)
on conflict (slug) do nothing;

-- ------------------------------------------------------------ curation
--
-- The registry is admin-curated. The weekly sync used to insert every server
-- from the official MCP Registry as `published`, unscanned, which put hundreds
-- of items no administrator had looked at into the public catalogue. Those go
-- back to `draft`: a pool an admin chooses from, scans, and publishes. Anything
-- that carries a grade stays, because a scan and an admin action put it there.
--
-- Scoped to `source = 'registry'`. Admin-added items and approved suggestions
-- were published by a person, and are left as that person left them.
update public.mcp_listings
   set status = 'draft', updated_at = now()
 where source = 'registry'
   and status = 'published'
   and current_trust_grade is null;

-- A listing's status no longer changes while it is scanned: scan progress is
-- recorded on the version (`scan_status`). It used to be parked in `scanning`
-- and then set to `published` when the scan finished - whatever it had been
-- before, so scanning a draft or a suggestion under review published it with
-- no admin decision. Nothing moves a row out of `scanning` any more, so any
-- caught there now goes to the state its evidence supports: published if a
-- grade exists, otherwise draft for an admin to decide.
update public.mcp_listings
   set status = case when current_trust_grade is not null then 'published' else 'draft' end,
       updated_at = now()
 where status = 'scanning';

-- A listing now distinguishes "never scanned" from "scanned, but no grade
-- could be established" - a server that needs a credential to start is the
-- second, and is publishable with that state shown. The distinction is read
-- from `current_version`: set means a scan was applied.
--
-- 0047 withdrew every grade from the previous engine but left
-- `current_version`/`current_scanned_at` in place, so those listings would now
-- claim "scanned, not graded" on the strength of a scan by an engine Aevrin no
-- longer runs. The projection is cleared wherever the version it names has no
-- scan from the current engine (`scans.scanner_name` exists only since 0047).
-- A migration writes these columns only because 0047 already did the same
-- correction to the grade beside them; grading.py remains their only writer.
update public.mcp_listings l
   set current_version = null,
       current_scanned_at = null,
       current_coverage_complete = null
 where l.current_trust_grade is null
   and l.current_version is not null
   and not exists (
     select 1
       from public.mcp_listing_versions v
       join public.scans s on s.id = v.scan_id
      where v.listing_id = l.id
        and v.version = l.current_version
        and s.scanner_name is not null
   );

-- --------------------------------------------------- organisation policy
--
-- Policies were written when the letters stopped at D. An F server looked up
-- a key that did not exist and fell through to `require_approval`: the worst
-- grade got a milder action than the second worst. F now blocks by default,
-- and every stored policy gains the key it was missing.
alter table public.org_mcp_policies alter column grade_actions set default
  '{"A":"allow","B":"allow","C":"require_approval","D":"block","F":"block"}'::jsonb;

update public.org_mcp_policies
   set grade_actions = grade_actions || '{"F":"block"}'::jsonb
 where not (grade_actions ? 'F');

comment on table public.mcp_listings is
  'The Aevrin Registry: every catalogued capability, of every item_type. Security never lives here: it lives on mcp_listing_versions, which references a real scan, and only mcp_server items have one.';
