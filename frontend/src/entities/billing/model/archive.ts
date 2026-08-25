"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Archiving and hiding a payment are display preferences, never data. A row in
 * billing history is a financial record: it stays on the account, stays in the
 * API response, and stays available to support either way. All this decides is
 * what the billing page draws.
 *
 * That is also why it lives in localStorage rather than on the server. There
 * is deliberately no endpoint that can mark a charge as put away, so nothing
 * here can be the reason a customer cannot find a payment they made.
 *
 * Archived rows are keyed by payment id, which is unique per account, so two
 * people sharing a browser cannot hide each other's history: the stored ids
 * simply never match the other account's payments.
 */
const ARCHIVED_KEY = "aevrin.billing.archived-payments";
const HIDDEN_KEY = "aevrin.billing.history-hidden";

/** Storage throws outright in some private-browsing modes, and a hand-edited
 *  value can hold anything at all. Neither is a reason to fail to render
 *  invoices, so every read falls back to showing everything. */
function readArchived(): Set<string> {
  try {
    const raw = window.localStorage.getItem(ARCHIVED_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((id): id is string => typeof id === "string"));
  } catch {
    return new Set();
  }
}

function readHidden(): boolean {
  try {
    return window.localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // The cache below still holds the change, so a preference that cannot be
    // saved at least applies for this visit.
  }
}

// An external store rather than state loaded in an effect: localStorage does
// not exist while the page is prerendered, so the server snapshot is the
// show-everything default and React swaps in the real one at hydration. The
// payments themselves arrive over the network, which is slower than that, so
// the table never draws an archived row and then pulls it away.
const EMPTY_SET: ReadonlySet<string> = new Set<string>();

const listeners = new Set<() => void>();
let archivedCache: ReadonlySet<string> | null = null;
let hiddenCache: boolean | null = null;
let watchingStorage = false;

function notify() {
  for (const listener of listeners) listener();
}

/** Another tab archiving a row should not leave this one still showing it. */
function onStorageChanged() {
  archivedCache = null;
  hiddenCache = null;
  notify();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!watchingStorage) {
    window.addEventListener("storage", onStorageChanged);
    watchingStorage = true;
  }
  return () => {
    listeners.delete(listener);
  };
}

// Cached because useSyncExternalStore compares snapshots by identity: parsing
// the JSON afresh on every render would return a new Set each time and loop.
function getArchived(): ReadonlySet<string> {
  archivedCache ??= readArchived();
  return archivedCache;
}

function getHidden(): boolean {
  hiddenCache ??= readHidden();
  return hiddenCache;
}

function getArchivedOnServer(): ReadonlySet<string> {
  return EMPTY_SET;
}

function getHiddenOnServer(): boolean {
  return false;
}

export interface BillingHistoryPrefs {
  archived: ReadonlySet<string>;
  hidden: boolean;
  archive: (paymentId: string) => void;
  restore: (paymentId: string) => void;
  restoreAll: () => void;
  setHidden: (hidden: boolean) => void;
}

export function useBillingHistoryPrefs(): BillingHistoryPrefs {
  const archived = useSyncExternalStore(subscribe, getArchived, getArchivedOnServer);
  const hidden = useSyncExternalStore(subscribe, getHidden, getHiddenOnServer);

  const update = useCallback((change: (next: Set<string>) => void) => {
    const next = new Set(getArchived());
    change(next);
    archivedCache = next;
    write(ARCHIVED_KEY, JSON.stringify([...next]));
    notify();
  }, []);

  const archive = useCallback((paymentId: string) => update((next) => next.add(paymentId)), [update]);
  const restore = useCallback((paymentId: string) => update((next) => next.delete(paymentId)), [update]);
  const restoreAll = useCallback(() => update((next) => next.clear()), [update]);

  const setHidden = useCallback((next: boolean) => {
    hiddenCache = next;
    write(HIDDEN_KEY, next ? "1" : "0");
    notify();
  }, []);

  return { archived, hidden, archive, restore, restoreAll, setHidden };
}
