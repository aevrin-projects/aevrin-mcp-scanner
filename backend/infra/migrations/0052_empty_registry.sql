-- Empty the registry: every item (MCP servers, skills, prompts, every other
-- type), every category, and everything attached to them.
--
-- The owner asked on 2026-10-03 for /marketplace and /admin/marketplace to
-- start from nothing, and stopped the weekly registry sync in the same
-- change (.github/workflows/scheduler.yml), so the ~18,000 official-registry
-- drafts do not come back. Items are added by an administrator from here on.
--
-- SAFE TO APPLY BEFORE OR AFTER THE DEPLOY, AND SAFE TO RUN TWICE. Data only:
-- no table, column, index, policy or function is dropped or altered.
-- apply-migration.ps1 sends the file as one query, which Postgres runs as
-- one implicit transaction: every table is emptied, or none is.
--
-- Children before parents. Every table below holds registry data only:
--   mcp_listing_links     related-item links (0048)
--   mcp_favorites         users' saved items
--   mcp_reports           user reports against items
--   mcp_events            item timelines, and the sync's own run markers
--                         (listing_id null), which are its watermark: a sync
--                         run by hand after this is a full crawl, which is
--                         what an empty registry needs
--   mcp_listing_versions  per-version records and scan pointers
--   mcp_submissions       "Suggest an item" queue
--   mcp_listings          the items
--   mcp_categories        the categories (seeded by 0037)
--
-- Deliberately kept: admin_audit_log rows about past registry actions (the
-- audit log is append-only evidence and is written to outlive the item),
-- scans and findings (a scan of a server stands on its own), and every
-- account, workspace and billing table.

delete from public.mcp_listing_links;
delete from public.mcp_favorites;
delete from public.mcp_reports;
delete from public.mcp_events;
delete from public.mcp_listing_versions;
delete from public.mcp_submissions;
delete from public.mcp_listings;
delete from public.mcp_categories;

select
  (select count(*) from public.mcp_listing_links)    as listing_links,
  (select count(*) from public.mcp_favorites)        as favorites,
  (select count(*) from public.mcp_reports)          as reports,
  (select count(*) from public.mcp_events)           as events,
  (select count(*) from public.mcp_listing_versions) as listing_versions,
  (select count(*) from public.mcp_submissions)      as submissions,
  (select count(*) from public.mcp_listings)         as listings,
  (select count(*) from public.mcp_categories)       as categories;
