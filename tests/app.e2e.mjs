// End-to-end checks for index.html in headless Chromium, opened from disk (file://)
// the way a user would open it. Run: npm run test:e2e
// Set CHROMIUM_PATH to use a specific Chromium build.
import { chromium } from "playwright-core";
import { pathToFileURL, fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const root = fileURLToPath(new URL("..", import.meta.url));
const appUrl = pathToFileURL(root + "index.html").href;
const csv = root + "tests/fixtures/orders.csv";
const xlsx = root + "tests/fixtures/workbook.xlsx";

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ acceptDownloads: true });
const problems = [];
const externalRequests = [];
page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
page.on("console", (m) => { if (m.type() === "error") problems.push("console: " + m.text()); });
page.on("request", (r) => { if (!r.url().startsWith("file://") && !r.url().startsWith("data:")) externalRequests.push(r.url()); });

const steps = [];
async function step(name, fn) {
  try { await fn(); steps.push(["PASS", name]); }
  catch (e) { steps.push(["FAIL", name + " — " + e.message.split("\n")[0]]); }
}
const toastText = () => page.locator("#toastHost").innerText().catch(() => "");
const navRows = () => page.locator("#navRows").innerText();
async function go(view) { await page.click(`.nav-btn[data-view="${view}"]`); }
async function action(name) { await page.click(`[data-action="${name}"]`); }

await page.goto(appUrl, { waitUntil: "load" });

await step("overview renders and sidebar uses the new label", async () => {
  await page.waitForSelector("h1.page-title");
  assert.match(await page.locator("h1.page-title").innerText(), /Make data make sense/);
  assert.match(await page.locator('.nav-btn[data-view="funnels"]').innerText(), /Category breakdown/);
});

await step("SQL lab runs on the bundled engine (file://) and returns rows", async () => {
  await go("sql");
  await page.click("#runSqlBtn");
  await page.waitForFunction(() => !/Preparing/.test(document.querySelector("#sqlMessage")?.innerText || "Preparing"), null, { timeout: 60000 });
  const msg = await page.locator("#sqlMessage").innerText();
  assert.match(msg, /Query completed/, msg);
  assert.match(await page.locator("#sqlHost").innerText(), /total_revenue/);
});

await step("importing a CSV loads 12 rows", async () => {
  await page.setInputFiles("#fileInput", csv);
  await page.waitForFunction(() => document.querySelector("#navRows")?.textContent === "12");
  assert.equal(await navRows(), "12");
});

await step("dedupe removes the repeated row and is logged", async () => {
  await go("clean");
  await action("dedupe");
  await page.waitForFunction(() => document.querySelector("#navRows")?.textContent === "11");
  assert.match(await page.locator("#toastHost").innerText().catch(() => "") + await page.locator("body").innerText(), /Change log/);
  assert.match(await page.locator("body").innerText(), /Removed 1 exact duplicate rows/);
  assert.equal(await page.locator('[data-action="undo"]').isDisabled(), false);
});

await step("fill numeric blanks with zero, then undo, then restore as imported", async () => {
  await go("clean");
  await page.selectOption("#fillStrategy", "zero");
  await action("apply-missing");
  await page.waitForFunction(() => /Filled 1 blank cells/.test(document.body.innerText));
  await go("clean");
  assert.equal(await page.locator(".panel .insight-list li").count(), 2, "two change-log entries expected");
  await action("undo");
  await page.waitForFunction(() => document.querySelector("#navRows")?.textContent === "11");
  await go("clean");
  assert.match(await page.locator("body").innerText(), /Undid|Change log/);
  await action("reset-data");
  await page.waitForFunction(() => document.querySelector("#navRows")?.textContent === "12");
  assert.equal(await navRows(), "12");
});

await step("formula builder adds a derived column", async () => {
  await go("formulas");
  await page.fill("#formulaName", "revenue_per_unit");
  await page.fill("#formulaExpr", "[revenue] / [units]");
  await action("apply-formula");
  await page.waitForSelector("#formulaHost .result-message.ok");
  assert.match(await page.locator("#formulaHost").innerText(), /revenue_per_unit/);
});

await step("regression reports the slope standard error and p-value", async () => {
  await go("regression");
  await action("run-regression");
  await page.waitForSelector("#regHost .result-box");
  const text = await page.locator("#regHost").innerText();
  assert.match(text, /Standard error of the slope/);
  assert.match(text, /Two-sided p-value for the slope/);
});

await step("Welch test reports a confidence interval and Cohen's d", async () => {
  await go("hypothesis");
  await page.selectOption("#testA", "North");
  await page.selectOption("#testB", "South");
  await action("run-hypothesis");
  await page.waitForSelector("#testHost .result-box");
  const text = await page.locator("#testHost").innerText();
  assert.match(text, /95% confidence interval/);
  assert.match(text, /Cohen’s d/);
});

await step("descriptive statistics table renders", async () => {
  await go("statistics");
  assert.match(await page.locator("#statsHost").innerText(), /Field/);
});

await step("insights brief downloads with the preparation log", async () => {
  await go("clean");
  await action("dedupe");
  await page.waitForFunction(() => document.querySelector("#navRows")?.textContent === "11");
  await go("report");
  const [download] = await Promise.all([page.waitForEvent("download"), action("export-report")]);
  const body = readFileSync(await download.path(), "utf8");
  assert.match(body, /## Data preparation log/);
  assert.match(body, /Removed 1 exact duplicate rows/);
});

await step("SQL results reflect the current data after changes (cache is rebuilt)", async () => {
  await go("sql");
  await page.fill("#sqlEditor", "SELECT COUNT(*) AS n FROM data;");
  await page.click("#runSqlBtn");
  await page.waitForFunction(() => /Query completed/.test(document.querySelector("#sqlMessage")?.innerText || ""));
  assert.match(await page.locator("#sqlHost").innerText(), /\b11\b/);
});

await step("SQL statements cannot change the dataset (rolled back)", async () => {
  await page.fill("#sqlEditor", "DELETE FROM data;");
  await page.click("#runSqlBtn");
  await page.waitForFunction(() => /SQL statement completed|Query completed/.test(document.querySelector("#sqlMessage")?.innerText || ""));
  await page.fill("#sqlEditor", "SELECT COUNT(*) AS n FROM data;");
  await page.click("#runSqlBtn");
  await page.waitForFunction(() => /Query completed/.test(document.querySelector("#sqlMessage")?.innerText || ""));
  assert.match(await page.locator("#sqlHost").innerText(), /\b11\b/);
  assert.equal(await navRows(), "11");
});

await step("Excel import: sheet picker and date-only cells as ISO dates", async () => {
  await go("import");
  await page.setInputFiles("#fileInput", xlsx);
  await page.waitForSelector("#excelSheetPicker:not([hidden])");
  await page.selectOption("#excelSheet", { label: "Sales" });
  await action("import-excel-sheet");
  await page.waitForFunction(() => document.querySelector("#navRows")?.textContent === "2");
  await go("dataset");
  assert.match(await page.locator("#dataTableHost").innerText(), /2026-04-01/);
});

await step("no network requests leave the file (everything is bundled)", async () => {
  assert.deepEqual(externalRequests, [], "external requests: " + externalRequests.join(", "));
});

await step("no page or console errors", async () => {
  assert.deepEqual(problems, [], problems.join("\n"));
});

await browser.close();
let failed = 0;
for (const [status, name] of steps) { console.log(status.padEnd(5), name); if (status === "FAIL") failed++; }
console.log(`\n${steps.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
