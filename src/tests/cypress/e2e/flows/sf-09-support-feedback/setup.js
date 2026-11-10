import { callAs, portalPostAs, refAs } from "../../../support/odoo";

export const SALES = "demo.sales";
export const CUSTOMER = "demo.customer";
// A customer of another business, who must never see demo.customer's documents.
export const OTHER_CUSTOMER = "demo.individual";

// The business demo.customer orders for, and the contact the orders name.
const COMPANY = "sol_demo.demo_res_partner_nuoc_sach";
const CONTACT = "sol_demo.demo_res_partner_hoa";

// A text no earlier run used, so a test finds its own records.
export function unique(text) {
  return `${text} ${Date.now()}`;
}

// The catalog product of the lead parameter that sol_demo seeds.
function leadProduct() {
  return refAs(SALES, "sol_demo.demo_test_parameter_lead")
    .then(({ id }) => callAs(SALES, "product.product", "search", [[["parameter_id", "=", id]]], { limit: 1 }))
    .then(([id]) => id);
}

// An order of demo.customer that demo.sales handles, in the given status, like the completed and open orders sol_demo
// seeds. Building it through the earlier flows would replay WF-01 to WF-06.
export function orderIn(status) {
  const ids = {};
  refAs(SALES, COMPANY).then(({ id }) => (ids.company = id));
  refAs(SALES, CONTACT).then(({ id }) => (ids.contact = id));
  leadProduct().then((id) => (ids.product = id));
  callAs(SALES, "res.users", "search", [[["login", "=", SALES]]]).then(([id]) => (ids.sales = id));
  return cy
    .then(() =>
      callAs(
        SALES,
        "sale.order",
        "create",
        [
          {
            partner_id: ids.contact,
            customer_id: ids.company,
            order_status: status,
            user_id: ids.sales,
            order_line: [[0, 0, { product_id: ids.product, product_uom_qty: 1 }]],
          },
        ],
        { context: { medilab_sales_order: true } },
      ),
    )
    .then((id) => callAs(SALES, "sale.order", "read", [[id], ["name", "order_status"]]))
    .then(([order]) => {
      expect(order.order_status, "order status").to.equal(status);
      return { model: "sale.order", id: order.id, name: order.name };
    });
}

// The customer opens a support request from the portal's form, about an order or about none.
export function openRequest(subject, order = null, login = CUSTOMER) {
  return portalPostAs(login, "/support/new", "/support/open", {
    subject,
    order_id: order ? String(order.id) : "",
    body: `${subject}: please help.`,
  }).then(({ location }) => {
    const [, id] = location.match(/^\/support\/(\d+)$/);
    return { model: "medilab.support.request", id: Number(id), subject };
  });
}

// The customer rates a completed order from its page.
export function rateOrder(order, rating, comment) {
  return portalPostAs(CUSTOMER, `/orders/${order.id}`, `/orders/${order.id}/feedback`, {
    rating: String(rating),
    comment,
  });
}
