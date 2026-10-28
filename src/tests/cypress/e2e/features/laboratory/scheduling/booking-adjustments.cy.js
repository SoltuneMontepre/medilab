import { call, callRefused } from "../../../../support/odoo";
import { pick, save } from "../../../../support/form";
import { milliseconds, odooTime, release, schedulingFixture, snapshot, typeStart } from "./setup";

describe("WF-03 booking adjustments", () => {
  let fixture;
  beforeEach(() => schedulingFixture().then((created) => (fixture = created)));
  afterEach(() => release(fixture));

  it("TC-F24-03 keeps every reservation after a conflicting UI move and saves a valid retry on the same form", () => {
    snapshot(fixture).then((before) => {
      const [taken, booking] = before.bookings;
      const valid = odooTime(milliseconds(booking.starts_at) + 3600000);
      cy.signInAs("tester");
      cy.visit(`/odoo/machine-schedule/${booking.id}`);
      cy.get('.o_field_widget[name="starts_at"]').should("not.have.class", "o_readonly_modifier");
      typeStart(taken.starts_at);
      cy.expectRefusal({
        read: () => snapshot(fixture),
        action: () => cy.get(".o_form_button_save").click(),
        message: `${booking.machine_id[1]} is not free`,
      });
      cy.contains(".o_error_dialog .modal-footer button", "Close").click();
      typeStart(valid);
      save();
      snapshot(fixture).then((after) => {
        const moved = after.bookings.find((row) => row.id === booking.id);
        const task = after.tasks.find((row) => row.id === booking.task_id[0]);
        const previousEvents = before.events.filter((event) => event.id === booking.calendar_event_id[0] || booking.room_event_ids.includes(event.id));
        expect(after.activeBookings).to.deep.equal(before.activeBookings);
        expect(after.tests).to.deep.equal(before.tests);
        expect(after.bookings.find((row) => row.id === taken.id)).to.deep.equal(taken);
        expect(moved.status).to.equal("scheduled");
        ["sample_test_id", "task_id", "machine_id", "person_id"].forEach((field) => expect(moved[field]).to.deep.equal(booking[field]));
        expect(moved.starts_at).to.equal(valid);
        expect(milliseconds(moved.ends_at) - milliseconds(moved.starts_at)).to.equal(milliseconds(booking.ends_at) - milliseconds(booking.starts_at));
        expect(moved.room_event_ids).to.deep.equal(booking.room_event_ids);
        expect(moved.calendar_event_id).to.deep.equal(booking.calendar_event_id);
        expect(task.planned_start).to.equal(moved.starts_at);
        expect(task.planned_end).to.equal(moved.ends_at);
        expect(after.events).to.have.length(before.events.length);
        previousEvents.forEach((event) => {
          const changed = after.events.find((row) => row.id === event.id);
          expect(milliseconds(changed.start) - milliseconds(event.start)).to.equal(3600000);
          expect(milliseconds(changed.stop) - milliseconds(event.stop)).to.equal(3600000);
          expect(changed.partner_ids).to.deep.equal(event.partner_ids);
          expect(changed.machine_booking_id).to.deep.equal(event.machine_booking_id);
          expect(changed.location_id).to.deep.equal(event.location_id);
        });
      });
    });
  });

  it("TC-F24-03 hides another tester's booking and refuses a forged move without changing related records", () => {
    snapshot(fixture).then((before) => {
      const [booking] = before.bookings;
      cy.signInAs("chemistry_tester");
      cy.visit("/odoo/machine-schedule?view_type=list");
      cy.get(".o_list_renderer").should("not.contain", fixture.tag);
      callRefused("medilab.machine.booking", "write", [[booking.id], { starts_at: booking.starts_at }])
        .should("contain", "doesn't have 'read' access")
        .and("contain", "Machine Booking");
      snapshot(fixture).should("deep.equal", before);
    });
  });
});

// These assertions describe PR #373's proposed retained-read contract, whose access-policy decision remains open.
describe("PR #373 proposed department-transfer contract", () => {
  let fixture;
  beforeEach(() => schedulingFixture(1).then((created) => (fixture = created)));
  afterEach(() => release(fixture));

  it("TC-F23-03 retries a missing transfer reason from the task form and keeps the moved task read-only", () => {
    const reason = "Microbiology will continue the sample's work.";
    snapshot(fixture).then((before) => {
      cy.signInAs("head_of_department");
      cy.openRecord({ model: "medilab.task", id: fixture.tasks[0] });
      cy.contains(".o_statusbar_buttons button", /^Assign$/).click();
      pick("department_id", "Microbiology");
      cy.get('.modal .o_field_widget[name="assignee_id"] input').should("have.value", "");
      cy.get('.modal button[name="action_confirm"]').click();
      cy.get('.modal .o_field_widget[name="reason"]').should("have.class", "o_field_invalid");
      snapshot(fixture).should("deep.equal", before);
      cy.get('.modal .o_field_widget[name="reason"] textarea').type(reason);
      cy.get('.modal button[name="action_confirm"]').click();
      cy.get(".modal").should("not.exist");
      cy.get(".o_error_dialog").should("not.exist");
      cy.get(".o_form_view").should("contain", "Microbiology");
      cy.get('button[name="action_assign_sample"]:visible').should("not.exist");
      cy.get('button[name="action_cancel"]:visible').should("not.exist");
      cy.get('.o_field_widget[name="note"] textarea').should("not.exist");
      call("medilab.task", "read", [[fixture.tasks[0]], ["can_edit", "department_id", "status", "assignee_id", "moved_out_by_ids"]]).then(([task]) => {
        expect(task.can_edit).to.equal(false);
        expect(task.department_id[1]).to.equal("Microbiology");
        expect(task.status).to.equal("open");
        expect(task.assignee_id).to.equal(false);
        expect(task.moved_out_by_ids).to.include(fixture.head);
      });
      snapshot(fixture).then((after) => {
        expect(after.activeBookings).to.be.empty;
        expect(after.events).to.be.empty;
        expect(after.bookings[0].status).to.equal("cancelled");
        expect(after.bookings[0].calendar_event_id).to.equal(false);
        expect(after.bookings[0].room_event_ids).to.be.empty;
        expect(after.tasks[0].reassign_reason).to.equal(reason);
        expect(after.tasks[0].planned_start).to.equal(false);
        expect(after.tasks[0].planned_end).to.equal(false);
        expect(after.tests[0].status).not.to.equal("cancelled");
      });
    });
  });
});
