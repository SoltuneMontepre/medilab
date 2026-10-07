const { defineConfig } = require("cypress");

module.exports = defineConfig({
  allowCypressEnv: false,
  e2e: {
    baseUrl: process.env.MEDILAB_URL || "http://localhost:8069",
    supportFile: false,
  },
});
