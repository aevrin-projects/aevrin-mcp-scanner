"use client";

import { useEffect, useState } from "react";
import { organizationApi } from "../api/organization-api";

/** The permission keys this app renders against. The catalogue itself (labels,
 *  descriptions) is fetched from `/orgs/permissions`; these are only the keys a
 *  page checks before offering a control. */
export const WORKSPACE_PERMISSIONS = {
  scansRun: "scans.run",
  scansDelete: "scans.delete",
  findingsTriage: "findings.triage",
  agentsDelete: "agents.delete",
  membersManage: "members.manage",
  rolesManage: "roles.manage",
  orgManage: "org.manage",
} as const;

export type WorkspacePermission = (typeof WORKSPACE_PERMISSIONS)[keyof typeof WORKSPACE_PERMISSIONS];

export interface WorkspaceGrant {
  /** False only when the caller is in a workspace whose role lacks the
   *  permission. */
  allowed: boolean;
  /** The caller's workspace role, for saying why a control is missing. */
  role: string | null;
}

/**
 * Whether to offer a control, from the same `my_permissions` the workspace
 * page reads. Not a permission check: the API refuses on its own, and this
 * only keeps a page from offering a button whose one outcome is a 403.
 *
 * Someone in no workspace acts on personal rows and is always allowed. Until
 * the membership arrives, and if it cannot be read, the control is offered:
 * the server still decides, and hiding every action because one read failed
 * would make the page look broken rather than refused.
 */
export function useWorkspacePermission(permission: WorkspacePermission): WorkspaceGrant {
  const [grant, setGrant] = useState<WorkspaceGrant>({ allowed: true, role: null });

  useEffect(() => {
    let cancelled = false;
    organizationApi
      .getMembership()
      .then((membership) => {
        if (cancelled) return;
        const org = membership.organization;
        setGrant(
          org
            ? { allowed: org.my_permissions.includes(permission), role: org.my_role }
            : { allowed: true, role: null },
        );
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [permission]);

  return grant;
}
