const { defineConfig } = require("cypress");

module.exports = defineConfig({
  env: {
    demoPassword: process.env.MEDILAB_DEMO_PASSWORD || "demo",
  },
  e2e: {
    baseUrl: process.env.MEDILAB_URL || "http://localhost:8069",
    supportFile: "cypress/support/e2e.js",
  },
});
