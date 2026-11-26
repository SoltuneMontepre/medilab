import fs from "node:fs";
import { expect, handOver, received, step, test } from "../support/journey";
import { choose, field, listed, money, openListed, openMenu, openRow, openTab, press, pressLabel, search, status, type } from "../support/odoo";
import { follow, loads, openHeader, openMyAccount, openOrder } from "../support/portal";

const SALES = "sale.sale_menu_root";
const ORDERS = "sol_commerce.menu_sale_order";
const COMMERCE = "sol_commerce.menu_commerce_root";
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

// What the customer still pays in cash after the transfer.
const CASH_PART = 200000;

// The words of Sales's Vietnamese screens that carry no name to select them by.
const VI = {
  recordPayment: "Ghi nhận thanh toán",
  cash: "Tiền mặt",
  balance: "Số dư",
  open: "Mở",
  funded: "Đã thu đủ",
  partlyPaid: "Thanh toán một phần",
  partlyPaidAwaiting: "Thanh toán một phần (chờ xác nhận)",
  paid: "Đã thanh toán",
  awaitingAccountant: "Chờ kế toán xác nhận",
  confirmed: "Đã xác nhận",
  rejected: "Đã từ chối",
  awaitingFullPayment: "Chờ thanh toán đủ",
};

// Where a payment receipt would be linked from; only the address /my/invoices/<invoice>/receipt/<payment> serves it.
const RECEIPT_LINK = "main a[href*='/receipt/']";

const english = (amount) => amount.toLocaleString("en-US");
const ascending = (amounts) => [...amounts].sort((first, second) => first - second);

test("SF-01 Invoicing and payment collection", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "orderNumber", "orderTotal", "advanceAmount", "balanceAmount");
  const transferPart = journey.balanceAmount - CASH_PART;
  const transfer = `Journey transfer ${journey.tag}`;
  const refusedCash = `Journey cash first try ${journey.tag}`;
  const cash = `Journey cash ${journey.tag}`;
  const reason = `The cash did not reach the cashier ${journey.tag}`;
  const posted = [];

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const request = customer.locator("#medilab_payment_request");
  const payForm = request.locator("form[action$='/pay']");
  const requestAmount = async (id) => money(await request.locator(`#payment_request_${id}`).innerText());

  await step(customer, "The customer sees the open balance payment request on the order", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(request.locator("h2")).toHaveText("Balance payment request");
    await expect(request.locator("h2 + p")).toHaveText("Open");
    expect(await requestAmount("amount")).toBe(journey.balanceAmount);
    expect(await requestAmount("remaining")).toBe(journey.balanceAmount);
    const applied = request.locator("dt", { hasText: "Already applied to the order" }).locator("xpath=following-sibling::dd[1]");
    expect(money(await applied.innerText())).toBe(journey.advanceAmount);
    await expect(payForm.locator("#medilab_payment_amount")).toHaveValue(String(journey.balanceAmount));
  });

  await step(customer, "SF-01-A1: The customer pays a first part by bank transfer and reports it on the order", async () => {
    await payForm.locator("#medilab_payment_amount").fill(String(transferPart));
    await payForm.locator("button[data-bs-target='#medilab_bank_transfer']").click();
    const anHourAgoInVietnam = new Date(Date.now() + 6 * 60 * 60 * 1000).toISOString().slice(0, 16);
    await payForm.locator("#medilab_received_at").fill(anHourAgoInVietnam);
    await payForm.locator("#medilab_transfer_reference").fill(transfer);
    await loads(customer, () => payForm.locator("button[name=method][value=bank_transfer]").click());
    await expect(customer).toHaveURL(/\/orders\/\d+$/);
    await expect(request.locator("h2 + p")).toHaveText("Open");
    expect(await requestAmount("pending")).toBe(transferPart);
    expect(await requestAmount("remaining")).toBe(journey.balanceAmount);
  });

  const accountant = await as("demo.accountant");

  const openPaymentTask = async (reference, amount, method) => {
    await openMenu(accountant, ...TASK_QUEUE);
    await openRow(accountant, reference);
    await expect(field(accountant, "memo").locator("input")).toHaveValue(reference);
    expect(money(await field(accountant, "amount").locator("input").inputValue())).toBe(amount);
    await expect(field(accountant, "method").locator("input")).toHaveValue(method);
    await expect(status(accountant)).toHaveAttribute("data-value", "draft");
  };

  const taskIsDone = async (reference) => {
    await openMenu(accountant, ...TASK_QUEUE);
    await search(accountant, reference);
    await expect(listed(accountant, reference)).toHaveCount(0);
  };

  // Confirms the payment on screen and returns the number of the invoice it posts.
  const confirmPayment = async () => {
    await press(accountant, "action_post");
    await expect(status(accountant)).not.toHaveAttribute("data-value", "draft");
    await expect(accountant.locator("button[name=action_reject_payment]:visible")).toHaveCount(0);
    await expect(field(accountant, "reviewed_by_id")).toHaveText(/\S/);
    await press(accountant, "button_open_invoices");
    await expect(status(accountant)).toHaveAttribute("data-value", "posted");
    await expect(field(accountant, "name")).toHaveText(/\S/);
    return (await field(accountant, "name").innerText()).trim();
  };

  await step(accountant, "SF-01-A1: The accountant confirms the transfer from its payment confirmation task, which posts the invoice of that part", async () => {
    await openPaymentTask(transfer, transferPart, "Bank transfer");
    posted.push(await confirmPayment());
    await taskIsDone(transfer);
  });

  const sales = await as("demo.sales");
  const balance = field(sales, "payment_request_ids").locator(".o_data_row", { has: sales.locator("td[name=kind]", { hasText: VI.balance }) });
  const recorded = (reference) => field(sales, "recorded_payments_html").locator("tr", { hasText: reference });
  const balanceAmount = async (column) => money(await balance.locator(`td[name=${column}]`).innerText());

  const openSalesOrder = async () => {
    await openMenu(sales, SALES, ORDERS);
    await openRow(sales, journey.orderNumber);
  };

  const recordCash = async (reference) => {
    await pressLabel(sales, VI.recordPayment, { within: sales.locator(".o_statusbar_buttons") });
    expect(money(await field(sales, "amount").locator("input").inputValue())).toBe(CASH_PART);
    await choose(sales, "method", VI.cash);
    await type(sales, "reference", reference);
    await press(sales, "action_record");
    await expect(sales.locator(".modal:visible")).toHaveCount(0);
    await expect(sales.locator("button[name=action_awaiting_payment_confirmation]:visible")).toBeDisabled();
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.partlyPaidAwaiting);
    await openTab(sales, "payment");
    await expect(recorded(reference)).toContainText(VI.cash);
    await expect(recorded(reference)).toContainText(VI.awaitingAccountant);
    expect(await balanceAmount("pending_amount")).toBe(CASH_PART);
  };

  await step(sales, "SF-01-A1: Sales sees the first part verified and the rest of the balance still to pay", async () => {
    await openSalesOrder();
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.partlyPaid);
    await openTab(sales, "payment");
    await expect(balance).toHaveCount(1);
    await expect(balance.locator("td[name=state]")).toHaveText(VI.open);
    expect(await balanceAmount("verified_amount")).toBe(transferPart);
    expect(await balanceAmount("pending_amount")).toBe(0);
    expect(await balanceAmount("remaining_amount")).toBe(CASH_PART);
    await expect(recorded(transfer)).toContainText(VI.confirmed);
  });

  await step(sales, "SF-01-E1: Sales records the rest as a cash payment", async () => {
    await recordCash(refusedCash);
  });

  await step(accountant, "SF-01-E1: The accountant rejects the payment sales recorded, with the reason", async () => {
    await openPaymentTask(refusedCash, CASH_PART, "Cash");
    await type(accountant, "rejection_reason", reason);
    await press(accountant, "action_reject_payment");
    await expect(status(accountant)).toHaveAttribute("data-value", "canceled");
    await expect(field(accountant, "rejection_reason")).toHaveText(reason);
    await expect(accountant.locator("button[name=button_open_invoices]:visible")).toHaveCount(0);
    await taskIsDone(refusedCash);
  });

  await step(sales, "SF-01-E1: Sales reads the reason on the order, whose balance is back to what it was", async () => {
    await openSalesOrder();
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.partlyPaid);
    await openTab(sales, "payment");
    await expect(recorded(refusedCash)).toContainText(VI.rejected);
    await expect(recorded(refusedCash)).toContainText(reason);
    expect(await balanceAmount("verified_amount")).toBe(transferPart);
    expect(await balanceAmount("pending_amount")).toBe(0);
    expect(await balanceAmount("remaining_amount")).toBe(CASH_PART);
  });

  await step(sales, "SF-01-A2: Sales records the cash payment again", async () => {
    await recordCash(cash);
  });

  await step(accountant, "SF-01-A2: The accountant confirms the cash payment, which posts the closing invoice", async () => {
    await openPaymentTask(cash, CASH_PART, "Cash");
    posted.push(await confirmPayment());
    await taskIsDone(cash);
  });

  await step(accountant, "The accountant finds every invoice of the order posted and paid", async () => {
    await openMenu(accountant, COMMERCE, "sol_commerce.menu_invoice");
    await search(accountant, journey.customerName);
    const invoices = listed(accountant, journey.customerName);
    await expect(invoices).toHaveCount(3);
    for (const number of posted) await expect(listed(accountant, number)).toHaveCount(1);
    const totals = (await invoices.locator("td[name=amount_total_in_currency_signed]").allInnerTexts()).map(money);
    expect(ascending(totals)).toEqual(ascending([journey.advanceAmount, transferPart, CASH_PART]));
    expect(totals.reduce((sum, total) => sum + total)).toBe(journey.orderTotal);
    await expect(invoices.locator("td[name=status_in_payment]")).toHaveText(["Paid", "Paid", "Paid"]);
    expect((await invoices.locator("td[name=amount_residual_signed]").allInnerTexts()).map(money)).toEqual([0, 0, 0]);
  });

  await step(accountant, "The accountant sees the reconciliation days, of which the demo's locked day takes no more changes", async () => {
    await openMenu(accountant, COMMERCE, "sol_commerce.menu_reconciliation");
    await expect(listed(accountant, "Locked").first()).toBeVisible();
    await openListed(accountant, "Locked");
    await expect(status(accountant)).toHaveAttribute("data-value", "locked");
    await expect(accountant.locator("button[name=action_lock]:visible, button[name=action_post_missing_payments]:visible")).toHaveCount(0);
  });

  await step(customer, "The customer sees the balance payment request funded, with nothing left to pay", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(request.locator("h2")).toHaveText("Balance payment request");
    await expect(request.locator("h2 + p")).toHaveText("Funded");
    expect(await requestAmount("verified")).toBe(journey.balanceAmount);
    expect(await requestAmount("remaining")).toBe(0);
    await expect(request.locator("#payment_request_pending")).toHaveCount(0);
    await expect(payForm).toHaveCount(0);
    handOver("SF-01", { paymentStatusPortal: (await request.locator("h2 + p").innerText()).trim() });
  });

  let receiptLinks = 0;

  await step(customer, "The customer finds the invoices of the payments in My account and downloads each one", async () => {
    await openMyAccount(customer);
    await follow(customer, "/my/invoices?filterby=invoices");
    const invoices = customer.locator("main table tbody td:first-child a");
    await expect(invoices).toHaveCount(3);
    const numbers = (await invoices.allInnerTexts()).map((number) => number.trim());
    expect(numbers).toEqual(expect.arrayContaining(posted));
    const totals = [];
    for (const number of numbers) {
      await loads(customer, () => customer.locator("main table tbody td:first-child a", { hasText: number }).click());
      await expect(customer.locator(".breadcrumb-item.active")).toHaveText(number);
      totals.push(money(await customer.locator("#sidebar_price h2").innerText()));
      await expect(customer.locator("[name=invoice_paid_badge]")).toHaveText("Paid");
      expect(money(await customer.locator("main .alert-info", { hasText: "Amount owed" }).innerText())).toBe(0);
      await expect(customer.locator("main form[action$='/pay']")).toHaveCount(0);
      const [download] = await Promise.all([customer.waitForEvent("download"), customer.locator("a.o_download_btn").click()]);
      expect(download.suggestedFilename()).toBe(`${number.replaceAll("/", "_")}.pdf`);
      expect(fs.readFileSync(await download.path()).subarray(0, 5).toString()).toBe("%PDF-");
      receiptLinks += await customer.locator(RECEIPT_LINK).count();
      await loads(customer, () => customer.locator(".breadcrumb a[href^='/my/invoices']").click());
    }
    expect(ascending(totals)).toEqual(ascending([journey.advanceAmount, transferPart, CASH_PART]));
    handOver("SF-01", { invoiceNumbers: numbers });
  });

  await step(customer, "The customer reads the notice of each recorded payment", async () => {
    await openHeader(customer, "/my/account");
    await follow(customer, "/my/notifications");
    const notices = customer.locator("#portal-notifications li", { hasText: "Payment receipt" });
    await expect(notices).toHaveCount(3);
    await loads(customer, () => notices.first().locator("a").click());
    await expect(customer.locator("#notification-subject")).toHaveText("Payment receipt");
    await expect(customer.locator("#notification-body")).toHaveText(new RegExp(`Payment of ${english(CASH_PART)}\\s₫ was recorded\\.`));
    receiptLinks += await customer.locator(RECEIPT_LINK).count();
  });

  // No page links to the receipt: the report shows this step as failed and the flow goes on.
  await step(customer, "The customer opens the receipt of a payment", async () => {
    expect.soft(receiptLinks, "an invoice page or the payment notice links to the payment receipt").toBeGreaterThan(0);
  });

  await step(sales, "Sales sees the order paid in full, so its report is not withheld for payment", async () => {
    await openSalesOrder();
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.paid);
    await expect(field(sales, "result_status")).not.toHaveText(VI.awaitingFullPayment);
    await expect(sales.locator(".o_statusbar_buttons button:visible", { hasText: VI.recordPayment })).toHaveCount(0);
    await expect(sales.locator("button[name=action_awaiting_payment_confirmation]:visible")).toHaveCount(0);
    await openTab(sales, "payment");
    await expect(balance.locator("td[name=state]")).toHaveText(VI.funded);
    expect(await balanceAmount("verified_amount")).toBe(journey.balanceAmount);
    expect(await balanceAmount("remaining_amount")).toBe(0);
    await expect(field(sales, "payment_request_ids").locator(".o_data_row td[name=state]")).toHaveText([VI.funded, VI.funded]);
    await expect(recorded(cash)).toContainText(VI.confirmed);
    handOver("SF-01", { paymentStatus: (await field(sales, "payment_badge_status").innerText()).trim(), paidInFull: true });
  });
});
