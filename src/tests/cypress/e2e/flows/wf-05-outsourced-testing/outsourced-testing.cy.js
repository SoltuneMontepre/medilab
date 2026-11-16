import { newRecord, openMenu, openRow, pick, save } from "../../../support/form";
import { MENU } from "../../../support/menus";
import { step } from "../../../support/steps";
import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import { ADMINISTRATOR, PARAMETERS, TESTER, assignedTest, clearDrafts, inDays, outsourceDialog, outsourcedTest, reportedResult, resultAwaitingApproval, sentDispatch, shownDate, subcontractorResult, suggestedTest } from "./setup";

const REASON = "Máy AAS đang sửa, khách hàng cần kết quả chì trước hạn.";
const TRACKING = "Viettel Post, VTP 8402 1157 2210";
const REPORT = "PKQ-NTL-2026-0412.pdf";

const DISPATCH_FIELDS = ["status", "sample_test_ids", "write_date"];
const ACTIONS = ".o_form_view .o_statusbar_buttons";

// A date as an English list shows it, such as "Nov 4"; another year follows it.
function listedDate(date) {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

// Opens the outsource dialog of the sample test form shown.
function openOutsource() {
  cy.contains(`${ACTIONS} button:visible`, "Outsource").click();
  return cy.get(".modal:visible");
}

describe("WF-05 Outsourced testing", () => {
  it("TC-WF05-M lets the head accept a suggestion, staff carry the dispatch, the subcontractor enter the result and the head approve it", () => {
    const expected = inDays(7);
    clearDrafts();
    suggestedTest().then((test) => {
      step("The head of department outsources the suggested test");
      cy.signInAs("head_of_department");
      // The list shows the newest samples first, and its search looks up parameters, not sample codes.
      openMenu(MENU.laboratory, MENU.schedule, MENU.outsourcingSuggestions);
      cy.contains(".o_data_row", test.code).contains("button", "Outsource").click();
      cy.get(".modal:visible").within(() => {
        cy.get("[name=reason]").should("not.exist");
        cy.get("button[name=action_outsource]").click();
      });
      cy.location("pathname").should("match", /medilab\.subcontract\.dispatch\/\d+$/);
      cy.contains(".o_field_widget[name=sample_test_ids] .o_data_row", test.code).should("be.visible");
      step("The head sets the expected date and the courier, and sends the dispatch");
      cy.get(".o_field_widget[name=expected_date] input").clear().type(shownDate(expected));
      // Only people holding the sample delivery staff role named in the settings take a dispatch.
      cy.location("pathname").then((path) =>
        refAs(ADMINISTRATOR, "sol_demo.demo_person_tester").then((tester) =>
          refAs(ADMINISTRATOR, "sol_demo.demo_person_sample_delivery_staff").then((courier) =>
            cy
              .readRecord({ model: "medilab.subcontract.dispatch", id: Number(path.split("/").pop()) }, ["courier_choice_ids"])
              .its("courier_choice_ids")
              .should("include", courier.id)
              .and("not.include", tester.id),
          ),
        ),
      );
      pick("courier_id", "Vo Van Tai");
      cy.sendRecord("action_send");
      cy.get(`${ACTIONS} button[name=action_receive]:visible`).should("exist");
      cy.location("pathname").then((path) => {
        const dispatch = { model: "medilab.subcontract.dispatch", id: Number(path.split("/").pop()) };
        cy.readRecord(dispatch, ["code", "status", "expected_date", "courier_id"]).then((read) => {
          expect(read.status).to.equal("sent");
          expect(read.expected_date).to.equal(expected);
          expect(read.courier_id[1]).to.equal("Vo Van Tai");
          cy.readRecord(test, ["status"]).its("status").should("eq", "outsourced");
          step("The dispatch shows in the outsourcing schedule");
          openMenu(MENU.laboratory, MENU.schedule, MENU.outsourcingSchedule);
          cy.get(".o_switch_view.o_list").click();
          cy.contains(".o_data_row", read.code).find("td[name=expected_date]").should("contain", listedDate(expected));

          step("Sample delivery staff find the dispatch to carry");
          cy.signInAs("sample_delivery_staff");
          openMenu(MENU.laboratory, MENU.schedule, MENU.dispatchesToCarry);
          cy.contains(".o_data_row", read.code).should("be.visible");

          step("The subcontractor enters the result on the portal");
          cy.signInAs("subcontractor");
          cy.get("a[href='/my/dispatches']:visible").first().click();
          cy.contains("a", read.code).click();
          // A negative concentration is refused with the system's message, which the address never carries.
          cy.contains("tr", test.code).within(() => {
            cy.get("input[name=value]").type("-1");
            cy.get("button[type=submit]").click();
          });
          cy.get(".alert-danger").should("contain", "cannot be negative");
          cy.location("search").should("not.contain", "error");
          cy.reload();
          cy.get(".alert-danger").should("not.exist");
          cy.contains("tr", test.code).within(() => {
            cy.get("input[name=value]").type("4.6");
            cy.get("button[type=submit]").click();
          });
          cy.contains("tr", test.code).should("contain", "4.6").and("contain", "Entered by");
        });
        reportedResult(test).then((result) => {
          expect(result.entered_by_id[1]).to.equal("Nguyen Thi Lan");
          step("The tester sends the subcontractor's result for approval");
          cy.signInAs("tester");
          // The subcontractor's result waiting to be sent comes before any other.
          openMenu(MENU.laboratory, MENU.samples, MENU.sampleTests);
          openRow(test.code);
          cy.get(`${ACTIONS} button[name=action_enter_result]`).should("not.exist");
          openMenu(MENU.laboratory, MENU.results, MENU.testResults);
          openRow(test.code);
          cy.signRecord();
          cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
          cy.readRecord(result, ["status"]).its("status").should("eq", "requested");
          step("The head of department approves the result");
          cy.signInAs("head_of_department");
          openMenu(MENU.laboratory, MENU.results, MENU.testResults);
          openRow(test.code);
          cy.signRecord();
          cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
          cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
          cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
        });
      });
    });
  });

  it("TC-WF05-A1 sends a dispatch by a delivery service with its tracking number", () => {
    outsourcedTest().then(({ dispatch }) => {
      step("The head of department sets the expected date and the delivery service's tracking number");
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.get(".o_field_widget[name=expected_date] input")
        .clear()
        .type(shownDate(inDays(10)));
      cy.get(".o_field_widget[name=delivery_service] input").type(TRACKING);
      step("The head sends the dispatch, which has no courier");
      cy.sendRecord("action_send");
      cy.get(`${ACTIONS} button[name=action_receive]:visible`).should("exist");
      cy.readRecord(dispatch, ["status", "courier_id", "delivery_service"]).should((read) => {
        expect(read.status).to.equal("sent");
        expect(read.courier_id).to.equal(false);
        expect(read.delivery_service).to.equal(TRACKING);
      });
    });
  });

  it("TC-WF05-A2 lets a lab QA enter the result the subcontractor sent back", () => {
    sentDispatch().then(({ test, dispatch }) => {
      step("The head of department records that the subcontractor received the samples");
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.get(`${ACTIONS} button[name=action_receive]:visible`).click();
      cy.get(`${ACTIONS} button[name=action_receive]`).should("not.exist");
      cy.readRecord(dispatch, ["status"]).its("status").should("eq", "received");

      step("A lab QA enters the result the subcontractor sent back and sends it for approval");
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.get(`${ACTIONS} button[name=action_enter_result]:visible`).click();
      cy.get(".o_field_widget[name=value] input").clear().type("3.8");
      save();
      cy.get(`${ACTIONS} button[name=action_sign]:visible`).click();
      cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
      reportedResult(test).should((result) => {
        expect(result.entered_by_id[1]).to.equal("Dang Thi Lan");
        expect(result.status).to.equal("requested");
      });
      cy.readRecord(test, ["status"]).its("status").should("eq", "result_entered");
    });
  });

  it("TC-WF05-A3 lets the head outsource a test straight away in an emergency, with a reason", () => {
    clearDrafts();
    assignedTest("lead", { days: 30 }).then((test) => {
      step("The head of department outsources a test that has no suggestion, with a reason");
      cy.signInAs("head_of_department");
      cy.readRecord(test, ["outsourcing_suggested"]).its("outsourcing_suggested").should("eq", false);
      cy.openRecord(test);
      openOutsource().within(() => {
        cy.get("[name=reason] textarea").type(REASON);
        cy.get("button[name=action_outsource]").click();
      });
      step("The test is outsourced in a new dispatch");
      cy.location("pathname").should("match", /medilab\.subcontract\.dispatch\/\d+$/);
      cy.contains(".o_field_widget[name=sample_test_ids] .o_data_row", test.code).should("be.visible");
      cy.readRecord(test, ["status", "emergency_outsource_reason", "dispatch_ids"]).should((read) => {
        expect(read.status).to.equal("outsourced");
        expect(read.emergency_outsource_reason).to.equal(REASON);
        expect(read.dispatch_ids).to.have.length(1);
      });
      // Results of an outsourced test are entered once its dispatch is sent.
      step("No result is entered before the dispatch is sent");
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.get(`${ACTIONS} button[name=action_enter_result]`).should("not.exist");
    });
  });

  it("TC-WF05-A4 lets the head reject the subcontractor's result, and the subcontractor enter a new one", () => {
    const reason = "Kết quả vượt ngưỡng phát hiện của phương pháp, đề nghị đo lại.";
    resultAwaitingApproval().then(({ test, dispatch, result }) => {
      step("The head of department rejects the subcontractor's result with a reason");
      cy.signInAs("head_of_department");
      cy.openRecord(result);
      cy.rejectRecord(reason);
      cy.readRecord(result, ["status"]).its("status").should("eq", "rejected");
      cy.readRecord(test, ["status"]).its("status").should("eq", "outsourced");

      step("The subcontractor sees the rejection and enters a new result");
      cy.signInAs("subcontractor");
      cy.visit(`/my/dispatches/${dispatch.id}`);
      cy.contains("tr", test.code).should("contain", "Rejected: 4.2").and("contain", reason);
      cy.contains("tr", test.code).within(() => {
        cy.get("input[name=value]").type("4.4");
        cy.get("button[type=submit]").click();
      });
      cy.contains("tr", test.code).should("contain", "4.4");
      reportedResult(test).should((reported) => {
        expect(reported.id).not.to.equal(result.id);
        expect(reported.status).to.equal("none");
      });
    });
  });

  it("TC-WF05-A5 cancels a dispatch before any result, and its test goes in another dispatch", () => {
    sentDispatch().then(({ test, dispatch }) => {
      step("The head of department cancels a dispatch that has no result");
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.get(`${ACTIONS} button[name=action_cancel]:visible`).click();
      cy.get(".modal:visible .modal-footer .btn-primary").click();
      cy.get(`${ACTIONS} button[name=action_cancel]`).should("not.exist");
      cy.readRecord(dispatch, ["status"]).its("status").should("eq", "cancelled");
      cy.readRecord(test, ["status"]).its("status").should("eq", "outsourced");

      step("The head puts the still outsourced test in a new dispatch");
      newRecord("/odoo/subcontract-dispatches");
      pick("subcontractor_id", "Northern");
      cy.get(".o_field_widget[name=sample_test_ids] .o_field_x2many_list_row_add button").click();
      cy.get(".modal:visible").within(() => {
        cy.get(".o_searchview_input").type(`${test.code}{enter}`);
        cy.contains(".o_data_row", test.code).find(".o_list_record_selector input").check();
        cy.contains("button", "Select").click();
      });
      cy.contains(".o_field_widget[name=sample_test_ids] .o_data_row", test.code).should("be.visible");
      save();
      cy.readRecord(test, ["dispatch_ids"]).its("dispatch_ids").should("have.length", 2);
    });
  });

  // Generated by Cypress Author on 2026-11-08.
  it("TC-WF05-A6 lets the head attach the subcontractor's report to a received dispatch → staff carrying it and the subcontractor never read it", () => {
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
      call("medilab.subcontract.dispatch", "read", [[dispatch.id], ["code"]]).its("0.code").should("eq", dispatch.code);
      callRefused("medilab.subcontract.dispatch", "read", [[dispatch.id], ["report_file"]]).should("match", /not allowed|access/i);

      step("The subcontractor does not see the report");
      cy.signInAs("subcontractor");
      cy.visit(`/my/dispatches/${dispatch.id}`);
      cy.get("main").should("contain", dispatch.code).and("not.contain", REPORT);
    });
  });

  it("TC-WF05-E1 refuses to cancel a dispatch whose tests have results", () => {
    sentDispatch().then((sent) => {
      step("The subcontractor enters a result");
      subcontractorResult(sent);
      step("Cancelling the dispatch is refused");
      cy.signInAs("head_of_department");
      cy.openRecord(sent.dispatch);
      cy.expectRefusal({
        read: () => cy.readRecord(sent.dispatch, DISPATCH_FIELDS),
        action: () => {
          cy.get(`${ACTIONS} button[name=action_cancel]:visible`).click();
          cy.get(".modal:visible .modal-footer .btn-primary").click();
        },
        message: "A dispatch whose sample tests have results cannot be cancelled.",
      });
    });
  });

  it("TC-WF05-E2 shows a subcontractor user only their own dispatches, never a sample's customer", () => {
    sentDispatch("chlorpyrifos").then((other) =>
      sentDispatch().then(({ test, dispatch }) => {
        outsourcedTest().then((draft) => {
          step("The subcontractor sees only its own sent dispatches");
          cy.signInAs("subcontractor");
          cy.visit("/my/dispatches");
          cy.contains("a", dispatch.code).should("be.visible");
          cy.contains("a", other.dispatch.code).should("not.exist");
          cy.contains("a", draft.dispatch.code).should("not.exist");
          cy.request(`/my/dispatches/${draft.dispatch.id}`).should((response) => {
            expect(response.redirects, "sent back to the dispatches").not.to.be.empty;
            expect(response.body).not.to.contain(draft.test.code);
          });
        });
        step("Its dispatch shows the tests, never the sample's customer");
        cy.contains("a", dispatch.code).click();
        cy.contains("tr", test.code).should("contain", "Lead (Pb)");
        cy.get("main").should("not.contain", test.sampleName).and("not.contain", test.customerName);
        cy.request(`/my/dispatches/${other.dispatch.id}`).should((response) => {
          expect(response.redirects, "sent back to the dispatches").not.to.be.empty;
          expect(response.body).not.to.contain(other.test.code);
        });
        callRefused("medilab.sample.test", "read", [[test.id], ["sample_id"]]).should("match", /not allowed to access .*\(medilab\.sample\.test\)/);
      }),
    );
  });

  it("TC-WF05-E3 refuses outsourcing straight away without a reason, or a test already in testing", () => {
    assignedTest("lead", { days: 30 }).then((test) => {
      step("Outsourcing straight away without a reason is refused");
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      openOutsource().within(() => {
        cy.get("button[name=action_outsource]").click();
        cy.get("[name=reason].o_field_invalid").should("be.visible");
      });
      cy.get(".modal:visible .modal-footer button.btn-secondary").click();
      outsourceDialog(test).then((wizard) =>
        callRefused("medilab.sample.test.outsource", "action_outsource", [[wizard]]).should(
          "eq",
          "Give a reason for outsourcing the test straight away.",
        ),
      );
      cy.readRecord(test, ["status"]).its("status").should("eq", "assigned");
    });
    assignedTest("lead", { days: 30 }).then((test) => {
      step("Outsourcing a test already in testing is refused");
      callAs(TESTER, "medilab.test.result", "create", [{ sample_test_id: test.id, value: 2.5 }]);
      cy.signInAs("head_of_department");
      cy.readRecord(test, ["status"]).its("status").should("eq", "testing");
      cy.openRecord(test);
      cy.contains(`${ACTIONS} button:visible`, "Cancel Test").should("exist");
      cy.contains(`${ACTIONS} button`, "Outsource").should("not.exist");
      outsourceDialog(test, { reason: REASON }).then((wizard) =>
        callRefused("medilab.sample.test.outsource", "action_outsource", [[wizard]]).should(
          "match",
          /^Only a waiting or assigned sample test can be outsourced straight away: /,
        ),
      );
    });
  });

  // Generated by Cypress Author on 2026-11-08.
  it("TC-WF05-E4 refuses to outsource a test through another way than the one the customer accepted → it keeps its accepted way", () => {
    assignedTest("lead", { days: 30, accepted: PARAMETERS.lead.inHouse }).then((test) => {
      step("The head of department opens a test whose customer accepted the in-house way");
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      // The parameter has a subcontracted way, but the customer accepted the in-house one.
      cy.get(".o_form_view").should("contain", "Sales first obtains a revised quotation the customer accepts.");
      cy.contains(`${ACTIONS} button`, "Outsource").should("not.exist");
      step("Outsourcing it through another way is refused, and it keeps its accepted way");
      outsourceDialog(test, { reason: REASON }).then((wizard) =>
        callRefused("medilab.sample.test.outsource", "action_outsource", [[wizard]]).should(
          "match",
          /is tested by .+, the way of testing the customer accepted; another way needs a revised quotation\.$/,
        ),
      );
      refAs(ADMINISTRATOR, PARAMETERS.lead.inHouse).then((way) =>
        cy.readRecord(test, ["status", "parameter_method_id", "dispatch_ids"]).should((read) => {
          expect(read.status).to.equal("assigned");
          expect(read.parameter_method_id[0]).to.equal(way.id);
          expect(read.dispatch_ids).to.be.empty;
        }),
      );
    });
  });
});
