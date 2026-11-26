import { expect, handOver, received, step, test } from "../support/journey";
import { field, front, listed, openListed, openMenu, openTab, press, pressLabel, search, settled, shownDay, status, type } from "../support/odoo";
import { bookingSlot, findBookings, later, listedMoment, shownMoment, typeMoment } from "../support/schedule";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const SAMPLE_TESTS = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample_test"];
const PLAN_REVISIONS = [LABORATORY, "sol_laboratory.menu_laboratory_schedule", "sol_laboratory.menu_plan_revision"];
const MY_TASKS = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_mine"];
const CALENDAR = "calendar.mail_menu_calendar";

// The hours a booking may start at in the laboratory's working day, which breaks from 12:00 to 13:00.
const WORKING_BLOCKS = [[8, 12], [13, 17]];
const DAYS_AHEAD = 10;

// The free-slot candidates after a booking: each full hour of the working days after its start that fits its length.
function laterSlots(start, end) {
  const minutes = (new Date(end) - new Date(start)) / 60000;
  const slots = [];
  for (let ahead = 0; ahead < DAYS_AHEAD; ahead += 1) {
    const day = new Date(`${start.slice(0, 10)}T00:00:00Z`);
    day.setUTCDate(day.getUTCDate() + ahead);
    if ([0, 6].includes(day.getUTCDay())) continue;
    for (const [opens, closes] of WORKING_BLOCKS) {
      for (let hour = opens; hour * 60 + minutes <= closes * 60; hour += 1) {
        const slot = `${day.toISOString().slice(0, 10)}T${String(hour).padStart(2, "0")}:00:00+07:00`;
        if (new Date(slot) > new Date(start)) slots.push(slot);
      }
    }
  }
  return slots;
}

test("SF-10 Scheduling plan and revisions", async ({ as }) => {
  const journey = received("tag", "parameterName", "testerName", "sampleLabCode", "nitrateTaskName", "bookingMachineName", "bookingRoom", "bookingStart", "bookingEnd");
  const urgentReason = `Khách hàng cần kết quả gấp ${journey.tag}`;
  const planned = { start: journey.bookingStart, end: journey.bookingEnd };
  const moved = {};
  const roomName = journey.bookingRoom.replace(/^\S+ /, "");

  const tester = await as("demo.tester");
  const head = await as("demo.head_of_department");
  const bookingRow = (page) => field(page, "booking_ids").locator(".o_data_row");
  const roomRow = (page) => field(page, "room_event_ids").locator(".o_data_row", { hasText: journey.bookingRoom });

  await step(tester, "The tester finds their assigned test, which is not urgent", async () => {
    await openMenu(tester, ...SAMPLE_TESTS);
    await search(tester, journey.parameterName, { field: "Parameter" });
    const sampleTest = listed(tester, journey.parameterName);
    await expect(sampleTest).toHaveCount(1);
    await expect(sampleTest.locator("td[name=status]")).toHaveText("Assigned");
    await openListed(tester, journey.parameterName);
    await expect(status(tester)).toHaveAttribute("data-value", "assigned");
    await expect(field(tester, "sample_id")).toHaveText(journey.sampleLabCode);
    await expect(field(tester, "priority")).not.toHaveText("Urgent");
    await expect(tester.locator(".o_form_view:visible .o_statusbar_buttons").getByRole("button", { name: "Mark Urgent", exact: true })).toBeVisible();
  });

  await step(tester, "Marking the test urgent without a reason is refused", async () => {
    await pressLabel(tester, "Mark Urgent");
    const marking = front(tester);
    await expect(marking.locator(".modal-title")).toHaveText("Mark the Test Urgent");
    await press(tester, "action_mark", { within: marking });
    await expect(field(tester, "reason", marking)).toHaveClass(/o_field_invalid/);
    await expect(tester.locator(".o_notification", { hasText: "Missing required fields" })).toBeVisible();
    await expect(marking).toBeVisible();
  });

  await step(tester, "The tester marks the test urgent with a reason", async () => {
    await type(tester, "reason", urgentReason);
    await press(tester, "action_mark");
    await expect(tester.locator(".modal:visible")).toHaveCount(0);
    await expect(field(tester, "priority")).toHaveText("Urgent");
    await expect(field(tester, "urgent_reason")).toHaveText(urgentReason);
    await expect(field(tester, "marked_urgent_by_id")).toHaveText(journey.testerName);
    await expect(tester.locator(".o_form_view:visible button[name=action_unmark_urgent]")).toBeVisible();
    await expect(status(tester)).toHaveAttribute("data-value", "assigned");
    handOver("SF-10", { urgentReason, nitratePriority: (await field(tester, "priority").innerText()).trim() });
  });

  await step(head, "The plan keeps the approved booking of the urgent test in its slot", async () => {
    await openMenu(head, ...PLAN_REVISIONS);
    // The list opens on the plan revisions that wait for the head; a revision names the bookings it would move.
    await expect(head.locator(".o_searchview_facet", { hasText: "Proposed" })).toBeVisible();
    await expect(listed(head, journey.sampleLabCode)).toHaveCount(0);
    const bookings = await findBookings(head, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=priority]")).toHaveText("Urgent");
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(listedMoment(planned.start));
    await expect(bookings.locator("td[name=ends_at]")).toHaveText(listedMoment(planned.end));
  });

  await step(head, "The head moves the department's booking to another free slot, which pins it", async () => {
    await openListed(head, journey.parameterName);
    const form = head.locator(".o_form_view:visible");
    await expect(status(head)).toHaveAttribute("data-value", "scheduled");
    await expect(form.locator(".badge", { hasText: "Pinned" })).toHaveCount(0);
    expect(await bookingSlot(head)).toEqual(planned);
    const minutes = (new Date(planned.end) - new Date(planned.start)) / 60000;
    await openTab(head, "room_bookings");
    await expect(roomRow(head)).toHaveCount(1);
    const roomStart = (await roomRow(head).locator("td[name=start]").innerText()).trim();
    // The room is reserved for its step of the method, some quarter hours after the booking starts.
    moved.roomDelay = Array.from({ length: minutes / 15 + 1 }, (_, quarter) => quarter * 15).find((delay) => listedMoment(later(planned.start, delay)).test(roomStart));
    expect(moved.roomDelay, `The room's start ${roomStart} is within the booking`).toBeDefined();

    const refused = [];
    for (const slot of laterSlots(planned.start, planned.end)) {
      await typeMoment(head, "starts_at", slot);
      await expect(shownDay(head, "ends_at")).toHaveAttribute("data-tooltip", shownMoment(later(slot, minutes)));
      await head.locator(".o_form_button_save:visible").click();
      await settled(head, { refusals: true });
      const refusal = head.locator(".o_error_dialog");
      if (!(await refusal.count())) {
        moved.start = slot;
        break;
      }
      // A slot whose tester, machine or room is taken is refused with the name of what is not free.
      await expect(refusal).toContainText(`is not free for ${journey.nitrateTaskName} at that time.`);
      refused.push(slot);
      await refusal.locator(".modal-footer button").first().click();
      await expect(refusal).toHaveCount(0);
    }
    expect(moved.start, `One of the slots after ${planned.start} is free; refused: ${refused.join(", ") || "none"}`).toBeDefined();
    moved.end = later(moved.start, minutes);
    await expect(head.locator(".o_form_button_save:visible")).toHaveCount(0);
    expect(await bookingSlot(head)).toEqual({ start: moved.start, end: moved.end });
    await expect(status(head)).toHaveAttribute("data-value", "scheduled");
    await expect(form.locator(".badge", { hasText: "Pinned" })).toBeVisible();
    await expect(form.locator(".badge", { hasText: "Missed" })).toHaveCount(0);
    await expect(field(head, "person_id")).toHaveText(journey.testerName);
    await expect(field(head, "machine_id")).toHaveText(journey.bookingMachineName);
    handOver("SF-10", { bookingStart: moved.start, bookingEnd: moved.end, bookingPinned: true, bookingStatus: (await status(head).innerText()).trim() });
  });

  await step(head, "The reservation of the room moves with the booking", async () => {
    await openTab(head, "room_bookings");
    await expect(roomRow(head)).toHaveCount(1);
    await expect(roomRow(head).locator("td[name=start]")).toHaveText(listedMoment(later(moved.start, moved.roomDelay)));
    const bookings = await findBookings(head, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(listedMoment(moved.start));
    await expect(bookings.locator("td[name=ends_at]")).toHaveText(listedMoment(moved.end));
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
  });

  await step(tester, "The tester's calendar and task show the booking at its new time", async () => {
    await openMenu(tester, CALENDAR);
    await tester.locator(".o_switch_view.o_list").click();
    await settled(tester);
    await search(tester, journey.sampleLabCode);
    const machineEvent = listed(tester, `${journey.bookingMachineName}: ${journey.nitrateTaskName}`);
    await expect(machineEvent).toHaveCount(1);
    await expect(machineEvent.locator("td[name=start]")).toHaveText(listedMoment(moved.start));
    await expect(machineEvent.locator("td[name=stop]")).toHaveText(listedMoment(moved.end));
    const roomEvent = listed(tester, `${roomName}: ${journey.nitrateTaskName}`);
    await expect(roomEvent).toHaveCount(1);
    await expect(roomEvent.locator("td[name=start]")).toHaveText(listedMoment(later(moved.start, moved.roomDelay)));
    await openMenu(tester, ...MY_TASKS);
    await search(tester, journey.parameterName);
    await expect(listed(tester, journey.nitrateTaskName).locator("td[name=status]")).toHaveText("Assigned");
    await openListed(tester, journey.nitrateTaskName);
    await openTab(tester, "bookings");
    await expect(bookingRow(tester)).toHaveCount(1);
    await expect(bookingRow(tester).locator("td[name=starts_at]")).toHaveText(listedMoment(moved.start));
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("Scheduled");
    await expect(bookingRow(tester).locator("button[name=action_start]")).toBeVisible();
  });
});
