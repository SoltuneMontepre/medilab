import { callAs, portalPostAs, refAs } from "../../../support/odoo";

const SALES = "demo.sales";
const HEAD_OF_SALES = "demo.head_of_sales";

// Customers that sol_demo seeds, with the portal login of the contact who orders.
export const CUSTOMERS = {
  nuocSach: {
    company: "sol_demo.demo_res_partner_nuoc_sach",
    contact: "sol_demo.demo_res_partner_hoa",
    login: "demo.customer",
  },
  anPhu: {
    company: "sol_demo.demo_res_partner_an_phu",
    contact: "sol_demo.demo_res_partner_an_phu",
    login: "portal.anphu",
  },
};

const STAGES = ["submitted", "claimed", "sent", "accepted", "confirmed"];

// The catalog product of a parameter that sol_demo seeds.
export function parameterProduct(xmlId) {
  return refAs(SALES, xmlId)
    .then(({ id }) => callAs(SALES, "product.product", "search", [[["parameter_id", "=", id]]], { limit: 1 }))
    .then(([id]) => id);
}

// The latest quotation of an order and its advance invoice, as sales reads them.
export function latestQuotation(orderId) {
  return callAs(SALES, "medilab.quotation", "search_read", [[["order_id", "=", orderId]]], {
    fields: ["code", "revision", "status", "advance_invoice_id"],
    order: "revision desc",
    limit: 1,
  }).then(([quotation]) => quotation);
}

// Cancels drafts the customer left on the portal, which would otherwise become their cart.
export function clearCarts(customer) {
  return refAs(HEAD_OF_SALES, customer.company)
    .then(({ id }) =>
      callAs(HEAD_OF_SALES, "sale.order", "search", [
        [
          ["customer_id", "=", id],
          ["order_status", "=", "draft"],
          ["source", "=", "portal"],
        ],
      ]),
    )
    .then((ids) => ids.length && callAs(HEAD_OF_SALES, "sale.order", "action_sales_cancel", [ids]));
}

function addSample(order) {
  return refAs(SALES, "sol_demo.demo_sample_type_bottled_water")
    .then(({ id }) =>
      callAs(SALES, "medilab.order.sample", "create", [
        {
          order_id: order.id,
          customer_sample_name: `Bottled water ${order.id}`,
          sample_type_id: id,
          physical_state: "liquid",
        },
      ]),
    )
    .then((sampleId) =>
      callAs(SALES, "sale.order", "read", [[order.id], ["order_line"]]).then(([read]) =>
        callAs(SALES, "sale.order.line", "write", [read.order_line, { sample_id: sampleId }]),
      ),
    );
}

// Pays the advance the way a customer who transfers it does: declared on the portal, confirmed by the accountant.
export function payAdvance(order, customer = CUSTOMERS.nuocSach) {
  return latestQuotation(order.id).then(({ advance_invoice_id: [invoice] }) => {
    portalPostAs(customer.login, `/my/invoices/${invoice}`, `/my/invoices/${invoice}/pay`, { method: "bank_transfer" });
    return callAs("demo.accountant", "account.payment", "search", [
      [
        ["invoice_ids", "in", [invoice]],
        ["state", "=", "draft"],
      ],
    ]).then((ids) => {
      expect(ids, "declared transfer").to.have.length(1);
      return callAs("demo.accountant", "account.payment", "action_post", [ids]);
    });
  });
}

// The customer declines the latest quotation on the portal with a reason.
export function declineQuotation(order, reason, customer = CUSTOMERS.nuocSach) {
  return portalPostAs(customer.login, `/orders/${order.id}/quotation`, `/orders/${order.id}/quotation/decline`, { reason });
}

// Sales revises the declined quotation and sends the next revision; the Head of Sales sends one without an advance.
export function reviseQuotation(order, { advance = true } = {}) {
  const login = advance ? SALES : HEAD_OF_SALES;
  callAs(login, "sale.order", "action_revise_quotation", [[order.id]]);
  return callAs(login, "sale.order", "action_send_quotation", [[order.id]]);
}

// An order for Lead (Pb), taken through every step before `stage` by the actor who does it.
// Without `advance` the Head of Sales sends the quotation and the customer accepts it on the portal.
export function orderAt(stage, { customer = CUSTOMERS.nuocSach, advance = true, sample = true } = {}) {
  expect(STAGES, "order stage").to.include(stage);
  const reached = (name) => STAGES.indexOf(stage) >= STAGES.indexOf(name);
  const order = { model: "sale.order" };
  refAs(SALES, customer.company).then(({ id }) => (order.customerId = id));
  refAs(SALES, customer.contact).then(({ id }) => (order.contactId = id));
  parameterProduct("sol_demo.demo_test_parameter_lead")
    .then((productId) =>
      callAs(SALES, "sale.order", "create", [
        {
          customer_id: order.customerId,
          partner_id: order.contactId,
          source: "portal",
          order_status: "submitted",
          order_line: [[0, 0, { product_id: productId, product_uom_qty: 1 }]],
        },
      ]),
    )
    .then((id) => (order.id = id));
  const step = (login, method, args = []) => cy.then(() => callAs(login, "sale.order", method, [[order.id], ...args]));
  if (reached("claimed")) {
    step(SALES, "action_claim");
    if (sample) {
      cy.then(() => addSample(order));
    }
  }
  if (reached("sent")) {
    const login = advance ? SALES : HEAD_OF_SALES;
    step(login, "write", [advance ? { advance_method: "bank_transfer", advance_mode: "percentage", advance_value: 30 } : { advance_method: "none" }]);
    step(login, "action_send_quotation");
  }
  if (reached("accepted")) {
    if (advance) {
      cy.then(() => payAdvance(order, customer));
    } else {
      cy.then(() => portalPostAs(customer.login, `/orders/${order.id}/quotation`, `/orders/${order.id}/quotation/accept`));
    }
  }
  if (reached("confirmed")) {
    step(SALES, "action_confirm_order");
  }
  return cy.then(() => order);
}
