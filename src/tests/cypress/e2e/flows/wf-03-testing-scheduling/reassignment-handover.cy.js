import { search } from "../../../support/form";
import { callAs } from "../../../support/odoo";
import { reassign } from "./screens";
import { scheduleState } from "./state";
import { HEAD, PEOPLE, assignedChromium, awayFromQuarterHour, book, releaseFixtures, resetFixtures } from "./setup";

const REASON = "Ly Van Hung is available for this analysis.";

beforeEach(() => {
  resetFixtures();
  cy.viewport(1440, 900);
});
afterEach(releaseFixtures);

describe("WF-03 the receiving side of a reassignment", () => {
  it("TC-WF03-E1 partial shows the moved task and its booking to the new assignee and no longer to the previous one", () => {
    assignedChromium().then(({ sample, test }) => {
      awayFromQuarterHour();
      book(test).then((booking) => {
        reassign(test.task, PEOPLE.chemistryTester, REASON);
        // The booking returns to the plan for the new assignee, and the head approves its new slot.
        scheduleState([test]).should((state) => {
          expect(state.tasks[0].assignee_id[1]).to.equal("Ly Van Hung");
          expect(state.tasks[0].reassign_reason).to.equal(REASON);
          expect(state.bookings).to.have.length(1);
          expect(state.bookings[0].status).to.equal("proposed");
          expect(state.bookings[0].person_id[1]).to.equal("Ly Van Hung");
        });
        callAs(HEAD, "medilab.machine.booking", "action_accept", [[booking.id]]);
        scheduleState([test]).should((state) => {
          expect(state.bookings.map((row) => [row.status, row.person_id[1]])).to.deep.equal([["scheduled", "Ly Van Hung"]]);
        });

        cy.signInAs("chemistry_tester");
        cy.visit("/odoo/my-tasks");
        search(sample.code);
        cy.contains(".o_data_row", test.task.name).should("be.visible");
        cy.visit("/odoo/machine-schedule?view_type=list");
        search(booking.machine_id[1], { field: "Machine" });
        cy.contains(".o_data_row", sample.code).should("be.visible").and("contain", "Ly Van Hung");

        cy.signInAs("tester");
        cy.visit("/odoo/my-tasks");
        search(sample.code);
        cy.get(".o_list_renderer").should("not.contain", test.task.name);
        cy.visit("/odoo/machine-schedule?view_type=list");
        search(booking.machine_id[1], { field: "Machine" });
        cy.get(".o_list_renderer").should("not.contain", sample.code);
      });
    });
  });
});
