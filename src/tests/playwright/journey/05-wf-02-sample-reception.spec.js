import fs from "node:fs";
import { expect, handOver, outside, received, step, test } from "../support/journey";
import { addLine, choose, closeDialog, dated, field, listed, newRecord, openListed, openMenu, openTab, pick, press, save, search, settled, shownDay, status, type } from "../support/odoo";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const TEST_REQUESTS = [LABORATORY, "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_test_request"];
const HANDOVER_RECORDS = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_handover_record"];
const SCAN_LABEL = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample_scan"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

const RECEPTION_STAFF = "Vo Van Tai";
const HANDED_OVER = "1 chai 500 ml";
const RECEIPT = { physicalState: "Liquid", amount: "500 ml", condition: "Good", storage: "Tủ lạnh 2" };
const ENGLISH_DAY = "mm/dd/yyyy";

const iso = (date) => date.toISOString().slice(0, 10);

test("WF-02 Sample reception and handover", async ({ as }) => {
  const journey = received("tag", "parameterName", "leadParameterName", "contactName", "requestCode", "requestSearch", "requestSearchField", "sampleLabCode");
  const labCode = journey.sampleLabCode;
  const handover = {};

  const reception = await as("demo.sample_delivery_staff");
  const requestSample = field(reception, "sample_ids", reception.locator(".o_action_manager")).locator(".o_data_row", { hasText: labCode });

  const openRequest = async () => {
    await openMenu(reception, ...TEST_REQUESTS);
    await search(reception, journey.requestSearch, { field: journey.requestSearchField });
    await expect(listed(reception, journey.requestCode)).toHaveCount(1);
    await openListed(reception, journey.requestCode);
  };

  // The sample opens in a dialog over its test request.
  const openSample = async () => {
    await requestSample.locator("td[name=code]").click();
    await expect(reception.locator(".modal:visible .o_form_view")).toBeVisible();
    await settled(reception);
  };

  await step(reception, "The customer brings the sample; sample delivery staff find the paid test request that expects it", async () => {
    await openRequest();
    await expect(status(reception)).toHaveAttribute("data-value", "paid");
    await expect(requestSample).toHaveCount(1);
    await expect(requestSample.locator("td[name=status]")).toHaveText("Expected");
  });

  await step(reception, "Sample delivery staff adjust the expected samples to the actual handover and record the differences", async () => {
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
    handover.code = (await field(reception, "code").innerText()).trim();
    handOver("WF-02", { handoverRecordCode: handover.code, handedOverBy: journey.contactName });
  });

  await step(reception, "Sample delivery staff record the sample's condition, its receipt, the amount and the storage", async () => {
    await openRequest();
    await openSample();
    const sample = reception.locator(".modal:visible");
    await expect(status(reception)).toHaveAttribute("data-value", "expected");
    await openTab(reception, "handover_records");
    await expect(field(reception, "handover_line_ids").locator("td[name=record_id]")).toHaveText(handover.code);
    await choose(reception, "physical_state", RECEIPT.physicalState);
    await type(reception, "received_quantity", RECEIPT.amount);
    await choose(reception, "condition", RECEIPT.condition);
    await type(reception, "storage_location", RECEIPT.storage);
    await press(reception, "action_receive_entered", { within: sample });
    await expect(status(reception)).toHaveAttribute("data-value", "received");
    await expect(field(reception, "storage_location")).toHaveText(RECEIPT.storage);
    await openTab(reception, "receipt");
    await expect(field(reception, "received_quantity")).toHaveText(RECEIPT.amount);
    await expect(field(reception, "condition")).toHaveText(RECEIPT.condition);
    await expect(field(reception, "received_by_id")).toHaveText(RECEPTION_STAFF);
    handOver("WF-02", {
      sampleStatus: (await status(reception).innerText()).trim(),
      receivedAt: iso(dated(await shownDay(reception, "received_at").getAttribute("data-tooltip"), ENGLISH_DAY)),
      receivedBy: RECEPTION_STAFF,
      storageLocation: RECEIPT.storage,
    });
    await closeDialog(reception);
    await expect(requestSample.locator("td[name=status]")).toHaveText("Received");
  });

  // Medilab Mobile: staff give the phone to the customer, who signs the draft handover record on its screen.
  await outside("The customer confirms the actual samples and signs the handover record", "Medilab Mobile");

  await step(reception, "Sample delivery staff print the label and hand the sample to the department that tests it", async () => {
    await openRequest();
    await expect(status(reception)).toHaveAttribute("data-value", "sample_received");
    const [label] = await Promise.all([reception.waitForEvent("download"), press(reception, "action_print_labels")]);
    expect(label.suggestedFilename()).toBe(`Label ${labCode}.pdf`);
    expect(fs.readFileSync(await label.path()).subarray(0, 5).toString()).toBe("%PDF-");
    await openSample();
    await openTab(reception, "handovers");
    const departments = field(reception, "handover_ids").locator(".o_data_row");
    await expect(departments).toHaveCount(1);
    await expect(departments.locator("td[name=department_id]")).toHaveText(/\S/);
    await expect(departments.locator("td[name=received_at]")).toHaveText("");
    handover.department = (await departments.locator("td[name=department_id]").innerText()).trim();
    await closeDialog(reception);
  });

  const head = await as("demo.head_of_department");

  await step(head, "The head of department scans the label to record the department's receipt", async () => {
    await openMenu(head, ...SCAN_LABEL);
    await type(head, "code", labCode);
    await press(head, "action_confirm");
    await expect(head.locator(".o_notification", { hasText: labCode })).toContainText(`${handover.department} received ${labCode}.`);
    // The scan opens again, empty, for the next label.
    await expect(field(head, "code").locator("input")).toHaveValue("");
    await closeDialog(head);
    handOver("WF-02", { department: handover.department });
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
      await expect(task.locator("td[name=assignee_id]")).toHaveText("");
      await expect(task.locator("td[name=status]")).toHaveText("Open");
      tasks[key] = (await task.locator("td[name=name]").innerText()).trim();
    }
    handOver("WF-02", tasks);
  });
});
