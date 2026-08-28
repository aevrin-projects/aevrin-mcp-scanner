import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// No incrementalCache, tagCache or queue override: every page here is either
// statically prerendered at build time or reads only from the bundled MDX
// content. There is no ISR surface for a cache to serve.
export default defineCloudflareConfig();
