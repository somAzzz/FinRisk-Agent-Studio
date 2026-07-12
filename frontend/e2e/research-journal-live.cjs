const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const APP_URL = process.env.FRONTEND_URL;
const CONFIG_PATH = process.env.RESEARCH_JOURNAL_LIVE_CONFIG;
const REPORT_PATH = process.env.RESEARCH_JOURNAL_LIVE_REPORT;
const SCREENSHOT_DIR = process.env.RESEARCH_JOURNAL_SCREENSHOT_DIR;
const HEADED = process.env.HEADED === "1";

if (!APP_URL || !CONFIG_PATH || !REPORT_PATH || !SCREENSHOT_DIR) {
  throw new Error("live acceptance environment is incomplete");
}

const config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
const timeout = Number(config.timeouts.ui_action_ms);
const workflowTimeout = Number(config.timeouts.workflow_ms);
const report = { scenario_id: config.scenario_id, steps: [], screenshots: [] };

function record(name, details = {}) {
  report.steps.push({ name, status: "pass", ...details });
}

function futureDate(days) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + Number(days));
  return date.toISOString().slice(0, 10);
}

async function fill(page, label, value) {
  await page.getByLabel(label, { exact: true }).fill(String(value));
}

async function clickAndWaitForResponse(page, buttonName, urlPart, method = "POST", responseTimeout = timeout) {
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes(urlPart) && response.request().method() === method,
    { timeout: responseTimeout },
  );
  await page.getByRole("button", { name: buttonName, exact: true }).click();
  const response = await responsePromise;
  assert.ok(response.ok(), `${buttonName}: ${response.status()} ${response.url()}\n${await response.text()}`);
  return response;
}

async function screenshot(page, name) {
  const target = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: target, fullPage: true });
  report.screenshots.push(target);
}

async function openJournal(page, task = "cycle") {
  await page.goto(`${APP_URL}?view=journal&task=${task}`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("research-journal").waitFor({ timeout });
}

async function createThesisAndWatchlist(page) {
  const primary = config.primary;
  await fill(page, "Ticker", primary.ticker);
  await fill(page, "Thesis", primary.thesis);
  await fill(page, "Time horizon", primary.time_horizon);
  await fill(page, "What would disprove it?", primary.disconfirming_conditions);
  await fill(page, "Key drivers", primary.key_drivers);
  await fill(page, "Metrics to monitor", primary.monitoring_metrics);
  await clickAndWaitForResponse(page, "Save active thesis", "/research/theses");
  await page.locator(".thesis-card", { hasText: primary.thesis }).waitFor({ timeout });
  await fill(page, `Next review date for ${primary.ticker}`, futureDate(primary.next_review_days_from_now));
  await clickAndWaitForResponse(page, "Add to watchlist", "/research/watchlist", "PUT");
  await page.locator(".watchlist-ledger article", { hasText: primary.ticker }).waitFor({ timeout });
  record("thesis_and_watchlist", { ticker: primary.ticker });
}

async function setCyclePeriod(page, ticker, year, quarter) {
  await fill(page, "Research cycle ticker", ticker);
  await fill(page, "Research cycle year", year);
  await page.getByLabel("Research cycle quarter", { exact: true }).selectOption(String(quarter));
}

async function createBaseline(page) {
  const primary = config.primary;
  await setCyclePeriod(page, primary.ticker, primary.baseline_year, primary.quarter);
  await clickAndWaitForResponse(page, "Create snapshot", "/research/run", "POST", workflowTimeout);
  await page.locator(".cycle-record").filter({ hasText: `${primary.baseline_year}Q${primary.quarter}` }).waitFor({ timeout });
  record("baseline_snapshot", { period: `${primary.baseline_year}Q${primary.quarter}` });
}

async function runLinkedFinRisk(page) {
  const primary = config.primary;
  await setCyclePeriod(page, primary.ticker, primary.current_year, primary.quarter);
  await fill(page, "FinRisk analysis goal", primary.analysis_goal);
  await page.getByText("Research LLM", { exact: true }).click();
  await page.getByTestId("llm-provider-select").selectOption(config.llm.provider);
  await page.getByTestId("llm-base-url-input").fill(config.llm.base_url);
  await page.getByTestId("llm-model-input").fill(config.llm.model);

  let workflowPayload;
  page.on("request", (request) => {
    if (request.url().includes("/workflows/finrisk/run") && request.method() === "POST") {
      workflowPayload = request.postDataJSON();
    }
  });
  await page.getByRole("button", { name: "Run FinRisk + snapshot", exact: true }).click();
  const terminal = page.locator(".cycle-run-state").filter({ hasText: /FinRisk: (completed|needs_review)/ });
  await terminal.waitFor({ timeout: workflowTimeout });
  const text = await terminal.innerText();
  const workflowRunId = text.split(/\s+/).find((item) => item.startsWith("run-"));
  assert.ok(workflowRunId, `workflow run id missing from ${text}`);
  await page.locator(".cycle-record").filter({ hasText: `${primary.current_year}Q${primary.quarter}` }).waitFor({ timeout });
  assert.deepEqual(workflowPayload.llm_config, config.llm);
  assert.equal(workflowPayload.demo_mode, false);
  assert.equal(workflowPayload.cached_mode, false);
  report.workflow_run_id = workflowRunId;
  report.workflow_payload = workflowPayload;
  record("linked_local_llm_workflow", { run_id: workflowRunId });

  const materialChanges = page.getByRole("heading", { name: "Material changes", exact: true }).locator("..");
  const firstChange = materialChanges.locator(".cycle-change").first();
  const noChanges = materialChanges.getByText("No evidence-linked changes between these snapshots.");
  await Promise.race([firstChange.waitFor({ timeout }), noChanges.waitFor({ timeout })]);
  if (await firstChange.isVisible()) {
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes("/research/changes/") && response.url().endsWith("/review"),
      { timeout },
    );
    await firstChange.getByRole("button", { name: "Confirm", exact: true }).click();
    assert.ok((await responsePromise).ok(), "change confirmation failed");
    record("change_review", { outcome: "confirmed" });
  } else {
    record("change_review", { outcome: "no_changes" });
  }
}

async function exerciseExpectation(page) {
  const expectation = config.expectation;
  await page.getByText("Expectations and CSV import", { exact: true }).click();
  await fill(page, "Expectation metric", expectation.metric);
  await fill(page, "Expectation fiscal period", expectation.fiscal_period);
  await fill(page, "Expectation value", expectation.value);
  await fill(page, "Expectation unit", expectation.unit);
  await fill(page, "Expectation source", expectation.source);
  await fill(page, "Expectation observed date", expectation.observed_at);
  await fill(page, "Expectation as-of date", expectation.as_of);
  await clickAndWaitForResponse(page, "Save expectation", "/research/expectations");
  await page.locator(".expectation-record", { hasText: expectation.fiscal_period }).waitFor({ timeout });
  await clickAndWaitForResponse(page, "Compare actual", "/compare", "GET");
  await page.locator(".expectation-record p", { hasText: "actual" }).waitFor({ timeout });
  record("point_in_time_expectation", { fiscal_period: expectation.fiscal_period });
}

async function createPeerSnapshot(page) {
  const peer = config.peer;
  await setCyclePeriod(page, peer.ticker, peer.year, peer.quarter);
  await clickAndWaitForResponse(page, "Create snapshot", "/research/run", "POST", workflowTimeout);
  await page.locator(".cycle-record").filter({ hasText: `${peer.year}Q${peer.quarter}` }).waitFor({ timeout });
  record("peer_snapshot", { ticker: peer.ticker });
}

async function exerciseValuation(page) {
  const primary = config.primary;
  const valuation = config.valuation;
  await page.getByRole("button", { name: "Valuation", exact: true }).click();
  await setCyclePeriod(page, primary.ticker, primary.current_year, primary.quarter);
  await clickAndWaitForResponse(page, "Load history", `/research/snapshots?ticker=${primary.ticker}`, "GET");
  await page.getByText("Scenario valuation", { exact: true }).click();
  await fill(page, "Current share price", valuation.current_share_price);
  for (const name of ["bear", "base", "bull"]) {
    await fill(page, `${name} annual growth`, valuation[name].growth);
    await fill(page, `${name} terminal margin`, valuation[name].margin);
    await fill(page, `${name} multiple`, valuation[name].multiple);
  }
  await clickAndWaitForResponse(page, "Calculate user scenarios", "/research/valuation/scenarios");
  await page.locator(".valuation-results").waitFor({ timeout });
  await clickAndWaitForResponse(page, "Build sensitivity matrix", "/research/valuation/sensitivity");
  await page.locator(".sensitivity-results").waitFor({ timeout });

  await page.getByLabel("Multiple valuation method").selectOption(valuation.multiple_method);
  await fill(page, "Multiple valuation period", valuation.multiple_period);
  await fill(page, "Valuation earnings", valuation.earnings);
  await clickAndWaitForResponse(page, "Calculate multiple", "/research/valuation/multiple");
  await fill(page, "Forecast free cash flows", valuation.forecast_free_cash_flows.join(","));
  await fill(page, "DCF WACC", valuation.wacc);
  await fill(page, "DCF terminal growth", valuation.terminal_growth);
  await clickAndWaitForResponse(page, "Calculate DCF", "/research/valuation/dcf");
  await page.getByText("Implied value per share", { exact: true }).waitFor({ timeout });
  await page.getByText(/Assumption history/).click();
  assert.ok(await page.locator(".valuation-history article").count() >= 4, "valuation history has fewer than four methods");
  record("valuation_lab", { methods: ["scenario", "sensitivity", "multiple", "dcf"] });
}

async function exercisePeers(page) {
  const peer = config.peer;
  await page.getByRole("button", { name: "Peer analysis", exact: true }).click();
  await page.getByText("Create an analyst-confirmed peer group", { exact: true }).click();
  await fill(page, "Peer group name", peer.group_name);
  await fill(page, "Peer group base ticker", config.primary.ticker);
  await fill(page, "Peer group members", `${config.primary.ticker}, ${peer.ticker}`);
  await page.getByLabel("Peer group industry").selectOption(peer.industry_template);
  await clickAndWaitForResponse(page, "Save group", "/research/peer-groups");
  await page.getByRole("status").filter({ hasText: "Peer group saved" }).waitFor({ timeout });
  await clickAndWaitForResponse(page, "Compare peers", "/analysis");
  const rows = await page.locator(".peer-analysis-results tbody tr").count();
  assert.ok(rows >= 2, `peer analysis returned only ${rows} rows`);
  record("peer_analysis", { rows });
}

async function exerciseReview(page) {
  const primary = config.primary;
  await page.getByRole("button", { name: "Reviews", exact: true }).click();
  await setCyclePeriod(page, primary.ticker, primary.current_year, primary.quarter);
  await clickAndWaitForResponse(page, "Load history", `/research/snapshots?ticker=${primary.ticker}`, "GET");
  await clickAndWaitForResponse(page, "Generate draft", "/research/post-earnings/drafts");
  const draft = page.locator(".cycle-reviews article", { hasText: `${primary.ticker} · suggested` }).first();
  await draft.waitFor({ timeout });
  await draft.getByLabel(`Review notes for ${primary.ticker} draft`).fill("Live acceptance: evidence and assumptions reviewed by the analyst.");
  const responsePromise = page.waitForResponse((response) => response.url().includes("/confirm") && response.request().method() === "POST", { timeout });
  await draft.getByRole("button", { name: "Supported", exact: true }).click();
  assert.ok((await responsePromise).ok(), "post-earnings confirmation failed");
  await draft.getByText(/confirmed/).waitFor({ timeout });
  record("post_earnings_review", { outcome: "supported" });
}

async function auditResponsive(page) {
  await screenshot(page, "research-journal-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert.equal(layout.scrollWidth, layout.clientWidth, "mobile page has horizontal overflow");
  await screenshot(page, "research-journal-mobile");
  record("responsive_layout", layout);
}

async function main() {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: !HEADED });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleErrors = [];
  const httpErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("response", (response) => {
    if (response.status() >= 400 && response.url().startsWith(APP_URL)) httpErrors.push(`${response.status()} ${response.url()}`);
  });
  try {
    await openJournal(page);
    await createThesisAndWatchlist(page);
    await createBaseline(page);
    await runLinkedFinRisk(page);
    await exerciseExpectation(page);
    await createPeerSnapshot(page);
    await exerciseValuation(page);
    await exercisePeers(page);
    await exerciseReview(page);
    await auditResponsive(page);
    assert.deepEqual(consoleErrors, [], `console errors:\n${consoleErrors.join("\n")}`);
    assert.deepEqual(httpErrors, [], `HTTP errors:\n${httpErrors.join("\n")}`);
    report.console_errors = consoleErrors;
    report.http_errors = httpErrors;
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  } catch (error) {
    await screenshot(page, "failure").catch(() => {});
    report.failure = error.stack || String(error);
    report.console_errors = consoleErrors;
    report.http_errors = httpErrors;
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
    throw error;
  } finally {
    await browser.close();
  }
  console.log(`Research Journal live browser scenario passed: ${REPORT_PATH}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
