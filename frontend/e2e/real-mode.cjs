const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const APP_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:5173";
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
  await page.getByRole("button",{name:"New research",exact:true}).click();
  await page.getByRole("button",{name:"Company question",exact:true}).click();
  await page.getByTestId("ticker-input").fill("AAPL");
  await page.getByTestId("run-button").click();
  await page.waitForFunction(() => window.__workflowPayloadsReady !== false, null, {
    timeout: 1,
  }).catch(() => {});
  await page.waitForTimeout(500);
  assert.equal(workflowPayloads.length, 1, "Risk workflow request was not sent");
  for(const k of ["demo_mode","cached_mode","llm_config"]) assert.ok(!(k in workflowPayloads[0]));
  assert.equal(workflowPayloads[0].ticker, "AAPL");

  await page.getByTestId("research-decision-brief").waitFor({ timeout: 120_000 });
  assert.ok(await page.getByRole("heading",{name:"Decision brief"}).isVisible());
  await page.getByRole("button",{name:"Evidence",exact:true}).click();
  await page.getByRole("heading",{name:"Evidence",exact:true}).first().waitFor();

  // Product Supply Chain: run NVIDIA/GPU through the real path.
  await page.getByTestId("tab-supply-chain").click();
  await page.getByTestId("sc-company-input").fill("NVIDIA");
  await page.getByTestId("sc-product-input").fill("GPU");
  await page.getByTestId("sc-run-button").click();
  await page.waitForTimeout(500);
  assert.equal(supplyChainPayloads.length, 1, "Supply-chain request was not sent");
  assert.deepEqual(Object.keys(supplyChainPayloads[0]).sort(),["company_name","product_name"]);
  assert.equal(supplyChainPayloads[0].company_name, "NVIDIA");
  assert.equal(supplyChainPayloads[0].product_name, "GPU");

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
