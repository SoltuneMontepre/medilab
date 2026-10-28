// WF-03 mutates shared settings and triggers the real reminder job; one execution owns those resources.
if (/(^|\/)flows\/wf-03-testing-scheduling\//.test(Cypress.spec.relative)) {
  const execution = { id: crypto.randomUUID(), spec: Cypress.spec.relative };
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
