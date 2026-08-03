import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  assetPrefix:
    process.env.DOCS_ASSET_ORIGIN ?? "https://mcp.aevrin.net/docs-assets",
  turbopack: {
    root: import.meta.dirname,
  },
};

export default withMDX(config);
