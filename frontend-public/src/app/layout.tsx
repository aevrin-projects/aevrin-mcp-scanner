import type { Metadata } from "next";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/features/theme";
import { PublicNavbar } from "@/widgets/public-navbar";
import { PageTracker } from "@/features/analytics";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Headlines only (.mk-display, .mk-h2, .mk-h2-xl). A variable font with an
// optical-size axis, so one file covers every weight the headlines use and the
// CSS can ask for its 60pt display cut. next/font downloads it at build time
// and serves it from /_next/static/media, which `font-src 'self'` allows.
const displaySerif = Source_Serif_4({
  variable: "--font-display",
  subsets: ["latin"],
  axes: ["opsz"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://mcp.aevrin.net"),
  title: "Aevrin: MCP Security Scanner",
  description: "Aevrin starts an MCP server in a sandbox, reads every tool it declares, and grades what it could do, from A to F.",
  icons: {
    icon: "/favicon.ico",
    apple: "/logo.png",
  },
  openGraph: {
    title: "Aevrin: MCP Security Scanner",
    description: "Aevrin starts an MCP server in a sandbox, reads every tool it declares, and grades what it could do, from A to F.",
    images: ["/logo.png"],
  },
};

// Every route here is public marketing/content -- there is no signed-in
// state to branch on (that lives entirely in the authenticated app on
// app.mcp.aevrin.net), so this is always the marketing navbar, never the
// app shell. See DECISIONS.md ADR-011 for why this app exists at all.
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${displaySerif.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      {/* `.marketing` on the body puts every route, the fixed navbar and any
          portalled menu on the same tokens (globals.css). */}
      <body className="marketing min-h-full bg-background text-foreground">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
          <PublicNavbar />
          {/* The navbar is fixed, so the page starts below its 68px bar. */}
          <main id="main" className="flex-1 pt-[68px]">{children}</main>
          <PageTracker />
        </ThemeProvider>
      </body>
    </html>
  );
}
