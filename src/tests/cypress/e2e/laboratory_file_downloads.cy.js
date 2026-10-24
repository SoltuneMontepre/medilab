const PASSWORD = "demo";
// The HPLC results the tester and the chemistry tester saved from their computers; its bytes are in the bucket.
const RESULT_FILE = "HPLC-ket-qua-thang-10.xlsx";

function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

describe("Downloading laboratory file versions", () => {
  it("lets a member download a version straight from the bucket", () => {
    signIn("demo.tester");
    cy.visit("/odoo/laboratory-file-versions");
    cy.contains(".o_data_row td", RESULT_FILE).click();
    cy.get(".o_form_view").should("be.visible");
    // The download opens the presigned address of the bucket in a new tab.
    cy.window().then((win) => cy.stub(win, "open").as("open"));

    cy.get("button[name=action_download]").click();

    cy.get("@open").should("have.been.calledOnce");
    cy.get("@open")
      .its("firstCall.args.0")
      .should("match", /X-Amz-Signature=/)
      .and("contain", encodeURIComponent(RESULT_FILE));
  });
});
