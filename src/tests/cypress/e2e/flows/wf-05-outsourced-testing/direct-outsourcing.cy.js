import { step } from "../../../support/steps";
import { callAs, callRefused, refAs } from "../../../support/odoo";
import { ACTIONS, ADMINISTRATOR, PARAMETERS, REASON, TESTER, assignedTest, openOutsource, outsourceDialog } from "./setup";

describe("F-39 Direct outsourcing", () => {
  it("TC-F39-02 refuses to outsource a test with another method than the one the customer accepted → it keeps its accepted way", () => {
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

  it("TC-F39-03 refuses outsourcing straight away without a reason, or a test already in testing", () => {
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
});
