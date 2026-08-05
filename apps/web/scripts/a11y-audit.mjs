/**
 * WCAG 2.2 AA audit across every route, signed in and signed out.
 *
 * Automated rules catch roughly a third of real accessibility problems, so
 * this is a floor rather than a pass mark — keyboard traversal, focus order,
 * and zoom are checked separately in a11y-manual.mjs. Run with the dev
 * server up:  node scripts/a11y-audit.mjs
 */
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const EMAIL = process.env.QA_EMAIL ?? "qa+redesign@aevrin.net";
const PASSWORD = process.env.QA_PASSWORD ?? "AevrinQA!redesign2026";

const PUBLIC_ROUTES = ["/", "/pricing", "/cli", "/status", "/terms", "/privacy", "/docs", "/login"];
const AUTHED_ROUTES = [
  "/dashboard",
  "/scans/new",
  "/scans/history",
  "/usage",
  "/integrations",
  "/settings/api-keys",
  "/settings/billing",
  "/onboarding",
];

// WCAG 2.2 AA, plus the best-practice pack — best-practice findings are
// reported separately so they can't be mistaken for conformance failures.
const CONFORMANCE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const THEME = process.env.THEME ?? "dark";

async function analyze(page, url, tags) {
  await page.goto(`${BASE}${url}`, { waitUntil: "domcontentloaded" });
  // next-themes persists the choice in localStorage and stamps a class on
  // <html>; set both so the audit really renders the theme it claims to.
  await page.evaluate((theme) => {
    localStorage.setItem("theme", theme);
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, THEME);
  await page.waitForTimeout(2500); // client-rendered panels settle
  return new AxeBuilder({ page }).withTags(tags).analyze();
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const rows = [];
  const details = [];

  for (const route of PUBLIC_ROUTES) {
    const result = await analyze(page, route, CONFORMANCE_TAGS);
    rows.push({ route, violations: result.violations.length });
    for (const v of result.violations) {
      details.push({ route, id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, sample: v.nodes[0]?.html?.slice(0, 160) });
    }
  }

  // Sign in once, then sweep the product surface.
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  await page.locator("input[type=email]").fill(EMAIL);
  await page.locator("input[type=password]").fill(PASSWORD);
  await page.locator("button:has-text('Sign in'):not(:has-text('Google')):not(:has-text('GitHub'))").click();
  await page.waitForTimeout(4000);

  for (const route of AUTHED_ROUTES) {
    const result = await analyze(page, route, CONFORMANCE_TAGS);
    rows.push({ route, violations: result.violations.length });
    for (const v of result.violations) {
      details.push({ route, id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, sample: v.nodes[0]?.html?.slice(0, 160) });
    }
  }

  console.log("\n=== WCAG 2.2 AA violations by route ===");
  for (const r of rows) console.log(`${r.violations === 0 ? "PASS" : "FAIL"}  ${String(r.violations).padStart(2)}  ${r.route}`);

  console.log("\n=== unique violation rules ===");
  const byRule = new Map();
  for (const d of details) {
    const entry = byRule.get(d.id) ?? { impact: d.impact, help: d.help, routes: new Set(), nodes: 0, sample: d.sample };
    entry.routes.add(d.route);
    entry.nodes += d.nodes;
    byRule.set(d.id, entry);
  }
  if (byRule.size === 0) console.log("none");
  for (const [id, e] of byRule) {
    console.log(`\n[${e.impact}] ${id} — ${e.help}`);
    console.log(`  routes: ${[...e.routes].join(", ")}`);
    console.log(`  nodes : ${e.nodes}`);
    console.log(`  sample: ${e.sample}`);
  }

  const total = details.reduce((n, d) => n + d.nodes, 0);
  console.log(`\nTOTAL: ${byRule.size} distinct rules, ${total} nodes across ${rows.length} routes`);

  await browser.close();
  process.exit(byRule.size === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
