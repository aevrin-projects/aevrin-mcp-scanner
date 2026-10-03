import Image from "next/image";
import Link from "next/link";
import { Mail } from "lucide-react";

const PRODUCT_LINKS = [
  { label: "Pricing", href: "/#pricing" },
  { label: "Docs", href: "https://docs.mcp.aevrin.net" },
  { label: "CLI setup", href: "/cli" },
  { label: "Status", href: "/status" },
];

// Both /refund and /contact are required to be directly linkable, not buried
// inside the terms: payment providers check for them during merchant review,
// and a customer chasing a charge looks in the footer.
const LEGAL_LINKS = [
  { label: "Terms of Service", href: "/terms" },
  { label: "Privacy Policy", href: "/privacy" },
  { label: "Refunds & Cancellation", href: "/refund" },
  { label: "Contact", href: "/contact" },
];

const linkClass =
  "rounded-sm text-[var(--mk-muted)] transition-colors duration-150 hover:text-[var(--mk-fg)]";

/**
 * Folio's floating footer: one card (24px radius, hairline, a small shadow)
 * sitting inside the page margin rather than a full-bleed band: the brand
 * block, the three link columns and a copyright row.
 */
export function SiteFooter() {
  return (
    <footer className="mk-container pb-4 md:pb-6">
      <div className="rounded-[var(--mk-radius-shell)] border border-[var(--mk-line)] bg-[var(--mk-surface)] p-6 shadow-sm sm:p-8 md:p-12">
        <div className="grid gap-10 md:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1.3fr]">
          <div>
            <Link href="/" aria-label="Aevrin home" className="inline-flex items-center gap-2.5 rounded-md">
              <Image src="/logo.png" alt="" width={22} height={24} />
              <span className="text-[15px] font-semibold tracking-[0.14em] text-[var(--mk-fg-strong)] uppercase">
                Aevrin
              </span>
            </Link>
            <p className="mt-4 max-w-xs text-sm leading-6 text-[var(--mk-muted)]">
              Scan an MCP server before you install it, and check what your coding agents are allowed to do.
            </p>
            <a
              href="mailto:ujjwal@aevrin.net"
              className="mt-5 inline-flex h-8 items-center gap-2 rounded-full border border-[var(--mk-line)] px-3.5 text-sm font-medium text-[var(--mk-fg)] transition-colors hover:bg-[var(--mk-hover)]"
            >
              <Mail className="size-3.5" aria-hidden="true" />
              ujjwal@aevrin.net
            </a>
          </div>

          <nav aria-label="Product" className="flex flex-col gap-3 text-sm">
            <span className="font-semibold text-[var(--mk-fg-strong)]">Product</span>
            {PRODUCT_LINKS.map((link) => (
              <Link key={link.label} href={link.href} className={linkClass}>
                {link.label}
              </Link>
            ))}
          </nav>

          <nav aria-label="Legal" className="flex flex-col gap-3 text-sm">
            <span className="font-semibold text-[var(--mk-fg-strong)]">Legal</span>
            {LEGAL_LINKS.map((link) => (
              <Link key={link.label} href={link.href} className={linkClass}>
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="flex flex-col items-start gap-3 text-sm">
            <span className="font-semibold text-[var(--mk-fg-strong)]">Support</span>
            <p className="max-w-xs leading-6 text-[var(--mk-muted)]">
              Questions about a scan, account, or integration? Contact the Aevrin team.
            </p>
            <a href="mailto:ujjwal@aevrin.net?subject=Aevrin%20support" className="mk-btn mk-btn-sm mk-btn-outline">
              <Mail className="size-3.5" aria-hidden="true" />
              Contact support
            </a>
          </div>
        </div>

        <p className="mt-12 border-t border-[var(--mk-line)] pt-6 text-sm text-[var(--mk-muted)]">
          &copy; {new Date().getFullYear()} Aevrin. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
