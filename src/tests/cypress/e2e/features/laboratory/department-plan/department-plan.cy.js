import { callAs } from "../../../../support/odoo";
import {
  ADMINISTRATOR,
  assignedChromium,
  openBooking,
  releaseFixtures,
  resetFixtures,
} from "../../../flows/wf-03-testing-scheduling/setup";

const REASON = "Khách hàng cần kết quả gấp để thông quan.";

describe("Department plan", () => {
  beforeEach(() => {
    resetFixtures();
    cy.viewport(1440, 900);
  });
  afterEach(releaseFixtures);

  it("TC-F422-1 lets the tester accept the booking the plan proposes, which then reserves the machine and the calendar", () => {
    assignedChromium().then(({ test }) => {
      openBooking(test).then((proposed) => {
        expect(proposed.status).to.equal("proposed");
        expect(proposed.starts_at, "the plan placed it").to.be.a("string");
        expect(proposed.calendar_event_id, "a proposed slot reserves nothing").to.equal(false);
        cy.signInAs("tester");
        cy.visit(`/odoo/machine-schedule/${proposed.id}`);
        cy.intercept("POST", "**/medilab.machine.booking/action_accept").as("accepted");
        cy.get(".o_statusbar_buttons button[name=action_accept]").should("be.visible").click();
        cy.wait("@accepted").its("response.body.error").should("not.exist");
        cy.get(".o_statusbar_buttons button[name=action_accept]").should("not.exist");
        openBooking(test).should((scheduled) => {
          expect(scheduled.id).to.equal(proposed.id);
          expect(scheduled.status).to.equal("scheduled");
          expect([scheduled.starts_at, scheduled.ends_at]).to.deep.equal([proposed.starts_at, proposed.ends_at]);
          expect(scheduled.calendar_event_id).to.be.an("array");
        });
      });
    });
  });

  it("TC-F422-2 lets the tester mark their test urgent with a reason, which shows on the test", () => {
    assignedChromium().then(({ test }) => {
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.get(".o_statusbar_buttons button").contains("Mark Urgent").click();
      cy.get(".modal .o_field_widget[name=reason] textarea").type(REASON);
      cy.intercept("POST", "**/medilab.sample.test.urgent.mark/action_mark").as("marked");
      cy.get(".modal button[name=action_mark]").click();
      cy.wait("@marked").its("response.body.error").should("not.exist");
      cy.get(".o_field_widget[name=urgent_reason]").should("contain.text", REASON);
      callAs(ADMINISTRATOR, "medilab.sample.test", "read", [[test.id], ["priority", "marked_urgent"]]).then(([read]) => {
        expect([read.priority, read.marked_urgent]).to.deep.equal(["urgent", true]);
      });
    });
  });
});
