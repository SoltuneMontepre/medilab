const DRAG = 120;
const SAMPLE = "sol_demo.demo_sample_bottled_water_testing";
const SAMPLE_TEST = "sol_demo.demo_sample_test_lead_urgent";

const rect = (selector) => cy.get(selector).then(($el) => $el[0].getBoundingClientRect());

// The form beside the audit log keeps most of the width, and its status bar shows every state.
function expectReadableForm() {
  cy.get(".o-mail-ChatterPanel .o_audit_aside").should("be.visible");
  rect(".o-mail-ChatterPanel").then((panel) => {
    rect(".o_form_sheet_bg").then((sheet) => {
      expect(sheet.width).to.be.greaterThan(panel.width);
      expect(sheet.right).to.be.closeTo(panel.left, 1);
      rect(".o_statusbar_status").then((status) => {
        expect(status.left).to.be.at.least(sheet.left);
        expect(status.right).to.be.at.most(sheet.right);
      });
    });
  });
}

describe("Resizable audit log", () => {
  beforeEach(() => {
    cy.signInAs("lab_head");
  });

  it("keeps the sample form readable beside the audit log", () => {
    cy.openRecord(SAMPLE);
    expectReadableForm();
  });

  it("keeps the sample test form readable beside the audit log", () => {
    cy.openRecord(SAMPLE_TEST);
    expectReadableForm();
  });

  it("resizes by dragging the bar and keeps the width", () => {
    cy.openRecord(SAMPLE);
    rect(".o-mail-ChatterPanel").then((before) => {
      cy.get(".o-mail-ChatterPanel .o_resizable_panel_handle").then(($handle) => {
        const { left, top, width } = $handle[0].getBoundingClientRect();
        const center = left + width / 2;
        cy.wrap($handle).trigger("mousedown", { button: 0, clientX: center, clientY: top + 200 });
        cy.document().trigger("mousemove", { clientX: center - DRAG, clientY: top + 200 });
        cy.document().trigger("mouseup");
      });
      rect(".o-mail-ChatterPanel").its("width").should("be.closeTo", before.width + DRAG, 2);

      cy.reload();
      cy.get(".o-mail-ChatterPanel .o_audit_aside").should("be.visible");
      rect(".o-mail-ChatterPanel").its("width").should("be.closeTo", before.width + DRAG, 2);
    });
  });

  it("collapses to give the form the full width and reopens", () => {
    cy.openRecord(SAMPLE);
    rect(".o-mail-ChatterPanel").then((panel) => {
      cy.get(".o-mail-ChatterToggle").should("have.attr", "aria-expanded", "true").and("have.attr", "title", "Collapse the audit log").click();
      cy.get(".o_audit_aside").should("not.be.visible");
      rect(".o_form_sheet_bg").its("right").should("be.greaterThan", 1440 - 40);

      cy.reload();
      cy.get(".o-mail-ChatterToggle").should("have.attr", "aria-expanded", "false");
      cy.get(".o_audit_aside").should("not.be.visible");

      cy.get(".o-mail-ChatterToggle").click();
      cy.get(".o_audit_aside").should("be.visible");
      rect(".o-mail-ChatterPanel").its("width").should("be.closeTo", panel.width, 2);
    });
  });

  it("puts the audit log below the form on a narrow window", () => {
    cy.viewport(1000, 900);
    cy.openRecord(SAMPLE);
    cy.get(".o_audit_aside").should("be.visible");
    cy.get(".o-mail-ChatterPanel").should("not.exist");
    rect(".o_form_sheet_bg").then((sheet) => {
      rect(".o_audit_aside").its("top").should("be.at.least", sheet.bottom - 1);
    });
  });
});
