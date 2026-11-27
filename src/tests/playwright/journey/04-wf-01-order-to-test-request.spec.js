import { expect, handOver, received, step, test } from "../support/journey";
import { choose, dated, field, labDay, listed, money, openListed, openMenu, openRow, openTab, press, pressLabel, save, search, shownDay, status, type, typeDate, written } from "../support/odoo";
import { addToCart, cartChoices, cartLine, detail, loads, openHeader, openOrder, send } from "../support/portal";

const SALES = "sale.sale_menu_root";
const ORDERS = "sol_commerce.menu_sale_order";
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];
const TEST_REQUESTS = ["sol_laboratory.menu_laboratory_root", "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_test_request"];

const LEAD = "Lead (Pb)";
const LEAD_METHOD = "ISO 17294-2:2016";
const ADVANCE_PERCENT = 30;

// How each screen writes a day: Sales works in Vietnamese, the customer and the laboratory staff in English.
const SALES_DAY = "dd/mm/yyyy";
const ENGLISH_DAY = "mm/dd/yyyy";

// The words of Sales's Vietnamese screens that carry no name to select them by.
const VI = {
  requested: "Đã yêu cầu",
  accepted: "Đã chấp nhận",
  declined: "Đã từ chối",
  bankTransfer: "Chuyển khoản",
  percentage: "Phần trăm",
  beforeTheReport: "Trước khi trả kết quả",
  recordPayment: "Ghi nhận thanh toán",
  unpaid: "Chưa thanh toán",
  awaitingAccountant: "Chờ kế toán xác nhận",
  advancePaid: "Đã tạm ứng",
  partlyPaid: "Thanh toán một phần",
  awaitingSamples: "Chờ lấy mẫu",
};

const iso = (date) => date.toISOString().slice(0, 10);

// The first day from Monday to Friday, `days` after today or later.
function workingDay(days) {
  let day = labDay({ days });
  while ([0, 6].includes(day.getUTCDay())) day = new Date(day.getTime() + 24 * 60 * 60 * 1000);
  return day;
}

test("WF-01 Order to confirmed test request, with SF-07 Result dates and priority orders", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "sampleType", "price", "customerName", "customerLogin", "customerPassword", "contactName");
  const requested = workingDay(14);
  const pickup = workingDay(1);
  const journeyWay = `${journey.parameterName} – ${journey.methodCode}`;
  const leadWay = `${LEAD} – ${LEAD_METHOD}`;
  const reference = `Journey advance ${journey.tag}`;
  const order = {};

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const expectedSamples = customer.locator("main .o_medilab_expected_sampling");
  const chosen = (line, select) => cartChoices(customer, line).locator(`select[name=${select}] option:checked`);

  await step(customer, "The customer finds the journey's parameter in the catalog and puts it in the cart", async () => {
    await openHeader(customer, "/catalog");
    await customer.locator("main form[action='/catalog'] input[name=name]").fill(journey.parameterName);
    await send(customer, "/catalog");
    await addToCart(customer, journey.parameterName);
    await expect(chosen(journey.parameterName, "sample_type_id")).toHaveText(journey.sampleType);
    await expect(chosen(journey.parameterName, "parameter_method_id")).toHaveText(journeyWay);
  });

  await step(customer, "The customer adds Lead (Pb) for the same sample and chooses its way of testing", async () => {
    await openHeader(customer, "/catalog");
    await customer.locator("main form[action='/catalog'] input[name=name]").fill("Lead");
    await send(customer, "/catalog");
    await addToCart(customer, LEAD);
    const choices = cartChoices(customer, LEAD);
    // Each choice sends itself and the cart shows again.
    await loads(customer, () => choices.locator("select[name=sample_type_id]").selectOption({ label: journey.sampleType }));
    await loads(customer, () => choices.locator("select[name=parameter_method_id]").selectOption({ label: leadWay }));
    await expect(chosen(LEAD, "sample_type_id")).toHaveText(journey.sampleType);
    await expect(chosen(LEAD, "parameter_method_id")).toHaveText(leadWay);
    const leadPrice = money(await cartLine(customer, LEAD).locator("td").nth(1).innerText());
    await expect(customer.locator("main tfoot th").last()).toHaveText(new RegExp(`^${(journey.price + leadPrice).toLocaleString("en-US")}\\s`));
    await expect(expectedSamples.locator("[data-sample]")).toHaveCount(1);
    await expect(expectedSamples.locator(".o_medilab_objects")).toHaveText("1");
    await expect(expectedSamples.locator(".o_medilab_expected")).toHaveText("1");
    await expect(expectedSamples.locator("tbody tr")).toHaveCount(1);
    await expect(expectedSamples.locator("tbody tr")).toContainText(LEAD_METHOD);
    await expect(expectedSamples.locator("tbody tr")).toContainText(journey.methodCode);
    handOver("WF-01", { leadParameterName: LEAD, leadMethod: LEAD_METHOD, leadPrice });
  });

  const cart = customer.locator("main form[action='/cart/submit']");

  await step(customer, "SF-07: The customer reads the standard turnaround, gives the date they want the results and asks for priority", async () => {
    const turnaround = cart.locator("p.text-muted");
    await expect(turnaround).toHaveText(/Results within \d+ working days of receiving the samples\./);
    order.turnaroundDays = Number((await turnaround.innerText()).match(/\d+/)[0]);
    await cart.locator("#requested_date").fill(iso(requested));
    await cart.locator("#priority").check();
    await expect(cart.locator("#requested_date")).toHaveValue(iso(requested));
    await expect(cart.locator("#priority")).toBeChecked();
  });

  await step(customer, "The customer submits the cart, and the order waits in the sales queue", async () => {
    await expect(cart.locator("select[name=contact_id] option:checked")).toHaveText(journey.contactName);
    await loads(customer, () => cart.locator("button[type=submit]:not([formaction])").click());
    await expect(customer.locator("main h1")).toHaveText("Order submitted");
    order.number = (await customer.locator("main p").first().innerText()).match(/S\d+/)[0];
    handOver("WF-01", { orderNumber: order.number, requestedDate: iso(requested), turnaroundDays: order.turnaroundDays });
  });

  await step(customer, "SF-07: The customer sees the requested date and the priority request on the order", async () => {
    await openOrder(customer, order.number);
    await expect(customer.locator("main h1 + .badge")).toHaveText("Submitted");
    await expect(detail(customer, "Requested date")).toHaveText(written(requested, ENGLISH_DAY));
    await expect(detail(customer, "Priority")).toHaveText("Requested");
    // Until Sales gives the pickup day, the estimate counts from today.
    order.firstEstimate = dated(await detail(customer, "Expected return date").innerText(), ENGLISH_DAY);
    expect(order.firstEstimate <= requested, "the first estimate meets the date the customer asked for").toBe(true);
  });

  const sales = await as("demo.sales");

  await step(sales, "Sales claims the order from the unclaimed queue", async () => {
    await openMenu(sales, SALES, "sol_commerce.menu_sale_order_queue");
    await search(sales, order.number);
    await press(sales, "action_claim", { within: listed(sales, order.number) });
    await expect(status(sales)).toHaveAttribute("data-value", "claimed");
    await expect(field(sales, "customer_id").locator("input")).toHaveValue(journey.customerName);
    const salesName = await field(sales, "user_id").locator("input").inputValue();
    expect(salesName).not.toBe("");
    handOver("WF-01", { salesLogin: "demo.sales", salesName });
  });

  const line = (parameter) => field(sales, "product_line_ids").locator(".o_data_row", { hasText: parameter });

  await step(sales, "Sales confirms the selected ways and the expected sampling needs", async () => {
    await expect(field(sales, "product_line_ids").locator(".o_data_row")).toHaveCount(2);
    await expect(line(journey.parameterName).locator("td[name=parameter_method_id]")).toContainText(journey.methodCode);
    await expect(line(LEAD).locator("td[name=parameter_method_id]")).toContainText(LEAD_METHOD);
    const sampleType = (await line(journey.parameterName).locator("td[name=sample_type_id]").innerText()).trim();
    expect(sampleType).not.toBe("");
    await expect(line(LEAD).locator("td[name=sample_type_id]")).toHaveText(sampleType);
    for (const parameter of [journey.parameterName, LEAD]) {
      await expect(line(parameter).locator("td[name=expected_sample_count]")).toHaveText("1");
      await expect(line(parameter).locator("td[name=expected_sample_summary]")).toHaveText(/\S/);
    }
  });

  await step(sales, "Sales sets the sample pickup day agreed with the customer", async () => {
    await typeDate(sales, "expected_collection_date", pickup);
    await save(sales);
    await expect(shownDay(sales, "expected_collection_date")).toHaveAttribute("data-tooltip", written(pickup, SALES_DAY));
    handOver("WF-01", { pickupDay: iso(pickup) });
  });

  await step(sales, "SF-07: Sales sees the standard turnaround, the estimated return date and the customer's priority request", async () => {
    await expect(shownDay(sales, "requested_date")).toHaveAttribute("data-tooltip", written(requested, SALES_DAY));
    await expect(field(sales, "priority_request")).toHaveText(VI.requested);
    await expect(shownDay(sales, "committed_date")).toHaveAttribute("data-tooltip", /\d/);
    order.estimate = dated(await shownDay(sales, "committed_date").getAttribute("data-tooltip"), SALES_DAY);
    expect(order.estimate > pickup, "results come back after the samples are picked up").toBe(true);
    expect(order.estimate >= order.firstEstimate, "the pickup day does not bring the estimate forward").toBe(true);
    expect(order.estimate <= requested, "the laboratory's estimate meets the date the customer asked for").toBe(true);
    await openTab(sales, "other_information");
    await expect(field(sales, "turnaround_days")).toHaveText(String(order.turnaroundDays));
    await openTab(sales, "timeline");
    const timeline = field(sales, "return_timeline");
    await expect(timeline.locator(".o_medilab_timeline_step").first()).toContainText(written(pickup, "dd/mm"));
    await expect(timeline.locator(".o_medilab_timeline_step_final")).toContainText(written(order.estimate, "dd/mm"));
    await expect(timeline.locator("p")).toContainText(written(requested, "dd/mm"));
  });

  const refusal = sales.locator(".o_error_dialog");

  // A feasibility check that answers with a server error marks this flow as failed and the journey goes on without
  // the priority, so the flows after it still show whether they connect.
  let priority = "accepted";
  await step(sales, "SF-07: Sales checks the requested date and accepts the priority", async () => {
    await press(sales, "action_accept_priority", { refusals: true });
    if (await refusal.count()) {
      priority = "declined";
      await refusal.locator("summary").click();
      await refusal.locator(".o_error_detail").hover();
      await sales.mouse.wheel(0, 20000);
    }
    await expect.soft(refusal, "Accept priority answers without a server error").toHaveCount(0, { timeout: 1000 });
    if (priority === "accepted") {
      await expect(field(sales, "priority_request")).toHaveText(VI.accepted);
      order.estimate = requested;
      await expect(shownDay(sales, "committed_date")).toHaveAttribute("data-tooltip", written(order.estimate, SALES_DAY));
    }
  });

  if (priority === "declined") {
    await step(sales, "SF-07: Sales declines the priority, the decision the screen still takes", async () => {
      await refusal.locator("footer button").click();
      await expect(refusal).toHaveCount(0);
      await expect(field(sales, "priority_request")).toHaveText(VI.requested);
      await press(sales, "action_decline_priority");
      await expect(field(sales, "priority_request")).toHaveText(VI.declined);
      await expect(shownDay(sales, "committed_date")).toHaveAttribute("data-tooltip", written(order.estimate, SALES_DAY));
    });
  }
  await expect(sales.locator("button[name=action_accept_priority]:visible, button[name=action_decline_priority]:visible")).toHaveCount(0);
  handOver("WF-01", { priorityRequest: priority });

  await step(sales, "Sales sends the quotation with an advance payment request and the balance due before the report", async () => {
    await press(sales, "action_send_quotation");
    await expect(field(sales, "partner_email").locator("input")).toHaveValue(journey.customerLogin);
    await choose(sales, "payment_method", VI.bankTransfer);
    await choose(sales, "advance_mode", VI.percentage);
    await type(sales, "advance_value", ADVANCE_PERCENT);
    await choose(sales, "balance_due", VI.beforeTheReport);
    await press(sales, "action_send");
    await expect(sales.locator(".modal:visible")).toHaveCount(0);
    await expect(status(sales)).toHaveAttribute("data-value", "claimed");
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.unpaid);
    await expect(shownDay(sales, "committed_date")).toHaveAttribute("data-tooltip", written(order.estimate, SALES_DAY));
    await openTab(sales, "revisions");
    const revision = field(sales, "quotation_ids").locator(".o_data_row");
    await expect(revision).toHaveCount(1);
    order.quotation = (await revision.locator("td[name=code]").innerText()).trim();
    order.total = money(await revision.locator("td[name=amount_total]").innerText());
    await openTab(sales, "payment");
    const advance = field(sales, "payment_request_ids").locator(".o_data_row");
    await expect(advance).toHaveCount(1);
    order.advance = money(await advance.locator("td[name=amount]").innerText());
    expect(order.advance).toBe(Math.round((order.total * ADVANCE_PERCENT) / 100));
    await expect(advance.locator("td[name=remaining_amount]")).toHaveText(await advance.locator("td[name=amount]").innerText());
    handOver("WF-01", { quotationNumber: order.quotation, orderTotal: order.total, advanceAmount: order.advance });
  });

  await step(customer, "The customer reads the quotation with its advance payment request on the portal", async () => {
    await openOrder(customer, order.number);
    await expect(customer.locator("main h1 + .badge")).toHaveText("Quoted");
    await loads(customer, () => customer.locator("main a[href$='/quotation']").click());
    await expect(customer.locator("main h1")).toHaveText(`Quotation ${order.quotation}`);
    await expect(customer.locator("main")).toContainText("Status: Sent");
    await expect(customer.locator("#medilab_payment_request h2")).toHaveText("Advance payment request");
    expect(money(await customer.locator("#payment_request_amount").innerText())).toBe(order.advance);
    await expect(customer.locator("#medilab_payment_request")).toContainText("Bank transfer");
    await expect(detail(customer, "Requested date")).toHaveText(written(requested, ENGLISH_DAY));
    await expect(detail(customer, "Sample pickup")).toHaveText(written(pickup, ENGLISH_DAY));
    await expect(detail(customer, "Priority")).toHaveText(priority === "accepted" ? "Accepted" : "Declined");
    await expect(detail(customer, "Expected return date")).toHaveText(written(order.estimate, ENGLISH_DAY));
    await expect(detail(customer, "Balance due")).toHaveText("Before the report");
    expect(money(await customer.locator("main table.table tfoot th").last().innerText())).toBe(order.total);
    await expect(expectedSamples.locator(".o_medilab_expected")).toHaveText("1");
    // The customer accepts a quotation with an advance by paying it: the page has no button to accept.
    await expect(customer.locator("main form[action$='/quotation/accept']")).toHaveCount(0);
  });

  await step(sales, "Sales records the advance the customer paid by bank transfer as a pending payment", async () => {
    await pressLabel(sales, VI.recordPayment, { within: sales.locator(".o_statusbar_buttons") });
    expect(money(await field(sales, "amount").locator("input").inputValue())).toBe(order.advance);
    await expect(field(sales, "method").locator("input")).toHaveValue(VI.bankTransfer);
    await type(sales, "reference", reference);
    await press(sales, "action_record");
    await expect(sales.locator(".modal:visible")).toHaveCount(0);
    await expect(sales.locator("button[name=action_awaiting_payment_confirmation]:visible")).toBeDisabled();
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.awaitingAccountant);
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.unpaid);
  });

  const accountant = await as("demo.accountant");

  await step(accountant, "The accountant confirms the payment, which posts its invoice", async () => {
    await openMenu(accountant, ...TASK_QUEUE);
    await openRow(accountant, reference);
    await expect(field(accountant, "memo").locator("input")).toHaveValue(reference);
    expect(money(await field(accountant, "amount").locator("input").inputValue())).toBe(order.advance);
    await expect(status(accountant)).toHaveAttribute("data-value", "draft");
    await press(accountant, "action_post");
    await expect(status(accountant)).not.toHaveAttribute("data-value", "draft");
    await expect(field(accountant, "reviewed_by_id")).toHaveText(/\S/);
    await openMenu(accountant, ...TASK_QUEUE);
    await search(accountant, reference);
    await expect(listed(accountant, reference)).toHaveCount(0);
  });

  await step(sales, "Sales sees the advance verified and the quotation accepted", async () => {
    await openMenu(sales, SALES, ORDERS);
    await openRow(sales, order.number);
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.advancePaid);
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.partlyPaid);
    await openTab(sales, "payment");
    const advance = field(sales, "payment_request_ids").locator(".o_data_row");
    expect(money(await advance.locator("td[name=verified_amount]").innerText())).toBe(order.advance);
    expect(money(await advance.locator("td[name=remaining_amount]").innerText())).toBe(0);
    await expect(field(sales, "downpayment_line_ids").locator(".o_data_row")).toHaveCount(1);
    await expect(field(sales, "downpayment_line_ids").locator("td[name=downpayment_invoice_id]")).toContainText(order.number);
    await expect(sales.locator("button[name=action_confirm_order]:visible")).toBeEnabled();
  });

  await step(sales, "Sales confirms the order, which creates its test request, confirmed as paid", async () => {
    await press(sales, "action_confirm_order");
    await expect(status(sales)).toHaveAttribute("data-value", "confirmed");
    await expect(field(sales, "test_request_id")).toHaveText(/^YC\.\S+$/);
    order.request = (await field(sales, "test_request_id").innerText()).trim();
    await expect(field(sales, "result_status")).toHaveText(VI.awaitingSamples);
    await expect(shownDay(sales, "committed_date")).toHaveAttribute("data-tooltip", written(order.estimate, SALES_DAY));
    await expect(sales.locator("button[name=action_start_sample_collection]:visible")).toBeEnabled();
    await openTab(sales, "other_information");
    await expect(field(sales, "test_request_status").locator("span")).toHaveAttribute("raw-value", "paid");
    await openTab(sales, "payment");
    const balance = field(sales, "payment_request_ids").locator(".o_data_row").first();
    await expect(field(sales, "payment_request_ids").locator(".o_data_row")).toHaveCount(2);
    order.balance = money(await balance.locator("td[name=amount]").innerText());
    expect(order.balance).toBe(order.total - order.advance);
    handOver("WF-01", { requestCode: order.request, balanceAmount: order.balance, expectedReturnDate: iso(order.estimate) });
  });

  await step(customer, "The customer sees the order waiting for the samples, with its balance payment request", async () => {
    await openOrder(customer, order.number);
    await expect(customer.locator("main h1 + .badge")).toHaveText("Waiting");
    await expect(detail(customer, "Expected return date")).toHaveText(written(order.estimate, ENGLISH_DAY));
    await expect(customer.locator("#medilab_payment_request h2")).toHaveText("Balance payment request");
    expect(money(await customer.locator("#payment_request_amount").innerText())).toBe(order.balance);
    expect(money(await customer.locator("#payment_request_remaining").innerText())).toBe(order.balance);
    await expect(expectedSamples.locator(".o_medilab_expected")).toHaveText("1");
    await loads(customer, () => customer.locator("main a[href$='/quotation']").click());
    await expect(customer.locator("main")).toContainText("Status: Accepted");
    expect(money(await customer.locator("#payment_request_verified").innerText())).toBe(order.advance);
  });

  const reception = await as("demo.sample_delivery_staff");
  const sample = field(reception, "sample_ids").locator(".o_data_row");

  await step(reception, "Sample delivery staff find the paid test request with its one expected sample and both tests", async () => {
    await openMenu(reception, ...TEST_REQUESTS);
    await search(reception, journey.customerName, { field: "Customer" });
    await expect(listed(reception, order.request)).toHaveCount(1);
    await expect(listed(reception, order.request).locator("td[name=status]")).toHaveText("Paid");
    await openListed(reception, order.request);
    await expect(status(reception)).toHaveAttribute("data-value", "paid");
    await expect(sample).toHaveCount(1);
    await expect(sample.locator("td[name=sample_type_id]")).toHaveText(journey.sampleType);
    await expect(sample.locator("td[name=status]")).toHaveText("Expected");
    await expect(sample.locator("td[name=test_ids] .o_tag")).toHaveCount(2);
    await expect(sample.locator("td[name=test_ids]")).toContainText(journey.parameterName);
    await expect(sample.locator("td[name=test_ids]")).toContainText(LEAD);
    handOver("WF-01", {
      requestSearch: journey.customerName,
      requestSearchField: "Customer",
      sampleLabCode: (await sample.locator("td[name=code]").innerText()).trim(),
      sampleName: (await sample.locator("td[name=customer_sample_name]").innerText()).trim(),
    });
  });

  await step(reception, "SF-07: The test request keeps the requested date, the expected return date and the priority decision", async () => {
    await expect(shownDay(reception, "requested_date")).toHaveAttribute("data-tooltip", written(requested, ENGLISH_DAY));
    await expect(shownDay(reception, "committed_date")).toHaveAttribute("data-tooltip", written(order.estimate, ENGLISH_DAY));
    await expect(field(reception, "turnaround_days")).toHaveText(String(order.turnaroundDays));
    await expect(field(reception, "priority").locator("input")).toBeChecked({ checked: priority === "accepted" });
  });
});
