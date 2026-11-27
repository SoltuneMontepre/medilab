import { expect, handOver, received, step, test } from "../support/journey";
import { clearSearch, closeDialog, field, listed, openListed, openMenu, openNotices, openTab, press, pressLabel, receiveNoticesInApplication, save, search, settled, shownDay, status, toggleMessages, type } from "../support/odoo";
import { openOrder } from "../support/portal";
import { bookingMachine, findBookings, labMoment, listedMoment } from "../support/schedule";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const SAMPLE_TESTS = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample_test"];
const TEST_REQUESTS = [LABORATORY, "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_test_request"];
const TEST_RESULTS = [LABORATORY, "sol_laboratory.menu_laboratory_results", "sol_laboratory.menu_test_result"];
const TASKS = "sol_laboratory.menu_tasks_root";
const MY_TASKS = [TASKS, "sol_laboratory.menu_task_mine"];
const FINISHED_TASKS = [TASKS, "sol_laboratory.menu_task_finished"];

const HEAD = "Hoang Van Minh";
const MEASURED = "12.5";
const UNIT = "mg/L";
const LOD = "0.05";
const LOQ = "0.15";

const buttons = (page) => page.locator(".o_form_view:visible .o_statusbar_buttons").last();
const button = (page, label) => buttons(page).getByRole("button", { name: label, exact: true });
const bookingRow = (page) => field(page, "booking_ids").locator(".o_data_row");
const resultRow = (page) => field(page, "result_ids").locator(".o_data_row");
const alerts = (page) => page.locator(".o_form_view:visible .alert:visible");

test("WF-04 Result entry and approval", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "sampleType", "testerName", "sampleLabCode", "requestCode", "requestSearch", "requestSearchField", "customerLogin", "customerPassword", "orderNumber", "nitrateTaskName", "leadParameterName", "bookingMachine", "bookingMachineName", "bookingStart", "bookingEnd", "resultFolderName");
  const labCode = journey.sampleLabCode;
  const resultName = `${labCode} – ${journey.parameterName}`;
  const sentNotice = new RegExp(`Result ${resultName} \\(.+\\) was sent for approval\\.`);
  const result = {};

  const head = await as("demo.head_of_department");
  const tester = await as("demo.tester");

  // Returns to a form the breadcrumb still names.
  const back = async (page, name) => {
    await page.locator(".o_breadcrumb .breadcrumb-item a", { hasText: name }).last().click();
    await settled(page);
  };

  const openTask = async (page) => {
    await openMenu(page, ...MY_TASKS);
    await search(page, journey.parameterName);
    await expect(listed(page, journey.nitrateTaskName)).toHaveCount(1);
    await openListed(page, journey.nitrateTaskName);
    await expect(field(page, "sample_id")).toHaveText(labCode);
    await expect(field(page, "parameter_id")).toHaveText(journey.parameterName);
  };

  // The results of the sample, where the nitrate result is the one row of its parameter.
  const openResult = async (page) => {
    await openMenu(page, ...TEST_RESULTS);
    await search(page, labCode, { field: "Sample" });
    await expect(listed(page, journey.parameterName)).toHaveCount(1);
    await openListed(page, journey.parameterName);
    await expect(field(page, "display_name")).toContainText(resultName);
  };

  const resultsTile = head.locator(".o_task_tile_approve .o_task_row", { hasText: "Results to approve" });

  // The head's results to approve, from the tile of the open Tasks dashboard, narrowed to the journey's sample.
  const resultsToApprove = async () => {
    await resultsTile.locator("button.o_task_row_main").click();
    await settled(head);
    await expect(head.locator(".o_list_view:visible")).toBeVisible();
    await search(head, labCode, { field: "Sample" });
    return listed(head, journey.parameterName);
  };

  await step(head, "The head of department chooses to be notified in the application", async () => {
    await receiveNoticesInApplication(head);
  });

  await step(tester, "The tester finds the booked test in My Tasks", async () => {
    await openTask(tester);
    await expect(status(tester)).toHaveAttribute("data-value", "assigned");
    await expect(field(tester, "parameter_method_id")).toContainText(journey.methodCode);
    await openTab(tester, "bookings");
    await expect(bookingRow(tester)).toHaveCount(1);
    await expect(bookingRow(tester).locator("td[name=machine_id]")).toHaveText(journey.bookingMachineName);
    await expect(bookingRow(tester).locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookingRow(tester).locator("td[name=starts_at]")).toHaveText(listedMoment(journey.bookingStart));
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("Scheduled");
    await expect(bookingRow(tester).locator("button[name=action_start]")).toBeVisible();
  });

  await step(tester, "The tester starts the booking: the test is in testing", async () => {
    await press(tester, "action_start", { within: bookingRow(tester) });
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("In progress");
    await expect(bookingRow(tester).locator("button[name=action_start]")).toHaveCount(0);
    await expect(bookingRow(tester).locator("button[name=action_done]")).toBeVisible();
    await expect(status(tester)).toHaveAttribute("data-value", "testing");
    await expect(button(tester, "Enter Result")).toBeVisible();
    // Starting ahead of the slot leaves the booking at the time it was planned for.
    await expect(bookingRow(tester).locator("td[name=starts_at]")).toHaveText(listedMoment(journey.bookingStart));
    await expect(bookingRow(tester).locator("td[name=ends_at]")).toHaveText(listedMoment(journey.bookingEnd));
  });

  await step(tester, "The machine is busy through its booking in progress; its own status stays in use", async () => {
    await bookingRow(tester).locator("td[name=machine_id]").click();
    await settled(tester);
    await expect(tester.locator(".modal:visible .o_form_view")).toBeVisible();
    await expect(status(tester)).toHaveAttribute("data-value", "in_progress");
    await expect(field(tester, "person_id")).toHaveText(journey.testerName);
    const machine = await bookingMachine(tester);
    expect(machine).toEqual({ name: journey.bookingMachineName, code: journey.bookingMachine });
    await expect(status(tester)).toHaveAttribute("data-value", "in_use");
    handOver("WF-04", { machineStatusWhileTesting: (await status(tester).innerText()).trim() });
    await back(tester, journey.parameterName);
    await expect(status(tester)).toHaveAttribute("data-value", "testing");
  });

  await step(tester, "The tester saves the result file in the sample's folder from the browser", async () => {
    await field(tester, "sample_id").locator("a").click();
    await settled(tester);
    await expect(field(tester, "code")).toHaveText(labCode);
    await press(tester, "action_open_laboratory_folders");
    await expect(listed(tester, journey.resultFolderName)).toHaveCount(1);
    await openListed(tester, journey.resultFolderName);
    await expect(field(tester, "name")).toHaveText(journey.resultFolderName);
    await openTab(tester, "files");
    await expect(field(tester, "file_ids").locator(".o_data_row")).toHaveCount(0);
    const ways = await tester.locator(".o_field_widget[name=file_ids] .o_field_x2many_list_row_add, .o_action_manager input[type=file]").count();
    expect.soft(ways, "The tester has a way to save a result file in the sample's folder from the browser").toBeGreaterThan(0);
    await back(tester, journey.parameterName);
    await expect(status(tester)).toHaveAttribute("data-value", "testing");
  });

  await step(tester, "The tester enters the result with the snapshotted unit and LOD/LOQ", async () => {
    await pressLabel(tester, "Enter Result", { within: buttons(tester) });
    await expect(tester.locator(".o_form_button_save:visible")).toBeVisible();
    await expect(field(tester, "unit_id")).toHaveText(UNIT);
    await expect(field(tester, "value_decimals").locator("input")).toHaveValue("2");
    await expect(field(tester, "lod")).toHaveText(LOD);
    await expect(field(tester, "loq")).toHaveText(LOQ);
    await expect(field(tester, "parameter_method_id")).toContainText(journey.methodCode);
    await expect(field(tester, "sample_type_id")).toHaveText(journey.sampleType);
    await expect(field(tester, "machine_id")).toHaveText(journey.bookingMachineName);
    await type(tester, "value", MEASURED);
    await expect(field(tester, "value").locator("input")).toHaveValue(MEASURED);
  });

  await step(tester, "No comparison is requested, so no conclusion is asked; the measurement raises no warning", async () => {
    await expect(field(tester, "conclusion")).toBeHidden();
    await expect(tester.locator(".o_form_view:visible .o_test_result_card_title", { hasText: "Regulation" })).toBeHidden();
    await expect(alerts(tester)).toHaveCount(0);
    await save(tester);
    await expect(field(tester, "display_name")).toContainText(resultName);
    await expect(tester.locator(".o_form_view:visible .o_test_result_chip.o_chip_success")).toHaveText("Reported Result");
    await expect(field(tester, "version")).toHaveText("1");
    await expect(field(tester, "entered_by_id")).toHaveText(journey.testerName);
    await expect(field(tester, "value_display")).toHaveText(/^12[.,]50$/);
    await expect(alerts(tester)).toHaveCount(0);
    await expect(status(tester)).toHaveAttribute("data-value", "none");
    result.value = `${(await field(tester, "value_display").innerText()).trim()} ${(await field(tester, "unit_id").innerText()).trim()}`;
    handOver("WF-04", { nitrateResult: result.value, nitrateResultLod: LOD, nitrateResultLoq: LOQ });
    const startedAt = labMoment(await shownDay(tester, "started_at").getAttribute("data-tooltip"));
    expect(startedAt).toBe(journey.bookingStart);
    expect.soft(new Date(startedAt).getTime(), "The result of a booking started ahead of its slot does not start in the future").toBeLessThanOrEqual(Date.now());
  });

  await step(tester, "Recording the result ends the booking: the machine is free, the testing task stays open", async () => {
    await back(tester, journey.parameterName);
    await expect(status(tester)).toHaveAttribute("data-value", "testing");
    await openTab(tester, "bookings");
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("Done");
    await openTab(tester, "results");
    await expect(resultRow(tester)).toHaveCount(1);
    await expect(resultRow(tester).locator("td[name=status]")).toHaveText("Draft");
    await expect(await findBookings(tester, journey.parameterName)).toHaveCount(0);
    await openTask(tester);
  });

  await step(tester, "The tester sends and signs the result for Head of Department approval", async () => {
    await openTab(tester, "results");
    await resultRow(tester).locator("td[name=value_display]").click();
    await settled(tester);
    const dialog = tester.locator(".modal:visible");
    await expect(dialog.locator(".o_form_view")).toBeVisible();
    await pressLabel(tester, "Send for Approval", { within: buttons(tester) });
    // A click signs: no password, PIN or confirmation is asked.
    await expect(tester.locator(".modal:visible")).toHaveCount(1);
    await expect(status(tester)).toHaveAttribute("data-value", "requested");
    await expect(button(tester, "Send for Approval")).toHaveCount(0);
    await expect(button(tester, "Withdraw Signature")).toBeVisible();
    await expect(field(tester, "value").locator("input")).toHaveCount(0);
    await closeDialog(tester);
    await expect(resultRow(tester).locator("td[name=status]")).toHaveText("Awaiting Approval");
  });

  await step(tester, "Sending the result completes the testing task", async () => {
    await openMenu(tester, ...MY_TASKS);
    await search(tester, journey.parameterName);
    await expect(listed(tester, journey.nitrateTaskName)).toHaveCount(0);
    await openMenu(tester, ...FINISHED_TASKS);
    await search(tester, journey.parameterName);
    await expect(listed(tester, journey.nitrateTaskName).locator("td[name=status]")).toHaveText("Done");
    await openMenu(tester, ...SAMPLE_TESTS);
    await clearSearch(tester);
    await search(tester, labCode, { field: "Sample" });
    await expect(listed(tester, journey.parameterName).locator("td[name=status]")).toHaveText("Result Entered");
  });

  await step(head, "The head of department is notified, and the result waits under Results to approve", async () => {
    // The application lists a notice sent meanwhile once the page is loaded again.
    await head.reload();
    await settled(head);
    const notices = await openNotices(head);
    await expect(notices.filter({ hasText: sentNotice })).toHaveCount(1);
    await toggleMessages(head);
    await openMenu(head, TASKS);
    await expect(resultsTile.locator("strong")).toHaveText(/^[1-9]\d*$/);
    const waiting = await resultsToApprove();
    await expect(waiting).toHaveCount(1);
    await expect(waiting.locator("td[name=value_display]")).toHaveText(result.value.slice(0, -UNIT.length).trim());
    await expect(waiting.locator("td[name=unit_id]")).toHaveText(UNIT);
    await expect(waiting.locator("td[name=conclusion]")).toHaveText("");
    await expect(waiting.locator("td[name=entered_by_id]")).toHaveText(journey.testerName);
    await expect(waiting.locator("td[name=status]")).toHaveText("Awaiting Approval");
  });

  await step(tester, "The tester withdraws the result before the head acts", async () => {
    await openResult(tester);
    await expect(status(tester)).toHaveAttribute("data-value", "requested");
    await pressLabel(tester, "Withdraw Signature", { within: buttons(tester) });
    await expect(status(tester)).toHaveAttribute("data-value", "none");
    await expect(button(tester, "Withdraw Signature")).toHaveCount(0);
    await expect(button(tester, "Send for Approval")).toBeVisible();
    await expect(field(tester, "value").locator("input")).toHaveValue(MEASURED);
  });

  await step(head, "The withdrawn result leaves the head's results to approve", async () => {
    await openMenu(head, TASKS);
    // The tile lists only what waits, so it is gone when no other result waits for this head.
    if (await resultsTile.count()) await expect(await resultsToApprove()).toHaveCount(0);
    else await expect(head.locator(".o_task_dashboard")).toBeVisible();
  });

  await step(tester, "The withdrawn result reopens the testing task, and the tester sends it again", async () => {
    await openTask(tester);
    await expect(status(tester)).toHaveAttribute("data-value", "testing");
    await openTab(tester, "bookings");
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("Done");
    await openTab(tester, "results");
    await expect(resultRow(tester)).toHaveCount(1);
    await expect(resultRow(tester).locator("td[name=status]")).toHaveText("Draft");
    await resultRow(tester).locator("td[name=value_display]").click();
    await settled(tester);
    await expect(tester.locator(".modal:visible .o_form_view")).toBeVisible();
    await pressLabel(tester, "Send for Approval", { within: buttons(tester) });
    await expect(status(tester)).toHaveAttribute("data-value", "requested");
    await closeDialog(tester);
    await openMenu(tester, ...MY_TASKS);
    await search(tester, journey.parameterName);
    await expect(listed(tester, journey.nitrateTaskName)).toHaveCount(0);
  });

  await step(head, "The head of department opens the result sent again from its notice", async () => {
    await head.reload();
    await settled(head);
    const notices = await openNotices(head);
    // The result sent again after its withdrawal is told again.
    await expect(notices.filter({ hasText: sentNotice })).toHaveCount(2);
    await notices.filter({ hasText: sentNotice }).first().click();
    await settled(head);
    await expect(field(head, "display_name")).toContainText(resultName);
    await expect(status(head)).toHaveAttribute("data-value", "requested");
    await expect(field(head, "value_display")).toHaveText(result.value.slice(0, -UNIT.length).trim());
    await expect(field(head, "unit_id")).toHaveText(UNIT);
    await expect(field(head, "lod")).toHaveText(LOD);
    await expect(field(head, "loq")).toHaveText(LOQ);
    await expect(alerts(head)).toHaveCount(0);
    await expect(field(head, "conclusion")).toBeHidden();
    await expect(button(head, "Approve")).toBeVisible();
    await expect(button(head, "Reject")).toBeVisible();
  });

  await step(head, "The head of department approves the result", async () => {
    await pressLabel(head, "Approve", { within: buttons(head) });
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    await expect(button(head, "Approve")).toHaveCount(0);
    await expect(button(head, "Reject")).toHaveCount(0);
    const signed = field(head, "signature_ids").locator(".o_data_row", { hasText: "Head of department" });
    await expect(signed).toHaveCount(1);
    await expect(signed).toContainText("Signed");
    await expect(signed).toContainText(HEAD);
    handOver("WF-04", { nitrateResultStatus: (await status(head).innerText()).trim(), nitrateResultApprovedBy: HEAD });
  });

  await step(head, "The reported result is approved; the sample waits for its other test", async () => {
    await field(head, "sample_test_id").locator("a").click();
    await settled(head);
    await expect(field(head, "parameter_id")).toHaveText(journey.parameterName);
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    await openTab(head, "bookings");
    await expect(bookingRow(head)).toHaveCount(1);
    await expect(bookingRow(head).locator("td[name=status]")).toHaveText("Done");
    handOver("WF-04", { nitrateTestStatus: (await status(head).innerText()).trim(), bookingStatus: (await bookingRow(head).locator("td[name=status]").innerText()).trim() });
    await field(head, "sample_id").locator("a").click();
    await settled(head);
    await expect(field(head, "code")).toHaveText(labCode);
    await expect(status(head)).toHaveAttribute("data-value", "testing");
    const tests = field(head, "test_ids").locator(".o_data_row");
    await expect(tests.filter({ hasText: journey.parameterName }).locator("td[name=status]")).toHaveText("Approved");
    await expect(tests.filter({ hasText: journey.leadParameterName }).locator("td[name=status]")).toHaveText(/^(Waiting|Assigned)$/);
    handOver("WF-04", { sampleStatusAfterNitrate: (await status(head).innerText()).trim() });
  });

  const reception = await as("demo.sample_delivery_staff");

  await step(reception, "The test request stays in testing until every test of its sample is approved", async () => {
    await openMenu(reception, ...TEST_REQUESTS);
    await search(reception, journey.requestSearch, { field: journey.requestSearchField });
    await expect(listed(reception, journey.requestCode)).toHaveCount(1);
    await expect(listed(reception, journey.requestCode).locator("td[name=status]")).toHaveText("Testing");
    handOver("WF-04", { requestStatusAfterNitrate: (await listed(reception, journey.requestCode).locator("td[name=status]").innerText()).trim() });
  });

  await step(tester, "The testing task of the approved test is finished", async () => {
    await openMenu(tester, ...FINISHED_TASKS);
    await search(tester, journey.parameterName);
    await expect(listed(tester, journey.nitrateTaskName)).toHaveCount(1);
    await expect(listed(tester, journey.nitrateTaskName).locator("td[name=status]")).toHaveText("Done");
    handOver("WF-04", { nitrateTaskStatus: (await listed(tester, journey.nitrateTaskName).locator("td[name=status]").innerText()).trim() });
  });

  const customer = await as(journey.customerLogin, journey.customerPassword);

  await step(customer, "The customer sees the order in testing, without the approved result", async () => {
    await openOrder(customer, journey.orderNumber);
    const order = customer.locator("main");
    await expect(order.locator("h1 + .badge")).toHaveText("Testing");
    await expect(order.locator("tbody tr", { hasText: journey.parameterName })).toHaveCount(1);
    await expect(order).not.toContainText(/12[.,]50?\s*mg\/L/);
    handOver("WF-04", { customerOrderStatusAfterNitrate: (await order.locator("h1 + .badge").innerText()).trim() });
  });
});
