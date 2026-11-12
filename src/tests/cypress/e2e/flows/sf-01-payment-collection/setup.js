import { callAs, portalPostAs, randomId, refAs } from "../../../support/odoo";
import { CUSTOMERS, orderAt } from "../wf-01-order-to-test-request/setup";

export const ACCOUNTANT = "demo.accountant";
export const ADMINISTRATOR = "demo.administrator";
export const SALES = "demo.sales";
export const CUSTOMER = CUSTOMERS.nuocSach;

const INVOICE = "account.move";

// A confirmed order for Lead (Pb) whose 30% advance the customer paid and the accountant confirmed. The final invoice
// does not wait for testing: the catalog bills on the ordered quantity.
export function paidOrder() {
  return orderAt("confirmed").then((order) =>
    callAs(SALES, "sale.order", "read", [[order.id], ["name", "amount_total", "payment_status"]]).then(([read]) => {
      expect(read.payment_status, "advance paid").to.equal("paid");
      return { ...order, ...read };
    }),
  );
}

// An invoice as the accountant reads it.
export function readInvoice(invoice, fields) {
  return callAs(ACCOUNTANT, INVOICE, "read", [[invoice.id], fields]).then(([read]) => read);
}

// The final invoice of a paid order, which the accountant drafts and, unless `post` is false, posts. Yields `{ model, id }`.
export function finalInvoice({ post = true, values } = {}) {
  return paidOrder()
    .then((order) => callAs(ACCOUNTANT, "sale.order", "create_final_invoice", [[order.id]]))
    .then(([id]) => {
      const invoice = { model: INVOICE, id };
      if (values) {
        callAs(ACCOUNTANT, INVOICE, "write", [[id], values]);
      }
      if (post) {
        callAs(ACCOUNTANT, INVOICE, "action_post", [[id]]);
      }
      return cy.wrap(invoice, { log: false });
    });
}

// The PayOS link the customer started on the invoice and that is still waiting for money.
export function openPayosLink(invoice) {
  return callAs(
    ACCOUNTANT,
    "payment.transaction",
    "search_read",
    [
      [
        ["invoice_ids", "in", [invoice.id]],
        ["provider_code", "=", "payos"],
        ["state", "in", ["draft", "pending"]],
      ],
    ],
    { fields: ["reference", "amount"], order: "id desc", limit: 1 },
  ).then(([link]) => {
    expect(link, "open PayOS link").to.exist;
    return link;
  });
}

// The customer starts PayOS for the amount still owed on the portal, as its PayOS button does.
export function startPayos(invoice) {
  const page = `/my/invoices/${invoice.id}`;
  return portalPostAs(CUSTOMER.login, page, `${page}/pay`, { method: "payos" }).then(() => openPayosLink(invoice));
}

// The current time in Vietnam, as PayOS writes transactionDateTime.
function vietnamNow() {
  return new Date().toLocaleString("sv-SE", { timeZone: "Asia/Ho_Chi_Minh" });
}

// The transfer PayOS reports for a link: the bank moved `amount` under a new bank reference.
export function transfer(link, amount = link.amount) {
  return {
    orderCode: Number(link.reference),
    amount,
    code: "00",
    description: link.reference,
    reference: `FT${randomId().slice(0, 12)}`,
    transactionDateTime: vietnamNow(),
  };
}

// PayOS notifies the transfer to the webhook, signed with the checksum key.
export function notifyPayos(data) {
  return cy.task("payosNotify", data).should("eq", 200);
}

// The online payments recorded against the invoice.
export function onlinePayments(invoice) {
  return callAs(
    ACCOUNTANT,
    "account.payment",
    "search_read",
    [
      [
        ["invoice_ids", "in", [invoice.id]],
        ["method", "=", "online"],
      ],
    ],
    { fields: ["amount", "state"] },
  );
}

// A transfer PayOS reported as paid for the whole invoice on `day`, which the system holds no payment for. Only the
// gateway writes transactions, so the administrator stands in for it. Yields its id.
export function unrecordedTransfer(invoice, day) {
  const ids = {};
  refAs(ADMINISTRATOR, "sol_commerce.payment_provider_payos").then(({ id }) => (ids.provider = id));
  refAs(ADMINISTRATOR, "sol_commerce.payment_method_payos_qr").then(({ id }) => (ids.method = id));
  return readInvoice(invoice, ["amount_residual", "currency_id", "partner_id"]).then((read) => {
    const reference = `FT${randomId().slice(0, 12)}`;
    return callAs(ADMINISTRATOR, "payment.transaction", "create", [
      {
        provider_id: ids.provider,
        payment_method_id: ids.method,
        reference,
        payos_bank_reference: reference,
        amount: read.amount_residual,
        currency_id: read.currency_id[0],
        partner_id: read.partner_id[0],
        operation: "online_redirect",
        state: "done",
        // Noon in Vietnam.
        payos_transferred_at: `${day} 05:00:00`,
        invoice_ids: [[6, 0, [invoice.id]]],
      },
    ]);
  });
}

// A day with no reconciliation and no PayOS transfer yet: the day before the earliest of either.
export function unreconciledDay() {
  const days = [new Date().toISOString().slice(0, 10)];
  callAs(ACCOUNTANT, "medilab.reconciliation.day", "search_read", [[]], { fields: ["day"], order: "day asc", limit: 1 }).then(
    ([earliest]) => earliest && days.push(earliest.day),
  );
  callAs(ACCOUNTANT, "payment.transaction", "search_read", [[["payos_transferred_at", "!=", false]]], {
    fields: ["payos_transferred_at"],
    order: "payos_transferred_at asc",
    limit: 1,
  }).then(([earliest]) => earliest && days.push(earliest.payos_transferred_at.slice(0, 10)));
  return cy.then(() => {
    const earliest = days.reduce((first, other) => (other < first ? other : first), days[0]);
    const day = new Date(`${earliest}T00:00:00Z`);
    day.setUTCDate(day.getUTCDate() - 1);
    return day.toISOString().slice(0, 10);
  });
}
