"use client";

import { useCallback, useEffect, useState } from "react";
import { Trash2, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/shared/api";
import { organizationApi } from "@/entities/organization";
import type {
  Invite,
  Member,
  Membership,
  OrgPermission,
  Organization,
  Role,
} from "@/entities/organization";
import {
  EmptyState,
  PageHeader,
  Panel,
  PanelBody,
  PanelHeader,
  PanelSubtitle,
  PanelTitle,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  PanelTableWrap,
} from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Select } from "@/shared/ui/select";
import { Skeleton } from "@/shared/ui/skeleton";
import { Switch } from "@/shared/ui/switch";
import { formatDateTime } from "@/shared/lib/format";

const MEMBERS_MANAGE = "members.manage";
const ROLES_MANAGE = "roles.manage";
const ORG_MANAGE = "org.manage";

function message(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}

/** Nothing here is a permission check. The server decides; this only keeps
 *  the page from offering a control whose only outcome would be a 403. */
function can(org: Organization | null, permission: string) {
  return Boolean(org?.my_permissions.includes(permission));
}

// --- Not in a workspace yet -----------------------------------------------

function NoWorkspace({ membership, onChanged }: { membership: Membership; onChanged: () => void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    try {
      await organizationApi.create(name.trim());
      toast.success("Workspace created. Your existing scans and agents moved into it.");
      onChanged();
    } catch (err) {
      toast.error(message(err, "Could not create the workspace."));
    } finally {
      setBusy(false);
    }
  }

  async function accept(invite: Invite) {
    setBusy(true);
    try {
      await organizationApi.acceptInvite(invite.id);
      toast.success(`You joined as ${invite.role_name}.`);
      onChanged();
    } catch (err) {
      toast.error(message(err, "Could not accept that invitation."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Shown before the create form: someone who was invited should not
          have to make a workspace to discover they were already offered one. */}
      {membership.pending_invites.length > 0 ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>You have been invited</PanelTitle>
            <PanelSubtitle>Accepting puts your future scans in the shared workspace.</PanelSubtitle>
          </PanelHeader>
          <PanelBody className="flex flex-col gap-3">
            {membership.pending_invites.map((invite) => (
              <div key={invite.id} className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">Joining as {invite.role_name}</p>
                  <p className="text-[13px] text-muted-foreground">
                    Expires {formatDateTime(invite.expires_at)}
                  </p>
                </div>
                <Button size="sm" disabled={busy} onClick={() => void accept(invite)}>
                  Accept
                </Button>
              </div>
            ))}
          </PanelBody>
        </Panel>
      ) : null}

      <Panel>
        <PanelHeader>
          <PanelTitle>Create a workspace</PanelTitle>
          <PanelSubtitle>
            A workspace shares scans, agents and findings with the people in it, and lets you
            decide what each of them can do.
          </PanelSubtitle>
        </PanelHeader>
        <PanelBody className="flex flex-col gap-3 sm:flex-row">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Workspace name"
            maxLength={80}
            aria-label="Workspace name"
            className="sm:max-w-xs"
          />
          <Button disabled={busy || name.trim().length === 0} onClick={() => void create()}>
            Create workspace
          </Button>
        </PanelBody>
        <PanelBody className="pt-0">
          <p className="text-[13px] leading-5 text-muted-foreground">
            Your existing scans, agents and findings move into it, so the history you already have
            is what the workspace starts with. You stay the owner, and the owner can always
            administer the workspace whatever roles exist.
          </p>
        </PanelBody>
      </Panel>
    </div>
  );
}

// --- The workspace itself --------------------------------------------------

function RenamePanel({ org, onChanged }: { org: Organization; onChanged: () => void }) {
  const [name, setName] = useState(org.name);
  const [busy, setBusy] = useState(false);

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Workspace name</PanelTitle>
        <PanelSubtitle>What everyone in it sees at the top of this page.</PanelSubtitle>
      </PanelHeader>
      <PanelBody className="flex flex-col gap-3 sm:flex-row">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          aria-label="Workspace name"
          className="sm:max-w-xs"
        />
        <Button
          variant="outline"
          disabled={busy || name.trim().length === 0 || name.trim() === org.name}
          onClick={() => {
            setBusy(true);
            organizationApi
              .rename(name.trim())
              .then(() => {
                toast.success("Workspace renamed.");
                onChanged();
              })
              .catch((err: unknown) => toast.error(message(err, "Could not rename the workspace.")))
              .finally(() => setBusy(false));
          }}
        >
          Save
        </Button>
      </PanelBody>
    </Panel>
  );
}

// --- Members ---------------------------------------------------------------

function MembersPanel({
  org,
  members,
  roles,
  onChanged,
}: {
  org: Organization;
  members: Member[];
  roles: Role[];
  onChanged: () => void;
}) {
  const manage = can(org, MEMBERS_MANAGE);
  const assignable = roles.filter((r) => !r.is_owner_role);

  async function setRole(member: Member, roleId: string) {
    try {
      await organizationApi.setMemberRole(member.user_id, roleId);
      toast.success(`${member.email ?? "That member"} is now ${roles.find((r) => r.id === roleId)?.name}.`);
      onChanged();
    } catch (err) {
      toast.error(message(err, "Could not change that role."));
    }
  }

  async function remove(member: Member) {
    if (!window.confirm(`Remove ${member.email ?? "this member"} from ${org.name}?`)) return;
    try {
      await organizationApi.removeMember(member.user_id);
      toast.success("Member removed. Their scans stay in the workspace.");
      onChanged();
    } catch (err) {
      toast.error(message(err, "Could not remove that member."));
    }
  }

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Members</PanelTitle>
        <PanelSubtitle>
          {org.seats_used} of {org.seats} seat{org.seats === 1 ? "" : "s"} used, counting invitations
          nobody has accepted yet.
        </PanelSubtitle>
      </PanelHeader>
      <PanelTableWrap>
        <Table>
          <THead>
            <TR>
              <TH>Member</TH>
              <TH>Role</TH>
              <TH>Joined</TH>
              <TH className="text-right">Remove</TH>
            </TR>
          </THead>
          <TBody>
            {members.map((member) => (
              <TR key={member.user_id}>
                <TD>
                  <span className="font-medium">{member.email ?? "Unknown address"}</span>
                  {member.is_owner ? (
                    <Badge variant="outline" className="ml-2 rounded-full px-2 py-0.5">
                      Owner
                    </Badge>
                  ) : null}
                </TD>
                <TD>
                  {/* The owner's role is fixed. Offering a select that always
                      fails would be a control that lies about what it does. */}
                  {member.is_owner || !manage ? (
                    <span className="text-muted-foreground">{member.role_name}</span>
                  ) : (
                    <Select
                      value={member.role_id}
                      aria-label={`Role for ${member.email ?? member.user_id}`}
                      onChange={(e) => void setRole(member, e.target.value)}
                      className="max-w-[200px]"
                    >
                      {assignable.map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </TD>
                <TD className="text-muted-foreground">{formatDateTime(member.joined_at)}</TD>
                <TD className="text-right">
                  {member.is_owner || !manage ? null : (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove ${member.email ?? member.user_id}`}
                      onClick={() => void remove(member)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </PanelTableWrap>
    </Panel>
  );
}

// --- Invites ---------------------------------------------------------------

function InvitesPanel({
  org,
  roles,
  invites,
  onChanged,
}: {
  org: Organization;
  roles: Role[];
  invites: Invite[];
  onChanged: () => void;
}) {
  const assignable = roles.filter((r) => !r.is_owner_role);
  const [email, setEmail] = useState("");
  const [chosenRole, setChosenRole] = useState("");
  const [busy, setBusy] = useState(false);
  // Derived, not synced: the roles arrive after the first render, and an
  // effect that wrote the default back into state would re-render for a
  // value that can simply be computed.
  const roleId = chosenRole || assignable[0]?.id || "";

  async function send() {
    setBusy(true);
    try {
      await organizationApi.invite(email.trim(), roleId);
      toast.success(`Invitation created for ${email.trim()}.`);
      setEmail("");
      onChanged();
    } catch (err) {
      toast.error(message(err, "Could not send that invitation."));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(invite: Invite) {
    try {
      await organizationApi.revokeInvite(invite.id);
      toast.success("Invitation revoked, and its seat is free again.");
      onChanged();
    } catch (err) {
      toast.error(message(err, "Could not revoke that invitation."));
    }
  }

  const full = org.seats_used >= org.seats;

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Invitations</PanelTitle>
        <PanelSubtitle>
          An invitation can only be accepted by someone signed in as that address, so it has to be
          an address that already has an Aevrin account.
        </PanelSubtitle>
      </PanelHeader>
      <PanelBody className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="colleague@company.com"
          aria-label="Email to invite"
          className="sm:max-w-xs"
        />
        <Select
          value={roleId}
          onChange={(e) => setChosenRole(e.target.value)}
          aria-label="Role for the invitation"
          className="sm:max-w-[200px]"
        >
          {assignable.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </Select>
        <Button disabled={busy || full || email.trim().length < 3 || !roleId} onClick={() => void send()}>
          <UserPlus className="size-4" />
          Invite
        </Button>
      </PanelBody>

      {full ? (
        <PanelBody className="pt-0">
          <Alert>
            <AlertTitle>Every seat is taken</AlertTitle>
            <AlertDescription>
              {org.seats_used} of {org.seats} seats are in use, counting invitations nobody has
              accepted. Add seats on the billing page, or revoke an invitation below.
            </AlertDescription>
          </Alert>
        </PanelBody>
      ) : null}

      {invites.length === 0 ? (
        <EmptyState title="No invitations outstanding" body="Everyone invited has joined." />
      ) : (
        <PanelTableWrap>
          <Table>
            <THead>
              <TR>
                <TH>Address</TH>
                <TH>Role</TH>
                <TH>Expires</TH>
                <TH className="text-right">Revoke</TH>
              </TR>
            </THead>
            <TBody>
              {invites.map((invite) => (
                <TR key={invite.id}>
                  <TD className="font-medium">{invite.email}</TD>
                  <TD className="text-muted-foreground">{invite.role_name}</TD>
                  <TD className="text-muted-foreground">{formatDateTime(invite.expires_at)}</TD>
                  <TD className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Revoke the invitation for ${invite.email}`}
                      onClick={() => void revoke(invite)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </PanelTableWrap>
      )}
    </Panel>
  );
}

// --- Roles -----------------------------------------------------------------

function RoleEditor({
  role,
  catalogue,
  onSave,
  onDelete,
}: {
  role: Role;
  catalogue: OrgPermission[];
  onSave: (name: string, permissions: string[]) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [name, setName] = useState(role.name);
  const [granted, setGranted] = useState<string[]>(role.permissions);
  const [busy, setBusy] = useState(false);

  const dirty = name !== role.name || granted.join() !== [...role.permissions].sort().join();

  function toggle(key: string, on: boolean) {
    setGranted((current) =>
      on ? [...current, key].sort() : current.filter((k) => k !== key),
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {role.is_owner_role ? (
          <span className="text-sm font-medium">{role.name}</span>
        ) : (
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            aria-label={`Name of the ${role.name} role`}
            className="max-w-[220px]"
          />
        )}
        <span className="text-[13px] text-muted-foreground">
          {role.member_count} member{role.member_count === 1 ? "" : "s"}
        </span>
      </div>

      {role.is_owner_role ? (
        <p className="text-[13px] leading-5 text-muted-foreground">
          The owner holds every permission, and this role cannot be edited, deleted, or given to
          anyone else. Without that, a workspace could end up with nobody able to administer it.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {catalogue.map((permission) => (
            <div key={permission.key} className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <label htmlFor={`${role.id}-${permission.key}`} className="text-sm">
                  {permission.label}
                </label>
                <p className="text-[13px] leading-5 text-muted-foreground">
                  {permission.description}
                </p>
              </div>
              <Switch
                id={`${role.id}-${permission.key}`}
                checked={granted.includes(permission.key)}
                onCheckedChange={(on: boolean) => toggle(permission.key, on)}
              />
            </div>
          ))}
        </div>
      )}

      {role.is_owner_role ? null : (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            disabled={busy || !dirty || name.trim().length === 0}
            onClick={() => {
              setBusy(true);
              void onSave(name.trim(), granted).finally(() => setBusy(false));
            }}
          >
            Save changes
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void onDelete().finally(() => setBusy(false));
            }}
          >
            Delete role
          </Button>
        </div>
      )}
    </div>
  );
}

function RolesPanel({
  org,
  roles,
  catalogue,
  onChanged,
}: {
  org: Organization;
  roles: Role[];
  catalogue: OrgPermission[];
  onChanged: () => void;
}) {
  const [newRole, setNewRole] = useState("");
  const [busy, setBusy] = useState(false);

  if (!can(org, ROLES_MANAGE)) {
    return (
      <Panel>
        <PanelHeader>
          <PanelTitle>Roles</PanelTitle>
          <PanelSubtitle>Your role is {org.my_role}.</PanelSubtitle>
        </PanelHeader>
        <PanelBody className="flex flex-col gap-2">
          {roles.map((role) => (
            <div key={role.id} className="flex items-center justify-between gap-3 text-sm">
              <span>{role.name}</span>
              <span className="text-muted-foreground">
                {role.member_count} member{role.member_count === 1 ? "" : "s"}
              </span>
            </div>
          ))}
        </PanelBody>
      </Panel>
    );
  }

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Roles</PanelTitle>
        <PanelSubtitle>
          A role is a set of permissions. Anything a role does not hold is refused by the server,
          not merely hidden from the page.
        </PanelSubtitle>
      </PanelHeader>
      <PanelBody className="flex flex-col gap-3 sm:flex-row">
        <Input
          value={newRole}
          onChange={(e) => setNewRole(e.target.value)}
          placeholder="New role name"
          maxLength={40}
          aria-label="New role name"
          className="sm:max-w-xs"
        />
        <Button
          disabled={busy || newRole.trim().length === 0}
          onClick={() => {
            setBusy(true);
            organizationApi
              .createRole(newRole.trim(), [])
              .then(() => {
                toast.success(`Role "${newRole.trim()}" created with no permissions yet.`);
                setNewRole("");
                onChanged();
              })
              .catch((err: unknown) => toast.error(message(err, "Could not create that role.")))
              .finally(() => setBusy(false));
          }}
        >
          Add role
        </Button>
      </PanelBody>
      <PanelBody className="flex flex-col gap-4 pt-0">
        {roles.map((role) => (
          <RoleEditor
            key={role.id}
            role={role}
            catalogue={catalogue}
            onSave={async (name, permissions) => {
              try {
                await organizationApi.updateRole(role.id, name, permissions);
                toast.success(`${name} saved.`);
                onChanged();
              } catch (err) {
                toast.error(message(err, "Could not save that role."));
              }
            }}
            onDelete={async () => {
              if (!window.confirm(`Delete the ${role.name} role?`)) return;
              try {
                await organizationApi.deleteRole(role.id);
                toast.success(`${role.name} deleted.`);
                onChanged();
              } catch (err) {
                toast.error(message(err, "Could not delete that role."));
              }
            }}
          />
        ))}
      </PanelBody>
    </Panel>
  );
}

// --- Page ------------------------------------------------------------------

interface WorkspaceData {
  membership: Membership;
  catalogue: OrgPermission[];
  members: Member[];
  roles: Role[];
  invites: Invite[];
}

async function fetchWorkspace(): Promise<WorkspaceData> {
  const [membership, catalogue] = await Promise.all([
    organizationApi.getMembership(),
    organizationApi.listPermissions(),
  ]);
  const org = membership.organization;
  if (!org) return { membership, catalogue, members: [], roles: [], invites: [] };

  const [members, roles] = await Promise.all([
    organizationApi.listMembers(),
    organizationApi.listRoles(),
  ]);
  // Only someone who can manage members may list invitations, so a plain
  // member's page must not fail because of a panel they cannot see.
  const invites = org.my_permissions.includes(MEMBERS_MANAGE)
    ? await organizationApi.listInvites()
    : [];
  return { membership, catalogue, members, roles, invites };
}

export function WorkspacePage() {
  const [membership, setMembership] = useState<Membership | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [catalogue, setCatalogue] = useState<OrgPermission[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      fetchWorkspace()
        .then((data) => {
          setMembership(data.membership);
          setCatalogue(data.catalogue);
          setMembers(data.members);
          setRoles(data.roles);
          setInvites(data.invites);
          setError(null);
        })
        .catch((err: unknown) => {
          setError(message(err, "Could not load your workspace."));
          setMembership((existing) => existing ?? { organization: null, pending_invites: [] });
        }),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const org = membership?.organization ?? null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="Account"
        title={org ? org.name : "Workspace"}
        description={
          org
            ? `You are ${org.my_role} here. Everyone in a workspace sees the same scans, agents and findings.`
            : "Share scans and agents with your team, and decide what each person can do."
        }
      />

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load your workspace</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {membership === null && !error ? (
        <Panel>
          <PanelBody className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        </Panel>
      ) : membership === null ? null : !org ? (
        <NoWorkspace membership={membership} onChanged={() => void load()} />
      ) : (
        <>
          {can(org, ORG_MANAGE) ? <RenamePanel org={org} onChanged={() => void load()} /> : null}
          <MembersPanel org={org} members={members} roles={roles} onChanged={() => void load()} />
          {can(org, MEMBERS_MANAGE) ? (
            <InvitesPanel org={org} roles={roles} invites={invites} onChanged={() => void load()} />
          ) : null}
          <RolesPanel org={org} roles={roles} catalogue={catalogue} onChanged={() => void load()} />

          {org.is_owner ? null : (
            <Panel>
              <PanelHeader>
                <PanelTitle>Leave {org.name}</PanelTitle>
                <PanelSubtitle>
                  You lose access to the workspace&apos;s scans and agents. The work you did stays
                  with the workspace.
                </PanelSubtitle>
              </PanelHeader>
              <PanelBody>
                <Button
                  variant="outline"
                  onClick={() => {
                    if (!window.confirm(`Leave ${org.name}?`)) return;
                    organizationApi
                      .leave()
                      .then(() => {
                        toast.success(`You left ${org.name}.`);
                        void load();
                      })
                      .catch((err: unknown) =>
                        toast.error(message(err, "Could not leave that workspace.")),
                      );
                  }}
                >
                  <Users className="size-4" />
                  Leave workspace
                </Button>
              </PanelBody>
            </Panel>
          )}

        </>
      )}
    </div>
  );
}
