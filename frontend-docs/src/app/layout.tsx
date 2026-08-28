import type { Metadata } from "next";
import type { CSSProperties, ReactNode } from "react";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import "./docs.css";
import "fumadocs-ui/style.css";
import { RootProvider } from "fumadocs-ui/provider/next";
import { DocsLayout } from "fumadocs-ui/layouts/docs";
import { baseOptions } from "./layout.config";
import { source } from "@/lib/docs-source";
import DocsSearchDialog from "@/components/search";

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
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://docs.mcp.aevrin.net"),
  title: {
    template: "%s | Aevrin Docs",
    default: "Aevrin Docs",
  },
  icons: {
    icon: "/favicon.ico",
    apple: "/logo.png",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`dark ${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background text-foreground">
        <div className="docs-shell">
          <RootProvider theme={{ enabled: false }} search={{ SearchDialog: DocsSearchDialog }}>
            <DocsLayout
              tree={source.pageTree}
              {...baseOptions}
              containerProps={{ style: { "--fd-layout-width": "100%" } as CSSProperties }}
            >
              {children}
            </DocsLayout>
          </RootProvider>
        </div>
      </body>
    </html>
  );
}
