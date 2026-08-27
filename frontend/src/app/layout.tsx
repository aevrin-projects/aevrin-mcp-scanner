import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";
import { ThemeProvider } from "@/features/theme";
import { Toaster } from "@/shared/ui/sonner";
import { LayoutChrome } from "@/widgets/app-shell";
import { PageTracker } from "@/features/analytics";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Display face, used only at large sizes for headlines. A high-contrast
// transitional serif against the precise sans and mono is what stops a
// security dashboard reading like a generic admin template.
const instrumentSerif = Instrument_Serif({
  variable: "--font-display",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
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

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Resolved once, in the proxy (see lib/supabase/proxy.ts), reading the
  // header here instead of calling Supabase again avoids a second
  // concurrent refresh-token exchange on every single page load, which was
  // the actual cause of people getting logged out and having to sign in
  // repeatedly.
  const headersList = await headers();
  const email = headersList.get("x-aevrin-user-email") || undefined;

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background text-foreground">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
          <LayoutChrome email={email}>{children}</LayoutChrome>
          <PageTracker />
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
