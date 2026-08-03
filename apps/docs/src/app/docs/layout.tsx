import type { CSSProperties, ReactNode } from "react";
import { DocsLayout } from "fumadocs-ui/layouts/docs";
import { baseOptions } from "../layout.config";
import { source } from "@/lib/source";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <DocsLayout
      tree={source.pageTree}
      {...baseOptions}
      containerProps={{ style: { "--fd-layout-width": "100%" } as CSSProperties }}
    >
      {children}
    </DocsLayout>
  );
}
