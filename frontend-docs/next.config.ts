import type { NextConfig } from "next";
import path from "node:path";
import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

// A fully static site: every response header lives in `public/_headers`
// instead of here. `output: 'export'` -- there is no server at request time
// to run next.config's `headers()`, and Next.js warns (correctly) that it
// would silently do nothing. Cloudflare's static-assets handler reads
// `_headers` from the output root and applies it at the edge, which is a
// closer match anyway: these are the same fixed strings on every request,
// computed once at build time rather than recomputed per request.
const nextConfig: NextConfig = {
  output: "export",
  // The repo root has its own package-lock.json (for the shadcn CLI
  // devDependency used by the main frontend/ app), and this project sits
  // alongside frontend/ under the same root -- pin the workspace root
  // explicitly so Turbopack doesn't have to guess between the two.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default withMDX(nextConfig);
