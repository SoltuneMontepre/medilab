import { save } from "../../../support/form";
import { callRefused, refAs } from "../../../support/odoo";
import { TESTER, assignedTest, results, sentResult, testingTasks } from "./setup";

const ACTIONS = ".o_form_view .o_statusbar_buttons";
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
      cy.get(".o_field_widget[name=conclusion]").should("not.exist");
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

  it("TC-WF04-A1 lets the tester confirm the suggested text for a value below the LOD, keeping the measured value", () => {
    assignedTest("lead", { days: 7, sample: COMPARED_WATER }).then((test) => {
      cy.signInAs("tester");
      enterResult(test, "0.003");
      results(test).then(([result]) => {
        cy.readRecord(result, ["lod", "unit_id"]).then(({ lod, unit_id: [, unit] }) => {
          const text = `<${lod} ${unit} (below LOD)`;
          cy.get(".o_field_widget[name=value_suggestion]").should("have.text", text);
          cy.get("button[name=action_use_value_suggestion]").click();
          cy.get(".o_field_widget[name=value_text] input").should("have.value", text);
          cy.get(".o_field_widget[name=value_suggestion]").should("not.exist");
          cy.readRecord(result, ["value", "value_text", "conclusion"]).should("deep.include", {
            value: 0.003,
            value_text: text,
            conclusion: false,
          });
        });
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
      cy.signInAs("tester");
      enterResult(test, "0.12");
      cy.contains(".o_form_view .alert-warning", "can only be assessed as insufficient basis").should("be.visible");
      results(test).then(([result]) => {
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
});
