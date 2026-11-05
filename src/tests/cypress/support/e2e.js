import { register as registerCypressGrep } from "@cypress/grep";

import "./commands";
import { removeServiceWorkers } from "./odoo";
import "./wf03";

registerCypressGrep();

// Specs that submit the login form themselves need it too; signIn() also runs it for a sign-in in a before() hook.
beforeEach(removeServiceWorkers);

// The test browser allows notifications but has no push service, so Odoo's attempt to subscribe to web push fails
// with a toast on every page. Without the permission Odoo does not try.
Cypress.on("window:before:load", (win) => {
  if (win.Notification) {
    Object.defineProperty(win.Notification, "permission", { get: () => "default" });
  }
});
