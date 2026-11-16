import { step } from "../../../support/steps";
import { callAs, callRefused, refAs } from "../../../support/odoo";

const ADMIN = "demo.administrator";
const LAB_HEAD = "demo.lab_head";
const REPORT = "sol_demo.demo_test_report_draft";
const ISSUED = "sol_demo.demo_test_report_by_email";
const ACTIONS = ".o_form_view .o_statusbar_buttons";

// The status the online editor page answers with for a file, 503 while ONLYOFFICE is unavailable. Opening a file
// opens its editing session, so availability is asked with the tester's demo spreadsheet, whose session is open anyway.
function editorStatus(fileId) {
  return cy.request({ url: `/medilab/laboratory-files/${fileId}/edit`, failOnStatusCode: false }).its("status");
}

function editingAvailable() {
  cy.signInAs("tester");
  return callAs("demo.tester", "medilab.laboratory.file", "search_read", [[["path", "=", "2026/HPLC-ket-qua-thang-10.xlsx"]]], {
    fields: ["id"],
  }).then(([file]) => editorStatus(file.id).then((status) => status !== 503));
}

// The candidate waiting for review of the report, if any.
const waitingCandidate = (report) =>
  callAs(ADMIN, "medilab.test.report.candidate", "search_read", [[["report_id", "=", report.id], ["status", "=", "review"]]], {
    fields: ["report_number", "attachment_id", "docx_version_id", "template_version_id"],
  }).then((rows) => rows[0]);

// Opens the URL an action button opens in a new tab, in the current session.
function openedUrl(button) {
  cy.window().then((win) => cy.stub(win, "open").as("open"));
  cy.get(`${ACTIONS} button[name=${button}]`).click();
  return cy.get("@open").should("have.been.called").then((open) => open.firstCall.args[0]);
}

describe("WF-06 Report preparation", () => {
  it("TC-WF06-M2 shows the lab head the PDF MediLab prepared and lets nobody edit the draft", () => {
    refAs(ADMIN, REPORT).then((report) => {
      waitingCandidate(report).then((candidate) => {
        expect(candidate.report_number).to.match(/^PKQ\.\d{4}\.\d+$/);
        cy.signInAs("lab_head");
        cy.openRecord(report);
        cy.get(".o_form_view .alert-info").should("be.visible");
        cy.get(`${ACTIONS} button[name=action_edit_draft]`).should("not.exist");
        cy.get(`${ACTIONS} button[name=action_prepare_pdf]`).should("not.exist");
        openedUrl("action_open_candidate").then((url) => {
          expect(url).to.equal(`/web/content/${candidate.attachment_id[0]}`);
          cy.request(url).its("headers.content-type").should("contain", "application/pdf");
        });
        cy.readRecord(report, ["code", "status", "template_version_id", "draft_file_id"]).should((read) => {
          expect(read.code, "reserved number").to.equal(candidate.report_number);
          expect(read.status).to.equal("draft");
          expect(read.template_version_id[0]).to.equal(candidate.template_version_id[0]);
        });
        // The draft opens in no editor, and nobody holds an edit permission on a report.
        cy.readRecord(report, ["draft_file_id"]).then((read) => editorStatus(read.draft_file_id[0]).should("eq", 403));
        callRefused("medilab.test.report", "write", [[report.id], { language: "vi" }]).should("be.a", "string");
        callRefused("medilab.test.report", "action_edit_draft", [[report.id]]).should("be.a", "string");

        // Sample delivery staff deliver reports, but do not prepare their PDF.
        cy.signInAs("sample_delivery_staff");
        callRefused("medilab.test.report", "action_prepare_pdf", [[report.id]]).should("be.a", "string");
      });
    });
  });

  it("TC-WF06-A5 lets the lab head prepare the PDF again, which keeps the reserved number", function () {
    editingAvailable().then((available) => available || this.skip());
    refAs(ADMIN, REPORT).then((report) => {
      waitingCandidate(report).then((candidate) => {
        step("The lab head prepares the PDF again, which makes the prepared PDF obsolete");
        cy.signInAs("lab_head");
        callAs(LAB_HEAD, "medilab.test.report", "action_prepare_pdf", [[report.id]]);
        callAs(ADMIN, "medilab.test.report.candidate", "read", [[candidate.id], ["status"]]).its("0.status").should("eq", "obsolete");
        // A new PDF keeps the number reserved for the report.
        step("A new PDF keeps the number reserved for the report");
        cy.openRecord(report);
        cy.get(`${ACTIONS} button[name=action_open_candidate]`).should("be.visible");
        waitingCandidate(report).its("report_number").should("eq", candidate.report_number);
      });
    });
  });

  it("TC-WF06-E4 refuses a new PDF while ONLYOFFICE is unavailable and still serves issued PDFs", function () {
    editingAvailable().then((available) => available && this.skip());
    refAs(ADMIN, REPORT).then((report) => {
      step("Preparing a PDF is refused while ONLYOFFICE is unavailable");
      cy.signInAs("lab_head");
      cy.readRecord(report, ["code", "candidate_ids", "write_date"]).then((before) => {
        callRefused("medilab.test.report", "action_prepare_pdf", [[report.id]]).then((message) => {
          expect(message).to.contain("ONLYOFFICE");
          cy.readRecord(report, ["code", "candidate_ids", "write_date"]).should("deep.equal", before);
        });
      });

      step("The customer still downloads an issued report");
      refAs(ADMIN, ISSUED).then((issued) => {
        cy.signInAs("customer");
        cy.request(`/my/test-reports/${issued.id}/download`).its("headers.content-type").should("contain", "application/pdf");
      });
    });
  });

  it("TC-WF06-T shows the administrator the template's versions and refuses one without a preview", () => {
    refAs(ADMIN, "sol_demo.demo_report_template_bilingual").then((template) => {
      cy.signInAs("administrator");
      cy.openRecord(template);
      cy.get(".o_field_widget[name=version_ids] .o_data_row").should("have.length", 3);
      refAs(ADMIN, "sol_demo.demo_report_template_version_bilingual_3").then((draft) =>
        callRefused("medilab.report.template.version", "action_make_available", [[draft.id]]).then((message) =>
          cy.expectRefusal({
            read: () => cy.readRecord(draft, ["state", "docx_version_id", "write_date"]),
            action: () => {
              cy.get(".o_field_widget[name=version_ids] .o_data_row").first().find("button[name=action_make_available]").click();
              cy.get(".modal-footer .btn-primary").click();
            },
            message,
          }),
        ),
      );
    });
    cy.signInAs("tester");
    callRefused("medilab.report.template", "create", [{ name: "Mẫu của tôi", language: "vi" }]).should("be.a", "string");
  });
});
