import Image from "next/image";
import Link from "next/link";
import { Mail } from "lucide-react";
import { buttonVariants } from "@/shared/ui/button";

// /cli, /status, /terms, /privacy, /refund, and /contact moved to
// frontend-public/, at the root domain (DECISIONS.md ADR-011) - this app
// (now at app.mcp.aevrin.net) no longer has any of them itself.
const MARKETING_ORIGIN = "https://mcp.aevrin.net";

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-[1500px] px-6 py-14 lg:px-10 xl:px-14">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1.2fr]">
          <div>
            <div className="flex items-center gap-3 font-semibold">
              <Image src="/logo.png" alt="" width={22} height={24} />
              <span className="text-lg tracking-[0.14em] uppercase">Aevrin</span>
            </div>
            <p className="mt-3 max-w-xs text-sm text-muted-foreground">
              Review MCP server code, dependencies, configuration, and declared tools before installation.
            </p>
          </div>

          <div className="flex flex-col gap-2 text-sm">
            <span className="font-medium text-foreground">Product</span>
            <Link href="/pricing" className="text-muted-foreground hover:text-foreground">
              Pricing
            </Link>
            <Link href="https://docs.mcp.aevrin.net" className="text-muted-foreground hover:text-foreground">
              Docs
            </Link>
            <Link href={`${MARKETING_ORIGIN}/cli`} className="text-muted-foreground hover:text-foreground">
              CLI setup
            </Link>
            <Link href={`${MARKETING_ORIGIN}/status`} className="text-muted-foreground hover:text-foreground">
              Status
            </Link>
          </div>

          <div className="flex flex-col gap-2 text-sm">
            <span className="font-medium text-foreground">Legal</span>
            <Link href={`${MARKETING_ORIGIN}/terms`} className="text-muted-foreground hover:text-foreground">
              Terms of Service
            </Link>
            <Link href={`${MARKETING_ORIGIN}/privacy`} className="text-muted-foreground hover:text-foreground">
              Privacy Policy
            </Link>
            {/* Both are required to be directly linkable, not buried inside
                the terms: payment providers check for them during merchant
                review, and a customer chasing a charge looks in the footer. */}
            <Link href={`${MARKETING_ORIGIN}/refund`} className="text-muted-foreground hover:text-foreground">
              Refunds &amp; Cancellation
            </Link>
            <Link href={`${MARKETING_ORIGIN}/contact`} className="text-muted-foreground hover:text-foreground">
              Contact
            </Link>
          </div>

          <div className="flex flex-col items-start gap-3 text-sm">
            <span className="font-medium text-foreground">Support</span>
            <p className="max-w-xs leading-6 text-muted-foreground">
              Questions about a scan, account, or integration? Contact the Aevrin team.
            </p>
            <a href="mailto:ujjwal@aevrin.net?subject=Aevrin%20support" className={buttonVariants({ size: "sm", variant: "outline" })}>
              <Mail className="size-4" />
              Contact support
            </a>
            <a href="mailto:ujjwal@aevrin.net" className="text-muted-foreground hover:text-foreground">
              ujjwal@aevrin.net
            </a>
          </div>
        </div>

        <div className="mt-12 border-t border-border pt-6" />
      </div>
    </footer>
  );
}
