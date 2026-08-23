import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const baseUrl = process.env.AEVRIN_SMOKE_URL ?? "http://127.0.0.1:3100";
const browser = await chromium.launch({ headless: true });
const failures = [];
const allViewports = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet-small", width: 768, height: 900 },
  { name: "tablet", width: 1024, height: 900 },
  { name: "desktop-small", width: 1280, height: 960 },
  { name: "desktop", width: 1440, height: 1000 },
];
const allRoutes = [
  "/",
  "/pricing",
  "/docs",
  "/docs/cli",
  "/cli",
  "/login",
  "/status",
  "/terms",
  "/privacy",
  "/definitely-not-a-route",
];
const quick = process.env.AEVRIN_SMOKE_QUICK === "1";
const viewports = quick
  ? allViewports.filter(({ name }) => name === "mobile" || name === "desktop")
  : allViewports;
const routes = quick ? ["/", "/pricing", "/docs"] : allRoutes;

for (const viewport of viewports) {
  for (const route of routes) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const consoleErrors = [];
    const failedResponses = [];
    page.on("console", (message) => {
      const expected404 =
        route === "/definitely-not-a-route" && message.text().includes("404");
      if (message.type() === "error" && !expected404) consoleErrors.push(message.text());
    });
    page.on("response", (response) => {
      const expected404 =
        route === "/definitely-not-a-route" && response.url().endsWith(route);
      if (response.status() >= 400 && !expected404) {
        failedResponses.push(`${response.status()} ${response.url()}`);
      }
    });

    const response = await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
    const metrics = await page.evaluate(() => ({
      title: document.title,
      headings: [...document.querySelectorAll("h1")].map((heading) =>
        heading.textContent?.trim(),
      ),
      overflow: document.documentElement.scrollWidth - window.innerWidth,
    }));
    const expectedStatus = route === "/definitely-not-a-route" ? 404 : 200;
    if (response.status() !== expectedStatus) {
      failures.push(
        `${viewport.name} ${route}: status ${response.status()} expected ${expectedStatus}`,
      );
    }
    if (metrics.overflow > 1) {
      failures.push(`${viewport.name} ${route}: horizontal overflow ${metrics.overflow}px`);
    }
    if (metrics.headings.length !== 1) {
      failures.push(
        `${viewport.name} ${route}: expected one h1, found ${metrics.headings.length}`,
      );
    }
    if (!metrics.title.includes("Aevrin")) {
      failures.push(`${viewport.name} ${route}: title missing Aevrin: ${metrics.title}`);
    }
    if (consoleErrors.length) {
      failures.push(`${viewport.name} ${route}: console ${consoleErrors.join(" | ")}`);
    }
    if (failedResponses.length) {
      failures.push(
        `${viewport.name} ${route}: failed responses ${failedResponses.join(" | ")}`,
      );
    }
    if (
      (viewport.name === "mobile" || viewport.name === "desktop") &&
      route !== "/definitely-not-a-route"
    ) {
      // Audit the settled interface rather than a deliberate reveal animation's
      // partially transparent transition frame.
      await page.waitForTimeout(900);
      const accessibility = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      if (accessibility.violations.length) {
        failures.push(
          `${viewport.name} ${route}: accessibility ${accessibility.violations
            .map(
              (violation) =>
                `${violation.id} (${violation.nodes
                  .map((node) => node.target.join(" "))
                  .join(", ")})`,
            )
            .join(" | ")}`,
        );
      }
    }
    process.stdout.write(
      `${viewport.name.padEnd(13)} ${route.padEnd(25)} ${response.status()} overflow=${metrics.overflow}\n`,
    );
    await context.close();
  }
}

const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
const page = await context.newPage();
await page.goto(`${baseUrl}/pricing`, { waitUntil: "networkidle" });
const annualText = await page.locator("section#pricing").innerText();
const toggle = page.getByRole("switch", { name: "Toggle annual billing" });
if (!(await toggle.isVisible())) failures.push("pricing toggle is not visible");
await toggle.press("Space");
const monthlyText = await page.locator("section#pricing").innerText();
if (!annualText.includes("$180 billed today")) {
  failures.push("annual total is not visible");
}
if (!monthlyText.includes("$19 billed today for one month")) {
  failures.push("monthly charge is not visible after toggle");
}
const faq = page.getByRole("button", {
  name: "What happens when I hit my quota mid-month?",
});
await faq.click();
if (!(await page.getByText(/pauses until it resets/).isVisible())) {
  failures.push("pricing FAQ did not open");
}

const homeResponse = await page.goto(`${baseUrl}/`);
for (const header of [
  "content-security-policy",
  "x-content-type-options",
  "x-frame-options",
  "referrer-policy",
]) {
  if (!homeResponse.headers()[header]) failures.push(`missing security header ${header}`);
}

const internalHrefs = await page.locator("a[href]").evaluateAll((links) => [
  ...new Set(
    links
      .map((link) => link.getAttribute("href"))
      .filter((href) => href?.startsWith("/")),
  ),
]);
for (const href of internalHrefs) {
  const path = href.split("#")[0] || "/";
  const response = await page.request.get(`${baseUrl}${path}`, { maxRedirects: 0 });
  if (![200, 307, 308].includes(response.status())) {
    failures.push(`internal link ${href} returned ${response.status()}`);
  }
}

const protectedResponse = await page.goto(`${baseUrl}/usage`, { waitUntil: "networkidle" });
if (!page.url().endsWith("/login")) {
  failures.push(`protected /usage did not redirect to login: ${page.url()}`);
}
process.stdout.write(`protected /usage -> ${page.url()} (${protectedResponse.status()})\n`);

await browser.close();
if (failures.length) {
  process.stderr.write(`\nFAILURES\n${failures.join("\n")}\n`);
  process.exit(1);
}
process.stdout.write("\nBrowser verification passed.\n");
