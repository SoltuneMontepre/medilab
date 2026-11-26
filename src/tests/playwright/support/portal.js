// What a visitor or a customer does on the portal: follow its links, send its forms, fill the cart and sign out.

import { expect } from "@playwright/test";
import { settled } from "./odoo";

const HEADER = "ul.o_medilab_portal_navigation";

// The text as a pattern that matches a cell holding exactly it.
function exactly(text) {
  return new RegExp(`^\\s*${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$`);
}

// Does what leads to another page, a link or a form's button, and waits until that page shows.
export async function loads(page, action) {
  await Promise.all([page.waitForEvent("load"), action()]);
  await settled(page);
}

// The header's entry that leads to `href`, such as /catalog, /orders, /support or /my/account.
export function headerEntry(page, href) {
  return page.locator(`${HEADER} a[href="${href}"]`);
}

export async function openHeader(page, href) {
  await loads(page, () => headerEntry(page, href).click());
  await expect(headerEntry(page, href)).toHaveAttribute("aria-current", "page");
}

// Follows a link of the page's content by the address it leads to.
export async function follow(page, href) {
  await loads(page, () => page.locator(`main a[href="${href}"]`).first().click());
}

// Sends the page's form that posts to `action` with its own button.
export async function send(page, action) {
  await loads(page, () => page.locator(`main form[action="${action}"] button[type=submit]`).first().click());
}

// The catalog's button to the cart, which counts what the cart holds.
export function cartButton(page) {
  return page.locator("main a.btn[href='/cart']");
}

// Adds a parameter or package of the catalog to the cart, which shows next.
export async function addToCart(page, name, quantity = 1) {
  const product = page.locator("main tbody tr", { has: page.locator("td:first-child", { hasText: exactly(name) }) });
  await product.locator("input[name=quantity]").fill(String(quantity));
  await loads(page, () => product.locator("form[action='/catalog/add'] button[type=submit]").click());
  await expect(page).toHaveURL(/\/cart$/);
}

// The cart's line of a parameter or package.
export function cartLine(page, name) {
  return page.locator("main tbody tr", { has: page.locator("td:first-child", { hasText: exactly(name) }) });
}

// The cart's row under a line, where its sample type and way of testing are chosen.
export function cartChoices(page, name) {
  return cartLine(page, name).locator("xpath=following-sibling::tr[1]");
}

export async function removeFromCart(page, name) {
  await loads(page, () => cartLine(page, name).locator("button[name=quantity][value='0']").click());
  await expect(cartLine(page, name)).toHaveCount(0);
}

// Opens the customer's order from My orders, found by its number.
export async function openOrder(page, number) {
  await openHeader(page, "/orders");
  await page.locator("main form[action='/orders'] input[name=search]").fill(number);
  await send(page, "/orders");
  await loads(page, () => page.locator("main tbody a", { hasText: exactly(number) }).click());
  await expect(page.locator("main h1")).toHaveText(number);
}

// What a page's list of details says under `label`, such as Requested date on an order or a quotation.
export function detail(page, label) {
  return page.locator("main dl div", { has: page.locator("dt", { hasText: exactly(label) }) }).locator("dd");
}

// The header's menu of the signed-in user.
export function userMenu(page) {
  return page.locator("#top_menu li.dropdown:has(.js_usermenu) > a.dropdown-toggle");
}

// Opens My account from the user menu: the page of cards that lead to the customer's invoices and test reports.
export async function openMyAccount(page) {
  const entry = page.locator(".js_usermenu a[href='/my/home']");
  // The header's menus answer once the page's scripts have started, which is after the page shows.
  await expect(async () => {
    if (!(await entry.isVisible())) await userMenu(page).click();
    await expect(entry).toBeVisible({ timeout: 1000 });
  }).toPass();
  await loads(page, () => entry.click());
  await expect(page).toHaveURL(/\/my\/home$/);
}

export async function signOut(page) {
  const logout = page.locator("#o_logout");
  // The header's menus answer once the page's scripts have started, which is after the page shows.
  await expect(async () => {
    if (!(await logout.isVisible())) await userMenu(page).click();
    await expect(logout).toBeVisible({ timeout: 1000 });
  }).toPass();
  await loads(page, () => logout.click());
  await expect(page).toHaveURL(/\/web\/login/);
}
