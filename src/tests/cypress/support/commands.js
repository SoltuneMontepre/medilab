import { readRecord, recordRef, signIn } from "./odoo";

const ACTIONS = ".o_form_view .o_statusbar_buttons";
const REFUSAL_MESSAGES = ".o_error_dialog, .o_notification, .modal .alert";
const REFUSALS = ["odoo.exceptions.UserError", "odoo.exceptions.ValidationError", "odoo.exceptions.AccessError"];

function clickAction(name) {
  return cy.get(`${ACTIONS} button[name="${name}"]:visible`)
    .should("have.length", 1)
    .and("be.enabled")
    .click();
}

Cypress.Commands.add("signInAs", (role) => {
  expect(role, "demo role").to.match(/^[a-z][a-z0-9_]*$/);
  return signIn(`demo.${role}`);
});

Cypress.Commands.add("openRecord", (record) => {
  return recordRef(record).then((record) => {
    cy.visit(`/odoo/${record.model}/${record.id}`);
    cy.get(".o_form_view").should("be.visible");
    return cy.wrap(record, { log: false });
  });
});

Cypress.Commands.add("readRecord", readRecord);

Cypress.Commands.add("signRecord", (action = "action_sign") => clickAction(action));
Cypress.Commands.add("sendRecord", (action = "action_send") => clickAction(action));

Cypress.Commands.add("rejectRecord", (reason, {
  button = `${ACTIONS} button.btn-danger:visible`,
  reasonField = '[name="reason"] textarea',
  action = "action_reject",
} = {}) => {
  expect(reason, "rejection reason").to.be.a("string");
  expect(reason.trim(), "rejection reason").not.to.be.empty;
  cy.get(button).should("have.length", 1).and("be.enabled").click();
  cy.get(".modal:visible").last().within(() => {
    cy.get(reasonField).clear().type(reason, { parseSpecialCharSequences: false });
    cy.get(`button[name="${action}"]`).should("be.enabled").click();
  });
  return cy.get(".modal").should("not.exist");
});

Cypress.Commands.add("expectRefusal", ({
  action,
  message,
  read,
  messageSelector = REFUSAL_MESSAGES,
}) => {
  expect(action, "refused action").to.be.a("function");
  expect(read, "record snapshot reader").to.be.a("function");
  expect(message, "refusal message").to.be.a("string").and.not.be.empty;
  // Odoo shows a refusal in a dialog and also rejects the page's request; only that rejection is expected.
  const expectedRejection = (error) => !REFUSALS.includes(error.exceptionName);
  cy.on("uncaught:exception", expectedRejection);
  let snapshot;
  cy.then(read).then((before) => {
    expect(before, "record snapshot").not.to.be.oneOf([null, undefined]);
    snapshot = Cypress._.cloneDeep(before);
  });
  cy.contains(messageSelector, message).should("not.exist");
  cy.then(action);
  cy.contains(messageSelector, message).should("be.visible");
  cy.then(() => cy.removeListener("uncaught:exception", expectedRejection));
  return cy.then(read).then((after) => {
    expect(after, "record after refusal").to.deep.equal(snapshot);
  });
});
