import { signIn } from "../support/session";

const CONTAINER = "K55012345-01";

// Moves a container of the central store to another of its locations through the Move Stock dialog.
function moveContainer(destination, reason) {
  cy.visit("/odoo/move-stock");
  cy.get(".modal [name=container_scan] input").type(CONTAINER).blur();
  cy.get(".modal [name=container_id] input").should("have.value", CONTAINER);
  cy.get(".modal [name=location_dest_id] input").type(destination);
  cy.contains(".o-autocomplete--dropdown-item", destination).click();
  cy.get(".modal [name=reason] input").type(reason);
  cy.get(".modal button[name=action_confirm]").click();
  cy.get(".modal").should("not.exist");
}

describe("Stock moves, disposal and value", () => {
  beforeEach(() => {
    signIn("demo.storekeeper");
  });

  it("moves a container to another room of the central store and back", () => {
    const reason = `Browser test ${Date.now()}`;
    moveContainer("Room 102", reason);
    moveContainer("WH/Central store", `${reason} back`);

    cy.visit("/odoo/stock-moves");
    cy.get(".o_searchview_input").type(reason);
    cy.contains(".o_searchview_autocomplete .o-dropdown-item", /Reason|Lý do/).click();
    cy.get(".o_group_header").click();
    cy.get(".o_data_row").should("have.length", 2);
    cy.contains(".o_data_row", `${reason} back`).should("contain", "Room 102");
  });

  it("disposes of the expired sodium chloride bottle", () => {
    cy.visit("/odoo/disposal");
    cy.get(".o_group_header").click();
    cy.contains(".o_data_row", "NaCl-2509").find(".o_list_record_selector input").check();
    cy.get("button[name=action_dispose]").click();
    cy.get(".modal-footer .btn-primary").click();
    cy.contains(".o_data_row", "NaCl-2509").should("not.exist");
  });

  it("shows the stock on hand with its value", () => {
    cy.visit("/odoo/stock-on-hand");
    cy.get("th[data-name=value]").should("exist");
    cy.get(".o_group_header").should("have.length.at.least", 1);
  });
});
