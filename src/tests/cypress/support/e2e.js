import { register as registerCypressGrep } from "@cypress/grep";

import "./commands";
import "./wf03";

registerCypressGrep();

// The test browser allows notifications but has no push service, so Odoo's attempt to subscribe to web push fails
// with a toast on every page. Without the permission Odoo does not try.
Cypress.on("window:before:load", (win) => {
  if (win.Notification) {
    Object.defineProperty(win.Notification, "permission", { get: () => "default" });
  }
});

// A list that resizes while it redraws, such as after a row button, makes the browser report a ResizeObserver loop.
// The report is a notice, not an error of the page.
Cypress.on("uncaught:exception", (error) => !error.message.includes("ResizeObserver loop"));
