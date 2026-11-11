const PASSWORD = "demo";

function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

function confirmDialog() {
  cy.get(".modal-footer .btn-primary").click();
}

describe("Laboratory folders", () => {
  it("lets an administrator turn a folder off and on again", () => {
    signIn("demo.administrator");
    cy.visit("/odoo/laboratory-folders");

    cy.contains(".o_data_row", "Kết quả HPLC").click();
    cy.get("button[name=action_turn_off]").click();
    confirmDialog();
    cy.get("button[name=action_turn_on]").should("be.visible").click();

    cy.get("button[name=action_turn_off]").should("be.visible");
  });

  it("lets an administrator revoke a computer that is still signed in", () => {
    signIn("demo.administrator");
    cy.visit("/odoo/laboratory-devices");

    cy.contains(".o_data_row", "LAPTOP-HUNG").find("button[name=action_revoke]").should("not.exist");
    cy.contains(".o_data_row", "PC-HPLC-01").find("button[name=action_revoke]").should("be.visible");
  });

  it("shows a tester only the folders they are a member of, without the administrator's actions", () => {
    signIn("demo.tester");
    cy.visit("/odoo/laboratory-folders");

    cy.contains(".o_data_row", "AAS-01 dữ liệu thô").should("not.exist");
    cy.contains(".o_data_row", "Kết quả HPLC").click();
    cy.get(".o_form_view").should("be.visible");

    cy.get("button[name=action_turn_off]").should("not.exist");
    cy.get("button[name=action_archive_folder]").should("not.exist");
  });
});
