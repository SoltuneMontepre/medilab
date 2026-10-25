const http = require("node:http");
const { chromium } = require("playwright");

http.createServer(async (request, response) => {
  response.setHeader("Content-Type", "application/json");
  if (request.url === "/health") return response.end("{}");
  if (request.method !== "POST" || request.url !== "/edit") {
    response.writeHead(404); return response.end("{}");
  }
  let browser;
  try {
    let raw = "";
    for await (const part of request) {
      raw += part;
      if (raw.length > 4096) throw new Error("Request too large");
    }
    const target = new URL(JSON.parse(raw).url);
    if (target.hostname !== "runner" || target.protocol !== "http:" || target.pathname !== "/editor") {
      throw new Error("Unexpected test origin");
    }
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(target.href);
    await page.waitForFunction(async () => {
      const state = await fetch("/state").then(result => result.json());
      return state.edited && window.sawDirty && !window.dirty;
    }, null, { timeout: 120000 });
    await page.evaluate(() => window.editor.destroyEditor());
    await context.close();
    response.end(JSON.stringify({ edited: true }));
  } catch {
    response.writeHead(500);
    response.end(JSON.stringify({ edited: false }));
  } finally {
    if (browser) await browser.close();
  }
}).listen(3000, "0.0.0.0");
