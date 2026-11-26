import { newRecord, openMenu, openRow, pick, save } from "../../../support/form";
import { MENU } from "../../../support/menus";
import { step } from "../../../support/steps";
import { approveAsHead } from "../wf-04-result-approval/setup";
import { callAs, callRefused, refAs } from "../../../support/odoo";
import {
  ACTIONS,
  ADMINISTRATOR,
  PARAMETERS,
  REASON,
  assignedTest,
  clearDrafts,
  inDays,
  openOutsource,
  outsourcedTest,
  reportedResult,
  resultAwaitingApproval,
  sentDispatch,
  suggestedTest,
} from "./setup";

const SERVICE = "Viettel Post";
const TRACKING = "VTP 8402 1157 2210";
const FAILURE = "Xe giao mẫu hỏng giữa đường, thùng bảo quản mất lạnh.";

// A date as an English list shows it, such as "Nov 4"; another year follows it.
function listedDate(date) {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

describe("WF-05 Outsourced testing", () => {
  it("TC-WF05-M lets the head accept a suggestion, staff carry the dispatch, the subcontractor confirm receipt and enter the result and the head approve it", () => {
    // Northern returns lead results six days after the samples are sent.
    const expected = inDays(6);
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
      step("The head chooses the sample delivery staff who carry the dispatch");
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
      save();
      // Only the sample delivery staff of the dispatch hand it over.
      cy.contains(`${ACTIONS} button`, "Hand Over").should("not.exist");
      cy.location("pathname").then((path) => {
        const dispatch = { model: "medilab.subcontract.dispatch", id: Number(path.split("/").pop()) };
        cy.readRecord(dispatch, ["code"]).then((read) => {
          step("Sample delivery staff take the dispatch from their dispatches to carry");
          cy.signInAs("sample_delivery_staff");
          openMenu(MENU.laboratory, MENU.schedule, MENU.dispatchesToCarry);
          openRow(read.code);
          cy.contains(`${ACTIONS} button:visible`, "Hand Over").click();
          cy.get(".modal:visible").within(() => cy.get("button[name=action_hand_over]").click());
          cy.get(".modal").should("not.exist");
          cy.readRecord(dispatch, ["status", "sent_date", "expected_date", "courier_id"]).should((sent) => {
            expect(sent.status).to.equal("sent");
            expect(sent.sent_date).to.equal(inDays(0));
            expect(sent.expected_date).to.equal(expected);
            expect(sent.courier_id[1]).to.equal("Vo Van Tai");
          });
          cy.readRecord(test, ["status"]).its("status").should("eq", "outsourced");
          step("The dispatch shows in the outsourcing schedule");
          cy.signInAs("head_of_department");
          openMenu(MENU.laboratory, MENU.schedule, MENU.outsourcingSchedule);
          cy.get(".o_switch_view.o_list").click();
          cy.contains(".o_data_row", read.code).find("td[name=expected_date]").should("contain", listedDate(expected));

          step("The subcontractor confirms receipt and enters the result on the portal");
          cy.signInAs("subcontractor");
          cy.get("a[href='/my/dispatches']:visible").first().click();
          cy.contains("a", read.code).click();
          // No result is entered before the subcontractor confirms the samples arrived.
          cy.get("input[name=value]").should("not.exist");
          cy.contains("button", "Confirm Receipt").click();
          cy.contains("button", "Confirm Receipt").should("not.exist");
          cy.contains("p", "Received on").should("be.visible");
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
          // Outsourcing ended the tester's testing task, so the test is no longer theirs to work on.
          openMenu(MENU.laboratory, MENU.samples, MENU.sampleTests);
          cy.contains(".o_data_row", test.code).should("not.exist");
          // The subcontractor's result waiting to be sent comes before any other.
          cy.openRecord(test);
          cy.get(`${ACTIONS} button[name=action_enter_result]`).should("not.exist");
          openMenu(MENU.laboratory, MENU.results, MENU.testResults);
          openRow(test.code);
          cy.signRecord();
          cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
          cy.readRecord(result, ["status"]).its("status").should("eq", "requested");
          step("The head of department approves the result");
          approveAsHead(test, result);
        });
      });
    });
  });

  it("TC-WF05-A1 lets sample delivery staff hand a dispatch to a delivery service with its tracking number", () => {
    outsourcedTest().then(({ dispatch }) => {
      refAs(ADMINISTRATOR, "sol_demo.demo_person_sample_delivery_staff").then((courier) =>
        callAs(ADMINISTRATOR, "medilab.subcontract.dispatch", "write", [[dispatch.id], { courier_id: courier.id }]),
      );
      step("Sample delivery staff hand the dispatch to a delivery service");
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(dispatch);
      cy.contains(`${ACTIONS} button:visible`, "Hand Over").click();
      cy.get(".modal:visible").within(() => {
        cy.get(".o_field_widget[name=delivery_service] input").type(SERVICE).blur();
        // A delivery service needs its tracking number.
        cy.get(".o_field_widget[name=tracking_number] input").type(TRACKING);
        cy.get("button[name=action_hand_over]").click();
      });
      cy.readRecord(dispatch, ["status", "courier_id", "delivery_service", "tracking_number", "expected_date"]).should((read) => {
        expect(read.status).to.equal("sent");
        expect(read.courier_id[1]).to.equal("Vo Van Tai");
        expect(read.delivery_service).to.equal(SERVICE);
        expect(read.tracking_number).to.equal(TRACKING);
        expect(read.expected_date).to.equal(inDays(6));
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
      // Results of an outsourced test are entered once its subcontractor received the dispatch.
      step("No result is entered before the dispatch is received");
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.get(`${ACTIONS} button[name=action_enter_result]`).should("not.exist");
    });
  });

  it("TC-WF05-E1 lets the head reject the subcontractor's result, and the subcontractor enter a new one", () => {
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

  it("TC-WF05-E2 cancels a dispatch before any result, and its test goes in another dispatch", () => {
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

  it("TC-WF05-E3 lets sample delivery staff record a failed delivery → the dispatch is cancelled and its test stays outsourced", () => {
    sentDispatch().then(({ test, dispatch }) => {
      step("The sample delivery staff record why the delivery failed");
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(dispatch);
      cy.contains(`${ACTIONS} button:visible`, "Delivery Failed").click();
      cy.get(".modal:visible").within(() => {
        cy.get(".o_field_widget[name=reason] textarea").type(FAILURE);
        cy.get("button[name=action_confirm]").click();
      });
      cy.get(".modal").should("not.exist");
      cy.readRecord(dispatch, ["status", "failure_reason"]).should((read) => {
        expect(read.status).to.equal("cancelled");
        expect(read.failure_reason).to.equal(FAILURE);
      });
      step("The test stays outsourced for a new dispatch");
      cy.readRecord(test, ["status"]).its("status").should("eq", "outsourced");
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.get(".o_form_view").should("contain", FAILURE);
      cy.contains(`${ACTIONS} button`, "Delivery Failed").should("not.exist");
    });
  });

  it("TC-WF05-E4 tells the head about a lapsed accreditation; the head cancels the draft and moves its test to a subcontractor with the same method", () => {
    cy.signInAs("head_of_department");
    refAs(ADMINISTRATOR, "sol_demo.demo_subcontract_dispatch_accreditation_lapsed").then((dispatch) =>
      cy.readRecord(dispatch, ["status", "sample_test_ids"]).then(({ status, sample_test_ids: [testId] }) => {
        expect(status, "the seeded draft dispatch of a lapsed subcontractor").to.equal("draft");
        const test = { model: "medilab.sample.test", id: testId };
        step("The head cannot send the draft dispatch of a subcontractor whose accreditation lapsed");
        callRefused("medilab.subcontract.dispatch", "action_send", [[dispatch.id]]).should("match", /accreditation has expired/);
        step("The head cancels it and moves the test to Northern, which tests lead by the same method");
        cy.openRecord(dispatch);
        cy.get(`${ACTIONS} button[name=action_cancel]:visible`).click();
        cy.get(".modal:visible .modal-footer .btn-primary").click();
        cy.readRecord(dispatch, ["status"]).its("status").should("eq", "cancelled");
        cy.openRecord(test);
        cy.contains(`${ACTIONS} button:visible`, "Move to Another Subcontractor").click();
        cy.get(".modal:visible").within(() => {
          cy.get("[name=reason]").should("not.exist");
          cy.get("button[name=action_outsource]").click();
        });
        cy.location("pathname").should("match", /medilab\.subcontract\.dispatch\/\d+$/);
        refAs(ADMINISTRATOR, PARAMETERS.lead.way).then((northern) =>
          cy.readRecord(test, ["status", "parameter_method_id"]).should((read) => {
            expect(read.status).to.equal("outsourced");
            expect(read.parameter_method_id[0]).to.equal(northern.id);
          }),
        );
      }),
    );
  });
});
