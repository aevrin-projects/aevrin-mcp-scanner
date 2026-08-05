"use client";

import * as React from "react";
import { AlertTriangle, ArrowRight, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-[2rem]">
          {title}
        </h1>
        {description ? (
          <p className="max-w-3xl text-sm leading-6 text-muted-foreground sm:text-[0.95rem]">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  suffix,
  detail,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  /** Small trailing qualifier on the value line — "/100", "4 critical". Keeps
   *  the headline number dominant while the qualifier stays readable. */
  suffix?: React.ReactNode;
  detail?: React.ReactNode;
  tone?: "default" | "critical" | "high" | "success";
}) {
  const toneClass =
    tone === "critical"
      ? "border-severity-critical/35"
      : tone === "high"
        ? "border-severity-high/35"
        : tone === "success"
          ? "border-brand/35"
          : "border-border";

  return (
    <Card className={cn("gap-0 rounded-xl bg-card py-4", toneClass)}>
      <CardHeader className="gap-0 px-4 pb-2">
        <CardDescription className="text-xs font-medium text-muted-foreground">{label}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1 px-4">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold tracking-tight text-foreground tabular-nums">{value}</span>
          {suffix ? <span className="text-xs text-muted-foreground">{suffix}</span> : null}
        </div>
        {detail ? <p className="text-xs leading-5 text-muted-foreground">{detail}</p> : null}
      </CardContent>
    </Card>
  );
}

export function SectionCard({
  title,
  description,
  action,
  children,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("bg-card/80", className)}>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <CardTitle className="text-lg">{title}</CardTitle>
          {description ? (
            <CardDescription className="max-w-3xl text-sm leading-6">
              {description}
            </CardDescription>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function EmptyState({
  title,
  body,
  actionLabel,
  onAction,
  icon = "shield",
}: {
  title: string;
  body: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  icon?: "shield" | "attention";
}) {
  const Icon = icon === "attention" ? AlertTriangle : ShieldCheck;

  return (
    <div className="rounded-xl border border-dashed border-border bg-card/40 p-8 text-left">
      <div className="flex max-w-2xl flex-col gap-4">
        <div className="flex size-11 items-center justify-center rounded-full border border-border bg-background/80">
          <Icon className="size-5 text-brand-text" />
        </div>
        <div className="space-y-2">
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          <p className="text-sm leading-6 text-muted-foreground">{body}</p>
        </div>
        {actionLabel && onAction ? (
          <div>
            <Button onClick={onAction}>
              {actionLabel}
              <ArrowRight className="size-4" />
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
