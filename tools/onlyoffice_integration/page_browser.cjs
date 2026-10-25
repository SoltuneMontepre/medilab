// Released-page probe. Loopback proxies provide the isolated HTTP services at approved local origins.
const http = require("node:http");
const net = require("node:net");
const { chromium } = require("playwright");

function proxy(port, host, upstreamPort) {
  const server = http.createServer((req, res) => {
    const upstream = http.request({ hostname: host, port: upstreamPort, path: req.url,
      method: req.method, headers: req.headers }, answer => {
      res.writeHead(answer.statusCode, answer.headers); answer.pipe(res);
    });
    upstream.on("error", () => { res.writeHead(502); res.end(); });
    req.pipe(upstream);
  });
  server.on("upgrade", (req, socket, head) => {
    const upstream = net.connect(upstreamPort, host, () => {
      upstream.write(`${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`);
      for (const [name, value] of Object.entries(req.headers)) upstream.write(`${name}: ${value}\r\n`);
      upstream.write("\r\n"); upstream.write(head); socket.pipe(upstream).pipe(socket);
    });
    upstream.on("error", () => socket.destroy());
    socket.on("error", () => upstream.destroy());
  });
  server.listen(port, "127.0.0.1");
}
proxy(8081, "documentserver", 80);
proxy(3900, "garage", 3900);

async function openEditor(browser, input, credentials) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", () => errors.push("pageerror"));
  await page.goto(input.url);
  const login = new URL(page.url());
  const requested = new URL(input.url);
  if (login.pathname !== "/web/login" || login.searchParams.get("redirect") !== requested.pathname) {
    throw new Error("Unsafe browser login return");
  }
  await page.locator("input[name=login]").fill(credentials.login);
  await page.locator("input[name=password]").fill(credentials.password);
  await page.locator("button[type=submit]").click();
  await page.waitForURL(value => value.pathname === requested.pathname);
  await page.locator("#editor-status").filter({ hasText: "Editor ready." }).waitFor({ timeout: 120000 });
  const frame = page.frames().find(value => /\/web-apps\/apps\/(documenteditor|spreadsheeteditor|presentationeditor)\//.test(value.url()));
  if (!frame) throw new Error("Missing native editor frame");
  const xssAbsent = await page.evaluate(() => window.editorXss === undefined &&
    document.querySelector("#laboratory-editor img[src=x]") === null);
  if (!xssAbsent) throw new Error("Unsafe configuration rendering");
  return { context, page, frame, xssAbsent, errors };
}

async function edit(editor, extension, marker, secondary) {
  if (extension === "xlsx") {
    const address = editor.frame.locator("#ce-cell-name");
    await address.fill(secondary ? "B1" : "A1");
    await address.press("Enter");
    const formula = editor.frame.locator("#ce-cell-content");
    await formula.fill(marker);
    await formula.press("Enter");
  } else {
    const overlay = editor.frame.locator("#id_viewer_overlay");
    if (extension === "pptx") {
      await overlay.dblclick({ position: { x: 300, y: 250 } });
    } else {
      await overlay.click({ position: { x: 300, y: 250 } });
      await editor.page.keyboard.press("Control+Home");
    }
    await editor.page.keyboard.type(marker);
    await editor.page.keyboard.press("Escape");
  }
  await editor.page.keyboard.press("Control+s");
  await editor.page.waitForTimeout(1500);
}

http.createServer(async (request, response) => {
  response.setHeader("Content-Type", "application/json");
  if (request.url === "/health") return response.end("{}");
  if (request.method !== "POST" || request.url !== "/page") {
    response.writeHead(404); return response.end("{}");
  }
  let browser;
  let page;
  let stage = "input";
  try {
    let raw = "";
    for await (const part of request) {
      raw += part;
      if (raw.length > 4096) throw new Error("Request too large");
    }
    const input = JSON.parse(raw);
    const url = new URL(input.url);
    if (url.hostname !== "runner" || url.protocol !== "http:" || url.username || url.password || url.hash ||
        !/^\/medilab\/laboratory-files\/[1-9][0-9]*\/edit$/.test(url.pathname) || url.search ||
        !["docx", "xlsx", "pptx"].includes(input.extension ?? "docx") ||
        !/^MEDILAB_PAGE_[a-f0-9]{32}$/.test(input.marker)) {
      throw new Error("Unexpected test origin");
    }
    browser = await chromium.launch({ headless: true });
    stage = "login-return";
    const primary = await openEditor(browser, input, { login: "admin", password: "admin" });
    page = primary.page;
    let secondary;
    if (input.coeditor) {
      stage = "coeditor-login";
      secondary = await openEditor(browser, input, input.coeditor);
      stage = "coeditor-edit";
      await edit(secondary, input.extension, input.marker + "_MEMBER", true);
    }
    stage = "edit";
    await edit(primary, input.extension ?? "docx", input.marker, false);
    const hold = input.holdSeconds ?? 3;
    if (!Number.isInteger(hold) || hold < 3 || hold > 960) throw new Error("Invalid hold duration");
    await page.waitForTimeout(hold * 1000);
    stage = "close";
    if (secondary) {
      await secondary.page.goto("about:blank");
      await secondary.context.close();
    }
    await page.goto("about:blank");
    await primary.context.close();
    response.end(JSON.stringify({
      loginReturn: true, editorReady: true, keyboardEdit: true, holdSeconds: hold,
      editorSessions: secondary ? 2 : 1, xssAbsent: primary.xssAbsent && (!secondary || secondary.xssAbsent),
      errors: [...primary.errors, ...(secondary?.errors ?? [])],
    }));
  } catch (error) {
    response.writeHead(500);
    // Native error messages can contain capabilities; retain only the fixed stage and error type.
    const frames = [];
    if (page) {
      await page.screenshot({ path: "/tmp/page-probe-failure.png" }).catch(() => {});
      for (const frame of page.frames()) {
        frames.push(await frame.evaluate(() => Array.from(document.querySelectorAll("canvas, textarea, [contenteditable]"))
          .map(el => ({ tag: el.tagName, id: el.id, editable: el.getAttribute("contenteditable") })).slice(0, 20)).catch(() => []));
      }
    }
    response.end(JSON.stringify({ stage, error: error.name, frames }));
  } finally {
    if (browser) await browser.close();
  }
}).listen(3000, "0.0.0.0");
