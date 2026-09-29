/** Workspace rows (scans, agents) say whose they are when they are not the
 *  caller's own. The API sends `created_by` only for current members of the
 *  caller's workspace, the same emails the workspace page lists. */
export interface Attributed {
  mine: boolean;
  created_by: string | null;
}

/** Who a colleague's row belongs to, or null for the caller's own. */
export function workspaceAuthor(row: Attributed): string | null {
  if (row.mine) return null;
  return row.created_by ?? "a former member";
}
