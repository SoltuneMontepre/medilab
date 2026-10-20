// Cypress's browser grants notifications but cannot register for push, so Odoo would show a warning over the page.
Cypress.on("window:before:load", (win) => {
  if (win.Notification) {
    Object.defineProperty(win.Notification, "permission", { get: () => "denied" });
  }
});

// Signs in as a demo user once, and restores that session in later tests: a late response of the previous test's page
// can set its session cookie again, which a new sign-in would then reject as a CSRF failure. Demo users share the
// password of MEDILAB_DEMO_PASSWORD, which the demo module sets.
export function signIn(login) {
  cy.session(login, () => {
    cy.env(["demoPassword"]).then(({ demoPassword }) => {
      cy.visit("/web/login");
      cy.get("input[name=login]").type(login);
      cy.get("input[name=password]").type(`${demoPassword}{enter}`, { log: false });
      cy.location("pathname").should("match", /^\/odoo/);
    });
  });
}
