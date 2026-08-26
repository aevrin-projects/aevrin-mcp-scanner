/** A permission the server will accept in a role. The catalogue is fetched
 *  rather than restated here, so the role editor can never offer a switch the
 *  API would reject. */
export interface OrgPermission {
  key: string;
  label: string;
  description: string;
}

export interface Role {
  id: string;
  name: string;
  permissions: string[];
  /** The owner's role: holds everything, and cannot be edited, deleted or
   *  assigned to anyone else. */
  is_owner_role: boolean;
  member_count: number;
}

export interface Member {
  user_id: string;
  email: string | null;
  role_id: string;
  role_name: string;
  is_owner: boolean;
  joined_at: string;
}

export interface Invite {
  id: string;
  email: string;
  role_id: string;
  role_name: string;
  created_at: string;
  expires_at: string;
}

export interface Organization {
  id: string;
  name: string;
  seats: number;
  /** Members plus invites nobody has accepted yet: an open invite holds a
   *  seat, or the limit would be a race between colleagues as they arrive. */
  seats_used: number;
  owner_id: string;
  created_at: string;
  my_role: string;
  my_permissions: string[];
  is_owner: boolean;
}

/** `organization` is null for someone not in a workspace, which is every
 *  account until they make one. */
export interface Membership {
  organization: Organization | null;
  pending_invites: Invite[];
}
