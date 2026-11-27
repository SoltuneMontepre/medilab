import { expect, handOver, received, step, test } from "../support/journey";
import { choose, field, listed, money, openListed, openMenu, openRow, openTab, press, pressLabel, search, settled, status, type } from "../support/odoo";
import { cartButton, cartChoices, loads, openHeader, openOrder } from "../support/portal";

const SALES = "sale.sale_menu_root";
const ORDERS = "sol_commerce.menu_sale_order";
const MY_TASKS = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_mine"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];
const TEST_REQUESTS = ["sol_laboratory.menu_laboratory_root", "sol_laboratory.menu_laboratory_requests", "sol_laboratory.menu_test_request"];

const ADVANCE_PERCENT = 30;

// The words of Sales's Vietnamese screens that carry no name to select them by.
const VI = {
  bankTransfer: "Chuyển khoản",
  percentage: "Phần trăm",
  beforeTheReport: "Trước khi trả kết quả",
  recordPayment: "Ghi nhận thanh toán",
  unpaid: "Chưa thanh toán",
  awaitingAccountant: "Chờ kế toán xác nhận",
  advancePaid: "Đã tạm ứng",
};

const shown = async (locator) => (await locator.innerText()).trim();

test("SF-02 Order cancellation", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "orderNumber", "parameterName", "methodCode", "leadParameterName", "leadMethod", "sampleType", "salesName");
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
    handOver("SF-02", { reorderNumber: reorder.number });
  });

  await step(customer, "The customer chooses the sample type and the way of testing of each reordered line in the cart", async () => {
    await openHeader(customer, "/catalog");
    await expect(cartButton(customer)).toHaveText(/Cart \(2\)/);
    await loads(customer, () => cartButton(customer).click());
    for (const [parameter, way] of Object.entries(ways)) {
      const choices = cartChoices(customer, parameter);
      // Reordered lines come without a sample type.
      await expect(chosen(parameter, "sample_type_id")).toHaveText("Choose a sample type");
      await loads(customer, () => choices.locator("select[name=sample_type_id]").selectOption({ label: journey.sampleType }));
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

  const sales = await as("demo.sales");

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
    const lines = field(sales, "product_line_ids").locator(".o_data_row");
    await expect(lines).toHaveCount(2);
    // Sales reads the sample type under its Vietnamese name; both lines name the same one.
    const sampleTypes = await lines.locator("td[name=sample_type_id]").allInnerTexts();
    expect(sampleTypes[0].trim()).not.toBe("");
    expect(sampleTypes[1]).toBe(sampleTypes[0]);
  });

  await step(sales, "Sales sends the quotation with a 30 % advance by bank transfer and the balance due before the report", async () => {
    await press(sales, "action_send_quotation");
    await choose(sales, "payment_method", VI.bankTransfer);
    await choose(sales, "advance_mode", VI.percentage);
    await type(sales, "advance_value", ADVANCE_PERCENT);
    await choose(sales, "balance_due", VI.beforeTheReport);
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
    handOver("SF-02", { reorderTotal: reorder.total, reorderAdvance: reorder.advance });
  });

  await step(customer, "The customer reads the quotation of the reorder with its advance payment request", async () => {
    await openOrder(customer, reorder.number);
    await expect(orderBadge).toHaveText("Quoted");
    await loads(customer, () => customer.locator("main a[href$='/quotation']").click());
    await expect(customer.locator("#medilab_payment_request h2")).toHaveText("Advance payment request");
    expect(money(await customer.locator("#payment_request_amount").innerText())).toBe(reorder.advance);
  });

  await step(sales, "Sales records the advance the customer paid by bank transfer", async () => {
    await pressLabel(sales, VI.recordPayment, { within: sales.locator(".o_statusbar_buttons") });
    expect(money(await field(sales, "amount").locator("input").inputValue())).toBe(reorder.advance);
    await expect(field(sales, "method").locator("input")).toHaveValue(VI.bankTransfer);
    await type(sales, "reference", reference);
    await press(sales, "action_record");
    await expect(sales.locator(".modal:visible")).toHaveCount(0);
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.awaitingAccountant);
  });

  const accountant = await as("demo.accountant");

  await step(accountant, "The accountant confirms the advance", async () => {
    await openMenu(accountant, ...TASK_QUEUE);
    await openRow(accountant, reference);
    expect(money(await field(accountant, "amount").locator("input").inputValue())).toBe(reorder.advance);
    await expect(status(accountant)).toHaveAttribute("data-value", "draft");
    await press(accountant, "action_post");
    await expect(status(accountant)).not.toHaveAttribute("data-value", "draft");
  });

  await step(sales, "Sales confirms the reorder, which creates its paid test request; no sample is received", async () => {
    await openSalesOrder();
    await expect(field(sales, "quotation_follow_up")).toHaveText(VI.advancePaid);
    await press(sales, "action_confirm_order");
    await expect(status(sales)).toHaveAttribute("data-value", "confirmed");
    await expect(field(sales, "test_request_id")).toHaveText(/^YC\.\S+$/);
    reorder.request = await shown(field(sales, "test_request_id"));
    await openTab(sales, "other_information");
    await expect(field(sales, "test_request_status").locator("span")).toHaveAttribute("raw-value", "paid");
    handOver("SF-02", { reorderRequestCode: reorder.request });
  });

  await step(customer, "The customer sees the confirmed reorder waiting for its samples, cancellable only by request", async () => {
    await openOrder(customer, reorder.number);
    await expect(orderBadge).toHaveText("Waiting");
    await expect(actions.locator("button[data-bs-target='#order_cancellation_dialog']")).toBeVisible();
    await expect(actions.locator("button[data-bs-target='#order_cancel_dialog']")).toHaveCount(0);
  });

  await step(customer, "The customer requests the cancellation of the confirmed order with a reason", async () => {
    await actions.locator("button[data-bs-target='#order_cancellation_dialog']").click();
    const dialog = customer.locator("#order_cancellation_dialog");
    await expect(dialog).toBeVisible();
    await dialog.locator("textarea[name=reason]").fill(reason);
    await loads(customer, () => dialog.locator("button[type=submit]").click());
    await expect(customer.locator("main .text-danger")).toHaveCount(0);
    const box = customer.locator("main .border.rounded", { hasText: "Cancellation:" });
    await expect(box.locator("p").first()).toHaveText("Cancellation: requested");
    await expect(box).toContainText(reason);
    await expect(actions.locator("form[action$='/cancellation/withdraw']")).toBeVisible();
    await expect(actions.locator("button[data-bs-target='#order_cancellation_dialog']")).toHaveCount(0);
    await expect(orderBadge).toHaveText("Waiting");
  });

  await step(sales, "Sales finds the cancellation request in My Tasks and accepts it", async () => {
    await openMenu(sales, ...MY_TASKS);
    await search(sales, reorder.number);
    await expect(listed(sales, reorder.number)).toHaveCount(1);
    await openListed(sales, reorder.number);
    await expect(status(sales)).toHaveAttribute("data-value", "requested");
    await expect(field(sales, "order_id")).toHaveText(reorder.number);
    await expect(field(sales, "reason")).toHaveText(reason);
    await press(sales, "action_accept");
    const confirmation = sales.locator(".modal:visible");
    await expect(confirmation.locator(".modal-body")).toHaveText("Accepting cancels the order. A paid advance is not returned.");
    await confirmation.locator(".modal-footer .btn-primary").click();
    await settled(sales);
    await expect(status(sales)).toHaveAttribute("data-value", "accepted");
    await expect(field(sales, "decided_by_id")).toHaveText(journey.salesName);
    await expect(field(sales, "decided_at")).toHaveText(/\d/);
  });

  await step(sales, "Sales sees the reorder cancelled", async () => {
    await openSalesOrder();
    await expect(status(sales)).toHaveAttribute("data-value", "cancelled");
    reorder.status = await shown(status(sales));
    await openTab(sales, "other_information");
    reorder.requestStatusOnOrder = await field(sales, "test_request_status").locator("span").getAttribute("raw-value");
  });

  await step(customer, "The customer sees the order cancelled and the request accepted", async () => {
    await openOrder(customer, reorder.number);
    await expect(orderBadge).toHaveText("Cancelled");
    await expect(customer.locator("main .border.rounded", { hasText: "Cancellation:" }).locator("p").first()).toHaveText("Cancellation: accepted");
    await expect(actions.locator("button[data-bs-target='#order_cancellation_dialog'], button[data-bs-target='#order_cancel_dialog'], form[action$='/cancellation/withdraw']")).toHaveCount(0);
    reorder.customerStatus = await shown(orderBadge);
    handOver("SF-02", { reorderStatus: reorder.customerStatus, reorderSalesStatus: reorder.status });
  });

  const staff = await as("demo.sample_delivery_staff");
  const requestRow = () => listed(staff, reorder.request);

  const openRequest = async () => {
    await openMenu(staff, ...TEST_REQUESTS);
    await search(staff, journey.customerName, { field: "Customer" });
    await expect(requestRow()).toHaveCount(1);
    await openListed(staff, reorder.request);
  };

  // business-flows.md SF-02 main path: "the order and its test request are cancelled".
  await step(staff, "The test request of the cancelled order and its expected sample are cancelled", async () => {
    await openMenu(staff, ...TEST_REQUESTS);
    await search(staff, journey.customerName, { field: "Customer" });
    await expect(requestRow()).toHaveCount(1);
    await expect.soft(requestRow().locator("td[name=status]"), "the test request is cancelled with its order").toHaveText("Cancelled", { timeout: 1000 });
    await openListed(staff, reorder.request);
    const sample = field(staff, "sample_ids").locator(".o_data_row");
    await expect(sample).toHaveCount(1);
    await expect.soft(sample.locator("td[name=status]"), "the expected sample is cancelled with its order").toHaveText("Cancelled", { timeout: 1000 });
    reorder.requestStatusAfterAccept = await shown(status(staff));
    handOver("SF-02", { reorderRequestStatusAfterAccept: reorder.requestStatusAfterAccept });
  });

  if (reorder.requestStatusAfterAccept !== "Cancelled") {
    await step(staff, "Workaround: sample delivery staff cancel the test request by hand, which cancels its sample", async () => {
      await expect(staff.locator(".o_statusbar_buttons button[name=action_cancel]")).toBeVisible();
      await press(staff, "action_cancel");
      const confirmation = staff.locator(".modal:visible");
      await expect(confirmation.locator(".modal-body")).toHaveText("Cancel this test request with its samples and sample tests?");
      await confirmation.locator(".modal-footer .btn-primary").click();
      await settled(staff);
      await openRequest();
      await expect(status(staff)).toHaveAttribute("data-value", "cancelled");
      await expect(field(staff, "sample_ids").locator(".o_data_row td[name=status]")).toHaveText(["Cancelled"]);
    });
  }

  await step(staff, "The test request of the reorder ends cancelled", async () => {
    await openRequest();
    await expect(status(staff)).toHaveAttribute("data-value", "cancelled");
    handOver("SF-02", { reorderRequestStatus: await shown(status(staff)) });
  });
});
