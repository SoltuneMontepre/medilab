import path from "node:path";
import { expect, handOver, journeyTag, step, test } from "../support/journey";
import { field, openMenu, openRow, settled, signIn } from "../support/odoo";
import { addToCart, cartButton, cartLine, follow, headerEntry, loads, openHeader, removeFromCart, send, signOut, userMenu } from "../support/portal";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const CUSTOMERS = ["sol_laboratory.menu_laboratory_customers", "sol_laboratory.menu_customer"];

const DEMO_PARAMETER = "Lead (Pb)";
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

  await step(customer, "The customer keeps their profile: customer code, tax code and portal language", async () => {
    await openHeader(customer, "/my/account");
    const details = customer.locator("main dl");
    await expect(details.locator("dd").nth(0)).toHaveText(/^KH\.\d+$/);
    await expect(details.locator("dd").nth(1)).toHaveText(taxCode);
    await expect(customer.locator("main input[name=parent_name]")).toHaveValue(customerName);
    const language = customer.locator("main form[action='/my/language'] select[name=lang]");
    await language.selectOption("en_US");
    await send(customer, "/my/language");
    await expect(language).toHaveValue("en_US");
    await expect(customer.locator(".o_medilab_language_switcher > a")).toContainText("English");
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

  await step(customer, "The customer opens the catalog, puts a parameter in the cart and takes it out again", async () => {
    await openHeader(customer, "/catalog");
    await expect(cartButton(customer)).toContainText("Cart (0)");
    await addToCart(customer, DEMO_PARAMETER);
    await expect(cartLine(customer, DEMO_PARAMETER)).toBeVisible();
    await expect(customer.locator("main select[name=contact_id] option[selected]")).toHaveText(contactName);
    await openHeader(customer, "/catalog");
    await expect(cartButton(customer)).toContainText("Cart (1)");
    await loads(customer, () => cartButton(customer).click());
    await removeFromCart(customer, DEMO_PARAMETER);
    await expect(customer.locator("main")).toContainText("The cart is empty.");
    await openHeader(customer, "/catalog");
    await expect(cartButton(customer)).toContainText("Cart (0)");
  });

  await step(customer, "The customer signs out and signs in again with the new login", async () => {
    await signOut(customer);
    await signIn(customer, customerLogin, customerPassword);
    await expect(customer).toHaveURL(/\/my$/);
    await expect(customer.locator("main")).toContainText(contactName);
    await expect(headerEntry(customer, "/catalog")).toBeVisible();
  });

  const sales = await as("demo.sales");

  await step(sales, "Sales finds the registered customer among the laboratory's customers", async () => {
    await openMenu(sales, LABORATORY, ...CUSTOMERS);
    await openRow(sales, customerName);
    await expect(field(sales, "name").locator("input")).toHaveValue(customerName);
    await expect(field(sales, "code").locator("input")).toHaveValue(/^KH\.\d+$/);
    await expect(field(sales, "vat").locator("input")).toHaveValue(taxCode);
    await expect(field(sales, "default_contact_id").locator("input")).toHaveValue(new RegExp(contactName));
    await expect(field(sales, "child_ids").locator(".o_data_row", { hasText: secondContactName })).toHaveCount(1);
    await expect(sales.locator(".o_form_view button[name=action_merge_duplicate]")).toHaveCount(0);
  });

  // Sales has no screen that shows a customer's sales terms; the Head of Sales, who sets them, has.
  const headOfSales = await as("demo.head_of_sales");

  await step(headOfSales, "The Head of Sales sees the customer has no sales terms, so no credit", async () => {
    await openMenu(headOfSales, LABORATORY, ...CUSTOMERS);
    await openRow(headOfSales, customerName);
    await headOfSales.locator("button.oe_stat_button:visible", { has: headOfSales.locator("[data-icon=handshake]") }).click();
    await settled(headOfSales);
    await expect(headOfSales.locator(".o_searchview_facet")).toContainText(customerName);
    await expect(headOfSales.locator(".o_list_view .o_data_row")).toHaveCount(0);
  });
});
