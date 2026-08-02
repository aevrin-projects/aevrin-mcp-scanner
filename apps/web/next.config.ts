import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // The repo root has its own package-lock.json (for the shadcn CLI
  // devDependency) in addition to this app's — pin the workspace root
  // explicitly so Turbopack doesn't have to guess between the two.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
