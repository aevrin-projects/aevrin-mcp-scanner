/**
 * Core Web Vitals against a production build.
 *
 * Measured on the deployed site by default, because a dev build's numbers
 * are meaningless — no minification, no tree-shaking, and a compile step on
 * first hit. Targets: LCP ≤ 2.5s, CLS ≤ 0.1, TBT as the INP proxy (real INP
 * needs field data; TBT is the accepted lab stand-in).
 *
 *   node scripts/perf-audit.mjs
 *   BASE_URL=http://localhost:3000 node scripts/perf-audit.mjs
 */
import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "https://mcp.aevrin.net";
const ROUTES = ["/", "/pricing", "/cli", "/docs", "/login"];

const TARGETS = { lcp: 2500, cls: 0.1, tbt: 200 };

async function measure(browser, route) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  await page.addInitScript(() => {
    window.__vitals = { lcp: 0, cls: 0, longTasks: 0 };
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__vitals.lcp = e.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        // Layout shifts during an interaction don't count against CLS.
        if (!e.hadRecentInput) window.__vitals.cls += e.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
    new PerformanceObserver((list) => {
      // Total Blocking Time: the part of each long task beyond 50ms.
      for (const e of list.getEntries()) window.__vitals.longTasks += Math.max(0, e.duration - 50);
    }).observe({ type: "longtask", buffered: true });
  });

  await page.goto(`${BASE}${route}`, { waitUntil: "load" });
  // Let late-arriving images and client panels settle so LCP/CLS stabilise.
  await page.waitForTimeout(5000);

  const v = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    return { ...window.__vitals, ttfb: nav?.responseStart ?? 0, transfer: nav?.transferSize ?? 0 };
  });
  await ctx.close();
  return v;
}

const browser = await chromium.launch();
const rows = [];
for (const route of ROUTES) rows.push({ route, ...(await measure(browser, route)) });
await browser.close();

const pad = (s, n) => String(s).padEnd(n);
console.log(`${pad("route", 12)} ${pad("LCP", 10)} ${pad("CLS", 8)} ${pad("TBT", 9)} TTFB`);
let failures = 0;
for (const r of rows) {
  const lcpOk = r.lcp <= TARGETS.lcp;
  const clsOk = r.cls <= TARGETS.cls;
  const tbtOk = r.longTasks <= TARGETS.tbt;
  if (!lcpOk || !clsOk || !tbtOk) failures++;
  console.log(
    `${pad(r.route, 12)} ${pad(`${Math.round(r.lcp)}ms${lcpOk ? "" : " ✗"}`, 10)} ` +
      `${pad(`${r.cls.toFixed(3)}${clsOk ? "" : " ✗"}`, 8)} ` +
      `${pad(`${Math.round(r.longTasks)}ms${tbtOk ? "" : " ✗"}`, 9)} ${Math.round(r.ttfb)}ms`,
  );
}
console.log(`\ntargets: LCP ≤ ${TARGETS.lcp}ms, CLS ≤ ${TARGETS.cls}, TBT ≤ ${TARGETS.tbt}ms`);
console.log(failures === 0 ? "ALL PASS" : `${failures} route(s) over target`);
process.exit(failures === 0 ? 0 : 1);
