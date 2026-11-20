import { call, callAs, callRefused } from "../../../support/odoo";
import { orderAt } from "../wf-01-order-to-test-request/setup";
import { HEAD, TESTER, inEnglish, leadTest } from "./setup";

const REASON = "Máy AAS-01 bảo trì định kỳ; cần đo xong trước Tết Dương lịch.";
const CHANGE = ".o_form_view .o_statusbar_buttons button:contains('Change Due Date')";
// 10:00 on 1 January 2027 in the browser's time zone, which the form types dates in, as Odoo stores it.
const NEW_YEAR = new Date(2027, 0, 1, 10).toISOString().replace("T", " ").slice(0, 19);

describe("Result dates and priority orders", () => {
  inEnglish(HEAD, TESTER);
  beforeEach(() => leadTest().as("leadTest"));

  it("TC-SF07-A3 lets the head change a due date with a reason and reports that a public holiday is not a working day", () => {
    cy.signInAs("head_of_department");
    cy.get("@leadTest").then((test) => {
      cy.openRecord(test);
      cy.get(CHANGE).should("have.length", 1).click();
      cy.get(".modal:visible").last().within(() => {
        // Tết Dương lịch, a public holiday of the demo company calendar.
        cy.get(".o_field_widget[name=due_date] input").clear().type("01/01/2027 10:00:00{enter}");
        cy.contains(".alert-warning", "not a working day").should("be.visible");
        cy.get(".o_field_widget[name=reason] textarea").type(REASON);
        cy.get("button[name=action_change]").click();
      });
      cy.get(".modal").should("not.exist");
      cy.contains(".o_form_view .alert-warning", "not a working day").should("be.visible");
      cy.contains(".o_field_widget[name=due_date_reason]", REASON);
      cy.readRecord(test, ["due_date", "due_date_reason"]).should("deep.include", {
        due_date: NEW_YEAR,
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

  it("TC-SF07-M shows the standard turnaround and commits a requested date it meets", () => {
    orderAt("claimed").then((order) => {
      cy.signInAs("sales");
      callAs("demo.sales", "sale.order", "write", [[order.id], { requested_date: inDays(60) }]);
      cy.openRecord(order);
      cy.get(".o_field_widget[name=turnaround_days]").invoke("text").should("match", /[1-9]/);
      cy.get(".o_field_widget[name=estimated_result_date]").should("not.be.empty");
      callAs("demo.sales", "sale.order", "write", [[order.id], { advance_method: "cash", advance_mode: "full" }]);
      callAs("demo.sales", "sale.order", "action_send_quotation", [[order.id]]);
      cy.readRecord(order, ["requested_date", "committed_date"]).then((read) =>
        expect(read.committed_date).to.equal(read.requested_date),
      );
    });
  });

  it("TC-SF07-A1 keeps a portal priority request a request until Sales decides it", () => {
    orderAt("claimed").then((order) => {
      callAs("demo.sales", "sale.order", "write", [
        [order.id],
        { requested_date: inDays(1), priority_request: "requested", advance_method: "cash", advance_mode: "full" },
      ]);
      cy.signInAs("sales");
      callRefused("sale.order", "action_send_quotation", [[order.id]]).should("match", /priority|ưu tiên/i);
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_decline_priority]:visible").click();
      cy.readRecord(order, ["priority_request", "priority"]).should("deep.include", {
        priority_request: "declined",
        priority: false,
      });
    });
  });
});

// The day the given number of days from now in the laboratory, as Odoo stores a date.
function inDays(days) {
  return new Date(Date.now() + days * 86400000).toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });
}
