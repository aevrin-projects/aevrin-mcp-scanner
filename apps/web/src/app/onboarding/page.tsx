"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  ChevronLeft,
  FileCode2,
  GitBranch,
  GitPullRequest,
  Globe,
  KeyRound,
  RefreshCcw,
  ScanSearch,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// Onboarding completion is derived, never stored in a new column: a real
// GitHub installation is the actual signal, and "skip" is a local preference.
// That keeps this flow migration-free and means connecting GitHub later (from
// settings, or the first time Fix It runs) resolves the same state without a
// second source of truth.
const SKIP_KEY = "aevrin.onboarding.skipped";

type Path = "repository" | "server" | "developer";

const PATHS: {
  id: Path;
  icon: typeof ScanSearch;
  title: string;
  tagline: string;
  features: { icon: typeof ScanSearch; label: string }[];
  cta: string;
  /** Where this path sends you once onboarding finishes. */
  destination: string;
  /** Whether this path genuinely benefits from a GitHub App install. */
  needsGithub: boolean;
}[] = [
  {
    id: "repository",
    icon: GitBranch,
    title: "Scan a repository",
    tagline: "Broadest coverage — source, dependencies, and secrets together.",
    features: [
      { icon: ScanSearch, label: "Static analysis and secret detection" },
      { icon: ShieldCheck, label: "Dependency CVEs with EPSS and CISA KEV" },
      { icon: GitPullRequest, label: "Fix It opens draft pull requests" },
      { icon: RefreshCcw, label: "Re-scan to verify a fix actually landed" },
    ],
    cta: "Scan a repository",
    destination: "/scans/new",
    needsGithub: true,
  },
  {
    id: "server",
    icon: Globe,
    title: "Check a live server or config",
    tagline: "Fastest path when you're deciding whether to install something.",
    features: [
      { icon: Globe, label: "Live MCP server endpoint inspection" },
      { icon: FileCode2, label: "Paste an mcp.json configuration" },
      { icon: ShieldCheck, label: "Declared-tool and manifest checks" },
      { icon: ScanSearch, label: "No repository access required" },
    ],
    cta: "Check a server",
    destination: "/scans/new",
    needsGithub: false,
  },
  {
    id: "developer",
    icon: TerminalSquare,
    title: "Set up CLI and hook",
    tagline: "Bring checks into the terminal and block unsafe installs.",
    features: [
      { icon: TerminalSquare, label: "Scan locally with the aevrin CLI" },
      { icon: ShieldCheck, label: "Claude Code hook blocks risky MCP adds" },
      { icon: KeyRound, label: "API keys for CI and automation" },
      { icon: RefreshCcw, label: "Same findings across every surface" },
    ],
    cta: "Set up tooling",
    destination: "/integrations",
    needsGithub: false,
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [step, setStep] = useState(0);
  const [path, setPath] = useState<Path | null>(null);
  const [connecting, setConnecting] = useState(false);

  const selected = PATHS.find((entry) => entry.id === path) ?? null;
  // The GitHub step is only shown for paths it genuinely helps, so nobody is
  // asked for repository access to check a pasted config.
  const totalSteps = selected?.needsGithub ? 3 : 2;

  useEffect(() => {
    let cancelled = false;

    async function resolveState() {
      if (typeof window !== "undefined" && window.localStorage.getItem(SKIP_KEY) === "1") {
        router.replace("/dashboard");
        return;
      }
      try {
        const status = await api.getGithubStatus();
        if (!cancelled && status.connected) {
          router.replace("/dashboard");
          return;
        }
      } catch {
        // Status unavailable (API down, or auto-fix not configured yet) —
        // showing the flow is safe; the connect button surfaces the real
        // error if it's genuinely broken.
      }
      if (!cancelled) setChecking(false);
    }

    void resolveState();
    return () => {
      cancelled = true;
    };
  }, [router]);

  function choosePath(next: Path) {
    setPath(next);
    setStep(1);
  }

  async function connectGithub() {
    setConnecting(true);
    try {
      const { url } = await api.getGithubInstallUrl();
      window.location.href = url;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start the GitHub connection.");
      setConnecting(false);
    }
  }

  function finish(destination: string) {
    window.localStorage.setItem(SKIP_KEY, "1");
    router.replace(destination);
  }

  if (checking) {
    return (
      <div className="mx-auto flex min-h-[calc(100svh-4.5rem)] w-full max-w-4xl flex-col justify-center gap-4 px-6">
        <Skeleton className="mx-auto h-8 w-56 rounded-lg" />
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-64 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-[calc(100svh-4.5rem)] flex-col px-6 py-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {step > 0 ? (
            <button
              type="button"
              onClick={() => setStep((current) => current - 1)}
              className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <ChevronLeft className="size-4" />
              Back
            </button>
          ) : (
            <span className="flex items-center gap-2">
              <Image src="/logo.png" alt="" width={20} height={22} priority />
              <span className="text-sm font-medium tracking-[0.14em] text-muted-foreground uppercase">Aevrin</span>
            </span>
          )}
        </div>

        <ol className="flex items-center gap-1.5" aria-label={`Step ${step + 1} of ${totalSteps}`}>
          {Array.from({ length: totalSteps }).map((_, index) => (
            <li
              key={index}
              aria-current={index === step ? "step" : undefined}
              className={cn(
                "h-1 rounded-full transition-all",
                index === step ? "w-6 bg-foreground" : index < step ? "w-1.5 bg-muted-foreground" : "w-1.5 bg-border",
              )}
            />
          ))}
        </ol>

        <div className="w-16 text-right">
          <button
            type="button"
            onClick={() => finish("/dashboard")}
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Skip
          </button>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center py-10">
        {step === 0 ? (
          <div className="w-full max-w-4xl">
            <div className="text-center">
              <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">How do you want to start?</h1>
              <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
                Every path uses the same scanners and the same findings. Pick whichever matches what you have in
                front of you — you can use the others later.
              </p>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {PATHS.map((entry) => (
                <div
                  key={entry.id}
                  className="flex flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:border-muted-foreground/40"
                >
                  <div className="flex items-center gap-2">
                    <entry.icon className="size-4 text-foreground" aria-hidden="true" />
                    <h2 className="text-[15px] font-medium text-foreground">{entry.title}</h2>
                  </div>
                  <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{entry.tagline}</p>

                  <ul className="mt-4 flex flex-1 flex-col gap-2.5">
                    {entry.features.map((feature) => (
                      <li key={feature.label} className="flex items-start gap-2 text-[13px] text-muted-foreground">
                        <feature.icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                        <span>{feature.label}</span>
                      </li>
                    ))}
                  </ul>

                  <Button className="mt-5 w-full" onClick={() => choosePath(entry.id)}>
                    {entry.cta}
                    <ArrowRight className="size-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {step === 1 && selected?.needsGithub ? (
          <div className="w-full max-w-xl">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Connect GitHub</h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Aevrin scans public repositories without this. Connecting adds private-repository scanning and lets
              Fix It open pull requests for you.
            </p>

            <ul className="mt-6 flex flex-col gap-3">
              {[
                {
                  icon: GitBranch,
                  title: "Private repositories",
                  body: "Scan code that isn't publicly reachable.",
                },
                {
                  icon: GitPullRequest,
                  title: "Fix It pull requests",
                  body: "A patch is generated, re-verified by the scanner that flagged it, then opened as a draft PR — never merged automatically.",
                },
                {
                  icon: ShieldCheck,
                  title: "You choose the repositories",
                  body: "Access is scoped during install and revocable from GitHub at any time.",
                },
              ].map((item) => (
                <li key={item.title} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4">
                  <item.icon className="mt-0.5 size-4 shrink-0 text-brand-text" aria-hidden="true" />
                  <div>
                    <p className="text-[13px] font-medium text-foreground">{item.title}</p>
                    <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{item.body}</p>
                  </div>
                </li>
              ))}
            </ul>

            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <Button disabled={connecting} onClick={() => void connectGithub()} className="h-10 px-5">
                {connecting ? "Redirecting to GitHub…" : "Connect GitHub"}
                {!connecting && <ArrowRight className="size-4" />}
              </Button>
              <Button variant="ghost" onClick={() => setStep(2)} className="h-10 px-5 text-muted-foreground">
                Add later
              </Button>
            </div>
          </div>
        ) : null}

        {(step === 2 || (step === 1 && selected && !selected.needsGithub)) && selected ? (
          <div className="w-full max-w-md text-center">
            <div className="mx-auto flex size-10 items-center justify-center rounded-full border border-border bg-card">
              <Check className="size-4 text-foreground" aria-hidden="true" />
            </div>
            <h1 className="mt-5 text-2xl font-semibold tracking-tight">You&apos;re set up</h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {selected.id === "developer"
                ? "Install the CLI and add the Claude Code hook from the integrations page."
                : "Start your first scan — results land in the dashboard when it finishes."}
            </p>

            <div className="mt-6 flex flex-col gap-2">
              <Button onClick={() => finish(selected.destination)} className="h-10">
                {selected.id === "developer" ? "Go to integrations" : "Start first scan"}
                <ArrowRight className="size-4" />
              </Button>
              <button
                type="button"
                onClick={() => finish("/dashboard")}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Go to dashboard instead
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <p className="text-center text-xs text-muted-foreground">
        Need help getting started?{" "}
        <Link href="/docs" className={cn(buttonVariants({ variant: "link", size: "xs" }), "h-auto px-0 text-xs")}>
          Read the docs
        </Link>
      </p>
    </div>
  );
}
