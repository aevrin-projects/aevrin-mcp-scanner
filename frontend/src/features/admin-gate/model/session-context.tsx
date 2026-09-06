"use client";

import { createContext, useContext } from "react";

/**
 * Who the gate let in.
 *
 * `AdminGate` already resolves the admin session - it has to, to decide
 * whether to render anything at all - and used to throw the email away. The
 * shell needs it for the account menu, so it is handed down rather than
 * fetched a second time: two independent reads of the same session can
 * disagree for a few seconds after it goes stale, and the one in the sidebar
 * would be the one nobody re-checks.
 *
 * This carries identity for display only. Every admin endpoint re-derives
 * admin status, TOTP enrolment and session freshness server-side, so nothing
 * here is load-bearing for access control.
 */
export type AdminSession = { email: string | null };

const AdminSessionContext = createContext<AdminSession>({ email: null });

export const AdminSessionProvider = AdminSessionContext.Provider;

export function useAdminSession(): AdminSession {
  return useContext(AdminSessionContext);
}
