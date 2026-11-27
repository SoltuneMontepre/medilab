import { expect, handOver, received, step, test } from "../support/journey";
import { field, listed, openListed, openMenu, openRow, openTab, search } from "../support/odoo";
import { loads, openOrder } from "../support/portal";

const SALES = "sale.sale_menu_root";

const RATING = 4;

test("SF-09-A4 The customer rates a completed order", async ({ as }) => {
  const journey = received("tag", "customerLogin", "customerPassword", "orderNumber", "orderStatusAfterReport", "salesLogin");
  const comment = `Clear report and fast service ${journey.tag}`;

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const feedbackForm = customer.locator("main form[action$='/feedback']");
  const rating = customer.locator("main p", { hasText: "Your rating:" });

  await step(customer, "The customer rates the completed order once, with a comment", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(customer.locator("main h1 + span.badge")).toHaveText("Completed");
    await feedbackForm.locator(`#rating-${RATING}`).check();
    await feedbackForm.locator("textarea[name=comment]").fill(comment);
    await loads(customer, () => feedbackForm.locator("button[type=submit]").click());
    await expect(rating).toHaveText(`Your rating: ${RATING}/5`);
    await expect(customer.locator("main")).toContainText(comment);
    // business-flows.md SF-09: rating an order twice is refused.
    await openOrder(customer, journey.orderNumber);
    await expect(rating).toHaveText(`Your rating: ${RATING}/5`);
    await expect(feedbackForm).toHaveCount(0);
    handOver("SF-09-A4", { sf09a4Rating: RATING, sf09a4FeedbackComment: comment });
  });

  const sales = await as(journey.salesLogin);

  await step(sales, "The feedback is visible to Sales on the order", async () => {
    await openMenu(sales, SALES, "sol_commerce.menu_sale_order");
    await openRow(sales, journey.orderNumber);
    await openTab(sales, "feedback");
    await expect(field(sales, "feedback_rating").locator("input")).toHaveValue(String(RATING));
    await expect(field(sales, "feedback_comment").locator("textarea")).toHaveValue(comment);
  });

  const head = await as("demo.head_of_sales");

  await step(head, "The feedback is visible to management", async () => {
    await openMenu(head, SALES, "sol_commerce.menu_order_feedback");
    await search(head, journey.orderNumber, { field: "Resource name" });
    await expect(listed(head, journey.orderNumber)).toHaveCount(1);
    await openListed(head, journey.orderNumber);
    await expect(field(head, "feedback").locator("textarea")).toHaveValue(comment);
  });
});
