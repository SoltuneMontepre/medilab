import { register as registerCypressGrep } from "@cypress/grep";

import "./commands";
import { removeServiceWorkers } from "./odoo";
import "./steps";
import "./watch";
import "./wf03";

registerCypressGrep();

// Specs that submit the login form themselves need it too; signIn() also runs it for a sign-in in a before() hook.
beforeEach(removeServiceWorkers);

// The page's own requests stay out of the Command Log, which then reads as the test's steps; the routes a test
// intercepts itself still show. MEDILAB_E2E_NETWORK_LOG=1 shows every request.
beforeEach(() => {
  if (!Cypress.expose("networkLog")) cy.intercept({ resourceType: /xhr|fetch/ }, { log: false });
});

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
