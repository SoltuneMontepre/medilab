import { expect, received, step, test } from "../support/journey";
import { field, listed, openListed, openMenu, openTab, search, showList, status } from "../support/odoo";
import { bookingSlot, findBookings, later, listedMoment } from "../support/schedule";

const CALENDAR = "calendar.mail_menu_calendar";

test("SF-10 Scheduling plan and revisions", async ({ as }) => {
  const journey = received("tag", "parameterName", "testerName", "sampleLabCode", "nitrateTaskName", "bookingMachineName", "bookingRoom", "bookingStart", "bookingEnd");
  const planned = { start: journey.bookingStart, end: journey.bookingEnd };
  const minutes = (new Date(planned.end) - new Date(planned.start)) / 60000;
  // A room is reserved for its step of the method, some quarter hours into the booking.
  const withinBooking = (text) => Array.from({ length: minutes / 15 + 1 }, (_, quarter) => later(planned.start, quarter * 15)).some((moment) => listedMoment(moment).test(text));

  const head = await as("demo.head_of_department");

  await step(head, "The plan places the received, not-started test where its tester, machine and room are free", async () => {
    const bookings = await findBookings(head, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(journey.bookingMachineName);
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(listedMoment(planned.start));
    await expect(bookings.locator("td[name=ends_at]")).toHaveText(listedMoment(planned.end));
    await expect(bookings.locator("td[name=priority]")).toHaveText(/\S/);
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
  });

  await step(head, "The approved booking keeps its tester, machine and room reservations together", async () => {
    await openListed(head, journey.parameterName);
    await expect(status(head)).toHaveAttribute("data-value", "scheduled");
    expect(await bookingSlot(head)).toEqual(planned);
    await expect(field(head, "person_id")).toHaveText(journey.testerName);
    await expect(field(head, "machine_id")).toHaveText(journey.bookingMachineName);
    await openTab(head, "room_bookings");
    const room = field(head, "room_event_ids").locator(".o_data_row", { hasText: journey.bookingRoom });
    await expect(room).toHaveCount(1);
    expect(withinBooking((await room.locator("td[name=start]").innerText()).trim()), "The room is reserved within the booking").toBe(true);
  });

  const tester = await as("demo.tester");

  await step(tester, "The tester's calendar holds the machine and the room for the booking", async () => {
    await openMenu(tester, CALENDAR);
    await showList(tester);
    await search(tester, journey.sampleLabCode);
    const machineEvent = listed(tester, `${journey.bookingMachineName}: ${journey.nitrateTaskName}`);
    await expect(machineEvent).toHaveCount(1);
    await expect(machineEvent.locator("td[name=start]")).toHaveText(listedMoment(planned.start));
    await expect(machineEvent.locator("td[name=stop]")).toHaveText(listedMoment(planned.end));
    // A room's calendar events are named without its code.
    const roomEvent = listed(tester, `${journey.bookingRoom.replace(/^\S+ /, "")}: ${journey.nitrateTaskName}`);
    await expect(roomEvent).toHaveCount(1);
    await expect(roomEvent.locator("td[name=location]")).toHaveText(journey.bookingRoom);
    expect(withinBooking((await roomEvent.locator("td[name=start]").innerText()).trim()), "The room's event is within the booking").toBe(true);
  });
});
