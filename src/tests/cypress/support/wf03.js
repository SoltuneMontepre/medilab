import { randomId } from "./odoo";

// WF-03 and the SF-08 settings tests mutate shared settings and trigger the real reminder job; one execution owns those
// resources.
if (/(^|\/)flows\/(wf-03-testing-scheduling\/|sf-08-laboratory-setup\/settings\.cy\.js$)/.test(Cypress.spec.relative)) {
  const execution = { id: randomId(), spec: Cypress.spec.relative };
  let acquired = false;

  before(() => {
    Cypress.expose("wf03Execution", execution);
    return cy.task("odooBeginExecution", execution, { log: false }).then(() => {
      acquired = true;
    });
  });

  after(() => {
    if (!acquired) return;
    return cy.task("odooEndExecution", execution, { log: false }).then(() => {
      Cypress.expose("wf03Execution", null);
      acquired = false;
    });
  });
}
