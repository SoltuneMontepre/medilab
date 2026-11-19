import { callAs, portalPostAs, refAs } from "../../../support/odoo";
import { helper } from "../../../support/steps";

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

const STAGES = ["submitted", "claimed", "sent", "accepted", "confirmed", "paid"];

// Lead twice and E. coli three times on bottled water: Lead needs an acidified polyethylene bottle and E. coli a chilled
// sterile glass bottle, so 3 objects in two sampling groups make 6 expected samples.
export const SAMPLING_LINES = [
  ["sol_demo.demo_test_parameter_lead", 2],
  ["sol_demo.demo_test_parameter_e_coli", 3],
];

// The catalog product of a parameter that sol_demo seeds.
export const parameterProduct = helper("parameterProduct", function parameterProduct(xmlId) {
  return refAs(SALES, xmlId)
    .then(({ id }) => callAs(SALES, "product.product", "search", [[["parameter_id", "=", id]]], { limit: 1 }))
    .then(([id]) => id);
});

// The latest quotation of an order, as sales reads it.
export function latestQuotation(orderId) {
  return callAs(SALES, "medilab.quotation", "search_read", [[["order_id", "=", orderId]]], {
    fields: ["code", "revision", "status", "payment_request_ids"],
    order: "revision desc",
    limit: 1,
  }).then(([quotation]) => quotation);
}

// Cancels drafts the customer left on the portal, which would otherwise become their cart.
export const clearCarts = helper("clearCarts", function clearCarts(customer) {
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
});

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

export function currentRequest(order) {
  let id;
  return callAs(SALES, "sale.order", "read", [[order.id], ["payment_request_id"]])
    .then(([read]) => {
      expect(read.payment_request_id, "current payment request").to.be.an("array");
      [id] = read.payment_request_id;
    })
    .then(() => callAs(SALES, "medilab.payment.request", "read", [[id], ["kind", "amount", "remaining_amount", "deadline", "state"]]))
    .then(([paymentRequest]) => paymentRequest);
}

export function requestPaymentPath(order, request) {
  return `/orders/${order.id}/payment-requests/${request.id}/pay`;
}

// The customer reports the bank transfer and the accountant verifies the receipt.
export function payAdvance(order, customer = CUSTOMERS.nuocSach) {
  return currentRequest(order).then((request) => {
    const page = `/orders/${order.id}${request.kind === "advance" ? "/quotation" : ""}`;
    portalPostAs(customer.login, page, requestPaymentPath(order, request), { method: "bank_transfer" });
    return callAs("demo.accountant", "account.payment", "search", [
      [
        ["payment_request_id", "=", request.id],
        ["state", "=", "draft"],
      ],
    ]).then((ids) => {
      expect(ids, "reported transfer").to.have.length(1);
      return callAs("demo.accountant", "account.payment", "action_post", [ids]);
    });
  });
}

// The customer declines the latest quotation on the portal with a reason.
export const declineQuotation = helper("declineQuotation", function declineQuotation(order, reason, customer = CUSTOMERS.nuocSach) {
  return portalPostAs(customer.login, `/orders/${order.id}/quotation`, `/orders/${order.id}/quotation/decline`, { reason });
});

// Sales revises the declined quotation and sends the next revision; the Head of Sales sends one without an advance.
export const reviseQuotation = helper("reviseQuotation", function reviseQuotation(order, { advance = true } = {}) {
  const login = advance ? SALES : HEAD_OF_SALES;
  callAs(login, "sale.order", "action_revise_quotation", [[order.id]]);
  return callAs(login, "sale.order", "action_send_quotation", [[order.id]]);
});

function queueOrderProgress(order, stage, { customer, advance, sample }, step) {
  const reached = (name) => STAGES.indexOf(stage) >= STAGES.indexOf(name);
  if (reached("claimed")) {
    step(SALES, "action_claim");
    if (sample) cy.then(() => addSample(order));
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
  if (reached("confirmed")) step(SALES, "action_confirm_order");
  if (reached("paid")) cy.then(() => payAdvance(order, customer));
}

// An order for Lead (Pb), or the parameters and quantities of `lines`, taken through every step before `stage` by the
// actor who does it. Without `advance` the Head of Sales sends the quotation and the customer accepts it on the portal.
export const orderAt = helper("orderAt", function orderAt(
  stage,
  { customer = CUSTOMERS.nuocSach, advance = true, sample = true, lines = [["sol_demo.demo_test_parameter_lead", 1]] } = {},
) {
  if (!STAGES.includes(stage)) expect(STAGES, "order stage").to.include(stage);
  const order = { model: "sale.order" };
  refAs(SALES, customer.company).then(({ id }) => (order.customerId = id));
  refAs(SALES, customer.contact).then(({ id }) => (order.contactId = id));
  const products = [];
  for (const [xmlId] of lines) {
    parameterProduct(xmlId).then((productId) => products.push(productId));
  }
  cy.then(() =>
    callAs(SALES, "sale.order", "create", [
      {
        customer_id: order.customerId,
        partner_id: order.contactId,
        source: "portal",
        order_status: "submitted",
        order_line: lines.map(([, quantity], index) => [0, 0, { product_id: products[index], product_uom_qty: quantity }]),
      },
    ]),
  ).then((id) => (order.id = id));
  const step = (login, method, args = []) => cy.then(() => callAs(login, "sale.order", method, [[order.id], ...args]));
  queueOrderProgress(order, stage, { customer, advance, sample }, step);
  return cy.then(() => order);
});

export const REASON = "Giá xét nghiệm chì cao hơn báo giá năm trước.";
