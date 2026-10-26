// Field input on Odoo 20 forms and editable list rows, and list search.

// Opens a new record from a list, once Odoo has filled in its defaults; text typed before that is lost.
export function newRecord(path) {
  cy.intercept("POST", "/web/dataset/call_kw/*/onchange").as("defaults");
  cy.visit(path);
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

// Filters the shown list by the first field of its search view, so a record past the first page is found too.
export function search(text) {
  cy.get(".o_searchview_input").type(`${text}{enter}`);
}

export function save() {
  cy.get(".o_form_button_save").click();
  cy.get(".o_form_button_save").should("not.be.visible");
}

export function openTab(name) {
  cy.get(`.o_notebook .nav-link[name=${name}]`).click();
}
