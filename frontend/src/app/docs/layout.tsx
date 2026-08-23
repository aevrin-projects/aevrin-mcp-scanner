import type { CSSProperties, ReactNode } from "react";
import "fumadocs-ui/style.css";
import "./docs.css";
import { RootProvider } from "fumadocs-ui/provider/next";
import { DocsLayout } from "fumadocs-ui/layouts/docs";
import { baseOptions } from "./layout.config";
import { source } from "@/shared/lib/docs-source";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="docs-shell">
      <RootProvider theme={{ enabled: false }} search={{ options: { api: "/api/search" } }}>
        <DocsLayout
          tree={source.pageTree}
          {...baseOptions}
          containerProps={{ style: { "--fd-layout-width": "100%" } as CSSProperties }}
        >
          {children}
        </DocsLayout>
      </RootProvider>
    </div>
  );
}
