import { expect, received, step, test } from "../support/journey";
import { field, listed, openMenu, press, save, search, shownDay, status, typeDate, workingDay, written } from "../support/odoo";
import { addToCart, loads, openHeader, send } from "../support/portal";

const SALES_DAY = "dd/mm/yyyy";

// The words of Sales's Vietnamese screens that carry no name to select them by.
const VI = { requested: "Đã yêu cầu", accepted: "Đã chấp nhận" };

const iso = (date) => date.toISOString().slice(0, 10);

test("SF-07-A1 Priority request", async ({ as }) => {
  const journey = received("tag", "parameterName", "customerName", "customerLogin", "customerPassword");
  const requested = workingDay(7);
  const pickup = workingDay(1);
  let orderNumber;

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const cart = customer.locator("main form[action='/cart/submit']");

  await step(customer, "The customer puts the journey's parameter in a new cart", async () => {
    await openHeader(customer, "/catalog");
    await customer.locator("main form[action='/catalog'] input[name=name]").fill(journey.parameterName);
    await send(customer, "/catalog");
    await addToCart(customer, journey.parameterName);
    await expect(customer.locator("main tbody tr", { hasText: journey.parameterName }).first()).toBeVisible();
  });

  await step(customer, "The customer requests priority with the date they want the results and submits the order", async () => {
    await cart.locator("#requested_date").fill(iso(requested));
    await cart.locator("#priority").check();
    await loads(customer, () => cart.locator("button[type=submit]:not([formaction])").click());
    await expect(customer.locator("main h1")).toHaveText("Order submitted");
    orderNumber = (await customer.locator("main p").first().innerText()).match(/S\d+/)[0];
  });

  const sales = await as("demo.sales");

  await step(sales, "Sales claims the order and finds the customer's priority request on the quotation", async () => {
    await openMenu(sales, "sale.sale_menu_root", "sol_commerce.menu_sale_order_queue");
    await search(sales, orderNumber);
    await press(sales, "action_claim", { within: listed(sales, orderNumber) });
    await expect(status(sales)).toHaveAttribute("data-value", "claimed");
    await expect(field(sales, "customer_id").locator("input")).toHaveValue(journey.customerName);
    await expect(shownDay(sales, "requested_date")).toHaveAttribute("data-tooltip", written(requested, SALES_DAY));
    await expect(field(sales, "priority_request")).toHaveText(VI.requested);
  });

  await step(sales, "Sales sets the sample pickup day agreed with the customer", async () => {
    await typeDate(sales, "expected_collection_date", pickup);
    await save(sales);
    await expect(shownDay(sales, "expected_collection_date")).toHaveAttribute("data-tooltip", written(pickup, SALES_DAY));
  });

  await step(sales, "Sales checks feasibility and accepts the priority, and the requested date becomes the expected return date", async () => {
    await press(sales, "action_accept_priority", { refusals: true });
    const refusal = sales.locator(".o_error_dialog");
    let answer = "";
    if (await refusal.count()) {
      await refusal.locator("summary").click();
      // The server's own message is the last Python exception line of the details, before the browser's stack.
      const details = (await refusal.locator(".o_error_detail").innerText()).split("\n").map((text) => text.trim());
      answer = details.filter((text) => /^[\w.]+(Error|Exception): /.test(text)).pop() ?? details[0];
    }
    await expect(refusal, `Accept priority answers without an error: ${answer}`).toHaveCount(0, { timeout: 1000 });
    await expect(field(sales, "priority_request")).toHaveText(VI.accepted);
    await expect(shownDay(sales, "committed_date")).toHaveAttribute("data-tooltip", written(requested, SALES_DAY));
  });
});
