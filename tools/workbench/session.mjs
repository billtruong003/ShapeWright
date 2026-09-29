// A scripted human session in a real browser (Phase 15 gate, docs/WORKBENCH.md).
// Usage: node session.mjs URL ASSET PARAM VALUE SCREENSHOT.png
// Clicks through: open asset -> move a parameter -> Preview -> Apply -> Snapshot -> Export,
// then prints the commands the page ran (from its own console panel) as JSON.
import { chromium } from "playwright-core";

const [url, asset, param, value, shot] = process.argv.slice(2);
const exe = process.env.SW_CHROMIUM || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const browser = await chromium.launch({ executablePath: exe, args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const idle = () => page.waitForFunction(() => ![...document.querySelectorAll("button")].some(b => b.disabled), null, { timeout: 120000 });
const ran = (text) => page.waitForFunction(t => document.getElementById("console").textContent.includes(t), text, { timeout: 120000 });

await page.goto(url);
await page.click(`#assets li[data-name="${asset}"]`);
await page.waitForFunction(() => document.getElementById("view").naturalWidth > 0, null, { timeout: 120000 });
await idle();

const input = page.locator(`.param[data-name="${param}"] input[type=number]`);
await input.fill(String(value));
await input.dispatchEvent("input");
await page.click("#btn-preview");
await ran(`--set ${param}=${value}`);
await idle();

await page.click("#btn-apply");
await ran(`sw set`);
await idle();

await page.fill("#msg", `${param} ${value} from the workbench`);
await page.fill("#crit", "checked in the browser");
await page.click("#btn-snap");
await ran("sw snapshot");
await idle();

await page.click("#btn-export");
await ran("sw export");
await idle();

await page.screenshot({ path: shot, fullPage: true });
const cmds = await page.$$eval("#console .cmd", els => els.map(e => e.textContent));
console.log(JSON.stringify(cmds));
await browser.close();
