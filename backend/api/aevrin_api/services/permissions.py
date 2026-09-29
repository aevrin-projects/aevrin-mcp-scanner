"""What a role may hold, and what holding it means.

A fixed catalogue of permission strings, not a policy language. The workspace
owner composes roles out of these; anything a role does not hold is refused.
Adding a capability to the product means adding a line here, which is the
point: a permission that exists but is never checked is worse than no
permission system at all, so every key below names an action a route refuses
without it (see SECURITY.md, "What is actually enforced").

Reading is not in the catalogue. Membership *is* read access -- that is what
a shared workspace means -- and a "can view scans" switch that everyone must
hold to use the product at all would be a setting with one correct value.

Six keys were removed (DECISIONS.md ADR-051) because nothing they named was a
workspace action: `marketplace.publish` (only an Aevrin admin publishes),
`policy.manage` (the install policy was removed in ADR-049), `mcp.manage` (no
member-facing private listing route exists), `marketplace.submit` (a
suggestion to the public registry is personal and open to every signed-in
user), `ai_providers.manage` (a provider key is used only for its owner's own
requests) and `billing.manage` (buying Team is gated by workspace ownership).
Migration 0050 strips them from stored roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SCANS_RUN: Final = "scans.run"
SCANS_DELETE: Final = "scans.delete"
FINDINGS_TRIAGE: Final = "findings.triage"
AGENTS_DELETE: Final = "agents.delete"
MEMBERS_MANAGE: Final = "members.manage"
ROLES_MANAGE: Final = "roles.manage"
ORG_MANAGE: Final = "org.manage"


@dataclass(frozen=True)
class Permission:
    key: str
    label: str
    description: str


# Ordered for display: the things most roles should hold first, the things
# that hand over control of the workspace last.
CATALOGUE: Final[tuple[Permission, ...]] = (
    Permission(
        SCANS_RUN,
        "Run scans",
        "Start a scan from the dashboard, the CLI or the hook, upload a CLI result, "
        "report agent posture, and cancel a running scan.",
    ),
    Permission(
        SCANS_DELETE,
        "Delete scans",
        "Remove a scan and its findings from the workspace, or clear scan history.",
    ),
    Permission(
        FINDINGS_TRIAGE,
        "Triage findings",
        "Mark a finding fixed or a false positive, or reopen it.",
    ),
    Permission(AGENTS_DELETE, "Remove agents", "Forget a reported machine and its posture snapshot."),
    Permission(MEMBERS_MANAGE, "Manage members", "Invite people, remove them, and change their role."),
    Permission(ROLES_MANAGE, "Manage roles", "Create roles and choose what each one may do."),
    Permission(ORG_MANAGE, "Manage workspace", "Rename the workspace."),
)

ALL_KEYS: Final[frozenset[str]] = frozenset(p.key for p in CATALOGUE)
LABELS: Final[dict[str, str]] = {p.key: p.label for p in CATALOGUE}

# The roles a new workspace starts with. The owner role is special and is
# created separately; these are ordinary roles the owner can edit or delete.
DEFAULT_ROLES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("Admin", (SCANS_RUN, SCANS_DELETE, FINDINGS_TRIAGE, AGENTS_DELETE, MEMBERS_MANAGE)),
    # A security admin keeps the workspace's security record: runs scans,
    # triages, removes stale scans and retired machines. It holds nothing that
    # changes who is in the workspace or what they may do.
    ("Security Admin", (SCANS_RUN, SCANS_DELETE, FINDINGS_TRIAGE, AGENTS_DELETE)),
    ("Member", (SCANS_RUN, FINDINGS_TRIAGE)),
    # Viewer holds nothing. Membership alone grants read access, which is what
    # a shared workspace means; a viewer is someone who can see the findings
    # and change nothing, which includes not adding scans to them.
    ("Viewer", ()),
)

OWNER_ROLE_NAME: Final = "Owner"


def unknown_permissions(keys: list[str]) -> list[str]:
    """Names in `keys` that are not in the catalogue.

    Returned rather than raised so the caller can name all of them at once. A
    role saved with a permission nobody checks would look granted and behave
    denied, which is the failure mode worth being loud about.
    """
    return sorted(set(keys) - ALL_KEYS)


def held_by(*, is_owner: bool, permissions: list[str]) -> frozenset[str]:
    """Everything this member may do.

    The owner holds the whole catalogue by definition, whatever their role
    row says. Without that, an owner could edit their own role until nobody
    in the workspace could administer it, and there would be no way back in
    that did not involve the database.
    """
    return ALL_KEYS if is_owner else frozenset(permissions) & ALL_KEYS
