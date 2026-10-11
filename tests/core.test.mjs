// Unit tests for js/core.js. The file is a plain browser script, so it is loaded
// into a sandbox here. Reference values were computed with SciPy 1.18 (see README).
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { test } from "node:test";
import assert from "node:assert/strict";

const ctx = vm.createContext({});
vm.runInContext(readFileSync(new URL("../js/core.js", import.meta.url), "utf8"), ctx);
// Results come back from another realm; normalise them before comparing.
const plain = (x) => JSON.parse(JSON.stringify(x));
const near = (actual, expected, tol = 1e-9, label = "") =>
  assert.ok(Math.abs(actual - expected) <= tol * Math.max(1, Math.abs(expected)),
    `${label} expected ${expected}, got ${actual}`);

test("parseCSV handles quoted commas, escaped quotes, CRLF and numbers", () => {
  const text = 'id,name,amount\r\n1,"Smith, Jo",12.5\r\n2,"say ""hi""",\r\n\r\n3,plain,7\r\n';
  const rows = plain(ctx.parseCSV(text, ","));
  assert.deepEqual(rows, [
    { id: 1, name: "Smith, Jo", amount: 12.5 },
    { id: 2, name: 'say "hi"', amount: null },
    { id: 3, name: "plain", amount: 7 },
  ]);
});

test("csvString output parses back to the same values", () => {
  const original = [{ a: "x,y", b: 'q"uote', c: 3 }, { a: "line\nbreak", b: "", c: null }];
  const back = plain(ctx.parseCSV(ctx.csvString(original), ","));
  assert.deepEqual(back, [{ a: "x,y", b: 'q"uote', c: 3 }, { a: "line\nbreak", b: null, c: null }]);
});

test("descriptive statistics match hand-checked values", () => {
  near(ctx.mean([1, 2, 3, 4]), 2.5);
  near(ctx.median([1, 2, 3, 4]), 2.5);
  near(ctx.sd([2, 4, 4, 4, 5, 5, 7, 9]), 2.1380899352993947); // sample SD (n-1)
  near(ctx.quantile([1, 2, 3, 4, 5, 6, 7, 8, 9], 0.25), 3);
  assert.deepEqual(plain(ctx.uniq(["a", "", null, "a", "b"])), ["a", "b"]);
});

test("t quantiles match SciPy", () => {
  near(ctx.tQuantile(0.975, 10), 2.228138851986274, 1e-7, "df10");
  near(ctx.tQuantile(0.975, 3), 3.1824463052837078, 1e-7, "df3");
  near(ctx.tQuantile(0.975, 30), 2.0422724563012378, 1e-7, "df30");
});

test("regularised incomplete beta matches SciPy betainc", () => {
  const cases = [[0.3, 0.5, 5, 0.9347377538310915], [0.4, 2, 3, 0.5247999999999999],
    [0.9, 10, 0.5, 0.15164090963470994], [0.2, 4.5, 2, 0.003291492062879691]];
  for (const [x, a, b, ref] of cases) near(ctx.betaI(x, a, b), ref, 1e-7, `betaI(${x},${a},${b})`);
});

test("Welch t-test matches SciPy (statistic, df, p, CI and Cohen's d)", () => {
  const A = [12.1, 14.3, 11.8, 15.0, 13.2, 12.9, 14.8, 13.5];
  const B = [10.2, 11.9, 9.8, 12.4, 10.9, 11.2, 10.5];
  const r = plain(ctx.welch(A, B));
  near(r.t, 4.509258171712263, 1e-7, "t");
  near(r.df, 12.864915587312177, 1e-7, "df");
  near(r.p, 0.0006024667983475674, 1e-6, "p");
  near(r.diff, 2.4642857142857153, 1e-9, "diff");
  near(r.se, 0.5464947049926779, 1e-7, "se");
  near(r.ci95[0], 1.2823942641252888, 1e-6, "ci low");
  near(r.ci95[1], 3.646177164446142, 1e-6, "ci high");
  near(r.cohenD, 2.2934699664987526, 1e-7, "d");
});

test("Welch rejects groups that cannot be tested", () => {
  assert.throws(() => ctx.welch([1], [2, 3]), /at least two/);
  assert.throws(() => ctx.welch([1, 1, 1], [2, 2, 2]), /zero estimated variance/);
});

test("regression slope statistics match SciPy linregress", () => {
  const x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
  const y = [2.3, 4.1, 6.2, 7.9, 10.4, 11.8, 14.6, 15.7, 18.1, 20.4, 21.9, 24.2];
  const m = plain(ctx.regressionStats(x.map((v, i) => ({ x: v, y: y[i] }))));
  near(m.slope, 1.9937062937062935, 1e-9, "slope");
  near(m.intercept, 0.17424242424242564, 1e-9, "intercept");
  near(m.r, 0.9992961393689036, 1e-9, "r");
  near(m.seSlope, 0.023667308469942683, 1e-7, "se");
  near(m.t, 84.23882657541252, 1e-6, "t");
  assert.equal(m.df, 10);
  assert.ok(m.p < 1e-12, `p should be tiny, got ${m.p}`);
});

test("regression on an exact line reports zero standard error and p = 0", () => {
  const m = plain(ctx.regressionStats([1, 2, 3, 4].map((v) => ({ x: v, y: 2 * v + 1 }))));
  near(m.slope, 2); near(m.intercept, 1); near(m.r2, 1);
  assert.equal(m.seSlope, 0);
  assert.equal(m.p, 0);
});

test("regression rejects too few pairs and constant variables", () => {
  assert.throws(() => ctx.regressionStats([{ x: 1, y: 1 }, { x: 2, y: 2 }]), /three/);
  assert.throws(() => ctx.regressionStats([{ x: 1, y: 5 }, { x: 2, y: 5 }, { x: 3, y: 5 }]), /constant/);
});

test("formulaEval respects precedence, parentheses and column references", () => {
  const columns = ["a", "b"];
  const row = { a: 6, b: 4 };
  assert.equal(ctx.formulaEval("[a] + [b] * 2", row, columns), 14);
  assert.equal(ctx.formulaEval("([a] + [b]) * 2", row, columns), 20);
  assert.equal(ctx.formulaEval("-[a] % 4", row, columns), -2);
  assert.equal(ctx.formulaEval("1e2 / 4", row, columns), 25);
});

test("formulaEval returns null for blanks and division by zero, and rejects bad input", () => {
  const columns = ["a", "b"];
  assert.equal(ctx.formulaEval("[a] / [b]", { a: 1, b: 0 }, columns), null);
  assert.equal(ctx.formulaEval("[a] * [b]", { a: 1, b: null }, columns), null);
  assert.throws(() => ctx.formulaEval("[missing] + 1", { a: 1 }, columns), /Unknown column/);
  assert.throws(() => ctx.formulaEval("[a] + 1)", { a: 1 }, columns), /Unexpected token|Invalid/);
  assert.throws(() => ctx.formulaEval("[a] ^ 2", { a: 1 }, columns), /Invalid formula/);
});

test("normalizeRows accepts objects and arrays of arrays", () => {
  const objs = plain(ctx.normalizeRows([{ a: 1 }, { b: "" }]));
  assert.deepEqual(objs, [{ a: 1, b: null }, { a: null, b: null }]);
  const arrs = plain(ctx.normalizeRows([["name", "score"], ["x", 3]]));
  assert.deepEqual(arrs, [{ name: "x", score: 3 }]);
  assert.throws(() => ctx.normalizeRows("nope"), /JSON array/);
});

test("coerceRows enforces the row limit", () => {
  assert.throws(() => ctx.coerceRows([]), /No data rows/);
  assert.throws(() => ctx.coerceRows(new Array(250001).fill({ a: 1 })), /250,000/);
  assert.equal(ctx.coerceRows([{ a: "" }]).length, 1);
});

test("excelValue turns date-only cells into ISO dates and leaves other values alone", () => {
  // Dates are created inside the sandbox so instanceof Date matches, as it does in the app.
  const D = (s) => vm.runInContext(`new Date(${JSON.stringify(s)})`, ctx);
  assert.equal(ctx.excelValue(D("2026-03-01T00:00:00.000Z")), "2026-03-01");
  assert.equal(ctx.excelValue(D("2026-03-01T10:30:00.000Z")), "2026-03-01T10:30:00.000Z");
  assert.equal(ctx.excelValue(42), 42);
  assert.equal(ctx.excelValue("text"), "text");
});
