import { expect, handOver, outside, received, step, test } from "../support/journey";
import { closeDialog, field, listed, openListed, openMenu, openTab, press, pressLabel, save, search, settled, status, type } from "../support/odoo";
import { listedMoment } from "../support/schedule";

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
  const journey = received("tag", "parameterName", "methodCode", "sampleType", "testerName", "sampleLabCode", "nitrateTaskName", "leadParameterName", "bookingMachineName", "bookingStart");
  const labCode = journey.sampleLabCode;
  const resultName = `${labCode} – ${journey.parameterName}`;
  const result = {};

  const tester = await as("demo.tester");

  const openTask = async (page) => {
    await openMenu(page, ...MY_TASKS);
    await search(page, journey.parameterName);
    await expect(listed(page, journey.nitrateTaskName)).toHaveCount(1);
    await openListed(page, journey.nitrateTaskName);
    await expect(field(page, "sample_id")).toHaveText(labCode);
    await expect(field(page, "parameter_id")).toHaveText(journey.parameterName);
  };

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
  });

  // A machine is busy while a booking on it is in progress; the machine stores no busy status of its own.
  await step(tester, "The booked test starts: the test is in testing and its machine busy with the booking in progress", async () => {
    await press(tester, "action_start", { within: bookingRow(tester) });
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("In progress");
    await expect(status(tester)).toHaveAttribute("data-value", "testing");
    await expect(button(tester, "Enter Result")).toBeVisible();
  });

  await step(tester, "The tester records the result of the booking with the snapshotted unit and LOD/LOQ", async () => {
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

  await step(tester, "No regulation comparison is requested; the tester checks the measurement, which raises no warning", async () => {
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
  });

  await step(tester, "The tester sends and signs the result for Head of Department approval", async () => {
    await tester.locator(".o_breadcrumb .breadcrumb-item a", { hasText: journey.parameterName }).last().click();
    await settled(tester);
    await openTab(tester, "results");
    await expect(resultRow(tester)).toHaveCount(1);
    await resultRow(tester).locator("td[name=value_display]").click();
    await settled(tester);
    await expect(tester.locator(".modal:visible .o_form_view")).toBeVisible();
    await pressLabel(tester, "Send for Approval", { within: buttons(tester) });
    await expect(status(tester)).toHaveAttribute("data-value", "requested");
    await expect(button(tester, "Send for Approval")).toHaveCount(0);
    await expect(field(tester, "value").locator("input")).toHaveCount(0);
    await closeDialog(tester);
    await expect(resultRow(tester).locator("td[name=status]")).toHaveText("Awaiting Approval");
  });

  await step(tester, "Submitting the result completes the testing task and frees the machine", async () => {
    await openTab(tester, "bookings");
    await expect(bookingRow(tester).locator("td[name=status]")).toHaveText("Done");
    await openMenu(tester, ...MY_TASKS);
    await search(tester, journey.parameterName);
    await expect(listed(tester, journey.nitrateTaskName)).toHaveCount(0);
    await openMenu(tester, ...FINISHED_TASKS);
    await search(tester, journey.parameterName);
    await expect(listed(tester, journey.nitrateTaskName).locator("td[name=status]")).toHaveText("Done");
  });

  // test_result.sent goes to the head by the channel of their Odoo preference, e-mail for the demo users.
  await outside("The head of department is notified that the result waits for approval", "e-mail");

  const head = await as("demo.head_of_department");
  const resultsTile = head.locator(".o_task_tile_approve .o_task_row", { hasText: "Results to approve" });

  await step(head, "The head of department finds the result under Results to approve on the Tasks dashboard", async () => {
    await openMenu(head, TASKS);
    await expect(resultsTile.locator("strong")).toHaveText(/^[1-9]\d*$/);
    await resultsTile.locator("button.o_task_row_main").click();
    await settled(head);
    await expect(head.locator(".o_list_view:visible")).toBeVisible();
    await search(head, labCode, { field: "Sample" });
    const waiting = listed(head, journey.parameterName);
    await expect(waiting).toHaveCount(1);
    await expect(waiting.locator("td[name=value_display]")).toHaveText(result.value.slice(0, -UNIT.length).trim());
    await expect(waiting.locator("td[name=unit_id]")).toHaveText(UNIT);
    await expect(waiting.locator("td[name=entered_by_id]")).toHaveText(journey.testerName);
    await expect(waiting.locator("td[name=status]")).toHaveText("Awaiting Approval");
    await openListed(head, journey.parameterName);
    await expect(field(head, "display_name")).toContainText(resultName);
    await expect(status(head)).toHaveAttribute("data-value", "requested");
    await expect(field(head, "lod")).toHaveText(LOD);
    await expect(field(head, "loq")).toHaveText(LOQ);
    await expect(alerts(head)).toHaveCount(0);
  });

  await step(head, "The head of department approves the result", async () => {
    await pressLabel(head, "Approve", { within: buttons(head) });
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    await expect(button(head, "Approve")).toHaveCount(0);
    const signed = field(head, "signature_ids").locator(".o_data_row", { hasText: "Head of department" });
    await expect(signed).toContainText("Signed");
    await expect(signed).toContainText(HEAD);
    handOver("WF-04", {
      nitrateResult: result.value,
      nitrateResultLod: LOD,
      nitrateResultLoq: LOQ,
      nitrateResultStatus: (await status(head).innerText()).trim(),
      nitrateResultApprovedBy: HEAD,
    });
  });

  await step(head, "The reported result is approved; the sample waits for its other test", async () => {
    await field(head, "sample_test_id").locator("a").click();
    await settled(head);
    await expect(field(head, "parameter_id")).toHaveText(journey.parameterName);
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    const testStatus = (await status(head).innerText()).trim();
    await field(head, "sample_id").locator("a").click();
    await settled(head);
    await expect(field(head, "code")).toHaveText(labCode);
    await expect(status(head)).toHaveAttribute("data-value", "testing");
    const tests = field(head, "test_ids").locator(".o_data_row");
    await expect(tests.filter({ hasText: journey.parameterName }).locator("td[name=status]")).toHaveText("Approved");
    await expect(tests.filter({ hasText: journey.leadParameterName }).locator("td[name=status]")).toHaveText(/^(Waiting|Assigned)$/);
    handOver("WF-04", { nitrateTestStatus: testStatus, sampleStatusAfterNitrate: (await status(head).innerText()).trim() });
  });
});
