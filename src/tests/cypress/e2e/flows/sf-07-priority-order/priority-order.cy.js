import { call, callRefused } from "../../../support/odoo";
import { HEAD, TESTER, inEnglish, leadTest } from "./setup";

const REASON = "Máy AAS-01 bảo trì định kỳ; cần đo xong trước Tết Dương lịch.";
const CHANGE = ".o_form_view .o_statusbar_buttons button:contains('Change Due Date')";

describe("Result dates and priority orders", () => {
  inEnglish(HEAD, TESTER);
  beforeEach(() => leadTest().as("leadTest"));

  it("TC-SF07-A3 lets the head change a due date with a reason and reports that a public holiday is not a working day", () => {
    cy.signInAs("head_of_department");
    cy.get("@leadTest").then((test) => {
      cy.openRecord(test);
      cy.get(CHANGE).should("have.length", 1).click();
      cy.get(".modal:visible").last().within(() => {
        // Tết Dương lịch, a public holiday of the demo company calendar, at 10:00 in Vietnam.
        cy.get(".o_field_widget[name=due_date] input").clear().type("01/01/2027 10:00:00{enter}");
        cy.contains(".alert-warning", "not a working day").should("be.visible");
        cy.get(".o_field_widget[name=reason] textarea").type(REASON);
        cy.get("button[name=action_change]").click();
      });
      cy.get(".modal").should("not.exist");
      cy.contains(".o_form_view .alert-warning", "not a working day").should("be.visible");
      cy.contains(".o_field_widget[name=due_date_reason]", REASON);
      cy.readRecord(test, ["due_date", "due_date_reason"]).should("deep.include", {
        due_date: "2027-01-01 03:00:00",
        due_date_reason: REASON,
      });
    });
  });

  it("TC-SF07-A3 does not let a tester change a due date", () => {
    cy.signInAs("tester");
    cy.get("@leadTest").then((test) => {
      cy.openRecord(test);
      cy.get(CHANGE).should("not.exist");
      call("medilab.sample.test.due.date.change", "create", [
        { sample_test_id: test.id, due_date: "2027-01-04 03:00:00", reason: "Sớm hơn một ngày" },
      ])
        .then((wizard) => callRefused("medilab.sample.test.due.date.change", "action_change", [[wizard]]))
        .should("contain", "Only the head of the department testing");
      cy.readRecord(test, ["due_date_reason"]).its("due_date_reason").should("eq", false);
    });
  });
});
