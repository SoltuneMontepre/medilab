// What a person does on Odoo 20 screens: sign in, open menus, search lists, fill forms and press buttons.

import { expect } from "@playwright/test";

const pending = new WeakMap();

// Counts the page's open requests, so a step waits until the screen has its data.
export function watch(page) {
  const open = new Set();
  pending.set(page, open);
  const tracked = (request) => ["xhr", "fetch"].includes(request.resourceType()) && !request.url().includes("/websocket");
  page.on("request", (request) => tracked(request) && open.add(request));
  page.on("requestfinished", (request) => open.delete(request));
  page.on("requestfailed", (request) => open.delete(request));
}

// Waits until the page has answered every request and shows no loading state. A refusal the step did not expect
// fails it with the message on screen.
export async function settled(page, { refusals = false } = {}) {
  const open = pending.get(page);
  let quiet = 0;
  const deadline = Date.now() + 30000;
  while (quiet < 3) {
    if (Date.now() > deadline) throw new Error("The page did not settle within 30 seconds.");
    await page.waitForTimeout(100);
    const busy = (open && open.size > 0) || (await page.locator(".o_blockUI, .o_loading_indicator, .o_view_sample_data.o_loading").count()) > 0;
    quiet = busy ? 0 : quiet + 1;
  }
  if (!refusals) {
    const error = page.locator(".o_error_dialog");
    if (await error.count()) throw new Error(`Odoo refused: ${(await error.first().innerText()).trim()}`);
  }
}

export async function signIn(page, login, password) {
  await page.goto("/web/login");
  await page.locator("input[name=login]").fill(login);
  await page.locator("input[name=password]").fill(password);
  await page.locator("form.oe_login_form button[type=submit]").click();
  await expect(page).not.toHaveURL(/\/web\/login/);
  await settled(page);
}

// The dialog on top, or the page when none is open: what the person is looking at.
export function front(page) {
  return page.locator(".modal:visible").last().or(page.locator(".o_action_manager")).first();
}

function scope(page, within) {
  return within ?? page.locator(".modal:visible .o_form_view, .modal:visible .o_list_view").last().or(page.locator(".o_action_manager")).first();
}

// Opens a back-office menu as a person does: the app from the apps menu, then each section and entry of the menu
// bar, by their external IDs, which stay the same in every language.
export async function openMenu(page, app, ...entries) {
  await page.locator(".o_navbar_apps_menu button").click();
  await page.locator(`.ml_apps_panel [data-menu-xmlid="${app}"], .o-dropdown--menu [data-menu-xmlid="${app}"]`).first().click();
  await expect(page.locator(`.o_main_navbar [data-menu-xmlid="${app}"]`).first()).toBeAttached();
  await settled(page);
  for (const entry of entries) {
    const item = page.locator(`.o_main_navbar [data-menu-xmlid="${entry}"]:visible, .o-dropdown--menu [data-menu-xmlid="${entry}"]:visible`).first();
    if (!(await item.count())) {
      // A narrow menu bar keeps the sections that do not fit under More.
      const more = page.locator(".o_main_navbar .o_menu_sections_more button, .o_main_navbar .o_menu_sections .o-dropdown.o_menu_sections_more");
      if (await more.count()) await more.first().click();
    }
    await item.click();
    await settled(page);
  }
  await expect(page.locator(".o_action_manager .o_view_controller:visible, .modal:visible").first()).toBeVisible();
}

// Filters the shown list as a person types in its search box, by the first suggestion or the one labelled `field`.
export async function search(page, text, { field } = {}) {
  const input = page.locator(".o_searchview_input:visible").last();
  await input.click();
  await input.pressSequentially(text, { delay: 20 });
  const suggestions = page.locator(".o_searchview_autocomplete");
  await expect(suggestions).toContainText(text);
  if (field) {
    await suggestions.locator(".o-dropdown-item", { has: page.locator("b", { hasText: new RegExp(`^${field}$`) }) }).first().click();
  } else {
    await input.press("Enter");
  }
  await settled(page);
}

// Removes the filters of the shown list, so a search looks in every record.
export async function clearSearch(page) {
  const facets = page.locator(".o_searchview_facet .o_facet_remove:visible");
  while (await facets.count()) {
    await facets.first().click();
    await settled(page);
  }
}

// Opens the record of the shown list whose row contains `text`, after searching for it.
export async function openRow(page, text, options) {
  await search(page, text, options);
  await page.locator(".o_data_row", { hasText: text }).first().locator(".o_data_cell").first().click();
  await expect(page.locator(".o_form_view:visible").last()).toBeVisible();
  await settled(page);
}

export async function newRecord(page) {
  await page.locator(".o_list_button_add:visible, .o-kanban-button-new:visible, .o_form_button_create:visible").first().click();
  await expect(page.locator(".o_form_view:visible").last()).toBeVisible();
  await settled(page);
}

export function field(page, name, within) {
  return scope(page, within).locator(`.o_field_widget[name="${name}"]`).first();
}

// Types into a text, number or date field.
export async function type(page, name, value, within) {
  const input = field(page, name, within).locator("input:not([type=hidden]), textarea").first();
  await input.scrollIntoViewIfNeeded();
  await input.fill(String(value));
  await input.press("Tab");
  await settled(page);
}

// Picks a many2one value: types the text and clicks the suggestion that contains it.
export async function pick(page, name, text, within) {
  const input = field(page, name, within).locator("input").first();
  await input.scrollIntoViewIfNeeded();
  await input.fill("");
  await input.pressSequentially(text, { delay: 20 });
  const option = page.locator(".o-autocomplete--dropdown-item:visible a", { hasText: text }).first();
  await expect(option).toBeVisible();
  await option.click();
  await settled(page);
}

// Chooses a selection value by its label, in a select menu, a native select or radio buttons.
export async function choose(page, name, label, within) {
  const widget = field(page, name, within);
  await widget.scrollIntoViewIfNeeded();
  if (await widget.locator("select").count()) {
    await widget.locator("select").selectOption({ label });
  } else if (await widget.locator(".o_radio_item").count()) {
    await widget.locator(".o_radio_item", { hasText: label }).locator("input").check();
  } else {
    await widget.locator(".o_select_menu_toggler, input").first().click();
    await page.locator(".o_select_menu_item:visible, .o-autocomplete--dropdown-item:visible", { hasText: label }).first().click();
  }
  await settled(page);
}

export async function tick(page, name, checked = true, within) {
  await field(page, name, within).locator("input[type=checkbox]").setChecked(checked);
  await settled(page);
}

export async function openTab(page, name) {
  await page.locator(`.o_notebook .nav-link[name="${name}"]:visible`).last().click();
  await settled(page);
}

// Adds a line to an editable list field of the form.
export async function addLine(page, name, within) {
  const list = field(page, name, within);
  await list.locator(".o_field_x2many_list_row_add a, .o_field_x2many_list_row_add button").first().click();
  await expect(list.locator(".o_selected_row")).toBeVisible();
  await settled(page);
  return list.locator(".o_selected_row");
}

export async function save(page) {
  const button = page.locator(".o_form_button_save:visible").last();
  if (await button.count()) await button.click();
  await settled(page);
  await expect(page.locator(".o_form_button_save:visible")).toHaveCount(0);
}

// Presses a button of the form, its status bar or the dialog on top, by its `name` attribute.
export async function press(page, name, { refusals = false, within } = {}) {
  const button = (within ?? page).locator(`button[name="${name}"]:visible, a[name="${name}"]:visible`).last();
  await expect(button).toBeEnabled();
  await button.click();
  await settled(page, { refusals });
}

// Presses a button by the words on it.
export async function pressLabel(page, label, { refusals = false, within } = {}) {
  await (within ?? page).getByRole("button", { name: label, exact: true }).last().click();
  await settled(page, { refusals });
}

// The status the form's status bar marks as current.
export function status(page) {
  return page.locator(".o_form_view:visible .o_statusbar_status .o_arrow_button_current, .o_form_view:visible .o_statusbar_status [aria-current=true]").last();
}

// Opens the user menu and signs out.
export async function signOut(page) {
  await page.locator(".o_user_menu button").click();
  await page.locator("[data-menu=logout]").click();
  await expect(page).toHaveURL(/\/web\/login|\/$/);
}
