import { call } from "../../../../support/odoo";

const WARNING = "Each test request created from an order keeps the order's number as text.";

function openUninstallDialog(module) {
  call("ir.module.module", "search", [[["name", "=", module]]]).then(([id]) => {
    cy.visit(`/odoo/action-base.open_module_tree/${id}`);
  });
  cy.get(".o_form_view button[name='button_uninstall_wizard']:visible").click();
  return cy.get(".modal:visible").should("contain.text", "This will remove");
}

describe("Uninstall warning", () => {
  beforeEach(() => {
    cy.signInAs("administrator");
  });

  it("warns that test requests keep their order's number before uninstalling E-commerce", () => {
    openUninstallDialog("sol_commerce").within(() => {
      cy.get(".alert-warning").should("be.visible").and("contain.text", WARNING);
      cy.get("button[special='cancel']").click();
    });
    cy.get(".modal").should("not.exist");
  });

  it("does not show the warning when Laboratory leaves with E-commerce", () => {
    openUninstallDialog("sol_laboratory").within(() => {
      cy.contains(WARNING).should("not.exist");
      cy.get("button[special='cancel']").click();
    });
  });
});
