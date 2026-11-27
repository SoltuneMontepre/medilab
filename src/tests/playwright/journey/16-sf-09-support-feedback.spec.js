import { expect, handOver, outside, received, step, test } from "../support/journey";
import { field, listed, openListed, openMenu, search, settled, status } from "../support/odoo";
import { loads, openHeader, openOrder } from "../support/portal";

const MY_TASKS = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_mine"];

test("SF-09 Customer support and feedback, support", async ({ as }) => {
  const journey = received("tag", "customerLogin", "customerPassword", "orderNumber", "salesLogin", "salesName");
  const subject = `Order question ${journey.tag}`;
  const question = `Please confirm which report of order ${journey.orderNumber} we should file. ${journey.tag}`;
  const answer = `The latest report issued for ${journey.orderNumber} is the one to file. ${journey.tag}`;
  const support = {};

  const customer = await as(journey.customerLogin, journey.customerPassword);
  const supportBadge = customer.locator("main p", { hasText: "Status:" }).locator(".badge");
  const message = (page, text) => page.locator(".o-mail-Message-body", { hasText: text });

  await step(customer, "The customer opens a support request about the order", async () => {
    await openOrder(customer, journey.orderNumber);
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

  const sales = await as(journey.salesLogin);

  await step(sales, "The order's salesperson finds the support request in their to-do list", async () => {
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

  await step(sales, "The order's salesperson answers", async () => {
    // The chatter opens on Send message, which the customer follows.
    await expect(sales.locator(".o-mail-Chatter-sendMessage")).toHaveClass(/active/);
    await sales.locator(".o-mail-Chatter .o-mail-Composer-input").fill(answer);
    await sales.locator(".o-mail-Chatter .o-mail-Composer-send").click();
    await settled(sales);
    await expect(message(sales, answer)).toBeVisible();
  });

  await outside("The customer is notified of the answer", "e-mail");

  await step(customer, "The customer reads the answer on the portal; the request is answered", async () => {
    await openHeader(customer, "/support");
    const row = customer.locator("main tbody tr", { hasText: support.code });
    await expect(row.locator(".badge")).toHaveText("Answered");
    await loads(customer, () => row.locator("a", { hasText: support.code }).click());
    await expect(supportBadge).toHaveText("Answered");
    await expect(message(customer, answer)).toBeVisible();
    handOver("SF-09", { supportRequestStatus: (await supportBadge.innerText()).trim() });
  });
});
