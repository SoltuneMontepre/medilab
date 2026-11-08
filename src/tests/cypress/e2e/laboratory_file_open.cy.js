import { call, signIn } from "../support/odoo";

// The HPLC results spreadsheet and the CSV run the tester saved from their computer.
const OFFICE_FILE = "HPLC-ket-qua-thang-10.xlsx";
const CSV_FILE = "run-0412.csv";
const FOLDER = "Kết quả HPLC";

function fileId(name) {
  return call("medilab.laboratory.file", "search_read", [[["path", "like", name]], ["id"]]).then(([file]) => {
    expect(file, name).to.exist;
    return file.id;
  });
}

describe("Opening laboratory files from the back office", () => {
  beforeEach(() => {
    signIn("demo.tester");
  });

  it("opens an Office file of the Files list in the online editor, in a new tab the browser allows", () => {
    fileId(OFFICE_FILE).then((id) => {
      cy.visit("/odoo/laboratory-files");
      // The spy calls through, so a blocked popup shows as the null that window.open then returns.
      cy.window().then((win) => cy.spy(win, "open").as("open"));

      cy.contains(".o_data_row td", OFFICE_FILE).click();

      cy.get("@open").should("have.been.calledOnce");
      cy.get("@open").its("firstCall.args.0").should("contain", `/medilab/laboratory-files/${id}/edit`);
      cy.get("@open").its("firstCall.args.1").should("eq", "_blank");
      cy.get("@open").its("firstCall.returnValue").should("not.be.null");
      cy.get(".o_form_view").should("not.exist");
    });
  });

  it("opens the form of a file that is not edited online", () => {
    cy.visit("/odoo/laboratory-files");
    cy.window().then((win) => cy.spy(win, "open").as("open"));

    cy.contains(".o_data_row td", CSV_FILE).click();

    cy.get(".o_form_view").should("be.visible");
    cy.get("@open").should("not.have.been.called");
  });

  it("keeps the form for a file of the Files tab of a folder", () => {
    cy.visit("/odoo/laboratory-folders");
    cy.contains(".o_data_row td", FOLDER).click();
    cy.contains(".nav-link", "Files").click();
    cy.window().then((win) => cy.spy(win, "open").as("open"));

    cy.contains(".o_field_one2many .o_data_row td", OFFICE_FILE).click();

    cy.get(".o_form_view").should("be.visible");
    cy.get("@open").should("not.have.been.called");
  });
});
