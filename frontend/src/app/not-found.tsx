import Link from "next/link";
import { ArrowLeft, SearchX } from "lucide-react";
import { buttonVariants } from "@/shared/ui/button";

export default function NotFound() {
  return (
    <section className="mx-auto flex min-h-[70vh] max-w-3xl items-center px-6 py-24 text-center">
      <div className="w-full rounded-xl border border-border bg-card/70 p-8 sm:p-12">
        <div className="mx-auto flex size-12 items-center justify-center rounded-full border border-border bg-background">
          <SearchX className="size-5 text-brand-text" />
        </div>
        <p className="mt-6 text-xs font-medium uppercase tracking-[0.16em] text-brand-text">404</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Page not found</h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-muted-foreground sm:text-base">
          This route does not exist. Return to the product overview or start a new security scan.
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          {/* The marketing home page moved to frontend-public/ (DECISIONS.md
              ADR-011) - this app no longer has a "/" route of its own. */}
          <Link href="https://mcp.aevrin.net" className={buttonVariants({ variant: "outline" })}>
            <ArrowLeft className="size-4" />
            Home
          </Link>
          <Link href="/scans/new" className={buttonVariants()}>Start a scan</Link>
        </div>
      </div>
    </section>
  );
}
