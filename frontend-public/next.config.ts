import type { NextConfig } from "next";
import path from "node:path";

// A fully static site: every response header lives in `public/_headers`
// instead of here (see `frontend-docs/next.config.ts` for the full reasoning
// -- `headers()` in next.config doesn't run under `output: "export"`, and
// this app has no server left to run it anyway).
const nextConfig: NextConfig = {
  output: "export",
  turbopack: {
    root: path.join(__dirname),
  },
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
