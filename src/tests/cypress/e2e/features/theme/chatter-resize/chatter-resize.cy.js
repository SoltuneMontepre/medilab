import { call } from "../../../../support/odoo";

const STORAGE_KEY = "sol_theme.chatter";
const DRAG = 120;

const panelWidth = () => cy.get(".o-mail-ChatterPanel").then(($panel) => $panel[0].getBoundingClientRect().width);

describe("Resizable chatter", () => {
  beforeEach(() => {
    // The chatter sits beside the form from 1,400 px wide.
    cy.viewport(1600, 900);
    cy.signInAs("administrator");
    call("sale.order", "search_read", [[]], { fields: ["id"], limit: 1 }).then(([order]) => {
      cy.openRecord({ model: "sale.order", id: order.id });
    });
    cy.get(".o-mail-ChatterPanel").should("be.visible");
  });

  it("resizes by dragging the bar and keeps the width", () => {
    panelWidth().then((before) => {
      cy.get(".o-mail-ChatterPanel .o_resizable_panel_handle").then(($handle) => {
        const { left, top, width } = $handle[0].getBoundingClientRect();
        const center = left + width / 2;
        cy.wrap($handle).trigger("mousedown", { button: 0, clientX: center, clientY: top + 200 });
        cy.document().trigger("mousemove", { clientX: center - DRAG, clientY: top + 200 });
        cy.document().trigger("mouseup");
      });
      panelWidth().should("be.closeTo", before + DRAG, 2);

      cy.reload();
      cy.get(".o-mail-ChatterPanel").should("be.visible");
      panelWidth().should("be.closeTo", before + DRAG, 2);
    });
  });

  it("keeps the width that is shown when dragged past the limit", () => {
    cy.get(".o-mail-ChatterPanel .o_resizable_panel_handle").then(($handle) => {
      const { left, top, width } = $handle[0].getBoundingClientRect();
      const center = left + width / 2;
      cy.wrap($handle).trigger("mousedown", { button: 0, clientX: center, clientY: top + 200 });
      cy.document().trigger("mousemove", { clientX: 0, clientY: top + 200 });
      cy.document().trigger("mouseup");
    });
    panelWidth().should("be.within", 900, 1600 * 0.6 + 1);
    panelWidth().then((shown) => {
      cy.window().then((win) => {
        expect(JSON.parse(win.localStorage.getItem(STORAGE_KEY)).width).to.be.closeTo(shown, 1);
      });
    });
  });

  it("collapses from its top bar to a narrow strip and keeps it collapsed", () => {
    panelWidth().then((width) => {
      cy.get(".o-mail-Chatter-topbar .o-mail-ChatterCollapse").should("have.attr", "aria-expanded", "true").click();
      cy.get(".o-mail-ChatterBody").should("not.be.visible");
      cy.get(".o-mail-ChatterDock").should("be.visible").and("have.attr", "aria-expanded", "false");
      panelWidth().should("be.lessThan", 48);
      cy.get(".o_form_sheet_bg").should(($sheet) => {
        expect($sheet[0].getBoundingClientRect().right).to.be.greaterThan(1600 - 48);
      });

      cy.reload();
      cy.get(".o-mail-ChatterDock").should("be.visible");
      cy.get(".o-mail-ChatterBody").should("not.be.visible");

      cy.get(".o-mail-ChatterDock").click();
      cy.get(".o-mail-ChatterDock").should("not.exist");
      cy.get(".o-mail-ChatterBody").should("be.visible");
      panelWidth().should("be.closeTo", width, 2);
    });
  });

  it("opens ready to send a message and leaves the focus on the form", () => {
    cy.get(".o-mail-Chatter-sendMessage").should("have.class", "active");
    cy.get(".o-mail-Composer-input").should("be.visible").and("not.have.focus");
  });

  it("does not scroll the form to a chatter below it", () => {
    cy.viewport(1280, 800);
    cy.reload();
    cy.get(".o-mail-Chatter .o-mail-Composer-input").should("exist");
    cy.get(".o-mail-ChatterPanel").should("not.exist");
    cy.get(".o_content").should(($content) => expect($content[0].scrollTop).to.equal(0));
  });

  it("works when the browser storage is unavailable", () => {
    cy.window().then((win) => {
      const setItem = win.Storage.prototype.setItem;
      cy.stub(win.Storage.prototype, "setItem").callsFake(function (key, value) {
        if (key === STORAGE_KEY) {
          throw new Error("storage is full");
        }
        return setItem.call(this, key, value);
      });
    });
    cy.get(".o-mail-ChatterCollapse").click();
    cy.get(".o-mail-ChatterBody").should("not.be.visible");
    cy.window().then((win) => expect(win.localStorage.getItem(STORAGE_KEY)).to.be.null);
  });
});
