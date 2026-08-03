import Image from "next/image";
import Link from "next/link";
import { Mail } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";

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
            <Link href="/docs" className="text-muted-foreground hover:text-foreground">
              Docs
            </Link>
            <Link href="/cli" className="text-muted-foreground hover:text-foreground">
              CLI setup
            </Link>
            <Link href="/status" className="text-muted-foreground hover:text-foreground">
              Status
            </Link>
          </div>

          <div className="flex flex-col gap-2 text-sm">
            <span className="font-medium text-foreground">Legal</span>
            <Link href="/terms" className="text-muted-foreground hover:text-foreground">
              Terms of Service
            </Link>
            <Link href="/privacy" className="text-muted-foreground hover:text-foreground">
              Privacy Policy
            </Link>
          </div>

          <div className="flex flex-col items-start gap-3 text-sm">
            <span className="font-medium text-foreground">Support</span>
            <p className="max-w-xs leading-6 text-muted-foreground">
              Questions about a scan, account, or integration? Contact the Aevrin team.
            </p>
            <a href="mailto:support@aevrin.net" className={buttonVariants({ size: "sm", variant: "outline" })}>
              <Mail className="size-4" />
              Contact support
            </a>
            <a href="mailto:support@aevrin.net" className="text-muted-foreground hover:text-foreground">
              support@aevrin.net
            </a>
          </div>
        </div>

        <div className="mt-12 border-t border-border pt-6 text-xs text-muted-foreground">
          © {new Date().getFullYear()} Aevrin. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
