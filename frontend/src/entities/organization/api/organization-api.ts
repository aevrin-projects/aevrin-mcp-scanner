import { request } from "@/shared/api";
import type { Invite, Member, Membership, OrgPermission, Organization, Role } from "../model/types";

export const organizationApi = {
  getMembership: () => request<Membership>("/orgs/me"),
  listPermissions: () => request<OrgPermission[]>("/orgs/permissions"),

  create: (name: string) =>
    request<Organization>("/orgs", { method: "POST", body: JSON.stringify({ name }) }),
  rename: (name: string) =>
    request<Organization>("/orgs", { method: "PATCH", body: JSON.stringify({ name }) }),
  leave: () => request<void>("/orgs/leave", { method: "POST" }),

  listMembers: () => request<Member[]>("/orgs/members"),
  setMemberRole: (userId: string, roleId: string) =>
    request<void>(`/orgs/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role_id: roleId }),
    }),
  removeMember: (userId: string) => request<void>(`/orgs/members/${userId}`, { method: "DELETE" }),

  listInvites: () => request<Invite[]>("/orgs/invites"),
  invite: (email: string, roleId: string) =>
    request<Invite>("/orgs/invites", {
      method: "POST",
      body: JSON.stringify({ email, role_id: roleId }),
    }),
  revokeInvite: (id: string) => request<void>(`/orgs/invites/${id}`, { method: "DELETE" }),
  acceptInvite: (id: string) =>
    request<Organization>(`/orgs/invites/${id}/accept`, { method: "POST" }),

  listRoles: () => request<Role[]>("/orgs/roles"),
  createRole: (name: string, permissions: string[]) =>
    request<Role>("/orgs/roles", { method: "POST", body: JSON.stringify({ name, permissions }) }),
  updateRole: (id: string, name: string, permissions: string[]) =>
    request<Role>(`/orgs/roles/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name, permissions }),
    }),
  deleteRole: (id: string) => request<void>(`/orgs/roles/${id}`, { method: "DELETE" }),
};
