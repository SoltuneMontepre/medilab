import { callAs } from "../../../support/odoo";
import { save } from "../../../support/form";
import { formTime, milliseconds, typeTime } from "../../features/laboratory/scheduling/setup";
import { displayZone, dragBookingToSlot, wallClock } from "./screens";
import { eventsGone, scheduleState } from "./state";
import { HEAD, TESTER, awayFromQuarterHour, bookedOnOneMachine, book, assignedChromium, releaseFixtures, resetFixtures } from "./setup";

beforeEach(() => {
  resetFixtures();
  // Tall enough for the calendar to show the whole day, so a drag never needs it to scroll.
  cy.viewport(1440, 1800);
});
afterEach(releaseFixtures);

// Two tests booked one after the other on the machine; the second's booking is cancelled, which leaves its slot free.
function bookingWithFreeSlot() {
  awayFromQuarterHour();
  return bookedOnOneMachine().then(([booking, later]) => {
    callAs(TESTER, "medilab.machine.booking", "action_cancel", [[later.id]]);
    return cy.then(() => ({ booking, slot: later.starts_at, test: { model: "medilab.sample.test", id: booking.sample_test_id[0] } }));
  });
}

// The booking starts at the slot with the same machine, person, test and length, and its events moved by the same time.
function expectMovedTogether(before, after, slot) {
  const [was] = before.bookings;
  const [moved] = after.bookings;
  const movedBy = milliseconds(slot) - milliseconds(was.starts_at);
  expect(after.bookings).to.have.length(1);
  expect(moved.status).to.equal("scheduled");
  ["sample_test_id", "task_id", "machine_id", "person_id", "calendar_event_id", "room_event_ids"].forEach((field) =>
    expect(moved[field], field).to.deep.equal(was[field]),
  );
  expect(moved.starts_at).to.equal(slot);
  expect(milliseconds(moved.ends_at) - milliseconds(moved.starts_at)).to.equal(milliseconds(was.ends_at) - milliseconds(was.starts_at));
  expect(after.tasks[0].planned_start).to.equal(moved.starts_at);
  expect(after.tasks[0].planned_end).to.equal(moved.ends_at);
  expect(after.events).to.have.length(before.events.length);
  expect(after.events.length, "the tester's event and the room's").to.equal(1 + was.room_event_ids.length);
  before.events.forEach((event) => {
    const changed = after.events.find((row) => row.id === event.id);
    expect(milliseconds(changed.start) - milliseconds(event.start)).to.equal(movedBy);
    expect(milliseconds(changed.stop) - milliseconds(event.stop)).to.equal(movedBy);
    expect(changed.partner_ids).to.deep.equal(event.partner_ids);
    expect(changed.location_id).to.deep.equal(event.location_id);
  });
}

// The Monday-based week of a moment on the calendar of the zone.
// The week of a moment on the calendar of the zone, for a week that starts on Monday (offset 3) or Sunday (offset 4).
const weekOf = (value, zone, offset) =>
  Math.floor((Date.parse(`${wallClock(value, zone).date}T00:00:00Z`) / 86400000 + offset) / 7);
const sameWeek = (first, second, zone) => [3, 4].every((offset) => weekOf(first, zone, offset) === weekOf(second, zone, offset));

// The booking in the calendar week of the other booking: when the other fell into a later week, the booking moves to
// right after it, so a drag between them stays in one week of the calendar.
function inWeekOf(booking, other, zone) {
  if (sameWeek(booking.starts_at, other.starts_at, zone)) {
    return cy.wrap(booking);
  }
  callAs(HEAD, "medilab.machine.booking", "write", [[booking.id], { starts_at: other.ends_at }]);
  return callAs(HEAD, "medilab.machine.booking", "read", [[booking.id], Object.keys(booking).filter((key) => key !== "model")]).then(([moved]) => moved);
}

describe("SF-10 the head moves and cancels a department booking", () => {
  it("TC-SF10-A2 partial lets the head move a scheduled booking to a free slot and moves its reservations together", () => {
    bookingWithFreeSlot().then(({ booking, slot, test }) => {
      const movedBy = milliseconds(slot) - milliseconds(booking.starts_at);
      expect(movedBy, "the free slot lies after the booking").to.be.greaterThan(0);
      displayZone(HEAD).then((zone) =>
        scheduleState([test]).then((before) => {
          cy.signInAs("head_of_department");
          cy.visit(`/odoo/machine-schedule/${booking.id}`);
          cy.get('.o_field_widget[name="starts_at"]').should("not.have.class", "o_readonly_modifier");
          typeTime(slot, zone);
          const duration = milliseconds(booking.ends_at) - milliseconds(booking.starts_at);
          const movedEnd = new Date(milliseconds(slot) + duration).toISOString().replace("T", " ").slice(0, 19);
          cy.get('.o_field_widget[name="ends_at"]').should(($field) => {
            const shown = $field.find("input").val() || $field.text();
            expect(String(shown).trim()).to.include(formTime(movedEnd, zone).slice(0, 16));
          });
          cy.intercept("POST", "/web/dataset/call_kw/medilab.machine.booking/web_save").as("savedBooking");
          save();
          cy.wait("@savedBooking").its("response.body.error").should("not.exist");
          scheduleState([test]).should((after) => expectMovedTogether(before, after, slot));
        }),
      );
    });
  });

  it("TC-SF10-A2 partial lets the head cancel a booking, which leaves the sample test assigned and open to scheduling", () => {
    assignedChromium().then(({ test }) => {
      awayFromQuarterHour();
      book(test).then((booking) => {
        const eventIds = [booking.calendar_event_id[0], ...booking.room_event_ids];
        cy.signInAs("head_of_department");
        cy.visit(`/odoo/machine-schedule/${booking.id}`);
        cy.intercept("POST", "**/medilab.machine.booking/action_cancel").as("cancelledByHead");
        cy.get(".o_statusbar_buttons button[name=action_cancel]").click();
        cy.wait("@cancelledByHead").its("response.body.error").should("not.exist");
        cy.get(".o_statusbar_buttons button[name=action_cancel]").should("not.exist");
        scheduleState([test]).should((after) => {
          const cancelled = after.bookings.find((row) => row.id === booking.id);
          expect(cancelled.status).to.equal("cancelled");
          expect(cancelled.calendar_event_id).to.equal(false);
          expect(cancelled.room_event_ids).to.be.empty;
          // The cancelled slot goes back to the department's plan, which proposes another and reserves nothing.
          expect(after.bookings.filter((row) => row.id !== booking.id).map((row) => row.status)).to.deep.equal(["proposed"]);
          expect(after.tasks[0].planned_start).to.equal(false);
          expect(after.tasks[0].planned_end).to.equal(false);
          expect(after.tasks[0].status).to.equal("assigned");
          expect(after.tests[0].status).to.equal("assigned");
          expect(after.events).to.be.empty;
        });
        eventsGone(eventIds);
        cy.openRecord(test);
        cy.get(".o_statusbar_buttons button[name=action_approve_booking]").should("be.visible");
      });
    });
  });

  it("TC-SF10-A2 partial lets the head drag a booking to a free slot in the calendar and moves its reservations together", () => {
    bookingWithFreeSlot().then(({ booking, slot, test }) =>
      displayZone(HEAD).then((zone) =>
        scheduleState([test]).then((before) => {
          cy.signInAs("head_of_department");
          cy.intercept("POST", "/web/dataset/call_kw/medilab.machine.booking/write").as("droppedBooking");
          dragBookingToSlot(booking, slot, zone);
          cy.wait("@droppedBooking").its("response.body.error").should("not.exist");
          scheduleState([test]).should((after) => expectMovedTogether(before, after, slot));
        }),
      ),
    );
  });

  it("TC-SF10-A2 partial refuses a calendar drop onto the slot of another booking of the machine and keeps both bookings", () => {
    awayFromQuarterHour();
    bookedOnOneMachine().then(([first, taken]) =>
      displayZone(HEAD).then((zone) => inWeekOf(first, taken, zone).then((booking) => {
        const test = { model: "medilab.sample.test", id: booking.sample_test_id[0] };
        const takenTest = { model: "medilab.sample.test", id: taken.sample_test_id[0] };
        cy.signInAs("head_of_department");
        cy.expectRefusal({
          read: () => scheduleState([test, takenTest]),
          action: () => dragBookingToSlot(booking, taken.starts_at, zone),
          message: `${booking.machine_id[1]} is not free for ${booking.display_name} at that time.`,
        });
      })),
    );
  });
});
