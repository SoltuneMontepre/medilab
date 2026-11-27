import fs from "node:fs";
import { expect, handOver, received, step, test } from "../support/journey";
import { field, listed, money, openMenu, openRow, openTab, press, search, status } from "../support/odoo";
import { follow, loads, openMyAccount, openOrder } from "../support/portal";

const SALES = "sale.sale_menu_root";
const ORDERS = "sol_commerce.menu_sale_order";
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

// The words of Sales's Vietnamese screens that carry no name to select them by.
const VI = {
  balance: "Số dư",
  funded: "Đã thu đủ",
  paid: "Đã thanh toán",
};

test("SF-01 Invoicing and payment collection", async ({ as }) => {
  const journey = received("tag", "customerName", "customerLogin", "customerPassword", "orderNumber", "advanceAmount", "balanceAmount");
  const transfer = `Journey transfer ${journey.tag}`;
  const payment = {};

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const request = customer.locator("#medilab_payment_request");
  const payForm = request.locator("form[action$='/pay']");
  const requestAmount = async (id) => money(await request.locator(`#payment_request_${id}`).innerText());

  await step(customer, "MediLab sends the balance payment request: the customer finds it open on the order", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(request.locator("h2")).toHaveText("Balance payment request");
    await expect(request.locator("h2 + p")).toHaveText("Open");
    expect(await requestAmount("amount")).toBe(journey.balanceAmount);
    expect(await requestAmount("remaining")).toBe(journey.balanceAmount);
    const applied = request.locator("dt", { hasText: "Already applied to the order" }).locator("xpath=following-sibling::dd[1]");
    expect(money(await applied.innerText())).toBe(journey.advanceAmount);
    await expect(payForm.locator("#medilab_payment_amount")).toHaveValue(String(journey.balanceAmount));
  });

  await step(customer, "The customer pays the balance at once by bank transfer and reports it on the order (PayOS is not reachable)", async () => {
    await payForm.locator("button[data-bs-target='#medilab_bank_transfer']").click();
    const anHourAgoInVietnam = new Date(Date.now() + 6 * 60 * 60 * 1000).toISOString().slice(0, 16);
    await payForm.locator("#medilab_received_at").fill(anHourAgoInVietnam);
    await payForm.locator("#medilab_transfer_reference").fill(transfer);
    await loads(customer, () => payForm.locator("button[name=method][value=bank_transfer]").click());
    await expect(customer).toHaveURL(/\/orders\/\d+$/);
    expect(await requestAmount("pending")).toBe(journey.balanceAmount);
  });

  const accountant = await as("demo.accountant");

  await step(accountant, "The accountant verifies the transfer from its payment confirmation task, which posts its invoice", async () => {
    await openMenu(accountant, ...TASK_QUEUE);
    await openRow(accountant, transfer);
    await expect(field(accountant, "memo").locator("input")).toHaveValue(transfer);
    expect(money(await field(accountant, "amount").locator("input").inputValue())).toBe(journey.balanceAmount);
    await expect(field(accountant, "method").locator("input")).toHaveValue("Bank transfer");
    await expect(status(accountant)).toHaveAttribute("data-value", "draft");
    await press(accountant, "action_post");
    await expect(status(accountant)).not.toHaveAttribute("data-value", "draft");
    await expect(field(accountant, "reviewed_by_id")).toHaveText(/\S/);
    await press(accountant, "button_open_invoices");
    await expect(status(accountant)).toHaveAttribute("data-value", "posted");
    payment.invoice = (await field(accountant, "name").innerText()).trim();
    await openMenu(accountant, ...TASK_QUEUE);
    await search(accountant, transfer);
    await expect(listed(accountant, transfer)).toHaveCount(0);
  });

  const sales = await as("demo.sales");

  await step(sales, "The order reads paid in full", async () => {
    await openMenu(sales, SALES, ORDERS);
    await openRow(sales, journey.orderNumber);
    await expect(field(sales, "payment_badge_status")).toHaveText(VI.paid);
    await openTab(sales, "payment");
    const balance = field(sales, "payment_request_ids").locator(".o_data_row", { has: sales.locator("td[name=kind]", { hasText: VI.balance }) });
    await expect(balance.locator("td[name=state]")).toHaveText(VI.funded);
    expect(money(await balance.locator("td[name=remaining_amount]").innerText())).toBe(0);
    handOver("SF-01", { paymentStatus: (await field(sales, "payment_badge_status").innerText()).trim(), paidInFull: true });
  });

  await step(customer, "The customer downloads the invoice of the payment", async () => {
    await openMyAccount(customer);
    await follow(customer, "/my/invoices?filterby=invoices");
    const invoice = customer.locator("main table tbody td:first-child a", { hasText: payment.invoice });
    await expect(invoice).toHaveCount(1);
    await loads(customer, () => invoice.click());
    await expect(customer.locator(".breadcrumb-item.active")).toHaveText(payment.invoice);
    await expect(customer.locator("[name=invoice_paid_badge]")).toHaveText("Paid");
    const [download] = await Promise.all([customer.waitForEvent("download"), customer.locator("a.o_download_btn").click()]);
    expect(download.suggestedFilename()).toBe(`${payment.invoice.replaceAll("/", "_")}.pdf`);
    expect(fs.readFileSync(await download.path()).subarray(0, 5).toString()).toBe("%PDF-");
    handOver("SF-01", { invoiceNumbers: [payment.invoice] });
  });

  // customer.md, Invoices: after payment the customer downloads the payment receipt from the invoice.
  await step(customer, "The customer downloads the receipt of the payment", async () => {
    const receipt = customer.locator("main a[href*='/receipt/']");
    await expect(receipt, "the paid invoice links to the receipt of its payment").toHaveCount(1);
    await loads(customer, () => receipt.click());
    await expect(customer.locator("main")).toContainText(payment.invoice);
  });
});
