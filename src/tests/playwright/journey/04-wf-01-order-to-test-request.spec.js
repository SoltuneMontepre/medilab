import { expect, handOver, outside, received, step, test } from "../support/journey";
import { choose, dated, field, listed, money, openListed, openMenu, openRow, openTab, press, pressLabel, save, search, shownDay, status, type, typeDate, workingDay, written } from "../support/odoo";
import { addToCart, cartChoices, detail, loads, openHeader, openOrder, send } from "../support/portal";

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
  bankTransfer: "Chuyển khoản",
  percentage: "Phần trăm",
  recordPayment: "Ghi nhận thanh toán",
  unpaid: "Chưa thanh toán",
  awaitingAccountant: "Chờ kế toán xác nhận",
  advancePaid: "Đã tạm ứng",
};

const iso = (date) => date.toISOString().slice(0, 10);

test("WF-01 Order to confirmed test request", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "sampleType", "customerName", "customerLogin", "customerPassword", "contactName");
  const requested = workingDay(14);
  const pickup = workingDay(1);
  const journeyWay = `${journey.parameterName} – ${journey.methodCode}`;
  const leadWay = `${LEAD} – ${LEAD_METHOD}`;
  const reference = `Journey advance ${journey.tag}`;
  const order = {};

  const customer = await as(journey.customerLogin, journey.customerPassword);
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
  });

  const cart = customer.locator("main form[action='/cart/submit']");

  await step(customer, "SF-07: The customer reads the standard turnaround and gives the date they want the results", async () => {
    const turnaround = cart.locator("p.text-muted");
    await expect(turnaround).toHaveText(/Results within \d+ working days of receiving the samples\./);
    order.turnaroundDays = Number((await turnaround.innerText()).match(/\d+/)[0]);
    await cart.locator("#requested_date").fill(iso(requested));
    await expect(cart.locator("#requested_date")).toHaveValue(iso(requested));
    await expect(cart.locator("#priority")).not.toBeChecked();
  });

  await step(customer, "The customer submits the order, which waits in the sales queue", async () => {
    await expect(cart.locator("select[name=contact_id] option:checked")).toHaveText(journey.contactName);
    await loads(customer, () => cart.locator("button[type=submit]:not([formaction])").click());
    await expect(customer.locator("main h1")).toHaveText("Order submitted");
    order.number = (await customer.locator("main p").first().innerText()).match(/S\d+/)[0];
  });

  const sales = await as("demo.sales");

  await step(sales, "Sales claims the order from the unclaimed queue", async () => {
    await openMenu(sales, SALES, "sol_commerce.menu_sale_order_queue");
    await search(sales, order.number);
    await press(sales, "action_claim", { within: listed(sales, order.number) });
    await expect(status(sales)).toHaveAttribute("data-value", "claimed");
    await expect(field(sales, "customer_id").locator("input")).toHaveValue(journey.customerName);
    order.salesName = await field(sales, "user_id").locator("input").inputValue();
    expect(order.salesName).not.toBe("");
  });

  const line = (parameter) => field(sales, "product_line_ids").locator(".o_data_row", { hasText: parameter });

  await step(sales, "Sales confirms the selected ways and the expected sampling needs", async () => {
    await expect(field(sales, "product_line_ids").locator(".o_data_row")).toHaveCount(2);
    await expect(line(journey.parameterName).locator("td[name=parameter_method_id]")).toContainText(journey.methodCode);
    await expect(line(LEAD).locator("td[name=parameter_method_id]")).toContainText(LEAD_METHOD);
    // Sales's screen names the sample type in Vietnamese.
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
  });

  await step(sales, "SF-07: The quotation shows the standard turnaround and the estimated return date beside the customer's requested date", async () => {
    await expect(shownDay(sales, "requested_date")).toHaveAttribute("data-tooltip", written(requested, SALES_DAY));
    await expect(shownDay(sales, "committed_date")).toHaveAttribute("data-tooltip", /\d/);
    await openTab(sales, "other_information");
    await expect(field(sales, "turnaround_days")).toHaveText(String(order.turnaroundDays));
  });

  await step(sales, "Sales sends the quotation with an advance payment request by bank transfer, PayOS being unreachable (WF-01-A4)", async () => {
    await press(sales, "action_send_quotation");
    await expect(field(sales, "partner_email").locator("input")).toHaveValue(journey.customerLogin);
    await choose(sales, "payment_method", VI.bankTransfer);
    await choose(sales, "advance_mode", VI.percentage);
    await type(sales, "advance_value", ADVANCE_PERCENT);
    await press(sales, "action_send");
    await expect(sales.locator(".modal:visible")).toHaveCount(0);
    await expect(status(sales)).toHaveAttribute("data-value", "claimed");
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.unpaid);
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
  });

  await step(customer, "The customer reads the quotation with its advance payment request on the portal", async () => {
    await openOrder(customer, order.number);
    await loads(customer, () => customer.locator("main a[href$='/quotation']").click());
    await expect(customer.locator("main h1")).toHaveText(`Quotation ${order.quotation}`);
    await expect(customer.locator("main")).toContainText("Status: Sent");
    await expect(customer.locator("#medilab_payment_request h2")).toHaveText("Advance payment request");
    expect(money(await customer.locator("#payment_request_amount").innerText())).toBe(order.advance);
    await expect(customer.locator("#medilab_payment_request")).toContainText("Bank transfer");
    await expect(detail(customer, "Requested date")).toHaveText(written(requested, ENGLISH_DAY));
    await expect(detail(customer, "Sample pickup")).toHaveText(written(pickup, ENGLISH_DAY));
    await expect(detail(customer, "Expected return date")).toHaveText(/\d/);
  });

  await outside("The customer pays the advance by bank transfer (WF-01-A4)", "the customer's bank");

  await step(sales, "Sales records the advance paid by bank transfer as a pending payment (WF-01-A4)", async () => {
    await pressLabel(sales, VI.recordPayment, { within: sales.locator(".o_statusbar_buttons") });
    expect(money(await field(sales, "amount").locator("input").inputValue())).toBe(order.advance);
    await expect(field(sales, "method").locator("input")).toHaveValue(VI.bankTransfer);
    await type(sales, "reference", reference);
    await press(sales, "action_record");
    await expect(sales.locator(".modal:visible")).toHaveCount(0);
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.awaitingAccountant);
  });

  const accountant = await as("demo.accountant");

  await step(accountant, "The accountant confirms the payment, which posts its invoice (WF-01-A4)", async () => {
    await openMenu(accountant, ...TASK_QUEUE);
    await openRow(accountant, reference);
    await expect(field(accountant, "memo").locator("input")).toHaveValue(reference);
    expect(money(await field(accountant, "amount").locator("input").inputValue())).toBe(order.advance);
    await expect(status(accountant)).toHaveAttribute("data-value", "draft");
    await press(accountant, "action_post");
    await expect(status(accountant)).not.toHaveAttribute("data-value", "draft");
  });

  await step(sales, "Sales confirms the order, whose advance is verified and invoiced, which creates its test request", async () => {
    await openMenu(sales, SALES, ORDERS);
    await openRow(sales, order.number);
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.advancePaid);
    await openTab(sales, "payment");
    const advance = field(sales, "payment_request_ids").locator(".o_data_row");
    expect(money(await advance.locator("td[name=verified_amount]").innerText())).toBe(order.advance);
    await expect(field(sales, "downpayment_line_ids").locator("td[name=downpayment_invoice_id]")).toContainText(order.number);
    await press(sales, "action_confirm_order");
    await expect(status(sales)).toHaveAttribute("data-value", "confirmed");
    await expect(field(sales, "test_request_id")).toHaveText(/^YC\.\S+$/);
    order.request = (await field(sales, "test_request_id").innerText()).trim();
    const requests = field(sales, "payment_request_ids").locator(".o_data_row");
    await expect(requests).toHaveCount(2);
    order.balance = money(await requests.first().locator("td[name=amount]").innerText());
    expect(order.balance).toBe(order.total - order.advance);
    handOver("WF-01", {
      orderNumber: order.number,
      quotationNumber: order.quotation,
      salesLogin: "demo.sales",
      salesName: order.salesName,
      orderTotal: order.total,
      advanceAmount: order.advance,
      balanceAmount: order.balance,
      requestedDate: iso(requested),
      pickupDay: iso(pickup),
      turnaroundDays: order.turnaroundDays,
      expectedReturnDate: iso(dated(await shownDay(sales, "committed_date").getAttribute("data-tooltip"), SALES_DAY)),
      leadParameterName: LEAD,
      leadMethod: LEAD_METHOD,
    });
  });

  await step(sales, "The system confirms the test request as paid because the advance is verified", async () => {
    await openTab(sales, "other_information");
    const requestStatus = field(sales, "test_request_status");
    const shown = (await requestStatus.innerText()).trim();
    await expect(requestStatus.locator("span"), `The test request ${order.request} reads "${shown}"`).toHaveAttribute("raw-value", "paid");
    await expect(sales.locator("button[name=action_start_sample_collection]:visible")).toBeEnabled();
  });

  const reception = await as("demo.sample_delivery_staff");
  const sample = field(reception, "sample_ids").locator(".o_data_row");

  await step(reception, "Sample collection can start: the paid test request expects the sample with both tests", async () => {
    await openMenu(reception, ...TEST_REQUESTS);
    await search(reception, journey.customerName, { field: "Customer" });
    await expect(listed(reception, order.request).locator("td[name=status]")).toHaveText("Paid");
    await openListed(reception, order.request);
    await expect(status(reception)).toHaveAttribute("data-value", "paid");
    await expect(sample).toHaveCount(1);
    await expect(sample.locator("td[name=sample_type_id]")).toHaveText(journey.sampleType);
    await expect(sample.locator("td[name=status]")).toHaveText("Expected");
    await expect(sample.locator("td[name=test_ids]")).toContainText(journey.parameterName);
    await expect(sample.locator("td[name=test_ids]")).toContainText(LEAD);
    handOver("WF-01", {
      requestCode: order.request,
      requestSearch: journey.customerName,
      requestSearchField: "Customer",
      sampleLabCode: (await sample.locator("td[name=code]").innerText()).trim(),
      sampleName: (await sample.locator("td[name=customer_sample_name]").innerText()).trim(),
    });
  });
});
