import { expect, handOver, outside, received, step, test } from "../support/journey";
import { choose, field, listed, money, openListed, openMenu, openRow, openTab, press, pressLabel, save, search, settled, shownDay, status, type, typeDate, workingDay, written } from "../support/odoo";
import { cartButton, cartChoices, loads, openHeader, openOrder } from "../support/portal";

const SALES = "sale.sale_menu_root";
const ORDERS = "sol_commerce.menu_sale_order";
const MY_TASKS = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_mine"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

const ADVANCE_PERCENT = 30;

// The words of Sales's Vietnamese screens that carry no name to select them by.
const VI = {
  bankTransfer: "Chuyển khoản",
  percentage: "Phần trăm",
  recordPayment: "Ghi nhận thanh toán",
  unpaid: "Chưa thanh toán",
  awaitingAccountant: "Chờ kế toán xác nhận",
  advancePaid: "Đã tạm ứng",
  acceptingCancels: "Chấp nhận sẽ hủy đơn hàng. Khoản tạm ứng đã thanh toán không được hoàn lại.",
};

const SALES_DAY = "dd/mm/yyyy";

const shown = async (locator) => (await locator.innerText()).trim();

test("SF-02 Order cancellation", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "orderNumber", "salesOrderStatusAfterReport", "parameterName", "methodCode", "leadParameterName", "leadMethod", "sampleType", "salesLogin", "salesName");
  const reference = `Journey reorder advance ${journey.tag}`;
  const reason = `Journey cancel ${journey.tag}: samples no longer needed`;
  const ways = { [journey.parameterName]: `${journey.parameterName} – ${journey.methodCode}`, [journey.leadParameterName]: `${journey.leadParameterName} – ${journey.leadMethod}` };
  const reorder = {};

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const orderBadge = customer.locator("main h1 + span.badge");
  const actions = customer.locator("main #order_actions");
  const chosen = (line, select) => cartChoices(customer, line).locator(`select[name=${select}] option:checked`);

  await step(customer, "WF-01-A3: The customer reorders the completed order, which starts a draft order with the same lines", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(orderBadge).toHaveText("Completed");
    await loads(customer, () => actions.locator("form[action$='/reorder'] button[type=submit]").click());
    await expect(customer).toHaveURL(/\/orders\/\d+(\?|$)/);
    await expect(customer.locator("main h1")).toHaveText(/^S\d+$/);
    reorder.number = await shown(customer.locator("main h1"));
    expect(reorder.number).not.toBe(journey.orderNumber);
    await expect(orderBadge).toHaveText("Draft");
    for (const parameter of Object.keys(ways)) await expect(customer.locator("main tbody tr", { hasText: parameter })).toHaveCount(1);
  });

  await step(customer, "The customer chooses the sample type and the way of testing of each reordered line in the cart", async () => {
    await openHeader(customer, "/catalog");
    await expect(cartButton(customer)).toHaveText(/Cart \(2\)/);
    await loads(customer, () => cartButton(customer).click());
    for (const [parameter, way] of Object.entries(ways)) {
      // Reordered lines come without a sample type.
      await expect(chosen(parameter, "sample_type_id")).toHaveText("Choose a sample type");
      await loads(customer, () => cartChoices(customer, parameter).locator("select[name=sample_type_id]").selectOption({ label: journey.sampleType }));
      if ((await chosen(parameter, "parameter_method_id").innerText()).trim() !== way) {
        await loads(customer, () => cartChoices(customer, parameter).locator("select[name=parameter_method_id]").selectOption({ label: way }));
      }
      await expect(chosen(parameter, "sample_type_id")).toHaveText(journey.sampleType);
      await expect(chosen(parameter, "parameter_method_id")).toHaveText(way);
    }
    await expect(customer.locator("main .o_medilab_expected_sampling .o_medilab_expected")).toHaveText("1");
  });

  await step(customer, "The customer submits the reorder, which waits in the sales queue", async () => {
    const cart = customer.locator("main form[action='/cart/submit']");
    await loads(customer, () => cart.locator("button[type=submit]:not([formaction])").click());
    await expect(customer.locator("main h1")).toHaveText("Order submitted");
    await expect(customer.locator("main p").first()).toContainText(reorder.number);
  });

  const sales = await as(journey.salesLogin);

  const openSalesOrder = async () => {
    await openMenu(sales, SALES, ORDERS);
    await openRow(sales, reorder.number);
  };

  await step(sales, "Sales claims the reorder from the unclaimed queue", async () => {
    await openMenu(sales, SALES, "sol_commerce.menu_sale_order_queue");
    await search(sales, reorder.number);
    await press(sales, "action_claim", { within: listed(sales, reorder.number) });
    await expect(status(sales)).toHaveAttribute("data-value", "claimed");
    await expect(field(sales, "customer_id").locator("input")).toHaveValue(journey.customerName);
    await expect(field(sales, "user_id").locator("input")).toHaveValue(journey.salesName);
  });

  await step(sales, "Sales confirms the selected ways and the expected sampling needs", async () => {
    const lines = field(sales, "product_line_ids").locator(".o_data_row");
    await expect(lines).toHaveCount(2);
    await expect(lines.filter({ hasText: journey.parameterName }).locator("td[name=parameter_method_id]")).toContainText(journey.methodCode);
    await expect(lines.filter({ hasText: journey.leadParameterName }).locator("td[name=parameter_method_id]")).toContainText(journey.leadMethod);
    // Sales reads the sample type under its Vietnamese name; both lines name the same one.
    const sampleTypes = await lines.locator("td[name=sample_type_id]").allInnerTexts();
    expect(sampleTypes[0].trim()).not.toBe("");
    expect(sampleTypes[1]).toBe(sampleTypes[0]);
    await expect(lines.locator("td[name=expected_sample_count]")).toHaveText(["1", "1"]);
  });

  await step(sales, "Sales sets the sample pickup day agreed with the customer", async () => {
    const pickup = workingDay(1);
    await typeDate(sales, "expected_collection_date", pickup);
    await save(sales);
    await expect(shownDay(sales, "expected_collection_date")).toHaveAttribute("data-tooltip", written(pickup, SALES_DAY));
  });

  await step(sales, "Sales sends the quotation with an advance payment request by bank transfer, PayOS being unreachable (WF-01-A4)", async () => {
    await press(sales, "action_send_quotation");
    await choose(sales, "payment_method", VI.bankTransfer);
    await choose(sales, "advance_mode", VI.percentage);
    await type(sales, "advance_value", ADVANCE_PERCENT);
    await press(sales, "action_send");
    await expect(sales.locator(".modal:visible")).toHaveCount(0);
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.unpaid);
    await openTab(sales, "revisions");
    const revision = field(sales, "quotation_ids").locator(".o_data_row");
    await expect(revision).toHaveCount(1);
    reorder.total = money(await revision.locator("td[name=amount_total]").innerText());
    await openTab(sales, "payment");
    const advance = field(sales, "payment_request_ids").locator(".o_data_row");
    await expect(advance).toHaveCount(1);
    reorder.advance = money(await advance.locator("td[name=amount]").innerText());
    expect(reorder.advance).toBe(Math.round((reorder.total * ADVANCE_PERCENT) / 100));
  });

  await step(customer, "The customer reads the quotation of the reorder with its advance payment request", async () => {
    await openOrder(customer, reorder.number);
    await expect(orderBadge).toHaveText("Quoted");
    await loads(customer, () => customer.locator("main a[href$='/quotation']").click());
    await expect(customer.locator("#medilab_payment_request h2")).toHaveText("Advance payment request");
    expect(money(await customer.locator("#payment_request_amount").innerText())).toBe(reorder.advance);
  });

  await outside("The customer pays the advance by bank transfer (WF-01-A4)", "the customer's bank");

  await step(sales, "Sales records the advance paid by bank transfer as a pending payment (WF-01-A4)", async () => {
    await pressLabel(sales, VI.recordPayment, { within: sales.locator(".o_statusbar_buttons") });
    expect(money(await field(sales, "amount").locator("input").inputValue())).toBe(reorder.advance);
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
    expect(money(await field(accountant, "amount").locator("input").inputValue())).toBe(reorder.advance);
    await expect(status(accountant)).toHaveAttribute("data-value", "draft");
    await press(accountant, "action_post");
    await expect(status(accountant)).not.toHaveAttribute("data-value", "draft");
  });

  await step(sales, "Sales confirms the reorder, which creates its test request", async () => {
    await openSalesOrder();
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.advancePaid);
    await press(sales, "action_confirm_order");
    await expect(status(sales)).toHaveAttribute("data-value", "confirmed");
    await expect(field(sales, "test_request_id")).toHaveText(/^YC\.\S+$/);
    reorder.request = await shown(field(sales, "test_request_id"));
    handOver("SF-02", { reorderNumber: reorder.number, reorderRequestCode: reorder.request });
  });

  await step(customer, "The customer requests the cancellation of the confirmed order with a reason", async () => {
    await openOrder(customer, reorder.number);
    await actions.locator("button[data-bs-target='#order_cancellation_dialog']").click();
    const dialog = customer.locator("#order_cancellation_dialog");
    await expect(dialog).toBeVisible();
    await dialog.locator("textarea[name=reason]").fill(reason);
    await loads(customer, () => dialog.locator("button[type=submit]").click());
    await expect(customer.locator("main .text-danger")).toHaveCount(0);
    const box = customer.locator("main .border.rounded", { hasText: "Cancellation:" });
    await expect(box.locator("p").first()).toHaveText("Cancellation: requested");
    await expect(box).toContainText(reason);
  });

  await step(sales, "Sales finds the cancellation request in their to-do list and accepts it", async () => {
    await openMenu(sales, ...MY_TASKS);
    await search(sales, reorder.number);
    await expect(listed(sales, reorder.number)).toHaveCount(1);
    await openListed(sales, reorder.number);
    await expect(status(sales)).toHaveAttribute("data-value", "requested");
    await expect(field(sales, "order_id")).toHaveText(reorder.number);
    await expect(field(sales, "reason")).toHaveText(reason);
    await press(sales, "action_accept");
    const confirmation = sales.locator(".modal:visible");
    await expect(confirmation.locator(".modal-body")).toHaveText(VI.acceptingCancels);
    await confirmation.locator(".modal-footer .btn-primary").click();
    await settled(sales);
    await expect(status(sales)).toHaveAttribute("data-value", "accepted");
  });

  await step(sales, "The order and its test request are cancelled", async () => {
    await openSalesOrder();
    await expect(status(sales)).toHaveAttribute("data-value", "cancelled");
    handOver("SF-02", { reorderSalesStatus: await shown(status(sales)) });
    await openTab(sales, "other_information");
    await expect(field(sales, "test_request_status").locator("span"), `test request ${reorder.request} is cancelled with its order`).toHaveAttribute("raw-value", "cancelled");
    handOver("SF-02", { reorderRequestStatus: await shown(field(sales, "test_request_status")) });
  });

  await outside("The customer is told the cancellation is accepted", "e-mail");
});
