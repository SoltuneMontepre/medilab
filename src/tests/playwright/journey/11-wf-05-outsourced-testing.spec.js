import { expect, handOver, outside, received, step, test } from "../support/journey";
import { clearSearch, dated, field, labDay, listed, openListed, openMenu, openTab, pick, press, pressLabel, save, search, settled, shownDay, status, written } from "../support/odoo";
import { follow, loads, openOrder } from "../support/portal";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const SAMPLE_TESTS = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample_test"];
const DISPATCHES_TO_CARRY = [LABORATORY, "sol_laboratory.menu_laboratory_schedule", "sol_laboratory.menu_dispatch_to_carry"];
const TASKS = "sol_laboratory.menu_tasks_root";

// The demo subcontractor of the subcontracted lead way.
const SUBCONTRACTOR = "Northern Testing Laboratory";
const CARRIER = "Vo Van Tai";
const SUBCONTRACTOR_CONTACT = "Nguyen Thi Lan";
const RESULT = "4.6";
const ENGLISH_DAY = "mm/dd/yyyy";

const iso = (date) => date.toISOString().slice(0, 10);
const buttons = (page) => page.locator(".o_form_view:visible .o_statusbar_buttons");
const button = (page, label) => buttons(page).getByRole("button", { name: label, exact: true });

test("WF-05 Outsourced testing", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "orderNumber", "requestCode", "sampleType", "sampleLabCode", "leadParameterName", "leadMethod");
  const labCode = journey.sampleLabCode;
  const acceptedWay = `${journey.leadParameterName} – ${journey.leadMethod}`;
  const subcontractedWay = `${acceptedWay} (${SUBCONTRACTOR})`;
  const dispatch = {};
  const lead = {};

  const head = await as("demo.head_of_department");
  const dispatched = (page) => field(page, "sample_test_ids").locator(".o_data_row", { hasText: labCode });

  await step(head, "The system suggests a subcontracted way with the test's parameter and method for the journey's lead test", async () => {
    await openMenu(head, ...SAMPLE_TESTS);
    await clearSearch(head);
    await search(head, labCode, { field: "Sample" });
    await expect(listed(head, journey.leadParameterName)).toHaveCount(1);
    await openListed(head, journey.leadParameterName);
    await expect(field(head, "sample_id")).toHaveText(labCode);
    await expect(field(head, "parameter_id")).toHaveText(journey.leadParameterName);
    await expect(status(head)).toHaveAttribute("data-value", /^(waiting|assigned)$/);
    await expect(field(head, "accepted_method_id")).toHaveText(acceptedWay);
    await expect(head.locator(".o_form_view:visible .alert-warning", { hasText: "Outsource it through a subcontracted way of testing" })).toBeVisible();
  });

  await step(head, "The head of department accepts the suggestion and puts the sample test in a dispatch", async () => {
    await pressLabel(head, "Outsource", { within: buttons(head) });
    const dialog = head.locator(".modal:visible");
    await expect(dialog.locator(".modal-title")).toHaveText("Outsource the Test");
    await expect(field(head, "parameter_method_id").locator("input")).toHaveValue(subcontractedWay);
    await expect(field(head, "reason")).toBeHidden();
    await press(head, "action_outsource");
    await expect(dialog).toHaveCount(0);
    await expect(field(head, "code")).toHaveText(/^PGTP\.\S+$/);
    await expect(status(head)).toHaveAttribute("data-value", "draft");
    await expect(field(head, "subcontractor_id").locator("input")).toHaveValue(SUBCONTRACTOR);
    await expect(dispatched(head)).toHaveCount(1);
    await expect(dispatched(head).locator("td[name=parameter_method_id]")).toHaveText(subcontractedWay);
    await expect(dispatched(head).locator("td[name=status]")).toHaveText("Outsourced");
    dispatch.code = (await field(head, "code").innerText()).trim();
    dispatch.tests = await field(head, "sample_test_ids").locator(".o_data_row").count();
    handOver("WF-05", { dispatchCode: dispatch.code, dispatchTestCount: dispatch.tests, leadOutsourcedBy: "accepted suggestion" });
  });

  // sample-delivery-staff.md, Carrier: the head chooses the sample delivery staff on the draft dispatch.
  await step(head, "The head of department chooses the sample delivery staff who carry the dispatch", async () => {
    await pick(head, "courier_id", CARRIER);
    await save(head);
    await expect(field(head, "courier_id").locator("input")).toHaveValue(CARRIER);
    await expect(status(head)).toHaveAttribute("data-value", "draft");
    await head.locator(".o_breadcrumb .breadcrumb-item a", { hasText: journey.leadParameterName }).click();
    await settled(head);
    await expect(status(head)).toHaveAttribute("data-value", "outsourced");
    await expect(field(head, "parameter_method_id")).toHaveText(subcontractedWay);
    await field(head, "parameter_method_id").locator("a").click();
    await settled(head);
    await expect(field(head, "turnaround_days")).toHaveText(/^[1-9]\d*$/);
    dispatch.turnaroundDays = Number(await field(head, "turnaround_days").innerText());
  });

  const staff = await as("demo.sample_delivery_staff");

  await step(staff, "Sample delivery staff take the dispatch to carry it; it is marked sent with the date, who took it and the expected date", async () => {
    await openMenu(staff, ...DISPATCHES_TO_CARRY);
    await search(staff, dispatch.code);
    await expect(listed(staff, dispatch.code)).toHaveCount(1);
    await expect(listed(staff, dispatch.code).locator("td[name=status]")).toHaveText("Draft");
    await openListed(staff, dispatch.code);
    await expect(dispatched(staff)).toHaveCount(1);
    await pressLabel(staff, "Hand Over", { within: buttons(staff) });
    await expect(staff.locator(".modal:visible .modal-title")).toHaveText("Hand Over the Dispatch");
    await press(staff, "action_hand_over");
    await expect(staff.locator(".modal:visible")).toHaveCount(0);
    await expect(status(staff)).toHaveAttribute("data-value", "sent");
    dispatch.sent = written(labDay(), ENGLISH_DAY);
    dispatch.expected = written(labDay({ days: dispatch.turnaroundDays }), ENGLISH_DAY);
    await expect(shownDay(staff, "sent_date")).toHaveAttribute("data-tooltip", dispatch.sent);
    await expect(shownDay(staff, "expected_date")).toHaveAttribute("data-tooltip", dispatch.expected);
    await expect(field(staff, "courier_id")).toHaveText(CARRIER);
    handOver("WF-05", {
      dispatchSentDate: iso(dated(dispatch.sent, ENGLISH_DAY)),
      dispatchExpectedDate: iso(dated(dispatch.expected, ENGLISH_DAY)),
      dispatchTurnaroundDays: dispatch.turnaroundDays,
      dispatchCarrier: CARRIER,
    });
  });

  const subcontractor = await as("demo.subcontractor");
  const portal = subcontractor.locator("main");
  const portalDispatch = portal.locator("tbody tr", { has: subcontractor.locator("a", { hasText: dispatch.code }) });
  const portalTest = portal.locator("tbody tr", { has: subcontractor.locator("td:first-child", { hasText: labCode }) });
  // WF-05 acceptance criterion: a subcontractor user never sees a sample's customer.
  const customerIsHidden = async () => {
    for (const known of [journey.customerName, journey.orderNumber, journey.requestCode]) await expect(subcontractor.locator("body")).not.toContainText(known);
  };

  await step(subcontractor, "The subcontractor confirms receipt of the samples on the portal, which marks the dispatch received", async () => {
    await expect(subcontractor).toHaveURL(/\/my$/);
    await follow(subcontractor, "/my/dispatches");
    await expect(portalDispatch).toHaveCount(1);
    await expect(portalDispatch.locator("td").nth(1)).toHaveText(dispatch.sent);
    await expect(portalDispatch.locator("td").nth(2)).toHaveText(dispatch.expected);
    await expect(portalDispatch.locator("td").nth(3)).toHaveText(String(dispatch.tests));
    await expect(portalDispatch.locator("td").nth(4)).toHaveText("Sent");
    await loads(subcontractor, () => portalDispatch.locator("a").click());
    await expect(portal.locator("h2")).toHaveText(dispatch.code);
    await expect(portalTest).toHaveCount(1);
    await expect(portalTest.locator("td").nth(1)).toHaveText(journey.sampleType);
    await expect(portalTest.locator("td").nth(2)).toHaveText(journey.leadParameterName);
    await expect(portalTest.locator("td").nth(3)).toHaveText(journey.leadMethod);
    await customerIsHidden();
    await loads(subcontractor, () => portal.locator("form[action$='/receive'] button[type=submit]").click());
    await expect(portal).toContainText(`Received on ${written(labDay(), ENGLISH_DAY)}.`);
    await expect(portal.locator("form[action$='/receive']")).toHaveCount(0);
    await expect(portalTest.locator("input[name=value]")).toBeVisible();
  });

  await step(subcontractor, "The subcontractor enters the result of the journey's sample", async () => {
    lead.unit = (await portalTest.locator(".input-group-text").innerText()).trim();
    await portalTest.locator("input[name=value]").fill(RESULT);
    await loads(subcontractor, () => portalTest.locator("button[type=submit]").click());
    await expect(portal.locator(".alert-danger")).toHaveCount(0);
    const entered = portalTest.locator("td").last();
    await expect(entered).toContainText(`Entered by ${SUBCONTRACTOR_CONTACT}`);
    await expect(portalTest.locator("input[name=value]")).toHaveCount(0);
    lead.result = (await entered.innerText()).split("\n")[0].trim();
    expect(Number.parseFloat(lead.result)).toBe(Number(RESULT));
    expect(lead.result.endsWith(` ${lead.unit}`)).toBe(true);
    await customerIsHidden();
    await follow(subcontractor, "/my/dispatches");
    await expect(portalDispatch.locator("td").nth(4)).toHaveText("Received");
  });

  await outside("The head of department is notified of the subcontractor's result", "e-mail");

  const resultsTile = head.locator(".o_task_tile_approve .o_task_row", { hasText: "Results to approve" });

  // overview.md, Entered by: a subcontractor's result goes to approval when entered; the head approves it like any other.
  await step(head, "The head of department approves the subcontractor's result like any other result", async () => {
    await openMenu(head, TASKS);
    await expect(resultsTile, "results wait under Results to approve on the head's Tasks dashboard").toBeVisible();
    await resultsTile.locator("button.o_task_row_main").click();
    await settled(head);
    await search(head, labCode, { field: "Sample" });
    const waiting = listed(head, journey.leadParameterName);
    await expect(waiting, "the subcontractor's result waits under Results to approve").toHaveCount(1);
    await expect(waiting.locator("td[name=entered_by_id]")).toHaveText(SUBCONTRACTOR_CONTACT);
    await openListed(head, journey.leadParameterName);
    await expect(field(head, "subcontractor_id")).toHaveText(SUBCONTRACTOR);
    await expect(field(head, "value_display")).toHaveText(lead.result.slice(0, -lead.unit.length).trim());
    await expect(status(head)).toHaveAttribute("data-value", "requested");
    await pressLabel(head, "Approve", { within: buttons(head) });
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    await expect(field(head, "signature_ids").locator(".o_data_row", { hasText: "Head of department" })).toContainText("Signed");
    lead.status = (await status(head).innerText()).trim();
  });

  await step(head, "The outsourced test is approved; with every test of the sample approved, the sample completes", async () => {
    await field(head, "sample_test_id").locator("a").click();
    await settled(head);
    await expect(field(head, "parameter_id")).toHaveText(journey.leadParameterName);
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    lead.testStatus = (await status(head).innerText()).trim();
    await openTab(head, "dispatches");
    const sent = field(head, "dispatch_ids").locator(".o_data_row", { hasText: dispatch.code });
    await expect(sent.locator("td[name=status]")).toHaveText("Received");
    dispatch.status = (await sent.locator("td[name=status]").innerText()).trim();
    await field(head, "sample_id").locator("a").click();
    await settled(head);
    await expect(field(head, "code")).toHaveText(labCode);
    await expect(status(head)).toHaveAttribute("data-value", "completed");
    handOver("WF-05", {
      leadResult: lead.result,
      leadResultEnteredBy: SUBCONTRACTOR_CONTACT,
      leadResultStatus: lead.status,
      leadTestStatus: lead.testStatus,
      dispatchStatus: dispatch.status,
      sampleStatusAfterLead: (await status(head).innerText()).trim(),
    });
  });

  const customer = await as(journey.customerLogin, journey.customerPassword);

  await step(customer, "The customer is neither told nor asked: the order shows no outsourcing and no subcontractor", async () => {
    await openOrder(customer, journey.orderNumber);
    const order = customer.locator("main");
    await expect(order).toContainText(acceptedWay);
    await expect(order).not.toContainText(SUBCONTRACTOR);
    await expect(order).not.toContainText(dispatch.code);
    await expect(order).not.toContainText(/outsourc|subcontract/i);
  });
});
