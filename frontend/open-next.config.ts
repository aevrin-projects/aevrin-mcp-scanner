import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// No incrementalCache, tagCache or queue override: every page in this app is
// either statically prerendered at build time (robots.txt, sitemap.xml,
// llms.txt) or rendered per request against Supabase and the API. There is no
// ISR surface for a cache to serve, so binding a KV namespace here would add a
// moving part that nothing reads.
export default defineCloudflareConfig();
