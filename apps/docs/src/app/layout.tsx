import "fumadocs-ui/style.css";
import "./globals.css";
import type { ReactNode } from "react";
import { RootProvider } from "fumadocs-ui/provider/next";

export const metadata = {
  title: {
    template: "%s | Aevrin Docs",
    default: "Aevrin Docs — MCP Security Scanner",
  },
  description:
    "Documentation for Aevrin: the CLI, the Claude Code hook, the dashboard, and the API — scan Model Context Protocol servers for security risks before you trust them.",
  metadataBase: new URL("https://mcp.aevrin.net/docs"),
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="flex min-h-svh flex-col">
        <RootProvider
          theme={{ defaultTheme: "dark" }}
          search={{ options: { api: "https://mcp.aevrin.net/docs-search" } }}
        >
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
