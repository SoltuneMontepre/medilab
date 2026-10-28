import { newRecord, pick, save } from "../../../support/form";
import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import {
  ADMINISTRATOR,
  EXPIRED_SUBCONTRACTOR,
  TESTER,
  archivedSubcontractor,
  assignedTest,
  clearDrafts,
  inDays,
  newParameter,
  newSubcontractor,
  outsourceDialog,
  outsourcedTest,
  reportedResult,
  resultAwaitingApproval,
  sentDispatch,
  subcontractorResult,
  suggestedTest,
  wayParts,
} from "./setup";

const REASON = "Máy AAS đang sửa, khách hàng cần kết quả chì trước hạn.";
const TRACKING = "Viettel Post, VTP 8402 1157 2210";

const DISPATCH_FIELDS = ["status", "sample_test_ids", "write_date"];
const ACTIONS = ".o_form_view .o_statusbar_buttons";

// A date as the English back office shows it.
function shownDate(date) {
  const [year, month, day] = date.split("-");
  return `${month}/${day}/${year}`;
}

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
      cy.signInAs("head_of_department");
      // The list shows the newest samples first, and its search looks up parameters, not sample codes.
      cy.visit("/odoo/outsourcing-suggestions");
      cy.contains(".o_data_row", test.code).contains("button", "Outsource").click();
      cy.get(".modal:visible").within(() => {
        cy.get("[name=reason]").should("not.exist");
        cy.get("button[name=action_outsource]").click();
      });
      cy.location("pathname").should("match", /medilab\.subcontract\.dispatch\/\d+$/);
      cy.contains(".o_field_widget[name=sample_test_ids] .o_data_row", test.code).should("be.visible");
      cy.get(".o_field_widget[name=expected_date] input").clear().type(shownDate(expected));
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
          cy.visit("/odoo/outsourcing-schedule?view_type=list");
          cy.contains(".o_data_row", read.code).find("td[name=expected_date]").should("contain", listedDate(expected));

          cy.signInAs("sample_delivery_staff");
          cy.visit("/odoo/dispatches-to-carry");
          cy.contains(".o_data_row", read.code).should("be.visible");

          cy.signInAs("subcontractor");
          cy.visit("/my/dispatches");
          cy.contains("a", read.code).click();
          cy.contains("tr", test.code).within(() => {
            cy.get("input[name=value]").type("4.6");
            cy.get("button[type=submit]").click();
          });
          cy.contains("tr", test.code).should("contain", "4.6").and("contain", "Entered by");
        });
        reportedResult(test).then((result) => {
          expect(result.entered_by_id[1]).to.equal("Nguyen Thi Lan");
          cy.signInAs("tester");
          cy.openRecord(result);
          cy.signRecord();
          cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
          cy.readRecord(result, ["status"]).its("status").should("eq", "requested");
          cy.signInAs("head_of_department");
          cy.openRecord(result);
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
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.get(".o_field_widget[name=expected_date] input").clear().type(shownDate(inDays(10)));
      cy.get(".o_field_widget[name=delivery_service] input").type(TRACKING);
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
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.get(`${ACTIONS} button[name=action_receive]:visible`).click();
      cy.get(`${ACTIONS} button[name=action_receive]`).should("not.exist");
      cy.readRecord(dispatch, ["status"]).its("status").should("eq", "received");

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
      cy.signInAs("head_of_department");
      cy.readRecord(test, ["outsourcing_suggested"]).its("outsourcing_suggested").should("eq", false);
      cy.openRecord(test);
      openOutsource().within(() => {
        cy.get("[name=reason] textarea").type(REASON);
        cy.get("button[name=action_outsource]").click();
      });
      cy.location("pathname").should("match", /medilab\.subcontract\.dispatch\/\d+$/);
      cy.contains(".o_field_widget[name=sample_test_ids] .o_data_row", test.code).should("be.visible");
      cy.readRecord(test, ["status", "emergency_outsource_reason", "dispatch_ids"]).should((read) => {
        expect(read.status).to.equal("outsourced");
        expect(read.emergency_outsource_reason).to.equal(REASON);
        expect(read.dispatch_ids).to.have.length(1);
      });
    });
  });

  it("TC-WF05-A4 lets the head reject the subcontractor's result, and the subcontractor enter a new one", () => {
    resultAwaitingApproval().then(({ test, dispatch, result }) => {
      cy.signInAs("head_of_department");
      cy.openRecord(result);
      cy.rejectRecord("Kết quả vượt ngưỡng phát hiện của phương pháp, đề nghị đo lại.");
      cy.readRecord(result, ["status"]).its("status").should("eq", "rejected");
      cy.readRecord(test, ["status"]).its("status").should("eq", "outsourced");

      cy.signInAs("subcontractor");
      cy.visit(`/my/dispatches/${dispatch.id}`);
      cy.contains("tr", test.code).within(() => {
        cy.get("input[name=value]").type("4.4");
        cy.get("button[type=submit]").click();
      });
      cy.contains("tr", test.code).should("contain", "4.4");
      reportedResult(test).should((reported) => {
        expect(reported.attempt).to.equal(2);
        expect(reported.status).to.equal("none");
      });
    });
  });

  it("TC-WF05-A5 cancels a dispatch before any result, and its test goes in another dispatch", () => {
    sentDispatch().then(({ test, dispatch }) => {
      cy.signInAs("head_of_department");
      cy.openRecord(dispatch);
      cy.get(`${ACTIONS} button[name=action_cancel]:visible`).click();
      cy.get(".modal:visible .modal-footer .btn-primary").click();
      cy.get(`${ACTIONS} button[name=action_cancel]`).should("not.exist");
      cy.readRecord(dispatch, ["status"]).its("status").should("eq", "cancelled");
      cy.readRecord(test, ["status"]).its("status").should("eq", "outsourced");

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

  it("TC-WF05-E1 refuses to cancel a dispatch whose tests have results", () => {
    sentDispatch().then((sent) => {
      subcontractorResult(sent);
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
});

describe("WF-05 feature acceptance criteria", () => {
  it("TC-F37-01 lets the administrator choose a subcontractor with a valid accreditation on a way of testing", () => {
    newParameter().then((parameter) => {
      cy.signInAs("administrator");
      cy.openRecord(parameter);
      cy.get(".o_field_widget[name=method_ids] .o_field_x2many_list_row_add button").click();
      pick("method_id", "ISO 17294-2");
      pick("unit_id", "µg/L");
      // With nothing typed, the suggestions start from the first subcontractor codes, the seeded ones.
      cy.get(".o_selected_row .o_field_widget[name=subcontractor_id] input").click();
      cy.get(".o-autocomplete--dropdown-menu").should("contain", "Northern").and("not.contain", "Coastal").and("not.contain", "Mekong");
      cy.contains(".o-autocomplete--dropdown-item a", "Northern").click();
      save();
      call("medilab.parameter.method", "search_read", [[["parameter_id", "=", parameter.id]]], { fields: ["subcontractor_id"] }).should(
        ([way]) => expect(way.subcontractor_id[1]).to.contain("Northern"),
      );
    });
  });

  it("TC-F37-02 keeps a way's subcontractor after its accreditation expires, and renewing it makes it selectable again", () => {
    wayParts().then(({ methodId, unitId }) =>
      newSubcontractor().then((subcontractor) =>
        newParameter().then((first) =>
          newParameter().then((second) => {
            const way = (parameter) => ({ parameter_id: parameter.id, method_id: methodId, unit_id: unitId, subcontractor_id: subcontractor.id });
            callAs(ADMINISTRATOR, "medilab.parameter.method", "create", [way(first)]).then((id) => {
              const kept = { model: "medilab.parameter.method", id };
              callAs(ADMINISTRATOR, "medilab.subcontractor", "write", [[subcontractor.id], { accreditation_expiry: inDays(-1) }]);
              cy.signInAs("administrator");
              call(kept.model, "write", [[id], { lod: 0.07 }]);
              cy.readRecord(kept, ["subcontractor_id", "lod"]).should((read) => {
                expect(read.subcontractor_id[0]).to.equal(subcontractor.id);
                expect(read.lod).to.equal(0.07);
              });
              callRefused(kept.model, "create", [way(second)]).should(
                "match",
                new RegExp(`^The accreditation of ${subcontractor.name} expired on .+\\. Renew it before choosing this subcontractor\\.$`),
              );
              cy.openRecord(subcontractor);
              cy.get(".o_field_widget[name=accreditation_expiry] button").click();
              cy.get(".o_field_widget[name=accreditation_expiry] input").clear().type(shownDate(inDays(365)));
              save();
              call(kept.model, "create", [way(second)]).should("be.a", "number");
            });
          }),
        ),
      ),
    );
  });

  it("TC-F37-03 refuses to choose an archived subcontractor, or one whose accreditation expired", () => {
    wayParts().then(({ methodId, unitId }) =>
      newParameter().then((parameter) => {
        const way = (subcontractor) => ({ parameter_id: parameter.id, method_id: methodId, unit_id: unitId, subcontractor_id: subcontractor.id });
        cy.signInAs("administrator");
        refAs(ADMINISTRATOR, EXPIRED_SUBCONTRACTOR).then((expired) =>
          callRefused("medilab.parameter.method", "create", [way(expired)]).should(
            "match",
            /^The accreditation of Coastal .+ expired on .+\. Renew it before choosing this subcontractor\.$/,
          ),
        );
        archivedSubcontractor().then((archived) =>
          callRefused("medilab.parameter.method", "create", [way(archived)]).should("eq", "Mekong Food Testing is archived and cannot be chosen."),
        );
        call("medilab.parameter.method", "search_count", [[["parameter_id", "=", parameter.id]]]).should("eq", 0);
      }),
    );
  });
});
