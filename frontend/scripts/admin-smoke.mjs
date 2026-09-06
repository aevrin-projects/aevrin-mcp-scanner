/**
 * Browser verification for /admin: accessibility, responsiveness, real render.
 *
 * `public-smoke.mjs` covers only public routes, so the admin panel was never
 * checked in a browser at all - it sits behind an allowlist and a TOTP gate,
 * which is exactly why nothing automated reached it.
 *
 * Two layers of access, and only one of them can be stubbed:
 *
 *   The **session** cannot. `middleware.ts` calls `supabase.auth.getClaims()`,
 *   which verifies a real signed JWT, and every /admin request without one is
 *   redirected to /login. So this script signs in for real, with credentials
 *   supplied in the environment. The first version of this file stubbed only
 *   the API and reported a clean pass across every route and viewport - it had
 *   audited the login page fifteen times, because the login page also has one
 *   h1 and no accessibility violations. That is why the sign-in below is
 *   asserted rather than assumed.
 *
 *   The **admin API** is stubbed at the network layer, so pages render with
 *   realistic data instead of skeletons. That weakens nothing: `AdminGate` is
 *   documented as defence in depth, and every admin endpoint re-derives admin
 *   status, TOTP enrolment and freshness server-side. What this verifies is
 *   the interface - markup, contrast, focus order, overflow - not
 *   authorisation, which belongs in the API's own tests.
 *
 * Run it with an account that is on the admin allowlist:
 *
 *   AEVRIN_SMOKE_EMAIL=... AEVRIN_SMOKE_PASSWORD=... npm run test:admin
 *
 * Without those it exits 0 having checked nothing, and says so loudly rather
 * than printing a pass - a skip that looks like success is the failure mode
 * this whole file exists to correct.
 *
 * Fixtures are shaped from `entities/admin/model/types.ts`. If a page starts
 * reading a field that is not here it renders empty, which the assertions
 * below will not catch - so add the field when you add the read.
 */
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const baseUrl = process.env.AEVRIN_SMOKE_URL ?? "http://127.0.0.1:3100";
const email = process.env.AEVRIN_SMOKE_EMAIL;
const password = process.env.AEVRIN_SMOKE_PASSWORD;
const failures = [];

if (!email || !password) {
  process.stderr.write(
    [
      "",
      "SKIPPED: /admin was not verified.",
      "This needs a real signed-in session - middleware verifies a Supabase JWT, so",
      "an unauthenticated run only ever measures the login page.",
      "Set AEVRIN_SMOKE_EMAIL and AEVRIN_SMOKE_PASSWORD for an allowlisted admin",
      "account and run again.",
      "",
    ].join("\n"),
  );
  process.exit(0);
}

const USER_ID = "11111111-2222-3333-4444-555555555555";
const now = new Date().toISOString();

const users = {
  rows: [
    {
      user_id: USER_ID,
      email: "ada@example.com",
      tier: "pro",
      effective_tier: "pro",
      status: "active",
      flagged: false,
      paid_until: now,
      created_at: now,
      last_scan_at: now,
      scans_this_period: 12,
    },
    {
      user_id: "66666666-7777-8888-9999-000000000000",
      email: "grace@example.com",
      tier: "team",
      effective_tier: "free",
      status: "blocked",
      flagged: true,
      paid_until: null,
      created_at: now,
      last_scan_at: null,
      scans_this_period: 0,
    },
  ],
  total: 2,
  page: 1,
  page_size: 30,
};

const userDetail = {
  user_id: USER_ID,
  email: "ada@example.com",
  tier: "pro",
  effective_tier: "pro",
  status: "active",
  status_reason: null,
  flagged: false,
  paid_until: now,
  created_at: now,
  has_password: true,
  auth_providers: ["password"],
  usage: [
    { bucket: "cli", used: 4, limit: 100, resets_at: now },
    { bucket: "dashboard", used: 9, limit: null, resets_at: now },
  ],
  overrides: [],
  recent_scans: [{ target: "github.com/acme/server", risk_score: 27 }],
  api_key_count: 2,
  github_connected: true,
  seats: 5,
};

const analytics = {
  accounts_total: 128,
  signups_in_window: 9,
  scans_in_window: 340,
  scans_total: 4210,
  visitors_in_window: 900,
  pageviews_in_window: 2400,
  views_by_day: [{ day: "2026-09-01", views: 120, visitors: 40 }],
  scans_by_day: [{ day: "2026-09-01", count: 30 }],
  signups_by_day: [{ day: "2026-09-01", count: 2 }],
  top_pages: [{ path: "/dashboard", views: 300 }],
  top_referrers: [{ referrer: "github.com", views: 90 }],
  devices: { desktop: 70, mobile: 30 },
  scans_by_source: { cli: 200, dashboard: 140 },
  plan_distribution: { free: 100, pro: 28 },
  device_authorizations: { cli: 40, hook: 12 },
  scan_outcomes: { completed: 300, incomplete: 40 },
  payments_by_status: { created: 4, captured: 20 },
  cli_authenticated_accounts: 60,
  cli_active_accounts: 25,
  hook_active_accounts: 14,
  hook_cached_targets: 88,
  revenue_paise_in_window: 4500000,
  revenue_paise_total: 91000000,
};

const accountUsage = [
  {
    user_id: USER_ID,
    email: "ada@example.com",
    effective_tier: "pro",
    status: "active",
    bucket: "cli",
    used: 4,
    limit_value: 100,
    is_override: false,
    pct: 4,
  },
];

const audit = [
  {
    id: 1,
    actor_user_id: "admin-1",
    actor_email: "root@example.com",
    action: "user.plan.grant",
    target_user_id: USER_ID,
    target_email: "ada@example.com",
    target_resource: null,
    reason: "support request",
    metadata: {},
    ip_address: "203.0.113.9",
    created_at: now,
  },
];

const loginAttempts = [
  { id: 1, email: "root@example.com", succeeded: true, failure_reason: null, ip_address: "203.0.113.9", created_at: now },
  { id: 2, email: "mallory@example.com", succeeded: false, failure_reason: "bad totp", ip_address: "198.51.100.4", created_at: now },
];

const marketplaceSummary = {
  total: 42, scanned: 30, unscanned: 12, stale_scans: 3, partial_coverage: 2,
  grades: { A: 10, B: 8, C: 7, D: 3, F: 2 },
  statuses: { published: 40, scanning: 2 },
  open_reports: 1, pending_submissions: 2,
};

const marketplaceList = [
  {
    id: "listing-1", slug: "acme-server", title: "Acme MCP Server", status: "published",
    security: { grade: "C", risk_score: 27, state: "scanned", label: "Caution" },
  },
];

/** Route table for the stub. Longest path first so `/admin/marketplace/mcp`
 *  is not swallowed by `/admin/marketplace`. */
const ROUTES = [
  [/\/admin\/session$/, { is_admin: true, totp_enrolled: true, session_fresh: true, email: "root@example.com" }],
  [/\/admin\/marketplace\/summary/, marketplaceSummary],
  [/\/admin\/marketplace\/mcp/, marketplaceList],
  [/\/admin\/marketplace\/submissions/, []],
  [/\/admin\/marketplace\/reports/, []],
  [/\/admin\/analytics/, analytics],
  [/\/admin\/account-usage/, accountUsage],
  [/\/admin\/audit/, audit],
  [/\/admin\/login-attempts/, loginAttempts],
  [/\/admin\/users\/[^/?]+$/, userDetail],
  [/\/admin\/users/, users],
];

const viewports = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 1024, height: 900 },
  { name: "desktop", width: 1440, height: 1000 },
];

const routes = [
  "/admin",
  "/admin/analytics",
  "/admin/audit",
  "/admin/marketplace",
  `/admin/users/${USER_ID}`,
];

const browser = await chromium.launch({ headless: true });

/** Sign in once and keep the storage state, so each viewport gets a fresh
 *  context without fifteen round trips through the login form. */
async function signedInState() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/login`, { waitUntil: "networkidle" });
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).first().fill(password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 30_000 });
  const state = await context.storageState();
  await context.close();
  return state;
}

let storageState;
try {
  storageState = await signedInState();
} catch (error) {
  process.stderr.write(`
FAILURES
could not sign in as ${email}: ${error.message}
`);
  await browser.close();
  process.exit(1);
}

for (const viewport of viewports) {
  for (const route of routes) {
    const context = await browser.newContext({ viewport, storageState });
    const page = await context.newPage();
    const consoleErrors = [];

    page.on("console", (m) => {
      // The dev server's HMR socket cannot upgrade through Playwright's proxy.
      // That is a harness artifact, not a page defect.
      const hmrNoise = m.text().includes("webpack-hmr");
      if (m.type() === "error" && !hmrNoise) consoleErrors.push(m.text());
    });

    // Only API calls, never the page navigation itself. `/admin/analytics` is
    // both a route in this app and a path on the API, so matching on the URL
    // alone served a 500 in place of the document and every page came back
    // blank - which read as "no h1" and "no lang attribute" rather than as the
    // harness fault it was.
    //
    // Anything under /admin that the stub does not know about is failed loudly
    // rather than allowed through to a real backend: a silent pass-through
    // would make this suite depend on whatever happened to be running.
    await context.route("**/*", async (routeCtl) => {
      const request = routeCtl.request();
      const isApiCall = request.resourceType() === "xhr" || request.resourceType() === "fetch";
      const url = request.url();
      if (!isApiCall || !url.includes("/admin/")) return routeCtl.fallback();
      const match = ROUTES.find(([pattern]) => pattern.test(url));
      if (!match) {
        failures.push(`${route}: unstubbed admin request ${url}`);
        return routeCtl.fulfill({ status: 500, body: "{}" });
      }
      return routeCtl.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: JSON.stringify(match[1]),
      });
    });

    await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
    // The gate polls its session before rendering children, and charts mount
    // after their container measures; audit the settled page, not a frame of it.
    await page.waitForTimeout(1200);

    const metrics = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      h1: [...document.querySelectorAll("h1")].map((h) => h.textContent?.trim()),
      hasSidebarNav: Boolean(document.querySelector('[data-slot="sidebar"], nav')),
      bodyText: document.body.innerText.slice(0, 200),
    }));

    if (metrics.overflow > 1) {
      failures.push(`${viewport.name} ${route}: horizontal overflow ${metrics.overflow}px`);
    }
    // The check whose absence produced a clean pass over fifteen login pages.
    // A redirect to /login is not a rendered admin page, however healthy it
    // looks by every other measure here.
    if (!page.url().includes("/admin")) {
      failures.push(`${viewport.name} ${route}: redirected away to ${page.url()} - not signed in`);
    }
    if (metrics.h1.length !== 1) {
      failures.push(`${viewport.name} ${route}: expected one h1, found ${metrics.h1.length} (${metrics.h1.join("|")})`);
    }
    if (/Could not load|Upstream data store error/i.test(metrics.bodyText)) {
      failures.push(`${viewport.name} ${route}: page rendered an error state: ${metrics.bodyText}`);
    }
    if (consoleErrors.length) {
      failures.push(`${viewport.name} ${route}: console ${consoleErrors.join(" | ")}`);
    }

    if (viewport.name === "mobile" || viewport.name === "desktop") {
      const a11y = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      if (a11y.violations.length) {
        failures.push(
          `${viewport.name} ${route}: accessibility ${a11y.violations
            .map((v) => `${v.id} [${v.impact}] (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`)
            .join(" | ")}`,
        );
      }
    }

    process.stdout.write(
      `${viewport.name.padEnd(8)} ${route.padEnd(46)} overflow=${metrics.overflow} h1=${metrics.h1.length}\n`,
    );
    await context.close();
  }
}

// Keyboard reachability of the primary navigation. The sidebar is the only way
// to move around the panel, so a mouse-only sidebar would make the whole area
// unusable without a pointer - and it is the sort of thing axe cannot see,
// because a focusable link that is visually hidden still passes a rule check.
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, storageState });
  const page = await context.newPage();
  await context.route("**/*", async (routeCtl) => {
    const request = routeCtl.request();
    const isApiCall = request.resourceType() === "xhr" || request.resourceType() === "fetch";
    if (!isApiCall || !request.url().includes("/admin/")) return routeCtl.fallback();
    const match = ROUTES.find(([pattern]) => pattern.test(request.url()));
    return match
      ? routeCtl.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(match[1]) })
      : routeCtl.fulfill({ status: 500, body: "{}" });
  });
  await page.goto(`${baseUrl}/admin`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);

  for (const label of ["Analytics", "Accounts", "Marketplace", "Audit log"]) {
    const link = page.getByRole("link", { name: label, exact: true }).first();
    if ((await link.count()) === 0) {
      failures.push(`sidebar is missing a link to ${label}`);
      continue;
    }
    await link.focus();
    const focused = await page.evaluate(() => document.activeElement?.textContent?.trim());
    if (!focused?.includes(label)) {
      failures.push(`sidebar link ${label} did not take keyboard focus (got ${focused})`);
    }
  }

  // The active page must be announced, not only tinted: the active state is a
  // background colour, which is no signal at all to a screen reader.
  const current = await page.locator('[aria-current="page"]').count();
  if (current !== 1) {
    failures.push(`expected exactly one aria-current="page" in the sidebar, found ${current}`);
  }
  await context.close();
}

await browser.close();
if (failures.length) {
  process.stderr.write(`\nFAILURES\n${failures.join("\n")}\n`);
  process.exit(1);
}
process.stdout.write("\nAdmin browser verification passed.\n");
