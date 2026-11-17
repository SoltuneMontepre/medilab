import { callAs } from "../../../support/odoo";
import { HEAD, releaseFixtures, resetFixtures } from "./setup";
import { RUN, cancelTests, currentBooking, dueAt, milliseconds, movesOf, openRevision, recordOvertime, urgentNeedsScheduledSlots } from "./revision-setup";

beforeEach(() => {
  resetFixtures();
  cy.viewport(1440, 900);
});
afterEach(() => {
  releaseFixtures();
  cancelTests();
});

// The rows of the revision form that move a booking of the scenario's parameter.
function rowsOfScenario(scenario) {
  return cy.get(".o_field_one2many .o_data_row").filter(`:contains("${scenario.made.parameterName}")`);
}

function approveThroughScreen() {
  cy.intercept("POST", "**/medilab.plan.revision/action_approve").as("approvedRevision");
  cy.get(".o_statusbar_buttons button[name=action_approve]").should("be.visible").and("be.enabled").click();
  cy.wait("@approvedRevision").its("response.body.error").should("not.exist");
  cy.get(".o_statusbar_buttons button[name=action_approve]").should("not.exist");
  cy.get(".o_statusbar_status .o_arrow_button_current").should("contain.text", "Applied");
}

// Z moved to Y's interval, Y to the OverTime after it, and X took Z's interval; nobody passes the due date.
function expectMovedForUrgentWork(scenario) {
  const { x, y, z, zBooking, yBooking, due } = scenario;
  currentBooking(z).should((booking) => {
    expect(booking.status).to.equal("scheduled");
    expect(booking.starts_at).to.equal(yBooking.starts_at);
    expect(milliseconds(booking.ends_at)).to.be.at.most(due);
  });
  currentBooking(y).should((booking) => {
    expect(booking.status).to.equal("scheduled");
    expect(booking.starts_at).to.equal(yBooking.ends_at);
    expect(milliseconds(booking.ends_at)).to.be.at.most(due);
  });
  currentBooking(x).should((booking) => {
    expect(booking.status).to.equal("proposed");
    expect(booking.starts_at).to.equal(zBooking.starts_at);
  });
}

describe("SF-10 the head approves a plan revision", () => {
  it("TC-SF10-E1 moves the bookings that hold the urgent work's slots and applies them together", () => {
    urgentNeedsScheduledSlots({ roomForTheMoves: true }).then((scenario) => {
      // The OverTime the head recorded gives the moved bookings a place before their due date.
      recordOvertime(scenario.made, milliseconds(scenario.yBooking.ends_at));
      openRevision().then((revision) => {
        movesOf(revision).then((moves) => {
          const ours = moves.filter(({ booking_id: [id] }) => [scenario.zBooking.id, scenario.yBooking.id].includes(id));
          expect(ours.map(({ status }) => status)).to.deep.equal(["proposed", "proposed"]);
        });
        cy.signInAs("head_of_department");
        cy.visit(`/odoo/plan-revisions/${revision.id}`);
        rowsOfScenario(scenario).should("have.length", 2).each(($row) => expect($row.text()).to.contain("Proposed"));
        approveThroughScreen();
      });
      expectMovedForUrgentWork(scenario);
    });
  });

  it("TC-SF10-E2 holds back a move that would pass its due date until the head frees capacity with OverTime", () => {
    urgentNeedsScheduledSlots().then((scenario) => {
      // Both moves would pass the due date, so both bookings keep their slots and the revision only lists the moves.
      openRevision().then((revision) => {
        cy.signInAs("head_of_department");
        cy.visit(`/odoo/plan-revisions/${revision.id}`);
        rowsOfScenario(scenario).should("have.length", 2).each(($row) => expect($row.text()).to.contain("Held Back"));
      });
      currentBooking(scenario.z).its("starts_at").should("equal", scenario.zBooking.starts_at);
      currentBooking(scenario.y).its("starts_at").should("equal", scenario.yBooking.starts_at);

      // Freeing capacity needs no customer: with OverTime, and the same dates, the recalculated revision can be approved.
      const due = milliseconds(scenario.yBooking.ends_at) + RUN;
      [scenario.z, scenario.y, scenario.x].forEach((test) => dueAt(test, due));
      recordOvertime(scenario.made, milliseconds(scenario.yBooking.ends_at));
      openRevision().then((revision) => {
        cy.visit(`/odoo/plan-revisions/${revision.id}`);
        rowsOfScenario(scenario).should("have.length", 2).each(($row) => expect($row.text()).to.contain("Proposed"));
        approveThroughScreen();
      });
      expectMovedForUrgentWork({ ...scenario, due });
    });
  });
});
