// Field input on Odoo 20 forms and editable list rows, and list search.

// Opens a new record from a list, once Odoo has filled in its defaults; text typed before that is lost. The list is
// given by its path, or by a function that opens it, such as through its menu.
export function newRecord(list) {
  cy.intercept("POST", "/web/dataset/call_kw/*/onchange").as("defaults");
  if (typeof list === "function") {
    list();
  } else {
    cy.visit(list);
  }
  cy.get(".o_list_button_add").click();
  cy.wait("@defaults");
}

// Picks a many2one value in the edited form or list row. Odoo closes the suggestions on any scroll in the page,
// and a field still being drawn can lose them, so the arrow key opens them again with the typed text until they
// are shown.
export function pick(field, text) {
  const input = `.o_field_widget[name=${field}] input`;
  // Leave room for the form's sticky status bar above the field.
  cy.get(input).scrollIntoView({ offset: { top: -200, left: 0 } });
  cy.get(input).clear({ scrollBehavior: false }).type(text, { scrollBehavior: false });
  cy.get(input).should(($input) => {
    if (!Cypress.$(".o-autocomplete--dropdown-item").length) {
      $input[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    }
    expect(Cypress.$(".o-autocomplete--dropdown-item").text(), "suggestions").to.contain(text);
  });
  cy.contains(".o-autocomplete--dropdown-item a", text).click({ scrollBehavior: false });
}

// Picks a selection value in the edited form or list row by its label.
export function choose(field, label) {
  cy.get(`.o_field_widget[name=${field}] .o_select_menu_toggler`).click();
  cy.contains(".o_select_menu_item", label).click();
  cy.get(`.o_field_widget[name=${field}] .o_select_menu_toggler`).should("have.value", label);
}

// Filters the shown list by a search field, so a record past the first page is found too.
export function search(text, { grouped = false, field } = {}) {
  cy.get(".o_searchview_input").type(text);
  // Enter applies the first suggestion only once the suggestions are shown.
  cy.get(".o_searchview_autocomplete").should("contain", text);
  // Rows shown before the filtered list arrives still match the callers' row queries.
  cy.intercept("POST", `/web/dataset/call_kw/*/${grouped ? "web_read_group" : "web_search_read"}`).as("filtered");
  if (field) {
    cy.contains(".o_searchview_autocomplete .o-dropdown-item b", new RegExp(`^${Cypress._.escapeRegExp(field)}$`))
      .closest(".o-dropdown-item")
      .click();
  } else {
    cy.get(".o_searchview_input").type("{enter}");
  }
  cy.contains(".o_searchview_facet", text);
  cy.wait("@filtered");
}

// Opens a back-office menu as a user does: the app from the apps menu, then each section and entry of the menu bar,
// given by their external IDs, so it works in every language.
export function openMenu(app, ...entries) {
  // An entry with a link has opened once the address is its link; a section only opens its list of entries.
  const click = (selector) =>
    cy
      .get(selector)
      .first()
      .then(($menu) => {
        const href = $menu.attr("href");
        cy.wrap($menu, { log: false }).click();
        if (href && href !== "#") {
          cy.location("pathname").should((pathname) => {
            if (pathname !== href.split("?")[0]) expect(Cypress.$(".modal:visible"), "the menu action dialog").to.have.length.greaterThan(0);
          });
        }
      });
  cy.get(".o_navbar_apps_menu button").click();
  // The MediLab theme shows the apps as tiles of a panel; Odoo's own menu is a dropdown. An app opens its first
  // menu, whose address is not the app's link.
  cy.get(`.ml_apps_panel [data-menu-xmlid="${app}"], .o-dropdown--menu [data-menu-xmlid="${app}"]`).first().click();
  cy.get(`.o_main_navbar [data-menu-xmlid="${app}"]`).should("exist");
  for (const entry of entries) {
    click(`.o_main_navbar [data-menu-xmlid="${entry}"]:visible, .o-dropdown--menu [data-menu-xmlid="${entry}"]:visible`);
  }
  // A menu opens a view, or a dialog such as the label scan.
  return cy.get(".o_action_manager .o_view_controller:visible, .modal:visible").should("exist");
}

// Opens the record of the shown list whose row contains `text`, finding it with the search first.
export function openRow(text, options) {
  search(text, options);
  cy.contains(".o_data_row", text).find(".o_data_cell").first().click();
  return cy.get(".o_form_view").should("be.visible");
}

export function save() {
  cy.get(".o_form_button_save").click();
  cy.get(".o_form_button_save").should("not.be.visible");
}

export function openTab(name) {
  cy.get(`.o_notebook .nav-link[name=${name}]`).click();
}

// Saves the form and waits for the server's answer, so what follows reads or changes the saved record.
export function saveAndWait(model) {
  cy.intercept("POST", `/web/dataset/call_kw/${model}/web_save`).as("saved");
  save();
  cy.wait("@saved");
}

// Adds a line to an editable list field of the form and waits until it is edited.
export function addLine(field) {
  cy.get(`.o_field_widget[name=${field}] .o_field_x2many_list_row_add button`).click();
  cy.get(`.o_field_widget[name=${field}] .o_selected_row`).should("exist");
}

// Discards the form's unsaved changes, so leaving the page does not save them, and waits until the form has read the
// record again, which would otherwise drop a line added meanwhile.
export function discard() {
  cy.intercept("POST", "/web/dataset/call_kw/*/web_read").as("reread");
  cy.get(".o_form_button_cancel").click();
  cy.wait("@reread");
  cy.get(".o_form_button_save").should("not.be.visible");
}

// Closes the dialog that shows a refusal, then discards the changes it refused.
export function discardRefused() {
  cy.get(".o_error_dialog .btn-close").click();
  cy.get(".o_error_dialog").should("not.exist");
  discard();
}
