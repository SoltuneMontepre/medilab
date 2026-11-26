import { expect, handOver, received, step, test } from "../support/journey";
import { field, front, listed, openListed, openMenu, openTab, pick, press, search, settled, status, suggested } from "../support/odoo";
import { bookingMachine, bookingSlot, findBookings, listedMoment, shownMoment } from "../support/schedule";

const TASKS = "sol_laboratory.menu_tasks_root";
const TASK_QUEUE = [TASKS, "sol_laboratory.menu_task_queue"];
const ALL_TASKS = [TASKS, "sol_laboratory.menu_task_all"];
const MY_TASKS = [TASKS, "sol_laboratory.menu_task_mine"];
const CALENDAR = "calendar.mail_menu_calendar";

const HEAD = "Hoang Van Minh";
// Every person of Chemistry has these letters in their name, so the suggestions show who may be assigned.
const ANY_CHEMIST = "an";

test("WF-03 Testing assignment and scheduling", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "machineCodes", "testerName", "sampleLabCode", "nitrateTaskName", "leadTaskName", "department");
  const booking = {};

  const tester = await as("demo.tester");
  const head = await as("demo.head_of_department");
  const bookingRow = (page) => field(page, "booking_ids").locator(".o_data_row");

  // The notices of the signed-in person, newest first, in the messaging menu's inbox.
  const openInbox = async (page) => {
    await page.locator(".o_menu_systray .o-mail-DiscussSystray-class").click();
    await page.locator(".o-mail-MessagingMenu button", { hasText: "Inbox" }).click();
    await settled(page);
    return page.locator(".o-mail-MessagingMenu .o-mail-NotificationItem");
  };

  await step(tester, "The tester chooses to be notified in the application", async () => {
    await tester.locator(".o_user_menu").click();
    await tester.locator(".o-dropdown--menu [data-menu=preferences]").click();
    await settled(tester);
    await field(tester, "notification_type").locator(".o_radio_item", { hasText: "In Odoo" }).locator("input").check();
    await Promise.all([tester.waitForEvent("load"), tester.locator(".modal:visible footer button[name=preference_save]").click()]);
    await settled(tester);
    await tester.locator(".o_menu_systray .o-mail-DiscussSystray-class").click();
    await expect(tester.locator(".o-mail-MessagingMenu button", { hasText: "Inbox" })).toBeVisible();
    await tester.keyboard.press("Escape");
  });

  await step(head, "The testing tasks of the sample wait in the queue of their department", async () => {
    await openMenu(head, ...TASK_QUEUE);
    await search(head, journey.sampleLabCode);
    await expect(head.locator(".o_list_view:visible .o_group_header")).toContainText(journey.department);
    for (const task of [journey.nitrateTaskName, journey.leadTaskName]) {
      await expect(listed(head, task).locator("td[name=status]")).toHaveText("Open");
      await expect(listed(head, task).locator("td[name=assignee_id]")).toHaveText("");
    }
  });

  await step(head, "The head assigns an authorized tester to the test", async () => {
    await listed(head, journey.nitrateTaskName).locator(".o_list_record_selector input").check();
    await head.locator(".o_control_panel .o_cp_action_menus button.dropdown-toggle").click();
    await head.locator(".o-dropdown--menu .o-dropdown-item", { hasText: /^Assign$/ }).click();
    await settled(head);
    const assign = front(head);
    await expect(field(head, "task_ids").locator(".o_tag")).toHaveCount(1);
    await expect(field(head, "task_ids").locator(".o_tag")).toHaveAttribute("data-tooltip", journey.nitrateTaskName);
    await expect(field(head, "department_id").locator("input")).toHaveValue(journey.department);
    // Only the people of the department the Lab Head authorized for the parameter are offered.
    await expect(await suggested(head, "assignee_id", ANY_CHEMIST)).toHaveText([journey.testerName]);
    await pick(head, "assignee_id", journey.testerName);
    await press(head, "action_confirm", { within: assign });
    await expect(head.locator(".o_notification", { hasText: journey.testerName })).toContainText(`1 tasks go to ${journey.testerName}.`);
    await expect(listed(head, journey.nitrateTaskName)).toHaveCount(0);
    await expect(listed(head, journey.leadTaskName).locator("td[name=status]")).toHaveText("Open");
    await expect(listed(head, journey.leadTaskName).locator("td[name=assignee_id]")).toHaveText("");
  });

  await step(tester, "The assigned tester is notified", async () => {
    const notices = await openInbox(tester);
    await expect(notices.filter({ hasText: journey.nitrateTaskName }).first()).toContainText(`${HEAD} assigned you ${journey.nitrateTaskName}.`);
    await tester.keyboard.press("Escape");
  });

  await step(head, "The department's plan proposes a booking of the agreed way", async () => {
    await openMenu(head, ...ALL_TASKS);
    await search(head, journey.parameterName);
    const task = listed(head, journey.nitrateTaskName);
    await expect(task).toHaveCount(1);
    await expect(task.locator("td[name=assignee_id]")).toHaveText(journey.testerName);
    await expect(task.locator("td[name=status]")).toHaveText("Assigned");
    await openListed(head, journey.nitrateTaskName);
    await expect(status(head)).toHaveAttribute("data-value", "assigned");
    await expect(field(head, "parameter_id")).toHaveText(journey.parameterName);
    await expect(field(head, "accepted_method_id")).toContainText(journey.methodCode);
    await expect(field(head, "recommended_method_id")).toHaveText((await field(head, "accepted_method_id").innerText()).trim());
    await expect(field(head, "recommended_machine_id")).toHaveText(/\S/);
    await expect(field(head, "recommended_start")).toHaveText(/\S/);
    await openTab(head, "bookings");
    await expect(bookingRow(head)).toHaveCount(1);
    await expect(bookingRow(head).locator("td[name=machine_id]")).toHaveText((await field(head, "recommended_machine_id").innerText()).trim());
    await expect(bookingRow(head).locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookingRow(head).locator("td[name=status]")).toHaveText("Proposed");
    await expect(bookingRow(head).locator("button[name=action_approve]")).toBeVisible();
  });

  await step(head, "The head approves the proposed booking", async () => {
    await press(head, "action_approve_booking");
    await expect(head.locator(".o_form_view:visible button[name=action_approve_booking]")).toHaveCount(0);
    await expect(field(head, "recommended_start")).toHaveCount(0);
    await expect(bookingRow(head)).toHaveCount(1);
    await expect(bookingRow(head).locator("td[name=status]")).toHaveText("Scheduled");
    await expect(bookingRow(head).locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookingRow(head).locator("button[name=action_start]")).toBeVisible();
    // The test moves on to Testing when its booking starts.
    await expect(status(head)).toHaveAttribute("data-value", "assigned");
  });

  await step(head, "The booking reserves its tester, its machine and the room of its method", async () => {
    const bookings = await findBookings(head, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
    await openListed(head, journey.parameterName);
    await expect(status(head)).toHaveAttribute("data-value", "scheduled");
    await expect(field(head, "display_name")).toHaveText(journey.nitrateTaskName);
    await expect(field(head, "method_id")).toHaveText(journey.methodCode);
    await expect(field(head, "person_id")).toHaveText(journey.testerName);
    await expect(field(head, "task_id")).toHaveText(journey.nitrateTaskName);
    Object.assign(booking, await bookingSlot(head));
    expect(new Date(booking.end).getTime()).toBeGreaterThan(new Date(booking.start).getTime());
    expect(new Date(booking.start).getTime(), "The approved booking starts in the future").toBeGreaterThan(Date.now());
    await openTab(head, "room_bookings");
    const rooms = field(head, "room_event_ids").locator(".o_data_row");
    await expect(rooms).not.toHaveCount(0);
    await expect(rooms.first().locator("td[name=location_id]")).toHaveText(/\S/);
    await expect(rooms.first().locator("td[name=start]")).toHaveText(/\S/);
    booking.room = (await rooms.first().locator("td[name=location_id]").innerText()).trim();
    booking.status = (await status(head).innerText()).trim();
    Object.assign(booking, { machine: await bookingMachine(head) });
    expect(journey.machineCodes).toContain(booking.machine.code);
    handOver("WF-03", {
      bookingMachine: booking.machine.code,
      bookingMachineName: booking.machine.name,
      bookingStart: booking.start,
      bookingEnd: booking.end,
      bookingStatus: booking.status,
      bookingRoom: booking.room,
    });
  });

  await step(tester, "The tester is notified of the approved booking", async () => {
    const notices = await openInbox(tester);
    await expect(notices.filter({ hasText: "is approved" }).first()).toContainText(`${journey.nitrateTaskName} is approved: it starts at ${shownMoment(booking.start).replace(/ (AM|PM)$/, ":00 $1")}.`);
    await tester.keyboard.press("Escape");
  });

  await step(tester, "The tester finds the scheduled booking of the assigned test in My Tasks", async () => {
    await openMenu(tester, ...MY_TASKS);
    await search(tester, journey.parameterName);
    const task = listed(tester, journey.nitrateTaskName);
    await expect(task).toHaveCount(1);
    await expect(task.locator("td[name=status]")).toHaveText("Assigned");
    handOver("WF-03", { nitrateTaskStatus: (await task.locator("td[name=status]").innerText()).trim() });
    await openListed(tester, journey.nitrateTaskName);
    await expect(status(tester)).toHaveAttribute("data-value", "assigned");
    await expect(tester.locator(".o_form_view:visible button[name=action_approve_booking]")).toHaveCount(0);
    await openTab(tester, "bookings");
    await expect(bookingRow(tester)).toHaveCount(1);
    await expect(bookingRow(tester).locator("td[name=machine_id]")).toHaveText(booking.machine.name);
    await expect(bookingRow(tester).locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookingRow(tester).locator("td[name=starts_at]")).toHaveText(listedMoment(booking.start));
    await expect(bookingRow(tester).locator("td[name=ends_at]")).toHaveText(listedMoment(booking.end));
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("Scheduled");
    await expect(bookingRow(tester).locator("button[name=action_start]")).toBeVisible();
  });

  await step(tester, "The tester sees the booking on the Machine Schedule and on the calendar", async () => {
    const bookings = await findBookings(tester, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(booking.machine.name);
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(listedMoment(booking.start));
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
    await openMenu(tester, CALENDAR);
    await tester.locator(".o_switch_view.o_list").click();
    await settled(tester);
    await search(tester, journey.sampleLabCode);
    const event = listed(tester, journey.nitrateTaskName);
    await expect(event).toHaveCount(1);
    await expect(event).toContainText(booking.machine.name);
  });
});
