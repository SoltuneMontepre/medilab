import { expect, handOver, received, step, test } from "../support/journey";
import { field, labDay, listed, openListed, openMenu, openRow, openTab, press, search, settled, status, written } from "../support/odoo";
import { follow, loads, openHeader, openMyAccount, openOrder, send } from "../support/portal";
import { download, pdfText, printed, reviewPdf, waitForPdf } from "../support/report";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const RESULTS = [LABORATORY, "sol_laboratory.menu_laboratory_results"];
const TEST_REPORTS = [...RESULTS, "sol_laboratory.menu_test_report"];
const REPORTS_TO_SIGN = [...RESULTS, "sol_laboratory.menu_test_report_to_sign"];
const REPORTS_TO_DELIVER = [...RESULTS, "sol_laboratory.menu_test_report_to_deliver"];
const TEST_REQUESTS = [LABORATORY, "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_test_request"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];
const SALES_ORDERS = ["sale.sale_menu_root", "sol_commerce.menu_sale_order"];

const DELIVERER = "Vo Van Tai";
const TEMPLATE = "Phiếu kết quả nước uống song ngữ";
const ENGLISH_DAY = "mm/dd/yyyy";

const buttons = (page) => page.locator(".o_form_view:visible .o_statusbar_buttons");
const alerts = (page) => page.locator(".o_form_view:visible .alert:visible");
const shown = async (locator) => (await locator.innerText()).trim();

test("WF-06 Report signing, release and delivery", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "contactName", "orderNumber", "requestCode", "requestSearch", "requestSearchField", "sampleLabCode", "parameterName", "leadParameterName", "nitrateResult", "leadResult", "paidInFull");
  const draftTitle = `Draft report of ${journey.requestCode}`;
  const report = {};

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const orderStatus = customer.locator("main h1 + span.badge");

  await step(customer, "With all its samples completed, the customer's order reads Completed before its report is issued", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(orderStatus).toHaveText("Completed");
    handOver("WF-06", { orderStatusBeforeReport: await shown(orderStatus) });
  });

  // Results released is sent by e-mail unless the customer also chooses the portal for it.
  await step(customer, "The customer chooses to be told in the portal when results are released", async () => {
    await openHeader(customer, "/my/account");
    await follow(customer, "/my/notifications");
    await customer.locator("input[name='result.released:popup']").check();
    await send(customer, "/my/notifications");
    await expect(customer.locator("#notifications-saved")).toBeVisible();
    await expect(customer.locator("input[name='result.released:popup']")).toBeChecked();
  });

  const sales = await as("demo.sales");

  await step(sales, "Sales sees the order still confirmed until its report is issued", async () => {
    await openMenu(sales, ...SALES_ORDERS);
    await openRow(sales, journey.orderNumber);
    await expect(status(sales)).toHaveAttribute("data-value", "confirmed");
  });

  const head = await as("demo.lab_head");

  const openDraft = async () => {
    await openMenu(head, ...REPORTS_TO_SIGN);
    await search(head, journey.requestSearch, { field: journey.requestSearchField });
    await expect(listed(head, journey.requestCode)).toHaveCount(1);
    await openListed(head, journey.requestCode);
    await expect(field(head, "request_id")).toHaveText(journey.requestCode);
  };

  await step(head, "The Lab Head finds the signing task of the draft report in the department queue", async () => {
    await openMenu(head, ...TASK_QUEUE);
    await search(head, journey.requestCode);
    const task = listed(head, draftTitle);
    await expect(task).toHaveCount(1);
    await expect(task.locator("td[name=type_id]")).toHaveText("Report signing");
    await expect(task.locator("td[name=status]")).toHaveText("Open");
    await openListed(head, draftTitle);
    await expect(field(head, "request_id")).toHaveText(journey.requestCode);
    await expect(field(head, "version")).toHaveText("1");
  });

  await step(head, "The Lab Head opens the draft report from Reports to Sign: bilingual, delivered in person, with both approved results", async () => {
    await openMenu(head, ...REPORTS_TO_SIGN);
    await search(head, journey.requestSearch, { field: journey.requestSearchField });
    const row = listed(head, journey.requestCode);
    await expect(row).toHaveCount(1);
    // The report takes its reserved number once its PDF is prepared.
    await expect(row.locator("td[name=display_name]")).toHaveText(new RegExp(`^(${draftTitle}|PKQ\\.\\d{4}\\.\\d+)$`));
    await expect(row.locator("td[name=version]")).toHaveText("1");
    await expect(row.locator("td[name=language]")).toHaveText("Bilingual");
    await expect(row.locator("td[name=status]")).toHaveText("Draft");
    await openListed(head, journey.requestCode);
    await expect(status(head)).toHaveAttribute("data-value", "draft");
    await expect(field(head, "customer_id")).toHaveText(journey.customerName);
    await expect(field(head, "language")).toHaveText("Bilingual");
    await expect(field(head, "delivery_method")).toHaveText("In Person");
    await expect(field(head, "recipient_id")).toContainText(journey.contactName);
    await expect(head.locator(".o_form_view:visible .alert-warning")).toHaveCount(0);
    const results = field(head, "result_ids").locator(".o_data_row");
    await expect(results).toHaveCount(2);
    for (const [parameter, value] of [[journey.parameterName, journey.nitrateResult], [journey.leadParameterName, journey.leadResult]]) {
      const result = results.filter({ hasText: parameter });
      await expect(result.locator("td[name=sample_id]")).toHaveText(journey.sampleLabCode);
      await expect(result.locator("td[name=value_display]")).toHaveText(value.split(" ")[0]);
      await expect(result.locator("td[name=unit_id]")).toHaveText(value.split(" ").slice(1).join(" "));
      await expect(result.locator("td[name=status]")).toHaveText("Approved");
    }
  });

  await step(head, "MediLab prepares the report's PDF with its reserved number for the Lab Head's review", async () => {
    await waitForPdf(head, openDraft);
  });

  await step(head, "The Lab Head reviews the prepared PDF with its reserved number and the approved results", async () => {
    await expect(alerts(head)).toHaveText(["A prepared draft PDF waits for the lab head's review. It is not issued and not digitally signed."]);
    await expect(field(head, "display_name")).toHaveText(/^PKQ\.\d{4}\.\d+$/);
    report.number = await shown(field(head, "display_name"));
    await openTab(head, "candidates");
    const prepared = field(head, "candidate_ids").locator(".o_data_row");
    await expect(prepared).toHaveCount(1);
    await expect(prepared.locator("td[name=report_number]")).toHaveText(report.number);
    await expect(prepared.locator("td[name=template_version_id]")).toContainText(TEMPLATE);
    await expect(prepared.locator("td[name=status]")).toHaveText("Waiting for Review");
    expect(await reviewPdf(head)).toBe(`${report.number}.pdf`);
    await expect(buttons(head).locator("button[name=action_sign]")).toBeVisible();
  });

  await step(head, "WF-06-A4: The Lab Head gives final internal approval; with digital signing disabled the reviewed PDF is issued unsigned", async () => {
    await press(head, "action_sign");
    const confirmation = head.locator(".modal:visible");
    await expect(confirmation.locator(".modal-body")).toHaveText("Sign the prepared PDF you reviewed? The last signature issues it once its PDF is stored.");
    await confirmation.locator(".modal-footer .btn-primary").click();
    await settled(head);
    await expect(status(head)).toHaveAttribute("data-value", "issued");
    await expect(field(head, "display_name")).toHaveText(report.number);
    await expect(field(head, "attachment_id")).toHaveText(`${report.number}.pdf`);
    await expect(field(head, "issued_at")).toBeVisible();
    await expect(field(head, "digital_signature_id")).toBeHidden();
    await expect(alerts(head)).toHaveCount(0);
    await expect(buttons(head).locator("button[name=action_sign], button[name=action_open_candidate]")).toHaveCount(0);
    await openTab(head, "candidates");
    await expect(field(head, "candidate_ids").locator(".o_data_row td[name=status]")).toHaveText(["Issued"]);
    handOver("WF-06", {
      reportNumber: report.number,
      reportStatus: (await status(head).innerText()).trim(),
      reportLanguage: await shown(field(head, "language")),
    });
  });

  const checkPrinted = (bytes) => {
    expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
    const text = pdfText(bytes);
    const named = {
      "report number": report.number,
      customer: journey.customerName,
      "test request": journey.requestCode,
      sample: journey.sampleLabCode,
      "nitrate parameter": journey.parameterName,
      "nitrate result": journey.nitrateResult.split(" ")[0],
      "lead parameter": journey.leadParameterName,
      "lead result": journey.leadResult.split(" ")[0],
    };
    const missing = Object.entries(named).filter(([, value]) => !printed(value).test(text)).map(([what, value]) => `${what} ${value}`);
    expect(missing, "the PDF prints the report number, the customer, the sample and both results").toEqual([]);
    return text;
  };

  await step(head, "The Lab Head downloads the issued PDF, which names the customer and both results", async () => {
    const pdf = await download(head, () => buttons(head).locator("button[name=action_download]").click());
    expect(pdf.name).toBe(`${report.number}.pdf`);
    const text = checkPrinted(pdf.bytes);
    // SF-06 made the nitrate test accredited; its mark would follow the parameter's name, as (*) follows a registered one.
    const name = journey.parameterName.replace(/\s+/g, "");
    const mark = text.slice(text.indexOf(name) + name.length).match(/^\([^)]{1,3}\)/)?.[0] ?? "";
    expect.soft(mark, "the report marks the accredited nitrate test").not.toBe("");
    handOver("WF-06", { nitrateMarkOnReport: mark });
  });

  await step(head, "Issue makes the reserved number official: the report leaves Reports to Sign and the test request is reported", async () => {
    await openMenu(head, ...REPORTS_TO_SIGN);
    await search(head, journey.requestSearch, { field: journey.requestSearchField });
    await expect(listed(head, journey.requestCode)).toHaveCount(0);
    await openMenu(head, ...TEST_REQUESTS);
    await search(head, journey.requestCode);
    const request = listed(head, journey.requestCode);
    await expect(request).toHaveCount(1);
    await expect(request.locator("td[name=status]")).toHaveText("Reported");
    handOver("WF-06", { requestStatusAfterReport: await shown(request.locator("td[name=status]")) });
  });

  const staff = await as("demo.sample_delivery_staff");

  await step(staff, "WF-06-A1: Sample delivery staff hand the report over in person and record the delivery, which sends no e-mail", async () => {
    await openMenu(staff, ...REPORTS_TO_DELIVER);
    await search(staff, report.number);
    const row = listed(staff, report.number);
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=request_id]")).toHaveText(journey.requestCode);
    await expect(row.locator("td[name=customer_id]")).toHaveText(journey.customerName);
    await expect(row.locator("td[name=delivery_method]")).toHaveText("In Person");
    await expect(row.locator("td[name=recipient_id]")).toContainText(journey.contactName);
    const delivery = await shown(row.locator("td[name=delivery_method]"));
    await press(staff, "action_record_delivery", { within: row });
    await expect(listed(staff, report.number)).toHaveCount(0);
    await expect(staff.locator(".modal:visible")).toHaveCount(0);
    handOver("WF-06", { reportDelivery: delivery });
  });

  await step(staff, "Sample delivery staff find the delivery recorded on the report and the sample retained after the report", async () => {
    await openMenu(staff, ...TEST_REPORTS);
    await openRow(staff, report.number);
    await expect(status(staff)).toHaveAttribute("data-value", "issued");
    await expect(field(staff, "delivered_by_id")).toHaveText(DELIVERER);
    await expect(field(staff, "delivered_at")).toBeVisible();
    await expect(buttons(staff).locator("button[name=action_record_delivery]")).toHaveCount(0);
    await expect(buttons(staff).getByRole("button", { name: "Request a Change", exact: true })).toBeVisible();
    await openTab(staff, "samples");
    const sample = field(staff, "sample_ids").locator(".o_data_row", { hasText: journey.sampleLabCode });
    await expect(sample).toHaveCount(1);
    await expect(sample.locator("td[name=status]")).toHaveText("Retained");
    handOver("WF-06", { sampleStatusAfterReport: await shown(sample.locator("td[name=status]")), reportDeliveredBy: DELIVERER });
  });

  await step(customer, "The customer is notified in the portal that the results are ready", async () => {
    await openHeader(customer, "/my/account");
    await follow(customer, "/my/notifications");
    // The notice is titled with the report's number.
    const notice = customer.locator("#portal-notifications li", { hasText: report.number });
    await expect(notice).toHaveCount(1);
    await loads(customer, () => notice.locator("a").click());
    await expect(customer.locator("#notification-subject")).toHaveText(report.number);
    await expect(customer.locator("#notification-body")).toHaveText(`The results of order ${journey.orderNumber} are ready. Download report ${report.number} from your portal.`);
  });

  await step(customer, "The customer finds the report under Test Reports in My account and downloads the issued PDF", async () => {
    await openMyAccount(customer);
    await follow(customer, "/my/test-reports");
    const row = customer.locator("main tbody tr", { hasText: report.number });
    await expect(row).toHaveCount(1);
    await expect(row.locator("td").nth(1)).toHaveText(journey.requestCode);
    await expect(row.locator("td").nth(2)).toHaveText(written(labDay(), ENGLISH_DAY));
    const pdf = await download(customer, () => row.locator("a", { hasText: "Download" }).click());
    expect(pdf.name).toBe(`${report.number}.pdf`);
    checkPrinted(pdf.bytes);
  });

  await step(customer, "The customer sees the order completed and can rate it", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(orderStatus).toHaveText("Completed");
    await expect(customer.locator(`main form[action$='/feedback']`)).toBeVisible();
    handOver("WF-06", { orderStatusAfterReport: await shown(orderStatus) });
  });

  await step(sales, "Issue completes the order for Sales", async () => {
    await openMenu(sales, ...SALES_ORDERS);
    await openRow(sales, journey.orderNumber);
    await expect(status(sales)).toHaveAttribute("data-value", "completed");
    handOver("WF-06", { salesOrderStatusAfterReport: (await status(sales).innerText()).trim() });
  });
});
