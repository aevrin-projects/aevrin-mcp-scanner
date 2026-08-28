import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
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

const instrumentSerif = Instrument_Serif({
  variable: "--font-display",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://mcp.aevrin.net"),
  title: "Aevrin: MCP Security Scanner",
  description: "Scan MCP servers for vulnerabilities using established open-source security tools.",
  icons: {
    icon: "/favicon.ico",
    apple: "/logo.png",
  },
  openGraph: {
    title: "Aevrin: MCP Security Scanner",
    description: "Scan MCP servers for vulnerabilities using established open-source security tools.",
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
      className={`${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background text-foreground">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
          <PublicNavbar signedIn={false} />
          <main className="flex-1">{children}</main>
          <PageTracker />
        </ThemeProvider>
      </body>
    </html>
  );
}
