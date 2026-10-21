const PASSWORD = "demo";
// The lead results of the bottled water in testing: version 1 is signed by the head of chemistry, version 2 is newer.
const RESULT_FILE = "Pb-ket-qua.xlsx";

function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

function openCurrentResultVersion() {
  cy.visit("/odoo/laboratory-file-versions");
  // Versions are listed newest first, so the first row of the file is its current version.
  cy.contains(".o_data_row td", RESULT_FILE).click();
  cy.get(".o_form_view").should("be.visible");
}

describe("Sample folders and signing file versions", () => {
  it("lets the head of department create the folders of a sample they test", () => {
    signIn("demo.head_of_department");
    cy.visit("/odoo/samples");

    cy.contains(".o_data_row", "Received").click();
    cy.get("button[name=action_create_laboratory_folders]").click();

    cy.get(".o_data_row").should("have.length", 2);
    cy.contains(".o_data_row", "Raw Data").should("be.visible");
    cy.contains(".o_data_row", "Results").should("be.visible");
  });

  it("lets the head of department sign the current version of a result file", () => {
    signIn("demo.head_of_department");
    cy.visit("/odoo/laboratory-files");
    cy.contains(".o_data_row", RESULT_FILE).should("contain", "Not Signed");

    openCurrentResultVersion();
    cy.get("button[name=action_sign]").click();
    cy.get(".modal-footer .btn-primary").click();

    cy.get(".o_form_view .o_field_badge").should("contain", "Signed");
    cy.get("button[name=action_sign]").should("not.exist");
    cy.get("button[name=action_withdraw]").should("be.visible");
  });

  it("does not let a tester sign a result version", () => {
    signIn("demo.chemistry_tester");

    openCurrentResultVersion();

    cy.get("button[name=action_sign]").should("not.exist");
    cy.get(".o_form_view").should("not.contain", "Signatures");
  });
});
