import path from "node:path";
import { expect, handOver, journeyTag, step, test } from "../support/journey";
import { follow, headerEntry, loads, openHeader, send, userMenu } from "../support/portal";

const LOGO = path.join(__dirname, "..", "fixtures", "journey-logo.png");

test("SF-09 Customer support and feedback, account", async ({ as }) => {
  const tag = journeyTag();
  const customerName = `Journey Foods ${tag}`;
  const contactName = `Journey Buyer ${tag}`;
  const secondContactName = `Journey QA ${tag}`;
  const customerLogin = `journey.${tag.toLowerCase()}@example.com`;
  const customerPassword = `Journey-${tag}!`;
  // A tax code another customer holds would flag the new account as a possible duplicate.
  const taxCode = `09${tag.replace(/\D/g, "").slice(-8)}`;

  const customer = await as.visitor("customer");
  const contactRow = (name) => customer.locator("main tbody tr", { hasText: name });

  await step(customer, "A visitor opens the portal and reaches the sign-up form", async () => {
    await customer.goto("/");
    await expect(customer).toHaveURL(/\/web\/login/);
    await loads(customer, () => customer.locator("a[href^='/web/signup']").click());
    await expect(customer.locator("form.oe_signup_form select[name=customer_type]")).toBeVisible();
  });

  await step(customer, "The customer registers as a business and is signed in", async () => {
    const form = customer.locator("form.oe_signup_form");
    await form.locator("input[name=name]").fill(contactName);
    await form.locator("input[name=login]").fill(customerLogin);
    await form.locator("select[name=customer_type]").selectOption("business");
    await form.locator("input[name=company_name]").fill(customerName);
    await form.locator("input[name=vat]").fill(taxCode);
    await form.locator("input[name=phone]").fill("028 3999 2026");
    await form.locator("input[name=street]").fill("12 Nguyen Hue");
    await form.locator("input[name=city]").fill("Ho Chi Minh");
    await form.locator("input[name=password]").fill(customerPassword);
    await form.locator("input[name=confirm_password]").fill(customerPassword);
    await loads(customer, () => form.locator("button[type=submit]").click());
    await expect(customer).toHaveURL(/\/my$/);
    await expect(userMenu(customer)).toBeVisible();
    for (const href of ["/catalog", "/orders", "/support", "/my/account"]) await expect(headerEntry(customer, href)).toBeVisible();
    await expect(customer.locator("main")).toContainText(contactName);
    await expect(customer.locator("main")).toContainText(customerName);
    handOver("SF-09", { customerName, customerLogin, customerPassword, contactName });
  });

  await step(customer, "The customer keeps their profile: customer code, tax code and language", async () => {
    await openHeader(customer, "/my/account");
    const details = customer.locator("main dl");
    await expect(details.locator("dd").nth(0)).toHaveText(/^KH\.\d+$/);
    await expect(details.locator("dd").nth(1)).toHaveText(taxCode);
    await expect(customer.locator("main input[name=parent_name]")).toHaveValue(customerName);
    await expect(customer.locator("main form[action='/my/language'] select[name=lang]")).toHaveValue("en_US");
    handOver("SF-09", { customerCode: (await details.locator("dd").nth(0).innerText()).trim(), customerTaxCode: taxCode });
  });

  await step(customer, "The customer keeps their contacts: the default contact and a second person", async () => {
    await follow(customer, "/my/contacts");
    await expect(contactRow(contactName).locator(".badge")).toHaveText("Default");
    await follow(customer, "/my/contacts/new");
    const form = customer.locator("main form[action='/my/contacts/save']");
    await form.locator("input[name=name]").fill(secondContactName);
    await form.locator("input[name=function]").fill("Quality manager");
    await form.locator("input[name=email]").fill(`journey.qa.${tag.toLowerCase()}@example.com`);
    await form.locator("input[name=phone]").fill("028 3999 2027");
    await send(customer, "/my/contacts/save");
    await expect(customer).toHaveURL(/\/my\/contacts$/);
    await expect(contactRow(secondContactName)).toContainText("Quality manager");
    await expect(contactRow(secondContactName).locator(".badge")).toHaveCount(0);
    await expect(contactRow(contactName).locator(".badge")).toHaveText("Default");
  });

  await step(customer, "The customer uploads a logo", async () => {
    await openHeader(customer, "/my/account");
    await expect(customer.locator("main img[alt=Logo]")).toHaveCount(0);
    await customer.locator("main form[action='/my/logo'] input[name=logo]").setInputFiles(LOGO);
    await send(customer, "/my/logo");
    await expect(customer.locator("main .alert-danger")).toHaveCount(0);
    await expect(customer.locator("main img[alt=Logo]")).toBeVisible();
  });
});
