import { call, resolveRecord } from "../../../../support/odoo";

const NARROW = 1024;
const WIDE = 1600;

function openApp(menuId) {
  cy.visit(`/odoo?menu_id=${menuId}`);
  cy.get(".o_menu_sections").should("be.visible");
}

// Every section shown in the menu bar lies inside it; the ones that do not fit are in the "More" menu.
function expectSectionsFit() {
  return cy.get(".o_menu_sections").should(($menu) => {
    const bar = $menu[0].getBoundingClientRect();
    const shown = $menu.children(":not(.o_menu_sections_more)").filter(":visible").toArray();
    expect(shown, "sections shown in the menu bar").not.to.be.empty;
    for (const section of shown) {
      expect(section.getBoundingClientRect().right, section.textContent.trim()).to.be.at.most(bar.right + 1);
    }
  });
}

describe("Menu bar on a narrow window", () => {
  it("moves the Sales sections that do not fit into the More menu", () => {
    cy.viewport(NARROW, 800);
    cy.signInAs("sales");
    resolveRecord("sale.sale_menu_root").then(({ id }) => openApp(id));
    expectSectionsFit();
    cy.get(".o_menu_sections_more").should("be.visible").click();
    cy.get(".o-dropdown--menu .dropdown-item").should("have.length.greaterThan", 0);
  });

  it("keeps every app's sections inside the menu bar on a narrow and a wide window", () => {
    cy.signInAs("administrator");
    call("ir.ui.menu", "search_read", [[["parent_id", "=", false]]], { fields: ["id"] }).then((apps) => {
      expect(apps, "apps").not.to.be.empty;
      for (const width of [NARROW, WIDE]) {
        for (const app of apps) {
          cy.viewport(width, 800);
          openApp(app.id);
          cy.get(".o_menu_sections").then(($menu) => {
            if ($menu.children().length) {
              expectSectionsFit();
            }
          });
        }
      }
    });
  });
});
