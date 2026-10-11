// Regenerates tests/fixtures/workbook.xlsx with the vendored SheetJS build.
// Run: node tests/make-fixtures.mjs
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const XLSX = require("../vendor/xlsx/xlsx.full.min.js");
const wb = XLSX.utils.book_new();
const sales = [
  { order_id: "RD-3001", order_date: new Date("2026-04-01T00:00:00Z"), amount: 120.5, region: "North" },
  { order_id: "RD-3002", order_date: new Date("2026-04-02T00:00:00Z"), amount: 80, region: "South" },
];
XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(sales), "Sales");
XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet([{ team: "Ops", headcount: 4 }]), "Teams");
writeFileSync(new URL("./fixtures/workbook.xlsx", import.meta.url), XLSX.write(wb, { type: "buffer", bookType: "xlsx", cellDates: true }));
console.log("wrote tests/fixtures/workbook.xlsx");
