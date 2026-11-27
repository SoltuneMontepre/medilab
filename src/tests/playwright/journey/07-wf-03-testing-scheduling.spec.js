import { expect, handOver, outside, received, step, test } from "../support/journey";
import { field, front, listed, openListed, openMenu, openTab, pick, press, search, settled, status, suggested } from "../support/odoo";
import { bookingMachine, bookingSlot, findBookings } from "../support/schedule";

const TASKS = "sol_laboratory.menu_tasks_root";
const TASK_QUEUE = [TASKS, "sol_laboratory.menu_task_queue"];
const ALL_TASKS = [TASKS, "sol_laboratory.menu_task_all"];

// Every person of Chemistry has these letters in their name, so the suggestions show who may be assigned.
const ANY_CHEMIST = "an";

test("WF-03 Testing assignment and scheduling", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "machineCodes", "testerName", "sampleLabCode", "nitrateTaskName", "leadTaskName", "department");
  const booking = {};

  const head = await as("demo.head_of_department");
  const bookingRow = () => field(head, "booking_ids").locator(".o_data_row");

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
    // The row's Assign Sample would assign every task of the sample, the Lead test too.
    await listed(head, journey.nitrateTaskName).locator(".o_list_record_selector input").check();
    await head.locator(".o_control_panel .o_cp_action_menus button.dropdown-toggle").click();
    await head.locator(".o-dropdown--menu .o-dropdown-item", { hasText: /^Assign$/ }).click();
    await settled(head);
    const assign = front(head);
    await expect(field(head, "task_ids").locator(".o_tag")).toHaveAttribute("data-tooltip", journey.nitrateTaskName);
    await expect(field(head, "department_id").locator("input")).toHaveValue(journey.department);
    // Only the people of the department the Lab Head authorized for the parameter are offered.
    await expect(await suggested(head, "assignee_id", ANY_CHEMIST)).toHaveText([journey.testerName]);
    await pick(head, "assignee_id", journey.testerName);
    await press(head, "action_confirm", { within: assign });
    await expect(head.locator(".o_notification", { hasText: journey.testerName })).toBeVisible();
    await expect(listed(head, journey.nitrateTaskName)).toHaveCount(0);
    await expect(listed(head, journey.leadTaskName).locator("td[name=assignee_id]")).toHaveText("");
  });

  await outside("The assigned tester is notified", "e-mail");

  await step(head, "The department's plan proposes a booking of the agreed way", async () => {
    await openMenu(head, ...ALL_TASKS);
    await search(head, journey.parameterName);
    const task = listed(head, journey.nitrateTaskName);
    await expect(task).toHaveCount(1);
    await expect(task.locator("td[name=assignee_id]")).toHaveText(journey.testerName);
    await openListed(head, journey.nitrateTaskName);
    await expect(status(head)).toHaveAttribute("data-value", "assigned");
    await expect(field(head, "accepted_method_id")).toContainText(journey.methodCode);
    await expect(field(head, "recommended_method_id")).toHaveText((await field(head, "accepted_method_id").innerText()).trim());
    await expect(field(head, "recommended_start")).toHaveText(/\S/);
    await openTab(head, "bookings");
    await expect(bookingRow()).toHaveCount(1);
    await expect(bookingRow().locator("td[name=machine_id]")).toHaveText((await field(head, "recommended_machine_id").innerText()).trim());
    await expect(bookingRow().locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookingRow().locator("td[name=status]")).toHaveText("Proposed");
  });

  await step(head, "The head approves the proposed booking, feasible before the due date", async () => {
    await press(head, "action_approve_booking");
    await expect(head.locator(".o_form_view:visible button[name=action_approve_booking]")).toHaveCount(0);
    await expect(bookingRow()).toHaveCount(1);
    await expect(bookingRow().locator("td[name=status]")).toHaveText("Scheduled");
    await expect(bookingRow().locator("td[name=person_id]")).toHaveText(journey.testerName);
  });

  await step(head, "The booking reserves its tester, its machine and the room of its method together", async () => {
    const bookings = await findBookings(head, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await openListed(head, journey.parameterName);
    await expect(status(head)).toHaveAttribute("data-value", "scheduled");
    await expect(field(head, "method_id")).toHaveText(journey.methodCode);
    await expect(field(head, "person_id")).toHaveText(journey.testerName);
    await expect(field(head, "task_id")).toHaveText(journey.nitrateTaskName);
    Object.assign(booking, await bookingSlot(head));
    await openTab(head, "room_bookings");
    const rooms = field(head, "room_event_ids").locator(".o_data_row");
    await expect(rooms).not.toHaveCount(0);
    await expect(rooms.first().locator("td[name=location_id]")).toHaveText(/\S/);
    booking.room = (await rooms.first().locator("td[name=location_id]").innerText()).trim();
    booking.status = (await status(head).innerText()).trim();
    booking.machine = await bookingMachine(head);
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

  await outside("The tester is notified of the approved booking", "e-mail");
  await outside("The tester is reminded before the booking starts", "e-mail, before the booking starts");
});
