"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Scan, TargetType } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { UsageMeters } from "@/components/usage-meters";
import Link from "next/link";

const DEMO_SERVERS = [
  { label: "modelcontextprotocol/servers", target: "https://github.com/modelcontextprotocol/servers" },
  { label: "github/github-mcp-server", target: "https://github.com/github/github-mcp-server" },
];

const TARGET_LABELS: Record<TargetType, string> = {
  github_repo: "GitHub repository URL",
  live_mcp_server: "Live MCP server URL",
  config_paste: "Paste config (mcp.json)",
};

export default function DashboardPage() {
  const router = useRouter();
  const [tab, setTab] = useState<TargetType>("github_repo");
  const [target, setTarget] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [recentScans, setRecentScans] = useState<Scan[] | null>(null);

  useEffect(() => {
    api
      .listScans()
      .then(setRecentScans)
      .catch(() => setRecentScans([]));
  }, []);

  async function submit(target_type: TargetType, targetValue: string) {
    if (!targetValue.trim()) {
      toast.error("Enter a target before starting a scan.");
      return;
    }
    setSubmitting(true);
    try {
      const scan = await api.createScan(target_type, targetValue.trim());
      router.push(`/scans/${scan.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        // Quota exceeded — the api returns a structured body (bucket,
        // resets_at, upgrade_url) but ApiError only carries `.message`
        // (already the human-readable `detail` string) at this layer, so
        // surface it plus a direct upgrade link rather than a bare toast.
        toast.error(err.message, {
          action: { label: "Upgrade", onClick: () => router.push("/pricing") },
        });
      } else {
        const message = err instanceof ApiError ? err.message : "Could not start the scan.";
        toast.error(message);
      }
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">New scan</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Scan an MCP server against the OWASP MCP Top 10 using established open-source security
        tools.
      </p>

      <div className="mt-6">
        <UsageMeters />
      </div>

      <Card className="mt-8">
        <CardContent className="pt-6">
          <Tabs value={tab} onValueChange={(v) => setTab(v as TargetType)}>
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="github_repo">GitHub repo</TabsTrigger>
              <TabsTrigger value="live_mcp_server">Live server</TabsTrigger>
              <TabsTrigger value="config_paste">Paste config</TabsTrigger>
            </TabsList>

            <TabsContent value="github_repo" className="mt-6 flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="github-target">{TARGET_LABELS.github_repo}</Label>
                <Input
                  id="github-target"
                  placeholder="https://github.com/owner/repo"
                  value={tab === "github_repo" ? target : ""}
                  onChange={(e) => setTarget(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Enables the full scanner set: static analysis, secrets, dependencies, and
                  tool-description checks.
                </p>
              </div>
              <Button
                disabled={submitting}
                onClick={() => submit("github_repo", target)}
                data-testid="submit-scan"
              >
                {submitting ? "Starting scan…" : "Scan repository"}
              </Button>
              <div className="flex flex-wrap gap-2">
                {DEMO_SERVERS.map((demo) => (
                  <Button
                    key={demo.target}
                    variant="outline"
                    size="sm"
                    disabled={submitting}
                    onClick={() => {
                      setTarget(demo.target);
                      submit("github_repo", demo.target);
                    }}
                  >
                    {demo.label}
                  </Button>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="live_mcp_server" className="mt-6 flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="live-target">{TARGET_LABELS.live_mcp_server}</Label>
                <Input
                  id="live-target"
                  placeholder="https://my-mcp-server.example.com"
                  value={tab === "live_mcp_server" ? target : ""}
                  onChange={(e) => setTarget(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Manifest-level checks only, via MCP-Shield and mcp-scan.
                </p>
              </div>
              <Button disabled={submitting} onClick={() => submit("live_mcp_server", target)}>
                {submitting ? "Starting scan…" : "Scan live server"}
              </Button>
            </TabsContent>

            <TabsContent value="config_paste" className="mt-6 flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="config-target">{TARGET_LABELS.config_paste}</Label>
                <Textarea
                  id="config-target"
                  placeholder={'{\n  "mcpServers": {\n    "my-server": { "command": "node", "args": ["server.js"] }\n  }\n}'}
                  className="min-h-40 font-mono text-sm"
                  value={tab === "config_paste" ? target : ""}
                  onChange={(e) => setTarget(e.target.value)}
                />
              </div>
              <Button disabled={submitting} onClick={() => submit("config_paste", target)}>
                {submitting ? "Starting scan…" : "Scan config"}
              </Button>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <div className="mt-10">
        <h2 className="text-sm font-medium text-muted-foreground">Recent scans</h2>
        <div className="mt-3 flex flex-col gap-2">
          {recentScans === null &&
            Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
          {recentScans?.length === 0 && (
            <p className="text-sm text-muted-foreground">No scans yet.</p>
          )}
          {recentScans?.map((scan) => (
            <Link
              key={scan.id}
              href={`/scans/${scan.id}`}
              className="flex items-center justify-between rounded-lg border border-border px-4 py-3 text-sm hover:bg-accent"
            >
              <span className="truncate font-mono">{scan.target}</span>
              <div className="flex items-center gap-3">
                {scan.score !== null && <Badge variant="outline">{scan.score}/100</Badge>}
                <Badge variant={scan.status === "completed" ? "secondary" : "outline"}>
                  {scan.status}
                </Badge>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
