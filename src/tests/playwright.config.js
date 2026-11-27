const { defineConfig } = require("@playwright/test");

// MEDILAB_JOURNEY_WATCH=1 opens each actor's browser on the screen and waits MEDILAB_JOURNEY_WATCH_DELAY milliseconds,
// 600 by default, before every click and keystroke, so a person can follow the journey.
const watching = process.env.MEDILAB_JOURNEY_WATCH === "1";
const delay = Number(process.env.MEDILAB_JOURNEY_WATCH_DELAY || 600);

module.exports = defineConfig({
  testDir: "playwright/journey",
  outputDir: "playwright/.output/results",
  // The flows continue one another on one database, so they run one at a time in the order of their file names.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  // A flow is one test of many screens.
  timeout: (watching ? 60 : 10) * 60 * 1000,
  expect: { timeout: 15000 },
  reporter: [["list"], ["html", { outputFolder: "playwright/.output/report", open: "never" }]],
  use: {
    headless: !watching,
    // MEDILAB_JOURNEY_BROWSER=chrome uses the installed Google Chrome instead of Playwright's Chromium.
    channel: process.env.MEDILAB_JOURNEY_BROWSER || undefined,
    launchOptions: { slowMo: watching ? delay : 0 },
    baseURL: process.env.MEDILAB_URL || "http://localhost:8069",
    viewport: { width: 1440, height: 900 },
    timezoneId: "Asia/Ho_Chi_Minh",
    actionTimeout: watching ? 15000 + 20 * delay : 15000,
    navigationTimeout: 30000,
    // Odoo's cached page and background fetches would load a user's first page twice at once.
    serviceWorkers: "block",
    // Each actor's browser records its own video; see playwright/support/journey.js.
    video: "off",
    trace: "off",
  },
});
