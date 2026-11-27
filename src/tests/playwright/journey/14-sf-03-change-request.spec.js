import { expect, handOver, received, step, test } from "../support/journey";
import { field, listed, openListed, openMenu, openNotices, openRow, openTab, press, pressLabel, receiveNoticesInApplication, search, settled, status, toggleMessages, type } from "../support/odoo";
import { follow, openMyAccount } from "../support/portal";
import { download, reviewPdf, waitForPdf } from "../support/report";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const RESULTS = [LABORATORY, "sol_laboratory.menu_laboratory_results"];
const TEST_REPORTS = [...RESULTS, "sol_laboratory.menu_test_report"];
const REPORTS_TO_SIGN = [...RESULTS, "sol_laboratory.menu_test_report_to_sign"];
const REPORTS_TO_DELIVER = [...RESULTS, "sol_laboratory.menu_test_report_to_deliver"];
const CHANGE_REQUESTS = [LABORATORY, "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_change_request"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

const REQUESTER = "Vo Van Tai";

const buttons = (page) => page.locator(".o_form_view:visible .o_statusbar_buttons");
const shown = async (locator) => (await locator.innerText()).trim();

test("SF-03 Change request on a signed document", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "requestCode", "reportNumber");
  const first = journey.reportNumber;
  const change = `Reissue report ${first} of ${journey.customerName} as a replacement version.`;
  const reason = `Journey ${journey.tag}: the customer asks for a reissued report after the delivered copy was found incomplete.`;
  const replacement = {};

  const head = await as("demo.lab_head");
  const staff = await as("demo.sample_delivery_staff");

  // The journey's reports, newest version first.
  const reportsOfRequest = async (page) => {
    await openMenu(page, ...TEST_REPORTS);
    await search(page, journey.requestCode, { field: "Test Request" });
    return page.locator(".o_list_view:visible .o_data_row");
  };

  await step(head, "The Lab Head chooses to be notified in the application", async () => {
    await receiveNoticesInApplication(head);
  });

  await step(staff, "SF-03-A1: Sample delivery staff raise a change request on the issued report with what to change and why", async () => {
    await openMenu(staff, ...TEST_REPORTS);
    await openRow(staff, first);
    await expect(status(staff)).toHaveAttribute("data-value", "issued");
    await expect(field(staff, "version")).toHaveText("1");
    await pressLabel(staff, "Request a Change", { within: buttons(staff) });
    await expect(staff.locator(".modal:visible .modal-title")).toHaveText("Request a Change");
    await type(staff, "requested_change", change);
    await type(staff, "reason", reason);
    await press(staff, "action_raise");
    await expect(staff.locator(".modal:visible")).toHaveCount(0);
    await expect(staff).toHaveURL(/\/medilab\.change\.request\/\d+/);
    await expect(status(staff)).toHaveAttribute("data-value", "requested");
    await expect(field(staff, "document_name")).toHaveText(first);
    await expect(field(staff, "requested_by_id")).toHaveText(REQUESTER);
    await expect(field(staff, "code")).toHaveText(/^YCTD\.\d{4}\.\d+$/);
    replacement.changeRequest = await shown(field(staff, "code"));
    handOver("SF-03", { changeRequestCode: replacement.changeRequest });
  });

  // business-flows.md SF-03 has the lab head approve; nothing tells them a change request waits.
  await step(head, "The Lab Head is told that a change request waits for approval", async () => {
    const notices = await openNotices(head);
    await expect.soft(notices.filter({ hasText: replacement.changeRequest }), "the Lab Head receives a notice of the change request").not.toHaveCount(0, { timeout: 1000 });
    await toggleMessages(head);
    await openMenu(head, ...TASK_QUEUE);
    await search(head, replacement.changeRequest);
    await expect.soft(listed(head, replacement.changeRequest), "the Lab Head has a task for the change request").not.toHaveCount(0, { timeout: 1000 });
  });

  await step(head, "SF-03-A1: The Lab Head approves the change request on the report, which creates the new report version", async () => {
    await openMenu(head, ...CHANGE_REQUESTS);
    await search(head, replacement.changeRequest);
    const row = listed(head, replacement.changeRequest);
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=document_name]")).toHaveText(first);
    await expect(row.locator("td[name=status]")).toHaveText("Requested");
    await openListed(head, replacement.changeRequest);
    await expect(field(head, "requested_change")).toHaveText(change);
    await expect(field(head, "reason")).toHaveText(reason);
    await expect(field(head, "requested_by_id")).toHaveText(REQUESTER);
    await press(head, "action_sign");
    const confirmation = head.locator(".modal:visible");
    await expect(confirmation.locator(".modal-body")).toHaveText("Approve this change request? The last approval creates the new version.");
    await confirmation.locator(".modal-footer .btn-primary").click();
    await settled(head);
    await expect(status(head)).toHaveAttribute("data-value", "applied");
    await expect(buttons(head).locator("button[name=action_open_new_version]")).toBeVisible();
  });

  await step(head, "The Lab Head opens the new version: a draft replacing the issued report, with a fresh signing task", async () => {
    await press(head, "action_open_new_version");
    await expect(status(head)).toHaveAttribute("data-value", "draft");
    await expect(field(head, "request_id")).toHaveText(journey.requestCode);
    await expect(field(head, "version")).toHaveText("2");
    await expect(field(head, "replaces_id")).toHaveText(first);
    await openMenu(head, ...TASK_QUEUE);
    await search(head, journey.requestCode);
    const task = listed(head, `Draft report of ${journey.requestCode}`);
    await expect(task).toHaveCount(1);
    await expect(task.locator("td[name=type_id]")).toHaveText("Report signing");
    await expect(task.locator("td[name=status]")).toHaveText("Open");
  });

  const openReplacement = async () => {
    await openMenu(head, ...REPORTS_TO_SIGN);
    await search(head, journey.requestCode, { field: "Test Request" });
    await expect(listed(head, journey.requestCode)).toHaveCount(1);
    await openListed(head, journey.requestCode);
    await expect(field(head, "version")).toHaveText("2");
  };

  await step(head, "WF-06: The Lab Head finds the replacement in Reports to Sign and MediLab prepares its PDF", async () => {
    await openReplacement();
    await expect(field(head, "replaces_id")).toHaveText(first);
    replacement.refusal = await waitForPdf(head, openReplacement);
    expect.soft(replacement.refusal, "The replacement report's PDF is prepared").toBeNull();
  });
  if (replacement.refusal) return;

  await step(head, "WF-06: The Lab Head reviews the replacement's PDF, which reserves a new report number", async () => {
    await expect(field(head, "display_name")).toHaveText(/^PKQ\.\d{4}\.\d+$/);
    replacement.number = await shown(field(head, "display_name"));
    expect(replacement.number).not.toBe(first);
    await openTab(head, "candidates");
    await expect(field(head, "candidate_ids").locator(".o_data_row td[name=status]")).toHaveText(["Waiting for Review"]);
    expect(await reviewPdf(head)).toBe(`${replacement.number}.pdf`);
  });

  await step(head, "WF-06-A4: The Lab Head approves the replacement, which is issued without a digital signature", async () => {
    await press(head, "action_sign");
    await head.locator(".modal:visible .modal-footer .btn-primary").click();
    await settled(head);
    await expect(status(head)).toHaveAttribute("data-value", "issued");
    await expect(field(head, "display_name")).toHaveText(replacement.number);
    await expect(field(head, "attachment_id")).toHaveText(`${replacement.number}.pdf`);
    handOver("SF-03", { replacementReportNumber: replacement.number, replacedReportNumber: first });
  });

  await step(head, "Issuing the replacement marks the earlier report replaced; it keeps its number", async () => {
    const reports = await reportsOfRequest(head);
    await expect(reports).toHaveCount(2);
    const issued = reports.filter({ hasText: replacement.number });
    const replaced = reports.filter({ hasText: first });
    await expect(issued.locator("td[name=version]")).toHaveText("2");
    await expect(issued.locator("td[name=status]")).toHaveText("Issued");
    await expect(replaced.locator("td[name=version]")).toHaveText("1");
    await expect(replaced.locator("td[name=status]")).toHaveText("Replaced");
    handOver("SF-03", { replacedReportStatus: await shown(replaced.locator("td[name=status]")) });
  });

  await step(staff, "WF-06-A1: Sample delivery staff record the delivery of the replacement", async () => {
    await openMenu(staff, ...REPORTS_TO_DELIVER);
    await search(staff, replacement.number);
    const row = listed(staff, replacement.number);
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=delivery_method]")).toHaveText("In Person");
    await press(staff, "action_record_delivery", { within: row });
    await expect(listed(staff, replacement.number)).toHaveCount(0);
  });

  const customer = await as(journey.customerLogin, journey.customerPassword);

  await step(customer, "The customer's Test Reports list the replacement in place of the replaced report, and the customer downloads it", async () => {
    await openMyAccount(customer);
    await follow(customer, "/my/test-reports");
    const rows = customer.locator("main tbody tr", { hasText: journey.requestCode });
    await expect(rows).toHaveCount(1);
    await expect(rows.locator("td").first()).toHaveText(replacement.number);
    const pdf = await download(customer, () => rows.locator("a", { hasText: "Download" }).click());
    expect(pdf.name).toBe(`${replacement.number}.pdf`);
    expect(pdf.bytes.subarray(0, 5).toString()).toBe("%PDF-");
  });
});
