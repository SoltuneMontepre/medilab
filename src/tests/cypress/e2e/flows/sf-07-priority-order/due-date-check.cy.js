import { call, callRefused } from "../../../support/odoo";
import { assignedChromium, releaseFixtures, resetFixtures } from "../wf-03-testing-scheduling/setup";
import { HEAD, TESTER, inEnglish } from "./setup";

const REASON = "Khách hàng cần kết quả trong buổi sáng; giữ ngày này dù máy chưa kịp.";
const CHANGE = ".o_form_view .o_statusbar_buttons button:contains('Change Due Date')";
const FIVE_MINUTES = 5 * 60000;

// Five minutes from now as the English form types it, in the browser's time zone: no machine finishes a test by then.
function soonTyped() {
  const soon = new Date(Date.now() + FIVE_MINUTES);
  const two = (number) => String(number).padStart(2, "0");
  const time = `${two(soon.getHours())}:${two(soon.getMinutes())}:${two(soon.getSeconds())}`;
  return `${two(soon.getMonth() + 1)}/${two(soon.getDate())}/${soon.getFullYear()} ${time}`;
}

// Five minutes from now as Odoo stores it.
function soonStored() {
  return new Date(Date.now() + FIVE_MINUTES).toISOString().slice(0, 19).replace("T", " ");
}

describe("Due date check", () => {
  inEnglish(HEAD, TESTER);
  beforeEach(() => {
    resetFixtures();
    cy.viewport(1440, 900);
  });
  afterEach(releaseFixtures);

  it("TC-F179-1 shows the head why a due date cannot be met and the earliest feasible date, and keeps it at risk with a reason", () => {
    assignedChromium().then(({ test }) => {
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      cy.get(CHANGE).should("have.length", 1).click();
      cy.get(".modal:visible").last().within(() => {
        cy.get(".o_field_widget[name=due_date] input").clear().type(`${soonTyped()}{enter}`);
        cy.contains(".alert-danger", "The laboratory cannot meet this date").should("be.visible");
        cy.get(".alert-danger").should("contain.text", "after the due date").and("contain.text", "Earliest feasible date");
        // An unmeetable date is kept only on purpose: the plain change is not offered.
        cy.get("button[name=action_change]").should("not.exist");
        cy.get(".o_field_widget[name=reason] textarea").type(REASON);
        cy.intercept("POST", "**/medilab.sample.test.due.date.change/action_keep_at_risk").as("kept");
        cy.get("button[name=action_keep_at_risk]").click();
      });
      cy.wait("@kept").its("response.body.error").should("not.exist");
      cy.get(".modal").should("not.exist");
      cy.contains(".o_form_view .alert-danger", "at risk of missing its internal due date").should("be.visible");
      cy.contains(".o_field_widget[name=due_date_reason]", REASON);
      cy.readRecord(test, ["due_date_reason", "at_risk"]).should("deep.include", { due_date_reason: REASON, at_risk: true });
    });
  });

  it("TC-F179-2 refuses a due date no resource can meet unless the head keeps it at risk, and refuses a tester", () => {
    assignedChromium().then(({ test }) => {
      const values = { sample_test_id: test.id, due_date: soonStored(), reason: REASON };
      cy.signInAs("head_of_department");
      cy.readRecord(test, ["due_date"]).then(({ due_date: before }) => {
        call("medilab.sample.test.due.date.change", "create", [values]).then((wizard) => {
          callRefused("medilab.sample.test.due.date.change", "action_change", [[wizard]]).should("contain", "cannot meet this due date");
        });
        cy.signInAs("tester");
        call("medilab.sample.test.due.date.change", "create", [values]).then((wizard) => {
          callRefused("medilab.sample.test.due.date.change", "action_keep_at_risk", [[wizard]]).should("contain", "Only the head of the department testing");
        });
        cy.readRecord(test, ["due_date", "due_date_reason"]).should("deep.include", { due_date: before, due_date_reason: false });
      });
    });
  });
});
