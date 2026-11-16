import { callAs, refAs } from "../../../support/odoo";
import { ADMINISTRATOR, HEAD } from "./setup";

// The head moves a task to another person with a reason through the assign wizard, as its dialog does.
export function reassign(task, person, reason) {
  const context = { active_ids: [task.id] };
  return refAs(HEAD, person)
    .then(({ id }) => callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: id, reason }], { context }))
    .then((wizard) => callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }));
}

// The time zone in which the screens of a user show times.
export function displayZone(login) {
  return callAs(ADMINISTRATOR, "res.users", "search_read", [[["login", "=", login]]], { fields: ["tz"] }).then(([user]) => {
    expect(user.tz, `the display timezone of ${login}`).to.be.a("string").and.not.be.empty;
    return user.tz;
  });
}

// Opens the cancel dialog from the sample test form.
export function openCancelTest() {
  cy.contains(".o_statusbar_buttons button", /^Cancel Test$/).click();
  cy.get(".modal .o_field_widget[name=reason] textarea").should("be.visible");
}

// The sample test as the cancel dialog records it.
export function cancellation(test) {
  return callAs(ADMINISTRATOR, "medilab.sample.test", "read", [[test.id], ["status", "cancel_reason", "cancelled_by_id", "cancelled_at"]]).then(
    ([read]) => read,
  );
}

// The date and time on a user's clock for an Odoo UTC value, as the calendar labels its days and slots.
function wallClock(value, zone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(`${value}Z`));
  const clock = Object.fromEntries(parts.map(({ type, value: part }) => [type, part]));
  return { date: `${clock.year}-${clock.month}-${clock.day}`, time: `${clock.hour}:${clock.minute}:00` };
}

const SCROLLED_SLOT_OFFSET = 100;

// The vertical position of a clock time inside the rendered lane that contains it. The machine schedule keeps
// FullCalendar's slotMinTime of 00:00:00 and slotDuration of 00:30:00, and snaps a drop to 15 minutes, so a booking
// can start halfway through a lane. The pointer stays inside that lane, at the offset of the requested time.
function pointInLanes(clock) {
  const [hour, minute] = clock.time.split(":").map(Number);
  const wanted = hour * 60 + minute;
  const lanes = [...Cypress.$(".fc-timegrid-slot-lane")]
    .map((lane) => {
      const [laneHour, laneMinute] = lane.getAttribute("data-time").split(":").map(Number);
      return { lane, minutes: laneHour * 60 + laneMinute };
    })
    .filter((lane) => Number.isFinite(lane.minutes))
    .sort((left, right) => left.minutes - right.minutes);
  const chosen = lanes.filter((lane) => lane.minutes <= wanted).at(-1);
  if (!chosen) {
    throw new Error(`The calendar has no lane for ${clock.time}.`);
  }
  const following = lanes.find((lane) => lane.minutes > chosen.minutes);
  const span = following ? following.minutes - chosen.minutes : 30;
  const box = chosen.lane.getBoundingClientRect();
  return { lane: chosen.lane, clientY: box.top + (box.height * (wanted - chosen.minutes)) / span };
}

// Opens the Machine Schedule calendar on the week of a booking and drags the booking from its start to the slot.
// FullCalendar reads pageX and pageY, and Cypress must not scroll the calendar, which would move the slots under the pointer.
export function dragBookingToSlot(booking, slot, zone) {
  const from = wallClock(booking.starts_at, zone);
  const to = wallClock(slot, zone);
  cy.visit("/odoo/machine-schedule?view_type=calendar");
  cy.get(".fc-col-header-cell[data-date]")
    .first()
    .invoke("attr", "data-date")
    .then((weekStart) => {
      const weeks = Math.floor((Date.parse(`${from.date}T00:00:00Z`) - Date.parse(`${weekStart}T00:00:00Z`)) / (7 * 86400000));
      Cypress._.times(weeks, () => cy.get(".o_calendar_button_next").click());
    });
  // The booking's slot goes to the upper part of the calendar's own scroller, away from the edges where a drag scrolls it,
  // as far as the scroller goes: a slot late in the day stays lower.
  cy.get(".fc-timegrid-slot-lane").should("have.length.at.least", 1);
  cy.get(".fc-timegrid-slot-lane").then(() => {
    const fromPoint = pointInLanes(from);
    const scroller = fromPoint.lane.closest(".fc-scroller");
    const offset = fromPoint.lane.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
    const wanted = scroller.scrollTop + offset - SCROLLED_SLOT_OFFSET;
    scroller.scrollTop = Math.max(0, Math.min(wanted, scroller.scrollHeight - scroller.clientHeight));
  });
  cy.contains(".fc-event", booking.display_name)
    .should("be.visible")
    .then(($event) => {
      const eventBox = $event[0].getBoundingClientRect();
      const fromPoint = pointInLanes(from);
      const toPoint = pointInLanes(to);
      const column = Cypress.$(`.fc-timegrid-col[data-date="${to.date}"]`)[0].getBoundingClientRect();
      const point = (clientX, clientY) => ({ button: 0, clientX, clientY, pageX: clientX + window.scrollX, pageY: clientY + window.scrollY });
      const grabbed = point(eventBox.left + eventBox.width / 2, eventBox.top + eventBox.height / 2);
      const dropped = point(column.left + column.width / 2, grabbed.clientY + toPoint.clientY - fromPoint.clientY);
      cy.wrap($event).trigger("mousedown", { ...grabbed, scrollBehavior: false });
      cy.document().trigger("mousemove", { ...point(grabbed.clientX + 1, grabbed.clientY + 1), scrollBehavior: false });
      cy.document().trigger("mousemove", { ...dropped, scrollBehavior: false });
      cy.document().trigger("mouseup", { ...dropped, scrollBehavior: false });
    });
}
