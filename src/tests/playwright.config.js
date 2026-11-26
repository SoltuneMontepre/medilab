const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "playwright/journey",
  outputDir: "playwright/.output/results",
  // The flows continue one another on one database, so they run one at a time in the order of their file names.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  // A flow is one test of many screens.
  timeout: 10 * 60 * 1000,
  expect: { timeout: 15000 },
  reporter: [["list"], ["html", { outputFolder: "playwright/.output/report", open: "never" }]],
  use: {
    baseURL: process.env.MEDILAB_URL || "http://localhost:8069",
    viewport: { width: 1440, height: 900 },
    timezoneId: "Asia/Ho_Chi_Minh",
    actionTimeout: 15000,
    navigationTimeout: 30000,
    // Odoo's cached page and background fetches would load a user's first page twice at once.
    serviceWorkers: "block",
    // Each actor's browser records its own video; see playwright/support/journey.js.
    video: "off",
    trace: "off",
  },
});
