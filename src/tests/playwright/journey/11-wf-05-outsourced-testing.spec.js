import { expect, handOver, received, step, test } from "../support/journey";
import { clearSearch, dated, field, labDay, listed, openListed, openMenu, openTab, pick, press, pressLabel, save, search, settled, shownDay, status, type, written } from "../support/odoo";
import { follow, loads, openOrder } from "../support/portal";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const SAMPLE_TESTS = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample_test"];
const TEST_RESULTS = [LABORATORY, "sol_laboratory.menu_laboratory_results", "sol_laboratory.menu_test_result"];
const DISPATCHES_TO_CARRY = [LABORATORY, "sol_laboratory.menu_laboratory_schedule", "sol_laboratory.menu_dispatch_to_carry"];
const OUTSOURCING_SCHEDULE = [LABORATORY, "sol_laboratory.menu_laboratory_schedule", "sol_laboratory.menu_outsourcing_schedule"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

const CARRIER = "Vo Van Tai";
const SUBCONTRACTOR_CONTACT = "Nguyen Thi Lan";
const RESULT = "4.6";
const ENGLISH_DAY = "mm/dd/yyyy";

const iso = (date) => date.toISOString().slice(0, 10);
const buttons = (page) => page.locator(".o_form_view:visible .o_statusbar_buttons");
const button = (page, label) => buttons(page).getByRole("button", { name: label, exact: true });

test("WF-05 Outsourced testing", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "orderNumber", "requestCode", "sampleType", "sampleLabCode", "leadTaskName", "leadParameterName", "leadMethod", "subcontractorName");
  const labCode = journey.sampleLabCode;
  const acceptedWay = `${journey.leadParameterName} – ${journey.leadMethod}`;
  const subcontractedWay = `${acceptedWay} (${journey.subcontractorName})`;
  const reason = `Journey ${journey.tag}: ICP-MS-01 cannot meet the due date; ${journey.subcontractorName} tests lead by the same ${journey.leadMethod} method.`;
  const dispatch = {};
  const lead = {};

  const head = await as("demo.head_of_department");
  const suggestion = head.locator(".o_form_view:visible .alert-warning", { hasText: "Outsource it through a subcontracted way of testing" });
  const dispatched = (page) => field(page, "sample_test_ids").locator(".o_data_row", { hasText: labCode });

  // The results of the sample, where the lead result is the one row of its parameter.
  const openLeadResult = async (page) => {
    await openMenu(page, ...TEST_RESULTS);
    await search(page, labCode, { field: "Sample" });
    await expect(listed(page, journey.leadParameterName)).toHaveCount(1);
    await openListed(page, journey.leadParameterName);
    await expect(field(page, "display_name")).toContainText(`${labCode} – ${journey.leadParameterName}`);
    await expect(field(page, "subcontractor_id")).toHaveText(journey.subcontractorName);
    await expect(field(page, "entered_by_id")).toHaveText(SUBCONTRACTOR_CONTACT);
  };

  await step(head, "The head of department opens the journey's lead test, which waits in the department", async () => {
    await openMenu(head, ...SAMPLE_TESTS);
    await clearSearch(head);
    await search(head, labCode, { field: "Sample" });
    await expect(listed(head, journey.leadParameterName)).toHaveCount(1);
    await openListed(head, journey.leadParameterName);
    await expect(field(head, "sample_id")).toHaveText(labCode);
    await expect(field(head, "parameter_id")).toHaveText(journey.leadParameterName);
    await expect(status(head)).toHaveAttribute("data-value", /^(waiting|assigned)$/);
    await expect(field(head, "accepted_method_id")).toHaveText(acceptedWay);
    await expect(button(head, "Outsource")).toBeVisible();
    lead.suggested = await suggestion.isVisible();
  });

  const outsourcing = lead.suggested
    ? "The head of department accepts the suggested subcontracted way and puts the sample test in a dispatch"
    : "The head of department outsources the waiting test straight away with a reason and puts it in a dispatch";
  await step(head, outsourcing, async () => {
    await pressLabel(head, "Outsource", { within: buttons(head) });
    const dialog = head.locator(".modal:visible");
    await expect(dialog.locator(".modal-title")).toHaveText("Outsource the Test");
    await expect(field(head, "parameter_method_id").locator("input")).toHaveValue(subcontractedWay);
    // The dialog asks for a reason only when the scheduler did not suggest outsourcing the test.
    if (lead.suggested) {
      await expect(field(head, "reason")).toBeHidden();
    } else {
      await expect(dialog).toContainText("No outsourcing suggestion: give the reason");
      await type(head, "reason", reason);
    }
    await press(head, "action_outsource");
    await expect(dialog).toHaveCount(0);
    await expect(field(head, "code")).toHaveText(/^PGTP\.\S+$/);
    await expect(status(head)).toHaveAttribute("data-value", "draft");
    await expect(field(head, "subcontractor_id").locator("input")).toHaveValue(journey.subcontractorName);
    await expect(dispatched(head)).toHaveCount(1);
    await expect(dispatched(head).locator("td[name=parameter_id]")).toHaveText(journey.leadParameterName);
    await expect(dispatched(head).locator("td[name=parameter_method_id]")).toHaveText(subcontractedWay);
    await expect(dispatched(head).locator("td[name=status]")).toHaveText("Outsourced");
    dispatch.code = (await field(head, "code").innerText()).trim();
    dispatch.tests = await field(head, "sample_test_ids").locator(".o_data_row").count();
    handOver("WF-05", {
      dispatchCode: dispatch.code,
      dispatchTestCount: dispatch.tests,
      leadOutsourcedBy: lead.suggested ? "accepted suggestion" : "direct with a reason",
    });
  });

  await step(head, "The head of department names the sample delivery staff who take the dispatch", async () => {
    await pick(head, "courier_id", CARRIER);
    await save(head);
    await expect(field(head, "courier_id").locator("input")).toHaveValue(CARRIER);
    await expect(status(head)).toHaveAttribute("data-value", "draft");
    await expect(button(head, "Hand Over")).toHaveCount(0);
  });

  await step(head, "The outsourced test leaves the department's queue for the subcontracted way with the same method", async () => {
    await head.locator(".o_breadcrumb .breadcrumb-item a", { hasText: journey.leadParameterName }).click();
    await settled(head);
    await expect(field(head, "sample_id")).toHaveText(labCode);
    await expect(status(head)).toHaveAttribute("data-value", "outsourced");
    await expect(suggestion).toHaveCount(0);
    await expect(button(head, "Outsource")).toHaveCount(0);
    await expect(field(head, "accepted_method_id")).toHaveText(acceptedWay);
    await expect(field(head, "parameter_method_id")).toHaveText(subcontractedWay);
    if (!lead.suggested) await expect(field(head, "emergency_outsource_reason")).toHaveText(reason);
    await field(head, "parameter_method_id").locator("a").click();
    await settled(head);
    await expect(field(head, "turnaround_days")).toHaveText(/^[1-9]\d*$/);
    dispatch.turnaroundDays = Number(await field(head, "turnaround_days").innerText());
    await openMenu(head, ...TASK_QUEUE);
    await search(head, labCode);
    await expect(listed(head, journey.leadTaskName)).toHaveCount(0);
  });

  const staff = await as("demo.sample_delivery_staff");

  await step(staff, "Sample delivery staff take the dispatch to carry it; it is marked sent with the date, who took it and the expected date", async () => {
    await openMenu(staff, ...DISPATCHES_TO_CARRY);
    await search(staff, dispatch.code);
    await expect(listed(staff, dispatch.code)).toHaveCount(1);
    await expect(listed(staff, dispatch.code).locator("td[name=status]")).toHaveText("Draft");
    await openListed(staff, dispatch.code);
    await expect(field(staff, "code")).toHaveText(dispatch.code);
    await expect(dispatched(staff)).toHaveCount(1);
    await pressLabel(staff, "Hand Over", { within: buttons(staff) });
    await expect(staff.locator(".modal:visible .modal-title")).toHaveText("Hand Over the Dispatch");
    await expect(field(staff, "delivery_service").locator("input")).toHaveValue("");
    await press(staff, "action_hand_over");
    await expect(staff.locator(".modal:visible")).toHaveCount(0);
    await expect(status(staff)).toHaveAttribute("data-value", "sent");
    dispatch.sent = written(labDay(), ENGLISH_DAY);
    dispatch.expected = written(labDay({ days: dispatch.turnaroundDays }), ENGLISH_DAY);
    await expect(shownDay(staff, "sent_date")).toHaveAttribute("data-tooltip", dispatch.sent);
    await expect(shownDay(staff, "expected_date")).toHaveAttribute("data-tooltip", dispatch.expected);
    await expect(field(staff, "courier_id")).toHaveText(CARRIER);
    await expect(button(staff, "Hand Over")).toHaveCount(0);
    await expect(button(staff, "Delivery Failed")).toBeVisible();
    handOver("WF-05", {
      dispatchSentDate: iso(dated(dispatch.sent, ENGLISH_DAY)),
      dispatchExpectedDate: iso(dated(dispatch.expected, ENGLISH_DAY)),
      dispatchTurnaroundDays: dispatch.turnaroundDays,
      dispatchCarrier: CARRIER,
    });
  });

  await step(head, "The head of department sees the sent dispatch in the outsourcing schedule", async () => {
    await openMenu(head, ...OUTSOURCING_SCHEDULE);
    await head.locator(".o_switch_view.o_list").click();
    await settled(head);
    await search(head, dispatch.code);
    const sent = listed(head, dispatch.code);
    await expect(sent).toHaveCount(1);
    await expect(sent.locator("td[name=subcontractor_id]")).toHaveText(journey.subcontractorName);
    await expect(sent.locator("td[name=courier_id]")).toHaveText(CARRIER);
    await expect(sent.locator("td[name=status]")).toHaveText("Sent");
  });

  const subcontractor = await as("demo.subcontractor");
  const portal = subcontractor.locator("main");
  const portalDispatch = portal.locator("tbody tr", { has: subcontractor.locator("a", { hasText: dispatch.code }) });
  const portalTest = portal.locator("tbody tr", { has: subcontractor.locator("td:first-child", { hasText: labCode }) });
  const customerIsHidden = async () => {
    for (const known of [journey.customerName, journey.orderNumber, journey.requestCode]) await expect(subcontractor.locator("body")).not.toContainText(known);
  };

  await step(subcontractor, "The subcontractor confirms receipt of the samples of the dispatch on the portal", async () => {
    await expect(subcontractor).toHaveURL(/\/my$/);
    await follow(subcontractor, "/my/dispatches");
    await expect(portalDispatch).toHaveCount(1);
    await expect(portalDispatch.locator("td").nth(1)).toHaveText(dispatch.sent);
    await expect(portalDispatch.locator("td").nth(2)).toHaveText(dispatch.expected);
    await expect(portalDispatch.locator("td").nth(3)).toHaveText(String(dispatch.tests));
    await expect(portalDispatch.locator("td").nth(4)).toHaveText("Sent");
    await loads(subcontractor, () => portalDispatch.locator("a").click());
    await expect(portal.locator("h2")).toHaveText(dispatch.code);
    await expect(portal).toContainText(`Sent on ${dispatch.sent}, results expected by ${dispatch.expected}.`);
    await expect(portalTest).toHaveCount(1);
    await expect(portalTest.locator("td").nth(1)).toHaveText(journey.sampleType);
    await expect(portalTest.locator("td").nth(2)).toHaveText(journey.leadParameterName);
    await expect(portalTest.locator("td").nth(3)).toHaveText(journey.leadMethod);
    await expect(portal.locator("input[name=value]")).toHaveCount(0);
    await customerIsHidden();
    await loads(subcontractor, () => portal.locator("form[action$='/receive'] button[type=submit]").click());
    await expect(portal.locator("h2")).toHaveText(dispatch.code);
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
    handOver("WF-05", { leadResult: lead.result, leadResultEnteredBy: SUBCONTRACTOR_CONTACT });
  });

  await step(head, "The head of department finds the subcontractor's result to approve", async () => {
    await openLeadResult(head);
    await expect(field(head, "value_display")).toHaveText(lead.result.slice(0, -lead.unit.length).trim());
    await expect(field(head, "unit_id")).toHaveText(lead.unit);
    await expect.soft(button(head, "Approve"), "The subcontractor's result waits for the head's approval as soon as it is entered").toBeVisible({ timeout: 1000 });
    lead.waitsForTester = !(await button(head, "Approve").isVisible());
  });

  if (lead.waitsForTester) {
    const tester = await as("demo.tester");

    await step(tester, "A tester of the department sends the subcontractor's result for approval", async () => {
      await openLeadResult(tester);
      await expect(status(tester)).toHaveAttribute("data-value", "none");
      await pressLabel(tester, "Send for Approval", { within: buttons(tester) });
      await expect(status(tester)).toHaveAttribute("data-value", "requested");
      await expect(button(tester, "Send for Approval")).toHaveCount(0);
    });
  }

  await step(head, "The head of department approves the subcontractor's result like any other result", async () => {
    await openLeadResult(head);
    await expect(status(head)).toHaveAttribute("data-value", "requested");
    await pressLabel(head, "Approve", { within: buttons(head) });
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    await expect(button(head, "Approve")).toHaveCount(0);
    await expect(field(head, "signature_ids").locator(".o_data_row", { hasText: "Head of department" })).toContainText("Signed");
    handOver("WF-05", { leadResultStatus: (await status(head).innerText()).trim() });
  });

  await step(head, "The outsourced test is approved and its dispatch is received", async () => {
    await field(head, "sample_test_id").locator("a").click();
    await settled(head);
    await expect(field(head, "sample_id")).toHaveText(labCode);
    await expect(field(head, "parameter_id")).toHaveText(journey.leadParameterName);
    await expect(status(head)).toHaveAttribute("data-value", "approved");
    await expect(field(head, "parameter_method_id")).toHaveText(subcontractedWay);
    await openTab(head, "results");
    const result = field(head, "result_ids").locator(".o_data_row");
    await expect(result).toHaveCount(1);
    await expect(result.locator("td[name=entered_by_id]")).toHaveText(SUBCONTRACTOR_CONTACT);
    await expect(result.locator("td[name=status]")).toHaveText("Approved");
    await openTab(head, "dispatches");
    const sent = field(head, "dispatch_ids").locator(".o_data_row", { hasText: dispatch.code });
    await expect(sent).toHaveCount(1);
    await expect(sent.locator("td[name=status]")).toHaveText("Received");
    handOver("WF-05", {
      leadTestStatus: (await status(head).innerText()).trim(),
      dispatchStatus: (await sent.locator("td[name=status]").innerText()).trim(),
    });
  });

  const customer = await as(journey.customerLogin, journey.customerPassword);

  await step(customer, "The customer is neither told nor asked: the order shows no outsourcing and no subcontractor", async () => {
    await openOrder(customer, journey.orderNumber);
    const order = customer.locator("main");
    await expect(order).toContainText(acceptedWay);
    await expect(order).not.toContainText(journey.subcontractorName);
    await expect(order).not.toContainText(dispatch.code);
    await expect(order).not.toContainText(/outsourc|subcontract/i);
  });
});
