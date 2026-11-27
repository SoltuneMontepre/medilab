import { expect, handOver, received, step, test } from "../support/journey";
import { field, listed, openListed, openMenu, openRow, openTab, press, search, settled, status } from "../support/odoo";
import { loads, openHeader, openOrder } from "../support/portal";

const SALES = "sale.sale_menu_root";
const ORDERS = "sol_commerce.menu_sale_order";
const SUPPORT_REQUESTS = [SALES, "sol_commerce.menu_support_request"];
const MY_TASKS = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_mine"];

const RATING = 4;

test("SF-09 Customer support and feedback, support", async ({ as }) => {
  const journey = received("tag", "customerLogin", "customerPassword", "orderNumber", "salesName", "replacementReportNumber");
  const subject = `Report question ${journey.tag}`;
  const question = `Please confirm the report ${journey.replacementReportNumber} of order ${journey.orderNumber} is the one to file. ${journey.tag}`;
  const answer = `Yes, ${journey.replacementReportNumber} replaces the first report of ${journey.orderNumber} and is the one to file. ${journey.tag}`;
  const comment = `Clear report and fast service ${journey.tag}`;
  const support = {};

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const orderBadge = customer.locator("main h1 + span.badge");
  const feedbackForm = customer.locator("main form[action$='/feedback']");
  const supportBadge = customer.locator("main p", { hasText: "Status:" }).locator(".badge");
  const message = (page, text) => page.locator(".o-mail-Message-body", { hasText: text });

  await step(customer, "The customer opens the completed order, which offers help and feedback", async () => {
    await openOrder(customer, journey.orderNumber);
    await expect(orderBadge).toHaveText("Completed");
    await expect(customer.locator("main a[href^='/support/new?order_id=']")).toBeVisible();
    await expect(feedbackForm).toBeVisible();
  });

  await step(customer, "The customer opens a support request about the order", async () => {
    await loads(customer, () => customer.locator("main a[href^='/support/new?order_id=']").click());
    const form = customer.locator("main form[action='/support/open']");
    await expect(form.locator("select[name=order_id] option:checked")).toHaveText(journey.orderNumber);
    await form.locator("input[name=subject]").fill(subject);
    await form.locator("textarea[name=body]").fill(question);
    await loads(customer, () => form.locator("button[type=submit]").click());
    await expect(customer).toHaveURL(/\/support\/\d+$/);
    await expect(customer.locator("main h1")).toHaveText(new RegExp(`^HT\\.\\d+ ${subject}$`));
    support.code = (await customer.locator("main h1").innerText()).split(" ")[0];
    await expect(supportBadge).toHaveText("Open");
    await expect(customer.locator("main p", { hasText: "Order:" }).locator("a")).toHaveText(journey.orderNumber);
    await expect(customer.locator("main p", { hasText: "Handled by:" })).toHaveText(`Handled by: ${journey.salesName}`);
    await expect(message(customer, question)).toBeVisible();
    handOver("SF-09", { supportRequestCode: support.code, supportSubject: subject });
  });

  const sales = await as("demo.sales");

  await step(sales, "The order's salesperson finds the support request in My Tasks", async () => {
    await openMenu(sales, ...MY_TASKS);
    await search(sales, support.code);
    await expect(listed(sales, support.code)).toHaveCount(1);
    await openListed(sales, support.code);
    await expect(field(sales, "code").locator("input")).toHaveValue(support.code);
    await expect(status(sales)).toHaveAttribute("data-value", "open");
    await expect(field(sales, "handled_by_id")).toHaveText(journey.salesName);
    await expect(field(sales, "order_id").locator("input")).toHaveValue(journey.orderNumber);
    await expect(message(sales, question)).toBeVisible();
  });

  await step(sales, "The salesperson answers; the request reads answered and leaves the to-do list", async () => {
    // The chatter opens on Send message, which the customer follows.
    await expect(sales.locator(".o-mail-Chatter-sendMessage")).toHaveClass(/active/);
    const composer = sales.locator(".o-mail-Chatter .o-mail-Composer-input");
    await composer.fill(answer);
    await sales.locator(".o-mail-Chatter .o-mail-Composer-send").click();
    await settled(sales);
    await expect(message(sales, answer)).toBeVisible();
    await openMenu(sales, ...MY_TASKS);
    await search(sales, support.code);
    await expect(listed(sales, support.code)).toHaveCount(0);
    // The open form keeps showing Open after the answer; the request reads answered once it is opened again.
    await openMenu(sales, ...SUPPORT_REQUESTS);
    await search(sales, support.code);
    await expect(listed(sales, support.code).locator("td[name=status]")).toHaveText(/\S/);
    await openListed(sales, support.code);
    await expect(status(sales)).toHaveAttribute("data-value", "answered");
  });

  await step(customer, "The customer reads the answer on the portal", async () => {
    await openHeader(customer, "/support");
    const row = customer.locator("main tbody tr", { hasText: support.code });
    await expect(row.locator(".badge")).toHaveText("Answered");
    await loads(customer, () => row.locator(`a`, { hasText: support.code }).click());
    await expect(supportBadge).toHaveText("Answered");
    await expect(message(customer, answer)).toBeVisible();
  });

  // business-flows.md SF-09 closes the request after the customer reads the answer without naming who closes it.
  await step(customer, "The customer's page has no way to close the request", async () => {
    await expect(customer.locator("main").getByRole("button", { name: "Close" })).toHaveCount(0);
    await expect(customer.locator("main form[action*='/close']")).toHaveCount(0);
  });

  await step(sales, "Sales closes the answered request", async () => {
    await openMenu(sales, ...SUPPORT_REQUESTS);
    await openRow(sales, support.code);
    await expect(status(sales)).toHaveAttribute("data-value", "answered");
    await expect(message(sales, answer)).toBeVisible();
    await press(sales, "action_close");
    await expect(status(sales)).toHaveAttribute("data-value", "closed");
    await expect(field(sales, "closed_at")).toHaveText(/\d/);
    await expect(sales.locator("button[name=action_close]:visible")).toHaveCount(0);
  });

  await step(customer, "The customer sees the request closed", async () => {
    await openHeader(customer, "/support");
    const row = customer.locator("main tbody tr", { hasText: support.code });
    await loads(customer, () => row.locator(`a`, { hasText: support.code }).click());
    await expect(supportBadge).toHaveText("Closed");
    await expect(customer.locator("main .alert")).toContainText("This request is closed.");
    handOver("SF-09", { supportRequestStatus: (await supportBadge.innerText()).trim() });
  });

  await step(customer, "SF-09-A4: The customer rates the completed order with a comment", async () => {
    await openOrder(customer, journey.orderNumber);
    await feedbackForm.locator(`#rating-${RATING}`).check();
    await feedbackForm.locator("textarea[name=comment]").fill(comment);
    await loads(customer, () => feedbackForm.locator("button[type=submit]").click());
    await expect(customer.locator("main p", { hasText: "Your rating:" })).toHaveText(`Your rating: ${RATING}/5`);
    await expect(customer.locator("main")).toContainText(comment);
    await expect(customer.locator("main li", { hasText: support.code }).locator(".badge")).toHaveText("Closed");
    handOver("SF-09", { rating: RATING, feedbackComment: comment });
  });

  await step(customer, "SF-09-A4: A second rating of the order is not offered", async () => {
    await expect(feedbackForm).toHaveCount(0);
    await openOrder(customer, journey.orderNumber);
    await expect(feedbackForm).toHaveCount(0);
    await expect(customer.locator("main p", { hasText: "Your rating:" })).toHaveText(`Your rating: ${RATING}/5`);
  });

  await step(sales, "Sales sees the rating and the closed support request on the order", async () => {
    await openMenu(sales, SALES, ORDERS);
    await openRow(sales, journey.orderNumber);
    await openTab(sales, "feedback");
    await expect(field(sales, "feedback_rating").locator("input")).toHaveValue(String(RATING));
    await expect(field(sales, "feedback_comment").locator("textarea")).toHaveValue(comment);
    await openTab(sales, "support");
    const row = field(sales, "support_request_ids").locator(".o_data_row", { hasText: support.code });
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=status]")).toHaveText(/\S/);
    await expect(row.locator("td[name=handled_by_id]")).toHaveText(journey.salesName);
  });

  const head = await as("demo.head_of_sales");

  await step(head, "The Head of Sales finds the order's feedback", async () => {
    await openMenu(head, SALES, "sol_commerce.menu_order_feedback");
    await search(head, journey.orderNumber, { field: "Resource name" });
    await expect(listed(head, journey.orderNumber)).toHaveCount(1);
    await openListed(head, journey.orderNumber);
    await expect(field(head, "feedback").locator("textarea")).toHaveValue(comment);
  });
});
