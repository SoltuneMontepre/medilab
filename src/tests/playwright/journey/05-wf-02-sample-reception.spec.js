import fs from "node:fs";
import { expect, handOver, received, step, test } from "../support/journey";
import { addLine, choose, closeDialog, dated, field, labDay, listed, newRecord, openListed, openMenu, openRow, openTab, pick, press, save, search, settled, shownDay, status, type, written } from "../support/odoo";
import { detail, openOrder } from "../support/portal";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const TEST_REQUESTS = [LABORATORY, "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_test_request"];
const SAMPLES = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample"];
const HANDOVER_RECORDS = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_handover_record"];
const SCAN_LABEL = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample_scan"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

const RECEPTION_STAFF = "Vo Van Tai";
const HANDED_OVER = "1 chai 500 ml";
const RECEIPT = { physicalState: "Liquid", amount: "500 ml", condition: "Good", storage: "Tủ lạnh 2" };
const ENGLISH_DAY = "mm/dd/yyyy";

const iso = (date) => date.toISOString().slice(0, 10);

test("WF-02 Sample reception and handover", async ({ as }) => {
  const journey = received("tag", "parameterName", "leadParameterName", "customerLogin", "customerPassword", "contactName", "orderNumber", "requestCode", "requestSearch", "requestSearchField", "expectedReturnDate", "sampleLabCode");
  const expectedReturn = written(new Date(`${journey.expectedReturnDate}T00:00:00Z`), ENGLISH_DAY);
  const labCode = journey.sampleLabCode;
  const handover = {};

  const reception = await as("demo.sample_delivery_staff");
  const requestSample = field(reception, "sample_ids", reception.locator(".o_action_manager")).locator(".o_data_row", { hasText: labCode });

  const findRequest = async () => {
    await openMenu(reception, ...TEST_REQUESTS);
    await search(reception, journey.requestSearch, { field: journey.requestSearchField });
    await expect(listed(reception, journey.requestCode)).toHaveCount(1);
  };

  await step(reception, "Sample delivery staff find the paid test request that expects the customer's sample", async () => {
    await findRequest();
    await expect(listed(reception, journey.requestCode).locator("td[name=status]")).toHaveText("Paid");
    await openListed(reception, journey.requestCode);
    await expect(status(reception)).toHaveAttribute("data-value", "paid");
    await expect(shownDay(reception, "committed_date")).toHaveAttribute("data-tooltip", expectedReturn);
    await expect(requestSample).toHaveCount(1);
    await expect(requestSample.locator("td[name=status]")).toHaveText("Expected");
  });

  await step(reception, "Sample delivery staff adjust the expected samples to the actual handover on a handover record", async () => {
    await openMenu(reception, ...HANDOVER_RECORDS);
    await newRecord(reception);
    await pick(reception, "request_id", journey.requestCode);
    await type(reception, "handed_over_by_name", journey.contactName);
    await pick(reception, "received_by_id", RECEPTION_STAFF);
    const line = await addLine(reception, "sample_ids");
    await pick(reception, "sample_id", labCode, line);
    await expect(line.locator("td[name=expected_count]")).toHaveText("1");
    await expect(field(reception, "actual_count", line).locator("input")).toHaveValue("1");
    await type(reception, "quantity", HANDED_OVER, line);
    await choose(reception, "condition", RECEIPT.condition, line);
    await save(reception);
    const recorded = field(reception, "sample_ids").locator(".o_data_row", { hasText: labCode });
    await expect(recorded.locator("td[name=actual_count]")).toHaveText("1");
    await expect(recorded.locator("td[name=extra_count]")).toHaveText("0");
    await expect(recorded.locator("td[name=missing_count]")).toHaveText("0");
    await expect(recorded.locator("td[name=condition]")).toHaveText(RECEIPT.condition);
    await expect(field(reception, "code")).toHaveText(/^BBGN\.\d{4}\.\d{4}$/);
    await expect(status(reception)).toHaveAttribute("data-value", "draft");
    handover.code = (await field(reception, "code").innerText()).trim();
    handOver("WF-02", { handoverRecordCode: handover.code, handedOverBy: journey.contactName });
  });

  await step(reception, "Sample delivery staff record the sample's condition, its receipt, the amount and the storage", async () => {
    await findRequest();
    await openListed(reception, journey.requestCode);
    await requestSample.locator("td[name=code]").click();
    const sample = reception.locator(".modal:visible");
    await expect(sample.locator(".o_form_view")).toBeVisible();
    await settled(reception);
    await expect(status(reception)).toHaveAttribute("data-value", "expected");
    await expect(sample.locator(".alert-info")).toContainText("then press Receive");
    await openTab(reception, "expected_sampling");
    await expect(field(reception, "expected_sample_count")).toHaveText("1");
    await openTab(reception, "handover_records");
    await expect(field(reception, "handover_line_ids").locator(".o_data_row")).toHaveCount(1);
    await expect(field(reception, "handover_line_ids").locator("td[name=record_id]")).toHaveText(handover.code);
    await choose(reception, "physical_state", RECEIPT.physicalState);
    await type(reception, "received_quantity", RECEIPT.amount);
    await choose(reception, "condition", RECEIPT.condition);
    await type(reception, "storage_location", RECEIPT.storage);
    await press(reception, "action_receive_entered");
    await expect(status(reception)).toHaveAttribute("data-value", "received");
    await expect(shownDay(reception, "received_at")).toHaveAttribute("data-tooltip", new RegExp(`^${written(labDay(), ENGLISH_DAY)} `));
    const receivedAt = iso(dated(await shownDay(reception, "received_at").getAttribute("data-tooltip"), ENGLISH_DAY));
    await expect(field(reception, "storage_location")).toHaveText(RECEIPT.storage);
    await openTab(reception, "receipt");
    await expect(field(reception, "received_quantity")).toHaveText(RECEIPT.amount);
    await expect(field(reception, "condition")).toHaveText(RECEIPT.condition);
    await expect(field(reception, "received_by_id")).toHaveText(RECEPTION_STAFF);
    await openTab(reception, "handovers");
    const departments = field(reception, "handover_ids").locator(".o_data_row");
    await expect(departments).toHaveCount(1);
    await expect(departments.locator("td[name=department_id]")).toHaveText(/\S/);
    await expect(departments.locator("td[name=received_at]")).toHaveText("");
    handover.department = (await departments.locator("td[name=department_id]").innerText()).trim();
    handOver("WF-02", {
      sampleLabCode: (await field(reception, "code").innerText()).trim(),
      sampleStatus: (await status(reception).innerText()).trim(),
      receivedAt,
      receivedBy: RECEPTION_STAFF,
      storageLocation: RECEIPT.storage,
      department: handover.department,
    });
    await closeDialog(reception);
    await expect(requestSample.locator("td[name=status]")).toHaveText("Received");
  });

  await step(reception, "The customer confirms the actual samples and signs the handover record", async () => {
    await openMenu(reception, ...HANDOVER_RECORDS);
    await openRow(reception, handover.code);
    await expect(field(reception, "code")).toHaveText(handover.code);
    const record = reception.locator(".o_form_view:visible");
    const signing = record.locator(".o_statusbar_buttons button:visible, .o_field_widget[name=signature_attachment_id]:not(.o_readonly_modifier)");
    await expect.soft(signing, "The handover record has a button or a field to take the customer's signature in the browser").not.toHaveCount(0, { timeout: 1000 });
    await expect(status(reception)).toHaveText(/\S/);
    handOver("WF-02", { handoverRecordStatus: (await status(reception).innerText()).trim() });
  });

  const customer = await as(journey.customerLogin, journey.customerPassword);

  await step(customer, "The customer finds the handover record of the received sample on the order", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(customer.locator("main h1 + .badge")).toHaveText("Waiting");
    await expect(detail(customer, "Expected return date")).toHaveText(expectedReturn);
    handOver("WF-02", { customerOrderStatusAfterReception: (await customer.locator("main h1 + .badge").innerText()).trim() });
    await expect.soft(customer.locator("main").getByText(handover.code), "The order's page shows the customer the handover record to confirm").not.toHaveCount(0, { timeout: 1000 });
  });

  await step(reception, "Sample delivery staff print the label of the received sample", async () => {
    await findRequest();
    await expect(listed(reception, journey.requestCode).locator("td[name=status]")).toHaveText("Sample Received");
    handOver("WF-02", { requestStatusAfterReception: (await listed(reception, journey.requestCode).locator("td[name=status]").innerText()).trim() });
    await openListed(reception, journey.requestCode);
    await expect(status(reception)).toHaveAttribute("data-value", "sample_received");
    // SF-07: the receipt keeps the return date the customer was promised.
    await expect(shownDay(reception, "committed_date")).toHaveAttribute("data-tooltip", expectedReturn);
    const [label] = await Promise.all([reception.waitForEvent("download"), press(reception, "action_print_labels")]);
    expect(label.suggestedFilename()).toBe(`Label ${labCode}.pdf`);
    expect(fs.readFileSync(await label.path()).subarray(0, 5).toString()).toBe("%PDF-");
    await expect(status(reception)).toHaveAttribute("data-value", "sample_received");
  });

  const head = await as("demo.head_of_department");

  await step(head, "The head of department scans the label to record the department's receipt", async () => {
    await openMenu(head, ...SCAN_LABEL);
    await type(head, "code", labCode);
    await press(head, "action_confirm");
    await expect(head.locator(".o_notification", { hasText: labCode })).toContainText(`${handover.department} received ${labCode}.`);
    // The scan opens again for the next label.
    await expect(field(head, "code").locator("input")).toHaveValue("");
    await closeDialog(head);
  });

  await step(head, "The testing tasks of the sample wait in the department's queue", async () => {
    await openMenu(head, ...TASK_QUEUE);
    await search(head, labCode);
    const queue = head.locator(".o_list_view:visible");
    await expect(queue.locator(".o_group_header")).toHaveCount(1);
    await expect(queue.locator(".o_group_header")).toContainText(handover.department);
    await expect(queue.locator(".o_data_row")).toHaveCount(2);
    const tasks = {};
    for (const [key, parameter] of [["nitrateTaskName", journey.parameterName], ["leadTaskName", journey.leadParameterName]]) {
      const task = listed(head, `${labCode}: ${parameter}`);
      await expect(task).toHaveCount(1);
      await expect(task.locator("td[name=type_id]")).toHaveText("Sample test");
      await expect(task.locator("td[name=assignee_id]")).toHaveText("");
      await expect(task.locator("td[name=status]")).toHaveText("Open");
      tasks[key] = (await task.locator("td[name=name]").innerText()).trim();
    }
    handOver("WF-02", tasks);
  });

  await step(head, "The head of department sees the sample received by the department", async () => {
    await openMenu(head, ...SAMPLES);
    await search(head, labCode);
    await expect(listed(head, labCode).locator("td[name=status]")).toHaveText("Received");
    await openListed(head, labCode);
    await expect(status(head)).toHaveAttribute("data-value", "received");
    await openTab(head, "handovers");
    const department = field(head, "handover_ids").locator(".o_data_row");
    await expect(department).toHaveCount(1);
    await expect(department.locator("td[name=department_id]")).toHaveText(handover.department);
    await expect(department.locator("td[name=received_at]")).toHaveText(/\S/);
    await expect(department.locator("td[name=received_by_id]")).toHaveText(/\S/);
    handOver("WF-02", { departmentReceivedBy: (await department.locator("td[name=received_by_id]").innerText()).trim() });
  });
});
