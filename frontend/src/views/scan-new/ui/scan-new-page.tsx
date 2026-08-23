"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { ArrowRight, FolderGit2, Globe, FileJson, ShieldAlert } from "lucide-react";
import { ApiError } from "@/shared/api";
import { scanApi } from "@/entities/scan";
import type { DashboardTargetType, Scan } from "@/entities/scan";
import { PageHeader, SectionCard } from "@/shared/ui";
import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { Textarea } from "@/shared/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Skeleton } from "@/shared/ui/skeleton";
import { SCAN_SOURCE_LABELS, TARGET_MODE_LABELS, TARGET_TYPE_LABELS } from "@/entities/scan";
import { formatDateTime } from "@/shared/lib/format";
import { StatusBadge } from "@/entities/scan";
import { GithubRepoPicker } from "@/features/github-connect";
import { usageApi } from "@/entities/usage";

const MODE_CONTENT: Record<
  DashboardTargetType,
  {
    label: string;
    example: string;
    coverage: string;
    limitations: string;
    icon: React.ReactNode;
    cta: string;
  }
> = {
  github_repo: {
    label: "GitHub repository URL",
    example: "https://github.com/owner/repo",
    coverage: "Source, secret, dependency, and MCP manifest checks when the repository contents are discoverable.",
    limitations: "Live runtime prompt-injection testing is still out of scope.",
    icon: <FolderGit2 className="size-4 text-brand-text" />,
    cta: "Scan repository",
  },
  live_mcp_server: {
    label: "Live MCP server URL",
    example: "https://server.example.com/mcp",
    coverage: "Manifest and MCP tool-description checks when source code is not available.",
    limitations: "No repository-level static analysis, dependency, or secret scanning.",
    icon: <Globe className="size-4 text-brand-text" />,
    cta: "Scan live server",
  },
  config_paste: {
    label: "Paste MCP configuration",
    example: '{\n  "mcpServers": {\n    "my-server": { "command": "node", "args": ["server.js"] }\n  }\n}',
    coverage: "Configuration and tool-definition review before a local install.",
    limitations: "No repository clone or runtime validation unless you rescan the source or live endpoint.",
    icon: <FileJson className="size-4 text-brand-text" />,
    cta: "Scan configuration",
  },
};

const DASHBOARD_MODES: DashboardTargetType[] = ["github_repo", "live_mcp_server", "config_paste"];

function isDashboardTargetType(value: string | null): value is DashboardTargetType {
  return DASHBOARD_MODES.some((mode) => mode === value);
}

export function NewScanPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedMode = searchParams.get("mode");
  const initialMode: DashboardTargetType = isDashboardTargetType(requestedMode) ? requestedMode : "github_repo";
  const initialTarget = searchParams.get("target") ?? "";
  const [mode, setMode] = useState<DashboardTargetType>(initialMode);
  const [values, setValues] = useState<Record<DashboardTargetType, string>>({
    github_repo: initialMode === "github_repo" ? initialTarget : "",
    live_mcp_server: initialMode === "live_mcp_server" ? initialTarget : "",
    config_paste: initialMode === "config_paste" ? initialTarget : "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [recentScans, setRecentScans] = useState<Scan[] | null>(null);
  const [quotaText, setQuotaText] = useState<string | null>(null);

  useEffect(() => {
    scanApi.listScans().then(setRecentScans).catch(() => setRecentScans([]));
    usageApi
      .getUsage()
      .then((usage) => {
        const bucket = usage.buckets.find((entry) => entry.bucket === "dashboard");
        if (!bucket) return;
        setQuotaText(
          bucket.limit === null
            ? "Unlimited dashboard scans on this plan."
            : `${bucket.used} of ${bucket.limit} dashboard scans used. Resets ${formatDateTime(bucket.resets_at)}.`,
        );
      })
      .catch(() => setQuotaText(null));
  }, []);

  const currentValue = values[mode];
  const validationError = useMemo(() => validateTarget(mode, currentValue), [mode, currentValue]);

  async function handleSubmit(targetType: DashboardTargetType, target: string) {
    const error = validateTarget(targetType, target);
    if (error) {
      toast.error(error);
      return;
    }

    setSubmitting(true);
    try {
      const scan = await scanApi.createScan(targetType, target.trim());
      router.push(`/scans/${scan.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        toast.error(err.message, {
          action: { label: "Upgrade", onClick: () => router.push("/pricing") },
        });
      } else {
        toast.error(err instanceof ApiError ? err.message : "Could not start the scan.");
      }
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        pretitle="Scans"
        title="New scan"
        description="Choose the target type, review what coverage that mode can actually provide, and start one scan with clear quota and error handling."
      />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]">
        <SectionCard
          title="Scan target"
          description="GitHub source scans provide the broadest coverage. Live-server and config-only scans expose fewer signals and say so explicitly."
        >
          <Tabs value={mode} onValueChange={(value) => setMode(value as DashboardTargetType)}>
            <TabsList className="grid w-full grid-cols-3">
              {DASHBOARD_MODES.map((targetType) => (
                <TabsTrigger key={targetType} value={targetType}>
                  {TARGET_MODE_LABELS[targetType]}
                </TabsTrigger>
              ))}
            </TabsList>

            {DASHBOARD_MODES.map((targetType) => {
              const config = MODE_CONTENT[targetType];
              const value = values[targetType];
              const error = targetType === mode ? validationError : null;

              return (
                <TabsContent key={targetType} value={targetType} className="mt-6 space-y-5">
                  <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)]">
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor={`${targetType}-input`}>{config.label}</Label>
                        {targetType === "config_paste" ? (
                          <Textarea
                            id={`${targetType}-input`}
                            value={value}
                            onChange={(event) =>
                              setValues((current) => ({ ...current, [targetType]: event.target.value }))
                            }
                            className="min-h-72 font-mono text-sm"
                            placeholder={config.example}
                          />
                        ) : (
                          <Input
                            id={`${targetType}-input`}
                            value={value}
                            onChange={(event) =>
                              setValues((current) => ({ ...current, [targetType]: event.target.value }))
                            }
                            placeholder={config.example}
                          />
                        )}
                        <p className="text-xs text-muted-foreground">Example: {config.example}</p>
                        {error ? (
                          <p className="text-sm text-destructive" role="alert">
                            {error}
                          </p>
                        ) : null}
                      </div>

                      {/* Pasting a URL still works; this is the shortcut for
                          your own repositories, and it doubles as the honest
                          answer to "which repos can Fix It actually touch",
                          since both read the same installation grant. */}
                      {targetType === "github_repo" ? (
                        <div className="space-y-2 border-t border-border pt-4">
                          <p className="text-sm font-medium text-foreground">Or pick one of your repositories</p>
                          <GithubRepoPicker
                            selected={values.github_repo}
                            onSelect={(repo) =>
                              setValues((current) => ({ ...current, github_repo: repo.html_url }))
                            }
                          />
                        </div>
                      ) : null}

                      <div className="flex flex-col gap-3 rounded-xl border border-border bg-background/70 p-4 sm:flex-row sm:items-center sm:justify-between">
                        <div className="space-y-1">
                          <p className="text-sm font-medium text-foreground">{config.cta}</p>
                          <p className="text-sm text-muted-foreground">
                            {quotaText ?? "Dashboard quota appears here when usage data is available."}
                          </p>
                        </div>
                        <Button
                          disabled={submitting || Boolean(error)}
                          onClick={() => handleSubmit(targetType, values[targetType])}
                        >
                          {submitting && targetType === mode ? "Starting scan…" : config.cta}
                          <ArrowRight className="size-4" />
                        </Button>
                      </div>
                    </div>

                    <Card className="bg-background/80">
                      <CardContent className="space-y-4 pt-6">
                        <div className="flex items-center gap-2 text-sm font-medium">
                          {config.icon}
                          What this mode covers
                        </div>
                        <p className="text-sm leading-6 text-muted-foreground">{config.coverage}</p>
                        <div className="rounded-xl border border-severity-medium/25 bg-severity-medium/10 p-4">
                          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                            <ShieldAlert className="size-4 text-severity-medium" />
                            Limitations
                          </p>
                          <p className="mt-2 text-sm leading-6 text-muted-foreground">
                            {config.limitations}
                          </p>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>
              );
            })}
          </Tabs>
        </SectionCard>

        <div className="space-y-6">
          <SectionCard
            title="Recent scans"
            description="Resume the last result or review what was scanned most recently."
            action={
              <Button nativeButton={false} render={<Link href="/scans/history" />} variant="outline" size="sm">
                History
              </Button>
            }
          >
            <div className="space-y-3">
              {recentScans === null ? (
                Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-20 rounded-xl" />)
              ) : recentScans.length === 0 ? (
                <Alert>
                  <ShieldAlert className="size-4" />
                  <AlertTitle>No scans yet</AlertTitle>
                  <AlertDescription>
                    Your first successful scan becomes the reference point for future results and repeat comparisons.
                  </AlertDescription>
                </Alert>
              ) : (
                recentScans.slice(0, 4).map((scan) => (
                  <Link
                    key={scan.id}
                    href={`/scans/${scan.id}`}
                    className="flex flex-col gap-2 rounded-xl border border-border bg-background/80 p-4 transition-colors hover:bg-muted/30"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={scan.status} />
                      <span className="text-xs text-muted-foreground">{TARGET_TYPE_LABELS[scan.target_type]}</span>
                      <span className="text-xs text-muted-foreground">{SCAN_SOURCE_LABELS[scan.source]}</span>
                    </div>
                    <div className="break-all text-sm font-medium text-foreground">{scan.target}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatDateTime(scan.completed_at ?? scan.created_at)}
                    </div>
                  </Link>
                ))
              )}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

function validateTarget(mode: DashboardTargetType, value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "Enter a target before starting a scan.";

  if (mode === "config_paste") {
    try {
      JSON.parse(trimmed);
      return null;
    } catch {
      return "Paste valid JSON so the scan can inspect the MCP configuration.";
    }
  }

  try {
    const url = new URL(trimmed);
    if (!["http:", "https:"].includes(url.protocol)) {
      return "Use an http or https URL.";
    }
    if (mode === "github_repo") {
      const segments = url.pathname.split("/").filter(Boolean);
      if (url.hostname !== "github.com" || segments.length < 2) {
        return "Enter a full GitHub repository URL such as https://github.com/owner/repo.";
      }
    }
    return null;
  } catch {
    return mode === "github_repo"
      ? "Enter a valid GitHub repository URL."
      : "Enter a valid MCP server URL.";
  }
}
