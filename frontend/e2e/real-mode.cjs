const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const APP_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:5173";

async function waitForText(page, selector, pattern, timeout = 120_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const text = await page.locator(selector).textContent().catch(() => "");
    if (pattern.test(text ?? "")) return text;
    await page.waitForTimeout(500);
  }
  throw new Error(`Timed out waiting for ${selector} to match ${pattern}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const workflowPayloads = [];
  const supplyChainPayloads = [];
  page.on("request", (request) => {
    const url = request.url();
    const postData = request.postData();
    if (!postData) return;
    if (url.includes("/workflows/finrisk/run")) {
      workflowPayloads.push(JSON.parse(postData));
    }
    if (url.includes("/supply-chain/explore")) {
      supplyChainPayloads.push(JSON.parse(postData));
    }
  });

  await page.goto(APP_URL);

  // Risk Intelligence: run AAPL through the real path.
  await page.getByTestId("ticker-input").fill("AAPL");
  const demoMode = page.getByTestId("demo-mode");
  if (await demoMode.isChecked()) await demoMode.uncheck();
  const cachedMode = page.locator("#cached-mode");
  if (await cachedMode.isChecked()) await cachedMode.uncheck();
  await page.getByTestId("run-button").click();
  await page.waitForFunction(() => window.__workflowPayloadsReady !== false, null, {
    timeout: 1,
  }).catch(() => {});
  await page.waitForTimeout(500);
  assert.equal(workflowPayloads.length, 1, "Risk workflow request was not sent");
  assert.equal(workflowPayloads[0].demo_mode, false, "Risk demo_mode must be false");
  assert.equal(workflowPayloads[0].cached_mode, false, "Risk cached_mode must be false");
  assert.equal(workflowPayloads[0].ticker, "AAPL");
  assert.equal(workflowPayloads[0].llm_config.provider, "sglang");
  assert.equal(workflowPayloads[0].llm_config.base_url, "http://localhost:30000/v1");

  await page.getByTestId("risk-report").waitFor({ timeout: 120_000 });
  await page.getByTestId("evaluation-tab").waitFor({ timeout: 10_000 });
  await page.getByTestId("agent-timeline").waitFor({ timeout: 10_000 });
  await waitForText(page, "[data-testid='risk-report']", /Risk Report/);
  const riskReportText = await page.getByTestId("risk-report").textContent();
  assert.match(riskReportText ?? "", /Disclaimer|Top Risks/);

  // Product Supply Chain: run NVIDIA/GPU through the real path.
  await page.getByTestId("tab-supply-chain").click();
  await page.getByTestId("sc-company-input").fill("NVIDIA");
  await page.getByTestId("sc-product-input").fill("GPU");
  const scDemoMode = page.getByTestId("sc-demo-mode");
  if (await scDemoMode.isChecked()) await scDemoMode.uncheck();
  await page.getByTestId("sc-run-button").click();
  await page.waitForTimeout(500);
  assert.equal(supplyChainPayloads.length, 1, "Supply-chain request was not sent");
  assert.equal(supplyChainPayloads[0].demo_mode, false, "Supply-chain demo_mode must be false");
  assert.equal(supplyChainPayloads[0].cached_mode, false, "Supply-chain cached_mode must be false");
  assert.equal(supplyChainPayloads[0].company_name, "NVIDIA");
  assert.equal(supplyChainPayloads[0].product_name, "GPU");
  assert.equal(supplyChainPayloads[0].llm_config.provider, "sglang");

  await page.getByTestId("sc-sankey").waitFor({ timeout: 120_000 });
  const nodeCountText = await page.getByTestId("sc-sankey-node-count").textContent();
  const nodeCount = Number((nodeCountText ?? "").match(/\d+/)?.[0] ?? 0);
  assert.ok(nodeCount > 2, `Expected real supply-chain graph, got ${nodeCountText}`);
  const warnings = await page.locator("[data-testid='sc-sankey-warnings']").textContent().catch(() => "");
  assert.ok(!/no demo fixture/i.test(warnings ?? ""), "Should not show demo fixture warning in real mode");

  await browser.close();
  console.log("Playwright real-mode frontend checks passed");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
