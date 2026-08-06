-- First-party, cookie-free pageview collection. See apps/web/src/app/api/track.
create table if not exists public.page_views (
  id bigserial primary key,
  path text not null,
  referrer text,
  country text,
  device text,
  visitor_hash text not null,
  user_id uuid,
  created_at timestamptz not null default now()
);
create index if not exists page_views_created_idx on public.page_views (created_at desc);
create index if not exists page_views_path_idx on public.page_views (path, created_at desc);
create index if not exists page_views_visitor_idx on public.page_views (visitor_hash, created_at desc);
comment on table public.page_views is
  'Cookie-free first-party pageviews. visitor_hash is a daily-rotating salted hash of IP+UA: it counts distinct visitors within one day and cannot be joined across days or reversed.';
alter table public.page_views enable row level security;
