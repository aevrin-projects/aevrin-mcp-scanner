import type { NextConfig } from "next";
import path from "node:path";
import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

// A public documentation site: no API origin, no payment provider, no
// dashboard session to protect. The policy is narrower than the main app's
// on purpose -- there is nothing here that needs script-src beyond 'self'.
const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // The repo root has its own package-lock.json (for the shadcn CLI
  // devDependency used by the main frontend/ app), and this project sits
  // alongside frontend/ under the same root -- pin the workspace root
  // explicitly so Turbopack doesn't have to guess between the two.
  turbopack: {
    root: path.join(__dirname),
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default withMDX(nextConfig);
