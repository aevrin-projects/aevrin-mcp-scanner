"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowLeft, Gift, KeyRound, RotateCcw, ShieldOff, SlidersHorizontal } from "lucide-react";
import { ApiError } from "@/shared/api";
import { StatusPill, adminApi } from "@/entities/admin";
import type { AdminUserDetail } from "@/entities/admin";
import { Button } from "@/shared/ui/button";
import { Select } from "@/shared/ui/select";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Skeleton } from "@/shared/ui/skeleton";
import { formatDate } from "@/shared/lib/format";

const BUCKET_LABEL: Record<string, string> = {
  cli: "CLI scans",
  hook: "Hook auto-scans",
  dashboard: "Dashboard scans",
  auto_fix: "Auto-fix PRs",
};

export function AdminUserDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDetail(await adminApi.getUserDetail(id));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this account.");
    }
  }, [id]);

  useEffect(() => {
    const id = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(id);
  }, [load]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!detail) return <Skeleton className="h-96 rounded-xl" />;

  return (
    <div className="space-y-6">
      <Link href="/admin" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" />
        All accounts
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{detail.email ?? detail.user_id}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <StatusPill status={detail.status} />
            <span className="capitalize">{detail.effective_tier}</span>
            {detail.paid_until ? <span>· paid until {formatDate(detail.paid_until)}</span> : null}
            <span>· joined {detail.created_at ? formatDate(detail.created_at) : "-"}</span>
            <span>· {detail.auth_providers.join(", ") || "password"}</span>
          </div>
          {detail.status !== "active" && detail.status_reason ? (
            <p className="mt-2 text-sm text-severity-high">Reason on file: {detail.status_reason}</p>
          ) : null}
        </div>
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <GrantAddons detail={detail} onDone={load} />
          <QuotaOverrides detail={detail} onDone={load} />
          <DangerZone detail={detail} onDone={load} />
        </div>

        <div className="space-y-6">
          <Panel title="Usage this period">
            <ul className="space-y-2.5">
              {detail.usage.map((u) => (
                <li key={u.bucket} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{BUCKET_LABEL[u.bucket] ?? u.bucket}</span>
                  <span className="tabular-nums">
                    {u.used}
                    {u.limit === null ? " / ∞" : ` / ${u.limit}`}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Account">
            <dl className="space-y-2 text-sm">
              <Row label="Active API keys" value={String(detail.api_key_count)} />
              <Row label="GitHub connected" value={detail.github_connected ? "Yes" : "No"} />
              <Row label="Password sign-in" value={detail.has_password ? "Yes" : "OAuth only"} />
              <Row label="Flagged for abuse" value={detail.flagged ? "Yes" : "No"} />
            </dl>
          </Panel>

          <Panel title="Recent scans">
            {detail.recent_scans.length === 0 ? (
              <p className="text-sm text-muted-foreground">No scans yet.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {detail.recent_scans.slice(0, 6).map((s, i) => (
                  <li key={i} className="flex items-center justify-between gap-3">
                    <span className="min-w-0 truncate text-muted-foreground">{String(s.target ?? "-")}</span>
                    <span className="shrink-0 tabular-nums">{String(s.score ?? "-")}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** Comp an add-on the customer would otherwise pay for. */
function GrantAddons({ detail, onDone }: { detail: AdminUserDetail; onDone: () => Promise<void> }) {
  const [addon, setAddon] = useState<"auto_fix_prs" | "byok" | "scan_credits">("auto_fix_prs");
  const [quantity, setQuantity] = useState(10);
  const [bucket, setBucket] = useState("cli");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function grant() {
    setBusy(true);
    try {
      const result = await adminApi.grantAddon(detail.user_id, {
        addon,
        quantity,
        bucket: addon === "scan_credits" ? bucket : undefined,
        reason,
      });
      toast.success(`Granted. ${result.note ?? ""}`);
      setReason("");
      await onDone();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not grant that add-on.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Grant an add-on" icon={<Gift className="size-4 text-brand-text" />}>
      <p className="text-sm text-muted-foreground">
        Comped add-ons are indistinguishable from purchased ones at the point of use; the product reads the same
        state either way.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="addon">Add-on</Label>
          <Select
            id="addon"
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm"
            value={addon}
            onChange={(e) => setAddon(e.target.value as typeof addon)}
          >
            <option value="auto_fix_prs">Auto-fix pull requests</option>
            <option value="byok">Bring your own API key</option>
            <option value="scan_credits">Extra scan credits</option>
          </Select>
        </div>

        {addon !== "byok" ? (
          <div className="space-y-1.5">
            <Label htmlFor="qty">{addon === "auto_fix_prs" ? "Extra PRs" : "Extra scans"}</Label>
            <Input
              id="qty"
              type="number"
              min={1}
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
            />
          </div>
        ) : null}

        {addon === "scan_credits" ? (
          <div className="space-y-1.5">
            <Label htmlFor="bucket">Bucket</Label>
            <Select
              id="bucket"
              className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm"
              value={bucket}
              onChange={(e) => setBucket(e.target.value)}
            >
              <option value="cli">CLI scans</option>
              <option value="hook">Hook auto-scans</option>
              <option value="dashboard">Dashboard scans</option>
            </Select>
          </div>
        ) : null}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="grant-reason">Reason (goes to the audit log)</Label>
        <Input
          id="grant-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. goodwill after the scan outage"
        />
      </div>

      <Button disabled={busy || reason.trim().length < 3} onClick={() => void grant()}>
        {busy ? "Granting…" : "Grant add-on"}
      </Button>

      {addon === "byok" ? (
        <p className="text-xs text-muted-foreground">
          This only enables the entitlement. The customer still supplies their own key; an admin can never set or
          see it.
        </p>
      ) : null}
    </Panel>
  );
}

/** Raise or lower a specific limit, independent of plan. */
function QuotaOverrides({ detail, onDone }: { detail: AdminUserDetail; onDone: () => Promise<void> }) {
  const [bucket, setBucket] = useState("cli");
  const [value, setValue] = useState(50);
  const [unlimited, setUnlimited] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function apply() {
    setBusy(true);
    try {
      await adminApi.setOverride(detail.user_id, {
        bucket,
        limit_value: unlimited ? null : value,
        unlimited,
        reason,
      });
      toast.success("Limit override applied.");
      setReason("");
      await onDone();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not set that override.");
    } finally {
      setBusy(false);
    }
  }

  async function clear(b: string) {
    try {
      await adminApi.clearOverride(detail.user_id, b);
      toast.success("Override removed: back to the plan default.");
      await onDone();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not clear that override.");
    }
  }

  async function resetUsage(b: string) {
    try {
      await adminApi.resetUsage(detail.user_id, { bucket: b, reason: "Support reset from admin panel" });
      toast.success(`${BUCKET_LABEL[b]} usage reset to zero.`);
      await onDone();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not reset usage.");
    }
  }

  return (
    <Panel title="Rate limits" icon={<SlidersHorizontal className="size-4 text-brand-text" />}>
      <p className="text-sm text-muted-foreground">
        An override replaces the plan&apos;s limit for one bucket and applies everywhere, dashboard, CLI and hook
        alike.
      </p>

      {detail.overrides.length > 0 ? (
        <ul className="space-y-2">
          {detail.overrides.map((o) => (
            <li
              key={o.bucket}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-background/70 px-3 py-2 text-sm"
            >
              <span>
                <span className="font-medium">{BUCKET_LABEL[o.bucket] ?? o.bucket}</span>
                <span className="ml-2 text-muted-foreground">
                  {o.limit_value === null ? "unlimited" : `${o.limit_value}/month`}
                  {o.expires_at ? ` · until ${formatDate(o.expires_at)}` : " · no expiry"}
                </span>
              </span>
              <Button size="sm" variant="ghost" onClick={() => void clear(o.bucket)}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No overrides: this account is on plan defaults.</p>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="ov-bucket">Bucket</Label>
          <Select
            id="ov-bucket"
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm"
            value={bucket}
            onChange={(e) => setBucket(e.target.value)}
          >
            {Object.entries(BUCKET_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ov-value">New limit</Label>
          <Input
            id="ov-value"
            type="number"
            min={0}
            disabled={unlimited}
            value={value}
            onChange={(e) => setValue(Number(e.target.value))}
          />
        </div>
        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={unlimited} onChange={(e) => setUnlimited(e.target.checked)} />
            Unlimited
          </label>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="ov-reason">Reason</Label>
        <Input id="ov-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why?" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || reason.trim().length < 3} onClick={() => void apply()}>
          {busy ? "Applying…" : "Apply override"}
        </Button>
        <Button variant="outline" onClick={() => void resetUsage(bucket)}>
          <RotateCcw className="size-3.5" />
          Reset {BUCKET_LABEL[bucket]} usage
        </Button>
      </div>
    </Panel>
  );
}

/** Actions that need the second factor presented with the request. */
function DangerZone({ detail, onDone }: { detail: AdminUserDetail; onDone: () => Promise<void> }) {
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  async function setStatus(next: "active" | "disabled" | "blocked") {
    const consequence =
      next === "active"
        ? `Restore full access for ${detail.email}?`
        : `This immediately blocks all scans and invalidates active sessions and CLI tokens for ${detail.email}. Continue?`;
    if (!window.confirm(consequence)) return;

    setBusy(true);
    try {
      await adminApi.setStatus(detail.user_id, { status: next, reason, totp_code: code });
      toast.success(`Account ${next}.`);
      setReason("");
      setCode("");
      await onDone();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not change the account status.");
    } finally {
      setBusy(false);
    }
  }

  async function sendReset() {
    setBusy(true);
    try {
      const r = await adminApi.sendPasswordReset(detail.user_id, reason || "Support request");
      toast.success(`Reset email sent to ${r.email}.`);
      await onDone();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not send a reset.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Danger zone" icon={<ShieldOff className="size-4 text-severity-critical" />}>
      <div className="space-y-1.5">
        <Label htmlFor="dz-reason">Reason (required, audited)</Label>
        <Input id="dz-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why?" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="dz-code">Authentication code</Label>
        <Input
          id="dz-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="123456"
        />
        <p className="text-xs text-muted-foreground">
          Blocking and disabling re-prompt for your second factor even inside a live session.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {detail.status === "active" ? (
          <>
            <Button
              variant="outline"
              disabled={busy || reason.trim().length < 3 || code.trim().length < 6}
              onClick={() => void setStatus("disabled")}
            >
              Disable account
            </Button>
            <Button
              variant="destructive"
              disabled={busy || reason.trim().length < 3 || code.trim().length < 6}
              onClick={() => void setStatus("blocked")}
            >
              Block for abuse
            </Button>
          </>
        ) : (
          <Button
            disabled={busy || reason.trim().length < 3 || code.trim().length < 6}
            onClick={() => void setStatus("active")}
          >
            Restore access
          </Button>
        )}

        <Button variant="outline" disabled={busy || !detail.has_password} onClick={() => void sendReset()}>
          <KeyRound className="size-3.5" />
          Send password reset
        </Button>
      </div>

      {!detail.has_password ? (
        <p className="text-xs text-muted-foreground">
          This account signs in with {detail.auth_providers.join(" / ") || "OAuth"} and has no password to reset.
        </p>
      ) : null}
    </Panel>
  );
}

function Panel({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-5">
      <h2 className="flex items-center gap-2 text-sm font-medium">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
