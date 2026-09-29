import Image from "next/image";
import Link from "next/link";
import { Mail } from "lucide-react";

const SOCIAL_LINKS = [
  { label: "GitHub", href: "https://github.com/AkashaPrasad", icon: GitHubIcon },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/akasha-a-prasad-639547344/", icon: LinkedInIcon },
  { label: "YouTube", href: "https://www.youtube.com/@aevrin.cofounders", icon: YouTubeIcon },
] as const;

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 2C6.48 2 2 6.58 2 12.24c0 4.52 2.87 8.36 6.84 9.71.5.1.68-.22.68-.5 0-.24-.01-1.04-.01-1.89-2.78.62-3.37-1.22-3.37-1.22-.46-1.19-1.11-1.51-1.11-1.51-.91-.64.07-.62.07-.62 1 .07 1.53 1.05 1.53 1.05.89 1.56 2.34 1.11 2.91.85.09-.66.35-1.11.63-1.37-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.31.1-2.72 0 0 .84-.27 2.75 1.05a9.3 9.3 0 0 1 5 0c1.91-1.32 2.75-1.05 2.75-1.05.55 1.41.2 2.46.1 2.72.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.8-4.57 5.06.36.32.68.94.68 1.9 0 1.37-.01 2.47-.01 2.81 0 .27.18.6.69.5A10.03 10.03 0 0 0 22 12.24C22 6.58 17.52 2 12 2Z"
      />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
      <path
        fill="currentColor"
        d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.03-1.85-3.03-1.85 0-2.14 1.45-2.14 2.94v5.66H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29ZM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12ZM7.12 20.45H3.56V9h3.56v11.45Z"
      />
    </svg>
  );
}

function YouTubeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
      <path
        fill="currentColor"
        d="M21.58 7.19a2.51 2.51 0 0 0-1.77-1.78C18.25 5 12 5 12 5s-6.25 0-7.81.41A2.51 2.51 0 0 0 2.42 7.2 26.4 26.4 0 0 0 2 12a26.4 26.4 0 0 0 .42 4.81 2.51 2.51 0 0 0 1.77 1.78C5.75 19 12 19 12 19s6.25 0 7.81-.41a2.51 2.51 0 0 0 1.77-1.78A26.4 26.4 0 0 0 22 12a26.4 26.4 0 0 0-.42-4.81ZM10 15.2V8.8L15.5 12 10 15.2Z"
      />
    </svg>
  );
}

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
 * sitting inside the page margin rather than a full-bleed band. The brand
 * block, the three columns and every link are the ones this footer always
 * carried; only the surface changed, plus the copyright row it lacked.
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
              href="mailto:support@aevrin.net"
              className="mt-5 inline-flex h-8 items-center gap-2 rounded-full border border-[var(--mk-line)] px-3.5 text-sm font-medium text-[var(--mk-fg)] transition-colors hover:bg-[var(--mk-hover)]"
            >
              <Mail className="size-3.5" aria-hidden="true" />
              support@aevrin.net
            </a>
            <div className="mt-5 flex items-center gap-2">
              {SOCIAL_LINKS.map((social) => (
                <a
                  key={social.label}
                  href={social.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={social.label}
                  className="flex size-10 items-center justify-center rounded-lg border border-[var(--mk-line)] text-[var(--mk-muted)] transition-colors hover:bg-[var(--mk-hover)] hover:text-[var(--mk-fg)]"
                >
                  <social.icon />
                </a>
              ))}
            </div>
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
            <a href="mailto:support@aevrin.net" className="mk-btn mk-btn-sm mk-btn-outline">
              <Mail className="size-3.5" aria-hidden="true" />
              Contact support
            </a>
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t border-[var(--mk-line)] pt-6 text-sm text-[var(--mk-muted)] sm:flex-row sm:items-center sm:justify-between">
          <p>&copy; {new Date().getFullYear()} Aevrin. All rights reserved.</p>
          <p>Operated from India. Delivered online.</p>
        </div>
      </div>
    </footer>
  );
}
