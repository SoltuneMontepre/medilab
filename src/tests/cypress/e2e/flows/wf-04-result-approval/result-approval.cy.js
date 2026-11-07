import { save } from "../../../support/form";
import { refAs } from "../../../support/odoo";
import { TESTER, assignedTest, results, sentResult, testingTasks } from "./setup";

const ACTIONS = ".o_form_view .o_statusbar_buttons";

// Enters a value for the sample test through its form and saves the result.
function enterResult(test, value) {
  cy.openRecord(test);
  cy.signRecord("action_enter_result");
  cy.get(".o_field_widget[name=value] input").clear().type(value);
  save();
}

describe("WF-04 Result entry and approval", () => {
  it("TC-WF04-M lets the tester enter and send a result, which completes their testing task, and the head approve it", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      cy.signInAs("tester");
      enterResult(test, "0.008");
      cy.signRecord();
      cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
      testingTasks(test).then((tasks) => expect(tasks.map((task) => task.status)).to.deep.equal(["done"]));
      cy.readRecord(test, ["status"]).its("status").should("eq", "result_entered");

      results(test).then(([result]) => {
        cy.signInAs("head_of_department");
        cy.openRecord(result);
        cy.signRecord();
        cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
        cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
        cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
      });
    });
  });

  it("TC-WF04-A2 lets the tester withdraw a sent result, which gives them back their testing task", () => {
    sentResult().then(({ test, result }) => {
      cy.signInAs("tester");
      cy.openRecord(result);
      cy.signRecord("action_withdraw");
      cy.get(`${ACTIONS} button[name=action_withdraw]`).should("not.exist");
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

  it("TC-WF04-E1 lets the head reject a result, which stays on record and opens a new testing task", () => {
    const reason = "Mẫu chuẩn kiểm tra đọc cao 15%, hiệu chuẩn lại máy AAS và đo lại.";
    sentResult().then(({ test, result }) => {
      cy.signInAs("head_of_department");
      cy.openRecord(result);
      cy.rejectRecord(reason);
      cy.readRecord(result, ["status"]).its("status").should("eq", "rejected");
      cy.readRecord(test, ["status"]).its("status").should("eq", "testing");
      testingTasks(test).then(([done, retest, ...others]) => {
        expect(others).to.be.empty;
        expect(done.status).to.equal("done");
        expect(retest.status).to.equal("open");
        expect(retest.assignee_id).to.equal(false);
        expect(retest.note).to.contain(reason);
      });

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
});
