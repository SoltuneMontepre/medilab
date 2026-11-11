import { callAs, callRefused, refAs } from "../../../support/odoo";

const ADMIN = "demo.administrator";
const STAFF = "demo.sample_delivery_staff";
const LAB_HEAD = "demo.lab_head";
const REPORT = "medilab.test.report";
const ACTIONS = ".o_form_view .o_statusbar_buttons";

// The report's prepared PDF that waits for signature or was issued.
const signedCandidate = (report) =>
  callAs(ADMIN, "medilab.test.report.candidate", "search_read", [[["report_id", "=", report.id], ["status", "in", ["review", "issued"]]]], {
    fields: ["status", "report_number", "attachment_id"],
  }).then((rows) => rows[0]);

// The record's fields as the administrator reads them.
const readAs = (record, fields) => callAs(ADMIN, record.model, "read", [[record.id], fields]).its(0);

// The base64 content of a file the browser's session downloads.
const downloaded = (url) => cy.request({ url, encoding: "base64" }).its("body");

// The rows of a list of the Laboratory menu, by its path.
function listRows(path) {
  cy.visit(`/odoo/${path}`);
  return cy.get(".o_list_view").should("be.visible").find(".o_data_row, .o_view_nocontent").should("exist");
}

// The replacement of a report, made through a change request the lab head approves when it has none yet.
function replacementOf(report) {
  const replacements = () => callAs(ADMIN, REPORT, "search_read", [[["replaces_id", "=", report.id]]], { fields: ["status"] });
  return replacements().then((rows) => {
    if (rows.length) return rows[0];
    return callAs(STAFF, "medilab.change.request.raise", "create", [
      {
        document_model: REPORT,
        document_id: report.id,
        requested_change: "Phát hành lại phiếu với địa chỉ nhận mới của khách hàng.",
        reason: "Khách hàng đã đổi địa chỉ nhận phiếu.",
      },
    ]).then((wizard) =>
      callAs(STAFF, "medilab.change.request.raise", "action_raise", [[wizard]]).then((action) => {
        cy.signInAs("lab_head");
        cy.openRecord({ model: "medilab.change.request", id: action.res_id });
        cy.signRecord();
        cy.get(".modal-footer .btn-primary").click();
        cy.get(`${ACTIONS} button[name=action_open_new_version]`).should("be.visible");
        return replacements().then((rows) => rows[0]);
      }),
    );
  });
}

describe("WF-06 Report release", () => {
  it("TC-WF06-E1 keeps a report pending digital signing unissued, then issues its reviewed PDF once on retry", () => {
    refAs(ADMIN, "sol_demo.demo_test_report_pending").then((report) =>
      signedCandidate(report).then((candidate) => {
        readAs(report, ["status", "code", "attachment_id", "request_id"]).then((read) => {
          expect(read.status).to.equal("pending_signing");
          expect(read.code).to.equal(candidate.report_number);
          expect(read.attachment_id).to.equal(false);

          cy.signInAs("sample_delivery_staff");
          listRows("reports-to-deliver").should("not.contain.text", read.code);
          callRefused(REPORT, "action_record_delivery", [[report.id]]).should("be.a", "string");
          cy.signInAs("customer");
          cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false }).its("status").should("eq", 404);

          cy.signInAs("lab_head");
          listRows("reports-to-sign").should("not.contain.text", read.request_id[1]);
          cy.openRecord(report);
          cy.get(".o_form_view .alert-warning").should("contain.text", "Viettel Sign");
          cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
          // Digital signing is off in the demo, so the retry issues the reviewed PDF as it is.
          cy.get(`${ACTIONS} button[name=action_retry_digital_signing]`).click();
          cy.get(`${ACTIONS} button[name=action_retry_digital_signing]`).should("not.exist");
          cy.get(`${ACTIONS} button[name=action_download]`).should("be.visible");
        });
        readAs(report, ["status", "code"]).should((read) => {
          expect(read.status).to.equal("issued");
          expect(read.code).to.equal(candidate.report_number);
        });
        signedCandidate(report).its("status").should("eq", "issued");
        callRefused(REPORT, "action_retry_digital_signing", [[report.id]]).should("be.a", "string");
        downloaded(`/web/content/${candidate.attachment_id[0]}`).then((reviewed) => {
          cy.signInAs("customer");
          downloaded(`/my/test-reports/${report.id}/download`).should("eq", reviewed);
        });
      }),
    );
  });

  it("TC-WF06-E1 keeps the issued report current until its replacement is issued", () => {
    refAs(ADMIN, "sol_demo.demo_test_report_in_person").then((replaced) =>
      refAs(ADMIN, "sol_demo.demo_test_report_reissued").then((reissued) => {
        readAs(replaced, ["status"]).its("status").should("eq", "replaced");
        readAs(reissued, ["status", "replaces_id"]).should((read) => {
          expect(read.status).to.equal("issued");
          expect(read.replaces_id[0]).to.equal(replaced.id);
        });
      }),
    );
    refAs(ADMIN, "sol_demo.demo_test_report_by_email").then((report) =>
      replacementOf(report).then((replacement) => {
        expect(replacement.status).to.equal("draft");
        readAs(report, ["status", "request_id"]).then((read) => {
          expect(read.status).to.equal("issued");
          cy.signInAs("lab_head");
          listRows("reports-to-sign").should("contain.text", read.request_id[1]);
        });
        // The replacement waits for its own prepared PDF before the lab head can sign it.
        callAs(LAB_HEAD, REPORT, "read", [[replacement.id], ["approval_can_sign"]]).its("0.approval_can_sign").should("eq", false);
        cy.signInAs("customer");
        cy.request(`/my/test-reports/${report.id}/download`).its("headers.content-type").should("contain", "application/pdf");
        cy.request({ url: `/my/test-reports/${replacement.id}/download`, failOnStatusCode: false }).its("status").should("eq", 404);
      }),
    );
  });
});
