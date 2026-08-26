"""What a role may hold, and what holding it means.

A fixed catalogue of permission strings, not a policy language. The workspace
owner composes roles out of these; anything a role does not hold is refused.
Adding a capability to the product means adding a line here, which is the
point: a permission that exists but is never checked is worse than no
permission system at all, so the catalogue and the checks are kept in one
file where they can be read against each other.

Reading is not in the catalogue. Membership *is* read access -- that is what
a shared workspace means -- and a "can view scans" switch that everyone must
hold to use the product at all would be a setting with one correct value.
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
BILLING_MANAGE: Final = "billing.manage"
ORG_MANAGE: Final = "org.manage"


@dataclass(frozen=True)
class Permission:
    key: str
    label: str
    description: str


# Ordered for display: the things most roles should hold first, the things
# that hand over control of the workspace last.
CATALOGUE: Final[tuple[Permission, ...]] = (
    Permission(SCANS_RUN, "Run scans", "Start a scan and upload results from the CLI."),
    Permission(SCANS_DELETE, "Delete scans", "Remove a scan and its findings from the workspace."),
    Permission(FINDINGS_TRIAGE, "Triage findings", "Mark a finding fixed or a false positive."),
    Permission(AGENTS_DELETE, "Remove agents", "Forget a reported machine and its posture snapshot."),
    Permission(MEMBERS_MANAGE, "Manage members", "Invite people, remove them, and change their role."),
    Permission(ROLES_MANAGE, "Manage roles", "Create roles and choose what each one may do."),
    Permission(BILLING_MANAGE, "Manage billing", "Change the plan and the number of seats."),
    Permission(ORG_MANAGE, "Manage workspace", "Rename or delete the workspace."),
)

ALL_KEYS: Final[frozenset[str]] = frozenset(p.key for p in CATALOGUE)

# The roles a new workspace starts with. The owner role is special and is
# created separately; these are ordinary roles the owner can edit or delete.
DEFAULT_ROLES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("Admin", (SCANS_RUN, SCANS_DELETE, FINDINGS_TRIAGE, AGENTS_DELETE, MEMBERS_MANAGE)),
    ("Member", (SCANS_RUN, FINDINGS_TRIAGE)),
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
