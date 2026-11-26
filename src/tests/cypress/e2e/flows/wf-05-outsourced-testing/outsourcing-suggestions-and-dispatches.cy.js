import { save } from "../../../support/form";
import { PORTAL_MENU } from "../../../support/menus";
import { step } from "../../../support/steps";
import { CUSTOMERS, clearCarts } from "../wf-01-order-to-test-request/setup";
import { call, callRefused, refAs } from "../../../support/odoo";
import {
  ACTIONS,
  ADMINISTRATOR,
  PARAMETERS,
  assignedTest,
  clearDrafts,
  openOutsource,
  receivedDispatch,
  sentDispatch,
  subcontractorResult,
} from "./setup";

const REPORT = "PKQ-NTL-2026-0412.pdf";

describe("F-38 Outsourcing suggestions, urgent outsourcing and dispatches", () => {
  it("TC-F38-01 lets the head attach the subcontractor's report to a received dispatch → staff carrying it and the subcontractor never read it", () => {
    sentDispatch().then(({ dispatch }) => {
      step("The head of department records the receipt and attaches the subcontractor's report");
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.sendRecord("action_receive");
      cy.get(`${ACTIONS} button[name=action_receive]`).should("not.exist");
      cy.get(".o_field_widget[name=report_file] input[type=file]").selectFile(
        { contents: Cypress.Buffer.from("%PDF-1.4 Northern Testing report"), fileName: REPORT, mimeType: "application/pdf" },
        { force: true },
      );
      cy.get(".o_field_widget[name=report_file] input:not([type=file])").should("have.value", REPORT);
      save();
      cy.readRecord(dispatch, ["status", "report_filename"]).should((read) => {
        expect(read.status).to.equal("received");
        expect(read.report_filename).to.equal(REPORT);
      });

      // The sample delivery staff still read the dispatch they carried, without its report.
      step("Staff who carried the dispatch still read it, but not its report");
      cy.signInAs("sample_delivery_staff");
      call("medilab.subcontract.dispatch", "read", [[dispatch.id], ["code"]])
        .its("0.code")
        .should("eq", dispatch.code);
      callRefused("medilab.subcontract.dispatch", "read", [[dispatch.id], ["report_file"]]).should("match", /not allowed|access/i);

      step("The subcontractor does not see the report");
      cy.signInAs("subcontractor");
      cy.visit(`/my/dispatches/${dispatch.id}`);
      cy.get("main").should("contain", dispatch.code).and("not.contain", REPORT);
    });
  });

  it("TC-F38-01 prints a dispatch with its sample tests and never the customer", () => {
    sentDispatch().then(({ test, dispatch }) => {
      step("The head of department prints the dispatch");
      cy.signInAs("head_of_department");
      cy.request(`/report/html/sol_laboratory.report_subcontract_dispatch/${dispatch.id}`).then(({ body }) => {
        expect(body).to.contain(dispatch.code);
        expect(body).to.contain(test.code);
        expect(body).to.contain("ISO 17294-2:2016");
        expect(body).not.to.contain(test.customerName);
      });
    });
  });

  it("TC-F38-02 lets the head outsource a test accepted in-house to a subcontractor with the same method, without the customer", () => {
    clearDrafts();
    assignedTest("lead", { days: 30, accepted: PARAMETERS.lead.sameMethod }).then((test) => {
      // No in-house machine runs ICP-MS in time, so the scheduler suggests outsourcing it.
      step("The head of department accepts the suggestion for a test the customer accepted in-house by ICP-MS");
      cy.signInAs("head_of_department");
      cy.readRecord(test, ["outsourcing_suggested"]).its("outsourcing_suggested").should("eq", true);
      cy.openRecord(test);
      cy.get(".o_form_view").should("not.contain", "needs a revised quotation");
      openOutsource().within(() => {
        cy.get(".o_field_widget[name=parameter_method_id] input")
          .invoke("val")
          .should("match", /^Lead \(Pb\) – ISO 17294-2:2016 \(.+\)$/);
        cy.get("button[name=action_outsource]").click();
      });
      step("Northern tests it, and the customer's accepted way stays");
      cy.location("pathname").should("match", /medilab\.subcontract\.dispatch\/\d+$/);
      refAs(ADMINISTRATOR, PARAMETERS.lead.way).then((northern) =>
        refAs(ADMINISTRATOR, PARAMETERS.lead.sameMethod).then((accepted) =>
          cy.readRecord(test, ["status", "parameter_method_id", "accepted_method_id"]).should((read) => {
            expect(read.status).to.equal("outsourced");
            expect(read.parameter_method_id[0]).to.equal(northern.id);
            expect(read.accepted_method_id[0]).to.equal(accepted.id);
          }),
        ),
      );
    });
  });

  it("TC-F38-02 offers the customer each method once in the cart, never naming the subcontractor", () => {
    clearCarts(CUSTOMERS.nuocSach);
    step("The customer chooses bottled water for lead, which Chemistry and Northern both test by ICP-MS");
    cy.signInAs("customer");
    cy.get(`${PORTAL_MENU} a[href='/catalog']`).click();
    cy.contains("tr", "Lead (Pb)").find("button[type=submit]").click();
    cy.location("pathname").should("eq", "/cart");
    cy.get("select[name=sample_type_id]")
      .first()
      .find("option")
      .contains(/Nước đóng chai|Bottled water/)
      .invoke("val")
      .then((value) => cy.get("select[name=sample_type_id]").first().select(String(value)));
    step("Each method is offered once, and no way names who tests it");
    cy.get("select[name=parameter_method_id]")
      .first()
      .find("option[value!='']")
      .then((options) => {
        const names = [...options].map((option) => option.textContent.trim());
        expect(names).to.have.members(["Lead (Pb) – TCVN 7602:2007", "Lead (Pb) – ISO 17294-2:2016"]);
      });
    cy.get("main").should("not.contain", "Northern");
  });

  it("TC-F38-03 refuses to cancel a dispatch whose tests have results", () => {
    receivedDispatch().then((sent) => {
      step("The subcontractor enters a result");
      subcontractorResult(sent);
      step("The head sees no cancel action, and cancelling through RPC is refused");
      cy.signInAs("head_of_department");
      cy.openRecord(sent.dispatch);
      cy.get(`${ACTIONS} button[name=action_cancel]`).should("not.exist");
      callRefused("medilab.subcontract.dispatch", "action_cancel", [[sent.dispatch.id]]).should(
        "match",
        /Only a draft or sent dispatch can be cancelled/,
      );
      cy.readRecord(sent.dispatch, ["status"]).its("status").should("eq", "received");
    });
  });
});
