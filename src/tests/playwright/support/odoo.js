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

// The dialog on top, or the page when none is open: what the person is looking at. Dialogs come after the page in
// the document, the one on top last.
export function front(page) {
  return page.locator(".modal:visible").or(page.locator(".o_action_manager")).last();
}

function scope(page, within) {
  return within ?? front(page);
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
  // An app's own page, such as the Tasks dashboard, is an action without a view.
  await expect(page.locator(".o_action_manager .o_view_controller:visible, .o_action_manager .o_action:visible, .modal:visible").first()).toBeVisible();
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

// The rows of the shown list that contain `text`.
export function listed(page, text) {
  return front(page).locator(".o_data_row", { hasText: text });
}

// Opens the record of the shown list whose row contains `text`.
export async function openListed(page, text) {
  await listed(page, text).first().locator(".o_data_cell").first().click();
  await expect(page.locator(".o_form_view:visible").last()).toBeVisible();
  await settled(page);
}

// Opens the record of the shown list whose row contains `text`, after searching for it.
export async function openRow(page, text, options) {
  await search(page, text, options);
  await openListed(page, text);
}

export async function newRecord(page) {
  await page.locator(".o_list_button_add:visible, .o-kanban-button-new:visible, .o_form_button_create:visible").first().click();
  await expect(page.locator(".o_form_view:visible").last()).toBeVisible();
  await settled(page);
}

// The text as a pattern that matches it letter for letter.
function literal(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function field(page, name, within) {
  return scope(page, within).locator(`.o_field_widget[name="${name}"]`).first();
}

// The full day or time a date field of a form shows, which the field itself abbreviates.
export function shownDay(page, name, within) {
  return field(page, name, within).locator("[data-tooltip]").first();
}

// Types into a text or number field. Leaving the field takes the value; Tab would add a line after the last cell
// of an editable list.
export async function type(page, name, value, within) {
  const input = field(page, name, within).locator("input:not([type=hidden]), textarea").first();
  await input.scrollIntoViewIfNeeded();
  await input.fill(String(value));
  await input.blur();
  await settled(page);
}

// The laboratory's calendar day, `days` and `years` from today.
export function labDay({ days = 0, years = 0 } = {}) {
  const [year, month, day] = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date()).split("-").map(Number);
  return new Date(Date.UTC(year + years, month - 1, day + days));
}

// The day as `pattern` writes it, such as mm/dd/yyyy.
export function written(date, pattern) {
  const parts = { yyyy: date.getUTCFullYear(), mm: String(date.getUTCMonth() + 1).padStart(2, "0"), dd: String(date.getUTCDate()).padStart(2, "0") };
  return pattern.toLowerCase().replace(/yyyy|mm|dd/g, (part) => parts[part]);
}

// The day a text written as `pattern` names, such as 03/12/2026 as dd/mm/yyyy.
export function dated(text, pattern) {
  const order = pattern.toLowerCase().match(/yyyy|mm|dd/g);
  const numbers = text.match(/\d+/g).map(Number);
  const part = (name) => numbers[order.indexOf(name)];
  return new Date(Date.UTC(part("yyyy"), part("mm") - 1, part("dd")));
}

// The whole đồng of an amount as a screen writes it, such as 151.800 ₫.
export function money(text) {
  return Number(text.replace(/\D/g, ""));
}

// Types a day into a date field, in the format the field asks for in the user's language. Returns it as typed.
export async function typeDate(page, name, date, within) {
  const widget = field(page, name, within);
  await widget.scrollIntoViewIfNeeded();
  // A day already set shows as a button until it is clicked.
  await widget.locator("input, button").first().click();
  const input = widget.locator("input").first();
  await expect(input).toHaveAttribute("placeholder", /yyyy/i);
  const text = written(date, await input.getAttribute("placeholder"));
  await input.fill(text);
  await input.blur();
  await settled(page);
  return text;
}

// Types the text into a many2one or tag field and returns the records it suggests, without the suggestions that
// create a record.
export async function suggested(page, name, text, within) {
  const input = field(page, name, within).locator("input").first();
  await input.scrollIntoViewIfNeeded();
  await input.fill("");
  // The field asks for its suggestions a moment after the last letter.
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("name_search")),
    input.pressSequentially(text, { delay: 20 }),
  ]);
  await settled(page);
  await expect(page.locator(".o-autocomplete--dropdown-menu:visible")).toBeVisible();
  return page.locator(".o-autocomplete--dropdown-item:visible:not(.o_m2o_dropdown_option) a");
}

// Picks a many2one or tag value: types the text and clicks the record suggested under exactly that name, or else
// the first one that contains it.
export async function pick(page, name, text, within) {
  const records = await suggested(page, name, text, within);
  await expect(records.filter({ hasText: text }).first()).toBeVisible();
  const exact = records.filter({ hasText: new RegExp(`^\\s*${literal(text)}\\s*$`) });
  await ((await exact.count()) ? exact : records.filter({ hasText: text })).first().click();
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

// Adds a line to a list that is edited in place and returns it.
export async function addRow(page) {
  await page.locator(".o_list_button_add:visible").first().click();
  const row = page.locator(".o_list_view:visible .o_selected_row").last();
  await expect(row).toBeVisible();
  await settled(page);
  return row;
}

// Saves the form, or the line being edited in a list. A field the screen marks as invalid fails the step with its
// message.
export async function save(page) {
  const buttons = page.locator(".o_form_button_save:visible, .o_list_button_save:visible");
  if (await buttons.count()) await buttons.last().click();
  await settled(page);
  const invalid = page.locator(".o_notification:visible", { has: page.locator(".o_notification_bar.bg-danger, .text-danger") });
  if ((await buttons.count()) && (await invalid.count())) throw new Error(`Odoo did not save: ${(await invalid.first().innerText()).trim()}`);
  await expect(buttons).toHaveCount(0);
}

// Leaves the form without saving what was changed on it.
export async function discard(page) {
  await page.locator(".o_form_button_cancel:visible").last().click();
  await settled(page);
  await expect(page.locator(".o_form_button_save:visible")).toHaveCount(0);
}

// Closes the dialog on top with its cross.
export async function closeDialog(page) {
  const dialogs = page.locator(".modal:visible");
  const open = await dialogs.count();
  await dialogs.last().locator(".btn-close").click();
  await expect(dialogs).toHaveCount(open - 1);
  await settled(page);
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

// Shows the records of the open screen as a list, on a screen that opens as a calendar.
export async function showList(page) {
  await page.locator(".o_switch_view.o_list:visible").click();
  await expect(page.locator(".o_list_view:visible")).toBeVisible();
  await settled(page);
}

// Opens or closes the messaging menu of the menu bar.
export async function toggleMessages(page) {
  await page.locator(".o_menu_systray .o-mail-DiscussSystray-class").click();
}

// The messaging menu's tab of the notices a person receives in the application; people notified by e-mail have none.
export function noticesTab(page) {
  return page.locator(".o-mail-MessagingMenuInDropdown .o-mail-MessagingMenu-tab[data-id=notification]");
}

// Opens the messaging menu on the notices the signed-in person received in the application. The menu reads them
// once: a notice sent after that shows when the page is loaded again.
export async function openNotices(page) {
  await toggleMessages(page);
  await noticesTab(page).click();
  await settled(page);
  return page.locator(".o-mail-MessagingMenuInDropdown .o-mail-NotificationItem");
}

// Chooses, in the user's preferences, to be notified in the application instead of by e-mail.
export async function receiveNoticesInApplication(page) {
  await page.locator(".o_user_menu").click();
  await page.locator(".o-dropdown--menu [data-menu=preferences]").click();
  await settled(page);
  const preferences = front(page);
  const inApplication = field(page, "notification_type").locator(".o_radio_item", { hasText: "In Odoo" }).locator("input");
  if (await inApplication.isChecked()) {
    await pressLabel(page, "Discard", { within: preferences });
  } else {
    await inApplication.check();
    // Saving the preferences loads the page again.
    await Promise.all([page.waitForEvent("load"), preferences.locator("button[name=preference_save]").click()]);
    await settled(page);
  }
  await toggleMessages(page);
  await expect(noticesTab(page)).toBeVisible();
  await toggleMessages(page);
}

// Opens the user menu and signs out.
export async function signOut(page) {
  await page.locator(".o_user_menu button").click();
  await page.locator("[data-menu=logout]").click();
  await expect(page).toHaveURL(/\/web\/login|\/$/);
}
