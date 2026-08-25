"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, GitBranch, Lock, Search, ShieldQuestion } from "lucide-react";
import { ApiError } from "@/shared/api";
import { githubApi } from "@/entities/github";
import type { GithubRepo } from "@/entities/github";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/skeleton";
import { cn } from "@/shared/lib/utils";

/**
 * Pick one of your own repositories instead of pasting a URL.
 *
 * The list comes from the GitHub App *installation*, so it shows exactly
 * what was granted at install time, a few hand-picked repos, or all of
 * them, so the list here and what Aevrin can actually reach can never
 * disagree.
 *
 * The MCP label is a hint for scanning the list, never a gate. The
 * heuristic only looks for a committed MCP config or an SDK dependency, so
 * a perfectly good server that ships neither would read as "not MCP".
 * Nothing here is disabled on the strength of it, a repo it doesn't
 * recognise stays fully selectable, and the scan itself re-checks and says
 * so honestly if no MCP server turns up.
 */
export function GithubRepoPicker({
  onSelect,
  selected,
}: {
  onSelect: (repo: GithubRepo) => void;
  selected?: string | null;
}) {
  const [state, setState] = useState<
    { status: "loading" } | { status: "error"; message: string } | { status: "ready"; connected: boolean; repos: GithubRepo[] }
  >({ status: "loading" });
  const [query, setQuery] = useState("");
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    githubApi
      .getRepos()
      .then((result) => {
        if (!cancelled) setState({ status: "ready", connected: result.connected, repos: result.repos });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            status: "error",
            message: err instanceof ApiError ? err.message : "Could not load your repositories.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    if (state.status !== "ready") return [];
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? state.repos.filter((repo) => repo.full_name.toLowerCase().includes(needle))
      : state.repos;
    // Likely-MCP repos first: that's what someone opening this list is
    // almost always looking for, then most recently pushed.
    return [...matched].sort((a, b) => {
      if (a.looks_like_mcp !== b.looks_like_mcp) return a.looks_like_mcp ? -1 : 1;
      return (b.pushed_at ?? "").localeCompare(a.pushed_at ?? "");
    });
  }, [query, state]);

  async function connect() {
    setConnecting(true);
    try {
      const { url } = await githubApi.getInstallUrl();
      window.location.href = url;
    } catch {
      setConnecting(false);
    }
  }

  if (state.status === "loading") {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-12 rounded-lg" />
        ))}
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <p className="rounded-lg border border-border bg-background/70 px-4 py-3 text-sm text-muted-foreground">
        {state.message}
      </p>
    );
  }

  if (!state.connected) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-border px-4 py-5">
        <p className="text-sm font-medium">Connect GitHub to pick from your repositories</p>
        <p className="text-sm text-muted-foreground">
          You choose which repositories to grant: a few, or all of them. The same grant is what lets Aevrin read
          pull requests.
        </p>
        <Button variant="outline" size="sm" disabled={connecting} onClick={() => void connect()}>
          <GitBranch className="size-4" />
          {connecting ? "Redirecting…" : "Connect GitHub"}
        </Button>
      </div>
    );
  }

  if (state.repos.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-5">
        <p className="text-sm font-medium">No repositories granted</p>
        <p className="mt-1 text-sm text-muted-foreground">
          GitHub is connected, but the installation has access to no repositories. Adjust it on GitHub and reload.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="pl-9"
          placeholder="Filter your repositories"
          aria-label="Filter repositories"
        />
      </div>

      <ul className="max-h-80 divide-y divide-border overflow-y-auto rounded-xl border border-border">
        {visible.map((repo) => {
          const isSelected = selected === repo.html_url;
          return (
            <li key={repo.full_name}>
              <button
                type="button"
                onClick={() => onSelect(repo)}
                aria-pressed={isSelected}
                className={cn(
                  "flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-muted/40",
                  isSelected && "bg-brand/10",
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-[13px] text-foreground">{repo.full_name}</span>
                    {repo.private ? (
                      <Lock aria-label="Private repository" className="size-3 shrink-0 text-muted-foreground" />
                    ) : null}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    {repo.default_branch}
                    {repo.pushed_at ? ` · pushed ${new Date(repo.pushed_at).toLocaleDateString()}` : ""}
                  </span>
                </span>

                {repo.looks_like_mcp === true ? (
                  <span className="shrink-0 rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 text-[10px] font-medium text-brand-text">
                    MCP
                  </span>
                ) : repo.looks_like_mcp === null ? (
                  <ShieldQuestion
                    aria-label="Could not check whether this is an MCP repository"
                    className="size-3.5 shrink-0 text-muted-foreground"
                  />
                ) : null}

                {isSelected ? <Check className="size-4 shrink-0 text-brand-text" /> : null}
              </button>
            </li>
          );
        })}
        {visible.length === 0 ? (
          <li className="px-3.5 py-6 text-center text-[13px] text-muted-foreground">
            No repositories match that filter.
          </li>
        ) : null}
      </ul>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        The MCP tag is a quick check for a committed MCP config or SDK dependency. Repos without it are still
        scannable, the scan re-checks and tells you if it finds no MCP server.
      </p>
    </div>
  );
}
