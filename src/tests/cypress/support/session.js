// Cypress's browser grants notifications but cannot register for push, so Odoo would show a warning over the page.
Cypress.on("window:before:load", (win) => {
  if (win.Notification) {
    Object.defineProperty(win.Notification, "permission", { get: () => "denied" });
  }
});

// Signs in as a demo user. Demo users share the password of MEDILAB_DEMO_PASSWORD, which the demo module sets.
export function signIn(login) {
  cy.env(["demoPassword"]).then(({ demoPassword }) => {
    cy.visit("/web/login");
    cy.get("input[name=login]").type(login);
    cy.get("input[name=password]").type(`${demoPassword}{enter}`, { log: false });
    cy.location("pathname").should("match", /^\/odoo/);
  });
}
