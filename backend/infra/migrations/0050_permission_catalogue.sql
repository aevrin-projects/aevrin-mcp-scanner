-- Workspace roles: strip the permission keys the catalogue no longer has.
--
-- DATA-ONLY, SAFE TO APPLY BEFORE OR AFTER THE DEPLOY. No table, column,
-- constraint or policy changes; it rewrites `organization_roles.permissions`
-- arrays and nothing else.
--
--   * The image deployed before this change still has these six keys in its
--     catalogue, but checks none of them anywhere (SECURITY.md said so), so a
--     role losing them loses nothing that image enforced. Its role editor
--     simply shows those switches off.
--   * The image that ships with this change no longer knows them. It ignores
--     unknown stored keys when deciding what a member holds
--     (`permissions.held_by` intersects with the catalogue) and filters them
--     out of every role it returns (`org_controller._role_out`), so the role
--     editor never sends one back to be refused as unknown. It works the
--     same with or without this file applied.
--
-- So the order does not matter for correctness. Apply it after the deploy is
-- healthy, as the routine step, so stored roles match the catalogue and a
-- direct database read shows no key that means nothing.
--
-- Removed keys, and why (DECISIONS.md ADR-051):
--
--   marketplace.publish   only an Aevrin admin publishes (ADR-048); no member
--                         route publishes anything.
--   policy.manage         the per-grade install policy was removed (ADR-049).
--   mcp.manage            no member-facing route creates or edits a private
--                         registry item; only the admin editor does.
--   marketplace.submit    a registry suggestion is a personal act open to
--                         every signed-in user, including those in no
--                         workspace; the suggested item is public.
--   ai_providers.manage   a provider key is stored per user and used only for
--                         that user's own explanations; no member uses
--                         another's key.
--   billing.manage        buying Team is owner-only by workspace ownership
--                         (ADR-050); every other purchase is personal.
--
-- Also stripped from the Owner role's stored row, which is written with the
-- whole catalogue at creation. The owner holds every permission implicitly
-- whatever that row says, so this changes nothing an owner can do.
--
-- Nothing is granted. Roles only lose keys; no role gains one, including the
-- default Security Admin, whose new-workspace default changed in code
-- (ADR-051) but is not back-filled into existing workspaces: a stored role is
-- the owner's decision, and widening it silently is not this file's to make.
--
-- Idempotent: the `where` clause matches only rows that still hold a removed
-- key, so re-running it updates nothing.

update public.organization_roles as r
set permissions = coalesce(
  (
    select array_agg(p.key order by p.ord)
    from unnest(r.permissions) with ordinality as p(key, ord)
    where p.key <> all (array[
      'marketplace.publish', 'policy.manage', 'mcp.manage',
      'marketplace.submit', 'ai_providers.manage', 'billing.manage'
    ]::text[])
  ),
  '{}'::text[]
)
where r.permissions && array[
  'marketplace.publish', 'policy.manage', 'mcp.manage',
  'marketplace.submit', 'ai_providers.manage', 'billing.manage'
]::text[];
