// Automated real browser input only. The Python observer establishes callback and immutable-byte persistence.
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
const packageRoot = path.join(root, ".local/onlyoffice-tools/node_modules/playwright");
const { chromium } = require(packageRoot);
const { isDocumentEditorFrame } = require("./managed_frame.cjs");

async function readOwnedInput() {
  let raw = "";
  for await (const part of process.stdin) {
    raw += part;
    if (raw.length > 8192) throw new Error("Input too large");
  }
  const input = JSON.parse(raw);
  const local = value => /^http:\/\/localhost:([1-9]\d{0,4})$/.test(value) && Number(new URL(value).port) <= 65535;
  if (!/^[a-f0-9]{32}$/.test(input.nonce) || !local(input.base) || !local(input.editor) ||
      !Number.isSafeInteger(input.fileId) || input.fileId <= 0 || input.login !== "demo.tester" ||
      input.marker !== "MEDILAB_MANAGED_" + input.nonce || typeof input.password !== "string") {
    throw new Error("Unexpected managed input");
  }
  if (require(path.join(packageRoot, "package.json")).version !== "1.56.1") throw new Error("Unexpected driver version");
  const directory = path.join(root, ".local/onlyoffice-managed", input.nonce);
  if (!fs.statSync(directory).isDirectory() || fs.lstatSync(directory).isSymbolicLink()) throw new Error("Missing owned output");
  const manifestFile = path.join(directory, "manifest.json");
  if (fs.lstatSync(manifestFile).isSymbolicLink()) throw new Error("Linked manifest refused");
  const manifest = JSON.parse(fs.readFileSync(manifestFile, "utf8"));
  if (manifest.status !== "running" || manifest.stage !== "real_browser" || manifest.nonce !== input.nonce ||
      manifest.actor !== input.login || manifest.file_id !== input.fileId ||
      manifest.selection.odoo_origin !== input.base || manifest.selection.editor_origin !== input.editor ||
      manifest.edit_marker !== input.marker) throw new Error("Input differs from the reviewed owned manifest");
  return { input, directory };
}

async function main() {
  const { input, directory } = await readOwnedInput();
  const resultPath = path.join(directory, "browser-result.json");
  if (fs.existsSync(resultPath)) throw new Error("A browser result already exists");
  function record(result) {
    const temporary = path.join(directory, `.browser-result-${process.pid}.tmp`);
    const descriptor = fs.openSync(temporary, "wx", 0o600);
    try {
      fs.writeFileSync(descriptor, JSON.stringify({ format: 1, nonce: input.nonce, file_id: input.fileId, ...result }, null, 2));
      fs.fsyncSync(descriptor);
    } finally { fs.closeSync(descriptor); }
    try { fs.linkSync(temporary, resultPath); } finally { fs.unlinkSync(temporary); }
    console.log("Managed browser result recorded.");
  }
  let context;
  let page;
  let stage = "launch";
  let timedOut = false;
  let responseCount = 0;
  let commandLine = [];
  const deadline = setTimeout(() => {
    timedOut = true;
    if (context) context.close().catch(() => {});
  }, 180000);
  try {
    context = await chromium.launchPersistentContext(path.join(directory, "browser-profile"), {
      executablePath: path.join(root, "tools/onlyoffice_integration/managed_browser_exec.py"),
      headless: true,
      chromiumSandbox: true,
      ignoreHTTPSErrors: false,
      viewport: { width: 1440, height: 1000 },
      env: { ...process.env,
        MEDILAB_MANAGED_NONCE: input.nonce,
        XDG_CONFIG_HOME: path.join(directory, "browser-config"),
        XDG_CACHE_HOME: path.join(directory, "browser-cache"),
        XDG_DATA_HOME: path.join(directory, "browser-data"),
      },
    });
    page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    commandLine = (await cdp.send("Browser.getBrowserCommandLine")).arguments;
    const forbidden = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-web-security",
      "--ignore-certificate-errors", "--allow-running-insecure-content", "--enable-unsafe-swiftshader", "--disable-gpu"];
    if (commandLine.some(argument => forbidden.some(flag => argument === flag || argument.startsWith(flag + "=")))) {
      throw new Error("The actual browser command line weakens its security or graphics policy");
    }
    page.on("response", response => {
      const url = new URL(response.url());
      if (url.origin === input.editor && url.pathname === "/web-apps/apps/api/documents/api.js" && response.status() === 200) responseCount++;
    });
    const editorPath = `/medilab/laboratory-files/${input.fileId}/edit`;
    stage = "login-return";
    await page.goto(input.base + editorPath);
    const login = new URL(page.url());
    if (login.origin !== input.base || login.pathname !== "/web/login" || login.searchParams.get("redirect") !== editorPath) {
      throw new Error("Unexpected normal login return");
    }
    await page.locator("input[name=login]").fill(input.login);
    await page.locator("input[name=password]").fill(input.password);
    await page.locator("button[type=submit]").click();
    await page.waitForURL(url => url.origin === input.base && url.pathname === editorPath);
    stage = "native-editor-ready";
    await page.waitForFunction(() => {
      const status = document.getElementById("editor-status");
      const ready = document.querySelector('[data-message="ready"]');
      return Boolean(status && status.textContent === ready?.textContent);
    }, null, { timeout: 120000 });
    const frame = page.frames().find(value => isDocumentEditorFrame(value.url(), input.editor));
    if (!frame || responseCount < 1) throw new Error("Missing real Document Server response or frame");
    await page.screenshot({ path: path.join(directory, "editor-ready.png") });
    await page.evaluate(() => {
      window.managedTransitions = [];
      const status = document.getElementById("editor-status");
      new MutationObserver(() => {
        const state = [...document.querySelectorAll("[data-message]")]
          .find(node => node.textContent === status.textContent)?.dataset.message;
        if (state) window.managedTransitions.push(state);
      }).observe(status, { childList: true, subtree: true, characterData: true });
    });
    stage = "native-keyboard-edit";
    await frame.locator("#id_viewer_overlay").click({ position: { x: 300, y: 250 } });
    await page.keyboard.press("Control+Home");
    await page.keyboard.type(input.marker);
    await page.keyboard.press("Control+s");
    await page.waitForFunction(() => window.managedTransitions.includes("editing") &&
      window.managedTransitions.includes("sent") && document.getElementById("editor-status").textContent ===
      document.querySelector('[data-message="sent"]').textContent, null, { timeout: 60000 });
    await page.screenshot({ path: path.join(directory, "editor-after-input.png") });
    stage = "normal-editor-close";
    await page.goto("about:blank");
    await context.close();
    context = null;
    if (timedOut) throw new Error("Overall deadline exceeded");
    record({ automated: true, manual_gui: false, keyboard_edit: true,
      real_editor_api_responses: responseCount, chromium_sandbox: true, tls_verification: true,
      normal_close: true, stage: "browser_completed", command_line: commandLine });
  } catch (error) {
    let screenshot = false;
    let editorState = "unavailable";
    if (page) {
      try {
        await page.screenshot({ path: path.join(directory, "browser-failure.png"), timeout: 5000 });
        screenshot = true;
        editorState = await page.evaluate(() => [...document.querySelectorAll("[data-message]")]
          .find(node => node.textContent === document.getElementById("editor-status")?.textContent)?.dataset.message ?? "unknown");
      } catch { screenshot = false; }
    }
    record({ automated: true, keyboard_edit: false, stage, command_line: commandLine,
      failure_type: error.name, timed_out: timedOut, real_editor_api_responses: responseCount,
      failure_screenshot: screenshot, editor_state: editorState,
      ...(stage === "launch" ? { launch_diagnostic: error.message.replace(/https?:\/\/[^\s"'<>]+/g, "[url]").slice(0,3000) } : {}) });
    process.exitCode = 1;
  } finally {
    clearTimeout(deadline);
    if (context) await context.close().catch(() => {});
  }
}
main().catch(error => {
  console.log(JSON.stringify({ keyboard_edit: false, stage: "input", failure_type: error.name }));
  process.exitCode = 1;
});
