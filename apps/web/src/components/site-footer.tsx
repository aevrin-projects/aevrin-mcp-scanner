import Image from "next/image";
import Link from "next/link";
import { Mail } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";

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
            <div className="mt-5 flex items-center gap-2">
              {SOCIAL_LINKS.map((social) => (
                <a
                  key={social.label}
                  href={social.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={social.label}
                  className="flex size-9 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
                >
                  <social.icon />
                </a>
              ))}
            </div>
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
