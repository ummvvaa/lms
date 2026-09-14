// Печать обзора телефонной версии в PDF (фаза 74, доводка).
// Открывает локальный HTML и печатает: A4, фон включён, поля минимальные.
// Запускается сборщиком build_mobile_review.py, руками: node print_mobile_review.mjs <html> <pdf>
import { chromium } from "@playwright/test";

const [html, pdf] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`file://${html}`, { waitUntil: "load" });
await page.pdf({
  path: pdf,
  format: "A4",
  printBackground: true,
  margin: { top: "8mm", right: "8mm", bottom: "8mm", left: "8mm" },
  preferCSSPageSize: false,
});
await browser.close();
