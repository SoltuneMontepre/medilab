const { defineConfig } = require("cypress");
const { plugin: grepPlugin } = require("@cypress/grep/plugin");
const { odooTasks } = require("./cypress/plugins/odoo");
const { executionTasks } = require("./cypress/plugins/execution");
const { payosTasks } = require("./cypress/plugins/payos");
const { appendFileSync } = require("node:fs");

const demoPassword = process.env.MEDILAB_DEMO_PASSWORD || "demo";

module.exports = defineConfig({
  projectId: "kry6yc",
  env: {
    demoPassword,
  },
  expose: {
    // `--expose grep=TC-WF01-A5` loads only the specs with a matching test and runs only those tests.
    grepFilterSpecs: true,
    grepOmitFiltered: true,
    // The watch mode of support/watch.js and the page's requests in the Command Log of support/e2e.js.
    watch: process.env.MEDILAB_E2E_WATCH || "",
    watchDelay: process.env.MEDILAB_E2E_WATCH_DELAY || "",
    networkLog: process.env.MEDILAB_E2E_NETWORK_LOG === "1",
  },
  e2e: {
    baseUrl: process.env.MEDILAB_URL || "http://localhost:8069",
    // Odoo screens load their data after the page; four seconds is often too short.
    defaultCommandTimeout: 10000,
    // A laptop screen, so the back office shows its desktop layout.
    viewportWidth: 1440,
    viewportHeight: 900,
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
        ...payosTasks(config.baseUrl),
        odooCall: execution.call,
        odooCheckpointSettings: execution.checkpoint,
        odooRestoreSettings: execution.restore,
        odooBeginExecution: execution.begin,
        odooEndExecution: execution.finish,
        // A step of the test in the terminal of a headless run.
        logStep(label) {
          console.log(`      ${label}`);
          return null;
        },
      });
      on("after:run", () => execution.cleanup());
      const timings = process.env.MEDILAB_E2E_TIMINGS;
      if (timings && config.isTextTerminal) {
        on("after:spec", (spec, results) => {
          const { startedAt, endedAt } = results.stats;
          const duration = Date.parse(endedAt) - Date.parse(startedAt);
          appendFileSync(timings, `spec\t${spec.relative}\t${duration}\n`);
        });
      }
      return config;
    },
  },
});
