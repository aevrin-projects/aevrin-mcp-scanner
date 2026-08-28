import type { MetadataRoute } from "next";
import { source } from "@/lib/docs-source";

const SITE_URL = "https://docs.mcp.aevrin.net";

export const revalidate = false;

export default function sitemap(): MetadataRoute.Sitemap {
  return source.getPages().map((page) => ({
    url: `${SITE_URL}${page.url}`,
  }));
}
