// Génère les icônes PNG de la PWA à partir de public/icons/icon.svg (Chromium via Playwright).
// Usage : node scripts/generate-icons.mjs   (nécessite le paquet « playwright » disponible)
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "icons");
const svg = readFileSync(join(dir, "icon.svg"), "utf8");

const targets = [
  { file: "icon-192.png", size: 192, pad: 0, round: true },
  { file: "icon-512.png", size: 512, pad: 0, round: true },
  // Icône « maskable » : fond plein et pictogramme dans la zone de sécurité (80 %).
  { file: "maskable-512.png", size: 512, pad: 0.1, round: false },
  { file: "apple-touch-icon.png", size: 180, pad: 0, round: false },
];

const browser = await chromium.launch();
const page = await browser.newPage();
for (const t of targets) {
  const inner = Math.round(t.size * (1 - 2 * t.pad));
  const body = t.round ? svg : svg.replace('rx="16"', 'rx="0"');
  await page.setViewportSize({ width: t.size, height: t.size });
  await page.setContent(`<html><body style="margin:0;background:${t.round ? "transparent" : "#0b5f59"};display:grid;place-items:center;width:${t.size}px;height:${t.size}px">
    <div style="width:${inner}px;height:${inner}px">${body.replace("<svg ", `<svg width="${inner}" height="${inner}" `)}</div></body></html>`);
  await page.screenshot({ path: join(dir, t.file), omitBackground: t.round });
  console.log("écrit", t.file);
}
await browser.close();
