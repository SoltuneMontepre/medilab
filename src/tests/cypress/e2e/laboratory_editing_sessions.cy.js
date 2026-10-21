const PASSWORD = "demo";
// The lead results of the bottled water in testing, which both testers edited online.
const SPREADSHEET = "Pb-ket-qua.xlsx";

function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

describe("Laboratory editing sessions", () => {
  it("shows a tester the sessions of the results spreadsheet their colleagues edited online", () => {
    signIn("demo.tester");
    cy.visit("/odoo/laboratory-editing-sessions");

    for (const status of ["Open", "Expired", "Committed"]) {
      cy.contains(".o_data_row", status).should("contain", SPREADSHEET);
    }
    cy.get(".o_list_button_add").should("not.exist");
  });

  it("lists the sessions on the spreadsheet's form next to the version saved online", () => {
    signIn("demo.tester");
    cy.visit("/odoo/laboratory-files");

    cy.contains(".o_data_row", SPREADSHEET).click();
    cy.contains(".o_data_row", "Edited Online").should("be.visible");
    cy.get("button.nav-link[name=editing_sessions]").click();
    cy.get(".o_field_widget[name=editing_session_ids] .o_data_row").should("have.length", 3);
  });
});
