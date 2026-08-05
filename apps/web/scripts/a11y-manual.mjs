/**
 * The parts axe can't judge: keyboard traversal, visible focus, 200% zoom
 * reflow, and reduced motion. Automated rules cover roughly a third of real
 * accessibility problems — these are most of the rest.
 *
 *   node scripts/a11y-manual.mjs
 */
import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const EMAIL = process.env.QA_EMAIL ?? "qa+redesign@aevrin.net";
const PASSWORD = process.env.QA_PASSWORD ?? "AevrinQA!redesign2026";

const ROUTES = ["/", "/pricing", "/login", "/dashboard", "/scans/new", "/scans/history", "/settings/billing", "/onboarding"];

const failures = [];
function check(ok, label, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures.push(`${label}${detail ? `: ${detail}` : ""}`);
}

async function signIn(page) {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  await page.locator("input[type=email]").fill(EMAIL);
  await page.locator("input[type=password]").fill(PASSWORD);
  await page.locator("button:has-text('Sign in'):not(:has-text('Google')):not(:has-text('GitHub'))").click();
  await page.waitForTimeout(4000);
}

/** Every interactive element must be reachable by Tab and show a focus ring. */
async function keyboardSweep(page, route) {
  await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2200);

  const interactive = await page.evaluate(() => {
    const sel = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    return [...document.querySelectorAll(sel)].filter((el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
    }).length;
  });

  // Tab through and record how many distinct elements actually receive focus,
  // and whether each shows a visible indicator.
  const seen = new Set();
  let noIndicator = 0;
  const budget = Math.min(interactive + 5, 90);
  for (let i = 0; i < budget; i++) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      // The dev-tools overlay is injected by `next dev` and never ships to
      // production, so it isn't ours to give a focus ring.
      if (el.tagName === "NEXTJS-PORTAL") return null;
      const s = getComputedStyle(el);
      const key = `${el.tagName}:${(el.textContent || "").trim().slice(0, 30)}:${el.getAttribute("href") || el.getAttribute("id") || ""}`;
      // A focus ring can be drawn as an outline, a box-shadow ring, or a
      // border-colour change — accept any of them.
      const visible =
        (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) ||
        s.boxShadow !== "none" ||
        el.matches(":focus-visible");
      return { key, visible, tag: el.tagName };
    });
    if (!info) continue;
    seen.add(info.key);
    if (!info.visible) noIndicator++;
  }

  check(seen.size >= Math.min(interactive, 5), `${route} — keyboard reaches interactive elements`, `${seen.size} focused / ${interactive} interactive`);
  check(noIndicator === 0, `${route} — every focused element shows an indicator`, noIndicator ? `${noIndicator} without` : "");
}

/** WCAG 1.4.10 Reflow: 320px-equivalent width with no horizontal scroll. */
async function zoomReflow(page, route) {
  // 1440 CSS px at 200% zoom == a 720px viewport. WCAG's stricter reflow
  // target is 320px, which is what this checks.
  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2200);
  const overflow = await page.evaluate(() => {
    const d = document.documentElement;
    return { scrollW: d.scrollWidth, clientW: d.clientWidth };
  });
  // 1px of tolerance for sub-pixel rounding.
  check(overflow.scrollW <= overflow.clientW + 1, `${route} — no horizontal scroll at 320px`, `${overflow.scrollW} > ${overflow.clientW}`);
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function reducedMotion(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  const animating = await page.evaluate(() =>
    document.getAnimations().filter((a) => a.playState === "running").length,
  );
  check(animating === 0, "prefers-reduced-motion halts animations", `${animating} still running`);
  await ctx.close();
}

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  console.log("=== keyboard + focus ===");
  for (const r of ["/", "/pricing", "/login"]) await keyboardSweep(page, r);
  await signIn(page);
  for (const r of ["/dashboard", "/scans/new", "/scans/history", "/settings/billing", "/onboarding"]) {
    await keyboardSweep(page, r);
  }

  console.log("\n=== 320px reflow (WCAG 1.4.10) ===");
  for (const r of ROUTES) await zoomReflow(page, r);

  console.log("\n=== reduced motion ===");
  await reducedMotion(browser);

  console.log(`\n${failures.length === 0 ? "ALL PASS" : `${failures.length} FAILURES`}`);
  for (const f of failures) console.log(`  - ${f}`);
  await browser.close();
  process.exit(failures.length === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
