import { expect, handOver, outside, received, step, test } from "../support/journey";
import { closeDialog, field, listed, openListed, openMenu, openTab, press, pressLabel, save, search, settled, status, type } from "../support/odoo";
import { follow, openMyAccount } from "../support/portal";
import { download, pdfText, printed, reviewPdf, waitForPdf } from "../support/report";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const RESULTS = [LABORATORY, "sol_laboratory.menu_laboratory_results"];
const TEST_RESULTS = [...RESULTS, "sol_laboratory.menu_test_result"];
const TEST_REPORTS = [...RESULTS, "sol_laboratory.menu_test_report"];
const REPORTS_TO_SIGN = [...RESULTS, "sol_laboratory.menu_test_report_to_sign"];
const REPORTS_TO_DELIVER = [...RESULTS, "sol_laboratory.menu_test_report_to_deliver"];
const CHANGE_REQUESTS = [LABORATORY, "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_change_request"];
const TASKS = "sol_laboratory.menu_tasks_root";
const TASK_QUEUE = [TASKS, "sol_laboratory.menu_task_queue"];
const MY_TASKS = [TASKS, "sol_laboratory.menu_task_mine"];

const CORRECTED = "12.4";
const UNIT = "mg/L";

const buttons = (page) => page.locator(".o_form_view:visible .o_statusbar_buttons").last();
const button = (page, label) => buttons(page).getByRole("button", { name: label, exact: true });
const shown = async (locator) => (await locator.innerText()).trim();

test("SF-03 Change request on a signed document", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "requestCode", "sampleLabCode", "parameterName", "nitrateTaskName", "testerName", "nitrateResult", "reportNumber");
  const labCode = journey.sampleLabCode;
  const first = journey.reportNumber;
  const change = `Correct the measured value of ${journey.parameterName} on ${labCode} from ${journey.nitrateResult} to ${CORRECTED}0 ${UNIT}.`;
  const reason = `Journey ${journey.tag}: the absorbance was read against the wrong calibration standard.`;
  const correction = {};

  const tester = await as("demo.tester");

  await step(tester, "A tester raises a change request on the completed result with what to change and why", async () => {
    await openMenu(tester, ...TEST_RESULTS);
    await search(tester, labCode, { field: "Sample" });
    await expect(listed(tester, journey.parameterName)).toHaveCount(1);
    await openListed(tester, journey.parameterName);
    await expect(status(tester)).toHaveAttribute("data-value", "approved");
    await expect(field(tester, "version")).toHaveText("1");
    correction.result = await shown(field(tester, "display_name"));
    await pressLabel(tester, "Request a Change", { within: buttons(tester) });
    await expect(tester.locator(".modal:visible .modal-title")).toHaveText("Request a Change");
    await type(tester, "requested_change", change);
    await type(tester, "reason", reason);
    await press(tester, "action_raise");
    await expect(tester.locator(".modal:visible")).toHaveCount(0);
    await expect(status(tester)).toHaveAttribute("data-value", "requested");
    await expect(field(tester, "document_name")).toHaveText(correction.result);
    await expect(field(tester, "requested_by_id")).toHaveText(journey.testerName);
    await expect(field(tester, "code")).toHaveText(/^YCTD\.\d{4}\.\d+$/);
    correction.code = await shown(field(tester, "code"));
  });

  await step(tester, "SF-03-A3: The correction of a result in an issued report creates that report's change request", async () => {
    await expect(field(tester, "report_change_request_id")).toHaveText(/^YCTD\.\d{4}\.\d+$/);
    correction.reportCode = await shown(field(tester, "report_change_request_id"));
    expect(correction.reportCode).not.toBe(correction.code);
    handOver("SF-03", { changeRequestCode: correction.code, reportChangeRequestCode: correction.reportCode });
  });

  const head = await as("demo.lab_head");

  const approveChangeRequest = async (code, document) => {
    await openMenu(head, ...CHANGE_REQUESTS);
    await search(head, code);
    const row = listed(head, code);
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=document_name]")).toHaveText(document);
    await expect(row.locator("td[name=status]")).toHaveText("Requested");
    await openListed(head, code);
    await press(head, "action_sign");
    await head.locator(".modal:visible .modal-footer .btn-primary").click();
    await settled(head);
  };

  await step(head, "The change-request chain signs the result's change request: the Lab Head approves it, which creates the unsigned corrected version", async () => {
    await approveChangeRequest(correction.code, correction.result);
    await expect(field(head, "requested_change")).toHaveText(change);
    await expect(status(head)).toHaveAttribute("data-value", "applied");
    await expect(button(head, "Open New Version")).toBeVisible();
  });

  await step(head, "SF-03-A3: The Lab Head approves the report's change request, which waits for the corrected result", async () => {
    await approveChangeRequest(correction.reportCode, first);
    await expect(status(head)).toHaveAttribute("data-value", "approved");
  });

  // The sample test lists the replaced signed version beside the new one.
  const resultRow = (page) => field(page, "result_ids").locator(".o_data_row").filter({ hasNot: page.locator("td[name=status]", { hasText: /^Approved$/ }) });

  await step(tester, "The correction is queued in the department: the tester claims it and corrects the new version", async () => {
    await openMenu(tester, ...TASK_QUEUE);
    await search(tester, journey.parameterName);
    const task = listed(tester, journey.nitrateTaskName);
    await expect(task).toHaveCount(1);
    await press(tester, "action_claim", { within: task });
    await openMenu(tester, ...MY_TASKS);
    await search(tester, journey.parameterName);
    await openListed(tester, journey.nitrateTaskName);
    await expect(field(tester, "sample_id")).toHaveText(labCode);
    await expect(status(tester)).toHaveAttribute("data-value", "testing");
    await openTab(tester, "results");
    await expect(resultRow(tester)).toHaveCount(1);
    await resultRow(tester).locator("td[name=value_display]").click();
    await settled(tester);
    await expect(tester.locator(".modal:visible .o_form_view")).toBeVisible();
    await expect(field(tester, "version")).toHaveText("2");
    await expect(status(tester)).toHaveAttribute("data-value", "none");
    await type(tester, "value", CORRECTED);
    await save(tester);
    await expect(field(tester, "value_display")).toHaveText(/^12[.,]40$/);
    correction.value = `${await shown(field(tester, "value_display"))} ${UNIT}`;
  });

  await step(tester, "The tester sends and signs the corrected result for Head of Department approval", async () => {
    await pressLabel(tester, "Send for Approval", { within: buttons(tester) });
    await expect(status(tester)).toHaveAttribute("data-value", "requested");
    await closeDialog(tester);
    await expect(resultRow(tester).locator("td[name=status]")).toHaveText("Awaiting Approval");
  });

  await outside("The head of department is notified that the corrected result waits for approval", "e-mail");

  const headOfDepartment = await as("demo.head_of_department");
  const resultsTile = headOfDepartment.locator(".o_task_tile_approve .o_task_row", { hasText: "Results to approve" });

  await step(headOfDepartment, "The head of department approves the corrected result", async () => {
    await openMenu(headOfDepartment, TASKS);
    await resultsTile.locator("button.o_task_row_main").click();
    await settled(headOfDepartment);
    await search(headOfDepartment, labCode, { field: "Sample" });
    await expect(listed(headOfDepartment, journey.parameterName)).toHaveCount(1);
    await openListed(headOfDepartment, journey.parameterName);
    await expect(field(headOfDepartment, "version")).toHaveText("2");
    await pressLabel(headOfDepartment, "Approve", { within: buttons(headOfDepartment) });
    await expect(status(headOfDepartment)).toHaveAttribute("data-value", "approved");
    handOver("SF-03", { correctedNitrateResult: correction.value });
  });

  const openReplacement = async () => {
    await openMenu(head, ...REPORTS_TO_SIGN);
    await search(head, journey.requestCode, { field: "Test Request" });
    await expect(listed(head, journey.requestCode)).toHaveCount(1);
    await openListed(head, journey.requestCode);
    await expect(field(head, "version")).toHaveText("2");
  };

  await outside("The Lab Head is notified that the replacement draft waits for review", "e-mail");

  await step(head, "With every corrected result approved, MediLab prepares the replacement draft with a fresh signing task", async () => {
    await openMenu(head, ...CHANGE_REQUESTS);
    await search(head, correction.reportCode);
    await expect(listed(head, correction.reportCode).locator("td[name=status]")).toHaveText("Applied");
    await openMenu(head, ...TASK_QUEUE);
    await search(head, journey.requestCode);
    const task = listed(head, `Draft report of ${journey.requestCode}`);
    await expect(task).toHaveCount(1);
    await expect(task.locator("td[name=status]")).toHaveText("Open");
    await openListed(head, `Draft report of ${journey.requestCode}`);
    await expect(status(head)).toHaveAttribute("data-value", "draft");
    await expect(field(head, "version")).toHaveText("2");
    await expect(field(head, "replaces_id")).toHaveText(first);
    const corrected = field(head, "result_ids").locator(".o_data_row", { hasText: journey.parameterName });
    await expect(corrected.locator("td[name=value_display]")).toHaveText(correction.value.split(" ")[0]);
    await expect(corrected.locator("td[name=status]")).toHaveText("Approved");
  });

  await step(head, "WF-06: MediLab prepares the replacement's PDF, which reserves a new number, and the Lab Head reviews it", async () => {
    await waitForPdf(head, openReplacement);
    await expect(field(head, "display_name")).toHaveText(/^PKQ\.\d{4}\.\d+$/);
    correction.number = await shown(field(head, "display_name"));
    expect(correction.number).not.toBe(first);
    await openTab(head, "candidates");
    await expect(field(head, "candidate_ids").locator(".o_data_row td[name=status]")).toHaveText(["Waiting for Review"]);
    expect(await reviewPdf(head)).toBe(`${correction.number}.pdf`);
  });

  await step(head, "WF-06-A4: The Lab Head approves the replacement, which is issued without a digital signature", async () => {
    await press(head, "action_sign");
    await head.locator(".modal:visible .modal-footer .btn-primary").click();
    await settled(head);
    await expect(status(head)).toHaveAttribute("data-value", "issued");
    await expect(field(head, "display_name")).toHaveText(correction.number);
    await expect(field(head, "attachment_id")).toHaveText(`${correction.number}.pdf`);
  });

  await step(head, "The new version replaces the issued report, which stays readable with its file", async () => {
    await openMenu(head, ...TEST_REPORTS);
    await search(head, journey.requestCode, { field: "Test Request" });
    const reports = head.locator(".o_list_view:visible .o_data_row");
    await expect(reports).toHaveCount(2);
    await expect(reports.filter({ hasText: correction.number }).locator("td[name=status]")).toHaveText("Issued");
    const replaced = reports.filter({ hasText: first });
    await expect(replaced.locator("td[name=status]")).toHaveText("Replaced");
    await openListed(head, first);
    await expect(status(head)).toHaveAttribute("data-value", "replaced");
    await expect(field(head, "attachment_id")).toHaveText(`${first}.pdf`);
    handOver("SF-03", { replacementReportNumber: correction.number, replacedReportNumber: first, replacedReportStatus: (await status(head).innerText()).trim() });
  });

  await outside("The customer is notified that the replacement report is released", "e-mail");

  const staff = await as("demo.sample_delivery_staff");

  await step(staff, "WF-06-A1: Sample delivery staff hand the replacement over in person and record the delivery", async () => {
    await openMenu(staff, ...REPORTS_TO_DELIVER);
    await search(staff, correction.number);
    const row = listed(staff, correction.number);
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=delivery_method]")).toHaveText("In Person");
    await press(staff, "action_record_delivery", { within: row });
    await expect(listed(staff, correction.number)).toHaveCount(0);
  });

  const customer = await as(journey.customerLogin, journey.customerPassword);

  await step(customer, "The portal offers the replacement in place of the replaced report, and the customer downloads it", async () => {
    await openMyAccount(customer);
    await follow(customer, "/my/test-reports");
    const rows = customer.locator("main tbody tr", { hasText: journey.requestCode });
    await expect(rows).toHaveCount(1);
    await expect(rows.locator("td").first()).toHaveText(correction.number);
    const pdf = await download(customer, () => rows.locator("a", { hasText: "Download" }).click());
    expect(pdf.name).toBe(`${correction.number}.pdf`);
    expect(printed(correction.value.split(" ")[0]).test(pdfText(pdf.bytes)), "the replacement prints the corrected result").toBe(true);
  });
});
