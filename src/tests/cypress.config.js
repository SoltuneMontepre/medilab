const { defineConfig } = require("cypress");
const { plugin: grepPlugin } = require("@cypress/grep/plugin");
const { odooTasks } = require("./cypress/plugins/odoo");

const demoPassword = process.env.MEDILAB_DEMO_PASSWORD || "demo";

module.exports = defineConfig({
  env: {
    demoPassword,
  },
  expose: {
    // `--expose grep=TC-WF01-A5` loads only the specs with a matching test and runs only those tests.
    grepFilterSpecs: true,
    grepOmitFiltered: true,
  },
  e2e: {
    baseUrl: process.env.MEDILAB_URL || "http://localhost:8069",
    // Odoo screens load their data after the page; four seconds is often too short.
    defaultCommandTimeout: 10000,
    supportFile: "cypress/support/e2e.js",
    setupNodeEvents(on, config) {
      grepPlugin(config);
      on("task", odooTasks(config.baseUrl, demoPassword));
      return config;
    },
  },
});
