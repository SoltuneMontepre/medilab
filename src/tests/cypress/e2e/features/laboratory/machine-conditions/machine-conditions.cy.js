import { callAs } from "../../../../support/odoo";
import { ADMIN, odooTime, release, schedulingFixture } from "../scheduling/setup";

const HOUR = 3600000;

describe("Machine conditions", () => {
  let fixture;
  let overrun;
  beforeEach(() => {
    fixture = undefined;
    overrun = undefined;
    // Two tests booked on the fixture's machine; the first one's booking is replaced by a measurement that started two
    // hours ago and whose end passed an hour ago without a result.
    return schedulingFixture(2, (created) => (fixture = created)).then(() =>
      callAs(ADMIN, "medilab.machine.booking", "action_cancel", [[fixture.bookings[0]]])
        .then(() => callAs(ADMIN, "medilab.machine.booking", "read", [[fixture.bookings[0]], ["task_id", "person_id"]]))
        .then(([cancelled]) =>
          callAs(ADMIN, "medilab.machine.booking", "create", [{
            machine_id: fixture.machine,
            sample_test_id: fixture.tests[0],
            task_id: cancelled.task_id[0],
            person_id: cancelled.person_id[0],
            starts_at: odooTime(Date.now() - 2 * HOUR),
            ends_at: odooTime(Date.now() - HOUR),
            status: "in_progress",
          }]),
        )
        .then((id) => (overrun = id)),
    );
  });
  afterEach(() => {
    if (overrun) callAs(ADMIN, "medilab.machine.booking", "action_done", [[overrun]]);
    return release(fixture);
  });

  it("TC-F424-1 warns the tester that an overrun holds the machine and puts the next booking at risk", () => {
    cy.signInAs("tester");
    cy.visit(`/odoo/machine-schedule/${overrun}`);
    cy.get(".o_form_view .alert-warning").should("contain", "end has passed");
    cy.visit(`/odoo/machine-schedule/${fixture.bookings[1]}`);
    cy.get(".o_form_view .alert-warning").should("contain", "At risk").and("contain", "past its end");
    callAs(ADMIN, "medilab.machine.booking", "read", [[fixture.bookings[1]], ["status"]]).then(([next]) => {
      expect(next.status, "nothing moves by itself").to.equal("scheduled");
    });
  });
});
