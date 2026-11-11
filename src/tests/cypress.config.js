const { defineConfig } = require("cypress");
const { plugin: grepPlugin } = require("@cypress/grep/plugin");
const { odooTasks } = require("./cypress/plugins/odoo");
const { executionTasks } = require("./cypress/plugins/execution");
const { appendFileSync } = require("node:fs");

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
    experimentalInteractiveRunEvents: true,
    supportFile: "cypress/support/e2e.js",
    setupNodeEvents(on, config) {
      grepPlugin(config);
      const backend = odooTasks(config.baseUrl, demoPassword);
      const execution = executionTasks({
        call: backend.odooCall,
        settings: backend,
        baseUrl: config.baseUrl,
        trace: process.env.MEDILAB_E2E_TRACE
          ? (event) => appendFileSync(process.env.MEDILAB_E2E_TRACE, `${JSON.stringify(event)}\n`, { mode: 0o600 })
          : undefined,
      });
      on("task", {
        ...backend,
        odooCall: execution.call,
        odooCheckpointSettings: execution.checkpoint,
        odooRestoreSettings: execution.restore,
        odooBeginExecution: execution.begin,
        odooEndExecution: execution.finish,
      });
      on("after:run", () => execution.cleanup());
      return config;
    },
  },
});
