import { addLine, discardRefused, openMenu, openRow, openTab, pick, save, saveAndWait } from "../../../support/form";
import { MENU } from "../../../support/menus";
import { step } from "../../../support/steps";
import { call, callAs, callRefused, refAs, resolveRecord } from "../../../support/odoo";
import { releaseFixtures } from "../wf-03-testing-scheduling/setup";
import {
  LAB_HEAD,
  TESTER,
  approveAsHead,
  approvedResult,
  assignedTest,
  bookedLead,
  enteredResult,
  leadInTesting,
  newRegulation,
  results,
  sentResult,
  testingTasks,
} from "./setup";

const ACTIONS = ".o_form_view .o_statusbar_buttons";
const CANCELLATION = "Mẫu không đủ thể tích để phân tích chì.";
// Lead in bottled water compared with QCVN 6-1:2010/BYT, which limits it there.
const COMPARED_WATER = { regulation: "sol_demo.demo_regulation_qcvn_6_1" };
// Lead in lettuce compared with QCVN 8-2:2011/BYT, which limits lead on cabbage but not on lettuce.
const LETTUCE_WITHOUT_LIMIT = {
  sampleType: "sol_demo.demo_sample_type_lettuce",
  state: "solid",
  regulation: "sol_demo.demo_regulation_qcvn_8_2",
};

// Chooses an assessment of the open result and saves it.
function assess(label) {
  cy.get(".o_field_widget[name=conclusion]").contains("label", label).click();
  save();
}

// Enters a value on the open form of a sample test and saves the result.
function enterResultOnForm(value) {
  cy.signRecord("action_enter_result");
  cy.get(".o_field_widget[name=value] input").clear().type(value);
  save();
}

// Enters a value for the sample test through its form and saves the result.
function enterResult(test, value) {
  cy.openRecord(test);
  enterResultOnForm(value);
}

// Only the bookings these tests made are released, so the machines stay free for the next ones.
afterEach(releaseFixtures);

describe("WF-04 Result entry and approval", () => {
  it("TC-WF04-M lets the tester enter and send a result, which completes their testing task, and the head approve it", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      step("The tester opens the sample test and enters its result");
      cy.signInAs("tester");
      openMenu(MENU.laboratory, MENU.samples, MENU.sampleTests);
      openRow(test.code);
      enterResultOnForm("0.008");
      cy.get(".o_field_widget[name=conclusion]").should("not.exist");
      step("The tester signs and sends the result, which completes the testing task");
      cy.signRecord();
      cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
      testingTasks(test).then((tasks) => expect(tasks.map((task) => task.status)).to.deep.equal(["done"]));
      cy.readRecord(test, ["status"]).its("status").should("eq", "result_entered");

      results(test).then(([result]) => {
        callRefused("medilab.test.result", "write", [[result.id], { value: 0.003 }]).should(
          "eq",
          "The document has signatures; withdraw them before changing it.",
        );
        step("The head of department opens the result and approves it");
        approveAsHead(test, result);
      });
    });
  });

  it("TC-WF04-A2 lets the tester withdraw a sent result, which gives them back their testing task", () => {
    sentResult().then(({ test, result }) => {
      step("The tester withdraws the result they sent");
      cy.signInAs("tester");
      cy.openRecord(result);
      cy.signRecord("action_withdraw");
      cy.get(`${ACTIONS} button[name=action_withdraw]`).should("not.exist");
      step("The result is back with the tester, who has their testing task again");
      cy.readRecord(result, ["status"]).its("status").should("eq", "none");
      refAs(TESTER, "sol_demo.demo_person_tester").then((tester) =>
        testingTasks(test).then(([task, ...others]) => {
          expect(others).to.be.empty;
          expect(task.status).to.equal("assigned");
          expect(task.assignee_id[0]).to.equal(tester.id);
        }),
      );
    });
  });

  it("TC-WF04-E1 lets the head reject a result, which stays on record and gives the tester a new testing task", () => {
    const reason = "Mẫu chuẩn kiểm tra đọc cao 15%, hiệu chuẩn lại máy AAS và đo lại.";
    sentResult().then(({ test, result }) => {
      step("The head of department rejects the result with a reason");
      cy.signInAs("head_of_department");
      cy.openRecord(result);
      cy.rejectRecord(reason);
      step("The rejected result stays on record, and a new testing task with the reason goes back to the tester");
      cy.readRecord(result, ["status"]).its("status").should("eq", "rejected");
      cy.readRecord(test, ["status"]).its("status").should("eq", "testing");
      refAs(TESTER, "sol_demo.demo_person_tester").then((tester) =>
        testingTasks(test).then(([done, retest, ...others]) => {
          expect(others).to.be.empty;
          expect(done.status).to.equal("done");
          expect(retest.status).to.equal("assigned");
          expect(retest.assignee_id[0]).to.equal(tester.id);
          expect(retest.note).to.contain(reason);
        }),
      );

      step("The tester enters the retest result, which is the one reported");
      cy.signInAs("tester");
      enterResult(test, "0.009");
      results(test).then((rows) => {
        expect(rows.map((row) => [row.status, row.is_reported])).to.deep.equal([
          ["none", true],
          ["rejected", false],
        ]);
      });
    });
  });

  it("TC-WF04-A1 lets the tester assess and send a value below the LOD, keeping the measured value", () => {
    assignedTest("lead", { days: 7, sample: COMPARED_WATER }).then((test) => {
      step("The tester enters a value below the LOD, and the regulation's limit shows");
      cy.signInAs("tester");
      enterResult(test, "0.003");
      cy.get(".o_field_widget[name=limit_max]").should("contain", "0.01");
      cy.get(".o_field_widget[name=limit_unit_id]").should("contain", "mg/L");
      results(test).then(([result]) => {
        cy.readRecord(result, ["value", "conclusion"]).should("deep.include", { value: 0.003, conclusion: false });
        step("The tester assesses the result and sends it for approval");
        assess("Pass");
        cy.signRecord();
        cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
        cy.readRecord(result, ["status", "conclusion"]).should("deep.include", {
          status: "requested",
          conclusion: "pass",
        });
      });
    });
  });

  it("TC-WF04-A4 shows a missing exact-type limit and lets the tester send it only as insufficient basis", () => {
    assignedTest("lead", { days: 7, sample: LETTUCE_WITHOUT_LIMIT }).then((test) => {
      step("The tester enters a result on a sample type the regulation sets no limit for");
      cy.signInAs("tester");
      enterResult(test, "0.12");
      cy.contains(".o_form_view .alert-warning", "can only be assessed as insufficient basis").should("be.visible");
      results(test).then(([result]) => {
        step("Only insufficient basis can be chosen, and the tester sends it so");
        callRefused("medilab.test.result", "write", [[result.id], { conclusion: "pass" }]).should("contain", "insufficient basis");
        assess("Insufficient Basis");
        cy.signRecord();
        cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
        cy.readRecord(result, ["status", "conclusion", "limit_missing"]).should("deep.include", {
          status: "requested",
          conclusion: "insufficient",
          limit_missing: true,
        });
      });
    });
  });

  it("TC-WF04-A1 lets the tester enter and send a plain text result on a sample without a regulation", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      step("The tester enters a plain text result on a sample without a regulation");
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.signRecord("action_enter_result");
      cy.get(".o_field_widget[name=conclusion]").should("not.exist");
      cy.get(".o_field_widget[name=value_text] input").type("Not detected").blur();
      cy.get(".o_field_widget[name=value]").should("not.exist");
      save();
      step("The tester sends the text result for approval");
      cy.signRecord();
      cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
      results(test).then(([result]) =>
        cy.readRecord(result, ["status", "value_display"]).should("deep.include", { status: "requested", value_display: "Not detected" }),
      );
    });
  });

  it("TC-WF04-E3 lets the head cancel a test with a reason, and completes the sample and its report without it", () => {
    leadInTesting().then((sample) => {
      const { lead, ph } = sample;
      step("The sample's other test is approved");
      approvedResult(ph, { value: 7.2 }).as("phResult");
      step("The head of department cancels the lead test with a reason");
      cy.signInAs("head_of_department");
      cy.openRecord(lead);
      cy.rejectRecord(CANCELLATION, { action: "action_cancel" });
      cy.get(".o_field_widget[name=cancel_reason]").should("contain", CANCELLATION);
      cy.readRecord(lead, ["status", "cancel_reason"]).should("deep.include", { status: "cancelled", cancel_reason: CANCELLATION });
      step("Its task and booking are cancelled, and the sample completes");
      cy.readRecord(lead.task, ["status"]).its("status").should("eq", "cancelled");
      cy.readRecord(lead.booking, ["status"]).its("status").should("eq", "cancelled");
      cy.readRecord(sample, ["status"]).its("status").should("eq", "completed");
      step("The report holds only the approved test");
      cy.readRecord(sample, ["request_id"]).then(({ request_id: [requestId] }) =>
        cy
          .get("@phResult")
          .then((phResult) =>
            callAs(LAB_HEAD, "medilab.test.report", "search_read", [[["request_id", "=", requestId]]], { fields: ["result_ids"] }).should(
              ([report]) => expect(report.result_ids).to.deep.equal([phResult.id]),
            ),
          ),
      );
    });
  });
});

describe("WF-04 feature acceptance criteria", () => {
  it("TC-F30-01 shows the tester the steps of the method on their testing task, in number order", () => {
    bookedLead().then((test) => {
      cy.signInAs("tester");
      cy.openRecord(test.task);
      openTab("method_steps");
      cy.readRecord(test.task, ["method_step_ids"])
        .then(({ method_step_ids }) =>
          call("medilab.testing.method.step", "read", [method_step_ids, ["sequence", "duration_minutes", "instruction", "note"]]),
        )
        .then((steps) => {
          expect(steps, "steps of the method").not.to.be.empty;
          const ordered = Cypress._.sortBy(steps, "sequence");
          cy.get(".o_field_widget[name=method_step_ids] .o_data_row")
            .should("have.length", ordered.length)
            .each((row, index) => {
              const step = ordered[index];
              cy.wrap(row).find("td[name=sequence]").should("have.text", String(step.sequence));
              cy.wrap(row).find("td[name=duration_minutes]").should("have.text", String(step.duration_minutes));
              cy.wrap(row).find("td[name=instruction]").should("have.text", step.instruction);
              cy.wrap(row)
                .find("td[name=note]")
                .should("have.text", step.note || "");
            });
        });
    });
  });

  it("TC-F30-02 refuses two steps of one method with the same number", () => {
    cy.signInAs("administrator");
    resolveRecord("sol_demo.demo_testing_method_tcvn_7602").then((method) => {
      cy.openRecord(method);
      cy.expectRefusal({
        read: () => call("medilab.testing.method.step", "search_read", [[["method_id", "=", method.id]]], { fields: ["sequence", "write_date"] }),
        action: () => {
          addLine("step_ids");
          cy.get(".o_selected_row [name=sequence] input").clear().type("1");
          cy.get(".o_selected_row [name=duration_minutes] input").clear().type("10");
          cy.get(".o_selected_row [name=instruction] textarea").type("Tráng chén nung bằng axit nitric.");
          cy.get(".o_form_button_save").click();
        },
        message: "Two steps of a testing method cannot have the same number.",
      });
      discardRefused();
    });
  });

  it("TC-F30-03 does not let a tester change a step", () => {
    cy.signInAs("tester");
    resolveRecord("sol_demo.demo_testing_method_tcvn_7602").then((method) => {
      cy.openRecord(method);
      cy.get(".o_field_widget[name=step_ids] .o_data_row").should("have.length.greaterThan", 0);
      cy.get(".o_field_widget[name=step_ids] .o_field_x2many_list_row_add").should("not.exist");
    });
    resolveRecord("sol_demo.demo_testing_method_step_tcvn_7602_1").then((step) => {
      callRefused("medilab.testing.method.step", "write", [[step.id], { duration_minutes: 20 }]).should(
        "match",
        /^You are not allowed to Edit these records: /,
      );
      cy.readRecord(step, ["duration_minutes"]).its("duration_minutes").should("eq", 15);
    });
  });

  it("TC-F32-02 keeps a result's copied limit when the regulation changes, and holds one limit per parameter and sample type", () => {
    newRegulation(0.05).then((regulation) => {
      assignedTest("lead", { days: 7, sample: { regulation } }).then((test) => {
        enteredResult(test, { value: 0.004 }).then((result) => {
          cy.signInAs("administrator");
          cy.openRecord(regulation);
          cy.expectRefusal({
            read: () => cy.readRecord(regulation, ["limit_ids", "write_date"]),
            action: () => {
              addLine("limit_ids");
              pick("parameter_id", "Lead (Pb)");
              pick("sample_type_id", "Bottled water");
              cy.get(".o_selected_row [name=limit_text] input").type("Không phát hiện");
              cy.get(".o_form_button_save").click();
            },
            message: "A regulation sets at most one limit per parameter and sample type.",
          });
          discardRefused();
          cy.get(".o_field_widget[name=limit_ids] .o_data_row td[name=max_value]").click();
          cy.get(".o_selected_row [name=max_value] input").clear().type("0.02");
          saveAndWait("medilab.regulation");
          cy.readRecord(regulation, ["limit_ids"]).then(({ limit_ids: [limit] }) =>
            cy.readRecord({ model: "medilab.regulation.limit", id: limit }, ["max_value"]).its("max_value").should("eq", 0.02),
          );
          cy.readRecord(result, ["limit_max"]).its("limit_max").should("eq", 0.05);
        });
      });
    });
  });

  it("TC-F32-03 refuses to send a result whose requested comparison has no conclusion", () => {
    assignedTest("lead", { days: 7, sample: COMPARED_WATER }).then((test) => {
      enteredResult(test, { value: 0.004 }).then((result) => {
        cy.signInAs("tester");
        cy.openRecord(result);
        cy.expectRefusal({
          read: () => cy.readRecord(result, ["status", "value", "conclusion", "write_date"]),
          action: () => cy.signRecord(),
          message: "Assess the result against the regulation as pass, fail or insufficient basis before sending it.",
        });
      });
    });
  });

  it("TC-F34-02 sends only the latest result of a test for approval", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      enteredResult(test, { value: 0.004 }).then((first) => {
        enteredResult(test, { value: 0.005 });
        cy.signInAs("tester");
        cy.openRecord(first);
        cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
        callRefused("medilab.test.result", "action_sign", [[first.id]]).should(
          "eq",
          "Only the reported result of a sample test is sent for approval.",
        );
        cy.readRecord(first, ["status", "is_reported"]).should("deep.include", { status: "none", is_reported: false });
      });
    });
  });

  it("TC-F36-03 refuses to cancel a test without a reason, or a test with an approved result", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      cy.expectRefusal({
        read: () => cy.readRecord(test, ["status", "cancel_reason", "write_date"]),
        action: () => {
          cy.get(`${ACTIONS} button.btn-danger:visible`).click();
          cy.get(".modal:visible [name=reason] textarea").type("   ");
          cy.get(".modal:visible button[name=action_cancel]").click();
        },
        message: "Give a reason for cancelling the test.",
      });
    });
    assignedTest("lead", { days: 7 }).then((test) => {
      approvedResult(test, { value: 0.004 });
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      cy.get(`${ACTIONS} button.btn-danger`).should("not.exist");
      callRefused("medilab.sample.test", "action_cancel", [[test.id], CANCELLATION]).should(
        "match",
        /^Only a waiting, assigned or testing sample test can be cancelled: /,
      );
      cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
    });
  });
});
