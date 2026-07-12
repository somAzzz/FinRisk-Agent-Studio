const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const APP_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:5173";
const OUTPUT_DIR = process.env.WORKBENCH_SCREENSHOT_DIR ?? path.resolve("../artifacts/frontend-remediation");

async function auditViewport(browser, name, width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
  const consoleErrors = [];
  const httpErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) httpErrors.push(`${response.status()} ${response.url()}`);
  });

  await page.goto(APP_URL, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => document.activeElement?.blur());
  await page.keyboard.press("Tab");
  assert.equal(await page.locator(".skip-link").evaluate((element) => document.activeElement === element), true, `${name}: skip link is not first`);
  await page.evaluate(() => document.activeElement?.blur());

  for (let pass = 0; pass < 3; pass += 1) {
    for (const id of ["tab-journal", "tab-agent-runs", "tab-supply-chain", "tab-finrisk"]) {
      await page.getByTestId(id).click();
      await page.waitForTimeout(80);
    }
  }

  await page.getByTestId("tab-journal").click();
  const valuationTask = page.getByRole("button", { name: "Valuation", exact: true });
  await valuationTask.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  const focusOutline = await valuationTask.evaluate((element) => getComputedStyle(element).outlineStyle);
  assert.notEqual(focusOutline, "none", `${name}: task focus is not visible`);
  await page.keyboard.press("Enter");
  await page.getByLabel("Research cycle ticker").fill("AAPL");
  await page.getByRole("button", { name: "Load history" }).click();
  await page.getByText("Scenario valuation").waitFor({ timeout: 30_000 });
  assert.match(page.url(), /[?&]view=journal/);
  assert.match(page.url(), /[?&]task=valuation/);

  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    docks: [...document.querySelectorAll(".process-monitor,.run-history")].map((element) => ({
      position: getComputedStyle(element).position,
      collapsed: element.getAttribute("data-collapsed"),
    })),
  }));
  assert.equal(layout.scrollWidth, layout.clientWidth, `${name}: page-level horizontal overflow`);
  if (width <= 920) {
    assert.ok(layout.docks.every((dock) => dock.position === "relative"), `${name}: dock still overlays content`);
  }
  assert.ok(layout.docks.every((dock) => dock.collapsed === "true"), `${name}: docks must start collapsed`);
  const historyToggle = page.getByRole("button", { name: "Show run history" });
  await historyToggle.focus();
  await page.keyboard.press("Enter");
  const hideHistory = page.getByRole("button", { name: "Hide run history" });
  assert.equal(await hideHistory.getAttribute("aria-expanded"), "true", `${name}: history dock is not keyboard operable`);
  await page.keyboard.press("Enter");

  await page.emulateMedia({ reducedMotion: "reduce" });
  const transitionDuration = await page.locator(".research-task-nav button").first().evaluate((element) => getComputedStyle(element).transitionDuration);
  assert.ok(transitionDuration === "0s" || transitionDuration === "", `${name}: reduced motion is not honored`);

  await page.locator(".skip-link").evaluate((element) => { element.style.visibility = "hidden"; });
  await page.screenshot({ path: path.join(OUTPUT_DIR, `${name}.png`), fullPage: true });
  assert.deepEqual(consoleErrors, [], `${name}: console errors\n${consoleErrors.join("\n")}`);
  assert.deepEqual(httpErrors, [], `${name}: HTTP errors\n${httpErrors.join("\n")}`);
  await page.close();
}

async function exerciseValuation(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(`${APP_URL}?view=journal&task=valuation`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Research cycle ticker").fill("AAPL");
  await page.getByRole("button", { name: "Load history" }).click();
  await page.getByText("Scenario valuation").waitFor({ timeout: 30_000 });
  await page.getByText("Scenario valuation").click();

  await page.getByLabel("Current share price").fill("200");
  await page.getByLabel("Valuation earnings").fill("100000000000");
  await page.getByRole("button", { name: "Calculate multiple" }).click();
  await page.locator(".valuation-result-card").first().waitFor({ timeout: 30_000 });

  await page.getByLabel("Forecast free cash flows").fill("100000000000,110000000000,120000000000");
  await page.getByLabel("DCF WACC").fill("0.10");
  await page.getByLabel("DCF terminal growth").fill("0.03");
  await page.getByRole("button", { name: "Calculate DCF" }).click();
  await page.getByText("Implied value per share").waitFor({ timeout: 30_000 });

  await page.getByText(/Assumption history/).click();
  assert.ok(await page.locator(".valuation-history article").count() >= 2, "valuation assumption history did not refresh");
  await page.screenshot({ path: path.join(OUTPUT_DIR, "valuation-live.png"), fullPage: true });
  await page.close();
}

async function exercisePeerLifecycle(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(`${APP_URL}?view=journal&task=peers`, { waitUntil: "domcontentloaded" });
  await page.getByText("Create an analyst-confirmed peer group").click();
  const uniqueName = `Browser smoke ${Date.now()}`;
  await page.getByLabel("Peer group name").fill(uniqueName);
  await page.getByLabel("Peer group base ticker").fill("AAPL");
  await page.getByLabel("Peer group members").fill("AAPL, MSFT");
  await page.getByRole("button", { name: "Save group" }).click();
  await page.getByRole("status").filter({ hasText: "Peer group saved" }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: "Delete peer group" }).click();
  await page.getByRole("button", { name: "Confirm delete peer group" }).click();
  await page.getByRole("status").filter({ hasText: "Peer group deleted" }).waitFor({ timeout: 30_000 });
  await page.close();
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    await auditViewport(browser, "desktop-1440", 1440, 1000);
    await auditViewport(browser, "tablet-1024", 1024, 900);
    await auditViewport(browser, "mobile-390", 390, 844);
    await exerciseValuation(browser);
    await exercisePeerLifecycle(browser);
  } finally {
    await browser.close();
  }
  console.log("Workbench Chromium smoke passed");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
