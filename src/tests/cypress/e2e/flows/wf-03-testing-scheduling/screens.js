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
export function wallClock(value, zone) {
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

const minutesOf = (time) => {
  const [hour, minute] = time.split(":").map(Number);
  return hour * 60 + minute;
};

const SNAP_MINUTES = 15;

// The calendar draws a lane every half hour and snaps a drop to the quarter hour, so a time between two lanes is not
// a lane of its own. Yields the lane a time, in minutes, falls in and how far into it the time lies, from 0 to 1.
function laneOf(wanted) {
  const lanes = Cypress.$(".fc-timegrid-slot-lane[data-time]").toArray();
  const starts = lanes.map((lane) => minutesOf(lane.dataset.time));
  const index = starts.findLastIndex((start) => start <= wanted);
  expect(index, `the calendar lane of minute ${wanted}`).to.be.at.least(0);
  const length = starts[1] - starts[0];
  return { lane: lanes[index], fraction: (wanted - starts[index]) / length };
}

// The height on the screen of a time in the calendar.
function timeTop(minutes) {
  const { lane, fraction } = laneOf(minutes);
  const box = lane.getBoundingClientRect();
  return box.top + fraction * box.height;
}

// Moves the dragged booking's preview to a time of a day: the pointer goes by the distance from the preview to the
// time, as often as the preview, snapped to the quarter hour, is not there yet.
function moveDragTo(point, x, y, date, time, tries = 3) {
  cy.document({ log: false }).trigger("mousemove", { ...point(x, y), scrollBehavior: false });
  cy.document({ log: false }).then((document) => {
    const mirror = document.querySelector(`.fc-timegrid-col[data-date="${date}"] .fc-event-mirror`);
    expect(mirror, `the preview of the drag on ${date}`).to.exist;
    const gap = timeTop(minutesOf(time)) - mirror.getBoundingClientRect().top;
    if (Math.abs(gap) < 1) return cy.document({ log: false }).trigger("mouseup", { ...point(x, y), scrollBehavior: false });
    expect(tries, `the preview of the drag at ${time} on ${date}`).to.be.above(1);
    return moveDragTo(point, x, y + gap, date, time, tries - 1);
  });
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
  const lanes = ".fc-timegrid-slot-lane[data-time]";
  const offsetInScroller = ($lanes) =>
    timeTop(minutesOf(from.time) + SNAP_MINUTES / 2) - $lanes.closest(".fc-scroller")[0].getBoundingClientRect().top;
  const scrolledTop = ($lanes) => {
    const scroller = $lanes.closest(".fc-scroller")[0];
    const wanted = scroller.scrollTop + offsetInScroller($lanes) - SCROLLED_SLOT_OFFSET;
    return Math.max(0, Math.min(wanted, scroller.scrollHeight - scroller.clientHeight));
  };
  cy.get(lanes).then(($lanes) => {
    $lanes.closest(".fc-scroller")[0].scrollTop = scrolledTop($lanes);
  });
  cy.get(lanes).should(($lanes) => expect($lanes.closest(".fc-scroller")[0].scrollTop).to.be.closeTo(scrolledTop($lanes), 1));
  cy.contains(".fc-event", booking.display_name)
    .should("be.visible")
    .then(($event) => {
      const eventBox = $event[0].getBoundingClientRect();
      const $column = Cypress.$(`.fc-timegrid-col[data-date="${to.date}"]`);
      expect($column, `the day of the slot, ${to.date}, in the booking's week`).to.have.length(1);
      const column = $column[0].getBoundingClientRect();
      const point = (clientX, clientY) => ({ button: 0, clientX, clientY, pageX: clientX + window.scrollX, pageY: clientY + window.scrollY });
      // The booking is grabbed in its first quarter hour, away from the edges where the pointer may snap either way.
      const grabbed = point(eventBox.left + eventBox.width / 2, timeTop(minutesOf(from.time) + SNAP_MINUTES / 2));
      expect(grabbed.clientY, "the grab point inside the booking").to.be.within(eventBox.top, eventBox.bottom);
      cy.wrap($event).trigger("mousedown", { ...grabbed, scrollBehavior: false });
      cy.document().trigger("mousemove", { ...point(grabbed.clientX + 1, grabbed.clientY + 1), scrollBehavior: false });
      const y = grabbed.clientY + timeTop(minutesOf(to.time)) - timeTop(minutesOf(from.time));
      moveDragTo(point, column.left + column.width / 2, y, to.date, to.time);
    });
}
