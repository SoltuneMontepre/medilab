import { newRecord, openMenu, openRow, pick, save } from "../../../support/form";
import { MENU, PORTAL_MENU } from "../../../support/menus";
import { step } from "../../../support/steps";
import { CUSTOMERS, clearCarts } from "../wf-01-order-to-test-request/setup";
import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import { ADMINISTRATOR, PARAMETERS, TESTER, assignedTest, clearDrafts, inDays, outsourceDialog, outsourcedTest, reportedResult, receivedDispatch, resultAwaitingApproval, sentDispatch, subcontractorResult, suggestedTest } from "./setup";

const REASON = "Máy AAS đang sửa, khách hàng cần kết quả chì trước hạn.";
const SERVICE = "Viettel Post";
const TRACKING = "VTP 8402 1157 2210";
const REPORT = "PKQ-NTL-2026-0412.pdf";

const FAILURE = "Xe giao mẫu hỏng giữa đường, thùng bảo quản mất lạnh.";
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
    receivedDispatch().then((sent) => {
      step("The subcontractor enters a result");
      subcontractorResult(sent);
      step("The head sees no cancel action, and cancelling through RPC is refused");
      cy.signInAs("head_of_department");
      cy.openRecord(sent.dispatch);
      cy.get(`${ACTIONS} button[name=action_cancel]`).should("not.exist");
      callRefused("medilab.subcontract.dispatch", "action_cancel", [[sent.dispatch.id]]).should("match", /Only a draft or sent dispatch can be cancelled/);
      cy.readRecord(sent.dispatch, ["status"]).its("status").should("eq", "received");
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
  it("TC-WF05-E4 refuses to outsource a test with another method than the one the customer accepted → it keeps its accepted way", () => {
    assignedTest("lead", { days: 30, accepted: PARAMETERS.lead.inHouse }).then((test) => {
      step("The head of department opens a test whose customer accepted a method no subcontractor tests");
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      // Northern tests lead by ICP-MS; the customer accepted AAS.
      cy.get(".o_form_view").should("contain", "outsourcing it with another method needs a revised quotation the customer accepts.");
      cy.contains(`${ACTIONS} button`, "Outsource").should("not.exist");
      step("Outsourcing it with another method is refused, and it keeps its accepted way");
      outsourceDialog(test, { reason: REASON }).then((wizard) =>
        callRefused("medilab.sample.test.outsource", "action_outsource", [[wizard]]).should(
          "match",
          /with another method than the one the customer accepted; outsourcing through it needs a revised quotation the customer accepts\.$/,
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

  it("TC-WF05-A7 lets the head outsource a test accepted in-house to a subcontractor with the same method, without the customer", () => {
    clearDrafts();
    assignedTest("lead", { days: 30, accepted: PARAMETERS.lead.sameMethod }).then((test) => {
      // No in-house machine runs ICP-MS in time, so the scheduler suggests outsourcing it.
      step("The head of department accepts the suggestion for a test the customer accepted in-house by ICP-MS");
      cy.signInAs("head_of_department");
      cy.readRecord(test, ["outsourcing_suggested"]).its("outsourcing_suggested").should("eq", true);
      cy.openRecord(test);
      cy.get(".o_form_view").should("not.contain", "needs a revised quotation");
      openOutsource().within(() => {
        cy.get(".o_field_widget[name=parameter_method_id] input").invoke("val").should("match", /^Lead \(Pb\) – ISO 17294-2:2016 \(.+\)$/);
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

  it("TC-WF05-E5 offers the customer each method once in the cart, never naming the subcontractor", () => {
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

  it("TC-WF05-E6 lets sample delivery staff record a failed delivery → the dispatch is cancelled and its test stays outsourced", () => {
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

  it("TC-WF05-E7 tells the head about a lapsed accreditation; the head cancels the draft and moves its test to a subcontractor with the same method", () => {
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

  it("TC-WF05-A8 prints a dispatch with its sample tests and never the customer", () => {
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

  it("TC-WF05-A9 lets a person with the subcontractor permission add its contact people", () => {
    const name = `Người liên hệ ${Date.now()}`;
    refAs(ADMINISTRATOR, "sol_demo.demo_subcontractor_southern_micro").then((subcontractor) => {
      step("The administrator adds a contact person to the subcontractor");
      cy.signInAs("administrator");
      cy.openRecord(subcontractor);
      cy.contains(".o_form_view .o_form_statusbar button:visible", "Add a Contact Person").click();
      cy.get(".modal:visible").within(() => {
        cy.get(".o_field_widget[name=name] input").type(name);
        cy.get("button[name=action_add]").click();
      });
      cy.get(".modal").should("not.exist");
      cy.contains(".o_notebook .nav-link", "Contact People").click();
      cy.contains(".o_field_widget[name=contact_ids] .o_data_row", name).should("be.visible");
    });
  });
});
