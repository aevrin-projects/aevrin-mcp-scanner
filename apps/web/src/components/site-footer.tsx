import Image from "next/image";
import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-[1500px] px-6 py-14 lg:px-10 xl:px-14">
        <div className="grid gap-10 sm:grid-cols-[1.5fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-3 font-semibold">
              <Image src="/logo.png" alt="" width={22} height={24} />
              <span className="text-lg tracking-[0.14em] uppercase">Aevrin</span>
            </div>
            <p className="mt-3 max-w-xs text-sm text-muted-foreground">
              MCP security scanning — know what a server can do before it touches your machine.
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
        </div>

        <div className="mt-12 border-t border-border pt-6 text-xs text-muted-foreground">
          © {new Date().getFullYear()} Aevrin. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
