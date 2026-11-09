import { pick, save } from "../../../support/form";
import { callAs, callRefused } from "../../../support/odoo";
import { LEAD_VALUE, TESTER, approvedResult, issuedReport, requestedChange, signatures, signedOrder } from "./setup";

const BUTTONS = ".o_form_view .o_statusbar_buttons";
const WITHDRAW = `${BUTTONS} button[name=action_withdraw]`;
const CHANGE = "Change the lead result from 0.008 to 0.006 mg/L.";
const REASON = "The value was copied from the wrong line of the AAS log.";
// What a change request leaves unchanged on its result until it is applied.
const RESULT_FIELDS = ["status", "version", "value", "is_replaced", "write_date"];

// Raises a change request from the open document's Request a Change dialog, filled with `change` and `reason`.
function raiseChange(change, reason) {
  cy.contains(`${BUTTONS} button`, "Request a Change").should("be.visible").click();
  cy.get(".modal:visible").within(() => {
    if (change) cy.get(".o_field_widget[name=requested_change] textarea").type(change);
    if (reason) cy.get(".o_field_widget[name=reason] textarea").type(reason);
    cy.get("button[name=action_raise]").click();
  });
}

// Raises the change request on the open document and yields it, opened as Odoo opens it after raising.
function raiseRequest(change, reason) {
  raiseChange(change, reason);
  cy.get(".modal").should("not.exist");
  cy.location("pathname").should("match", /\/medilab\.change\.request\/\d+$/);
  cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Requested");
  return cy.location("pathname").then((path) => ({ model: "medilab.change.request", id: Number(path.split("/").pop()) }));
}

// The lab head approves the open change request, the chain's only level, and confirms it.
function approveRequest() {
  cy.signRecord();
  cy.get(".modal:visible .modal-footer .btn-primary").click();
  cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Applied");
}

// The change requests raised on a document.
function changeRequests(document) {
  return callAs(
    "demo.administrator",
    "medilab.change.request",
    "search_read",
    [
      [
        ["document_model", "=", document.model],
        ["document_id", "=", document.id],
      ],
    ],
    { fields: ["status"] },
  );
}

describe("SF-03 Change request on a signed document", () => {
  it("TC-SF03-M replaces a completed result by a new version once the chain signs the tester's change request", () => {
    approvedResult().then((result) => {
      cy.signInAs("tester");
      cy.openRecord(result);
      cy.get(WITHDRAW).should("not.exist");
      raiseRequest(CHANGE, REASON).then((request) => {
        cy.get(".o_field_widget[name=requested_change]").should("contain", CHANGE);
        cy.get(".o_field_widget[name=reason]").should("contain", REASON);

        cy.signInAs("lab_head");
        cy.openRecord(request);
        approveRequest();
        cy.readRecord(request, ["status", "new_document_id"]).then(({ status, new_document_id: version }) => {
          expect(status).to.equal("applied");
          cy.contains(`${BUTTONS} button`, "Open New Version").click();
          cy.location("pathname").should("contain", `/medilab.test.result/${version}`);
          cy.get(".o_field_widget[name=version]").should("have.text", "2");
          cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Draft");
          cy.readRecord({ model: "medilab.test.result", id: version }, ["replaces_id", "status", "is_reported"]).should((read) => {
            expect(read.replaces_id[0], "replaces").to.equal(result.id);
            expect(read.status).to.equal("none");
            expect(read.is_reported, "reported in place of the old version").to.be.true;
          });
        });

        // The replaced version keeps its signed value and stays readable.
        cy.signInAs("tester");
        cy.openRecord(result);
        cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Approved");
        cy.get(".o_field_widget[name=is_replaced] input").should("be.checked");
        cy.contains(`${BUTTONS} button`, "Request a Change").should("not.exist");
        cy.readRecord(result, ["status", "version", "value", "is_replaced"]).should((read) => {
          expect(read).to.deep.equal({ id: result.id, status: "approved", version: 1, value: LEAD_VALUE, is_replaced: true });
        });
      });
    });
  });

  it("TC-SF03-A1 creates a new version of an issued report once the lab head approves its change request", () => {
    issuedReport().then((report) => {
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(report);
      raiseRequest("Reissue the report with the customer's new registered name.", "The customer changed its business registration.").then(
        (request) => {
          cy.signInAs("lab_head");
          cy.openRecord(request);
          approveRequest();
          cy.readRecord(request, ["new_document_id"]).then(({ new_document_id: version }) => {
            cy.contains(`${BUTTONS} button`, "Open New Version").click();
            cy.location("pathname").should("contain", `/medilab.test.report/${version}`);
            cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Draft");
            cy.readRecord({ model: "medilab.test.report", id: version }, ["replaces_id", "version", "status", "code"]).should((read) => {
              expect(read.replaces_id[0], "replaces").to.equal(report.id);
              expect(read.version).to.equal(2);
              expect(read.status).to.equal("draft");
              expect(read.code, "numbered when issued").to.be.false;
            });
          });
          // The issued version keeps its number and its PDF.
          cy.readRecord(report, ["code", "version", "attachment_id"]).should((read) => {
            expect(read.code).to.equal(report.code);
            expect(read.version).to.equal(1);
            expect(read.attachment_id, "PDF").to.be.an("array");
          });
        },
      );
    });
  });

  it("TC-SF03-A2 keeps the signed result unchanged and the reason when the chain rejects the change request", () => {
    const reason = "The AAS log shows 0.008 mg/L on the line of this sample, so the measured value stands.";
    approvedResult().then((result) => {
      callAs(TESTER, "medilab.test.result", "read", [[result.id], RESULT_FIELDS]).then(([before]) => {
        requestedChange(result, CHANGE, REASON).then((request) => {
          cy.signInAs("lab_head");
          cy.openRecord(request);
          cy.rejectRecord(reason);
          cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Rejected");
          cy.get(".o_field_widget[name=rejection_reason]").should("contain", reason);
          cy.get(`${BUTTONS} button[name=action_sign]`).should("not.exist");
          cy.readRecord(request, ["status", "rejection_reason", "new_document_id"]).should((read) => {
            expect(read.status).to.equal("rejected");
            expect(read.rejection_reason).to.equal(reason);
            expect(read.new_document_id, "new version").to.equal(0);
          });
          callAs(TESTER, "medilab.test.result", "read", [[result.id], RESULT_FIELDS])
            .its("0")
            .should("deep.equal", before);
          callAs(TESTER, "medilab.test.result", "search", [[["replaces_id", "=", result.id]]]).should("be.empty");
        });
      });
    });
  });

  it("TC-SF03-A3 lets signers withdraw from the top level down before the process is completed, which reopens the document", () => {
    signedOrder().then((order) => {
      cy.signInAs("lab_head");
      cy.openRecord(order);
      cy.get(WITHDRAW).click();
      cy.get(WITHDRAW).should("not.exist");
      cy.readRecord(order, ["approval_status"]).its("approval_status").should("eq", "requested");

      cy.signInAs("storekeeper");
      cy.openRecord(order);
      cy.get(WITHDRAW).click();
      cy.get(WITHDRAW).should("not.exist");
      cy.readRecord(order, ["approval_status", "document_version"]).should("deep.equal", {
        id: order.id,
        approval_status: "none",
        document_version: 2,
      });
      signatures(order).should((rows) => {
        expect(rows.map((row) => row.level_name)).to.deep.equal(["Storekeeper", "Lab head"]);
        rows.forEach((row) => expect(row.withdrawn_at, `${row.level_name} withdrawn`).to.be.a("string"));
      });

      // What the signers approved can be edited again.
      pick("department_id", "Microbiology");
      save();
      cy.readRecord(order, ["department_id"]).its("department_id.1").should("eq", "Microbiology");
    });
  });

  it("TC-SF03-E1 refuses a change request without what to change or why", () => {
    approvedResult().then((result) => {
      const read = () =>
        changeRequests(result).then((requests) =>
          callAs(TESTER, "medilab.test.result", "read", [[result.id], RESULT_FIELDS]).then(([read]) => ({ requests, result: read })),
        );
      cy.signInAs("tester");
      cy.openRecord(result);
      cy.expectRefusal({
        read,
        action: () => raiseChange(CHANGE, ""),
        message: "Missing required fields",
      });
      cy.get(".modal:visible .o_field_widget[name=reason]").should("have.class", "o_field_invalid");
      cy.get(".modal:visible .modal-footer button.btn-secondary").click();

      cy.expectRefusal({
        read,
        action: () => raiseChange(" ", REASON),
        message: "Say what to change and why.",
      });
      read().its("requests").should("be.empty");
    });
  });

  it("TC-SF03-E2 refuses withdrawing a signature while a later one stands, or once the process is completed", () => {
    signedOrder().then((order) => {
      cy.signInAs("storekeeper");
      cy.openRecord(order);
      cy.get(WITHDRAW).should("not.exist");
      signatures(order).then((before) => {
        callRefused("purchase.order", "action_withdraw", [[order.id]]).should("eq", "Withdraw the signatures given after yours first.");
        signatures(order).should("deep.equal", before);
      });
    });

    approvedResult().then((result) => {
      cy.signInAs("head_of_department");
      cy.openRecord(result);
      cy.get(WITHDRAW).should("not.exist");
      signatures(result).then((before) => {
        callRefused("medilab.test.result", "action_withdraw", [[result.id]]).should(
          "eq",
          "The process of the document is completed, so a signature cannot be withdrawn.",
        );
        signatures(result).should("deep.equal", before);
        cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
      });
    });
  });
});
