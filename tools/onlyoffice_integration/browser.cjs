const http = require("node:http");
const { chromium } = require("playwright");

http.createServer(async (request, response) => {
  response.setHeader("Content-Type", "application/json");
  if (request.url === "/health") return response.end("{}");
  if (request.method !== "POST" || !["/edit", "/edit-many"].includes(request.url)) {
    response.writeHead(404); return response.end("{}");
  }
  let browser;
  let page;
  let stage = "input";
  const failures = [];
  const pluginRequests = [];
  const redact = value => String(value)
    .replace(/https?:\/\/[^\s"'<>]+/g, "[url]")
    .replace(/eyJ[A-Za-z0-9_.-]+/g, "[jwt]")
    .replace(/\/medilab\/laboratory-files\/callback\/[^\s"'<>]+/g, "[callback]");
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
    stage = "launch";
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    async function openEditor(url) {
    page = await context.newPage();
    page.on("pageerror", error => failures.push(redact(error.message)));
    page.on("requestfailed", request => failures.push(redact(request.failure()?.errorText || "request failed")));
    page.on("request", request => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith("/plugin/")) pluginRequests.push(path);
    });
    stage = "navigate";
    await page.goto(url);
    stage = "editor-save";
    await page.evaluate(() => {
      window.relayEdited = false;
      window.relayPoll = setInterval(() => {
        fetch("/state" + window.location.search).then(result => result.json()).then(state => {
          window.relayEdited = state.edited;
        }).catch(() => {});
      }, 100);
    });
    await page.waitForFunction(() => {
      return window.relayEdited && window.sawDirty && !window.dirty;
    }, null, { timeout: 120000 });
    return page;
    }
    const keeper = await openEditor(target.href);
    if (request.url === "/edit-many") {
      for (let index = 1; index <= 25; index++) {
        const url = new URL(target.href);
        url.searchParams.set("participant", String(index));
        const editor = await openEditor(url.href);
        await editor.evaluate(() => window.editor.destroyEditor());
        await editor.close();
      }
      const last = await openEditor(target.href);
      await last.evaluate(() => window.editor.destroyEditor());
      await last.close();
    }
    page = keeper;
    await page.evaluate(() => window.editor.destroyEditor());
    await context.close();
    response.end(JSON.stringify({ edited: true, editorSessions: request.url === "/edit-many" ? 27 : 1 }));
  } catch (error) {
    let state = {};
    if (page) state = await page.evaluate(() => ({ dirty: window.dirty, sawDirty: window.sawDirty })).catch(() => ({}));
    response.writeHead(500);
    response.end(JSON.stringify({ edited: false, stage, error: redact(error.message),
      failures: failures.slice(-20), pluginRequests, state }));
  } finally {
    if (browser) await browser.close();
  }
}).listen(3000, "0.0.0.0");
