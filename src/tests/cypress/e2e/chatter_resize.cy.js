import { call, signIn } from "../support/odoo";

const STORAGE_KEY = "sol_theme.chatter";
const DRAG = 120;

const panelWidth = () => cy.get(".o-mail-ChatterPanel").then(($panel) => $panel[0].getBoundingClientRect().width);

describe("Resizable chatter", () => {
  beforeEach(() => {
    // The chatter sits beside the form from 1,400 px wide.
    cy.viewport(1600, 900);
    signIn("demo.administrator");
    call("sale.order", "search_read", [[]], { fields: ["id"], limit: 1 }).then(([order]) => {
      cy.visit(`/odoo/sales/${order.id}`);
    });
    cy.get(".o-mail-ChatterPanel").should("be.visible");
  });

  it("resizes by dragging the bar and keeps the width", () => {
    panelWidth().then((before) => {
      cy.get(".o-mail-ChatterPanel .o_resizable_panel_handle").then(($handle) => {
        const { left, top, width } = $handle[0].getBoundingClientRect();
        const center = left + width / 2;
        cy.wrap($handle).trigger("mousedown", { button: 0, clientX: center, clientY: top + 200 });
        cy.get("body").trigger("mousemove", { force: true, clientX: center - DRAG, clientY: top + 200 });
        cy.get("body").trigger("mouseup", { force: true });
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
      cy.get("body").trigger("mousemove", { force: true, clientX: 0, clientY: top + 200 });
      cy.get("body").trigger("mouseup", { force: true });
    });
    panelWidth().should("be.within", 900, 1600 * 0.6 + 1);
    panelWidth().then((shown) => {
      cy.window().then((win) => {
        expect(JSON.parse(win.localStorage.getItem(STORAGE_KEY)).width).to.be.closeTo(shown, 1);
      });
    });
  });

  it("collapses to give the form the full width and keeps it collapsed", () => {
    panelWidth().then((width) => {
      cy.get(".o-mail-ChatterToggle").should("have.attr", "aria-expanded", "true").click();
      cy.get(".o-mail-ChatterBody").should("not.be.visible");
      cy.get(".o_form_sheet_bg").should(($sheet) => {
        expect($sheet[0].getBoundingClientRect().right).to.be.greaterThan(1600 - 40);
      });

      cy.reload();
      cy.get(".o-mail-ChatterToggle").should("have.attr", "aria-expanded", "false");
      cy.get(".o-mail-ChatterBody").should("not.be.visible");

      cy.get(".o-mail-ChatterToggle").click();
      cy.get(".o-mail-ChatterBody").should("be.visible");
      panelWidth().should("be.closeTo", width, 2);
    });
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
    cy.get(".o-mail-ChatterToggle").click();
    cy.get(".o-mail-ChatterBody").should("not.be.visible");
    cy.window().then((win) => expect(win.localStorage.getItem(STORAGE_KEY)).to.be.null);
  });
});
